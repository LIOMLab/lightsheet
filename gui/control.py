'''
Created on May 22, 2019

@authors: Pierre Girard-Collins & flesage
'''

import sys
sys.path.append("..")

import os
import numpy as np
#from PyQt5 import QtGui
from PyQt5 import uic
from PyQt5.QtWidgets import QWidget, QFileDialog
#from PyQt5.QtWidgets import QApplication, QMainWindow, QMenu, QVBoxLayout, QSizePolicy, QMessageBox, QPushButton
#from PyQt5.QtGui import QIcon
#from PyQt5.QtCore import QThread

import pyqtgraph as pg
#import ctypes
import copy

import nidaqmx
#from nidaqmx.constants import AcquisitionType

from src.hardware import AOETLGalvos
from src.hardware import Motors
from src.pcoEdge import Camera
#from zaber.serial import AsciiSerial, AsciiDevice, AsciiCommand
import threading
import time
import queue
#import multiprocessing
import h5py
import posixpath
import datetime

'''Default parameters'''
parameters = dict()
parameters["samplerate"]=40000          # In samples/seconds
parameters["sweeptime"]=0.4             # In seconds
parameters["galvo_l_frequency"]=100     # In Hertz
parameters["galvo_l_amplitude"]=2       # In Volts
parameters["galvo_l_offset"]=-3         # In Volts
parameters["galvo_r_frequency"]=100     # In Hertz
parameters["galvo_r_amplitude"]=2       # In Volts
parameters["galvo_r_offset"]=-3         # In Volts
parameters["etl_l_amplitude"]=2         # In Volts
parameters["etl_l_offset"]=0            # In Volts
parameters["etl_r_amplitude"]=2         # In Volts
parameters["etl_r_offset"]=0            # In Volts
parameters["laser_l_voltage"]=0.905     # In Volts
parameters["laser_r_voltage"]=0.935     # In Volts
parameters["columns"] = 2560            # In pixels
parameters["rows"] = 2160               # In pixels 
parameters["etl_step"] = 100            # In pixels
parameters["camera_delay"] = 10         # In %
parameters["min_t_delay"] = 0.0354404   # In seconds
parameters["t_start_exp"] = 0.017712    # In seconds

'''DAQ channels'''
terminals = dict()
terminals["galvos_etls"] = '/Dev1/ao0:3'
terminals["camera"]='/Dev1/port0/line1'
terminals["lasers"]='/Dev7/ao0:1'

