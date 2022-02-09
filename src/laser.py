'''
Created on February 8, 2022
'''

import os
import sys
sys.path.append(".")

class Laser:
    
    def __init__(self):
        self.error = 0
        self.error_message = ""
        self.both_lasers_activated = False
        self.left_laser_activated = False
        self.right_laser_activated = False
        self.laser_on = False
    
    def turn_laser_on(self):
        self.both_lasers_activated = True
        self.left_laser_activated = True
        self.right_laser_activated = True
        self.laser_on = True

    def turn_laser_off(self):
        self.both_lasers_activated = False
        self.left_laser_activated = False
        self.right_laser_activated = False
        self.laser_on = False
