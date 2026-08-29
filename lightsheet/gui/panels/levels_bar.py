"""LevelsBar(QWidget) — custom stock-Qt6 contrast widget with FIVE draggable
handles on a grayscale gradient.

The widget implements the ImageJ/napari window/level contrast pattern with
two slider sets and a central handle:

  - RANGE min/max handles follow the data (0-65535 for uint16, set via
    ``set_data_range``). The grayscale gradient spans this range.
  - WINDOW min/max handles sit within the range and define the display
    levels window (the ImageView clamps to these for display).
  - A central handle between the WINDOW handles drags both window setpoints
    together — preserving the window width and shifting the center, clamped
    so neither setpoint exits ``[range_min, range_max]``.

Implementation is intentionally stock-Qt6 only: ``paintEvent`` +
``mousePressEvent`` / ``mouseMoveEvent`` / ``mouseReleaseEvent`` +
``QColor`` / ``QPainter`` / ``QLinearGradient``. No third-party plotting
dependency.

The display clamp is applied to a COPY for display only — saved frames are
the raw uint16. The 0-2000 floor from the earlier single-handle widget is
gone; the range is data-following.

Mock-testable under ``QT_QPA_PLATFORM=offscreen`` via synthesized
``QMouseEvent`` sequences asserting handle positions and underlying
range/window values.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter
from PySide6.QtWidgets import QSizePolicy, QWidget

# Hit radius for every handle (px). A press within this many pixels of a
# handle's x position grabs that handle.
HANDLE_HIT_RADIUS_PX = 8

# Default data-following range for uint16 frames. ``set_data_range`` is the
# canonical way to update this from the live frame; this default just gives
# the widget a sane range before the first frame arrives.
DEFAULT_RANGE_MIN = 0
DEFAULT_RANGE_MAX = 65535


class LevelsBar(QWidget):
    """Stock-Qt6 levels adjuster with two slider sets + a central handle
    on a grayscale gradient.

    The RANGE set (``range_min``/``range_max``) follows the data and frames
    the grayscale gradient. The WINDOW set (``window_min``/``window_max``)
    sits within the range and defines the display levels window. The
    central handle drags both window setpoints together (preserves width,
    shifts center). ``levels_min``/``levels_max`` are read-only aliases for
    the window values (carried forward for the existing ImageView wiring).
    """

    sig_levelsChanged = Signal(int, int)  # window min, window max
    sig_rangeChanged = Signal(int, int)  # range min, range max

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._range_min = DEFAULT_RANGE_MIN
        self._range_max = DEFAULT_RANGE_MAX
        self._window_min = DEFAULT_RANGE_MIN
        self._window_max = DEFAULT_RANGE_MAX
        self._dragging_handle: str | None = None
        # Minimum 320x64 so all 5 handles + the central handle are
        # grabbable and the two slider rows have height. Expanding/Fixed
        # with horstretch=1 so the bar grows with the image pane and never
        # grows vertically.
        self.setMinimumSize(320, 64)
        sp = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sp.setHorizontalStretch(1)
        sp.setVerticalStretch(0)
        self.setSizePolicy(sp)

    # -- properties --------------------------------------------------------

    @property
    def range_min(self) -> int:
        return self._range_min

    @property
    def range_max(self) -> int:
        return self._range_max

    @property
    def window_min(self) -> int:
        return self._window_min

    @window_min.setter
    def window_min(self, value: int) -> None:
        v = int(max(self._range_min, min(value, self._window_max)))
        if v != self._window_min:
            self._window_min = v
            self.sig_levelsChanged.emit(self._window_min, self._window_max)
            self.update()

    @property
    def window_max(self) -> int:
        return self._window_max

    @window_max.setter
    def window_max(self, value: int) -> None:
        v = int(max(self._window_min, min(value, self._range_max)))
        if v != self._window_max:
            self._window_max = v
            self.sig_levelsChanged.emit(self._window_min, self._window_max)
            self.update()

    # Backward-compat aliases — the window values are the 07.1 "levels"
    # set, now subordinate to the range. The ImageView wiring consumes
    # these via sig_levelsChanged.
    @property
    def levels_min(self) -> int:
        return self._window_min

    @levels_min.setter
    def levels_min(self, value: int) -> None:
        self.window_min = value

    @property
    def levels_max(self) -> int:
        return self._window_max

    @levels_max.setter
    def levels_max(self, value: int) -> None:
        self.window_max = value

    # -- data-following range ---------------------------------------------

    def set_data_range(self, dmin: int, dmax: int) -> None:
        """Set the data-following range and clamp the window into it.

        Emits ``sig_rangeChanged`` with the new (range_min, range_max). If
        the window was clamped, ``sig_levelsChanged`` is also emitted so the
        ImageView's display window stays consistent with the new range.
        No-ops (no signal, no repaint) when the range is unchanged — callers
        invoke this on every incoming frame, and for a fixed dtype the range
        is constant, so the guard prevents redundant emissions and keeps the
        operator's RANGE handle adjustments stable across frames.
        """
        new_min = int(dmin)
        new_max = int(dmax)
        if new_max < new_min:
            new_min, new_max = new_max, new_min
        if new_min == self._range_min and new_max == self._range_max:
            return
        self._range_min = new_min
        self._range_max = new_max
        # Clamp the window into the new range.
        old_wmin, old_wmax = self._window_min, self._window_max
        self._window_min = max(new_min, min(self._window_min, new_max))
        self._window_max = max(self._window_min, min(self._window_max, new_max))
        self.sig_rangeChanged.emit(self._range_min, self._range_max)
        if (self._window_min, self._window_max) != (old_wmin, old_wmax):
            self.sig_levelsChanged.emit(self._window_min, self._window_max)
        self.update()

    # -- coordinate mapping ------------------------------------------------

    def _value_to_x(self, value: int) -> int:
        """Map a value in [range_min, range_max] to an x pixel in [0, width]."""
        width = max(1, self.width())
        span = max(1, self._range_max - self._range_min)
        return int((value - self._range_min) / span * width)

    def _x_to_value(self, x: int) -> int:
        """Map an x pixel in [0, width] to a value in [range_min, range_max]."""
        width = max(1, self.width())
        span = max(1, self._range_max - self._range_min)
        return int(self._range_min + x / width * span)

    # -- painting ----------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        width = self.width()
        height = self.height()

        # Grayscale gradient across the full widget width (the data range).
        gradient = QLinearGradient(0, 0, width, 0)
        gradient.setColorAt(0.0, QColor(0, 0, 0))
        gradient.setColorAt(1.0, QColor(255, 255, 255))
        painter.fillRect(0, 0, width, height, gradient)

        cy = height // 2
        handle_radius = 7

        # Handle x positions.
        x_rmin = self._value_to_x(self._range_min)
        x_rmax = self._value_to_x(self._range_max)
        x_wmin = self._value_to_x(self._window_min)
        x_wmax = self._value_to_x(self._window_max)
        x_center = (x_wmin + x_wmax) // 2

        # RANGE handles: dark gray filled circles, drawn first (outer).
        painter.setBrush(QColor(80, 80, 80))
        painter.setPen(QColor(20, 20, 20))
        painter.drawEllipse(
            x_rmin - handle_radius, cy - handle_radius,
            handle_radius * 2, handle_radius * 2,
        )
        painter.drawEllipse(
            x_rmax - handle_radius, cy - handle_radius,
            handle_radius * 2, handle_radius * 2,
        )

        # WINDOW handles: lighter gray with a distinct outline.
        painter.setBrush(QColor(180, 180, 180))
        painter.setPen(QColor(40, 40, 40))
        painter.drawEllipse(
            x_wmin - handle_radius, cy - handle_radius,
            handle_radius * 2, handle_radius * 2,
        )
        painter.drawEllipse(
            x_wmax - handle_radius, cy - handle_radius,
            handle_radius * 2, handle_radius * 2,
        )

        # Central handle: small accent square between the window handles.
        painter.setBrush(QColor(220, 120, 40))
        painter.setPen(QColor(60, 30, 0))
        half = handle_radius - 1
        painter.drawRect(x_center - half, cy - half, half * 2, half * 2)

    # -- mouse interaction -------------------------------------------------

    def _hit_handle(self, x: int) -> str | None:
        """Return the name of the handle within ±8px of x, or None.

        When two handles are within the hit radius, the closer one wins.
        Ties prefer the more-often-grabbed handle (window > center > range)
        so the operator can grab the window handles even when they coincide
        with the range handles (the default full-range state).
        """
        x_rmin = self._value_to_x(self._range_min)
        x_rmax = self._value_to_x(self._range_max)
        x_wmin = self._value_to_x(self._window_min)
        x_wmax = self._value_to_x(self._window_max)
        x_center = (x_wmin + x_wmax) // 2

        candidates = [
            (abs(x - x_wmin), "window_min"),
            (abs(x - x_wmax), "window_max"),
            (abs(x - x_center), "center"),
            (abs(x - x_rmin), "range_min"),
            (abs(x - x_rmax), "range_max"),
        ]
        # Filter to within hit radius, then pick the closest. The list
        # ordering above is the tiebreaker (window first).
        in_range = [(d, name) for (d, name) in candidates
                    if d <= HANDLE_HIT_RADIUS_PX]
        if not in_range:
            return None
        in_range.sort(key=lambda dn: dn[0])
        return in_range[0][1]

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
        h = self._dragging_handle

        if h == "range_min":
            new_min = min(value, self._range_max)
            if new_min != self._range_min:
                self._range_min = new_min
                # Clamp the window into the new range.
                old_wmin, old_wmax = self._window_min, self._window_max
                self._window_min = max(
                    self._range_min, min(self._window_min, self._range_max)
                )
                self._window_max = max(
                    self._window_min, min(self._window_max, self._range_max)
                )
                self.sig_rangeChanged.emit(self._range_min, self._range_max)
                if (self._window_min, self._window_max) != (old_wmin, old_wmax):
                    self.sig_levelsChanged.emit(
                        self._window_min, self._window_max
                    )
                self.update()
        elif h == "range_max":
            new_max = max(value, self._range_min)
            if new_max != self._range_max:
                self._range_max = new_max
                old_wmin, old_wmax = self._window_min, self._window_max
                self._window_min = max(
                    self._range_min, min(self._window_min, self._range_max)
                )
                self._window_max = max(
                    self._window_min, min(self._window_max, self._range_max)
                )
                self.sig_rangeChanged.emit(self._range_min, self._range_max)
                if (self._window_min, self._window_max) != (old_wmin, old_wmax):
                    self.sig_levelsChanged.emit(
                        self._window_min, self._window_max
                    )
                self.update()
        elif h == "window_min":
            if value > self._window_max:
                # Swap: the dragged handle becomes window_max.
                new_wmin = self._window_max
                new_wmax = min(value, self._range_max)
            else:
                new_wmin = max(self._range_min, min(value, self._window_max))
                new_wmax = self._window_max
            if (new_wmin, new_wmax) != (self._window_min, self._window_max):
                self._window_min = new_wmin
                self._window_max = new_wmax
                self.sig_levelsChanged.emit(
                    self._window_min, self._window_max
                )
                self.update()
        elif h == "window_max":
            if value < self._window_min:
                # Swap: the dragged handle becomes window_min.
                new_wmin = max(self._range_min, value)
                new_wmax = self._window_min
            else:
                new_wmin = self._window_min
                new_wmax = max(self._window_min, min(value, self._range_max))
            if (new_wmin, new_wmax) != (self._window_min, self._window_max):
                self._window_min = new_wmin
                self._window_max = new_wmax
                self.sig_levelsChanged.emit(
                    self._window_min, self._window_max
                )
                self.update()
        elif h == "center":
            # Preserve window width, shift both setpoints, clamp to range.
            half_width = (self._window_max - self._window_min) // 2
            new_min = value - half_width
            new_max = value + half_width
            if new_min < self._range_min:
                shift = self._range_min - new_min
                new_min += shift
                new_max += shift
            if new_max > self._range_max:
                shift = new_max - self._range_max
                new_min -= shift
                new_max -= shift
            if (new_min, new_max) != (self._window_min, self._window_max):
                self._window_min = new_min
                self._window_max = new_max
                self.sig_levelsChanged.emit(
                    self._window_min, self._window_max
                )
                self.update()
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt API name
        self._dragging_handle = None
        event.accept()
