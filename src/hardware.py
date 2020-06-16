'''
Created on May 16, 2019

@author: Pierre Girard-Collins
'''
import sys
sys.path.append("..")

import serial

import os
import numpy as np
import csv

'''National Instruments Imports'''
import nidaqmx
from nidaqmx.constants import AcquisitionType, TaskMode
from nidaqmx.constants import LineGrouping, DigitalWidthUnits, Edge
from nidaqmx.types import CtrTime

from PyQt5 import QtCore

from src.waveforms import sawtooth
from src.waveforms import tunable_lens_ramp
from src.waveforms import laser_signal
from src.waveforms import etl_stairs, etl_live_mode_waveform
from src.waveforms import galvo_trapeze, galvo_live_mode_waveform
from src.waveforms import camera_digital_output_signal, camera_live_mode_waveform


class AOETLGalvos(QtCore.QObject):
    '''Class for generating and sending AO ramps to ETLs and galvos
       Update: Also includes the ramp for the camera
       Note: Possibility of also including lasers' ramps. Comments indicate 
             where the lasers'task should be implemented in the following
             functions'''

    sig_update_gui_from_state = QtCore.pyqtSignal(bool)

    def __init__(self,parameters):
        self.parameters = parameters
        
    def close_tasks(self):
        '''Closes the tasks for triggering, analog and counter outputs.
           Tasks should only be closed after they are stopped.
           Master task always last. '''
        
        #self.laser_task.close()
        self.camera_task.close()
        self.galvo_etl_task.close()
        
    def create_digital_output_camera_waveform(self, case = 'NONE'):
        '''live_mode ramp isn't in use anymore, its presence was for 
           calibrating purposes in the early stages of the microscope. It is
           kept only for reference.'''
        
        if case == 'STAIRS_FITTING':
            self.camera_waveform = camera_digital_output_signal(samples_per_half_period = self.samples_per_half_period, 
                                                    t_start_exp = self.parameters["t_start_exp"], 
                                                    samplerate = self.parameters["samplerate"], 
                                                    samples_per_half_delay = self.samples_per_half_delay, 
                                                    number_of_samples = self.number_of_samples, 
                                                    number_of_steps = self.number_of_steps, 
                                                    samples_per_step = self.samples_per_step,
                                                    min_samples_per_delay = self.min_samples_per_delay)
        elif case == 'LIVE_MODE':
            self.camera_waveform = camera_live_mode_waveform(samples_per_half_period = self.samples_per_half_period,
                                                              t_start_exp = self.parameters["t_start_exp"], 
                                                              samplerate = self.parameters["samplerate"], 
                                                              samples_per_half_delay = self.samples_per_half_delay, 
                                                              number_of_samples = self.number_of_samples)
        
    def create_etl_waveforms(self, case = 'NONE'):
        '''live_mode ramps aren't in use anymore, their presence was for 
           calibrating purposes in the early stages of the microscope. They are
           kept only for reference.'''
        
        if case == 'STAIRS':
            self.etl_l_waveform = etl_stairs(amplitude = self.parameters["etl_l_amplitude"], 
                                             number_of_steps = self.number_of_steps, 
                                             number_of_samples = self.number_of_samples, 
                                             samples_per_step = self.samples_per_step, 
                                             offset = self.parameters["etl_l_offset"], 
                                             direction = 'UP')
            
            self.etl_r_waveform = etl_stairs(amplitude = self.parameters["etl_r_amplitude"], 
                                             number_of_steps = self.number_of_steps, 
                                             number_of_samples = self.number_of_samples, 
                                             samples_per_step = self.samples_per_step, 
                                             offset = self.parameters["etl_r_offset"], 
                                             direction = 'DOWN')
            
        elif case == 'LIVE_MODE':
            self.etl_l_waveform = etl_live_mode_waveform(amplitude = self.parameters["etl_l_amplitude"], 
                                                         number_of_samples = self.number_of_samples) 
            
            self.etl_r_waveform = etl_live_mode_waveform(amplitude = self.parameters["etl_r_amplitude"], 
                                                         number_of_samples = self.number_of_samples) 

    
    def create_galvos_waveforms(self, case = 'NONE'):
        '''live_mode ramps aren't in use anymore, their presence was for 
           calibrating purposes in the early stages of the microscope. They are
           kept only for reference.'''
        
        if case == 'TRAPEZE':
            self.galvo_l_waveform = galvo_trapeze(amplitude = self.parameters["galvo_l_amplitude"], 
                                                  samples_per_half_period = self.samples_per_half_period, 
                                                  samples_per_delay = self.samples_per_delay, 
                                                  number_of_samples = self.number_of_samples, 
                                                  number_of_steps = self.number_of_steps, 
                                                  samples_per_step = self.samples_per_step, 
                                                  samples_per_half_delay = self.samples_per_half_delay,
                                                  min_samples_per_delay = self.min_samples_per_delay,
                                                  t_start_exp = self.parameters["t_start_exp"], 
                                                  samplerate = self.parameters["samplerate"],
                                                  offset = self.parameters["galvo_l_offset"])
            
            self.galvo_r_waveform = galvo_trapeze(amplitude = self.parameters["galvo_r_amplitude"], 
                                                  samples_per_half_period = self.samples_per_half_period, 
                                                  samples_per_delay = self.samples_per_delay, 
                                                  number_of_samples = self.number_of_samples, 
                                                  number_of_steps = self.number_of_steps, 
                                                  samples_per_step = self.samples_per_step, 
                                                  samples_per_half_delay = self.samples_per_half_delay,
                                                  min_samples_per_delay = self.min_samples_per_delay,
                                                  t_start_exp = self.parameters["t_start_exp"], 
                                                  samplerate = self.parameters["samplerate"],
                                                  offset = self.parameters["galvo_r_offset"])
        elif case == 'LIVE_MODE':
            self.galvo_l_waveform = galvo_live_mode_waveform(amplitude = self.parameters["galvo_l_amplitude"], 
                                                             samples_per_half_period = self.samples_per_half_period, 
                                                             samples_per_delay = self.samples_per_delay, 
                                                             number_of_samples = self.number_of_samples,
                                                             samples_per_half_delay = self.samples_per_half_delay, 
                                                             offset = self.parameters["galvo_l_offset"])
            
            self.galvo_r_waveform = galvo_live_mode_waveform(amplitude = self.parameters["galvo_r_amplitude"], 
                                                             samples_per_half_period = self.samples_per_half_period, 
                                                             samples_per_delay = self.samples_per_delay, 
                                                             number_of_samples = self.number_of_samples,
                                                             samples_per_half_delay = self.samples_per_half_delay, 
                                                             offset = self.parameters["galvo_r_offset"])
            
    
    def create_lasers_waveforms(self):
        '''The laser_signal() ramp isn't in use anymore, its presence was for 
           calibrating purposes in the early stages of the microscope. For 
           future implementation of a distinct laser waveform, this function can
           be used with the appropriate signal shape imported and coded in 
           waveform.py'''
        self.laser_l_waveform = laser_signal(samplerate = self.parameters["samplerate"], 
                                             sweeptime = self.sweeptime, 
                                             voltage = self.parameters["laser_l_voltage"])
        
        self.laser_r_waveform = laser_signal(samplerate = self.parameters["samplerate"], 
                                             sweeptime = self.sweeptime, 
                                             voltage = self.parameters["laser_r_voltage"])
        

    def create_tasks(self, terminals, acquisition):
        '''Creates a total of four tasks for the light-sheet:

        These are:
        - the master trigger task, a digital out task that only provides a trigger pulse for the others
        - the camera trigger task, a counter task that triggers the camera in lightsheet mode
        - the galvo task (analog out) that controls the left & right galvos for creation of
          the light-sheet and shadow avoidance
        - the ETL & Laser task (analog out) that controls all the laser intensities (Laser should only
          be on when the camera is acquiring) and the left/right ETL waveforms
        
        7/26/2019: acquisition parameter was added, options are; 'FINITE' or 'CONTINUOUS'
        '''
        
        mode = 'NONE'
        if acquisition == 'FINITE':
            mode = AcquisitionType.FINITE
        elif acquisition == 'CONTINUOUS':
            mode = AcquisitionType.CONTINUOUS
        
        #self.calculate_samples()

        #self.master_trigger_task = nidaqmx.Task()
        self.galvo_etl_task = nidaqmx.Task(new_task_name='galvo_etl_ramps')
        self.camera_task = nidaqmx.Task(new_task_name='camera_do_signal')
        #self.laser_task = nidaqmx.Task(new_task_name='laser_ramps')


        '''Housekeeping: Setting up the AO task for the Galvo and ETLs. It is the master task'''
        self.galvo_etl_task.ao_channels.add_ao_voltage_chan(terminals["galvos_etls"])
        self.galvo_etl_task.timing.cfg_samp_clk_timing(rate=self.parameters["samplerate"],
                                                   sample_mode=mode,
                                                   samps_per_chan=self.samples)
        
        '''Housekeeping: Setting up the DO task for the camera. It is the slave task'''
        self.camera_task.do_channels.add_do_chan(terminals["camera"], line_grouping = LineGrouping.CHAN_PER_LINE)
        self.camera_task.timing.cfg_samp_clk_timing(rate=self.parameters["samplerate"], sample_mode=mode, samps_per_chan=self.samples)
        
        #self.laser_task.ao_channels.add_ao_voltage_chan(terminals["lasers"])
        #self.laser_task.timing.cfg_samp_clk_timing(rate=self.parameters["samplerate"], sample_mode=mode, samps_per_chan=self.samples)
        
        '''Configures the task to start acquiring/generating samples on a rising/falling edge of a digital signal. 
            args: terminal of the trigger source (master), which edge of the digital signal the task start (optionnal)
            Important to do this configuration for each slave task'''
        self.camera_task.triggers.start_trigger.cfg_dig_edge_start_trig('/Dev1/ao/StartTrigger', trigger_edge=Edge.RISING)
        #self.laser_task.triggers.start_trigger.cfg_dig_edge_start_trig('/Dev1/ao/StartTrigger', trigger_edge=Edge.RISING)
        
    def initialize(self):
        '''Should always be executed first as it instantiates the variables 
           needed for waveforms generation
           
           The half period of the galvos is the exposure time, i.e. the time 
           taken for a single upwards or downwards galvo scan. It is defined 
           with the left galvo frequency (choice of galvo is arbitrary since 
           they both should have the same frequency.'''
        
        self.t_half_period = 0.5*(1/self.parameters["galvo_l_frequency"])     #It is our exposure time (is in the range of the camera)
        self.samples_per_half_period = np.ceil(self.t_half_period*self.parameters["samplerate"])
        #print('Samples per half period: '+str(self.samples_per_half_period))
        
        self.min_samples_per_delay = np.ceil(self.parameters["min_t_delay"]*self.parameters["samplerate"])
        #print('Minimum samples per delay: '+str(self.min_samples_per_delay))
        
        self.min_samples_per_step = self.min_samples_per_delay + self.samples_per_half_period
        #print('Minimum samples per step: '+str(self.min_samples_per_step)+'\n')
        
        self.rest_samples_added = np.ceil(self.min_samples_per_step*self.parameters["camera_delay"]/100)  #Samples added to allow down time for the camera
        self.samples_per_step = self.min_samples_per_step + self.rest_samples_added
        #print('Samples per step: ' + str(self.samples_per_step))
        
        self.samples_per_delay = self.samples_per_step-self.samples_per_half_period
        #print('Samples per delay: '+str(self.samples_per_delay))
        
        self.samples_per_half_delay = np.floor(self.samples_per_delay/2)
        #print('Samples per half delay: '+str(self.samples_per_half_delay)+'\n')
        
        #print('Number of columns: '+str(self.parameters["columns"]))
        #print('Etl step: '+str(self.parameters["etl_step"]) + ' columns')
        
        self.number_of_steps = np.ceil(self.parameters["columns"]/self.parameters["etl_step"])
        #print('Number of steps: ' + str(self.number_of_steps)+'\n')
        
        self.number_of_samples = self.number_of_steps*self.samples_per_step
        #print('Number of samples: '+str(self.number_of_samples))
        
        self.sweeptime = self.number_of_samples/self.parameters["samplerate"]
        #print('Sweeptime: '+str(self.sweeptime)+'s')
        
        self.samples = int(self.number_of_samples)
        
    
    def initialize_live_mode(self):
        '''Should always be executed first as it instantiates the variables 
           needed for waveforms generation
           
           This function isn't currently in use as it was for calibrating
           purposes in the early stages of the microscope. It is kept for
           reference'''
        
        self.t_half_period = (1/self.parameters["galvo_l_frequency"])     #It is our exposure time (is in the range of the camera)
        self.samples_per_half_period = np.ceil(self.t_half_period*self.parameters["samplerate"])
        
        self.min_samples_per_delay = np.ceil(self.parameters["min_t_delay"]*self.parameters["samplerate"])
        
        self.min_samples_per_step = self.min_samples_per_delay + self.samples_per_half_period
        
        self.rest_samples_added = np.ceil(self.min_samples_per_step*self.parameters["camera_delay"]/100)  #Samples added to allow down time for the camera
        self.samples_per_step = self.min_samples_per_step + self.rest_samples_added
        
        self.samples_per_delay = self.samples_per_step-self.samples_per_half_period
        
        self.samples_per_half_delay = np.floor(self.samples_per_delay/2)
        
        self.number_of_samples = self.samples_per_step
        
        self.sweeptime = self.number_of_samples/self.parameters["samplerate"]
        
        self.samples = int(self.number_of_samples)  
        
    def run_tasks(self):
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
        
    def start_tasks(self):
        '''Master task needs to always be started last'''
        
        #self.laser_task.start()
        self.camera_task.start()
        self.galvo_etl_task.start()
        
    def stop_tasks(self):
        '''Stops the tasks for triggering, analog and counter outputs
           Master task always last'''
        
        #self.laser_task.stop()
        self.camera_task.stop()
        self.galvo_etl_task.stop()
            
    
    def write_waveforms_to_tasks(self):
        '''Write the waveforms to the tasks'''
        self.galvo_and_etl_waveforms = np.stack((self.galvo_r_waveform,
                                                 self.galvo_l_waveform,
                                                 self.etl_r_waveform,
                                                 self.etl_l_waveform))
       
        self.galvo_etl_task.write(self.galvo_and_etl_waveforms)
        
        self.camera_task.write(self.camera_waveform)
        
        #self.lasers_waveforms = np.stack((self.laser_r_waveform,
        #                                  self.laser_l_waveform))
        
        #self.laser_task.write(self.lasers_waveforms)

  
  
    
