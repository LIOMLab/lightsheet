"""AcquisitionTableManager — QTableWidget queue of z-stacks by
position/range/step (audit #11 in-full).

The operator adds/edits/removes/reorders stack rows; each row specifies a
z-stack by start position, end position, and step. Start Queue (Task 2)
executes the rows sequentially, re-using the existing stack worker per row
without the operator re-driving the stage to each boundary.

This file covers the table CRUD + row validation + empty/error/partial
states + E8 overflow/long-text/zero-one-many. The queue execution loop is
covered by test_table_queue_execution.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from pytestqt.qtbot import QtBot

pytest.importorskip("PySide6")

from _helpers.controller_fixture import make_controller
from PySide6.QtWidgets import QTableWidget, QWidget

if TYPE_CHECKING:
    from lightsheet.gui.panels.acquisition_table_manager import (
        AcquisitionTableManager,
    )
    from lightsheet.gui.shell.controller import Controller_MainWindow


def _mgr(
    qtbot: QtBot, request: pytest.FixtureRequest
) -> tuple[Controller_MainWindow, AcquisitionTableManager]:
    ctrl, _ = make_controller(qtbot, request)
    return ctrl, ctrl.stack_panel.table_manager


def test_table_manager_exists(qtbot: QtBot, request: pytest.FixtureRequest) -> None:
    _ctrl, mgr = _mgr(qtbot, request)
    assert isinstance(mgr, QWidget)
    assert isinstance(mgr.table, QTableWidget)


def test_table_columns(qtbot: QtBot, request: pytest.FixtureRequest) -> None:
    """Test 1: columns Name, Start (mm), End (mm), Step (μm), #Planes,
    Est. Time, Est. Size. Start/End display in mm; Step stays µm."""
    _ctrl, mgr = _mgr(qtbot, request)
    headers = [
        mgr.table.horizontalHeaderItem(i).text()
        for i in range(mgr.table.columnCount())
    ]
    assert headers == ["Name", "Start (mm)", "End (mm)",
                       "Step (\u03bcm)", "#Planes", "Est. Time", "Est. Size"]


def test_empty_state_copy(qtbot: QtBot, request: pytest.FixtureRequest) -> None:
    """Test 2: empty state renders the documented copy."""
    _ctrl, mgr = _mgr(qtbot, request)
    assert mgr.table.rowCount() == 0
    text = mgr.empty_state_text()
    assert "No stacks in the queue" in text
    assert "re-driving the stage" in text


def test_add_stack_default_row(qtbot: QtBot, request: pytest.FixtureRequest) -> None:
    """Test 3: Add Stack appends a row pre-filled with the current stack
    panel values (first plane, last plane, step size) + computed #planes."""
    ctrl, mgr = _mgr(qtbot, request)
    # Set the stack panel spinboxes to known values. The step spinbox is
    # in µm (the fixed stack-display unit; the global units toggle is
    # gone). 25.0 µm is a typical fine step.
    sp = ctrl.stack_panel.ui
    sp.doubleSpinBox_acqFirstPlane.setValue(0.0)
    sp.doubleSpinBox_acqLastPlane.setValue(0.0)
    sp.doubleSpinBox_acqPlaneStepSize.setValue(25.0)
    mgr.add_stack()
    assert mgr.table.rowCount() == 1
    row = mgr.row_at(0)
    assert row.name.startswith("Stack")
    assert row.start == 0.0
    assert row.end == 0.0
    assert row.step == 25.0
    # start == end → 0 planes (incomplete row).
    assert row.n_planes == 0


def test_cell_edit_recomputes(qtbot: QtBot, request: pytest.FixtureRequest) -> None:
    """Test 4: editing a cell updates the value + recomputes #planes/est.
    time/est. size. Start/End cells display in mm (converted to µm for the
    internal _Row); Step stays µm."""
    _ctrl, mgr = _mgr(qtbot, request)
    mgr.add_stack()
    # Edit start=10 mm, end=20 mm, step=10 µm → 1001 planes.
    mgr.set_cell(0, 1, "10")
    mgr.set_cell(0, 2, "20")
    mgr.set_cell(0, 3, "10")
    row = mgr.row_at(0)
    assert row.start == 10000.0  # 10 mm → 10000 µm
    assert row.end == 20000.0  # 20 mm → 20000 µm
    assert row.step == 10.0
    assert row.n_planes == 1001
    assert row.est_time_s > 0
    assert row.est_size_mb > 0


def test_remove_stack_confirmation(
    qtbot: QtBot, request: pytest.FixtureRequest
) -> None:
    """Test 5: Remove Stack shows a confirmation dialog with the row name;
    Yes removes, Cancel does not."""
    from unittest.mock import patch

    from PySide6.QtWidgets import QMessageBox

    _ctrl, mgr = _mgr(qtbot, request)
    mgr.add_stack()
    mgr.set_cell(0, 0, "MyStack")
    mgr.table.selectRow(0)
    assert mgr.table.rowCount() == 1

    # Cancel → row stays.
    with patch("PySide6.QtWidgets.QMessageBox.question",
               return_value=QMessageBox.StandardButton.Cancel):
        mgr.remove_stack()
    assert mgr.table.rowCount() == 1

    # Yes → row removed.
    seen_prompt: list[str] = []
    mgr.table.selectRow(0)

    def _capture(
        _parent: Any, _title: str, text: str, *args: Any, **kwargs: Any
    ) -> QMessageBox.StandardButton:
        seen_prompt.append(text)
        return QMessageBox.StandardButton.Yes

    with patch("PySide6.QtWidgets.QMessageBox.question", side_effect=_capture):
        mgr.remove_stack()
    assert mgr.table.rowCount() == 0
    assert seen_prompt, "remove_stack did not show a confirmation dialog"
    assert "MyStack" in seen_prompt[0]
    assert "Remove" in seen_prompt[0]


