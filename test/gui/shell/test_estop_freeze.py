"""UAT regression for the E-stop Arm/Reset GUI freeze (G-07-4, BLOCKER).

The E-stop handler must release the GUI thread within 200 ms of the press so
the operator can immediately interact with the Arm/Reset button. The freeze
root cause is the synchronous post-kill refresh
(``_hw._poll_laser_status`` / ``_hw._refresh_laser_readback`` /
``_hw._refresh_laser2_readback_async``) called inline from
``updateUi_estop_pressed``. The fix defers those three calls via
``QTimer.singleShot(0, ...)`` so the handler returns immediately after the
synchronous kill loop (``estop_event.set()`` + ``for laser in self.lasers:
laser.off()``).

On the Mac dev box the mock HAL refresh calls are fast (no real serial
round-trip), so the freeze is not directly observable here. These tests
therefore assert the *structural* invariant of the fix: the three
post-kill refresh calls are deferred via ``QTimer.singleShot`` (NOT called
synchronously inline from the handler), while the kill loop itself
(``estop_event.set()`` + ``laser.off()`` for every laser) stays
synchronous and lock-free on the GUI thread (AGENTS.md §2).

The real ``Controller_MainWindow`` is constructed via ``make_controller``
(see ``test/_helpers/controller_fixture.py``), mirroring
``lightsheet/__main__.main()``'s composition root.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lightsheet.gui.shell.controller import Controller_MainWindow

from collections.abc import Callable
from typing import Any
from unittest.mock import patch

from pytest import FixtureRequest
from pytestqt.qtbot import QtBot


def test_estop_handler_defers_post_kill_refresh(
    controller: Controller_MainWindow,
    qtbot: QtBot,
    request: FixtureRequest,
) -> None:
    """The three post-kill refresh calls (_poll_laser_status /
    _refresh_laser_readback / _refresh_laser2_readback_async) are deferred
    via QTimer.singleShot(0, ...) — they are NOT called synchronously
    inline from updateUi_estop_pressed. A probe QTimer.singleShot(0, ...)
    scheduled before the handler fires within 200 ms of the press (the GUI
    thread is responsive), and the deferred refresh calls land after the
    event loop pumps.
    """
    ctrl = controller

    # Record synchronous-vs-deferred timing for each refresh call. A call
    # is "synchronous" if it happens during updateUi_estop_pressed() (i.e.
    # before the handler returns). A call is "deferred" if it happens
    # after the handler returns, via a QTimer.singleShot callback.
    sync_poll: list[int] = []
    sync_readback_l1: list[int] = []
    sync_readback_l2: list[int] = []
    deferred_poll: list[int] = []
    deferred_readback_l1: list[int] = []
    deferred_readback_l2: list[int] = []
    in_handler = {"value": False}

    def _fake_poll(indices: object) -> None:
        if in_handler["value"]:
            sync_poll.append(1)
        else:
            deferred_poll.append(1)

    def _fake_readback_l1(idx: object) -> None:
        if in_handler["value"]:
            sync_readback_l1.append(1)
        else:
            deferred_readback_l1.append(1)

    def _fake_readback_l2() -> None:
        if in_handler["value"]:
            sync_readback_l2.append(1)
        else:
            deferred_readback_l2.append(1)

    patchers = [
        patch.object(ctrl._hw, "_poll_laser_status", side_effect=_fake_poll),
        patch.object(
            ctrl._hw, "_refresh_laser_readback", side_effect=_fake_readback_l1
        ),
        patch.object(
            ctrl._hw,
            "_refresh_laser2_readback_async",
            side_effect=_fake_readback_l2,
        ),
    ]
    for p in patchers:
        p.start()
        request.addfinalizer(p.stop)

    from PySide6.QtCore import QTimer

    # Probe: a QTimer.singleShot(0, ...) scheduled before the handler must
    # fire within 200 ms of the press — proving the event loop pumps right
    # after the handler returns (no synchronous refresh blocking it).
    probe_fired = {"value": False}

    def _probe() -> None:
        probe_fired["value"] = True

    QTimer.singleShot(0, _probe)

    in_handler["value"] = True
    ctrl.updateUi_estop_pressed()
    in_handler["value"] = False

    # The probe must fire within 200 ms — the GUI thread is responsive.
    qtbot.waitUntil(lambda: probe_fired["value"], timeout=200)
    assert probe_fired["value"] is True

    # The refresh calls must NOT have been called synchronously (the fix
    # defers them via QTimer.singleShot). This is the structural invariant.
    assert sync_poll == [], (
        f"_poll_laser_status was called synchronously ({len(sync_poll)}x) "
        "— it must be deferred via QTimer.singleShot(0, ...) so the GUI "
        "thread releases within 200ms of the E-stop press."
    )
    assert sync_readback_l1 == [], (
        f"_refresh_laser_readback was called synchronously "
        f"({len(sync_readback_l1)}x) — it must be deferred via "
        "QTimer.singleShot(0, ...)."
    )
    assert sync_readback_l2 == [], (
        f"_refresh_laser2_readback_async was called synchronously "
        f"({len(sync_readback_l2)}x) — it must be deferred via "
        "QTimer.singleShot(0, ...)."
    )

    # The deferred refresh calls must eventually fire (after the event
    # loop pumps). Wait up to 500 ms for all three to land.
    qtbot.waitUntil(
        lambda: (
            len(deferred_poll) >= 1
            and len(deferred_readback_l1) >= 1
            and len(deferred_readback_l2) >= 1
        ),
        timeout=500,
    )
    assert len(deferred_poll) >= 1
    assert len(deferred_readback_l1) >= 1
    assert len(deferred_readback_l2) >= 1

def test_estop_kill_path_stays_synchronous_and_lock_free(
    controller: Controller_MainWindow,
    request: FixtureRequest,
) -> None:
    """The kill loop (estop_event.set() + for laser in self.lasers:
    laser.off()) stays synchronous on the GUI thread — no thread/queue
    offload (AGENTS.md §2). The cooperative-abort Event is set before the
    handler returns, and every laser's off() is called synchronously.
    """
    ctrl = controller

    # Record which lasers had off() called. Wrap each laser's off() so we
    # can observe the synchronous call.
    off_calls: list[int] = []
    original_offs = []
    for idx, laser in enumerate(ctrl.lasers):
        original_offs.append(laser.off)

        def _make_recorder(i: int, _orig: Any) -> Callable[[], None]:
            def _off() -> None:
                off_calls.append(i)
                _orig()

            return _off

        laser.off = _make_recorder(idx, laser.off)

    # Patch the refresh calls so they do not spawn a QThread (the L2
    # async readback) or otherwise interfere with the synchronous kill
    # path observation.
    patchers = [
        patch.object(ctrl._hw, "_poll_laser_status"),
        patch.object(ctrl._hw, "_refresh_laser_readback"),
        patch.object(ctrl._hw, "_refresh_laser2_readback_async"),
    ]
    for p in patchers:
        p.start()
        request.addfinalizer(p.stop)

    # The estop_event must be set synchronously — check it BEFORE pumping
    # the event loop (right after the handler returns).
    assert not ctrl.estop_event.is_set()
    ctrl.updateUi_estop_pressed()
    # Synchronous postcondition: the Event is set immediately.
    assert ctrl.estop_event.is_set()
    # Synchronous postcondition: every laser's off() was called inline
    # from the handler (before any deferred callback fires).
    assert off_calls == list(range(len(ctrl.lasers))), (
        f"Expected laser.off() called synchronously for every laser in "
        f"self.lasers, got {off_calls} — the kill path must stay "
        "synchronous and lock-free on the GUI thread (AGENTS.md §2)."
    )

    # Restore the original off() methods (the fixture teardown will
    # handle the controller, but be tidy).
    for idx, laser in enumerate(ctrl.lasers):
        laser.off = original_offs[idx]

def test_estop_laser_off_precedes_dock_freeze(
    controller: Controller_MainWindow,
    request: FixtureRequest,
) -> None:
    """The synchronous laser-off kill path completes before either
    trajectory dock is frozen. For an E-stop with both adaptive and focus
    active, every laser.off() call precedes any call to the dock
    controllers' freeze() methods."""
    ctrl = controller

    # Patch the refresh calls so the handler does not spawn a QThread.
    patchers = [
        patch.object(ctrl._hw, "_poll_laser_status"),
        patch.object(ctrl._hw, "_refresh_laser_readback"),
        patch.object(ctrl._hw, "_refresh_laser2_readback_async"),
    ]
    for p in patchers:
        p.start()
        request.addfinalizer(p.stop)

    order: list[str] = []
    original_offs: list[Callable[[], None]] = []

    def _make_off_recorder(
        _laser: Any, _orig: Callable[[], None]
    ) -> Callable[[], None]:
        def _off() -> None:
            order.append("laser.off")
            _orig()

        return _off

    for laser in ctrl.lasers:
        original_offs.append(laser.off)
        laser.off = _make_off_recorder(laser, laser.off)

    def _record_adaptive_freeze() -> None:
        order.append("adaptive.freeze")

    def _record_focus_freeze() -> None:
        order.append("focus.freeze")

    adaptive_p = patch.object(
        ctrl._adaptive_dock_controller, "freeze", side_effect=_record_adaptive_freeze
    )
    focus_p = patch.object(
        ctrl._focus_dock_controller, "freeze", side_effect=_record_focus_freeze
    )
    adaptive_p.start()
    focus_p.start()
    request.addfinalizer(adaptive_p.stop)
    request.addfinalizer(focus_p.stop)

    ctrl.updateUi_estop_pressed()

    # Restore original off() methods.
    for laser, orig in zip(ctrl.lasers, original_offs, strict=True):
        laser.off = orig

    # Every laser must appear before every freeze.
    off_positions = [i for i, v in enumerate(order) if v == "laser.off"]
    freeze_positions = [
        i for i, v in enumerate(order) if v in ("adaptive.freeze", "focus.freeze")
    ]
    assert off_positions, "laser.off was never called"
    assert freeze_positions, "dock freeze was never called"
    assert max(off_positions) < min(freeze_positions), (
        f"laser.off must precede dock freeze; got order {order}"
    )

