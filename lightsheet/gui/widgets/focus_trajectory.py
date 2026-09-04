"""Dockable pyqtgraph trajectory widget for the camera focus
compensation loop.

A ``QWidget`` containing a ``pyqtgraph.PlotWidget`` and a word-wrapped
empty-state ``QLabel``. The widget is GUI-thread-only — the ``StackWorker``
emits ``sig_focus_trajectory`` (a queued ``Signal``) and the shell's
GUI-thread slot calls ``append_sample``. The worker NEVER calls pyqtgraph
directly.

Plot layout:
- Left Y axis: camera position (mm) — accent blue.
- Right Y axis (linked ViewBox): horizontal stage position (mm) —
  Breeze midtone grey.
- X axis: block index ("Block").
- Residual markers: warning-olive diamonds at blocks where a non-zero
  residual was applied.

States: empty (label visible, plot hidden), populated (plot visible,
label hidden), frozen (further appends ignored).
"""

from __future__ import annotations

from typing import Any, cast

import pyqtgraph as pg
from pyqtgraph.GraphicsScene.mouseEvents import MouseDragEvent
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

from lightsheet.gui.styles import colors as _c
from lightsheet.gui.styles import spacing as _s
from lightsheet.gui.widgets.adaptive_trajectory import (
    _clamp_view_range,
    _make_axis_range_drag,
)

# Breeze dark theme tokens imported from the shared color palette.
_BG = _c.BREEZE_BG
_FG = _c.BREEZE_FG
_ACCENT = _c.BREEZE_ACCENT
_MIDTONE = _c.BREEZE_MIDTONE
_WARNING = _c.BREEZE_WARNING

# The exact empty-state copy.
EMPTY_COPY = (
    "No focus run yet. Enable Camera focus compensation in the Stack panel, "
    "load a calibration file, and start a stack to see the focus trajectory."
)

# Sliding X-axis window: show the last N blocks, retain all in memory.
_X_WINDOW = 200


