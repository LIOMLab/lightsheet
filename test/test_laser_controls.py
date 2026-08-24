"""
Laser power-control regression tests for the staged-percent spinbox
contract and the E-stop cooperative-skip guard.

The real Controller_MainWindow is constructed via make_controller
(test/_helpers/controller_fixture.py), which mirrors
lightsheet/__main__.main()'s composition root: a mock DeviceBundle, real
Controller_MainWindow, all four collaborators wired, hardware_init called.
Laser write/toggle/poll/readback methods live on the real HardwareManager
(ctrl._hw) and the controller (ctrl); tests call them directly and assert
on real attributes, Qt labels, and signals — via real construction.

Pure-math tests cover the %-to-absolute scaling at the HAL boundary.
"""

import contextlib
import threading
from unittest.mock import patch

from _helpers.controller_fixture import make_controller


# --------------------------------------------------------------------------- #
# Pure-math tests for the %-to-absolute scaling at the HAL boundary.
# --------------------------------------------------------------------------- #


def test_pct_scaling_laser1_midrange() -> None:
    """50 % of a 5 V max -> 2.5 V (laser 1, DAQ AO)."""
    pct = 50
    max_power = 5.0
    assert pct / 100.0 * max_power == 2.5


def test_pct_scaling_laser2_midrange() -> None:
    """50 % of a 150000 uW max -> 75000 uW (laser 2, iBeam)."""
    pct = 50
    max_power = 150000
    assert pct / 100.0 * max_power == 75000.0


def test_pct_scaling_full() -> None:
    """100 % -> full Max Power (both lasers)."""
    assert 100 / 100.0 * 5.0 == 5.0
    assert 100 / 100.0 * 150000 == 150000.0


def test_pct_scaling_zero() -> None:
    """0 % -> 0 (laser off)."""
    assert 0 / 100.0 * 150000 == 0.0
    assert 0 / 100.0 * 5.0 == 0.0


# --------------------------------------------------------------------------- #
# Behavioral test: the cooperative-skip guard actually prevents the HAL
# write when estop_event is set — not just a static-source string match.
#
# The real HardwareManager (ctrl._hw) is constructed via make_controller.
# Its _write_laser*_power methods read self.lasers[i] (real MockLaser
# instances), call .set_power(mw), check .active/.error/.max_power, and
# emit through self._shell (the real controller). Tests call the real
# methods directly and assert on real MockLaser state.
# --------------------------------------------------------------------------- #


def test_write_laser1_power_skips_when_estop_set(qtbot, request) -> None:
    """When estop_event is set, _write_laser1_power must NOT call
    self.lasers[0].set_power (the HAL write is skipped)."""
    ctrl, _ = make_controller(qtbot, request)
    ctrl._hw.lasers[0].active = True
    ctrl.estop_event.set()

    ctrl._hw._write_laser1_power(50.0)

    # set_power was not called — the staged power stays at 0.0.
    assert ctrl._hw.lasers[0].power == 0.0


def test_write_laser2_power_skips_when_estop_set(qtbot, request) -> None:
    """When estop_event is set, _write_laser2_power must NOT call
    self.lasers[1].set_power (the HAL write is skipped)."""
    ctrl, _ = make_controller(qtbot, request)
    ctrl._hw.lasers[1].active = True
    ctrl.estop_event.set()

    ctrl._hw._write_laser2_power(50.0)

    assert ctrl._hw.lasers[1].power == 0.0


def test_write_laser1_power_writes_when_estop_clear_and_active(qtbot, request) -> None:
    """When estop_event is clear and laser 1 is active, _write_laser1_power
    must scale the staged percentage to mW (pct/100 * max_power) and call
    self.lasers[0].set_power(mw). The mW value is the canonical ILaser
    unit; the backend (DAQLaser) converts mW -> V internally."""
    ctrl, _ = make_controller(qtbot, request)
    ctrl._hw.lasers[0].active = True

    ctrl._hw._write_laser1_power(50.0)

    # 50 % of 300 mW = 150 mW must be staged on the MockLaser's .power.
    assert ctrl._hw.lasers[0].power == 150.0


