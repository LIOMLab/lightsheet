"""
Two-tier pydantic-settings config schema — layers validation ON TOP
of the existing cfg_read/cfg_write configparser helpers.

The strict baseline tier (extra='forbid') rejects unknown/typo'd keys
instead of silently falling into the configparser fallback. The lax overlay
tier (extra='ignore') tolerates extra keys in the rig-specific overlay so rig
calibration freedom is preserved.

Safety-critical keys ([iBeam] Max Power <= 150000 uW, [Motors] * Limit High
<= their mechanical limits) are REJECTED (not clamped) out-of-range in BOTH
tiers via the same field_validator — a tampered overlay cannot bypass the
same check that guards the tracked baseline.

Non-safety out-of-range values are collected as WARNings by the collect-all
entry point AFTER construction succeeds — they do NOT raise ValidationError.

settings_customise_sources returns ONLY the init (kwargs) source — no
environment-variable source, no dotenv source.

case_sensitive=True + Field(alias="<Exact INI Key>") + populate_by_name=True
preserves the case-sensitive Title-Case INI key contract — a typo'd key is
rejected, not silently lowercased and accepted.
"""

import configparser
import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, ValidationError, field_validator
from pydantic.fields import FieldInfo
from pydantic_core.core_schema import ValidationInfo
from pydantic_settings import BaseSettings, SettingsConfigDict

from lightsheet.config import cfg_read

logger = logging.getLogger(__name__)

# --- Safety-critical constants ---
# iBeam Smart 640 hard limit: 150 mW = 150000 uW. The schema validates Max
# Power, not wavelength — 640 nm is the physical diode emission peak; 647 nm
# is the recorded capture/detection wavelength.
_IBEAM_MAX_MW: int = 150000  # uW

# Zaber T-LS mechanical travel limits. A stage driven past mechanical limits
# damages hardware.
_MOTORS_VERTICAL_LIMIT_HIGH_MM: float = 41.0
_MOTORS_HORIZONTAL_LIMIT_HIGH_MM: float = 18.8
_MOTORS_CAMERA_LIMIT_HIGH_MM: float = 35.0

# --- Non-safety recommended ranges (WARN, not REJECT) ---
_GALVO_VOLTAGE_LIMIT: float = 10.0  # ±10 V NI-6363 AO range
# ETL drive is a 0-5 V analog input to the EL-10-30 lens driver, which maps
# it to its 0-292.84 mA coil-current range internally. The config [SigGen]
# ETL Amplitude values are volts (the DAQ AO drive), so the warn check
# compares volts against the 5 V analog input range.
_ETL_VOLTAGE_LIMIT: float = 5.0  # 0-5 V Optotune EL-10-30 analog input


# ---------------------------------------------------------------------------
# Shared base — provides settings_customise_sources so no environment or
# dotenv source is ever registered. Each per-section model declares its own
# model_config with the tier-appropriate extra policy.
# ---------------------------------------------------------------------------


class _NoEnvBaseSettings(BaseSettings):
    """BaseSettings that reads ONLY the init (kwargs) source — no
    environment-variable, dotenv, or file-secret source."""

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: Any,
        env_settings: Any,
        dotenv_settings: Any,
        file_secret_settings: Any,
    ) -> tuple[Any, ...]:
        return (init_settings,)


# ---------------------------------------------------------------------------
# Safety-key field validators — applied to BOTH tiers (a tampered overlay
# cannot bypass the same check that guards the tracked baseline).
# ---------------------------------------------------------------------------


def _validate_ibeam_max_power(v: int) -> int:
    if v > _IBEAM_MAX_MW:
        raise ValueError(
            f"Max Power {v} uW exceeds iBeam hard limit {_IBEAM_MAX_MW} uW (150 mW)"
        )
    return v


def _validate_vertical_limit_high(v: float) -> float:
    if v > _MOTORS_VERTICAL_LIMIT_HIGH_MM:
        raise ValueError(
            f"Vertical Limit High {v} mm exceeds mechanical travel limit "
            f"{_MOTORS_VERTICAL_LIMIT_HIGH_MM} mm"
        )
    return v


def _validate_horizontal_limit_high(v: float) -> float:
    if v > _MOTORS_HORIZONTAL_LIMIT_HIGH_MM:
        raise ValueError(
            f"Horizontal Limit High {v} mm exceeds mechanical travel limit "
            f"{_MOTORS_HORIZONTAL_LIMIT_HIGH_MM} mm"
        )
    return v


def _validate_camera_limit_high(v: float) -> float:
    if v > _MOTORS_CAMERA_LIMIT_HIGH_MM:
        raise ValueError(
            f"Camera Limit High {v} mm exceeds mechanical travel limit "
            f"{_MOTORS_CAMERA_LIMIT_HIGH_MM} mm"
        )
    return v


# ---------------------------------------------------------------------------
# Per-section models. Field aliases match config.ini's verbatim key casing.
# One strict (extra='forbid') + one overlay (extra='ignore') subclass per
# section.
# ---------------------------------------------------------------------------


