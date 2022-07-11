'''
Created on May 22, 2019

@authors: Pierre Girard-Collins & flesage
'''
import os
import sys
sys.path.append(".")

from PyQt5.QtCore import Qt, QObject, QTimer, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import QApplication, QMainWindow, QDialog, QFileDialog, QTableWidgetItem, QAbstractItemView, QMessageBox, QLabel, QProgressBar, QDesktopWidget, QButtonGroup

import logging
import copy
import threading
import time
import queue
import h5py
import datetime
import webbrowser
import nidaqmx
import numpy as np
from matplotlib import pyplot as plt
from scipy import signal, optimize, ndimage, stats

from gui.ui_controller import Ui_Controller
from gui.ui_properties import Ui_Properties

#FIXME - Free functions to integrate into own class (or at least cleanup/rename)
from src.config import cfg_read, cfg_write
from src.gaussian import gaussian, func, fwhm

from src.camera import Camera
from src.siggen import SigGen
from src.motors import Motors
from src.lasers import Lasers
from src.etls import ETLs


class Controller_MainWindow(QMainWindow):
    '''Class for the MesoSPIM Controller'''

    # Default confgurable settings
    _cfg_settings = {}
    _cfg_settings['Units'] = 'mm'

    # Signals
    sig_beep = pyqtSignal()
    sig_stylesheet = pyqtSignal(str)
    sig_message = pyqtSignal(str)
    sig_progress_update = pyqtSignal(int)

    sig_single_mode_finished = pyqtSignal()
    sig_live_mode_finished = pyqtSignal()
    sig_stack_mode_finished = pyqtSignal()
    sig_preview_mode_finished = pyqtSignal()
    sig_calibrate_camera_finished = pyqtSignal() #TODO
    sig_calibrate_etl_finished = pyqtSignal() #TODO

    sig_refresh_position_horizontal = pyqtSignal() #TODO
    sig_refresh_position_vertical = pyqtSignal() #TODO
    sig_refresh_position_camera = pyqtSignal() #TODO


    def __init__(self):
        # NOTES
        #
        # Previous Ui loading was done directly from .ui file with:
        # basepath = os.path.join(os.path.dirname(__file__))
        # uic.loadUi(os.path.join(basepath,"controller.ui"), self)
        # 
        # Ui approach taken below requires generating .py file from .ui (Qt Designer file format)
        # This enables VSCode IntelliSense to work properly on Ui classes
        # PS command for Ui file:
        # pyuic5 .\ui_controller.ui -o .\ui_controller.py
        #
        # PS command for resource file:
        # pyrcc5 .\ui_controller.qrc -o .\ui_controller_rc.py
        #
        # For resource file to be in path
        # add following two lines to ui_controller.py
        #   import sys
        #   sys.path.append("./gui") 
        #
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

        # Resize mainwindow    
        #self.resize(QDesktopWidget().availableGeometry(self).size() * 0.75)

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
        self.cfg_settings = cfg_read('config.ini', 'Controller', self.cfg_settings)

        # Assign configurable settings to instance variables
        self.units                  = str(self.cfg_settings['Units'])
        self.save_directory         = os.path.normpath(os.path.expanduser('~') + '\\Documents\\LightSheetData')
        self.save_filename          = ''
        self.save_description       = ''

        # Set units comboBox options (default: millimeters)
        self.ui.comboBox_units.insertItems(0,['mm','\u03BCm'])
        if self.units == '\u03BCm':
            self.ui.comboBox_units.setCurrentIndex(1)
        else:
            self.ui.comboBox_units.setCurrentIndex(0)

        if self.save_directory != '':
            self.ui.lineEdit_saveDirectory.setText(self.save_directory)
            self.ui.lineEdit_saveFilename.setText(self.save_filename)
            self.ui.lineEdit_saveFilename.setEnabled(True)
            self.ui.lineEdit_saveDescription.setText(self.save_description)
            self.ui.lineEdit_saveDescription.setEnabled(True)
        else:
            self.ui.lineEdit_saveDirectory.setText('')
            self.ui.lineEdit_saveFilename.setText('Filename - Select Save Directory First')
            self.ui.lineEdit_saveFilename.setEnabled(False)
            self.ui.lineEdit_saveDescription.setText('Description - Select Save Directory First')
            self.ui.lineEdit_saveDescription.setEnabled(False)

        # Flags
        self.single_mode_started = False
        self.preview_mode_started = False
        self.live_mode_started = False
        self.stack_mode_started = False
        self.camera_calibration_started = False
        self.etls_calibration_started = False

        self.saving_allowed = False
        self.focus_selected = False
        self.horizontal_forward_boundary_selected = False
        self.horizontal_backward_boundary_selected = False
        self.stack_starting_plane = None
        self.stack_ending_plane = None

        self.default_buttons = [self.ui.pushButton_acqStartPreviewMode,
                                self.ui.pushButton_acqStartLiveMode,
                                self.ui.pushButton_acqStartStackMode,
                                self.ui.pushButton_acqGetSingleImage,
                                self.ui.pushButton_calCameraStartCalibration,
                                self.ui.pushButton_calEtlStartCalibration]
        
        # Initial state of modes buttons
        #self.updateUi_modes_buttons(self.default_buttons)

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


        # Initial state of First and Last plane selection (for Stack Mode)
        self.ui.checkBox_acqFirstPlaneSet.setEnabled(False)
        self.ui.checkBox_acqLastPlaneSet.setEnabled(False)
        self.ui.pushButton_acqSetFirstPlane.setEnabled(True)
        self.ui.pushButton_acqSetLastPlane.setEnabled(True)

        # Initial state of some file selection buttons
        self.ui.pushButton_selectDataset.setEnabled(False)


        # -------------------------------------------------------------------------------------------------------------------------------
        # Signal connections for progress bar and command log
        # -------------------------------------------------------------------------------------------------------------------------------
        self.sig_progress_update.connect(self.ui.statusBar_progress.setValue)
        self.sig_message.connect(self.updateUi_message_printer)


        # -------------------------------------------------------------------------------------------------------------------------------
        # Connections for menu actions
        # -------------------------------------------------------------------------------------------------------------------------------
        self.ui.action_Exit.triggered.connect(self.close)
        self.ui.action_ShowHideControlsPane.triggered.connect(self.updateUi_show_hide_controls_pane)
        self.ui.action_ShowHideImagesPane.triggered.connect(self.updateUi_show_hide_images_pane)
        self.ui.action_ShowHideMessageLog.triggered.connect(self.updateUi_show_hide_message_log)
        self.ui.action_lightTheme.triggered.connect(self.updateUi_light_theme)
        self.ui.action_darkTheme.triggered.connect(self.updateUi_dark_theme)
        self.ui.action_showSystemProperties.triggered.connect(self.open_properties_dialog)
        self.ui.action_openDocumentation.triggered.connect(self.open_help)


        # -------------------------------------------------------------------------------------------------------------------------------
        # Connections for the 'Motion' tab controls
        # -------------------------------------------------------------------------------------------------------------------------------

        # Connection for unit change
        self.ui.comboBox_units.currentTextChanged.connect(self.updateUi_units)

        # Connections for the sample motion buttons
        self.ui.pushButton_sampleStepUp.clicked.connect(self.updateUi_move_sample_up)
        self.ui.pushButton_sampleStepDown.clicked.connect(self.updateUi_move_sample_down)
        self.ui.pushButton_sampleStepForward.clicked.connect(self.updateUi_move_sample_forward)
        self.ui.pushButton_sampleStepBackward.clicked.connect(self.updateUi_move_sample_backward)
        self.ui.pushButton_sampleGotoOrigin.clicked.connect(self.updateUi_move_sample_to_origin)
        self.ui.pushButton_sampleSetOrigin.clicked.connect(self.updateUi_set_sample_origin)
        self.ui.pushButton_sampleGotoHPosition.clicked.connect(self.updateUi_move_to_horizontal_position)
        self.ui.pushButton_sampleGotoVPosition.clicked.connect(self.updateUi_move_to_vertical_position)

        # Connections for the camera motion buttons
        self.ui.pushButton_cameraGotoPosition.clicked.connect(self.updateUi_move_camera_to_position)
        self.ui.pushButton_cameraSetFocus.clicked.connect(self.updateUi_set_camera_focus)
        self.ui.pushButton_cameraStepForward.clicked.connect(self.updateUi_move_camera_forward)
        self.ui.pushButton_cameraStepBackward.clicked.connect(self.updateUi_move_camera_backward)
        self.ui.pushButton_cameraGotoFocus.clicked.connect(self.updateUi_move_camera_to_focus)


        # -------------------------------------------------------------------------------------------------------------------------------
        # Connections for the 'Scan Settings' tab controls
        # -------------------------------------------------------------------------------------------------------------------------------

        # Connection for etl settings changes
        self.ui.doubleSpinBox_etlLeftAmplitude.valueChanged.connect(self.updateUi_etl_left_amplitude)
        self.ui.doubleSpinBox_etlRightAmplitude.valueChanged.connect(self.updateUi_etl_right_amplitude)
        self.ui.doubleSpinBox_etlLeftOffset.valueChanged.connect(self.updateUi_etl_left_offset)
        self.ui.doubleSpinBox_etlRightOffset.valueChanged.connect(self.updateUi_etl_right_offset)
        self.ui.checkBox_etlSync.stateChanged.connect(self.updateUi_etl_sync)
        self.ui.checkBox_etlActivate.stateChanged.connect(self.updateUi_etl_activate)
        self.ui.doubleSpinBox_etlSteps.valueChanged.connect(self.updateUi_etl_steps)

        # Connection for galvo settings changes
        self.ui.doubleSpinBox_galvoLeftAmplitude.valueChanged.connect(self.updateUi_galvo_left_amplitude)
        self.ui.doubleSpinBox_galvoRightAmplitude.valueChanged.connect(self.updateUi_galvo_right_amplitude)
        self.ui.doubleSpinBox_galvoLeftOffset.valueChanged.connect(self.updateUi_galvo_left_offset)
        self.ui.doubleSpinBox_galvoRightOffset.valueChanged.connect(self.updateUi_galvo_right_offset)
        self.ui.checkBox_galvoSync.stateChanged.connect(self.updateUi_galvo_sync)
        self.ui.checkBox_galvoActivate.stateChanged.connect(self.updateUi_galvo_activate)
        self.ui.checkBox_galvoInvert.stateChanged.connect(self.updateUi_galvo_invert)

        # Connection for laser settings changes
        self.ui.doubleSpinBox_laserOneAmplitude.valueChanged.connect(self.updateUi_laser1_amplitude)
        self.ui.doubleSpinBox_laserTwoAmplitude.valueChanged.connect(self.updateUi_laser2_amplitude)

        # Connection for general acquisition settings changes
        self.ui.doubleSpinBox_acqSampleRate.valueChanged.connect(self.updateUi_acq_sample_rate)
        self.ui.doubleSpinBox_acqExposureTime.valueChanged.connect(self.updateUi_acq_exposure_time)
        self.ui.doubleSpinBox_acqLineTime.valueChanged.connect(self.updateUi_acq_line_time)
        self.ui.doubleSpinBox_acqLineExposure.valueChanged.connect(self.updateUi_acq_line_exposure)
        self.ui.doubleSpinBox_acqLineDelay.valueChanged.connect(self.updateUi_acq_line_delay)

        # -------------------------------------------------------------------------------------------------------------------------------
        # Connections for the 'Calibration' tab controls
        # -------------------------------------------------------------------------------------------------------------------------------
        self.ui.pushButton_calCameraStartCalibration.clicked.connect(self.camera_calibration_button)
        self.ui.pushButton_calCameraComputeFocus.clicked.connect(self.calculate_camera_focus)
        self.ui.pushButton_calCameraShowInterpolation.clicked.connect(self.show_camera_interpolation)
        self.ui.pushButton_calEtlStartCalibration.clicked.connect(self.etls_calibration_button)
        self.ui.pushButton_calEtlShowInterpolation.clicked.connect(self.show_etl_interpolation)
        self.ui.pushButton_calHorizontalStartRangeSelection.clicked.connect(self.updateUi_reset_boundaries)
        self.ui.pushButton_calHorizontalSetForwardLimit.clicked.connect(self.updateUi_set_horizontal_forward_boundary)
        self.ui.pushButton_calHorizontalSetBackwardLimit.clicked.connect(self.updateUi_set_horizontal_backward_boundary)


        # -------------------------------------------------------------------------------------------------------------------------------
        # Connections for the 'File Manager' tab controls
        # -------------------------------------------------------------------------------------------------------------------------------
        self.ui.pushButton_selectFile.clicked.connect(self.updateUi_select_file)
        self.ui.pushButton_selectDataset.clicked.connect(self.updateUi_select_dataset)
        self.ui.listWidget_fileDatasets.doubleClicked.connect(self.updateUi_select_dataset)


        # -------------------------------------------------------------------------------------------------------------------------------
        # Connections for the 'Manual Acquisition' controls
        # -------------------------------------------------------------------------------------------------------------------------------
        self.ui.pushButton_acqGetSingleImage.clicked.connect(self.updateUi_single_mode_button)
        self.ui.pushButton_acqStartLiveMode.clicked.connect(self.updateUi_live_mode_button)
        self.ui.pushButton_acqStartPreviewMode.clicked.connect(self.updateUi_preview_mode_button)


        # -------------------------------------------------------------------------------------------------------------------------------
        # Connections for the 'Automatic Acquisition' controls
        # -------------------------------------------------------------------------------------------------------------------------------
        self.ui.pushButton_acqStartStackMode.clicked.connect(self.updateUi_stack_mode_button)
        self.ui.doubleSpinBox_acqPlaneStepSize.valueChanged.connect(self.updateUi_set_number_of_planes)
        self.ui.pushButton_acqSetFirstPlane.clicked.connect(self.updateUi_set_stack_mode_starting_point)
        self.ui.pushButton_acqSetLastPlane.clicked.connect(self.updateUi_set_stack_mode_ending_point)


        # -------------------------------------------------------------------------------------------------------------------------------
        # Connections for the 'Lasers' controls
        # -------------------------------------------------------------------------------------------------------------------------------
        self.ui.pushButton_laserOneToggle.clicked.connect(self.laser1_toggle_button)
        self.ui.pushButton_laserTwoToggle.clicked.connect(self.laser2_toggle_button)


        # -------------------------------------------------------------------------------------------------------------------------------
        # Connections for the 'Save Settings' controls
        # -------------------------------------------------------------------------------------------------------------------------------
        self.ui.pushButton_saveSelectDirectory.clicked.connect(self.updateUi_select_directory)
        self.ui.pushButton_saveCurrentImage.clicked.connect(self.updateUi_save_single_image)

        self.save_option_button_group = QButtonGroup(self)
        self.save_option_button_group.addButton(self.ui.checkBox_saveStitch)
        self.save_option_button_group.addButton(self.ui.checkBox_saveStitchBlend)
        self.save_option_button_group.addButton(self.ui.checkBox_saveAllCrop)
        self.save_option_button_group.addButton(self.ui.checkBox_saveAllFull)
        self.save_option_button_group.setExclusive(True)

        # -------------------------------------------------------------------------------------------------------------------------------
        # Signal connections for post modes (threads) Ui updates
        # -------------------------------------------------------------------------------------------------------------------------------
        self.sig_single_mode_finished.connect(self.updateUi_post_single_mode)
        self.sig_live_mode_finished.connect(self.updateUi_post_live_mode)
        self.sig_stack_mode_finished.connect(self.updateUi_post_stack_mode)
        self.sig_preview_mode_finished.connect(self.updateUi_post_preview_mode)


        # -------------------------------------------------------------------------------------------------------------------------------
        # Signal connections for position refresh requests
        # -------------------------------------------------------------------------------------------------------------------------------
        self.sig_refresh_position_horizontal.connect(self.updateUi_position_horizontal)
        self.sig_refresh_position_vertical.connect(self.updateUi_position_vertical)
        self.sig_refresh_position_camera.connect(self.updateUi_position_camera)


        # Start single shot timer to complete hardware init after event loop is started
        self.timer_hardware_init = QTimer()
        self.timer_hardware_init.setSingleShot(True)
        self.timer_hardware_init.timeout.connect(self.hardware_init)
        self.timer_hardware_init.start(100)


    def hardware_init(self):
        """
        Completes initialisation of hardware and image consumers
        Launches timer to periodically refresh image display port (imageView)
        """
        # Change to busy cursor and display status message
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.ui.statusbar.showMessage('Initializing hardware, please wait...')
        self.ui.statusbar.repaint()

        # Instantiating hardware components
        self.camera = Camera(verbose=True)
        # Signal Generator needs to know about Camera settings to generate proper scan waveforms
        self.siggen = SigGen(self.camera)
        self.motors = Motors()
        self.lasers = Lasers()
        self.etls = ETLs()

        # Making sure ETLs are in analog mode
        self.etls.open()
        self.etls.set_analog_mode()

        # Update Ui with initial hardware state
        self.updateUi_initial_hardware_state()

        # Instantiating the display port queue (image consumer)
        self.frame_viewer = FrameViewer(self, rows=self.camera.ysize, columns=self.camera.xsize)

        # Instantiating the frame saver (image consumer)
        self.frame_saver = FrameSaver(self)

        # Start timer to periodically (100ms) refresh the display port
        self.timer_imageview = QTimer()
        self.timer_imageview.timeout.connect(self.frame_viewer.updateUi_refresh_view)
        self.timer_imageview.start(100)

        # Init done, restore normal cursor
        QApplication.restoreOverrideCursor()
        self.ui.statusbar.showMessage('Ready', 2000)


    def closeEvent(self, event):
        """
        Making sure that everything is closed when the user exits the software.
        This function executes automatically when the user closes the UI.
        This is an intrinsic function name of Qt, don't change the name even 
        if it doesn't follow the naming convention
        """
        result = QMessageBox.question(self, "Confirm Exit...", "Are you sure you want to exit ?", QMessageBox.Yes | QMessageBox.No)
        if result == QMessageBox.Yes:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            self.ui.statusbar.showMessage('Shutting down hardware...')
            self.ui.statusbar.repaint()
            self.close_modes()
            # FIXME
            # waits one second for the threaded workers to stop ... implement checks or join
            time.sleep(1)
            self.camera.close()
            self.etls.close()
            self.timer_imageview.stop()
            QApplication.restoreOverrideCursor()
            event.accept()
        else:
            event.ignore()
            
    @pyqtSlot(str)
    def updateUi_message_printer(self, message:str):
        '''Print text in console, in controller text box and in status bar'''
        logging.info(message)
        self.ui.statusbar.showMessage(message, 2000)
        self.ui.plainTextEdit_messageLog.appendPlainText(message)
        self.ui.plainTextEdit_messageLog.verticalScrollBar().setValue(self.ui.plainTextEdit_messageLog.verticalScrollBar().maximum())

    def open_properties_dialog(self):
        '''Open the dialog window for showing properties'''
        self.properties_dialog = Properties_Dialog(self)
        self.properties_dialog.setAttribute(Qt.WA_DeleteOnClose)
        self.properties_dialog.open()
        self.properties_dialog.get_properties()

    def open_help(self):
        '''Open help documentation (PDF)'''
        guide_pdf = os.path.dirname(os.path.abspath(__file__)) + r'\..\Guide.pdf'
        webbrowser.open_new(guide_pdf)

    def updateUi_light_theme(self):
        self.sig_stylesheet.emit('light')
        return None

    def updateUi_dark_theme(self):
        self.sig_stylesheet.emit('dark')
        return None

    def updateUi_show_hide_images_pane(self):
        if self.ui.imagesPane.isVisible():
            self.ui.imagesPane.hide()
        else:
            self.ui.imagesPane.show()

    def updateUi_show_hide_controls_pane(self):
        if self.ui.controlsPane.isVisible():
            self.ui.controlsPane.hide()
        else:
            self.ui.controlsPane.show()

    def updateUi_show_hide_message_log(self):
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
    #         self.ui.imageView.setImage(frame, autoRange=False, autoLevels=False, autoHistogramRange=False)
    

    def updateUi_motor_buttons(self, disable_button=True):
        '''Enable or disable all motor buttons'''
        #FIXME
        buttons_to_disable = [self.ui.pushButton_sampleStepUp,
                              self.ui.pushButton_sampleGotoOrigin,
                              self.ui.pushButton_sampleStepDown,
                              self.ui.pushButton_sampleStepBackward,
                              self.ui.pushButton_sampleStepForward,
                              self.ui.pushButton_sampleGotoHPosition,
                              self.ui.pushButton_sampleGotoVPosition,
                              self.ui.pushButton_cameraStepBackward,
                              self.ui.pushButton_cameraStepForward,
                              self.ui.pushButton_cameraGotoFocus,
                              self.ui.pushButton_cameraGotoPosition]
        for button in buttons_to_disable:
            if disable_button:
                button.setEnabled(False)
            else:
                button.setEnabled(True)
    
    def updateUi_modes_buttons(self, buttons_to_enable):
        '''Update mode buttons status : disable buttons, except for those specified to be enabled'''
        #FIXME
        aquisition_buttons = [self.ui.pushButton_acqStartPreviewMode,
                              self.ui.pushButton_acqStartLiveMode,
                              self.ui.pushButton_acqStartStackMode,
                              self.ui.pushButton_acqGetSingleImage,
                              self.ui.pushButton_saveCurrentImage,
                              self.ui.pushButton_calCameraStartCalibration,
                              self.ui.pushButton_calCameraComputeFocus,
                              self.ui.pushButton_calCameraShowInterpolation,
                              self.ui.pushButton_calEtlStartCalibration,
                              self.ui.pushButton_calEtlShowInterpolation]
        for button in aquisition_buttons:
            if button in buttons_to_enable:
                button.setEnabled(True)
            else:
                button.setEnabled(False)

    def updateUi_enable_buttons(self, buttons_to_enable):
        '''Enable buttons'''
        for button in buttons_to_enable:
            button.setEnabled(True)

    def updateUi_disable_buttons(self, buttons_to_disable):
        '''Disable buttons'''
        for button in buttons_to_disable:
            button.setEnabled(True)

    def close_modes(self):
        '''Close all thread modes if they are active'''
        #FIXME
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
        if self.lasers.laser1_active or self.lasers.laser2_active:
            self.stop_lasers()


    def updateUi_initial_hardware_state(self):
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

        self.ui.doubleSpinBox_acqSampleRate.setValue(self.siggen.sample_rate)
        self.ui.doubleSpinBox_acqExposureTime.setValue(self.camera.exposure_time * 1e3) #camera(s) to ui(ms)

        self.ui.doubleSpinBox_acqLineTime.setValue(self.camera.lightsheet_line_time * 1e6) #camera(s) to ui(us)
        self.ui.doubleSpinBox_acqLineExposure.setValue(self.camera.lightsheet_exposed_lines)
        self.ui.doubleSpinBox_acqLineDelay.setValue(self.camera.lightsheet_delay_lines)

        # Lasers
        self.ui.doubleSpinBox_laserOneAmplitude.setValue(self.lasers.laser1_power)
        self.ui.doubleSpinBox_laserTwoAmplitude.setValue(self.lasers.laser2_power)
        # Motors
        self.updateUi_units()


    def updateUi_units(self):
        '''Updates all the widgets of the motion tab after an unit change'''
        self.units = self.ui.comboBox_units.currentText()
        
        if self.units == 'mm':
            self.units_decimals = 3
            self.units_fixformat = str('{:.5f} {}')
            self.units_increment = 0.1
        elif self.units == '\u03BCm':
            self.units_decimals = 0
            self.units_fixformat = str('{:.2f} {}')
            self.units_increment = 100

        # Updates to horizontal position
        self.ui.doubleSpinBox_sampleSetHPosition.setDecimals(self.units_decimals)
        self.ui.doubleSpinBox_sampleSetHPosition.setSuffix(" {}".format(self.units))
        self.ui.doubleSpinBox_sampleSetHPosition.setMinimum(self.motors.horizontal.get_limit_low(self.units))
        self.ui.doubleSpinBox_sampleSetHPosition.setMaximum(self.motors.horizontal.get_limit_high(self.units))

        # Updates to vertical position
        self.ui.doubleSpinBox_sampleSetVPosition.setDecimals(self.units_decimals)
        self.ui.doubleSpinBox_sampleSetVPosition.setSuffix(" {}".format(self.units))
        self.ui.doubleSpinBox_sampleSetVPosition.setMinimum(self.motors.vertical.get_limit_low(self.units))
        self.ui.doubleSpinBox_sampleSetVPosition.setMaximum(self.motors.vertical.get_limit_high(self.units))

        # Updates to camera position
        self.ui.doubleSpinBox_cameraSetPosition.setDecimals(self.units_decimals)
        self.ui.doubleSpinBox_cameraSetPosition.setSuffix(" {}".format(self.units))
        self.ui.doubleSpinBox_cameraSetPosition.setMinimum(self.motors.camera.get_limit_low(self.units))
        self.ui.doubleSpinBox_cameraSetPosition.setMaximum(self.motors.camera.get_limit_high(self.units))

        # Updates to horizontal step size (increment/decrement)
        self.ui.doubleSpinBox_sampleHStepSize.setValue(self.units_increment)
        self.ui.doubleSpinBox_sampleHStepSize.setDecimals(self.units_decimals)
        self.ui.doubleSpinBox_sampleHStepSize.setSuffix(" {}".format(self.units))
        self.ui.doubleSpinBox_sampleHStepSize.setMinimum(10**-self.units_decimals)
        maximum_horizontal_increment = self.ui.doubleSpinBox_sampleSetHPosition.maximum() - self.ui.doubleSpinBox_sampleSetHPosition.minimum()
        self.ui.doubleSpinBox_sampleHStepSize.setMaximum(maximum_horizontal_increment)

        # Updates to vertical step size (increment/decrement)
        self.ui.doubleSpinBox_sampleVStepSize.setValue(self.units_increment)
        self.ui.doubleSpinBox_sampleVStepSize.setDecimals(self.units_decimals)
        self.ui.doubleSpinBox_sampleVStepSize.setSuffix(" {}".format(self.units))
        self.ui.doubleSpinBox_sampleVStepSize.setMinimum(10**-self.units_decimals)
        maximum_vertical_increment = self.ui.doubleSpinBox_sampleSetVPosition.maximum() - self.ui.doubleSpinBox_sampleSetVPosition.minimum()
        self.ui.doubleSpinBox_sampleVStepSize.setMaximum(maximum_vertical_increment)

        # Updates to camera step size (increment/decrement)
        self.ui.doubleSpinBox_cameraStepSize.setValue(self.units_increment)
        self.ui.doubleSpinBox_cameraStepSize.setDecimals(self.units_decimals)
        self.ui.doubleSpinBox_cameraStepSize.setSuffix(" {}".format(self.units))
        self.ui.doubleSpinBox_cameraStepSize.setMinimum(10**-self.units_decimals)
        maximum_camera_increment = self.ui.doubleSpinBox_cameraSetPosition.maximum() - self.ui.doubleSpinBox_cameraSetPosition.minimum()
        self.ui.doubleSpinBox_cameraStepSize.setMaximum(maximum_camera_increment)
        
        # Update current positions indicators
        self.updateUi_position_indicators()

    def updateUi_position_indicators(self):
        '''Refreshes the position indicators'''
        self.updateUi_position_horizontal()
        self.updateUi_position_vertical()
        self.updateUi_position_camera()

    def updateUi_position_horizontal(self):
        '''Updates the current horizontal sample position displayed'''
        self.current_horizontal_position_text = self.units_fixformat.format(self.motors.horizontal.get_position(self.units), self.units)
        self.ui.label_sampleCurrentHPosition.setText(self.current_horizontal_position_text)
    
    def updateUi_position_vertical(self):
        '''Updates the current vertical sample position displayed'''
        self.current_vertical_position_text = self.units_fixformat.format(self.motors.vertical.get_position(self.units), self.units)
        self.ui.label_sampleCurrentVPosition.setText(self.current_vertical_position_text)
        
    def updateUi_position_camera(self):
        '''Updates the current camera position displayed'''
        self.current_camera_position_text = self.units_fixformat.format(self.motors.camera.get_position(self.units), self.units)
        self.ui.label_cameraCurrentPosition.setText(self.current_camera_position_text)
    
    def updateUi_move_to_horizontal_position(self):
        '''Moves the sample to a specified horizontal position'''
        if ((self.ui.doubleSpinBox_sampleSetHPosition.value() >= self.motors.horizontal.get_limit_low(self.units)) and (self.ui.doubleSpinBox_sampleSetHPosition.value() <= self.motors.horizontal.get_limit_high(self.units))):
            self.motors.horizontal.move_absolute_position(self.ui.doubleSpinBox_sampleSetHPosition.value(), self.units)
            self.updateUi_message_printer('Sample moving to horizontal position')
            self.updateUi_position_horizontal()
        else:
            self.updateUi_message_printer('Out of boundaries')
            self.sig_beep.emit()
    
    def updateUi_move_to_vertical_position(self):
        '''Moves the sample to a specified vertical position'''
        if ((self.ui.doubleSpinBox_sampleSetVPosition.value() >= self.motors.vertical.get_limit_low(self.units)) and (self.ui.doubleSpinBox_sampleSetVPosition.value() <= self.motors.vertical.get_limit_high(self.units))):
            self.motors.vertical.move_absolute_position(self.ui.doubleSpinBox_sampleSetVPosition.value(), self.units)
            self.updateUi_message_printer('Sample moving to vertical position')
            self.updateUi_position_vertical()
        else:
            self.updateUi_message_printer('Out of boundaries')
            self.sig_beep.emit()

    def updateUi_move_sample_to_origin(self):
        '''Moves vertical and horizontal sample motors to origin position'''
        if (self.motors.horizontal.get_origin(self.units) <= self.motors.horizontal.get_limit_high(self.units)) and (self.motors.horizontal.get_origin(self.units) >= self.motors.horizontal.get_limit_low(self.units)):
            '''Moving sample to horizontal origin'''
            self.motors.horizontal.move_absolute_position(self.motors.horizontal.get_origin(self.units), self.units)
            self.updateUi_message_printer('Moving to horizontal origin')
            self.updateUi_position_horizontal()
        else:
            self.sig_beep.emit()
            self.updateUi_message_printer('Horizontal origin out of boundaries')
        
        if (self.motors.vertical.get_origin(self.units) <= self.motors.vertical.get_limit_high(self.units)) and (self.motors.vertical.get_origin(self.units) >= self.motors.vertical.get_limit_low(self.units)):
            '''Moving sample to vertical origin'''
            self.motors.vertical.move_absolute_position(self.motors.vertical.get_origin(self.units), self.units)
            self.updateUi_message_printer('Moving to vertical origin')
            self.updateUi_position_vertical()
        else:
            self.sig_beep.emit()
            self.updateUi_message_printer('Vertical origin out of boundaries')

    def updateUi_move_camera_to_position(self):
        '''Moves the sample to a specified vertical position'''
        if ((self.ui.doubleSpinBox_cameraSetPosition.value() >= self.motors.camera.get_limit_low(self.units)) and (self.ui.doubleSpinBox_cameraSetPosition.value() <= self.motors.camera.get_limit_high(self.units))):
            self.motors.camera.move_absolute_position(self.ui.doubleSpinBox_cameraSetPosition.value(), self.units)
            self.updateUi_message_printer ('Camera moving to position')
            self.updateUi_position_camera()
        else:
            self.updateUi_message_printer('Out of boundaries')
            self.sig_beep.emit()

    def updateUi_move_camera_to_focus(self):
        '''Moves camera to focus position'''
        if self.focus_selected:
            if self.motors.camera.get_origin(self.units) > self.motors.camera.get_limit_high(self.units):
                self.motors.camera.move_absolute_position(self.motors.camera.get_limit_high(self.units), self.units)
                self.updateUi_message_printer('Focus out of boundaries')
                self.sig_beep.emit()
                self.updateUi_position_camera()
            elif self.motors.camera.get_origin(self.units) < self.motors.camera.get_limit_low(self.units):
                self.motors.camera.move_absolute_position(self.motors.camera.get_limit_low(self.units), self.units)
                self.updateUi_message_printer('Focus out of boundaries')
                self.sig_beep.emit()
                self.updateUi_position_camera()
            else:
                self.motors.camera.move_absolute_position(self.motors.camera.get_origin(self.units), self.units)
                self.updateUi_message_printer('Moving to focus')
                self.updateUi_position_camera()
        else:
            self.motors.camera.move_absolute_position(self.motors.camera.get_origin(self.units), self.units)
            self.updateUi_message_printer('Focus not yet set. Moving camera to default focus')
            self.updateUi_position_camera()

    def updateUi_move_sample_backward(self):
        '''Sample motor backward horizontal motion'''
        if self.motors.horizontal.get_position(self.units) - self.ui.doubleSpinBox_sampleHStepSize.value() >= self.motors.horizontal.get_limit_low(self.units):
            self.motors.horizontal.move_relative_position(-self.ui.doubleSpinBox_sampleHStepSize.value(), self.units)
            self.updateUi_message_printer ('Sample moving backward')
            self.updateUi_position_horizontal()
        else:
            self.motors.horizontal.move_absolute_position(self.motors.horizontal.get_limit_low(self.units), self.units)
            self.updateUi_message_printer('Out of boundaries')
            self.sig_beep.emit()
            self.updateUi_position_horizontal()

    def updateUi_move_sample_forward(self):
        '''Sample motor forward horizontal motion'''
        if self.motors.horizontal.get_position(self.units) + self.ui.doubleSpinBox_sampleHStepSize.value() <= self.motors.horizontal.get_limit_high(self.units):
            self.motors.horizontal.move_relative_position(self.ui.doubleSpinBox_sampleHStepSize.value(), self.units)
            self.updateUi_message_printer('Sample moving forward')
            self.updateUi_position_horizontal()
        else:
            self.motors.horizontal.move_absolute_position(self.motors.horizontal.get_limit_high(self.units), self.units)
            self.updateUi_message_printer('Out of boundaries')
            self.sig_beep.emit()
            self.updateUi_position_horizontal()

    def updateUi_move_sample_up(self):
        '''Sample motor upward vertical motion'''
        if self.motors.vertical.get_position(self.units) - self.ui.doubleSpinBox_sampleVStepSize.value() >= self.motors.vertical.get_limit_low(self.units):
            self.motors.vertical.move_relative_position(-self.ui.doubleSpinBox_sampleVStepSize.value(), self.units)
            self.updateUi_message_printer('Sample stepping up')
            self.updateUi_position_vertical()
        else:
            self.motors.vertical.move_absolute_position(self.motors.vertical.get_limit_low(self.units), self.units)
            self.updateUi_message_printer('Out of boundaries')
            self.sig_beep.emit()
            self.updateUi_position_vertical()
    
    def updateUi_move_sample_down(self):
        '''Sample motor downward vertical motion'''
        if self.motors.vertical.get_position(self.units) + self.ui.doubleSpinBox_sampleVStepSize.value() <= self.motors.vertical.get_limit_high(self.units):
            self.motors.vertical.move_relative_position(self.ui.doubleSpinBox_sampleVStepSize.value(), self.units)
            self.updateUi_message_printer('Sample stepping down')
            self.updateUi_position_vertical()
        else:
            self.motors.vertical.move_absolute_position(self.motors.vertical.get_limit_high(self.units), self.units)
            self.updateUi_message_printer('Out of boundaries')
            self.sig_beep.emit()
            self.updateUi_position_vertical()

    def updateUi_move_camera_backward(self):
        '''Camera motor backward horizontal motion'''
        if self.motors.camera.get_position(self.units) - self.ui.doubleSpinBox_cameraStepSize.value() >= self.motors.camera.get_limit_low(self.units):
            self.motors.camera.move_relative_position(-self.ui.doubleSpinBox_cameraStepSize.value(), self.units)
            self.updateUi_message_printer('Camera stepping backward')
            self.updateUi_position_camera()
        else:
            self.motors.camera.move_absolute_position(self.motors.camera.get_limit_low(self.units), self.units)
            self.updateUi_message_printer('Out of boundaries')
            self.sig_beep.emit()
            self.updateUi_position_camera()

    def updateUi_move_camera_forward(self):
        '''Camera motor forward horizontal motion'''
        if self.motors.camera.get_position(self.units) + self.ui.doubleSpinBox_cameraStepSize.value() <= self.motors.camera.get_limit_high(self.units):
            self.motors.camera.move_relative_position(self.ui.doubleSpinBox_cameraStepSize.value(), self.units)
            self.updateUi_message_printer('Camera stepping forward')
            self.updateUi_position_camera()
        else:
            self.motors.camera.move_absolute_position(self.motors.camera.get_limit_high(self.units), self.units)
            self.updateUi_message_printer('Out of boundaries')
            self.sig_beep.emit()
            self.updateUi_position_camera()


    def updateUi_reset_boundaries(self):
        '''Reset variables for setting sample's horizontal motion range'''
        self.ui.pushButton_calHorizontalStartRangeSelection.setEnabled(False)
        self.ui.pushButton_calHorizontalSetForwardLimit.setEnabled(True)
        self.ui.pushButton_calHorizontalSetBackwardLimit.setEnabled(True)
        self.ui.label_calibrateRange.setText("Move Horizontal Position")
        '''Default boundaries'''
        self.motors.horizontal.set_limit_low(0, self.units)
        self.motors.horizontal.set_limit_high(0, self.units)
        self.updateUi_units() 
    
    def updateUi_set_horizontal_backward_boundary(self):
        '''Set lower limit of sample's horizontal motion'''
        self.motors.horizontal.set_limit_low(self.motors.horizontal.get_position(self.units), self.units)
        self.updateUi_units()
        self.horizontal_backward_boundary_selected = True
        self.ui.pushButton_calHorizontalSetBackwardLimit.setEnabled(False)
        if self.horizontal_forward_boundary_selected:
            self.ui.pushButton_calHorizontalStartRangeSelection.setEnabled(True)
            self.ui.label_calibrateRange.setText('Press Calibrate Range To Start')
    
    def updateUi_set_horizontal_forward_boundary(self):
        '''Set upper limit of sample's horizontal motion'''
        self.motors.horizontal.set_limit_high(self.motors.horizontal.get_position(self.units), self.units)
        self.updateUi_units()
        self.horizontal_forward_boundary_selected = True
        self.ui.pushButton_calHorizontalSetForwardLimit.setEnabled(False)
        if self.horizontal_backward_boundary_selected:
            self.ui.pushButton_calHorizontalStartRangeSelection.setEnabled(True)
            self.ui.label_calibrateRange.setText('Press Calibrate Range To Start')
    
    def updateUi_set_sample_origin(self):
        '''Modifies the sample origin position'''
        self.motors.horizontal.set_origin(self.motors.horizontal.get_position(self.units), self.units)
        self.motors.vertical.set_origin(self.motors.vertical.get_position(self.units), self.units)
        origin_text = f'Sample origin set at ({self.motors.horizontal.get_origin(self.units)}, {self.motors.vertical.get_origin(self.units)}) {self.units}'
        self.updateUi_message_printer(origin_text)
 
    def updateUi_set_camera_focus(self):
        '''Modifies manually the camera focus position'''
        self.focus_selected = True
        self.motors.camera.set_origin(self.motors.camera.get_position(self.units), self.units)
        focus_text = f'Camera focus manually set at {self.motors.camera.get_origin(self.units)} {self.units}'
        self.updateUi_message_printer(focus_text)

    def calculate_camera_focus(self):
        '''Interpolates the camera focus position'''
        # Current sample position
        current_position = self.motors.horizontal.get_position(self.units)
        # Compute corresponding optimal focus position
        focus_regression = self.slope_camera * current_position + self.intercept_camera
        self.motors.camera.set_origin(focus_regression, self.units)
        print('focus_regression:' + str(focus_regression)) #debugging
        self.focus_selected = True
        self.updateUi_message_printer('Focus automatically set')
    
    def show_camera_interpolation(self):
        '''Shows the camera focus interpolation'''
        x = self.camera_focus_relation[:,0]
        y = self.camera_focus_relation[:,1]
        
        '''Calculating linear regression'''
        xnew = np.linspace(self.camera_focus_relation[0,0], self.camera_focus_relation[-1,0], 1000) ##1000 points
        self.slope_camera, self.intercept_camera, r_value, p_value, std_err = stats.linregress(x, y)
        print('r_value:'+str(r_value)) #debugging
        print('p_value:'+str(p_value)) #debugging
        print('std_err:'+str(std_err)) #debugging
        yreg = self.slope_camera * xnew + self.intercept_camera
        
        '''Setting colormap'''
        xstart = self.motors.horizontal.get_limit_low(self.units)
        xend = self.motors.horizontal.get_limit_high(self.units)
        ystart = self.focus_forward_boundary
        yend = self.focus_backward_boundary
        transp = copy.deepcopy(self.donnees)
        for q in range(int(self.number_of_calibration_planes)):
            transp[q,:] = np.flip(transp[q,:])
        transp = np.transpose(transp)

        '''Showing interpolation graph'''
        plt.figure(1)
        plt.title('Camera Focus Regression') 
        plt.xlabel('Sample Horizontal Position ({})'.format(self.units)) 
        plt.ylabel('Camera Position ({})'.format(self.units))
        plt.imshow(transp, cmap='gray', extent=[xstart,xend, ystart,yend]) #Colormap
        plt.plot(x, y, 'o') #Raw data
        plt.plot(xnew,yreg) #Linear regression
        plt.show(block=False)   #Prevents the plot from blocking the execution of the code...
        
        #debugging
        n=int(self.number_of_camera_positions)
        x=np.arange(n)
        for g in range(int(self.number_of_calibration_planes)):
            plt.figure(g+2)
            plt.plot(self.donnees[g,:])
            plt.plot(x,gaussian(x,*self.popt[g]),'ro:',label='fit')
            plt.show(block=False)
    
    def show_etl_interpolation(self):
        '''Shows the etl focus interpolation'''
        xl = self.etl_l_relation[:,0]
        yl = self.etl_l_relation[:,1]
        #Left linear regression
        xlnew = np.linspace(self.etl_l_relation[0,0], self.etl_l_relation[-1,0], 1000) #1000 points
        lslope, lintercept, r_value, p_value, std_err = stats.linregress(xl, yl)
        print('r_value:'+str(r_value)) #debugging
        print('p_value:'+str(p_value)) #debugging
        print('std_err:'+str(std_err)) #debugging
        ylnew = lslope * xlnew + lintercept
        
        xr = self.etl_r_relation[:,0]
        yr = self.etl_r_relation[:,1]
        #Right linear regression
        xrnew = np.linspace(self.etl_r_relation[0,0], self.etl_r_relation[-1,0], 1000) #1000 points
        rslope, rintercept, r_value, p_value, std_err = stats.linregress(xr, yr)
        print('r_value:'+str(r_value)) #debugging
        print('p_value:'+str(p_value)) #debugging
        print('std_err:'+str(std_err)) #debugging
        yrnew = rslope * xrnew + rintercept
        
        '''Showing interpolation graph'''
        plt.figure(1)
        plt.title('ETL Focus Regression') 
        plt.xlabel('ETL Voltage (V)') 
        plt.ylabel('Focal Point Horizontal Position (column)')
        plt.plot(xl, yl, 'o', label='Left ETL') #Raw left data
        plt.plot(xlnew,ylnew) #Left regression
        plt.plot(xr, yr, 'o', label='Right ETL') #Raw right data
        plt.plot(xrnew,yrnew) #Right regression
        plt.legend()
        plt.show(block=False)   #Prevents the plot from blocking the execution of the code...
        
        #debugging
        for g in range(int(self.number_of_etls_points)):
            plt.figure(g+2)
            plt.plot(self.xdata[g],self.ydata[g],'.')
            plt.plot(self.xdata[g], func(self.xdata[g], *self.popt[g]), 'r-')
            plt.show(block=False)
        
    def updateUi_galvo_left_amplitude(self):
        # Propagate Ui changes to hardware instance
        self.siggen.galvo_left_amplitude = self.ui.doubleSpinBox_galvoLeftAmplitude.value()
        # Adjust Min and Max to prevent amplitude + offset being <-10V or > 10V
        self.ui.doubleSpinBox_galvoLeftOffset.setMinimum(-10 + self.ui.doubleSpinBox_galvoLeftAmplitude.value())
        self.ui.doubleSpinBox_galvoLeftOffset.setMaximum(10 - self.ui.doubleSpinBox_galvoLeftAmplitude.value())
        if self.ui.checkBox_galvoSync.isChecked():
            # Set opposite galvo amplitude and offset
            self.ui.doubleSpinBox_galvoRightAmplitude.setValue(self.ui.doubleSpinBox_galvoLeftAmplitude.value())
            self.ui.doubleSpinBox_galvoRightOffset.setValue(self.ui.doubleSpinBox_galvoLeftOffset.value())
            # Adjust Min and Max to prevent amplitude + offset being <-10V or > 10V
            self.ui.doubleSpinBox_galvoRightOffset.setMinimum(self.ui.doubleSpinBox_galvoLeftOffset.minimum())
            self.ui.doubleSpinBox_galvoRightOffset.setMaximum(self.ui.doubleSpinBox_galvoLeftOffset.maximum())
            # Propagate Ui changes to hardware instance
            self.siggen.galvo_right_amplitude = self.ui.doubleSpinBox_galvoRightAmplitude.value()
            self.siggen.galvo_right_offset = self.ui.doubleSpinBox_galvoRightOffset.value()

    def updateUi_galvo_right_amplitude(self):
        # Propagate Ui changes to hardware instance
        self.siggen.galvo_right_amplitude = self.ui.doubleSpinBox_galvoRightAmplitude.value()
        # Adjust Min and Max to prevent amplitude + offset being <-10V or > 10V
        self.ui.doubleSpinBox_galvoRightOffset.setMinimum(-10 + self.ui.doubleSpinBox_galvoRightAmplitude.value())
        self.ui.doubleSpinBox_galvoRightOffset.setMaximum(10 - self.ui.doubleSpinBox_galvoRightAmplitude.value())
        if self.ui.checkBox_galvoSync.isChecked():
            # Set opposite galvo amplitude and offset
            self.ui.doubleSpinBox_galvoLeftAmplitude.setValue(self.ui.doubleSpinBox_galvoRightAmplitude.value())
            self.ui.doubleSpinBox_galvoLeftOffset.setValue(self.ui.doubleSpinBox_galvoRightOffset.value())
            # Adjust Min and Max to prevent amplitude + offset being <-10V or > 10V
            self.ui.doubleSpinBox_galvoLeftOffset.setMinimum(self.ui.doubleSpinBox_galvoRightOffset.minimum())
            self.ui.doubleSpinBox_galvoLeftOffset.setMaximum(self.ui.doubleSpinBox_galvoRightOffset.maximum())
            # Propagate Ui changes to hardware instance
            self.siggen.galvo_left_amplitude = self.ui.doubleSpinBox_galvoLeftAmplitude.value()
            self.siggen.galvo_left_offset = self.ui.doubleSpinBox_galvoLeftOffset.value()

    def updateUi_galvo_left_offset(self):
        # Propagate Ui changes to hardware instance
        self.siggen.galvo_left_offset = self.ui.doubleSpinBox_galvoLeftOffset.value()
        if self.ui.checkBox_galvoSync.isChecked():
            # Set opposite galvo amplitude and offset
            self.ui.doubleSpinBox_galvoRightAmplitude.setValue(self.ui.doubleSpinBox_galvoLeftAmplitude.value())
            self.ui.doubleSpinBox_galvoRightOffset.setValue(self.ui.doubleSpinBox_galvoLeftOffset.value())
            self.ui.doubleSpinBox_galvoRightOffset.setMinimum(self.ui.doubleSpinBox_galvoLeftOffset.minimum())
            self.ui.doubleSpinBox_galvoRightOffset.setMaximum(self.ui.doubleSpinBox_galvoLeftOffset.maximum())
            # Propagate Ui changes to hardware instance
            self.siggen.galvo_right_amplitude = self.ui.doubleSpinBox_galvoRightAmplitude.value()
            self.siggen.galvo_right_offset = self.ui.doubleSpinBox_galvoRightOffset.value()

    def updateUi_galvo_right_offset(self):
        # Propagate Ui changes to hardware instance
        self.siggen.galvo_right_offset = self.ui.doubleSpinBox_galvoRightOffset.value()
        if self.ui.checkBox_galvoSync.isChecked():
            # Set opposite galvo amplitude and offset
            self.ui.doubleSpinBox_galvoLeftAmplitude.setValue(self.ui.doubleSpinBox_galvoRightAmplitude.value())
            self.ui.doubleSpinBox_galvoLeftOffset.setValue(self.ui.doubleSpinBox_galvoRightOffset.value())
            self.ui.doubleSpinBox_galvoLeftOffset.setMinimum(self.ui.doubleSpinBox_galvoRightOffset.minimum())
            self.ui.doubleSpinBox_galvoLeftOffset.setMaximum(self.ui.doubleSpinBox_galvoRightOffset.maximum())
            # Propagate Ui changes to hardware instance
            self.siggen.galvo_left_amplitude = self.ui.doubleSpinBox_galvoLeftAmplitude.value()
            self.siggen.galvo_left_offset = self.ui.doubleSpinBox_galvoLeftOffset.value()

    def updateUi_galvo_sync(self):
        if self.ui.checkBox_galvoSync.isChecked():
            # Set left galvo amplitude and offset to right galvo
            self.ui.doubleSpinBox_galvoRightAmplitude.setValue(self.ui.doubleSpinBox_galvoLeftAmplitude.value())
            self.ui.doubleSpinBox_galvoRightOffset.setValue(self.ui.doubleSpinBox_galvoLeftOffset.value())
            self.ui.doubleSpinBox_galvoRightOffset.setMinimum(self.ui.doubleSpinBox_galvoLeftOffset.minimum())
            self.ui.doubleSpinBox_galvoRightOffset.setMaximum(self.ui.doubleSpinBox_galvoLeftOffset.maximum())
            # Propagate Ui changes to hardware instance
            self.siggen.galvo_right_amplitude = self.ui.doubleSpinBox_galvoRightAmplitude.value()
            self.siggen.galvo_right_offset = self.ui.doubleSpinBox_galvoRightOffset.value()

    def updateUi_galvo_activate(self):
        # Propagate Ui changes to hardware instance
        self.siggen.galvo_activated = self.ui.checkBox_galvoActivate.isChecked()

    def updateUi_galvo_invert(self):
        # Propagate Ui changes to hardware instance
        self.siggen.galvo_inverted = self.ui.checkBox_galvoInvert.isChecked()

    def updateUi_etl_left_amplitude(self):
        # Propagate Ui changes to hardware instance
        self.siggen.etl_left_amplitude = self.ui.doubleSpinBox_etlLeftAmplitude.value()
        # Adjust Min and Max to prevent amplitude + offset being <-5V or > 5V
        self.ui.doubleSpinBox_etlLeftOffset.setMinimum(-5 + self.ui.doubleSpinBox_etlLeftAmplitude.value())
        self.ui.doubleSpinBox_etlLeftOffset.setMaximum(5 - self.ui.doubleSpinBox_etlLeftAmplitude.value()) 
        if self.ui.checkBox_etlSync.isChecked():
            # Set opposite etl amplitude and offset
            self.ui.doubleSpinBox_etlRightAmplitude.setValue(self.ui.doubleSpinBox_etlLeftAmplitude.value())
            self.ui.doubleSpinBox_etlRightOffset.setValue(self.ui.doubleSpinBox_etlLeftOffset.value())
            # Adjust Min and Max to prevent amplitude + offset being <-5V or > 5V
            self.ui.doubleSpinBox_etlRightOffset.setMinimum(self.ui.doubleSpinBox_etlLeftOffset.minimum())
            self.ui.doubleSpinBox_etlRightOffset.setMaximum(self.ui.doubleSpinBox_etlLeftOffset.maximum())
            # Propagate Ui changes to hardware instance
            self.siggen.etl_right_amplitude = self.ui.doubleSpinBox_etlRightAmplitude.value()
            self.siggen.etl_right_offset = self.ui.doubleSpinBox_etlRightOffset.value()

    def updateUi_etl_right_amplitude(self):
        # Propagate Ui changes to hardware instance
        self.siggen.etl_right_amplitude = self.ui.doubleSpinBox_etlRightAmplitude.value()
        # Adjust Min and Max to prevent amplitude + offset being <-5V or > 5V
        self.ui.doubleSpinBox_etlRightOffset.setMinimum(-5 + self.ui.doubleSpinBox_etlRightAmplitude.value())
        self.ui.doubleSpinBox_etlRightOffset.setMaximum(5 - self.ui.doubleSpinBox_etlRightAmplitude.value()) 
        if self.ui.checkBox_etlSync.isChecked():
            # Set opposite etl amplitude and offset
            self.ui.doubleSpinBox_etlLeftAmplitude.setValue(self.ui.doubleSpinBox_etlRightAmplitude.value())
            self.ui.doubleSpinBox_etlLeftOffset.setValue(self.ui.doubleSpinBox_etlRightOffset.value())
            # Adjust Min and Max to prevent amplitude + offset being <-5V or > 5V
            self.ui.doubleSpinBox_etlLeftOffset.setMinimum(self.ui.doubleSpinBox_etlRightOffset.minimum())
            self.ui.doubleSpinBox_etlLeftOffset.setMaximum(self.ui.doubleSpinBox_etlRightOffset.maximum()) 
            # Propagate Ui changes to hardware instance
            self.siggen.etl_left_amplitude = self.ui.doubleSpinBox_etlLeftAmplitude.value()
            self.siggen.etl_left_offset = self.ui.doubleSpinBox_etlLeftOffset.value()

    def updateUi_etl_left_offset(self):
        # Propagate Ui changes to hardware instance
        self.siggen.etl_left_offset = self.ui.doubleSpinBox_etlLeftOffset.value()
        if self.ui.checkBox_etlSync.isChecked():
            self.ui.doubleSpinBox_etlRightAmplitude.setValue(self.ui.doubleSpinBox_etlLeftAmplitude.value())
            self.ui.doubleSpinBox_etlRightOffset.setValue(self.ui.doubleSpinBox_etlLeftOffset.value())
            self.ui.doubleSpinBox_etlRightOffset.setMinimum(self.ui.doubleSpinBox_etlLeftOffset.minimum())
            self.ui.doubleSpinBox_etlRightOffset.setMaximum(self.ui.doubleSpinBox_etlLeftOffset.maximum())
            # Propagate Ui changes to hardware instance
            self.siggen.etl_right_amplitude = self.ui.doubleSpinBox_etlRightAmplitude.value()
            self.siggen.etl_right_offset = self.ui.doubleSpinBox_etlRightOffset.value()

    def updateUi_etl_right_offset(self):
        # Propagate Ui changes to hardware instance
        self.siggen.etl_right_offset = self.ui.doubleSpinBox_etlRightOffset.value()
        if self.ui.checkBox_etlSync.isChecked():
            self.ui.doubleSpinBox_etlLeftAmplitude.setValue(self.ui.doubleSpinBox_etlRightAmplitude.value())
            self.ui.doubleSpinBox_etlLeftOffset.setValue(self.ui.doubleSpinBox_etlRightOffset.value())
            self.ui.doubleSpinBox_etlLeftOffset.setMinimum(self.ui.doubleSpinBox_etlRightOffset.minimum())
            self.ui.doubleSpinBox_etlLeftOffset.setMaximum(self.ui.doubleSpinBox_etlRightOffset.maximum()) 
            # Propagate Ui changes to hardware instance
            self.siggen.etl_left_amplitude = self.ui.doubleSpinBox_etlLeftAmplitude.value()
            self.siggen.etl_left_offset = self.ui.doubleSpinBox_etlLeftOffset.value()

    def updateUi_etl_sync(self):
        # Propagate Ui changes to hardware instance
        if self.ui.checkBox_etlSync.isChecked():
            self.ui.doubleSpinBox_etlRightAmplitude.setValue(self.ui.doubleSpinBox_etlLeftAmplitude.value())
            self.ui.doubleSpinBox_etlRightOffset.setValue(self.ui.doubleSpinBox_etlLeftOffset.value())
            self.ui.doubleSpinBox_etlRightOffset.setMinimum(self.ui.doubleSpinBox_etlLeftOffset.minimum())
            self.ui.doubleSpinBox_etlRightOffset.setMaximum(self.ui.doubleSpinBox_etlLeftOffset.maximum())
            # Propagate Ui changes to hardware instance
            self.siggen.etl_right_amplitude = self.ui.doubleSpinBox_etlRightAmplitude.value()
            self.siggen.etl_right_offset = self.ui.doubleSpinBox_etlRightOffset.value()

    def updateUi_etl_steps(self):
        # Propagate Ui changes to hardware instance
        self.siggen.etl_steps = int(self.ui.doubleSpinBox_etlSteps.value())

    def updateUi_etl_activate(self):
        # Propagate Ui changes to hardware instance
        self.siggen.etl_activated = self.ui.checkBox_etlActivate.isChecked()

    def updateUi_acq_sample_rate(self):
        # Propagate Ui changes to hardware instance
        self.siggen.sample_rate = self.ui.doubleSpinBox_acqSampleRate.value()

    def updateUi_acq_exposure_time(self):
        # Propagate Ui changes to hardware instance
        self.camera.exposure_time = self.ui.doubleSpinBox_acqExposureTime.value() * 1e-3  # ui(ms) to camera(s)

    def updateUi_acq_line_time(self):
        # Propagate Ui changes to Camera instance
        self.camera.lightsheet_line_time = self.ui.doubleSpinBox_acqLineTime.value() * 1e-6 # ui(us) to camera(s)

    def updateUi_acq_line_exposure(self):
        # Propagate Ui changes to Camera instance
        self.camera.lightsheet_exposed_lines = int(self.ui.doubleSpinBox_acqLineExposure.value())

    def updateUi_acq_line_delay(self):
        # Propagate Ui changes to Camera instance
        self.camera.lightsheet_delay_lines = int(self.ui.doubleSpinBox_acqLineDelay.value())


    def updateUi_laser1_amplitude(self):
        # Propagate Ui changes to hardware instance
        self.lasers.laser1_power = self.ui.doubleSpinBox_laserOneAmplitude.value()

    def updateUi_laser2_amplitude(self):
        # Propagate Ui changes to hardware instance
        self.lasers.laser2_power = self.ui.doubleSpinBox_laserTwoAmplitude.value()

    def laser1_toggle_button(self):
        self.lasers.laser1_toggle()
            
    def laser2_toggle_button(self):
        self.lasers.laser2_toggle()

    def start_lasers(self):
        '''Starts the lasers at a certain voltage'''
        if self.ui.checkBox_laserOneAutomatic.isChecked:
            self.lasers.laser1_on
        if self.ui.checkBox_laserTwoAutomatic.isChecked:
            self.lasers.laser2_on

    def stop_lasers(self):
        '''Stops the lasers, puts their voltage to zero'''
        if self.ui.checkBox_laserOneAutomatic.isChecked:
            self.lasers.laser1_off
        if self.ui.checkBox_laserTwoAutomatic.isChecked:
            self.lasers.laser2_off
 
    '''File Open Methods'''
        
    def updateUi_select_file(self):
        '''Allows the selection of a file (.hdf5), opens it and displays its datasets'''
        
        '''Retrieve File'''
        self.open_directory = QFileDialog.getOpenFileName(self, 'Choose File', '', 'Hierarchical files (*.hdf5)')[0]
        
        if self.open_directory != '': #If file directory specified
            self.ui.label_currentFileDirectory.setText(self.open_directory)
            self.ui.listWidget_fileDatasets.clear()
            
            '''Open the file and display its datasets'''
            with h5py.File(self.open_directory, "r") as f:
                dataset_names = list(f.keys())
                for item in range(len(dataset_names)):
                    self.ui.listWidget_fileDatasets.insertItem(item,dataset_names[item])
            self.ui.listWidget_fileDatasets.setCurrentRow(0)
            self.updateUi_message_printer('File ' + self.open_directory + ' opened')
            self.ui.pushButton_selectDataset.setEnabled(True)
        else:
            self.ui.label_currentFileDirectory.setText('None Specified')
    
    def updateUi_select_dataset(self):
        """
        Opens one or many HDF5 datasets and displays its attributes and data as an image
        """
        if (self.open_directory != '') and (self.ui.listWidget_fileDatasets.count() != 0):
            for item in range(len(self.ui.listWidget_fileDatasets.selectedItems())):
                self.dataset_name = self.ui.listWidget_fileDatasets.selectedItems()[item].text()
                with h5py.File(self.open_directory, "r") as f:
                    dataset = f[self.dataset_name]
                    
                    # Display attributes of the first selected dataset
                    if item == 0:
                        self.ui.label_currentDataset.setText(self.dataset_name)
                        attribute_names = list(dataset.attrs.keys())
                        attribute_values = list(dataset.attrs.values())
                        self.ui.tableWidget_fileAttributes.setColumnCount(2)
                        self.ui.tableWidget_fileAttributes.setRowCount(len(attribute_names))
                        self.ui.tableWidget_fileAttributes.setHorizontalHeaderItem(0,QTableWidgetItem('Attributes'))
                        self.ui.tableWidget_fileAttributes.setHorizontalHeaderItem(1,QTableWidgetItem('Values'))
                        for attribute in range(0,len(attribute_names)):
                            self.ui.tableWidget_fileAttributes.setItem(attribute,0,QTableWidgetItem(attribute_names[attribute]))
                            self.ui.tableWidget_fileAttributes.setItem(attribute,1,QTableWidgetItem(str(attribute_values[attribute])))
                        self.ui.tableWidget_fileAttributes.resizeColumnsToContents()
                        self.ui.tableWidget_fileAttributes.setEditTriggers(QAbstractItemView.NoEditTriggers) #No editing possible
                    
                    # Display image
                    data = dataset[()]
                    plt.figure(self.open_directory + ' (' + self.dataset_name + ')')
                    plt.imshow(data,cmap = 'gray')
                    plt.show(block = False)   #Prevents the plot from blocking the execution of the code...
                    
                    ##'''Convert to tiff format'''
                    ## tiff = Image.fromarray(data)
                    ##tiff_filename = self.open_directory.replace('.hdf5', '.tiff')
                    ##tiff.save(tiff_filename)
                
                self.updateUi_message_printer('Dataset ' + self.dataset_name + ' of file ' + self.open_directory + ' displayed')


    def updateUi_preview_mode_button(self):
        '''Start or stop preview mode, depending on the button status'''
        if self.preview_mode_started:
            self.preview_mode_started = False
            self.preview_mode_thread.join()
            self.ui.pushButton_acqStartPreviewMode.setText('Start Preview Mode')
