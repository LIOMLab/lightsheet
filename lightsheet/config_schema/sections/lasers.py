"""Lasers settings models — strict + overlay tiers."""

from pydantic import Field, field_validator
from pydantic_settings import SettingsConfigDict

from lightsheet.config_schema.shared import (
    _make_overlay,
    _NoEnvBaseSettings,
    _validate_laser2_max_power,
    _validate_laser2_mw_per_volt,
)


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
    # L2 DAQLaser on /Dev7/ao1 — 0-5 V analog modulation, camera-aligned.
    # The retained iBeam serial backend is composed as readback_backend.
    laser2_wavelength: int = Field(alias="Laser2 Wavelength")
    laser2_power: float = Field(alias="Laser2 Power")
    laser2_max_power: float = Field(alias="Laser2 Max Power")
    laser2_mw_per_volt: float = Field(alias="Laser2 mW per Volt")

    @field_validator("laser2_max_power")
    @classmethod
    def _hard_laser2_max_power(cls, v: float) -> float:
        return _validate_laser2_max_power(v)

    @field_validator("laser2_mw_per_volt")
    @classmethod
    def _hard_laser2_mw_per_volt(cls, v: float) -> float:
        return _validate_laser2_mw_per_volt(v)


LasersSettingsOverlay = _make_overlay(LasersSettings)
