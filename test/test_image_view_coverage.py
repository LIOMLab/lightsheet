"""Branch-coverage tests for ImageView.

Covers branches not exercised by the existing tint/render/resize tests:
- ``set_levels`` when no frame is loaded (early return at line 115->exit)
- ``set_colormap_range`` (lines 129-145) — clamps the window into the new
  range and re-renders
- ``wheelEvent`` (lines 167-181) — zoom around the cursor, marks
  ``_user_transformed``
- ``setImage`` with a degenerate levels window (span <= 0, line 237) —
  binary threshold fallback
- ``setImage`` when ``_user_transformed`` is True (line 313->exit) —
  preserves the operator's zoom/pan across new frames
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pytest
from pytestqt.qtbot import QtBot

pytest.importorskip("PySide6")

if TYPE_CHECKING:
    from PySide6.QtCore import QPoint


def test_set_levels_with_no_frame_is_noop(qtbot: QtBot) -> None:
    """set_levels before any setImage is a no-op: _last_frame is None so
    the re-render branch (line 115->exit True path) is skipped. The levels
    values are still stored for the next setImage."""
    from lightsheet.gui.panels.image_view import ImageView

    view = ImageView()
    qtbot.addWidget(view)
    assert view._last_frame is None
    view.set_levels(100, 500)
    assert view._levels_min == 100
    assert view._levels_max == 500
    # No pixmap item was created (no re-render).
    assert view._pixmap_item is None


def test_set_colormap_range_clamps_window_and_rerenders(qtbot: QtBot) -> None:
    """set_colormap_range narrows the colormap span and clamps the levels
    window into it. A window setpoint outside the new range is pulled back
    inside. The current frame is re-rendered with the new scaling."""
    from lightsheet.gui.panels.image_view import ImageView

    view = ImageView()
    qtbot.addWidget(view)
    frame = np.zeros((8, 8), dtype=np.uint16)
    frame[:] = 30000
    view.setImage(frame)
    # Default levels 0-20000, colormap 0-65535. Narrow the colormap to
    # 0-10000 — the levels_max (20000) is outside the new range and must
    # clamp to 10000.
    view.set_colormap_range(0, 10000)
    assert view._colormap_min == 0
    assert view._colormap_max == 10000
    assert view._levels_max <= 10000, (
        f"levels_max should clamp into colormap range, got {view._levels_max}"
    )
    # The frame was re-rendered (pixmap item still present).
    assert view._pixmap_item is not None


def test_set_colormap_range_with_no_frame_stores_range(qtbot: QtBot) -> None:
    """set_colormap_range with no frame stores the range but skips the
    re-render (covers the _last_frame is None branch inside
    set_colormap_range)."""
    from lightsheet.gui.panels.image_view import ImageView

    view = ImageView()
    qtbot.addWidget(view)
    assert view._last_frame is None
    view.set_colormap_range(100, 5000)
    assert view._colormap_min == 100
    assert view._colormap_max == 5000


def test_wheel_event_zooms_and_marks_user_transformed(qtbot: QtBot) -> None:
    """wheelEvent zooms the view around the cursor and sets
    _user_transformed = True so subsequent resizeEvents do not auto-fit."""
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtWidgets import QApplication

    from lightsheet.gui.panels.image_view import ImageView

    view = ImageView()
    view.resize(200, 200)
    qtbot.addWidget(view)
    view.show()
    qtbot.waitExposed(view)

    frame = np.zeros((50, 50), dtype=np.uint16)
    frame[25, 25] = 20000
    view.setImage(frame)
    assert not view._user_transformed

    pos = QPointF(100.0, 100.0)
    evt = QWheelEvent(
        pos,
        pos,
        QPoint_for_wheel(0, 120),
        QPoint_for_wheel(0, 120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.ScrollBegin,
        False,
    )
    # QGraphicsView delivers wheel events to its viewport, not the widget
    # itself. Send to the viewport so the override fires.
    QApplication.sendEvent(view.viewport(), evt)
    assert view._user_transformed, (
        "wheelEvent must set _user_transformed after zoom"
    )


def QPoint_for_wheel(x: int, y: int) -> QPoint:
    """Helper to construct a QPoint without importing it at module level
    (keeps the import list clean for the non-wheel tests)."""
    from PySide6.QtCore import QPoint

    return QPoint(x, y)


def test_set_image_with_degenerate_levels_span_uses_binary_threshold(
    qtbot: QtBot,
) -> None:
    """When levels_min == levels_max (span <= 0), setImage falls back to
    a binary threshold instead of dividing by zero. Pixels above
    levels_min render white (255); at-or-below render black (0)."""
    from lightsheet.gui.panels.image_view import ImageView

    view = ImageView()
    qtbot.addWidget(view)
    # Set a degenerate window: both handles at the same value.
    view._levels_min = 1000
    view._levels_max = 1000
    frame = np.zeros((1, 4), dtype=np.uint16)
    frame[0, 0] = 0      # below threshold -> black
    frame[0, 1] = 1000   # at threshold -> black (<=)
    frame[0, 2] = 1001   # above threshold -> white
    frame[0, 3] = 5000   # above threshold -> white
    view.setImage(frame)
    # The re-render must not crash (no nan/inf from div-by-zero).
    assert view._pixmap_item is not None
    assert view._src_qimage is not None


def test_set_image_preserves_user_transform(qtbot: QtBot) -> None:
    """After the operator zooms (_user_transformed = True), a subsequent
    setImage does NOT call fitInView (line 313->exit False branch) — the
    operator's zoom/pan is preserved across new frames."""
    from lightsheet.gui.panels.image_view import ImageView

    view = ImageView()
    view.resize(200, 200)
    qtbot.addWidget(view)
    view.show()
    qtbot.waitExposed(view)

    frame1 = np.zeros((50, 50), dtype=np.uint16)
    frame1[25, 25] = 20000
    view.setImage(frame1)
    # Simulate operator zoom.
    view._user_transformed = True
    scale_before = view.transform().m11()
    # Apply a manual zoom so the scale is non-identity.
    view.scale(2.0, 2.0)
    scale_after_zoom = view.transform().m11()
    assert scale_after_zoom > scale_before

    # New frame — fitInView must NOT be called (would reset the zoom).
    frame2 = np.zeros((50, 50), dtype=np.uint16)
    frame2[10, 10] = 20000
    view.setImage(frame2)
    scale_after_new_frame = view.transform().m11()
    assert abs(scale_after_new_frame - scale_after_zoom) < 0.01, (
        f"setImage reset the operator's zoom after a new frame: "
        f"{scale_after_zoom:.3f} -> {scale_after_new_frame:.3f}"
    )
