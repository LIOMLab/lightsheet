"""Worker-state smoke test for the frozen snapshot and applied-state feedback.

The real ``Controller_MainWindow`` is constructed via the controller fixture.
We construct the real ``StackWorker`` directly, feed it a frozen snapshot, and
exercise the adaptive ``_apply_adaptive_command`` path. The applied-state
signal is connected to ``MicroscopeState.apply_worker_snapshot`` with a
queued connection; we pump Qt events and assert the HAL-derived percentages
end up on the model and on the laser spinboxes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

if TYPE_CHECKING:
    from lightsheet.gui.shell.controller import Controller_MainWindow


def test_worker_snapshot_is_frozen_and_feedback_reaches_model(
    qtbot: QtBot,
    controller: Controller_MainWindow,
) -> None:
    """A worker keeps an immutable snapshot; model edits after spawn do not
    mutate it. Applied-state readback from the worker reaches the model and
    the matching laser spinbox via queued signals.
    """
    ctrl = controller
    assert ctrl._hw is not None

    # Arm both mock lasers so _write_laser*_power actually stages power.
    ctrl._hw.lasers[0].active = True
    ctrl._hw.lasers[1].active = True

    # Sample one frozen snapshot on the GUI thread before "spawning".
    snapshot = ctrl.state.snapshot()
    original_power = snapshot.laser_power_pct

    # Build a real StackWorker; assert it stores the frozen snapshot, not the
    # live model object.
    from lightsheet.adaptive.types import AdaptiveCommand
    from lightsheet.gui.workers.stack import StackWorker
    from lightsheet.state import MicroscopeSnapshot

    worker = StackWorker(
        ctrl._bundle,
        ctrl._hw,
        ctrl,
        snapshot=snapshot,
    )
    assert isinstance(worker._snapshot, MicroscopeSnapshot)
    assert worker._snapshot is not ctrl.state
    assert worker._snapshot.laser_power_pct == original_power

    # Connect the worker's applied-state signal to the model slot using a
    # queued connection (same pattern as production).
    worker.sig_applied_state.connect(
        ctrl.state.apply_worker_snapshot,
        Qt.ConnectionType.QueuedConnection,
    )

    # Call the adaptive command on the test thread. The emitted signal is
    # queued, so the model update happens when Qt processes events.
    cmd = AdaptiveCommand.fixed(
        exposure_s=0.01,
        laser1_mw=150.0,
        laser2_mw=75.0,
    )
    worker._apply_adaptive_command(cmd)

    # Wait for the model to publish the derived power change to the laser panel.
    with qtbot.waitSignal(ctrl.state.sig_laser_power_changed, timeout=1000):
        pass

    # HAL clamps to the requested mW values; for the mock lasers these are
    # 50 % of max (300 mW / 150 mW).
    assert ctrl._hw.lasers[0].power == 150.0
    assert ctrl._hw.lasers[1].power == 75.0
    assert ctrl.state.laser_power_pct == (50.0, 50.0)
    assert ctrl.laser_panel.ui.doubleSpinBox_laserOneAmplitude.value() == 50.0
    assert ctrl.laser_panel.ui.doubleSpinBox_laserTwoAmplitude.value() == 50.0

    # The worker's frozen input snapshot is unchanged despite the model update.
    assert worker._snapshot.laser_power_pct == original_power
