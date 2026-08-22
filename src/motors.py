"""
Created on February 10, 2022

"""

import logging

import serial
from lightsheet.config import cfg_read, cfg_str2bool, cfg_write

logger = logging.getLogger(__name__)


class Motors:
    """Class for translation stages"""

    # Configurable settings defaults
    # Used as base dictionnary for .ini file allowable keys
    _cfg_defaults: dict = {}  # noqa: RUF012 - class-level config template, populated at definition, never mutated at runtime
    _cfg_defaults["Port"] = "COM3"
    _cfg_defaults["Device Number Vertical"] = "1"
    _cfg_defaults["Device Number Horizontal"] = "2"
    _cfg_defaults["Device Number Camera"] = "3"
    _cfg_defaults["Vertical Inverted"] = "False"
    _cfg_defaults["Vertical Units"] = "mm"
    _cfg_defaults["Vertical Origin"] = "0.0"
    _cfg_defaults["Vertical Limit Low"] = "0.0"
    _cfg_defaults["Vertical Limit High"] = "10.0"
    _cfg_defaults["Horizontal Inverted"] = "False"
    _cfg_defaults["Horizontal Units"] = "mm"
    _cfg_defaults["Horizontal Origin"] = "0.0"
    _cfg_defaults["Horizontal Limit Low"] = "0.0"
    _cfg_defaults["Horizontal Limit High"] = "10.0"
    _cfg_defaults["Camera Inverted"] = "False"
    _cfg_defaults["Camera Units"] = "mm"
    _cfg_defaults["Camera Origin"] = "0.0"
    _cfg_defaults["Camera Limit Low"] = "0.0"
    _cfg_defaults["Camera Limit High"] = "50.0"

    def __init__(self):
        # Error status
        self.error = 0
        self.error_message = ""

        # read configurable settings from config.ini file
        self._cfg_filename = "config.ini"
        self._cfg_section = "Motors"
        self.cfg_load_ini()

        # check existance of vertical, horizontal and camera motors
        # and apply initial configuration
        self.vertical = ZaberMotor(self.port, self.device_no_vertical)
        if self.vertical.is_supported:
            self.vertical.set_inverted(self.vertical_inverted)
            self.vertical.set_units(self.vertical_units)
            self.vertical.set_origin(self.vertical_origin, self.vertical_units)
            self.vertical.set_limit_low(self.vertical_limit_low, self.vertical_units)
            self.vertical.set_limit_high(self.vertical_limit_high, self.vertical_units)

        self.horizontal = ZaberMotor(self.port, self.device_no_horizontal)
        if self.horizontal.is_supported:
            self.horizontal.set_inverted(self.horizontal_inverted)
            self.horizontal.set_units(self.horizontal_units)
            self.horizontal.set_origin(self.horizontal_origin, self.horizontal_units)
            self.horizontal.set_limit_low(
                self.horizontal_limit_low, self.horizontal_units
            )
            self.horizontal.set_limit_high(
                self.horizontal_limit_high, self.horizontal_units
            )

        self.camera = ZaberMotor(self.port, self.device_no_camera)
        if self.camera.is_supported:
            self.camera.set_inverted(self.camera_inverted)
            self.camera.set_units(self.camera_units)
            self.camera.set_origin(self.camera_origin, self.camera_units)
            self.camera.set_limit_low(self.camera_limit_low, self.camera_units)
            self.camera.set_limit_high(self.camera_limit_high, self.camera_units)

    def cfg_load_ini(self):
        self._cfg = cfg_read(self._cfg_filename, self._cfg_section, self._cfg_defaults)
        # set instance variables from configuration dictionary values
        self.port = str(self._cfg["Port"])
        self.device_no_vertical = int(self._cfg["Device Number Vertical"])
        self.device_no_horizontal = int(self._cfg["Device Number Horizontal"])
        self.device_no_camera = int(self._cfg["Device Number Camera"])
        self.vertical_inverted = cfg_str2bool(self._cfg["Vertical Inverted"])
        self.vertical_units = str(self._cfg["Vertical Units"])
        self.vertical_origin = float(self._cfg["Vertical Origin"])
        self.vertical_limit_low = float(self._cfg["Vertical Limit Low"])
        self.vertical_limit_high = float(self._cfg["Vertical Limit High"])
        self.horizontal_inverted = cfg_str2bool(self._cfg["Horizontal Inverted"])
        self.horizontal_units = str(self._cfg["Horizontal Units"])
        self.horizontal_origin = float(self._cfg["Horizontal Origin"])
        self.horizontal_limit_low = float(self._cfg["Horizontal Limit Low"])
        self.horizontal_limit_high = float(self._cfg["Horizontal Limit High"])
        self.camera_inverted = cfg_str2bool(self._cfg["Camera Inverted"])
        self.camera_units = str(self._cfg["Camera Units"])
        self.camera_origin = float(self._cfg["Camera Origin"])
        self.camera_limit_low = float(self._cfg["Camera Limit Low"])
        self.camera_limit_high = float(self._cfg["Camera Limit High"])

    def cfg_save_ini(self):
        # pack current instance variables into configuration dictionary
        self._cfg = {}
        self._cfg["Port"] = str(self.port)
        self._cfg["Device Number Vertical"] = str(self.device_no_vertical)
        self._cfg["Device Number Horizontal"] = str(self.device_no_horizontal)
        self._cfg["Device Number Camera"] = str(self.device_no_camera)
        self._cfg["Vertical Inverted"] = str(self.vertical_inverted)
        self._cfg["Vertical Origin"] = str(self.vertical_origin)
        self._cfg["Vertical Limit Low"] = str(self.vertical_limit_low)
        self._cfg["Vertical Limit High"] = str(self.vertical_limit_high)
        self._cfg["Horizontal Inverted"] = str(self.horizontal_inverted)
        self._cfg["Horizontal Origin"] = str(self.horizontal_origin)
        self._cfg["Horizontal Limit Low"] = str(self.horizontal_limit_low)
        self._cfg["Horizontal Limit High"] = str(self.horizontal_limit_high)
        self._cfg["Camera Inverted"] = str(self.camera_inverted)
        self._cfg["Camera Origin"] = str(self.camera_origin)
        self._cfg["Camera Limit Low"] = str(self.camera_limit_low)
        self._cfg["Camera Limit High"] = str(self.camera_limit_high)
        self._cfg = cfg_write(self._cfg_filename, self._cfg_section, self._cfg)

    def get_properties(self):
        motors_properties = {}
        motors_properties.update({"vertical name": self.vertical.get_name()})
        motors_properties.update({"horizontal name": self.horizontal.get_name()})
        motors_properties.update({"camera name": self.camera.get_name()})
        return motors_properties

    def get_positions(self):
        motors_positions = {}
        motors_positions.update({"vertical position": self.vertical.get_position("mm")})
        motors_positions.update(
            {"horizontal position": self.horizontal.get_position("mm")}
        )
        motors_positions.update({"camera position": self.camera.get_position("mm")})
        return motors_positions


