"""LevelsBar(QWidget) — custom stock-Qt6 widget with FIVE draggable handles
on a grayscale gradient: RANGE min/max (data-following) + WINDOW min/max
(within the range) + a central handle that drags both window setpoints
together (preserves width, shifts center).

The widget is a pure stock-Qt6 QWidget: paintEvent draws the gradient +
handles, mousePressEvent/mouseMoveEvent implement hit-test + drag. No
pyqtgraph. Mock-testable under QT_QPA_PLATFORM=offscreen via synthesized
QMouseEvent sequences.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from pytestqt.qtbot import QtBot

if TYPE_CHECKING:
    from lightsheet.gui.panels.levels_bar import LevelsBar

pytest.importorskip("PySide6")


def _make_bar(qtbot: QtBot) -> LevelsBar:
    from lightsheet.gui.panels.levels_bar import LevelsBar

    bar = LevelsBar()
    bar.resize(400, 64)
    qtbot.addWidget(bar)
    bar.show()
    qtbot.waitExposed(bar)
    return bar


def test_levels_bar_is_qwidget_subclass(qtbot: QtBot) -> None:
    from PySide6.QtWidgets import QWidget

    bar = _make_bar(qtbot)
    assert isinstance(bar, QWidget)


def test_levels_bar_default_range_and_window(qtbot: QtBot) -> None:
    """Default range is 0-65535 (uint16); window defaults to the full range."""
    bar = _make_bar(qtbot)
    assert bar.range_min == 0
    assert bar.range_max == 65535
    assert bar.window_min == 0
    assert bar.window_max == 65535
    # Backward-compat aliases (window values).
    assert bar.levels_min == 0
    assert bar.levels_max == 65535


def test_levels_bar_has_sig_levels_changed(qtbot: QtBot) -> None:
    bar = _make_bar(qtbot)
    received: list[tuple[int, int]] = []
    bar.sig_levelsChanged.connect(lambda lo, hi: received.append((lo, hi)))
    bar.window_min = 500
    assert (500, 65535) in received


def test_levels_bar_has_sig_range_changed(qtbot: QtBot) -> None:
    """sig_rangeChanged is Signal(int, int) and fires on set_data_range."""
    bar = _make_bar(qtbot)
    received: list[tuple[int, int]] = []
    bar.sig_rangeChanged.connect(lambda lo, hi: received.append((lo, hi)))
    # Use a non-default range so the call is not a no-op (the default range
    # is already 0-65535).
    bar.set_data_range(0, 4000)
    assert (0, 4000) in received


def test_set_data_range_clamps_user_owned_range_into_narrowed_bounds(
    qtbot: QtBot,
) -> None:
    """When the operator has dragged a RANGE handle (_range_user_owned), a
    subsequent dtype change that narrows the data bounds must clamp the
    user-owned range into the new bounds. _value_to_x maps handle positions
    against the data bounds, so an unclamped range_max > data_max would
    draw the range_max handle off-screen (x > width). Also verifies
    sig_rangeChanged fires so the ImageView colormap range stays
    consistent."""
    bar = _make_bar(qtbot)
    bar.set_data_range(0, 65535)  # uint16
    # Operator drags range_max out to 50000 (within uint16 data bounds).
    bar._range_user_owned = True
    bar._range_max = 50000
    range_events: list[tuple[int, int]] = []
    bar.sig_rangeChanged.connect(lambda lo, hi: range_events.append((lo, hi)))
    # Dtype change narrows the data bounds to uint8 (0-255).
    bar.set_data_range(0, 255)
    assert bar.range_max <= 255, (
        f"range_max {bar.range_max} not clamped into uint8 bounds"
    )
    assert bar.range_min >= 0
    # The range was clamped, so sig_rangeChanged fired with the new bounds.
    assert any(hi <= 255 for _, hi in range_events), (
        f"sig_rangeChanged did not fire with clamped range: {range_events}"
    )


def test_levels_bar_min_size_and_size_policy(qtbot: QtBot) -> None:
    from PySide6.QtWidgets import QSizePolicy

    bar = _make_bar(qtbot)
    assert bar.minimumSize().width() >= 320
    assert bar.minimumSize().height() >= 64
    sp = bar.sizePolicy()
    assert sp.horizontalPolicy() == QSizePolicy.Policy.Expanding
    assert sp.verticalPolicy() == QSizePolicy.Policy.Fixed
    assert sp.horizontalStretch() == 1
    assert sp.verticalStretch() == 0


def _press_at(bar: LevelsBar, x: int, y: int = 32) -> None:
    """Synthesize a left-button press at widget-local coords (x, y)."""
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication

    pos = QPointF(float(x), float(y))
    evt = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        pos,
        pos,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(bar, evt)


def _window_row_y(bar: LevelsBar) -> int:
    """The y pixel center of the WINDOW + central handle row."""
    _range_y, window_y = bar._row_y()
    return window_y


def _range_row_y(bar: LevelsBar) -> int:
    """The y pixel center of the RANGE handle row (upper half)."""
    range_y, _window_y = bar._row_y()
    return range_y


def _move_to(bar: LevelsBar, x: int, y: int = 32) -> None:
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication

    pos = QPointF(float(x), float(y))
    evt = QMouseEvent(
        QEvent.Type.MouseMove,
        pos,
        pos,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(bar, evt)


def _release(bar: LevelsBar) -> None:
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication

    pos = QPointF(0.0, 0.0)
    evt = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        pos,
        pos,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(bar, evt)


# -- set_data_range behavior ----------------------------------------------


def test_set_data_range_sets_range_and_clamps_window(qtbot: QtBot) -> None:
    """set_data_range(0, 65535) sets the range; window clamps into it."""
    bar = _make_bar(qtbot)
    bar.set_data_range(0, 65535)
    assert bar.range_min == 0
    assert bar.range_max == 65535
    # Window defaults to full range; still in range.
    assert 0 <= bar.window_min <= bar.window_max <= 65535


def test_set_data_range_clamps_existing_window_in(qtbot: QtBot) -> None:
    """set_data_range(100, 500) with prior window (200, 300) keeps it;
    with prior window (50, 600) clamps to (100, 500)."""
    bar = _make_bar(qtbot)
    # Establish a window of (200, 300) within a wide range first.
    bar.set_data_range(0, 1000)
    bar.window_min = 200
    bar.window_max = 300
    # Narrow the range to (100, 500) — window stays inside.
    bar.set_data_range(100, 500)
    assert bar.window_min == 200
    assert bar.window_max == 300

    # Now widen back, set a window that exceeds the next range, then narrow.
    bar.set_data_range(0, 1000)
    bar.window_min = 50
    bar.window_max = 600
    bar.set_data_range(100, 500)
    assert bar.window_min == 100, (
        f"window_min should clamp to range_min=100, got {bar.window_min}"
    )
    assert bar.window_max == 500, (
        f"window_max should clamp to range_max=500, got {bar.window_max}"
    )


def test_set_data_range_emits_sig_range_changed(qtbot: QtBot) -> None:
    bar = _make_bar(qtbot)
    received: list[tuple[int, int]] = []
    bar.sig_rangeChanged.connect(lambda lo, hi: received.append((lo, hi)))
    bar.set_data_range(100, 500)
    assert (100, 500) in received


def test_hardcoded_2000_bound_is_gone(qtbot: QtBot) -> None:
    """The old LEVELS_MAX_BOUND=2000 would have clipped set_data_range(0, 65535).
    The new widget accepts the full uint16 range."""
    bar = _make_bar(qtbot)
    bar.set_data_range(0, 65535)
    assert bar.range_max == 65535


# -- _hit_handle behavior -------------------------------------------------


def test_hit_handle_returns_none_outside_all_radii(qtbot: QtBot) -> None:
    """A click far from every handle returns None."""
    bar = _make_bar(qtbot)
    bar.set_data_range(0, 1000)
    bar.window_min = 200
    bar.window_max = 400
    # width=400: range_min@0, window_min@80, center@120, window_max@160, range_max@400.
    # x=250 is >8px from every handle.
    assert bar._hit_handle(250) is None


def test_hit_handle_returns_handle_names(qtbot: QtBot) -> None:
    """Pressing within ±8px of each handle returns its name."""
    bar = _make_bar(qtbot)
    bar.set_data_range(0, 1000)
    bar.window_min = 200
    bar.window_max = 400
    # width=400: range_min@0, window_min@80, center@120, window_max@160, range_max@400.
    assert bar._hit_handle(0) == "range_min"
    assert bar._hit_handle(400) == "range_max"
    assert bar._hit_handle(80) == "window_min"
    assert bar._hit_handle(160) == "window_max"
    assert bar._hit_handle(120) == "center"


def test_press_near_center_starts_center_drag(qtbot: QtBot) -> None:
    """Pressing within ±8px of the central handle starts a 'center' drag."""
    bar = _make_bar(qtbot)
    bar.set_data_range(0, 1000)
    bar.window_min = 200
    bar.window_max = 400
    # center@120; press at 120 on the window row.
    _press_at(bar, 120, _window_row_y(bar))
    assert bar._dragging_handle == "center"
    _release(bar)


# -- central-handle drag --------------------------------------------------


def test_center_drag_preserves_width_and_shifts(qtbot: QtBot) -> None:
    """From window (200, 400) (width 200, center 300), dragging center to
    500 yields window (400, 600) (width preserved)."""
    bar = _make_bar(qtbot)
    bar.set_data_range(0, 1000)
    bar.window_min = 200
    bar.window_max = 400
    received: list[tuple[int, int]] = []
    bar.sig_levelsChanged.connect(lambda lo, hi: received.append((lo, hi)))
    # center@120 (value 300). Press, drag to value 500 → x = 500/1000*400 = 200.
    _press_at(bar, 120, _window_row_y(bar))
    _move_to(bar, 200, _window_row_y(bar))
    _release(bar)
    assert bar.window_min == 400, (
        f"expected window_min=400 after center drag, got {bar.window_min}"
    )
    assert bar.window_max == 600, (
        f"expected window_max=600 after center drag, got {bar.window_max}"
    )
    assert any(lo == 400 and hi == 600 for (lo, hi) in received)


def test_center_drag_clamps_at_range_max(qtbot: QtBot) -> None:
    """Dragging center past range_max shifts both so window_max == range_max."""
    bar = _make_bar(qtbot)
    bar.set_data_range(0, 1000)
    bar.window_min = 200
    bar.window_max = 400  # half_width = 100
    _press_at(bar, 120, _window_row_y(bar))  # center@120
    # Drag center to a value that would push window_max past 1000.
    # value 2000 → x = 2000/1000*400 = 800.
    _move_to(bar, 800, _window_row_y(bar))
    _release(bar)
    assert bar.window_max == 1000, (
        f"window_max should clamp to range_max=1000, got {bar.window_max}"
    )
    # width preserved: window_max - window_min == 200.
    assert bar.window_max - bar.window_min == 200


def test_center_drag_clamps_at_range_min(qtbot: QtBot) -> None:
    """Dragging center past range_min shifts both so window_min == range_min."""
    bar = _make_bar(qtbot)
    bar.set_data_range(0, 1000)
    bar.window_min = 600
    bar.window_max = 800  # half_width = 100, center = 700
    # center@x = 700/1000*400 = 280.
    _press_at(bar, 280, _window_row_y(bar))
    # Drag center to a negative-ish value: x=0 → value 0.
    _move_to(bar, 0, _window_row_y(bar))
    _release(bar)
    assert bar.window_min == 0, (
        f"window_min should clamp to range_min=0, got {bar.window_min}"
    )
    assert bar.window_max - bar.window_min == 200


# -- WINDOW handle drag ---------------------------------------------------


def test_drag_window_min_handle(qtbot: QtBot) -> None:
    """Dragging the window_min handle updates window_min and emits
    sig_levelsChanged (not sig_rangeChanged)."""
    bar = _make_bar(qtbot)
    bar.set_data_range(0, 1000)
    bar.window_min = 200
    bar.window_max = 400
    levels_received: list[tuple[int, int]] = []
    range_received: list[tuple[int, int]] = []
    bar.sig_levelsChanged.connect(lambda lo, hi: levels_received.append((lo, hi)))
    bar.sig_rangeChanged.connect(lambda lo, hi: range_received.append((lo, hi)))
    # window_min@80. Press, drag to x=160 (value 400) — but that's window_max's
    # position; drag to x=120 (value 300) instead to stay below window_max.
    _press_at(bar, 80, _window_row_y(bar))
    _move_to(bar, 120, _window_row_y(bar))
    _release(bar)
    assert bar.window_min == 300, f"expected window_min=300, got {bar.window_min}"
    assert any(lo == 300 for (lo, _hi) in levels_received)
    # Moving a WINDOW handle must NOT emit sig_rangeChanged.
    assert range_received == []


def test_drag_window_max_handle(qtbot: QtBot) -> None:
    bar = _make_bar(qtbot)
    bar.set_data_range(0, 1000)
    bar.window_min = 200
    bar.window_max = 400
    received: list[tuple[int, int]] = []
    bar.sig_levelsChanged.connect(lambda lo, hi: received.append((lo, hi)))
    # window_max@160. Press, drag to x=120 (value 300) — below window_min? No,
    # window_min=200 → x=80. Drag to x=200 (value 500).
    _press_at(bar, 160, _window_row_y(bar))
    _move_to(bar, 200, _window_row_y(bar))
    _release(bar)
    assert bar.window_max == 500, f"expected window_max=500, got {bar.window_max}"
    assert any(hi == 500 for (_lo, hi) in received)


def test_window_handle_drag_clamps_to_range(qtbot: QtBot) -> None:
    """Dragging window_min below range_min clamps to range_min."""
    bar = _make_bar(qtbot)
    bar.set_data_range(0, 1000)
    bar.window_min = 200
    bar.window_max = 400
    _press_at(bar, 80, _window_row_y(bar))  # window_min@80
    _move_to(bar, 0, _window_row_y(bar))  # value 0
    _release(bar)
    assert bar.window_min == 0, (
        f"window_min should clamp to range_min=0, got {bar.window_min}"
    )


def test_window_handles_swap_when_dragged_past(qtbot: QtBot) -> None:
    """Dragging window_min past window_max swaps them."""
    bar = _make_bar(qtbot)
    bar.set_data_range(0, 1000)
    bar.window_min = 200
    bar.window_max = 400
    _press_at(bar, 80, _window_row_y(bar))  # window_min@80 (value 200)
    # Drag to x=200 (value 500) — past window_max (400).
    _move_to(bar, 200, _window_row_y(bar))
    _release(bar)
    # After swap: window_min = old window_max (400), window_max = 500.
    assert bar.window_min == 400, (
        f"after swap window_min should be 400, got {bar.window_min}"
    )
    assert bar.window_max == 500, (
        f"after swap window_max should be 500, got {bar.window_max}"
    )


# -- RANGE handle drag ----------------------------------------------------


def test_drag_range_min_handle(qtbot: QtBot) -> None:
    """Dragging the range_min handle updates range_min and emits
    sig_rangeChanged."""
    bar = _make_bar(qtbot)
    bar.set_data_range(0, 1000)
    # Narrow the window so window_min is NOT at x=0 (otherwise the
    # hit-test tiebreaker grabs window_min, not range_min).
    bar.window_min = 200
    bar.window_max = 400
    range_received: list[tuple[int, int]] = []
    bar.sig_rangeChanged.connect(lambda lo, hi: range_received.append((lo, hi)))
    # range_min@0. Press, drag to x=100 (value 250).
    _press_at(bar, 0, _range_row_y(bar))
    _move_to(bar, 100, _range_row_y(bar))
    _release(bar)
    assert bar.range_min == 250, f"expected range_min=250, got {bar.range_min}"
    assert any(lo == 250 for (lo, _hi) in range_received)


def test_range_handles_cannot_cross(qtbot: QtBot) -> None:
    """Dragging range_min past range_max clamps range_min to range_max."""
    bar = _make_bar(qtbot)
    bar.set_data_range(0, 1000)
    # Narrow the window so range_min is grabbable at x=0.
    bar.window_min = 200
    bar.window_max = 400
    # range_max@400 (value 1000). Drag range_min to x=400 (value 1000).
    _press_at(bar, 0, _range_row_y(bar))
    _move_to(bar, 400, _range_row_y(bar))
    _release(bar)
    assert bar.range_min == 1000, (
        f"range_min should clamp to range_max=1000, got {bar.range_min}"
    )
    assert bar.range_min <= bar.range_max


# -- paint + misc ---------------------------------------------------------


def test_paint_event_renders_without_error(qtbot: QtBot) -> None:
    """paintEvent draws 5 handles on the gradient without error at 320x64."""
    bar = _make_bar(qtbot)
    bar.set_data_range(0, 65535)
    bar.window_min = 1000
    bar.window_max = 5000
    bar.resize(320, 64)
    qtbot.wait(10)
    # Force a repaint — if paintEvent raises, the test fails.
    bar.repaint()
    assert bar.width() == 320
    assert bar.height() == 64


def test_click_far_from_handle_does_not_grab(qtbot: QtBot) -> None:
    """A click >8px from every handle does NOT grab any handle."""
    bar = _make_bar(qtbot)
    bar.set_data_range(0, 1000)
    bar.window_min = 200
    bar.window_max = 400
    _press_at(bar, 250)  # >8px from every handle
    _move_to(bar, 100)
    _release(bar)
    assert bar.window_min == 200
    assert bar.window_max == 400
    assert bar.range_min == 0
    assert bar.range_max == 1000


def test_no_pyqtgraph_import_in_levels_bar_module() -> None:
    """The levels bar must be stock-Qt6 only — no pyqtgraph dependency."""
    import inspect

    from lightsheet.gui.panels import levels_bar

    src = inspect.getsource(levels_bar)
    assert "pyqtgraph" not in src.lower(), (
        "levels_bar.py must not import or reference pyqtgraph"
    )
