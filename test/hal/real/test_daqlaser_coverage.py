"""Branch-coverage closure for ``lightsheet.hal.real.daqlaser``.

Closes the two remaining branch-coverage gaps:

- ``InvertedVoltMap.to_volts`` line 201: the
  ``if self.max_power_mw <= 0: return self.max_volts`` early return
  (the "safe: off" guard). When the inverted map is constructed with
  ``max_power_mw=0`` (e.g. an unconfigured L2 channel), any requested
  power must return ``max_volts`` (5 V = true-off for inverted polarity)
  rather than divide by zero.

- ``DAQLaser.open()`` with a readback backend: if the off-voltage DAQ
  write fails, ``open()`` must abort before calling the serial backend's
  ``open()`` (lines 307-312 and 390). This also exercises the typed
  ``_write_volts`` except path that is not reached on the mock-only
  failure variants.

Behavior tests (AGENTS.md §5) — asserts on the returned voltage and the
abort behavior, never a static-source grep.
"""

from unittest.mock import MagicMock

import pytest

from lightsheet.hal.real.daqlaser import DAQLaser, InvertedVoltMap


def test_inverted_volt_map_zero_max_power_returns_off_volts() -> None:
    """InvertedVoltMap with max_power_mw=0 -> to_volts(any) returns
    max_volts (5 V = true-off for inverted polarity), not a
    ZeroDivisionError (line 201 — the ``safe: off`` guard).

    This is the defensive guard for an unconfigured L2 channel: the
    inverted formula ``V = max_volts * (1 - mw / max_power_mw)`` would
    divide by zero when max_power_mw=0, so the guard short-circuits to
    the off-voltage (5 V) — the safe, true-off state for an inverted
    analog-modulated laser."""
    vm = InvertedVoltMap(max_volts=5.0, max_power_mw=0.0)
    # Any requested power returns the off voltage (5 V).
    assert vm.to_volts(0.0) == 5.0
    assert vm.to_volts(50.0) == 5.0
    assert vm.to_volts(150.0) == 5.0
    # off_volts mirrors max_volts for inverted polarity.
    assert vm.off_volts == 5.0


def test_inverted_volt_map_negative_max_power_returns_off_volts() -> None:
    """A negative max_power_mw (a config typo) is equally guarded — the
    ``<= 0`` check catches it and returns the off voltage rather than
    producing a nonsensical negative-voltage result (which would trip
    the iBeam current-clip latch per the class docstring)."""
    vm = InvertedVoltMap(max_volts=5.0, max_power_mw=-10.0)
    assert vm.to_volts(50.0) == 5.0


def test_daqlaser_open_aborts_on_off_write_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the true-off DAQ write inside open() fails, the serial backend
    open is not attempted and the HAL error surface is set (lines 307-312
    and 390)."""
    monkeypatch.setattr(
        "lightsheet.hal.real.daqlaser.nidaqmx.Task",
        MagicMock(side_effect=RuntimeError("DAQ off-write failure")),
    )
    backend = MagicMock()
    laser = DAQLaser(
        terminal="/Dev7/ao0",
        wavelength=555,
        max_power_mw=300.0,
        mw_per_volt=60.0,
        readback_backend=backend,
    )
    assert laser.error == 0

    result = laser.open()

    assert result is None
    assert laser.error == 1
    assert "DAQ off-write failure" in laser.error_message
    assert not backend.open.called
