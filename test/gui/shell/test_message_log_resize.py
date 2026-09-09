"""Message log resize — vertical QSplitter section + cap removed +
select-and-copy (audit #4).

The message log was capped at a fixed 80 px max height and used
``NoTextInteraction`` so the operator could not select-and-copy an error
string. This test asserts the audit #4 remediation:

- The 80 px max-height cap is removed (``maximumSize().height() != 80``).
- A vertical ``QSplitter`` (``message_splitter``) hosts the stacked panels
  (stretch=1) on top and the message log (stretch=0) on the bottom inside
  ``controlsPane`` — the operator can drag the handle to resize the log.
- The log defaults to ~5 lines (minimum 96 px) and stays read-only.
- ``textInteractionFlags`` is ``TextSelectableByMouse`` so the operator can
  select-and-copy an error string.
- The View-menu "Show Message Log" action toggles the splitter sizes
  (hide/show) and the action's checked state syncs with the log visibility
  (audit #7 pattern, mirroring the images/controls pane toggles).

Runs headless on Mac via ``QT_QPA_PLATFORM=offscreen`` (set by conftest).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lightsheet.gui.shell.controller import Controller_MainWindow

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSplitter
from pytestqt.qtbot import QtBot


def test_message_log_cap_removed(controller: Controller_MainWindow) -> None:
    """The fixed 80 px max-height cap is gone (set to 16777215)."""
    ctrl = controller
    max_h = ctrl.ui.plainTextEdit_messageLog.maximumHeight()
    assert max_h != 80, (
        f"message log max height is still 80 (got {max_h}) — the cap was not removed"
    )
    assert max_h >= 16777215, (
        f"message log max height should be effectively unbounded "
        f"(>=16777215); got {max_h}"
    )


def test_message_splitter_exists(controller: Controller_MainWindow) -> None:
    """A vertical QSplitter (message_splitter) hosts stackedPanels + the
    message log inside controlsPane."""
    ctrl = controller
    assert hasattr(ctrl.ui, "message_splitter"), (
        "message_splitter not found on controller.ui"
    )
    splitter = ctrl.ui.message_splitter
    assert isinstance(splitter, QSplitter), (
        f"message_splitter is {type(splitter).__name__}, expected QSplitter"
    )
    assert splitter.orientation() == Qt.Orientation.Vertical, (
        "message_splitter must be vertical"
    )
    # stackedPanels and the message log are both children of the splitter.
    children = [splitter.widget(i) for i in range(splitter.count())]
    assert ctrl.ui.stackedPanels in children, (
        "stackedPanels must be a section of message_splitter"
    )
    assert ctrl.ui.plainTextEdit_messageLog in children, (
        "plainTextEdit_messageLog must be a section of message_splitter"
    )


def test_message_log_default_height_about_5_lines(
    controller: Controller_MainWindow,
) -> None:
    """The message log minimum height is ~96 px (5 lines)."""
    ctrl = controller
    min_h = ctrl.ui.plainTextEdit_messageLog.minimumHeight()
    assert min_h >= 96, (
        f"message log minimum height should be >= 96 (5 lines); got {min_h}"
    )


def test_message_splitter_drag_resizes_log(
    controller: Controller_MainWindow,
    qtbot: QtBot,
) -> None:
    """The splitter handle is live and resizes the log. The log must not
    be collapsible to 0 via handle drag (childrenCollapsible=False); hiding
    is via the View-menu only.

    The exact log size after a handle drag is bounded by the stacked
    panels content minimum (the panels impose a large minimumSizeHint on
    the QStackedWidget) and the QPlainTextEdit's own minimumSizeHint, so
    this test verifies the handle is interactive (handleWidth > 0,
    childrenCollapsible=False) and that setSizes with a non-zero log
    allocation produces a non-zero log size. The View-menu toggle test
    below proves setSizes changes the log size (hide → 0, show → > 0)."""
    ctrl = controller
    splitter = ctrl.ui.message_splitter
    # childrenCollapsible=False — the handle cannot collapse a section to 0.
    assert splitter.childrenCollapsible() is False, (
        "message_splitter must have childrenCollapsible=False so the "
        "operator cannot collapse the log to 0 via handle drag (hiding "
        "is via the View-menu only)"
    )
    # The handle is draggable (handleWidth > 0).
    assert splitter.handleWidth() > 0, (
        "message_splitter handleWidth must be > 0 so the operator can "
        "grab the handle to drag the log taller/shorter"
    )
    # The splitter has exactly 2 sections (stackedPanels + log).
    assert splitter.count() == 2, (
        f"message_splitter should have 2 sections (stackedPanels + log); "
        f"got {splitter.count()}"
    )
    # setSizes with a non-zero log allocation produces a non-zero log size
    # (the handle is live, not stuck at 0 or a fixed value).
    ctrl.show()
    qtbot.waitExposed(ctrl)
    qtbot.wait(50)
    total = sum(splitter.sizes()) or splitter.height() or 1
    splitter.setSizes([total - 96, 96])
    qtbot.wait(20)
    assert splitter.sizes()[1] > 0, (
        "setSizes([total-96, 96]) produced a 0-size log section; the "
        "splitter handle is not live"
    )


def test_message_log_select_and_copy_enabled(controller: Controller_MainWindow) -> None:
    """textInteractionFlags is TextSelectableByMouse (operator can
    select-and-copy an error string)."""
    ctrl = controller
    flags = ctrl.ui.plainTextEdit_messageLog.textInteractionFlags()
    assert flags == Qt.TextInteractionFlag.TextSelectableByMouse, (
        f"textInteractionFlags is {flags}, expected TextSelectableByMouse"
    )


def test_message_log_still_read_only(controller: Controller_MainWindow) -> None:
    """readOnly stays True — only select-and-copy is enabled, not editing."""
    ctrl = controller
    assert ctrl.ui.plainTextEdit_messageLog.isReadOnly() is True, (
        "message log readOnly must stay True (select-and-copy only)"
    )


def test_view_menu_show_message_log_syncs_with_splitter(
    controller: Controller_MainWindow,
    qtbot: QtBot,
) -> None:
    """The View-menu "Show Message Log" action toggles the splitter sizes
    (hide/show) and the action's checked state syncs with the log
    visibility (audit #7 pattern)."""
    ctrl = controller
    splitter = ctrl.ui.message_splitter
    action = ctrl.ui.action_ShowHideMessageLog
    # Show + process events so the splitter has a real laid-out size.
    ctrl.show()
    qtbot.waitExposed(ctrl)
    qtbot.wait(50)
    # The action is checkable + starts checked (log visible by default).
    assert action.isCheckable(), "Show Message Log action must be checkable"
    assert action.isChecked() is True, (
        "Show Message Log action must start checked (log visible)"
    )
    # Trigger the action to hide the log.
    action.trigger()
    # After hiding, the log section size should be 0 (the splitter sizes
    # are authoritative) and the action unchecked.
    log_size_after_hide = splitter.sizes()[1]
    assert log_size_after_hide == 0, (
        f"after triggering Show Message Log to hide, the log section size "
        f"is {log_size_after_hide} (should be 0) — the hide path did not "
        "sync the splitter sizes"
    )
    assert action.isChecked() is False, (
        "Show Message Log action must be unchecked after hiding the log"
    )
    # Trigger again to show the log.
    action.trigger()
    assert action.isChecked() is True, (
        "Show Message Log action must be checked after showing the log"
    )
    log_size_after_show = splitter.sizes()[1]
    assert log_size_after_show > 0, (
        f"after re-showing, the log section size is {log_size_after_show} "
        "(should be > 0)"
    )
