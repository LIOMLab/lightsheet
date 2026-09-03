"""Two-press Arm/Reset UX — 3-step indicator + state-aware button labels.

The E-stop re-arm sequence is a two-press state machine (AGENTS.md §2 —
no single-press re-arm of a Class IIIB laser). The state transitions are:

    ARMED --(E-stop)--> ACTUATED --(1st Arm/Reset)--> DISARMED
    --(2nd Arm/Reset)--> ARMED

The UI must make this state machine explicit on screen (audit #6):
  - ``label_estopStatus`` shows the 3-step indicator with the current step:
        ``● E-STOP ACTUATED`` (#FF3B30 bold) / ``● DISARMED`` (#8E8E93 bold) /
        ``● ARMED`` (#34C759 bold).
  - ``pushButton_armReset`` shows the NEXT action available:
        ``Clear E-stop`` (when ACTUATED) / ``Arm Lasers`` (when DISARMED) /
        ``Arm/Reset`` (when ARMED).
  - ``pushButton_armReset`` tooltip documents the two-press sequence.
  - A single press from ACTUATED must NOT re-arm — it must transition to
    DISARMED first (the two-press invariant).

The real ``Controller_MainWindow`` is constructed via ``make_controller``
(see ``test/_helpers/controller_fixture.py``), mirroring
``lightsheet/__main__.main()``'s composition root.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

from pytest import FixtureRequest

if TYPE_CHECKING:
    from lightsheet.gui.shell.controller import Controller_MainWindow

def _patch_refresh(ctrl: Controller_MainWindow, request: FixtureRequest) -> None:
    """Patch the three post-kill refresh calls so the E-stop handler does
    not spawn a QThread (L2 readback) or otherwise interfere with the
    state-machine observation. The deferred QTimer.singleShot calls land
    on the patched no-ops."""
    patchers = [
        patch.object(ctrl._hw, "_poll_laser_status"),
        patch.object(ctrl._hw, "_refresh_laser_readback"),
        patch.object(ctrl._hw, "_refresh_laser2_readback_async"),
    ]
    for p in patchers:
        p.start()
        request.addfinalizer(p.stop)

def test_initial_state_is_armed(controller: Controller_MainWindow) -> None:
    """On construction the system is ARMED: label_estopStatus shows
    '● ARMED' with color #34C759, pushButton_armReset shows 'Arm/Reset'."""
    ctrl = controller
    assert ctrl.label_estopStatus.text() == "● ARMED"
    assert "#34C759" in ctrl.label_estopStatus.styleSheet()
    assert ctrl.pushButton_armReset.text() == "Arm/Reset"

def test_estop_actuated_state(
    controller: Controller_MainWindow,
    request: FixtureRequest,
) -> None:
    """After E-stop (ACTUATED): label_estopStatus shows '● E-STOP ACTUATED'
    with color #FF3B30, pushButton_armReset shows 'Clear E-stop'."""
    ctrl = controller
    _patch_refresh(ctrl, request)

    ctrl.updateUi_estop_pressed()

    assert ctrl.label_estopStatus.text() == "⬤ E-STOP ACTUATED"
    assert "#FF3B30" in ctrl.label_estopStatus.styleSheet()
    assert ctrl.pushButton_armReset.text() == "Clear E-stop", (
        f"Expected 'Clear E-stop' (ACTUATED state), got "
        f"{ctrl.pushButton_armReset.text()!r}"
    )

def test_first_arm_reset_press_transitions_to_disarmed(
    controller: Controller_MainWindow,
    request: FixtureRequest,
) -> None:
    """After the first Arm/Reset press (ACTUATED -> DISARMED):
    label_estopStatus shows '● DISARMED' with color #8E8E93,
    pushButton_armReset shows 'Arm Lasers'. The E-stop button itself
    stays safety-red (#FF3B30) — only the status label goes gray
    (UI-SPEC §Safety-Critical Invariant)."""
    ctrl = controller
    _patch_refresh(ctrl, request)

    ctrl.updateUi_estop_pressed()
    ctrl.updateUi_arm_reset_pressed()

    assert ctrl.label_estopStatus.text() == "○ DISARMED"
    assert "#8E8E93" in ctrl.label_estopStatus.styleSheet()
    assert ctrl.pushButton_armReset.text() == "Arm Lasers", (
        f"Expected 'Arm Lasers' (DISARMED state), got "
        f"{ctrl.pushButton_armReset.text()!r}"
    )
    # The cooperative-abort Event is cleared on the first press.
    assert not ctrl.estop_event.is_set()
    # B1 safety: the E-stop button stays red in DISARMED state — the
    # gray (#8E8E93) belongs to the status label only, NOT the button.
    assert "#FF3B30" in ctrl.pushButton_estop.styleSheet(), (
        "E-stop button must stay #FF3B30 red in DISARMED state "
        "(UI-SPEC §Safety-Critical Invariant — a gray E-stop is harder "
        "to spot in an emergency)"
    )
    assert "#8E8E93" not in ctrl.pushButton_estop.styleSheet(), (
        "E-stop button must NOT be gray (#8E8E93) in DISARMED state — "
        "the gray belongs on label_estopStatus only"
    )

