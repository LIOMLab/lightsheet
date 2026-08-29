"""FieldSpecSpinBox — promoted QDoubleSpinBox subclass with focus-gated
wheel + Ctrl/Shift page-step, driven by a declarative FieldSpec policy table.

Mock-testable under ``QT_QPA_PLATFORM=offscreen`` via synthesized QWheelEvent
and QApplication.keyboardModifiers monkeypatching.
"""

from __future__ import annotations

import dataclasses

import pytest

pytest.importorskip("PySide6")


# Canonical 22 objectName keys from the UI-SPEC FieldSpec Policy Table.
EXPECTED_FIELD_SPEC_KEYS = [
    "doubleSpinBox_sampleHPosition",
    "doubleSpinBox_sampleVPosition",
    "doubleSpinBox_cameraPosition",
    "doubleSpinBox_sampleStepSize",
    "doubleSpinBox_cameraStepSize",
    "doubleSpinBox_acqFirstPlane",
    "doubleSpinBox_acqLastPlane",
    "doubleSpinBox_acqPlaneStepSize",
    "doubleSpinBox_etlLeftAmplitude",
    "doubleSpinBox_etlRightAmplitude",
    "doubleSpinBox_etlLeftOffset",
    "doubleSpinBox_etlRightOffset",
    "doubleSpinBox_etlSteps",
    "doubleSpinBox_galvoLeftAmplitude",
    "doubleSpinBox_galvoRightAmplitude",
    "doubleSpinBox_galvoLeftOffset",
    "doubleSpinBox_galvoRightOffset",
    "doubleSpinBox_cameraExposureTime",
    "doubleSpinBox_cameraLineTime",
    "doubleSpinBox_cameraExposedLines",
    "doubleSpinBox_cameraDelayLines",
    "doubleSpinBox_laserOneAmplitude",
    "doubleSpinBox_laserTwoAmplitude",
]


def _make_spinbox(qtbot):
    from lightsheet.gui.widgets.field_spec_spinbox import FieldSpecSpinBox

    sb = FieldSpecSpinBox()
    sb.resize(160, 32)
    qtbot.addWidget(sb)
    sb.show()
    qtbot.waitExposed(sb)
    return sb


# ---------------------------------------------------------------------------
# FieldSpec dataclass
# ---------------------------------------------------------------------------


def test_field_spec_is_frozen_dataclass() -> None:
    from lightsheet.gui.widgets.field_spec import FieldSpec

    assert dataclasses.is_dataclass(FieldSpec)
    fields = [f.name for f in dataclasses.fields(FieldSpec)]
    assert fields == ["unit", "decimals", "single_step", "page_step", "minimum", "maximum"]
    spec = FieldSpec(unit="mm", decimals=3, single_step=0.1, page_step=1.0, minimum=0.0, maximum=41.0)
    assert spec.unit == "mm"
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.unit = "um"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_spinbox_constructs_with_parent_none(qtbot) -> None:
    from lightsheet.gui.widgets.field_spec_spinbox import FieldSpecSpinBox

    sb = FieldSpecSpinBox(parent=None)
    qtbot.addWidget(sb)
    assert sb._spec is None


def test_spinbox_constructs_with_parent(qtbot) -> None:
    from PySide6.QtWidgets import QWidget

    from lightsheet.gui.widgets.field_spec_spinbox import FieldSpecSpinBox

    parent = QWidget()
    qtbot.addWidget(parent)
    sb = FieldSpecSpinBox(parent=parent)
    assert sb.parent() is parent


# ---------------------------------------------------------------------------
# applySpec
# ---------------------------------------------------------------------------


def test_apply_spec_sets_all_properties(qtbot) -> None:
    from lightsheet.gui.widgets.field_spec import FieldSpec

    sb = _make_spinbox(qtbot)
    sb.applySpec(FieldSpec(unit="mm", decimals=3, single_step=0.1, page_step=1.0, minimum=0.0, maximum=41.0))
    assert sb.suffix() == " mm"
    assert sb.decimals() == 3
    assert sb.singleStep() == pytest.approx(0.1)
    assert sb.minimum() == pytest.approx(0.0)
    assert sb.maximum() == pytest.approx(41.0)
    assert sb._spec is not None


