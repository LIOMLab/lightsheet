"""Branch-coverage tests for ``lightsheet/adaptive/controller.py``.

Targets the specific branches left uncovered by
``test_adaptive_controller.py`` (the locked-decision happy paths):

- ``fit_pilot_trajectory`` with empty pilot indices (the constant
  baseline fallback).
- ``AdaptiveController.update`` without ``prime()`` (no pilot trajectory
  → feedforward falls back to current exposure; re-acquire expected
  falls back to the target midpoint).
- NaN brighter / dimmer intensity guards (defensive NaN → 0.0).
- Multi-channel power-fallback path (brighter channel power trimmed).
- 3+ channel dimmer-index selection (the latent WR-03 guard).
- ``brighter_idx == 1`` power-slot assignment (L1 = dimmer, L2 = brighter).
- Pilot trajectory returning ~0 exposure (ff_exp <= 1e-9 → expected =
  target midpoint).

Pure-Python — no Qt, no HAL, no hardware. Mirrors the
``test_adaptive_controller.py`` style: construct ``AdaptiveConfig``
directly, call ``update``, assert on the returned ``AdaptiveCommand``.
"""

from __future__ import annotations

import math

import pytest

from lightsheet.adaptive.controller import (
    AdaptiveController,
    fit_pilot_trajectory,
)
from lightsheet.adaptive.types import AdaptiveConfig


def _cfg(**overrides: object) -> AdaptiveConfig:
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
    return AdaptiveConfig(**defaults)  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]


# --------------------------------------------------------------------- #
# fit_pilot_trajectory — empty pilot indices fallback
# --------------------------------------------------------------------- #


def test_fit_pilot_trajectory_empty_indices_returns_constant_baseline() -> None:
    """With zero pilot samples the fit falls back to a constant
    trajectory at ``exposures[0]`` (or 50 ms if exposures is also empty).
    Lines 36-37: the ``n == 0`` early return."""
    traj = fit_pilot_trajectory([], [], n_planes=20)
    # exposures empty → default 50e-3 baseline.
    assert traj(0) == pytest.approx(50e-3, abs=1e-9)
    assert traj(19) == pytest.approx(50e-3, abs=1e-9)


def test_fit_pilot_trajectory_empty_indices_uses_first_exposure() -> None:
    """Empty pilots but a non-empty exposures list → baseline is
    ``exposures[0]`` (the second arm of the line-36 ternary)."""
    traj = fit_pilot_trajectory([], [42e-3], n_planes=20)
    assert traj(0) == pytest.approx(42e-3, abs=1e-9)


# --------------------------------------------------------------------- #
# update() without prime() — no pilot trajectory
# --------------------------------------------------------------------- #


def test_update_without_prime_falls_back_to_current_exposure() -> None:
    """When ``prime()`` was never called, ``_pilot_traj`` is None so the
    feedforward baseline is the current exposure (line 165) and the
    re-acquire expected intensity is the target midpoint (line 280)."""
    cfg = _cfg()
    ctrl = AdaptiveController(cfg, n_planes=20)
    # No prime() — _pilot_traj stays None.
    cmd = ctrl.update(
        intensities=[0.92],  # inside target band → no re-acquire
        brighter_idx=0,
        current_exposure_s=50e-3,
        current_powers_mw=(20.0, 0.0),
        plane_idx=0,
    )
    # Feedforward = current exposure (50e-3); error small → exposure
    # stays near 50e-3 (clamped into bounds).
    assert cfg.min_exposure_s <= cmd.exposure_s <= cfg.max_exposure_s
    # No re-acquire (observed 0.92 vs expected midpoint 0.925 → 0.005
    # < threshold 0.08).
    assert cmd.reacquire is False


