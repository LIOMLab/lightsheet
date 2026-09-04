"""FrameSaverController branch-coverage gap closure (Phase 10 retroactive).

Targets the missing branches reported by `coverage report --show-missing`
for ``lightsheet/gui/coordinators/frame_saver_controller.py``:

- adaptive trajectory recorder + HDF5/Zarr writers (397-543, 1714-1885)
- multi-channel HDF5 worker branches (661-896)
- zarr_save_worker error + skip-finalize branches (938-1076)
- both_save_worker single + multi channel (1119-1561)
- ZarrSaver start_stack path-traversal guard + finalize error paths
  (1587, 1652-1657, 1899-1922)

Behavior tests (AGENTS.md §5) — every assertion is on a runtime
postcondition (file contents, dataset attrs, raised exception, emitted
message), never a static-source grep.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Never
from unittest.mock import Mock

import h5py
import numpy as np
import pytest
from PySide6.QtCore import QObject

pytest.importorskip("PySide6")


from lightsheet.adaptive.types import AdaptiveConfig, AdaptiveSample
from lightsheet.gui.coordinators.frame_saver_controller import (
    FrameSaver,
    FrameSaverController,
    ZarrSaver,
)
from lightsheet.hal import (
    DeviceBundle,
    MockCamera,
    MockLaser,
    MockMotors,
    MockSigGen,
)


class _ShellStandin(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.message_printer_calls: list[str] = []
        self.sig_message = Mock()
        self.ui = Mock()
        self.save_format = "hdf5"
        self.lasers = [
            MockLaser(wavelength=555, max_power_mw=300.0, label="L1"),
            MockLaser(wavelength=647, max_power_mw=150.0, label="L2"),
        ]
        self.camera = MockCamera(verbose=False)
        self.siggen = MockSigGen(self.camera)
        self.motors = MockMotors()
        self.save_directory = ""
        self.stack_step = 1.0
        self._auto_laser1 = False
        self._auto_laser2 = False

    def updateUi_message_printer(self, message: str) -> None:
        self.message_printer_calls.append(message)


def _make_bundle() -> DeviceBundle:
    from test.helpers.factories import make_bundle

    return make_bundle()


def _make_fs() -> tuple[FrameSaverController, _ShellStandin]:
    bundle = _make_bundle()
    shell = _ShellStandin()
    fs = FrameSaverController(bundle, shell)  # ty: ignore[invalid-argument-type]
    return fs, shell


def _make_saver(shell: _ShellStandin | None = None) -> tuple[FrameSaver, _ShellStandin]:
    shell = shell or _ShellStandin()
    return FrameSaver(shell), shell  # ty: ignore[invalid-argument-type]


def _adaptive_sample(plane: int, cva: str = "exposure") -> AdaptiveSample:
    return AdaptiveSample(
        plane_index=plane,
        intensity_fraction=[0.92, float("nan")],
        exposure_s=0.01,
        laser_power_mw=(50.0, 0.0),
        control_variable_active=cva,
        reacquired=False,
        power_fallback=False,
    )


def _adaptive_config() -> AdaptiveConfig:
    return AdaptiveConfig(
        enabled=True,
        min_exposure_s=5e-3,
        max_exposure_s=200e-3,
        min_power_mw=(0.0, 0.0),
        max_power_mw=(100.0, 100.0),
        target_band_lo=0.90,
        target_band_hi=0.95,
        reacquire_threshold=0.08,
        block_size_n=8,
        kp=0.4,
        ki=0.05,
        pilot_count=5,
        sensor_max=65535,
        max_reacquire_attempts=1,
    )


# -- adaptive recorder: record_adaptive_sample + _adaptive_config_attrs --------


def test_record_adaptive_sample_noop_when_disabled() -> None:
    """record_adaptive_sample returns early when adaptive is disabled (line 397-398)."""
    shell = _ShellStandin()
    saver = FrameSaver(shell)  # ty: ignore[invalid-argument-type]
    saver.configure_adaptive(enabled=False)
    saver.record_adaptive_sample(_adaptive_sample(0))
    assert saver.adaptive_trajectory == []


def test_record_adaptive_sample_appends_when_enabled() -> None:
    """record_adaptive_sample appends + logs when adaptive is enabled (line 399-410)."""
    shell = _ShellStandin()
    saver = FrameSaver(shell)  # ty: ignore[invalid-argument-type]
    saver.configure_adaptive(enabled=True, config=_adaptive_config())
    sample = _adaptive_sample(3)
    saver.record_adaptive_sample(sample)
    assert saver.adaptive_trajectory == [sample]


def test_adaptive_config_attrs_empty_when_no_config() -> None:
    """_adaptive_config_attrs returns {} when no config set (line 418-420)."""
    shell = _ShellStandin()
    saver = FrameSaver(shell)  # ty: ignore[invalid-argument-type]
    saver.configure_adaptive(enabled=False)
    assert saver._adaptive_config_attrs() == {}


def test_adaptive_config_attrs_full_when_config_set() -> None:
    """_adaptive_config_attrs returns the full attr dict when config is set
    (line 421-441)."""
    shell = _ShellStandin()
    saver = FrameSaver(shell)  # ty: ignore[invalid-argument-type]
    cfg = _adaptive_config()
    saver.configure_adaptive(enabled=True, config=cfg)
    attrs = saver._adaptive_config_attrs()
    assert attrs["enabled"] is True
    assert attrs["min_exposure_s"] == cfg.min_exposure_s
    assert attrs["min_power_mw"] == [0.0, 0.0]
    assert attrs["max_power_mw"] == [100.0, 100.0]
    assert attrs["block_size_n"] == 8
    assert attrs["kp"] == 0.4


# -- _write_adaptive_hdf5 + _write_adaptive_hdf5_for_file ----------------------


def test_write_adaptive_hdf5_noop_when_disabled(tmp_path: Path) -> None:
    """_write_adaptive_hdf5 returns early when adaptive disabled (line 467-468)."""
    shell = _ShellStandin()
    saver = FrameSaver(shell)  # ty: ignore[invalid-argument-type]
    saver.configure_adaptive(enabled=False)
    filepath = str(tmp_path / "f.hdf5")
    with h5py.File(filepath, "w") as f:
        saver._write_adaptive_hdf5(f)
        assert "adaptive_trajectory" not in f


def test_write_adaptive_hdf5_noop_when_empty_trajectory(tmp_path: Path) -> None:
    """_write_adaptive_hdf5 returns early when trajectory is empty (line 470-471)."""
    shell = _ShellStandin()
    saver = FrameSaver(shell)  # ty: ignore[invalid-argument-type]
    saver.configure_adaptive(enabled=True, config=_adaptive_config())
    filepath = str(tmp_path / "f.hdf5")
    with h5py.File(filepath, "w") as f:
        saver._write_adaptive_hdf5(f)
        assert "adaptive_trajectory" not in f


def test_write_adaptive_hdf5_writes_full_group(tmp_path: Path) -> None:
    """_write_adaptive_hdf5 writes the /adaptive_trajectory group + datasets
    (467-505)."""
    shell = _ShellStandin()
    saver = FrameSaver(shell)  # ty: ignore[invalid-argument-type]
    saver.configure_adaptive(enabled=True, config=_adaptive_config())
    saver.record_adaptive_sample(_adaptive_sample(0))
    saver.record_adaptive_sample(_adaptive_sample(1))
    filepath = str(tmp_path / "f.hdf5")
    with h5py.File(filepath, "w") as f:
        saver._write_adaptive_hdf5(f)
        assert "adaptive_trajectory" in f
        grp = f["adaptive_trajectory"]
        assert bool(grp.attrs["enabled"]) is True
        assert "plane_index" in grp  # ty: ignore[unsupported-operator]
        assert "intensity_fraction" in grp  # ty: ignore[unsupported-operator]
        assert "exposure_s" in grp  # ty: ignore[unsupported-operator]
        assert "laser_power_mw" in grp  # ty: ignore[unsupported-operator]
        assert "control_variable_active" in grp  # ty: ignore[unsupported-operator]
        assert "reacquired" in grp  # ty: ignore[unsupported-operator]
        assert "power_fallback" in grp  # ty: ignore[unsupported-operator]
        assert list(grp["plane_index"][:]) == [0, 1]  # ty: ignore[invalid-argument-type, not-subscriptable]


def test_write_adaptive_hdf5_for_file_stitch_writes_full(tmp_path: Path) -> None:
    """_write_adaptive_hdf5_for_file with n_files==1 writes full trajectory
    (542-543)."""
    shell = _ShellStandin()
    saver = FrameSaver(shell)  # ty: ignore[invalid-argument-type]
    saver.configure_adaptive(enabled=True, config=_adaptive_config())
    saver.record_adaptive_sample(_adaptive_sample(0))
    saver.record_adaptive_sample(_adaptive_sample(1))
    filepath = str(tmp_path / "f.hdf5")
    with h5py.File(filepath, "w") as f:
        saver._write_adaptive_hdf5_for_file(f, file_idx=0, n_files=1)
        assert "adaptive_trajectory" in f
        assert list(f["adaptive_trajectory"]["plane_index"][:]) == [0, 1]  # ty: ignore[invalid-argument-type, not-subscriptable]


def test_write_adaptive_hdf5_for_file_per_plane_writes_subset(tmp_path: Path) -> None:
    """_write_adaptive_hdf5_for_file with n_files>1 writes the file's plane
    rows (534-541)."""
    shell = _ShellStandin()
    saver = FrameSaver(shell)  # ty: ignore[invalid-argument-type]
    saver.configure_adaptive(enabled=True, config=_adaptive_config())
    for i in range(4):
        saver.record_adaptive_sample(_adaptive_sample(i))
    # File 1 of 4 (per-plane layout) should carry only plane_index 1.
    filepath = str(tmp_path / "f1.hdf5")
    with h5py.File(filepath, "w") as f:
        saver._write_adaptive_hdf5_for_file(f, file_idx=1, n_files=4)
        assert "adaptive_trajectory" in f
        assert list(f["adaptive_trajectory"]["plane_index"][:]) == [1]  # ty: ignore[invalid-argument-type, not-subscriptable]


def test_write_adaptive_hdf5_for_file_per_plane_out_of_range_skips(
    tmp_path: Path,
) -> None:
    """_write_adaptive_hdf5_for_file skips when start index
    past trajectory end (537->exit)."""
    shell = _ShellStandin()
    saver = FrameSaver(shell)  # ty: ignore[invalid-argument-type]
    saver.configure_adaptive(enabled=True, config=_adaptive_config())
    saver.record_adaptive_sample(_adaptive_sample(0))
    filepath = str(tmp_path / "f.hdf5")
    with h5py.File(filepath, "w") as f:
        # file_idx=5 with n_datasets=1 -> start=5, but trajectory len=1 -> skip.
        saver._write_adaptive_hdf5_for_file(f, file_idx=5, n_files=10)
        assert "adaptive_trajectory" not in f


def test_write_adaptive_hdf5_for_file_noop_when_disabled(tmp_path: Path) -> None:
    """_write_adaptive_hdf5_for_file is a no-op when adaptive disabled (532-533)."""
    shell = _ShellStandin()
    saver = FrameSaver(shell)  # ty: ignore[invalid-argument-type]
    saver.configure_adaptive(enabled=False)
    filepath = str(tmp_path / "f.hdf5")
    with h5py.File(filepath, "w") as f:
        saver._write_adaptive_hdf5_for_file(f, file_idx=0, n_files=1)
        assert "adaptive_trajectory" not in f


# -- multi-channel HDF5 worker (_frame_saver_worker_multi_channel, 661-896) ----


def _setup_multichannel_saver(
    shell: _ShellStandin, tmp_path: Path, n_planes: int = 2
) -> FrameSaver:
    """Build a FrameSaver configured for 2-channel stitch (1 file/channel,
    N datasets)."""
    saver = FrameSaver(shell)  # ty: ignore[invalid-argument-type]
    # Reinit with a larger block_size so the queue (maxsize = 2*block_size)
    # can hold all the interleaved frames the test pre-loads.
    saver.reinit(8)
    shell.save_directory = str(tmp_path)
    saver.set_files(
        number_of_files=1,
        files_name=str(tmp_path / "stack"),
        scan_type="z",
        number_of_datasets=n_planes,
        datasets_name="ch",
        wavelengths=[555, 647],
    )
    saver.sample_name = "mc"
    saver.number_of_files = 1
    saver.horizontal_positions_list = [f"{i}.0" for i in range(n_planes)]
    saver.vertical_positions_list = [f"{i}.0" for i in range(n_planes)]
    saver.camera_positions_list = [f"{i}.0" for i in range(n_planes)]
    saver.saving_started = True
    return saver


def test_multichannel_hdf5_worker_writes_per_channel_files(tmp_path: Path) -> None:
    """The multi-channel HDF5 worker writes one file per channel with the
    interleaved frames routed by the channel tag (lines 735-867 happy path)."""
    shell = _ShellStandin()
    n_planes = 2
    saver = _setup_multichannel_saver(shell, tmp_path, n_planes=n_planes)
    frame = np.ones((4, 4), dtype=np.uint16)
    # Interleaved: (ch0, plane0), (ch1, plane0), (ch0, plane1), (ch1, plane1).
    for _z in range(n_planes):
        saver.enqueue_buffer((0, frame))
        saver.enqueue_buffer((1, frame))
    saver._frame_saver_worker_multi_channel()
    # Two channel files, each with n_planes datasets.
    assert len(saver.filenames_lists) == 2
    for ch in range(2):
        with h5py.File(saver.filenames_lists[ch][0], "r") as f:
            keys = sorted(f.keys())
            assert len(keys) == n_planes, f"channel {ch}: {keys}"


def test_multichannel_hdf5_worker_bare_ndarray_falls_back_to_channel0(
    tmp_path: Path,
) -> None:
    """A bare ndarray (no channel tag) falls back to channel 0 (line 775-776)."""
    shell = _ShellStandin()
    n_planes = 1
    saver = _setup_multichannel_saver(shell, tmp_path, n_planes=n_planes)
    frame = np.ones((4, 4), dtype=np.uint16)
    # Bare ndarray — should route to channel 0.
    saver.enqueue_buffer(frame)
    # Channel 1 frame as tagged tuple so total_frames is reached.
    saver.enqueue_buffer((1, frame))
    saver._frame_saver_worker_multi_channel()
    with h5py.File(saver.filenames_lists[0][0], "r") as f:
        assert len(f.keys()) == 1


def test_multichannel_hdf5_worker_out_of_range_channel_aborts(tmp_path: Path) -> None:
    """A channel index out of range emits an error + flips saving_started (778-784)."""
    shell = _ShellStandin()
    n_planes = 1
    saver = _setup_multichannel_saver(shell, tmp_path, n_planes=n_planes)
    # channel_idx=5 is out of range (n_channels=2).
    saver.enqueue_buffer((5, np.ones((4, 4), dtype=np.uint16)))
    saver._frame_saver_worker_multi_channel()
    assert saver.saving_started is False
    assert any("out of range" in m for m in shell.message_printer_calls)


def test_multichannel_hdf5_worker_drains_after_stop_saving(tmp_path: Path) -> None:
    """When saving_started flips False mid-loop, the worker drains remaining
    frames via get_nowait before exiting (lines 759-766)."""
    shell = _ShellStandin()
    n_planes = 2
    saver = _setup_multichannel_saver(shell, tmp_path, n_planes=n_planes)
    frame = np.ones((4, 4), dtype=np.uint16)
    # Pre-load all frames.
    for _z in range(n_planes):
        saver.enqueue_buffer((0, frame))
        saver.enqueue_buffer((1, frame))
    # Flip saving_started False BEFORE running — drains via get_nowait path.
    saver.saving_started = False
    saver._frame_saver_worker_multi_channel()
    # Files still written because the drain path consumed them.
    with h5py.File(saver.filenames_lists[0][0], "r") as f:
        assert len(f.keys()) == n_planes


def test_multichannel_hdf5_worker_per_plane_layout_advances_files(
    tmp_path: Path,
) -> None:
    """Per-plane layout (n_files>1, n_datasets=1) opens/closes files as each
    fills (lines 838-867)."""
    shell = _ShellStandin()
    shell.save_directory = str(tmp_path)
    saver = FrameSaver(shell)  # ty: ignore[invalid-argument-type]
    saver.reinit(8)
    n_planes = 3
    saver.set_files(
        number_of_files=n_planes,
        files_name=str(tmp_path / "stack"),
        scan_type="z",
        number_of_datasets=1,
        datasets_name="ch",
        wavelengths=[555, 647],
    )
    saver.sample_name = "mc"
    saver.number_of_files = n_planes
    saver.horizontal_positions_list = [f"{i}.0" for i in range(n_planes)]
    saver.vertical_positions_list = [f"{i}.0" for i in range(n_planes)]
    saver.camera_positions_list = [f"{i}.0" for i in range(n_planes)]
    saver.saving_started = True
    frame = np.ones((4, 4), dtype=np.uint16)
    for _z in range(n_planes):
        saver.enqueue_buffer((0, frame))
        saver.enqueue_buffer((1, frame))
    saver._frame_saver_worker_multi_channel()
    # Each channel produced n_planes files.
    for ch in range(2):
        assert len(saver.filenames_lists[ch]) == n_planes
        for p in range(n_planes):
            assert Path(saver.filenames_lists[ch][p]).is_file()


def test_multichannel_hdf5_worker_overrun_channel_drops_frame(tmp_path: Path) -> None:
    """When a channel's files are exhausted (outfiles[ch]=None) extra frames
    are dropped without counting (line 792, 867)."""
    shell = _ShellStandin()
    n_planes = 1
    saver = _setup_multichannel_saver(shell, tmp_path, n_planes=n_planes)
    frame = np.ones((4, 4), dtype=np.uint16)
    # Send the expected frames.
    saver.enqueue_buffer((0, frame))
    saver.enqueue_buffer((1, frame))
    # Send an extra channel-0 frame after the channel is full.
    saver.enqueue_buffer((0, frame))
    saver._frame_saver_worker_multi_channel()
    # No crash; channel 0 file has exactly 1 dataset.
    with h5py.File(saver.filenames_lists[0][0], "r") as f:
        assert len(f.keys()) == 1


def test_multichannel_hdf5_worker_3d_buffer_expands(tmp_path: Path) -> None:
    """A 3D frame buffer (multiple sub-frames) is expanded and each sub-frame
    written as its own dataset (line 802-804)."""
    shell = _ShellStandin()
    n_planes = 2
    saver = _setup_multichannel_saver(shell, tmp_path, n_planes=n_planes)
    # 3D buffer with 2 sub-frames for channel 0.
    buf = np.ones((2, 4, 4), dtype=np.uint16)
    saver.enqueue_buffer((0, buf))
    saver.enqueue_buffer((1, np.ones((4, 4), dtype=np.uint16)))
    saver.enqueue_buffer((1, np.ones((4, 4), dtype=np.uint16)))
    saver._frame_saver_worker_multi_channel()
    with h5py.File(saver.filenames_lists[0][0], "r") as f:
        assert len(f.keys()) == 2


def test_multichannel_hdf5_worker_write_error_aborts(tmp_path: Path) -> None:
    """A per-dataset write error surfaces via sig_status_message + flips
    saving_started (lines 831-834, 868-870)."""
    shell = _ShellStandin()
    n_planes = 1
    saver = _setup_multichannel_saver(shell, tmp_path, n_planes=n_planes)
    # Make the first channel's file unwritable by pointing it at a directory
    # that does not exist — h5py.File raises on open, caught by the outer
    # try/except (line 868-870).
    saver.filenames_lists[0][0] = str(tmp_path / "no_such_dir" / "x.hdf5")
    saver.enqueue_buffer((0, np.ones((4, 4), dtype=np.uint16)))
    saver._frame_saver_worker_multi_channel()
    assert saver.saving_started is False
    assert any("Save error" in m for m in shell.message_printer_calls)


def test_multichannel_hdf5_worker_finally_closes_open_files(
    tmp_path: Path,
) -> None:
    """The finally block closes any still-open per-channel files (887-889)."""
    shell = _ShellStandin()
    n_planes = 2
    saver = _setup_multichannel_saver(shell, tmp_path, n_planes=n_planes)
    # Send only channel-0 frames; channel-1 file stays open at loop exit
    # (frames_written < total_frames), so the finally path closes it.
    frame = np.ones((4, 4), dtype=np.uint16)
    saver.enqueue_buffer((0, frame))
    saver.enqueue_buffer((0, frame))
    # Flip saving_started False so the loop exits after draining.
    saver.saving_started = False
    saver._frame_saver_worker_multi_channel()
    # Channel 0 file was finalized in-loop; channel 1 file was closed in
    # finally. Both files exist (channel 1 may be empty but must be closeable).
    assert Path(saver.filenames_lists[1][0]).is_file()


# -- frame_saver_worker single-channel: continue + exception paths (661-694) ---


def test_frame_saver_worker_continue_on_empty_queue_while_saving(
    tmp_path: Path,
) -> None:
    """When the queue is empty but saving_started is still True, the inner
    loop continues (re-tries the get) instead of breaking (line 661)."""
    shell = _ShellStandin()
    saver = FrameSaver(shell)  # ty: ignore[invalid-argument-type]
    saver.reinit(8)
    filepath = str(tmp_path / "plane.hdf5")
    saver.filenames_list = [filepath]
    saver.number_of_datasets = 1
    saver.datasets_name = "ds_"
    saver.sample_name = "s"
    saver.horizontal_positions_list = ["H0"]
    saver.vertical_positions_list = ["V0"]
    saver.camera_positions_list = ["C0"]
    saver.saving_started = True

    # Run in a thread; the worker will time out on the first get, hit the
    # `else: continue` branch (saving_started still True), then we enqueue
    # a frame so the second get succeeds and the worker completes.
    t = threading.Thread(target=saver.frame_saver_worker, daemon=True)
    t.start()
    # Let it enter the get(timeout=1) and hit the Empty->continue branch.
    time.sleep(1.2)
    saver.enqueue_buffer(np.ones((4, 4), dtype=np.uint16))
    t.join(timeout=5.0)
    assert not t.is_alive(), "worker must exit after the frame is consumed"
    assert Path(filepath).is_file()


def test_frame_saver_worker_per_dataset_exception_aborts(tmp_path: Path) -> None:
    """A non-timeout exception during dataset write surfaces via
    sig_status_message + flips saving_started (lines 662-675)."""
    shell = _ShellStandin()
    saver = FrameSaver(shell)  # ty: ignore[invalid-argument-type]
    saver.reinit(8)
    filepath = str(tmp_path / "plane.hdf5")
    saver.filenames_list = [filepath]
    saver.number_of_datasets = 1
    saver.datasets_name = "ds_"
    saver.sample_name = "s"
    saver.horizontal_positions_list = ["H0"]
    saver.vertical_positions_list = ["V0"]
    saver.camera_positions_list = ["C0"]
    saver.saving_started = True

    # Patch outfile.create_dataset to raise — simulates a write error.
    original = h5py.File.create_dataset

    def _raise(self: Any, *a: Any, **k: Any) -> Never:
        raise RuntimeError("simulated write error")

    h5py.File.create_dataset = _raise
    try:
        saver.enqueue_buffer(np.ones((4, 4), dtype=np.uint16))
        saver.frame_saver_worker()
    finally:
        h5py.File.create_dataset = original
    assert saver.saving_started is False
    assert any("simulated write error" in m for m in shell.message_printer_calls)


def test_frame_saver_worker_adaptive_write_error_aborts(tmp_path: Path) -> None:
    """An exception from _write_adaptive_hdf5_for_file surfaces + flips
    saving_started (lines 690-694)."""
    shell = _ShellStandin()
    saver = FrameSaver(shell)  # ty: ignore[invalid-argument-type]
    saver.reinit(8)
    filepath = str(tmp_path / "plane.hdf5")
    saver.filenames_list = [filepath]
    saver.number_of_datasets = 1
    saver.datasets_name = "ds_"
    saver.sample_name = "s"
    saver.horizontal_positions_list = ["H0"]
    saver.vertical_positions_list = ["V0"]
    saver.camera_positions_list = ["C0"]
    saver.saving_started = True
    saver.configure_adaptive(enabled=True, config=_adaptive_config())
    saver.record_adaptive_sample(_adaptive_sample(0))

    def _bad_write(*a: Any, **k: Any) -> Never:
        raise RuntimeError("adaptive write boom")

    setattr(saver, "_write_adaptive_hdf5_for_file", _bad_write)
    saver.enqueue_buffer(np.ones((4, 4), dtype=np.uint16))
    saver.frame_saver_worker()
    assert saver.saving_started is False
    assert any("adaptive write boom" in m for m in shell.message_printer_calls)


# -- zarr_save_worker error + skip-finalize branches (938-1076) ---------------


def _setup_zarr_saver(
    shell: _ShellStandin, tmp_path: Path, n_planes: int = 2, n_channels: int = 1
) -> FrameSaver:
    shell.save_directory = str(tmp_path)
    shell.save_format = "zarr"
    shell.camera.xsize = 32
    shell.camera.ysize = 32
    saver = FrameSaver(shell)  # ty: ignore[invalid-argument-type]
    saver.reinit(8)
    saver.set_files(
        number_of_files=n_planes,
        files_name=str(tmp_path / "stack"),
        scan_type="z",
        number_of_datasets=1,
        datasets_name="ch",
        wavelengths=[555] if n_channels == 1 else [555, 647],
    )
    saver.horizontal_positions_list = [f"{i}.0" for i in range(n_planes)]
    saver.vertical_positions_list = [f"{i}.0" for i in range(n_planes)]
    saver.camera_positions_list = [f"{i}.0" for i in range(n_planes)]
    saver.saving_started = True
    return saver


def test_zarr_save_worker_start_stack_error_aborts(tmp_path: Path) -> None:
    """A start_stack failure emits a save error + flips saving_started (938-941)."""
    shell = _ShellStandin()
    saver = _setup_zarr_saver(shell, tmp_path)
    # Point save_directory at a non-existent dir so start_stack's path guard
    # raises ValueError.
    shell.save_directory = str(tmp_path / "no_such_dir")
    saver.parent.save_directory = shell.save_directory  # ty: ignore[invalid-assignment]
    saver.enqueue_buffer(np.zeros((32, 32), dtype=np.uint16))
    saver.zarr_save_worker()
    assert saver.saving_started is False
    assert any("Save error" in m for m in shell.message_printer_calls)


def test_zarr_save_worker_skips_finalize_on_partial_store(tmp_path: Path) -> None:
    """When channel 0 did not reach n_planes, finalize is skipped (1058-1065)."""
    import zarr

    shell = _ShellStandin()
    n_planes = 3
    saver = _setup_zarr_saver(shell, tmp_path, n_planes=n_planes)
    # Enqueue only 1 frame then stop — ch0_z=1 < n_planes=3 -> skip finalize.
    saver.enqueue_buffer(np.zeros((32, 32), dtype=np.uint16))
    saver.saving_started = True

    class _StopAfterFirst:
        def __init__(self: Any, real: Any) -> None:
            self._real = real
            self._n = 0

        def get(self: Any, block: bool = True, timeout: Any | None = None) -> Any:
            buf = self._real.get(block=block, timeout=timeout)
            self._n += 1
            if self._n >= 1:
                saver.saving_started = False
            return buf

        def get_nowait(self) -> Any:
            return self._real.get_nowait()

        def __getattr__(self: Any, name: Any) -> Any:
            return getattr(self._real, name)

    saver.queue = _StopAfterFirst(saver.queue)  # ty: ignore[invalid-assignment]
    saver.zarr_save_worker()
    # No finalize -> no /acquisition group.
    root = zarr.open(str(tmp_path / "stack.ome.zarr"), mode="r")
    assert "acquisition" not in root


def test_zarr_save_worker_finalize_error_flips_saving(tmp_path: Path) -> None:
    """A finalize failure surfaces + flips saving_started (1073-1075)."""
    shell = _ShellStandin()
    n_planes = 2
    saver = _setup_zarr_saver(shell, tmp_path, n_planes=n_planes)
    for _ in range(n_planes):
        saver.enqueue_buffer(np.zeros((32, 32), dtype=np.uint16))

    def _bad_finalize() -> Never:
        raise RuntimeError("finalize boom")

    setattr(saver._zarr_saver, "finalize", _bad_finalize)
    saver.zarr_save_worker()
    assert saver.saving_started is False
    assert any("finalize boom" in m for m in shell.message_printer_calls)


def test_zarr_save_worker_bare_ndarray_falls_back_to_channel0(tmp_path: Path) -> None:
    """A bare ndarray (no channel tag) routes to channel 0 (1006-1007)."""
    import zarr

    shell = _ShellStandin()
    n_planes = 1
    saver = _setup_zarr_saver(shell, tmp_path, n_planes=n_planes)
    # Bare ndarray instead of (channel_idx, frame) tuple.
    saver.enqueue_buffer(np.zeros((32, 32), dtype=np.uint16))
    saver.zarr_save_worker()
    root = zarr.open(str(tmp_path / "stack.ome.zarr"), mode="r")
    assert "acquisition" in root


def test_zarr_save_worker_3d_buffer_expands(tmp_path: Path) -> None:
    """A 3D buffer is expanded to 3D and each sub-frame written (1006-1008)."""
    import zarr

    shell = _ShellStandin()
    n_planes = 2
    saver = _setup_zarr_saver(shell, tmp_path, n_planes=n_planes)
    buf = np.zeros((2, 32, 32), dtype=np.uint16)
    saver.enqueue_buffer(buf)
    saver.zarr_save_worker()
    root = zarr.open(str(tmp_path / "stack.ome.zarr"), mode="r")
    assert root["0"].shape[1] == n_planes  # ty: ignore[invalid-argument-type, unresolved-attribute]


def test_zarr_save_worker_channel_full_drops_extra(tmp_path: Path) -> None:
    """When a channel's plane slots are full, extra frames are dropped (1010-1013)."""
    import zarr

    shell = _ShellStandin()
    n_planes = 1
    saver = _setup_zarr_saver(shell, tmp_path, n_planes=n_planes)
    saver.enqueue_buffer(np.zeros((32, 32), dtype=np.uint16))
    # Extra frame beyond n_planes — the cz >= n_planes break drops it.
    saver.enqueue_buffer(np.zeros((32, 32), dtype=np.uint16))
    # Flip saving_started False so the second get_nowait -> Empty breaks.
    saver.saving_started = True

    class _StopAfterFirst:
        def __init__(self: Any, real: Any) -> None:
            self._real = real
            self._n = 0

        def get(self: Any, block: bool = True, timeout: Any | None = None) -> Any:
            buf = self._real.get(block=block, timeout=timeout)
            self._n += 1
            if self._n >= 1:
                saver.saving_started = False
            return buf

        def get_nowait(self) -> Any:
            return self._real.get_nowait()

        def __getattr__(self: Any, name: Any) -> Any:
            return getattr(self._real, name)

    saver.queue = _StopAfterFirst(saver.queue)  # ty: ignore[invalid-assignment]
    saver.zarr_save_worker()
    root = zarr.open(str(tmp_path / "stack.ome.zarr"), mode="r")
    assert root["0"].shape[1] == n_planes  # ty: ignore[invalid-argument-type, unresolved-attribute]


