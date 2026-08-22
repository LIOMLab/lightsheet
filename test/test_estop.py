"""
Stdlib threading.Event semantics tests for the E-stop cooperative-abort path.

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

The kill-path wiring itself (updateUi_estop_pressed drives both lasers off,
every worker polls estop_event.is_set()) is NOT verified by static-source
greps — those are fragile and exercise no code. See AGENTS.md §5: when a
class cannot be instantiated on Mac, exercise the real method via exec of
its extracted body against a Mock stand-in, or test the HAL logic in
isolation. Do not grep the source.
"""

import threading


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
