"""Integration test: StackWorker multi-channel save path exercises the
REAL FrameSaverController (no _fs mock) end-to-end.

The StackWorker multi-channel tests previously mocked _fs
(FrameSaverController), so the real set_files / save workers never saw
the channel-tagged (channel_idx, frame) tuples — the integration gap
that let the Critical bugs ship (set_files called without wavelengths,
Zarr writer sized to n_channels=1, natural-completion break dropping
the last channel-1 frame).

This test constructs a real Controller_MainWindow via make_controller
(real FrameSaverController / HardwareManager / AcquisitionCoordinator /
MotorController wired), sets both auto-laser checkboxes (multi-channel
mode), configures a valid 2-plane stack plan, and runs StackWorker.run()
against the REAL _fs. The hardware-touching methods that would block or
move real hardware (acquire_scan, the motor move) are stubbed; lasers
are MockLaser instances (safe to energize/de-energize). The save worker
thread really runs, really writes HDF5 files to tmp_path, and really
joins on stop_saving.

Asserts:
  - ctrl._fs.frame_saver.filenames_lists is populated (2 channels x 2
    planes) — verifies set_files was called with wavelengths (the CR-01
    fix).
  - The filenames carry the correct per-channel wavelength suffixes
    (_555nm / _647nm) read from the live ILaser instances.
  - The HDF5 files were actually written to disk by the real save
    worker (the integration gap is closed: the tagged tuples reached
    the real _frame_saver_worker_multi_channel consumer).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import numpy as np
import pytest
from pytestqt.qtbot import QtBot

if TYPE_CHECKING:
    from lightsheet.gui.shell.controller import Controller_MainWindow

pytest.importorskip("PySide6")


def test_stack_worker_multi_channel_real_fs_writes_per_channel_files(
    qtbot: QtBot, controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """StackWorker.run in multi-channel mode calls set_files with
    wavelengths and the real save worker writes one HDF5 file per
    channel per plane."""

    from lightsheet.gui.workers import StackWorker

    ctrl = controller

    # Multi-channel mode: both auto-laser checkboxes checked.
    ctrl._auto_laser1 = True
    ctrl._auto_laser2 = True

    # Valid 2-plane stack plan.
    ctrl.saving_allowed = True
    ctrl.number_of_planes = 2
    ctrl.stack_mode_started = True
    ctrl.stack_starting_plane = 0.0
    ctrl.stack_step = 10.0
    ctrl.save_format = "hdf5"
    ctrl.save_directory = str(tmp_path)
    ctrl.save_filepath = str(tmp_path / "test")
    ctrl.save_description = "integration test sample"
    # Position text attrs read by add_motor_parameters.
    ctrl.current_horizontal_position_text = "0.0"
    ctrl.current_vertical_position_text = "0.0"
    ctrl.current_camera_position_text = "0.0"

    # Crop save path: one HDF5 file per plane per channel
    # (set_files(number_of_planes, ..., 1, "ETLscan") builds
    # number_of_files=2 entries per channel in filenames_lists).
    ctrl.save_panel.ui.radioButton_saveAllCrop.setChecked(True)
    ctrl.save_panel.ui.radioButton_saveAllFull.setChecked(False)

    # Wavelengths come from the live ILaser instances — never hardcoded.
    wl1 = int(ctrl.lasers[0].wavelength)
    wl2 = int(ctrl.lasers[1].wavelength)

    # Construct the StackWorker exactly as _spawn_stack_worker does.
    worker = StackWorker(
        ctrl._bundle,
        ctrl._hw,
        ctrl,
        save_description="integration test sample",
        save_stitch_blend=False,
        save_all_crop=True,
        save_all_full=False,
        multi_channel=True,
    )

    # Stub acquire_scan so we don't run the full camera+siggen scan
    # logic — just set reconstructed_frame to a small frame so the
    # multi-channel capture+enqueue path runs. The real _fs receives
    # the tagged tuples.
    def _fake_acquire_scan() -> bool:
        ctrl.reconstructed_frame = np.zeros((4, 4), dtype=np.uint16)
        return True

    worker.acquire_scan = _fake_acquire_scan  # type: ignore[method-assign]  # ty: ignore[invalid-assignment]
    worker.camera.recorder_timeout_status = False
    worker.siggen.error = 0

    # Stub the motor move so MockMotors travel-limit enforcement does
    # not abort the stack (the mock enforces limits; a 10um step from 0
    # is fine but stubbing keeps the test independent of mock limits).
    with patch.object(worker.motors.horizontal, "move_absolute_position"):
        finished_emits: list[None] = []
        worker.finished.connect(lambda: finished_emits.append(None))
        worker.run()

    # The worker must have emitted finished exactly once.
    assert len(finished_emits) == 1, (
        f"StackWorker.run must emit finished exactly once; got {len(finished_emits)}"
    )

    # CR-01 verification: set_files was called with wavelengths, so
    # filenames_lists is populated (2 channels x 2 planes).
    fs = ctrl._fs.frame_saver
    assert isinstance(fs.filenames_lists, list), (
        "filenames_lists must be a list of lists in multi-channel mode"
    )
    assert len(fs.filenames_lists) == 2, (
        f"filenames_lists must have one list per channel (2); "
        f"got {len(fs.filenames_lists)}"
    )
    for ch in range(2):
        assert len(fs.filenames_lists[ch]) == 2, (
            f"channel {ch} must have 2 plane entries; got {len(fs.filenames_lists[ch])}"
        )

    # The filenames must carry the per-channel wavelength suffix read
    # from the live ILaser instances.
    assert f"_{wl1}nm" in fs.filenames_lists[0][0], (
        f"channel 0 filename must carry _{wl1}nm suffix; got {fs.filenames_lists[0][0]}"
    )
    assert f"_{wl2}nm" in fs.filenames_lists[1][0], (
        f"channel 1 filename must carry _{wl2}nm suffix; got {fs.filenames_lists[1][0]}"
    )

    # The real save worker must have written the HDF5 files to disk
    # (the integration gap is closed: the tagged tuples reached the
    # real _frame_saver_worker_multi_channel consumer).
    for ch in range(2):
        for plane in range(2):
            fname = fs.filenames_lists[ch][plane]
            p = Path(fname)
            assert p.exists(), (
                f"channel {ch} plane {plane} HDF5 file must exist on "
                f"disk after the real save worker drained: {p}"
            )
            assert p.suffix == ".hdf5", (
                f"channel {ch} plane {plane} must be an .hdf5 file; got {p.suffix}"
            )


def test_stack_worker_multi_channel_stitch_branch_writes_one_file_per_channel(
    qtbot: QtBot, controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """StackWorker.run in multi-channel stitch mode (the default
    reconstructed_frame branch — save_all_crop=False, save_all_full=False)
    writes ONE HDF5 file per channel, each containing all planes as
    datasets — mirroring the single-channel stitch convention
    (set_files(1, ..., number_of_planes, "reconstructed_frame")) extended
    to one file per channel.

    The _plane_00001 segment in the filename is the collision-avoidance
    sequence (number_of_files=1 → only plane_00001), NOT a plane index.
    Each per-channel file holds number_of_planes datasets
    (reconstructed_frame001.. reconstructed_frameNNN).

    Regression gate for the per-(channel,plane) convention bug: the
    prior fix switched multi-channel stitch to the crop/full convention
    (one file per plane per channel), which produced one file per plane
    instead of one container per channel. The save loop must open ONE
    file per channel and write multiple datasets into it, terminating on
    frames consumed (n_channels * n_planes) — not files written.
    """
    import h5py

    from lightsheet.gui.workers import StackWorker

    ctrl = controller

    # Multi-channel mode: both auto-laser checkboxes checked.
    ctrl._auto_laser1 = True
    ctrl._auto_laser2 = True

    # Valid 2-plane stack plan.
    ctrl.saving_allowed = True
    ctrl.number_of_planes = 2
    ctrl.stack_mode_started = True
    ctrl.stack_starting_plane = 0.0
    ctrl.stack_step = 10.0
    ctrl.save_format = "hdf5"
    ctrl.save_directory = str(tmp_path)
    ctrl.save_filepath = str(tmp_path / "test")
    ctrl.save_description = "stitch integration test sample"
    # Position text attrs read by add_motor_parameters.
    ctrl.current_horizontal_position_text = "0.0"
    ctrl.current_vertical_position_text = "0.0"
    ctrl.current_camera_position_text = "0.0"

    # Stitch save path (the default reconstructed_frame branch):
    # save_all_crop=False, save_all_full=False. Multi-channel stitch
    # uses the "1 file per channel containing N datasets" convention —
    # set_files(1, ..., number_of_planes, "reconstructed_frame",
    # wavelengths=[...]) — so filenames_lists has 1 entry per channel.
    ctrl.save_panel.ui.radioButton_saveAllCrop.setChecked(False)
    ctrl.save_panel.ui.radioButton_saveAllFull.setChecked(False)

    # Wavelengths come from the live ILaser instances — never hardcoded.
    wl1 = int(ctrl.lasers[0].wavelength)
    wl2 = int(ctrl.lasers[1].wavelength)

    # Construct the StackWorker exactly as _spawn_stack_worker does.
    worker = StackWorker(
        ctrl._bundle,
        ctrl._hw,
        ctrl,
        save_description="stitch integration test sample",
        save_stitch_blend=False,
        save_all_crop=False,
        save_all_full=False,
        multi_channel=True,
    )

    # Stub acquire_scan so we don't run the full camera+siggen scan
    # logic — just set reconstructed_frame to a small frame so the
    # multi-channel capture+enqueue path runs. The real _fs receives
    # the tagged tuples.
    def _fake_acquire_scan() -> bool:
        ctrl.reconstructed_frame = np.zeros((4, 4), dtype=np.uint16)
        return True

    worker.acquire_scan = _fake_acquire_scan  # type: ignore[method-assign]  # ty: ignore[invalid-assignment]
    worker.camera.recorder_timeout_status = False
    worker.siggen.error = 0

    # Stub the motor move so MockMotors travel-limit enforcement does
    # not abort the stack (the mock enforces limits; a 10um step from 0
    # is fine but stubbing keeps the test independent of mock limits).
    with patch.object(worker.motors.horizontal, "move_absolute_position"):
        finished_emits: list[None] = []
        worker.finished.connect(lambda: finished_emits.append(None))
        worker.run()

    # The worker must have emitted finished exactly once — a deadlock
    # would never reach this assertion.
    assert len(finished_emits) == 1, (
        f"StackWorker.run must emit finished exactly once; "
        f"got {len(finished_emits)} (stitch multi-channel must not "
        f"deadlock)"
    )

    # The save side must have drained: saving_started is False after
    # run() returns (the save worker exited its consumer loop after
    # consuming n_channels * n_planes frames).
    assert ctrl._fs.frame_saver.saving_started is False, (
        "stitch multi-channel save worker must drain and exit — "
        "saving_started should be False after run() returns"
    )

    # set_files convention verification: the stitch branch must call
    # set_files(1, ..., number_of_planes, "reconstructed_frame",
    # wavelengths=[...]) in multi-channel mode — the "1 file per
    # channel containing N datasets" form. filenames_lists has 2
    # channels, each with 1 entry (number_of_files=1).
    fs = ctrl._fs.frame_saver
    assert isinstance(fs.filenames_lists, list), (
        "filenames_lists must be a list of lists in multi-channel stitch mode"
    )
    assert len(fs.filenames_lists) == 2, (
        f"filenames_lists must have one list per channel (2); "
        f"got {len(fs.filenames_lists)}"
    )
    for ch in range(2):
        assert len(fs.filenames_lists[ch]) == 1, (
            f"channel {ch} must have 1 entry (one file per channel, "
            f"not one per plane); got {len(fs.filenames_lists[ch])}"
        )

    # The filenames must carry the per-channel wavelength suffix read
    # from the live ILaser instances.
    assert f"_{wl1}nm" in fs.filenames_lists[0][0], (
        f"channel 0 filename must carry _{wl1}nm suffix; got {fs.filenames_lists[0][0]}"
    )
    assert f"_{wl2}nm" in fs.filenames_lists[1][0], (
        f"channel 1 filename must carry _{wl2}nm suffix; got {fs.filenames_lists[1][0]}"
    )

    # The real save worker must have written exactly ONE HDF5 file per
    # channel to disk (the consumer drained every enqueued tagged frame
    # into the per-channel container, no deadlock).
    per_channel_files = []
    for ch in range(2):
        fname = fs.filenames_lists[ch][0]
        p = Path(fname)
        assert p.exists(), (
            f"channel {ch} HDF5 file must exist on disk after the real "
            f"save worker drained: {p}"
        )
        assert p.suffix == ".hdf5", (
            f"channel {ch} must be an .hdf5 file; got {p.suffix}"
        )
        per_channel_files.append(p)

    # Each per-channel file must contain number_of_planes (2) datasets —
    # the "1 file containing N datasets" convention. Datasets are named
    # reconstructed_frame001, reconstructed_frame002 (per-channel
    # counter, 1-based).
    for ch, p in enumerate(per_channel_files):
        with h5py.File(p, "r") as f:  # ty: ignore[invalid-argument-type]
            ds_keys = [k for k in f if k.startswith("reconstructed_frame")]
            assert len(ds_keys) == ctrl.number_of_planes, (
                f"channel {ch} file {p.name} must contain "
                f"{ctrl.number_of_planes} datasets (one per plane); "
                f"got {len(ds_keys)}: {sorted(ds_keys)}"
            )
            assert "reconstructed_frame001" in ds_keys, (
                f"channel {ch} must have dataset reconstructed_frame001; "
                f"got {sorted(ds_keys)}"
            )
            assert "reconstructed_frame002" in ds_keys, (
                f"channel {ch} must have dataset reconstructed_frame002; "
                f"got {sorted(ds_keys)}"
            )
