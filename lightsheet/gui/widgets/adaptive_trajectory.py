"""Dockable pyqtgraph trajectory widget for the adaptive exposure + laser
power control loop (D-04).

A ``QWidget`` containing a ``pyqtgraph.PlotWidget`` and a word-wrapped
empty-state ``QLabel``. The widget is GUI-thread-only — the
``StackWorker`` emits ``sig_adaptive_trajectory`` (a queued ``Signal``)
and the shell's GUI-thread slot calls ``append_sample``. The worker
NEVER calls pyqtgraph directly (AGENTS.md §11 — no cross-thread Qt
widget access from workers).

Plot layout (UI-SPEC §Color, §States/Interactions):
- Left Y axis: intensity (% of max) + a target-band LinearRegionItem
  (accent blue at ~25% alpha, fixed — does not scroll).
- Right Y axis (linked ViewBox): exposure (ms) and L1 power (mW),
  twin-axis so the operator sees the control variable the loop is
  actuating alongside the intensity it is tracking.
- X axis: plane index. Beyond 200 planes the X view auto-scrolls to
  the last 200 while retaining the complete in-memory data for
  zoom-out (downsampling + a sliding X-range window).
- Re-acquire events: vertical dashed warning lines at the plane index.
- Power-fallback events: small information-blue triangles at the plane.

States:
- empty (no run): label visible, plot hidden.
- populated (run in progress): plot visible, label hidden; one point
  per plane appended via the same append path (zero/one/many all work).
- frozen (E-stop / abort): further appends are ignored so the last
  trajectory is preserved for operator review.

pyqtgraph is reintroduced ONLY for ``PlotWidget`` — no image-view
widget from pyqtgraph is imported (UI-SPEC §Registry Safety). The
native ``lightsheet/gui/image_view.py`` stays the image viewer.
"""

from __future__ import annotations

import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

# Breeze dark theme tokens (UI-SPEC §Color).
_BG = "#1d2023"  # view:background — plot background
_FG = "#eff0f1"  # foreground — axis pens / text
_ACCENT = "#3daee9"  # highlight — target band + exposure curve
_WARNING = "#99995C"  # re-acquire marker
_INFORMATION = "#406880"  # power-fallback marker

