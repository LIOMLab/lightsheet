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
the raw uint16. The 0-20000 floor from the earlier single-handle widget is
gone; the range is data-following.

Mock-testable under ``QT_QPA_PLATFORM=offscreen`` via synthesized
``QMouseEvent`` sequences asserting handle positions and underlying
range/window values.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import (
    QColor,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPaintEvent,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

from lightsheet.gui.styles import colors as _c

# Hit radius for every handle (px). A press within this many pixels of a
# handle's x position grabs that handle.
HANDLE_HIT_RADIUS_PX = 14
# Vertical hit zone for a handle row. The range row sits near the top
# (y=12) and the window row near the bottom (y=h-12). A click within
# this many pixels of a row's y grabs that row. Generous so the
# operator does not have to pixel-aim at a 10px-tall triangle, but kept
# at 10 so the hit zones ([2, 22] and [h-22, h-2]) do not overlap the
# gradient band ([22, h-22]) — a click inside the gradient grabs
# nothing, preventing an accidental range/window handle grab when the
# operator clicks the bar to look at it.
HANDLE_HIT_RADIUS_Y_PX = 10

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

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._range_min = DEFAULT_RANGE_MIN
        self._range_max = DEFAULT_RANGE_MAX
        self._window_min = DEFAULT_RANGE_MIN
        self._window_max = DEFAULT_RANGE_MAX
        self._dragging_handle: str | None = None
        # Once the operator drags a RANGE handle, the range is
        # user-owned: set_data_range (called per-frame from the
        # controller) must not reset it. Without this flag, the
        # per-frame set_data_range(0, 65535) would undo the drag.
        self._range_user_owned = False
        # The DATA bounds (dtype range, e.g. 0-65535 for uint16) frame
        # the coordinate mapping. The gradient spans this full range,
        # and the RANGE/WINDOW handles move freely within it. This is
        # distinct from the operator-adjustable RANGE set: the data
        # bounds are fixed by the dtype, so dragging a RANGE handle
        # inward moves the handle to a new x position (instead of
        # pinning it to the edge, which happens if the coordinate
        # mapping uses the RANGE set itself as the span).
        self._data_min = DEFAULT_RANGE_MIN
        self._data_max = DEFAULT_RANGE_MAX
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
        is constant, so the guard prevents redundant emissions.

        Once the operator has manually dragged a RANGE handle
        (``_range_user_owned``), this method no longer resets the range —
        the per-frame call would otherwise undo the operator's adjustment.
        The window is still clamped into the (now user-owned) range so a
        dtype change does not leave the window outside it.
        """
        new_min = int(dmin)
        new_max = int(dmax)
        if new_max < new_min:
            new_min, new_max = new_max, new_min
        # Always update the data bounds (the coordinate-mapping frame)
        # so the gradient and handle positions track the dtype range.
        self._data_min = new_min
        self._data_max = new_max
        if self._range_user_owned:
            # The operator owns the range, but a dtype change can narrow
            # the data bounds below the user-owned range (e.g. uint16 ->
            # uint8). _value_to_x maps handle positions against the data
            # bounds, so an unclamped range_max > data_max would draw the
            # handle off-screen. Clamp the range into the new data bounds
            # first, then clamp the window into the (now valid) range.
            old_rmin, old_rmax = self._range_min, self._range_max
            self._range_min = max(self._data_min, min(self._range_min, self._data_max))
            self._range_max = max(self._range_min, min(self._range_max, self._data_max))
            range_changed = (self._range_min, self._range_max) != (old_rmin, old_rmax)
            old_wmin, old_wmax = self._window_min, self._window_max
            self._window_min = max(
                self._range_min, min(self._window_min, self._range_max)
            )
            self._window_max = max(
                self._window_min, min(self._window_max, self._range_max)
            )
            window_changed = (self._window_min, self._window_max) != (
                old_wmin,
                old_wmax,
            )
            if range_changed:
                self.sig_rangeChanged.emit(self._range_min, self._range_max)
            if window_changed:
                self.sig_levelsChanged.emit(self._window_min, self._window_max)
            if range_changed or window_changed:
                self.update()
            return
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
        """Map a value in [data_min, data_max] to an x pixel in [0, width].

        The data bounds (dtype range) frame the coordinate mapping, NOT
        the operator-adjustable RANGE set. This is critical: if the
        mapping used the RANGE set as the span, range_max would always
        map to x=width and the handle would be pinned to the right edge
        — dragging it would never appear to move it. Using the fixed
        data bounds lets the RANGE handles move freely to any x position
        within the full data range.
        """
        width = max(1, self.width())
        span = max(1, self._data_max - self._data_min)
        return int((value - self._data_min) / span * width)

    def _x_to_value(self, x: int) -> int:
        """Map an x pixel in [0, width] to a value in [data_min, data_max]."""
        width = max(1, self.width())
        span = max(1, self._data_max - self._data_min)
        return int(self._data_min + x / width * span)

    # -- painting ----------------------------------------------------------

    def _row_y(self) -> tuple[int, int]:
        """Return the (range_row_y, window_row_y) pixel centers for the
        two handle rows. The RANGE handles sit above the gradient as
        downward-pointing triangles (apex touching the gradient top); the
        WINDOW handles + central handle sit below the gradient as
        upward-pointing triangles (apex touching the gradient bottom).
        The two rows are on opposite sides of the gradient so the handles
        never visually overlap when they coincide (the default full-range
        state has window == range, so all four handles share x positions)
        and each handle is visually attached to the bar via its triangle
        apex."""
        h = self.height()
        y_range = 12
        y_window = h - 12
        return y_range, y_window

    def _gradient_bounds(self) -> tuple[int, int]:
        """Return the (top, bottom) y pixels of the gradient band. The
        band sits between the two handle rows so the triangles point at it."""
        h = self.height()
        return 22, h - 22

    def paintEvent(self, event: QPaintEvent) -> None:
        from PySide6.QtCore import QPointF
        from PySide6.QtGui import QPolygonF

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        width = self.width()
        self.height()

        # Grayscale gradient band in the middle of the widget, between the
        # two handle rows. The RANGE triangles above point down at it; the
        # WINDOW triangles below point up at it — so every handle is
        # visually attached to the bar.
        g_top, g_bottom = self._gradient_bounds()
        gradient = QLinearGradient(0, 0, width, 0)
        gradient.setColorAt(0.0, _c.Q_GRADIENT_START)
        gradient.setColorAt(1.0, _c.Q_GRADIENT_END)
        painter.fillRect(0, g_top, width, g_bottom - g_top, gradient)

        _y_range, y_window = self._row_y()
        tri_half = 7  # half-width of the triangle base
        tri_h = 10  # triangle height (apex to base)

        # Handle x positions.
        x_rmin = self._value_to_x(self._range_min)
        x_rmax = self._value_to_x(self._range_max)
        x_wmin = self._value_to_x(self._window_min)
        x_wmax = self._value_to_x(self._window_max)
        x_center = (x_wmin + x_wmax) // 2

        # RANGE handles: dark gray downward-pointing triangles above the
        # gradient. Apex at (x, g_top) touches the gradient; base at
        # y = g_top - tri_h.
        painter.setBrush(_c.Q_RANGE_BRUSH)
        painter.setPen(_c.Q_RANGE_PEN)
        for x in (x_rmin, x_rmax):
            tri = QPolygonF(
                [
                    QPointF(x - tri_half, g_top - tri_h),
                    QPointF(x + tri_half, g_top - tri_h),
                    QPointF(float(x), float(g_top)),
                ]
            )
            painter.drawPolygon(tri)
            # Color-blind-safe dot marker on top of the dark triangle.
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(_c.BREEZE_FG))
            painter.drawEllipse(int(x) - 2, g_top - tri_h + 1, 4, 4)
            painter.setPen(_c.Q_RANGE_PEN)
            painter.setBrush(_c.Q_RANGE_BRUSH)

        # WINDOW handles: lighter gray upward-pointing triangles below the
        # gradient. Apex at (x, g_bottom) touches the gradient; base at
        # y = g_bottom + tri_h.
        painter.setBrush(_c.Q_WINDOW_BRUSH)
        painter.setPen(_c.Q_WINDOW_PEN)
        for x in (x_wmin, x_wmax):
            tri = QPolygonF(
                [
                    QPointF(x - tri_half, g_bottom + tri_h),
                    QPointF(x + tri_half, g_bottom + tri_h),
                    QPointF(float(x), float(g_bottom)),
                ]
            )
            painter.drawPolygon(tri)
            # Color-blind-safe diamond marker on top of the light triangle.
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(_c.BREEZE_BG))
            diamond = QPolygonF(
                [
                    QPointF(float(x), g_bottom + tri_h - 5),
                    QPointF(float(x) + 3, g_bottom + tri_h - 2),
                    QPointF(float(x), g_bottom + tri_h + 1),
                    QPointF(float(x) - 3, g_bottom + tri_h - 2),
                ]
            )
            painter.drawPolygon(diamond)
            painter.setPen(_c.Q_WINDOW_PEN)
            painter.setBrush(_c.Q_WINDOW_BRUSH)

        # Central handle: small neutral-gray square between the window
        # handles on the lower row. Uses a lighter neutral gray so it
        # reads as a distinct affordance without introducing a new accent
        # color.
        painter.setBrush(_c.Q_CENTER_BRUSH)
        painter.setPen(_c.Q_CENTER_PEN)
        half = tri_half - 1
        painter.drawRect(x_center - half, y_window - half, half * 2, half * 2)
        # Color-blind-safe dot in the center of the square.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(_c.BREEZE_FG))
        painter.drawEllipse(int(x_center) - 2, int(y_window) - 2, 4, 4)

    # -- mouse interaction -------------------------------------------------

    def _hit_handle(self, x: int, y: int | None = None) -> str | None:
        """Return the name of the handle within ±14px of (x, y), or None.

        The RANGE handles sit above the gradient (y near ``y_range``), the
        WINDOW + central handles below it (y near ``y_window``). When
        ``y`` is supplied, the click is assigned to the row whose y is
        closer — but only if the click is within the hit radius of that
        row's y. A click in the gradient band (between the rows) or far
        from both rows grabs nothing, so the operator cannot
        accidentally grab the wrong row's handle when both rows have a
        handle at the same x (the default full-range state). When two
        handles on the same row are within the hit radius, the closer
        one wins.
        """
        x_rmin = self._value_to_x(self._range_min)
        x_rmax = self._value_to_x(self._range_max)
        x_wmin = self._value_to_x(self._window_min)
        x_wmax = self._value_to_x(self._window_max)
        x_center = (x_wmin + x_wmax) // 2
        y_range, y_window = self._row_y()

        # Assign the click to a row only if the click's y is within the
        # hit radius of that row's y. A click in the gradient band
        # (equidistant from both rows, or closer to the band than to
        # either row) grabs nothing — this prevents grabbing the wrong
        # handle when both rows share an x position.
        upper_row = None
        if y is not None:
            d_range = abs(y - y_range)
            d_window = abs(y - y_window)
            if d_range <= HANDLE_HIT_RADIUS_Y_PX and d_range <= d_window:
                upper_row = "range"
            elif d_window <= HANDLE_HIT_RADIUS_Y_PX and d_window < d_range:
                upper_row = "window"
            else:
                return None
        else:
            upper_row = "range"

        candidates = [
            (abs(x - x_wmin), y_window, "window_min"),
            (abs(x - x_wmax), y_window, "window_max"),
            (abs(x - x_center), y_window, "center"),
            (abs(x - x_rmin), y_range, "range_min"),
            (abs(x - x_rmax), y_range, "range_max"),
        ]
        in_range = []
        for dx, cy, name in candidates:
            if dx > HANDLE_HIT_RADIUS_PX:
                continue
            if y is not None:
                cand_row = "range" if cy == y_range else "window"
                if cand_row != upper_row:
                    continue
            in_range.append((dx, name))
        if not in_range:
            return None
        in_range.sort(key=lambda dn: dn[0])
        return in_range[0][1]

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return
        handle = self._hit_handle(int(event.position().x()), int(event.position().y()))
        if handle is None:
            event.ignore()
            return
        self._dragging_handle = handle
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._dragging_handle is None:
            event.ignore()
            return
        value = self._x_to_value(int(event.position().x()))
        h = self._dragging_handle

        if h == "range_min":
            # Clamp to [data_min, range_max] so the handle stays within
            # the data bounds and cannot cross the range_max handle.
            new_min = max(self._data_min, min(value, self._range_max))
            if new_min != self._range_min:
                self._range_user_owned = True
                self._range_min = new_min
                # Do NOT clamp the window during the drag — clamping
                # makes the window handles jump, which reads as
                # "spazzing" when the operator is only dragging a range
                # handle. The window is clamped into the new range on
                # mouseReleaseEvent.
                self.sig_rangeChanged.emit(self._range_min, self._range_max)
                self.update()
        elif h == "range_max":
            # Clamp to [range_min, data_max] so the handle stays within
            # the data bounds and cannot cross the range_min handle.
            new_max = min(self._data_max, max(value, self._range_min))
            if new_max != self._range_max:
                self._range_user_owned = True
                self._range_max = new_max
                self.sig_rangeChanged.emit(self._range_min, self._range_max)
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
                self.sig_levelsChanged.emit(self._window_min, self._window_max)
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
                self.sig_levelsChanged.emit(self._window_min, self._window_max)
                self.update()
        elif h == "center":
            # Preserve window width, shift both setpoints, clamp to range.
            # Use the exact width (not // 2) so an odd-width window does
            # not silently shrink by 1 unit per drag: half_width is the
            # floor of width/2, and new_max is computed as new_min + width
            # so the full width survives the integer division.
            width = self._window_max - self._window_min
            half_width = width // 2
            new_min = value - half_width
            new_max = new_min + width
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
                self.sig_levelsChanged.emit(self._window_min, self._window_max)
                self.update()
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        # If a RANGE handle was dragged, clamp the window into the new
        # range now (deferred from mouseMoveEvent so the window handles
        # do not jump during the drag).
        if self._dragging_handle in ("range_min", "range_max"):
            old_wmin, old_wmax = self._window_min, self._window_max
            self._window_min = max(
                self._range_min, min(self._window_min, self._range_max)
            )
            self._window_max = max(
                self._window_min, min(self._window_max, self._range_max)
            )
            if (self._window_min, self._window_max) != (old_wmin, old_wmax):
                self.sig_levelsChanged.emit(self._window_min, self._window_max)
            self.update()
        self._dragging_handle = None
        event.accept()
