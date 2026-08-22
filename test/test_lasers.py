"""
Unit tests for src/lasers.py — laser write-failure state revert and Max Power clamping.

The conftest.py stub makes nidaqmx.Task() raise nidaqmx.errors.Error on this
Mac (no NI-DAQmx driver runtime), so the typed-except path in
Lasers._update_setpoints fires naturally — no extra mocking is required.
"""

from lightsheet.lasers import Lasers


def test_write_failure_reverts_state() -> None:
    """laser1_on() under a DAQ write failure must revert laser1_active and
    the setpoint to off/zero and populate the error surface."""
    lasers = Lasers()
    lasers.laser1_on()
    assert lasers.laser1_active is False
    assert lasers._laser1_setpoint == 0
    assert lasers.error == 1
    assert isinstance(lasers.error_message, str) and lasers.error_message != ""


def test_write_failure_reverts_both_lasers() -> None:
    """Both lasers share one nidaqmx.Task write, so a write failure reverts
    both laser states together."""
    lasers = Lasers()
    lasers.laser2_on()
    assert lasers.laser2_active is False
    assert lasers._laser2_setpoint == 0


def test_power_clamp_laser1() -> None:
    """_update_setpoints clamps laser1 setpoint to laser1_max_power before
    attempting the write."""
    lasers = Lasers()
    lasers.laser1_max_power = 5
    lasers._laser1_setpoint = 10
    lasers._laser2_setpoint = 0
    lasers._update_setpoints()
    assert lasers._laser1_setpoint == 5


def test_power_clamp_laser2() -> None:
    """_update_setpoints clamps laser2 setpoint to laser2_max_power before
    attempting the write."""
    lasers = Lasers()
    lasers.laser2_max_power = 5
    lasers._laser1_setpoint = 0
    lasers._laser2_setpoint = 10
    lasers._update_setpoints()
    assert lasers._laser2_setpoint == 5


def test_power_clamp_floor_zero() -> None:
    """No negative voltages — setpoint is clamped to a floor of 0."""
    lasers = Lasers()
    lasers.laser1_max_power = 5
    lasers._laser1_setpoint = -3
    lasers._laser2_setpoint = 0
    lasers._update_setpoints()
    assert lasers._laser1_setpoint == 0


def test_laser1_on_clamps_to_max_power() -> None:
    """laser1_on() must clamp the commanded laser1_power to laser1_max_power
    before the write attempt. The DAQ stub makes the write fail and revert
    the active laser's setpoint to 0, so we cannot observe the clamped
    setpoint post-write on an active laser. Instead we verify the clamp by
    inspecting _laser1_setpoint AFTER laser1_on() but with the write path
    disabled: we point laser1_power above max, call laser1_on(), and confirm
    the setpoint was clamped to max_power before _update_setpoints ran.

    To observe the pre-write clamped setpoint, we stub _update_setpoints so
    it records the setpoint without attempting the (failing) DAQ write and
    without reverting state. This exercises the real laser1_on() clamp
    expression, not Python's min()."""
    lasers = Lasers()
    lasers.laser1_power = 10
    lasers.laser1_max_power = 5

    captured = {}
    original_update = lasers._update_setpoints

    def capturing_update() -> None:
        # Record the setpoint laser1_on() staged BEFORE the write/revert.
        captured["setpoint"] = lasers._laser1_setpoint

    lasers._update_setpoints = capturing_update
    try:
        lasers.laser1_on()
    finally:
        lasers._update_setpoints = original_update

    # The clamp inside laser1_on() must have reduced 10 to 5.
    assert captured["setpoint"] == 5
    # And a below-max power is preserved (not clamped upward).
    lasers.laser1_power = 3
    captured.clear()
    lasers._update_setpoints = capturing_update
    try:
        lasers.laser1_on()
    finally:
        lasers._update_setpoints = original_update
    assert captured["setpoint"] == 3
