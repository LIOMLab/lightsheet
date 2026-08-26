"""HardwareManager extraction tests (god-object split).

``HardwareManager`` is a plain-Python collaborator that owns the laser
write/toggle daemon threads, the per-laser RLock-guarded write paths,
both status-poll methods, and ``start_lasers``/``stop_lasers`` — but does
NOT own an ``estop()``/kill-path method of any kind (safety anti-pattern,
the pitfall). The E-stop kill path (``updateUi_estop_pressed``) stays in
the thin shell with a direct ``list[ILaser]`` ref, lock-free, on the GUI
thread.

The real controller is constructed via ``make_controller`` (see
``test/_helpers/controller_fixture.py``). HardwareManager methods are
exercised via ``ctrl._hw.<method>()`` real calls against the real
collaborator wired into the real controller.

Behavior covered:

1. ``ctrl._hw.start_lasers()`` with ``ctrl._auto_laser1 = True`` calls
   ``.set_power(...)`` then ``.on()`` on ``ctrl._hw.lasers[0]`` (a
   MockLaser), mirroring the pre-extraction ``start_lasers`` behavior.
2. ``ctrl._hw._toggle_laser1()`` with ``ctrl.estop_event.is_set() -> True``
   returns immediately without calling ``.on()``/``.off()`` on
   ``ctrl._hw.lasers[0]`` — the E-stop cooperative-skip survives the
   extraction.
3. (regression) ``HardwareManager`` has NO ``estop`` method
   (``hasattr(HardwareManager, "estop")`` is False); the shell's
   ``updateUi_estop_pressed`` drives every laser off synchronously on the
   GUI thread, lock-free, NOT routed through HardwareManager, NOT
   offloaded to a thread/timer/queue — verified via behavior assertions
   on the real method.
"""

from __future__ import annotations

import threading
from unittest.mock import Mock, patch

import lightsheet.gui.shell.controller as controller_module
from _helpers.controller_fixture import make_controller, make_bundle
from lightsheet.gui.coordinators.hardware_manager import HardwareManager
from lightsheet.hal import DeviceBundle


# --------------------------------------------------------------------------- #
# Test 1 — start_lasers drives the auto-selected lasers via the bundle.
# --------------------------------------------------------------------------- #


def test_start_lasers_drives_auto_laser1_via_bundle(qtbot, request) -> None:
    """ctrl._hw.start_lasers() with ctrl._auto_laser1 = True calls
    .set_power(mw) then .on() on ctrl._hw.lasers[0] — mirroring the
    pre-extraction start_lasers behavior exactly (set_power before on so
    the DAQ backend writes the staged power when it energizes the AO
    channel). Verified via real construction with spies on the real
    MockLaser methods."""
    ctrl, _bundle = make_controller(qtbot, request)
    ctrl._auto_laser1 = True
    ctrl._auto_laser2 = False
    ctrl.laser1_power_pct = 50.0

    laser0 = ctrl._hw.lasers[0]

    # Spy on the real MockLaser methods (wraps preserves behavior).
    with (
        patch.object(laser0, "set_power", wraps=laser0.set_power) as spy_set_power,
        patch.object(laser0, "on", wraps=laser0.on) as spy_on,
    ):
        ctrl._hw.start_lasers()

    # 50 % of 300 mW = 150 mW, staged before .on().
    spy_set_power.assert_called_once_with(150.0)
    spy_on.assert_called_once()


# --------------------------------------------------------------------------- #
# Test 2 — _toggle_laser1 cooperative-skip on E-stop survives the extraction.
# --------------------------------------------------------------------------- #


def test_toggle_laser1_skips_when_estop_set(qtbot, request) -> None:
    """ctrl._hw._toggle_laser1() with ctrl.estop_event.is_set() -> True
    returns immediately without calling .on()/.off() on
    ctrl._hw.lasers[0] — the E-stop cooperative-skip survives the
    extraction. Verified via real construction with spies on the real
    MockLaser methods."""
    ctrl, _bundle = make_controller(qtbot, request)
    ctrl.estop_event.set()
    ctrl.laser1_power_pct = 50.0

    laser0 = ctrl._hw.lasers[0]

    with (
        patch.object(laser0, "on", wraps=laser0.on) as spy_on,
        patch.object(laser0, "off", wraps=laser0.off) as spy_off,
    ):
        ctrl._hw._toggle_laser1()

    spy_on.assert_not_called()
    spy_off.assert_not_called()


# --------------------------------------------------------------------------- #
# Test 3 — regression: no HardwareManager.estop; shell kill path
# stays direct + lock-free.
# --------------------------------------------------------------------------- #


def test_hardware_manager_has_no_estop_method() -> None:
    """HardwareManager must NOT declare an estop/kill/e_stop method — the
    E-stop kill path stays in the shell (safety anti-pattern check).
    A future maintainer who sees HardwareManager.estop() will be tempted to
    queue/thread it — the single most safety-critical regression risk."""
    assert not hasattr(HardwareManager, "estop"), (
        "HardwareManager must NOT declare an estop method (safety anti-pattern)"
    )
    assert not hasattr(HardwareManager, "kill"), (
        "HardwareManager must NOT declare a kill method"
    )
    assert not hasattr(HardwareManager, "e_stop"), (
        "HardwareManager must NOT declare an e_stop method"
    )


