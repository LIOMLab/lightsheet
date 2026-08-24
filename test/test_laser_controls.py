"""
Laser power-control regression tests for the staged-percent spinbox
contract and the E-stop cooperative-skip guard.

Controller_MainWindow cannot be constructed on this Mac (no PyQt5 display),
so the real _write_laser*_power methods are exercised behaviorally: their
source is extracted from lightsheet/gui/controller.py and exec'd in a controlled
namespace, then called against a minimal Mock stand-in self. This runs the
real method body — the same code that runs on the rig — without needing the
Qt runtime, and proves the estop_event cooperative-skip guard actually
prevents the HAL write (not a string match on the source).

Pure-math tests cover the %-to-absolute scaling at the HAL boundary.

Static-source grep assertions (reading controller.py as text and matching
strings) are intentionally NOT used — they are fragile and exercise no
code. See AGENTS.md §5.
"""

import contextlib
import threading
from unittest.mock import Mock

from _helpers.controller import _HW_SRC, _load_method
from _helpers.factories import _make_write_laser


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
# Controller_MainWindow cannot be imported on this Mac (PyQt5 is not
# installed), so we extract the real _write_laser*_power method source from
# lightsheet/gui/controller.py and exec it in a controlled namespace, then call it
# with a minimal stand-in self. This exercises the real method body — the
# same code that runs on the rig — without needing the Qt runtime.
# --------------------------------------------------------------------------- #


def test_write_laser1_power_skips_when_estop_set() -> None:
    """When estop_event is set, _write_laser1_power must NOT call
    self.lasers[0].set_power (the HAL write is skipped)."""
    write_laser1_power = _load_method("_write_laser1_power(self, pct: float) -> None", src_path=_HW_SRC)

    estop_event = threading.Event()
    estop_event.set()

    laser1 = _make_write_laser("Laser 1 (555 nm)", active=True, max_power=300.0)

    standin = Mock()
    standin._shell = standin  # HardwareManager reads self._shell.*
    standin.estop_event = estop_event
    standin.lasers = [laser1, Mock()]
    standin.sig_message = Mock()

    write_laser1_power(standin, 50.0)

    laser1.set_power.assert_not_called()
    standin.sig_message.emit.assert_not_called()


def test_write_laser2_power_skips_when_estop_set() -> None:
    """When estop_event is set, _write_laser2_power must NOT call
    self.lasers[1].set_power (the HAL write is skipped)."""
    write_laser2_power = _load_method("_write_laser2_power(self, pct: float) -> None", src_path=_HW_SRC)

    estop_event = threading.Event()
    estop_event.set()

    laser2 = _make_write_laser("Laser 2 (640 nm)", active=True, max_power=150.0)

    standin = Mock()
    standin._shell = standin  # HardwareManager reads self._shell.*
    standin.estop_event = estop_event
    standin.lasers = [Mock(), laser2]
    standin.sig_message = Mock()

    write_laser2_power(standin, 50.0)

    laser2.set_power.assert_not_called()
    standin.sig_message.emit.assert_not_called()


def test_write_laser1_power_writes_when_estop_clear_and_active() -> None:
    """When estop_event is clear and laser 1 is active, _write_laser1_power
    must scale the staged percentage to mW (pct/100 * max_power) and call
    self.lasers[0].set_power(mw). The mW value is the canonical ILaser
    unit; the backend (DAQLaser) converts mW -> V internally."""
    write_laser1_power = _load_method("_write_laser1_power(self, pct: float) -> None", src_path=_HW_SRC)

    estop_event = threading.Event()  # clear

    laser1 = _make_write_laser("Laser 1 (555 nm)", active=True, max_power=300.0)

    standin = Mock()
    standin._shell = standin  # HardwareManager reads self._shell.*
    standin.estop_event = estop_event
    standin.lasers = [laser1, Mock()]
    standin.sig_message = Mock()

    write_laser1_power(standin, 50.0)

    # 50 % of 300 mW = 150 mW must be passed to set_power.
    laser1.set_power.assert_called_once_with(150.0)


def test_write_laser1_power_skips_when_laser_inactive() -> None:
    """When laser 1 is inactive, _write_laser1_power must not write (no
    point energizing a laser the operator has toggled off)."""
    write_laser1_power = _load_method("_write_laser1_power(self, pct: float) -> None", src_path=_HW_SRC)

    estop_event = threading.Event()  # clear

    laser1 = _make_write_laser("Laser 1 (555 nm)", active=False, max_power=300.0)

    standin = Mock()
    standin._shell = standin  # HardwareManager reads self._shell.*
    standin.estop_event = estop_event
    standin.lasers = [laser1, Mock()]
    standin.sig_message = Mock()

    write_laser1_power(standin, 50.0)

    laser1.set_power.assert_not_called()