def test_write_laser1_power_skips_when_laser_inactive(qtbot, request) -> None:
    """When laser 1 is inactive, _write_laser1_power must not write (no
    point energizing a laser the operator has toggled off)."""
    ctrl, _ = make_controller(qtbot, request)
    ctrl._hw.lasers[0].active = False

    ctrl._hw._write_laser1_power(50.0)

    assert ctrl._hw.lasers[0].power == 0.0


def test_write_laser2_power_writes_when_estop_clear_and_active(qtbot, request) -> None:
    """When estop_event is clear and laser 2 is active, _write_laser2_power
    must scale the staged percentage to mW (pct/100 * max_power) and call
    self.lasers[1].set_power(mw)."""
    ctrl, _ = make_controller(qtbot, request)
    ctrl._hw.lasers[1].active = True

    ctrl._hw._write_laser2_power(50.0)

    # 50 % of 150 mW = 75 mW must be staged on the MockLaser's .power.
    assert ctrl._hw.lasers[1].power == 75.0


def test_write_laser1_power_surfaces_error_and_resets(qtbot, request) -> None:
    """When self.lasers[0].set_power leaves .error set, _write_laser1_power
    must emit a sig_message naming the laser's label + error_message and
    reset .error = 0."""
    ctrl, _ = make_controller(qtbot, request)
    ctrl._hw.lasers[0].active = True

    def _fail_set_power(mw: float) -> None:
        ctrl._hw.lasers[0].error = 1
        ctrl._hw.lasers[0].error_message = "daq write failed"

    with patch.object(ctrl._hw.lasers[0], "set_power", side_effect=_fail_set_power):
        with qtbot.waitSignal(ctrl.sig_message, timeout=1000) as blocker:
            ctrl._hw._write_laser1_power(50.0)

    msg = blocker.args[0]
    assert "Laser 1 (555 nm)" in msg
    assert "daq write failed" in msg
    assert ctrl._hw.lasers[0].error == 0


# --------------------------------------------------------------------------- #
# Toggle + start_lasers/stop_lasers rewrite tests — the toggle bodies and
# the acquisition-worker start/stop paths collapse to one shape operating
# on self.lasers[i] uniformly (no laser-2-specific self.ibeam branch).
# --------------------------------------------------------------------------- #


def test_toggle_laser1_off_when_active(qtbot, request) -> None:
    """_toggle_laser1 calls self.lasers[0].off() when the laser is active."""
    ctrl, _ = make_controller(qtbot, request)
    ctrl._hw.lasers[0].active = True

    ctrl._hw._toggle_laser1()

    # MockLaser.off() sets active=False and power=0.0.
    assert ctrl._hw.lasers[0].active is False


def test_toggle_laser1_on_when_inactive(qtbot, request) -> None:
    """_toggle_laser1 calls self.lasers[0].on() when the laser is inactive,
    then applies the staged percentage via _write_laser1_power."""
    ctrl, _ = make_controller(qtbot, request)
    ctrl._hw.lasers[0].active = False
    ctrl.laser1_power_pct = 50.0

    ctrl._hw._toggle_laser1()

    # on() was called (active=True) and _write_laser1_power(50.0) staged
    # 50 % of 300 mW = 150 mW.
    assert ctrl._hw.lasers[0].active is True
    assert ctrl._hw.lasers[0].power == 150.0


def test_toggle_laser2_on_when_inactive(qtbot, request) -> None:
    """_toggle_laser2 calls self.lasers[1].on() when inactive, then applies
    the staged percentage via _write_laser2_power. Symmetric with laser 1 —
    no laser-2-specific self.ibeam branch."""
    ctrl, _ = make_controller(qtbot, request)
    ctrl._hw.lasers[1].active = False
    ctrl.laser2_power_pct = 50.0

    ctrl._hw._toggle_laser2()

    assert ctrl._hw.lasers[1].active is True
    # 50 % of 150 mW = 75 mW.
    assert ctrl._hw.lasers[1].power == 75.0