#            self.updateUi_laser_buttons()
        else:
            self.close_modes()
            self.preview_mode_started = True
            self.ui.pushButton_acqStartPreviewMode.setText('Stop Preview Mode')
#            self.updateUi_laser_buttons(False)

            # updating ui before starting preview mode thread
            self.updateUi_modes_buttons([self.ui.pushButton_acqStartPreviewMode])
            self.updateUi_message_printer('->Preview mode started')
            self.ui.statusBar_label.setText('Current Acquisition Mode: Preview ')
            self.ui.statusBar_progress.setValue(100)
            self.ui.statusBar_progress.show()

            # Starting preview mode thread
            self.preview_mode_thread = threading.Thread(target = self.preview_mode_worker)
            self.preview_mode_thread.start()
            
    @pyqtSlot()
    def updateUi_post_preview_mode(self):
        # updating ui after preview mode thread has completed
        self.updateUi_modes_buttons(self.default_buttons)
        self.updateUi_message_printer('->Preview mode stopped')
        self.ui.statusBar_label.setText('')
        self.ui.statusBar_progress.setValue(0)
        self.ui.statusBar_progress.hide()
    
    def preview_mode_worker(self):
        '''This thread allows the visualization and manual control of the 
           parameters of the beams in the UI. There is no scan here, 
           beams only changes when parameters are changed. This the preferred 
           mode for beam calibration'''
       
        # Setting the camera for self triggered acquisition
        self.camera.set_trigger_mode('auto_trigger')
        self.camera.set_exposure_time(self.ui.doubleSpinBox_acqExposureTime)
        self.camera.arm()

        while self.preview_mode_started:
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
        
        # Emit finished signal
        self.sig_preview_mode_finished.emit()


    def updateUi_live_mode_button(self):
        '''Start or stop live mode, depending on the button status'''
        if self.live_mode_started:
            self.live_mode_started = False
            self.live_mode_thread.join()
            self.ui.pushButton_acqStartLiveMode.setText('Start Live Mode')
