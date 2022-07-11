'''
Created on May 16, 2019

@authors: Pierre Girard-Collins & flesage
'''

import sys
sys.path.append(".")
#print(sys.path)

import logging

from PyQt5.QtCore import pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import QApplication
from gui.controller import Controller_MainWindow

import qdarkstyle
from qdarkstyle.light.palette import LightPalette
from qdarkstyle.dark.palette import DarkPalette

logging.basicConfig(format="%(message)s", level=logging.INFO)

# This block permits messages display of errors occurring in all the files
sys._excepthook = sys.excepthook
def exception_hook(exctype, value, traceback):
    '''Permits messages display of errors occurring in all the files'''
    print(exctype, value, traceback)
    sys._excepthook(exctype, value, traceback)
    sys.exit(1)
sys.excepthook = exception_hook

@pyqtSlot(str)
def set_app_stylesheet(stylesheet_code:str):
    '''Function that allows stylesheet selection for the app'''
    if stylesheet_code == 'light':
        app.setStyleSheet(qdarkstyle.load_stylesheet(qt_api='pyqt5', palette=LightPalette))
    elif stylesheet_code == 'dark':
        app.setStyleSheet(qdarkstyle.load_stylesheet(qt_api='pyqt5', palette=DarkPalette))

# Initializing the app, controller (class which connects GUI to features)
app = QApplication(sys.argv)
app.setStyleSheet(qdarkstyle.load_stylesheet(qt_api='pyqt5', palette=LightPalette))
controller = Controller_MainWindow()
controller.sig_beep.connect(app.beep) #connection for beep sounds
controller.sig_stylesheet.connect(set_app_stylesheet) #connection for app stylesheet

# Show controller UI and execute main event loop
controller.show()
sys.exit(app.exec_())
