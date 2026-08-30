"""
Thin shell for the MesoSPIM Controller — composes 7 per-panel widget modules
and retains the safety-critical E-stop kill path.

The shell shrinks from ~1975 LOC to ~400 by delegating per-concern updateUi_*
slots to panel modules (LaserPanelWidget, MotorPanelWidget,
AcquisitionPanelWidget, SavePanelWidget, StackPanelWidget, ScanPanelWidget,
CalibrationPanelWidget). The shell retains:
- All 13 Signal declarations
- hardware_init (HAL handle assignment + timer setup)
- closeEvent (QThread shutdown loop)
- wire_collaborators (panel + collaborator signal connections)
- updateUi_estop_pressed (the E-stop kill path — lock-free, GUI thread)
- updateUi_arm_reset_pressed (two-press re-arm)
- Shell-level slots: message printer, theme, show/hide panes,
  updateUi_initial_hardware_state, close_modes, _cache_auto_laser_flags

The E-stop kill path (estop_event.set() → for laser in self.lasers:
laser.off()) stays synchronous on the GUI thread (AGENTS.md §2). It is NOT
in any panel. The 4 laser daemon threads stay threading.Thread in
laser_panel.py (lock-free E-stop contract).

@authors: Pierre Girard-Collins & flesage
"""

import copy
import logging
import os
import threading
import typing
import webbrowser
from functools import partial

import numpy as np

from PySide6.QtCore import QSize, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QActionGroup, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QButtonGroup,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStyle,
)

from lightsheet.config import cfg_read, cfg_write
from lightsheet.gui.panels.acquisition_panel import AcquisitionPanelWidget
from lightsheet.gui.panels.calibration_panel import CalibrationPanelWidget
from lightsheet.gui.panels.laser_panel import LaserPanelWidget
from lightsheet.gui.panels.motor_panel import MotorPanelWidget
from lightsheet.gui.panels.past_acquisitions_browser import (
    PastAcquisitionsPanel,
)
from lightsheet.gui.panels.properties_dialog import Properties_Dialog
from lightsheet.gui.panels.save_panel import SavePanelWidget
from lightsheet.gui.panels.scan_panel import ScanPanelWidget
from lightsheet.gui.panels.stack_panel import StackPanelWidget
from lightsheet.gui.shell.ui_shell import Ui_Shell
from lightsheet.hal.bundle import DeviceBundle

logger = logging.getLogger(__name__)

# Shell-owned widget objectNames. The ``vars(panel.ui)`` merge loop below
# only surfaces these onto ``self.ui``; panel-internal widgets stay on
# their owning panel's ``ui`` and are reached via the panel-qualified path
# (``self.ui.<name>`` inside a panel, ``self._shell.<panel>.ui.<name>``
# across panels). The shell-owned set covers the safety-critical E-stop
# toolbar (AGENTS.md §2 — the kill path's widget references must never
# strand), the status bar, the message log, the left-rail navigation
# primitives, and the controls/images pane primitives. Most of these live
# on ``Ui_Shell`` via ``setupUi`` (so they are already on ``self.ui`` and
# never appear in a panel's ``vars(panel.ui)``); listing them here is
# harmless and documents the shell-owned surface.
SHELL_OWNED_OBJECTNAMES = frozenset({
    # E-stop toolbar (safety-critical — AGENTS.md §2).
    "toolBar_estop",
    "pushButton_estop",
    "pushButton_armReset",
    "label_estopStatus",
    "label_modeBadge",
    "shortcut_estop",
    # Status bar.
    "statusbar",
    "statusBar_label",
    "statusBar_progress",
    # Message log.
    "plainTextEdit_messageLog",
    # Left-rail navigation + stacked panes (shell-owned).
    "stackedPanels",
    "leftRail",
    "buttonGroup_leftRail",
    "action_followSystemTheme",
    # Controls / images pane primitives.
    "splitter",
    "controlsPane",
    "imagesPane",
    "imageView",
    "centralwidget",
    # View-menu / theme / help actions.
    "action_Exit",
    "action_ShowHideControlsPane",
    "action_ShowHideImagesPane",
    "action_ShowHideMessageLog",
    "action_lightTheme",
    "action_darkTheme",
    "action_showSystemProperties",
    "action_openDocumentation",
    "actionGuidePdf",
    "action_OpenFile",
    # Menus.
    "menuFile",
    "menuDisplay",
    "menuHelp",
    "menu_Select_Theme",
    "menubar",
})

if typing.TYPE_CHECKING:
    from lightsheet.gui.coordinators.acquisition_coordinator import (
        AcquisitionCoordinator,
    )
    from lightsheet.gui.coordinators.frame_saver_controller import FrameSaverController
    from lightsheet.gui.coordinators.hardware_manager import HardwareManager
    from lightsheet.gui.coordinators.motor_controller import MotorController


