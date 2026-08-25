"""HardwareManager branch-coverage closure.

Exercises the _write_laser*_power estop-skip + error-surface branches,
the _toggle_laser* on/off + error branches, the start_lasers /
stop_lasers auto-laser2 branches, the _poll_laser_status error/active/
inactive branches, the _poll_laser2_status_gated lock-held/lock-free
branches, the _refresh_laser2_readback_async stacking guard, and the
_refresh_laser_readback idx=0 calibrated/uncalibrated + idx=1 None
branches.

Behavior tests (AGENTS.md §5) — every assertion is on a runtime
postcondition (laser.on/off/set_power call, sig_message emit, sig_laser_status
emit), never a static-source grep.
"""

from __future__ import annotations

import threading
from unittest.mock import Mock

import pytest

pytest.importorskip("PySide6")

from lightsheet.gui.hardware_manager import HardwareManager
from lightsheet.hal import DeviceBundle, MockCamera, MockETLs, MockLaser, MockMotors, MockSigGen


def _make_bundle() -> DeviceBundle:
    camera = MockCamera(verbose=False)
    siggen = MockSigGen(camera)
    motors = MockMotors()
    lasers = (
        MockLaser(wavelength=555, max_power_mw=300.0, label="L1"),
        MockLaser(wavelength=640, max_power_mw=150.0, label="L2"),
    )
    etls = MockETLs()
    return DeviceBundle(camera=camera, siggen=siggen, motors=motors, etls=etls, lasers=lasers)


def _make_laser(
    label: str = "L",
    max_power: float = 300.0,
    active: bool = False,
    error: int = 0,
    power: float = 0.0,
    output_power: float | None = 0.0,
    calibrated: bool = False,
) -> Mock:
    laser = Mock()
    laser.label = label
    laser.max_power = max_power
    laser.active = active
    laser.error = error
    laser.error_message = "" if error == 0 else "boom"
    laser.power = power
    laser._lock = threading.RLock()
    laser.get_output_power = Mock(return_value=output_power)
    laser.calibrated = calibrated
    return laser


def _make_hw(
    laser1: Mock | None = None,
    laser2: Mock | None = None,
    auto1: bool = False,
    auto2: bool = False,
    pct1: float = 50.0,
    pct2: float = 50.0,
    estop: bool = False,
) -> tuple[HardwareManager, Mock]:
    bundle = _make_bundle()
    shell = Mock()
    shell.sig_message = Mock()
    shell.sig_laser_status = Mock()
    shell.sig_laser_readback = Mock()
    shell._auto_laser1 = auto1
    shell._auto_laser2 = auto2
    shell.laser1_power_pct = pct1
    shell.laser2_power_pct = pct2
    shell.estop_event = threading.Event()
    if estop:
        shell.estop_event.set()
    hw = HardwareManager(bundle, shell)
    hw.lasers = [laser1 or _make_laser("L1"), laser2 or _make_laser("L2", max_power=150.0)]
    return hw, shell


# -- _write_laser1_power branches -------------------------------------------


def test_write_laser1_power_skips_when_estop_set() -> None:
    """estop_event set at top-of-method -> return before HAL write."""
    laser1 = _make_laser(active=True)
    hw, shell = _make_hw(laser1=laser1, estop=True)
    hw._write_laser1_power(50.0)
    laser1.set_power.assert_not_called()


def test_write_laser1_power_skips_when_laser_inactive() -> None:
    """laser.active False -> no set_power call (the if-active branch)."""
    laser1 = _make_laser(active=False)
    hw, shell = _make_hw(laser1=laser1)
    hw._write_laser1_power(50.0)
    laser1.set_power.assert_not_called()


def test_write_laser1_power_writes_when_active() -> None:
    laser1 = _make_laser(active=True)
    hw, shell = _make_hw(laser1=laser1)
    hw._write_laser1_power(50.0)
    # 50% of 300 = 150 mW
    laser1.set_power.assert_called_once_with(150.0)


