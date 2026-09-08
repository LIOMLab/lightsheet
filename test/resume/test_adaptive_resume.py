"""Tests for adaptive-exposure checkpoint/restore and crash/resume.

Covers the controller checkpoint API, manifest update persistence, and
the FrameSaver pre-resume trajectory merge for phase 16-04.
"""

from __future__ import annotations

import uuid as uuid_mod
from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pytest
from pytestqt.qtbot import QtBot

from lightsheet.adaptive.controller import AdaptiveController
from lightsheet.adaptive.types import AdaptiveCommand, AdaptiveConfig, AdaptiveSample
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


def _controller() -> AdaptiveController:
    """Fresh adaptive controller with a small flat pilot trajectory."""
    cfg = AdaptiveConfig(enabled=True)
    ctrl = AdaptiveController(cfg, 10)
    ctrl.prime([0, 1, 2, 3, 4], [0.01, 0.01, 0.01, 0.01, 0.01])
    return ctrl


def test_adaptive_controller_checkpoint_roundtrip() -> None:
    """A checkpoint captures and restores PI state and the last command."""
    ctrl = _controller()
    # Drive the controller through two planes and capture its state.
    c1 = ctrl.update([0.90], 0, 0.01, (10.0, 0.0), 0)
    c2 = ctrl.update([0.94], 0, c1.exposure_s, (c1.laser1_mw, c1.laser2_mw), 1)
    state = ctrl.checkpoint()

    restored = AdaptiveController(AdaptiveConfig(enabled=True), 10, initial_state=state)
    assert restored._integral == pytest.approx(ctrl._integral)
    assert restored._reacquire_count == ctrl._reacquire_count
    assert restored._last_command is not None
    assert restored._last_command == c2

    # The restored controller must be able to continue the trajectory
    # exactly as the original would for the next plane.
    c3_restored = restored.update(
        [0.88], 0, c2.exposure_s, (c2.laser1_mw, c2.laser2_mw), 2
    )
    original = _controller()
    o1 = original.update([0.90], 0, 0.01, (10.0, 0.0), 0)
    o2 = original.update([0.94], 0, o1.exposure_s, (o1.laser1_mw, o1.laser2_mw), 1)
    c3_original = original.update(
        [0.88], 0, o2.exposure_s, (o2.laser1_mw, o2.laser2_mw), 2
    )
    assert c3_restored == c3_original


def test_adaptive_controller_restore_rejects_invalid_state() -> None:
    """restore() validates the checkpoint before mutating internal state."""
    ctrl = _controller()
    c1 = ctrl.update([0.90], 0, 0.01, (10.0, 0.0), 0)
    base = ctrl.checkpoint()
    assert base["last_command"] is not None

    with pytest.raises(ValueError, match="integral"):
        AdaptiveController(AdaptiveConfig(enabled=True), 10, initial_state={**base, "integral": "x"})

    with pytest.raises(ValueError, match="reacquire_count"):
        AdaptiveController(AdaptiveConfig(enabled=True), 10, initial_state={**base, "reacquire_count": -1})

    last = base["last_command"]
    assert last is not None
    with pytest.raises(ValueError, match="exposure_s"):
        AdaptiveController(
            AdaptiveConfig(enabled=True),
            10,
            initial_state={
                **base,
                "last_command": {**last, "exposure_s": 999.0},
            },
        )

    with pytest.raises(ValueError, match="laser"):
        AdaptiveController(
            AdaptiveConfig(enabled=True),
            10,
            initial_state={
                **base,
                "last_command": {**last, "laser1_mw": float("nan")},
            },
        )


def test_adaptive_sample_as_dict_is_manifest_safe() -> None:
    """AdaptiveSample.as_dict yields JSON-safe values."""
    sample = AdaptiveSample(
        plane_index=3,
        intensity_fraction=[0.5, None],
        exposure_s=0.02,
        laser_power_mw=(10.0, 20.0),
        control_variable_active="exposure",
        reacquired=False,
        power_fallback=False,
    )
    d = sample.as_dict()
    assert d["laser_power_mw"] == [10.0, 20.0]
    assert d["intensity_fraction"] == [0.5, pytest.approx(float("nan"), nan_ok=True)]
    assert d["reacquired"] is False


