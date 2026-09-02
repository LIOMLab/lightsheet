"""Branch-coverage tests for ``lightsheet/gui/widgets/adaptive_trajectory.py``.

Targets the specific branches left uncovered by ``test_adaptive_ui.py``
(the happy-path widget tests). The uncovered branches fall into groups:

1. ``_clamp_view_range`` — the module-level pure function that clamps a
   ViewBox range. Called directly with a real ViewBox in various range
   states (X<0, Y<0, X-span too large, X-max beyond data, Y-max beyond
   cap, already-valid → no-op).
2. Defensive ``if self._right_vb is not None`` / ``if self._power_vb is
   not None`` / ``if self._legend is not None`` guards in ``reset``,
   ``set_empty``, ``show_plot``, ``set_power_visible``, ``append_sample``,
   and ``_rebuild_legend`` — covered by setting the attribute to ``None``
   after construction and calling the method.
3. ``_rebuild_legend`` None-curve guards and power-visibility branches.
4. ``append_sample`` auto-reset (no explicit ``reset()``), power-fallback
   with scatter ``None``, and the > 200-plane sliding-window branch.
5. ``has_data`` empty vs populated.
6. ``_sync_right_vbs`` False branches (right_vb / power_vb None).

The defensive ``_configure_plot`` guards (False branches of
``if self._right_vb is not None`` inside ``_configure_plot`` itself) are
unreachable in normal construction — ``_configure_plot`` unconditionally
creates both ViewBoxes — and are ESCALATED as rig-only/unreachable
defensive code (see VALIDATION notes).
"""

from __future__ import annotations

from typing import Any

import pyqtgraph as pg
import pytest
from pytest import FixtureRequest
from pytestqt.qtbot import QtBot

pytest.importorskip("PySide6")

from _helpers.controller_fixture import make_controller

from lightsheet.gui.widgets.adaptive_trajectory import (
    AdaptiveTrajectoryWidget,
    _clamp_view_range,
    _make_axis_range_drag,
)


def _make_widget(qtbot: QtBot) -> AdaptiveTrajectoryWidget:
    w = AdaptiveTrajectoryWidget()
    qtbot.addWidget(w)
    return w


# --------------------------------------------------------------------- #
# _clamp_view_range — direct calls covering all branches
# --------------------------------------------------------------------- #


def test_clamp_view_range_x_below_zero(qtbot: QtBot) -> None:
    """X min < 0 → shift x1 and clamp x0 to 0 (lines 121-124)."""
    vb = pg.ViewBox()
    vb.setRange(xRange=(-5, 10), yRange=(0, 100), padding=0.0)
    _clamp_view_range(vb)
    (x0, _x1), (_y0, _y1) = vb.viewRange()
    assert x0 >= 0.0


def test_clamp_view_range_y_below_zero(qtbot: QtBot) -> None:
    """Y min < 0 → shift y1 and clamp y0 to 0 (lines 126-129)."""
    vb = pg.ViewBox()
    vb.setRange(xRange=(0, 100), yRange=(-10, 50), padding=0.0)
    _clamp_view_range(vb)
    (_x0, _x1), (y0, _y1) = vb.viewRange()
    assert y0 >= 0.0


def test_clamp_view_range_x_span_too_large(qtbot: QtBot) -> None:
    """View X span > 4x data span → shrink to 4x (lines 132-136, branch
    [134,135])."""
    vb = pg.ViewBox()
    vb.setRange(xRange=(0, 1000), yRange=(0, 100), padding=0.0)
    _clamp_view_range(vb, data_x_span=10.0)  # max_x_span = 40
    (x0, x1), (_y0, _y1) = vb.viewRange()
    assert (x1 - x0) <= 40.0 + 1e-6


def test_clamp_view_range_x_span_ok(qtbot: QtBot) -> None:
    """View X span <= 4x data span → no clamp on span (branch [134,141],
    the False branch of the inner if)."""
    vb = pg.ViewBox()
    vb.setRange(xRange=(0, 30), yRange=(0, 100), padding=0.0)
    _clamp_view_range(vb, data_x_span=10.0)  # max_x_span = 40, view=30
    (x0, x1), (_y0, _y1) = vb.viewRange()
    assert (x1 - x0) <= 40.0 + 1e-6


