"""
Created on May 22, 2019

@authors: Pierre Girard-Collins & flesage
"""

import contextlib
import copy
import datetime
import logging
import os
import queue
import threading
import webbrowser

import h5py
import numpy as np
from matplotlib import pyplot as plt
from PyQt5.QtCore import QObject, Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QCloseEvent, QKeySequence
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QDialog,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QShortcut,
    QTableWidgetItem,
    QToolBar,
)
from scipy import stats

# FIXME - Free functions to integrate into own class (or at least cleanup/rename)
from lightsheet.config import cfg_read
from lightsheet.gaussian import func, gaussian
from lightsheet.gui.ui_controller import Ui_Controller
from lightsheet.gui.ui_properties import Ui_Properties
from lightsheet.hal import Camera, ETLs, Motors, SigGen

logger = logging.getLogger(__name__)


class Controller_MainWindow(QMainWindow):
    """Class for the MesoSPIM Controller"""

    # Dictionnary of configurable settings and their default values
    _cfg_settings: dict[str, str] = {}  # noqa: RUF012 - class-level config template, populated at definition, never mutated at runtime
    _cfg_settings["Units"] = "mm"
    _cfg_settings["Image File Format"] = "HDF5"

    # Signals
    sig_beep = pyqtSignal()
    sig_stylesheet = pyqtSignal(str)
    sig_message = pyqtSignal(str)
    sig_progress_update = pyqtSignal(int)

    sig_single_mode_finished = pyqtSignal()
    sig_live_mode_finished = pyqtSignal()
    sig_stack_mode_finished = pyqtSignal()
    sig_preview_mode_finished = pyqtSignal()
    sig_calibrate_camera_finished = pyqtSignal()  # TODO
    sig_calibrate_etl_finished = pyqtSignal()  # TODO

    sig_refresh_position_horizontal = pyqtSignal()  # TODO
    sig_refresh_position_vertical = pyqtSignal()  # TODO
    sig_refresh_position_camera = pyqtSignal()  # TODO

    # Per-laser status indicator (LSR-06). QTimer-driven polls (the L1
    # 100ms display timer and the L2 gated ~1s iBeam timer) and the
    # refresh-after-action call sites emit (idx, status) on this signal;
    # the GUI-thread slot updateUi_laser_status mutates the QLabel. No
    # QTimer callback or worker thread ever writes a QLabel directly
    # (AGENTS.md §11 — cross-thread UI updates go through signals).
    sig_laser_status = pyqtSignal(int, str)

    def __init__(self, demo: bool = False) -> None:
        # Demo mode flag — when True, hardware_init constructs Mock* HAL
        # instances (no hardware init) so the app runs on a dev box without
        # the microscope. Set from the --demo CLI flag / LIGHTSHEET_DEMO=1
        # env var parsed in lightsheet.__main__.main().
        self._demo_mode = demo
        # NOTES
        #
        # Previous Ui loading was done directly from .ui file with:
        # basepath = os.path.join(os.path.dirname(__file__))
        # uic.loadUi(os.path.join(basepath,"controller.ui"), self)
        #
        # Ui approach taken below requires generating .py file from .ui (Qt Designer file format)  # noqa: E501
        # This enables VSCode IntelliSense to work properly on Ui classes
        # PS command for Ui file:
        # pyuic5 .\ui_controller.ui -o .\ui_controller.py
        #
        # PS command for resource file:
        # pyrcc5 .\ui_controller.qrc -o .\ui_controller_rc.py
        #
        # The generated ui_controller.py uses a bare 'import ui_controller_rc'
        # for its resource module. That bare import relies on the gui/ directory
        # being on the search path; the gui and lightsheet packages themselves
        # resolve through the editable install (pip install -e .), so no search
        # path mutation is needed here for the project's own modules. The
        # generated resource import is a pyuic5 artifact that will be replaced
        # by a package-qualified import when the UI is regenerated.
        #
        # Also, see https://fuhm.org/super-harmful/
        # for explanation why we don't automatically init inherited class with:
        # super(Controller, self).__init__()
        # but rather explicitly with:
        # QMainWindow.__init__(self)
        #

        QMainWindow.__init__(self)
        self.ui = Ui_Controller()
        self.ui.setupUi(self)

        # E-stop cooperative-abort event. Starts clear (not set) so the
        # system boots ARMED — worker loops run normally until the operator
        # actuates the E-stop. Polled at the top of every acquisition worker
        # loop (live/single/stack) so a mid-acquisition E-stop stops new
        # frame acquisition at the next safe boundary. The synchronous
        # laser-zeroing happens on the GUI thread in updateUi_estop_pressed,
        # independent of when the worker threads reach their poll point.
        self.estop_event = threading.Event()
        # Track the Arm/Reset two-press state so a single press never returns
        # the system straight from ACTUATED to ARMED (D-01: reset only permits
        # re-arm, never re-energizes). False = button reads "Arm/Reset"
        # (actuated or armed); True = button reads "Arm" (disarmed, one more
        # press re-arms).
        self._estop_disarmed = False

        # Safety toolbar — created programmatically (not in the generated
        # .ui file) so it survives pyuic5 regeneration. Holds the E-stop
        # status indicator, the E-stop button, and the Arm/Reset button.
        self.toolBar_estop = QToolBar("Safety", self)
        self.toolBar_estop.setMovable(False)
        self.addToolBar(Qt.TopToolBarArea, self.toolBar_estop)

        # E-stop status indicator (green = ARMED, red = ACTUATED, gray = DISARMED)
        self.label_estopStatus = QLabel("● ARMED")
        self.label_estopStatus.setMinimumWidth(140)
        self.label_estopStatus.setStyleSheet("color: #34C759; font-weight: bold;")
        self.toolBar_estop.addWidget(self.label_estopStatus)

        self.toolBar_estop.addSeparator()

        # E-stop button — 18px Bold white "E-STOP" on red fill, 96x48 min
        # (prominent two-finger panic target). Checkable so the latch state
        # is queryable, though the visual state is driven by QSS in the
        # press handler rather than Qt's checked styling.
        self.pushButton_estop = QPushButton("E-STOP")
        self.pushButton_estop.setCheckable(True)
        self.pushButton_estop.setMinimumSize(96, 48)
        self.pushButton_estop.setStyleSheet(
            "QPushButton { background-color: #FF3B30; color: white; "
            "font-size: 18px; font-weight: bold; border: 2px solid black; }"
        )
        self.pushButton_estop.setToolTip(
            "Emergency stop (F12) — drives all lasers to 0 V and aborts the current acquisition"  # noqa: E501
        )
        self.pushButton_estop.clicked.connect(self.updateUi_estop_pressed)
        self.toolBar_estop.addWidget(self.pushButton_estop)

        # Arm/Reset button — 88x32 min (smaller than E-stop so the panic
        # stroke hits E-stop first). Two-press sequence: first press after
        # an E-stop DISARMS (gray), second press re-ARMS (green). Never
        # re-energizes a laser itself.
        self.pushButton_armReset = QPushButton("Arm/Reset")
        self.pushButton_armReset.setMinimumSize(88, 32)
        self.pushButton_armReset.clicked.connect(self.updateUi_arm_reset_pressed)
        self.toolBar_estop.addWidget(self.pushButton_armReset)

        # F12 hotkey — fires regardless of which widget has focus.
        self.shortcut_estop = QShortcut(QKeySequence("F12"), self)
        self.shortcut_estop.setContext(Qt.ApplicationShortcut)
        self.shortcut_estop.activated.connect(self.updateUi_estop_pressed)

        # Per-laser status indicators (LSR-06). Added programmatically per
        # AGENTS.md §8 (generated UI files are never hand-edited) — parented
        # into the existing groupBox_15 laser-panel column layouts
        # (verticalLayout_43 = L1 column, verticalLayout_44 = L2 column).
        # The labels show ● ON / ● OFF / ● ERR with green/gray/red bold
        # encoding, matching the E-stop status-label precedent. Updated via
        # sig_laser_status -> updateUi_laser_status (AGENTS.md §11 — no
        # direct widget mutation from a timer callback).
        #
        # Both columns already end with an Expanding vertical spacer
        # (spacerItem8 / spacerItem9) from the .ui file. We insert the
        # status + readback widgets BEFORE that spacer (at index 4) so they
        # sit right after the checkbox in both columns and the spacer pushes
        # them up from below — keeping the two columns horizontally aligned.
        # Using addWidget() would append after the spacer and push the
        # labels to the bottom, breaking alignment.
        self.label_laserOneStatus = QLabel("● OFF")
        self.label_laserOneStatus.setMinimumWidth(140)
        self.label_laserOneStatus.setStyleSheet(
            "color: #8E8E93; font-weight: bold;"
        )
        self.ui.verticalLayout_43.insertWidget(4, self.label_laserOneStatus)

        # L1 power readback field — DAQLaser has no hardware readback, so
        # this shows the staged mW (pct/100 * max_power_mw) returned by
        # get_output_power() (which returns self.power). Updated on the
        # 100ms display timer (same cadence as the L1 status poll) and on
        # refresh-after-action call sites. Mirrors the L2 readback label
        # structure so the two laser columns are visually symmetric.
        self.label_laserOneReadback = QLabel("0.0 mW")
        self.label_laserOneReadback.setMinimumWidth(80)
        self.label_laserOneReadback.setToolTip(
            "Laser 1 staged power (mW) — DAQ analog output has no hardware "
            "readback; this is the commanded value derived from the percentage"
        )
        self.ui.verticalLayout_43.insertWidget(5, self.label_laserOneReadback)

        self.label_laserTwoStatus = QLabel("● OFF")
        self.label_laserTwoStatus.setMinimumWidth(140)
        self.label_laserTwoStatus.setStyleSheet(
            "color: #8E8E93; font-weight: bold;"
        )
        self.ui.verticalLayout_44.insertWidget(4, self.label_laserTwoStatus)

        # iBeam power readback field (LSD-04) + manual Refresh button.
        # The readback is a read-only QLabel showing '{value:.1f} mW'
        # from self.lasers[1].get_output_power(), or a degraded
        # '{power:.1f} mW (cmd)' fallback with a tooltip on parse
        # failure / unsupported variant. The Refresh button re-queries
        # on demand (the gated ~1s poll also refreshes it). Both are
        # parented into the L2 column programmatically per AGENTS.md §8.
        # Inserted before the expanding spacer (same pattern as L1) so the
        # status + readback labels align with L1's; the Refresh button goes
        # after the readback (still before the spacer) and only L2 has it.
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
            self.updateUi_laser2_refresh_clicked
        )
        self.ui.verticalLayout_44.insertWidget(6, self.pushButton_laserTwoRefresh)

        # Connect the status signal to its GUI-thread slot once, here in
        # __init__, so every emit (from any poll path or refresh-after-
        # action call site) routes through the slot.
        self.sig_laser_status.connect(self.updateUi_laser_status)

        # Resize mainwindow
        # self.resize(QDesktopWidget().availableGeometry(self).size() * 0.75)

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

        # Update configurable settings with values found in config file
        self.cfg_settings = cfg_read("config.ini", "Controller", self.cfg_settings)

        # Assign configurable settings to instance variables
        if str(self.cfg_settings["Units"]) == "mm":
            self.units = "mm"
        if (
            str(self.cfg_settings["Units"]) == "\u03bcm"
            or str(self.cfg_settings["Units"]) == "um"
        ):
            self.units = "\u03bcm"
        else:  # default units
            self.units = "mm"

        if str.lower(self.cfg_settings["Image File Format"]) == "hdf5":
            self.save_format = "hdf5"
        if str.lower(self.cfg_settings["Image File Format"]) == "tiff":
            self.save_format = "tiff"
        else:  # default file format
            self.save_format = "hdf5"

        self.save_directory = os.path.normpath(
            os.path.expanduser("~") + "\\Documents\\LightSheetData"
        )
        self.save_filename = ""
        self.save_description = ""

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
            self.ui.lineEdit_saveFilename.setText(
                "Filename - Select Save Directory First"
            )
            self.ui.lineEdit_saveFilename.setEnabled(False)
            self.ui.lineEdit_saveDescription.setText(
                "Description - Select Save Directory First"
            )
            self.ui.lineEdit_saveDescription.setEnabled(False)

        # Flags
        self.single_mode_started = False
        self.preview_mode_started = False
        self.live_mode_started = False
        self.stack_mode_started = False
        self.camera_calibration_started = False
        self.etls_calibration_started = False

        # Operator-facing staged laser power setpoints in percent (0-100).
        # These are the single persistent source of truth for the spinbox
        # values, decoupled from the HAL's Volts/microwatt state so the
        # staged percentage survives laser on/off and E-stop disarm/re-arm
        # cycles within a running session — it only resets to 0 on app
        # restart. Set once at startup; only mutated by the debounced
        # amplitude handlers (_apply_laser*_amplitude).
        self.laser1_power_pct = 0.0
        self.laser2_power_pct = 0.0

        # Auto-laser checkbox states sampled on the GUI thread before an
        # acquisition worker starts. The workers must never read the widgets
        # themselves — Qt widgets belong to the GUI thread, and reading one
        # from a worker is undefined behaviour per Qt's threading model
        # (AGENTS.md §11) that can stall the worker mid-acquisition.
        # _cache_auto_laser_flags() refreshes these at every GUI-thread
        # entry point that leads to a worker calling start_lasers()/
        # stop_lasers().
        self._auto_laser1 = False
        self._auto_laser2 = False

        # Per-laser write locks live on each ILaser instance
        # (self.lasers[i]._lock), set in DAQLaser.__init__ /
        # IBeamSmartLaser.__init__ / MockLaser.__init__. The daemon-thread
        # write paths (_write_laser*_power, _toggle_laser*) acquire
        # self.lasers[i]._lock. Reentrant (RLock) so _toggle_laser* can
        # call _write_laser*_power under the same lock without deadlocking.
        # The E-stop path intentionally does NOT acquire any laser lock —
        # it must remain lock-free so a stuck toggle thread holding a
        # laser's lock can never delay the kill path (AGENTS.md §2).

        self.saving_allowed = False
        self.focus_selected = False
        self.horizontal_forward_boundary_selected = False
        self.horizontal_backward_boundary_selected = False
        self.stack_starting_plane = None
        self.stack_ending_plane = None

        self.default_buttons = [
            self.ui.pushButton_acqStartPreviewMode,
            self.ui.pushButton_acqStartLiveMode,
            self.ui.pushButton_acqStartStackMode,
            self.ui.pushButton_acqGetSingleImage,
        ]

        # Initial state of modes buttons
        # self.updateUi_modes_buttons(self.default_buttons)

        self.ui.pushButton_acqStartPreviewMode.setEnabled(True)
        self.ui.pushButton_acqStartLiveMode.setEnabled(True)
        self.ui.pushButton_acqStartStackMode.setEnabled(True)
        self.ui.pushButton_acqGetSingleImage.setEnabled(True)
        self.ui.pushButton_saveCurrentImage.setEnabled(False)
        self.ui.pushButton_calCameraStartCalibration.setEnabled(False)
        self.ui.pushButton_calCameraComputeFocus.setEnabled(False)
        self.ui.pushButton_calCameraShowInterpolation.setEnabled(False)
        self.ui.pushButton_calEtlStartCalibration.setEnabled(False)
        self.ui.pushButton_calEtlShowInterpolation.setEnabled(False)

        # The Camera Calibration and ETL Calibration workflows are dead code
        # (their worker bodies were never rebuilt after an earlier refactor).
        # Hide the start buttons programmatically rather than editing the
        # generated .ui file. The slot methods and signal connections are
        # kept so the buttons can be re-enabled later; the worker bodies are
        # stripped to no-ops below. Restorable from git history.
        self.ui.pushButton_calCameraStartCalibration.setVisible(False)
        self.ui.pushButton_calEtlStartCalibration.setVisible(False)

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
        self.ui.action_showSystemProperties.triggered.connect(
            self.open_properties_dialog
        )
        self.ui.action_openDocumentation.triggered.connect(self.open_help)

        # ---
        # Connections for the 'Motion' tab controls
        # ---

        # Connection for unit change
        self.ui.comboBox_units.currentTextChanged.connect(self.updateUi_units)

        # Connections for the sample motion buttons
        self.ui.pushButton_sampleStepUp.clicked.connect(self.updateUi_move_sample_up)
        self.ui.pushButton_sampleStepDown.clicked.connect(
            self.updateUi_move_sample_down
        )
        self.ui.pushButton_sampleStepForward.clicked.connect(
            self.updateUi_move_sample_forward
        )
        self.ui.pushButton_sampleStepBackward.clicked.connect(
            self.updateUi_move_sample_backward
        )
        self.ui.pushButton_sampleGotoOrigin.clicked.connect(
            self.updateUi_move_sample_to_origin
        )
        self.ui.pushButton_sampleSetOrigin.clicked.connect(
            self.updateUi_set_sample_origin
        )
        self.ui.pushButton_sampleGotoHPosition.clicked.connect(
            self.updateUi_move_to_horizontal_position
        )
        self.ui.pushButton_sampleGotoVPosition.clicked.connect(
            self.updateUi_move_to_vertical_position
        )

        # Connections for the camera motion buttons
        self.ui.pushButton_cameraGotoPosition.clicked.connect(
            self.updateUi_move_camera_to_position
        )
        self.ui.pushButton_cameraSetFocus.clicked.connect(
            self.updateUi_set_camera_focus
        )
        self.ui.pushButton_cameraStepForward.clicked.connect(
            self.updateUi_move_camera_forward
        )
        self.ui.pushButton_cameraStepBackward.clicked.connect(
            self.updateUi_move_camera_backward
        )
        # self.ui.pushButton_cameraGotoFocus.clicked.connect(self.updateUi_move_camera_to_focus)  # noqa: E501

        # ---
        # Connections for the 'Scan Settings' tab controls
        # ---

        # Connection for etl settings changes
        self.ui.doubleSpinBox_etlLeftAmplitude.valueChanged.connect(
            self.updateUi_etl_left_amplitude
        )
        self.ui.doubleSpinBox_etlRightAmplitude.valueChanged.connect(
            self.updateUi_etl_right_amplitude
        )
        self.ui.doubleSpinBox_etlLeftOffset.valueChanged.connect(
            self.updateUi_etl_left_offset
        )
        self.ui.doubleSpinBox_etlRightOffset.valueChanged.connect(
            self.updateUi_etl_right_offset
        )
        self.ui.checkBox_etlSync.stateChanged.connect(self.updateUi_etl_sync)
        self.ui.checkBox_etlActivate.stateChanged.connect(self.updateUi_etl_activate)
        self.ui.doubleSpinBox_etlSteps.valueChanged.connect(self.updateUi_etl_steps)

        # Connection for galvo settings changes
        self.ui.doubleSpinBox_galvoLeftAmplitude.valueChanged.connect(
            self.updateUi_galvo_left_amplitude
        )
        self.ui.doubleSpinBox_galvoRightAmplitude.valueChanged.connect(
            self.updateUi_galvo_right_amplitude
        )
        self.ui.doubleSpinBox_galvoLeftOffset.valueChanged.connect(
            self.updateUi_galvo_left_offset
        )
        self.ui.doubleSpinBox_galvoRightOffset.valueChanged.connect(
            self.updateUi_galvo_right_offset
        )
        self.ui.checkBox_galvoSync.stateChanged.connect(self.updateUi_galvo_sync)
        self.ui.checkBox_galvoActivate.stateChanged.connect(
            self.updateUi_galvo_activate
        )
        self.ui.checkBox_galvoInvert.stateChanged.connect(self.updateUi_galvo_invert)

        # Connection for laser settings changes
        self.ui.doubleSpinBox_laserOneAmplitude.valueChanged.connect(
            self.updateUi_laser1_amplitude
        )
        self.ui.doubleSpinBox_laserTwoAmplitude.valueChanged.connect(
            self.updateUi_laser2_amplitude
        )

        # Connection for camera settings changes
        self.ui.comboBox_cameraShutterMode.currentTextChanged.connect(
            self.updateUi_camera_shutter_mode
        )
        self.ui.doubleSpinBox_cameraExposureTime.valueChanged.connect(
            self.updateUi_camera_exposure_time
        )
        self.ui.doubleSpinBox_cameraLineTime.valueChanged.connect(
            self.updateUi_camera_line_time
        )
        self.ui.doubleSpinBox_cameraExposedLines.valueChanged.connect(
            self.updateUi_camera_exposed_lines
        )
        self.ui.doubleSpinBox_cameraDelayLines.valueChanged.connect(
            self.updateUi_camera_delay_lines
        )

        # ---
        # Connections for the 'Calibration' tab controls
        # ---
        self.ui.pushButton_calCameraStartCalibration.clicked.connect(
            self.camera_calibration_button
        )
        self.ui.pushButton_calCameraComputeFocus.clicked.connect(
            self.calculate_camera_focus
        )
        self.ui.pushButton_calCameraShowInterpolation.clicked.connect(
            self.show_camera_interpolation
        )
        self.ui.pushButton_calEtlStartCalibration.clicked.connect(
            self.etls_calibration_button
        )
        self.ui.pushButton_calEtlShowInterpolation.clicked.connect(
            self.show_etl_interpolation
        )
        self.ui.pushButton_calHorizontalStartRangeSelection.clicked.connect(
            self.updateUi_reset_boundaries
        )
        self.ui.pushButton_calHorizontalSetForwardLimit.clicked.connect(
            self.updateUi_set_horizontal_forward_boundary
        )
        self.ui.pushButton_calHorizontalSetBackwardLimit.clicked.connect(
            self.updateUi_set_horizontal_backward_boundary
        )

        # ---
        # Connections for the 'File Manager' tab controls
        # ---
        self.ui.pushButton_selectFile.clicked.connect(self.updateUi_select_file)
        self.ui.pushButton_selectDataset.clicked.connect(self.updateUi_select_dataset)
        self.ui.listWidget_fileDatasets.doubleClicked.connect(
            self.updateUi_select_dataset
        )

        # ---
        # Connections for the 'Manual Acquisition' controls
        # ---
        self.ui.pushButton_acqGetSingleImage.clicked.connect(
            self.updateUi_single_mode_button
        )
        self.ui.pushButton_acqStartLiveMode.clicked.connect(
            self.updateUi_live_mode_button
        )
        self.ui.pushButton_acqStartPreviewMode.clicked.connect(
            self.updateUi_preview_mode_button
        )

        # ---
        # Connections for the 'Automatic Acquisition' controls
        # ---
        self.ui.pushButton_acqStartStackMode.clicked.connect(
            self.updateUi_stack_mode_button
        )
        self.ui.doubleSpinBox_acqPlaneStepSize.valueChanged.connect(
            self.updateUi_set_number_of_planes
        )
        self.ui.pushButton_acqSetFirstPlane.clicked.connect(
            self.updateUi_set_stack_mode_starting_point
        )
        self.ui.pushButton_acqSetLastPlane.clicked.connect(
            self.updateUi_set_stack_mode_ending_point
        )

        # ---
        # Connections for the 'Lasers' controls
        # ---
        self.ui.pushButton_laserOneToggle.clicked.connect(self.laser1_toggle_button)
        self.ui.pushButton_laserTwoToggle.clicked.connect(self.laser2_toggle_button)

        # ---
        # Connections for the 'Save Settings' controls
        # ---
        self.ui.pushButton_saveSelectDirectory.clicked.connect(
            self.updateUi_select_directory
        )
        self.ui.pushButton_saveCurrentImage.clicked.connect(
            self.updateUi_save_single_image
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
        self.sig_single_mode_finished.connect(self.updateUi_post_single_mode)
        self.sig_live_mode_finished.connect(self.updateUi_post_live_mode)
        self.sig_stack_mode_finished.connect(self.updateUi_post_stack_mode)
        self.sig_preview_mode_finished.connect(self.updateUi_post_preview_mode)

        # ---
        # Signal connections for position refresh requests
        # ---
        self.sig_refresh_position_horizontal.connect(self.updateUi_position_horizontal)
        self.sig_refresh_position_vertical.connect(self.updateUi_position_vertical)
        self.sig_refresh_position_camera.connect(self.updateUi_position_camera)

        # Start single shot timer to complete hardware init after event loop is started
        self.timer_hardware_init = QTimer()
        self.timer_hardware_init.setSingleShot(True)
        self.timer_hardware_init.timeout.connect(self.hardware_init)
        self.timer_hardware_init.start(100)

        # Debounce timers for the laser amplitude spinboxes. Each valueChanged
        # restarts the timer; only 300ms after the last edit does the timeout
        # slot fire, coalescing rapid keystrokes into a single committed write
        # (one HAL round-trip instead of one per keystroke). The timeout slot
        # stores the staged percentage and offloads the scaled HAL write to a
        # short-lived worker thread so the GUI event loop is never blocked.
        self._laser1_amplitude_timer = QTimer()
        self._laser1_amplitude_timer.setSingleShot(True)
        self._laser1_amplitude_timer.timeout.connect(self._apply_laser1_amplitude)
        self._laser2_amplitude_timer = QTimer()
        self._laser2_amplitude_timer.setSingleShot(True)
        self._laser2_amplitude_timer.timeout.connect(self._apply_laser2_amplitude)

    def hardware_init(self) -> None:
        """
        Completes initialisation of hardware and image consumers
        Launches timer to periodically refresh image display port (imageView)
        """
        # Change to busy cursor and display status message
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.ui.statusbar.showMessage("Initializing hardware, please wait...")
        self.ui.statusbar.repaint()

        # Instantiating hardware components. Under demo mode all device
        # families construct Mock* instances so no hardware init runs on a
        # dev box. The camera-before-siggen dependency ordering is preserved
        # under both branches (the mock camera still carries the
        # xsize/ysize/line_time the SigGen waveform timing derives from).
        #
        # Lasers: self.lasers is a list[ILaser] — index 0 is Laser 1
        # (DAQ AO /Dev7/ao0, 555 nm), index 1 is Laser 2 (Toptica iBeam,
        # 640 nm, COM4). The old 2-channel Lasers container + separate
        # IBeam attribute are retired; self.ibeam no longer exists.
        if self._demo_mode:
            from lightsheet.hal import (
                MockCamera,
                MockETLs,
                MockLaser,
                MockMotors,
                MockSigGen,
            )

            self.camera = MockCamera(verbose=True)
            # Signal Generator needs to know about Camera settings to generate
            # proper scan waveforms — dependency ordering must be preserved
            # under both branches (the mock camera still carries the
            # xsize/ysize/line_time the SigGen waveform timing derives from).
            self.siggen = MockSigGen(self.camera)
            self.motors = MockMotors()
            self.lasers = [
                MockLaser(
                    wavelength=555,
                    max_power_mw=300.0,
                    mw_per_volt=60.0,
                    label="Laser 1 (555 nm)",
                ),
                MockLaser(
                    wavelength=640,
                    max_power_mw=150.0,
                    label="Laser 2 (640 nm)",
                ),
            ]
            self.etls = MockETLs()
        else:
            from lightsheet.hal import DAQLaser, IBeamSmartLaser

            self.camera = Camera(verbose=True)
            self.siggen = SigGen(self.camera)
            self.motors = Motors()
            # Laser 1 calibration lives in config.ini [Lasers] — the single
            # source of truth for the 555 nm diode's mW-per-Volt and max
            # output. DAQLaser takes mW-native constructor args, so derive
            # them here: max_power_mw = Max Power (V) * mW per Volt,
            # mw_per_volt = mW per Volt, wavelength = Wavelength.
            _l1_cfg = cfg_read(
                "config.ini",
                "Lasers",
                {
                    "Laser1 Wavelength": 555,
                    "Laser1 Power": 0.0,
                    "Laser1 Max Power": 5.0,
                    "Laser1 mW per Volt": 60.0,
                },
            )
            self.lasers = [
                DAQLaser(
                    terminal="/Dev7/ao0",
                    wavelength=int(_l1_cfg["Laser1 Wavelength"]),
                    mw_per_volt=float(_l1_cfg["Laser1 mW per Volt"]),
                    max_power_mw=float(_l1_cfg["Laser1 Max Power"])
                    * float(_l1_cfg["Laser1 mW per Volt"]),
                    label="Laser 1 (555 nm)",
                ),
                IBeamSmartLaser(label="Laser 2 (640 nm)"),
            ]
            self.etls = ETLs()

        # Making sure ETLs are in analog mode
        self.etls.open()
        self.etls.set_analog_mode()

        # Open the Toptica iBeam serial laser (COM4). Laser 2 is now
        # self.lasers[1] (an IBeamSmartLaser adapter wrapping the inner
        # IBeam serial engine). The adapter constructs the inner IBeam in
        # __init__ but does NOT open the serial port — open() is a real-
        # hardware lifecycle verb the controller drives here, mirroring the
        # pre-rewrite pattern. Failure is non-fatal — the DAQ laser path
        # still works if the iBeam is offline — but surface the error so the
        # operator knows the red laser is unavailable. open() calls
        # enable_channel() internally; enable_channel() catches
        # SerialException and sets self.error without re-raising, so a plain
        # try/except around open() cannot detect a channel-enable failure —
        # the error surface must be inspected after open() returns.
        #
        # The ILaser.open() contract is uniform across backends:
        # IBeamSmartLaser.open() delegates to the inner serial engine and
        # mirrors its error surface onto the adapter; MockLaser.open() is a
        # no-op (no hardware to open), so the same call site works in demo
        # mode without a demo-mode gate.
        try:
            self.lasers[1].open()
            if self.lasers[1].error:
                self.sig_message.emit(
                    f"iBeam opened but channel enable failed: "
                    f"{self.lasers[1].error_message}"
                )
                self.lasers[1].error = 0
        except Exception as e:
            self.sig_message.emit(f"iBeam open failed: {e}")

        # Update Ui with initial hardware state
        self.updateUi_initial_hardware_state()

        # Instantiating the display port queue (image consumer)
        self.frame_viewer = FrameViewer(
            self, rows=self.camera.ysize, columns=self.camera.xsize
        )

        # Instantiating the frame saver (image consumer)
        self.frame_saver = FrameSaver(self)

        # Start timer to periodically (100ms) refresh the display port.
        # The L1 status poll rides this same timer (additive connection —
        # zero added serial cost, L1 status is a pure in-HAL active-flag
        # read) so the DAQ laser status is genuinely live at 100ms. The L1
        # readback refresh rides it too — DAQLaser has no hardware
        # readback, so get_output_power() returns the staged mW (pure
        # in-HAL attribute read, no serial I/O), and the 100ms cadence
        # keeps the L1 mW field live as the operator edits the percentage.
        self.timer_imageview = QTimer()
        self.timer_imageview.timeout.connect(self.frame_viewer.updateUi_refresh_view)
        self.timer_imageview.timeout.connect(lambda: self._poll_laser_status([0]))
        self.timer_imageview.timeout.connect(lambda: self._refresh_laser_readback(0))
        self.timer_imageview.start(100)

        # L2 (iBeam) status poll — a separate gated QTimer at the
        # config-tunable [iBeam] Status Poll Interval (default 1.0s,
        # rig-validated 0/12 misattribution at 1s and 0.5s). The poll
        # callback (_poll_laser2_status_gated) probes the iBeam
        # per-instance lock and skips silently while a power write is in
        # progress, so a periodic status query never blocks on a write
        # and never misattributes a reply.
        _ibeam_cfg = cfg_read("config.ini", "iBeam", {"Status Poll Interval": 1.0})
        self.timer_laser2_status = QTimer()
        self.timer_laser2_status.timeout.connect(self._poll_laser2_status_gated)
        # The L2 gated poll calls get_output_power() — now part of the
        # ILaser contract on every backend (IBeamSmartLaser queries the
        # serial engine; DAQLaser / MockLaser return the staged mW power).
        # The timer starts in both real and demo mode so the L2 status
        # indicator + readback field stay live under demo too.
        self.timer_laser2_status.start(
            int(float(_ibeam_cfg["Status Poll Interval"]) * 1000)
        )

        # Init done, restore normal cursor. Under demo mode emit the demo
        # indicator (window-title suffix + status-bar message) directly via
        # QStatusBar.showMessage — NOT via sig_message.emit — so it does not
        # pollute the future golden-master sig_message sequence (UI-SPEC).
        QApplication.restoreOverrideCursor()
        if self._demo_mode:
            self.setWindowTitle(self.windowTitle() + " [DEMO]")
            self.ui.statusbar.showMessage(
                "Demo mode — no hardware connected (mock HAL)", 5000
            )
        else:
            self.ui.statusbar.showMessage("Ready", 2000)

    def closeEvent(self, event: QCloseEvent) -> None:
        """
        Making sure that everything is closed when the user exits the software.
        This function executes automatically when the user closes the UI.
        This is an intrinsic function name of Qt, don't change the name even
        if it doesn't follow the naming convention
        """
        result = QMessageBox.question(
            self,
            "Confirm Exit...",
            "Are you sure you want to exit ?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if result == QMessageBox.Yes:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            self.ui.statusbar.showMessage("Shutting down hardware...")
            self.ui.statusbar.repaint()
            self.close_modes()
            # Join each acquisition worker thread with a bounded timeout
            # instead of an unconditional fixed sleep. A worker stuck
            # inside a blocking hardware call (camera.monitor_recorder up to
            # its timeout, an iBeam serial round-trip, a motor move) would
            # otherwise hang shutdown indefinitely; the bounded wait gives
            # it a chance to exit cleanly while guaranteeing shutdown
            # proceeds regardless. These thread attributes only exist once
            # their mode has been started at least once, hence getattr.
            for attr in (
                "single_mode_thread",
                "preview_mode_thread",
                "live_mode_thread",
                "stack_mode_thread",
            ):
                worker_thread = getattr(self, attr, None)
                if worker_thread is not None and worker_thread.is_alive():
                    worker_thread.join(timeout=5.0)
                    if worker_thread.is_alive():
                        logger.warning(
                            "%s still alive after 5s join timeout during "
                            "closeEvent — proceeding with shutdown anyway.",
                            attr,
                        )
            self.camera.close()
            self.etls.close()
            # Laser 2 (iBeam) lifecycle close — ILaser.close() delegates to
            # the inner serial engine on IBeamSmartLaser and is a no-op on
            # MockLaser, so the same call site works in real and demo mode.
            self.lasers[1].close()
            self.timer_imageview.stop()
            self.timer_laser2_status.stop()
            QApplication.restoreOverrideCursor()
            event.accept()
        else:
            event.ignore()

    @pyqtSlot(str)
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
        self.properties_dialog.setAttribute(Qt.WA_DeleteOnClose)
        self.properties_dialog.open()
        self.properties_dialog.get_properties()

    def open_help(self) -> None:
        """Open help documentation (PDF)"""
        guide_pdf = os.path.dirname(os.path.abspath(__file__)) + r"\..\Guide.pdf"
        webbrowser.open_new(guide_pdf)

    def updateUi_light_theme(self) -> None:
        self.sig_stylesheet.emit("light")
        return None

    def updateUi_dark_theme(self) -> None:
        self.sig_stylesheet.emit("dark")
        return None

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

    # def enqueue_frame(self, frame:np.uint16):
    #     '''
    #     Enqueue a frame for display into the imageView widget
    #     '''
    #     try:
    #         self.frame_display_queue.put(frame, block=False)
    #     except queue.Full:
    #         pass

    # def updateUi_refresh_view(self):
    #     '''
    #     Retrieve frame from queue and display into imageView widget
    #     Executes on each interval of the QTimer
    #     '''
    #     try:
    #         frame = self.frame_display_queue.get(block=False)
    #     except queue.Empty:
    #         pass
    #     else:
    #         self.ui.imageView.setImage(frame, autoRange=False, autoLevels=False, autoHistogramRange=False)  # noqa: E501

    def updateUi_motor_buttons(self, disable_button: bool = True) -> None:
        """Enable or disable all motor buttons"""
        # FIXME
        buttons_to_disable = [
            self.ui.pushButton_sampleStepUp,
            self.ui.pushButton_sampleGotoOrigin,
            self.ui.pushButton_sampleStepDown,
            self.ui.pushButton_sampleStepBackward,
            self.ui.pushButton_sampleStepForward,
            self.ui.pushButton_sampleGotoHPosition,
            self.ui.pushButton_sampleGotoVPosition,
            self.ui.pushButton_cameraStepBackward,
            self.ui.pushButton_cameraStepForward,
            # self.ui.pushButton_cameraGotoFocus,
            self.ui.pushButton_cameraGotoPosition,
        ]
        for button in buttons_to_disable:
            if disable_button:
                button.setEnabled(False)
            else:
                button.setEnabled(True)

    def updateUi_modes_buttons(self, buttons_to_enable: list[QPushButton]) -> None:
        """Update mode buttons status : disable buttons, except for those specified to be enabled"""  # noqa: E501
        # FIXME
        aquisition_buttons = [
            self.ui.pushButton_acqStartPreviewMode,
            self.ui.pushButton_acqStartLiveMode,
            self.ui.pushButton_acqStartStackMode,
            self.ui.pushButton_acqGetSingleImage,
            self.ui.pushButton_saveCurrentImage,
            self.ui.pushButton_calCameraComputeFocus,
            self.ui.pushButton_calCameraShowInterpolation,
            self.ui.pushButton_calEtlShowInterpolation,
        ]
        for button in aquisition_buttons:
            if button in buttons_to_enable:
                button.setEnabled(True)
            else:
                button.setEnabled(False)

    def updateUi_enable_buttons(self, buttons_to_enable: list[QPushButton]) -> None:
        """Enable buttons"""
        for button in buttons_to_enable:
            button.setEnabled(True)

    def updateUi_disable_buttons(self, buttons_to_disable: list[QPushButton]) -> None:
        """Disable buttons"""
        for button in buttons_to_disable:
            button.setEnabled(False)

    def _cache_auto_laser_flags(self) -> None:
        """Sample the auto-laser checkboxes. GUI thread only.

        Acquisition workers run start_lasers()/stop_lasers() off the GUI
        thread and must read these cached bools rather than the widgets,
        which belong to the GUI thread (AGENTS.md §11). Called at every
        entry point that leads to a worker calling start_lasers()/
        stop_lasers(): close_modes (which calls stop_lasers directly) and
        the three updateUi_*_mode_button handlers that spawn a worker.
        """
        self._auto_laser1 = self.ui.checkBox_laserOneAutomatic.isChecked()
        self._auto_laser2 = self.ui.checkBox_laserTwoAutomatic.isChecked()

    def close_modes(self) -> None:
        """Close all thread modes if they are active"""
        # FIXME
        # Sample the auto-laser checkboxes on the GUI thread before any
        # stop_lasers() call below — stop_lasers runs off the GUI thread
        # in some call paths and must read the cached bools, not widgets.
        self._cache_auto_laser_flags()
        if self.preview_mode_started:
            self.preview_mode_started = False
        if self.live_mode_started:
            self.live_mode_started = False
        if self.stack_mode_started:
            self.stack_mode_started = False
        if self.camera_calibration_started:
            self.camera_calibration_started = False
        if self.etls_calibration_started:
            self.etls_calibration_started = False
        if self.lasers[0].active or self.lasers[1].active:
            self.stop_lasers()

    @pyqtSlot()
    def updateUi_estop_pressed(self) -> None:
        """E-stop button / F12 hotkey handler.

                Synchronously zeroes both lasers on the GUI thread the instant it
        fires, then sets the cooperative-abort Event so worker threads stop acquiring
        new frames at their next poll point. Idempotent (re-press re-sets the Event
        and re-writes 0 V). Never re-energizes — re-arming requires the two-press
        Arm/Reset sequence in updateUi_arm_reset_pressed.
        """
        # 1. Cooperative-abort Event — workers poll this at the top of
        #    live_mode_worker, before acquire_scan in single_mode_worker,
        #    and alongside stack_mode_started in stack_mode_worker.
        self.estop_event.set()
        # 2. Drive BOTH lasers off synchronously on the GUI thread. The
        #    kill path is lock-free — it does NOT acquire self.lasers[i]._lock
        #    — so a stuck daemon write thread holding a laser's lock can
        #    never delay the kill path (AGENTS.md §2). Each backend's off()
        #    catches its own SDK errors internally and sets laser.error
        #    rather than re-raising, so a try/except here can never fire
        #    for a hardware failure. Check the error surface after each
        #    off() and warn the operator explicitly that the laser may
        #    still be emitting — never silently show a clean state.
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
        self._poll_laser_status([0, 1])
        self._refresh_laser_readback(0)
        self._refresh_laser_readback(1)

        # 4. Latch the UI into ACTUATED: red indicator, yellow 4px border
        #    on the E-stop button ("latched — Arm/Reset before re-energizing").
        #    Re-presses are idempotent — re-applying the same QSS is a no-op.
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

    @pyqtSlot()
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
        self.ui.doubleSpinBox_galvoLeftAmplitude.setValue(
            self.siggen.galvo_left_amplitude
        )
        self.ui.doubleSpinBox_galvoRightAmplitude.setValue(
            self.siggen.galvo_right_amplitude
        )
        self.ui.doubleSpinBox_galvoLeftOffset.setValue(self.siggen.galvo_left_offset)
        self.ui.doubleSpinBox_galvoRightOffset.setValue(self.siggen.galvo_right_offset)

        self.ui.checkBox_etlActivate.setChecked(self.siggen.etl_activated)
        self.ui.doubleSpinBox_etlLeftAmplitude.setValue(self.siggen.etl_left_amplitude)
        self.ui.doubleSpinBox_etlRightAmplitude.setValue(
            self.siggen.etl_right_amplitude
        )
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
        self.updateUi_camera_shutter_mode()

        # Lasers — both spinboxes are 0-100 % staged setpoints (per the
        # .ui source). Seed from the persistent controller-side percentage,
        # not the live HAL state, so the staged value survives laser on/off
        # and E-stop disarm/re-arm cycles within the session. The %-to-
        # absolute conversion (pct/100 * Max Power) happens once, at the
        # HAL call boundary inside _write_laser1_power/_write_laser2_power.
        self.ui.doubleSpinBox_laserOneAmplitude.setValue(self.laser1_power_pct)
        self.ui.doubleSpinBox_laserTwoAmplitude.setValue(self.laser2_power_pct)

        # Wavelength labels — read from the live list[ILaser] instances so the
        # operator sees the real configured wavelength (no hardcoded numbers).
        self.ui.label_72.setText(
            f'<html><head/><body><p><span style=" font-weight:600; font-size:18px;">'
            f"{self.lasers[0].wavelength} nm</span></p></body></html>"
        )
        self.ui.label_73.setText(
            f'<html><head/><body><p><span style=" font-weight:600; font-size:18px;">'
            f"{self.lasers[1].wavelength} nm</span></p></body></html>"
        )

        # Toggle button text + tooltips so the operator can find each laser by
        # wavelength rather than the generic "Laser1"/"Laser2" placeholder.
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
        self.updateUi_units()

    def _poll_laser_status(self, indices: list[int]) -> None:
        """Compute a status string per requested laser index and emit
        sig_laser_status(idx, status). Called from the L1 100ms display
        timer, the L2 gated ~1s iBeam timer, and the refresh-after-action
        call sites (toggle / write / start / stop / E-stop).

        Status precedence is error > active > inactive: an errored-but-
        still-active laser shows ERR, not ON (the HAL error surface is
        authoritative — AGENTS.md §10). The emit crosses through the Qt
        signal/slot queue so the QLabel mutation happens on the GUI
        thread (AGENTS.md §11 — no direct widget write from a timer).
        """
        for i in indices:
            laser = self.lasers[i]
            if laser.error:
                status = "error"
            elif laser.active:
                status = "active"
            else:
                status = "inactive"
            self.sig_laser_status.emit(i, status)

    def _poll_laser2_status_gated(self) -> None:
        """Gated L2 status + readback poll driven by the ~1s iBeam status
        QTimer.

        Probes self.lasers[1]._lock with acquire(blocking=False): if the
        lock is held by an in-progress power write, skip this cycle
        silently (no error surfaced — the operator can retry via the
        Refresh button or wait for the next tick). If the lock is free,
        release it immediately and proceed with the status poll + the
        readback refresh. The status poll reads only instant in-HAL
        attributes (.error / .active — no serial I/O, no misattribution
        risk); the readback refresh acquires the lock itself for the
        serial round-trip. The probe-then-release pattern means a write
        can start between the probe and the readback's own acquire, but
        the readback's acquire(blocking=False) will then skip — the
        operator simply sees the next tick's reading.
        """
        if not self.lasers[1]._lock.acquire(blocking=False):
            return
        self.lasers[1]._lock.release()
        self._poll_laser_status([1])
        self._refresh_laser_readback(1)

    def _refresh_laser_readback(self, idx: int) -> None:
        """Query self.lasers[idx].get_output_power() and update the
        per-laser readback label. Acquires the laser's per-instance lock
        with acquire(blocking=False): if held by an in-progress write,
        return silently (no-op — the operator can retry). On success,
        query and update the label, then release in finally.

        On a populated readback (float mW): sets the label to
        '{value:.1f} mW'. On a None readback (parse failure / unsupported
        variant): sets the label to '{power:.1f} mW (cmd)' — the last
        commanded power — with a tooltip explaining the fallback so the
        operator can distinguish a live readback from a stale commanded
        value.

        Works for both lasers: idx=0 (L1/DAQLaser — get_output_power()
        returns the staged mW, never None in practice) and idx=1 (L2/iBeam
        — get_output_power() queries the serial readback, may return None).
        The readback labels are indexed in parallel with self.lasers.
        """
        labels = [self.label_laserOneReadback, self.label_laserTwoReadback]
        label = labels[idx]
        laser = self.lasers[idx]
        if not laser._lock.acquire(blocking=False):
            return
        try:
            value = laser.get_output_power()
            if value is not None:
                label.setText(f"{value:.1f} mW")
            else:
                label.setText(f"{laser.power:.1f} mW (cmd)")
                label.setToolTip(
                    "Power readback unavailable (parse failure or this "
                    "variant does not support readback). Showing last "
                    "commanded value may be stale."
                )
        finally:
            laser._lock.release()

    @pyqtSlot()
    def updateUi_laser2_refresh_clicked(self) -> None:
        """Manual Refresh Power button handler — re-queries the L2 laser
        status + power readback on demand. The readback refresh and the
        status poll each acquire the L2 per-instance lock independently
        with acquire(blocking=False); if a power write is in progress,
        both are silent no-ops (the operator can retry).

        Works uniformly across backends: ``get_output_power()`` is on the
        ILaser contract (IBeamSmartLaser queries the serial engine;
        DAQLaser / MockLaser return the staged mW power), so no demo-mode
        gate is needed."""
        self._refresh_laser_readback(1)
        self._poll_laser_status([1])

    @pyqtSlot(int, str)
    def updateUi_laser_status(self, idx: int, status: str) -> None:
        """GUI-thread slot — maps a (idx, status) emit from
        sig_laser_status to the per-laser QLabel text + semantic color.
        status is 'active' / 'inactive' / 'error' (set by
        _poll_laser_status). The label list is indexed by laser index.
        """
        labels = [self.label_laserOneStatus, self.label_laserTwoStatus]
        if status == "active":
            labels[idx].setText("● ON")
            labels[idx].setStyleSheet(
                "color: #34C759; font-weight: bold;"
            )
        elif status == "inactive":
            labels[idx].setText("● OFF")
            labels[idx].setStyleSheet(
                "color: #8E8E93; font-weight: bold;"
            )
        else:  # "error"
            labels[idx].setText("● ERR")
            labels[idx].setStyleSheet(
                "color: #FF3B30; font-weight: bold;"
            )

    def updateUi_units(self) -> None:
        """Updates all the widgets of the motion tab after a unit change"""
        self.units = self.ui.comboBox_units.currentText()

        if self.units == "mm":
            self.units_decimals = 3
            self.units_fixformat = "{:.5f} {}"
            self.units_increment = 0.1
        elif self.units == "\u03bcm":
            self.units_decimals = 0
            self.units_fixformat = "{:.2f} {}"
            self.units_increment = 100

        # Updates to horizontal position
        self.ui.doubleSpinBox_sampleSetHPosition.setDecimals(self.units_decimals)
        self.ui.doubleSpinBox_sampleSetHPosition.setSuffix(f" {self.units}")
        self.ui.doubleSpinBox_sampleSetHPosition.setMinimum(
            self.motors.horizontal.get_limit_low(self.units)
        )
        self.ui.doubleSpinBox_sampleSetHPosition.setMaximum(
            self.motors.horizontal.get_limit_high(self.units)
        )

        # Updates to vertical position
        self.ui.doubleSpinBox_sampleSetVPosition.setDecimals(self.units_decimals)
        self.ui.doubleSpinBox_sampleSetVPosition.setSuffix(f" {self.units}")
        self.ui.doubleSpinBox_sampleSetVPosition.setMinimum(
            self.motors.vertical.get_limit_low(self.units)
        )
        self.ui.doubleSpinBox_sampleSetVPosition.setMaximum(
            self.motors.vertical.get_limit_high(self.units)
        )

        # Updates to camera position
        self.ui.doubleSpinBox_cameraSetPosition.setDecimals(self.units_decimals)
        self.ui.doubleSpinBox_cameraSetPosition.setSuffix(f" {self.units}")
        self.ui.doubleSpinBox_cameraSetPosition.setMinimum(
            self.motors.camera.get_limit_low(self.units)
        )
        self.ui.doubleSpinBox_cameraSetPosition.setMaximum(
            self.motors.camera.get_limit_high(self.units)
        )

        # Updates to horizontal step size (increment/decrement)
        self.ui.doubleSpinBox_sampleHStepSize.setValue(self.units_increment)
        self.ui.doubleSpinBox_sampleHStepSize.setDecimals(self.units_decimals)
        self.ui.doubleSpinBox_sampleHStepSize.setSuffix(f" {self.units}")
        self.ui.doubleSpinBox_sampleHStepSize.setMinimum(10**-self.units_decimals)
        maximum_horizontal_increment = (
            self.ui.doubleSpinBox_sampleSetHPosition.maximum()
            - self.ui.doubleSpinBox_sampleSetHPosition.minimum()
        )
        self.ui.doubleSpinBox_sampleHStepSize.setMaximum(maximum_horizontal_increment)

        # Updates to vertical step size (increment/decrement)
        self.ui.doubleSpinBox_sampleVStepSize.setValue(self.units_increment)
        self.ui.doubleSpinBox_sampleVStepSize.setDecimals(self.units_decimals)
        self.ui.doubleSpinBox_sampleVStepSize.setSuffix(f" {self.units}")
        self.ui.doubleSpinBox_sampleVStepSize.setMinimum(10**-self.units_decimals)
        maximum_vertical_increment = (
            self.ui.doubleSpinBox_sampleSetVPosition.maximum()
            - self.ui.doubleSpinBox_sampleSetVPosition.minimum()
        )
        self.ui.doubleSpinBox_sampleVStepSize.setMaximum(maximum_vertical_increment)

        # Updates to camera step size (increment/decrement)
        self.ui.doubleSpinBox_cameraStepSize.setValue(self.units_increment)
        self.ui.doubleSpinBox_cameraStepSize.setDecimals(self.units_decimals)
        self.ui.doubleSpinBox_cameraStepSize.setSuffix(f" {self.units}")
        self.ui.doubleSpinBox_cameraStepSize.setMinimum(10**-self.units_decimals)
        maximum_camera_increment = (
            self.ui.doubleSpinBox_cameraSetPosition.maximum()
            - self.ui.doubleSpinBox_cameraSetPosition.minimum()
        )
        self.ui.doubleSpinBox_cameraStepSize.setMaximum(maximum_camera_increment)

        # Update current positions indicators
        self.updateUi_position_indicators()

    def updateUi_position_indicators(self) -> None:
        """Refreshes the position indicators"""
        self.updateUi_position_horizontal()
        self.updateUi_position_vertical()
        self.updateUi_position_camera()

    def updateUi_position_horizontal(self) -> None:
        """Updates the current horizontal sample position displayed"""
        self.current_horizontal_position_text = self.units_fixformat.format(
            self.motors.horizontal.get_position(self.units), self.units
        )
        self.ui.label_sampleCurrentHPosition.setText(
            self.current_horizontal_position_text
        )

    def updateUi_position_vertical(self) -> None:
        """Updates the current vertical sample position displayed"""
        self.current_vertical_position_text = self.units_fixformat.format(
            self.motors.vertical.get_position(self.units), self.units
        )
        self.ui.label_sampleCurrentVPosition.setText(
            self.current_vertical_position_text
        )

    def updateUi_position_camera(self) -> None:
        """Updates the current camera position displayed"""
        self.current_camera_position_text = self.units_fixformat.format(
            self.motors.camera.get_position(self.units), self.units
        )
        self.ui.label_cameraCurrentPosition.setText(self.current_camera_position_text)

    def updateUi_move_to_horizontal_position(self) -> None:
        """Moves the sample to a specified horizontal position"""
        if (
            self.ui.doubleSpinBox_sampleSetHPosition.value()
            >= self.motors.horizontal.get_limit_low(self.units)
        ) and (
            self.ui.doubleSpinBox_sampleSetHPosition.value()
            <= self.motors.horizontal.get_limit_high(self.units)
        ):
            try:
                self.motors.horizontal.move_absolute_position(
                    self.ui.doubleSpinBox_sampleSetHPosition.value(), self.units
                )
            except ValueError:
                self.sig_message.emit(
                    "Move rejected — horizontal would exceed travel limits. Move the stage closer to the travel range and retry."  # noqa: E501
                )
                self.sig_beep.emit()
            else:
                self.updateUi_message_printer("Sample moving to horizontal position")
            self.updateUi_position_horizontal()
        else:
            self.updateUi_message_printer("Out of boundaries")
            self.sig_beep.emit()

    def updateUi_move_to_vertical_position(self) -> None:
        """Moves the sample to a specified vertical position"""
        if (
            self.ui.doubleSpinBox_sampleSetVPosition.value()
            >= self.motors.vertical.get_limit_low(self.units)
        ) and (
            self.ui.doubleSpinBox_sampleSetVPosition.value()
            <= self.motors.vertical.get_limit_high(self.units)
        ):
            try:
                self.motors.vertical.move_absolute_position(
                    self.ui.doubleSpinBox_sampleSetVPosition.value(), self.units
                )
            except ValueError:
                self.sig_message.emit(
                    "Move rejected — vertical would exceed travel limits. Move the stage closer to the travel range and retry."  # noqa: E501
                )
                self.sig_beep.emit()
            else:
                self.updateUi_message_printer("Sample moving to vertical position")
            self.updateUi_position_vertical()
        else:
            self.updateUi_message_printer("Out of boundaries")
            self.sig_beep.emit()

    def updateUi_move_sample_to_origin(self) -> None:
        """Moves vertical and horizontal sample motors to origin position"""
        if (
            self.motors.horizontal.get_origin(self.units)
            <= self.motors.horizontal.get_limit_high(self.units)
        ) and (
            self.motors.horizontal.get_origin(self.units)
            >= self.motors.horizontal.get_limit_low(self.units)
        ):
            # Moving sample to horizontal origin
            try:
                self.motors.horizontal.move_absolute_position(
                    self.motors.horizontal.get_origin(self.units), self.units
                )
            except ValueError:
                self.sig_message.emit(
                    "Move rejected — horizontal would exceed travel limits. Move the stage closer to the travel range and retry."  # noqa: E501
                )
                self.sig_beep.emit()
            else:
                self.updateUi_message_printer("Moving to horizontal origin")
            self.updateUi_position_horizontal()
        else:
            self.sig_beep.emit()
            self.updateUi_message_printer("Horizontal origin out of boundaries")

        if (
            self.motors.vertical.get_origin(self.units)
            <= self.motors.vertical.get_limit_high(self.units)
        ) and (
            self.motors.vertical.get_origin(self.units)
            >= self.motors.vertical.get_limit_low(self.units)
        ):
            # Moving sample to vertical origin
            try:
                self.motors.vertical.move_absolute_position(
                    self.motors.vertical.get_origin(self.units), self.units
                )
            except ValueError:
                self.sig_message.emit(
                    "Move rejected — vertical would exceed travel limits. Move the stage closer to the travel range and retry."  # noqa: E501
                )
                self.sig_beep.emit()
            else:
                self.updateUi_message_printer("Moving to vertical origin")
            self.updateUi_position_vertical()
        else:
            self.sig_beep.emit()
            self.updateUi_message_printer("Vertical origin out of boundaries")

    def updateUi_move_camera_to_position(self) -> None:
        """Moves the sample to a specified vertical position"""
        if (
            self.ui.doubleSpinBox_cameraSetPosition.value()
            >= self.motors.camera.get_limit_low(self.units)
        ) and (
            self.ui.doubleSpinBox_cameraSetPosition.value()
            <= self.motors.camera.get_limit_high(self.units)
        ):
            try:
                self.motors.camera.move_absolute_position(
                    self.ui.doubleSpinBox_cameraSetPosition.value(), self.units
                )
            except ValueError:
                self.sig_message.emit(
                    "Move rejected — camera would exceed travel limits. Move the stage closer to the travel range and retry."  # noqa: E501
                )
                self.sig_beep.emit()
            else:
                self.updateUi_message_printer("Camera moving to position")
            self.updateUi_position_camera()
        else:
            self.updateUi_message_printer("Out of boundaries")
            self.sig_beep.emit()

    def updateUi_move_camera_to_focus(self) -> None:
        """Moves camera to focus position"""
        if self.focus_selected:
            if self.motors.camera.get_origin(
                self.units
            ) > self.motors.camera.get_limit_high(self.units):
                # self.motors.camera.move_absolute_position(self.motors.camera.get_limit_high(self.units), self.units)  # noqa: E501
                # rather only report out of boundaries
                self.updateUi_message_printer("Focus out of boundaries")
                self.sig_beep.emit()
                self.updateUi_position_camera()
            elif self.motors.camera.get_origin(
                self.units
            ) < self.motors.camera.get_limit_low(self.units):
                # self.motors.camera.move_absolute_position(self.motors.camera.get_limit_low(self.units), self.units)  # noqa: E501
                # rather only report out of boundaries
                self.updateUi_message_printer("Focus out of boundaries")
                self.sig_beep.emit()
                self.updateUi_position_camera()
            else:
                try:
                    self.motors.camera.move_absolute_position(
                        self.motors.camera.get_origin(self.units), self.units
                    )
                except ValueError:
                    self.sig_message.emit(
                        "Move rejected — camera would exceed travel limits. Move the stage closer to the travel range and retry."  # noqa: E501
                    )
                    self.sig_beep.emit()
                else:
                    self.updateUi_message_printer("Moving to focus")
                self.updateUi_position_camera()
        else:
            try:
                self.motors.camera.move_absolute_position(
                    self.motors.camera.get_origin(self.units), self.units
                )
            except ValueError:
                self.sig_message.emit(
                    "Move rejected — camera would exceed travel limits. Move the stage closer to the travel range and retry."  # noqa: E501
                )
                self.sig_beep.emit()
            else:
                self.updateUi_message_printer(
                    "Focus not yet set. Moving camera to default focus"
                )
            self.updateUi_position_camera()

    def updateUi_move_sample_backward(self) -> None:
        """Sample motor backward horizontal motion"""
        if (
            self.motors.horizontal.get_position(self.units)
            - self.ui.doubleSpinBox_sampleHStepSize.value()
            >= self.motors.horizontal.get_limit_low(self.units)
        ):
            try:
                self.motors.horizontal.move_relative_position(
                    -self.ui.doubleSpinBox_sampleHStepSize.value(), self.units
                )
            except ValueError:
                self.sig_message.emit(
                    "Move rejected — horizontal would exceed travel limits. Move the stage closer to the travel range and retry."  # noqa: E501
                )
                self.sig_beep.emit()
            else:
                self.updateUi_message_printer("Sample moving backward")
            self.updateUi_position_horizontal()
        else:
            # self.motors.horizontal.move_absolute_position(self.motors.horizontal.get_limit_low(self.units), self.units)  # noqa: E501
            # rather only report out of boundaries
            self.updateUi_message_printer("Out of boundaries")
            self.sig_beep.emit()
            self.updateUi_position_horizontal()

    def updateUi_move_sample_forward(self) -> None:
        """Sample motor forward horizontal motion"""
        if (
            self.motors.horizontal.get_position(self.units)
            + self.ui.doubleSpinBox_sampleHStepSize.value()
            <= self.motors.horizontal.get_limit_high(self.units)
        ):
            try:
                self.motors.horizontal.move_relative_position(
                    self.ui.doubleSpinBox_sampleHStepSize.value(), self.units
                )
            except ValueError:
                self.sig_message.emit(
                    "Move rejected — horizontal would exceed travel limits. Move the stage closer to the travel range and retry."  # noqa: E501
                )
                self.sig_beep.emit()
            else:
                self.updateUi_message_printer("Sample moving forward")
            self.updateUi_position_horizontal()
        else:
            # self.motors.horizontal.move_absolute_position(self.motors.horizontal.get_limit_high(self.units), self.units)  # noqa: E501
            # rather only report out of boundaries
            self.updateUi_message_printer("Out of boundaries")
            self.sig_beep.emit()
            self.updateUi_position_horizontal()

    def updateUi_move_sample_up(self) -> None:
        """Sample motor upward vertical motion"""
        if (
            self.motors.vertical.get_position(self.units)
            - self.ui.doubleSpinBox_sampleVStepSize.value()
            >= self.motors.vertical.get_limit_low(self.units)
        ):
            try:
                self.motors.vertical.move_relative_position(
                    -self.ui.doubleSpinBox_sampleVStepSize.value(), self.units
                )
            except ValueError:
                self.sig_message.emit(
                    "Move rejected — vertical would exceed travel limits. Move the stage closer to the travel range and retry."  # noqa: E501
                )
                self.sig_beep.emit()
            else:
                self.updateUi_message_printer("Sample stepping up")
            self.updateUi_position_vertical()
        else:
            # self.motors.vertical.move_absolute_position(self.motors.vertical.get_limit_low(self.units), self.units)  # noqa: E501
            # rather only report out of boundaries
            self.updateUi_message_printer("Out of boundaries")
            self.sig_beep.emit()
            self.updateUi_position_vertical()

    def updateUi_move_sample_down(self) -> None:
        """Sample motor downward vertical motion"""
        if (
            self.motors.vertical.get_position(self.units)
            + self.ui.doubleSpinBox_sampleVStepSize.value()
            <= self.motors.vertical.get_limit_high(self.units)
        ):
            try:
                self.motors.vertical.move_relative_position(
                    self.ui.doubleSpinBox_sampleVStepSize.value(), self.units
                )
            except ValueError:
                self.sig_message.emit(
                    "Move rejected — vertical would exceed travel limits. Move the stage closer to the travel range and retry."  # noqa: E501
                )
                self.sig_beep.emit()
            else:
                self.updateUi_message_printer("Sample stepping down")
            self.updateUi_position_vertical()
        else:
            # self.motors.vertical.move_absolute_position(self.motors.vertical.get_limit_high(self.units), self.units)  # noqa: E501
            # rather only report out of boundaries
            self.updateUi_message_printer("Out of boundaries")
            self.sig_beep.emit()
            self.updateUi_position_vertical()

    def updateUi_move_camera_backward(self) -> None:
        """Camera motor backward horizontal motion"""
        if (
            self.motors.camera.get_position(self.units)
            - self.ui.doubleSpinBox_cameraStepSize.value()
            >= self.motors.camera.get_limit_low(self.units)
        ):
            try:
                self.motors.camera.move_relative_position(
                    -self.ui.doubleSpinBox_cameraStepSize.value(), self.units
                )
            except ValueError:
                self.sig_message.emit(
                    "Move rejected — camera would exceed travel limits. Move the stage closer to the travel range and retry."  # noqa: E501
                )
                self.sig_beep.emit()
            else:
                self.updateUi_message_printer("Camera stepping backward")
            self.updateUi_position_camera()
        else:
            # self.motors.camera.move_absolute_position(self.motors.camera.get_limit_low(self.units), self.units)  # noqa: E501
            # In case of a communication glitch with motor, this was bringing the stage back to min position  # noqa: E501
            # rather only report out of boundaries
            self.updateUi_message_printer("Out of boundaries")
            self.sig_beep.emit()
            self.updateUi_position_camera()

    def updateUi_move_camera_forward(self) -> None:
        """Camera motor forward horizontal motion"""
        if (
            self.motors.camera.get_position(self.units)
            + self.ui.doubleSpinBox_cameraStepSize.value()
            <= self.motors.camera.get_limit_high(self.units)
        ):
            try:
                self.motors.camera.move_relative_position(
                    self.ui.doubleSpinBox_cameraStepSize.value(), self.units
                )
            except ValueError:
                self.sig_message.emit(
                    "Move rejected — camera would exceed travel limits. Move the stage closer to the travel range and retry."  # noqa: E501
                )
                self.sig_beep.emit()
            else:
                self.updateUi_message_printer("Camera stepping forward")
            self.updateUi_position_camera()
        else:
            # self.motors.camera.move_absolute_position(self.motors.camera.get_limit_high(self.units), self.units)  # noqa: E501
            # In case of a communication glitch with motor, this was bringing the stage back to max position  # noqa: E501
            # rather only report out of boundaries
            self.updateUi_message_printer("Out of boundaries")
            self.sig_beep.emit()
            self.updateUi_position_camera()

    def updateUi_reset_boundaries(self) -> None:
        """Reset variables for setting sample's horizontal motion range"""
        self.ui.pushButton_calHorizontalStartRangeSelection.setEnabled(False)
        self.ui.pushButton_calHorizontalSetForwardLimit.setEnabled(True)
        self.ui.pushButton_calHorizontalSetBackwardLimit.setEnabled(True)
        self.ui.label_calibrateRange.setText("Move Horizontal Position")
        # Default boundaries
        self.motors.horizontal.set_limit_low(0, self.units)
        self.motors.horizontal.set_limit_high(0, self.units)
        self.updateUi_units()

    def updateUi_set_horizontal_backward_boundary(self) -> None:
        """Set lower limit of sample's horizontal motion"""
        self.motors.horizontal.set_limit_low(
            self.motors.horizontal.get_position(self.units), self.units
        )
        self.updateUi_units()
        self.horizontal_backward_boundary_selected = True
        self.ui.pushButton_calHorizontalSetBackwardLimit.setEnabled(False)
        if self.horizontal_forward_boundary_selected:
            self.ui.pushButton_calHorizontalStartRangeSelection.setEnabled(True)
            self.ui.label_calibrateRange.setText("Press Calibrate Range To Start")

    def updateUi_set_horizontal_forward_boundary(self) -> None:
        """Set upper limit of sample's horizontal motion"""
        self.motors.horizontal.set_limit_high(
            self.motors.horizontal.get_position(self.units), self.units
        )
        self.updateUi_units()
        self.horizontal_forward_boundary_selected = True
        self.ui.pushButton_calHorizontalSetForwardLimit.setEnabled(False)
        if self.horizontal_backward_boundary_selected:
            self.ui.pushButton_calHorizontalStartRangeSelection.setEnabled(True)
            self.ui.label_calibrateRange.setText("Press Calibrate Range To Start")

    def updateUi_set_sample_origin(self) -> None:
        """Modifies the sample origin position"""
        self.motors.horizontal.set_origin(
            self.motors.horizontal.get_position(self.units), self.units
        )
        self.motors.vertical.set_origin(
            self.motors.vertical.get_position(self.units), self.units
        )
        origin_text = f"Sample origin set at ({self.motors.horizontal.get_origin(self.units)}, {self.motors.vertical.get_origin(self.units)}) {self.units}"  # noqa: E501
        self.updateUi_message_printer(origin_text)

    def updateUi_set_camera_focus(self) -> None:
        """Modifies manually the camera focus position"""
        self.focus_selected = True
        self.motors.camera.set_origin(
            self.motors.camera.get_position(self.units), self.units
        )
        focus_text = f"Camera focus manually set at {self.motors.camera.get_origin(self.units)} {self.units}"  # noqa: E501
        self.updateUi_message_printer(focus_text)

    def calculate_camera_focus(self) -> None:
        """Interpolates the camera focus position"""
        # Current sample position
        current_position = self.motors.horizontal.get_position(self.units)
        # Compute corresponding optimal focus position
        focus_regression = self.slope_camera * current_position + self.intercept_camera
        self.motors.camera.set_origin(focus_regression, self.units)
        print("focus_regression:" + str(focus_regression))  # debugging
        self.focus_selected = True
        self.updateUi_message_printer("Focus automatically set")

    def show_camera_interpolation(self) -> None:
        """Shows the camera focus interpolation"""
        x = self.camera_focus_relation[:, 0]
        y = self.camera_focus_relation[:, 1]

        # Calculating linear regression
        xnew = np.linspace(
            self.camera_focus_relation[0, 0], self.camera_focus_relation[-1, 0], 1000
        )  ##1000 points
        self.slope_camera, self.intercept_camera, r_value, p_value, std_err = (
            stats.linregress(x, y)
        )
        print("r_value:" + str(r_value))  # debugging
        print("p_value:" + str(p_value))  # debugging
        print("std_err:" + str(std_err))  # debugging
        yreg = self.slope_camera * xnew + self.intercept_camera

        # Setting colormap
        xstart = self.motors.horizontal.get_limit_low(self.units)
        xend = self.motors.horizontal.get_limit_high(self.units)
        ystart = self.focus_forward_boundary
        yend = self.focus_backward_boundary
        transp = copy.deepcopy(self.donnees)
        for q in range(int(self.number_of_calibration_planes)):
            transp[q, :] = np.flip(transp[q, :])
        transp = np.transpose(transp)

        # Showing interpolation graph
        plt.figure(1)
        plt.title("Camera Focus Regression")
        plt.xlabel(f"Sample Horizontal Position ({self.units})")
        plt.ylabel(f"Camera Position ({self.units})")
        plt.imshow(transp, cmap="gray", extent=[xstart, xend, ystart, yend])  # Colormap
        plt.plot(x, y, "o")  # Raw data
        plt.plot(xnew, yreg)  # Linear regression
        plt.show(
            block=False
        )  # Prevents the plot from blocking the execution of the code...

        # debugging
        n = int(self.number_of_camera_positions)
        x = np.arange(n)
        for g in range(int(self.number_of_calibration_planes)):
            plt.figure(g + 2)
            plt.plot(self.donnees[g, :])
            plt.plot(x, gaussian(x, *self.popt[g]), "ro:", label="fit")
            plt.show(block=False)

    def show_etl_interpolation(self) -> None:
        """Shows the etl focus interpolation"""
        xl = self.etl_l_relation[:, 0]
        yl = self.etl_l_relation[:, 1]
        # Left linear regression
        xlnew = np.linspace(
            self.etl_l_relation[0, 0], self.etl_l_relation[-1, 0], 1000
        )  # 1000 points
        lslope, lintercept, r_value, p_value, std_err = stats.linregress(xl, yl)
        print("r_value:" + str(r_value))  # debugging
        print("p_value:" + str(p_value))  # debugging
        print("std_err:" + str(std_err))  # debugging
        ylnew = lslope * xlnew + lintercept

        xr = self.etl_r_relation[:, 0]
        yr = self.etl_r_relation[:, 1]
        # Right linear regression
        xrnew = np.linspace(
            self.etl_r_relation[0, 0], self.etl_r_relation[-1, 0], 1000
        )  # 1000 points
        rslope, rintercept, r_value, p_value, std_err = stats.linregress(xr, yr)
        print("r_value:" + str(r_value))  # debugging
        print("p_value:" + str(p_value))  # debugging
        print("std_err:" + str(std_err))  # debugging
        yrnew = rslope * xrnew + rintercept

        # Showing interpolation graph
        plt.figure(1)
        plt.title("ETL Focus Regression")
        plt.xlabel("ETL Voltage (V)")
        plt.ylabel("Focal Point Horizontal Position (column)")
        plt.plot(xl, yl, "o", label="Left ETL")  # Raw left data
        plt.plot(xlnew, ylnew)  # Left regression
        plt.plot(xr, yr, "o", label="Right ETL")  # Raw right data
        plt.plot(xrnew, yrnew)  # Right regression
        plt.legend()
        plt.show(
            block=False
        )  # Prevents the plot from blocking the execution of the code...

        # debugging
        for g in range(int(self.number_of_etls_points)):
            plt.figure(g + 2)
            plt.plot(self.xdata[g], self.ydata[g], ".")
            plt.plot(self.xdata[g], func(self.xdata[g], *self.popt[g]), "r-")
            plt.show(block=False)

    def updateUi_galvo_left_amplitude(self) -> None:
        # Propagate Ui changes to hardware instance
        self.siggen.galvo_left_amplitude = (
            self.ui.doubleSpinBox_galvoLeftAmplitude.value()
        )
        # Adjust Min and Max to prevent amplitude + offset being <-10V or > 10V
        self.ui.doubleSpinBox_galvoLeftOffset.setMinimum(
            -10 + self.ui.doubleSpinBox_galvoLeftAmplitude.value()
        )
        self.ui.doubleSpinBox_galvoLeftOffset.setMaximum(
            10 - self.ui.doubleSpinBox_galvoLeftAmplitude.value()
        )
        if self.ui.checkBox_galvoSync.isChecked():
            # Set opposite galvo amplitude and offset
            self.ui.doubleSpinBox_galvoRightAmplitude.setValue(
                self.ui.doubleSpinBox_galvoLeftAmplitude.value()
            )
            self.ui.doubleSpinBox_galvoRightOffset.setValue(
                self.ui.doubleSpinBox_galvoLeftOffset.value()
            )
            # Adjust Min and Max to prevent amplitude + offset being <-10V or > 10V
            self.ui.doubleSpinBox_galvoRightOffset.setMinimum(
                self.ui.doubleSpinBox_galvoLeftOffset.minimum()
            )
            self.ui.doubleSpinBox_galvoRightOffset.setMaximum(
                self.ui.doubleSpinBox_galvoLeftOffset.maximum()
            )
            # Propagate Ui changes to hardware instance
            self.siggen.galvo_right_amplitude = (
                self.ui.doubleSpinBox_galvoRightAmplitude.value()
            )
            self.siggen.galvo_right_offset = (
                self.ui.doubleSpinBox_galvoRightOffset.value()
            )

    def updateUi_galvo_right_amplitude(self) -> None:
        # Propagate Ui changes to hardware instance
        self.siggen.galvo_right_amplitude = (
            self.ui.doubleSpinBox_galvoRightAmplitude.value()
        )
        # Adjust Min and Max to prevent amplitude + offset being <-10V or > 10V
        self.ui.doubleSpinBox_galvoRightOffset.setMinimum(
            -10 + self.ui.doubleSpinBox_galvoRightAmplitude.value()
        )
        self.ui.doubleSpinBox_galvoRightOffset.setMaximum(
            10 - self.ui.doubleSpinBox_galvoRightAmplitude.value()
        )
        if self.ui.checkBox_galvoSync.isChecked():
            # Set opposite galvo amplitude and offset
            self.ui.doubleSpinBox_galvoLeftAmplitude.setValue(
                self.ui.doubleSpinBox_galvoRightAmplitude.value()
            )
            self.ui.doubleSpinBox_galvoLeftOffset.setValue(
                self.ui.doubleSpinBox_galvoRightOffset.value()
            )
            # Adjust Min and Max to prevent amplitude + offset being <-10V or > 10V
            self.ui.doubleSpinBox_galvoLeftOffset.setMinimum(
                self.ui.doubleSpinBox_galvoRightOffset.minimum()
            )
            self.ui.doubleSpinBox_galvoLeftOffset.setMaximum(
                self.ui.doubleSpinBox_galvoRightOffset.maximum()
            )
            # Propagate Ui changes to hardware instance
            self.siggen.galvo_left_amplitude = (
                self.ui.doubleSpinBox_galvoLeftAmplitude.value()
            )
            self.siggen.galvo_left_offset = (
                self.ui.doubleSpinBox_galvoLeftOffset.value()
            )

    def updateUi_galvo_left_offset(self) -> None:
        # Propagate Ui changes to hardware instance
        self.siggen.galvo_left_offset = self.ui.doubleSpinBox_galvoLeftOffset.value()
        if self.ui.checkBox_galvoSync.isChecked():
            # Set opposite galvo amplitude and offset
            self.ui.doubleSpinBox_galvoRightAmplitude.setValue(
                self.ui.doubleSpinBox_galvoLeftAmplitude.value()
            )
            self.ui.doubleSpinBox_galvoRightOffset.setValue(
                self.ui.doubleSpinBox_galvoLeftOffset.value()
            )
            self.ui.doubleSpinBox_galvoRightOffset.setMinimum(
                self.ui.doubleSpinBox_galvoLeftOffset.minimum()
            )
            self.ui.doubleSpinBox_galvoRightOffset.setMaximum(
                self.ui.doubleSpinBox_galvoLeftOffset.maximum()
            )
            # Propagate Ui changes to hardware instance
            self.siggen.galvo_right_amplitude = (
                self.ui.doubleSpinBox_galvoRightAmplitude.value()
            )
            self.siggen.galvo_right_offset = (
                self.ui.doubleSpinBox_galvoRightOffset.value()
            )

    def updateUi_galvo_right_offset(self) -> None:
        # Propagate Ui changes to hardware instance
        self.siggen.galvo_right_offset = self.ui.doubleSpinBox_galvoRightOffset.value()
        if self.ui.checkBox_galvoSync.isChecked():
            # Set opposite galvo amplitude and offset
            self.ui.doubleSpinBox_galvoLeftAmplitude.setValue(
                self.ui.doubleSpinBox_galvoRightAmplitude.value()
            )
            self.ui.doubleSpinBox_galvoLeftOffset.setValue(
                self.ui.doubleSpinBox_galvoRightOffset.value()
            )
            self.ui.doubleSpinBox_galvoLeftOffset.setMinimum(
                self.ui.doubleSpinBox_galvoRightOffset.minimum()
            )
            self.ui.doubleSpinBox_galvoLeftOffset.setMaximum(
                self.ui.doubleSpinBox_galvoRightOffset.maximum()
            )
            # Propagate Ui changes to hardware instance
            self.siggen.galvo_left_amplitude = (
                self.ui.doubleSpinBox_galvoLeftAmplitude.value()
            )
            self.siggen.galvo_left_offset = (
                self.ui.doubleSpinBox_galvoLeftOffset.value()
            )

    def updateUi_galvo_sync(self) -> None:
        if self.ui.checkBox_galvoSync.isChecked():
            # Set left galvo amplitude and offset to right galvo
            self.ui.doubleSpinBox_galvoRightAmplitude.setValue(
                self.ui.doubleSpinBox_galvoLeftAmplitude.value()
            )
            self.ui.doubleSpinBox_galvoRightOffset.setValue(
                self.ui.doubleSpinBox_galvoLeftOffset.value()
            )
            self.ui.doubleSpinBox_galvoRightOffset.setMinimum(
                self.ui.doubleSpinBox_galvoLeftOffset.minimum()
            )
            self.ui.doubleSpinBox_galvoRightOffset.setMaximum(
                self.ui.doubleSpinBox_galvoLeftOffset.maximum()
            )
            # Propagate Ui changes to hardware instance
            self.siggen.galvo_right_amplitude = (
                self.ui.doubleSpinBox_galvoRightAmplitude.value()
            )
            self.siggen.galvo_right_offset = (
                self.ui.doubleSpinBox_galvoRightOffset.value()
            )

    def updateUi_galvo_activate(self) -> None:
        # Propagate Ui changes to hardware instance
        self.siggen.galvo_activated = self.ui.checkBox_galvoActivate.isChecked()

    def updateUi_galvo_invert(self) -> None:
        # Propagate Ui changes to hardware instance
        self.siggen.galvo_inverted = self.ui.checkBox_galvoInvert.isChecked()

    def updateUi_etl_left_amplitude(self) -> None:
        # Propagate Ui changes to hardware instance
        self.siggen.etl_left_amplitude = self.ui.doubleSpinBox_etlLeftAmplitude.value()
        # Adjust Min and Max to prevent amplitude + offset being <-5V or > 5V
        self.ui.doubleSpinBox_etlLeftOffset.setMinimum(
            -5 + self.ui.doubleSpinBox_etlLeftAmplitude.value()
        )
        self.ui.doubleSpinBox_etlLeftOffset.setMaximum(
            5 - self.ui.doubleSpinBox_etlLeftAmplitude.value()
        )
        if self.ui.checkBox_etlSync.isChecked():
            # Set opposite etl amplitude and offset
            self.ui.doubleSpinBox_etlRightAmplitude.setValue(
                self.ui.doubleSpinBox_etlLeftAmplitude.value()
            )
            self.ui.doubleSpinBox_etlRightOffset.setValue(
                self.ui.doubleSpinBox_etlLeftOffset.value()
            )
            # Adjust Min and Max to prevent amplitude + offset being <-5V or > 5V
            self.ui.doubleSpinBox_etlRightOffset.setMinimum(
                self.ui.doubleSpinBox_etlLeftOffset.minimum()
            )
            self.ui.doubleSpinBox_etlRightOffset.setMaximum(
                self.ui.doubleSpinBox_etlLeftOffset.maximum()
            )
            # Propagate Ui changes to hardware instance
            self.siggen.etl_right_amplitude = (
                self.ui.doubleSpinBox_etlRightAmplitude.value()
            )
            self.siggen.etl_right_offset = self.ui.doubleSpinBox_etlRightOffset.value()

    def updateUi_etl_right_amplitude(self) -> None:
        # Propagate Ui changes to hardware instance
        self.siggen.etl_right_amplitude = (
            self.ui.doubleSpinBox_etlRightAmplitude.value()
        )
        # Adjust Min and Max to prevent amplitude + offset being <-5V or > 5V
        self.ui.doubleSpinBox_etlRightOffset.setMinimum(
            -5 + self.ui.doubleSpinBox_etlRightAmplitude.value()
        )
        self.ui.doubleSpinBox_etlRightOffset.setMaximum(
            5 - self.ui.doubleSpinBox_etlRightAmplitude.value()
        )
        if self.ui.checkBox_etlSync.isChecked():
            # Set opposite etl amplitude and offset
            self.ui.doubleSpinBox_etlLeftAmplitude.setValue(
                self.ui.doubleSpinBox_etlRightAmplitude.value()
            )
            self.ui.doubleSpinBox_etlLeftOffset.setValue(
                self.ui.doubleSpinBox_etlRightOffset.value()
            )
            # Adjust Min and Max to prevent amplitude + offset being <-5V or > 5V
            self.ui.doubleSpinBox_etlLeftOffset.setMinimum(
                self.ui.doubleSpinBox_etlRightOffset.minimum()
            )
            self.ui.doubleSpinBox_etlLeftOffset.setMaximum(
                self.ui.doubleSpinBox_etlRightOffset.maximum()
            )
            # Propagate Ui changes to hardware instance
            self.siggen.etl_left_amplitude = (
                self.ui.doubleSpinBox_etlLeftAmplitude.value()
            )
            self.siggen.etl_left_offset = self.ui.doubleSpinBox_etlLeftOffset.value()

    def updateUi_etl_left_offset(self) -> None:
        # Propagate Ui changes to hardware instance
        self.siggen.etl_left_offset = self.ui.doubleSpinBox_etlLeftOffset.value()
        if self.ui.checkBox_etlSync.isChecked():
            self.ui.doubleSpinBox_etlRightAmplitude.setValue(
                self.ui.doubleSpinBox_etlLeftAmplitude.value()
            )
            self.ui.doubleSpinBox_etlRightOffset.setValue(
                self.ui.doubleSpinBox_etlLeftOffset.value()
            )
            self.ui.doubleSpinBox_etlRightOffset.setMinimum(
                self.ui.doubleSpinBox_etlLeftOffset.minimum()
            )
            self.ui.doubleSpinBox_etlRightOffset.setMaximum(
                self.ui.doubleSpinBox_etlLeftOffset.maximum()
            )
            # Propagate Ui changes to hardware instance
            self.siggen.etl_right_amplitude = (
                self.ui.doubleSpinBox_etlRightAmplitude.value()
            )
            self.siggen.etl_right_offset = self.ui.doubleSpinBox_etlRightOffset.value()

    def updateUi_etl_right_offset(self) -> None:
        # Propagate Ui changes to hardware instance
        self.siggen.etl_right_offset = self.ui.doubleSpinBox_etlRightOffset.value()
        if self.ui.checkBox_etlSync.isChecked():
            self.ui.doubleSpinBox_etlLeftAmplitude.setValue(
                self.ui.doubleSpinBox_etlRightAmplitude.value()
            )
            self.ui.doubleSpinBox_etlLeftOffset.setValue(
                self.ui.doubleSpinBox_etlRightOffset.value()
            )
            self.ui.doubleSpinBox_etlLeftOffset.setMinimum(
                self.ui.doubleSpinBox_etlRightOffset.minimum()
            )
            self.ui.doubleSpinBox_etlLeftOffset.setMaximum(
                self.ui.doubleSpinBox_etlRightOffset.maximum()
            )
            # Propagate Ui changes to hardware instance
            self.siggen.etl_left_amplitude = (
                self.ui.doubleSpinBox_etlLeftAmplitude.value()
            )
            self.siggen.etl_left_offset = self.ui.doubleSpinBox_etlLeftOffset.value()

    def updateUi_etl_sync(self) -> None:
        # Propagate Ui changes to hardware instance
        if self.ui.checkBox_etlSync.isChecked():
            self.ui.doubleSpinBox_etlRightAmplitude.setValue(
                self.ui.doubleSpinBox_etlLeftAmplitude.value()
            )
            self.ui.doubleSpinBox_etlRightOffset.setValue(
                self.ui.doubleSpinBox_etlLeftOffset.value()
            )
            self.ui.doubleSpinBox_etlRightOffset.setMinimum(
                self.ui.doubleSpinBox_etlLeftOffset.minimum()
            )
            self.ui.doubleSpinBox_etlRightOffset.setMaximum(
                self.ui.doubleSpinBox_etlLeftOffset.maximum()
            )
            # Propagate Ui changes to hardware instance
            self.siggen.etl_right_amplitude = (
                self.ui.doubleSpinBox_etlRightAmplitude.value()
            )
            self.siggen.etl_right_offset = self.ui.doubleSpinBox_etlRightOffset.value()

    def updateUi_etl_steps(self) -> None:
        # Propagate Ui changes to hardware instance
        self.siggen.etl_steps = int(self.ui.doubleSpinBox_etlSteps.value())

    def updateUi_etl_activate(self) -> None:
        # Propagate Ui changes to hardware instance
        self.siggen.etl_activated = self.ui.checkBox_etlActivate.isChecked()

    #    def updateUi_acq_sample_rate(self):
    #        # Propagate Ui changes to hardware instance
    #        self.siggen.sample_rate = self.ui.doubleSpinBox_acqSampleRate.value()

    def updateUi_camera_shutter_mode(self) -> None:
        # Propagate Ui changes to hardware instance
        self.camera.shutter_mode = self.ui.comboBox_cameraShutterMode.currentText()
        # Update enabled settings
        if self.camera.shutter_mode == "Rolling":
            self.ui.label_doubleSpinBox_cameraExposureTime.setEnabled(True)
            self.ui.doubleSpinBox_cameraExposureTime.setEnabled(True)
            self.ui.label_doubleSpinBox_cameraLineTime.setEnabled(False)
            self.ui.doubleSpinBox_cameraLineTime.setEnabled(False)
            self.ui.label_doubleSpinBox_cameraExposedLines.setEnabled(False)
            self.ui.doubleSpinBox_cameraExposedLines.setEnabled(False)
            self.ui.label_doubleSpinBox_cameraDelayLines.setEnabled(False)
            self.ui.doubleSpinBox_cameraDelayLines.setEnabled(False)
        elif self.camera.shutter_mode == "Lightsheet":
            self.ui.label_doubleSpinBox_cameraExposureTime.setEnabled(False)
            self.ui.doubleSpinBox_cameraExposureTime.setEnabled(False)
            self.ui.label_doubleSpinBox_cameraLineTime.setEnabled(True)
            self.ui.doubleSpinBox_cameraLineTime.setEnabled(True)
            self.ui.label_doubleSpinBox_cameraExposedLines.setEnabled(True)
            self.ui.doubleSpinBox_cameraExposedLines.setEnabled(True)
            self.ui.label_doubleSpinBox_cameraDelayLines.setEnabled(True)
            self.ui.doubleSpinBox_cameraDelayLines.setEnabled(True)
        else:
            self.ui.label_doubleSpinBox_cameraExposureTime.setEnabled(True)
            self.ui.doubleSpinBox_cameraExposureTime.setEnabled(True)
            self.ui.label_doubleSpinBox_cameraLineTime.setEnabled(False)
            self.ui.doubleSpinBox_cameraLineTime.setEnabled(False)
            self.ui.label_doubleSpinBox_cameraExposedLines.setEnabled(False)
            self.ui.doubleSpinBox_cameraExposedLines.setEnabled(False)
            self.ui.label_doubleSpinBox_cameraDelayLines.setEnabled(False)
            self.ui.doubleSpinBox_cameraDelayLines.setEnabled(False)

    def updateUi_camera_exposure_time(self) -> None:
        # Propagate Ui changes to hardware instance
        self.camera.exposure_time = (
            self.ui.doubleSpinBox_cameraExposureTime.value() * 1e-3
        )  # ui(ms) to camera(s)

    def updateUi_camera_line_time(self) -> None:
        # Propagate Ui changes to Camera instance
        self.camera.lightsheet_line_time = (
            self.ui.doubleSpinBox_cameraLineTime.value() * 1e-6
        )  # ui(us) to camera(s)

    def updateUi_camera_exposed_lines(self) -> None:
        # Propagate Ui changes to Camera instance
        self.camera.lightsheet_exposed_lines = int(
            self.ui.doubleSpinBox_cameraExposedLines.value()
        )

    def updateUi_camera_delay_lines(self) -> None:
        # Propagate Ui changes to Camera instance
        self.camera.lightsheet_delay_lines = int(
            self.ui.doubleSpinBox_cameraDelayLines.value()
        )

    def updateUi_laser1_amplitude(self) -> None:
        # Debounce-only slot: restart the 300ms single-shot timer so rapid
        # keystrokes coalesce into a single committed write. The actual
        # (scaled, thread-offloaded) HAL write happens in _apply_laser1_amplitude
        # when the timer fires. No hardware write happens here.
        #
        # Capture the spinbox value into laser1_power_pct NOW (on the GUI
        # thread) rather than only when the debounce timer fires. This keeps
        # the staged percentage current for _toggle_laser1's just-on path,
        # which reads laser1_power_pct — without this, toggling the laser
        # within the 300ms debounce window after a spinbox edit would apply
        # the OLD percentage and the operator would see the wrong power for
        # 300ms until the debounce fires. The debounce timer still governs
        # when the actual DAQ write happens; this only updates the staged
        # value the toggle reads.
        self.laser1_power_pct = self.ui.doubleSpinBox_laserOneAmplitude.value()
        self._laser1_amplitude_timer.start(300)

    def updateUi_laser2_amplitude(self) -> None:
        # Debounce-only slot for laser 2 (iBeam). See updateUi_laser1_amplitude.
        # Capture the staged percentage now for the same reason as laser 1:
        # _toggle_laser2's just-on path reads laser2_power_pct.
        self.laser2_power_pct = self.ui.doubleSpinBox_laserTwoAmplitude.value()
        self._laser2_amplitude_timer.start(300)

    def _apply_laser1_amplitude(self) -> None:
        """Debounce timeout slot (GUI thread): store the staged percentage
        and offload the scaled DAQ write to a worker thread so the GUI event
        loop is never blocked on a DAQ round-trip."""
        pct = self.ui.doubleSpinBox_laserOneAmplitude.value()
        self.laser1_power_pct = pct
        threading.Thread(
            target=self._write_laser1_power, args=(pct,), daemon=True
        ).start()

    def _apply_laser2_amplitude(self) -> None:
        """Debounce timeout slot (GUI thread): store the staged percentage
        and offload the scaled iBeam serial write to a worker thread."""
        pct = self.ui.doubleSpinBox_laserTwoAmplitude.value()
        self.laser2_power_pct = pct
        threading.Thread(
            target=self._write_laser2_power, args=(pct,), daemon=True
        ).start()

    def _write_laser1_power(self, pct: float) -> None:
        """Worker-thread HAL write for laser 1. Scales the staged percentage
        to mW at the HAL boundary (pct/100 * max_power) and calls
        self.lasers[0].set_power(mw). The DAQLaser backend converts mW -> V
        internally and clamps both units (two-layer safety, AGENTS.md §2).

        Cooperative-skip: checks estop_event immediately before the HAL write
        and skips entirely if set — the E-stop has already driven laser 1 off
        with its own synchronous write, and a queued amplitude write must not
        re-energize or mutate its state after that point. The lock lives on
        the ILaser instance (self.lasers[0]._lock), not the controller.
        """
        with self.lasers[0]._lock:
            if self.estop_event.is_set():
                return
            if self.lasers[0].active:
                mw = pct / 100.0 * self.lasers[0].max_power
                # Re-check E-stop immediately before the HAL write — E-stop
                # is intentionally lock-free (it runs on the GUI thread and
                # zeroes the laser via .off() without taking this lock), so
                # it can fire between the top-of-method check and this
                # point. If it did, force mw = 0 so the HAL write cannot
                # re-energize the laser past the kill path.
                if self.estop_event.is_set():
                    mw = 0.0
                self.lasers[0].set_power(mw)
                if self.lasers[0].error:
                    self.sig_message.emit(
                        f"{self.lasers[0].label} write failed — laser "
                        f"reverted to OFF. Check the hardware connection "
                        f"and re-enable the laser. Cause: "
                        f"{self.lasers[0].error_message}"
                    )
                    self.lasers[0].error = 0
                # Refresh-after-action: the status label reflects the
                # post-write state immediately, not just on the 100ms
                # timer tick.
                self._poll_laser_status([0])
                self._refresh_laser_readback(0)

    def _write_laser2_power(self, pct: float) -> None:
        """Worker-thread HAL write for laser 2. Scales the staged percentage
        to mW at the HAL boundary (pct/100 * max_power) and calls
        self.lasers[1].set_power(mw). The IBeamSmartLaser adapter converts
        mW -> µW internally and the inner IBeam.set_power clamps µW as a
        second physical-safety layer.

        Cooperative-skip: checks estop_event immediately before the HAL write
        and skips entirely if set — the E-stop has already driven laser 2 off
        with its own synchronous write. The lock lives on the ILaser instance
        (self.lasers[1]._lock, identity-shared with the inner IBeam._lock).
        """
        with self.lasers[1]._lock:
            if self.estop_event.is_set():
                return
            if self.lasers[1].active:
                mw = pct / 100.0 * self.lasers[1].max_power
                if self.estop_event.is_set():
                    mw = 0.0
                self.lasers[1].set_power(mw)
                if self.lasers[1].error:
                    self.sig_message.emit(
                        f"{self.lasers[1].label} write failed — laser "
                        f"reverted to OFF. Check the COM4 USB cable and the "
                        f"iBeam power, then re-enable. Cause: "
                        f"{self.lasers[1].error_message}"
                    )
                    self.lasers[1].error = 0
                # Refresh-after-action: the iBeam status label reflects
                # the post-write state immediately (the gated ~1s poll
                # would otherwise lag up to a second behind the write).
                self._poll_laser_status([1])
                self._refresh_laser_readback(1)

    def laser1_toggle_button(self) -> None:
        # Slot only spawns a worker thread — the DAQ toggle (and the
        # immediate scaled-power application when turning on) happens off
        # the GUI thread so the event loop is never blocked on a DAQ
        # round-trip.
        threading.Thread(target=self._toggle_laser1, daemon=True).start()

    def _toggle_laser1(self) -> None:
        """Worker-thread toggle for laser 1. Toggles self.lasers[0], and if
        it was just turned on, immediately applies the staged percentage
        (scaled to mW) so the operator sees the chosen power, not 0.
        HAL failures are surfaced via sig_message. The lock lives on the
        ILaser instance (self.lasers[0]._lock)."""
        with self.lasers[0]._lock:
            # E-stop cooperative-skip: if E-stop was pressed while this
            # toggle thread was in flight (waiting on the lock or before it
            # was scheduled), do NOT energize. The E-stop path already drove
            # the laser off synchronously on the GUI thread via .off();
            # a queued toggle that calls .on() would re-energize a Class
            # IIIB laser past the kill path. E-stop must be the final word.
            if self.estop_event.is_set():
                return
            if self.lasers[0].active:
                self.lasers[0].off()
            else:
                self.lasers[0].on()
            # Re-check after the toggle — E-stop may have fired mid-toggle
            # (between .on()/.off() returning and this line). If it did,
            # force the laser back off and do not apply the staged power.
            if self.estop_event.is_set():
                self.lasers[0].off()
                return
            if self.lasers[0].error:
                self.sig_message.emit(
                    f"{self.lasers[0].label} write failed — laser reverted "
                    f"to OFF. Check the hardware connection and re-enable "
                    f"the laser. Cause: {self.lasers[0].error_message}"
                )
                self.lasers[0].error = 0
            elif self.lasers[0].active:
                # Just turned on — apply the staged percentage (scaled).
                # _write_laser1_power re-acquires the same RLock (reentrant)
                # and checks estop_event before the write.
                self._write_laser1_power(self.laser1_power_pct)
            # Refresh-after-action: the status label reflects the
            # post-toggle state immediately (the 100ms timer would
            # otherwise lag up to 100ms behind the toggle).
            self._poll_laser_status([0])
            self._refresh_laser_readback(0)

    def laser2_toggle_button(self) -> None:
        # Slot only spawns a worker thread — the iBeam serial on/off (and
        # the immediate scaled-power application when turning on) happens
        # off the GUI thread so the event loop is never blocked on a
        # serial round-trip.
        threading.Thread(target=self._toggle_laser2, daemon=True).start()

    def _toggle_laser2(self) -> None:
        """Worker-thread toggle for laser 2. Symmetric with _toggle_laser1
        — both operate on self.lasers[i] uniformly. The IBeamSmartLaser
        adapter's .on() mirrors active from the inner _is_on and guards on
        the inner error surface, so the controller no longer needs its own
        iBeam-specific verify-before-mark-active branch. The lock lives on
        the ILaser instance (self.lasers[1]._lock, identity-shared with the
        inner IBeam._lock)."""
        with self.lasers[1]._lock:
            # E-stop cooperative-skip: if E-stop was pressed while this
            # toggle thread was in flight, do NOT energize. The E-stop path
            # already drove the laser off synchronously on the GUI thread
            # via .off(); a queued toggle that calls .on() would re-enable
            # emission of a Class IIIB laser past the kill path.
            if self.estop_event.is_set():
                return
            if self.lasers[1].active:
                self.lasers[1].off()
                if self.lasers[1].error:
                    self.sig_message.emit(
                        f"{self.lasers[1].label} off failed — the laser may "
                        f"STILL BE ON. Manually verify the laser is off "
                        f"before approaching the microscope. Cause: "
                        f"{self.lasers[1].error_message}"
                    )
                    self.lasers[1].error = 0
            else:
                # Re-check before energizing — E-stop may have fired while
                # we were waiting on the lock or inside the off() branch
                # above. Do not call .on() if the kill path has run.
                if self.estop_event.is_set():
                    return
                self.lasers[1].on()
                if self.lasers[1].error:
                    self.sig_message.emit(
                        f"{self.lasers[1].label} on failed — laser stays "
                        f"OFF. Check COM4 and the iBeam power. Cause: "
                        f"{self.lasers[1].error_message}"
                    )
                    self.lasers[1].error = 0
                    self._poll_laser_status([1])
                    return
                # Apply the staged percentage (scaled to mW).
                # _write_laser2_power re-acquires the same RLock (reentrant)
                # and checks estop_event before the write.
                self._write_laser2_power(self.laser2_power_pct)
                if self.lasers[1].error:
                    self.lasers[1].off()
            # Refresh-after-action: the iBeam status label reflects the
            # post-toggle state immediately (the gated ~1s poll would
            # otherwise lag up to a second behind the toggle).
            self._poll_laser_status([1])
            self._refresh_laser_readback(1)

    def start_lasers(self) -> None:
        """Starts the lasers at a certain power. Called from acquisition
        worker threads (not the GUI thread), so no further nested thread is
        needed — only the %-to-absolute scaling at the HAL boundary.

        Drives self.lasers[0] and self.lasers[1] uniformly: stage the
        scaled power via .set_power(mw) BEFORE .on() so the DAQLaser
        backend writes the staged power when it energizes the AO channel,
        and the IBeamSmartLaser adapter stages the channel power before
        enabling global emission.

        The auto-laser flags (self._auto_laser1 / self._auto_laser2) are
        sampled on the GUI thread by _cache_auto_laser_flags() before the
        worker is spawned, so this method reads only cached bools and never
        touches a Qt widget (AGENTS.md §11).
        """
        if self._auto_laser1:
            mw = self.laser1_power_pct / 100.0 * self.lasers[0].max_power
            self.lasers[0].set_power(mw)
            self.lasers[0].on()
            # Surface a HAL write failure to the operator. The backend's
            # .on() catches the write failure, sets .error = 1, mirrors
            # .active = False, and deliberately does NOT raise (hardware-
            # absence tolerance). The caller is responsible for reading the
            # flag — a failed laser start during acquisition was previously
            # a silent no-op (PSU dark, no message).
            if self.lasers[0].error:
                self.sig_message.emit(
                    f"{self.lasers[0].label} on failed — laser reverted to "
                    f"OFF. Check the NI DAQ connection (Dev7) and re-enable "
                    f"the laser. Cause: {self.lasers[0].error_message}"
                )
                self.lasers[0].error = 0
        if self._auto_laser2:
            mw = self.laser2_power_pct / 100.0 * self.lasers[1].max_power
            self.lasers[1].set_power(mw)
            self.lasers[1].on()
            if self.lasers[1].error:
                self.sig_message.emit(
                    f"{self.lasers[1].label} on failed — laser reverted to "
                    f"OFF. Check COM4 and the iBeam power. Cause: "
                    f"{self.lasers[1].error_message}"
                )
                self.lasers[1].error = 0
        # Refresh-after-action: both status labels reflect the post-start
        # state immediately (the periodic timers would otherwise lag).
        self._poll_laser_status([0, 1])
        self._refresh_laser_readback(0)
        self._refresh_laser_readback(1)

    def stop_lasers(self) -> None:
        """Stops the lasers. Called from acquisition worker threads (not the
        GUI thread). Drives self.lasers[0] and self.lasers[1] uniformly via
        .off(). Reads only the cached auto-laser flags sampled on the GUI
        thread by _cache_auto_laser_flags() — never a Qt widget
        (AGENTS.md §11)."""
        if self._auto_laser1:
            self.lasers[0].off()
            if self.lasers[0].error:
                self.sig_message.emit(
                    f"{self.lasers[0].label} off failed — the laser may "
                    f"STILL BE ON. Manually verify before approaching the "
                    f"microscope. Cause: {self.lasers[0].error_message}"
                )
                self.lasers[0].error = 0
        if self._auto_laser2:
            self.lasers[1].off()
            if self.lasers[1].error:
                self.sig_message.emit(
                    f"{self.lasers[1].label} off failed — the laser may "
                    f"STILL BE ON. Manually verify before approaching the "
                    f"microscope. Cause: {self.lasers[1].error_message}"
                )
                self.lasers[1].error = 0
        # Refresh-after-action: both status labels reflect the post-stop
        # state immediately (the periodic timers would otherwise lag).
        self._poll_laser_status([0, 1])
        self._refresh_laser_readback(0)
        self._refresh_laser_readback(1)

    # File Open Methods

    def updateUi_select_file(self) -> None:
        """Allows the selection of a file (.hdf5), opens it and displays its datasets"""

        # Retrieve File
        self.open_directory = QFileDialog.getOpenFileName(
            self, "Choose File", "", "Hierarchical files (*.hdf5)"
        )[0]

        if self.open_directory != "":  # If file directory specified
            self.ui.label_currentFileDirectory.setText(self.open_directory)
            self.ui.listWidget_fileDatasets.clear()

            # Open the file and display its datasets
            with h5py.File(self.open_directory, "r") as f:
                dataset_names = list(f.keys())
                for item in range(len(dataset_names)):
                    self.ui.listWidget_fileDatasets.insertItem(
                        item, dataset_names[item]
                    )
            self.ui.listWidget_fileDatasets.setCurrentRow(0)
            self.updateUi_message_printer("File " + self.open_directory + " opened")
            self.ui.pushButton_selectDataset.setEnabled(True)
        else:
            self.ui.label_currentFileDirectory.setText("None Specified")

    def updateUi_select_dataset(self) -> None:
        """
        Opens one or many HDF5 datasets and displays its attributes and data as an image
        """
        if (self.open_directory != "") and (
            self.ui.listWidget_fileDatasets.count() != 0
        ):
            for item in range(len(self.ui.listWidget_fileDatasets.selectedItems())):
                self.dataset_name = self.ui.listWidget_fileDatasets.selectedItems()[
                    item
                ].text()
                with h5py.File(self.open_directory, "r") as f:
                    dataset = f[self.dataset_name]

                    # Display attributes of the first selected dataset
                    if item == 0:
                        self.ui.label_currentDataset.setText(self.dataset_name)
                        attribute_names = list(dataset.attrs.keys())
                        attribute_values = list(dataset.attrs.values())
                        self.ui.tableWidget_fileAttributes.setColumnCount(2)
                        self.ui.tableWidget_fileAttributes.setRowCount(
                            len(attribute_names)
                        )
                        self.ui.tableWidget_fileAttributes.setHorizontalHeaderItem(
                            0, QTableWidgetItem("Attributes")
                        )
                        self.ui.tableWidget_fileAttributes.setHorizontalHeaderItem(
                            1, QTableWidgetItem("Values")
                        )
                        for attribute in range(0, len(attribute_names)):
                            self.ui.tableWidget_fileAttributes.setItem(
                                attribute,
                                0,
                                QTableWidgetItem(attribute_names[attribute]),
                            )
                            self.ui.tableWidget_fileAttributes.setItem(
                                attribute,
                                1,
                                QTableWidgetItem(str(attribute_values[attribute])),
                            )
                        self.ui.tableWidget_fileAttributes.resizeColumnsToContents()
                        self.ui.tableWidget_fileAttributes.setEditTriggers(
                            QAbstractItemView.NoEditTriggers
                        )  # No editing possible

                    # Display image
                    data = dataset[()]
                    plt.figure(self.open_directory + " (" + self.dataset_name + ")")
                    plt.imshow(data, cmap="gray")
                    plt.show(
                        block=False
                    )  # Prevents the plot from blocking the execution of the code...

                    ##'''Convert to tiff format'''
                    ## tiff = Image.fromarray(data)
                    ##tiff_filename = self.open_directory.replace('.hdf5', '.tiff')
                    ##tiff.save(tiff_filename)

                self.updateUi_message_printer(
                    "Dataset "
                    + self.dataset_name
                    + " of file "
                    + self.open_directory
                    + " displayed"
                )

    def updateUi_preview_mode_button(self) -> None:
        """Start or stop preview mode, depending on the button status"""
        if self.preview_mode_started:
            # Do NOT join the worker thread here — joining blocks the Qt event
            # loop for the remainder of whatever blocking hardware call
            # (camera.monitor_recorder up to its timeout, or a serial
            # round-trip) the worker is currently inside, freezing the GUI.
            # Just clear the flag; the worker polls preview_mode_started at
            # the top of its loop and exits on its own, emitting
            # sig_preview_mode_finished — already connected to
            # updateUi_post_preview_mode — which re-enables the UI from the
            # GUI thread.
            self.preview_mode_started = False
            self.ui.pushButton_acqStartPreviewMode.setText("Start Preview Mode")
        #            self.updateUi_laser_buttons()
        else:
            self.close_modes()
            self.preview_mode_started = True
            self.ui.pushButton_acqStartPreviewMode.setText("Stop Preview Mode")
            #            self.updateUi_laser_buttons(False)

            # updating ui before starting preview mode thread
            self.updateUi_modes_buttons([self.ui.pushButton_acqStartPreviewMode])
            self.updateUi_message_printer("->Preview mode started")
            self.ui.statusBar_label.setText("Current Acquisition Mode: Preview ")
            self.ui.statusBar_progress.setValue(100)
            self.ui.statusBar_progress.show()

            # Starting preview mode thread
            self.preview_mode_thread = threading.Thread(target=self.preview_mode_worker)
            self.preview_mode_thread.start()

    @pyqtSlot()
    def updateUi_post_preview_mode(self) -> None:
        # updating ui after preview mode thread has completed
        self.updateUi_modes_buttons(self.default_buttons)
        self.updateUi_message_printer("->Preview mode stopped")
        self.ui.statusBar_label.setText("")
        self.ui.statusBar_progress.setValue(0)
        self.ui.statusBar_progress.hide()

    def preview_mode_worker(self) -> None:
        """This thread allows the visualization and manual control of the
        parameters of the beams in the UI. There is no scan here,
        beams only changes when parameters are changed. This the preferred
        mode for beam calibration"""
        try:
            # Setting the camera for self triggered acquisition
            self.camera.set_trigger_mode("auto_trigger")
            self.camera.set_exposure_time(
                int(self.ui.doubleSpinBox_cameraExposureTime.value())
            )
            self.camera.arm()

            while self.preview_mode_started:
                # E-stop poll point — checked at the top of each iteration
                # before any frame acquisition work. The lasers are already
                # dark (driven off synchronously on the GUI thread in
                # updateUi_estop_pressed); this break just stops acquiring
                # new frames. Preview mode does not drive lasers or scan
                # generation, but the camera stays armed and grabbing until
                # the operator manually stops — polling estop_event aligns
                # preview_mode_worker with live/single/stack per the
                # AGENTS.md §2 rule that E-stop is polled in all acquisition
                # worker loops.
                if self.estop_event.is_set():
                    break

                # # Updating Galvo and ETL voltages
                # self.siggen.update_all()

                # Recording a single image
                self.camera.start_recorder(1)
                self.camera.monitor_recorder(1)
                self.camera.stop_recorder()
                cam_images = self.camera.copy_recorder_images(1)
                self.camera.delete_recorder()

                # Sending first (and should be only) image to display port
                frame = cam_images[0]
                self.frame_viewer.enqueue_frame(frame)

            # Stopping camera
            self.camera.disarm()
        except Exception as e:
            self.sig_message.emit(
                f"Preview acquisition failed — the run was aborted. Cause: {e}"
            )
            logger.exception("Preview mode worker failed")
        finally:
            # The finished signal must fire exactly once whether the method
            # completes normally or an exception propagates from
            # start_lasers()/acquire_scan()/camera.disarm()/anything else in
            # the body. Without this, a worker that dies mid-cleanup leaves
            # the UI stuck on "Stop Preview Mode" with no slot to re-enable it.
            self.sig_preview_mode_finished.emit()

    def updateUi_live_mode_button(self) -> None:
        """Start or stop live mode, depending on the button status"""
        if self.live_mode_started:
            # Do NOT join the worker thread here — joining blocks the Qt event
            # loop for the remainder of whatever blocking hardware call
            # (camera.monitor_recorder up to its timeout, an iBeam serial
            # round-trip, or a motor move) the worker is currently inside,
            # freezing the GUI. Just clear the flag; the worker polls
            # live_mode_started (and estop_event) at each iteration and exits
            # on its own, emitting sig_live_mode_finished — already connected
            # to updateUi_post_live_mode — which re-enables the UI from the
            # GUI thread.
            self.live_mode_started = False
            self.ui.pushButton_acqStartLiveMode.setText("Start Live Mode")
        #            self.updateUi_laser_buttons()
        else:
            self.close_modes()
            self.live_mode_started = True
            self.ui.pushButton_acqStartLiveMode.setText("Stop Live Mode")
            #            self.updateUi_laser_buttons(False)
            # updating ui before starting live mode thread
            self.updateUi_modes_buttons([self.ui.pushButton_acqStartLiveMode])
            self.updateUi_message_printer("->Live mode started")
            self.ui.statusBar_label.setText("Current Acquisition Mode: Live ")
            self.ui.statusBar_progress.setValue(100)
            self.ui.statusBar_progress.show()

            # Sample the auto-laser checkboxes on the GUI thread before
            # spawning the worker — the worker reads the cached bools in
            # start_lasers()/stop_lasers(), never the widgets (AGENTS.md §11).
            self._cache_auto_laser_flags()

            # Starting live mode thread
            self.live_mode_thread = threading.Thread(target=self.live_mode_worker)
            self.live_mode_thread.start()

    @pyqtSlot()
    def updateUi_post_live_mode(self) -> None:
        # updating ui after live mode thread has completed
        self.updateUi_modes_buttons(self.default_buttons)
        self.updateUi_message_printer("->Live mode stopped")
        self.ui.statusBar_label.setText("")
        self.ui.statusBar_progress.setValue(0)
        self.ui.statusBar_progress.hide()

    def live_mode_worker(self) -> None:
        """This thread allows the execution of scan_mode while modifying
        parameters in the UI"""
        try:
            # Moving the camera to focus
            ##self.move_camera_to_focus()

            #        # Setting the camera for scan acquisition
            #        self.camera.arm_scan()

            # Starting lasers
            self.start_lasers()

            while self.live_mode_started:
                # E-stop poll point — checked at the top of each iteration before
                # any frame acquisition work. The lasers are already dark (driven
                # off synchronously on the GUI thread in updateUi_estop_pressed);
                # this break just stops acquiring new frames.
                if self.estop_event.is_set():
                    break

                # Setting the camera for scan acquisition
                self.camera.arm_scan()

                # Refresh scan waveforms every loop (live mode)
                self.siggen.compute_scan_waveforms()
                # Get single image
                self.acquire_scan()

            # Put ETLs in standby mode: 2.5V corresponds no current through coil (mid 0-5V adjustable range)  # noqa: E501
            self.siggen.update_etls(left_etl=2.5, right_etl=2.5)

            # Stopping lasers
            self.stop_lasers()

            # Stopping camera
            self.camera.disarm()
        except Exception as e:
            self.sig_message.emit(
                f"Live acquisition failed — the run was aborted. Cause: {e}"
            )
            logger.exception("Live mode worker failed")
        finally:
            # The finished signal must fire exactly once whether the method
            # completes normally, breaks out of the loop on E-stop, or an
            # exception propagates from start_lasers()/acquire_scan()/
            # stop_lasers()/camera.disarm()/anything else in the body.
            # Without this, a worker that dies mid-cleanup leaves the UI
            # stuck on "Stop Live Mode" with no slot to re-enable it.
            self.sig_live_mode_finished.emit()

    def updateUi_single_mode_button(self) -> None:
        """Acquire a single image"""
        if not self.single_mode_started:
            self.close_modes()

            self.single_mode_started = True
            # Disabling modes while single frame acquisition
            self.ui.pushButton_acqGetSingleImage.setText("Acquiring...")
            self.updateUi_modes_buttons([self.ui.pushButton_acqGetSingleImage])
            self.updateUi_message_printer("->Getting single image")

            # Sample the auto-laser checkboxes on the GUI thread before
            # spawning the worker — the worker reads the cached bools in
            # start_lasers()/stop_lasers(), never the widgets (AGENTS.md §11).
            self._cache_auto_laser_flags()

            # Starting single image thread
            self.single_mode_thread = threading.Thread(target=self.single_mode_worker)
            self.single_mode_thread.start()

    @pyqtSlot()
    def updateUi_post_single_mode(self) -> None:
        # Re-enabling modes after single frame acquisition
        self.single_mode_started = False
        self.ui.pushButton_acqGetSingleImage.setText("Get Single Image")
        self.default_buttons.append(self.ui.pushButton_saveCurrentImage)
        self.updateUi_modes_buttons(self.default_buttons)

    def single_mode_worker(self) -> None:
        """Generates and display a single scan which can be saved afterwards"""
        try:
            # Moving the camera to focus
            ##self.move_camera_to_focus()

            # Getting positions for the image
            self.image_hor_pos_text = self.current_horizontal_position_text
            self.image_ver_pos_text = self.current_vertical_position_text
            self.image_cam_pos_text = self.current_camera_position_text

            # Setting the camera for scan acquisition
            self.camera.arm_scan()

            # Start lasers
            self.start_lasers()

            # E-stop poll point — checked before acquire_scan so a mid-acquisition
            # E-stop (pressed between mode start and the single frame grab) aborts
            # without acquiring the frame. The lasers are already dark from the
            # synchronous GUI-thread zeroing in updateUi_estop_pressed.
            if self.estop_event.is_set():
                # Put ETLs in standby and stop lasers/camera before exiting so the
                # post-mode cleanup matches the normal single_mode_worker exit.
                self.siggen.update_etls(left_etl=2.5, right_etl=2.5)
                self.stop_lasers()
                self.camera.disarm()
                return

            # Refresh scan waveforms with current settings
            self.siggen.compute_scan_waveforms()

            # Acquire a single scan
            self.acquire_scan()

            # Put ETLs in standby mode
            # 2.5V corresponds no current through coil (mid 0-5V adjustable range)
            self.siggen.update_etls(left_etl=2.5, right_etl=2.5)

            # Stop lasers
            self.stop_lasers()

            # Stop camera
            self.camera.disarm()
        except Exception as e:
            self.sig_message.emit(
                f"Single image acquisition failed — the run was aborted. Cause: {e}"
            )
            logger.exception("Single image mode worker failed")
        finally:
            # The finished signal must fire exactly once whether the method
            # returns early (E-stop), completes normally, or an exception
            # propagates from stop_lasers()/camera.disarm()/anything else.
            # Without this, a worker that dies mid-cleanup leaves the UI
            # stuck on "Acquiring..." with no slot to re-enable it.
            self.sig_single_mode_finished.emit()

    def crop_buffer(self, buffer: np.ndarray) -> np.ndarray:
        """Crops each frame of a buffer with 20% frame-to-frame overlap"""

        image_xsize = buffer.shape[2]
        image_ysize = buffer.shape[1]
        tile_count = buffer.shape[0]

        if tile_count == 1:
            cropped_buffer = buffer
        else:
            tile_width = int(image_xsize / tile_count)
            tile_width_overlap = int(tile_width * 0.2)

            # Initializing empty cropped buffer
            cropped_buffer = np.zeros(
                (tile_count, image_ysize, tile_width + (2 * tile_width_overlap)),
                np.uint16,
            )

            # Crop with overlap
            for frame in range(tile_count):
                # NOTE - disabled intensity normalization
                # # Uniformize frame intensities
                # average = np.average(buffer[frame,0:100,:]) #Average the  first rows
                # if frame == 0:
                #     reference_average = average
                # else:
                #     average_ratio = reference_average/average
                #     # buffer[frame,:,:] = buffer[frame,:,:] * average_ratio

                first_column = int(frame * tile_width - tile_width_overlap)
                next_first_column = int(
                    first_column + tile_width + (2 * tile_width_overlap)
                )
                if frame == 0:  # For the first column step
                    cropped_buffer[frame, :, tile_width_overlap:] = buffer[
                        frame, :, 0 : tile_width + tile_width_overlap
                    ]
                elif (
                    frame == tile_count - 1
                ):  # For the last column step (may be different than the others...)
                    last_column_step = int(image_xsize - first_column)
                    cropped_buffer[frame, :, 0:last_column_step] = buffer[
                        frame, :, first_column:
                    ]
                else:
                    cropped_buffer[frame, :, :] = buffer[
                        frame, :, first_column:next_first_column
                    ]
        return cropped_buffer

    def reconstruct_frame(self, buffer: np.ndarray) -> np.ndarray:
        """Reconstructs frame from buffer"""

        image_xsize = buffer.shape[2]
        image_ysize = buffer.shape[1]
        tile_count = buffer.shape[0]

        # Initializing empty frame
        reconstructed_frame = np.zeros((image_ysize, image_xsize), np.uint16)

        # Crops each frame of a buffer with no overlap and merge
        if tile_count == 1:
            reconstructed_frame = buffer[0, :, :]
        else:
            tile_width = int(image_xsize / tile_count)

            for frame in range(tile_count):
                # NOTE - disabled intensity normalization
                # # Uniformize frame intensities
                # average = np.average(buffer[frame,0:100,:]) #Average the  first rows
                # if frame == 0:
                #     reference_average = average
                # else:
                #     average_ratio = reference_average/average
                #     #print('average_ratio:'+str(average_ratio))
                #     # buffer[frame,:,:] = buffer[frame,:,:] * average_ratio

                # Reconstruct frame
                first_column = frame * tile_width
                next_first_column = first_column + tile_width
                if (
                    frame == tile_count - 1
                ):  # For the last column step (may be different than the others...)
                    reconstructed_frame[:, first_column:] = buffer[
                        frame, :, first_column:
                    ]
                else:
                    reconstructed_frame[:, first_column:next_first_column] = buffer[
                        frame, :, first_column:next_first_column
                    ]
        return reconstructed_frame

    def reconstruct_frame_linear_blend(self, buffer: np.ndarray) -> np.ndarray:
        """Reconstructs frame from buffer using linear blend over 20% overlap"""

        image_xsize = buffer.shape[2]
        image_ysize = buffer.shape[1]
        tile_count = buffer.shape[0]

        # Initializing empty output frame
        reconstructed_frame = np.zeros((image_ysize, image_xsize), np.uint16)

        if tile_count == 1:
            reconstructed_frame = buffer[0, :, :]
        else:
            # Crops each frame of a buffer with 20% overlap for futher frame reconstruction  # noqa: E501
            tile_width = int(image_xsize / tile_count)
            tile_width_overlap = int(tile_width * 0.2)

            # Initializing empty cropped buffer
            cropped_buffer = np.zeros(
                (tile_count, image_ysize, tile_width + (2 * tile_width_overlap)),
                np.uint16,
            )

            # Crop with overlap
            for frame in range(tile_count):
                first_column = int(frame * tile_width - tile_width_overlap)
                next_first_column = int(
                    first_column + tile_width + (2 * tile_width_overlap)
                )
                if frame == 0:  # For the first column step
                    cropped_buffer[frame, :, tile_width_overlap:] = buffer[
                        frame, :, 0 : tile_width + tile_width_overlap
                    ]
                elif (
                    frame == tile_count - 1
                ):  # For the last column step (may be different than the others...)
                    last_column_step = int(image_xsize - first_column)
                    cropped_buffer[frame, :, 0:last_column_step] = buffer[
                        frame, :, first_column:
                    ]
                else:
                    cropped_buffer[frame, :, :] = buffer[
                        frame, :, first_column:next_first_column
                    ]

            # Reconstruct frame with linear blend for overlapping region
            weight_step = 1 / (2 * tile_width_overlap)

            for frame in range(tile_count):
                first_center_column = int(frame * tile_width + tile_width_overlap)
                last_center_column = int((frame + 1) * tile_width - tile_width_overlap)
                previous_last_center_column = int(
                    frame * tile_width - tile_width_overlap
                )

                if frame == 0:  # For the first column step
                    reconstructed_frame[:, 0:last_center_column] = cropped_buffer[
                        frame, :, tile_width_overlap:tile_width
                    ]
                else:
                    for column in range(2 * tile_width_overlap):
                        frame_column = column + previous_last_center_column
                        last_buffer_column = column + tile_width
                        buffer_weight = column * weight_step
                        last_buffer_weight = 1 - column * weight_step
                        reconstructed_frame[:, frame_column] = (
                            buffer_weight * cropped_buffer[frame, :, column]
                            + last_buffer_weight
                            * cropped_buffer[(frame - 1), :, last_buffer_column]
                        )
                    if (
                        frame == tile_count - 1
                    ):  # For the last column step (may be different than the others...)
                        last_column_step = int(image_xsize - first_center_column)
                        reconstructed_frame[:, first_center_column:] = cropped_buffer[
                            frame,
                            :,
                            (2 * tile_width_overlap) : (2 * tile_width_overlap)
                            + last_column_step,
                        ]
                    else:
                        reconstructed_frame[
                            :, first_center_column:last_center_column
                        ] = cropped_buffer[
                            frame, :, (2 * tile_width_overlap) : tile_width
                        ]
        return reconstructed_frame

    def acquire_scan(self) -> None:
        """
        Generate scan tasks using previously computed waveforms and
        acquire a single reconstructed frame
        """

        # TODO - thread lock siggen and camera while we acquire

        # Store metadata about buffer to be acquired
        self.buffer_metadata_general = {}
        self.buffer_metadata_general["Date"] = str(datetime.date.today())
        self.buffer_metadata_general["Sample Name"] = str(
            self.ui.lineEdit_saveDescription.text()
        )

        self.buffer_metadata_waveforms = {}
        self.buffer_metadata_waveforms = self.siggen.waveform_metadata

        # TODO - motors and lasers and camera (?) metadata
        self.buffer_metadata_motors = {}
        self.buffer_metadata_lasers = {}
        self.buffer_metadata_camera = {}

        # self.buffer_metadata['Horizontal Position']  = self.motors.horizontal.get_position('mm')  # noqa: E501
        # self.buffer_metadata['Vertical Position']  = self.motors.vertical.get_position('mm')  # noqa: E501
        # self.buffer_metadata['Camera Position']  = self.motors.camera.get_position('mm')  # noqa: E501

        # Number of images to be acquired from the camera
        number_of_images = self.siggen.waveform_cycles

        # Creating acquisition tasks
        # Clear any error left over from a previous acquisition so the check
        # below reflects this create_scanner() call only.
        self.siggen.error = 0
        self.siggen.create_scanner()
        # create_scanner() wraps its DAQ task creation in a bare except that
        # sets self.siggen.error = 1 + a generic 'create_scan error' message
        # but never raises. Without this check a failed create_scanner()
        # leaves task_galvo_etl / task_camera as None, start_scanner() /
        # monitor_scanner() become no-ops, and the camera waits out its full
        # recorder timeout with nothing to report — a silent 15 s timeout
        # that is impossible to diagnose. Surface it here, before the
        # recorder is primed, so the operator sees the real DAQ fault
        # instead of a camera timeout. The recorder is never primed on this
        # path, so there is no recorder to delete; the scanner task objects
        # are None so delete_scanner() is a safe no-op, and disarm() returns
        # the camera to a consistent state. Do NOT clear self.siggen.error
        # here — the stack worker inspects it to decide whether to abort the
        # remaining planes, and the reset above clears it at the start of
        # the next acquisition.
        if self.siggen.error:
            self.sig_message.emit(
                f"Scan task creation failed — the acquisition was aborted before the camera was triggered. Check the NI DAQ connection (Dev1). Cause: {self.siggen.error_message}"  # noqa: E501
            )
            logger.warning("SigGen create_scanner failed during acquire_scan")
            self.siggen.delete_scanner()
            self.camera.disarm()
            return

        # Prime the camera recorder before we start the acquisition taks
        self.camera.start_recorder(number_of_images)
        self.siggen.start_scanner()

        # Monitor completion of acquisition tasks and camera recorder
        self.camera.monitor_recorder(number_of_images)
        self.siggen.monitor_scanner()

        # Stop tasks and recorder
        self.camera.stop_recorder()
        self.siggen.stop_scanner()

        # Abort on recorder timeout — never copy zero-filled frames to disk.
        # The recorder timeout flag is set by monitor_recorder when the camera
        # did not return the expected frames in time. Returning here before
        # copy_recorder_images ensures a timed-out plane is not mistaken for
        # a real (dark) frame on disk.
        if self.camera.recorder_timeout_status:
            self.sig_message.emit(
                "Camera timeout — plane was not recorded (camera did not return frames in time). "  # noqa: E501
                "The acquisition was aborted. Reduce the number of images per plane or check the camera USB connection, then restart the run."  # noqa: E501
            )
            logger.warning("Camera recorder timeout during acquire_scan")
            self.camera.delete_recorder()
            # Delete the DAQ scanner task. The scanner was already stopped
            # above (before the timeout check) — NI-DAQmx Task.stop() is
            # idempotent, so a second stop_scanner() here was redundant and
            # is omitted. delete_scanner() tears down the task so the DAQ
            # hardware is left in a consistent state.
            self.siggen.delete_scanner()
            # Disarm the camera before returning. Camera.disarm() is
            # idempotent (it only issues the SDK stop-recording call when
            # the camera reports recording state == 'on'), so calling it
            # here and again from a caller that reaches its own disarm()
            # is safe. This ensures a camera left mid-timeout is always
            # disarmed before any worker that might die afterward gets a
            # chance to skip its own cleanup.
            self.camera.disarm()
            return

        # Recover images from the recorder
        # Note: Images must be recovered before deleting the recorder
        recorded_images = self.camera.copy_recorder_images(number_of_images)
        self.buffer = np.asarray(recorded_images)

        # Delete tasks and recorder
        self.camera.delete_recorder()
        self.siggen.delete_scanner()

        # Frame reconstruction options
        if self.ui.checkBox_saveStitchBlend.isChecked():
            self.reconstructed_frame = self.reconstruct_frame_linear_blend(self.buffer)
        else:
            self.reconstructed_frame = self.reconstruct_frame(self.buffer)

        # Send reconstructed frame to display port
        self.frame_viewer.enqueue_frame(self.reconstructed_frame)

    def updateUi_select_directory(self) -> None:
        """Allows the selection of a directory for single scan or stack saving"""
        options = QFileDialog.Options()
        options |= QFileDialog.DontResolveSymlinks
        options |= QFileDialog.ShowDirsOnly
        tmp_directory = QFileDialog.getExistingDirectory(
            self, "Choose Directory", self.save_directory, options
        )
        if tmp_directory != "":
            self.save_directory = os.path.normpath(tmp_directory)

        if self.save_directory != "":
            self.ui.lineEdit_saveDirectory.setText(self.save_directory)
            self.ui.lineEdit_saveFilename.setText("")
            self.ui.lineEdit_saveFilename.setEnabled(True)
            self.ui.lineEdit_saveDescription.setText("")
            self.ui.lineEdit_saveDescription.setEnabled(True)
        else:
            self.ui.lineEdit_saveDirectory.setText("")
            self.ui.lineEdit_saveFilename.setText(
                "Filename - Select Save Directory First"
            )
            self.ui.lineEdit_saveFilename.setEnabled(False)
            self.ui.lineEdit_saveDescription.setText(
                "Description - Select Save Directory First"
            )
            self.ui.lineEdit_saveDescription.setEnabled(False)

    def validate_file_name(self) -> None:
        """
        Validate filename set by the user
        """

        # To validate individual char. Only alphanumeric, - and _ characters are permitted  # noqa: E501
        def safe_char(c: str) -> str:
            if c.isalnum() or c == "-":
                return c
            else:
                return "_"

        # TODO
        # Check that save path exists

        tmp_string = self.ui.lineEdit_saveFilename.text()
        tmp_string = "".join(safe_char(c) for c in tmp_string).rstrip("_")

        if tmp_string != "":
            self.save_filename = tmp_string

        if (self.save_directory != "") and (self.save_filename != ""):
            self.save_filename = os.path.normpath(
                self.save_directory + "\\" + self.save_filename
            )
            self.saving_allowed = True
        else:
            self.saving_allowed = False

    def updateUi_save_single_image(self) -> None:
        """Saves the frame generated by self.get_single_image()"""

        # Check that filename is valid and saving is allowed
        self.validate_file_name()

        if self.saving_allowed:
            # Getting sample name
            self.save_description = str(self.ui.lineEdit_saveDescription.text())

            """Setting up frame saver"""
            self.frame_saver.reinit(1)
            self.frame_saver.add_sample_name(self.save_description)
            self.frame_saver.add_motor_parameters(
                self.image_hor_pos_text,
                self.image_ver_pos_text,
                self.image_cam_pos_text,
            )

            """Saving frame"""
            if self.ui.checkBox_saveAllCrop.isChecked():
                self.frame_saver.set_files(
                    1, self.save_filename, "singleImage", 1, "ETLscan"
                )
                cropped_buffer = self.crop_buffer(self.buffer)
                self.frame_saver.enqueue_buffer(cropped_buffer)
                self.updateUi_message_printer(
                    "Saving Images (one for each ETL scan, cropped)"
                )
            elif self.ui.checkBox_saveAllFull.isChecked():
                self.frame_saver.set_files(
                    1, self.save_filename, "singleImage", 1, "FullETLscan"
                )
                self.frame_saver.enqueue_buffer(self.buffer)
                self.updateUi_message_printer(
                    "Saving Images (one for each ETL scan, full)"
                )
            else:
                self.frame_saver.set_files(
                    1, self.save_filename, "singleImage", 1, "reconstructed_frame"
                )
                self.frame_saver.enqueue_buffer(self.reconstructed_frame)
                self.updateUi_message_printer("Saving Reconstructed Image")

            self.frame_saver.start_saving()
            self.frame_saver.stop_saving()
        else:
            self.sig_beep.emit()
            QMessageBox.warning(
                self,
                "Save Warning",
                "Select a directory and enter a valid filename before saving",
                QMessageBox.Ok,
                QMessageBox.Ok,
            )
            self.sig_message.emit(
                "Select a directory and enter a valid filename before saving"
            )

    def updateUi_set_stack_mode_starting_point(self) -> None:
        """Defines the starting point where the first plane of the stack volume will be recorded"""  # noqa: E501
        self.stack_starting_plane = self.motors.horizontal.get_position(
            "\u03bcm"
        )  # Units in micro-meters, because plane step is in micro-meters
        self.ui.checkBox_acqFirstPlaneSet.setChecked(True)
        self.updateUi_set_number_of_planes()

    def updateUi_set_stack_mode_ending_point(self) -> None:
        """Defines the ending point of the recorded stack volume"""
        self.stack_ending_plane = self.motors.horizontal.get_position(
            "\u03bcm"
        )  # Units in micro-meters, because plane step is in micro-meters
        self.ui.checkBox_acqLastPlaneSet.setChecked(True)
        self.updateUi_set_number_of_planes()

    def updateUi_set_number_of_planes(self) -> None:
        """Calculates the number of planes that will be saved in the stack acquisition"""  # noqa: E501
        if self.ui.doubleSpinBox_acqPlaneStepSize.value() != 0:
            if (
                self.ui.checkBox_acqFirstPlaneSet.isChecked()
                and self.ui.checkBox_acqLastPlaneSet.isChecked()
            ):
                self.number_of_planes = np.ceil(
                    abs(
                        (self.stack_ending_plane - self.stack_starting_plane)
                        / self.ui.doubleSpinBox_acqPlaneStepSize.value()
                    )
                )
                self.number_of_planes += 1  # Takes into account the initial plane
                self.ui.label_acqNumberOfPlanes.setText(str(self.number_of_planes))
        else:
            self.sig_message.emit("Set a non-zero value to plane step")

    def updateUi_stack_mode_button(self) -> None:
        """Start or stop stack mode, depending on the button status"""
        if self.stack_mode_started:
            # Do NOT join the worker thread here — joining blocks the Qt event
            # loop for the remainder of whatever blocking hardware call
            # (camera.monitor_recorder up to its timeout, an iBeam serial
            # round-trip, or a motor move) the worker is currently inside,
            # freezing the GUI. Just clear the flag; the worker polls
            # stack_mode_started (and estop_event) at each plane boundary and
            # at the new pre-move/pre-acquire guards, exits on its own next
            # poll, and emits sig_stack_mode_finished — already connected to
            # updateUi_post_stack_mode — which re-enables the UI from the GUI
            # thread.
            self.stack_mode_started = False
        else:
            self.close_modes()
            # Making sure the limits of the volume are set
            if (
                (not self.ui.checkBox_acqFirstPlaneSet.isChecked())
                or (not self.ui.checkBox_acqLastPlaneSet.isChecked())
                or (self.ui.doubleSpinBox_acqPlaneStepSize.value() == 0)
            ):
                self.sig_message.emit(
                    "Set starting and ending points and select a non-zero plane step value"  # noqa: E501
                )
                self.sig_beep.emit()
                QMessageBox.warning(
                    self,
                    "Stack Acquisition Warning",
                    "Set starting and ending points and select a non-zero plane step value",  # noqa: E501
                    QMessageBox.Ok,
                    QMessageBox.Ok,
                )
            else:
                # Setting stack step size sign (taking into account the direction of acquisition)  # noqa: E501
                if self.stack_starting_plane > self.stack_ending_plane:
                    self.stack_step = (
                        -1 * self.ui.doubleSpinBox_acqPlaneStepSize.value()
                    )
                else:
                    self.stack_step = self.ui.doubleSpinBox_acqPlaneStepSize.value()

                # Check that filename is valid and saving is allowed
                self.validate_file_name()

                if not self.saving_allowed:
                    self.sig_beep.emit()
                    nosave_answer = QMessageBox.question(
                        self,
                        "Stack Acquisition Question",
                        "Make stack acquisition without saving ?",
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.Yes,
                    )

                if self.saving_allowed or nosave_answer:
                    self.ui.pushButton_acqStartStackMode.setText("Stop Stack Mode")
                    self.ui.statusBar_label.setText("Current Acquisition Mode: Stack ")
                    self.ui.statusBar_progress.setValue(0)  # To reset progress bar
                    self.ui.statusBar_progress.show()
                    self.stack_mode_started = True

                    # Modes disabling while stack acquisition
                    self.updateUi_modes_buttons([self.ui.pushButton_acqStartStackMode])
                    self.updateUi_motor_buttons()
                    self.updateUi_message_printer(
                        "->Stack mode started -- Number of frames to save: "
                        + str(int(self.number_of_planes))
                    )

                    # Sample the auto-laser checkboxes on the GUI thread
                    # before spawning the worker — the worker reads the
                    # cached bools in start_lasers()/stop_lasers(), never
                    # the widgets (AGENTS.md §11).
                    self._cache_auto_laser_flags()

                    # Starting stack mode thread
                    self.stack_mode_thread = threading.Thread(
                        target=self.stack_mode_worker
                    )
                    self.stack_mode_thread.start()

    @pyqtSlot()
    def updateUi_post_stack_mode(self) -> None:
        """Enabling modes after stack mode"""
        self.ui.pushButton_acqStartStackMode.setText("Start Stack Mode")
        self.updateUi_modes_buttons(self.default_buttons)
        self.updateUi_motor_buttons(disable_button=False)

        self.stack_mode_started = False
        self.updateUi_message_printer("->Stack Mode Acquisition Done")
        self.ui.statusBar_label.setText("")
        self.ui.statusBar_progress.hide()

    def stack_mode_worker(self) -> None:
        """Thread for volume acquisition and saving"""
        try:
            # Making sure saving is allowed and filename isn't empty
            if self.saving_allowed:
                # Getting sample name
                self.save_description = str(self.ui.lineEdit_saveDescription.text())

                # Setting frame saver
                self.frame_saver.reinit(3)
                self.frame_saver.add_sample_name(self.save_description)
                if self.ui.checkBox_saveAllCrop.isChecked():
                    self.frame_saver.set_files(
                        self.number_of_planes, self.save_filename, "stack", 1, "ETLscan"
                    )
                elif self.ui.checkBox_saveAllFull.isChecked():
                    self.frame_saver.set_files(
                        self.number_of_planes,
                        self.save_filename,
                        "stack",
                        1,
                        "FullETLscan",
                    )
                else:
                    self.frame_saver.set_files(
                        1,
                        self.save_filename,
                        "stack",
                        self.number_of_planes,
                        "reconstructed_frame",
                    )
                # Starting frame saver
                self.frame_saver.start_saving()

            # Setting the camera for scan acquisition
            self.camera.arm_scan()

            # Pre-stop guard: a Stop or E-stop pressed in the instant between
            # thread start and this line skips energizing the lasers entirely.
            # The per-plane loop's first-iteration poll then breaks immediately
            # and the end-of-method cleanup (stop_lasers/disarm/emit) runs
            # unchanged, so no lasers are left on and the UI re-enables.
            if self.stack_mode_started and not self.estop_event.is_set():
                self.start_lasers()

            # Set progress bar
            progress_value = 0
            progress_increment = 100 / self.number_of_planes
            self.sig_progress_update.emit(0)  # To reset progress bar

            # Compute scan waveforms only once before we start the stack acquisition
            # Changes to settings won't be effective until we stop/restart mode
            self.siggen.compute_scan_waveforms()

            for plane in range(int(self.number_of_planes)):
                if not self.stack_mode_started:
                    self.sig_message.emit("Stack Acquisition Interrupted")
                    break
                elif self.estop_event.is_set():
                    # E-stop poll point — checked alongside the stack_mode_started
                    # flag at each plane boundary. The lasers are already dark
                    # (driven off synchronously on the GUI thread); this break
                    # stops acquiring new planes.
                    self.sig_message.emit("Stack Acquisition Interrupted")
                    break
                else:
                    # Pre-move guard: a Stop or E-stop requested while the worker
                    # was between blocking calls (after the loop-top poll but
                    # before this motor move) must not start a new blocking call.
                    if not self.stack_mode_started or self.estop_event.is_set():
                        break

                    # Moving sample position
                    position = self.stack_starting_plane + (plane * self.stack_step)
                    try:
                        self.motors.horizontal.move_absolute_position(
                            position, "\u03bcm"
                        )  # Position in micro-meters
                    except ValueError:
                        self.sig_message.emit(
                            "Move rejected — horizontal would exceed travel limits. Stack acquisition aborted."  # noqa: E501
                        )
                        self.sig_beep.emit()
                        break
                    # FIXME - updating ui within secondary thread
                    self.updateUi_position_horizontal()

                    # Moving the camera to focus
                    # FIXME - Add focus adjustement to stack mode
                    # self.calculate_camera_focus()
                    # self.move_camera_to_focus()

                    if self.saving_allowed:
                        self.frame_saver.add_motor_parameters(
                            self.current_horizontal_position_text,
                            self.current_vertical_position_text,
                            self.current_camera_position_text,
                        )

                    # Pre-acquire guard: a Stop or E-stop requested while the worker
                    # was between the motor move and this acquisition must not start
                    # the (potentially long, up to recorder-timeout) camera grab.
                    if not self.stack_mode_started or self.estop_event.is_set():
                        break

                    # Getting image
                    self.acquire_scan()

                    # Abort the stack if the camera timed out on this plane —
                    # acquire_scan already emitted the timeout warning and cleaned
                    # up the recorder/scanner; do not enqueue a (nonexistent)
                    # frame for this plane or attempt the next one.
                    if self.camera.recorder_timeout_status:
                        break

                    # A DAQ scan-task failure would recur on every remaining
                    # plane — abort the stack instead of emitting the same
                    # message N times. acquire_scan already emitted the
                    # operator message and cleaned up the scanner/camera for
                    # this plane; the post-loop stop_lasers/disarm cleanup
                    # runs unchanged.
                    if self.siggen.error:
                        break

                    # Saving frame
                    if self.saving_allowed:
                        if self.ui.checkBox_saveAllCrop.isChecked():
                            cropped_buffer = self.crop_buffer(self.buffer)
                            self.frame_saver.enqueue_buffer(cropped_buffer)
                            self.sig_message.emit(
                                "Saving All Images (one for each ETL step, cropped)"
                            )
                        elif self.ui.checkBox_saveAllFull.isChecked():
                            self.frame_saver.enqueue_buffer(self.buffer)
                            self.sig_message.emit(
                                "Saving All Images (one for each ETL step, full)"
                            )
                        else:
                            self.frame_saver.enqueue_buffer(self.reconstructed_frame)
                            self.sig_message.emit("Saving Reconstructed Image")

                    # Update progress bar
                    progress_value += progress_increment
                    self.sig_progress_update.emit(int(progress_value))

            if self.stack_mode_started:
                self.sig_progress_update.emit(
                    100
                )  # In case the number of planes is not a multiple of 100

            if self.saving_allowed:
                self.frame_saver.stop_saving()

            # Put ETLs in standby mode: 2.5V corresponds no current through coil (mid 0-5V adjustable range)  # noqa: E501
            self.siggen.update_etls(left_etl=2.5, right_etl=2.5)

            # Stopping laser
            self.stop_lasers()

            # Stopping camera
            self.camera.disarm()
        except Exception as e:
            self.sig_message.emit(
                f"Stack acquisition failed — the run was aborted. Cause: {e}"
            )
            logger.exception("Stack mode worker failed")
        finally:
            # The finished signal must fire exactly once whether the method
            # completes normally, breaks out of the per-plane loop, or an
            # exception propagates from stop_lasers()/camera.disarm()/
            # anything else in the body. Without this, a worker that dies
            # mid-cleanup leaves the UI stuck on "Stop Stack Mode" with no
            # slot to re-enable it.
            self.sig_stack_mode_finished.emit()

    # Calibration Methods

    def camera_calibration_button(self) -> None:
        """Start or stop camera calibration, depending on the button status"""
        if self.camera_calibration_started:
            self.camera_calibration_started = False
            self.calibrate_camera_thread.join()
        else:
            self.close_modes()
            self.camera_calibration_started = True
            self.ui.pushButton_calCameraStartCalibration.setText(
                "Stop Camera Calibration"
            )
            self.updateUi_motor_buttons()
            self.start_calibrate_camera()

    def start_calibrate_camera(self) -> None:
        """Initiates camera calibration"""

        # Modes disabling while stack acquisition
        self.updateUi_modes_buttons([self.ui.pushButton_calCameraStartCalibration])

        self.updateUi_message_printer("Camera calibration started")
        self.ui.statusBar_label.setText("Current Mode: Camera Calibration ")
        self.ui.statusBar_progress.show()

        # Starting camera calibration thread
        self.calibrate_camera_thread = threading.Thread(
            target=self.calibrate_camera_worker
        )
        self.calibrate_camera_thread.start()

    def calibrate_camera_worker(self) -> None:
        """Camera calibration worker.

        The calibration workflow that this worker used to drive was never
        rebuilt after an earlier refactor and had become dead code (it
        printed a placeholder message and returned before any of the
        unreachable calibration logic). The body is now a no-op. The start
        button is hidden in __init__; the slot method and its signal
        connection are retained so a scoped rebuild can restore the
        workflow from git history.
        """
        return None

    def etls_calibration_button(self) -> None:
        """Start or stop etls calibration, depending on the button status"""
        if self.etls_calibration_started:
            self.etls_calibration_started = False
            self.calibrate_etls_thread.join()
        else:
            self.close_modes()
            self.etls_calibration_started = True
            self.ui.pushButton_calEtlStartCalibration.setText("Stop ETL Calibration")
            self.updateUi_motor_buttons()
            self.start_calibrate_etls()

    def start_calibrate_etls(self) -> None:
        """Initiates etls-galvos calibration"""

        # Modes disabling while stack acquisition
        self.updateUi_modes_buttons([self.ui.pushButton_calEtlStartCalibration])
        self.updateUi_message_printer("ETL calibration started")

        # Starting camera calibration thread
        self.calibrate_etls_thread = threading.Thread(target=self.calibrate_etls_worker)
        self.calibrate_etls_thread.start()

    def calibrate_etls_worker(self) -> None:
        """ETL/galvo calibration worker.

        The calibration workflow that this worker used to drive was never
        rebuilt after an earlier refactor and had become dead code (it
        printed a placeholder message and returned before any of the
        unreachable calibration logic). The body is now a no-op. The start
        button is hidden in __init__; the slot method and its signal
        connection are retained so a scoped rebuild can restore the
        workflow from git history.
        """
        return None


class Properties_Dialog(QDialog):
    """Class for Properties Dialog"""

    sig_status_message = pyqtSignal(str)

    def __init__(self, parent: Controller_MainWindow) -> None:
        QDialog.__init__(self, parent)
        self.parent = parent
        self.camera = self.parent.camera
        self.motors = self.parent.motors

        self.ui = Ui_Properties()
        self.ui.setupUi(self)
        self.ui.pushButton_refresh.clicked.connect(self.refresh_properties)
        self.sig_status_message.connect(self.parent.updateUi_message_printer)

        self.get_properties()

    def get_properties(self) -> None:
        # Read properties from the camera
        camera_properties = {}
        camera_properties = self.camera.get_properties()
        self.ui.label_cameraName.setText(f"{camera_properties.get('camera name', '-')}")
        self.ui.label_imageSize.setText(
            f"{camera_properties.get('x', '0')} X {camera_properties.get('y', '0')}"
        )
        self.ui.label_cameraTemperature.setText(
            f"{camera_properties.get('camera temperature', 0):.1f} \u2103"
        )
        self.ui.label_sensorTemperature.setText(
            f"{camera_properties.get('sensor temperature', 0):.1f} \u2103"
        )
        self.ui.label_powerTemperature.setText(
            f"{camera_properties.get('power temperature', 0):.1f} \u2103"
        )
        self.ui.label_triggerMode.setText(
            f"{camera_properties.get('trigger mode', '-')}"
        )
        self.ui.label_delayTime.setText(
            f"{camera_properties.get('delay', '-')}  {camera_properties.get('delay timebase', 'ms')}"  # noqa: E501
        )
        self.ui.label_exposureTime.setText(
            f"{camera_properties.get('exposure', '-')}  {camera_properties.get('exposure timebase', 'ms')}"  # noqa: E501
        )
        self.ui.label_acquireMode.setText(
            f"{camera_properties.get('acquire mode', '-')}"
        )
        self.ui.label_storageMode.setText(
            f"{camera_properties.get('storage mode', '-')}"
        )
        if camera_properties.get("storage mode", "-") == "Recorder":
            self.ui.label_recorderMode.setText(
                f"{camera_properties.get('recorder submode', '-')}"
            )
        else:
            self.ui.label_recorderMode.setText("-")

        # Read properties from the motors
        motors_properties = {}
        motors_properties = self.motors.get_properties()
        self.ui.label_horizontalMotorName.setText(
            f"{motors_properties.get('horizontal name', '-')}"
        )
        self.ui.label_verticalMotorName.setText(
            f"{motors_properties.get('vertical name', '-')}"
        )
        self.ui.label_cameraMotorName.setText(
            f"{motors_properties.get('camera name', '-')}"
        )

    def refresh_properties(self) -> None:
        """Refresh system properties"""
        self.get_properties()
        self.sig_status_message.emit("System Properties Refreshed")


class FrameViewer(QObject):
    """Class for queueing and displaying images"""

    def __init__(self, parent: Controller_MainWindow, rows: int, columns: int) -> None:
        QObject.__init__(self, parent)
        self.parent = parent
        self.queue = queue.Queue(3)

        # Default frame size is 2000x2000 if no valid size provided
        if rows is not None:
            self.rows = int(rows)
        else:
            self.rows = 2000
        if columns is not None:
            self.columns = int(columns)
        else:
            self.columns = 2000

        # Empty frame
        frame_init = np.zeros((self.rows, self.columns), dtype=np.uint16)
        # Set one pixel to trick histogram initial range (0-2000)
        frame_init[0, 0] = 2000
        # Transpose since setImage is column-major
        frame_init = np.transpose(frame_init)
        # Set initial view
        self.parent.ui.imageView.setImage(frame_init)

    def enqueue_frame(self, frame: np.uint16) -> None:
        with contextlib.suppress(queue.Full):
            self.queue.put(frame, block=False)

    def updateUi_refresh_view(self) -> None:
        try:
            frame = self.queue.get(block=False)
        except queue.Empty:
            pass
        else:
            # setImage is column-major
            frame = np.transpose(frame)
            self.parent.ui.imageView.setImage(
                frame, autoRange=False, autoLevels=False, autoHistogramRange=False
            )


class FrameSaver(QObject):
    """Class for storing buffers (images) in its queue and saving them
    afterwards in a specified directory in a HDF5 format"""

    sig_status_message = pyqtSignal(str)

    def __init__(self, parent: Controller_MainWindow, block_size: int = 1) -> None:
        QObject.__init__(self, parent)
        self.parent = parent
        self.sig_status_message.connect(self.parent.updateUi_message_printer)
        self.file_format = self.parent.save_format

        self.saving_started = False
        self.block_size = block_size
        self.queue = queue.Queue(2 * block_size)

        self.sample_name = ""
        self.number_of_files = 1
        self.filenames_list = []
        self.horizontal_positions_list = []
        self.vertical_positions_list = []
        self.camera_positions_list = []

    def reinit(self, block_size: int) -> None:
        if self.saving_started:
            self.saving_started = False

        self.block_size = block_size
        self.queue = queue.Queue(
            2 * block_size
        )  # Set up queue of maxsize 2*block_size (frames)

        self.sample_name = ""
        self.number_of_files = 1
        self.filenames_list = []
        self.horizontal_positions_list = []
        self.vertical_positions_list = []
        self.camera_positions_list = []

    def add_sample_name(self, sample_name: str) -> None:
        """Add to a list the different motor positions"""
        self.sample_name = sample_name

    def add_motor_parameters(
        self,
        current_hor_position_txt: str,
        current_ver_position_txt: str,
        current_cam_position_txt: str,
    ) -> None:
        """Add to a list the different motor positions"""
        self.horizontal_positions_list.append(current_hor_position_txt)
        self.vertical_positions_list.append(current_ver_position_txt)
        self.camera_positions_list.append(current_cam_position_txt)

    def set_files(
        self,
        number_of_files: int,
        files_name: str,
        scan_type: str,
        number_of_datasets: int,
        datasets_name: str,
    ) -> None:
        """Set the number and name of files to save and makes sure the filenames
        are unique in the path to avoid overwrite on other files"""
        self.number_of_files = int(number_of_files)
        self.files_name = str(files_name)
        self.scan_type = str(scan_type)
        self.number_of_datasets = int(number_of_datasets)
        self.datasets_name = str(datasets_name)

        counter = 0
        for _ in range(self.number_of_files):
            while True:
                counter += 1
                new_filename = (
                    self.files_name
                    + "_"
                    + scan_type
                    + "_plane_"
                    + f"{counter:05d}"
                    + ".hdf5"
                )
                if not os.path.isfile(new_filename):  # Check for existing files
                    self.filenames_list.append(new_filename)
                    break

    # Saving methods

    def enqueue_buffer(self, buffer: np.ndarray) -> None:
        """Put an image in the save queue"""
        self.queue.put(item=buffer, block=True)

    def start_saving(self) -> None:
        """Initiates saving thread"""
        self.saving_started = True
        self.frame_saver_thread = threading.Thread(target=self.frame_saver_worker)
        self.frame_saver_thread.start()

    def _write_laser_metadata(self, outfile: h5py.File) -> None:
        """Write per-laser metadata as h5py.File ROOT attrs once per file.

        For each configured laser (ALL lasers, including inactive ones
        with power=0 / active=False — reproducibility context), writes:
        Laser{i+1} Wavelength (nm), Laser{i+1} Power (mW, canonical),
        Laser{i+1} Max Power (mW), Laser{i+1} Active (bool),
        Laser{i+1} Label (str). Read exclusively from the live
        self.parent.lasers instances — never re-parsed from config.ini
        at save time (fixes the config-drift metadata bug). Uniform mW
        units mean no per-laser unit attr is needed.
        """
        for i, laser in enumerate(self.parent.lasers):
            outfile.attrs[f"Laser{i+1} Wavelength"] = laser.wavelength
            outfile.attrs[f"Laser{i+1} Power"] = laser.power
            outfile.attrs[f"Laser{i+1} Max Power"] = laser.max_power
            outfile.attrs[f"Laser{i+1} Active"] = bool(laser.active)
            outfile.attrs[f"Laser{i+1} Label"] = laser.label

    def frame_saver_worker(self) -> None:
        """Thread for saving 3D arrays (or 2D arrays).
        The number of datasets per file is the number of 2D arrays"""
        for idx in range(len(self.filenames_list)):
            print("File created:" + str(self.filenames_list[idx]))  # debugging
            # Create file
            outfile = h5py.File(self.filenames_list[idx], "a")
            # Write per-laser metadata as file-level root attrs once per
            # file, read from the live list[ILaser] the controller holds
            # (never re-parsed from config.ini — fixes the config-drift
            # metadata bug). All configured lasers are included, even
            # inactive ones (power=0, active=False), for reproducibility.
            self._write_laser_metadata(outfile)

            counter = 1
            for dataset in range(int(self.number_of_datasets)):
                while True:
                    try:
                        # Retrieve buffer
                        buffer: np.ndarray = self.queue.get(True, 1)
                        if buffer.ndim == 2:
                            buffer = np.expand_dims(
                                buffer, axis=0
                            )  # To consider 2D arrays as a 3D array
                        for frame in range(buffer.shape[0]):  # For each 2D frame
                            # Create dataset
                            path_root = self.datasets_name + f"{counter:03d}"
                            self.dataset = outfile.create_dataset(
                                path_root, data=buffer[frame, :, :]
                            )
                            print(
                                "Dataset "
                                + str(dataset)
                                + "/"
                                + str(int(self.number_of_datasets))
                                + " created:"
                                + str(path_root)
                            )  # debugging

                            # Add attributes
                            self.dataset.attrs["Sample Name"] = self.sample_name
                            self.dataset.attrs["Date"] = str(datetime.date.today())

                            if buffer.shape[0] == 1:
                                pos_index = dataset + idx * int(self.number_of_datasets)
                            else:
                                pos_index = idx

                            self.dataset.attrs["Horizontal Position"] = (
                                self.horizontal_positions_list[pos_index]
                            )
                            self.dataset.attrs["Vertical Position"] = (
                                self.vertical_positions_list[pos_index]
                            )
                            self.dataset.attrs["Camera Position"] = (
                                self.camera_positions_list[pos_index]
                            )

                            counter += 1
                        break
                    except Exception:
                        if not self.saving_started:
                            break
                if not self.saving_started:
                    break
            outfile.close()
            self.sig_status_message.emit("File " + self.filenames_list[idx] + " saved")
            if not self.saving_started:
                break

    def stop_saving(self) -> None:
        """Changes the flag status to end the saving thread"""
        self.saving_started = False
        # self.frame_saver_thread.join()
