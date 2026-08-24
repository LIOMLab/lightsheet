"""FrameSaverController branch-coverage closure.

Exercises the FrameViewer None-rows/columns branches, the
updateUi_refresh_view queue.Empty + success branches, the FrameSaver.reinit
saving_started-True branch, the _write_laser_metadata per-laser attr writes,
the frame_saver_worker happy-path (file create + dataset write + close),
and the reconstruct_frame / reconstruct_frame_linear_blend multi-tile
branches (first/middle/last frame).

Behavior tests (AGENTS.md §5) — every assertion is on a runtime
postcondition (file exists, dataset attrs, returned array shape), never a
static-source grep.
"""

from __future__ import annotations

import os
import queue
import threading
from unittest.mock import Mock

import h5py
import numpy as np
import pytest
from PyQt5.QtCore import QObject

pytest.importorskip("PyQt5")

from lightsheet.gui.frame_saver_controller import FrameSaver, FrameViewer, FrameSaverController
from lightsheet.hal import DeviceBundle, MockCamera, MockETLs, MockLaser, MockMotors, MockSigGen


class _ShellStandin(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.message_printer_calls: list[str] = []
        self.sig_message = Mock()
        self.ui = Mock()
        self.save_format = "hdf5"
        self.lasers = [
            MockLaser(wavelength=555, max_power_mw=300.0, label="L1"),
            MockLaser(wavelength=640, max_power_mw=150.0, label="L2"),
        ]

    def updateUi_message_printer(self, message: str) -> None:
        self.message_printer_calls.append(message)


def _make_bundle() -> DeviceBundle:
    camera = MockCamera(verbose=False)
    siggen = MockSigGen(camera)
    motors = MockMotors()
    lasers = (
        MockLaser(wavelength=555, max_power_mw=300.0, label="L1"),
        MockLaser(wavelength=640, max_power_mw=150.0, label="L2"),
    )
    etls = MockETLs()
    return DeviceBundle(camera=camera, siggen=siggen, motors=motors, etls=etls, lasers=lasers)


def _make_fs() -> tuple[FrameSaverController, _ShellStandin]:
    bundle = _make_bundle()
    shell = _ShellStandin()
    fs = FrameSaverController(bundle, shell)
    return fs, shell


# -- FrameViewer None rows/columns branches ---------------------------------


def test_frame_viewer_none_rows_falls_back_to_2000() -> None:
    """FrameViewer with rows=None falls back to 2000 (the else branch)."""
    shell = _ShellStandin()
    fv = FrameViewer(shell, rows=None, columns=10)
    assert fv.rows == 2000


def test_frame_viewer_none_columns_falls_back_to_2000() -> None:
    """FrameViewer with columns=None falls back to 2000 (the else branch)."""
    shell = _ShellStandin()
    fv = FrameViewer(shell, rows=10, columns=None)
    assert fv.columns == 2000


# -- FrameViewer enqueue_frame queue.Full suppress + refresh_view ------------


def test_frame_viewer_enqueue_frame_suppresses_queue_full() -> None:
    """When the queue is full, enqueue_frame suppresses queue.Full (no raise)."""
    shell = _ShellStandin()
    fv = FrameViewer(shell, rows=4, columns=4)
    # Fill the queue (maxsize=3).
    for i in range(3):
        fv.enqueue_frame(np.zeros((4, 4), dtype=np.uint16))
    # Fourth put must not raise — queue.Full is suppressed.
    fv.enqueue_frame(np.zeros((4, 4), dtype=np.uint16))


def test_frame_viewer_refresh_view_empty_queue_is_noop() -> None:
    """updateUi_refresh_view with an empty queue is a no-op (queue.Empty branch)."""
    shell = _ShellStandin()
    fv = FrameViewer(shell, rows=4, columns=4)
    # Queue is empty — must not raise.
    fv.updateUi_refresh_view()


def test_frame_viewer_refresh_view_with_frame_sets_image() -> None:
    """updateUi_refresh_view with a frame in the queue transposes + sets image."""
    shell = _ShellStandin()
    fv = FrameViewer(shell, rows=4, columns=4)
    frame = np.ones((4, 4), dtype=np.uint16)
    fv.enqueue_frame(frame)
    fv.updateUi_refresh_view()
    # imageView.setImage was called (Mock on shell.ui.imageView).
    shell.ui.imageView.setImage.assert_called()


# -- FrameSaver.reinit saving_started-True branch ----------------------------


def test_frame_saver_reinit_resets_saving_started_when_true() -> None:
    """reinit with saving_started=True flips it to False first (the if-branch)."""
    shell = _ShellStandin()
    saver = FrameSaver(shell)
    saver.saving_started = True
    saver.reinit(5)
    assert saver.saving_started is False
    assert saver.block_size == 5


def test_frame_saver_reinit_when_not_saving_is_direct() -> None:
    """reinit with saving_started=False skips the if-branch (the else-path)."""
    shell = _ShellStandin()
    saver = FrameSaver(shell)
    saver.saving_started = False
    saver.reinit(2)
    assert saver.block_size == 2


# -- FrameSaver.add_sample_name + add_motor_parameters ----------------------


def test_frame_saver_add_sample_name_sets_attribute() -> None:
    shell = _ShellStandin()
    saver = FrameSaver(shell)
    saver.add_sample_name("my_sample")
    assert saver.sample_name == "my_sample"


def test_frame_saver_add_motor_parameters_appends_to_lists() -> None:
    shell = _ShellStandin()
    saver = FrameSaver(shell)
    saver.add_motor_parameters("1.0mm", "2.0mm", "3.0mm")
    assert saver.horizontal_positions_list == ["1.0mm"]
    assert saver.vertical_positions_list == ["2.0mm"]
    assert saver.camera_positions_list == ["3.0mm"]


# -- FrameSaver.start_saving + _write_laser_metadata ------------------------


def test_frame_saver_start_saving_starts_thread() -> None:
    shell = _ShellStandin()
    saver = FrameSaver(shell)
    saver.filenames_list = []  # empty so worker exits immediately
    saver.start_saving()
    assert saver.saving_started is True
    assert hasattr(saver, "frame_saver_thread")
    # Wait for the thread to finish (empty filenames_list -> immediate exit).
    saver.frame_saver_thread.join(timeout=2.0)
    saver.stop_saving()


def test_frame_saver_write_laser_metadata_writes_per_laser_attrs(tmp_path) -> None:
    """_write_laser_metadata writes Laser{i+1} attrs for each laser on the shell."""
    shell = _ShellStandin()
    saver = FrameSaver(shell)
    filepath = str(tmp_path / "test_laser_meta.hdf5")
    with h5py.File(filepath, "w") as outfile:
        saver._write_laser_metadata(outfile)
        # Two lasers on the shell -> Laser1 + Laser2 attrs.
        assert "Laser1 Wavelength" in outfile.attrs
        assert "Laser2 Wavelength" in outfile.attrs
        assert outfile.attrs["Laser1 Wavelength"] == 555
        assert outfile.attrs["Laser2 Wavelength"] == 640


# -- FrameSaver.frame_saver_worker happy path --------------------------------


def test_frame_saver_worker_writes_dataset_and_emits_saved_message(tmp_path) -> None:
    """The happy path: frame_saver_worker creates a file, writes a dataset,
    closes the file, and emits a 'File ... saved' message."""
    shell = _ShellStandin()
    saver = FrameSaver(shell)
    filepath = str(tmp_path / "plane_00001.hdf5")
    saver.filenames_list = [filepath]
    saver.number_of_datasets = 1
    saver.datasets_name = "dataset_"
    saver.sample_name = "test_sample"
    saver.horizontal_positions_list = ["1.0mm"]
    saver.vertical_positions_list = ["2.0mm"]
    saver.camera_positions_list = ["3.0mm"]
    saver.saving_started = True

    # Enqueue a 2D buffer (will be expanded to 3D by the worker).
    frame = np.ones((4, 4), dtype=np.uint16)
    saver.enqueue_buffer(frame)

    saver.frame_saver_worker()

    # File was created and contains the dataset.
    assert os.path.isfile(filepath), "frame_saver_worker must create the file"
    with h5py.File(filepath, "r") as f:
        assert "dataset_001" in f, "dataset_001 must exist in the saved file"
        assert f["dataset_001"].attrs["Sample Name"] == "test_sample"
        assert f["dataset_001"].attrs["Horizontal Position"] == "1.0mm"

    # A 'File ... saved' message was emitted.
    saved_msgs = [m for m in shell.message_printer_calls if "saved" in m]
    assert saved_msgs, "frame_saver_worker must emit a 'File ... saved' message"


def test_frame_saver_worker_3d_buffer_uses_idx_for_pos_index(tmp_path) -> None:
    """When buffer.ndim == 3 (multiple frames), pos_index uses idx (not dataset+idx)."""
    shell = _ShellStandin()
    saver = FrameSaver(shell)
    filepath = str(tmp_path / "plane_00001.hdf5")
    saver.filenames_list = [filepath]
    saver.number_of_datasets = 1
    saver.datasets_name = "dataset_"
    saver.sample_name = "test"
    saver.horizontal_positions_list = ["H0"]
    saver.vertical_positions_list = ["V0"]
    saver.camera_positions_list = ["C0"]
    saver.saving_started = True

    # Enqueue a 3D buffer (2 frames).
    buf = np.ones((2, 4, 4), dtype=np.uint16)
    saver.enqueue_buffer(buf)

    saver.frame_saver_worker()

    with h5py.File(filepath, "r") as f:
        assert "dataset_001" in f
        assert "dataset_002" in f


def test_frame_saver_worker_timeout_exits_inner_loop(tmp_path) -> None:
    """When the queue is empty and saving_started is False, the inner loop
    breaks on queue.Empty + the not-saving_started check (line 294-295)."""
    shell = _ShellStandin()
    saver = FrameSaver(shell)
    filepath = str(tmp_path / "plane_00001.hdf5")
    saver.filenames_list = [filepath]
    saver.number_of_datasets = 1
    saver.datasets_name = "dataset_"
    saver.sample_name = "test"
    saver.horizontal_positions_list = ["H0"]
    saver.vertical_positions_list = ["V0"]
    saver.camera_positions_list = ["C0"]
    saver.saving_started = True

    # Don't enqueue anything — the worker will time out on queue.get.
    # Run in a thread so we can flip saving_started after a moment.
    t = threading.Thread(target=saver.frame_saver_worker, daemon=True)
    t.start()
    # Give the worker time to enter the queue.get(timeout=1) call, then
    # flip saving_started to False so the Empty handler breaks.
    import time
    time.sleep(0.1)
    saver.saving_started = False
    t.join(timeout=5.0)
    assert not t.is_alive(), "worker must exit after saving_started=False"


# -- crop_buffer / reconstruct_frame / reconstruct_frame_linear_blend --------


def test_crop_buffer_single_tile_returns_buffer_unchanged() -> None:
    """crop_buffer with tile_count=1 returns the buffer as-is (the if-branch)."""
    shell = _ShellStandin()
    fs, _ = _make_fs()
    buf = np.ones((1, 4, 8), dtype=np.uint16)
    result = fs.crop_buffer(buf)
    assert result is buf


def test_crop_buffer_multi_tile_crops_with_overlap() -> None:
    """crop_buffer with tile_count>1 crops each frame with 20% overlap.
    Buffer must be large enough that tile_width * 0.2 >= 1."""
    fs, _ = _make_fs()
    # 4 tiles, image_xsize=40 -> tile_width=10, overlap=2
    buf = np.ones((4, 4, 40), dtype=np.uint16)
    result = fs.crop_buffer(buf)
    assert result.shape[0] == 4  # 4 tiles


def test_reconstruct_frame_single_tile_returns_first_frame() -> None:
    """reconstruct_frame with tile_count=1 returns buffer[0, :, :] (the if-branch)."""
    fs, _ = _make_fs()
    buf = np.ones((1, 4, 8), dtype=np.uint16) * 42
    result = fs.reconstruct_frame(buf)
    assert result.shape == (4, 8)
    assert (result == 42).all()


def test_reconstruct_frame_multi_tile_merges_tiles() -> None:
    """reconstruct_frame with tile_count>1 merges tiles side by side."""
    fs, _ = _make_fs()
    buf = np.ones((4, 4, 16), dtype=np.uint16)
    result = fs.reconstruct_frame(buf)
    assert result.shape == (4, 16)


def test_reconstruct_frame_linear_blend_single_tile() -> None:
    """reconstruct_frame_linear_blend with tile_count=1 returns buffer[0]."""
    fs, _ = _make_fs()
    buf = np.ones((1, 4, 8), dtype=np.uint16) * 7
    result = fs.reconstruct_frame_linear_blend(buf)
    assert result.shape == (4, 8)
    assert (result == 7).all()


def test_reconstruct_frame_linear_blend_multi_tile() -> None:
    """reconstruct_frame_linear_blend with tile_count>1 blends overlapping regions.
    Buffer must be large enough that tile_width * 0.2 >= 1 (overlap > 0)."""
    fs, _ = _make_fs()
    # 4 tiles, image_xsize=40 -> tile_width=10, overlap=2
    buf = np.ones((4, 4, 40), dtype=np.uint16)
    result = fs.reconstruct_frame_linear_blend(buf)
    assert result.shape == (4, 40)


def test_reconstruct_frame_linear_blend_three_tiles() -> None:
    """3 tiles exercises the middle-frame branch (neither first nor last).
    image_xsize=30 -> tile_width=10, overlap=2."""
    fs, _ = _make_fs()
    buf = np.ones((3, 4, 30), dtype=np.uint16)
    result = fs.reconstruct_frame_linear_blend(buf)
    assert result.shape == (4, 30)
