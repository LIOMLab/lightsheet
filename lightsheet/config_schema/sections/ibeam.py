"""iBeam laser settings models — strict + overlay tiers."""

from pydantic import Field, field_validator
from pydantic_settings import SettingsConfigDict

from lightsheet.config_schema.shared import (
    _make_overlay,
    _NoEnvBaseSettings,
    _validate_ibeam_max_power,
)


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


IBeamSettingsOverlay = _make_overlay(IBeamSettings)
