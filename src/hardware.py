'''
Created on May 16, 2019

@author: Pierre Girard-Collins
'''
import sys
sys.path.append(".")

import serial

#import os
import numpy as np
#import csv

'''National Instruments Imports'''
import nidaqmx
from nidaqmx.constants import AcquisitionType, LineGrouping, Edge
#from nidaqmx.constants import TaskMode, DigitalWidthUnits
#from nidaqmx.types import CtrTime

from PyQt5 import QtCore

#from src.waveforms import sawtooth
#from src.waveforms import tunable_lens_ramp
#from src.waveforms import laser_signal
#from src.waveforms import etl_stairs, etl_live_mode_waveform, galvo_live_mode_waveform, camera_live_mode_waveform
from src.waveforms import galvo_trapeze, calibrated_etl_stairs, camera_digital_output_signal


class AOETLGalvos(QtCore.QObject):
    '''Class for generating and sending AO ramps to ETLs and galvos
       Update: Also includes the ramp for the camera
       Note: Possibility of also including lasers' ramps. Comments indicate 
             where the lasers'task should be implemented in the following
             functions'''

    #sig_update_gui_from_state = QtCore.pyqtSignal(bool) ###utilité?
    
    def __init__(self, parameters):
        self.parameters = parameters
        self.t_half_period = 0.5*(1/self.parameters["Galvo Frequency"]) #The half period is the exposure time, the time taken for a single upwards or downwards galvo scan
        #print('t_half_period:'+str(self.t_half_period)) #debugging
        self.samples_per_half_period = np.ceil(self.t_half_period*self.parameters["Sample Rate"]) #Number of samples per exposure time
        #print('Samples per half period: '+str(self.samples_per_half_period)) #debugging
        self.min_samples_per_delay = np.ceil(self.parameters["min_t_delay"]*self.parameters["Sample Rate"]) #Number of samples per camera internal delay (delay for acquiring image, excluding exposure time)
        #print('Minimum samples per delay: '+str(self.min_samples_per_delay)) #debugging
        self.min_samples_per_step = self.min_samples_per_delay + self.samples_per_half_period #Number of samples per image acquisition (including exposure time)
        #print('Minimum samples per step: '+str(self.min_samples_per_step)+'\n') #debugging
        self.rest_samples_added = np.ceil(self.min_samples_per_step*self.parameters["camera_delay"]/100)  #Number of samples added to each step to allow down time for the camera
        self.samples_per_step = self.min_samples_per_step + self.rest_samples_added #Number of samples per step (including all delay)
        #print('Samples per step: ' + str(self.samples_per_step)) #debugging
        self.samples_per_delay = self.samples_per_step - self.samples_per_half_period #Number of samples per total delay (internal + added), between each camera exposition
        #print('Samples per delay: '+str(self.samples_per_delay)) #debugging
        self.samples_per_half_delay = np.floor(self.samples_per_delay/2) #Number of samples per half total delay
        #print('Samples per half delay: '+str(self.samples_per_half_delay)+'\n') #debugging
        #print('Number of Columns: '+str(self.parameters["Columns"])) #debugging
        #print('Etl step: '+str(self.parameters["ETL Step"]) + ' Columns') #debugging
        self.number_of_steps = np.ceil(self.parameters["Columns"]/self.parameters["ETL Step"]) #Number of focal length values needed for each ETL to achieve a full scan
        #print('Number of steps: ' + str(self.number_of_steps)+'\n') #debugging
        self.number_of_samples = self.number_of_steps*self.samples_per_step #Total number of samples for acquisition
        self.samples = int(self.number_of_samples)
        #print('Number of samples: '+str(self.number_of_samples)) #debugging
        self.sweeptime = self.number_of_samples/self.parameters["Sample Rate"] #Total time for acquisition
        #print('Sweeptime: '+str(self.sweeptime)+'s') #debugging
    
    '''Tasks methods'''
        
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
        
        '''Set up NiDAQ acquisition mode'''
        mode = 'NONE'
        if acquisition == 'FINITE':
            mode = AcquisitionType.FINITE
        elif acquisition == 'CONTINUOUS':
            mode = AcquisitionType.CONTINUOUS
        
        #self.calculate_samples()

        #self.master_trigger_task = nidaqmx.Task()
        '''Create tasks for galvos, ETLs and camera'''
        self.galvo_etl_task = nidaqmx.Task(new_task_name='galvo_etl_ramps')
        self.camera_task = nidaqmx.Task(new_task_name='camera_do_signal')
        #self.laser_task = nidaqmx.Task(new_task_name='laser_ramps')

        '''Housekeeping: Setting up the AO task for the Galvo and ETLs. It is the master task'''
        self.galvo_etl_task.ao_channels.add_ao_voltage_chan(terminals["galvos_etls"])
        self.galvo_etl_task.timing.cfg_samp_clk_timing(rate=self.parameters["Sample Rate"],
                                                   sample_mode=mode,
                                                   samps_per_chan=self.samples)
        
        '''Housekeeping: Setting up the DO task for the camera. It is the slave task'''
        self.camera_task.do_channels.add_do_chan(terminals["camera"], line_grouping = LineGrouping.CHAN_PER_LINE)
        self.camera_task.timing.cfg_samp_clk_timing(rate=self.parameters["Sample Rate"], sample_mode=mode, samps_per_chan=self.samples)
        
        #self.laser_task.ao_channels.add_ao_voltage_chan(terminals["lasers"])
        #self.laser_task.timing.cfg_samp_clk_timing(rate=self.parameters["Sample Rate"], sample_mode=mode, samps_per_chan=self.samples)
        
        '''Configures the task to start acquiring/generating samples on a rising/falling edge of a digital signal. 
            args: terminal of the trigger source (master), which edge of the digital signal the task start (optionnal)
            Important to do this configuration for each slave task'''
        self.camera_task.triggers.start_trigger.cfg_dig_edge_start_trig('/Dev1/ao/StartTrigger', trigger_edge=Edge.RISING)
        #self.laser_task.triggers.start_trigger.cfg_dig_edge_start_trig('/Dev1/ao/StartTrigger', trigger_edge=Edge.RISING)
    
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

    def create_calibrated_etl_waveforms(self, left_slope, left_intercept, right_slope, right_intercept,activate=False):
        '''live_mode ramps aren't in use anymore, their presence was for 
           calibrating purposes in the early stages of the microscope. They are
           kept only for reference.'''
        self.etl_l_waveform = calibrated_etl_stairs(left_slope, left_intercept,###
                                         right_slope, right_intercept, ###
                                         etl_step=self.parameters["ETL Step"], ###
                                         amplitude = self.parameters["Left ETL Amplitude"], 
                                         number_of_steps = self.number_of_steps, 
                                         number_of_samples = self.number_of_samples, 
                                         samples_per_step = self.samples_per_step, 
                                         offset = self.parameters["Left ETL Offset"], 
                                         direction = 'UP',activate=activate)
        
        self.etl_r_waveform = calibrated_etl_stairs(left_slope, left_intercept,###
                                         right_slope, right_intercept, ###
                                         etl_step=self.parameters["ETL Step"], ###
                                         amplitude = self.parameters["Right ETL Amplitude"], 
                                         number_of_steps = self.number_of_steps, 
                                         number_of_samples = self.number_of_samples, 
                                         samples_per_step = self.samples_per_step, 
                                         offset = self.parameters["Right ETL Offset"], 
                                         direction = 'DOWN',activate=activate)
    
    def create_galvos_waveforms(self, case = 'NONE',invert=False):
        '''live_mode ramps aren't in use anymore, their presence was for 
           calibrating purposes in the early stages of the microscope. They are
           kept only for reference.'''
        
        if case == 'TRAPEZE':
            self.galvo_l_waveform = galvo_trapeze(amplitude = self.parameters["Left Galvo Amplitude"], 
                                                  samples_per_half_period = self.samples_per_half_period, 
                                                  samples_per_delay = self.samples_per_delay, 
                                                  number_of_samples = self.number_of_samples, 
                                                  number_of_steps = self.number_of_steps, 
                                                  samples_per_step = self.samples_per_step, 
                                                  samples_per_half_delay = self.samples_per_half_delay,
                                                  min_samples_per_delay = self.min_samples_per_delay,
                                                  t_start_exp = self.parameters["t_start_exp"], 
                                                  samplerate = self.parameters["Sample Rate"],
                                                  offset = self.parameters["Left Galvo Offset"],invert=invert)
            
            self.galvo_r_waveform = galvo_trapeze(amplitude = self.parameters["Right Galvo Amplitude"], 
                                                  samples_per_half_period = self.samples_per_half_period, 
                                                  samples_per_delay = self.samples_per_delay, 
                                                  number_of_samples = self.number_of_samples, 
                                                  number_of_steps = self.number_of_steps, 
                                                  samples_per_step = self.samples_per_step, 
                                                  samples_per_half_delay = self.samples_per_half_delay,
                                                  min_samples_per_delay = self.min_samples_per_delay,
                                                  t_start_exp = self.parameters["t_start_exp"], 
                                                  samplerate = self.parameters["Sample Rate"],
                                                  offset = self.parameters["Right Galvo Offset"],invert=invert)
  
  
    
