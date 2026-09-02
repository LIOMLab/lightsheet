"""Shared config-schema primitives.

No-environment ``_NoEnvBaseSettings`` base, the ``_make_overlay`` factory,
hard-limit safety constants, and the six safety-key validators used by the
section models.
"""

from types import new_class
from typing import Any, cast

from pydantic_settings import BaseSettings

# --- Safety-critical constants ---
# iBeam Smart 640 hard limit: 150 mW = 150000 uW. The schema validates Max
# Power, not wavelength — 640 nm is the physical diode emission peak; 647 nm
# is the recorded capture/detection wavelength.
_IBEAM_MAX_MW: int = 150000  # uW

# L2 DAQLaser ceiling: 150 mW full-scale at 30.0 mW/V = 5.0 V on /Dev7/ao1.
# The schema rejects a Laser2 Max Power above this ceiling and a nonpositive
# mW per Volt conversion factor in both tiers — these are safety-critical
# config values that bound the two-layer runtime clamp.
_LASER2_MAX_POWER_MW: float = 150.0

# Zaber T-LS mechanical travel limits. A stage driven past mechanical limits
# damages hardware.
_MOTORS_VERTICAL_LIMIT_HIGH_MM: float = 41.0
_MOTORS_HORIZONTAL_LIMIT_HIGH_MM: float = 18.8
_MOTORS_CAMERA_LIMIT_HIGH_MM: float = 35.0


class _NoEnvBaseSettings(BaseSettings):
    """BaseSettings that reads ONLY the init (kwargs) source — no
    environment-variable, dotenv, or file-secret source."""

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: Any,
        env_settings: Any,
        dotenv_settings: Any,
        file_secret_settings: Any,
    ) -> tuple[Any, ...]:
        return (init_settings,)


def _make_overlay(strict_cls: type[_NoEnvBaseSettings]) -> type[Any]:
    """Return a named overlay subclass of ``strict_cls`` that changes only
    ``extra`` to ``'ignore'``.

    The overlay inherits every field alias, default, and validator from the
    strict model, so there is a single source of safety truth per section.
    It remains init-only via the inherited ``settings_customise_sources``.

    The return type is ``type[Any]`` because ``ty`` cannot infer fields on a
    class created dynamically with ``types.new_class``; this keeps the overlay
    classes type-checkable at the call sites without losing runtime behavior.
    """
    overlay_name = f"{strict_cls.__name__}Overlay"

    def _exec_body(ns: dict[str, Any]) -> None:
        ns["__module__"] = strict_cls.__module__
        ns["__qualname__"] = overlay_name
        # Copy the strict model's config and relax only the extra-key policy.
        overlay_config = dict(strict_cls.model_config)
        overlay_config["extra"] = "ignore"
        ns["model_config"] = overlay_config

    return cast(
        type[Any],
        new_class(overlay_name, (strict_cls,), exec_body=_exec_body),
    )


def _validate_ibeam_max_power(v: int) -> int:
    if v > _IBEAM_MAX_MW:
        raise ValueError(
            f"Max Power {v} uW exceeds iBeam hard limit {_IBEAM_MAX_MW} uW (150 mW)"
        )
    return v


def _validate_vertical_limit_high(v: float) -> float:
    if v > _MOTORS_VERTICAL_LIMIT_HIGH_MM:
        raise ValueError(
            f"Vertical Limit High {v} mm exceeds mechanical travel limit "
            f"{_MOTORS_VERTICAL_LIMIT_HIGH_MM} mm"
        )
    return v


def _validate_horizontal_limit_high(v: float) -> float:
    if v > _MOTORS_HORIZONTAL_LIMIT_HIGH_MM:
        raise ValueError(
            f"Horizontal Limit High {v} mm exceeds mechanical travel limit "
            f"{_MOTORS_HORIZONTAL_LIMIT_HIGH_MM} mm"
        )
    return v


def _validate_camera_limit_high(v: float) -> float:
    if v > _MOTORS_CAMERA_LIMIT_HIGH_MM:
        raise ValueError(
            f"Camera Limit High {v} mm exceeds mechanical travel limit "
            f"{_MOTORS_CAMERA_LIMIT_HIGH_MM} mm"
        )
    return v


def _validate_laser2_max_power(v: float) -> float:
    if v > _LASER2_MAX_POWER_MW:
        raise ValueError(
            f"Laser2 Max Power {v} mW exceeds the L2 ceiling "
            f"{_LASER2_MAX_POWER_MW} mW (150 mW iBeam full-scale)"
        )
    return v


def _validate_laser2_mw_per_volt(v: float) -> float:
    if v <= 0:
        raise ValueError(
            f"Laser2 mW per Volt {v} must be positive (nonzero conversion factor)"
        )
    return v
