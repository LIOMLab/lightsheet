'''
Created on May 22, 2019

@author: flesage
'''

import sys
from IPython.utils import frame
sys.path.append("..")

import os
import numpy as np
from PyQt5 import QtGui
from PyQt5 import uic
from PyQt5.QtWidgets import QWidget, QFileDialog
from PyQt5.QtWidgets import QApplication, QMainWindow, QMenu, QVBoxLayout, QSizePolicy, QMessageBox, QPushButton
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import QThread

import pyqtgraph as pg
import ctypes
import copy

import nidaqmx
from nidaqmx.constants import AcquisitionType

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
parameters["samplerate"]=100
parameters["sweeptime"]=1        #0.4
parameters["galvo_l_frequency"]=10
parameters["galvo_l_amplitude"]=2
parameters["galvo_l_offset"]=0
parameters["galvo_l_duty_cycle"]=50
parameters["galvo_l_phase"]=np.pi/2
parameters["galvo_r_frequency"]=10
parameters["galvo_r_amplitude"]=2
parameters["galvo_r_offset"]=0
parameters["galvo_r_duty_cycle"]=50
parameters["galvo_r_phase"]=np.pi/2
parameters["etl_l_delay"]=7.5
parameters["etl_l_ramp_rising"]=85
parameters["etl_l_ramp_falling"]=2.5
parameters["etl_l_amplitude"]=2
parameters["etl_l_offset"]=0
parameters["etl_r_delay"]=7.5
parameters["etl_r_ramp_rising"]=85
parameters["etl_r_ramp_falling"]=2.5
parameters["etl_r_amplitude"]=2
parameters["etl_r_offset"]=0
parameters["laser_l_voltage"]=0.905
parameters["laser_r_voltage"]=0.935

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
        basepath= os.path.join(os.path.dirname(__file__))
        uic.loadUi(os.path.join(basepath,"control.ui"), self)
        
        self.parameters = copy.deepcopy(parameters)
        self.defaultParameters = copy.deepcopy(parameters)
        
        self.consumers = []
        
        '''Initializing flags'''
        self.allLasersOn = False
        self.leftLaserOn = False
        self.rightLaserOn = False
        self.previewModeStarted = False
        self.liveModeStarted = False
        self.cameraOn = True
        
        self.motor1 = Motors(1, 'COM3')             #Vertical motor
        self.motor2 = Motors(2, 'COM3')             #Horizontal motor for sample motion
        self.motor3 = Motors(3, 'COM3')             #Horizontal motor for detection arm motion
        
        self.camera = Camera()
        
        #Right values for the origin to determine
        self.originX = 533333
        self.originZ = 0
        self.focus = 533333
        
        #Lasers default voltage
        self.leftLaserVoltage = 0.905
        self.rightLaserVoltage = 0.935
        
        #For optimized parameters calculations
        self.frequency=0
        self.samplerate=0
        self.sweeptime=0
        self.delay=0
        
        #Decimal number is the same for all widgets for a specific unit
        self.decimals = self.doubleSpinBox_incrementHorizontal.decimals()
        
        self.comboBox_unit.insertItems(0,["cm","mm","\u03BCm"])
        self.comboBox_unit.setCurrentIndex(1)
        self.comboBox_unit.currentTextChanged.connect(self.update_all)
        
        #To initialize the widget that are updated by a change of unit (the motion tab)
        self.update_all()
        #To initialize the properties of the other widgets
        self.initialize_other_widgets()
        
        self.lineEdit_filename.setEnabled(False)
        self.pushButton_selectDirectory.clicked.connect(self.select_directory)
        self.savingAllowed = False
        
        
        #**********************************************************************
        # Connections for the modes
        #**********************************************************************
        self.pushButton_getSingleImage.clicked.connect(self.start_get_single_image)
        self.pushButton_saveImage.clicked.connect(self.save_single_image)
        self.pushButton_startLiveMode.clicked.connect(self.start_live_mode)
        self.pushButton_stopLiveMode.clicked.connect(self.stop_live_mode)
        self.pushButton_startStack.clicked.connect(self.start_stack_mode)
        self.pushButton_stopStack.clicked.connect(self.stop_stack_mode)
        self.pushButton_startPreviewMode.clicked.connect(self.start_preview_mode)
        self.pushButton_stopPreviewMode.clicked.connect(self.stop_preview_mode)
        #self.pushButton_closeCamera.clicked.connect(self.close_camera)
        
        #**********************************************************************
        # Connections for the motion
        #**********************************************************************
        self.pushButton_MotorUp.clicked.connect(self.move_up)
        self.pushButton_MotorDown.clicked.connect(self.move_down)
        self.pushButton_MotorRight.clicked.connect(self.move_right)
        self.pushButton_MotorLeft.clicked.connect(self.move_left)
        self.pushButton_MotorOrigin.clicked.connect(self.move_to_origin)
        self.pushButton_moveHome.clicked.connect(self.move_home)
        #self.pushButton_moveMaxPosition.clicked.connect(self.move_to_maximum_position)
        self.pushButton_setAsOrigin.clicked.connect(self.set_origin )
        
        #Motion of the detection arm to implement when clicked (self.motor3)
        #Might write a function for this button
        self.pushButton_movePosition.clicked.connect(lambda: self.motor2.move_absolute_position(self.doubleSpinBox_choosePosition.value(),self.comboBox_unit.currentText()))
        self.pushButton_movePosition.clicked.connect(lambda: self.label_currentHorizontalNumerical.setText("{} {}".format(round(self.motor2.current_position(self.comboBox_unit.currentText()),self.decimals), self.comboBox_unit.currentText())))
        
        #Might write a function for this button
        self.pushButton_moveHeight.clicked.connect(lambda: self.motor1.move_absolute_position(self.doubleSpinBox_chooseHeight.value(),self.comboBox_unit.currentText()))
        self.pushButton_moveHeight.clicked.connect(lambda: self.label_currentHeightNumerical.setText("{} {}".format(round(self.motor1.current_position(self.comboBox_unit.currentText()),self.decimals), self.comboBox_unit.currentText())))
       
        #Might write a function for this button
        self.pushButton_moveCamera.clicked.connect(lambda: self.motor3.move_absolute_position(self.doubleSpinBox_chooseCamera.value(),self.comboBox_unit.currentText()))
        self.pushButton_moveCamera.clicked.connect(lambda: self.label_currentCameraNumerical.setText("{} {}".format(round(self.motor3.current_position(self.comboBox_unit.currentText()),self.decimals), self.comboBox_unit.currentText())))
        self.pushButton_setFocus.clicked.connect(self.set_focus)
        
        self.pushButton_forward.clicked.connect(self.move_forward)
        self.pushButton_backward.clicked.connect(self.move_backward)
        self.pushButton_focus.clicked.connect(self.move_to_focus)
        
        
        #**********************************************************************
        # Connections for the ETLs and Galvos parameters
        #**********************************************************************
        self.pushButton_calculateOptimized.clicked.connect(self.synchronize_ramps)
        self.pushButton_setOptimized.clicked.connect(self.set_optimized_parameters)
        
        self.doubleSpinBox_leftEtlAmplitude.valueChanged.connect(lambda: self.etl_galvos_parameters_changed(1))
        self.doubleSpinBox_rightEtlAmplitude.valueChanged.connect(lambda: self.etl_galvos_parameters_changed(2))
        self.doubleSpinBox_leftEtlOffset.valueChanged.connect(lambda: self.etl_galvos_parameters_changed(3))
        self.doubleSpinBox_rightEtlOffset.valueChanged.connect(lambda: self.etl_galvos_parameters_changed(4))
        self.doubleSpinBox_leftEtlDelay.valueChanged.connect(lambda: self.etl_galvos_parameters_changed(5))
        self.doubleSpinBox_rightEtlDelay.valueChanged.connect(lambda: self.etl_galvos_parameters_changed(6))
        self.doubleSpinBox_leftEtlRising.valueChanged.connect(lambda: self.etl_galvos_parameters_changed(7))
        self.doubleSpinBox_rightEtlRising.valueChanged.connect(lambda: self.etl_galvos_parameters_changed(8))
        self.doubleSpinBox_leftEtlFalling.valueChanged.connect(lambda: self.etl_galvos_parameters_changed(9))
        self.doubleSpinBox_rightEtlFalling.valueChanged.connect(lambda: self.etl_galvos_parameters_changed(10))
        self.doubleSpinBox_leftGalvoAmplitude.valueChanged.connect(lambda: self.etl_galvos_parameters_changed(11))
        self.doubleSpinBox_rightGalvoAmplitude.valueChanged.connect(lambda: self.etl_galvos_parameters_changed(12))
        self.doubleSpinBox_leftGalvoOffset.valueChanged.connect(lambda: self.etl_galvos_parameters_changed(13))
        self.doubleSpinBox_rightGalvoOffset.valueChanged.connect(lambda: self.etl_galvos_parameters_changed(14))
        self.doubleSpinBox_leftGalvoFrequency.valueChanged.connect(lambda: self.etl_galvos_parameters_changed(15))
        self.doubleSpinBox_rightGalvoFrequency.valueChanged.connect(lambda: self.etl_galvos_parameters_changed(16))
        self.doubleSpinBox_leftGalvoDutyCycle.valueChanged.connect(lambda: self.etl_galvos_parameters_changed(17))
        self.doubleSpinBox_rightGalvoDutyCycle.valueChanged.connect(lambda: self.etl_galvos_parameters_changed(18))
        self.doubleSpinBox_leftGalvoPhase.valueChanged.connect(lambda: self.etl_galvos_parameters_changed(19))
        self.doubleSpinBox_rightGalvoPhase.valueChanged.connect(lambda: self.etl_galvos_parameters_changed(20))
        self.doubleSpinBox_samplerate.valueChanged.connect(lambda: self.etl_galvos_parameters_changed(21))
        self.doubleSpinBox_sweeptime.valueChanged.connect(lambda: self.etl_galvos_parameters_changed(22))
        
        self.pushButton_defaultParameters.clicked.connect(self.back_to_default_parameters)
    
        
        #**********************************************************************
        # Connections for the camera
        #**********************************************************************
        self.pushButton_getTemp.clicked.connect(self.get_camera_temp)
        
        
        #**********************************************************************
        # Connections for the lasers
        #**********************************************************************
        self.pushButton_lasersOn.clicked.connect(self.lasers_on)
        self.pushButton_lasersOff.clicked.connect(self.lasers_off)
        self.pushButton_leftLaserOn.clicked.connect(self.left_laser_on)
        self.pushButton_leftLaserOff.clicked.connect(self.left_laser_off)
        self.pushButton_rightLaserOn.clicked.connect(self.right_laser_on)
        self.pushButton_rightLaserOff.clicked.connect(self.right_laser_off)
        
        self.horizontalSlider_leftLaser.sliderReleased.connect(self.left_laser_update)
        self.horizontalSlider_rightLaser.sliderReleased.connect(self.right_laser_update)
        
        
    def start_get_single_image(self):
        
        '''Flags check up'''
        if self.previewModeStarted == True:
            self.stop_preview_mode()
            self.previewModeStarted = False
        elif self.liveModeStarted == True:
            self.stop_live_mode()
            self.liveModeStarted = False
            
        self.pushButton_getSingleImage.setEnabled(False)
        self.pushButton_startLiveMode.setEnabled(False)
        self.pushButton_stopLiveMode.setEnabled(False)
        self.pushButton_startStack.setEnabled(False)
        self.pushButton_stopStack.setEnabled(False)
        self.pushButton_startPreviewMode.setEnabled(False)
        self.pushButton_stopPreviewMode.setEnabled(False)
        print('Getting single image')
        
        '''Setting the camera for acquisition'''
        self.camera.set_trigger_mode('ExternalExposureControl')
        self.camera.arm_camera() 
        self.camera.get_sizes() 
        self.camera.allocate_buffer()    
        self.camera.set_recording_state(1)
        self.camera.insert_buffers_in_queue()
        
        self.ramps=AOETLGalvos(self.parameters)                  
        self.ramps.create_tasks(terminals,'FINITE')                           
        self.ramps.create_galvos_waveforms()
        self.ramps.create_etl_waveforms()
        self.ramps.create_DO_camera_waveform()
        self.ramps.create_lasers_waveforms()                   
        self.ramps.write_waveforms_to_tasks()                            
        self.ramps.start_tasks()
        self.ramps.run_tasks()
        
        frame = self.camera.retrieve_single_image()*1.0
        
        for i in range(0, len(self.consumers), 4):
            if self.consumers[i+2] == "CameraWindow":
                try:
                    self.consumers[i].put(frame)
                except:      #self.consumers[i].Full:
                    print("Queue is full")
                    
        self.single_frame = frame
                    
        self.camera.cancel_images()
        self.camera.set_recording_state(0)
        self.camera.free_buffer()

        self.ramps.stop_tasks()                             
        self.ramps.close_tasks()
        
        '''Put the lasers voltage to zero
           This is done at the end, because we do not want to shut down the lasers
           after each sweep to make sure their power values stay the same '''
        self.lasers_task = nidaqmx.Task()
        self.lasers_task.ao_channels.add_ao_voltage_chan(terminals["lasers"])
        waveforms = np.stack(([0],[0]))
        self.lasers_task.write(waveforms)
        self.lasers_task.stop()
        self.lasers_task.close()
        
        self.pushButton_getSingleImage.setEnabled(True)
        self.pushButton_saveImage.setEnabled(True)
        self.pushButton_startLiveMode.setEnabled(True)
        self.pushButton_startStack.setEnabled(True)
        self.pushButton_startPreviewMode.setEnabled(True)
        
    def save_single_image(self):
        
        self.filename = str(self.lineEdit_filename.text())
        '''Removing spaces, dots and commas'''
        self.filename = self.filename.replace(' ', '')
        self.filename = self.filename.replace('.', '')
        self.filename = self.filename.replace(',', '')
        
        if self.savingAllowed and self.filename != '':
            self.filename = self.save_directory + '/' + self.filename + '.hdf5'
            self.frame_saver = FrameSaver(self.filename)
            self.scan_type = 'SingleImage'
            self.scan_date = str(datetime.date.today())
            self.path_root = posixpath.join('/', self.scan_date)
            self.file_number = self.frame_saver.check_existing_files(self.path_root, self.scan_type)
            self.scan_number = self.scan_type + '_' + str(self.file_number)
            self.path_name = posixpath.join(self.path_root, self.scan_number)
            #self.frame_saver.set_dataset_name(self.path_name)
            print(self.path_name)
            '''We can add attributes here'''
            #self.frame_saver.f[self.frame_saver.path_name]= self.single_frame
            self.frame_saver.f.create_dataset(self.path_name, data=self.single_frame)
            self.frame_saver.f.close()
            
        else:
            print('Select directory and enter a valid filename before saving')
        
    def start_live_mode(self):
        
        '''Flags check up'''
        if self.previewModeStarted == True:
            self.stop_preview_mode()
            self.previewModeStarted = False
        elif self.liveModeStarted == True:
            self.stop_live_mode()
            self.liveModeStarted = False
            
        self.liveModeStarted = True
        self.pushButton_getSingleImage.setEnabled(False)
        self.pushButton_saveImage.setEnabled(False)
        self.pushButton_startLiveMode.setEnabled(False)
        self.pushButton_stopLiveMode.setEnabled(True)
        self.pushButton_startStack.setEnabled(False)
        self.pushButton_stopStack.setEnabled(False)
        self.pushButton_startPreviewMode.setEnabled(False)
        self.pushButton_stopPreviewMode.setEnabled(False)
        
        print('Start live mode')
        
        '''Setting the camera for acquisition'''
        self.camera.set_trigger_mode('ExternalExposureControl')
        self.camera.arm_camera() 
        self.camera.get_sizes() 
        self.camera.allocate_buffer()    
        self.camera.set_recording_state(1)
        self.camera.insert_buffers_in_queue()
        
        # Setup from data in gui
        self.ramps=AOETLGalvos(self.parameters)                  
        self.ramps.create_tasks(terminals, 'CONTINUOUS')                           
        self.ramps.create_galvos_waveforms()
        self.ramps.create_etl_waveforms()
        self.ramps.create_DO_camera_waveform()
        self.ramps.create_lasers_waveforms()                     
        self.ramps.write_waveforms_to_tasks()                            
        self.ramps.start_tasks()
        
        liveMode_thread = threading.Thread(target = self.live_mode_thread)
        liveMode_thread.start()
        
    def live_mode_thread(self):
        continuer = True
        for i in range(0, len(self.consumers), 4):
            if self.consumers[i+2] == "CameraWindow":
                while continuer:
                    
                    '''Retrieving image from camera and putting it in its queue'''
                    if self.liveModeStarted == True:
                        frame = self.camera.retrieve_single_image()*1.0
        
                        try:
                            self.consumers[i].put(frame)
                        except self.consumers[i].Full:
                            print("Queue is full")
                    elif self.liveModeStarted == False:
                        continuer = False
        
        self.camera.cancel_images()
        self.camera.set_recording_state(0)
        self.camera.free_buffer()
        
        self.ramps.stop_tasks()                             
        self.ramps.close_tasks()
        
        '''Put the lasers voltage to zero
           This is done at the end, because we do not want to shut down the lasers
           after each sweep to make sure their power values stay the same '''
        self.lasers_task = nidaqmx.Task()
        self.lasers_task.ao_channels.add_ao_voltage_chan(terminals["lasers"])
        waveforms = np.stack(([0],[0]))
        self.lasers_task.write(waveforms)
        self.lasers_task.stop()
        self.lasers_task.close()
        
        self.pushButton_getSingleImage.setEnabled(True)
        self.pushButton_startLiveMode.setEnabled(True)
        self.pushButton_stopLiveMode.setEnabled(False)
        self.pushButton_startStack.setEnabled(True)
        self.pushButton_startPreviewMode.setEnabled(True)
        
        print('Live mode stopped')
        
    def stop_live_mode(self):
        self.liveModeStarted = False
        
    
        
    def start_stack_mode(self):
        '''Detection arm (self.motor3) to be implemented 
        
        Note: check if there's a NI-Daqmx function to repeat the data sent instead of closing each time the task. This would be useful
        if it is possible to break a task with self.stop_stack_mode
        
        An option to scan forward or backward should be implemented
        A progress bar would be nice
        '''
        self.pushButton_getSingleImage.setEnabled(False)
        self.pushButton_saveImage.setEnabled(False)
        self.pushButton_startLiveMode.setEnabled(False)
        self.pushButton_stopLiveMode.setEnabled(False)
        self.pushButton_startStack.setEnabled(False)
        self.pushButton_stopStack.setEnabled(True)
        self.pushButton_startPreviewMode.setEnabled(False)
        self.pushButton_stopPreviewMode.setEnabled(False)
        
        print('Start stack mode')
        for i in range(int(self.doubleSpinBox_planeNumber.value())):
            self.ramps=AOETLGalvos(parameters)                  
            self.ramps.create_tasks(terminals, 'FINITE')                           
            self.ramps.create_galvos_waveforms()
            self.ramps.create_etl_waveforms()                   
            self.ramps.write_waveforms_to_tasks()
            self.ramps.run_tasks()                            
            self.ramps.start_tasks()
            self.ramps.run_tasks()
            self.ramps.stop_tasks()                             
            self.ramps.close_tasks()
            #Sample motion
            if self.comboBox_stackDirection.currentText() == 'Forward':
                self.motor2.move_relative_position(-self.doubleSpinBox_planeStep.value(),'\u03BCm')
            elif self.comboBox_stackDirection.currentText() == 'Backward':
                self.motor2.move_relative_position(self.doubleSpinBox_planeStep.value(),'\u03BCm')
        
        print('Acquisition done')
        #Current camera position update
        self.label_currentHorizontalNumerical.setText("{} {}".format(round(self.motor2.current_position(self.comboBox_unit.currentText()),self.decimals), self.comboBox_unit.currentText())) 
        self.pushButton_getSingleImage.setEnabled(True)
        self.pushButton_startLiveMode.setEnabled(True)
        self.pushButton_startStack.setEnabled(True)
        self.pushButton_stopStack.setEnabled(False)
        self.pushButton_startPreviewMode.setEnabled(True)
            
    def stop_stack_mode(self):
        '''Useless function for now. Would be useful to find a way to stop stack mode before it's done. Note: check how to break a NI-Daqmx task '''
        pass
        

                           
    
    def move_up(self):
        print('Moving up')
        self.motor1.move_relative_position(-self.doubleSpinBox_incrementVertical.value(),self.comboBox_unit.currentText())
        #Current height update
        self.label_currentHeightNumerical.setText("{} {}".format(round(self.motor1.current_position(self.comboBox_unit.currentText()),self.decimals), self.comboBox_unit.currentText()))
