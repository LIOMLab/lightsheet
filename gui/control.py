'''
Created on May 22, 2019

@authors: Pierre Girard-Collins & flesage
'''
import os
import sys
sys.path.append(".")

from PyQt5.QtCore import QObject, QTimer, QThread, pyqtSignal
from PyQt5.QtWidgets import QMainWindow, QDialog, QFileDialog, QTableWidgetItem, QAbstractItemView, QMessageBox, QLabel, QProgressBar, QDesktopWidget
from PyQt5.QtGui import QTextCursor

from pyqtgraph import ImageView

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
from configparser import ConfigParser
from matplotlib import pyplot as plt
from scipy import signal, optimize, ndimage, stats

#from gui.ui_controller import Ui_Controller
from gui.ui_controller_v2 import Ui_Controller
from gui.ui_properties import Ui_Properties
from gui.ui_settings import Ui_Settings

from src.hardware import AOETLGalvos
from src.motors import Motors
from src.camera import Camera
from src.lasers import Lasers

#mainlog = logging.getLogger('main')
#mainlog.setLevel(level=logging.INFO)
#fileHandler = logging.FileHandler('log.txt')
#fileFormatter = logging.Formatter("%(asctime)s | %(message)s")
#fileHandler.setLevel(logging.INFO)
#fileHandler.setFormatter(fileFormatter)
#consoleHandler = logging.StreamHandler()
#consoleFormatter = logging.Formatter("%(message)s")
#consoleHandler.setLevel(logging.INFO)
#consoleHandler.setFormatter(consoleFormatter)
#mainlog.addHandler(fileHandler)
#mainlog.addHandler(consoleHandler)


'''Default parameters'''
parameters = {}
parameters["Sample Name"]= 'No Sample Name'
parameters["Columns"] = 2560            # In pixels
parameters["Rows"] = 2160               # In pixels
parameters["camera_delay"] = 10         # In %
parameters["min_t_delay"] = 0.0354404   # In seconds
parameters["t_start_exp"] = 0.017712    # In seconds
save_parameters_policy = 0
default_save_directory = 'None Specified'
default_filename = 'Test'


'''Math functions'''
def gaussian(x,a,x0,sigma):
    '''1D Gaussian Function'''
    return a*np.exp(-(x-x0)**2/(2*sigma**2))

def func(x, w0, x0, xR, offset):
    '''Gaussian Beam Width Function'''
    return w0 * (1+((x-x0)/xR)**2)**0.5 + offset

def fwhm(y):
    '''Full width at half maximum'''
    max_y = max(y)  # Find the maximum y value
    xs = [x for x in range(len(y)) if y[x] > max_y/2.0]
    fwhm_val = max(xs) - min(xs) + 1
    return fwhm_val  


class Settings_Dialog(QDialog):
    '''Class for Settings Dialog'''
    
    def __init__(self, status_printer):
        QDialog.__init__(self)
        self.ui = Ui_Settings()
        self.ui.setupUi(self)   
        self.ui.pushButton_selectDirectory.clicked.connect(self.select_directory)
        self.ui.pushButton_selectNone.clicked.connect(self.select_none)

        self.status_printer = status_printer
        self.load_preset()

    def load_preset(self):
        '''Load preset'''
        self.ui.comboBox_savePolicy.setCurrentIndex(save_parameters_policy)
        self.ui.label_saveDirectory.setText(default_save_directory)
        self.ui.lineEdit_defaultFilename.setText(default_filename)
        if default_save_directory == 'None Specified':
            self.ui.lineEdit_defaultFilename.setEnabled(False)
    
    def select_directory(self):
        '''Allows the selection of a default save directory'''
        options = QFileDialog.Options()
        options |= QFileDialog.DontResolveSymlinks
        options |= QFileDialog.ShowDirsOnly
        default_save_directory = QFileDialog.getExistingDirectory(self, 'Choose Directory', '', options)
        if default_save_directory != '': #If directory specified
            self.ui.label_saveDirectory.setText(default_save_directory)
            self.ui.lineEdit_defaultFilename.setEnabled(True)
        else:
            self.select_none()
    
    def select_none(self):
        '''Selects no default save directory'''
        self.ui.label_saveDirectory.setText('None Specified')
        self.ui.lineEdit_defaultFilename.setEnabled(False)


class Properties_Dialog(QDialog):
    '''Class for Properties Dialog'''
    
    def __init__(self, camera: Camera, motors: Motors, status_printer):
        QDialog.__init__(self)
        self.ui = Ui_Properties()
        self.ui.setupUi(self)   
        self.ui.pushButton_refresh.clicked.connect(self.refresh_properties)
        
        self.camera = camera
        self.motors = motors
        self.status_printer = status_printer
        self.get_properties()
    
    def get_properties(self):
        '''Read properties from the camera'''
        self.ui.label_cameraName.setText(self.camera.get_name())
        self.ui.label_imageSize.setText(str(self.camera.get_xsize()) + " x " + str(self.camera.get_ysize()))
        self.ui.label_cameraTemperature.setText("{:.1f} \u2103".format(self.camera.get_camera_temperature()))
        self.ui.label_sensorTemperature.setText("{:.1f} \u2103".format(self.camera.get_sensor_temperature()))
        self.ui.label_powerTemperature.setText("{:.1f} \u2103".format(self.camera.get_power_temperature()))
        self.ui.label_triggerMode.setText(self.camera.get_trigger_mode())
        self.ui.label_delayTime.setText(str(self.camera.get_delay_time()) + " " + self.camera.get_delay_timebase())
        self.ui.label_exposureTime.setText(str(self.camera.get_exposure_time()) + " " + self.camera.get_exposure_timebase())
        self.ui.label_acquireMode.setText(self.camera.get_acquire_mode())
        self.ui.label_storageMode.setText(self.camera.get_storage_mode())
        if self.camera.get_storage_mode() == 'Recorder':
            self.ui.label_recorderMode.setText(self.camera.get_recorder_submode())
        else:
            self.ui.label_recorderMode.setText('N/A')
        
        '''Read properties from the motors'''
        self.ui.label_horizontalMotorName.setText(self.motors.horizontal_get_name())
        self.ui.label_verticalMotorName.setText(self.motors.vertical_get_name())
        self.ui.label_cameraMotorName.setText(self.motors.camera_get_name())
    
    def refresh_properties(self):
        '''Refresh system properties'''
        self.get_properties()
        self.status_printer('System Properties Refreshed')


class Controller_MainWindow(QMainWindow):
    '''Class for the MesoSPIM MainWindow'''

    # Default parameters
    _cfg_settings = {}
    _cfg_settings['Terminals'] = '/Dev1/ao0:3'       # DAQ board terminals
    _cfg_settings['Sample Clock Rate'] = '40000'     # In samples/second
    _cfg_settings['Galvo Frequency'] = '20'          # In Hertz
    _cfg_settings['Galvo Left Amplitude'] = '2'      # In Volts
    _cfg_settings['Galvo Right Amplitude'] = '2'     # In Volts
    _cfg_settings['Galvo Left Offset'] = '0.6'       # In Volts
    _cfg_settings['Galvo Right Offset'] = '0.6'      # In Volts
    _cfg_settings['ETL Left Amplitude'] = '2.0'      # In Volts
    _cfg_settings['ETL Right Amplitude'] = '2.0'     # In Volts
    _cfg_settings['ETL Left Offset'] = '0'           # In Volts
    _cfg_settings['ETL Right Offset'] = '0'          # In Volts
    _cfg_settings['ETL Steps'] = '8'                 # In # of steps (distinct focus regions over FOV)
    _cfg_settings['Laser Left Amplitude'] = '0.9'    # In Volts
    _cfg_settings['Laser Right Amplitude'] = '0.9'   # In Volts

    _hard_settings = {}
    _hard_settings['Image XSize'] = '2560'         # In pixels
    _hard_settings['Image YSize'] = '2160'         # In pixels
    _hard_settings['Camera Delay'] = '10'          # In % (duty cycle)
    _hard_settings['min_t_delay'] = '0.0354404'    # In seconds
    _hard_settings['t_start_exp'] = '0.017712'     # In seconds

    # Default terminals
    _terminals = {}
    _terminals["galvos_etls"] = '/Dev1/ao0:3'
    _terminals["camera"]      = '/Dev1/port0/line1'
    _terminals["lasers"]      = '/Dev7/ao0:1'

    # Signals
    sig_update_progress = pyqtSignal(int) #Status bar progress indicator update
    sig_beep = pyqtSignal(bool) #Beep sound
    sig_stylesheet = pyqtSignal(int) #App stylesheet change

    def __init__(self):
        # NOTES
        # 
        # Ui approach taken below requires generating .py file from .ui (Qt Designer file format)
        # This enables VSCode IntelliSense to work properly on Ui classes
        # PS command: pyuic5 .\controller.ui -o .\ui_controller.py
        # 
        # Previous Ui loading was done directly from .ui file with:
        # basepath = os.path.join(os.path.dirname(__file__))
        # uic.loadUi(os.path.join(basepath,"controller.ui"), self)
        #
        # Also, see https://fuhm.org/super-harmful/
        # for explanation why we don't automatically init inherited class with:
        # super(Controller, self).__init__()
        # but rather manually do so with: QMainWindow.__init__(self)
        #

        QMainWindow.__init__(self)
        self.ui = Ui_Controller()
        self.ui.setupUi(self)

        self.label_statusBar = QLabel()
        self.progress_statusBar = QProgressBar()
        self.ui.statusbar.addPermanentWidget(self.label_statusBar)
        self.ui.statusbar.addPermanentWidget(self.progress_statusBar)
        self.progress_statusBar.setFixedWidth(250)
        self.progress_statusBar.hide()
        self.resize(QDesktopWidget().availableGeometry(self).size() * 0.75);

        self.ui.plainTextEdit_cmdLog.appendPlainText("--The last commands will show here--\n")
        
        '''Instantiating the camera window where the frames are displayed'''
        self.camera_window = CameraWindow(self.ui.imageView)

        # Start timer to periodically refresh the imageview widget
        self.timer_imageview = QTimer()
        self.timer_imageview.timeout.connect(self.camera_window.update)        
        self.timer_imageview.start(100)

        # Set default hardcoded and configurable settings
        self.hard_settings = copy.deepcopy(self._hard_settings)
        self.cfg_settings = copy.deepcopy(self._cfg_settings)

        # Read configurable settings file
        self.cfg_read('config.ini')

        # Update UI with configurable settings
        self.updateUi_cfg_settings()

        '''Instantiating the hardware components'''
        self.motors = Motors()
        self.camera = Camera()
        self.lasers = Lasers()

        '''Instantiating the settings and properties windows'''
        self.settings_dialog = Settings_Dialog(self.status_printer)
        self.properties_dialog = Properties_Dialog(self.camera, self.motors, self.status_printer)
        
        '''Initially, CameraWindow is the only image consumer. Later when the user request 
        to save images, a second consumer (FrameSaver) is added in controller'''
        self.consumers = []
        self.set_data_consumer(self.camera_window, False, "CameraWindow", True)
        
        self.figure_counter = 1
        self.save_directory = ""
        self.save_parameters_policy = save_parameters_policy
        self.default_save_directory = default_save_directory
        self.default_filename = default_filename
        
        self.default_buttons = [self.ui.pushButton_acqStartStandbyMode,
                                self.ui.pushButton_acqStartPreviewMode,
                                self.ui.pushButton_acqStartLiveMode,
                                self.ui.pushButton_acqStartStackMode,
                                self.ui.pushButton_acqGetSingleImage,
                                self.ui.pushButton_calCameraStartCalibration,
                                self.ui.pushButton_calEtlStartCalibration]
        
#        self.modifiable_param_boxes = etl_volt_boxes + galvo_volt_boxes + laser_volt_boxes + [self.ui.doubleSpinBox_galvoFrequency,self.ui.doubleSpinBox_paramSampleRate,self.ui.spinBox_etlNumberOfSteps]
        
        '''Default ETL relation values'''
        self.left_slope = -0.0008978829380085525
        self.left_intercept = 4.25548088287623
        self.right_slope = 0.000826220401525251
        self.right_intercept = 2.384849899181325
        
        '''Initializing flags'''
        self.both_lasers_activated = False
        self.left_laser_activated = False
        self.right_laser_activated = False
        self.laser_on = False
        
        self.standby = False
        self.preview_mode_started = False
        self.live_mode_started = False
        self.stack_mode_started = False
        
        self.saving_allowed = False
        self.camera_calibration_started = False
        self.etls_calibration_started = False
        
        self.horizontal_forward_boundary_selected = False
        self.horizontal_backward_boundary_selected = False
        self.focus_selected = False
        
        '''Initializing settings'''
        self.ui.label_currentSaveDirectory.setText(default_save_directory)
        
        '''Initializing the properties of the widgets'''
        # Set units comboBox options (default: millimeters)
        self.ui.comboBox_units.insertItems(0,["mm","\u03BCm"])
        self.ui.comboBox_units.setCurrentIndex(0)
        
        '''Initialize values'''
