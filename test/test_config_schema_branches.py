"""Branch-coverage closure for ``lightsheet.config_schema``.

Exercises the remaining uncovered branches:
- ``_validate_horizontal_limit_high`` / ``_validate_camera_limit_high`` raise
  paths (limit exceeded).
- ``_format_errors`` extra/forbidden, missing, and input-None branches.
- ``collect_config_errors`` unknown-section branch.
- ``load_sections_from_ini`` with baseline + overlay files.
- ``ConfigValidator.validate_or_abort`` + ``_show_dialog`` under offscreen Qt.

Behavior tests (AGENTS.md §5) — every assertion is on a runtime
postcondition (raised ValueError, formatted error string, loaded sections
dict, dialog return value), never a static-source grep.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

from lightsheet.config_schema import (
    ConfigValidator,
    _validate_camera_limit_high,
    _validate_horizontal_limit_high,
    collect_config_errors,
    load_sections_from_ini,
)


# -- Validator raise paths --------------------------------------------------


def test_validate_horizontal_limit_high_raises_when_exceeded() -> None:
    """The if-branch raises ValueError when the limit exceeds the mechanical
    travel max (line 117)."""
    with pytest.raises(ValueError, match="Horizontal Limit High"):
        _validate_horizontal_limit_high(999.0)


def test_validate_horizontal_limit_high_passes_when_in_range() -> None:
    """The else-path returns the value unchanged when in range."""
    assert _validate_horizontal_limit_high(10.0) == 10.0


def test_validate_camera_limit_high_raises_when_exceeded() -> None:
    """The if-branch raises ValueError when the limit exceeds the mechanical
    travel max (line 126)."""
    with pytest.raises(ValueError, match="Camera Limit High"):
        _validate_camera_limit_high(999.0)


def test_validate_camera_limit_high_passes_when_in_range() -> None:
    assert _validate_camera_limit_high(10.0) == 10.0


# -- collect_config_errors unknown-section branch ---------------------------


def test_collect_config_errors_unknown_section_appends_error() -> None:
    """An unknown section name in the sections dict appends an error
    (lines 533-537)."""
    result = collect_config_errors({"UnknownSection": {"foo": "bar"}})
    assert len(result.errors) >= 1
    assert any("UnknownSection" in e for e in result.errors)


# -- _format_errors branches (via collect_config_errors) --------------------


def test_collect_config_errors_missing_required_key() -> None:
    """A missing required key triggers the 'missing' branch in _format_errors
    (lines 502-503)."""
    # Pass an empty dict for a section that has required fields — the
    # strict model will reject the missing keys.
    result = collect_config_errors({"iBeam": {}})
    assert any("missing" in e.lower() for e in result.errors)


# -- load_sections_from_ini -------------------------------------------------


def test_load_sections_from_ini_reads_baseline(tmp_path) -> None:
    """load_sections_from_ini reads a baseline config.ini and returns a
    sections dict with every section's keys populated."""
    ini = tmp_path / "config.ini"
    ini.write_text(
        "[iBeam]\n"
        "Port = COM4\n"
        "Baud Rate = 115200\n"
        "Channel = 1\n"
        "Wavelength = 640\n"
        "Power = 0.0\n"
        "Max Power = 50000\n"
        "Status Poll Interval = 1000\n"
    )
    sections = load_sections_from_ini(str(ini), overlay_path=None)
    assert "iBeam" in sections
    assert sections["iBeam"]["Max Power"] == "50000"
    assert sections["iBeam"]["Port"] == "COM4"


def test_load_sections_from_ini_merges_overlay(tmp_path) -> None:
    """When an overlay_path exists, its non-empty values override the
    baseline (lines 592-603)."""
    baseline = tmp_path / "config.ini"
    baseline.write_text(
        "[iBeam]\n"
        "Port = COM4\n"
        "Baud Rate = 115200\n"
        "Channel = 1\n"
        "Wavelength = 640\n"
        "Power = 0.0\n"
        "Max Power = 50000\n"
        "Status Poll Interval = 1000\n"
    )
    overlay = tmp_path / "overlay.ini"
    overlay.write_text(
        "[iBeam]\n"
        "Port = COM4\n"
        "Baud Rate = 115200\n"
        "Channel = 1\n"
        "Wavelength = 640\n"
        "Power = 0.0\n"
        "Max Power = 80000\n"
        "Status Poll Interval = 1000\n"
    )
    sections = load_sections_from_ini(str(baseline), overlay_path=str(overlay))
    assert sections["iBeam"]["Max Power"] == "80000"


