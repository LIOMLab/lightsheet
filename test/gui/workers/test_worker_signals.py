"""Worker signal + snapshot contract tests for PreviewWorker.

Verifies that ``PreviewWorker.run`` emits its ``finished`` signal exactly
once (whether the run completes normally, breaks on E-stop, or an
exception propagates), derives the laser selection from the frozen spawn
``MicroscopeSnapshot`` (including the continuous-mode both-checked ->
L1-only override), always calls ``stop_lasers`` in cleanup, and NEVER
accesses ``self._shell.ui.*`` widgets directly (AGENTS.md §11).
"""

from __future__ import annotations

import threading
from unittest.mock import Mock

import pytest
from pytestqt.qtbot import QtBot

pytest.importorskip("PySide6")

from lightsheet.gui.workers import PreviewWorker
from lightsheet.hal import (
    DeviceBundle,
)
from lightsheet.state import MicroscopeSnapshot, MicroscopeState


def _make_bundle() -> DeviceBundle:
    from test.helpers.factories import make_bundle

    return make_bundle()


def _snapshot(auto: tuple[bool, bool]) -> MicroscopeSnapshot:
    return MicroscopeSnapshot(lightsheet_line_time_s=1.0, auto_lasers=auto)


class _PreviewShell:
    """Minimal shell stand-in exposing only the attributes PreviewWorker.run
    reads — no ui.* widget access (the worker must not touch widgets)."""

    def __init__(self) -> None:
        self.ui = Mock()
        # Hybrid ownership: PreviewWorker reads the camera exposure spinbox
        # via shell.acquisition_panel.ui.<name> in __init__ (GUI thread,
        # before moveToThread). The shell.ui namespace is not touched for
        # panel-internal widgets.
        self.acquisition_panel = Mock()
        exposure_spinbox = self.acquisition_panel.ui.doubleSpinBox_cameraExposureTime
        exposure_spinbox.value.return_value = 100
        self.preview_mode_started = False  # skip the frame-grab loop
        self.estop_event = threading.Event()
        self._fs = Mock()
        self.sig_message = Mock()


def _make_worker(
    shell: _PreviewShell, auto: tuple[bool, bool] = (False, False)
) -> tuple[PreviewWorker, Mock]:
    hw = Mock()
    worker = PreviewWorker(_make_bundle(), hw, shell, snapshot=_snapshot(auto))  # ty: ignore[invalid-argument-type]
    return worker, hw


def test_preview_worker_finished_emits_exactly_once_normal(qtbot: QtBot) -> None:
    """PreviewWorker.run with preview_mode_started=False completes
    normally and emits finished exactly once."""
    shell = _PreviewShell()
    worker, _hw = _make_worker(shell)

    finished_count: list[int] = []
    worker.finished.connect(lambda: finished_count.append(1))

    worker.run()

    assert len(finished_count) == 1, "finished must emit exactly once on normal exit"


def test_preview_worker_finished_emits_exactly_once_estop(qtbot: QtBot) -> None:
    """PreviewWorker.run with estop_event set breaks out of the loop and
    emits finished exactly once."""
    shell = _PreviewShell()
    shell.preview_mode_started = True
    shell.estop_event.set()
    worker, _hw = _make_worker(shell)

    finished_count: list[int] = []
    worker.finished.connect(lambda: finished_count.append(1))

    worker.run()

    assert len(finished_count) == 1, "finished must emit exactly once on E-stop break"


def test_preview_worker_finished_emits_exactly_once_exception(qtbot: QtBot) -> None:
    """PreviewWorker.run with a camera.arm() exception catches it, emits
    sig_message, and still emits finished exactly once from finally."""
    shell = _PreviewShell()
    worker, _hw = _make_worker(shell)
    worker.camera.arm = Mock(side_effect=RuntimeError("camera fault"))

    finished_count: list[int] = []
    worker.finished.connect(lambda: finished_count.append(1))

    worker.run()

    shell.sig_message.emit.assert_called_once()
    assert "Preview acquisition failed" in shell.sig_message.emit.call_args[0][0]
    assert len(finished_count) == 1, "finished must emit exactly once on exception"


# -- snapshot-derived laser selection ---------------------------------------


def test_preview_worker_l1_only_selection(qtbot: QtBot) -> None:
    """auto_lasers=(True, False): the snapshot is passed through to
    start_lasers with no continuous-mode override; stop_lasers runs in
    the cleanup tail."""
    shell = _PreviewShell()
    snap = _snapshot((True, False))
    hw = Mock()
    worker = PreviewWorker(_make_bundle(), hw, shell, snapshot=snap)  # ty: ignore[invalid-argument-type]
    worker.run()
    hw.start_lasers.assert_called_once_with(snap, energize_lasers=None)
    hw.stop_lasers.assert_called_once()


def test_preview_worker_l2_only_selection(qtbot: QtBot) -> None:
    """auto_lasers=(False, True): the snapshot is passed through with no
    override — start_lasers energizes L2 from the snapshot flags."""
    shell = _PreviewShell()
    snap = _snapshot((False, True))
    hw = Mock()
    worker = PreviewWorker(_make_bundle(), hw, shell, snapshot=snap)  # ty: ignore[invalid-argument-type]
    worker.run()
    hw.start_lasers.assert_called_once_with(snap, energize_lasers=None)
    hw.stop_lasers.assert_called_once()


