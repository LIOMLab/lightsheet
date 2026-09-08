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


@pytest.mark.xfail(
    reason="needs full multi-channel save/resume wiring in the test harness",
    strict=False,
)
def test_multi_channel_crash_resumes_at_complete_plane_pair(
    qtbot: QtBot, controller: object, tmp_path: object
) -> None:
    """Full tracer: a 2-channel stack is killed mid-pair, the common
    resume plane is the last complete pair, and a fresh worker with
    start_plane at that pair re-acquires both channels in lockstep.

    Pending fixture wiring for a multi-channel partial save; the unit
    contract is covered in test/resume/test_multi_channel_resume.py.
    """
    raise AssertionError("multi-channel crash/resume harness not ready")


def test_resume_manifest_restores_matching_controller_checkpoint(
    qtbot: QtBot,
) -> None:
    """A resume manifest carrying mixed controller checkpoints restores the
    row tagged for each controller type — adaptive rows (and untagged
    legacy rows) never feed the focus controllers."""
    import uuid as uuid_mod

    from lightsheet.resume import ResumeManifest

    bundle = _make_bundle()
    shell = _make_shell(bundle, n_planes=4)
    manifest = ResumeManifest(
        uuid=uuid_mod.uuid4().hex,
        state="interrupted",
        n_planes=4,
        stack_starting_plane=0.0,
        stack_ending_plane=30.0,
        stack_step=10.0,
        save_mode="stitch",
        created_at="2026-09-08T00:00:00+00:00",
        controller_checkpoints=[
            {
                "controller": "focus",
                "residual_mm": 0.1,
                "reference_sharpness": 50.0,
                "last_command": 20.1,
                "block_count": 2,
            },
            {
                "controller": "adaptive",
                "integral": 0.01,
                "reacquire_count": 0,
                "pilot": None,
                "last_command": None,
            },
            {
                "controller": "focus",
                "residual_mm": 0.2,
                "reference_sharpness": 55.0,
                "last_command": 20.2,
                "block_count": 3,
            },
        ],
    )
    worker = StackWorker(
        bundle,
        Mock(),
        shell,  # ty: ignore[invalid-argument-type]
        save_description="resume checkpoint routing",
        resume_manifest=manifest,
    )
    focus_cp = worker._last_controller_checkpoint("focus")
    assert focus_cp is not None
    assert focus_cp["residual_mm"] == 0.2
    assert focus_cp["block_count"] == 3
    adaptive_cp = worker._last_controller_checkpoint("adaptive")
    assert adaptive_cp is not None
    assert adaptive_cp["integral"] == 0.01
    assert worker._last_controller_checkpoint("autofocus") is None


def test_resumed_progress_bar_offsets_from_start_plane(
    qtbot: QtBot,
) -> None:
    """A resumed worker emits progress relative to the remaining planes,
    not the total stack, so the bar fills from start_plane to n_planes."""
    bundle = _make_bundle()
    shell = _make_shell(bundle, n_planes=4)
    worker = _make_worker(bundle, shell, n_planes=4, start_plane=2)
    worker.acquire_scan = Mock(return_value=True)  # type: ignore[assignment]

    worker.run()

    values = [
        c.args[0] for c in shell.sig_progress_update.emit.call_args_list
    ]
    assert values[0] == 0
    assert values[-1] == 100
    assert 50 in values, values