class Controller(QWidget):
    '''
    classdocs
    '''
    def __init__(self):
        QWidget.__init__(self)
        
        '''Loading user interface'''
        basepath= os.path.join(os.path.dirname(__file__))
        uic.loadUi(os.path.join(basepath,"control.ui"), self)
        
        '''Defining attributes'''
        self.parameters = copy.deepcopy(parameters)
        self.defaultParameters = copy.deepcopy(parameters)
        
        self.consumers = []
        
        '''Initializing flags'''
        self.all_lasers_on = False
        self.left_laser_on = False
        self.right_laser_on = False
        self.preview_mode_started = False
        self.live_mode_started = False
        self.stack_mode_started = False
        self.camera_on = True
        self.standby = False
        self.saving_allowed = False
        self.camera_calibration_started = False
        
        '''Instantiating the motors'''
        self.motor1 = Motors(1, 'COM3')             #Vertical motor
        self.motor2 = Motors(2, 'COM3')             #Horizontal motor for sample motion
        self.motor3 = Motors(3, 'COM3')             #Horizontal motor for camera motion (detection arm)
        
        '''Instantiating the camera'''
        self.camera = Camera()
        
        self.camera_focus_relation = np.zeros((10,2))
        
        '''Arbitrary origin positions (in micro-steps)'''
        self.originX = 533333   # In micro-steps
        self.originZ = 0        # In micro-steps
        self.focus = 533333     # In micro-steps
        
        '''Lasers default voltage (the associated laser power output is not 
        dangerous for the eyes, but beam exposition should always be avoided)'''
        self.left_laser_voltage = 0.905     #In Volts
        self.right_laser_voltage = 0.935    #In Volts
        
        
        '''Decimal number is the same for all widgets for a specific unit'''
        self.decimals = self.doubleSpinBox_incrementHorizontal.decimals()
        
        '''Defining distance units allowed by the software '''
        self.comboBox_unit.insertItems(0,["cm","mm","\u03BCm"])
        self.comboBox_unit.setCurrentIndex(1)
        self.comboBox_unit.currentTextChanged.connect(self.update_all)
        
        '''Initializing the properties of the other widgets'''
        self.initialize_other_widgets()
        
        '''Initializing every other widget that are updated by a change of unit 
            (the motion tab)'''
        self.update_all()
        
        
        '''Connection for data saving'''
        self.pushButton_selectDirectory.clicked.connect(self.select_directory)
        
        
        '''Connections for the modes'''
        self.pushButton_getSingleImage.clicked.connect(self.start_get_single_image)
        self.pushButton_saveImage.clicked.connect(self.save_single_image)
        self.pushButton_startLiveMode.clicked.connect(self.start_live_mode)
        self.pushButton_stopLiveMode.clicked.connect(self.stop_live_mode)
        self.pushButton_startStack.clicked.connect(self.start_stack_mode)
        self.pushButton_stopStack.clicked.connect(self.stop_stack_mode)
        self.pushButton_setStartPoint.clicked.connect(self.set_stack_mode_starting_point)
        self.pushButton_setEndPoint.clicked.connect(self.set_stack_mode_ending_point)
        self.doubleSpinBox_planeStep.valueChanged.connect(self.set_number_of_planes)
        self.pushButton_startPreviewMode.clicked.connect(self.start_preview_mode)
        self.pushButton_stopPreviewMode.clicked.connect(self.stop_preview_mode)
        self.pushButton_standbyOn.pressed.connect(self.start_standby)
        self.pushButton_standbyOff.pressed.connect(self.stop_standby)
       
       
        '''Connections for the motion'''
        self.pushButton_motorUp.clicked.connect(self.move_up)
        self.pushButton_motorDown.clicked.connect(self.move_down)
        self.pushButton_motorRight.clicked.connect(self.move_right)
        self.pushButton_motorLeft.clicked.connect(self.move_left)
        self.pushButton_motorOrigin.clicked.connect(self.move_to_origin)
        self.pushButton_setAsOrigin.clicked.connect(self.set_origin )
        
        #Might write a function for this button instead of using lambda commands
        self.pushButton_movePosition.clicked.connect(lambda: self.motor2.move_absolute_position(self.doubleSpinBox_choosePosition.value(),self.comboBox_unit.currentText()))
        self.pushButton_movePosition.clicked.connect(lambda: self.label_currentHorizontalNumerical.setText("{} {}".format(round(self.motor2.current_position(self.comboBox_unit.currentText()),self.decimals), self.comboBox_unit.currentText())))
        
        #Might write a function for this button instead of using lambda commands
        self.pushButton_moveHeight.clicked.connect(lambda: self.motor1.move_absolute_position(self.doubleSpinBox_chooseHeight.value(),self.comboBox_unit.currentText()))
        self.pushButton_moveHeight.clicked.connect(lambda: self.label_currentHeightNumerical.setText("{} {}".format(round(self.motor1.current_position(self.comboBox_unit.currentText()),self.decimals), self.comboBox_unit.currentText())))
       
        #Might write a function for this button instead of using lambda commands
        self.pushButton_moveCamera.clicked.connect(lambda: self.motor3.move_absolute_position(self.doubleSpinBox_chooseCamera.value(),self.comboBox_unit.currentText()))
        self.pushButton_moveCamera.clicked.connect(lambda: self.label_currentCameraNumerical.setText("{} {}".format(round(self.motor3.current_position(self.comboBox_unit.currentText()),self.decimals), self.comboBox_unit.currentText())))
        self.pushButton_setFocus.clicked.connect(self.set_focus)
        
        self.pushButton_forward.clicked.connect(self.move_forward)
        self.pushButton_backward.clicked.connect(self.move_backward)
        self.pushButton_focus.clicked.connect(self.move_to_focus)
        
        self.pushButton_calibrateRange.clicked.connect(self.reset_boundaries)
        self.pushButton_setUpperLimit.clicked.connect(self.set_upper_boundary)
        self.pushButton_setLowerLimit.clicked.connect(self.set_lower_boundary)
        
        self.pushButton_calibrateCamera.pressed.connect(self.calibrate_camera)
        
        '''Connections for the ETLs and Galvos parameters'''
        self.doubleSpinBox_leftEtlAmplitude.valueChanged.connect(lambda: self.etl_galvos_parameters_changed(1))
        self.doubleSpinBox_rightEtlAmplitude.valueChanged.connect(lambda: self.etl_galvos_parameters_changed(2))
        self.doubleSpinBox_leftEtlOffset.valueChanged.connect(lambda: self.etl_galvos_parameters_changed(3))
        self.doubleSpinBox_rightEtlOffset.valueChanged.connect(lambda: self.etl_galvos_parameters_changed(4))
        self.doubleSpinBox_leftGalvoAmplitude.valueChanged.connect(lambda: self.etl_galvos_parameters_changed(5))
        self.doubleSpinBox_rightGalvoAmplitude.valueChanged.connect(lambda: self.etl_galvos_parameters_changed(6))
        self.doubleSpinBox_leftGalvoOffset.valueChanged.connect(lambda: self.etl_galvos_parameters_changed(7))
        self.doubleSpinBox_rightGalvoOffset.valueChanged.connect(lambda: self.etl_galvos_parameters_changed(8))
        self.doubleSpinBox_leftGalvoFrequency.valueChanged.connect(lambda: self.etl_galvos_parameters_changed(9))
        self.doubleSpinBox_rightGalvoFrequency.valueChanged.connect(lambda: self.etl_galvos_parameters_changed(10))
        self.doubleSpinBox_samplerate.valueChanged.connect(lambda: self.etl_galvos_parameters_changed(11))
        self.spinBox_etlStep.valueChanged.connect(lambda: self.etl_galvos_parameters_changed(12))
        self.pushButton_defaultParameters.clicked.connect(self.back_to_default_parameters)
    
        
        '''Connections for the lasers'''
        self.pushButton_lasersOn.clicked.connect(self.lasers_on)
        self.pushButton_lasersOff.clicked.connect(self.lasers_off)
        self.pushButton_leftLaserOn.clicked.connect(self.start_left_laser)
        self.pushButton_leftLaserOff.clicked.connect(self.stop_left_laser)
        self.pushButton_rightLaserOn.clicked.connect(self.start_right_laser)
        self.pushButton_rightLaserOff.clicked.connect(self.stop_right_laser)
        self.horizontalSlider_leftLaser.sliderReleased.connect(self.left_laser_update)
        self.horizontalSlider_rightLaser.sliderReleased.connect(self.right_laser_update)
        
    def back_to_default_parameters(self):
        '''Change all the modifiable parameters to go back to the initial state'''
        
        self.parameters = copy.deepcopy(self.defaultParameters)
        self.doubleSpinBox_leftEtlAmplitude.setValue(self.parameters["etl_l_amplitude"])
        self.doubleSpinBox_rightEtlAmplitude.setValue(self.parameters["etl_r_amplitude"])
        self.doubleSpinBox_leftEtlOffset.setValue(self.parameters["etl_l_offset"])
        self.doubleSpinBox_rightEtlOffset.setValue(self.parameters["etl_r_offset"])
        self.doubleSpinBox_leftGalvoAmplitude.setValue(self.parameters["galvo_l_amplitude"])
        self.doubleSpinBox_rightGalvoAmplitude.setValue(self.parameters["galvo_r_amplitude"])
        self.doubleSpinBox_leftGalvoOffset.setValue(self.parameters["galvo_l_offset"])
        self.doubleSpinBox_rightGalvoOffset.setValue(self.parameters["galvo_r_offset"])
        self.doubleSpinBox_leftGalvoFrequency.setValue(self.parameters["galvo_l_frequency"])
        self.doubleSpinBox_rightGalvoFrequency.setValue(self.parameters["galvo_r_frequency"])
        self.doubleSpinBox_samplerate.setValue(self.parameters["samplerate"])    
        
    def close_camera(self):
        self.camera_on = False
        self.camera.close_camera()
        print('Camera closed')
        self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Camera closed')    
        
    def closeEvent(self, event):
        '''Making sure that everything is closed when the user exits the software.
           This function executes automatically when the user closes the UI.
           This is an intrinsic function name of Qt, don't change the name even 
           if it doesn't follow the naming convention'''

        if self.all_lasers_on == True:
            self.lasers_off()
            
        if self.left_laser_on == True:
            self.stop_left_laser()
            
        if self.right_laser_on == True:
            self.right_laser_off()
            
        if self.preview_mode_started == True:
            self.stop_preview_mode()
            
        if self.live_mode_started == True:
            self.stop_live_mode()
            
        if self.stack_mode_started == True:
            self.stop_stack_mode()
            
        if self.camera_on == True:
            self.close_camera()
            
        event.accept()    
        
    def etl_galvos_parameters_changed(self, parameterNumber):
        '''Updates the parameters in the software after a modification by the
           user'''
        
        if parameterNumber==1:
            self.doubleSpinBox_leftEtlAmplitude.setMaximum(5-self.doubleSpinBox_leftEtlOffset.value())
            self.parameters["etl_l_amplitude"]=self.doubleSpinBox_leftEtlAmplitude.value()
            if self.checkBox_checkBox_etlsTogether.isChecked() == True:
                self.parameters["etl_r_amplitude"]=self.doubleSpinBox_leftEtlAmplitude.value()
                self.doubleSpinBox_rightEtlAmplitude.setValue(self.parameters["etl_r_amplitude"])
        elif parameterNumber==2:
            self.doubleSpinBox_rightEtlAmplitude.setMaximum(5-self.doubleSpinBox_rightEtlOffset.value())
            self.parameters["etl_r_amplitude"]=self.doubleSpinBox_rightEtlAmplitude.value()
            if self.checkBox_etlsTogether.isChecked() == True:
                self.parameters["etl_l_amplitude"]=self.doubleSpinBox_rightEtlAmplitude.value()
                self.doubleSpinBox_leftEtlAmplitude.setValue(self.parameters["etl_l_amplitude"])
        elif parameterNumber==3:
            self.doubleSpinBox_leftEtlOffset.setMaximum(5-self.doubleSpinBox_leftEtlAmplitude.value())
            self.parameters["etl_l_offset"]=self.doubleSpinBox_leftEtlOffset.value()
            if self.checkBox_etlsTogether.isChecked() == True:
                self.parameters["etl_r_offset"]=self.doubleSpinBox_leftEtlOffset.value()
                self.doubleSpinBox_rightEtlOffset.setValue(self.parameters["etl_r_offset"])
        elif parameterNumber==4:
            self.doubleSpinBox_rightEtlOffset.setMaximum(5-self.doubleSpinBox_rightEtlAmplitude.value())
            self.parameters["etl_r_offset"]=self.doubleSpinBox_rightEtlOffset.value()
            if self.checkBox_etlsTogether.isChecked() == True:
                self.parameters["etl_l_offset"]=self.doubleSpinBox_rightEtlOffset.value()
                self.doubleSpinBox_leftEtlOffset.setValue(self.parameters["etl_l_offset"])
        elif parameterNumber==5:
            self.parameters["etl_l_delay"]=self.doubleSpinBox_leftEtlDelay.value()
            if self.checkBox_etlsTogether.isChecked() == True:
                self.parameters["etl_r_delay"]=self.doubleSpinBox_leftEtlDelay.value()
                self.doubleSpinBox_rightEtlDelay.setValue(self.parameters["etl_r_delay"])
        elif parameterNumber==6:
            self.parameters["etl_r_delay"]=self.doubleSpinBox_rightEtlDelay.value()
            if self.checkBox_etlsTogether.isChecked() == True:
                self.parameters["etl_l_delay"]=self.doubleSpinBox_rightEtlDelay.value()
                self.doubleSpinBox_leftEtlDelay.setValue(self.parameters["etl_l_delay"])
        elif parameterNumber==7:
            self.parameters["etl_l_ramp_rising"]=self.doubleSpinBox_leftEtlRising.value()
            if self.checkBox_etlsTogether.isChecked() == True:
                self.parameters["etl_r_ramp_rising"]=self.doubleSpinBox_leftEtlRising.value()
                self.doubleSpinBox_rightEtlRising.setValue(self.parameters["etl_r_ramp_rising"])
        elif parameterNumber==8:
            self.parameters["etl_r_ramp_rising"]=self.doubleSpinBox_rightEtlRising.value()
            if self.checkBox_etlsTogether.isChecked() == True:
                self.parameters["etl_l_ramp_rising"]=self.doubleSpinBox_rightEtlRising.value()
                self.doubleSpinBox_leftEtlRising.setValue(self.parameters["etl_l_ramp_rising"])
        elif parameterNumber==9:
            self.parameters["etl_l_ramp_falling"]=self.doubleSpinBox_leftEtlFalling.value()
            if self.checkBox_etlsTogether.isChecked() == True:
                self.parameters["etl_r_ramp_falling"]=self.doubleSpinBox_leftEtlFalling.value()
                self.doubleSpinBox_rightEtlFalling.setValue(self.parameters["etl_r_ramp_falling"])
        elif parameterNumber==10:
            self.parameters["etl_r_ramp_falling"]=self.doubleSpinBox_rightEtlFalling.value()
            if self.checkBox_etlsTogether.isChecked() == True:
                self.parameters["etl_l_ramp_falling"]=self.doubleSpinBox_rightEtlFalling.value()
                self.doubleSpinBox_leftEtlFalling.setValue(self.parameters["etl_l_ramp_falling"])
        elif parameterNumber==11:
            self.doubleSpinBox_leftGalvoAmplitude.setMaximum(10-self.doubleSpinBox_leftGalvoOffset.value())
            self.doubleSpinBox_leftGalvoAmplitude.setMinimum(-10-self.doubleSpinBox_leftGalvoOffset.value())
            self.parameters["galvo_l_amplitude"]=self.doubleSpinBox_leftGalvoAmplitude.value()
            if self.checkBox_galvosTogether.isChecked() == True:
                self.parameters["galvo_r_amplitude"]=self.doubleSpinBox_leftGalvoAmplitude.value()
                self.doubleSpinBox_rightGalvoAmplitude.setValue(self.parameters["galvo_r_amplitude"])
        elif parameterNumber==12:
            self.doubleSpinBox_rightGalvoAmplitude.setMaximum(10-self.doubleSpinBox_rightGalvoOffset.value())
            self.doubleSpinBox_rightGalvoAmplitude.setMinimum(-10-self.doubleSpinBox_rightGalvoOffset.value())
            self.parameters["galvo_r_amplitude"]=self.doubleSpinBox_rightGalvoAmplitude.value()
            if self.checkBox_galvosTogether.isChecked() == True:
                self.parameters["galvo_l_amplitude"]=self.doubleSpinBox_rightGalvoAmplitude.value()
                self.doubleSpinBox_leftGalvoAmplitude.setValue(self.parameters["galvo_l_amplitude"])
        elif parameterNumber==13:
            self.doubleSpinBox_leftGalvoOffset.setMaximum(10-self.doubleSpinBox_leftGalvoAmplitude.value())
            self.doubleSpinBox_leftGalvoOffset.setMinimum(-10-self.doubleSpinBox_leftGalvoAmplitude.value())
            self.parameters["galvo_l_offset"]=self.doubleSpinBox_leftGalvoOffset.value()
            if self.checkBox_galvosTogether.isChecked() == True:
                self.parameters["galvo_r_offset"]=self.doubleSpinBox_leftGalvoOffset.value()
                self.doubleSpinBox_rightGalvoOffset.setValue(self.parameters["galvo_r_offset"])
        elif parameterNumber==14:
            self.doubleSpinBox_rightGalvoOffset.setMaximum(10-self.doubleSpinBox_rightGalvoAmplitude.value())
            self.doubleSpinBox_rightGalvoOffset.setMinimum(-10-self.doubleSpinBox_rightGalvoAmplitude.value())
            self.parameters["galvo_r_offset"]=self.doubleSpinBox_rightGalvoOffset.value()
            if self.checkBox_galvosTogether.isChecked() == True:
                self.parameters["galvo_l_offset"]=self.doubleSpinBox_rightGalvoOffset.value()
                self.doubleSpinBox_leftGalvoOffset.setValue(self.parameters["galvo_l_offset"])
        elif parameterNumber==15:
            self.parameters["galvo_l_frequency"]=self.doubleSpinBox_leftGalvoFrequency.value()
            if self.checkBox_galvosTogether.isChecked() == True:
                self.parameters["galvo_r_frequency"]=self.doubleSpinBox_leftGalvoFrequency.value()
                self.doubleSpinBox_rightGalvoFrequency.setValue(self.parameters["galvo_r_frequency"])
        elif parameterNumber==16:
            self.parameters["galvo_r_frequency"]=self.doubleSpinBox_rightGalvoFrequency.value()
            if self.checkBox_galvosTogether.isChecked() == True:
                self.parameters["galvo_l_frequency"]=self.doubleSpinBox_rightGalvoFrequency.value()
                self.doubleSpinBox_leftGalvoFrequency.setValue(self.parameters["galvo_l_frequency"])
        elif parameterNumber==17:
            self.parameters["galvo_l_duty_cycle"]=self.doubleSpinBox_leftGalvoDutyCycle.value()
            if self.checkBox_galvosTogether.isChecked() == True:
                self.parameters["galvo_r_duty_cycle"]=self.doubleSpinBox_leftGalvoDutyCycle.value()
                self.doubleSpinBox_rightGalvoDutyCycle.setValue(self.parameters["galvo_r_duty_cycle"])
        elif parameterNumber==18:
            self.parameters["galvo_r_duty_cycle"]=self.doubleSpinBox_rightGalvoDutyCycle.value()
            if self.checkBox_galvosTogether.isChecked() == True:
                self.parameters["galvo_l_duty_cycle"]=self.doubleSpinBox_rightGalvoDutyCycle.value()
                self.doubleSpinBox_leftGalvoDutyCycle.setValue(self.parameters["galvo_l_duty_cycle"])
        elif parameterNumber==19:
            self.parameters["galvo_l_phase"]=self.doubleSpinBox_leftGalvoPhase.value()
            if self.checkBox_galvosTogether.isChecked() == True:
                self.parameters["galvo_r_phase"]=self.doubleSpinBox_leftGalvoPhase.value()
                self.doubleSpinBox_rightGalvoPhase.setValue(self.parameters["galvo_r_phase"])
        elif parameterNumber==20:
            self.parameters["galvo_r_phase"]=self.doubleSpinBox_rightGalvoPhase.value()
            if self.checkBox_galvosTogether.isChecked() == True:
                self.parameters["galvo_l_phase"]=self.doubleSpinBox_rightGalvoPhase.value()
                self.doubleSpinBox_leftGalvoPhase.setValue(self.parameters["galvo_l_phase"])
        elif parameterNumber==21:
            self.parameters["samplerate"]=self.doubleSpinBox_samplerate.value()
        elif parameterNumber==22:
            self.parameters["sweeptime"]=self.doubleSpinBox_sweeptime.value()
        elif parameterNumber==23:
            self.parameters["etl_step"]=self.spinBox_etlStep.value()
        elif parameterNumber==24:
            self.parameters["camera_delay"]=self.doubleSpinBox_cameraDelay.value()
    
    def update_all(self):
        '''Updates all the widgets of the motion tab after an unit change'''
        
        unit = self.comboBox_unit.currentText()
        
        self.doubleSpinBox_incrementHorizontal.setSuffix(" {}".format(unit))
        self.doubleSpinBox_incrementHorizontal.setValue(1)
        self.doubleSpinBox_incrementVertical.setSuffix(" {}".format(unit))
        self.doubleSpinBox_incrementVertical.setValue(1)
        self.doubleSpinBox_incrementCamera.setSuffix(" {}".format(unit))
        self.doubleSpinBox_incrementCamera.setValue(1)
        self.doubleSpinBox_choosePosition.setSuffix(" {}".format(unit))
        self.doubleSpinBox_choosePosition.setValue(0)
        self.doubleSpinBox_chooseHeight.setSuffix(" {}".format(unit))
        self.doubleSpinBox_chooseHeight.setValue(0)
        self.doubleSpinBox_chooseCamera.setSuffix(" {}".format(unit))
        self.doubleSpinBox_chooseCamera.setValue(0)
        
        if unit == 'cm':
            self.horizontal_maximum = self.motor2.data_to_position(self.upper_boundary,'cm')
            self.horizontal_minimum = self.motor2.data_to_position(self.lower_boundary,'cm')
            maximum_increment = self.horizontal_maximum-self.horizontal_minimum
            self.doubleSpinBox_incrementHorizontal.setDecimals(4)
            self.doubleSpinBox_incrementHorizontal.setMaximum(maximum_increment)
            self.doubleSpinBox_incrementVertical.setDecimals(4)
            self.doubleSpinBox_incrementVertical.setMaximum(5.08)
            self.doubleSpinBox_incrementCamera.setDecimals(4)
            self.doubleSpinBox_incrementCamera.setMaximum(10.16)
            self.doubleSpinBox_choosePosition.setDecimals(4)
            self.doubleSpinBox_choosePosition.setMaximum(self.horizontal_maximum)
            self.doubleSpinBox_choosePosition.setMinimum(self.horizontal_minimum)
            self.doubleSpinBox_chooseHeight.setDecimals(4)
            self.doubleSpinBox_chooseHeight.setMaximum(5.08)
            self.doubleSpinBox_chooseCamera.setDecimals(4)
            self.doubleSpinBox_chooseCamera.setMaximum(10.16)
            self.decimals = self.doubleSpinBox_incrementHorizontal.decimals()
            self.label_currentHeightNumerical.setText("{} {}".format(round(self.motor1.current_position(unit),self.decimals), unit))
            self.label_currentHorizontalNumerical.setText("{} {}".format(round(self.motor2.current_position(unit),self.decimals), unit))
            self.label_currentCameraNumerical.setText("{} {}".format(round(self.motor3.current_position(unit),self.decimals), unit))
        elif unit == 'mm':
            self.horizontal_maximum = self.motor2.data_to_position(self.upper_boundary,'mm')
            self.horizontal_minimum = self.motor2.data_to_position(self.lower_boundary,'mm')
            maximum_increment = self.horizontal_maximum-self.horizontal_minimum
            self.doubleSpinBox_incrementHorizontal.setDecimals(3)
            self.doubleSpinBox_incrementHorizontal.setMaximum(maximum_increment)
            self.doubleSpinBox_incrementVertical.setDecimals(3)
            self.doubleSpinBox_incrementVertical.setMaximum(50.8)
            self.doubleSpinBox_incrementCamera.setDecimals(3)
            self.doubleSpinBox_incrementCamera.setMaximum(101.6)
            self.doubleSpinBox_choosePosition.setDecimals(3)
            self.doubleSpinBox_choosePosition.setMaximum(self.horizontal_maximum)
            self.doubleSpinBox_choosePosition.setMinimum(self.horizontal_minimum)
            self.doubleSpinBox_chooseHeight.setDecimals(3)
            self.doubleSpinBox_chooseHeight.setMaximum(50.8)
            self.doubleSpinBox_chooseCamera.setDecimals(3)
            self.doubleSpinBox_chooseCamera.setMaximum(101.6)
            self.decimals = self.doubleSpinBox_incrementHorizontal.decimals()
            self.label_currentHeightNumerical.setText("{} {}".format(round(self.motor1.current_position(unit),self.decimals), unit))
            self.label_currentHorizontalNumerical.setText("{} {}".format(round(self.motor2.current_position(unit),self.decimals), unit))
            self.label_currentCameraNumerical.setText("{} {}".format(round(self.motor3.current_position(unit),self.decimals), unit))
        elif unit == '\u03BCm':
            self.horizontal_maximum = self.motor2.data_to_position(self.upper_boundary,'\u03BCm')
            self.horizontal_minimum = self.motor2.data_to_position(self.lower_boundary,'\u03BCm')
            maximum_increment = self.horizontal_maximum-self.horizontal_minimum
            self.doubleSpinBox_incrementHorizontal.setDecimals(0)
            self.doubleSpinBox_incrementHorizontal.setMaximum(maximum_increment)
            self.doubleSpinBox_incrementVertical.setDecimals(0)
            self.doubleSpinBox_incrementVertical.setMaximum(50800)
            self.doubleSpinBox_incrementCamera.setDecimals(0)
            self.doubleSpinBox_incrementCamera.setMaximum(101600)
            self.doubleSpinBox_choosePosition.setDecimals(0)
            self.doubleSpinBox_choosePosition.setMaximum(self.horizontal_maximum)
            self.doubleSpinBox_choosePosition.setMinimum(self.horizontal_minimum)
            self.doubleSpinBox_chooseHeight.setDecimals(0)
            self.doubleSpinBox_chooseHeight.setMaximum(50800)
            self.doubleSpinBox_chooseCamera.setDecimals(0)
            self.doubleSpinBox_chooseCamera.setMaximum(101600)
            self.decimals = self.doubleSpinBox_incrementHorizontal.decimals()
            self.label_currentHeightNumerical.setText("{} {}".format(round(self.motor1.current_position(unit),self.decimals), unit))
            self.label_currentHorizontalNumerical.setText("{} {}".format(round(self.motor2.current_position(unit),self.decimals), unit))
            self.label_currentCameraNumerical.setText("{} {}".format(round(self.motor3.current_position(unit),self.decimals), unit))
    
    def initialize_other_widgets(self):
        '''Initializes the properties of the widgets that are not updated by a 
        change of units, i.e. the widgets that cannot be initialize with 
        self.update_all()'''
        
        '''Data saving's related widgets'''
        self.lineEdit_filename.setEnabled(False)
        
        
        '''Motion's related widgets'''
        self.pushButton_setUpperLimit.setEnabled(False)
        self.pushButton_setLowerLimit.setEnabled(False)
        self.upper_boundary = 533333
        self.lower_boundary = 0
        
        
        '''Modes' related widgets'''
        self.pushButton_stopLiveMode.setEnabled(False)
        self.pushButton_stopStack.setEnabled(False)
        #self.pushButton_setOptimized.setEnabled(False)
        self.pushButton_saveImage.setEnabled(False)
        self.pushButton_stopPreviewMode.setEnabled(False)
        self.pushButton_standbyOff.setEnabled(False)
        
        self.checkBox_setStartPoint.setEnabled(False)
        self.checkBox_setEndPoint.setEnabled(False)
        
        self.doubleSpinBox_planeStep.setSuffix(' \u03BCm')
        self.doubleSpinBox_planeStep.setDecimals(0)
        self.doubleSpinBox_planeStep.setMaximum(101600)
        self.doubleSpinBox_planeStep.setSingleStep(1)
        
        
        '''ETLs and galvos parameters' related widgets'''
        self.doubleSpinBox_leftEtlAmplitude.setValue(self.parameters["etl_l_amplitude"])
        self.doubleSpinBox_leftEtlAmplitude.setSuffix(" V")
        self.doubleSpinBox_leftEtlAmplitude.setSingleStep(0.1)
        self.doubleSpinBox_leftEtlAmplitude.setMaximum(5)
        self.doubleSpinBox_rightEtlAmplitude.setValue(self.parameters["etl_r_amplitude"])
        self.doubleSpinBox_rightEtlAmplitude.setSuffix(" V")
        self.doubleSpinBox_rightEtlAmplitude.setSingleStep(0.1)
        self.doubleSpinBox_rightEtlAmplitude.setMaximum(5)
        self.doubleSpinBox_leftEtlOffset.setValue(self.parameters["etl_l_offset"])
        self.doubleSpinBox_leftEtlOffset.setSuffix(" V")
        self.doubleSpinBox_leftEtlOffset.setSingleStep(0.1)
        self.doubleSpinBox_leftEtlOffset.setMaximum(5)
        self.doubleSpinBox_rightEtlOffset.setValue(self.parameters["etl_r_offset"])
        self.doubleSpinBox_rightEtlOffset.setSuffix(" V")
        self.doubleSpinBox_rightEtlOffset.setSingleStep(0.1)
        self.doubleSpinBox_rightEtlOffset.setMaximum(5)
        
        self.doubleSpinBox_leftGalvoAmplitude.setValue(self.parameters["galvo_l_amplitude"])
        self.doubleSpinBox_leftGalvoAmplitude.setSuffix(" V")
        self.doubleSpinBox_leftGalvoAmplitude.setSingleStep(0.1)
        self.doubleSpinBox_leftGalvoAmplitude.setMaximum(10)
        self.doubleSpinBox_leftGalvoAmplitude.setMinimum(-10)
        self.doubleSpinBox_rightGalvoAmplitude.setValue(self.parameters["galvo_r_amplitude"])
        self.doubleSpinBox_rightGalvoAmplitude.setSuffix(" V")
        self.doubleSpinBox_rightGalvoAmplitude.setSingleStep(0.1)
        self.doubleSpinBox_rightGalvoAmplitude.setMaximum(10)
        self.doubleSpinBox_rightGalvoAmplitude.setMinimum(-10)
        self.doubleSpinBox_leftGalvoOffset.setMaximum(10)
        self.doubleSpinBox_leftGalvoOffset.setMinimum(-10)
        self.doubleSpinBox_leftGalvoOffset.setValue(self.parameters["galvo_l_offset"])
        self.doubleSpinBox_leftGalvoOffset.setSuffix(" V")
        self.doubleSpinBox_leftGalvoOffset.setSingleStep(0.1)
        self.doubleSpinBox_rightGalvoOffset.setMaximum(10)
        self.doubleSpinBox_rightGalvoOffset.setMinimum(-10)
        self.doubleSpinBox_rightGalvoOffset.setValue(self.parameters["galvo_r_offset"])
        self.doubleSpinBox_rightGalvoOffset.setSuffix(" V")
        self.doubleSpinBox_rightGalvoOffset.setSingleStep(0.1)
        self.doubleSpinBox_leftGalvoFrequency.setValue(self.parameters["galvo_l_frequency"])
        self.doubleSpinBox_leftGalvoFrequency.setSuffix(" Hz")
        self.doubleSpinBox_leftGalvoFrequency.setMaximum(130)
        self.doubleSpinBox_rightGalvoFrequency.setValue(self.parameters["galvo_r_frequency"])
        self.doubleSpinBox_rightGalvoFrequency.setSuffix(" Hz")
        self.doubleSpinBox_rightGalvoFrequency.setMaximum(130)
        
        self.doubleSpinBox_samplerate.setMaximum(1000000)
        self.doubleSpinBox_samplerate.setValue(self.parameters["samplerate"])
        self.doubleSpinBox_samplerate.setSuffix(" samples/s")
                
        self.spinBox_etlStep.setMaximum(2560)
        self.spinBox_etlStep.setSuffix(" columns")
        self.spinBox_etlStep.setValue(self.parameters["etl_step"])
        
        
        '''Lasers parameters' related widgets'''
        self.pushButton_lasersOff.setEnabled(False)
        self.pushButton_leftLaserOff.setEnabled(False)
        self.pushButton_rightLaserOff.setEnabled(False)
        
        self.label_leftLaserVoltage.setText('{} {}'.format(parameters["laser_l_voltage"], 'V'))
        self.label_rightLaserVoltage.setText('{} {}'.format(parameters["laser_r_voltage"], 'V'))
        
        '''QSlider only takes integers, the integers are 10x the voltage
           QSlider range is [0,25], voltage range is [0, 2.5]
        '''
        self.horizontalSlider_leftLaser.setTickPosition(2)  #Draw tick marks below the slider
        self.horizontalSlider_leftLaser.setTickInterval(10)
        self.horizontalSlider_leftLaser.setSingleStep(1)
        self.horizontalSlider_leftLaser.setValue(int(self.parameters["laser_l_voltage"]*100))
        self.horizontalSlider_leftLaser.setMaximum(250)
        self.horizontalSlider_leftLaser.setMinimum(0)
        
        self.horizontalSlider_rightLaser.setTickPosition(2)  #Draw tick marks below the slider
        self.horizontalSlider_rightLaser.setTickInterval(10)
        self.horizontalSlider_rightLaser.setSingleStep(1)
        self.horizontalSlider_rightLaser.setValue(int(self.parameters["laser_r_voltage"]*100))
        self.horizontalSlider_rightLaser.setMaximum(250)
        self.horizontalSlider_rightLaser.setMinimum(0)
    
    def lasers_off(self):
        '''Flag and lasers' pushButton managing for both lasers deactivation'''
        self.all_lasers_on = False
        self.pushButton_lasersOn.setEnabled(True)
        self.pushButton_lasersOff.setEnabled(False)
        self.pushButton_leftLaserOn.setEnabled(True)
        self.pushButton_rightLaserOn.setEnabled(True)
        print('Lasers off')
        self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Lasers off')  
        
    def lasers_on(self):
        '''Flag and lasers' pushButton managing for both lasers activation'''
        self.all_lasers_on = True
        self.pushButton_lasersOn.setEnabled(False)
        self.pushButton_lasersOff.setEnabled(True)
        self.pushButton_leftLaserOn.setEnabled(False)
        self.pushButton_rightLaserOn.setEnabled(False)
        print('Lasers on')
        self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Lasers on') 
        
    def lasers_thread(self):
        '''This thread allows the modification of lasers' power output while 
          executing another operation'''
        continuer = True
        while continuer:
            
            if self.stop_lasers == True:
                continuer = False
            
            else:
                left_laser_voltage = 0
                right_laser_voltage = 0
                
                '''Laser status override already dealt with by enabling 
                   pushButtons in lasers' functions'''
                if self.all_lasers_on == True:
                    left_laser_voltage = self.parameters['laser_l_voltage']
                    right_laser_voltage = self.parameters['laser_r_voltage']
                
                if self.left_laser_on == True:
                    left_laser_voltage = self.parameters['laser_l_voltage']
                
                if self.right_laser_on == True:
                    right_laser_voltage = self.parameters['laser_r_voltage']
                    
                self.lasers_waveforms = np.stack((np.array([right_laser_voltage]),
                                                        np.array([left_laser_voltage])))   
                    
                self.lasers_task.write(self.lasers_waveforms, auto_start=True)
        
        '''Put the lasers voltage to zero
           This is done at the end, because we do not want to shut down the lasers
           after each sweep to minimize their power fluctuations '''
        
        waveforms = np.stack(([0],[0]))
        self.lasers_task.write(waveforms)
        self.lasers_task.stop()
        self.lasers_task.close()        
            
    def stop_left_laser(self):
        '''Flag and lasers' pushButton managing for left laser deactivation'''
        self.left_laser_on = False
        print('Left laser off')
        self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Lasers off') 
        self.pushButton_leftLaserOn.setEnabled(True)
        self.pushButton_leftLaserOff.setEnabled(False)
        if self.pushButton_rightLaserOn.isEnabled() == True:
            self.pushButton_lasersOn.setEnabled(True)
            
    def start_left_laser(self):
        '''Flag and lasers' pushButton managing for left laser activation'''
        self.left_laser_on = True
        self.pushButton_lasersOn.setEnabled(False)
        self.pushButton_leftLaserOn.setEnabled(False)
        self.pushButton_leftLaserOff.setEnabled(True)
        print('Left laser on')
        self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Lasers on') 
        
    def left_laser_update(self):
        '''Updates left laser voltage after value change by the user'''
        self.label_leftLaserVoltage.setText('{} {}'.format(self.horizontalSlider_leftLaser.value()/100, 'V'))
        self.parameters["laser_l_voltage"] = self.horizontalSlider_leftLaser.value()/100 
    
    def stop_right_laser(self):
        '''Flag and lasers' pushButton managing for right laser deactivation'''
        self.right_laser_on = False
        print('Left laser off')
        self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Left laser off')
        self.pushButton_rightLaserOn.setEnabled(True)
        self.pushButton_rightLaserOff.setEnabled(False)
        if self.pushButton_leftLaserOn.isEnabled() == True:
            self.pushButton_lasersOn.setEnabled(True)
        
    def start_right_laser(self):
        '''Flag and lasers' pushButton managing for right laser activation'''
        self.right_laser_on = True
        self.pushButton_lasersOn.setEnabled(False)
        self.pushButton_rightLaserOn.setEnabled(False)
        self.pushButton_rightLaserOff.setEnabled(True)
        print('Left laser on')
        self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Left laser on')
        
    def right_laser_update(self):
        '''Updates right laser voltage after value change by the user'''
        self.label_rightLaserVoltage.setText('{} {}'.format(self.horizontalSlider_rightLaser.value()/100, 'V'))
        self.parameters["laser_r_voltage"] = self.horizontalSlider_rightLaser.value()/100
    
    def move_backward(self):
        '''Camera motor backward horizontal motion'''
        print('Camera moving backward')
        self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Camera moving backward')
        self.motor3.move_relative_position(-self.doubleSpinBox_incrementCamera.value(),self.comboBox_unit.currentText())
        #Current camera position update
        self.label_currentCameraNumerical.setText("{} {}".format(round(self.motor3.current_position(self.comboBox_unit.currentText()),self.decimals), self.comboBox_unit.currentText()))
    
    def move_forward(self):
        '''Camera motor forward horizontal motion'''
        print('Camera moving forward')
        self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Camera moving forward')
        self.motor3.move_relative_position(self.doubleSpinBox_incrementCamera.value(),self.comboBox_unit.currentText())
        #Current camera position update
        self.label_currentCameraNumerical.setText("{} {}".format(round(self.motor3.current_position(self.comboBox_unit.currentText()),self.decimals), self.comboBox_unit.currentText()))
    
    def move_to_focus(self):
        '''Moves camera to focus position'''
        print('Moving to focus')
        self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Moving to focus')
        self.motor3.move_absolute_position(self.focus,'\u03BCStep')
        #Current camera position update
        self.label_currentCameraNumerical.setText("{} {}".format(round(self.motor3.current_position(self.comboBox_unit.currentText()),self.decimals), self.comboBox_unit.currentText()))
    
    def move_down(self):
        '''Sample motor downward vertical motion'''
        print ('Moving down')
        self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Moving down')
        self.motor1.move_relative_position(self.doubleSpinBox_incrementVertical.value(),self.comboBox_unit.currentText())
        #Current height update
        self.label_currentHeightNumerical.setText("{} {}".format(round(self.motor1.current_position(self.comboBox_unit.currentText()),self.decimals), self.comboBox_unit.currentText()))
    
    def move_up(self):
        '''Sample motor upward vertical motion'''
        print('Moving up')
        self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Moving up')
        self.motor1.move_relative_position(-self.doubleSpinBox_incrementVertical.value(),self.comboBox_unit.currentText())
        #Current height update
        self.label_currentHeightNumerical.setText("{} {}".format(round(self.motor1.current_position(self.comboBox_unit.currentText()),self.decimals), self.comboBox_unit.currentText()))
    
    def move_left(self):
        '''Sample motor backward horizontal motion
           Maybe implement camera motion here to keep imaging plane into focus?'''
        #Motion of the detection arm to implement (self.motor3)
        current_position = self.motor2.current_position(self.comboBox_unit.currentText())
        if current_position-self.doubleSpinBox_incrementHorizontal.value() >= self.horizontal_minimum:
            print ('Sample moving backward')
            self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Sample moving backward')
            self.motor2.move_relative_position(-self.doubleSpinBox_incrementHorizontal.value(),self.comboBox_unit.currentText())
            #Current horizontal position update
            self.label_currentHorizontalNumerical.setText("{} {}".format(round(self.motor2.current_position(self.comboBox_unit.currentText()),self.decimals), self.comboBox_unit.currentText()))
        else:
            print('Out of boundaries')
            self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Out of boundaries')
            
    def move_right(self):
        '''Sample motor forward horizontal motion
           Maybe implement camera motion here to keep imaging plane into focus?'''
        #Motion of the detection arm to implement (self.motor3)
        current_position = self.motor2.current_position(self.comboBox_unit.currentText())
        if current_position+self.doubleSpinBox_incrementHorizontal.value() <= self.horizontal_maximum:
            print ('Sample moving forward')
            self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Sample moving forward')
            self.motor2.move_relative_position(self.doubleSpinBox_incrementHorizontal.value(),self.comboBox_unit.currentText())
            #Current horizontal position update
            self.label_currentHorizontalNumerical.setText("{} {}".format(round(self.motor2.current_position(self.comboBox_unit.currentText()), self.decimals), self.comboBox_unit.currentText()))
        else:
            print('Out of boundaries')
            self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Out of boundaries')
    
    def move_to_origin(self):
        '''Moves vertical and horizontal sample motors to origin position
           Maybe implement camera motion here to keep origin position into focus?'''
        #Motion of the detection arm to implement (self.motor3)
        originX_current_unit = self.motor2.data_to_position(self.originX, self.comboBox_unit.currentText())
        print('Moving to origin')
        self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Moving to origin')
        if originX_current_unit >= self.horizontal_minimum and originX_current_unit <= self.horizontal_maximum:
            self.motor2.move_absolute_position(self.originX,'\u03BCStep')
        else:
            print('Sample Horizontal Origin Out Of Boundaries')
            self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Sample Horizontal Origin Out of boundaries')
            
        self.motor1.move_absolute_position(self.originZ,'\u03BCStep')
        #Current positions update
        self.label_currentHorizontalNumerical.setText("{} {}".format(round(self.motor2.current_position(self.comboBox_unit.currentText()),self.decimals), self.comboBox_unit.currentText()))
        self.label_currentHeightNumerical.setText("{} {}".format(round(self.motor1.current_position(self.comboBox_unit.currentText()),self.decimals), self.comboBox_unit.currentText()))
      
    def open_camera(self):
        self.camera_on=True
        self.camera = Camera()
        print('Camera opened') 
        self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Camera opened') 
            
    def reset_boundaries(self):
        '''Reset variables for setting sample's horizontal motion range 
           (to avoid hitting the glass walls)'''
        self.pushButton_setUpperLimit.setEnabled(True)
        self.pushButton_setLowerLimit.setEnabled(True)
        self.label_calibrateRange.setText("Move Horizontal Position")
        self.upperBoundarySelected = False
        self.lowerBoundarySelected = False
        self.pushButton_calibrateRange.setEnabled(False)
        
        self.upper_boundary = 533333
        self.lower_boundary = 0
        
        self.update_all()   
    
    def select_directory(self):
        '''Allows the selection of a directory for single_image or stack saving'''
        options = QFileDialog.Options()
        options |= QFileDialog.DontResolveSymlinks
        options |= QFileDialog.ShowDirsOnly
        self.save_directory = QFileDialog.getExistingDirectory(self, 'Choose Directory', '', options)
        
        if self.save_directory != '':
            self.label_currentDirectory.setText(self.save_directory)
            self.lineEdit_filename.setEnabled(True)
            self.lineEdit_filename.setText('')
            self.saving_allowed = True
        else:
            self.label_currentDirectory.setText('None specified')
            self.lineEdit_filename.setEnabled(False)
            self.lineEdit_filename.setText('Select directory first')
            self.saving_allowed = False
            
    def set_camera_window(self, camera_window):
        '''Instantiates the camera window where the frames are displayed'''
        self.camera_window = camera_window
        
    def set_data_consumer(self, consumer, wait, consumer_type, update_flag):
        ''' Regroups all the consumers in the same list'''
        self.consumers.append(consumer)
        self.consumers.append(wait)
        self.consumers.append(consumer_type)
        self.consumers.append(update_flag)
    
    def set_lower_boundary(self):
        '''Set lower limit of sample's horizontal motion 
           (to avoid hitting the glass walls)'''
        self.lower_boundary = self.motor2.current_position('\u03BCStep')
        self.lower_boundary_selected = True
        self.pushButton_setLowerLimit.setEnabled(False)
        
        self.update_all()
        
        if self.upper_boundary_selected == True:
            self.pushButton_calibrateRange.setEnabled(True)
            self.label_calibrateRange.setText('Press Calibrate Range To Start')
    
    def set_upper_boundary(self):
        '''Set upper limit of sample's horizontal motion 
           (to avoid hitting the glass walls)'''
        self.upper_boundary = self.motor2.current_position('\u03BCStep')
        self.upper_boundary_selected = True
        self.pushButton_setUpperLimit.setEnabled(False)
        
        self.update_all()
        
        if self.lower_boundary_selected == True:
            self.pushButton_calibrateRange.setEnabled(True)
            self.label_calibrateRange.setText('Press Calibrate Range To Start')
    
    def set_origin(self):
        '''Modifies the sample origin position'''
        self.originX = self.motor2.position_to_data(self.motor2.current_position(self.comboBox_unit.currentText()),self.comboBox_unit.currentText())
        self.originZ = 1066666 - self.motor1.position_to_data(self.motor1.current_position(self.comboBox_unit.currentText()),self.comboBox_unit.currentText())
        print('Origin set')
        self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Origin set')
    
    def set_focus(self):
        '''Modifies the camera focus position'''
        self.focus = self.motor3.position_to_data(self.motor3.current_position(self.comboBox_unit.currentText()),self.comboBox_unit.currentText())
        print('Focus set')
        self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Focus set')
        
    def set_number_of_planes(self):
        '''Calculates the number of planes that will be saved in the stack 
           acquisition'''
        if self.doubleSpinBox_planeStep.value() != 0:
            if self.checkBox_setStartPoint.isChecked() == True and self.checkBox_setEndPoint.isChecked() == True:
                self.number_of_planes = np.ceil(abs((self.stack_mode_ending_point-self.stack_mode_starting_point)/self.doubleSpinBox_planeStep.value()))
                self.number_of_planes +=1   #Takes into account the initial plane
                self.label_numberOfPlanes.setText(str(self.number_of_planes))
        else:
            print('Set a non-zero value to plane step')
            self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Set a non-zero value to plane step')
        
    def set_stack_mode_ending_point(self):
        '''Defines the ending point of the recorded stack volume'''
        self.stack_mode_ending_point = self.motor2.current_position('\u03BCm') #Units in micro-meters, because plane step is in micro-meters
        self.checkBox_setEndPoint.setChecked(True)
        self.set_number_of_planes()
        
    def set_stack_mode_starting_point(self):
        '''Defines the starting point where the first plane of the stack volume
           will be recorded'''
        self.stack_mode_starting_point = self.motor2.current_position('\u03BCm') #Units in micro-meters, because plane step is in micro-meters
        self.checkBox_setStartPoint.setChecked(True)
        self.set_number_of_planes()    

    
    '''Acquisition Modes Functions'''
    
    def standby_thread(self):
        '''Repeatedly sends 2.5V to the ETLs to keep their currents at 0A'''
        standby_task = nidaqmx.Task()
        standby_task.ao_channels.add_ao_voltage_chan('/Dev1/ao2:3')
        
        etl_voltage = 2.5 #volts
        standby_waveform = np.stack((np.array([etl_voltage]),np.array([etl_voltage])))
        
        while self.standby:
            standby_task.write(standby_waveform, auto_start = True)
            time.sleep(5) #seconds
            
        standby_task.stop()
        standby_task.close()
        self.open_camera()
        print('Standby off')
        self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Standby off')
        
        '''Modes enabling after standby'''
        self.pushButton_getSingleImage.setEnabled(True)
        self.pushButton_saveImage.setEnabled(False)
        self.pushButton_startStack.setEnabled(True)
        self.pushButton_stopStack.setEnabled(False)
        self.pushButton_startLiveMode.setEnabled(True)
        self.pushButton_stopLiveMode.setEnabled(False)
        self.pushButton_startPreviewMode.setEnabled(True)
        self.pushButton_stopPreviewMode.setEnabled(False)
        self.pushButton_standbyOn.setEnabled(True)
        self.pushButton_standbyOff.setEnabled(False)
    
    def start_standby(self):
        '''Close camera and initiates thread to keep ETLs'currents at 0A while
           the microscope is not in use'''
        self.standby = True
        self.close_camera()
        standby_thread = threading.Thread(target = self.standby_thread)
        standby_thread.start()
        print('Standby on')
        self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Standby on')
        
        '''Modes disabling while in standby'''
        self.pushButton_getSingleImage.setEnabled(False)
        self.pushButton_saveImage.setEnabled(False)
        self.pushButton_startStack.setEnabled(False)
        self.pushButton_stopStack.setEnabled(False)
        self.pushButton_startLiveMode.setEnabled(False)
        self.pushButton_stopLiveMode.setEnabled(False)
        self.pushButton_startPreviewMode.setEnabled(False)
        self.pushButton_stopPreviewMode.setEnabled(False)
        self.pushButton_standbyOn.setEnabled(False)
        self.pushButton_standbyOff.setEnabled(True)
    
    def stop_standby(self):
        '''Changes the standby flag status to end the thread'''
        self.standby = False
    
    def preview_mode_thread(self):
        '''This thread allows the visualization and manual control of the 
           parameters of the beams in the UI. There is no scan here, 
           beams only changes when parameters are changed. This the preferred 
           mode for beam calibration'''
        
        '''Setting tasks'''
        self.preview_lasers_task = nidaqmx.Task()
        self.preview_lasers_task.ao_channels.add_ao_voltage_chan(terminals["lasers"])
        
        self.preview_galvos_etls_task = nidaqmx.Task()
        self.preview_galvos_etls_task.ao_channels.add_ao_voltage_chan(terminals["galvos_etls"])
        
        
        for i in range(0, len(self.consumers), 4):
            if self.consumers[i+2] == "CameraWindow":
                while self.preview_mode_started:
                    
                    '''Getting the data to send to the AO'''
                    left_galvo_voltage = self.parameters['galvo_l_amplitude']
                    right_galvo_voltage = self.parameters['galvo_r_amplitude']
                    left_etl_voltage = self.parameters['etl_l_amplitude']
                    right_etl_voltage = self.parameters['etl_r_amplitude']
                    left_laser_voltage = 0
                    right_laser_voltage = 0
                    
                    '''Laser status override already dealt with by enabling 
                       pushButtons in lasers' functions'''
                    if self.all_lasers_on == True:
                        left_laser_voltage = self.parameters['laser_l_voltage']
                        right_laser_voltage = self.parameters['laser_r_voltage']
                    
                    if self.left_laser_on == True:
                        left_laser_voltage = self.parameters['laser_l_voltage']
                    
                    if self.right_laser_on == True:
                        right_laser_voltage = self.parameters['laser_r_voltage']
                    
                    '''Writing the data'''
                    preview_galvos_etls_waveforms = np.stack((np.array([right_galvo_voltage]),
                                                              np.array([left_galvo_voltage]),
                                                              np.array([right_etl_voltage]),
                                                              np.array([left_etl_voltage])))
                    
                    preview_lasers_waveforms = np.stack((np.array([right_laser_voltage]),
                                                         np.array([left_laser_voltage])))
                    
                    
                    self.preview_lasers_task.write(preview_lasers_waveforms, auto_start=True)
                    self.preview_galvos_etls_task.write(preview_galvos_etls_waveforms, auto_start=True)
                    
                    '''Retrieving image from camera and putting it in its queue
                       for display'''
                    frame = self.camera.retrieve_single_image()*1.0
                    try:
                        self.consumers[i].put(frame)
                    except self.consumers[i].Full:
                        print("Queue is full")
                        self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Queue is full')
        
        self.camera.cancel_images()
        self.camera.set_recording_state(0)
        self.camera.free_buffer()
        
        self.preview_galvos_etls_task.stop()
        self.preview_galvos_etls_task.close()
        
        '''Put the lasers voltage to zero
           This is done at the end, because we do not want to shut down the lasers
           after each sweep to minimize their power fluctuations '''
        waveforms = np.stack(([0],[0]))
        self.preview_lasers_task.write(waveforms)
        self.preview_lasers_task.stop()
        self.preview_lasers_task.close()
        
        '''Enabling modes after preview_mode'''
        self.pushButton_getSingleImage.setEnabled(True)
        self.pushButton_startStack.setEnabled(True)
        self.pushButton_startLiveMode.setEnabled(True)
        self.pushButton_startPreviewMode.setEnabled(True)
        self.pushButton_stopPreviewMode.setEnabled(False)
        self.pushButton_standbyOn.setEnabled(True)
        self.pushButton_calibrateCamera.setEnabled(True)
        
        print('Preview mode stopped') 
        self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Preview mode stopped')
    
    def start_preview_mode(self):
        '''Initializes variables for preview modes where beam and focal 
           positions are manually controlled by the user'''
        
        print('Start preview mode')
        self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Start preview mode')
        
        '''Flags check up'''
        if self.preview_mode_started == True:
            self.stop_preview_mode()
            self.preview_mode_started = False
        elif self.live_mode_started == True:
            self.stop_live_mode()
            self.live_mode_started = False
            
        self.preview_mode_started = True
        
        '''Modes disabling while preview_mode execution'''
        self.pushButton_getSingleImage.setEnabled(False)
        self.pushButton_saveImage.setEnabled(False)
        self.pushButton_startStack.setEnabled(False)
        self.pushButton_stopStack.setEnabled(False)
        self.pushButton_startLiveMode.setEnabled(False)
        self.pushButton_stopLiveMode.setEnabled(False)
        self.pushButton_startPreviewMode.setEnabled(False)
        self.pushButton_stopPreviewMode.setEnabled(True)
        self.pushButton_standbyOn.setEnabled(False)
        self.pushButton_calibrateCamera.setEnabled(False)
        
        '''Setting the camera for acquisition'''
        self.camera.set_trigger_mode('AutoSequence')
        self.camera.arm_camera() 
        self.camera.get_sizes() 
        self.camera.allocate_buffer()    
        self.camera.set_recording_state(1)
        self.camera.insert_buffers_in_queue()
        
        preview_mode_thread = threading.Thread(target = self.preview_mode_thread)
        preview_mode_thread.start()
    
    def stop_preview_mode(self):
        '''Changes the preview_mode flag status to end the thread'''
        self.preview_mode_started = False
    
    def live_mode_thread(self):
        '''This thread allows the execution of live_mode while modifying
           parameters in the UI'''
        
        continuer = True
        for i in range(0, len(self.consumers), 4):
            if self.consumers[i+2] == "CameraWindow":
                while continuer:
                    
                    '''Retrieving image from camera and putting it in its queue'''
                    if self.live_mode_started == True:
                        
                        left_laser_voltage = 0
                        right_laser_voltage = 0
                        
                        '''Laser status override already dealt with by enabling 
                           pushButtons in lasers' functions'''
                        if self.all_lasers_on == True:
                            left_laser_voltage = self.parameters['laser_l_voltage']
                            right_laser_voltage = self.parameters['laser_r_voltage']
                        
                        if self.left_laser_on == True:
                            left_laser_voltage = self.parameters['laser_l_voltage']
                        
                        if self.right_laser_on == True:
                            right_laser_voltage = self.parameters['laser_r_voltage']
                            
                        self.lasers_waveforms = np.stack((np.array([right_laser_voltage]),
                                                                np.array([left_laser_voltage])))   
                            
                        self.lasers_task.write(self.lasers_waveforms, auto_start=True)
                        
                        '''Creating ETLs, galvos & camera's ramps and waveforms'''
                        self.ramps=AOETLGalvos(self.parameters)
                        self.ramps.initialize()                  
                        self.ramps.create_tasks(terminals,'FINITE') 
                        self.ramps.create_etl_waveforms(case = 'STAIRS')
                        self.ramps.create_galvos_waveforms(case = 'TRAPEZE')
                        self.ramps.create_digital_output_camera_waveform( case = 'STAIRS_FITTING')
                        
                        '''Writing waveform to task and running'''
                        self.ramps.write_waveforms_to_tasks()                            
                        self.ramps.start_tasks()
                        self.ramps.run_tasks()
                        
                        '''Frame retrieving and reconstruction for display'''
                        self.buffer = self.camera.retrieve_multiple_images(1, self.ramps.t_halfPeriod, sleep_timeout = 5)
                        frame = np.zeros((int(self.parameters["rows"]), int(self.parameters["columns"])))  #Initializing
                        for i in range(int(1)):
                            if i == int(1-1): #Last loop
                                frame[:,int(i*self.parameters['etl_step']):] = self.buffer[i,:,int(i*self.parameters['etl_step']):]
                            else:
                                frame[:,int(i*self.parameters['etl_step']):int(i*self.parameters['etl_step']+self.parameters['etl_step'])] = self.buffer[i,:,int(i*self.parameters['etl_step']):int(i*self.parameters['etl_step']+self.parameters['etl_step'])]
                        
                        '''Frame display'''
                        for i in range(0, len(self.consumers), 4):
                            if self.consumers[i+2] == "CameraWindow":
                                try:
                                    self.consumers[i].put(frame)
                                except:      #self.consumers[i].Full:
                                    print("Queue is full")
                                    self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Queue is full')     
                            
                        self.ramps.stop_tasks()                             
                        self.ramps.close_tasks()
        
                    elif self.live_mode_started == False:
                        continuer = False
        
        self.camera.cancel_images()
        self.camera.set_recording_state(0)
        self.camera.free_buffer()
        
        '''Put the lasers voltage to zero
           This is done at the end, because we do not want to shut down the lasers
           after each sweep to minimize their power fluctuations '''
        waveforms = np.stack(([0],[0]))
        self.lasers_task.write(waveforms)
        self.lasers_task.stop()
        self.lasers_task.close()
        
        '''Enabling modes after live_mode'''
        self.pushButton_getSingleImage.setEnabled(True)
        self.pushButton_startLiveMode.setEnabled(True)
        self.pushButton_stopLiveMode.setEnabled(False)
        self.pushButton_startStack.setEnabled(True)
        self.pushButton_startPreviewMode.setEnabled(True)
        self.pushButton_standbyOn.setEnabled(True)
        self.pushButton_calibrateCamera.setEnabled(True)
        
        print('Live mode stopped')
        self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Live mode stopped')
        
    def start_live_mode(self):
        '''This mode is for visualizing (and modifying) the effects of the 
           chosen parameters of the ramps which will be sent for single image 
           saving or volume saving (with stack_mode)'''
        
        '''Flags check up'''
        if self.preview_mode_started == True:
            self.stop_preview_mode()
            self.preview_mode_started = False
        if self.live_mode_started == True:
            self.stop_live_mode()
            self.live_mode_started = False
        if self.stack_mode_started == True:
            self.stop_stack_mode()
            self.stack_mode_started = False
            
        self.live_mode_started = True
        
        '''Disabling other modes while in live_mode'''
        self.pushButton_getSingleImage.setEnabled(False)
        self.pushButton_saveImage.setEnabled(False)
        self.pushButton_startLiveMode.setEnabled(False)
        self.pushButton_stopLiveMode.setEnabled(True)
        self.pushButton_startStack.setEnabled(False)
        self.pushButton_stopStack.setEnabled(False)
        self.pushButton_startPreviewMode.setEnabled(False)
        self.pushButton_stopPreviewMode.setEnabled(False)
        self.pushButton_standbyOn.setEnabled(False)
        self.pushButton_calibrateCamera.setEnabled(False)
        
        print('Start live mode')
        self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Start live mode')
        
        '''Setting the camera for acquisition'''
        self.camera.set_trigger_mode('ExternalExposureControl')
        self.camera.arm_camera() 
        self.camera.get_sizes() 
        self.camera.allocate_buffer()    
        self.camera.set_recording_state(1)
        self.camera.insert_buffers_in_queue()
        
        '''Creating task for lasers'''
        self.lasers_task = nidaqmx.Task()
        self.lasers_task.ao_channels.add_ao_voltage_chan(terminals["lasers"])
        
        '''Creating thread for live_mode'''
        live_mode_thread = threading.Thread(target = self.live_mode_thread)
        live_mode_thread.start()

    def stop_live_mode(self):
        '''Changes the live_mode flag status to end the thread'''
        self.live_mode_started = False
    
    def save_single_image(self):
        '''Saves the frame generated by self.start_get_single_image()'''
        
        '''Retrieving filename set by the user'''
        self.filename = str(self.lineEdit_filename.text())
        '''Removing spaces, dots and commas'''
        #self.filename = self.filename.replace(' ', '')
        #self.filename = self.filename.replace('.', '')
        #self.filename = self.filename.replace(',', '')
        
        if self.saving_allowed and self.filename != '':
            
            self.filename = self.save_directory + '/' + self.filename
            self.frame_saver = FrameSaver(self.filename)
            self.frame_saver.set_block_size(1) #Block size is a number of buffers
            self.frame_saver.check_existing_files(self.filename, 1, 'singleImage')
            
            '''We can add attributes here (none implemented yet)'''
            
            self.frame_saver.put(self.buffer,1)
            self.frame_saver.start_saving(data_type = 'BUFFER')
            self.frame_saver.stop_saving()
            
            print('Image saved')
            self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Image saved')
            
        else:
            print('Select directory and enter a valid filename before saving')
            self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Select directory and enter a valid filename before saving')
    
    def start_get_single_image(self):
        '''Generates and display a single frame which can be saved afterwards 
        using self.save_single_image()'''
        
        '''Flags check up'''
        if self.preview_mode_started == True:
            self.stop_preview_mode()
            self.preview_mode_started = False
        if self.live_mode_started == True:
            self.stop_live_mode()
            self.live_mode_started = False
        if self.stack_mode_started == True:
            self.stop_stack_mode()
            self.stack_mode_started = False
            
        '''Disabling modes while single frame acquisition'''
        self.pushButton_getSingleImage.setEnabled(False)
        self.pushButton_startLiveMode.setEnabled(False)
        self.pushButton_stopLiveMode.setEnabled(False)
        self.pushButton_startStack.setEnabled(False)
        self.pushButton_stopStack.setEnabled(False)
        self.pushButton_startPreviewMode.setEnabled(False)
        self.pushButton_stopPreviewMode.setEnabled(False)
        print('Getting single image')
        self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Getting single image')
        
        self.stop_lasers = False
        
        '''Setting the camera for acquisition'''
        self.camera.set_trigger_mode('ExternalExposureControl')
        self.camera.arm_camera() 
        self.camera.get_sizes() 
        self.camera.allocate_buffer()    
        self.camera.set_recording_state(1)
        self.camera.insert_buffers_in_queue()
        
        '''Creating tasks and laser thread'''
        self.lasers_task = nidaqmx.Task()
        self.lasers_task.ao_channels.add_ao_voltage_chan(terminals["lasers"])
        lasers_thread = threading.Thread(target = self.lasers_thread)
        lasers_thread.start()
                        
        '''Creating ETLs, galvos & camera's ramps and waveforms'''
        self.ramps=AOETLGalvos(self.parameters)
        self.ramps.initialize()                  
        self.ramps.create_tasks(terminals,'FINITE') 
        self.ramps.create_etl_waveforms(case = 'STAIRS')
        self.ramps.create_galvos_waveforms(case = 'TRAPEZE')
        self.ramps.create_digital_output_camera_waveform( case = 'STAIRS_FITTING')
        
        '''Writing waveform to task and running'''
        self.ramps.write_waveforms_to_tasks()                            
        self.ramps.start_tasks()
        self.ramps.run_tasks()
        
        '''Number of galvo sweeps in a frame, 
           or alternatively the number of ETL focal step'''
        self.number_of_steps = np.ceil(self.parameters["columns"]/self.parameters["etl_step"])
        
        '''Frame retrieving and reconstruction for display'''
        self.buffer = self.camera.retrieve_multiple_images(self.number_of_steps, self.ramps.t_halfPeriod, sleep_timeout = 5)
        frame = np.zeros((int(self.parameters["rows"]), int(self.parameters["columns"])))  #Initializing
        for i in range(int(self.number_of_steps)):
            if i == int(self.number_of_steps-1): #Last loop
                frame[:,int(i*self.parameters['etl_step']):] = self.buffer[i,:,int(i*self.parameters['etl_step']):]
            else:
                frame[:,int(i*self.parameters['etl_step']):int(i*self.parameters['etl_step']+self.parameters['etl_step'])] = self.buffer[i,:,int(i*self.parameters['etl_step']):int(i*self.parameters['etl_step']+self.parameters['etl_step'])]
        
        '''Frame display'''
        for i in range(0, len(self.consumers), 4):
            if self.consumers[i+2] == "CameraWindow":
                try:
                    self.consumers[i].put(frame)
                except:      #self.consumers[i].Full:
                    print("Queue is full")   
                    self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Queue is full') 
        
        '''Stopping lasers'''
        self.stop_lasers = True   
        
        '''Stopping camera'''            
        self.camera.cancel_images()
        self.camera.set_recording_state(0)
        self.camera.free_buffer()
        
        '''Stopping and closing ramps'''
        self.ramps.stop_tasks()                             
        self.ramps.close_tasks()
        
        '''Enabling modes after single frame acquisition'''
        self.pushButton_getSingleImage.setEnabled(True)
        self.pushButton_saveImage.setEnabled(True)
        self.pushButton_startLiveMode.setEnabled(True)
        self.pushButton_startStack.setEnabled(True)
        self.pushButton_startPreviewMode.setEnabled(True)
    
    def stack_mode_thread(self):
        ''' Thread for volume acquisition and saving 
        
        Camera motion (self.motor3) to be implemented 
        
        Note: check if there's a NI-Daqmx function to repeat the data sent 
              instead of closing each time the task. This would be useful
              if it is possible to break a task with self.stop_stack_mode
        Simpler solution: Use conditions with self._stack_mode_started status 
                          such as in self.live_mode_thread() and 
                          self.preview_mode_thread()
        
        A progress bar would be nice
        '''
        
        for i in range(int(self.number_of_planes)):
            
            if self.stack_mode_started == False:
                print('Acquisition Interrupted')
                self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Acquisition Interrupted')
                break
            else:
                '''Moving sample position'''
                position = self.start_point+i*self.step
                self.motor2.move_absolute_position(position,'\u03BCm')  #Position in micro-meters
                
                '''We would move the camera here, and make it it is stabilized 
                   before sending ramps'''
                
                
                '''Acquiring the frame '''
                self.ramps.create_tasks(terminals,'FINITE')
                self.ramps.write_waveforms_to_tasks()                            
                self.ramps.start_tasks()
                self.ramps.run_tasks()
                
                '''Retrieving buffer for the plane of the current position, 
                   and frame reconstruction for display'''
                buffer = self.camera.retrieve_multiple_images(self.number_of_steps, self.ramps.t_half_period, sleep_timeout = 5)
                frame = np.zeros((int(self.rows), int(self.columns)))
                for i in range(int(self.number_of_steps)):
                    if i == int(self.number_of_steps-1): #Last loop
                        frame[:,int(i*self.etl_step):] = buffer[i,:,int(i*self.etl_step):]
                    else:
                        frame[:,int(i*self.etl_step):int(i*self.etl_step+self.etl_step)] = buffer[i,:,int(i*self.etl_step):int(i*self.etl_step+self.etl_step)]
                
                
                '''Frame display and buffer saving'''
                for ii in range(0, len(self.consumers), 4):
                    if self.consumers[ii+2] == 'CameraWindow':
                        try:
                            self.consumers[ii].put(frame)
                            print('Frame put in CameraWindow')
                            self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Frame put in CameraWindow')
                        except:      #self.consumers[ii].Full:
                            print("CameraWindow queue is full")
                            self.label_lastCommands.setText(self.label_lastCommands.text()+'\n CameraWindow queue is full')
                        
                    if self.consumers[ii+2] == 'FrameSaver':
                        try:
                            self.consumers[ii].put(buffer,1)
                            print('Frame put in FrameSaver')
                            self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Frame put in FrameSaver')
                        except:      #self.consumers[ii].Full:
                            print("FrameSaver queue is full")
                            self.label_lastCommands.setText(self.label_lastCommands.text()+'\n FrameSaver queue is full')
    
                self.ramps.stop_tasks()                             
                self.ramps.close_tasks()
                
        
        self.stop_lasers = True
           
        self.camera.cancel_images()
        self.camera.set_recording_state(0)
        self.camera.free_buffer()
        
        '''Put the lasers voltage to zero
           This is done at the end, because we do not want to shut down the lasers
           after each sweep to minimize their power fluctuations '''
        waveforms = np.stack(([0],[0]))
        self.lasers_task.write(waveforms)
        self.lasers_task.stop()
        self.lasers_task.close()
        
        print('Acquisition done')
        self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Acquisition done')
        '''Would be nice here to display in motor tab the current positions after stack_mode'''
        #Current camera position update
        #self.label_currentHorizontalNumerical.setText("{} {}".format(round(self.motor2.current_position(self.comboBox_unit.currentText()),self.decimals), self.comboBox_unit.currentText())) 
        self.pushButton_getSingleImage.setEnabled(True)
        self.pushButton_startLiveMode.setEnabled(True)
        self.pushButton_startStack.setEnabled(True)
        self.pushButton_stopStack.setEnabled(False)
        self.pushButton_startPreviewMode.setEnabled(True)
        self.pushButton_standbyOn.setEnabled(True)
        self.pushButton_calibrateCamera.setEnabled(True)
        
        self.frame_saver.stop_saving()
    
    def start_stack_mode(self):
        '''Initializes variables for volume saving which will take place in 
           self.stack_mode_thread afterwards'''
        
        '''Flags check up'''
        if self.preview_mode_started == True:
            self.stop_preview_mode()
            self.preview_mode_started = False
        if self.live_mode_started == True:
            self.stop_live_mode()
            self.live_mode_started = False
        if self.stack_mode_started == True:
            self.stop_stack_mode()
            self.stack_mode_started = False
        
        self.stack_mode_started = True
        
        '''Retrieving filename set by the user'''       
        self.filename = str(self.lineEdit_filename.text())   
        '''Removing spaces, dots and commas'''
            #self.filename = self.filename.replace(' ', '')
            #self.filename = self.filename.replace('.', '')
            #self.filename = self.filename.replace(',', '')
        
        '''Making sure the limits of the volume are set, saving is allowed and 
           filename isn't empty'''
        if self.checkBox_setStartPoint.isChecked()==False or self.checkBox_setEndPoint.isChecked()==False or self.doubleSpinBox_planeStep.value()==0:
            print('Set starting and ending points and select a non-zero plane step value')
            self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Set starting and ending points and select a non-zero plane step value')
            
        elif self.saving_allowed == False or self.filename == '':
            print('Select directory and enter a valid filename before saving')
            self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Select directory and enter a valid filename before saving')
            
        else:
            
            
            '''Setting start & end points and plane step (takes into account the direction of acquisition) '''
            if self.stack_mode_starting_point > self.stack_mode_ending_point:
                self.step = -1*self.doubleSpinBox_planeStep.value()
                self.start_point = self.stack_mode_starting_point
                self.end_point = self.stack_mode_starting_point+self.step*(self.number_of_planes-1)
            else:
                self.step = self.doubleSpinBox_planeStep.value()
                self.start_point = self.stack_mode_starting_point
                self.end_point = self.stack_mode_starting_point+self.step*(self.number_of_planes-1)
                
            
            self.stack_mode_started = True
            
            '''Modes disabling while stack acquisition'''
            self.pushButton_getSingleImage.setEnabled(False)
            self.pushButton_saveImage.setEnabled(False)
            self.pushButton_startLiveMode.setEnabled(False)
            self.pushButton_stopLiveMode.setEnabled(False)
            self.pushButton_startStack.setEnabled(False)
            self.pushButton_stopStack.setEnabled(True)
            self.pushButton_startPreviewMode.setEnabled(False)
            self.pushButton_stopPreviewMode.setEnabled(False)
            self.pushButton_standbyOn.setEnabled(False)
            
            
            '''Setting the camera for acquisition'''
            self.camera.set_trigger_mode('ExternalExposureControl')
            self.camera.arm_camera() 
            self.camera.get_sizes() 
            self.camera.allocate_buffer(number_of_buffers=2)    
            self.camera.set_recording_state(1)
            self.camera.insert_buffers_in_queue()
            
            
            ''' Prepare saving (if we lose planes while saving, add more buffers 
                to block size, but make sure they don't take all the RAM'''
            self.filename = self.save_directory + '/' + self.filename
            self.frame_saver = FrameSaver(self.filename)
            self.frame_saver.set_block_size(3)  #3 buffers allowed in the queue
            self.frame_saver.check_existing_files(self.filename, self.number_of_planes, 'stack')
            
            '''We can add attributes here (none implemented yet)'''
            
            self.set_data_consumer(self.frame_saver, False, "FrameSaver", True)
            self.frame_saver.start_saving(data_type = 'BUFFER')
            
            print(self.frame_saver.filenames_list)
            self.label_lastCommands.setText(self.label_lastCommands.text()+'\n '+self.frame_saver.filenames_list)
            
            '''Stop lasers thread if one is active (maybe use time.sleep() after
               if thread doesn't close fast enough before starting new lasers
               task)'''
            self.stop_lasers = False
            
            self.lasers_task = nidaqmx.Task()
            self.lasers_task.ao_channels.add_ao_voltage_chan(terminals["lasers"])
            lasers_thread = threading.Thread(target = self.lasers_thread)
            lasers_thread.start()
            
            self.ramps=AOETLGalvos(self.parameters)
            self.ramps.initialize()                   
            self.ramps.create_etl_waveforms(case = 'STAIRS')
            self.ramps.create_galvos_waveforms(case = 'TRAPEZE')
            self.ramps.create_digital_output_camera_waveform( case = 'STAIRS_FITTING')
            
            self.number_of_steps = np.ceil(self.parameters["columns"]/self.parameters["etl_step"])
            self.columns = self.parameters["columns"]
            self.etl_step = self.parameters["etl_step"]
            self.rows = self.parameters["rows"]
            
            print('Number of frames to save: '+str(self.number_of_planes))
            self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Number of frames to save: '+str(self.number_of_planes))
                
            stack_mode_thread = threading.Thread(target = self.stack_mode_thread)
            stack_mode_thread.start()
    
    def stop_stack_mode(self):
        '''Useless function for now. Would be useful to find a way to stop stack mode before it's done. 
           Note: check how to break a NI-Daqmx task
           Simpler solution: Use conditions with self._stack_mode_started status 
                             such as in self.live_mode_thread() and 
                             self.preview_mode_thread() '''
        self.stack_mode_started = False
    
    def calibrate_camera_thread(self):
        '''
        '''
        
        for i in range(10): #10 planes
            if self.camera_calibration_started == False: ###Pas encore implémenté
                print('Camera calibration interrupted')
                self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Camera calibration interrupted')
                break
            else:
                '''Moving sample position'''
                position = self.startPoint+i*100 #Step of 100 micro-meters
                self.motor2.move_absolute_position(position,'\u03BCm')  #Position in micro-meters
                self.camera_focus_relation[i,0]=position
                
                average_intensities=np.zeros(10)
                for j in range(-5,5): #10 positions de caméra?
                    position_camera = position+j #VÉRFIER
                    self.motor3.move_absolute_position(position_camera,'\u03BCm')  #Position in micro-meters
                    
                    '''Acquiring the frame'''
                    self.ramps.create_tasks(terminals,'FINITE')
                    self.ramps.write_waveforms_to_tasks()                            
                    self.ramps.start_tasks()
                    self.ramps.run_tasks()
                    
                    '''Retrieving buffer for the plane of the current position, 
                    and frame reconstruction for display'''
                    buffer = self.camera.retrieve_multiple_images(self.number_of_steps, self.ramps.t_half_period, sleep_timeout = 5)
        
                    self.ramps.stop_tasks()                             
                    self.ramps.close_tasks()
                    
                    intensities = np.sort(buffer, axis=None)
                    average_intensities[j]=np.average(intensities[-10:]) #10 max intensities considered
                
                self.camera_focus_relation[i,1]=np.argmax(average_intensities)+position #VÉRIFIER
                
        
        self.stopLasers = True
           
        self.camera.cancel_images()
        self.camera.set_recording_state(0)
        self.camera.free_buffer()
        

        print(self.camera_focus_relation)
        print('Camera calibration done')
        self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Camera calibration done')
        self.pushButton_getSingleImage.setEnabled(True)
        self.pushButton_startStack.setEnabled(True)
        self.pushButton_startLiveMode.setEnabled(True)
        self.pushButton_startPreviewMode.setEnabled(True)
        self.pushButton_calibrateCamera.setEnabled(True)
        self.pushButton_standbyOn.setEnabled(True)
        
        self.frame_saver.stop_saving()
        
        self.camera_calibration_started = False ###???
    
    def calibrate_camera(self):
        calibrate_camera_thread = threading.Thread(target = self.calibrate_camera_thread)
        calibrate_camera_thread.start()
        print('Camera calibration started')
        self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Camera calibration started')
        
        self.pushButton_getSingleImage.setEnabled(False)
        self.pushButton_saveImage.setEnabled(False)
        self.pushButton_startStack.setEnabled(False)
        self.pushButton_stopStack.setEnabled(False)
        self.pushButton_startLiveMode.setEnabled(False)
        self.pushButton_stopLiveMode.setEnabled(False)
        self.pushButton_startPreviewMode.setEnabled(False)
        self.pushButton_stopPreviewMode.setEnabled(False)
        self.pushButton_calibrateCamera.setEnabled(False)
        self.pushButton_standbyOn.setEnabled(False)
        self.pushButton_standbyOff.setEnabled(False)   

