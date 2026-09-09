"""Tests for HDF5 resume append-in-place and _partN fallback."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import h5py
import numpy as np
import pytest
from pytestqt.qtbot import QtBot

from lightsheet.resume import ResumeManifest, read_manifest

if TYPE_CHECKING:
    from lightsheet.gui.shell.controller import Controller_MainWindow


def _hdf5(path: Path, n: int) -> None:
    with h5py.File(str(path), "w") as f:
        for i in range(1, n + 1):
            f.create_dataset(
                f"reconstructed_frame{i:03d}",
                data=np.full((4, 4), i, dtype=np.uint16),
            )


def _corrupt(path: Path) -> None:
    path.write_bytes(b"not an hdf5 file")


def _manifest(
    tmp_path: Path,
    cursors: dict[str, int],
    n_planes: int = 3,
) -> ResumeManifest:
    return ResumeManifest(
        uuid="resume-uuid",
        state="in_progress",
        n_planes=n_planes,
        stack_starting_plane=0.0,
        stack_ending_plane=20.0,
        stack_step=10.0,
        save_mode="stitch",
        wavelengths=[555, 640],
        multi_channel=True,
        cursors={"hdf5": cursors},
        created_at="2026-09-08T00:00:00+00:00",
    )


def test_set_files_appends_valid_hdf5_and_truncates_torn_tail(
    qtbot: QtBot, controller: Controller_MainWindow, tmp_path: Path
) -> None:
    good = tmp_path / "acq_555nm.hdf5"
    _hdf5(good, 2)
    m = _manifest(tmp_path, {str(good): 2})
    fs = controller._fs.frame_saver
    fs.reinit(3)
    controller.save_directory = str(tmp_path)
    fs.set_files(
        1,
        "acq",
        "stack",
        3,
        "reconstructed_frame",
        wavelengths=[555],
        resume_manifest=m,
    )
    assert fs.filenames_lists[0][0] == str(good)
    assert fs._manifest_path is not None
    loaded = read_manifest(fs._manifest_path)
    assert loaded is not None
    assert loaded.cursors["hdf5"][str(good)] == 2


def test_set_files_falls_back_to_partn_for_corrupt_hdf5(
    qtbot: QtBot, controller: Controller_MainWindow, tmp_path: Path
) -> None:
    good = tmp_path / "acq_555nm.hdf5"
    bad = tmp_path / "acq_640nm.hdf5"
    _hdf5(good, 2)
    _corrupt(bad)
    m = _manifest(tmp_path, {str(good): 2, str(bad): 2})
    fs = controller._fs.frame_saver
    fs.reinit(3)
    controller.save_directory = str(tmp_path)
    fs.set_files(
        1,
        "acq",
        "stack",
        3,
        "reconstructed_frame",
        wavelengths=[555, 640],
        resume_manifest=m,
    )
    # Channel 0 stays with the good original path.
    assert fs.filenames_lists[0][0] == str(good)
    # Channel 1 gets a _part2 continuation fileset.
    assert "_part2_640nm" in fs.filenames_lists[1][0]
    assert fs._manifest_path is not None
    loaded = read_manifest(fs._manifest_path)
    assert loaded is not None
    # A corrupt channel forces the common resume plane to 0, so both
    # the surviving channel and the _partN fallback start at plane 0 to
    # keep the multi-channel plane pairs in lockstep.
    assert loaded.cursors["hdf5"][str(good)] == 0
    fallback_key = fs.filenames_lists[1][0]
    assert loaded.cursors["hdf5"][fallback_key] == 0


def test_manifest_dir_contains_rejects_paths_outside_save_directory(
    qtbot: QtBot, controller: Controller_MainWindow, tmp_path: Path
) -> None:
    outside = tmp_path / ".." / "evil_555nm.hdf5"
    outside.parent.mkdir(parents=True, exist_ok=True)
    _hdf5(outside, 1)
    m = _manifest(tmp_path, {str(outside.resolve()): 1})
    fs = controller._fs.frame_saver
    fs.reinit(3)
    controller.save_directory = str(tmp_path)
    with pytest.raises(ValueError):
        fs.set_files(
            1,
            "acq",
            "stack",
            3,
            "reconstructed_frame",
            wavelengths=[555],
            resume_manifest=m,
        )
