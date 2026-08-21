'''
Unit tests for src/motors.py — Zaber travel-limit enforcement.

ZaberMotor.__init__ opens a real serial port via ask_id(), which fails on
this Mac (no Zaber stage). To exercise the limit-check logic in isolation
we bypass __init__ with __new__ and populate the attributes the limit
checks read (id, microstep_size, limit_low_microsteps, limit_high_microsteps,
error, port, device_number). The fixture mirrors the T-LSM050A vertical
motor documented in ask_id()'s docstring.
'''

import pytest

from src.motors import ZaberMotor


def _make_motor():
    '''Build a ZaberMotor-like instance without running __init__'s serial
    hardware probe. Attributes match a T-LSM050A (id 6210).'''
    motor = ZaberMotor.__new__(ZaberMotor)
    motor.id = 6210
    motor.name = "T-LSM050A"
    motor.microstep_size = 0.047625
    motor.microsteps_max = 1066666
    motor.units = 'mm'
    motor.inverted = False
    motor.homed = False
    motor.limit_low_microsteps = 0
    motor.limit_high_microsteps = 1066666
    motor.origin_microsteps = 0
    motor.error = 0
    motor.error_message = ""
    motor.port = 'COM3'
    motor.device_number = 1
    return motor


def test_move_absolute_rejects_over_high_limit():
    '''An absolute move past the high travel limit must raise ValueError
    before any serial command is sent — protecting the objective/sample.'''
    motor = _make_motor()
    # 999 mm is far beyond the ~50.8 mm travel of a T-LSM050A
    with pytest.raises(ValueError):
        motor.move_absolute_position(999, 'mm')


def test_move_absolute_accepts_within_limits():
    '''An absolute move within the travel range must not raise ValueError.
    The serial call itself will fail silently on Mac (no port), setting
    self.error — that is expected and not asserted here.'''
    motor = _make_motor()
    # 5 mm is well within the 0..~50.8 mm range
    try:
        motor.move_absolute_position(5, 'mm')
    except ValueError:
        pytest.fail("move_absolute_position raised ValueError for an in-range move")


def test_move_absolute_rejects_below_low_limit():
    '''An absolute move below the low travel limit must raise ValueError.'''
    motor = _make_motor()
    with pytest.raises(ValueError):
        motor.move_absolute_position(-1, 'mm')


def test_move_relative_rejects_resulting_position_over_limit():
    '''A relative move whose RESULTING position would exceed the high limit
    must raise ValueError. The check validates the resulting position, not
    the raw delta — a small delta near the top of travel is still rejected.'''
    motor = _make_motor()
    # Patch _motorIO so the position query (cmd 60) reports a position near
    # the high limit, and the subsequent move (cmd 21) is never reached
    # because the limit check raises first.
    near_high = motor.limit_high_microsteps - 1000  # ~50.79 mm in microsteps

    def fake_motorIO(cmd_no, cmd_param):
        # cmd 60 = get position; return a near-the-top position
        if cmd_no == 60:
            motor.error = 0
            return near_high
        # Any other command (e.g. cmd 21 = move relative) means the limit
        # check did not fire — record it so the test fails clearly.
        raise AssertionError(
            "move_relative_position sent cmd %s to the stage before the "
            "limit check rejected the over-travel resulting position" % cmd_no)

    motor._motorIO = fake_motorIO
    # A +5 mm delta from near the top would push the resulting position
    # well past limit_high_microsteps.
    with pytest.raises(ValueError):
        motor.move_relative_position(5, 'mm')


def test_move_maximum_position_removed():
    '''move_maximum_position is confirmed dead code (no GUI caller) and
    must be deleted from the ZaberMotor class.'''
    assert hasattr(ZaberMotor, 'move_maximum_position') is False
