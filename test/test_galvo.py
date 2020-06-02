'''
Created on May 16, 2019

@authors: Pierre Girard-Collins & flesage
'''
import sys
sys.path.append("..")

from PyQt5.QtWidgets import QApplication
from gui.control import Controller, CameraWindow
import pyqtgraph as pg

'''This block permits messages display of errors occurring in all the files
   related to the software (not only in the main ones, such as control.py)'''
sys._excepthook = sys.excepthook
def exception_hook(exctype, value, traceback):
    print(exctype, value, traceback)
    sys._excepthook(exctype, value, traceback)
    sys.exit(1)
sys.excepthook = exception_hook

'''Initializing the app, controller (class which connects GUI to features), and
   camera window (where images are displayed)'''
app = QApplication(sys.argv)
controller = Controller()
camera_window = CameraWindow()
controller.set_camera_window(camera_window)

'''Setting QTimer. update() function of camera window (retrieves an image in its 
   queue and displays it) executes at each time interval specified in 
   timer.start()'''
timer = pg.QtCore.QTimer()
timer.timeout.connect(camera_window.update)
timer.start(100)

'''Initially, the only consumer is camera_window. Later when the user wished to
   save images, a second consumer (FrameSaver) is set in controller'''
controller.set_data_consumer(controller.camera_window, False, "CameraWindow", True)

'''Shows the UI of controller and executes'''
controller.show()
app.exec_()  

'''Timer is stopped when the user closes the GUI'''
timer.stop()