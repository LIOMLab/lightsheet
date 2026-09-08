"""Stack pause lifecycle tests.

Covers the plane-boundary pause: the shell ``pause_requested`` event (a
peer of ``estop_event``, never a wrapper), the Pause button enable/latch
semantics, the ``STACK PAUSING`` mode badge, the worker's loop-top poll
and ``paused`` manifest lifecycle, E-stop precedence over pause, and the
pause→resume path through a fresh worker with a ``start_plane`` offset.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest
from pytestqt.qtbot import QtBot

pytest.importorskip("PySide6")

from lightsheet.gui.workers import StackWorker
from lightsheet.hal import DeviceBundle

if TYPE_CHECKING:
    from lightsheet.gui.shell.controller import Controller_MainWindow


def _make_bundle() -> DeviceBundle:
    from test.helpers.factories import make_bundle

    return make_bundle()


def _make_shell(bundle: DeviceBundle, n_planes: int) -> Mock:
    """Minimal mock shell stand-in (same pattern as test_stack_resume.py)."""
    shell = Mock()
    shell.lasers = bundle.lasers
    shell.stack_mode_started = True
    shell.estop_event = threading.Event()
    shell.pause_requested = threading.Event()
    shell.saving_allowed = False
    shell.number_of_planes = n_planes
    shell.stack_starting_plane = 0.0
    shell.stack_step = 10.0
    shell.reconstructed_frame = None
    shell.reconstructed_frames = {}
    shell._fs = Mock()
    shell.state.snapshot.return_value = None
    return shell


def _make_worker(
    bundle: DeviceBundle, shell: Mock, n_planes: int, start_plane: int = 0
) -> StackWorker:
    worker = StackWorker(
        bundle,
        Mock(),
        shell,
        save_description="pause test",
        start_plane=start_plane,
    )
    worker.acquire_scan = Mock(return_value=True)
    return worker


def test_pause_requested_is_separate_event(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """The shell carries a dedicated threading.Event for pause — it must
    never alias or wrap estop_event."""
    assert isinstance(controller.pause_requested, threading.Event)
    assert isinstance(controller.estop_event, threading.Event)
    assert controller.pause_requested is not controller.estop_event
    controller.pause_requested.set()
    assert controller.pause_requested.is_set()
    assert not controller.estop_event.is_set()
    controller.pause_requested.clear()
    assert not controller.pause_requested.is_set()


def test_pause_button_disabled_when_idle(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """With no stack running, the Pause control stays latched off."""
    btn = controller.stack_panel.ui.pushButton_acqPauseStack
    assert not btn.isEnabled()


def test_pause_click_sets_event_and_latches_button(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """Clicking Pause while a stack runs sets pause_requested, disables
    the button, and shows the STACK PAUSING badge."""
    btn = controller.stack_panel.ui.pushButton_acqPauseStack
    controller.stack_mode_started = True
    controller.number_of_planes = 5
    btn.setEnabled(True)

    controller.acquisition_panel.on_stack_pause_clicked()

    assert controller.pause_requested.is_set()
    assert not btn.isEnabled()
    assert "PAUSING" in controller.ui.label_modeBadge.text()
    controller.pause_requested.clear()
    controller.stack_mode_started = False


def test_estop_does_not_set_pause(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """The E-stop kill path touches only estop_event and lasers — pause
    is never part of the E-stop path."""
    controller.updateUi_estop_pressed()
    assert controller.estop_event.is_set()
    assert not controller.pause_requested.is_set()


def test_pause_poll_breaks_at_plane_boundary(qtbot: QtBot) -> None:
    """A set pause_requested breaks the plane loop before the next plane
    and finalizes the manifest as paused."""
    bundle = _make_bundle()
    shell = _make_shell(bundle, n_planes=5)
    shell.saving_allowed = True
    worker = _make_worker(bundle, shell, n_planes=5)

    moves: list[float] = []
    orig = worker.motors.horizontal.move_absolute_position

    def _rec(pos: float, units: str) -> None:
        moves.append(pos)
        orig(pos, units)
        # Pause lands mid-run: the next loop-top poll must break.
        if len(moves) == 1:
            shell.pause_requested.set()

    worker.motors.horizontal.move_absolute_position = _rec  # ty: ignore[invalid-assignment]

    finished: list[None] = []
    worker.finished.connect(lambda: finished.append(None))
    worker.run()

    assert moves == [0.0]  # one plane committed, then the break
    assert worker._run_completed is False
    assert shell._fs.stop_saving.call_args.kwargs.get("lifecycle") == "paused"
    # The event is cleared by teardown so a follow-on run starts unpaused.
    assert not shell.pause_requested.is_set()
    assert len(finished) == 1


def test_estop_precedence_over_pause(qtbot: QtBot) -> None:
    """If E-stop is actuated after a pause request, the run finalizes as
    interrupted — the kill path always wins."""
    bundle = _make_bundle()
    shell = _make_shell(bundle, n_planes=5)
    shell.saving_allowed = True
    worker = _make_worker(bundle, shell, n_planes=5)

    shell.pause_requested.set()
    shell.estop_event.set()

    worker.run()

    assert worker._run_completed is False
    assert shell._fs.stop_saving.call_args.kwargs.get("lifecycle") == "interrupted"


def test_pause_resume_end_to_end(
    qtbot: QtBot, controller: Controller_MainWindow, tmp_path: Path, request: object
) -> None:
    """Full pause→resume: pause a fixed 3-plane stack after the first
    plane, verify the sidecar manifest reads ``paused`` with a committed
    cursor, then resume on a fresh controller + fresh worker from the
    manifest cursor and verify the run completes."""
    import numpy as np

    from lightsheet.resume import manifest_path_for, read_manifest

    ctrl = controller
    ctrl.saving_allowed = True
    ctrl.number_of_planes = 3
    ctrl.stack_mode_started = True
    ctrl.stack_starting_plane = 0.0
    ctrl.stack_ending_plane = 20.0
    ctrl.stack_step = 10
    ctrl.save_format = "hdf5"
    ctrl.save_directory = str(tmp_path)
    ctrl.save_filepath = str(tmp_path / "pause_run")
    ctrl.current_horizontal_position_text = "0.0"
    ctrl.current_vertical_position_text = "0.0"
    ctrl.current_camera_position_text = "0.0"
    ctrl.save_panel.ui.radioButton_saveAllCrop.setChecked(True)
    ctrl.save_panel.ui.radioButton_saveAllFull.setChecked(False)

    worker = StackWorker(
        ctrl._bundle,
        ctrl._hw,
        ctrl,
        save_description="pause integration",
        save_stitch_blend=False,
        save_all_crop=True,
        save_all_full=False,
        multi_channel=False,
    )

    # Commit one plane, then request the pause — the next loop-top poll
    # must break before the second plane's motor move.
    planes_done: list[int] = []

    def _fake_acquire_scan() -> bool:
        planes_done.append(1)
        # Crop save mode reads the raw camera buffer (tiles, y, x).
        ctrl.buffer = np.zeros((1, 4, 4), dtype=np.uint16)
        ctrl.reconstructed_frame = np.zeros((4, 4), dtype=np.uint16)
        if len(planes_done) == 1:
            ctrl.pause_requested.set()
        return True

    worker.acquire_scan = _fake_acquire_scan  # ty: ignore[invalid-assignment]
    worker.camera.recorder_timeout_status = False
    worker.siggen.error = 0

    worker.run()

    # Teardown ran: lasers are off and the event was cleared.
    assert not any(laser.active for laser in ctrl.lasers)
    assert not ctrl.pause_requested.is_set()
    assert worker._run_completed is False

    # The sidecar manifest finalized as paused with a durable cursor.
    fs = ctrl._fs.frame_saver
    manifest_path = manifest_path_for(fs.filenames_lists[0][0])
    manifest = read_manifest(manifest_path)
    assert manifest is not None, f"no manifest at {manifest_path}"
    assert manifest.state == "paused"
    hdf5_cursors = manifest.cursors.get("hdf5", {})
    assert hdf5_cursors, "paused manifest must carry an hdf5 cursor"
    resume_plane = min(hdf5_cursors.values())
    assert resume_plane == 1, (
        f"one plane must be durably committed before the pause; "
        f"got cursor {resume_plane}"
    )
    assert manifest.last_motor_positions, (
        "paused manifest must record the motor positions at pause time"
    )

    # --- Simulated app restart: new controller, fresh worker ---------
    from test.fixtures.controller import _build_controller
    from test.helpers.factories import make_bundle

    ctrl2 = _build_controller(make_bundle(), qtbot, request)
    ctrl2.saving_allowed = True
    ctrl2.number_of_planes = 3
    ctrl2.stack_mode_started = True
    ctrl2.stack_starting_plane = 0.0
    ctrl2.stack_ending_plane = 20.0
    ctrl2.stack_step = 10
    ctrl2.save_format = "hdf5"
    ctrl2.save_directory = str(tmp_path)
    ctrl2.save_filepath = str(tmp_path / "pause_run")
    ctrl2.current_horizontal_position_text = "0.0"
    ctrl2.current_vertical_position_text = "0.0"
    ctrl2.current_camera_position_text = "0.0"
    ctrl2.save_panel.ui.radioButton_saveAllCrop.setChecked(True)
    ctrl2.save_panel.ui.radioButton_saveAllFull.setChecked(False)

    resumed = StackWorker(
        ctrl2._bundle,
        ctrl2._hw,
        ctrl2,
        save_description="pause integration",
        save_stitch_blend=False,
        save_all_crop=True,
        save_all_full=False,
        multi_channel=False,
        start_plane=resume_plane,
        resume_manifest=manifest,
    )

    def _fake_acquire_scan2() -> bool:
        ctrl2.buffer = np.zeros((1, 4, 4), dtype=np.uint16)
        ctrl2.reconstructed_frame = np.zeros((4, 4), dtype=np.uint16)
        return True

    resumed.acquire_scan = _fake_acquire_scan2  # ty: ignore[invalid-assignment]
    resumed.camera.recorder_timeout_status = False
    resumed.siggen.error = 0

    resumed.run()

    assert resumed._run_completed is True
    fs2 = ctrl2._fs.frame_saver
    final = read_manifest(manifest_path_for(fs2.filenames_lists[0][0]))
    assert final is not None
    assert final.state == "completed"
