"""
PKG-04 pure-logic tests for lightsheet.config_schema — the two-tier
pydantic-settings config validation layer.

The strict baseline tier (extra='forbid') rejects unknown/typo'd keys instead
of silently falling into the configparser fallback (the PKG-04 root-cause bug).
The lax overlay tier (extra='ignore') tolerates extra keys in the rig-specific
overlay so rig calibration freedom is preserved. Safety-critical keys
([iBeam] Max Power, [Motors] * Limit High) are REJECTED (not clamped)
out-of-range in BOTH tiers via the same field_validator. Non-safety
out-of-range values (galvo/ETL amplitudes, negative exposure) are collected
as WARNings. Validation is collect-all: two independent errors surface in one
pass, not fail-fast.

Tests execute the real pydantic models + the collect-all entry point against
plain dict inputs (no file I/O — the models validate already-parsed dicts,
mirroring how cfg_read hands back a dict). Per AGENTS.md §5 this is the
pure-logic pattern (test_config.py / test_waveforms.py style); no Qt, no
hardware, no static-source grep.
"""

import pytest
from pydantic import ValidationError

from lightsheet.config_schema import (
    CameraSettings,
    CameraSettingsOverlay,
    ConfigValidationResult,
    ControllerSettings,
    ControllerSettingsOverlay,
    ETLsSettings,
    ETLsSettingsOverlay,
    IBeamSettings,
    IBeamSettingsOverlay,
    LasersSettings,
    LasersSettingsOverlay,
    LoggingSettings,
    LoggingSettingsOverlay,
    MotorsSettings,
    MotorsSettingsOverlay,
    SigGenSettings,
    SigGenSettingsOverlay,
    collect_config_errors,
)


def _ibeam_valid() -> dict:
    """A valid [iBeam] dict built from config.ini's actual values."""
    return {
        "Port": "COM4",
        "Baud Rate": 115200,
        "Channel": 1,
        "Wavelength": 640,
        "Power": 0,
        "Max Power": 150000,
        "Status Poll Interval": 1.0,
    }


def _motors_valid() -> dict:
    """A valid [Motors] dict built from config.ini's actual values."""
    return {
        "Port": "COM7",
        "Device Number Vertical": 1,
        "Device Number Horizontal": 2,
        "Device Number Camera": 3,
        "Vertical Inverted": False,
        "Vertical Units": "mm",
        "Vertical Origin": 48.5,
        "Vertical Limit Low": 0.0,
        "Vertical Limit High": 41.0,
        "Horizontal Inverted": False,
        "Horizontal Units": "mm",
        "Horizontal Origin": 0.0,
        "Horizontal Limit Low": 0.0,
        "Horizontal Limit High": 18.8,
        "Camera Inverted": False,
        "Camera Units": "mm",
        "Camera Origin": 20.0,
        "Camera Limit Low": 0.0,
        "Camera Limit High": 35.0,
    }


def _siggen_valid() -> dict:
    """A valid [SigGen] dict built from config.ini's actual values."""
    return {
        "AO Terminals": "/Dev1/ao0:3",
        "DO Terminals": "/Dev1/port0/line1",
        "Sample Rate": 40000,
        "Galvo Pre Time": 0.100,
        "Galvo Scan Time": 0.100,
        "Galvo Reset Time": 0.020,
        "Galvo Post Time": 0.020,
        "Galvo Activated": True,
        "Galvo Inverted": True,
        "Galvo Left Amplitude": 3.8,
        "Galvo Left Offset": -1.3,
        "Galvo Right Amplitude": 3.8,
        "Galvo Right Offset": -1.3,
        "ETL Activated": True,
        "ETL Steps": 5,
        "ETL Left Amplitude": 1.1,
        "ETL Left Offset": 2.4,
        "ETL Right Amplitude": 1.25,
        "ETL Right Offset": 3.0,
    }


def _camera_valid() -> dict:
    """A valid [Camera] dict built from config.ini's actual values."""
    return {
        "Shutter Mode": "Lightsheet",
        "Exposure Time": 100,
        "Lightsheet Line Time": 100.00,
        "Lightsheet Exposed Lines": 25,
        "Lightsheet Delay Lines": 225,
        "Recorder Timeout": 15,
        "Recorder Timeout Floor": 5,
        "Recorder Timeout Safety Factor": 3.0,
    }


def _controller_valid() -> dict:
    return {"Units": "mm"}


def _lasers_valid() -> dict:
    return {
        "Lasers Terminals": "/Dev7/ao0:1",
        "Laser1 Wavelength": 555,
        "Laser1 Power": 2,
        "Laser1 Max Power": 5,
        "Laser1 mW per Volt": 60,
    }


def _etls_valid() -> dict:
    return {"Port ETL Left": "COM5", "Port ETL Right": "COM6"}


def _logging_valid() -> dict:
    return {"Level": "INFO", "Log Dir": ""}


def _full_valid_config() -> dict[str, dict]:
    """All 8 sections built from config.ini's actual values."""
    return {
        "Controller": _controller_valid(),
        "Camera": _camera_valid(),
        "SigGen": _siggen_valid(),
        "Lasers": _lasers_valid(),
        "iBeam": _ibeam_valid(),
        "ETLs": _etls_valid(),
        "Motors": _motors_valid(),
        "Logging": _logging_valid(),
    }


# --- Test 1: strict baseline rejects unknown/typo'd key (extra_forbidden) ---