class ControllerSettings(_NoEnvBaseSettings):
    model_config = SettingsConfigDict(
        extra="forbid", case_sensitive=True, populate_by_name=True
    )
    units: str = Field(alias="Units")
    # Image File Format — the persisted default save format loaded at
    # startup. The before-validator lowercases so the rig's Title-Case
    # config.ini values are accepted, and maps the "" sentinel (a key
    # absent from config.ini arrives as "" via load_sections_from_ini)
    # to "hdf5" (the operator-facing default).
    image_file_format: Literal["hdf5", "zarr", "both", "tiff"] = Field(
        alias="Image File Format", default="both"
    )
    # Theme — the persisted UI theme override. The before-validator
    # lowercases and maps "" to "system".
    theme: Literal["light", "dark", "system"] = Field(alias="Theme", default="system")

    @field_validator("image_file_format", mode="before")
    @classmethod
    def _lowercase_image_file_format(cls, v: Any) -> Any:
        if isinstance(v, str):
            if v == "":
                return "hdf5"
            return v.lower()
        return v

    @field_validator("theme", mode="before")
    @classmethod
    def _lowercase_theme(cls, v: Any) -> Any:
        if isinstance(v, str):
            if v == "":
                return "system"
            return v.lower()
        return v


class ControllerSettingsOverlay(_NoEnvBaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore", case_sensitive=True, populate_by_name=True
    )
    units: str = Field(alias="Units")
    image_file_format: Literal["hdf5", "zarr", "both", "tiff"] = Field(
        alias="Image File Format", default="both"
    )
    theme: Literal["light", "dark", "system"] = Field(alias="Theme", default="system")

    @field_validator("image_file_format", mode="before")
    @classmethod
    def _lowercase_image_file_format(cls, v: Any) -> Any:
        if isinstance(v, str):
            if v == "":
                return "hdf5"
            return v.lower()
        return v

    @field_validator("theme", mode="before")
    @classmethod
    def _lowercase_theme(cls, v: Any) -> Any:
        if isinstance(v, str):
            if v == "":
                return "system"
            return v.lower()
        return v


class CameraSettings(_NoEnvBaseSettings):
    model_config = SettingsConfigDict(
        extra="forbid", case_sensitive=True, populate_by_name=True
    )
    shutter_mode: str = Field(alias="Shutter Mode")
    exposure_time: float = Field(alias="Exposure Time")
    lightsheet_line_time: float = Field(alias="Lightsheet Line Time")
    lightsheet_exposed_lines: int = Field(alias="Lightsheet Exposed Lines")
    lightsheet_delay_lines: int = Field(alias="Lightsheet Delay Lines")
    recorder_timeout: float = Field(alias="Recorder Timeout")
    recorder_timeout_floor: float = Field(alias="Recorder Timeout Floor")
    recorder_timeout_safety_factor: float = Field(
        alias="Recorder Timeout Safety Factor"
    )


class CameraSettingsOverlay(_NoEnvBaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore", case_sensitive=True, populate_by_name=True
    )
    shutter_mode: str = Field(alias="Shutter Mode")
    exposure_time: float = Field(alias="Exposure Time")
    lightsheet_line_time: float = Field(alias="Lightsheet Line Time")
    lightsheet_exposed_lines: int = Field(alias="Lightsheet Exposed Lines")
    lightsheet_delay_lines: int = Field(alias="Lightsheet Delay Lines")
    recorder_timeout: float = Field(alias="Recorder Timeout")
    recorder_timeout_floor: float = Field(alias="Recorder Timeout Floor")
    recorder_timeout_safety_factor: float = Field(
        alias="Recorder Timeout Safety Factor"
    )


class SigGenSettings(_NoEnvBaseSettings):
    model_config = SettingsConfigDict(
        extra="forbid", case_sensitive=True, populate_by_name=True
    )
    ao_terminals: str = Field(alias="AO Terminals")
    do_terminals: str = Field(alias="DO Terminals")
    sample_rate: int = Field(alias="Sample Rate")
    galvo_pre_time: float = Field(alias="Galvo Pre Time")
    galvo_scan_time: float = Field(alias="Galvo Scan Time")
    galvo_reset_time: float = Field(alias="Galvo Reset Time")
    galvo_post_time: float = Field(alias="Galvo Post Time")
    galvo_activated: bool = Field(alias="Galvo Activated")
    galvo_inverted: bool = Field(alias="Galvo Inverted")
    galvo_left_amplitude: float = Field(alias="Galvo Left Amplitude")
    galvo_left_offset: float = Field(alias="Galvo Left Offset")
    galvo_right_amplitude: float = Field(alias="Galvo Right Amplitude")
    galvo_right_offset: float = Field(alias="Galvo Right Offset")
    etl_activated: bool = Field(alias="ETL Activated")
    etl_steps: int = Field(alias="ETL Steps")
    etl_left_amplitude: float = Field(alias="ETL Left Amplitude")
    etl_left_offset: float = Field(alias="ETL Left Offset")
    etl_right_amplitude: float = Field(alias="ETL Right Amplitude")
    etl_right_offset: float = Field(alias="ETL Right Offset")
    # Default False so a missing key does not break existing configs.
    galvo_left_right_swap: bool = Field(alias="Galvo Left Right Swap", default=False)