def test_move_up_down(qtbot: QtBot, request: pytest.FixtureRequest) -> None:
    """Test 6: Move Up / Move Down reorder the selected row."""
    _ctrl, mgr = _mgr(qtbot, request)
    mgr.add_stack()
    mgr.set_cell(0, 0, "A")
    mgr.add_stack()
    mgr.set_cell(1, 0, "B")
    mgr.add_stack()
    mgr.set_cell(2, 0, "C")
    # Select row 2 (C) and move it up → order A, C, B.
    mgr.table.selectRow(2)
    mgr.move_up()
    assert [mgr.row_at(i).name for i in range(3)] == ["A", "C", "B"]
    # Now C is at index 1; move it down → A, B, C.
    mgr.table.selectRow(1)
    mgr.move_down()
    assert [mgr.row_at(i).name for i in range(3)] == ["A", "B", "C"]


def test_incomplete_row_disables_start_queue(
    qtbot: QtBot, request: pytest.FixtureRequest
) -> None:
    """Test 7: a row with start == end or step == 0 is flagged; Start Queue
    disabled while any row is incomplete."""
    _ctrl, mgr = _mgr(qtbot, request)
    mgr.add_stack()  # default start=end=0, step=1 → incomplete (start==end)
    assert not mgr.start_queue_enabled()
    # Make it complete (10 mm / 20 mm / 10 µm — within mock motor limits).
    mgr.set_cell(0, 1, "10")
    mgr.set_cell(0, 2, "20")
    mgr.set_cell(0, 3, "10")
    assert mgr.start_queue_enabled()
    # step == 0 → incomplete again.
    mgr.set_cell(0, 3, "0")
    assert not mgr.start_queue_enabled()


def test_incomplete_row_flagged_visually(
    qtbot: QtBot, request: pytest.FixtureRequest
) -> None:
    """Test 7b: an incomplete row is flagged with a red background on the
    offending cell."""
    _ctrl, mgr = _mgr(qtbot, request)
    mgr.add_stack()
    # default start==end → incomplete; the row should be flagged.
    assert mgr.is_row_flagged(0)
    mgr.set_cell(0, 1, "10")
    mgr.set_cell(0, 2, "20")
    mgr.set_cell(0, 3, "10")
    assert not mgr.is_row_flagged(0)


def test_out_of_range_row_flagged(qtbot: QtBot, request: pytest.FixtureRequest) -> None:
    """Test 8: a start/end value outside the motor travel limits is flagged
    + the row shows the out-of-range error."""
    ctrl, mgr = _mgr(qtbot, request)
    high = ctrl.motors.horizontal.get_limit_high("\u03bcm")
    mgr.add_stack()
    # End past the high limit. The cell displays in mm; convert the
    # out-of-range µm value to mm for the cell text.
    mgr.set_cell(0, 1, "10")
    mgr.set_cell(0, 2, str((high + 10000.0) / 1000.0))
    mgr.set_cell(0, 3, "10")
    assert mgr.is_row_flagged(0)
    assert not mgr.start_queue_enabled()


def test_long_name_truncates_with_tooltip(
    qtbot: QtBot, request: pytest.FixtureRequest
) -> None:
    """Test 9: long stack names truncate with ellipsis; the full name is in
    the cell tooltip."""
    _ctrl, mgr = _mgr(qtbot, request)
    long_name = "A" * 200
    mgr.add_stack()
    mgr.set_cell(0, 0, long_name)
    item = mgr.table.item(0, 0)
    assert item.toolTip() == long_name


def test_table_scrollable(qtbot: QtBot, request: pytest.FixtureRequest) -> None:
    """Test 10: the table scrolls horizontally/vertically when content
    exceeds the viewport."""
    _ctrl, mgr = _mgr(qtbot, request)
    from PySide6.QtCore import Qt
    assert (
        mgr.table.horizontalScrollBarPolicy()
        != Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    )
    assert (
        mgr.table.verticalScrollBarPolicy()
        != Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    )


def test_zero_one_many(qtbot: QtBot, request: pytest.FixtureRequest) -> None:
    """Test 11: the table renders 0 (empty copy), 1, and N rows."""
    _ctrl, mgr = _mgr(qtbot, request)
    # 0 rows.
    assert mgr.table.rowCount() == 0
    assert "No stacks in the queue" in mgr.empty_state_text()
    # 1 row.
    mgr.add_stack()
    assert mgr.table.rowCount() == 1
    # N rows.
    for _ in range(5):
        mgr.add_stack()
    assert mgr.table.rowCount() == 6
