'''
Created on May 16, 2019

@author: flesage
'''

import os
import numpy as np
import csv

'''National Instruments Imports'''
import nidaqmx
from nidaqmx.constants import AcquisitionType, TaskMode
from nidaqmx.constants import LineGrouping, DigitalWidthUnits
from nidaqmx.types import CtrTime

from PyQt5 import QtCore

from src.waveforms import sawtooth
from src.waveforms import tunable_lens_ramp


class AOETLGalvos(QtCore.QObject):

    sig_update_gui_from_state = QtCore.pyqtSignal(bool)

    def __init__(self,parameters):
        self.parameters = parameters
    
    def create_synch_waveforms(self):
        self.calculate_samples()
        self.create_etl_waveforms()
        self.create_galvo_waveforms()
        '''Bundle everything'''
        self.bundle_galvo_and_etl_waveforms()
        
    def calculate_samples(self):
        self.samples = int(self.parameters["samplerate"]*self.parameters["sweeptime"])
    
    def create_etl_waveforms(self):
        self.etl_l_waveform = tunable_lens_ramp(samplerate = self.parameters["samplerate"],
                                                sweeptime = self.parameters["sweeptime"],
                                                delay = self.parameters["etl_l_delay"],
                                                rise = self.parameters["etl_l_ramp_rising"],
                                                fall = self.parameters["etl_l_ramp_falling"],
                                                amplitude = self.parameters["etl_l_amplitude"],
                                                offset = self.parameters["etl_l_offset"])

        self.etl_r_waveform = tunable_lens_ramp(samplerate = self.parameters["samplerate"],
                                                sweeptime = self.parameters["sweeptime"],
                                                delay = self.parameters["etl_r_delay"],
                                                rise = self.parameters["etl_r_ramp_rising"],
                                                fall = self.parameters["etl_r_ramp_falling"],
                                                amplitude = self.parameters["etl_r_amplitude"],
                                                offset = self.parameters["etl_r_offset"])

    
    def create_galvos_waveforms(self):
        
        '''Create Galvo waveforms:'''
        self.galvo_l_waveform = sawtooth(samplerate = self.parameters["samplerate"],
                                         sweeptime = self.parameters["sweeptime"],
                                         frequency = self.parameters["galvo_l_frequency"],
                                         amplitude = self.parameters["galvo_l_amplitude"],
                                         offset = self.parameters["galvo_l_offset"],
                                         dutycycle = self.parameters["galvo_l_duty_cycle"],
                                         phase = self.parameters["galvo_l_phase"])

        ''' Attention: Right Galvo gets the left frequency for now '''

        self.galvo_r_waveform = sawtooth(samplerate = self.parameters["samplerate"],
                                         sweeptime = self.parameters["sweeptime"],
                                         frequency = self.parameters["galvo_l_frequency"],
                                         amplitude = self.parameters["galvo_r_amplitude"],
                                         offset = self.parameters["galvo_r_offset"],
                                         dutycycle = self.parameters["galvo_r_duty_cycle"],
                                         phase = self.parameters["galvo_r_phase"])

    def create_tasks(self):
        '''Creates a total of four tasks for the mesoSPIM:

        These are:
        - the master trigger task, a digital out task that only provides a trigger pulse for the others
        - the camera trigger task, a counter task that triggers the camera in lightsheet mode
        - the galvo task (analog out) that controls the left & right galvos for creation of
          the light-sheet and shadow avoidance
        - the ETL & Laser task (analog out) that controls all the laser intensities (Laser should only
          be on when the camera is acquiring) and the left/right ETL waveforms
        '''
        self.calculate_samples()

        #self.master_trigger_task = nidaqmx.Task()
        #self.camera_trigger_task = nidaqmx.Task()
        self.galvo_etl_task = nidaqmx.Task(new_task_name='galvo_etl_ramps')


#        '''Setting up the counter task for the camera trigger'''
#        self.camera_trigger_task.co_channels.add_co_pulse_chan_time(ah['camera_trigger_out_line'],
#                                                                    high_time=self.camera_high_time,
#                                                                    initial_delay=self.camera_delay)

#        self.camera_trigger_task.triggers.start_trigger.cfg_dig_edge_start_trig(ah['camera_trigger_source'])

        '''Housekeeping: Setting up the AO task for the Galvo and setting the trigger input'''
        self.galvo_etl_task.ao_channels.add_ao_voltage_chan('/Dev1/ao0:3')
        self.galvo_etl_task.timing.cfg_samp_clk_timing(rate=self.parameters["samplerate"],
                                                   sample_mode=AcquisitionType.FINITE,
                                                   samps_per_chan=self.samples)
        #self.galvo_etl_task.triggers.start_trigger.cfg_dig_edge_start_trig(ah['galvo_etl_task_trigger_source'])

        '''Housekeeping: Setting up the AO task for the ETL and lasers and setting the trigger input'''
        #self.laser_task.ao_channels.add_ao_voltage_chan(ah['laser_task_line'])
        #self.laser_task.timing.cfg_samp_clk_timing(rate=samplerate,
        #                                            sample_mode=AcquisitionType.FINITE,
        #                                            samps_per_chan=samples)
        #self.laser_task.triggers.start_trigger.cfg_dig_edge_start_trig(ah['laser_task_trigger_source'])    
    
    def write_waveforms_to_tasks(self):
        '''Write the waveforms to the slave tasks'''
        self.galvo_and_etl_waveforms = np.stack((self.galvo_l_waveform,
                                                 self.galvo_r_waveform,
                                                 self.etl_l_waveform,
                                                 self.etl_r_waveform))
        self.galvo_etl_task.write(self.galvo_and_etl_waveforms)

    def start_tasks(self):
        '''Starts the tasks for camera triggering and analog outputs

        If the tasks are configured to be triggered, they won't output any
        signals until run_tasks() is called.
        '''
        #self.camera_trigger_task.start()
        self.galvo_etl_task.start()
        #self.laser_task.start()

    def run_tasks(self):
        '''Runs the tasks for triggering, analog and counter outputs

        Firstly, the master trigger triggers all other task via a shared trigger
        line (PFI line as given in the config file).

        For this to work, all analog output and counter tasks have to be started so
        that they are waiting for the trigger signal.
        '''
        #self.master_trigger_task.write([False, True, True, True, False], auto_start=True)

        '''Wait until everything is done - this is effectively a sleep function.'''
        print('waiting until done')
        self.galvo_etl_task.wait_until_done()
        print('done')
        #self.laser_task.wait_until_done()
        #self.camera_trigger_task.wait_until_done()

    def stop_tasks(self):
        '''Stops the tasks for triggering, analog and counter outputs'''
        self.galvo_etl_task.stop()
        #self.laser_task.stop()
        #self.camera_trigger_task.stop()
        #self.master_trigger_task.stop()

    def close_tasks(self):
        '''Closes the tasks for triggering, analog and counter outputs.

        Tasks should only be closed are they are stopped.
        '''
        self.galvo_etl_task.close()
        #self.laser_task.close()
        #self.camera_trigger_task.close()
        #self.master_trigger_task.close()