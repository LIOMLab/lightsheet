"""
PKG-04 two-tier pydantic-settings config schema — layers validation ON TOP
of the existing cfg_read/cfg_write configparser helpers (D-03: does NOT
replace them).

The strict baseline tier (extra='forbid') rejects unknown/typo'd keys
instead of silently falling into the configparser fallback — the PKG-04
root-cause bug. The lax overlay tier (extra='ignore') tolerates extra keys
in the rig-specific overlay so rig calibration freedom is preserved.

Safety-critical keys ([iBeam] Max Power <= 150000 uW, [Motors] * Limit High
<= their AGENTS.md Sec.2 mechanical limits) are REJECTED (not clamped)
out-of-range in BOTH tiers via the same field_validator — a tampered overlay
cannot bypass the same check that guards the tracked baseline.

Non-safety out-of-range values (galvo/ETL amplitudes, negative exposure
time) are collected as WARNings by the collect-all entry point AFTER
construction succeeds — they do NOT raise ValidationError.

settings_customise_sources returns ONLY the init (kwargs) source — no
environment-variable source, no dotenv source (Pitfall 4: env-var pollution
into extra='forbid' validation).

case_sensitive=True + Field(alias="<Exact INI Key>") + populate_by_name=True
preserves the case-sensitive Title-Case INI key contract (AGENTS.md Sec.9,
Pitfall 5) — a typo'd key ('Max power' lowercase-p) is rejected, not silently
lowercased and accepted.
"""

import logging
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import Field, ValidationError, field_validator
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, SettingsConfigDict

from lightsheet.config import cfg_read

logger = logging.getLogger(__name__)

# --- Safety-critical constants (AGENTS.md Sec.2 / hardware_inventory.yaml) ---
# iBeam Smart 640 hard limit: 150 mW = 150000 uW (rig-confirmed 640 nm, not
# the older 636 nm reference).
_IBEAM_MAX_MW: int = 150000  # uW

# Zaber T-LS mechanical travel limits per AGENTS.md Sec.2 / config.ini tracked
# values as the ceiling. A stage driven past mechanical limits damages hardware.
_MOTORS_VERTICAL_LIMIT_HIGH_MM: float = 41.0
_MOTORS_HORIZONTAL_LIMIT_HIGH_MM: float = 18.8
_MOTORS_CAMERA_LIMIT_HIGH_MM: float = 35.0

# --- Non-safety recommended ranges (WARN, not REJECT) ---
_GALVO_VOLTAGE_LIMIT: float = 10.0  # ±10 V NI-6363 AO range
# ETL drive is a 0–5 V analog input to the EL-10-30 lens driver, which
# maps it to its 0–292.84 mA coil-current range internally. The config
# [SigGen] ETL Left/Right Amplitude values are volts (the DAQ AO drive),
# so the warn check compares volts against the 5 V analog input range,
# not the 292.84 mA coil-current limit.
_ETL_VOLTAGE_LIMIT: float = 5.0  # 0–5 V Optotune EL-10-30 analog input


# ---------------------------------------------------------------------------
# Shared base — provides settings_customise_sources so no environment or
# dotenv source is ever registered (Pitfall 4). Each per-section model
# declares its own model_config with the tier-appropriate extra policy.
# ---------------------------------------------------------------------------


class _NoEnvBaseSettings(BaseSettings):
    """BaseSettings that reads ONLY the init (kwargs) source — no
    environment-variable source, no dotenv source, no file-secret source.
    The models validate already-parsed dicts handed back by cfg_read; the
    Pitfall 4 env-var pollution path into extra='forbid' is closed."""

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


# ---------------------------------------------------------------------------
# Safety-key field validators — applied to BOTH tiers (a tampered overlay
# cannot bypass the same check that guards the tracked baseline).
# ---------------------------------------------------------------------------


