'''
Created on May 22, 2019

@authors: Pierre Girard-Collins & flesage
'''

import sys
#from numpy import linspace
sys.path.append("..")

import os
import math
import numpy as np
from matplotlib import pyplot as plt
from scipy import interpolate, signal, optimize, ndimage, stats
from PyQt5 import QtGui, QtCore
from PyQt5 import uic
from PyQt5.QtWidgets import QWidget, QFileDialog, QTableWidgetItem,QAbstractItemView
#from PyQt5.QtWidgets import QApplication, QMainWindow, QMenu, QVBoxLayout, QSizePolicy, QMessageBox, QPushButton
#from PyQt5.QtGui import QIcon
#from PyQt5.QtCore import QThread

import pyqtgraph as pg
#import ctypes
import copy

import nidaqmx
#from nidaqmx.constants import AcquisitionType

#import src.config
from src.hardware import AOETLGalvos
from src.hardware import Motors
from src.pcoEdge import Camera
#from zaber.serial import AsciiSerial, AsciiDevice, AsciiCommand
import threading
import time
import queue
import multiprocessing
import h5py
import posixpath
import datetime

parameters = dict()
modifiable_parameters = list(["etl_l_amplitude","etl_r_amplitude",
    "etl_l_offset","etl_r_offset","galvo_l_amplitude","galvo_r_amplitude",
    "galvo_l_offset","galvo_r_offset","galvo_l_frequency","galvo_r_frequency",
    "samplerate"])

'''Read modifiable parameters from configuration file'''
with open(r"C:\git-projects\lightsheet\src\configuration.txt") as file:
    for param_string in modifiable_parameters:
        parameters[param_string] = float(file.readline())

'''Default parameters'''
parameters["sample_name"]='No Sample Name'
parameters["samplerate"]=40000          # In samples/seconds
parameters["galvo_l_frequency"]=100     # In Hertz
parameters["galvo_l_amplitude"]=6.5 #2       # In Volts
parameters["galvo_l_offset"]=-3         # In Volts
parameters["galvo_r_frequency"]=100     # In Hertz
parameters["galvo_r_amplitude"]=6.5 #2       # In Volts
parameters["galvo_r_offset"]=-2.9         # In Volts
parameters["etl_l_amplitude"]=2         # In Volts
parameters["etl_l_offset"]=0            # In Volts
parameters["etl_r_amplitude"]=2         # In Volts
parameters["etl_r_offset"]=0            # In Volts
parameters["laser_l_voltage"]=0.905#1.3      # In Volts
parameters["laser_r_voltage"]=0.935     # In Volts

parameters["sweeptime"]=0.4             # In seconds
parameters["columns"] = 2560            # In pixels
parameters["rows"] = 2160               # In pixels 
parameters["etl_step"] = 400#100            # In pixels
parameters["camera_delay"] = 10         # In %
parameters["min_t_delay"] = 0.0354404   # In seconds
parameters["t_start_exp"] = 0.017712    # In seconds

'''DAQ channels'''
terminals = dict()
terminals["galvos_etls"] = '/Dev1/ao0:3'
terminals["camera"]='/Dev1/port0/line1'
terminals["lasers"]='/Dev7/ao0:1'


'''Math functions'''
def gaussian(x,a,x0,sigma):
    '''Gaussian Function'''
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