def test_apply_spec_empty_unit_no_leading_space(qtbot) -> None:
    from lightsheet.gui.widgets.field_spec import FieldSpec

    sb = _make_spinbox(qtbot)
    sb.applySpec(FieldSpec(unit="", decimals=0, single_step=1, page_step=10, minimum=0, maximum=1000))
    assert sb.suffix() == ""


# ---------------------------------------------------------------------------
# Wheel gate (focus-gated)
# ---------------------------------------------------------------------------


def _make_wheel_event(angle_delta=120):
    """Synthesize a QWheelEvent with a positive (up) angle delta."""
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent

    pos = QPointF(80.0, 16.0)
    global_pos = QPointF(80.0, 16.0)
    pixel_delta = QPoint(0, 0)
    angle = QPoint(0, int(angle_delta))
    return QWheelEvent(
        pos,
        global_pos,
        pixel_delta,
        angle,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )


def test_wheel_ignored_when_unfocused(qtbot) -> None:
    from PySide6.QtWidgets import QApplication, QLineEdit

    from lightsheet.gui.widgets.field_spec import FieldSpec

    sb = _make_spinbox(qtbot)
    sb.applySpec(FieldSpec(unit="mm", decimals=3, single_step=0.1, page_step=1.0, minimum=0.0, maximum=41.0))
    sb.setValue(5.0)
    # clearFocus() alone does not remove focus when the spinbox is the only
    # focusable widget in the window — Qt re-assigns focus to it. Give focus
    # to a separate widget so the spinbox genuinely loses focus.
    other = QLineEdit(sb.parentWidget() if sb.parentWidget() is not None else None)
    other.show()
    qtbot.addWidget(other)
    other.setFocus()
    sb.clearFocus()
    QApplication.processEvents()
    assert not sb.hasFocus()

    evt = _make_wheel_event(angle_delta=120)
    QApplication.sendEvent(sb, evt)
    # Event must be ignored (not accepted) and value unchanged.
    assert not evt.isAccepted()
    assert sb.value() == pytest.approx(5.0)


def test_wheel_steps_value_when_focused(qtbot) -> None:
    from PySide6.QtWidgets import QApplication

    from lightsheet.gui.widgets.field_spec import FieldSpec

    sb = _make_spinbox(qtbot)
    sb.applySpec(FieldSpec(unit="mm", decimals=3, single_step=0.1, page_step=1.0, minimum=0.0, maximum=41.0))
    sb.setValue(5.0)
    sb.setFocus()
    QApplication.processEvents()
    sb.activateWindow()
    QApplication.processEvents()
    assert sb.hasFocus()

    evt = _make_wheel_event(angle_delta=120)
    QApplication.sendEvent(sb, evt)
    assert sb.value() > 5.0


# ---------------------------------------------------------------------------
# stepBy page-step (Ctrl/Shift)
# ---------------------------------------------------------------------------


def test_step_by_no_modifier_uses_single_step(qtbot) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from lightsheet.gui.widgets.field_spec import FieldSpec

    sb = _make_spinbox(qtbot)
    sb.applySpec(FieldSpec(unit="mm", decimals=3, single_step=0.1, page_step=1.0, minimum=0.0, maximum=41.0))
    sb.setValue(5.0)

    # No modifier: stepBy(1) advances by single_step (0.1).
    QApplication.setKeyboardModifiers(Qt.KeyboardModifier.NoModifier) if hasattr(
        QApplication, "setKeyboardModifiers"
    ) else None
    sb.stepBy(1)
    assert sb.value() == pytest.approx(5.1)


def test_step_by_control_modifier_uses_page_step(qtbot, monkeypatch) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from lightsheet.gui.widgets.field_spec import FieldSpec

    sb = _make_spinbox(qtbot)
    sb.applySpec(FieldSpec(unit="mm", decimals=3, single_step=0.1, page_step=1.0, minimum=0.0, maximum=41.0))
    sb.setValue(5.0)

    monkeypatch.setattr(
        QApplication, "keyboardModifiers", staticmethod(lambda: Qt.KeyboardModifier.ControlModifier)
    )
    sb.stepBy(1)
    # page_step / single_step = 1.0 / 0.1 = 10 → 10 single steps = +1.0
    assert sb.value() == pytest.approx(6.0)


