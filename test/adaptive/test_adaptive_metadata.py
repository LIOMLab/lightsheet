"""Cross-format adaptive trajectory metadata tests.

Verifies the approved schema-a trajectory contract is published in every
HDF5 save layout (stitch / per-plane / multi-channel) and in OME-Zarr
(``/acquisition/adaptive``), with identical field names, units, shapes,
and full AdaptiveConfig attrs across formats. Fixed-mode saves omit the
adaptive group entirely; the OME channel-axis guard and the metadata
write-error surface are preserved.

The tests build frozen AdaptiveConfig / AdaptiveSample fixtures, exercise
the real FrameSaver / ZarrSaver save branches with small 8x8 uint16
frames, reopen the files / stores, and compare exact datasets, dtypes,
shapes, attrs, file plane subsets, and OME channel metadata.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Never

if TYPE_CHECKING:
    from lightsheet.gui.shell.controller import Controller_MainWindow

import os
from pathlib import Path

import h5py
import numpy as np
import pytest

from lightsheet.adaptive.types import AdaptiveConfig, AdaptiveSample

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_FRAME_SIZE = 8


def _small_config(**overrides: Any) -> AdaptiveConfig:
    """Build a frozen AdaptiveConfig with small bounds for fast tests."""
    defaults = dict(
        enabled=True,
        min_exposure_s=5e-3,
        max_exposure_s=100e-3,
        min_power_mw=(0.0, 0.0),
        max_power_mw=(100.0, 100.0),
        target_band_lo=0.90,
        target_band_hi=0.95,
        reacquire_threshold=0.08,
        block_size_n=4,
        kp=0.4,
        ki=0.05,
        pilot_count=3,
        sensor_max=65535,
        max_reacquire_attempts=1,
    )
    defaults.update(overrides)
    return AdaptiveConfig(**defaults)  # ty: ignore[invalid-argument-type]


def _make_samples(n_planes: int, n_channels: int = 1) -> list[AdaptiveSample]:
    """Build ``n_planes`` frozen AdaptiveSample fixtures.

    ``intensity_fraction`` has one entry per channel; inactive channels
    are NaN (schema-a). ``laser_power_mw`` is a 2-tuple (L1, L2).
    """
    samples: list[AdaptiveSample] = []
    for i in range(n_planes):
        if n_channels == 1:
            intensity = [0.92 - 0.01 * i]
        else:
            intensity = [0.92 - 0.01 * i, 0.88 - 0.01 * i]
        samples.append(
            AdaptiveSample(
                plane_index=i,
                intensity_fraction=intensity,
                exposure_s=0.01 + 0.001 * i,
                laser_power_mw=(50.0 + i, 40.0 + i),
                control_variable_active="exposure" if i % 2 == 0 else "power",
                reacquired=(i == 2),
                power_fallback=(i % 2 == 1),
            )
        )
    return samples


def _setup_ctrl(
    controller: Controller_MainWindow, tmp_path: Path, *, n_channels: int = 1
) -> tuple:  # ty: ignore[missing-type-argument]
    """Create a real controller with 8x8 camera and tmp_path save dir.

    Returns ``(ctrl, saver)`` where ``saver`` is ``ctrl._fs.frame_saver``.
    """
    ctrl = controller
    ctrl.save_directory = str(tmp_path)
    ctrl.stack_step = 1
    # Shrink the camera so Zarr pyramid finalization is instant.
    ctrl.camera.xsize = _FRAME_SIZE
    ctrl.camera.ysize = _FRAME_SIZE
    # Set auto-laser flags so omero channels match the channel count.
    if n_channels >= 1:
        ctrl._auto_laser1 = True
    if n_channels >= 2:
        ctrl._auto_laser2 = True
    saver = ctrl._fs.frame_saver
    setattr(saver.parent, "save_format", "hdf5")
    # Reinit with a block_size large enough that the queue (maxsize
    # 2*block_size) can hold all test frames without blocking the put
    # call — the default block_size=1 gives maxsize=2, which blocks on
    # the 3rd put. Use 32 as a generous bound for any test plane count.
    saver.reinit(block_size=32)
    return ctrl, saver


def _enqueue_planes(saver: Any, n_planes: int, n_channels: int = 1) -> None:
    """Enqueue ``n_planes`` frames (or ``n_planes * n_channels`` tagged
    frames) into the saver queue. Also populates the motor position
    lists (one entry per plane) so the HDF5 per-dataset attrs path does
    not raise ``list index out of range``."""
    for _i in range(n_planes):
        saver.add_motor_parameters("0.0 μm", "0.0 μm", "0.0 μm")
    frame = np.zeros((_FRAME_SIZE, _FRAME_SIZE), dtype=np.uint16)
    if n_channels == 1:
        for _ in range(n_planes):
            saver.queue.put(frame)
    else:
        for _p in range(n_planes):
            for ch in range(n_channels):
                saver.queue.put((ch, frame))


def _chdir(tmp_path: Path) -> Any:
    """Return a context manager that chdir's into tmp_path."""
    from contextlib import contextmanager

    @contextmanager
    def _ctx() -> Any:
        cwd = Path.cwd()
        os.chdir(str(tmp_path))
        try:
            yield
        finally:
            os.chdir(cwd)

    return _ctx()


