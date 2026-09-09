"""View-menu / QSplitter sync — menu drives splitter.setSizes() (audit #7).

The View-menu "Show Images Pane" / "Show Controls Pane" actions and the
QSplitter drag are two mechanisms that can hide/show a pane. Offering
both leads to desync: the menu action's checked state drifts from the
splitter sizes when the operator drags the handle, and the menu's
show()/hide() calls fight the splitter's geometry.

The fix (audit #7): the View-menu actions call ``splitter.setSizes()``
instead of show()/hide() on the pane widget directly. ``childrenCollapsible``
stays ``False`` (handle-drag-to-zero is blocked; hiding is via the menu
only). The menu action's checked state stays in sync with the splitter
sizes (checked = pane width > 0).

The real ``Controller_MainWindow`` is constructed via the ``controller`` fixture
(see ``test/fixtures/controller.py``), mirroring
``lightsheet/__main__.main()``'s composition root.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pytestqt.qtbot import QtBot

if TYPE_CHECKING:
    from lightsheet.gui.shell.controller import Controller_MainWindow


def _show_window(ctrl: Controller_MainWindow, qtbot: QtBot) -> None:
    """Show the controller window and wait for it to be exposed so the
    splitter has real geometry (width > 0) for setSizes() to partition."""
    ctrl.show()
    qtbot.waitExposed(ctrl)


def test_splitter_children_not_collapsible(
    controller: Controller_MainWindow,
    qtbot: QtBot,
) -> None:
    """childrenCollapsible stays False on the splitter — handle-drag-to-
    zero is blocked; hiding a pane is via the View menu only (audit #7)."""
    ctrl = controller
    _show_window(ctrl, qtbot)
    assert ctrl.ui.splitter.childrenCollapsible() is False


def test_show_hide_images_pane_uses_splitter_set_sizes(
    controller: Controller_MainWindow,
    qtbot: QtBot,
) -> None:
    """Toggling 'Show Images Pane' off calls splitter.setSizes([0, total])
    so the imagesPane width is 0 (hidden via the splitter, not via
    hide()). Toggling it back on calls splitter.setSizes([>0, ...]) so the
    imagesPane is visible again. The menu action's checked state stays in
    sync with the pane visibility."""
    ctrl = controller
    _show_window(ctrl, qtbot)

    splitter = ctrl.ui.splitter
    images_pane = ctrl.ui.imagesPane
    action = ctrl.ui.action_ShowHideImagesPane

    # Sanity: the splitter has real geometry.
    total = splitter.width()
    assert total > 0, "Splitter must have non-zero width after show()"

    # Initial state: both panes visible, action checked.
    assert action.isChecked() is True
    assert images_pane.width() > 0

    # Toggle OFF via the slot (the menu action triggers it).
    ctrl.updateUi_show_hide_images_pane()
    # The imagesPane width is now 0 (hidden via splitter.setSizes, not
    # hide()). We cannot assert imagesPane.isVisible() directly because
    # Qt may still report the widget visible()=True when its parent
    # splitter gives it 0 width — the authoritative signal is the
    # splitter sizes + the action checked state.
    sizes_after_hide = splitter.sizes()
    assert sizes_after_hide[0] == 0, (
        f"Expected imagesPane splitter size 0 after hide, got {sizes_after_hide}"
    )
    # The action's checked state must reflect the pane visibility
    # (unchecked = pane hidden).
    assert action.isChecked() is False

    # Toggle ON via the slot.
    ctrl.updateUi_show_hide_images_pane()
    sizes_after_show = splitter.sizes()
    assert sizes_after_show[0] > 0, (
        f"Expected imagesPane splitter size > 0 after show, got {sizes_after_show}"
    )
    assert action.isChecked() is True


def test_show_hide_controls_pane_uses_splitter_set_sizes(
    controller: Controller_MainWindow,
    qtbot: QtBot,
) -> None:
    """Toggling 'Show Controls Pane' off calls splitter.setSizes([total, 0])
    so the controlsPane width is 0 (hidden via the splitter, not via
    hide()). Toggling it back on calls splitter.setSizes([..., >0]) so the
    controlsPane is visible again. The menu action's checked state stays
    in sync with the pane visibility."""
    ctrl = controller
    _show_window(ctrl, qtbot)

    splitter = ctrl.ui.splitter
    controls_pane = ctrl.ui.controlsPane
    action = ctrl.ui.action_ShowHideControlsPane

    total = splitter.width()
    assert total > 0

    # Initial state: both panes visible, action checked.
    assert action.isChecked() is True
    assert controls_pane.width() > 0

    # Toggle OFF via the slot.
    ctrl.updateUi_show_hide_controls_pane()
    sizes_after_hide = splitter.sizes()
    # controlsPane is the SECOND widget in the splitter (index 1).
    assert sizes_after_hide[1] == 0, (
        f"Expected controlsPane splitter size 0 after hide, got {sizes_after_hide}"
    )
    assert action.isChecked() is False

    # Toggle ON via the slot.
    ctrl.updateUi_show_hide_controls_pane()
    sizes_after_show = splitter.sizes()
    assert sizes_after_show[1] > 0, (
        f"Expected controlsPane splitter size > 0 after show, got {sizes_after_show}"
    )
    assert action.isChecked() is True


def test_show_hide_images_pane_does_not_call_widget_hide(
    controller: Controller_MainWindow,
    qtbot: QtBot,
) -> None:
    """The slot must NOT call imagesPane.hide()/show() directly — it must
    route through splitter.setSizes() so the splitter sizes stay
    authoritative (audit #7). Verified by spying on the pane widget's
    hide/show methods."""
    from unittest.mock import patch

    ctrl = controller
    _show_window(ctrl, qtbot)

    images_pane = ctrl.ui.imagesPane

    with (
        patch.object(images_pane, "hide") as spy_hide,
        patch.object(images_pane, "show") as spy_show,
    ):
        ctrl.updateUi_show_hide_images_pane()  # toggle off
        ctrl.updateUi_show_hide_images_pane()  # toggle on

    spy_hide.assert_not_called()
    spy_show.assert_not_called()


def test_show_hide_controls_pane_does_not_call_widget_hide(
    controller: Controller_MainWindow,
    qtbot: QtBot,
) -> None:
    """The slot must NOT call controlsPane.hide()/show() directly — it
    must route through splitter.setSizes() (audit #7)."""
    from unittest.mock import patch

    ctrl = controller
    _show_window(ctrl, qtbot)

    controls_pane = ctrl.ui.controlsPane

    with (
        patch.object(controls_pane, "hide") as spy_hide,
        patch.object(controls_pane, "show") as spy_show,
    ):
        ctrl.updateUi_show_hide_controls_pane()  # toggle off
        ctrl.updateUi_show_hide_controls_pane()  # toggle on

    spy_hide.assert_not_called()
    spy_show.assert_not_called()
