"""SigGen settings models — strict + overlay tiers."""

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from lightsheet.config_schema.shared import _make_overlay, _NoEnvBaseSettings


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


SigGenSettingsOverlay = _make_overlay(SigGenSettings)
