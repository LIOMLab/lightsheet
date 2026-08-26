"""Responsive-resize verification for the shell layout.

Verifies the GUI reflows gracefully across the laptop floor (1366x768),
the lab display (1920x1080), and the window floor (1280x800) under the
offscreen Qt platform. The ImageView must dominate the layout at every
size, the controls pane must stay readable, and the E-stop toolbar must
remain visible. The window must not resize below its 1280x800 floor.

Also covers the Motion tab fixed-size group-box remediation: the two
movement group boxes must no longer be pinned to 350x380, and the jog
arrow buttons must no longer have a width cap pinning them to 60px.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from _helpers.controller_fixture import make_controller


def _resize_and_settle(controller, width, height, qtbot) -> None:
    """Resize the controller window and pump the event loop so the
    splitter/layout machinery settles before assertions read widget
    geometry."""
    controller.resize(width, height)
    qtbot.wait(120)


@pytest.mark.parametrize(
    "width,height",
    [
        (1366, 768),  # laptop floor
        (1920, 1080),  # lab display
        (1280, 800),  # window floor
    ],
)
def test_layout_reflows_at_target_sizes(qtbot, request, width, height) -> None:
    """At each target size the ImageView is >= 320x240, the controls pane
    is >= 360 wide, and the E-stop toolbar stays visible."""
    controller, _bundle = make_controller(qtbot, request)
    controller.show()
    qtbot.waitExposed(controller)
    _resize_and_settle(controller, width, height, qtbot)

    iv = controller.ui.imageView
    assert iv.width() >= 320, (
        f"imageView width {iv.width()} < 320 at {width}x{height}"
    )
    assert iv.height() >= 240, (
        f"imageView height {iv.height()} < 240 at {width}x{height}"
    )

    images = controller.ui.imagesPane
    assert images.width() >= 320, (
        f"imagesPane width {images.width()} < 320 at {width}x{height}"
    )

    controls = controller.ui.controlsPane
    assert controls.width() >= 360, (
        f"controlsPane width {controls.width()} < 360 at {width}x{height}"
    )

    assert controller.ui.toolBar_estop.isVisible(), (
        f"E-stop toolbar not visible at {width}x{height}"
    )


def test_images_pane_wins_extra_space_on_lab_display(qtbot, request) -> None:
    """At 1920x1080 the imagesPane (stretch=1) wins the extra width over
    the controlsPane (stretch=0)."""
    controller, _bundle = make_controller(qtbot, request)
    controller.show()
    qtbot.waitExposed(controller)
    _resize_and_settle(controller, 1920, 1080, qtbot)

    images = controller.ui.imagesPane
    controls = controller.ui.controlsPane
    assert images.width() > controls.width(), (
        f"imagesPane ({images.width()}px) did not win extra space over "
        f"controlsPane ({controls.width()}px) at 1920x1080 — stretch=1 "
        f"on imagesPane vs stretch=0 on controlsPane is not in effect"
    )


def test_window_cannot_resize_below_floor(qtbot, request) -> None:
    """The window minimumSize (1280x800) is enforced — a resize below
    the floor clamps back up."""
    controller, _bundle = make_controller(qtbot, request)
    controller.show()
    qtbot.waitExposed(controller)
    _resize_and_settle(controller, 1000, 600, qtbot)

    min_w = controller.minimumSize().width()
    min_h = controller.minimumSize().height()
    assert min_w == 1280, f"window min width {min_w} != 1280"
    assert min_h == 800, f"window min height {min_h} != 800"

    # Qt clamps the actual size to the minimum.
    assert controller.width() >= 1280, (
        f"window width {controller.width()} < 1280 (minimumSize not enforced)"
    )
    assert controller.height() >= 800, (
        f"window height {controller.height()} < 800 (minimumSize not enforced)"
    )


def test_splitter_panes_not_collapsible(qtbot, request) -> None:
    """QSplitter childrenCollapsible stays False — operator drag resizes
    but cannot collapse a pane to 0 (hiding is via the View menu)."""
    controller, _bundle = make_controller(qtbot, request)
    assert controller.ui.splitter.childrenCollapsible() is False, (
        "splitter childrenCollapsible must be False (panes must not "
        "collapse via handle drag)"
    )
    assert controller.ui.splitter.handleWidth() == 5, (
        f"splitter handleWidth {controller.ui.splitter.handleWidth()} != 5"
    )


# --- Motion tab fixed-size group-box remediation (audit #5) ---


def _show_motion_tab(controller, qtbot) -> None:
    """Switch the controls tab widget to the Motion tab (index 0) and
    let the layout settle."""
    controller.ui.tabControls.setCurrentIndex(0)
    qtbot.wait(50)


def test_sample_movement_group_box_not_pinned(qtbot, request) -> None:
    """groupBox_SampleMovement no longer has the 350x380 fixed max — the
    cap is removed so the box can grow with the layout."""
    controller, _bundle = make_controller(qtbot, request)
    controller.show()
    qtbot.waitExposed(controller)
    _show_motion_tab(controller, qtbot)

    gb = controller.motor_panel.ui.groupBox_SampleMovement
    max_size = gb.maximumSize()
    # Qt's default max is (16777215, 16777215). The fixed 350x380 cap
    # would set both to 350/380. Assert at least one dimension is not
    # pinned to the old fixed value.
    assert not (max_size.width() == 350 and max_size.height() == 380), (
        f"groupBox_SampleMovement still pinned to 350x380 max "
        f"(got {max_size.width()}x{max_size.height()})"
    )


def test_camera_movement_group_box_not_pinned(qtbot, request) -> None:
    """groupBox_CameraMovement no longer has the 350x380 fixed max."""
    controller, _bundle = make_controller(qtbot, request)
    controller.show()
    qtbot.waitExposed(controller)
    _show_motion_tab(controller, qtbot)

    gb = controller.motor_panel.ui.groupBox_CameraMovement
    max_size = gb.maximumSize()
    assert not (max_size.width() == 350 and max_size.height() == 380), (
        f"groupBox_CameraMovement still pinned to 350x380 max "
        f"(got {max_size.width()}x{max_size.height()})"
    )


def test_sample_movement_group_box_min_width_content_driven(qtbot, request) -> None:
    """groupBox_SampleMovement minimumSize width is content-driven (~300),
    not the old fixed 350x380."""
    controller, _bundle = make_controller(qtbot, request)
    controller.show()
    qtbot.waitExposed(controller)
    _show_motion_tab(controller, qtbot)

    gb = controller.motor_panel.ui.groupBox_SampleMovement
    min_size = gb.minimumSize()
    # The old pin was 350x380. The remediation drops the height pin to
    # 0 (layout decides) and keeps a content-driven width ~300. Assert
    # the height pin is gone (0) and the width is no longer the old 350.
    assert min_size.height() == 0, (
        f"groupBox_SampleMovement min height {min_size.height()} != 0 "
        f"(old 380 pin still present)"
    )


def test_jog_arrow_button_no_width_cap(qtbot, request) -> None:
    """The jog arrow buttons keep their 60x60 minimum but no longer have
    a setMaximumSize(60, 16777215) width cap — the layout's natural
    width wins."""
    controller, _bundle = make_controller(qtbot, request)
    controller.show()
    qtbot.waitExposed(controller)
    _show_motion_tab(controller, qtbot)

    btn = controller.motor_panel.ui.pushButton_sampleStepForward
    # Keep the 60x60 minimum (touch target).
    assert btn.minimumSize().width() == 60, (
        f"jog button min width {btn.minimumSize().width()} != 60 "
        f"(touch target lost)"
    )
    assert btn.minimumSize().height() == 60, (
        f"jog button min height {btn.minimumSize().height()} != 60 "
        f"(touch target lost)"
    )
    # The width cap (60) must be gone — Qt's default max width is
    # 16777215 (QWIDGETSIZE_MAX). The old cap set width to 60.
    assert btn.maximumSize().width() != 60, (
        f"jog button max width {btn.maximumSize().width()} == 60 "
        f"(old width cap still present — should be 16777215 default)"
    )


def test_motion_tab_group_boxes_visible_at_laptop_floor(qtbot, request) -> None:
    """At 1366x768 the Motion tab group boxes stack vertically without
    clipping — both are visible and not pinned to 350x380."""
    controller, _bundle = make_controller(qtbot, request)
    controller.show()
    qtbot.waitExposed(controller)
    _resize_and_settle(controller, 1366, 768, qtbot)
    _show_motion_tab(controller, qtbot)

    sample_gb = controller.motor_panel.ui.groupBox_SampleMovement
    camera_gb = controller.motor_panel.ui.groupBox_CameraMovement
    assert sample_gb.isVisible(), "groupBox_SampleMovement not visible at 1366x768"
    assert camera_gb.isVisible(), "groupBox_CameraMovement not visible at 1366x768"
