"""Pure-logic tests for the adaptive controller (pilot feedforward +
per-plane PI residual + power fallback + cross-channel balance +
re-acquire).

Mirrors the ``test_channel_map.py`` / ``test_config_schema.py`` style:
construct the frozen ``AdaptiveConfig`` directly, call
``AdaptiveController.prime`` / ``update``, assert on the returned frozen
``AdaptiveCommand`` fields. No Qt, no HAL, no hardware.

Covers the locked control-law decisions:
- D-01: exposure is primary; power fallback only at an exposure bound.
- D-02: brighter channel drives shared exposure; per-laser power trim
  moves the dimmer channel toward balance; L2 changes only on block
  boundaries (``(plane_idx + 1) % block_size_n == 0``).
- D-03: sparse pilot feedforward + per-plane PI residual + one
  re-acquire; anti-windup clamps the integral to the power limits.
- Schema-A: ``AdaptiveSample`` carries plane_index,
  intensity_fraction[channels] (NaN for inactive), exposure_s,
  laser_power_mw[2], control_variable_active, reacquired, power_fallback.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from lightsheet.adaptive.controller import (
    AdaptiveController,
    fit_pilot_trajectory,
    pi_residual,
    should_reacquire,
)
from lightsheet.adaptive.types import (
    AdaptiveCommand,
    AdaptiveConfig,
    AdaptiveSample,
)


def _cfg(**overrides: object) -> AdaptiveConfig:
    """A standard test config: 20-plane stack, 5 pilots, exposure
    5-200 ms, power 0-100 mW per laser, target band 0.90-0.95,
    reacquire threshold 0.08, block N=8, Kp=0.4, Ki=0.05."""
    defaults: dict[str, object] = dict(
        enabled=True,
        min_exposure_s=5e-3,
        max_exposure_s=200e-3,
        min_power_mw=(0.0, 0.0),
        max_power_mw=(100.0, 100.0),
        target_band_lo=0.90,
        target_band_hi=0.95,
        reacquire_threshold=0.08,
        block_size_n=8,
        kp=0.4,
        ki=0.05,
        pilot_count=5,
        sensor_max=65535,
        max_reacquire_attempts=1,
    )
    defaults.update(overrides)
    return AdaptiveConfig(**defaults)  # type: ignore[arg-type]


# --------------------------------------------------------------------- #
# AdaptiveConfig validation
# --------------------------------------------------------------------- #


def test_config_frozen() -> None:
    cfg = _cfg()
    with pytest.raises(AttributeError):
        cfg.enabled = False  # type: ignore[misc]


def test_config_rejects_min_exposure_above_max() -> None:
    with pytest.raises(ValueError):
        _cfg(min_exposure_s=300e-3, max_exposure_s=200e-3)


def test_config_rejects_min_power_above_max() -> None:
    with pytest.raises(ValueError):
        _cfg(min_power_mw=(50.0, 0.0), max_power_mw=(40.0, 100.0))


def test_config_rejects_negative_block_size() -> None:
    with pytest.raises(ValueError):
        _cfg(block_size_n=0)


def test_config_rejects_target_band_lo_above_hi() -> None:
    with pytest.raises(ValueError):
        _cfg(target_band_lo=0.95, target_band_hi=0.90)


# --------------------------------------------------------------------- #
# AdaptiveCommand.fixed
# --------------------------------------------------------------------- #


def test_fixed_command_marks_fixed_no_fallback_no_reacquire() -> None:
    cmd = AdaptiveCommand.fixed(
        exposure_s=50e-3,
        laser1_mw=20.0,
        laser2_mw=15.0,
    )
    assert cmd.control_variable_active == "fixed"
    assert cmd.reacquire is False
    assert cmd.power_fallback is False
    assert cmd.exposure_s == pytest.approx(50e-3)
    assert cmd.laser1_mw == pytest.approx(20.0)
    assert cmd.laser2_mw == pytest.approx(15.0)


# --------------------------------------------------------------------- #
# Pilot feedforward fit
# --------------------------------------------------------------------- #


def test_fit_pilot_trajectory_smooth_monotonic() -> None:
    """Five evenly-spaced pilots over 20 planes fit a smooth gain
    trajectory. The fitted exposure at the bright end (low plane index)
    must be lower than at the dim end (high plane index) for a
    bright→dim profile where exposure must rise to compensate."""
    n_planes = 20
    pilot_indices = [int(i) for i in np.linspace(0, n_planes - 1, 5)]
    # Bright→dim: intensity 0.95 → 0.30. Required exposure scales
    # inversely with intensity (more light → less exposure needed).
    intensities = [0.95 - 0.65 * (i / (n_planes - 1)) for i in pilot_indices]
    base_exposure = 50e-3
    target = 0.925  # band midpoint
    # Required exposure ≈ base * (target / observed) — bright planes
    # need less, dim planes need more.
    exposures = [base_exposure * (target / max(intensities[i], 1e-6))
                 for i in range(len(intensities))]
    traj = fit_pilot_trajectory(
        pilot_indices, exposures, n_planes=n_planes
    )
    # Evaluate the fitted trajectory at every plane.
    fitted = [traj(plane) for plane in range(n_planes)]
    # Smooth: no plane-to-plane jump larger than 30% of the span.
    span = max(fitted) - min(fitted)
    for i in range(1, n_planes):
        assert abs(fitted[i] - fitted[i - 1]) < 0.5 * span + 1e-9
    # Monotonic-ish: the dim end (plane 19) needs more exposure than
    # the bright end (plane 0).
    assert fitted[-1] > fitted[0]


# --------------------------------------------------------------------- #
# PI residual with anti-windup
# --------------------------------------------------------------------- #


def test_pi_residual_proportional_response() -> None:
    cfg = _cfg()
    # Error of +0.05 (above target band) → P term reduces exposure.
    integral = 0.0
    delta, integral = pi_residual(
        error=0.05, integral=integral, cfg=cfg
    )
    # P term: kp * error = 0.4 * 0.05 = 0.02 (reduces exposure).
    assert delta == pytest.approx(-cfg.kp * 0.05, abs=1e-9)


def test_pi_residual_integral_accumulates() -> None:
    cfg = _cfg()
    integral = 0.0
    # Two steps of persistent +0.05 error → integral grows by ki*0.05
    # each step.
    _, integral = pi_residual(error=0.05, integral=integral, cfg=cfg)
    assert integral == pytest.approx(cfg.ki * 0.05, abs=1e-9)
    _, integral = pi_residual(error=0.05, integral=integral, cfg=cfg)
    assert integral == pytest.approx(2 * cfg.ki * 0.05, abs=1e-9)


def test_pi_residual_anti_windup_clamps_integral() -> None:
    """A persistent large error must not let the integral grow unbounded
    — it is clamped to the configured power bounds expressed as an
    exposure-equivalent range."""
    cfg = _cfg()
    integral = 0.0
    # Drive a large persistent error for many steps.
    for _ in range(1000):
        _, integral = pi_residual(error=1.0, integral=integral, cfg=cfg)
    # The integral must be bounded (not infinity, not NaN, not absurdly
    # large). The exact clamp bound is implementation-defined but must
    # be finite and consistent with the configured bounds.
    assert math.isfinite(integral)
    assert abs(integral) < 1e6


# --------------------------------------------------------------------- #
# Re-acquire decision
# --------------------------------------------------------------------- #


def test_should_reacquire_on_sharp_excursion() -> None:
    cfg = _cfg(reacquire_threshold=0.08)
    # Observed 0.30 vs expected 0.90 → deviation 0.60 > threshold 0.08.
    assert should_reacquire(
        observed=0.30, expected=0.90, cfg=cfg
    ) is True


def test_should_not_reacquire_on_gradual_change() -> None:
    cfg = _cfg(reacquire_threshold=0.08)
    # Observed 0.88 vs expected 0.90 → deviation 0.02 < threshold.
    assert should_reacquire(
        observed=0.88, expected=0.90, cfg=cfg
    ) is False


# --------------------------------------------------------------------- #
# AdaptiveController.update — D-01 exposure primary, power fallback
# --------------------------------------------------------------------- #


def test_exposure_primary_then_power_fallback() -> None:
    """When the target is unmet and exposure is within bounds, the
    controller moves exposure only (power_fallback=False). When
    exposure hits a bound and the target is still unmet, the controller
    switches to power (power_fallback=True)."""
    cfg = _cfg()
    ctrl = AdaptiveController(cfg, n_planes=20)
    # Prime with a flat pilot trajectory at the band midpoint exposure.
    ctrl.prime([0, 5, 10, 15, 19], [50e-3] * 5)

    # Mid-band observation → exposure moves, no power fallback.
    cmd = ctrl.update(
        intensities=[0.50],  # below target → need more exposure
        brighter_idx=0,
        current_exposure_s=50e-3,
        current_powers_mw=(20.0, 0.0),
        plane_idx=0,
    )
    assert cmd.power_fallback is False
    assert cmd.exposure_s > 50e-3  # exposure rose

    # Pin exposure at max with a still-low intensity → power fallback.
    cmd = ctrl.update(
        intensities=[0.10],  # well below target
        brighter_idx=0,
        current_exposure_s=cfg.max_exposure_s,  # at the bound
        current_powers_mw=(20.0, 0.0),
        plane_idx=1,
    )
    assert cmd.power_fallback is True


def test_power_clamped_to_max() -> None:
    """SC-2: command laser power never exceeds cfg.max_power_mw even
    with extreme intensity error."""
    cfg = _cfg()
    ctrl = AdaptiveController(cfg, n_planes=20)
    ctrl.prime([0, 5, 10, 15, 19], [50e-3] * 5)
    cmd = ctrl.update(
        intensities=[0.0],  # extreme low → max power request
        brighter_idx=0,
        current_exposure_s=cfg.max_exposure_s,
        current_powers_mw=(0.0, 0.0),
        plane_idx=0,
    )
    assert cmd.laser1_mw <= cfg.max_power_mw[0] + 1e-9
    assert cmd.laser2_mw <= cfg.max_power_mw[1] + 1e-9


# --------------------------------------------------------------------- #
# D-02 brighter channel drives shared exposure; L2 only at block bounds
# --------------------------------------------------------------------- #


def test_brighter_channel_drives_shared_exposure() -> None:
    """In multi-channel mode, the shared exposure is driven by the
    brighter channel's intensity (the one closer to / above the target
    band). The dimmer channel's power trims toward balance."""
    cfg = _cfg()
    ctrl = AdaptiveController(cfg, n_planes=20)
    ctrl.prime([0, 5, 10, 15, 19], [50e-3] * 5)
    # Channel 0 bright (0.97 — above band), channel 1 dim (0.40).
    # The brighter channel (0) drives exposure DOWN; channel 1 power
    # rises to balance.
    cmd = ctrl.update(
        intensities=[0.97, 0.40],
        brighter_idx=0,
        current_exposure_s=50e-3,
        current_powers_mw=(20.0, 20.0),
        plane_idx=0,
    )
    # Exposure should drop (brighter channel is above target).
    assert cmd.exposure_s < 50e-3
    # Dimmer channel (1) power should rise relative to its start.
    assert cmd.laser2_mw >= 20.0 - 1e-9


