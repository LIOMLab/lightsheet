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

import os
import re
import threading
from collections.abc import Callable
from typing import Any
from unittest.mock import Mock

_CONTROLLER_SRC = os.path.join(
    os.path.dirname(__file__), "..", "lightsheet", "gui", "controller.py"
)


def _read_controller_source() -> str:
    with open(_CONTROLLER_SRC) as f:
        return f.read()


def _slice_method(src: str, method_sig: str) -> str:
    """Return the body of a method, from its `def <sig>:` line up to the
    next top-level def/@pyqtSlot decorator."""
    m = re.search(r"def " + re.escape(method_sig) + r":", src)
    assert m, f"{method_sig} is missing"
    body = src[m.start() :]
    end = re.search(r"\n    def |\n    @pyqtSlot", body[1:])
    if end:
        body = body[: end.start() + 1]
    return body


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


def _load_method(method_sig: str) -> Callable[..., Any]:
    """Extract a method body from lightsheet/gui/controller.py and return a callable
    `func(self, pct)` that executes the real source."""
    src = _read_controller_source()
    body = _slice_method(src, method_sig)
    # The body starts with `def <sig>:` — strip the docstring/def line and
    # re-wrap as a standalone function. _slice_method returns from the
    # `def` line, so the whole thing is already a valid function def.
    namespace = {}
    exec(compile(body, _CONTROLLER_SRC, "exec"), namespace)
    func_name = method_sig.split("(")[0].strip()
    return namespace[func_name]


def _make_write_laser(
    label: str,
    active: bool = True,
    max_power: float = 5.0,
    error: int = 0,
    error_message: str = "",
) -> Mock:
    """Build a Mock ILaser stand-in for the _write_laser*_power paths.

    The write paths read .active, .max_power, .error, .error_message,
    .label, and call .set_power(mw). The per-instance RLock lives on
    ._lock (the daemon-thread write path acquires it).
    """
    laser = Mock()
    laser.label = label
    laser.active = active
    laser.max_power = max_power
    laser.error = error
    laser.error_message = error_message
    laser._lock = threading.RLock()
    return laser


def test_write_laser1_power_skips_when_estop_set() -> None:
    """When estop_event is set, _write_laser1_power must NOT call
    self.lasers[0].set_power (the HAL write is skipped)."""
    write_laser1_power = _load_method("_write_laser1_power(self, pct: float) -> None")

    estop_event = threading.Event()
    estop_event.set()

    laser1 = _make_write_laser("Laser 1 (561 nm)", active=True, max_power=300.0)

    standin = Mock()
    standin.estop_event = estop_event
    standin.lasers = [laser1, Mock()]
    standin.sig_message = Mock()

    write_laser1_power(standin, 50.0)

    laser1.set_power.assert_not_called()
    standin.sig_message.emit.assert_not_called()


def test_write_laser2_power_skips_when_estop_set() -> None:
    """When estop_event is set, _write_laser2_power must NOT call
    self.lasers[1].set_power (the HAL write is skipped)."""
    write_laser2_power = _load_method("_write_laser2_power(self, pct: float) -> None")

    estop_event = threading.Event()
    estop_event.set()

    laser2 = _make_write_laser("Laser 2 (640 nm)", active=True, max_power=150.0)

    standin = Mock()
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
    write_laser1_power = _load_method("_write_laser1_power(self, pct: float) -> None")

    estop_event = threading.Event()  # clear

    laser1 = _make_write_laser("Laser 1 (561 nm)", active=True, max_power=300.0)

    standin = Mock()
    standin.estop_event = estop_event
    standin.lasers = [laser1, Mock()]
    standin.sig_message = Mock()

    write_laser1_power(standin, 50.0)

    # 50 % of 300 mW = 150 mW must be passed to set_power.
    laser1.set_power.assert_called_once_with(150.0)


def test_write_laser1_power_skips_when_laser_inactive() -> None:
    """When laser 1 is inactive, _write_laser1_power must not write (no
    point energizing a laser the operator has toggled off)."""
    write_laser1_power = _load_method("_write_laser1_power(self, pct: float) -> None")

    estop_event = threading.Event()  # clear

    laser1 = _make_write_laser("Laser 1 (561 nm)", active=False, max_power=300.0)

    standin = Mock()
    standin.estop_event = estop_event
    standin.lasers = [laser1, Mock()]
    standin.sig_message = Mock()

    write_laser1_power(standin, 50.0)

    laser1.set_power.assert_not_called()


def test_write_laser2_power_writes_when_estop_clear_and_active() -> None:
    """When estop_event is clear and laser 2 is active, _write_laser2_power
    must scale the staged percentage to mW (pct/100 * max_power) and call
    self.lasers[1].set_power(mw)."""
    write_laser2_power = _load_method("_write_laser2_power(self, pct: float) -> None")

    estop_event = threading.Event()  # clear

    laser2 = _make_write_laser("Laser 2 (640 nm)", active=True, max_power=150.0)

    standin = Mock()
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
    write_laser1_power = _load_method("_write_laser1_power(self, pct: float) -> None")

    estop_event = threading.Event()  # clear

    def _fail_set_power(mw: float) -> None:
        laser1.error = 1
        laser1.error_message = "daq write failed"

    laser1 = _make_write_laser("Laser 1 (561 nm)", active=True, max_power=300.0)
    laser1.set_power.side_effect = _fail_set_power

    standin = Mock()
    standin.estop_event = estop_event
    standin.lasers = [laser1, Mock()]
    standin.sig_message = Mock()

    write_laser1_power(standin, 50.0)

    assert standin.sig_message.emit.called
    msg = standin.sig_message.emit.call_args[0][0]
    assert "Laser 1 (561 nm)" in msg
    assert "daq write failed" in msg
    assert laser1.error == 0


