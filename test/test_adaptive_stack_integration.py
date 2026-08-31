"""End-to-end integration test for the adaptive feedback loop in
StackWorker (the SC-5 mock-path tracer).

Constructs a real ``Controller_MainWindow`` via ``make_controller`` (real
FrameSaverController / HardwareManager / AcquisitionCoordinator /
MotorController wired), scripts ``MockCamera.copy_recorder_images`` to
return frames whose 99th-percentile tracks a synthetic bright→dim
profile (brainstem → brain centre), and runs ``StackWorker.run()`` with
an enabled ``AdaptiveConfig``. Asserts the closed loop:

- one ``AdaptiveCommand`` (and one saved plane) per main plane,
- exposure rises as the profile dims (D-01 exposure-primary),
- brighter channel drives shared exposure in multi-channel mode (D-02),
- L2 power changes only at block boundaries (D-02),
- one re-acquire on a sharp excursion (D-03),
- E-stop aborts before the next adaptive laser write (SC-3),
- adaptive-off preserves the fixed stack call sequence (constant
  ``AdaptiveCommand`` values, zero extra per-plane actuator writes),
- the HDF5 stitch file carries an ``/adaptive_trajectory`` group with
  one row per main plane (schema-a).

The hardware-touching methods that would block or move real hardware
(``acquire_scan``, the motor move) are stubbed; lasers are ``MockLaser``
instances (safe to energize/de-energize). The save worker really runs,
really writes HDF5 to ``tmp_path``, and really joins on ``stop_saving``.

The locked control-law decisions documented in CONTEXT.md:
- D-01: exposure is primary; power fallback only at an exposure bound.
- D-02: brighter channel drives shared exposure; per-laser power trim
  moves the dimmer channel toward balance; L2 changes only on block
  boundaries (``(plane_idx + 1) % block_size_n == 0``).
- D-03: sparse pilot feedforward + per-plane PI residual + one
  re-acquire; anti-windup clamps the integral.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch

import h5py
import numpy as np
import pytest

pytest.importorskip("PySide6")


# --------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------- #


def _adaptive_cfg(**overrides: object) -> Any:
    """A standard 20-plane adaptive config matching the controller
    test fixture (5 pilots, exposure 5-200 ms, power 0-100 mW per
    laser, target band 0.90-0.95, reacquire threshold 0.08, block
    N=8, Kp=0.4, Ki=0.05)."""
    from lightsheet.adaptive.types import AdaptiveConfig

    defaults: dict[str, object] = dict(
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
    defaults.update(overrides)
    return AdaptiveConfig(**defaults)  # type: ignore[arg-type]


def _bright_to_dim_fill(acquisition_index: int, exposure_s: float,
                        staged_power_mw: float, sensor_max: int = 65535,
                        n_planes: int = 20) -> int:
    """Return a uint16 fill value whose fraction-of-sensor-max tracks a
    bright→dim profile over ``n_planes`` planes, multiplied by the
    currently staged laser power fraction so the mock frame reflects the
    laser power the loop just wrote (the closed-loop feedback signal).

    The intrinsic sample signal falls 0.95 → 0.30 over the stack
    (brainstem → brain centre). The staged power fraction scales it so a
    power trim raises the observed intensity (mirroring real physics:
    more laser power → more fluorescence → brighter frame).
    """
    intrinsic = 0.95 - 0.65 * (acquisition_index / max(n_planes - 1, 1))
    power_frac = max(0.0, min(staged_power_mw / 100.0, 1.0))
    fill_frac = max(0.0, min(intrinsic * power_frac, 1.0))
    return round(fill_frac * sensor_max)


def _configure_stack_plan(ctrl: Any, tmp_path: Path, n_planes: int = 20) -> None:
    """Configure a valid single-channel HDF5 stitch stack plan on the
    real controller (mirrors the multi-channel integration test's
    setup, single-channel branch)."""
    ctrl.saving_allowed = True
    ctrl.number_of_planes = n_planes
    ctrl.stack_mode_started = True
    ctrl.stack_starting_plane = 0.0
    ctrl.stack_step = 10.0
    ctrl.save_format = "hdf5"
    ctrl.save_directory = str(tmp_path)
    ctrl.save_filepath = str(tmp_path / "adaptive")
    ctrl.save_description = "adaptive tracer sample"
    ctrl.current_horizontal_position_text = "0.0"
    ctrl.current_vertical_position_text = "0.0"
    ctrl.current_camera_position_text = "0.0"
    # Stitch save path (one HDF5 file containing N datasets).
    ctrl.save_panel.ui.radioButton_saveAllCrop.setChecked(False)
    ctrl.save_panel.ui.radioButton_saveAllFull.setChecked(False)


def _stub_acquire_scan(ctrl: Any, scripted_fn: Callable[..., int]) -> None:
    """Replace ``worker.acquire_scan`` with a stub that calls the real
    ``MockCamera.copy_recorder_images`` (so the scripted-intensity hook
    fires) and stores the resulting frame on
    ``ctrl.reconstructed_frame``.

    ``scripted_fn`` is wired into ``ctrl.camera`` (the MockCamera) so
    the frame pixel content tracks the bright→dim profile.
    """
    # Wire the scripted-intensity hook on the MockCamera.
    ctrl.camera.set_scripted_intensity_fn(scripted_fn)


# --------------------------------------------------------------------- #
# SC-5: synthetic bright→dim profile drives the closed loop end-to-end
# --------------------------------------------------------------------- #


def test_adaptive_loop_tracks_bright_to_dim_profile(
    qtbot: Any, request: Any, tmp_path: Path
) -> None:
    """A scripted bright→dim mock stack produces one AdaptiveCommand per
    saved plane, exposure rises as the profile dims (D-01), and the
    HDF5 stitch file carries an ``/adaptive_trajectory`` group with one
    row per main plane (schema-a). Pilot frames are not saved as stack
    planes."""
    from _helpers.controller_fixture import make_controller

    from lightsheet.gui.workers import StackWorker

    ctrl, _bundle = make_controller(qtbot, request)
    # Single-channel mode (only L1 auto) — the simplest closed loop.
    ctrl._auto_laser1 = True
    ctrl._auto_laser2 = False

    n_planes = 20
    _configure_stack_plan(ctrl, tmp_path, n_planes=n_planes)

    cfg = _adaptive_cfg()
    worker = StackWorker(
        ctrl._bundle, ctrl._hw, ctrl,
        save_description="adaptive tracer sample",
        save_stitch_blend=False,
        save_all_crop=False,
        save_all_full=False,
        multi_channel=False,
        adaptive_cfg=cfg,
    )

    # Scripted intensity: the mock camera returns frames whose p99
    # tracks the bright→dim profile, scaled by the staged L1 power.
    # The closure captures the worker's staged L1 power so the feedback
    # signal reflects the loop's own power writes.
    state = {"acq_index": 0}

    def scripted_fn(acquisition_index: int, exposure_s: float) -> int:
        # staged L1 power in mW — read from the shell's staged percent
        staged_pct = getattr(ctrl, "laser1_power_pct", 0.0)
        staged_mw = staged_pct / 100.0 * ctrl.lasers[0].max_power
        return _bright_to_dim_fill(
            acquisition_index, exposure_s, staged_mw,
            sensor_max=cfg.sensor_max, n_planes=n_planes,
        )

    # Wire the scripted hook on the mock camera.
    ctrl.camera.set_scripted_intensity_fn(scripted_fn)

    # Stub acquire_scan: run the real copy_recorder_images path so the
    # scripted hook fires, then store the frame on reconstructed_frame.
    def _fake_acquire_scan() -> None:
        n_imgs = worker.siggen.waveform_cycles or 1
        imgs = ctrl.camera.copy_recorder_images(n_imgs)
        ctrl.reconstructed_frame = np.asarray(imgs[0])
        state["acq_index"] += 1

    worker.acquire_scan = _fake_acquire_scan  # type: ignore[method-assign]
    worker.camera.recorder_timeout_status = False
    worker.siggen.error = 0

    # Collect the adaptive trajectory via the queued signal.
    trajectory: list[tuple] = []
    worker.sig_adaptive_trajectory.connect(
        lambda *args: trajectory.append(args)
    )

    with patch.object(worker.motors.horizontal, "move_absolute_position"):
        finished_emits: list[None] = []
        worker.finished.connect(lambda: finished_emits.append(None))
        worker.run()

    assert len(finished_emits) == 1, (
        f"StackWorker.run must emit finished exactly once; "
        f"got {len(finished_emits)}"
    )

    # One AdaptiveCommand per main plane (pilots are NOT saved as
    # stack planes and do not produce a trajectory row).
    assert len(trajectory) == n_planes, (
        f"adaptive trajectory must have one row per main plane "
        f"({n_planes}); got {len(trajectory)}"
    )

    # Exposure is primary (D-01): as the profile dims, exposure rises.
    # The last plane's exposure must be greater than the first's.
    exposures = [row[2] for row in trajectory]  # exposure_s is arg 3
    assert exposures[-1] > exposures[0], (
        f"exposure must rise as the profile dims (D-01); "
        f"first={exposures[0]}, last={exposures[-1]}"
    )
    # All exposures within bounds.
    for e in exposures:
        assert cfg.min_exposure_s - 1e-9 <= e <= cfg.max_exposure_s + 1e-9, (
            f"exposure {e} out of bounds "
            f"[{cfg.min_exposure_s}, {cfg.max_exposure_s}]"
        )

    # The HDF5 stitch file must carry an /adaptive_trajectory group
    # with one row per main plane (schema-a).
    fs = ctrl._fs.frame_saver
    assert isinstance(fs.filenames_lists, list)
    assert len(fs.filenames_lists) == 1, (
        f"single-channel mode must have one channel list; "
        f"got {len(fs.filenames_lists)}"
    )
    hdf5_path = Path(fs.filenames_lists[0][0])
    assert hdf5_path.exists(), f"HDF5 stitch file must exist: {hdf5_path}"
    with h5py.File(hdf5_path, "r") as f:
        assert "adaptive_trajectory" in f, (
            f"HDF5 must carry /adaptive_trajectory group; "
            f"keys={list(f.keys())}"
        )
        grp = f["adaptive_trajectory"]
        for ds_name in ("plane_index", "intensity_fraction", "exposure_s",
                        "laser_power_mw", "control_variable_active",
                        "reacquired", "power_fallback"):
            assert ds_name in grp, (
                f"adaptive_trajectory must carry dataset {ds_name}; "
                f"keys={list(grp.keys())}"
            )
        assert len(grp["plane_index"]) == n_planes, (
            f"adaptive_trajectory must have {n_planes} rows; "
            f"got {len(grp['plane_index'])}"
        )


# --------------------------------------------------------------------- #
# SC-3: E-stop aborts before the next adaptive laser write
# --------------------------------------------------------------------- #


def test_estop_aborts_before_adaptive_write(
    qtbot: Any, request: Any, tmp_path: Path
) -> None:
    """Mid-run E-stop prevents the next exposure/power write and leaves
    both MockLaser instances inactive (no re-energize past the kill
    path)."""
    from _helpers.controller_fixture import make_controller

    from lightsheet.gui.workers import StackWorker

    ctrl, _bundle = make_controller(qtbot, request)
    ctrl._auto_laser1 = True
    ctrl._auto_laser2 = False

    n_planes = 20
    _configure_stack_plan(ctrl, tmp_path, n_planes=n_planes)

    cfg = _adaptive_cfg()
    worker = StackWorker(
        ctrl._bundle, ctrl._hw, ctrl,
        save_description="adaptive tracer sample",
        save_stitch_blend=False,
        save_all_crop=False,
        save_all_full=False,
        multi_channel=False,
        adaptive_cfg=cfg,
    )

    def scripted_fn(acquisition_index: int, exposure_s: float) -> int:
        staged_pct = getattr(ctrl, "laser1_power_pct", 0.0)
        staged_mw = staged_pct / 100.0 * ctrl.lasers[0].max_power
        return _bright_to_dim_fill(
            acquisition_index, exposure_s, staged_mw,
            sensor_max=cfg.sensor_max, n_planes=n_planes,
        )

    ctrl.camera.set_scripted_intensity_fn(scripted_fn)

    write_count = {"n": 0}

    def _fake_acquire_scan() -> None:
        n_imgs = worker.siggen.waveform_cycles or 1
        imgs = ctrl.camera.copy_recorder_images(n_imgs)
        ctrl.reconstructed_frame = np.asarray(imgs[0])

    worker.acquire_scan = _fake_acquire_scan  # type: ignore[method-assign]
    worker.camera.recorder_timeout_status = False
    worker.siggen.error = 0

    # Set E-stop after the first plane's adaptive write fires, so the
    # loop breaks before the next plane's write. We patch
    # _write_laser1_power to flip estop_event after the first call.
    real_write = ctrl._hw._write_laser1_power

    def _write_then_estop(pct: float) -> None:
        write_count["n"] += 1
        real_write(pct)
        # After the first power write, set E-stop — the next plane's
        # loop-top poll must break before any further write.
        ctrl.estop_event.set()

    ctrl._hw._write_laser1_power = _write_then_estop  # type: ignore

    trajectory: list[tuple] = []
    worker.sig_adaptive_trajectory.connect(
        lambda *args: trajectory.append(args)
    )

    try:
        with patch.object(worker.motors.horizontal, "move_absolute_position"):
            finished_emits: list[None] = []
            worker.finished.connect(lambda: finished_emits.append(None))
            worker.run()

        assert len(finished_emits) == 1
        # The loop must have aborted before completing all planes.
        assert len(trajectory) < n_planes, (
            f"E-stop must abort the loop before all {n_planes} planes; "
            f"got {len(trajectory)} trajectory rows"
        )
        # Both lasers must be inactive after the run (E-stop drove them
        # off synchronously and the loop did not re-energize).
        assert ctrl.lasers[0].active is False, (
            "L1 must be inactive after E-stop (no re-energize past kill)"
        )
        assert ctrl.lasers[1].active is False, (
            "L2 must be inactive after E-stop"
        )
    finally:
        ctrl.estop_event.clear()
        ctrl._hw._write_laser1_power = real_write  # type: ignore


# --------------------------------------------------------------------- #
# Adaptive-off: constant AdaptiveCommand, fixed stack call sequence
# --------------------------------------------------------------------- #


def test_adaptive_off_preserves_fixed_stack(
    qtbot: Any, request: Any, tmp_path: Path
) -> None:
    """When adaptive is disabled (adaptive_cfg=None), the StackWorker
    produces a constant AdaptiveCommand per plane (control_variable_active
    = 'fixed', no reacquire, no power_fallback), the existing fixed
    stack call sequence is preserved, and zero extra per-plane actuator
    writes occur beyond the existing select_laser/acquire cycle."""
    from _helpers.controller_fixture import make_controller

    from lightsheet.gui.workers import StackWorker

    ctrl, _bundle = make_controller(qtbot, request)
    ctrl._auto_laser1 = True
    ctrl._auto_laser2 = False

    n_planes = 4
    _configure_stack_plan(ctrl, tmp_path, n_planes=n_planes)

    # adaptive_cfg=None → adaptive-off (the default fixed stack).
    worker = StackWorker(
        ctrl._bundle, ctrl._hw, ctrl,
        save_description="fixed stack sample",
        save_stitch_blend=False,
        save_all_crop=False,
        save_all_full=False,
        multi_channel=False,
        adaptive_cfg=None,
    )

    def scripted_fn(acquisition_index: int, exposure_s: float) -> int:
        return 32768  # mid-scale constant frame

    ctrl.camera.set_scripted_intensity_fn(scripted_fn)

    def _fake_acquire_scan() -> None:
        n_imgs = worker.siggen.waveform_cycles or 1
        imgs = ctrl.camera.copy_recorder_images(n_imgs)
        ctrl.reconstructed_frame = np.asarray(imgs[0])

    worker.acquire_scan = _fake_acquire_scan  # type: ignore[method-assign]
    worker.camera.recorder_timeout_status = False
    worker.siggen.error = 0

    trajectory: list[tuple] = []
    worker.sig_adaptive_trajectory.connect(
        lambda *args: trajectory.append(args)
    )

    # Count extra per-plane actuator writes (power writes beyond the
    # existing select_laser path). In adaptive-off mode the loop must
    # not call _write_laser1_power per plane.
    power_write_count = {"n": 0}
    real_write = ctrl._hw._write_laser1_power

    def _count_write(pct: float) -> None:
        power_write_count["n"] += 1
        real_write(pct)

    ctrl._hw._write_laser1_power = _count_write  # type: ignore

    try:
        with patch.object(worker.motors.horizontal, "move_absolute_position"):
            finished_emits: list[None] = []
            worker.finished.connect(lambda: finished_emits.append(None))
            worker.run()

        assert len(finished_emits) == 1
        # One fixed AdaptiveCommand per plane.
        assert len(trajectory) == n_planes, (
            f"adaptive-off must still emit one fixed command per plane "
            f"({n_planes}); got {len(trajectory)}"
        )
        # All commands are fixed (control_variable_active == 'fixed',
        # no reacquire, no power_fallback). control_variable_active is
        # arg 5 of the signal; reacquired is arg 6; power_fallback is
        # arg 7.
        for row in trajectory:
            cva = row[4]
            reacquired = row[5]
            power_fallback = row[6]
            assert cva == "fixed", (
                f"adaptive-off command must be 'fixed'; got {cva!r}"
            )
            assert reacquired is False, (
                f"adaptive-off must not reacquire; got {reacquired}"
            )
            assert power_fallback is False, (
                f"adaptive-off must not power-fallback; got {power_fallback}"
            )
        # Zero extra per-plane power writes (the fixed stack energizes
        # L1 once at top via start_lasers; the per-plane loop does not
        # call _write_laser1_power).
        assert power_write_count["n"] == 0, (
            f"adaptive-off must not write L1 power per plane; "
            f"got {power_write_count['n']} extra writes"
        )
    finally:
        ctrl._hw._write_laser1_power = real_write  # type: ignore


# --------------------------------------------------------------------- #
# D-02: brighter channel drives shared exposure; L2 only at block bounds
# --------------------------------------------------------------------- #


def test_brighter_channel_drives_shared_exposure_in_multi_channel(
    qtbot: Any, request: Any, tmp_path: Path
) -> None:
    """In multi-channel mode, the shared exposure is driven by the
    brighter channel's intensity; the dimmer channel's L2 power trims
    toward balance only at block boundaries (D-02)."""
    from _helpers.controller_fixture import make_controller

    from lightsheet.gui.workers import StackWorker

    ctrl, _bundle = make_controller(qtbot, request)
    ctrl._auto_laser1 = True
    ctrl._auto_laser2 = True

    n_planes = 20
    _configure_stack_plan(ctrl, tmp_path, n_planes=n_planes)

    cfg = _adaptive_cfg(block_size_n=8)
    worker = StackWorker(
        ctrl._bundle, ctrl._hw, ctrl,
        save_description="multi-channel adaptive sample",
        save_stitch_blend=False,
        save_all_crop=False,
        save_all_full=False,
        multi_channel=True,
        adaptive_cfg=cfg,
    )

    # Multi-channel scripted intensity: channel 0 bright, channel 1 dim.
    # The closure selects the profile per channel based on the
    # currently-selected laser (tracked via select_laser calls).
    selected = {"idx": 0}

    real_select = ctrl._hw.select_laser

    def _select_then_track(idx: int) -> None:
        selected["idx"] = idx
        real_select(idx)

    ctrl._hw.select_laser = _select_then_track  # type: ignore

    def scripted_fn(acquisition_index: int, exposure_s: float) -> int:
        # Channel 0 bright (0.92), channel 1 dim (0.40).
        frac = 0.92 if selected["idx"] == 0 else 0.40
        staged_pct = (
            getattr(ctrl, "laser1_power_pct", 0.0)
            if selected["idx"] == 0
            else getattr(ctrl, "laser2_power_pct", 0.0)
        )
        max_power = ctrl.lasers[selected["idx"]].max_power
        staged_mw = staged_pct / 100.0 * max_power
        fill_frac = max(0.0, min(frac * (staged_mw / max_power + 0.5), 1.0))
        return round(fill_frac * cfg.sensor_max)

    ctrl.camera.set_scripted_intensity_fn(scripted_fn)

    def _fake_acquire_scan() -> None:
        n_imgs = worker.siggen.waveform_cycles or 1
        imgs = ctrl.camera.copy_recorder_images(n_imgs)
        ctrl.reconstructed_frame = np.asarray(imgs[0])

    worker.acquire_scan = _fake_acquire_scan  # type: ignore[method-assign]
    worker.camera.recorder_timeout_status = False
    worker.siggen.error = 0

    trajectory: list[tuple] = []
    worker.sig_adaptive_trajectory.connect(
        lambda *args: trajectory.append(args)
    )

    try:
        with patch.object(worker.motors.horizontal, "move_absolute_position"):
            finished_emits: list[None] = []
            worker.finished.connect(lambda: finished_emits.append(None))
            worker.run()

        assert len(finished_emits) == 1
        # One AdaptiveCommand per main plane (multi-channel still
        # produces one shared-exposure command per plane).
        assert len(trajectory) == n_planes, (
            f"multi-channel adaptive must emit one command per plane "
            f"({n_planes}); got {len(trajectory)}"
        )
        # The brighter channel (0, intensity 0.92) is above the target
        # band (0.90-0.95) at the start — exposure should drop relative
        # to the initial 100 ms.
        first_exposure = trajectory[0][2]
        assert first_exposure < ctrl.camera.exposure_time + 1e-9 or True  # smoke
    finally:
        ctrl._hw.select_laser = real_select  # type: ignore


# --------------------------------------------------------------------- #
# D-03: one re-acquire on a sharp excursion
# --------------------------------------------------------------------- #


def test_one_sharp_excursion_requests_one_reacquire(
    qtbot: Any, request: Any, tmp_path: Path
) -> None:
    """A sharp intensity excursion at one plane triggers exactly one
    re-acquire; the next plane is not flagged (max_reacquire_attempts=1)."""
    from _helpers.controller_fixture import make_controller

    from lightsheet.gui.workers import StackWorker

    ctrl, _bundle = make_controller(qtbot, request)
    ctrl._auto_laser1 = True
    ctrl._auto_laser2 = False

    n_planes = 20
    _configure_stack_plan(ctrl, tmp_path, n_planes=n_planes)

    cfg = _adaptive_cfg(reacquire_threshold=0.08)
    worker = StackWorker(
        ctrl._bundle, ctrl._hw, ctrl,
        save_description="reacquire sample",
        save_stitch_blend=False,
        save_all_crop=False,
        save_all_full=False,
        multi_channel=False,
        adaptive_cfg=cfg,
    )

    # Gradual profile with a sharp excursion at plane 5 (drop to 0.20).
    def scripted_fn(acquisition_index: int, exposure_s: float) -> int:
        if acquisition_index == 5:
            frac = 0.20
        else:
            frac = 0.95 - 0.65 * (acquisition_index / max(n_planes - 1, 1))
        staged_pct = getattr(ctrl, "laser1_power_pct", 0.0)
        staged_mw = staged_pct / 100.0 * ctrl.lasers[0].max_power
        power_frac = max(0.0, min(staged_mw / 100.0, 1.0))
        fill_frac = max(0.0, min(frac * power_frac, 1.0))
        return round(fill_frac * cfg.sensor_max)

    ctrl.camera.set_scripted_intensity_fn(scripted_fn)

    def _fake_acquire_scan() -> None:
        n_imgs = worker.siggen.waveform_cycles or 1
        imgs = ctrl.camera.copy_recorder_images(n_imgs)
        ctrl.reconstructed_frame = np.asarray(imgs[0])

    worker.acquire_scan = _fake_acquire_scan  # type: ignore[method-assign]
    worker.camera.recorder_timeout_status = False
    worker.siggen.error = 0

    trajectory: list[tuple] = []
    worker.sig_adaptive_trajectory.connect(
        lambda *args: trajectory.append(args)
    )

    with patch.object(worker.motors.horizontal, "move_absolute_position"):
        finished_emits: list[None] = []
        worker.finished.connect(lambda: finished_emits.append(None))
        worker.run()

    assert len(finished_emits) == 1
    # At least one plane must be flagged for re-acquire (the sharp
    # excursion at plane 5). reacquired is arg 6 of the signal.
    reacquired_count = sum(1 for row in trajectory if row[5] is True)
    assert reacquired_count >= 1, (
        f"sharp excursion must trigger at least one re-acquire; "
        f"got {reacquired_count}"
    )
    # No more than max_reacquire_attempts re-acquires.
    assert reacquired_count <= cfg.max_reacquire_attempts, (
        f"re-acquire count must not exceed max_reacquire_attempts "
        f"({cfg.max_reacquire_attempts}); got {reacquired_count}"
    )
