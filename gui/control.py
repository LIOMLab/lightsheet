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

from src.hardware import AOETLGalvos
from src.hardware import Motors
#from zaber.serial import AsciiSerial, AsciiDevice, AsciiCommand

parameters = dict()
parameters["samplerate"]=1000
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
        
      
        
        self.pushButton_startLive.clicked.connect(self.start_live_mode)
        self.pushButton_startLive.clicked.connect(lambda: self.pushButton_startLive.setEnabled(False) )
        self.pushButton_startLive.clicked.connect(lambda: self.pushButton_stopLive.setEnabled(True) )
        
        self.pushButton_stopLive.clicked.connect(self.stop_live_mode)
        self.pushButton_stopLive.setEnabled(False)
        self.pushButton_stopLive.clicked.connect(lambda: self.pushButton_stopLive.setEnabled(False) )
        self.pushButton_stopLive.clicked.connect(lambda: self.pushButton_startLive.setEnabled(True) )
        
        self.pushButton_MotorUp.clicked.connect(self.move_up)
        self.pushButton_MotorDown.clicked.connect(self.move_down)
        self.pushButton_MotorRight.clicked.connect(self.move_backward)
        self.pushButton_MotorLeft.clicked.connect(self.move_forward)
        self.pushButton_MotorOrigin.clicked.connect(self.move_to_origin)
        
        
        
        #Unit value changed to implement
        self.comboBox_unit.insertItems(0,["cm","mm","\u03BCm","\u03BCStep"])
        self.comboBox_unit.setCurrentIndex(1)
        
        self.pushButton_moveHome.clicked.connect(self.move_home)
        
        self.pushButton_moveMaxPosition.clicked.connect(self.move_to_maximum_position)

        self.doubleSpinBox_incrementHorizontal.setSuffix(" {}".format(self.comboBox_unit.currentText()))
        self.doubleSpinBox_incrementHorizontal.setDecimals(3)
        self.doubleSpinBox_incrementHorizontal.setSingleStep(1)
        self.doubleSpinBox_incrementHorizontal.setValue(1)
        
        self.doubleSpinBox_incrementVertical.setSuffix(" {}".format(self.comboBox_unit.currentText()))
        self.doubleSpinBox_incrementVertical.setDecimals(3)
        self.doubleSpinBox_incrementVertical.setSingleStep(1)
        self.doubleSpinBox_incrementVertical.setValue(1)
        
        self.label_currentHorizontalNumerical.setText("{} {}".format(self.motor2.current_position(self.comboBox_unit.currentText()), self.comboBox_unit.currentText()))
        
        self.label_currentHeightNumerical.setText("{} {}".format(self.motor1.current_position(self.comboBox_unit.currentText()), self.comboBox_unit.currentText()))
        
        self.pushButton_setAsOrigin.clicked.connect(self.set_origin )
        
        self.doubleSpinBox_choosePosition.setSuffix(" {}".format(self.comboBox_unit.currentText()))
        self.doubleSpinBox_choosePosition.setDecimals(3)
        self.doubleSpinBox_choosePosition.setSingleStep(1)
        
        self.doubleSpinBox_chooseHeight.setSuffix(" {}".format(self.comboBox_unit.currentText()))
        self.doubleSpinBox_chooseHeight.setDecimals(3)
        self.doubleSpinBox_chooseHeight.setSingleStep(1)
        
        #Motion of the detection arm to implement when clicked (self.motor3)
        self.pushButton_movePosition.clicked.connect(lambda: self.motor2.move_absolute_position(self.doubleSpinBox_choosePosition.value(),self.comboBox_unit.currentText()))
        
        self.pushButton_moveHeight.clicked.connect(lambda: self.motor1.move_absolute_position(self.doubleSpinBox_chooseHeight.value(),self.comboBox_unit.currentText()))

        
    def start_live_mode(self):

        print('start live mode')
        # Setup from data in gui
        self.ramps=AOETLGalvos(parameters)                  
        self.ramps.create_tasks()                           
        self.ramps.create_galvos_waveforms()                
        #plt.plot(range(len(self.ramps.galvo_l_waveform)),self.ramps.galvo_l_waveform)
        #plt.plot(range(len(self.ramps.galvo_r_waveform)),self.ramps.galvo_r_waveform)
        self.ramps.create_etl_waveforms()                   
        self.ramps.write_waveforms_to_tasks()
        self.ramps.run_tasks()                             
        self.ramps.start_tasks()                           
        #self.ramps.start_tasks()

    
    def stop_live_mode(self):
        self.ramps.stop_tasks()                             
        self.ramps.close_tasks()                            
    
    def move_up(self):
        print('Moving up')
        self.motor1.move_relative_position(-self.doubleSpinBox_incrementVertical.value(),self.comboBox_unit.currentText())
#        port = AsciiSerial("COM3")
#        command = AsciiCommand("home")
#        port.write(command)
        
    def move_down(self):
        print ('Moving down')
        self.motor1.move_relative_position(self.doubleSpinBox_incrementVertical.value(),self.comboBox_unit.currentText())

    def move_backward(self):
        #Motion of the detection arm to implement (self.motor3)
        print ('Moving backward')
        self.motor2.move_relative_position(self.doubleSpinBox_incrementHorizontal.value(),self.comboBox_unit.currentText())
    
    def move_forward(self):
        #Motion of the detection arm to implement (self.motor3)
        print ('Moving forward')
        self.motor2.move_relative_position(-self.doubleSpinBox_incrementHorizontal.value(),self.comboBox_unit.currentText())
        
    def move_to_origin(self):
        #Motion of the detection arm to implement (self.motor3)
        print('Moving to origin')
        self.motor2.move_absolute_position(self.originX,'\u03BCStep')
        self.motor1.move_absolute_position(self.originZ,'\u03BCStep')
    
    def move_home(self):
        self.motor1.move_home()
        self.motor2.move_home()
        self.motor3.move_home()
    
    def move_to_maximum_position(self):
        self.motor3.move_maximum_position()
        self.motor2.move_maximum_position()
        self.motor1.move_maximum_position()
    
    def set_origin(self):
        self.originX = self.motor2.position_to_data(self.motor2.current_position(self.comboBox_unit.currentText()),self.comboBox_unit.currentText())
        self.originZ = 1066666 - self.motor1.position_to_data(self.motor1.current_position(self.comboBox_unit.currentText()),self.comboBox_unit.currentText())
        print('Origin set')