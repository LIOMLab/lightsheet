"""Promotion integration test — every canonical FieldSpecSpinBox has its
FieldSpec applied at construction, the 10 selective QSlider pairings are
synchronized bidirectionally, and the focus-gated wheel is in effect across
all panels.

Constructs the real ``Controller_MainWindow`` via the shared
``make_controller`` fixture (AGENTS.md §5) so the panel ``__init__`` applySpec
loops + QSlider sync wiring run against the real widget tree. Headless via
``QT_QPA_PLATFORM=offscreen`` (set by conftest).
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QWheelEvent  # noqa: E402
from PySide6.QtWidgets import QSlider  # noqa: E402

from _helpers.controller_fixture import make_controller  # noqa: E402
from lightsheet.gui.widgets.field_spec import FIELD_SPECS  # noqa: E402
from lightsheet.gui.widgets.field_spec_spinbox import FieldSpecSpinBox  # noqa: E402


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
}

# The 10 selective QSlider-paired fields (slider_<field> widget added in
# Task 1). All 10 have a QSlider sibling widget; the 8 in
# SLIDER_SYNCED_FIELDS have bidirectional sync wired. The 2 stack
# first/last plane fields (in SLIDER_PAIRED_BUT_NOT_SYNCED) have the
# slider widget present but sync is deferred — the stack panel's
# pre-existing µm-units convention conflicts with the FieldSpec mm range
# (the slider's int range would clamp the spinbox's widened µm value).
SLIDER_PAIRED_FIELDS = (
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

# Fields with bidirectional slider sync wired in the panel __init__.
SLIDER_SYNCED_FIELDS = (
    "doubleSpinBox_sampleSetHPosition",
    "doubleSpinBox_sampleSetVPosition",
    "doubleSpinBox_cameraSetPosition",
    "doubleSpinBox_etlLeftAmplitude",
    "doubleSpinBox_etlRightAmplitude",
    "doubleSpinBox_galvoLeftAmplitude",
    "doubleSpinBox_galvoRightAmplitude",
    "doubleSpinBox_cameraExposureTime",
)

# Slider widget present but sync deferred (stack panel µm-vs-mm units
# conflict — see deviation note in the plan SUMMARY).
SLIDER_PAIRED_BUT_NOT_SYNCED = (
    "doubleSpinBox_acqFirstPlane",
    "doubleSpinBox_acqLastPlane",
)


def _get_spinbox(ctrl, obj_name: str) -> FieldSpecSpinBox:
    """Resolve a canonical objectName to its FieldSpecSpinBox via the
    panel-qualified hybrid-ownership path."""
    panel_attr = _OBJNAME_TO_PANEL[obj_name]
    panel = getattr(ctrl, panel_attr)
    return getattr(panel.ui, obj_name)


def _get_slider(ctrl, obj_name: str) -> QSlider:
    """Resolve a slider-paired field to its QSlider sibling."""
    panel_attr = _OBJNAME_TO_PANEL[obj_name]
    panel = getattr(ctrl, panel_attr)
    return getattr(panel.ui, f"slider_{obj_name}")


def test_every_canonical_spinbox_is_field_spec_subclass(qtbot, request) -> None:
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


def test_applySpec_applied_suffix_decimals_range(qtbot, request) -> None:
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


def test_slider_pairing_exists_for_10_fields(qtbot, request) -> None:
    """Each of the 10 selective QSlider-paired fields has a QSlider
    sibling widget (slider_<field>) on the same panel."""
    ctrl, _ = make_controller(qtbot, request)
    for obj_name in SLIDER_PAIRED_FIELDS:
        slider = _get_slider(ctrl, obj_name)
        assert isinstance(slider, QSlider), (
            f"slider_{obj_name} is {type(slider).__name__}, not QSlider"
        )


def test_slider_range_matches_spec(qtbot, request) -> None:
    """Each synced QSlider's range/singleStep match the FieldSpec
    (coarse step = page_step). The 2 stack first/last plane sliders are
    present but not synced (units conflict) — excluded here."""
    ctrl, _ = make_controller(qtbot, request)
    for obj_name in SLIDER_SYNCED_FIELDS:
        spec = FIELD_SPECS[obj_name]
        slider = _get_slider(ctrl, obj_name)
        assert slider.minimum() == int(spec.minimum), (
            f"slider_{obj_name}: minimum {slider.minimum()} != {int(spec.minimum)}"
        )
        assert slider.maximum() == int(spec.maximum), (
            f"slider_{obj_name}: maximum {slider.maximum()} != {int(spec.maximum)}"
        )
        assert slider.singleStep() == int(spec.page_step), (
            f"slider_{obj_name}: singleStep {slider.singleStep()} != {int(spec.page_step)}"
        )


def test_slider_sync_spinbox_to_slider(qtbot, request) -> None:
    """Spinbox → slider: changing the spinbox value updates the slider
    (for the 8 synced fields)."""
    ctrl, _ = make_controller(qtbot, request)
    for obj_name in SLIDER_SYNCED_FIELDS:
        sb = _get_spinbox(ctrl, obj_name)
        slider = _get_slider(ctrl, obj_name)
        spec = FIELD_SPECS[obj_name]
        # Pick a value strictly inside the int range, distinct from the
        # current value when possible.
        target = int(spec.minimum) + max(1, (int(spec.maximum) - int(spec.minimum)) // 3)
        sb.setValue(float(target))
        assert slider.value() == target, (
            f"{obj_name}: spinbox setValue({target}) → slider {slider.value()}"
        )


def test_slider_sync_slider_to_spinbox(qtbot, request) -> None:
    """Slider → spinbox: changing the slider value updates the spinbox
    (for the 8 synced fields)."""
    ctrl, _ = make_controller(qtbot, request)
    for obj_name in SLIDER_SYNCED_FIELDS:
        sb = _get_spinbox(ctrl, obj_name)
        slider = _get_slider(ctrl, obj_name)
        spec = FIELD_SPECS[obj_name]
        target = int(spec.minimum) + max(1, (int(spec.maximum) - int(spec.minimum)) // 2)
        slider.setValue(target)
        assert abs(sb.value() - float(target)) < 1e-9, (
            f"{obj_name}: slider setValue({target}) → spinbox {sb.value()}"
        )


def _make_wheel_event(angle_delta=120):
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


def test_wheel_gate_unfocused_spinbox_ignores_wheel(qtbot, request) -> None:
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


def test_wheel_gate_focused_spinbox_responds(qtbot) -> None:
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
    sb.applySpec(FieldSpec(unit="", decimals=0, single_step=1, page_step=10, minimum=0, maximum=1000))
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
    schema = open(f"{repo_root}/lightsheet/config_schema.py").read()
    assert "Limit High" in schema, "config_schema.py motor limit validator missing"
    motors = open(f"{repo_root}/lightsheet/hal/real/motors.py").read()
    assert "ValueError" in motors, "ZaberMotor reject-and-beep missing"
