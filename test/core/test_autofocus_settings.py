"""Unit tests for the [Autofocus] config schema models."""

from typing import Any

import pytest
from pydantic import ValidationError

from lightsheet.config_schema import AutofocusSettings, AutofocusSettingsOverlay


def _autofocus_valid() -> dict[str, Any]:
    return {
        "Enabled": False,
        "Cadence": 1,
        "Residual Gain Mm": 0.05,
        "Max Residual Mm": 0.5,
        "Smoothing": 0.5,
        "Use Curve Seed": False,
    }


def test_autofocus_settings_defaults() -> None:
    s = AutofocusSettings()
    assert s.enabled is False
    assert s.cadence == 1
    assert s.residual_gain_mm == 0.05
    assert s.max_residual_mm == 0.5
    assert s.smoothing == 0.5
    assert s.use_curve_seed is False


def test_autofocus_settings_coerces_string_values() -> None:
    s = AutofocusSettings.model_validate({
        "Enabled": "True",
        "Cadence": "2",
        "Residual Gain Mm": "0.1",
        "Max Residual Mm": "0.2",
        "Smoothing": "0.3",
        "Use Curve Seed": "True",
    })
    assert s.enabled is True
    assert s.cadence == 2
    assert s.residual_gain_mm == 0.1
    assert s.max_residual_mm == 0.2
    assert s.smoothing == 0.3
    assert s.use_curve_seed is True


def test_autofocus_settings_rejects_cadence_out_of_range() -> None:
    with pytest.raises(ValidationError):
        AutofocusSettings.model_validate({**_autofocus_valid(), "Cadence": 0})
    with pytest.raises(ValidationError):
        AutofocusSettings.model_validate({**_autofocus_valid(), "Cadence": 1001})


def test_autofocus_settings_rejects_residual_gain_out_of_range() -> None:
    with pytest.raises(ValidationError):
        AutofocusSettings.model_validate({**_autofocus_valid(), "Residual Gain Mm": 1.5})
    with pytest.raises(ValidationError):
        AutofocusSettings.model_validate({**_autofocus_valid(), "Residual Gain Mm": -0.1})


def test_autofocus_settings_rejects_max_residual_out_of_range() -> None:
    with pytest.raises(ValidationError):
        AutofocusSettings.model_validate({**_autofocus_valid(), "Max Residual Mm": 5.5})
    with pytest.raises(ValidationError):
        AutofocusSettings.model_validate({**_autofocus_valid(), "Max Residual Mm": -0.1})


def test_autofocus_settings_rejects_smoothing_out_of_range() -> None:
    with pytest.raises(ValidationError):
        AutofocusSettings.model_validate({**_autofocus_valid(), "Smoothing": -0.1})
    with pytest.raises(ValidationError):
        AutofocusSettings.model_validate({**_autofocus_valid(), "Smoothing": 1.5})


def test_autofocus_settings_rejects_unknown_key() -> None:
    with pytest.raises(ValidationError) as exc_info:
        AutofocusSettings.model_validate({**_autofocus_valid(), "Unknown Key": 1})
    err_types = [e["type"] for e in exc_info.value.errors()]
    assert any("extra" in t or "forbidden" in t for t in err_types)


def test_autofocus_overlay_tolerates_extra_key() -> None:
    s = AutofocusSettingsOverlay.model_validate({**_autofocus_valid(), "Unknown Key": 1})
    assert s.cadence == 1
    assert s.smoothing == 0.5