def test_estop_warning_emitted_and_freeze_still_runs(
    controller: Controller_MainWindow,
    request: FixtureRequest,
) -> None:
    """If a laser off() fails and sets laser.error, the E-stop handler
    emits a warning message AND still freezes the dock plots afterwards."""
    ctrl = controller

    patchers = [
        patch.object(ctrl._hw, "_poll_laser_status"),
        patch.object(ctrl._hw, "_refresh_laser_readback"),
        patch.object(ctrl._hw, "_refresh_laser2_readback_async"),
    ]
    for p in patchers:
        p.start()
        request.addfinalizer(p.stop)

    messages: list[str] = []
    ctrl.sig_message.connect(messages.append)

    def _failing_off(laser: Any) -> Callable[[], None]:
        def _off() -> None:
            # Simulate a backend that reports the off() command failed.
            laser.error = True
            laser.error_message = "mock off failure"

        return _off

    for laser in ctrl.lasers:
        laser.off = _failing_off(laser)

    ctrl.updateUi_estop_pressed()

    # The warning for the first failing laser appears in sig_message.
    assert any("off command failed" in m for m in messages), (
        f"Expected laser-off warning in sig_message, got {messages}"
    )
    # Both dock widgets are frozen even when a laser off fails.
    assert ctrl._adaptive_dock_controller.widget._frozen is True
    assert ctrl._focus_dock_controller.widget._frozen is True