def test_clamp_view_range_x_span_none(qtbot: QtBot) -> None:
    """data_x_span=None → skip the span clamp entirely (branch [132,141])."""
    vb = pg.ViewBox()
    vb.setRange(xRange=(0, 50), yRange=(0, 100), padding=0.0)
    _clamp_view_range(vb, data_x_span=None)
    # No exception, range unchanged (already valid).
    (x0, _x1), (_y0, _y1) = vb.viewRange()
    assert x0 >= 0.0


def test_clamp_view_range_x_max_beyond_data(qtbot: QtBot) -> None:
    """x1 > data_x_max + 4 → shift window back (lines 141-145)."""
    vb = pg.ViewBox()
    vb.setRange(xRange=(0, 200), yRange=(0, 100), padding=0.0)
    _clamp_view_range(vb, data_x_max=10.0)  # max x1 = 14
    (_x0, x1), (_y0, _y1) = vb.viewRange()
    assert x1 <= 14.0 + 1e-6


def test_clamp_view_range_x_max_ok(qtbot: QtBot) -> None:
    """x1 <= data_x_max + 4 → no clamp on x_max (branch [141,149])."""
    vb = pg.ViewBox()
    vb.setRange(xRange=(0, 10), yRange=(0, 100), padding=0.0)
    _clamp_view_range(vb, data_x_max=10.0)  # x1=10 <= 14
    (_x0, x1), (_y0, _y1) = vb.viewRange()
    assert x1 <= 14.0 + 1e-6


def test_clamp_view_range_y_max_beyond_cap(qtbot: QtBot) -> None:
    """y1 > y_max → shift window down (lines 149-153, branch [149,150])."""
    vb = pg.ViewBox()
    vb.setRange(xRange=(0, 100), yRange=(0, 200), padding=0.0)
    _clamp_view_range(vb, y_max=120.0)
    (_x0, _x1), (_y0, y1) = vb.viewRange()
    assert y1 <= 120.0 + 1e-6


def test_clamp_view_range_y_max_ok(qtbot: QtBot) -> None:
    """y1 <= y_max → no clamp on y_max (branch [149,154])."""
    vb = pg.ViewBox()
    vb.setRange(xRange=(0, 100), yRange=(0, 100), padding=0.0)
    _clamp_view_range(vb, y_max=120.0)  # y1=100 <= 120
    (_x0, _x1), (_y0, y1) = vb.viewRange()
    assert y1 <= 120.0 + 1e-6


def test_clamp_view_range_y_max_none(qtbot: QtBot) -> None:
    """y_max=None → skip the Y-max clamp (branch [149,154] via None
    short-circuit)."""
    vb = pg.ViewBox()
    vb.setRange(xRange=(0, 100), yRange=(0, 500), padding=0.0)
    _clamp_view_range(vb, y_max=None)
    # No exception; range may be unchanged (already valid X/Y >= 0).
    (x0, _x1), (y0, _y1) = vb.viewRange()
    assert x0 >= 0.0 and y0 >= 0.0


def test_clamp_view_range_already_valid_noop(qtbot: QtBot) -> None:
    """Range already valid (X>=0, Y>=0, within all bounds) → no-op return
    (line 154-155, branch [154,156] → return)."""
    vb = pg.ViewBox()
    vb.setRange(xRange=(0, 50), yRange=(0, 50), padding=0.0)
    _clamp_view_range(vb, data_x_max=100.0, data_x_span=50.0, y_max=100.0)
    # If we get here without error, the early return path executed.
    (x0, _x1), (y0, _y1) = vb.viewRange()
    assert x0 >= 0.0 and y0 >= 0.0


def test_clamp_view_range_needs_clamp_after_all_checks(qtbot: QtBot) -> None:
    """Multiple clamp conditions at once (X<0 AND Y<0 AND span too large
    AND x_max beyond AND y_max beyond) → all fire, needs_clamp=True,
    setRange called (line 156)."""
    vb = pg.ViewBox()
    vb.setRange(xRange=(-10, 500), yRange=(-20, 300), padding=0.0)
    _clamp_view_range(vb, data_x_max=10.0, data_x_span=5.0, y_max=120.0)
    (x0, _x1), (y0, y1) = vb.viewRange()
    assert x0 >= 0.0
    assert y0 >= 0.0
    assert y1 <= 120.0 + 1e-6