class Motors:
    '''Class for Zaber's T-LSM series linear stage motor control'''
    
    def __init__(self, device_number, port):
        '''device_number is the number of the device in the daisy chain '''
        self.error = 0
        self.error_message = ""
        self.device_number = device_number
        self.port = port
        self.ID = 0
        self.name = ""
        self.micro_step = 0
        self.ask_ID()

    def __motorIO__(self, cmd_no, cmd_param):
        #Default return
        reply_data = 0

        #Generate 6-byte instruction from cmd_no and cmd_param
        #Taking into account negative data (such as a relative motion)
        if cmd_param < 0:
            cmd_param = pow(256,4) + cmd_param            
        #Generates bytes 3 to 6
        byte_6 = int(cmd_param // pow(256,3))
        cmd_param = cmd_param % pow(256,3)
        byte_5 = int(cmd_param // pow(256,2))
        cmd_param = cmd_param % pow(256,2)
        byte_4 = int(cmd_param // pow(256,1))
        cmd_param = cmd_param % pow(256,1)
        byte_3 = int(cmd_param // pow(256,0))
        #Assemble instruction
        instruction = []
        instruction.append(int(self.device_number))
        instruction.append(int(cmd_no))
        instruction.append(byte_3)
        instruction.append(byte_4)
        instruction.append(byte_5)
        instruction.append(byte_6)

        try:
            #Try to open a serial connection
            motor = serial.Serial(port=self.port, baudrate=9600, bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE, timeout = 2)
        except serial.SerialException:
            self.error = 1
            self.error_message = "Error - Serial port cannot be found or cannot be configured"
        else:
            #We have an open serial port to the motor
            #Clear I/O buffers
            motor.reset_input_buffer()
            motor.reset_output_buffer()
            #Write instruction bytes to motor
            motor.write(bytes(instruction))
            #Read 6-bytes reply
            reply_bytes = motor.read(6)
            #Close serial connection to motor  
            motor.close()
            #Checks if reply is valid length
            if len(reply_bytes) == 6:
                if reply_bytes[0] == self.device_no and reply_bytes[1] == cmd_no:
                    #Reply has a valid length and fits expected format
                    #Convert returned bytes into data value (handling negative values)
                    if reply_bytes[5] > 127:
                        reply_data = (pow(256,3) * reply_bytes[5] + pow(256,2) * reply_bytes[4] + pow(256,1) * reply_bytes[3] + pow(256,0) * reply_bytes[2]) - pow(256,4)
                    else:
                        reply_data = (pow(256,3) * reply_bytes[5] + pow(256,2) * reply_bytes[4] + pow(256,1) * reply_bytes[3] + pow(256,0) * reply_bytes[2])      
                elif reply_bytes[0] == self.device_no and reply_bytes[1] == 255:
                    self.error = 1
                    self.error_message = "Error - Motor reports an error as occured"
                else:
                    self.error = 1
                    self.error_message = "Error - Reply does not fit expected format"
            else:
                self.error = 1
                self.error_message = "Error - No valid reply received"
        return reply_data


    def ask_ID(self):
        '''Returns the ID of the motor. 
        
        If the ID is 6210, it is the vertical motor
        If the ID is 6320, it is the horizontal motor
        If the ID is 4152, it is the camera motor
        If the ID is 0, no motor was found
        ''' 
        cmd_no = 50
        cmd_param = 0 
        reply_data = self.__motorIO__(cmd_no, cmd_param)

        if not self.error:
            if reply_data == 6210:   
                self.ID = 6210
                self.name = "T-LSM050A"
                self.micro_step = 0.047625
            elif reply_data == 6320:
                self.ID = 6320
                self.name = "T-LSM100B"
                self.micro_step = 0.19050
            elif reply_data == 4152:
                self.ID = 4152
                self.name = "T-LSR150B"
                self.micro_step = 0.49609
            else:
                self.error = 1
                self.error_message = "Error - Unknown Device"
                self.ID = 0
                self.name = "Unsupported device"
                self.micro_step = 0
        else:
            self.ID = 0
            self.name = ""
            self.micro_step = 0
        return self.ID
    
    def byte_to_int(self,byte): ###pourquoi pas int.from_bytes(byte)
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

        cmd_no = 60
        cmd_param = 0 
        reply_data = self.__motorIO__(cmd_no, cmd_param)
        
        #The first two conditions are there to avoid a result with a huge number of decimals for the extremum positions. These could be taken off later
        #by controling the number of decimals to display on the associated label of the GUI
        if reply_data == 1066666:
                return 0
        elif reply_data == 533333:
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
                    return 0.0508-self.data_to_position(reply_data,unit)
                elif unit == "cm":
                    return 5.08-self.data_to_position(reply_data,unit)
                elif unit == "mm":
                    return 50.8-self.data_to_position(reply_data,unit)
                elif unit =='\u03BCm':
                    return 50800-self.data_to_position(reply_data,unit)
                elif unit == '\u03BCStep':
                    return 1066666-self.data_to_position(reply_data,unit)
        else:
            return self.data_to_position(reply_data,unit)


    def move_absolute_position(self, absolute_position, unit):
        '''Moves the device to a specified absolute position.
        
        Parameters:
            absolutePosition: Numerical value of the absolute position
            unit: A string which indicate the scale of the numerical value.
                  The options are: 'm', 'cm', 'mm', '\u03BCm' (micro meter) and '\u03BCStep' (micro-step)
                  
        For the horizontal motors, position 0 is the home position.
        For the vertical motor, height 0 is the maximum position.
        '''
        position = 0
        if self.ID == 6210:
            position = 1066666 - self.position_to_data(absolute_position,unit)
        elif self.ID == 6320:
            position = self.position_to_data(absolute_position,unit)
        elif self.ID == 4152:
            position = self.position_to_data(absolute_position,unit)

        cmd_no = 20
        cmd_param = position 
        self.__motorIO__(cmd_no, cmd_param)

    
    def move_home(self):
        '''Moves the device to home position. For the vertical motor, it matches the maximum height. '''
        cmd_no = 20
        cmd_param = 0
        self.__motorIO__(cmd_no, cmd_param)

        
    def move_maximum_position(self):
        '''Moves the device to its maximum position. For the vertical motor it matches the minimum height.  '''
        position = 0
        if self.ID == 6210:
            position = 1066666
        elif self.ID == 6320:
            position = 533333
        elif self.ID == 4152:
            position = 258015

        cmd_no = 20
        cmd_param = position
        self.__motorIO__(cmd_no, cmd_param)


    def move_relative_position(self, relative_position, unit):
        '''Moves the device to a specified relative position
        
        Parameters:
            relativePosition: Numerical value of the relative motion
            unit: A string which indicate the scale of the numerical value.
                  The options are: 'm', 'cm', 'mm', '\u03BCm' (micro meter) and '\u03BCStep' (micro-step)
        '''
        cmd_no = 21
        cmd_param = self.position_to_data(relative_position, unit)
        self.__motorIO__(cmd_no, cmd_param)  


    def data_to_position(self, data, unit):
        '''Converts a data into a position 
        
        Parameters:
            data: An integer or a float
            unit: A string wich specifies the unit into which the position will be converted. 
                  The options are: 'm', 'cm', 'mm', '\u03BCm' (micro meter) and '\u03BCStep' (micro-step) 
        '''
        factor = 1
        micro_step = self.micro_step
        
        if unit == 'm':
            factor = 1
        elif unit == 'cm':
            factor = pow(10,-2)
        elif unit == 'mm':
            factor = pow(10,-3)
        elif unit == '\u03BCm':
            factor = pow(10,-6)
        elif unit == '\u03BCStep':
            factor = micro_step*pow(10,-6)
            
        return data*micro_step*pow(10,-6)/factor

    def position_to_data(self, position, unit):
        '''Converts the position into the form of a data 
        
        Parameters:
            position: Numerical value of the position
            unit: A string which specifies the unit of the numerical position. 
                  The options are: 'm', 'cm', 'mm', '\u03BCm' (micro meter) and '\u03BCStep' (micro-step) 
        '''
        factor = 1
        micro_step = self.micro_step
        
        if unit == 'm':
            factor = 1
        elif unit == 'cm':
            factor = pow(10,-2)
        elif unit == 'mm':
            factor = pow(10,-3)
        elif unit == '\u03BCm':
            factor = pow(10,-6)
        elif unit == '\u03BCStep':
            factor = micro_step*pow(10,-6)
        
        return position*factor/(micro_step*pow(10,-6))