"""Cross-format focus trajectory metadata tests.

Verifies the approved 11-01 focus-trajectory schema is published in every
HDF5 save layout and in OME-Zarr (``/acquisition/focus``), with identical
field names, units, shapes, and full FocusConfig attrs across formats.
Fixed-mode saves omit the focus group entirely.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from lightsheet.gui.shell.controller import Controller_MainWindow

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import h5py
import numpy as np
import pytest

from lightsheet.focus.types import AutofocusConfig, FocusConfig, FocusSample

_FRAME_SIZE = 8


def _small_config(**overrides: Any) -> FocusConfig:
    """Build a frozen FocusConfig with small bounds for fast tests."""
    defaults: dict[str, Any] = dict(
        enabled=True,
        block_size_n=8,
        autofocus_residual=True,
        curve_path="",
        residual_gain_mm=0.05,
        max_residual_mm=0.5,
    )
    defaults.update(overrides)
    return FocusConfig(**defaults)


def _make_samples(n_blocks: int) -> list[FocusSample]:
    """Build ``n_blocks`` frozen FocusSample fixtures."""
    samples: list[FocusSample] = []
    for b in range(n_blocks):
        sharpness = None if b == 0 else 0.1 + 0.01 * b
        samples.append(
            FocusSample(
                block_index=b,
                stage_pos_mm=0.01 * b,
                feedforward_camera_pos_mm=20.0 + 0.5 * b,
                residual_mm=0.0 if b == 0 else 0.01 * b,
                applied_camera_pos_mm=20.0 + 0.5 * b + (0.0 if b == 0 else 0.01 * b),
                sharpness_metric=sharpness,
            )
        )
    return samples


def _setup_ctrl(
    controller: Controller_MainWindow, tmp_path: Path, *, n_channels: int = 1
) -> tuple[Any, Any]:
    """Create a real controller with 8x8 camera and tmp_path save dir."""
    ctrl = controller
    ctrl.save_directory = str(tmp_path)
    ctrl.stack_step = 1
    ctrl.camera.xsize = _FRAME_SIZE
    ctrl.camera.ysize = _FRAME_SIZE
    if n_channels >= 1:
        ctrl._auto_laser1 = True
    if n_channels >= 2:
        ctrl._auto_laser2 = True
    saver = ctrl._fs.frame_saver
    parent = cast("Controller_MainWindow", saver.parent)
    parent.save_format = "hdf5"
    saver.reinit(block_size=32)
    return ctrl, saver


def _enqueue_planes(saver: Any, n_planes: int, n_channels: int = 1) -> None:
    """Enqueue ``n_planes`` frames (or ``n_planes * n_channels`` tagged
    frames) into the saver queue and populate motor position lists."""
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


@contextmanager
def _chdir(tmp_path: Path) -> Iterator[None]:
    """Temporarily switch to ``tmp_path``."""
    cwd = Path.cwd()
    os.chdir(str(tmp_path))
    try:
        yield
    finally:
        os.chdir(cwd)


_FOCUS_DATASET_NAMES = [
    "block_index",
    "stage_pos_mm",
    "feedforward_camera_pos_mm",
    "residual_mm",
    "applied_camera_pos_mm",
    "sharpness_metric",
]

_FOCUS_CONFIG_ATTRS = [
    "enabled",
    "block_size_n",
    "autofocus_residual",
    "curve_path",
    "residual_gain_mm",
    "max_residual_mm",
]


def _assert_focus_group(
    grp: Any, samples: list[FocusSample], config: FocusConfig
) -> None:
    """Assert a group (HDF5 or Zarr) carries the schema-a focus datasets
    and FocusConfig attrs matching ``samples``."""
    for name in _FOCUS_DATASET_NAMES:
        assert name in grp, f"focus group missing dataset: {name}"

    n = len(samples)

    bi = np.asarray(grp["block_index"])
    assert bi.shape == (n,)
    assert np.array_equal(bi, np.array([s.block_index for s in samples]))

    sp = np.asarray(grp["stage_pos_mm"])
    assert sp.shape == (n,)
    np.testing.assert_allclose(sp, np.array([s.stage_pos_mm for s in samples]))

    ff = np.asarray(grp["feedforward_camera_pos_mm"])
    assert ff.shape == (n,)
    expected_ff = np.array([s.feedforward_camera_pos_mm for s in samples])
    np.testing.assert_allclose(ff, expected_ff)

    res = np.asarray(grp["residual_mm"])
    assert res.shape == (n,)
    expected_res = np.array([s.residual_mm for s in samples])
    np.testing.assert_allclose(res, expected_res)

    app = np.asarray(grp["applied_camera_pos_mm"])
    assert app.shape == (n,)
    expected_app = np.array([s.applied_camera_pos_mm for s in samples])
    np.testing.assert_allclose(app, expected_app)

    sharp = np.asarray(grp["sharpness_metric"])
    assert sharp.shape == (n,)
    expected_sharp = np.array(
        [
            s.sharpness_metric if s.sharpness_metric is not None else float("nan")
            for s in samples
        ],
        dtype=float,
    )
    # NaN for the first (None) entry; allclose handles NaN as False so
    # compare elementwise with isnan parity.
    for i, (a, e) in enumerate(zip(sharp, expected_sharp, strict=True)):
        if np.isnan(e):
            assert np.isnan(a), f"sharpness_metric[{i}] should be NaN, got {a}"
        else:
            assert a == pytest.approx(e), f"sharpness_metric[{i}] {a} != {e}"

    for attr in _FOCUS_CONFIG_ATTRS:
        assert attr in grp.attrs, f"focus group missing FocusConfig attr: {attr}"
    assert grp.attrs["enabled"] == config.enabled
    assert grp.attrs["block_size_n"] == config.block_size_n
    assert grp.attrs["autofocus_residual"] == config.autofocus_residual
    assert grp.attrs["curve_path"] == config.curve_path
    assert grp.attrs["residual_gain_mm"] == pytest.approx(config.residual_gain_mm)
    assert grp.attrs["max_residual_mm"] == pytest.approx(config.max_residual_mm)


# ---------------------------------------------------------------------------
# HDF5 single-channel stitch
# ---------------------------------------------------------------------------


def test_hdf5_writes_focus_trajectory_group(
    controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """Single-channel stitch writes the full ``/focus_trajectory`` group
    with one row per focus block and the frozen FocusConfig attrs."""
    _ctrl, saver = _setup_ctrl(controller, tmp_path)
    config = _small_config()
    n_blocks = 2
    n_planes = 16

    with _chdir(tmp_path):
        saver.set_files(
            1,
            "scan",
            "stack",
            n_planes,
            "reconstructed_frame",
            wavelengths=[555],
        )
        saver.configure_focus(True, config=config)
        for s in _make_samples(n_blocks):
            saver.record_focus_sample(s)
        saver.saving_started = True
        _enqueue_planes(saver, n_planes)
        saver.frame_saver_worker()

        fname = saver.filenames_list[0]
        with h5py.File(fname, "r") as f:
            assert "focus_trajectory" in f
            _assert_focus_group(f["focus_trajectory"], saver.focus_trajectory, config)


def test_fixed_mode_omits_focus_trajectory_group(
    controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """Fixed-mode HDF5 save contains no ``/focus_trajectory`` group."""
    _ctrl, saver = _setup_ctrl(controller, tmp_path)
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
        saver.configure_focus(False)
        saver.saving_started = True
        _enqueue_planes(saver, n_planes)
        saver.frame_saver_worker()

        fname = saver.filenames_list[0]
        with h5py.File(fname, "r") as f:
            assert "focus_trajectory" not in f, (
                "fixed-mode HDF5 must not contain /focus_trajectory"
            )


# ---------------------------------------------------------------------------
# OME-Zarr
# ---------------------------------------------------------------------------


def test_zarr_focus_group_sibling_of_adaptive(
    controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """When both adaptive and focus are enabled, the Zarr store contains
    both ``/acquisition/adaptive`` and ``/acquisition/focus`` as sibling
    groups with the correct per-block focus rows."""
    import zarr

    from lightsheet.adaptive.types import AdaptiveConfig, AdaptiveSample

    ctrl, saver = _setup_ctrl(controller, tmp_path)
    ctrl.save_format = "zarr"
    focus_config = _small_config()
    adaptive_config = AdaptiveConfig(
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
    n_planes = 4
    n_blocks = 2

    with _chdir(tmp_path):
        saver.set_files(
            1,
            "scan",
            "stack",
            n_planes,
            "reconstructed_frame",
            wavelengths=[555],
        )
        saver.configure_adaptive(True, config=adaptive_config)
        saver.configure_focus(True, config=focus_config)
        for s in _make_samples(n_blocks):
            saver.record_focus_sample(s)
        for i in range(n_planes):
            saver.record_adaptive_sample(
                AdaptiveSample(
                    plane_index=i,
                    intensity_fraction=[0.92],
                    exposure_s=0.01,
                    laser_power_mw=(50.0, 0.0),
                    control_variable_active="exposure",
                    reacquired=False,
                    power_fallback=False,
                )
            )
        saver.saving_started = True
        _enqueue_planes(saver, n_planes)
        saver.zarr_save_worker()

        store_path = str(tmp_path / "scan.ome.zarr")
        root = cast(zarr.Group, zarr.open(store_path, mode="r"))
        assert "acquisition" in root
        acq = cast(zarr.Group, root["acquisition"])
        assert "adaptive" in acq, "/acquisition/adaptive group missing"
        assert "focus" in acq, "/acquisition/focus group missing"
        _assert_focus_group(acq["focus"], saver.focus_trajectory, focus_config)


def test_fixed_mode_omits_focus_group_zarr(
    controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """Fixed-mode Zarr save contains no ``/acquisition/focus`` group."""
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
        saver.configure_focus(False)
        saver.saving_started = True
        _enqueue_planes(saver, n_planes)
        saver.zarr_save_worker()

        store_path = str(tmp_path / "scan.ome.zarr")
        root = cast(zarr.Group, zarr.open(store_path, mode="r"))
        assert "acquisition" in root
        acq = cast(zarr.Group, root["acquisition"])
        assert "focus" not in acq, "fixed-mode Zarr must not contain /acquisition/focus"


# ---------------------------------------------------------------------------
# Both (HDF5 + Zarr)
# ---------------------------------------------------------------------------


def test_both_writes_focus_in_both_formats(
    controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """Both save writes ``/focus_trajectory`` in HDF5 and ``/acquisition/focus``
    in Zarr with identical schema values."""
    import zarr

    ctrl, saver = _setup_ctrl(controller, tmp_path)
    ctrl.save_format = "both"
    config = _small_config()
    n_planes = 4
    n_blocks = 2

    with _chdir(tmp_path):
        saver.set_files(
            1,
            "scan",
            "stack",
            n_planes,
            "reconstructed_frame",
            wavelengths=[555],
        )
        saver.configure_focus(True, config=config)
        for s in _make_samples(n_blocks):
            saver.record_focus_sample(s)
        saver.saving_started = True
        _enqueue_planes(saver, n_planes)
        saver.both_save_worker()

        # HDF5
        fname = saver.filenames_list[0]
        with h5py.File(fname, "r") as f:
            assert "focus_trajectory" in f
            _assert_focus_group(f["focus_trajectory"], saver.focus_trajectory, config)

        # Zarr
        store_path = str(tmp_path / "scan.ome.zarr")
        root = cast(zarr.Group, zarr.open(store_path, mode="r"))
        assert "acquisition" in root
        acq = cast(zarr.Group, root["acquisition"])
        assert "focus" in acq
        _assert_focus_group(acq["focus"], saver.focus_trajectory, config)


def test_hdf5_autofocus_writes_one_row_per_plane(
    controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """A 3-plane single-channel stack with per-plane autofocus writes the
    ``/focus_trajectory`` group with one row per plane."""
    from unittest.mock import patch

    from lightsheet.gui.workers import StackWorker

    ctrl, saver = _setup_ctrl(controller, tmp_path)
    ctrl.save_format = "hdf5"
    n_planes = 3

    ctrl.saving_allowed = True
    ctrl.number_of_planes = n_planes
    ctrl.stack_mode_started = True
    ctrl.stack_starting_plane = 0.0
    ctrl.stack_step = 10
    ctrl.save_directory = str(tmp_path)
    ctrl.save_filepath = str(tmp_path / "autofocus_metadata")
    ctrl.save_description = "autofocus metadata sample"
    ctrl.current_horizontal_position_text = "0.0"
    ctrl.current_vertical_position_text = "0.0"
    ctrl.current_camera_position_text = "0.0"
    ctrl.save_panel.ui.radioButton_saveAllCrop.setChecked(False)
    ctrl.save_panel.ui.radioButton_saveAllFull.setChecked(False)

    config = AutofocusConfig(
        enabled=True,
        cadence=1,
        residual_gain_mm=0.05,
        max_residual_mm=0.5,
        smoothing=0.5,
        use_curve_seed=False,
    )
    worker = StackWorker(
        ctrl._bundle,
        ctrl._hw,
        ctrl,
        save_description="autofocus metadata sample",
        save_stitch_blend=False,
        save_all_crop=False,
        save_all_full=False,
        multi_channel=False,
        adaptive_cfg=None,
        autofocus_cfg=config,
    )
    worker.camera.recorder_timeout_status = False
    worker.siggen.error = 0

    state = {"acq_index": 0}

    def _fake_acquire_scan() -> bool:
        n_imgs = worker.siggen.waveform_cycles or 1
        imgs = worker.camera.copy_recorder_images(n_imgs)
        assert imgs is not None
        frame = np.asarray(imgs[0])
        frame[:] = 30000
        worker._shell.reconstructed_frame = frame
        state["acq_index"] += 1
        return True

    finished_emits: list[None] = []
    worker.finished.connect(lambda: finished_emits.append(None))
    with _chdir(tmp_path), patch.object(worker, "acquire_scan", _fake_acquire_scan):
        worker.run()

    assert len(finished_emits) == 1
    fname = saver.filenames_list[0]
    with h5py.File(fname, "r") as f:
        assert "focus_trajectory" in f
        grp = cast(h5py.Group, f["focus_trajectory"])
        block_ds = cast(h5py.Dataset, grp["block_index"])
        assert len(block_ds) == n_planes
        assert list(block_ds[:]) == [0, 1, 2]

        residuals = np.asarray(cast(h5py.Dataset, grp["residual_mm"])[:])
        feedforward = np.asarray(
            cast(h5py.Dataset, grp["feedforward_camera_pos_mm"])[:]
        )
        applied = np.asarray(cast(h5py.Dataset, grp["applied_camera_pos_mm"])[:])
        sharpness = np.asarray(cast(h5py.Dataset, grp["sharpness_metric"])[:])

        # Constant frames keep the residual correction at zero so the
        # applied camera position equals the feedforward seed position.
        np.testing.assert_allclose(residuals, 0.0)
        np.testing.assert_allclose(applied, feedforward)
        # All sharpness values are zero for the uniform 30000 frame.
        np.testing.assert_allclose(sharpness, 0.0)


def test_hdf5_autofocus_applied_equals_predicted_target_with_nonzero_residual(
    controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """A 3-plane single-channel stack with varying sharpness produces a
    non-zero residual, and the saved ``applied_camera_pos_mm`` equals the
    predicted target ``feedforward_camera_pos_mm + residual_mm`` for every
    plane."""
    from unittest.mock import patch

    from lightsheet.gui.workers import StackWorker

    ctrl, saver = _setup_ctrl(controller, tmp_path)
    ctrl.save_format = "hdf5"
    n_planes = 3

    ctrl.saving_allowed = True
    ctrl.number_of_planes = n_planes
    ctrl.stack_mode_started = True
    ctrl.stack_starting_plane = 0.0
    ctrl.stack_step = 10
    ctrl.save_directory = str(tmp_path)
    ctrl.save_filepath = str(tmp_path / "autofocus_metadata_residual")
    ctrl.save_description = "autofocus metadata residual"
    ctrl.current_horizontal_position_text = "0.0"
    ctrl.current_vertical_position_text = "0.0"
    ctrl.current_camera_position_text = "0.0"
    ctrl.save_panel.ui.radioButton_saveAllCrop.setChecked(False)
    ctrl.save_panel.ui.radioButton_saveAllFull.setChecked(False)

    config = AutofocusConfig(
        enabled=True,
        cadence=1,
        residual_gain_mm=0.05,
        max_residual_mm=0.5,
        smoothing=0.5,
        use_curve_seed=False,
    )
    worker = StackWorker(
        ctrl._bundle,
        ctrl._hw,
        ctrl,
        save_description="autofocus metadata residual",
        save_stitch_blend=False,
        save_all_crop=False,
        save_all_full=False,
        multi_channel=False,
        adaptive_cfg=None,
        autofocus_cfg=config,
    )
    worker.camera.recorder_timeout_status = False
    worker.siggen.error = 0

    state = {"acq_index": 0}

    def _fake_acquire_scan() -> bool:
        n_imgs = worker.siggen.waveform_cycles or 1
        imgs = worker.camera.copy_recorder_images(n_imgs)
        assert imgs is not None
        frame = np.asarray(imgs[0])
        frame[:] = 30000
        worker._shell.reconstructed_frame = frame
        state["acq_index"] += 1
        return True

    finished_emits: list[None] = []
    worker.finished.connect(lambda: finished_emits.append(None))
    with (
        _chdir(tmp_path),
        patch.object(worker, "acquire_scan", _fake_acquire_scan),
        patch(
            "lightsheet.focus.sharpness.frame_sharpness_variance",
            side_effect=[1.0, 2.0, 3.0],
        ),
    ):
        worker.run()

    assert len(finished_emits) == 1
    fname = saver.filenames_list[0]
    with h5py.File(fname, "r") as f:
        assert "focus_trajectory" in f
        grp = cast(h5py.Group, f["focus_trajectory"])
        block_ds = cast(h5py.Dataset, grp["block_index"])
        assert len(block_ds) == n_planes
        assert list(block_ds[:]) == [0, 1, 2]

        residuals = np.asarray(cast(h5py.Dataset, grp["residual_mm"])[:])
        feedforward = np.asarray(
            cast(h5py.Dataset, grp["feedforward_camera_pos_mm"])[:]
        )
        applied = np.asarray(cast(h5py.Dataset, grp["applied_camera_pos_mm"])[:])

        # Varying sharpness drives a positive residual from the second
        # update onward; the residual stored for each plane is the residual
        # used for that plane's move (before that plane's own update).
        np.testing.assert_allclose(residuals, [0.0, 0.0, 0.05], atol=1e-9)
        # The applied camera position is the predicted target:
        # feedforward + residual for the plane that produced it.
        np.testing.assert_allclose(applied, feedforward + residuals)
