"""Physical-safety regressions: the reactive state model stays outside the
kill path and cannot defeat active-based laser shutdown.

These tests use the real ``controller`` fixture (real
``Controller_MainWindow`` + real ``HardwareManager`` against the mock HAL)
and prove, at the behavior level:

1. ``updateUi_estop_pressed`` is synchronous, GUI-thread, lock-free, and
   has NO dependency on the state model — it works even when every model
   method is configured to raise on access.
2. ``HardwareManager.stop_lasers`` reads the live ``laser.active`` flags,
   so a mid-run model edit (auto-laser flags cleared, laser intent turned
   off) cannot leave an energized laser on.
3. An applied-state delivery (``apply_worker_snapshot``) cannot clear or
   re-arm ``estop_event``, and no energizing/power write proceeds while
   the event is set.
4. The four laser amplitude/toggle actions still spawn daemon
   ``threading.Thread`` objects (never QThreads), while the E-stop path
   itself creates no thread.
"""

from __future__ import annotations

import dataclasses
import threading
import types
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest

pytest.importorskip("PySide6")

from pytestqt.qtbot import QtBot

import lightsheet.gui.panels.laser_panel as laser_panel_module
import lightsheet.gui.shell.controller as controller_module
from lightsheet.gui.workers import PreviewWorker, StackWorker
from lightsheet.state import AppliedMicroscopeSnapshot, MicroscopeSnapshot

if TYPE_CHECKING:
    from lightsheet.gui.shell.controller import Controller_MainWindow


class _ExplodingState:
    """Stand-in that raises on ANY attribute access.

    Replacing ``ctrl.state`` with this proves the kill path has zero
    model dependency: if any code in ``updateUi_estop_pressed`` touches
    the model — read or write — the test fails immediately.
    """

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(
            f"E-stop kill path touched the state model (.{name}) — the "
            "kill path must stay model-independent, lock-free, and "
            "synchronous on the GUI thread"
        )


def _snapshot_with(
    ctrl: Controller_MainWindow, **overrides: Any
) -> MicroscopeSnapshot:
    """Return the current model snapshot with selected fields replaced."""
    return dataclasses.replace(ctrl.state.snapshot(), **overrides)


# --------------------------------------------------------------------------- #
# E-stop: synchronous, GUI-thread, model-independent.
# --------------------------------------------------------------------------- #


