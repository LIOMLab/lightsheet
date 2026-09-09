"""Branch-coverage tests for ``lightsheet/gui/widgets/focus_trajectory.py``.

Targets the branches left uncovered by ``test_focus_ui.py``. The
FocusTrajectoryWidget reuses the same defensive-guard pattern as the
adaptive widget, so these tests cover the ``None`` branches of the
curve/scatter/legend guards and the state-machine branches
(``_frozen``, ``_run_started``, ``has_data``, sliding window).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import numpy as np
import pytest
from pytestqt.qtbot import QtBot

pytest.importorskip("PySide6")

if TYPE_CHECKING:
    from lightsheet.gui.shell.controller import Controller_MainWindow

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
    parent = w.plotWidget_focusTrajectory.parentWidget()
    assert parent is not None
    assert w.plotWidget_focusTrajectory.isVisibleTo(parent)
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
    assert w._camera_curve is not None
    xs, _ys = w._camera_curve.getData()
    assert len(xs) == 1


def test_sync_right_vb_none(qtbot: QtBot) -> None:
    """The _sync_right_vbs closure safely no-ops when _right_vb is None."""
    w = _make_widget(qtbot)
    w._right_vb = None
    main_vb = w.plotWidget_focusTrajectory.getPlotItem().getViewBox()
    main_vb.sigResized.emit(main_vb)


# --------------------------------------------------------------------- #
# Dock controller extraction: focus
# --------------------------------------------------------------------- #


def test_focus_dock_controller_module(controller: Controller_MainWindow) -> None:
    """FocusDockController lives in its own focused module."""
    from lightsheet.gui.coordinators.focus_dock_controller import (
        FocusDockController,
    )

    assert FocusDockController.__module__ == (
        "lightsheet.gui.coordinators.focus_dock_controller"
    )
    ctrl = controller
    assert hasattr(ctrl, "_focus_dock_controller")
    assert ctrl._focus_dock_controller.__class__ is FocusDockController


def test_focus_dock_controller_is_presentation_only(
    controller: Controller_MainWindow,
) -> None:
    """The focus dock controller does not hold HAL state."""
    from lightsheet.gui.coordinators.focus_dock_controller import (
        FocusDockController,
    )

    ctrl = controller
    fdc = ctrl._focus_dock_controller
    assert isinstance(fdc, FocusDockController)
    for attr in ("lasers", "camera", "motors", "etls", "siggen"):
        assert not hasattr(fdc, attr), (
            f"FocusDockController must not own {attr} (HAL state)"
        )
    assert not hasattr(fdc, "estop_event")


def test_focus_shell_aliases_reachable(controller: Controller_MainWindow) -> None:
    """The shell still exposes focus dock/widget/plot/label attributes."""
    ctrl = controller
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
    controller: Controller_MainWindow,
) -> None:
    """_on_focus_trajectory remains a shell-bound callable that
    delegates to the presentation controller."""
    from lightsheet.gui.coordinators.focus_dock_controller import (
        FocusDockController,
    )

    ctrl = controller
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
    assert ctrl.focusTrajectoryWidget._camera_curve is not None
    xs, _ys = ctrl.focusTrajectoryWidget._camera_curve.getData()
    assert len(xs) == 1


def test_adaptive_and_focus_share_title_bar_helper(
    controller: Controller_MainWindow,
) -> None:
    """Both docks use the build_no_dbl_click_title_bar helper from
    dock_utils."""
    from lightsheet.gui.coordinators.dock_utils import (
        build_no_dbl_click_title_bar,
    )

    ctrl = controller
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


# --------------------------------------------------------------------------- #
# Adaptive focus worker branches: over-travel and cadence
# --------------------------------------------------------------------------- #


def _autofocus_cfg(**overrides: Any) -> Any:
    """A standard per-plane autofocus config for branch tests."""
    from lightsheet.focus.types import AutofocusConfig

    defaults: dict[str, Any] = dict(
        enabled=True,
        cadence=1,
        residual_gain_mm=0.05,
        max_residual_mm=0.5,
        smoothing=0.5,
        use_curve_seed=False,
    )
    defaults.update(overrides)
    return AutofocusConfig(**defaults)


def _configure_autofocus_stack_plan(
    ctrl: Any, tmp_path: Any, n_planes: int = 4
) -> None:
    """Configure a valid 4-plane single-channel stack plan for autofocus."""
    ctrl.saving_allowed = True
    ctrl.number_of_planes = n_planes
    ctrl.stack_mode_started = True
    ctrl.stack_starting_plane = 0.0
    ctrl.stack_step = 10
    ctrl.save_format = "hdf5"
    ctrl.save_directory = str(tmp_path)
    ctrl.save_filepath = str(tmp_path / "autofocus_branches")
    ctrl.save_description = "autofocus branch sample"
    ctrl.current_horizontal_position_text = "0.0"
    ctrl.current_vertical_position_text = "0.0"
    ctrl.current_camera_position_text = "0.0"
    ctrl.save_panel.ui.radioButton_saveAllCrop.setChecked(False)
    ctrl.save_panel.ui.radioButton_saveAllFull.setChecked(False)


def _make_autofocus_worker(ctrl: Any, **overrides: Any) -> Any:
    """Build a single-channel StackWorker with the supplied autofocus config."""
    from lightsheet.gui.workers import StackWorker

    return StackWorker(
        ctrl._bundle,
        ctrl._hw,
        ctrl,
        save_description="autofocus branch sample",
        save_stitch_blend=False,
        save_all_crop=False,
        save_all_full=False,
        multi_channel=False,
        adaptive_cfg=None,
        autofocus_cfg=_autofocus_cfg(**overrides),
    )


def _fake_acquire_scan(worker: Any, state: dict[str, Any]) -> Any:
    """Return an ``acquire_scan`` stub that fills ``reconstructed_frame``
    with a constant 30000 frame."""

    def _acquire() -> bool:
        n_imgs = worker.siggen.waveform_cycles or 1
        imgs = worker.camera.copy_recorder_images(n_imgs)
        frame = np.asarray(imgs[0])
        frame[:] = 30000
        worker._shell.reconstructed_frame = frame
        state["acq_index"] += 1
        return True

    return _acquire


def test_autofocus_over_travel_camera_axis_aborts_with_message_and_beep(
    controller: Controller_MainWindow, tmp_path: Any
) -> None:
    """A ``ValueError`` from ``move_axes_parallel`` on the camera axis
    aborts the stack with the focus over-travel message and a beep."""
    ctrl = controller
    _configure_autofocus_stack_plan(ctrl, tmp_path, n_planes=4)

    worker = _make_autofocus_worker(ctrl)
    worker.camera.recorder_timeout_status = False
    worker.siggen.error = 0

    messages: list[str] = []
    beeps: list[None] = []
    ctrl.sig_message.connect(messages.append)
    ctrl.sig_beep.connect(lambda: beeps.append(None))

    finished_emits: list[None] = []
    worker.finished.connect(lambda: finished_emits.append(None))
    with (
        patch.object(
            worker, "acquire_scan", _fake_acquire_scan(worker, {"acq_index": 0})
        ),
        patch.object(
            worker.motors,
            "move_axes_parallel",
            side_effect=ValueError("camera out of limits"),
        ),
    ):
        worker.run()

    assert len(finished_emits) == 1
    assert len(beeps) >= 1, "expected at least one beep on over-travel abort"
    focus_msgs = [m for m in messages if "Focus move rejected" in m]
    assert len(focus_msgs) >= 1, f"expected over-travel message; got {messages}"


def test_autofocus_cadence_two_updates_residual_twice(
    controller: Controller_MainWindow, tmp_path: Any
) -> None:
    """With ``cadence=2`` over 4 planes, the residual ``update()`` is
    called exactly 2 times (planes 0 and 2)."""
    from lightsheet.focus.adaptive_controller import AdaptiveFocusController

    ctrl = controller
    _configure_autofocus_stack_plan(ctrl, tmp_path, n_planes=4)

    worker = _make_autofocus_worker(ctrl, cadence=2)
    worker.camera.recorder_timeout_status = False
    worker.siggen.error = 0

    update_calls: list[tuple[float, float]] = []
    real_update = AdaptiveFocusController.update

    def _track_update(stage_pos_mm: float, sharpness: float) -> None:
        update_calls.append((stage_pos_mm, sharpness))
        real_update(worker._autofocus_controller, stage_pos_mm, sharpness)

    finished_emits: list[None] = []
    worker.finished.connect(lambda: finished_emits.append(None))
    with (
        patch.object(
            worker, "acquire_scan", _fake_acquire_scan(worker, {"acq_index": 0})
        ),
        patch.object(AdaptiveFocusController, "update", side_effect=_track_update),
    ):
        worker.run()

    assert len(finished_emits) == 1
    assert len(update_calls) == 2, (
        f"expected 2 residual update calls; got {len(update_calls)}"
    )
