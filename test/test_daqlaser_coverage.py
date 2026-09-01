"""Branch-coverage closure for ``lightsheet.hal.real.daqlaser``.

The single missing branch is line 201 in ``InvertedVoltMap.to_volts``:
the ``if self.max_power_mw <= 0: return self.max_volts`` early return
(the "safe: off" guard). When the inverted map is constructed with
``max_power_mw=0`` (e.g. an unconfigured L2 channel), any requested
power must return ``max_volts`` (5 V = true-off for inverted polarity)
rather than divide by zero.

This is pure conversion logic — no NI-DAQmx hardware involved — so it
runs on the dev machine without the conftest nidaqmx stub mattering.

Behavior test (AGENTS.md §5) — asserts on the returned voltage, never a
static-source grep.
"""

from lightsheet.hal.real.daqlaser import InvertedVoltMap


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
