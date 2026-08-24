"""Behavior tests for the DAQLaser V->mW calibration curve (control + display).

Covers the calibration-curve infrastructure that makes the L1 percentage
slider map linearly to actual optical power. When a curve is loaded, the
control path uses the *inverse* curve to find the voltage that produces a
desired mW, and ``max_power`` is overridden to the curve's max mW so the
slider range matches the real optical power range.

Behavior covered:
- No curve (default) -> ``calibrated`` is False, ``get_output_power()``
  returns the staged ``self.power`` (unchanged linear behavior).
- Valid curve -> ``calibrated`` is True, ``max_power`` is the curve's max
  mW, ``set_power`` clamps to that, and ``_mw_to_volts`` uses the inverse
  curve to find the right voltage for the desired power.
- The control path uses the inverse curve: ``set_power(mw)`` stages ``mw``
  and converts to V via ``np.interp(mw, curve_mw, curve_v)``.
- Invalid curve (non-increasing V, negative mW, non-numeric, single point)
  -> ``error == 1``, falls back to ``calibrated=False`` / linear mode,
  ``get_output_power()`` returns staged mW. Never raises (AGENTS.md §10).
- Empty curve (``[]``) -> treated as "no curve" (None), not an error.

This is a BEHAVIOR test (AGENTS.md §5) — it executes the real DAQLaser code
under the conftest nidaqmx stub and asserts on runtime state.
"""

from __future__ import annotations

import numpy as np
import pytest

from lightsheet.hal.real.daqlaser import DAQLaser

_CURVE_TYPE = list[tuple[float, float]] | None


def _make_l1(calibration_curve: _CURVE_TYPE = None) -> DAQLaser:
    """Construct a DAQLaser mirroring Laser 1's config (555 nm, 300 mW max,
    60 mW per Volt, /Dev7/ao0), with an optional calibration curve."""
    return DAQLaser(
        terminal="/Dev7/ao0",
        wavelength=555,
        mw_per_volt=60.0,
        max_power_mw=300.0,
        label="Laser 1 (555 nm)",
        calibration_curve=calibration_curve,
    )


# A realistic DPSS-shaped curve: threshold knee ~0.8 V, linear region,
# slight saturation rolloff near 5 V. Endpoint 236.6 mW (lab-measured max).
_CURVE = [
    (0.0, 0.0),
    (0.8, 0.0),
    (1.5, 30.0),
    (2.5, 110.0),
    (3.5, 185.0),
    (5.0, 236.6),
]


def test_no_curve_is_uncalibrated_linear_mode() -> None:
    """Default construction (no calibration_curve) -> calibrated=False,
    max_power stays at config value, get_output_power() returns the staged
    self.power (linear-through-origin estimate, unchanged behavior)."""
    laser = _make_l1()
    assert laser.calibrated is False
    assert laser.error == 0
    assert laser.max_power == 300.0
    laser.set_power(150.0)
    # No curve -> returns the staged mW directly (150.0).
    assert laser.get_output_power() == 150.0


def test_empty_curve_treated_as_no_curve() -> None:
    """An empty curve list is treated as 'no curve' (None), not an error —
    calibrated=False, error surface clean, get_output_power() returns
    staged mW."""
    laser = _make_l1(calibration_curve=[])
    assert laser.calibrated is False
    assert laser.error == 0
    laser.set_power(150.0)
    assert laser.get_output_power() == 150.0


def test_valid_curve_overrides_max_power() -> None:
    """A valid curve -> calibrated=True, max_power is overridden to the
    curve's max mW (236.6), _max_volts is the curve's max V (5.0)."""
    laser = _make_l1(calibration_curve=_CURVE)
    assert laser.calibrated is True
    assert laser.error == 0
    assert laser.max_power == pytest.approx(236.6)
    assert laser._max_volts == pytest.approx(5.0)


def test_valid_curve_set_power_clamps_to_curve_max() -> None:
    """set_power clamps mW to the curve's max mW (236.6), not the config
    max (300). This makes the percentage slider map to the actual optical
    power range."""
    laser = _make_l1(calibration_curve=_CURVE)
    laser.set_power(999.0)
    assert laser.power == pytest.approx(236.6)
    laser.set_power(-50.0)
    assert laser.power == 0.0


def test_valid_curve_get_output_power_returns_staged_mw() -> None:
    """get_output_power() returns the staged self.power — the commanded mW.
    The inverse curve in set_power ensures the voltage produces this power,
    so the staged value IS the real output."""
    laser = _make_l1(calibration_curve=_CURVE)
    laser.set_power(110.0)
    assert laser.power == pytest.approx(110.0)
    assert laser.get_output_power() == pytest.approx(110.0)
    laser.set_power(236.6)
    assert laser.get_output_power() == pytest.approx(236.6)