class SigGenSettingsOverlay(_NoEnvBaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore", case_sensitive=True, populate_by_name=True
    )
    ao_terminals: str = Field(alias="AO Terminals")
    do_terminals: str = Field(alias="DO Terminals")
    sample_rate: int = Field(alias="Sample Rate")
    galvo_pre_time: float = Field(alias="Galvo Pre Time")
    galvo_scan_time: float = Field(alias="Galvo Scan Time")
    galvo_reset_time: float = Field(alias="Galvo Reset Time")
    galvo_post_time: float = Field(alias="Galvo Post Time")
    galvo_activated: bool = Field(alias="Galvo Activated")
    galvo_inverted: bool = Field(alias="Galvo Inverted")
    galvo_left_amplitude: float = Field(alias="Galvo Left Amplitude")
    galvo_left_offset: float = Field(alias="Galvo Left Offset")
    galvo_right_amplitude: float = Field(alias="Galvo Right Amplitude")
    galvo_right_offset: float = Field(alias="Galvo Right Offset")
    etl_activated: bool = Field(alias="ETL Activated")
    etl_steps: int = Field(alias="ETL Steps")
    etl_left_amplitude: float = Field(alias="ETL Left Amplitude")
    etl_left_offset: float = Field(alias="ETL Left Offset")
    etl_right_amplitude: float = Field(alias="ETL Right Amplitude")
    etl_right_offset: float = Field(alias="ETL Right Offset")
    galvo_left_right_swap: bool = Field(alias="Galvo Left Right Swap", default=False)


class LasersSettings(_NoEnvBaseSettings):
    model_config = SettingsConfigDict(
        extra="forbid", case_sensitive=True, populate_by_name=True
    )
    lasers_terminals: str = Field(alias="Lasers Terminals")
    laser1_wavelength: int = Field(alias="Laser1 Wavelength")
    laser1_power: float = Field(alias="Laser1 Power")
    laser1_max_power: float = Field(alias="Laser1 Max Power")
    laser1_mw_per_volt: float = Field(alias="Laser1 mW per Volt")
    # Optional V->mW calibration curve (display-only). Semicolon-separated
    # "V,mW" pairs. Empty/absent -> linear-through-origin estimate.
    laser1_calibration_curve: str = Field(alias="Laser1 Calibration Curve", default="")


class LasersSettingsOverlay(_NoEnvBaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore", case_sensitive=True, populate_by_name=True
    )
    lasers_terminals: str = Field(alias="Lasers Terminals")
    laser1_wavelength: int = Field(alias="Laser1 Wavelength")
    laser1_power: float = Field(alias="Laser1 Power")
    laser1_max_power: float = Field(alias="Laser1 Max Power")
    laser1_mw_per_volt: float = Field(alias="Laser1 mW per Volt")
    laser1_calibration_curve: str = Field(alias="Laser1 Calibration Curve", default="")


class IBeamSettings(_NoEnvBaseSettings):
    model_config = SettingsConfigDict(
        extra="forbid", case_sensitive=True, populate_by_name=True
    )
    port: str = Field(alias="Port")
    baud_rate: int = Field(alias="Baud Rate")
    channel: int = Field(alias="Channel")
    wavelength: int = Field(alias="Wavelength")
    power: int = Field(alias="Power")
    max_power: int = Field(alias="Max Power")  # uW in config.ini
    status_poll_interval: float = Field(alias="Status Poll Interval")

    @field_validator("max_power")
    @classmethod
    def _hard_max_power(cls, v: int) -> int:
        return _validate_ibeam_max_power(v)


class IBeamSettingsOverlay(_NoEnvBaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore", case_sensitive=True, populate_by_name=True
    )
    port: str = Field(alias="Port")
    baud_rate: int = Field(alias="Baud Rate")
    channel: int = Field(alias="Channel")
    wavelength: int = Field(alias="Wavelength")
    power: int = Field(alias="Power")
    max_power: int = Field(alias="Max Power")
    status_poll_interval: float = Field(alias="Status Poll Interval")

    @field_validator("max_power")
    @classmethod
    def _hard_max_power(cls, v: int) -> int:
        return _validate_ibeam_max_power(v)


class ETLsSettings(_NoEnvBaseSettings):
    model_config = SettingsConfigDict(
        extra="forbid", case_sensitive=True, populate_by_name=True
    )
    port_etl_left: str = Field(alias="Port ETL Left")
    port_etl_right: str = Field(alias="Port ETL Right")


class ETLsSettingsOverlay(_NoEnvBaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore", case_sensitive=True, populate_by_name=True
    )
    port_etl_left: str = Field(alias="Port ETL Left")
    port_etl_right: str = Field(alias="Port ETL Right")