# --------------------------------------------------------------------------- #
# Toggle + start_lasers/stop_lasers rewrite tests — the toggle bodies and
# the acquisition-worker start/stop paths collapse to one shape operating
# on self.lasers[i] uniformly (no laser-2-specific self.ibeam branch).
# --------------------------------------------------------------------------- #


def test_toggle_laser1_off_when_active() -> None:
    """_toggle_laser1 calls self.lasers[0].off() when the laser is active."""
    toggle = _load_method("_toggle_laser1(self) -> None")

    estop_event = threading.Event()  # clear
    laser1 = _make_write_laser("Laser 1 (561 nm)", active=True, max_power=300.0)

    standin = Mock()
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
    toggle = _load_method("_toggle_laser1(self) -> None")

    estop_event = threading.Event()  # clear
    laser1 = _make_write_laser("Laser 1 (561 nm)", active=False, max_power=300.0)
    # .on() must flip .active to True so the toggle body's post-on branch
    # applies the staged percentage (a real ILaser's .on() does this).
    laser1.on.side_effect = lambda: setattr(laser1, "active", True)

    standin = Mock()
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
    toggle = _load_method("_toggle_laser2(self) -> None")

    estop_event = threading.Event()  # clear
    laser2 = _make_write_laser("Laser 2 (640 nm)", active=False, max_power=150.0)
    # .on() must flip .active to True so the toggle body's post-on branch
    # applies the staged percentage (a real ILaser's .on() does this).
    laser2.on.side_effect = lambda: setattr(laser2, "active", True)

    standin = Mock()
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
    toggle = _load_method("_toggle_laser1(self) -> None")

    estop_event = threading.Event()
    estop_event.set()
    laser1 = _make_write_laser("Laser 1 (561 nm)", active=False, max_power=300.0)

    standin = Mock()
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
    start_lasers = _load_method("start_lasers(self) -> None")

    laser1 = _make_write_laser("Laser 1 (561 nm)", active=False, max_power=300.0)
    laser2 = _make_write_laser("Laser 2 (640 nm)", active=False, max_power=150.0)

    standin = Mock()
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
    start_lasers = _load_method("start_lasers(self) -> None")

    laser1 = _make_write_laser("Laser 1 (561 nm)", active=False, max_power=300.0)
    laser2 = _make_write_laser("Laser 2 (640 nm)", active=False, max_power=150.0)

    standin = Mock()
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
    stop_lasers = _load_method("stop_lasers(self) -> None")

    laser1 = _make_write_laser("Laser 1 (561 nm)", active=True, max_power=300.0)
    laser2 = _make_write_laser("Laser 2 (640 nm)", active=True, max_power=150.0)

    standin = Mock()
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


def _make_laser_mock(
    label: str, error: int = 0, error_message: str = ""
) -> Mock:
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
    laser1 = _make_laser_mock("Laser 1 (561 nm)")
    laser2 = _make_laser_mock("Laser 2 (640 nm)")

    standin = Mock()
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
    laser1 = _make_laser_mock("Laser 1 (561 nm)")
    laser2 = _make_laser_mock(
        "Laser 2 (640 nm)", error=1, error_message="serial write failed"
    )

    standin = Mock()
    standin.estop_event = estop_event
    standin.lasers = [laser1, laser2]
    standin.sig_message = Mock()
    standin.label_estopStatus = Mock()
    standin.pushButton_estop = Mock()

    estop(standin)

    # laser2 had an error — a warning was emitted naming its label + cause.
    warning_msgs = [
        str(c.args[0]) for c in standin.sig_message.emit.call_args_list
    ]
    assert any(
        "Laser 2 (640 nm)" in m and "serial write failed" in m
        for m in warning_msgs
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
    laser1 = _make_laser_mock("Laser 1 (561 nm)")
    laser2 = _make_laser_mock("Laser 2 (640 nm)")
    laser1._lock = _NoLockAcquire()
    laser2._lock = _NoLockAcquire()

    standin = Mock()
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

    laser1 = _make_laser_mock("Laser 1 (561 nm)")
    laser2 = _make_laser_mock("Laser 2 (640 nm)")
    laser1.active = False
    laser2.active = False

    standin = Mock()
    standin.lasers = [laser1, laser2]
    standin.sig_message = Mock()
    # close_modes reads several *_mode_started flags + calls
    # _cache_auto_laser_flags; all are auto-Mock attrs (no-ops).
    standin.stop_lasers = Mock()

    close_modes(standin)

    standin.stop_lasers.assert_not_called()


def test_close_modes_calls_stop_lasers_when_a_laser_active() -> None:
    """close_modes must call stop_lasers when either laser is active —
    reading self.lasers[0].active or self.lasers[1].active."""
    close_modes = _load_method("close_modes(self) -> None")

    laser1 = _make_laser_mock("Laser 1 (561 nm)")
    laser2 = _make_laser_mock("Laser 2 (640 nm)")
    laser1.active = False
    laser2.active = True  # laser 2 is on -> must stop

    standin = Mock()
    standin.lasers = [laser1, laser2]
    standin.sig_message = Mock()
    standin.stop_lasers = Mock()

    close_modes(standin)

    standin.stop_lasers.assert_called_once()