class Controller(QWidget):
    '''
    Class for control of the MesoSPIM
    '''
    
    sig_update_progress = QtCore.pyqtSignal(int) #Signal for progress bar
    
    '''Initialization Methods'''
    
    def __init__(self):
        QWidget.__init__(self)
        
        ###Test
        self.left_slope = -0.001282893174259485
        self.left_intercept = 4.920315064788371
        self.right_slope = 0.0013507132995247916
        self.right_intercept = 1.8730880902476752
        ###
        
        '''Loading user interface'''
        basepath= os.path.join(os.path.dirname(__file__))
        uic.loadUi(os.path.join(basepath,"control.ui"), self)
        
        '''Defining attributes'''
        self.parameters = copy.deepcopy(parameters)
        self.defaultParameters = copy.deepcopy(parameters)
        
        self.consumers = [] ###
        self.figure_counter = 1
        self.default_buttons = [self.pushButton_standbyOn,
                                self.pushButton_getSingleImage,
                                self.pushButton_startPreviewMode,
                                self.pushButton_startLiveMode,
                                self.pushButton_startStack,
                                self.pushButton_calibrateCamera,
                                self.pushButton_calibrateEtlsGalvos]
        
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
        self.etls_calibration_started = False
        
        self.horizontal_forward_boundary_selected = False
        self.horizontal_backward_boundary_selected = False
        self.focus_selected = False
        self.etls_calibrated = True#False
        
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
        self.sig_update_progress.connect(self.progressBar_stackMode.setValue)
        '''Connection for unit change'''
        self.comboBox_unit.currentTextChanged.connect(self.update_unit)
        
        '''Connection for data saving'''
        self.pushButton_selectDirectory.clicked.connect(self.select_directory)
        
        self.pushButton_selectFile.clicked.connect(self.select_file)
        self.pushButton_selectDataset.clicked.connect(self.select_dataset)
        
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
        self.pushButton_showInterpolation.pressed.connect(self.show_camera_interpolation)
        
        self.pushButton_calibrateEtlsGalvos.pressed.connect(self.start_calibrate_etls)
        self.pushButton_stopEtlsGalvosCalibration.pressed.connect(self.stop_calibrate_etls)
        self.pushButton_showEtlInterpolation.pressed.connect(self.show_etl_interpolation)
        
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
        self.doubleSpinBox_leftLaser.valueChanged.connect(lambda: self.update_etl_galvos_parameters(13))
        self.doubleSpinBox_rightLaser.valueChanged.connect(lambda: self.update_etl_galvos_parameters(14))
        
        self.pushButton_defaultParameters.clicked.connect(self.back_to_default_parameters)
        self.pushButton_changeDefaultParameters.clicked.connect(self.change_default_parameters)
        self.pushButton_saveDefaultParameters.clicked.connect(self.save_default_parameters)
        
        '''Connections for the lasers'''
        self.pushButton_lasersOn.clicked.connect(self.activate_both_lasers)
        self.pushButton_lasersOff.clicked.connect(self.deactivate_both_lasers)
        self.pushButton_leftLaserOn.clicked.connect(self.activate_left_laser)
        self.pushButton_leftLaserOff.clicked.connect(self.deactivate_left_laser)
        self.pushButton_rightLaserOn.clicked.connect(self.activate_right_laser)
        self.pushButton_rightLaserOff.clicked.connect(self.deactivate_right_laser)
    
    def initialize_widgets(self):
        '''Initializes the properties of the widgets that are not updated by a 
        change of units, i.e. the widgets that cannot be initialize with 
        self.update_unit()'''
        
        '''--Data saving's related widgets--'''
        self.lineEdit_filename.setEnabled(False)
        self.lineEdit_sampleName.setEnabled(False)
        
        self.pushButton_selectDataset.setEnabled(False)
        
        '''--Motion's related widgets--'''
        self.comboBox_unit.insertItems(0,["cm","mm","\u03BCm"])
        self.comboBox_unit.setCurrentIndex(1) #Default unit in millimeters
        
        self.pushButton_setForwardLimit.setEnabled(False)
        self.pushButton_setBackwardLimit.setEnabled(False)
        self.pushButton_calculateFocus.setEnabled(False)
        self.pushButton_showInterpolation.setEnabled(False)
        
        '''Arbitrary default positions (in micro-steps)'''
        self.horizontal_forward_boundary = 428346 #533333.3333  #Maximum motor position, in micro-steps
        self.horizontal_backward_boundary = 375853 #0           #Mimimum motor position, in micro-steps
        self.origin_horizontal = self.horizontal_forward_boundary
        self.origin_vertical = self.motor_vertical.position_to_data(1.0, 'cm') ##
        
        self.vertical_up_boundary = 1060000.6667        #Maximum motor position, in micro-steps
        self.vertical_down_boundary = 0                 #Mimimum motor position, in micro-steps
        
        self.camera_forward_boundary = 500000           #Maximum motor position, in micro-steps ##À adapter selon le nouveau porte-cuvette
        self.camera_backward_boundary = 0               #Mimimum motor position, in micro-steps
        self.focus = 265000     #Default focus position ##Possiblement à changer
        
        '''--Modes' related widgets--'''
        '''Disable some buttons'''
        self.pushButton_stopLiveMode.setEnabled(False)
        self.pushButton_stopStack.setEnabled(False)
        self.pushButton_saveImage.setEnabled(False)
        self.pushButton_stopPreviewMode.setEnabled(False)
        self.pushButton_standbyOff.setEnabled(False)
        self.pushButton_cancelCalibrateCamera.setEnabled(False)
        self.pushButton_stopEtlsGalvosCalibration.setEnabled(False)
        self.pushButton_showEtlInterpolation.setEnabled(False)
        
        self.checkBox_setStartPoint.setEnabled(False)
        self.checkBox_setEndPoint.setEnabled(False)
        
        '''Initialize plane steps'''
        self.doubleSpinBox_planeStep.setSuffix(' \u03BCm')
        self.doubleSpinBox_planeStep.setDecimals(0)
        self.doubleSpinBox_planeStep.setMaximum(101600) ##???
        self.doubleSpinBox_planeStep.setSingleStep(1)
        
        self.doubleSpinBox_numberOfCalibrationPlanes.setSuffix(' planes')
        self.doubleSpinBox_numberOfCalibrationPlanes.setDecimals(0)
        self.doubleSpinBox_numberOfCalibrationPlanes.setValue(10) #10 planes by default
        self.doubleSpinBox_numberOfCalibrationPlanes.setMinimum(3) #To allow interpolation
        self.doubleSpinBox_numberOfCalibrationPlanes.setMaximum(10000) ##???
        self.doubleSpinBox_numberOfCalibrationPlanes.setSingleStep(1)
        
        self.doubleSpinBox_numberOfCameraPositions.setSuffix(' planes')
        self.doubleSpinBox_numberOfCameraPositions.setDecimals(0)
        self.doubleSpinBox_numberOfCameraPositions.setValue(15) #15 camera positions by default
        self.doubleSpinBox_numberOfCameraPositions.setMaximum(10000) ##???
        self.doubleSpinBox_numberOfCameraPositions.setSingleStep(1)
        
        self.doubleSpinBox_numberOfEtlVoltages.setSuffix(' voltages')
        self.doubleSpinBox_numberOfEtlVoltages.setDecimals(0)
        self.doubleSpinBox_numberOfEtlVoltages.setValue(10) #10 ETL points by default
        self.doubleSpinBox_numberOfEtlVoltages.setMaximum(10000) ##???
        self.doubleSpinBox_numberOfEtlVoltages.setSingleStep(1)
        
        '''--ETLs and galvos parameters' related widgets--'''
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
        
        self.doubleSpinBox_leftLaser.setMaximum(2.5)
        self.doubleSpinBox_leftLaser.setMaximum(2.5)
        
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
        
        self.doubleSpinBox_leftLaser.setValue(self.parameters["laser_l_voltage"])
        self.doubleSpinBox_rightLaser.setValue(self.parameters["laser_r_voltage"])
        
        '''Initialize step values'''
        self.doubleSpinBox_leftEtlAmplitude.setSingleStep(0.1)
        self.doubleSpinBox_rightEtlAmplitude.setSingleStep(0.1)
        self.doubleSpinBox_leftEtlOffset.setSingleStep(0.1)
        self.doubleSpinBox_rightEtlOffset.setSingleStep(0.1)
        
        self.doubleSpinBox_leftGalvoAmplitude.setSingleStep(0.1)
        self.doubleSpinBox_rightGalvoAmplitude.setSingleStep(0.1)
        self.doubleSpinBox_leftGalvoOffset.setSingleStep(0.1)
        self.doubleSpinBox_rightGalvoOffset.setSingleStep(0.1)
        
        self.doubleSpinBox_leftLaser.setSingleStep(0.1)
        self.doubleSpinBox_rightLaser.setSingleStep(0.1)
        
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
        
        self.doubleSpinBox_leftLaser.setSuffix(" V")
        self.doubleSpinBox_rightLaser.setSuffix(" V")
        
        '''--Lasers parameters' related widgets--'''
        '''Disable some buttons'''
        self.pushButton_lasersOff.setEnabled(False)
        self.pushButton_leftLaserOff.setEnabled(False)
        self.pushButton_rightLaserOff.setEnabled(False)
    
    
    '''General Methods'''
    
    def close_modes(self):
        '''Close all modes if they are active'''

        if self.laser_on == True:
            self.stop_lasers()
        if self.preview_mode_started == True:
            self.stop_preview_mode()
        if self.live_mode_started == True:
            self.stop_live_mode()
        if self.stack_mode_started == True:
            self.stop_stack_mode()
        if self.standby == True:
            self.stop_standby()
        if self.camera_calibration_started == True:
            self.stop_calibrate_camera()
        if self.etls_calibration_started == True:
            self.stop_calibrate_etls()
    
    def closeEvent(self, event):
        '''Making sure that everything is closed when the user exits the software.
           This function executes automatically when the user closes the UI.
           This is an intrinsic function name of Qt, don't change the name even 
           if it doesn't follow the naming convention'''
        
        self.close_modes()
        if self.camera_on == True:
            self.close_camera()
        
        event.accept()
    
    def open_camera(self):
        '''Opens the camera'''
        
        self.camera_on = True
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
        self.consumers.append(wait)             ###Pas implémenté
        self.consumers.append(consumer_type)    
        self.consumers.append(update_flag)      ###Pas implémenté
    
    def print_controller(self,text):
        '''Print text to console and controller text box'''
        
        print(text)
        self.label_lastCommands.setText(self.label_lastCommands.text()+'\n '+text)
    
    
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
        self.doubleSpinBox_chooseCamera.setValue(0) ##Impossible, car le min est 50mm
        
        '''Update maximum and minimum values'''
        
        if self.unit == 'cm':
            self.decimals = 4
            
            self.horizontal_correction = 10.16  #Horizontal correction to fit choice of axis
            self.vertical_correction = 1.0      #Vertical correction to fit choice of axis ##À ajuster avec nouveau porte-cuvette
            self.camera_sample_min_distance = 3.0   #Approximate minimal horizontal distance between camera  ##Possiblement à changer
            self.camera_correction = 9.525 + 4.0  #Camera correction to fit choice of axis##À ajuster avec nouveau porte-cuvette +arranger 5cm entre camera et origine
        elif self.unit == 'mm':
            self.decimals = 3
            
            self.horizontal_correction = 101.6      #Correction to fit choice of axis
            self.vertical_correction = 10.0         #Correction to fit choice of axis ##À ajuster avec nouveau porte-cuvette
            self.camera_sample_min_distance = 30.0   #Approximate minimal horizontal distance between camera  ##Possiblement à changer
            self.camera_correction =95.25 + 40.0      #Camera correction to fit choice of axis##À ajuster avec nouveau porte-cuvette
        elif self.unit == '\u03BCm':
            self.decimals = 0
            
            self.horizontal_correction = 101600     #Correction to fit choice of axis
            self.vertical_correction = 10000        #Correction to fit choice of axis ##À ajuster avec nouveau porte-cuvette
            self.camera_sample_min_distance = 30000   #Approximate minimal horizontal distance between camera  ##Possiblement à changer
            self.camera_correction = 95250 + 40000    #Camera correction to fit choice of axis##À ajuster avec nouveau porte-cuvette
        
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
    
    def return_current_horizontal_position(self):
        '''Returns the current horizontal position with respect to the choice of axis'''
        return -self.motor_horizontal.current_position(self.unit)+self.horizontal_correction #Minus sign and correction to fit choice of axis
    
    def return_current_vertical_position(self):
        '''Returns the current vertical position with respect to the choice of axis'''
        return -self.motor_vertical.current_position(self.unit)+self.vertical_correction #Minus sign and correction to fit choice of axis
    
    def return_current_camera_position(self):
        '''Returns the current camera position with respect to the choice of axis'''
        return -self.motor_camera.current_position(self.unit)+self.camera_correction #Minus sign and correction to fit choice of axis
    

    def update_position_horizontal(self):
        '''Updates the current horizontal sample position displayed'''
        
        current_horizontal_position = round(self.return_current_horizontal_position(),self.decimals)
        self.current_horizontal_position_text = "{} {}".format(current_horizontal_position, self.unit)
        self.label_currentHorizontalNumerical.setText(self.current_horizontal_position_text)
    
    def update_position_vertical(self):
        '''Updates the current vertical sample position displayed'''
        
        self.current_vertical_position = round(self.return_current_vertical_position(),self.decimals)
        self.current_vertical_position_text = "{} {}".format(self.current_vertical_position, self.unit)
        self.label_currentHeightNumerical.setText(self.current_vertical_position_text)
        
    def update_position_camera(self):
        '''Updates the current (horizontal) camera position displayed'''

        self.current_camera_position = round(self.return_current_camera_position(),self.decimals)
        self.current_camera_position_text = "{} {}".format(self.current_camera_position, self.unit)
        self.label_currentCameraNumerical.setText(self.current_camera_position_text)
    
    
    def move_to_horizontal_position(self):
        '''Moves the sample to a specified horizontal position'''
        
        if self.doubleSpinBox_choosePosition.value() >= self.horizontal_minimum_in_new_axis and self.doubleSpinBox_choosePosition.value() <= self.horizontal_maximum_in_new_axis:
            
            if (self.return_current_camera_position() - self.doubleSpinBox_choosePosition.value() >= self.camera_sample_min_distance):  #To prevent the sample from hitting the camera
                self.print_controller('Sample moving to horizontal position')
                
                horizontal_position = -self.doubleSpinBox_choosePosition.value()+self.horizontal_correction
                self.motor_horizontal.move_absolute_position(horizontal_position,self.unit)
            
                self.update_position_horizontal()
            else:
                self.print_controller('Camera prevents sample movement')
            
        else:
            self.print_controller('Out Of Boundaries')
    
    def move_to_vertical_position(self):
        '''Moves the sample to a specified vertical position'''
        
        self.print_controller ('Sample moving to vertical position')
            
        vertical_position = -self.doubleSpinBox_chooseHeight.value()+self.vertical_correction #Minus sign and correction to fit choice of axis
        self.motor_vertical.move_absolute_position(vertical_position,self.unit)
        
        self.update_position_vertical()
    
    def move_camera_to_position(self):
        '''Moves the sample to a specified vertical position'''
        
        if (self.doubleSpinBox_chooseCamera.value() - self.return_current_horizontal_position() >= self.camera_sample_min_distance):  #To prevent the sample from hitting the camera
            self.print_controller ('Camera moving to position')
            
            camera_position = -self.doubleSpinBox_chooseCamera.value()+self.camera_correction #Minus sign and correction to fit choice of axis
            self.motor_camera.move_absolute_position(camera_position,self.unit)
            
            self.update_position_camera()
        else:
            self.print_controller('Sample prevents camera movement')
    
    def move_camera_backward(self):
        '''Camera motor backward horizontal motion'''
        
        if self.motor_camera.current_position(self.unit) - self.doubleSpinBox_incrementCamera.value() >= self.camera_minimum_in_old_axis:
            self.print_controller ('Camera moving backward')
            
            self.motor_camera.move_relative_position(-self.doubleSpinBox_incrementCamera.value(),self.unit)
        else:
            self.print_controller('Out of boundaries')
            
            self.motor_camera.move_absolute_position(self.camera_backward_boundary,'\u03BCStep')
            
        self.update_position_camera()
    
    def move_camera_forward(self):
        '''Camera motor forward horizontal motion'''
        
        if self.motor_camera.current_position(self.unit) + self.doubleSpinBox_incrementCamera.value() <= self.camera_maximum_in_old_axis:
            
            next_camera_position = -(self.motor_camera.current_position(self.unit)+self.doubleSpinBox_incrementCamera.value()) + self.camera_correction
            
            if (next_camera_position - self.return_current_horizontal_position() >= self.camera_sample_min_distance):  #To prevent the sample from hitting the camea
                self.print_controller ('Camera moving forward')
                self.motor_camera.move_relative_position(self.doubleSpinBox_incrementCamera.value(),self.unit)
            else:
                self.print_controller('Sample prevents camera movement')
        else:
            self.print_controller('Out of boundaries')
            
            self.motor_camera.move_absolute_position(self.camera_forward_boundary,'\u03BCStep')
            
        self.update_position_camera()
    
    def move_camera_to_focus(self):
        '''Moves camera to focus position'''
        if self.focus_selected == True:
        
            if self.focus < self.camera_backward_boundary:
                self.print_controller('Focus out of boundaries')
                
                self.motor_camera.move_absolute_position(self.camera_minimum_in_old_axis,self.unit)
            elif self.focus > self.camera_forward_boundary:
                self.print_controller('Focus out of boundaries')
                
                self.motor_camera.move_absolute_position(self.camera_maximum_in_old_axis,self.unit)
            else:
                next_camera_position = -self.motor_camera.data_to_position(self.focus, self.unit) + self.camera_correction
                
                if (next_camera_position - self.return_current_horizontal_position() >= self.camera_sample_min_distance):  #To prevent the sample from hitting the camea
                    self.print_controller('Moving to focus')
                    
                    self.motor_camera.move_absolute_position(self.focus,'\u03BCStep')
                else:
                    self.print_controller('Sample prevents camera movement')
        else:
            self.print_controller('Focus not yet set. Moving camera to default focus')
            
            self.motor_camera.move_absolute_position(self.focus,'\u03BCStep')
        
        self.update_position_camera()
    
    def move_sample_down(self):
        '''Sample motor downward vertical motion'''
        
        if self.motor_vertical.current_position(self.unit) - self.doubleSpinBox_incrementVertical.value() >= self.vertical_minimum_in_old_axis:
            self.print_controller('Sample moving down')
            
            self.motor_vertical.move_relative_position(self.doubleSpinBox_incrementVertical.value(),self.unit)
        else:
            self.print_controller('Out of boundaries')
            
            self.motor_vertical.move_absolute_position(self.vertical_down_boundary,'\u03BCStep')
            
        self.update_position_vertical()
    
    def move_sample_up(self):
        '''Sample motor upward vertical motion'''
        
        if self.motor_vertical.current_position(self.unit) + self.doubleSpinBox_incrementVertical.value() <= self.vertical_maximum_in_old_axis:
            self.print_controller('Sample moving up')
            
            self.motor_vertical.move_relative_position(-self.doubleSpinBox_incrementVertical.value(),self.unit)
        else:
            self.print_controller('Out of boundaries')
            
            self.motor_vertical.move_absolute_position(self.vertical_up_boundary,'\u03BCStep')
        
        self.update_position_vertical()
    
    def move_sample_backward(self):
        '''Sample motor backward horizontal motion'''
        
        if self.motor_horizontal.current_position(self.unit) - self.doubleSpinBox_incrementHorizontal.value() >= self.horizontal_minimum_in_old_axis:
            
            next_horizontal_position = -(self.motor_horizontal.current_position(self.unit)-self.doubleSpinBox_incrementHorizontal.value()) + self.horizontal_correction
            
            if (self.return_current_camera_position() - next_horizontal_position >= self.camera_sample_min_distance):  #To prevent the sample from hitting the camea
                self.print_controller ('Sample moving backward')
                
                self.motor_horizontal.move_relative_position(-self.doubleSpinBox_incrementHorizontal.value(),self.unit)
            else:
                self.print_controller('Camera prevents sample movement')
        else:
            self.print_controller('Out of boundaries')
            
            self.motor_horizontal.move_absolute_position(self.horizontal_backward_boundary, '\u03BCStep')
        
        self.update_position_horizontal()
            
    def move_sample_forward(self):
        '''Sample motor forward horizontal motion'''
        
        if self.motor_horizontal.current_position(self.unit) + self.doubleSpinBox_incrementHorizontal.value() <= self.horizontal_maximum_in_old_axis:
            self.print_controller('Sample moving forward')
            self.motor_horizontal.move_relative_position(self.doubleSpinBox_incrementHorizontal.value(),self.unit)
        else:
            self.print_controller('Out of boundaries')
            
            self.motor_horizontal.move_absolute_position(self.horizontal_forward_boundary, '\u03BCStep')
        
        self.update_position_horizontal()
    
    def move_sample_to_origin(self):
        '''Moves vertical and horizontal sample motors to origin position'''
        
        self.print_controller('Moving to origin')
        
        origin_horizontal_current_unit = self.motor_horizontal.data_to_position(self.origin_horizontal, self.unit)
        if origin_horizontal_current_unit >= self.horizontal_minimum_in_old_axis and origin_horizontal_current_unit <= self.horizontal_maximum_in_old_axis:
            
            next_horizontal_position = -origin_horizontal_current_unit + self.horizontal_correction
            
            if (self.return_current_camera_position() - next_horizontal_position >= self.camera_sample_min_distance):  #To prevent the sample from hitting the camea
                '''Moving sample to horizontal origin'''
                self.motor_horizontal.move_absolute_position(self.origin_horizontal,'\u03BCStep')
                self.update_position_horizontal()
            else:
                self.print_controller('Camera prevents sample movement')
            
        else:
            self.print_controller('Sample Horizontal Origin Out Of Boundaries')
        
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
        self.horizontal_forward_boundary = 428346 #533333.3333  #Maximum motor position, in micro-steps
        self.horizontal_backward_boundary = 375853 #0           #Minimum motor position, in micro-steps
        
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
        self.origin_vertical = 1066666 - self.motor_vertical.position_to_data(self.motor_vertical.current_position(self.unit),self.unit) ##???
        
        origin_text = 'Origin set at (x,z) = ({}, {}) {}'.format(self.origin_horizontal,self.origin_vertical, self.unit)
        self.print_controller(origin_text)
    
    def set_camera_focus(self):
        '''Modifies manually the camera focus position'''
        
        self.focus_selected = True
        self.focus = self.motor_camera.current_position('\u03BCStep')
        
        self.print_controller('Focus manually set')
        
    def calculate_camera_focus(self):
        '''Interpolates the camera focus position'''
        
        current_position = -self.motor_horizontal.current_position(self.unit) + self.horizontal_correction
        focus_regression = self.slope_camera * current_position + self.intercept_camera
        self.focus = self.motor_camera.position_to_data(-focus_regression+self.camera_correction, self.unit)#self.motor_camera.position_to_data(-focus_interpolation+self.camera_correction, self.unit)
        print('focus_regression:'+str(focus_regression)) #debugging
        print('focus:'+str(self.focus)) #debugging
        
        self.focus_selected = True
        
        self.print_controller('Focus automatically set')
    
    def show_camera_interpolation(self):
        '''Shows the camera focus interpolation'''
        
        x = self.camera_focus_relation[:,0]
        y = self.camera_focus_relation[:,1]
        
        '''Calculatinf linear regression'''
        xnew = np.linspace(self.camera_focus_relation[0,0], self.camera_focus_relation[-1,0], 1000) ##1000 points
        self.slope_camera, self.intercept_camera, r_value, p_value, std_err = stats.linregress(x, y)
        #print('r_value:'+str(r_value)) #debugging
        #print('p_value:'+str(p_value)) #debugging
        #print('std_err:'+str(std_err)) #debugging
        yreg = self.slope_camera * xnew + self.intercept_camera
        
        '''Setting colormap'''
        xstart = -self.motor_horizontal.data_to_position(self.horizontal_forward_boundary, 'mm') + self.horizontal_correction
        xend = -self.motor_horizontal.data_to_position(self.horizontal_backward_boundary, 'mm') + self.horizontal_correction
        ystart = -self.motor_camera.data_to_position(self.focus_forward_boundary, 'mm') + self.camera_correction
        yend = -self.motor_camera.data_to_position(self.focus_backward_boundary, 'mm') + self.camera_correction
        transp = copy.deepcopy(self.donnees)
        for q in range(int(self.number_of_calibration_planes)):
            transp[q,:] = np.flip(transp[q,:])
        transp = np.transpose(transp)

        '''Showing interpolation graph'''
        plt.figure(1)
        plt.title('Camera Focus Regression') 
        plt.xlabel('Sample Horizontal Position ({})'.format(self.unit)) 
        plt.ylabel('Camera Position ({})'.format(self.unit))
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
    
    def change_default_parameters(self):
        '''Change all the default modifiable parameters to the current parameters'''
        
        self.defaultParameters["etl_l_amplitude"] = self.doubleSpinBox_leftEtlAmplitude.value()
        self.defaultParameters["etl_r_amplitude"] = self.doubleSpinBox_rightEtlAmplitude.value()
        self.defaultParameters["etl_l_offset"] = self.doubleSpinBox_leftEtlOffset.value()
        self.defaultParameters["etl_r_offset"] = self.doubleSpinBox_rightEtlOffset.value()
        self.defaultParameters["galvo_l_amplitude"] = self.doubleSpinBox_leftGalvoAmplitude.value()
        self.defaultParameters["galvo_r_amplitude"] = self.doubleSpinBox_rightGalvoAmplitude.value()
        self.defaultParameters["galvo_l_offset"] = self.doubleSpinBox_leftGalvoOffset.value()
        self.defaultParameters["galvo_r_offset"] = self.doubleSpinBox_rightGalvoOffset.value()
        self.defaultParameters["galvo_l_frequency"] = self.doubleSpinBox_leftGalvoFrequency.value()
        self.defaultParameters["galvo_r_frequency"] = self.doubleSpinBox_rightGalvoFrequency.value()
        self.defaultParameters["samplerate"] = self.doubleSpinBox_samplerate.value()
        
    def save_default_parameters(self):
        '''Change all the default parameters of the configuration file to current default parameters'''
        
        with open(r"C:\git-projects\lightsheet\src\configuration.txt","w") as file:
            file.write(str(parameters["etl_l_amplitude"])+'\n'+
                       str(parameters["etl_r_amplitude"])+'\n'+
                       str(parameters["etl_l_offset"])+'\n'+
                       str(parameters["etl_r_offset"])+'\n'+
                       str(parameters["galvo_l_amplitude"])+'\n'+
                       str(parameters["galvo_r_amplitude"])+'\n'+
                       str(parameters["galvo_l_offset"])+'\n'+
                       str(parameters["galvo_r_offset"])+'\n'+
                       str(parameters["galvo_l_frequency"])+'\n'+
                       str(parameters["galvo_r_frequency"])+'\n'+
                       str(parameters["samplerate"])
                       )  
    
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
        elif parameterNumber==13:
            self.parameters["laser_l_voltage"]=self.doubleSpinBox_leftLaser.value()
        elif parameterNumber==14:
            self.parameters["laser_r_voltage"]=self.doubleSpinBox_rightLaser.value()

    
    def activate_both_lasers(self):
        '''Flag and lasers' pushButton managing for both lasers activation'''
        
        self.both_lasers_activated = True
        
        self.pushButton_lasersOn.setEnabled(False)
        self.pushButton_lasersOff.setEnabled(True)
        self.pushButton_leftLaserOn.setEnabled(False)
        self.pushButton_rightLaserOn.setEnabled(False)
        
        self.print_controller('Lasers on')
    
    def deactivate_both_lasers(self):
        '''Flag and lasers' pushButton managing for both lasers deactivation'''
        
        self.both_lasers_activated = False
        
        self.pushButton_lasersOn.setEnabled(True)
        self.pushButton_lasersOff.setEnabled(False)
        self.pushButton_leftLaserOn.setEnabled(True)
        self.pushButton_rightLaserOn.setEnabled(True)
        
        self.print_controller('Lasers off')
    
    def activate_left_laser(self):
        '''Flag and lasers' pushButton managing for left laser activation'''
        
        self.left_laser_activated = True
        
        self.pushButton_lasersOn.setEnabled(False)
        self.pushButton_leftLaserOn.setEnabled(False)
        self.pushButton_leftLaserOff.setEnabled(True)
        
        self.print_controller('Left laser on')
    
    def deactivate_left_laser(self):
        '''Flag and lasers' pushButton managing for left laser deactivation'''
        
        self.left_laser_activated = False
         
        self.pushButton_leftLaserOn.setEnabled(True)
        self.pushButton_leftLaserOff.setEnabled(False)
        if self.pushButton_rightLaserOn.isEnabled() == True:
            self.pushButton_lasersOn.setEnabled(True)
        
        self.print_controller('Left laser off')
    
    def activate_right_laser(self):
        '''Flag and lasers' pushButton managing for right laser activation'''
        
        self.right_laser_activated = True
        
        self.pushButton_lasersOn.setEnabled(False)
        self.pushButton_rightLaserOn.setEnabled(False)
        self.pushButton_rightLaserOff.setEnabled(True)
        
        self.print_controller('Left laser on')
    
    def deactivate_right_laser(self):
        '''Flag and lasers' pushButton managing for right laser deactivation'''
        
        self.right_laser_activated = False
        
        self.pushButton_rightLaserOn.setEnabled(True)
        self.pushButton_rightLaserOff.setEnabled(False)
        if self.pushButton_leftLaserOn.isEnabled() == True:
            self.pushButton_lasersOn.setEnabled(True)
        
        self.print_controller('Left laser off')
    
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
 
 
    '''File Open Methods'''
        
    def select_file(self):
        '''Allows the selection of a file (.hdf5), opens it and displays its datasets'''
        
        '''Retrieve File'''
        self.open_directory = QFileDialog.getOpenFileName(self, 'Choose File', '', 'Hierarchical files (*.hdf5)')[0]
        
        if self.open_directory != '':
            self.label_currentFileDirectory.setText(self.open_directory)
            self.listWidget_fileDatasets.clear()
            
            '''Open the file and display its datasets'''
            with h5py.File(self.open_directory, "r") as f:
                dataset_names = list(f.keys())
                for item in range(0,len(dataset_names)):
                    self.listWidget_fileDatasets.insertItem(item,dataset_names[item])
            self.listWidget_fileDatasets.setCurrentRow(0)
            
            self.print_controller('File '+self.open_directory+' opened')
            
            self.pushButton_selectDataset.setEnabled(True)
        else:
            self.label_currentFileDirectory.setText('None specified')
    
    def select_dataset(self):
        '''Opens a HDF5 dataset and displays its attributes and data as an image'''
        
        if (self.open_directory != '') and  (self.listWidget_fileDatasets.count() != 0):
            self.dataset_name = self.listWidget_fileDatasets.currentItem().text()
            with h5py.File(self.open_directory, "r") as f:
                dataset = f[self.dataset_name]
                
                '''Display attributes'''
                attribute_names = list(dataset.attrs.keys())
                attribute_values = list(dataset.attrs.values())
                self.tableWidget_fileAttributes.setColumnCount(2)
                self.tableWidget_fileAttributes.setRowCount(len(attribute_names))
                self.tableWidget_fileAttributes.setHorizontalHeaderItem(0,QTableWidgetItem('Attributes'))
                self.tableWidget_fileAttributes.setHorizontalHeaderItem(1,QTableWidgetItem('Values'))
                for attribute in range(0,len(attribute_names)):
                    self.tableWidget_fileAttributes.setItem(attribute,0,QTableWidgetItem(attribute_names[attribute]))
                    self.tableWidget_fileAttributes.setItem(attribute,1,QTableWidgetItem(str(attribute_values[attribute])))
                self.tableWidget_fileAttributes.resizeColumnsToContents()
                self.tableWidget_fileAttributes.setEditTriggers(QAbstractItemView.NoEditTriggers) #No editing possible
                
                '''Display image'''
                data = dataset[()]
                plt.figure('Figure '+str(self.figure_counter)+': '+self.open_directory+' ('+self.dataset_name+')')
                plt.imshow(data,cmap='gray')
                plt.show(block=False)   #Prevents the plot from blocking the execution of the code...
                self.figure_counter+=1
            
            self.print_controller('Dataset '+self.dataset_name+' of file '+self.open_directory+' displayed')
    
    
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
            self.lineEdit_sampleName.setEnabled(True)
            self.saving_allowed = True
        else:
            self.label_currentDirectory.setText('None specified')
            self.lineEdit_filename.setEnabled(False)
            self.lineEdit_filename.setText('Select directory first')
            self.lineEdit_sampleName.setEnabled(False)
            self.saving_allowed = False
    
    def update_buttons(self,buttons_to_enable):
        '''Update buttons status (enable/disable)'''
        
        aquisition_buttons = [self.pushButton_standbyOn,
                              self.pushButton_standbyOff,
                              self.pushButton_startPreviewMode,
                              self.pushButton_stopPreviewMode,
                              self.pushButton_startLiveMode,
                              self.pushButton_stopLiveMode,
                              self.pushButton_getSingleImage,
                              self.pushButton_saveImage,
                              self.pushButton_startStack,
                              self.pushButton_stopStack,
                              self.pushButton_calibrateCamera,
                              self.pushButton_calculateFocus,
                              self.pushButton_showInterpolation,
                              self.pushButton_calibrateEtlsGalvos,
                              self.pushButton_showEtlInterpolation
                              ]
        for button in aquisition_buttons:
            if button in buttons_to_enable:
                button.setEnabled(True)
            else:
                button.setEnabled(False)
    
    
    def start_standby(self):
        '''Closes the camera and initiates thread to keep ETLs'currents at 0A while
           the microscope is not in use'''
        
        self.close_modes()
        self.standby = True
        
        '''Close camera'''
        self.close_camera()
        
        '''Modes disabling while in standby'''
        self.update_buttons([self.pushButton_standbyOff])
        
        self.print_controller('Standby on')
        
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
        self.update_buttons(self.default_buttons)
        
        self.print_controller('Standby off')
    
    def stop_standby(self):
        '''Changes the standby flag status to end the thread'''
        
        self.standby = False
    
    
    def start_preview_mode(self):
        '''Initializes variables for preview modes where beam and focal 
           positions are manually controlled by the user'''
        
        self.close_modes()
        self.preview_mode_started = True
        
        '''Modes disabling during preview_mode execution'''
        self.update_buttons([self.pushButton_stopPreviewMode])
        
        self.print_controller('Preview mode started')
        
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
                                                              np.array([left_etl_voltage]),
                                                              np.array([right_etl_voltage])))
                    
                    '''Writing the data'''
                    self.preview_galvos_etls_task.write(preview_galvos_etls_waveforms, auto_start=True)
                    
                    '''Retrieving image from camera and putting it in its queue
                       for display'''
                    frame = self.camera.retrieve_single_image()*1.0
                    frame = np.transpose(frame)
                    try:
                        self.consumers[i].put(frame)
                    except self.consumers[i].Full:
                        print("Queue is full")
        
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
        self.update_buttons(self.default_buttons)
        
        self.print_controller('Preview mode stopped')
    
    def stop_preview_mode(self):
        '''Changes the preview_mode flag status to end the thread'''
        
        self.preview_mode_started = False
    
    def reconstruct_frame(self):
        '''Reconstructs a frame from multiple frames'''
        
        frame = np.zeros((int(self.parameters["rows"]), int(self.parameters["columns"])))  #Initializing frame
                
        #For each column step
        for i in range(int(self.number_of_steps)-1):
            current_step = int(i*self.parameters['etl_step'])
            next_step = int(i*self.parameters['etl_step']+self.parameters['etl_step'])
            frame[:,current_step:next_step] = self.buffer[i,:,current_step:next_step]
        #For the last column step (may be different than the others...)
        last_step = int(int(self.number_of_steps-1) * self.parameters['etl_step'])
        frame[:,last_step:] = self.buffer[int(self.number_of_steps-1),:,last_step:]
        
        return frame
    
    
    def start_live_mode(self):
        '''This mode is for visualizing (and modifying) the effects of the 
           chosen parameters of the ramps which will be sent for single image 
           saving or volume saving (with stack_mode)'''
        
        self.close_modes()
        self.live_mode_started = True
        
        '''Disabling other modes while in live_mode'''
        self.update_buttons([self.pushButton_stopLiveMode])
        
        self.print_controller('Live mode started')
        
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
        
        '''Moving the camera to focus'''
        ###self.move_camera_to_focus() 
        
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
                    if self.etls_calibrated == True:
                        self.ramps.create_calibrated_etl_waveforms(self.left_slope, self.left_intercept, self.right_slope, self.right_intercept, case = 'STAIRS')##
                    else: ##
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
                    frame = self.reconstruct_frame()
                       
                    '''Frame display'''
                    frame = np.transpose(frame)
                    for i in range(0, len(self.consumers), 4):
                        if self.consumers[i+2] == "CameraWindow":
                            try:
                                self.consumers[i].put(frame)
                            except:      #self.consumers[i].Full:
                                print("Queue is full")
                    
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
        self.update_buttons(self.default_buttons)
        
        self.print_controller('Live mode stopped')

    def stop_live_mode(self):
        '''Changes the live_mode flag status to end the thread'''
        
        self.live_mode_started = False
    
    
    def get_single_image(self):
        '''Generates and display a single frame which can be saved afterwards 
        using self.save_single_image()'''
        
        self.close_modes()
            
        '''Disabling modes while single frame acquisition'''
        self.update_buttons([self.pushButton_saveImage])
        
        self.print_controller('Getting single image')
        
        '''Setting the camera for acquisition'''
        self.camera.set_trigger_mode('ExternalExposureControl')
        self.camera.arm_camera() 
        self.camera.get_sizes() 
        self.camera.allocate_buffer()    
        self.camera.set_recording_state(1)
        self.camera.insert_buffers_in_queue()
        
        '''Moving the camera to focus'''
        ###self.move_camera_to_focus()  
        
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
        frame = self.reconstruct_frame()
        self.save_buffer = np.insert(self.buffer, 0, frame, axis=0)
        
        '''Frame display'''
        frame = np.transpose(frame)
        for i in range(0, len(self.consumers), 4):
            if self.consumers[i+2] == "CameraWindow":
                try:
                    self.consumers[i].put(frame)
                except:      #self.consumers[i].Full:
                    print("Queue is full")
      
        
        '''Stopping camera'''            
        self.camera.cancel_images()
        self.camera.set_recording_state(0)
        self.camera.free_buffer()
        
        '''Stopping and closing ramps'''
        self.ramps.stop_tasks()                             
        self.ramps.close_tasks()
        
        '''Stopping lasers'''
        self.stop_lasers()
        self.both_lasers_activated = False
        
        '''Enabling modes after single frame acquisition'''
        self.update_buttons(self.default_buttons)
    
    def save_single_image(self):
        '''Saves the frame generated by self.get_single_image()'''
        
        '''Retrieving filename set by the user'''
        self.filename = str(self.lineEdit_filename.text())
        
        '''Removing spaces, dots and commas''' ###???
        for symbol in [' ','.',',']:
            self.filename = self.filename.replace(symbol, '')
        
        if self.saving_allowed and self.filename != '':
            self.filename = self.save_directory + '/' + self.filename
            
            '''Setting up frame saver'''
            self.frame_saver = FrameSaver()
            self.frame_saver.set_block_size(1) #Block size is a number of buffers
            self.frame_saver.set_files(1,self.filename, 'singleImage','ETLscan')
            self.frame_saver.add_motor_parameters(self.current_horizontal_position_text,self.current_vertical_position_text,self.current_camera_position_text)
            
            '''Getting sample name'''
            if str(self.lineEdit_sampleName.text()) != '':
                parameters["sample_name"] = str(self.lineEdit_sampleName.text())
            
            '''Saving frame'''
            self.frame_saver.put(self.save_buffer,1)
            self.frame_saver.start_saving(data_type = 'auto')
            self.frame_saver.stop_saving()
            
            self.print_controller('Image saved')
            
        else:
            print('Select directory and enter a valid filename before saving')
    
    
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
    
    
    
    #def start_stack_mode_mp(self):
    #    self.close_modes()
    #    '''Retrieving filename set by the user'''       
    #    self.filename = str(self.lineEdit_filename.text())
    #     
    #    '''Removing spaces, dots and commas''' ###???
    #    for symbol in [' ','.',',']:
    #        self.filename = self.filename.replace(symbol, '')
    #    
    #    '''Making sure the limits of the volume are set, saving is allowed and 
    #       filename isn't empty'''
    #    if (self.checkBox_setStartPoint.isChecked() == False) or (self.checkBox_setEndPoint.isChecked() == False) or (self.doubleSpinBox_planeStep.value() == 0):
    #        print('Set starting and ending points and select a non-zero plane step value')
    #    elif (self.saving_allowed == False) or (self.filename == ''):
    #        print('Select directory and enter a valid filename before saving')
    #    else:
    #        '''Setting start & end points and plane step (takes into account the direction of acquisition) '''
    #        if self.stack_mode_starting_point > self.stack_mode_ending_point:
    #            self.step = -1*self.doubleSpinBox_planeStep.value()
    #            self.start_point = self.stack_mode_starting_point
    #            self.end_point = self.stack_mode_starting_point+self.step*(self.number_of_planes-1)
    #        else:
    #            self.step = self.doubleSpinBox_planeStep.value()
    #            self.start_point = self.stack_mode_starting_point
    #            self.end_point = self.stack_mode_starting_point+self.step*(self.number_of_planes-1)
    #            
    #        self.stack_mode_started = True
    #        
    #        '''Modes disabling while stack acquisition'''
    #        self.update_buttons([self.pushButton_stopStack])
    #        
    #        self.print_controller('Stack mode started -- Number of frames to save: '+str(self.number_of_planes))
    #        
    #        '''Starting stack mode process'''   
    #        
    #        self.p = multiprocessing.Process(target = self.stack_mode_process)
    #        self.p.start()
    #        
    #def stack_mode_process(self): ##utliser get_single_image
    #    ''' Thread for volume acquisition and saving 
    #    
    #    Note: check if there's a NI-Daqmx function to repeat the data sent 
    #          instead of closing each time the task. This would be useful
    #          if it is possible to break a task with self.stop_stack_mode
    #    Simpler solution: Use conditions with self._stack_mode_started status 
    #                      such as in self.live_mode_thread() and 
    #                      self.preview_mode_thread()
    #    
    #    A progress bar would be nice
    #    '''
    #    
    #    '''Setting the camera for acquisition'''
    #    self.camera.set_trigger_mode('ExternalExposureControl')
    #    self.camera.arm_camera() 
    #    self.camera.get_sizes() 
    #    self.camera.allocate_buffer(number_of_buffers=2)    
    #    self.camera.set_recording_state(1)
    #    self.camera.insert_buffers_in_queue()
    #    
    #    ''' Prepare saving (if we lose planes while saving, add more buffers 
    #        to block size, but make sure they don't take all the RAM'''
    #    #self.filename = self.save_directory + '/' + self.filename
    #    #self.frame_saver = FrameSaver()
    #    #self.frame_saver.set_block_size(3)  #3 buffers allowed in the queue
    #    #self.frame_saver.set_files(self.number_of_planes, self.filename, 'stack', 'ETL_scan')
    #    
    #    #self.set_data_consumer(self.frame_saver, False, "FrameSaver", True) ###???
    #    #self.frame_saver.start_saving(data_type = 'auto')
    #    
    #    '''Creating lasers task'''
    #    self.lasers_task = nidaqmx.Task()
    #    self.lasers_task.ao_channels.add_ao_voltage_chan(terminals["lasers"])
    #    
    #    '''Starting lasers'''
    #    self.start_lasers()
    #    
    #    '''Creating ETLs, galvos & camera's ramps and waveforms'''
    #    self.ramps=AOETLGalvos(self.parameters)
    #    self.ramps.initialize()
    #    self.ramps.create_etl_waveforms(case = 'STAIRS')
    #    self.ramps.create_galvos_waveforms(case = 'TRAPEZE')
    #    self.ramps.create_digital_output_camera_waveform( case = 'STAIRS_FITTING')
    #    
    #    '''Set progress bar'''
    #    progress_value = 0
    #    progress_increment = int(100/self.number_of_planes)
    #    self.sig_update_progress.emit(0) #To reset progress bar
    #    
    #    frame_list = []
    #    xvals_list = []
    #    
    #    for plane in range(int(self.number_of_planes)):
    #        
    #        if self.stack_mode_started == False:
    #            self.print_controller('Acquisition Interrupted')
    #            break
    #        else:
    #            '''Moving sample position'''
    #            position = self.start_point+plane*self.step
    #            self.motor_horizontal.move_absolute_position(position,'\u03BCm')  #Position in micro-meters
    #            self.update_position_horizontal()
    #            #self.frame_saver.add_motor_parameters(self.current_horizontal_position_text,self.current_vertical_position_text,self.current_camera_position_text)
    #            
    #            '''Moving the camera to focus'''
    #            ###self.move_camera_to_focus()   
    #            
    #            '''Acquiring the frame '''
    #            self.ramps.create_tasks(terminals,'FINITE')
    #            self.ramps.write_waveforms_to_tasks()                            
    #            self.ramps.start_tasks()
    #            self.ramps.run_tasks()
    #            
    #            '''Retrieving buffer'''
    #            self.number_of_steps = np.ceil(self.parameters["columns"]/self.parameters["etl_step"]) #Number of galvo sweeps in a frame, or alternatively the number of ETL focal step
    #            self.buffer = self.camera.retrieve_multiple_images(self.number_of_steps, self.ramps.t_half_period, sleep_timeout = 5)
    #            
    #            '''Frame reconstruction for display'''
    #            frame = self.reconstruct_frame()
    #            buffer = np.insert(self.buffer, 0, frame, axis=0)
    #            transp_frame = np.transpose(frame)
    #            
    #            xvals_list.append(plane+1) ###changer pour position horizontale?
    #            frame_list.append(transp_frame.tolist())
    #            if len(frame_list) > 3 : ##20 #To prevent the list of frames from being too big
    #                frame_list.pop(0)
    #                xvals_list.pop(0)
    #            
    #            frame3d = np.array(frame_list)
    #            
    #            xvals = np.array(xvals_list)
    #            self.camera_window.change_xvals(xvals)
    #            
    #            '''Frame display and buffer saving'''
    #            for ii in range(0, len(self.consumers), 4):
    #                if self.consumers[ii+2] == 'CameraWindow':
    #                    try:
    #                        self.consumers[ii].put(frame3d)
    #                        print('Frame put in CameraWindow')
    #                    except:      #self.consumers[ii].Full:
    #                        print("CameraWindow queue is full")
    #                    
    #                #if self.consumers[ii+2] == 'FrameSaver':
    #                #    try:
    #                #        self.consumers[ii].put(buffer,1)
    #                #        print('Frame put in FrameSaver')
    #                #    except:      #self.consumers[ii].Full:
    #                #        print("FrameSaver queue is full")
    #            
    #            '''Ending tasks'''
    #            self.ramps.stop_tasks()                             
    #            self.ramps.close_tasks()
    #            
    #            '''Update progress bar'''
    #            progress_value += progress_increment
    #            self.sig_update_progress.emit(progress_value)
    #    
    #    self.finalize_stack_mode_mp()
    #   
    #def finalize_stack_mode_mp(self):
    #    self.sig_update_progress.emit(100) #In case the number of planes is not a multiple of 100
    #    
    #    self.camera_window.change_xvals(None) #Return xvals to default
    #    
    #    self.laser_on = False
    #    
    #    self.frame_saver.stop_saving()
    #    
    #    '''Stopping camera'''
    #    self.camera.cancel_images()
    #    self.camera.set_recording_state(0)
    #    self.camera.free_buffer()
    #            
    #    '''Stopping laser'''
    #    self.stop_lasers()
    #    
    #    '''Enabling modes after stack mode'''
    #    self.update_buttons(self.default_buttons)
    #    
    #    self.print_controller('Acquisition done')
    #    self.p.join()    
    #
    #def stop_stack_mode_mp(self):
    #    '''Changes the live_mode flag status to end the thread'''
    #    self.stack_mode_started = False
    #
    
    
    
    
    
    def start_stack_mode(self):
        '''Initializes variables for volume saving which will take place in 
           self.stack_mode_thread afterwards'''
        
        self.close_modes()
        
        '''Retrieving filename set by the user'''       
        self.filename = str(self.lineEdit_filename.text())
         
        '''Removing spaces, dots and commas''' ###???
        for symbol in [' ','.',',']:
            self.filename = self.filename.replace(symbol, '')
        
        '''Making sure the limits of the volume are set, saving is allowed and 
           filename isn't empty'''
        if (self.checkBox_setStartPoint.isChecked() == False) or (self.checkBox_setEndPoint.isChecked() == False) or (self.doubleSpinBox_planeStep.value() == 0):
            print('Set starting and ending points and select a non-zero plane step value')
        elif (self.saving_allowed == False) or (self.filename == ''):
            print('Select directory and enter a valid filename before saving')
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
            self.update_buttons([self.pushButton_stopStack])
            
            self.print_controller('Stack mode started -- Number of frames to save: '+str(self.number_of_planes))
            
            '''Starting stack mode thread'''
            stack_mode_thread = threading.Thread(target = self.stack_mode_thread)
            stack_mode_thread.start()
    
    def stack_mode_thread(self): ##utliser get_single_image
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
        self.frame_saver = FrameSaver()
        self.frame_saver.set_block_size(3)  #3 buffers allowed in the queue
        self.frame_saver.set_files(self.number_of_planes, self.filename, 'stack', 'ETL_scan')
        
        self.set_data_consumer(self.frame_saver, False, "FrameSaver", True) ###???
        self.frame_saver.start_saving(data_type = 'auto')
        
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
        progress_increment = int(100/self.number_of_planes)
        self.sig_update_progress.emit(0) #To reset progress bar
        
        frame_list = []
        xvals_list = []
        
        for plane in range(int(self.number_of_planes)):
            
            if self.stack_mode_started == False:
                self.print_controller('Acquisition Interrupted')
                break
            else:
                '''Moving sample position'''
                position = self.start_point+plane*self.step
                self.motor_horizontal.move_absolute_position(position,'\u03BCm')  #Position in micro-meters
                self.update_position_horizontal()
                self.frame_saver.add_motor_parameters(self.current_horizontal_position_text,self.current_vertical_position_text,self.current_camera_position_text)
                
                '''Moving the camera to focus'''
                ###self.move_camera_to_focus()   
                
                '''Acquiring the frame '''
                self.ramps.create_tasks(terminals,'FINITE')
                self.ramps.write_waveforms_to_tasks()                            
                self.ramps.start_tasks()
                self.ramps.run_tasks()
                
                '''Retrieving buffer'''
                self.number_of_steps = np.ceil(self.parameters["columns"]/self.parameters["etl_step"]) #Number of galvo sweeps in a frame, or alternatively the number of ETL focal step
                self.buffer = self.camera.retrieve_multiple_images(self.number_of_steps, self.ramps.t_half_period, sleep_timeout = 5)
                
                '''Frame reconstruction for display'''
                frame = self.reconstruct_frame()
                buffer = np.insert(self.buffer, 0, frame, axis=0)
                transp_frame = np.transpose(frame)
                
                xvals_list.append(plane+1) ###changer pour position horizontale?
                frame_list.append(transp_frame.tolist())
                if len(frame_list) > 3 : ##20 #To prevent the list of frames from being too big
                    frame_list.pop(0)
                    xvals_list.pop(0)
                
                frame3d = np.array(frame_list)
                
                xvals = np.array(xvals_list)
                self.camera_window.change_xvals(xvals)
                
                '''Frame display and buffer saving'''
                for ii in range(0, len(self.consumers), 4):
                    if self.consumers[ii+2] == 'CameraWindow':
                        try:
                            self.consumers[ii].put(frame3d)
                            print('Frame put in CameraWindow')
                        except:      #self.consumers[ii].Full:
                            print("CameraWindow queue is full")
                        
                    if self.consumers[ii+2] == 'FrameSaver':
                        try:
                            self.consumers[ii].put(buffer,1)
                            print('Frame put in FrameSaver')
                        except:      #self.consumers[ii].Full:
                            print("FrameSaver queue is full")
                
                '''Ending tasks'''
                self.ramps.stop_tasks()                             
                self.ramps.close_tasks()
                
                '''Update progress bar'''
                progress_value += progress_increment
                self.sig_update_progress.emit(progress_value)
        
        self.sig_update_progress.emit(100) #In case the number of planes is not a multiple of 100
        
        self.camera_window.change_xvals(None) #Return xvals to default
        
        self.laser_on = False
        
        self.frame_saver.stop_saving()
        
        '''Stopping camera'''
        self.camera.cancel_images()
        self.camera.set_recording_state(0)
        self.camera.free_buffer()
                
        '''Stopping laser'''
        self.stop_lasers()
        
        '''Enabling modes after stack mode'''
        self.update_buttons(self.default_buttons)
        
        self.print_controller('Acquisition done')
    
    def stop_stack_mode(self):
        '''Changes the live_mode flag status to end the thread'''
        
        self.stack_mode_started = False
    
    
    '''Calibration Methods'''
    
    def start_calibrate_camera(self):
        '''Initiates camera calibration'''
        
        self.close_modes()
        self.camera_calibration_started = True
       
        '''Modes disabling while stack acquisition'''
        self.update_buttons([self.pushButton_cancelCalibrateCamera])
            
        self.print_controller('Camera calibration started')
            
        '''Starting camera calibration thread'''
        calibrate_camera_thread = threading.Thread(target = self.calibrate_camera_thread)
        calibrate_camera_thread.start()
    
    def calibrate_camera_thread(self):
        ''' Calibrates the camera focus by finding the ideal camera position 
            for multiple sample horizontal positions'''
        
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
        self.parameters["etl_step"] = self.parameters["columns"] #To keep ETL constant, scan only 1 column
        
        self.ramps=AOETLGalvos(self.parameters)
        self.ramps.initialize()
        self.ramps.create_etl_waveforms(case = 'STAIRS')
        self.ramps.create_galvos_waveforms(case = 'TRAPEZE')
        self.ramps.create_digital_output_camera_waveform( case = 'STAIRS_FITTING')
        
        '''Getting calibration parameters'''
        if self.doubleSpinBox_numberOfCalibrationPlanes.value() != 0:
            self.number_of_calibration_planes = self.doubleSpinBox_numberOfCalibrationPlanes.value()
        if self.doubleSpinBox_numberOfCameraPositions.value() != 0:
            self.number_of_camera_positions = self.doubleSpinBox_numberOfCameraPositions.value()
        
        sample_increment_length = (self.horizontal_forward_boundary - self.horizontal_backward_boundary) / self.number_of_calibration_planes
        self.focus_backward_boundary = 245000#int(200000*0.75)#200000#245000#225000#245000#250000 #263000   ##Position arbitraire en u-steps
        self.focus_forward_boundary = 265000#int(300000*25/20)#300000#265000#255000#265000#270000  #269000   ##Position arbitraire en u-steps
        camera_increment_length = (self.focus_forward_boundary - self.focus_backward_boundary) / self.number_of_camera_positions
        
        position_depart_sample = self.motor_horizontal.current_position('\u03BCStep')
        position_depart_camera = self.focus
        
        self.camera_focus_relation = np.zeros((int(self.number_of_calibration_planes),2))
        metricvar=np.zeros((int(self.number_of_camera_positions)))
        self.donnees=np.zeros(((int(self.number_of_calibration_planes)),(int(self.number_of_camera_positions)))) #debugging
        self.popt = np.zeros((int(self.number_of_calibration_planes),3))    #debugging
        
        '''Retrieving filename set by the user''' #debugging
        self.filename = str(self.lineEdit_filename.text())
        if self.saving_allowed and self.filename != '':
            
            self.filename = self.save_directory + '/' + self.filename
            
            '''Setting frame saver'''
            self.frame_saver = FrameSaver()
            self.frame_saver.set_block_size(3) #Block size is a number of buffers
            self.frame_saver.set_files(self.number_of_calibration_planes,self.filename,'cameraCalibration','camera_position')
            '''File attributes'''
            if str(self.lineEdit_sampleName.text()) != '':
                parameters["sample_name"] = str(self.lineEdit_sampleName.text())
            
            '''Starting frame saver'''
            self.frame_saver.start_saving(data_type = 'calib')
        else:
            print('Select directory and enter a valid filename before saving')
        
        for i in range(int(self.number_of_calibration_planes)): #For each sample position
            
            if self.camera_calibration_started == False:
                self.print_controller('Camera calibration interrupted')
                break
            else:
                '''Moving sample position'''
                position = self.horizontal_forward_boundary - (i * sample_increment_length)    #Increments of +sample_increment_length
                self.motor_horizontal.move_absolute_position(position,'\u03BCStep')
                self.update_position_horizontal()
                
                buffer3d_list=[]
                for j in range(int(self.number_of_camera_positions)): #For each camera position
                    '''Moving camera position'''
                    position_camera = self.focus_forward_boundary - (j * camera_increment_length) #Increments of +camera_increment_length
                    self.motor_camera.move_absolute_position(position_camera,'\u03BCStep')
                    time.sleep(0.5) #To make sure the camera is at the right position
                    self.update_position_camera()
                    
                    '''Writing waveform to task and running'''
                    self.ramps.create_tasks(terminals,'FINITE')
                    self.ramps.write_waveforms_to_tasks()                            
                    self.ramps.start_tasks()
                    self.ramps.run_tasks()
                    
                    '''Retrieving buffer'''
                    self.number_of_steps = 1 #To retrieve only one image
                    #self.buffer = self.camera.retrieve_multiple_images(self.number_of_steps, self.ramps.t_half_period, sleep_timeout = 5)
                    self.buffer = self.camera.retrieve_single_image()*1.0
                    buffer_copy = copy.deepcopy(self.buffer)##
                    buffer_copy = np.transpose(buffer_copy)
                    buffer_copy_save = copy.deepcopy(self.buffer)##
                    
                    for ii in range(0, len(self.consumers), 4):
                        if self.consumers[ii+2] == "CameraWindow":
                            try:
                                self.consumers[ii].put(buffer_copy)
                            except self.consumers[ii].Full:
                                print("Queue is full")
                    
                    #'''Frame reconstruction for display'''
                    #frame = self.reconstruct_frame()
                    #
                    #'''Frame display'''
                    #for ii in range(0, len(self.consumers), 4):
                    #    if self.consumers[ii+2] == "CameraWindow":
                    #        try:
                    #            self.consumers[ii].put(buffer_copy[0])
                    #        except:      #self.consumers[i].Full:
                    #            print("Queue is full")
                    

                    '''Retrieving filename set by the user''' #debugging
                    if self.saving_allowed and self.filename != '': #debugging
                        self.frame_saver.add_motor_parameters(self.current_horizontal_position_text,self.current_vertical_position_text,self.current_camera_position_text)
                    
                    buffer3d_list.append(buffer_copy_save)
                    
                    '''Filtering frame'''
                    frame = ndimage.gaussian_filter(self.buffer, sigma=3)
                    flatframe=frame.flatten()
                    metricvar[j]=np.var(flatframe)
                    
                    '''Ending tasks'''
                    self.ramps.stop_tasks()                             
                    self.ramps.close_tasks()
                
                buffer3d = np.array(buffer3d_list)
                if self.saving_allowed and self.filename != '': #debugging
                    '''Saving frame'''
                    self.frame_saver.put(buffer3d,1)
                    print('buffer put in queue ')
                
                '''Calculating ideal camera position'''
                
                metricvar=(metricvar-np.min(metricvar))/(np.max(metricvar)-np.min(metricvar))#normalize
                metricvar = signal.savgol_filter(metricvar, 11, 3) # window size 11, polynomial order 3
                self.donnees[i,:] = metricvar #debugging
                
                n=len(metricvar)
                x=np.arange(n)            
                mean = sum(x*metricvar)/n           
                sigma = sum(metricvar*(x-mean)**2)/n
                poscenter=np.argmax(metricvar)
                print('poscenter:'+str(poscenter))
                
                popt,pcov = optimize.curve_fit(gaussian,x,metricvar,p0=[1,mean,sigma],bounds=(0, 'inf'), maxfev=10000)
                
                amp,center,variance=popt
                self.popt[i] = popt
                print('center:'+str(center)) #debugging
                print('amp:'+str(amp)) #debugging
                print('variance:'+str(variance)) #debugging
                
                '''Saving focus relation'''
                self.camera_focus_relation[i,0] = -self.motor_horizontal.current_position(self.unit) + self.horizontal_correction
                max_variance_camera_position = self.focus_forward_boundary - (center * camera_increment_length)
                self.camera_focus_relation[i,1] = -self.motor_camera.data_to_position(max_variance_camera_position, self.unit) + self.camera_correction
                
            self.print_controller('--Calibration of plane '+str(i+1)+'/'+str(int(self.number_of_calibration_planes))+' done')
        
        print('relation:') #debugging
        print(self.camera_focus_relation)#debugging
        
        if self.saving_allowed and self.filename != '': #debugging
            self.frame_saver.stop_saving()
            self.print_controller('Images saved')
        
        '''Returning sample and camera at initial positions'''
        self.motor_horizontal.move_absolute_position(position_depart_sample,'\u03BCStep')
        self.update_position_horizontal()
        self.motor_camera.move_absolute_position(position_depart_camera,'\u03BCStep')
        self.update_position_camera()
        
        '''Stopping camera'''
        self.camera.cancel_images()
        self.camera.set_recording_state(0)
        self.camera.free_buffer()
        
        '''Stopping lasers'''
        self.stop_lasers()
        self.both_lasers_activated = False
        
        '''Calculating focus'''
        if self.camera_calibration_started == True: #To make sure calibration wasn't stopped before the end
            x = self.camera_focus_relation[:,0]
            y = self.camera_focus_relation[:,1]
            self.slope_camera, self.intercept_camera, r_value, p_value, std_err = stats.linregress(x, y)
            self.calculate_camera_focus()
            
            self.default_buttons.append([self.pushButton_calculateFocus,self.pushButton_showInterpolation])
        
        self.print_controller('Camera calibration done')
            
        '''Enabling modes after camera calibration'''
        self.update_buttons(self.default_buttons)
            
        self.camera_calibration_started = False

    def stop_calibrate_camera(self):
        '''Interrups camera calibration'''
        
        self.camera_calibration_started = False

    
    def start_calibrate_etls(self):
        '''Initiates etls-galvos calibration'''
        
        self.close_modes()
        self.etls_calibration_started = True
       
        '''Modes disabling while stack acquisition'''
        self.update_buttons([self.pushButton_stopEtlsGalvosCalibration])
        
        self.print_controller('ETL calibration started')
        
        '''Starting camera calibration thread'''
        calibrate_etls_thread = threading.Thread(target = self.calibrate_etls_thread)
        calibrate_etls_thread.start()
    
    def calibrate_etls_thread(self):
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
        
        self.galvos_etls_task = nidaqmx.Task()
        self.galvos_etls_task.ao_channels.add_ao_voltage_chan(terminals["galvos_etls"])
        
        '''Getting parameters'''
        self.number_of_etls_points = 20 ##
        self.number_of_etls_images = 10 ##
        
        self.etl_l_relation = np.zeros((int(self.number_of_etls_points),2))
        self.etl_r_relation = np.zeros((int(self.number_of_etls_points),2))
        
        '''Finding relation between etls' voltage and focal point vertical's position'''
        for side in ['etl_l','etl_r']: #For each etl
            '''Parameters'''
            if side == 'etl_l':
                etl_max_voltage = 5 #3.5#4.2      #Volts ##Arbitraire
                etl_min_voltage = 0 #2.5#1.8        #Volts ##Arbitraire
            if side == 'etl_r':
                etl_max_voltage = 5 #3.5#4.2      #Volts ##Arbitraire
                etl_min_voltage = 0 #2.5#1.8        #Volts ##Arbitraire
            etl_increment_length = (etl_max_voltage - etl_min_voltage) / self.number_of_etls_points
            
            '''Starting automatically lasers'''
            if side == 'etl_l':
                self.left_laser_activated = True
            if side == 'etl_r':
                self.right_laser_activated = True
            self.parameters['laser_l_voltage'] = 2.5#2#.2 #Volts
            self.parameters['laser_r_voltage'] = 2.5#2.5 #Volts
            self.start_lasers()
            
            self.camera.retrieve_single_image()*1.0 ##pour éviter images de bruit
            
            self.xdata = np.zeros((int(self.number_of_etls_points),128))
            self.ydata = np.zeros((int(self.number_of_etls_points),128))
            self.popt = np.zeros((int(self.number_of_etls_points),4))
            
            #For each interpolation point
            for j in range(int(self.number_of_etls_points)):
                
                if self.etls_calibration_started == False:
                    self.print_controller('Calibration interrupted')
                    
                    break
                else:
                    '''Getting the data to send to the AO'''
                    right_etl_voltage = etl_min_voltage + (j * etl_increment_length) #Volts
                    left_etl_voltage = etl_min_voltage + (j * etl_increment_length) #Volts
                    
                    left_galvo_voltage = 0 #Volts
                    right_galvo_voltage = 0.1 #Volts
                    
                    '''Writing the data'''
                    galvos_etls_waveforms = np.stack((np.array([right_galvo_voltage]),
                                                              np.array([left_galvo_voltage]),
                                                              np.array([left_etl_voltage]),
                                                              np.array([right_etl_voltage])))
                    self.galvos_etls_task.write(galvos_etls_waveforms, auto_start=True)
                   
                    '''Retrieving buffer for the plane of the current position'''
                    self.ramps=AOETLGalvos(self.parameters)
                    self.ramps.initialize()
                    self.number_of_steps = 1
                    self.buffer = self.camera.retrieve_multiple_images(self.number_of_steps, self.ramps.t_half_period, sleep_timeout = 5) #debugging
                    self.save_single_image() #debugging
                    
                    ydatas = np.zeros((self.number_of_etls_images,128))  ##128=K
                    
                    #For each image
                    for y in range(self.number_of_etls_images):
                        '''Retrieving image from camera and putting it in its queue
                               for display'''
                        frame = self.camera.retrieve_single_image()*1.0
                        blurred_frame = ndimage.gaussian_filter(frame, sigma=20)
                        
                        frame = np.transpose(frame)
                        blurred_frame = np.transpose(blurred_frame)
                        
                        for ii in range(0, len(self.consumers), 4):
                            if self.consumers[ii+2] == "CameraWindow":
                                #Initial frame
                                try:
                                    self.consumers[ii].put(frame)
                                except self.consumers[ii].Full:
                                    print("Queue is full")
                                #Blurred frame
                                try:
                                    self.consumers[ii].put(blurred_frame)
                                except self.consumers[ii].Full:
                                    print("Queue is full")
                        
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
                        ydatas[y,:] = signal.savgol_filter(ydata, 51, 3) # window size 51, polynomial order 3
                    
                    #Calculate fit for average of images
                    xdata=np.linspace(0,width-1,K)
                    good_ydata=np.mean(ydatas,0)
                    popt, pcov = optimize.curve_fit(func, xdata, good_ydata,bounds=((0.5,0,0,0),(np.inf,np.inf,np.inf,np.inf)), maxfev=10000) #,bounds=(0,np.inf) #,bounds=((0,-np.inf,-np.inf,0),(np.inf,np.inf,np.inf,np.inf))
                    beamWidth,focusLocation,rayleighRange,offset = popt
                    
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
                        self.xdata[j]=xdata
                        self.ydata[j]=good_ydata
                        self.popt[j]=popt
                    
                    '''Saving relations'''
                    if side == 'etl_l':
                        self.etl_l_relation[j,0] = left_etl_voltage
                        self.etl_l_relation[j,1] = int(focusLocation)
                    if side == 'etl_r':
                        self.etl_r_relation[j,0] = right_etl_voltage
                        self.etl_r_relation[j,1] = int(focusLocation)
                
                    self.print_controller('--Calibration of plane '+str(j+1)+'/'+str(self.number_of_etls_points)+' for '+side+' done')
            
            '''Closing lasers after calibration of each side'''    
            self.left_laser_activated = False
            self.right_laser_activated = False
        
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
        self.camera.cancel_images()
        self.camera.set_recording_state(0)
        self.camera.free_buffer()
        
        '''Ending tasks'''
        self.galvos_etls_task.stop()
        self.galvos_etls_task.close()
        
        '''Stopping lasers'''
        self.stop_lasers()
        self.both_lasers_activated = False
        
        if self.etls_calibration_started == True: #To make sure calibration wasn't stopped before the end
            self.default_buttons.append([self.pushButton_showEtlInterpolation])
            self.etls_calibrated = True
        
        self.print_controller('Calibration done')
            
        '''Enabling modes after camera calibration'''
        self.update_buttons(self.default_buttons)
            
        self.etls_calibration_started = False

    def stop_calibrate_etls(self):
        '''Interrups elts-galvos calibration'''
        
        self.etls_calibration_started = False

