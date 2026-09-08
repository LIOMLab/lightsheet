"""Tests for focus checkpoint/restore and crash/resume.

Covers the ``FocusController`` and ``AdaptiveFocusController``
checkpoint APIs, manifest persistence of focus trajectory rows, and the
FrameSaver pre-resume focus trajectory merge.
"""

from __future__ import annotations

import queue
import uuid as uuid_mod
from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pytest
from pytestqt.qtbot import QtBot

from lightsheet.focus.adaptive_controller import AdaptiveFocusController
from lightsheet.focus.controller import FocusController
from lightsheet.focus.types import (
    AutofocusConfig,
    FocusConfig,
    FocusCurve,
    FocusSample,
)
from lightsheet.resume import (
    ManifestUpdate,
    ResumeManifest,
    apply_manifest_update,
)

pytest.importorskip("PySide6")


def _manifest(**overrides: object) -> ResumeManifest:
    """Build a minimal valid manifest with override slots."""
    kwargs: dict = {
        "uuid": uuid_mod.uuid4().hex,
        "state": "in_progress",
        "n_planes": 6,
        "stack_starting_plane": 0.0,
        "stack_ending_plane": 50.0,
        "stack_step": 10.0,
        "save_mode": "stitch",
        "wavelengths": [555],
        "created_at": "2026-09-08T00:00:00+00:00",
    }
    kwargs.update(overrides)
    return ResumeManifest(**kwargs)


def _curve() -> FocusCurve:
    return FocusCurve(stage_pos=(0.0, 0.2), camera_pos=(20.0, 35.0))


def _focus_controller() -> FocusController:
    return FocusController(
        FocusConfig(enabled=True, block_size_n=2),
        _curve(),
        cam_lo_mm=0.0,
        cam_hi_mm=128.0,
    )


def _autofocus_controller() -> AdaptiveFocusController:
    return AdaptiveFocusController(
        AutofocusConfig(enabled=True, cadence=1, update_threshold=0.0),
        cam_lo_mm=0.0,
        cam_hi_mm=128.0,
        seed_camera_pos_mm=25.0,
    )


# --------------------------------------------------------------------- #
# FocusController checkpoint/restore
# --------------------------------------------------------------------- #


def test_focus_controller_checkpoint_roundtrip() -> None:
    """A checkpoint captures residual, reference sharpness, and the last
    command, and a restored controller continues the same trajectory."""
    ctrl = _focus_controller()
    ctrl.target(0.0)
    ctrl.update_residual(100.0)  # first call stores the reference
    ctrl.update_residual(80.0)  # trims the residual
    ctrl.target(0.05)
    state = ctrl.checkpoint()

    restored = FocusController(
        FocusConfig(enabled=True, block_size_n=2),
        _curve(),
        cam_lo_mm=0.0,
        cam_hi_mm=128.0,
        initial_state=state,
    )
    assert restored._residual_mm == pytest.approx(ctrl._residual_mm)
    assert restored._residual_mm != 0.0
    assert restored._reference_sharpness == pytest.approx(
        ctrl._reference_sharpness
    )
    assert restored._last_command == pytest.approx(ctrl._last_command)

    # The restored controller continues the residual path identically.
    assert restored.target(0.1) == pytest.approx(ctrl.target(0.1))
    restored.update_residual(90.0)
    ctrl.update_residual(90.0)
    assert restored._residual_mm == pytest.approx(ctrl._residual_mm)


