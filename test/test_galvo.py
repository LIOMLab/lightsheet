'''
Created on May 16, 2019

@author: flesage
'''
import sys
sys.path.append("..")

from PyQt5.QtWidgets import QApplication
from gui.control import Controller

#This block is to show the error messages that do not print normally
sys._excepthook = sys.excepthook
def exception_hook(exctype, value, traceback):
    print(exctype, value, traceback)
    sys._excepthook(exctype, value, traceback)
    sys.exit(1)
sys.excepthook = exception_hook

app = QApplication(sys.argv)
controller = Controller()
controller.show()
app.exec_()  
