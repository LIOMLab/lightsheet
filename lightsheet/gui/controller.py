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

from PySide6.QtCore import Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
)

from lightsheet.config import cfg_read
from lightsheet.gui.acquisition_panel import AcquisitionPanelWidget
from lightsheet.gui.calibration_panel import CalibrationPanelWidget
from lightsheet.gui.laser_panel import LaserPanelWidget
from lightsheet.gui.motor_panel import MotorPanelWidget
from lightsheet.gui.properties_dialog import Properties_Dialog
from lightsheet.gui.save_panel import SavePanelWidget
from lightsheet.gui.scan_panel import ScanPanelWidget
from lightsheet.gui.stack_panel import StackPanelWidget
from lightsheet.gui.ui_shell import Ui_Shell
from lightsheet.hal.bundle import DeviceBundle

logger = logging.getLogger(__name__)

if typing.TYPE_CHECKING:
    from lightsheet.gui.acquisition_coordinator import AcquisitionCoordinator
    from lightsheet.gui.frame_saver_controller import FrameSaverController
    from lightsheet.gui.hardware_manager import HardwareManager
    from lightsheet.gui.motor_controller import MotorController


class Controller_MainWindow(QMainWindow):
    """Thin shell for the MesoSPIM Controller — composes 7 per-panel widget
    modules and retains the safety-critical E-stop kill path."""

    # Dictionnary of configurable settings and their default values
    _cfg_settings: dict[str, str] = {}  # noqa: RUF012
    _cfg_settings["Units"] = "mm"
    _cfg_settings["Image File Format"] = "HDF5"

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
        # tabControls with a placeholder tab). The shell .ui provides the
        # safety toolbar + placeholder containers; the 7 panel widgets are
        # composed into tabControls programmatically below.
        self.ui = Ui_Shell()
        self.ui.setupUi(self)

        # Expose the E-stop widgets as direct attributes for backward
        # compatibility with existing slot code and tests.
        self.toolBar_estop = self.ui.toolBar_estop
        self.label_estopStatus = self.ui.label_estopStatus
        self.pushButton_estop = self.ui.pushButton_estop
        self.pushButton_armReset = self.ui.pushButton_armReset
        self.shortcut_estop = self.ui.shortcut_estop

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

        # F12 hotkey — fires regardless of which widget has focus. The
        # QShortcut is declared in ui_shell.ui (with ApplicationShortcut
        # context); the F12 key sequence is set here because pyside6-uic
        # maps the .ui "shortcut" property to setShortcut() which QShortcut
        # does not have (it uses setKey()).
        self.shortcut_estop.setKey(QKeySequence("F12"))
        self.shortcut_estop.activated.connect(self.updateUi_estop_pressed)

        # --- Compose the 7 per-panel widgets into tabControls ---
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

        # The units selector (comboBox_units + "Units:" label) was in the
        # monolith's tabMotion but was not included in the motor panel .ui
        # during the 07-07 split. Create it programmatically and insert it
        # at the top of the motor panel's layout (before groupBox_SampleMovement).
        from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel as _QLabel

        self.units_label = _QLabel("Units:")
        self.motor_panel.ui.comboBox_units = QComboBox(self.motor_panel)
        self.motor_panel.ui.comboBox_units.setObjectName("comboBox_units")
        self.motor_panel.ui.comboBox_units.setMinimumSize(75, 0)
        _units_layout = QHBoxLayout()
        _units_layout.addWidget(self.units_label)
        _units_layout.addWidget(self.motor_panel.ui.comboBox_units)
        # Insert at position 0 (before groupBox_SampleMovement)
        self.motor_panel.ui.verticalLayout_panel.insertLayout(0, _units_layout)

        # Remove the placeholder tab and add each panel as its own tab.
        self.ui.tabControls.removeTab(0)
        self.ui.tabControls.addTab(self.motor_panel, "Motion")
        self.ui.tabControls.addTab(self.laser_panel, "Lasers")
        self.ui.tabControls.addTab(self.acquisition_panel, "Acquisition")
        self.ui.tabControls.addTab(self.stack_panel, "Stack")
        self.ui.tabControls.addTab(self.scan_panel, "Scan Settings")
        self.ui.tabControls.addTab(self.save_panel, "File Manager")
        self.ui.tabControls.addTab(self.calibration_panel, "Calibration")

        # Merge each panel's widget attributes onto self.ui so the flat
        # self.ui.<objectName> namespace works across all panels + shell.
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
                if not attr_name.startswith("_"):
                    setattr(self.ui, attr_name, getattr(panel.ui, attr_name))

        # Per-laser status indicators (LSR-06). Added programmatically per
        # AGENTS.md §8 (generated UI files are never hand-edited) — parented
        # into the laser panel's groupBox_15 column layouts
        # (verticalLayout_43 = L1 column, verticalLayout_44 = L2 column).
        # Inserted BEFORE the expanding spacer so they align.
        self.label_laserOneStatus = QLabel("● OFF")
        self.label_laserOneStatus.setMinimumWidth(140)
        self.label_laserOneStatus.setStyleSheet("color: #8E8E93; font-weight: bold;")
        self.ui.verticalLayout_43.insertWidget(4, self.label_laserOneStatus)

        self.label_laserOneReadback = QLabel("0.0 mW (est.)")
        self.label_laserOneReadback.setMinimumWidth(80)
        self.label_laserOneReadback.setToolTip(
            "Linear-through-origin estimate (mW = V * mW_per_volt). "
            "Unverified — the linear model predicts 300 mW at 5V, but "
            "the rig-measured output is ~107.5 mW at 5V (DPSS threshold "
            "knee + free-space measurement geometry). Run the rig "
            "calibration sweep to load a measured V->mW curve."
        )
        self.ui.verticalLayout_43.insertWidget(5, self.label_laserOneReadback)

        self.label_laserTwoStatus = QLabel("● OFF")
        self.label_laserTwoStatus.setMinimumWidth(140)
        self.label_laserTwoStatus.setStyleSheet("color: #8E8E93; font-weight: bold;")
        self.ui.verticalLayout_44.insertWidget(4, self.label_laserTwoStatus)

        self.label_laserTwoReadback = QLabel("N/A")
        self.label_laserTwoReadback.setMinimumWidth(80)
        self.label_laserTwoReadback.setToolTip(
            "iBeam power readback — click Refresh Power to re-query"
        )
        self.ui.verticalLayout_44.insertWidget(5, self.label_laserTwoReadback)

        self.pushButton_laserTwoRefresh = QPushButton("Refresh Power")
        self.pushButton_laserTwoRefresh.setToolTip(
            "Re-query iBeam status and power readback now "
            "(skipped while a power write is in progress)"
        )
        self.pushButton_laserTwoRefresh.clicked.connect(
            self.laser_panel.updateUi_laser2_refresh_clicked
        )
        self.ui.verticalLayout_44.insertWidget(6, self.pushButton_laserTwoRefresh)

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

        # Set configurable settings to default values
        self.cfg_settings = copy.deepcopy(self._cfg_settings)
        self.cfg_settings = cfg_read("config.ini", "Controller", self.cfg_settings)

        if str(self.cfg_settings["Units"]) == "mm":
            self.units = "mm"
        if (
            str(self.cfg_settings["Units"]) == "\u03bcm"
            or str(self.cfg_settings["Units"]) == "um"
        ):
            self.units = "\u03bcm"
        else:
            self.units = "mm"

        if str.lower(self.cfg_settings["Image File Format"]) == "hdf5":
            self.save_format = "hdf5"
        if str.lower(self.cfg_settings["Image File Format"]) == "tiff":
            self.save_format = "tiff"
        else:
            self.save_format = "hdf5"

        self.save_directory = os.path.normpath(
            os.path.expanduser("~") + "\\Documents\\LightSheetData"
        )
        self.save_filename = ""
        self.save_description = ""
        self.open_directory = ""
        self.dataset_name = ""

        # Set units comboBox options (default: millimeters)
        self.ui.comboBox_units.insertItems(0, ["mm", "\u03bcm"])
        if self.units == "\u03bcm":
            self.ui.comboBox_units.setCurrentIndex(1)
        else:
            self.ui.comboBox_units.setCurrentIndex(0)

        if self.save_directory != "":
            self.ui.lineEdit_saveDirectory.setText(self.save_directory)
            self.ui.lineEdit_saveFilename.setText(self.save_filename)
            self.ui.lineEdit_saveFilename.setEnabled(True)
            self.ui.lineEdit_saveDescription.setText(self.save_description)
            self.ui.lineEdit_saveDescription.setEnabled(True)
        else:
            self.ui.lineEdit_saveDirectory.setText("")
            self.ui.lineEdit_saveFilename.setText("Filename - Select Save Directory First")
            self.ui.lineEdit_saveFilename.setEnabled(False)
            self.ui.lineEdit_saveDescription.setText("Description - Select Save Directory First")
            self.ui.lineEdit_saveDescription.setEnabled(False)

        # Flags
        self.single_mode_started = False
        self.preview_mode_started = False
        self.live_mode_started = False
        self.stack_mode_started = False

        # Operator-facing staged laser power setpoints in percent (0-100).
        self.laser1_power_pct = 0.0
        self.laser2_power_pct = 0.0

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
            self.ui.pushButton_acqStartPreviewMode,
            self.ui.pushButton_acqStartLiveMode,
            self.ui.pushButton_acqStartStackMode,
            self.ui.pushButton_acqGetSingleImage,
        ]

        # Initial state of modes buttons
        self.ui.pushButton_acqStartPreviewMode.setEnabled(True)
        self.ui.pushButton_acqStartLiveMode.setEnabled(True)
        self.ui.pushButton_acqStartStackMode.setEnabled(True)
        self.ui.pushButton_acqGetSingleImage.setEnabled(True)
        self.ui.pushButton_saveCurrentImage.setEnabled(False)
        self.ui.pushButton_calCameraComputeFocus.setEnabled(False)
        self.ui.pushButton_calCameraShowInterpolation.setEnabled(False)
        self.ui.pushButton_calEtlShowInterpolation.setEnabled(False)

        # Initial state of First and Last plane selection (for Stack Mode)
        self.ui.checkBox_acqFirstPlaneSet.setEnabled(False)
        self.ui.checkBox_acqLastPlaneSet.setEnabled(False)
        self.ui.pushButton_acqSetFirstPlane.setEnabled(True)
        self.ui.pushButton_acqSetLastPlane.setEnabled(True)

        # Initial state of some file selection buttons
        self.ui.pushButton_selectDataset.setEnabled(False)

        # ---
        # Signal connections for progress bar and command log
        # ---
        self.sig_progress_update.connect(self.ui.statusBar_progress.setValue)
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
        self.ui.action_showSystemProperties.triggered.connect(self.open_properties_dialog)
        self.ui.action_openDocumentation.triggered.connect(self.open_help)

        # Connection for unit change
        self.ui.comboBox_units.currentTextChanged.connect(self.motor_panel.updateUi_units)

        # Connection for laser settings changes — target the laser panel slots.
        self.ui.doubleSpinBox_laserOneAmplitude.valueChanged.connect(
            self.laser_panel.updateUi_laser1_amplitude
        )
        self.ui.doubleSpinBox_laserTwoAmplitude.valueChanged.connect(
            self.laser_panel.updateUi_laser2_amplitude
        )

        # Connections for the 'File Manager' tab controls — target save panel.
        self.ui.pushButton_selectFile.clicked.connect(self.save_panel.updateUi_select_file)
        self.ui.pushButton_selectDataset.clicked.connect(self.save_panel.updateUi_select_dataset)
        self.ui.listWidget_fileDatasets.doubleClicked.connect(self.save_panel.updateUi_select_dataset)

        # Connections for the 'Manual Acquisition' controls — target acquisition panel.
        self.ui.pushButton_acqGetSingleImage.clicked.connect(
            self.acquisition_panel.updateUi_single_mode_button
        )
        self.ui.pushButton_acqStartLiveMode.clicked.connect(
            self.acquisition_panel.updateUi_live_mode_button
        )
        self.ui.pushButton_acqStartPreviewMode.clicked.connect(
            self.acquisition_panel.updateUi_preview_mode_button
        )

        # Connections for the 'Automatic Acquisition' controls — target stack panel.
        self.ui.pushButton_acqStartStackMode.clicked.connect(
            self.acquisition_panel.updateUi_stack_mode_button
        )
        self.ui.doubleSpinBox_acqPlaneStepSize.valueChanged.connect(
            self.stack_panel.updateUi_set_number_of_planes
        )
        self.ui.pushButton_acqSetFirstPlane.clicked.connect(
            self.stack_panel.updateUi_set_stack_mode_starting_point
        )
        self.ui.pushButton_acqSetLastPlane.clicked.connect(
            self.stack_panel.updateUi_set_stack_mode_ending_point
        )

        # Connections for the 'Lasers' controls — target laser panel.
        self.ui.pushButton_laserOneToggle.clicked.connect(self.laser_panel.laser1_toggle_button)
        self.ui.pushButton_laserTwoToggle.clicked.connect(self.laser_panel.laser2_toggle_button)

        # Connections for the 'Save Settings' controls — target save panel.
        self.ui.pushButton_saveSelectDirectory.clicked.connect(
            self.save_panel.updateUi_select_directory
        )
        self.ui.pushButton_saveCurrentImage.clicked.connect(
            self.save_panel.updateUi_save_single_image
        )

        self.save_option_button_group = QButtonGroup(self)
        self.save_option_button_group.addButton(self.ui.checkBox_saveStitch)
        self.save_option_button_group.addButton(self.ui.checkBox_saveStitchBlend)
        self.save_option_button_group.addButton(self.ui.checkBox_saveAllCrop)
        self.save_option_button_group.addButton(self.ui.checkBox_saveAllFull)
        self.save_option_button_group.setExclusive(True)

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

        # FrameSaverController display-port refresh timer
        self.timer_imageview = QTimer()
        self.timer_imageview.timeout.connect(self._fs.frame_viewer.updateUi_refresh_view)
        self.timer_imageview.timeout.connect(lambda: self._hw._poll_laser_status([0]))
        self.timer_imageview.timeout.connect(lambda: self._hw._refresh_laser_readback(0))
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
        else:
            self.ui.statusbar.showMessage("Ready", 2000)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Making sure that everything is closed when the user exits the software."""  # noqa: E501
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
            self.close_modes()
            # Stop the frame_saver QThread BEFORE the acquisition threads so
            # h5py.File.close() completes before the camera/etls close.
            self._fs.frame_saver.stop_saving()
            # Shut down all four acquisition worker QThreads via a single
            # uniform quit() + wait(5000) loop. The cooperative poll model
            # means each worker exits on its own at the next loop iteration
            # after close_modes() cleared its mode-started flag. The 4 laser
            # daemon threads stay threading.Thread and are NOT in this loop
            # (lock-free E-stop, AGENTS.md §2).
            for attr in ("_preview_thread", "_live_thread", "_single_thread", "_stack_thread"):
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
            self.timer_imageview.stop()
            self.timer_laser2_status.stop()
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

    def open_properties_dialog(self) -> None:
        """Open the dialog window for showing properties"""
        self.properties_dialog = Properties_Dialog(self)
        self.properties_dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.properties_dialog.open()
        self.properties_dialog.get_properties()

    def open_help(self) -> None:
        """Open help documentation (PDF)"""
        guide_pdf = os.path.dirname(os.path.abspath(__file__)) + r"\..\Guide.pdf"
        webbrowser.open_new(guide_pdf)

    def updateUi_light_theme(self) -> None:
        self.sig_stylesheet.emit("light")

    def updateUi_dark_theme(self) -> None:
        self.sig_stylesheet.emit("dark")

    def updateUi_show_hide_images_pane(self) -> None:
        if self.ui.imagesPane.isVisible():
            self.ui.imagesPane.hide()
        else:
            self.ui.imagesPane.show()

    def updateUi_show_hide_controls_pane(self) -> None:
        if self.ui.controlsPane.isVisible():
            self.ui.controlsPane.hide()
        else:
            self.ui.controlsPane.show()

    def updateUi_show_hide_message_log(self) -> None:
        if self.ui.plainTextEdit_messageLog.isVisible():
            self.ui.plainTextEdit_messageLog.hide()
        else:
            self.ui.plainTextEdit_messageLog.show()

    def _cache_auto_laser_flags(self) -> None:
        """Sample the auto-laser checkboxes. GUI thread only.

        Acquisition workers run start_lasers()/stop_lasers() off the GUI
        thread and must read these cached bools rather than the widgets,
        which belong to the GUI thread (AGENTS.md §11). Called at every
        mode-*start* entry point that leads to a worker calling
        start_lasers()/stop_lasers().
        """
        self._auto_laser1 = self.ui.checkBox_laserOneAutomatic.isChecked()
        self._auto_laser2 = self.ui.checkBox_laserTwoAutomatic.isChecked()

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
        self.ui.pushButton_sampleStepUp.clicked.connect(self._mc.updateUi_move_sample_up)
        self.ui.pushButton_sampleStepDown.clicked.connect(self._mc.updateUi_move_sample_down)
        self.ui.pushButton_sampleStepForward.clicked.connect(self._mc.updateUi_move_sample_forward)
        self.ui.pushButton_sampleStepBackward.clicked.connect(self._mc.updateUi_move_sample_backward)
        self.ui.pushButton_sampleGotoOrigin.clicked.connect(self._mc.updateUi_move_sample_to_origin)
        self.ui.pushButton_sampleSetOrigin.clicked.connect(self._mc.updateUi_set_sample_origin)
        self.ui.pushButton_sampleGotoHPosition.clicked.connect(self._mc.updateUi_move_to_horizontal_position)
        self.ui.pushButton_sampleGotoVPosition.clicked.connect(self._mc.updateUi_move_to_vertical_position)

        # Connections for the camera motion buttons
        self.ui.pushButton_cameraGotoPosition.clicked.connect(self._mc.updateUi_move_camera_to_position)
        self.ui.pushButton_cameraSetFocus.clicked.connect(self._mc.updateUi_set_camera_focus)
        self.ui.pushButton_cameraStepForward.clicked.connect(self._mc.updateUi_move_camera_forward)
        self.ui.pushButton_cameraStepBackward.clicked.connect(self._mc.updateUi_move_camera_backward)

        # ---
        # Connections for the 'Scan Settings' tab controls
        # (AcquisitionCoordinator)
        # ---
        self.ui.doubleSpinBox_etlLeftAmplitude.valueChanged.connect(self._acq.updateUi_etl_left_amplitude)
        self.ui.doubleSpinBox_etlRightAmplitude.valueChanged.connect(self._acq.updateUi_etl_right_amplitude)
        self.ui.doubleSpinBox_etlLeftOffset.valueChanged.connect(self._acq.updateUi_etl_left_offset)
        self.ui.doubleSpinBox_etlRightOffset.valueChanged.connect(self._acq.updateUi_etl_right_offset)
        self.ui.checkBox_etlSync.stateChanged.connect(self._acq.updateUi_etl_sync)
        self.ui.checkBox_etlActivate.stateChanged.connect(self._acq.updateUi_etl_activate)
        self.ui.doubleSpinBox_etlSteps.valueChanged.connect(self._acq.updateUi_etl_steps)

        # Connection for galvo settings changes
        self.ui.doubleSpinBox_galvoLeftAmplitude.valueChanged.connect(self._acq.updateUi_galvo_left_amplitude)
        self.ui.doubleSpinBox_galvoRightAmplitude.valueChanged.connect(self._acq.updateUi_galvo_right_amplitude)
        self.ui.doubleSpinBox_galvoLeftOffset.valueChanged.connect(self._acq.updateUi_galvo_left_offset)
        self.ui.doubleSpinBox_galvoRightOffset.valueChanged.connect(self._acq.updateUi_galvo_right_offset)
        self.ui.checkBox_galvoSync.stateChanged.connect(self._acq.updateUi_galvo_sync)
        self.ui.checkBox_galvoActivate.stateChanged.connect(self._acq.updateUi_galvo_activate)
        self.ui.checkBox_galvoInvert.stateChanged.connect(self._acq.updateUi_galvo_invert)

        # Connection for camera settings changes
        self.ui.comboBox_cameraShutterMode.currentTextChanged.connect(self._acq.updateUi_camera_shutter_mode)
        self.ui.doubleSpinBox_cameraExposureTime.valueChanged.connect(self._acq.updateUi_camera_exposure_time)
        self.ui.doubleSpinBox_cameraLineTime.valueChanged.connect(self._acq.updateUi_camera_line_time)
        self.ui.doubleSpinBox_cameraExposedLines.valueChanged.connect(self._acq.updateUi_camera_exposed_lines)
        self.ui.doubleSpinBox_cameraDelayLines.valueChanged.connect(self._acq.updateUi_camera_delay_lines)

        # ---
        # Connections for the 'Calibration' tab controls (MotorController)
        # ---
        self.ui.pushButton_calCameraComputeFocus.clicked.connect(self._mc.calculate_camera_focus)
        self.ui.pushButton_calCameraShowInterpolation.clicked.connect(self._mc.show_camera_interpolation)
        self.ui.pushButton_calEtlShowInterpolation.clicked.connect(self._mc.show_etl_interpolation)
        self.ui.pushButton_calHorizontalStartRangeSelection.clicked.connect(self._mc.updateUi_reset_boundaries)
        self.ui.pushButton_calHorizontalSetForwardLimit.clicked.connect(self._mc.updateUi_set_horizontal_forward_boundary)
        self.ui.pushButton_calHorizontalSetBackwardLimit.clicked.connect(self._mc.updateUi_set_horizontal_backward_boundary)

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
        # state immediately (the periodic timers would otherwise lag).
        # Routed through HardwareManager — the kill loop itself (laser.off()
        # above) stays in the shell, direct on self.lasers, lock-free.
        self._hw._poll_laser_status([0, 1])
        self._hw._refresh_laser_readback(0)
        self._hw._refresh_laser2_readback_async()

        # 4. Latch the UI into ACTUATED: red indicator, yellow 4px border
        #    on the E-stop button.
        self.label_estopStatus.setText("● E-STOP ACTUATED")
        self.label_estopStatus.setStyleSheet("color: #FF3B30; font-weight: bold;")
        self.pushButton_estop.setStyleSheet(
            "QPushButton { background-color: #FF3B30; color: white; "
            "font-size: 18px; font-weight: bold; border: 4px solid #FFC107; }"
        )

        # 5. Warn the operator. Re-energizing requires Arm/Reset then Arm.
        self.sig_message.emit(
            "E-STOP actuated — all lasers driven to 0 V and the acquisition "
            "was aborted. Press Arm/Reset, then Arm, to re-enable lasers."
        )

    @Slot()
    def updateUi_arm_reset_pressed(self) -> None:
        """Arm/Reset button handler — the two-press re-arm sequence.

        First press (while ACTUATED): clears the E-stop Event and transitions
        to DISARMED (gray indicator, button label -> "Arm"). Lasers are NOT
        re-energized — they stay off until the operator explicitly toggles one
        or starts an acquisition.

        Second press (while DISARMED, button labeled "Arm"): transitions back
        to ARMED (green indicator, button label -> "Arm/Reset"). The system
        is now ready; energizing still requires a separate deliberate action.

        Never re-energizes a laser itself (D-01).
        """
        if self._estop_disarmed:
            # Second press: re-arm. System returns to ARMED; lasers stay off
            # until the operator explicitly toggles one or starts a run.
            self._estop_disarmed = False
            self.label_estopStatus.setText("● ARMED")
            self.label_estopStatus.setStyleSheet("color: #34C759; font-weight: bold;")
            self.pushButton_estop.setStyleSheet(
                "QPushButton { background-color: #FF3B30; color: white; "
                "font-size: 18px; font-weight: bold; border: 2px solid black; }"
            )
            self.pushButton_armReset.setText("Arm/Reset")
        else:
            # First press after an E-stop: clear the cooperative-abort Event
            # and transition to DISARMED. Lasers remain off.
            self.estop_event.clear()
            self._estop_disarmed = True
            self.label_estopStatus.setText("● DISARMED")
            self.label_estopStatus.setStyleSheet("color: #8E8E93; font-weight: bold;")
            self.pushButton_estop.setStyleSheet(
                "QPushButton { background-color: #8E8E93; color: white; "
                "font-size: 18px; font-weight: bold; border: 2px solid black; }"
            )
            self.pushButton_armReset.setText("Arm")

    def updateUi_initial_hardware_state(self) -> None:
        # SigGen
        self.ui.checkBox_galvoActivate.setChecked(self.siggen.galvo_activated)
        self.ui.checkBox_galvoInvert.setChecked(self.siggen.galvo_inverted)
        self.ui.doubleSpinBox_galvoLeftAmplitude.setValue(self.siggen.galvo_left_amplitude)
        self.ui.doubleSpinBox_galvoRightAmplitude.setValue(self.siggen.galvo_right_amplitude)
        self.ui.doubleSpinBox_galvoLeftOffset.setValue(self.siggen.galvo_left_offset)
        self.ui.doubleSpinBox_galvoRightOffset.setValue(self.siggen.galvo_right_offset)

        self.ui.checkBox_etlActivate.setChecked(self.siggen.etl_activated)
        self.ui.doubleSpinBox_etlLeftAmplitude.setValue(self.siggen.etl_left_amplitude)
        self.ui.doubleSpinBox_etlRightAmplitude.setValue(self.siggen.etl_right_amplitude)
        self.ui.doubleSpinBox_etlLeftOffset.setValue(self.siggen.etl_left_offset)
        self.ui.doubleSpinBox_etlRightOffset.setValue(self.siggen.etl_right_offset)
        self.ui.doubleSpinBox_etlSteps.setValue(self.siggen.etl_steps)

        # Camera
        self.ui.doubleSpinBox_cameraExposureTime.setValue(
            self.camera.exposure_time * 1e3
        )  # camera(s) to ui(ms)
        self.ui.doubleSpinBox_cameraLineTime.setValue(
            self.camera.lightsheet_line_time * 1e6
        )  # camera(s) to ui(us)
        self.ui.doubleSpinBox_cameraExposedLines.setValue(
            self.camera.lightsheet_exposed_lines
        )
        self.ui.doubleSpinBox_cameraDelayLines.setValue(
            self.camera.lightsheet_delay_lines
        )
        # Set camera shutter mode comboBox options (default: Rolling)
        self.ui.comboBox_cameraShutterMode.insertItems(0, ["Rolling", "Lightsheet"])
        if self.camera.shutter_mode == "Lightsheet":
            self.ui.comboBox_cameraShutterMode.setCurrentIndex(1)
        else:
            self.ui.comboBox_cameraShutterMode.setCurrentIndex(0)
        self._acq.updateUi_camera_shutter_mode()

        # Lasers — both spinboxes are 0-100 % staged setpoints. Seed from
        # the persistent controller-side percentage, not the live HAL state,
        # so the staged value survives laser on/off and E-stop disarm/re-arm
        # cycles within the session.
        self.ui.doubleSpinBox_laserOneAmplitude.setValue(self.laser1_power_pct)
        self.ui.doubleSpinBox_laserTwoAmplitude.setValue(self.laser2_power_pct)

        # Wavelength labels — read from the live list[ILaser] instances.
        self.ui.label_72.setText(
            f'<html><head/><body><p><span style=" font-weight:600; font-size:18px;">'
            f"{self.lasers[0].wavelength} nm</span></p></body></html>"
        )
        self.ui.label_73.setText(
            f'<html><head/><body><p><span style=" font-weight:600; font-size:18px;">'
            f"{self.lasers[1].wavelength} nm</span></p></body></html>"
        )

        # Toggle button text + tooltips so the operator can find each laser
        # by wavelength rather than the generic "Laser1"/"Laser2" placeholder.
        self.ui.pushButton_laserOneToggle.setText(
            f"Toggle {self.lasers[0].wavelength} nm"
        )
        self.ui.pushButton_laserTwoToggle.setText(
            f"Toggle {self.lasers[1].wavelength} nm"
        )
        self.ui.pushButton_laserOneToggle.setToolTip(
            f"Toggle {self.lasers[0].wavelength} nm laser (DAQ AO Dev7/ao0)"
        )
        self.ui.pushButton_laserTwoToggle.setToolTip(
            f"Toggle Toptica iBeam ({self.lasers[1].wavelength} nm, COM4)"
        )

        # Motors
        self.motor_panel.updateUi_units()