def test_toggle_laser1_skips_when_estop_set(qtbot, request) -> None:
    """_toggle_laser1 must NOT energize when estop_event is set — the
    E-stop path already drove the laser off synchronously; a queued toggle
    must not re-energize a Class IIIB laser past the kill path."""
    ctrl, _ = make_controller(qtbot, request)
    ctrl._hw.lasers[0].active = False
    ctrl.laser1_power_pct = 50.0
    ctrl.estop_event.set()

    ctrl._hw._toggle_laser1()

    # on() was not called — active stays False.
    assert ctrl._hw.lasers[0].active is False


def test_start_lasers_drives_both_auto_lasers(qtbot, request) -> None:
    """start_lasers drives self.lasers[0] and self.lasers[1] uniformly
    (.on() / .set_power(mw)) for the auto-selected lasers — no
    laser-2-specific self.ibeam branch."""
    ctrl, _ = make_controller(qtbot, request)
    ctrl._hw.lasers[0].active = False
    ctrl._hw.lasers[1].active = False
    ctrl._auto_laser1 = True
    ctrl._auto_laser2 = True
    ctrl.laser1_power_pct = 50.0
    ctrl.laser2_power_pct = 50.0

    ctrl._hw.start_lasers()

    assert ctrl._hw.lasers[0].active is True
    assert ctrl._hw.lasers[1].active is True
    # 50 % of 300 mW = 150 mW; 50 % of 150 mW = 75 mW.
    assert ctrl._hw.lasers[0].power == 150.0
    assert ctrl._hw.lasers[1].power == 75.0


def test_start_lasers_skips_non_auto_lasers(qtbot, request) -> None:
    """start_lasers only energizes lasers whose auto-checkbox was sampled
    True; the other laser is untouched."""
    ctrl, _ = make_controller(qtbot, request)
    ctrl._hw.lasers[0].active = False
    ctrl._hw.lasers[1].active = False
    ctrl._auto_laser1 = True
    ctrl._auto_laser2 = False
    ctrl.laser1_power_pct = 50.0
    ctrl.laser2_power_pct = 50.0

    ctrl._hw.start_lasers()

    assert ctrl._hw.lasers[0].active is True
    # Laser 2 was not auto-selected — untouched.
    assert ctrl._hw.lasers[1].active is False


def test_stop_lasers_drives_both_auto_lasers_off(qtbot, request) -> None:
    """stop_lasers drives self.lasers[0].off() / self.lasers[1].off()
    uniformly for the auto-selected lasers — no laser-2-specific
    self.ibeam branch."""
    ctrl, _ = make_controller(qtbot, request)
    ctrl._hw.lasers[0].active = True
    ctrl._hw.lasers[1].active = True
    ctrl._auto_laser1 = True
    ctrl._auto_laser2 = True

    ctrl._hw.stop_lasers()

    assert ctrl._hw.lasers[0].active is False
    assert ctrl._hw.lasers[1].active is False


# --------------------------------------------------------------------------- #
# E-stop rewrite tests — updateUi_estop_pressed drives BOTH lasers off via
# self.lasers[i].off() in a loop, synchronously on the GUI thread, with NO
# lock acquisition anywhere in the kill path (a stuck daemon write thread
# holding a laser's lock must never delay the kill path). close_modes reads
# self.lasers[i].active (not the old 2-channel container laser1_active /
# laser2_active reads).
#
# These tests call the real method bodies on the real controller via real
# construction. They fail against the pre-rewrite source (which calls
# self.lasers.laser1_off() / self.ibeam.off() and reads
# self.lasers.laser1_active / self.lasers.laser2_active) and pass after the
# rewrite.
# --------------------------------------------------------------------------- #


def test_estop_drives_both_lasers_off_in_loop(qtbot, request) -> None:
    """updateUi_estop_pressed must call .off() on BOTH self.lasers[0] and
    self.lasers[1] (a loop over self.lasers), synchronously on the GUI
    thread. The pre-rewrite code calls self.lasers.laser1_off() and
    self.ibeam.off() — neither is a method on a list[ILaser], so this test
    fails until the method is rewritten to the loop form."""
    ctrl, _ = make_controller(qtbot, request)
    ctrl._hw.lasers[0].active = True
    ctrl._hw.lasers[1].active = True

    # Patch _refresh_laser2_readback_async to avoid spawning a daemon
    # thread during the test (the refresh-after-action call site in the
    # real method offloads the L2 serial readback to a thread).
    with patch.object(ctrl._hw, "_refresh_laser2_readback_async"):
        ctrl.updateUi_estop_pressed()

    # MockLaser.off() sets active=False synchronously.
    assert ctrl._hw.lasers[0].active is False
    assert ctrl._hw.lasers[1].active is False
    # The cooperative-abort Event was set (step 1, preserved verbatim).
    assert ctrl.estop_event.is_set()