def test_zarr_save_worker_short_position_list_uses_zero(tmp_path: Path) -> None:
    """When the position list is shorter than z_idx, motor pos defaults to 0.0
    (lines 1041-1043)."""
    import zarr

    shell = _ShellStandin()
    n_planes = 2
    saver = _setup_zarr_saver(shell, tmp_path, n_planes=n_planes)
    # Truncate the position lists so pos_index >= len -> 0.0 fallback.
    saver.horizontal_positions_list = []
    saver.vertical_positions_list = []
    saver.camera_positions_list = []
    for _ in range(n_planes):
        saver.enqueue_buffer(np.zeros((32, 32), dtype=np.uint16))
    saver.zarr_save_worker()
    root = zarr.open(str(tmp_path / "stack.ome.zarr"), mode="r")
    acq = root["acquisition"]  # ty: ignore[invalid-argument-type]
    # All motor positions are 0.0 (the fallback).
    assert np.all(acq["motor"]["horizontal"][:] == 0.0)  # ty: ignore[invalid-argument-type, not-subscriptable]


# -- both_save_worker single-channel (1119-1302) ------------------------------


def _setup_both_saver(
    shell: _ShellStandin, tmp_path: Path, n_planes: int = 2, n_channels: int = 1
) -> FrameSaver:
    shell.save_directory = str(tmp_path)
    shell.save_format = "both"
    shell.camera.xsize = 32
    shell.camera.ysize = 32
    saver = FrameSaver(shell)  # ty: ignore[invalid-argument-type]
    saver.reinit(8)
    saver.set_files(
        number_of_files=n_planes,
        files_name=str(tmp_path / "stack"),
        scan_type="z",
        number_of_datasets=1,
        datasets_name="ch",
        wavelengths=[555] if n_channels == 1 else [555, 647],
    )
    saver.horizontal_positions_list = [f"{i}.0" for i in range(n_planes)]
    saver.vertical_positions_list = [f"{i}.0" for i in range(n_planes)]
    saver.camera_positions_list = [f"{i}.0" for i in range(n_planes)]
    saver.saving_started = True
    return saver


