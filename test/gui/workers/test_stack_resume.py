"""StackWorker resume-offset tests.

The fixed-stack crash/resume tracer: ``start_plane`` shifts the
acquisition loop to ``range(start_plane, n_planes)`` while the position
formula stays absolute (``stack_starting_plane + plane * stack_step``),
so a resumed run re-acquires only the missing planes at the correct
motor positions.

The full on-disk crash/resume tracers (reopen + append into the torn
fileset, single-channel and multi-channel) run against the real
``FrameSaverController`` with a synchronous save-consumer drain so the
committed-plane cursor is deterministic.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import Mock

import h5py
import numpy as np
import pytest
from pytestqt.qtbot import QtBot

pytest.importorskip("PySide6")

from lightsheet.gui.workers import StackWorker
from lightsheet.hal import DeviceBundle
from lightsheet.resume import read_manifest
from lightsheet.resume.probe import _common_resume_plane, probe_hdf5

if TYPE_CHECKING:
    from lightsheet.gui.shell.controller import Controller_MainWindow


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
        shell,
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
            shell,
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
    qtbot: QtBot, controller: Controller_MainWindow, monkeypatch: pytest.MonkeyPatch
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


def _image_datasets(path: str | Path) -> list[str]:
    """Sorted reconstructed_frame dataset names in an HDF5 file."""
    with h5py.File(str(path), "r") as f:
        return sorted(k for k in f if k.startswith("reconstructed_frame"))


def _dataset(f: h5py.File, name: str) -> h5py.Dataset:
    """Narrow ``f[name]`` to an image dataset (asserts on wrong types)."""
    ds = f[name]
    assert isinstance(ds, h5py.Dataset)
    return ds


def _arm_crash_run(ctrl: Controller_MainWindow, tmp_path: Path, n_planes: int) -> None:
    """Point the real controller at tmp_path with a valid stack plan."""
    ctrl.saving_allowed = True
    ctrl.number_of_planes = n_planes
    ctrl.stack_mode_started = True
    ctrl.stack_starting_plane = 0.0
    ctrl.stack_step = 10
    ctrl.save_format = "hdf5"
    ctrl.save_directory = str(tmp_path)


def test_fixed_stack_crash_resume_end_to_end(
    qtbot: QtBot, controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """Full tracer: run part of a fixed stack through the real save
    path, simulate a crash (the save consumer dies with no stop_saving
    lifecycle), then resume through a FRESH worker with
    start_plane=manifest cursor. The torn fileset must be appended in
    place: all N planes land in the original file with contiguous
    dataset indices, pre-crash data is preserved, and the manifest
    reaches a terminal state.

    The save consumer is kept synchronous (start_saving only sets the
    flag; the test drains the queue via frame_saver_worker) so exactly
    the frames committed before the 'crash' land on disk — no thread
    timing can flake the cursor.
    """
    ctrl = controller
    n_planes = 5
    crash_after = 2
    _arm_crash_run(ctrl, tmp_path, n_planes)
    ctrl.save_filepath = str(tmp_path / "fixed_crash")
    ctrl.save_description = "crash resume"
    # Single-channel run: laser 1 only.
    ctrl._auto_laser1 = True
    ctrl._auto_laser2 = False
    ctrl.save_panel.ui.radioButton_saveAllCrop.setChecked(False)
    ctrl.save_panel.ui.radioButton_saveAllFull.setChecked(False)

    fs = ctrl._fs.frame_saver
    # No saver QThread: frames accumulate in the queue; the test drains
    # them synchronously — that is exactly the consumer's durable work.
    fs.start_saving = lambda: setattr(fs, "saving_started", True)  # ty: ignore[invalid-assignment]

    def _acquire_then_die() -> bool:
        i = getattr(_acquire_then_die, "_n", 0)
        _acquire_then_die._n = i + 1  # ty: ignore[unresolved-attribute]
        # Plane i carries pixel value i+1 so on-disk reads identify
        # which run produced each dataset.
        ctrl.reconstructed_frame = np.full((4, 4), i + 1, dtype=np.uint16)
        if i >= crash_after:
            # The process dies here: the consumer never sees a
            # stop_saving lifecycle update.
            ctrl.saving_allowed = False
            ctrl.stack_mode_started = False
        return True

    worker1 = StackWorker(
        ctrl._bundle,
        ctrl._hw,
        ctrl,
        save_description="crash resume",
        multi_channel=False,
    )
    worker1.acquire_scan = _acquire_then_die  # ty: ignore[invalid-assignment]
    worker1.run()
    assert worker1._run_completed is False
    # Crash signature: no lifecycle update was ever staged.
    assert fs.manifest_update_queue.empty()

    # The consumer had committed exactly `crash_after` planes when it
    # died (saving_started False -> drain the queue and exit).
    fs.saving_started = False
    fs.frame_saver_worker()

    torn_path = fs.filenames_list[0]
    manifest_path = fs._manifest_path
    assert manifest_path is not None
    crashed = read_manifest(manifest_path)
    assert crashed is not None
    assert crashed.state == "in_progress"
    assert probe_hdf5(torn_path) == crash_after
    # The manifest cursor is the committed-plane truth the resume
    # offsets from.
    resume_plane = max(crashed.cursors["hdf5"].values())
    assert resume_plane == crash_after, (
        f"crash manifest must record {crash_after} committed planes; "
        f"got cursors {crashed.cursors}"
    )

    # --- resume through a fresh worker -------------------------------
    ctrl.saving_allowed = True
    ctrl.stack_mode_started = True

    def _acquire_resumed() -> bool:
        i = getattr(_acquire_resumed, "_n", 0)
        _acquire_resumed._n = i + 1  # ty: ignore[unresolved-attribute]
        # Resumed planes carry 1000+plane so on-disk reads can tell
        # re-acquired data from pre-crash data.
        plane = resume_plane + i
        ctrl.reconstructed_frame = np.full((4, 4), 1000 + plane, dtype=np.uint16)
        return True

    worker2 = StackWorker(
        ctrl._bundle,
        ctrl._hw,
        ctrl,
        save_description="crash resume",
        multi_channel=False,
        start_plane=resume_plane,
        resume_manifest=crashed,
    )
    worker2.acquire_scan = _acquire_resumed  # ty: ignore[invalid-assignment]
    worker2.run()
    assert worker2._run_completed is True
    fs.saving_started = False
    fs.frame_saver_worker()

    # Every plane 0..n_planes-1 must land in the ORIGINAL torn fileset —
    # append-in-place is the contract; a healthy torn file must never
    # spawn a second fileset.
    names = _image_datasets(torn_path)
    assert names == [f"reconstructed_frame{i:03d}" for i in range(1, n_planes + 1)], (
        f"torn fileset incomplete after resume: {names} in {torn_path}"
    )
    with h5py.File(str(torn_path), "r") as f:
        for p in range(crash_after):
            ds = _dataset(f, f"reconstructed_frame{p + 1:03d}")
            assert (ds[0] == p + 1).all(), (
                f"pre-crash plane {p} data was altered by the resume"
            )
        for p in range(crash_after, n_planes):
            ds = _dataset(f, f"reconstructed_frame{p + 1:03d}")
            assert (ds[0] == 1000 + p).all(), (
                f"resumed plane {p} missing from the torn fileset"
            )

    # The torn fileset's own manifest must reach a terminal state — a
    # manifest left in_progress means the next scan would offer the same
    # acquisition for resume again.
    assert manifest_path is not None
    final = read_manifest(manifest_path)
    assert final is not None
    assert final.state == "completed", (
        f"manifest must finalize as completed after a full resume; "
        f"got {final.state!r} (cursors {final.cursors})"
    )
    assert final.cursors["hdf5"].get(torn_path) == n_planes


def test_multi_channel_crash_resumes_at_complete_plane_pair(
    qtbot: QtBot, controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """Full tracer: a 2-channel stack is killed mid-pair — the channel-0
    frame of plane K reaches disk but its channel-1 partner is lost.
    The common resume plane is the last complete pair (K); a fresh
    worker with start_plane=K re-acquires both channels in lockstep and
    each channel file ends with all N planes, contiguously indexed, with
    the torn tail overwritten by the resumed data.
    """
    ctrl = controller
    n_planes = 4
    k = 2  # last complete plane-pair index boundary
    _arm_crash_run(ctrl, tmp_path, n_planes)
    ctrl.save_filepath = str(tmp_path / "mc_crash")
    ctrl.save_description = "mc crash resume"
    ctrl._auto_laser1 = True
    ctrl._auto_laser2 = True
    ctrl.save_panel.ui.radioButton_saveAllCrop.setChecked(False)
    ctrl.save_panel.ui.radioButton_saveAllFull.setChecked(False)

    fs = ctrl._fs.frame_saver
    fs.start_saving = lambda: setattr(fs, "saving_started", True)  # ty: ignore[invalid-assignment]

    # Frame values encode (plane, channel): 10*plane + channel + 1.
    def _acquire_crash() -> bool:
        i = getattr(_acquire_crash, "_n", 0)
        _acquire_crash._n = i + 1  # ty: ignore[unresolved-attribute]
        plane, channel = divmod(i, 2)
        ctrl.reconstructed_frame = np.full(
            (4, 4), 10 * plane + channel + 1, dtype=np.uint16
        )
        return True

    # The consumer dies after the channel-0 frame of plane K is
    # delivered: every later enqueue is dropped (the torn plane pair).
    delivered = {"n": 0}
    orig_enqueue = fs.enqueue_buffer

    def _enqueue_until_death(item: object) -> None:
        delivered["n"] += 1
        if delivered["n"] > 2 * k + 1:
            return  # consumer dead — frame lost
        orig_enqueue(item)  # ty: ignore[invalid-argument-type]
        if delivered["n"] == 2 * k + 1:
            ctrl.saving_allowed = False
            ctrl.stack_mode_started = False

    fs.enqueue_buffer = _enqueue_until_death  # ty: ignore[invalid-assignment]

    worker1 = StackWorker(
        ctrl._bundle,
        ctrl._hw,
        ctrl,
        save_description="mc crash resume",
        multi_channel=True,
    )
    worker1.acquire_scan = _acquire_crash  # ty: ignore[invalid-assignment]
    worker1.run()
    assert worker1._run_completed is False
    assert fs.manifest_update_queue.empty()

    fs.saving_started = False
    fs.frame_saver_worker()

    ch0_path = fs.filenames_lists[0][0]
    ch1_path = fs.filenames_lists[1][0]
    manifest_path = fs._manifest_path
    assert manifest_path is not None
    crashed = read_manifest(manifest_path)
    assert crashed is not None
    assert crashed.state == "in_progress"
    # Torn pair: channel 0 committed plane K, channel 1 stopped at K-1.
    assert probe_hdf5(ch0_path) == k + 1
    assert probe_hdf5(ch1_path) == k
    assert crashed.cursors["hdf5"][ch0_path] == k + 1
    assert crashed.cursors["hdf5"][ch1_path] == k

    # The common resume plane is the last COMPLETE pair — the torn
    # channel-0 tail must be re-acquired in lockstep.
    probes = {
        "hdf5": {
            ch0_path: probe_hdf5(ch0_path),
            ch1_path: probe_hdf5(ch1_path),
        }
    }
    common, torn_tail = _common_resume_plane(crashed, probes)
    assert torn_tail is True
    assert common == k

    # --- resume through a fresh worker -------------------------------
    fs.enqueue_buffer = orig_enqueue  # ty: ignore[invalid-assignment]
    ctrl.saving_allowed = True
    ctrl.stack_mode_started = True

    # Record the per-plane laser selection order — lockstep proof.
    selects: list[int] = []
    orig_select = ctrl._hw.select_laser

    def _record_select(idx: int) -> None:
        selects.append(idx)
        orig_select(idx)

    ctrl._hw.select_laser = _record_select  # ty: ignore[invalid-assignment]

    def _acquire_resumed() -> bool:
        i = getattr(_acquire_resumed, "_n", 0)
        _acquire_resumed._n = i + 1  # ty: ignore[unresolved-attribute]
        plane, channel = divmod(i, 2)
        # Resumed frames carry 500 + 10*plane + channel so on-disk
        # reads distinguish re-acquired data from pre-crash data.
        ctrl.reconstructed_frame = np.full(
            (4, 4), 500 + 10 * (common + plane) + channel, dtype=np.uint16
        )
        return True

    worker2 = StackWorker(
        ctrl._bundle,
        ctrl._hw,
        ctrl,
        save_description="mc crash resume",
        multi_channel=True,
        start_plane=common,
        resume_manifest=crashed,
    )
    worker2.acquire_scan = _acquire_resumed  # ty: ignore[invalid-assignment]
    worker2.run()
    assert worker2._run_completed is True
    # Both channels re-acquired in lockstep for planes K..N-1.
    assert selects == [0, 1] * (n_planes - common)
    fs.saving_started = False
    fs.frame_saver_worker()

    # Per-channel on-disk parity: N contiguous datasets each, the torn
    # tail replaced by the resumed data.
    for ch, path in enumerate((ch0_path, ch1_path)):
        names = _image_datasets(path)
        assert names == [
            f"reconstructed_frame{i:03d}" for i in range(1, n_planes + 1)
        ], f"channel {ch} fileset incomplete after resume: {names}"
        with h5py.File(str(path), "r") as f:
            for p in range(common):
                expected = 10 * p + ch + 1
                ds = _dataset(f, f"reconstructed_frame{p + 1:03d}")
                assert (ds[0] == expected).all(), (
                    f"channel {ch} plane {p}: pre-crash data altered"
                )
            for p in range(common, n_planes):
                expected = 500 + 10 * p + ch
                ds = _dataset(f, f"reconstructed_frame{p + 1:03d}")
                assert (ds[0] == expected).all(), (
                    f"channel {ch} plane {p}: resumed data missing — "
                    f"torn tail not re-acquired"
                )

    assert manifest_path is not None
    final = read_manifest(manifest_path)
    assert final is not None
    assert final.state == "completed"
    # Per-channel cursors both reach the full plane count.
    assert final.cursors["hdf5"][ch0_path] == n_planes
    assert final.cursors["hdf5"][ch1_path] == n_planes


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
        shell,
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
    """A resumed worker emits the planes completed in this run
    (current_plane - start_plane) so the bar — ranged 0 to
    n_planes - start_plane — fills across the remaining planes only."""
    bundle = _make_bundle()
    shell = _make_shell(bundle, n_planes=4)
    worker = _make_worker(bundle, shell, n_planes=4, start_plane=2)
    worker.acquire_scan = Mock(return_value=True)  # type: ignore[assignment]

    worker.run()

    values = [c.args[0] for c in shell.sig_progress_update.emit.call_args_list]
    assert values[0] == 0
    assert values[-1] == 2  # n_planes - start_plane: the bar's maximum
    assert 1 in values, values
