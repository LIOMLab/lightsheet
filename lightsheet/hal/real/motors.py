"""
Created on February 10, 2022

"""

import logging
import threading

import serial

from lightsheet.config import cfg_read, cfg_str2bool, cfg_write
from lightsheet.hal.interfaces import IMotor, IMotors

logger = logging.getLogger(__name__)


class Motors(IMotors):
    """Class for translation stages"""

    # Configurable settings defaults
    # Used as base dictionnary for .ini file allowable keys
    _cfg_defaults: dict[str, str] = {}  # noqa: RUF012 - class-level config template, populated at definition, never mutated at runtime
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

    def __init__(self, port: str | None = None) -> None:
        # Error status
        self.error = 0
        self.error_message = ""

        # read configurable settings from config.ini file
        self._cfg_filename = "config.ini"
        self._cfg_section = "Motors"
        self.cfg_load_ini()

        # Allow the composition root (DeviceRegistry) to override the
        # configured Port with a live USB-serial resolved value. If no port
        # is supplied, the config.ini value loaded above is used.
        if port is not None:
            self.port = port

        # Serialize all traffic on the shared Zaber serial bus. The worker,
        # GUI position refresh, and configuration commands must not interleave
        # on the same COM port; otherwise a reset_input_buffer() from one caller
        # can cancel an in-flight read() from another and wedge the port.
        self._io_lock = threading.RLock()

        # Open ONE shared serial handle for the lifetime of the bundle.
        # The real Zaber T-LSR chain on COM7 is shared across all 3 devices.
        # serial-open is unreachable on Mac (no Zaber stage).
        self._serial = serial.Serial(  # pragma: no branch
            port=self.port,
            baudrate=9600,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=2,
        )

        # check existance of vertical, horizontal and camera motors
        # and apply initial configuration
        self.vertical = ZaberMotor(self._serial, self.device_no_vertical, self._io_lock)
        if self.vertical.is_supported:
            self.vertical.set_inverted(self.vertical_inverted)
            self.vertical.set_units(self.vertical_units)
            self.vertical.set_origin(self.vertical_origin, self.vertical_units)
            self.vertical.set_limit_low(self.vertical_limit_low, self.vertical_units)
            self.vertical.set_limit_high(self.vertical_limit_high, self.vertical_units)

        self.horizontal = ZaberMotor(self._serial, self.device_no_horizontal, self._io_lock)
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

        self.camera = ZaberMotor(self._serial, self.device_no_camera, self._io_lock)
        if self.camera.is_supported:
            self.camera.set_inverted(self.camera_inverted)
            self.camera.set_units(self.camera_units)
            self.camera.set_origin(self.camera_origin, self.camera_units)
            self.camera.set_limit_low(self.camera_limit_low, self.camera_units)
            self.camera.set_limit_high(self.camera_limit_high, self.camera_units)

    def cfg_load_ini(self) -> None:
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

    def cfg_save_ini(self) -> None:
        # pack current instance variables into configuration dictionary
        self._cfg = {}
        self._cfg["Port"] = str(self.port)
        self._cfg["Device Number Vertical"] = str(self.device_no_vertical)
        self._cfg["Device Number Horizontal"] = str(self.device_no_horizontal)
        self._cfg["Device Number Camera"] = str(self.device_no_camera)
        self._cfg["Vertical Inverted"] = str(self.vertical_inverted)
        self._cfg["Vertical Units"] = str(self.vertical_units)
        self._cfg["Vertical Origin"] = str(self.vertical_origin)
        self._cfg["Vertical Limit Low"] = str(self.vertical_limit_low)
        self._cfg["Vertical Limit High"] = str(self.vertical_limit_high)
        self._cfg["Horizontal Inverted"] = str(self.horizontal_inverted)
        self._cfg["Horizontal Units"] = str(self.horizontal_units)
        self._cfg["Horizontal Origin"] = str(self.horizontal_origin)
        self._cfg["Horizontal Limit Low"] = str(self.horizontal_limit_low)
        self._cfg["Horizontal Limit High"] = str(self.horizontal_limit_high)
        self._cfg["Camera Inverted"] = str(self.camera_inverted)
        self._cfg["Camera Units"] = str(self.camera_units)
        self._cfg["Camera Origin"] = str(self.camera_origin)
        self._cfg["Camera Limit Low"] = str(self.camera_limit_low)
        self._cfg["Camera Limit High"] = str(self.camera_limit_high)
        self._cfg = cfg_write(self._cfg_filename, self._cfg_section, self._cfg)

    def get_properties(self) -> dict[str, str]:
        motors_properties = {}
        motors_properties.update({"vertical name": self.vertical.get_name()})  # ty: ignore[unresolved-attribute]
        motors_properties.update({"horizontal name": self.horizontal.get_name()})  # ty: ignore[unresolved-attribute]
        motors_properties.update({"camera name": self.camera.get_name()})  # ty: ignore[unresolved-attribute]
        return motors_properties  # ty: ignore[unsound-return-statement]

    def get_positions(self) -> dict[str, float]:
        motors_positions = {}
        motors_positions.update({"vertical position": self.vertical.get_position("mm")})  # ty: ignore[unresolved-attribute]
        motors_positions.update(
            {"horizontal position": self.horizontal.get_position("mm")}  # ty: ignore[unresolved-attribute]
        )
        motors_positions.update({"camera position": self.camera.get_position("mm")})  # ty: ignore[unresolved-attribute]
        return motors_positions  # ty: ignore[unsound-return-statement]

    def close(self) -> None:
        """Close the shared serial handle. Called on app shutdown."""
        if self._serial is not None and self._serial.is_open:
            self._serial.close()

    def move_axes_parallel(self, moves: list[tuple[str, float, str]]) -> None:
        """Move multiple axes on the shared serial bus.

        Validates ALL targets against travel limits BEFORE any serial bytes
        are written. Raises ``ValueError`` if ANY axis is over-travel. Commands
        are sent back-to-back, then one 6-byte reply is read per command in
        send order.
        """
        # Pass 1: validate ALL targets before any serial byte is written.
        validated: list[tuple[ZaberMotor, int]] = []
        for axis_name, position, units in moves:
            motor = getattr(self, axis_name)
            target_microsteps = motor.position_to_microsteps(position, units)
            if target_microsteps < motor.limit_low_microsteps:
                raise ValueError(
                    f"{axis_name} target {position} {units}"
                    " is below the low travel limit"
                )
            if target_microsteps > motor.limit_high_microsteps:
                raise ValueError(
                    f"{axis_name} target {position} {units}"
                    " exceeds the high travel limit"
                )
            validated.append((motor, target_microsteps))

        # The shared serial handle is locked for the whole command/response
        # sequence. Move commands only reply once each stage reaches the
        # target, so the read timeout is extended to 60 s.
        io_lock = getattr(self, "_io_lock", None)
        if io_lock is None:
            io_lock = threading.RLock()
            self._io_lock = io_lock

        original_timeout = self._serial.timeout
        with io_lock:
            try:
                self._serial.timeout = 60.0
                # Pass 2: send all commands back-to-back on the shared handle.
                self._serial.reset_input_buffer()
                self._serial.reset_output_buffer()
                for motor, target_microsteps in validated:
                    instruction = motor._encode_instruction(20, target_microsteps)
                    self._serial.write(bytes(instruction))

                # Pass 3: read one 6-byte reply per command, in send order.
                for motor, _ in validated:
                    reply = self._serial.read(6)
                    motor._parse_reply(reply, 20)
            finally:
                if original_timeout is not None:
                    self._serial.timeout = original_timeout


