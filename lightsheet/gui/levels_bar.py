"""LevelsBar(QWidget) — custom stock-Qt6 widget with two draggable handles
on a grayscale gradient.

The widget maps a 0-2000 levels window onto its full width: a black-to-white
QLinearGradient is painted as the background, and two handles (drawn as
filled circles) sit at the x positions corresponding to ``levels_min`` and
``levels_max``. The operator drags a handle to change the display window
applied to the ImageView (display clamp only — saved frames are raw uint16).

Implementation is intentionally stock-Qt6 only: ``paintEvent`` +
``mousePressEvent`` / ``mouseMoveEvent`` / ``mouseReleaseEvent`` +
``QColor`` / ``QPainter`` / ``QLinearGradient``. No third-party plotting
dependency.

Mock-testable under ``QT_QPA_PLATFORM=offscreen`` via synthesized
``QMouseEvent`` sequences asserting handle positions and underlying levels
values.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter
from PySide6.QtWidgets import QSizePolicy, QWidget

# Display levels window bounds. The 0-2000 range maps to the full gradient
# width; values outside the window saturate when the ImageView scales to
# uint8 for display. This is a DISPLAY clamp only — saved frames are the
# raw uint16.
LEVELS_MIN_BOUND = 0
LEVELS_MAX_BOUND = 2000
HANDLE_HIT_RADIUS_PX = 8


class LevelsBar(QWidget):
    """Stock-Qt6 levels adjuster with two draggable handles on a
    grayscale gradient."""

    sig_levelsChanged = Signal(int, int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._levels_min = LEVELS_MIN_BOUND
        self._levels_max = LEVELS_MAX_BOUND
        self._dragging_handle: str | None = None
        # Minimum 240x32 so the handles are grabbable; Expanding/Fixed with
        # horstretch=1 so the bar grows with the image pane and never grows
        # vertically.
        self.setMinimumSize(240, 32)
        sp = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sp.setHorizontalStretch(1)
        sp.setVerticalStretch(0)
        self.setSizePolicy(sp)

    # -- properties --------------------------------------------------------

    @property
    def levels_min(self) -> int:
        return self._levels_min

    @levels_min.setter
    def levels_min(self, value: int) -> None:
        v = int(max(LEVELS_MIN_BOUND, min(value, self._levels_max)))
        if v != self._levels_min:
            self._levels_min = v
            self.sig_levelsChanged.emit(self._levels_min, self._levels_max)
            self.update()

    @property
    def levels_max(self) -> int:
        return self._levels_max

    @levels_max.setter
    def levels_max(self, value: int) -> None:
        v = int(max(self._levels_min, min(value, LEVELS_MAX_BOUND)))
        if v != self._levels_max:
            self._levels_max = v
            self.sig_levelsChanged.emit(self._levels_min, self._levels_max)
            self.update()

    # -- coordinate mapping ------------------------------------------------

    def _value_to_x(self, value: int) -> int:
        width = max(1, self.width())
        span = LEVELS_MAX_BOUND - LEVELS_MIN_BOUND
        return int((value - LEVELS_MIN_BOUND) / span * width)

    def _x_to_value(self, x: int) -> int:
        width = max(1, self.width())
        span = LEVELS_MAX_BOUND - LEVELS_MIN_BOUND
        return int(x / width * span)

    # -- painting ----------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        width = self.width()
        height = self.height()

        # Grayscale gradient across the full widget width.
        gradient = QLinearGradient(0, 0, width, 0)
        gradient.setColorAt(0.0, QColor(0, 0, 0))
        gradient.setColorAt(1.0, QColor(255, 255, 255))
        painter.fillRect(0, 0, width, height, gradient)

        # Handle positions.
        x_min = self._value_to_x(self._levels_min)
        x_max = self._value_to_x(self._levels_max)
        cy = height // 2
        handle_radius = 7

        painter.setBrush(QColor(80, 80, 80))
        painter.setPen(QColor(20, 20, 20))
        painter.drawEllipse(x_min - handle_radius, cy - handle_radius,
                            handle_radius * 2, handle_radius * 2)
        painter.drawEllipse(x_max - handle_radius, cy - handle_radius,
                            handle_radius * 2, handle_radius * 2)

    # -- mouse interaction -------------------------------------------------

    def _hit_handle(self, x: int) -> str | None:
        x_min = self._value_to_x(self._levels_min)
        x_max = self._value_to_x(self._levels_max)
        # Prefer the closer handle when both are within the hit radius
        # (handles can be at the same x when levels_min == levels_max).
        d_min = abs(x - x_min)
        d_max = abs(x - x_max)
        if d_min <= HANDLE_HIT_RADIUS_PX and d_min <= d_max:
            return "min"
        if d_max <= HANDLE_HIT_RADIUS_PX:
            return "max"
        return None

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return
        handle = self._hit_handle(int(event.position().x()))
        if handle is None:
            event.ignore()
            return
        self._dragging_handle = handle
        event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if self._dragging_handle is None:
            event.ignore()
            return
        value = self._x_to_value(int(event.position().x()))
        if self._dragging_handle == "min":
            new_min = max(LEVELS_MIN_BOUND, min(value, self._levels_max))
            if new_min != self._levels_min:
                self._levels_min = new_min
                self.sig_levelsChanged.emit(self._levels_min, self._levels_max)
                self.update()
        else:  # "max"
            new_max = max(self._levels_min, min(value, LEVELS_MAX_BOUND))
            if new_max != self._levels_max:
                self._levels_max = new_max
                self.sig_levelsChanged.emit(self._levels_min, self._levels_max)
                self.update()
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt API name
        self._dragging_handle = None
        event.accept()
