'''
Created on February 8, 2022
'''

import sys
sys.path.append(".")

import copy
import nidaqmx
import numpy as np
from configparser import ConfigParser


class Lasers:
        
    # Default hardware configuration
    _lasers = {}
    _lasers['Terminals'] = '/Dev7/ao0:1'
    _lasers['Laser1 Voltage'] = 0.0  # In Volts
    _lasers['Laser2 Voltage'] = 0.0  # In Volts

    # State flags
    laser1_is_open = False
    laser2_is_open = False

    # Error status
    error = 0
    error_message = ""

    def __init__(self):
        self.cfg_default()
        self.cfg_read()
        self.laser1 = analogLaser(self.lasers.get('Terminals'))
            
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

    def turn_laser1_on(self):
        self.laser1.create_task()
        self.laser1_on = True
        laser1_voltage = float(self.lasers.get('Laser1 Voltage'))
        laser2_voltage = float(self.lasers.get('Laser2 Voltage'))
        lasers_waveforms = np.stack((np.array([laser1_voltage]), np.array([laser2_voltage])))

    def turn_laser1_off(self):
        self.laser1_on = False
        lasers_waveforms = np.stack((np.array([0.0]), np.array([0.0])))



class analogLaser:

    # State flags
    ao_task_created = False

    def __init__(self, Terminals:str):
        self.Terminals = Terminals

    def create_task(self):
        try:
            self.ao_task = nidaqmx.Task()
            self.ao_task.ao_channels.add_ao_voltage_chan(self.Terminals)
        except:
            self.ao_task.close()
            print('Could not create analog output task. Device or Terminals invalid?')
        else:
            self.ao_task_created = True
            print('Task created!')
        
    def write_task(self):
        pass

    def start_task(self):
        pass

    def stop_task(self):
        pass

    def close_task(self):
        pass



if __name__ == "__main__":
    mylasers = Lasers()
    mylasers.turn_laser1_on()
    mylasers.turn_laser1_off()