class Controller_MainWindow(QMainWindow):
    """Thin shell for the MesoSPIM Controller — composes 7 per-panel widget
    modules and retains the safety-critical E-stop kill path."""

    # Default configurable settings. Used as the base for the per-instance
    # cfg_settings dict (deep-copied in __init__ before merging config.ini).
    _cfg_defaults: dict[str, str] = {"Units": "mm", "Image File Format": "HDF5"}

    # Signals
    sig_beep = Signal()
    sig_stylesheet = Signal(str)
    sig_message = Signal(str)
    sig_progress_update = Signal(int)

    sig_single_mode_finished = Signal()
    sig_live_mode_finished = Signal()
    sig_stack_mode_finished = Signal()
    sig_preview_mode_finished = Signal()

    sig_refresh_position_horizontal = Signal()
    sig_refresh_position_vertical = Signal()
    sig_refresh_position_camera = Signal()

    # Per-laser status indicator (LSR-06). QTimer-driven polls and
    # refresh-after-action call sites emit (idx, status) on this signal;
    # the GUI-thread slot updateUi_laser_status (in laser_panel) mutates
    # the QLabel. No QTimer callback or worker thread ever writes a QLabel
    # directly (AGENTS.md §11).
    sig_laser_status = Signal(int, str)

    # Per-laser power readback (LSR-06). _refresh_laser_readback emits
    # (idx, text, tooltip) on this signal from any thread; the GUI-thread
    # slot updateUi_laser_readback (in laser_panel) mutates the readback
    # QLabel. Mirrors sig_laser_status so no worker thread ever writes a
    # QLabel directly (AGENTS.md §11).
    sig_laser_readback = Signal(int, str, str)

    def __init__(
        self,
        bundle: DeviceBundle,
        demo: bool = False,
        fs: "FrameSaverController | None" = None,
        hw: "HardwareManager | None" = None,
        acq: "AcquisitionCoordinator | None" = None,
        mc: "MotorController | None" = None,
    ) -> None:
        # The pre-built DeviceBundle is the sole HAL-handle channel into
        # the shell. The frozen bundle invariant protects the E-stop kill
        # path: a re-bound laser handle after construction would fail to
        # de-energize a live Class IIIB laser.
        self._bundle = bundle
        self._fs = fs
        self._hw = hw
        self._acq = acq
        self._mc = mc
        self._demo_mode = demo

        QMainWindow.__init__(self)

        # Load the shell UI (E-stop toolbar, ImageView, message log,
        # leftRail of 8 checkable QToolButtons + stackedPanels
        # QStackedWidget with a placeholder page). The shell .ui provides
        # the safety toolbar + the left-rail/stacked-pane primitives; the
        # 8 per-panel widgets are composed into stackedPanels
        # programmatically below (each wrapped in a QScrollArea).
        self.ui = Ui_Shell()
        self.ui.setupUi(self)

        # Expose the E-stop widgets as direct attributes for backward
        # compatibility with existing slot code and tests.
        self.toolBar_estop = self.ui.toolBar_estop
        self.label_estopStatus = self.ui.label_estopStatus
        self.pushButton_estop = self.ui.pushButton_estop
        self.pushButton_armReset = self.ui.pushButton_armReset
        self.shortcut_estop = self.ui.shortcut_estop
        # Safety: the E-stop toolbar is fixed (non-movable, non-floatable)
        # so the kill button stays in a predictable location at every
        # window size. The .ui sets both, but enforce programmatically as
        # a belt-and-suspenders guard against a .ui regen losing the
        # property (a floatable toolbar could be dragged off-screen).
        self.toolBar_estop.setMovable(False)
        self.toolBar_estop.setFloatable(False)
        # UI-SPEC §Spacing Scale: lg = 24 px for the E-stop toolbar
        # internal padding. Per-widget stylesheet on the toolbar itself —
        # the E-stop button's own per-widget setStyleSheet overrides at
        # the widget level, so this does not affect the safety-red
        # background (AGENTS.md §2).
        self.toolBar_estop.setStyleSheet(
            "QToolBar { spacing: 24px; padding: 0 24px; }"
        )

        # E-stop cooperative-abort event. Starts clear (not set) so the
        # system boots ARMED. Polled at the top of every acquisition worker
        # loop. The synchronous laser-zeroing happens on the GUI thread in
        # updateUi_estop_pressed, independent of when the worker threads
        # reach their poll point.
        self.estop_event = threading.Event()
        self._estop_disarmed = False

        # Wire the E-stop signal/slot connections. The widget CONSTRUCTION
        # comes from the .ui-generated code; the connections stay explicit
        # in the shell for visibility and testability. The kill-path logic
        # in updateUi_estop_pressed stays synchronous and lock-free.
        self.pushButton_estop.clicked.connect(self.updateUi_estop_pressed)
        self.pushButton_armReset.clicked.connect(self.updateUi_arm_reset_pressed)

        # Two-press re-arm sequence documentation (audit #6). The button
        # label changes per state (Clear E-stop / Arm Lasers / Arm/Reset);
        # the tooltip stays constant and explains the whole sequence so
        # the operator can discover the two-press requirement without
        # trial-and-error on a Class IIIB laser.
        self.pushButton_armReset.setToolTip(
            "Two-press sequence to re-arm after an E-stop. "
            "First press: Clear E-stop (disarm the kill latch). "
            "Second press: Arm Lasers (system ready; lasers still off "
            "until you toggle one or start a run)."
        )

        # F12 hotkey — fires regardless of which widget has focus. The
        # QShortcut is declared in ui_shell.ui (with ApplicationShortcut
        # context); the F12 key sequence is set here because pyside6-uic
        # maps the .ui "shortcut" property to setShortcut() which QShortcut
        # does not have (it uses setKey()).
        self.shortcut_estop.setKey(QKeySequence("F12"))
        self.shortcut_estop.activated.connect(self.updateUi_estop_pressed)

        # --- Compose the 8 per-panel widgets into stackedPanels ---
        # Each panel widget creates its own widgets via its Ui_* class.
        # After creation, the panel's widget attributes are merged onto
        # self.ui so the shell (and tests) can reference any widget via
        # self.ui.<objectName> regardless of which panel owns it. This
        # preserves the monolith's flat widget namespace.
        self.laser_panel = LaserPanelWidget(self)
        self.motor_panel = MotorPanelWidget(self)
        self.acquisition_panel = AcquisitionPanelWidget(self)
        self.stack_panel = StackPanelWidget(self)
        self.scan_panel = ScanPanelWidget(self)
        self.save_panel = SavePanelWidget(self)
        self.calibration_panel = CalibrationPanelWidget(self)
        self.past_panel = PastAcquisitionsPanel(self)

        # The per-field units are now fixed (motor travel in mm, plane
        # step in µm) — the global units toggle is gone. The per-field
        # suffix/decimals are applied via FieldSpec in a later plan; the
        # spinboxes temporarily have no suffix in this intermediate state.

        # Compose the 8 per-panel widgets into stackedPanels (the
        # QStackedWidget that replaces the old tabbed shell). Each panel
        # Each panel is wrapped in a QScrollArea(widgetResizable=True)
        # so it scrolls gracefully on small screens (UI-SPEC QScrollArea
        # Wrapping Rules). Horizontal scrollbar is always off (panels are
        # vertical-scroll only). The page order matches the left-rail
        # button order: Motion(0), Acquire(1), Stack(2), Scan(3),
        # Lasers(4), Files(5), Past(6), Calibrate(7).
        from PySide6.QtWidgets import QScrollArea, QWidget

        def _wrap(panel) -> QScrollArea:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.Shape.NoFrame)
            scroll.setHorizontalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )
            scroll.setVerticalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAsNeeded
            )
            scroll.setWidget(panel)
            return scroll

        # Remove the placeholder page the .ui ships, then add the 8
        # panel-wrapping scroll areas in left-rail order.
        self.ui.stackedPanels.removeWidget(self.ui.stackedPanelsPlaceholder)
        self.ui.stackedPanels.addWidget(_wrap(self.motor_panel))            # 0 Motion
        self.ui.stackedPanels.addWidget(_wrap(self.acquisition_panel))      # 1 Acquire
        self.ui.stackedPanels.addWidget(_wrap(self.stack_panel))            # 2 Stack
        self.ui.stackedPanels.addWidget(_wrap(self.scan_panel))             # 3 Scan
        self.ui.stackedPanels.addWidget(_wrap(self.laser_panel))            # 4 Lasers
        self.ui.stackedPanels.addWidget(_wrap(self.save_panel))             # 5 Files
        # Past (index 6): the dedicated PastAcquisitionsPanel hosts the
        # past-acquisitions browser (parser + async scan worker), the
        # read-only past table, the Planned/Past toggle, and the Refresh
        # button. Wrapped in a QScrollArea per the uniform convention.
        self.ui.stackedPanels.addWidget(_wrap(self.past_panel))             # 6 Past
        self.ui.stackedPanels.addWidget(_wrap(self.calibration_panel))      # 7 Calibrate

        # --- Left-rail navigation wiring ---
        # An exclusive QButtonGroup maps each of the 8 left-rail
        # QToolButtons to a stackedPanels page index. idClicked(int)
        # drives stackedPanels.setCurrentIndex(int) — the canonical Qt
        # left-rail + QStackedWidget navigation pattern. Bare bound-method
        # connection (no lambda) preserves the cycle-break fix.
        self._rail_group = QButtonGroup(self)
        self._rail_group.setExclusive(True)
        _rail_buttons = (
            self.ui.toolButton_railMotion,    # id 0
            self.ui.toolButton_railAcquire,   # id 1
            self.ui.toolButton_railStack,     # id 2
            self.ui.toolButton_railScan,      # id 3
            self.ui.toolButton_railLasers,    # id 4
            self.ui.toolButton_railFiles,     # id 5
            self.ui.toolButton_railPast,      # id 6
            self.ui.toolButton_railCalibrate, # id 7
        )
        for _id, _btn in enumerate(_rail_buttons):
            self._rail_group.addButton(_btn, id=_id)
        self._rail_group.idClicked.connect(self.ui.stackedPanels.setCurrentIndex)
        # Motion is the default active page (matches the .ui's checked
        # property on toolButton_railMotion).
        self.ui.toolButton_railMotion.setChecked(True)
        self.ui.stackedPanels.setCurrentIndex(0)

        # UI-SPEC §Left-Rail Composition: each of the 8 rail buttons gets
        # a 24x24 QStyle.SP_* standard icon + a per-button tooltip
        # following the "{Panel}: {purpose}." pattern. The .ui ships the
        # buttons with toolButtonStyle=ToolButtonTextUnderIcon, which
        # reserves the icon area — setting the icons here fills that area
        # instead of leaving empty space above the label.
        _style = self.style()
        _rail_icon_specs = (
            (self.ui.toolButton_railMotion, QStyle.SP_MediaSkipForward,
             "Motion: Jog the stage and set positions."),
            (self.ui.toolButton_railAcquire, QStyle.SP_MediaPlay,
             "Acquire: Start preview, live, or single-frame acquisition."),
            (self.ui.toolButton_railStack, QStyle.SP_ToolBarHorizontalExtensionButton,
             "Stack: Configure and run a z-stack."),
            (self.ui.toolButton_railScan, QStyle.SP_MediaSeekForward,
             "Scan: Set galvo/ETL scan parameters."),
            (self.ui.toolButton_railLasers, QStyle.SP_DialogYesButton,
             "Lasers: Toggle and set laser power; per-laser status."),
            (self.ui.toolButton_railFiles, QStyle.SP_DialogSaveButton,
             "Files: Set save directory, filename, and format."),
            (self.ui.toolButton_railPast, QStyle.SP_DirOpenIcon,
             "Past: Browse previously saved acquisitions."),
            (self.ui.toolButton_railCalibrate, QStyle.SP_DialogResetButton,
             "Calibrate: Camera/ETL calibration (advanced)."),
        )
        for _btn, _sp_icon, _tooltip in _rail_icon_specs:
            _btn.setIcon(_style.standardIcon(_sp_icon))
            _btn.setIconSize(QSize(24, 24))
            _btn.setToolTip(_tooltip)

        # Merge each panel's SHELL-OWNED widget attributes onto self.ui.
        # Panel-internal widgets stay on their owning panel's ``ui`` and
        # are reached via the panel-qualified path (hybrid ownership,
        # D-05): ``self.ui.<name>`` inside a panel for its own widgets,
        # ``self._shell.<panel>.ui.<name>`` for cross-panel reads. Only
        # the shell-owned widgets are surfaced onto ``self.ui`` so the
        # shell + the E-stop kill path keep a single owner for the
        # safety-critical surface (AGENTS.md §2).
        for panel in (
            self.laser_panel,
            self.motor_panel,
            self.acquisition_panel,
            self.stack_panel,
            self.scan_panel,
            self.save_panel,
            self.calibration_panel,
        ):
            for attr_name in vars(panel.ui):
                if not attr_name.startswith("_") and attr_name in SHELL_OWNED_OBJECTNAMES:
                    setattr(self.ui, attr_name, getattr(panel.ui, attr_name))

        # Per-laser status/readback labels + the L2 Refresh Power button are
        # defined in ui_laser_panel.ui (verticalLayout_43 / verticalLayout_44
        # column layouts) so they share the panel's layout/style. The panel
        # slots reach them via self.ui.label_laser* (panel-local, hybrid
        # ownership). The signal connections below stay explicit in the shell
        # for visibility and testability.
        self.laser_panel.ui.pushButton_laserTwoRefresh.clicked.connect(
            self.laser_panel.updateUi_laser2_refresh_clicked
        )

        # Connect the status/readback signals to the laser panel slots.
        self.sig_laser_status.connect(self.laser_panel.updateUi_laser_status)
        self.sig_laser_readback.connect(self.laser_panel.updateUi_laser_readback)

        # Add label and progress bar to status bar
        self.ui.statusBar_label = QLabel(self.ui.statusbar)
        self.ui.statusBar_progress = QProgressBar(self.ui.statusbar)
        self.ui.statusbar.addPermanentWidget(self.ui.statusBar_label)
        self.ui.statusbar.addPermanentWidget(self.ui.statusBar_progress)
        self.ui.statusBar_progress.setFixedWidth(250)
        self.ui.statusBar_progress.hide()

        # Add first entry to message log
        self.ui.plainTextEdit_messageLog.appendPlainText("-- message log --")

        # LevelsBar → ImageView wiring. The LevelsBar (image-adjacent,
        # below the ImageView) drives two display properties:
        #   sig_levelsChanged (window min/max) → ImageView display clamp
        #   sig_rangeChanged  (range  min/max) → ImageView colormap scaling
        # Both are display-only — saved frames are the raw uint16. The
        # connections use bare bound-method references (no lambda) so the
        # signal system holds no strong ref to the controller after
        # disconnect (the reference-cycle break).
        self.ui.levelsBar.sig_levelsChanged.connect(self._on_levels_changed)
        self.ui.levelsBar.sig_rangeChanged.connect(self._on_range_changed)

        # Set configurable settings to default values
        self.cfg_settings = copy.deepcopy(self._cfg_defaults)
        self.cfg_settings = cfg_read("config.ini", "Controller", self.cfg_settings)

        # Reflect the persisted [Controller] Theme onto the checked action
        # of the exclusive theme QActionGroup (wired above). The read side
        # in __main__.py reads the same key with a "system" default.
        _persisted_theme = str(self.cfg_settings.get("Theme", "system")).lower()
        if _persisted_theme == "light":
            self.ui.action_lightTheme.setChecked(True)
        elif _persisted_theme == "dark":
            self.ui.action_darkTheme.setChecked(True)
        else:
            self.ui.action_followSystemTheme.setChecked(True)

        units_cfg = str(self.cfg_settings.get("Units", "mm"))
        # The global units toggle is gone — per-field units are now fixed
        # (motor travel in mm, plane step in µm). The legacy "Units"
        # config key is retained for backward compatibility but no longer
        # drives a shell attribute; a later plan applies per-field units
        # via FieldSpec.
        _ = units_cfg  # read so cfg_settings stays consistent; no attr set

        fmt_cfg = str(self.cfg_settings["Image File Format"]).lower()
        if fmt_cfg == "tiff":
            self.save_format = "tiff"
        elif fmt_cfg == "zarr":
            self.save_format = "zarr"
        elif fmt_cfg == "both":
            self.save_format = "both"
        else:
            self.save_format = "hdf5"

        # The format radio group is created later in __init__ (after the
        # save panel widgets exist); reflect self.save_format onto the
        # checked radio once the group is wired (see _reflect_save_format_radio).
        self._pending_save_format_reflection = self.save_format

        self.save_directory = os.path.normpath(
            os.path.join(os.path.expanduser("~"), "Desktop", "LightSheetData")
        )
        self.save_filename = ""
        self.save_filepath = ""
        self.save_description = ""
        self.open_directory = ""
        self.dataset_name = ""

        if self.save_directory != "":
            self.save_panel.ui.lineEdit_saveDirectory.setText(self.save_directory)
            self.save_panel.ui.lineEdit_saveFilename.setText(self.save_filename)
            self.save_panel.ui.lineEdit_saveFilename.setEnabled(True)
            self.save_panel.ui.lineEdit_saveDescription.setText(self.save_description)
            self.save_panel.ui.lineEdit_saveDescription.setEnabled(True)
        else:
            self.save_panel.ui.lineEdit_saveDirectory.setText("")
            self.save_panel.ui.lineEdit_saveFilename.setPlaceholderText("Filename - Select Save Directory First")  # noqa: E501
            self.save_panel.ui.lineEdit_saveFilename.setEnabled(False)
            self.save_panel.ui.lineEdit_saveDescription.setPlaceholderText("Description - Select Save Directory First")  # noqa: E501
            self.save_panel.ui.lineEdit_saveDescription.setEnabled(False)

        # Flags
        self.single_mode_started = False
        self.preview_mode_started = False
        self.live_mode_started = False
        self.stack_mode_started = False

        # Operator-facing staged laser power setpoints in percent (0-100).
        self.laser1_power_pct = 0.0
        self.laser2_power_pct = 0.0

        # First-energize confirmation per-session flags (audit #15). Each
        # laser gets its own flag; the dialog gates the FIRST energize of
        # that laser in a session unless the operator clicked "Don't warn
        # again this session" (which sets the flag and skips subsequent
        # dialogs). Cancel does NOT set the flag — the next energize still
        # warns. The flag is per-session (in-memory), not persisted.
        self._laser1_first_energize_done = False
        self._laser2_first_energize_done = False

        # Auto-laser checkbox states sampled on the GUI thread before an
        # acquisition worker starts (AGENTS.md §11).
        self._auto_laser1 = False
        self._auto_laser2 = False

        self.saving_allowed = False
        self.focus_selected = False
        self.horizontal_forward_boundary_selected = False
        self.horizontal_backward_boundary_selected = False
        self.stack_starting_plane = None
        self.stack_ending_plane = None
        self.number_of_planes = 0
        self.stack_step = 0

        # Image display state (referenced by save_panel.updateUi_save_single_image)
        self.image_hor_pos_text = ""
        self.image_ver_pos_text = ""
        self.image_cam_pos_text = ""
        self.buffer = None
        self.reconstructed_frame = None

        self.default_buttons = [
            self.acquisition_panel.ui.pushButton_acqStartPreviewMode,
            self.acquisition_panel.ui.pushButton_acqStartLiveMode,
            self.stack_panel.ui.pushButton_acqStartStackMode,
            self.acquisition_panel.ui.pushButton_acqGetSingleImage,
        ]

        # Initial state of modes buttons
        self.acquisition_panel.ui.pushButton_acqStartPreviewMode.setEnabled(True)
        self.acquisition_panel.ui.pushButton_acqStartLiveMode.setEnabled(True)
        self.stack_panel.ui.pushButton_acqStartStackMode.setEnabled(True)
        self.acquisition_panel.ui.pushButton_acqGetSingleImage.setEnabled(True)
        self.save_panel.ui.pushButton_saveCurrentImage.setEnabled(False)
        self.calibration_panel.ui.pushButton_calCameraComputeFocus.setEnabled(False)
        self.calibration_panel.ui.pushButton_calCameraShowInterpolation.setEnabled(False)
        self.calibration_panel.ui.pushButton_calEtlShowInterpolation.setEnabled(False)

        # Initial state of First and Last plane selection (for Stack Mode).
        # The boundary-set boolean is now a shell flag (the checkboxes were
        # replaced with editable spinboxes). The spinboxes are always
        # enabled so the operator can type a value directly; the
        # editingFinished handler validates against the motor travel
        # limits and rejects with a beep on out-of-range.
        self.stack_first_plane_set = False
        self.stack_last_plane_set = False
        self.stack_panel.ui.pushButton_acqSetFirstPlane.setEnabled(True)
        self.stack_panel.ui.pushButton_acqSetLastPlane.setEnabled(True)

        # Initial state of some file selection buttons
        self.save_panel.ui.pushButton_selectDataset.setEnabled(False)

        # ---
        # Signal connections for progress bar and command log
        # ---
        self.sig_progress_update.connect(self.ui.statusBar_progress.setValue)
        self.sig_progress_update.connect(self._on_progress_update)
        self.sig_message.connect(self.updateUi_message_printer)

        # ---
        # Connections for menu actions
        # ---
        self.ui.action_Exit.triggered.connect(self.close)
        self.ui.action_ShowHideControlsPane.triggered.connect(self.updateUi_show_hide_controls_pane)
        self.ui.action_ShowHideImagesPane.triggered.connect(self.updateUi_show_hide_images_pane)
        self.ui.action_ShowHideMessageLog.triggered.connect(self.updateUi_show_hide_message_log)
        self.ui.action_lightTheme.triggered.connect(self.updateUi_light_theme)
        self.ui.action_darkTheme.triggered.connect(self.updateUi_dark_theme)
        self.ui.action_followSystemTheme.triggered.connect(self.updateUi_follow_system_theme)
        # UI-SPEC §Registry Safety: theme actions are checkable + held in
        # an exclusive QActionGroup so the menu reflects the active theme.
        # action_followSystemTheme is already checkable per the .ui; the
        # other two are made checkable here. The persisted-theme → checked
        # action reflection happens after cfg_settings is loaded below.
        self.ui.action_lightTheme.setCheckable(True)
        self.ui.action_darkTheme.setCheckable(True)
        self._theme_action_group = QActionGroup(self)
        self._theme_action_group.addAction(self.ui.action_lightTheme)
        self._theme_action_group.addAction(self.ui.action_darkTheme)
        self._theme_action_group.addAction(self.ui.action_followSystemTheme)
        self._theme_action_group.setExclusive(True)
        self.ui.action_showSystemProperties.triggered.connect(self.open_properties_dialog)
        self.ui.actionGuidePdf.triggered.connect(self.open_help)

        # Per-field units are now fixed (motor travel in mm, plane step in
        # µm) — the global units toggle that re-rendered both panels on a
        # unit switch is gone. A later plan applies per-field
        # suffix/decimals via FieldSpec.

        # Connection for laser settings changes — target the laser panel slots.
        self.laser_panel.ui.doubleSpinBox_laserOneAmplitude.valueChanged.connect(
            self.laser_panel.updateUi_laser1_amplitude
        )
        self.laser_panel.ui.doubleSpinBox_laserTwoAmplitude.valueChanged.connect(
            self.laser_panel.updateUi_laser2_amplitude
        )

        # Connections for the 'File Manager' tab controls — target save panel.
        self.save_panel.ui.pushButton_selectFile.clicked.connect(self.save_panel.updateUi_select_file)
        self.save_panel.ui.pushButton_selectDataset.clicked.connect(self.save_panel.updateUi_select_dataset)
        self.save_panel.ui.listWidget_fileDatasets.doubleClicked.connect(self.save_panel.updateUi_select_dataset)

        # Connections for the 'Manual Acquisition' controls — target acquisition panel.
        self.acquisition_panel.ui.pushButton_acqGetSingleImage.clicked.connect(
            self.acquisition_panel.updateUi_single_mode_button
        )
        self.acquisition_panel.ui.pushButton_acqStartLiveMode.clicked.connect(
            self.acquisition_panel.updateUi_live_mode_button
        )
        self.acquisition_panel.ui.pushButton_acqStartPreviewMode.clicked.connect(
            self.acquisition_panel.updateUi_preview_mode_button
        )

        # Connections for the 'Automatic Acquisition' controls — target stack panel.
        self.stack_panel.ui.pushButton_acqStartStackMode.clicked.connect(
            self.acquisition_panel.updateUi_stack_mode_button
        )
        self.stack_panel.ui.doubleSpinBox_acqPlaneStepSize.valueChanged.connect(
            self.stack_panel.updateUi_set_number_of_planes
        )
        self.stack_panel.ui.pushButton_acqSetFirstPlane.clicked.connect(
            self.stack_panel.updateUi_set_stack_mode_starting_point
        )
        self.stack_panel.ui.pushButton_acqSetLastPlane.clicked.connect(
            self.stack_panel.updateUi_set_stack_mode_ending_point
        )
        # Manual entry on the first/last plane spinbox validates against
        # the motor travel limits and rejects with a beep on out-of-range
        # (the worker's per-plane ValueError catch is the physical-safety
        # backstop if the soft block slips).
        self.stack_panel.ui.doubleSpinBox_acqFirstPlane.editingFinished.connect(
            self.stack_panel._on_first_plane_edited
        )
        self.stack_panel.ui.doubleSpinBox_acqLastPlane.editingFinished.connect(
            self.stack_panel._on_last_plane_edited
        )

        # Connections for the 'Lasers' controls — target laser panel.
        self.laser_panel.ui.pushButton_laserOneToggle.clicked.connect(self.laser_panel.laser1_toggle_button)
        self.laser_panel.ui.pushButton_laserTwoToggle.clicked.connect(self.laser_panel.laser2_toggle_button)

        # Connections for the 'Save Settings' controls — target save panel.
        self.save_panel.ui.pushButton_saveSelectDirectory.clicked.connect(
            self.save_panel.updateUi_select_directory
        )
        self.save_panel.ui.pushButton_saveCurrentImage.clicked.connect(
            self.save_panel.updateUi_save_single_image
        )

        self.save_option_button_group = QButtonGroup(self)
        self.save_option_button_group.addButton(self.save_panel.ui.radioButton_saveStitch)
        self.save_option_button_group.addButton(self.save_panel.ui.radioButton_saveStitchBlend)
        self.save_option_button_group.addButton(self.save_panel.ui.radioButton_saveAllCrop)
        self.save_option_button_group.addButton(self.save_panel.ui.radioButton_saveAllFull)
        self.save_option_button_group.setExclusive(True)

        # Format radio group — exclusive, session-only (does NOT write
        # config.ini). The slot maps the clicked radio to a lowercase
        # constant and sets self.save_format for the current session.
        self.save_format_button_group = QButtonGroup(self)
        self.save_format_button_group.addButton(self.save_panel.ui.radioButton_saveFormat_hdf5)
        self.save_format_button_group.addButton(self.save_panel.ui.radioButton_saveFormat_zarr)
        self.save_format_button_group.addButton(self.save_panel.ui.radioButton_saveFormat_both)
        self.save_format_button_group.setExclusive(True)
        self.save_format_button_group.buttonClicked.connect(self.updateUi_save_format_changed)
        # Re-estimate every planned-queue row's Est. Size cell when the
        # format radio changes (HDF5 = raw bytes; OME-Zarr = raw L0 +
        # multiscale pyramid overhead; Both = sum). Connected AFTER
        # updateUi_save_format_changed so save_format is updated before
        # the recompute reads it (Qt calls slots in connection order).
        self.save_format_button_group.buttonClicked.connect(
            self.stack_panel.table_manager.recompute_all_rows
        )

        # Reflect the config-driven save_format default onto the checked
        # format radio. "tiff" (legacy) maps to the HDF5 radio as the
        # closest equivalent — tiff is not in the radio group.
        fmt = getattr(self, "_pending_save_format_reflection", "hdf5")
        if fmt == "zarr":
            self.save_panel.ui.radioButton_saveFormat_zarr.setChecked(True)
        elif fmt == "both":
            self.save_panel.ui.radioButton_saveFormat_both.setChecked(True)
        else:
            # hdf5 or tiff (legacy) → HDF5 radio
            self.save_panel.ui.radioButton_saveFormat_hdf5.setChecked(True)

        # ---
        # Signal connections for post modes (threads) Ui updates
        # ---
        self.sig_single_mode_finished.connect(self.acquisition_panel.updateUi_post_single_mode)
        self.sig_live_mode_finished.connect(self.acquisition_panel.updateUi_post_live_mode)
        self.sig_stack_mode_finished.connect(self.acquisition_panel.updateUi_post_stack_mode)
        self.sig_preview_mode_finished.connect(self.acquisition_panel.updateUi_post_preview_mode)

        # ---
        # Signal connections for position refresh requests
        # ---
        self.sig_refresh_position_horizontal.connect(self.motor_panel.updateUi_position_horizontal)
        self.sig_refresh_position_vertical.connect(self.motor_panel.updateUi_position_vertical)
        self.sig_refresh_position_camera.connect(self.motor_panel.updateUi_position_camera)

        # Start single shot timer to complete hardware init after event loop is started
        self.timer_hardware_init = QTimer()
        self.timer_hardware_init.setSingleShot(True)
        self.timer_hardware_init.timeout.connect(self.hardware_init)
        self.timer_hardware_init.start(100)

        # Debounce timers for the laser amplitude spinboxes. The timeout
        # slots are in laser_panel; the timers live on the shell so the
        # panel can reference them via self._shell._laser*_amplitude_timer.
        self._laser1_amplitude_timer = QTimer()
        self._laser1_amplitude_timer.setSingleShot(True)
        self._laser1_amplitude_timer.timeout.connect(self.laser_panel._apply_laser1_amplitude)
        self._laser2_amplitude_timer = QTimer()
        self._laser2_amplitude_timer.setSingleShot(True)
        self._laser2_amplitude_timer.timeout.connect(self.laser_panel._apply_laser2_amplitude)

    def _on_levels_changed(self, levels_min: int, levels_max: int) -> None:
        """Apply a LevelsBar WINDOW handle drag to the ImageView display
        clamp window and re-render."""
        self.ui.imageView.set_levels(levels_min, levels_max)

    def _on_range_changed(self, range_min: int, range_max: int) -> None:
        """Apply a LevelsBar RANGE handle drag (or set_data_range) to the
        ImageView colormap scaling bounds. The range frames the grayscale
        gradient; the window (sig_levelsChanged) clamps the display."""
        self.ui.imageView.set_colormap_range(range_min, range_max)

    def _update_levels_readout(self, frame) -> None:
        """Update the live min/max QLabel readout with the actual pixel
        range of the supplied frame (not the display window), and push the
        data-following range to the LevelsBar so its RANGE handles track
        the frame's dtype bounds (0-65535 for uint16)."""
        if frame is None:
            return
        try:
            lo = int(frame.min())
            hi = int(frame.max())
        except (ValueError, TypeError):
            return
        self.ui.label_levelsReadout.setText(f"min: {lo}   max: {hi}")
        # Push the data-following range to the LevelsBar. For integer
        # dtypes the range is the dtype bounds (0-65535 for uint16); for
        # float dtypes the range is the observed pixel range. set_data_range
        # no-ops when the range is unchanged, so per-frame calls with a
        # constant dtype do not reset the operator's RANGE adjustments.
        try:
            if frame.dtype.kind in ("u", "i"):
                info = np.iinfo(frame.dtype)
                dmin = max(0, int(info.min))
                dmax = int(info.max)
            else:
                dmin, dmax = lo, hi
            self.ui.levelsBar.set_data_range(dmin, dmax)
        except (ValueError, TypeError):
            pass

    def _save_stack_params(self) -> None:
        """Persist the last stack's start/end/step to config.ini so a
        re-run does not required re-driving the stage. Called on close.
        Skipped in demo mode so the test suite (which constructs many
        controllers with demo=True and tears them down concurrently under
        xdist) does not corrupt the real config.ini."""
        if getattr(self, "_demo_mode", False):
            return
        start = self.stack_starting_plane
        end = self.stack_ending_plane
        step = self.stack_panel.ui.doubleSpinBox_acqPlaneStepSize.value()
        cfg_write("config.ini", "Controller", {
            "StackLastStart": "" if start is None else f"{start:.4f}",
            "StackLastEnd": "" if end is None else f"{end:.4f}",
            "StackLastStep": f"{step:.4f}",
        })

    def _load_stack_params(self) -> None:
        """Load the last stack's start/end/step from config.ini and
        populate the spinboxes + set the shell flags if present."""
        cfg = cfg_read("config.ini", "Controller", {
            "StackLastStart": "",
            "StackLastEnd": "",
            "StackLastStep": "",
        })
        start_s = str(cfg.get("StackLastStart", "")).strip()
        end_s = str(cfg.get("StackLastEnd", "")).strip()
        step_s = str(cfg.get("StackLastStep", "")).strip()
        if start_s:
            try:
                self.stack_panel.ui.doubleSpinBox_acqFirstPlane.setValue(float(start_s))
                self.stack_starting_plane = float(start_s)
                self.stack_first_plane_set = True
            except ValueError:
                pass
        if end_s:
            try:
                self.stack_panel.ui.doubleSpinBox_acqLastPlane.setValue(float(end_s))
                self.stack_ending_plane = float(end_s)
                self.stack_last_plane_set = True
            except ValueError:
                pass
        if step_s:
            try:
                self.stack_panel.ui.doubleSpinBox_acqPlaneStepSize.setValue(float(step_s))
            except ValueError:
                pass

    def hardware_init(self) -> None:
        """Completes initialisation of hardware and image consumers.
        Launches timer to periodically refresh image display port (imageView).
        """
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.ui.statusbar.showMessage("Initializing hardware, please wait...")
        self.ui.statusbar.repaint()

        # Instantiating hardware components from the pre-built DeviceBundle.
        # self.lasers is a mutable list copy so the E-stop kill path has a
        # stable reference, while the frozen bundle's tuple cannot be
        # re-bound after construction.
        self.camera = self._bundle.camera
        self.siggen = self._bundle.siggen
        self.motors = self._bundle.motors
        self.etls = self._bundle.etls
        self.lasers = list(self._bundle.lasers)

        # Making sure ETLs are in analog mode
        self.etls.open()
        self.etls.set_analog_mode()

        # Open the Toptica iBeam serial laser (COM4 / self.lasers[1]).
        # Called here (not from HardwareManager.__init__) to preserve the
        # pre-extraction post-show timing.
        self._hw.open_laser2()

        # Update Ui with initial hardware state
        self.updateUi_initial_hardware_state()
        # Now that motors are assigned, seed the stack plane spinbox ranges
        # from the motor travel limits (the soft widget-layer block).
        self.stack_panel._seed_spinbox_ranges()
        # Restore the last stack's start/end/step from config.ini so a
        # re-run does not require re-driving the stage.
        self._load_stack_params()
        # Render the summary for the restored state.
        self.stack_panel._render_stack_plan_summary()

        # FrameSaverController display-port refresh timer
        self.timer_imageview = QTimer()
        self.timer_imageview.timeout.connect(self._fs.frame_viewer.updateUi_refresh_view)
        # Use functools.partial (bound callables) instead of lambdas so
        # the connection does not capture self._hw in a closure cell and
        # create a reference cycle (controller -> timer -> lambda ->
        # self._hw -> self._shell -> controller). This matches the
        # bound-method pattern documented in wire_collaborators.
        self.timer_imageview.timeout.connect(partial(self._hw._poll_laser_status, [0]))
        self.timer_imageview.timeout.connect(partial(self._hw._refresh_laser_readback, 0))
        self.timer_imageview.start(100)

        # L2 (iBeam) status poll — a separate gated QTimer
        _ibeam_cfg = cfg_read("config.ini", "iBeam", {"Status Poll Interval": 1.0})
        self.timer_laser2_status = QTimer()
        self.timer_laser2_status.timeout.connect(self._hw._poll_laser2_status_gated)
        self.timer_laser2_status.start(
            int(float(_ibeam_cfg["Status Poll Interval"]) * 1000)
        )

        # Init done, restore normal cursor.
        QApplication.restoreOverrideCursor()
        if self._demo_mode:
            self.setWindowTitle(self.windowTitle() + " [DEMO]")
            self.ui.statusbar.showMessage(
                "Demo mode — no hardware connected (mock HAL)", 5000
            )
            # Load a bundled sample image in grayscale so the operator
            # can test the contrast slider and levels bar without
            # hardware. The image lives in lightsheet/resources/ so it
            # works on any machine with the repo checked out.
            import os as _os
            _demo_img_path = _os.path.join(
                _os.path.dirname(_os.path.dirname(_os.path.dirname(__file__))),
                "resources", "demo_image.png",
            )
            try:
                from PySide6.QtGui import QImage
                import numpy as _np
                _img = QImage(_demo_img_path)
                if not _img.isNull():
                    # Convert to grayscale numpy array for ImageView.
                    _ptr = _img.convertToFormat(QImage.Format_Grayscale8)
                    _arr_u8 = _np.frombuffer(
                        _ptr.bits(), dtype=_np.uint8
                    ).reshape(_ptr.height(), _ptr.width()).copy()
                    # Scale the 8-bit sample to the microscope's uint16
                    # range (0-65535) so the contrast bar / LevelsBar
                    # shows the full range the operator sees on the rig.
                    # 255 * 257 == 65535, so this maps the 8-bit gradient
                    # onto the full 16-bit span without clipping.
                    _arr = _arr_u8.astype(_np.uint16) * 257
                    self.ui.imageView.setImage(_arr)
                    # Push the demo frame's data range to the LevelsBar
                    # and update the live min/max readout.
                    self._update_levels_readout(_arr)
            except Exception:
                pass  # Missing image file is non-fatal — just no preview
        else:
            self.ui.statusbar.showMessage("Ready", 2000)

        # Set the default splitter ratio to 60/40 (60% image viewer,
        # 40% controls pane). The splitter has no initial sizes in the
        # .ui file, so without this Qt defaults to 50/50.
        _total = self.ui.splitter.width() or 1280
        self.ui.splitter.setSizes([int(_total * 0.6), int(_total * 0.4)])

    def closeEvent(self, event: QCloseEvent) -> None:
        """Making sure that everything is closed when the user exits the software."""
        result = QMessageBox.question(
            self,
            "Confirm Exit...",
            "Are you sure you want to exit ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if result == QMessageBox.StandardButton.Yes:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            self.ui.statusbar.showMessage("Shutting down hardware...")
            self.ui.statusbar.repaint()
            # Persist the last stack's start/end/step so a re-run does not
            # require re-driving the stage.
            self._save_stack_params()
            # Guard: hardware_init may not have run yet (100ms single-shot
            # timer). If the window is closed before it fires, self.lasers /
            # self.camera / self.etls / self.timer_imageview /
            # self.timer_laser2_status are not yet set — skip the hardware
            # shutdown path entirely (nothing to shut down).
            if not hasattr(self, "lasers"):
                # Stop the past-acquisitions browser scan thread even when
                # hardware_init hasn't run yet — past_panel is constructed
                # in __init__ (before hardware_init), so an async scan
                # could be running if the operator opened the Past panel
                # and triggered a scan before closing the window. Without
                # this the QThread is destroyed while still running on
                # app exit (crash).
                self.past_panel.stop_scan()
                self.timer_hardware_init.stop()
                QApplication.restoreOverrideCursor()
                event.accept()
                return
            self.close_modes()
            # Stop the past-acquisitions browser scan thread if it is
            # running — without this the QThread is destroyed while
            # still running on app exit (crash).
            self.past_panel.stop_scan()
            # Stop the frame_saver QThread BEFORE the acquisition threads so
            # h5py.File.close() completes before the camera/etls close.
            self._fs.frame_saver.stop_saving()
            # Shut down all four acquisition worker QThreads via a single
            # uniform quit() + wait(5000) loop. The cooperative poll model
            # means each worker exits on its own at the next loop iteration
            # after close_modes() cleared its mode-started flag. The 4 laser
            # daemon threads stay threading.Thread and are NOT in this loop
            # (lock-free E-stop, AGENTS.md §2).
            for attr in ("_preview_thread", "_live_thread", "_single_thread", "_stack_thread"):  # noqa: E501
                worker_thread = getattr(self, attr, None)
                if worker_thread is not None and worker_thread.isRunning():
                    worker_thread.quit()
                    if not worker_thread.wait(5000):
                        logger.warning(
                            "%s still running after 5s wait "
                            "timeout during closeEvent — proceeding with "
                            "shutdown anyway.",
                            attr,
                        )
            self.camera.close()
            self.etls.close()
            # Laser 2 (iBeam) lifecycle close
            self.lasers[1].close()
            # Stop the display/status timers. Guard each with getattr
            # because a partial hardware_init failure (e.g. self.etls.open()
            # raising after self.lasers is set but before the timers are
            # created) would leave one or both timer attributes unset, and
            # an unguarded .stop() would raise AttributeError and prevent
            # a clean shutdown.
            for timer_attr in ("timer_imageview", "timer_laser2_status"):
                timer = getattr(self, timer_attr, None)
                if timer is not None:
                    timer.stop()
            QApplication.restoreOverrideCursor()
            event.accept()
        else:
            event.ignore()

    @Slot(str)
    def updateUi_message_printer(self, message: str) -> None:
        """Print text in console, in controller text box and in status bar"""
        logger.info(message)
        self.ui.statusbar.showMessage(message, 2000)
        self.ui.plainTextEdit_messageLog.appendPlainText(message)
        self.ui.plainTextEdit_messageLog.verticalScrollBar().setValue(
            self.ui.plainTextEdit_messageLog.verticalScrollBar().maximum()
        )

    @Slot(QAbstractButton)
    def updateUi_save_format_changed(self, button: QAbstractButton) -> None:
        """Map the clicked format radio to a lowercase constant and set
        ``self.save_format`` for the current session. This is session-only
        — it does NOT write config.ini. The config-driven default is
        reflected at startup; the operator override lives until the app
        exits."""
        ui = self.save_panel.ui
        if button is ui.radioButton_saveFormat_hdf5:
            self.save_format = "hdf5"
        elif button is ui.radioButton_saveFormat_zarr:
            self.save_format = "zarr"
        elif button is ui.radioButton_saveFormat_both:
            self.save_format = "both"
        self.sig_message.emit(f"Save format set to {self.save_format} (session only)")

    def open_properties_dialog(self) -> None:
        """Open the dialog window for showing properties"""
        self.properties_dialog = Properties_Dialog(self)
        self.properties_dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.properties_dialog.open()
        self.properties_dialog.get_properties()

    def open_help(self) -> None:
        """Open the operator manual (Guide.pdf, French reference).

        The path is built cross-platform so the Help menu works on the
        Mac dev box as well as the Windows rig.
        """
        guide_pdf = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            os.pardir,
            "Guide.pdf",
        )
        webbrowser.open_new(os.path.abspath(guide_pdf))

    def updateUi_light_theme(self) -> None:
        self.sig_stylesheet.emit("light")
        # UI-SPEC §Theme Contract (D-01): persist the operator's choice to
        # config.ini under [Controller] Theme so it survives restart, and
        # show an ephemeral status-bar hint.
        cfg_write("config.ini", "Controller", {"Theme": "light"})
        self.ui.statusbar.showMessage("Theme: Light (saved).", 3000)
        self.ui.action_lightTheme.setChecked(True)

    def updateUi_dark_theme(self) -> None:
        self.sig_stylesheet.emit("dark")
        cfg_write("config.ini", "Controller", {"Theme": "dark"})
        self.ui.statusbar.showMessage("Theme: Dark (saved).", 3000)
        self.ui.action_darkTheme.setChecked(True)

    def updateUi_follow_system_theme(self) -> None:
        """Emit the 'system' stylesheet token so the theme manager follows
        the operating system's light/dark setting. Mirrors
        updateUi_light_theme / updateUi_dark_theme; the theme manager
        resolves 'system' to the current OS appearance and persists the
        override across sessions."""
        self.sig_stylesheet.emit("system")
        cfg_write("config.ini", "Controller", {"Theme": "system"})
        self.ui.statusbar.showMessage("Theme: Follow System (saved).", 3000)
        self.ui.action_followSystemTheme.setChecked(True)

    def updateUi_show_hide_images_pane(self) -> None:
        """Toggle the images pane via splitter.setSizes() (audit #7).

        The View-menu action and the QSplitter drag are two mechanisms
        that can hide/show a pane. Routing the menu through
        splitter.setSizes() (instead of show()/hide() on the pane widget
        directly) keeps the splitter sizes authoritative — the menu and
        the splitter stay in sync, and childrenCollapsible=False blocks
        handle-drag-to-zero so hiding is via the menu only.

        The pane has a non-zero minimum width (320 px, the D-02d floor),
        so setSizes([0, total]) alone cannot shrink it to 0 — Qt's
        splitter respects the widget minimum. Temporarily setting
        minimumWidth=0 + maximumWidth=0 lets the splitter reach 0 (the
        standard Qt pattern for a collapsible section under
        childrenCollapsible=False); restoring both to their defaults
        (minimum 320, maximum 16777215) lets the splitter allocate
        space again on re-show.
        """
        splitter = self.ui.splitter
        images_pane = self.ui.imagesPane
        # imagesPane is the FIRST widget in the splitter (index 0).
        # A pane is "visible" in the splitter sense when its size > 0.
        images_visible = splitter.sizes()[0] > 0
        total = splitter.width() or sum(splitter.sizes()) or 1
        if images_visible:
            images_pane.setMinimumWidth(0)
            images_pane.setMaximumWidth(0)
            splitter.setSizes([0, total])
            self.ui.action_ShowHideImagesPane.setChecked(False)
        else:
            # Restore the D-02d floor minimum + the Qt default maximum,
            # then a sensible default (50/50 split) on re-show.
            images_pane.setMinimumWidth(320)
            images_pane.setMaximumWidth(16777215)
            half = total // 2
            splitter.setSizes([half, total - half])
            self.ui.action_ShowHideImagesPane.setChecked(True)

    def updateUi_show_hide_controls_pane(self) -> None:
        """Toggle the controls pane via splitter.setSizes() (audit #7).

        Mirrors updateUi_show_hide_images_pane — controlsPane is the
        SECOND widget in the splitter (index 1). The pane has a 360 px
        minimum width (the controls floor), so minimumWidth=0 +
        maximumWidth=0 is used to let the splitter reach 0 on hide.
        """
        splitter = self.ui.splitter
        controls_pane = self.ui.controlsPane
        controls_visible = splitter.sizes()[1] > 0
        total = splitter.width() or sum(splitter.sizes()) or 1
        if controls_visible:
            controls_pane.setMinimumWidth(0)
            controls_pane.setMaximumWidth(0)
            splitter.setSizes([total, 0])
            self.ui.action_ShowHideControlsPane.setChecked(False)
        else:
            controls_pane.setMinimumWidth(360)
            controls_pane.setMaximumWidth(16777215)
            half = total // 2
            splitter.setSizes([total - half, half])
            self.ui.action_ShowHideControlsPane.setChecked(True)

    def updateUi_show_hide_message_log(self) -> None:
        """Toggle the message log via message_splitter.setSizes() (audit #4
        + audit #7 sync pattern).

        Mirrors updateUi_show_hide_images_pane / _controls_pane — the
        message log is now a vertical QSplitter section inside
        controlsPane (message_splitter), not a standalone widget. Routing
        the View-menu toggle through splitter.setSizes() keeps the splitter
        sizes authoritative so the menu and the splitter handle stay in
        sync. childrenCollapsible=False blocks handle-drag-to-zero, so
        hiding is via the menu only (the operator can still drag the log
        taller/shorter, but not collapse it to 0).

        The log has a non-zero minimum height (96 px, ~5 lines), so
        setSizes([total, 0]) alone cannot shrink it to 0 — Qt's splitter
        respects the widget minimum. Temporarily setting minimumHeight=0
        + maximumHeight=0 lets the splitter reach 0 (the standard Qt
        pattern for a collapsible section under
        childrenCollapsible=False); restoring both to their defaults
        (minimum 96, maximum 16777215) lets the splitter allocate space
        again on re-show.

        The log section is the SECOND widget in message_splitter (index
        1). A log section size > 0 means "visible".
        """
        splitter = self.ui.message_splitter
        log = self.ui.plainTextEdit_messageLog
        log_visible = splitter.sizes()[1] > 0
        total = sum(splitter.sizes()) or splitter.height() or 1
        if log_visible:
            log.setMinimumHeight(0)
            log.setMaximumHeight(0)
            splitter.setSizes([total, 0])
            self.ui.action_ShowHideMessageLog.setChecked(False)
        else:
            # Restore the ~5-line default minimum + the Qt default maximum,
            # then a sensible default (96 px log) on re-show.
            log.setMinimumHeight(96)
            log.setMaximumHeight(16777215)
            default_log_height = 96
            splitter.setSizes([total - default_log_height, default_log_height])
            self.ui.action_ShowHideMessageLog.setChecked(True)

    def _update_mode_badge(
        self, mode: str, state: str = "", plane: int = 0, total: int = 0,
        queue_row: int = 0, queue_total: int = 0,
    ) -> None:
        """Update the mode/state badge in the E-stop toolbar.

        The badge mirrors the progress bar value into the badge text so
        the operator never has to look at the status bar mid-run. The
        badge uses QDarkStyle default text color + bold weight — no
        accent color (audit #12).

        Modes:
        - idle → "IDLE"
        - preview → "PREVIEW"
        - live → "LIVE"
        - single → "SINGLE"
        - stack running → "STACK RUNNING — plane {plane}/{total}"
        - stack running in a queue → appended " (row {queue_row}/{queue_total})"
        """
        if mode == "IDLE":
            text = "IDLE"
        elif mode == "PREVIEW":
            text = "PREVIEW"
        elif mode == "LIVE":
            text = "LIVE"
        elif mode == "SINGLE":
            text = "SINGLE"
        elif mode == "STACK":
            n = plane if plane > 0 else 1
            n_total = total if total > 0 else int(getattr(self, "number_of_planes", 0))
            text = f"STACK {state} \u2014 plane {n}/{n_total}" if state else (
                f"STACK RUNNING \u2014 plane {n}/{n_total}"
            )
            if queue_row and queue_total:
                text += f" (row {queue_row}/{queue_total})"
        else:
            text = mode
        self.ui.label_modeBadge.setText(text)

    @Slot(int)
    def _on_progress_update(self, value: int) -> None:
        """Mirror sig_progress_update into the mode badge during a stack
        run so the operator sees 'STACK RUNNING — plane {n}/{N}' without
        looking at the status bar (audit #12). Outside a stack run, the
        progress value is not shown in the badge (the badge reflects the
        mode, set by the mode-start/complete sites). During a queue run,
        the badge appends the row index so the operator sees which row is
        acquiring."""
        if getattr(self, "stack_mode_started", False):
            total = int(getattr(self, "number_of_planes", 0))
            mgr = getattr(self, "stack_panel", None)
            qm = getattr(mgr, "table_manager", None) if mgr else None
            q_row = int(getattr(qm, "_queue_row_index", 0)) + 1 if qm else 0
            q_total = int(getattr(qm, "_queue_rows_total", 0)) if qm else 0
            if qm is not None and getattr(qm, "_queue_active", False):
                self._update_mode_badge(
                    "STACK", "RUNNING", plane=value, total=total,
                    queue_row=q_row, queue_total=q_total,
                )
            else:
                self._update_mode_badge("STACK", "RUNNING", plane=value, total=total)

    def _cache_auto_laser_flags(self) -> None:
        """Sample the auto-laser checkboxes. GUI thread only.

        Acquisition workers run start_lasers()/stop_lasers() off the GUI
        thread and must read these cached bools rather than the widgets,
        which belong to the GUI thread (AGENTS.md §11). Called at every
        mode-*start* entry point that leads to a worker calling
        start_lasers()/stop_lasers().
        """
        self._auto_laser1 = self.laser_panel.ui.checkBox_laserOneAutomatic.isChecked()
        self._auto_laser2 = self.laser_panel.ui.checkBox_laserTwoAutomatic.isChecked()

    def close_modes(self) -> None:
        """Close all thread modes if they are active.

        Do NOT re-sample the auto-laser checkboxes here. The flags were
        cached at mode *start* by the updateUi_*_mode_button handler that
        spawned the worker, and stop_lasers() must use those start-of-run
        flags — not a fresh re-cache. If the operator unchecks an auto-laser
        checkbox mid-run, a re-cache here would flip _auto_laser* to False
        and stop_lasers() would skip that laser, leaving a Class IIIB laser
        energized after the operator pressed Stop.
        """
        if self.preview_mode_started:
            self.preview_mode_started = False
        if self.live_mode_started:
            self.live_mode_started = False
        if self.stack_mode_started:
            self.stack_mode_started = False
        if self.lasers[0].active or self.lasers[1].active:
            self._hw.stop_lasers()

    def wire_collaborators(self) -> None:
        """Wire the collaborator-dependent signal connections.

        MUST be called by the composition root (main() and the
        make_controller test fixture) AFTER self._mc / self._acq /
        self._hw / self._fs are assigned — never from __init__, where
        those attrs are still None (two-phase init). Connecting bare
        bound methods (e.g. ``self._mc.updateUi_move_sample_up``)
        instead of lambda wrappers breaks the reference cycle at the
        connection layer.
        """
        # ---
        # Connections for the 'Motion' tab controls (MotorController)
        # ---
        self.motor_panel.ui.pushButton_sampleStepUp.clicked.connect(self._mc.updateUi_move_sample_up)
        self.motor_panel.ui.pushButton_sampleStepDown.clicked.connect(self._mc.updateUi_move_sample_down)
        self.motor_panel.ui.pushButton_sampleStepForward.clicked.connect(self._mc.updateUi_move_sample_forward)
        self.motor_panel.ui.pushButton_sampleStepBackward.clicked.connect(self._mc.updateUi_move_sample_backward)
        self.motor_panel.ui.pushButton_sampleGotoOrigin.clicked.connect(self._mc.updateUi_move_sample_to_origin)
        self.motor_panel.ui.pushButton_sampleSetOrigin.clicked.connect(self._mc.updateUi_set_sample_origin)
        self.motor_panel.ui.pushButton_sampleGotoHPosition.clicked.connect(self._mc.updateUi_move_to_horizontal_position)
        self.motor_panel.ui.pushButton_sampleGotoVPosition.clicked.connect(self._mc.updateUi_move_to_vertical_position)

        # Connections for the camera motion buttons
        self.motor_panel.ui.pushButton_cameraGotoPosition.clicked.connect(self._mc.updateUi_move_camera_to_position)
        self.motor_panel.ui.pushButton_cameraSetFocus.clicked.connect(self._mc.updateUi_set_camera_focus)
        self.motor_panel.ui.pushButton_cameraStepForward.clicked.connect(self._mc.updateUi_move_camera_forward)
        self.motor_panel.ui.pushButton_cameraStepBackward.clicked.connect(self._mc.updateUi_move_camera_backward)

        # ---
        # Connections for the 'Scan Settings' tab controls
        # (AcquisitionCoordinator)
        # ---
        self.scan_panel.ui.doubleSpinBox_etlLeftAmplitude.valueChanged.connect(self._acq.updateUi_etl_left_amplitude)
        self.scan_panel.ui.doubleSpinBox_etlRightAmplitude.valueChanged.connect(self._acq.updateUi_etl_right_amplitude)
        self.scan_panel.ui.doubleSpinBox_etlLeftOffset.valueChanged.connect(self._acq.updateUi_etl_left_offset)
        self.scan_panel.ui.doubleSpinBox_etlRightOffset.valueChanged.connect(self._acq.updateUi_etl_right_offset)
        self.scan_panel.ui.checkBox_etlSync.stateChanged.connect(self._acq.updateUi_etl_sync)
        self.scan_panel.ui.checkBox_etlActivate.stateChanged.connect(self._acq.updateUi_etl_activate)
        self.scan_panel.ui.doubleSpinBox_etlSteps.valueChanged.connect(self._acq.updateUi_etl_steps)

        # Connection for galvo settings changes
        self.scan_panel.ui.doubleSpinBox_galvoLeftAmplitude.valueChanged.connect(self._acq.updateUi_galvo_left_amplitude)
        self.scan_panel.ui.doubleSpinBox_galvoRightAmplitude.valueChanged.connect(self._acq.updateUi_galvo_right_amplitude)
        self.scan_panel.ui.doubleSpinBox_galvoLeftOffset.valueChanged.connect(self._acq.updateUi_galvo_left_offset)
        self.scan_panel.ui.doubleSpinBox_galvoRightOffset.valueChanged.connect(self._acq.updateUi_galvo_right_offset)
        self.scan_panel.ui.checkBox_galvoSync.stateChanged.connect(self._acq.updateUi_galvo_sync)
        self.scan_panel.ui.checkBox_galvoActivate.stateChanged.connect(self._acq.updateUi_galvo_activate)
        self.scan_panel.ui.checkBox_galvoInvert.stateChanged.connect(self._acq.updateUi_galvo_invert)

        # Connection for camera settings changes
        self.acquisition_panel.ui.comboBox_cameraShutterMode.currentTextChanged.connect(self._acq.updateUi_camera_shutter_mode)
        self.acquisition_panel.ui.doubleSpinBox_cameraExposureTime.valueChanged.connect(self._acq.updateUi_camera_exposure_time)
        self.acquisition_panel.ui.doubleSpinBox_cameraLineTime.valueChanged.connect(self._acq.updateUi_camera_line_time)
        self.acquisition_panel.ui.doubleSpinBox_cameraExposedLines.valueChanged.connect(self._acq.updateUi_camera_exposed_lines)
        self.acquisition_panel.ui.doubleSpinBox_cameraDelayLines.valueChanged.connect(self._acq.updateUi_camera_delay_lines)

        # ---
        # Connections for the 'Calibration' tab controls (MotorController)
        # ---
        self.calibration_panel.ui.pushButton_calCameraComputeFocus.clicked.connect(self._mc.calculate_camera_focus)
        self.calibration_panel.ui.pushButton_calCameraShowInterpolation.clicked.connect(self._mc.show_camera_interpolation)
        self.calibration_panel.ui.pushButton_calEtlShowInterpolation.clicked.connect(self._mc.show_etl_interpolation)
        self.calibration_panel.ui.pushButton_calHorizontalStartRangeSelection.clicked.connect(self._mc.updateUi_reset_boundaries)
        self.calibration_panel.ui.pushButton_calHorizontalSetForwardLimit.clicked.connect(self._mc.updateUi_set_horizontal_forward_boundary)
        self.calibration_panel.ui.pushButton_calHorizontalSetBackwardLimit.clicked.connect(self._mc.updateUi_set_horizontal_backward_boundary)

    @Slot()
    def updateUi_estop_pressed(self) -> None:
        """E-stop button / F12 hotkey handler.

        Synchronously zeroes both lasers on the GUI thread the instant it
        fires, then sets the cooperative-abort Event so worker threads stop
        acquiring new frames at their next poll point. Idempotent (re-press
        re-sets the Event and re-writes 0 V). Never re-energizes — re-arming
        requires the two-press Arm/Reset sequence in
        updateUi_arm_reset_pressed.

        The kill path is synchronous (no thread/queue offload) so a Class
        IIIB laser is driven off the instant the handler fires. The E-stop
        path is intentionally lock-free — a stuck toggle thread must never
        delay the kill path (AGENTS.md §2).
        """
        # 1. Cooperative-abort Event — workers poll this at the top of
        #    live_mode_worker, before acquire_scan in single_mode_worker,
        #    and alongside stack_mode_started in stack_mode_worker.
        self.estop_event.set()
        # 2. Drive BOTH lasers off synchronously on the GUI thread.
        #    Each backend's off() catches its own SDK errors internally and
        #    sets laser.error rather than re-raising, so a try/except here
        #    can never fire for a hardware failure. Check the error surface
        #    after each off() and warn the operator explicitly that the
        #    laser may still be emitting — never silently show a clean state.
        for laser in self.lasers:
            laser.off()
            if laser.error:
                self.sig_message.emit(
                    f"E-STOP: {laser.label} off command failed — may "
                    f"STILL BE ON. Manually verify before approaching the "
                    f"microscope. Cause: {laser.error_message}"
                )
                laser.error = 0
        # Refresh-after-action: both status labels reflect the post-E-stop
        # state. Deferred via QTimer.singleShot(0, ...) so the GUI thread
        # releases within ~1 ms of the press — the synchronous kill loop
        # above (estop_event.set() + laser.off()) is the only blocking
        # work, and it is lock-free. The L2 (iBeam) readback is a ~3s
        # serial round-trip on the rig; calling it synchronously froze
        # the GUI for the duration of every E-stop press (G-07-4). The
        # kill loop itself (laser.off() above) stays in the shell, direct
        # on self.lasers, lock-free — only the post-kill *refresh* is
        # deferred (AGENTS.md §2 — the kill path is never offloaded).
        QTimer.singleShot(0, lambda: self._hw._poll_laser_status([0, 1]))
        QTimer.singleShot(0, lambda: self._hw._refresh_laser_readback(0))
        QTimer.singleShot(0, self._hw._refresh_laser2_readback_async)

        # 4. Latch the UI into ACTUATED: red indicator, yellow 4px border
        #    on the E-stop button. The Arm/Reset button label reflects the
        #    NEXT action available — "Clear E-stop" (the first press of the
        #    two-press re-arm sequence, audit #6).
        self.label_estopStatus.setText("● E-STOP ACTUATED")
        self.label_estopStatus.setStyleSheet("color: #FF3B30; font-weight: bold;")
        self.pushButton_estop.setStyleSheet(
            "QPushButton { background-color: #FF3B30; color: white; "
            "font-size: 18px; font-weight: bold; border: 4px solid #FFC107; }"
        )
        self.pushButton_armReset.setText("Clear E-stop")

        # 5. Warn the operator. Re-energizing requires Arm/Reset then Arm.
        self.sig_message.emit(
            "E-STOP actuated — all lasers driven to 0 V and the acquisition "
            "was aborted. Press Arm/Reset, then Arm, to re-enable lasers."
        )

        # 6. The E-stop button is checkable (setCheckable(True) in the .ui).
        # Clear the checked state so the button does not stay visually
        # pressed after the momentary action — the actuated state is shown
        # by the red indicator label + yellow border stylesheet above, not
        # by the button's checked state.
        self.pushButton_estop.setChecked(False)

    @Slot()
    def updateUi_arm_reset_pressed(self) -> None:
        """Arm/Reset button handler — the two-press re-arm sequence.

        State machine (audit #6 — made explicit on screen):

            ARMED --(E-stop)--> ACTUATED --(1st press)--> DISARMED --(2nd press)--> ARMED

        First press (while ACTUATED, button labeled "Clear E-stop"):
        clears the E-stop Event and transitions to DISARMED (gray
        indicator, button label -> "Arm Lasers"). Lasers are NOT
        re-energized — they stay off until the operator explicitly
        toggles one or starts an acquisition.

        Second press (while DISARMED, button labeled "Arm Lasers"):
        transitions back to ARMED (green indicator, button label ->
        "Arm/Reset"). The system is now ready; energizing still requires
        a separate deliberate action.

        A single press from ACTUATED must NOT re-arm — it transitions to
        DISARMED first (no single-press re-arm of a Class IIIB laser,
        AGENTS.md §2).

        Never re-energizes a laser itself.
        """
        if self._estop_disarmed:
            # Second press: re-arm. System returns to ARMED; lasers stay
            # off until the operator explicitly toggles one or starts a
            # run.
            self._estop_disarmed = False
            self.label_estopStatus.setText("● ARMED")
            self.label_estopStatus.setStyleSheet("color: #34C759; font-weight: bold;")
            self.pushButton_estop.setStyleSheet(
                "QPushButton { background-color: #FF3B30; color: white; "
                "font-size: 18px; font-weight: bold; border: 2px solid black; }"
            )
            self.pushButton_armReset.setText("Arm/Reset")
            self.sig_message.emit(
                "System armed. Lasers stay off until you toggle one or "
                "start a run."
            )
        else:
            # First press after an E-stop: clear the cooperative-abort
            # Event and transition to DISARMED. Lasers remain off. A
            # single press from ACTUATED does NOT re-arm — the second
            # press (above) is required (AGENTS.md §2).
            self.estop_event.clear()
            self._estop_disarmed = True
            self.label_estopStatus.setText("● DISARMED")
            self.label_estopStatus.setStyleSheet("color: #8E8E93; font-weight: bold;")
            # UI-SPEC §Safety-Critical Invariant: the E-stop button
            # background stays safety-red in ALL states (ARMED, DISARMED,
            # ACTUATED) — only the border changes. The DISARMED state is
            # communicated by the gray status label above, NOT by graying
            # out the button (a gray E-stop is harder to spot in an
            # emergency).
            self.pushButton_estop.setStyleSheet(
                "QPushButton { background-color: #FF3B30; color: white; "
                "font-size: 18px; font-weight: bold; border: 2px solid black; }"
            )
            self.pushButton_armReset.setText("Arm Lasers")
            self.sig_message.emit(
                "E-stop cleared. Press Arm Lasers to re-arm."
            )

    def updateUi_initial_hardware_state(self) -> None:
        # SigGen
        self.scan_panel.ui.checkBox_galvoActivate.setChecked(self.siggen.galvo_activated)
        self.scan_panel.ui.checkBox_galvoInvert.setChecked(self.siggen.galvo_inverted)
        self.scan_panel.ui.doubleSpinBox_galvoLeftAmplitude.setValue(self.siggen.galvo_left_amplitude)
        self.scan_panel.ui.doubleSpinBox_galvoRightAmplitude.setValue(self.siggen.galvo_right_amplitude)
        self.scan_panel.ui.doubleSpinBox_galvoLeftOffset.setValue(self.siggen.galvo_left_offset)
        self.scan_panel.ui.doubleSpinBox_galvoRightOffset.setValue(self.siggen.galvo_right_offset)

        self.scan_panel.ui.checkBox_etlActivate.setChecked(self.siggen.etl_activated)
        self.scan_panel.ui.doubleSpinBox_etlLeftAmplitude.setValue(self.siggen.etl_left_amplitude)
        self.scan_panel.ui.doubleSpinBox_etlRightAmplitude.setValue(self.siggen.etl_right_amplitude)
        self.scan_panel.ui.doubleSpinBox_etlLeftOffset.setValue(self.siggen.etl_left_offset)
        self.scan_panel.ui.doubleSpinBox_etlRightOffset.setValue(self.siggen.etl_right_offset)
        self.scan_panel.ui.doubleSpinBox_etlSteps.setValue(self.siggen.etl_steps)

        # Camera
        self.acquisition_panel.ui.doubleSpinBox_cameraExposureTime.setValue(
            self.camera.exposure_time * 1e3
        )  # camera(s) to ui(ms)
        self.acquisition_panel.ui.doubleSpinBox_cameraLineTime.setValue(
            self.camera.lightsheet_line_time * 1e6
        )  # camera(s) to ui(us)
        self.acquisition_panel.ui.doubleSpinBox_cameraExposedLines.setValue(
            self.camera.lightsheet_exposed_lines
        )
        self.acquisition_panel.ui.doubleSpinBox_cameraDelayLines.setValue(
            self.camera.lightsheet_delay_lines
        )
        # Set camera shutter mode comboBox options (default: Rolling)
        self.acquisition_panel.ui.comboBox_cameraShutterMode.insertItems(0, ["Rolling", "Lightsheet"])
        if self.camera.shutter_mode == "Lightsheet":
            self.acquisition_panel.ui.comboBox_cameraShutterMode.setCurrentIndex(1)
        else:
            self.acquisition_panel.ui.comboBox_cameraShutterMode.setCurrentIndex(0)
        self._acq.updateUi_camera_shutter_mode()

        # Lasers — both spinboxes are 0-100 % staged setpoints. Seed from
        # the persistent controller-side percentage, not the live HAL state,
        # so the staged value survives laser on/off and E-stop disarm/re-arm
        # cycles within the session.
        self.laser_panel.ui.doubleSpinBox_laserOneAmplitude.setValue(self.laser1_power_pct)
        self.laser_panel.ui.doubleSpinBox_laserTwoAmplitude.setValue(self.laser2_power_pct)

        # Wavelength labels — read from the live list[ILaser] instances.
        self.laser_panel.ui.label_72.setText(
            f'<html><head/><body><p><span style=" font-weight:600; font-size:18px;">'
            f"{self.lasers[0].wavelength} nm</span></p></body></html>"
        )
        self.laser_panel.ui.label_73.setText(
            f'<html><head/><body><p><span style=" font-weight:600; font-size:18px;">'
            f"{self.lasers[1].wavelength} nm</span></p></body></html>"
        )

        # Toggle button text + tooltips so the operator can find each laser
        # by wavelength rather than the generic "Laser1"/"Laser2" placeholder.
        self.laser_panel.ui.pushButton_laserOneToggle.setText(
            f"Toggle {self.lasers[0].wavelength} nm"
        )
        self.laser_panel.ui.pushButton_laserTwoToggle.setText(
            f"Toggle {self.lasers[1].wavelength} nm"
        )
        self.laser_panel.ui.pushButton_laserOneToggle.setToolTip(
            f"Toggle {self.lasers[0].wavelength} nm laser (DAQ AO Dev7/ao0)"
        )
        self.laser_panel.ui.pushButton_laserTwoToggle.setToolTip(
            f"Toggle Toptica iBeam ({self.lasers[1].wavelength} nm, COM4)"
        )

        # Motors — refresh the position indicators with the fixed mm
        # display unit. The global units toggle is gone; per-field units
        # are fixed (motor travel in mm). The spinbox suffix/decimals are
        # applied via FieldSpec in a later plan.
        self.motor_panel.updateUi_position_indicators()