def test_estop_emits_per_laser_warning_on_error(qtbot, request) -> None:
    """When a laser's .off() leaves .error set, updateUi_estop_pressed must
    emit a sig_message naming that laser's .label and .error_message, then
    reset .error = 0 — mirroring the existing per-laser warning pattern but
    templated on laser.label so both lasers share one code path."""
    ctrl, _ = make_controller(qtbot, request)

    def _fail_off() -> None:
        ctrl.lasers[1].error = 1
        ctrl.lasers[1].error_message = "serial write failed"
        ctrl.lasers[1].active = False

    with patch.object(ctrl._hw, "_refresh_laser2_readback_async"), patch.object(
        ctrl.lasers[1], "off", side_effect=_fail_off
    ):
        with qtbot.waitSignal(ctrl.sig_message, timeout=1000) as blocker:
            ctrl.updateUi_estop_pressed()

    # laser2 had an error — a warning was emitted naming its label + cause.
    msg = blocker.args[0]
    assert "Laser 2 (640 nm)" in msg
    assert "serial write failed" in msg
    # The error was reset after the warning.
    assert ctrl.lasers[1].error == 0


def test_estop_acquires_no_laser_lock(qtbot, request) -> None:
    """The E-stop kill path must NOT acquire self.lasers[i]._lock anywhere
    in the method body — a stuck daemon write thread holding a laser's lock
    must never delay the kill path (AGENTS.md §2). This test records any
    attempt to enter a laser's _lock by wrapping both lasers' locks in a
    raising context manager; if the E-stop body acquires either lock, the
    method raises and the test fails."""
    ctrl, _ = make_controller(qtbot, request)
    # Stop the hardware_init timers before replacing the locks — the
    # 100ms timer_imageview callback calls _refresh_laser_readback(0)
    # which probes laser0._lock.acquire(blocking=False), and the
    # _NoLockAcquire stand-in below has no .acquire method. Stopping
    # here prevents the timer from firing during teardown (before the
    # finalizer stops it) and propagating a deferred event-loop error
    # into subsequent tests.
    ctrl.timer_imageview.stop()
    ctrl.timer_laser2_status.stop()

    class _NoLockAcquire:
        """A lock stand-in whose __enter__ raises — proves the E-stop
        kill loop never uses ``with lock:``. The ``acquire`` /
        ``release`` methods are provided so the timer-driven
        ``_refresh_laser_readback`` probe (which calls
        ``acquire(blocking=False)`` outside the patched scope, e.g.
        during teardown) returns False (lock-skip no-op) instead of
        raising ``AttributeError``."""

        def __enter__(self) -> "_NoLockAcquire":
            raise AssertionError(
                "E-stop must not acquire self.lasers[i]._lock — the kill "
                "path is lock-free so a stuck daemon write thread can never "
                "delay it (AGENTS.md §2)."
            )

        def __exit__(self, *exc: object) -> None:
            return None

        def acquire(self, blocking: bool = True) -> bool:
            return False

        def release(self) -> None:
            return None

    ctrl.lasers[0]._lock = _NoLockAcquire()
    ctrl.lasers[1]._lock = _NoLockAcquire()

    # Patch the refresh-after-action call sites so only the kill loop
    # itself runs (the refresh calls probe the lock with
    # acquire(blocking=False), which is separate from the kill path).
    with (
        patch.object(ctrl._hw, "_poll_laser_status"),
        patch.object(ctrl._hw, "_refresh_laser_readback"),
        patch.object(ctrl._hw, "_refresh_laser2_readback_async"),
    ):
        # Must not raise — if the body acquires either lock, _NoLockAcquire
        # raises.
        ctrl.updateUi_estop_pressed()