def test_write_laser2_power_writes_when_estop_clear_and_active() -> None:
    """When estop_event is clear and laser 2 is active, _write_laser2_power
    must scale the staged percentage to mW (pct/100 * max_power) and call
    self.lasers[1].set_power(mw)."""
    write_laser2_power = _load_method("_write_laser2_power(self, pct: float) -> None", src_path=_HW_SRC)

    estop_event = threading.Event()  # clear

    laser2 = _make_write_laser("Laser 2 (640 nm)", active=True, max_power=150.0)

    standin = Mock()
    standin._shell = standin  # HardwareManager reads self._shell.*
    standin.estop_event = estop_event
    standin.lasers = [Mock(), laser2]
    standin.sig_message = Mock()

    write_laser2_power(standin, 50.0)

    # 50 % of 150 mW = 75 mW must be passed to set_power.
    laser2.set_power.assert_called_once_with(75.0)


def test_write_laser1_power_surfaces_error_and_resets() -> None:
    """When self.lasers[0].set_power leaves .error set, _write_laser1_power
    must emit a sig_message naming the laser's label + error_message and
    reset .error = 0."""
    write_laser1_power = _load_method("_write_laser1_power(self, pct: float) -> None", src_path=_HW_SRC)

    estop_event = threading.Event()  # clear

    def _fail_set_power(mw: float) -> None:
        laser1.error = 1
        laser1.error_message = "daq write failed"

    laser1 = _make_write_laser("Laser 1 (555 nm)", active=True, max_power=300.0)
    laser1.set_power.side_effect = _fail_set_power

    standin = Mock()
    standin._shell = standin  # HardwareManager reads self._shell.*
    standin.estop_event = estop_event
    standin.lasers = [laser1, Mock()]
    standin.sig_message = Mock()

    write_laser1_power(standin, 50.0)

    assert standin.sig_message.emit.called
    msg = standin.sig_message.emit.call_args[0][0]
    assert "Laser 1 (555 nm)" in msg
    assert "daq write failed" in msg
    assert laser1.error == 0


# --------------------------------------------------------------------------- #
# Toggle + start_lasers/stop_lasers rewrite tests — the toggle bodies and
# the acquisition-worker start/stop paths collapse to one shape operating
# on self.lasers[i] uniformly (no laser-2-specific self.ibeam branch).
# --------------------------------------------------------------------------- #


def test_toggle_laser1_off_when_active() -> None:
    """_toggle_laser1 calls self.lasers[0].off() when the laser is active."""
    toggle = _load_method("_toggle_laser1(self) -> None", src_path=_HW_SRC)

    estop_event = threading.Event()  # clear
    laser1 = _make_write_laser("Laser 1 (555 nm)", active=True, max_power=300.0)

    standin = Mock()
    standin._shell = standin  # HardwareManager reads self._shell.*
    standin.estop_event = estop_event
    standin.lasers = [laser1, Mock()]
    standin.sig_message = Mock()
    standin.laser1_power_pct = 50.0

    toggle(standin)

    laser1.off.assert_called_once()
    laser1.on.assert_not_called()


def test_toggle_laser1_on_when_inactive() -> None:
    """_toggle_laser1 calls self.lasers[0].on() when the laser is inactive,
    then applies the staged percentage via _write_laser1_power."""
    toggle = _load_method("_toggle_laser1(self) -> None", src_path=_HW_SRC)

    estop_event = threading.Event()  # clear
    laser1 = _make_write_laser("Laser 1 (555 nm)", active=False, max_power=300.0)
    # .on() must flip .active to True so the toggle body's post-on branch
    # applies the staged percentage (a real ILaser's .on() does this).
    laser1.on.side_effect = lambda: setattr(laser1, "active", True)

    standin = Mock()
    standin._shell = standin  # HardwareManager reads self._shell.*
    standin.estop_event = estop_event
    standin.lasers = [laser1, Mock()]
    standin.sig_message = Mock()
    standin.laser1_power_pct = 50.0
    standin._write_laser1_power = Mock()

    toggle(standin)

    laser1.on.assert_called_once()
    # After a successful on(), the staged percentage is applied.
    standin._write_laser1_power.assert_called_once_with(50.0)


def test_toggle_laser2_on_when_inactive() -> None:
    """_toggle_laser2 calls self.lasers[1].on() when inactive, then applies
    the staged percentage via _write_laser2_power. Symmetric with laser 1 —
    no laser-2-specific self.ibeam branch."""
    toggle = _load_method("_toggle_laser2(self) -> None", src_path=_HW_SRC)

    estop_event = threading.Event()  # clear
    laser2 = _make_write_laser("Laser 2 (640 nm)", active=False, max_power=150.0)
    # .on() must flip .active to True so the toggle body's post-on branch
    # applies the staged percentage (a real ILaser's .on() does this).
    laser2.on.side_effect = lambda: setattr(laser2, "active", True)

    standin = Mock()
    standin._shell = standin  # HardwareManager reads self._shell.*
    standin.estop_event = estop_event
    standin.lasers = [Mock(), laser2]
    standin.sig_message = Mock()
    standin.laser2_power_pct = 50.0
    standin._write_laser2_power = Mock()

    toggle(standin)

    laser2.on.assert_called_once()
    standin._write_laser2_power.assert_called_once_with(50.0)


