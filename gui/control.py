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
        print ('Moving up')
        distance = self.lineEdit_MotorStep.text()
        print(distance)
#        port = AsciiSerial("COM3")
#        command = AsciiCommand("home")
#        port.write(command)
        
    def move_down(self):
        print ('Moving down')

    def move_backward(self):
        print ('Moving backward')
    
    def move_forward(self):
        print ('Moving forward')       