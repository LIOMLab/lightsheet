"""Tests for Zarr L0 reopen and deferred finalize on resume."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING

import numpy as np
import pytest
import zarr
from pytestqt.qtbot import QtBot

from lightsheet.resume import ResumeManifest
from lightsheet.resume.probe import ResumeProbeError

if TYPE_CHECKING:
    from lightsheet.gui.shell.controller import Controller_MainWindow


ACQ_UUID = "resume-uuid-123"


def _frame(z: int) -> np.ndarray:
    return np.full((4, 4), z + 1, dtype=np.uint16)


def _partial_store(
    fs: object, controller: Controller_MainWindow, tmp_path: Path, n_written: int, n_planes: int
) -> Path:
    controller.camera.xsize = 4
    controller.camera.ysize = 4
    store_path = tmp_path / "acq.ome.zarr"
    saver = fs._zarr_saver
    saver.start_stack(
        str(store_path),
        n_planes,
        n_channels=1,
        acquisition_uuid=ACQ_UUID,
    )
    for z in range(n_written):
        saver.write_plane(0, z, _frame(z), 0.0, 0.0, 0.0)
    return store_path


def test_fresh_start_stamps_acquisition_uuid(
    qtbot: QtBot, controller: Controller_MainWindow, tmp_path: Path
) -> None:
    fs = controller._fs.frame_saver
    fs.reinit(3)
    controller.save_directory = str(tmp_path)
    store_path = _partial_store(fs, controller, tmp_path, 2, 4)
    root = zarr.open(str(store_path), mode="r")
    assert "acquisition" in root
    assert root["acquisition"].attrs["uuid"] == ACQ_UUID


def test_resume_stack_reopens_and_writes_missing_planes(
    qtbot: QtBot, controller: Controller_MainWindow, tmp_path: Path
) -> None:
    fs = controller._fs.frame_saver
    fs.reinit(3)
    controller.save_directory = str(tmp_path)
    store_path = _partial_store(fs, controller, tmp_path, 2, 4)

    fs.reinit(3)
    saver = fs._zarr_saver
    saver.resume_stack(str(store_path), 4, 1, ACQ_UUID)
    assert saver._resumed
    assert saver.resume_offset(0) == 2

    for z in range(2, 4):
        saver.write_plane(0, z, _frame(z), 0.0, 0.0, 0.0)

    assert not saver._finalized
    saver.finalize()
    assert saver._finalized


def test_resume_stack_rejects_uuid_mismatch(
    qtbot: QtBot, controller: Controller_MainWindow, tmp_path: Path
) -> None:
    fs = controller._fs.frame_saver
    fs.reinit(3)
    controller.save_directory = str(tmp_path)
    store_path = _partial_store(fs, controller, tmp_path, 1, 3)

    fs.reinit(3)
    saver = fs._zarr_saver
    with pytest.raises(ResumeProbeError):
        saver.resume_stack(str(store_path), 3, 1, "different-uuid")


def test_manifest_cursor_matches_observed_zarr_planes(
    qtbot: QtBot, controller: Controller_MainWindow, tmp_path: Path
) -> None:
    # The worker path is unit-tested above; this is the integration hook.
    fs = controller._fs.frame_saver
    fs.reinit(3)
    controller.save_directory = str(tmp_path)
    store_path = _partial_store(fs, controller, tmp_path, 2, 4)

    manifest = ResumeManifest(
        uuid=ACQ_UUID,
        state="in_progress",
        n_planes=4,
        stack_starting_plane=0.0,
        stack_ending_plane=30.0,
        stack_step=10.0,
        save_mode="stitch",
        wavelengths=[555],
        created_at="2026-09-08T00:00:00+00:00",
        cursors={"zarr": {str(store_path): 2}},
    )
    fs.set_files(
        1,
        "acq",
        "stack",
        4,
        "reconstructed_frame",
        wavelengths=[555],
        resume_manifest=manifest,
    )
    # set_files resolves the resume manifest; the actual Zarr L0 reopen is
    # performed by zarr_save_worker when it starts.
    assert fs.resume_manifest is not None
    assert fs.resume_manifest.cursors["zarr"][str(store_path)] == 2


def _adaptive_sample(plane: int) -> object:
    """Minimal adaptive-trajectory sample matching the field names read
    by ``ZarrSaver._write_adaptive_group``."""
    return SimpleNamespace(
        plane_index=plane,
        intensity_fraction=[0.5, 0.5],
        exposure_s=0.01,
        laser_power_mw=[1.0, 2.0],
        control_variable_active="exposure",
        reacquired=False,
        power_fallback=False,
    )


def _focus_sample(block: int) -> object:
    """Minimal focus-trajectory sample matching the field names read
    by ``ZarrSaver._write_focus_group``."""
    return SimpleNamespace(
        block_index=block,
        stage_pos_mm=1.0 + block,
        feedforward_camera_pos_mm=2.0,
        residual_mm=0.01,
        applied_camera_pos_mm=2.01,
        sharpness_metric=None,
    )


def test_resumed_finalize_writes_acquisition_metadata(
    qtbot: QtBot, controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """A resumed Zarr run must still publish ``/acquisition`` metadata
    (motor positions + scan params) and the adaptive/focus trajectory
    groups when it finalizes — only the analysis pyramid build is
    skipped in resume mode."""
    fs = controller._fs.frame_saver
    fs.reinit(3)
    controller.save_directory = str(tmp_path)
    store_path = _partial_store(fs, controller, tmp_path, 2, 4)

    fs.reinit(3)
    saver = fs._zarr_saver
    saver.resume_stack(str(store_path), 4, 1, ACQ_UUID)
    for z in range(2, 4):
        saver.write_plane(0, z, _frame(z), 10.0 + z, 20.0 + z, 30.0 + z)

    saver.set_adaptive_trajectory([_adaptive_sample(z) for z in range(4)], None)
    saver.set_focus_trajectory([_focus_sample(0)], None)
    saver.finalize()
    assert saver._finalized

    root = zarr.open(str(store_path), mode="r")
    assert "acquisition" in root
    acq = root["acquisition"]
    assert acq.attrs["uuid"] == ACQ_UUID
    # Scan params are published as group attrs.
    assert "exposure_time_s" in acq.attrs
    assert "galvo_left_amplitude" in acq.attrs
    # Per-plane motor positions cover the planes streamed by the resumed
    # run (the resumed run only records planes it wrote).
    motor = acq["motor"]
    np.testing.assert_array_equal(
        motor["horizontal"][:], np.array([10.0 + z for z in range(2, 4)])
    )
    np.testing.assert_array_equal(
        motor["vertical"][:], np.array([20.0 + z for z in range(2, 4)])
    )
    np.testing.assert_array_equal(
        motor["camera"][:], np.array([30.0 + z for z in range(2, 4)])
    )

    adaptive = acq["adaptive"]
    np.testing.assert_array_equal(
        adaptive["plane_index"][:], np.array([0, 1, 2, 3])
    )

    focus = acq["focus"]
    np.testing.assert_array_equal(focus["block_index"][:], np.array([0]))


def test_resumed_finalize_without_trajectories_omits_groups(
    qtbot: QtBot, controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """Fixed-mode resume: no adaptive/focus groups, but the acquisition
    group and motor positions are still written."""
    fs = controller._fs.frame_saver
    fs.reinit(3)
    controller.save_directory = str(tmp_path)
    store_path = _partial_store(fs, controller, tmp_path, 1, 2)

    fs.reinit(3)
    saver = fs._zarr_saver
    saver.resume_stack(str(store_path), 2, 1, ACQ_UUID)
    saver.write_plane(0, 1, _frame(1), 1.0, 2.0, 3.0)
    saver.finalize()
    assert saver._finalized

    root = zarr.open(str(store_path), mode="r")
    acq = root["acquisition"]
    assert "motor" in acq
    assert "adaptive" not in acq
    assert "focus" not in acq
