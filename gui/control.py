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

from functools import partial
import pyqtgraph as pg
#import ctypes
import copy

import nidaqmx
#from nidaqmx.constants import AcquisitionType
from PIL import Image
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

'''Parameters'''
etl_parameters = ["etl_l_amplitude","etl_r_amplitude","etl_l_offset","etl_r_offset"]
galvo_parameters = ["galvo_l_amplitude","galvo_r_amplitude","galvo_l_offset","galvo_r_offset","galvo_l_frequency","galvo_r_frequency"]
laser_parameters = ["laser_l_voltage","laser_r_voltage"]
modifiable_parameters = etl_parameters + galvo_parameters + ["samplerate","etl_step"] + laser_parameters

parameters = dict()
'''Read modifiable parameters from configuration file'''
with open(r"C:\git-projects\lightsheet\src\configuration.txt") as file:
    for param_string in modifiable_parameters:
        parameters[param_string] = float(file.readline())
'''Default parameters'''
parameters["sample_name"]='No Sample Name'
parameters["sweeptime"]=0.4             # In seconds
parameters["columns"] = 2560            # In pixels
parameters["rows"] = 2160               # In pixels
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
    
    def __init__(self):
        QWidget.__init__(self)
        
        '''Loading user interface'''
        basepath= os.path.join(os.path.dirname(__file__))
        uic.loadUi(os.path.join(basepath,"control.ui"), self)
        
        '''Instantiating the camera window where the frames are displayed'''
        self.camera_window = CameraWindow()
        
        '''Instantiating the hardware components'''
        self.motor_vertical = Motors(1, 'COM3')    #Vertical motor
        self.motor_horizontal = Motors(2, 'COM3')  #Horizontal motor for sample motion
        self.motor_camera = Motors(3, 'COM3')      #Horizontal motor for camera motion (detection arm)
        
        self.open_camera()
        
        '''Defining attributes'''
        self.parameters = copy.deepcopy(parameters)
        self.defaultParameters = copy.deepcopy(parameters)
        
        self.consumers = []
        self.figure_counter = 1
        self.save_directory = ''
        
        self.default_buttons = [self.pushButton_standbyOn,
                                self.pushButton_getSingleImage,
                                self.pushButton_startPreviewMode,
                                self.pushButton_startLiveMode,
                                self.pushButton_startStack,
                                self.pushButton_calibrateCamera,
                                self.pushButton_calibrateEtlsGalvos]
        etl_voltages_boxes = [self.doubleSpinBox_leftEtlAmplitude,
                                self.doubleSpinBox_rightEtlAmplitude,
                                self.doubleSpinBox_leftEtlOffset,
                                self.doubleSpinBox_rightEtlOffset]
        galvo_voltages_boxes = [self.doubleSpinBox_leftGalvoAmplitude,
                                  self.doubleSpinBox_rightGalvoAmplitude,
                                  self.doubleSpinBox_leftGalvoOffset,
                                  self.doubleSpinBox_rightGalvoOffset]
        galvo_frequencies_boxes = [self.doubleSpinBox_leftGalvoFrequency,
                                     self.doubleSpinBox_rightGalvoFrequency]
        laser_boxes = [self.doubleSpinBox_leftLaser,
                         self.doubleSpinBox_rightLaser]
        
        self.modifiable_param_boxes = etl_voltages_boxes + galvo_voltages_boxes + galvo_frequencies_boxes + [self.doubleSpinBox_samplerate,self.spinBox_etlStep] + laser_boxes 
        
        '''Default ETL relation values'''###Test
        self.left_slope = -0.001282893174259485
        self.left_intercept = 4.920315064788371
        self.right_slope = 0.0013507132995247916
        self.right_intercept = 1.8730880902476752
        
        '''Arbitrary default positions (in micro-steps)'''
        self.boundaries = dict()
        self.boundaries['vertical_up_boundary'] = 19.4
        self.boundaries['vertical_down_boundary'] = 0
        self.boundaries['origin_vertical'] = self.boundaries['vertical_down_boundary']
        self.boundaries['horizontal_forward_boundary'] = 0
        self.boundaries['horizontal_backward_boundary'] = 10
        self.boundaries['origin_horizontal'] = self.boundaries['horizontal_forward_boundary']
        self.boundaries['camera_forward_boundary'] = 30
        self.boundaries['camera_backward_boundary'] = 115
        self.boundaries['focus'] = 40 ###
        self.defaultBoundaries = copy.deepcopy(self.boundaries) #The default boundaries are in mm
        
        '''Initializing flags'''
        self.both_lasers_activated = False
        self.left_laser_activated = False
        self.right_laser_activated = False
        self.laser_on = False
        
        self.standby = False
        self.preview_mode_started = False
        self.live_mode_started = False
        self.stack_mode_started = False
        self.camera_on = False
        
        self.saving_allowed = False
        self.camera_calibration_started = False
        self.etls_calibration_started = False
        
        self.horizontal_forward_boundary_selected = False
        self.horizontal_backward_boundary_selected = False
        self.focus_selected = False
        
        '''Initializing the properties of the widgets'''
        '''--Motion's related widgets--'''
        self.comboBox_unit.insertItems(0,["cm","mm","\u03BCm"])
        self.comboBox_unit.setCurrentIndex(1) #Default unit in millimeters
        
        '''--ETLs and galvos parameters' related widgets--'''
        '''Initialize maximum and minimum values; suffixes; step values'''
        for box in etl_voltages_boxes:
            box.setMaximum(5)
            box.setSingleStep(0.1)
            box.setSuffix(" V")
        for box in galvo_voltages_boxes:
            box.setMaximum(10)
            box.setMinimum(-10)
            box.setSingleStep(0.1)
            box.setSuffix(" V")
        for box in galvo_frequencies_boxes:
            box.setMaximum(130) #corresponds to an exposure time of 3.8462 ms
            box.setMinimum(5) #corresponds to an exposure time of 100ms
            box.setSuffix(" Hz")
        for box in laser_boxes:
            box.setMaximum(2.5)
            box.setSingleStep(0.1)
            box.setSuffix(" V")
        self.doubleSpinBox_samplerate.setMaximum(1000000)
        self.doubleSpinBox_samplerate.setMinimum(1)
        self.doubleSpinBox_samplerate.setSuffix(" samples/s")
        self.spinBox_etlStep.setMaximum(2560)
        self.spinBox_etlStep.setMinimum(1)
        self.spinBox_etlStep.setSuffix(" columns")
        
        '''Initialize values'''
        self.back_to_default_parameters()
        
        '''Initializing every other widget that are updated by a change of unit 
            (the motion tab)'''
        self.update_unit()
        
        '''Initialize calibration boxes'''
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
        
        '''Initializing widgets' connections'''
        self.sig_update_progress.connect(self.progressBar_stackMode.setValue)
        
        '''Disable some buttons'''
        buttons_to_disable = [self.lineEdit_filename,
                              self.lineEdit_sampleName,
                              self.pushButton_selectDataset,
                              self.checkBox_setStartPoint,
                              self.checkBox_setEndPoint,
                              self.pushButton_setForwardLimit,
                              self.pushButton_setBackwardLimit,
                              self.pushButton_lasersOff,
                              self.pushButton_leftLaserOff,
                              self.pushButton_rightLaserOff]
        for button in buttons_to_disable:
            button.setEnabled(False)
        self.update_buttons_modes(self.default_buttons)
        
        '''Connect buttons'''
        '''Connection for unit change'''
        self.comboBox_unit.currentTextChanged.connect(self.update_unit)
        
        '''Connection for data saving'''
        self.pushButton_selectDirectory.clicked.connect(self.select_directory)
        
        self.pushButton_selectFile.clicked.connect(self.select_file)
        self.pushButton_selectDataset.clicked.connect(self.select_dataset)
        
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
        self.pushButton_showCamInterpolation.pressed.connect(self.show_camera_interpolation)
        
        self.pushButton_calibrateEtlsGalvos.pressed.connect(self.start_calibrate_etls)
        self.pushButton_stopEtlsGalvosCalibration.pressed.connect(self.stop_calibrate_etls)
        self.pushButton_showEtlInterpolation.pressed.connect(self.show_etl_interpolation)
        
        '''Connections for the ETLs and Galvos parameters'''
        for param_string,param_box in zip(modifiable_parameters,self.modifiable_param_boxes):
            param_box.valueChanged.connect(lambda _,parameter_name=param_string,parameter_box=param_box: self.update_etl_galvos_parameters(parameter_name,parameter_box)) 
            #The parameter '_' (the box signal, a float number) is necessary because the first lambda parameter is always overwritten by the signal return
        
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

    
    '''General Methods'''
    
    def update_buttons_modes(self,buttons_to_enable):
        '''Update mode buttons status : disable buttons, except for those specified to be enabled'''
        
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
                              self.pushButton_cancelCalibrateCamera,
                              self.pushButton_calculateFocus,
                              self.pushButton_showCamInterpolation,
                              self.pushButton_calibrateEtlsGalvos,
                              self.pushButton_stopEtlsGalvosCalibration,
                              self.pushButton_showEtlInterpolation]
        for button in aquisition_buttons:
            if button in buttons_to_enable:
                button.setEnabled(True)
            else:
                button.setEnabled(False)
    
    def close_modes(self):
        '''Close all thread modes if they are active'''

        if self.laser_on:
            self.stop_lasers()
        if self.preview_mode_started:
            self.stop_preview_mode()
        if self.live_mode_started:
            self.stop_live_mode()
        if self.stack_mode_started:
            self.stop_stack_mode()
        if self.standby:
            self.stop_standby()
        if self.camera_calibration_started:
            self.stop_calibrate_camera()
        if self.etls_calibration_started:
            self.stop_calibrate_etls()
    
    def closeEvent(self, event):
        '''Making sure that everything is closed when the user exits the software.
           This function executes automatically when the user closes the UI.
           This is an intrinsic function name of Qt, don't change the name even 
           if it doesn't follow the naming convention'''
        
        self.close_modes()
        if self.camera_on:
            self.close_camera()
        
        event.accept()
    
    def print_controller(self,text):
        '''Print text in console and in controller text box'''
        
        print(text)
        self.label_lastCommands.setText(self.label_lastCommands.text()+'\n '+text)
    
    def open_camera(self):
        '''Opens the camera'''
        
        self.camera_on = True
        self.camera = Camera()
        
        self.print_controller('Camera opened')
    
    def close_camera(self):
        '''Closes the camera'''
        
        self.camera_on = False
        self.camera.close_camera()
        
        self.print_controller('Camera closed')
    
    def start_camera_recording(self,trigger_mode):
        '''Starts camera recording with certain settings'''
        
        self.camera.set_trigger_mode(trigger_mode)
        self.camera.arm_camera() 
        self.camera.get_sizes() 
        self.camera.allocate_buffer() 
        self.camera.set_recording_state(1)
        self.camera.insert_buffers_in_queue()
    
    def stop_camera_recording(self):
        '''Stops camera recording'''
        
        self.camera.cancel_images()
        self.camera.set_recording_state(0)
        self.camera.free_buffer()
    
    def set_data_consumer(self, consumer, wait, consumer_type, update_flag):
        ''' Regroups all the consumers in the same list'''
        
        self.consumers.append(consumer)
        self.consumers.append(wait)             ###Pas implémenté
        self.consumers.append(consumer_type)    
        self.consumers.append(update_flag)      ###Pas implémenté
    
    
    '''Motion Methods'''
    
    def update_unit(self):
        '''Updates all the widgets of the motion tab after an unit change'''
        
        self.unit = self.comboBox_unit.currentText()
        
        for boundary_name in self.boundaries:
            self.boundaries[boundary_name] = self.defaultBoundaries[boundary_name]
            if self.unit == 'cm':
                self.boundaries[boundary_name] /= 10
            elif self.unit == '\u03BCm':
                self.boundaries[boundary_name] *= 1000
        
        if self.unit == 'cm':
            self.decimals = 4
            self.horizontal_correction = 8.2#10.16  #Horizontal correction to fit choice of axis
            self.vertical_correction = -3.1#1.0      #Vertical correction to fit choice of axis
            self.camera_sample_min_distance = 1.5   #Approximate minimal horizontal distance between camera
            self.camera_correction = 7.525 + 4.0 #9.525  #Camera correction to fit choice of axis
        elif self.unit == 'mm':
            self.decimals = 3
            self.horizontal_correction = 82#101.6      #Correction to fit choice of axis
            self.vertical_correction = -31#10.0         #Correction to fit choice of axis
            self.camera_sample_min_distance = 15   #Approximate minimal horizontal distance between camera
            self.camera_correction = 75.25 + 40.0  #95.25     #Camera correction to fit choice of axis
        elif self.unit == '\u03BCm':
            self.decimals = 0
            self.horizontal_correction = 82000#101600     #Correction to fit choice of axis
            self.vertical_correction = -31000#10000        #Correction to fit choice of axis
            self.camera_sample_min_distance = 15000   #Approximate minimal horizontal distance between camera
            self.camera_correction = 75250 + 40000#95250    #Camera correction to fit choice of axis
        
        increment_boxes = [self.doubleSpinBox_incrementHorizontal,
                      self.doubleSpinBox_incrementVertical,
                      self.doubleSpinBox_incrementCamera]
        position_boxes = [self.doubleSpinBox_choosePosition,
                      self.doubleSpinBox_chooseHeight,
                      self.doubleSpinBox_chooseCamera]
        unit_boxes = increment_boxes + position_boxes
        
        '''Update suffixes'''
        for box in unit_boxes:
            box.setSuffix(" {}".format(self.unit))
            box.setDecimals(self.decimals)
        for box in increment_boxes:
            box.setMinimum(10**-self.decimals)
            box.setValue(1)
        
        '''Update maximum and minimum values for horizontal sample motion'''
        self.doubleSpinBox_choosePosition.setMinimum(self.boundaries['horizontal_forward_boundary'])
        self.doubleSpinBox_choosePosition.setMaximum(self.boundaries['horizontal_backward_boundary'])
        maximum_horizontal_increment = self.boundaries['horizontal_backward_boundary'] - self.boundaries['horizontal_forward_boundary']
        self.doubleSpinBox_incrementHorizontal.setMaximum(maximum_horizontal_increment)
        
        '''Update maximum and minimum values for vertical sample motion'''
        self.doubleSpinBox_chooseHeight.setMinimum(self.boundaries['vertical_up_boundary'])
        self.doubleSpinBox_chooseHeight.setMaximum(self.boundaries['vertical_down_boundary'])
        maximum_vertical_increment = self.boundaries['vertical_up_boundary'] - self.boundaries['vertical_down_boundary']
        self.doubleSpinBox_incrementVertical.setMaximum(maximum_vertical_increment)
        
        '''Update maximum and minimum values for camera motion'''
        self.doubleSpinBox_chooseCamera.setMinimum(self.boundaries['camera_forward_boundary'])
        self.doubleSpinBox_chooseCamera.setMaximum(self.boundaries['camera_backward_boundary'])
        maximum_camera_increment = self.boundaries['camera_backward_boundary'] - self.boundaries['camera_forward_boundary']
        self.doubleSpinBox_incrementCamera.setMaximum(maximum_camera_increment)
        
        '''Update current positions'''
        self.update_position_vertical()
        self.update_position_horizontal()
        self.update_position_camera()
    
    def return_current_horizontal_position(self):
        '''Returns the current horizontal position with respect to the choice of axis'''
        return round(-self.motor_horizontal.current_position(self.unit)+self.horizontal_correction,self.decimals) #Minus sign and correction to fit choice of axis
    
    def return_current_vertical_position(self):
        '''Returns the current vertical position with respect to the choice of axis'''
        return round(self.motor_vertical.current_position(self.unit)+self.vertical_correction,self.decimals) #Minus sign and correction to fit choice of axis
    
    def return_current_camera_position(self):
        '''Returns the current camera position with respect to the choice of axis'''
        return round(-self.motor_camera.current_position(self.unit)+self.camera_correction,self.decimals) #Minus sign and correction to fit choice of axis
    

    def update_position_horizontal(self):
        '''Updates the current horizontal sample position displayed'''
        self.current_horizontal_position_text = "{} {}".format(self.return_current_horizontal_position(), self.unit)
        self.label_currentHorizontalNumerical.setText(self.current_horizontal_position_text)
    
    def update_position_vertical(self):
        '''Updates the current vertical sample position displayed'''
        self.current_vertical_position_text = "{} {}".format(self.return_current_vertical_position(), self.unit)
        self.label_currentHeightNumerical.setText(self.current_vertical_position_text)
        
    def update_position_camera(self):
        '''Updates the current (horizontal) camera position displayed'''
        self.current_camera_position_text = "{} {}".format(self.return_current_camera_position(), self.unit)
        self.label_currentCameraNumerical.setText(self.current_camera_position_text)
    
    
    def move_to_horizontal_position(self):
        '''Moves the sample to a specified horizontal position'''

        if (self.return_current_camera_position() - self.doubleSpinBox_choosePosition.value()) >= self.camera_sample_min_distance:  #To prevent the sample from hitting the camera
            self.print_controller('Sample moving to horizontal position')
            horizontal_position = -self.doubleSpinBox_choosePosition.value() + self.horizontal_correction
            self.motor_horizontal.move_absolute_position(horizontal_position,self.unit)
            self.update_position_horizontal()
        else:
            self.print_controller('Camera prevents sample movement')
    
    def move_to_vertical_position(self):
        '''Moves the sample to a specified vertical position'''
        
        self.print_controller ('Sample moving to vertical position')
        vertical_position = self.doubleSpinBox_chooseHeight.value() - self.vertical_correction #Minus sign and correction to fit choice of axis
        self.motor_vertical.move_absolute_position(vertical_position,self.unit)
        self.update_position_vertical()
    
    def move_camera_to_position(self):
        '''Moves the sample to a specified vertical position'''
        
        if (self.doubleSpinBox_chooseCamera.value() - self.return_current_horizontal_position() >= self.camera_sample_min_distance):  #To prevent the sample from hitting the camera
            self.print_controller ('Camera moving to position')
            camera_position = -self.doubleSpinBox_chooseCamera.value() + self.camera_correction #Minus sign and correction to fit choice of axis
            self.motor_camera.move_absolute_position(camera_position,self.unit)
            self.update_position_camera()
        else:
            self.print_controller('Sample prevents camera movement')
    
    def move_camera_backward(self):
        '''Camera motor backward horizontal motion'''
        
        if self.return_current_camera_position() - self.doubleSpinBox_incrementCamera.value() <= self.boundaries['camera_backward_boundary']:
            self.print_controller ('Camera moving backward')
            self.motor_camera.move_relative_position(-self.doubleSpinBox_incrementCamera.value(),self.unit)
        else:
            self.print_controller('Out of boundaries')
            self.motor_camera.move_absolute_position(-self.boundaries['camera_backward_boundary']+self.camera_correction,'\u03BCStep')
        self.update_position_camera()
    
    def move_camera_forward(self):
        '''Camera motor forward horizontal motion'''
        
        if self.return_current_camera_position() - self.doubleSpinBox_incrementCamera.value() >= self.boundaries['camera_forward_boundary']:
            next_camera_position = self.return_current_camera_position() - self.doubleSpinBox_incrementCamera.value()
            if (next_camera_position - self.return_current_horizontal_position() >= self.camera_sample_min_distance):  #To prevent the sample from hitting the camea
                self.print_controller ('Camera moving forward')
                self.motor_camera.move_relative_position(self.doubleSpinBox_incrementCamera.value(),self.unit)
            else:
                self.print_controller('Sample prevents camera movement')
        else:
            self.print_controller('Out of boundaries')
            self.motor_camera.move_absolute_position(-self.boundaries['camera_forward_boundary']+self.camera_correction,self.unit)
        self.update_position_camera()
    
    def move_camera_to_focus(self):
        '''Moves camera to focus position'''
        
        if self.focus_selected:
            if self.boundaries['focus'] > self.boundaries['camera_backward_boundary']:
                self.print_controller('Focus out of boundaries')
                self.motor_camera.move_absolute_position(-self.boundaries['camera_backward_boundary']+self.camera_correction,self.unit)
            elif self.boundaries['focus'] < self.boundaries['camera_forward_boundary']:
                self.print_controller('Focus out of boundaries')
                self.motor_camera.move_absolute_position(-self.boundaries['camera_forward_boundary']+self.camera_correction,self.unit)
            else:
                if (self.boundaries['focus'] - self.return_current_horizontal_position() >= self.camera_sample_min_distance):  #To prevent the sample from hitting the camea
                    self.print_controller('Moving to focus')
                    self.motor_camera.move_absolute_position(-self.boundaries['focus']+self.camera_correction,self.unit)
                else:
                    self.print_controller('Sample prevents camera movement')
        else:
            self.print_controller('Focus not yet set. Moving camera to default focus')
            self.motor_camera.move_absolute_position(-self.boundaries['focus']+self.camera_correction,self.unit)
        self.update_position_camera()
    
    def move_sample_down(self):
        '''Sample motor downward vertical motion'''
        
        if self.return_current_vertical_position() - self.doubleSpinBox_incrementVertical.value() >= self.boundaries['vertical_down_boundary']:
            self.print_controller('Sample moving down')
            self.motor_vertical.move_relative_position(self.doubleSpinBox_incrementVertical.value(),self.unit)
        else:
            self.print_controller('Out of boundaries')
            self.motor_vertical.move_absolute_position((self.boundaries['vertical_down_boundary'] - self.vertical_correction),self.unit)
        self.update_position_vertical()
    
    def move_sample_up(self):
        '''Sample motor upward vertical motion'''
        
        if self.return_current_vertical_position() + self.doubleSpinBox_incrementVertical.value() <= self.boundaries['vertical_up_boundary']:
            self.print_controller('Sample moving up')
            self.motor_vertical.move_relative_position(-self.doubleSpinBox_incrementVertical.value(),self.unit)
        else:
            self.print_controller('Out of boundaries')
            self.motor_vertical.move_absolute_position((self.boundaries['vertical_up_boundary'] - self.vertical_correction),self.unit)
        self.update_position_vertical()
    
    def move_sample_backward(self):
        '''Sample motor backward horizontal motion'''
        
        next_horizontal_position = self.return_current_horizontal_position() + self.doubleSpinBox_incrementHorizontal.value()
        if (self.return_current_camera_position() - next_horizontal_position) >= self.camera_sample_min_distance:  #To prevent the sample from hitting the camea
            self.print_controller ('Sample moving backward')
            self.motor_horizontal.move_relative_position(-self.doubleSpinBox_incrementHorizontal.value(),self.unit)
        else:
            self.print_controller('Camera prevents sample movement')
        self.update_position_horizontal()
            
    def move_sample_forward(self):
        '''Sample motor forward horizontal motion'''
        
        if self.return_current_horizontal_position() - self.doubleSpinBox_incrementHorizontal.value() >= self.boundaries['horizontal_forward_boundary']:
            self.print_controller('Sample moving forward')
            self.motor_horizontal.move_relative_position(self.doubleSpinBox_incrementHorizontal.value(),self.unit)
        else:
            self.print_controller('Out of boundaries')
            self.motor_horizontal.move_absolute_position(-self.boundaries['horizontal_forward_boundary']+self.horizontal_correction, self.unit)
        self.update_position_horizontal()
    
    def move_sample_to_origin(self):
        '''Moves vertical and horizontal sample motors to origin position'''
        
        self.print_controller('Moving to origin')
        if self.boundaries['origin_horizontal'] >= self.boundaries['horizontal_forward_boundary'] and self.boundaries['origin_horizontal'] <= self.boundaries['horizontal_backward_boundary']:
            if (self.return_current_camera_position() - self.boundaries['origin_horizontal']) >= self.camera_sample_min_distance:  #To prevent the sample from hitting the camea
                '''Moving sample to horizontal origin'''
                self.motor_horizontal.move_absolute_position(-self.boundaries['origin_horizontal']+self.horizontal_correction,self.unit)
                self.update_position_horizontal()
            else:
                self.print_controller('Camera prevents sample movement')
        else:
            self.print_controller('Sample Horizontal Origin Out Of Boundaries')
        
        '''Moving sample to vertical origin'''
        self.motor_vertical.move_absolute_position(self.boundaries['origin_vertical']-self.vertical_correction,self.unit)
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
        self.boundaries['horizontal_forward_boundary'] = 0 #428346 #533333.3333  #Maximum motor position, in micro-steps
        self.boundaries['horizontal_backward_boundary'] = 10 #375853 #0           #Minimum motor position, in micro-steps
        
        self.update_unit() 
    
    def set_horizontal_backward_boundary(self):
        '''Set lower limit of sample's horizontal motion 
           (to avoid hitting the glass walls)'''
        
        self.boundaries['horizontal_backward_boundary'] = self.return_current_horizontal_position(self.unit)
        self.change_default_boundaries(['horizontal_backward_boundary'])
        self.update_unit()
        self.horizontal_backward_boundary_selected = True
        
        self.pushButton_setBackwardLimit.setEnabled(False)
        if self.horizontal_forward_boundary_selected:
            self.pushButton_calibrateRange.setEnabled(True)
            self.label_calibrateRange.setText('Press Calibrate Range To Start')
    
    def set_horizontal_forward_boundary(self):
        '''Set upper limit of sample's horizontal motion 
           (to avoid hitting the glass walls)'''
        
        self.boundaries['horizontal_forward_boundary'] = self.return_current_horizontal_position(self.unit)
        self.change_default_boundaries(['horizontal_forward_boundary'])
        self.update_unit()
        
        self.horizontal_forward_boundary_selected = True
        
        self.pushButton_setForwardLimit.setEnabled(False)
        if self.horizontal_backward_boundary_selected:
            self.pushButton_calibrateRange.setEnabled(True)
            self.label_calibrateRange.setText('Press Calibrate Range To Start')
    
    def set_sample_origin(self):
        '''Modifies the sample origin position'''
        
        self.boundaries['origin_horizontal'] = self.return_current_vertical_position()
        self.boundaries['origin_vertical'] = self.return_current_vertical_position()
        origin_text = 'Origin set at (x,z) = ({}, {}) {}'.format(self.boundaries['origin_horizontal'],self.boundaries['origin_vertical'],self.unit)
        self.print_controller(origin_text)
        self.change_default_boundaries(['origin_horizontal','origin_vertical'])
    
    def change_default_boundaries(self,boundaries_to_change):
        '''Save default boundaries (with unit in mm)'''
        
        for boundary_name in boundaries_to_change:
            self.defaultBoundaries[boundary_name] = self.boundaries[boundary_name]
        if self.unit == 'cm':
            self.defaultBoundaries[boundary_name] /= 10
        elif self.unit == '\u03BCm':
            self.defaultBoundaries[boundary_name] *= 1000
    
    def set_camera_focus(self):
        '''Modifies manually the camera focus position'''
        
        self.focus_selected = True
        self.boundaries['focus'] = self.return_current_camera_position()
        self.change_default_boundaries(['focus'])
        self.print_controller('Camera focus manually set a {} mm'.format(self.boundaries['focus']))
        
    def calculate_camera_focus(self):
        '''Interpolates the camera focus position'''
        
        current_position = -self.motor_horizontal.current_position(self.unit) + self.horizontal_correction
        focus_regression = self.slope_camera * current_position + self.intercept_camera
        self.boundaries['focus'] = focus_regression
        print('focus_regression:'+str(focus_regression)) #debugging
        
        self.focus_selected = True
        
        self.print_controller('Focus automatically set')
    
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
        xstart = self.boundaries['horizontal_forward_boundary']
        xend = self.boundaries['horizontal_backward_boundary']
        ystart = self.focus_forward_boundary
        yend = self.focus_backward_boundary
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
        for param_string, param_box in zip(modifiable_parameters,self.modifiable_param_boxes):
            param_box.setValue(self.parameters[param_string]) 
    
    def change_default_parameters(self):
        '''Change all the default modifiable parameters to the current parameters'''
        
        for param_string,param_box in zip(modifiable_parameters,self.modifiable_param_boxes):
            self.defaultParameters[param_string] = param_box.value()
        self.print_controller('Default parameters changed')
        
    def save_default_parameters(self):
        '''Change all the default parameters of the configuration file to current default parameters'''
        
        with open(r"C:\git-projects\lightsheet\src\configuration.txt","w") as file:
            for param_string in modifiable_parameters:
                file.write(str(self.defaultParameters[param_string]) + '\n')
        self.print_controller('Default parameters saved in configuration file')
    
    def update_etl_galvos_parameters(self, parameter_name, parameter_box):
        '''Updates the parameters in the software after a modification by the
           user'''
        
        self.parameters[parameter_name] = parameter_box.value()
        
        if parameter_name == "etl_l_amplitude":
            parameter_box.setMaximum(5-self.doubleSpinBox_leftEtlOffset.value()) #To prevent ETL's amplitude + offset being > 5V
            opposed_parameter_box = self.doubleSpinBox_rightEtlAmplitude
        elif parameter_name == "etl_r_amplitude":
            parameter_box.setMaximum(5-self.doubleSpinBox_rightEtlOffset.value()) #To prevent ETL's amplitude + offset being > 5V
            opposed_parameter_box = self.doubleSpinBox_leftEtlAmplitude
        elif parameter_name == "etl_l_offset":
            parameter_box.setMaximum(5-self.doubleSpinBox_leftEtlAmplitude.value()) #To prevent ETL's amplitude + offset being > 5V
            opposed_parameter_box = self.doubleSpinBox_rightEtlOffset
        elif parameter_name == "etl_r_offset":
            parameter_box.setMaximum(5-self.doubleSpinBox_rightEtlAmplitude.value()) #To prevent ETL's amplitude + offset being > 5V
            opposed_parameter_box = self.doubleSpinBox_leftEtlOffset
        elif parameter_name == "galvo_l_amplitude":
            parameter_box.setMaximum(10-self.doubleSpinBox_leftGalvoOffset.value()) #To prevent galvo's amplitude + offset being > 10V
            parameter_box.setMinimum(-10-self.doubleSpinBox_leftGalvoOffset.value()) #To prevent galvo's amplitude + offset being < -10V
            opposed_parameter_box = self.doubleSpinBox_rightGalvoAmplitude
        elif parameter_name == "galvo_r_amplitude":
            parameter_box.setMaximum(10-self.doubleSpinBox_rightGalvoOffset.value()) #To prevent galvo's amplitude + offset being > 10V
            parameter_box.setMinimum(-10-self.doubleSpinBox_rightGalvoOffset.value()) #To prevent galvo's amplitude + offset being < -10V
            opposed_parameter_box = self.doubleSpinBox_leftGalvoAmplitude
        elif parameter_name == "galvo_l_offset":
            parameter_box.setMaximum(10-self.doubleSpinBox_leftGalvoAmplitude.value()) #To prevent galvo's amplitude + offset being > 10V
            parameter_box.setMinimum(-10-self.doubleSpinBox_leftGalvoAmplitude.value()) #To prevent galvo's amplitude + offset being < -10V
            opposed_parameter_box = self.doubleSpinBox_rightGalvoOffset
        elif parameter_name == "galvo_r_offset":
            parameter_box.setMaximum(10-self.doubleSpinBox_rightGalvoAmplitude.value()) #To prevent galvo's amplitude + offset being > 10V
            parameter_box.setMinimum(-10-self.doubleSpinBox_rightGalvoAmplitude.value()) #To prevent galvo's amplitude + offset being < -10V
            opposed_parameter_box = self.doubleSpinBox_leftGalvoOffset
        elif parameter_name == "galvo_l_frequency":
            opposed_parameter_box = self.doubleSpinBox_rightGalvoFrequency
        elif parameter_name == "galvo_r_frequency":
            opposed_parameter_box = self.doubleSpinBox_leftGalvoFrequency
        
        '''Modify simultaneously left and right parameters, if specified'''
        if self.checkBox_etlsTogether.isChecked() and (parameter_name in etl_parameters):
            opposed_parameter_box.setValue(self.parameters[parameter_name])
        if self.checkBox_galvosTogether.isChecked() and (parameter_name in galvo_parameters):
            opposed_parameter_box.setValue(self.parameters[parameter_name])
    
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
        if self.pushButton_rightLaserOn.isEnabled():
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
        if self.pushButton_leftLaserOn.isEnabled():
            self.pushButton_lasersOn.setEnabled(True)
        
        self.print_controller('Left laser off')
    
    def start_lasers(self):
        '''Starts the lasers at a certain voltage'''
        
        self.laser_on = True
        
        '''Setting up voltage'''
        left_laser_voltage = 0  #Default voltage of 0V
        right_laser_voltage = 0 #Default voltage of 0V
        
        if self.both_lasers_activated:
            left_laser_voltage = self.parameters['laser_l_voltage']
            right_laser_voltage = self.parameters['laser_r_voltage']   
        if self.left_laser_activated:
            left_laser_voltage = self.parameters['laser_l_voltage']  
        if self.right_laser_activated:
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
        
        '''Deactivating lasers'''
        if self.both_lasers_activated:
            self.deactivate_both_lasers()
        if self.left_laser_activated:
            self.deactivate_left_laser()
        if self.right_laser_activated:
            self.deactivate_right_laser()
 
 
    '''File Open Methods'''
        
    def select_file(self):
        '''Allows the selection of a file (.hdf5), opens it and displays its datasets'''
        
        '''Retrieve File'''
        self.open_directory = QFileDialog.getOpenFileName(self, 'Choose File', '', 'Hierarchical files (*.hdf5)')[0]
        
        if self.open_directory != '': #If file directory specified
            self.label_currentFileDirectory.setText(self.open_directory)
            self.listWidget_fileDatasets.clear()
            
            '''Open the file and display its datasets'''
            with h5py.File(self.open_directory, "r") as f:
                dataset_names = list(f.keys())
                for item in range(len(dataset_names)):
                    self.listWidget_fileDatasets.insertItem(item,dataset_names[item])
            self.listWidget_fileDatasets.setCurrentRow(0)
            
            self.print_controller('File '+self.open_directory+' opened')
            
            self.pushButton_selectDataset.setEnabled(True)
        else:
            self.label_currentFileDirectory.setText('None specified')
    
    def select_dataset(self):
        '''Opens a HDF5 dataset and displays its attributes and data as an image'''
        
        if (self.open_directory != '') and (self.listWidget_fileDatasets.count() != 0):
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
                self.figure_counter += 1
                
                ##'''Convert to tiff format'''
                ##tiff = Image.fromarray(data)
                ##tiff_filename = self.open_directory.replace('.hdf5', '.tiff')
                ##tiff.save(tiff_filename)
            
            self.print_controller('Dataset '+self.dataset_name+' of file '+self.open_directory+' displayed')
    
    
    '''Acquisition Modes Methods'''
    
    def start_standby(self):
        '''Closes the camera and initiates thread to keep ETLs'currents at 0A while
           the microscope is not in use'''
        
        self.close_modes()
        self.standby = True
        
        '''Close camera'''
        self.close_camera()
        
        '''Create ETL standby task'''
        self.standby_task = nidaqmx.Task()
        self.standby_task.ao_channels.add_ao_voltage_chan('/Dev1/ao2:3')
        
        etl_voltage = 2.5 #In volts
        standby_waveform = np.stack((np.array([etl_voltage]),np.array([etl_voltage])))
        
        '''Inject voltage'''
        self.standby_task.write(standby_waveform, auto_start = True)
        
        '''Modes disabling while in standby'''
        self.update_buttons_modes([self.pushButton_standbyOff])
        
        self.print_controller('Standby on')
        
    def stop_standby(self):
        '''Changes the standby flag status to end the thread'''
        
        self.standby = False
        
        '''Close task'''
        self.standby_task.stop()
        self.standby_task.close()
        
        '''Open camera'''
        self.open_camera()
        
        '''Modes enabling after standby'''
        self.update_buttons_modes(self.default_buttons)
        
        self.print_controller('Standby off')
    
    
    def send_frame_to_consumer(self,frame,to_cam_window=True,to_saver=False):
        '''Tries to add a frame to a consumer, either the camera window or the saver'''
        
        for consumer in range(0, len(self.consumers), 4):
            if to_cam_window:
                if self.consumers[consumer+2] == 'CameraWindow':
                    try:
                        self.consumers[consumer].put(frame)
                        #print('Frame put in CameraWindow') #debugging
                    except:      #self.consumers[ii].Full:
                        #print("CameraWindow queue is full") #debugging
                        pass
            if to_saver:
                if self.consumers[consumer+2] == 'FrameSaver':
                    try:
                        self.consumers[consumer].put(frame,1)
                        #print('Frame put in FrameSaver') #debugging
                    except:      #self.consumers[ii].Full:
                        #print("FrameSaver queue is full") #debugging
                        pass
    
    def start_preview_mode(self):
        '''Initializes variables for preview modes where beam and focal 
           positions are manually controlled by the user'''
        
        self.close_modes()
        self.preview_mode_started = True
        
        '''Modes disabling during preview_mode execution'''
        self.update_buttons_modes([self.pushButton_stopPreviewMode])
        
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
        self.start_camera_recording('AutoSequence')
        
        self.camera_window.change_frame_display_mode('frame2d')  
        
        '''Setting tasks'''
        self.lasers_task = nidaqmx.Task()
        self.lasers_task.ao_channels.add_ao_voltage_chan(terminals["lasers"])
        
        self.preview_galvos_etls_task = nidaqmx.Task()
        self.preview_galvos_etls_task.ao_channels.add_ao_voltage_chan(terminals["galvos_etls"])
        
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
            self.send_frame_to_consumer(frame)
        
        '''Stopping camera'''
        self.stop_camera_recording()
        
        '''End tasks'''
        self.preview_galvos_etls_task.stop()
        self.preview_galvos_etls_task.close()
        
        '''Stopping lasers'''
        self.stop_lasers()
        
        '''Enabling modes after preview_mode'''
        self.update_buttons_modes(self.default_buttons)
        
        self.print_controller('Preview mode stopped')
    
    def stop_preview_mode(self):
        '''Changes the preview_mode flag status to end the thread'''
        self.preview_mode_started = False
    
    
    def reconstruct_frame(self,buffer):
        '''Reconstructs a frame from multiple frames'''
    
        reconstructed_frame = np.zeros((int(self.parameters["rows"]), int(self.parameters["columns"])))  #Initializing frame
        
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
            first_column = int(frame * self.parameters['etl_step'])
            next_first_column = int(first_column + self.parameters['etl_step'])
            if frame == int(self.number_of_steps-1):  #For the last column step (may be different than the others...)
                reconstructed_frame[:,first_column:] = buffer[frame,:,first_column:]
            else:
                reconstructed_frame[:,first_column:next_first_column] = buffer[frame,:,first_column:next_first_column]
        
        return reconstructed_frame
    
    def crop_buffer(self,buffer):
        '''Crops each frame of a buffer for a frame reconstruction'''
        
        column_buffer = int(self.parameters["etl_step"]*0.2)
        reconstructed_buffer = np.zeros((buffer.shape[0],int(self.parameters["rows"]),int(self.parameters["etl_step"]+ (2*column_buffer))))  #Initializing frame

        for frame in range(int(self.number_of_steps)):
            first_column = int(frame * self.parameters['etl_step'] - column_buffer)
            next_first_column = int(first_column + self.parameters['etl_step'] + (2*column_buffer))
            if frame == 0:  #For the first column step
                reconstructed_buffer[frame,:,column_buffer:] = buffer[frame,:,0:int(self.parameters['etl_step'] + column_buffer)]
            elif frame == int(self.number_of_steps-1):  #For the last column step (may be different than the others...)
                last_column_step = int(self.parameters["columns"] - first_column)
                reconstructed_buffer[frame,:,0:last_column_step] = buffer[frame,:,first_column:]
            else:
                reconstructed_buffer[frame,:,:] = buffer[frame,:,first_column:next_first_column]
        
        return reconstructed_buffer
    
    def reconstruct_frame_from_cropped_buffer(self,cropped_buffer):
        '''Reconstructs a frame from multiple cropped frames (does some linear image stitching)'''
        
        column_buffer = int(self.parameters["etl_step"]*0.2)
        weight_step = 1/(2*column_buffer)
        reconstructed_frame = np.zeros((int(self.parameters["rows"]), int(self.parameters["columns"])))  #Initializing frame
        
        for frame in range(int(self.number_of_steps)):
            #'''Uniformize frame intensities'''
            #average = np.average(cropped_buffer[frame,0:100,:]) #Average the first rows
            #print(str(frame)+' average:'+str(average))
            ##print(buffer[1,:,:] == buffer[3,:,:])
            #if frame == 0:
            #    reference_average = average
            #    #print('reference_average:'+str(reference_average))
            #else:
            #    average_ratio = reference_average/average
            #    #print('average_ratio:'+str(average_ratio))
            #    cropped_buffer[frame,:,:] = cropped_buffer[frame,:,:] * average_ratio
            #
            '''Reconstruct frame'''
            first_center_column = int(frame * self.parameters['etl_step'] + column_buffer)
            #print('first_center_column:'+str(first_center_column))
            last_center_column = int((frame+1) * self.parameters['etl_step'] - column_buffer)
            #print('last_center_column:'+str(last_center_column))
            previous_last_center_column = int(frame * self.parameters['etl_step'] - column_buffer)
            #print('previous_last_center_column:'+str(previous_last_center_column))
            
            if frame == 0:  #For the first column step
                reconstructed_frame[:,0:last_center_column] = cropped_buffer[frame,:,column_buffer:int(self.parameters['etl_step'])]
            else:
                for column in range(2*column_buffer):
                    frame_column = column + previous_last_center_column
                    #print('frame_column:'+str(frame_column))
                    last_buffer_column = column + int(self.parameters['etl_step'])
                    #print('last_buffer_column:'+str(last_buffer_column))
                    buffer_weight = column * weight_step
                    #print('buffer_weight:'+str(buffer_weight))
                    last_buffer_weight = 1 - column * weight_step
                    #print('last_buffer_weight:'+str(last_buffer_weight))
                    reconstructed_frame[:,frame_column] = buffer_weight * cropped_buffer[frame,:,column] + last_buffer_weight*cropped_buffer[(frame-1),:,last_buffer_column]
                #print('frame_column:'+str(frame_column))
                if frame == int(self.number_of_steps-1):  #For the last column step (may be different than the others...)
                    last_column_step = int(self.parameters["columns"] - first_center_column)
                    #print('last_column_step:'+str(last_column_step))
                    reconstructed_frame[:,first_center_column:] = cropped_buffer[frame,:,column_buffer:column_buffer+last_column_step]
                else:
                    reconstructed_frame[:,first_center_column:last_center_column] = cropped_buffer[frame,:,(2*column_buffer):int(self.parameters['etl_step'])]

        return reconstructed_frame
    
    def get_single_image(self):
        '''Generate ETLs, galvos & camera's ramps, get a single reconstructed image and display it'''
        
        '''Creating ETLs, galvos & camera's ramps and waveforms'''
        self.ramps = AOETLGalvos(self.parameters)  
        self.ramps.create_tasks(terminals,'FINITE')
        activate=False
        if self.checkBox_activateEtlFocus.isChecked():
            activate = True
        self.ramps.create_calibrated_etl_waveforms(self.left_slope, self.left_intercept, self.right_slope, self.right_intercept,activate=activate)
        invert=False
        if self.checkBox_invertGalvos.isChecked():
            invert = True
        self.ramps.create_galvos_waveforms(case = 'TRAPEZE',invert=invert)
        self.ramps.create_digital_output_camera_waveform(case = 'STAIRS_FITTING')
        
        '''Writing waveform to task and running'''
        self.ramps.write_waveforms_to_tasks()                            
        self.ramps.start_tasks()
        self.ramps.run_tasks()
        
        '''Retrieving buffer'''
        self.number_of_steps = np.ceil(self.parameters["columns"]/self.parameters["etl_step"]) #Number of galvo sweeps in a frame, or alternatively the number of ETL focal step
        self.buffer = self.camera.retrieve_multiple_images(self.number_of_steps, self.ramps.t_half_period, sleep_timeout = 5)
        
        '''Frame reconstruction for display'''
        cropped_buffer = self.crop_buffer(self.buffer)
        if self.checkBox_stitching.isChecked():
            self.reconstructed_frame = self.reconstruct_frame_from_cropped_buffer(cropped_buffer)
        else:
            self.reconstructed_frame = self.reconstruct_frame(self.buffer)
        
        '''Frame display'''
        frame = np.transpose(self.reconstructed_frame)
        self.send_frame_to_consumer(frame)
        
        '''End tasks'''
        self.ramps.stop_tasks()                             
        self.ramps.close_tasks()
    
    def start_live_mode(self):
        '''This mode is for visualizing (and modifying) the effects of the 
           chosen parameters of the ramps which will be sent for single image 
           saving or volume saving (with stack_mode)'''
        
        self.close_modes()
        self.live_mode_started = True
        
        '''Disabling other modes while in live_mode'''
        self.update_buttons_modes([self.pushButton_stopLiveMode])
        
        self.print_controller('Live mode started')
        
        '''Starting live mode thread'''
        live_mode_thread = threading.Thread(target = self.live_mode_thread)
        live_mode_thread.start()
    
    def live_mode_thread(self):
        '''This thread allows the execution of live_mode while modifying
           parameters in the UI'''
        
        '''Setting the camera for acquisition'''
        self.start_camera_recording('ExternalExposureControl')
        
        self.camera_window.change_frame_display_mode('frame2d')  
        
        '''Moving the camera to focus'''
        ##self.move_camera_to_focus() 
        
        '''Creating task for lasers'''
        self.lasers_task = nidaqmx.Task()
        self.lasers_task.ao_channels.add_ao_voltage_chan(terminals["lasers"])
        
        while self.live_mode_started:
            '''Starting lasers'''
            self.start_lasers()
            '''Get single image'''
            self.get_single_image()
        
        '''Stopping camera'''
        self.stop_camera_recording()
        
        '''Stopping lasers'''
        self.stop_lasers()
        
        '''Enabling modes after live_mode'''
        self.update_buttons_modes(self.default_buttons)
        
        self.print_controller('Live mode stopped')

    def stop_live_mode(self):
        '''Changes the live_mode flag status to end the thread'''    
        self.live_mode_started = False
    
    
    def start_get_single_image(self):
        '''Generates and display a single frame which can be saved afterwards 
        using self.save_single_image()'''
        
        self.close_modes()
            
        '''Disabling modes while single frame acquisition'''
        self.update_buttons_modes(self.default_buttons)
        
        self.print_controller('Getting single image')
        
        '''Setting the camera for acquisition'''
        self.start_camera_recording('ExternalExposureControl')
        
        self.camera_window.change_frame_display_mode('frame2d')  
        
        '''Moving the camera to focus'''
        ##self.move_camera_to_focus()
        
        '''Getting positions for the image'''
        self.image_hor_pos_text = self.current_horizontal_position_text
        self.image_ver_pos_text = self.current_vertical_position_text
        self.image_cam_pos_text = self.current_camera_position_text
        
        '''Creating laser tasks'''
        self.lasers_task = nidaqmx.Task()
        self.lasers_task.ao_channels.add_ao_voltage_chan(terminals["lasers"])
        
        '''Starting lasers'''
        self.both_lasers_activated = True
        self.start_lasers()
        
        '''Get single image'''
        self.get_single_image()
        
        '''Stopping camera'''            
        self.stop_camera_recording()
        
        '''Stopping lasers'''
        self.stop_lasers()
        self.both_lasers_activated = False
        
        '''Enabling modes after single frame acquisition'''
        self.default_buttons.append(self.pushButton_saveImage)
        self.update_buttons_modes(self.default_buttons)
    
    def select_directory(self):
        '''Allows the selection of a directory for single_image or stack saving'''
        
        options = QFileDialog.Options()
        options |= QFileDialog.DontResolveSymlinks
        options |= QFileDialog.ShowDirsOnly
        self.save_directory = QFileDialog.getExistingDirectory(self, 'Choose Directory', '', options)
        
        if self.save_directory != '': #If directory specified
            self.label_currentDirectory.setText(self.save_directory)
            self.lineEdit_filename.setEnabled(True)
            self.lineEdit_filename.setText('')
            self.lineEdit_sampleName.setEnabled(True)
        else:
            self.label_currentDirectory.setText('None specified')
            self.lineEdit_filename.setEnabled(False)
            self.lineEdit_filename.setText('Select directory first')
            self.lineEdit_sampleName.setEnabled(False)
    
    def get_file_name(self):
        '''Retrieve filename set by the user'''
        
        self.filename = str(self.lineEdit_filename.text())
        #Removing spaces, dots and commas in filename
        for symbol in [' ','.',',']:
            self.filename = self.filename.replace(symbol, '')
            
        if (self.save_directory != '') and (self.filename != ''):
            self.filename = self.save_directory + '/' + self.filename
            self.saving_allowed = True
    
    def get_sample_name(self):
        '''Retrieve sample name'''
        
        if str(self.lineEdit_sampleName.text()) != '':
            parameters["sample_name"] = str(self.lineEdit_sampleName.text())
    
    def save_single_image(self):
        '''Saves the frame generated by self.get_single_image()'''
        
        '''Retrieving filename set by the user'''
        self.get_file_name()
        
        if self.saving_allowed:
            '''Setting up frame saver'''
            self.frame_saver = FrameSaver()
            self.frame_saver.set_block_size(1) #Block size is a number of buffers ##
            self.frame_saver.add_motor_parameters(self.image_hor_pos_text,self.image_ver_pos_text,self.image_cam_pos_text)
            
            '''Getting sample name'''
            self.get_sample_name()
            
            '''Saving frame'''
            if self.checkBox_saveAllFrames.isChecked():
                self.frame_saver.set_files(1,self.filename,'singleImage',1,'ETLscan',True)
                cropped_buffer = self.crop_buffer(self.buffer)
                self.frame_saver.put(cropped_buffer,1)
                self.print_controller('Saving Images (one for each ETL scan)')
            else:
                self.frame_saver.set_files(1,self.filename,'singleImage',1,'reconstructed_frame')
                self.frame_saver.put(self.reconstructed_frame,1)
                self.print_controller('Saving Reconstructed Image')
            
            self.frame_saver.start_saving()
            self.frame_saver.stop_saving()
        else:
            print('Select directory and enter a valid filename before saving')
    
    
    def set_number_of_planes(self):
        '''Calculates the number of planes that will be saved in the stack 
           acquisition'''
        
        if self.doubleSpinBox_planeStep.value() != 0:
            if self.checkBox_setStartPoint.isChecked() and self.checkBox_setEndPoint.isChecked():
                self.number_of_planes = np.ceil(abs((self.stack_mode_ending_point-self.stack_mode_starting_point)/self.doubleSpinBox_planeStep.value()))
                self.number_of_planes += 1   #Takes into account the initial plane
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
    
    def start_stack_mode(self):
        '''Initializes variables for volume saving which will take place in 
           self.stack_mode_thread afterwards'''
        
        self.close_modes()
        
        '''Making sure the limits of the volume are set'''
        if (self.checkBox_setStartPoint.isChecked() == False) or (self.checkBox_setEndPoint.isChecked() == False) or (self.doubleSpinBox_planeStep.value() == 0):
            print('Set starting and ending points and select a non-zero plane step value')
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
            self.update_buttons_modes([self.pushButton_stopStack])
            
            self.print_controller('Stack mode started -- Number of frames to save: '+str(int(self.number_of_planes)))
            
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
        self.start_camera_recording('ExternalExposureControl')
        
        self.camera_window.change_frame_display_mode('frame3d')
        
        '''Retrieving filename set by the user'''
        self.get_file_name()
        
        '''Making sure saving is allowed and filename isn't empty'''
        if self.saving_allowed:
            '''Setting frame saver'''
            self.frame_saver = FrameSaver()
            self.frame_saver.set_block_size(3) #Block size is a number of buffers
            '''Getting sample name'''
            self.get_sample_name()
            
            self.set_data_consumer(self.frame_saver, False, "FrameSaver", True) ###
            
            '''Starting frame saver'''
            if self.checkBox_saveAllFrames.isChecked():
                self.frame_saver.set_files(self.number_of_planes,self.filename,'stack',1,'ETLscan',True)
            else:
                self.frame_saver.set_files(1,self.filename,'stack',self.number_of_planes,'reconstructed_frame')
            self.frame_saver.start_saving()
        else:
            print('Select directory and enter a valid filename before saving')
        
        '''Creating lasers task'''
        self.lasers_task = nidaqmx.Task()
        self.lasers_task.ao_channels.add_ao_voltage_chan(terminals["lasers"])
        
        '''Starting lasers'''
        self.both_lasers_activated = True
        self.start_lasers()
        
        '''Set progress bar'''
        progress_value = 0
        progress_increment = int(100/self.number_of_planes)
        self.sig_update_progress.emit(0) #To reset progress bar
        
        for plane in range(int(self.number_of_planes)):
            if self.stack_mode_started == False:
                self.print_controller('Stack Acquisition Interrupted')
                break
            else:
                '''Moving sample position'''
                position = self.start_point + (plane * self.step)
                self.motor_horizontal.move_absolute_position(position,'\u03BCm')  #Position in micro-meters
                self.update_position_horizontal()
                
                '''Moving the camera to focus'''
                ##self.move_camera_to_focus()   
                
                if self.saving_allowed:
                    self.frame_saver.add_motor_parameters(self.current_horizontal_position_text,self.current_vertical_position_text,self.current_camera_position_text)
                
                '''Getting image'''
                self.get_single_image()
                
                '''Saving frame'''
                if self.saving_allowed:
                    if self.checkBox_saveAllFrames.isChecked():
                        cropped_buffer = self.crop_buffer(self.buffer)
                        self.send_frame_to_consumer(cropped_buffer,False,True)
                        self.print_controller('Saving Images (one for each ETL scan)')
                    else:
                        self.send_frame_to_consumer(self.reconstructed_frame,False,True)
                        self.print_controller('Saving Reconstructed Image')
                
                '''Update progress bar'''
                progress_value += progress_increment
                self.sig_update_progress.emit(progress_value)
        if self.stack_mode_started:
            self.sig_update_progress.emit(100) #In case the number of planes is not a multiple of 100
        
        if self.saving_allowed:
            self.frame_saver.stop_saving()
        
        '''Stopping camera'''
        self.stop_camera_recording()  
        
        '''Stopping laser'''
        self.stop_lasers()
        self.both_lasers_activated = False
        
        '''Enabling modes after stack mode'''
        self.update_buttons_modes(self.default_buttons)
        
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
        self.update_buttons_modes([self.pushButton_cancelCalibrateCamera])
            
        self.print_controller('Camera calibration started')
            
        '''Starting camera calibration thread'''
        calibrate_camera_thread = threading.Thread(target = self.calibrate_camera_thread)
        calibrate_camera_thread.start()
    
    def calibrate_camera_thread(self):
        ''' Calibrates the camera focus by finding the ideal camera position 
            for multiple sample horizontal positions'''
        
        '''Setting the camera for acquisition'''
        self.start_camera_recording('ExternalExposureControl')
        
        '''Creating laser tasks'''
        self.lasers_task = nidaqmx.Task()
        self.lasers_task.ao_channels.add_ao_voltage_chan(terminals["lasers"])
        
        '''Starting lasers'''
        self.both_lasers_activated = True
        self.start_lasers()
        
        '''Getting calibration parameters'''
        if self.doubleSpinBox_numberOfCalibrationPlanes.value() != 0:
            self.number_of_calibration_planes = self.doubleSpinBox_numberOfCalibrationPlanes.value()
        if self.doubleSpinBox_numberOfCameraPositions.value() != 0:
            self.number_of_camera_positions = self.doubleSpinBox_numberOfCameraPositions.value()
        
        #sample_increment_length = (self.horizontal_forward_boundary - self.horizontal_backward_boundary) / self.number_of_calibration_planes
        sample_increment_length = (self.boundaries['horizontal_backward_boundary']-self.boundaries['horizontal_forward_boundary']) / (self.number_of_calibration_planes-1) #-1 to account for last position (backward_boundary)
        self.focus_backward_boundary = 42#397626#245000#int(200000*0.75)#200000#245000#225000#245000#250000 #263000   ##Position arbitraire en u-steps
        self.focus_forward_boundary = 32#447506#450000 #447506#265000#int(300000*25/20)#300000#265000#255000#265000#270000  #269000   ##Position arbitraire en u-steps
        camera_increment_length = (self.focus_backward_boundary - self.focus_forward_boundary) / (self.number_of_camera_positions-1) #-1 to account for last position (backward_boundary)
        
        position_depart_sample = self.motor_horizontal.current_position('\u03BCStep')
        
        self.camera_focus_relation = np.zeros((int(self.number_of_calibration_planes),2))
        metricvar=np.zeros((int(self.number_of_camera_positions)))
        self.donnees=np.zeros(((int(self.number_of_calibration_planes)),(int(self.number_of_camera_positions)))) #debugging
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
        
        for sample_plane in range(int(self.number_of_calibration_planes)): #For each sample position
            if self.camera_calibration_started == False:
                self.print_controller('Camera calibration interrupted')
                break
            else:
                '''Moving sample position'''
                position = self.boundaries['horizontal_forward_boundary'] + (sample_plane * sample_increment_length)    #Increments of +sample_increment_length
                self.motor_horizontal.move_absolute_position(-position+self.horizontal_correction,self.unit)
                self.update_position_horizontal()
                
                for camera_plane in range(int(self.number_of_camera_positions)): #For each camera position
                    '''Moving camera position'''
                    position_camera = self.focus_forward_boundary + (camera_plane * camera_increment_length) #Increments of +camera_increment_length
                    print('position_camera:'+str(position_camera))
                    self.motor_camera.move_absolute_position(-position_camera+self.camera_correction,'mm')
                    time.sleep(0.5) #To make sure the camera is at the right position
                    self.update_position_camera()

                    '''Retrieving filename set by the user''' #debugging
                    if self.saving_allowed:
                        self.frame_saver.add_motor_parameters(self.current_horizontal_position_text,self.current_vertical_position_text,self.current_camera_position_text)
                    
                    '''Getting image'''
                    self.get_single_image()
                    
                    '''Saving frame''' #debugging
                    if self.saving_allowed:
                        self.send_frame_to_consumer(self.reconstructed_frame,False,True)
                        self.print_controller('Saving Reconstructed Image')
                    
                    '''Filtering frame'''
                    frame = ndimage.gaussian_filter(self.reconstructed_frame, sigma=3)
                    flatframe = frame.flatten()
                    intensities = np.sort(frame,axis=None)
                    metricvar[camera_plane] = np.average(intensities[-50:])#np.var(flatframe)
                    print(np.var(flatframe))
                
                '''Calculating ideal camera position'''
                metricvar = signal.savgol_filter(metricvar, 11, 3) # window size 11, polynomial order 3
                metricvar = (metricvar - np.min(metricvar))/(np.max(metricvar) - np.min(metricvar))#normalize
                self.donnees[sample_plane,:] = metricvar #debugging
                
                n = len(metricvar)
                x = np.arange(n)            
                mean = sum(x*metricvar)/n           
                sigma = sum(metricvar*(x-mean)**2)/n
                poscenter = np.argmax(metricvar)
                print('poscenter:'+str(poscenter)) #debugging
                popt,pcov = optimize.curve_fit(gaussian,x,metricvar,p0=[1,mean,sigma],bounds=(0, 'inf'), maxfev=10000)
                amp,center,variance = popt
                self.popt[sample_plane] = popt
                print('center:'+str(center)) #debugging
                print('amp:'+str(amp)) #debugging
                print('variance:'+str(variance)) #debugging
                print('pcov:'+str(pcov)) #debugging
                
                '''Saving focus relation'''
                self.camera_focus_relation[sample_plane,0] = self.return_current_horizontal_position()
                max_variance_camera_position = self.focus_forward_boundary + (center * camera_increment_length)
                print('max_variance_camera_position:'+str(max_variance_camera_position))
                self.camera_focus_relation[sample_plane,1] = max_variance_camera_position#-self.motor_camera.data_to_position(max_variance_camera_position, self.unit) + self.camera_correction
                
            self.print_controller('--Calibration of plane '+str(sample_plane+1)+'/'+str(int(self.number_of_calibration_planes))+' done')
        
        print('relation:') #debugging
        print(self.camera_focus_relation)#debugging
        
        if self.saving_allowed: #debugging
            self.frame_saver.stop_saving()
            self.print_controller('Images saved')
        
        '''Returning sample and camera at initial positions'''
        self.motor_horizontal.move_absolute_position(position_depart_sample,'\u03BCStep')
        self.update_position_horizontal()
        self.motor_camera.move_absolute_position(-self.boundaries['focus']+self.camera_correction,self.unit)
        self.update_position_camera()
        
        '''Stopping camera'''
        self.stop_camera_recording()
        
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
            
            self.default_buttons.append(self.pushButton_calculateFocus)
            self.default_buttons.append(self.pushButton_showCamInterpolation)
        
        self.print_controller('Camera calibration done')
            
        '''Enabling modes after camera calibration'''
        self.update_buttons_modes(self.default_buttons)
            
        self.camera_calibration_started = False

    def stop_calibrate_camera(self):
        '''Interrups camera calibration'''
        
        self.camera_calibration_started = False

    
    def start_calibrate_etls(self):
        '''Initiates etls-galvos calibration'''
        
        self.close_modes()
        self.etls_calibration_started = True
       
        '''Modes disabling while stack acquisition'''
        self.update_buttons_modes([self.pushButton_stopEtlsGalvosCalibration])
        
        self.print_controller('ETL calibration started')
        
        '''Starting camera calibration thread'''
        calibrate_etls_thread = threading.Thread(target = self.calibrate_etls_thread)
        calibrate_etls_thread.start()
    
    def calibrate_etls_thread(self):
        ''' Calibrates the focal position relation with etls-galvos voltage'''
        
        '''Setting the camera for acquisition'''
        self.start_camera_recording('AutoSequence')
        
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
            for etl_point in range(int(self.number_of_etls_points)):
                
                if self.etls_calibration_started == False:
                    self.print_controller('Calibration interrupted')
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
                    self.ramps=AOETLGalvos(self.parameters)
                    self.ramps.initialize()
                    self.number_of_steps = 1
                    self.buffer = self.camera.retrieve_multiple_images(self.number_of_steps, self.ramps.t_half_period, sleep_timeout = 5) #debugging
                    self.save_single_image() #debugging
                    
                    ydatas = np.zeros((self.number_of_etls_images,128))  ##128=K
                    
                    #For each image
                    for etl_image in range(self.number_of_etls_images):
                        '''Retrieving image from camera and putting it in its queue
                               for display'''
                        frame = self.camera.retrieve_single_image()*1.0
                        blurred_frame = ndimage.gaussian_filter(frame, sigma=20)
                        
                        frame = np.transpose(frame)
                        blurred_frame = np.transpose(blurred_frame)
                        
                        self.send_frame_to_consumer(frame)
                        self.send_frame_to_consumer(blurred_frame)
                        ##for ii in range(0, len(self.consumers), 4):
                        ##    if self.consumers[ii+2] == "CameraWindow":
                        ##        #Initial frame
                        ##        try:
                        ##            self.consumers[ii].put(frame)
                        ##        except self.consumers[ii].Full:
                        ##            print("Queue is full")
                        ##        #Blurred frame
                        ##        try:
                        ##            self.consumers[ii].put(blurred_frame)
                        ##        except self.consumers[ii].Full:
                        ##            print("Queue is full")
                        
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
                
                    self.print_controller('--Calibration of plane '+str(etl_point+1)+'/'+str(self.number_of_etls_points)+' for '+side+' done')
            
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
        self.stop_camera_recording()
        
        '''Ending tasks'''
        self.galvos_etls_task.stop()
        self.galvos_etls_task.close()
        
        '''Stopping lasers'''
        self.stop_lasers()
        self.both_lasers_activated = False
        
        if self.etls_calibration_started: #To make sure calibration wasn't stopped before the end
            self.default_buttons.append([self.pushButton_showEtlInterpolation])
        
        self.print_controller('Calibration done')
            
        '''Enabling modes after camera calibration'''
        self.update_buttons_modes(self.default_buttons)
            
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
        
        
        self.frame_list = []
        self.xvals_list = []
        self.histogram_level = []
        self.frame_counter = 1
        self.stack_mode = False
        
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
    
    def change_frame_display_mode(self,mode='frame2d'):
        '''Change the mode of the frame display'''
        
        if mode == 'frame2d':
            self.stack_mode = False
        if mode == 'frame3d':
            self.stack_mode = True
    
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
            if self.stack_mode:
                self.frame_list.append(frame.tolist())
                if len(self.frame_list) > 10 : #To prevent the list of frames from being too big
                    self.frame_list.pop(0)
                    self.xvals_list.pop(0)
                frame3d = np.array(self.frame_list)
                #frame3d = np.flip(frame3d,axis=0)
                
                self.xvals_list.append(self.frame_counter) ###changer pour position horizontale?
                self.frame_counter += 1
                xvals = np.array(self.xvals_list)
                #xvals = np.flip(xvals)
                #print(xvals) #debugging
                self.imv.setImage(frame3d,xvals=xvals)
            else:
                self.imv.setImage(frame)
            
            '''Showing saturated pixels in red'''
            saturated_pixels = np.array(np.where(frame >= 65335)) #65535 is the max intensity value that the camera can output (2^16-1)
            saturated_pixels = saturated_pixels + 0.5 #To make sure red pixels are at the right position...
            saturated_pixels_list = saturated_pixels.tolist()
            self.plot_item.plot(saturated_pixels_list[0],saturated_pixels_list[1],pen=None,symbolBrush=(255,0,0),symbol='s',symbolSize=1,pxMode=False)
            
            '''Keeping old view settings with new image'''
            _view_box.setState(_state)
            if not first_update: #To keep the histogram setting with image refresh
                _histo_widget.setLevels(self.histogram_level[0],self.histogram_level[1])
        
        except queue.Empty:
            if self.stack_mode == False:
                self.frame_counter = 1 #reset
            pass