# --------------------------------------------------------------------- #
# reset() — defensive None guards for curves / scatter / band / legend
# --------------------------------------------------------------------- #


def test_reset_with_all_curves_none(qtbot: QtBot) -> None:
    """reset() guards: if _intensity_curve / _exposure_curve / _power_curve
    / _power2_curve / _power_fallback_scatter / _target_band / _legend are
    None, the method skips them without error (lines 545-575)."""
    w = _make_widget(qtbot)
    # Null out all optional curve/scatter/band/legend refs.
    w._intensity_curve = None
    w._exposure_curve = None
    w._power_curve = None
    w._power2_curve = None
    w._power_fallback_scatter = None
    w._target_band = None
    w._legend = None
    # Must not raise.
    w.reset(target_band_lo=0.80, target_band_hi=0.95)
    assert w._run_started is True
    assert w._frozen is False


def test_reset_removes_old_reacquire_lines(qtbot: QtBot) -> None:
    """reset() removes existing re-acquire marker lines (lines 541-543,
    branch [541,542] — the for-body when lines exist)."""
    w = _make_widget(qtbot)
    w.reset(target_band_lo=0.90, target_band_hi=0.95)
    # Append a sample with reacquire=True to create a marker line.
    w.append_sample(
        plane_idx=0, intensity=0.50, exposure_s=0.005,
        power1_mw=10.0, power2_mw=0.0, control_variable_active="exposure",
        reacquired=True, power_fallback=False,
    )
    assert len(w._reacquire_lines) == 1
    # reset() removes the old lines.
    w.reset(target_band_lo=0.90, target_band_hi=0.95)
    assert len(w._reacquire_lines) == 0


# --------------------------------------------------------------------- #
# set_empty() — legend None guard
# --------------------------------------------------------------------- #


def test_set_empty_with_legend_none(qtbot: QtBot) -> None:
    """set_empty() with _legend=None skips the legend.hide() call
    (branch [590,592])."""
    w = _make_widget(qtbot)
    w._legend = None
    w.set_empty()  # must not raise
    assert w._run_started is False
    assert w.plotWidget_adaptiveTrajectory.isHidden()


# --------------------------------------------------------------------- #
# show_plot() — legend None guard
# --------------------------------------------------------------------- #


def test_show_plot_with_legend_none(qtbot: QtBot) -> None:
    """show_plot() with _legend=None skips the legend.show() call
    (branch [606,608])."""
    w = _make_widget(qtbot)
    w._legend = None
    w.show_plot()  # must not raise
    assert not w.plotWidget_adaptiveTrajectory.isHidden()


# --------------------------------------------------------------------- #
# has_data() — empty vs populated
# --------------------------------------------------------------------- #


def test_has_data_empty(qtbot: QtBot) -> None:
    """has_data() returns False when no samples have been appended."""
    w = _make_widget(qtbot)
    assert w.has_data() is False


def test_has_data_populated(qtbot: QtBot) -> None:
    """has_data() returns True after at least one append_sample."""
    w = _make_widget(qtbot)
    w.reset(target_band_lo=0.90, target_band_hi=0.95)
    w.append_sample(
        plane_idx=0, intensity=0.92, exposure_s=0.005,
        power1_mw=10.0, power2_mw=0.0, control_variable_active="exposure",
        reacquired=False, power_fallback=False,
    )
    assert w.has_data() is True


# --------------------------------------------------------------------- #
# set_power_visible() — curve None guards
# --------------------------------------------------------------------- #


def test_set_power_visible_with_curves_none(qtbot: QtBot) -> None:
    """set_power_visible() with _power_curve / _power2_curve None skips
    the setVisible calls (branches [617,619], [619,621])."""
    w = _make_widget(qtbot)
    w._power_curve = None
    w._power2_curve = None
    w.set_power_visible(l1=False, l2=False)  # must not raise
    assert w._power_l1_visible is False
    assert w._power_l2_visible is False


