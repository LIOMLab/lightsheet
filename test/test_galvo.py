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