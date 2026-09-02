"""Dockable pyqtgraph trajectory widget for the adaptive exposure + laser
power control loop.

A ``QWidget`` containing a ``pyqtgraph.PlotWidget`` and a word-wrapped
empty-state ``QLabel``. The widget is GUI-thread-only — the ``StackWorker``
emits ``sig_adaptive_trajectory`` (a queued ``Signal``) and the shell's
GUI-thread slot calls ``append_sample``. The worker NEVER calls pyqtgraph
directly.

Plot layout:
- Left Y axis: intensity (% of max) + a target-band LinearRegionItem
  (accent blue at ~25% alpha, fixed — does not scroll).
- Right Y axis (linked ViewBox): exposure (ms) — Breeze midtone grey.
- Right-2 Y axis (linked ViewBox): L1/L2 power (mW) — amber.
- X axis: plane index. Beyond 200 planes the X view auto-scrolls.
- Re-acquire events: vertical dashed warning-olive lines.
- Power-fallback events: small amber triangles (power-family color;
  positioned on the exposure axis because their y-value is exposure,
  but their event semantics are power).

States: empty (label visible, plot hidden), populated (plot visible,
label hidden), frozen (further appends ignored).
"""

from __future__ import annotations

from typing import Any

import pyqtgraph as pg
from pyqtgraph.GraphicsScene.mouseEvents import MouseDragEvent
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

from lightsheet.gui.styles import colors as _c
from lightsheet.gui.styles import spacing as _s


def _make_axis_range_drag(ax: pg.AxisItem, vb: pg.ViewBox) -> None:
    """Override an AxisItem's mouseDragEvent so dragging the axis bar
    changes that axis's visible range (zoom) instead of panning. The
    range is anchored at 0 (the fixed point) so the scaling happens
    relative to the origin, not the click center — dragging down pulls
    higher numbers into view (natural "grab and pull" feel).

    pyqtgraph's default AxisItem drag forwards to
    ViewBox.mouseDragEvent(axis=1) which translates (pans) — this
    override scales the range instead. Only responds to drags that did
    NOT start inside the linked ViewBox (mirroring AxisItem's own guard)
    so body drags still pan.
    """
    def _range_drag(ev: MouseDragEvent) -> None:
        if vb.sceneBoundingRect().contains(ev.buttonDownScenePos()):
            ev.ignore()
            return
        if ev.button() != Qt.MouseButton.LeftButton:
            ev.ignore()
            return
        ev.accept()
        # Map the drag delta (in scene coords) to a range scale.
        # Vertical drag on a left/right axis scales Y; horizontal on
        # top/bottom scales X. Dragging down (negative dy) pulls higher
        # numbers into view (zoom out), dragging up zooms in.
        if ax.orientation in ("left", "right"):
            (x0, x1), (y0, y1) = vb.viewRange()
            span = y1 - y0
            if span <= 0:
                return
            # Qt scene Y increases downward. Dragging down (positive dy)
            # should pull higher numbers into view (zoom out), so the Y
            # sign is the opposite of X (where drag right zooms in).
            dy = ev.pos().y() - ev.lastPos().y()
            scale = 1.0 + (dy / 100.0)
            new_span = max(span * scale, span * 0.1)  # don't zoom in past 10x
            new_span = min(new_span, span * 10.0)  # don't zoom out past 0.1x
            # Anchor at 0: the new range is [0, new_span] so the origin
            # is the fixed point and everything scales relative to it.
            new_y0 = 0.0
            new_y1 = new_span
            vb.setRange(yRange=(new_y0, new_y1), padding=0.0)
        else:
            (x0, x1), (y0, y1) = vb.viewRange()
            span = x1 - x0
            if span <= 0:
                return
            dx = ev.pos().x() - ev.lastPos().x()
            # Drag right -> zoom out (higher numbers in view).
            scale = 1.0 - (dx / 100.0)
            new_span = max(span * scale, span * 0.1)
            new_span = min(new_span, span * 10.0)
            # Anchor at 0: [0, new_span].
            new_x0 = 0.0
            new_x1 = new_span
            vb.setRange(xRange=(new_x0, new_x1), padding=0.0)

    ax.mouseDragEvent = _range_drag  # ty: ignore[invalid-assignment]


