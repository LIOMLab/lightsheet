"""Adaptive exposure/laser-power settings models — strict + overlay tiers."""

from pydantic import Field, field_validator
from pydantic_core.core_schema import ValidationInfo
from pydantic_settings import SettingsConfigDict

from lightsheet.config_schema.shared import _make_overlay, _NoEnvBaseSettings


class AdaptiveSettings(_NoEnvBaseSettings):
    model_config = SettingsConfigDict(
        extra="forbid", case_sensitive=True, populate_by_name=True
    )
    enabled: bool = Field(alias="Enabled", default=False)
    min_exposure: float = Field(alias="Min Exposure", default=1)
    max_exposure: float = Field(alias="Max Exposure", default=1000)
    laser1_min_power: float = Field(alias="Laser1 Min Power", default=0.0)
    laser1_max_power: float = Field(alias="Laser1 Max Power", default=5.0)
    laser2_min_power: float = Field(alias="Laser2 Min Power", default=0.0)
    laser2_max_power: float = Field(alias="Laser2 Max Power", default=150.0)
    target_band_lo: float = Field(alias="Target Band Lo", default=90.0)
    target_band_hi: float = Field(alias="Target Band Hi", default=95.0)
    reacquire_threshold: float = Field(alias="Reacquire Threshold", default=8.0)
    block_size_n: int = Field(alias="Block Size N", default=8)
    kp: float = Field(alias="Kp", default=0.4)
    ki: float = Field(alias="Ki", default=0.05)
    pilot_count: int = Field(alias="Pilot Count", default=5)

    @field_validator("min_exposure", "max_exposure")
    @classmethod
    def _exposure_range(cls, v: float) -> float:
        if v < 1 or v > 1000:
            raise ValueError(f"exposure {v} is outside the valid range 1..1000")
        return v

    @field_validator(
        "laser1_min_power",
        "laser1_max_power",
        "laser2_min_power",
        "laser2_max_power",
    )
    @classmethod
    def _power_range(cls, v: float) -> float:
        if v < 0 or v > 150:
            raise ValueError(f"power {v} mW is outside the valid range 0..150 mW")
        return v

    @field_validator("target_band_lo", "target_band_hi")
    @classmethod
    def _target_range(cls, v: float) -> float:
        if v < 0 or v > 100:
            raise ValueError(f"target band {v} % is outside the valid range 0..100 %")
        return v

    @field_validator("reacquire_threshold")
    @classmethod
    def _reacquire_range(cls, v: float) -> float:
        if v < 0 or v > 50:
            raise ValueError(
                f"reacquire threshold {v} % is outside the valid range 0..50 %"
            )
        return v

    @field_validator("block_size_n")
    @classmethod
    def _block_range(cls, v: int) -> int:
        if v < 1 or v > 100:
            raise ValueError(f"block size N {v} is outside the valid range 1..100")
        return v

    @field_validator("kp")
    @classmethod
    def _kp_range(cls, v: float) -> float:
        if v < 0 or v > 5:
            raise ValueError(f"Kp {v} is outside the valid range 0..5")
        return v

    @field_validator("ki")
    @classmethod
    def _ki_range(cls, v: float) -> float:
        if v < 0 or v > 1:
            raise ValueError(f"Ki {v} is outside the valid range 0..1")
        return v

    @field_validator("pilot_count")
    @classmethod
    def _pilot_range(cls, v: int) -> int:
        if v < 0 or v > 50:
            raise ValueError(f"pilot count {v} is outside the valid range 0..50")
        return v

    @field_validator("max_exposure")
    @classmethod
    def _exposure_pair(cls, v: float, info: ValidationInfo) -> float:
        # Validate min <= max after both fields are parsed. The
        # values-by-name path is available via info.data.
        min_v = info.data.get("min_exposure")
        if min_v is not None and min_v > v:
            raise ValueError(
                f"Min Exposure ({min_v}) is greater than Max Exposure ({v})"
            )
        return v

    @field_validator("laser1_max_power")
    @classmethod
    def _laser1_pair(cls, v: float, info: ValidationInfo) -> float:
        min_v = info.data.get("laser1_min_power")
        if min_v is not None and min_v > v:
            raise ValueError(
                f"Laser1 Min Power ({min_v}) is greater than Laser1 Max Power ({v})"
            )
        return v

    @field_validator("laser2_max_power")
    @classmethod
    def _laser2_pair(cls, v: float, info: ValidationInfo) -> float:
        min_v = info.data.get("laser2_min_power")
        if min_v is not None and min_v > v:
            raise ValueError(
                f"Laser2 Min Power ({min_v}) is greater than Laser2 Max Power ({v})"
            )
        return v

    @field_validator("target_band_hi")
    @classmethod
    def _target_pair(cls, v: float, info: ValidationInfo) -> float:
        lo = info.data.get("target_band_lo")
        if lo is not None and lo > v:
            raise ValueError(
                f"Target Band Lo ({lo}) is greater than Target Band Hi ({v})"
            )
        return v


AdaptiveSettingsOverlay = _make_overlay(AdaptiveSettings)
