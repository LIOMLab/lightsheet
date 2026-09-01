"""Focus controller: feedforward interpolation + per-block residual.

Pure-Python — no Qt, no HAL, no scipy.
"""

from __future__ import annotations

import numpy as np

from lightsheet.focus.types import FocusConfig, FocusCurve


class FocusController:
    """Feedforward interpolation + clamped residual focus controller.

    Constructed with a frozen ``FocusConfig``, a frozen ``FocusCurve``, and
    the camera travel limits. ``target()`` returns the clamped camera focus
    position for a given stage position;
    ``update_residual()`` adjusts the residual based on the per-block sharpness
    metric.
    """

    def __init__(
        self,
        cfg: FocusConfig,
        curve: FocusCurve,
        cam_lo_mm: float,
        cam_hi_mm: float,
    ) -> None:
        self._cfg = cfg
        self._curve = curve
        self._cam_lo = cam_lo_mm
        self._cam_hi = cam_hi_mm
        self._residual_mm = 0.0
        self._reference_sharpness: float | None = None

    @property
    def residual_mm(self) -> float:
        """Current residual correction in millimetres (read-only)."""
        return self._residual_mm

    def target(self, stage_pos_mm: float) -> float:
        """Return the clamped camera focus position for ``stage_pos_mm``."""
        ff = float(
            np.interp(
                stage_pos_mm,
                self._curve.stage_pos,
                self._curve.camera_pos,
            )
        )
        if self._cfg.enabled and self._cfg.autofocus_residual:
            ff = ff + self._residual_mm
        return max(self._cam_lo, min(self._cam_hi, ff))

    def update_residual(self, sharpness_metric: float) -> None:
        """Trim the residual proportional to the sharpness deviation.

        The first call stores the reference sharpness. Subsequent calls compare
        the supplied sharpness to that reference and apply a proportional trim,
        clamped to ``[-max_residual_mm, max_residual_mm]``. When the controller
        is disabled or residual correction is off, the residual is pinned at
        ``0.0``.
        """
        if not self._cfg.enabled or not self._cfg.autofocus_residual:
            return

        if self._reference_sharpness is None:
            self._reference_sharpness = sharpness_metric
            return

        reference = self._reference_sharpness or 1.0
        delta = (
            self._cfg.residual_gain_mm
            * (self._reference_sharpness - sharpness_metric)
            / reference
        )
        new_residual = self._residual_mm + delta
        self._residual_mm = max(
            -self._cfg.max_residual_mm,
            min(self._cfg.max_residual_mm, new_residual),
        )