def test_focus_controller_restore_rejects_invalid_state() -> None:
    """restore() rejects malformed or out-of-range checkpoints."""
    ctrl = _focus_controller()
    ctrl.update_residual(100.0)
    ctrl.update_residual(50.0)
    base = ctrl.checkpoint()

    # Out-of-range residual — a forged checkpoint must not push the
    # residual past the configured bound.
    with pytest.raises(ValueError, match="residual_mm"):
        FocusController(
            FocusConfig(enabled=True),
            _curve(),
            0.0,
            128.0,
            initial_state={**base, "residual_mm": 99.0},
        )
    with pytest.raises(ValueError, match="residual_mm"):
        FocusController(
            FocusConfig(enabled=True),
            _curve(),
            0.0,
            128.0,
            initial_state={**base, "residual_mm": float("nan")},
        )
    with pytest.raises(ValueError, match="reference_sharpness"):
        FocusController(
            FocusConfig(enabled=True),
            _curve(),
            0.0,
            128.0,
            initial_state={**base, "reference_sharpness": "loud"},
        )
    # A last command beyond the camera travel range is rejected.
    with pytest.raises(ValueError, match="last_command"):
        FocusController(
            FocusConfig(enabled=True),
            _curve(),
            0.0,
            128.0,
            initial_state={**base, "last_command": 9999.0},
        )
    with pytest.raises(ValueError, match="dict"):
        FocusController(
            FocusConfig(enabled=True),
            _curve(),
            0.0,
            128.0,
            initial_state=["not", "a", "dict"],  # type: ignore[arg-type]
        )


# --------------------------------------------------------------------- #
# AdaptiveFocusController checkpoint/restore
# --------------------------------------------------------------------- #


def test_autofocus_controller_checkpoint_roundtrip() -> None:
    """The per-plane autofocus controller round-trips residual, previous
    residual, predicted sharpness, seed, and last command."""
    ctrl = _autofocus_controller()
    ctrl.target(0.0)
    ctrl.update(0.0, 100.0)  # first call stores the reference
    ctrl.update(0.01, 120.0)  # residual step
    ctrl.target(0.01)
    state = ctrl.checkpoint()

    restored = AdaptiveFocusController(
        AutofocusConfig(enabled=True, cadence=1, update_threshold=0.0),
        cam_lo_mm=0.0,
        cam_hi_mm=128.0,
        seed_camera_pos_mm=25.0,
        initial_state=state,
    )
    assert restored._residual_mm == pytest.approx(ctrl._residual_mm)
    assert restored._residual_mm != 0.0
    assert restored._prev_residual_mm == pytest.approx(ctrl._prev_residual_mm)
    assert restored._predicted_sharpness == pytest.approx(
        ctrl._predicted_sharpness
    )
    assert restored._seed == pytest.approx(ctrl._seed)
    assert restored._last_command == pytest.approx(ctrl._last_command)

    # Restored controller continues the residual path identically.
    restored.update(0.02, 110.0)
    ctrl.update(0.02, 110.0)
    assert restored._residual_mm == pytest.approx(ctrl._residual_mm)
    assert restored.target(0.02) == pytest.approx(ctrl.target(0.02))


def test_autofocus_controller_restore_rejects_invalid_state() -> None:
    """restore() validates residuals, predicted sharpness, seed, and the
    last command before mutating state."""
    ctrl = _autofocus_controller()
    ctrl.update(0.0, 100.0)
    ctrl.update(0.01, 130.0)
    base = ctrl.checkpoint()

    cfg = AutofocusConfig(enabled=True)
    with pytest.raises(ValueError, match="residual_mm"):
        AdaptiveFocusController(
            cfg, 0.0, 128.0, initial_state={**base, "residual_mm": 99.0}
        )
    with pytest.raises(ValueError, match="prev_residual_mm"):
        AdaptiveFocusController(
            cfg, 0.0, 128.0, initial_state={**base, "prev_residual_mm": "x"}
        )
    with pytest.raises(ValueError, match="predicted_sharpness"):
        AdaptiveFocusController(
            cfg,
            0.0,
            128.0,
            initial_state={**base, "predicted_sharpness": float("inf")},
        )
    # Seed outside the camera travel range is rejected.
    with pytest.raises(ValueError, match="seed_camera_pos_mm"):
        AdaptiveFocusController(
            cfg, 0.0, 128.0, initial_state={**base, "seed_camera_pos_mm": -5.0}
        )
    with pytest.raises(ValueError, match="last_command"):
        AdaptiveFocusController(
            cfg, 0.0, 128.0, initial_state={**base, "last_command": 9999.0}
        )


# --------------------------------------------------------------------- #
# Manifest persistence
# --------------------------------------------------------------------- #