#        self.back_to_default_parameters()
        
        '''Initializing every other widget that are updated by a change of unit 
            (the motion tab)'''
        self.updateUi_units()
        
        '''Initializing widgets' connections'''
        self.sig_update_progress.connect(self.progress_statusBar.setValue)
        
        '''Disable some buttons'''
        self.ui.lineEdit_filename.setEnabled(False)
        self.ui.lineEdit_sampleName.setEnabled(False)
        self.ui.pushButton_selectDataset.setEnabled(False)
        self.ui.checkBox_acqFirstPlaneSet.setEnabled(False)
        self.ui.checkBox_acqLastPlaneSet.setEnabled(False)
        self.ui.pushButton_acqSetFirstPlane.setEnabled(False)
        self.ui.pushButton_acqSetLastPlane.setEnabled(False)

        self.update_laser_buttons()
        self.update_buttons_modes(self.default_buttons)
        
        if default_save_directory != 'None Specified':
            self.ui.lineEdit_filename.setEnabled(True)
            self.ui.lineEdit_filename.setText(self.default_filename)
            self.ui.lineEdit_sampleName.setEnabled(True)
        
        '''Connect menu options'''
        self.ui.action_Exit.triggered.connect(self.close)
        self.ui.action_ShowHideControlsPane.triggered.connect(self.updateUi_show_hide_controls_pane)
        self.ui.action_ShowHideImagesPane.triggered.connect(self.updateUi_show_hide_images_pane)
        self.ui.action_ShowHideCommandLog.triggered.connect(self.updateUi_show_hide_command_log)
        self.ui.action_lightTheme.triggered.connect(self.updateUi_light_theme)
        self.ui.action_darkTheme.triggered.connect(self.updateUi_dark_theme)

        self.ui.action_ModifyProgramSettings.triggered.connect(self.open_settings_dialog)
        self.ui.action_showSystemProperties.triggered.connect(self.open_properties_dialog)
        self.ui.action_openDocumentation.triggered.connect(self.open_help)

        '''Connect settings options'''
        self.settings_dialog.ui.buttonBox.accepted.connect(self.change_settings)
        self.settings_dialog.ui.buttonBox.rejected.connect(self.settings_dialog.load_preset)
        
        '''Connect buttons'''

        # Connection for unit change (updateUi)
        self.ui.comboBox_units.currentTextChanged.connect(self.updateUi_units)

        # Connection for galvo parameters change (updateUi)
        self.ui.doubleSpinBox_galvoLeftAmplitude.valueChanged.connect(self.updateUi_galvo_left_amplitude)
        self.ui.doubleSpinBox_galvoRightAmplitude.valueChanged.connect(self.updateUi_galvo_right_amplitude)
        self.ui.doubleSpinBox_galvoLeftOffset.valueChanged.connect(self.updateUi_galvo_left_offset)
        self.ui.doubleSpinBox_galvoRightOffset.valueChanged.connect(self.updateUi_galvo_right_offset)
        self.ui.checkBox_galvoSync.stateChanged.connect(self.updateUi_galvo_sync)

        # Connection for etl parameters change (updateUi)
        self.ui.doubleSpinBox_etlLeftAmplitude.valueChanged.connect(self.updateUi_etl_left_amplitude)
        self.ui.doubleSpinBox_etlRightAmplitude.valueChanged.connect(self.updateUi_etl_right_amplitude)
        self.ui.doubleSpinBox_etlLeftOffset.valueChanged.connect(self.updateUi_etl_left_offset)
        self.ui.doubleSpinBox_etlRightOffset.valueChanged.connect(self.updateUi_etl_right_offset)
        self.ui.checkBox_etlSync.stateChanged.connect(self.updateUi_etl_sync)

        # Connection for laser parameters change (updateUi)
        self.ui.doubleSpinBox_laserLeftAmplitude
        self.ui.doubleSpinBox_laserRightAmplitude


        '''Connection for data saving'''
        self.ui.pushButton_selectSaveDirectory.clicked.connect(self.select_directory)
        self.ui.pushButton_selectFile.clicked.connect(self.select_file)
        self.ui.pushButton_selectDataset.clicked.connect(self.select_dataset)
        
        '''Connections for the modes'''
        self.ui.pushButton_acqGetSingleImage.clicked.connect(self.start_get_single_image)
        self.ui.pushButton_acqSaveSingleImage.clicked.connect(self.save_single_image)
        self.ui.pushButton_acqStartLiveMode.clicked.connect(self.live_button)
        self.ui.pushButton_acqStartStackMode.clicked.connect(self.stack_button)
        self.ui.pushButton_acqSetFirstPlane.clicked.connect(self.set_stack_mode_starting_point)
        self.ui.pushButton_acqSetLastPlane.clicked.connect(self.set_stack_mode_ending_point)
        self.ui.doubleSpinBox_acqPlaneStepSize.valueChanged.connect(self.set_number_of_planes)
        self.ui.pushButton_acqStartPreviewMode.clicked.connect(self.preview_button)
        self.ui.pushButton_acqStartStandbyMode.clicked.connect(self.standby_button)
       
        '''Connections for the motion'''
        self.ui.pushButton_sampleStepUp.clicked.connect(self.move_sample_up)
        self.ui.pushButton_sampleStepDown.clicked.connect(self.move_sample_down)
        self.ui.pushButton_sampleStepForward.clicked.connect(self.move_sample_forward)
        self.ui.pushButton_sampleStepBackward.clicked.connect(self.move_sample_backward)
        self.ui.pushButton_sampleGotoOrigin.clicked.connect(self.move_sample_to_origin)
        self.ui.pushButton_sampleSetOrigin.clicked.connect(self.set_sample_origin)
        self.ui.pushButton_sampleGotoHPosition.clicked.connect(self.move_to_horizontal_position)
        self.ui.pushButton_sampleGotoVPosition.clicked.connect(self.move_to_vertical_position)

        self.ui.pushButton_cameraGotoPosition.clicked.connect(self.move_camera_to_position)
        self.ui.pushButton_cameraSetFocus.clicked.connect(self.set_camera_focus)
        self.ui.pushButton_cameraStepForward.clicked.connect(self.move_camera_forward)
        self.ui.pushButton_cameraStepBackward.clicked.connect(self.move_camera_backward)
        self.ui.pushButton_cameraGotoFocus.clicked.connect(self.move_camera_to_focus)

        self.ui.pushButton_calCameraStartCalibration.clicked.connect(self.camera_calibration_button)
        self.ui.pushButton_calCameraComputeFocus.clicked.connect(self.calculate_camera_focus)
        self.ui.pushButton_calCameraShowInterpolation.clicked.connect(self.show_camera_interpolation)
        self.ui.pushButton_calEtlStartCalibration.clicked.connect(self.etls_calibration_button)
        self.ui.pushButton_calEtlShowInterpolation.clicked.connect(self.show_etl_interpolation)
        self.ui.pushButton_calHorizontalStartRangeSelection.clicked.connect(self.reset_boundaries)
        self.ui.pushButton_calHorizontalSetForwardLimit.clicked.connect(self.set_horizontal_forward_boundary)
        self.ui.pushButton_calHorizontalSetBackwardLimit.clicked.connect(self.set_horizontal_backward_boundary)
        

        
#        for param_string,param_box in zip(modifiable_parameters,self.modifiable_param_boxes):
#            param_box.valueChanged.connect(lambda _,parameter_name=param_string,parameter_box=param_box: self.update_etl_galvos_parameters(parameter_name,parameter_box)) 
#            #The parameter '_' (the box signal, a float number) is necessary because the first lambda parameter is always overwritten by the signal return
        
#        self.ui.pushButton_defaultParameters.clicked.connect(self.back_to_default_parameters)
#        self.ui.pushButton_changeDefaultParameters.clicked.connect(self.change_default_parameters)
        
        '''Connections for the lasers'''
        self.ui.pushButton_laserAllActivate.clicked.connect(self.lasers_button)
        self.ui.pushButton_laserLeftActivate.clicked.connect(self.left_laser_button)
        self.ui.pushButton_laserRightActivate.clicked.connect(self.right_laser_button)

    
    def cfg_read(self, cfg_filename):
        section = 'GalvoETL'
        values_dict = {}
        cfg = ConfigParser()
        cfg.optionxform = str
        cfg.read(cfg_filename)
        if cfg.has_section(section):
            for key, value in cfg[section].items():
                values_dict[key] = value
        for key in self.cfg_settings:
            if key in values_dict:
                self.cfg_settings[key] = values_dict[key]
        return None

    def cfg_write(self, cfg_filename):
        section = 'GalvoETL'
        values_dict = self.cfg_settings
        cfg = ConfigParser()
        cfg.optionxform = str
        cfg.read(cfg_filename)
        if not cfg.has_section(section):
            cfg.add_section(section)
        for key in values_dict:
            cfg.set(section, str(key), str(values_dict[key]))
        with open(cfg_filename, 'w') as output_file:
            cfg.write(output_file)
        return None    


    def closeEvent(self, event):
        '''Making sure that everything is closed when the user exits the software.
           This function executes automatically when the user closes the UI.
           This is an intrinsic function name of Qt, don't change the name even 
           if it doesn't follow the naming convention'''
        result = QMessageBox.question(self, "Confirm Exit...", "Are you sure you want to exit ?", QMessageBox.Yes | QMessageBox.No)
        if result == QMessageBox.Yes:
            self.close_modes()
            self.camera.close()
#            self.save_default_parameters()
            self.timer_imageview.stop()
            event.accept()
        else:
            event.ignore()

    def updateUi_light_theme(self):
        self.sig_stylesheet.emit(0)
        return None

    def updateUi_dark_theme(self):
        self.sig_stylesheet.emit(1)
        return None

    def status_printer(self,text):
        '''Print text in console, in controller text box and in status bar'''
        #print(text)
        # print() is not thread-safe
        # https://realpython.com/python-print/#thread-safe-printing
        logging.info(text)
        self.ui.statusbar.showMessage(text)
        self.ui.plainTextEdit_cmdLog.appendPlainText(text)
        self.ui.plainTextEdit_cmdLog.verticalScrollBar().setValue(self.ui.plainTextEdit_cmdLog.verticalScrollBar().maximum())
