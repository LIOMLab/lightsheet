"""Behavior tests for lightsheet/hal/mocks/mock_power_meter.py.

``MockPowerMeter`` is a pure-Python ``IPowerMeter`` backend with no hardware
dependency. These tests exercise every branch of the mock directly:
construction, open/close no-ops, read_power / read_power_mw / read_averaged,
zero offset, set_simulated_power, and the context-manager protocol.

This is a BEHAVIOR test (AGENTS.md §5).
"""

import pytest

from lightsheet.hal.mocks.mock_power_meter import MockPowerMeter


def test_construction_defaults() -> None:
    """__init__ clears the HAL error surface and stores the wavelength /
    simulated power. ``_opened`` starts False so read_power warns before
    open() is called."""
    meter = MockPowerMeter(wavelength_nm=488.0, simulated_power_w=0.001)
    assert meter.error == 0
    assert meter.error_message == ""
    assert meter._wavelength_nm == 488.0
    assert meter._simulated_power_w == 0.001
    assert meter._zero_offset == 0.0
    assert meter._opened is False


def test_open_sets_opened_flag() -> None:
    """open() is a no-op lifecycle verb that sets ``_opened=True`` and
    returns None."""
    meter = MockPowerMeter()
    assert meter._opened is False
    result = meter.open()
    assert result is None
    assert meter._opened is True


def test_close_clears_opened_flag() -> None:
    """close() is a no-op lifecycle verb that sets ``_opened=False`` and
    returns None."""
    meter = MockPowerMeter()
    meter.open()
    assert meter._opened is True
    result = meter.close()
    assert result is None
    assert meter._opened is False


def test_read_power_returns_simulated_value() -> None:
    """read_power() returns the simulated power minus the zero offset."""
    meter = MockPowerMeter(simulated_power_w=0.0025)
    meter.open()
    assert meter.read_power() == pytest.approx(0.0025)


def test_read_power_warns_when_not_opened() -> None:
    """read_power() called before open() logs a warning but still returns
    the simulated value (the not-opened branch)."""
    meter = MockPowerMeter(simulated_power_w=0.001)
    assert meter._opened is False
    # Should not raise — just logs a warning.
    assert meter.read_power() == pytest.approx(0.001)


def test_read_power_mw_converts_to_milliwatts() -> None:
    """read_power_mw() returns read_power() * 1000.0."""
    meter = MockPowerMeter(simulated_power_w=0.0025)
    meter.open()
    assert meter.read_power_mw() == pytest.approx(2.5)


def test_read_averaged_with_fewer_than_two_samples() -> None:
    """read_averaged(n<2) short-circuits to a single read_power() call
    (the n_samples < 2 branch)."""
    meter = MockPowerMeter(simulated_power_w=0.003)
    meter.open()
    assert meter.read_averaged(1, delay_s=0.0) == pytest.approx(0.003)
    assert meter.read_averaged(0, delay_s=0.0) == pytest.approx(0.003)


def test_read_averaged_discards_first_and_averages() -> None:
    """read_averaged(n>=2) takes n readings, discards the first, and
    returns the mean of the rest. With a constant simulated value the
    mean equals the simulated value. delay_s=0 skips the sleep branch."""
    meter = MockPowerMeter(simulated_power_w=0.004)
    meter.open()
    result = meter.read_averaged(4, delay_s=0.0)
    assert result == pytest.approx(0.004)


def test_read_averaged_with_delay_sleeps_between_readings() -> None:
    """read_averaged with delay_s > 0 sleeps between readings (the
    ``i > 0 and delay_s > 0`` True branch). Use a tiny delay so the test
    stays fast."""
    meter = MockPowerMeter(simulated_power_w=0.004)
    meter.open()
    result = meter.read_averaged(3, delay_s=0.001)
    assert result == pytest.approx(0.004)


def test_zero_records_current_power_as_offset() -> None:
    """zero() records the current simulated power as the zero offset so
    subsequent readings subtract it (simulating a dark offset)."""
    meter = MockPowerMeter(simulated_power_w=0.005)
    meter.open()
    meter.zero()
    assert meter._zero_offset == pytest.approx(0.005)
    # After zeroing, read_power returns simulated - offset == 0.
    assert meter.read_power() == pytest.approx(0.0)


def test_set_simulated_power_updates_value() -> None:
    """set_simulated_power() updates the simulated power reading."""
    meter = MockPowerMeter(simulated_power_w=0.0)
    meter.open()
    meter.set_simulated_power(0.007)
    assert meter._simulated_power_w == pytest.approx(0.007)
    assert meter.read_power() == pytest.approx(0.007)


def test_context_manager_opens_and_closes() -> None:
    """__enter__ calls open() and returns self; __exit__ calls close()."""
    meter = MockPowerMeter(simulated_power_w=0.001)
    assert meter._opened is False
    with meter as ctx:
        assert ctx is meter
        assert meter._opened is True
    assert meter._opened is False


def test_error_surface_starts_clean() -> None:
    """The HAL error surface (error / error_message) starts at 0 / empty
    after construction."""
    meter = MockPowerMeter()
    assert meter.error == 0
    assert meter.error_message == ""
