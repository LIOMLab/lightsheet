'''
Created on May 16, 2019

@author: flesage
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
from src.waveforms import DO_signal
from src.waveforms import laser_signal


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
        
    
    def create_DO_camera_waveform(self):
        self.camera_waveform = DO_signal(samplerate = self.parameters["samplerate"], 
                                            sweeptime = self.parameters["sweeptime"], 
                                            delay = self.parameters["etl_l_delay"], 
                                            rise = self.parameters["etl_l_ramp_rising"], 
                                            fall = self.parameters["etl_l_ramp_falling"])
        
        
    def create_lasers_waveforms(self):
        self.laser_l_waveform = laser_signal(samplerate = self.parameters["samplerate"], 
                                             sweeptime = self.parameters["sweeptime"], 
                                             voltage = self.parameters["laser_l_voltage"])
        
        self.laser_r_waveform = laser_signal(samplerate = self.parameters["samplerate"], 
                                             sweeptime = self.parameters["sweeptime"], 
                                             voltage = self.parameters["laser_r_voltage"])
        

    def create_tasks(self, terminals, acquisition):
        '''Creates a total of four tasks for the mesoSPIM:

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
        
        self.calculate_samples()

        #self.master_trigger_task = nidaqmx.Task()
        self.galvo_etl_task = nidaqmx.Task(new_task_name='galvo_etl_ramps')
        self.camera_task = nidaqmx.Task(new_task_name='camera_do_signal')
        self.laser_task = nidaqmx.Task(new_task_name='laser_ramps')


        '''Housekeeping: Setting up the AO task for the Galvo and ETLs. It is the master task'''
        self.galvo_etl_task.ao_channels.add_ao_voltage_chan(terminals["galvos_etls"])
        self.galvo_etl_task.timing.cfg_samp_clk_timing(rate=self.parameters["samplerate"],
                                                   sample_mode=mode,
                                                   samps_per_chan=self.samples)
        
        self.camera_task.do_channels.add_do_chan(terminals["camera"], line_grouping = LineGrouping.CHAN_PER_LINE)
        self.camera_task.timing.cfg_samp_clk_timing(rate=self.parameters["samplerate"], sample_mode=mode, samps_per_chan=self.samples)
        
        self.laser_task.ao_channels.add_ao_voltage_chan(terminals["lasers"])
        self.laser_task.timing.cfg_samp_clk_timing(rate=self.parameters["samplerate"], sample_mode=mode, samps_per_chan=self.samples)
        
        '''Configures the task to start acquiring/generating samples on a rising/falling edge of a digital signal. 
            args: terminal of the trigger source, which edge of the digital signal the task start (optionnal) '''
        self.camera_task.triggers.start_trigger.cfg_dig_edge_start_trig('/Dev1/ao/StartTrigger', trigger_edge=Edge.RISING)
        #self.laser_task.triggers.start_trigger.cfg_dig_edge_start_trig('/Dev1/ao/StartTrigger', trigger_edge=Edge.RISING)

        '''Housekeeping: Setting up the AO task for the ETL and lasers and setting the trigger input'''
        #self.laser_task.ao_channels.add_ao_voltage_chan(ah['laser_task_line'])
        #self.laser_task.timing.cfg_samp_clk_timing(rate=samplerate,
        #                                            sample_mode=AcquisitionType.FINITE,
        #                                            samps_per_chan=samples)
        #self.laser_task.triggers.start_trigger.cfg_dig_edge_start_trig(ah['laser_task_trigger_source'])    
    
    def write_waveforms_to_tasks(self):
        '''Write the waveforms to the slave tasks'''
        self.galvo_and_etl_waveforms = np.stack((self.galvo_r_waveform,
                                                 self.galvo_l_waveform,
                                                 self.etl_r_waveform,
                                                 self.etl_l_waveform))
       
        self.galvo_etl_task.write(self.galvo_and_etl_waveforms)
        
        self.camera_task.write(self.camera_waveform)
        
        self.lasers_waveforms = np.stack((self.laser_r_waveform,
                                          self.laser_l_waveform))
        
        self.laser_task.write(self.lasers_waveforms)

    def start_tasks(self):
        '''Starts the tasks for camera triggering and analog outputs

        If the tasks are configured to be triggered, they won't output any
        signals until run_tasks() is called.
        '''
        
        self.laser_task.start()
        self.camera_task.start()
        self.galvo_etl_task.start()
    
    #This function is only for FINITE task, we don't call it for CONTINUOUS
    def run_tasks(self):
        '''Runs the tasks for triggering, analog and counter outputs

        Firstly, the master trigger triggers all other task via a shared trigger
        line (PFI line as given in the config file).

        For this to work, all analog output and counter tasks have to be started so
        that they are waiting for the trigger signal.
        '''
        #self.master_trigger_task.write([False, True, True, True, False], auto_start=True)
        

        '''Wait until everything is done - this is effectively a sleep function.'''
      
        self.laser_task.wait_until_done()
        self.camera_task.wait_until_done()
        self.galvo_etl_task.wait_until_done()

    def stop_tasks(self):
        '''Stops the tasks for triggering, analog and counter outputs'''
        
        self.laser_task.stop()
        self.camera_task.stop()
        self.galvo_etl_task.stop()

    def close_tasks(self):
        '''Closes the tasks for triggering, analog and counter outputs.

        Tasks should only be closed are they are stopped.
        '''
        
        self.laser_task.close()
        self.camera_task.close()
        self.galvo_etl_task.close()
        
        
        
        
        
        
        