def test_step_by_shift_modifier_uses_page_step(qtbot, monkeypatch) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from lightsheet.gui.widgets.field_spec import FieldSpec

    sb = _make_spinbox(qtbot)
    sb.applySpec(FieldSpec(unit="mm", decimals=3, single_step=0.1, page_step=1.0, minimum=0.0, maximum=41.0))
    sb.setValue(5.0)

    monkeypatch.setattr(
        QApplication, "keyboardModifiers", staticmethod(lambda: Qt.KeyboardModifier.ShiftModifier)
    )
    sb.stepBy(1)
    assert sb.value() == pytest.approx(6.0)


def test_step_by_negative_with_modifier_decrements(qtbot, monkeypatch) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from lightsheet.gui.widgets.field_spec import FieldSpec

    sb = _make_spinbox(qtbot)
    sb.applySpec(FieldSpec(unit="V", decimals=2, single_step=0.05, page_step=0.5, minimum=-10.0, maximum=10.0))
    sb.setValue(0.0)

    monkeypatch.setattr(
        QApplication, "keyboardModifiers", staticmethod(lambda: Qt.KeyboardModifier.ControlModifier)
    )
    sb.stepBy(-1)
    # page_step / single_step = 0.5 / 0.05 = 10 → -10 single steps = -0.5
    assert sb.value() == pytest.approx(-0.5)


# ---------------------------------------------------------------------------
# FIELD_SPECS table — 22 canonical entries
# ---------------------------------------------------------------------------


def test_field_specs_has_all_canonical_keys() -> None:
    from lightsheet.gui.widgets.field_spec import FIELD_SPECS

    assert len(FIELD_SPECS) == 23
    for key in EXPECTED_FIELD_SPEC_KEYS:
        assert key in FIELD_SPECS, f"missing key: {key}"


def test_field_specs_units() -> None:
    from lightsheet.gui.widgets.field_spec import FIELD_SPECS

    assert FIELD_SPECS["doubleSpinBox_acqPlaneStepSize"].unit == "µm"
    assert FIELD_SPECS["doubleSpinBox_sampleHPosition"].unit == "mm"
    assert FIELD_SPECS["doubleSpinBox_galvoLeftAmplitude"].unit == "V"
    assert FIELD_SPECS["doubleSpinBox_cameraExposureTime"].unit == "ms"
    assert FIELD_SPECS["doubleSpinBox_etlSteps"].unit == ""
    assert FIELD_SPECS["doubleSpinBox_cameraLineTime"].unit == "µs"
    assert FIELD_SPECS["doubleSpinBox_laserOneAmplitude"].unit == "%"


def test_field_specs_motor_max_matches_hal() -> None:
    """FieldSpec motor max values are soft blocks aligned to rig physical
    ranges (mm). A regression in the table must be caught."""
    from lightsheet.gui.widgets.field_spec import FIELD_SPECS

    assert FIELD_SPECS["doubleSpinBox_sampleHPosition"].maximum == 41.0
    assert FIELD_SPECS["doubleSpinBox_sampleVPosition"].maximum == 18.8
    assert FIELD_SPECS["doubleSpinBox_cameraPosition"].maximum == 35.0


def test_field_specs_galvo_offset_signed_range() -> None:
    from lightsheet.gui.widgets.field_spec import FIELD_SPECS

    assert FIELD_SPECS["doubleSpinBox_galvoLeftOffset"].minimum == -10.0
    assert FIELD_SPECS["doubleSpinBox_galvoLeftOffset"].maximum == 10.0


# ---------------------------------------------------------------------------
# Re-export from field_spec_spinbox module (promotion header convenience)
# ---------------------------------------------------------------------------


def test_field_spec_reexported_from_spinbox_module() -> None:
    from lightsheet.gui.widgets.field_spec_spinbox import FIELD_SPECS, FieldSpec

    assert FieldSpec is not None
    assert len(FIELD_SPECS) == 23
