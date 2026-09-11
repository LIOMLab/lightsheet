"""iBeam laser settings models — strict + overlay tiers."""

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from lightsheet.config_schema.shared import (
    _make_overlay,
    _NoEnvBaseSettings,
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
    status_poll_interval: float = Field(alias="Status Poll Interval")


IBeamSettingsOverlay = _make_overlay(IBeamSettings)
