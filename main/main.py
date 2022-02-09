'''
Created on May 16, 2019

@authors: Pierre Girard-Collins & flesag
'''
import sys
sys.path.append(".")

#from matplotlib.colors import LightSource
import qdarkstyle
from qdarkstyle.dark.palette import DarkPalette
from qdarkstyle.light.palette import LightPalette

from PyQt5.QtWidgets import QApplication
from gui.control import Controller_MainWindow
import pyqtgraph as pg

def set_app_stylesheet(stylesheet_code):
    '''Function that allows stylesheet selection for the app'''
    if stylesheet_code == 0:
        app.setStyleSheet(qdarkstyle.load_stylesheet(qt_api='pyqt5', palette=LightPalette))
    elif stylesheet_code == 1:
        app.setStyleSheet(qdarkstyle.load_stylesheet(qt_api='pyqt5', palette=DarkPalette))
   

'''This block permits messages display of errors occurring in all the files
   related to the software (not only in the main ones, such as control.py)'''
sys._excepthook = sys.excepthook
def exception_hook(exctype, value, traceback):
    print(exctype, value, traceback)
    sys._excepthook(exctype, value, traceback)
    sys.exit(1)
sys.excepthook = exception_hook

'''Initializing the app, controller (class which connects GUI to features), and
   at the same time the camera window (where images are displayed)'''
app = QApplication(sys.argv)
app.setStyleSheet(qdarkstyle.load_stylesheet(qt_api='pyqt5', palette=LightPalette))
controller = Controller_MainWindow()
controller.sig_beep.connect(app.beep) #connection for beep sounds
controller.sig_stylesheet.connect(set_app_stylesheet) #connection for app stylesheet

'''Setting QTimer. update() function of camera window (retrieves an image in its 
   queue and displays it) executes at each time interval specified in 
   timer.start()'''
timer = pg.QtCore.QTimer()
timer.timeout.connect(controller.camera_window.update)
timer.start(100)

'''Initially, the only consumer is camera_window. Later when the user wished to
   save images, a second consumer (FrameSaver) is set in controller'''
controller.set_data_consumer(controller.camera_window, False, "CameraWindow", True)

'''Shows the UI of controller and executes'''
controller.show()
app.exec_()

'''Timer is stopped when the user closes the GUI'''
timer.stop()