class MotorsSettings(_NoEnvBaseSettings):
    model_config = SettingsConfigDict(
        extra="forbid", case_sensitive=True, populate_by_name=True
    )
    port: str = Field(alias="Port")
    device_number_vertical: int = Field(alias="Device Number Vertical")
    device_number_horizontal: int = Field(alias="Device Number Horizontal")
    device_number_camera: int = Field(alias="Device Number Camera")
    vertical_inverted: bool = Field(alias="Vertical Inverted")
    vertical_units: str = Field(alias="Vertical Units")
    vertical_origin: float = Field(alias="Vertical Origin")
    vertical_limit_low: float = Field(alias="Vertical Limit Low")
    vertical_limit_high: float = Field(alias="Vertical Limit High")
    horizontal_inverted: bool = Field(alias="Horizontal Inverted")
    horizontal_units: str = Field(alias="Horizontal Units")
    horizontal_origin: float = Field(alias="Horizontal Origin")
    horizontal_limit_low: float = Field(alias="Horizontal Limit Low")
    horizontal_limit_high: float = Field(alias="Horizontal Limit High")
    camera_inverted: bool = Field(alias="Camera Inverted")
    camera_units: str = Field(alias="Camera Units")
    camera_origin: float = Field(alias="Camera Origin")
    camera_limit_low: float = Field(alias="Camera Limit Low")
    camera_limit_high: float = Field(alias="Camera Limit High")

    @field_validator("vertical_limit_high")
    @classmethod
    def _hard_vertical_limit_high(cls, v: float) -> float:
        return _validate_vertical_limit_high(v)

    @field_validator("horizontal_limit_high")
    @classmethod
    def _hard_horizontal_limit_high(cls, v: float) -> float:
        return _validate_horizontal_limit_high(v)

    @field_validator("camera_limit_high")
    @classmethod
    def _hard_camera_limit_high(cls, v: float) -> float:
        return _validate_camera_limit_high(v)


class MotorsSettingsOverlay(_NoEnvBaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore", case_sensitive=True, populate_by_name=True
    )
    port: str = Field(alias="Port")
    device_number_vertical: int = Field(alias="Device Number Vertical")
    device_number_horizontal: int = Field(alias="Device Number Horizontal")
    device_number_camera: int = Field(alias="Device Number Camera")
    vertical_inverted: bool = Field(alias="Vertical Inverted")
    vertical_units: str = Field(alias="Vertical Units")
    vertical_origin: float = Field(alias="Vertical Origin")
    vertical_limit_low: float = Field(alias="Vertical Limit Low")
    vertical_limit_high: float = Field(alias="Vertical Limit High")
    horizontal_inverted: bool = Field(alias="Horizontal Inverted")
    horizontal_units: str = Field(alias="Horizontal Units")
    horizontal_origin: float = Field(alias="Horizontal Origin")
    horizontal_limit_low: float = Field(alias="Horizontal Limit Low")
    horizontal_limit_high: float = Field(alias="Horizontal Limit High")
    camera_inverted: bool = Field(alias="Camera Inverted")
    camera_units: str = Field(alias="Camera Units")
    camera_origin: float = Field(alias="Camera Origin")
    camera_limit_low: float = Field(alias="Camera Limit Low")
    camera_limit_high: float = Field(alias="Camera Limit High")

    @field_validator("vertical_limit_high")
    @classmethod
    def _hard_vertical_limit_high(cls, v: float) -> float:
        return _validate_vertical_limit_high(v)

    @field_validator("horizontal_limit_high")
    @classmethod
    def _hard_horizontal_limit_high(cls, v: float) -> float:
        return _validate_horizontal_limit_high(v)

    @field_validator("camera_limit_high")
    @classmethod
    def _hard_camera_limit_high(cls, v: float) -> float:
        return _validate_camera_limit_high(v)


class LoggingSettings(_NoEnvBaseSettings):
    model_config = SettingsConfigDict(
        extra="forbid", case_sensitive=True, populate_by_name=True
    )
    level: str = Field(alias="Level")
    log_dir: str = Field(alias="Log Dir", default="")


class LoggingSettingsOverlay(_NoEnvBaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore", case_sensitive=True, populate_by_name=True
    )
    level: str = Field(alias="Level")
    log_dir: str = Field(alias="Log Dir", default="")


# --- Adaptive section (operator-configurable bounds + gains) ---------------
#
# The [Adaptive] section is an OPTIONAL baseline section: a config.ini
# without it must validate using the model defaults. Both tiers carry
# identical aliases/defaults and the same range/pair validators so a
# tampered overlay cannot bypass the same check that guards the tracked
# baseline.
#
# Field ranges (rejected, not clamped, in BOTH tiers):
# - Exposure: 1..1000 (ms in Rolling / lines in Lightsheet).
# - Each laser power: 0..150 mW.
# - Target band: 0..100 %, lo <= hi.
# - Reacquire threshold: 0..50 %.
# - Block size N: 1..100 planes.
# - Kp: 0..5; Ki: 0..1.
# - Pilot count: 0..50 frames.
#
# Cross-section rejection (collect-all, after per-section validation):
# Adaptive Laser1 Max Power > [Lasers] Laser1 Max Power (mW) and
# Adaptive Laser2 Max Power > [iBeam] Max Power / 1000 (uW -> mW) are
# rejected in one pass — never silently clamped.