def test_focus_sample_as_dict_is_manifest_safe() -> None:
    """FocusSample.as_dict yields JSON-safe values."""
    sample = FocusSample(
        block_index=3,
        stage_pos_mm=0.03,
        feedforward_camera_pos_mm=26.0,
        residual_mm=0.05,
        applied_camera_pos_mm=26.05,
        sharpness_metric=123.4,
    )
    d = sample.as_dict()
    assert d["block_index"] == 3
    assert d["sharpness_metric"] == pytest.approx(123.4)

    no_sharp = FocusSample(
        block_index=0,
        stage_pos_mm=0.0,
        feedforward_camera_pos_mm=20.0,
        residual_mm=0.0,
        applied_camera_pos_mm=20.0,
    )
    assert no_sharp.as_dict()["sharpness_metric"] is None


def test_manifest_stores_focus_checkpoint_and_trajectory() -> None:
    """apply_manifest_update appends focus checkpoints and trajectory rows."""
    m = _manifest()
    cp = {
        "controller": "focus",
        "residual_mm": 0.1,
        "reference_sharpness": 100.0,
        "last_command": 26.1,
        "block_count": 2,
    }
    traj = FocusSample(
        block_index=1,
        stage_pos_mm=0.01,
        feedforward_camera_pos_mm=23.75,
        residual_mm=0.1,
        applied_camera_pos_mm=23.85,
        sharpness_metric=42.0,
    ).as_dict()
    m = apply_manifest_update(
        m, ManifestUpdate(kind="checkpoint", payload=cp, plane_index=2)
    )
    m = apply_manifest_update(
        m, ManifestUpdate(kind="trajectory", payload=traj, plane_index=2)
    )
    assert len(m.controller_checkpoints) == 1
    assert m.controller_checkpoints[0]["controller"] == "focus"
    assert m.controller_checkpoints[0]["plane_index"] == 2
    assert len(m.trajectory_samples) == 1
    assert m.trajectory_samples[0]["block_index"] == 1


# --------------------------------------------------------------------- #
# FrameSaver pre-resume focus trajectory merge
# --------------------------------------------------------------------- #


def test_frame_saver_merges_pre_resume_focus_trajectory(
    qtbot: QtBot, controller: object, tmp_path: Path
) -> None:
    """Resumed FrameSaver prepends manifest focus rows before recording
    new ones, sorted by absolute block index."""
    ctrl = controller
    ctrl.save_directory = str(tmp_path)
    ctrl.save_format = "hdf5"
    fs = ctrl._fs
    fs.reinit(1)

    pre_rows = [
        FocusSample(
            block_index=1,
            stage_pos_mm=0.01,
            feedforward_camera_pos_mm=23.75,
            residual_mm=0.02,
            applied_camera_pos_mm=23.77,
            sharpness_metric=40.0,
        ).as_dict(),
        FocusSample(
            block_index=0,
            stage_pos_mm=0.0,
            feedforward_camera_pos_mm=20.0,
            residual_mm=0.0,
            applied_camera_pos_mm=20.0,
        ).as_dict(),
    ]
    fs.frame_saver.resume_manifest = _manifest(
        n_planes=4,
        trajectory_samples=pre_rows,
    )

    fs.configure_focus(True, config=FocusConfig(enabled=True))
    assert [s.block_index for s in fs.frame_saver.focus_trajectory] == [0, 1]

    fs.record_focus_sample(
        FocusSample(
            block_index=2,
            stage_pos_mm=0.02,
            feedforward_camera_pos_mm=27.5,
            residual_mm=0.03,
            applied_camera_pos_mm=27.53,
            sharpness_metric=50.0,
        )
    )
    assert [s.block_index for s in fs.frame_saver.focus_trajectory] == [0, 1, 2]


