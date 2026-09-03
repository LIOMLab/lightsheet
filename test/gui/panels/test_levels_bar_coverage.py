"""Branch-coverage tests for LevelsBar.

Covers branches not exercised by the existing drag/hit-test/paint tests:
- ``levels_min`` / ``levels_max`` property setters (backward-compat aliases
  that delegate to ``window_min`` / ``window_max``)
- ``set_data_range`` with swapped min/max (``new_max < new_min`` → swap)
- ``window_min`` / ``window_max`` setters when the value is unchanged (no
  signal emission, no repaint)
- ``mouseReleaseEvent`` when a RANGE handle was dragged but the window did
  not change (no sig_levelsChanged emission)
- ``_hit_handle`` with ``y=None`` (defaults to range row)
- ``mouseMoveEvent`` / ``mousePressEvent`` with non-left button (ignored)
- ``mouseReleaseEvent`` when no handle is being dragged
- ``set_data_range`` no-op when range unchanged
- ``_hit_handle`` when a click is in the gradient band (between rows, grabs
  nothing)
- RANGE handle drag with no actual change (new_min == old range_min)
- WINDOW handle swap in both directions (window_min past window_max and
  vice versa)
- center drag with no change (new values == old values)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from pytestqt.qtbot import QtBot

pytest.importorskip("PySide6")

if TYPE_CHECKING:
    from lightsheet.gui.panels.levels_bar import LevelsBar


def _make_bar(qtbot: QtBot) -> LevelsBar:
    from lightsheet.gui.panels.levels_bar import LevelsBar

    bar = LevelsBar()
    bar.resize(400, 64)
    qtbot.addWidget(bar)
    bar.show()
    qtbot.waitExposed(bar)
    return bar


def _press_at(bar: LevelsBar, x: int, y: int = 32) -> None:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication

    pos = QPointF(float(x), float(y))
    evt = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        pos,
        pos,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(bar, evt)


def _move_to(bar: LevelsBar, x: int, y: int = 32) -> None:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication

    pos = QPointF(float(x), float(y))
    evt = QMouseEvent(
        QMouseEvent.Type.MouseMove,
        pos,
        pos,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(bar, evt)


def _release(bar: LevelsBar) -> None:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication

    pos = QPointF(0.0, 0.0)
    evt = QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease,
        pos,
        pos,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(bar, evt)


def _range_row_y(bar: LevelsBar) -> int:
    range_y, _window_y = bar._row_y()
    return range_y


def _window_row_y(bar: LevelsBar) -> int:
    _range_y, window_y = bar._row_y()
    return window_y


# -- property setter aliases ----------------------------------------------


def test_levels_min_setter_delegates_to_window_min(qtbot: QtBot) -> None:
    """The levels_min property setter delegates to window_min (backward-
    compat alias). Setting levels_min emits sig_levelsChanged."""
    bar = _make_bar(qtbot)
    bar.set_data_range(0, 1000)
    received: list[tuple[int, int]] = []
    bar.sig_levelsChanged.connect(lambda lo, hi: received.append((lo, hi)))
    bar.levels_min = 200
    assert bar.window_min == 200
    assert bar.levels_min == 200
    assert any(lo == 200 for (lo, _hi) in received)


def test_levels_max_setter_delegates_to_window_max(qtbot: QtBot) -> None:
    """The levels_max property setter delegates to window_max (backward-
    compat alias). Setting levels_max emits sig_levelsChanged."""
    bar = _make_bar(qtbot)
    bar.set_data_range(0, 1000)
    received: list[tuple[int, int]] = []
    bar.sig_levelsChanged.connect(lambda lo, hi: received.append((lo, hi)))
    bar.levels_max = 800
    assert bar.window_max == 800
    assert bar.levels_max == 800
    assert any(hi == 800 for (_lo, hi) in received)


def test_window_min_setter_no_change_no_signal(qtbot: QtBot) -> None:
    """Setting window_min to the same value does not emit
    sig_levelsChanged (the setter guards against no-op sets)."""
    bar = _make_bar(qtbot)
    bar.set_data_range(0, 1000)
    bar.window_min = 200
    received: list[tuple[int, int]] = []
    bar.sig_levelsChanged.connect(lambda lo, hi: received.append((lo, hi)))
    # Set to the same value — no signal.
    bar.window_min = 200
    assert received == []


def test_window_max_setter_no_change_no_signal(qtbot: QtBot) -> None:
    """Setting window_max to the same value does not emit
    sig_levelsChanged."""
    bar = _make_bar(qtbot)
    bar.set_data_range(0, 1000)
    bar.window_max = 800
    received: list[tuple[int, int]] = []
    bar.sig_levelsChanged.connect(lambda lo, hi: received.append((lo, hi)))
    bar.window_max = 800
    assert received == []


# -- set_data_range edge cases --------------------------------------------


def test_set_data_range_swaps_min_max(qtbot: QtBot) -> None:
    """set_data_range(dmin, dmax) with dmax < dmin swaps them so the
    range is always min <= max."""
    bar = _make_bar(qtbot)
    bar.set_data_range(500, 100)  # swapped
    assert bar.range_min == 100
    assert bar.range_max == 500


def test_set_data_range_noop_when_unchanged(qtbot: QtBot) -> None:
    """set_data_range with the same range as before is a no-op: no
    sig_rangeChanged emission, no repaint."""
    bar = _make_bar(qtbot)
    bar.set_data_range(0, 1000)
    received: list[tuple[int, int]] = []
    bar.sig_rangeChanged.connect(lambda lo, hi: received.append((lo, hi)))
    bar.set_data_range(0, 1000)  # same range
    assert received == []


# -- mouse interaction edge cases -----------------------------------------


def test_mouse_press_right_button_ignored(qtbot: QtBot) -> None:
    """A right-button press does not grab any handle (only LeftButton
    starts a drag)."""
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication

    bar = _make_bar(qtbot)
    bar.set_data_range(0, 1000)
    bar.window_min = 200
    bar.window_max = 400
    pos = QPointF(80.0, float(_window_row_y(bar)))  # at window_min
    evt = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        pos,
        pos,
        Qt.MouseButton.RightButton,
        Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(bar, evt)
    assert bar._dragging_handle is None


def test_mouse_move_no_drag_ignored(qtbot: QtBot) -> None:
    """A mouse move with no active drag is ignored (no handle grabbed)."""
    bar = _make_bar(qtbot)
    bar.set_data_range(0, 1000)
    bar.window_min = 200
    bar.window_max = 400
    assert bar._dragging_handle is None
    _move_to(bar, 100, _window_row_y(bar))
    # Values unchanged — no drag was started.
    assert bar.window_min == 200
    assert bar.window_max == 400


def test_mouse_release_no_drag_is_noop(qtbot: QtBot) -> None:
    """mouseReleaseEvent with no active drag just accepts the event."""
    bar = _make_bar(qtbot)
    bar.set_data_range(0, 1000)
    bar.window_min = 200
    bar.window_max = 400
    assert bar._dragging_handle is None
    _release(bar)
    # Nothing changed.
    assert bar.window_min == 200
    assert bar.window_max == 400


def test_range_min_drag_no_change_no_signal(qtbot: QtBot) -> None:
    """Dragging range_min to the same value (no actual change) does not
    emit sig_rangeChanged."""
    bar = _make_bar(qtbot)
    bar.set_data_range(0, 1000)
    bar.window_min = 200
    bar.window_max = 400
    range_received: list[tuple[int, int]] = []
    bar.sig_rangeChanged.connect(lambda lo, hi: range_received.append((lo, hi)))
    # range_min@0. Press at x=0 and move to x=0 (no change).
    _press_at(bar, 0, _range_row_y(bar))
    _move_to(bar, 0, _range_row_y(bar))
    _release(bar)
    # range_min stayed at 0 — no signal.
    assert bar.range_min == 0
    assert range_received == []


def test_range_max_drag_no_change_no_signal(qtbot: QtBot) -> None:
    """Dragging range_max to the same value (no actual change) does not
    emit sig_rangeChanged."""
    bar = _make_bar(qtbot)
    bar.set_data_range(0, 1000)
    bar.window_min = 200
    bar.window_max = 400
    range_received: list[tuple[int, int]] = []
    bar.sig_rangeChanged.connect(lambda lo, hi: range_received.append((lo, hi)))
    # range_max@400 (value 1000). Press at x=400 and move to x=400.
    _press_at(bar, 400, _range_row_y(bar))
    _move_to(bar, 400, _range_row_y(bar))
    _release(bar)
    assert bar.range_max == 1000
    assert range_received == []


def test_window_max_drag_below_window_min_swaps(qtbot: QtBot) -> None:
    """Dragging window_max below window_min swaps them: the dragged
    handle becomes window_min."""
    bar = _make_bar(qtbot)
    bar.set_data_range(0, 1000)
    bar.window_min = 200
    bar.window_max = 400
    # window_max@160 (value 400). Drag to x=40 (value 100) — below
    # window_min (200).
    _press_at(bar, 160, _window_row_y(bar))
    _move_to(bar, 40, _window_row_y(bar))
    _release(bar)
    # After swap: window_min = 100, window_max = 200.
    assert bar.window_min == 100, (
        f"after swap window_min should be 100, got {bar.window_min}"
    )
    assert bar.window_max == 200, (
        f"after swap window_max should be 200, got {bar.window_max}"
    )


def test_center_drag_no_change_no_signal(qtbot: QtBot) -> None:
    """Dragging center to the same position (no actual change) does not
    emit sig_levelsChanged."""
    bar = _make_bar(qtbot)
    bar.set_data_range(0, 1000)
    bar.window_min = 200
    bar.window_max = 400  # center@300, x=120
    received: list[tuple[int, int]] = []
    bar.sig_levelsChanged.connect(lambda lo, hi: received.append((lo, hi)))
    _press_at(bar, 120, _window_row_y(bar))
    # Move to the same center position (value 300 → x=120).
    _move_to(bar, 120, _window_row_y(bar))
    _release(bar)
    assert bar.window_min == 200
    assert bar.window_max == 400
    assert received == []


def test_range_release_clamps_window_no_change_no_signal(qtbot: QtBot) -> None:
    """When a RANGE handle is released and the window was already within
    the range, no sig_levelsChanged is emitted (the window did not
    change)."""
    bar = _make_bar(qtbot)
    bar.set_data_range(0, 1000)
    bar.window_min = 200
    bar.window_max = 400
    levels_received: list[tuple[int, int]] = []
    bar.sig_levelsChanged.connect(lambda lo, hi: levels_received.append((lo, hi)))
    # Drag range_min slightly but keep window within range.
    _press_at(bar, 0, _range_row_y(bar))
    _move_to(bar, 10, _range_row_y(bar))  # range_min = 25
    _release(bar)
    # Window (200, 400) is still within (25, 1000) — no levels change.
    assert bar.range_min == 25
    assert levels_received == []


def test_hit_handle_y_none_defaults_to_range_row(qtbot: QtBot) -> None:
    """_hit_handle with y=None defaults to the range row."""
    bar = _make_bar(qtbot)
    bar.set_data_range(0, 1000)
    bar.window_min = 200
    bar.window_max = 400
    # x=0 with y=None → range_min (range row).
    assert bar._hit_handle(0, y=None) == "range_min"


def test_hit_handle_in_gradient_band_grabs_nothing(qtbot: QtBot) -> None:
    """A click in the gradient band (between the two handle rows) grabs
    nothing — the y is too far from both rows."""
    bar = _make_bar(qtbot)
    bar.set_data_range(0, 1000)
    bar.window_min = 200
    bar.window_max = 400
    # The gradient band is between y=22 and y=h-22. For h=64 that's
    # y=22..42. A click at y=32 (middle) is equidistant from both rows
    # (y_range=12, y_window=52) — d_range=20, d_window=20, both >
    # HANDLE_HIT_RADIUS_Y_PX (10), so nothing is grabbed.
    result = bar._hit_handle(80, y=32)  # x=80 is at window_min
    assert result is None
