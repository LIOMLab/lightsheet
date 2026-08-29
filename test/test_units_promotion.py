"""Units selector promotion — comboBox_units from Motion tab to E-stop
toolbar + suffix display + Stack re-render (audit #9).

The units selector was buried on the Motion tab, invisible on every other
tab. This test asserts the audit #9 remediation:

- ``comboBox_units`` is in the E-stop toolbar (``toolBar_estop``), not the
  Motion tab — visible on every tab.
- The 75 px minimum width is preserved.
- Switching tabs does not hide the units selector (it is in the toolbar,
  not a tab page).
- The active unit suffix is displayed next to Stack plane spinboxes.
- Switching units re-renders the Stack plane spinboxes (suffix + displayed
  value conversion) in addition to the Motion position labels.
- The ``updateUi_units`` hook calls both ``motor_panel.updateUi_units`` AND
  ``stack_panel._rerender_stack_units``.

Runs headless on Mac via ``QT_QPA_PLATFORM=offscreen`` (set by conftest).
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from _helpers.controller_fixture import make_controller


def _make(qtbot, request):
    return make_controller(qtbot, request)


def _combo_is_in_toolbar(combo, toolbar) -> bool:
    """Return True if ``combo`` is a descendant of ``toolbar`` (the
    toolbar is its parent or ancestor)."""
    parent = combo.parent()
    while parent is not None:
        if parent is toolbar:
            return True
        parent = parent.parent()
    return False


def test_combo_box_units_in_estop_toolbar(qtbot, request) -> None:
    """comboBox_units is in the E-stop toolbar, not the Motion tab."""
    ctrl, _ = _make(qtbot, request)
    combo = ctrl.ui.comboBox_units
    toolbar = ctrl.ui.toolBar_estop
    assert _combo_is_in_toolbar(combo, toolbar), (
        "comboBox_units must be in the E-stop toolbar (toolBar_estop) so "
        "it is visible on every tab — its parent chain does not include "
        "the toolbar"
    )
    # It must NOT be parented into the motor panel.
    assert combo.parent() is not ctrl.motor_panel, (
        "comboBox_units is still parented to the motor panel — it must "
        "be in the E-stop toolbar"
    )


def test_combo_box_units_minimum_width_preserved(qtbot, request) -> None:
    """comboBox_units minimum width is >= 75 px (preserved)."""
    ctrl, _ = _make(qtbot, request)
    assert ctrl.ui.comboBox_units.minimumWidth() >= 75, (
        f"comboBox_units minimum width should be >= 75 px; got "
        f"{ctrl.ui.comboBox_units.minimumWidth()}"
    )


def test_combo_box_units_visible_on_every_tab(qtbot, request) -> None:
    """comboBox_units is visible on every tab (it is in the toolbar, not a
    tab page). Switching tabs does not hide it."""
    ctrl, _ = _make(qtbot, request)
    ctrl.show()
    qtbot.waitExposed(ctrl)
    qtbot.wait(50)
    combo = ctrl.ui.comboBox_units
    tab = ctrl.ui.tabControls
    # Switch through each tab and assert the combo stays visible.
    for i in range(tab.count()):
        tab.setCurrentIndex(i)
        qtbot.wait(20)
        assert combo.isVisible() or not ctrl.isVisible(), (
            f"comboBox_units is not visible on tab {i} ({tab.tabText(i)}) "
            "— it must be in the toolbar so it is visible on every tab"
        )


def test_stack_plane_spinbox_suffix_matches_unit(qtbot, request) -> None:
    """The active unit suffix is displayed next to Stack plane spinboxes."""
    ctrl, _ = _make(qtbot, request)
    # After hardware_init + updateUi_units, the stack plane spinbox suffix
    # should reflect the current unit.
    current_unit = ctrl.ui.comboBox_units.currentText()
    suffix = ctrl.stack_panel.ui.doubleSpinBox_acqFirstPlane.suffix()
    assert current_unit in suffix, (
        f"doubleSpinBox_acqFirstPlane suffix is {suffix!r}, expected it "
        f"to contain the current unit {current_unit!r}"
    )


def test_switching_units_rerenders_stack_spinboxes(qtbot, request) -> None:
    """Switching comboBox_units to 'mm' re-renders the Stack plane spinboxes
    with the 'mm' suffix + converts the displayed value; switching back to
    'μm' reverts."""
    ctrl, _ = _make(qtbot, request)
    sb_first = ctrl.stack_panel.ui.doubleSpinBox_acqFirstPlane
    # Start in μm (the default for the test fixture).
    ctrl.ui.comboBox_units.setCurrentText("\u03bcm")
    qtbot.wait(30)
    um_value = sb_first.value()
    assert "\u03bcm" in sb_first.suffix(), (
        f"after switching to μm, suffix is {sb_first.suffix()!r}"
    )
    # Switch to mm — the suffix should change and the displayed value
    # should convert (μm → mm = divide by 1000).
    ctrl.ui.comboBox_units.setCurrentText("mm")
    qtbot.wait(30)
    assert "mm" in sb_first.suffix(), (
        f"after switching to mm, suffix is {sb_first.suffix()!r}"
    )
    mm_value = sb_first.value()
    # The value should have converted: mm_value ≈ um_value / 1000.
    if um_value != 0:
        assert abs(mm_value - um_value / 1000.0) < 0.01, (
            f"after switching to mm, value is {mm_value} but should be "
            f"≈ {um_value / 1000.0} (μm value / 1000)"
        )
    # Switch back to μm — the suffix and value should revert.
    ctrl.ui.comboBox_units.setCurrentText("\u03bcm")
    qtbot.wait(30)
    assert "\u03bcm" in sb_first.suffix(), (
        f"after switching back to μm, suffix is {sb_first.suffix()!r}"
    )
    um_value_after = sb_first.value()
    if um_value != 0:
        assert abs(um_value_after - um_value) < 1.0, (
            f"after switching back to μm, value is {um_value_after} but "
            f"should be ≈ {um_value} (the original μm value)"
        )


def test_switching_units_scales_step_spinbox_min_max(qtbot, request) -> None:
    """Switching comboBox_units scales the plane-step spinbox min/max/step
    by the same factor as the value, so fine steps (e.g. 6.5 μm = 0.0065 mm)
    are enterable in mm mode. Without this, switching to mm leaves the min
    at 0.25 (now 0.25 mm = 250 μm), blocking sub-250-μm steps."""
    ctrl, _ = _make(qtbot, request)
    sb_step = ctrl.stack_panel.ui.doubleSpinBox_acqPlaneStepSize

    # Start in μm (the default).
    ctrl.ui.comboBox_units.setCurrentText("\u03bcm")
    qtbot.wait(30)
    um_min = sb_step.minimum()
    um_max = sb_step.maximum()
    um_step = sb_step.singleStep()

    # Switch to mm — min/max/step should all divide by 1000.
    ctrl.ui.comboBox_units.setCurrentText("mm")
    qtbot.wait(30)
    mm_min = sb_step.minimum()
    mm_max = sb_step.maximum()
    mm_step = sb_step.singleStep()
    assert abs(mm_min - um_min / 1000.0) < 1e-9, (
        f"mm min is {mm_min} but should be {um_min / 1000.0}"
    )
    assert abs(mm_max - um_max / 1000.0) < 1e-9, (
        f"mm max is {mm_max} but should be {um_max / 1000.0}"
    )
    assert abs(mm_step - um_step / 1000.0) < 1e-9, (
        f"mm singleStep is {mm_step} but should be {um_step / 1000.0}"
    )

    # 6.5 μm = 0.0065 mm must be within the mm-mode range.
    assert mm_min <= 0.0065 <= mm_max, (
        f"0.0065 mm (6.5 μm) is outside the mm-mode step range "
        f"[{mm_min}, {mm_max}]"
    )

    # Switch back to μm — min/max/step should revert.
    ctrl.ui.comboBox_units.setCurrentText("\u03bcm")
    qtbot.wait(30)
    assert abs(sb_step.minimum() - um_min) < 1e-6, (
        f"after switching back to μm, min is {sb_step.minimum()} "
        f"but should be {um_min}"
    )
    assert abs(sb_step.maximum() - um_max) < 1e-6, (
        f"after switching back to μm, max is {sb_step.maximum()} "
        f"but should be {um_max}"
    )


def test_updateUi_units_hook_calls_both_panels(qtbot, request) -> None:
    """The updateUi_units hook calls both motor_panel.updateUi_units AND
    stack_panel._rerender_stack_units (the re-render extension)."""
    from unittest.mock import patch

    ctrl, _ = _make(qtbot, request)
    with patch.object(ctrl.motor_panel, "updateUi_units") as mock_motor, \
         patch.object(ctrl.stack_panel, "_rerender_stack_units") as mock_stack:
        # Trigger the units change signal.
        ctrl.ui.comboBox_units.setCurrentText(
            "mm" if ctrl.ui.comboBox_units.currentText() == "\u03bcm" else "\u03bcm"
        )
        qtbot.wait(30)
    assert mock_motor.called, (
        "motor_panel.updateUi_units was not called on unit switch"
    )
    assert mock_stack.called, (
        "stack_panel._rerender_stack_units was not called on unit switch "
        "— the updateUi_units hook must re-render Stack in addition to Motion"
    )