def test_strict_baseline_rejects_typo_key() -> None:
    """A typo'd key ('Max power' lowercase-p alongside the real 'Max Power')
    is rejected by the strict baseline tier with an extra_forbidden error."""
    data = {**_ibeam_valid(), "Max power": 100}  # typo'd extra key
    with pytest.raises(ValidationError) as exc_info:
        IBeamSettings(**data)
    # The error list must contain an extra-forbidden type for the typo'd key.
    err_types = [e["type"] for e in exc_info.value.errors()]
    assert any("extra" in t or "forbidden" in t for t in err_types), (
        f"expected an extra_forbidden error type, got {err_types}"
    )


# --- Test 2: lax overlay tolerates extra key (extra='ignore') ---


def test_lax_overlay_tolerates_extra_key() -> None:
    """The lax overlay tier (extra='ignore') silently ignores an extra key
    so rig calibration freedom is preserved in config.rig-specific.ini."""
    data = {**_ibeam_valid(), "Calibration Note": "rig-specific tweak"}
    # Should construct without error — the extra key is ignored.
    settings = IBeamSettingsOverlay(**data)
    assert settings.max_power == 150000


# --- Test 3: safety-key (Max Power) rejected in BOTH tiers ---


def test_max_power_rejected_in_both_tiers() -> None:
    """[iBeam] Max Power = 200000 (>150000 µW = 150 mW iBeam hard limit)
    raises ValidationError on BOTH the strict baseline and the lax overlay
    — safety-key rejection is tier-independent."""
    strict_data = {**_ibeam_valid(), "Max Power": 200000}
    overlay_data = {**_ibeam_valid(), "Max Power": 200000}
    with pytest.raises(ValidationError):
        IBeamSettings(**strict_data)
    with pytest.raises(ValidationError):
        IBeamSettingsOverlay(**overlay_data)


# --- Test 4: safety-key (Vertical Limit High) rejected in BOTH tiers ---


def test_vertical_limit_high_rejected_in_both_tiers() -> None:
    """[Motors] Vertical Limit High = 50.0 (>41.0 mm per AGENTS.md §2
    mechanical limit) raises ValidationError on both tiers."""
    strict_data = {**_motors_valid(), "Vertical Limit High": 50.0}
    overlay_data = {**_motors_valid(), "Vertical Limit High": 50.0}
    with pytest.raises(ValidationError):
        MotorsSettings(**strict_data)
    with pytest.raises(ValidationError):
        MotorsSettingsOverlay(**overlay_data)


# --- Test 5: valid [iBeam] dict constructs without error ---


def test_valid_ibeam_constructs_without_error() -> None:
    """A valid [iBeam] dict built from config.ini's actual values
    (Max Power = 150000) constructs without error on the strict tier."""
    settings = IBeamSettings(**_ibeam_valid())
    assert settings.max_power == 150000
    assert settings.port == "COM4"


# --- Test 6: collect-all surfaces BOTH independent errors ---


def test_collect_config_errors_surfaces_both_errors() -> None:
    """collect_config_errors called with TWO independently-broken sections
    (bad Max Power + bad Vertical Limit High) returns a result containing
    BOTH errors, not just the first — proves collect-all, not fail-fast."""
    sections = {
        "iBeam": {**_ibeam_valid(), "Max Power": 200000},
        "Motors": {**_motors_valid(), "Vertical Limit High": 50.0},
    }
    result = collect_config_errors(sections)
    assert isinstance(result, ConfigValidationResult)
    assert len(result.errors) == 2, (
        f"expected 2 errors (collect-all), got {len(result.errors)}: "
        f"{result.errors}"
    )
    assert result.warnings == []


# --- Test 7: non-safety out-of-range collected as WARN, not error ---


def test_collect_config_errors_galvo_amplitude_is_warning() -> None:
    """collect_config_errors called with a [SigGen] dict where
    Galvo Left Amplitude = 12.5 (>±10 V, non-safety) returns the item in
    the warnings list, not the errors list."""
    sections = {"SigGen": {**_siggen_valid(), "Galvo Left Amplitude": 12.5}}
    result = collect_config_errors(sections)
    assert result.errors == [], (
        f"expected no errors for non-safety out-of-range, got {result.errors}"
    )
    assert len(result.warnings) == 1, (
        f"expected 1 warning for galvo amplitude, got {len(result.warnings)}: "
        f"{result.warnings}"
    )


# --- Test 8: fully valid config returns empty errors and warnings ---


def test_collect_config_errors_valid_config_is_clean() -> None:
    """collect_config_errors called with a fully valid config (all 8
    sections built from config.ini's real values) returns errors == [] and
    warnings == [] — silence is the success state."""
    result = collect_config_errors(_full_valid_config())
    assert result.errors == [], (
        f"expected no errors for valid config, got {result.errors}"
    )
    assert result.warnings == [], (
        f"expected no warnings for valid config, got {result.warnings}"
    )


# --- Test 9: case-sensitive aliases — wrong case rejected on strict tier ---


def test_motors_aliases_are_case_sensitive() -> None:
    """The [Motors] model's field aliases resolve 'Vertical Limit High'
    case-sensitively — passing 'vertical limit high' (wrong case) to the
    strict tier raises ValidationError (case_sensitive=True, Pitfall 5)."""
    data = {**_motors_valid()}
    # Replace the correct-case key with a wrong-case variant.
    del data["Vertical Limit High"]
    data["vertical limit high"] = 50.0
    with pytest.raises(ValidationError):
        MotorsSettings(**data)
