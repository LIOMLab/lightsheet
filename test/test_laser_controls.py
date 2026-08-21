'''
Laser power-control regression tests for the staged-percent spinbox
contract, the offloaded/debounced write wiring, and the E-stop
cooperative-skip guard.

Controller_MainWindow cannot be constructed on this Mac (no PyQt5 display),
so the wiring is verified by static-source assertions against
gui/controller.py (following test_estop.py's _read_controller_source() +
method-body-slicing pattern), plus pure-math tests for the %-to-absolute
scaling and a behavioral test that calls the real _write_laser*_power
unbound method against a minimal stand-in self to prove the estop_event
cooperative-skip guard actually prevents the HAL write (not just a
static-source string match).

These tests guard the safety-critical invariants:
  - Both spinboxes are 0-100 % staged setpoints scaled to each laser's
    Max Power only at the HAL call boundary.
  - Toggle and amplitude HAL writes are offloaded off the GUI thread.
  - The E-stop path (updateUi_estop_pressed) remains fully synchronous on
    the GUI thread — never offloaded, never waiting on a lock.
  - Once estop_event is set, no offloaded amplitude/toggle write can
    re-energize either laser (cooperative-skip guard gates the write,
    not just exists somewhere in the method).
'''

import os
import re
import sys
sys.path.append(".")

import threading
from unittest.mock import Mock

_CONTROLLER_SRC = os.path.join(os.path.dirname(__file__), '..', 'gui', 'controller.py')


def _read_controller_source():
    with open(_CONTROLLER_SRC, 'r') as f:
        return f.read()


def _slice_method(src, method_sig):
    """Return the body of a method, from its `def <sig>:` line up to the
    next top-level def/@pyqtSlot decorator."""
    m = re.search(r'def ' + re.escape(method_sig) + r':', src)
    assert m, f"{method_sig} is missing"
    body = src[m.start():]
    end = re.search(r'\n    def |\n    @pyqtSlot', body[1:])
    if end:
        body = body[:end.start() + 1]
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
# Static-source assertions: toggle offload + E-stop stays synchronous.
# --------------------------------------------------------------------------- #

def test_laser1_toggle_offloaded():
    """laser1_toggle_button must spawn a worker thread rather than calling
    self.lasers.laser1_toggle() directly in the slot body (GUI freeze fix)."""
    src = _read_controller_source()
    body = _slice_method(src, 'laser1_toggle_button(self)')
    assert 'threading.Thread(target=' in body, (
        "laser1_toggle_button must offload via threading.Thread")
    assert 'self.lasers.laser1_toggle()' not in body, (
        "laser1_toggle_button must not call self.lasers.laser1_toggle() "
        "directly in the slot body")


def test_laser2_toggle_offloaded():
    """laser2_toggle_button must spawn a worker thread rather than calling
    self.ibeam.on()/off() directly in the slot body."""
    src = _read_controller_source()
    body = _slice_method(src, 'laser2_toggle_button(self)')
    assert 'threading.Thread(target=' in body, (
        "laser2_toggle_button must offload via threading.Thread")
    assert 'self.ibeam.on()' not in body, (
        "laser2_toggle_button must not call self.ibeam.on() directly")
    assert 'self.ibeam.off()' not in body, (
        "laser2_toggle_button must not call self.ibeam.off() directly")


def test_estop_handler_remains_synchronous():
    """updateUi_estop_pressed must still directly call lasers.laser1_off()
    and ibeam.off() with no threading.Thread wrapping — the kill path must
    never be offloaded or wait on a lock (AGENTS.md §2)."""
    src = _read_controller_source()
    body = _slice_method(src, 'updateUi_estop_pressed(self)')
    assert 'self.lasers.laser1_off()' in body, (
        "E-stop handler must synchronously call self.lasers.laser1_off()")
    assert 'self.ibeam.off()' in body, (
        "E-stop handler must synchronously call self.ibeam.off()")
    assert 'threading.Thread' not in body, (
        "E-stop handler must NOT be offloaded to a worker thread")


# --------------------------------------------------------------------------- #
# Static-source assertions: scaling boundary + cooperative-skip ordering.
# --------------------------------------------------------------------------- #

def test_write_laser1_power_scaling_and_estop_guard():
    """_write_laser1_power must reference laser1_max_power (scaling
    boundary) and the estop_event.is_set() check must appear before the
    _update_setpoints() call within the same body (cooperative-skip gates
    the write, not just exists somewhere in the method)."""
    src = _read_controller_source()
    body = _slice_method(src, '_write_laser1_power(self, pct)')
    assert 'self.lasers.laser1_max_power' in body, (
        "_write_laser1_power must scale via self.lasers.laser1_max_power")
    estop_idx = body.find('self.estop_event.is_set()')
    write_idx = body.find('self.lasers._update_setpoints()')
    assert estop_idx != -1, "_write_laser1_power must check estop_event"
    assert write_idx != -1, "_write_laser1_power must call _update_setpoints"
    assert estop_idx < write_idx, (
        "_write_laser1_power: estop_event check must precede the DAQ write")


def test_write_laser2_power_scaling_and_estop_guard():
    """_write_laser2_power must reference ibeam.max_power (scaling
    boundary) and the estop_event.is_set() check must appear before the
    ibeam.set_power( call within the same body."""
    src = _read_controller_source()
    body = _slice_method(src, '_write_laser2_power(self, pct)')
    assert 'self.ibeam.max_power' in body, (
        "_write_laser2_power must scale via self.ibeam.max_power")
    estop_idx = body.find('self.estop_event.is_set()')
    write_idx = body.find('self.ibeam.set_power(')
    assert estop_idx != -1, "_write_laser2_power must check estop_event"
    assert write_idx != -1, "_write_laser2_power must call ibeam.set_power"
    assert estop_idx < write_idx, (
        "_write_laser2_power: estop_event check must precede the serial write")


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
    exec(compile(body, _CONTROLLER_SRC, 'exec'), namespace)
    func_name = method_sig.split('(')[0].strip()
    return namespace[func_name]


def test_write_laser1_power_skips_when_estop_set():
    """When estop_event is set, _write_laser1_power must NOT call
    _update_setpoints (the DAQ write is skipped)."""
    write_laser1_power = _load_method('_write_laser1_power(self, pct)')

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
    write_laser2_power = _load_method('_write_laser2_power(self, pct)')

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
    must scale and call _update_setpoints (the happy path)."""
    write_laser1_power = _load_method('_write_laser1_power(self, pct)')

    estop_event = threading.Event()  # clear

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

    # 50 % of 5 V = 2.5 V was set on lasers.laser1_power before the write.
    assert lasers.laser1_power == 2.5
    lasers._update_setpoints.assert_called_once()


def test_write_laser1_power_skips_when_laser_inactive():
    """When laser1 is inactive, _write_laser1_power must not write (no
    point energizing a laser the operator has toggled off)."""
    write_laser1_power = _load_method('_write_laser1_power(self, pct)')

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
