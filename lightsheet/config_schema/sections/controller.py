"""Controller settings models — strict + overlay tiers."""

from typing import Any, Literal

from pydantic import Field, field_validator
from pydantic_settings import SettingsConfigDict

from lightsheet.config_schema.shared import _make_overlay, _NoEnvBaseSettings


class ControllerSettings(_NoEnvBaseSettings):
    model_config = SettingsConfigDict(
        extra="forbid", case_sensitive=True, populate_by_name=True
    )
    units: str = Field(alias="Units")
    # Image File Format — the persisted default save format loaded at
    # startup. The before-validator lowercases so the rig's Title-Case
    # config.ini values are accepted, and maps the "" sentinel (a key
    # absent from config.ini arrives as "" via load_sections_from_ini)
    # to "hdf5" (the operator-facing default). Only the three implemented
    # save paths (hdf5, zarr, both) are accepted; the legacy "tiff" literal
    # is rejected at startup.
    image_file_format: Literal["hdf5", "zarr", "both"] = Field(
        alias="Image File Format", default="both"
    )
    # Theme — the persisted UI theme override. The before-validator
    # lowercases and maps "" to "system".
    theme: Literal["light", "dark", "system"] = Field(alias="Theme", default="system")

    @field_validator("image_file_format", mode="before")
    @classmethod
    def _lowercase_image_file_format(cls, v: Any) -> Any:
        if isinstance(v, str):
            if v == "":
                return "hdf5"
            return v.lower()
        return v

    @field_validator("theme", mode="before")
    @classmethod
    def _lowercase_theme(cls, v: Any) -> Any:
        if isinstance(v, str):
            if v == "":
                return "system"
            return v.lower()
        return v


ControllerSettingsOverlay = _make_overlay(ControllerSettings)
