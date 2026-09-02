"""ETLs (Optotune tunable lens) settings models — strict + overlay tiers."""

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from lightsheet.config_schema.shared import _make_overlay, _NoEnvBaseSettings


class ETLsSettings(_NoEnvBaseSettings):
    model_config = SettingsConfigDict(
        extra="forbid", case_sensitive=True, populate_by_name=True
    )
    port_etl_left: str = Field(alias="Port ETL Left")
    port_etl_right: str = Field(alias="Port ETL Right")


ETLsSettingsOverlay = _make_overlay(ETLsSettings)
