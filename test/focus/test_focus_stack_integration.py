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
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import numpy as np
import pytest

pytest.importorskip("PySide6")

if TYPE_CHECKING:
    from lightsheet.gui.shell.controller import Controller_MainWindow

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
    ctrl.stack_step = 10
    ctrl.save_format = "hdf5"
    ctrl.save_directory = str(tmp_path)
    ctrl.save_filepath = str(tmp_path / "focus")
    ctrl.save_description = "focus tracer sample"
    ctrl.current_horizontal_position_text = "0.0"
    ctrl.current_vertical_position_text = "0.0"
    ctrl.current_camera_position_text = "0.0"
    ctrl.save_panel.ui.radioButton_saveAllCrop.setChecked(False)
    ctrl.save_panel.ui.radioButton_saveAllFull.setChecked(False)


def _autofocus_cfg(**overrides: Any) -> Any:
    """A standard per-plane autofocus config with cadence 1."""
    from lightsheet.focus.types import AutofocusConfig

    defaults: dict[str, Any] = dict(
        enabled=True,
        cadence=1,
        residual_gain_mm=0.05,
        max_residual_mm=0.5,
        smoothing=0.5,
        use_curve_seed=False,
    )
    defaults.update(overrides)
    return AutofocusConfig(**defaults)


