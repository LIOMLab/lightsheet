"""Branch coverage for the defensive signal/dock wiring in
`lightsheet/gui/panels/acquisition_panel.py`.

These tests exercise the queue-active post-stack path and the reused
QThread/worker signal guard branches that the main GUI tests do not hit.
A fake `QThread` and `StackWorker` are used so the tests run without
starting real worker threads.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest
from PySide6.QtCore import SIGNAL, QObject, QThread, Signal

pytest.importorskip("PySide6")

import lightsheet.gui.panels.acquisition_panel as _ap

if TYPE_CHECKING:
    from lightsheet.gui.shell.controller import Controller_MainWindow


def _configure_for_spawn(ctrl: Controller_MainWindow) -> None:
    """Set the minimal stack plan fields expected by _spawn_stack_worker."""
    ctrl.stack_first_plane_set = True
    ctrl.stack_last_plane_set = True
    ctrl.stack_starting_plane = 0.0
    ctrl.stack_ending_plane = 100.0
    ctrl.number_of_planes = 2
    ctrl.saving_allowed = True


class _FakeQThread(QThread):
    """QThread stand-in that never starts a real thread."""

    def start(self, *args: Any, **kwargs: Any) -> None:
        pass

    def isRunning(self) -> bool:
        return False

    def wait(self, *args: Any, **kwargs: Any) -> bool:
        return True

    def quit(self) -> None:
        pass


class _FakeStackWorker(QObject):
    """StackWorker stand-in with the exact signals _spawn_stack_worker wires."""

    finished = Signal()
    sig_adaptive_trajectory = Signal(
        int, float, float, float, float, str, bool, bool
    )
    sig_focus_trajectory = Signal(int, float, float, float, float)
    sig_autofocus_status = Signal(int, int, float, float, float, str)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self.run = lambda: None


@pytest.fixture
def _patched_spawn(controller: Controller_MainWindow) -> Any:
    """Yield a controller configured for spawn with the fake worker/thread.

    The same fake worker is returned on every `StackWorker(...)` call so the
    reused-worker guard branches are exercised.
    """
    _configure_for_spawn(controller)
    worker = _FakeStackWorker()
    with (
        patch.object(_ap, "QThread", _FakeQThread),
        patch.object(
            _ap,
            "StackWorker",
            new=lambda *args, **kwargs: worker,
        ),
    ):
        yield controller, worker


def test_reused_worker_defensively_disconnects_stale_signal_connections(
    _patched_spawn: tuple[Controller_MainWindow, _FakeStackWorker],
) -> None:
    """On a second spawn the panel disconnects prior worker-signal and
    QThread started() connections before reconnecting, preventing duplicate
    queued slots."""
    ctrl, worker = _patched_spawn

    # First spawn wires the worker and thread.
    ctrl.acquisition_panel._spawn_stack_worker()
    first_thread = ctrl._stack_thread
    assert first_thread is not None
    assert first_thread.receivers(SIGNAL("started()")) == 1
    assert (
        worker.receivers(
            SIGNAL(
                "sig_adaptive_trajectory(int,double,double,double,double,QString,bool,bool)"
            )
        )
        == 1
    )
    assert (
        worker.receivers(
            SIGNAL("sig_focus_trajectory(int,double,double,double,double)")
        )
        == 1
    )
    assert (
        worker.receivers(
            SIGNAL("sig_autofocus_status(int,int,double,double,double,QString)")
        )
        == 1
    )

    # Second spawn reuses the QThread and the same worker instance.
    ctrl.acquisition_panel._spawn_stack_worker()
    assert ctrl._stack_thread is first_thread, "QThread must be reused"
    assert first_thread.receivers(SIGNAL("started()")) == 1
    assert (
        worker.receivers(
            SIGNAL(
                "sig_adaptive_trajectory(int,double,double,double,double,QString,bool,bool)"
            )
        )
        == 1
    )
    assert (
        worker.receivers(
            SIGNAL("sig_focus_trajectory(int,double,double,double,double)")
        )
        == 1
    )
    assert (
        worker.receivers(
            SIGNAL("sig_autofocus_status(int,int,double,double,double,QString)")
        )
        == 1
    )


def test_reused_qthread_without_prev_worker_skips_finished_disconnect(
    _patched_spawn: tuple[Controller_MainWindow, _FakeStackWorker],
) -> None:
    """When the previous worker wrapper is gone, the reused-QThread path
    skips the stale finished/started disconnections and still reuses the
    thread."""
    ctrl, _ = _patched_spawn

    ctrl.acquisition_panel._spawn_stack_worker()
    first_thread = ctrl._stack_thread
    assert first_thread is not None

    # Remove the worker reference before the second spawn.
    ctrl._stack_worker = None
    ctrl.acquisition_panel._spawn_stack_worker()
    assert ctrl._stack_thread is first_thread, "QThread must still be reused"


def test_reused_qthread_connects_started_without_stale_disconnect(
    _patched_spawn: tuple[Controller_MainWindow, _FakeStackWorker],
) -> None:
    """If the prior started() connection is already gone, the guard
    reconnects it without attempting a disconnect of none."""
    ctrl, _ = _patched_spawn

    ctrl.acquisition_panel._spawn_stack_worker()
    first_thread = ctrl._stack_thread
    assert first_thread is not None
    assert first_thread.receivers(SIGNAL("started()")) == 1

    # Simulate an external cleanup of the started() slot.
    first_thread.started.disconnect()
    assert first_thread.receivers(SIGNAL("started()")) == 0

    ctrl.acquisition_panel._spawn_stack_worker()
    assert ctrl._stack_thread is first_thread
    assert first_thread.receivers(SIGNAL("started()")) == 1


def test_spawn_keeps_dock_plots_visible_when_docks_are_open(
    _patched_spawn: tuple[Controller_MainWindow, _FakeStackWorker],
) -> None:
    """When the adaptive or focus trajectory docks are open, _spawn_stack_worker
    does not re-hide the plot widgets."""
    ctrl, _ = _patched_spawn
    from PySide6.QtWidgets import QApplication

    # First spawn with missing legends covers the _legend guard branches.
    ctrl.adaptiveTrajectoryWidget._legend = None
    ctrl.focusTrajectoryWidget._legend = None
    ctrl.acquisition_panel._spawn_stack_worker()
    QApplication.processEvents()
    assert ctrl.adaptiveTrajectoryWidget.plotWidget_adaptiveTrajectory.isHidden()

    # Open the adaptive dock.
    ui = ctrl.stack_panel.ui
    ui.checkBox_adaptiveEnable.setChecked(True)
    ui.checkBox_adaptiveEnable.toggled.emit(True)
    QApplication.processEvents()
    ctrl.ui.toolButton_railAdaptive.setChecked(True)
    ctrl.ui.toolButton_railAdaptive.toggled.emit(True)
    QApplication.processEvents()
    assert ctrl.dockWidget_adaptiveTrajectory.isVisible()

    # Arm focus so its rail button is shown, then open the focus dock.
    ui.checkBox_focusEnable.setChecked(True)
    ui.checkBox_focusEnable.toggled.emit(True)
    QApplication.processEvents()
    ctrl.ui.toolButton_railFocus.setChecked(True)
    ctrl.ui.toolButton_railFocus.toggled.emit(True)
    QApplication.processEvents()
    assert ctrl.dockWidget_focusTrajectory.isVisible()

    # Second spawn reuses the thread and should not hide open-dock plots.
    ctrl.acquisition_panel._spawn_stack_worker()
    QApplication.processEvents()
    assert not ctrl.adaptiveTrajectoryWidget.plotWidget_adaptiveTrajectory.isHidden()
    assert not ctrl.focusTrajectoryWidget.plotWidget_focusTrajectory.isHidden()


def test_updateUi_post_stack_mode_preserves_button_for_active_queue(
    controller: Controller_MainWindow,
) -> None:
    """When a table queue is active, updateUi_post_stack_mode still disables
    autofocus but does not reset the Start Stack Mode button."""
    ctrl = controller
    ctrl.stack_panel.table_manager._queue_active = True
    btn = ctrl.stack_panel.ui.pushButton_acqStartStackMode
    btn.setText("Stop Stack Mode")

    with patch.object(ctrl.stack_panel, "set_autofocus_running") as mock_set:
        ctrl.acquisition_panel.updateUi_post_stack_mode()

    assert btn.text() == "Stop Stack Mode"
    mock_set.assert_called_once_with(False)