#        cursor = QTextCursor(self.ui.plainTextEdit_cmdLog.document())
#        cursor.setPosition(0)
#        self.ui.plainTextEdit_cmdLog.setTextCursor(cursor)
#        self.ui.plainTextEdit_cmdLog.insertPlainText(text + '\n ')
#        self.ui.label_lastCommands.setText(self.ui.label_lastCommands.text() + text + '\n ')
#        self.ui.scrollArea_lastCommands.verticalScrollBar().setValue(self.ui.scrollArea_lastCommands.verticalScrollBar().maximum())
    

    '''General Methods'''
    def open_settings_dialog(self):
        '''Open the dialog window for modification of settings'''
        self.settings_dialog.exec_()
    
    def open_properties_dialog(self):
        '''Open the dialog window for showing properties'''
        self.properties_dialog.open()
        self.properties_dialog.get_properties()
    
    def change_settings(self):
        '''Change the configuration settings'''
        self.save_parameters_policy = self.settings_dialog.ui.comboBox_savePolicy.currentIndex()
        self.default_save_directory = self.settings_dialog.ui.label_saveDirectory.text()
        self.default_filename = self.settings_dialog.ui.lineEdit_defaultFilename.text()
        self.status_printer('Configuration Settings Changed')
    
    def open_help(self):
        '''Open help documentation for the program (PDF)'''
        guide_pdf = os.path.dirname(os.path.abspath(__file__)) + '\..\Guide.pdf'
        webbrowser.open_new(guide_pdf)

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

    def updateUi_show_hide_command_log(self):
        if self.ui.plainTextEdit_cmdLog.isVisible():
            self.ui.plainTextEdit_cmdLog.hide()
        else:
            self.ui.plainTextEdit_cmdLog.show()

  # -------------------------------------------------------------------------------------------------------------------------------
  # -------------------------------------------------------------------------------------------------------------------------------
    
    def update_laser_buttons(self, disable_button = True):
        '''Deactivate lasers, and enable or disable all laser buttons'''
        if self.both_lasers_activated:
            self.lasers_button()
        elif self.left_laser_activated:
            self.left_laser_button()
        elif self.right_laser_activated:
            self.right_laser_button()
        
        buttons_to_disable = [self.ui.pushButton_laserAllActivate,
                              self.ui.pushButton_laserLeftActivate,
                              self.ui.pushButton_laserRightActivate]
        for button in buttons_to_disable:
            if disable_button:
                button.setEnabled(False)
            else:
                button.setEnabled(True)
    
    def update_motor_buttons(self, disable_button=True):
        '''Enable or disable all motor buttons'''
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
    
    def update_buttons_modes(self, buttons_to_enable):
        '''Update mode buttons status : disable buttons, except for those specified to be enabled'''
        aquisition_buttons = [self.ui.pushButton_acqStartStandbyMode,
                              self.ui.pushButton_acqStartPreviewMode,
                              self.ui.pushButton_acqStartLiveMode,
                              self.ui.pushButton_acqStartStackMode,
                              self.ui.pushButton_acqGetSingleImage,
                              self.ui.pushButton_acqSaveSingleImage,
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
    
    def close_modes(self):
        '''Close all thread modes if they are active'''
        if self.standby:
            self.stop_standby()
        if self.laser_on:
            self.stop_lasers()
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
    
    
    def set_data_consumer(self, consumer, wait, consumer_type, update_flag):
        ''' Regroups all the consumers in the same list'''
        self.consumers.append(consumer)
        self.consumers.append(wait)             ###Pas implémenté
        self.consumers.append(consumer_type)    
        self.consumers.append(update_flag)      ###Pas implémenté
    
    '''Motion Methods'''
    
    def updateUi_units(self):
        '''Updates all the widgets of the motion tab after an unit change'''
        self.units = self.ui.comboBox_units.currentText()
        
        if self.units == 'mm':
            self.decimals = 3
            self.fixformat = str('{:.3f} {}')
        elif self.units == '\u03BCm':
            self.decimals = 0
            self.fixformat = str('{:.0f} {}')
        
        increment_boxes = [self.ui.doubleSpinBox_sampleHStepSize,
                           self.ui.doubleSpinBox_sampleVStepSize,
                           self.ui.doubleSpinBox_cameraStepSize]
        position_boxes  = [self.ui.doubleSpinBox_sampleSetHPosition,
                           self.ui.doubleSpinBox_sampleSetVPosition,
                           self.ui.doubleSpinBox_cameraSetPosition]
        unit_boxes = increment_boxes + position_boxes
        
        '''Update suffixes'''
        for box in unit_boxes:
            box.setSuffix(" {}".format(self.units))
            box.setDecimals(self.decimals)
        for box in increment_boxes:
            box.setMinimum(10**-self.decimals)
            box.setValue(1)
        
        '''Update maximum and minimum values for horizontal sample motion'''
        self.ui.doubleSpinBox_sampleSetHPosition.setMinimum(self.motors.horizontal.get_limit_low(self.units))
        self.ui.doubleSpinBox_sampleSetHPosition.setMaximum(self.motors.horizontal.get_limit_high(self.units))
        maximum_horizontal_increment = self.motors.horizontal.get_limit_high(self.units) - self.motors.horizontal.get_limit_low(self.units)
        self.ui.doubleSpinBox_sampleHStepSize.setMaximum(maximum_horizontal_increment)
        
        '''Update maximum and minimum values for vertical sample motion'''
        self.ui.doubleSpinBox_sampleSetVPosition.setMinimum(self.motors.vertical.get_limit_low(self.units))
        self.ui.doubleSpinBox_sampleSetVPosition.setMaximum(self.motors.vertical.get_limit_high(self.units))
        maximum_vertical_increment = self.motors.vertical.get_limit_high(self.units) - self.motors.vertical.get_limit_low(self.units)
        self.ui.doubleSpinBox_sampleVStepSize.setMaximum(maximum_vertical_increment)
        
        '''Update maximum and minimum values for camera motion'''
        self.ui.doubleSpinBox_cameraSetPosition.setMinimum(self.motors.camera.get_limit_low(self.units))
        self.ui.doubleSpinBox_cameraSetPosition.setMaximum(self.motors.camera.get_limit_high(self.units))
        maximum_camera_increment = self.motors.camera.get_limit_high(self.units) - self.motors.camera.get_limit_low(self.units)
        self.ui.doubleSpinBox_cameraStepSize.setMaximum(maximum_camera_increment)
        
        '''Update current positions'''
        self.updateUi_position_vertical()
        self.updateUi_position_horizontal()
        self.updateUi_position_camera()
    
    def updateUi_position_horizontal(self):
        '''Updates the current horizontal sample position displayed'''
        self.current_horizontal_position_text = self.fixformat.format(self.motors.horizontal.get_position(self.units), self.units)
        self.ui.label_sampleCurrentHPosition.setText(self.current_horizontal_position_text)
    
    def updateUi_position_vertical(self):
        '''Updates the current vertical sample position displayed'''
        self.current_vertical_position_text = self.fixformat.format(self.motors.vertical.get_position(self.units), self.units)
        self.ui.label_sampleCurrentVPosition.setText(self.current_vertical_position_text)
        
    def updateUi_position_camera(self):
        '''Updates the current camera position displayed'''
        self.current_camera_position_text = self.fixformat.format(self.motors.camera.get_position(self.units), self.units)
        self.ui.label_cameraCurrentPosition.setText(self.current_camera_position_text)
    
    def move_to_horizontal_position(self):
        '''Moves the sample to a specified horizontal position'''
        if ((self.ui.doubleSpinBox_sampleSetHPosition.value() >= self.motors.horizontal.get_limit_low(self.units)) and (self.ui.doubleSpinBox_sampleSetHPosition.value() <= self.motors.horizontal.get_limit_high(self.units))):
            self.motors.horizontal.move_absolute_position(self.ui.doubleSpinBox_sampleSetHPosition.value(), self.units)
            self.status_printer('Sample moving to horizontal position')
            self.updateUi_position_horizontal()
        else:
            self.status_printer('Out of boundaries')
            self.sig_beep.emit(True)
    
    def move_to_vertical_position(self):
        '''Moves the sample to a specified vertical position'''
        if ((self.ui.doubleSpinBox_sampleSetVPosition.value() >= self.motors.vertical.get_limit_low(self.units)) and (self.ui.doubleSpinBox_sampleSetVPosition.value() <= self.motors.vertical.get_limit_high(self.units))):
            self.motors.vertical.move_absolute_position(self.ui.doubleSpinBox_sampleSetVPosition.value(), self.units)
            self.status_printer ('Sample moving to vertical position')
            self.updateUi_position_vertical()
        else:
            self.status_printer('Out of boundaries')
            self.sig_beep.emit(True)

    def move_sample_to_origin(self):
        '''Moves vertical and horizontal sample motors to origin position'''
        if (self.motors.horizontal.get_origin(self.units) <= self.motors.horizontal.get_limit_high(self.units)) and (self.motors.horizontal.get_origin(self.units) >= self.motors.horizontal.get_limit_low(self.units)):
            '''Moving sample to horizontal origin'''
            self.motors.horizontal.move_absolute_position(self.motors.horizontal.get_origin(self.units), self.units)
            self.status_printer('Moving to horizontal origin')
            self.updateUi_position_horizontal()
        else:
            self.sig_beep.emit(True)
            self.status_printer('Horizontal origin out of boundaries')
        
        if (self.motors.vertical.get_origin(self.units) <= self.motors.vertical.get_limit_high(self.units)) and (self.motors.vertical.get_origin(self.units) >= self.motors.vertical.get_limit_low(self.units)):
            '''Moving sample to vertical origin'''
            self.motors.vertical.move_absolute_position(self.motors.vertical.get_origin(self.units), self.units)
            self.status_printer('Moving to vertical origin')
            self.updateUi_position_vertical()
        else:
            self.sig_beep.emit(True)
            self.status_printer('Vertical origin out of boundaries')

    def move_camera_to_position(self):
        '''Moves the sample to a specified vertical position'''
        if ((self.ui.doubleSpinBox_cameraSetPosition.value() >= self.motors.camera.get_limit_low(self.units)) and (self.ui.doubleSpinBox_cameraSetPosition.value() <= self.motors.camera.get_limit_high(self.units))):
            self.motors.camera.move_absolute_position(self.ui.doubleSpinBox_cameraSetPosition.value(), self.units)
            self.status_printer ('Camera moving to position')
            self.updateUi_position_camera()
        else:
            self.status_printer('Out of boundaries')
            self.sig_beep.emit(True)

    def move_camera_to_focus(self):
        '''Moves camera to focus position'''
        if self.focus_selected:
            if self.motors.camera.get_origin(self.units) > self.motors.camera.get_limit_high(self.units):
                self.motors.camera.move_absolute_position(self.motors.camera.get_limit_high(), self.units)
                self.status_printer('Focus out of boundaries')
                self.sig_beep.emit(True)
                self.updateUi_position_camera()
            elif self.motors.camera.get_origin(self.units) < self.motors.camera.get_limit_low(self.units):
                self.motors.camera.move_absolute_position(self.motors.camera.get_limit_low(self.units), self.units)
                self.status_printer('Focus out of boundaries')
                self.sig_beep.emit(True)
                self.updateUi_position_camera()
            else:
                self.motors.camera.move_absolute_position(self.motors.camera.get_origin(self.units), self.units)
                self.status_printer('Moving to focus')
                self.updateUi_position_camera()
        else:
            self.motors.camera.move_absolute_position(self.motors.camera.get_origin(self.units), self.units)
            self.status_printer('Focus not yet set. Moving camera to default focus')
            self.updateUi_position_camera()

    def move_sample_backward(self):
        '''Sample motor backward horizontal motion'''
        if self.motors.horizontal.get_position(self.units) - self.ui.doubleSpinBox_sampleHStepSize.value() >= self.motors.horizontal.get_limit_low(self.units):
            self.motors.horizontal.move_relative_position(-self.ui.doubleSpinBox_sampleHStepSize.value(), self.units)
            self.status_printer ('Sample moving backward')
            self.updateUi_position_horizontal()
        else:
            self.motors.horizontal.move_absolute_position(self.motors.horizontal.get_limit_low(self.units), self.units)
            self.status_printer('Out of boundaries')
            self.sig_beep.emit(True)
            self.updateUi_position_horizontal()

    def move_sample_forward(self):
        '''Sample motor forward horizontal motion'''
        if self.motors.horizontal.get_position(self.units) + self.ui.doubleSpinBox_sampleHStepSize.value() <= self.motors.horizontal.get_limit_high(self.units):
            self.motors.horizontal.move_relative_position(self.ui.doubleSpinBox_sampleHStepSize.value(), self.units)
            self.status_printer('Sample moving forward')
            self.updateUi_position_horizontal()
        else:
            self.motors.horizontal.move_absolute_position(self.motors.horizontal.get_limit_high(self.units), self.units)
            self.status_printer('Out of boundaries')
            self.sig_beep.emit(True)
            self.updateUi_position_horizontal()

    def move_sample_down(self):
        '''Sample motor downward vertical motion'''
        if self.motors.vertical.get_position(self.units) - self.ui.doubleSpinBox_sampleVStepSize.value() >= self.motors.vertical.get_limit_low(self.units):
            self.motors.vertical.move_relative_position(-self.ui.doubleSpinBox_sampleVStepSize.value(), self.units)
            self.status_printer('Sample stepping down')
            self.updateUi_position_vertical()
        else:
            self.motors.vertical.move_absolute_position(self.motors.vertical.get_limit_low(self.units), self.units)
            self.status_printer('Out of boundaries')
            self.sig_beep.emit(True)
            self.updateUi_position_vertical()
    
    def move_sample_up(self):
        '''Sample motor upward vertical motion'''
        if self.motors.vertical.get_position(self.units) + self.ui.doubleSpinBox_sampleVStepSize.value() <= self.motors.vertical.get_limit_high(self.units):
            self.motors.vertical.move_relative_position(self.ui.doubleSpinBox_sampleVStepSize.value(), self.units)
            self.status_printer('Sample stepping up')
            self.updateUi_position_vertical()
        else:
            self.motors.vertical.move_absolute_position(self.motors.vertical.get_limit_high(self.units), self.units)
            self.status_printer('Out of boundaries')
            self.sig_beep.emit(True)
            self.updateUi_position_vertical()

    def move_camera_backward(self):
        '''Camera motor backward horizontal motion'''
        if self.motors.camera.get_position(self.units) - self.ui.doubleSpinBox_cameraStepSize.value() >= self.motors.camera.get_limit_low(self.units):
            self.motors.camera.move_relative_position(-self.ui.doubleSpinBox_cameraStepSize.value(), self.units)
            self.status_printer ('Camera stepping backward')
            self.updateUi_position_camera()
        else:
            self.motors.camera.move_absolute_position(self.motors.camera.get_limit_low(self.units), self.units)
            self.status_printer('Out of boundaries')
            self.sig_beep.emit(True)
            self.updateUi_position_camera()

    def move_camera_forward(self):
        '''Camera motor forward horizontal motion'''
        if self.motors.camera.get_position(self.units) + self.ui.doubleSpinBox_cameraStepSize.value() <= self.motors.camera.get_limit_high(self.units):
            self.motors.camera.move_relative_position(self.ui.doubleSpinBox_cameraStepSize.value(), self.units)
            self.status_printer ('Camera stepping forward')
            self.updateUi_position_camera()
        else:
            self.motors.camera.move_absolute_position(self.motors.camera.get_limit_high(self.units), self.units)
            self.status_printer('Out of boundaries')
            self.sig_beep.emit(True)
            self.updateUi_position_camera()


    def reset_boundaries(self):
        '''Reset variables for setting sample's horizontal motion range 
           (to avoid hitting the glass walls)'''
        self.ui.pushButton_calHorizontalSetForwardLimit.setEnabled(True)
        self.ui.pushButton_calHorizontalSetBackwardLimit.setEnabled(True)
        self.ui.label_calibrateRange.setText("Move Horizontal Position")

        #self.upperBoundarySelected = False
        #self.lowerBoundarySelected = False
        self.ui.pushButton_calHorizontalStartRangeSelection.setEnabled(False)
        
        '''Default boundaries'''
        self.motors.horizontal.set_limit_low(0, self.units)
        self.motors.horizontal.set_limit_high(0, self.units)

        self.updateUi_units() 
    
    def set_horizontal_backward_boundary(self):
        '''Set lower limit of sample's horizontal motion 
           (to avoid hitting the glass walls)'''
        self.motors.horizontal.set_limit_low(self.motors.horizontal.get_position(self.units), self.units)
        self.updateUi_units()
        self.horizontal_backward_boundary_selected = True
        self.ui.pushButton_calHorizontalSetBackwardLimit.setEnabled(False)
        if self.horizontal_forward_boundary_selected:
            self.ui.pushButton_calHorizontalStartRangeSelection.setEnabled(True)
            self.ui.label_calibrateRange.setText('Press Calibrate Range To Start')
    
    def set_horizontal_forward_boundary(self):
        '''Set upper limit of sample's horizontal motion 
           (to avoid hitting the glass walls)'''
        self.motors.horizontal.set_limit_high(self.motors.horizontal.get_position(self.units), self.units)
        self.updateUi_units()
        self.horizontal_forward_boundary_selected = True
        self.ui.pushButton_calHorizontalSetForwardLimit.setEnabled(False)
        if self.horizontal_backward_boundary_selected:
            self.ui.pushButton_calHorizontalStartRangeSelection.setEnabled(True)
            self.ui.label_calibrateRange.setText('Press Calibrate Range To Start')
    
    def set_sample_origin(self):
        '''Modifies the sample origin position'''
        self.motors.horizontal.set_origin(self.motors.horizontal.get_position(self.units), self.units)
        self.motors.vertical.set_origin(self.motors.vertical.get_position(self.units), self.units)
        origin_text = 'Origin set at (x,z) = ({}, {}) {}'.format(self.motors.horizontal.get_origin(self.units), self.motors.vertical.get_origin(self.units), self.units)
        self.status_printer(origin_text)
 
    def set_camera_focus(self):
        '''Modifies manually the camera focus position'''
        self.focus_selected = True
        self.motors.camera.set_origin(self.motors.camera.get_position(self.units), self.units)
        self.status_printer('Camera focus manually set a {} mm'.format(self.motors.camera.get_origin(self.units)))

    def calculate_camera_focus(self):
        '''Interpolates the camera focus position'''
        # Current sample position
        current_position = self.motors.horizontal.get_position(self.units)
        # Compute corresponding optimal focus position
        focus_regression = self.slope_camera * current_position + self.intercept_camera
        self.motors.camera.set_origin(focus_regression, self.units)
        print('focus_regression:' + str(focus_regression)) #debugging
        self.focus_selected = True
        self.status_printer('Focus automatically set')
    
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
        
    '''Parameters Methods'''
    
#    def back_to_default_parameters(self):
#        '''Change all the modifiable parameters to go back to the initial state'''
#        self.parameters = copy.deepcopy(self.defaultParameters)
#        for param_string, param_box in zip(modifiable_parameters,self.modifiable_param_boxes):
#            param_box.setValue(self.parameters[param_string]) 
    
#    def change_default_parameters(self):
#        '''Change all the default modifiable parameters to the current parameters'''
#        for param_string,param_box in zip(modifiable_parameters,self.modifiable_param_boxes):
#            self.defaultParameters[param_string] = param_box.value()
#        self.status_printer('Default parameters changed')
    
#    def save_default_parameters(self):
#        '''Change all the default parameters of the configuration file to current default parameters'''
#        config_file = r"configuration.txt"
#        if self.save_parameters_policy == 0: #Save Default Parameters
#            with open(config_file,"w") as file:
#                for param_string in modifiable_parameters:
#                    file.write(str(self.defaultParameters[param_string]) + '\n')
#                file.write(str(self.save_parameters_policy) + '\n')
#                file.write(str(self.default_save_directory)+ '\n')
#                file.write(str(self.default_filename))
#        elif self.save_parameters_policy == 1: #Save Last Parameters As Default
#            with open(config_file,"w") as file:
#                for param_box in self.modifiable_param_boxes:
#                    file.write(str(param_box.value()) + '\n')
#                file.write(str(self.save_parameters_policy) + '\n')
#                file.write(str(self.default_save_directory)+ '\n')
#                file.write(str(self.default_filename))

    def updateUi_cfg_settings(self):
        # Apply configurable settings to UI
        self.ui.doubleSpinBox_paramSampleRate.setValue(float(self.cfg_settings['Sample Clock Rate']))
        self.ui.doubleSpinBox_galvoFrequency.setValue(float(self.cfg_settings['Galvo Frequency']))
        self.ui.doubleSpinBox_galvoLeftAmplitude.setValue(float(self.cfg_settings['Galvo Left Amplitude']))
        self.ui.doubleSpinBox_galvoRightAmplitude.setValue(float(self.cfg_settings['Galvo Right Amplitude']))
        self.ui.doubleSpinBox_galvoLeftOffset.setValue(float(self.cfg_settings['Galvo Left Offset']))
        self.ui.doubleSpinBox_galvoRightOffset.setValue(float(self.cfg_settings['Galvo Right Offset']))
        self.ui.doubleSpinBox_etlLeftAmplitude.setValue(float(self.cfg_settings['ETL Left Amplitude']))
        self.ui.doubleSpinBox_etlRightAmplitude.setValue(float(self.cfg_settings['ETL Right Amplitude']))
        self.ui.doubleSpinBox_etlLeftOffset.setValue(float(self.cfg_settings['ETL Left Offset']))
        self.ui.doubleSpinBox_etlRightOffset.setValue(float(self.cfg_settings['ETL Right Offset']))
        self.ui.doubleSpinBox_etlSteps.setValue(float(self.cfg_settings['ETL Steps']))
        self.ui.doubleSpinBox_laserLeftAmplitude.setValue(float(self.cfg_settings['Laser Left Amplitude']))
        self.ui.doubleSpinBox_laserRightAmplitude.setValue(float(self.cfg_settings['Laser Right Amplitude']))

    def updateUi_galvo_left_amplitude(self):
        # Adjust Min and Max to prevent amplitude + offset being <-10V or > 10V
        self.ui.doubleSpinBox_galvoLeftOffset.setMinimum(-10 + self.ui.doubleSpinBox_galvoLeftAmplitude.value())
        self.ui.doubleSpinBox_galvoLeftOffset.setMaximum(10 - self.ui.doubleSpinBox_galvoLeftAmplitude.value()) 
        if self.ui.checkBox_galvoSync.isChecked():
            self.ui.doubleSpinBox_galvoRightAmplitude.setValue(self.ui.doubleSpinBox_galvoLeftAmplitude.value())
            self.ui.doubleSpinBox_galvoRightOffset.setValue(self.ui.doubleSpinBox_galvoLeftOffset.value())
            self.ui.doubleSpinBox_galvoRightOffset.setMinimum(self.ui.doubleSpinBox_galvoLeftOffset.minimum())
            self.ui.doubleSpinBox_galvoRightOffset.setMaximum(self.ui.doubleSpinBox_galvoLeftOffset.maximum()) 

    def updateUi_galvo_right_amplitude(self):
        # Adjust Min and Max to prevent amplitude + offset being <-10V or > 10V
        self.ui.doubleSpinBox_galvoRightOffset.setMinimum(-10 + self.ui.doubleSpinBox_galvoRightAmplitude.value())
        self.ui.doubleSpinBox_galvoRightOffset.setMaximum(10 - self.ui.doubleSpinBox_galvoRightAmplitude.value()) 
        if self.ui.checkBox_galvoSync.isChecked():
            self.ui.doubleSpinBox_galvoLeftAmplitude.setValue(self.ui.doubleSpinBox_galvoRightAmplitude.value())
            self.ui.doubleSpinBox_galvoLeftOffset.setValue(self.ui.doubleSpinBox_galvoRightOffset.value())
            self.ui.doubleSpinBox_galvoLeftOffset.setMinimum(self.ui.doubleSpinBox_galvoRightOffset.minimum())
            self.ui.doubleSpinBox_galvoLeftOffset.setMaximum(self.ui.doubleSpinBox_galvoRightOffset.maximum()) 

    def updateUi_galvo_left_offset(self):
        if self.ui.checkBox_galvoSync.isChecked():
            self.ui.doubleSpinBox_galvoRightAmplitude.setValue(self.ui.doubleSpinBox_galvoLeftAmplitude.value())
            self.ui.doubleSpinBox_galvoRightOffset.setValue(self.ui.doubleSpinBox_galvoLeftOffset.value())
            self.ui.doubleSpinBox_galvoRightOffset.setMinimum(self.ui.doubleSpinBox_galvoLeftOffset.minimum())
            self.ui.doubleSpinBox_galvoRightOffset.setMaximum(self.ui.doubleSpinBox_galvoLeftOffset.maximum()) 

    def updateUi_galvo_right_offset(self):
        if self.ui.checkBox_galvoSync.isChecked():
            self.ui.doubleSpinBox_galvoLeftAmplitude.setValue(self.ui.doubleSpinBox_galvoRightAmplitude.value())
            self.ui.doubleSpinBox_galvoLeftOffset.setValue(self.ui.doubleSpinBox_galvoRightOffset.value())
            self.ui.doubleSpinBox_galvoLeftOffset.setMinimum(self.ui.doubleSpinBox_galvoRightOffset.minimum())
            self.ui.doubleSpinBox_galvoLeftOffset.setMaximum(self.ui.doubleSpinBox_galvoRightOffset.maximum()) 

    def updateUi_galvo_sync(self):
        if self.ui.checkBox_galvoSync.isChecked():
            self.ui.doubleSpinBox_galvoRightAmplitude.setValue(self.ui.doubleSpinBox_galvoLeftAmplitude.value())
            self.ui.doubleSpinBox_galvoRightOffset.setValue(self.ui.doubleSpinBox_galvoLeftOffset.value())
            self.ui.doubleSpinBox_galvoRightOffset.setMinimum(self.ui.doubleSpinBox_galvoLeftOffset.minimum())
            self.ui.doubleSpinBox_galvoRightOffset.setMaximum(self.ui.doubleSpinBox_galvoLeftOffset.maximum()) 

    def updateUi_etl_left_amplitude(self):
        # Adjust Min and Max to prevent amplitude + offset being <-5V or > 5V
        self.ui.doubleSpinBox_etlLeftOffset.setMinimum(-5 + self.ui.doubleSpinBox_etlLeftAmplitude.value())
        self.ui.doubleSpinBox_etlLeftOffset.setMaximum(5 - self.ui.doubleSpinBox_etlLeftAmplitude.value()) 
        if self.ui.checkBox_etlSync.isChecked():
            self.ui.doubleSpinBox_etlRightAmplitude.setValue(self.ui.doubleSpinBox_etlLeftAmplitude.value())
            self.ui.doubleSpinBox_etlRightOffset.setValue(self.ui.doubleSpinBox_etlLeftOffset.value())
            self.ui.doubleSpinBox_etlRightOffset.setMinimum(self.ui.doubleSpinBox_etlLeftOffset.minimum())
            self.ui.doubleSpinBox_etlRightOffset.setMaximum(self.ui.doubleSpinBox_etlLeftOffset.maximum())

    def updateUi_etl_right_amplitude(self):
        # Adjust Min and Max to prevent amplitude + offset being <-5V or > 5V
        self.ui.doubleSpinBox_etlRightOffset.setMinimum(-5 + self.ui.doubleSpinBox_etlRightAmplitude.value())
        self.ui.doubleSpinBox_etlRightOffset.setMaximum(5 - self.ui.doubleSpinBox_etlRightAmplitude.value()) 
        if self.ui.checkBox_etlSync.isChecked():
            self.ui.doubleSpinBox_etlLeftAmplitude.setValue(self.ui.doubleSpinBox_etlRightAmplitude.value())
            self.ui.doubleSpinBox_etlLeftOffset.setValue(self.ui.doubleSpinBox_etlRightOffset.value())
            self.ui.doubleSpinBox_etlLeftOffset.setMinimum(self.ui.doubleSpinBox_etlRightOffset.minimum())
            self.ui.doubleSpinBox_etlLeftOffset.setMaximum(self.ui.doubleSpinBox_etlRightOffset.maximum()) 

    def updateUi_etl_left_offset(self):
        if self.ui.checkBox_etlSync.isChecked():
            self.ui.doubleSpinBox_etlRightAmplitude.setValue(self.ui.doubleSpinBox_etlLeftAmplitude.value())
            self.ui.doubleSpinBox_etlRightOffset.setValue(self.ui.doubleSpinBox_etlLeftOffset.value())
            self.ui.doubleSpinBox_etlRightOffset.setMinimum(self.ui.doubleSpinBox_etlLeftOffset.minimum())
            self.ui.doubleSpinBox_etlRightOffset.setMaximum(self.ui.doubleSpinBox_etlLeftOffset.maximum())

    def updateUi_etl_right_offset(self):
        if self.ui.checkBox_etlSync.isChecked():
            self.ui.doubleSpinBox_etlLeftAmplitude.setValue(self.ui.doubleSpinBox_etlRightAmplitude.value())
            self.ui.doubleSpinBox_etlLeftOffset.setValue(self.ui.doubleSpinBox_etlRightOffset.value())
            self.ui.doubleSpinBox_etlLeftOffset.setMinimum(self.ui.doubleSpinBox_etlRightOffset.minimum())
            self.ui.doubleSpinBox_etlLeftOffset.setMaximum(self.ui.doubleSpinBox_etlRightOffset.maximum()) 

    def updateUi_etl_sync(self):
        if self.ui.checkBox_etlSync.isChecked():
            self.ui.doubleSpinBox_etlRightAmplitude.setValue(self.ui.doubleSpinBox_etlLeftAmplitude.value())
            self.ui.doubleSpinBox_etlRightOffset.setValue(self.ui.doubleSpinBox_etlLeftOffset.value())
            self.ui.doubleSpinBox_etlRightOffset.setMinimum(self.ui.doubleSpinBox_etlLeftOffset.minimum())
            self.ui.doubleSpinBox_etlRightOffset.setMaximum(self.ui.doubleSpinBox_etlLeftOffset.maximum())


    def lasers_button(self):
        '''Activate or deactivate lasers, depending on the button status'''
        if self.both_lasers_activated:
            self.both_lasers_activated = False
            self.status_printer('All Lasers Off')
            self.ui.pushButton_laserAllActivate.setText('Activate All Lasers')
            self.ui.pushButton_laserLeftActivate.setEnabled(True)
            self.ui.pushButton_laserRightActivate.setEnabled(True)
        else:
            self.both_lasers_activated = True
            self.status_printer('All Lasers On')
            self.ui.pushButton_laserAllActivate.setText('Deactivate All Lasers')
            self.ui.pushButton_laserLeftActivate.setEnabled(False)
            self.ui.pushButton_laserRightActivate.setEnabled(False)
    
    def left_laser_button(self):
        '''Activate or deactivate left laser, depending on the button status'''
        if self.left_laser_activated:
            self.left_laser_activated = False
            self.status_printer('Left Laser Off')
            self.ui.pushButton_laserAllActivate.setEnabled(True)
            self.ui.pushButton_laserLeftActivate.setText('Activate Left Laser')
            self.ui.pushButton_laserRightActivate.setEnabled(True)
        else:
            self.left_laser_activated = True
            self.status_printer('Left Laser On')
            self.ui.pushButton_laserAllActivate.setEnabled(False)
            self.ui.pushButton_laserLeftActivate.setText('Deactivate Left Laser')
            self.ui.pushButton_laserRightActivate.setEnabled(False)
            
    def right_laser_button(self):
        '''Activate or deactivate right laser, depending on the button status'''
        if self.right_laser_activated:
            self.right_laser_activated = False
            self.status_printer('Right Laser Off')
            self.ui.pushButton_laserAllActivate.setEnabled(True)
            self.ui.pushButton_laserLeftActivate.setEnabled(True)
            self.ui.pushButton_laserRightActivate.setText('Activate Right Laser')
        else:
            self.right_laser_activated = True
            self.status_printer('Right Laser On')
            self.ui.pushButton_laserAllActivate.setEnabled(False)
            self.ui.pushButton_laserLeftActivate.setEnabled(False)
            self.ui.pushButton_laserRightActivate.setText('Deactivate Right Laser')

    def start_lasers(self):
        '''Starts the lasers at a certain voltage'''
        self.laser_on = True

        self.lasers_task = nidaqmx.Task()
        self.lasers_task.ao_channels.add_ao_voltage_chan(self._terminals["lasers"])

        '''Setting up voltage'''
        left_laser_voltage = 0  #Default voltage of 0V
        right_laser_voltage = 0 #Default voltage of 0V
        
        if self.both_lasers_activated:
            left_laser_voltage = self.cfg_settings['Left Laser Voltage']
            right_laser_voltage = self.cfg_settings['Right Laser Voltage']   
        if self.left_laser_activated:
            left_laser_voltage = self.cfg_settings['Left Laser Voltage']  
        if self.right_laser_activated:
            right_laser_voltage = self.cfg_settings['Right Laser Voltage']
        
        self.lasers_waveforms = np.stack((np.array([right_laser_voltage]), np.array([left_laser_voltage])))   
        
        '''Writing voltage'''
        self.lasers_task.write(self.lasers_waveforms, auto_start = True)
    
    def stop_lasers(self):
        '''Stops the lasers, puts their voltage to zero'''
        self.laser_on = False
        
        '''Writing voltage'''
        waveforms = np.stack(([0],[0]))
        self.lasers_task.write(waveforms)
        
        '''Ending task'''
        self.lasers_task.stop()
        self.lasers_task.close()
        
        '''Deactivating lasers'''
        if self.both_lasers_activated:
            self.both_lasers_activated = False
        if self.left_laser_activated:
            self.left_laser_activated = False
        if self.right_laser_activated:
            self.right_laser_activated = False
 
 
    '''File Open Methods'''
        
    def select_file(self):
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
            self.status_printer('File ' + self.open_directory + ' opened')
            self.ui.pushButton_selectDataset.setEnabled(True)
        else:
            self.ui.label_currentFileDirectory.setText('None Specified')
    
    def select_dataset(self):
        '''Opens one or many HDF5 datasets and displays its attributes and data as an image'''
        
        if (self.open_directory != '') and (self.ui.listWidget_fileDatasets.count() != 0):
            for item in range(len(self.ui.listWidget_fileDatasets.selectedItems())):
                self.dataset_name = self.ui.listWidget_fileDatasets.selectedItems()[item].text()
                with h5py.File(self.open_directory, "r") as f:
                    dataset = f[self.dataset_name]
                    
                    '''Display attributes of the first selected dataset'''
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
                    
                    '''Display image'''
                    data = dataset[()]
                    plt.figure('Figure ' + str(self.figure_counter) + ': ' + self.open_directory + ' (' + self.dataset_name + ')')
                    plt.imshow(data,cmap = 'gray')
                    plt.show(block = False)   #Prevents the plot from blocking the execution of the code...
                    self.figure_counter += 1
                    
                    ##'''Convert to tiff format'''
                    ## tiff = Image.fromarray(data)
                    ##tiff_filename = self.open_directory.replace('.hdf5', '.tiff')
                    ##tiff.save(tiff_filename)
                
                self.status_printer('Dataset ' + self.dataset_name + ' of file ' + self.open_directory + ' displayed')
    
    
    '''Acquisition Modes Methods'''
    def standby_button(self):
        '''Start or stop standby, depending on the button status'''
        if self.standby:
            self.ui.pushButton_acqStartStandbyMode.setText('Start Standby')
            self.stop_standby()
        else:
            self.ui.pushButton_acqStartStandbyMode.setText('Stop Standby')
            self.start_standby()
    
    def start_standby(self):
        '''Initiates task to keep ETLs'currents at 0A while
           the microscope is not in use'''

        # Stop acquisition mode if any
        self.close_modes()
        
        # Create ETL standby task
        self.standby_task = nidaqmx.Task()
        self.standby_task.ao_channels.add_ao_voltage_chan('/Dev1/ao2:3')
        
        etl_voltage = 2.5 #In volts, corresponds to a current of 0
        standby_waveform = np.stack((np.array([etl_voltage]),np.array([etl_voltage])))
        
        # Inject voltage
        self.standby_task.write(standby_waveform, auto_start = True)
        
        # Disable some buttons while in standby
        self.update_buttons_modes([self.pushButton_acqStartStandbyMode])
        
        # Set flag and report
        self.standby = True
        self.status_printer('Standby on')


    def stop_standby(self):
        '''Exit standby mode'''

        # Stop/close ETL standby task
        self.standby_task.stop()
        self.standby_task.close()
        
        # Re-enable some buttons after standby
        self.update_buttons_modes(self.default_buttons)
        
        # Set flag and report
        self.standby = False
        self.status_printer('Standby off')
    
    
    def send_frame_to_consumer(self, frame, to_cam_window = True, to_saver = False):
        '''Tries to add a frame to a consumer, either the camera window or the saver'''
        
        for consumer in range(0, len(self.consumers), 4):
            if to_cam_window:
                if self.consumers[consumer+2] == 'CameraWindow':
                    try:
                        self.consumers[consumer].put(frame)
                    except:
                        pass
            if to_saver:
                if self.consumers[consumer+2] == 'FrameSaver':
                    try:
                        self.consumers[consumer].put(frame,1)
                    except:
                        pass
    

    def preview_button(self):
        '''Start or stop preview mode, depending on the button status'''
        if self.preview_mode_started:
            self.preview_mode_started = False
            self.ui.pushButton_acqStartPreviewMode.setText('Start Preview Mode')
            self.update_laser_buttons()
        else:
            self.close_modes()
            self.preview_mode_started = True
            self.update_buttons_modes([self.ui.pushButton_acqStartPreviewMode])
            self.ui.pushButton_acqStartPreviewMode.setText('Stop Preview Mode')
            self.update_laser_buttons(False)
            self.start_preview_mode()
    
    def start_preview_mode(self):
        '''Initializes variables for preview modes where beam and focal 
           positions are manually controlled by the user'''
        
        '''Modes disabling during preview_mode execution'''
        self.update_buttons_modes([self.ui.pushButton_acqStartPreviewMode])
        self.status_printer('->Preview mode started')
        self.label_statusBar.setText('Current Acquisition Mode: Preview ')
        self.progress_statusBar.show()
        self.sig_update_progress.emit(100)
        
        '''Starting preview mode thread'''
        preview_mode_thread = threading.Thread(target = self.preview_mode_thread)
        preview_mode_thread.start()
    
    def preview_mode_thread(self):
        '''This thread allows the visualization and manual control of the 
           parameters of the beams in the UI. There is no scan here, 
           beams only changes when parameters are changed. This the preferred 
           mode for beam calibration'''
        
        '''Setting tasks'''
        self.preview_galvos_etls_task = nidaqmx.Task()
        self.preview_galvos_etls_task.ao_channels.add_ao_voltage_chan(self._terminals["galvos_etls"])
        
        '''Setting the camera for acquisition'''
        self.camera.set_trigger_mode('auto_trigger')
        self.camera.arm()

        '''Starting lasers'''
        self.start_lasers()

        while self.preview_mode_started:
            
            '''Setting data values'''
            left_galvo_voltage = self.cfg_settings['Left Galvo Amplitude'] + self.cfg_settings['Left Galvo Offset']
            right_galvo_voltage = self.cfg_settings['Right Galvo Amplitude'] + self.cfg_settings['Right Galvo Offset']
            left_etl_voltage = self.cfg_settings['Left ETL Amplitude'] + self.cfg_settings['Left ETL Offset']
            right_etl_voltage = self.cfg_settings['Right ETL Amplitude'] + self.cfg_settings['Right ETL Offset']
            
            '''Setting waveforms'''
            preview_galvos_etls_waveforms = np.stack((np.array([right_galvo_voltage]),
                                                      np.array([left_galvo_voltage]),
                                                      np.array([left_etl_voltage]),
                                                      np.array([right_etl_voltage])))
            '''Writing the data'''
            self.preview_galvos_etls_task.write(preview_galvos_etls_waveforms, auto_start = True)

            '''Retrieving image from camera and putting it in its queue for display'''
            self.camera.start_recorder(1)
            self.camera.monitor_recorder(1)
            self.camera.stop_recorder()
            cam_images = self.camera.get_images()
            frame = cam_images[0]
            self.camera.delete_recorder()

            frame = np.transpose(frame)
            self.send_frame_to_consumer(frame)

        '''Stopping lasers'''
        self.stop_lasers()

        '''Stopping camera'''
        self.camera.disarm()
        
        '''End tasks'''
        self.preview_galvos_etls_task.stop()
        self.preview_galvos_etls_task.close()
        
        '''Enabling modes after preview_mode'''
        self.update_buttons_modes(self.default_buttons)
        
        self.status_printer('->Preview mode stopped')
        self.label_statusBar.setText('')
        self.progress_statusBar.hide()
        self.sig_update_progress.emit(0)
    
    
    def reconstruct_frame(self,buffer):
        '''Reconstructs a frame from multiple frames'''
    
        reconstructed_frame = np.zeros((int(self.parameters["Rows"]), int(self.parameters["Columns"])), np.uint16)  #Initializing frame
        
        for frame in range(int(self.number_of_steps)):
            '''Uniformize frame intensities'''
            average = np.average(buffer[frame,0:100,:]) #Average the  first rows
            #print(str(frame)+' average:'+str(average))
            #print(buffer[1,:,:] == buffer[3,:,:])
            if frame == 0:
                reference_average = average
                #print('reference_average:'+str(reference_average))
            else:
                average_ratio = reference_average/average
                #print('average_ratio:'+str(average_ratio))
                buffer[frame,:,:] = buffer[frame,:,:] * average_ratio
            '''Reconstruct frame'''
            first_column = int(frame * self.parameters['ETL Step'])
            next_first_column = int(first_column + self.parameters['ETL Step'])
            if frame == int(self.number_of_steps-1):  #For the last column step (may be different than the others...)
                reconstructed_frame[:,first_column:] = buffer[frame,:,first_column:]
            else:
                reconstructed_frame[:,first_column:next_first_column] = buffer[frame,:,first_column:next_first_column]
        
        return reconstructed_frame
    
    def crop_buffer(self,buffer):
        '''Crops each frame of a buffer for a frame reconstruction'''
        
        if buffer.shape[0] == 1:
            reconstructed_buffer = buffer
        else:
            column_buffer = int(self.parameters["ETL Step"]*0.2)
            reconstructed_buffer = np.zeros((buffer.shape[0],int(self.parameters["Rows"]),int(self.parameters["ETL Step"]+ (2*column_buffer))), np.uint16)  #Initializing frame
    
            for frame in range(int(self.number_of_steps)):
                '''Uniformize frame intensities'''
                average = np.average(buffer[frame,0:100,:]) #Average the  first rows
                if frame == 0:
                    reference_average = average
                else:
                    average_ratio = reference_average/average
                    buffer[frame,:,:] = buffer[frame,:,:] * average_ratio
                '''Crop buffer'''
                first_column = int(frame * self.parameters['ETL Step'] - column_buffer)
                next_first_column = int(first_column + self.parameters['ETL Step'] + (2*column_buffer))
                if frame == 0:  #For the first column step
                    reconstructed_buffer[frame,:,column_buffer:] = buffer[frame,:,0:int(self.parameters['ETL Step'] + column_buffer)]
                elif frame == int(self.number_of_steps-1):  #For the last column step (may be different than the others...)
                    last_column_step = int(self.parameters["Columns"] - first_column)
                    reconstructed_buffer[frame,:,0:last_column_step] = buffer[frame,:,first_column:]
                else:
                    reconstructed_buffer[frame,:,:] = buffer[frame,:,first_column:next_first_column]
        
        return reconstructed_buffer
    
    def reconstruct_frame_from_cropped_buffer(self,cropped_buffer):
        '''Reconstructs a frame from multiple cropped frames (does some linear image stitching)'''
        
        column_buffer = int(self.parameters["ETL Step"]*0.2)
        weight_step = 1/(2*column_buffer)
        reconstructed_frame = np.zeros((int(self.parameters["Rows"]), int(self.parameters["Columns"])), np.uint16)  #Initializing frame
        
        for frame in range(int(self.number_of_steps)):
            first_center_column = int(frame * self.parameters['ETL Step'] + column_buffer)
            last_center_column = int((frame+1) * self.parameters['ETL Step'] - column_buffer)
            previous_last_center_column = int(frame * self.parameters['ETL Step'] - column_buffer)
            
            if frame == 0:  #For the first column step
                reconstructed_frame[:,0:last_center_column] = cropped_buffer[frame,:,column_buffer:int(self.parameters['ETL Step'])]
            else:
                for column in range(2*column_buffer):
                    frame_column = column + previous_last_center_column
                    last_buffer_column = column + int(self.parameters['ETL Step'])
                    buffer_weight = column * weight_step
                    last_buffer_weight = 1 - column * weight_step
                    reconstructed_frame[:,frame_column] = buffer_weight*cropped_buffer[frame,:,column] + last_buffer_weight*cropped_buffer[(frame-1),:,last_buffer_column]
                if frame == int(self.number_of_steps-1):  #For the last column step (may be different than the others...)
                    last_column_step = int(self.parameters["Columns"] - first_center_column)
                    reconstructed_frame[:,first_center_column:] = cropped_buffer[frame,:,(2*column_buffer):(2*column_buffer)+last_column_step]
                else:
                    reconstructed_frame[:,first_center_column:last_center_column] = cropped_buffer[frame,:,(2*column_buffer):int(self.parameters['ETL Step'])]

        return reconstructed_frame
    
    def get_single_image(self):
        '''Generate ETLs, galvos & camera's ramps, get a single reconstructed image and display it'''
        
        '''Creating ETLs, galvos & camera's ramps and waveforms'''
        self.ramps = AOETLGalvos(self.parameters)  
        self.ramps.create_tasks(self._terminals, 'FINITE')
        
        if self.ui.checkBox_etlActivate.isChecked():
            self.ramps.create_calibrated_etl_waveforms(self.left_slope, self.left_intercept, self.right_slope, self.right_intercept, activate = True)
        else:
            self.ramps.create_calibrated_etl_waveforms(self.left_slope, self.left_intercept, self.right_slope, self.right_intercept, activate = False)
        
        if self.ui.checkBox_galvoInvert.isChecked():
            self.ramps.create_galvos_waveforms(case = 'TRAPEZE', invert = True)
        else:
            self.ramps.create_galvos_waveforms(case = 'TRAPEZE', invert = False)

        self.ramps.create_digital_output_camera_waveform(case = 'STAIRS_FITTING')
            
        '''Writing waveform to task and running'''
        self.ramps.write_waveforms_to_tasks()                            
        self.number_of_steps = int(np.ceil(self.parameters["Columns"]/self.parameters["ETL Step"])) #Number of galvo sweeps in a frame, or alternatively the number of ETL focal step

        # Start camera recorder session before we start the scan/trigger task
        self.camera.start_recorder(self.number_of_steps)
        self.ramps.start_tasks()

        # Monitor completion of scan/trigger task and camera recorder session
        self.ramps.monitor_tasks()
        self.camera.monitor_recorder(self.number_of_steps)

        # Stop task and recorder session
        self.camera.stop_recorder()
        self.ramps.stop_tasks()                             

        # Recover images from the recorder
        images = self.camera.get_images()
        self.buffer = np.asarray(images)

        # Delete task and recorder session
        self.camera.delete_recorder()
#        self.ramps.stop_tasks()                             
        self.ramps.delete_tasks()

        # Frame reconstruction options
        if self.ui.checkBox_acqStitchFrames.isChecked():
            self.reconstructed_frame = self.reconstruct_frame_from_cropped_buffer(self.crop_buffer(self.buffer))
        else:
            self.reconstructed_frame = self.reconstruct_frame(self.buffer)
        frame = np.transpose(self.reconstructed_frame)

        # Send reconstructed frame to consumers
        self.send_frame_to_consumer(frame)
        
    
    def live_button(self):
        '''Start or stop live mode, depending on the button status'''
        if self.live_mode_started:
            self.live_mode_started = False
            self.ui.pushButton_acqStartLiveMode.setText('Start Live Mode')
            self.update_laser_buttons()
        else:
            self.close_modes()
            self.live_mode_started = True
            self.ui.pushButton_acqStartLiveMode.setText('Stop Live Mode')
            self.update_laser_buttons(False)
            self.start_live_mode()
    
    def start_live_mode(self):
        '''This mode is for visualizing (and modifying) the effects of the 
           chosen parameters of the ramps which will be sent for single image 
           saving or volume saving (with stack_mode)'''
        
        '''Disabling other modes while in live_mode'''
        self.update_buttons_modes([self.ui.pushButton_acqStartLiveMode])
        
        self.status_printer('->Live mode started')
        self.label_statusBar.setText('Current Acquisition Mode: Live ')
        self.progress_statusBar.show()
        self.sig_update_progress.emit(100)
        
        '''Starting live mode thread'''
        live_mode_thread = threading.Thread(target = self.live_mode_thread)
        live_mode_thread.start()
    
    def live_mode_thread(self):
        '''This thread allows the execution of live_mode while modifying
           parameters in the UI'''

        '''Moving the camera to focus'''
        ##self.move_camera_to_focus() 

        '''Setting the camera for acquisition'''
        self.camera.set_trigger_mode('external_exposure')
        self.camera.arm()
        
        '''Starting lasers'''
        self.start_lasers()
        
        while self.live_mode_started:
            '''Get single image'''
            self.get_single_image()
        
        '''Stopping lasers'''
        self.stop_lasers()

        '''Stopping camera'''
        self.camera.disarm()

        '''Enabling modes after live_mode'''
        self.update_buttons_modes(self.default_buttons)
        
        self.status_printer('->Live mode stopped')
        self.label_statusBar.setText('')
        self.progress_statusBar.hide()
        self.sig_update_progress.emit(0)
    
    
    def start_get_single_image(self):
        '''Generates and display a single frame which can be saved afterwards 
        using self.save_single_image()'''
        
        self.close_modes()
            
        '''Disabling modes while single frame acquisition'''
        self.update_buttons_modes(self.default_buttons)
        
        self.status_printer('->Getting single image')
        
        '''Moving the camera to focus'''
        ##self.move_camera_to_focus()
        
        '''Getting positions for the image'''
        self.image_hor_pos_text = self.current_horizontal_position_text
        self.image_ver_pos_text = self.current_vertical_position_text
        self.image_cam_pos_text = self.current_camera_position_text
        
        '''Setting the camera for acquisition'''
        self.camera.set_trigger_mode('external_exposure')
        self.camera.arm()

        '''Starting lasers'''
        self.both_lasers_activated = True
        self.start_lasers()
        
        '''Get single image'''
        self.get_single_image()
        
        '''Stopping lasers'''
        self.stop_lasers()
        self.both_lasers_activated = False

        '''Stopping camera'''            
        self.camera.disarm()

        '''Enabling modes after single frame acquisition'''
        self.default_buttons.append(self.ui.pushButton_acqSaveSingleImage)
        self.update_buttons_modes(self.default_buttons)
    
    def select_directory(self):
        '''Allows the selection of a directory for single_image or stack saving'''
        
        options = QFileDialog.Options()
        options |= QFileDialog.DontResolveSymlinks
        options |= QFileDialog.ShowDirsOnly
        self.save_directory = QFileDialog.getExistingDirectory(self, 'Choose Directory', '', options)
        
        if self.save_directory != '': #If directory specified
            self.ui.label_currentSaveDirectory.setText(self.save_directory)
            self.ui.lineEdit_filename.setEnabled(True)
            self.ui.lineEdit_filename.setText('')
            self.ui.lineEdit_sampleName.setEnabled(True)
        else:
            self.ui.label_currentSaveDirectory.setText('None Specified')
            self.ui.lineEdit_filename.setEnabled(False)
            self.ui.lineEdit_filename.setText('Select Directory First')
            self.ui.lineEdit_sampleName.setEnabled(False)
    
    def get_file_name(self):
        '''Retrieve filename set by the user'''
        self.filename = str(self.ui.lineEdit_filename.text())
        #Removing spaces, dots and commas in filename
        for symbol in [' ','.',',']:
            self.filename = self.filename.replace(symbol, '')
        
        if (self.save_directory != '') and (self.filename != ''):
            self.filename = self.save_directory + '/' + self.filename
            self.saving_allowed = True
        else:
            self.saving_allowed = False
    
    def get_sample_name(self):
        '''Retrieve sample name'''
        if str(self.ui.lineEdit_sampleName.text()) != '':
            parameters["Sample Name"] = str(self.ui.lineEdit_sampleName.text())
    
    def save_single_image(self):
        '''Saves the frame generated by self.get_single_image()'''
        
        '''Retrieving filename set by the user'''
        self.get_file_name()
        
        if self.saving_allowed:
            '''Setting up frame saver'''
            self.frame_saver = FrameSaver(self.status_printer)
            self.frame_saver.set_block_size(1) #Block size is a number of buffers ##
            self.frame_saver.add_motor_parameters(self.image_hor_pos_text,self.image_ver_pos_text,self.image_cam_pos_text)
            
            '''Getting sample name'''
            self.get_sample_name()
            
            '''Saving frame'''
            if self.ui.checkBox_acqSaveAllFrames.isChecked():
                self.frame_saver.set_files(1,self.filename,'singleImage',1,'ETLscan')
                cropped_buffer = self.crop_buffer(self.buffer)
                self.frame_saver.put(cropped_buffer,1)
                self.status_printer('Saving Images (one for each ETL scan)')
            else:
                self.frame_saver.set_files(1,self.filename,'singleImage',1,'reconstructed_frame')
                self.frame_saver.put(self.reconstructed_frame,1)
                self.status_printer('Saving Reconstructed Image')
            
            self.frame_saver.start_saving()
            self.frame_saver.stop_saving()
        else:
            self.show_single_save_popup()
            print('Select a directory and enter a valid filename before saving')
    
    def show_single_save_popup(self):
        '''Asks to select a directory and a filename before saving'''
        
        self.sig_beep.emit(True)
        single_save_popup = QMessageBox()
        single_save_popup.setWindowTitle('Save Single Image Warning')
        single_save_popup.setText('Select a directory and enter a valid filename before saving')
        single_save_popup.setIcon(QMessageBox.Warning)
        single_save_popup.setStandardButtons(QMessageBox.Ok)
        single_save_popup.setDefaultButton(QMessageBox.Ok)
        single_save_popup.exec_()

    
    def set_number_of_planes(self):
        '''Calculates the number of planes that will be saved in the stack 
           acquisition'''
        
        if self.ui.doubleSpinBox_acqPlaneStepSize.value() != 0:
            if self.ui.checkBox_acqFirstPlaneSet.isChecked() and self.ui.checkBox_acqLastPlaneSet.isChecked():
                self.number_of_planes = np.ceil(abs((self.stack_mode_ending_point-self.stack_mode_starting_point)/self.ui.doubleSpinBox_acqPlaneStepSize.value()))
                self.number_of_planes += 1   #Takes into account the initial plane
                self.ui.label_acqNumberOfPlanes.setText(str(self.number_of_planes))
        else:
            print('Set a non-zero value to plane step')
        
    def set_stack_mode_ending_point(self):
        '''Defines the ending point of the recorded stack volume'''
        self.stack_mode_ending_point = self.motors.horizontal.get_position('\u03BCm') #Units in micro-meters, because plane step is in micro-meters
        self.ui.checkBox_acqLastPlaneSet.setChecked(True)
        self.set_number_of_planes()
        
    def set_stack_mode_starting_point(self):
        '''Defines the starting point where the first plane of the stack volume will be recorded'''
        self.stack_mode_starting_point = self.motors.horizontal.get_position('\u03BCm') #Units in micro-meters, because plane step is in micro-meters
        self.ui.checkBox_acqFirstPlaneSet.setChecked(True)
        self.set_number_of_planes()
    
    def stack_button(self):
        '''Start or stop stack mode, depending on the button status'''
        if self.stack_mode_started:
            self.stack_mode_started = False
        else:
            self.close_modes()
            self.start_stack_mode()
    
    def start_stack_mode(self):
        '''Initializes variables for volume saving which will take place in 
           self.stack_mode_thread afterwards'''
        
        '''Making sure the limits of the volume are set'''
        if (self.ui.checkBox_acqFirstPlaneSet.isChecked() == False) or (self.ui.checkBox_acqLastPlaneSet.isChecked() == False) or (self.ui.doubleSpinBox_acqPlaneStepSize.value() == 0):
            print('Set starting and ending points and select a non-zero plane step value')
            self.show_stack_popup()
        else:
            '''Setting start & end points and plane step (takes into account the direction of acquisition) '''
            if self.stack_mode_starting_point > self.stack_mode_ending_point:
                self.step = -1 * self.ui.doubleSpinBox_acqPlaneStepSize.value()
                self.start_point = self.stack_mode_starting_point
                self.end_point = self.stack_mode_starting_point+self.step*(self.number_of_planes-1)
            else:
                self.step = self.ui.doubleSpinBox_acqPlaneStepSize.value()
                self.start_point = self.stack_mode_starting_point
                self.end_point = self.stack_mode_starting_point+self.step*(self.number_of_planes-1)
            
            '''Retrieving filename set by the user'''
            self.get_file_name()
            if self.saving_allowed:
                self.start_stack_thread()
            else:
                self.show_stack_save_popup()
    
    def show_stack_popup(self):
        '''Asks to set starting and ending points and select a non-zero plane step value'''
        
        self.sig_beep.emit(True)
        save_popup = QMessageBox()
        save_popup.setWindowTitle('Stack Acquisition Warning')
        save_popup.setText('Set starting and ending points and select a non-zero plane step value')
        save_popup.setIcon(QMessageBox.Warning)
        save_popup.setStandardButtons(QMessageBox.Ok)
        save_popup.setDefaultButton(QMessageBox.Ok)
        save_popup.exec_()
    
    def start_stack_thread(self):
        '''Starts the thread for stack mode'''
        
        self.ui.pushButton_acqStartStackMode.setText('Stop Stack Mode')
        self.label_statusBar.setText('Current Acquisition Mode: Stack ')
        self.sig_update_progress.emit(0) #To reset progress bar
        self.progress_statusBar.show()
        
        self.stack_mode_started = True
        '''Modes disabling while stack acquisition'''
        self.update_buttons_modes([self.ui.pushButton_acqStartStackMode])
        self.update_motor_buttons()
        
        self.status_printer('->Stack mode started -- Number of frames to save: ' + str(int(self.number_of_planes)))
        '''Starting stack mode thread'''
        stack_mode_thread = threading.Thread(target = self.stack_mode_thread)
        stack_mode_thread.start()
    
    def show_stack_save_popup(self):
        '''Asks if the stack acquisition whether is to be done without saving'''
        
        self.sig_beep.emit(True)
        save_popup = QMessageBox()
        save_popup.setWindowTitle('Stack Acquisition Question')
        save_popup.setText('Make stack acquisition without saving?')
        save_popup.setIcon(QMessageBox.Question)
        save_popup.setStandardButtons(QMessageBox.Yes|QMessageBox.No)
        save_popup.setDefaultButton(QMessageBox.Yes)
        save_popup.buttonClicked.connect(self.stack_popup_button)
        save_popup.exec_()
    
    def stack_popup_button(self,button):
        '''Takes action depending on the save_popup button that was clicked'''
        if button.text() == '&Yes': #& is necessary...
            self.start_stack_thread()
    
    def stack_mode_thread(self):
        ''' Thread for volume acquisition and saving'''
        
        '''Setting the camera for acquisition'''
        self.camera.set_trigger_mode('external_exposure')
        self.camera.arm()
       
        '''Making sure saving is allowed and filename isn't empty'''
        if self.saving_allowed:
            '''Setting frame saver'''
            self.frame_saver = FrameSaver(self.status_printer)
            self.frame_saver.set_block_size(3) #Block size is a number of buffers
            '''Getting sample name'''
            self.get_sample_name()
            
            self.set_data_consumer(self.frame_saver, False, "FrameSaver", True)
            
            '''Starting frame saver'''
            if self.ui.checkBox_acqSaveAllFrames.isChecked():
                self.frame_saver.set_files(self.number_of_planes,self.filename,'stack',1,'ETLscan')
            else:
                self.frame_saver.set_files(1,self.filename,'stack',self.number_of_planes,'reconstructed_frame')
            self.frame_saver.start_saving()
        else:
            print('Select directory and enter a valid filename to save')
        
        
        '''Starting lasers'''
        self.both_lasers_activated = True
        self.start_lasers()
        
        '''Set progress bar'''
        progress_value = 0
        progress_increment = 100/self.number_of_planes
        self.sig_update_progress.emit(0) #To reset progress bar
        
        for plane in range(int(self.number_of_planes)):
            if self.stack_mode_started == False:
                self.status_printer('Stack Acquisition Interrupted')
                break
            else:
                '''Moving sample position'''
                position = self.start_point + (plane * self.step)
                self.motors.horizontal.move_absolute_position(position,'\u03BCm')  #Position in micro-meters
                self.updateUi_position_horizontal()
                
                '''Moving the camera to focus'''
                ###self.calculate_camera_focus()
                ###self.move_camera_to_focus()   
                
                if self.saving_allowed:
                    self.frame_saver.add_motor_parameters(self.current_horizontal_position_text,self.current_vertical_position_text,self.current_camera_position_text)
                
                '''Getting image'''
                self.get_single_image()
                
                '''Saving frame'''
                if self.saving_allowed:
                    if self.ui.checkBox_acqSaveAllFrames.isChecked():
                        cropped_buffer = self.crop_buffer(self.buffer)
                        self.send_frame_to_consumer(cropped_buffer,False,True)
                        self.status_printer('Saving Images (one for each ETL scan)')
                    else:
                        self.send_frame_to_consumer(self.reconstructed_frame,False,True)
                        self.status_printer('Saving Reconstructed Image')
                
                '''Update progress bar'''
                progress_value += progress_increment
                self.sig_update_progress.emit(int(progress_value))
        if self.stack_mode_started:
            self.sig_update_progress.emit(100) #In case the number of planes is not a multiple of 100

        if self.saving_allowed:
            self.frame_saver.stop_saving()
        
        '''Stopping camera'''
        self.camera.disarm() 
        
        '''Stopping laser'''
        self.stop_lasers()
        self.both_lasers_activated = False
        
        '''Enabling modes after stack mode'''
        self.ui.pushButton_acqStartStackMode.setText('Start Stack Mode')
        self.update_buttons_modes(self.default_buttons)
        self.update_motor_buttons(disable_button=False)
        
        self.stack_mode_started = False
        self.status_printer('->Stack Mode Acquisition Done')
        self.label_statusBar.setText('')
        self.progress_statusBar.hide()
    
    '''Calibration Methods'''
    def camera_calibration_button(self):
        '''Start or stop camera calibration, depending on the button status'''
        if self.camera_calibration_started:
            self.camera_calibration_started = False
        else:
            self.close_modes()
            self.camera_calibration_started = True
            self.ui.pushButton_calCameraStartCalibration.setText('Stop Camera Calibration')
            self.update_motor_buttons()
            self.start_calibrate_camera()
    
    def start_calibrate_camera(self):
        '''Initiates camera calibration'''
       
        '''Modes disabling while stack acquisition'''
        self.update_buttons_modes([self.ui.pushButton_calCameraStartCalibration])
            
        self.status_printer('Camera calibration started')
        self.label_statusBar.setText('Current Mode: Camera Calibration ')
        self.progress_statusBar.show()
            
        '''Starting camera calibration thread'''
        calibrate_camera_thread = threading.Thread(target = self.calibrate_camera_thread)
        calibrate_camera_thread.start()
    
    def calibrate_camera_thread(self):
        ''' Calibrates the camera focus by finding the ideal camera position 
            for multiple sample horizontal positions'''
        
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
        
        '''Retrieving filename set by the user''' #debugging
        self.get_file_name()
        if self.saving_allowed:
            '''Setting frame saver'''
            self.frame_saver = FrameSaver()
            self.frame_saver.set_block_size(3) #Block size is a number of buffers
            self.frame_saver.set_files(self.number_of_calibration_planes,self.filename,'cameraCalibration',self.number_of_camera_positions,'camera_position')
            '''Getting sample name'''
            self.get_sample_name()
            
            self.set_data_consumer(self.frame_saver, False, "FrameSaver", True) ###
            '''Starting frame saver'''
            self.frame_saver.start_saving()
        else:
            print('Select directory and enter a valid filename before saving')
        
        '''Set progress bar'''
        progress_value = 0
        progress_increment = 100/self.number_of_calibration_planes
        self.sig_update_progress.emit(0) #To reset progress bar
        
        for sample_plane in range(int(self.number_of_calibration_planes)): #For each sample position
            if self.camera_calibration_started == False:
                self.status_printer('Camera calibration interrupted')
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
                        self.get_single_image()
                        
                        '''Saving frame''' #debugging
                        if self.saving_allowed:
                            self.send_frame_to_consumer(self.reconstructed_frame,False,True)
                            self.status_printer('Saving Reconstructed Image')
                        
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
                    
                    self.status_printer('--Calibration of plane ' + str(sample_plane+1) + '/' + str(int(self.number_of_calibration_planes)) + ' done')
            
                    '''Update progress bar'''
                    progress_value += progress_increment
                    self.sig_update_progress.emit(int(progress_value))
                except:
                    self.camera_calibration_started = False
                    self.status_printer('Camera calibration failed')
        if self.camera_calibration_started:
            self.sig_update_progress.emit(100) #In case the number of planes is not a multiple of 100
        
        print('relation:') #debugging
        print(self.camera_focus_relation)#debugging
        
        if self.saving_allowed: #debugging
            self.frame_saver.stop_saving()
            self.status_printer('Images saved')
        
        '''Returning sample and camera at initial positions'''
        self.motors.horizontal.move_absolute_position(position_depart_sample,'\u03BCStep')
        self.updateUi_position_horizontal()
        self.motors.camera.move_absolute_position(self.motors.camera.get_origin(self.units), self.units)
        self.updateUi_position_camera()
        
        '''Stopping camera'''
        self.camera.disarm()
        
        '''Stopping lasers'''
        self.stop_lasers()
        self.both_lasers_activated = False

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
        
        self.status_printer('Camera calibration done')
        self.label_statusBar.setText('')
        self.progress_statusBar.hide()
            
        '''Enabling modes after camera calibration'''
        self.update_buttons_modes(self.default_buttons)
        self.update_motor_buttons(False)
            
        self.camera_calibration_started = False
        self.ui.pushButton_calCameraStartCalibration.setText('Start Camera Calibration')

    
    def etls_calibration_button(self):
        '''Start or stop etls calibration, depending on the button status'''
        if self.etls_calibration_started:
            self.etls_calibration_started = False
        else:
            self.close_modes()
            self.etls_calibration_started = True
            self.ui.pushButton_calEtlStartCalibration.setText('Stop ETL Calibration')
            self.update_motor_buttons()
            self.start_calibrate_etls()
    
    def start_calibrate_etls(self):
        '''Initiates etls-galvos calibration'''
       
        '''Modes disabling while stack acquisition'''
        self.update_buttons_modes([self.ui.pushButton_calEtlStartCalibration])
        self.status_printer('ETL calibration started')
        
        '''Starting camera calibration thread'''
        calibrate_etls_thread = threading.Thread(target = self.calibrate_etls_thread)
        calibrate_etls_thread.start()
    
    def calibrate_etls_thread(self):
        ''' Calibrates the focal position relation with etls-galvos voltage'''
        
        '''Setting the camera for acquisition'''
        self.camera.set_trigger_mode('auto_trigger')
        self.camera.arm()        
        
        '''Setting tasks'''
        self.galvos_etls_task = nidaqmx.Task()
        self.galvos_etls_task.ao_channels.add_ao_voltage_chan(self._terminals["galvos_etls"])
        
        '''Getting parameters'''
        self.number_of_etls_points = 20 ##
        self.number_of_etls_images = 20 ##
        
        self.etl_l_relation = np.zeros((int(self.number_of_etls_points),2))
        self.etl_r_relation = np.zeros((int(self.number_of_etls_points),2))
        
        
        '''Retrieving filename set by the user''' #debugging
        self.get_file_name()
        if self.saving_allowed:
            '''Setting frame saver'''
            self.frame_saver = FrameSaver()
            self.frame_saver.set_block_size(3) #Block size is a number of buffers
            self.frame_saver.set_files(2*self.number_of_etls_points,self.filename,'etlCalibration',self.number_of_etls_images,'etl_image')
            '''Getting sample name'''
            self.get_sample_name()
            
            self.set_data_consumer(self.frame_saver, False, "FrameSaver", True) ###
            '''Starting frame saver'''
            self.frame_saver.start_saving()
        else:
            print('Select directory and enter a valid filename before saving')
        
        
        '''Finding relation between etls' voltage and focal point vertical's position'''
        for side in ['etl_l','etl_r']: #For each etl
            '''Parameters'''
            if side == 'etl_l':
                etl_max_voltage = 4.2 #3.5#4.2      #Volts ##Arbitraire
                etl_min_voltage = 2 #2.5#1.8        #Volts ##Arbitraire
            if side == 'etl_r':
                etl_max_voltage = 4.2 #3.5#4.2      #Volts ##Arbitraire
                etl_min_voltage = 2 #2.5#1.8        #Volts ##Arbitraire
            etl_increment_length = (etl_max_voltage - etl_min_voltage) / self.number_of_etls_points
            
            '''Starting automatically lasers'''
            if side == 'etl_l':
                self.left_laser_activated = True
            if side == 'etl_r':
                self.right_laser_activated = True
            self.parameters['Left Laser Voltage'] = 2.5#2#.2 #Volts
            self.parameters['Right Laser Voltage'] = 2.5#2.5 #Volts
            self.start_lasers()
            
            #self.camera.retrieve_single_image()*1.0 ##pour éviter images de bruit
            
            self.xdata = np.zeros((int(self.number_of_etls_points),128))
            self.ydata = np.zeros((int(self.number_of_etls_points),128))
            self.popt = np.zeros((int(self.number_of_etls_points),4))
            
            #For each interpolation point
            for etl_point in range(int(self.number_of_etls_points)):
                
                if self.etls_calibration_started == False:
                    self.status_printer('ETL calibration interrupted')
                    break
                else:
                    '''Getting the data to send to the AO'''
                    right_etl_voltage = etl_min_voltage + (etl_point * etl_increment_length) #Volts
                    left_etl_voltage = etl_min_voltage + (etl_point * etl_increment_length) #Volts
                    
                    left_galvo_voltage = 0 #Volts
                    right_galvo_voltage = 0.1 #Volts
                    
                    '''Writing the data'''
                    galvos_etls_waveforms = np.stack((np.array([right_galvo_voltage]),
                                                              np.array([left_galvo_voltage]),
                                                              np.array([left_etl_voltage]),
                                                              np.array([right_etl_voltage])))
                    self.galvos_etls_task.write(galvos_etls_waveforms, auto_start=True)
                   
                    '''Retrieving buffer for the plane of the current position'''
                    #self.ramps = AOETLGalvos(self.parameters)
                    #self.number_of_steps = 1
                    #self.buffer = self.camera.retrieve_multiple_images(self.number_of_steps, self.ramps.t_half_period, sleep_timeout = 5) #debugging
                    #self.save_single_image() #debugging
                    
                    ydatas = np.zeros((self.number_of_etls_images,128))  ##128=K
                    
                    #For each image
                    for etl_image in range(self.number_of_etls_images):
                        '''Retrieving image from camera and putting it in its queue
                               for display'''
                        time.sleep(1)
                        frame = self.camera.retrieve_single_image()*1.0
                        blurred_frame = ndimage.gaussian_filter(frame, sigma=20)
                        
                        
                        '''Retrieving filename set by the user''' #debugging
                        if self.saving_allowed:
                            self.frame_saver.add_motor_parameters(self.current_horizontal_position_text,self.current_vertical_position_text,self.current_camera_position_text)
                        
                        '''Saving frame''' #debugging
                        if self.saving_allowed:
                            self.send_frame_to_consumer(blurred_frame,False,True)
                            self.status_printer('Saving Reconstructed Image')
                        
                        frame = np.transpose(frame)
                        blurred_frame = np.transpose(blurred_frame)
                        
                        self.send_frame_to_consumer(frame)
                        self.send_frame_to_consumer(blurred_frame)
                        
                        '''Calculating focal point horizontal position'''
                        #filtering image:
                        dset = np.transpose(blurred_frame)
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
                    
                        self.status_printer('--Calibration of plane '+str(etl_point+1)+'/'+str(self.number_of_etls_points)+' for '+side+' done')
                    except:
                        self.etls_calibration_started = False
                        self.status_printer('ETL calibration failed')
            
            '''Closing lasers after calibration of each side'''    
            self.left_laser_activated = False
            self.right_laser_activated = False
        
        if self.saving_allowed: #debugging
            self.frame_saver.stop_saving()
            self.status_printer('Images saved')
        
        
        print(self.etl_l_relation) #debugging
        print(self.etl_r_relation) #debugging
        '''Calculating linear regressions'''
        xl = self.etl_l_relation[:,0]
        yl = self.etl_l_relation[:,1]
        #Left linear regression
        self.left_slope, self.left_intercept, r_value, p_value, std_err = stats.linregress(yl, xl)
        print('r_value:'+str(r_value)) #debugging
        print('p_value:'+str(p_value)) #debugging
        print('std_err:'+str(std_err)) #debugging
        print('left_slope:'+str(self.left_slope)) #debugging
        print('left_intercept:'+str(self.left_intercept)) #debugging
        print(self.left_slope * 2559 + self.left_intercept) #debugging
        
        xr = self.etl_r_relation[:,0]
        yr = self.etl_r_relation[:,1]
        #Right linear regression
        self.right_slope, self.right_intercept, r_value, p_value, std_err = stats.linregress(yr, xr)
        print('r_value:'+str(r_value)) #debugging
        print('p_value:'+str(p_value)) #debugging
        print('std_err:'+str(std_err)) #debugging
        print('right_slope:'+str(self.right_slope)) #debugging
        print('right_intercept:'+str(self.right_intercept)) #debugging
        print(self.right_slope * 2559 + self.right_intercept) #debugging
        
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
        
        self.status_printer('Calibration done')
            
        '''Enabling modes after camera calibration'''
        self.update_buttons_modes(self.default_buttons)
        self.update_motor_buttons(False)
        
        self.etls_calibration_started = False
        self.ui.pushButton_calEtlStartCalibration.setText('Start ETL Calibration')


class CameraWindow(queue.Queue):
    '''Class for image display'''
    
    def __init__(self, graphicsview:ImageView):
        '''Bigger queue size allows more image to be buffered. However, 
        since many images can take a lot of RAM and it is not necessary to display
        all the acquired frames, we keep the queue short. It is more 
        important to save all the planes then to see all of them while in
        acquisition. To this effect, the block_size (i.e. the queue) of 
        FrameSaver should be prioritized. '''
        
        # Queue of maxsize 3 elements (frames)
        queue.Queue.__init__(self, 3)
        self.graphicsview = graphicsview
        self.histogram_level = []

        # Create an all zero values image but for a single pixel 
        # (trick to get initial range of the histogram)
        img_lines = 2160
        img_columns = 2560
        img_data = np.zeros((img_lines, img_columns))
        img_data[0,0] = 1000

        # Set initial displayed image
        self.graphicsview.setImage(np.transpose(img_data))
        self.histogram_level = [0, 1000]

    def put(self, item, block=True, timeout=None):
        '''Put an image in the display queue'''
        if queue.Queue.full(self) == False: 
            queue.Queue.put(self, item, block=block, timeout=timeout)
                 
    def update(self):
        '''Takes an image from the queue (if any) and displays it in the window
           Executes at each interval of the QTimer'''

        try:
            # Retrieve handle to viewbox and histogram
            _view = self.graphicsview.getView()
            _histo = self.graphicsview.getHistogramWidget()

            # Get current histograms level and viewbox state
            _state = _view.getState()
            self.histogram_level = _histo.getLevels()

            # Retrieve and display a new frame'''
            frame = self.get(False)
            self.graphicsview.setImage(frame)

            # Set histograms level and viewbox state 
            # (to keep display settings between image refresh)
            _view.setState(_state)
            _histo.setLevels(self.histogram_level[0], self.histogram_level[1])
        except queue.Empty:
            pass


class FrameSaver():
    '''Class for storing buffers (images) in its queue and saving them 
       afterwards in a specified directory in a HDF5 format'''
    
    '''Set up methods'''
    def __init__(self, status_printer):
        self.status_printer = status_printer
        self.filenames_list = [] 
        self.number_of_files = 1
        
        self.horizontal_positions_list = []
        self.vertical_positions_list = []
        self.camera_positions_list = []
    
    def add_motor_parameters(self, current_hor_position_txt, current_ver_position_txt, current_cam_position_txt):
        '''Add to a list the different motor positions'''
        self.horizontal_positions_list.append(current_hor_position_txt)
        self.vertical_positions_list.append(current_ver_position_txt)
        self.camera_positions_list.append(current_cam_position_txt)
    
    def set_files(self,number_of_files, files_name, scan_type, number_of_datasets, datasets_name):
        '''Set the number and name of files to save and makes sure the filenames 
        are unique in the path to avoid overwrite on other files'''
        self.number_of_files = number_of_files
        self.files_name = files_name
        self.number_of_datasets = number_of_datasets
        self.datasets_name = datasets_name
        
        counter = 0
        for _ in range(int(self.number_of_files)):
            in_loop = True
            while in_loop:
                counter += 1
                new_filename = self.files_name + '_' + scan_type + '_plane_' + u'%05d'%counter + '.hdf5'
                
                if os.path.isfile(new_filename) == False: #Check for existing files
                    in_loop = False
                    self.filenames_list.append(new_filename)
    
    def add_attribute(self, attribute, value):
        '''Add an attribute to a dataset: a string associated to a value'''
        self.dataset.attrs[attribute] = value
    
    def set_block_size(self, block_size):
        '''If we lose images while stack_mode acquisition, think about setting a
           bigger block_size (storing more images at a time), or use time.sleep()
           after each stack_mode loop if we don't have enough RAM to enlarge the
           block_size (hence we give time to FrameSaver to make space in its
           queue)'''
        self.block_size = block_size
        self.queue = queue.Queue(2*block_size) #Set up queue of maxsize 2*block_size (frames)
    
    '''Saving methods'''
    def put(self, value, flag):
        '''Put an image in the save queue'''
        self.queue.put(value, flag)
    
    def start_saving(self):
        '''Initiates saving thread'''
        self.saving_started = True
        frame_saver_thread = threading.Thread(target = self.save_thread)
        frame_saver_thread.start()
    
    def save_thread(self):
        '''Thread for saving 3D arrays (or 2D arrays). 
            The number of datasets per file is the number of 2D arrays'''
        for file in range(len(self.filenames_list)):
            print('File created:'+str(self.filenames_list[file])) #debugging
            '''Create file'''
            f = h5py.File(self.filenames_list[file],'a')
            
            counter = 1
            for dataset in range(int(self.number_of_datasets)):
                in_loop = True
                while in_loop:
                    try:
                        '''Retrieve buffer'''
                        buffer = self.queue.get(True,1)
                        if buffer.ndim == 2:
                            buffer = np.expand_dims(buffer, axis=0) #To consider 2D arrays as a 3D arrays
                        for frame in range(buffer.shape[0]): #For each 2D frame
                            '''Create dataset'''
                            path_root = self.datasets_name+u'%03d'%counter
                            self.dataset = f.create_dataset(path_root, data=buffer[frame,:,:])
                            print('Dataset '+str(dataset)+'/'+str(int(self.number_of_datasets))+' created:'+str(path_root)) #debugging
                            
                            '''Add attributes'''
                            self.add_attribute('Sample Name', parameters["Sample Name"])
                            self.add_attribute('Date', str(datetime.date.today()))
                            if buffer.shape[0] == 1:
                                pos_index = dataset + file * int(self.number_of_datasets)
                            else:
                                pos_index = file
                            self.add_attribute('Current sample horizontal position', self.horizontal_positions_list[pos_index])
                            self.add_attribute('Current sample vertical position', self.vertical_positions_list[pos_index])
                            self.add_attribute('Current camera horizontal position', self.camera_positions_list[pos_index])
#                            for param_string in modifiable_parameters:
#                                self.add_attribute(param_string, parameters[param_string])
                            counter += 1

                        in_loop = False
                    except:
                        if self.saving_started == False:
                            in_loop = False
            f.close()
            self.status_printer('File '+self.filenames_list[file]+' saved')

    def stop_saving(self):
        '''Changes the flag status to end the saving thread''' 
        self.saving_started = False