def test_shell_estop_pressed_calls_laser_off_directly_not_via_hw(
    qtbot, request
) -> None:
    """The shell's updateUi_estop_pressed must drive every laser off
    synchronously on the GUI thread, lock-free, NOT routed through
    HardwareManager, NOT offloaded to a thread/queue. The kill loop
    (estop_event.set() + for laser in self.lasers: laser.off()) runs
    inline; only the post-kill *refresh* (_poll_laser_status /
    _refresh_laser_readback / _refresh_laser2_readback_async) is deferred
    via QTimer.singleShot(0, ...) so the GUI thread releases within ~1 ms
    of the press (G-07-4 freeze fix).

    Verified via real construction: patch threading.Thread in the
    controller module (the kill path must not offload through it) and
    spy on each laser's off() (the kill path drives every laser off
    synchronously). QTimer is NOT patched out — the deferred refresh is
    expected to schedule QTimer.singleShot calls, and the kill path
    itself does not touch QTimer."""
    ctrl, _bundle = make_controller(qtbot, request)

    laser0 = ctrl.lasers[0]
    laser1 = ctrl.lasers[1]

    # Patch threading.Thread ONLY in the controller module's namespace.
    # The kill path (laser.off() loop) must not offload through a thread.
    # QTimer is intentionally NOT patched: the post-kill refresh is
    # deferred via QTimer.singleShot(0, ...) (the G-07-4 fix), and the
    # kill path itself does not touch QTimer.
    with (
        patch.object(controller_module, "threading") as mock_threading,
        patch.object(laser0, "off", wraps=laser0.off) as spy_off0,
        patch.object(laser1, "off", wraps=laser1.off) as spy_off1,
    ):
        ctrl.updateUi_estop_pressed()

    # The kill path must NOT offload through a thread.
    mock_threading.Thread.assert_not_called()
    # Each laser's off() WAS called synchronously on the GUI thread.
    spy_off0.assert_called_once()
    spy_off1.assert_called_once()


# --------------------------------------------------------------------------- #
# Test 4 — open_laser2 drives the iBeam serial open + surfaces channel-
# enable failure via sig_message; __init__ does NOT call .open() (regression
# gate proving the composition root stays non-blocking).
# --------------------------------------------------------------------------- #


def test_open_laser2_calls_open_on_laser2_and_surfaces_error(
    qtbot, request
) -> None:
    """ctrl._hw.open_laser2() calls .open() on ctrl._hw.lasers[1] and,
    when .error is set afterward (channel-enable failure caught inside
    enable_channel()), emits sig_message on the shell with the error
    message and clears the error flag — mirroring the pre-extraction
    hardware_init inline block verbatim. Verified via real construction."""
    ctrl, _bundle = make_controller(qtbot, request)

    laser1 = ctrl._hw.lasers[1]
    # Simulate a channel-enable failure: open() succeeds (MockLaser no-op)
    # but the error surface is set afterward.
    laser1.error = 1
    laser1.error_message = "enable_channel rejected: %SYS-E"

    # Record sig_message emissions.
    messages: list[str] = []
    ctrl.sig_message.connect(lambda msg: messages.append(msg))

    with patch.object(laser1, "open", wraps=laser1.open) as spy_open:
        ctrl._hw.open_laser2()

    spy_open.assert_called_once()
    assert any("iBeam opened but channel enable failed" in m for m in messages), (
        "sig_message must surface the channel-enable failure"
    )
    assert any("enable_channel rejected: %SYS-E" in m for m in messages), (
        "sig_message must include the error message text"
    )
    assert laser1.error == 0, "open_laser2 must clear the error flag after surfacing"


def test_open_laser2_surfaces_open_exception_via_sig_message(
    qtbot, request
) -> None:
    """If ctrl._hw.lasers[1].open() raises, open_laser2() catches it and
    emits sig_message with the exception text — the operator is told the
    red laser is unavailable, but the failure is non-fatal (no re-raise).
    Verified via real construction."""
    ctrl, _bundle = make_controller(qtbot, request)

    laser1 = ctrl._hw.lasers[1]

    messages: list[str] = []
    ctrl.sig_message.connect(lambda msg: messages.append(msg))

    with patch.object(laser1, "open", side_effect=OSError("COM4 not available")):
        # Must not raise — failure is non-fatal.
        ctrl._hw.open_laser2()

    assert any("iBeam open failed" in m for m in messages), (
        "sig_message must surface the open exception"
    )
    assert any("COM4 not available" in m for m in messages), (
        "sig_message must include the exception text"
    )


def test_hardware_manager_init_does_not_call_open_on_laser2(
    qtbot, request
) -> None:
    """Regression gate: constructing HardwareManager(bundle, shell) must
    NOT call .open() on bundle.lasers[1]. __init__ runs synchronously in
    main()'s composition root BEFORE controller.show() — calling the iBeam
    serial open there would block the GUI window on the serial round-trip
    (a startup-latency regression). The open is driven post-show from
    hardware_init via open_laser2(). Verified via real construction: a
    fresh HardwareManager is built with observable Mock lasers after
    make_controller provides the real shell."""
    ctrl, bundle = make_controller(qtbot, request)

    # Build a fresh bundle with Mock lasers whose .open() is observable.
    laser1 = Mock()
    laser1._lock = threading.RLock()
    laser2 = Mock()
    laser2._lock = threading.RLock()
    test_bundle = DeviceBundle(
        camera=bundle.camera,
        siggen=bundle.siggen,
        motors=bundle.motors,
        etls=bundle.etls,
        lasers=(laser1, laser2),
    )

    hw = HardwareManager(test_bundle, ctrl)

    # __init__ must not have triggered any HAL lifecycle call on laser 2.
    laser2.open.assert_not_called()
    laser2.on.assert_not_called()
    laser2.set_power.assert_not_called()
    # Sanity: the manager did take a lasers reference (so the test isn't
    # trivially passing because the attribute was never assigned).
    assert hw.lasers[1] is laser2
