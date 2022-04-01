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
    _cfg_settings['AOTerminals'] = '/Dev7/ao0:1'
    _cfg_settings['Laser Left Amplitude'] = 0.0  # In Volts
    _cfg_settings['Laser Right Amplitude'] = 0.0  # In Volts

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
        self.aoterminals        = str(self.cfg_settings['AOTerminals'])
        self.left_amplitude     = float(self.cfg_settings['Laser Left Amplitude'])
        self.right_amplitude    = float(self.cfg_settings['Laser Right Amplitude'])


    def create_tasks(self):
        self.lasers_task = nidaqmx.Task(new_task_name = 'ao_lasers_modulation')
        self.lasers_task.ao_channels.add_ao_voltage_chan(self.aoterminals)

    def start_tasks(self):
        '''Master task needs to always be started last'''
        self.lasers_task.start()

    def monitor_tasks(self):
        '''Wait until everything is done - this is effectively a sleep function.
           Master task always last'''
        self.lasers_task.wait_until_done()

    def stop_tasks(self):
        '''Stops the tasks for triggering, analog and counter outputs
           Master task always last'''
        self.lasers_task.stop()

    def delete_tasks(self):
        '''Closes the tasks for triggering, analog and counter outputs.
           Tasks should only be closed after they are stopped.
           Master task always last. '''
        self.lasers_task.close()

    def write_waveforms_to_tasks(self):
        '''Write the waveforms to the tasks'''
        self.lasers_waveforms = np.stack((self.right_waveform, self.left_waveform))
        self.lasers_task.write(self.lasers_waveforms, auto_start=True)

    def create_waveforms_on(self):
        self.left_waveform = np.array([self.left_amplitude])
        self.right_waveform = np.array([self.right_amplitude])

    def create_waveforms_off(self):
        self.left_waveform = np.array([0])
        self.right_waveform = np.array([0])