class ZaberMotor:
    """Class for Zaber's T-LS series linear stage motor control"""

    def __init__(self, port: str, device_number: int):
        # Error status
        self.error = 0
        self.error_message = ""

        # State flags
        self.is_supported = False

        # Default attributes
        self.id = 0
        self.name = ""
        self.inverted = False
        self.homed = False
        self.microstep_size = 0
        self.microsteps_max = 0
        self.units = "mm"
        self.limit_high_microsteps = 0
        self.limit_low_microsteps = 0
        self.origin_microsteps = 0

        self.port = port
        self.device_number = device_number
        self.ask_id()

    def _motorIO(self, cmd_no, cmd_param):
        # Default return
        reply_data = 0

        # Generate 6-byte instruction from cmd_no and cmd_param
        # Taking into account negative data (such as a relative motion)
        if cmd_param < 0:
            cmd_param = pow(256, 4) + cmd_param
        # Generates bytes 3 to 6
        byte_6 = int(cmd_param // pow(256, 3))
        cmd_param = cmd_param % pow(256, 3)
        byte_5 = int(cmd_param // pow(256, 2))
        cmd_param = cmd_param % pow(256, 2)
        byte_4 = int(cmd_param // pow(256, 1))
        cmd_param = cmd_param % pow(256, 1)
        byte_3 = int(cmd_param // pow(256, 0))
        # Assemble instruction
        instruction = []
        instruction.append(int(self.device_number))
        instruction.append(int(cmd_no))
        instruction.append(byte_3)
        instruction.append(byte_4)
        instruction.append(byte_5)
        instruction.append(byte_6)

        try:
            # Try to open a serial connection
            motor = serial.Serial(
                port=self.port,
                baudrate=9600,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=2,
            )
            # Clear I/O buffers
            motor.reset_input_buffer()
            motor.reset_output_buffer()
            # Write instruction bytes to motor
            motor.write(bytes(instruction))
            # Read 6-bytes reply
            reply_bytes = motor.read(6)
            # Close serial connection to motor
            motor.close()
        except Exception:
            self.error = 1
            self.error_message = "Serial port error"
            logger.exception("Serial port error!")
        else:
            # Checks if reply is valid length
            if len(reply_bytes) == 6:
                if reply_bytes[0] == self.device_number and reply_bytes[1] == cmd_no:
                    # Reply has a valid length and fits expected format.
                    # Clear any previous error so a transient serial glitch
                    # does not permanently block relative moves (which query
                    # position and check self.error before moving).
                    self.error = 0
                    self.error_message = ""
                    # Convert returned bytes into data value (handling negative values)
                    if reply_bytes[5] > 127:
                        reply_data = (
                            pow(256, 3) * reply_bytes[5]
                            + pow(256, 2) * reply_bytes[4]
                            + pow(256, 1) * reply_bytes[3]
                            + pow(256, 0) * reply_bytes[2]
                        ) - pow(256, 4)
                    else:
                        reply_data = (
                            pow(256, 3) * reply_bytes[5]
                            + pow(256, 2) * reply_bytes[4]
                            + pow(256, 1) * reply_bytes[3]
                            + pow(256, 0) * reply_bytes[2]
                        )
                elif reply_bytes[0] == self.device_number and reply_bytes[1] == 255:
                    self.error = 1
                    self.error_message = "Motor reports an error as occured"
                else:
                    self.error = 1
                    self.error_message = "Reply does not fit expected format"
            else:
                self.error = 1
                self.error_message = "No valid reply received"
        return reply_data

    def ask_id(self):
        """Returns the ID of the motor.

        Supported devices ID are:
        6210 -> T-LSM050A (vertical motor)
        6320 -> T-LSM100B (horizontal motor)
        4152 -> T-LSR150B (camera motor)
        """

        cmd_no = 50
        cmd_param = 0
        reply_data = self._motorIO(cmd_no, cmd_param)

        if not self.error:
            if reply_data == 6210:
                self.is_supported = True
                self.id = 6210
                self.name = "T-LSM050A"
                self.microstep_size = 0.047625
                self.microsteps_max = 1066666
            elif reply_data == 6320:
                self.is_supported = True
                self.id = 6320
                self.name = "T-LSM100B"
                self.microstep_size = 0.19050
                self.microsteps_max = 533333
            elif reply_data == 4152:
                self.is_supported = True
                self.id = 4152
                self.name = "T-LSR150B"
                self.microstep_size = 0.49609
                self.microsteps_max = 258015
            else:
                self.is_supported = False
                self.error = 1
                self.error_message = "Unsupported device"
                self.id = 0
                self.name = "Unsupported device"
        else:
            self.id = 0
            self.name = "Device not found"
        return self.id

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
        limit_high_units = self.microsteps_to_position(
            self.limit_high_microsteps, units
        )
        return limit_high_units

    def get_origin(self, units):
        origin_units = self.microsteps_to_position(self.origin_microsteps, units)
        return origin_units

    def get_name(self):
        return self.name

    def get_position(self, units):
        """Returns the current position of the device, converted to the unit specified.

        Parameter:
            unit: A string. Options: 'm', 'cm', 'mm', '\u03bcm' (micrometers),
                  '\u03bcStep' (microsteps)
        """
        if self.id != 0:
            cmd_no = 60
            cmd_param = 0
            reply_data = self._motorIO(cmd_no, cmd_param)
            position = self.microsteps_to_position(reply_data, units)
        else:
            position = 0
        return position

    def move_home(self):
        """Moves the device to its physical home position.

        Sends Zaber command 1 (physical home). This does NOT honor the
        configured travel limits — the stage homes to its mechanical end,
        not the configured origin. Not GUI-wired today; documented for any
        future caller.
        """
        if self.id != 0:
            cmd_no = 1
            cmd_param = 0
            self._motorIO(cmd_no, cmd_param)

    def move_absolute_position(self, absolute_position, units):
        """Moves the device to a specified absolute position.

        The target position is validated against the configured travel
        limits BEFORE any serial command is sent. An out-of-range target
        raises ValueError so the caller can reject-and-beep instead of
        silently over-traveling the stage.

        Parameters:
            absolutePosition: Numerical value of the absolute position
            unit: A string which indicate the scale of the numerical value.
                  Options: 'm', 'cm', 'mm', '\u03bcm' (micrometers),
                  '\u03bcStep' (microsteps)
        """
        if self.id != 0:
            target_microsteps = self.position_to_microsteps(absolute_position, units)
            if target_microsteps < self.limit_low_microsteps:
                raise ValueError(
                    f"Target position {absolute_position} {units}"
                    " is below the low travel limit"
                )
            if target_microsteps > self.limit_high_microsteps:
                raise ValueError(
                    f"Target position {absolute_position} {units}"
                    " exceeds the high travel limit"
                )
            cmd_no = 20
            self._motorIO(cmd_no, target_microsteps)

    def move_relative_position(self, relative_position, units):
        """Moves the device to a specified relative position.

        The RESULTING position (current position + delta) is validated
        against the configured travel limits BEFORE the move command is
        sent. Validating the resulting position rather than the raw delta
        catches small deltas that would push the stage past a limit when
        it is already near the edge of travel. An out-of-range resulting
        position raises ValueError.

        If the current position cannot be read (the position-query serial
        call leaves self.error truthy), ValueError is raised before any
        move is attempted — an unreadable position must not silently pass
        validation.

        Parameters:
            relativePosition: Numerical value of the relative motion
            unit: A string which indicate the scale of the numerical value.
                  Options: 'm', 'cm', 'mm', '\u03bcm' (micrometers),
                  '\u03bcStep' (microsteps)
        """
        if self.id != 0:
            delta_microsteps = self.position_to_microsteps(relative_position, units)
            # cmd 60 = get current position (matches get_position's internal call)
            current_microsteps = self._motorIO(60, 0)
            if self.error:
                raise ValueError(
                    "Cannot read current position to validate relative move"
                )
            resulting_microsteps = current_microsteps + delta_microsteps
            if resulting_microsteps < self.limit_low_microsteps:
                raise ValueError(
                    f"Relative move would result in {resulting_microsteps} microsteps, "
                    f"below the low travel limit of {self.limit_low_microsteps}"
                )
            if resulting_microsteps > self.limit_high_microsteps:
                raise ValueError(
                    f"Relative move would result in {resulting_microsteps} microsteps, "
                    f"exceeding the high travel limit of {self.limit_high_microsteps}"
                )
            cmd_no = 21
            self._motorIO(cmd_no, delta_microsteps)

    def microsteps_to_position(self, microsteps, units: str = "mm"):
        """Converts microsteps into position

        Parameters:
            microsteps: Numerical value
            unit: A string wich specifies the unit for position conversion.
                  Options: 'm', 'cm', 'mm', '\u03bcm' (micrometers),
                  '\u03bcStep' (microsteps)
        """
        if units == "m":
            factor = 1
        elif units == "cm":
            factor = pow(10, -2)
        elif units == "mm":
            factor = pow(10, -3)
        elif units == "\u03bcm":
            factor = pow(10, -6)
        elif units == "\u03bcStep":
            factor = self.microstep_size * pow(10, -6)

        if self.microstep_size > 0 and factor > 0:
            position = microsteps * self.microstep_size * pow(10, -6) / factor
        else:
            position = 0

        return position

    def position_to_microsteps(self, position, units: str = "mm"):
        """Converts position into microsteps

        Parameters:
            position: Numerical value of the position
            unit: A string which specifies the unit of the numerical position.
                  Options: 'm', 'cm', 'mm', '\u03bcm' (micrometers),
                  '\u03bcStep' (microsteps)
        """
        if units == "m":
            factor = 1
        elif units == "cm":
            factor = pow(10, -2)
        elif units == "mm":
            factor = pow(10, -3)
        elif units == "\u03bcm":
            factor = pow(10, -6)
        elif units == "\u03bcStep":
            factor = self.microstep_size * pow(10, -6)

        if self.microstep_size > 0 and factor > 0:
            microsteps = position * factor / (self.microstep_size * pow(10, -6))
        else:
            microsteps = 0

        return microsteps