def test_manifest_stores_adaptive_checkpoint_and_trajectory() -> None:
    """apply_manifest_update appends controller checkpoints and trajectory rows."""
    m = _manifest()
    cp = {
        "integral": 0.1,
        "reacquire_count": 0,
        "pilot": None,
        "last_command": None,
    }
    traj = {
        "plane_index": 2,
        "intensity_fraction": [0.5],
        "exposure_s": 0.02,
        "laser_power_mw": [10.0, 20.0],
        "control_variable_active": "exposure",
        "reacquired": False,
        "power_fallback": False,
    }
    m = apply_manifest_update(
        m, ManifestUpdate(kind="checkpoint", payload=cp, plane_index=2)
    )
    m = apply_manifest_update(
        m, ManifestUpdate(kind="trajectory", payload=traj, plane_index=2)
    )
    assert len(m.controller_checkpoints) == 1
    assert m.controller_checkpoints[0]["plane_index"] == 2
    assert len(m.trajectory_samples) == 1
    assert m.trajectory_samples[0]["plane_index"] == 2


def test_frame_saver_merges_pre_resume_adaptive_trajectory(
    qtbot: QtBot, controller: object, tmp_path: Path
) -> None:
    """Resumed FrameSaver prepends manifest trajectory samples before recording new ones."""
    ctrl = controller
    ctrl.save_directory = str(tmp_path)
    ctrl.save_format = "hdf5"
    fs = ctrl._fs
    fs.reinit(1)

    pre_sample = AdaptiveSample(
        plane_index=0,
        intensity_fraction=[0.6],
        exposure_s=0.01,
        laser_power_mw=(10.0, 0.0),
        control_variable_active="exposure",
        reacquired=False,
        power_fallback=False,
    )
    fs.frame_saver.resume_manifest = _manifest(
        n_planes=4,
        trajectory_samples=[pre_sample.as_dict()],
        controller_checkpoints=[
            {
                "integral": 0.0,
                "reacquire_count": 0,
                "pilot": None,
                "last_command": None,
            }
        ],
    )

    fs.configure_adaptive(True, config=AdaptiveConfig(enabled=True))
    assert len(fs.frame_saver.adaptive_trajectory) == 1
    assert fs.frame_saver.adaptive_trajectory[0].plane_index == 0

    new_sample = AdaptiveSample(
        plane_index=1,
        intensity_fraction=[0.7],
        exposure_s=0.02,
        laser_power_mw=(11.0, 0.0),
        control_variable_active="exposure",
        reacquired=False,
        power_fallback=False,
    )
    fs.record_adaptive_sample(new_sample)
    assert len(fs.frame_saver.adaptive_trajectory) == 2
    assert [s.plane_index for s in fs.frame_saver.adaptive_trajectory] == [0, 1]


def test_frame_saver_skips_malformed_pre_resume_trajectory(
    qtbot: QtBot, controller: object, tmp_path: Path
) -> None:
    """Malformed pre-resume trajectory rows are skipped with a warning."""
    ctrl = controller
    ctrl.save_directory = str(tmp_path)
    ctrl.save_format = "hdf5"
    fs = ctrl._fs
    fs.reinit(1)

    resume_manifest = _manifest(
        n_planes=2,
        trajectory_samples=[{"bogus": "row"}],
    )
    fs.frame_saver.resume_manifest = resume_manifest

    fs.configure_adaptive(True, config=AdaptiveConfig(enabled=True))
    assert fs.frame_saver.adaptive_trajectory == []


def test_stack_worker_stages_adaptive_manifest_updates() -> None:
    """_record_adaptive_step stages checkpoint and trajectory manifest updates."""
    from lightsheet.gui.workers import StackWorker
    from test.helpers.factories import make_bundle

    bundle = make_bundle()
    shell = Mock()
    shell.lasers = bundle.lasers
    shell.lasers[0].max_power = 100.0
    shell.lasers[1].max_power = 100.0
    shell.saving_allowed = True
    shell.reconstructed_frame = np.full((4, 4), 1000, dtype=np.uint16)
    shell.reconstructed_frames = {}
    shell._fs = Mock()
    shell._fs.manifest_update_queue = Mock()
    shell.sig_message = Mock()

    worker = StackWorker(
        bundle,
        Mock(),
        shell,
        save_description="adaptive staging",
        multi_channel=False,
    )
    worker._adaptive_cfg = AdaptiveConfig(enabled=True)
    worker._adaptive_controller = _controller()
    worker._adaptive_current_cmd = AdaptiveCommand.fixed(
        exposure_s=0.01,
        laser1_mw=10.0,
        laser2_mw=0.0,
    )
    worker._multi_channel = False
    worker._record_adaptive_step(0)

    assert shell._fs.record_adaptive_sample.called
    assert shell._fs.manifest_update_queue.put_nowait.call_count == 2
    kinds = [
        shell._fs.manifest_update_queue.put_nowait.call_args_list[i].args[0].kind
        for i in range(2)
    ]
    assert set(kinds) == {"checkpoint", "trajectory"}