class Motors:
    
    def __init__(self, deviceNumber, port):
        '''deviceNumber is the number of the device in the daisy chain '''
        self.deviceNumber = deviceNumber
        self.port = port
        self.ID = self.ask_ID()
        
    
    def generate_command(self,cmdNumber,data):
        '''Generates the command to send to the motor device
        
        Parameters:
            cmdNumber: Determines the type of operation (see Zaber T-LSM series User's Manual for a complete list)
            data: The value associated to the cmdNumber
        '''
        command=[self.deviceNumber,cmdNumber]
        
        #To take into account negative data (such as a relative motion)
        if data < 0:
            data = pow(256,4) + data
        
        #Generates bytes 3 to 6
        Byte6 = int(data//pow(256,3))
        data = data - Byte6*pow(256,3)
        Byte5 = int(data//pow(256,2))
        data = data - Byte5*pow(256,2)
        Byte4 = int(data//256)
        data = data - Byte4*256
        Byte3 = int(data//1)
        
        command.append(Byte3)
        command.append(Byte4)
        command.append(Byte5)
        command.append(Byte6)
        #command=bytearray(command)
        
        return bytearray(command)
    
    def byte_to_int(self,byte):
        '''Converts bytes into an integer'''
        
        result = 0
        for b in byte:
            result = result * 256 + int(b)
        return result
    
    
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
        lastRead = []
        for i in range(6):
            lastRead.append(self.byte_to_int(motor.read(1)))
        
        #Byte3 (index 2) is the least significant byte of the data read and can determine alone the ID in this case
        if lastRead[2] == 66:
            ID = 6210
        elif lastRead[2] == 176:
            ID = 6320
        
        motor.close()
        
        return ID
    
    
    def data_to_position(self,data,unit):
        '''Converts a data into a position 
        
        Parameters:
            data: An integer or a float
            unit: A string wich specifies the unit into which the position will be converted. 
                  The options are: 'm', 'cm', 'mm', '\u03BCm' (micro meter) and '\u03BCStep' (micro-step) 
        '''
        factor = 0
        microStep = 0
        
        #The microstep size, necessary for the conversion, differs from each type of device
        if self.ID == 6210:
            microStep = 0.047625
        elif self.ID == 6320:
            microStep = 0.1905
       
        if unit == 'm':
            factor = 1
        elif unit == 'cm':
            factor=pow(10,-2)
        elif unit == 'mm':
            factor=pow(10,-3)
        elif unit == '\u03BCm':
            factor=pow(10,-6)
        elif unit == '\u03BCStep':
            factor = microStep*pow(10,-6)
            
        return data*microStep*pow(10,-6)/factor
    
    
    def position_to_data(self,position,unit):
        '''Converts the position into the form of a data 
        
        Parameters:
            position: Numerical value of the position
            unit: A string which specifies the unit of the numerical position. 
                  The options are: 'm', 'cm', 'mm', '\u03BCm' (micro meter) and '\u03BCStep' (micro-step) 
        '''
        factor = 0
        microStep = 0
        
        #The microstep size, necessary for the conversion, differs from each type of device
        if self.ID == 6210:
            microStep = 0.047625
        elif self.ID == 6320:
            microStep = 0.1905
        
        if unit == 'm':
            factor = 1
        elif unit == 'cm':
            factor=pow(10,-2)
        elif unit == 'mm':
            factor=pow(10,-3)
        elif unit == '\u03BCm':
            factor=pow(10,-6)
        elif unit == '\u03BCStep':
            factor = microStep*pow(10,-6)
        
        return position*factor/(microStep*pow(10,-6))
    
    
    def current_position(self, unit):
        '''Returns the current position of the device. The position is converted into the unit specified. 
        
        Parameter:
            unit: A string. The options are: 'm', 'cm', 'mm', '\u03BCm' (micro meter) and '\u03BCStep' (micro-step)
        '''
        motor=serial.Serial(port=self.port,baudrate=9600,bytesize=serial.EIGHTBITS,parity=serial.PARITY_NONE,stopbits=serial.STOPBITS_ONE)
        cmdNumber = 60
        command = self.generate_command(cmdNumber,0)
        motor.write(command)
        
        lastRead = []
        for i in range(6):
            lastRead.append(self.byte_to_int(motor.read(1)))
        
        motor.close()
        
        data = pow(256,3)*lastRead[5]+pow(256,2)*lastRead[4]+256*lastRead[3]+lastRead[2]
        
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
        
    
    def move_absolute_position(self, absolutePosition, unit):
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
            data = 1066666-self.position_to_data(absolutePosition,unit)
        elif self.ID == 6320:
            data = self.position_to_data(absolutePosition,unit)
        
        command = self.generate_command(20,data)
        motor.write(command)
        #All the reply bytes are read, so they doesn't interfere with further operations, suchas self.current_position(unit)
        motor.read(6)
        
        motor.close()
        
        
    def move_relative_position(self, relativePosition, unit):
        '''Moves the device to a specified relative position
        
        Parameters:
            relativePosition: Numerical value of the relative motion
            unit: A string which indicate the scale of the numerical value.
                  The options are: 'm', 'cm', 'mm', '\u03BCm' (micro meter) and '\u03BCStep' (micro-step)
        '''
        motor=serial.Serial(port=self.port,baudrate=9600,bytesize=serial.EIGHTBITS,parity=serial.PARITY_NONE,stopbits=serial.STOPBITS_ONE)
        
        data = self.position_to_data(relativePosition, unit)
        command = self.generate_command(21,data)
        motor.write(command)
        #All the reply bytes are read, so they doesn't interfere with further operations, suchas self.current_position(unit)
        motor.read(6)
        
        motor.close()