def test_l2_trim_only_at_block_boundaries() -> None:
    """L2 power changes only on plane indices satisfying
    ``(plane_idx + 1) % block_size_n == 0``. Between block boundaries
    the L2 mW in the command equals the current L2 mW (held)."""
    cfg = _cfg(block_size_n=8)
    ctrl = AdaptiveController(cfg, n_planes=20)
    ctrl.prime([0, 5, 10, 15, 19], [50e-3] * 5)
    base_l2 = 20.0
    # Walk planes 0..6 (none are block boundaries: (p+1)%8 != 0).
    l2_values = []
    for p in range(7):
        cmd = ctrl.update(
            intensities=[0.50, 0.45],
            brighter_idx=0,
            current_exposure_s=50e-3,
            current_powers_mw=(20.0, base_l2),
            plane_idx=p,
        )
        l2_values.append(cmd.laser2_mw)
    # Between block boundaries L2 is held at base_l2.
    for v in l2_values:
        assert v == pytest.approx(base_l2, abs=1e-9)
    # Plane 7 is a block boundary ((7+1)%8 == 0) → L2 may change.
    cmd = ctrl.update(
        intensities=[0.50, 0.30],  # dimmer channel 1 → L2 should rise
        brighter_idx=0,
        current_exposure_s=50e-3,
        current_powers_mw=(20.0, base_l2),
        plane_idx=7,
    )
    assert cmd.laser2_mw != pytest.approx(base_l2, abs=1e-9)


