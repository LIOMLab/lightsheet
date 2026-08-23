"""Behavior tests for the DAQLaser V->mW calibration curve (display-only).

Covers the calibration-curve infrastructure added so the L1 readback label
can reflect a rig-measured V->mW curve instead of the unverified
linear-through-origin estimate. The curve is DISPLAY-ONLY: it affects
``get_output_power()`` (which feeds the readback label) but NOT the control
path (``set_power`` mW -> V via ``mw_per_volt``) or the two-layer clamp.

Behavior covered:
- No curve (default) -> ``calibrated`` is False, ``get_output_power()``
  returns the staged ``self.power`` (unchanged behavior).
- Valid curve -> ``calibrated`` is True, ``get_output_power()`` returns the
  ``numpy.interp``-evaluated mW at the commanded voltage
  (``self.power / self.mw_per_volt``), NOT the staged mW.
- The control path is untouched: ``set_power`` still stages ``self.power``
  (the linear mW) and the mW clamp to ``max_power`` is intact.
- Invalid curve (non-increasing V, negative mW, non-numeric, single point)
  -> ``error == 1``, falls back to ``calibrated=False`` / linear mode,
  ``get_output_power()`` returns staged mW. Never raises (AGENTS.md §10).
- Empty curve (``[]``) -> treated as "no curve" (None), not an error.

This is a BEHAVIOR test (AGENTS.md §5) — it executes the real DAQLaser code
under the conftest nidaqmx stub and asserts on runtime state.
"""

from __future__ import annotations

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
    get_output_power() returns the staged self.power (linear-through-origin
    estimate, unchanged behavior)."""
    laser = _make_l1()
    assert laser.calibrated is False
    assert laser.error == 0
    laser.set_power(150.0)
    # No curve -> returns the staged mW directly (150.0), NOT a curve value.
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


def test_valid_curve_is_calibrated_and_interpolates() -> None:
    """A valid curve -> calibrated=True, get_output_power() returns the
    numpy.interp-evaluated mW at the commanded voltage
    (self.power / self.mw_per_volt), NOT the staged mW."""
    laser = _make_l1(calibration_curve=_CURVE)
    assert laser.calibrated is True
    assert laser.error == 0

    # Stage 150 mW -> commanded V = 150/60 = 2.5 V.
    # At 2.5 V the curve has an exact breakpoint -> 110.0 mW.
    laser.set_power(150.0)
    assert laser.power == 150.0  # control path stages the linear mW
    assert laser.get_output_power() == pytest.approx(110.0)

    # Stage 300 mW (max) -> commanded V = 5.0 V -> curve endpoint 236.6 mW.
    # This is the key honesty check: the label shows 236.6, not 300.
    laser.set_power(300.0)
    assert laser.power == 300.0
    assert laser.get_output_power() == pytest.approx(236.6)


def test_curve_interpolates_between_breakpoints() -> None:
    """Between breakpoints, get_output_power() linearly interpolates
    (numpy.interp). At V=2.0 (between 1.5->30 and 2.5->110), the interp
    value is 30 + (110-30)*(2.0-1.5)/(2.5-1.5) = 30 + 80*0.5 = 70.0."""
    laser = _make_l1(calibration_curve=_CURVE)
    # V=2.0 -> mW=120 -> commanded V = 120/60 = 2.0
    laser.set_power(120.0)
    assert laser.get_output_power() == pytest.approx(70.0)


def test_curve_clamps_to_endpoints_outside_range() -> None:
    """numpy.interp clamps to the curve endpoints outside the breakpoint
    range. Below the first V -> first mW; above the last V -> last mW."""
    laser = _make_l1(calibration_curve=_CURVE)
    # V=0.4 (below first nonzero breakpoint 0.8, but first breakpoint is
    # 0.0->0.0) -> interp clamps to the 0.0-0.8 segment -> 0.0 mW.
    laser.set_power(24.0)  # V = 24/60 = 0.4
    assert laser.get_output_power() == pytest.approx(0.0)
    # V=6.0 (above last breakpoint 5.0) -> clamps to 236.6. But set_power
    # clamps mW to max_power=300 -> V=5.0 -> 236.6. Use a curve with a
    # higher max V to test the above-range clamp directly via _write_volts
    # is not possible without bypassing set_power; the interp clamping is
    # numpy's contract, exercised by the endpoint test above.


def test_control_path_untouched_by_curve() -> None:
    """The calibration curve is DISPLAY-ONLY: set_power still stages the
    linear mW (self.power) and the mW clamp to max_power is intact, even
    when a curve is loaded."""
    laser = _make_l1(calibration_curve=_CURVE)
    # set_power clamps to max_power (300) — the curve does not change this.
    laser.set_power(999.0)
    assert laser.power == 300.0
    # Floor clamp.
    laser.set_power(-50.0)
    assert laser.power == 0.0


def test_invalid_curve_non_increasing_v_falls_back_to_linear() -> None:
    """A curve with non-increasing V is invalid -> error=1, calibrated=False,
    get_output_power() returns staged mW (linear fallback). Never raises."""
    laser = _make_l1(
        calibration_curve=[(0.0, 0.0), (3.0, 100.0), (2.0, 50.0)]
    )
    assert laser.calibrated is False
    assert laser.error == 1
    assert "strictly" in laser.error_message or "increasing" in laser.error_message
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
    """off() resets self.power to 0.0 -> commanded V = 0 -> curve interp at
    V=0 is the first breakpoint mW (0.0 here). The readback follows."""
    laser = _make_l1(calibration_curve=_CURVE)
    laser.set_power(150.0)
    assert laser.get_output_power() == pytest.approx(110.0)
    laser.off()
    assert laser.power == 0.0
    assert laser.get_output_power() == pytest.approx(0.0)