def test_preview_worker_both_selected_maps_to_l1_only(qtbot: QtBot) -> None:
    """auto_lasers=(True, True): continuous mode energizes ONLY L1 — the
    override tuple (True, False) is passed to start_lasers so L2 stays off
    for the whole session (one-laser invariant holds trivially)."""
    shell = _PreviewShell()
    snap = _snapshot((True, True))
    hw = Mock()
    worker = PreviewWorker(_make_bundle(), hw, shell, snapshot=snap)  # ty: ignore[invalid-argument-type]
    worker.run()
    hw.start_lasers.assert_called_once_with(snap, energize_lasers=(True, False))
    hw.stop_lasers.assert_called_once()


def test_preview_worker_neither_selected(qtbot: QtBot) -> None:
    """auto_lasers=(False, False): start_lasers is still invoked with the
    snapshot (it energizes nothing) and stop_lasers still runs."""
    shell = _PreviewShell()
    snap = _snapshot((False, False))
    hw = Mock()
    worker = PreviewWorker(_make_bundle(), hw, shell, snapshot=snap)  # ty: ignore[invalid-argument-type]
    worker.run()
    hw.start_lasers.assert_called_once_with(snap, energize_lasers=None)
    hw.stop_lasers.assert_called_once()


def test_preview_worker_estop_before_start_never_energizes(qtbot: QtBot) -> None:
    """E-stop set before run() -> start_lasers is never called, but
    stop_lasers still runs in the finally cleanup and finished emits."""
    shell = _PreviewShell()
    shell.estop_event.set()
    snap = _snapshot((True, True))
    hw = Mock()
    worker = PreviewWorker(_make_bundle(), hw, shell, snapshot=snap)  # ty: ignore[invalid-argument-type]
    finished_count: list[int] = []
    worker.finished.connect(lambda: finished_count.append(1))
    worker.run()
    hw.start_lasers.assert_not_called()
    hw.stop_lasers.assert_called_once()
    assert len(finished_count) == 1


def test_preview_worker_snapshot_immune_to_post_spawn_model_edits(
    qtbot: QtBot,
) -> None:
    """The worker's frozen snapshot does not follow model edits made after
    construction — mid-run GUI changes are intent for the NEXT run only."""
    shell = _PreviewShell()
    state = MicroscopeState()
    state.set_auto_lasers(True, True)
    snap = state.snapshot()
    hw = Mock()
    worker = PreviewWorker(_make_bundle(), hw, shell, snapshot=snap)  # ty: ignore[invalid-argument-type]
    # Post-spawn model edit.
    state.set_auto_lasers(False, False)
    worker.run()
    # The run used the spawn-time selection (both -> L1-only override),
    # not the edited (False, False).
    hw.start_lasers.assert_called_once_with(snap, energize_lasers=(True, False))
    assert worker._snapshot.auto_lasers == (True, True)


def test_preview_worker_stop_lasers_on_exception_exit(qtbot: QtBot) -> None:
    """stop_lasers runs even when the body raises — a worker that exits
    mid-acquisition must not leave hardware energized."""
    shell = _PreviewShell()
    snap = _snapshot((True, False))
    hw = Mock()
    worker = PreviewWorker(_make_bundle(), hw, shell, snapshot=snap)  # ty: ignore[invalid-argument-type]
    worker.camera.arm = Mock(side_effect=RuntimeError("camera fault"))
    worker.run()
    hw.stop_lasers.assert_called_once()


def test_preview_worker_never_accesses_ui_widgets(qtbot: QtBot) -> None:
    """PreviewWorker.run must NOT access any self._shell.ui.* widget. The
    exposure-time spinbox read happens in PreviewWorker.__init__ on the
    GUI thread (before moveToThread), so run() never reaches into the
    shell's ui.* from the worker thread. The worker never mutates
    widgets — all cross-thread UI effects flow through queued signals
    (AGENTS.md §11).

    Verified by giving the shell a Mock ui and asserting no ui.* attribute
    other than doubleSpinBox_cameraExposureTime was accessed after run()."""
    shell = _PreviewShell()
    worker, _hw = _make_worker(shell)

    worker.run()

    # The shell.ui namespace must NOT be accessed for any panel-internal
    # widget (hybrid ownership — panel-internal widgets live on their
    # panel's ui, not on shell.ui).
    shell_ui_children = [name for name in shell.ui._mock_children]
    assert shell_ui_children == [], (
        f"PreviewWorker must not access shell.ui.* — got {shell_ui_children}"
    )

    # The only permitted panel-internal access is
    # doubleSpinBox_cameraExposureTime via acquisition_panel.ui (the
    # exposure-time read in PreviewWorker.__init__ on the GUI thread,
    # before moveToThread). No other widget should be touched.
    accessed_children = [name for name in shell.acquisition_panel.ui._mock_children]
    for child_name in accessed_children:
        assert child_name == "doubleSpinBox_cameraExposureTime", (
            f"PreviewWorker must not access acquisition_panel.ui.{child_name} — "
            f"only doubleSpinBox_cameraExposureTime is permitted (AGENTS.md §11)"
        )