def test_frame_saver_skips_malformed_pre_resume_focus_trajectory(
    qtbot: QtBot, controller: object, tmp_path: Path
) -> None:
    """Malformed focus rows and non-focus rows are skipped."""
    ctrl = controller
    ctrl.save_directory = str(tmp_path)
    ctrl.save_format = "hdf5"
    fs = ctrl._fs
    fs.reinit(1)

    fs.frame_saver.resume_manifest = _manifest(
        n_planes=2,
        trajectory_samples=[
            {"bogus": "row"},
            # An adaptive trajectory row — not a focus sample.
            {
                "plane_index": 0,
                "intensity_fraction": [0.5],
                "exposure_s": 0.02,
                "laser_power_mw": [10.0, 0.0],
                "control_variable_active": "exposure",
                "reacquired": False,
                "power_fallback": False,
            },
            {
                "block_index": 0,
                "stage_pos_mm": 0.0,
                "feedforward_camera_pos_mm": 20.0,
                "residual_mm": 0.0,
                "applied_camera_pos_mm": 20.0,
                "sharpness_metric": "not-a-number",
            },
        ],
    )

    fs.configure_focus(True, config=FocusConfig(enabled=True))
    assert fs.frame_saver.focus_trajectory == []


# --------------------------------------------------------------------- #
# StackWorker manifest staging
# --------------------------------------------------------------------- #


def _make_shell(bundle: object, n_planes: int) -> Mock:
    shell = Mock()
    shell.lasers = bundle.lasers
    shell.stack_mode_started = True
    shell.estop_event = Mock()
    shell.estop_event.is_set.return_value = False
    shell.saving_allowed = True
    shell.number_of_planes = n_planes
    shell.stack_starting_plane = 0.0
    shell.stack_step = 10.0
    shell.reconstructed_frame = np.full((4, 4), 30000, dtype=np.uint16)
    shell.reconstructed_frames = {}
    shell._fs = Mock()
    shell._fs.manifest_update_queue = queue.Queue()
    shell.state.snapshot.return_value = None
    return shell


def test_block_focus_worker_stages_manifest_updates(qtbot: QtBot) -> None:
    """A block-focus stack stages a checkpoint and a trajectory row on the
    manifest update queue at each focus block boundary."""
    from lightsheet.gui.workers import StackWorker
    from test.helpers.factories import make_bundle

    bundle = make_bundle()
    shell = _make_shell(bundle, n_planes=4)
    worker = StackWorker(
        bundle,
        Mock(),
        shell,
        save_description="focus staging",
        focus_cfg=FocusConfig(enabled=True, block_size_n=2),
        focus_curve=_curve(),
    )
    worker.acquire_scan = Mock(return_value=True)  # ty: ignore[invalid-assignment]

    worker.run()
    assert worker._run_completed is True

    updates: list[ManifestUpdate] = []
    while not shell._fs.manifest_update_queue.empty():
        updates.append(shell._fs.manifest_update_queue.get_nowait())

    kinds = [u.kind for u in updates]
    # Block size 2 over 4 planes → two block boundaries (planes 0 and 2),
    # each staging a checkpoint and a trajectory row.
    assert kinds == ["checkpoint", "trajectory"] * 2
    checkpoints = [u for u in updates if u.kind == "checkpoint"]
    assert checkpoints[-1].payload["controller"] == "focus"
    assert checkpoints[-1].payload["block_count"] >= 1
    traj = [u for u in updates if u.kind == "trajectory"]
    assert traj[0].payload["block_index"] == 0
    assert traj[1].payload["block_index"] == 1


def test_autofocus_worker_stages_manifest_updates(qtbot: QtBot) -> None:
    """A per-plane autofocus stack stages a checkpoint and a trajectory
    row for every plane."""
    from lightsheet.gui.workers import StackWorker
    from test.helpers.factories import make_bundle

    bundle = make_bundle()
    shell = _make_shell(bundle, n_planes=3)
    worker = StackWorker(
        bundle,
        Mock(),
        shell,
        save_description="autofocus staging",
        autofocus_cfg=AutofocusConfig(enabled=True, cadence=1),
    )
    worker.acquire_scan = Mock(return_value=True)  # ty: ignore[invalid-assignment]

    worker.run()
    assert worker._run_completed is True

    updates: list[ManifestUpdate] = []
    while not shell._fs.manifest_update_queue.empty():
        updates.append(shell._fs.manifest_update_queue.get_nowait())

    kinds = [u.kind for u in updates]
    assert kinds == ["checkpoint", "trajectory"] * 3
    checkpoints = [u for u in updates if u.kind == "checkpoint"]
    assert all(u.payload["controller"] == "autofocus" for u in checkpoints)
    assert checkpoints[-1].payload["predicted_sharpness"] is not None


