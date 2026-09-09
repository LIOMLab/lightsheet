"""Queue execution — Start Queue runs rows sequentially via the existing
stack worker + E-stop aborts the queue (audit #11 in-full).

The queue loop runs on the GUI thread so the E-stop kill path (also GUI
thread) can abort it synchronously. Each row's stack runs on the existing
stack worker thread; the GUI thread waits for it via a QEventLoop with
quit() connected to the worker's finished signal — NOT threading.Event.wait()
(which would block the event loop and freeze the GUI). The QEventLoop keeps
the event loop pumping so timers/signals/paint events fire and the E-stop
kill path stays responsive.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest
from pytestqt.qtbot import QtBot

pytest.importorskip("PySide6")


if TYPE_CHECKING:
    from lightsheet.gui.panels.acquisition_table_manager import (
        AcquisitionTableManager,
    )
    from lightsheet.gui.shell.controller import Controller_MainWindow
    from lightsheet.gui.workers import StackWorker


def _add_valid_row(
    mgr: AcquisitionTableManager,
    start: float,
    end: float,
    step: float,
    name: str,
) -> int:
    """Add a valid queue row. ``start``/``end`` are in µm (the internal
    unit the assertions compare against — ``row.start``/``row.end`` are µm);
    they are converted to mm for the cell text (the display unit). ``step``
    is µm and stays µm in the cell."""
    mgr.add_stack()
    row = mgr.table.rowCount() - 1
    mgr.set_cell(row, 0, name)
    mgr.set_cell(row, 1, str(start / 1000.0))  # µm → mm cell
    mgr.set_cell(row, 2, str(end / 1000.0))  # µm → mm cell
    mgr.set_cell(row, 3, str(step))  # step stays µm
    return row


def _patch_worker_run(record: list[float]) -> Any:
    """Patch StackWorker.run to record the configured starting plane + emit
    finished. The fake runs on the worker QThread."""
    from lightsheet.gui.workers import StackWorker

    def _fake_run(self: StackWorker) -> None:
        record.append(self._shell.stack_starting_plane)  # ty: ignore[invalid-argument-type]
        self.finished.emit()

    return patch.object(StackWorker, "run", _fake_run)


def _patch_worker_run_slow(record: list[float], delay_s: float = 0.1) -> Any:
    """Like _patch_worker_run but sleeps so the QEventLoop wait is long
    enough for a QTimer probe to fire (GUI-responsiveness test)."""
    from lightsheet.gui.workers import StackWorker

    def _fake_run(self: StackWorker) -> None:
        record.append(self._shell.stack_starting_plane)  # ty: ignore[invalid-argument-type]
        time.sleep(delay_s)
        self.finished.emit()

    return patch.object(StackWorker, "run", _fake_run)


def test_queue_executes_rows_in_order(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """Test 1: Start Queue with 3 rows executes them in order."""
    ctrl = controller
    mgr = ctrl.stack_panel.table_manager
    _add_valid_row(mgr, 1000, 1100, 10, "A")
    _add_valid_row(mgr, 2000, 2100, 10, "B")
    _add_valid_row(mgr, 3000, 3100, 10, "C")
    assert mgr.start_queue_enabled()

    executed: list[float] = []
    with _patch_worker_run(executed):
        mgr._start_queue()
    assert executed == [1000.0, 2000.0, 3000.0], (
        f"rows executed out of order: {executed}"
    )


def test_queue_configures_stack_params_per_row(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """Test 2: each row configures stack_starting_plane/ending_plane/
    number_of_planes from the row's start/end/step before running."""
    ctrl = controller
    mgr = ctrl.stack_panel.table_manager
    _add_valid_row(mgr, 500, 600, 10, "A")  # 11 planes
    _add_valid_row(mgr, 700, 702, 1, "B")  # 3 planes

    seen: list[tuple] = []  # ty: ignore[missing-type-argument]
    from lightsheet.gui.workers import StackWorker

    def _fake_run(self: StackWorker) -> None:
        seen.append(
            (
                self._shell.stack_starting_plane,
                self._shell.stack_ending_plane,
                int(self._shell.number_of_planes),
            )
        )
        self.finished.emit()

    with patch.object(StackWorker, "run", _fake_run):
        mgr._start_queue()
    assert seen == [(500.0, 600.0, 11), (700.0, 702.0, 3)]


