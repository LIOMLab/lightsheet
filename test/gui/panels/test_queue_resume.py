"""Queue-level resume and safety-gate integration tests.

Covers the resume-row machinery in ``AcquisitionTableManager`` (D-05),
the report-then-confirm ``show_resume_safety_dialog`` (D-06), the
queue-level ``QueueResumeManifest`` lifecycle, and the gate + E-stop
re-check inside ``_spawn_stack_worker`` (T-16-07-01/03).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

pytest.importorskip("PySide6")

from collections.abc import Callable
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QThread, QTimer, Signal
from PySide6.QtWidgets import QMessageBox, QWidget

import lightsheet.gui.panels.acquisition_table_manager as atm_mod
from lightsheet.gui.panels.acquisition_table_manager import (
    show_resume_safety_dialog,
)
from lightsheet.resume import (
    QueueResumeManifest,
    hash_queue_rows,
    queue_manifest_path_for,
    read_queue_manifest,
    write_manifest,
    write_queue_manifest,
)
from lightsheet.resume.gate import GateFindings
from lightsheet.resume.manifest import ResumeManifest

if TYPE_CHECKING:
    from lightsheet.gui.panels.acquisition_table_manager import (
        AcquisitionTableManager,
    )
    from lightsheet.gui.shell.controller import Controller_MainWindow


class _FakeWorker(QObject):
    """A stand-in stack worker whose finished signal fires immediately."""

    finished = Signal()


def _stub_spawn(
    qtbot: QtBot, ctrl: Controller_MainWindow, calls: list[dict]
) -> None:
    """Replace _spawn_stack_worker with a recorder that finishes at once."""

    def spawn(
        *, start_plane: int = 0, resume_manifest: ResumeManifest | None = None
    ) -> _FakeWorker:
        calls.append(
            {"start_plane": start_plane, "resume_manifest": resume_manifest}
        )
        worker = _FakeWorker()
        # The queue loop's watchdog reads _stack_thread.isRunning() — a
        # real (unstarted) QThread reports False so the watchdog quits the
        # wait loop; the finished signal is the fast path. A real QThread
        # also survives the controller fixture's thread teardown.
        ctrl._stack_thread = QThread()
        QTimer.singleShot(0, worker.finished.emit)
        return worker

    ctrl.acquisition_panel._spawn_stack_worker = spawn


def _write_manifest(
    tmp_path: Path, name: str = "acq", **kw: object
) -> Path:
    base = dict(
        uuid="cafe" * 8,
        state="interrupted",
        n_planes=4,
        stack_starting_plane=3000.0,
        stack_ending_plane=3030.0,
        stack_step=10.0,
        save_mode="stitch",
        created_at="2026-09-08T00:00:00+00:00",
        save_filepath=str(tmp_path / name),
    )
    base.update(kw)
    path = tmp_path / f"{name}.resume.json"
    write_manifest(path, ResumeManifest(**base))
    return path


def _write_queue_manifest(
    tmp_path: Path,
    rows: list[dict],
    row_index: int = 0,
    row_uuids: list[str] | None = None,
    state: str = "in_progress",
) -> Path:
    qm = QueueResumeManifest(
        uuid="feed" * 8,
        state=state,
        row_index=row_index,
        rows=rows,
        row_uuids=row_uuids or ["u0"] * len(rows),
        row_hash=hash_queue_rows(rows),
        created_at="2026-09-08T00:00:00+00:00",
        save_directory=str(tmp_path),
    )
    path = tmp_path / "acq.queue-resume.json"
    write_queue_manifest(path, qm)
    return path


def _add_two_rows(
    ctrl: Controller_MainWindow, mgr: AcquisitionTableManager
) -> None:
    sp = ctrl.stack_panel.ui
    sp.doubleSpinBox_acqFirstPlane.setValue(3.0)
    sp.doubleSpinBox_acqLastPlane.setValue(5.0)
    sp.doubleSpinBox_acqPlaneStepSize.setValue(10.0)
    mgr.add_stack()
    mgr.add_stack()


# --------------------------------------------------------------------- #
# Queue manifest lifecycle (Task 3)
# --------------------------------------------------------------------- #


def test_queue_run_writes_queue_manifest(
    qtbot: QtBot, controller: Controller_MainWindow, tmp_path: Path
) -> None:
    ctrl = controller
    mgr = ctrl.stack_panel.table_manager
    ctrl.save_directory = str(tmp_path)
    ctrl.save_filepath = str(tmp_path / "acq")
    ctrl.saving_allowed = True
    calls: list[dict] = []
    _stub_spawn(qtbot, ctrl, calls)
    _add_two_rows(ctrl, mgr)

    mgr._start_queue()

    assert len(calls) == 2
    qm_path = queue_manifest_path_for(tmp_path, "acq")
    qm = read_queue_manifest(qm_path)
    assert qm is not None
    assert qm.state == "completed"
    # row_index points at the last executed row.
    assert qm.row_index == 1
    assert len(qm.rows) == 2
    assert qm.row_uuids == mgr._row_uuids


def test_queue_abort_marks_manifest_interrupted(
    qtbot: QtBot, controller: Controller_MainWindow, tmp_path: Path
) -> None:
    ctrl = controller
    mgr = ctrl.stack_panel.table_manager
    ctrl.save_directory = str(tmp_path)
    ctrl.save_filepath = str(tmp_path / "acq")
    ctrl.saving_allowed = True
    calls: list[dict] = []

    def spawn_abort(
        *, start_plane: int = 0, resume_manifest: ResumeManifest | None = None
    ) -> _FakeWorker:
        calls.append({"start_plane": start_plane})
        ctrl.estop_event.set()
        worker = _FakeWorker()
        ctrl._stack_thread = QThread()
        QTimer.singleShot(0, worker.finished.emit)
        return worker

    ctrl.acquisition_panel._spawn_stack_worker = spawn_abort
    _add_two_rows(ctrl, mgr)

    mgr._start_queue()
    ctrl.estop_event.clear()

    qm = read_queue_manifest(queue_manifest_path_for(tmp_path, "acq"))
    assert qm is not None
    assert qm.state == "interrupted"
    # The queue ran only the first row; the abort hit before row 2.
    assert len(calls) == 1
    # The abort was detected at the row-1 loop-top check, so the manifest
    # still points at row 0 — the row that was running when the E-stop hit.
    assert qm.row_index == 0


# --------------------------------------------------------------------- #
# Resume row + state restore (Task 2)
# --------------------------------------------------------------------- #


def test_enqueue_resume_row_and_run(
    qtbot: QtBot, controller: Controller_MainWindow, tmp_path: Path
) -> None:
    ctrl = controller
    mgr = ctrl.stack_panel.table_manager
    ctrl.save_directory = str(tmp_path)
    ctrl.save_filepath = str(tmp_path / "acq")
    ctrl.saving_allowed = True
    mpath = _write_manifest(
        tmp_path,
        cursors={"hdf5": {str(tmp_path / "acq_488nm.hdf5"): 2}},
        laser_power_pct=[42.0, 7.5],
        laser_enabled=[True, False],
        auto_lasers=[True, False],
        save_options={"mode": "stitch", "description": "resumed"},
        lightsheet_line_time_s=0.001,
    )

    assert mgr.enqueue_resume_row(mpath) is True
    assert mgr.table.rowCount() == 1
    row = mgr.row_at(0)
    assert row.name.startswith("Resume:")
    assert row.start_plane == 2
    assert row.resume_manifest is not None
    assert row.n_planes == 4  # total stack planes, not remaining

    calls: list[dict] = []
    _stub_spawn(qtbot, ctrl, calls)
    mgr._start_queue()

    assert len(calls) == 1
    assert calls[0]["start_plane"] == 2
    assert calls[0]["resume_manifest"] is row.resume_manifest
    # The manifest's operator intent flowed through the model mutators.
    assert ctrl.state.laser_power_pct == (42.0, 7.5)
    assert (ctrl.state.auto_laser1, ctrl.state.auto_laser2) == (True, False)
    # Queue state was restored after the run.
    assert ctrl.stack_queue_row_index is None


def test_enqueue_resume_row_rejects_bad_manifest(
    qtbot: QtBot, controller: Controller_MainWindow, tmp_path: Path
) -> None:
    ctrl = controller
    mgr = ctrl.stack_panel.table_manager
    bad = tmp_path / "bad.resume.json"
    bad.write_text("{not json", encoding="utf-8")
    assert mgr.enqueue_resume_row(bad) is False
    assert mgr.table.rowCount() == 0

    done = _write_manifest(tmp_path, name="done", state="completed")
    assert mgr.enqueue_resume_row(done) is False
    assert mgr.table.rowCount() == 0


# --------------------------------------------------------------------- #
# Queue-level resume (Task 3)
# --------------------------------------------------------------------- #


def test_queue_resume_mid_row_continues_remaining(
    qtbot: QtBot, controller: Controller_MainWindow, tmp_path: Path
) -> None:
    ctrl = controller
    mgr = ctrl.stack_panel.table_manager
    ctrl.save_directory = str(tmp_path)
    ctrl.save_filepath = str(tmp_path / "acq")
    ctrl.saving_allowed = True
    _add_two_rows(ctrl, mgr)
    live_rows = [mgr._row_to_dict(mgr.row_at(i)) for i in range(2)]
    qpath = _write_queue_manifest(
        tmp_path, live_rows, row_index=0, row_uuids=list(mgr._row_uuids)
    )
    mpath = _write_manifest(
        tmp_path,
        cursors={"hdf5": {str(tmp_path / "acq_488nm.hdf5"): 1}},
        row_index=0,
    )

    assert mgr.enqueue_resume_row(mpath, queue_manifest=qpath) is True
    # The untouched pre-crash queue is replaced by [resume row, row 2].
    assert mgr.table.rowCount() == 2
    assert mgr.row_at(0).resume_manifest is not None
    assert mgr.row_at(1).name == "Stack 2"

    calls: list[dict] = []
    _stub_spawn(qtbot, ctrl, calls)
    mgr._start_queue()

    assert len(calls) == 2
    # The interrupted row resumes mid-stack; the remaining row runs fresh.
    assert calls[0]["start_plane"] == 1
    assert calls[0]["resume_manifest"] is not None
    assert calls[1]["start_plane"] == 0
    assert calls[1]["resume_manifest"] is None


def test_queue_resume_rejects_edited_table(
    qtbot: QtBot, controller: Controller_MainWindow, tmp_path: Path
) -> None:
    ctrl = controller
    mgr = ctrl.stack_panel.table_manager
    _add_two_rows(ctrl, mgr)
    # A queue manifest describing a DIFFERENT row list must be rejected.
    qpath = _write_queue_manifest(
        tmp_path,
        [
            {
                "name": "Other stack",
                "start": 0.0,
                "end": 100.0,
                "step": 10.0,
                "n_planes": 11,
            }
        ],
        row_index=0,
    )
    mpath = _write_manifest(tmp_path)
    assert mgr.enqueue_resume_row(mpath, queue_manifest=qpath) is False
    assert mgr.table.rowCount() == 2  # table untouched


def test_queue_resume_rebuilds_empty_table(
    qtbot: QtBot, controller: Controller_MainWindow, tmp_path: Path
) -> None:
    ctrl = controller
    mgr = ctrl.stack_panel.table_manager
    rows = [
        {"name": "Stack 1", "start": 3000.0, "end": 5000.0,
         "step": 10.0, "n_planes": 201},
        {"name": "Stack 2", "start": 3000.0, "end": 5000.0,
         "step": 10.0, "n_planes": 201},
    ]
    qpath = _write_queue_manifest(tmp_path, rows, row_index=0)
    mpath = _write_manifest(
        tmp_path, cursors={"hdf5": {str(tmp_path / "acq_488nm.hdf5"): 3}}
    )
    assert mgr.enqueue_resume_row(mpath, queue_manifest=qpath) is True
    assert mgr.table.rowCount() == 2
    assert mgr.row_at(0).resume_manifest is not None
    assert mgr.row_at(1).name == "Stack 2"


def test_corrupt_queue_manifest_rejected(tmp_path: Path) -> None:
    """A row_hash that does not match the stored rows fails closed."""
    rows = [{"name": "A", "start": 0.0, "end": 1.0, "step": 1.0,
             "n_planes": 2}]
    qm = QueueResumeManifest(
        uuid="x" * 4,
        state="in_progress",
        row_index=0,
        rows=rows,
        row_uuids=["u0"],
        row_hash="0" * 64,  # wrong on purpose
        created_at="2026-09-08T00:00:00+00:00",
    )
    path = tmp_path / "tampered.queue-resume.json"
    path.write_text(
        __import__("json").dumps(qm.to_dict()), encoding="utf-8"
    )
    assert read_queue_manifest(path) is None


# --------------------------------------------------------------------- #
# Report-then-confirm dialog (Task 1)
# --------------------------------------------------------------------- #


def _exec_clicking(button_text: str) -> Callable[[QMessageBox], int]:
    def fake_exec(self: QMessageBox) -> int:
        for btn in self.buttons():
            if btn.text() == button_text:
                btn.click()
                break
        return self.result()

    return fake_exec


def test_safety_dialog_resume_returns_true(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict = {}

    def fake_exec(self: QMessageBox) -> int:
        # Cancel must be the default AND the escape action.
        assert self.defaultButton() is not None
        assert self.defaultButton().text() == "Cancel"
        seen["escape"] = self.escapeButton()
        for btn in self.buttons():
            if btn.text() == "Resume":
                btn.click()
        return self.result()

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    findings = GateFindings(warnings=["motor drifted +0.2 mm"])
    assert show_resume_safety_dialog(None, findings) is True


def test_safety_dialog_cancel_returns_false(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(QMessageBox, "exec", _exec_clicking("Cancel"))
    findings = GateFindings(warnings=["config diff"])
    assert show_resume_safety_dialog(None, findings) is False


def test_safety_dialog_errors_block_resume(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list = []
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        staticmethod(lambda *a, **k: calls.append(a) or None),
    )
    findings = GateFindings(errors=["remaining range exceeds limits"])
    assert show_resume_safety_dialog(None, findings) is False
    assert len(calls) == 1


# --------------------------------------------------------------------- #
# Gate enforcement inside _spawn_stack_worker (T-16-07-01/03)
# --------------------------------------------------------------------- #


def test_spawn_resume_cancelled_by_dialog(
    qtbot: QtBot,
    controller: Controller_MainWindow,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A resume row whose dialog is cancelled must not spawn a worker."""
    ctrl = controller
    _write_manifest(tmp_path)
    manifest = __import__(
        "lightsheet.resume", fromlist=["read_manifest"]
    ).read_manifest(tmp_path / "acq.resume.json")
    seen: list = []

    def fake_dialog(parent: QWidget | None, findings: GateFindings) -> bool:
        seen.append(findings)
        return False

    monkeypatch.setattr(
        atm_mod, "show_resume_safety_dialog", fake_dialog
    )
    prev_worker = getattr(ctrl, "_stack_worker", None)
    worker = ctrl.acquisition_panel._spawn_stack_worker(
        resume_manifest=manifest
    )
    assert worker is None
    assert getattr(ctrl, "_stack_worker", None) is prev_worker
    assert len(seen) == 1  # findings were computed and reported


def test_spawn_resume_rechecks_estop(
    qtbot: QtBot,
    controller: Controller_MainWindow,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A confirmed resume still aborts when the E-stop is actuated."""
    ctrl = controller
    _write_manifest(tmp_path)
    manifest = __import__(
        "lightsheet.resume", fromlist=["read_manifest"]
    ).read_manifest(tmp_path / "acq.resume.json")
    monkeypatch.setattr(
        atm_mod, "show_resume_safety_dialog", lambda parent, findings: True
    )
    ctrl.estop_event.set()
    try:
        worker = ctrl.acquisition_panel._spawn_stack_worker(
            resume_manifest=manifest
        )
        assert worker is None
    finally:
        ctrl.estop_event.clear()
