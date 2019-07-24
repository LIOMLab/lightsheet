'''
Created on May 16, 2019

@author: flesage
'''
import sys
sys.path.append("..")

from PyQt5.QtWidgets import QApplication
from gui.control import Controller

app = QApplication(sys.argv)
controller = Controller()
controller.show()
app.exec_()  