def test_close_modes_reads_lasers_index_active(qtbot, request) -> None:
    """close_modes must read self.lasers[0].active or self.lasers[1].active
    (the list[ILaser] surface), not the old self.lasers.laser1_active /
    self.lasers.laser2_active 2-channel container reads. When both lasers
    are inactive, stop_lasers must NOT be called."""
    ctrl, _ = make_controller(qtbot, request)
    ctrl.lasers[0].active = False
    ctrl.lasers[1].active = False

    with patch.object(ctrl._hw, "stop_lasers") as spy:
        ctrl.close_modes()

    spy.assert_not_called()


def test_close_modes_calls_stop_lasers_when_a_laser_active(qtbot, request) -> None:
    """close_modes must call stop_lasers when either laser is active —
    reading self.lasers[0].active or self.lasers[1].active."""
    ctrl, _ = make_controller(qtbot, request)
    ctrl.lasers[0].active = False
    ctrl.lasers[1].active = True  # laser 2 is on -> must stop

    with patch.object(ctrl._hw, "stop_lasers") as spy:
        ctrl.close_modes()

    spy.assert_called_once()


# --------------------------------------------------------------------------- #
# Per-laser status indicator tests — _poll_laser_status computes a status
# string per requested laser index (error > active > inactive precedence)
# and emits sig_laser_status(idx, status); updateUi_laser_status maps that
# string to the ● ON / ● OFF / ● ERR label text + semantic color. The gated
# L2 poll (_poll_laser2_status_gated) skips silently when the iBeam
# per-instance lock is held so a periodic status query never blocks on a
# write in progress and never misattributes a reply.
# --------------------------------------------------------------------------- #


def test_poll_laser_status_active_emits_active(qtbot, request) -> None:
    """_poll_laser_status([0]) on an active, error-free laser emits
    sig_laser_status(0, 'active') — the connected updateUi_laser_status
    slot sets label_laserOneStatus to '● ON'."""
    ctrl, _ = make_controller(qtbot, request)
    ctrl._hw.lasers[0].active = True
    ctrl._hw.lasers[0].error = 0

    ctrl._hw._poll_laser_status([0])

    assert ctrl.label_laserOneStatus.text() == "● ON"


def test_poll_laser_status_inactive_emits_inactive(qtbot, request) -> None:
    """_poll_laser_status([0]) on an inactive, error-free laser emits
    sig_laser_status(0, 'inactive') — the connected slot sets
    label_laserOneStatus to '● OFF'."""
    ctrl, _ = make_controller(qtbot, request)
    ctrl._hw.lasers[0].active = False
    ctrl._hw.lasers[0].error = 0

    ctrl._hw._poll_laser_status([0])

    assert ctrl.label_laserOneStatus.text() == "● OFF"


def test_poll_laser_status_error_wins_over_active(qtbot, request) -> None:
    """_poll_laser_status([1]) on a laser with error=1 AND active=True
    emits 'error' — the HAL error surface is authoritative (AGENTS.md §10)
    so an errored-but-still-active laser shows ERR, not ON."""
    ctrl, _ = make_controller(qtbot, request)
    ctrl._hw.lasers[1].active = True
    ctrl._hw.lasers[1].error = 1
    ctrl._hw.lasers[1].error_message = "serial fault"

    ctrl._hw._poll_laser_status([1])

    assert ctrl.label_laserTwoStatus.text() == "● ERR"


def test_poll_laser_status_both_indices_emits_twice(qtbot, request) -> None:
    """_poll_laser_status([0, 1]) emits once per index — used by the
    E-stop / start_lasers / stop_lasers refresh-after-action paths that
    touch both lasers."""
    ctrl, _ = make_controller(qtbot, request)
    ctrl._hw.lasers[0].active = True
    ctrl._hw.lasers[0].error = 0
    ctrl._hw.lasers[1].active = False
    ctrl._hw.lasers[1].error = 0

    ctrl._hw._poll_laser_status([0, 1])

    # Both labels were updated via the connected slots — one emission per
    # index.
    assert ctrl.label_laserOneStatus.text() == "● ON"
    assert ctrl.label_laserTwoStatus.text() == "● OFF"


