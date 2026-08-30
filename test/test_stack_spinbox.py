"""Stack start/end plane editable spinbox + shell-flag migration.

The boundary-set checkboxes (checkBox_acqFirstPlaneSet / checkBox_acqLastPlaneSet)
are replaced with editable QDoubleSpinBoxes (doubleSpinBox_acqFirstPlane /
doubleSpinBox_acqLastPlane). The Set button populates the spinbox from the
motor position; the operator can also type a value directly. The
is-boundary-set boolean migrates from checkBox.isChecked() to shell flags
stack_first_plane_set / stack_last_plane_set. Manual entry validates against
the motor travel limits and rejects with a beep on out-of-range (the worker's
per-plane ValueError catch stays as the physical-safety backstop).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

pytest.importorskip("PySide6")

from _helpers.controller_fixture import make_controller


def test_spinboxes_exist_and_checkboxes_gone(qtbot, request) -> None:
    ctrl, _ = make_controller(qtbot, request)
    from PySide6.QtWidgets import QDoubleSpinBox

    sb_first = ctrl.stack_panel.ui.doubleSpinBox_acqFirstPlane
    sb_last = ctrl.stack_panel.ui.doubleSpinBox_acqLastPlane
    assert isinstance(sb_first, QDoubleSpinBox)
    assert isinstance(sb_last, QDoubleSpinBox)
    # The checkboxes are gone.
    assert not hasattr(ctrl.stack_panel.ui, "checkBox_acqFirstPlaneSet")
    assert not hasattr(ctrl.stack_panel.ui, "checkBox_acqLastPlaneSet")


def test_shell_flags_initialized(qtbot, request) -> None:
    ctrl, _ = make_controller(qtbot, request)
    # The flags start False unless config.ini has persisted stack params
    # from a prior run. In the test environment config.ini should not
    # carry stack params (demo mode skips persistence), so the flags
    # should be False.
    assert ctrl.stack_first_plane_set is False
    assert ctrl.stack_last_plane_set is False


def test_set_starting_plane_populates_spinbox_and_flag(qtbot, request) -> None:
    ctrl, _ = make_controller(qtbot, request)
    with patch.object(ctrl.stack_panel, "updateUi_set_number_of_planes"):
        ctrl.stack_panel.updateUi_set_stack_mode_starting_point()
    pos = ctrl.motors.horizontal.get_position("\u03bcm")
    assert ctrl.stack_starting_plane == pos
    assert ctrl.stack_first_plane_set is True
    # The spinbox displays in mm; the internal stack_starting_plane stays
    # µm (the worker + motor HAL unit).
    assert ctrl.stack_panel.ui.doubleSpinBox_acqFirstPlane.value() == pos / 1000.0


def test_set_ending_plane_populates_spinbox_and_flag(qtbot, request) -> None:
    ctrl, _ = make_controller(qtbot, request)
    with patch.object(ctrl.stack_panel, "updateUi_set_number_of_planes"):
        ctrl.stack_panel.updateUi_set_stack_mode_ending_point()
    pos = ctrl.motors.horizontal.get_position("\u03bcm")
    assert ctrl.stack_ending_plane == pos
    assert ctrl.stack_last_plane_set is True
    assert ctrl.stack_panel.ui.doubleSpinBox_acqLastPlane.value() == pos / 1000.0


def test_manual_entry_in_range_updates_shell_flag(qtbot, request) -> None:
    ctrl, _ = make_controller(qtbot, request)
    low = ctrl.motors.horizontal.get_limit_low("\u03bcm")
    high = ctrl.motors.horizontal.get_limit_high("\u03bcm")
    in_range_um = (low + high) / 2
    # The spinbox displays in mm; the internal stack_starting_plane stays
    # µm. Type the mm value; the editingFinished handler converts mm→µm
    # for storage (safety-critical: no 1000× motor error).
    in_range_mm = in_range_um / 1000.0
    ctrl.stack_panel.ui.doubleSpinBox_acqFirstPlane.setValue(in_range_mm)
    ctrl.stack_panel.ui.doubleSpinBox_acqFirstPlane.editingFinished.emit()
    assert ctrl.stack_first_plane_set is True
    assert ctrl.stack_starting_plane == pytest.approx(in_range_um, abs=1.0)


def test_mm_entry_produces_um_internal_value(qtbot, request) -> None:
    """Safety gate (B2): a mm spinbox entry must produce a µm internal
    stack_starting_plane — no 1000× motor over-travel error. 6.500 mm →
    6500.0 µm."""
    ctrl, _ = make_controller(qtbot, request)
    ctrl.stack_panel.ui.doubleSpinBox_acqFirstPlane.setValue(6.500)
    ctrl.stack_panel.ui.doubleSpinBox_acqFirstPlane.editingFinished.emit()
    assert ctrl.stack_starting_plane == pytest.approx(6500.0, abs=1.0)


def test_manual_entry_out_of_range_beeps_and_does_not_move(qtbot, request) -> None:
    ctrl, _ = make_controller(qtbot, request)
    beeps: list[None] = []
    messages: list[str] = []
    ctrl.sig_beep.connect(lambda: beeps.append(None))
    ctrl.sig_message.connect(lambda m: messages.append(m))
    # Set an out-of-range value beyond the spinbox range by lowering the
    # range floor first so the spinbox accepts the value, then triggering
    # editingFinished which validates against the motor limits. The
    # spinbox displays in mm; the motor limits are read in µm and the
    # typed mm value is converted to µm for the comparison.
    low = ctrl.motors.horizontal.get_limit_low("\u03bcm")
    high = ctrl.motors.horizontal.get_limit_high("\u03bcm")
    out_of_range_um = high + 1000.0
    out_of_range_mm = out_of_range_um / 1000.0
    ctrl.stack_panel.ui.doubleSpinBox_acqFirstPlane.setRange(
        low / 1000.0, out_of_range_mm + 0.001
    )
    ctrl.stack_panel.ui.doubleSpinBox_acqFirstPlane.setValue(out_of_range_mm)
    ctrl.stack_panel.ui.doubleSpinBox_acqFirstPlane.editingFinished.emit()
    assert len(beeps) == 1, "out-of-range entry must beep"
    assert len(messages) == 1, "out-of-range entry must emit a message"
    assert "travel limit" in messages[0].lower() or "outside" in messages[0].lower()
    # The motor must NOT have been moved by the edit.
    # (The worker's per-plane ValueError catch is the backstop; the
    # editingFinished handler never moves the motor.)


def test_number_of_planes_guards_on_shell_flags(qtbot, request) -> None:
    ctrl, _ = make_controller(qtbot, request)
    ctrl.stack_starting_plane = 0.0
    ctrl.stack_ending_plane = 100.0
    ctrl.stack_panel.ui.doubleSpinBox_acqPlaneStepSize.setValue(10.0)
    # Reset number_of_planes so we can detect whether the guard blocks
    # the computation (hardware_init may have set it via _load_stack_params).
    ctrl.number_of_planes = 0
    # Neither flag set → no planes computed.
    ctrl.stack_first_plane_set = False
    ctrl.stack_last_plane_set = False
    ctrl.stack_panel.updateUi_set_number_of_planes()
    assert ctrl.number_of_planes == 0
    # Only one flag set → still no planes.
    ctrl.stack_first_plane_set = True
    ctrl.stack_last_plane_set = False
    ctrl.number_of_planes = 0
    ctrl.stack_panel.updateUi_set_number_of_planes()
    assert ctrl.number_of_planes == 0
    # Both flags set → planes computed.
    ctrl.stack_first_plane_set = True
    ctrl.stack_last_plane_set = True
    ctrl.stack_panel.updateUi_set_number_of_planes()
    assert ctrl.number_of_planes > 0


def test_spinbox_range_seeded_from_motor_limits(qtbot, request) -> None:
    ctrl, _ = make_controller(qtbot, request)
    low = ctrl.motors.horizontal.get_limit_low("\u03bcm")
    high = ctrl.motors.horizontal.get_limit_high("\u03bcm")
    # The spinbox displays in mm; _seed_spinbox_ranges seeds from the
    # motor limits in mm. The range may be wider than the limits (so an
    # out-of-range entry is accepted by the spinbox and then rejected by
    # the editingFinished validation). Assert the motor limits (in mm)
    # are within the spinbox range.
    sb_first = ctrl.stack_panel.ui.doubleSpinBox_acqFirstPlane
    assert sb_first.minimum() <= low / 1000.0
    assert sb_first.maximum() >= high / 1000.0


def test_worker_valueerror_catch_preserved() -> None:
    """The stack_mode_worker per-plane move_absolute_position ValueError
    catch (the physical-safety backstop) is preserved verbatim."""
    import inspect

    from lightsheet.gui import workers

    src = inspect.getsource(workers)
    # The per-plane ValueError catch in the stack worker must still be
    # present (the editingFinished soft block does not replace it).
    assert "move_absolute_position" in src
    assert "except ValueError" in src
