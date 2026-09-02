"""Branch-coverage tests for ``lightsheet/gui/widgets/focus_trajectory.py``.

Targets the branches left uncovered by ``test_focus_ui.py``. The
FocusTrajectoryWidget reuses the same defensive-guard pattern as the
adaptive widget, so these tests cover the ``None`` branches of the
curve/scatter/legend guards and the state-machine branches
(``_frozen``, ``_run_started``, ``has_data``, sliding window).
"""

from __future__ import annotations

from typing import Any

import pyqtgraph as pg
import pytest
from pytest import FixtureRequest
from pytestqt.qtbot import QtBot

pytest.importorskip("PySide6")

from _helpers.controller_fixture import make_controller

from lightsheet.gui.widgets.focus_trajectory import FocusTrajectoryWidget


def _make_widget(qtbot: QtBot) -> FocusTrajectoryWidget:
    w = FocusTrajectoryWidget()
    qtbot.addWidget(w)
    return w


def test_reset_with_none_curves_and_legend(qtbot: QtBot) -> None:
    """reset() skips setData/show when the curves/legend are None."""
    w = _make_widget(qtbot)
    w._camera_curve = None
    w._stage_curve = None
    w._residual_scatter = None
    w._legend = None
    w.reset()
    assert w._run_started is True
    assert w.plotWidget_focusTrajectory.isVisibleTo(w.plotWidget_focusTrajectory.parentWidget())  # type: ignore[unresolved-attribute]
    assert w.label_focusTrajectoryEmpty.isHidden()


def test_set_empty_and_has_data_with_none_legend(qtbot: QtBot) -> None:
    """set_empty() and has_data() handle a None legend and empty/populated
    state."""
    w = _make_widget(qtbot)
    w._legend = None
    w.set_empty()
    assert not w.has_data()
    w.append_sample(
        block_idx=0,
        stage_pos_mm=0.0,
        camera_pos_mm=20.0,
        residual_mm=0.0,
        x_axis_value=0.0,
    )
    assert w.has_data()


def test_show_plot_and_legend_none(qtbot: QtBot) -> None:
    """show_plot() toggles the plot and skips a None legend."""
    w = _make_widget(qtbot)
    w.show_plot()
    assert not w.plotWidget_focusTrajectory.isHidden()
    w._legend = None
    w.set_empty()
    w.show_plot()
    assert not w.plotWidget_focusTrajectory.isHidden()


def test_none_guards_in_rebuild_and_append(qtbot: QtBot) -> None:
    """With the curves/scatter set to None, _rebuild_x_values and
    append_sample skip the setData calls and the residual scatter guard."""
    w = _make_widget(qtbot)
    w._camera_curve = None
    w._stage_curve = None
    w._residual_scatter = None
    w.reset()
    w.append_sample(
        block_idx=0,
        stage_pos_mm=0.01,
        camera_pos_mm=20.0,
        residual_mm=0.05,
        x_axis_value=0.0,
    )
    # The residual branch is short-circuited because _residual_scatter is None.
    assert w._residual == [0.05]


def test_append_auto_reset_and_sliding_window(qtbot: QtBot) -> None:
    """append_sample with _run_started=False auto-resets, and appending more
    than _X_WINDOW samples exercises the sliding X-window branch."""
    w = _make_widget(qtbot)
    w.set_empty()
    assert not w._run_started
    w.append_sample(
        block_idx=0,
        stage_pos_mm=0.0,
        camera_pos_mm=20.0,
        residual_mm=0.0,
        x_axis_value=0.0,
    )
    assert w._run_started
    # Append enough samples to trigger the sliding window clamp.
    for i in range(1, 210):
        w.append_sample(
            block_idx=i,
            stage_pos_mm=0.001 * i,
            camera_pos_mm=20.0 + 0.001 * i,
            residual_mm=0.0,
            x_axis_value=float(i),
        )
    assert len(w._xs) == 210