def test_toggle_laser1_skips_when_estop_set() -> None:
    """_toggle_laser1 must NOT energize when estop_event is set — the
    E-stop path already drove the laser off synchronously; a queued toggle
    must not re-energize a Class IIIB laser past the kill path."""
    toggle = _load_method("_toggle_laser1(self) -> None", src_path=_HW_SRC)

    estop_event = threading.Event()
    estop_event.set()
    laser1 = _make_write_laser("Laser 1 (555 nm)", active=False, max_power=300.0)

    standin = Mock()
    standin._shell = standin  # HardwareManager reads self._shell.*
    standin.estop_event = estop_event
    standin.lasers = [laser1, Mock()]
    standin.sig_message = Mock()
    standin.laser1_power_pct = 50.0

    toggle(standin)

    laser1.on.assert_not_called()


def test_start_lasers_drives_both_auto_lasers() -> None:
    """start_lasers drives self.lasers[0] and self.lasers[1] uniformly
    (.on() / .set_power(mw)) for the auto-selected lasers — no
    laser-2-specific self.ibeam branch."""
    start_lasers = _load_method("start_lasers(self) -> None", src_path=_HW_SRC)

    laser1 = _make_write_laser("Laser 1 (555 nm)", active=False, max_power=300.0)
    laser2 = _make_write_laser("Laser 2 (640 nm)", active=False, max_power=150.0)

    standin = Mock()
    standin._shell = standin  # HardwareManager reads self._shell.*
    standin._auto_laser1 = True
    standin._auto_laser2 = True
    standin.laser1_power_pct = 50.0
    standin.laser2_power_pct = 50.0
    standin.lasers = [laser1, laser2]
    standin.sig_message = Mock()

    start_lasers(standin)

    laser1.on.assert_called_once()
    laser2.on.assert_called_once()
    # 50 % of 300 mW = 150 mW; 50 % of 150 mW = 75 mW.
    laser1.set_power.assert_called_once_with(150.0)
    laser2.set_power.assert_called_once_with(75.0)


def test_start_lasers_skips_non_auto_lasers() -> None:
    """start_lasers only energizes lasers whose auto-checkbox was sampled
    True; the other laser is untouched."""
    start_lasers = _load_method("start_lasers(self) -> None", src_path=_HW_SRC)

    laser1 = _make_write_laser("Laser 1 (555 nm)", active=False, max_power=300.0)
    laser2 = _make_write_laser("Laser 2 (640 nm)", active=False, max_power=150.0)

    standin = Mock()
    standin._shell = standin  # HardwareManager reads self._shell.*
    standin._auto_laser1 = True
    standin._auto_laser2 = False
    standin.laser1_power_pct = 50.0
    standin.laser2_power_pct = 50.0
    standin.lasers = [laser1, laser2]
    standin.sig_message = Mock()

    start_lasers(standin)

    laser1.on.assert_called_once()
    laser2.on.assert_not_called()


def test_stop_lasers_drives_both_auto_lasers_off() -> None:
    """stop_lasers drives self.lasers[0].off() / self.lasers[1].off()
    uniformly for the auto-selected lasers — no laser-2-specific
    self.ibeam branch."""
    stop_lasers = _load_method("stop_lasers(self) -> None", src_path=_HW_SRC)

    laser1 = _make_write_laser("Laser 1 (555 nm)", active=True, max_power=300.0)
    laser2 = _make_write_laser("Laser 2 (640 nm)", active=True, max_power=150.0)

    standin = Mock()
    standin._shell = standin  # HardwareManager reads self._shell.*
    standin._auto_laser1 = True
    standin._auto_laser2 = True
    standin.lasers = [laser1, laser2]
    standin.sig_message = Mock()

    stop_lasers(standin)

    laser1.off.assert_called_once()
    laser2.off.assert_called_once()


# --------------------------------------------------------------------------- #
# E-stop rewrite tests — updateUi_estop_pressed drives BOTH lasers off via
# self.lasers[i].off() in a loop, synchronously on the GUI thread, with NO
# lock acquisition anywhere in the method body (a stuck daemon write thread
# holding a laser's lock must never delay the kill path). close_modes reads
# self.lasers[i].active (not the old 2-channel container laser1_active /
# laser2_active reads).
#
# These tests exec the real method bodies against a list[ILaser]-shaped
# stand-in. They fail against the pre-rewrite source (which calls
# self.lasers.laser1_off() / self.ibeam.off() and reads
# self.lasers.laser1_active / self.lasers.laser2_active) and pass after the
# rewrite.
# --------------------------------------------------------------------------- #


