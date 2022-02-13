'''
Created on February 8, 2022
'''

import sys
sys.path.append(".")

import copy
from configparser import ConfigParser

class Lasers:
        
    '''Default hardware configuration'''
    _lasers = {}
    _lasers['Terminal'] = '/Dev7/ao0:1'
    _lasers["Voltage Left"] = 0.905   # In Volts
    _lasers["Voltage Right"] = 0.935  # In Volts

    def __init__(self):
        self.cfg_default()
        self.cfg_read()
        
        self.error = 0
        self.error_message = ""
        self.laser_on = False
        self.left_laser_activated = False
        self.right_laser_activated = False
    

    def cfg_default(self):
        # Copy default values to current values
        self.lasers = copy.deepcopy(self._lasers)

    def cfg_read(self):
        cfg = ConfigParser()
        cfg.optionxform = str
        cfg.read('config.ini')
        for key, value in cfg['Lasers'].items():
            self.lasers[key] = value

    def cfg_write(self):
        cfg = ConfigParser()
        cfg.optionxform = str
        cfg.read('config.ini')
        for key in self.lasers:
            cfg.set('Lasers', str(key), str(self.lasers[key]))
        with open('config.ini', 'w') as output_file:
            cfg.write(output_file)

    def turn_laser_on(self):
        self.laser_on = True
        self.left_laser_activated = True
        self.right_laser_activated = True

    def turn_laser_off(self):
        self.laser_on = False
        self.left_laser_activated = False
        self.right_laser_activated = False

mylasers = Lasers()
mylasers.cfg_write()