"""Adaptive controller: pilot feedforward + per-plane PI residual +
power fallback + cross-channel balance + re-acquire decision.

Pure-Python — no Qt, no HAL, no scipy. The control law is P+I (D=0 to
avoid noise amplification). The pilot trajectory fit uses
``numpy.polyfit`` (degree 1-2); the iDISCO+ profile is monotonic-ish so
a low-degree polynomial is sufficient.
"""

from __future__ import annotations

import math
from collections.abc import Callable

import numpy as np

from lightsheet.adaptive.types import AdaptiveCommand, AdaptiveConfig

# --------------------------------------------------------------------- #
# Pilot feedforward trajectory fit
# --------------------------------------------------------------------- #


def fit_pilot_trajectory(
    pilot_indices: list[int],
    exposures: list[float],
    n_planes: int,
) -> Callable[[int], float]:
    """Fit a smooth exposure-vs-depth trajectory from sparse pilot samples.

    Returns ``traj(plane_idx) -> float`` evaluating the fitted exposure
    at any plane index in ``[0, n_planes)``.
    """
    n = len(pilot_indices)
    if n == 0:
        base = exposures[0] if exposures else 50e-3
        return lambda plane_idx: base
    # Normalize depth to [0, 1] for well-conditioned coefficients.
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

    ``error`` is (observed - target): positive means too bright, so the
    loop reduces exposure/power. Anti-windup clamps the integral to the
    exposure span so a persistent large error cannot grow it unbounded.

    Unit convention (intentional, not a bug): the P-term delta returned
    here is a dimensionless fraction (``-kp * error``); the caller in
    ``AdaptiveController.update`` scales it by the current exposure
    (``scaled_delta = delta * current_exposure_s``) so the proportional
    correction is proportional to the exposure level. The integral is
    NOT scaled by exposure at the subtraction site — it accumulates
    ``ki * error`` (dimensionless fraction x gain) and is subtracted
    directly from exposure in seconds. The anti-windup limit
    (``max_exposure_s - min_exposure_s``) treats the integral as having
    units of seconds, so ``ki`` is tuned so that ``ki * error`` lands in
    the right exposure-second magnitude. The practical consequence: the
    integral's relative contribution to the exposure correction varies
    with the current exposure level — at low exposure the integral
    dominates, at high exposure the P-term dominates. This is the
    intended tuning; ``ki`` is small (0.05) so the integral acts as a
    slow steady-state trim rather than a fast correction. Scaling the
    integral by exposure (matching the P-term) would change the loop
    response and require re-tuning ``ki`` and re-validating the pilot
    trajectory — do not change this without operator sign-off.
    """
    new_integral = integral + cfg.ki * error
    # Anti-windup: clamp the integral to the exposure span.
    integral_limit = cfg.max_exposure_s - cfg.min_exposure_s
    new_integral = max(-integral_limit, min(integral_limit, new_integral))
    # P-term delta (negative: positive error → reduce exposure).
    delta = -cfg.kp * error
    return delta, new_integral


# --------------------------------------------------------------------- #
# Re-acquire decision
# --------------------------------------------------------------------- #


def should_reacquire(observed: float, expected: float, cfg: AdaptiveConfig) -> bool:
    """True if observed intensity deviates from expected by more than
    ``reacquire_threshold`` (a fraction of the sensor range)."""
    return abs(observed - expected) > cfg.reacquire_threshold


# --------------------------------------------------------------------- #
# AdaptiveController
# --------------------------------------------------------------------- #


class AdaptiveController:
    """Per-plane adaptive controller implementing the pilot+PI law.

    Constructed with a frozen ``AdaptiveConfig`` and the total plane
    count. ``prime()`` stores the fitted pilot trajectory;
    ``update()`` is called once per main plane and returns a frozen
    ``AdaptiveCommand``. Pure-Python — never touches Qt, HAL, or
    hardware.
    """

    def __init__(self, cfg: AdaptiveConfig, n_planes: int) -> None:
        self._cfg = cfg
        self._n_planes = n_planes
        self._integral = 0.0
        self._pilot_traj: Callable[[int], float] | None = None
        self._reacquire_count = 0

    def prime(self, pilot_indices: list[int], pilot_exposures: list[float]) -> None:
        """Store the fitted pilot feedforward trajectory."""
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

        When disabled, returns a constant fixed command. When enabled:
        feedforward baseline from pilot trajectory, PI residual
        correction, exposure-primary clamping with power fallback at
        bounds, cross-channel balance (brighter drives exposure,
        dimmer trims power), and re-acquire on sharp deviation.
        """
        cfg = self._cfg

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

        # The brighter channel drives the shared exposure.
        brighter_intensity = intensities[brighter_idx] if intensities else 0.0
        # Guard against NaN.
        if isinstance(brighter_intensity, float) and math.isnan(brighter_intensity):
            brighter_intensity = 0.0
        error = brighter_intensity - cfg.target_midpoint

        # PI residual: P-term delta scaled relative to current exposure;
        # integral removes steady-state offset.
        delta, self._integral = pi_residual(error, self._integral, cfg)
        scaled_delta = delta * current_exposure_s
        new_exposure = ff_exposure + scaled_delta - self._integral

        # Clamp exposure first.
        clamped_exposure = cfg.clamp_exposure(new_exposure)
        # Power fallback when current exposure is at a bound and target
        # is still unmet — checks current_exposure_s (the physical limit),
        # not the newly computed value.
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

        # Per-laser power trim: L1 trims per-plane on power fallback;
        # L2 trims only at block boundaries.
        is_block_boundary = ((plane_idx + 1) % cfg.block_size_n) == 0
        n_channels = len(intensities)

        if n_channels <= 1:
            # Single-channel: trim L1 power only on power fallback.
            if power_fallback:
                power_delta_mw = -error * cfg.max_power_mw[0] * 0.5
                new_l1 = current_powers_mw[0] + power_delta_mw
            else:
                new_l1 = current_powers_mw[0]
            new_l2 = current_powers_mw[1]
        else:
            # Multi-channel: the BRIGHTER channel drives the shared
            # exposure, so on power fallback its power is the one to
            # trim (trimming the dimmer channel would not bring the
            # brighter one into the target band). The dimmer channel
            # trims toward balance at block boundaries only.
            brighter_max = cfg.max_power_mw[brighter_idx]
            if power_fallback:
                brighter_error = brighter_intensity - cfg.target_midpoint
                brighter_delta = -brighter_error * brighter_max * 0.5
                new_brighter_power = current_powers_mw[brighter_idx] + brighter_delta
            else:
                new_brighter_power = current_powers_mw[brighter_idx]

            # The dimmer channel is the other active channel. For the
            # current 2-channel system it is ``1 - brighter_idx``; the
            # guard below picks the dimmest remaining channel if a
            # third channel is ever added (latent-bug guard, WR-03).
            if n_channels == 2:
                dimmer_idx = 1 - brighter_idx
            else:
                dimmer_idx = min(
                    (i for i in range(n_channels) if i != brighter_idx),
                    key=lambda i: intensities[i] if i < len(intensities) else 0.0,
                    default=brighter_idx,
                )
            dimmer_intensity = (
                intensities[dimmer_idx] if dimmer_idx < len(intensities) else 0.0
            )
            if isinstance(dimmer_intensity, float) and math.isnan(dimmer_intensity):
                dimmer_intensity = 0.0

            # Dimmer channel power: trim toward balance at block
            # boundaries only. Guard the max_power_mw / current_powers_mw
            # lookups against dimmer_idx >= len(...) — the system is
            # currently 2-channel only (max_power_mw is a 2-tuple), but
            # the dimmer_idx fallback above can pick index >= 2 if a
            # third channel is ever added without also extending
            # max_power_mw. Fall back to channel 0's bounds in that case
            # rather than raising IndexError mid-loop.
            dimmer_max = (
                cfg.max_power_mw[dimmer_idx]
                if dimmer_idx < len(cfg.max_power_mw)
                else cfg.max_power_mw[0]
            )
            dimmer_current = (
                current_powers_mw[dimmer_idx]
                if dimmer_idx < len(current_powers_mw)
                else current_powers_mw[0]
            )
            if is_block_boundary:
                dimmer_error = dimmer_intensity - cfg.target_midpoint
                dimmer_delta = -dimmer_error * dimmer_max * 0.5
                new_dimmer_power = dimmer_current + dimmer_delta
            else:
                new_dimmer_power = dimmer_current

            # Assign the computed powers back to the correct laser
            # slots (L1 = index 0, L2 = index 1).
            if brighter_idx == 0:
                new_l1 = new_brighter_power
                new_l2 = new_dimmer_power
            else:
                new_l1 = new_dimmer_power
                new_l2 = new_brighter_power

        # Clamp powers to configured bounds.
        clamped_powers = cfg.clamp_power((new_l1, new_l2))

        # Re-acquire decision: expected intensity is gain * current_exposure
        # where gain = target / feedforward_exposure. A sharp deviation
        # from this expectation (not from target) flags re-acquire. The
        # expected value is computed and the deviation tested even after
        # the attempt cap is reached so a CONTINUING sharp deviation
        # surfaces reacquire_exhausted=True (the controller has spent its
        # re-acquire budget and the latest observation still deviates).
        reacquire = False
        reacquire_exhausted = False
        if self._pilot_traj is not None:
            ff_exp = self._pilot_traj(plane_idx)
            if ff_exp > 1e-9:
                expected = cfg.target_midpoint * (current_exposure_s / ff_exp)
            else:
                expected = cfg.target_midpoint
        else:
            expected = cfg.target_midpoint
        # Clamp expected to [0, 1] — it's a fraction of sensor max.
        expected = max(0.0, min(1.0, expected))
        if should_reacquire(brighter_intensity, expected, cfg):
            if self._reacquire_count < cfg.max_reacquire_attempts:
                # Under the cap: request a re-acquire and consume one
                # attempt.
                reacquire = True
                self._reacquire_count += 1
            else:
                # Cap reached but the deviation persists: surface
                # exhaustion so the worker emits the operator message.
                # Do NOT request another re-acquire (the budget is
                # spent).
                reacquire_exhausted = True

        return AdaptiveCommand(
            exposure_s=clamped_exposure,
            laser1_mw=clamped_powers[0],
            laser2_mw=clamped_powers[1],
            reacquire=reacquire,
            control_variable_active=control_variable_active,
            power_fallback=power_fallback,
            reacquire_exhausted=reacquire_exhausted,
        )