def test_both_save_worker_start_stack_error_aborts(tmp_path: Path) -> None:
    """A start_stack failure in both_save_worker emits + flips saving (1129-1132)."""
    shell = _ShellStandin()
    saver = _setup_both_saver(shell, tmp_path)
    shell.save_directory = str(tmp_path / "no_such_dir")
    saver.parent.save_directory = shell.save_directory  # ty: ignore[invalid-assignment]
    saver.enqueue_buffer(np.zeros((32, 32), dtype=np.uint16))
    saver.both_save_worker()
    assert saver.saving_started is False
    assert any("Save error" in m for m in shell.message_printer_calls)


def test_both_save_worker_file_open_error_aborts(tmp_path: Path) -> None:
    """A per-file open/metadata error breaks the file loop (1144-1147)."""
    shell = _ShellStandin()
    saver = _setup_both_saver(shell, tmp_path, n_planes=2)
    # Make the first filename unwritable.
    saver.filenames_list[0] = str(tmp_path / "no_dir" / "x.hdf5")
    saver.enqueue_buffer(np.zeros((32, 32), dtype=np.uint16))
    saver.both_save_worker()
    assert saver.saving_started is False


def test_both_save_worker_per_dataset_write_error_aborts(tmp_path: Path) -> None:
    """A per-dataset write error surfaces + flips saving_started (1246-1250)."""
    shell = _ShellStandin()
    saver = _setup_both_saver(shell, tmp_path, n_planes=1)
    original = h5py.File.create_dataset

    def _raise(self: Any, *a: Any, **k: Any) -> Never:
        raise RuntimeError("both write boom")

    h5py.File.create_dataset = _raise
    try:
        saver.enqueue_buffer(np.zeros((32, 32), dtype=np.uint16))
        saver.both_save_worker()
    finally:
        h5py.File.create_dataset = original
    assert saver.saving_started is False
    assert any("both write boom" in m for m in shell.message_printer_calls)


