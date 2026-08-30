"""Left-rail navigation regression test.

The shell uses a vertical left rail of 8 checkable QToolButtons in an
exclusive QButtonGroup driving a QStackedWidget (``stackedPanels``). This
module is the regression gate for the left-rail + QStackedWidget
navigation:

- ``stackedPanels`` has 8 pages (one per left-rail button).
- The 8 left-rail buttons exist and are checkable.
- ``ctrl._rail_group`` is an exclusive QButtonGroup with 8 buttons.
- Clicking each button sets ``stackedPanels.currentIndex`` to the
  corresponding index.
- The E-stop toolbar (``toolBar_estop``) stays visible across all panel
  switches and is not movable (fixed).
- The Phase 9 extension seam holds: a 9th page can be added to
  ``stackedPanels`` without re-architecture.

Runs headless on Mac via ``QT_QPA_PLATFORM=offscreen`` (set by conftest).
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QButtonGroup, QWidget

from _helpers.controller_fixture import make_controller

# The 8 left-rail button objectNames in left-rail order (index 0..7).
_RAIL_BUTTON_NAMES = (
    "toolButton_railMotion",
    "toolButton_railAcquire",
    "toolButton_railStack",
    "toolButton_railScan",
    "toolButton_railLasers",
    "toolButton_railFiles",
    "toolButton_railPast",
    "toolButton_railCalibrate",
)


def test_left_rail_buttons_exist_and_are_checkable(qtbot, request) -> None:
    """The 8 left-rail QToolButtons exist on ui and are checkable."""
    ctrl, _ = make_controller(qtbot, request)
    for name in _RAIL_BUTTON_NAMES:
        btn = getattr(ctrl.ui, name)
        assert btn is not None, f"{name} missing from controller.ui"
        assert btn.isCheckable(), f"{name} must be checkable"


def test_rail_group_is_exclusive_with_eight_buttons(qtbot, request) -> None:
    """ctrl._rail_group is an exclusive QButtonGroup with 8 buttons."""
    ctrl, _ = make_controller(qtbot, request)
    group = ctrl._rail_group
    assert isinstance(group, QButtonGroup)
    assert group.exclusive() is True, "left-rail QButtonGroup must be exclusive"
    assert len(group.buttons()) == 8, (
        f"left-rail QButtonGroup has {len(group.buttons())} buttons, expected 8"
    )


def test_rail_button_ids_match_page_indices(qtbot, request) -> None:
    """Each left-rail button's QButtonGroup id matches its page index
    (Motion=0, Acquire=1, ..., Calibrate=7)."""
    ctrl, _ = make_controller(qtbot, request)
    group = ctrl._rail_group
    for expected_id, name in enumerate(_RAIL_BUTTON_NAMES):
        btn = getattr(ctrl.ui, name)
        assert group.id(btn) == expected_id, (
            f"{name} has id {group.id(btn)}, expected {expected_id}"
        )


def test_clicking_each_rail_button_switches_stacked_page(qtbot, request) -> None:
    """Clicking each left-rail button sets stackedPanels.currentIndex to
    the corresponding index."""
    ctrl, _ = make_controller(qtbot, request)
    group = ctrl._rail_group
    for expected_id, name in enumerate(_RAIL_BUTTON_NAMES):
        btn = getattr(ctrl.ui, name)
        # Check the button (exclusive group unchecks the others) and emit
        # idClicked so the setCurrentIndex connection fires.
        btn.setChecked(True)
        group.idClicked.emit(expected_id)
        assert ctrl.ui.stackedPanels.currentIndex() == expected_id, (
            f"clicking {name} (id {expected_id}) set currentIndex to "
            f"{ctrl.ui.stackedPanels.currentIndex()}, expected {expected_id}"
        )


def test_motion_is_default_active_page(qtbot, request) -> None:
    """Motion (index 0) is the default active page after construction."""
    ctrl, _ = make_controller(qtbot, request)
    assert ctrl.ui.stackedPanels.currentIndex() == 0
    assert ctrl.ui.toolButton_railMotion.isChecked() is True


def test_estop_toolbar_visible_across_all_switches(qtbot, request) -> None:
    """The E-stop toolbar stays visible across all panel switches (it is
    in the TopToolBarArea, not inside any stacked page)."""
    ctrl, _ = make_controller(qtbot, request)
    group = ctrl._rail_group
    ctrl.show()
    qtbot.waitExposed(ctrl)
    qtbot.wait(30)
    for expected_id, name in enumerate(_RAIL_BUTTON_NAMES):
        btn = getattr(ctrl.ui, name)
        btn.setChecked(True)
        group.idClicked.emit(expected_id)
        qtbot.wait(10)
        assert ctrl.ui.toolBar_estop.isVisible(), (
            f"toolBar_estop not visible after switching to {name}"
        )


def test_estop_toolbar_is_not_movable(qtbot, request) -> None:
    """The E-stop toolbar is fixed (movable=False) — the safety-critical
    E-stop button must not be draggable off the TopToolBarArea."""
    ctrl, _ = make_controller(qtbot, request)
    assert ctrl.ui.toolBar_estop.isMovable() is False, (
        "toolBar_estop must be non-movable (movable=False) so the E-stop "
        "button stays in the TopToolBarArea (AGENTS.md §2)"
    )


def test_phase9_extension_seam_adds_ninth_page(qtbot, request) -> None:
    """The Phase 9 extension seam: a 9th page can be added to
    stackedPanels without re-architecture (addWidget appends)."""
    ctrl, _ = make_controller(qtbot, request)
    initial_count = ctrl.ui.stackedPanels.count()
    ninth = QWidget()
    ctrl.ui.stackedPanels.addWidget(ninth)
    assert ctrl.ui.stackedPanels.count() == initial_count + 1
    # Clean up the added page so it does not leak into other tests.
    ctrl.ui.stackedPanels.removeWidget(ninth)
    ninth.deleteLater()