def test_freeze_blocks_appends(qtbot: QtBot) -> None:
    """freeze() makes subsequent append_sample calls no-ops."""
    w = _make_widget(qtbot)
    w.reset()
    w.append_sample(
        block_idx=0,
        stage_pos_mm=0.0,
        camera_pos_mm=20.0,
        residual_mm=0.0,
        x_axis_value=0.0,
    )
    w.freeze()
    w.append_sample(
        block_idx=1,
        stage_pos_mm=0.01,
        camera_pos_mm=20.5,
        residual_mm=0.0,
        x_axis_value=1.0,
    )
    xs, _ys = w._camera_curve.getData()  # type: ignore[unresolved-attribute]
    assert len(xs) == 1


def test_sync_right_vb_none(qtbot: QtBot) -> None:
    """The _sync_right_vbs closure safely no-ops when _right_vb is None."""
    w = _make_widget(qtbot)
    w._right_vb = None
    main_vb = w.plotWidget_focusTrajectory.getPlotItem().getViewBox()
    main_vb.sigResized.emit(main_vb)


# --------------------------------------------------------------------- #
# D-12.2.2: focus dock controller owns presentation logic
# --------------------------------------------------------------------- #


def test_focus_dock_controller_module(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """FocusDockController lives in its own focused module."""
    from lightsheet.gui.coordinators.focus_dock_controller import (
        FocusDockController,
    )

    assert FocusDockController.__module__ == (
        "lightsheet.gui.coordinators.focus_dock_controller"
    )
    ctrl, _ = make_controller(qtbot, request)
    assert hasattr(ctrl, "_focus_dock_controller")
    assert ctrl._focus_dock_controller.__class__ is FocusDockController


def test_focus_dock_controller_is_presentation_only(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """The focus dock controller does not hold HAL state."""
    from lightsheet.gui.coordinators.focus_dock_controller import (
        FocusDockController,
    )

    ctrl, _ = make_controller(qtbot, request)
    fdc = ctrl._focus_dock_controller
    assert isinstance(fdc, FocusDockController)
    for attr in ("lasers", "camera", "motors", "etls", "siggen"):
        assert not hasattr(fdc, attr), (
            f"FocusDockController must not own {attr} (HAL state)"
        )
    assert not hasattr(fdc, "estop_event")


def test_focus_shell_aliases_reachable(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """The shell still exposes focus dock/widget/plot/label attributes."""
    ctrl, _ = make_controller(qtbot, request)
    assert ctrl.dockWidget_focusTrajectory is ctrl._focus_dock_controller.dock
    assert ctrl.focusTrajectoryWidget is ctrl._focus_dock_controller.widget
    assert (
        ctrl.plotWidget_focusTrajectory
        is ctrl._focus_dock_controller.plotWidget_focusTrajectory
    )
    assert (
        ctrl.label_focusTrajectoryEmpty
        is ctrl._focus_dock_controller.label_focusTrajectoryEmpty
    )


def test_focus_trajectory_slot_is_shell_bound_method(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """_on_focus_trajectory remains a shell-bound callable that
    delegates to the presentation controller."""
    from lightsheet.gui.coordinators.focus_dock_controller import (
        FocusDockController,
    )

    ctrl, _ = make_controller(qtbot, request)
    slot = getattr(ctrl, "_on_focus_trajectory", None)
    assert slot is not None
    assert slot.__self__ is ctrl or isinstance(slot.__self__, FocusDockController)
    ctrl.focusTrajectoryWidget.reset()
    slot(
        0,
        0.01,
        20.0,
        0.0,
        20.0,
    )
    xs, _ys = ctrl.focusTrajectoryWidget._camera_curve.getData()  # type: ignore[unresolved-attribute]
    assert len(xs) == 1


def test_adaptive_and_focus_share_title_bar_helper(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """Both docks use the build_no_dbl_click_title_bar helper from
    dock_utils."""
    from lightsheet.gui.coordinators.dock_utils import (
        build_no_dbl_click_title_bar,
    )

    ctrl, _ = make_controller(qtbot, request)
    assert (
        ctrl.dockWidget_adaptiveTrajectory.titleBarWidget().__class__.__name__
        == "_NoDblClickTitleBar"
    )
    assert (
        ctrl.dockWidget_focusTrajectory.titleBarWidget().__class__.__name__
        == "_NoDblClickTitleBar"
    )
    assert build_no_dbl_click_title_bar.__module__ == (
        "lightsheet.gui.coordinators.dock_utils"
    )