#            self.updateUi_laser_buttons()
        else:
            self.close_modes()
            self.live_mode_started = True
            self.ui.pushButton_acqStartLiveMode.setText('Stop Live Mode')
#            self.updateUi_laser_buttons(False)
            # updating ui before starting live mode thread
            self.updateUi_modes_buttons([self.ui.pushButton_acqStartLiveMode])
            self.updateUi_message_printer('->Live mode started')
            self.ui.statusBar_label.setText('Current Acquisition Mode: Live ')
            self.ui.statusBar_progress.setValue(100)
            self.ui.statusBar_progress.show()

            # Starting live mode thread
            self.live_mode_thread = threading.Thread(target = self.live_mode_worker)
            self.live_mode_thread.start()

    @pyqtSlot()
    def updateUi_post_live_mode(self):
        # updating ui after live mode thread has completed
        self.updateUi_modes_buttons(self.default_buttons)
        self.updateUi_message_printer('->Live mode stopped')
        self.ui.statusBar_label.setText('')
        self.ui.statusBar_progress.setValue(0)
        self.ui.statusBar_progress.hide()

    def live_mode_worker(self):
        '''This thread allows the execution of scan_mode while modifying
           parameters in the UI'''

        '''Moving the camera to focus'''
        ##self.move_camera_to_focus() 