# --------------------------------------------------------------------- #
# Crash/resume integration
# --------------------------------------------------------------------- #


def _fake_acquire_frames(
    worker: object, shell: Mock, frames: dict[int, np.ndarray], default: int = 30000
) -> None:
    """Install an acquire_scan stub that fills ``reconstructed_frame`` with
    a deterministic per-plane pattern. ``frames`` maps acquisition index to
    a fill value (or ``"checkerboard"`` for a high-sharpness pattern)."""
    state = {"idx": 0}

    def _acquire() -> bool:
        idx = state["idx"]
        frame = np.full((64, 64), default, dtype=np.uint16)
        fill = frames.get(idx)
        if fill == "checkerboard":
            frame[:32, :32] = 50000
            frame[:32, 32:] = 10000
            frame[32:, :32] = 10000
            frame[32:, 32:] = 50000
        elif isinstance(fill, int):
            frame[:] = fill
        shell.reconstructed_frame = frame
        state["idx"] += 1
        return True

    worker.acquire_scan = _acquire  # ty: ignore[invalid-assignment]
    worker._acquire_state = state


def _drain_updates(shell: Mock) -> list[ManifestUpdate]:
    updates: list[ManifestUpdate] = []
    q = shell._fs.manifest_update_queue
    while not q.empty():
        updates.append(q.get_nowait())
    return updates


def test_block_focus_crash_resume_continues_trajectory(qtbot: QtBot) -> None:
    """Run a block-focus stack for half the planes, simulate a crash, then
    resume from the manifest — the residual and block numbering continue
    instead of resetting to zero."""
    from lightsheet.gui.workers import StackWorker
    from test.helpers.factories import make_bundle

    bundle = make_bundle()
    shell = _make_shell(bundle, n_planes=8)
    cfg = FocusConfig(enabled=True, block_size_n=2)
    worker = StackWorker(
        bundle,
        Mock(),
        shell,
        save_description="focus crash",
        focus_cfg=cfg,
        focus_curve=_curve(),
    )
    # Plane 1's frame is high-sharpness (becomes the reference at the
    # plane-2 block boundary); later frames are flat so the residual
    # grows by residual_gain_mm at each subsequent boundary.
    _fake_acquire_frames(worker, shell, {1: "checkerboard"})

    # Simulate a crash after plane 5: the loop-top poll breaks before
    # plane 6, leaving the manifest in_progress.
    orig_run_acquire = worker.acquire_scan
    def _crash_after_five() -> bool:
        ok = orig_run_acquire()
        if worker._acquire_state["idx"] >= 6:
            shell.stack_mode_started = False
        return ok
    worker.acquire_scan = _crash_after_five  # ty: ignore[invalid-assignment]

    worker.run()
    assert worker._run_completed is False
    pre_crash_residual = worker._focus_controller._residual_mm
    assert pre_crash_residual > 0.0
    pre_crash_block_count = worker._focus_block_count
    assert pre_crash_block_count == 3  # boundaries at planes 0, 2, 4

    # Persist the staged updates into a manifest like the save worker would.
    manifest = _manifest(n_planes=8)
    for update in _drain_updates(shell):
        manifest = apply_manifest_update(manifest, update)
    assert manifest.controller_checkpoints
    assert manifest.trajectory_samples

    # Resume from the last durable plane with a fresh worker + shell.
    shell2 = _make_shell(bundle, n_planes=8)
    resumed = StackWorker(
        bundle,
        Mock(),
        shell2,
        save_description="focus crash resumed",
        focus_cfg=cfg,
        focus_curve=_curve(),
        start_plane=4,
        resume_manifest=manifest,
    )
    _fake_acquire_frames(resumed, shell2, {})
    resumed.run()

    assert resumed._run_completed is True
    # The residual was restored and continued (flat frames keep growing it
    # by residual_gain_mm at each boundary) — it did not reset to zero.
    assert resumed._focus_controller._residual_mm > pre_crash_residual
    # Block numbering continued: restored count 3, plus boundaries at
    # planes 4 and 6 → 5.
    assert resumed._focus_block_count == 5

    updates2 = _drain_updates(shell2)
    traj_rows = [u.payload for u in updates2 if u.kind == "trajectory"]
    assert [r["block_index"] for r in traj_rows] == [3, 4]
    # The first post-resume checkpoint carries the restored reference
    # sharpness and a non-zero residual.
    cp_rows = [u.payload for u in updates2 if u.kind == "checkpoint"]
    assert cp_rows[0]["controller"] == "focus"
    assert cp_rows[0]["reference_sharpness"] is not None
    assert cp_rows[0]["residual_mm"] > 0.0