def test_write_laser1_power_zeroes_mw_when_estop_set_mid_write() -> None:
    """estop set between the top check and the inner re-check -> mw=0."""
    laser1 = _make_laser(active=True)
    hw, shell = _make_hw(laser1=laser1)
    # Set estop AFTER the top-of-method check passes — patch is_set to
    # return False on first call, True on second.
    call_count = [0]
    orig_is_set = shell.estop_event.is_set

    def side_effect():
        call_count[0] += 1
        return call_count[0] >= 2  # False first, True second

    shell.estop_event.is_set = side_effect
    hw._write_laser1_power(50.0)
    # set_power called with 0.0 (the estop mid-write zeroing).
    laser1.set_power.assert_called_once_with(0.0)


def test_write_laser1_power_surfaces_error_via_sig_message() -> None:
    """laser.error set after set_power -> sig_message emit + error cleared."""
    laser1 = _make_laser(active=True)
    hw, shell = _make_hw(laser1=laser1)
    # set_power sets error=1
    def set_power_side_effect(mw):
        laser1.error = 1
        laser1.error_message = "DAQ write failed"
    laser1.set_power.side_effect = set_power_side_effect
    hw._write_laser1_power(50.0)
    shell.sig_message.emit.assert_called_once()
    assert laser1.error == 0


# -- _write_laser2_power branches -------------------------------------------


def test_write_laser2_power_skips_when_estop_set() -> None:
    laser2 = _make_laser("L2", max_power=150.0, active=True)
    hw, shell = _make_hw(laser2=laser2, estop=True)
    hw._write_laser2_power(50.0)
    laser2.set_power.assert_not_called()


def test_write_laser2_power_writes_when_active() -> None:
    laser2 = _make_laser("L2", max_power=150.0, active=True)
    hw, shell = _make_hw(laser2=laser2)
    hw._write_laser2_power(50.0)
    # 50% of 150 = 75 mW
    laser2.set_power.assert_called_once_with(75.0)


def test_write_laser2_power_surfaces_error_via_sig_message() -> None:
    laser2 = _make_laser("L2", max_power=150.0, active=True)
    hw, shell = _make_hw(laser2=laser2)
    def set_power_side_effect(mw):
        laser2.error = 1
        laser2.error_message = "iBeam write failed"
    laser2.set_power.side_effect = set_power_side_effect
    hw._write_laser2_power(50.0)
    shell.sig_message.emit.assert_called_once()
    assert laser2.error == 0


# -- _toggle_laser1 branches ------------------------------------------------


def test_toggle_laser1_off_when_active() -> None:
    """laser1 active -> .off() called (the if-active branch)."""
    laser1 = _make_laser(active=True)
    hw, shell = _make_hw(laser1=laser1)
    hw._toggle_laser1()
    laser1.off.assert_called_once()
    laser1.on.assert_not_called()


def test_toggle_laser1_on_when_inactive_applies_staged_power() -> None:
    """laser1 inactive -> .on() called + _write_laser1_power applies staged pct."""
    laser1 = _make_laser(active=False)
    hw, shell = _make_hw(laser1=laser1, pct1=50.0)
    # After .on(), active becomes True so the write path runs.
    def on_side_effect():
        laser1.active = True
    laser1.on.side_effect = on_side_effect
    hw._toggle_laser1()
    laser1.on.assert_called_once()
    # set_power called with 150 mW (50% of 300).
    laser1.set_power.assert_called_with(150.0)


def test_toggle_laser1_error_after_toggle_emits_sig_message() -> None:
    """laser.error set after on/off -> sig_message emit + error cleared."""
    laser1 = _make_laser(active=False)
    hw, shell = _make_hw(laser1=laser1)
    def on_side_effect():
        laser1.error = 1
        laser1.error_message = "on failed"
        laser1.active = False
    laser1.on.side_effect = on_side_effect
    hw._toggle_laser1()
    shell.sig_message.emit.assert_called_once()
    assert laser1.error == 0


def test_toggle_laser1_estop_mid_toggle_forces_off() -> None:
    """estop set after the toggle -> .off() forced + return before staged power."""
    laser1 = _make_laser(active=False)
    hw, shell = _make_hw(laser1=laser1)
    # estop fires after .on() but before the staged-power write.
    def on_side_effect():
        laser1.active = True
        shell.estop_event.set()
    laser1.on.side_effect = on_side_effect
    hw._toggle_laser1()
    laser1.on.assert_called_once()
    # .off() called again (the forced-off after estop).
    assert laser1.off.call_count >= 1
    # set_power NOT called with the staged value (estop aborted before it).
    laser1.set_power.assert_not_called()