def test_arm_reset_first_press_clears_estop_event(
    controller: Controller_MainWindow,
    qtbot: QtBot,
    request: FixtureRequest,
) -> None:
    """After E-stop, the first Arm/Reset press clears the cooperative-abort
    Event (transitions to DISARMED). The GUI thread must stay responsive
    through the press — a QTimer.singleShot(0, ...) probe fires within
    200 ms of the Arm/Reset press.
    """
    ctrl = controller

    # Patch the refresh calls so the E-stop handler does not spawn a QThread
    # for the L2 readback (keeps the test focused on the Arm/Reset path).
    patchers = [
        patch.object(ctrl._hw, "_poll_laser_status"),
        patch.object(ctrl._hw, "_refresh_laser_readback"),
        patch.object(ctrl._hw, "_refresh_laser2_readback_async"),
    ]
    for p in patchers:
        p.start()
        request.addfinalizer(p.stop)

    # Arm -> E-stop -> Arm/Reset (first press).
    ctrl.updateUi_estop_pressed()
    assert ctrl.estop_event.is_set()

    from PySide6.QtCore import QTimer

    flag = {"value": False}

    def _probe() -> None:
        flag["value"] = True

    QTimer.singleShot(0, _probe)
    ctrl.updateUi_arm_reset_pressed()

    # The probe must fire within 200 ms — the GUI thread is responsive
    # after the Arm/Reset press.
    qtbot.waitUntil(lambda: flag["value"], timeout=200)
    assert flag["value"] is True

    # First press clears the cooperative-abort Event.
    assert not ctrl.estop_event.is_set()