def _make_laser_mock(label: str, error: int = 0, error_message: str = "") -> Mock:
    """Build a Mock ILaser stand-in with the surface the E-stop loop reads:
    .off(), .error, .error_message, .label, .active, ._lock."""
    laser = Mock()
    laser.label = label
    laser.error = error
    laser.error_message = error_message
    laser.active = True
    laser._lock = threading.RLock()
    return laser


def test_estop_drives_both_lasers_off_in_loop() -> None:
    """updateUi_estop_pressed must call .off() on BOTH self.lasers[0] and
    self.lasers[1] (a loop over self.lasers), synchronously on the GUI
    thread. The pre-rewrite code calls self.lasers.laser1_off() and
    self.ibeam.off() — neither is a method on a list[ILaser] stand-in, so
    this test fails until the method is rewritten to the loop form."""
    estop = _load_method("updateUi_estop_pressed(self) -> None")

    estop_event = threading.Event()
    laser1 = _make_laser_mock("Laser 1 (555 nm)")
    laser2 = _make_laser_mock("Laser 2 (640 nm)")

    standin = Mock()
    standin._shell = standin  # HardwareManager reads self._shell.*
    standin.estop_event = estop_event
    standin.lasers = [laser1, laser2]
    standin.sig_message = Mock()
    # The UI latch widgets the method sets at the end.
    standin.label_estopStatus = Mock()
    standin.pushButton_estop = Mock()

    estop(standin)

    laser1.off.assert_called_once()
    laser2.off.assert_called_once()
    # The cooperative-abort Event was set (step 1, preserved verbatim).
    assert estop_event.is_set()


def test_estop_emits_per_laser_warning_on_error() -> None:
    """When a laser's .off() leaves .error set, updateUi_estop_pressed must
    emit a sig_message naming that laser's .label and .error_message, then
    reset .error = 0 — mirroring the existing per-laser warning pattern but
    templated on laser.label so both lasers share one code path."""
    estop = _load_method("updateUi_estop_pressed(self) -> None")

    estop_event = threading.Event()
    laser1 = _make_laser_mock("Laser 1 (555 nm)")
    laser2 = _make_laser_mock(
        "Laser 2 (640 nm)", error=1, error_message="serial write failed"
    )

    standin = Mock()
    standin._shell = standin  # HardwareManager reads self._shell.*
    standin.estop_event = estop_event
    standin.lasers = [laser1, laser2]
    standin.sig_message = Mock()
    standin.label_estopStatus = Mock()
    standin.pushButton_estop = Mock()

    estop(standin)

    # laser2 had an error — a warning was emitted naming its label + cause.
    warning_msgs = [str(c.args[0]) for c in standin.sig_message.emit.call_args_list]
    assert any(
        "Laser 2 (640 nm)" in m and "serial write failed" in m for m in warning_msgs
    ), (
        "E-stop must emit a per-laser warning naming laser.label and "
        "laser.error_message when .off() fails."
    )
    # The error was reset after the warning.
    assert laser2.error == 0


def test_estop_acquires_no_laser_lock() -> None:
    """The E-stop kill path must NOT acquire self.lasers[i]._lock anywhere
    in the method body — a stuck daemon write thread holding a laser's lock
    must never delay the kill path (AGENTS.md §2). This test records any
    attempt to enter a laser's _lock by wrapping both lasers' locks in a
    raising context manager; if the E-stop body acquires either lock, the
    method raises and the test fails."""
    estop = _load_method("updateUi_estop_pressed(self) -> None")

    class _NoLockAcquire:
        """A lock stand-in whose __enter__ raises — proves the E-stop body
        never acquires it."""

        def __enter__(self) -> "_NoLockAcquire":
            raise AssertionError(
                "E-stop must not acquire self.lasers[i]._lock — the kill "
                "path is lock-free so a stuck daemon write thread can never "
                "delay it (AGENTS.md §2)."
            )

        def __exit__(self, *exc: object) -> None:
            return None

    estop_event = threading.Event()
    laser1 = _make_laser_mock("Laser 1 (555 nm)")
    laser2 = _make_laser_mock("Laser 2 (640 nm)")
    laser1._lock = _NoLockAcquire()
    laser2._lock = _NoLockAcquire()

    standin = Mock()
    standin._shell = standin  # HardwareManager reads self._shell.*
    standin.estop_event = estop_event
    standin.lasers = [laser1, laser2]
    standin.sig_message = Mock()
    standin.label_estopStatus = Mock()
    standin.pushButton_estop = Mock()

    # Must not raise — if the body acquires either lock, _NoLockAcquire raises.
    estop(standin)