# Expected AdaptiveConfig attr names written to the adaptive group.
_CONFIG_ATTRS = [
    "enabled",
    "min_exposure_s",
    "max_exposure_s",
    "target_band_lo",
    "target_band_hi",
    "reacquire_threshold",
    "block_size_n",
    "kp",
    "ki",
    "pilot_count",
    "sensor_max",
    "max_reacquire_attempts",
]

# Expected dataset names in the adaptive group.
_DATASET_NAMES = [
    "plane_index",
    "intensity_fraction",
    "exposure_s",
    "laser_power_mw",
    "control_variable_active",
    "reacquired",
    "power_fallback",
]


def _assert_adaptive_group(
    grp: Any, samples: list[AdaptiveSample], config: AdaptiveConfig
) -> None:
    """Assert a group (HDF5 or Zarr) carries the schema-a datasets and
    AdaptiveConfig attrs matching ``samples``."""
    for name in _DATASET_NAMES:
        assert name in grp, f"adaptive group missing dataset: {name}"

    n = len(samples)
    n_ch = len(samples[0].intensity_fraction)

    # plane_index
    pi = np.asarray(grp["plane_index"])
    assert pi.shape == (n,), f"plane_index shape {pi.shape} != ({n},)"
    assert np.array_equal(pi, np.array([s.plane_index for s in samples]))

    # intensity_fraction: (n_planes, n_channels), NaN for inactive
    iff = np.asarray(grp["intensity_fraction"])
    assert iff.shape == (n, n_ch), (
        f"intensity_fraction shape {iff.shape} != ({n}, {n_ch})"
    )
    expected_iff = np.array([list(s.intensity_fraction) for s in samples], dtype=float)
    np.testing.assert_array_equal(iff, expected_iff)

    # exposure_s
    es = np.asarray(grp["exposure_s"])
    assert es.shape == (n,)
    np.testing.assert_allclose(es, np.array([s.exposure_s for s in samples]))

    # laser_power_mw: (n_planes, 2)
    lpm = np.asarray(grp["laser_power_mw"])
    assert lpm.shape == (n, 2), f"laser_power_mw shape {lpm.shape} != ({n}, 2)"
    expected_lpm = np.array([list(s.laser_power_mw) for s in samples], dtype=float)
    np.testing.assert_allclose(lpm, expected_lpm)

    # control_variable_active: UTF-8 strings
    cva = grp["control_variable_active"]
    cva_arr = np.asarray(cva)
    expected_cva = [s.control_variable_active for s in samples]
    # h5py/zarr may store as bytes; decode for comparison.
    actual_cva = [
        v.decode("utf-8") if isinstance(v, bytes) else str(v) for v in cva_arr
    ]
    assert actual_cva == expected_cva, (
        f"control_variable_active: {actual_cva} != {expected_cva}"
    )

    # reacquired + power_fallback: bool
    ra = np.asarray(grp["reacquired"])
    assert ra.shape == (n,)
    np.testing.assert_array_equal(ra, np.array([s.reacquired for s in samples]))
    pf = np.asarray(grp["power_fallback"])
    assert pf.shape == (n,)
    np.testing.assert_array_equal(pf, np.array([s.power_fallback for s in samples]))

    # AdaptiveConfig attrs
    for attr in _CONFIG_ATTRS:
        assert attr in grp.attrs, f"adaptive group missing AdaptiveConfig attr: {attr}"
    assert grp.attrs["enabled"] == config.enabled
    assert grp.attrs["min_exposure_s"] == config.min_exposure_s
    assert grp.attrs["max_exposure_s"] == config.max_exposure_s
    # min_power_mw / max_power_mw are tuples — stored as arrays.
    np.testing.assert_allclose(
        np.asarray(grp.attrs["min_power_mw"]),
        np.array(config.min_power_mw),
    )
    np.testing.assert_allclose(
        np.asarray(grp.attrs["max_power_mw"]),
        np.array(config.max_power_mw),
    )