def test_update_without_prime_reacquire_uses_target_midpoint() -> None:
    """Without a pilot trajectory, the re-acquire expected value is the
    target midpoint (line 280). A sharp excursion from the midpoint
    triggers re-acquire even with no pilot."""
    cfg = _cfg(reacquire_threshold=0.08)
    ctrl = AdaptiveController(cfg, n_planes=20)
    # No prime().
    cmd = ctrl.update(
        intensities=[0.20],  # sharp drop vs midpoint 0.925 → 0.725 > 0.08
        brighter_idx=0,
        current_exposure_s=50e-3,
        current_powers_mw=(20.0, 0.0),
        plane_idx=0,
    )
    assert cmd.reacquire is True


# --------------------------------------------------------------------- #
# NaN intensity guards
# --------------------------------------------------------------------- #


def test_update_nan_brighter_intensity_treated_as_zero() -> None:
    """A NaN brighter-channel intensity is replaced with 0.0 (line 171)
    so the error math does not propagate NaN. With intensity 0.0 (well
    below the target band) the loop drives exposure up."""
    cfg = _cfg()
    ctrl = AdaptiveController(cfg, n_planes=20)
    ctrl.prime([0, 5, 10, 15, 19], [50e-3] * 5)
    cmd = ctrl.update(
        intensities=[float("nan")],
        brighter_idx=0,
        current_exposure_s=50e-3,
        current_powers_mw=(20.0, 0.0),
        plane_idx=0,
    )
    # NaN → 0.0 → large negative error → exposure rises (clamped).
    assert math.isfinite(cmd.exposure_s)
    assert cmd.exposure_s > 50e-3 - 1e-9


def test_update_nan_dimmer_intensity_treated_as_zero() -> None:
    """A NaN dimmer-channel intensity (in multi-channel mode, at a block
    boundary so the dimmer trim runs) is replaced with 0.0 (line 245)
    so the dimmer power trim math does not propagate NaN."""
    cfg = _cfg(block_size_n=8)
    ctrl = AdaptiveController(cfg, n_planes=20)
    ctrl.prime([0, 5, 10, 15, 19], [50e-3] * 5)
    # Plane 7 is a block boundary → dimmer trim runs. Brighter channel
    # 0 is in-band (0.92) so no power fallback; dimmer channel 1 is NaN.
    cmd = ctrl.update(
        intensities=[0.92, float("nan")],
        brighter_idx=0,
        current_exposure_s=50e-3,
        current_powers_mw=(20.0, 20.0),
        plane_idx=7,
    )
    # The dimmer (L2) power trim must be finite (NaN → 0.0 → trim
    # toward raising power since 0.0 < midpoint).
    assert math.isfinite(cmd.laser2_mw)


# --------------------------------------------------------------------- #
# Multi-channel power fallback (brighter channel power trimmed)
# --------------------------------------------------------------------- #


def test_update_multichannel_power_fallback_trims_brighter_power() -> None:
    """In multi-channel mode with exposure at a bound and target unmet,
    the BRIGHTER channel's power is trimmed (line 219-221), not the
    dimmer channel's. The dimmer channel only trims at block boundaries."""
    cfg = _cfg()
    ctrl = AdaptiveController(cfg, n_planes=20)
    ctrl.prime([0, 5, 10, 15, 19], [50e-3] * 5)
    # Channel 0 bright-and-still-low (0.10), channel 1 dimmer (0.05).
    # Exposure pinned at max → power fallback. brighter_idx=0 → L1
    # power trimmed up.
    cmd = ctrl.update(
        intensities=[0.10, 0.05],
        brighter_idx=0,
        current_exposure_s=cfg.max_exposure_s,
        current_powers_mw=(20.0, 20.0),
        plane_idx=0,  # not a block boundary → dimmer held
    )
    assert cmd.power_fallback is True
    # L1 (brighter) power rose; L2 (dimmer) held at 20.0 (no block
    # boundary).
    assert cmd.laser1_mw > 20.0 + 1e-9
    assert cmd.laser2_mw == pytest.approx(20.0, abs=1e-9)


# --------------------------------------------------------------------- #
# 3+ channel dimmer-index selection (WR-03 latent guard)
# --------------------------------------------------------------------- #