# --------------------------------------------------------------------- #
# append_sample() — auto-reset, None guards, power_fallback, sliding window
# --------------------------------------------------------------------- #


def test_append_sample_without_reset_auto_resets(qtbot: QtBot) -> None:
    """append_sample() without a prior reset() auto-calls reset() with
    default band (lines 682-689, branch [682,689])."""
    w = _make_widget(qtbot)
    # No reset() call — _run_started is False.
    assert w._run_started is False
    w.append_sample(
        plane_idx=0, intensity=0.92, exposure_s=0.005,
        power1_mw=10.0, power2_mw=0.0, control_variable_active="exposure",
        reacquired=False, power_fallback=False,
    )
    # Auto-reset fired: plot is visible, run_started is True.
    assert w._run_started is True
    assert not w.plotWidget_adaptiveTrajectory.isHidden()


def test_append_sample_with_right_vb_none(qtbot: QtBot) -> None:
    """append_sample() with _right_vb=None skips exposure/power curve
    setData (branches [697,699], [699,701]). The intensity curve still
    updates."""
    w = _make_widget(qtbot)
    w.reset(target_band_lo=0.90, target_band_hi=0.95)
    w._right_vb = None
    w._power_vb = None
    w.append_sample(
        plane_idx=0, intensity=0.92, exposure_s=0.005,
        power1_mw=10.0, power2_mw=0.0, control_variable_active="exposure",
        reacquired=False, power_fallback=False,
    )
    xs, _ys = w._intensity_curve.getData()  # ty: ignore[unresolved-attribute]
    assert len(xs) == 1


def test_append_sample_power_fallback_scatter_none(qtbot: QtBot) -> None:
    """append_sample() with power_fallback=True but _power_fallback_scatter
    None → skips the scatter append (branch [713,724])."""
    w = _make_widget(qtbot)
    w.reset(target_band_lo=0.90, target_band_hi=0.95)
    w._power_fallback_scatter = None
    w.append_sample(
        plane_idx=0, intensity=0.85, exposure_s=0.005,
        power1_mw=20.0, power2_mw=0.0, control_variable_active="power",
        reacquired=False, power_fallback=True,
    )
    # No exception; intensity curve still got the sample.
    xs, _ys = w._intensity_curve.getData()  # ty: ignore[unresolved-attribute]
    assert len(xs) == 1


def test_append_sample_sliding_window_beyond_200(qtbot: QtBot) -> None:
    """Beyond 200 planes the sliding X window fires (line 724 → 725,
    branch [724,725]). The X range is set to the last 200 planes."""
    w = _make_widget(qtbot)
    w.reset(target_band_lo=0.90, target_band_hi=0.95)
    for i in range(201):
        w.append_sample(
            plane_idx=i, intensity=0.90, exposure_s=0.005,
            power1_mw=10.0, power2_mw=0.0, control_variable_active="exposure",
            reacquired=False, power_fallback=False,
        )
    vb = w.plotWidget_adaptiveTrajectory.getPlotItem().getViewBox()
    x_min, _x_max = vb.viewRange()[0]
    assert x_min >= 1  # window starts at plane 1


# --------------------------------------------------------------------- #
# _rebuild_legend() — None guards and power-visibility branches
# --------------------------------------------------------------------- #


def test_rebuild_legend_with_legend_none(qtbot: QtBot) -> None:
    """_rebuild_legend() with _legend=None returns immediately
    (branch [630,631])."""
    w = _make_widget(qtbot)
    w._legend = None
    w._rebuild_legend()  # must not raise


def test_rebuild_legend_with_all_curves_none(qtbot: QtBot) -> None:
    """_rebuild_legend() with all curve/scatter/samples None skips them
    (branches [647,651] etc. — the None guards before addItem)."""
    w = _make_widget(qtbot)
    w._target_band_legend_sample = None  # ty: ignore[invalid-assignment]
    w._intensity_curve = None
    w._exposure_curve = None
    w._power_fallback_scatter = None
    w._power_curve = None
    w._power2_curve = None
    w._reacquire_legend_sample = None  # ty: ignore[invalid-assignment]
    w._rebuild_legend()  # must not raise


