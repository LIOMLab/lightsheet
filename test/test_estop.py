"""
Stdlib threading.Event semantics tests for the E-stop cooperative-abort path.

These tests document the exact threading.Event behavior that
lightsheet/gui/controller.py relies on for the E-stop:

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

regression gate (god-object split): HardwareManager must
NOT declare an estop/kill/e_stop method — the E-stop kill path stays in the
shell with a direct list[ILaser] ref, lock-free, on the GUI thread. A future
maintainer who sees HardwareManager.estop() will be tempted to queue/thread
it — the single most safety-critical regression risk.
"""

import threading


def test_estop_event_starts_clear() -> None:
    """A fresh threading.Event (mirroring self.estop_event's initial state)
    is unset — the system starts ARMED, not actuated."""
    estop_event = threading.Event()
    assert estop_event.is_set() is False


def test_estop_event_set_is_idempotent() -> None:
    """Calling .set() twice leaves the Event set with no error — re-pressing
    E-stop is safe and does not raise."""
    estop_event = threading.Event()
    estop_event.set()
    estop_event.set()  # idempotent — no exception
    assert estop_event.is_set() is True


def test_estop_event_clear_after_set() -> None:
    """The Arm/Reset sequence: .set() then .clear() leaves the Event unset,
    so worker loops resume on the next acquisition."""
    estop_event = threading.Event()
    estop_event.set()
    estop_event.clear()
    assert estop_event.is_set() is False


def test_worker_poll_logic_breaks_on_set() -> None:
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
# regression gate — HardwareManager must NOT own an estop method.
# The E-stop kill path stays in the shell (updateUi_estop_pressed) with a
# direct list[ILaser] ref, lock-free, on the GUI thread. This gate runs at
# every future commit touching lightsheet/gui/hardware_manager.py.
# --------------------------------------------------------------------------- #


def test_hardware_manager_has_no_estop_method() -> None:
    """HardwareManager must NOT declare an estop/kill/e_stop method — the
    E-stop kill path stays in the shell (safety anti-pattern)."""
    from lightsheet.gui.hardware_manager import HardwareManager

    assert not hasattr(HardwareManager, "estop"), (
        "HardwareManager must NOT declare an estop method (safety anti-pattern) "
        "— the E-stop kill path stays in the shell, lock-free on the GUI thread."
    )
    assert not hasattr(HardwareManager, "kill"), (
        "HardwareManager must NOT declare a kill method"
    )
    assert not hasattr(HardwareManager, "e_stop"), (
        "HardwareManager must NOT declare an e_stop method"
    )


# --------------------------------------------------------------------------- #
# regression gate — MotorController must NOT own an estop method.
# MotorController is a motion collaborator (motor-move + focus/interpolation-
# display slots), NOT a safety kill-path owner. The E-stop kill path stays in
# the shell (updateUi_estop_pressed) with a direct list[ILaser] ref, lock-free,
# on the GUI thread. A future maintainer who sees MotorController.estop() will
# be tempted to queue/thread it — the single most safety-critical regression
# risk. Mirrors the HardwareManager anti-pattern check.
# --------------------------------------------------------------------------- #


def test_motor_controller_has_no_estop_method() -> None:
    """MotorController must NOT declare an estop/kill/e_stop method — motion
    collaborators are not safety kill-path owners (safety anti-pattern)."""
    from lightsheet.gui.motor_controller import MotorController

    assert not hasattr(MotorController, "estop"), (
        "MotorController must NOT declare an estop method (safety anti-pattern) "
        "— the E-stop kill path stays in the shell, lock-free on the GUI thread."
    )
    assert not hasattr(MotorController, "kill"), (
        "MotorController must NOT declare a kill method"
    )
    assert not hasattr(MotorController, "e_stop"), (
        "MotorController must NOT declare an e_stop method"
    )
