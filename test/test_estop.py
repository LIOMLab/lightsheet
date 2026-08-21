'''
Stdlib threading.Event semantics tests for the E-stop cooperative-abort path,
plus static-source assertions that the controller's kill-path wiring is
present.

These tests document the exact threading.Event behavior that
gui/controller.py relies on for the E-stop:

  - The system starts ARMED: a fresh threading.Event() is clear (not set),
    so worker loops run normally.
  - Re-pressing E-stop is safe: calling .set() twice on the same Event leaves
    it set with no error (idempotent panic control).
  - The Arm/Reset sequence clears the Event: .set() then .clear() leaves it
    unset, so worker loops resume on the next acquisition.
  - A worker loop that polls `if estop_event.is_set(): break` at the top of
    each iteration exits immediately (zero body executions) when the Event is
    pre-set — validating the poll-point placement logic independent of the
    real PyQt5 GUI, which cannot be instantiated on this Mac.

Controller_MainWindow cannot be constructed here (no PyQt5 display), so the
kill-path wiring itself is verified by static-source assertions against
gui/controller.py: the E-stop handler must synchronously drive both lasers
off (lasers.laser1_off + ibeam.off) and check ibeam.error to warn on serial
failure, and each acquisition worker must poll estop_event.is_set(). These
grep-based assertions add real regression protection without instantiating Qt.
'''

import os
import re
import sys
sys.path.append(".")

import threading

_CONTROLLER_SRC = os.path.join(os.path.dirname(__file__), '..', 'gui', 'controller.py')


def _read_controller_source():
    with open(_CONTROLLER_SRC, 'r') as f:
        return f.read()


def test_estop_event_starts_clear():
    """A fresh threading.Event (mirroring self.estop_event's initial state)
    is unset — the system starts ARMED, not actuated."""
    estop_event = threading.Event()
    assert estop_event.is_set() is False


def test_estop_event_set_is_idempotent():
    """Calling .set() twice leaves the Event set with no error — re-pressing
    E-stop is safe and does not raise."""
    estop_event = threading.Event()
    estop_event.set()
    estop_event.set()  # idempotent — no exception
    assert estop_event.is_set() is True


def test_estop_event_clear_after_set():
    """The Arm/Reset sequence: .set() then .clear() leaves the Event unset,
    so worker loops resume on the next acquisition."""
    estop_event = threading.Event()
    estop_event.set()
    estop_event.clear()
    assert estop_event.is_set() is False


def test_worker_poll_logic_breaks_on_set():
    """A worker loop polling `if estop_event.is_set(): break` at the top of
    each iteration runs zero body iterations when the Event is pre-set.

    This validates the poll-point placement logic (poll BEFORE the frame
    acquisition work, not after) independent of the real GUI/Qt — the same
    shape used in live_mode_worker, single_mode_worker, and stack_mode_worker.
    """
    estop_event = threading.Event()
    estop_event.set()  # E-stop actuated before the loop starts

    iterations = 0
    stop_flag = True  # mimic live_mode_started gating entry
    while stop_flag:
        if estop_event.is_set():
            break
        iterations += 1
        # Guard against an accidental infinite loop if the poll logic is wrong
        if iterations > 10:
            break

    assert iterations == 0


# --------------------------------------------------------------------------- #
# Static-source assertions on gui/controller.py — the safety-critical kill
# path that cannot be exercised by instantiating Controller_MainWindow on Mac.
# These guard against regressions where the E-stop handler or worker poll
# points are accidentally removed or weakened.
# --------------------------------------------------------------------------- #

def test_estop_handler_drives_both_lasers_off():
    """updateUi_estop_pressed must synchronously call lasers.laser1_off()
    and ibeam.off() on the GUI thread (not via a queue or worker)."""
    src = _read_controller_source()
    # Locate the E-stop handler body and assert both kill calls are present.
    m = re.search(r'def updateUi_estop_pressed\(self\):', src)
    assert m, "updateUi_estop_pressed handler is missing"
    body = src[m.start():]
    # Limit to this method (up to the next def at column 4).
    end = re.search(r'\n    def |\n    @pyqtSlot', body[1:])
    if end:
        body = body[:end.start() + 1]
    assert 'self.lasers.laser1_off()' in body, (
        "E-stop handler must synchronously call self.lasers.laser1_off()")
    assert 'self.ibeam.off()' in body, (
        "E-stop handler must synchronously call self.ibeam.off()")


def test_estop_handler_warns_on_ibeam_serial_failure():
    """The E-stop handler must check ibeam.error after ibeam.off() and emit
    the 'may STILL BE ON' warning on serial failure (the off() call catches
    SerialException internally and never re-raises, so a try/except cannot
    detect the failure — the handler must inspect the error surface)."""
    src = _read_controller_source()
    m = re.search(r'def updateUi_estop_pressed\(self\):', src)
    assert m
    body = src[m.start():]
    end = re.search(r'\n    def |\n    @pyqtSlot', body[1:])
    if end:
        body = body[:end.start() + 1]
    assert 'self.ibeam.error' in body, (
        "E-stop handler must check self.ibeam.error after ibeam.off()")
    assert 'STILL BE ON' in body, (
        "E-stop handler must emit the 'may STILL BE ON' warning on failure")


def test_estop_event_set_in_handler():
    """The E-stop handler must set estop_event so worker loops abort."""
    src = _read_controller_source()
    m = re.search(r'def updateUi_estop_pressed\(self\):', src)
    assert m
    body = src[m.start():]
    end = re.search(r'\n    def |\n    @pyqtSlot', body[1:])
    if end:
        body = body[:end.start() + 1]
    assert 'self.estop_event.set()' in body, (
        "E-stop handler must call self.estop_event.set()")


def test_worker_loops_poll_estop_event():
    """Each acquisition worker (single_mode_worker, stack_mode_worker) must
    poll estop_event.is_set() so a mid-acquisition E-stop aborts the run."""
    src = _read_controller_source()
    for worker in ('single_mode_worker', 'stack_mode_worker'):
        m = re.search(r'def ' + worker + r'\(self\):', src)
        assert m, f"{worker} is missing"
        body = src[m.start():]
        end = re.search(r'\n    def ', body[1:])
        if end:
            body = body[:end.start() + 1]
        assert 'self.estop_event.is_set()' in body, (
            f"{worker} must poll self.estop_event.is_set()")
