'''
Created on February 10, 2022

'''

import sys
sys.path.append(".")

import copy
import serial
from configparser import ConfigParser

class Motors:

    '''Default hardware configuration'''
    _motors = {}
    _motors['Port'] = 'COM3'
    _motors['Device Number Vertical'] = 1
    _motors['Device Number Horizontal'] = 2
    _motors['Device Number Camera'] = 3

    '''Default axis settings (positions in mm)'''
    _settings = {}
    _settings['Vertical Inverted'] = False
    _settings['Vertical Units'] = 'mm'
    _settings['Vertical Origin'] = 0.0
    _settings['Vertical Limit Low'] = 0.0
    _settings['Vertical Limit High'] = 10.0
    _settings['Horizontal Inverted'] = False
    _settings['Horizontal Units'] = 'mm'
    _settings['Horizontal Origin'] = 0.0
    _settings['Horizontal Limit Low'] = 0.0
    _settings['Horizontal Limit High'] = 10.0
    _settings['Camera Inverted'] = False
    _settings['Camera Units'] = 'mm'
    _settings['Camera Origin'] = 0.0
    _settings['Camera Limit Low'] = 0.0
    _settings['Camera Limit High'] = 50.0

    def __init__(self):
        self.cfg_default()
        self.cfg_read()

        self.vertical = zaberMotor(str(self.motors['Port']), int(self.motors['Device Number Vertical']))
        self.vertical.set_inverted(bool(self.settings['Vertical Inverted']))
        self.vertical.set_units(str(self.settings['Vertical Units']))
        self.vertical.set_origin(float(self.settings['Vertical Origin']), str(self.settings['Vertical Units']))
        self.vertical.set_limit_low(float(self.settings['Vertical Limit Low']), str(self.settings['Vertical Units']))
        self.vertical.set_limit_high(float(self.settings['Vertical Limit High']), str(self.settings['Vertical Units']))

        self.horizontal = zaberMotor(str(self.motors['Port']), int(self.motors['Device Number Horizontal']))
        self.horizontal.set_inverted(bool(self.settings['Horizontal Inverted']))
        self.horizontal.set_units(str(self.settings['Horizontal Units']))
        self.horizontal.set_origin(float(self.settings['Horizontal Origin']), str(self.settings['Horizontal Units']))
        self.horizontal.set_limit_low(float(self.settings['Horizontal Limit Low']), str(self.settings['Horizontal Units']))
        self.horizontal.set_limit_high(float(self.settings['Horizontal Limit High']), str(self.settings['Horizontal Units']))

        self.camera = zaberMotor(self.motors['Port'], int(self.motors['Device Number Camera']))
        self.camera.set_inverted(bool(self.settings['Camera Inverted']))
        self.camera.set_units(str(self.settings['Camera Units']))
        self.camera.set_origin(float(self.settings['Camera Origin']), str(self.settings['Camera Units']))
        self.camera.set_limit_low(float(self.settings['Camera Limit Low']), str(self.settings['Camera Units']))
        self.camera.set_limit_high(float(self.settings['Camera Limit High']), str(self.settings['Camera Units']))


    def cfg_default(self):
        # Copy default values to current values
        self.motors = copy.deepcopy(self._motors)
        self.settings = copy.deepcopy(self._settings)

    def cfg_read(self):
        cfg = ConfigParser()
        cfg.optionxform = str
        cfg.read('config.ini')
        for key, value in cfg['Motors'].items():
            self.motors[key] = value
        for key, value in cfg['AxisSettings'].items():
            self.settings[key] = value

    def cfg_write(self):
        cfg = ConfigParser()
        cfg.optionxform = str
        cfg.read('config.ini')
        for key in self.motors:
            cfg.set('Motors', str(key), str(self.motors[key]))
        for key in self.settings:
            cfg.set('AxisSettings', str(key), str(self.settings[key]))

        with open('config.ini', 'w') as output_file:
            cfg.write(output_file)
    