class FrameSaver():
    '''Class for storing buffers (images) in its queue and saving them 
       afterwards in a specified directory in a HDF5 format'''
    
    '''Set up methods'''
    
    def __init__(self):
        self.filenames_list = [] 
        self.number_of_files = 1
        
        self.horizontal_positions_list = []
        self.vertical_positions_list = []
        self.camera_positions_list = []
    
    def add_motor_parameters(self,current_hor_position_txt,current_ver_position_txt,current_cam_position_txt):
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
            '''Create file'''
            f = h5py.File(self.filenames_list[file],'a')
            
            counter = 1
            for dataset in range(int(self.number_of_datasets)):
                in_loop = True
                while in_loop:
                    try:
                        '''Retrieve buffer'''
                        buffer = self.queue.get(True,1)
                        #print(buffer.shape[0]) #debugging
                        #print('Buffer received') #debugging
                        if buffer.ndim == 2:
                            buffer = np.expand_dims(buffer, axis=0) #To consider 2D arrays as a 3D arrays
                        for frame in range(buffer.shape[0]): #For each 2D frame
                            '''Create dataset'''
                            path_root = self.datasets_name+u'%03d'%counter
                            self.dataset = f.create_dataset(path_root, data=buffer[frame,:,:])
                            #print('Dataset created:'+str(path_root)) #debugging
                            
                            '''Add attributes'''
                            self.add_attribute('Sample', parameters["sample_name"])
                            self.add_attribute('Date', str(datetime.date.today()))
                            if buffer.shape[0] == 1:
                                pos_index = dataset + file * int(self.number_of_datasets)
                            else:
                                pos_index = file
                            self.add_attribute('Current sample horizontal position', self.horizontal_positions_list[pos_index])
                            self.add_attribute('Current sample vertical position', self.vertical_positions_list[pos_index])
                            self.add_attribute('Current camera horizontal position', self.camera_positions_list[pos_index])
                            for param_string in modifiable_parameters:
                                self.add_attribute(param_string, parameters[param_string])
                            #print('attributes ok') #debugging
                            counter += 1
                        in_loop = False
                    except:
                        #print('No buffer') #debugging
                        if self.saving_started == False:
                            in_loop = False
            f.close()
            print('File '+self.filenames_list[file]+' saved')

    def stop_saving(self):
        '''Changes the flag status to end the saving thread''' 
        self.saving_started = False

