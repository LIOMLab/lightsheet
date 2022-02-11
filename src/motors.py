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

    '''Default positions (in mm)'''
    _positions = {}
    _positions['Vertical Limit Up'] = 19.4
    _positions['Vertical Limit Down'] = 0
    _positions['Vertical Origin'] = _positions['Vertical Limit Down']
    _positions['Horizontal Limit Forward'] = 0
    _positions['Horizontal Limit Backward'] = 15
    _positions['Horizontal Origin'] = _positions['Horizontal Limit Forward']
    _positions['Camera Limit Forward'] = 50.0
    _positions['Camera Limit Backward'] = 115
    _positions['Camera Focus'] = 55.0

    def __init__(self):
        self.cfg_default()
        self.cfg_read()
        self.vertical   = zaberMotor(self.motors['Port'], self.motors['Device Number Vertical'])    #Vertical motor
        self.horizontal = zaberMotor(self.motors['Port'], self.motors['Device Number Horizontal'])  #Horizontal motor for sample motion
        self.camera     = zaberMotor(self.motors['Port'], self.motors['Device Number Camera'])      #Horizontal motor for camera motion (detection arm)

    def cfg_default(self):
        # Copy default values to current values
        self.motors = copy.deepcopy(self._motors)

    def cfg_read(self):
        cfg = ConfigParser()
        cfg.optionxform = str
        cfg.read('config.ini')
        for key, value in cfg['Motors'].items():
            self.motors[key] = value

    def cfg_write(self):
        cfg = ConfigParser()
        cfg.optionxform = str
        cfg.read('config.ini')
        for key in self.motors:
            cfg.set('Motors', str(key), str(self.motors[key]))
        with open('config.ini', 'w') as output_file:
            cfg.write(output_file)
    
    def get_positions(self):
        return [self.vertical.current_position(), self.horizontal.current_position(), self.camera.current_position()]
    
    def get_names(self):
        return [self.vertical.get_name(), self.horizontal.get_name(), self.camera.get_name()]



class zaberMotor:
    '''Class for Zaber's T-LSM series linear stage motor control'''

    def __init__(self, port, device_number):
        '''device_number is the number of the device in the daisy chain '''
        self.error = 0
        self.error_message = ""
        self.port = port
        self.device_number = device_number
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
                self.micro_step = 1
        else:
            self.ID = 0
            self.name = ""
            self.micro_step = 1
        return self.ID
    
    def get_name(self):
        return self.name
    
    def get_id(self):
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