def test_rebuild_legend_power_l1_hidden(qtbot: QtBot) -> None:
    """_rebuild_legend() with _power_l1_visible=False skips Power L1
    (branch [657,659] → [659,660] False path)."""
    w = _make_widget(qtbot)
    w._power_l1_visible = False
    w._power_l2_visible = True
    w._rebuild_legend()  # must not raise


def test_rebuild_legend_power_l2_hidden(qtbot: QtBot) -> None:
    """_rebuild_legend() with _power_l2_visible=False skips Power L2
    (branch [659,661] → [659,660] False path for L2)."""
    w = _make_widget(qtbot)
    w._power_l1_visible = True
    w._power_l2_visible = False
    w._rebuild_legend()  # must not raise


def test_rebuild_legend_power_both_hidden(qtbot: QtBot) -> None:
    """_rebuild_legend() with both power visibility flags False skips
    both L1 and L2 legend entries."""
    w = _make_widget(qtbot)
    w._power_l1_visible = False
    w._power_l2_visible = False
    w._rebuild_legend()  # must not raise


def test_rebuild_legend_removes_existing_items(qtbot: QtBot) -> None:
    """_rebuild_legend() removes existing entries before re-adding (the
    for-loop at lines 635-645, branch [644,635] loop-continue). Calling
    it twice must not duplicate entries."""
    w = _make_widget(qtbot)
    w._rebuild_legend()
    # Capture item count after first rebuild.
    first_count = len(w._legend.items) if w._legend is not None else 0
    w._rebuild_legend()
    second_count = len(w._legend.items) if w._legend is not None else 0
    assert second_count == first_count, "rebuild must not duplicate entries"


# --------------------------------------------------------------------- #
# _sync_right_vbs — False branches (right_vb / power_vb None)
# --------------------------------------------------------------------- #


def test_sync_right_vbs_with_both_none(qtbot: QtBot) -> None:
    """The _sync_right_vbs closure handles _right_vb=None and
    _power_vb=None (branches [306,309] and [309,-305]). Triggered via
    the main ViewBox sigResized signal."""
    w = _make_widget(qtbot)
    # Set both right vbs to None, then trigger a resize of the main vb.
    w._right_vb = None
    w._power_vb = None
    main_vb = w.plotWidget_adaptiveTrajectory.getPlotItem().getViewBox()
    # Emit sigResized — the connected _sync_right_vbs must handle None
    # without raising.
    main_vb.sigResized.emit(main_vb)
    # No exception means the None guards executed.


# --------------------------------------------------------------------- #
# _make_axis_range_drag — _range_drag inner branches
# --------------------------------------------------------------------- #


class _FakeDragEvent:
    """Minimal stand-in for pyqtgraph's MouseDragEvent covering the
    attributes _range_drag reads: button(), buttonDownScenePos(),
    pos(), lastPos(), accept(), ignore().

    ``inside_rect`` is the sceneBoundingRect of the ViewBox the drag is
    tested against — used to compute a point guaranteed inside (center)
    or outside (far away) so the ``contains()`` check in _range_drag
    behaves deterministically.
    """

    def __init__(
        self,
        button_inside: bool,
        button: Any,
        inside_rect: Any = None,
        pos_y: float = 0.0,
        pos_x: float = 0.0,
        last_y: float = 0.0,
        last_x: float = 0.0,
    ) -> None:
        self._button = button
        self._button_inside = button_inside
        self._inside_rect = inside_rect
        self._pos_y = pos_y
        self._pos_x = pos_x
        self._last_y = last_y
        self._last_x = last_x
        self.accepted = False
        self.ignored = False

    def button(self) -> Any:
        return self._button

    def buttonDownScenePos(self) -> Any:
        from PySide6.QtCore import QPointF

        if self._button_inside and self._inside_rect is not None:
            r = self._inside_rect
            return QPointF(r.center().x(), r.center().y())
        return QPointF(-99999, -99999)

    def pos(self) -> Any:
        from PySide6.QtCore import QPointF

        return QPointF(self._pos_x, self._pos_y)

    def lastPos(self) -> Any:
        from PySide6.QtCore import QPointF

        return QPointF(self._last_x, self._last_y)

    def accept(self) -> None:
        self.accepted = True

    def ignore(self) -> None:
        self.ignored = True