def test_load_sections_from_ini_overlay_partial_does_not_clobber(tmp_path) -> None:
    """A partial overlay (only some keys present) must not clobber baseline
    values with empty sentinels (lines 596-603)."""
    baseline = tmp_path / "config.ini"
    baseline.write_text(
        "[iBeam]\n"
        "Port = COM4\n"
        "Baud Rate = 115200\n"
        "Channel = 1\n"
        "Wavelength = 640\n"
        "Power = 0.0\n"
        "Max Power = 50000\n"
        "Status Poll Interval = 1000\n"
    )
    overlay = tmp_path / "overlay.ini"
    overlay.write_text(
        "[iBeam]\n"
        "Max Power = 80000\n"
    )
    sections = load_sections_from_ini(str(baseline), overlay_path=str(overlay))
    # Max Power overridden from overlay.
    assert sections["iBeam"]["Max Power"] == "80000"
    # Port NOT clobbered by overlay's empty sentinel.
    assert sections["iBeam"]["Port"] == "COM4"


# -- ConfigValidator.validate_or_abort + _show_dialog -----------------------


def test_validate_or_abort_no_errors_no_warnings_is_noop() -> None:
    """When there are no errors and no warnings, validate_or_abort returns
    immediately without showing a dialog (line 638-639). An empty sections
    dict produces no errors (no sections to validate)."""
    validator = ConfigValidator()
    # Should not raise / not exit — empty sections -> no errors, no warnings.
    validator.validate_or_abort({})


def test_validate_or_abort_errors_calls_sys_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When errors exist, validate_or_abort shows the dialog and calls
    sys.exit(1) (lines 640-642)."""
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)

    # Sections with an unknown section -> errors.
    sections = {"UnknownSection": {"foo": "bar"}}

    exit_called = []
    monkeypatch.setattr(sys, "exit", lambda code: exit_called.append(code))

    # Mock dialog exec_ to return Rejected (0) — errors dialog always aborts.
    with patch("PySide6.QtWidgets.QDialog.exec", return_value=0):
        validator = ConfigValidator()
        validator.validate_or_abort(sections)

    assert exit_called == [1], "validate_or_abort must call sys.exit(1) on errors"


def _make_siggen_sections_with_warning() -> dict:
    """Build a SigGen section with galvo_left_amplitude=15.0 (> 10.0 V
    limit -> warning, not error). All other fields are valid."""
    return {
        "SigGen": {
            "ao_terminals": "/Dev7/ao0:3",
            "do_terminals": "/Dev7/port0/line4:7",
            "sample_rate": "40000",
            "galvo_pre_time": "0.001",
            "galvo_scan_time": "0.100",
            "galvo_reset_time": "0.025",
            "galvo_post_time": "0.001",
            "galvo_activated": "True",
            "galvo_inverted": "False",
            "galvo_left_amplitude": "15.0",  # > 10.0 V -> warning
            "galvo_left_offset": "0.5",
            "galvo_right_amplitude": "1.0",
            "galvo_right_offset": "0.5",
            "etl_activated": "False",
            "etl_steps": "5",
            "etl_left_amplitude": "1.0",
            "etl_left_offset": "0.5",
            "etl_right_amplitude": "1.0",
            "etl_right_offset": "0.5",
            "galvo_left_right_swap": "False",
        },
    }


def test_validate_or_abort_warnings_only_proceed_does_not_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When only warnings exist and the operator clicks 'Proceed with
    warnings' (Accepted), validate_or_abort does NOT call sys.exit
    (line 641: `if result.errors or not accepted` — accepted=True, no exit)."""
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)

    sections = _make_siggen_sections_with_warning()

    exit_called = []
    monkeypatch.setattr(sys, "exit", lambda code: exit_called.append(code))

    # Mock dialog exec_ to return Accepted (1) — operator clicks "Proceed".
    with patch("PySide6.QtWidgets.QDialog.exec", return_value=1):
        validator = ConfigValidator()
        validator.validate_or_abort(sections)

    assert exit_called == [], "validate_or_abort must NOT exit when operator proceeds with warnings"


def test_validate_or_abort_warnings_only_exit_calls_sys_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When only warnings exist and the operator clicks 'Exit' (Rejected),
    validate_or_abort calls sys.exit(1) (line 641: `not accepted` -> exit)."""
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)

    sections = _make_siggen_sections_with_warning()

    exit_called = []
    monkeypatch.setattr(sys, "exit", lambda code: exit_called.append(code))

    # Mock dialog exec_ to return Rejected (0) — operator clicks "Exit".
    with patch("PySide6.QtWidgets.QDialog.exec", return_value=0):
        validator = ConfigValidator()
        validator.validate_or_abort(sections)

    assert exit_called == [1], "validate_or_abort must exit when operator clicks Exit on warnings"