def test_inverse_curve_finds_correct_voltage() -> None:
    """_mw_to_volts uses the inverse curve (np.interp on reversed axes)
    to find the voltage that produces a desired mW. At 110.0 mW the curve
    has an exact breakpoint at 2.5 V; at 30.0 mW it's at 1.5 V."""
    laser = _make_l1(calibration_curve=_CURVE)
    # Exact breakpoint: 110.0 mW -> 2.5 V
    assert laser._mw_to_volts(110.0) == pytest.approx(2.5)
    # Exact breakpoint: 30.0 mW -> 1.5 V
    assert laser._mw_to_volts(30.0) == pytest.approx(1.5)
    # Endpoint: 236.6 mW -> 5.0 V
    assert laser._mw_to_volts(236.6) == pytest.approx(5.0)


def test_inverse_curve_interpolates_between_breakpoints() -> None:
    """Between breakpoints, _mw_to_volts linearly interpolates the inverse
    curve. At 70.0 mW (between 30->1.5V and 110->2.5V), the interp voltage
    is 1.5 + (2.5-1.5)*(70-30)/(110-30) = 1.5 + 1.0*0.5 = 2.0 V."""
    laser = _make_l1(calibration_curve=_CURVE)
    assert laser._mw_to_volts(70.0) == pytest.approx(2.0)


def test_zero_mw_gives_zero_volts() -> None:
    """0 mW -> 0 V, not the threshold voltage. The inverse curve has a flat
    zero-power region (below the DPSS threshold knee) where np.interp would
    return the rightmost V with mW=0, but 0 mW means 'off' and should drive
    0V."""
    laser = _make_l1(calibration_curve=_CURVE)
    assert laser._mw_to_volts(0.0) == 0.0
    assert laser._mw_to_volts(-1.0) == 0.0


def test_percentage_maps_linearly_to_optical_power() -> None:
    """The key behavior: 0% = 0 mW (off), 100% = curve max mW, 50% = half
    the curve max. The slider maps linearly to actual optical power, not
    to voltage."""
    laser = _make_l1(calibration_curve=_CURVE)
    curve_max = 236.6
    for pct in [0, 25, 50, 75, 100]:
        mw = pct / 100.0 * curve_max
        laser.set_power(mw)
        assert laser.get_output_power() == pytest.approx(mw)
        # 0% -> 0V, 100% -> 5V (curve max V)
        v = laser._mw_to_volts(mw)
        if pct == 0:
            assert v == 0.0
        elif pct == 100:
            assert v == pytest.approx(5.0)


def test_invalid_curve_non_increasing_v_falls_back_to_linear() -> None:
    """A curve with non-increasing V is invalid -> error=1, calibrated=False,
    max_power stays at config value, get_output_power() returns staged mW
    (linear fallback). Never raises."""
    laser = _make_l1(
        calibration_curve=[(0.0, 0.0), (3.0, 100.0), (2.0, 50.0)]
    )
    assert laser.calibrated is False
    assert laser.error == 1
    assert "strictly" in laser.error_message or "increasing" in laser.error_message
    assert laser.max_power == 300.0
    laser.set_power(150.0)
    assert laser.get_output_power() == 150.0


def test_invalid_curve_negative_mw_falls_back_to_linear() -> None:
    """A curve with negative mW entries is invalid -> error=1,
    calibrated=False, linear fallback."""
    laser = _make_l1(
        calibration_curve=[(0.0, 0.0), (3.0, -10.0), (5.0, 200.0)]
    )
    assert laser.calibrated is False
    assert laser.error == 1
    assert "negative" in laser.error_message
    laser.set_power(150.0)
    assert laser.get_output_power() == 150.0


def test_invalid_curve_single_point_falls_back_to_linear() -> None:
    """A curve with only one point cannot be interpolated -> error=1,
    calibrated=False, linear fallback."""
    laser = _make_l1(calibration_curve=[(5.0, 236.6)])
    assert laser.calibrated is False
    assert laser.error == 1
    laser.set_power(150.0)
    assert laser.get_output_power() == 150.0


def test_invalid_curve_non_numeric_falls_back_to_linear() -> None:
    """A curve with non-numeric entries is invalid -> error=1,
    calibrated=False, linear fallback. Never raises."""
    laser = _make_l1(
        calibration_curve=[(0.0, 0.0), ("not", "numeric"), (5.0, 236.6)]  # type: ignore[list-item]
    )
    assert laser.calibrated is False
    assert laser.error == 1
    laser.set_power(150.0)
    assert laser.get_output_power() == 150.0


def test_off_resets_staged_power_with_curve_loaded() -> None:
    """off() resets self.power to 0.0 and writes 0V. The readback follows."""
    laser = _make_l1(calibration_curve=_CURVE)
    laser.set_power(110.0)
    assert laser.get_output_power() == pytest.approx(110.0)
    laser.off()
    assert laser.power == 0.0
    assert laser.get_output_power() == pytest.approx(0.0)


def test_uncalibrated_mw_to_volts_uses_linear_model() -> None:
    """Without a curve, _mw_to_volts uses the linear model (mw / mw_per_volt).
    With mw_per_volt=60: 150 mW -> 2.5 V, 300 mW -> 5.0 V."""
    laser = _make_l1()
    assert laser._mw_to_volts(150.0) == pytest.approx(2.5)
    assert laser._mw_to_volts(300.0) == pytest.approx(5.0)
    assert laser._mw_to_volts(0.0) == 0.0