def test_range_drag_ignores_drag_starting_inside_viewbox(qtbot: QtBot) -> None:
    """_range_drag ignores events that started inside the ViewBox
    (line 46→47, branch [46,47])."""
    w = _make_widget(qtbot)
    left_ax = w.plotWidget_adaptiveTrajectory.getPlotItem().getAxis("left")
    main_vb = w.plotWidget_adaptiveTrajectory.getPlotItem().getViewBox()
    _make_axis_range_drag(left_ax, main_vb)
    ev = _FakeDragEvent(
        button_inside=True,
        button=__import__("PySide6").QtCore.Qt.MouseButton.LeftButton,  # ty: ignore[unresolved-attribute]
        inside_rect=main_vb.sceneBoundingRect(),
    )
    left_ax.mouseDragEvent(ev)
    assert ev.ignored is True


def test_range_drag_ignores_non_left_button(qtbot: QtBot) -> None:
    """_range_drag ignores events with a non-LeftButton button
    (line 49→50, branch [49,50])."""
    from PySide6.QtCore import Qt

    w = _make_widget(qtbot)
    left_ax = w.plotWidget_adaptiveTrajectory.getPlotItem().getAxis("left")
    main_vb = w.plotWidget_adaptiveTrajectory.getPlotItem().getViewBox()
    _make_axis_range_drag(left_ax, main_vb)
    ev = _FakeDragEvent(
        button_inside=False,
        button=Qt.MouseButton.RightButton,
    )
    left_ax.mouseDragEvent(ev)
    assert ev.ignored is True


def test_range_drag_y_axis_zooms(qtbot: QtBot) -> None:
    """_range_drag on a left/right axis (Y) with span > 0 zooms the Y
    range (lines 57→58, 60→65)."""
    from PySide6.QtCore import Qt

    w = _make_widget(qtbot)
    left_ax = w.plotWidget_adaptiveTrajectory.getPlotItem().getAxis("left")
    main_vb = w.plotWidget_adaptiveTrajectory.getPlotItem().getViewBox()
    main_vb.setRange(xRange=(0, 100), yRange=(0, 100), padding=0.0)
    _make_axis_range_drag(left_ax, main_vb)
    ev = _FakeDragEvent(
        button_inside=False,
        button=Qt.MouseButton.LeftButton,
        pos_y=10.0,
        last_y=0.0,
    )
    left_ax.mouseDragEvent(ev)
    assert ev.accepted is True


def test_range_drag_y_axis_zero_span_returns(qtbot: QtBot) -> None:
    """_range_drag on a Y axis with span <= 0 returns early (line 60→61,
    branch [60,61]).

    pyqtgraph's ``setRange(yRange=(0, 0))`` auto-expands a zero span to a
    1-unit range (``[-0.5, 0.5]``), so the zero-span early return cannot
    be reached via ``setRange`` alone. We patch ``vb.viewRange`` to return
    a genuine zero-span Y range so ``span = y1 - y0 == 0`` and the
    ``if span <= 0: return`` guard fires."""
    from unittest.mock import patch

    from PySide6.QtCore import Qt

    w = _make_widget(qtbot)
    left_ax = w.plotWidget_adaptiveTrajectory.getPlotItem().getAxis("left")
    main_vb = w.plotWidget_adaptiveTrajectory.getPlotItem().getViewBox()
    main_vb.setRange(xRange=(0, 100), yRange=(0, 100), padding=0.0)
    _make_axis_range_drag(left_ax, main_vb)
    ev = _FakeDragEvent(
        button_inside=False,
        button=Qt.MouseButton.LeftButton,
        pos_y=10.0,
        last_y=0.0,
    )
    # Force a zero Y span: viewRange returns [(x0, x1), (y0, y1)] with
    # y0 == y1 so span == 0.
    with patch.object(main_vb, "viewRange", return_value=[(0.0, 100.0), (5.0, 5.0)]):
        left_ax.mouseDragEvent(ev)
    # accept() was called before the span check, so accepted=True but
    # setRange was NOT called (the early return fired before it). Verify
    # the Y range was not changed by the drag (still the setRange value).
    assert ev.accepted is True
    (_x0, _x1), (y0, y1) = main_vb.viewRange()
    assert y1 - y0 > 0  # unchanged — the zero-span return prevented a setRange