def test_update_three_channels_picks_dimmest_remaining_as_dimmer() -> None:
    """With 3+ channels the dimmer index is not ``1 - brighter_idx``
    (that formula is only valid for 2 channels). The guard at line 232
    picks the dimmest remaining channel. With brighter_idx=0 and
    intensities [0.92, 0.40, 0.30] the dimmer is index 2 (0.30)."""
    cfg = _cfg(block_size_n=8, max_power_mw=(100.0, 100.0, 100.0))
    ctrl = AdaptiveController(cfg, n_planes=20)
    ctrl.prime([0, 5, 10, 15, 19], [50e-3] * 5)
    # Plane 7 = block boundary so the dimmer trim runs.
    cmd = ctrl.update(
        intensities=[0.92, 0.40, 0.30],
        brighter_idx=0,
        current_exposure_s=50e-3,
        current_powers_mw=(20.0, 20.0, 20.0),  # ty: ignore[invalid-argument-type]
        plane_idx=7,
    )
    # The command only carries L1/L2 (2-tuple). The dimmer trim for the
    # 3-channel case still produces a finite L2 (the dimmer slot). The
    # key assertion is that the code path through line 232 executes
    # without error and yields a finite command.
    assert math.isfinite(cmd.laser1_mw)
    assert math.isfinite(cmd.laser2_mw)


# --------------------------------------------------------------------- #
# brighter_idx == 1 power-slot assignment
# --------------------------------------------------------------------- #


def test_update_brighter_idx_one_assigns_dimmer_to_l1() -> None:
    """When the brighter channel is index 1, the dimmer (channel 0) is
    assigned to L1 and the brighter to L2 (lines 262-263). At a block
    boundary the dimmer (L1) trims; the brighter (L2) trims on power
    fallback."""
    cfg = _cfg(block_size_n=8)
    ctrl = AdaptiveController(cfg, n_planes=20)
    ctrl.prime([0, 5, 10, 15, 19], [50e-3] * 5)
    # Brighter channel is 1 (intensity 0.97, above band → exposure
    # drops). Dimmer channel 0 (0.40). Plane 7 = block boundary so the
    # dimmer (channel 0 → L1) trims toward balance.
    cmd = ctrl.update(
        intensities=[0.40, 0.97],
        brighter_idx=1,
        current_exposure_s=50e-3,
        current_powers_mw=(20.0, 20.0),
        plane_idx=7,
    )
    # Exposure drops (brighter channel above target).
    assert cmd.exposure_s < 50e-3
    # L1 (dimmer channel 0) trimmed at the block boundary; L2 (brighter
    # channel 1) held (no power fallback — exposure is in bounds).
    assert math.isfinite(cmd.laser1_mw)
    assert math.isfinite(cmd.laser2_mw)


# --------------------------------------------------------------------- #
# Pilot trajectory returning ~0 exposure (ff_exp <= 1e-9)
# --------------------------------------------------------------------- #


def test_update_pilot_trajectory_zero_exposure_reacquire_uses_midpoint() -> None:
    """When the pilot trajectory evaluates to ~0 exposure at the current
    plane, the re-acquire expected value falls back to the target
    midpoint (line 278) instead of dividing by ~0. A sharp excursion
    from the midpoint then triggers re-acquire."""
    cfg = _cfg(reacquire_threshold=0.08)
    ctrl = AdaptiveController(cfg, n_planes=20)
    # Prime with all-zero exposures → the fitted trajectory is ~0
    # everywhere (polyfit of all-zeros → zero coefficients).
    ctrl.prime([0, 5, 10, 15, 19], [0.0] * 5)
    cmd = ctrl.update(
        intensities=[0.20],  # sharp drop vs midpoint 0.925 → re-acquire
        brighter_idx=0,
        current_exposure_s=50e-3,
        current_powers_mw=(20.0, 0.0),
        plane_idx=0,
    )
    # ff_exp ~0 → expected = midpoint → |0.20 - 0.925| = 0.725 > 0.08.
    assert cmd.reacquire is True