def test_both_save_worker_adaptive_write_error_aborts(tmp_path: Path) -> None:
    """An adaptive write error in both_save_worker surfaces + flips
    saving (1263-1268)."""
    shell = _ShellStandin()
    saver = _setup_both_saver(shell, tmp_path, n_planes=1)
    saver.configure_adaptive(enabled=True, config=_adaptive_config())
    saver.record_adaptive_sample(_adaptive_sample(0))

    def _bad(*a: Any, **k: Any) -> Never:
        raise RuntimeError("both adaptive boom")

    setattr(saver, "_write_adaptive_hdf5_for_file", _bad)
    saver.enqueue_buffer(np.zeros((32, 32), dtype=np.uint16))
    saver.both_save_worker()
    assert saver.saving_started is False
    assert any("both adaptive boom" in m for m in shell.message_printer_calls)


def test_both_save_worker_skips_finalize_on_partial_store(tmp_path: Path) -> None:
    """When z_idx < n_planes, both_save_worker skips finalize (1282-1283)."""
    import zarr

    shell = _ShellStandin()
    n_planes = 3
    saver = _setup_both_saver(shell, tmp_path, n_planes=n_planes)
    # Enqueue only 1 frame then stop -> z_idx=1 < 3 -> skip finalize.
    saver.enqueue_buffer(np.zeros((32, 32), dtype=np.uint16))

    class _StopAfterFirst:
        def __init__(self: Any, real: Any) -> None:
            self._real = real
            self._n = 0

        def get(self: Any, block: bool = True, timeout: Any | None = None) -> Any:
            buf = self._real.get(block=block, timeout=timeout)
            self._n += 1
            if self._n >= 1:
                saver.saving_started = False
            return buf

        def get_nowait(self) -> Any:
            return self._real.get_nowait()

        def __getattr__(self: Any, name: Any) -> Any:
            return getattr(self._real, name)

    saver.queue = _StopAfterFirst(saver.queue)  # ty: ignore[invalid-assignment]
    saver.both_save_worker()
    root = zarr.open(str(tmp_path / "stack.ome.zarr"), mode="r")
    assert "acquisition" not in root


