"""Branch-coverage tests for AcquisitionTableManager.

Covers branches not exercised by the existing CRUD/validation tests:
- ``add_stack`` with step==0 (fallback to 1.0)
- ``remove_stack`` with no row selected (row < 0)
- ``move_up`` at row 0 (no-op)
- ``move_down`` at the last row (no-op)
- ``set_cell`` when the item is None (creates a new item)
- ``_safe_float`` with a None item and with non-numeric text
- ``_parse_or_flag`` with non-numeric text (flags the cell)
- ``_estimate_per_plane_time`` exception fallback
- ``_estimate_stack_size_mb`` exception fallback
- ``_zarr_pyramid_multiplier`` exception fallback
- ``recompute_all_rows`` / ``_recompute_row`` re-entrancy guard
- ``_on_cell_changed`` on a readonly column and during recompute
- ``_recompute_row_impl`` with None name item / motors None / limit
  exception / no limits / flagged → sig_message
- ``_start_queue`` gates: hardware not initialized, no rows, incomplete
  row, no save path
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from pytestqt.qtbot import QtBot

pytest.importorskip("PySide6")


if TYPE_CHECKING:
    from lightsheet.gui.panels.acquisition_table_manager import (
        AcquisitionTableManager,
    )
    from lightsheet.gui.shell.controller import Controller_MainWindow


def _mgr(
    qtbot: QtBot, controller: Controller_MainWindow
) -> tuple[Controller_MainWindow, AcquisitionTableManager]:
    ctrl = controller
    return ctrl, ctrl.stack_panel.table_manager  # ty: ignore[unsound-return-statement]


# -- add_stack edge case --------------------------------------------------


def test_add_stack_with_zero_step_falls_back_to_one(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """add_stack with the step spinbox at 0 falls back to step=1.0 so the
    n_planes computation does not divide by zero."""
    ctrl, mgr = _mgr(qtbot, controller)
    sp = ctrl.stack_panel.ui
    sp.doubleSpinBox_acqFirstPlane.setValue(0.0)
    sp.doubleSpinBox_acqLastPlane.setValue(1.0)
    sp.doubleSpinBox_acqPlaneStepSize.setValue(0.0)
    mgr.add_stack()
    row = mgr.row_at(0)
    assert row.step == 1.0, (
        f"step should fall back to 1.0 when spinbox is 0, got {row.step}"
    )


# -- remove_stack / move edge cases ---------------------------------------


def test_remove_stack_no_selection_is_noop(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """remove_stack with no row selected (currentRow() < 0) is a no-op."""
    _ctrl, mgr = _mgr(qtbot, controller)
    mgr.add_stack()
    mgr.table.clearSelection()
    mgr.table.setCurrentCell(-1, -1)
    assert mgr.table.currentRow() < 0
    mgr.remove_stack()
    assert mgr.table.rowCount() == 1


def test_move_up_at_row_zero_is_noop(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """move_up at row 0 is a no-op (cannot move the first row up)."""
    _ctrl, mgr = _mgr(qtbot, controller)
    mgr.add_stack()
    mgr.set_cell(0, 0, "A")
    mgr.table.selectRow(0)
    mgr.move_up()
    assert mgr.row_at(0).name == "A"


def test_move_down_at_last_row_is_noop(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """move_down at the last row is a no-op."""
    _ctrl, mgr = _mgr(qtbot, controller)
    mgr.add_stack()
    mgr.set_cell(0, 0, "A")
    mgr.table.selectRow(0)
    mgr.move_down()
    assert mgr.row_at(0).name == "A"


# -- set_cell / _safe_float / _parse_or_flag ------------------------------


def test_set_cell_creates_new_item_when_none(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """set_cell on a cell with no existing item creates a new
    QTableWidgetItem instead of raising AttributeError."""
    _ctrl, mgr = _mgr(qtbot, controller)
    mgr.add_stack()
    # Force-remove the start cell item so set_cell hits the None path.
    mgr.table.takeItem(0, 1)
    assert mgr.table.item(0, 1) is None
    mgr.set_cell(0, 1, "15")
    assert mgr.table.item(0, 1) is not None
    assert mgr.table.item(0, 1).text() == "15"  # ty: ignore[unresolved-attribute]


def test_safe_float_with_none_item_returns_zero(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """_safe_float on a cell with no item returns 0.0 (does not raise
    AttributeError)."""
    _ctrl, mgr = _mgr(qtbot, controller)
    mgr.add_stack()
    mgr.table.takeItem(0, 1)  # remove the start cell item
    assert mgr.table.item(0, 1) is None
    assert mgr._safe_float(0, 1) == 0.0


def test_safe_float_with_non_numeric_text_returns_zero(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """_safe_float on a cell with non-numeric text (e.g. "abc") returns
    0.0 instead of raising ValueError."""
    _ctrl, mgr = _mgr(qtbot, controller)
    mgr.add_stack()
    mgr.set_cell(0, 1, "abc")
    assert mgr._safe_float(0, 1) == 0.0


def test_parse_or_flag_non_numeric_flags_cell(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """_parse_or_flag on non-numeric text flags the cell red and returns
    0.0."""
    _ctrl, mgr = _mgr(qtbot, controller)
    mgr.add_stack()
    result = mgr._parse_or_flag(0, 1, "xyz")
    assert result == 0.0
    assert mgr.is_row_flagged(0)


# -- estimate helpers exception fallbacks ---------------------------------


def test_estimate_per_plane_time_exception_fallback(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """_estimate_per_plane_time returns 0.5 when the acquisition panel's
    exposure spinbox cannot be read (AttributeError / ValueError /
    TypeError)."""
    ctrl, mgr = _mgr(qtbot, controller)
    # Remove the acquisition_panel attr so the access raises.
    orig = ctrl.acquisition_panel
    ctrl.acquisition_panel = None  # type: ignore[assignment]  # ty: ignore[invalid-assignment]
    try:
        assert mgr._estimate_per_plane_time() == 0.5
    finally:
        ctrl.acquisition_panel = orig


def test_estimate_stack_size_mb_camera_exception_fallback(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """_estimate_stack_size_mb returns a raw-bytes estimate when the
    camera attrs cannot be read (falls back to 2000x2000)."""
    ctrl, mgr = _mgr(qtbot, controller)

    # Replace camera with an object that raises on ysize.
    class BadCamera:
        @property
        def ysize(self) -> int:
            raise TypeError("no camera")

    orig = ctrl.camera
    ctrl.camera = BadCamera()  # type: ignore[assignment]  # ty: ignore[invalid-assignment]
    try:
        mb = mgr._estimate_stack_size_mb(100)
        # 2000*2000*2*100 / (1024*1024) ≈ 762.9 MB
        assert mb > 700
        assert mb < 800
    finally:
        ctrl.camera = orig


def test_zarr_pyramid_multiplier_exception_fallback(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """_zarr_pyramid_multiplier returns a sane multiplier when
    stack_step cannot be parsed (TypeError / ValueError fallback to 0.0)."""
    ctrl, mgr = _mgr(qtbot, controller)

    # Set stack_step to an object that raises on float().
    class BadFloat:
        def __float__(self) -> float:
            raise ValueError("bad float")

    orig = ctrl.stack_step
    ctrl.stack_step = BadFloat()  # type: ignore[assignment]  # ty: ignore[invalid-assignment]
    try:
        mult = mgr._zarr_pyramid_multiplier()
        # stack_step=0.0 → base_res=(0, 6.5, 6.5) → max_res=6.5 → all
        # targets (10, 25, 50, 100) >= 6.5 → 4 levels → multiplier =
        # 1 + 0.25 + 0.0625 + 0.015625 = 1.328125
        assert mult > 1.0
    finally:
        ctrl.stack_step = orig


# -- recompute re-entrancy guards -----------------------------------------


def test_recompute_all_rows_reentrancy_guard(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """recompute_all_rows is a no-op when _recomputing is already True
    (re-entrancy guard)."""
    _ctrl, mgr = _mgr(qtbot, controller)
    mgr.add_stack()
    mgr._recomputing = True
    # Should return immediately without touching the table.
    mgr.recompute_all_rows()
    # _recomputing still True (the guard returned before the try/finally).
    assert mgr._recomputing is True
    mgr._recomputing = False


def test_recompute_row_reentrancy_guard(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """_recompute_row is a no-op when _recomputing is already True."""
    _ctrl, mgr = _mgr(qtbot, controller)
    mgr.add_stack()
    mgr._recomputing = True
    mgr._recompute_row(0)
    assert mgr._recomputing is True
    mgr._recomputing = False


def test_on_cell_changed_on_readonly_column_is_noop(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """_on_cell_changed on a readonly column (#Planes / Est. Time / Est.
    Size) is a no-op — the recompute is skipped."""
    _ctrl, mgr = _mgr(qtbot, controller)
    mgr.add_stack()
    # Directly call _on_cell_changed on a readonly column.
    mgr._on_cell_changed(0, 4)  # _COL_NPLANES
    # No exception, no recompute triggered.


def test_on_cell_changed_during_recompute_is_noop(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """_on_cell_changed during a recompute (_recomputing=True) is a
    no-op — the re-entrancy guard prevents a loop."""
    _ctrl, mgr = _mgr(qtbot, controller)
    mgr.add_stack()
    mgr._recomputing = True
    mgr._on_cell_changed(0, 1)  # _COL_START
    assert mgr._recomputing is True
    mgr._recomputing = False


# -- _recompute_row_impl edge cases ---------------------------------------


def test_recompute_with_none_name_item(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """_recompute_row_impl does not raise when the name cell item is
    None (the tooltip update is skipped)."""
    _ctrl, mgr = _mgr(qtbot, controller)
    mgr.add_stack()
    mgr.table.takeItem(0, 0)  # remove name item
    assert mgr.table.item(0, 0) is None
    # Should not raise.
    mgr._recompute_row(0)


def test_recompute_with_motors_none(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """_recompute_row_impl does not raise when self._shell.motors is
    None (the limit check is skipped)."""
    ctrl, mgr = _mgr(qtbot, controller)
    mgr.add_stack()
    orig = ctrl.motors
    ctrl.motors = None  # type: ignore[assignment]  # ty: ignore[invalid-assignment]
    try:
        mgr._recompute_row(0)
    finally:
        ctrl.motors = orig


def test_recompute_with_bad_motor_limits(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """_recompute_row_impl does not raise when the motor limits raise
    (TypeError / ValueError / AttributeError → low/high = None, skip the
    range check)."""
    ctrl, mgr = _mgr(qtbot, controller)
    mgr.add_stack()

    # Replace the horizontal motor's get_limit_low with one that raises.
    orig_motor = ctrl.motors.horizontal

    class BadMotor:
        def get_limit_low(self, unit: str) -> float:
            raise ValueError("bad limit")

        def get_limit_high(self, unit: str) -> float:
            raise ValueError("bad limit")

        move_absolute_position = orig_motor.move_absolute_position

    ctrl.motors.horizontal = BadMotor()  # type: ignore[assignment]  # ty: ignore[invalid-assignment]
    try:
        mgr._recompute_row(0)
    finally:
        ctrl.motors.horizontal = orig_motor


def test_recompute_flagged_row_emits_sig_message(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """When a row is flagged (incomplete or out-of-range), the shell's
    sig_message is emitted with a descriptive message."""
    ctrl, mgr = _mgr(qtbot, controller)
    messages: list[str] = []
    ctrl.sig_message.connect(lambda msg: messages.append(msg))
    mgr.add_stack()
    # Force start == end so the row is incomplete (on the rig, config.ini
    # may have non-zero spinbox values that make the default row valid).
    mgr.set_cell(0, 1, "5")
    mgr.set_cell(0, 2, "5")
    assert any("incomplete or out of range" in m for m in messages), (
        f"sig_message not emitted for flagged row: {messages}"
    )


# -- _start_queue gates ---------------------------------------------------


def test_start_queue_hardware_not_initialized(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """_start_queue emits a 'Hardware is still initializing' message and
    beeps when _hardware_initialized is False."""
    ctrl, mgr = _mgr(qtbot, controller)
    mgr.add_stack()
    mgr.set_cell(0, 1, "10")
    mgr.set_cell(0, 2, "20")
    mgr.set_cell(0, 3, "10")
    assert mgr.start_queue_enabled()
    # Force hardware not initialized.
    orig = getattr(ctrl, "_hardware_initialized", True)
    ctrl._hardware_initialized = False
    messages: list[str] = []
    ctrl.sig_message.connect(lambda msg: messages.append(msg))
    beeps: list[None] = []
    ctrl.sig_beep.connect(lambda: beeps.append(None))
    try:
        mgr._start_queue()
    finally:
        ctrl._hardware_initialized = orig
    assert any("initializing" in m for m in messages), messages
    assert len(beeps) >= 1


def test_start_queue_no_rows(qtbot: QtBot, controller: Controller_MainWindow) -> None:
    """_start_queue with no rows emits an error message and beeps."""
    ctrl, mgr = _mgr(qtbot, controller)
    assert mgr.table.rowCount() == 0
    messages: list[str] = []
    ctrl.sig_message.connect(lambda msg: messages.append(msg))
    beeps: list[None] = []
    ctrl.sig_beep.connect(lambda: beeps.append(None))
    mgr._start_queue()
    assert any("no stacks" in m for m in messages), messages
    assert len(beeps) >= 1


def test_start_queue_incomplete_row(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """_start_queue with an incomplete row (n_planes==0) emits an error
    and beeps."""
    ctrl, mgr = _mgr(qtbot, controller)
    mgr.add_stack()
    # Force start == end so n_planes==0 (on the rig, config.ini may have
    # non-zero spinbox values that make the default row valid).
    mgr.set_cell(0, 1, "5")
    mgr.set_cell(0, 2, "5")
    messages: list[str] = []
    ctrl.sig_message.connect(lambda msg: messages.append(msg))
    beeps: list[None] = []
    ctrl.sig_beep.connect(lambda: beeps.append(None))
    mgr._start_queue()
    assert any("incomplete" in m for m in messages), messages
    assert len(beeps) >= 1


def test_start_queue_no_save_path(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """_start_queue with saving_allowed=True but no save_directory emits
    an error and beeps."""
    ctrl, mgr = _mgr(qtbot, controller)
    mgr.add_stack()
    mgr.set_cell(0, 1, "10")
    mgr.set_cell(0, 2, "20")
    mgr.set_cell(0, 3, "10")
    # Force saving_allowed=True and save_directory="".
    with (
        patch.object(ctrl, "saving_allowed", True),
        patch.object(ctrl, "save_directory", ""),
    ):
        messages: list[str] = []
        ctrl.sig_message.connect(lambda msg: messages.append(msg))
        beeps: list[None] = []
        ctrl.sig_beep.connect(lambda: beeps.append(None))
        mgr._start_queue()
    assert any("no save path" in m for m in messages), messages
    assert len(beeps) >= 1