def test_updateUi_laser_status_active_sets_on_label(qtbot, request) -> None:
    """updateUi_laser_status(0, 'active') sets label_laserOneStatus text
    to '● ON' and a green bold stylesheet."""
    ctrl, _ = make_controller(qtbot, request)

    ctrl.updateUi_laser_status(0, "active")

    assert ctrl.label_laserOneStatus.text() == "● ON"
    style = ctrl.label_laserOneStatus.styleSheet()
    assert "#34C759" in style
    assert "bold" in style


def test_updateUi_laser_status_inactive_sets_off_label(qtbot, request) -> None:
    """updateUi_laser_status(0, 'inactive') sets label_laserOneStatus text
    to '● OFF' and a gray bold stylesheet."""
    ctrl, _ = make_controller(qtbot, request)

    ctrl.updateUi_laser_status(0, "inactive")

    assert ctrl.label_laserOneStatus.text() == "● OFF"
    style = ctrl.label_laserOneStatus.styleSheet()
    assert "#8E8E93" in style
    assert "bold" in style


def test_updateUi_laser_status_error_sets_err_label_for_laser2(qtbot, request) -> None:
    """updateUi_laser_status(1, 'error') sets label_laserTwoStatus text
    to '● ERR' and a red bold stylesheet."""
    ctrl, _ = make_controller(qtbot, request)

    ctrl.updateUi_laser_status(1, "error")

    assert ctrl.label_laserTwoStatus.text() == "● ERR"
    style = ctrl.label_laserTwoStatus.styleSheet()
    assert "#FF3B30" in style
    assert "bold" in style


def test_poll_laser2_status_gated_skips_when_lock_held(qtbot, request) -> None:
    """_poll_laser2_status_gated must NOT call _poll_laser_status when
    self.lasers[1]._lock is held by an in-progress write — the poll
    probes the lock with acquire(blocking=False) and skips silently on
    failure so a periodic status query never blocks on a write and
    never misattributes a reply.

    The real _lock is an RLock (reentrant), so holding it from this
    thread would still let the gated probe acquire it. A non-reentrant
    Lock stand-in models the cross-thread 'held by another thread'
    condition: acquire(blocking=False) returns False once it's held."""
    ctrl, _ = make_controller(qtbot, request)
    # Stop the hardware_init timers — the timer_laser2_status callback
    # calls _poll_laser2_status_gated which would spawn a readback thread
    # if the lock is free during teardown.
    ctrl.timer_imageview.stop()
    ctrl.timer_laser2_status.stop()
    # Use a non-reentrant Lock so acquire(blocking=False) fails once held
    # (models the cross-thread 'held by the daemon write thread' case).
    ctrl._hw.lasers[1]._lock = threading.Lock()
    ctrl._hw.lasers[1]._lock.acquire()
    try:
        with (
            patch.object(ctrl._hw, "_poll_laser_status") as spy_poll,
            patch.object(ctrl._hw, "_refresh_laser2_readback_async"),
        ):
            ctrl._hw._poll_laser2_status_gated()

        spy_poll.assert_not_called()
    finally:
        ctrl._hw.lasers[1]._lock.release()


def test_poll_laser2_status_gated_polls_when_lock_free(qtbot, request) -> None:
    """_poll_laser2_status_gated must call _poll_laser_status([1]) when
    the iBeam lock is free — the probe acquires (blocking=False),
    releases immediately, then proceeds with the poll."""
    ctrl, _ = make_controller(qtbot, request)

    with (
        patch.object(ctrl._hw, "_poll_laser_status") as spy_poll,
        patch.object(ctrl._hw, "_refresh_laser2_readback_async"),
    ):
        ctrl._hw._poll_laser2_status_gated()

    spy_poll.assert_called_once_with([1])


