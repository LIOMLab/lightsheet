"""Two-tier pydantic-settings config schema — package compatibility barrel.

This module re-exports the section models and validation helpers from their
focused submodules. It contains no logic; all implementation lives in
``lightsheet.config_schema.sections`` and ``lightsheet.config_schema.validation``.
"""

from lightsheet.config_schema.sections import (
    AdaptiveSettings,
    AdaptiveSettingsOverlay,
    CameraSettings,
    CameraSettingsOverlay,
    ControllerSettings,
    ControllerSettingsOverlay,
    ETLsSettings,
    ETLsSettingsOverlay,
    FocusSettings,
    FocusSettingsOverlay,
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
)
from lightsheet.config_schema.shared import (
    _make_overlay,
    _NoEnvBaseSettings,
    _validate_camera_limit_high,
    _validate_horizontal_limit_high,
)
from lightsheet.config_schema.validation import (
    ConfigValidationResult,
    ConfigValidator,
    collect_config_errors,
    load_sections_from_ini,
)

__all__ = [
    "AdaptiveSettings",
    "AdaptiveSettingsOverlay",
    "CameraSettings",
    "CameraSettingsOverlay",
    "ConfigValidationResult",
    "ConfigValidator",
    "ControllerSettings",
    "ControllerSettingsOverlay",
    "ETLsSettings",
    "ETLsSettingsOverlay",
    "FocusSettings",
    "FocusSettingsOverlay",
    "IBeamSettings",
    "IBeamSettingsOverlay",
    "LasersSettings",
    "LasersSettingsOverlay",
    "LoggingSettings",
    "LoggingSettingsOverlay",
    "MotorsSettings",
    "MotorsSettingsOverlay",
    "SigGenSettings",
    "SigGenSettingsOverlay",
    "_NoEnvBaseSettings",
    "_make_overlay",
    "_validate_camera_limit_high",
    "_validate_horizontal_limit_high",
    "collect_config_errors",
    "load_sections_from_ini",
]