class ZaberMotor(IMotor):
    """Class for Zaber's T-LS series linear stage motor control"""

    def __init__(
        self,
        shared_serial: serial.Serial,
        device_number: int,
        io_lock = None,
    ) -> None:
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

        # Shared serial handle for the lifetime of the Zaber chain.
        # In production this is the Motors bundle handle; in isolated
        # unit tests the __new__ bypass may leave this None and the
        # legacy per-call open fallback is used.
        self._serial = shared_serial
        # Tests that bypass __init__ will fall back to a private RLock;
        # production uses the shared Motors bundle lock.
        self._io_lock = io_lock if io_lock is not None else threading.RLock()
        self.port = ""
        self.device_number = device_number
        self.ask_id()

    def _encode_instruction(self, cmd_no: int, cmd_param: int) -> list[int]:
        """Build the 6-byte Zaber binary instruction from cmd_no and cmd_param."""
        if cmd_param < 0:
            cmd_param = pow(256, 4) + cmd_param
        byte_6 = int(cmd_param // pow(256, 3))
        cmd_param = cmd_param % pow(256, 3)
        byte_5 = int(cmd_param // pow(256, 2))
        cmd_param = cmd_param % pow(256, 2)
        byte_4 = int(cmd_param // pow(256, 1))
        cmd_param = cmd_param % pow(256, 1)
        byte_3 = int(cmd_param // pow(256, 0))
        return [
            int(self.device_number),
            int(cmd_no),
            byte_3,
            byte_4,
            byte_5,
            byte_6,
        ]

    def _parse_reply(self, reply_bytes: bytes, cmd_no: int) -> int:
        """Parse a 6-byte Zaber reply and update error state."""
        reply_data = 0
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

    def _motorIO(self, cmd_no: int, cmd_param: int) -> int:
        # Default return
        reply_data = 0

        instruction = self._encode_instruction(cmd_no, cmd_param)

        # Move commands (home, move-to-stored, absolute/relative/constant, stop)
        # do not reply until the physical stage has finished moving. The real
        # serial timeout must be long enough to wait for that reply.
        _MOVE_COMMANDS = frozenset({1, 18, 20, 21, 22, 23})
        is_move = cmd_no in _MOVE_COMMANDS
        original_timeout = None

        # Tests may create a ZaberMotor directly via __new__ without a shared
        # Motors lock. Fallback to a private RLock in that case.
        io_lock = getattr(self, "_io_lock", None)
        if io_lock is None:
            io_lock = threading.RLock()
            self._io_lock = io_lock

        with io_lock:
            try:
                if is_move:
                    # Save and extend pyserial read timeout for the duration of
                    # the motion. Restored in the finally block.
                    original_timeout = self._serial.timeout
                    self._serial.timeout = 60.0
                # All real Zaber I/O uses the shared serial handle injected by
                # Motors.__init__. Mac tests inject a Mock serial via the __new__
                # bypass to exercise every branch without hardware.
                self._serial.reset_input_buffer()
                self._serial.reset_output_buffer()
                # Write instruction bytes to motor
                self._serial.write(bytes(instruction))
                # Read 6-bytes reply
                reply_bytes = self._serial.read(6)
            except Exception:  # pragma: no branch
                # Mac tests run with a Mock serial; this except path is exercised
                # when the injected serial raises (transient error simulation).
                self.error = 1
                self.error_message = "Serial port error"
                logger.exception("Serial port error!")
            else:
                reply_data = self._parse_reply(reply_bytes, cmd_no)
            finally:
                if is_move and original_timeout is not None:
                    self._serial.timeout = original_timeout
        return reply_data

    def ask_id(self) -> int:
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

    def set_units(self, units: str) -> None:
        self.units = units

    def set_inverted(self, inverted: bool) -> None:
        self.inverted = inverted

    def set_limit_low(self, position: float, units: str) -> None:
        self.limit_low_microsteps = self.position_to_microsteps(position, units)

    def set_limit_high(self, position: float, units: str) -> None:
        self.limit_high_microsteps = self.position_to_microsteps(position, units)

    def set_origin(self, position: float, units: str) -> None:
        self.origin_microsteps = self.position_to_microsteps(position, units)

    def get_units(self) -> str:
        return self.units

    def get_inverted(self) -> bool:
        return self.inverted

    def get_limit_low(self, units: str) -> float:
        limit_low_units = self.microsteps_to_position(self.limit_low_microsteps, units)
        return limit_low_units

    def get_limit_high(self, units: str) -> float:
        limit_high_units = self.microsteps_to_position(
            self.limit_high_microsteps, units
        )
        return limit_high_units

    def get_origin(self, units: str) -> float:
        origin_units = self.microsteps_to_position(self.origin_microsteps, units)
        return origin_units

    def get_name(self) -> str:
        return self.name

    def get_position(self, units: str) -> float:
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

    def move_home(self) -> None:
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

    def move_absolute_position(self, absolute_position: float, units: str) -> None:
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

    def move_relative_position(self, relative_position: float, units: str) -> None:
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

    def microsteps_to_position(self, microsteps: int, units: str = "mm") -> float:
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
        else:
            # Unknown unit — fall back to factor=0 so the downstream
            # `factor > 0` guard yields 0 rather than UnboundLocalError.
            # Matches MockMotor.microsteps_to_position (mock-vs-real parity).
            factor = 0

        if self.microstep_size > 0 and factor > 0:
            position = microsteps * self.microstep_size * pow(10, -6) / factor
        else:
            position = 0

        return position

    def position_to_microsteps(self, position: float, units: str = "mm") -> int:
        """Converts position into microsteps

        Parameters:
            position: Numerical value of the position
            unit: A string which specifies the unit of the numerical position.
                  Options: 'm', 'cm', 'mm', '\u03bcm' (micrometers),
                  '\u03bcStep' (microsteps)

        Returns:
            int: microsteps, truncated toward zero. The truncation matches the
            Zaber T-LS ``_motorIO`` byte-packing, which packs the integer part
            of the command parameter into the serial frame (``int(cmd_param //
            pow(256,3))`` etc.) — floor division on a non-negative microstep
            count is equivalent to truncation toward zero here. Using ``int()``
            rather than ``//`` preserves this behavior for any negative
            position a caller might pass (floor would shift by one microstep,
            a hardware risk near a travel limit). Rig-verify at end-of-milestone
            that the rounding only matters for sub-microstep positions near a
            limit boundary.
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
        else:
            # Unknown unit — fall back to factor=0 so the downstream
            # `factor > 0` guard yields 0 rather than UnboundLocalError.
            # Matches MockMotor.position_to_microsteps (mock-vs-real parity).
            factor = 0

        if self.microstep_size > 0 and factor > 0:
            microsteps = position * factor / (self.microstep_size * pow(10, -6))
        else:
            microsteps = 0

        return int(microsteps)
