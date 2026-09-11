"""Regression test: single-channel ``both`` save resumes the Zarr half.

A torn ``both`` acquisition must reopen the existing OME-Zarr store at
the common resume plane (``resume_stack``), not call ``start_stack`` —
whose merge check would append the resumed planes as a NEW channel and
diverge the store from the resumed HDF5 fileset and the manifest
cursors. The HDF5 half must likewise split the common resume plane into
(file index, dataset counter) so appended datasets continue the torn
file's numbering instead of colliding with existing names.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import TYPE_CHECKING, Any

import h5py
import numpy as np
import zarr
from pytestqt.qtbot import QtBot

if TYPE_CHECKING:
    from lightsheet.gui.coordinators.frame_saver_controller import FrameSaver
    from lightsheet.gui.shell.controller import Controller_MainWindow


class _StopAfterN:
    """Queue wrapper that flips ``saving_started`` after N consumed
    frames — simulates the acquisition stopping mid-stack so the save
    loop drains and exits instead of polling forever."""

    def __init__(self, real: Any, saver: FrameSaver, n: int) -> None:
        self._real = real
        self._saver = saver
        self._n = 0
        self._stop_after = n

    def get(self, block: bool = True, timeout: Any | None = None) -> Any:
        buf = self._real.get(block=block, timeout=timeout)
        self._n += 1
        if self._n >= self._stop_after:
            self._saver.saving_started = False
        return buf

    def get_nowait(self) -> Any:
        return self._real.get_nowait()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


def _zarr_array(node: object) -> zarr.Array[Any]:
    assert isinstance(node, zarr.Array)
    return node


def test_both_save_worker_resume_appends_in_lockstep(
    qtbot: QtBot, controller: Controller_MainWindow, tmp_path: Path
) -> None:
    ctrl = controller
    ctrl.save_directory = str(tmp_path)
    ctrl.save_filepath = str(tmp_path / "acq")
    ctrl.camera.xsize = 4
    ctrl.camera.ysize = 4

    fs = ctrl._fs.frame_saver
    fs.reinit(8)
    fs.set_files(
        1,
        "acq",
        "stack",
        4,
        "reconstructed_frame",
        wavelengths=[555],
    )

    # Partial run: 2 of 4 planes are consumed, then the producer stops
    # (the crash leaves the manifest cursors at 2 for both formats).
    fs.horizontal_positions_list = ["0.0", "1.0"]
    fs.vertical_positions_list = ["0.0", "1.0"]
    fs.camera_positions_list = ["0.0", "1.0"]
    fs.saving_started = True
    for i in range(2):
        fs.enqueue_buffer(np.full((4, 4), i + 1, dtype=np.uint16))
    fs.queue = _StopAfterN(fs.queue, fs, 2)  # ty: ignore[assignment]
    fs.both_save_worker()

    h5_path = fs.filenames_list[0]
    store_path = str(tmp_path / "acq.ome.zarr")
    with h5py.File(h5_path, "r") as f:
        torn = sorted(k for k in f if k.startswith("reconstructed_frame"))
    assert torn == ["reconstructed_frame001", "reconstructed_frame002"]
    assert fs.resume_manifest is not None
    assert fs.resume_manifest.cursors["hdf5"][h5_path] == 2
    assert fs.resume_manifest.cursors["zarr"][store_path] == 2

    # Resume: reinit + set_files against the interrupted manifest, then
    # run the remaining 2 planes through the same loop. (reinit clears
    # resume_manifest — capture the interrupted copy first.)
    interrupted = dataclasses.replace(fs.resume_manifest, state="interrupted")
    fs.reinit(8)
    fs.set_files(
        1,
        "acq",
        "stack",
        4,
        "reconstructed_frame",
        wavelengths=[555],
        resume_manifest=interrupted,
    )
    assert fs._common_resume_plane == 2
    fs.horizontal_positions_list = ["2.0", "3.0"]
    fs.vertical_positions_list = ["2.0", "3.0"]
    fs.camera_positions_list = ["2.0", "3.0"]
    fs.saving_started = True
    for i in range(2, 4):
        fs.enqueue_buffer(np.full((4, 4), i + 1, dtype=np.uint16))
    fs.queue = _StopAfterN(fs.queue, fs, 2)  # ty: ignore[assignment]
    fs.both_save_worker()

    assert fs.saving_started is False

    # HDF5 half: the torn file gained datasets 003/004 (no name
    # collision, no rewrite of 001/002).
    with h5py.File(h5_path, "r") as f:
        names = sorted(k for k in f if k.startswith("reconstructed_frame"))
        assert names == [f"reconstructed_frame{i:03d}" for i in range(1, 5)]
        for i, name in enumerate(names, start=1):
            assert int(np.asarray(f[name])[0, 0]) == i

    # Zarr half: the store kept ONE channel (resume, not merge) and the
    # resumed planes landed in channel 0 slots 2 and 3.
    root = zarr.open(store_path, mode="r")
    arr = _zarr_array(root["0"])
    assert arr.shape[0] == 1
    assert arr.shape[1] == 4
    assert [int(arr[0, z, 0, 0]) for z in range(4)] == [1, 2, 3, 4]

    # Manifest cursors advanced to 4 for both formats.
    assert fs.resume_manifest is not None
    assert fs.resume_manifest.cursors["hdf5"][h5_path] == 4
    assert fs.resume_manifest.cursors["zarr"][store_path] == 4