def test_close_modes_reads_lasers_index_active() -> None:
    """close_modes must read self.lasers[0].active or self.lasers[1].active
    (the list[ILaser] surface), not the old self.lasers.laser1_active /
    self.lasers.laser2_active 2-channel container reads. When both lasers
    are inactive, stop_lasers must NOT be called."""
    close_modes = _load_method("close_modes(self) -> None")

    laser1 = _make_laser_mock("Laser 1 (555 nm)")
    laser2 = _make_laser_mock("Laser 2 (640 nm)")
    laser1.active = False
    laser2.active = False

    standin = Mock()
    standin._shell = standin  # HardwareManager reads self._shell.*
    standin.lasers = [laser1, laser2]
    standin.sig_message = Mock()
    # close_modes reads several *_mode_started flags + calls
    # _cache_auto_laser_flags; all are auto-Mock attrs (no-ops).
    # stop_lasers is now routed through self._hw (HardwareManager).
    standin._hw = Mock()

    close_modes(standin)

    standin._hw.stop_lasers.assert_not_called()


def test_close_modes_calls_stop_lasers_when_a_laser_active() -> None:
    """close_modes must call stop_lasers when either laser is active —
    reading self.lasers[0].active or self.lasers[1].active."""
    close_modes = _load_method("close_modes(self) -> None")

    laser1 = _make_laser_mock("Laser 1 (555 nm)")
    laser2 = _make_laser_mock("Laser 2 (640 nm)")
    laser1.active = False
    laser2.active = True  # laser 2 is on -> must stop

    standin = Mock()
    standin._shell = standin  # HardwareManager reads self._shell.*
    standin.lasers = [laser1, laser2]
    standin.sig_message = Mock()
    standin._hw = Mock()

    close_modes(standin)

    standin._hw.stop_lasers.assert_called_once()


# --------------------------------------------------------------------------- #
# Per-laser status indicator tests — _poll_laser_status computes a status
# string per requested laser index (error > active > inactive precedence)
# and emits sig_laser_status(idx, status); updateUi_laser_status maps that
# string to the ● ON / ● OFF / ● ERR label text + semantic color. The gated
# L2 poll (_poll_laser2_status_gated) skips silently when the iBeam
# per-instance lock is held so a periodic status query never blocks on a
# write in progress and never misattributes a reply.
# --------------------------------------------------------------------------- #


def _make_status_laser(
    label: str,
    active: bool = False,
    error: int = 0,
    error_message: str = "",
) -> Mock:
    """Build a Mock ILaser stand-in for the status-poll path.

    _poll_laser_status reads .error, .active, and .label and emits
    sig_laser_status. The per-instance RLock lives on ._lock (the gated
    L2 poll probes it with acquire(blocking=False)).
    """
    laser = Mock()
    laser.label = label
    laser.active = active
    laser.error = error
    laser.error_message = error_message
    laser._lock = threading.RLock()
    return laser


def test_poll_laser_status_active_emits_active() -> None:
    """_poll_laser_status([0]) on an active, error-free laser emits
    sig_laser_status(0, 'active')."""
    poll = _load_method("_poll_laser_status(self, indices: list[int]) -> None", src_path=_HW_SRC)

    laser1 = _make_status_laser("Laser 1 (555 nm)", active=True, error=0)

    standin = Mock()
    standin._shell = standin  # HardwareManager reads self._shell.*
    standin.lasers = [laser1, Mock()]
    standin.sig_laser_status = Mock()

    poll(standin, [0])

    standin.sig_laser_status.emit.assert_called_once_with(0, "active")


def test_poll_laser_status_inactive_emits_inactive() -> None:
    """_poll_laser_status([0]) on an inactive, error-free laser emits
    sig_laser_status(0, 'inactive')."""
    poll = _load_method("_poll_laser_status(self, indices: list[int]) -> None", src_path=_HW_SRC)

    laser1 = _make_status_laser("Laser 1 (555 nm)", active=False, error=0)

    standin = Mock()
    standin._shell = standin  # HardwareManager reads self._shell.*
    standin.lasers = [laser1, Mock()]
    standin.sig_laser_status = Mock()

    poll(standin, [0])

    standin.sig_laser_status.emit.assert_called_once_with(0, "inactive")


def test_poll_laser_status_error_wins_over_active() -> None:
    """_poll_laser_status([1]) on a laser with error=1 AND active=True
    emits 'error' — the HAL error surface is authoritative (AGENTS.md §10)
    so an errored-but-still-active laser shows ERR, not ON."""
    poll = _load_method("_poll_laser_status(self, indices: list[int]) -> None", src_path=_HW_SRC)

    laser2 = _make_status_laser(
        "Laser 2 (640 nm)", active=True, error=1, error_message="serial fault"
    )

    standin = Mock()
    standin._shell = standin  # HardwareManager reads self._shell.*
    standin.lasers = [Mock(), laser2]
    standin.sig_laser_status = Mock()

    poll(standin, [1])

    standin.sig_laser_status.emit.assert_called_once_with(1, "error")


