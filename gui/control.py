'''
Created on May 22, 2019

@authors: Pierre Girard-Collins & flesage
'''

import sys
sys.path.append("..")

import os
import numpy as np
from matplotlib import pyplot as plt
from scipy import interpolate
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
    Class for control of the MesoSPIM
    '''
    
    '''Initialization Methods'''
    
    def __init__(self):
        QWidget.__init__(self)
        
        '''Loading user interface'''
        basepath= os.path.join(os.path.dirname(__file__))
        uic.loadUi(os.path.join(basepath,"control.ui"), self)
        
        '''Defining attributes'''
        self.parameters = copy.deepcopy(parameters)
        self.defaultParameters = copy.deepcopy(parameters)
        
        self.consumers = [] ###classer
        
        '''Initializing flags'''
        self.both_lasers_activated = False
        self.left_laser_activated = False
        self.right_laser_activated = False
        self.laser_on = False
        
        self.standby = False
        self.preview_mode_started = False
        self.live_mode_started = False
        self.stack_mode_started = False
        self.camera_on = True
        
        self.saving_allowed = False
        self.camera_calibration_started = False
        self.etls_galvos_calibration_started = False
        
        self.horizontal_forward_boundary_selected = False
        self.horizontal_backward_boundary_selected = False
        self.focus_selected = False
        
        '''Instantiating the camera window where the frames are displayed'''
        self.camera_window = CameraWindow()
        
        '''Instantiating the hardware components'''
        self.motor_vertical = Motors(1, 'COM3')    #Vertical motor
        self.motor_horizontal = Motors(2, 'COM3')  #Horizontal motor for sample motion
        self.motor_camera = Motors(3, 'COM3')      #Horizontal motor for camera motion (detection arm)
        
        self.camera = Camera()
        
        '''Initializing the properties of the widgets'''
        self.initialize_widgets()        
        
        '''Initializing every other widget that are updated by a change of unit 
            (the motion tab)'''
        self.update_unit()
        
        '''Initializing widgets' connections'''
        '''Connection for unit change'''
        self.comboBox_unit.currentTextChanged.connect(self.update_unit)
        
        '''Connection for data saving'''
        self.pushButton_selectDirectory.clicked.connect(self.select_directory)
        
        '''Connections for the modes'''
        self.pushButton_getSingleImage.clicked.connect(self.get_single_image)
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
        self.pushButton_motorUp.clicked.connect(self.move_sample_up)
        self.pushButton_motorDown.clicked.connect(self.move_sample_down)
        self.pushButton_motorRight.clicked.connect(self.move_sample_forward)
        self.pushButton_motorLeft.clicked.connect(self.move_sample_backward)
        self.pushButton_motorOrigin.clicked.connect(self.move_sample_to_origin)
        self.pushButton_setAsOrigin.clicked.connect(self.set_sample_origin)
        
        self.pushButton_movePosition.clicked.connect(self.move_to_horizontal_position)
        self.pushButton_moveHeight.clicked.connect(self.move_to_vertical_position)
        self.pushButton_moveCamera.clicked.connect(self.move_camera_to_position)
        
        self.pushButton_setFocus.clicked.connect(self.set_camera_focus)
        self.pushButton_calculateFocus.clicked.connect(self.calculate_camera_focus)
        
        self.pushButton_forward.clicked.connect(self.move_camera_forward)
        self.pushButton_backward.clicked.connect(self.move_camera_backward)
        self.pushButton_focus.clicked.connect(self.move_camera_to_focus)
        
        self.pushButton_calibrateRange.clicked.connect(self.reset_boundaries)
        self.pushButton_setForwardLimit.clicked.connect(self.set_horizontal_forward_boundary)
        self.pushButton_setBackwardLimit.clicked.connect(self.set_horizontal_backward_boundary)
        
        self.pushButton_calibrateCamera.pressed.connect(self.start_calibrate_camera)
        self.pushButton_cancelCalibrateCamera.pressed.connect(self.stop_calibrate_camera)
        self.pushButton_showInterpolation.pressed.connect(self.show_interpolation)
        
        self.pushButton_calibrateEtlsGalvos.pressed.connect(self.start_calibrate_etls_galvos)
        self.pushButton_stopEtlsGalvosCalibration.pressed.connect(self.stop_calibrate_etls_galvos)
        
        '''Connections for the ETLs and Galvos parameters'''
        self.doubleSpinBox_leftEtlAmplitude.valueChanged.connect(lambda: self.update_etl_galvos_parameters(1))
        self.doubleSpinBox_rightEtlAmplitude.valueChanged.connect(lambda: self.update_etl_galvos_parameters(2))
        self.doubleSpinBox_leftEtlOffset.valueChanged.connect(lambda: self.update_etl_galvos_parameters(3))
        self.doubleSpinBox_rightEtlOffset.valueChanged.connect(lambda: self.update_etl_galvos_parameters(4))
        self.doubleSpinBox_leftGalvoAmplitude.valueChanged.connect(lambda: self.update_etl_galvos_parameters(5))
        self.doubleSpinBox_rightGalvoAmplitude.valueChanged.connect(lambda: self.update_etl_galvos_parameters(6))
        self.doubleSpinBox_leftGalvoOffset.valueChanged.connect(lambda: self.update_etl_galvos_parameters(7))
        self.doubleSpinBox_rightGalvoOffset.valueChanged.connect(lambda: self.update_etl_galvos_parameters(8))
        self.doubleSpinBox_leftGalvoFrequency.valueChanged.connect(lambda: self.update_etl_galvos_parameters(9))
        self.doubleSpinBox_rightGalvoFrequency.valueChanged.connect(lambda: self.update_etl_galvos_parameters(10))
        self.doubleSpinBox_samplerate.valueChanged.connect(lambda: self.update_etl_galvos_parameters(11))
        self.spinBox_etlStep.valueChanged.connect(lambda: self.update_etl_galvos_parameters(12))
        self.pushButton_defaultParameters.clicked.connect(self.back_to_default_parameters)
        
        '''Connections for the lasers'''
        self.pushButton_lasersOn.clicked.connect(self.activate_both_lasers)
        self.pushButton_lasersOff.clicked.connect(self.deactivate_both_lasers)
        self.pushButton_leftLaserOn.clicked.connect(self.activate_left_laser)
        self.pushButton_leftLaserOff.clicked.connect(self.deactivate_left_laser)
        self.pushButton_rightLaserOn.clicked.connect(self.activate_right_laser)
        self.pushButton_rightLaserOff.clicked.connect(self.deactivate_right_laser)
        self.horizontalSlider_leftLaser.sliderReleased.connect(self.update_left_laser)
        self.horizontalSlider_rightLaser.sliderReleased.connect(self.update_right_laser)
    
    def initialize_widgets(self):
        '''Initializes the properties of the widgets that are not updated by a 
        change of units, i.e. the widgets that cannot be initialize with 
        self.update_unit()'''
        
        '''--Data saving's related widgets--'''
        self.lineEdit_filename.setEnabled(False)
        
        '''--Motion's related widgets--'''
        self.comboBox_unit.insertItems(0,["cm","mm","\u03BCm"])
        self.comboBox_unit.setCurrentIndex(1) #Default unit in millimeters
        
        self.pushButton_setForwardLimit.setEnabled(False)
        self.pushButton_setBackwardLimit.setEnabled(False)
        self.pushButton_calculateFocus.setEnabled(False)
        self.pushButton_showInterpolation.setEnabled(True) ###changer pour false
        
        self.horizontal_forward_boundary = 533333.3333  #Maximum motor position, in micro-steps
        self.horizontal_backward_boundary = 0           #Mimimum motor position, in micro-steps
        
        self.vertical_up_boundary = 1060000.6667        #Maximum motor position, in micro-steps
        self.vertical_down_boundary = 0                 #Mimimum motor position, in micro-steps
        
        self.camera_forward_boundary = 500000           #Maximum motor position, in micro-steps ###À adapter selon le nouveau porte-cuvette
        self.camera_backward_boundary = 0               #Mimimum motor position, in micro-steps
        
        self.focus = 265000     #Default focus position ###Possiblement à changer
        
        self.last_horizontal_position = self.motor_horizontal.current_position('\u03BCStep')
        self.last_vertical_position = self.motor_vertical.current_position('\u03BCStep')
        self.last_camera_position = self.motor_camera.current_position('\u03BCStep')
        
        '''Arbitrary origin positions (in micro-steps)'''
        self.origin_horizontal = self.horizontal_forward_boundary
        self.origin_vertical = self.motor_vertical.position_to_data(1.0, 'cm') ###
        
        '''--Modes' related widgets--'''
        '''Disable some buttons'''
        self.pushButton_stopLiveMode.setEnabled(False)
        self.pushButton_stopStack.setEnabled(False)
        self.pushButton_saveImage.setEnabled(False)
        self.pushButton_stopPreviewMode.setEnabled(False)
        self.pushButton_standbyOff.setEnabled(False)
        self.pushButton_cancelCalibrateCamera.setEnabled(False)
        
        self.checkBox_setStartPoint.setEnabled(False)
        self.checkBox_setEndPoint.setEnabled(False)
        
        '''Initialize plane steps'''
        self.doubleSpinBox_planeStep.setSuffix(' \u03BCm')
        self.doubleSpinBox_planeStep.setDecimals(0)
        self.doubleSpinBox_planeStep.setMaximum(101600) ###???
        self.doubleSpinBox_planeStep.setSingleStep(1)
        
        self.doubleSpinBox_numberOfCalibrationPlanes.setSuffix(' planes')
        self.doubleSpinBox_numberOfCalibrationPlanes.setDecimals(0)
        self.doubleSpinBox_numberOfCalibrationPlanes.setValue(10) #10 planes by default
        self.doubleSpinBox_numberOfCalibrationPlanes.setMinimum(3) #To allow interpolation
        self.doubleSpinBox_numberOfCalibrationPlanes.setMaximum(10000) ###???
        self.doubleSpinBox_numberOfCalibrationPlanes.setSingleStep(1)
        
        self.doubleSpinBox_numberOfCameraPositions.setSuffix(' planes')
        self.doubleSpinBox_numberOfCameraPositions.setDecimals(0)
        self.doubleSpinBox_numberOfCameraPositions.setValue(10) #10 camera positions by default
        self.doubleSpinBox_numberOfCameraPositions.setMaximum(10000) ###???
        self.doubleSpinBox_numberOfCameraPositions.setSingleStep(1)
        
        '''--ETLs and galvos parameters' related widgets--'''
        '''Initialize values'''
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
        
        self.spinBox_etlStep.setValue(self.parameters["etl_step"])
        
        '''Initialize step values'''
        self.doubleSpinBox_leftEtlAmplitude.setSingleStep(0.1)
        self.doubleSpinBox_rightEtlAmplitude.setSingleStep(0.1)
        self.doubleSpinBox_leftEtlOffset.setSingleStep(0.1)
        self.doubleSpinBox_rightEtlOffset.setSingleStep(0.1)
        
        self.doubleSpinBox_leftGalvoAmplitude.setSingleStep(0.1)
        self.doubleSpinBox_rightGalvoAmplitude.setSingleStep(0.1)
        self.doubleSpinBox_leftGalvoOffset.setSingleStep(0.1)
        self.doubleSpinBox_rightGalvoOffset.setSingleStep(0.1)
        
        '''Initialize suffixes'''
        self.doubleSpinBox_leftEtlAmplitude.setSuffix(" V")
        self.doubleSpinBox_rightEtlAmplitude.setSuffix(" V")
        self.doubleSpinBox_leftEtlOffset.setSuffix(" V")
        self.doubleSpinBox_rightEtlOffset.setSuffix(" V")
        
        self.doubleSpinBox_leftGalvoAmplitude.setSuffix(" V")
        self.doubleSpinBox_rightGalvoAmplitude.setSuffix(" V")
        self.doubleSpinBox_leftGalvoOffset.setSuffix(" V")
        self.doubleSpinBox_rightGalvoOffset.setSuffix(" V")
        self.doubleSpinBox_leftGalvoFrequency.setSuffix(" Hz")
        self.doubleSpinBox_rightGalvoFrequency.setSuffix(" Hz")
        
        self.doubleSpinBox_samplerate.setSuffix(" samples/s")
        
        self.spinBox_etlStep.setSuffix(" columns")
        
        '''Initialize maximum and minimum values'''
        self.doubleSpinBox_leftEtlAmplitude.setMaximum(5)
        self.doubleSpinBox_rightEtlAmplitude.setMaximum(5)
        self.doubleSpinBox_leftEtlOffset.setMaximum(5)
        self.doubleSpinBox_rightEtlOffset.setMaximum(5)
        
        self.doubleSpinBox_leftGalvoAmplitude.setMaximum(10)
        self.doubleSpinBox_leftGalvoAmplitude.setMinimum(-10)
        self.doubleSpinBox_rightGalvoAmplitude.setMaximum(10)
        self.doubleSpinBox_rightGalvoAmplitude.setMinimum(-10)
        self.doubleSpinBox_leftGalvoOffset.setMaximum(10)
        self.doubleSpinBox_leftGalvoOffset.setMinimum(-10)
        self.doubleSpinBox_rightGalvoOffset.setMaximum(10)
        self.doubleSpinBox_rightGalvoOffset.setMinimum(-10)
        self.doubleSpinBox_leftGalvoFrequency.setMaximum(130)
        self.doubleSpinBox_rightGalvoFrequency.setMaximum(130)
        
        self.doubleSpinBox_samplerate.setMaximum(1000000)
        
        self.spinBox_etlStep.setMaximum(2560)
        
        '''--Lasers parameters' related widgets--'''
        '''Disable some buttons'''
        self.pushButton_lasersOff.setEnabled(False)
        self.pushButton_leftLaserOff.setEnabled(False)
        self.pushButton_rightLaserOff.setEnabled(False)
        
        '''Initialize text'''
        self.label_leftLaserVoltage.setText('{} {}'.format(parameters["laser_l_voltage"], 'V'))
        self.label_rightLaserVoltage.setText('{} {}'.format(parameters["laser_r_voltage"], 'V'))
        
        '''Initialize sliders
           Note: QSlider only takes integers, the integers are 10x the voltage
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
    
    
    '''General Methods'''
    
    def closeEvent(self, event):
        '''Making sure that everything is closed when the user exits the software.
           This function executes automatically when the user closes the UI.
           This is an intrinsic function name of Qt, don't change the name even 
           if it doesn't follow the naming convention'''
        
        if self.laser_on == True:
            self.stop_lasers()
        if self.preview_mode_started == True:
            self.stop_preview_mode()
        if self.live_mode_started == True:
            self.stop_live_mode()
        if self.stack_mode_started == True:
            self.stop_stack_mode()
        if self.camera_on == True:
            self.close_camera()
        if self.standby == True:
            self.stop_standby()
        if self.camera_calibration_started == True:
            self.stop_calibrate_camera()
        ###if self.etls_galvos_calibration_started == True:
        ###    self.stop_calibrate_etls_galvos()
            
        event.accept()
    
    def open_camera(self):
        '''Opens the camera'''
        
        self.camera_on=True
        self.camera = Camera()
        print('Camera opened') 
        self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Camera opened')
    
    def close_camera(self):
        '''Closes the camera'''
        
        self.camera_on = False
        self.camera.close_camera()
        print('Camera closed')
        self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Camera closed')
    
    def set_data_consumer(self, consumer, wait, consumer_type, update_flag): ###Arranger
        ''' Regroups all the consumers in the same list'''
        
        self.consumers.append(consumer)
        self.consumers.append(wait)             #Pas implémenté
        self.consumers.append(consumer_type)    #Nom
        self.consumers.append(update_flag)      #Pas implémenté
    
    
    '''Motion Methods'''
    
    def update_unit(self):
        '''Updates all the widgets of the motion tab after an unit change'''
        
        self.unit = self.comboBox_unit.currentText()
        
        '''Update suffixes'''
        self.doubleSpinBox_incrementHorizontal.setSuffix(" {}".format(self.unit))
        self.doubleSpinBox_incrementVertical.setSuffix(" {}".format(self.unit))
        self.doubleSpinBox_incrementCamera.setSuffix(" {}".format(self.unit))
        self.doubleSpinBox_choosePosition.setSuffix(" {}".format(self.unit))
        self.doubleSpinBox_chooseHeight.setSuffix(" {}".format(self.unit))
        self.doubleSpinBox_chooseCamera.setSuffix(" {}".format(self.unit))
        
        '''Update default values'''
        self.doubleSpinBox_incrementHorizontal.setValue(1)
        self.doubleSpinBox_incrementVertical.setValue(1)
        self.doubleSpinBox_incrementCamera.setValue(1)
        self.doubleSpinBox_choosePosition.setValue(0)
        self.doubleSpinBox_chooseHeight.setValue(0)
        self.doubleSpinBox_chooseCamera.setValue(0) ###Impossible, car le min est 50mm
        
        '''Update maximum and minimum values'''
        
        if self.unit == 'cm':
            self.decimals = 4
            
            self.horizontal_correction = 10.16  #Horizontal correction to fit choice of axis
            self.vertical_correction = 1.0      #Vertical correction to fit choice of axis ###À ajuster avec nouveau porte-cuvette
            self.camera_sample_min_distance = 3.0   #Approximate minimal horizontal distance between camera  ###Possiblement à changer
            self.camera_correction = 9.525 + 4.0  #Camera correction to fit choice of axis###À ajuster avec nouveau porte-cuvette +arranger 5cm entre camera et origine
        elif self.unit == 'mm':
            self.decimals = 3
            
            self.horizontal_correction = 101.6      #Correction to fit choice of axis
            self.vertical_correction = 10.0         #Correction to fit choice of axis ###À ajuster avec nouveau porte-cuvette
            self.camera_sample_min_distance = 30.0   #Approximate minimal horizontal distance between camera  ###Possiblement à changer
            self.camera_correction =95.25 + 40.0      #Camera correction to fit choice of axis###À ajuster avec nouveau porte-cuvette
        elif self.unit == '\u03BCm':
            self.decimals = 0
            
            self.horizontal_correction = 101600     #Correction to fit choice of axis
            self.vertical_correction = 10000        #Correction to fit choice of axis ###À ajuster avec nouveau porte-cuvette
            self.camera_sample_min_distance = 30000   #Approximate minimal horizontal distance between camera  ###Possiblement à changer
            self.camera_correction = 95250 + 40000    #Camera correction to fit choice of axis###À ajuster avec nouveau porte-cuvette
        
        '''Update the number of decimals'''
        self.doubleSpinBox_incrementHorizontal.setDecimals(self.decimals)
        self.doubleSpinBox_incrementVertical.setDecimals(self.decimals)
        self.doubleSpinBox_incrementCamera.setDecimals(self.decimals)
        self.doubleSpinBox_choosePosition.setDecimals(self.decimals)
        self.doubleSpinBox_chooseHeight.setDecimals(self.decimals)
        self.doubleSpinBox_chooseCamera.setDecimals(self.decimals)
        
        '''Update maximum and minimum values for horizontal sample motion'''
        self.horizontal_maximum_in_old_axis = self.motor_horizontal.data_to_position(self.horizontal_forward_boundary,self.unit)    #This max is actually the min in our axis system
        self.horizontal_minimum_in_old_axis = self.motor_horizontal.data_to_position(self.horizontal_backward_boundary,self.unit)   #This min is actually the max in our axis system
        
        self.horizontal_maximum_in_new_axis = -self.horizontal_minimum_in_old_axis+self.horizontal_correction #Minus sign and correction to fit choice of axis
        self.horizontal_minimum_in_new_axis = -self.horizontal_maximum_in_old_axis+self.horizontal_correction #Minus sign and correction to fit choice of axis
        
        self.doubleSpinBox_choosePosition.setMinimum(self.horizontal_minimum_in_new_axis)
        self.doubleSpinBox_choosePosition.setMaximum(self.horizontal_maximum_in_new_axis)
        
        maximum_horizontal_increment = self.horizontal_maximum_in_new_axis-self.horizontal_minimum_in_new_axis
        self.doubleSpinBox_incrementHorizontal.setMaximum(maximum_horizontal_increment)
        self.doubleSpinBox_incrementHorizontal.setMinimum(1)
        
        '''Update maximum and minimum values for vertical sample motion'''
        self.vertical_maximum_in_old_axis = self.motor_vertical.data_to_position(self.vertical_up_boundary,self.unit)   #This max is actually the min in our axis system
        self.vertical_minimum_in_old_axis = self.motor_vertical.data_to_position(self.vertical_down_boundary,self.unit) #This min is actually the max in our axis system
        
        self.vertical_maximum_in_new_axis = -self.vertical_minimum_in_old_axis+self.vertical_correction #Minus sign and correction to fit choice of axis
        self.vertical_minimum_in_new_axis = -self.vertical_maximum_in_old_axis+self.vertical_correction #Minus sign and correction to fit choice of axis
        
        self.doubleSpinBox_chooseHeight.setMinimum(self.vertical_minimum_in_new_axis)
        self.doubleSpinBox_chooseHeight.setMaximum(self.vertical_maximum_in_new_axis)
        
        maximum_vertical_increment = self.vertical_maximum_in_new_axis-self.vertical_minimum_in_new_axis
        self.doubleSpinBox_incrementVertical.setMaximum(maximum_vertical_increment)
        self.doubleSpinBox_incrementVertical.setMinimum(1)
        
        '''Update maximum and minimum values for camera motion'''
        self.camera_maximum_in_old_axis = self.motor_camera.data_to_position(self.camera_forward_boundary,self.unit)    #This max is actually the min in our axis system
        self.camera_minimum_in_old_axis = self.motor_camera.data_to_position(self.camera_backward_boundary,self.unit)   #This min is actually the max in our axis system
        
        self.camera_maximum_in_new_axis = -self.camera_minimum_in_old_axis+self.camera_correction #Minus sign and correction to fit choice of axis
        self.camera_minimum_in_new_axis = -self.camera_maximum_in_old_axis+self.camera_correction #Minus sign and correction to fit choice of axis
        
        self.doubleSpinBox_chooseCamera.setMinimum(self.camera_minimum_in_new_axis)
        self.doubleSpinBox_chooseCamera.setMaximum(self.camera_maximum_in_new_axis)
        
        maximum_camera_increment = self.camera_maximum_in_new_axis-self.camera_minimum_in_new_axis
        self.doubleSpinBox_incrementVertical.setMaximum(maximum_camera_increment)
        self.doubleSpinBox_incrementCamera.setMinimum(1)
        
        '''Update current positions'''
        self.update_position_vertical()
        self.update_position_horizontal()
        self.update_position_camera()
    
    def update_position_horizontal(self):
        '''Updates the current horizontal sample position displayed'''
        
        current_horizontal_position = round(-self.motor_horizontal.current_position(self.unit)+self.horizontal_correction,self.decimals) #Minus sign and correction to fit choice of axis
        current__horizontal_position_text = "{} {}".format(current_horizontal_position, self.unit)
        self.label_currentHorizontalNumerical.setText(current__horizontal_position_text)
    
    def update_position_vertical(self):
        '''Updates the current vertical sample position displayed'''
        
        current_vertical_position = round(-self.motor_vertical.current_position(self.unit)+self.vertical_correction,self.decimals) #Minus sign and correction to fit choice of axis
        current_vertical_position_text = "{} {}".format(current_vertical_position, self.unit)
        self.label_currentHeightNumerical.setText(current_vertical_position_text)
        
    def update_position_camera(self):
        '''Updates the current (horizontal) camera position displayed'''
        
        #print(self.motor_camera.position_to_data(self.motor_camera.current_position(self.unit), self.unit)) #debugging
        
        current_camera_position = round(-self.motor_camera.current_position(self.unit)+self.camera_correction,self.decimals) #Minus sign and correction to fit choice of axis
        current__camera_position_text = "{} {}".format(current_camera_position, self.unit)
        self.label_currentCameraNumerical.setText(current__camera_position_text)
    
    
    def move_to_horizontal_position(self):
        '''Moves the sample to a specified horizontal position'''
        
        current_camera_position = -self.motor_camera.current_position(self.unit) + self.camera_correction #Minus sign and correction to fit choice of axis
            
        if (current_camera_position - self.doubleSpinBox_choosePosition.value() >= self.camera_sample_min_distance):  #To prevent the sample from hitting the camera
            print ('Sample moving to horizontal position')
            self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Sample moving to horizontal position')
            
            horizontal_position = -self.doubleSpinBox_choosePosition.value()+self.horizontal_correction
            self.motor_horizontal.move_absolute_position(horizontal_position,self.unit)
        
            self.update_position_horizontal()
        else:
            print('Camera prevents sample movement')
            self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Camera prevents sample movement')
    
    def move_to_vertical_position(self):
        '''Moves the sample to a specified vertical position'''
        
        print ('Sample moving to vertical position')
        self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Sample moving to vertical position')
            
        vertical_position = -self.doubleSpinBox_chooseHeight.value()+self.vertical_correction #Minus sign and correction to fit choice of axis
        self.motor_vertical.move_absolute_position(vertical_position,self.unit)
        
        self.update_position_vertical()
    
    def move_camera_to_position(self):
        '''Moves the sample to a specified vertical position'''
        
        current_horizontal_position = -self.motor_horizontal.current_position(self.unit) + self.horizontal_correction #Minus sign and correction to fit choice of axis
            
        if (self.doubleSpinBox_chooseCamera.value() - current_horizontal_position >= self.camera_sample_min_distance):  #To prevent the sample from hitting the camera
            print ('Camera moving to position')
            self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Camera moving to position')
            
            camera_position = -self.doubleSpinBox_chooseCamera.value()+self.camera_correction #Minus sign and correction to fit choice of axis
            self.motor_camera.move_absolute_position(camera_position,self.unit)
            
            self.update_position_camera()
        else:
            print('Sample prevents camera movement')
            self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Sample prevents camera movement')
    
    def move_camera_backward(self):
        '''Camera motor backward horizontal motion'''
        
        if self.motor_camera.current_position(self.unit) - self.doubleSpinBox_incrementCamera.value() >= self.camera_minimum_in_old_axis:
            print ('Camera moving backward')
            self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Camera moving backward')
            
            self.motor_camera.move_relative_position(-self.doubleSpinBox_incrementCamera.value(),self.unit) ###Vérifier
        else:
            print('Out of boundaries')
            self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Out of boundaries')
            
            self.motor_camera.move_absolute_position(self.camera_backward_boundary,'\u03BCStep')
            
        self.update_position_camera()
    
    def move_camera_forward(self):
        '''Camera motor forward horizontal motion'''
        
        if self.motor_camera.current_position(self.unit) + self.doubleSpinBox_incrementCamera.value() <= self.camera_maximum_in_old_axis:
            
            current_horizontal_position = -self.motor_horizontal.current_position(self.unit) + self.horizontal_correction
            next_camera_position = -(self.motor_camera.current_position(self.unit)+self.doubleSpinBox_incrementCamera.value()) + self.camera_correction
            
            if (next_camera_position - current_horizontal_position >= self.camera_sample_min_distance):  #To prevent the sample from hitting the camea
                print ('Camera moving forward')
                self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Camera moving forward')
                self.motor_camera.move_relative_position(self.doubleSpinBox_incrementCamera.value(),self.unit)
            else:
                print('Sample prevents camera movement')
                self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Sample prevents camera movement')
        else:
            print('Out of boundaries')
            self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Out of boundaries')
            
            self.motor_camera.move_absolute_position(self.camera_forward_boundary,'\u03BCStep')
            
        self.update_position_camera()
    
    def move_camera_to_focus(self):
        '''Moves camera to focus position'''
        if self.focus_selected == True:
        
            if self.focus < self.camera_backward_boundary:
                print('Focus out of boundaries')
                self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Focus out of boundaries')
                
                self.motor_camera.move_absolute_position(self.camera_minimum_in_old_axis,self.unit)
            elif self.focus > self.camera_forward_boundary:
                print('Focus out of boundaries')
                self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Focus out of boundaries')
                
                self.motor_camera.move_absolute_position(self.camera_maximum_in_old_axis,self.unit)
            else:
                current_horizontal_position = -self.motor_horizontal.current_position(self.unit) + self.horizontal_correction
                next_camera_position = -self.motor_camera.data_to_position(self.focus, self.unit) + self.camera_correction
                
                if (next_camera_position - current_horizontal_position >= self.camera_sample_min_distance):  #To prevent the sample from hitting the camea
                    print('Moving to focus')
                    self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Moving to focus')
                    
                    self.motor_camera.move_absolute_position(self.focus,'\u03BCStep')
                else:
                    print('Sample prevents camera movement')
                    self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Sample prevents camera movement')
        else:
            print('Focus not yet set. Moving camera to default focus')
            self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Focus not yet set. Moving camera to default focus')
            
            self.motor_camera.move_absolute_position(self.focus,'\u03BCStep')
        
        self.update_position_camera()
    
    def move_sample_down(self):
        '''Sample motor downward vertical motion'''
        
        if self.motor_vertical.current_position(self.unit) - self.doubleSpinBox_incrementVertical.value() >= self.vertical_minimum_in_old_axis:
            print('Sample moving down')
            self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Sample moving down')
            
            self.motor_vertical.move_relative_position(self.doubleSpinBox_incrementVertical.value(),self.unit)
        else:
            print('Out of boundaries')
            self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Out of boundaries')
            
            self.motor_vertical.move_absolute_position(self.vertical_down_boundary,'\u03BCStep')
            
        self.update_position_vertical()
    
    def move_sample_up(self):
        '''Sample motor upward vertical motion'''
        
        if self.motor_vertical.current_position(self.unit) + self.doubleSpinBox_incrementVertical.value() <= self.vertical_maximum_in_old_axis:
            print('Sample moving up')
            self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Sample moving up')
            
            self.motor_vertical.move_relative_position(-self.doubleSpinBox_incrementVertical.value(),self.unit)
        else:
            print('Out of boundaries')
            self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Out of boundaries')
            
            self.motor_vertical.move_absolute_position(self.vertical_up_boundary,'\u03BCStep')
        
        self.update_position_vertical()
    
    def move_sample_backward(self):
        '''Sample motor backward horizontal motion'''
        
        if self.motor_horizontal.current_position(self.unit) - self.doubleSpinBox_incrementHorizontal.value() >= self.horizontal_minimum_in_old_axis:
            
            current_camera_position = -self.motor_camera.current_position(self.unit) + self.camera_correction
            next_horizontal_position = -(self.motor_horizontal.current_position(self.unit)-self.doubleSpinBox_incrementHorizontal.value()) + self.horizontal_correction
            
            if (current_camera_position - next_horizontal_position >= self.camera_sample_min_distance):  #To prevent the sample from hitting the camea
                print ('Sample moving backward')
                self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Sample moving backward')
                
                self.motor_horizontal.move_relative_position(-self.doubleSpinBox_incrementHorizontal.value(),self.unit)
            else:
                print('Camera prevents sample movement')
                self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Camera prevents sample movement')
        else:
            print('Out of boundaries')
            self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Out of boundaries')
            
            self.motor_horizontal.move_absolute_position(self.horizontal_backward_boundary, '\u03BCStep')
        
        self.update_position_horizontal()
            
    def move_sample_forward(self):
        '''Sample motor forward horizontal motion'''
        
        if self.motor_horizontal.current_position(self.unit) + self.doubleSpinBox_incrementHorizontal.value() <= self.horizontal_maximum_in_old_axis:
            print ('Sample moving forward')
            self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Sample moving forward')
            
            self.motor_horizontal.move_relative_position(self.doubleSpinBox_incrementHorizontal.value(),self.unit)
        else:
            print('Out of boundaries')
            self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Out of boundaries')
            
            self.motor_horizontal.move_absolute_position(self.horizontal_forward_boundary, '\u03BCStep')
        
        self.update_position_horizontal()
    
    def move_sample_to_origin(self):
        '''Moves vertical and horizontal sample motors to origin position'''
        
        print('Moving to origin')
        self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Moving to origin')        
        
        origin_horizontal_current_unit = self.motor_horizontal.data_to_position(self.origin_horizontal, self.unit)
        if origin_horizontal_current_unit >= self.horizontal_minimum_in_old_axis and origin_horizontal_current_unit <= self.horizontal_maximum_in_old_axis:
            
            current_camera_position = -self.motor_camera.current_position(self.unit) + self.camera_correction
            next_horizontal_position = -origin_horizontal_current_unit + self.horizontal_correction
            
            if (current_camera_position - next_horizontal_position >= self.camera_sample_min_distance):  #To prevent the sample from hitting the camea
                '''Moving sample to horizontal origin'''
                self.motor_horizontal.move_absolute_position(self.origin_horizontal,'\u03BCStep')
                self.update_position_horizontal()
            else:
                print('Camera prevents sample movement')
                self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Camera prevents sample movement')
            
        else:
            print('Sample Horizontal Origin Out Of Boundaries')
            self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Sample Horizontal Origin Out of boundaries')
        
        '''Moving sample to vertical origin'''
        self.motor_vertical.move_absolute_position(self.origin_vertical,'\u03BCStep')
        self.update_position_vertical()
    
    
    def reset_boundaries(self):
        '''Reset variables for setting sample's horizontal motion range 
           (to avoid hitting the glass walls)'''
        
        self.pushButton_setForwardLimit.setEnabled(True)
        self.pushButton_setBackwardLimit.setEnabled(True)
        
        self.label_calibrateRange.setText("Move Horizontal Position")
        
        self.upperBoundarySelected = False
        self.lowerBoundarySelected = False
        self.pushButton_calibrateRange.setEnabled(False)
        
        '''Default boundaries'''
        self.horizontal_forward_boundary = 533333.3333  #Maximum motor position, in micro-steps
        self.horizontal_backward_boundary = 0           #Minimum motor position, in micro-steps
        
        self.update_unit() 
    
    def set_horizontal_backward_boundary(self):
        '''Set lower limit of sample's horizontal motion 
           (to avoid hitting the glass walls)'''
        
        self.horizontal_backward_boundary = self.motor_horizontal.current_position('\u03BCStep')
        self.update_unit()
        
        self.horizontal_backward_boundary_selected = True
        
        self.pushButton_setBackwardLimit.setEnabled(False)
        if self.horizontal_forward_boundary_selected == True:
            self.pushButton_calibrateRange.setEnabled(True)
            self.label_calibrateRange.setText('Press Calibrate Range To Start')
    
    def set_horizontal_forward_boundary(self):
        '''Set upper limit of sample's horizontal motion 
           (to avoid hitting the glass walls)'''
        
        self.horizontal_forward_boundary = self.motor_horizontal.current_position('\u03BCStep')
        self.update_unit()
        
        self.horizontal_forward_boundary_selected = True
        
        self.pushButton_setForwardLimit.setEnabled(False)
        if self.horizontal_backward_boundary_selected == True:
            self.pushButton_calibrateRange.setEnabled(True)
            self.label_calibrateRange.setText('Press Calibrate Range To Start')
    
    def set_sample_origin(self):
        '''Modifies the sample origin position'''
        
        self.origin_horizontal = self.motor_horizontal.position_to_data(self.motor_horizontal.current_position(self.unit),self.unit)
        self.origin_vertical = 1066666 - self.motor_vertical.position_to_data(self.motor_vertical.current_position(self.unit),self.unit) ###???
        
        origin_text = 'Origin set at (x,z) = ({}, {}) {}'.format(self.origin_horizontal,self.origin_vertical, self.unit)
        print(origin_text)
        self.label_lastCommands.setText(self.label_lastCommands.text()+origin_text)
    
    def set_camera_focus(self):
        '''Modifies manually the camera focus position'''
        
        self.focus_selected = True
        self.focus = self.motor_camera.current_position('\u03BCStep')
        
        print('Focus manually set')
        self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Focus manually set')
        
    def calculate_camera_focus(self):
        '''Interpolates the camera focus position'''
        
        x = self.camera_focus_relation[:,0]
        y = self.camera_focus_relation[:,1]
        
        #tck = interpolate.splrep(x,y) #tck is a tuple (t,c,k) containing the vector of knots, the B-spline coefficients, and the degree of the spline
        f = interpolate.interp1d(x, y, kind='quadratic', fill_value='extrapolate')
        current_position = round(-self.motor_horizontal.current_position(self.unit) + self.horizontal_correction, self.decimals)
        ###focus_interpolation = interpolate.splev(current_position,tck) ###Arranger interpolation
        focus_interpolation = f(current_position)
        self.focus = self.motor_camera.position_to_data(-focus_interpolation+self.camera_correction, self.unit)
        
        ###print('interpolation_coefficients:') #debugging
        ###print(tck)
        print('focus:') #debugging
        print(self.focus)
        ###print(focus_interpolation)
        print(round(-self.motor_camera.data_to_position(self.focus, self.unit)+self.camera_correction, self.decimals))
        
        self.focus_selected = True
        
        print('Focus automatically set')
        self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Focus automatically set')
    
    def show_interpolation(self):
        '''Shows the camera focus interpolation'''
        
        #self.camera_focus_relation = np.array([[20.15,   94.25], [20.3,   94.2 ], 
        #                              [20.45,   94.35], [20.6,   94.25],
        #                              [20.75,   94.25], [20.9,   94.3 ], 
        #                              [21.05,   94.3 ], [21.2,   94.25],
        #                              [21.35,   94.4 ], [21.5,   94.25],
        #                              [21.65,   94.15], [21.8,   94.2 ],
        #                              [21.95,   94.3 ], [22.1,   94.25],
        #                              [22.25,   94.25], [22.4,   94.3 ],
        #                              [22.55,   94.2 ], [22.7,   94.35],
        #                              [22.85,   94.3 ], [23.,   94.3 ],
        #                              [23.15,   94.2 ], [23.3,   94.4 ],
        #                              [23.45,   94.25], [23.6,   94.2 ],
        #                              [23.75,   94.35], [23.9,   94.3 ],
        #                              [24.05,   94.25], [24.2,   94.45],
        #                              [24.35,   94.15], [24.5,   94.45]])
        #self.camera_focus_relation[:,0]=[ 20.5, 21., 21.5, 22., 22.5, 23., 23.5, 24. , 24.5, 25.] #debugging
        #self.camera_focus_relation[:,1]=[96.7, 96.7, 96.7, 94., 96.7, 96.7, 96.7, 96.7, 96.7, 96.7]
        
        x = self.camera_focus_relation[:,0]
        y = self.camera_focus_relation[:,1]
        
        variance = np.var(y)
        print('variance:') #debugging
        print(variance)
        
        xnew = np.linspace(self.camera_focus_relation[0,0], self.camera_focus_relation[-1,0], 1000) ###1000 points
        #tck = interpolate.splrep(x,y) #tck is a tuple (t,c,k) containing the vector of knots, the B-spline coefficients, and the degree of the spline
        #ynew = interpolate.splev(xnew, tck)
        f = interpolate.interp1d(x, y, kind='quadratic', fill_value='extrapolate')
        ynew = f(xnew)
        
        '''Showing interpolation graph'''
        plt.figure(1)
        plt.title('Camera Focus Interpolation') 
        plt.xlabel('Sample Horizontal Position ({})'.format(self.unit)) 
        plt.ylabel('Camera Position ({})'.format(self.unit))
        plt.plot(x, y, 'o')
        plt.plot(xnew,ynew)
        plt.show(block=False)   #Prevents the plot from blocking the execution of the code...
        
        plt.figure(2)
        plt.title('Camera Focus Intensities Averages') 
        plt.xlabel('Camera Horizontal Position ({})'.format(self.unit)) 
        plt.ylabel('Intensity average')
        plt.plot(self.cam_positions, self.averages[:,0], 'o')
        plt.plot(self.cam_positions, self.averages[:,1], 'o')
        plt.show(block=False)   #Prevents the plot from blocking the execution of the code...
        
        plt.figure(3)
        plt.title('Camera Focus Intensities Variances') 
        plt.xlabel('Camera Horizontal Position ({})'.format(self.unit)) 
        plt.ylabel('Intensity variance')
        plt.plot(self.cam_positions, self.variances[:,0], 'o')
        plt.plot(self.cam_positions, self.variances[:,1], 'o')
        plt.show(block=False)   #Prevents the plot from blocking the execution of the code...
    
    
    '''Parameters Methods'''
    
    def back_to_default_parameters(self):
        '''Change all the modifiable parameters to go back to the initial state'''
        
        self.parameters = copy.deepcopy(self.defaultParameters) ###Nécessaire?
        
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
    
    def update_etl_galvos_parameters(self, parameterNumber):
        '''Updates the parameters in the software after a modification by the
           user'''
        
        if parameterNumber==1:
            self.doubleSpinBox_leftEtlAmplitude.setMaximum(5-self.doubleSpinBox_leftEtlOffset.value()) #To prevent ETL's amplitude + offset being > 5V
            self.parameters["etl_l_amplitude"]=self.doubleSpinBox_leftEtlAmplitude.value()
            if self.checkBox_etlsTogether.isChecked() == True:
                self.parameters["etl_r_amplitude"]=self.doubleSpinBox_leftEtlAmplitude.value()
                self.doubleSpinBox_rightEtlAmplitude.setValue(self.parameters["etl_r_amplitude"])
        elif parameterNumber==2:
            self.doubleSpinBox_rightEtlAmplitude.setMaximum(5-self.doubleSpinBox_rightEtlOffset.value()) #To prevent ETL's amplitude + offset being > 5V
            self.parameters["etl_r_amplitude"]=self.doubleSpinBox_rightEtlAmplitude.value()
            if self.checkBox_etlsTogether.isChecked() == True:
                self.parameters["etl_l_amplitude"]=self.doubleSpinBox_rightEtlAmplitude.value()
                self.doubleSpinBox_leftEtlAmplitude.setValue(self.parameters["etl_l_amplitude"])
        elif parameterNumber==3:
            self.doubleSpinBox_leftEtlOffset.setMaximum(5-self.doubleSpinBox_leftEtlAmplitude.value()) #To prevent ETL's amplitude + offset being > 5V
            self.parameters["etl_l_offset"]=self.doubleSpinBox_leftEtlOffset.value()
            if self.checkBox_etlsTogether.isChecked() == True:
                self.parameters["etl_r_offset"]=self.doubleSpinBox_leftEtlOffset.value()
                self.doubleSpinBox_rightEtlOffset.setValue(self.parameters["etl_r_offset"])
        elif parameterNumber==4:
            self.doubleSpinBox_rightEtlOffset.setMaximum(5-self.doubleSpinBox_rightEtlAmplitude.value()) #To prevent ETL's amplitude + offset being > 5V
            self.parameters["etl_r_offset"]=self.doubleSpinBox_rightEtlOffset.value()
            if self.checkBox_etlsTogether.isChecked() == True:
                self.parameters["etl_l_offset"]=self.doubleSpinBox_rightEtlOffset.value()
                self.doubleSpinBox_leftEtlOffset.setValue(self.parameters["etl_l_offset"])
        elif parameterNumber==5:
            self.doubleSpinBox_leftGalvoAmplitude.setMaximum(10-self.doubleSpinBox_leftGalvoOffset.value()) #To prevent galvo's amplitude + offset being > 10V
            self.doubleSpinBox_leftGalvoAmplitude.setMinimum(-10-self.doubleSpinBox_leftGalvoOffset.value()) #To prevent galvo's amplitude + offset being < -10V
            self.parameters["galvo_l_amplitude"]=self.doubleSpinBox_leftGalvoAmplitude.value()
            if self.checkBox_galvosTogether.isChecked() == True:
                self.parameters["galvo_r_amplitude"]=self.doubleSpinBox_leftGalvoAmplitude.value()
                self.doubleSpinBox_rightGalvoAmplitude.setValue(self.parameters["galvo_r_amplitude"])
        elif parameterNumber==6:
            self.doubleSpinBox_rightGalvoAmplitude.setMaximum(10-self.doubleSpinBox_rightGalvoOffset.value()) #To prevent galvo's amplitude + offset being > 10V
            self.doubleSpinBox_rightGalvoAmplitude.setMinimum(-10-self.doubleSpinBox_rightGalvoOffset.value()) #To prevent galvo's amplitude + offset being < -10V
            self.parameters["galvo_r_amplitude"]=self.doubleSpinBox_rightGalvoAmplitude.value()
            if self.checkBox_galvosTogether.isChecked() == True:
                self.parameters["galvo_l_amplitude"]=self.doubleSpinBox_rightGalvoAmplitude.value()
                self.doubleSpinBox_leftGalvoAmplitude.setValue(self.parameters["galvo_l_amplitude"])
        elif parameterNumber==7:
            self.doubleSpinBox_leftGalvoOffset.setMaximum(10-self.doubleSpinBox_leftGalvoAmplitude.value()) #To prevent galvo's amplitude + offset being > 10V
            self.doubleSpinBox_leftGalvoOffset.setMinimum(-10-self.doubleSpinBox_leftGalvoAmplitude.value()) #To prevent galvo's amplitude + offset being < -10V
            self.parameters["galvo_l_offset"]=self.doubleSpinBox_leftGalvoOffset.value()
            if self.checkBox_galvosTogether.isChecked() == True:
                self.parameters["galvo_r_offset"]=self.doubleSpinBox_leftGalvoOffset.value()
                self.doubleSpinBox_rightGalvoOffset.setValue(self.parameters["galvo_r_offset"])
        elif parameterNumber==8:
            self.doubleSpinBox_rightGalvoOffset.setMaximum(10-self.doubleSpinBox_rightGalvoAmplitude.value()) #To prevent galvo's amplitude + offset being > 10V
            self.doubleSpinBox_rightGalvoOffset.setMinimum(-10-self.doubleSpinBox_rightGalvoAmplitude.value()) #To prevent galvo's amplitude + offset being < -10V
            self.parameters["galvo_r_offset"]=self.doubleSpinBox_rightGalvoOffset.value()
            if self.checkBox_galvosTogether.isChecked() == True:
                self.parameters["galvo_l_offset"]=self.doubleSpinBox_rightGalvoOffset.value()
                self.doubleSpinBox_leftGalvoOffset.setValue(self.parameters["galvo_l_offset"])
        elif parameterNumber==9:
            self.parameters["galvo_l_frequency"]=self.doubleSpinBox_leftGalvoFrequency.value()
            if self.checkBox_galvosTogether.isChecked() == True:
                self.parameters["galvo_r_frequency"]=self.doubleSpinBox_leftGalvoFrequency.value()
                self.doubleSpinBox_rightGalvoFrequency.setValue(self.parameters["galvo_r_frequency"])
        elif parameterNumber==10:
            self.parameters["galvo_r_frequency"]=self.doubleSpinBox_rightGalvoFrequency.value()
            if self.checkBox_galvosTogether.isChecked() == True:
                self.parameters["galvo_l_frequency"]=self.doubleSpinBox_rightGalvoFrequency.value()
                self.doubleSpinBox_leftGalvoFrequency.setValue(self.parameters["galvo_l_frequency"])
        elif parameterNumber==11:
            self.parameters["samplerate"]=self.doubleSpinBox_samplerate.value()
        elif parameterNumber==12:
            self.parameters["etl_step"]=self.spinBox_etlStep.value()
    
    
    def update_left_laser(self):
        '''Updates left laser voltage after value change by the user'''
        
        self.label_leftLaserVoltage.setText('{} {}'.format(self.horizontalSlider_leftLaser.value()/100, 'V'))
        self.parameters["laser_l_voltage"] = self.horizontalSlider_leftLaser.value()/100 
    
    def update_right_laser(self):
        '''Updates right laser voltage after value change by the user'''
        
        self.label_rightLaserVoltage.setText('{} {}'.format(self.horizontalSlider_rightLaser.value()/100, 'V'))
        self.parameters["laser_r_voltage"] = self.horizontalSlider_rightLaser.value()/100
    
    def activate_both_lasers(self):
        '''Flag and lasers' pushButton managing for both lasers activation'''
        
        self.both_lasers_activated = True
        
        self.pushButton_lasersOn.setEnabled(False)
        self.pushButton_lasersOff.setEnabled(True)
        self.pushButton_leftLaserOn.setEnabled(False)
        self.pushButton_rightLaserOn.setEnabled(False)
        
        print('Lasers on')
        self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Lasers on')
    
    def deactivate_both_lasers(self):
        '''Flag and lasers' pushButton managing for both lasers deactivation'''
        
        self.both_lasers_activated = False
        
        self.pushButton_lasersOn.setEnabled(True)
        self.pushButton_lasersOff.setEnabled(False)
        self.pushButton_leftLaserOn.setEnabled(True)
        self.pushButton_rightLaserOn.setEnabled(True)
        
        print('Lasers off')
        self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Lasers off')  
    
    def activate_left_laser(self):
        '''Flag and lasers' pushButton managing for left laser activation'''
        
        self.left_laser_activated = True
        
        self.pushButton_lasersOn.setEnabled(False)
        self.pushButton_leftLaserOn.setEnabled(False)
        self.pushButton_leftLaserOff.setEnabled(True)
        
        print('Left laser on')
        self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Lasers on') 
    
    def deactivate_left_laser(self):
        '''Flag and lasers' pushButton managing for left laser deactivation'''
        
        self.left_laser_activated = False
         
        self.pushButton_leftLaserOn.setEnabled(True)
        self.pushButton_leftLaserOff.setEnabled(False)
        if self.pushButton_rightLaserOn.isEnabled() == True:
            self.pushButton_lasersOn.setEnabled(True)
        
        print('Left laser off')
        self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Left laser off')
    
    def activate_right_laser(self):
        '''Flag and lasers' pushButton managing for right laser activation'''
        
        self.right_laser_activated = True
        
        self.pushButton_lasersOn.setEnabled(False)
        self.pushButton_rightLaserOn.setEnabled(False)
        self.pushButton_rightLaserOff.setEnabled(True)
        
        print('Left laser on')
        self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Left laser on')
    
    def deactivate_right_laser(self):
        '''Flag and lasers' pushButton managing for right laser deactivation'''
        
        self.right_laser_activated = False
        
        self.pushButton_rightLaserOn.setEnabled(True)
        self.pushButton_rightLaserOff.setEnabled(False)
        if self.pushButton_leftLaserOn.isEnabled() == True:
            self.pushButton_lasersOn.setEnabled(True)
        
        print('Left laser off')
        self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Left laser off')
    
    def start_lasers(self):
        '''Starts the lasers at a certain voltage'''
        
        self.laser_on = True
        
        left_laser_voltage = 0  #Default voltage of 0V
        right_laser_voltage = 0 #Default voltage of 0V
        
        if self.both_lasers_activated == True:
            left_laser_voltage = self.parameters['laser_l_voltage']
            right_laser_voltage = self.parameters['laser_r_voltage']   
        elif self.left_laser_activated == True:
            left_laser_voltage = self.parameters['laser_l_voltage']  
        elif self.right_laser_activated == True:
            right_laser_voltage = self.parameters['laser_r_voltage']
        
        self.lasers_waveforms = np.stack((np.array([right_laser_voltage]),
                                          np.array([left_laser_voltage])))   
        
        '''Writing voltage'''
        self.lasers_task.write(self.lasers_waveforms, auto_start=True)
    
    def stop_lasers(self):
        '''Stops the lasers, puts their voltage to zero'''
        
        self.laser_on = False
        
        '''Writing voltage'''
        waveforms = np.stack(([0],[0]))
        self.lasers_task.write(waveforms)
        
        '''Ending task'''
        self.lasers_task.stop()
        self.lasers_task.close()
 
 
    '''Acquisition Modes Methods'''
    
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
    
    
    def start_standby(self):
        '''Closes the camera and initiates thread to keep ETLs'currents at 0A while
           the microscope is not in use'''
        
        self.standby = True
        
        '''Flags check up'''
        if self.preview_mode_started == True:
            self.stop_preview_mode()
        if self.live_mode_started == True:
            self.stop_live_mode()
        if self.stack_mode_started == True:
            self.stop_stack_mode()
        
        '''Close camera'''
        self.close_camera()
        
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
        
        print('Standby on')
        self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Standby on')
        
        '''Start standby thread'''
        standby_thread = threading.Thread(target = self.standby_thread)
        standby_thread.start()
    
    def standby_thread(self):
        '''Repeatedly sends 2.5V to the ETLs to keep their currents at 0A'''
        
        '''Create ETL standby task'''
        standby_task = nidaqmx.Task()
        standby_task.ao_channels.add_ao_voltage_chan('/Dev1/ao2:3')
        
        etl_voltage = 2.5 #In volts
        standby_waveform = np.stack((np.array([etl_voltage]),np.array([etl_voltage])))
        
        '''Inject voltage'''
        while self.standby:
            standby_task.write(standby_waveform, auto_start = True)
            time.sleep(5) #In seconds
        
        '''Close task'''
        standby_task.stop()
        standby_task.close()
        
        '''Open camera'''
        self.open_camera()
        
        '''Modes enabling after standby'''
        self.pushButton_getSingleImage.setEnabled(True)
        self.pushButton_startStack.setEnabled(True)
        self.pushButton_startLiveMode.setEnabled(True)
        self.pushButton_startPreviewMode.setEnabled(True)
        self.pushButton_standbyOn.setEnabled(True)
        self.pushButton_standbyOff.setEnabled(False)
        
        print('Standby off')
        self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Standby off')
    
    def stop_standby(self):
        '''Changes the standby flag status to end the thread'''
        
        self.standby = False
    
    
    def start_preview_mode(self):
        '''Initializes variables for preview modes where beam and focal 
           positions are manually controlled by the user'''
        
        self.preview_mode_started = True
        
        '''Flags check up'''
        if self.standby == True:
            self.stop_standby()
        if self.live_mode_started == True:
            self.stop_live_mode()
        if self.stack_mode_started == True:
            self.stop_stack_mode()
        
        '''Modes disabling during preview_mode execution'''
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
        
        print('Preview mode started')
        self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Preview mode started')
        
        '''Starting preview mode thread'''
        preview_mode_thread = threading.Thread(target = self.preview_mode_thread)
        preview_mode_thread.start()
    
    def preview_mode_thread(self):
        '''This thread allows the visualization and manual control of the 
           parameters of the beams in the UI. There is no scan here, 
           beams only changes when parameters are changed. This the preferred 
           mode for beam calibration'''
        
        '''Setting the camera for acquisition'''
        self.camera.set_trigger_mode('AutoSequence')
        self.camera.arm_camera() 
        self.camera.get_sizes() 
        self.camera.allocate_buffer()    
        self.camera.set_recording_state(1)
        self.camera.insert_buffers_in_queue()
        
        '''Setting tasks'''
        self.lasers_task = nidaqmx.Task()
        self.lasers_task.ao_channels.add_ao_voltage_chan(terminals["lasers"])
        
        self.preview_galvos_etls_task = nidaqmx.Task()
        self.preview_galvos_etls_task.ao_channels.add_ao_voltage_chan(terminals["galvos_etls"])
        
        for i in range(0, len(self.consumers), 4):
            if self.consumers[i+2] == "CameraWindow":
                while self.preview_mode_started:
                    
                    '''Starting lasers'''
                    self.start_lasers()
                    
                    '''Setting data values'''
                    left_galvo_voltage = self.parameters['galvo_l_amplitude'] + self.parameters['galvo_l_offset']
                    right_galvo_voltage = self.parameters['galvo_r_amplitude'] + self.parameters['galvo_r_offset']
                    left_etl_voltage = self.parameters['etl_l_amplitude'] + self.parameters['etl_l_offset']
                    right_etl_voltage = self.parameters['etl_r_amplitude'] + self.parameters['etl_r_offset']
                                
                    '''Setting waveforms'''
                    preview_galvos_etls_waveforms = np.stack((np.array([right_galvo_voltage]),
                                                              np.array([left_galvo_voltage]),
                                                              np.array([right_etl_voltage]),
                                                              np.array([left_etl_voltage])))
                    
                    '''Writing the data'''
                    self.preview_galvos_etls_task.write(preview_galvos_etls_waveforms, auto_start=True)
                    
                    '''Retrieving image from camera and putting it in its queue
                       for display'''
                    frame = self.camera.retrieve_single_image()*1.0
                    try:
                        self.consumers[i].put(frame)
                    except self.consumers[i].Full:
                        print("Queue is full")
                        self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Queue is full')
                    
                    ###max_value = np.max(frame.flatten())
                    ###if max_value >= 65000:
                    ###    print('Saturation')
        
        '''Stopping camera'''
        self.camera.cancel_images()
        self.camera.set_recording_state(0)
        self.camera.free_buffer()
        
        '''End tasks'''
        self.preview_galvos_etls_task.stop()
        self.preview_galvos_etls_task.close()
        
        '''Stopping lasers'''
        self.stop_lasers()
        
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
    
    def stop_preview_mode(self):
        '''Changes the preview_mode flag status to end the thread'''
        
        self.preview_mode_started = False
    
    
    def start_live_mode(self):
        '''This mode is for visualizing (and modifying) the effects of the 
           chosen parameters of the ramps which will be sent for single image 
           saving or volume saving (with stack_mode)'''
        
        self.live_mode_started = True
        
        '''Flags check up'''
        if self.standby == True:
            self.stop_standby()
        if self.preview_mode_started == True:
            self.stop_preview_mode()
        if self.stack_mode_started == True:
            self.stop_stack_mode()
        
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
        
        print('Live mode started')
        self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Live mode started')
        
        '''Starting live mode thread'''
        live_mode_thread = threading.Thread(target = self.live_mode_thread)
        live_mode_thread.start()
    
    def live_mode_thread(self):
        '''This thread allows the execution of live_mode while modifying
           parameters in the UI'''
        
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
        
        for i in range(0, len(self.consumers), 4):
            if self.consumers[i+2] == "CameraWindow":
                while self.live_mode_started:
                        
                    '''Starting lasers'''
                    self.start_lasers()
                    
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
                        
                    '''Retrieving buffer'''
                    self.number_of_steps = np.ceil(self.parameters["columns"]/self.parameters["etl_step"]) #Number of galvo sweeps in a frame, or alternatively the number of ETL focal step
                    buffer = self.camera.retrieve_multiple_images(self.number_of_steps, self.ramps.t_half_period, sleep_timeout = 5)
                    
                    '''Frame reconstruction for display'''
                    frame = np.zeros((int(self.parameters["rows"]), int(self.parameters["columns"])))  #Initializing frame
                    
                    #For each column step
                    for i in range(int(self.number_of_steps)-1):
                        current_step = int(i*self.parameters['etl_step'])
                        next_step = int(i*self.parameters['etl_step']+self.parameters['etl_step'])
                        frame[:,current_step:next_step] = buffer[i,:,current_step:next_step]
                    #For the last column step (may be different than the others...)
                    last_step = int(int(self.number_of_steps-1) * self.parameters['etl_step'])
                    frame[:,last_step:] = buffer[int(self.number_of_steps-1),:,last_step:]
                       
                    '''Frame display'''
                    for i in range(0, len(self.consumers), 4):
                        if self.consumers[i+2] == "CameraWindow":
                            try:
                                self.consumers[i].put(frame)
                            except:      #self.consumers[i].Full:
                                print("Queue is full")
                                self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Queue is full')     
                    
                    '''End tasks'''
                    self.ramps.stop_tasks()                             
                    self.ramps.close_tasks()
        
        '''Stopping camera'''
        self.camera.cancel_images()
        self.camera.set_recording_state(0)
        self.camera.free_buffer()
        
        '''Stopping lasers'''
        self.stop_lasers()
        
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

    def stop_live_mode(self):
        '''Changes the live_mode flag status to end the thread'''
        
        self.live_mode_started = False
    
    
    def get_single_image(self):
        '''Generates and display a single frame which can be saved afterwards 
        using self.save_single_image()'''
        
        '''Flags check up'''
        if self.standby == True:
            self.stop_standby()
        if self.preview_mode_started == True:
            self.stop_preview_mode()
        if self.live_mode_started == True:
            self.stop_live_mode()
        if self.stack_mode_started == True:
            self.stop_stack_mode()
            
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
        
        '''Setting the camera for acquisition'''
        self.camera.set_trigger_mode('ExternalExposureControl')
        self.camera.arm_camera() 
        self.camera.get_sizes() 
        self.camera.allocate_buffer()    
        self.camera.set_recording_state(1)
        self.camera.insert_buffers_in_queue()
        
        '''Creating laser tasks'''
        self.lasers_task = nidaqmx.Task()
        self.lasers_task.ao_channels.add_ao_voltage_chan(terminals["lasers"])
        
        '''Starting lasers'''
        self.both_lasers_activated = True
        self.start_lasers()
                        
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
        
        
        '''Retrieving buffer'''
        self.number_of_steps = np.ceil(self.parameters["columns"]/self.parameters["etl_step"]) #Number of galvo sweeps in a frame, or alternatively the number of ETL focal step
        self.buffer = self.camera.retrieve_multiple_images(self.number_of_steps, self.ramps.t_half_period, sleep_timeout = 5)
        
        '''Frame reconstruction for display'''
        frame = np.zeros((int(self.parameters["rows"]), int(self.parameters["columns"])))  #Initializing frame
        
        #For each column step
        for i in range(int(self.number_of_steps)-1):
            current_step = int(i*self.parameters['etl_step'])
            next_step = int(i*self.parameters['etl_step']+self.parameters['etl_step'])
            frame[:,current_step:next_step] = self.buffer[i,:,current_step:next_step]
        #For the last column step (may be different than the others...)
        last_step = int(int(self.number_of_steps-1) * self.parameters['etl_step'])
        frame[:,last_step:] = self.buffer[int(self.number_of_steps-1),:,last_step:]
        
        '''Frame display'''
        for i in range(0, len(self.consumers), 4):
            if self.consumers[i+2] == "CameraWindow":
                try:
                    self.consumers[i].put(frame)
                except:      #self.consumers[i].Full:
                    print("Queue is full")   
                    self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Queue is full') 
        
        '''Stopping lasers'''
        self.stop_lasers()
        self.both_lasers_activated = False   
        
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
    
    def save_single_image(self):
        '''Saves the frame generated by self.get_single_image()'''
        
        '''Retrieving filename set by the user'''
        self.filename = str(self.lineEdit_filename.text())
        
        '''Removing spaces, dots and commas''' ###???
        #self.filename = self.filename.replace(' ', '')
        #self.filename = self.filename.replace('.', '')
        #self.filename = self.filename.replace(',', '')
        
        if self.saving_allowed and self.filename != '':
            
            self.filename = self.save_directory + '/' + self.filename
            
            '''Setting frame saver'''
            self.frame_saver = FrameSaver(self.filename)
            self.frame_saver.set_block_size(1) #Block size is a number of buffers
            self.frame_saver.check_existing_files(self.filename, 1, 'singleImage')
            
            '''We can add attributes here (none implemented yet)'''###???
            
            '''Saving frame'''
            self.frame_saver.put(self.buffer,1)
            self.frame_saver.start_saving(data_type = 'BUFFER')
            self.frame_saver.stop_saving()
            
            print('Image saved')
            self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Image saved')
            
        else:
            print('Select directory and enter a valid filename before saving')
            self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Select directory and enter a valid filename before saving')
    
    
    def set_number_of_planes(self):
        '''Calculates the number of planes that will be saved in the stack 
           acquisition'''
        
        if self.doubleSpinBox_planeStep.value() != 0:
            if (self.checkBox_setStartPoint.isChecked() == True) and (self.checkBox_setEndPoint.isChecked() == True):
                self.number_of_planes = np.ceil(abs((self.stack_mode_ending_point-self.stack_mode_starting_point)/self.doubleSpinBox_planeStep.value()))
                self.number_of_planes +=1   #Takes into account the initial plane
                self.label_numberOfPlanes.setText(str(self.number_of_planes))
        else:
            print('Set a non-zero value to plane step')
            self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Set a non-zero value to plane step')
        
    def set_stack_mode_ending_point(self):
        '''Defines the ending point of the recorded stack volume'''
        
        self.stack_mode_ending_point = self.motor_horizontal.current_position('\u03BCm') #Units in micro-meters, because plane step is in micro-meters
        self.checkBox_setEndPoint.setChecked(True)
        self.set_number_of_planes()
        
    def set_stack_mode_starting_point(self):
        '''Defines the starting point where the first plane of the stack volume
           will be recorded'''
        
        self.stack_mode_starting_point = self.motor_horizontal.current_position('\u03BCm') #Units in micro-meters, because plane step is in micro-meters
        self.checkBox_setStartPoint.setChecked(True)
        self.set_number_of_planes()
    
    def start_stack_mode(self):
        '''Initializes variables for volume saving which will take place in 
           self.stack_mode_thread afterwards'''
        
        '''Flags check up'''
        if self.standby == True:
            self.stop_standby()
        if self.preview_mode_started == True:
            self.stop_preview_mode()
        if self.live_mode_started == True:
            self.stop_live_mode()
        
        '''Retrieving filename set by the user'''       
        self.filename = str(self.lineEdit_filename.text())
         
        '''Removing spaces, dots and commas''' ###???
            #self.filename = self.filename.replace(' ', '')
            #self.filename = self.filename.replace('.', '')
            #self.filename = self.filename.replace(',', '')
        
        '''Making sure the limits of the volume are set, saving is allowed and 
           filename isn't empty'''
        if (self.checkBox_setStartPoint.isChecked() == False) or (self.checkBox_setEndPoint.isChecked() == False) or (self.doubleSpinBox_planeStep.value() == 0):
            print('Set starting and ending points and select a non-zero plane step value')
            self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Set starting and ending points and select a non-zero plane step value')
        elif (self.saving_allowed == False) or (self.filename == ''):
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
            
            print('Stack mode started -- Number of frames to save: '+str(self.number_of_planes))
            self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Stack mode started -- Number of frames to save: '+str(self.number_of_planes))
            
            '''Starting stack mode thread'''
            stack_mode_thread = threading.Thread(target = self.stack_mode_thread)
            stack_mode_thread.start()
    
    def stack_mode_thread(self):
        ''' Thread for volume acquisition and saving 
        
        Note: check if there's a NI-Daqmx function to repeat the data sent 
              instead of closing each time the task. This would be useful
              if it is possible to break a task with self.stop_stack_mode
        Simpler solution: Use conditions with self._stack_mode_started status 
                          such as in self.live_mode_thread() and 
                          self.preview_mode_thread()
        
        A progress bar would be nice
        '''
        
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
        
        '''We can add attributes here (none implemented yet)'''###???
        
        self.set_data_consumer(self.frame_saver, False, "FrameSaver", True)
        self.frame_saver.start_saving(data_type = 'BUFFER')
        
        print(self.frame_saver.filenames_list)
        
        '''Creating lasers task'''
        self.lasers_task = nidaqmx.Task()
        self.lasers_task.ao_channels.add_ao_voltage_chan(terminals["lasers"])
        
        '''Starting lasers'''
        self.start_lasers()
        
        '''Creating ETLs, galvos & camera's ramps and waveforms'''
        self.ramps=AOETLGalvos(self.parameters)
        self.ramps.initialize()                   
        self.ramps.create_etl_waveforms(case = 'STAIRS')
        self.ramps.create_galvos_waveforms(case = 'TRAPEZE')
        self.ramps.create_digital_output_camera_waveform( case = 'STAIRS_FITTING')
        
        '''Set progress bar'''
        progress_value = 0
        progress_increment = 100 // int(self.number_of_planes)
        
        for i in range(int(self.number_of_planes)):
            
            if self.stack_mode_started == False:
                print('Acquisition Interrupted')
                self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Acquisition Interrupted')
                
                break
            else:
                '''Moving sample position'''
                position = self.start_point+i*self.step
                self.motor_horizontal.move_absolute_position(position,'\u03BCm')  #Position in micro-meters
                
                '''Moving the camera to focus'''
                ###self.calculate_camera_focus()
                self.move_camera_to_focus()               
                
                '''Acquiring the frame '''
                self.ramps.create_tasks(terminals,'FINITE')
                self.ramps.write_waveforms_to_tasks()                            
                self.ramps.start_tasks()
                self.ramps.run_tasks()
                
                '''Retrieving buffer'''
                self.number_of_steps = np.ceil(self.parameters["columns"]/self.parameters["etl_step"]) #Number of galvo sweeps in a frame, or alternatively the number of ETL focal step
                self.buffer = self.camera.retrieve_multiple_images(self.number_of_steps, self.ramps.t_half_period, sleep_timeout = 5)
                
                '''Frame reconstruction for display'''
                frame = np.zeros((int(self.parameters["rows"]), int(self.parameters["columns"])))  #Initializing frame
                
                #For each column step
                for i in range(int(self.number_of_steps)-1):
                    current_step = int(i*self.parameters['etl_step'])
                    next_step = int(i*self.parameters['etl_step']+self.parameters['etl_step'])
                    frame[:,current_step:next_step] = self.buffer[i,:,current_step:next_step]
                #For the last column step (may be different than the others...)
                last_step = int(int(self.number_of_steps-1) * self.parameters['etl_step'])
                frame[:,last_step:] = self.buffer[int(self.number_of_steps-1),:,last_step:]
                
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
                            self.consumers[ii].put(self.buffer,1)
                            print('Frame put in FrameSaver')
                            self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Frame put in FrameSaver')
                        except:      #self.consumers[ii].Full:
                            print("FrameSaver queue is full")
                            self.label_lastCommands.setText(self.label_lastCommands.text()+'\n FrameSaver queue is full')
                
                '''Ending tasks'''
                self.ramps.stop_tasks()                             
                self.ramps.close_tasks()
                
                '''Update progress bar'''
                progress_value += progress_increment
                self.progressBar_stackMode.setValue(progress_value) ###Corriger QObject::setParent: Cannot set parent, new parent is in a different thread
            
            self.update_position_horizontal()
            
        self.laser_on = False
        
        '''Stopping camera'''
        self.camera.cancel_images()
        self.camera.set_recording_state(0)
        self.camera.free_buffer()
        
        self.frame_saver.stop_saving()
                
        '''Stopping laser'''
        self.stop_lasers()
        
        '''Enabling modes after stack mode'''
        self.pushButton_getSingleImage.setEnabled(True)
        self.pushButton_startLiveMode.setEnabled(True)
        self.pushButton_startStack.setEnabled(True)
        self.pushButton_stopStack.setEnabled(False)
        self.pushButton_startPreviewMode.setEnabled(True)
        self.pushButton_standbyOn.setEnabled(True)
        self.pushButton_calibrateCamera.setEnabled(True)
        
        print('Acquisition done')
        self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Acquisition done')
    
    def stop_stack_mode(self):
        '''Changes the live_mode flag status to end the thread'''
        ###Note: check how to break a NI-Daqmx task...
        
        self.stack_mode_started = False
    
    
    '''Calibration Methods'''
    
    def start_calibrate_camera(self):
        '''Initiates camera calibration'''
        
        self.camera_calibration_started = True
        
        '''Flags check up'''
        if self.standby == True:
            self.stop_standby()
        if self.preview_mode_started == True:
            self.stop_preview_mode()
        if self.live_mode_started == True:
            self.stop_live_mode()
        if self.stack_mode_started == True:
            self.stop_stack_mode()
       
       
       
        '''Retrieving filename set by the user'''       
        self.filename = str(self.lineEdit_filename.text())
         
        '''Removing spaces, dots and commas''' ###???
        #self.filename = self.filename.replace(' ', '')
        #self.filename = self.filename.replace('.', '')
        #self.filename = self.filename.replace(',', '')
       
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
        self.pushButton_standbyOff.setEnabled(False)
        self.pushButton_calibrateCamera.setEnabled(False)
        self.pushButton_cancelCalibrateCamera.setEnabled(True)
            
            
            
            
            
        print('Camera calibration started')
        self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Camera calibration started')
            
        '''Starting camera calibration thread'''
        calibrate_camera_thread = threading.Thread(target = self.calibrate_camera_thread)
        calibrate_camera_thread.start()
    
    def calibrate_camera_thread(self):
        ''' Calibrates the camera focus by finding the ideal camera position 
            for multiple sample horizontal positions'''
        
        '''Verifying boundaries selection'''
        if (self.horizontal_forward_boundary_selected == False) or (self.horizontal_backward_boundary_selected == False):
            print('Select horizontal boundaries before calibrating camera')
            self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Select horizontal boundaries before calibrating camera')
        else:
            ''' Prepare saving (if we lose planes while saving, add more buffers 
            to block size, but make sure they don't take all the RAM'''
            self.filename = self.save_directory + '/' + self.filename
            self.frame_saver = FrameSaver(self.filename)
            self.frame_saver.set_block_size(3)  #3 buffers allowed in the queue
            self.number_of_planes = 1###
            self.frame_saver.check_existing_files(self.filename, self.number_of_planes, 'stack')
            
            '''We can add attributes here (none implemented yet)'''###???
            
            self.set_data_consumer(self.frame_saver, False, "FrameSaver", True)
            self.frame_saver.start_saving(data_type = 'BUFFER')
            
            print(self.frame_saver.filenames_list)
        
        
            
            '''Setting the camera for acquisition'''
            self.camera.set_trigger_mode('AutoSequence')
            self.camera.arm_camera() 
            self.camera.get_sizes() 
            self.camera.allocate_buffer()    
            self.camera.set_recording_state(1)
            self.camera.insert_buffers_in_queue()
            
            '''Setting tasks'''
            self.lasers_task = nidaqmx.Task()
            self.lasers_task.ao_channels.add_ao_voltage_chan(terminals["lasers"])
            
            self.preview_galvos_etls_task = nidaqmx.Task()
            self.preview_galvos_etls_task.ao_channels.add_ao_voltage_chan(terminals["galvos_etls"])
            
            '''Getting the data to send to the AO'''
            left_galvo_voltage = self.parameters['galvo_l_amplitude']+self.parameters['galvo_l_offset']
            right_galvo_voltage = self.parameters['galvo_r_amplitude']+self.parameters['galvo_r_offset']
            
            left_etl_voltage = self.parameters['etl_l_amplitude']+self.parameters['etl_l_offset']
            right_etl_voltage = self.parameters['etl_r_amplitude']+self.parameters['etl_r_offset']
                        
            '''Writing the data'''
            preview_galvos_etls_waveforms = np.stack((np.array([right_galvo_voltage]),
                                                      np.array([left_galvo_voltage]),
                                                      np.array([right_etl_voltage]),
                                                      np.array([left_etl_voltage])))
            self.preview_galvos_etls_task.write(preview_galvos_etls_waveforms, auto_start=True)
            
            '''Starting lasers'''
            self.both_lasers_activated = True   #Automatically activate lasers
            self.start_lasers()
            
            '''Getting calibration parameters'''
            if self.doubleSpinBox_numberOfCalibrationPlanes.value() != 0:
                self.number_of_calibration_planes = self.doubleSpinBox_numberOfCalibrationPlanes.value()
            if self.doubleSpinBox_numberOfCameraPositions.value() != 0:
                self.number_of_camera_positions = self.doubleSpinBox_numberOfCameraPositions.value()
            
            sample_increment_length = (self.horizontal_forward_boundary - self.horizontal_backward_boundary) / self.number_of_calibration_planes
            focus_backward_boundary = 260000 #263000      ###Arbitraire
            focus_forward_boundary = 270000  #269000   ###Arbitraire
            camera_increment_length = (focus_forward_boundary - focus_backward_boundary) / self.number_of_camera_positions
            
            position_depart_sample = self.motor_horizontal.current_position('\u03BCStep')
            position_depart_camera = self.focus
            
            self.camera_focus_relation = np.zeros((int(self.number_of_calibration_planes),2))
            self.averages = np.zeros((int(self.number_of_camera_positions),2)) #debugging
            self.variances = np.zeros((int(self.number_of_camera_positions),2)) #debugging
            
            for i in range(int(self.number_of_calibration_planes) + 1): #The first camera acquisition is noise and is not considered for calibration... ###Pourquoi?
                
                if self.camera_calibration_started == False:
                    print('Camera calibration interrupted')
                    self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Camera calibration interrupted')
                    
                    break
                else:
                    '''Moving sample position'''
                    position = self.horizontal_forward_boundary - (i * sample_increment_length)    #Increments of +sample_increment_length
                    self.motor_horizontal.move_absolute_position(position,'\u03BCStep')
                    self.update_position_horizontal()
                    #print('Sample moved to:'+str(position)+'---mesured:'+str(-self.motor_horizontal.current_position(self.unit)+self.horizontal_correction)) #debugging
                    
                    average_intensities = np.zeros(int(self.number_of_camera_positions))
                    variance = np.zeros(int(self.number_of_camera_positions))
                    self.cam_positions = np.zeros(int(self.number_of_camera_positions)) #debugging
                    
                    for j in range(int(self.number_of_camera_positions)):
                        '''Moving camera position'''
                        position_camera = focus_forward_boundary - (j * camera_increment_length) #Increments of +camera_increment_length
                        self.motor_camera.move_absolute_position(position_camera,'\u03BCStep')
                        self.update_position_camera()
                        #print('Camera moved to:'+str(position_camera)+'---mesured:'+str(-self.motor_camera.current_position(self.unit)+self.camera_correction)) #debugging
                        
                        '''Retrieving buffer for the plane of the current position'''
                        self.buffer = self.camera.retrieve_single_image()*1.0
                        
                        
                        '''buffer saving'''
                        for ii in range(0, len(self.consumers), 4):
                            if self.consumers[ii+2] == 'FrameSaver':
                                try:
                                    self.consumers[ii].put(self.buffer,1)
                                    print('Frame put in FrameSaver')
                                    self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Frame put in FrameSaver')
                                except:      #self.consumers[ii].Full:
                                    print("FrameSaver queue is full")
                                    self.label_lastCommands.setText(self.label_lastCommands.text()+'\n FrameSaver queue is full')
                        
                        #self.save_single_image()
                        
                        
                        
                        self.buffer = self.buffer[1100:1300,600:800] ###cible point
                        '''Calculating ideal camera position (with most intense pixels)'''
                        intensities = np.sort(self.buffer, axis=None)
                        average_intensities[j] = np.average(intensities[-10:]) #25 max intensities considered
                        variance[j] = np.var(intensities)
                        
                        self.cam_positions[j] = -self.motor_camera.current_position(self.unit)+self.camera_correction #debugging
                        if i == 1: #debugging
                            self.averages[j,0] = average_intensities[j]
                            self.variances[j,0] = variance[j]
                            
                        if i == int(self.number_of_camera_positions):
                            self.variances[j,1] = variance[j]
                        
                    print('averages:') #debugging
                    print(average_intensities) #debugging
                    
                    '''Saving focus relation'''
                    if i!=0: ###Exclusion du premier cas qui donne du bruit...
                        
                        
                        
                        self.camera_focus_relation[i-1,0] = -self.motor_horizontal.current_position(self.unit) + self.horizontal_correction
                        
                        #Méthode des moyennes
                        #max_intensity_camera_position = focus_forward_boundary - (np.argmax(average_intensities) * camera_increment_length)
                        #self.camera_focus_relation[i-1,1] = -self.motor_camera.data_to_position(max_intensity_camera_position, self.unit) + self.camera_correction
                        
                        #Méthode des variances
                        max_variance_camera_position = focus_forward_boundary - (np.argmax(variance) * camera_increment_length)
                        self.camera_focus_relation[i-1,1] = -self.motor_camera.data_to_position(max_variance_camera_position, self.unit) + self.camera_correction
                        
                        
                print('Plan '+str(i)+' done') #debugging
            
            print('relation:') #debugging
            print(self.camera_focus_relation)
            
            
            self.frame_saver.stop_saving()
            
            
            '''Returning sample and camera at initial positions'''
            self.motor_horizontal.move_absolute_position(position_depart_sample,'\u03BCStep')
            self.update_position_horizontal()
            self.motor_camera.move_absolute_position(position_depart_camera,'\u03BCStep')
            self.update_position_camera()
            
            '''Stopping camera'''
            self.camera.cancel_images()
            self.camera.set_recording_state(0)
            self.camera.free_buffer()
            
            '''Ending tasks'''
            self.preview_galvos_etls_task.stop()
            self.preview_galvos_etls_task.close()
            
            '''Stopping lasers'''
            self.stop_lasers()
            self.both_lasers_activated = False
            
            '''Calculating focus'''
            if self.camera_calibration_started == True:
                self.calculate_camera_focus()
            
            print('Camera calibration done')
            self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Camera calibration done')
            
        '''Enabling modes after camera calibration'''
        self.pushButton_getSingleImage.setEnabled(True)
        self.pushButton_startStack.setEnabled(True)
        self.pushButton_startLiveMode.setEnabled(True)
        self.pushButton_startPreviewMode.setEnabled(True)
        self.pushButton_calibrateCamera.setEnabled(True)
        self.pushButton_standbyOn.setEnabled(True)
        self.pushButton_cancelCalibrateCamera.setEnabled(False)
        self.pushButton_calculateFocus.setEnabled(True)
        self.pushButton_showInterpolation.setEnabled(True)
            
        self.camera_calibration_started = False

    def stop_calibrate_camera(self):
        '''Interrups camera calibration'''
        
        self.camera_calibration_started = False

    ###
    def start_calibrate_etls_galvos(self):
        '''Initiates etls-galvos calibration'''
        
        self.etls_galvos_calibration_started = True
        
        '''Flags check up'''
        if self.standby == True:
            self.stop_standby()
        if self.preview_mode_started == True:
            self.stop_preview_mode()
        if self.live_mode_started == True:
            self.stop_live_mode()
        if self.stack_mode_started == True:
            self.stop_stack_mode()
        ###ajouter autres flags de calibration
       
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
        self.pushButton_standbyOff.setEnabled(False)
        self.pushButton_calibrateCamera.setEnabled(False)
        self.pushButton_cancelCalibrateCamera.setEnabled(True)
        
        print('Camera calibration started')
        self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Camera calibration started')
        
        '''Starting camera calibration thread'''
        calibrate_etls_galvos_thread = threading.Thread(target = self.calibrate_etls_galvos_thread)
        calibrate_etls_galvos_thread.start()
    
    def calibrate_etls_galvos_thread(self):
        ''' Calibrates the focal position relation with etls-galvos voltage'''
        
        '''Setting the camera for acquisition'''
        self.camera.set_trigger_mode('AutoSequence')
        self.camera.arm_camera() 
        self.camera.get_sizes() 
        self.camera.allocate_buffer()    
        self.camera.set_recording_state(1)
        self.camera.insert_buffers_in_queue()
        
        '''Setting tasks'''
        self.lasers_task = nidaqmx.Task()
        self.lasers_task.ao_channels.add_ao_voltage_chan(terminals["lasers"])
        
        self.preview_galvos_etls_task = nidaqmx.Task()
        self.preview_galvos_etls_task.ao_channels.add_ao_voltage_chan(terminals["galvos_etls"])
        
        '''Starting lasers'''
        self.both_lasers_activated = True   #Automatically activate lasers
        self.start_lasers()
        
        '''Getting parameters'''
        self.number_of_galvos_points = 10
        self.number_of_etls_points = 10
        
        etl_max_voltage = 3.5      #Volts ###Arbitraire
        etl_min_voltage = -3        #Volts ###Arbitraire
        galvo_increment_length = (etl_max_voltage - etl_min_voltage) / self.number_of_galvos_points
            
        self.galvos_relation = np.zeros((int(self.number_of_galvos_points),2))
        
        '''Finding relation between galvos' voltage and focal point vertical's position'''
        for i in ['galvo_l','galvo_r']: #For each galvo
            for j in range(int(self.number_of_galvos_points)):
                
                if self.etls_galvos_calibration_started == False:
                    print('Calibration interrupted')
                    self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Calibration interrupted')
                    
                    break
                else:
                    '''Getting the data to send to the AO'''
                    if i == 'galvo_l':
                        left_galvo_voltage = etl_min_voltage + (j * galvo_increment_length)
                        right_galvo_voltage = self.parameters['galvo_r_amplitude']+self.parameters['galvo_r_offset']
                    
                    if i == 'galvo_r':
                        right_galvo_voltage = etl_min_voltage + (j * galvo_increment_length)
                        left_galvo_voltage = self.parameters['galvo_r_amplitude']+self.parameters['galvo_r_offset']
                        
                    left_etl_voltage = self.parameters['etl_l_amplitude']+self.parameters['etl_l_offset']
                    right_etl_voltage = self.parameters['etl_r_amplitude']+self.parameters['etl_r_offset']
                        
                    '''Writing the data'''
                    preview_galvos_etls_waveforms = np.stack((np.array([right_galvo_voltage]),
                                                              np.array([left_galvo_voltage]),
                                                              np.array([right_etl_voltage]),
                                                              np.array([left_etl_voltage])))
                    self.preview_galvos_etls_task.write(preview_galvos_etls_waveforms, auto_start=True)
                   
                    '''Retrieving buffer for the plane of the current position'''
                    buffer = self.camera.retrieve_single_image()*1.0
                    
                    '''Calculating focal point vertical position'''
                    ###À faire
        
        '''Stopping camera'''
        self.camera.cancel_images()
        self.camera.set_recording_state(0)
        self.camera.free_buffer()
        
        '''Ending tasks'''
        self.preview_galvos_etls_task.stop()
        self.preview_galvos_etls_task.close()
        
        '''Stopping lasers'''
        self.stop_lasers()
        self.both_lasers_activated = False
        
        print('Calibration done')
        self.label_lastCommands.setText(self.label_lastCommands.text()+'\n Calibration done')
            
        '''Enabling modes after camera calibration'''
        self.pushButton_getSingleImage.setEnabled(True)
        self.pushButton_startStack.setEnabled(True)
        self.pushButton_startLiveMode.setEnabled(True)
        self.pushButton_startPreviewMode.setEnabled(True)
        self.pushButton_calibrateCamera.setEnabled(True)
        self.pushButton_standbyOn.setEnabled(True)
        self.pushButton_cancelCalibrateCamera.setEnabled(False)
        self.pushButton_calculateFocus.setEnabled(True)
        self.pushButton_showInterpolation.setEnabled(True)
            
        self.etls_galvos_calibration_started = False

    def stop_calibrate_etls_galvos(self):
        '''Interrups elts-galvos calibration'''
        
        self.etls_galvos_calibration_started = False

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
        
        #position = [0.0, 0.25, 0.5, 0.75, 1.0] ###test chaud-froid
        #colors = [[0, 0, 0], [0, 0, 255], [255, 0, 0], [242, 125, 0], [253, 207, 88]]###test chaud-froid
        position = [0.0, 0.99999999, 1.0] ###ajuster valeur centrale
        colors = [[0, 0, 0], [255, 255, 255], [255, 0, 0]]
        bi_polar_color_map = pg.ColorMap(position, colors)
        self.imv.setColorMap(bi_polar_color_map)
        
    def put(self, item, block=True, timeout=None): ###nécessaire?
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
            
            if not first_update: #To keep the histogram setting with image refresh
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

def save_process(queue, filenames_list, path_root, block_size, conn):    ###enlever
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