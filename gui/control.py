'''
Created on May 22, 2019

@author: flesage
'''

import sys
sys.path.append("..")

import os
import numpy as np
from PyQt5 import QtGui
from PyQt5 import uic
from PyQt5.QtWidgets import QWidget, QFileDialog
from PyQt5.QtWidgets import QApplication, QMainWindow, QMenu, QVBoxLayout, QSizePolicy, QMessageBox, QPushButton
from PyQt5.QtGui import QIcon

import nidaqmx
from nidaqmx.constants import AcquisitionType

from src.hardware import AOETLGalvos
from src.hardware import Motors
#from zaber.serial import AsciiSerial, AsciiDevice, AsciiCommand

parameters = dict()
parameters["samplerate"]=100
parameters["sweeptime"]=0.4
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

class Controller(QWidget):
    '''
    classdocs
    '''


    def __init__(self):
        QWidget.__init__(self)
        basepath= os.path.join(os.path.dirname(__file__))
        uic.loadUi(os.path.join(basepath,"control.ui"), self)
        
        self.motor1 = Motors(1, 'COM3')             #Vertical motor
        self.motor2 = Motors(2, 'COM3')             #Horizontal motor for sample motion
        self.motor3 = Motors(3, 'COM3')             #Horizontal motor for detection arm motion
        
        #Right values for the origin to determine
        self.originX = 533333
        self.originZ = 0
        self.focus = 533333
        
        #For optimized parameters calculations
        self.frequency=0
        self.samplerate=0
        self.sweeptime=0
        self.delay=0
        
        #Decimal number is the same for all widgets for a specific unit
        self.decimals = self.doubleSpinBox_incrementHorizontal.decimals()
        
        
        self.pushButton_startLive.clicked.connect(self.start_live_mode)
        self.pushButton_stopLive.clicked.connect(self.stop_live_mode)
        self.pushButton_startContinuous.clicked.connect(self.start_continuous_mode)
        self.pushButton_stopContinuous.clicked.connect(self.stop_continuous_mode)
        self.pushButton_startAcquisition.clicked.connect(self.start_acquisition_mode)
        self.pushButton_stopAcquisition.clicked.connect(self.stop_acquisition_mode)
        
        self.pushButton_MotorUp.clicked.connect(self.move_up)
        self.pushButton_MotorDown.clicked.connect(self.move_down)
        self.pushButton_MotorRight.clicked.connect(self.move_right)
        self.pushButton_MotorLeft.clicked.connect(self.move_left)
        self.pushButton_MotorOrigin.clicked.connect(self.move_to_origin)
        
        #Unit value changed to implement
        self.comboBox_unit.insertItems(0,["cm","mm","\u03BCm"])
        self.comboBox_unit.setCurrentIndex(1)
        self.comboBox_unit.currentTextChanged.connect(self.update_all)
        
        #To initialize the widget that are updated by a change of unit
        self.update_all()
        #To initialize the properties of the other widgets
        self.initialize_other_widgets()
        
        self.pushButton_moveHome.clicked.connect(self.move_home)
        self.pushButton_moveMaxPosition.clicked.connect(self.move_to_maximum_position)
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
        
        self.pushButton_calculateOptimized.clicked.connect(self.synchronize_ramps)
        self.pushButton_setOptimized.clicked.connect(self.set_optimized_parameters)
        
        self.pushButton_lasersOn.clicked.connect(self.lasers_on)
        self.pushButton_lasersOff.clicked.connect(self.lasers_off)
        self.pushButton_leftLaserOn.clicked.connect(self.left_laser_on)
        self.pushButton_leftLaserOff.clicked.connect(self.left_laser_off)
        self.pushButton_rightLaserOn.clicked.connect(self.right_laser_on)
        self.pushButton_rightLaserOff.clicked.connect(self.right_laser_off)
        
        
    def start_live_mode(self):
        self.pushButton_startLive.setEnabled(False)
        self.pushButton_stopLive.setEnabled(True)
        self.pushButton_startContinuous.setEnabled(False)
        self.pushButton_stopContinuous.setEnabled(False)
        self.pushButton_startAcquisition.setEnabled(False)
        self.pushButton_stopAcquisition.setEnabled(False)
        print('Start live mode')
        # Setup from data in gui
        self.ramps=AOETLGalvos(parameters)                  
        self.ramps.create_tasks('FINITE')                           
        self.ramps.create_galvos_waveforms()
        self.ramps.create_etl_waveforms()                   
        self.ramps.write_waveforms_to_tasks()
        self.ramps.run_tasks()                             
        self.ramps.start_tasks()
    
    def stop_live_mode(self):
        self.ramps.stop_tasks()                             
        self.ramps.close_tasks()
        self.pushButton_startLive.setEnabled(True)
        self.pushButton_stopLive.setEnabled(False)
        self.pushButton_startContinuous.setEnabled(True)
        self.pushButton_stopContinuous.setEnabled(False)
        self.pushButton_startAcquisition.setEnabled(True)
        self.pushButton_stopAcquisition.setEnabled(False)
        
    def start_continuous_mode(self):
        self.pushButton_startLive.setEnabled(False)
        self.pushButton_stopLive.setEnabled(False)
        self.pushButton_startContinuous.setEnabled(False)
        self.pushButton_stopContinuous.setEnabled(True)
        self.pushButton_startAcquisition.setEnabled(False)
        self.pushButton_stopAcquisition.setEnabled(False)
        print('Start continuous mode')
        # Setup from data in gui
        self.ramps=AOETLGalvos(parameters)                  
        self.ramps.create_tasks('CONTINUOUS')                           
        self.ramps.create_galvos_waveforms()
        self.ramps.create_etl_waveforms()                   
        self.ramps.write_waveforms_to_tasks()                            
        self.ramps.start_tasks()
        
    def stop_continuous_mode(self):
        self.ramps.stop_tasks()                             
        self.ramps.close_tasks()
        self.pushButton_startLive.setEnabled(True)
        self.pushButton_stopLive.setEnabled(False)
        self.pushButton_startContinuous.setEnabled(True)
        self.pushButton_stopContinuous.setEnabled(False)
        self.pushButton_startAcquisition.setEnabled(True)
        self.pushButton_stopAcquisition.setEnabled(False)
        
    def start_acquisition_mode(self):
        '''Detextion arm (self.motor3) to be implemented 
        
        Note: check if there's a NI-Daqmx function to repeat the data sent instead of closing each time the task. This would be useful
        if it is possible to break a task with self.stop_acquisition_mode
        
        An option to scan forward or backward should be implemented
        A progress bar would be nice
        '''
        self.pushButton_startLive.setEnabled(False)
        self.pushButton_stopLive.setEnabled(True)
        self.pushButton_startContinuous.setEnabled(False)
        self.pushButton_stopContinuous.setEnabled(False)
        self.pushButton_startAcquisition.setEnabled(False)
        self.pushButton_stopAcquisition.setEnabled(True)
        print('Start acquisition mode')
        for i in range(int(self.doubleSpinBox_planeNumber.value())):
            self.ramps=AOETLGalvos(parameters)                  
            self.ramps.create_tasks('FINITE')                           
            self.ramps.create_galvos_waveforms()
            self.ramps.create_etl_waveforms()                   
            self.ramps.write_waveforms_to_tasks()
            self.ramps.run_tasks()                             
            self.ramps.start_tasks()
            self.ramps.stop_tasks()                             
            self.ramps.close_tasks()
            #Sample motion
            if self.comboBox_acquisitionDirection.currentText() == 'Forward':
                self.motor2.move_relative_position(-self.doubleSpinBox_planeStep.value(),'\u03BCm')
            elif self.comboBox_acquisitionDirection.currentText() == 'Backward':
                self.motor2.move_relative_position(self.doubleSpinBox_planeStep.value(),'\u03BCm')
        
        print('Acquisition done')
        #Current camera position update
        self.label_currentHorizontalNumerical.setText("{} {}".format(round(self.motor2.current_position(self.comboBox_unit.currentText()),self.decimals), self.comboBox_unit.currentText())) 
        self.pushButton_startLive.setEnabled(True)
        self.pushButton_stopLive.setEnabled(False)
        self.pushButton_startContinuous.setEnabled(True)
        self.pushButton_stopContinuous.setEnabled(False)
        self.pushButton_startAcquisition.setEnabled(True)
        self.pushButton_stopAcquisition.setEnabled(False)
            
    def stop_acquisition_mode(self):
        '''Useless function for now. Would be useful to find a way to stop acquisition mode before it's done. Note: check how to break a NI-Daqmx task '''
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
        parameters["galvo_l_frequency"] = self.frequency
        parameters["galvo_r_frequency"] = parameters["galvo_l_frequency"]
        parameters["etl_l_delay"] = self.delay
        parameters["etl_r_delay"] = parameters["etl_l_delay"]
        
    def initialize_other_widgets(self):
        '''Initializes the properties of the widgets that are not upadted by a change of units, so the widgets that cannot be initialize with self.update_all() '''
        self.pushButton_stopLive.setEnabled(False)
        self.pushButton_stopContinuous.setEnabled(False)
        self.pushButton_stopAcquisition.setEnabled(False)
        self.pushButton_setOptimized.setEnabled(False)
        
        #Might change it for a spin box
        self.doubleSpinBox_planeNumber.setDecimals(0)
        self.doubleSpinBox_planeNumber.setMaximum(101600)
        self.doubleSpinBox_planeNumber.setMinimum(1)
        self.doubleSpinBox_planeNumber.setSingleStep(1)
        
        self.doubleSpinBox_planeStep.setSuffix(' \u03BCm')
        self.doubleSpinBox_planeNumber.setDecimals(0)
        self.doubleSpinBox_planeStep.setMaximum(101600)
        self.doubleSpinBox_planeStep.setSingleStep(1)
        
        self.comboBox_acquisitionDirection.insertItems(0,['Forward','Backward'])
        self.comboBox_acquisitionDirection.setCurrentIndex(0)
        
        self.doubleSpinBox_galvoFrequency.setMaximum(130)
        self.doubleSpinBox_galvoFrequency.setSuffix(' Hz')
        self.doubleSpinBox_galvoFrequency.setSingleStep(5)
        
        self.spinBox_lines.setMinimum(1)
        self.spinBox_lines.setMaximum(9999)
        
        self.spinBox_columns.setMinimum(1)
        self.spinBox_columns.setMaximum(9999)
        
        self.pushButton_lasersOff.setEnabled(False)
        self.pushButton_leftLaserOff.setEnabled(False)
        self.pushButton_rightLaserOff.setEnabled(False)
        
    def lasers_on(self):
        self.pushButton_lasersOn.setEnabled(False)
        self.pushButton_lasersOff.setEnabled(True)
        self.pushButton_leftLaserOn.setEnabled(False)
        self.pushButton_rightLaserOn.setEnabled(False)
        self.lasers_task = nidaqmx.Task()
        self.lasers_task.ao_channels.add_ao_voltage_chan('/Dev2/ao0:1')
        waveforms = np.stack(([0.935],[0.905]))
        self.lasers_task.write(waveforms)
        print('Lasers on')
        
    def lasers_off(self):
        self.pushButton_lasersOn.setEnabled(True)
        self.pushButton_lasersOff.setEnabled(False)
        self.pushButton_leftLaserOn.setEnabled(True)
        self.pushButton_rightLaserOn.setEnabled(True)
        waveforms = np.stack(([0],[0]))
        self.lasers_task.write(waveforms)
        self.lasers_task.stop()
        self.lasers_task.close()
        print('Lasers off')
        
    def left_laser_on(self):
        self.pushButton_lasersOn.setEnabled(False)
        self.pushButton_leftLaserOn.setEnabled(False)
        self.pushButton_leftLaserOff.setEnabled(True)
        self.left_laser = nidaqmx.Task()
        self.left_laser.ao_channels.add_ao_voltage_chan('/Dev2/ao1')
        self.left_laser.write(0.905)
        print('Left laser on')
        
    def left_laser_off(self):
        self.left_laser.write(0)
        self.left_laser.stop()
        self.left_laser.close()
        print('Left laser off')
        self.pushButton_leftLaserOn.setEnabled(True)
        self.pushButton_leftLaserOff.setEnabled(False)
        if self.pushButton_rightLaserOn.isEnabled() == True:
            self.pushButton_lasersOn.setEnabled(True)
        
    def right_laser_on(self):
        self.pushButton_lasersOn.setEnabled(False)
        self.pushButton_rightLaserOn.setEnabled(False)
        self.pushButton_rightLaserOff.setEnabled(True)
        self.right_laser = nidaqmx.Task()
        self.right_laser.ao_channels.add_ao_voltage_chan('/Dev2/ao0')
        self.right_laser.write(0.935)
        print('Left laser on')
        
    def right_laser_off(self):
        self.right_laser.write(0)
        self.right_laser.stop()
        self.right_laser.close()
        print('Left laser off')
        self.pushButton_rightLaserOn.setEnabled(True)
        self.pushButton_rightLaserOff.setEnabled(False)
        if self.pushButton_leftLaserOn.isEnabled() == True:
            self.pushButton_lasersOn.setEnabled(True)
        
        
        