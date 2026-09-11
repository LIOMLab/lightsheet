"""Thin shell for the MesoSPIM Controller — composes per-panel widget modules
and retains the safety-critical E-stop kill path.

The E-stop kill path (estop_event.set() -> for laser in self.lasers:
laser.off()) stays synchronous and lock-free on the GUI thread.

@authors: Pierre Girard-Collins & flesage
"""

from __future__ import annotations

import copy
import logging
import threading
import typing
from functools import partial
from pathlib import Path
from typing import ClassVar

import numpy as np
from PySide6.QtCore import QEvent, QRect, QSize, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import (
    QActionGroup,
    QCloseEvent,
    QFontMetrics,
    QIcon,
    QKeySequence,
    QPainter,
    QPalette,
)
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QProgressDialog,
    QStyle,
    QStyleOptionToolButton,
    QToolButton,
)

from lightsheet import CONFIG_PATH
from lightsheet.config import cfg_read
from lightsheet.gui.coordinators.adaptive_dock_controller import (
    AdaptiveDockController,
)
from lightsheet.gui.coordinators.focus_dock_controller import (
    FocusDockController,
)
from lightsheet.gui.panels.acquisition_panel import AcquisitionPanelWidget
from lightsheet.gui.panels.calibration_panel import CalibrationPanelWidget
from lightsheet.gui.panels.laser_panel import LaserPanelWidget
from lightsheet.gui.panels.motor_panel import MotorPanelWidget
from lightsheet.gui.panels.past_acquisitions_browser import (
    PastAcquisitionsPanel,
)
from lightsheet.gui.panels.save_panel import SavePanelWidget
from lightsheet.gui.panels.scan_panel import ScanPanelWidget
from lightsheet.gui.panels.stack_panel import StackPanelWidget
from lightsheet.gui.shell.ui_delegates import _ShellUiDelegatesMixin
from lightsheet.gui.shell.ui_shell import Ui_Shell
from lightsheet.gui.styles import colors as _c
from lightsheet.gui.styles import spacing as _s
from lightsheet.gui.styles import symbols as _sym
from lightsheet.gui.styles import typography as _t
from lightsheet.gui.widgets.channel_radio import ChannelRadio
from lightsheet.hal.bundle import DeviceBundle
from lightsheet.state import MicroscopeState

logger = logging.getLogger(__name__)