# --------------------------------------------------------------------------- #
# Power readback tests — _refresh_laser_readback(idx) queries
# self.lasers[idx].get_output_power() under the laser's per-instance lock
# and emits (idx, text, tooltip) on sig_laser_readback for the GUI-thread
# slot updateUi_laser_readback to apply to the readback label. The lock is
# probed with acquire(blocking=False): if held by an in-progress write, the
# refresh is a silent no-op (the operator can retry via the Refresh button).
# On success the lock is always released in the finally block. A None
# readback (parse failure / unsupported variant) emits the last commanded
# power with a (cmd) suffix + tooltip; a live readback emits an empty
# tooltip (clearing any prior stale-value warning).
#
# idx=1 covers the L2/iBeam path (serial readback, may return None).
# idx=0 covers the L1/DAQLaser path (get_output_power returns the staged
# mW — self.power — never None in practice, but the None fallback path is
# shared so the contract holds uniformly).
# --------------------------------------------------------------------------- #


def test_refresh_laser2_readback_populated(qtbot, request) -> None:
    """_refresh_laser_readback(1) on a stand-in where the lock is free and
    get_output_power() returns 75.0 emits (1, '75.0 mW', '') on
    sig_laser_readback — the GUI-thread slot applies it to the label."""
    ctrl, _ = make_controller(qtbot, request)
    ctrl._hw.lasers[1].power = 75.0

    ctrl._hw._refresh_laser_readback(1)

    # The connected updateUi_laser_readback slot applied the emit.
    assert ctrl.label_laserTwoReadback.text() == "75.0 mW"
    assert ctrl.label_laserTwoReadback.toolTip() == ""


def test_refresh_laser2_readback_degraded_shows_commanded_fallback(
    qtbot, request
) -> None:
    """_refresh_laser_readback(1) on a stand-in where get_output_power()
    returns None (parse failure / unsupported variant) emits
    (1, '{power:.1f} mW (cmd)', <degraded tooltip>) on sig_laser_readback
    so the GUI-thread slot can show the commanded fallback + tooltip."""
    ctrl, _ = make_controller(qtbot, request)
    ctrl._hw.lasers[1].power = 42.0

    with patch.object(ctrl._hw.lasers[1], "get_output_power", return_value=None):
        ctrl._hw._refresh_laser_readback(1)

    assert ctrl.label_laserTwoReadback.text() == "42.0 mW (cmd)"
    tooltip = ctrl.label_laserTwoReadback.toolTip()
    assert "readback unavailable" in tooltip or "parse failure" in tooltip


def test_refresh_laser2_readback_lock_skip_is_noop(qtbot, request) -> None:
    """_refresh_laser_readback(1) on a stand-in where the lock is held
    returns silently without calling get_output_power() and without
    emitting on sig_laser_readback — the lock-skip no-op contract. Uses a
    non-reentrant Lock to model the cross-thread 'held by the daemon
    write thread' condition."""
    ctrl, _ = make_controller(qtbot, request)
    # Stop the hardware_init timers — the timer_imageview callback calls
    # _refresh_laser_readback(0) which would probe laser0's lock during
    # teardown, and timer_laser2_status could spawn a readback thread.
    ctrl.timer_imageview.stop()
    ctrl.timer_laser2_status.stop()
    ctrl._hw.lasers[1]._lock = threading.Lock()
    ctrl._hw.lasers[1]._lock.acquire()
    try:
        with patch.object(ctrl._hw.lasers[1], "get_output_power") as spy:
            ctrl._hw._refresh_laser_readback(1)

            spy.assert_not_called()
    finally:
        ctrl._hw.lasers[1]._lock.release()


def test_refresh_laser2_readback_releases_lock_in_finally(qtbot, request) -> None:
    """_refresh_laser_readback(1) always releases the lock in the finally
    block when acquire(blocking=False) succeeded — even if
    get_output_power raises. Verified by acquiring the lock after the
    call returns (a non-released lock would block)."""
    ctrl, _ = make_controller(qtbot, request)

    with patch.object(
        ctrl._hw.lasers[1], "get_output_power", side_effect=RuntimeError("serial glitch")
    ):
        # The method must not let the exception escape (or if it does, the
        # lock is still released). Wrap so we can assert the lock is free
        # afterward regardless.
        with contextlib.suppress(RuntimeError):
            ctrl._hw._refresh_laser_readback(1)

    # The lock must be releasable (free) — acquire(blocking=False)
    # succeeds iff it was released by the finally block.
    assert ctrl._hw.lasers[1]._lock.acquire(blocking=False), (
        "_refresh_laser_readback did not release the iBeam lock in the "
        "finally block — a held lock would block the next write."
    )
    ctrl._hw.lasers[1]._lock.release()