class CameraWindow(queue.Queue):
    '''Class for image display'''
    
    histogram_level = []
    
    def __init__(self):
        
        '''Bigger queue size allows more image to be put in its queue. However, 
        since many images can take a lot of RAM and it is not necessary to see 
        all the planes that are saved, we keep the queue short. It is more 
        important to save all the planes then to see all of them while in
        acquisition. To this effect, the block_size (i.e. the queue) of 
        FrameSaver should be prioritized. On the other end, setting a shorter 
        time for the QTimer in test_galvo.py permits more frequent updates for
        image display thus potentially avoiding the need of a bigger queue if it 
        is important for the user to see all the frames.'''
        queue.Queue.__init__(self,2)   #Queue of size 2
        
        self.lines = 2160
        self.columns = 2560
        self.container = np.zeros((self.lines, self.columns))
        self.container[0] = 1000 #To get initial range of the histogram 
        self.imv = pg.ImageView(view = pg.PlotItem())  
        self.imv.setWindowTitle('Camera Window')
        self.scene = self.imv.scene
        self.imv.show()
        self.imv.setImage(np.transpose(self.container))
        
    def put(self, item, block=True, timeout=None):
        '''Put the image in its queue'''
        
        if queue.Queue.full(self) == False: 
            queue.Queue.put(self, item, block=block, timeout=timeout)
        else:
            pass    
                 
    def update(self):
        '''Executes at each interval of the QTimer set in test_galvo.py
           Takes the image in its queue and displays it in the window'''
        try:
            _view = self.imv.getView()
            _view_box = _view.getViewBox()
            _state = _view_box.getState()
            
            first_update = False
            if self.histogram_level == []:
                first_update = True
            _histo_widget = self.imv.getHistogramWidget()
            self.histogram_level = _histo_widget.getLevels()
            
            frame = self.get(False)
            self.imv.setImage(np.transpose(frame))
            
            _view_box.setState(_state)
            
            if not first_update:
                _histo_widget.setLevels(self.histogram_level[0],self.histogram_level[1])
        
        except queue.Empty:
            pass
        

