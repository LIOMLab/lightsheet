"""Mode/state badge — persistent mode + run-state indicator in the E-stop
toolbar (audit #12).

The operator had no persistent mode/state indicator mid-run and had to look
at the status bar to see the progress. This test asserts the audit #12
remediation:

- A QLabel (``label_modeBadge``) is in the E-stop toolbar, always visible
  on every tab.
- Initial state (idle) — badge text is "IDLE".
- When preview starts — badge text is "PREVIEW".
- When live starts — badge text is "LIVE".
- When single acquisition starts — badge text is "SINGLE".
- When stack starts — badge text is "STACK RUNNING — plane 1/{N}".
- During a stack run, sig_progress_update updates the badge to
  "STACK RUNNING — plane {n}/{N}" mirroring the progress bar value.
- When a run completes/aborts — badge text reverts to "IDLE".
- The badge uses QDarkStyle default text color + bold weight (no accent
  color — no #FF/#34/#8E stylesheet on the badge).

Runs headless on Mac via ``QT_QPA_PLATFORM=offscreen`` (set by conftest).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from pytest import FixtureRequest
from pytestqt.qtbot import QtBot

pytest.importorskip("PySide6")

from _helpers.controller_fixture import make_controller

if TYPE_CHECKING:
    from PySide6.QtWidgets import QLabel, QToolBar

    from lightsheet.gui.shell.controller import Controller_MainWindow
    from lightsheet.hal import DeviceBundle


def _make(
    qtbot: QtBot, request: FixtureRequest
) -> tuple[Controller_MainWindow, DeviceBundle]:
    return make_controller(qtbot, request)


def _badge_is_in_toolbar(badge: QLabel, toolbar: QToolBar) -> bool:
    """Return True if ``badge`` is a descendant of ``toolbar``."""
    parent = badge.parent()
    while parent is not None:
        if parent is toolbar:
            return True
        parent = parent.parent()
    return False


def test_mode_badge_exists_in_estop_toolbar(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """A QLabel objectName label_modeBadge exists in the E-stop toolbar."""
    ctrl, _ = _make(qtbot, request)
    assert hasattr(ctrl.ui, "label_modeBadge"), (
        "label_modeBadge not found on controller.ui"
    )
    badge = ctrl.ui.label_modeBadge
    toolbar = ctrl.ui.toolBar_estop
    assert _badge_is_in_toolbar(badge, toolbar), (
        "label_modeBadge must be in the E-stop toolbar (toolBar_estop) so "
        "it is always visible on every tab"
    )


def test_mode_badge_initial_idle(qtbot: QtBot, request: FixtureRequest) -> None:
    """Initial state (idle) — badge text is 'IDLE'."""
    ctrl, _ = _make(qtbot, request)
    assert ctrl.ui.label_modeBadge.text() == "IDLE", (
        f"initial badge text is {ctrl.ui.label_modeBadge.text()!r}, "
        "expected 'IDLE'"
    )


def test_mode_badge_preview(qtbot: QtBot, request: FixtureRequest) -> None:
    """When preview starts — badge text is 'PREVIEW'."""
    ctrl, _ = _make(qtbot, request)
    ctrl._update_mode_badge("PREVIEW")
    assert ctrl.ui.label_modeBadge.text() == "PREVIEW", (
        f"after preview start, badge text is "
        f"{ctrl.ui.label_modeBadge.text()!r}, expected 'PREVIEW'"
    )


def test_mode_badge_live(qtbot: QtBot, request: FixtureRequest) -> None:
    """When live starts — badge text is 'LIVE'."""
    ctrl, _ = _make(qtbot, request)
    ctrl._update_mode_badge("LIVE")
    assert ctrl.ui.label_modeBadge.text() == "LIVE", (
        f"after live start, badge text is "
        f"{ctrl.ui.label_modeBadge.text()!r}, expected 'LIVE'"
    )


def test_mode_badge_single(qtbot: QtBot, request: FixtureRequest) -> None:
    """When single acquisition starts — badge text is 'SINGLE'."""
    ctrl, _ = _make(qtbot, request)
    ctrl._update_mode_badge("SINGLE")
    assert ctrl.ui.label_modeBadge.text() == "SINGLE", (
        f"after single start, badge text is "
        f"{ctrl.ui.label_modeBadge.text()!r}, expected 'SINGLE'"
    )


def test_mode_badge_stack_running(qtbot: QtBot, request: FixtureRequest) -> None:
    """When stack starts — badge text is 'STACK RUNNING — plane 1/{N}'."""
    ctrl, _ = _make(qtbot, request)
    ctrl.number_of_planes = 240
    ctrl._update_mode_badge("STACK", "RUNNING", plane=1, total=240)
    expected = "STACK RUNNING \u2014 plane 1/240"
    assert ctrl.ui.label_modeBadge.text() == expected, (
        f"after stack start, badge text is "
        f"{ctrl.ui.label_modeBadge.text()!r}, expected {expected!r}"
    )


def test_mode_badge_progress_mirror(qtbot: QtBot, request: FixtureRequest) -> None:
    """During a stack run, sig_progress_update updates the badge to
    'STACK RUNNING — plane {n}/{N}' mirroring the progress bar value."""
    ctrl, _ = _make(qtbot, request)
    ctrl.number_of_planes = 240
    ctrl.stack_mode_started = True
    # Emit a progress update — the badge should mirror it.
    ctrl.sig_progress_update.emit(12)
    expected = "STACK RUNNING \u2014 plane 12/240"
    assert ctrl.ui.label_modeBadge.text() == expected, (
        f"after sig_progress_update(12), badge text is "
        f"{ctrl.ui.label_modeBadge.text()!r}, expected {expected!r}"
    )


def test_mode_badge_reverts_to_idle_on_complete(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """When a run completes/aborts — badge text reverts to 'IDLE'."""
    ctrl, _ = _make(qtbot, request)
    ctrl._update_mode_badge("STACK", "RUNNING", plane=1, total=240)
    assert ctrl.ui.label_modeBadge.text() != "IDLE"
    ctrl._update_mode_badge("IDLE")
    assert ctrl.ui.label_modeBadge.text() == "IDLE", (
        f"after run complete, badge text is "
        f"{ctrl.ui.label_modeBadge.text()!r}, expected 'IDLE'"
    )


def test_mode_badge_no_accent_color(qtbot: QtBot, request: FixtureRequest) -> None:
    """The badge uses QDarkStyle default text color + bold weight (no
    accent color — no #FF/#34/#8E in the badge stylesheet)."""
    ctrl, _ = _make(qtbot, request)
    ss = ctrl.ui.label_modeBadge.styleSheet() or ""
    # The badge may have a bold-weight stylesheet but must NOT contain
    # accent colors (#FF = red, #34 = green, #8E = gray).
    for accent in ("#FF", "#34", "#8E"):
        assert accent not in ss, (
            f"badge stylesheet contains accent color {accent!r}: {ss!r} "
            "— the badge must use QDarkStyle default text + bold weight only"
        )


def test_mode_badge_bold_weight(qtbot: QtBot, request: FixtureRequest) -> None:
    """The badge uses bold font weight (the QDarkStyle default text color
    with bold weight, matching the existing status-label pattern)."""
    ctrl, _ = _make(qtbot, request)
    ss = ctrl.ui.label_modeBadge.styleSheet() or ""
    assert "bold" in ss.lower(), (
        f"badge stylesheet should include 'font-weight: bold': {ss!r}"
    )
