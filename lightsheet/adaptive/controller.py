"""Adaptive controller: pilot feedforward + per-plane PI residual +
power fallback + cross-channel balance + re-acquire decision.

Pure-Python — no Qt, no HAL, no scipy. The control law is trivial math
(P+I, D=0; the standard scanning-microscopy choice — D is suppressed to
avoid noise amplification). The pilot trajectory fit uses
``numpy.polyfit`` (degree 1-2); the iDISCO+ profile is monotonic-ish so
a low-degree polynomial is sufficient.

The locked control-law decisions:
- D-01: exposure is primary; power fallback only at an exposure bound.
- D-02: brighter channel drives shared exposure; per-laser power trim
  moves the dimmer channel toward balance; L2 changes only on block
  boundaries (``(plane_idx + 1) % block_size_n == 0``).
- D-03: sparse pilot feedforward + per-plane PI residual + one
  re-acquire; anti-windup clamps the integral.
"""

from __future__ import annotations

import math

import numpy as np

from lightsheet.adaptive.types import AdaptiveCommand, AdaptiveConfig

# --------------------------------------------------------------------- #
# Pilot feedforward trajectory fit
# --------------------------------------------------------------------- #


def fit_pilot_trajectory(
    pilot_indices: list[int],
    exposures: list[float],
    n_planes: int,
) -> callable:  # type: ignore[type-arg]
    """Fit a smooth exposure-vs-depth trajectory from sparse pilot
    acquisitions.

    Returns a callable ``traj(plane_idx: int) -> float`` that evaluates
    the fitted exposure at any plane index in ``[0, n_planes)``.

    Uses ``numpy.polyfit`` with degree ``min(2, n_samples - 1)`` over
    normalized depth (plane_idx / (n_planes - 1)). A low-degree
    polynomial is sufficient for the monotonic-ish iDISCO+ profile and
    avoids overfitting the sparse pilot samples.
    """
    n = len(pilot_indices)
    if n == 0:
        # No pilots — return a flat trajectory at the first exposure
        # (or a sensible default if exposures is also empty).
        base = exposures[0] if exposures else 50e-3
        return lambda plane_idx: base
    # Normalize depth to [0, 1] so the polynomial coefficients are
    # well-conditioned regardless of n_planes.
    x = np.array(
        [idx / max(n_planes - 1, 1) for idx in pilot_indices],
        dtype=float,
    )
    y = np.array(exposures, dtype=float)
    degree = min(2, n - 1)
    coeffs = np.polyfit(x, y, degree)

    def traj(plane_idx: int) -> float:
        t = plane_idx / max(n_planes - 1, 1)
        return float(np.polyval(coeffs, t))

    return traj


# --------------------------------------------------------------------- #
# PI residual with anti-windup
# --------------------------------------------------------------------- #


def pi_residual(
    error: float, integral: float, cfg: AdaptiveConfig
) -> tuple[float, float]:
    """Compute the PI residual delta and the updated integral.

    ``error`` is (observed - target): positive means the frame is
    brighter than the target, so the loop should reduce exposure (or
    power). The proportional term is ``-kp * error`` (negative because
    a positive error → reduce the actuator). The integral accumulates
    ``ki * error`` each step and is added to the delta on subsequent
    calls (the integral removes steady-state offset).

    Anti-windup: the integral is clamped to a finite range derived from
    the configured exposure bounds so a persistent large error cannot
    grow the integral unbounded. The clamp range is the exposure span
    (max_exposure_s - min_exposure_s) — the integral represents an
    exposure-equivalent accumulated correction, so clamping to the
    exposure span bounds it physically.

    Returns ``(delta, new_integral)`` where ``delta`` is the
    proportional correction to apply to the current exposure (in
    seconds), and ``new_integral`` is the updated accumulated integral
    (to pass back on the next call).
    """
    new_integral = integral + cfg.ki * error
    # Anti-windup: clamp the integral to the exposure span (the
    # exposure-equivalent accumulated correction cannot exceed the
    # physical exposure range).
    integral_limit = cfg.max_exposure_s - cfg.min_exposure_s
    new_integral = max(-integral_limit, min(integral_limit, new_integral))
    # Proportional term: negative because positive error (too bright)
    # → reduce exposure. The integral is applied separately by the
    # controller (added to the feedforward baseline) so this function
    # returns only the P-term delta.
    delta = -cfg.kp * error
    return delta, new_integral


# --------------------------------------------------------------------- #
# Re-acquire decision
# --------------------------------------------------------------------- #