class Motors:
    '''Class for Zaber's T-LSM series linear stage motor control'''
    
    def __init__(self, device_number, port):
        '''device_number is the number of the device in the daisy chain '''
        self.device_number = device_number
        self.port = port
        self.ID = self.ask_ID()
        
    def ask_ID(self):
        '''Returns the ID of the device. 
        
        If the ID is 6210, it is the vertical motor
        If the ID is 6320, it is one of the horizontal motors
        ''' 
        motor=serial.Serial(port=self.port,baudrate=9600,bytesize=serial.EIGHTBITS,parity=serial.PARITY_NONE,stopbits=serial.STOPBITS_ONE)
        
        command = self.generate_command(50,0)
        motor.write(command)
        
        ID=0
        #All the bytes are read, so they doesn't interfere with another command later
        last_read = []
        for i in range(6):
            last_read.append(self.byte_to_int(motor.read(1)))
        
        #Byte3 (index 2) is the least significant byte of the data read and can determine alone the ID in this case
        if last_read[2] == 66:
            ID = 6210
        elif last_read[2] == 176:
            ID = 6320
        
        motor.close()
        
        return ID
    
    def byte_to_int(self,byte):
        '''Converts bytes into an integer'''
        
        result = 0
        for b in byte:
            result = result * 256 + int(b)
        return result
    
    def current_position(self, unit):
        '''Returns the current position of the device. The position is converted into the unit specified. 
        
        Parameter:
            unit: A string. The options are: 'm', 'cm', 'mm', '\u03BCm' (micro meter) and '\u03BCStep' (micro-step)
        '''
        motor=serial.Serial(port=self.port,baudrate=9600,bytesize=serial.EIGHTBITS,parity=serial.PARITY_NONE,stopbits=serial.STOPBITS_ONE)
        cmdNumber = 60
        command = self.generate_command(cmdNumber,0)
        motor.write(command)
        
        last_read = []
        for i in range(6):
            last_read.append(self.byte_to_int(motor.read(1)))
        
        motor.close()
        
        data = pow(256,3)*last_read[5]+pow(256,2)*last_read[4]+256*last_read[3]+last_read[2]
        
        #The first two conditions are there to avoid a result with a huge number of decimals for the extremum positions. These could be taken off later
        #by controling the number of decimals to display on the associated label of the GUI
        if data == 1066666:
                return 0
            
        elif data == 533333:
                if unit == "m":
                    return 0.1016
                elif unit == "cm":
                    return 10.16
                elif unit == "mm":
                    return 101.6
                elif unit =='\u03BCm':
                    return 101600
                elif unit == '\u03BCStep':
                    return 533333
        
        #Take into account that the minimum position (home position) of the vertical motor is at its maximum height in the physical structure
        elif self.ID == 6210:
                if unit == "m":
                    return 0.0508-self.data_to_position(data,unit)
                elif unit == "cm":
                    return 5.08-self.data_to_position(data,unit)
                elif unit == "mm":
                    return 50.8-self.data_to_position(data,unit)
                elif unit =='\u03BCm':
                    return 50800-self.data_to_position(data,unit)
                elif unit == '\u03BCStep':
                    return 1066666-self.data_to_position(data,unit)
                
        else:
            return self.data_to_position(data,unit)
    
    def data_to_position(self,data,unit):
        '''Converts a data into a position 
        
        Parameters:
            data: An integer or a float
            unit: A string wich specifies the unit into which the position will be converted. 
                  The options are: 'm', 'cm', 'mm', '\u03BCm' (micro meter) and '\u03BCStep' (micro-step) 
        '''
        factor = 0
        micro_step = 0
        
        #The microstep size, necessary for the conversion, differs from each type of device
        if self.ID == 6210:
            micro_step = 0.047625
        elif self.ID == 6320:
            micro_step = 0.1905
       
        if unit == 'm':
            factor = 1
        elif unit == 'cm':
            factor=pow(10,-2)
        elif unit == 'mm':
            factor=pow(10,-3)
        elif unit == '\u03BCm':
            factor=pow(10,-6)
        elif unit == '\u03BCStep':
            factor = micro_step*pow(10,-6)
            
        return data*micro_step*pow(10,-6)/factor
        
    def generate_command(self,cmd_number,data):
        '''Generates the command to send to the motor device
        
        Parameters:
            cmdNumber: Determines the type of operation (see Zaber T-LSM series User's Manual for a complete list)
            data: The value associated to the cmdNumber
        '''
        command=[self.device_number,cmd_number]
        
        #To take into account negative data (such as a relative motion)
        if data < 0:
            data = pow(256,4) + data
        
        #Generates bytes 3 to 6
        byte_6 = int(data//pow(256,3))
        data = data - byte_6*pow(256,3)
        byte_5 = int(data//pow(256,2))
        data = data - byte_5*pow(256,2)
        byte_4 = int(data//256)
        data = data - byte_4*256
        byte_3 = int(data//1)
        
        command.append(byte_3)
        command.append(byte_4)
        command.append(byte_5)
        command.append(byte_6)
        
        return bytearray(command)
    
    def move_absolute_position(self, absolute_position, unit):
        '''Moves the device to a specified absolute position.
        
        Parameters:
            absolutePosition: Numerical value of the absolute position
            unit: A string which indicate the scale of the numerical value.
                  The options are: 'm', 'cm', 'mm', '\u03BCm' (micro meter) and '\u03BCStep' (micro-step)
                  
        For the horizontal motors, position 0 is the home position.
        For the vertical motor, height 0 is the maximum position.
        '''
        motor=serial.Serial(port=self.port,baudrate=9600,bytesize=serial.EIGHTBITS,parity=serial.PARITY_NONE,stopbits=serial.STOPBITS_ONE)
        
        data=0
        if self.ID == 6210:
            data = 1066666-self.position_to_data(absolute_position,unit)
        elif self.ID == 6320:
            data = self.position_to_data(absolute_position,unit)
        
        command = self.generate_command(20,data)
        motor.write(command)
        #All the reply bytes are read, so they doesn't interfere with further operations, suchas self.current_position(unit)
        motor.read(6)
        
        motor.close()
    
    def move_home(self):
        '''Moves the device to home position. For the vertical motor, it matches the maximum height. '''
        motor=serial.Serial(port=self.port,baudrate=9600,bytesize=serial.EIGHTBITS,parity=serial.PARITY_NONE,stopbits=serial.STOPBITS_ONE)
        
        command = self.generate_command(20,0)
        motor.write(command)
        #All the reply bytes are read, so they doesn't interfere with further operations, suchas self.current_position(unit)
        motor.read(6)
        
        motor.close()
        
        
    def move_maximum_position(self):
        '''Moves the device to its maximum position. For the vertical motor it matches the minimum height.  '''
        if self.ID == 6210:
            data = 1066666
        elif self.ID == 6320:
            data = 533333
        
        motor=serial.Serial(port=self.port,baudrate=9600,bytesize=serial.EIGHTBITS,parity=serial.PARITY_NONE,stopbits=serial.STOPBITS_ONE)
        
        command = self.generate_command(20,data)
        motor.write(command)
        #All the reply bytes are read, so they doesn't interfere with further operations, suchas self.current_position(unit)
        motor.read(6)
        
        motor.close()
        
    def move_relative_position(self, relative_position, unit):
        '''Moves the device to a specified relative position
        
        Parameters:
            relativePosition: Numerical value of the relative motion
            unit: A string which indicate the scale of the numerical value.
                  The options are: 'm', 'cm', 'mm', '\u03BCm' (micro meter) and '\u03BCStep' (micro-step)
        '''
        motor=serial.Serial(port=self.port,baudrate=9600,bytesize=serial.EIGHTBITS,parity=serial.PARITY_NONE,stopbits=serial.STOPBITS_ONE)
        
        data = self.position_to_data(relative_position, unit)
        
        command = self.generate_command(21,data)
        motor.write(command)
        #All the reply bytes are read, so they doesn't interfere with further operations, such as self.current_position(unit)
        motor.read(6)
    
        motor.close()    
    
    def position_to_data(self,position,unit):
        '''Converts the position into the form of a data 
        
        Parameters:
            position: Numerical value of the position
            unit: A string which specifies the unit of the numerical position. 
                  The options are: 'm', 'cm', 'mm', '\u03BCm' (micro meter) and '\u03BCStep' (micro-step) 
        '''
        factor = 0
        micro_step = 0
        
        #The microstep size, necessary for the conversion, differs from each type of device
        if self.ID == 6210:
            micro_step = 0.047625
        elif self.ID == 6320:
            micro_step = 0.1905
        
        if unit == 'm':
            factor = 1
        elif unit == 'cm':
            factor=pow(10,-2)
        elif unit == 'mm':
            factor=pow(10,-3)
        elif unit == '\u03BCm':
            factor=pow(10,-6)
        elif unit == '\u03BCStep':
            factor = micro_step*pow(10,-6)
        
        return position*factor/(micro_step*pow(10,-6))