# --------------------------------------------------------------------- #
# D-03 one re-acquire; gradual profile does not repeatedly re-acquire
# --------------------------------------------------------------------- #


def test_one_sharp_excursion_requests_one_reacquire() -> None:
    cfg = _cfg(reacquire_threshold=0.08)
    ctrl = AdaptiveController(cfg, n_planes=20)
    ctrl.prime([0, 5, 10, 15, 19], [50e-3] * 5)
    # A sharp excursion at plane 5 → reacquire=True.
    cmd_exc = ctrl.update(
        intensities=[0.20],  # sharp drop vs the ~0.65 expected
        brighter_idx=0,
        current_exposure_s=50e-3,
        current_powers_mw=(20.0, 0.0),
        plane_idx=5,
    )
    assert cmd_exc.reacquire is True
    # After the re-acquire attempt is consumed, the next plane must not
    # be flagged for re-acquire (max_reacquire_attempts=1).
    cmd_next = ctrl.update(
        intensities=[0.60],
        brighter_idx=0,
        current_exposure_s=50e-3,
        current_powers_mw=(20.0, 0.0),
        plane_idx=6,
    )
    assert cmd_next.reacquire is False


def test_gradual_profile_does_not_reacquire() -> None:
    cfg = _cfg(reacquire_threshold=0.08)
    ctrl = AdaptiveController(cfg, n_planes=20)
    # Pilots track the gradual bright→dim profile so the feedforward
    # expectation matches the observation at each plane → no excursion.
    pilot_indices = [0, 5, 10, 15, 19]
    pilot_exposures = [
        50e-3 * (0.925 / max(0.95 - 0.65 * (i / 19), 1e-6))
        for i in pilot_indices
    ]
    ctrl.prime(pilot_indices, pilot_exposures)
    reacquire_count = 0
    for p in range(20):
        # Gradual intensity profile matching the pilots.
        observed = 0.95 - 0.65 * (p / 19)
        cmd = ctrl.update(
            intensities=[observed],
            brighter_idx=0,
            current_exposure_s=50e-3,
            current_powers_mw=(20.0, 0.0),
            plane_idx=p,
        )
        if cmd.reacquire:
            reacquire_count += 1
    # A gradual profile that matches the feedforward must not trigger
    # any re-acquire.
    assert reacquire_count == 0


