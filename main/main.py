'''
Created on May 16, 2019

@authors: Pierre Girard-Collins & flesage
'''

import sys
sys.path.append(".")

from PyQt5.QtWidgets import QApplication
from gui.control import Controller_MainWindow

import qdarkstyle
from qdarkstyle.light.palette import LightPalette
from qdarkstyle.dark.palette import DarkPalette


def set_app_stylesheet(stylesheet_code):
    '''Function that allows stylesheet selection for the app'''
    if stylesheet_code == 0:
        app.setStyleSheet(qdarkstyle.load_stylesheet(qt_api='pyqt5', palette=LightPalette))
    elif stylesheet_code == 1:
        app.setStyleSheet(qdarkstyle.load_stylesheet(qt_api='pyqt5', palette=DarkPalette))
   

'''This block permits messages display of errors occurring in all the files
   related to the software (not only in the main ones)'''
sys._excepthook = sys.excepthook
def exception_hook(exctype, value, traceback):
    print(exctype, value, traceback)
    sys._excepthook(exctype, value, traceback)
    sys.exit(1)
sys.excepthook = exception_hook


# Initializing the app, controller (class which connects GUI to features)
app = QApplication(sys.argv)
app.setStyleSheet(qdarkstyle.load_stylesheet(qt_api='pyqt5', palette=LightPalette))
controller = Controller_MainWindow()
controller.sig_beep.connect(app.beep) #connection for beep sounds
controller.sig_stylesheet.connect(set_app_stylesheet) #connection for app stylesheet


# Show controller UI and execute main event loop
controller.show()
sys.exit(app.exec())