def _center_toolbutton_paint(btn: QToolButton) -> None:
    """Center the icon and text within the full button width.

    macOS Aqua left-aligns the icon under ToolButtonTextUnderIcon and clips
    the text to the icon width. Draw the button chrome, then paint icon+text
    centered ourselves.
    """
    icon = btn.icon()
    icon_size = btn.iconSize()
    text = btn.text()
    style = btn.style()

    def _paint(_event: QEvent) -> None:
        p = QPainter(btn)
        opt = QStyleOptionToolButton()
        opt.initFrom(btn)
        opt.features = QStyleOptionToolButton.ToolButtonFeature.None_
        # Draw only button chrome; we paint the centered icon+text below.
        opt.toolButtonStyle = Qt.ToolButtonStyle.ToolButtonIconOnly
        opt.text = ""
        opt.icon = QIcon()
        opt.iconSize = icon_size
        style.drawComplexControl(QStyle.ComplexControl.CC_ToolButton, opt, p, btn)
        cr = btn.rect()
        icon_h = icon_size.height()
        text_h = QFontMetrics(btn.font()).height()
        gap = 4
        total = icon_h + gap + text_h
        icon_y = cr.top() + max(0, (cr.height() - total) // 2)
        text_y = icon_y + icon_h + gap
        pix = icon.pixmap(icon_size)
        # Use icon_size for centering, not pix.width() — on HiDPI pix.width()
        # can return the physical width (2x) and offset the icon.
        icon_w = icon_size.width()
        p.drawPixmap(cr.left() + (cr.width() - icon_w) // 2, icon_y, pix)
        p.setPen(btn.palette().color(QPalette.ColorRole.ButtonText))
        p.drawText(
            QRect(cr.left(), text_y, cr.width(), text_h),
            int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop),
            text,
        )

    btn.paintEvent = _paint  # ty: ignore[invalid-assignment]


# Anti-clipping padding added to the mode badge's font-metric width so the
# label's internal text margins do not clip the widest mode string.
_MODE_BADGE_HPADDING_PX = 10

# Shell-owned widget objectNames. Only these are surfaced onto self.ui via
# the vars(panel.ui) merge loop; panel-internal widgets stay on their owning
# panel's ui. Covers the safety-critical E-stop toolbar, status bar, message
# log, left-rail navigation, and controls/images pane primitives.
SHELL_OWNED_OBJECTNAMES = frozenset(
    {
        # E-stop toolbar (safety-critical).
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
    }
)

if typing.TYPE_CHECKING:
    from lightsheet.gui.coordinators.acquisition_coordinator import (
        AcquisitionCoordinator,
    )
    from lightsheet.gui.coordinators.frame_saver_controller import FrameSaverController
    from lightsheet.gui.coordinators.hardware_manager import HardwareManager
    from lightsheet.gui.coordinators.motor_controller import MotorController
    from lightsheet.gui.panels.past_acquisitions_browser import (
        PastAcquisitionEntry,
    )
    from lightsheet.hal.interfaces import ICamera, IETLs, ILaser, IMotors, ISigGen


class Controller_MainWindow(_ShellUiDelegatesMixin, QMainWindow):
    """Thin shell composing per-panel widget modules; retains the E-stop kill path."""

    # Default configurable settings. Used as the base for the per-instance
    # cfg_settings dict (deep-copied in __init__ before merging config.ini).
    _cfg_defaults: ClassVar[dict[str, str]] = {
        "Units": "mm",
        "Image File Format": "HDF5",
    }

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

    # Per-laser status indicator. Workers/timers emit (idx, status); the
    # GUI-thread slot mutates the QLabel. Workers must not touch GUI widgets
    # directly; emit signals instead.
    sig_laser_status = Signal(int, str)

    # Per-laser power readback. Emitted from any thread; the GUI-thread slot
    # mutates the readback QLabel. Workers must not touch GUI widgets directly.
    sig_laser_readback = Signal(int, str, str)

    # Collaborator references (set by ``main()`` / the test fixture after
    # construction; cast to non-optional for the type checker because the
    # production and test composition roots always populate them before use).
    # The generated ``Ui_Shell`` gains runtime attributes (statusBar_*,
    # message_splitter, etc.) beyond the .ui file, so treat it as ``Any``
    # to keep the codebase ty-clean without maintaining a parallel type stub.
    ui: typing.Any

    _fs: FrameSaverController
    _hw: HardwareManager
    _acq: AcquisitionCoordinator
    _mc: MotorController

    # HAL device references (set in ``hardware_init``).
    camera: ICamera
    siggen: ISigGen
    motors: IMotors
    etls: IETLs
    lasers: list[ILaser]

    # Worker threads / worker objects (created on first acquisition button click).
    _preview_thread: QThread | None = None
    _preview_worker: typing.Any | None = None
    _live_thread: QThread | None = None
    _live_worker: typing.Any | None = None
    _single_thread: QThread | None = None
    _single_worker: typing.Any | None = None
    _stack_thread: QThread | None = None
    _stack_worker: typing.Any | None = None

    def __init__(
        self,
        bundle: DeviceBundle,
        demo: bool = False,
        fs: FrameSaverController | None = None,
        hw: HardwareManager | None = None,
        acq: AcquisitionCoordinator | None = None,
        mc: MotorController | None = None,
    ) -> None:
        # The frozen DeviceBundle is the sole HAL-handle channel. A re-bound
        # laser handle after construction would fail to de-energize a live
        # Class IIIB laser in the E-stop kill path.
        self._bundle = bundle
        self._fs = typing.cast("FrameSaverController", fs)
        self._hw = typing.cast("HardwareManager", hw)
        self._acq = typing.cast("AcquisitionCoordinator", acq)
        self._mc = typing.cast("MotorController", mc)
        self._demo_mode = demo

        QMainWindow.__init__(self)

        # GUI-thread-owned observable state model. Constructed before panels
        # so compatibility properties (laser1_power_pct, _auto_laser*, etc.)
        # and the model's snapshot source are available to all widgets. The
        # model sanitizes a non-positive/non-finite HAL line time to a safe
        # fallback internally so a bad config value cannot crash startup.
        self.state = MicroscopeState(
            lightsheet_line_time_s=bundle.camera.lightsheet_line_time,
            parent=self,
        )

        # Load the shell UI (E-stop toolbar, ImageView, message log, leftRail
        # + stackedPanels). The 8 per-panel widgets are composed into
        # stackedPanels programmatically below.
        self.ui = typing.cast(typing.Any, Ui_Shell())
        self.ui.setupUi(self)

        # Expose the E-stop widgets as direct attributes for back-compat.
        self.toolBar_estop = self.ui.toolBar_estop
        self.label_estopStatus = self.ui.label_estopStatus
        self.pushButton_estop = self.ui.pushButton_estop
        self.pushButton_armReset = self.ui.pushButton_armReset

        # Apply semantic color tokens and color-blind-safe bullets to the
        # E-stop toolbar; the .ui defaults are overridden so the single
        # source of truth lives in the styles modules.
        self.label_estopStatus.setText(f"{_sym.ESTOP_ARMED} ARMED")
        self.label_estopStatus.setStyleSheet(f"color: {_c.SUCCESS}; {_t.BOLD}")
        self.pushButton_estop.setText("E-STOP")
        # pushButton_estop toolTip is set in ui_shell.ui and must stay
        # verbatim with the UI-SPEC copywriting contract.
        self.pushButton_estop.setStyleSheet(
            f"QPushButton {{ background-color: {_c.DANGER}; color: {_c.ON_DANGER}; "
            f"{_t.HEADING} border: 2px solid {_c.BREEZE_BG}; }}"
        )
        self.pushButton_estop.setIcon(
            QApplication.style().standardIcon(
                QStyle.StandardPixmap.SP_MessageBoxWarning
            )
        )
        self.shortcut_estop = self.ui.shortcut_estop
        # Safety: E-stop toolbar is fixed (non-movable, non-floatable) so the
        # kill button stays in a predictable location.
        self.toolBar_estop.setMovable(False)
        self.toolBar_estop.setFloatable(False)
        # lg spacing for the E-stop toolbar; the button's own stylesheet
        # overrides at the widget level.
        self.toolBar_estop.setStyleSheet(
            f"QToolBar {{ spacing: {_s.XL}px; padding: 0 {_s.XL}px; }}"
        )

        # E-stop cooperative-abort event. Starts clear so the system boots
        # ARMED. Polled at the top of every acquisition worker loop; the
        # synchronous laser-zeroing happens on the GUI thread.
        self.estop_event = threading.Event()
        self._estop_disarmed = False

        # Pause cooperative-suspend event, a peer of estop_event — never
        # wrapped or aliased to it. Set by the stack panel's Pause button;
        # the stack worker polls it at each plane boundary and exits
        # through the normal teardown, finalizing the resume manifest as
        # "paused" so the run can be resumed later through the queue.
        self.pause_requested = threading.Event()

        # Wire the E-stop signal/slot connections explicitly in the shell.
        self.pushButton_estop.clicked.connect(self.updateUi_estop_pressed)
        self.pushButton_armReset.clicked.connect(self.updateUi_arm_reset_pressed)

        # Two-press re-arm tooltip explains the sequence so the operator can
        # discover the requirement without trial-and-error on a Class IIIB laser.
        self.pushButton_armReset.setToolTip(
            "Two-press sequence to re-arm after an E-stop. "
            "First press: Clear E-stop (disarm the kill latch). "
            "Second press: Arm Lasers (system ready; lasers still off "
            "until you toggle one or start a run)."
        )

        # F12 hotkey — fires regardless of focus. The key sequence is set
        # here because pyside6-uic maps the .ui "shortcut" property to
        # setShortcut() which QShortcut does not have (it uses setKey()).
        self.shortcut_estop.setKey(QKeySequence("F12"))
        self.shortcut_estop.activated.connect(self.updateUi_estop_pressed)

        # --- Compose the 8 per-panel widgets into stackedPanels ---
        # Each panel creates its own widgets; afterwards the panel's widget
        # attributes are merged onto self.ui to preserve the flat namespace.
        self.laser_panel = LaserPanelWidget(self)
        self.motor_panel = MotorPanelWidget(self)
        self.acquisition_panel = AcquisitionPanelWidget(self)
        self.stack_panel = StackPanelWidget(self)
        self.scan_panel = ScanPanelWidget(self)
        self.save_panel = SavePanelWidget(self)
        self.calibration_panel = CalibrationPanelWidget(self)
        self.past_panel = PastAcquisitionsPanel(self)
        self.past_panel.past_acquisitions_scan_finished.connect(
            self._on_startup_scan_finished
        )

        # Per-field units are now fixed (motor travel in mm, plane step in µm);
        # the global units toggle is gone.

        # Compose the 8 per-panel widgets into stackedPanels. Each panel is
        # wrapped in a QScrollArea(widgetResizable=True) for small screens
        # (horizontal scrollbar off). Page order matches the left-rail order:
        # Motion(0), Acquire(1), Stack(2), Scan(3), Lasers(4), Files(5),
        # Past(6), Calibrate(7).
        from PySide6.QtWidgets import QScrollArea, QWidget

        def _wrap(panel: QWidget) -> QScrollArea:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.Shape.NoFrame)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            # Zero the panel's top-level layout margins so content aligns
            # edge-to-edge with the message log sibling in the splitter.
            layout = panel.layout()
            if layout is not None:
                layout.setContentsMargins(_s.ZERO, _s.ZERO, _s.ZERO, _s.ZERO)
            scroll.setWidget(panel)
            return scroll

        # Remove the placeholder page, then add the 8 panel scroll areas in
        # left-rail order.
        self.ui.stackedPanels.removeWidget(self.ui.stackedPanelsPlaceholder)
        self.ui.stackedPanels.addWidget(_wrap(self.motor_panel))  # 0 Motion
        self.ui.stackedPanels.addWidget(_wrap(self.acquisition_panel))  # 1 Acquire
        self.ui.stackedPanels.addWidget(_wrap(self.stack_panel))  # 2 Stack
        self.ui.stackedPanels.addWidget(_wrap(self.scan_panel))  # 3 Scan
        self.ui.stackedPanels.addWidget(_wrap(self.laser_panel))  # 4 Lasers
        self.ui.stackedPanels.addWidget(_wrap(self.save_panel))  # 5 Files
        # Past (index 6): hosts the past-acquisitions browser, read-only
        # past table, Planned/Past toggle, and Refresh button.
        self.ui.stackedPanels.addWidget(_wrap(self.past_panel))  # 6 Past
        self.ui.stackedPanels.addWidget(_wrap(self.calibration_panel))  # 7 Calibrate

        # --- Left-rail navigation wiring ---
        # Exclusive QButtonGroup maps each rail button to a stackedPanels
        # page index. Bare bound-method connection preserves the cycle-break fix.
        self._rail_group = QButtonGroup(self)
        self._rail_group.setExclusive(True)
        _rail_buttons = (
            self.ui.toolButton_railMotion,  # id 0
            self.ui.toolButton_railAcquire,  # id 1
            self.ui.toolButton_railStack,  # id 2
            self.ui.toolButton_railScan,  # id 3
            self.ui.toolButton_railLasers,  # id 4
            self.ui.toolButton_railFiles,  # id 5
            self.ui.toolButton_railPast,  # id 6
            self.ui.toolButton_railCalibrate,  # id 7
        )
        for _id, _btn in enumerate(_rail_buttons):
            self._rail_group.addButton(_btn, id=_id)
        self._rail_group.idClicked.connect(self.ui.stackedPanels.setCurrentIndex)
        # Motion is the default active page.
        self.ui.toolButton_railMotion.setChecked(True)
        self.ui.stackedPanels.setCurrentIndex(0)

        # Each rail button gets a 24x24 standard icon + tooltip.
        _style = self.style()
        _rail_icon_specs = (
            (
                self.ui.toolButton_railMotion,
                QStyle.StandardPixmap.SP_MediaSkipForward,
                "Motion: Jog the stage and set positions.",
            ),
            (
                self.ui.toolButton_railAcquire,
                QStyle.StandardPixmap.SP_MediaPlay,
                "Acquire: Start preview, live, or single-frame acquisition.",
            ),
            (
                self.ui.toolButton_railStack,
                QStyle.StandardPixmap.SP_ToolBarHorizontalExtensionButton,
                "Stack: Configure and run a z-stack.",
            ),
            (
                self.ui.toolButton_railScan,
                QStyle.StandardPixmap.SP_MediaSeekForward,
                "Scan: Set galvo/ETL scan parameters.",
            ),
            (
                self.ui.toolButton_railLasers,
                QStyle.StandardPixmap.SP_DialogYesButton,
                "Lasers: Toggle and set laser power; per-laser status.",
            ),
            (
                self.ui.toolButton_railFiles,
                QStyle.StandardPixmap.SP_DialogSaveButton,
                "Files: Set save directory, filename, and format.",
            ),
            (
                self.ui.toolButton_railPast,
                QStyle.StandardPixmap.SP_DirOpenIcon,
                "Past: Browse previously saved acquisitions.",
            ),
            (
                self.ui.toolButton_railCalibrate,
                QStyle.StandardPixmap.SP_DialogResetButton,
                "Calibrate: Camera/ETL calibration (advanced).",
            ),
        )
        _RAIL_ACTIVE_STYLE = (
            f"QToolButton:checked {{ background-color: {_c.BREEZE_ACCENT}; "
            f"color: {_c.BREEZE_FG}; border: 1px solid {_c.BREEZE_BG}; }}"
            f"QToolButton:hover {{ background-color: {_c.HOVER}; }}"
        )
        for _btn, _sp_icon, _tooltip in _rail_icon_specs:
            _btn.setIcon(_style.standardIcon(_sp_icon))
            _btn.setIconSize(QSize(_s.XL, _s.XL))
            _btn.setToolTip(_tooltip)
            _btn.setStatusTip(_tooltip)
            _btn.setStyleSheet(_RAIL_ACTIVE_STYLE)
            _center_toolbutton_paint(_btn)

        # Adaptive trajectory dock rail button — NOT part of the
        # exclusive page-switching QButtonGroup. It is a conditional
        # toggle: hidden until adaptive mode is enabled, then visible
        # so the operator can re-open the dock after closing it without
        # having to toggle the adaptive checkbox off and on. Checked
        # state mirrors dock visibility.
        self.ui.toolButton_railAdaptive.setIcon(
            _style.standardIcon(QStyle.StandardPixmap.SP_MediaVolume)
        )
        self.ui.toolButton_railAdaptive.setIconSize(QSize(_s.XL, _s.XL))
        self.ui.toolButton_railAdaptive.setToolTip(
            "Adaptive: Toggle the trajectory dock visibility."
        )
        self.ui.toolButton_railAdaptive.setStatusTip(
            "Adaptive: Toggle the trajectory dock visibility."
        )
        self.ui.toolButton_railAdaptive.setStyleSheet(_RAIL_ACTIVE_STYLE)
        _center_toolbutton_paint(self.ui.toolButton_railAdaptive)
        # The toggled connection is wired after the adaptive dock
        # controller is constructed later in __init__.

        # Focus trajectory dock rail button — same conditional pattern as
        # the adaptive rail button: hidden until focus is enabled, then
        # visible so the operator can open the focus trajectory dock on
        # demand. Checked state mirrors the dock's visibility.
        self.ui.toolButton_railFocus.setIcon(
            _style.standardIcon(QStyle.StandardPixmap.SP_MediaPause)
        )
        self.ui.toolButton_railFocus.setIconSize(QSize(_s.XL, _s.XL))
        self.ui.toolButton_railFocus.setToolTip(
            "Focus: Toggle the focus trajectory dock visibility."
        )
        self.ui.toolButton_railFocus.setStatusTip(
            "Focus: Toggle the focus trajectory dock visibility."
        )
        self.ui.toolButton_railFocus.setStyleSheet(_RAIL_ACTIVE_STYLE)
        _center_toolbutton_paint(self.ui.toolButton_railFocus)
        # The toggled connection is wired after the focus dock
        # controller is constructed later in __init__.

        # Merge each panel's SHELL-OWNED widget attributes onto self.ui so
        # the shell + E-stop kill path keep a single owner for the
        # safety-critical surface.
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
                if (
                    not attr_name.startswith("_")
                    and attr_name in SHELL_OWNED_OBJECTNAMES
                ):
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
        # Let the status bar size the progress bar with its default size policy.
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

        # Auto-fit the levels window to the first frame's observed min/max
        # so the initial image is visible at a sensible contrast (the
        # ImageView defaults to a 0-20000 window which makes a full-range
        # uint16 demo image render mostly white). Set once on the first
        # frame; subsequent frames keep the operator's adjustments.
        self._levels_autofit_done = False

        # Set configurable settings to default values
        self.cfg_settings = copy.deepcopy(self._cfg_defaults)
        self.cfg_settings = cfg_read(str(CONFIG_PATH), "Controller", self.cfg_settings)

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
        if fmt_cfg == "zarr":
            self.save_format = "zarr"
        elif fmt_cfg == "both":
            self.save_format = "both"
        else:
            self.save_format = "hdf5"

        # The format radio group is created later in __init__ (after the
        # save panel widgets exist); reflect self.save_format onto the
        # checked radio once the group is wired (see _reflect_save_format_radio).
        self._pending_save_format_reflection = self.save_format

        self.save_directory = str(Path.home() / "Desktop" / "LightSheetData")
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
            self.save_panel.ui.lineEdit_saveFilename.setPlaceholderText(
                "Filename - Select Save Directory First"
            )
            self.save_panel.ui.lineEdit_saveFilename.setEnabled(False)
            self.save_panel.ui.lineEdit_saveDescription.setPlaceholderText(
                "Description - Select Save Directory First"
            )
            self.save_panel.ui.lineEdit_saveDescription.setEnabled(False)

        # Flags
        self.single_mode_started = False
        self.preview_mode_started = False
        self.live_mode_started = False
        self.stack_mode_started = False

        self.focus_mode_started = False

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
        # acquisition worker starts.
        self._auto_laser1 = False
        self._auto_laser2 = False

        self.saving_allowed = False
        self.focus_selected = False
        self.horizontal_forward_boundary_selected = False
        self.horizontal_backward_boundary_selected = False

        # Focus / calibration transient state (populated by MotorController).
        # Typed as ``typing.Any`` because these are set by calibration methods
        # before use; the exact shapes vary across focus and ETL pipelines.
        self.slope_camera: typing.Any = None
        self.intercept_camera: typing.Any = None
        self.camera_focus_relation: typing.Any = None
        self.focus_forward_boundary: typing.Any = None
        self.focus_backward_boundary: typing.Any = None
        self.etl_l_relation: typing.Any = None
        self.etl_r_relation: typing.Any = None
        self.donnees: typing.Any = None
        self.xdata: list[typing.Any] = []
        self.ydata: list[typing.Any] = []
        self.popt: list[typing.Any] = []
        self.number_of_calibration_planes: int = 0
        self.number_of_camera_positions: int = 0
        self.number_of_etls_points: int = 0

        # Live position text updated by MotorController for display/image metadata.
        self.current_horizontal_position_text: str = ""
        self.current_vertical_position_text: str = ""
        self.current_camera_position_text: str = ""
        self.stack_starting_plane = None
        self.stack_ending_plane = None
        self.number_of_planes = 0
        self.stack_step: int | float = 0
        # Resume offset for the current stack run; the acquisition panel
        # stamps it before the worker spawns and the mode badge reads it
        # back. 0 = fresh run (no resume offset).
        self._start_plane: int = 0
        # Queue row currently executing (None outside a queue run); the
        # per-acquisition manifest picks it up at set_files time.
        self.stack_queue_row_index: int | None = None
        # Set True at the end of hardware_init (deferred via a 100ms
        # single-shot timer from __init__). Acquisition entry points gate
        # on this so the deferred hardware_init cannot fire mid-acquisition
        # and clobber stack params (e.g. _load_stack_params' step-spinbox
        # setValue triggers updateUi_set_number_of_planes, which re-reads
        # the first-plane spinbox and overwrites stack_starting_plane).
        self._hardware_initialized = False

        # One-shot startup notification for incomplete acquisitions. Set
        # True briefly during the post-hardware_init scan so the scan
        # completion slot can show a notification-only dialog if any
        # resumable acquisitions are found.
        self._startup_notification_pending = False

        # Image display state (referenced by save_panel.updateUi_save_single_image)
        self.image_hor_pos_text = ""
        self.image_ver_pos_text = ""
        self.image_cam_pos_text = ""
        self.buffer = None
        self.reconstructed_frame = None
        # Multi-channel per-channel frames dict. Populated by
        # SingleWorker.run / StackWorker.run multi-channel branch, keyed
        # by laser wavelength (int nm). reconstructed_frame stays as an
        # alias to the last channel's frame for back-compat with
        # existing single-field consumers (save_panel, display).
        self.reconstructed_frames: dict[int, np.ndarray] = {}

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
        self.calibration_panel.ui.pushButton_calCameraShowInterpolation.setEnabled(
            False
        )
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
        self.ui.action_ShowHideControlsPane.triggered.connect(
            self.updateUi_show_hide_controls_pane
        )
        self.ui.action_ShowHideImagesPane.triggered.connect(
            self.updateUi_show_hide_images_pane
        )
        self.ui.action_ShowHideMessageLog.triggered.connect(
            self.updateUi_show_hide_message_log
        )
        self.ui.action_lightTheme.triggered.connect(self.updateUi_light_theme)
        self.ui.action_darkTheme.triggered.connect(self.updateUi_dark_theme)
        self.ui.action_followSystemTheme.triggered.connect(
            self.updateUi_follow_system_theme
        )
        # Theme actions are checkable + held in an exclusive QActionGroup.
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
        self.ui.action_showSystemProperties.triggered.connect(
            self.open_properties_dialog
        )
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
        self.save_panel.ui.pushButton_selectFile.clicked.connect(
            self.save_panel.updateUi_select_file
        )
        self.save_panel.ui.pushButton_selectDataset.clicked.connect(
            self.save_panel.updateUi_select_dataset
        )
        self.save_panel.ui.listWidget_fileDatasets.doubleClicked.connect(
            self.save_panel.updateUi_select_dataset
        )

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
        self.stack_panel.ui.pushButton_acqPauseStack.clicked.connect(
            self.acquisition_panel.on_stack_pause_clicked
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
        self.laser_panel.ui.pushButton_laserOneToggle.clicked.connect(
            self.laser_panel.laser1_toggle_button
        )
        self.laser_panel.ui.pushButton_laserTwoToggle.clicked.connect(
            self.laser_panel.laser2_toggle_button
        )

        # Connections for the 'Save Settings' controls — target save panel.
        self.save_panel.ui.pushButton_saveSelectDirectory.clicked.connect(
            self.save_panel.updateUi_select_directory
        )
        self.save_panel.ui.pushButton_saveCurrentImage.clicked.connect(
            self.save_panel.updateUi_save_single_image
        )

        self.save_option_button_group = QButtonGroup(self)
        self.save_option_button_group.addButton(
            self.save_panel.ui.radioButton_saveStitch
        )
        self.save_option_button_group.addButton(
            self.save_panel.ui.radioButton_saveStitchBlend
        )
        self.save_option_button_group.addButton(
            self.save_panel.ui.radioButton_saveAllCrop
        )
        self.save_option_button_group.addButton(
            self.save_panel.ui.radioButton_saveAllFull
        )
        self.save_option_button_group.setExclusive(True)
        # Save-mode radios + description line edit commit to the reactive
        # model; the model projects back through sig_save_options_changed.
        self.save_option_button_group.buttonClicked.connect(
            self.save_panel.updateUi_save_mode
        )
        # buttonClicked only fires on real clicks; toggled covers
        # programmatic setChecked so model and widgets cannot diverge.
        for _radio in self.save_panel._radio_by_mode.values():
            _radio.toggled.connect(self.save_panel.updateUi_save_mode_checked)
        self.save_panel.ui.lineEdit_saveDescription.editingFinished.connect(
            self.save_panel.updateUi_save_description
        )
        # Seed the model once from the actual post-setup widget defaults,
        # then render through the model so widget and model cannot diverge
        # at startup.
        self.state.set_save_options(self.save_panel.save_options_from_widgets())
        self.save_panel.updateUi_save_options_from_state(self.state.save_options)

        # Format radio group — exclusive, session-only (does NOT write
        # config.ini). The slot maps the clicked radio to a lowercase
        # constant and sets self.save_format for the current session.
        self.save_format_button_group = QButtonGroup(self)
        self.save_format_button_group.addButton(
            self.save_panel.ui.radioButton_saveFormat_hdf5
        )
        self.save_format_button_group.addButton(
            self.save_panel.ui.radioButton_saveFormat_zarr
        )
        self.save_format_button_group.addButton(
            self.save_panel.ui.radioButton_saveFormat_both
        )
        self.save_format_button_group.setExclusive(True)
        self.save_format_button_group.buttonClicked.connect(
            self.updateUi_save_format_changed
        )
        # Re-estimate every planned-queue row's Est. Size cell when the
        # format radio changes (HDF5 = raw bytes; OME-Zarr = raw L0 +
        # multiscale pyramid overhead; Both = sum). Connected AFTER
        # updateUi_save_format_changed so save_format is updated before
        # the recompute reads it (Qt calls slots in connection order).
        self.save_format_button_group.buttonClicked.connect(
            self.stack_panel.table_manager.recompute_all_rows
        )

        # Reflect the config-driven save_format default onto the checked
        # format radio. Only hdf5, zarr, and both are supported; the
        # catch-all else maps any non-zarr/non-both value to the HDF5 radio.
        fmt = getattr(self, "_pending_save_format_reflection", "hdf5")
        if fmt == "zarr":
            self.save_panel.ui.radioButton_saveFormat_zarr.setChecked(True)
        elif fmt == "both":
            self.save_panel.ui.radioButton_saveFormat_both.setChecked(True)
        else:
            # hdf5 (or any unexpected value) → HDF5 radio
            self.save_panel.ui.radioButton_saveFormat_hdf5.setChecked(True)

        # ---
        # Signal connections for post modes (threads) Ui updates
        # ---
        self.sig_single_mode_finished.connect(
            self.acquisition_panel.updateUi_post_single_mode
        )
        self.sig_live_mode_finished.connect(
            self.acquisition_panel.updateUi_post_live_mode
        )
        self.sig_stack_mode_finished.connect(
            self.acquisition_panel.updateUi_post_stack_mode
        )
        self.sig_preview_mode_finished.connect(
            self.acquisition_panel.updateUi_post_preview_mode
        )

        # ---
        # Signal connections for position refresh requests
        # ---
        self.sig_refresh_position_horizontal.connect(
            self.motor_panel.updateUi_position_horizontal
        )
        self.sig_refresh_position_vertical.connect(
            self.motor_panel.updateUi_position_vertical
        )
        self.sig_refresh_position_camera.connect(
            self.motor_panel.updateUi_position_camera
        )

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
        self._laser1_amplitude_timer.timeout.connect(
            self.laser_panel._apply_laser1_amplitude
        )
        self._laser2_amplitude_timer = QTimer()
        self._laser2_amplitude_timer.setSingleShot(True)
        self._laser2_amplitude_timer.timeout.connect(
            self.laser_panel._apply_laser2_amplitude
        )

        # --- adaptive trajectory dock ---
        # Presentation-only controller builds/owns the floating dock and
        # the per-plane trajectory plot. The shell retains the
        # GUI-thread slot that the worker signal connects to.
        self._adaptive_dock_state_key = "ui/adaptiveTrajectoryDockState"
        self._adaptive_dock_controller = AdaptiveDockController(self)
        # Shell-visible aliases for AcquisitionPanelWidget and tests.
        self.dockWidget_adaptiveTrajectory = self._adaptive_dock_controller.dock
        self.adaptiveTrajectoryWidget = self._adaptive_dock_controller.widget
        self.plotWidget_adaptiveTrajectory = (
            self._adaptive_dock_controller.plotWidget_adaptiveTrajectory
        )
        self.label_adaptiveTrajectoryEmpty = (
            self._adaptive_dock_controller.label_adaptiveTrajectoryEmpty
        )
        # Rail toggle was deferred until the controller existed.
        self.ui.toolButton_railAdaptive.toggled.connect(
            self._adaptive_dock_controller.on_rail_adaptive_toggled
        )

        # --- focus trajectory dock ---
        # Presentation-only controller builds/owns the focus floating dock
        # and the per-block trajectory plot.
        self._focus_dock_state_key = "ui/focusTrajectoryDockState"
        self._focus_dock_controller = FocusDockController(self)
        self.dockWidget_focusTrajectory = self._focus_dock_controller.dock
        self.focusTrajectoryWidget = self._focus_dock_controller.widget
        self.plotWidget_focusTrajectory = (
            self._focus_dock_controller.plotWidget_focusTrajectory
        )
        self.label_focusTrajectoryEmpty = (
            self._focus_dock_controller.label_focusTrajectoryEmpty
        )
        # Rail toggle was deferred until the controller existed.
        self.ui.toolButton_railFocus.toggled.connect(
            self._focus_dock_controller.on_rail_focus_toggled
        )

        # Restore the persisted dock state (geometry + dock-widget-area)
        # from QSettings. This is the dock-state persistence reversibility
        # concern noted in — QSettings, not config.ini, so demo
        # tests do not write config.ini.
        self._adaptive_dock_controller.restore_state()
        self._focus_dock_controller.restore_state()
        # restoreState applies saved dock *visibility* too: each call
        # re-applies the whole saved window state, so a dock persisted
        # open by a previous run would auto-open here. Docks are opt-in
        # per session — re-hide both so only the rail buttons open them.
        self._adaptive_dock_controller.dock.hide()
        self._focus_dock_controller.dock.hide()

        # Wire the adaptive + focus enable toggles on the stack panel to
        # show/hide their trajectory docks. Both handlers now live on their
        # respective dock controllers.
        self.stack_panel.ui.checkBox_adaptiveEnable.toggled.connect(
            self._adaptive_dock_controller.on_adaptive_enabled_toggled
        )
        self.stack_panel.ui.checkBox_focusEnable.toggled.connect(
            self._focus_dock_controller.on_focus_enabled_toggled
        )
        # Sync the conditional rail button visibility with the initial
        # focus-enabled state (e.g. when restored from config.ini). The
        # dock stays hidden until the operator explicitly opens it.
        self._focus_dock_controller.on_focus_enabled_toggled(
            self.stack_panel.ui.checkBox_focusEnable.isChecked()
        )
        # The mode badge min width accommodates the longest single-line
        # mode string: "ADAPTIVE RUNNING — plane 999/999 (row 3/5)
        # · MULTI-CH". It is measured from the label's font at
        # construction so the badge reserves the full width before the
        # first mode render.
        _badge_fm = QFontMetrics(self.ui.label_modeBadge.font())
        _badge_widest = (
            "ADAPTIVE RUNNING \u2014 plane 999/999 (row 3/5) \u00b7 MULTI-CH"
        )
        self.ui.label_modeBadge.setMinimumWidth(
            _badge_fm.horizontalAdvance(_badge_widest) + _MODE_BADGE_HPADDING_PX
        )

    def _on_levels_changed(self, levels_min: int, levels_max: int) -> None:
        """Apply a LevelsBar WINDOW handle drag to the ImageView display
        clamp window and re-render."""
        self.ui.imageView.set_levels(levels_min, levels_max)
        self._update_levels_handle_readout()

    def _on_range_changed(self, range_min: int, range_max: int) -> None:
        """Apply a LevelsBar RANGE handle drag (or set_data_range) to the
        ImageView colormap scaling bounds. The range frames the grayscale
        gradient; the window (sig_levelsChanged) clamps the display."""
        self.ui.imageView.set_colormap_range(range_min, range_max)
        self._update_levels_handle_readout()

    def _update_levels_handle_readout(self) -> None:
        """Show the current RANGE and WINDOW handle values in the readout
        label so the operator sees the values change during a drag."""
        lb = self.ui.levelsBar
        self.ui.label_levelsReadout.setText(
            f"range: {lb.range_min}-{lb.range_max}   "
            f"window: {lb.window_min}-{lb.window_max}"
        )

    def _update_levels_readout(self, frame: np.ndarray) -> None:
        """Update the live min/max QLabel readout with the actual pixel
        range of the supplied frame (not the display window), and push the
        data-following range to the LevelsBar so its RANGE handles track
        the frame's dtype bounds (0-65535 for uint16).

        On the first frame, auto-fit the WINDOW (levels) to the frame's
        observed min/max so the initial image is visible at a sensible
        contrast — the ImageView defaults to a 0-20000 window which makes
        a full-range uint16 frame render mostly white. After the first
        frame the operator owns the window; later frames do not reset it.
        """
        if frame is None:
            return
        try:
            lo = int(frame.min())
            hi = int(frame.max())
        except (ValueError, TypeError):
            return
        # Show the frame's observed pixel range AND the current handle
        # values so the operator sees both the data range and the
        # display window/range in one readout.
        lb = self.ui.levelsBar
        self.ui.label_levelsReadout.setText(
            f"frame: {lo}-{hi}   "
            f"range: {lb.range_min}-{lb.range_max}   "
            f"window: {lb.window_min}-{lb.window_max}"
        )
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
        # Auto-fit the window to the first frame's observed range. Use a
        # small percentile guard so a single saturated pixel does not
        # stretch the window to the full dtype range (e.g. one hot pixel
        # at 65535 would otherwise make the rest of the frame black).
        if not self._levels_autofit_done and hi > lo:
            self._levels_autofit_done = True
            self.ui.levelsBar.window_min = lo
            self.ui.levelsBar.window_max = hi

    def hardware_init(self) -> None:
        """Completes initialisation of hardware and image consumers.
        Launches timer to periodically refresh image display port (imageView).
        """
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self._hw_progress = QProgressDialog(
            "Initializing hardware, please wait...",
            "",
            0,
            0,
            self,
        )
        self._hw_progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        self._hw_progress.setMinimumDuration(0)
        self._hw_progress.show()
        QApplication.processEvents()
        self.ui.statusbar.showMessage("Initializing hardware, please wait...")
        self.ui.statusbar.repaint()

        try:
            # Instantiating hardware components from the pre-built DeviceBundle.
            # self.lasers is a mutable list copy so the E-stop kill path has a
            # stable reference, while the frozen bundle's tuple cannot be
            # re-bound after construction.
            self.camera = self._bundle.camera
            self.siggen = self._bundle.siggen
            self.motors = self._bundle.motors
            self.etls = self._bundle.etls
            self.lasers = list(self._bundle.lasers)

            # Arm a NI-DAQmx hardware watchdog so a process crash or a
            # hung acquisition worker leaves the laser AO channels at
            # their safe off-voltage. The watchdog is armed by the
            # acquisition worker at run start and disarmed in its
            # finally block; a hung worker or a dead process lets the
            # DAQ expire the timer and write the safe voltage.
            from lightsheet.hal.real.laser_watchdog import LaserWatchdog

            self._laser_watchdog = LaserWatchdog(self.lasers)

            # Give every laser a back-reference to the E-stop event so on() can
            # re-check it immediately before the HAL energization write. The kill
            # path (laser.off()) remains synchronous and lock-free in its contract
            # with the shell; this is an extra guard inside the laser itself.
            for laser in self.lasers:
                laser._estop_event = self.estop_event

            # Making sure ETLs are in analog mode
            self.etls.open()
            self.etls.set_analog_mode()

            # Open the Toptica iBeam serial laser (COM4 / self.lasers[1]).
            # Called here (not from HardwareManager.__init__) to preserve the
            # pre-extraction post-show timing.
            self._hw.open_laser2()

            # Update Ui with initial hardware state
            self.updateUi_initial_hardware_state()
            # Channel-radio (L1/L2 display selector) for the ImageView area.
            # Constructed here (after self.lasers is populated) so the button
            # labels read the live ILaser.wavelength values. The radio lives
            # inside a fixed-height container that is inserted at layout
            # index 1 — BETWEEN the ImageView (index 0) and the LevelsBar
            # layout — so the radio sits below the ImageView viewport, not
            # above it. The container is always visible (it always reserves
            # its fixed height in the layout); only the inner ChannelRadio
            # is shown/hidden. This prevents the show/hide reflow that
            # displaced the ImageView on every visibility toggle: the layout
            # slot is reserved regardless of the radio's visibility.
            wl1 = (
                getattr(self.lasers[0], "wavelength", None)
                if len(self.lasers) > 0
                else None
            )
            wl2 = (
                getattr(self.lasers[1], "wavelength", None)
                if len(self.lasers) > 1
                else None
            )
            self.channel_radio = ChannelRadio(
                parent=self.ui.imagesPane,
                wl1=wl1,
                wl2=wl2,
            )
            # Fixed-height container wrapping the ChannelRadio. The container
            # reserves the layout slot; the inner radio shows/hides without
            # reflowing the ImageView or LevelsBar.
            from PySide6.QtWidgets import QVBoxLayout, QWidget

            self.channel_radio_container = QWidget(self.ui.imagesPane)
            self.channel_radio_container.setFixedHeight(_s.XXL)
            container_layout = QVBoxLayout(self.channel_radio_container)
            container_layout.setContentsMargins(_s.ZERO, _s.ZERO, _s.ZERO, _s.ZERO)
            container_layout.setSpacing(_s.ZERO)
            container_layout.addWidget(self.channel_radio)
            # Insert the container at index 1 (between the ImageView at 0
            # and the LevelsBar layout).
            images_layout = self.ui.imagesPane.layout()
            if images_layout is not None:
                typing.cast(QVBoxLayout, images_layout).insertWidget(
                    1, self.channel_radio_container
                )
            # Switch the ImageView + reset the LevelsBar when the operator
            # clicks L1/L2. Reads reconstructed_frames[wavelength] (no RGB
            # overlay; no per-channel levels state stored — the LevelsBar
            # reads the displayed frame's min/max on switch).
            self.channel_radio.idClicked.connect(self._on_channel_radio_clicked)
            # Wire the auto-laser checkbox stateChanged signals so the radio
            # visibility tracks the checkbox-pair state synchronously. The
            # slot re-caches the flags (harmless on the GUI thread) and
            # updates the radio visibility.
            self.laser_panel.ui.checkBox_laserOneAutomatic.stateChanged.connect(
                self._on_auto_laser_checkbox_changed
            )
            self.laser_panel.ui.checkBox_laserTwoAutomatic.stateChanged.connect(
                self._on_auto_laser_checkbox_changed
            )
            # Apply the initial visibility (hidden — checkboxes default
            # unchecked).
            self._update_channel_radio_visibility()
            # Now that motors are assigned, seed the stack plane spinbox ranges
            # from the motor travel limits (the soft widget-layer block).
            self.stack_panel._seed_spinbox_ranges()
            # Restore the last stack's start/end/step from config.ini so a
            # re-run does not require re-driving the stage. Skipped in demo
            # mode so tests do not inherit persisted state from the real
            # config.ini.
            self._load_stack_params()
            # Render the summary for the restored state.
            self.stack_panel._render_stack_plan_summary()

            # FrameSaverController display-port refresh timer
            self.timer_imageview = QTimer()
            self.timer_imageview.timeout.connect(
                self._fs.frame_viewer.updateUi_refresh_view
            )
            # Use functools.partial (bound callables) instead of lambdas so
            # the connection does not capture self._hw in a closure cell and
            # create a reference cycle (controller -> timer -> lambda ->
            # self._hw -> self._shell -> controller). This matches the
            # bound-method pattern documented in wire_collaborators.
            assert self._hw is not None
            self.timer_imageview.timeout.connect(
                partial(self._hw._poll_laser_status, [0])
            )
            self.timer_imageview.timeout.connect(
                partial(self._hw._refresh_laser_readback, 0)
            )
            self.timer_imageview.start(100)

            # L2 (iBeam) status poll — a separate gated QTimer
            _ibeam_defaults = {"Status Poll Interval": "1.0"}
            _ibeam_cfg = cfg_read(str(CONFIG_PATH), "iBeam", _ibeam_defaults)
            self.timer_laser2_status = QTimer()
            self.timer_laser2_status.timeout.connect(self._hw._poll_laser2_status_gated)
            self.timer_laser2_status.start(
                int(float(_ibeam_cfg["Status Poll Interval"]) * 1000)
            )

        finally:
            self._hw_progress.close()
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
            _demo_img_path = (
                Path(__file__).resolve().parents[2] / "resources" / "demo_image.png"
            )
            try:
                import numpy as _np
                from PySide6.QtGui import QImage

                _img = QImage(str(_demo_img_path))
                if not _img.isNull():
                    # Convert to grayscale numpy array for ImageView.
                    _ptr = _img.convertToFormat(QImage.Format.Format_Grayscale8)
                    _arr_u8 = (
                        _np.frombuffer(_ptr.bits(), dtype=_np.uint8)
                        .reshape(_ptr.height(), _ptr.width())
                        .copy()
                    )
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
            except (FileNotFoundError, OSError, ValueError) as exc:
                logger.warning("Demo preview image could not be loaded: %s", exc)
            except Exception:
                logger.exception("Unexpected error loading demo preview image")
        else:
            self.ui.statusbar.showMessage("Ready", 2000)

        # Set the default splitter ratio to 60/40 (60% image viewer,
        # 40% controls pane). The splitter has no initial sizes in the
        # .ui file, so without this Qt defaults to 50/50.
        _total = self.ui.splitter.width() or 1280
        self.ui.splitter.setSizes([int(_total * 0.6), int(_total * 0.4)])

        # Hardware init complete — acquisition entry points (queue, single
        # stack) may now run. Set LAST so a deferred timer callback that
        # fires mid-acquisition cannot clobber stack params (the race that
        # produced stack_starting_plane=0.0 on the rig: hardware_init's
        # _load_stack_params setValue triggered updateUi_set_number_of_planes,
        # which re-read the first-plane spinbox and overwrote the queue's
        # value).
        self._hardware_initialized = True

    def _on_startup_scan_finished(self, entries: list[PastAcquisitionEntry]) -> None:
        """Show a notification-only dialog if the startup scan found any
        resumable acquisitions. The dialog deliberately has no Resume
        Now button — the operator must open the Past panel and confirm
        the safety gate."""
        if not self._startup_notification_pending:
            return
        self._startup_notification_pending = False
        if any(getattr(e, "resumable", False) for e in entries):
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.information(
                self,
                "Incomplete acquisition",
                "Incomplete acquisition found — see Past acquisitions",
            )

    def _check_startup_incomplete_acquisitions(self) -> None:
        """Trigger an asynchronous past-acquisitions scan for the startup
        notification. The actual dialog is shown by _on_startup_scan_finished
        when the scan completes; this method returns immediately so app
        startup is not blocked."""
        self._startup_notification_pending = True
        self.past_panel.refresh()

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
            # Persist the adaptive + focus trajectory dock state to QSettings.
            # After the synchronous shutdown decision so a "No" does not
            # persist. Skipped in demo mode.
            self._adaptive_dock_controller.save_state()
            self._focus_dock_controller.save_state()
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
            # (lock-free E-stop).
            for attr in (
                "_preview_thread",
                "_live_thread",
                "_single_thread",
                "_stack_thread",
            ):
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
            # Close any live DAQ scan tasks before shutting the camera/etls,
            # then close all laser backends and the motor serial chain.
            self.siggen.delete_scanner()
            self.camera.close()
            self.etls.close()
            # Laser backends — L1 (DAQ AO) + L2 (iBeam serial) both need a
            # lifecycle close so any per-session readback/handles are released.
            self.lasers[0].close()
            self.lasers[1].close()
            # Release the NI-DAQmx laser watchdog tasks so a clean shutdown
            # does not leave them armed after the app exits.
            watchdog = getattr(self, "_laser_watchdog", None)
            if watchdog is not None:
                watchdog.disarm()
            # Shared serial handle for Zaber motor chain
            self.motors.close()
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

    # --- GUI-thread signal receivers (must stay in this class dict) ---
    # PySide6's Signal.connect() classifies a bound method as a real Qt slot
    # (queued to the receiver's thread) only while the method lives in the
    # receiver's own class body; methods inherited from a plain mixin are
    # connected as contextless callables that run on the EMITTING thread.
    # The four methods below receive signals that workers emit from their
    # QThread (sig_message / sig_progress_update / sig_*_trajectory), so they
    # must remain declared here — moving them to the delegate mixin would
    # deliver GUI-widget mutation on the worker thread.
    @Slot(str)
    def updateUi_message_printer(self, message: str) -> None:
        """Print text in console, in controller text box and in status bar"""
        logger.info(message)
        self.ui.statusbar.showMessage(message, 2000)
        self.ui.plainTextEdit_messageLog.appendPlainText(message)
        self.ui.plainTextEdit_messageLog.verticalScrollBar().setValue(
            self.ui.plainTextEdit_messageLog.verticalScrollBar().maximum()
        )

    @Slot(int)
    def _on_progress_update(self, value: int) -> None:
        """Mirror sig_progress_update into the mode badge during a stack
        run so the operator sees 'STACK RUNNING — plane {n}/{N}' without
        looking at the status bar (audit #12). The emitted value counts
        planes completed in the current run (current_plane - start_plane);
        the badge adds ``_start_plane`` back so it always shows the
        absolute plane index of the stack. Outside a stack run, the
        progress value is not shown in the badge (the badge reflects the
        mode, set by the mode-start/complete sites). During a queue run,
        the badge appends the row index so the operator sees which row is
        acquiring."""
        if getattr(self, "stack_mode_started", False):
            total = int(getattr(self, "number_of_planes", 0))
            start_plane = int(getattr(self, "_start_plane", 0))
            plane = value + start_plane
            mgr = getattr(self, "stack_panel", None)
            qm = getattr(mgr, "table_manager", None) if mgr else None
            q_row = int(getattr(qm, "_queue_row_index", 0)) + 1 if qm else 0
            q_total = int(getattr(qm, "_queue_rows_total", 0)) if qm else 0
            mode = "FOCUS" if getattr(self, "focus_mode_started", False) else "STACK"
            # A requested-but-not-yet-completed pause must keep showing
            # PAUSED — the per-plane progress emit would otherwise
            # overwrite the badge back to RUNNING until teardown lands.
            if self.pause_requested.is_set():
                run_state = "PAUSED"
            elif start_plane > 0:
                run_state = "RESUMING"
            else:
                run_state = "RUNNING"
            if qm is not None and getattr(qm, "_queue_active", False):
                self._update_mode_badge(
                    mode,
                    run_state,
                    plane=plane,
                    total=total,
                    queue_row=q_row,
                    queue_total=q_total,
                )
            else:
                self._update_mode_badge(mode, run_state, plane=plane, total=total)

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
        if self.focus_mode_started:
            self.focus_mode_started = False
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
        self.motor_panel.ui.pushButton_sampleStepUp.clicked.connect(
            self._mc.updateUi_move_sample_up
        )
        self.motor_panel.ui.pushButton_sampleStepDown.clicked.connect(
            self._mc.updateUi_move_sample_down
        )
        self.motor_panel.ui.pushButton_sampleStepForward.clicked.connect(
            self._mc.updateUi_move_sample_forward
        )
        self.motor_panel.ui.pushButton_sampleStepBackward.clicked.connect(
            self._mc.updateUi_move_sample_backward
        )
        self.motor_panel.ui.pushButton_sampleGotoOrigin.clicked.connect(
            self._mc.updateUi_move_sample_to_origin
        )
        self.motor_panel.ui.pushButton_sampleSetOrigin.clicked.connect(
            self._mc.updateUi_set_sample_origin
        )
        self.motor_panel.ui.pushButton_sampleGotoHPosition.clicked.connect(
            self._mc.updateUi_move_to_horizontal_position
        )
        self.motor_panel.ui.pushButton_sampleGotoVPosition.clicked.connect(
            self._mc.updateUi_move_to_vertical_position
        )

        # Connections for the camera motion buttons
        self.motor_panel.ui.pushButton_cameraGotoPosition.clicked.connect(
            self._mc.updateUi_move_camera_to_position
        )
        self.motor_panel.ui.pushButton_cameraSetFocus.clicked.connect(
            self._mc.updateUi_set_camera_focus
        )
        self.motor_panel.ui.pushButton_cameraGotoFocus.clicked.connect(
            self._mc.updateUi_move_camera_to_focus
        )
        self.motor_panel.ui.pushButton_cameraStepForward.clicked.connect(
            self._mc.updateUi_move_camera_forward
        )
        self.motor_panel.ui.pushButton_cameraStepBackward.clicked.connect(
            self._mc.updateUi_move_camera_backward
        )

        # Connections for the stack 'go to plane' controls (MotorController)
        self.stack_panel.ui.pushButton_acqGoToFirstPlane.clicked.connect(
            self._mc.updateUi_move_to_stack_start
        )
        self.stack_panel.ui.pushButton_acqGoToLastPlane.clicked.connect(
            self._mc.updateUi_move_to_stack_end
        )

        # ---
        # Connections for the 'Scan Settings' tab controls
        # (AcquisitionCoordinator)
        # ---
        self.scan_panel.ui.doubleSpinBox_etlLeftAmplitude.valueChanged.connect(
            self._acq.updateUi_etl_left_amplitude
        )
        self.scan_panel.ui.doubleSpinBox_etlRightAmplitude.valueChanged.connect(
            self._acq.updateUi_etl_right_amplitude
        )
        self.scan_panel.ui.doubleSpinBox_etlLeftOffset.valueChanged.connect(
            self._acq.updateUi_etl_left_offset
        )
        self.scan_panel.ui.doubleSpinBox_etlRightOffset.valueChanged.connect(
            self._acq.updateUi_etl_right_offset
        )
        self.scan_panel.ui.checkBox_etlSync.stateChanged.connect(
            self._acq.updateUi_etl_sync
        )
        self.scan_panel.ui.checkBox_etlActivate.stateChanged.connect(
            self._acq.updateUi_etl_activate
        )
        self.scan_panel.ui.doubleSpinBox_etlSteps.valueChanged.connect(
            self._acq.updateUi_etl_steps
        )

        # Connection for galvo settings changes
        self.scan_panel.ui.doubleSpinBox_galvoLeftAmplitude.valueChanged.connect(
            self._acq.updateUi_galvo_left_amplitude
        )
        self.scan_panel.ui.doubleSpinBox_galvoRightAmplitude.valueChanged.connect(
            self._acq.updateUi_galvo_right_amplitude
        )
        self.scan_panel.ui.doubleSpinBox_galvoLeftOffset.valueChanged.connect(
            self._acq.updateUi_galvo_left_offset
        )
        self.scan_panel.ui.doubleSpinBox_galvoRightOffset.valueChanged.connect(
            self._acq.updateUi_galvo_right_offset
        )
        self.scan_panel.ui.checkBox_galvoSync.stateChanged.connect(
            self._acq.updateUi_galvo_sync
        )
        self.scan_panel.ui.checkBox_galvoActivate.stateChanged.connect(
            self._acq.updateUi_galvo_activate
        )
        self.scan_panel.ui.checkBox_galvoInvert.stateChanged.connect(
            self._acq.updateUi_galvo_invert
        )

        # Connection for camera settings changes
        self.acquisition_panel.ui.comboBox_cameraShutterMode.currentTextChanged.connect(
            self._acq.updateUi_camera_shutter_mode
        )
        # The adaptive exposure-bound spinbox units track the camera
        # shutter mode (ms in Rolling / lines in Lightsheet). Hook the
        # same currentTextChanged signal so the adaptive group swaps
        # units in lockstep with the camera shutter-mode slot.
        self.acquisition_panel.ui.comboBox_cameraShutterMode.currentTextChanged.connect(
            self.stack_panel._update_adaptive_shutter_units
        )
        self.acquisition_panel.ui.doubleSpinBox_cameraExposureTime.valueChanged.connect(
            self._acq.updateUi_camera_exposure_time
        )
        self.acquisition_panel.ui.doubleSpinBox_cameraLineTime.valueChanged.connect(
            self._acq.updateUi_camera_line_time
        )
        self.acquisition_panel.ui.doubleSpinBox_cameraExposedLines.valueChanged.connect(
            self._acq.updateUi_camera_exposed_lines
        )
        self.acquisition_panel.ui.doubleSpinBox_cameraDelayLines.valueChanged.connect(
            self._acq.updateUi_camera_delay_lines
        )

        # ---
        # Connections for the 'Calibration' tab controls (MotorController)
        # ---
        self.calibration_panel.ui.pushButton_calCameraComputeFocus.clicked.connect(
            self._mc.calculate_camera_focus
        )
        self.calibration_panel.ui.pushButton_calCameraShowInterpolation.clicked.connect(
            self._mc.show_camera_interpolation
        )
        self.calibration_panel.ui.pushButton_calEtlShowInterpolation.clicked.connect(
            self._mc.show_etl_interpolation
        )
        self.calibration_panel.ui.pushButton_calHorizontalStartRangeSelection.clicked.connect(
            self._mc.updateUi_reset_boundaries
        )
        self.calibration_panel.ui.pushButton_calHorizontalSetForwardLimit.clicked.connect(
            self._mc.updateUi_set_horizontal_forward_boundary
        )
        self.calibration_panel.ui.pushButton_calHorizontalSetBackwardLimit.clicked.connect(
            self._mc.updateUi_set_horizontal_backward_boundary
        )

        # Reactive model projections: laser-panel spinboxes reflect
        # model-originated power changes with blockSignals to avoid echo loops.
        self.state.sig_laser_power_changed.connect(
            self.laser_panel.updateUi_laser_power_from_state
        )
        # The camera line-time spinbox is a reactive projection of the
        # model's seconds value (rendered in microseconds); worker-applied
        # readback reaches it through this signal.
        self.state.sig_lightsheet_line_time_changed.connect(
            self.acquisition_panel.updateUi_lightsheet_line_time_from_state
        )
        # The save description + exclusive save-mode radios are reactive
        # projections of the model's SaveOptions.
        self.state.sig_save_options_changed.connect(
            self.save_panel.updateUi_save_options_from_state
        )

    # --- adaptive trajectory dock lifecycle ---
    @Slot(int, float, float, float, float, str, bool, bool)
    def _on_adaptive_trajectory(
        self,
        plane_idx: int,
        intensity: float,
        exposure_s: float,
        power1_mw: float,
        power2_mw: float,
        control_variable_active: str,
        reacquired: bool,
        power_fallback: bool,
    ) -> None:
        """GUI-thread slot for the per-plane adaptive trajectory signal.

        The worker emits ``sig_adaptive_trajectory`` (a queued
        ``Signal``); this shell slot delegates to the presentation
        controller. The worker NEVER calls pyqtgraph directly."""
        self._adaptive_last_plane = plane_idx
        self._adaptive_dock_controller.append_sample(
            plane_idx=plane_idx,
            intensity=intensity,
            exposure_s=exposure_s,
            power1_mw=power1_mw,
            power2_mw=power2_mw,
            control_variable_active=control_variable_active,
            reacquired=reacquired,
            power_fallback=power_fallback,
        )

    # --- focus trajectory dock lifecycle ---
    @Slot(int, float, float, float, float)
    def _on_focus_trajectory(
        self,
        block_idx: int,
        stage_pos_mm: float,
        feedforward_camera_pos_mm: float,
        residual_mm: float,
        applied_camera_pos_mm: float,
    ) -> None:
        """GUI-thread slot for the per-block focus trajectory signal.

        The worker emits ``sig_focus_trajectory`` (a queued ``Signal``);
        this shell slot delegates to the presentation controller. The
        worker NEVER calls pyqtgraph directly.

        The X-axis is hardcoded to the block index ("Block") in this
        phase; the Stage position (mm) X-axis option has been removed.
        """
        self._focus_last_block = block_idx
        self._focus_dock_controller.append_sample(
            block_idx=block_idx,
            stage_pos_mm=stage_pos_mm,
            feedforward_camera_pos_mm=feedforward_camera_pos_mm,
            residual_mm=residual_mm,
            applied_camera_pos_mm=applied_camera_pos_mm,
        )

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
        delay the kill path.
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
        # Freeze the adaptive + focus trajectory plots AFTER the synchronous
        # laser-off kill path completes. The docks stay visible so the
        # operator can review the partial trajectory. No-op if the respective
        # trajectory widget does not exist. This post-kill cosmetic step is
        # guarded so a failure in it (e.g. the badge's model read) can never
        # propagate out of the E-stop handler — the kill path above is
        # already complete and the remaining UI latching must still run.
        try:
            if hasattr(self, "adaptiveTrajectoryWidget"):
                self._adaptive_dock_controller.freeze()
            if hasattr(self, "focusTrajectoryWidget"):
                self._focus_dock_controller.freeze()
        except Exception:
            logger.exception("E-stop post-kill trajectory freeze failed")
        # Refresh-after-action: both status labels reflect the post-E-stop
        # state. Deferred via QTimer.singleShot(0, ...) so the GUI thread
        # releases within ~1 ms of the press — the synchronous kill loop
        # above (estop_event.set() + laser.off()) is the only blocking
        # work, and it is lock-free. The L2 (iBeam) readback is a ~3s
        # serial round-trip on the rig; calling it synchronously froze
        # The kill loop itself (laser.off() above) stays in the shell,
        # direct on self.lasers, lock-free — only the post-kill *refresh*
        # is deferred (the kill path is never offloaded).
        QTimer.singleShot(0, lambda: self._hw._poll_laser_status([0, 1]))
        QTimer.singleShot(0, lambda: self._hw._refresh_laser_readback(0))
        QTimer.singleShot(0, self._hw._refresh_laser2_readback_async)

        # 4. Latch the UI into ACTUATED: red indicator, yellow 4px border
        #    on the E-stop button. The Arm/Reset button label reflects the
        #    NEXT action available — "Clear E-stop" (the first press of the
        #    two-press re-arm sequence, audit #6).
        self.label_estopStatus.setText(f"{_sym.ESTOP_ACTUATED} E-STOP ACTUATED")
        self.label_estopStatus.setStyleSheet(f"color: {_c.DANGER}; {_t.BOLD}")
        self.pushButton_estop.setStyleSheet(
            f"QPushButton {{ background-color: {_c.DANGER}; color: {_c.ON_DANGER}; "
            f"{_t.HEADING} border: 4px solid {_c.WARNING}; }}"
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

            ARMED --(E-stop)--> ACTUATED
                --(1st press)--> DISARMED --(2nd press)--> ARMED

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
        DISARMED first (no single-press re-arm of a Class IIIB laser).

        Never re-energizes a laser itself.
        """
        if self._estop_disarmed:
            # Second press: re-arm. System returns to ARMED; lasers stay
            # off until the operator explicitly toggles one or starts a
            # run.
            self._estop_disarmed = False
            self.label_estopStatus.setText(f"{_sym.ESTOP_ARMED} ARMED")
            self.label_estopStatus.setStyleSheet(f"color: {_c.SUCCESS}; {_t.BOLD}")
            self.pushButton_estop.setStyleSheet(
                f"QPushButton {{ background-color: {_c.DANGER}; color: {_c.ON_DANGER}; "
                f"{_t.HEADING} border: 2px solid {_c.BREEZE_BG}; }}"
            )
            self.pushButton_armReset.setText("Arm/Reset")
            self.sig_message.emit(
                "System armed. Lasers stay off until you toggle one or start a run."
            )
        else:
            # First press after an E-stop: clear the cooperative-abort
            # Event and transition to DISARMED. Lasers remain off. A
            # single press from ACTUATED does NOT re-arm — the second
            # press (above) is required.
            self.estop_event.clear()
            self._estop_disarmed = True
            self.label_estopStatus.setText(f"{_sym.ESTOP_DISARMED} DISARMED")
            self.label_estopStatus.setStyleSheet(f"color: {_c.DISABLED}; {_t.BOLD}")
            # The E-stop button background stays safety-red in ALL states
            # (ARMED, DISARMED, ACTUATED) — only the border changes. The
            # DISARMED state is communicated by the gray status label above,
            # NOT by graying out the button.
            self.pushButton_estop.setStyleSheet(
                f"QPushButton {{ background-color: {_c.DANGER}; color: {_c.ON_DANGER}; "
                f"{_t.HEADING} border: 2px solid {_c.BREEZE_BG}; }}"
            )
            self.pushButton_armReset.setText("Arm Lasers")
            self.sig_message.emit("E-stop cleared. Press Arm Lasers to re-arm.")

    def updateUi_initial_hardware_state(self) -> None:
        # SigGen
        self.scan_panel.ui.checkBox_galvoActivate.setChecked(
            self.siggen.galvo_activated
        )
        self.scan_panel.ui.checkBox_galvoInvert.setChecked(self.siggen.galvo_inverted)
        self.scan_panel.ui.doubleSpinBox_galvoLeftAmplitude.setValue(
            self.siggen.galvo_left_amplitude
        )
        self.scan_panel.ui.doubleSpinBox_galvoRightAmplitude.setValue(
            self.siggen.galvo_right_amplitude
        )
        self.scan_panel.ui.doubleSpinBox_galvoLeftOffset.setValue(
            self.siggen.galvo_left_offset
        )
        self.scan_panel.ui.doubleSpinBox_galvoRightOffset.setValue(
            self.siggen.galvo_right_offset
        )

        self.scan_panel.ui.checkBox_etlActivate.setChecked(self.siggen.etl_activated)
        self.scan_panel.ui.doubleSpinBox_etlLeftAmplitude.setValue(
            self.siggen.etl_left_amplitude
        )
        self.scan_panel.ui.doubleSpinBox_etlRightAmplitude.setValue(
            self.siggen.etl_right_amplitude
        )
        self.scan_panel.ui.doubleSpinBox_etlLeftOffset.setValue(
            self.siggen.etl_left_offset
        )
        self.scan_panel.ui.doubleSpinBox_etlRightOffset.setValue(
            self.siggen.etl_right_offset
        )
        self.scan_panel.ui.doubleSpinBox_etlSteps.setValue(self.siggen.etl_steps)

        # Camera
        self.acquisition_panel.ui.doubleSpinBox_cameraExposureTime.setValue(
            self.camera.exposure_time * 1e3
        )  # camera(s) to ui(ms)
        # Line-time intent is seeded from the model so model, HAL intent,
        # and widget start from one source of truth (model seconds ->
        # widget microseconds).
        self.camera.lightsheet_line_time = self.state.lightsheet_line_time_s
        self.acquisition_panel.ui.doubleSpinBox_cameraLineTime.setValue(
            self.state.lightsheet_line_time_s * 1e6
        )  # model(s) to ui(us)
        self.acquisition_panel.ui.doubleSpinBox_cameraExposedLines.setValue(
            self.camera.lightsheet_exposed_lines
        )
        self.acquisition_panel.ui.doubleSpinBox_cameraDelayLines.setValue(
            self.camera.lightsheet_delay_lines
        )
        # Set camera shutter mode comboBox options (default: Rolling)
        self.acquisition_panel.ui.comboBox_cameraShutterMode.insertItems(
            0, ["Rolling", "Lightsheet"]
        )
        if self.camera.shutter_mode == "Lightsheet":
            self.acquisition_panel.ui.comboBox_cameraShutterMode.setCurrentIndex(1)
        else:
            self.acquisition_panel.ui.comboBox_cameraShutterMode.setCurrentIndex(0)
        self._acq.updateUi_camera_shutter_mode()

        # Lasers — both spinboxes are 0-100 % staged setpoints. Seed from
        # the persistent model-side percentage, not the live HAL state,
        # so the staged value survives laser on/off and E-stop disarm/re-arm
        # cycles within the session.
        self.laser_panel.ui.doubleSpinBox_laserOneAmplitude.setValue(
            self.state.laser_power_pct[0]
        )
        self.laser_panel.ui.doubleSpinBox_laserTwoAmplitude.setValue(
            self.state.laser_power_pct[1]
        )

        # Wavelength labels — read from the live list[ILaser] instances.
        self.laser_panel.ui.label_72.setText(
            f'<html><head/><body><p><span style="{_t.POWER}">'
            f"{self.lasers[0].wavelength} nm</span></p></body></html>"
        )
        self.laser_panel.ui.label_73.setText(
            f'<html><head/><body><p><span style="{_t.POWER}">'
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

    # ------------------------------------------------------------------ #
    # Compatibility properties delegating to the reactive state model.
    # These keep the existing ``laser*_power_pct`` / ``_auto_laser*``
    # surface alive for legacy callers (hardware manager, workers) while
    # the model becomes the single source of truth.
    # ------------------------------------------------------------------ #

    @property
    def laser1_power_pct(self) -> float:
        return self.state.laser_power_pct[0]

    @laser1_power_pct.setter
    def laser1_power_pct(self, value: float) -> None:
        self.state.set_laser_power_pct(0, float(value))

    @property
    def laser2_power_pct(self) -> float:
        return self.state.laser_power_pct[1]

    @laser2_power_pct.setter
    def laser2_power_pct(self, value: float) -> None:
        self.state.set_laser_power_pct(1, float(value))

    @property
    def _auto_laser1(self) -> bool:
        return self.state.auto_laser1

    @_auto_laser1.setter
    def _auto_laser1(self, value: bool) -> None:
        self.state.set_auto_lasers(bool(value), self.state.auto_laser2)

    @property
    def _auto_laser2(self) -> bool:
        return self.state.auto_laser2

    @_auto_laser2.setter
    def _auto_laser2(self, value: bool) -> None:
        self.state.set_auto_lasers(self.state.auto_laser1, bool(value))

    @property
    def save_description(self) -> str:
        return self.state.save_options.description

    @save_description.setter
    def save_description(self, value: str) -> None:
        self.state.set_save_description(str(value))
