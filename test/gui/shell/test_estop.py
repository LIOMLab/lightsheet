"""
Stdlib threading.Event semantics tests for the E-stop cooperative-abort path.

These tests document the exact threading.Event behavior that
lightsheet/gui/controller.py relies on for the E-stop:

  - The system starts ARMED: a fresh threading.Event() is clear (not set),
    so worker loops run normally.
  - Re-pressing E-stop is safe: calling .set() twice on the same Event leaves
    it set with no error (idempotent panic control).
  - The Arm/Reset sequence clears the Event: .set() then .clear() leaves it
    unset, so worker loops resume on the next acquisition.
  - A worker loop that polls `if estop_event.is_set(): break` at the top of
    each iteration exits immediately (zero body executions) when the Event is
    pre-set — validating the poll-point placement logic independent of the
    real PySide6 GUI, which cannot be instantiated on this Mac.

The kill-path wiring itself (updateUi_estop_pressed drives both lasers off,
every worker polls estop_event.is_set()) is NOT verified by static-source
greps — those are fragile and exercise no code. See AGENTS.md §5: when a
class cannot be instantiated on Mac, exercise the real method via exec of
its extracted body against a Mock stand-in, or test the HAL logic in
isolation. Do not grep the source.

regression gate (god-object split): HardwareManager must
NOT declare an estop/kill/e_stop method — the E-stop kill path stays in the
shell with a direct list[ILaser] ref, lock-free, on the GUI thread. A future
maintainer who sees HardwareManager.estop() will be tempted to queue/thread
it — the single most safety-critical regression risk.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lightsheet.gui.shell.controller import Controller_MainWindow

import threading
from typing import Any
from unittest.mock import patch


def test_estop_event_starts_clear() -> None:
    """A fresh threading.Event (mirroring self.estop_event's initial state)
    is unset — the system starts ARMED, not actuated."""
    estop_event = threading.Event()
    assert estop_event.is_set() is False

def test_estop_event_set_is_idempotent() -> None:
    """Calling .set() twice leaves the Event set with no error — re-pressing
    E-stop is safe and does not raise."""
    estop_event = threading.Event()
    estop_event.set()
    estop_event.set()  # idempotent — no exception
    assert estop_event.is_set() is True

def test_estop_event_clear_after_set() -> None:
    """The Arm/Reset sequence: .set() then .clear() leaves the Event unset,
    so worker loops resume on the next acquisition."""
    estop_event = threading.Event()
    estop_event.set()
    estop_event.clear()
    assert estop_event.is_set() is False

def test_worker_poll_logic_breaks_on_set() -> None:
    """A worker loop polling `if estop_event.is_set(): break` at the top of
    each iteration runs zero body iterations when the Event is pre-set.

    This validates the poll-point placement logic (poll BEFORE the frame
    acquisition work, not after) independent of the real GUI/Qt — the same
    shape used in live_mode_worker, single_mode_worker, and stack_mode_worker.
    """
    estop_event = threading.Event()
    estop_event.set()  # E-stop actuated before the loop starts

    iterations = 0
    stop_flag = True  # mimic live_mode_started gating entry
    while stop_flag:
        if estop_event.is_set():
            break
        iterations += 1
        # Guard against an accidental infinite loop if the poll logic is wrong
        if iterations > 10:
            break

    assert iterations == 0

# --------------------------------------------------------------------------- #
# regression gate — HardwareManager must NOT own an estop method.
# The E-stop kill path stays in the shell (updateUi_estop_pressed) with a
# direct list[ILaser] ref, lock-free, on the GUI thread. This gate runs at
# every future commit touching lightsheet/gui/hardware_manager.py.
# --------------------------------------------------------------------------- #

def test_hardware_manager_has_no_estop_method() -> None:
    """HardwareManager must NOT declare an estop/kill/e_stop method — the
    E-stop kill path stays in the shell (safety anti-pattern)."""
    from lightsheet.gui.coordinators.hardware_manager import HardwareManager

    assert not hasattr(HardwareManager, "estop"), (
        "HardwareManager must NOT declare an estop method (safety anti-pattern) "
        "— the E-stop kill path stays in the shell, lock-free on the GUI thread."
    )
    assert not hasattr(HardwareManager, "kill"), (
        "HardwareManager must NOT declare a kill method"
    )
    assert not hasattr(HardwareManager, "e_stop"), (
        "HardwareManager must NOT declare an e_stop method"
    )

# --------------------------------------------------------------------------- #
# regression gate — MotorController must NOT own an estop method.
# MotorController is a motion collaborator (motor-move + focus/interpolation-
# display slots), NOT a safety kill-path owner. The E-stop kill path stays in
# the shell (updateUi_estop_pressed) with a direct list[ILaser] ref, lock-free,
# on the GUI thread. A future maintainer who sees MotorController.estop() will
# be tempted to queue/thread it — the single most safety-critical regression
# risk. Mirrors the HardwareManager anti-pattern check.
# --------------------------------------------------------------------------- #

def test_motor_controller_has_no_estop_method() -> None:
    """MotorController must NOT declare an estop/kill/e_stop method — motion
    collaborators are not safety kill-path owners (safety anti-pattern)."""
    from lightsheet.gui.coordinators.motor_controller import MotorController

    assert not hasattr(MotorController, "estop"), (
        "MotorController must NOT declare an estop method (safety anti-pattern) "
        "— the E-stop kill path stays in the shell, lock-free on the GUI thread."
    )
    assert not hasattr(MotorController, "kill"), (
        "MotorController must NOT declare a kill method"
    )
    assert not hasattr(MotorController, "e_stop"), (
        "MotorController must NOT declare an e_stop method"
    )

# --------------------------------------------------------------------------- #
# regression gate — dock presentation controllers must NOT own an estop method.
# The E-stop kill path stays in the shell (updateUi_estop_pressed); moving it
# into a presentation-only dock controller would hide the laser-off calls and
# risk threading them.
# --------------------------------------------------------------------------- #

def test_adaptive_dock_controller_has_no_estop_method() -> None:
    """AdaptiveDockController must NOT declare an estop/kill/e_stop method —
    the E-stop kill path stays in the shell, lock-free on the GUI thread."""
    from lightsheet.gui.coordinators.adaptive_dock_controller import (
        AdaptiveDockController,
    )

    for name in ("estop", "kill", "e_stop"):
        assert not hasattr(AdaptiveDockController, name), (
            f"AdaptiveDockController must NOT declare a {name} method — "
            "the E-stop kill path stays in the shell."
        )

def test_focus_dock_controller_has_no_estop_method() -> None:
    """FocusDockController must NOT declare an estop/kill/e_stop method —
    the E-stop kill path stays in the shell, lock-free on the GUI thread."""
    from lightsheet.gui.coordinators.focus_dock_controller import (
        FocusDockController,
    )

    for name in ("estop", "kill", "e_stop"):
        assert not hasattr(FocusDockController, name), (
            f"FocusDockController must NOT declare a {name} method — "
            "the E-stop kill path stays in the shell."
        )

# --------------------------------------------------------------------------- #
# Adaptive focus E-stop poll points
# --------------------------------------------------------------------------- #

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

def _configure_autofocus_stack_plan(
    ctrl: Any, tmp_path: Any, n_planes: int = 3
) -> None:
    """Configure a valid 3-plane single-channel stack plan for autofocus."""
    ctrl.saving_allowed = True
    ctrl.number_of_planes = n_planes
    ctrl.stack_mode_started = True
    ctrl.stack_starting_plane = 0.0
    ctrl.stack_step = 10
    ctrl.save_format = "hdf5"
    ctrl.save_directory = str(tmp_path)
    ctrl.save_filepath = str(tmp_path / "estop_autofocus")
    ctrl.save_description = "autofocus estop sample"
    ctrl.current_horizontal_position_text = "0.0"
    ctrl.current_vertical_position_text = "0.0"
    ctrl.current_camera_position_text = "0.0"
    ctrl.save_panel.ui.radioButton_saveAllCrop.setChecked(False)
    ctrl.save_panel.ui.radioButton_saveAllFull.setChecked(False)

def _make_autofocus_worker(ctrl: Any, **overrides: Any) -> Any:
    """Build a single-channel StackWorker with the supplied autofocus config."""
    from lightsheet.gui.workers import StackWorker

    return StackWorker(
        ctrl._bundle,
        ctrl._hw,
        ctrl,
        save_description="autofocus estop sample",
        save_stitch_blend=False,
        save_all_crop=False,
        save_all_full=False,
        multi_channel=False,
        adaptive_cfg=None,
        autofocus_cfg=_autofocus_cfg(**overrides),
    )

def test_autofocus_estop_after_first_move_prevents_acquire(
    controller: Controller_MainWindow,
    tmp_path: Any,
) -> None:
    """Setting the E-stop after the first adaptive focus move prevents the
    frame acquisition from running and the loop breaks cleanly."""
    ctrl = controller
    _configure_autofocus_stack_plan(ctrl, tmp_path, n_planes=3)

    worker = _make_autofocus_worker(ctrl)
    setattr(worker.camera, "recorder_timeout_status", False)
    setattr(worker.siggen, "error", 0)

    real_parallel = worker.motors.move_axes_parallel
    parallel_calls: list[list[tuple[str, float, str]]] = []

    def _track_and_stop(moves: list[tuple[str, float, str]]) -> None:
        # Trip the E-stop on the very first dual-axis focus move.
        if len(parallel_calls) == 0:
            ctrl.estop_event.set()
        parallel_calls.append(list(moves))
        real_parallel(moves)

    finished_emits: list[None] = []
    worker.finished.connect(lambda: finished_emits.append(None))
    with (
        patch.object(worker, "acquire_scan") as mock_acquire,
        patch.object(worker.motors, "move_axes_parallel", _track_and_stop),
    ):
        mock_acquire.return_value = True
        worker.run()

    try:
        assert len(finished_emits) == 1
        assert len(parallel_calls) == 1
        assert mock_acquire.call_count == 0, (
            "E-stop before acquire must prevent the scan from starting"
        )
    finally:
        ctrl.estop_event.clear()

def test_autofocus_estop_set_before_acquire_breaks_loop(
    controller: Controller_MainWindow,
    tmp_path: Any,
) -> None:
    """If the E-stop is already actuated, the adaptive focus loop breaks
    before any motor move or laser/arming acquire step."""
    ctrl = controller
    _configure_autofocus_stack_plan(ctrl, tmp_path, n_planes=3)

    worker = _make_autofocus_worker(ctrl)
    ctrl.estop_event.set()
    setattr(worker.camera, "recorder_timeout_status", False)
    setattr(worker.siggen, "error", 0)

    finished_emits: list[None] = []
    worker.finished.connect(lambda: finished_emits.append(None))
    with (
        patch.object(worker, "acquire_scan") as mock_acquire,
        patch.object(worker.motors, "move_axes_parallel") as mock_parallel,
    ):
        worker.run()

    try:
        assert len(finished_emits) == 1
        assert mock_parallel.call_count == 0
        assert mock_acquire.call_count == 0
    finally:
        ctrl.estop_event.clear()
