'''
Created on February 8, 2022
'''

import sys
sys.path.append(".")

import copy
import nidaqmx
from nidaqmx.constants import AcquisitionType, LineGrouping, Edge
import numpy as np
from configparser import ConfigParser


class Lasers:
    # Default hardware configuration
    _lasers = {}
    _lasers['Terminals'] = '/Dev7/ao0:1'
    _lasers['Lines'] = '/Dev1/port0/line1'
    _lasers['Laser1 Voltage'] = 0.0  # In Volts
    _lasers['Laser2 Voltage'] = 0.0  # In Volts

    def __init__(self):
        # Error status
        self.error = 0
        self.error_message = ''

        # State flags
        self.laser1_is_on = False
        self.laser2_is_on = False

        # Read configuration file
        self.cfg_default()
        self.cfg_read()
        self.laser1 = nidaqmx_analogLaser(self.lasers.get('Terminals'))
        self.laser2 = nidaqmx_digitalLaser(self.lasers.get('Lines'))
            
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

    def laser1_on(self):
        laser1_voltage = float(self.lasers.get('Laser1 Voltage'))
        self.laser1.create_task()
        self.laser1.write_task(laser1_voltage)
        self.laser1.stop_task()
        self.laser1_is_on = True
        return None

    def laser1_off(self):
        laser1_voltage = float(0)
        self.laser1.write_task(laser1_voltage)
        self.laser1.stop_task()
        self.laser1.close_task()
        self.laser1_is_on = False
        return None

    def laser2_on(self):
        laser2_voltage = float(self.lasers.get('Laser2 Voltage'))
        self.laser2.create_task()
        self.laser2.write_task(laser2_voltage)
        self.laser2.stop_task()
        self.laser2_is_on = True
        return None

    def laser2_off(self):
        laser2_voltage = float(0)
        self.laser2.write_task(laser2_voltage)
        self.laser2.stop_task()
        self.laser2.close_task()
        self.laser2_is_on = False
        return None


class nidaqmx_analogLaser:

    def __init__(self, terminals:str, verbose=True):
        # Error status
        self.error = 0
        self.error_message = ''
        
        # State flags
        self.ao_task_created = False

        self.verbose = verbose
        self.terminals = terminals

    def create_task(self):
        try:
            if self.verbose:
                print(f"Attempting to create AO task using {self.terminals}")
            self.ao_task = nidaqmx.Task()
            self.ao_task.ao_channels.add_ao_voltage_chan(self.terminals)
        except:
            self.ao_task.close()
            print("Could not create analog output task. Device or Terminals invalid?")
        else:
            self.ao_task_created = True
            if self.verbose:
                print(" AO task successfully created")
        return None
        
    def write_task(self, voltage):
        if self.ao_task_created:
            print(f"Set laser to {voltage}V")
        return None

    def start_task(self):
        pass

    def stop_task(self):
        pass

    def close_task(self):
        if self.ao_task_created:
            self.ao_task.close()
            if self.verbose:
                print("AO task closed")
        return None


class nidaqmx_digitalLaser:

    def __init__(self, lines:str, verbose=True):
        # Error status
        self.error = 0
        self.error_message = ""
        
        # State flags
        self.do_task_created = False

        self.verbose = verbose
        self.lines = lines

    def create_task(self):
        try:
            if self.verbose:
                print(f"Attempting to create DO task using {self.lines}")
            self.do_task = nidaqmx.Task()
            self.do_task.do_channels.add_do_chan(self.lines, line_grouping = LineGrouping.CHAN_PER_LINE)
        except:
            self.do_task.close()
            print("Could not create digital output task. Device or Lines invalid?")
        else:
            self.do_task_created = True
            if self.verbose:
                print(" DO task successfully created")
        return None

    def write_task(self, voltage):
        if self.do_task_created:
            print(f"Set laser to {voltage}V")
        return None

    def start_task(self):
        pass

    def stop_task(self):
        pass

    def close_task(self):
        if self.do_task_created:
            self.do_task.close()
            if self.verbose:
                print("DO task closed")
        return None



if __name__ == "__main__":
    mylasers = Lasers()
    mylasers.laser1_on()
    mylasers.laser1_off()

    mylasers.laser2_on()
    mylasers.laser2_off()