class FrameSaver():
    '''Class for storing buffers (images) in its queue and saving them 
       afterwards in a specified directory in a HDF5 format'''
    
    def __init__(self, filename):
        #self.filename = filename
        #self.f = h5py.File(self.filename, 'a')
        pass
    
    def add_attribute(self, attribute, value):
        '''Attribute should be a string associated to the value, 
           like in a dictionary'''
        self.f[self.path_root].attrs[attribute]=value
        
    def check_existing_files(self, filename, number_of_planes, scan_type, data_type = 'BUFFER'):   #(self,path_name, scan_type)
        '''Makes sure the filenames are unique in the path to avoid overwrite on
           other files'''
        
        if data_type == "BUFFER":
            number_of_files = number_of_planes
        else:
            number_of_files = np.ceil(number_of_planes/self.block_size)
        
        self.filenames_list = [] 
        counter = 0
        
        for i in range(int(number_of_files)):
            in_loop = True
            while in_loop:
                counter += 1
                new_filename = filename + '_' + scan_type + '_plane_'+u'%05d'%counter+'.hdf5'
                
                if os.path.isfile(new_filename) == False:
                    in_loop = False
                    self.filenames_list.append(new_filename)
                    
    def put(self, value, flag):
        self.queue.put(value, flag)
        
    def save_thread(self):
        '''Thread for 2D array saving (kind of useless, we can always use
           self.save_thread_buffer even with a a 2D array)'''
        
        self.started = True
        for i in range(len(self.filenames_list)):
        
            f = h5py.File(self.filenames_list[i],'a')
            frame_number = 0
            in_loop = True
            counter = 1
            
            while in_loop:
                try:
                    frame = self.queue.get(True,1)
                    print('Frame received')
                    
                    if frame_number == 0:
                        buffer = np.zeros((frame.shape[0],frame.shape[1],self.block_size))
                    
                    buffer[:,:,frame_number] = frame
                    frame_number = (frame_number+1) % self.block_size
                    
                    '''Executes when block_size is reached'''
                    if frame_number == 0:
                        for ii in range(self.block_size):
                            path_root = self.path_root+'_'+u'%05d'%counter
                            f.create_dataset(path_root, data = buffer[:,:,ii])
                            counter = counter + 1
                        
                        in_loop = False
                        #self.child_conn.send([i, self.queue.qsize()])
                        
                except:
                    print('No frame')
                    
                    if self.started == False:
                        in_loop = False
                        
            if frame_number !=0:
                buffer2 = np.zeros((frame.shape[0], frame.shape[1], frame_number+1))
                buffer2 = buffer[:,:,0:frame_number]
                
                for ii in range(frame_number):
                    path_root = self.path_root+'_'+u'%05d'%counter
                    f.create_dataset(path_root, data = buffer2[:,:,ii])
                    counter = counter +1
            
            f.close()
            
    def save_thread_buffer(self):
        '''Thread for buffer saving'''
        self.started = True
        for i in range(len(self.filenames_list)):
            
            f = h5py.File(self.filenames_list[i],'a')
            in_loop = True
            counter = 1
            
            while in_loop:
                try:
                    buffer = self.queue.get(True,1)
                    print('Buffer received \n')
                    
                    for ii in range(buffer.shape[0]):
                        path_root = 'scan'+'_'+u'%03d'%counter
                        f.create_dataset(path_root, data = buffer[ii,:,:])
                        counter += 1
                        
                    in_loop = False
                
                except:
                    print('No buffer')
                    
                    if self.started == False:
                        in_loop = False
            
            f.close()
        
    def set_block_size(self, block_size):
        '''If we lose images while stack_mode acquisition, think about setting a
           bigger block_size (storing more images at a time), or use time.sleep()
           after each stack_mode loop if we don't have enough RAM to enlarge the
           block_size (hence we give time to FrameSaver to make space in its
           queue)'''
        self.block_size = block_size
        self.queue = queue.Queue(2*block_size)
        
    def set_dataset_name(self,path_name):
        self.path_name = path_name
        self.f.create_group(self.path_name)   #Create sub-group (folder)
        
    def set_path_root(self):
        scan_date = str(datetime.date.today())
        self.path_root = posixpath.join('/', scan_date) 
        
    def start_saving(self, data_type):
        
        if data_type == '2D_ARRAY':
            frame_saver_thread = threading.Thread(target = self.save_thread)
            frame_saver_thread.start()
        elif data_type == 'BUFFER':
            frame_saver_thread = threading.Thread(target = self.save_thread_buffer)
            frame_saver_thread.start()
            
    def stop_saving(self):
        '''Changes the flag status to end the thread'''
        self.started = False

def save_process(queue, filenames_list, path_root, block_size, conn):    
    '''Old version version of the thread saving function. Not in use.'''
    
    for i in range(len(filenames_list)):
        
        f = h5py.File(filenames_list[i],'a')
        frame_number = 0
        in_loop = True
        
        while in_loop:
            try:
                frame = queue.get(True,1)
                print('Frame received')
                
                if frame_number == 0:
                    buffer = np.zeros((frame.shape[0],frame.shape[1],block_size))
                
                buffer[:,:,frame_number] = frame
                frame_number = (frame_number+1) % block_size
                
                '''Executes when block_size is reached'''
                if frame_number == 0:
                    for ii in range(block_size):
                        f.create_dataset(path_root, data = buffer[:,:,ii])
                    
                    in_loop = False
                    conn.send([i, queue.qsize()])
                    
            except:
                print('No frame')
                
                if conn.poll():
                    print('Checking connection status')
                    in_loop = conn.recv()[0]
                    
        if frame_number !=0:
            buffer2 = np.zeros((frame.shape[0], frame.shape[1], frame_number+1))
            buffer2 = buffer[:,:,0:frame_number]
            
            for ii in range(frame_number):
                f.create_dataset(path_root, data = buffer2[:,:,ii])
        
        f.close()