# -- _toggle_laser2 branches ------------------------------------------------


def test_toggle_laser2_off_when_active_surfaces_off_error() -> None:
    """laser2 active -> .off() called; if .error set after, sig_message emit."""
    laser2 = _make_laser("L2", active=True)
    hw, shell = _make_hw(laser2=laser2)
    def off_side_effect():
        laser2.error = 1
        laser2.error_message = "off failed"
    laser2.off.side_effect = off_side_effect
    hw._toggle_laser2()
    laser2.off.assert_called_once()
    shell.sig_message.emit.assert_called_once()
    assert laser2.error == 0


def test_toggle_laser2_on_when_inactive_applies_staged_power() -> None:
    laser2 = _make_laser("L2", max_power=150.0, active=False)
    hw, shell = _make_hw(laser2=laser2, pct2=50.0)
    def on_side_effect():
        laser2.active = True
    laser2.on.side_effect = on_side_effect
    hw._toggle_laser2()
    laser2.on.assert_called_once()
    # 50% of 150 = 75 mW
    laser2.set_power.assert_called_with(75.0)


def test_toggle_laser2_on_error_emits_sig_message_and_returns() -> None:
    """laser2.on() sets error -> sig_message emit + early return (no staged power)."""
    laser2 = _make_laser("L2", max_power=150.0, active=False)
    hw, shell = _make_hw(laser2=laser2)
    def on_side_effect():
        laser2.error = 1
        laser2.error_message = "on failed"
        laser2.active = False
    laser2.on.side_effect = on_side_effect
    hw._toggle_laser2()
    shell.sig_message.emit.assert_called_once()
    assert laser2.error == 0
    # set_power NOT called with staged value (on failed -> early return).
    laser2.set_power.assert_not_called()


def test_toggle_laser2_estop_before_energize_skips_on() -> None:
    """estop set while in the off() branch above -> return before .on()."""
    laser2 = _make_laser("L2", active=False)
    hw, shell = _make_hw(laser2=laser2)
    # estop is set before the toggle, but the top-of-method check passes
    # because we want to exercise the inner re-check before .on().
    # Actually the top check returns immediately. To exercise the inner
    # re-check (line 263), estop must be set AFTER the top check but
    # before the .on() call. Use a side_effect on .off() — but laser2 is
    # inactive so .off() is not called. The inner re-check is reached
    # only via the else (inactive) branch. Set estop just before the
    # inner check by patching is_set.
    call_count = [0]
    def is_set_side():
        call_count[0] += 1
        # First call (top-of-method) False; second call (inner re-check) True.
        return call_count[0] >= 2
    shell.estop_event.is_set = is_set_side
    hw._toggle_laser2()
    laser2.on.assert_not_called()


def test_toggle_laser2_write_path_runs_after_on() -> None:
    """laser2 on succeeds -> _write_laser2_power is called with staged pct.
    The _write_laser2_power error-clear means the post-write error check
    (line 279) sees error=0, so the forced-off branch (line 280) is not
    reached — this test covers the happy-path write after a successful on."""
    laser2 = _make_laser("L2", max_power=150.0, active=False)
    hw, shell = _make_hw(laser2=laser2, pct2=50.0)
    def on_side_effect():
        laser2.active = True
    laser2.on.side_effect = on_side_effect
    hw._toggle_laser2()
    laser2.on.assert_called_once()
    # 50% of 150 = 75 mW — staged power written.
    laser2.set_power.assert_called_with(75.0)


# -- start_lasers / stop_lasers auto-laser2 branches ------------------------


def test_start_lasers_auto_laser2_writes_and_energizes() -> None:
    laser2 = _make_laser("L2", max_power=150.0, active=False)
    hw, shell = _make_hw(laser2=laser2, auto2=True, pct2=50.0)
    hw.start_lasers()
    # 50% of 150 = 75 mW
    laser2.set_power.assert_called_once_with(75.0)
    laser2.on.assert_called_once()