# The exact empty-state copy (UI-SPEC §Copywriting Contract).
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

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Empty-state label: word-wrapped so the fixed English sentence
        # wraps without clipping at the dock's minimum width (backstop
        # truths #11, #12).
        self.label_adaptiveTrajectoryEmpty = QLabel(EMPTY_COPY, self)
        self.label_adaptiveTrajectoryEmpty.setWordWrap(True)
        self.label_adaptiveTrajectoryEmpty.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        self.label_adaptiveTrajectoryEmpty.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )
        layout.addWidget(self.label_adaptiveTrajectoryEmpty)

        # Curves / markers (created in reset() so the plot starts empty).
        # Initialized to None BEFORE _configure_plot() so the right
        # ViewBox assignment in _configure_plot() is not overwritten.
        self._intensity_curve: pg.PlotDataItem | None = None
        self._exposure_curve: pg.PlotDataItem | None = None
        self._power_curve: pg.PlotDataItem | None = None
        self._target_band: pg.LinearRegionItem | None = None
        self._reacquire_lines: list[pg.InfiniteLine] = []
        self._power_fallback_scatter: pg.ScatterPlotItem | None = None
        self._right_vb: pg.ViewBox | None = None

        # PlotWidget — the only pyqtgraph surface reintroduced this phase.
        self.plotWidget_adaptiveTrajectory = pg.PlotWidget(self)
        self.plotWidget_adaptiveTrajectory.setBackground(_BG)
        self._configure_plot()
        self.plotWidget_adaptiveTrajectory.hide()
        layout.addWidget(self.plotWidget_adaptiveTrajectory)

        # In-memory data buffers (retained for zoom-out beyond the
        # sliding X window).
        self._xs: list[float] = []
        self._intensity: list[float] = []
        self._exposure: list[float] = []
        self._power: list[float] = []

    def _configure_plot(self) -> None:
        """Set axis pens/text, labels, downsampling, and the twin-axis
        right ViewBox for exposure/power."""
        item = self.plotWidget_adaptiveTrajectory.getPlotItem()
        # Axis pens + text color (Breeze foreground).
        for side in ("left", "bottom"):
            ax = item.getAxis(side)
            ax.setPen(_FG)
            ax.setTextPen(_FG)
        item.setLabel("left", "Intensity (% of max)")
        item.setLabel("bottom", "Plane")
        # Twin-axis right ViewBox for exposure (ms) + L1 power (mW).
        self._right_vb = pg.ViewBox()
        item.scene().addItem(self._right_vb)
        right_ax = pg.AxisItem("right")
        right_ax.setPen(_FG)
        right_ax.setTextPen(_FG)
        right_ax.linkToView(self._right_vb)
        item.layout.addItem(right_ax, 2, 3)
        # Link the right ViewBox's X to the left ViewBox so the twin
        # axes share the plane index.
        self._right_vb.setXLink(item.getViewBox())
        right_ax.setLabel("Exposure (ms) / Power (mW)")
        # Downsampling keeps long stacks responsive (threat T-10-06).
        item.getViewBox().enableAutoRange(axis="x", enable=False)

    def reset(
        self, target_band_lo: float = 0.90, target_band_hi: float = 0.95
    ) -> None:
        """Reset the plot for a new run with the given target band
        (fractions 0..1). Clears all curves/markers and re-adds the
        target band region."""
        self._frozen = False
        self._target_band_lo = target_band_lo
        self._target_band_hi = target_band_hi
        self._xs = []
        self._intensity = []
        self._exposure = []
        self._power = []
        self._reacquire_lines = []
        item = self.plotWidget_adaptiveTrajectory.getPlotItem()
        # Clear all items and re-create the curves. item.clear() removes
        # items from the main ViewBox; the right ViewBox survives (it
        # was added to the scene, not as a PlotItem item).
        item.clear()
        # Target band: LinearRegionItem spanning lo..hi %, accent blue
        # at ~25% alpha (fixed — does not scroll).
        self._target_band = pg.LinearRegionItem(
            [target_band_lo * 100.0, target_band_hi * 100.0],
            brush=pg.mkBrush(61, 174, 233, 64),  # #3daee9 @ ~25% alpha
            movable=False,
        )
        self._target_band.lines[0].setPen(pg.mkPen(_ACCENT))
        self._target_band.lines[1].setPen(pg.mkPen(_ACCENT))
        item.addItem(self._target_band)
        # Intensity curve (left axis, accent blue).
        self._intensity_curve = item.plot(
            [], [], pen=pg.mkPen(_ACCENT, width=2), name="Intensity"
        )
        # Exposure + power curves on the twin-axis right ViewBox. The
        # right ViewBox + axis were created once in _configure_plot();
        # here we just (re)create the curves on it. Clear any prior
        # curves from the right ViewBox first (item.clear() above only
        # clears the main ViewBox).
        if self._right_vb is not None:
            for it in list(self._right_vb.addedItems):
                self._right_vb.removeItem(it)
            self._exposure_curve = pg.PlotDataItem(
                [], [],
                pen=pg.mkPen(_ACCENT, width=1, style=Qt.PenStyle.DashLine),
                name="Exposure",
            )
            self._right_vb.addItem(self._exposure_curve)
            self._power_curve = pg.PlotDataItem(
                [], [], pen=pg.mkPen(_INFORMATION, width=1),
                name="Power L1",
            )
            self._right_vb.addItem(self._power_curve)
        # Power-fallback scatter (information-blue triangles).
        self._power_fallback_scatter = pg.ScatterPlotItem(
            symbol="t", size=10, pen=pg.mkPen(_INFORMATION),
            brush=pg.mkBrush(_INFORMATION), name="Power fallback",
        )
        item.addItem(self._power_fallback_scatter)
        # Show the plot, hide the empty label.
        self.plotWidget_adaptiveTrajectory.show()
        self.label_adaptiveTrajectoryEmpty.hide()

    def set_empty(self) -> None:
        """Show the empty-state label and hide the plot (no run yet)."""
        self._frozen = False
        self._xs = []
        self._intensity = []
        self._exposure = []
        self._power = []
        self._reacquire_lines = []
        self.plotWidget_adaptiveTrajectory.hide()
        self.label_adaptiveTrajectoryEmpty.show()

    def append_sample(
        self,
        plane_idx: int,
        intensity: float,
        exposure_s: float,
        power1_mw: float,
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
        if self._intensity_curve is None:
            # First sample of a run without an explicit reset() — reset
            # with default band so the plot initializes.
            self.reset()
        self._xs.append(float(plane_idx))
        self._intensity.append(intensity * 100.0)  # fraction -> %
        self._exposure.append(exposure_s * 1000.0)  # s -> ms
        self._power.append(power1_mw)
        assert self._intensity_curve is not None
        self._intensity_curve.setData(self._xs, self._intensity)
        if self._exposure_curve is not None:
            self._exposure_curve.setData(self._xs, self._exposure)
        if self._power_curve is not None:
            self._power_curve.setData(self._xs, self._power)
        # Re-acquire marker: vertical dashed warning line.
        if reacquired:
            line = pg.InfiniteLine(
                pos=float(plane_idx), angle=90,
                pen=pg.mkPen(_WARNING, style=Qt.PenStyle.DashLine, width=1),
            )
            self.plotWidget_adaptiveTrajectory.getPlotItem().addItem(line)
            self._reacquire_lines.append(line)
        # Power-fallback marker: information-blue triangle.
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
        # in-memory data for zoom-out (threat T-10-06).
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
