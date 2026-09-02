"""Camera settings models — strict + overlay tiers."""

from pydantic import Field, field_validator
from pydantic_settings import SettingsConfigDict

from lightsheet.config_schema.shared import _make_overlay, _NoEnvBaseSettings


class CameraSettings(_NoEnvBaseSettings):
    model_config = SettingsConfigDict(
        extra="forbid", case_sensitive=True, populate_by_name=True
    )
    shutter_mode: str = Field(default="Rolling", alias="Shutter Mode")
    exposure_time: float = Field(alias="Exposure Time")
    lightsheet_line_time: float = Field(alias="Lightsheet Line Time")
    lightsheet_exposed_lines: int = Field(alias="Lightsheet Exposed Lines")
    lightsheet_delay_lines: int = Field(alias="Lightsheet Delay Lines")
    recorder_timeout: int = Field(alias="Recorder Timeout")
    recorder_timeout_floor: int = Field(alias="Recorder Timeout Floor")
    recorder_timeout_safety_factor: float = Field(
        alias="Recorder Timeout Safety Factor"
    )

    @field_validator("shutter_mode")
    @classmethod
    def _shutter_allowed(cls, v: str) -> str:
        allowed = {"Rolling", "Lightsheet", "Global"}
        if v not in allowed:
            raise ValueError(f"Shutter Mode must be one of {allowed}")
        return v


CameraSettingsOverlay = _make_overlay(CameraSettings)
