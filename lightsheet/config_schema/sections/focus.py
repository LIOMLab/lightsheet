"""Focus compensation settings models — strict + overlay tiers."""

from pydantic import Field, field_validator
from pydantic_settings import SettingsConfigDict

from lightsheet.config_schema.shared import _make_overlay, _NoEnvBaseSettings


class FocusSettings(_NoEnvBaseSettings):
    model_config = SettingsConfigDict(
        extra="forbid", case_sensitive=True, populate_by_name=True
    )
    enabled: bool = Field(alias="Enabled", default=False)
    block_size_n: int = Field(alias="Block Size N", default=8)
    autofocus_residual: bool = Field(alias="Autofocus Residual Enabled", default=True)
    residual_gain_mm: float = Field(alias="Residual Gain Mm", default=0.05)
    max_residual_mm: float = Field(alias="Max Residual Mm", default=0.5)

    @field_validator("block_size_n")
    @classmethod
    def _block_range(cls, v: int) -> int:
        if v < 1 or v > 100:
            raise ValueError(f"block size N {v} is outside the valid range 1..100")
        return v

    @field_validator("residual_gain_mm")
    @classmethod
    def _residual_gain_range(cls, v: float) -> float:
        if v < 0 or v > 1:
            raise ValueError(f"residual gain {v} mm is outside the valid range 0..1")
        return v

    @field_validator("max_residual_mm")
    @classmethod
    def _max_residual_range(cls, v: float) -> float:
        if v < 0 or v > 5:
            raise ValueError(f"max residual {v} mm is outside the valid range 0..5")
        return v


FocusSettingsOverlay = _make_overlay(FocusSettings)