#        port = AsciiSerial("COM3")
#        command = AsciiCommand("home")
#        port.write(command)
        
    def move_down(self):
        print ('Moving down')
        self.motor1.move_relative_position(self.doubleSpinBox_incrementVertical.value(),self.comboBox_unit.currentText())
        #Current height update
        self.label_currentHeightNumerical.setText("{} {}".format(round(self.motor1.current_position(self.comboBox_unit.currentText()),self.decimals), self.comboBox_unit.currentText()))

    def move_right(self):
        #Motion of the detection arm to implement (self.motor3)
        print ('Sample moving forward')
        self.motor2.move_relative_position(self.doubleSpinBox_incrementHorizontal.value(),self.comboBox_unit.currentText())
        #Current horizontal position update
        self.label_currentHorizontalNumerical.setText("{} {}".format(round(self.motor2.current_position(self.comboBox_unit.currentText()), self.decimals), self.comboBox_unit.currentText()))
    
    def move_left(self):
        #Motion of the detection arm to implement (self.motor3)
        print ('Sample moving backward')
        self.motor2.move_relative_position(-self.doubleSpinBox_incrementHorizontal.value(),self.comboBox_unit.currentText())
        #Current horizontal position update
        self.label_currentHorizontalNumerical.setText("{} {}".format(round(self.motor2.current_position(self.comboBox_unit.currentText()),self.decimals), self.comboBox_unit.currentText()))
        
    def move_to_origin(self):
        #Motion of the detection arm to implement (self.motor3)
        print('Moving to origin')
        self.motor2.move_absolute_position(self.originX,'\u03BCStep')
        self.motor1.move_absolute_position(self.originZ,'\u03BCStep')
        #Current positions update
        self.label_currentHorizontalNumerical.setText("{} {}".format(round(self.motor2.current_position(self.comboBox_unit.currentText()),self.decimals), self.comboBox_unit.currentText()))
        self.label_currentHeightNumerical.setText("{} {}".format(round(self.motor1.current_position(self.comboBox_unit.currentText()),self.decimals), self.comboBox_unit.currentText()))
        
    def move_forward(self):
        print('Camera moving forward')
        self.motor3.move_relative_position(self.doubleSpinBox_incrementCamera.value(),self.comboBox_unit.currentText())
        #Current camera position update
        self.label_currentCameraNumerical.setText("{} {}".format(round(self.motor3.current_position(self.comboBox_unit.currentText()),self.decimals), self.comboBox_unit.currentText()))
        
    def move_backward(self):
        print('Camera moving backward')
        self.motor3.move_relative_position(-self.doubleSpinBox_incrementCamera.value(),self.comboBox_unit.currentText())
        #Current camera position update
        self.label_currentCameraNumerical.setText("{} {}".format(round(self.motor3.current_position(self.comboBox_unit.currentText()),self.decimals), self.comboBox_unit.currentText()))
        
    def move_to_focus(self):
        print('Moving to focus')
        self.motor3.move_absolute_position(self.focus,'\u03BCStep')
        #Current camera position update
        self.label_currentCameraNumerical.setText("{} {}".format(round(self.motor3.current_position(self.comboBox_unit.currentText()),self.decimals), self.comboBox_unit.currentText()))
    
    def move_home(self):
        self.motor1.move_home()
        self.motor2.move_home()
        self.motor3.move_home()
        #Current positions update
        self.label_currentHorizontalNumerical.setText("{} {}".format(round(self.motor2.current_position(self.comboBox_unit.currentText()),self.decimals), self.comboBox_unit.currentText()))
        self.label_currentHeightNumerical.setText("{} {}".format(round(self.motor1.current_position(self.comboBox_unit.currentText()),self.decimals), self.comboBox_unit.currentText()))
        self.label_currentCameraNumerical.setText("{} {}".format(round(self.motor3.current_position(self.comboBox_unit.currentText()),self.decimals), self.comboBox_unit.currentText()))
    
    def move_to_maximum_position(self):
        self.motor3.move_maximum_position()
        self.motor2.move_maximum_position()
        self.motor1.move_maximum_position()
        #Current positions update
        self.label_currentHorizontalNumerical.setText("{} {}".format(round(self.motor2.current_position(self.comboBox_unit.currentText()),self.decimals), self.comboBox_unit.currentText()))
        self.label_currentHeightNumerical.setText("{} {}".format(round(self.motor1.current_position(self.comboBox_unit.currentText()),self.decimals), self.comboBox_unit.currentText()))
        self.label_currentCameraNumerical.setText("{} {}".format(round(self.motor3.current_position(self.comboBox_unit.currentText()),self.decimals), self.comboBox_unit.currentText()))
    
    def set_origin(self):
        self.originX = self.motor2.position_to_data(self.motor2.current_position(self.comboBox_unit.currentText()),self.comboBox_unit.currentText())
        self.originZ = 1066666 - self.motor1.position_to_data(self.motor1.current_position(self.comboBox_unit.currentText()),self.comboBox_unit.currentText())
        print('Origin set')
        
    def set_focus(self):
        self.focus = self.motor3.position_to_data(self.motor3.current_position(self.comboBox_unit.currentText()),self.comboBox_unit.currentText())
        print('Focus set')
        
    def update_all(self):
        unit = self.comboBox_unit.currentText()
        
        self.doubleSpinBox_incrementHorizontal.setSuffix(" {}".format(unit))
        self.doubleSpinBox_incrementHorizontal.setValue(1)
        self.doubleSpinBox_incrementVertical.setSuffix(" {}".format(unit))
        self.doubleSpinBox_incrementVertical.setValue(1)
        self.doubleSpinBox_incrementCamera.setSuffix(" {}".format(self.comboBox_unit.currentText()))
        self.doubleSpinBox_incrementCamera.setValue(1)
        self.doubleSpinBox_choosePosition.setSuffix(" {}".format(unit))
        self.doubleSpinBox_choosePosition.setValue(0)
        self.doubleSpinBox_chooseHeight.setSuffix(" {}".format(unit))
        self.doubleSpinBox_chooseHeight.setValue(0)
        self.doubleSpinBox_chooseCamera.setSuffix(" {}".format(self.comboBox_unit.currentText()))
        self.doubleSpinBox_chooseCamera.setValue(0)
        
        if unit == 'cm':
            self.doubleSpinBox_incrementHorizontal.setDecimals(4)
            self.doubleSpinBox_incrementHorizontal.setMaximum(10.16)
            self.doubleSpinBox_incrementVertical.setDecimals(4)
            self.doubleSpinBox_incrementVertical.setMaximum(10.16)
            self.doubleSpinBox_incrementCamera.setDecimals(4)
            self.doubleSpinBox_incrementCamera.setMaximum(10.16)
            self.doubleSpinBox_choosePosition.setDecimals(4)
            self.doubleSpinBox_choosePosition.setMaximum(10.16)
            self.doubleSpinBox_chooseHeight.setDecimals(4)
            self.doubleSpinBox_chooseHeight.setMaximum(10.16)
            self.doubleSpinBox_chooseCamera.setDecimals(4)
            self.doubleSpinBox_chooseCamera.setMaximum(10.16)
            self.decimals = self.doubleSpinBox_incrementHorizontal.decimals()
            self.label_currentHeightNumerical.setText("{} {}".format(round(self.motor1.current_position(unit),self.decimals), unit))
            self.label_currentHorizontalNumerical.setText("{} {}".format(round(self.motor2.current_position(unit),self.decimals), unit))
            self.label_currentCameraNumerical.setText("{} {}".format(round(self.motor3.current_position(unit),self.decimals), unit))
        elif unit == 'mm':
            self.doubleSpinBox_incrementHorizontal.setDecimals(3)
            self.doubleSpinBox_incrementHorizontal.setMaximum(101.6)
            self.doubleSpinBox_incrementVertical.setDecimals(3)
            self.doubleSpinBox_incrementVertical.setMaximum(101.6)
            self.doubleSpinBox_incrementCamera.setDecimals(3)
            self.doubleSpinBox_incrementCamera.setMaximum(101.6)
            self.doubleSpinBox_choosePosition.setDecimals(3)
            self.doubleSpinBox_choosePosition.setMaximum(101.6)
            self.doubleSpinBox_chooseHeight.setDecimals(3)
            self.doubleSpinBox_chooseHeight.setMaximum(101.6)
            self.doubleSpinBox_chooseCamera.setDecimals(3)
            self.doubleSpinBox_chooseCamera.setMaximum(101.6)
            self.decimals = self.doubleSpinBox_incrementHorizontal.decimals()
            self.label_currentHeightNumerical.setText("{} {}".format(round(self.motor1.current_position(unit),self.decimals), unit))
            self.label_currentHorizontalNumerical.setText("{} {}".format(round(self.motor2.current_position(unit),self.decimals), unit))
            self.label_currentCameraNumerical.setText("{} {}".format(round(self.motor3.current_position(unit),self.decimals), unit))
        elif unit == '\u03BCm':
            self.doubleSpinBox_incrementHorizontal.setDecimals(0)
            self.doubleSpinBox_incrementHorizontal.setMaximum(101600)
            self.doubleSpinBox_incrementVertical.setDecimals(0)
            self.doubleSpinBox_incrementVertical.setMaximum(101600)
            self.doubleSpinBox_incrementCamera.setDecimals(0)
            self.doubleSpinBox_incrementCamera.setMaximum(101600)
            self.doubleSpinBox_choosePosition.setDecimals(0)
            self.doubleSpinBox_choosePosition.setMaximum(101600)
            self.doubleSpinBox_chooseHeight.setDecimals(0)
            self.doubleSpinBox_chooseHeight.setMaximum(101600)
            self.doubleSpinBox_chooseCamera.setDecimals(0)
            self.doubleSpinBox_chooseCamera.setMaximum(101600)
            self.decimals = self.doubleSpinBox_incrementHorizontal.decimals()
            self.label_currentHeightNumerical.setText("{} {}".format(round(self.motor1.current_position(unit),self.decimals), unit))
            self.label_currentHorizontalNumerical.setText("{} {}".format(round(self.motor2.current_position(unit),self.decimals), unit))
            self.label_currentCameraNumerical.setText("{} {}".format(round(self.motor3.current_position(unit),self.decimals), unit))
    
    def synchronize_ramps(self):
        '''Synchronizes ETLs' and galvos' ramps at a frequency specified. The number of samples for a period of the galvos is twice the number of lines because
           there is two scans in one period. The number of columns is the number of scans, it is also the number of galvos' half periods. The delay period
           of the ETLs is adjusted so the galvos go from their rest positions to the positions to start scanning (1/4 period for a phase of pi/2).
           
           Parameters: 
               frequency: A float or integer, in Hz
               lines: An integer. Usually the number of lines (pixels) of the camera.
               columns: An integer. Usually the number of columns (pixels) of the camera.
               
           Further modifications will take into account the positions of the lines and columns to scan a specific area of the sample, and so decreasing
           the acquisition time.Positions will have an effect on the offsets, whereas the size of the area will have an effect on the voltage.
        '''
        #Half period of the galvo scans all the lines
        samples_per_period = 2*self.spinBox_lines.value()
        #Number of columns is the number of galvos half periods  (lines*columns)
        samples_in_rise = samples_per_period*self.spinBox_columns.value()/2
        #Rule of three for a fixed value of ramp rising
        samples =100*samples_in_rise/parameters["etl_r_ramp_rising"]
        
        self.samplerate = samples_per_period*self.doubleSpinBox_galvoFrequency.value()
        self.sweeptime = samples/self.samplerate
        self.delay = (1/4*samples_per_period/samples)*100
        self.frequency = self.doubleSpinBox_galvoFrequency.value()
        
        self.label_galvoFrequencyNumerical.setText('{} {}'.format(self.frequency, 'Hz'))
        self.label_samplerateNumerical.setText('{} {}'.format(round(self.samplerate,5), 'sample/s'))
        self.label_sweeptimeNumerical.setText('{} {}'.format(round(self.sweeptime,5), 's'))
        self.label_delayNumerical.setText('{} {}'.format(round(self.delay,5), '%'))
        
        self.pushButton_setOptimized.setEnabled(True)
        
    def set_optimized_parameters(self):
        parameters["samplerate"] = self.samplerate
        parameters["sweeptime"] = self.sweeptime
        parameters["galvo_l_frequency"] = parameters["galvo_r_frequency"]=self.frequency
        parameters["etl_l_delay"] = parameters["etl_r_delay"] = self.delay
        self.doubleSpinBox_samplerate.setValue(self.samplerate)
        self.doubleSpinBox_sweeptime.setValue(self.sweeptime)
        self.doubleSpinBox_leftGalvoFrequency.setValue(self.frequency)
        self.doubleSpinBox_rightGalvoFrequency.setValue(self.frequency)
        self.doubleSpinBox_leftEtlDelay.setValue(self.delay)
        self.doubleSpinBox_rightEtlDelay.setValue(self.delay)
        
    def initialize_other_widgets(self):
        '''Initializes the properties of the widgets that are not upadted by a change of units, so the widgets that cannot be initialize with self.update_all() '''
        
        #**********************************************************************
        # Modes
        #**********************************************************************
        self.pushButton_stopLiveMode.setEnabled(False)
        self.pushButton_stopStack.setEnabled(False)
        self.pushButton_setOptimized.setEnabled(False)
        self.pushButton_saveImage.setEnabled(False)
        self.pushButton_stopPreviewMode.setEnabled(False)
        
        self.spinBox_planeNumber.setMaximum(101600)
        self.spinBox_planeNumber.setMinimum(1)
        self.spinBox_planeNumber.setSingleStep(1)
        
        self.doubleSpinBox_planeStep.setSuffix(' \u03BCm')
        self.doubleSpinBox_planeStep.setDecimals(0)
        self.doubleSpinBox_planeStep.setMaximum(101600)
        self.doubleSpinBox_planeStep.setSingleStep(1)
        
        self.comboBox_stackDirection.insertItems(0,['Forward','Backward'])
        self.comboBox_stackDirection.setCurrentIndex(0)
        
        
        #**********************************************************************
        # ETLs and Galvos Parameters
        #**********************************************************************
        self.doubleSpinBox_galvoFrequency.setMaximum(130)
        self.doubleSpinBox_galvoFrequency.setSuffix(' Hz')
        self.doubleSpinBox_galvoFrequency.setSingleStep(5)
        
        self.spinBox_lines.setMinimum(1)
        self.spinBox_lines.setMaximum(10000)
        self.spinBox_lines.setValue(2160)
        
        self.spinBox_columns.setMinimum(1)
        self.spinBox_columns.setMaximum(10000)
        self.spinBox_columns.setValue(2560)
        
        self.doubleSpinBox_leftEtlAmplitude.setValue(self.parameters["etl_l_amplitude"])
        self.doubleSpinBox_leftEtlAmplitude.setSuffix(" V")
        self.doubleSpinBox_leftEtlAmplitude.setMaximum(5)
        self.doubleSpinBox_rightEtlAmplitude.setValue(self.parameters["etl_r_amplitude"])
        self.doubleSpinBox_rightEtlAmplitude.setSuffix(" V")
        self.doubleSpinBox_rightEtlAmplitude.setMaximum(5)
        self.doubleSpinBox_leftEtlOffset.setValue(self.parameters["etl_l_offset"])
        self.doubleSpinBox_leftEtlOffset.setSuffix(" V")
        self.doubleSpinBox_leftEtlOffset.setMaximum(5)
        self.doubleSpinBox_rightEtlOffset.setValue(self.parameters["etl_r_offset"])
        self.doubleSpinBox_rightEtlOffset.setSuffix(" V")
        self.doubleSpinBox_rightEtlOffset.setMaximum(5)
        self.doubleSpinBox_leftEtlDelay.setValue(self.parameters["etl_l_delay"])
        self.doubleSpinBox_leftEtlDelay.setSuffix(" %")
        self.doubleSpinBox_rightEtlDelay.setValue(self.parameters["etl_r_delay"])
        self.doubleSpinBox_rightEtlDelay.setSuffix(" %")
        self.doubleSpinBox_leftEtlRising.setValue(self.parameters["etl_l_ramp_rising"])
        self.doubleSpinBox_leftEtlRising.setSuffix(" %")
        self.doubleSpinBox_rightEtlRising.setValue(self.parameters["etl_r_ramp_rising"])
        self.doubleSpinBox_rightEtlRising.setSuffix(" %")
        self.doubleSpinBox_leftEtlFalling.setValue(self.parameters["etl_l_ramp_falling"])
        self.doubleSpinBox_leftEtlFalling.setSuffix(" %")
        self.doubleSpinBox_rightEtlFalling.setValue(self.parameters["etl_r_ramp_falling"])
        self.doubleSpinBox_rightEtlFalling.setSuffix(" %")
        
        self.doubleSpinBox_leftGalvoAmplitude.setValue(self.parameters["galvo_l_amplitude"])
        self.doubleSpinBox_leftGalvoAmplitude.setSuffix(" V")
        self.doubleSpinBox_leftGalvoAmplitude.setMaximum(10)
        self.doubleSpinBox_leftGalvoAmplitude.setMinimum(-10)
        self.doubleSpinBox_rightGalvoAmplitude.setValue(self.parameters["galvo_r_amplitude"])
        self.doubleSpinBox_rightGalvoAmplitude.setSuffix(" V")
        self.doubleSpinBox_rightGalvoAmplitude.setMaximum(10)
        self.doubleSpinBox_rightGalvoAmplitude.setMinimum(-10)
        self.doubleSpinBox_leftGalvoOffset.setValue(self.parameters["galvo_l_offset"])
        self.doubleSpinBox_leftGalvoOffset.setSuffix(" V")
        self.doubleSpinBox_leftGalvoOffset.setMaximum(10)
        self.doubleSpinBox_leftGalvoOffset.setMinimum(-10)
        self.doubleSpinBox_rightGalvoOffset.setValue(self.parameters["galvo_r_offset"])
        self.doubleSpinBox_rightGalvoOffset.setSuffix(" V")
        self.doubleSpinBox_rightGalvoOffset.setMaximum(10)
        self.doubleSpinBox_rightGalvoOffset.setMinimum(-10)
        self.doubleSpinBox_leftGalvoFrequency.setValue(self.parameters["galvo_l_frequency"])
        self.doubleSpinBox_leftGalvoFrequency.setSuffix(" Hz")
        self.doubleSpinBox_leftGalvoFrequency.setMaximum(130)
        self.doubleSpinBox_rightGalvoFrequency.setValue(self.parameters["galvo_r_frequency"])
        self.doubleSpinBox_rightGalvoFrequency.setSuffix(" Hz")
        self.doubleSpinBox_rightGalvoFrequency.setMaximum(130)
        self.doubleSpinBox_leftGalvoDutyCycle.setValue(self.parameters["galvo_l_duty_cycle"])
        self.doubleSpinBox_leftGalvoDutyCycle.setSuffix(" %")
        self.doubleSpinBox_rightGalvoDutyCycle.setValue(self.parameters["galvo_r_duty_cycle"])
        self.doubleSpinBox_rightGalvoDutyCycle.setSuffix(" %")
        self.doubleSpinBox_leftGalvoPhase.setValue(self.parameters["galvo_l_phase"])
        self.doubleSpinBox_leftGalvoPhase.setSuffix(" rad")
        self.doubleSpinBox_leftGalvoPhase.setMaximum(np.pi*2)
        self.doubleSpinBox_leftGalvoPhase.setMinimum(-np.pi*2)
        self.doubleSpinBox_rightGalvoPhase.setValue(self.parameters["galvo_r_phase"])
        self.doubleSpinBox_rightGalvoPhase.setSuffix(" rad")
        self.doubleSpinBox_rightGalvoPhase.setMaximum(np.pi*2)
        self.doubleSpinBox_rightGalvoPhase.setMinimum(-np.pi*2)
        
        self.doubleSpinBox_samplerate.setMaximum(1000000)
        self.doubleSpinBox_samplerate.setValue(self.parameters["samplerate"])
        self.doubleSpinBox_samplerate.setSuffix(" samples/s")
        self.doubleSpinBox_sweeptime.setValue(self.parameters["sweeptime"])
        self.doubleSpinBox_sweeptime.setSuffix(" s")
        
        
        #**********************************************************************
        # Camera parameters
        #**********************************************************************
        #self.label_cameraName.setText(self.camera.name)
        self.get_camera_temp()
        self.comboBox_timeUnit.insertItems(0, ["ns","\u03BCs","ms"])
        self.comboBox_timeUnit.setCurrentIndex(2)
        
        #**********************************************************************
        # Lasers parameters
        #**********************************************************************
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
        
    def lasers_on(self):
        self.allLasersOn = True
        self.pushButton_lasersOn.setEnabled(False)
        self.pushButton_lasersOff.setEnabled(True)
        self.pushButton_leftLaserOn.setEnabled(False)
        self.pushButton_rightLaserOn.setEnabled(False)
        print('Lasers on')
        
    def lasers_off(self):
        self.allLasersOn = False
        self.pushButton_lasersOn.setEnabled(True)
        self.pushButton_lasersOff.setEnabled(False)
        self.pushButton_leftLaserOn.setEnabled(True)
        self.pushButton_rightLaserOn.setEnabled(True)
        print('Lasers off')
        
    def left_laser_on(self):
        self.leftLaserOn = True
        self.pushButton_lasersOn.setEnabled(False)
        self.pushButton_leftLaserOn.setEnabled(False)
        self.pushButton_leftLaserOff.setEnabled(True)
        print('Left laser on')
        
    def left_laser_off(self):
        self.leftLaserOn = False
        print('Left laser off')
        self.pushButton_leftLaserOn.setEnabled(True)
        self.pushButton_leftLaserOff.setEnabled(False)
        if self.pushButton_rightLaserOn.isEnabled() == True:
            self.pushButton_lasersOn.setEnabled(True)
        
    def right_laser_on(self):
        self.rightLaserOn = True
        self.pushButton_lasersOn.setEnabled(False)
        self.pushButton_rightLaserOn.setEnabled(False)
        self.pushButton_rightLaserOff.setEnabled(True)
        print('Left laser on')
        
    def right_laser_off(self):
        self.rightLaserOn = False
        print('Left laser off')
        self.pushButton_rightLaserOn.setEnabled(True)
        self.pushButton_rightLaserOff.setEnabled(False)
        if self.pushButton_leftLaserOn.isEnabled() == True:
            self.pushButton_lasersOn.setEnabled(True)
            
    def left_laser_update(self):
        self.label_leftLaserVoltage.setText('{} {}'.format(self.horizontalSlider_leftLaser.value()/100, 'V'))
        self.parameters["laser_l_voltage"] = self.horizontalSlider_leftLaser.value()/100
    
    def right_laser_update(self):
        self.label_rightLaserVoltage.setText('{} {}'.format(self.horizontalSlider_rightLaser.value()/100, 'V'))
        self.parameters["laser_r_voltage"] = self.horizontalSlider_rightLaser.value()/100
     
    #Camera functions 
    
    def start_preview_mode(self):
        
        print('Start preview mode')
        
        '''Flags check up'''
        if self.previewModeStarted == True:
            self.stop_preview_mode()
            self.previewModeStarted = False
        elif self.liveModeStarted == True:
            self.stop_live_mode()
            self.liveModeStarted = False
            
        self.previewModeStarted = True
        
        self.pushButton_getSingleImage.setEnabled(False)
        self.pushButton_saveImage.setEnabled(False)
        self.pushButton_startStack.setEnabled(False)
        self.pushButton_stopStack.setEnabled(False)
        self.pushButton_startLiveMode.setEnabled(False)
        self.pushButton_stopLiveMode.setEnabled(False)
        self.pushButton_startPreviewMode.setEnabled(False)
        self.pushButton_stopPreviewMode.setEnabled(True)
        
        '''Setting tasks'''
        self.preview_lasers_task = nidaqmx.Task()
        self.preview_lasers_task.ao_channels.add_ao_voltage_chan(terminals["lasers"])
        
        self.preview_galvos_etls_task = nidaqmx.Task()
        self.preview_galvos_etls_task.ao_channels.add_ao_voltage_chan(terminals["galvos_etls"])
        
        '''Setting the camera for acquisition'''
        self.camera.set_trigger_mode('AutoSequence')
        self.camera.arm_camera() 
        self.camera.get_sizes() 
        self.camera.allocate_buffer()    
        self.camera.set_recording_state(1)
        self.camera.insert_buffers_in_queue()
        
        previewMode_thread = threading.Thread(target = self.previewThread)
        previewMode_thread.start()
     
    def stop_preview_mode(self):
        self.previewModeStarted = False
    
    
    def close_camera(self):
        self.cameraOn = False
        self.camera.close_camera()
        print('Camera closed')
     
     
    def etl_galvos_parameters_changed(self, parameterNumber):
        if parameterNumber==1:
            self.parameters["etl_l_amplitude"]=self.doubleSpinBox_leftEtlAmplitude.value()
        elif parameterNumber==2: 
            self.parameters["etl_r_amplitude"]=self.doubleSpinBox_rightEtlAmplitude.value()
        elif parameterNumber==3:
            self.parameters["etl_l_offset"]=self.doubleSpinBox_leftEtlOffset.value()
        elif parameterNumber==4:
            self.parameters["etl_r_offset"]=self.doubleSpinBox_rightEtlOffset.value()
        elif parameterNumber==5:
            self.parameters["etl_l_delay"]=self.doubleSpinBox_leftEtlDelay.value()
        elif parameterNumber==6:
            self.parameters["etl_r_delay"]=self.doubleSpinBox_rightEtlDelay.value()
        elif parameterNumber==7:
            self.parameters["etl_l_ramp_rising"]=self.doubleSpinBox_leftEtlRising.value()
        elif parameterNumber==8:
            self.parameters["etl_r_ramp_rising"]=self.doubleSpinBox_rightEtlRising.value()
        elif parameterNumber==9:
            self.parameters["etl_l_ramp_falling"]=self.doubleSpinBox_leftEtlFalling.value()
        elif parameterNumber==10:
            self.parameters["etl_r_ramp_falling"]=self.doubleSpinBox_rightEtlFalling.value()
        elif parameterNumber==11:
            self.parameters["galvo_l_amplitude"]=self.doubleSpinBox_leftGalvoAmplitude.value()
        elif parameterNumber==12:
            self.parameters["galvo_r_amplitude"]=self.doubleSpinBox_rightGalvoAmplitude.value()
        elif parameterNumber==13:
            self.parameters["galvo_l_offset"]=self.doubleSpinBox_leftGalvoOffset.value()
        elif parameterNumber==14:
            self.parameters["galvo_r_offset"]=self.doubleSpinBox_rightGalvoOffset.value()
        elif parameterNumber==15:
            self.parameters["galvo_l_frequency"]=self.doubleSpinBox_leftGalvoFrequency.value()
        elif parameterNumber==16:
            self.parameters["galvo_r_frequency"]=self.doubleSpinBox_rightGalvoFrequency.value()
        elif parameterNumber==17:
            self.parameters["galvo_l_duty_cycle"]=self.doubleSpinBox_leftGalvoDutyCycle.value()
        elif parameterNumber==18:
            self.parameters["galvo_r_duty_cycle"]=self.doubleSpinBox_rightGalvoDutyCycle.value()
        elif parameterNumber==19:
            self.parameters["galvo_l_phase"]=self.doubleSpinBox_leftGalvoPhase.value()
        elif parameterNumber==20:
            self.parameters["galvo_r_phase"]=self.doubleSpinBox_rightGalvoPhase.value()
        elif parameterNumber==21:
            self.parameters["samplerate"]=self.doubleSpinBox_samplerate.value()
        elif parameterNumber==22:
            self.parameters["sweeptime"]=self.doubleSpinBox_sweeptime.value()
            
                          
     
    def back_to_default_parameters(self):
        self.parameters = copy.deepcopy(self.defaultParameters)
        self.doubleSpinBox_leftEtlAmplitude.setValue(self.parameters["etl_l_amplitude"])
        self.doubleSpinBox_rightEtlAmplitude.setValue(self.parameters["etl_r_amplitude"])
        self.doubleSpinBox_leftEtlOffset.setValue(self.parameters["etl_l_offset"])
        self.doubleSpinBox_rightEtlOffset.setValue(self.parameters["etl_r_offset"])
        self.doubleSpinBox_leftEtlDelay.setValue(self.parameters["etl_l_delay"])
        self.doubleSpinBox_rightEtlDelay.setValue(self.parameters["etl_r_delay"])
        self.doubleSpinBox_leftEtlRising.setValue(self.parameters["etl_l_ramp_rising"])
        self.doubleSpinBox_rightEtlRising.setValue(self.parameters["etl_r_ramp_rising"])
        self.doubleSpinBox_leftEtlFalling.setValue(self.parameters["etl_l_ramp_falling"])
        self.doubleSpinBox_rightEtlFalling.setValue(self.parameters["etl_r_ramp_falling"])
        self.doubleSpinBox_leftGalvoAmplitude.setValue(self.parameters["galvo_l_amplitude"])
        self.doubleSpinBox_rightGalvoAmplitude.setValue(self.parameters["galvo_r_amplitude"])
        self.doubleSpinBox_leftGalvoOffset.setValue(self.parameters["galvo_l_offset"])
        self.doubleSpinBox_rightGalvoOffset.setValue(self.parameters["galvo_r_offset"])
        self.doubleSpinBox_leftGalvoFrequency.setValue(self.parameters["galvo_l_frequency"])
        self.doubleSpinBox_rightGalvoFrequency.setValue(self.parameters["galvo_r_frequency"])
        self.doubleSpinBox_leftGalvoDutyCycle.setValue(self.parameters["galvo_l_duty_cycle"])
        self.doubleSpinBox_rightGalvoDutyCycle.setValue(self.parameters["galvo_r_duty_cycle"])
        self.doubleSpinBox_leftGalvoPhase.setValue(self.parameters["galvo_l_phase"])
        self.doubleSpinBox_rightGalvoPhase.setValue(self.parameters["galvo_r_phase"])
        self.doubleSpinBox_samplerate.setValue(self.parameters["samplerate"])
        self.doubleSpinBox_sweeptime.setValue(self.parameters["sweeptime"])
     
    def get_camera_temp(self):
        self.camera.get_temperature()
        self.label_cameraTemp.setText("{} \u2103".format(self.camera.camTemp.value))
        self.label_ccdTemp.setText("{} \u2103".format(self.camera.ccdTemp.value/10))
        self.label_powerSupplyTemp.setText("{} \u2103".format(self.camera.powTemp.value))
        
    def get_camera_exposure(self):
        self.camera.get_exposure_time()
        
    def set_camera_window(self, cameraWindow):
        self.cameraWindow = cameraWindow
        
    def setDataConsumer(self, consumer, wait, consumerType, updateFlag):
        """ Use this function when we will need flags or if we have multiple consumers"""
        self.consumers.append(consumer)
        self.consumers.append(wait)
        self.consumers.append(consumerType)
        self.consumers.append(updateFlag)
        
        
    def previewThread(self):
        continuer = True
        for i in range(0, len(self.consumers), 4):
            if self.consumers[i+2] == "CameraWindow":
                while continuer:
                    
                    '''Getting the data to send to the AO'''
                    leftGalvoVoltage = self.parameters['galvo_l_offset']
                    rightGalvoVoltage = self.parameters['galvo_r_offset']
                    leftEtlVoltage = self.parameters['etl_l_offset']
                    rightEtlVoltage = self.parameters['etl_r_offset']
                    leftLaserVoltage = 0
                    rightLaserVoltage = 0
                    
                    '''Laser status override already dealt with by enabling 
                       pushButtons in lasers' functions'''
                    if self.allLasersOn == True:
                        leftLaserVoltage = self.parameters['laser_l_voltage']
                        rightLaserVoltage = self.parameters['laser_r_voltage']
                    
                    if self.leftLaserOn == True:
                        leftLaserVoltage = self.parameters['laser_l_voltage']
                    
                    if self.rightLaserOn == True:
                        rightLaserVoltage = self.parameters['laser_r_voltage']
                    
                    '''Writing the data'''
                    preview_galvos_etls_waveforms = np.stack((np.array([rightGalvoVoltage]),
                                                              np.array([leftGalvoVoltage]),
                                                              np.array([rightEtlVoltage]),
                                                              np.array([leftEtlVoltage])))
                    
                    preview_lasers_waveforms = np.stack((np.array([rightLaserVoltage]),
                                                         np.array([leftLaserVoltage])))
                    
                    
                    self.preview_lasers_task.write(preview_lasers_waveforms, auto_start=True)
                    self.preview_galvos_etls_task.write(preview_galvos_etls_waveforms, auto_start=True)
                    
                    '''Retrieving image from camera and putting it in its queue'''
                    if self.previewModeStarted == True:
                        frame = self.camera.retrieve_single_image()*1.0
        
                        try:
                            self.consumers[i].put(frame)
                        except self.consumers[i].Full:
                            print("Queue is full")
                    elif self.previewModeStarted == False:
                        continuer = False
        
            
        self.camera.cancel_images()
        self.camera.set_recording_state(0)
        self.camera.free_buffer()
        
        self.preview_lasers_task.stop()
        self.preview_galvos_etls_task.stop()
        
        self.preview_lasers_task.close()
        self.preview_galvos_etls_task.close()
        
        self.pushButton_getSingleImage.setEnabled(True)
        self.pushButton_startStack.setEnabled(True)
        self.pushButton_startLiveMode.setEnabled(True)
        self.pushButton_startPreviewMode.setEnabled(True)
        self.pushButton_stopPreviewMode.setEnabled(False)
        
        print('Preview mode stopped')
        
    def closeEvent(self, event):
        '''Making sure that everything is closed when the user exits the software'''

        if self.allLasersOn == True:
            self.lasers_off()
            
        if self.leftLaserOn == True:
            self.left_laser_off()
            
        if self.rightLaserOn == True:
            self.right_laser_off()
            
        if self.previewModeStarted == True:
            self.stop_preview_mode()
            
        if self.liveModeStarted == True:
            self.stop_live_mode()
            
        if self.cameraOn == True:
            self.close_camera()
            
        event.accept()
        
        
    def select_directory(self):
        options = QFileDialog.Options()
        options |= QFileDialog.DontResolveSymlinks
        options |= QFileDialog.ShowDirsOnly
        self.save_directory = QFileDialog.getExistingDirectory(self, 'Choose Directory', '', options)
        
        if self.save_directory != '':
            self.label_currentDirectory.setText(self.save_directory)
            self.lineEdit_filename.setEnabled(True)
            self.lineEdit_filename.setText('')
            self.savingAllowed = True
        else:
            self.label_currentDirectory.setText('None specified')
            self.lineEdit_filename.setEnabled(False)
            self.lineEdit_filename.setText('Select directory first')
            self.savingAllowed = False
        
        
        