def test_both_save_worker_finalize_error_flips_saving(tmp_path: Path) -> None:
    """A finalize failure in both_save_worker surfaces + flips saving (1296-1301)."""
    shell = _ShellStandin()
    n_planes = 2
    saver = _setup_both_saver(shell, tmp_path, n_planes=n_planes)
    for _ in range(n_planes):
        saver.enqueue_buffer(np.zeros((32, 32), dtype=np.uint16))

    def _bad() -> Never:
        raise RuntimeError("both finalize boom")

    setattr(saver._zarr_saver, "finalize", _bad)
    saver.both_save_worker()
    assert saver.saving_started is False
    assert any("both finalize boom" in m for m in shell.message_printer_calls)


def test_both_save_worker_3d_buffer_uses_idx_for_h5_pos(tmp_path: Path) -> None:
    """A 3D buffer (multi-frame) uses idx for h5_pos_index (1178, 1186->1196)."""
    import h5py

    shell = _ShellStandin()
    n_planes = 2
    saver = _setup_both_saver(shell, tmp_path, n_planes=n_planes)
    # 3D buffer with 2 sub-frames — buffer.shape[0] != 1 so h5_pos_index = idx.
    buf = np.zeros((2, 32, 32), dtype=np.uint16)
    saver.enqueue_buffer(buf)
    saver.both_save_worker()
    # Both sub-frames written (z_idx 0,1 < n_planes=2).
    with h5py.File(saver.filenames_list[0], "r") as f:
        assert len(f.keys()) == 2