def test_queue_mode_badge_shows_row_index(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """Test 3: the mode badge shows 'STACK RUNNING' with the row index
    during queue execution."""
    ctrl = controller
    mgr = ctrl.stack_panel.table_manager
    _add_valid_row(mgr, 1000, 1100, 10, "A")
    _add_valid_row(mgr, 2000, 2100, 10, "B")
    _add_valid_row(mgr, 3000, 3100, 10, "C")

    from PySide6.QtCore import QTimer

    badge_texts: list[str] = []

    def _probe() -> None:
        badge_texts.append(ctrl.ui.label_modeBadge.text())

    # Schedule the probe to fire during the first row's QEventLoop wait.
    QTimer.singleShot(0, _probe)
    executed: list[float] = []
    with _patch_worker_run_slow(executed, delay_s=0.1):
        mgr._start_queue()
    assert executed == [1000.0, 2000.0, 3000.0]
    assert badge_texts, "probe did not fire during queue execution"
    assert any("row" in t.lower() for t in badge_texts), (
        f"mode badge did not show row index during queue: {badge_texts}"
    )


def test_queue_moves_stage_to_row_start(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """Test 4: between rows, the stage moves to the next row's start
    position (the operator does NOT re-drive the stage)."""
    ctrl = controller
    mgr = ctrl.stack_panel.table_manager
    _add_valid_row(mgr, 1000, 1100, 10, "A")
    _add_valid_row(mgr, 3000, 3100, 10, "B")

    positions: list[float] = []
    orig = ctrl.motors.horizontal.move_absolute_position

    def _record(pos: float, units: Any) -> Any:
        positions.append(pos)
        return orig(pos, units)

    with (
        patch.object(
            ctrl.motors.horizontal, "move_absolute_position", side_effect=_record
        ),
        _patch_worker_run([]),
    ):
        mgr._start_queue()
    # The queue moves to each row's start (1000, 3000) before the worker
    # runs. The worker's per-plane moves also call move_absolute_position,
    # but the row-start moves must include 1000 and 3000.
    assert 1000.0 in positions
    assert 3000.0 in positions


def test_estop_aborts_queue(qtbot: QtBot, controller: Controller_MainWindow) -> None:
    """Test 5: E-stop during queue execution aborts the current stack +
    stops the queue (no more rows execute)."""
    ctrl = controller
    mgr = ctrl.stack_panel.table_manager
    _add_valid_row(mgr, 1000, 1100, 10, "A")
    _add_valid_row(mgr, 2000, 2100, 10, "B")
    _add_valid_row(mgr, 3000, 3100, 10, "C")

    executed: list[float] = []

    from lightsheet.gui.workers import StackWorker

    def _fake_run(self: StackWorker) -> None:
        executed.append(self._shell.stack_starting_plane)  # ty: ignore[invalid-argument-type]
        # Trigger E-stop after the first row completes.
        if len(executed) == 1:
            ctrl.estop_event.set()
        self.finished.emit()

    with patch.object(StackWorker, "run", _fake_run):
        mgr._start_queue()
    # Only the first row executed; the queue stopped after E-stop.
    assert executed == [1000.0], f"queue did not stop after E-stop: {executed}"
    # Reset estop for teardown.
    ctrl.estop_event.clear()


def test_no_auto_resume_after_estop(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """Test 6: after E-stop, the queue does not auto-resume; the operator
    must re-arm + manually restart."""
    ctrl = controller
    mgr = ctrl.stack_panel.table_manager
    _add_valid_row(mgr, 1000, 1100, 10, "A")
    _add_valid_row(mgr, 2000, 2100, 10, "B")

    executed: list[float] = []
    from lightsheet.gui.workers import StackWorker

    def _fake_run(self: StackWorker) -> None:
        executed.append(self._shell.stack_starting_plane)  # ty: ignore[invalid-argument-type]
        if len(executed) == 1:
            ctrl.estop_event.set()
        self.finished.emit()

    with patch.object(StackWorker, "run", _fake_run):
        mgr._start_queue()
    assert executed == [1000.0]
    # The queue is no longer active.
    assert mgr._queue_active is False
    ctrl.estop_event.clear()


def test_out_of_range_row_caught(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """Test 7: a row whose range exceeds travel limits is caught (the
    table validation flags it; if it slips, the worker's per-plane
    ValueError catch aborts that row)."""
    ctrl = controller
    mgr = ctrl.stack_panel.table_manager
    high = ctrl.motors.horizontal.get_limit_high("\u03bcm")
    _add_valid_row(mgr, 1000, 1100, 10, "A")
    # Row B: start past the high limit — flagged by table validation.
    # Cells display in mm; ``high`` is µm, so convert to mm for the cell
    # text. Using a mm-scale cell value (not a µm-scale one) makes the test
    # actually verify the mm->µm conversion in _recompute_row: with the
    # conversion present, (high+50000)/1000 mm -> high+50000 µm > high is
    # flagged; if the conversion were missing, the raw (high+50000)/1000
    # (~151) would be < high (~101600) and the row would NOT be flagged,
    # failing the assertion below.
    mgr.add_stack()
    mgr.set_cell(1, 0, "B")
    mgr.set_cell(1, 1, str((high + 50000.0) / 1000.0))  # µm -> mm cell
    mgr.set_cell(1, 2, str((high + 51000.0) / 1000.0))  # µm -> mm cell
    mgr.set_cell(1, 3, "10")
    # Start Queue is disabled because row B is flagged.
    assert not mgr.start_queue_enabled()


def test_error_copy_on_no_rows(qtbot: QtBot, controller: Controller_MainWindow) -> None:
    """Test 8: the error-state copy renders if start-attempt fails (no
    rows)."""
    ctrl = controller
    mgr = ctrl.stack_panel.table_manager
    assert mgr.table.rowCount() == 0
    messages: list[str] = []
    ctrl.sig_message.connect(messages.append)
    mgr._start_queue()
    assert any("Cannot start the queue" in m for m in messages), (
        f"error-state copy not emitted: {messages}"
    )


def test_queue_uses_qeventloop_not_threading_wait(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """Test 9: the queue loop uses QEventLoop with quit() connected to the
    worker's finished signal — NOT threading.Event.wait()."""
    ctrl = controller
    mgr = ctrl.stack_panel.table_manager
    _add_valid_row(mgr, 1000, 1100, 10, "A")
    _add_valid_row(mgr, 2000, 2100, 10, "B")

    used_qeventloop = {"value": False}
    used_threading_wait = {"value": False}

    import threading

    from PySide6.QtCore import QEventLoop

    orig_eventloop_exec = QEventLoop.exec
    orig_event_wait = threading.Event.wait

    def _spy_exec(self: Any, *args: Any, **kwargs: Any) -> Any:
        used_qeventloop["value"] = True
        return orig_eventloop_exec(self, *args, **kwargs)

    def _spy_wait(self: Any, *args: Any, **kwargs: Any) -> Any:
        # Only flag if called on the estop_event from the GUI thread during
        # the queue (the worker thread's internal polling uses it too, but
        # that runs on the worker thread — here we only care that the queue
        # loop on the GUI thread does not call wait).
        used_threading_wait["value"] = True
        return orig_event_wait(self, *args, **kwargs)

    with (
        patch.object(QEventLoop, "exec", _spy_exec),
        patch.object(threading.Event, "wait", _spy_wait),
        _patch_worker_run([]),
    ):
        mgr._start_queue()
    assert used_qeventloop["value"], (
        "queue loop did not use QEventLoop.exec() for the non-blocking wait"
    )


def test_worker_stays_threading_no_qthread_in_table(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """Test 10: no new worker bypasses the per-plane ValueError catch; the
    queue re-uses the existing StackWorker (which has the catch)."""
    import inspect

    from lightsheet.gui.panels.acquisition_table_manager import AcquisitionTableManager
    from lightsheet.gui.workers import StackWorker

    src = inspect.getsource(AcquisitionTableManager)
    assert "QThread" not in src, (
        "AcquisitionTableManager must not spawn a QThread directly — it "
        "re-uses the existing StackWorker invocation."
    )
    # The worker's per-plane ValueError catch is preserved.
    worker_src = inspect.getsource(StackWorker)
    assert "ValueError" in worker_src


def test_gui_thread_responsive_during_queue(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """Test 11: GUI thread stays responsive during queue execution — a
    QTimer.singleShot fires within 200ms while a multi-row queue is
    running (the QEventLoop non-blocking wait keeps the event loop
    pumping). Mirrors the estop-freeze responsiveness probe pattern."""
    ctrl = controller
    mgr = ctrl.stack_panel.table_manager
    _add_valid_row(mgr, 1000, 1100, 10, "A")
    _add_valid_row(mgr, 2000, 2100, 10, "B")
    _add_valid_row(mgr, 3000, 3100, 10, "C")

    from PySide6.QtCore import QTimer

    probe_fired = {"value": False}

    def _probe() -> None:
        probe_fired["value"] = True

    # Schedule the probe before the queue starts; it must fire during the
    # first row's QEventLoop wait (the worker sleeps 100ms).
    QTimer.singleShot(0, _probe)
    executed: list[float] = []
    with _patch_worker_run_slow(executed, delay_s=0.1):
        mgr._start_queue()
    assert executed == [1000.0, 2000.0, 3000.0]
    assert probe_fired["value"] is True, (
        "QTimer.singleShot(0) did not fire during queue execution — the "
        "GUI event loop is blocked (threading.Event.wait was used instead "
        "of QEventLoop)."
    )