class AdaptiveSettings(_NoEnvBaseSettings):
    model_config = SettingsConfigDict(
        extra="forbid", case_sensitive=True, populate_by_name=True
    )
    enabled: bool = Field(alias="Enabled", default=False)
    min_exposure: float = Field(alias="Min Exposure", default=1)
    max_exposure: float = Field(alias="Max Exposure", default=1000)
    laser1_min_power: float = Field(alias="Laser1 Min Power", default=0.0)
    laser1_max_power: float = Field(alias="Laser1 Max Power", default=5.0)
    laser2_min_power: float = Field(alias="Laser2 Min Power", default=0.0)
    laser2_max_power: float = Field(alias="Laser2 Max Power", default=150.0)
    target_band_lo: float = Field(alias="Target Band Lo", default=90.0)
    target_band_hi: float = Field(alias="Target Band Hi", default=95.0)
    reacquire_threshold: float = Field(alias="Reacquire Threshold", default=8.0)
    block_size_n: int = Field(alias="Block Size N", default=8)
    kp: float = Field(alias="Kp", default=0.4)
    ki: float = Field(alias="Ki", default=0.05)
    pilot_count: int = Field(alias="Pilot Count", default=5)

    @field_validator("min_exposure", "max_exposure")
    @classmethod
    def _exposure_range(cls, v: float) -> float:
        if v < 1 or v > 1000:
            raise ValueError(f"exposure {v} is outside the valid range 1..1000")
        return v

    @field_validator(
        "laser1_min_power",
        "laser1_max_power",
        "laser2_min_power",
        "laser2_max_power",
    )
    @classmethod
    def _power_range(cls, v: float) -> float:
        if v < 0 or v > 150:
            raise ValueError(f"power {v} mW is outside the valid range 0..150 mW")
        return v

    @field_validator("target_band_lo", "target_band_hi")
    @classmethod
    def _target_range(cls, v: float) -> float:
        if v < 0 or v > 100:
            raise ValueError(f"target band {v} % is outside the valid range 0..100 %")
        return v

    @field_validator("reacquire_threshold")
    @classmethod
    def _reacquire_range(cls, v: float) -> float:
        if v < 0 or v > 50:
            raise ValueError(
                f"reacquire threshold {v} % is outside the valid range 0..50 %"
            )
        return v

    @field_validator("block_size_n")
    @classmethod
    def _block_range(cls, v: int) -> int:
        if v < 1 or v > 100:
            raise ValueError(f"block size N {v} is outside the valid range 1..100")
        return v

    @field_validator("kp")
    @classmethod
    def _kp_range(cls, v: float) -> float:
        if v < 0 or v > 5:
            raise ValueError(f"Kp {v} is outside the valid range 0..5")
        return v

    @field_validator("ki")
    @classmethod
    def _ki_range(cls, v: float) -> float:
        if v < 0 or v > 1:
            raise ValueError(f"Ki {v} is outside the valid range 0..1")
        return v

    @field_validator("pilot_count")
    @classmethod
    def _pilot_range(cls, v: int) -> int:
        if v < 0 or v > 50:
            raise ValueError(f"pilot count {v} is outside the valid range 0..50")
        return v

    @field_validator("max_exposure")
    @classmethod
    def _exposure_pair(cls, v: float, info: ValidationInfo) -> float:
        # Validate min <= max after both fields are parsed. The
        # values-by-name path is available via info.data.
        min_v = info.data.get("min_exposure")
        if min_v is not None and min_v > v:
            raise ValueError(
                f"Min Exposure ({min_v}) is greater than Max Exposure ({v})"
            )
        return v

    @field_validator("laser1_max_power")
    @classmethod
    def _laser1_pair(cls, v: float, info: ValidationInfo) -> float:
        min_v = info.data.get("laser1_min_power")
        if min_v is not None and min_v > v:
            raise ValueError(
                f"Laser1 Min Power ({min_v}) is greater than Laser1 Max Power ({v})"
            )
        return v

    @field_validator("laser2_max_power")
    @classmethod
    def _laser2_pair(cls, v: float, info: ValidationInfo) -> float:
        min_v = info.data.get("laser2_min_power")
        if min_v is not None and min_v > v:
            raise ValueError(
                f"Laser2 Min Power ({min_v}) is greater than Laser2 Max Power ({v})"
            )
        return v

    @field_validator("target_band_hi")
    @classmethod
    def _target_pair(cls, v: float, info: ValidationInfo) -> float:
        lo = info.data.get("target_band_lo")
        if lo is not None and lo > v:
            raise ValueError(
                f"Target Band Lo ({lo}) is greater than Target Band Hi ({v})"
            )
        return v