def test_start_lasers_auto_laser2_surfaces_on_error() -> None:
    laser2 = _make_laser("L2", max_power=150.0, active=False)
    hw, shell = _make_hw(laser2=laser2, auto2=True, pct2=50.0)
    def on_side_effect():
        laser2.error = 1
        laser2.error_message = "on failed"
    laser2.on.side_effect = on_side_effect
    hw.start_lasers()
    shell.sig_message.emit.assert_called_once()
    assert laser2.error == 0


def test_start_lasers_auto_laser1_surfaces_on_error() -> None:
    laser1 = _make_laser("L1", active=False)
    hw, shell = _make_hw(laser1=laser1, auto1=True, pct1=50.0)
    def on_side_effect():
        laser1.error = 1
        laser1.error_message = "on failed"
    laser1.on.side_effect = on_side_effect
    hw.start_lasers()
    shell.sig_message.emit.assert_called_once()
    assert laser1.error == 0


def test_stop_lasers_auto_laser1_off() -> None:
    laser1 = _make_laser("L1", active=True)
    hw, shell = _make_hw(laser1=laser1, auto1=True)
    hw.stop_lasers()
    laser1.off.assert_called_once()


def test_stop_lasers_auto_laser2_off() -> None:
    laser2 = _make_laser("L2", active=True)
    hw, shell = _make_hw(laser2=laser2, auto2=True)
    hw.stop_lasers()
    laser2.off.assert_called_once()


def test_stop_lasers_auto_laser1_surfaces_off_error() -> None:
    laser1 = _make_laser("L1", active=True)
    hw, shell = _make_hw(laser1=laser1, auto1=True)
    def off_side_effect():
        laser1.error = 1
        laser1.error_message = "off failed"
    laser1.off.side_effect = off_side_effect
    hw.stop_lasers()
    shell.sig_message.emit.assert_called_once()
    assert laser1.error == 0


def test_stop_lasers_auto_laser2_surfaces_off_error() -> None:
    laser2 = _make_laser("L2", active=True)
    hw, shell = _make_hw(laser2=laser2, auto2=True)
    def off_side_effect():
        laser2.error = 1
        laser2.error_message = "off failed"
    laser2.off.side_effect = off_side_effect
    hw.stop_lasers()
    shell.sig_message.emit.assert_called_once()
    assert laser2.error == 0


# -- _poll_laser_status branches --------------------------------------------


def test_poll_laser_status_error_branch() -> None:
    laser1 = _make_laser("L1", error=1)
    hw, shell = _make_hw(laser1=laser1)
    hw._poll_laser_status([0])
    shell.sig_laser_status.emit.assert_called_once_with(0, "error")


def test_poll_laser_status_active_branch() -> None:
    laser1 = _make_laser("L1", active=True, error=0)
    hw, shell = _make_hw(laser1=laser1)
    hw._poll_laser_status([0])
    shell.sig_laser_status.emit.assert_called_once_with(0, "active")


def test_poll_laser_status_inactive_branch() -> None:
    laser1 = _make_laser("L1", active=False, error=0)
    hw, shell = _make_hw(laser1=laser1)
    hw._poll_laser_status([0])
    shell.sig_laser_status.emit.assert_called_once_with(0, "inactive")


# -- _poll_laser2_status_gated branches -------------------------------------


def test_poll_laser2_status_gated_skips_when_lock_held() -> None:
    """When the laser2 lock is held by another thread, the gated poll
    returns immediately (the lock-held branch). RLock is reentrant so the
    lock must be held from a different thread to block acquire(blocking=False)."""
    laser2 = _make_laser("L2")
    hw, shell = _make_hw(laser2=laser2)
    held = threading.Event()
    release = threading.Event()

    def hold_lock():
        with laser2._lock:
            held.set()
            release.wait(timeout=2.0)

    t = threading.Thread(target=hold_lock, daemon=True)
    t.start()
    held.wait(timeout=2.0)
    try:
        hw._poll_laser2_status_gated()
    finally:
        release.set()
        t.join(timeout=2.0)
    shell.sig_laser_status.emit.assert_not_called()


def test_poll_laser2_status_gated_proceeds_when_lock_free() -> None:
    """When the lock is free, the gated poll proceeds with the status poll."""
    laser2 = _make_laser("L2", active=True)
    hw, shell = _make_hw(laser2=laser2)
    hw._poll_laser2_status_gated()
    shell.sig_laser_status.emit.assert_called_once_with(1, "active")