#        # Setting the camera for scan acquisition
#        self.camera.arm_scan()
        
        # Starting lasers
        self.start_lasers()
        
        while self.live_mode_started:
            # Setting the camera for scan acquisition
            self.camera.arm_scan()

            # Refresh scan waveforms every loop (live mode)
            self.siggen.compute_scan_waveforms()
            # Get single image
            self.acquire_scan()
        
        # Put ETLs in standby mode: 2.5V corresponds no current through coil (mid 0-5V adjustable range)
        self.siggen.update_etls(left_etl=2.5, right_etl=2.5)

        # Stopping lasers
        self.stop_lasers()

        # Stopping camera
        self.camera.disarm()

        # Emit finished signal
        self.sig_live_mode_finished.emit()


    def updateUi_single_mode_button(self):
        '''Acquire a single image '''
        if not self.single_mode_started:
            self.close_modes()

            self.single_mode_started = True
            # Disabling modes while single frame acquisition
            self.ui.pushButton_acqGetSingleImage.setText('Acquiring...')
            self.updateUi_modes_buttons([self.ui.pushButton_acqGetSingleImage])
            self.updateUi_message_printer('->Getting single image')

            # Starting single image thread
            self.single_mode_thread = threading.Thread(target = self.single_mode_worker)
            self.single_mode_thread.start()


    @pyqtSlot()
    def updateUi_post_single_mode(self):
        # Re-enabling modes after single frame acquisition
        self.single_mode_started = False
        self.ui.pushButton_acqGetSingleImage.setText('Get Single Image')
        self.default_buttons.append(self.ui.pushButton_saveCurrentImage)
        self.updateUi_modes_buttons(self.default_buttons)


    def single_mode_worker(self):
        '''Generates and display a single scan which can be saved afterwards'''
        
        # Moving the camera to focus
        ##self.move_camera_to_focus()
        
        # Getting positions for the image
        self.image_hor_pos_text = self.current_horizontal_position_text
        self.image_ver_pos_text = self.current_vertical_position_text
        self.image_cam_pos_text = self.current_camera_position_text
        
        # Setting the camera for scan acquisition
        self.camera.arm_scan()

        # Start lasers
        self.both_lasers_activated = True
        self.start_lasers()
        
        # Refresh scan waveforms with current settings
        self.siggen.compute_scan_waveforms()
        # Acquire a single scan
        self.acquire_scan()

        # Put ETLs in standby mode
        # 2.5V corresponds no current through coil (mid 0-5V adjustable range)
        self.siggen.update_etls(left_etl=2.5, right_etl=2.5)

        # Stop lasers
        self.stop_lasers()
        self.both_lasers_activated = False

        # Stop camera            
        self.camera.disarm()

        # Emit finished signal
        self.sig_single_mode_finished.emit()


    def crop_buffer(self, buffer):
        '''Crops each frame of a buffer with 20% frame-to-frame overlap'''
      
        image_xsize = buffer.shape[2]
        image_ysize = buffer.shape[1]
        tile_count = buffer.shape[0]

        if tile_count == 1:
            cropped_buffer = buffer
        else:
            tile_width = int(image_xsize/tile_count)
            tile_width_overlap = int(tile_width*0.2)

            #Initializing empty cropped buffer
            cropped_buffer = np.zeros((tile_count, image_ysize, tile_width + (2*tile_width_overlap)), np.uint16)
   
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
                next_first_column = int(first_column + tile_width + (2*tile_width_overlap))
                if frame == 0:  #For the first column step
                    cropped_buffer[frame,:,tile_width_overlap:] = buffer[frame,:,0:tile_width + tile_width_overlap]
                elif frame == tile_count-1:  #For the last column step (may be different than the others...)
                    last_column_step = int(image_xsize - first_column)
                    cropped_buffer[frame,:,0:last_column_step] = buffer[frame,:,first_column:]
                else:
                    cropped_buffer[frame,:,:] = buffer[frame,:,first_column:next_first_column]
        return cropped_buffer


    def reconstruct_frame(self, buffer):
        '''Reconstructs frame from buffer'''
    
        image_xsize = buffer.shape[2]
        image_ysize = buffer.shape[1]
        tile_count = buffer.shape[0]

        #Initializing empty frame
        reconstructed_frame = np.zeros((image_ysize, image_xsize), np.uint16)

        # Crops each frame of a buffer with no overlap and merge
        if tile_count == 1:
            reconstructed_frame = buffer[0,:,:]
        else:
            tile_width = int(image_xsize/tile_count)

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
                if frame == tile_count-1:  #For the last column step (may be different than the others...)
                    reconstructed_frame[:,first_column:] = buffer[frame,:,first_column:]
                else:
                    reconstructed_frame[:,first_column:next_first_column] = buffer[frame,:,first_column:next_first_column]
        return reconstructed_frame


    def reconstruct_frame_linear_blend(self, buffer):
        '''Reconstructs frame from buffer using linear blend over 20% overlap'''

        image_xsize = buffer.shape[2]
        image_ysize = buffer.shape[1]
        tile_count = buffer.shape[0]

        # Initializing empty output frame
        reconstructed_frame = np.zeros((image_ysize, image_xsize), np.uint16)

        if tile_count == 1:
            reconstructed_frame = buffer[0,:,:]
        else:
            # Crops each frame of a buffer with 20% overlap for futher frame reconstruction
            tile_width = int(image_xsize/tile_count)
            tile_width_overlap = int(tile_width*0.2)

            # Initializing empty cropped buffer
            cropped_buffer = np.zeros((tile_count, image_ysize, tile_width + (2*tile_width_overlap)), np.uint16)
   
            # Crop with overlap
            for frame in range(tile_count):
                first_column = int(frame * tile_width - tile_width_overlap)
                next_first_column = int(first_column + tile_width + (2*tile_width_overlap))
                if frame == 0:  #For the first column step
                    cropped_buffer[frame,:,tile_width_overlap:] = buffer[frame,:,0:tile_width + tile_width_overlap]
                elif frame == tile_count-1:  #For the last column step (may be different than the others...)
                    last_column_step = int(image_xsize - first_column)
                    cropped_buffer[frame,:,0:last_column_step] = buffer[frame,:,first_column:]
                else:
                    cropped_buffer[frame,:,:] = buffer[frame,:,first_column:next_first_column]

            # Reconstruct frame with linear blend for overlapping region
            weight_step = 1/(2*tile_width_overlap)

            for frame in range(tile_count):
                first_center_column = int(frame * tile_width + tile_width_overlap)
                last_center_column = int((frame+1) * tile_width - tile_width_overlap)
                previous_last_center_column = int(frame * tile_width - tile_width_overlap)
                
                if frame == 0:  #For the first column step
                    reconstructed_frame[:,0:last_center_column] = cropped_buffer[frame,:,tile_width_overlap:tile_width]
                else:
                    for column in range(2*tile_width_overlap):
                        frame_column = column + previous_last_center_column
                        last_buffer_column = column + tile_width
                        buffer_weight = column * weight_step
                        last_buffer_weight = 1 - column * weight_step
                        reconstructed_frame[:,frame_column] = buffer_weight*cropped_buffer[frame,:,column] + last_buffer_weight*cropped_buffer[(frame-1),:,last_buffer_column]
                    if frame == tile_count-1:  #For the last column step (may be different than the others...)
                        last_column_step = int(image_xsize - first_center_column)
                        reconstructed_frame[:,first_center_column:] = cropped_buffer[frame,:,(2*tile_width_overlap):(2*tile_width_overlap)+last_column_step]
                    else:
                        reconstructed_frame[:,first_center_column:last_center_column] = cropped_buffer[frame,:,(2*tile_width_overlap):tile_width]
        return reconstructed_frame


    def acquire_scan(self):
        """
        Generate scan tasks using previously computed waveforms and acquire a single reconstructed frame
        """

        # TODO - thread lock siggen and camera while we acquire

        # Store metadata about buffer to be acquired
        self.buffer_metadata_general = {}
        self.buffer_metadata_general['Date']  = str(datetime.date.today())
        self.buffer_metadata_general['Sample Name']  = str(self.ui.lineEdit_saveDescription.text())

        self.buffer_metadata_waveforms = {}
        self.buffer_metadata_waveforms = self.siggen.waveform_metadata

        # TODO - motors and lasers and camera (?) metadata
        self.buffer_metadata_motors = {}
        self.buffer_metadata_lasers = {}
        self.buffer_metadata_camera = {}

        # self.buffer_metadata['Horizontal Position']  = self.motors.horizontal.get_position('mm')
        # self.buffer_metadata['Vertical Position']  = self.motors.vertical.get_position('mm')
        # self.buffer_metadata['Camera Position']  = self.motors.camera.get_position('mm')

        # Number of images to be acquired from the camera
        number_of_images = self.siggen.waveform_cycles

        # Creating acquisition tasks
        self.siggen.create_scanner()

        # Prime the camera recorder before we start the acquisition taks
        self.camera.start_recorder(number_of_images)
        self.siggen.start_scanner()

        # Monitor completion of acquisition tasks and camera recorder
        self.camera.monitor_recorder(number_of_images)
        self.siggen.monitor_scanner()

        # Stop tasks and recorder
        self.camera.stop_recorder()
        self.siggen.stop_scanner()                             

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


    def updateUi_select_directory(self):
        '''Allows the selection of a directory for single scan or stack saving'''
        options = QFileDialog.Options()
        options |= QFileDialog.DontResolveSymlinks
        options |= QFileDialog.ShowDirsOnly
        tmp_directory = QFileDialog.getExistingDirectory(self, 'Choose Directory', self.save_directory, options)
        if tmp_directory != '':
            self.save_directory = os.path.normpath(tmp_directory)

        if self.save_directory != '':
            self.ui.lineEdit_saveDirectory.setText(self.save_directory)
            self.ui.lineEdit_saveFilename.setText('')
            self.ui.lineEdit_saveFilename.setEnabled(True)
            self.ui.lineEdit_saveDescription.setText('')
            self.ui.lineEdit_saveDescription.setEnabled(True)
        else:
            self.ui.lineEdit_saveDirectory.setText('')
            self.ui.lineEdit_saveFilename.setText('Filename - Select Save Directory First')
            self.ui.lineEdit_saveFilename.setEnabled(False)
            self.ui.lineEdit_saveDescription.setText('Description - Select Save Directory First')
            self.ui.lineEdit_saveDescription.setEnabled(False)


    def validate_file_name(self):
        """
        Validate filename set by the user
        """
        # To validate individual char. Only alphanumeric, - and _ characters are permitted
        def safe_char(c):
            if c.isalnum() or c == '-':
                return c
            else:
                return '_'

        #TODO
        # Check that save path exists

        tmp_string = self.ui.lineEdit_saveFilename.text()
        tmp_string = ''.join(safe_char(c) for c in tmp_string).rstrip("_")

        if tmp_string != '':
            self.save_filename = tmp_string

        if (self.save_directory != '') and (self.save_filename != ''):
            self.save_filename = os.path.normpath(self.save_directory + '\\' + self.save_filename)
            self.saving_allowed = True
        else:
            self.saving_allowed = False
    
    
    def updateUi_save_single_image(self):
        '''Saves the frame generated by self.get_single_image()'''
        
        # Check that filename is valid and saving is allowed
        self.validate_file_name()
        
        if self.saving_allowed:
            # Getting sample name
            self.save_description = str(self.ui.lineEdit_saveDescription.text())

            '''Setting up frame saver'''
            self.frame_saver.reinit(1)
            self.frame_saver.add_sample_name(self.save_description)
            self.frame_saver.add_motor_parameters(self.image_hor_pos_text, self.image_ver_pos_text, self.image_cam_pos_text)
            
            '''Saving frame'''
            if self.ui.checkBox_saveAllCrop.isChecked():
                self.frame_saver.set_files(1,self.save_filename,'singleImage',1,'ETLscan')
                cropped_buffer = self.crop_buffer(self.buffer)
                self.frame_saver.enqueue_buffer(cropped_buffer)
                self.updateUi_message_printer('Saving Images (one for each ETL scan, cropped)')
            elif self.ui.checkBox_saveAllFull.isChecked():
                self.frame_saver.set_files(1,self.save_filename,'singleImage',1,'FullETLscan')
                self.frame_saver.enqueue_buffer(self.buffer)
                self.updateUi_message_printer('Saving Images (one for each ETL scan, full)')
            else:
                self.frame_saver.set_files(1,self.save_filename,'singleImage',1,'reconstructed_frame')
                self.frame_saver.enqueue_buffer(self.reconstructed_frame)
                self.updateUi_message_printer('Saving Reconstructed Image')
            
            self.frame_saver.start_saving()
            self.frame_saver.stop_saving()
        else:
            self.sig_beep.emit()
            QMessageBox.warning(self, "Save Warning", "Select a directory and enter a valid filename before saving", QMessageBox.Ok, QMessageBox.Ok)
            print('Select a directory and enter a valid filename before saving')

    def updateUi_set_stack_mode_starting_point(self):
        '''Defines the starting point where the first plane of the stack volume will be recorded'''
        self.stack_starting_plane = self.motors.horizontal.get_position('\u03BCm') #Units in micro-meters, because plane step is in micro-meters
        self.ui.checkBox_acqFirstPlaneSet.setChecked(True)
        self.updateUi_set_number_of_planes()

    def updateUi_set_stack_mode_ending_point(self):
        '''Defines the ending point of the recorded stack volume'''
        self.stack_ending_plane = self.motors.horizontal.get_position('\u03BCm') #Units in micro-meters, because plane step is in micro-meters
        self.ui.checkBox_acqLastPlaneSet.setChecked(True)
        self.updateUi_set_number_of_planes()
    
    def updateUi_set_number_of_planes(self):
        '''Calculates the number of planes that will be saved in the stack acquisition'''
        if self.ui.doubleSpinBox_acqPlaneStepSize.value() != 0:
            if self.ui.checkBox_acqFirstPlaneSet.isChecked() and self.ui.checkBox_acqLastPlaneSet.isChecked():
                self.number_of_planes = np.ceil(abs((self.stack_ending_plane-self.stack_starting_plane)/self.ui.doubleSpinBox_acqPlaneStepSize.value()))
                self.number_of_planes += 1   #Takes into account the initial plane
                self.ui.label_acqNumberOfPlanes.setText(str(self.number_of_planes))
        else:
            print('Set a non-zero value to plane step')

    def updateUi_stack_mode_button(self):
        '''Start or stop stack mode, depending on the button status'''
        if self.stack_mode_started:
            self.stack_mode_started = False
            self.stack_mode_thread.join()
        else:
            self.close_modes()
            '''Making sure the limits of the volume are set'''
            if (self.ui.checkBox_acqFirstPlaneSet.isChecked() == False) or (self.ui.checkBox_acqLastPlaneSet.isChecked() == False) or (self.ui.doubleSpinBox_acqPlaneStepSize.value() == 0):
                print('Set starting and ending points and select a non-zero plane step value')
                self.sig_beep.emit()
                QMessageBox.warning(self, "Stack Acquisition Warning", "Set starting and ending points and select a non-zero plane step value", QMessageBox.Ok, QMessageBox.Ok)
            else:
                # Setting stack step size sign (taking into account the direction of acquisition)
                if self.stack_starting_plane > self.stack_ending_plane:
                    self.stack_step = -1 * self.ui.doubleSpinBox_acqPlaneStepSize.value()
                else:
                    self.stack_step = self.ui.doubleSpinBox_acqPlaneStepSize.value()
                
                # Check that filename is valid and saving is allowed
                self.validate_file_name()

                if not self.saving_allowed:
                    self.sig_beep.emit()
                    nosave_answer = QMessageBox.question(self, "Stack Acquisition Question", "Make stack acquisition without saving ?", QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)

                if self.saving_allowed or nosave_answer:
                    self.ui.pushButton_acqStartStackMode.setText('Stop Stack Mode')
                    self.ui.statusBar_label.setText('Current Acquisition Mode: Stack ')
                    self.ui.statusBar_progress.setValue(0) #To reset progress bar
                    self.ui.statusBar_progress.show()
                    self.stack_mode_started = True

                    '''Modes disabling while stack acquisition'''
                    self.updateUi_modes_buttons([self.ui.pushButton_acqStartStackMode])
                    self.updateUi_motor_buttons()
                    self.updateUi_message_printer('->Stack mode started -- Number of frames to save: ' + str(int(self.number_of_planes)))

                    '''Starting stack mode thread'''
                    self.stack_mode_thread = threading.Thread(target = self.stack_mode_worker)
                    self.stack_mode_thread.start()

    @pyqtSlot()
    def updateUi_post_stack_mode(self):
        '''Enabling modes after stack mode'''
        self.ui.pushButton_acqStartStackMode.setText('Start Stack Mode')
        self.updateUi_modes_buttons(self.default_buttons)
        self.updateUi_motor_buttons(disable_button=False)
        
        self.stack_mode_started = False
        self.updateUi_message_printer('->Stack Mode Acquisition Done')
        self.ui.statusBar_label.setText('')
        self.ui.statusBar_progress.hide()

    def stack_mode_worker(self):
        ''' Thread for volume acquisition and saving'''

        # Making sure saving is allowed and filename isn't empty
        if self.saving_allowed:
            # Getting sample name
            self.save_description = str(self.ui.lineEdit_saveDescription.text())

            # Setting frame saver
            self.frame_saver.reinit(3)
            self.frame_saver.add_sample_name(self.save_description)
            if self.ui.checkBox_saveAllCrop.isChecked():
                self.frame_saver.set_files(self.number_of_planes, self.save_filename, 'stack', 1, 'ETLscan')
            elif self.ui.checkBox_saveAllFull.isChecked():
                self.frame_saver.set_files(self.number_of_planes, self.save_filename, 'stack', 1, 'FullETLscan')             
            else:
                self.frame_saver.set_files(1, self.save_filename, 'stack', self.number_of_planes, 'reconstructed_frame')
            # Starting frame saver
            self.frame_saver.start_saving()

        # Setting the camera for scan acquisition
        self.camera.arm_scan()
        
        # Starting lasers
        self.both_lasers_activated = True
        self.start_lasers()

        # Set progress bar
        progress_value = 0
        progress_increment = 100/self.number_of_planes
        self.sig_progress_update.emit(0) #To reset progress bar

        # Compute scan waveforms only once before we start the stack acquisition       
        # Changes to settings won't be effective until we stop/restart mode 
        self.siggen.compute_scan_waveforms()

        for plane in range(int(self.number_of_planes)):
            if self.stack_mode_started == False:
                self.sig_message.emit('Stack Acquisition Interrupted')
                break
            else:
                '''Moving sample position'''
                position = self.stack_starting_plane + (plane * self.stack_step)
                self.motors.horizontal.move_absolute_position(position,'\u03BCm')  #Position in micro-meters
                #FIXME - updating ui within secondary thread
                self.updateUi_position_horizontal()

                '''Moving the camera to focus'''
                #FIXME - Add focus adjustement to stack mode
                #self.calculate_camera_focus()
                #self.move_camera_to_focus()
                
                if self.saving_allowed:
                    self.frame_saver.add_motor_parameters(self.current_horizontal_position_text, self.current_vertical_position_text, self.current_camera_position_text)
                
                '''Getting image'''
                self.acquire_scan()
                
                '''Saving frame'''
                if self.saving_allowed:
                    if self.ui.checkBox_saveAllCrop.isChecked():
                        cropped_buffer = self.crop_buffer(self.buffer)
                        self.frame_saver.enqueue_buffer(cropped_buffer)
                        self.sig_message.emit('Saving All Images (one for each ETL step, cropped)')
                    elif self.ui.checkBox_saveAllFull.isChecked():
                        self.frame_saver.enqueue_buffer(self.buffer)
                        self.sig_message.emit('Saving All Images (one for each ETL step, full)')                 
                    else:
                        self.frame_saver.enqueue_buffer(self.reconstructed_frame)
                        self.sig_message.emit('Saving Reconstructed Image')
                
                '''Update progress bar'''
                progress_value += progress_increment
                self.sig_progress_update.emit(int(progress_value))

        if self.stack_mode_started:
            self.sig_progress_update.emit(100) #In case the number of planes is not a multiple of 100

        if self.saving_allowed:
            self.frame_saver.stop_saving()
        
        # Put ETLs in standby mode: 2.5V corresponds no current through coil (mid 0-5V adjustable range)
        self.siggen.update_etls(left_etl=2.5, right_etl=2.5)
       
        # Stopping laser
        self.stop_lasers()
        self.both_lasers_activated = False

        # Stopping camera
        self.camera.disarm()

        # Stack mode finished
        self.sig_stack_mode_finished.emit()


    '''Calibration Methods'''
    def camera_calibration_button(self):
        '''Start or stop camera calibration, depending on the button status'''
        if self.camera_calibration_started:
            self.camera_calibration_started = False
            self.calibrate_camera_thread.join()
        else:
            self.close_modes()
            self.camera_calibration_started = True
            self.ui.pushButton_calCameraStartCalibration.setText('Stop Camera Calibration')
            self.updateUi_motor_buttons()
            self.start_calibrate_camera()
    
    def start_calibrate_camera(self):
        '''Initiates camera calibration'''
       
        '''Modes disabling while stack acquisition'''
        self.updateUi_modes_buttons([self.ui.pushButton_calCameraStartCalibration])
            
        self.updateUi_message_printer('Camera calibration started')
        self.ui.statusBar_label.setText('Current Mode: Camera Calibration ')
        self.ui.statusBar_progress.show()
            
        '''Starting camera calibration thread'''
        self.calibrate_camera_thread = threading.Thread(target = self.calibrate_camera_worker)
        self.calibrate_camera_thread.start()
    
    def calibrate_camera_worker(self):
        ''' Calibrates the camera focus by finding the ideal camera position 
            for multiple sample horizontal positions'''
        
        print('calibrate_camera: code refactoring in progress')

        self.ui.statusBar_label.setText('')
        self.ui.statusBar_progress.hide()
            
        '''Enabling modes after camera calibration'''
        self.updateUi_modes_buttons(self.default_buttons)
        self.updateUi_motor_buttons(False)
            
        self.camera_calibration_started = False
        self.ui.pushButton_calCameraStartCalibration.setText('Start Camera Calibration')

        self.sig_beep.emit()
        return None


        '''Setting the camera for acquisition'''
        self.camera.set_trigger_mode('external_exposure')
        self.camera.arm()
        
        '''Starting lasers'''
        self.both_lasers_activated = True
        self.start_lasers()
        
        '''Getting calibration parameters'''
        if self.ui.doubleSpinBox_calNumberOfPlanes.value() != 0:
            self.number_of_calibration_planes = self.ui.doubleSpinBox_calNumberOfPlanes.value()
        if self.ui.doubleSpinBox_calNumberOfCameraPositions.value() != 0:
            self.number_of_camera_positions = self.ui.doubleSpinBox_calNumberOfCameraPositions.value()
        
        sample_increment_length = (self.motors.horizontal.get_limit_high(self.units) - self.motors.horizontal.get_limit_low(self.units)) / (self.number_of_calibration_planes - 1) #-1 to account for last position
        self.focus_backward_boundary = 38 ##Position arbitraire en u-steps
        self.focus_forward_boundary = 31 ##Position arbitraire en u-steps
        camera_increment_length = (self.focus_backward_boundary - self.focus_forward_boundary) / (self.number_of_camera_positions-1) #-1 to account for last position
        
        position_depart_sample = self.motors.horizontal.get_position('\u03BCStep')
        
        self.camera_focus_relation = np.zeros((int(self.number_of_calibration_planes),2))
        metricvar = np.zeros((int(self.number_of_camera_positions)))
        self.donnees = np.zeros(((int(self.number_of_calibration_planes)),(int(self.number_of_camera_positions)))) #debugging
        self.popt = np.zeros((int(self.number_of_calibration_planes),3))    #debugging
        
        # Check that filename is valid and saving is allowed
        self.validate_file_name()
        if self.saving_allowed:
            '''Getting sample name'''
            self.save_description = str(self.ui.lineEdit_saveDescription.text())

            '''Setting frame saver'''
            self.frame_saver.reinit(3)
            self.frame_saver.add_sample_name(self.save_description)
            self.frame_saver.set_files(self.number_of_calibration_planes,self.save_filename,'cameraCalibration',self.number_of_camera_positions,'camera_position')
            
            '''Starting frame saver'''
            self.frame_saver.start_saving()
        else:
            print('Select directory and enter a valid filename before saving')
        
        '''Set progress bar'''
        progress_value = 0
        progress_increment = 100/self.number_of_calibration_planes
        self.sig_progress_update.emit(0) #To reset progress bar

        # Compute scan waveforms only once before we start the calibration
        # Changes to settings won't be effective until we stop/restart mode 
        self.siggen.compute_scan_waveforms()

        for sample_plane in range(int(self.number_of_calibration_planes)): #For each sample position
            if self.camera_calibration_started == False:
                self.sig_message.emit('Camera calibration interrupted')
                break
            else:
                '''Moving sample position'''
                position = self.motors.horizontal.get_limit_low(self.units) + (sample_plane * sample_increment_length)    #Increments of +sample_increment_length
                self.motors.horizontal.move_absolute_position(position, self.units)
                self.updateUi_position_horizontal()
                
                for camera_plane in range(int(self.number_of_camera_positions)): #For each camera position
                    if self.camera_calibration_started == False:
                        break
                    else:
                        '''Moving camera position'''
                        position_camera = self.focus_forward_boundary + (camera_plane * camera_increment_length) #Increments of +camera_increment_length
                        #print('position_camera:'+str(position_camera))
                        self.motors.camera.move_absolute_position(position_camera, 'mm')
                        time.sleep(0.5) #To make sure the camera is at the right position
                        self.updateUi_position_camera()
    
                        '''Retrieving filename set by the user''' #debugging
                        if self.saving_allowed:
                            self.frame_saver.add_motor_parameters(self.current_horizontal_position_text, self.current_vertical_position_text, self.current_camera_position_text)
                        
                        '''Getting image'''
                        self.acquire_scan()
                        
                        '''Saving frame''' #debugging
                        if self.saving_allowed:
                            self.frame_saver.enqueue_buffer(self.reconstructed_frame)
                            self.sig_message.emit('Saving Reconstructed Image')
                        
                        '''Filtering frame'''
                        frame = ndimage.gaussian_filter(self.reconstructed_frame, sigma=3)
                        ##flatframe = frame.flatten()
                        intensities = np.sort(frame,axis=None)
                        metricvar[camera_plane] = np.average(intensities[-50:]) ##np.var(flatframe)
                        #print(np.var(flatframe))
                
                '''Calculating ideal camera position'''
                try:
                    metricvar = signal.savgol_filter(metricvar, 11, 3) # window size 11, polynomial order 3
                    metricvar = (metricvar - np.min(metricvar))/(np.max(metricvar) - np.min(metricvar))#normalize
                    self.donnees[sample_plane,:] = metricvar #debugging
                    
                    n = len(metricvar)
                    x = np.arange(n)            
                    mean = sum(x*metricvar)/n           
                    sigma = sum(metricvar*(x-mean)**2)/n
                    poscenter = np.argmax(metricvar)
                    print('poscenter:' + str(poscenter)) #debugging
                    popt, pcov = optimize.curve_fit(gaussian, x, metricvar, p0=[1,mean,sigma], bounds=(0, 'inf'), maxfev=10000)
                    amp, center, variance = popt
                    self.popt[sample_plane] = popt
                    print('center:' + str(center)) #debugging
                    print('amp:' + str(amp)) #debugging
                    print('variance:' + str(variance)) #debugging
                    print('pcov:' + str(pcov)) #debugging
                    
                    '''Saving focus relation'''
                    self.camera_focus_relation[sample_plane,0] = self.motors.horizontal.get_position(self.units)
                    max_variance_camera_position = self.focus_forward_boundary + (center * camera_increment_length)
                    print('max_variance_camera_position:'+str(max_variance_camera_position))
                    if max_variance_camera_position > self.focus_backward_boundary:
                        max_variance_camera_position = self.focus_backward_boundary
                    self.camera_focus_relation[sample_plane,1] = max_variance_camera_position
                    
                    self.sig_message.emit('--Calibration of plane ' + str(sample_plane+1) + '/' + str(int(self.number_of_calibration_planes)) + ' done')
            
                    '''Update progress bar'''
                    progress_value += progress_increment
                    self.sig_progress_update.emit(int(progress_value))
                except:
                    self.camera_calibration_started = False
                    self.sig_message.emit('Camera calibration failed')
        if self.camera_calibration_started:
            self.sig_progress_update.emit(100) #In case the number of planes is not a multiple of 100
        
        print('relation:') #debugging
        print(self.camera_focus_relation)#debugging
        
        if self.saving_allowed: #debugging
            self.frame_saver.stop_saving()
            self.sig_message.emit('Images saved')
        
        '''Returning sample and camera at initial positions'''
        self.motors.horizontal.move_absolute_position(position_depart_sample,'\u03BCStep')
        self.updateUi_position_horizontal()
        self.motors.camera.move_absolute_position(self.motors.camera.get_origin(self.units), self.units)
        self.updateUi_position_camera()

        # Put ETLs in standby mode: 2.5V corresponds no current through coil (mid 0-5V adjustable range)
        self.siggen.update_etls(left_etl=2.5, right_etl=2.5)

        '''Stopping lasers'''
        self.stop_lasers()
        self.both_lasers_activated = False

        '''Stopping camera'''
        self.camera.disarm()

        '''Calculating focus'''
        if self.camera_calibration_started: #To make sure calibration wasn't stopped before the end
            x = self.camera_focus_relation[:,0]
            y = self.camera_focus_relation[:,1]
            self.slope_camera, self.intercept_camera, r_value, p_value, std_err = stats.linregress(x, y)
            print('r_value:'+str(r_value)) #debugging
            print('p_value:'+str(p_value)) #debugging
            print('std_err:'+str(std_err)) #debugging
            self.calculate_camera_focus()
            
            self.default_buttons.append(self.ui.pushButton_calCameraComputeFocus)
            self.default_buttons.append(self.ui.pushButton_calCameraShowInterpolation)
        
        self.sig_message.emit('Camera calibration done')
        self.ui.statusBar_label.setText('')
        self.ui.statusBar_progress.hide()
            
        '''Enabling modes after camera calibration'''
        self.updateUi_modes_buttons(self.default_buttons)
        self.updateUi_motor_buttons(False)
            
        self.camera_calibration_started = False
        self.ui.pushButton_calCameraStartCalibration.setText('Start Camera Calibration')

    
    def etls_calibration_button(self):
        '''Start or stop etls calibration, depending on the button status'''
        if self.etls_calibration_started:
            self.etls_calibration_started = False
            self.calibrate_etls_thread.join()
        else:
            self.close_modes()
            self.etls_calibration_started = True
            self.ui.pushButton_calEtlStartCalibration.setText('Stop ETL Calibration')
            self.updateUi_motor_buttons()
            self.start_calibrate_etls()
    
    def start_calibrate_etls(self):
        '''Initiates etls-galvos calibration'''
       
        '''Modes disabling while stack acquisition'''
        self.updateUi_modes_buttons([self.ui.pushButton_calEtlStartCalibration])
        self.updateUi_message_printer('ETL calibration started')
        
        '''Starting camera calibration thread'''
        self.calibrate_etls_thread = threading.Thread(target = self.calibrate_etls_worker)
        self.calibrate_etls_thread.start()


    def calibrate_etls_worker(self):
        ''' Calibrates the focal position relation with etls-galvos voltage'''
        print('calibrate_etls: code refactoring in progress')
        self.etls_calibration_started = False

        '''Enabling modes after camera calibration'''
        self.updateUi_modes_buttons(self.default_buttons)
        self.updateUi_motor_buttons(False)
        
        self.etls_calibration_started = False
        self.ui.pushButton_calEtlStartCalibration.setText('Start ETL Calibration')

        return None
       
        # TODO - Clean up calibrate_etls_thread
        _terminals = {}
        _terminals["galvos_etls"] = '/Dev1/ao0:3'

        '''Setting the camera for acquisition'''
        self.camera.set_trigger_mode('auto_trigger')
        self.camera.set_exposure_time(self.ui.doubleSpinBox_acqExposureTime.value())
        self.camera.arm()        
        
        '''Setting tasks'''
        self.galvos_etls_task = nidaqmx.Task()
        self.galvos_etls_task.ao_channels.add_ao_voltage_chan(_terminals["galvos_etls"])
        
        '''Getting parameters'''
        self.number_of_etls_points = 20 ##
        self.number_of_etls_images = 20 ##
        
        self.etl_l_relation = np.zeros((int(self.number_of_etls_points),2))
        self.etl_r_relation = np.zeros((int(self.number_of_etls_points),2))
        
        
        # Check that filename is valid and saving is allowed
        self.validate_file_name()
        if self.saving_allowed:
            '''Getting sample name'''
            self.save_description = str(self.ui.lineEdit_saveDescription.text())

            '''Setting frame saver'''
            self.frame_saver.reinit(3)
            self.frame_saver.add_sample_name(self.save_description)
            self.frame_saver.set_files(2*self.number_of_etls_points,self.save_filename,'etlCalibration',self.number_of_etls_images,'etl_image')
            
            '''Starting frame saver'''
            self.frame_saver.start_saving()
        else:
            print('Select directory and enter a valid filename before saving')
        
        
        '''Finding relation between etls' voltage and focal point vertical's position'''
        for side in ['etl_l','etl_r']: #For each etl
            '''Parameters'''
            if side == 'etl_l':
                etl_max_voltage = 4.2       #Volts ##Arbitraire
                etl_min_voltage = 2         #Volts ##Arbitraire
            if side == 'etl_r':
                etl_max_voltage = 4.2       #Volts ##Arbitraire
                etl_min_voltage = 2         #Volts ##Arbitraire
            etl_increment_length = (etl_max_voltage - etl_min_voltage) / self.number_of_etls_points
            
            '''Starting automatically lasers'''
            if side == 'etl_l':
                self.left_laser_activated = True
            if side == 'etl_r':
                self.right_laser_activated = True
            self.start_lasers()
            
            #self.camera.retrieve_single_image()*1.0 ##pour éviter images de bruit
            
            self.xdata = np.zeros((int(self.number_of_etls_points),128))
            self.ydata = np.zeros((int(self.number_of_etls_points),128))
            self.popt = np.zeros((int(self.number_of_etls_points),4))
            
            #For each interpolation point
            for etl_point in range(int(self.number_of_etls_points)):
                if self.etls_calibration_started is False:
                    self.sig_message.emit('ETL calibration interrupted')
                    break
                else:
                    '''Getting the data to send to the AO'''
                    right_etl_voltage = etl_min_voltage + (etl_point * etl_increment_length) #Volts
                    left_etl_voltage = etl_min_voltage + (etl_point * etl_increment_length) #Volts
                    
                    left_galvo_voltage = 0 #Volts
                    right_galvo_voltage = 0.1 #Volts
                    
                    '''Writing the data'''
                    galvos_etls_waveforms = np.stack((  np.array([right_galvo_voltage]),
                                                        np.array([left_galvo_voltage]),
                                                        np.array([left_etl_voltage]),
                                                        np.array([right_etl_voltage])   ))
                    self.galvos_etls_task.write(galvos_etls_waveforms, auto_start=True)
                   
                    '''Retrieving buffer for the plane of the current position'''
                    #self.ramps = AOETLGalvos(self.parameters)
                    #self.number_of_steps = 1
                    #self.buffer = self.camera.retrieve_multiple_images(self.number_of_steps, self.ramps.t_half_period, sleep_timeout = 5) #debugging
                    #self.save_single_image() #debugging
                    
                    ydatas = np.zeros((self.number_of_etls_images,128))  ##128=K
                    
                    #For each image
                    for etl_image in range(self.number_of_etls_images):
                        time.sleep(1)

                        # Retrieving image from camera and putting it in its queue for display
                        frame = self.camera.grab_image()*1.0
                        blurred_frame = ndimage.gaussian_filter(frame, sigma=20)
                        
                        '''Retrieving filename set by the user''' #debugging
                        if self.saving_allowed:
                            self.frame_saver.add_motor_parameters(self.current_horizontal_position_text,self.current_vertical_position_text,self.current_camera_position_text)
                        
                        '''Saving frame''' #debugging
                        if self.saving_allowed:
                            self.frame_saver.enqueue_buffer(blurred_frame)
                            self.sig_message.emit('Saving Reconstructed Image')
                        
                        self.frame_viewer.enqueue_frame(frame)
                        self.frame_viewer.enqueue_frame(blurred_frame)

                        '''Calculating focal point horizontal position'''
                        #filtering image:
                        #dset = np.transpose(blurred_frame)
                        #reshape image to average over profiles:
                        height=dset.shape[0]
                        width=dset.shape[1]
                        C=20
                        K=int(width/C) #average over C columns
                        dset=np.reshape(dset,(height,K,int(width/K)))
                        dset=np.mean(dset,2)
                        
                        #get average profile to restrict vertical range
                        avprofile=np.mean(dset,1)
                        indmax=np.argmax(avprofile)
                        rangeAroundPeak=np.arange(indmax-100,indmax+100)
                        #correct if the range exceeds the original range of the image
                        rangeAroundPeak = rangeAroundPeak[rangeAroundPeak < height]
                        rangeAroundPeak = rangeAroundPeak[rangeAroundPeak > -1]
                        
                        #compute fwhm for each profile:
                        std_val=[]
                        for i in range(dset.shape[1]):
                            curve=(dset[rangeAroundPeak,i]-np.min(dset[rangeAroundPeak,i]))/(np.max(dset[rangeAroundPeak,i])-np.min(dset[rangeAroundPeak,i]))
                            std_val.append(fwhm(curve)/2*np.sqrt(2*np.log(2)))
                        
                        #prepare data for fit:
                        ydata=np.array(std_val)
                        ydatas[etl_image,:] = signal.savgol_filter(ydata, 51, 3) # window size 51, polynomial order 3
                    
                    '''Calculate focus'''
                    try:
                        #Calculate fit for average of images
                        xdata=np.linspace(0,width-1,K)
                        good_ydata=np.mean(ydatas,0)
                        popt, pcov = optimize.curve_fit(func, xdata, good_ydata,bounds=((0.5,0,0,0),(np.inf,np.inf,np.inf,np.inf)), maxfev=10000) #,bounds=(0,np.inf) #,bounds=((0,-np.inf,-np.inf,0),(np.inf,np.inf,np.inf,np.inf))
                        beamWidth,focusLocation,rayleighRange,offset = popt
                        print('pcov'+str(pcov)) #debugging
                        
                        if focusLocation < 0:
                            focusLocation = 0
                        elif focusLocation > 2559:
                            focusLocation = 2559
                        np.set_printoptions(threshold=sys.maxsize)
                        print(func(xdata, *popt))
                        print('offset:'+str(int(offset))) #debugging
                        print('beamWidth:'+str(int(beamWidth))) #debugging
                        print('focusLocation:'+str(int(focusLocation))) #debugging
                        print('rayleighRange:'+str(rayleighRange)) #debugging
                        
                        ##Pour afficher graphique
                        if side == 'etl_r':
                            self.xdata[etl_point]=xdata
                            self.ydata[etl_point]=good_ydata
                            self.popt[etl_point]=popt
                        
                        '''Saving relations'''
                        if side == 'etl_l':
                            self.etl_l_relation[etl_point,0] = left_etl_voltage
                            self.etl_l_relation[etl_point,1] = int(focusLocation)
                        if side == 'etl_r':
                            self.etl_r_relation[etl_point,0] = right_etl_voltage
                            self.etl_r_relation[etl_point,1] = int(focusLocation)
                    
                        self.sig_message.emit('--Calibration of plane '+str(etl_point+1)+'/'+str(self.number_of_etls_points)+' for '+side+' done')
                    except:
                        self.etls_calibration_started = False
                        self.sig_message.emit('ETL calibration failed')
            
            '''Closing lasers after calibration of each side'''    
            self.left_laser_activated = False
            self.right_laser_activated = False
        
        if self.saving_allowed: #debugging
            self.frame_saver.stop_saving()
            self.sig_message.emit('Images saved')
        
        
        print(self.etl_l_relation) #debugging
        print(self.etl_r_relation) #debugging
        '''Calculating linear regressions'''
        xl = self.etl_l_relation[:,0]
        yl = self.etl_l_relation[:,1]
        #Left linear regression
        self.etl_left_slope, self.etl_left_intercept, r_value, p_value, std_err = stats.linregress(yl, xl)
        print('r_value:'+str(r_value)) #debugging
        print('p_value:'+str(p_value)) #debugging
        print('std_err:'+str(std_err)) #debugging
        print('left_slope:'+str(self.etl_left_slope)) #debugging
        print('left_intercept:'+str(self.etl_left_intercept)) #debugging
        print(self.etl_left_slope * 2559 + self.etl_left_intercept) #debugging
        
        xr = self.etl_r_relation[:,0]
        yr = self.etl_r_relation[:,1]
        #Right linear regression
        self.etl_right_slope, self.etl_right_intercept, r_value, p_value, std_err = stats.linregress(yr, xr)
        print('r_value:'+str(r_value)) #debugging
        print('p_value:'+str(p_value)) #debugging
        print('std_err:'+str(std_err)) #debugging
        print('right_slope:'+str(self.etl_right_slope)) #debugging
        print('right_intercept:'+str(self.etl_right_intercept)) #debugging
        print(self.etl_right_slope * 2559 + self.etl_right_intercept) #debugging
        
        '''Stopping camera'''
        self.camera.disarm()
        
        '''Ending tasks'''
        self.galvos_etls_task.stop()
        self.galvos_etls_task.close()
        
        '''Stopping lasers'''
        self.stop_lasers()
        self.both_lasers_activated = False

        if self.etls_calibration_started: #To make sure calibration wasn't stopped before the end
            self.default_buttons.append(self.ui.pushButton_calEtlShowInterpolation)
        
        self.sig_message.emit('Calibration done')
            
        '''Enabling modes after camera calibration'''
        self.updateUi_modes_buttons(self.default_buttons)
        self.updateUi_motor_buttons(False)
        
        self.etls_calibration_started = False
        self.ui.pushButton_calEtlStartCalibration.setText('Start ETL Calibration')