def _clamp_view_range(
    vb: pg.ViewBox,
    data_x_max: float | None = None,
    data_x_span: float | None = None,
    y_max: float | None = None,
) -> None:
    """Clamp a ViewBox's view range so X/Y cannot go below 0, the X
    pan is limited to +10 planes beyond the acquired data, and the
    view span is bounded so the data cannot be completely scrolled or
    zoomed out of view.

    - X min >= 0, Y min >= 0.
    - X max <= data_x_max + 4 (no infinite forward pan).
    - View span <= 4x the data span on X (can't lose data).
    - Y max <= y_max if provided (e.g. intensity capped at 120%).

    ``data_x_max`` / ``data_x_span`` are passed in from the widget
    because the ViewBox's ``itemBoundingRect()`` includes the target
    band (a LinearRegionItem that spans the full ViewBox width), which
    would otherwise make the X bounds infinite.

    Only runs after a manual drag/zoom (from the drag/wheel guards).
    If the range is already valid (no clamping needed), do nothing —
    this preserves pyqtgraph's auto-range, which setRange would
    disable.
    """
    (x0, x1), (y0, y1) = vb.viewRange()
    needs_clamp = False
    # X: don't go below 0.
    if x0 < 0:
        x1 -= x0
        x0 = 0.0
        needs_clamp = True
    # Y: don't go below 0.
    if y0 < 0:
        y1 -= y0
        y0 = 0.0
        needs_clamp = True
    # X span: clamp to <= 4x the data span so the data stays at least
    # partially in view.
    if data_x_span is not None and data_x_span > 0:
        max_x_span = data_x_span * 4
        if (x1 - x0) > max_x_span:
            x1 = x0 + max_x_span
            needs_clamp = True
    # X max: limit forward pan to +4 planes beyond the acquired data
    # (no infinite X+ pan). Preserve the view span — shift the window
    # back so x1 hits the limit, instead of shrinking the span (which
    # would scale the X axis).
    if data_x_max is not None and x1 > data_x_max + 4:
        span = x1 - x0
        x1 = data_x_max + 4
        x0 = max(0.0, x1 - span)
        needs_clamp = True
    # Y max: cap if provided (e.g. intensity at 120%). Preserve the
    # view span — shift the window down so y1 hits the limit, instead
    # of shrinking the span (which would scale the Y axis).
    if y_max is not None and y1 > y_max:
        span = y1 - y0
        y1 = y_max
        y0 = max(0.0, y1 - span)
        needs_clamp = True
    if not needs_clamp:
        return  # range already valid — don't touch auto-range
    vb.setRange(xRange=(x0, x1), yRange=(y0, y1), padding=0.0)

# Breeze dark theme tokens imported from the shared color palette.
_BG = _c.BREEZE_BG
_FG = _c.BREEZE_FG
_ACCENT = _c.BREEZE_ACCENT
_EXPOSURE = _c.BREEZE_MIDTONE
_INFORMATION = _c.BREEZE_INFORMATION
_POWER2 = _c.BREEZE_POWER2
_WARNING = _c.BREEZE_WARNING
_TARGET = _c.BREEZE_ACCENT

# The exact empty-state copy.
EMPTY_COPY = (
    "No adaptive run yet. Enable Adaptive Control in the Stack panel "
    "and start a stack to see the per-plane intensity trajectory."
)

# Sliding X-axis window: show the last N planes, retain all in memory.
_X_WINDOW = 200