# -- _refresh_laser2_readback_async stacking guard --------------------------


def test_refresh_laser2_readback_async_skips_when_thread_alive() -> None:
    """When a prior readback thread is still running, the async refresh is a no-op."""
    laser2 = _make_laser("L2")
    hw, shell = _make_hw(laser2=laser2)
    # Plant a fake running QThread.
    fake_thread = Mock()
    fake_thread.isRunning.return_value = True
    hw._readback_thread = fake_thread
    hw._refresh_laser2_readback_async()
    # No new thread started — the fake thread is still the cached one.
    assert hw._readback_thread is fake_thread


def test_refresh_laser2_readback_async_starts_thread_when_none() -> None:
    """When no prior thread exists, a new QThread is started."""
    laser2 = _make_laser("L2", output_power=10.0)
    hw, shell = _make_hw(laser2=laser2)
    hw._refresh_laser2_readback_async()
    # Wait for the QThread to complete so the test doesn't leak.
    if hw._readback_thread is not None:
        hw._readback_thread.quit()
        hw._readback_thread.wait(2000)
    # A readback emit happened (the thread ran _refresh_laser_readback(1)).
    shell.sig_laser_readback.emit.assert_called()


# -- _refresh_laser_readback branches ---------------------------------------


def test_refresh_laser_readback_skips_when_lock_held() -> None:
    """When the laser lock is held by another thread, the readback returns
    immediately. RLock is reentrant so the lock must be held from a
    different thread to block acquire(blocking=False)."""
    laser1 = _make_laser("L1")
    hw, shell = _make_hw(laser1=laser1)
    held = threading.Event()
    release = threading.Event()

    def hold_lock():
        with laser1._lock:
            held.set()
            release.wait(timeout=2.0)

    t = threading.Thread(target=hold_lock, daemon=True)
    t.start()
    held.wait(timeout=2.0)
    try:
        hw._refresh_laser_readback(0)
    finally:
        release.set()
        t.join(timeout=2.0)
    shell.sig_laser_readback.emit.assert_not_called()


def test_refresh_laser_readback_l1_uncalibrated_emits_est_suffix() -> None:
    """L1 (idx=0) uncalibrated -> '(est.)' suffix in the emit text."""
    laser1 = _make_laser("L1", output_power=150.0, calibrated=False)
    hw, shell = _make_hw(laser1=laser1)
    hw._refresh_laser_readback(0)
    shell.sig_laser_readback.emit.assert_called_once()
    args, _ = shell.sig_laser_readback.emit.call_args
    assert "(est.)" in args[1]


def test_refresh_laser_readback_l1_calibrated_emits_cal_suffix() -> None:
    """L1 (idx=0) calibrated -> '(cal.)' suffix in the emit text."""
    laser1 = _make_laser("L1", output_power=150.0, calibrated=True)
    hw, shell = _make_hw(laser1=laser1)
    hw._refresh_laser_readback(0)
    shell.sig_laser_readback.emit.assert_called_once()
    args, _ = shell.sig_laser_readback.emit.call_args
    assert "(cal.)" in args[1]


def test_refresh_laser_readback_l2_with_value_emits_mw() -> None:
    """L2 (idx=1) with a real readback value -> '{value:.1f} mW' text."""
    laser2 = _make_laser("L2", output_power=75.0)
    hw, shell = _make_hw(laser2=laser2)
    hw._refresh_laser_readback(1)
    shell.sig_laser_readback.emit.assert_called_once()
    args, _ = shell.sig_laser_readback.emit.call_args
    assert "75.0 mW" in args[1]
    assert "(cmd)" not in args[1]


def test_refresh_laser_readback_l2_none_emits_cmd_fallback() -> None:
    """L2 (idx=1) with None readback -> '{power:.1f} mW (cmd)' fallback."""
    laser2 = _make_laser("L2", output_power=None, power=50.0)
    hw, shell = _make_hw(laser2=laser2)
    hw._refresh_laser_readback(1)
    shell.sig_laser_readback.emit.assert_called_once()
    args, _ = shell.sig_laser_readback.emit.call_args
    assert "(cmd)" in args[1]
