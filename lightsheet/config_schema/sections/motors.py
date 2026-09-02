"""Motors (Zaber) settings models — strict + overlay tiers."""

from pydantic import Field, field_validator
from pydantic_settings import SettingsConfigDict

from lightsheet.config_schema.shared import (
    _make_overlay,
    _NoEnvBaseSettings,
    _validate_camera_limit_high,
    _validate_horizontal_limit_high,
    _validate_vertical_limit_high,
)


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


MotorsSettingsOverlay = _make_overlay(MotorsSettings)
