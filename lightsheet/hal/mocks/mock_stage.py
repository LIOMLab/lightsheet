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
from scipy.ndimage import gaussian_filter

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
    # Sample-lensing focus model: the ideal camera focus plane sits at
    # ``light_sheet_x_mm + lensing_shift(h)`` where ``lensing_shift`` is a
    # small Gaussian bump of the axial sample position (peak
    # ``lensing_amplitude_mm`` at ``center_x_mm``, width
    # ``lensing_sigma_mm``). Camera defocus in mm maps to a 2D Gaussian
    # PSF sigma in pixels via ``defocus_scale`` (fraction of the
    # defocus-in-pixels to use), capped at ``max_blur_sigma_px`` so the
    # per-plane blur stays inside the demo timing budget (~21 ms at
    # sigma=2 on the 1500x1500 demo default). ``blur_deadband_mm``
    # skips the blur entirely for near-focus planes (~2 ms path).
    lensing_amplitude_mm: float = 0.3
    lensing_sigma_mm: float = 2.0
    defocus_scale: float = 0.02
    max_blur_sigma_px: float = 2.0
    blur_deadband_mm: float = 0.02
    # Deterministic high-frequency sample texture: a zero-mean
    # sinusoidal grid modulated by the Gaussian envelope
    # (``lateral * (1 + texture_amplitude * sin(...) * sin(...))``).
    # The smooth envelope alone yields almost no
    # ``frame_sharpness_variance`` gradient under a few-px PSF blur —
    # variance is a global statistic, so blurring a broad Gaussian
    # barely changes it. The texture adds high-frequency energy that
    # the defocus blur removes, producing a strong, monotonic
    # sharpness-vs-defocus signal for the focus residual. Fully
    # deterministic (closed-form, no RNG) so frames stay bit-exact.
    # ``texture_period_px`` is the grid period in sensor pixels.
    texture_amplitude: float = 0.5
    texture_period_px: float = 4.0

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
        if self.lensing_sigma_mm <= 0:
            raise ValueError(
                f"lensing_sigma_mm must be positive, got {self.lensing_sigma_mm}"
            )
        if self.texture_period_px <= 0:
            raise ValueError(
                f"texture_period_px must be positive, got {self.texture_period_px}"
            )
        for name in (
            "lensing_amplitude_mm",
            "defocus_scale",
            "max_blur_sigma_px",
            "blur_deadband_mm",
            "texture_amplitude",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be >= 0, got {getattr(self, name)}")


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

        # Camera-defocus blur: convolve the cached lateral slice with a
        # 2D Gaussian PSF whose sigma grows with the distance between the
        # camera focus position and the (lensing-shifted) ideal focus.
        # gaussian_filter returns a fresh array, so the cached profile
        # is never mutated. The blur is applied to the unscaled density
        # before the peak_density * power * exposure scaling.
        blur_sigma_px = self._defocus_sigma_px(cam_mm, h_mm)
        if blur_sigma_px > 0.0:
            lateral = gaussian_filter(lateral, blur_sigma_px, mode="nearest")

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
        land on the sensor centre. A deterministic zero-mean sinusoidal
        texture modulates the envelope when ``texture_amplitude`` > 0 so
        the defocus blur has high-frequency energy to remove (without
        it, blurring a smooth Gaussian barely moves the frame's
        variance). Cached on the geometry + texture parameters so the
        per-plane cost stays ~2 ms.
        """
        sample = self.sample
        key = (
            tuple(sample.sensor_shape),
            sample.sigma_y_mm,
            sample.sigma_z_mm,
            sample.texture_amplitude,
            sample.texture_period_px,
        )
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
            if sample.texture_amplitude > 0:
                k = 2.0 * math.pi / sample.texture_period_px
                texture = np.sin(k * np.arange(rows))[:, None] * np.sin(
                    k * np.arange(cols)
                )[None, :]
                profile = profile * (1.0 + sample.texture_amplitude * texture)
            self._lateral_key = key
            self._lateral_profile = profile
        return self._lateral_profile

    def _ideal_focus_mm(self, h_mm: float) -> float:
        """Ideal camera focus position for a given axial sample position.

        The static light sheet sits at ``light_sheet_x_mm``; the sample
        lenses the sheet slightly, shifting the ideal focus plane by a
        small Gaussian bump centred on the sample's axial centre.
        """
        sample = self.sample
        shift = sample.lensing_amplitude_mm * math.exp(
            -((h_mm - sample.center_x_mm) ** 2) / (2 * sample.lensing_sigma_mm**2)
        )
        return sample.light_sheet_x_mm + shift

    def _defocus_sigma_px(self, cam_mm: float, h_mm: float) -> float:
        """Map camera defocus (mm) to a 2D Gaussian PSF sigma in pixels.

        Returns ``0.0`` inside the deadband and for blur sigmas too small
        to matter (~0.3 px), so in-focus planes keep the ~2 ms unblurred
        path. Larger defocus maps linearly to sigma via
        ``defocus_scale``, hard-capped at ``max_blur_sigma_px`` so the
        per-plane cost stays inside the demo timing budget.
        """
        sample = self.sample
        defocus_mm = abs(cam_mm - self._ideal_focus_mm(h_mm))
        if defocus_mm < sample.blur_deadband_mm:
            return 0.0
        sigma_px = defocus_mm * 1000.0 / sample.pixel_size_um * sample.defocus_scale
        sigma_px = min(sigma_px, sample.max_blur_sigma_px)
        if sigma_px <= 0.3:
            return 0.0
        return sigma_px