class CameraWindow(queue.Queue):
    '''Class for image display'''
    
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
        
        queue.Queue.__init__(self,2)   #Set up queue of maxsize 2 (frames)
        
        self.histogram_level = []
        self.xvals = None
        
        '''Set up display window'''
        self.plot_item = pg.PlotItem()
        self.imv = pg.ImageView(view = self.plot_item)
        self.imv.setWindowTitle('Camera Window')
        self.scene = self.imv.scene
        self.imv.show()
        #Initial displayed frame 
        self.lines = 2160
        self.columns = 2560
        self.container = np.zeros((self.lines, self.columns))
        self.container[0] = 1000 #To get initial range of the histogram 
        self.imv.setImage(np.transpose(self.container))
    
    def change_xvals(self,xvals):
        '''Change the number of frames to display in the window'''
        
        self.xvals = xvals
    
    def put(self, item, block=True, timeout=None):
        '''Put an image in the display queue'''
        
        if queue.Queue.full(self) == False: 
            queue.Queue.put(self, item, block=block, timeout=timeout)
                 
    def update(self):
        '''Executes at each interval of the QTimer set in test_galvo.py
           Takes the image in its queue and displays it in the window'''
        try:
            '''Retrieving old view settings'''
            _view = self.imv.getView()
            _view_box = _view.getViewBox()
            _state = _view_box.getState()
            
            first_update = False
            if self.histogram_level == []:
                first_update = True
            _histo_widget = self.imv.getHistogramWidget()
            self.histogram_level = _histo_widget.getLevels()
            
            '''Retrieving and displaying new frame'''
            frame = self.get(False)
            self.imv.setImage(frame,xvals = self.xvals)
            
            '''Showing saturated pixels in red'''
            saturated_pixels = np.array(np.where(frame>=65335)) #65535 is the max intensity value that the camera can output (2^16-1)
            saturated_pixels = saturated_pixels + 0.5 #To make sure red pixels are at the right position...
            saturated_pixels_list = saturated_pixels.tolist()
            self.plot_item.plot(saturated_pixels_list[0],saturated_pixels_list[1],pen=None,symbolBrush=(255,0,0),symbol='s',symbolSize=1,pxMode=False)
            
            '''Keeping old view settings with new image'''
            _view_box.setState(_state)
            if not first_update: #To keep the histogram setting with image refresh
                _histo_widget.setLevels(self.histogram_level[0],self.histogram_level[1])
        
        except queue.Empty:
            pass
        