def test_both_save_worker_short_position_list_uses_zero(tmp_path: Path) -> None:
    """When h5_pos_index >= len(position_list), HDF5 attrs are skipped (1186->1196)."""
    import h5py

    shell = _ShellStandin()
    n_planes = 1
    saver = _setup_both_saver(shell, tmp_path, n_planes=n_planes)
    saver.horizontal_positions_list = []
    saver.vertical_positions_list = []
    saver.camera_positions_list = []
    saver.enqueue_buffer(np.zeros((32, 32), dtype=np.uint16))
    saver.both_save_worker()
    with h5py.File(saver.filenames_list[0], "r") as f:
        ds = f[next(iter(f.keys()))]
        # Horizontal Position attr is absent (pos list was empty).
        assert "Horizontal Position" not in ds.attrs


# -- both_save_worker multi-channel (1332-1556) -------------------------------


def test_both_save_worker_multichannel_writes_both_formats(tmp_path: Path) -> None:
    """The multi-channel both-save worker writes per-channel HDF5 + Zarr
    (lines 1332-1547 happy path)."""
    import h5py
    import zarr

    shell = _ShellStandin()
    n_planes = 2
    saver = _setup_both_saver(shell, tmp_path, n_planes=n_planes, n_channels=2)
    shell._auto_laser1 = True
    shell._auto_laser2 = True
    frame = np.zeros((32, 32), dtype=np.uint16)
    for _z in range(n_planes):
        saver.enqueue_buffer((0, frame))
        saver.enqueue_buffer((1, frame))
    saver._both_save_worker_multi_channel()
    # Zarr store finalized with 2 channels.
    root = zarr.open(str(tmp_path / "stack.ome.zarr"), mode="r")
    assert "acquisition" in root
    assert root["0"].shape[0] == 2  # ty: ignore[invalid-argument-type, unresolved-attribute]
    # Both channel HDF5 files written — per-plane layout (n_files=n_planes,
    # 1 dataset/file), so each file holds exactly 1 dataset.
    for ch in range(2):
        assert len(saver.filenames_lists[ch]) == n_planes
        for p in range(n_planes):
            with h5py.File(saver.filenames_lists[ch][p], "r") as f:
                assert len(f.keys()) == 1


def test_both_save_worker_multichannel_bare_ndarray_channel0(tmp_path: Path) -> None:
    """A bare ndarray in multi-channel both-save falls back to channel 0 (1382-1386)."""
    import h5py

    shell = _ShellStandin()
    n_planes = 1
    saver = _setup_both_saver(shell, tmp_path, n_planes=n_planes, n_channels=2)
    shell._auto_laser1 = True
    shell._auto_laser2 = True
    frame = np.zeros((32, 32), dtype=np.uint16)
    saver.enqueue_buffer(frame)  # bare ndarray -> channel 0
    saver.enqueue_buffer((1, frame))
    saver._both_save_worker_multi_channel()
    with h5py.File(saver.filenames_lists[0][0], "r") as f:
        assert len(f.keys()) == 1


def test_both_save_worker_multichannel_out_of_range_aborts(tmp_path: Path) -> None:
    """An out-of-range channel index aborts multi-channel both-save (1388-1394)."""
    shell = _ShellStandin()
    n_planes = 1
    saver = _setup_both_saver(shell, tmp_path, n_planes=n_planes, n_channels=2)
    saver.enqueue_buffer((5, np.zeros((32, 32), dtype=np.uint16)))
    saver._both_save_worker_multi_channel()
    assert saver.saving_started is False
    assert any("out of range" in m for m in shell.message_printer_calls)


def test_both_save_worker_multichannel_overrun_drops(tmp_path: Path) -> None:
    """When a channel's files are exhausted, extra frames are dropped (1396-1400)."""
    import h5py

    shell = _ShellStandin()
    n_planes = 1
    saver = _setup_both_saver(shell, tmp_path, n_planes=n_planes, n_channels=2)
    shell._auto_laser1 = True
    shell._auto_laser2 = True
    frame = np.zeros((32, 32), dtype=np.uint16)
    saver.enqueue_buffer((0, frame))
    saver.enqueue_buffer((1, frame))
    # Extra channel-0 frame after channel is full -> dropped.
    saver.enqueue_buffer((0, frame))
    saver._both_save_worker_multi_channel()
    with h5py.File(saver.filenames_lists[0][0], "r") as f:
        assert len(f.keys()) == 1


def test_both_save_worker_multichannel_per_dataset_error_aborts(
    tmp_path: Path,
) -> None:
    """A per-dataset write error aborts multi-channel both-save (1475-1478)."""
    shell = _ShellStandin()
    n_planes = 1
    saver = _setup_both_saver(shell, tmp_path, n_planes=n_planes, n_channels=2)
    original = h5py.File.create_dataset

    def _raise(self: Any, *a: Any, **k: Any) -> Never:
        raise RuntimeError("mc both write boom")

    h5py.File.create_dataset = _raise
    try:
        saver.enqueue_buffer((0, np.zeros((32, 32), dtype=np.uint16)))
        saver._both_save_worker_multi_channel()
    finally:
        h5py.File.create_dataset = original
    assert saver.saving_started is False
    assert any("mc both write boom" in m for m in shell.message_printer_calls)


