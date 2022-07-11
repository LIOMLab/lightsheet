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
    _cfg_settings['Laser1 Wavelength'] = 405       # In nm
    _cfg_settings['Laser1 Power'] = 0.0            # In Volts
    _cfg_settings['Laser2 Wavelength'] = 405       # in nm
    _cfg_settings['Laser2 Power'] = 0.0            # In Volts

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
        self.laser1_wavelength     = int(self.cfg_settings['Laser1 Wavelength'])
        self.laser1_power          = float(self.cfg_settings['Laser1 Power'])
        self.laser1_active         = False
        self.laser2_wavelength     = int(self.cfg_settings['Laser2 Wavelength'])
        self.laser2_power          = float(self.cfg_settings['Laser2 Power'])
        self.laser2_active         = False

        self._laser1_setpoint = 0
        self._laser2_setpoint = 0


    def laser1_on(self):
        self.laser1_active = True
        self._laser1_setpoint = self.laser1_power
        self._update_setpoints()

    def laser1_off(self):
        self.laser1_active = False
        self._laser1_setpoint = 0
        self._update_setpoints()

    def laser1_toggle(self):
        if self.laser1_active:
            self.laser1_off()
        else:
            self.laser1_on()

    def laser2_on(self):
        self.laser2_active = True
        self._laser2_setpoint = self.laser2_power
        self._update_setpoints()

    def laser2_off(self):
        self.laser2_active = False
        self._laser2_setpoint = 0
        self._update_setpoints()

    def laser2_toggle(self):
        if self.laser2_active:
            self.laser2_off()
        else:
            self.laser2_on()


    def _update_setpoints(self):
        # Setpoints
        lasers_setpoints = np.stack((   np.array([self._laser1_setpoint]),
                                        np.array([self._laser2_setpoint])     ))
        # Run task
        try:
            with nidaqmx.Task(new_task_name = 'lasers_setpoint') as lasers_task:
                lasers_task.ao_channels.add_ao_voltage_chan(self.ao_terminals)
                lasers_task.write(lasers_setpoints, auto_start = True)
        except:
            print('Error setting laser power: NI device is present?')
            pass