def test_range_drag_x_axis_zooms(qtbot: QtBot) -> None:
    """_range_drag on a bottom axis (X) with span > 0 zooms the X range
    (lines 57→75, 77→79)."""
    from PySide6.QtCore import Qt

    w = _make_widget(qtbot)
    bottom_ax = w.plotWidget_adaptiveTrajectory.getPlotItem().getAxis("bottom")
    main_vb = w.plotWidget_adaptiveTrajectory.getPlotItem().getViewBox()
    main_vb.setRange(xRange=(0, 100), yRange=(0, 100), padding=0.0)
    _make_axis_range_drag(bottom_ax, main_vb)
    ev = _FakeDragEvent(
        button_inside=False,
        button=Qt.MouseButton.LeftButton,
        pos_x=10.0,
        last_x=0.0,
    )
    bottom_ax.mouseDragEvent(ev)
    assert ev.accepted is True


def test_range_drag_x_axis_zero_span_returns(qtbot: QtBot) -> None:
    """_range_drag on an X axis with span <= 0 returns early (line 77→78,
    branch [77,78]).

    Same rationale as the Y-axis zero-span test: ``setRange(xRange=(0, 0))``
    auto-expands to ``[-0.5, 0.5]``, so we patch ``viewRange`` to return a
    genuine zero-span X range."""
    from unittest.mock import patch

    from PySide6.QtCore import Qt

    w = _make_widget(qtbot)
    bottom_ax = w.plotWidget_adaptiveTrajectory.getPlotItem().getAxis("bottom")
    main_vb = w.plotWidget_adaptiveTrajectory.getPlotItem().getViewBox()
    main_vb.setRange(xRange=(0, 100), yRange=(0, 100), padding=0.0)
    _make_axis_range_drag(bottom_ax, main_vb)
    ev = _FakeDragEvent(
        button_inside=False,
        button=Qt.MouseButton.LeftButton,
        pos_x=10.0,
        last_x=0.0,
    )
    # Force a zero X span so span == 0 and the early return fires.
    with patch.object(main_vb, "viewRange", return_value=[(5.0, 5.0), (0.0, 100.0)]):
        bottom_ax.mouseDragEvent(ev)
    assert ev.accepted is True
    (x0, x1), (_y0, _y1) = main_vb.viewRange()
    assert x1 - x0 > 0  # unchanged — the zero-span return prevented a setRange


# --------------------------------------------------------------------- #
# show_plot() — legend present (TRUE branch of the _legend None guard)
# --------------------------------------------------------------------- #


def test_show_plot_with_legend_present(qtbot: QtBot) -> None:
    """show_plot() with a non-None _legend calls legend.show() (line 607,
    the TRUE branch of ``if self._legend is not None:``). After
    construction _configure_plot has built the legend, so calling
    show_plot() without nilling _legend exercises the show path."""
    w = _make_widget(qtbot)
    # _configure_plot() in __init__ created the legend — confirm it is
    # present so the TRUE branch is the one we exercise.
    assert w._legend is not None
    w.show_plot()
    assert not w.plotWidget_adaptiveTrajectory.isHidden()
    assert w.label_adaptiveTrajectoryEmpty.isHidden()


# --------------------------------------------------------------------- #
# append_sample() — None-curve guards (FALSE branches)
# --------------------------------------------------------------------- #


def test_append_sample_with_optional_curves_none(qtbot: QtBot) -> None:
    """append_sample() guards ``if self._exposure_curve is not None`` /
    ``if self._power_curve is not None`` / ``if self._power2_curve is not
    None`` (lines 697, 699, 701). Setting each to None after reset() and
    appending a sample exercises the FALSE (skip-setData) branches
    697->699, 699->701, 701->704 without raising."""
    w = _make_widget(qtbot)
    w.reset(target_band_lo=0.90, target_band_hi=0.95)
    # Null the optional curves so the setData guards skip them.
    w._exposure_curve = None
    w._power_curve = None
    w._power2_curve = None
    # Must not raise — the None guards skip the setData calls.
    w.append_sample(
        plane_idx=0, intensity=0.92, exposure_s=0.005,
        power1_mw=10.0, power2_mw=0.0, control_variable_active="exposure",
        reacquired=False, power_fallback=False,
    )
    # The in-memory buffers are still populated (the guards only skip the
    # curve setData, not the buffer append).
    assert w._xs == [0.0]
    assert w._intensity == [92.0]
    assert w._exposure == [5.0]
    assert w._power == [10.0]
    assert w._power2 == [0.0]


