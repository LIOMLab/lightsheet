"""Cursor-durability tests: the manifest cursor is the save-consumer truth.

Uses the ``controller`` fixture (real construction) so the real
``FrameSaver`` runs its ``frame_saver_worker`` loop against a synthetic
frame queue. A simulated crash = the worker exits (or is abandoned)
without ``stop_saving`` ever running a lifecycle update — the manifest
must stay ``in_progress`` and its cursor must equal the number of
datasets actually on disk, never the number of frames enqueued.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import h5py
import numpy as np
import pytest
from pytestqt.qtbot import QtBot

pytest.importorskip("PySide6")

from lightsheet.resume import read_manifest

if TYPE_CHECKING:
    from lightsheet.gui.coordinators.frame_saver_controller import FrameSaver
    from lightsheet.gui.shell.controller import Controller_MainWindow


def _frame(i: int) -> np.ndarray:
    return np.full((4, 4), i, dtype=np.uint16)


def _count_datasets(path: str, prefix: str) -> int:
    with h5py.File(path, "r") as f:
        return sum(1 for k in f if k.startswith(prefix))


def _prepare_stack_saver(
    controller: Controller_MainWindow, tmp_path: Path, n_planes: int = 5
) -> FrameSaver:
    """Point the FrameSaver at tmp_path and mint a stack manifest."""
    controller.save_directory = str(tmp_path)
    controller.saving_allowed = True
    controller.number_of_planes = n_planes
    controller.stack_starting_plane = 0.0
    controller.stack_ending_plane = float(n_planes - 1) * 10.0
    controller.stack_step = 10.0
    fs = controller._fs.frame_saver
    fs.reinit(3)
    fs.set_files(
        1,
        "durability_test",
        "stack",
        n_planes,
        "reconstructed_frame",
        wavelengths=[555],
    )
    return fs


def test_set_files_mints_manifest_and_uuid(
    qtbot: QtBot, controller: Controller_MainWindow, tmp_path: Path
) -> None:
    fs = _prepare_stack_saver(controller, tmp_path)
    assert fs._manifest_path is not None and fs._manifest_path.is_file()
    m = read_manifest(fs._manifest_path)
    assert m is not None
    assert m.state == "in_progress"
    assert m.uuid == fs.acquisition_uuid
    assert m.n_planes == 5
    assert m.wavelengths == [555]


def test_cursor_equals_datasets_on_disk_after_crash(
    qtbot: QtBot, controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """Simulated crash: worker writes 3 of 5 frames, then the process
    'dies' — no stop_saving, no lifecycle update. The manifest cursor
    must equal the 3 datasets on disk and stay ``in_progress``."""
    fs = _prepare_stack_saver(controller, tmp_path, n_planes=5)
    # saving_started is left False: the worker drains the queue on its
    # first timeout and exits via the abort path — the closest mock-path
    # stand-in for dying mid-run.
    fs.saving_started = False
    for i in range(3):
        fs.enqueue_buffer(_frame(i))
    fs.frame_saver_worker()

    hdf5_path = fs.filenames_list[0]
    n_on_disk = _count_datasets(hdf5_path, "reconstructed_frame")
    assert n_on_disk == 3

    m = read_manifest(fs._manifest_path)  # ty: ignore[invalid-argument-type]
    assert m is not None
    assert m.cursors["hdf5"][hdf5_path] == n_on_disk == 3
    # No lifecycle update ran — the crash signature is preserved.
    assert m.state == "in_progress"
    # The output file carries the manifest's UUID.
    with h5py.File(hdf5_path, "r") as f:
        assert f.attrs["Acquisition UUID"] == m.uuid


def test_completed_lifecycle_written_by_stop_saving(
    qtbot: QtBot, controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """Normal completion: all 5 frames written, then stop_saving stages
    the ``completed`` lifecycle update — applied even though the worker
    already exited (post-join finalize)."""
    fs = _prepare_stack_saver(controller, tmp_path, n_planes=5)
    fs.saving_started = True
    for i in range(5):
        fs.enqueue_buffer(_frame(i))
    fs.frame_saver_worker()
    fs.stop_saving(lifecycle="completed")

    m = read_manifest(fs._manifest_path)  # ty: ignore[invalid-argument-type]
    assert m is not None
    assert m.state == "completed"
    assert m.completed_at is not None
    assert m.cursors["hdf5"][fs.filenames_list[0]] == 5
    assert m.last_motor_positions  # staged by stop_saving


def test_interrupted_lifecycle_written_by_stop_saving(
    qtbot: QtBot, controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """Abort path: stop_saving with ``interrupted`` persists the state and
    the cursor reflects only what is on disk."""
    fs = _prepare_stack_saver(controller, tmp_path, n_planes=5)
    fs.saving_started = True
    for i in range(2):
        fs.enqueue_buffer(_frame(i))
    fs.stop_saving(lifecycle="interrupted")
    fs.frame_saver_worker()

    m = read_manifest(fs._manifest_path)  # ty: ignore[invalid-argument-type]
    assert m is not None
    assert m.state == "interrupted"
    assert m.cursors["hdf5"][fs.filenames_list[0]] == 2


def test_no_manifest_for_single_image_save(
    qtbot: QtBot, controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """Single-image saves produce no resumable artifact — set_files with
    a non-stack scan_type must not write a manifest."""
    controller.save_directory = str(tmp_path)
    fs = controller._fs.frame_saver
    fs.reinit(1)
    fs.set_files(
        1,
        "single_img",
        "singleImage",
        1,
        "reconstructed_frame",
        wavelengths=[555],
    )
    assert fs.resume_manifest is None
    assert fs.acquisition_uuid is None
    assert list(tmp_path.glob("*.resume.json")) == []