class CameraWindow(queue.Queue):
    
    def __init__(self):
        
        queue.Queue.__init__(self,2)   #Queue of size 2
        
        self.lines = 2160
        self.columns = 2560
        self.container = np.zeros((self.lines, self.columns)) 
        self.imv = pg.ImageView(None, 'Camera Window')
        self.imv.setWindowTitle('Camera Window')
        self.scene = self.imv.scene
        self.imv.show()
        self.imv.setImage(np.transpose(self.container))
        
    def update(self):
        try:
            frame = self.get(False)
            self.imv.setImage(np.transpose(frame))
        except queue.Empty:
            pass
           
           
           
           
class FrameSaver():
    
    def __init__(self, filename):
        self.filename = filename
        self.f = h5py.File(self.filename, 'a')
        
        
    def set_block_size(self, block_size):
        self.block_size = block_size
        self.queue = queue(2*block_size)
        
    def set_dataset_name(self,path_name):
        self.path_name = path_name
        self.f.create_group(self.path_name)   #Create sub-group (folder)
        
    def add_attribute(self, attribute, value):
        self.f[self.path_name].attrs[attribute]=value
        
    def start_saving(self):
        self.f.close()
        self.parent_conn, child_conn = multiprocessing.Pipe()
        self.p = multiprocessing.Process(target=save_process, args = (self.queue, self.block_size, self.path_name, child_conn, self.filename))
        self.p.start()
        
    def stop_saving(self):
        '''Stop saving, join save thread and clear data in queue to prepare for next round '''
        self.parent_conn.send([False])
        self.p.join()
        
    def put(self, value, flag):
        self.queue.put(value, flag)
        
    def check_existing_files(self, path_name, scan_type):
        in_loop = True
        counter = 0
        
        while in_loop:
            counter = counter +1
            self.path_name = posixpath.join(path_name, scan_type + '_' + str(counter))
            in_loop = self.path_name in self.f
            
        return counter
    