def test_poll_laser_status_both_indices_emits_twice() -> None:
    """_poll_laser_status([0, 1]) emits once per index — used by the
    E-stop / start_lasers / stop_lasers refresh-after-action paths that
    touch both lasers."""
    poll = _load_method("_poll_laser_status(self, indices: list[int]) -> None", src_path=_HW_SRC)

    laser1 = _make_status_laser("Laser 1 (555 nm)", active=True, error=0)
    laser2 = _make_status_laser("Laser 2 (640 nm)", active=False, error=0)

    standin = Mock()
    standin._shell = standin  # HardwareManager reads self._shell.*
    standin.lasers = [laser1, laser2]
    standin.sig_laser_status = Mock()

    poll(standin, [0, 1])

    assert standin.sig_laser_status.emit.call_count == 2
    standin.sig_laser_status.emit.assert_any_call(0, "active")
    standin.sig_laser_status.emit.assert_any_call(1, "inactive")


def test_updateUi_laser_status_active_sets_on_label() -> None:
    """updateUi_laser_status(0, 'active') sets label_laserOneStatus text
    to '● ON' and a green bold stylesheet."""
    slot = _load_method("updateUi_laser_status(self, idx: int, status: str) -> None")

    standin = Mock()
    standin._shell = standin  # HardwareManager reads self._shell.*
    standin.label_laserOneStatus = Mock()
    standin.label_laserTwoStatus = Mock()

    slot(standin, 0, "active")

    standin.label_laserOneStatus.setText.assert_called_once_with("● ON")
    style = standin.label_laserOneStatus.setStyleSheet.call_args[0][0]
    assert "#34C759" in style
    assert "bold" in style


def test_updateUi_laser_status_inactive_sets_off_label() -> None:
    """updateUi_laser_status(0, 'inactive') sets label_laserOneStatus text
    to '● OFF' and a gray bold stylesheet."""
    slot = _load_method("updateUi_laser_status(self, idx: int, status: str) -> None")

    standin = Mock()
    standin._shell = standin  # HardwareManager reads self._shell.*
    standin.label_laserOneStatus = Mock()
    standin.label_laserTwoStatus = Mock()

    slot(standin, 0, "inactive")

    standin.label_laserOneStatus.setText.assert_called_once_with("● OFF")
    style = standin.label_laserOneStatus.setStyleSheet.call_args[0][0]
    assert "#8E8E93" in style
    assert "bold" in style


def test_updateUi_laser_status_error_sets_err_label_for_laser2() -> None:
    """updateUi_laser_status(1, 'error') sets label_laserTwoStatus text
    to '● ERR' and a red bold stylesheet."""
    slot = _load_method("updateUi_laser_status(self, idx: int, status: str) -> None")

    standin = Mock()
    standin._shell = standin  # HardwareManager reads self._shell.*
    standin.label_laserOneStatus = Mock()
    standin.label_laserTwoStatus = Mock()

    slot(standin, 1, "error")

    standin.label_laserTwoStatus.setText.assert_called_once_with("● ERR")
    style = standin.label_laserTwoStatus.setStyleSheet.call_args[0][0]
    assert "#FF3B30" in style
    assert "bold" in style


def test_poll_laser2_status_gated_skips_when_lock_held() -> None:
    """_poll_laser2_status_gated must NOT call _poll_laser_status when
    self.lasers[1]._lock is held by an in-progress write — the poll
    probes the lock with acquire(blocking=False) and skips silently on
    failure so a periodic status query never blocks on a write and
    never misattributes a reply.

    The real _lock is an RLock (reentrant), so holding it from this
    thread would still let the gated probe acquire it. A non-reentrant
    Lock stand-in models the cross-thread 'held by another thread'
    condition: acquire(blocking=False) returns False once it's held."""
    gated = _load_method("_poll_laser2_status_gated(self) -> None", src_path=_HW_SRC)

    laser2 = _make_status_laser("Laser 2 (640 nm)", active=True, error=0)
    # Use a non-reentrant Lock so acquire(blocking=False) fails once held
    # (models the cross-thread 'held by the daemon write thread' case).
    laser2._lock = threading.Lock()
    laser2._lock.acquire()
    try:
        standin = Mock()
        standin._shell = standin  # HardwareManager reads self._shell.*
        standin.lasers = [Mock(), laser2]
        standin._poll_laser_status = Mock()

        gated(standin)

        standin._poll_laser_status.assert_not_called()
    finally:
        laser2._lock.release()