def test_refresh_laser1_readback_shows_staged_mw(qtbot, request) -> None:
    """_refresh_laser_readback(0) emits (0, '12.5 mW (est.)', <tooltip>) on
    sig_laser_readback with the staged mW from get_output_power().
    DAQLaser has no hardware readback — get_output_power() returns
    self.power (the staged mW derived from pct/100 * max_power_mw). The L1
    label carries an '(est.)' suffix + tooltip flagging the
    linear-through-origin estimate as unverified (the linear model predicts
    300 mW at 5V, but the rig-measured output is ~107.5 mW at 5V) until a
    rig-measured calibration curve is loaded. The 100ms display timer
    drives this refresh so the L1 mW field stays live as the operator
    edits the percentage."""
    ctrl, _ = make_controller(qtbot, request)
    ctrl._hw.lasers[0].power = 12.5

    ctrl._hw._refresh_laser_readback(0)

    # Exactly one emit for L1 (idx=0); the L2 label is not touched by an
    # L1 refresh. The L1 (est.) suffix + unverified-estimate tooltip is
    # asserted on the text + tooltip (the tooltip mentions 107.5 mW).
    assert ctrl.label_laserOneReadback.text() == "12.5 mW (est.)"
    assert "107.5 mW" in ctrl.label_laserOneReadback.toolTip()


# --------------------------------------------------------------------------- #
# updateUi_laser_readback slot — the GUI-thread side of sig_laser_readback.
# Applies (idx, text, tooltip) to the per-laser readback QLabel. An empty
# tooltip clears any prior stale-value warning (live readback); a non-empty
# tooltip explains the commanded-power fallback (degraded readback).
# --------------------------------------------------------------------------- #


def test_updateUi_laser_readback_live_clears_tooltip(qtbot, request) -> None:
    """updateUi_laser_readback(1, '75.0 mW', '') sets label_laserTwoReadback
    text to '75.0 mW' and clears the tooltip (empty string) — a live
    readback must not keep a stale degraded-readback tooltip."""
    ctrl, _ = make_controller(qtbot, request)

    ctrl.updateUi_laser_readback(1, "75.0 mW", "")

    assert ctrl.label_laserTwoReadback.text() == "75.0 mW"
    assert ctrl.label_laserTwoReadback.toolTip() == ""
    # L1 label was not touched.
    assert ctrl.label_laserOneReadback.text() == "0.0 mW (est.)"


def test_updateUi_laser_readback_degraded_sets_tooltip(qtbot, request) -> None:
    """updateUi_laser_readback(1, '42.0 mW (cmd)', <tooltip>) sets the
    label text to the commanded fallback and applies the degraded-readback
    tooltip so the operator can distinguish a live readback from a stale
    commanded value."""
    ctrl, _ = make_controller(qtbot, request)

    tooltip = (
        "Power readback unavailable (parse failure). "
        "Showing last commanded value may be stale."
    )
    ctrl.updateUi_laser_readback(1, "42.0 mW (cmd)", tooltip)

    assert ctrl.label_laserTwoReadback.text() == "42.0 mW (cmd)"
    assert ctrl.label_laserTwoReadback.toolTip() == tooltip


def test_updateUi_laser_readback_l1_routes_to_l1_label(qtbot, request) -> None:
    """updateUi_laser_readback(0, ...) routes to label_laserOneReadback,
    not label_laserTwoReadback — the idx selects the correct label."""
    ctrl, _ = make_controller(qtbot, request)

    ctrl.updateUi_laser_readback(0, "12.5 mW", "")

    assert ctrl.label_laserOneReadback.text() == "12.5 mW"
    # L2 label was not touched.
    assert ctrl.label_laserTwoReadback.text() == "N/A"
