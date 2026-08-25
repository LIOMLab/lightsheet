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
    from lightsheet.gui.image_view import ImageView

    view = ImageView()
    qtbot.addWidget(view)

    # Create a 100x100 uint16 frame with a single seed pixel at 2000
    # (the maximum of the fixed 0-2000 levels window). After scaling to
    # uint8 [0, 255] this pixel must map to 255; every other pixel is 0.
    frame = np.zeros((100, 100), dtype=np.uint16)
    frame[50, 50] = 2000

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