def test_disarmed_button_stays_red(
    controller: Controller_MainWindow,
    request: FixtureRequest,
) -> None:
    """B1 safety gate: after ACTUATED -> DISARMED, the E-stop button
    background is #FF3B30 (red), NOT #8E8E93 (gray). The gray indicator
    stays on label_estopStatus only."""
    ctrl = controller
    _patch_refresh(ctrl, request)

    ctrl.updateUi_estop_pressed()
    ctrl.updateUi_arm_reset_pressed()  # ACTUATED -> DISARMED

    assert "#FF3B30" in ctrl.pushButton_estop.styleSheet()
    assert "#8E8E93" not in ctrl.pushButton_estop.styleSheet()
    # The label keeps the gray indicator.
    assert "#8E8E93" in ctrl.label_estopStatus.styleSheet()

def test_second_arm_reset_press_transitions_to_armed(
    controller: Controller_MainWindow,
    request: FixtureRequest,
) -> None:
    """After the second Arm/Reset press (DISARMED -> ARMED):
    label_estopStatus shows '● ARMED' with color #34C759,
    pushButton_armReset shows 'Arm/Reset'."""
    ctrl = controller
    _patch_refresh(ctrl, request)

    ctrl.updateUi_estop_pressed()
    ctrl.updateUi_arm_reset_pressed()  # ACTUATED -> DISARMED
    ctrl.updateUi_arm_reset_pressed()  # DISARMED -> ARMED

    assert ctrl.label_estopStatus.text() == "● ARMED"
    assert "#34C759" in ctrl.label_estopStatus.styleSheet()
    assert ctrl.pushButton_armReset.text() == "Arm/Reset"

def test_single_press_from_actuated_does_not_re_arm(
    controller: Controller_MainWindow,
    request: FixtureRequest,
) -> None:
    """A single press from ACTUATED must NOT re-arm to ARMED — it must
    transition to DISARMED first (the two-press invariant, AGENTS.md §2).
    After one press from ACTUATED, the state is DISARMED (not ARMED) and
    the cooperative-abort Event is cleared but the system is not armed."""
    ctrl = controller
    _patch_refresh(ctrl, request)

    ctrl.updateUi_estop_pressed()
    assert ctrl.label_estopStatus.text() == "⬤ E-STOP ACTUATED"

    # A single press from ACTUATED -> DISARMED (NOT -> ARMED).
    ctrl.updateUi_arm_reset_pressed()
    assert ctrl.label_estopStatus.text() == "○ DISARMED", (
        "A single press from ACTUATED must transition to DISARMED, not "
        "re-arm to ARMED — no single-press re-arm of a Class IIIB laser "
        "(AGENTS.md §2)."
    )
    assert ctrl.pushButton_armReset.text() == "Arm Lasers"
    # The Event is cleared (DISARMED), but the system is not ARMED — a
    # second press is required to re-arm.
    assert not ctrl.estop_event.is_set()

def test_arm_reset_button_has_two_press_tooltip(
    controller: Controller_MainWindow,
) -> None:
    """pushButton_armReset has a tooltip documenting the two-press
    sequence (audit #6)."""
    ctrl = controller
    tooltip = ctrl.pushButton_armReset.toolTip()
    assert "Two-press sequence" in tooltip, (
        f"Expected tooltip to document the two-press sequence, got: {tooltip!r}"
    )

def test_status_bar_hint_on_each_transition(
    controller: Controller_MainWindow,
    request: FixtureRequest,
) -> None:
    """Each Arm/Reset transition emits a one-line status-bar hint so the
    operator knows what just happened and what to do next.

    First press (ACTUATED -> DISARMED): hint mentions clearing the E-stop
    and pressing Arm Lasers to re-arm.
    Second press (DISARMED -> ARMED): hint mentions the system is armed
    and lasers stay off until toggled or a run starts.
    """
    ctrl = controller
    _patch_refresh(ctrl, request)

    # Capture sig_message emissions (the status-bar hint channel).
    messages: list[str] = []
    ctrl.sig_message.connect(messages.append)

    ctrl.updateUi_estop_pressed()
    # Clear the E-stop actuated message so we only observe the Arm/Reset
    # hints.
    messages.clear()

    ctrl.updateUi_arm_reset_pressed()  # ACTUATED -> DISARMED
    disarm_messages = list(messages)
    assert any(
        "Arm Lasers" in m or "re-arm" in m.lower() or "cleared" in m.lower()
        for m in disarm_messages
    ), f"Expected a status-bar hint after the first press, got: {disarm_messages}"

    messages.clear()
    ctrl.updateUi_arm_reset_pressed()  # DISARMED -> ARMED
    arm_messages = list(messages)
    assert any("armed" in m.lower() for m in arm_messages), (
        f"Expected a status-bar hint after the second press, got: {arm_messages}"
    )
