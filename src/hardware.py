'''
Created on May 16, 2019

@author: Pierre Girard-Collins
'''
import sys
sys.path.append(".")

import numpy as np

'''National Instruments Imports'''
import nidaqmx
from nidaqmx.constants import AcquisitionType, LineGrouping, Edge

from PyQt5 import QtCore

#from src.waveforms import sawtooth
#from src.waveforms import tunable_lens_ramp
#from src.waveforms import laser_signal
#from src.waveforms import etl_stairs, etl_live_mode_waveform, galvo_live_mode_waveform, camera_live_mode_waveform
from src.waveforms import galvo_trapeze, calibrated_etl_stairs, camera_digital_output_signal


class AOETLGalvos:
    '''Class for generating and sending AO ramps to ETLs and galvos
       Update: Also includes the ramp for the camera
       Note: Possibility of also including lasers' ramps. Comments indicate 
             where the lasers'task should be implemented in the following
             functions'''
    
    def __init__(self, parameters):
        self.parameters = parameters

        #The half period is the exposure time, the time taken for a single upwards or downwards galvo scan
        self.t_half_period = 0.5*(1/self.parameters["Galvo Frequency"])

        #Number of samples per exposure time
        self.samples_per_half_period = np.ceil(self.t_half_period*self.parameters["Sample Rate"])

        #Number of samples per camera internal delay (delay for acquiring image, excluding exposure time)
        self.min_samples_per_delay = np.ceil(self.parameters["min_t_delay"]*self.parameters["Sample Rate"])

        #Number of samples per image acquisition (including exposure time)
        self.min_samples_per_step = self.min_samples_per_delay + self.samples_per_half_period

        #Number of samples added to each step to allow down time for the camera
        self.rest_samples_added = np.ceil(self.min_samples_per_step*self.parameters["camera_delay"]/100)

        #Number of samples per step (including all delay)
        self.samples_per_step = self.min_samples_per_step + self.rest_samples_added

        #Number of samples per total delay (internal + added), between each camera exposition
        self.samples_per_delay = self.samples_per_step - self.samples_per_half_period

        #Number of samples per half total delay
        self.samples_per_half_delay = np.floor(self.samples_per_delay/2)

        #Number of focal length values needed for each ETL to achieve a full scan
        self.number_of_steps = np.ceil(self.parameters["Columns"]/self.parameters["ETL Step"])

        #Total number of samples for acquisition
        self.number_of_samples = self.number_of_steps*self.samples_per_step
        self.samples = int(self.number_of_samples)

        #Total time for acquisition
        self.sweeptime = self.number_of_samples/self.parameters["Sample Rate"]


    '''Tasks methods'''
        
    def create_tasks(self, terminals, acquisition):
        '''Creates a total of four tasks for the lightsheet:

        These are:
        - the master trigger task, a digital out task that only provides a trigger pulse for the others
        - the camera trigger task, a counter task that triggers the camera in lightsheet mode
        - the galvo task (analog out) that controls the left & right galvos for creation of
          the light-sheet and shadow avoidance
        - the ETL & Laser task (analog out) that controls all the laser intensities (Laser should only
          be on when the camera is acquiring) and the left/right ETL waveforms
        
        7/26/2019: acquisition parameter was added, options are; 'FINITE' or 'CONTINUOUS'
        '''
        
        '''Set up NiDAQ acquisition mode'''
        mode = 'NONE'
        if acquisition == 'FINITE':
            mode = AcquisitionType.FINITE
        elif acquisition == 'CONTINUOUS':
            mode = AcquisitionType.CONTINUOUS
        
        #self.calculate_samples()

        #self.master_trigger_task = nidaqmx.Task()
        '''Create tasks for galvos, ETLs and camera'''
        self.galvo_etl_task = nidaqmx.Task(new_task_name = 'galvo_etl_ramps')
        self.camera_task = nidaqmx.Task(new_task_name = 'camera_do_signal')
        #self.laser_task = nidaqmx.Task(new_task_name='laser_ramps')

        '''Housekeeping: Setting up the AO task for the Galvo and ETLs. It is the master task'''
        self.galvo_etl_task.ao_channels.add_ao_voltage_chan(terminals["galvos_etls"])
        self.galvo_etl_task.timing.cfg_samp_clk_timing(rate = self.parameters["Sample Rate"], sample_mode = mode, samps_per_chan = self.samples)
        
        '''Housekeeping: Setting up the DO task for the camera. It is the slave task'''
        self.camera_task.do_channels.add_do_chan(terminals["camera"], line_grouping = LineGrouping.CHAN_PER_LINE)
        self.camera_task.timing.cfg_samp_clk_timing(rate = self.parameters["Sample Rate"], sample_mode = mode, samps_per_chan = self.samples)
        
        #self.laser_task.ao_channels.add_ao_voltage_chan(terminals["lasers"])
        #self.laser_task.timing.cfg_samp_clk_timing(rate=self.parameters["Sample Rate"], sample_mode=mode, samps_per_chan=self.samples)
        
        '''Configures the task to start acquiring/generating samples on a rising/falling edge of a digital signal. 
            args: terminal of the trigger source (master), which edge of the digital signal the task start (optionnal)
            Important to do this configuration for each slave task'''
        self.camera_task.triggers.start_trigger.cfg_dig_edge_start_trig('/Dev1/ao/StartTrigger', trigger_edge = Edge.RISING)
        #self.laser_task.triggers.start_trigger.cfg_dig_edge_start_trig('/Dev1/ao/StartTrigger', trigger_edge = Edge.RISING)
    
    def write_waveforms_to_tasks(self):
        '''Write the waveforms to the tasks'''
        self.galvo_and_etl_waveforms = np.stack((self.galvo_r_waveform, self.galvo_l_waveform, self.etl_r_waveform, self.etl_l_waveform))
       
        self.galvo_etl_task.write(self.galvo_and_etl_waveforms)
        self.camera_task.write(self.camera_waveform, auto_start = False)
        #self.lasers_waveforms = np.stack((self.laser_r_waveform, self.laser_l_waveform))
        #self.laser_task.write(self.lasers_waveforms)
    
    def start_tasks(self):
        '''Master task needs to always be started last'''
        #self.laser_task.start()
        self.camera_task.start()
        self.galvo_etl_task.start()
        
    def run_tasks(self): ###nécessaire?
        '''Runs the tasks for triggering, analog and counter outputs

        If the tasks are connected via a shared trigger line (PFI line), then
        firstly, the master trigger triggers all other task For this to work, 
        all analog output and counter tasks have to be started so that they are 
        waiting for the trigger signal. (No PFI line needed, but the related
        command is the first line in comment for reference purposes)
        
        This function is only for FINITE task, we don't call it for CONTINUOUS'''
        
        #self.master_trigger_task.write([False, True, True, True, False], auto_start=True)
        
        '''Wait until everything is done - this is effectively a sleep function.
           Master task always last'''
      
        #self.laser_task.wait_until_done()
        self.camera_task.wait_until_done()
        self.galvo_etl_task.wait_until_done()

    
    def stop_tasks(self):
        '''Stops the tasks for triggering, analog and counter outputs
           Master task always last'''
        #etl_voltage = 2.5 #In volts, corresponds to a current of 0
        #galvo_voltage = 2.5
        #standby_waveform = np.stack((np.array([galvo_voltage]),np.array([galvo_voltage]),np.array([etl_voltage]),np.array([etl_voltage])))
        #self.galvo_etl_task.write(standby_waveform, auto_start = True)
        #self.laser_task.stop()
        self.camera_task.stop()
        self.galvo_etl_task.stop()
    
    def close_tasks(self):
        '''Closes the tasks for triggering, analog and counter outputs.
           Tasks should only be closed after they are stopped.
           Master task always last. '''
        #self.laser_task.close()
        self.camera_task.close()
        self.galvo_etl_task.close()
    
    
    '''Waveform creation methods'''
        
    def create_digital_output_camera_waveform(self, case = 'NONE'):
        '''live_mode ramp isn't in use anymore, its presence was for 
           calibrating purposes in the early stages of the microscope. It is
           kept only for reference.'''
        
        if case == 'STAIRS_FITTING':
            self.camera_waveform = camera_digital_output_signal(samples_per_half_period = self.samples_per_half_period, 
                                                                t_start_exp = self.parameters["t_start_exp"], 
                                                                samplerate = self.parameters["Sample Rate"], 
                                                                samples_per_half_delay = self.samples_per_half_delay, 
                                                                number_of_samples = self.number_of_samples, 
                                                                number_of_steps = self.number_of_steps, 
                                                                samples_per_step = self.samples_per_step,
                                                                min_samples_per_delay = self.min_samples_per_delay)

    def create_calibrated_etl_waveforms(self, left_slope, left_intercept, right_slope, right_intercept, activate=False):
        '''live_mode ramps aren't in use anymore, their presence was for 
           calibrating purposes in the early stages of the microscope. They are
           kept only for reference.'''
        self.etl_l_waveform = calibrated_etl_stairs(left_slope, 
                                                    left_intercept, 
                                                    right_slope, 
                                                    right_intercept, 
                                                    etl_step = self.parameters["ETL Step"], 
                                                    amplitude = self.parameters["Left ETL Amplitude"], 
                                                    number_of_steps = self.number_of_steps, 
                                                    number_of_samples = self.number_of_samples, 
                                                    samples_per_step = self.samples_per_step, 
                                                    offset = self.parameters["Left ETL Offset"], 
                                                    direction = 'UP',
                                                    activate=activate)
        
        self.etl_r_waveform = calibrated_etl_stairs(left_slope, 
                                                    left_intercept, 
                                                    right_slope, 
                                                    right_intercept, 
                                                    etl_step = self.parameters["ETL Step"], 
                                                    amplitude = self.parameters["Right ETL Amplitude"], 
                                                    number_of_steps = self.number_of_steps, 
                                                    number_of_samples = self.number_of_samples, 
                                                    samples_per_step = self.samples_per_step, 
                                                    offset = self.parameters["Right ETL Offset"], 
                                                    direction = 'DOWN', 
                                                    activate = activate)
    
    def create_galvos_waveforms(self, case = 'NONE', invert = False):
        '''live_mode ramps aren't in use anymore, their presence was for 
           calibrating purposes in the early stages of the microscope. They are
           kept only for reference.'''
        
        if case == 'TRAPEZE':
            self.galvo_l_waveform = galvo_trapeze(  amplitude = self.parameters["Left Galvo Amplitude"], 
                                                    samples_per_half_period = self.samples_per_half_period, 
                                                    samples_per_delay = self.samples_per_delay, 
                                                    number_of_samples = self.number_of_samples, 
                                                    number_of_steps = self.number_of_steps, 
                                                    samples_per_step = self.samples_per_step, 
                                                    samples_per_half_delay = self.samples_per_half_delay,
                                                    min_samples_per_delay = self.min_samples_per_delay,
                                                    t_start_exp = self.parameters["t_start_exp"], 
                                                    samplerate = self.parameters["Sample Rate"],
                                                    offset = self.parameters["Left Galvo Offset"], 
                                                    invert = invert)
            
            self.galvo_r_waveform = galvo_trapeze(  amplitude = self.parameters["Right Galvo Amplitude"], 
                                                    samples_per_half_period = self.samples_per_half_period, 
                                                    samples_per_delay = self.samples_per_delay, 
                                                    number_of_samples = self.number_of_samples, 
                                                    number_of_steps = self.number_of_steps, 
                                                    samples_per_step = self.samples_per_step, 
                                                    samples_per_half_delay = self.samples_per_half_delay,
                                                    min_samples_per_delay = self.min_samples_per_delay,
                                                    t_start_exp = self.parameters["t_start_exp"], 
                                                    samplerate = self.parameters["Sample Rate"],
                                                    offset = self.parameters["Right Galvo Offset"],
                                                    invert = invert)
  
