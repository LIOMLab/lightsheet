"""SC2 render smoke test for the native Qt6 ImageView.

Exit-criterion test for the native ImageView replacement: asserts that
``setImage`` produces non-zero pixel data on the underlying QPixmap, i.e.
the widget actually renders the frame rather than showing a blank image.
Runs headless on Mac via ``QT_QPA_PLATFORM=offscreen`` (set by conftest).
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("PySide6")


def test_image_view_render_nonzero(qtbot) -> None:
    """SC2: native ImageView renders non-zero pixel data after setImage."""
    from lightsheet.gui.panels.image_view import ImageView

    view = ImageView()
    qtbot.addWidget(view)

    # Create a 100x100 uint16 frame with a single seed pixel at 20000
    # (the maximum of the fixed 0-20000 levels window). After scaling to
    # uint8 [0, 255] this pixel must map to 255; every other pixel is 0.
    frame = np.zeros((100, 100), dtype=np.uint16)
    frame[50, 50] = 20000

    view.setImage(frame)

    # The scene must exist and contain at least one item.
    scene = view.scene()
    assert scene is not None, "ImageView has no scene after setImage"
    items = scene.items()
    assert len(items) > 0, "ImageView scene has no items after setImage"

    # The first item must be the QGraphicsPixmapItem holding the frame.
    from PySide6.QtWidgets import QGraphicsPixmapItem

    pixmap_item = items[0]
    assert isinstance(pixmap_item, QGraphicsPixmapItem), (
        f"Expected QGraphicsPixmapItem, got {type(pixmap_item).__name__}"
    )

    pixmap = pixmap_item.pixmap()
    assert not pixmap.isNull(), "Pixmap is null after setImage"

    # At least one pixel must be non-zero — the seed pixel at (50, 50)
    # must render as 255 after the levels scaling. Iterating pixels and
    # breaking on the first non-zero value keeps the test fast.
    qimage = pixmap.toImage()
    has_nonzero = False
    for y in range(qimage.height()):
        for x in range(qimage.width()):
            if qimage.pixelColor(x, y).value() > 0:
                has_nonzero = True
                break
        if has_nonzero:
            break
    assert has_nonzero, "ImageView rendered a blank image (all pixels zero)"


def test_scrollbar_policy_always_off(qtbot) -> None:
    """ImageView scrollbar policy is AlwaysOff on both axes — prevents
    resize→fitInView→scrollbar-toggle→resize recursion."""
    from PySide6.QtCore import Qt

    from lightsheet.gui.panels.image_view import ImageView

    view = ImageView()
    qtbot.addWidget(view)

    assert (
        view.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    ), "horizontalScrollBarPolicy must be ScrollBarAlwaysOff"
    assert (
        view.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    ), "verticalScrollBarPolicy must be ScrollBarAlwaysOff"


def test_scene_rect_at_construction(qtbot) -> None:
    """ImageView has a non-empty sceneRect at construction so fitInView
    has geometry before the first frame (no tiny black square)."""
    from lightsheet.gui.panels.image_view import ImageView

    view = ImageView()
    qtbot.addWidget(view)

    rect = view.sceneRect()
    assert rect.width() > 0, "sceneRect width must be > 0 at construction"
    assert rect.height() > 0, "sceneRect height must be > 0 at construction"


def test_min_size_floor(qtbot) -> None:
    """ImageView minimum size is 320x240 (dropped from 700x700) so it can
    actually shrink on small screens."""
    from lightsheet.gui.panels.image_view import ImageView

    view = ImageView()
    qtbot.addWidget(view)

    assert view.minimumSize().width() <= 320, (
        f"ImageView min width {view.minimumSize().width()} must be <= 320"
    )
    assert view.minimumSize().height() <= 240, (
        f"ImageView min height {view.minimumSize().height()} must be <= 240"
    )


def test_resize_refits_pixmap(qtbot) -> None:
    """resizeEvent re-calls fitInView so the pixmap fills the viewport
    on every resize (no tiny black square)."""
    import numpy as np

    from lightsheet.gui.panels.image_view import ImageView

    view = ImageView()
    view.resize(200, 200)
    qtbot.addWidget(view)
    view.show()
    qtbot.waitExposed(view)

    # 100x100 frame with a seed pixel at the levels max.
    frame = np.zeros((100, 100), dtype=np.uint16)
    frame[50, 50] = 20000
    view.setImage(frame)
    qtbot.wait(20)
    scale_before = view.transform().m11()

    # Resize to a larger viewport and let the layout settle. The
    # resizeEvent override must re-call fitInView so the pixmap scales
    # up to fill the new viewport (KeepAspectRatio). Without the
    # override the transform stays at the small-viewport scale.
    view.resize(640, 480)
    qtbot.wait(50)
    scale_after = view.transform().m11()

    assert scale_after > scale_before, (
        f"resizeEvent did not refit: transform scale went {scale_before:.3f} "
        f"-> {scale_after:.3f} (expected increase after growing viewport — "
        f"fitInView not re-called on resize)"
    )


def test_resize_event_no_recursion(qtbot) -> None:
    """resizeEvent must not cause infinite recursion (scrollbar AlwaysOff
    prevents the show/hide→resize cycle). The test simply asserts the
    widget survives a resize without hanging or crashing."""
    import numpy as np

    from lightsheet.gui.panels.image_view import ImageView

    view = ImageView()
    view.resize(400, 300)
    qtbot.addWidget(view)
    view.show()
    qtbot.waitExposed(view)

    frame = np.zeros((100, 100), dtype=np.uint16)
    frame[50, 50] = 20000
    view.setImage(frame)

    # Several resizes — if resizeEvent recursed this would hang/CPU-spin
    # and the test would time out.
    for w, h in [(640, 480), (320, 240), (800, 600), (500, 500)]:
        view.resize(w, h)
        qtbot.wait(20)

    # If we got here without hanging, recursion did not occur.
    assert view.width() == 500


def test_levels_driven_clamp(qtbot) -> None:
    """set_levels updates the display window; a frame with values 0-4000
    displayed with levels 1000-3000 clamps to that window (pixels below
    1000 render black, pixels above 3000 render white)."""
    from lightsheet.gui.panels.image_view import ImageView

    view = ImageView()
    qtbot.addWidget(view)

    # Frame with a known spread: 0, 1000, 2000, 3000, 4000 across 5 px.
    frame = np.zeros((1, 5), dtype=np.uint16)
    frame[0, 0] = 0
    frame[0, 1] = 1000
    frame[0, 2] = 2000
    frame[0, 3] = 3000
    frame[0, 4] = 4000

    view.setImage(frame)
    # Narrow the window to 1000-3000.
    view.set_levels(1000, 3000)

    # The displayed buffer must reflect the new window: pixel 0 (value 0,
    # below 1000) clamps to 0 (black); pixel 4 (value 4000, above 3000)
    # clamps to 255 (white); pixel 2 (value 2000, midpoint of 1000-3000)
    # renders ~127.
    qimage = view._pixmap_item.pixmap().toImage()
    # Column-major transposition aside, this 1-row frame maps directly.
    v0 = qimage.pixelColor(0, 0).value()
    v4 = qimage.pixelColor(4, 0).value()
    v2 = qimage.pixelColor(2, 0).value()
    assert v0 == 0, f"pixel below window should be black, got {v0}"
    assert v4 == 255, f"pixel above window should be white, got {v4}"
    assert 100 <= v2 <= 155, f"midpoint pixel should be ~127, got {v2}"


def test_levels_readout_updates(qtbot, request) -> None:
    """After setImage, the live min/max QLabel readout shows the frame's
    actual pixel range (not the display window)."""
    from _helpers.controller_fixture import make_controller

    ctrl, _ = make_controller(qtbot, request)
    import numpy as np

    frame = np.zeros((10, 10), dtype=np.uint16)
    frame[0, 0] = 1234
    frame[5, 5] = 5678
    ctrl._update_levels_readout(frame)
    text = ctrl.ui.label_levelsReadout.text()
    # The readout shows the actual pixel range (frame.min()/max()), not
    # the display window.
    assert "0" in text, f"readout missing frame min: {text!r}"
    assert "5678" in text, f"readout missing frame max: {text!r}"


def test_levels_bar_wired_to_image_view(qtbot, request) -> None:
    """Dragging the LevelsBar handles updates the ImageView display
    window via the shell's sig_levelsChanged → set_levels wiring."""
    from _helpers.controller_fixture import make_controller

    ctrl, _ = make_controller(qtbot, request)
    import numpy as np

    frame = np.zeros((10, 10), dtype=np.uint16)
    frame[0, 0] = 4000
    ctrl.ui.imageView.setImage(frame)
    # The demo launch pushes the demo image's uint16 data range (0-65535)
    # to the LevelsBar; the explicit set_data_range below is a no-op guard
    # so the window value is not clamped regardless of demo-image state,
    # then drive the LevelsBar window via its property (the setter emits
    # sig_levelsChanged, which the shell wires to set_levels).
    ctrl.ui.levelsBar.set_data_range(0, 65535)
    ctrl.ui.levelsBar.levels_max = 1000
    assert ctrl.ui.imageView._levels_max == 1000, (
        "LevelsBar sig_levelsChanged did not propagate to ImageView"
    )