def should_reacquire(
    observed: float, expected: float, cfg: AdaptiveConfig
) -> bool:
    """Return True if the observed intensity deviates from the expected
    value by more than ``reacquire_threshold`` (a fraction of the
    sensor range). This handles large excursions — the "wrong frame"
    is re-shot per the operator's vision."""
    return abs(observed - expected) > cfg.reacquire_threshold


# --------------------------------------------------------------------- #
# AdaptiveController
# --------------------------------------------------------------------- #


class AdaptiveController:
    """Per-plane adaptive controller implementing the pilot+PI law.

    Constructed with a frozen ``AdaptiveConfig`` and the total plane
    count. ``prime()`` stores the fitted pilot trajectory;
    ``update()`` is called once per main plane with the observed
    intensities and returns a frozen ``AdaptiveCommand``.

    The controller is pure-Python — it never touches Qt, HAL, or
    hardware. The worker thread reads the returned ``AdaptiveCommand``
    and applies it through the existing safe HAL paths.
    """

    def __init__(self, cfg: AdaptiveConfig, n_planes: int) -> None:
        self._cfg = cfg
        self._n_planes = n_planes
        self._integral = 0.0
        self._pilot_traj: callable | None = None  # type: ignore[type-arg]
        self._reacquire_count = 0

    def prime(
        self, pilot_indices: list[int], pilot_exposures: list[float]
    ) -> None:
        """Store the fitted pilot feedforward trajectory.

        Called after the pilot acquisitions complete and before the
        main per-plane loop begins. The pilot exposures are the
        exposure values that produced the target-band intensity at
        each pilot depth — the feedforward replays them as the
        per-plane baseline, and the PI corrects residual error on top.
        """
        self._pilot_traj = fit_pilot_trajectory(
            pilot_indices, pilot_exposures, self._n_planes
        )

    def update(
        self,
        intensities: list[float],
        brighter_idx: int,
        current_exposure_s: float,
        current_powers_mw: tuple[float, float],
        plane_idx: int,
    ) -> AdaptiveCommand:
        """Compute the next per-plane AdaptiveCommand.

        When adaptive is disabled (``cfg.enabled is False``), returns a
        constant ``AdaptiveCommand.fixed`` equal to the current
        exposure/power — zero extra per-plane actuator writes.

        When enabled:
        1. Feedforward: evaluate the fitted pilot trajectory at this
           plane to get the baseline exposure.
        2. PI residual: compute the error against the target band
           midpoint and apply the PI correction.
        3. D-01 exposure-primary: clamp exposure to bounds; if exposure
           hits a bound and the target is still unmet, switch to power
           fallback.
        4. D-02 cross-channel balance: the brighter channel drives the
           shared exposure; the dimmer channel's power trims toward
           balance. L2 power changes only at block boundaries.
        5. D-03 re-acquire: if the observed intensity deviates sharply
           from the feedforward expectation, flag for re-acquire
           (subject to ``max_reacquire_attempts``).
        """
        cfg = self._cfg

        # Adaptive-off: constant fixed command.
        if not cfg.enabled:
            return AdaptiveCommand.fixed(
                exposure_s=current_exposure_s,
                laser1_mw=current_powers_mw[0],
                laser2_mw=current_powers_mw[1],
            )

        # Feedforward baseline from the pilot trajectory.
        if self._pilot_traj is not None:
            ff_exposure = self._pilot_traj(plane_idx)
        else:
            ff_exposure = current_exposure_s

        # The brighter channel drives the shared exposure. The error
        # is (observed - target_midpoint): positive = too bright →
        # reduce exposure; negative = too dim → increase exposure.
        brighter_intensity = intensities[brighter_idx] if intensities else 0.0
        # Guard against NaN (inactive channel should not be the
        # brighter one, but guard anyway).
        if isinstance(brighter_intensity, float) and math.isnan(brighter_intensity):
            brighter_intensity = 0.0
        error = brighter_intensity - cfg.target_midpoint

        # PI residual correction on top of the feedforward. The P-term
        # delta is scaled relative to the current exposure so the
        # correction is proportional to the exposure magnitude (a 0.4
        # kp on a 0.5 fraction error at 50 ms moves exposure by
        # 0.4 * 0.425 * 50ms ≈ 8.5 ms, not 170 ms). The integral
        # (accumulated and anti-windup-clamped in pi_residual) removes
        # steady-state offset on subsequent planes — it is subtracted
        # because it accumulates ki*error (positive when too bright),
        # so subtracting it pushes exposure down more when consistently
        # too bright and up more when consistently too dim.
        delta, self._integral = pi_residual(error, self._integral, cfg)
        scaled_delta = delta * current_exposure_s
        new_exposure = ff_exposure + scaled_delta - self._integral

        # D-01: clamp exposure first.
        clamped_exposure = cfg.clamp_exposure(new_exposure)
        # Power fallback is active when the CURRENT exposure is already
        # at a bound (can't move further) AND the target is still unmet.
        # This checks current_exposure_s, not the new computed exposure,
        # because the bound condition means the loop has already pushed
        # exposure to its limit on a previous plane — the new exposure
        # might compute below the bound from the feedforward baseline,
        # but the physical exposure is at the limit.
        at_exposure_bound = (
            current_exposure_s <= cfg.min_exposure_s + 1e-12
            or current_exposure_s >= cfg.max_exposure_s - 1e-12
        )
        target_unmet = (
            brighter_intensity < cfg.target_band_lo
            or brighter_intensity > cfg.target_band_hi
        )
        power_fallback = at_exposure_bound and target_unmet

        # Determine the control variable active label.
        control_variable_active = "power" if power_fallback else "exposure"

        # D-02: per-laser power trim.
        # L1 (the brighter channel's laser in single-channel mode, or
        # the brighter channel's laser in multi-channel) trims per-plane
        # when power_fallback is active. L2 trims only at block
        # boundaries.
        is_block_boundary = ((plane_idx + 1) % cfg.block_size_n) == 0
        n_channels = len(intensities)

        if n_channels <= 1:
            # Single-channel: one active laser (L1 by convention).
            # Trim L1 power only on power fallback.
            if power_fallback:
                # Power moves in the direction that reduces the error:
                # too dim (error < 0) → increase power; too bright
                # (error > 0) → decrease power.
                power_delta_mw = -error * cfg.max_power_mw[0] * 0.5
                new_l1 = current_powers_mw[0] + power_delta_mw
            else:
                new_l1 = current_powers_mw[0]
            # L2 is inactive in single-channel mode — hold at current.
            new_l2 = current_powers_mw[1]
        else:
            # Multi-channel: brighter channel drives exposure (above);
            # dimmer channel's power trims toward balance.
            dimmer_idx = 1 - brighter_idx
            dimmer_intensity = (
                intensities[dimmer_idx] if dimmer_idx < len(intensities) else 0.0
            )
            if isinstance(dimmer_intensity, float) and math.isnan(dimmer_intensity):
                dimmer_intensity = 0.0

            # L1 (brighter channel) power: trim only on power fallback.
            if power_fallback:
                brighter_error = brighter_intensity - cfg.target_midpoint
                l1_delta = -brighter_error * cfg.max_power_mw[0] * 0.5
                new_l1 = current_powers_mw[0] + l1_delta
            else:
                new_l1 = current_powers_mw[0]

            # L2 (dimmer channel) power: trim toward balance, but only
            # at block boundaries (D-02). Between boundaries, hold L2.
            if is_block_boundary:
                dimmer_error = dimmer_intensity - cfg.target_midpoint
                l2_delta = -dimmer_error * cfg.max_power_mw[1] * 0.5
                new_l2 = current_powers_mw[1] + l2_delta
            else:
                new_l2 = current_powers_mw[1]

        # Clamp powers to configured bounds.
        clamped_powers = cfg.clamp_power((new_l1, new_l2))

        # D-03: re-acquire decision.
        # The expected intensity is what the feedforward predicts for
        # this depth given the current exposure. The pilot trajectory
        # was fit from exposures that produced the target midpoint at
        # each pilot depth, so the gain at depth t is
        # target / feedforward_exposure(t). With the current exposure,
        # the expected intensity is gain * current_exposure. A sharp
        # deviation from this expectation (not from the target) flags a
        # re-acquire — a gradual profile that matches the pilots has
        # observed ≈ expected at every plane, so no re-acquire fires.
        reacquire = False
        if self._reacquire_count < cfg.max_reacquire_attempts:
            if self._pilot_traj is not None:
                ff_exp = self._pilot_traj(plane_idx)
                if ff_exp > 1e-9:
                    expected = cfg.target_midpoint * (
                        current_exposure_s / ff_exp
                    )
                else:
                    expected = cfg.target_midpoint
            else:
                expected = cfg.target_midpoint
            # Clamp expected to [0, 1] — it's a fraction of sensor max.
            expected = max(0.0, min(1.0, expected))
            if should_reacquire(brighter_intensity, expected, cfg):
                reacquire = True
                self._reacquire_count += 1

        return AdaptiveCommand(
            exposure_s=clamped_exposure,
            laser1_mw=clamped_powers[0],
            laser2_mw=clamped_powers[1],
            reacquire=reacquire,
            control_variable_active=control_variable_active,
            power_fallback=power_fallback,
        )
