"""LevelsBar(QWidget) — custom stock-Qt6 widget with two draggable handles
on a grayscale gradient (D-03).

The widget is a pure stock-Qt6 QWidget: paintEvent draws the gradient + two
handles, mousePressEvent/mouseMoveEvent implement hit-test + drag. No
pyqtgraph. Mock-testable under QT_QPA_PLATFORM=offscreen via synthesized
QMouseEvent sequences.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")


def _make_bar(qtbot):
    from lightsheet.gui.panels.levels_bar import LevelsBar

    bar = LevelsBar()
    bar.resize(400, 40)
    qtbot.addWidget(bar)
    bar.show()
    qtbot.waitExposed(bar)
    return bar


def test_levels_bar_is_qwidget_subclass(qtbot) -> None:
    from PySide6.QtWidgets import QWidget

    bar = _make_bar(qtbot)
    assert isinstance(bar, QWidget)


def test_levels_bar_default_levels(qtbot) -> None:
    bar = _make_bar(qtbot)
    assert bar.levels_min == 0
    assert bar.levels_max == 2000


def test_levels_bar_has_sig_levels_changed(qtbot) -> None:
    bar = _make_bar(qtbot)
    # Signal must exist and accept (int, int)
    received: list[tuple[int, int]] = []
    bar.sig_levelsChanged.connect(lambda lo, hi: received.append((lo, hi)))
    bar.levels_min = 500
    assert (500, 2000) in received


def test_levels_bar_min_size_and_size_policy(qtbot) -> None:
    from PySide6.QtWidgets import QSizePolicy

    bar = _make_bar(qtbot)
    assert bar.minimumSize().width() >= 240
    assert bar.minimumSize().height() >= 32
    sp = bar.sizePolicy()
    assert sp.horizontalPolicy() == QSizePolicy.Policy.Expanding
    assert sp.verticalPolicy() == QSizePolicy.Policy.Fixed
    assert sp.horizontalStretch() == 1
    assert sp.verticalStretch() == 0


def _press_at(bar, x, y=20):
    """Synthesize a left-button press at widget-local coords (x, y)."""
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    pos = QPointF(float(x), float(y))
    evt = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        pos,
        pos,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    # QApplication.sendEvent dispatches directly to the widget.
    from PySide6.QtWidgets import QApplication

    QApplication.sendEvent(bar, evt)


def _move_to(bar, x, y=20):
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    pos = QPointF(float(x), float(y))
    evt = QMouseEvent(
        QEvent.Type.MouseMove,
        pos,
        pos,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    from PySide6.QtWidgets import QApplication

    QApplication.sendEvent(bar, evt)


def _release(bar):
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    pos = QPointF(0.0, 0.0)
    evt = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        pos,
        pos,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    from PySide6.QtWidgets import QApplication

    QApplication.sendEvent(bar, evt)


def test_drag_left_handle_updates_levels_min(qtbot) -> None:
    bar = _make_bar(qtbot)
    bar.levels_min = 0
    bar.levels_max = 2000
    received: list[tuple[int, int]] = []
    bar.sig_levelsChanged.connect(lambda lo, hi: received.append((lo, hi)))

    width = bar.width()
    # Left handle is at x = (levels_min / 2000) * width = 0.
    # Press on it, then drag to x = width/4 (which maps to value 500).
    _press_at(bar, 0)
    _move_to(bar, width // 4)
    _release(bar)

    assert bar.levels_min == 500, (
        f"expected levels_min=500 after drag, got {bar.levels_min}"
    )
    assert any(lo == 500 for (lo, _hi) in received)


def test_drag_right_handle_updates_levels_max(qtbot) -> None:
    bar = _make_bar(qtbot)
    bar.levels_min = 0
    bar.levels_max = 2000
    received: list[tuple[int, int]] = []
    bar.sig_levelsChanged.connect(lambda lo, hi: received.append((lo, hi)))

    width = bar.width()
    # Right handle is at x = width (value 2000).
    # Press on it, then drag left to x = width * 3/4 (value 1500).
    _press_at(bar, width - 1)
    _move_to(bar, (width * 3) // 4)
    _release(bar)

    assert bar.levels_max == 1500, (
        f"expected levels_max=1500 after drag, got {bar.levels_max}"
    )
    assert any(hi == 1500 for (_lo, hi) in received)


def test_click_far_from_handle_does_not_grab(qtbot) -> None:
    """A click 10px away from any handle does NOT grab (hit-test is ±8px)."""
    bar = _make_bar(qtbot)
    bar.levels_min = 0
    bar.levels_max = 2000

    width = bar.width()
    # Click at the middle of the bar (x = width/2, value 1000) — that's
    # far from both handles (which are at x=0 and x=width). Drag should
    # NOT move either handle.
    _press_at(bar, width // 2)
    _move_to(bar, width // 4)
    _release(bar)

    assert bar.levels_min == 0, (
        f"levels_min changed by a non-handle click: {bar.levels_min}"
    )
    assert bar.levels_max == 2000, (
        f"levels_max changed by a non-handle click: {bar.levels_max}"
    )


def test_no_pyqtgraph_import_in_levels_bar_module() -> None:
    """The levels bar must be stock-Qt6 only — no pyqtgraph dependency."""
    import inspect

    from lightsheet.gui.panels import levels_bar

    src = inspect.getsource(levels_bar)
    assert "pyqtgraph" not in src.lower(), (
        "levels_bar.py must not import or reference pyqtgraph"
    )
