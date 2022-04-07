'''
Created on February 8, 2022
'''

import sys
sys.path.append(".")

import copy
import numpy as np

import nidaqmx
#from nidaqmx.constants import AcquisitionType, LineGrouping, Edge

from src.config import cfg_read, cfg_write

class Lasers:
    '''Class for generating and sending AO signals to modulate lasers'''

    # Default configurable settings
    _cfg_settings = {}
    _cfg_settings['Lasers Terminals'] = '/Dev7/ao0:1'
    _cfg_settings['Laser Left Voltage'] = 0.0           # In Volts
    _cfg_settings['Laser Right Voltage'] = 0.0          # In Volts

    def __init__(self):
        # Error status
        self.error = 0
        self.error_message = ''

        self.lasers_task = None
        self.lasers_waveforms = None

        # State flags
        self.laser_left_is_on = False
        self.laser_right_is_on = False

        # Set configurable settings to default values
        self.cfg_settings = copy.deepcopy(self._cfg_settings)

        # Update configurable settings with values found in config file
        self.cfg_settings = cfg_read('config.ini', 'Lasers', self.cfg_settings)

        # Assign configurable settings to instance variables
        self.ao_terminals       = str(self.cfg_settings['Lasers Terminals'])
        self.left_amplitude     = float(self.cfg_settings['Laser Left Voltage'])
        self.right_amplitude    = float(self.cfg_settings['Laser Right Voltage'])


    def turn_on(self):
        # Define setpoints
        lasers_setpoints = np.stack((   np.array([self.left_amplitude]),
                                        np.array([self.right_amplitude])     ))
        # Run task
        with nidaqmx.Task(new_task_name = 'lasers_setpoint') as lasers_task:
            lasers_task.ao_channels.add_ao_voltage_chan(self.ao_terminals)
            lasers_task.write(lasers_setpoints, auto_start = True)

    def turn_off(self):
        # Define setpoints
        lasers_setpoints = np.stack((   np.array([0]),
                                        np.array([0])     ))
        # Run task
        with nidaqmx.Task(new_task_name = 'lasers_setpoint') as lasers_task:
            lasers_task.ao_channels.add_ao_voltage_chan(self.ao_terminals)
            lasers_task.write(lasers_setpoints, auto_start = True)
