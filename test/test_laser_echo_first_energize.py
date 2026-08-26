"""
Laser toggle checkable + optimistic state echo + first-energize confirmation
dialog (audit #15).

The laser toggle buttons used to be plain QPushButtons with no on/off state
echo — the status label only updated on the next poll, so a press could show
"ON" while the laser was actually still off (the "shows on, is off" Class
IIIB hazard window). There was also no first-energize confirmation for a
Class IIIB laser.

This test verifies:
- The toggle buttons are checkable.
- Pressing the toggle immediately sets the status label optimistically
  (ON green / OFF gray) BEFORE the toggle thread starts.
- The next poll corrects the label + button checked state if the HAL state
  differs (no permanent stale state).
- A first-energize QMessageBox appears the first time a laser is energized
  in a session, with the UI-SPEC copy (heading / wavelength + max_power +
  eye-protection body / Energize / Cancel / Don't warn again buttons).
- Cancel reverts the button checked state + label + does NOT energize.
- "Don't warn again this session" sets the per-session flag and skips the
  dialog on subsequent energizes.
- Energize proceeds to spawn the toggle thread.
- The E-stop kill path stays synchronous + lock-free (unchanged).
- The toggle threads stay threading.Thread (no QThread migration).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from _helpers.controller_fixture import make_controller

_LASER_PANEL_PATH = Path(__file__).resolve().parents[1] / "lightsheet" / "gui" / "panels" / "laser_panel.py"


# --------------------------------------------------------------------------- #
# Checkable toggle buttons.
# --------------------------------------------------------------------------- #


def test_laser1_toggle_is_checkable(qtbot, request) -> None:
    ctrl, _ = make_controller(qtbot, request)
    assert ctrl.laser_panel.ui.pushButton_laserOneToggle.isCheckable() is True


def test_laser2_toggle_is_checkable(qtbot, request) -> None:
    ctrl, _ = make_controller(qtbot, request)
    assert ctrl.laser_panel.ui.pushButton_laserTwoToggle.isCheckable() is True


# --------------------------------------------------------------------------- #
# Optimistic echo on press (BEFORE the toggle thread runs).
# --------------------------------------------------------------------------- #


def test_optimistic_echo_on_when_turning_on(qtbot, request) -> None:
    """Pressing the L1 toggle when OFF immediately sets the status label to
    '● ON' green BEFORE the toggle thread starts. We patch the thread spawn
    so the HAL never runs — the optimistic echo is purely GUI-thread."""
    ctrl, _ = make_controller(qtbot, request)
    btn = ctrl.laser_panel.ui.pushButton_laserOneToggle
    label = ctrl.laser_panel.ui.label_laserOneStatus
    assert not btn.isChecked()
    assert label.text() == "\u25cf OFF"

    spawned = {"did": False}
    real_thread = __import__("lightsheet.gui.panels.laser_panel", fromlist=["threading"]).threading

    def _fake_thread(*args, **kwargs):
        spawned["did"] = True
        class _T:
            def start(self):
                pass
        return _T()

    with patch.object(real_thread, "Thread", _fake_thread):
        btn.click()

    # Optimistic echo fired on the GUI thread before the thread spawn.
    assert label.text() == "\u25cf ON"
    assert "#34C759" in label.styleSheet()
    assert btn.isChecked() is True
    assert spawned["did"] is True


def test_optimistic_echo_off_when_turning_off(qtbot, request) -> None:
    """Pressing the L1 toggle when ON immediately sets the status label to
    '● OFF' gray."""
    ctrl, _ = make_controller(qtbot, request)
    btn = ctrl.laser_panel.ui.pushButton_laserOneToggle
    label = ctrl.laser_panel.ui.label_laserOneStatus
    # Pretend the laser is already on.
    btn.setChecked(True)
    ctrl._hw.lasers[0].active = True
    label.setText("\u25cf ON")
    label.setStyleSheet("color: #34C759; font-weight: bold;")

    real_thread = __import__("lightsheet.gui.panels.laser_panel", fromlist=["threading"]).threading

    def _fake_thread(*args, **kwargs):
        class _T:
            def start(self):
                pass
        return _T()

    with patch.object(real_thread, "Thread", _fake_thread):
        btn.click()

    assert label.text() == "\u25cf OFF"
    assert "#8E8E93" in label.styleSheet()
    assert btn.isChecked() is False


# --------------------------------------------------------------------------- #
# Poll correction: updateUi_laser_status also sets the button checked state.
# --------------------------------------------------------------------------- #


def test_poll_corrects_button_checked_state_active(qtbot, request) -> None:
    ctrl, _ = make_controller(qtbot, request)
    btn = ctrl.laser_panel.ui.pushButton_laserOneToggle
    assert not btn.isChecked()
    ctrl.laser_panel.updateUi_laser_status(0, "active")
    assert btn.isChecked() is True


def test_poll_corrects_button_checked_state_inactive(qtbot, request) -> None:
    ctrl, _ = make_controller(qtbot, request)
    btn = ctrl.laser_panel.ui.pushButton_laserOneToggle
    btn.setChecked(True)
    ctrl.laser_panel.updateUi_laser_status(0, "inactive")
    assert btn.isChecked() is False


# --------------------------------------------------------------------------- #
# First-energize confirmation dialog.
# --------------------------------------------------------------------------- #


def _patch_question(return_value):
    """Patch QMessageBox.question (the modal helper used by the dialog gate)
    to return the supplied value without showing a popup."""
    return patch(
        "lightsheet.gui.panels.laser_panel.QMessageBox.question",
        return_value=return_value,
    )


def test_first_energize_dialog_appears_first_time(qtbot, request) -> None:
    """The first time a laser is energized in a session, a QMessageBox appears
    with the UI-SPEC copy. We capture the heading/body via the patched
    question() call args."""
    ctrl, _ = make_controller(qtbot, request)
    btn = ctrl.laser_panel.ui.pushButton_laserOneToggle
    ctrl._laser1_first_energize_done = False

    captured = {"text": None}

    from PySide6.QtWidgets import QMessageBox

    def _capture(parent, title, text, *args, **kwargs):
        captured["text"] = (title, text)
        return QMessageBox.StandardButton.Yes  # Energize

    real_thread = __import__("lightsheet.gui.panels.laser_panel", fromlist=["threading"]).threading

    def _fake_thread(*a, **k):
        class _T:
            def start(self):
                pass
        return _T()

    with patch("lightsheet.gui.panels.laser_panel.QMessageBox.question", _capture), \
         patch.object(real_thread, "Thread", _fake_thread):
        btn.click()

    title, text = captured["text"]
    assert title is not None, "first-energize dialog must appear on first energize"
    # Heading: "Energize {label}?"
    assert "Energize" in title
    # Body: wavelength + max_power + eye-protection warning.
    assert "555" in text  # wavelength nm
    assert "300" in text  # max_power mW
    assert "eye protection" in text.lower() or "Class IIIB" in text


def test_first_energize_cancel_reverts_button_and_does_not_energize(qtbot, request) -> None:
    """If the operator clicks Cancel on the first-energize dialog, the laser
    is NOT energized (the toggle thread does not start), the button checked
    state reverts to unchecked, and the label reverts to '● OFF'."""
    ctrl, _ = make_controller(qtbot, request)
    btn = ctrl.laser_panel.ui.pushButton_laserOneToggle
    label = ctrl.laser_panel.ui.label_laserOneStatus
    ctrl._laser1_first_energize_done = False

    spawned = {"did": False}
    real_thread = __import__("lightsheet.gui.panels.laser_panel", fromlist=["threading"]).threading

    def _fake_thread(*a, **k):
        spawned["did"] = True
        class _T:
            def start(self):
                pass
        return _T()

    from PySide6.QtWidgets import QMessageBox

    with patch("lightsheet.gui.panels.laser_panel.QMessageBox.question",
               return_value=QMessageBox.StandardButton.Cancel), \
         patch.object(real_thread, "Thread", _fake_thread):
        btn.click()

    assert spawned["did"] is False, "Cancel must NOT spawn the toggle thread"
    assert btn.isChecked() is False, "Cancel must revert the button checked state"
    assert label.text() == "\u25cf OFF", "Cancel must revert the label to OFF"
    # The per-session flag must NOT be set on Cancel (next energize still warns).
    assert ctrl._laser1_first_energize_done is False


def test_first_energize_dont_warn_again_sets_flag(qtbot, request) -> None:
    """If the operator clicks 'Don't warn again this session', the per-session
    flag is set and subsequent energizes skip the dialog."""
    ctrl, _ = make_controller(qtbot, request)
    btn = ctrl.laser_panel.ui.pushButton_laserOneToggle
    ctrl._laser1_first_energize_done = False

    call_count = {"n": 0}
    real_thread = __import__("lightsheet.gui.panels.laser_panel", fromlist=["threading"]).threading

    def _fake_thread(*a, **k):
        class _T:
            def start(self):
                pass
        return _T()

    from PySide6.QtWidgets import QMessageBox

    # The "Don't warn again this session" button maps to Discard in the
    # implementation; patching question() to return Discard simulates the
    # operator clicking that button.
    def _question(parent, title, text, *args, **kwargs):
        call_count["n"] += 1
        return QMessageBox.StandardButton.Discard

    with patch("lightsheet.gui.panels.laser_panel.QMessageBox.question", _question), \
         patch.object(real_thread, "Thread", _fake_thread):
        btn.click()  # first energize — dialog shown, "don't warn again"
        # Reset the button to unchecked so the second click is again a
        # "turning on" — the flag must skip the dialog on this second
        # energize in the same session.
        btn.setChecked(False)
        btn.click()  # second energize — dialog must NOT appear

    assert call_count["n"] == 1, "second energize must skip the dialog"
    assert ctrl._laser1_first_energize_done is True


def test_first_energize_energize_proceeds(qtbot, request) -> None:
    """If the operator clicks Energize, the toggle thread starts and the
    optimistic echo stays."""
    ctrl, _ = make_controller(qtbot, request)
    btn = ctrl.laser_panel.ui.pushButton_laserOneToggle
    label = ctrl.laser_panel.ui.label_laserOneStatus
    ctrl._laser1_first_energize_done = False

    spawned = {"did": False}
    real_thread = __import__("lightsheet.gui.panels.laser_panel", fromlist=["threading"]).threading

    def _fake_thread(*a, **k):
        spawned["did"] = True
        class _T:
            def start(self):
                pass
        return _T()

    from PySide6.QtWidgets import QMessageBox

    with patch("lightsheet.gui.panels.laser_panel.QMessageBox.question",
               return_value=QMessageBox.StandardButton.Yes), \
         patch.object(real_thread, "Thread", _fake_thread):
        btn.click()

    assert spawned["did"] is True, "Energize must spawn the toggle thread"
    assert btn.isChecked() is True
    assert label.text() == "\u25cf ON"
    assert ctrl._laser1_first_energize_done is True


def test_per_session_flags_initialized_false(qtbot, request) -> None:
    ctrl, _ = make_controller(qtbot, request)
    assert ctrl._laser1_first_energize_done is False
    assert ctrl._laser2_first_energize_done is False


# --------------------------------------------------------------------------- #
# E-stop kill path + threading model preserved.
# --------------------------------------------------------------------------- #


def test_no_qthread_in_laser_panel() -> None:
    """The 4 laser toggle/power daemon threads stay threading.Thread — no
    QThread migration. The prohibition is on USING QThread (import or
    instantiation), not on the word appearing in the docstring that
    documents the prohibition."""
    src = _LASER_PANEL_PATH.read_text(encoding="utf-8")
    # Strip comments + docstrings by checking only executable lines: no
    # QThread import and no QThread(...) instantiation.
    import_lines = [
        line for line in src.splitlines()
        if line.strip().startswith(("import ", "from ")) and "QThread" in line
    ]
    instantiations = [
        line for line in src.splitlines()
        if "QThread(" in line and not line.strip().startswith("#")
    ]
    assert not import_lines, f"laser_panel.py must not import QThread: {import_lines}"
    assert not instantiations, (
        f"laser_panel.py must not instantiate QThread: {instantiations}"
    )


def test_estop_kill_path_unchanged(qtbot, request) -> None:
    """The E-stop kill path stays synchronous + lock-free in the shell:
    estop_event.set() + for laser in self.lasers: laser.off()."""
    ctrl, _ = make_controller(qtbot, request)
    ctrl._hw.lasers[0].active = True
    ctrl._hw.lasers[1].active = True
    ctrl.updateUi_estop_pressed()
    assert ctrl.estop_event.is_set()
    assert ctrl._hw.lasers[0].active is False
    assert ctrl._hw.lasers[1].active is False
