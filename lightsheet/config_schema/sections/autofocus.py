"""Autofocus settings models — strict + overlay tiers."""

from pydantic import Field, field_validator
from pydantic_settings import SettingsConfigDict

from lightsheet.config_schema.shared import _make_overlay, _NoEnvBaseSettings


class AutofocusSettings(_NoEnvBaseSettings):
    model_config = SettingsConfigDict(
        extra="forbid", case_sensitive=True, populate_by_name=True
    )
    enabled: bool = Field(alias="Enabled", default=False)
    cadence: int = Field(alias="Cadence", default=1)
    residual_gain_mm: float = Field(alias="Residual Gain Mm", default=0.05)
    max_residual_mm: float = Field(alias="Max Residual Mm", default=0.5)
    smoothing: float = Field(alias="Smoothing", default=0.5)
    update_threshold: float = Field(alias="Update Threshold", default=0.0)
    use_curve_seed: bool = Field(alias="Use Curve Seed", default=False)

    @field_validator("cadence")
    @classmethod
    def _cadence_range(cls, v: int) -> int:
        if v < 1 or v > 1000:
            raise ValueError(f"cadence {v} is outside the valid range 1..1000")
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

    @field_validator("smoothing")
    @classmethod
    def _smoothing_range(cls, v: float) -> float:
        if v < 0 or v > 1:
            raise ValueError(f"smoothing {v} is outside the valid range 0..1")
        return v

    @field_validator("update_threshold")
    @classmethod
    def _update_threshold_range(cls, v: float) -> float:
        if v < 0 or v > 1:
            raise ValueError(f"update threshold {v} is outside the valid range 0..1")
        return v


AutofocusSettingsOverlay = _make_overlay(AutofocusSettings)
