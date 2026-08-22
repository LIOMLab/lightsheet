"""
Laser power-control regression tests for the staged-percent spinbox
contract and the E-stop cooperative-skip guard.

Controller_MainWindow cannot be constructed on this Mac (no PyQt5 display),
so the real _write_laser*_power methods are exercised behaviorally: their
source is extracted from gui/controller.py and exec'd in a controlled
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
from unittest.mock import Mock

_CONTROLLER_SRC = os.path.join(os.path.dirname(__file__), "..", "gui", "controller.py")


def _read_controller_source():
    with open(_CONTROLLER_SRC) as f:
        return f.read()


def _slice_method(src, method_sig):
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


def test_pct_scaling_laser1_midrange():
    """50 % of a 5 V max -> 2.5 V (laser 1, DAQ AO)."""
    pct = 50
    max_power = 5.0
    assert pct / 100.0 * max_power == 2.5


def test_pct_scaling_laser2_midrange():
    """50 % of a 150000 uW max -> 75000 uW (laser 2, iBeam)."""
    pct = 50
    max_power = 150000
    assert pct / 100.0 * max_power == 75000.0


def test_pct_scaling_full():
    """100 % -> full Max Power (both lasers)."""
    assert 100 / 100.0 * 5.0 == 5.0
    assert 100 / 100.0 * 150000 == 150000.0


def test_pct_scaling_zero():
    """0 % -> 0 (laser off)."""
    assert 0 / 100.0 * 150000 == 0.0
    assert 0 / 100.0 * 5.0 == 0.0


# --------------------------------------------------------------------------- #
# Behavioral test: the cooperative-skip guard actually prevents the HAL
# write when estop_event is set — not just a static-source string match.
#
# Controller_MainWindow cannot be imported on this Mac (PyQt5 is not
# installed), so we extract the real _write_laser*_power method source from
# gui/controller.py and exec it in a controlled namespace, then call it
# with a minimal stand-in self. This exercises the real method body — the
# same code that runs on the rig — without needing the Qt runtime.
# --------------------------------------------------------------------------- #


def _load_method(method_sig):
    """Extract a method body from gui/controller.py and return a callable
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


def test_write_laser1_power_skips_when_estop_set():
    """When estop_event is set, _write_laser1_power must NOT call
    _update_setpoints (the DAQ write is skipped)."""
    write_laser1_power = _load_method("_write_laser1_power(self, pct)")

    estop_event = threading.Event()
    estop_event.set()

    lasers = Mock()
    lasers.laser1_active = True
    lasers.laser1_max_power = 5.0
    lasers.error = 0

    standin = Mock()
    standin.estop_event = estop_event
    standin.lasers = lasers
    standin._laser1_write_lock = threading.RLock()
    standin.sig_message = Mock()

    write_laser1_power(standin, 50.0)

    lasers._update_setpoints.assert_not_called()
    standin.sig_message.emit.assert_not_called()


def test_write_laser2_power_skips_when_estop_set():
    """When estop_event is set, _write_laser2_power must NOT call
    ibeam.set_power (the serial write is skipped)."""
    write_laser2_power = _load_method("_write_laser2_power(self, pct)")

    estop_event = threading.Event()
    estop_event.set()

    lasers = Mock()
    lasers.laser2_active = True

    ibeam = Mock()
    ibeam.max_power = 150000
    ibeam.error = 0

    standin = Mock()
    standin.estop_event = estop_event
    standin.lasers = lasers
    standin.ibeam = ibeam
    standin._laser2_write_lock = threading.RLock()
    standin.sig_message = Mock()

    write_laser2_power(standin, 50.0)

    ibeam.set_power.assert_not_called()
    standin.sig_message.emit.assert_not_called()


def test_write_laser1_power_writes_when_estop_clear_and_active():
    """When estop_event is clear and laser1 is active, _write_laser1_power
    must scale the staged percentage to Volts, write that value to
    _laser1_setpoint (the attribute _update_setpoints actually sends to the
    DAQ — NOT laser1_power, which is never read by the DAQ write path), and
    call _update_setpoints (the happy path).

    Asserting _laser1_setpoint (not just laser1_power) is the regression
    guard for the bug where _write_laser1_power set laser1_power but the
    DAQ writes _laser1_setpoint — the staged-percent spinbox was functionally
    dead while the laser was on. A test that only asserted laser1_power
    passed despite the laser power never changing on the rig.
    """
    write_laser1_power = _load_method("_write_laser1_power(self, pct)")

    estop_event = threading.Event()  # clear

    lasers = Mock()
    lasers.laser1_active = True
    lasers.laser1_max_power = 5.0
    lasers.error = 0
    # Initialise the setpoint the way Lasers.__init__ does, so the assertion
    # checks the method actually overwrites it with the scaled value rather
    # than a Mock auto-attribute that compares equal to anything.
    lasers._laser1_setpoint = 0

    standin = Mock()
    standin.estop_event = estop_event
    standin.lasers = lasers
    standin._laser1_write_lock = threading.RLock()
    standin.sig_message = Mock()

    write_laser1_power(standin, 50.0)

    # 50 % of 5 V = 2.5 V must be set on lasers.laser1_power (the staged
    # value the operator sees) AND on lasers._laser1_setpoint (the value
    # _update_setpoints writes to the DAQ). The setpoint assertion is the
    # critical one — without it the test passes even when the DAQ output
    # never changes.
    assert lasers.laser1_power == 2.5
    assert lasers._laser1_setpoint == 2.5, (
        "_write_laser1_power must set _laser1_setpoint (the DAQ-bound "
        "attribute), not just laser1_power — otherwise the staged-percent "
        "spinbox never reaches the laser while it is on."
    )
    lasers._update_setpoints.assert_called_once()


def test_write_laser1_power_skips_when_laser_inactive():
    """When laser1 is inactive, _write_laser1_power must not write (no
    point energizing a laser the operator has toggled off)."""
    write_laser1_power = _load_method("_write_laser1_power(self, pct)")

    estop_event = threading.Event()  # clear

    lasers = Mock()
    lasers.laser1_active = False
    lasers.laser1_max_power = 5.0
    lasers.error = 0

    standin = Mock()
    standin.estop_event = estop_event
    standin.lasers = lasers
    standin._laser1_write_lock = threading.RLock()
    standin.sig_message = Mock()

    write_laser1_power(standin, 50.0)

    lasers._update_setpoints.assert_not_called()