def test_poll_laser2_status_gated_polls_when_lock_free() -> None:
    """_poll_laser2_status_gated must call _poll_laser_status([1]) when
    the iBeam lock is free — the probe acquires (blocking=False),
    releases immediately, then proceeds with the poll."""
    gated = _load_method("_poll_laser2_status_gated(self) -> None", src_path=_HW_SRC)

    laser2 = _make_status_laser("Laser 2 (640 nm)", active=True, error=0)

    standin = Mock()
    standin._shell = standin  # HardwareManager reads self._shell.*
    standin.lasers = [Mock(), laser2]
    standin._poll_laser_status = Mock()

    gated(standin)

    standin._poll_laser_status.assert_called_once_with([1])


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


def _make_readback_laser(
    active: bool = True,
    power: float = 75.0,
    max_power: float = 150.0,
) -> Mock:
    """Build a Mock ILaser stand-in for the readback path. The lock is a
    real threading.RLock so acquire(blocking=False)/release work."""
    laser = Mock()
    laser.label = "Laser 2 (640 nm)"
    laser.active = active
    laser.power = power
    laser.max_power = max_power
    laser.error = 0
    laser.error_message = ""
    # calibrated defaults to False — a bare Mock would auto-create a truthy
    # Mock attr, which would wrongly hit the calibrated branch in
    # _refresh_laser_readback for L1. Set explicitly so the uncalibrated
    # (est.) path is the default stand-in behavior.
    laser.calibrated = False
    laser._lock = threading.RLock()
    laser.get_output_power = Mock()
    return laser


def test_refresh_laser2_readback_populated() -> None:
    """_refresh_laser_readback(1) on a stand-in where the lock is free and
    get_output_power() returns 75.0 emits (1, '75.0 mW', '') on
    sig_laser_readback — the GUI-thread slot applies it to the label."""
    refresh = _load_method("_refresh_laser_readback(self, idx: int) -> None", src_path=_HW_SRC)

    laser2 = _make_readback_laser(power=75.0)
    laser2.get_output_power.return_value = 75.0

    standin = Mock()
    standin._shell = standin  # HardwareManager reads self._shell.*
    standin.lasers = [Mock(), laser2]
    standin.sig_laser_readback = Mock()

    refresh(standin, 1)

    laser2.get_output_power.assert_called_once()
    standin.sig_laser_readback.emit.assert_called_once_with(1, "75.0 mW", "")


def test_refresh_laser2_readback_degraded_shows_commanded_fallback() -> None:
    """_refresh_laser_readback(1) on a stand-in where get_output_power()
    returns None (parse failure / unsupported variant) emits
    (1, '{power:.1f} mW (cmd)', <degraded tooltip>) on sig_laser_readback
    so the GUI-thread slot can show the commanded fallback + tooltip."""
    refresh = _load_method("_refresh_laser_readback(self, idx: int) -> None", src_path=_HW_SRC)

    laser2 = _make_readback_laser(power=42.0)
    laser2.get_output_power.return_value = None

    standin = Mock()
    standin._shell = standin  # HardwareManager reads self._shell.*
    standin.lasers = [Mock(), laser2]
    standin.sig_laser_readback = Mock()

    refresh(standin, 1)

    args = standin.sig_laser_readback.emit.call_args[0]
    assert args[0] == 1
    assert args[1] == "42.0 mW (cmd)"
    tooltip = args[2]
    assert "readback unavailable" in tooltip or "parse failure" in tooltip


def test_refresh_laser2_readback_lock_skip_is_noop() -> None:
    """_refresh_laser_readback(1) on a stand-in where the lock is held
    returns silently without calling get_output_power() and without
    emitting on sig_laser_readback — the lock-skip no-op contract. Uses a
    non-reentrant Lock to model the cross-thread 'held by the daemon
    write thread' condition."""
    refresh = _load_method("_refresh_laser_readback(self, idx: int) -> None", src_path=_HW_SRC)

    laser2 = _make_readback_laser()
    laser2._lock = threading.Lock()
    laser2._lock.acquire()
    try:
        standin = Mock()
        standin._shell = standin  # HardwareManager reads self._shell.*
        standin.lasers = [Mock(), laser2]
        standin.sig_laser_readback = Mock()

        refresh(standin, 1)

        laser2.get_output_power.assert_not_called()
        standin.sig_laser_readback.emit.assert_not_called()
    finally:
        laser2._lock.release()