def test_autofocus_crash_resume_continues_trajectory(qtbot: QtBot) -> None:
    """A per-plane autofocus stack resumes with the residual and the
    smoothed reference sharpness intact."""
    from lightsheet.gui.workers import StackWorker
    from test.helpers.factories import make_bundle

    bundle = make_bundle()
    shell = _make_shell(bundle, n_planes=6)
    cfg = AutofocusConfig(
        enabled=True, cadence=1, update_threshold=0.0, residual_gain_mm=0.05
    )
    worker = StackWorker(
        bundle,
        Mock(),
        shell,
        save_description="autofocus crash",
        autofocus_cfg=cfg,
    )
    _fake_acquire_frames(worker, shell, {0: "checkerboard", 1: "checkerboard"})

    orig_acquire = worker.acquire_scan
    def _crash_after_three() -> bool:
        ok = orig_acquire()
        if worker._acquire_state["idx"] >= 3:
            shell.stack_mode_started = False
        return ok
    worker.acquire_scan = _crash_after_three  # ty: ignore[invalid-assignment]

    worker.run()
    assert worker._run_completed is False
    pre_crash = worker._autofocus_controller.checkpoint()
    assert pre_crash["predicted_sharpness"] is not None

    manifest = _manifest(n_planes=6)
    for update in _drain_updates(shell):
        manifest = apply_manifest_update(manifest, update)

    shell2 = _make_shell(bundle, n_planes=6)
    resumed = StackWorker(
        bundle,
        Mock(),
        shell2,
        save_description="autofocus crash resumed",
        autofocus_cfg=cfg,
        start_plane=3,
        resume_manifest=manifest,
    )
    _fake_acquire_frames(resumed, shell2, {0: "checkerboard"})
    resumed.run()

    assert resumed._run_completed is True
    updates2 = _drain_updates(shell2)
    traj_rows = [u for u in updates2 if u.kind == "trajectory"]
    # Per-plane autofocus: rows for planes 3, 4, 5 (block_index == plane).
    assert [u.plane_index for u in traj_rows] == [3, 4, 5]
    cp_rows = [u.payload for u in updates2 if u.kind == "checkpoint"]
    # The restored controller's smoothed reference survived the resume —
    # the first post-resume checkpoint already carries a sharpness state.
    assert cp_rows[0]["controller"] == "autofocus"
    assert cp_rows[0]["predicted_sharpness"] is not None


def test_focus_controller_restore_rejects_out_of_range_residual() -> None:
    """The safety-gate fallback: a checkpoint whose residual exceeds the
    configured travel bound is rejected, so a forged or corrupted manifest
    cannot push the camera focus motor past its limits."""
    cfg = FocusConfig(enabled=True, max_residual_mm=0.5)
    ctrl = _focus_controller()
    state = {**ctrl.checkpoint(), "residual_mm": 0.6}
    with pytest.raises(ValueError, match="residual_mm"):
        FocusController(cfg, _curve(), 0.0, 128.0, initial_state=state)

    af_cfg = AutofocusConfig(enabled=True, max_residual_mm=0.5)
    af = _autofocus_controller()
    af_state = {**af.checkpoint(), "residual_mm": -0.7}
    with pytest.raises(ValueError, match="residual_mm"):
        AdaptiveFocusController(af_cfg, 0.0, 128.0, initial_state=af_state)