class FocusTrajectoryWidget(QWidget):
    """Dockable pyqtgraph trajectory widget for the focus loop.

    GUI-thread-only. The worker emits ``sig_focus_trajectory`` and the
    shell's GUI-thread slot calls ``append_sample``.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._frozen = False
        self._run_started = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(_s.LG, _s.LG, _s.LG, _s.LG)
        layout.setSpacing(_s.SM)

        # Empty-state label: word-wrapped so the fixed English sentence
        # wraps without clipping at the dock's minimum width.
        self.label_focusTrajectoryEmpty = QLabel(EMPTY_COPY, self)
        self.label_focusTrajectoryEmpty.setWordWrap(True)
        self.label_focusTrajectoryEmpty.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        self.label_focusTrajectoryEmpty.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )
        layout.addWidget(self.label_focusTrajectoryEmpty)

        # Curves / markers — created ONCE in _configure_plot() and reused
        # across resets. reset() only clears their data.
        self._camera_curve: pg.PlotDataItem | None = None
        self._stage_curve: pg.PlotDataItem | None = None
        self._residual_scatter: pg.ScatterPlotItem | None = None
        self._right_vb: pg.ViewBox | None = None
        self._legend: pg.LegendItem | None = None

        # PlotWidget — the only pyqtgraph surface in this widget.
        self.plotWidget_focusTrajectory = pg.PlotWidget(self)
        self.plotWidget_focusTrajectory.setStyleSheet(
            f"PlotWidget {{ background-color: {_BG}; }}"
        )
        self.plotWidget_focusTrajectory.setBackground(None)
        self._configure_plot()
        self.plotWidget_focusTrajectory.hide()
        layout.addWidget(self.plotWidget_focusTrajectory)

        # In-memory data buffers (retained for zoom-out beyond the sliding
        # X window).
        self._block_indices: list[float] = []
        self._stage_pos: list[float] = []
        self._camera_pos: list[float] = []
        self._residual: list[float] = []
        self._xs: list[float] = []

    def _configure_plot(self) -> None:
        """Set axis pens/text, labels, and the two Y axes: left (camera
        position) and right (stage position). Each axis is color-coded to
        its curve."""
        item = self.plotWidget_focusTrajectory.getPlotItem()

        # Left axis (camera position) — blue, matching the camera curve.
        left_ax = item.getAxis("left")
        left_ax.setPen(_ACCENT)
        left_ax.setTextPen(_ACCENT)
        item.setLabel("left", "Camera position (mm)", color=_ACCENT)

        bottom_ax = item.getAxis("bottom")
        bottom_ax.setPen(_FG)
        bottom_ax.setTextPen(_FG)
        item.setLabel("bottom", "Block")

        # Right axis (stage position) — grey ViewBox + axis.
        right_vb = pg.ViewBox()
        self._right_vb = right_vb
        item.scene().addItem(right_vb)
        right_ax = pg.AxisItem("right")
        right_ax.setPen(_MIDTONE)
        right_ax.setTextPen(_MIDTONE)
        right_ax.linkToView(right_vb)
        item.layout.addItem(right_ax, 2, 3)
        right_vb.setXLink(item.getViewBox())
        right_ax.setLabel("Horizontal stage position (mm)", color=_MIDTONE)

        # Geometry sync: mirror the main ViewBox onto the right ViewBox.
        main_vb = item.getViewBox()
        item.layout.setContentsMargins(_s.LG, _s.LG, _s.LG, _s.LG)

        def _sync_right_vbs() -> None:
            right_vb.setGeometry(main_vb.sceneBoundingRect())
            right_vb.linkedViewChanged(main_vb, right_vb.XAxis)

        main_vb.sigResized.connect(_sync_right_vbs)

        # Mouse: panning enabled, scroll-wheel zoom, clamp guards.
        main_vb.setMouseEnabled(x=True, y=True)
        right_vb.setMouseEnabled(x=True, y=True)
        main_vb.setMenuEnabled(False)

        # Camera Y auto-scales; stage Y auto-scales on its own ViewBox.
        main_vb.enableAutoRange(axis="y", enable=True)
        right_vb.enableAutoRange(axis="y", enable=True)
        right_vb.setDefaultPadding(0.1)

        def _data_bounds() -> tuple[float | None, float | None]:
            if not self._xs:  # pragma: no branch
                return None, None
            x_max = max(self._xs)
            x_min = min(self._xs)
            return x_max, max(1.0, x_max - x_min)

        def _make_drag_guard(vb: pg.ViewBox) -> Any:
            orig = vb.mouseDragEvent

            def _guarded(ev: MouseDragEvent, axis: int | None = None) -> None:
                orig(ev, axis)
                dx_max, dx_span = _data_bounds()
                _clamp_view_range(vb, data_x_max=dx_max, data_x_span=dx_span)

            return _guarded

        main_vb.mouseDragEvent = _make_drag_guard(main_vb)
        right_vb.mouseDragEvent = _make_drag_guard(right_vb)

        def _make_wheel_guard(vb: pg.ViewBox) -> Any:
            orig = vb.wheelEvent

            def _guarded(ev: Any, axis: int | None = None) -> None:
                orig(ev)
                dx_max, dx_span = _data_bounds()
                _clamp_view_range(vb, data_x_max=dx_max, data_x_span=dx_span)

            return _guarded

        main_vb.wheelEvent = _make_wheel_guard(main_vb)
        right_vb.wheelEvent = _make_wheel_guard(right_vb)

        _make_axis_range_drag(left_ax, main_vb)
        _make_axis_range_drag(bottom_ax, main_vb)
        _make_axis_range_drag(right_ax, right_vb)

        # Camera focus curve (left axis, accent blue, solid).
        self._camera_curve = pg.PlotDataItem(
            [], [], pen=pg.mkPen(_ACCENT, width=2), name="Camera position"
        )
        item.addItem(self._camera_curve)

        # Stage position curve (right ViewBox, grey, dashed).
        self._stage_curve = pg.PlotDataItem(
            [],
            [],
            pen=pg.mkPen(_MIDTONE, width=1, style=Qt.PenStyle.DashLine),
            name="Stage position",
        )
        right_vb.addItem(self._stage_curve)

        # Residual markers (warning-olive diamonds).
        self._residual_scatter = pg.ScatterPlotItem(
            symbol="d",
            size=8,
            pen=pg.mkPen(_WARNING),
            brush=pg.mkBrush(_WARNING),
            name="Residual applied",
        )
        item.addItem(self._residual_scatter)

        # Legend with the two curves + residual marker. The background
        # brush derives from the Breeze background token so it stays
        # consistent with the rest of the dark UI.
        _bg = cast(tuple[int, int, int, int], QColor(_BG).getRgb())
        _bg_rgba = (_bg[0], _bg[1], _bg[2], 200)
        self._legend = pg.LegendItem(
            (180, 80),
            offset=(10, 10),
            labelTextColor=_FG,
            brush=pg.mkBrush(*_bg_rgba),
        )
        self._legend.setParentItem(main_vb)
        self._legend.setZValue(1000)
        self._legend.addItem(self._camera_curve, "Camera position")
        self._legend.addItem(self._stage_curve, "Stage position")
        self._legend.addItem(self._residual_scatter, "Residual")
        self._legend.hide()

        # X auto-range enabled so the plot auto-scrolls as blocks append.
        item.getViewBox().enableAutoRange(axis="x", enable=True)

    def _rebuild_x_values(self) -> None:
        """Recompute ``self._xs`` from the block indices and redraw all
        curves."""
        self._xs = [float(v) for v in self._block_indices]

        item = self.plotWidget_focusTrajectory.getPlotItem()
        item.setLabel("bottom", "Block", color=_FG)

        if self._camera_curve is not None:
            self._camera_curve.setData(self._xs, self._camera_pos)
        if self._stage_curve is not None:
            self._stage_curve.setData(self._xs, self._stage_pos)

    def reset(self) -> None:
        """Reset the plot for a new run. Clears all curve/scatter data and
        removes stale markers; the curve objects themselves are reused."""
        self._frozen = False
        self._run_started = True
        self._block_indices = []
        self._stage_pos = []
        self._camera_pos = []
        self._residual = []
        self._xs = []

        if self._camera_curve is not None:
            self._camera_curve.setData([], [])
        if self._stage_curve is not None:
            self._stage_curve.setData([], [])
        if self._residual_scatter is not None:
            self._residual_scatter.setData([], [])

        self._rebuild_x_values()
        self.plotWidget_focusTrajectory.show()
        if self._legend is not None:
            self._legend.show()
        self.label_focusTrajectoryEmpty.hide()

    def set_empty(self) -> None:
        """Show the empty-state label and hide the plot (no run yet)."""
        self._frozen = False
        self._run_started = False
        self._block_indices = []
        self._stage_pos = []
        self._camera_pos = []
        self._residual = []
        self._xs = []
        self.plotWidget_focusTrajectory.hide()
        if self._legend is not None:
            self._legend.hide()
        self.label_focusTrajectoryEmpty.show()

    def has_data(self) -> bool:
        """Return True if the widget has acquired samples to display."""
        return len(self._xs) > 0

    def show_plot(self) -> None:
        """Show the plot + legend and hide the empty-state label,
        WITHOUT clearing data."""
        self.plotWidget_focusTrajectory.show()
        if self._legend is not None:
            self._legend.show()
        self.label_focusTrajectoryEmpty.hide()

    def append_sample(
        self,
        block_idx: float,
        stage_pos_mm: float,
        camera_pos_mm: float,
        residual_mm: float,
        x_axis_value: float,
    ) -> None:
        """Append one per-block sample to the trajectory. GUI-thread only.

        Ignored after ``freeze()`` so the last trajectory is preserved
        for review (E-stop / abort).
        """
        if self._frozen:
            return
        if not self._run_started:
            self.reset()

        self._block_indices.append(float(block_idx))
        self._stage_pos.append(float(stage_pos_mm))
        self._camera_pos.append(float(camera_pos_mm))
        self._residual.append(float(residual_mm))
        self._xs.append(float(x_axis_value))

        if self._camera_curve is not None:
            self._camera_curve.setData(self._xs, self._camera_pos)
        if self._stage_curve is not None:
            self._stage_curve.setData(self._xs, self._stage_pos)
        if self._residual_scatter is not None and residual_mm != 0.0:
            spots = self._residual_scatter.getData()
            existing_x = list(spots[0]) if spots[0] is not None else []
            existing_y = list(spots[1]) if spots[1] is not None else []
            existing_x.append(float(x_axis_value))
            existing_y.append(float(camera_pos_mm))
            self._residual_scatter.setData(existing_x, existing_y)

        # Sliding X window: show the last _X_WINDOW blocks, retain all
        # in-memory data for zoom-out.
        if len(self._xs) > _X_WINDOW:
            x_min = self._xs[-_X_WINDOW]
            x_max = self._xs[-1] + 1
            self.plotWidget_focusTrajectory.getPlotItem().getViewBox().setXRange(
                x_min, x_max, padding=0.0
            )

    def freeze(self) -> None:
        """Freeze the plot — further append_sample calls are ignored so
        the last trajectory is preserved for review (E-stop / abort)."""
        self._frozen = True
