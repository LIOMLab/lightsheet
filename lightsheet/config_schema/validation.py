"""Config-schema validation service — collect-all startup gate.

``collect_config_errors`` and ``ConfigValidator`` iterate every config
section, gather every per-section error and non-safety warning in one pass,
and show a modal QDialog abort path. Cross-section checks (e.g. adaptive
laser bounds vs. configured laser maxima) run after per-section validation.
"""

import configparser
import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings

from lightsheet.config import cfg_read

from .sections.adaptive import AdaptiveSettings, AdaptiveSettingsOverlay
from .sections.autofocus import AutofocusSettings, AutofocusSettingsOverlay
from .sections.camera import CameraSettings, CameraSettingsOverlay
from .sections.controller import ControllerSettings, ControllerSettingsOverlay
from .sections.etls import ETLsSettings, ETLsSettingsOverlay
from .sections.focus import FocusSettings, FocusSettingsOverlay
from .sections.ibeam import IBeamSettings, IBeamSettingsOverlay
from .sections.lasers import LasersSettings, LasersSettingsOverlay
from .sections.logging import LoggingSettings, LoggingSettingsOverlay
from .sections.motors import MotorsSettings, MotorsSettingsOverlay
from .sections.siggen import SigGenSettings, SigGenSettingsOverlay

logger = logging.getLogger(__name__)

# Safety-critical constants, the no-env base, the overlay factory, and the
# hard-limit validators live in shared.py so the section modules can import
# them without creating cycles.

# --- Non-safety recommended ranges (WARN, not REJECT) ---
_GALVO_VOLTAGE_LIMIT: float = 10.0  # ±10 V NI-6363 AO range
# ETL drive is a 0-5 V analog input to the EL-10-30 lens driver, which maps
# it to its 0-292.84 mA coil-current range internally. The config [SigGen]
# ETL Amplitude values are volts (the DAQ AO drive), so the warn check
# compares volts against the 5 V analog input range.
_ETL_VOLTAGE_LIMIT: float = 5.0  # 0-5 V Optotune EL-10-30 analog input


# ---------------------------------------------------------------------------
# Collect-all entry point — iterate ALL sections, collect every error +
# warning into two lists BEFORE any dialog is shown. REJECT (safety
# out-of-range, unknown key, wrong type, missing required) -> errors list.
# WARN (non-safety out-of-range: galvo >+-10 V, ETL drive >0-5 V, negative
# exposure) -> warnings list. Construction uses the STRICT tier for
# baseline-tier error classification.
# ---------------------------------------------------------------------------


@dataclass
class ConfigValidationResult:
    """Collect-all validation result — errors block startup, warnings are advisory."""

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
    "Adaptive": (AdaptiveSettings, AdaptiveSettingsOverlay),
    "Autofocus": (AutofocusSettings, AutofocusSettingsOverlay),
    "Focus": (FocusSettings, FocusSettingsOverlay),
}

# Optional baseline sections — a config.ini without one of these sections
# validates using the model defaults. Sections NOT in this set are required.
_OPTIONAL_SECTIONS: frozenset[str] = frozenset({"Adaptive", "Autofocus", "Focus"})


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
        (
            "galvo_left_amplitude",
            _galvo_amplitude_warn,
            "is above the galvo voltage limit",
        ),
        (
            "galvo_right_amplitude",
            _galvo_amplitude_warn,
            "is above the galvo voltage limit",
        ),
        (
            "etl_left_amplitude",
            _etl_amplitude_warn,
            "is outside the ETL drive voltage range",
        ),
        (
            "etl_right_amplitude",
            _etl_amplitude_warn,
            "is outside the ETL drive voltage range",
        ),
    ],
    "Camera": [
        ("exposure_time", _exposure_time_warn, "is negative"),
    ],
}


def _format_pydantic_errors(section: str, err: ValidationError) -> list[str]:
    """Translate pydantic ValidationError errors into operator-readable rows."""
    rows: list[str] = []
    for e in err.errors():
        loc = ".".join(str(part) for part in e["loc"])
        etype = e["type"]
        if "extra" in etype or "forbidden" in etype:
            # Unknown/typo'd key — loc is the alias of the offending key.
            key = loc
            rows.append(
                f'[{section}] Unknown key "{key}". Remove it or correct the spelling.'
            )
        elif "missing" in etype:
            key = loc
            rows.append(
                f'[{section}] Required key "{key}" is missing. Add it '
                f"with the correct type and value."
            )
        else:
            # Type/range/safety rejection — surface the value + a short
            # operator-readable violation phrase from the validator message.
            msg = e.get("msg", "is invalid")
            input_val = e.get("input")
            if input_val is not None:
                rows.append(f"[{section}] {loc} = {input_val!r}: {msg}.")
            else:
                rows.append(f"[{section}] {loc}: {msg}.")
    return rows


def collect_config_errors(
    sections: dict[str, dict],  # ty: ignore[missing-type-argument]
) -> ConfigValidationResult:
    """Validate all sections collect-all: every error and warning surfaces
    in one pass, not fail-fast on the first."""
    result = ConfigValidationResult()
    # Track the constructed settings objects so cross-section checks can
    # compare fields across sections after every section validated.
    constructed: dict[str, BaseSettings] = {}
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
        constructed[section_name] = settings
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
    # Cross-section safety checks — reject (never clamp) adaptive laser
    # maxima above the configured laser maxima.
    _cross_section_adaptive_power(result, constructed)
    return result