def save_process(queue, block_size, datasetname, conn, filename):
    
    f = h5py.File(filename, 'a')
    save_index = 0
    index = 0
    started = True
    
    while started:
        try:
            '''We block for 2s on no data to optimize CPU and avoid running the while loop for no reason'''
            frame = queue.get(True,1)
            
            '''Create data buffer '''
            if frame.ndim > 1:
                if index == 0:
                    buffer = np.zeros((frame.shape[0], frame.shape[1], block_size))
                buffer[:, :, index] = frame
                
            else:
                if index == 0:
                    buffer = np.zeros((frame.shape[0], block_size))
                buffer[:, index] = frame
                
            index = (index+1) % block_size  #Index returns to 0 when reaching block_size
            
            '''Add to file when index returns to 0'''
            if index == 0:
                f[posixpath.join(datasetname, 'scan'+u'%05d' % save_index)] = buffer
                save_index = save_index +1
                conn.send([save_index, queue.qsize()])
                
        except:
            print('No frame')
            
            if conn.poll():
                print('Checking connection status')
                started = conn.recv()[0]
                
    '''Save last acquisition if incomplete (did not reach block_size)'''
    if index != 0:
        if frame.ndim > 1:
            buffer2 = np.zeros((frame.shape[0], frame.shape[1], index+1))  #+1 to take into account the index 0
            buffer2 = buffer[:,:,0:index]
        
        else:
            buffer2 = np.zeros((frame.shape[0], index+1))    #+1 to take into account the index 0
            buffer2 = buffer[:, 0:index]
            
        f[posixpath.join('\scans', datasetname, 'scan'+u'%05d' % save_index)] = buffer2  #Path slightly changed
        f.close()
                
            

          
        