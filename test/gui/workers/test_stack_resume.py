"""StackWorker resume-offset tests.

The fixed-stack crash/resume tracer: ``start_plane`` shifts the
acquisition loop to ``range(start_plane, n_planes)`` while the position
formula stays absolute (``stack_starting_plane + plane * stack_step``),
so a resumed run re-acquires only the missing planes at the correct
motor positions.

The full on-disk crash/resume (reopen + append into the torn fileset)
needs the Plan-02 probe/append work, so that integration is xfail-marked
here; the offset/loop contract and the manifest cursor truth are covered
independently.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from pytestqt.qtbot import QtBot

pytest.importorskip("PySide6")

from lightsheet.gui.workers import StackWorker
from lightsheet.hal import DeviceBundle


def _make_bundle() -> DeviceBundle:
    from test.helpers.factories import make_bundle

    return make_bundle()


def _make_shell(bundle: DeviceBundle, n_planes: int) -> Mock:
    """Minimal mock shell stand-in (same pattern as
    test_stack_worker_position_emit.py)."""
    shell = Mock()
    shell.lasers = bundle.lasers
    shell.stack_mode_started = True
    shell.estop_event = Mock()
    shell.estop_event.is_set.return_value = False
    shell.saving_allowed = False
    shell.number_of_planes = n_planes
    shell.stack_starting_plane = 0.0
    shell.stack_step = 10.0
    shell.reconstructed_frame = None
    shell.reconstructed_frames = {}
    shell._fs = Mock()
    # No real MicroscopeState — StackWorker falls back to a default
    # snapshot when state.snapshot() does not return one.
    shell.state.snapshot.return_value = None
    return shell


def _make_worker(
    bundle: DeviceBundle, shell: Mock, n_planes: int, start_plane: int
) -> StackWorker:
    worker = StackWorker(
        bundle,
        Mock(),
        shell,  # ty: ignore[invalid-argument-type]
        save_description="resume test",
        start_plane=start_plane,
    )
    worker.acquire_scan = Mock(return_value=True)
    return worker


def test_start_plane_offsets_loop_and_positions(qtbot: QtBot) -> None:
    """start_plane=2 on a 4-plane stack acquires only planes 2 and 3, at
    absolute positions 20 µm and 30 µm."""
    bundle = _make_bundle()
    shell = _make_shell(bundle, n_planes=4)
    worker = _make_worker(bundle, shell, n_planes=4, start_plane=2)

    moves: list[tuple[float, str]] = []
    orig = worker.motors.horizontal.move_absolute_position
    def _rec(pos: float, units: str) -> None:
        moves.append((pos, units))
        orig(pos, units)
    worker.motors.horizontal.move_absolute_position = _rec  # ty: ignore[invalid-assignment]

    finished: list[None] = []
    worker.finished.connect(lambda: finished.append(None))
    worker.run()

    assert moves == [(20.0, "μm"), (30.0, "μm")]
    # The loop ran to completion for the remaining planes.
    assert worker._run_completed is True
    assert len(finished) == 1


def test_start_plane_zero_is_unchanged(qtbot: QtBot) -> None:
    """Default start_plane=0 keeps the legacy full-range behavior."""
    bundle = _make_bundle()
    shell = _make_shell(bundle, n_planes=3)
    worker = _make_worker(bundle, shell, n_planes=3, start_plane=0)

    moves: list[float] = []
    orig = worker.motors.horizontal.move_absolute_position
    def _rec(pos: float, units: str) -> None:
        moves.append(pos)
        orig(pos, units)
    worker.motors.horizontal.move_absolute_position = _rec  # ty: ignore[invalid-assignment]

    worker.run()
    assert moves == [0.0, 10.0, 20.0]
    assert worker._run_completed is True


def test_start_plane_negative_rejected(qtbot: QtBot) -> None:
    bundle = _make_bundle()
    shell = _make_shell(bundle, n_planes=3)
    with pytest.raises(ValueError, match="start_plane"):
        StackWorker(
            bundle,
            Mock(),
            shell,  # ty: ignore[invalid-argument-type]
            start_plane=-1,
        )


def test_interrupted_run_marks_manifest_interrupted(qtbot: QtBot) -> None:
    """A break path (stack_mode_started cleared mid-run) finalizes the
    save side with the interrupted lifecycle, not completed."""
    bundle = _make_bundle()
    shell = _make_shell(bundle, n_planes=5)
    shell.saving_allowed = True
    worker = _make_worker(bundle, shell, n_planes=5, start_plane=0)

    # Break after the first plane: acquire_scan flips the mode flag.
    def _acquire() -> bool:
        shell.stack_mode_started = False
        return True
    worker.acquire_scan = _acquire  # ty: ignore[invalid-assignment]

    worker.run()
    assert worker._run_completed is False
    # stop_saving received the interrupted lifecycle.
    assert shell._fs.stop_saving.called
    assert shell._fs.stop_saving.call_args.kwargs.get("lifecycle") == "interrupted"


def test_spawn_stack_worker_passes_start_plane(
    qtbot: QtBot, controller: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_spawn_stack_worker(start_plane=N) forwards the offset to the
    StackWorker constructor without disturbing thread/signal wiring."""
    import lightsheet.gui.panels.acquisition_panel as ap

    captured: dict = {}  # ty: ignore[missing-type-argument]
    fake_worker = Mock()
    def _ctor(*args: object, **kwargs: object) -> Mock:
        captured.update(kwargs)
        return fake_worker
    monkeypatch.setattr(ap, "StackWorker", _ctor)

    worker = controller.acquisition_panel._spawn_stack_worker(start_plane=7)
    assert worker is fake_worker
    assert captured["start_plane"] == 7


@pytest.mark.xfail(
    reason="needs Plan 02 append/reopen — torn fileset cannot yet be resumed",
    strict=False,
)
def test_fixed_stack_crash_resume_end_to_end(
    qtbot: QtBot, controller: object, tmp_path: object
) -> None:
    """Full tracer: run half a fixed stack, simulate a crash (no
    stop_saving lifecycle), then resume through a fresh worker with
    start_plane=cursor and verify all planes land on disk.

    Pending the append/reopen machinery; until then this documents the
    target contract.
    """
    raise AssertionError("resume append path not implemented yet")