def _make_worker(
    ctrl: Any,
    focus_cfg: Any | None = None,
    focus_curve: Any | None = None,
    autofocus_cfg: Any | None = None,
    autofocus_curve: Any | None = None,
    multi_channel: bool = False,
) -> Any:
    """Build a StackWorker with the supplied focus/autofocus config and curve."""
    from lightsheet.gui.workers import StackWorker

    return StackWorker(
        ctrl._bundle,
        ctrl._hw,
        ctrl,
        save_description="focus tracer sample",
        save_stitch_blend=False,
        save_all_crop=False,
        save_all_full=False,
        multi_channel=multi_channel,
        adaptive_cfg=None,
        focus_cfg=focus_cfg,
        focus_curve=focus_curve,
        autofocus_cfg=autofocus_cfg,
        autofocus_curve=autofocus_curve,
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
    controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """A 16-plane focus stack with block size 8 issues exactly two
    dual-axis ``move_axes_parallel`` calls (planes 0 and 8) and 14
    horizontal-only ``move_absolute_position`` calls."""
    ctrl = controller
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
        patch.object(worker.motors.camera, "move_absolute_position", _track_camera),
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
    controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """All 8 planes in a block log the same camera position, and that
    position is the actually-applied (held) position, not the
    feedforward target for planes 1-7."""
    ctrl = controller
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
    held_text = f"{held_camera_mm:.4f} mm"
    assert camera_texts[-1] == held_text, (
        f"last camera text {camera_texts[-1]!r} does not match "
        f"held position {held_text!r}"
    )


def test_focus_trajectory_records_one_sample_per_block(
    controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """The outer FrameSaverController records exactly one FocusSample per
    focus block boundary, and each sample's applied camera position
    matches the move_axes_parallel camera target."""
    ctrl = controller
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
    assert len(traj) == 2, f"expected 2 focus samples; got {len(traj)}"

    for i, sample in enumerate(traj):
        assert sample.block_index == i
        camera_move = next(m for m in parallel_calls[i] if m[0] == "camera")
        camera_target = camera_move[1]
        assert sample.applied_camera_pos_mm == pytest.approx(camera_target)


def test_update_residual_called_from_second_block_boundary_onward(
    controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """FocusController.update_residual is called exactly once at the
    second block boundary (plane 8) with the sharpness of the previous
    block's frame. The first FocusSample.sharpness_metric is None; the
    second equals the computed value."""
    from lightsheet.focus.controller import FocusController
    from lightsheet.focus.sharpness import frame_sharpness_variance

    ctrl = controller
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
    controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """Constructing StackWorker with focus enabled but no FocusCurve raises
    ValueError before any motor call — the worker must not fall back to
    loading a calibration file itself."""
    ctrl = controller
    _configure_stack_plan(ctrl, tmp_path, n_planes=16)

    with pytest.raises(ValueError, match="no calibration curve was loaded"):
        _make_worker(ctrl, focus_cfg=_focus_cfg(), focus_curve=None)


def test_focus_over_travel_aborts_stack_with_beep(
    controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """A block-boundary move whose horizontal target exceeds the travel
    limit aborts the stack with the focus-specific over-travel message
    and a beep, mirroring the existing horizontal-only abort path.

    The camera axis is within limits; the horizontal axis is forced
    over-travel at the second block boundary (plane 8) so the abort path
    on the ``move_axes_parallel`` call is exercised.
    """
    ctrl = controller
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
    controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """When focus compensation is disabled (focus_cfg=None), the stack
    runs the existing fixed-camera path: zero dual-axis moves, zero
    focus samples, and zero focus trajectory emissions."""
    from lightsheet.gui.workers import StackWorker

    ctrl = controller
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
    controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """Setting estop_event after the first block aborts before the second
    block-boundary focus move is attempted."""
    ctrl = controller
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


# --------------------------------------------------------------------- #
# D-13.4: per-plane adaptive autofocus
# --------------------------------------------------------------------- #


def _fake_acquire_scan_autofocus_factory(worker: Any, state: dict[str, Any]) -> Any:
    """Return an ``acquire_scan`` stub that fills ``reconstructed_frame``
    with a constant deterministic pattern for the autofocus tests."""

    def _fake_acquire_scan() -> bool:
        n_imgs = worker.siggen.waveform_cycles or 1
        imgs = worker.camera.copy_recorder_images(n_imgs)
        frame = np.asarray(imgs[0])
        frame[:] = 30000
        worker._shell.reconstructed_frame = frame
        state["acq_index"] += 1
        return True

    return _fake_acquire_scan


def _configure_autofocus_stack_plan(
    ctrl: Any, tmp_path: Path, n_planes: int = 4
) -> None:
    """Configure a valid 4-plane single-channel stack plan for autofocus."""
    ctrl.saving_allowed = True
    ctrl.number_of_planes = n_planes
    ctrl.stack_mode_started = True
    ctrl.stack_starting_plane = 0.0
    ctrl.stack_step = 10
    ctrl.save_format = "hdf5"
    ctrl.save_directory = str(tmp_path)
    ctrl.save_filepath = str(tmp_path / "autofocus")
    ctrl.save_description = "autofocus tracer sample"
    ctrl.current_horizontal_position_text = "0.0"
    ctrl.current_vertical_position_text = "0.0"
    ctrl.current_camera_position_text = "0.0"
    ctrl.save_panel.ui.radioButton_saveAllCrop.setChecked(False)
    ctrl.save_panel.ui.radioButton_saveAllFull.setChecked(False)


def test_autofocus_move_axes_parallel_called_every_plane(
    controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """A 4-plane autofocus stack calls ``move_axes_parallel`` once per
    plane, each time moving the horizontal and camera axes together."""
    ctrl = controller
    _configure_autofocus_stack_plan(ctrl, tmp_path, n_planes=4)

    worker = _make_worker(ctrl, autofocus_cfg=_autofocus_cfg())

    state = {"acq_index": 0}
    worker.camera.recorder_timeout_status = False
    worker.siggen.error = 0

    parallel_calls: list[list[tuple[str, float, str]]] = []

    def _track_parallel(moves: list[tuple[str, float, str]]) -> None:
        parallel_calls.append(list(moves))

    finished_emits: list[None] = []
    worker.finished.connect(lambda: finished_emits.append(None))
    with (
        patch.object(
            worker, "acquire_scan", _fake_acquire_scan_autofocus_factory(worker, state)
        ),
        patch.object(worker.motors, "move_axes_parallel", _track_parallel),
    ):
        worker.run()

    assert len(finished_emits) == 1
    assert len(parallel_calls) == 4, (
        f"expected 4 parallel calls; got {len(parallel_calls)}"
    )
    for i, moves in enumerate(parallel_calls):
        axes = [m[0] for m in moves]
        assert "horizontal" in axes, f"plane {i} missing horizontal"
        assert "camera" in axes, f"plane {i} missing camera"


def test_autofocus_update_called_at_cadence(
    controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """With cadence 2 over 4 planes, ``update()`` is called exactly 2
    times (planes 0 and 2)."""
    from lightsheet.focus.adaptive_controller import AdaptiveFocusController

    ctrl = controller
    _configure_autofocus_stack_plan(ctrl, tmp_path, n_planes=4)

    worker = _make_worker(ctrl, autofocus_cfg=_autofocus_cfg(cadence=2))

    state = {"acq_index": 0}
    worker.camera.recorder_timeout_status = False
    worker.siggen.error = 0

    update_calls: list[tuple[float, float]] = []
    real_update = AdaptiveFocusController.update

    def _track_update(stage_pos_mm: float, sharpness: float) -> None:
        # Class-level patch receives the explicit args only; call the
        # unbound method with the controller instance the worker constructed.
        update_calls.append((stage_pos_mm, sharpness))
        real_update(worker._autofocus_controller, stage_pos_mm, sharpness)

    finished_emits: list[None] = []
    worker.finished.connect(lambda: finished_emits.append(None))
    with (
        patch.object(
            worker, "acquire_scan", _fake_acquire_scan_autofocus_factory(worker, state)
        ),
        patch.object(AdaptiveFocusController, "update", side_effect=_track_update),
    ):
        worker.run()

    assert len(finished_emits) == 1
    assert len(update_calls) == 2, f"expected 2 update calls; got {len(update_calls)}"


def test_autofocus_records_one_focus_sample_per_plane(
    controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """The worker records exactly one ``FocusSample`` per plane and the
    sample's ``block_index`` equals the plane number."""
    ctrl = controller
    _configure_autofocus_stack_plan(ctrl, tmp_path, n_planes=4)

    worker = _make_worker(ctrl, autofocus_cfg=_autofocus_cfg())

    state = {"acq_index": 0}
    worker.camera.recorder_timeout_status = False
    worker.siggen.error = 0

    finished_emits: list[None] = []
    worker.finished.connect(lambda: finished_emits.append(None))
    with patch.object(
        worker, "acquire_scan", _fake_acquire_scan_autofocus_factory(worker, state)
    ):
        worker.run()

    assert len(finished_emits) == 1
    traj = ctrl._fs.focus_trajectory
    assert len(traj) == 4, f"expected 4 focus samples; got {len(traj)}"
    for i, sample in enumerate(traj):
        assert sample.block_index == i


def test_autofocus_uses_curve_seed_when_use_curve_seed_true(
    controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """When ``use_curve_seed`` is True the feedforward is sampled from
    the curve and varies with stage position; when False it is constant."""
    ctrl = controller
    _configure_autofocus_stack_plan(ctrl, tmp_path, n_planes=4)

    curve = _focus_curve()
    worker = _make_worker(
        ctrl,
        autofocus_cfg=_autofocus_cfg(use_curve_seed=True),
        autofocus_curve=curve,
    )

    state = {"acq_index": 0}
    worker.camera.recorder_timeout_status = False
    worker.siggen.error = 0

    finished_emits: list[None] = []
    worker.finished.connect(lambda: finished_emits.append(None))
    with patch.object(
        worker, "acquire_scan", _fake_acquire_scan_autofocus_factory(worker, state)
    ):
        worker.run()

    assert len(finished_emits) == 1
    traj = ctrl._fs.focus_trajectory
    assert len(traj) == 4
    feedforwards = [s.feedforward_camera_pos_mm for s in traj]
    assert feedforwards[-1] != feedforwards[0], (
        f"curve seed should vary; got {feedforwards}"
    )


def test_autofocus_over_travel_aborts_stack(
    controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """A ``ValueError`` from ``move_axes_parallel`` aborts the stack with
    the over-travel message and a beep."""
    ctrl = controller
    _configure_autofocus_stack_plan(ctrl, tmp_path, n_planes=4)

    worker = _make_worker(ctrl, autofocus_cfg=_autofocus_cfg())

    state = {"acq_index": 0}
    worker.camera.recorder_timeout_status = False
    worker.siggen.error = 0

    messages: list[str] = []
    beeps: list[None] = []
    ctrl.sig_message.connect(messages.append)
    ctrl.sig_beep.connect(lambda: beeps.append(None))

    finished_emits: list[None] = []
    worker.finished.connect(lambda: finished_emits.append(None))
    with (
        patch.object(
            worker, "acquire_scan", _fake_acquire_scan_autofocus_factory(worker, state)
        ),
        patch.object(
            worker.motors,
            "move_axes_parallel",
            side_effect=ValueError("out of limits"),
        ),
    ):
        worker.run()

    assert len(finished_emits) == 1
    assert len(beeps) >= 1, "expected at least one beep on over-travel abort"
    focus_msgs = [m for m in messages if "Focus move rejected" in m]
    assert len(focus_msgs) >= 1, f"expected over-travel message; got {messages}"


def test_autofocus_estop_breaks_loop(
    controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """Setting ``estop_event`` mid-run prevents further frames from being
    acquired."""
    ctrl = controller
    _configure_autofocus_stack_plan(ctrl, tmp_path, n_planes=4)

    worker = _make_worker(ctrl, autofocus_cfg=_autofocus_cfg())

    state = {"acq_index": 0, "plane": 0}

    def _fake_acquire_scan() -> bool:
        n_imgs = worker.siggen.waveform_cycles or 1
        imgs = worker.camera.copy_recorder_images(n_imgs)
        frame = np.asarray(imgs[0])
        frame[:] = 30000
        worker._shell.reconstructed_frame = frame
        state["plane"] += 1
        if state["plane"] == 2:
            ctrl.estop_event.set()
        state["acq_index"] += 1
        return True

    worker.camera.recorder_timeout_status = False
    worker.siggen.error = 0

    with patch.object(worker, "acquire_scan") as mock_acquire:
        mock_acquire.side_effect = _fake_acquire_scan

        finished_emits: list[None] = []
        worker.finished.connect(lambda: finished_emits.append(None))
        worker.run()

    assert len(finished_emits) == 1
    assert mock_acquire.call_count == 2, (
        f"E-stop must prevent further acquires; got {mock_acquire.call_count}"
    )


def test_autofocus_multi_channel_uses_same_camera_position_and_last_channel_update(
    controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """In multi-channel mode, both channels use the same predicted camera
    position and the residual is updated once per main plane from the last
    channel's acquired frame."""
    from lightsheet.focus.adaptive_controller import AdaptiveFocusController

    ctrl = controller
    _configure_autofocus_stack_plan(ctrl, tmp_path, n_planes=2)

    worker = _make_worker(ctrl, autofocus_cfg=_autofocus_cfg(), multi_channel=True)
    worker.camera.recorder_timeout_status = False
    worker.siggen.error = 0

    state = {"acq_index": 0}

    def _fake_acquire_scan() -> bool:
        n_imgs = worker.siggen.waveform_cycles or 1
        imgs = worker.camera.copy_recorder_images(n_imgs)
        frame = np.asarray(imgs[0])
        frame[:] = 30000
        worker._shell.reconstructed_frame = frame
        state["acq_index"] += 1
        return True

    parallel_calls: list[list[tuple[str, float, str]]] = []
    real_parallel = worker.motors.move_axes_parallel

    def _track_parallel(moves: list[tuple[str, float, str]]) -> None:
        parallel_calls.append(list(moves))
        real_parallel(moves)

    update_calls: list[tuple[float, float]] = []
    real_update = AdaptiveFocusController.update

    def _track_update(stage_pos_mm: float, sharpness: float) -> None:
        update_calls.append((stage_pos_mm, sharpness))
        real_update(worker._autofocus_controller, stage_pos_mm, sharpness)

    finished_emits: list[None] = []
    worker.finished.connect(lambda: finished_emits.append(None))
    with (
        patch.object(worker, "acquire_scan", _fake_acquire_scan),
        patch.object(worker.motors, "move_axes_parallel", _track_parallel),
        patch.object(AdaptiveFocusController, "update", side_effect=_track_update),
    ):
        worker.run()

    assert len(finished_emits) == 1
    # One dual-axis move per main plane (before the two channel acquires).
    assert len(parallel_calls) == 2
    for i, moves in enumerate(parallel_calls):
        assert any(m[0] == "camera" for m in moves), f"plane {i} missing camera move"
    # The same camera target is used for both channels because there is
    # only one focus move before the sequential channel acquisitions.
    camera_targets = [next(m[1] for m in p if m[0] == "camera") for p in parallel_calls]
    assert all(t == camera_targets[0] for t in camera_targets), (
        f"camera targets differ across planes: {camera_targets}"
    )
    # Residual is updated once per main plane, using the sharpness from the
    # last channel's frame (reconstructed_frame is aliased to channel 2).
    assert len(update_calls) == 2, (
        f"expected 2 residual updates; got {len(update_calls)}"
    )


# --------------------------------------------------------------------- #
# Sphere-driven stacks: MockStage feeds the focus residual path through
# camera.frame_source (the D-06 sharpness-gradient verification).
# --------------------------------------------------------------------- #


def _attach_sphere_stage(ctrl: Any, sample: Any | None = None) -> Any:
    """Construct a ``MockStage`` on the controller's OWN mock motors and
    lasers (identity — the stage must read the same instances the worker
    moves and ``start_lasers`` energizes) and wire it into
    ``camera.frame_source``.
    """
    from lightsheet.hal import MockSample, MockStage

    if sample is None:
        sample = MockSample()
    stage = MockStage(sample, ctrl._bundle.motors, ctrl._bundle.lasers)
    ctrl.camera.frame_source = stage.frame
    return stage


def _sphere_acquire_scan_preserve(ctrl: Any, worker: Any) -> Callable[[], bool]:
    """Return an ``acquire_scan`` stub that drives the sphere path
    WITHOUT overwriting the frame afterward.

    The ``frame_source`` branch in ``MockCamera.copy_recorder_images``
    is gated on ``new_data_ready`` — the stub MUST set it immediately
    before the copy or the camera returns zero-filled frames and the
    sphere never reaches the sharpness metric (a dead signal). The real
    ``monitor_recorder`` sets this flag after the exposure completes;
    the stub reproduces that ordering. Unlike
    ``_fake_acquire_scan_factory``, this stub stores ``imgs[0]``
    verbatim — drawing over the frame would measure the sharpness of
    the test pattern, not the sphere.
    """

    def _fake_acquire_scan() -> bool:
        n_imgs = worker.siggen.waveform_cycles or 1
        ctrl.camera.new_data_ready = True
        imgs = ctrl.camera.copy_recorder_images(n_imgs)
        assert imgs is not None
        worker._shell.reconstructed_frame = np.asarray(imgs[0])
        return True

    return _fake_acquire_scan


def test_sphere_drives_focus_residual(
    controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """A real StackWorker run whose frames come from MockStage (the
    Gaussian sphere) feeds ``FocusController.update_residual`` sharpness
    values computed from real sphere slices — non-None, non-zero, and
    varying across block boundaries as the camera axis approaches the
    lensing-shifted ideal focus.

    Strategy (b) from the plan: the ``FocusCurve`` camera targets
    interpolate TOWARD the ideal focus (~8.73-8.79 mm for the default
    sample over h = 7.0-10.0 mm), so the per-block camera position
    steps 9.40 -> 8.88 mm and the defocus PSF blur (and therefore the
    measured sharpness) changes at every boundary. The horizontal sweep
    (7.0 -> 10.75 mm, 250 um steps) crosses the sheet at 8.5 mm so the
    slices stay inside the sphere's bright region.
    """
    from lightsheet.focus.controller import FocusController
    from lightsheet.focus.types import FocusCurve

    ctrl = controller
    ctrl._auto_laser1 = True
    ctrl._auto_laser2 = False
    ctrl.laser1_power_pct = 80.0

    # 16 planes, block size 4 -> block boundaries at planes 0, 4, 8, 12
    # -> 3 update_residual calls (boundaries 4, 8, 12).
    _configure_stack_plan(ctrl, tmp_path, n_planes=16)
    ctrl.stack_starting_plane = 7000.0  # um
    ctrl.stack_step = 250.0  # um

    # Curve: camera target walks from a defocused 9.4 mm toward the
    # lensing-shifted ideal (~8.8 mm) as the stage sweeps the sheet.
    curve = FocusCurve(
        stage_pos=(7.0, 10.75),
        camera_pos=(9.4, 8.75),
    )
    worker = _make_worker(ctrl, focus_cfg=_focus_cfg(block_size_n=4), focus_curve=curve)

    _attach_sphere_stage(ctrl)

    worker.camera.recorder_timeout_status = False
    worker.siggen.error = 0

    residual_calls: list[float] = []
    captured_frames: list[np.ndarray] = []
    real_update = FocusController.update_residual

    def _track_residual(self: FocusController, sharpness: float) -> None:
        # Capture the exact frame the metric ran on (the previous
        # plane's reconstructed frame, still held on the shell).
        captured_frames.append(np.asarray(worker._shell.reconstructed_frame).copy())
        residual_calls.append(sharpness)
        real_update(self, sharpness)

    parallel_calls: list[list[tuple[str, float, str]]] = []
    real_parallel = worker.motors.move_axes_parallel

    def _track_parallel(moves: list[tuple[str, float, str]]) -> None:
        parallel_calls.append(list(moves))
        real_parallel(moves)

    finished_emits: list[None] = []
    worker.finished.connect(lambda: finished_emits.append(None))
    with (
        patch.object(
            worker, "acquire_scan", _sphere_acquire_scan_preserve(ctrl, worker)
        ),
        patch.object(FocusController, "update_residual", _track_residual),
        patch.object(worker.motors, "move_axes_parallel", _track_parallel),
    ):
        worker.run()

    assert len(finished_emits) == 1, (
        f"StackWorker.run must emit finished exactly once; got {len(finished_emits)}"
    )

    # One residual update per non-first block boundary: planes 4, 8, 12.
    assert len(residual_calls) == 3, (
        f"expected 3 residual updates; got {len(residual_calls)}"
    )

    # Every recorded sharpness came from a real sphere frame: non-zero
    # (flat/zero frames return exactly 0.0, so this is also the
    # dead-signal guard proving new_data_ready was set in the stub) and
    # equal to the metric recomputed from the captured frame.
    from lightsheet.focus.sharpness import frame_sharpness_variance

    for i, (sharp, frame) in enumerate(
        zip(residual_calls, captured_frames, strict=True)
    ):
        assert sharp > 0.0, (
            f"residual call {i} sharpness must be non-zero on a real "
            f"sphere slice; got {sharp}"
        )
        assert sharp == pytest.approx(frame_sharpness_variance(frame)), (
            f"residual call {i} must carry the metric of the actual frame"
        )
    # The captured frames are the sphere's slices, not a constant fill:
    # they differ as the stage sweeps and the defocus blur changes.
    assert not np.array_equal(captured_frames[0], captured_frames[-1]), (
        "sphere frames must differ across blocks (stage sweep + blur)"
    )

    # D-06 gradient: the defocus/lensing model produces distinct
    # sharpness values across blocks (the camera walks toward focus).
    assert len(set(residual_calls)) > 1, (
        f"sharpness must vary across blocks; got {residual_calls}"
    )

    # The residual actually moved (later blocks measure sharper frames
    # than the stored reference, so the trim is non-zero).
    assert worker._focus_controller.residual_mm != 0.0, (
        "residual must respond to the sphere sharpness gradient"
    )

    # Trajectory: 4 samples (one per block boundary); first has no
    # sharpness, the rest mirror the recorded calls.
    traj = ctrl._fs.focus_trajectory
    assert len(traj) == 4, f"expected 4 focus samples; got {len(traj)}"
    assert traj[0].sharpness_metric is None
    for i, call in enumerate(residual_calls, start=1):
        assert traj[i].sharpness_metric == pytest.approx(call), (
            f"sample {i} sharpness must equal the update_residual arg"
        )

    # All camera targets stayed inside the camera axis travel limits
    # (the move_axes_parallel path is the real MockMotor contract).
    cam_lo = worker.motors.camera.get_limit_low("mm")
    cam_hi = worker.motors.camera.get_limit_high("mm")
    for sample in traj:
        assert cam_lo <= sample.applied_camera_pos_mm <= cam_hi, (
            f"applied camera position {sample.applied_camera_pos_mm} mm "
            f"outside limits [{cam_lo}, {cam_hi}]"
        )
    for moves in parallel_calls:
        cam_target = next(m[1] for m in moves if m[0] == "camera")
        assert cam_lo <= cam_target <= cam_hi