class FrameSaver():
    '''Class for storing buffers (images) in its queue and saving them 
       afterwards in a specified directory in a HDF5 format'''
    
    '''Set up methods'''
    
    def __init__(self):
        self.filenames_list = [] 
        self.number_of_files = 1
        self.data_type = 'auto'
        
        self.horizontal_positions_list = []
        self.vertical_positions_list = []
        self.camera_positions_list = []
    
    def add_motor_parameters(self,current_hor_position_txt,current_ver_position_txt,current_cam_position_txt):
        '''Add to a list the different motor positions'''
        
        self.horizontal_positions_list.append(current_hor_position_txt)
        self.vertical_positions_list.append(current_ver_position_txt)
        self.camera_positions_list.append(current_cam_position_txt)
    
    def set_files(self,number_of_files, files_name, scan_type, datasets_name):
        '''Set the number and name of files to save and makes sure the filenames 
        are unique in the path to avoid overwrite on other files'''
        
        self.number_of_files = number_of_files
        self.files_name = files_name
        self.datasets_name = datasets_name
        
        counter = 0
        for _ in range(int(self.number_of_files)):
            in_loop = True
            while in_loop:
                counter += 1
                new_filename = self.files_name + '_' + scan_type + '_plane_'+u'%05d'%counter+'.hdf5'
                
                if os.path.isfile(new_filename) == False: #Check for existing files
                    in_loop = False
                    self.filenames_list.append(new_filename)
        print(self.filenames_list)
    
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
    
    def set_path_root(self): ###pas utilisé???
        scan_date = str(datetime.date.today())
        self.path_root = posixpath.join('/', scan_date) 
    
    
    '''Saving methods'''
    
    def put(self, value, flag):
        '''Put an image in the save queue'''
        
        self.queue.put(value, flag)
    
    def check_existing_files(self, filename, number_of_planes, scan_type, data_type = 'BUFFER'):
        '''Makes sure the filenames are unique in the path to avoid overwrite on
           other files'''
        
        if data_type == "BUFFER":
            number_of_files = number_of_planes ##éventuellement à changer
        else:
            number_of_files = np.ceil(number_of_planes/self.block_size)
        
        counter = 0
        for _ in range(int(number_of_files)):
            in_loop = True
            while in_loop:
                counter += 1
                new_filename = filename + '_' + scan_type + '_plane_'+u'%05d'%counter+'.hdf5'
                
                if os.path.isfile(new_filename) == False:
                    in_loop = False
                    self.filenames_list.append(new_filename)
    
    def start_saving(self, data_type):
        '''Initiates saving thread'''
        
        self.saving_started = True
        self.data_type = data_type
        
        frame_saver_thread = threading.Thread(target = self.save_thread)
        frame_saver_thread.start()
        
        ##if data_type == '2D_ARRAY':
        ##    frame_saver_thread = threading.Thread(target = self.save_thread)
        ##    frame_saver_thread.start()
        ##elif data_type == 'BUFFER':
        ##    frame_saver_thread = threading.Thread(target = self.save_thread_buffer)
        ##    frame_saver_thread.start()
        ##elif data_type == 'TESTS':
        ##    frame_saver_thread = threading.Thread(target = self.save_thread_for_tests)
        ##    frame_saver_thread.start()
    
    def save_thread(self):
        '''Thread for saving 3D arrays (or 2D arrays). 
            The number of datasets per file is the number of 2D arrays'''
        
        for file in range(len(self.filenames_list)):
            '''Create file'''
            f = h5py.File(self.filenames_list[file],'a')
            ###self.f.create_group(self.path_name)   #Create sub-group (folder)
            
            counter = 1
            in_loop = True
            while in_loop:
                try:
                    '''Retrieve buffer'''
                    buffer = self.queue.get(True,1)
                    #print('Buffer received') #debugging
                    if buffer.ndim == 2:
                        buffer = np.expand_dims(buffer, axis=0) #To consider 2D arrays as a 3D arrays
                    
                    for frame in range(buffer.shape[0]): #For each 2D frame
                        '''Create dataset'''
                        if self.data_type == 'auto' and frame == 0: #If first frame is reconstructed
                            path_root = 'reconstructed_frame'
                            counter -= 1
                        else:
                            path_root = self.datasets_name+u'%03d'%counter
                        dataset = f.create_dataset(path_root, data = buffer[frame,:,:])
                        #print('Dataset created:'+str(path_root)) #debugging
                        
                        '''Add attributes'''
                        dataset.attrs['Sample'] = parameters["sample_name"]
                        dataset.attrs['Current sample horizontal position'] = self.horizontal_positions_list[frame]
                        dataset.attrs['Current sample vertical position'] = self.vertical_positions_list[frame]
                        dataset.attrs['Current camera horizontal position'] = self.camera_positions_list[frame]
                        for param_string in modifiable_parameters:
                            dataset.attrs[param_string]=parameters[param_string]
                        
                        counter += 1
                    in_loop = False
                except:
                    #print('No buffer') #debugging
                    if self.saving_started == False: #To stop searching for buffers
                        in_loop = False
            f.close()
            print('File '+self.filenames_list[file]+' saved')
    
    def old_save_thread(self): ##Enlever
        '''Thread for 2D array saving (kind of useless, we can always use
           self.save_thread_buffer even with a a 2D array)'''
        
        self.saving_started = True
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
                            dataset = f.create_dataset(path_root, data = buffer[:,:,ii])
                            
                            counter = counter + 1
                        
                        in_loop = False
                        #self.child_conn.send([i, self.queue.qsize()])
                        
                except:
                    print('No frame')
                    
                    if self.saving_started == False:
                        in_loop = False
                        
            if frame_number !=0:
                buffer2 = np.zeros((frame.shape[0], frame.shape[1], frame_number+1))
                buffer2 = buffer[:,:,0:frame_number]
                
                for ii in range(frame_number):
                    path_root = self.path_root+'_'+u'%05d'%counter
                    f.create_dataset(path_root, data = buffer2[:,:,ii])
                    counter = counter +1
            
            f.close()
            
    def save_thread_buffer(self): ###
        '''Thread for buffer saving'''
        self.saving_started = True
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
                        self.dataset = f.create_dataset(path_root, data = buffer[ii,:,:])
                        
                        '''Add attributes'''
                        self.add_attribute('Sample', parameters["sample_name"])
                        self.add_attribute('Current sample horizontal position', self.current_horizontal_position_txt )
                        self.add_attribute('Current sample vertical position', self.current_vertical_position_txt)
                        self.add_attribute('Current camera horizontal position', self.current_camera_position_txt)
                        
                        for param_string in modifiable_parameters:
                            self.add_attribute(param_string, parameters[param_string])
                        
                        counter += 1
                        
                    in_loop = False
                
                except:
                    print('No buffer')
                    
                    if self.saving_started == False:
                        in_loop = False
            
            f.close()
    
    def save_thread_for_tests(self): ##
        '''Thread for buffer saving'''
        self.saving_started = True
        for i in range(len(self.filenames_list)):
            
            f = h5py.File(self.filenames_list[i],'a')
            
            counter = 1
            for _ in range(self.number_of_datasets):
                in_loop = True
                    
                while in_loop:
                    try:
                        buffer = self.queue.get(True,1)
                        print('Buffer received \n')
                        
                        for ii in range(1): #buffer.shape[0] ##si retrieve multiple an lieu de single
                            path_root = 'camera_position'+u'%03d'%counter
                            dataset = f.create_dataset(path_root, data = buffer[:,:])  #buffer[ii,:,:] ##
                            
                            '''Attributes'''
                            dataset.attrs['Sample'] = parameters["sample_name"]
                            dataset.attrs['Current sample horizontal position'] = self.current_horizontal_position_txt
                            dataset.attrs['Current sample vertical position'] = self.current_vertical_position_txt
                            dataset.attrs['Current camera horizontal position'] = self.current_camera_position_txt
                            
                            for param_string in modifiable_parameters:
                                dataset.attrs[param_string]=parameters[param_string]
                            
                        in_loop = False
                    
                    except:
                        print('No buffer')
                        
                        if self.saving_started == False:
                            in_loop = False
                
                counter += 1
                
            f.close()
            
    def stop_saving(self):
        '''Changes the flag status to end the saving thread'''
        
        self.saving_started = False