class AdaptiveSettingsOverlay(_NoEnvBaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore", case_sensitive=True, populate_by_name=True
    )
    enabled: bool = Field(alias="Enabled", default=False)
    min_exposure: float = Field(alias="Min Exposure", default=1)
    max_exposure: float = Field(alias="Max Exposure", default=1000)
    laser1_min_power: float = Field(alias="Laser1 Min Power", default=0.0)
    laser1_max_power: float = Field(alias="Laser1 Max Power", default=5.0)
    laser2_min_power: float = Field(alias="Laser2 Min Power", default=0.0)
    laser2_max_power: float = Field(alias="Laser2 Max Power", default=150.0)
    target_band_lo: float = Field(alias="Target Band Lo", default=90.0)
    target_band_hi: float = Field(alias="Target Band Hi", default=95.0)
    reacquire_threshold: float = Field(alias="Reacquire Threshold", default=8.0)
    block_size_n: int = Field(alias="Block Size N", default=8)
    kp: float = Field(alias="Kp", default=0.4)
    ki: float = Field(alias="Ki", default=0.05)
    pilot_count: int = Field(alias="Pilot Count", default=5)

    @field_validator("min_exposure", "max_exposure")
    @classmethod
    def _exposure_range(cls, v: float) -> float:
        if v < 1 or v > 1000:
            raise ValueError(f"exposure {v} is outside the valid range 1..1000")
        return v

    @field_validator(
        "laser1_min_power",
        "laser1_max_power",
        "laser2_min_power",
        "laser2_max_power",
    )
    @classmethod
    def _power_range(cls, v: float) -> float:
        if v < 0 or v > 150:
            raise ValueError(f"power {v} mW is outside the valid range 0..150 mW")
        return v

    @field_validator("target_band_lo", "target_band_hi")
    @classmethod
    def _target_range(cls, v: float) -> float:
        if v < 0 or v > 100:
            raise ValueError(f"target band {v} % is outside the valid range 0..100 %")
        return v

    @field_validator("reacquire_threshold")
    @classmethod
    def _reacquire_range(cls, v: float) -> float:
        if v < 0 or v > 50:
            raise ValueError(
                f"reacquire threshold {v} % is outside the valid range 0..50 %"
            )
        return v

    @field_validator("block_size_n")
    @classmethod
    def _block_range(cls, v: int) -> int:
        if v < 1 or v > 100:
            raise ValueError(f"block size N {v} is outside the valid range 1..100")
        return v

    @field_validator("kp")
    @classmethod
    def _kp_range(cls, v: float) -> float:
        if v < 0 or v > 5:
            raise ValueError(f"Kp {v} is outside the valid range 0..5")
        return v

    @field_validator("ki")
    @classmethod
    def _ki_range(cls, v: float) -> float:
        if v < 0 or v > 1:
            raise ValueError(f"Ki {v} is outside the valid range 0..1")
        return v

    @field_validator("pilot_count")
    @classmethod
    def _pilot_range(cls, v: int) -> int:
        if v < 0 or v > 50:
            raise ValueError(f"pilot count {v} is outside the valid range 0..50")
        return v

    @field_validator("max_exposure")
    @classmethod
    def _exposure_pair(cls, v: float, info: ValidationInfo) -> float:
        min_v = info.data.get("min_exposure")
        if min_v is not None and min_v > v:
            raise ValueError(
                f"Min Exposure ({min_v}) is greater than Max Exposure ({v})"
            )
        return v

    @field_validator("laser1_max_power")
    @classmethod
    def _laser1_pair(cls, v: float, info: ValidationInfo) -> float:
        min_v = info.data.get("laser1_min_power")
        if min_v is not None and min_v > v:
            raise ValueError(
                f"Laser1 Min Power ({min_v}) is greater than Laser1 Max Power ({v})"
            )
        return v

    @field_validator("laser2_max_power")
    @classmethod
    def _laser2_pair(cls, v: float, info: ValidationInfo) -> float:
        min_v = info.data.get("laser2_min_power")
        if min_v is not None and min_v > v:
            raise ValueError(
                f"Laser2 Min Power ({min_v}) is greater than Laser2 Max Power ({v})"
            )
        return v

    @field_validator("target_band_hi")
    @classmethod
    def _target_pair(cls, v: float, info: ValidationInfo) -> float:
        lo = info.data.get("target_band_lo")
        if lo is not None and lo > v:
            raise ValueError(
                f"Target Band Lo ({lo}) is greater than Target Band Hi ({v})"
            )
        return v


# ---------------------------------------------------------------------------
# Collect-all entry point — iterate ALL sections, collect every error +
# warning into two lists BEFORE any dialog is shown. REJECT (safety
# out-of-range, unknown key, wrong type, missing required) -> errors list.
# WARN (non-safety out-of-range: galvo >+-10 V, ETL drive >0-5 V, negative
# exposure) -> warnings list. Construction uses the STRICT tier for
# baseline-tier error classification.
# ---------------------------------------------------------------------------


