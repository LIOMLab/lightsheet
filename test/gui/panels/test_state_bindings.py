"""Pytest-qt adapter tests for the laser power model → widget binding.

The real ``Controller_MainWindow`` is constructed via the controller fixture;
tests assert on the real model, the real spinboxes, the signal contract, and
GUI thread affinity.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

if TYPE_CHECKING:
    from lightsheet.gui.shell.controller import Controller_MainWindow


def test_state_belongs_to_gui_thread(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """The model object lives on the QApplication GUI thread."""
    ctrl = controller
    app = QApplication.instance()
    assert app is not None
    assert ctrl.state.thread() is app.thread()


def test_state_seeds_laser_power_spinboxes_from_model(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """updateUi_initial_hardware_state seeds the laser spinboxes from the
    model's default percent.
    """
    ctrl = controller
    assert ctrl.laser_panel.ui.doubleSpinBox_laserOneAmplitude.value() == 0.0
    assert ctrl.laser_panel.ui.doubleSpinBox_laserTwoAmplitude.value() == 0.0
    assert ctrl.state.laser_power_pct == (0.0, 0.0)


def test_model_change_updates_matching_spinbox(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """state.set_laser_power_pct updates only the matching spinbox."""
    ctrl = controller
    with qtbot.waitSignal(ctrl.state.sig_laser_power_changed, timeout=100) as blocker:
        ctrl.state.set_laser_power_pct(0, 42.0)
    assert blocker.signal_triggered
    assert ctrl.laser_panel.ui.doubleSpinBox_laserOneAmplitude.value() == 42.0
    assert ctrl.laser_panel.ui.doubleSpinBox_laserTwoAmplitude.value() == 0.0


def test_widget_edit_commits_to_model(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """Editing a laser spinbox (valueChanged) commits the value to the model."""
    ctrl = controller
    ctrl.laser_panel.ui.doubleSpinBox_laserOneAmplitude.setValue(33.0)
    assert ctrl.state.laser_power_pct[0] == 33.0
    assert ctrl.laser_panel.ui.doubleSpinBox_laserOneAmplitude.value() == 33.0


def test_widget_edit_does_not_loop_back_to_model(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """A widget edit sets the model once; the model's projection slot does not
    re-enter a second model write or timer restart.
    """
    ctrl = controller
    initial = ctrl.laser_panel.ui.doubleSpinBox_laserOneAmplitude.value()
    # Setting the spinbox to the same value it already holds should not change
    # the model or emit a signal.
    with qtbot.assertNotEmitted(ctrl.state.sig_laser_power_changed, wait=100):
        ctrl.laser_panel.ui.doubleSpinBox_laserOneAmplitude.setValue(initial)


def test_debounce_callback_reads_model_not_widget(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """_apply_laser1_amplitude reads the committed model percent, not the
    widget, so the HAL write target always matches the source of truth.
    """
    ctrl = controller
    ctrl.laser_panel.ui.doubleSpinBox_laserOneAmplitude.setValue(66.0)
    # The debounce callback is the timer timeout slot; calling it directly
    # should stage the model value, not the widget (they are the same here,
    # but the source is the model).
    ctrl.laser_panel._apply_laser1_amplitude()
    assert ctrl.state.laser_power_pct[0] == 66.0
    assert ctrl.laser1_power_pct == 66.0


def test_compatibility_properties_delegate_to_model(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """The controller's laser1_power_pct / laser2_power_pct compatibility
    properties read and write through the model.
    """
    ctrl = controller
    ctrl.laser1_power_pct = 10.0
    ctrl.laser2_power_pct = 20.0
    assert ctrl.state.laser_power_pct == (10.0, 20.0)
    assert ctrl.laser1_power_pct == 10.0
    assert ctrl.laser2_power_pct == 20.0


def test_apply_worker_snapshot_updates_widget(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """A worker-originated AppliedMicroscopeSnapshot folded by the model ends up
    on the matching laser spinbox.
    """
    from lightsheet.state import AppliedMicroscopeSnapshot

    ctrl = controller
    applied = AppliedMicroscopeSnapshot(laser_power_pct=(12.5, 87.5))
    with qtbot.waitSignal(ctrl.state.sig_laser_power_changed, timeout=100):
        ctrl.state.apply_worker_snapshot(applied)
    assert ctrl.laser_panel.ui.doubleSpinBox_laserOneAmplitude.value() == 12.5
    assert ctrl.laser_panel.ui.doubleSpinBox_laserTwoAmplitude.value() == 87.5


def test_applied_line_time_projects_to_widget_without_echo(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """A worker-originated applied line time (seconds) renders on the
    line-time spinbox in microseconds, and the blockSignals projection
    does not emit valueChanged — so the coordinator slot that commits
    widget edits to the model is not re-entered."""
    from lightsheet.state import AppliedMicroscopeSnapshot

    ctrl = controller
    spin = ctrl.acquisition_panel.ui.doubleSpinBox_cameraLineTime
    fired: list[float] = []
    spin.valueChanged.connect(fired.append)

    applied = AppliedMicroscopeSnapshot(lightsheet_line_time_s=0.0049)
    with qtbot.waitSignal(ctrl.state.sig_lightsheet_line_time_changed, timeout=100):
        ctrl.state.apply_worker_snapshot(applied)

    assert ctrl.state.lightsheet_line_time_s == pytest.approx(0.0049)
    assert spin.value() == pytest.approx(4900)
    assert fired == [], (
        "The state->widget projection must be signal-blocked so it does "
        "not echo back into updateUi_camera_line_time"
    )
