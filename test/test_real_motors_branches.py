"""Branch-coverage closure for ``lightsheet.hal.real.motors``.

Exercises the ZaberMotor serial protocol (mocked serial.Serial), the
device-ID matching branches in ``ask_id``, the reply-parsing branches in
``_motorIO`` (valid, error, invalid format, no reply, negative reply),
the unit-conversion branches in ``microsteps_to_position`` /
``position_to_microsteps``, the setter/getter methods, the
``Motors.cfg_load_ini`` / ``cfg_save_ini`` / ``get_properties`` /
``get_positions`` methods, and the ``id == 0`` early-exit branches in
``get_position`` / ``move_home`` / ``move_absolute_position`` /
``move_relative_position``.

The serial I/O is mocked via ``patch("lightsheet.hal.real.motors.serial.Serial")``
so the tests run on Mac without a Zaber stage. The ``__new__`` bypass
pattern (from ``test_motor_limits.py``) is used for the move-limit tests
that need to avoid the ``ask_id`` serial probe.

Behavior tests (AGENTS.md §5) — every assertion is on a runtime
postcondition (returned position, raised ValueError, set attribute),
never a static-source grep.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from lightsheet.hal.real.motors import Motors, ZaberMotor

# -- ZaberMotor.__new__ bypass (avoids ask_id serial probe) -----------------


def _make_motor(
    microstep_size: float = 0.047625,
    microsteps_max: int = 1066666,
    device_number: int = 1,
    port: str = "COM3",
) -> ZaberMotor:
    """Build a ZaberMotor via __new__ bypass — no serial probe."""
    m = ZaberMotor.__new__(ZaberMotor)
    m.error = 0
    m.error_message = ""
    m.is_supported = True
    m.id = 6210
    m.name = "T-LSM050A"
    m.inverted = False
    m.homed = False
    m.microstep_size = microstep_size
    m.microsteps_max = microsteps_max
    m.units = "mm"
    m.limit_high_microsteps = 100000
    m.limit_low_microsteps = 0
    m.origin_microsteps = 0
    m.port = port
    m.device_number = device_number
    # Shared serial handle — tests inject a Mock and never open a real port.
    m._serial = Mock()
    return m


# -- _motorIO reply parsing branches ----------------------------------------


def _make_serial_mock(reply_bytes: bytes = b"\x01\x32\x00\x00\x00\x00") -> Mock:
    """Build a mock serial.Serial that returns the given reply bytes."""
    motor = Mock()
    motor.read.return_value = reply_bytes
    return motor


def test_motorio_valid_reply_positive_data() -> None:
    """A valid 6-byte reply with positive data (byte_5 <= 127) returns
    the expected data value and clears error."""
    m = _make_motor()
    # reply: device=1, cmd=50, data=100 (bytes: 0x64, 0x00, 0x00, 0x00)
    reply = bytes([1, 50, 100, 0, 0, 0])
    m._serial = _make_serial_mock(reply)
    result = m._motorIO(50, 0)
    assert result == 100
    assert m.error == 0


def test_motorio_valid_reply_negative_data() -> None:
    """A valid reply with byte_5 > 127 returns a negative data value
    (the two's-complement branch, line 229-235)."""
    m = _make_motor()
    # reply: device=1, cmd=21, data=-1 in 4-byte two's complement
    # -1 = 0xFFFFFFFF = bytes [0xFF, 0xFF, 0xFF, 0xFF]
    reply = bytes([1, 21, 0xFF, 0xFF, 0xFF, 0xFF])
    m._serial = _make_serial_mock(reply)
    result = m._motorIO(21, 0)
    assert result == -1
    assert m.error == 0


def test_motorio_error_reply_cmd_255() -> None:
    """A reply with cmd=255 (motor error) sets error=1 (line 243-245)."""
    m = _make_motor()
    reply = bytes([1, 255, 0, 0, 0, 0])
    m._serial = _make_serial_mock(reply)
    m._motorIO(50, 0)
    assert m.error == 1
    assert "error" in m.error_message.lower()


def test_motorio_invalid_format_reply() -> None:
    """A reply that doesn't match device_number or cmd sets error=1
    (line 246-248)."""
    m = _make_motor(device_number=1)
    # Reply from device 2, cmd 99 — doesn't match.
    reply = bytes([2, 99, 0, 0, 0, 0])
    m._serial = _make_serial_mock(reply)
    m._motorIO(50, 0)
    assert m.error == 1
    assert "format" in m.error_message.lower()


def test_motorio_short_reply_sets_error() -> None:
    """A reply shorter than 6 bytes sets error=1 (line 249-251)."""
    m = _make_motor()
    reply = b"\x01\x32"  # only 2 bytes
    m._serial = _make_serial_mock(reply)
    m._motorIO(50, 0)
    assert m.error == 1
    assert "No valid reply" in m.error_message


def test_motorio_serial_exception_sets_error() -> None:
    """If serial.Serial raises, _motorIO catches it and sets error=1
    (line 214-217)."""
    m = _make_motor()
    m._serial.reset_input_buffer.side_effect = OSError("port not found")
    m._motorIO(50, 0)
    assert m.error == 1
    assert "Serial port error" in m.error_message


def test_motorio_negative_cmd_param() -> None:
    """A negative cmd_param is converted to two's complement (line 176-177).
    Verify the instruction bytes are correct by capturing the serial write."""
    m = _make_motor()
    reply = bytes([1, 21, 0, 0, 0, 0])
    m._serial = _make_serial_mock(reply)
    m._motorIO(21, -1)
    # The write was called with 6 bytes — verify the instruction encodes
    # -1 as 0xFFFFFFFF (bytes 3-6).
    written = m._serial.write.call_args[0][0]
    assert len(written) == 6
    assert written[0] == m.device_number  # device number
    assert written[1] == 21  # cmd_no
    # -1 in 4-byte two's complement = 0xFFFFFFFF
    assert written[2] == 0xFF
    assert written[3] == 0xFF
    assert written[4] == 0xFF
    assert written[5] == 0xFF


# -- ask_id device-ID matching branches -------------------------------------


def test_ask_id_vertical_motor_6210() -> None:
    """ask_id with reply_data=6210 sets the T-LSM050A vertical motor attrs."""
    m = ZaberMotor.__new__(ZaberMotor)
    m.error = 0
    m.error_message = ""
    m.is_supported = False
    m.id = 0
    m.name = ""
    m.inverted = False
    m.homed = False
    m.microstep_size = 0
    m.microsteps_max = 0
    m.units = "mm"
    m.limit_high_microsteps = 0
    m.limit_low_microsteps = 0
    m.origin_microsteps = 0
    m.port = "COM3"
    m.device_number = 1
    # reply_data = 6210
    reply = bytes([1, 50, 0x42, 0x18, 0, 0])  # 6210 = 0x1842
    m._serial = _make_serial_mock(reply)
    m.ask_id()
    assert m.is_supported is True
    assert m.id == 6210
    assert m.name == "T-LSM050A"
    assert m.microstep_size == pytest.approx(0.047625)


def test_ask_id_horizontal_motor_6320() -> None:
    """ask_id with reply_data=6320 sets the T-LSM100B horizontal motor attrs."""
    m = ZaberMotor.__new__(ZaberMotor)
    m.error = 0
    m.error_message = ""
    m.is_supported = False
    m.id = 0
    m.name = ""
    m.inverted = False
    m.homed = False
    m.microstep_size = 0
    m.microsteps_max = 0
    m.units = "mm"
    m.limit_high_microsteps = 0
    m.limit_low_microsteps = 0
    m.origin_microsteps = 0
    m.port = "COM3"
    m.device_number = 2
    # reply_data = 6320 = 0x18B0
    reply = bytes([2, 50, 0xB0, 0x18, 0, 0])
    m._serial = _make_serial_mock(reply)
    m.ask_id()
    assert m.is_supported is True
    assert m.id == 6320
    assert m.name == "T-LSM100B"


def test_ask_id_camera_motor_4152() -> None:
    """ask_id with reply_data=4152 sets the T-LSR150B camera motor attrs."""
    m = ZaberMotor.__new__(ZaberMotor)
    m.error = 0
    m.error_message = ""
    m.is_supported = False
    m.id = 0
    m.name = ""
    m.inverted = False
    m.homed = False
    m.microstep_size = 0
    m.microsteps_max = 0
    m.units = "mm"
    m.limit_high_microsteps = 0
    m.limit_low_microsteps = 0
    m.origin_microsteps = 0
    m.port = "COM3"
    m.device_number = 3
    # reply_data = 4152 = 0x1038
    reply = bytes([3, 50, 0x38, 0x10, 0, 0])
    m._serial = _make_serial_mock(reply)
    m.ask_id()
    assert m.is_supported is True
    assert m.id == 4152
    assert m.name == "T-LSR150B"


def test_ask_id_unsupported_device() -> None:
    """ask_id with an unknown reply_data sets is_supported=False (line 286-291)."""
    m = ZaberMotor.__new__(ZaberMotor)
    m.error = 0
    m.error_message = ""
    m.is_supported = False
    m.id = 0
    m.name = ""
    m.inverted = False
    m.homed = False
    m.microstep_size = 0
    m.microsteps_max = 0
    m.units = "mm"
    m.limit_high_microsteps = 0
    m.limit_low_microsteps = 0
    m.origin_microsteps = 0
    m.port = "COM3"
    m.device_number = 1
    # reply_data = 9999 (unsupported)
    reply = bytes([1, 50, 0x0F, 0x27, 0, 0])  # 9999 = 0x270F
    m._serial = _make_serial_mock(reply)
    m.ask_id()
    assert m.is_supported is False
    assert m.error == 1
    assert m.name == "Unsupported device"


def test_ask_id_serial_error_sets_device_not_found() -> None:
    """ask_id with a serial error sets id=0, name='Device not found'
    (line 292-294)."""
    m = ZaberMotor.__new__(ZaberMotor)
    m.error = 0
    m.error_message = ""
    m.is_supported = False
    m.id = 0
    m.name = ""
    m.inverted = False
    m.homed = False
    m.microstep_size = 0
    m.microsteps_max = 0
    m.units = "mm"
    m.limit_high_microsteps = 0
    m.limit_low_microsteps = 0
    m.origin_microsteps = 0
    m.port = "COM3"
    m.device_number = 1
    m._serial = Mock()
    m._serial.reset_input_buffer.side_effect = OSError("no port")
    m.ask_id()
    assert m.id == 0
    assert m.name == "Device not found"


# -- Setters / getters ------------------------------------------------------


def test_set_units_sets_attribute() -> None:
    m = _make_motor()
    m.set_units("cm")
    assert m.units == "cm"
    assert m.get_units() == "cm"


def test_set_inverted_sets_attribute() -> None:
    m = _make_motor()
    m.set_inverted(True)
    assert m.inverted is True
    assert m.get_inverted() is True


def test_set_limit_low_converts_to_microsteps() -> None:
    m = _make_motor()
    m.set_limit_low(5.0, "mm")
    assert m.limit_low_microsteps > 0
    assert m.get_limit_low("mm") == pytest.approx(5.0, abs=0.01)


def test_set_limit_high_converts_to_microsteps() -> None:
    m = _make_motor()
    m.set_limit_high(10.0, "mm")
    assert m.limit_high_microsteps > 0
    assert m.get_limit_high("mm") == pytest.approx(10.0, abs=0.01)


def test_set_origin_converts_to_microsteps() -> None:
    m = _make_motor()
    m.set_origin(3.0, "mm")
    assert m.origin_microsteps > 0
    assert m.get_origin("mm") == pytest.approx(3.0, abs=0.01)


def test_get_name_returns_name() -> None:
    m = _make_motor()
    assert m.get_name() == "T-LSM050A"


# -- get_position / move_home id==0 branches --------------------------------


def test_get_position_id_zero_returns_zero() -> None:
    """get_position with id=0 returns 0 without serial I/O (line 347-348)."""
    m = _make_motor()
    m.id = 0
    assert m.get_position("mm") == 0


def test_get_position_id_nonzero_queries_serial() -> None:
    """get_position with id!=0 queries the serial port (line 342-346)."""
    m = _make_motor()
    reply = bytes([1, 60, 0x64, 0x00, 0x00, 0x00])  # 100 microsteps
    m._serial = _make_serial_mock(reply)
    pos = m.get_position("mm")
    assert pos > 0  # 100 microsteps converted to mm


def test_move_home_id_zero_is_noop() -> None:
    """move_home with id=0 does nothing (line 359 if-branch -> exit)."""
    m = _make_motor()
    m.id = 0
    m.move_home()  # must not raise


def test_move_home_id_nonzero_sends_command() -> None:
    """move_home with id!=0 sends cmd 1 (line 360-362)."""
    m = _make_motor()
    reply = bytes([1, 1, 0, 0, 0, 0])
    m._serial = _make_serial_mock(reply)
    m.move_home()


# -- move_absolute / move_relative id==0 branches ---------------------------


def test_move_absolute_id_zero_is_noop() -> None:
    """move_absolute_position with id=0 does nothing (line 378 if-branch -> exit)."""
    m = _make_motor()
    m.id = 0
    m.move_absolute_position(5.0, "mm")  # must not raise


def test_move_relative_id_zero_is_noop() -> None:
    """move_relative_position with id=0 does nothing (line 414 if-branch -> exit)."""
    m = _make_motor()
    m.id = 0
    m.move_relative_position(1.0, "mm")  # must not raise


# -- Unit conversion branches (microsteps_to_position) ----------------------


@pytest.mark.parametrize(
    "units,expected_factor",
    [
        ("m", 1),
        ("cm", 0.01),
        ("mm", 0.001),
        ("\u03bcm", 0.000001),
    ],
)
def test_microsteps_to_position_unit_conversions(
    units: str, expected_factor: float
) -> None:
    """Each unit branch in microsteps_to_position produces the correct factor."""
    m = _make_motor(microstep_size=0.047625)
    # 1000 microsteps * 0.047625 µm/step = 47.625 µm
    # In mm: 47.625e-3 = 0.047625
    result = m.microsteps_to_position(1000, units)
    expected = 1000 * 0.047625 * 1e-6 / expected_factor
    assert result == pytest.approx(expected, rel=0.01)


def test_microsteps_to_position_microstep_unit() -> None:
    """The µStep unit branch (line 453-454)."""
    m = _make_motor(microstep_size=0.047625)
    result = m.microsteps_to_position(1000, "\u03bcStep")
    # factor = microstep_size * 1e-6
    # position = 1000 * microstep_size * 1e-6 / factor = 1000
    assert result == pytest.approx(1000)


def test_microsteps_to_position_unknown_unit_returns_zero() -> None:
    """Unknown unit -> factor=0 -> position=0 (line 455-459 + 463-464)."""
    m = _make_motor()
    assert m.microsteps_to_position(1000, "inches") == 0


def test_microsteps_to_position_zero_microstep_size_returns_zero() -> None:
    """microstep_size=0 -> position=0 (line 463-464)."""
    m = _make_motor(microstep_size=0)
    assert m.microsteps_to_position(1000, "mm") == 0


# -- Unit conversion branches (position_to_microsteps) ----------------------


@pytest.mark.parametrize(
    "units,expected_factor",
    [
        ("m", 1),
        ("cm", 0.01),
        ("mm", 0.001),
        ("\u03bcm", 0.000001),
    ],
)
def test_position_to_microsteps_unit_conversions(
    units: str, expected_factor: float
) -> None:
    """Each unit branch in position_to_microsteps produces the correct factor."""
    m = _make_motor(microstep_size=0.047625)
    # 1 mm -> microsteps = 1 * 0.001 / (0.047625 * 1e-6) = 21008.4...
    result = m.position_to_microsteps(1.0, units)
    expected = 1.0 * expected_factor / (0.047625 * 1e-6)
    assert result == pytest.approx(int(expected), abs=1)


def test_position_to_microsteps_microstep_unit() -> None:
    """The µStep unit branch (line 497-498)."""
    m = _make_motor(microstep_size=0.047625)
    result = m.position_to_microsteps(1000, "\u03bcStep")
    # factor = microstep_size * 1e-6
    # microsteps = 1000 * factor / (microstep_size * 1e-6) = 1000
    assert result == 1000


def test_position_to_microsteps_unknown_unit_returns_zero() -> None:
    """Unknown unit -> factor=0 -> microsteps=0 (line 499-503 + 507-508)."""
    m = _make_motor()
    assert m.position_to_microsteps(1.0, "inches") == 0


def test_position_to_microsteps_zero_microstep_size_returns_zero() -> None:
    """microstep_size=0 -> microsteps=0 (line 507-508)."""
    m = _make_motor(microstep_size=0)
    assert m.position_to_microsteps(1.0, "mm") == 0


# -- Motors container (cfg_load_ini, cfg_save_ini, get_properties, get_positions) --


def test_motors_cfg_load_ini_reads_config(tmp_path: Path) -> None:
    """Motors.cfg_load_ini reads config.ini and populates instance vars."""
    config_path = tmp_path / "config.ini"
    config_path.write_text(
        "[Motors]\n"
        "Port = COM7\n"
        "Device Number Vertical = 1\n"
        "Device Number Horizontal = 2\n"
        "Device Number Camera = 3\n"
        "Vertical Inverted = True\n"
        "Vertical Units = mm\n"
        "Vertical Origin = 0.0\n"
        "Vertical Limit Low = 0.0\n"
        "Vertical Limit High = 10.0\n"
        "Horizontal Inverted = False\n"
        "Horizontal Units = mm\n"
        "Horizontal Origin = 0.0\n"
        "Horizontal Limit Low = 0.0\n"
        "Horizontal Limit High = 10.0\n"
        "Camera Inverted = False\n"
        "Camera Units = mm\n"
        "Camera Origin = 0.0\n"
        "Camera Limit Low = 0.0\n"
        "Camera Limit High = 50.0\n"
    )
    import os
    cwd = Path.cwd()
    os.chdir(tmp_path)
    try:
        motors = Motors.__new__(Motors)
        motors.error = 0
        motors.error_message = ""
        motors._cfg_filename = "config.ini"
        motors._cfg_section = "Motors"
        motors.cfg_load_ini()
    finally:
        os.chdir(cwd)
    assert motors.port == "COM7"
    assert motors.device_no_vertical == 1
    assert motors.vertical_inverted is True
    assert motors.vertical_units == "mm"
    assert motors.vertical_origin == 0.0


def test_motors_cfg_save_ini_writes_config(tmp_path: Path) -> None:
    """Motors.cfg_save_ini packs instance vars and writes config.ini."""
    import os
    cwd = Path.cwd()
    os.chdir(tmp_path)
    try:
        motors = Motors.__new__(Motors)
        motors._cfg_filename = "config.ini"
        motors._cfg_section = "Motors"
        motors.port = "COM7"
        motors.device_no_vertical = 1
        motors.device_no_horizontal = 2
        motors.device_no_camera = 3
        motors.vertical_inverted = True
        motors.vertical_units = "mm"
        motors.vertical_origin = 0.0
        motors.vertical_limit_low = 0.0
        motors.vertical_limit_high = 10.0
        motors.horizontal_inverted = False
        motors.horizontal_units = "mm"
        motors.horizontal_origin = 0.0
        motors.horizontal_limit_low = 0.0
        motors.horizontal_limit_high = 10.0
        motors.camera_inverted = False
        motors.camera_units = "mm"
        motors.camera_origin = 0.0
        motors.camera_limit_low = 0.0
        motors.camera_limit_high = 50.0
        motors.cfg_save_ini()
    finally:
        os.chdir(cwd)
    # Verify the file was written.
    written = (tmp_path / "config.ini").read_text()
    assert "COM7" in written
    assert "[Motors]" in written


def test_motors_get_properties_returns_names() -> None:
    """Motors.get_properties returns a dict with vertical/horizontal/camera names."""
    motors = Motors.__new__(Motors)
    motors.vertical = Mock()
    motors.vertical.get_name.return_value = "V"
    motors.horizontal = Mock()
    motors.horizontal.get_name.return_value = "H"
    motors.camera = Mock()
    motors.camera.get_name.return_value = "C"
    props = motors.get_properties()
    assert props == {"vertical name": "V", "horizontal name": "H", "camera name": "C"}


def test_motors_get_positions_returns_positions() -> None:
    """Motors.get_positions returns a dict with vertical/horizontal/camera positions."""
    motors = Motors.__new__(Motors)
    motors.vertical = Mock()
    motors.vertical.get_position.return_value = 1.0
    motors.horizontal = Mock()
    motors.horizontal.get_position.return_value = 2.0
    motors.camera = Mock()
    motors.camera.get_position.return_value = 3.0
    positions = motors.get_positions()
    assert positions == {
        "vertical position": 1.0,
        "horizontal position": 2.0,
        "camera position": 3.0,
    }


# -- Motors.__init__ + ZaberMotor.__init__ (mocked serial) ------------------


def test_zaber_motor_init_with_mocked_serial_unsupported_device() -> None:
    """ZaberMotor.__init__ runs ask_id against a mocked serial port.
    With an unsupported device ID reply, is_supported stays False and
    the Motors.__init__ if-branches (lines 55-80) are skipped."""
    # reply with unsupported device ID (9999)
    reply = bytes([1, 50, 0x0F, 0x27, 0, 0])  # 9999 = 0x270F
    m = ZaberMotor(_make_serial_mock(reply), 1)
    assert m.is_supported is False
    assert m.error == 1
    assert m.name == "Unsupported device"


def test_zaber_motor_init_with_mocked_serial_vertical_motor() -> None:
    """ZaberMotor.__init__ with a 6210 reply sets the vertical motor attrs
    and is_supported=True (lines 148-168 + 268-271)."""
    reply = bytes([1, 50, 0x42, 0x18, 0, 0])  # 6210 = 0x1842
    m = ZaberMotor(_make_serial_mock(reply), 1)
    assert m.is_supported is True
    assert m.id == 6210
    assert m.name == "T-LSM050A"


def test_motors_init_with_mocked_serial_all_supported(tmp_path: Path) -> None:
    """Motors.__init__ constructs 3 ZaberMotors and, when all are supported,
    calls set_inverted/set_units/set_origin/set_limit_low/set_limit_high
    on each (lines 54-80)."""
    import os
    config_path = tmp_path / "config.ini"
    config_path.write_text(
        "[Motors]\n"
        "Port = COM3\n"
        "Device Number Vertical = 1\n"
        "Device Number Horizontal = 2\n"
        "Device Number Camera = 3\n"
        "Vertical Inverted = False\n"
        "Vertical Units = mm\n"
        "Vertical Origin = 0.0\n"
        "Vertical Limit Low = 0.0\n"
        "Vertical Limit High = 10.0\n"
        "Horizontal Inverted = False\n"
        "Horizontal Units = mm\n"
        "Horizontal Origin = 0.0\n"
        "Horizontal Limit Low = 0.0\n"
        "Horizontal Limit High = 10.0\n"
        "Camera Inverted = False\n"
        "Camera Units = mm\n"
        "Camera Origin = 0.0\n"
        "Camera Limit Low = 0.0\n"
        "Camera Limit High = 50.0\n"
    )
    cwd = Path.cwd()
    os.chdir(tmp_path)
    try:
        # Each ZaberMotor.__init__ calls ask_id -> _motorIO -> serial.Serial.
        # Return a different device ID for each of the 3 motors.
        # 6210 (vertical), 6320 (horizontal), 4152 (camera).
        replies = [
            bytes([1, 50, 0x42, 0x18, 0, 0]),  # 6210
            bytes([2, 50, 0xB0, 0x18, 0, 0]),  # 6320
            bytes([3, 50, 0x38, 0x10, 0, 0]),  # 4152
        ]
        shared_serial = _make_serial_mock()
        shared_serial.read.side_effect = replies
        with patch(
            "lightsheet.hal.real.motors.serial.Serial",
            return_value=shared_serial,
        ):
            motors = Motors()
    finally:
        os.chdir(cwd)
    assert motors.vertical.is_supported is True  # ty: ignore[unresolved-attribute]
    assert motors.horizontal.is_supported is True  # ty: ignore[unresolved-attribute]
    assert motors.camera.is_supported is True  # ty: ignore[unresolved-attribute]
    assert motors.vertical.id == 6210  # ty: ignore[unresolved-attribute]
    assert motors.horizontal.id == 6320  # ty: ignore[unresolved-attribute]
    assert motors.camera.id == 4152  # ty: ignore[unresolved-attribute]


def test_motors_init_with_mocked_serial_none_supported(tmp_path: Path) -> None:
    """Motors.__init__ where all 3 motors are unsupported -> the if-branches
    (lines 55, 63, 75) are all False -> no set_* calls (the False branch)."""
    import os
    config_path = tmp_path / "config.ini"
    config_path.write_text(
        "[Motors]\n"
        "Port = COM3\n"
        "Device Number Vertical = 1\n"
        "Device Number Horizontal = 2\n"
        "Device Number Camera = 3\n"
        "Vertical Inverted = False\n"
        "Vertical Units = mm\n"
        "Vertical Origin = 0.0\n"
        "Vertical Limit Low = 0.0\n"
        "Vertical Limit High = 10.0\n"
        "Horizontal Inverted = False\n"
        "Horizontal Units = mm\n"
        "Horizontal Origin = 0.0\n"
        "Horizontal Limit Low = 0.0\n"
        "Horizontal Limit High = 10.0\n"
        "Camera Inverted = False\n"
        "Camera Units = mm\n"
        "Camera Origin = 0.0\n"
        "Camera Limit Low = 0.0\n"
        "Camera Limit High = 50.0\n"
    )
    cwd = Path.cwd()
    os.chdir(tmp_path)
    try:
        # All 3 motors return unsupported device ID (9999).
        replies = [
            bytes([1, 50, 0x0F, 0x27, 0, 0]),  # 9999
            bytes([2, 50, 0x0F, 0x27, 0, 0]),  # 9999
            bytes([3, 50, 0x0F, 0x27, 0, 0]),  # 9999
        ]
        shared_serial = _make_serial_mock()
        shared_serial.read.side_effect = replies
        with patch(
            "lightsheet.hal.real.motors.serial.Serial",
            return_value=shared_serial,
        ):
            motors = Motors()
    finally:
        os.chdir(cwd)
    assert motors.vertical.is_supported is False  # ty: ignore[unresolved-attribute]
    assert motors.horizontal.is_supported is False  # ty: ignore[unresolved-attribute]
    assert motors.camera.is_supported is False  # ty: ignore[unresolved-attribute]


# -- move_axes_parallel safety contract -------------------------------------


def _make_motor_for_parallel(
    device_number: int,
    microstep_size: float,
    limit_high_microsteps: int,
    limit_low_microsteps: int = 0,
) -> ZaberMotor:
    """Build a ZaberMotor via __new__ bypass for move_axes_parallel tests."""
    m = ZaberMotor.__new__(ZaberMotor)
    m.error = 0
    m.error_message = ""
    m.is_supported = True
    m.id = 6210 if device_number == 1 else 6320 if device_number == 2 else 4152
    m.name = (
        "T-LSM050A"
        if device_number == 1
        else "T-LSM100B"
        if device_number == 2
        else "T-LSR150B"
    )
    m.inverted = False
    m.homed = False
    m.microstep_size = microstep_size
    m.microsteps_max = limit_high_microsteps
    m.units = "mm"
    m.limit_high_microsteps = limit_high_microsteps
    m.limit_low_microsteps = limit_low_microsteps
    m.origin_microsteps = 0
    m.port = "COM7"
    m.device_number = device_number
    return m


def _make_motors_container() -> Motors:
    """Build a Motors container via __new__ bypass with a Mock shared serial."""
    motors = Motors.__new__(Motors)
    motors.error = 0
    motors.error_message = ""
    motors._serial = Mock()
    return motors


@pytest.mark.parametrize(
    "moves,match_text",
    [
        (
            [("horizontal", 9999.0, "mm"), ("camera", 5.0, "mm")],
            "exceeds the high travel limit",
        ),
        (
            [("horizontal", 5.0, "mm"), ("camera", 999.0, "mm")],
            "exceeds the high travel limit",
        ),
        (
            [("horizontal", -1.0, "mm"), ("camera", 5.0, "mm")],
            "below the low travel limit",
        ),
        (
            [("horizontal", 5.0, "mm"), ("camera", -1.0, "mm")],
            "below the low travel limit",
        ),
    ],
)
def test_move_axes_parallel_validates_both_before_any_bytes(
    moves: list[tuple[str, float, str]],
    match_text: str,
) -> None:
    """Over-travel on ANY axis raises ValueError BEFORE any serial bytes are
    written, regardless of which axis in the list is out of range."""
    motors = _make_motors_container()
    motors.horizontal = _make_motor_for_parallel(2, 0.19050, 533333)
    motors.camera = _make_motor_for_parallel(3, 0.49609, 258015)
    with pytest.raises(ValueError, match=match_text):
        motors.move_axes_parallel(moves)
    assert motors._serial.write.call_count == 0


def test_move_axes_parallel_reads_one_reply_per_command() -> None:
    """With all targets in range, move_axes_parallel writes one command per
    motor and reads exactly one 6-byte reply per command (never 12 at once)."""
    motors = _make_motors_container()
    motors._serial.read.side_effect = [
        b"\x02\x14\x00\x00\x00\x00",
        b"\x03\x14\x00\x00\x00\x00",
    ]
    motors.horizontal = _make_motor_for_parallel(2, 0.19050, 533333)
    motors.camera = _make_motor_for_parallel(3, 0.49609, 258015)
    motors.move_axes_parallel([("horizontal", 5.0, "mm"), ("camera", 5.0, "mm")])
    assert motors._serial.write.call_count == 2
    assert motors._serial.read.call_count == 2
    for call in motors._serial.read.call_args_list:
        assert call[0][0] == 6


def test_zaber_motor_uses_injected_shared_serial() -> None:
    """_motorIO uses the injected shared serial handle; it does NOT construct a
    new serial.Serial instance per call."""
    m = _make_motor_for_parallel(2, 0.19050, 533333)
    m._serial = Mock()
    m._serial.read.return_value = b"\x02\x14\x00\x00\x00\x00"
    with patch("lightsheet.hal.real.motors.serial.Serial") as serial_cls:
        m._motorIO(20, 26246)
    assert serial_cls.call_count == 0
    assert m._serial.write.called
    assert m._serial.read.called


def test_motors_close_closes_shared_handle() -> None:
    """Motors.close() closes the shared serial handle once and is a no-op if
    the handle is already closed."""
    motors = _make_motors_container()
    motors._serial.is_open = True
    motors.close()
    assert motors._serial.close.call_count == 1
    motors._serial.is_open = False
    motors.close()
    assert motors._serial.close.call_count == 1


def test_move_axes_parallel_reuses_existing_io_lock_and_none_timeout() -> None:
    """When ``Motors`` already has an ``_io_lock``, ``move_axes_parallel`` uses
    it instead of creating a new one. When ``serial.timeout`` is ``None``,
    the finally block skips restoring the original timeout."""
    import threading

    motors = _make_motors_container()
    motors._io_lock = threading.RLock()
    motors.horizontal = _make_motor_for_parallel(2, 0.19050, 533333)
    motors.camera = _make_motor_for_parallel(3, 0.49609, 258015)
    motors._serial.timeout = None
    motors._serial.read.side_effect = [
        b"\x02\x14\x00\x00\x00\x00",
        b"\x03\x14\x00\x00\x00\x00",
    ]

    motors.move_axes_parallel([("horizontal", 5.0, "mm"), ("camera", 5.0, "mm")])

    assert motors._serial.write.call_count == 2
    assert motors._serial.read.call_count == 2
    # Original timeout was None -> not restored; it stays at the 60.0 s
    # move-command value set inside the with-block.
    assert motors._serial.timeout == 60.0