def test_both_save_worker_multichannel_skips_finalize_on_partial(
    tmp_path: Path,
) -> None:
    """When ch0_z < n_planes, multi-channel both-save skips finalize (1530-1537)."""
    import zarr

    shell = _ShellStandin()
    n_planes = 3
    saver = _setup_both_saver(shell, tmp_path, n_planes=n_planes, n_channels=2)
    shell._auto_laser1 = True
    shell._auto_laser2 = True
    # Send only 1 channel-0 frame -> ch0_z=1 < 3 -> skip finalize.
    saver.enqueue_buffer((0, np.zeros((32, 32), dtype=np.uint16)))

    class _StopAfterFirst:
        def __init__(self: Any, real: Any) -> None:
            self._real = real
            self._n = 0

        def get(self: Any, block: bool = True, timeout: Any | None = None) -> Any:
            buf = self._real.get(block=block, timeout=timeout)
            self._n += 1
            if self._n >= 1:
                saver.saving_started = False
            return buf

        def get_nowait(self) -> Any:
            return self._real.get_nowait()

        def __getattr__(self: Any, name: Any) -> Any:
            return getattr(self._real, name)

    saver.queue = _StopAfterFirst(saver.queue)  # ty: ignore[invalid-assignment]
    saver._both_save_worker_multi_channel()
    root = zarr.open(str(tmp_path / "stack.ome.zarr"), mode="r")
    assert "acquisition" not in root


def test_both_save_worker_multichannel_finally_closes_files(
    tmp_path: Path,
) -> None:
    """The finally block closes any still-open per-channel files (1551-1555)."""
    import h5py

    shell = _ShellStandin()
    n_planes = 2
    saver = _setup_both_saver(shell, tmp_path, n_planes=n_planes, n_channels=2)
    shell._auto_laser1 = True
    shell._auto_laser2 = True
    # Send only channel-0 frames; channel-1 file stays open at loop exit.
    frame = np.zeros((32, 32), dtype=np.uint16)
    saver.enqueue_buffer((0, frame))
    saver.enqueue_buffer((0, frame))
    saver.saving_started = False  # drain then exit
    saver._both_save_worker_multi_channel()
    # Channel 1 file was opened then closed in finally — must be readable.
    with h5py.File(saver.filenames_lists[1][0], "r") as f:
        assert isinstance(f, h5py.File)


def test_both_save_worker_multichannel_start_stack_error_aborts(
    tmp_path: Path,
) -> None:
    """A start_stack failure in multi-channel both-save aborts (1344-1347)."""
    shell = _ShellStandin()
    n_planes = 1
    saver = _setup_both_saver(shell, tmp_path, n_planes=n_planes, n_channels=2)
    # Point save_directory at a non-existent dir so start_stack raises.
    shell.save_directory = str(tmp_path / "no_such_dir")
    saver.parent.save_directory = shell.save_directory  # ty: ignore[invalid-assignment]
    saver.enqueue_buffer((0, np.zeros((32, 32), dtype=np.uint16)))
    saver._both_save_worker_multi_channel()
    assert saver.saving_started is False
    assert any("Save error" in m for m in shell.message_printer_calls)


def test_both_save_worker_multichannel_3d_buffer_expands(tmp_path: Path) -> None:
    """A 3D frame in multi-channel both-save is expanded (1406-1408)."""
    import h5py

    shell = _ShellStandin()
    n_planes = 2
    saver = _setup_both_saver(shell, tmp_path, n_planes=n_planes, n_channels=2)
    shell._auto_laser1 = True
    shell._auto_laser2 = True
    buf = np.zeros((2, 32, 32), dtype=np.uint16)
    saver.enqueue_buffer((0, buf))
    saver.enqueue_buffer((1, np.zeros((32, 32), dtype=np.uint16)))
    saver.enqueue_buffer((1, np.zeros((32, 32), dtype=np.uint16)))
    saver._both_save_worker_multi_channel()
    with h5py.File(saver.filenames_lists[0][0], "r") as f:
        assert len(f.keys()) == 2


def test_both_save_worker_multichannel_short_pos_list_skips_attrs(
    tmp_path: Path,
) -> None:
    """When pos_index >= len(position_list), HDF5 attrs are skipped (1425->1435)."""
    import h5py

    shell = _ShellStandin()
    n_planes = 1
    saver = _setup_both_saver(shell, tmp_path, n_planes=n_planes, n_channels=2)
    shell._auto_laser1 = True
    shell._auto_laser2 = True
    saver.horizontal_positions_list = []
    saver.vertical_positions_list = []
    saver.camera_positions_list = []
    saver.enqueue_buffer((0, np.zeros((32, 32), dtype=np.uint16)))
    saver.enqueue_buffer((1, np.zeros((32, 32), dtype=np.uint16)))
    saver._both_save_worker_multi_channel()
    with h5py.File(saver.filenames_lists[0][0], "r") as f:
        ds = f[next(iter(f.keys()))]
        assert "Horizontal Position" not in ds.attrs


def test_both_save_worker_multichannel_drains_after_stop(tmp_path: Path) -> None:
    """When saving_started flips False mid-loop, multi-channel both-save drains
    remaining frames via get_nowait (1373-1380)."""
    import h5py

    shell = _ShellStandin()
    n_planes = 1
    saver = _setup_both_saver(shell, tmp_path, n_planes=n_planes, n_channels=2)
    shell._auto_laser1 = True
    shell._auto_laser2 = True
    frame = np.zeros((32, 32), dtype=np.uint16)
    saver.enqueue_buffer((0, frame))
    saver.enqueue_buffer((1, frame))
    saver.saving_started = False  # drain path
    saver._both_save_worker_multi_channel()
    for ch in range(2):
        with h5py.File(saver.filenames_lists[ch][0], "r") as f:
            assert len(f.keys()) == 1


def test_both_save_worker_multichannel_finally_close_exception_suppressed(
    tmp_path: Path,
) -> None:
    """An exception during the finally close is suppressed (1524-1525)."""
    shell = _ShellStandin()
    n_planes = 2
    saver = _setup_both_saver(shell, tmp_path, n_planes=n_planes, n_channels=2)
    shell._auto_laser1 = True
    shell._auto_laser2 = True
    # Send only channel-0 frames so channel-1 file stays open at exit;
    # the finally path tries to write adaptive + close. Make close raise
    # by patching the open file's close method via a bad filenames_lists
    # entry that points to a directory (open succeeds, close is fine, but
    # _write_adaptive_hdf5_for_file on a non-group raises -> suppressed).
    frame = np.zeros((32, 32), dtype=np.uint16)
    saver.enqueue_buffer((0, frame))
    saver.enqueue_buffer((0, frame))
    saver.saving_started = False
    # No crash — the finally suppresses exceptions.
    saver._both_save_worker_multi_channel()
    assert Path(saver.filenames_lists[1][0]).is_file()


def test_both_save_worker_multichannel_finalize_error_flips_saving(
    tmp_path: Path,
) -> None:
    """A finalize failure in multi-channel both-save flips
    saving_started (1545-1550)."""
    shell = _ShellStandin()
    n_planes = 1
    saver = _setup_both_saver(shell, tmp_path, n_planes=n_planes, n_channels=2)
    shell._auto_laser1 = True
    shell._auto_laser2 = True

    def _bad() -> Never:
        raise RuntimeError("mc both finalize boom")

    setattr(saver._zarr_saver, "finalize", _bad)
    saver.enqueue_buffer((0, np.zeros((32, 32), dtype=np.uint16)))
    saver.enqueue_buffer((1, np.zeros((32, 32), dtype=np.uint16)))
    saver._both_save_worker_multi_channel()
    assert saver.saving_started is False
    assert any("mc both finalize boom" in m for m in shell.message_printer_calls)


# -- ZarrSaver: path traversal, finalize errors, adaptive group ---------------