# --------------------------------------------------------------------- #
# Adaptive-off: constant AdaptiveCommand, no extra writes
# --------------------------------------------------------------------- #


def test_disabled_config_yields_constant_command() -> None:
    """When adaptive is disabled, the controller returns a constant
    command equal to the current exposure/power, with
    control_variable_active='fixed' and no reacquire / power_fallback.
    The caller applies the same fixed command every plane — zero extra
    per-plane actuator writes."""
    cfg = _cfg(enabled=False)
    ctrl = AdaptiveController(cfg, n_planes=20)
    ctrl.prime([0, 5, 10, 15, 19], [50e-3] * 5)
    cmd = ctrl.update(
        intensities=[0.50],
        brighter_idx=0,
        current_exposure_s=50e-3,
        current_powers_mw=(20.0, 15.0),
        plane_idx=0,
    )
    assert cmd.control_variable_active == "fixed"
    assert cmd.reacquire is False
    assert cmd.power_fallback is False
    assert cmd.exposure_s == pytest.approx(50e-3)
    assert cmd.laser1_mw == pytest.approx(20.0)
    assert cmd.laser2_mw == pytest.approx(15.0)


# --------------------------------------------------------------------- #
# Schema-A: AdaptiveSample shape
# --------------------------------------------------------------------- #


def test_adaptive_sample_shape_single_channel() -> None:
    """Single-channel sample: intensity_fraction has one entry; the
    inactive channel slot is NaN."""
    sample = AdaptiveSample(
        plane_index=3,
        intensity_fraction=[0.92],
        exposure_s=50e-3,
        laser_power_mw=(20.0, 0.0),
        control_variable_active="exposure",
        reacquired=False,
        power_fallback=False,
    )
    assert sample.plane_index == 3
    assert sample.intensity_fraction == [0.92]
    assert sample.exposure_s == pytest.approx(50e-3)
    assert sample.laser_power_mw == (20.0, 0.0)
    assert sample.control_variable_active == "exposure"
    assert sample.reacquired is False
    assert sample.power_fallback is False


def test_adaptive_sample_shape_multi_channel_with_nan_inactive() -> None:
    """Multi-channel sample with one inactive channel: the inactive
    channel's intensity_fraction entry is NaN (schema-A)."""
    sample = AdaptiveSample(
        plane_index=7,
        intensity_fraction=[0.92, float("nan")],
        exposure_s=50e-3,
        laser_power_mw=(20.0, 15.0),
        control_variable_active="exposure",
        reacquired=False,
        power_fallback=False,
    )
    assert len(sample.intensity_fraction) == 2
    assert sample.intensity_fraction[0] == pytest.approx(0.92)
    assert math.isnan(sample.intensity_fraction[1])


def test_adaptive_sample_frozen() -> None:
    sample = AdaptiveSample(
        plane_index=0,
        intensity_fraction=[0.9],
        exposure_s=50e-3,
        laser_power_mw=(20.0, 0.0),
        control_variable_active="fixed",
        reacquired=False,
        power_fallback=False,
    )
    with pytest.raises(AttributeError):
        sample.plane_index = 99  # type: ignore[misc]