#def save_process(queue, filenames_list, path_root, block_size, conn):    ##enlever
#    '''Old version version of the thread saving function. Not in use.'''
#    
#    for i in range(len(filenames_list)):
#        
#        f = h5py.File(filenames_list[i],'a')
#        frame_number = 0
#        in_loop = True
#        
#        while in_loop:
#            try:
#                frame = queue.get(True,1)
#                print('Frame received')
#                
#                if frame_number == 0:
#                    buffer = np.zeros((frame.shape[0],frame.shape[1],block_size))
#                
#                buffer[:,:,frame_number] = frame
#                frame_number = (frame_number+1) % block_size
#                
#                '''Executes when block_size is reached'''
#                if frame_number == 0:
#                    for ii in range(block_size):
#                        f.create_dataset(path_root, data = buffer[:,:,ii])
#                    
#                    in_loop = False
#                    conn.send([i, queue.qsize()])
#                    
#            except:
#                print('No frame')
#                
#                if conn.poll():
#                    print('Checking connection status')
#                    in_loop = conn.recv()[0]
#                    
#        if frame_number !=0:
#            buffer2 = np.zeros((frame.shape[0], frame.shape[1], frame_number+1))
#            buffer2 = buffer[:,:,0:frame_number]
#            
#            for ii in range(frame_number):
#                f.create_dataset(path_root, data = buffer2[:,:,ii])
#        
#        f.close()

