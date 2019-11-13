'''
Created on May 16, 2019

@author: flesage
'''
import sys
sys.path.append("..")

from PyQt5.QtWidgets import QApplication
from gui.control import Controller, CameraWindow
import pyqtgraph as pg

#This block is to show the error messages that do not print normally
sys._excepthook = sys.excepthook
def exception_hook(exctype, value, traceback):
    print(exctype, value, traceback)
    sys._excepthook(exctype, value, traceback)
    sys.exit(1)
sys.excepthook = exception_hook

app = QApplication(sys.argv)
controller = Controller()
cameraWindow = CameraWindow()
timer = pg.QtCore.QTimer()
timer.timeout.connect(cameraWindow.update)
timer.start(100)

#controller.set_camera_window(cameraWindow)
controller.setDataConsumer(cameraWindow, False, "CameraWindow", True)
controller.show()
app.exec_()  



timer.stop()

'''Making sure that everything is closed'''

if controller.allLasersOn == True:
    controller.lasers_off()
    
if controller.leftLaserOn == True:
    controller.left_laser_off()
    
if controller.rightLaserOn == True:
    controller.right_laser_off()
    
if controller.previewModeStarted == True:
    controller.stop_preview_mode()
    
if controller.liveModeStarted == True:
    controller.stop_live_mode()
    
if controller.cameraOn == True:
    controller.close_camera()
    