def _validate_ibeam_max_power(v: int) -> int:
    if v > _IBEAM_MAX_MW:
        raise ValueError(
            f"Max Power {v} uW exceeds iBeam hard limit {_IBEAM_MAX_MW} uW "
            f"(150 mW)"
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


# ---------------------------------------------------------------------------
# Per-section models. Field aliases match config.ini's verbatim key casing
# (AGENTS.md Sec.9). One strict (extra='forbid') + one overlay
# (extra='ignore') subclass per section.
# ---------------------------------------------------------------------------


class ControllerSettings(_NoEnvBaseSettings):
    model_config = SettingsConfigDict(
        extra="forbid", case_sensitive=True, populate_by_name=True
    )
    units: str = Field(alias="Units")


class ControllerSettingsOverlay(_NoEnvBaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore", case_sensitive=True, populate_by_name=True
    )
    units: str = Field(alias="Units")


class CameraSettings(_NoEnvBaseSettings):
    model_config = SettingsConfigDict(
        extra="forbid", case_sensitive=True, populate_by_name=True
    )
    shutter_mode: str = Field(alias="Shutter Mode")
    exposure_time: float = Field(alias="Exposure Time")
    lightsheet_line_time: float = Field(alias="Lightsheet Line Time")
    lightsheet_exposed_lines: int = Field(alias="Lightsheet Exposed Lines")
    lightsheet_delay_lines: int = Field(alias="Lightsheet Delay Lines")
    recorder_timeout: float = Field(alias="Recorder Timeout")
    recorder_timeout_floor: float = Field(alias="Recorder Timeout Floor")
    recorder_timeout_safety_factor: float = Field(
        alias="Recorder Timeout Safety Factor"
    )


class CameraSettingsOverlay(_NoEnvBaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore", case_sensitive=True, populate_by_name=True
    )
    shutter_mode: str = Field(alias="Shutter Mode")
    exposure_time: float = Field(alias="Exposure Time")
    lightsheet_line_time: float = Field(alias="Lightsheet Line Time")
    lightsheet_exposed_lines: int = Field(alias="Lightsheet Exposed Lines")
    lightsheet_delay_lines: int = Field(alias="Lightsheet Delay Lines")
    recorder_timeout: float = Field(alias="Recorder Timeout")
    recorder_timeout_floor: float = Field(alias="Recorder Timeout Floor")
    recorder_timeout_safety_factor: float = Field(
        alias="Recorder Timeout Safety Factor"
    )


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
    # 05-08-PLAN wires the real config.ini key + siggen.py consumption.
    # Default False so a missing key does not break existing configs.
    galvo_left_right_swap: bool = Field(
        alias="Galvo Left Right Swap", default=False
    )


class SigGenSettingsOverlay(_NoEnvBaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore", case_sensitive=True, populate_by_name=True
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
    galvo_left_right_swap: bool = Field(
        alias="Galvo Left Right Swap", default=False
    )


class LasersSettings(_NoEnvBaseSettings):
    model_config = SettingsConfigDict(
        extra="forbid", case_sensitive=True, populate_by_name=True
    )
    lasers_terminals: str = Field(alias="Lasers Terminals")
    laser1_wavelength: int = Field(alias="Laser1 Wavelength")
    laser1_power: float = Field(alias="Laser1 Power")
    laser1_max_power: float = Field(alias="Laser1 Max Power")
    laser1_mw_per_volt: float = Field(alias="Laser1 mW per Volt")


class LasersSettingsOverlay(_NoEnvBaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore", case_sensitive=True, populate_by_name=True
    )
    lasers_terminals: str = Field(alias="Lasers Terminals")
    laser1_wavelength: int = Field(alias="Laser1 Wavelength")
    laser1_power: float = Field(alias="Laser1 Power")
    laser1_max_power: float = Field(alias="Laser1 Max Power")
    laser1_mw_per_volt: float = Field(alias="Laser1 mW per Volt")


class IBeamSettings(_NoEnvBaseSettings):
    model_config = SettingsConfigDict(
        extra="forbid", case_sensitive=True, populate_by_name=True
    )
    port: str = Field(alias="Port")
    baud_rate: int = Field(alias="Baud Rate")
    channel: int = Field(alias="Channel")
    wavelength: int = Field(alias="Wavelength")
    power: int = Field(alias="Power")
    max_power: int = Field(alias="Max Power")  # uW in config.ini
    status_poll_interval: float = Field(alias="Status Poll Interval")

    @field_validator("max_power")
    @classmethod
    def _hard_max_power(cls, v: int) -> int:
        return _validate_ibeam_max_power(v)


class IBeamSettingsOverlay(_NoEnvBaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore", case_sensitive=True, populate_by_name=True
    )
    port: str = Field(alias="Port")
    baud_rate: int = Field(alias="Baud Rate")
    channel: int = Field(alias="Channel")
    wavelength: int = Field(alias="Wavelength")
    power: int = Field(alias="Power")
    max_power: int = Field(alias="Max Power")
    status_poll_interval: float = Field(alias="Status Poll Interval")

    @field_validator("max_power")
    @classmethod
    def _hard_max_power(cls, v: int) -> int:
        return _validate_ibeam_max_power(v)


class ETLsSettings(_NoEnvBaseSettings):
    model_config = SettingsConfigDict(
        extra="forbid", case_sensitive=True, populate_by_name=True
    )
    port_etl_left: str = Field(alias="Port ETL Left")
    port_etl_right: str = Field(alias="Port ETL Right")


class ETLsSettingsOverlay(_NoEnvBaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore", case_sensitive=True, populate_by_name=True
    )
    port_etl_left: str = Field(alias="Port ETL Left")
    port_etl_right: str = Field(alias="Port ETL Right")


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


class MotorsSettingsOverlay(_NoEnvBaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore", case_sensitive=True, populate_by_name=True
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


class LoggingSettings(_NoEnvBaseSettings):
    model_config = SettingsConfigDict(
        extra="forbid", case_sensitive=True, populate_by_name=True
    )
    level: str = Field(alias="Level")
    log_dir: str = Field(alias="Log Dir", default="")


class LoggingSettingsOverlay(_NoEnvBaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore", case_sensitive=True, populate_by_name=True
    )
    level: str = Field(alias="Level")
    log_dir: str = Field(alias="Log Dir", default="")


# ---------------------------------------------------------------------------
# Collect-all entry point — iterate ALL sections, collect every error +
# warning into two lists BEFORE any dialog is shown (UI-SPEC collect-all).
# REJECT (safety out-of-range, unknown key, wrong type, missing required) ->
# errors list. WARN (non-safety out-of-range: galvo >±10 V, ETL drive
# >0–5 V, negative exposure) -> warnings list. Construction uses the STRICT tier for
# baseline-tier error classification; the same field_validators run on the
# overlay tier when 05-05-PLAN's composition root wires the overlay merge.
# ---------------------------------------------------------------------------


@dataclass
class ConfigValidationResult:
    """Collect-all validation result — errors block startup, warnings are
    advisory (operator may proceed after review)."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# Section name -> (strict model class, overlay model class).
_SECTION_MODELS: dict[str, tuple[type[BaseSettings], type[BaseSettings]]] = {
    "Controller": (ControllerSettings, ControllerSettingsOverlay),
    "Camera": (CameraSettings, CameraSettingsOverlay),
    "SigGen": (SigGenSettings, SigGenSettingsOverlay),
    "Lasers": (LasersSettings, LasersSettingsOverlay),
    "iBeam": (IBeamSettings, IBeamSettingsOverlay),
    "ETLs": (ETLsSettings, ETLsSettingsOverlay),
    "Motors": (MotorsSettings, MotorsSettingsOverlay),
    "Logging": (LoggingSettings, LoggingSettingsOverlay),
}


# Non-safety recommended-range WARN checks. Each entry maps a section name
# to a list of (field_name, check, violation_phrase) tuples. The check runs
# AFTER the strict model constructs successfully; a True return adds a warning.
def _galvo_amplitude_warn(v: float) -> bool:
    return abs(v) > _GALVO_VOLTAGE_LIMIT


def _etl_amplitude_warn(v: float) -> bool:
    return v < 0.0 or v > _ETL_VOLTAGE_LIMIT


def _exposure_time_warn(v: float) -> bool:
    return v < 0.0


_WARN_CHECKS: dict[str, list[tuple[str, Callable[[Any], bool], str]]] = {
    "SigGen": [
        ("galvo_left_amplitude", _galvo_amplitude_warn, "is above the galvo voltage limit"),
        ("galvo_right_amplitude", _galvo_amplitude_warn, "is above the galvo voltage limit"),
        ("etl_left_amplitude", _etl_amplitude_warn, "is outside the ETL drive voltage range"),
        ("etl_right_amplitude", _etl_amplitude_warn, "is outside the ETL drive voltage range"),
    ],
    "Camera": [
        ("exposure_time", _exposure_time_warn, "is negative"),
    ],
}


def _format_pydantic_errors(section: str, err: ValidationError) -> list[str]:
    """Translate pydantic ValidationError errors into operator-readable
    rows. Pydantic-internal jargon (extra_forbidden, value_error, etc.) is
    NOT surfaced — the error type drives classification, never the displayed
    text (UI-SPEC Copywriting Contract)."""
    rows: list[str] = []
    for e in err.errors():
        loc = ".".join(str(part) for part in e["loc"])
        etype = e["type"]
        if "extra" in etype or "forbidden" in etype:
            # Unknown/typo'd key — loc is the alias of the offending key.
            key = loc
            rows.append(
                f"[{section}] Unknown key \"{key}\". Remove it or correct "
                f"the spelling."
            )
        elif "missing" in etype:
            key = loc
            rows.append(
                f"[{section}] Required key \"{key}\" is missing. Add it "
                f"with the correct type and value."
            )
        else:
            # Type/range/safety rejection — surface the value + a short
            # operator-readable violation phrase from the validator message.
            msg = e.get("msg", "is invalid")
            input_val = e.get("input")
            if input_val is not None:
                rows.append(
                    f"[{section}] {loc} = {input_val!r}: {msg}."
                )
            else:
                rows.append(f"[{section}] {loc}: {msg}.")
    return rows


def collect_config_errors(
    sections: dict[str, dict],
) -> ConfigValidationResult:
    """Validate all sections collect-all: every error and warning surfaces
    in one pass, not fail-fast on the first. REJECT (safety out-of-range,
    unknown key, wrong type, missing required) -> errors. WARN (non-safety
    out-of-range) -> warnings, surfaced only when the section constructed
    successfully."""
    result = ConfigValidationResult()
    for section_name, data in sections.items():
        models = _SECTION_MODELS.get(section_name)
        if models is None:
            result.errors.append(
                f"[{section_name}] Unknown section. Allowed sections are: "
                f"{', '.join(sorted(_SECTION_MODELS))}."
            )
            continue
        strict_cls = models[0]
        try:
            settings = strict_cls(**data)
        except ValidationError as exc:
            result.errors.extend(_format_pydantic_errors(section_name, exc))
            continue
        # Section constructed successfully — run non-safety WARN checks.
        warn_checks = _WARN_CHECKS.get(section_name, [])
        for field_name, check, violation in warn_checks:
            value = getattr(settings, field_name, None)
            if value is not None and check(value):
                # Look up the alias for the operator-facing key name.
                field_info: FieldInfo = strict_cls.model_fields[field_name]
                key = field_info.alias or field_name
                result.warnings.append(
                    f"[{section_name}] {key} = {value}: {violation}."
                )
    return result


# ---------------------------------------------------------------------------
# INI loading helper — reads all sections from config.ini (baseline) + the
# optional rig-specific overlay, returning a per-section dict of raw string
# values ready for collect_config_errors. cfg_read only returns keys present
# in its defaults dict, so the defaults dict is built from each section
# model's Field aliases to capture every file key.
# ---------------------------------------------------------------------------


def load_sections_from_ini(
    baseline_path: str, overlay_path: str | None
) -> dict[str, dict[str, str]]:
    """Load all config.ini sections as raw string dicts, ready for
    ``collect_config_errors``.

    For each section in ``_SECTION_MODELS``, reads the baseline file via
    ``cfg_read`` (using the strict model's Field aliases as the defaults
    dict so every file key is captured), then merges the overlay file's
    values on top if ``overlay_path`` exists (overlay values win via dict
    update). Returns a ``dict[section_name, dict[key, raw_string_value]]``.
    """
    sections: dict[str, dict[str, str]] = {}
    for section_name, (strict_cls, _overlay_cls) in _SECTION_MODELS.items():
        # Build the defaults dict from the strict model's Field aliases so
        # cfg_read captures every file key (cfg_read only returns keys
        # present in the defaults dict — passing {} would yield {}).
        defaults_template: dict[str, str] = {}
        for field_info in strict_cls.model_fields.values():
            key = field_info.alias or field_info.name
            defaults_template[key] = ""
        # cfg_read mutates the passed dict in place, so pass a fresh copy.
        baseline = cfg_read(
            baseline_path, section_name, dict(defaults_template)
        )
        if overlay_path is not None and os.path.exists(overlay_path):
            overlay = cfg_read(
                overlay_path, section_name, dict(defaults_template)
            )
            # Only override baseline with keys the overlay file actually
            # contains. cfg_read fills every alias key from the defaults
            # dict, returning the "" sentinel for keys absent from the
            # overlay file — those sentinels must NOT clobber the
            # baseline's real values (a partial overlay would otherwise
            # wipe the tracked baseline and ValidationError on every
            # int/float/bool field the overlay did not re-list).
            baseline.update({k: v for k, v in overlay.items() if v != ""})
        sections[section_name] = baseline
    return sections


# ---------------------------------------------------------------------------
# ConfigValidator — collect-all validation with a modal QDialog abort path.
# validate_or_abort() runs collect_config_errors on the sections dict, shows
# a modal QDialog listing all errors (red, startup-blocking) and warnings
# (amber, advisory), then aborts via sys.exit(1) if any errors exist. If
# only warnings are present, the operator may proceed. PyQt5 is imported
# inside _show_dialog so the module stays importable without Qt for the
# pure-logic collect_config_errors tests.
# ---------------------------------------------------------------------------


class ConfigValidator:
    """Collect-all config validation with a modal QDialog abort path.

    The composition root (``main()``) calls ``validate_or_abort`` AFTER the
    DeviceBundle exists but BEFORE any collaborator or the shell is
    constructed (UI-SPEC order-of-operations). A REJECT-classified error
    aborts via ``sys.exit(1)`` before any Qt window shows.
    """

    def validate_or_abort(
        self, sections: dict[str, dict[str, str]]
    ) -> None:
        """Run collect-all validation on the sections dict. If any errors
        or warnings exist, show a modal QDialog. Abort via ``sys.exit(1)``
        if any errors exist OR the operator clicked "Exit" on a
        warnings-only dialog (reject result). On a warnings-only dialog
        the operator may click "Proceed with warnings" (accept) to
        continue."""
        result = collect_config_errors(sections)
        if not result.errors and not result.warnings:
            return
        accepted = self._show_dialog(result.errors, result.warnings)
        if result.errors or not accepted:
            sys.exit(1)

    def _show_dialog(
        self, errors: list[str], warnings: list[str]
    ) -> bool:
        """Show the collect-all config-error QDialog (D-03 / PKG-04).

        Layout: errors block (red header + per-error rows) first, then
        warnings block (amber header + per-warning rows), then a
        right-aligned button row with "Exit" (always, default) and
        "Proceed with warnings" (only if 0 errors and ≥1 warning).

        Returns ``True`` if the operator clicked "Proceed with warnings"
        (``QDialog.Accepted``) and ``False`` otherwise (``QDialog.Rejected``
        — the "Exit" button, window close, or ESC). The caller uses this
        to decide whether to abort on the warnings-only path: an errors
        dialog always aborts regardless of the return value.
        """
        from PyQt5.QtWidgets import (
            QDialog,
            QHBoxLayout,
            QLabel,
            QPushButton,
            QVBoxLayout,
        )

        dlg = QDialog()
        dlg.setWindowTitle("Configuration validation")
        dlg.setMinimumWidth(480)
        layout = QVBoxLayout(dlg)

        if errors:
            header = QLabel("✕ Errors — startup blocked")
            header.setStyleSheet("color: #FF3B30; font-weight: bold;")
            layout.addWidget(header)
            for e in errors:
                row = QLabel(f"✕ {e}")
                row.setWordWrap(True)
                layout.addWidget(row)

        if warnings:
            if errors:
                spacer = QLabel()
                spacer.setFixedHeight(32)
                layout.addWidget(spacer)
            header = QLabel("⚠ Warnings — review before proceeding")
            header.setStyleSheet("color: #FF9500; font-weight: bold;")
            layout.addWidget(header)
            for w in warnings:
                row = QLabel(f"⚠ {w}")
                row.setWordWrap(True)
                layout.addWidget(row)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        exit_btn = QPushButton("Exit")
        exit_btn.setDefault(True)
        exit_btn.clicked.connect(dlg.reject)
        btn_layout.addWidget(exit_btn)

        if warnings and not errors:
            proceed_btn = QPushButton("Proceed with warnings")
            proceed_btn.setStyleSheet("color: #34C759;")
            proceed_btn.clicked.connect(dlg.accept)
            btn_layout.addWidget(proceed_btn)

        layout.addLayout(btn_layout)
        dlg.setModal(True)
        return dlg.exec_() == QDialog.Accepted