class Properties_Dialog(QDialog):
    '''Class for Properties Dialog'''

    sig_status_message = pyqtSignal(str)

    def __init__(self, parent:Controller_MainWindow):
        QDialog.__init__(self, parent)
        self.parent = parent
        self.camera = self.parent.camera
        self.motors = self.parent.motors
 
        self.ui = Ui_Properties()
        self.ui.setupUi(self)
        self.ui.pushButton_refresh.clicked.connect(self.refresh_properties)
        self.sig_status_message.connect(self.parent.updateUi_message_printer)

        self.get_properties()


    def get_properties(self):
        # Read properties from the camera
        camera_properties = {}
        camera_properties = self.camera.get_properties()
        self.ui.label_cameraName.setText(f"{camera_properties.get('camera name', '-')}")
        self.ui.label_imageSize.setText(f"{camera_properties.get('x', '0')} X {camera_properties.get('y', '0')}")
        self.ui.label_cameraTemperature.setText(f"{camera_properties.get('camera temperature', 0):.1f} \u2103")
        self.ui.label_sensorTemperature.setText(f"{camera_properties.get('sensor temperature', 0):.1f} \u2103")
        self.ui.label_powerTemperature.setText(f"{camera_properties.get('power temperature', 0):.1f} \u2103")
        self.ui.label_triggerMode.setText(f"{camera_properties.get('trigger mode', '-')}")
        self.ui.label_delayTime.setText(f"{camera_properties.get('delay', '-')}  {camera_properties.get('delay timebase', 'ms')}")
        self.ui.label_exposureTime.setText(f"{camera_properties.get('exposure', '-')}  {camera_properties.get('exposure timebase', 'ms')}")
        self.ui.label_acquireMode.setText(f"{camera_properties.get('acquire mode', '-')}")
        self.ui.label_storageMode.setText(f"{camera_properties.get('storage mode', '-')}")
        if camera_properties.get('storage mode', '-') == 'Recorder':
            self.ui.label_recorderMode.setText(f"{camera_properties.get('recorder submode', '-')}")
        else:
            self.ui.label_recorderMode.setText('-')
        
        # Read properties from the motors
        motors_properties = {}
        motors_properties = self.motors.get_properties()
        self.ui.label_horizontalMotorName.setText(f"{motors_properties.get('horizontal name', '-')}")
        self.ui.label_verticalMotorName.setText(f"{motors_properties.get('vertical name', '-')}")
        self.ui.label_cameraMotorName.setText(f"{motors_properties.get('camera name', '-')}")
    
    def refresh_properties(self):
        '''Refresh system properties'''
        self.get_properties()
        self.sig_status_message.emit('System Properties Refreshed')