def test_estop_kill_path_never_touches_state_model(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """With ``ctrl.state`` replaced by an object that raises on any
    access, the real ``updateUi_estop_pressed`` still sets
    ``estop_event``, drives every laser's ``off()`` synchronously on the
    GUI thread before returning, surfaces per-laser off failures, and
    emits the actuated warning."""
    ctrl = controller
    laser0 = ctrl.lasers[0]
    laser1 = ctrl.lasers[1]
    gui_thread = threading.current_thread()

    off_threads: list[threading.Thread] = []
    real_off0 = laser0.off
    real_off1 = laser1.off

    def _off0() -> None:
        off_threads.append(threading.current_thread())
        real_off0()
        # Simulate a backend that reports an off failure on its error
        # surface (the contract: off() never raises, it sets .error).
        laser0.error = 1
        laser0.error_message = "simulated off failure"

    def _off1() -> None:
        off_threads.append(threading.current_thread())
        real_off1()

    messages: list[str] = []
    ctrl.sig_message.connect(lambda msg: messages.append(msg))

    try:
        with (
            patch.object(ctrl, "state", _ExplodingState()),
            patch.object(laser0, "off", side_effect=_off0),
            patch.object(laser1, "off", side_effect=_off1),
        ):
            ctrl.updateUi_estop_pressed()

        assert ctrl.estop_event.is_set()
        # Both off() calls completed synchronously on the GUI thread
        # before the handler returned.
        assert off_threads == [gui_thread, gui_thread]
        # Per-laser off failure still surfaces and the flag is cleared.
        assert any("STILL BE ON" in m for m in messages), (
            "E-stop must warn when a laser's off() reports a failure"
        )
        assert laser0.error == 0
        # The actuated operator warning still fires.
        assert any("E-STOP actuated" in m for m in messages)
        assert not laser0.active
        assert not laser1.active
    finally:
        ctrl.estop_event.clear()


# --------------------------------------------------------------------------- #
# stop_lasers: live-active shutdown regardless of model flags.
# --------------------------------------------------------------------------- #


def test_stop_lasers_turns_off_active_laser_after_model_flags_cleared(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """Energize laser 1 through the snapshot-aware ``start_lasers``, then
    mutate every model laser-intent flag to off; ``stop_lasers`` must
    still drive the active laser off — it reads live ``laser.active``,
    never the model."""
    ctrl = controller
    laser0 = ctrl.lasers[0]
    laser1 = ctrl.lasers[1]

    snap = _snapshot_with(
        ctrl,
        auto_lasers=(True, False),
        laser_power_pct=(50.0, 50.0),
    )
    ctrl._hw.start_lasers(snap)
    assert laser0.active is True
    assert laser1.active is False

    # Mid-run model edits: the operator cleared every laser intent. A
    # flag-based stop would now skip laser 1 and leave it energized.
    ctrl.state.set_auto_lasers(False, False)
    ctrl.state.set_laser_enabled(0, False)
    ctrl.state.set_laser_enabled(1, False)
    ctrl.state.set_laser_power_pct(0, 0.0)
    ctrl.state.set_laser_power_pct(1, 0.0)

    with patch.object(laser0, "off", wraps=laser0.off) as spy_off0:
        ctrl._hw.stop_lasers()

    spy_off0.assert_called_once()
    assert laser0.active is False
    assert laser1.active is False


def test_stop_lasers_turns_off_both_active_lasers_after_model_flags_cleared(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """Same as above but with both lasers energized: a snapshot selecting
    both auto-lasers energizes both, and after the model flags are
    cleared ``stop_lasers`` turns off every active laser."""
    ctrl = controller
    laser0 = ctrl.lasers[0]
    laser1 = ctrl.lasers[1]

    snap = _snapshot_with(
        ctrl,
        auto_lasers=(True, True),
        laser_power_pct=(50.0, 50.0),
    )
    ctrl._hw.start_lasers(snap)
    assert laser0.active is True
    assert laser1.active is True

    ctrl.state.set_auto_lasers(False, False)
    ctrl.state.set_laser_enabled(0, False)
    ctrl.state.set_laser_enabled(1, False)

    with (
        patch.object(laser0, "off", wraps=laser0.off) as spy_off0,
        patch.object(laser1, "off", wraps=laser1.off) as spy_off1,
    ):
        ctrl._hw.stop_lasers()

    spy_off0.assert_called_once()
    spy_off1.assert_called_once()
    assert laser0.active is False
    assert laser1.active is False


# --------------------------------------------------------------------------- #
# E-stop set: applied-state delivery cannot re-arm; no later energize/write.
# --------------------------------------------------------------------------- #


def test_applied_state_delivery_cannot_rearm_estop(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """While ``estop_event`` is set, delivering a worker applied-state
    snapshot must not clear the event, and the energizing paths
    (``start_lasers``, ``_toggle_laser1``, ``_write_laser1_power``) must
    not perform any HAL write."""
    ctrl = controller
    laser0 = ctrl.lasers[0]
    laser1 = ctrl.lasers[1]

    ctrl.estop_event.set()
    try:
        # A queued applied-state payload arrives after the kill — folding
        # it into the model must not clear or re-arm estop_event.
        ctrl.state.apply_worker_snapshot(
            AppliedMicroscopeSnapshot(
                laser_power_pct=(90.0, 90.0),
                laser_enabled=(True, True),
                lightsheet_line_time_s=2.0,
            )
        )
        assert ctrl.estop_event.is_set()

        snap = _snapshot_with(ctrl, auto_lasers=(True, True))
        with (
            patch.object(laser0, "on") as spy_on0,
            patch.object(laser1, "on") as spy_on1,
            patch.object(laser0, "set_power") as spy_set0,
            patch.object(laser1, "set_power") as spy_set1,
        ):
            ctrl._hw.start_lasers(snap)
            ctrl._hw._toggle_laser1()
            ctrl._hw._toggle_laser2()
            ctrl._hw._write_laser1_power(50.0)
            ctrl._hw._write_laser2_power(50.0)

        spy_on0.assert_not_called()
        spy_on1.assert_not_called()
        spy_set0.assert_not_called()
        spy_set1.assert_not_called()
        assert laser0.active is False
        assert laser1.active is False
        assert ctrl.estop_event.is_set()
    finally:
        ctrl.estop_event.clear()


def test_preview_worker_estop_before_energize_makes_no_laser_write(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """With ``estop_event`` set before a preview run starts, the real
    ``PreviewWorker.run`` returns before ``start_lasers`` and emits
    ``finished`` exactly once — the estop-set path performs no energizing
    write even though the spawn snapshot selects both auto-lasers."""
    ctrl = controller
    laser0 = ctrl.lasers[0]
    laser1 = ctrl.lasers[1]

    ctrl.estop_event.set()
    try:
        snap = _snapshot_with(
            ctrl,
            auto_lasers=(True, True),
            laser_power_pct=(50.0, 50.0),
        )
        worker = PreviewWorker(ctrl._bundle, ctrl._hw, ctrl, snapshot=snap)
        ctrl.preview_mode_started = True

        finished_emits: list[None] = []
        worker.finished.connect(lambda: finished_emits.append(None))

        with (
            patch.object(
                ctrl._hw, "start_lasers", wraps=ctrl._hw.start_lasers
            ) as spy_start,
            patch.object(laser0, "on") as spy_on0,
            patch.object(laser1, "on") as spy_on1,
        ):
            worker.run()

        spy_start.assert_not_called()
        spy_on0.assert_not_called()
        spy_on1.assert_not_called()
        assert laser0.active is False
        assert laser1.active is False
        assert len(finished_emits) == 1
    finally:
        ctrl.estop_event.clear()
        ctrl.preview_mode_started = False


def test_stack_worker_estop_before_energize_makes_no_laser_write(
    qtbot: QtBot, controller: Controller_MainWindow, tmp_path: Any
) -> None:
    """With ``estop_event`` set, the real ``StackWorker.run`` skips the
    pre-loop ``start_lasers`` call and breaks at the first plane-boundary
    poll — no energizing write and ``finished`` fires exactly once."""
    ctrl = controller
    laser0 = ctrl.lasers[0]
    laser1 = ctrl.lasers[1]

    ctrl.estop_event.set()
    try:
        ctrl.saving_allowed = False
        ctrl.number_of_planes = 3
        ctrl.stack_mode_started = True
        ctrl.stack_starting_plane = 0.0
        ctrl.stack_step = 10

        snap = _snapshot_with(
            ctrl,
            auto_lasers=(True, False),
            laser_power_pct=(50.0, 50.0),
        )
        worker = StackWorker(ctrl._bundle, ctrl._hw, ctrl, snapshot=snap)
        worker.camera.recorder_timeout_status = False
        worker.siggen.error = 0

        finished_emits: list[None] = []
        worker.finished.connect(lambda: finished_emits.append(None))

        with (
            patch.object(
                ctrl._hw, "start_lasers", wraps=ctrl._hw.start_lasers
            ) as spy_start,
            patch.object(laser0, "on") as spy_on0,
            patch.object(laser1, "on") as spy_on1,
            patch.object(worker, "acquire_scan") as mock_acquire,
        ):
            worker.run()

        spy_start.assert_not_called()
        spy_on0.assert_not_called()
        spy_on1.assert_not_called()
        mock_acquire.assert_not_called()
        assert laser0.active is False
        assert laser1.active is False
        assert len(finished_emits) == 1
    finally:
        ctrl.estop_event.clear()
        ctrl.stack_mode_started = False


# --------------------------------------------------------------------------- #
# Daemon-thread regression: laser actions stay threading.Thread(daemon=True);
# the E-stop path creates no thread at all.
# --------------------------------------------------------------------------- #


class _RecordingThread:
    """Constructor-recording stand-in for ``threading.Thread``."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.kwargs = kwargs
        self.started = False

    def start(self) -> None:
        self.started = True


def test_laser_actions_spawn_daemon_threads_and_estop_spawns_none(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """The two amplitude writes and two toggle actions must construct
    ``threading.Thread`` objects with ``daemon=True`` targeting the
    HardwareManager write/toggle methods — never QThreads (a queued-slot
    dispatch window would re-energize a Class IIIB laser past the kill
    path). The E-stop handler itself must not construct any thread."""
    ctrl = controller
    panel = ctrl.laser_panel

    # Skip the first-energize confirmation dialogs so the toggle handlers
    # reach the thread-spawn line directly.
    ctrl._laser1_first_energize_done = True
    ctrl._laser2_first_energize_done = True

    created: list[_RecordingThread] = []

    def _thread_ctor(*args: Any, **kwargs: Any) -> _RecordingThread:
        t = _RecordingThread(*args, **kwargs)
        created.append(t)
        return t

    fake_threading = types.SimpleNamespace(Thread=_thread_ctor)

    with patch.object(laser_panel_module, "threading", fake_threading):
        panel._apply_laser1_amplitude()
        panel._apply_laser2_amplitude()
        panel.ui.pushButton_laserOneToggle.setChecked(True)
        panel.laser1_toggle_button()
        panel.ui.pushButton_laserTwoToggle.setChecked(True)
        panel.laser2_toggle_button()

    assert len(created) == 4
    for t in created:
        assert t.kwargs.get("daemon") is True, (
            "laser actions must spawn daemon threading.Threads"
        )
        assert t.started is True

    assert created[0].kwargs["target"] == ctrl._hw._write_laser1_power
    assert created[1].kwargs["target"] == ctrl._hw._write_laser2_power
    assert created[2].kwargs["target"] == ctrl._hw._toggle_laser1
    assert created[3].kwargs["target"] == ctrl._hw._toggle_laser2

    # The E-stop path itself creates no thread — patching threading in the
    # controller module must record zero Thread constructions.
    with patch.object(controller_module, "threading", fake_threading):
        ctrl.updateUi_estop_pressed()
    assert len(created) == 4, "E-stop must not spawn any thread"
    ctrl.estop_event.clear()