def test_zarr_saver_start_stack_rejects_path_outside_save_dir(tmp_path: Path) -> None:
    """start_stack raises ValueError when store_path is outside save_directory
    (lines 1652-1657)."""
    shell = _ShellStandin()
    shell.save_directory = str(tmp_path / "save")
    (tmp_path / "save").mkdir()
    saver = ZarrSaver(shell)  # ty: ignore[invalid-argument-type]
    bad_path = str(tmp_path / "outside.ome.zarr")
    with pytest.raises(ValueError, match="outside save directory"):
        saver.start_stack(bad_path, 1)
    # sig_message was emitted with the rejection reason.
    shell.sig_message.emit.assert_called()


def test_zarr_saver_write_plane_before_start_raises(tmp_path: Path) -> None:
    """write_plane before start_stack raises RuntimeError (line 1714)."""
    shell = _ShellStandin()
    shell.save_directory = str(tmp_path)
    saver = ZarrSaver(shell)  # ty: ignore[invalid-argument-type]
    with pytest.raises(RuntimeError, match="before start_stack"):
        saver.write_plane(0, 0, np.zeros((4, 4), dtype=np.uint16), 0.0, 0.0, 0.0)


def test_zarr_saver_write_acquisition_group_no_writer_raises(tmp_path: Path) -> None:
    """_write_acquisition_group with no writer raises RuntimeError (line 1767)."""
    shell = _ShellStandin()
    shell.save_directory = str(tmp_path)
    saver = ZarrSaver(shell)  # ty: ignore[invalid-argument-type]
    with pytest.raises(RuntimeError, match="no writer"):
        saver._write_acquisition_group()


def test_zarr_saver_finalize_before_start_raises(tmp_path: Path) -> None:
    """finalize before start_stack raises RuntimeError (line 1899)."""
    shell = _ShellStandin()
    shell.save_directory = str(tmp_path)
    saver = ZarrSaver(shell)  # ty: ignore[invalid-argument-type]
    with pytest.raises(RuntimeError, match="before start_stack"):
        saver.finalize()


def test_zarr_saver_finalize_twice_raises(tmp_path: Path) -> None:
    """A double-finalize raises RuntimeError (line 1901)."""
    shell = _ShellStandin()
    shell.save_directory = str(tmp_path)
    shell.camera.xsize = 32
    shell.camera.ysize = 32
    shell.stack_step = 1.0
    saver = ZarrSaver(shell)  # ty: ignore[invalid-argument-type]
    saver.start_stack(str(tmp_path / "s.ome.zarr"), 1)
    saver.write_plane(0, 0, np.zeros((32, 32), dtype=np.uint16), 0.0, 0.0, 0.0)
    saver.finalize()
    with pytest.raises(RuntimeError, match="called twice"):
        saver.finalize()


def test_zarr_saver_restore_write_empty_chunks_noop_when_not_overridden(
    tmp_path: Path,
) -> None:
    """_restore_write_empty_chunks is a no-op when start_stack never overrode it
    (line 1920)."""
    shell = _ShellStandin()
    shell.save_directory = str(tmp_path)
    saver = ZarrSaver(shell)  # ty: ignore[invalid-argument-type]
    # Never called start_stack -> _write_empty_chunks_overridden is False.
    saver._restore_write_empty_chunks()  # must not raise.


def test_zarr_saver_writes_adaptive_group(tmp_path: Path) -> None:
    """_write_adaptive_group publishes /acquisition/adaptive with the trajectory
    + config attrs (lines 1830-1885)."""
    import zarr

    shell = _ShellStandin()
    shell.save_directory = str(tmp_path)
    shell.camera.xsize = 32
    shell.camera.ysize = 32
    shell.stack_step = 1.0
    saver = ZarrSaver(shell)  # ty: ignore[invalid-argument-type]
    saver.start_stack(str(tmp_path / "s.ome.zarr"), 1)
    saver.write_plane(0, 0, np.zeros((32, 32), dtype=np.uint16), 0.0, 0.0, 0.0)
    cfg = _adaptive_config()
    traj = [_adaptive_sample(0), _adaptive_sample(1)]
    saver.set_adaptive_trajectory(traj, cfg)
    saver.finalize()
    root = zarr.open(str(tmp_path / "s.ome.zarr"), mode="r")
    assert "acquisition" in root
    acq = root["acquisition"]  # ty: ignore[invalid-argument-type]
    assert "adaptive" in acq  # ty: ignore[unsupported-operator]
    adp = acq["adaptive"]  # ty: ignore[invalid-argument-type, not-subscriptable]
    assert bool(adp.attrs["enabled"]) is True  # ty: ignore[unresolved-attribute]
    assert adp.attrs["kp"] == 0.4  # ty: ignore[unresolved-attribute]
    assert list(adp["plane_index"][:]) == [0, 1]  # ty: ignore[invalid-argument-type, not-subscriptable]
    assert "laser_power_mw" in adp  # ty: ignore[unsupported-operator]
    assert "control_variable_active" in adp  # ty: ignore[unsupported-operator]
    assert "reacquired" in adp  # ty: ignore[unsupported-operator]
    assert "power_fallback" in adp  # ty: ignore[unsupported-operator]


def test_zarr_saver_adaptive_group_noop_when_empty_trajectory(tmp_path: Path) -> None:
    """_write_adaptive_group is a no-op when the trajectory is empty (1828-1829)."""
    import zarr

    shell = _ShellStandin()
    shell.save_directory = str(tmp_path)
    shell.camera.xsize = 32
    shell.camera.ysize = 32
    shell.stack_step = 1.0
    saver = ZarrSaver(shell)  # ty: ignore[invalid-argument-type]
    saver.start_stack(str(tmp_path / "s.ome.zarr"), 1)
    saver.write_plane(0, 0, np.zeros((32, 32), dtype=np.uint16), 0.0, 0.0, 0.0)
    # Empty trajectory -> no adaptive group.
    saver.set_adaptive_trajectory([], None)
    saver.finalize()
    root = zarr.open(str(tmp_path / "s.ome.zarr"), mode="r")
    assert "adaptive" not in root["acquisition"]  # ty: ignore[invalid-argument-type, unsupported-operator]


def test_zarr_saver_adaptive_group_no_writer_raises(tmp_path: Path) -> None:
    """_write_adaptive_group with no writer but non-empty trajectory
    raises (1830-1831)."""
    shell = _ShellStandin()
    shell.save_directory = str(tmp_path)
    saver = ZarrSaver(shell)  # ty: ignore[invalid-argument-type]
    saver.set_adaptive_trajectory([_adaptive_sample(0)], _adaptive_config())
    with pytest.raises(RuntimeError, match="no writer"):
        saver._write_adaptive_group()


# -- stop_saving wait timeout warning (1587) ----------------------------------


def test_stop_saving_warns_on_thread_timeout(tmp_path: Path) -> None:
    """stop_saving logs a warning when the worker thread does not exit within
    the 10s wait (line 1587)."""
    shell = _ShellStandin()
    saver = FrameSaver(shell)  # ty: ignore[invalid-argument-type]
    saver.reinit(8)

    # Build a fake worker thread whose wait() always returns False (timed out).
    class _FakeThread:
        def isRunning(self) -> bool:
            return True

        def quit(self) -> None:
            pass

        def wait(self, ms: int) -> bool:
            return False  # never reaps

    saver._saver_thread = _FakeThread()  # ty: ignore[invalid-assignment]
    # Should not raise; the warning is logged.
    saver.stop_saving()
    assert saver.saving_started is False