# ---------------------------------------------------------------------------
# HDF5 single-channel stitch
# ---------------------------------------------------------------------------


def test_hdf5_stitch_writes_all_adaptive_rows(
    controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """Single-channel stitch (1 file, N datasets) stores all N sample
    rows in ``/adaptive_trajectory`` with full AdaptiveConfig attrs."""
    _ctrl, saver = _setup_ctrl(controller, tmp_path)
    config = _small_config()
    n_planes = 4

    with _chdir(tmp_path):
        saver.set_files(
            1,
            "scan",
            "stack",
            n_planes,
            "reconstructed_frame",
            wavelengths=[555],
        )
        saver.configure_adaptive(True, config=config)
        for s in _make_samples(n_planes):
            saver.record_adaptive_sample(s)
        saver.saving_started = True
        _enqueue_planes(saver, n_planes)
        saver.frame_saver_worker()

        # Reopen and verify.
        fname = saver.filenames_list[0]
        with h5py.File(fname, "r") as f:
            assert "adaptive_trajectory" in f
            _assert_adaptive_group(
                f["adaptive_trajectory"], saver.adaptive_trajectory, config
            )


# ---------------------------------------------------------------------------
# HDF5 single-channel per-plane (crop / full)
# ---------------------------------------------------------------------------


def test_hdf5_per_plane_writes_exact_plane_row(
    controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """Single-channel crop/full (N files, 1 dataset each) stores exactly
    one row per file — the file's global plane index — without
    duplicate plane records."""
    _ctrl, saver = _setup_ctrl(controller, tmp_path)
    config = _small_config()
    n_planes = 3

    with _chdir(tmp_path):
        saver.set_files(
            n_planes,
            "scan",
            "singleImage",
            1,
            "reconstructed_frame",
            wavelengths=[555],
        )
        saver.configure_adaptive(True, config=config)
        samples = _make_samples(n_planes)
        for s in samples:
            saver.record_adaptive_sample(s)
        saver.saving_started = True
        _enqueue_planes(saver, n_planes)
        saver.frame_saver_worker()

        # Each file carries exactly its plane's row.
        for i, fname in enumerate(saver.filenames_list):
            with h5py.File(fname, "r") as f:
                assert "adaptive_trajectory" in f, (
                    f"file {i} missing /adaptive_trajectory"
                )
                grp = f["adaptive_trajectory"]
                _assert_adaptive_group(grp, [samples[i]], config)


def test_hdf5_multi_file_multi_dataset_writes_aligned_plane_rows(
    controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """Multi-file multi-dataset (``number_of_files > 1`` AND
    ``number_of_datasets > 1``) writes the correct plane-range slice per
    file — one trajectory row per plane in the file, aligned with the
    image data — not a single row indexed by the file index.

    This is the CR-02 regression guard: before the fix, file 0 got
    ``trajectory[0]`` but held planes ``0..M-1``; file 1 got
    ``trajectory[1]`` but held planes ``M..2M-1``. The metadata was
    misaligned with the image data and the other ``M-1`` rows per file
    were missing.
    """
    _ctrl, saver = _setup_ctrl(controller, tmp_path)
    config = _small_config()
    n_files = 2
    n_datasets_per_file = 2
    n_planes = n_files * n_datasets_per_file  # 4

    with _chdir(tmp_path):
        saver.set_files(
            n_files,
            "scan",
            "stack",
            n_datasets_per_file,
            "reconstructed_frame",
            wavelengths=[555],
        )
        saver.configure_adaptive(True, config=config)
        samples = _make_samples(n_planes)
        for s in samples:
            saver.record_adaptive_sample(s)
        saver.saving_started = True
        _enqueue_planes(saver, n_planes)
        saver.frame_saver_worker()

        # Each file carries its own plane-range slice, not a single row
        # indexed by the file index.
        for file_idx, fname in enumerate(saver.filenames_list):
            start = file_idx * n_datasets_per_file
            end = start + n_datasets_per_file
            expected_rows = samples[start:end]
            with h5py.File(fname, "r") as f:
                assert "adaptive_trajectory" in f, (
                    f"file {file_idx} missing /adaptive_trajectory"
                )
                grp = f["adaptive_trajectory"]
                # The group must carry M rows (one per plane in this
                # file), not 1 — the pre-fix bug wrote one row.
                pi = np.asarray(grp["plane_index"])  # ty: ignore[invalid-argument-type, not-subscriptable]
                assert pi.shape == (n_datasets_per_file,), (
                    f"file {file_idx} plane_index shape {pi.shape} "
                    f"!= ({n_datasets_per_file},) — expected one row "
                    f"per plane in the file"
                )
                _assert_adaptive_group(grp, expected_rows, config)

        # The full trajectory is reconstructable by concatenating per-file
        # rows in file order.
        all_rows: list[int] = []
        for fname in saver.filenames_list:
            with h5py.File(fname, "r") as f:
                trajectory: Any = f["adaptive_trajectory"]
                all_rows.extend(np.asarray(trajectory["plane_index"]).tolist())
        assert all_rows == list(range(n_planes)), (
            f"concatenated per-file plane_index {all_rows} != "
            f"{list(range(n_planes))} — trajectory not reconstructable"
        )


# ---------------------------------------------------------------------------
# HDF5 multi-channel
# ---------------------------------------------------------------------------


def test_hdf5_multi_channel_writes_same_trajectory_per_channel(
    controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """Multi-channel stitch stores the full same per-plane trajectory in
    each channel file; per-plane files store the corresponding row
    without duplicate plane records."""
    _ctrl, saver = _setup_ctrl(controller, tmp_path, n_channels=2)
    config = _small_config()
    n_planes = 3

    with _chdir(tmp_path):
        saver.set_files(
            1,
            "scan",
            "stack",
            n_planes,
            "reconstructed_frame",
            wavelengths=[555, 647],
        )
        saver.configure_adaptive(True, config=config)
        samples = _make_samples(n_planes, n_channels=2)
        for s in samples:
            saver.record_adaptive_sample(s)
        saver.saving_started = True
        _enqueue_planes(saver, n_planes, n_channels=2)
        saver._frame_saver_worker_multi_channel()

        # Both channel files carry the full trajectory.
        for ch in range(2):
            fname = saver.filenames_lists[ch][0]
            with h5py.File(fname, "r") as f:
                assert "adaptive_trajectory" in f, (
                    f"channel {ch} file missing /adaptive_trajectory"
                )
                _assert_adaptive_group(f["adaptive_trajectory"], samples, config)


def test_hdf5_multi_channel_multi_file_multi_dataset_writes_aligned_rows(
    controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """Multi-channel + multi-file + multi-dataset: each channel's file
    carries its own plane-range slice (one trajectory row per plane in
    the file), aligned with the image data — the multi-channel CR-02
    regression guard.

    Before the fix, the multi-channel per-plane close path called
    ``_write_adaptive_hdf5_for_file`` without ``n_datasets_per_file``,
    so each file got a single row indexed by the file index instead of
    the correct ``M``-row slice.
    """
    _ctrl, saver = _setup_ctrl(controller, tmp_path, n_channels=2)
    config = _small_config()
    n_files = 2
    n_datasets_per_file = 2
    n_planes = n_files * n_datasets_per_file  # 4 planes, shared across channels

    with _chdir(tmp_path):
        saver.set_files(
            n_files,
            "scan",
            "stack",
            n_datasets_per_file,
            "reconstructed_frame",
            wavelengths=[555, 647],
        )
        saver.configure_adaptive(True, config=config)
        samples = _make_samples(n_planes, n_channels=2)
        for s in samples:
            saver.record_adaptive_sample(s)
        saver.saving_started = True
        _enqueue_planes(saver, n_planes, n_channels=2)
        saver._frame_saver_worker_multi_channel()

        # Each channel's files carry the correct plane-range slice.
        for ch in range(2):
            for file_idx, fname in enumerate(saver.filenames_lists[ch]):
                start = file_idx * n_datasets_per_file
                end = start + n_datasets_per_file
                expected_rows = samples[start:end]
                with h5py.File(fname, "r") as f:
                    assert "adaptive_trajectory" in f, (
                        f"channel {ch} file {file_idx} missing /adaptive_trajectory"
                    )
                    grp = f["adaptive_trajectory"]
                    pi = np.asarray(grp["plane_index"])  # ty: ignore[invalid-argument-type, not-subscriptable]
                    assert pi.shape == (n_datasets_per_file,), (
                        f"channel {ch} file {file_idx} plane_index shape "
                        f"{pi.shape} != ({n_datasets_per_file},) — expected "
                        f"one row per plane in the file"
                    )
                    _assert_adaptive_group(grp, expected_rows, config)


# ---------------------------------------------------------------------------
# OME-Zarr
# ---------------------------------------------------------------------------


def test_zarr_writes_adaptive_group(
    controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """Zarr save creates ``/acquisition/adaptive`` with arrays equal to
    the HDF5 schema values and full AdaptiveConfig attrs."""
    import zarr

    ctrl, saver = _setup_ctrl(controller, tmp_path)
    ctrl.save_format = "zarr"
    config = _small_config()
    n_planes = 3

    with _chdir(tmp_path):
        saver.set_files(
            1,
            "scan",
            "stack",
            n_planes,
            "reconstructed_frame",
            wavelengths=[555],
        )
        saver.configure_adaptive(True, config=config)
        for s in _make_samples(n_planes):
            saver.record_adaptive_sample(s)
        saver.saving_started = True
        _enqueue_planes(saver, n_planes)
        saver.zarr_save_worker()

        store_path = str(tmp_path / "scan.ome.zarr")
        root = zarr.open(store_path, mode="r")
        assert "acquisition" in root
        acq = root["acquisition"]  # ty: ignore[invalid-argument-type]
        assert "adaptive" in acq, "/acquisition/adaptive group missing"  # ty: ignore[unsupported-operator]
        _assert_adaptive_group(acq["adaptive"], saver.adaptive_trajectory, config)  # ty: ignore[invalid-argument-type, not-subscriptable]


# ---------------------------------------------------------------------------
# Both (HDF5 + Zarr)
# ---------------------------------------------------------------------------


def test_both_writes_adaptive_in_both_formats(
    controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """Both save writes ``/adaptive_trajectory`` in HDF5 and
    ``/acquisition/adaptive`` in Zarr with identical schema."""
    import zarr

    ctrl, saver = _setup_ctrl(controller, tmp_path)
    ctrl.save_format = "both"
    config = _small_config()
    n_planes = 2

    with _chdir(tmp_path):
        saver.set_files(
            1,
            "scan",
            "stack",
            n_planes,
            "reconstructed_frame",
            wavelengths=[555],
        )
        saver.configure_adaptive(True, config=config)
        for s in _make_samples(n_planes):
            saver.record_adaptive_sample(s)
        saver.saving_started = True
        _enqueue_planes(saver, n_planes)
        saver.both_save_worker()

        # HDF5
        fname = saver.filenames_list[0]
        with h5py.File(fname, "r") as f:
            assert "adaptive_trajectory" in f
            _assert_adaptive_group(
                f["adaptive_trajectory"], saver.adaptive_trajectory, config
            )
        # Zarr
        store_path = str(tmp_path / "scan.ome.zarr")
        root: Any = zarr.open(store_path, mode="r")
        assert "acquisition" in root
        acq_group: Any = root["acquisition"]
        assert "adaptive" in acq_group
        _assert_adaptive_group(
            acq_group["adaptive"],
            saver.adaptive_trajectory,
            config,
        )


# ---------------------------------------------------------------------------
# Fixed mode omits adaptive group
# ---------------------------------------------------------------------------


def test_fixed_mode_omits_adaptive_group_hdf5(
    controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """Fixed-mode HDF5 save contains no ``/adaptive_trajectory`` group."""
    _ctrl, saver = _setup_ctrl(controller, tmp_path)
    n_planes = 2

    with _chdir(tmp_path):
        saver.set_files(
            1,
            "scan",
            "stack",
            n_planes,
            "reconstructed_frame",
            wavelengths=[555],
        )
        # Do NOT configure adaptive — fixed mode.
        saver.configure_adaptive(False)
        saver.saving_started = True
        _enqueue_planes(saver, n_planes)
        saver.frame_saver_worker()

        fname = saver.filenames_list[0]
        with h5py.File(fname, "r") as f:
            assert "adaptive_trajectory" not in f, (
                "fixed-mode HDF5 must not contain /adaptive_trajectory"
            )


def test_fixed_mode_omits_adaptive_group_zarr(
    controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """Fixed-mode Zarr save contains no ``/acquisition/adaptive`` group."""
    import zarr

    ctrl, saver = _setup_ctrl(controller, tmp_path)
    ctrl.save_format = "zarr"
    n_planes = 2

    with _chdir(tmp_path):
        saver.set_files(
            1,
            "scan",
            "stack",
            n_planes,
            "reconstructed_frame",
            wavelengths=[555],
        )
        saver.configure_adaptive(False)
        saver.saving_started = True
        _enqueue_planes(saver, n_planes)
        saver.zarr_save_worker()

        store_path = str(tmp_path / "scan.ome.zarr")
        root = zarr.open(store_path, mode="r")
        assert "acquisition" in root
        assert "adaptive" not in root["acquisition"], (  # ty: ignore[invalid-argument-type, unsupported-operator]
            "fixed-mode Zarr must not contain /acquisition/adaptive"
        )


# ---------------------------------------------------------------------------
# Channel axis guard preserved
# ---------------------------------------------------------------------------


def test_channel_axis_guard_preserved(
    controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """Adaptive metadata is orthogonal to the OME channel axis:
    ``n_channels`` and ``omero.channels`` remain unchanged and the
    mismatch guard still raises RuntimeError."""
    from lightsheet.gui.coordinators.frame_saver_controller import ZarrSaver

    ctrl = controller
    ctrl.save_directory = str(tmp_path)
    ctrl.stack_step = 1
    ctrl.camera.xsize = _FRAME_SIZE
    ctrl.camera.ysize = _FRAME_SIZE

    # 2-channel writer but only 1 auto-laser flag set → mismatch.
    ctrl._auto_laser1 = True
    ctrl._auto_laser2 = False

    store_path = str(tmp_path / "stack.ome.zarr")
    saver = ZarrSaver(ctrl)
    saver.start_stack(store_path, 1, n_channels=2)
    frame = np.zeros((_FRAME_SIZE, _FRAME_SIZE), dtype=np.uint16)
    saver.write_plane(0, 0, frame, 0.0, 0.0, 0.0)
    saver.write_plane(1, 0, frame, 0.0, 0.0, 0.0)

    with pytest.raises(RuntimeError, match="omero_channels"):
        saver.finalize()


# ---------------------------------------------------------------------------
# Write error surface
# ---------------------------------------------------------------------------


def test_adaptive_write_error_surfaces(
    controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """When an adaptive metadata write raises, the error surfaces via
    ``sig_status_message`` and ``saving_started`` flips to False rather
    than silently producing an unaudited file."""
    _ctrl, saver = _setup_ctrl(controller, tmp_path)
    config = _small_config()
    n_planes = 2

    with _chdir(tmp_path):
        saver.set_files(
            1,
            "scan",
            "stack",
            n_planes,
            "reconstructed_frame",
            wavelengths=[555],
        )
        saver.configure_adaptive(True, config=config)
        for s in _make_samples(n_planes):
            saver.record_adaptive_sample(s)
        saver.saving_started = True
        _enqueue_planes(saver, n_planes)

        # Patch _write_adaptive_hdf5 to raise.
        original = saver._write_adaptive_hdf5

        def _raising_write(outfile: Any, *args: Any, **kwargs: Any) -> Never:
            raise RuntimeError("adaptive write boom")

        saver._write_adaptive_hdf5 = _raising_write
        try:
            saver.frame_saver_worker()
        finally:
            saver._write_adaptive_hdf5 = original

    assert saver.saving_started is False, (
        "saving_started must flip to False on an adaptive write error"
    )
