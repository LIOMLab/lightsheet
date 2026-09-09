"""Logging settings models — strict + overlay tiers."""

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from lightsheet.config_schema.shared import _make_overlay, _NoEnvBaseSettings


class LoggingSettings(_NoEnvBaseSettings):
    model_config = SettingsConfigDict(
        extra="forbid", case_sensitive=True, populate_by_name=True
    )
    level: str = Field(alias="Level")
    log_dir: str = Field(alias="Log Dir", default="")


LoggingSettingsOverlay = _make_overlay(LoggingSettings)