class FrameViewer(QObject):
    '''Class for queueing and displaying images'''

    def __init__(self, parent:Controller_MainWindow, rows, columns):
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
        frame_init[0,0] = 2000
        # Transpose since setImage is column-major
        frame_init = np.transpose(frame_init)
        # Set initial view
        self.parent.ui.imageView.setImage(frame_init)

    def enqueue_frame(self, frame:np.uint16):
        try:
            self.queue.put(frame, block=False)
        except queue.Full:
            pass

    def updateUi_refresh_view(self):
        try:
            frame = self.queue.get(block=False)
        except queue.Empty:
            pass
        else:
            # setImage is column-major
            frame = np.transpose(frame)
            self.parent.ui.imageView.setImage(frame, autoRange=False, autoLevels=False, autoHistogramRange=False)

class FrameSaver(QObject):
    '''Class for storing buffers (images) in its queue and saving them 
       afterwards in a specified directory in a HDF5 format'''
    
    sig_status_message = pyqtSignal(str)

    def __init__(self, parent:Controller_MainWindow, block_size:int = 1):
        QObject.__init__(self, parent)
        self.parent = parent
        self.sig_status_message.connect(self.parent.updateUi_message_printer)

        self.saving_started = False
        self.block_size = block_size
        self.queue = queue.Queue(2*block_size)

        self.sample_name = ''
        self.number_of_files = int(1)
        self.filenames_list = [] 
        self.horizontal_positions_list = []
        self.vertical_positions_list = []
        self.camera_positions_list = []

    def reinit(self, block_size:int):
        if self.saving_started:
            self.saving_started = False

        self.block_size = block_size
        self.queue = queue.Queue(2*block_size) #Set up queue of maxsize 2*block_size (frames)

        self.sample_name = ''
        self.number_of_files = int(1)
        self.filenames_list = [] 
        self.horizontal_positions_list = []
        self.vertical_positions_list = []
        self.camera_positions_list = []


    def add_sample_name(self, sample_name:str):
        '''Add to a list the different motor positions'''
        self.sample_name = sample_name

    def add_motor_parameters(self, current_hor_position_txt, current_ver_position_txt, current_cam_position_txt):
        '''Add to a list the different motor positions'''
        self.horizontal_positions_list.append(current_hor_position_txt)
        self.vertical_positions_list.append(current_ver_position_txt)
        self.camera_positions_list.append(current_cam_position_txt)
    
    def set_files(self, number_of_files:int, files_name:str, scan_type:str, number_of_datasets:int, datasets_name:str):
        '''Set the number and name of files to save and makes sure the filenames 
        are unique in the path to avoid overwrite on other files'''
        self.number_of_files = int(number_of_files)
        self.files_name = str(files_name)
        self.scan_type = str(scan_type)
        self.number_of_datasets = int(number_of_datasets)
        self.datasets_name = str(datasets_name)
        
        counter = 0
        for _ in range(self.number_of_files):
            while True:
                counter += 1
                new_filename = self.files_name + '_' + scan_type + '_plane_' + u'%05d'%counter + '.hdf5'
                if os.path.isfile(new_filename) == False: #Check for existing files
                    self.filenames_list.append(new_filename)
                    break
    
    def add_attribute(self, attribute, value):
        '''Add an attribute to a dataset: a string associated to a value'''
        self.dataset.attrs[attribute] = value
    
    '''Saving methods'''
    def enqueue_buffer(self, buffer):
        '''Put an image in the save queue'''
        self.queue.put(item=buffer, block=True)
    
    def start_saving(self):
        '''Initiates saving thread'''
        self.saving_started = True
        self.frame_saver_thread = threading.Thread(target = self.frame_saver_worker)
        self.frame_saver_thread.start()
    
    def frame_saver_worker(self):
        '''Thread for saving 3D arrays (or 2D arrays).
            The number of datasets per file is the number of 2D arrays'''
        for file in range(len(self.filenames_list)):
            print('File created:'+str(self.filenames_list[file])) #debugging
            '''Create file'''
            f = h5py.File(self.filenames_list[file],'a')
            
            counter = 1
            for dataset in range(int(self.number_of_datasets)):
                while True:
                    try:
                        '''Retrieve buffer'''
                        buffer = self.queue.get(True, 1)
                        if buffer.ndim == 2:
                            buffer = np.expand_dims(buffer, axis=0) #To consider 2D arrays as a 3D arrays
                        for frame in range(buffer.shape[0]): #For each 2D frame
                            '''Create dataset'''
                            path_root = self.datasets_name+u'%03d'%counter
                            self.dataset = f.create_dataset(path_root, data=buffer[frame,:,:])
                            print('Dataset '+str(dataset)+'/'+str(int(self.number_of_datasets))+' created:'+str(path_root)) #debugging
                            
                            '''Add attributes'''
                            self.add_attribute('Sample Name', self.sample_name)
                            self.add_attribute('Date', str(datetime.date.today()))
                            if buffer.shape[0] == 1:
                                pos_index = dataset + file * int(self.number_of_datasets)
                            else:
                                pos_index = file
                            self.add_attribute('Current sample horizontal position', self.horizontal_positions_list[pos_index])
                            self.add_attribute('Current sample vertical position', self.vertical_positions_list[pos_index])
                            self.add_attribute('Current camera horizontal position', self.camera_positions_list[pos_index])
                            counter += 1
                        break
                    except:
                        if self.saving_started == False:
                            break
                if self.saving_started == False:
                    break
            f.close()
            self.sig_status_message.emit('File ' + self.filenames_list[file] + ' saved')
            if self.saving_started == False:
                break

    def stop_saving(self):
        '''Changes the flag status to end the saving thread'''
        self.saving_started = False
        #self.frame_saver_thread.join()
