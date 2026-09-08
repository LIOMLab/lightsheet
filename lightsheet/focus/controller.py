"""Focus controller: feedforward interpolation + per-block residual.

Pure-Python — no Qt, no HAL, no scipy.
"""

from __future__ import annotations

import math
from typing import Any

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
        initial_state: dict[str, Any] | None = None,
    ) -> None:
        self._cfg = cfg
        self._curve = curve
        self._cam_lo = cam_lo_mm
        self._cam_hi = cam_hi_mm
        self._residual_mm = 0.0
        self._reference_sharpness: float | None = None
        self._last_command: float | None = None
        if initial_state is not None:
            self.restore(initial_state)

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
        applied = max(self._cam_lo, min(self._cam_hi, ff))
        # Record the last applied camera position so a checkpoint can carry
        # the most recent command across a resume.
        self._last_command = applied
        return applied

    def checkpoint(self) -> dict[str, Any]:
        """Return a JSON-safe dict of the controller's internal state.

        Captures the residual, the reference sharpness, and the last
        applied camera position so a resumed acquisition can continue the
        focus-compensation trajectory instead of resetting to zero.
        """
        return {
            "controller": "focus",
            "residual_mm": float(self._residual_mm),
            "reference_sharpness": (
                None
                if self._reference_sharpness is None
                else float(self._reference_sharpness)
            ),
            "last_command": (
                None if self._last_command is None else float(self._last_command)
            ),
        }

    def restore(self, state: dict[str, Any]) -> None:
        """Reinstate controller state from a checkpoint dict.

        Validates every field before mutating internal state: numeric
        values must be finite, the residual must stay inside the
        configured ``max_residual_mm`` bound, and the last command must
        stay inside the camera travel range. Raises ``ValueError`` on
        malformed or out-of-range input so a corrupted or forged manifest
        cannot move the camera focus motor past its limits. Unknown keys
        (e.g. manifest row metadata) are ignored.
        """
        if not isinstance(state, dict):
            raise ValueError(f"checkpoint state must be a dict; got {type(state)}")

        raw_residual = state.get("residual_mm", 0.0)
        if not isinstance(raw_residual, (int, float)) or isinstance(raw_residual, bool):
            raise ValueError(f"residual_mm must be a number; got {type(raw_residual)}")
        if not math.isfinite(raw_residual):
            raise ValueError(f"residual_mm must be finite; got {raw_residual}")
        residual = float(raw_residual)
        if abs(residual) > self._cfg.max_residual_mm + 1e-9:
            raise ValueError(
                f"residual_mm {residual} outside configured bound "
                f"[{-self._cfg.max_residual_mm}, {self._cfg.max_residual_mm}]"
            )

        raw_ref = state.get("reference_sharpness")
        reference: float | None = None
        if raw_ref is not None:
            if not isinstance(raw_ref, (int, float)) or isinstance(raw_ref, bool):
                raise ValueError(
                    f"reference_sharpness must be a number or None; got {type(raw_ref)}"
                )
            if not math.isfinite(raw_ref):
                raise ValueError(f"reference_sharpness must be finite; got {raw_ref}")
            reference = float(raw_ref)

        raw_last = state.get("last_command")
        last_command: float | None = None
        if raw_last is not None:
            if not isinstance(raw_last, (int, float)) or isinstance(raw_last, bool):
                raise ValueError(
                    f"last_command must be a number or None; got {type(raw_last)}"
                )
            if not math.isfinite(raw_last):
                raise ValueError(f"last_command must be finite; got {raw_last}")
            last_command = float(raw_last)
            tol = 1e-6
            if not (self._cam_lo - tol <= last_command <= self._cam_hi + tol):
                raise ValueError(
                    f"last_command {last_command} outside camera travel range "
                    f"[{self._cam_lo}, {self._cam_hi}] mm"
                )

        self._residual_mm = residual
        self._reference_sharpness = reference
        self._last_command = last_command

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
