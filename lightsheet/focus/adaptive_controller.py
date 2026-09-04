"""Predictive focus controller: FocusCurve feedforward + running residual.

Pure-Python — no Qt, no HAL, no plotting backends.
"""

from __future__ import annotations

import numpy as np

from lightsheet.focus.types import AutofocusConfig, FocusCurve


class AdaptiveFocusController:
    """Feedforward interpolation + one-frame-per-plane residual tracker.

    Constructed with a frozen ``AutofocusConfig``, the camera travel limits,
    an optional ``FocusCurve`` seed, and a constant camera seed position.
    ``target(stage_pos_mm)`` returns the clamped camera focus position for the
    current plane; ``update(stage_pos_mm, sharpness)`` adjusts the residual
    for the next plane from the measured, exposure-normalized sharpness.
    """

    def __init__(
        self,
        cfg: AutofocusConfig,
        cam_lo_mm: float,
        cam_hi_mm: float,
        curve: FocusCurve | None = None,
        seed_camera_pos_mm: float = 0.0,
    ) -> None:
        self._cfg = cfg
        self._cam_lo = cam_lo_mm
        self._cam_hi = cam_hi_mm
        self._curve = curve
        self._seed = seed_camera_pos_mm
        self._residual_mm = 0.0
        self._prev_residual_mm = 0.0
        self._predicted_sharpness: float | None = None

    @property
    def residual_mm(self) -> float:
        """Current residual correction in millimetres (read-only)."""
        return self._residual_mm

    @property
    def has_reference(self) -> bool:
        """A reference sharpness has been acquired and the controller can
        update residuals."""
        return self._predicted_sharpness is not None

    @property
    def residual_unchanged(self) -> bool:
        """The last update produced no residual step."""
        return abs(self._residual_mm - self._prev_residual_mm) < 1e-9

    def feedforward(self, stage_pos_mm: float) -> float:
        """Return the feedforward camera position for this stage position."""
        if self._curve is not None and self._cfg.use_curve_seed:
            return float(
                np.interp(
                    stage_pos_mm,
                    self._curve.stage_pos,
                    self._curve.camera_pos,
                )
            )
        return self._seed

    def target(self, stage_pos_mm: float) -> float:
        """Return the clamped camera focus position for ``stage_pos_mm``."""
        pos = self.feedforward(stage_pos_mm) + self._residual_mm
        return max(self._cam_lo, min(self._cam_hi, pos))

    def update(self, stage_pos_mm: float, sharpness: float) -> None:
        """Update the residual for the next plane from the measured sharpness."""
        _ = stage_pos_mm  # API symmetry with target(); not needed internally.

        if not self._cfg.enabled:
            return

        # First call only stores the reference sharpness.
        if self._predicted_sharpness is None:
            self._predicted_sharpness = sharpness
            return

        # Smooth the reference. ``smoothing`` is the new-sample weight.
        s = (1.0 - self._cfg.smoothing) * self._predicted_sharpness
        s += self._cfg.smoothing * sharpness
        self._predicted_sharpness = s

        error = sharpness - s

        # Deadband: ignore changes within the configured relative threshold.
        # ``residual_gain_mm`` then becomes the maximum step, applied
        # proportionally to the relative deviation outside the deadband.
        threshold = self._cfg.update_threshold
        if threshold > 0.0 and s > 0.0 and abs(error) <= threshold * s:
            self._prev_residual_mm = self._residual_mm
            return

        dr = self._residual_mm - self._prev_residual_mm

        if threshold > 0.0:
            # Proportional step scaled by the relative deviation from the
            # smoothed reference.  This makes the step small when the error is
            # small, eliminating the fixed bang-bang oscillation when the focus
            # is already close.  Cap the scale at 1.0 so the gain is the max.
            scale = 1.0 if s <= 0.0 else min(1.0, abs(error) / s)
        else:
            # Legacy fixed-step mode for threshold == 0.0.
            scale = 1.0

        # If there is no prior residual step to infer an ascent direction from,
        # take a bootstrap step in the direction of the sharpness error.
        direction = np.sign(error) if dr == 0.0 else np.sign(error) * np.sign(dr)

        self._prev_residual_mm = self._residual_mm
        new_residual = (
            self._residual_mm
            + self._cfg.residual_gain_mm * float(direction) * scale
        )
        self._residual_mm = max(
            -self._cfg.max_residual_mm,
            min(self._cfg.max_residual_mm, new_residual),
        )