class AdaptiveTrajectoryWidget(QWidget):
    """Dockable pyqtgraph trajectory widget for the adaptive loop.

    GUI-thread-only. The worker emits ``sig_adaptive_trajectory`` and
    the shell's GUI-thread slot calls ``append_sample``.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._frozen = False
        self._target_band_lo = 0.90
        self._target_band_hi = 0.95
        self._target_band_label = "Target band 90-95 %"
        self._run_started = False  # reset() called for current run

        layout = QVBoxLayout(self)
        layout.setContentsMargins(_s.LG, _s.LG, _s.LG, _s.LG)
        layout.setSpacing(_s.SM)

        # Empty-state label: word-wrapped so the fixed English sentence
        # wraps without clipping at the dock's minimum width.
        self.label_adaptiveTrajectoryEmpty = QLabel(EMPTY_COPY, self)
        self.label_adaptiveTrajectoryEmpty.setWordWrap(True)
        self.label_adaptiveTrajectoryEmpty.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        self.label_adaptiveTrajectoryEmpty.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )
        layout.addWidget(self.label_adaptiveTrajectoryEmpty)

        # Curves / markers — created ONCE in _configure_plot() and reused
        # across resets. reset() only clears their data (setData([], [])).
        # Recreating curves per reset() caused duplicates: item.clear()
        # removes main-ViewBox items but the right-ViewBox curves survived
        # the addedItems removal loop, stacking a new curve per run.
        # Initialized to None BEFORE _configure_plot() so the right
        # ViewBox assignment in _configure_plot() is not overwritten.
        self._intensity_curve: pg.PlotDataItem | None = None
        self._exposure_curve: pg.PlotDataItem | None = None
        self._power_curve: pg.PlotDataItem | None = None
        self._power2_curve: pg.PlotDataItem | None = None
        self._target_band: pg.LinearRegionItem | None = None
        self._reacquire_lines: list[pg.InfiniteLine] = []
        self._power_fallback_scatter: pg.ScatterPlotItem | None = None
        self._right_vb: pg.ViewBox | None = None  # exposure axis
        self._power_vb: pg.ViewBox | None = None  # power axis (third Y)
        self._power_l1_visible = True
        self._power_l2_visible = True
        self._legend: pg.LegendItem | None = None

        # PlotWidget — the only pyqtgraph surface in this widget.
        # The widget background is _BG (set via stylesheet) so the dark
        # plot area extends across the whole widget, covering the axes
        # and labels with a uniform dark background. The ViewBox
        # background is set to None (transparent) so the widget
        # background shows through; the ViewBox contents margins inset
        # the data area so labels have padding around them.
        self.plotWidget_adaptiveTrajectory = pg.PlotWidget(self)
        self.plotWidget_adaptiveTrajectory.setStyleSheet(
            f"PlotWidget {{ background-color: {_BG}; }}"
        )
        self.plotWidget_adaptiveTrajectory.setBackground(None)
        self._configure_plot()
        self.plotWidget_adaptiveTrajectory.hide()
        layout.addWidget(self.plotWidget_adaptiveTrajectory)

        # In-memory data buffers (retained for zoom-out beyond the
        # sliding X window).
        self._xs: list[float] = []
        self._intensity: list[float] = []
        self._exposure: list[float] = []
        self._power: list[float] = []
        self._power2: list[float] = []

    def _configure_plot(self) -> None:
        """Set axis pens/text, labels, downsampling, and the three Y
        axes: left (intensity), right-1 (exposure), right-2 (power).
        Each axis is color-coded to its curve(s) so the operator can
        see at a glance which Y axis belongs to which data."""
        item = self.plotWidget_adaptiveTrajectory.getPlotItem()
        # Left axis (intensity) — blue, matching the intensity curve.
        left_ax = item.getAxis("left")
        left_ax.setPen(_ACCENT)
        left_ax.setTextPen(_ACCENT)
        bottom_ax = item.getAxis("bottom")
        bottom_ax.setPen(_FG)
        bottom_ax.setTextPen(_FG)
        item.setLabel("left", "Intensity (% of max)", color=_ACCENT)
        item.setLabel("bottom", "Plane")
        # Right-1 axis (exposure) — grey ViewBox + axis (Breeze midtone
        # grey, not green — green is reserved for laser ● ON status).
        # Exposure is the acquisition path; it is physically decoupled
        # from power (illumination), so it gets its own axis.
        self._right_vb = pg.ViewBox()
        item.scene().addItem(self._right_vb)
        right_ax = pg.AxisItem("right")
        right_ax.setPen(_EXPOSURE)
        right_ax.setTextPen(_EXPOSURE)
        right_ax.linkToView(self._right_vb)
        item.layout.addItem(right_ax, 2, 3)
        self._right_vb.setXLink(item.getViewBox())
        right_ax.setLabel("Exposure (ms)", color=_EXPOSURE)
        # Right-2 axis (power) — amber ViewBox + axis, two columns
        # further right (column 5). Column 4 is a fixed-width gap (20px)
        # so the two right axes have visible padding between them.
        # L1 (amber) + L2 (lighter amber) share this axis. Amber is the
        # operator-approved power-family color — information blue clashed
        # with the accent-blue intensity curve, so amber groups the
        # entire power family (axis + L1 + L2 + fallback triangles)
        # under one visually distinct color.
        self._power_vb = pg.ViewBox()
        item.scene().addItem(self._power_vb)
        power_ax = pg.AxisItem("right")
        power_ax.setPen(_INFORMATION)
        power_ax.setTextPen(_INFORMATION)
        power_ax.linkToView(self._power_vb)
        item.layout.addItem(power_ax, 2, 5)
        item.layout.setColumnFixedWidth(4, 20)
        self._power_vb.setXLink(item.getViewBox())
        power_ax.setLabel("Power (mW)", color=_INFORMATION)
        # Geometry sync: without this the right ViewBoxes stay at their
        # default tiny positions instead of overlaying the main plot.
        # The main ViewBox's sigResized fires on every layout pass;
        # mirror its scene rect onto both right ViewBoxes so the three
        # axes stay coincident.
        main_vb = item.getViewBox()
        # Inset the whole PlotItem layout (axes + ViewBox) from the
        # widget edges so the dark widget background shows as padding
        # around the axes/labels on all sides (16 px = md spacing token).
        item.layout.setContentsMargins(16, 16, 16, 16)

        def _sync_right_vbs() -> None:
            if self._right_vb is not None:
                self._right_vb.setGeometry(main_vb.sceneBoundingRect())
                self._right_vb.linkedViewChanged(main_vb, self._right_vb.XAxis)
            if self._power_vb is not None:
                self._power_vb.setGeometry(main_vb.sceneBoundingRect())
                self._power_vb.linkedViewChanged(main_vb, self._power_vb.XAxis)

        main_vb.sigResized.connect(_sync_right_vbs)
        # Mouse: panning enabled on both axes (so dragging an axis bar
        # pans that axis), but body-initiated drags are ignored — the
        # AxisItem.mouseDragEvent only forwards when the drag did NOT
        # start inside the ViewBox. Override both ViewBoxes' mouseDragEvent
        # to reject drags that start in the plot body and to clamp the
        # resulting range so X/Y cannot go below 0 and the data cannot be
        # completely scrolled out of view. Scroll-wheel zoom disabled.
        main_vb.setMouseEnabled(x=True, y=True)
        if self._right_vb is not None:
            self._right_vb.setMouseEnabled(x=True, y=True)
        if self._power_vb is not None:
            self._power_vb.setMouseEnabled(x=True, y=True)
        main_vb.setMenuEnabled(False)
        # Intensity Y axis (left): fixed [0, 120] range — intensity is
        # a percentage with the target band at 90-95%; 120% gives
        # headroom for overshoot without wasting space. Y auto-range is
        # disabled so the axis stays fixed; X auto-range stays on for
        # auto-scroll. Range is [0, 125] so the 120 tick label is not
        # clipped at the top edge (the clamp caps panning at 120).
        main_vb.enableAutoRange(axis="y", enable=False)
        main_vb.setYRange(0, 125, padding=0.0)
        # Exposure + power Y axes: auto-scale so the operator sees the
        # actual exposure/power range. X auto-range is enabled too so
        # the plot auto-scrolls as planes are appended; the sliding
        # window in append_sample takes over beyond _X_WINDOW planes.
        if self._right_vb is not None:
            self._right_vb.enableAutoRange(axis="y", enable=True)
        if self._power_vb is not None:
            self._power_vb.enableAutoRange(axis="y", enable=True)
        if self._right_vb is not None:
            self._right_vb.setAutoVisible(y=True)
        if self._power_vb is not None:
            self._power_vb.setAutoVisible(y=True)
        # Y padding on the auto-scaled axes so the data doesn't touch
        # the top/bottom edges.
        if self._right_vb is not None:
            self._right_vb.setDefaultPadding(0.1)
        if self._power_vb is not None:
            self._power_vb.setDefaultPadding(0.1)

        def _data_bounds() -> tuple[float | None, float | None]:
            """Return (data_x_max, data_x_span) from the acquired
            samples, or (None, None) if no data yet. The ViewBox's
            itemBoundingRect() includes the target band which spans
            the full width, so we use the actual sample data instead."""
            if not self._xs:
                return None, None
            x_max = max(self._xs)
            x_min = min(self._xs)
            return x_max, max(1.0, x_max - x_min)

        def _make_drag_guard(vb: pg.ViewBox, y_max: float | None = None) -> Any:
            """Build a mouseDragEvent override for a ViewBox that wraps
            the original handler and clamps the resulting range after a
            pan/range-change so X/Y cannot go below 0 and the data stays
            at least partially in view. Body drags pan (scroll the
            visible window); axis-bar drags change that axis's range
            (pyqtgraph's AxisItem forwards with the axis param). Both
            go through the same clamp afterward.
            """
            orig = vb.mouseDragEvent

            def _guarded(ev: MouseDragEvent, axis: int | None = None) -> None:
                orig(ev, axis)
                dx_max, dx_span = _data_bounds()
                _clamp_view_range(vb, data_x_max=dx_max, data_x_span=dx_span,
                                  y_max=y_max)

            return _guarded

        # Intensity Y capped at 120%; exposure/power axes uncapped.
        main_vb.mouseDragEvent = _make_drag_guard(main_vb, y_max=120.0)
        if self._right_vb is not None:
            self._right_vb.mouseDragEvent = _make_drag_guard(self._right_vb)
        if self._power_vb is not None:
            self._power_vb.mouseDragEvent = _make_drag_guard(self._power_vb)

        def _make_wheel_guard(vb: pg.ViewBox, y_max: float | None = None) -> Any:
            """Wrap the ViewBox wheelEvent so scroll-wheel zoom is also
            clamped to the same bounds as drag (X/Y >= 0, X max limited,
            span bounded, Y capped)."""
            orig = vb.wheelEvent

            def _guarded(ev: Any, axis: int | None = None) -> None:
                # axis kwarg comes from AxisItem.wheelEvent forwarding.
                orig(ev)
                dx_max, dx_span = _data_bounds()
                _clamp_view_range(vb, data_x_max=dx_max, data_x_span=dx_span,
                                  y_max=y_max)

            return _guarded

        main_vb.wheelEvent = _make_wheel_guard(main_vb, y_max=120.0)
        if self._right_vb is not None:
            self._right_vb.wheelEvent = _make_wheel_guard(self._right_vb)
        if self._power_vb is not None:
            self._power_vb.wheelEvent = _make_wheel_guard(self._power_vb)
        # Axis-bar drags change that axis's range (zoom), not pan. The
        # default AxisItem drag forwards to ViewBox.mouseDragEvent which
        # translates; this override scales the range instead. Body drags
        # still pan (the override ignores drags that start in the ViewBox).
        _make_axis_range_drag(left_ax, main_vb)
        _make_axis_range_drag(bottom_ax, main_vb)
        if self._right_vb is not None:
            _make_axis_range_drag(right_ax, self._right_vb)
        if self._power_vb is not None:
            _make_axis_range_drag(power_ax, self._power_vb)
        # All curves, the target band, the fallback scatter, and the
        # legend are created ONCE here and reused across resets. reset()
        # only clears their data — it does not destroy or recreate them.
        # This avoids the duplicate-curve bug where item.clear() removed
        # main-ViewBox items but the right-ViewBox curves survived the
        # addedItems removal loop, stacking a new curve per run.
        # Target band: LinearRegionItem spanning lo..hi % on the Y axis
        # (intensity %), blue tint at ~20% alpha (intensity family,
        # fixed — does not scroll). orientation='horizontal' so it
        # spans Y=lo..hi, NOT X=lo..hi (the default 'vertical' would
        # cover the plane area). Region updated in reset() via
        # setRegion, not recreated.
        self._target_band = pg.LinearRegionItem(
            [90.0, 95.0],
            orientation="horizontal",
            brush=pg.mkBrush(*_c.BREEZE_ACCENT_RGBA),
            movable=False,
        )
        self._target_band.lines[0].setPen(pg.mkPen(_TARGET, width=1))
        self._target_band.lines[1].setPen(pg.mkPen(_TARGET, width=1))
        item.addItem(self._target_band)
        # Intensity curve (left axis, accent blue).
        self._intensity_curve = pg.PlotDataItem(
            [], [], pen=pg.mkPen(_ACCENT, width=2), name="Intensity"
        )
        item.addItem(self._intensity_curve)
        # Exposure curve on the right-1 ViewBox (grey, dashed) — the
        # acquisition path, decoupled from power (illumination).
        if self._right_vb is not None:
            self._exposure_curve = pg.PlotDataItem(
                [], [],
                pen=pg.mkPen(_EXPOSURE, width=1, style=Qt.PenStyle.DashLine),
                name="Exposure",
            )
            self._right_vb.addItem(self._exposure_curve)
        # L1/L2 power curves on the right-2 ViewBox (power axis).
        # L1 = amber, L2 = lighter amber, matching the power axis pen.
        if self._power_vb is not None:
            self._power_curve = pg.PlotDataItem(
                [], [], pen=pg.mkPen(_INFORMATION, width=1), name="Power L1"
            )
            self._power_vb.addItem(self._power_curve)
            self._power2_curve = pg.PlotDataItem(
                [], [], pen=pg.mkPen(_POWER2, width=1), name="Power L2"
            )
            self._power_vb.addItem(self._power2_curve)
        # Power-fallback scatter on the exposure ViewBox — its y-value
        # is exposure in ms, so it shares the exposure axis, not the
        # power or intensity axis. Its pen/brush use the amber
        # power-family color (not grey) because the event semantics are
        # power, even though the marker is positioned on the exposure
        # axis.
        self._power_fallback_scatter = pg.ScatterPlotItem(
            symbol="t",
            size=10,
            pen=pg.mkPen(_INFORMATION),
            brush=pg.mkBrush(_INFORMATION),
            name="Power fallback",
        )
        if self._right_vb is not None:
            self._right_vb.addItem(self._power_fallback_scatter)
        else:
            item.addItem(self._power_fallback_scatter)
        # Legend sample items for the target band and re-acquire marker.
        # These are NOT added to any ViewBox — they are off-screen dummy
        # PlotDataItems whose only purpose is to render a colored line
        # sample in the legend. Adding the real LinearRegionItem /
        # InfiniteLine to the legend crashed pyqtgraph's sample painter
        # (those are not curve-like items); dummy curves with the right
        # pen are the safe way to label them.
        self._target_band_legend_sample = pg.PlotDataItem(
            [], [], pen=pg.mkPen(_TARGET, width=1),
        )
        self._reacquire_legend_sample = pg.PlotDataItem(
            [], [],
            pen=pg.mkPen(_WARNING, style=Qt.PenStyle.DashLine, width=1),
        )
        # Legend parented to the main ViewBox so the offset is in view
        # pixels and it anchors to the plot area, not the PlotItem layout
        # (parenting to the PlotItem let the layout place it over the
        # left axis at a data-y around 1000). High z-value keeps it
        # above the curves. Populated once; survives resets.
        self._legend = pg.LegendItem(
            (180, 120),
            offset=(10, 10),
            labelTextColor=_FG,
            brush=pg.mkBrush(29, 32, 35, 200),
        )
        self._legend.setParentItem(main_vb)
        self._legend.setZValue(1000)
        # Populate the legend once in the canonical colour-grouped
        # order. _rebuild_legend (called from reset() and
        # set_power_visible) re-runs this whenever the laser state or
        # target band changes, so the order stays stable across runs.
        self._rebuild_legend()
        self._legend.hide()
        # X auto-range enabled so the plot auto-scrolls as planes are
        # appended — the operator sees the trajectory grow live. The
        # sliding window in append_sample takes over beyond _X_WINDOW
        # planes to keep long stacks readable (last N planes).
        item.getViewBox().enableAutoRange(axis="x", enable=True)

    def reset(
        self,
        target_band_lo: float = 0.90,
        target_band_hi: float = 0.95,
    ) -> None:
        """Reset the plot for a new run with the given target band
        (fractions 0..1). Clears all curve/scatter data and removes
        reacquire markers; the curve objects themselves are reused
        (created once in _configure_plot). X auto-range handles the
        initial and live range."""
        self._frozen = False
        self._run_started = True
        self._target_band_lo = target_band_lo
        self._target_band_hi = target_band_hi
        self._xs = []
        self._intensity = []
        self._exposure = []
        self._power = []
        self._power2 = []
        # Remove old re-acquire marker lines from the plot item.
        item = self.plotWidget_adaptiveTrajectory.getPlotItem()
        for line in self._reacquire_lines:
            item.removeItem(line)
        self._reacquire_lines = []
        # Clear curve data (curve objects are reused, not recreated).
        if self._intensity_curve is not None:
            self._intensity_curve.setData([], [])
        if self._exposure_curve is not None:
            self._exposure_curve.setData([], [])
        if self._power_curve is not None:
            self._power_curve.setData([], [])
        if self._power2_curve is not None:
            self._power2_curve.setData([], [])
        if self._power_fallback_scatter is not None:
            self._power_fallback_scatter.setData([], [])
        # Update the target band region to the new bounds.
        if self._target_band is not None:
            self._target_band.setRegion(
                [target_band_lo * 100.0, target_band_hi * 100.0]
            )
        # Update the target band legend label with the actual bounds
        # (spec: "Target band {lo}-{hi} %"), then rebuild the whole
        # legend so entries stay in the canonical colour-grouped order.
        self._target_band_label = (
            f"Target band {target_band_lo * 100:.0f}-"
            f"{target_band_hi * 100:.0f} %"
        )
        self._rebuild_legend()
        # X auto-range (enabled in _configure_plot) handles the initial
        # and live range — no manual setXRange here, it would fight the
        # auto-range. The sliding window in append_sample takes over
        # beyond _X_WINDOW planes to keep long stacks readable.
        # Show the plot + legend, hide the empty label.
        self.plotWidget_adaptiveTrajectory.show()
        if self._legend is not None:
            self._legend.show()
        self.label_adaptiveTrajectoryEmpty.hide()

    def set_empty(self) -> None:
        """Show the empty-state label and hide the plot (no run yet).
        Clears all buffered data so the plot starts fresh."""
        self._frozen = False
        self._run_started = False
        self._xs = []
        self._intensity = []
        self._exposure = []
        self._power = []
        self._power2 = []
        self._reacquire_lines = []
        self.plotWidget_adaptiveTrajectory.hide()
        if self._legend is not None:
            self._legend.hide()
        self.label_adaptiveTrajectoryEmpty.show()

    def has_data(self) -> bool:
        """Return True if the widget has acquired samples to display
        (i.e. a run is in progress or has finished). Used by the rail
        button to decide whether to restore the existing plot or show
        the empty state when reopening the dock."""
        return len(self._xs) > 0

    def show_plot(self) -> None:
        """Show the plot + legend and hide the empty-state label,
        WITHOUT clearing data. Used when reopening the dock via the
        rail button to restore a previously rendered trajectory."""
        self.plotWidget_adaptiveTrajectory.show()
        if self._legend is not None:
            self._legend.show()
        self.label_adaptiveTrajectoryEmpty.hide()

    def set_power_visible(self, l1: bool, l2: bool) -> None:
        """Show/hide the per-laser power curves + legend entries based on
        whether each laser is under automatic control. A laser that is not
        in auto mode is not driven by the adaptive loop, so plotting its
        computed power would be misleading."""
        self._power_l1_visible = l1
        self._power_l2_visible = l2
        if self._power_curve is not None:
            self._power_curve.setVisible(l1)
        if self._power2_curve is not None:
            self._power2_curve.setVisible(l2)
        self._rebuild_legend()

    def _rebuild_legend(self) -> None:
        """Clear and re-add all legend entries in the canonical
        colour-grouped order: blue (Target band, Intensity), grey
        (Exposure), amber (Power fallback, Power L1, Power L2),
        warning-olive (Re-acquire). Power L1/L2 are only added when
        their laser is under automatic control. LegendItem renders the
        first-added item at the top, so add in visual top-to-bottom
        order."""
        if self._legend is None:
            return
        # Remove all existing entries. removeItem takes the original
        # graphics item (the curve/scatter/legend-sample), not the
        # ItemSample wrapper stored in legend.items.
        for item in (
            self._target_band_legend_sample,
            self._intensity_curve,
            self._exposure_curve,
            self._power_fallback_scatter,
            self._power_curve,
            self._power2_curve,
            self._reacquire_legend_sample,
        ):
            if item is not None:
                self._legend.removeItem(item)
        # Re-add in canonical order.
        if self._target_band_legend_sample is not None:
            self._legend.addItem(
                self._target_band_legend_sample, self._target_band_label
            )
        if self._intensity_curve is not None:
            self._legend.addItem(self._intensity_curve, "Intensity")
        if self._exposure_curve is not None:
            self._legend.addItem(self._exposure_curve, "Exposure")
        if self._power_fallback_scatter is not None:
            self._legend.addItem(self._power_fallback_scatter, "Power fallback")
        if self._power_l1_visible and self._power_curve is not None:
            self._legend.addItem(self._power_curve, "Power L1")
        if self._power_l2_visible and self._power2_curve is not None:
            self._legend.addItem(self._power2_curve, "Power L2")
        if self._reacquire_legend_sample is not None:
            self._legend.addItem(self._reacquire_legend_sample, "Re-acquire")

    def append_sample(
        self,
        plane_idx: int,
        intensity: float,
        exposure_s: float,
        power1_mw: float,
        power2_mw: float,
        control_variable_active: str,
        reacquired: bool,
        power_fallback: bool,
    ) -> None:
        """Append one per-plane sample to the trajectory. GUI-thread only.

        Ignored after ``freeze()`` so the last trajectory is preserved
        for review (E-stop / abort).
        """
        if self._frozen:
            return
        if not self._run_started:
            # First sample of a run without an explicit reset() — reset
            # with default band so the plot initializes (curves already
            # exist from _configure_plot; reset clears their data and
            # shows the plot). Using _run_started rather than plot
            # isVisible() because the latter is unreliable in offscreen
            # Qt environments (returns False even after show()).
            self.reset()
        self._xs.append(float(plane_idx))
        self._intensity.append(intensity * 100.0)  # fraction -> %
        self._exposure.append(exposure_s * 1000.0)  # s -> ms
        self._power.append(power1_mw)
        self._power2.append(power2_mw)
        assert self._intensity_curve is not None
        self._intensity_curve.setData(self._xs, self._intensity)
        if self._exposure_curve is not None:
            self._exposure_curve.setData(self._xs, self._exposure)
        if self._power_curve is not None:
            self._power_curve.setData(self._xs, self._power)
        if self._power2_curve is not None:
            self._power2_curve.setData(self._xs, self._power2)
        # Re-acquire marker: vertical dashed warning line.
        if reacquired:
            line = pg.InfiniteLine(
                pos=float(plane_idx),
                angle=90,
                pen=pg.mkPen(_WARNING, style=Qt.PenStyle.DashLine, width=1),
            )
            self.plotWidget_adaptiveTrajectory.getPlotItem().addItem(line)
            self._reacquire_lines.append(line)
        # Power-fallback marker: amber triangle (power-family color).
        if power_fallback and self._power_fallback_scatter is not None:
            spots = self._power_fallback_scatter.getData()
            existing_x = list(spots[0]) if spots is not None else []
            existing_y = list(spots[1]) if spots is not None else []
            # Place the triangle at the exposure value on the right axis
            # so it lines up with the exposure/power curve.
            existing_x.append(float(plane_idx))
            existing_y.append(exposure_s * 1000.0)
            self._power_fallback_scatter.setData(existing_x, existing_y)
        # Sliding X window: show the last _X_WINDOW planes, retain all
        # in-memory data for zoom-out.
        if len(self._xs) > _X_WINDOW:
            x_min = self._xs[-_X_WINDOW]
            x_max = self._xs[-1] + 1
            self.plotWidget_adaptiveTrajectory.getPlotItem().getViewBox().setXRange(
                x_min, x_max, padding=0.0
            )

    def freeze(self) -> None:
        """Freeze the plot — further append_sample calls are ignored so
        the last trajectory is preserved for review (E-stop / abort)."""
        self._frozen = True
