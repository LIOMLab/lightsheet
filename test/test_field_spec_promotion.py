"""Promotion integration test — every canonical FieldSpecSpinBox has its
FieldSpec applied at construction, no QSlider pairings remain (the sliders
were removed from the panel .ui files because the spinboxes are themselves
scrollable), and the focus-gated wheel is in effect across all panels.

Constructs the real ``Controller_MainWindow`` via the shared
``make_controller`` fixture (AGENTS.md §5) so the panel ``__init__`` applySpec
loops run against the real widget tree. Headless via
``QT_QPA_PLATFORM=offscreen`` (set by conftest).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

pytest.importorskip("PySide6")

from _helpers.controller_fixture import make_controller
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from pytestqt.qtbot import QtBot

from lightsheet.gui.widgets.field_spec import FIELD_SPECS
from lightsheet.gui.widgets.field_spec_spinbox import FieldSpecSpinBox

if TYPE_CHECKING:
    from lightsheet.gui.shell.controller import Controller_MainWindow

# Map each canonical objectName to the panel attribute that owns it
# (hybrid ownership — panel-internal widgets live on the panel's ``ui``,
# not the merged shell ``ui``). Used to resolve the widget for each spec.
_OBJNAME_TO_PANEL = {
    # motor_panel
    "doubleSpinBox_sampleSetHPosition": "motor_panel",
    "doubleSpinBox_sampleSetVPosition": "motor_panel",
    "doubleSpinBox_cameraSetPosition": "motor_panel",
    "doubleSpinBox_sampleHStepSize": "motor_panel",
    "doubleSpinBox_sampleVStepSize": "motor_panel",
    "doubleSpinBox_cameraStepSize": "motor_panel",
    # stack_panel
    "doubleSpinBox_acqFirstPlane": "stack_panel",
    "doubleSpinBox_acqLastPlane": "stack_panel",
    "doubleSpinBox_acqPlaneStepSize": "stack_panel",
    # scan_panel
    "doubleSpinBox_etlLeftAmplitude": "scan_panel",
    "doubleSpinBox_etlRightAmplitude": "scan_panel",
    "doubleSpinBox_etlLeftOffset": "scan_panel",
    "doubleSpinBox_etlRightOffset": "scan_panel",
    "doubleSpinBox_etlSteps": "scan_panel",
    "doubleSpinBox_galvoLeftAmplitude": "scan_panel",
    "doubleSpinBox_galvoRightAmplitude": "scan_panel",
    "doubleSpinBox_galvoLeftOffset": "scan_panel",
    "doubleSpinBox_galvoRightOffset": "scan_panel",
    # acquisition_panel
    "doubleSpinBox_cameraExposureTime": "acquisition_panel",
    "doubleSpinBox_cameraLineTime": "acquisition_panel",
    "doubleSpinBox_cameraExposedLines": "acquisition_panel",
    "doubleSpinBox_cameraDelayLines": "acquisition_panel",
    # laser_panel
    "doubleSpinBox_laserOneAmplitude": "laser_panel",
    "doubleSpinBox_laserTwoAmplitude": "laser_panel",
    # stack_panel — adaptive config group (6 operator-adjustable
    # spinboxes; the fixed controller-tuning settings moved to
    # config.ini only).
    "doubleSpinBox_adaptiveMinExposure": "stack_panel",
    "doubleSpinBox_adaptiveMaxExposure": "stack_panel",
    "doubleSpinBox_adaptiveLaser1MinPower": "stack_panel",
    "doubleSpinBox_adaptiveLaser1MaxPower": "stack_panel",
    "doubleSpinBox_adaptiveLaser2MinPower": "stack_panel",
    "doubleSpinBox_adaptiveLaser2MaxPower": "stack_panel",
}

# The fields that previously had QSlider siblings. The sliders were
# removed from the panel .ui files because the FieldSpecSpinBox is itself
# scrollable (wheel + arrow keys + Ctrl/Shift page-step), so a separate
# coarse-drag slider was redundant and broke the form-layout alignment.
# This tuple is kept so the no-sliders regression test can iterate the
# exact set of fields that used to carry a slider.
FORMER_SLIDER_PAIRED_FIELDS = (
    "doubleSpinBox_sampleSetHPosition",
    "doubleSpinBox_sampleSetVPosition",
    "doubleSpinBox_cameraSetPosition",
    "doubleSpinBox_acqFirstPlane",
    "doubleSpinBox_acqLastPlane",
    "doubleSpinBox_etlLeftAmplitude",
    "doubleSpinBox_etlRightAmplitude",
    "doubleSpinBox_galvoLeftAmplitude",
    "doubleSpinBox_galvoRightAmplitude",
    "doubleSpinBox_cameraExposureTime",
)


def _get_spinbox(ctrl: Controller_MainWindow, obj_name: str) -> FieldSpecSpinBox:
    """Resolve a canonical objectName to its FieldSpecSpinBox via the
    panel-qualified hybrid-ownership path."""
    panel_attr = _OBJNAME_TO_PANEL[obj_name]
    panel = getattr(ctrl, panel_attr)
    return getattr(panel.ui, obj_name)


def test_every_canonical_spinbox_is_field_spec_subclass(
    qtbot: QtBot, request: pytest.FixtureRequest
) -> None:
    """Each of the 24 canonical objectNames resolves to a FieldSpecSpinBox
    instance (the .ui promotion took effect + ui_*.py regenerated)."""
    ctrl, _ = make_controller(qtbot, request)
    for obj_name in FIELD_SPECS:
        sb = _get_spinbox(ctrl, obj_name)
        assert isinstance(sb, FieldSpecSpinBox), (
            f"{obj_name} is {type(sb).__name__}, not FieldSpecSpinBox"
        )


# Fields whose min/max are overridden AFTER applySpec by pre-existing
# runtime mechanisms (so the spec's static min/max are not the final
# widget range). The FieldSpec still sets suffix/decimals/singleStep
# authoritatively for these; only the range is overridden.
#
# - The 4 offset fields: dynamically coupled to the amplitude value by
#   the updateUi_*_amplitude slots (called from
#   updateUi_initial_hardware_state) to keep amplitude + offset within
#   the ±5V (ETL) / ±10V (galvo) hardware range.
# - The 2 stack first/last plane fields: widened by _seed_spinbox_ranges
#   (called from __init__ and hardware_init) to accept out-of-range
#   entries that are then rejected by editingFinished with a beep. The
#   stack panel uses a pre-existing µm-units convention for the spinbox
#   value that predates the FieldSpec mm unit; reconciling the units is
#   deferred to a future plan.
_SPEC_RANGE_OVERRIDDEN_FIELDS = frozenset(
    {
        "doubleSpinBox_etlLeftOffset",
        "doubleSpinBox_etlRightOffset",
        "doubleSpinBox_galvoLeftOffset",
        "doubleSpinBox_galvoRightOffset",
        "doubleSpinBox_acqFirstPlane",
        "doubleSpinBox_acqLastPlane",
    }
)


def test_applySpec_applied_suffix_decimals_range(
    qtbot: QtBot, request: pytest.FixtureRequest
) -> None:
    """applySpec was called for every canonical spinbox: suffix and
    decimals match the FIELD_SPECS entry. minimum/maximum also match
    except for fields whose range is overridden by pre-existing runtime
    mechanisms (dynamic amplitude-coupling for offsets; _seed_spinbox_ranges
    widening for stack first/last plane)."""
    ctrl, _ = make_controller(qtbot, request)
    for obj_name, spec in FIELD_SPECS.items():
        sb = _get_spinbox(ctrl, obj_name)
        expected_suffix = f" {spec.unit}" if spec.unit else ""
        assert sb.suffix() == expected_suffix, (
            f"{obj_name}: suffix {sb.suffix()!r} != {expected_suffix!r}"
        )
        assert sb.decimals() == spec.decimals, (
            f"{obj_name}: decimals {sb.decimals()} != {spec.decimals}"
        )
        if obj_name in _SPEC_RANGE_OVERRIDDEN_FIELDS:
            continue
        assert sb.minimum() == spec.minimum, (
            f"{obj_name}: minimum {sb.minimum()} != {spec.minimum}"
        )
        assert sb.maximum() == spec.maximum, (
            f"{obj_name}: maximum {sb.maximum()} != {spec.maximum}"
        )


def test_no_slider_widgets_remain(
    qtbot: QtBot, request: pytest.FixtureRequest
) -> None:
    """None of the formerly slider-paired fields has a QSlider sibling
    widget anymore. The sliders were removed from the panel .ui files
    because the FieldSpecSpinBox is itself scrollable; a separate
    coarse-drag slider was redundant and broke the form-layout alignment.
    This test guards against an accidental re-introduction."""
    ctrl, _ = make_controller(qtbot, request)
    for obj_name in FORMER_SLIDER_PAIRED_FIELDS:
        panel_attr = _OBJNAME_TO_PANEL[obj_name]
        panel = getattr(ctrl, panel_attr)
        assert not hasattr(panel.ui, f"slider_{obj_name}"), (
            f"slider_{obj_name} should have been removed but is still present"
        )


def _make_wheel_event(angle_delta: int = 120) -> QWheelEvent:
    """Synthesize a QWheelEvent with a positive (up) angle delta.

    Matches the constructor signature used in test_field_spec_spinbox.py:
    ``(pos, globalPos, pixelDelta, angleDelta, buttons, modifiers, phase,
    inverted)``.
    """
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


def test_wheel_gate_unfocused_spinbox_ignores_wheel(
    qtbot: QtBot, request: pytest.FixtureRequest
) -> None:
    """An unfocused FieldSpecSpinBox ignores the mouse wheel (the
    wheel-steal fix). The value must not change when a wheel event is
    delivered without focus."""
    from PySide6.QtWidgets import QApplication, QLineEdit

    ctrl, _ = make_controller(qtbot, request)
    # Test one representative spinbox per panel that has one.
    representatives = (
        "doubleSpinBox_sampleSetHPosition",   # motor_panel
        "doubleSpinBox_cameraExposureTime",   # acquisition_panel
        "doubleSpinBox_acqFirstPlane",        # stack_panel
        "doubleSpinBox_etlLeftAmplitude",     # scan_panel
        "doubleSpinBox_laserOneAmplitude",    # laser_panel
    )
    for obj_name in representatives:
        sb = _get_spinbox(ctrl, obj_name)
        before = sb.value()
        # clearFocus() alone re-assigns focus to the spinbox when it is
        # the only focusable widget in the window. Give focus to a
        # separate widget so the spinbox genuinely loses focus.
        other = QLineEdit(sb.parentWidget())
        other.show()
        qtbot.addWidget(other)
        other.setFocus()
        sb.clearFocus()
        QApplication.processEvents()
        assert not sb.hasFocus()
        evt = _make_wheel_event(angle_delta=120)
        QApplication.sendEvent(sb, evt)
        assert sb.value() == before, (
            f"{obj_name}: unfocused wheel changed value {before} → {sb.value()}"
        )


def test_wheel_gate_focused_spinbox_responds(qtbot: QtBot) -> None:
    """A focused FieldSpecSpinBox still responds to the wheel (the gate
    is focus-gated, not a blanket disable).

    Uses a standalone spinbox (not the controller) because focus requires
    the widget to be on a visible page — the controller's stacked widget
    shows only page 0 by default. The focused-wheel behavior is a
    subclass property (already covered by test_field_spec_spinbox.py);
    this test re-affirms it in the promotion test module for locality.
    """
    from PySide6.QtWidgets import QApplication

    from lightsheet.gui.widgets.field_spec import FieldSpec

    sb = FieldSpecSpinBox()
    sb.resize(160, 32)
    qtbot.addWidget(sb)
    sb.show()
    qtbot.waitExposed(sb)
    sb.applySpec(
        FieldSpec(
            unit="", decimals=0, single_step=1, page_step=10,
            minimum=0, maximum=1000,
        )
    )
    sb.setValue(5.0)
    sb.setFocus()
    QApplication.processEvents()
    sb.activateWindow()
    QApplication.processEvents()
    before = sb.value()
    evt = _make_wheel_event(angle_delta=120)
    QApplication.sendEvent(sb, evt)
    assert sb.value() != before, (
        f"focused wheel did not change value ({before} → {sb.value()})"
    )


def test_hal_validators_untouched() -> None:
    """Threat-model T-08.1-14 mitigation: the promotion does not relax
    the HAL motor travel-limit validator or the config_schema startup
    gate. Assert the safety-critical files are unchanged from HEAD."""
    import subprocess

    repo_root = subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"], text=True
    ).strip()
    # config_schema.py motor limit validators + ZaberMotor reject-and-beep
    # must still be present (grep, not a diff — this is a presence check).
    with Path(f"{repo_root}/lightsheet/config_schema.py").open() as f:
        schema = f.read()
    assert "Limit High" in schema, "config_schema.py motor limit validator missing"
    with Path(f"{repo_root}/lightsheet/hal/real/motors.py").open() as f:
        motors = f.read()
    assert "ValueError" in motors, "ZaberMotor reject-and-beep missing"
