"""
Unit tests for src/motors.py — Zaber travel-limit enforcement.

ZaberMotor.__init__ opens a real serial port via ask_id(), which fails on
this Mac (no Zaber stage). To exercise the limit-check logic in isolation
we bypass __init__ with __new__ and populate the attributes the limit
checks read (id, microstep_size, limit_low_microsteps, limit_high_microsteps,
error, port, device_number). The fixture mirrors the T-LSM050A vertical
motor documented in ask_id()'s docstring.
"""

import pytest

from lightsheet.hal.real.motors import ZaberMotor


def _make_motor() -> ZaberMotor:
    """Build a ZaberMotor-like instance without running __init__'s serial
    hardware probe. Attributes match a T-LSM050A (id 6210)."""
    motor = ZaberMotor.__new__(ZaberMotor)
    motor.id = 6210
    motor.name = "T-LSM050A"
    motor.microstep_size = 0.047625
    motor.microsteps_max = 1066666
    motor.units = "mm"
    motor.inverted = False
    motor.homed = False
    motor.limit_low_microsteps = 0
    motor.limit_high_microsteps = 1066666
    motor.origin_microsteps = 0
    motor.error = 0
    motor.error_message = ""
    motor.port = "COM3"
    motor.device_number = 1
    return motor


def test_move_absolute_rejects_over_high_limit() -> None:
    """An absolute move past the high travel limit must raise ValueError
    before any serial command is sent — protecting the objective/sample."""
    motor = _make_motor()
    # 999 mm is far beyond the ~50.8 mm travel of a T-LSM050A
    with pytest.raises(ValueError):
        motor.move_absolute_position(999, "mm")


def test_move_absolute_accepts_within_limits() -> None:
    """An absolute move within the travel range must not raise ValueError.
    The serial call itself will fail silently on Mac (no port), setting
    self.error — that is expected and not asserted here."""
    motor = _make_motor()
    # 5 mm is well within the 0..~50.8 mm range
    try:
        motor.move_absolute_position(5, "mm")
    except ValueError:
        pytest.fail("move_absolute_position raised ValueError for an in-range move")


def test_move_absolute_rejects_below_low_limit() -> None:
    """An absolute move below the low travel limit must raise ValueError."""
    motor = _make_motor()
    with pytest.raises(ValueError):
        motor.move_absolute_position(-1, "mm")


def test_move_relative_rejects_resulting_position_over_limit() -> None:
    """A relative move whose RESULTING position would exceed the high limit
    must raise ValueError. The check validates the resulting position, not
    the raw delta — a small delta near the top of travel is still rejected."""
    motor = _make_motor()
    # Patch _motorIO so the position query (cmd 60) reports a position near
    # the high limit, and the subsequent move (cmd 21) is never reached
    # because the limit check raises first.
    near_high = motor.limit_high_microsteps - 1000  # ~50.79 mm in microsteps

    def fake_motorIO(cmd_no: int, cmd_param: int) -> int:
        # cmd 60 = get position; return a near-the-top position
        if cmd_no == 60:
            motor.error = 0
            return near_high
        # Any other command (e.g. cmd 21 = move relative) means the limit
        # check did not fire — record it so the test fails clearly.
        raise AssertionError(
            f"move_relative_position sent cmd {cmd_no} to the stage before the "
            "limit check rejected the over-travel resulting position"
        )

    motor._motorIO = fake_motorIO
    # A +5 mm delta from near the top would push the resulting position
    # well past limit_high_microsteps.
    with pytest.raises(ValueError):
        motor.move_relative_position(5, "mm")


def test_move_relative_raises_when_position_query_errors() -> None:
    """If the position-query serial call (cmd 60) leaves self.error truthy,
    move_relative_position must raise ValueError BEFORE any move command
    is sent — an unreadable position must not silently pass validation
    (the self.error arc at line 418-421). The patched _motorIO sets
    self.error on the position query and asserts no second (move) call
    follows."""
    motor = _make_motor()

    def fake_motorIO(cmd_no: int, cmd_param: int) -> int:
        if cmd_no == 60:
            # Position query fails — set the error surface, return 0.
            motor.error = 1
            return 0
        raise AssertionError(
            f"move_relative_position sent cmd {cmd_no} to the stage before "
            "the self.error check rejected the unreadable position"
        )

    motor._motorIO = fake_motorIO
    with pytest.raises(ValueError, match="Cannot read current position"):
        motor.move_relative_position(5, "mm")


def test_move_relative_rejects_resulting_position_below_low_limit() -> None:
    """A relative move whose RESULTING position would fall below the low
    travel limit must raise ValueError. The check validates the resulting
    position (current + delta), not the raw delta — a negative delta near
    the bottom of travel is still rejected."""
    motor = _make_motor()
    near_low = motor.limit_low_microsteps + 1000  # ~0.0476 mm in microsteps

    def fake_motorIO(cmd_no: int, cmd_param: int) -> int:
        if cmd_no == 60:
            motor.error = 0
            return near_low
        raise AssertionError(
            f"move_relative_position sent cmd {cmd_no} to the stage before "
            "the limit check rejected the below-low-limit resulting position"
        )

    motor._motorIO = fake_motorIO
    # A -5 mm delta from near the bottom would push the resulting position
    # well below limit_low_microsteps.
    with pytest.raises(ValueError):
        motor.move_relative_position(-5, "mm")


def test_move_relative_accepts_within_limits() -> None:
    """A relative move whose resulting position is within the travel range
    must not raise ValueError and must send the move command (cmd 21)."""
    motor = _make_motor()
    mid_position = motor.limit_high_microsteps // 2
    calls: list[int] = []

    def fake_motorIO(cmd_no: int, cmd_param: int) -> int:
        calls.append(cmd_no)
        if cmd_no == 60:
            motor.error = 0
            return mid_position
        # cmd 21 = move relative — the happy path sends this.
        return 0

    motor._motorIO = fake_motorIO
    # A small +1 mm delta from mid-position stays within limits.
    motor.move_relative_position(1, "mm")
    # Both the position query (60) and the move command (21) were sent.
    assert calls == [60, 21]


def test_move_maximum_position_removed() -> None:
    """move_maximum_position is confirmed dead code (no GUI caller) and
    must be deleted from the ZaberMotor class."""
    assert hasattr(ZaberMotor, "move_maximum_position") is False