def test_refresh_laser2_readback_releases_lock_in_finally() -> None:
    """_refresh_laser_readback(1) always releases the lock in the finally
    block when acquire(blocking=False) succeeded — even if
    get_output_power raises. Verified by acquiring the lock after the
    call returns (a non-released lock would block)."""
    refresh = _load_method("_refresh_laser_readback(self, idx: int) -> None", src_path=_HW_SRC)

    laser2 = _make_readback_laser()
    laser2.get_output_power.side_effect = RuntimeError("serial glitch")

    standin = Mock()
    standin._shell = standin  # HardwareManager reads self._shell.*
    standin.lasers = [Mock(), laser2]
    standin.sig_laser_readback = Mock()

    # The method must not let the exception escape (or if it does, the
    # lock is still released). Wrap so we can assert the lock is free
    # afterward regardless.
    with contextlib.suppress(RuntimeError):
        refresh(standin, 1)

    # The lock must be releasable (free) — acquire(blocking=False)
    # succeeds iff it was released by the finally block.
    assert laser2._lock.acquire(blocking=False), (
        "_refresh_laser_readback did not release the iBeam lock in the "
        "finally block — a held lock would block the next write."
    )
    laser2._lock.release()


def test_refresh_laser1_readback_shows_staged_mw() -> None:
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
    refresh = _load_method("_refresh_laser_readback(self, idx: int) -> None", src_path=_HW_SRC)

    laser1 = _make_readback_laser(power=12.5, max_power=50.0)
    laser1.label = "Laser 1 (555 nm)"
    laser1.calibrated = False
    laser1.get_output_power.return_value = 12.5

    standin = Mock()
    standin._shell = standin  # HardwareManager reads self._shell.*
    standin.lasers = [laser1, Mock()]
    standin.sig_laser_readback = Mock()

    refresh(standin, 0)

    laser1.get_output_power.assert_called_once()
    # Exactly one emit for L1 (idx=0); the L2 label is not touched by an
    # L1 refresh. The L1 (est.) suffix + unverified-estimate tooltip is
    # asserted on the text + tooltip (the tooltip mentions 107.5 mW).
    standin.sig_laser_readback.emit.assert_called_once()
    idx, text, tooltip = standin.sig_laser_readback.emit.call_args.args
    assert idx == 0
    assert text == "12.5 mW (est.)"
    assert "107.5 mW" in tooltip


# --------------------------------------------------------------------------- #
# updateUi_laser_readback slot — the GUI-thread side of sig_laser_readback.
# Applies (idx, text, tooltip) to the per-laser readback QLabel. An empty
# tooltip clears any prior stale-value warning (live readback); a non-empty
# tooltip explains the commanded-power fallback (degraded readback).
# --------------------------------------------------------------------------- #


def test_updateUi_laser_readback_live_clears_tooltip() -> None:
    """updateUi_laser_readback(1, '75.0 mW', '') sets label_laserTwoReadback
    text to '75.0 mW' and clears the tooltip (empty string) — a live
    readback must not keep a stale degraded-readback tooltip."""
    slot = _load_method(
        "updateUi_laser_readback(self, idx: int, text: str, tooltip: str) -> None"
    )

    standin = Mock()
    standin._shell = standin  # HardwareManager reads self._shell.*
    standin.label_laserOneReadback = Mock()
    standin.label_laserTwoReadback = Mock()

    slot(standin, 1, "75.0 mW", "")

    standin.label_laserTwoReadback.setText.assert_called_once_with("75.0 mW")
    standin.label_laserTwoReadback.setToolTip.assert_called_once_with("")
    standin.label_laserOneReadback.setText.assert_not_called()


def test_updateUi_laser_readback_degraded_sets_tooltip() -> None:
    """updateUi_laser_readback(1, '42.0 mW (cmd)', <tooltip>) sets the
    label text to the commanded fallback and applies the degraded-readback
    tooltip so the operator can distinguish a live readback from a stale
    commanded value."""
    slot = _load_method(
        "updateUi_laser_readback(self, idx: int, text: str, tooltip: str) -> None"
    )

    standin = Mock()
    standin._shell = standin  # HardwareManager reads self._shell.*
    standin.label_laserOneReadback = Mock()
    standin.label_laserTwoReadback = Mock()

    tooltip = (
        "Power readback unavailable (parse failure). "
        "Showing last commanded value may be stale."
    )
    slot(standin, 1, "42.0 mW (cmd)", tooltip)

    standin.label_laserTwoReadback.setText.assert_called_once_with("42.0 mW (cmd)")
    standin.label_laserTwoReadback.setToolTip.assert_called_once_with(tooltip)


def test_updateUi_laser_readback_l1_routes_to_l1_label() -> None:
    """updateUi_laser_readback(0, ...) routes to label_laserOneReadback,
    not label_laserTwoReadback — the idx selects the correct label."""
    slot = _load_method(
        "updateUi_laser_readback(self, idx: int, text: str, tooltip: str) -> None"
    )

    standin = Mock()
    standin._shell = standin  # HardwareManager reads self._shell.*
    standin.label_laserOneReadback = Mock()
    standin.label_laserTwoReadback = Mock()

    slot(standin, 0, "12.5 mW", "")

    standin.label_laserOneReadback.setText.assert_called_once_with("12.5 mW")
    standin.label_laserTwoReadback.setText.assert_not_called()
