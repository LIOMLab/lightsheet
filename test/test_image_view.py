"""Behavior tests for the ImageView RGB tint extension.

When ``setImage`` is called with a ``tint`` (a 6-char hex color string, no
``#``), the displayed frame is an RGB888 image whose R/G/B channels are the
grayscale values modulated by the tint color (``channel_c = (frame_scaled *
color_c) // 255``). When no tint is passed, the existing grayscale
``Format_Grayscale8`` path runs unchanged (single-channel back-compat).

The format is asserted on the source QImage the widget builds
(``view._src_qimage``) — the QPixmap round-trip converts to the
screen-backed 32-bit format and would mask the source format. The pixel
data is asserted on the source QImage's interleaved RGB bytes, which
survive the round-trip as the same color on screen.

Runs headless on Mac via ``QT_QPA_PLATFORM=offscreen`` (set by conftest).
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("PySide6")


def _scaled_uint8(frame: np.ndarray, levels_min: int, levels_max: int) -> np.ndarray:
    """Mirror the ImageView's grayscale scaling for test setup."""
    span = levels_max - levels_min
    if span <= 0:
        return (frame > levels_min).astype(np.uint8) * 255
    clamped = np.clip(frame, levels_min, levels_max)
    return ((clamped - levels_min) / span * 255).astype(np.uint8)


def test_set_image_with_tint_produces_rgb888(qtbot) -> None:
    """setImage(frame, tint='00FF00') produces a Format_RGB888 QImage where
    R is all-zero, G equals the scaled grayscale, and B is all-zero — the
    displayed pixmap is green-tinted."""
    from PySide6.QtGui import QImage

    from lightsheet.gui.panels.image_view import ImageView

    view = ImageView()
    qtbot.addWidget(view)

    frame = np.zeros((10, 10), dtype=np.uint16)
    frame[:] = 10000  # midpoint of the default 0-20000 window

    view.setImage(frame, tint="00FF00")

    assert view._pixmap_item is not None, "pixmap item not set after setImage"
    qimage = view._src_qimage
    assert qimage is not None
    assert qimage.format() == QImage.Format.Format_RGB888, (
        f"tinted source image must be Format_RGB888; got {qimage.format()}"
    )

    # The default levels window is 0-20000; 10000 -> uint8 127.
    expected_g = _scaled_uint8(frame, 0, 20000)
    # Pull the interleaved RGB bytes out of the source QImage (RGB888 is
    # packed as (H, W, 3) uint8 row-major).
    ptr = qimage.constBits()
    arr = np.frombuffer(ptr, dtype=np.uint8, count=10 * 10 * 3).reshape(10, 10, 3)
    assert np.all(arr[:, :, 0] == 0), "R channel must be zero for a green tint"
    assert np.all(arr[:, :, 2] == 0), "B channel must be zero for a green tint"
    assert np.array_equal(arr[:, :, 1], expected_g), (
        "G channel must equal the scaled grayscale for a green tint"
    )


def test_set_image_with_red_tint_produces_red_channel_only(qtbot) -> None:
    """setImage(frame, tint='FF0000') puts the grayscale into the R channel
    only (G and B are zero) — the displayed pixmap is red-tinted."""
    from PySide6.QtGui import QImage

    from lightsheet.gui.panels.image_view import ImageView

    view = ImageView()
    qtbot.addWidget(view)

    frame = np.zeros((8, 8), dtype=np.uint16)
    frame[:] = 5000

    view.setImage(frame, tint="FF0000")

    qimage = view._src_qimage
    assert qimage is not None
    assert qimage.format() == QImage.Format.Format_RGB888

    expected_r = _scaled_uint8(frame, 0, 20000)
    ptr = qimage.constBits()
    arr = np.frombuffer(ptr, dtype=np.uint8, count=8 * 8 * 3).reshape(8, 8, 3)
    assert np.array_equal(arr[:, :, 0], expected_r), "R channel must equal scaled grayscale"
    assert np.all(arr[:, :, 1] == 0), "G channel must be zero for a red tint"
    assert np.all(arr[:, :, 2] == 0), "B channel must be zero for a red tint"


def test_set_image_without_tint_is_grayscale8(qtbot) -> None:
    """setImage(frame) with no tint produces Format_Grayscale8 exactly as
    before (single-channel back-compat — byte-identical display path)."""
    from PySide6.QtGui import QImage

    from lightsheet.gui.panels.image_view import ImageView

    view = ImageView()
    qtbot.addWidget(view)

    frame = np.zeros((10, 10), dtype=np.uint16)
    frame[5, 5] = 20000

    view.setImage(frame)

    qimage = view._src_qimage
    assert qimage is not None
    assert qimage.format() == QImage.Format.Format_Grayscale8, (
        f"no-tint source image must be Format_Grayscale8; got {qimage.format()}"
    )


def test_set_image_stores_last_tint_for_levels_rerender(qtbot) -> None:
    """After setImage(frame, tint='00FF00'), set_levels re-renders WITH the
    stored tint so the operator does not lose the channel color after
    dragging the levels window. The re-rendered source image is still
    RGB888."""
    from PySide6.QtGui import QImage

    from lightsheet.gui.panels.image_view import ImageView

    view = ImageView()
    qtbot.addWidget(view)

    frame = np.zeros((8, 8), dtype=np.uint16)
    frame[:] = 10000
    view.setImage(frame, tint="00FF00")
    assert view._last_tint == "00FF00", "setImage must store the tint on _last_tint"

    # Re-render via set_levels — the tint must survive the re-render.
    view.set_levels(0, 20000)
    qimage = view._src_qimage
    assert qimage is not None
    assert qimage.format() == QImage.Format.Format_RGB888, (
        "set_levels must re-apply the stored tint (RGB888 source image)"
    )


def test_set_image_without_tint_stores_none(qtbot) -> None:
    """When no tint is passed, _last_tint is None so set_levels re-renders
    grayscale (single-channel back-compat across level adjustments)."""
    from lightsheet.gui.panels.image_view import ImageView

    view = ImageView()
    qtbot.addWidget(view)

    frame = np.zeros((8, 8), dtype=np.uint16)
    frame[:] = 10000
    view.setImage(frame)
    assert view._last_tint is None, "no-tint setImage must store None on _last_tint"