@dataclass
class ConfigValidationResult:
    """Collect-all validation result — errors block startup, warnings are advisory."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# Section name -> (strict model class, overlay model class).
_SECTION_MODELS: dict[str, tuple[type[BaseSettings], type[BaseSettings]]] = {
    "Controller": (ControllerSettings, ControllerSettingsOverlay),
    "Camera": (CameraSettings, CameraSettingsOverlay),
    "SigGen": (SigGenSettings, SigGenSettingsOverlay),
    "Lasers": (LasersSettings, LasersSettingsOverlay),
    "iBeam": (IBeamSettings, IBeamSettingsOverlay),
    "ETLs": (ETLsSettings, ETLsSettingsOverlay),
    "Motors": (MotorsSettings, MotorsSettingsOverlay),
    "Logging": (LoggingSettings, LoggingSettingsOverlay),
    "Adaptive": (AdaptiveSettings, AdaptiveSettingsOverlay),
}

# Optional baseline sections — a config.ini without one of these sections
# validates using the model defaults. Sections NOT in this set are required.
_OPTIONAL_SECTIONS: frozenset[str] = frozenset({"Adaptive"})


# Non-safety recommended-range WARN checks. Each entry maps a section name
# to a list of (field_name, check, violation_phrase) tuples. The check runs
# AFTER the strict model constructs successfully; a True return adds a warning.
def _galvo_amplitude_warn(v: float) -> bool:
    return abs(v) > _GALVO_VOLTAGE_LIMIT


def _etl_amplitude_warn(v: float) -> bool:
    return v < 0.0 or v > _ETL_VOLTAGE_LIMIT


def _exposure_time_warn(v: float) -> bool:
    return v < 0.0


_WARN_CHECKS: dict[str, list[tuple[str, Callable[[Any], bool], str]]] = {
    "SigGen": [
        (
            "galvo_left_amplitude",
            _galvo_amplitude_warn,
            "is above the galvo voltage limit",
        ),
        (
            "galvo_right_amplitude",
            _galvo_amplitude_warn,
            "is above the galvo voltage limit",
        ),
        (
            "etl_left_amplitude",
            _etl_amplitude_warn,
            "is outside the ETL drive voltage range",
        ),
        (
            "etl_right_amplitude",
            _etl_amplitude_warn,
            "is outside the ETL drive voltage range",
        ),
    ],
    "Camera": [
        ("exposure_time", _exposure_time_warn, "is negative"),
    ],
}


def _format_pydantic_errors(section: str, err: ValidationError) -> list[str]:
    """Translate pydantic ValidationError errors into operator-readable rows."""
    rows: list[str] = []
    for e in err.errors():
        loc = ".".join(str(part) for part in e["loc"])
        etype = e["type"]
        if "extra" in etype or "forbidden" in etype:
            # Unknown/typo'd key — loc is the alias of the offending key.
            key = loc
            rows.append(
                f'[{section}] Unknown key "{key}". Remove it or correct the spelling.'
            )
        elif "missing" in etype:
            key = loc
            rows.append(
                f'[{section}] Required key "{key}" is missing. Add it '
                f"with the correct type and value."
            )
        else:
            # Type/range/safety rejection — surface the value + a short
            # operator-readable violation phrase from the validator message.
            msg = e.get("msg", "is invalid")
            input_val = e.get("input")
            if input_val is not None:
                rows.append(f"[{section}] {loc} = {input_val!r}: {msg}.")
            else:
                rows.append(f"[{section}] {loc}: {msg}.")
    return rows


def collect_config_errors(
    sections: dict[str, dict],
) -> ConfigValidationResult:
    """Validate all sections collect-all: every error and warning surfaces
    in one pass, not fail-fast on the first."""
    result = ConfigValidationResult()
    # Track the constructed settings objects so cross-section checks can
    # compare fields across sections after every section validated.
    constructed: dict[str, BaseSettings] = {}
    for section_name, data in sections.items():
        models = _SECTION_MODELS.get(section_name)
        if models is None:
            result.errors.append(
                f"[{section_name}] Unknown section. Allowed sections are: "
                f"{', '.join(sorted(_SECTION_MODELS))}."
            )
            continue
        strict_cls = models[0]
        try:
            settings = strict_cls(**data)
        except ValidationError as exc:
            result.errors.extend(_format_pydantic_errors(section_name, exc))
            continue
        constructed[section_name] = settings
        # Section constructed successfully — run non-safety WARN checks.
        warn_checks = _WARN_CHECKS.get(section_name, [])
        for field_name, check, violation in warn_checks:
            value = getattr(settings, field_name, None)
            if value is not None and check(value):
                # Look up the alias for the operator-facing key name.
                field_info: FieldInfo = strict_cls.model_fields[field_name]
                key = field_info.alias or field_name
                result.warnings.append(
                    f"[{section_name}] {key} = {value}: {violation}."
                )
    # Cross-section safety checks — reject (never clamp) adaptive laser
    # maxima above the configured laser maxima.
    _cross_section_adaptive_power(result, constructed)
    return result


def _cross_section_adaptive_power(
    result: ConfigValidationResult,
    constructed: dict[str, BaseSettings],
) -> None:
    """Reject adaptive laser maxima above the configured laser maxima.

    Both checks are collect-all: a config violating both surfaces two
    errors in one pass. The comparison is strict (>) so a value sitting
    exactly at the configured maximum is accepted.
    """
    adaptive = constructed.get("Adaptive")
    if adaptive is None:
        # [Adaptive] absent or failed per-section validation — nothing
        # to compare. A per-section failure is already in result.errors.
        return
    lasers = constructed.get("Lasers")
    if lasers is not None:
        l1_max = float(lasers.laser1_max_power)
        adaptive_l1_max = float(adaptive.laser1_max_power)
        if adaptive_l1_max > l1_max:
            result.errors.append(
                f"[Adaptive] Laser1 Max Power = {adaptive_l1_max} mW exceeds "
                f"[Lasers] Laser1 Max Power = {l1_max} mW. Lower the "
                f"adaptive bound or raise the configured laser maximum."
            )
    ibeam = constructed.get("iBeam")
    if ibeam is not None:
        # [iBeam] Max Power is in uW; convert to mW for the comparison.
        l2_max_mw = float(ibeam.max_power) / 1000.0
        adaptive_l2_max = float(adaptive.laser2_max_power)
        if adaptive_l2_max > l2_max_mw:
            result.errors.append(
                f"[Adaptive] Laser2 Max Power = {adaptive_l2_max} mW exceeds "
                f"[iBeam] Max Power = {l2_max_mw:.1f} mW (150000 uW / 1000). "
                f"Lower the adaptive bound or raise the configured laser "
                f"maximum."
            )


# ---------------------------------------------------------------------------
# INI loading helper — reads all sections from config.ini (baseline) + the
# optional rig-specific overlay, returning a per-section dict of raw string
# values ready for collect_config_errors. cfg_read only returns keys present
# in its defaults dict, so the defaults dict is built from each section
# model's Field aliases to capture every file key.
# ---------------------------------------------------------------------------


def load_sections_from_ini(
    baseline_path: str, overlay_path: str | None
) -> dict[str, dict[str, str]]:
    """Load all config.ini sections as raw string dicts, ready for
    ``collect_config_errors``."""
    sections: dict[str, dict[str, str]] = {}
    # Detect which sections the baseline file actually contains so an
    # absent OPTIONAL section (e.g. [Adaptive]) is supplied as {} and the
    # pydantic model defaults apply — never an empty-string parse failure.
    _base_cfg = configparser.ConfigParser()
    _base_cfg.optionxform = str  # preserve case
    _base_cfg.read(baseline_path)
    for section_name, (strict_cls, _overlay_cls) in _SECTION_MODELS.items():
        # An optional section absent from the baseline file is supplied
        # as {} so the pydantic model defaults apply.
        if section_name in _OPTIONAL_SECTIONS and not _base_cfg.has_section(
            section_name
        ):
            sections[section_name] = {}
            continue
        # Build the defaults dict from the strict model's Field aliases so
        # cfg_read captures every file key.
        defaults_template: dict[str, str] = {}
        for field_info in strict_cls.model_fields.values():
            key = field_info.alias or field_info.name
            defaults_template[key] = ""
        # cfg_read mutates the passed dict in place, so pass a fresh copy.
        baseline = cfg_read(baseline_path, section_name, dict(defaults_template))
        if overlay_path is not None and Path(overlay_path).exists():
            overlay = cfg_read(overlay_path, section_name, dict(defaults_template))
            # Only override baseline with keys the overlay file actually
            # contains. cfg_read fills every alias key from the defaults
            # dict, returning the "" sentinel for keys absent from the
            # overlay file — those sentinels must NOT clobber the
            # baseline's real values. Determine the set of keys the
            # overlay section actually contains via configparser and merge
            # only those — an explicitly-empty value propagates as "".
            _ov_cfg = configparser.ConfigParser()
            _ov_cfg.optionxform = str  # preserve case
            _ov_cfg.read(overlay_path)
            present_keys = (
                set(_ov_cfg[section_name].keys())
                if _ov_cfg.has_section(section_name)
                else set()
            )
            baseline.update({k: v for k, v in overlay.items() if k in present_keys})
        sections[section_name] = baseline
    return sections


# ---------------------------------------------------------------------------
# ConfigValidator — collect-all validation with a modal QDialog abort path.
# validate_or_abort() runs collect_config_errors, shows a modal QDialog
# listing all errors (red) and warnings (amber), then aborts via sys.exit(1)
# if any errors exist. PySide6 is imported inside _show_dialog so the module
# stays importable without Qt for pure-logic tests.
# ---------------------------------------------------------------------------


class ConfigValidator:
    """Collect-all config validation with a modal QDialog abort path."""

    def validate_or_abort(self, sections: dict[str, dict[str, str]]) -> None:
        """Run collect-all validation. Abort via sys.exit(1) if any errors
        exist OR the operator clicked "Exit" on a warnings-only dialog."""
        result = collect_config_errors(sections)
        if not result.errors and not result.warnings:
            return
        accepted = self._show_dialog(result.errors, result.warnings)
        if result.errors or not accepted:
            sys.exit(1)

    def _show_dialog(self, errors: list[str], warnings: list[str]) -> bool:
        """Show the collect-all config-error QDialog.

        Returns True if the operator clicked "Proceed with warnings"
        and False otherwise.
        """
        from PySide6.QtWidgets import (
            QDialog,
            QHBoxLayout,
            QLabel,
            QPushButton,
            QVBoxLayout,
        )

        dlg = QDialog()
        dlg.setWindowTitle("Configuration validation")
        dlg.setMinimumWidth(480)
        layout = QVBoxLayout(dlg)

        if errors:
            header = QLabel("✕ Errors — startup blocked")
            header.setStyleSheet("color: #FF3B30; font-weight: bold;")
            layout.addWidget(header)
            for e in errors:
                row = QLabel(f"✕ {e}")
                row.setWordWrap(True)
                layout.addWidget(row)

        if warnings:
            if errors:
                spacer = QLabel()
                spacer.setFixedHeight(32)
                layout.addWidget(spacer)
            header = QLabel("⚠ Warnings — review before proceeding")
            header.setStyleSheet("color: #FF9500; font-weight: bold;")
            layout.addWidget(header)
            for w in warnings:
                row = QLabel(f"⚠ {w}")
                row.setWordWrap(True)
                layout.addWidget(row)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        exit_btn = QPushButton("Exit")
        exit_btn.setDefault(True)
        exit_btn.clicked.connect(dlg.reject)
        btn_layout.addWidget(exit_btn)

        if warnings and not errors:
            proceed_btn = QPushButton("Proceed with warnings")
            proceed_btn.setStyleSheet("color: #34C759;")
            proceed_btn.clicked.connect(dlg.accept)
            btn_layout.addWidget(proceed_btn)

        layout.addLayout(btn_layout)
        dlg.setModal(True)
        return dlg.exec() == QDialog.DialogCode.Accepted