class zaberMotor:
    '''Class for Zaber's T-LS series linear stage motor control'''

    '''Default attributes'''
    ID = 0
    name = ""
    inverted = False
    homed = False
    microstep_size = 0
    microsteps_max = 0
    units = 'mm'
    limit_high_microsteps = 0
    limit_low_microsteps = 0
    origin_microsteps = 0


    def __init__(self, port:str, device_number:int):
        '''device_number is the number of the device in the daisy chain '''
        self.error = 0
        self.error_message = ""
        self.port = port
        self.device_number = device_number
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
            motor = serial.Serial(port = self.port, baudrate = 9600, bytesize = serial.EIGHTBITS, parity = serial.PARITY_NONE, stopbits = serial.STOPBITS_ONE, timeout = 2)
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
                if reply_bytes[0] == self.device_number and reply_bytes[1] == cmd_no:
                    #Reply has a valid length and fits expected format
                    #Convert returned bytes into data value (handling negative values)
                    if reply_bytes[5] > 127:
                        reply_data = (pow(256,3) * reply_bytes[5] + pow(256,2) * reply_bytes[4] + pow(256,1) * reply_bytes[3] + pow(256,0) * reply_bytes[2]) - pow(256,4)
                    else:
                        reply_data = (pow(256,3) * reply_bytes[5] + pow(256,2) * reply_bytes[4] + pow(256,1) * reply_bytes[3] + pow(256,0) * reply_bytes[2])      
                elif reply_bytes[0] == self.device_number and reply_bytes[1] == 255:
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
        
        Supported devices ID are:
        6210 - T-LSM050A (vertical motor)
        6320 - T-LSM100B (horizontal motor)
        4152 - T-LSR150B (camera motor)
        ''' 

        cmd_no = 50
        cmd_param = 0 
        reply_data = self.__motorIO__(cmd_no, cmd_param)

        if not self.error:
            if reply_data == 6210:   
                self.ID = 6210
                self.name = "T-LSM050A"
                self.microstep_size = 0.047625
                self.microsteps_max = 1066666
            elif reply_data == 6320:
                self.ID = 6320
                self.name = "T-LSM100B"
                self.microstep_size = 0.19050
                self.microsteps_max = 533333
            elif reply_data == 4152:
                self.ID = 4152
                self.name = "T-LSR150B"
                self.microstep_size = 0.49609
                self.microsteps_max = 258015
            else:
                self.error = 1
                self.error_message = "Error - Unsupported device"
                self.ID = 0
                self.name = "Unsupported device"
        else:
            self.ID = 0
            self.name = ""
        return self.ID

    def set_units(self, units: str):
        self.units = units

    def set_inverted(self, inverted: bool):
        self.inverted = inverted

    def set_limit_low(self, position, units):
        self.limit_low_microsteps = self.position_to_microsteps(position, units)

    def set_limit_high(self, position, units):
        self.limit_high_microsteps = self.position_to_microsteps(position, units)

    def set_origin(self, position, units):
        self.origin_microsteps = self.position_to_microsteps(position, units)
        
    def get_units(self):
        return self.units

    def get_inverted(self):
        return self.inverted

    def get_limit_low(self, units):
        limit_low_units = self.microsteps_to_position(self.limit_low_microsteps, units)
        return limit_low_units

    def get_limit_high(self, units):
        limit_high_units = self.microsteps_to_position(self.limit_high_microsteps, units)
        return limit_high_units

    def get_origin(self, units):
        origin_units = self.microsteps_to_position(self.origin_microsteps, units)
        return origin_units

    def get_name(self):
        return self.name

    def get_position(self, units):
        '''Returns the current position of the device. The position is converted into the unit specified. 
        
        Parameter:
            unit: A string. The options are: 'm', 'cm', 'mm', '\u03BCm' (micrometers) and '\u03BCStep' (microsteps)
        '''
        if self.ID != 0:
            cmd_no = 60
            cmd_param = 0 
            reply_data = self.__motorIO__(cmd_no, cmd_param)
            position = self.microsteps_to_position(reply_data, units)
        else:
            position = 0
        return position

    def move_home(self):
        '''Moves the device to home position.'''
        if self.ID != 0:
            cmd_no = 1
            cmd_param = 0
            self.__motorIO__(cmd_no, cmd_param)

    def move_absolute_position(self, absolute_position, units):
        '''Moves the device to a specified absolute position.
        
        Parameters:
            absolutePosition: Numerical value of the absolute position
            unit: A string which indicate the scale of the numerical value.
                  The options are: 'm', 'cm', 'mm', '\u03BCm' (micrometers) and '\u03BCStep' (microsteps)
                  
        '''
        if self.ID != 0:        
            cmd_no = 20
            cmd_param = self.position_to_microsteps(absolute_position, units)
            self.__motorIO__(cmd_no, cmd_param)


    def move_relative_position(self, relative_position, units):
        '''Moves the device to a specified relative position
        
        Parameters:
            relativePosition: Numerical value of the relative motion
            unit: A string which indicate the scale of the numerical value.
                  The options are: 'm', 'cm', 'mm', '\u03BCm' (micrometers) and '\u03BCStep' (microsteps)
        '''
        if self.ID != 0:
            cmd_no = 21
            cmd_param = self.position_to_microsteps(relative_position, units)
            self.__motorIO__(cmd_no, cmd_param)  


    def move_maximum_position(self):
        '''Moves the device to its maximum position.'''
        if self.ID != 0:
            cmd_no = 20
            cmd_param = self.microsteps_max
            self.__motorIO__(cmd_no, cmd_param)


    def microsteps_to_position(self, microsteps, units):
        '''Converts microsteps into position 
        
        Parameters:
            microsteps: Numerical value
            unit: A string wich specifies the unit into which the position will be converted. 
                  The options are: 'm', 'cm', 'mm', '\u03BCm' (micrometers) and '\u03BCStep' (microsteps) 
        '''
        if units == 'm':
            factor = 1
        elif units == 'cm':
            factor = pow(10,-2)
        elif units == 'mm':
            factor = pow(10,-3)
        elif units == '\u03BCm':
            factor = pow(10,-6)
        elif units == '\u03BCStep':
            factor = self.microstep_size * pow(10,-6)
            
        if self.microstep_size > 0 and factor > 0:
            position = microsteps * self.microstep_size * pow(10,-6) / factor
        else:
            position = 0

        return position


    def position_to_microsteps(self, position, units):
        '''Converts position into microsteps 
        
        Parameters:
            position: Numerical value of the position
            unit: A string which specifies the unit of the numerical position. 
                  The options are: 'm', 'cm', 'mm', '\u03BCm' (micrometers) and '\u03BCStep' (microsteps) 
        '''
        if units == 'm':
            factor = 1
        elif units == 'cm':
            factor = pow(10,-2)
        elif units == 'mm':
            factor = pow(10,-3)
        elif units == '\u03BCm':
            factor = pow(10,-6)
        elif units == '\u03BCStep':
            factor = self.microstep_size * pow(10,-6)

        if self.microstep_size > 0 and factor > 0:
            microsteps = position * factor / (self.microstep_size * pow(10,-6))
        else:
            microsteps = 0
        
        return microsteps

