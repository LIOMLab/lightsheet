"""End-to-end integration test for the camera focus compensation loop in
StackWorker (the D-11.3/D-11.4 mock-path tracer).

Constructs a real ``Controller_MainWindow`` via ``make_controller`` (real
FrameSaverController / HardwareManager / AcquisitionCoordinator /
MotorController wired), drives a real 16-plane stack with a synthetic
2-point ``FocusCurve``, and asserts the per-block focus move, residual
wiring, held-position metadata honesty, trajectory recording, and
abort-on-over-travel contracts.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch

import numpy as np
import pytest

pytest.importorskip("PySide6")


# --------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------- #


def _focus_cfg(**overrides: Any) -> Any:
    """A standard 16-plane focus config with block size 8 and residual on."""
    from lightsheet.focus.types import FocusConfig

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


def _focus_curve() -> Any:
    """A 2-point synthetic defocus curve.

    Stage positions 0 mm and 0.2 mm map to camera positions 20 mm and 35 mm.
    With a 16-plane stack starting at 0 um and stepping 10 um, the block
    boundaries are at stage 0 mm (camera 20 mm) and 0.08 mm (camera 26 mm).
    """
    from lightsheet.focus.types import FocusCurve

    return FocusCurve(
        stage_pos=(0.0, 0.2),
        camera_pos=(20.0, 35.0),
    )


def _configure_stack_plan(ctrl: Any, tmp_path: Path, n_planes: int = 16) -> None:
    """Configure a valid single-channel HDF5 stitch stack plan on the
    real controller."""
    ctrl.saving_allowed = True
    ctrl.number_of_planes = n_planes
    ctrl.stack_mode_started = True
    ctrl.stack_starting_plane = 0.0
    ctrl.stack_step = 10.0
    ctrl.save_format = "hdf5"
    ctrl.save_directory = str(tmp_path)
    ctrl.save_filepath = str(tmp_path / "focus")
    ctrl.save_description = "focus tracer sample"
    ctrl.current_horizontal_position_text = "0.0"
    ctrl.current_vertical_position_text = "0.0"
    ctrl.current_camera_position_text = "0.0"
    ctrl.save_panel.ui.radioButton_saveAllCrop.setChecked(False)
    ctrl.save_panel.ui.radioButton_saveAllFull.setChecked(False)


def _make_worker(
    ctrl: Any,
    focus_cfg: Any | None = None,
    focus_curve: Any | None = None,
) -> Any:
    """Build a StackWorker with the supplied focus config and curve."""
    from lightsheet.gui.workers import StackWorker

    return StackWorker(
        ctrl._bundle,
        ctrl._hw,
        ctrl,
        save_description="focus tracer sample",
        save_stitch_blend=False,
        save_all_crop=False,
        save_all_full=False,
        multi_channel=False,
        adaptive_cfg=None,
        focus_cfg=focus_cfg,
        focus_curve=focus_curve,
    )


def _fake_acquire_scan_factory(
    worker: Any, state: dict[str, Any]
) -> Callable[[], bool]:
    """Return an ``acquire_scan`` stub that fills ``reconstructed_frame``
    with a deterministic pattern.

    Frames in the first block (planes 0-7) get a checkerboard so the
    sharpness metric is non-zero at the second block boundary. The last
    plane of the first block (plane 7) is the frame used for residual
    computation. Frames in the second block are flat.
    """

    def _fake_acquire_scan() -> bool:
        n_imgs = worker.siggen.waveform_cycles or 1
        imgs = worker.camera.copy_recorder_images(n_imgs)
        idx = state["acq_index"]
        frame = np.asarray(imgs[0])
        if idx == 7:
            # Checkerboard: non-zero variance so frame_sharpness_variance > 0.
            frame[:32, :32] = 50000
            frame[:32, 32:] = 10000
            frame[32:, :32] = 10000
            frame[32:, 32:] = 50000
        else:
            # Constant frame: zero sharpness.
            frame[:] = 30000
        worker._shell.reconstructed_frame = frame
        state["acq_index"] += 1
        return True

    return _fake_acquire_scan


# --------------------------------------------------------------------- #
# D-11.3: per-block focus move
# --------------------------------------------------------------------- #


def test_move_axes_parallel_called_only_at_block_boundaries(
    qtbot: Any, request: Any, tmp_path: Path
) -> None:
    """A 16-plane focus stack with block size 8 issues exactly two
    dual-axis ``move_axes_parallel`` calls (planes 0 and 8) and 14
    horizontal-only ``move_absolute_position`` calls."""
    from _helpers.controller_fixture import make_controller


    ctrl, _bundle = make_controller(qtbot, request)
    _configure_stack_plan(ctrl, tmp_path, n_planes=16)

    worker = _make_worker(ctrl, focus_cfg=_focus_cfg(), focus_curve=_focus_curve())

    state = {"acq_index": 0}
    worker.camera.recorder_timeout_status = False
    worker.siggen.error = 0

    parallel_calls: list[list[tuple[str, float, str]]] = []
    horizontal_calls: list[tuple[float, str]] = []
    camera_calls: list[tuple[float, str]] = []

    real_parallel = worker.motors.move_axes_parallel

    def _track_parallel(moves: list[tuple[str, float, str]]) -> None:
        parallel_calls.append(list(moves))
        real_parallel(moves)

    assert worker.motors.horizontal is not None
    assert worker.motors.camera is not None
    real_horizontal = worker.motors.horizontal.move_absolute_position

    def _track_horizontal(pos: float, units: str) -> None:
        horizontal_calls.append((pos, units))
        real_horizontal(pos, units)

    real_camera = worker.motors.camera.move_absolute_position

    def _track_camera(pos: float, units: str) -> None:
        camera_calls.append((pos, units))
        real_camera(pos, units)

    fake_acquire_scan = _fake_acquire_scan_factory(worker, state)
    finished_emits: list[None] = []
    worker.finished.connect(lambda: finished_emits.append(None))
    with (
        patch.object(worker, "acquire_scan", fake_acquire_scan),
        patch.object(worker.motors, "move_axes_parallel", _track_parallel),
        patch.object(
            worker.motors.horizontal, "move_absolute_position", _track_horizontal
        ),
        patch.object(
            worker.motors.camera, "move_absolute_position", _track_camera
        ),
    ):
        worker.run()

    assert len(finished_emits) == 1
    assert len(parallel_calls) == 2, (
        f"expected 2 parallel calls; got {len(parallel_calls)}"
    )
    assert len(horizontal_calls) == 14, (
        f"expected 14 horizontal-only calls; got {len(horizontal_calls)}"
    )
    assert len(camera_calls) == 0, (
        f"expected 0 per-plane camera calls; got {len(camera_calls)}"
    )

    # Both parallel calls include horizontal and camera axes.
    for moves in parallel_calls:
        axes = [m[0] for m in moves]
        assert "horizontal" in axes
        assert "camera" in axes


def test_add_motor_parameters_logs_held_camera_position_within_block(
    qtbot: Any, request: Any, tmp_path: Path
) -> None:
    """All 8 planes in a block log the same camera position, and that
    position is the actually-applied (held) position, not the
    feedforward target for planes 1-7."""
    from _helpers.controller_fixture import make_controller


    ctrl, _bundle = make_controller(qtbot, request)
    _configure_stack_plan(ctrl, tmp_path, n_planes=16)

    worker = _make_worker(ctrl, focus_cfg=_focus_cfg(), focus_curve=_focus_curve())

    state = {"acq_index": 0}
    worker.camera.recorder_timeout_status = False
    worker.siggen.error = 0

    finished_emits: list[None] = []
    worker.finished.connect(lambda: finished_emits.append(None))
    with patch.object(
        worker, "acquire_scan", _fake_acquire_scan_factory(worker, state)
    ):
        worker.run()

    assert len(finished_emits) == 1
    fs = ctrl._fs.frame_saver
    camera_texts = fs.camera_positions_list
    assert len(camera_texts) == 16, (
        f"expected 16 camera entries; got {len(camera_texts)}"
    )

    # All planes in each block share the same camera position text.
    assert len(set(camera_texts[:8])) == 1, (
        f"first block camera texts vary: {set(camera_texts[:8])}"
    )
    assert len(set(camera_texts[8:])) == 1, (
        f"second block camera texts vary: {set(camera_texts[8:])}"
    )

    # The held camera text is the formatted real camera position.
    held_camera_mm = worker.motors.camera.get_position("mm")
    held_text = f"{held_camera_mm:.5f} mm"
    assert camera_texts[-1] == held_text, (
        f"last camera text {camera_texts[-1]!r} does not match "
        f"held position {held_text!r}"
    )


def test_focus_trajectory_records_one_sample_per_block(
    qtbot: Any, request: Any, tmp_path: Path
) -> None:
    """The outer FrameSaverController records exactly one FocusSample per
    focus block boundary, and each sample's applied camera position
    matches the move_axes_parallel camera target."""
    from _helpers.controller_fixture import make_controller


    ctrl, _bundle = make_controller(qtbot, request)
    _configure_stack_plan(ctrl, tmp_path, n_planes=16)

    worker = _make_worker(ctrl, focus_cfg=_focus_cfg(), focus_curve=_focus_curve())

    state = {"acq_index": 0}
    worker.camera.recorder_timeout_status = False
    worker.siggen.error = 0

    parallel_calls: list[list[tuple[str, float, str]]] = []
    real_parallel = worker.motors.move_axes_parallel

    def _track_parallel(moves: list[tuple[str, float, str]]) -> None:
        parallel_calls.append(list(moves))
        real_parallel(moves)

    finished_emits: list[None] = []
    worker.finished.connect(lambda: finished_emits.append(None))
    with (
        patch.object(worker, "acquire_scan", _fake_acquire_scan_factory(worker, state)),
        patch.object(worker.motors, "move_axes_parallel", _track_parallel),
    ):
        worker.run()

    assert len(finished_emits) == 1
    traj = ctrl._fs.focus_trajectory
    assert len(traj) == 2, (
        f"expected 2 focus samples; got {len(traj)}"
    )

    for i, sample in enumerate(traj):
        assert sample.block_index == i
        camera_move = next(
            m for m in parallel_calls[i] if m[0] == "camera"
        )
        camera_target = camera_move[1]
        assert sample.applied_camera_pos_mm == pytest.approx(camera_target)


def test_update_residual_called_from_second_block_boundary_onward(
    qtbot: Any, request: Any, tmp_path: Path
) -> None:
    """FocusController.update_residual is called exactly once at the
    second block boundary (plane 8) with the sharpness of the previous
    block's frame. The first FocusSample.sharpness_metric is None; the
    second equals the computed value."""
    from _helpers.controller_fixture import make_controller

    from lightsheet.focus.controller import FocusController
    from lightsheet.focus.sharpness import frame_sharpness_variance

    ctrl, _bundle = make_controller(qtbot, request)
    _configure_stack_plan(ctrl, tmp_path, n_planes=16)

    worker = _make_worker(ctrl, focus_cfg=_focus_cfg(), focus_curve=_focus_curve())

    state = {"acq_index": 0}
    worker.camera.recorder_timeout_status = False
    worker.siggen.error = 0

    residual_calls: list[float] = []
    captured_frames: list[np.ndarray] = []
    real_update = FocusController.update_residual

    def _track_residual(self: FocusController, sharpness: float) -> None:
        # Capture the frame that the sharpness metric was computed from.
        captured_frames.append(worker._shell.reconstructed_frame.copy())
        residual_calls.append(sharpness)
        real_update(self, sharpness)

    with (
        patch.object(worker, "acquire_scan", _fake_acquire_scan_factory(worker, state)),
        patch.object(FocusController, "update_residual", _track_residual),
    ):
        finished_emits: list[None] = []
        worker.finished.connect(lambda: finished_emits.append(None))
        worker.run()

    assert len(finished_emits) == 1
    assert len(residual_calls) == 1, (
        f"expected 1 residual update; got {len(residual_calls)}"
    )

    # The sharpness stored in the second sample equals the value passed.
    traj = ctrl._fs.focus_trajectory
    assert len(traj) == 2
    assert traj[0].sharpness_metric is None
    assert traj[1].sharpness_metric == pytest.approx(residual_calls[0])

    # The sharpness value must equal the value computed from the
    # actual frame that was held at the second block boundary.
    assert len(captured_frames) == 1
    assert residual_calls[0] == pytest.approx(
        frame_sharpness_variance(captured_frames[0])
    )


def test_focus_curve_required_when_enabled_worker_does_not_reload_file(
    qtbot: Any, request: Any, tmp_path: Path
) -> None:
    """Constructing StackWorker with focus enabled but no FocusCurve raises
    ValueError before any motor call — the worker must not fall back to
    loading a calibration file itself."""
    from _helpers.controller_fixture import make_controller

    ctrl, _bundle = make_controller(qtbot, request)
    _configure_stack_plan(ctrl, tmp_path, n_planes=16)

    with pytest.raises(ValueError, match="no calibration curve was loaded"):
        _make_worker(ctrl, focus_cfg=_focus_cfg(), focus_curve=None)


def test_focus_over_travel_aborts_stack_with_beep(
    qtbot: Any, request: Any, tmp_path: Path
) -> None:
    """A block-boundary move whose horizontal target exceeds the travel
    limit aborts the stack with the focus-specific over-travel message
    and a beep, mirroring the existing horizontal-only abort path.

    The camera axis is within limits; the horizontal axis is forced
    over-travel at the second block boundary (plane 8) so the abort path
    on the ``move_axes_parallel`` call is exercised.
    """
    from _helpers.controller_fixture import make_controller


    ctrl, _bundle = make_controller(qtbot, request)
    _configure_stack_plan(ctrl, tmp_path, n_planes=16)

    worker = _make_worker(ctrl, focus_cfg=_focus_cfg(), focus_curve=_focus_curve())

    # Force the horizontal axis to over-travel at the second block boundary.
    # Plane 8 is at 80 um; limit it to 75 um so the first boundary passes.
    assert worker.motors.horizontal is not None
    worker.motors.horizontal.set_limit_high(0.075, "mm")

    state = {"acq_index": 0}
    worker.camera.recorder_timeout_status = False
    worker.siggen.error = 0

    messages: list[str] = []
    beeps: list[None] = []
    ctrl.sig_message.connect(messages.append)
    ctrl.sig_beep.connect(lambda: beeps.append(None))

    finished_emits: list[None] = []
    worker.finished.connect(lambda: finished_emits.append(None))
    with patch.object(
        worker, "acquire_scan", _fake_acquire_scan_factory(worker, state)
    ):
        worker.run()

    assert len(finished_emits) == 1
    assert len(beeps) >= 1, "expected at least one beep on over-travel abort"
    focus_msgs = [m for m in messages if "Focus compensation move rejected" in m]
    assert len(focus_msgs) >= 1, f"expected focus over-travel message; got {messages}"


def test_focus_disabled_matches_fixed_stack_behavior(
    qtbot: Any, request: Any, tmp_path: Path
) -> None:
    """When focus compensation is disabled (focus_cfg=None), the stack
    runs the existing fixed-camera path: zero dual-axis moves, zero
    focus samples, and zero focus trajectory emissions."""
    from _helpers.controller_fixture import make_controller

    from lightsheet.gui.workers import StackWorker

    ctrl, _bundle = make_controller(qtbot, request)
    _configure_stack_plan(ctrl, tmp_path, n_planes=16)

    worker = StackWorker(
        ctrl._bundle,
        ctrl._hw,
        ctrl,
        save_description="fixed stack sample",
        save_stitch_blend=False,
        save_all_crop=False,
        save_all_full=False,
        multi_channel=False,
        adaptive_cfg=None,
    )

    state = {"acq_index": 0}
    worker.camera.recorder_timeout_status = False
    worker.siggen.error = 0

    parallel_calls: list[list[tuple[str, float, str]]] = []
    real_parallel = worker.motors.move_axes_parallel

    def _track_parallel(moves: list[tuple[str, float, str]]) -> None:
        parallel_calls.append(list(moves))
        real_parallel(moves)

    focus_emissions: list[tuple[Any, ...]] = []
    worker.sig_focus_trajectory.connect(lambda *args: focus_emissions.append(args))

    finished_emits: list[None] = []
    worker.finished.connect(lambda: finished_emits.append(None))
    with (
        patch.object(worker, "acquire_scan", _fake_acquire_scan_factory(worker, state)),
        patch.object(worker.motors, "move_axes_parallel", _track_parallel),
    ):
        worker.run()

    assert len(finished_emits) == 1
    assert len(parallel_calls) == 0, (
        f"expected 0 parallel moves; got {len(parallel_calls)}"
    )
    assert len(ctrl._fs.focus_trajectory) == 0
    assert len(focus_emissions) == 0


def test_estop_prevents_next_block_boundary_focus_move(
    qtbot: Any, request: Any, tmp_path: Path
) -> None:
    """Setting estop_event after the first block aborts before the second
    block-boundary focus move is attempted."""
    from _helpers.controller_fixture import make_controller


    ctrl, _bundle = make_controller(qtbot, request)
    _configure_stack_plan(ctrl, tmp_path, n_planes=16)

    worker = _make_worker(ctrl, focus_cfg=_focus_cfg(), focus_curve=_focus_curve())

    state = {"acq_index": 0, "plane": 0}

    def _fake_acquire_scan() -> bool:
        n_imgs = worker.siggen.waveform_cycles or 1
        imgs = worker.camera.copy_recorder_images(n_imgs)
        worker._shell.reconstructed_frame = np.asarray(imgs[0])
        state["plane"] += 1
        # E-stop after the first block completes (after plane 7).
        if state["plane"] == 8:
            ctrl.estop_event.set()
        state["acq_index"] += 1
        return True

    worker.camera.recorder_timeout_status = False
    worker.siggen.error = 0

    parallel_calls: list[list[tuple[str, float, str]]] = []
    real_parallel = worker.motors.move_axes_parallel

    def _track_parallel(moves: list[tuple[str, float, str]]) -> None:
        parallel_calls.append(list(moves))
        real_parallel(moves)

    try:
        finished_emits: list[None] = []
        worker.finished.connect(lambda: finished_emits.append(None))
        with (
            patch.object(worker, "acquire_scan", _fake_acquire_scan),
            patch.object(worker.motors, "move_axes_parallel", _track_parallel),
        ):
            worker.run()

        assert len(finished_emits) == 1
        assert len(parallel_calls) == 1, (
            f"E-stop must prevent second block boundary move; got {len(parallel_calls)}"
        )
    finally:
        ctrl.estop_event.clear()
