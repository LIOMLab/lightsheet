"""Synthetic sample/stage world model for demo and test acquisitions.

``MockSample`` is a frozen parameter bundle describing an anisotropic
Gaussian ellipsoid sample and the static light sheet it moves through.
``MockStage`` reads live motor positions and laser state at
frame-generation time and returns a floating-point density frame via
``frame(camera, plane_index)`` — the ``MockCamera.frame_source``
contract. ``MockCamera.copy_recorder_images`` owns the uint16
conversion.

Model scope (demo/test only):

- The sample moves through a STATIC light sheet fixed at
  ``light_sheet_x_mm`` in stage coordinates — stage frame, not beam
  frame.
- ETL/ASLM horizontal beam-waist scanning is intentionally not
  modelled; the sheet thickness is a fixed Gaussian.
- All math is closed-form numpy — deterministic, no RNG, no
  time-dependence — so test output is reproducible.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# Gaussian FWHM -> sigma conversion (2*sqrt(2*ln 2)).
_FWHM_TO_SIGMA = 2.3548200450309493


@dataclass(frozen=True)
class MockSample:
    """Physical and illumination parameters of the synthetic sample.

    All positions are in millimetres; sizes marked ``_um`` are in
    micrometres. The defaults describe a sample centred at 8.5 mm on
    the horizontal (stack) axis — the middle of the real sample's
    3-14 mm horizontal span — with a static light sheet at the same
    position.
    """

    center_x_mm: float = 8.5
    center_y_mm: float = 0.0
    center_z_mm: float = 0.0
    # Small axial sigma so the 3-14 mm horizontal sweep produces a
    # strong intensity gradient through the sheet.
    sigma_x_mm: float = 2.5
    # Large lateral sigmas so the projected half-max cross-section
    # covers ~75 % of the default 2048-px FOV (2048 px x 6.5 µm
    # = 13.312 mm).
    sigma_y_mm: float = 4.2
    sigma_z_mm: float = 4.2
    # Tuned so the brightest slice's p99 lands in the 0.90-0.95
    # sensor_max band at exposure_time = 0.1 s and full laser power.
    peak_density: float = 9.4
    light_sheet_x_mm: float = 8.5
    # mesoSPIM DSLM/ASLM axial resolution (~5.6-6.5 µm FWHM, Voigt et
    # al. 2019). Sheet sigma = fwhm * 1e-3 / 2.355 mm.
    light_sheet_fwhm_um: float = 6.0
    pixel_size_um: float = 6.5
    sensor_shape: tuple[int, int] = (2048, 2048)

    def __post_init__(self) -> None:
        """Reject ill-formed parameters — a non-positive sigma or pixel
        size would silently produce a degenerate or inverted profile."""
        for name in ("sigma_x_mm", "sigma_y_mm", "sigma_z_mm"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive, got {getattr(self, name)}")
        if self.pixel_size_um <= 0:
            raise ValueError(
                f"pixel_size_um must be positive, got {self.pixel_size_um}"
            )
        if self.light_sheet_fwhm_um <= 0:
            raise ValueError(
                f"light_sheet_fwhm_um must be positive, got {self.light_sheet_fwhm_um}"
            )
        if len(self.sensor_shape) != 2 or any(s <= 0 for s in self.sensor_shape):
            raise ValueError(
                f"sensor_shape must be two positive ints, got {self.sensor_shape}"
            )


class MockStage:
    """World model binding a ``MockSample`` to live motor/laser state.

    NOT a HAL device — a plain object holding ``Any``-typed handles to
    the mock motors and lasers. ``frame()`` reads positions and laser
    state at call time and never mutates them.
    """

    def __init__(self, sample: MockSample, motors: Any, lasers: tuple) -> None:
        self.sample = sample
        self.motors = motors
        self.lasers = lasers
        self._lateral_key: tuple | None = None
        self._lateral_profile: np.ndarray | None = None

    def frame(self, camera: Any, plane_index: int) -> np.ndarray:
        """Return the float density frame for the current stage state.

        Reads ``motors.horizontal`` / ``motors.camera`` positions (mm),
        the first active laser's ``power / max_power`` fraction, and
        ``camera.exposure_time`` at call time. The caller (MockCamera)
        owns conversion to uint16.
        """
        sample = self.sample
        h_mm = float(self.motors.horizontal.get_position("mm"))
        cam_mm = float(self.motors.camera.get_position("mm"))

        power_frac = self._active_power_fraction()

        # Finite-thickness sheet: convolving the sample's axial Gaussian
        # with the sheet's Gaussian profile yields an effective slice
        # whose amplitude is Gaussian in (h - sheet_x) with the
        # quadrature-combined sigma.
        sigma_sheet_mm = sample.light_sheet_fwhm_um * 1e-3 / _FWHM_TO_SIGMA
        sigma_eff = math.sqrt(sample.sigma_x_mm**2 + sigma_sheet_mm**2)
        axial = math.exp(-((h_mm - sample.light_sheet_x_mm) ** 2) / (2 * sigma_eff**2))

        lateral = self._lateral()

        # Extension seam for camera-defocus blur: a future sigma > 0
        # blurs the lateral slice before scaling. Currently always 0.
        blur_sigma_px = self._defocus_sigma_px(cam_mm, h_mm)
        if blur_sigma_px > 0.0:
            from scipy.ndimage import gaussian_filter

            lateral = gaussian_filter(lateral, blur_sigma_px)

        exposure_s = float(getattr(camera, "exposure_time", 0.0))
        return sample.peak_density * lateral * axial * power_frac * exposure_s

    def _active_power_fraction(self) -> float:
        """Return the first active laser's power fraction, else 0.0."""
        for laser in self.lasers:
            if getattr(laser, "active", False):
                max_power = float(getattr(laser, "max_power", 0.0))
                if max_power <= 0:
                    return 0.0
                return float(getattr(laser, "power", 0.0)) / max_power
        return 0.0

    def _lateral(self) -> np.ndarray:
        """2D anisotropic Gaussian over the sensor, centred on the sample.

        Sensor rows map to the sample y axis and columns to the z axis,
        scaled by ``pixel_size_um``; ``center_y_mm`` / ``center_z_mm``
        land on the sensor centre. Cached on
        ``(sensor_shape, sigma_y_mm, sigma_z_mm)`` so the per-plane cost
        stays ~2 ms.
        """
        sample = self.sample
        key = (tuple(sample.sensor_shape), sample.sigma_y_mm, sample.sigma_z_mm)
        if self._lateral_key != key or self._lateral_profile is None:
            rows, cols = sample.sensor_shape
            pixel_mm = sample.pixel_size_um * 1e-3
            y = (np.arange(rows) - (rows - 1) / 2.0) * pixel_mm
            z = (np.arange(cols) - (cols - 1) / 2.0) * pixel_mm
            dy = y - sample.center_y_mm
            dz = z - sample.center_z_mm
            profile = np.exp(
                -(
                    (dy[:, None] ** 2) / (2 * sample.sigma_y_mm**2)
                    + (dz[None, :] ** 2) / (2 * sample.sigma_z_mm**2)
                )
            )
            self._lateral_key = key
            self._lateral_profile = profile
        return self._lateral_profile

    def _defocus_sigma_px(self, cam_mm: float, h_mm: float) -> float:
        """Camera-defocus blur sigma in pixels. Always 0.0 for now —
        the blur model lands in a later change without altering the
        ``frame()`` signature."""
        return 0.0