def _cross_section_adaptive_power(
    result: ConfigValidationResult,
    constructed: dict[str, BaseSettings],
) -> None:
    """Reject adaptive laser maxima above the configured laser maxima.

    Both checks are collect-all: a config violating both surfaces two
    errors in one pass. The comparison is strict (>) so a value sitting
    exactly at the configured maximum is accepted.
    """
    adaptive = constructed.get("Adaptive")
    if adaptive is None:
        # [Adaptive] absent or failed per-section validation — nothing
        # to compare. A per-section failure is already in result.errors.
        return
    lasers = constructed.get("Lasers")
    if lasers is not None:
        l1_max = float(lasers.laser1_max_power)  # ty: ignore[unresolved-attribute]
        adaptive_l1_max = float(adaptive.laser1_max_power)  # ty: ignore[unresolved-attribute]
        if adaptive_l1_max > l1_max:
            result.errors.append(
                f"[Adaptive] Laser1 Max Power = {adaptive_l1_max} mW exceeds "
                f"[Lasers] Laser1 Max Power = {l1_max} mW. Lower the "
                f"adaptive bound or raise the configured laser maximum."
            )
    ibeam = constructed.get("iBeam")
    if ibeam is not None:
        # [iBeam] Max Power is in uW; convert to mW for the comparison.
        l2_max_mw = float(ibeam.max_power) / 1000.0  # ty: ignore[unresolved-attribute]
        adaptive_l2_max = float(adaptive.laser2_max_power)  # ty: ignore[unresolved-attribute]
        if adaptive_l2_max > l2_max_mw:
            result.errors.append(
                f"[Adaptive] Laser2 Max Power = {adaptive_l2_max} mW exceeds "
                f"[iBeam] Max Power = {l2_max_mw:.1f} mW (150000 uW / 1000). "
                f"Lower the adaptive bound or raise the configured laser "
                f"maximum."
            )


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
    ``collect_config_errors``."""
    sections: dict[str, dict[str, str]] = {}
    # Detect which sections the baseline file actually contains so an
    # absent OPTIONAL section (e.g. [Adaptive]) is supplied as {} and the
    # pydantic model defaults apply — never an empty-string parse failure.
    _base_cfg = configparser.ConfigParser()
    _base_cfg.optionxform = str  # preserve case  # ty: ignore[invalid-assignment]
    _base_cfg.read(baseline_path)
    for section_name, (strict_cls, _overlay_cls) in _SECTION_MODELS.items():
        # An optional section absent from the baseline file is supplied
        # as {} so the pydantic model defaults apply.
        if section_name in _OPTIONAL_SECTIONS and not _base_cfg.has_section(
            section_name
        ):
            sections[section_name] = {}
            continue
        # Build the defaults dict from the strict model's Field aliases so
        # cfg_read captures every file key.
        defaults_template: dict[str, str] = {}
        for field_info in strict_cls.model_fields.values():
            key = field_info.alias or field_info.name
            defaults_template[key] = ""
        # cfg_read mutates the passed dict in place, so pass a fresh copy.
        baseline = cfg_read(baseline_path, section_name, dict(defaults_template))
        if overlay_path is not None and Path(overlay_path).exists():
            overlay = cfg_read(overlay_path, section_name, dict(defaults_template))
            # Only override baseline with keys the overlay file actually
            # contains. cfg_read fills every alias key from the defaults
            # dict, returning the "" sentinel for keys absent from the
            # overlay file — those sentinels must NOT clobber the
            # baseline's real values. Determine the set of keys the
            # overlay section actually contains via configparser and merge
            # only those — an explicitly-empty value propagates as "".
            _ov_cfg = configparser.ConfigParser()
            _ov_cfg.optionxform = str  # preserve case  # ty: ignore[invalid-assignment]
            _ov_cfg.read(overlay_path)
            present_keys = (
                set(_ov_cfg[section_name].keys())
                if _ov_cfg.has_section(section_name)
                else set()
            )
            baseline.update({k: v for k, v in overlay.items() if k in present_keys})
        sections[section_name] = baseline
    return sections


# ---------------------------------------------------------------------------
# ConfigValidator — collect-all validation with a modal QDialog abort path.
# validate_or_abort() runs collect_config_errors, shows a modal QDialog
# listing all errors (red) and warnings (amber), then aborts via sys.exit(1)
# if any errors exist. PySide6 is imported inside _show_dialog so the module
# stays importable without Qt for pure-logic tests.
# ---------------------------------------------------------------------------


class ConfigValidator:
    """Collect-all config validation with a modal QDialog abort path."""

    def validate_or_abort(self, sections: dict[str, dict[str, str]]) -> None:
        """Run collect-all validation. Abort via sys.exit(1) if any errors
        exist OR the operator clicked "Exit" on a warnings-only dialog."""
        result = collect_config_errors(sections)
        if not result.errors and not result.warnings:
            return
        accepted = self._show_dialog(result.errors, result.warnings)
        if result.errors or not accepted:
            sys.exit(1)

    def _show_dialog(self, errors: list[str], warnings: list[str]) -> bool:
        """Show the collect-all config-error QDialog.

        Returns True if the operator clicked "Proceed with warnings"
        and False otherwise.
        """
        from PySide6.QtWidgets import (
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
        return dlg.exec() == QDialog.DialogCode.Accepted