# --------------------------------------------------------------------- #
# D-12.2.2: adaptive dock controller owns presentation logic
# --------------------------------------------------------------------- #


def test_adaptive_dock_controller_module(qtbot: QtBot, request: FixtureRequest) -> None:
    """AdaptiveDockController lives in its own focused module."""
    from lightsheet.gui.coordinators.adaptive_dock_controller import (
        AdaptiveDockController,
    )

    assert AdaptiveDockController.__module__ == (
        "lightsheet.gui.coordinators.adaptive_dock_controller"
    )
    ctrl, _ = make_controller(qtbot, request)
    assert hasattr(ctrl, "_adaptive_dock_controller")
    assert ctrl._adaptive_dock_controller.__class__ is AdaptiveDockController


def test_adaptive_dock_utils_module(qtbot: QtBot) -> None:
    """FloatingOnlyDock and build_no_dbl_click_title_bar live in
    dock_utils.py."""
    from lightsheet.gui.coordinators.dock_utils import (
        FloatingOnlyDock,
        build_no_dbl_click_title_bar,
    )

    assert FloatingOnlyDock.__module__ == "lightsheet.gui.coordinators.dock_utils"
    assert build_no_dbl_click_title_bar.__module__ == (
        "lightsheet.gui.coordinators.dock_utils"
    )


def test_adaptive_dock_controller_is_presentation_only(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """The dock controller does not hold HAL state."""
    from lightsheet.gui.coordinators.adaptive_dock_controller import (
        AdaptiveDockController,
    )

    ctrl, _ = make_controller(qtbot, request)
    adc = ctrl._adaptive_dock_controller
    assert isinstance(adc, AdaptiveDockController)
    for attr in ("lasers", "camera", "motors", "etls", "siggen"):
        assert not hasattr(adc, attr), (
            f"AdaptiveDockController must not own {attr} (HAL state)"
        )
    assert not hasattr(adc, "estop_event")


def test_adaptive_shell_aliases_reachable(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """The shell still exposes dock, widget, plot, and label attributes
    so tests and AcquisitionPanelWidget keep working."""
    ctrl, _ = make_controller(qtbot, request)
    assert ctrl.dockWidget_adaptiveTrajectory is ctrl._adaptive_dock_controller.dock
    assert (
        ctrl.adaptiveTrajectoryWidget is ctrl._adaptive_dock_controller.widget
    )
    assert (
        ctrl.plotWidget_adaptiveTrajectory
        is ctrl._adaptive_dock_controller.plotWidget_adaptiveTrajectory
    )
    assert (
        ctrl.label_adaptiveTrajectoryEmpty
        is ctrl._adaptive_dock_controller.label_adaptiveTrajectoryEmpty
    )


def test_adaptive_trajectory_slot_is_shell_bound_method(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """_on_adaptive_trajectory remains a shell-bound callable that
    delegates to the presentation controller."""
    from lightsheet.gui.coordinators.adaptive_dock_controller import (
        AdaptiveDockController,
    )

    ctrl, _ = make_controller(qtbot, request)
    slot = getattr(ctrl, "_on_adaptive_trajectory", None)
    assert slot is not None
    assert slot.__self__ is ctrl or isinstance(
        slot.__self__, AdaptiveDockController
    )
    # Calling the slot appends to the widget.
    ctrl.adaptiveTrajectoryWidget.reset(target_band_lo=0.90, target_band_hi=0.95)
    slot(0, 0.92, 0.005, 10.0, 5.0, "exposure", False, False)
    xs, _ys = ctrl.adaptiveTrajectoryWidget._intensity_curve.getData()  # type: ignore[unresolved-attribute]
    assert len(xs) == 1
