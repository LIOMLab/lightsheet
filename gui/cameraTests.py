import sys
sys.path.append("..")

import os
import numpy as np
from PyQt5 import QtGui
from PyQt5 import uic
from PyQt5.QtWidgets import QWidget, QFileDialog
from PyQt5.QtWidgets import QApplication, QMainWindow, QMenu, QVBoxLayout, QSizePolicy, QMessageBox, QPushButton
from PyQt5.QtGui import QIcon

#import matplotlib.pyplot as plt
import pyqtgraph as pg
import ctypes

#import nidaqmx
#from nidaqmx.constants import AcquisitionType

#from src.hardware import AOETLGalvos
#from src.hardware import Motors
from src.pcoEdge import Camera


class CameraWindow(QWidget):
    '''
    classdocs
    '''


    def __init__(self):
        QWidget.__init__(self)
        basepath= os.path.join(os.path.dirname(__file__))
        uic.loadUi(os.path.join(basepath,"control_v2.ui"), self)
        
        self.camera = Camera()
        
        self.pushButton_startPreviewMode.clicked.connect(self.start_preview_mode)
        self.pushButton_closeCamera.clicked.connect(self.close_camera)
        self.pushButton_stopPreviewMode.clicked.connect(self.stop_preview_mode)
        
        #self.pushButton_stopPreviewMode.setEnabled(False)
        
    #Camera functions 
    
    def start_preview_mode(self):
        self.pushButton_startPreviewMode.setEnabled(False)
        self.pushButton_stopPreviewMode.setEnabled(True)
        self.pushButton_stopPreviewMode.setCheckable(True)
        #self.pushButton_stopPreviewMode.checked(False)
        self.pushButton_closeCamera.setEnabled(False)
        
        self.camera.arm_camera()
         
        self.camera.get_sizes() 
        self.camera.allocate_buffer()    
        self.camera.set_recording_state(1)
        self.camera.insert_buffers_in_queue()
        
    
        print(self.camera.pointers[0].contents.value)
        print(self.camera.pointers[1].contents.value)
        
        
        #self.checked = False
         
        #for i in range(10):
        frame = self.camera.retrieve_single_image()
        #self.graphicsView = pg.ImageView()
        #self.graphicsView.setImage(image)
         
         
        #while self.checked==False:
            #pass
            #frame = self.camera.retrieve_single_image()
            #image = pg.ImageItem(frame)
            #self.graphicsView.setImage(image)
        
        self.camera.cancel_images()
        self.camera.set_recording_state(0)
        self.camera.free_buffer()
            
        self.pushButton_startPreviewMode.setEnabled(True)
        self.pushButton_stopPreviewMode.setEnabled(False)
        self.pushButton_closeCamera.setEnabled(True)
        
    def stop_preview_mode(self):
        self.checked = True
     
    def close_camera(self):
        self.camera.close_camera()
        