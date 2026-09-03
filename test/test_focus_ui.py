"""Runtime widget, validation, and pre-sampling tests for the Stack-panel
Focus Control group.

Constructs the real ``Controller_MainWindow`` via the shared
``make_controller`` fixture (AGENTS.md §5) so the panel ``__init__``
applySpec loop + the focus group wiring run against the real widget tree.
Headless via ``QT_QPA_PLATFORM=offscreen`` (set by conftest).

Covers the operator-facing contracts:
- The focus group widgets exist with the exact UI-SPEC objectNames.
- The block-size spinbox is a promoted ``FieldSpecSpinBox``.
- The enable toggle hides only the fields container.
- Browse opens a JSON-only ``QFileDialog``.
- Load Calibration arms the panel or emits the documented error copy.
- Out-of-range block-size edits beep and revert to the nearest bound.
- ``build_focus_config`` returns ``None`` when unchecked/unarmed and a
  frozen ``FocusConfig`` when armed.
- ``build_focus_curve`` returns the exact ``FocusCurve`` object already
  parsed by Load Calibration.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest
from pytest import FixtureRequest
from pytestqt.qtbot import QtBot

pytest.importorskip("PySide6")

from _helpers.controller_fixture import make_controller

from lightsheet.focus.types import AutofocusConfig, FocusConfig, FocusCurve
from lightsheet.gui.widgets.field_spec_spinbox import FieldSpecSpinBox

if TYPE_CHECKING:
    from lightsheet.gui.panels.ui_stack_panel import Ui_StackPanel
    from lightsheet.gui.shell.controller import Controller_MainWindow

FOCUS_WIDGET_NAMES = (
    "groupBox_focusControl",
    "checkBox_focusEnable",
    "widget_focusFields",
    "lineEdit_focusCurvePath",
    "pushButton_focusBrowse",
    "pushButton_focusLoad",
    "doubleSpinBox_focusBlockSize",
    "checkBox_focusAutofocusResidual",
    "line_focusResidualSeparator",
    "comboBox_focusXAxisVariable",
    "label_focusStatus",
    "label_focusBlockHint",
    "label_focusXAxisVariable",
)

AUTOFOCUS_WIDGET_NAMES = (
    "checkBox_adaptiveAutofocus",
    "line_autofocusSeparator",
    "widget_adaptiveAutofocusFields",
    "doubleSpinBox_autofocusCadence",
    "doubleSpinBox_autofocusResidualGain",
    "doubleSpinBox_autofocusMaxResidual",
    "doubleSpinBox_autofocusSmoothing",
    "checkBox_autofocusUseCurve",
    "label_autofocusStatus",
    "label_autofocusHint",
    "progressBar_autofocus",
)


def _focus_ui(ctrl: Controller_MainWindow) -> Ui_StackPanel:
    """Return the stack panel focus group widgets as a namespace."""
    return ctrl.stack_panel.ui


def _valid_calibration_json() -> str:
    """A 3-point calibration curve with camera positions inside the mock
    0-35 mm travel range."""
    return '{"points": [[0.0, 20.0], [10.0, 22.0], [20.0, 24.0]]}'


def test_focus_group_widgets_exist(qtbot: QtBot, request: FixtureRequest) -> None:
    """The focus control group and its child widgets exist on the stack
    panel with the exact UI-SPEC objectNames."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _focus_ui(ctrl)
    for name in FOCUS_WIDGET_NAMES:
        assert hasattr(ui, name), f"missing focus widget {name}"


def test_focus_x_axis_combo_has_only_block(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """The focus X-axis combo contains only "Block"; the
    "Stage position (mm)" option has been removed."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _focus_ui(ctrl)
    combo = ui.comboBox_focusXAxisVariable
    assert combo.count() == 1, f"expected one X-axis option, got {combo.count()}"
    assert combo.currentText() == "Block"


def test_focus_block_size_is_field_spec_subclass(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """The focus block-size spinbox is a promoted FieldSpecSpinBox."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _focus_ui(ctrl)
    sb = ui.doubleSpinBox_focusBlockSize
    assert isinstance(sb, FieldSpecSpinBox), (
        f"doubleSpinBox_focusBlockSize is {type(sb).__name__}, not FieldSpecSpinBox"
    )


def test_focus_toggle_off_hides_only_fields_container(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """When the toggle is unchecked, only the fields container is hidden
    -- the group box title row stays visible."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _focus_ui(ctrl)
    ui.checkBox_focusEnable.setChecked(False)
    ui.checkBox_focusEnable.toggled.emit(False)
    from PySide6.QtWidgets import QApplication

    QApplication.processEvents()
    fields_parent = ui.widget_focusFields.parentWidget()
    group_parent = ui.groupBox_focusControl.parentWidget()
    assert fields_parent is not None
    assert group_parent is not None
    assert not ui.widget_focusFields.isVisibleTo(fields_parent)
    assert ui.groupBox_focusControl.isVisibleTo(group_parent)


def test_focus_toggle_on_shows_fields_container(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """When the toggle is checked, the fields container becomes visible."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _focus_ui(ctrl)
    ui.checkBox_focusEnable.setChecked(True)
    ui.checkBox_focusEnable.toggled.emit(True)
    from PySide6.QtWidgets import QApplication

    QApplication.processEvents()
    fields_parent = ui.widget_focusFields.parentWidget()
    assert fields_parent is not None
    assert ui.widget_focusFields.isVisibleTo(fields_parent)


def test_focus_browse_filter_is_json_only(
    qtbot: QtBot, request: FixtureRequest, tmp_path: Any
) -> None:
    """pushButton_focusBrowse opens a QFileDialog restricted to *.json
    (plus All files) and writes the chosen path into the line edit."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _focus_ui(ctrl)
    chosen = str(tmp_path / "curve.json")
    with patch(
        "lightsheet.gui.panels.stack_panel.QFileDialog.getOpenFileName",
        return_value=(chosen, ""),
    ) as mock_getopen:
        ui.pushButton_focusBrowse.click()
    assert ui.lineEdit_focusCurvePath.text() == chosen
    assert mock_getopen.called, "QFileDialog.getOpenFileName was not called"
    filter_str = mock_getopen.call_args[0][-1]
    assert isinstance(filter_str, str)
    assert "*.json" in filter_str, f"filter missing *.json: {filter_str!r}"
    assert "*.yaml" not in filter_str and "*.csv" not in filter_str, (
        f"filter advertises unsupported formats: {filter_str!r}"
    )


def test_load_calibration_arms_status_label(
    qtbot: QtBot, request: FixtureRequest, tmp_path: Any
) -> None:
    """Load Calibration on a valid 3-point JSON file arms focus and
    updates label_focusStatus with the exact armed copy."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _focus_ui(ctrl)
    path = tmp_path / "curve.json"
    path.write_text(_valid_calibration_json())
    ui.checkBox_focusEnable.setChecked(True)
    ui.lineEdit_focusCurvePath.setText(str(path))
    ui.pushButton_focusLoad.click()
    status = ui.label_focusStatus.text()
    assert "Armed: 3 points" in status, f"unexpected status: {status!r}"
    assert "block size 8" in status, f"unexpected status: {status!r}"
    assert "per-block residual on" in status.lower(), f"unexpected status: {status!r}"


def test_demo_mode_preloads_sample_focus_curve(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """Demo mode auto-arms the bundled sample focus calibration so the
    feature is ready without a file dialog."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _focus_ui(ctrl)
    assert ctrl.stack_panel._armed_focus_curve is not None
    assert "focus_sample_calibration.json" in ui.lineEdit_focusCurvePath.text()
    assert "Armed: 3 points" in ui.label_focusStatus.text()


def test_load_calibration_invalid_file_shows_error_copy(
    qtbot: QtBot, request: FixtureRequest, tmp_path: Any
) -> None:
    """Load Calibration on a malformed/out-of-range file emits
    sig_beep + sig_message with the documented invalid-file copy and
    sets label_focusStatus to 'Invalid file -- {reason}'."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _focus_ui(ctrl)
    beeps: list[None] = []
    messages: list[str] = []
    ctrl.sig_beep.connect(lambda: beeps.append(None))
    ctrl.sig_message.connect(messages.append)
    path = tmp_path / "bad.json"
    # Camera position 200 mm is outside the mock camera travel limits.
    path.write_text('{"points": [[0.0, 200.0], [1.0, 201.0]]}')
    ui.checkBox_focusEnable.setChecked(True)
    ui.lineEdit_focusCurvePath.setText(str(path))
    ui.pushButton_focusLoad.click()
    assert len(beeps) == 1, "invalid calibration must beep"
    assert len(messages) == 1, "invalid calibration must emit a message"
    assert "Focus calibration file invalid" in messages[0]
    assert str(path) in messages[0]
    assert "Invalid file" in ui.label_focusStatus.text()


def test_focus_block_size_editing_finished_reverts_out_of_range(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """editingFinished on doubleSpinBox_focusBlockSize with a typed value
    of 0 or 150 beeps and reverts to 1 or 100 respectively."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _focus_ui(ctrl)
    beeps: list[None] = []
    ctrl.sig_beep.connect(lambda: beeps.append(None))
    sb = ui.doubleSpinBox_focusBlockSize
    # Widen the soft range temporarily so the test can inject an
    # out-of-range value; the editingFinished handler is the guard.
    sb.setRange(0, 200)
    sb.setValue(0)
    sb.editingFinished.emit()
    assert sb.value() == 1.0, f"expected 1, got {sb.value()}"
    assert len(beeps) == 1, "out-of-range low must beep"
    beeps.clear()
    sb.setRange(0, 200)
    sb.setValue(150)
    sb.editingFinished.emit()
    assert sb.value() == 100.0, f"expected 100, got {sb.value()}"
    assert len(beeps) == 1, "out-of-range high must beep"


def test_build_focus_config_returns_none_when_unarmed(
    qtbot: QtBot, request: FixtureRequest, tmp_path: Any
) -> None:
    """build_focus_config returns None when unchecked or unarmed; it
    returns a frozen FocusConfig with the armed path and current widget
    values when a valid file is loaded."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _focus_ui(ctrl)
    # Unchecked -> None.
    ui.checkBox_focusEnable.setChecked(False)
    assert ctrl.stack_panel.build_focus_config() is None
    # Checked but no file loaded -> None (clear any demo auto-loaded curve).
    ui.checkBox_focusEnable.setChecked(True)
    ui.lineEdit_focusCurvePath.setText("")
    ui.pushButton_focusLoad.click()
    assert ctrl.stack_panel.build_focus_config() is None
    # Load a valid file.
    path = tmp_path / "curve.json"
    path.write_text(_valid_calibration_json())
    ui.lineEdit_focusCurvePath.setText(str(path))
    ui.pushButton_focusLoad.click()
    cfg = ctrl.stack_panel.build_focus_config()
    assert cfg is not None
    assert isinstance(cfg, FocusConfig)
    assert cfg.enabled is True
    assert cfg.block_size_n == 8
    assert cfg.autofocus_residual is True
    assert cfg.curve_path == str(path)
    # FocusConfig is frozen.
    with pytest.raises(AttributeError):
        setattr(cfg, "block_size_n", 99)  # noqa: B010


def test_build_focus_curve_returns_loaded_curve_object(
    qtbot: QtBot, request: FixtureRequest, tmp_path: Any
) -> None:
    """build_focus_curve returns the exact FocusCurve object produced by
    a successful pushButton_focusLoad call, or None when unchecked or
    unarmed."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _focus_ui(ctrl)
    ui.checkBox_focusEnable.setChecked(True)
    expected = FocusCurve(stage_pos=(0.0, 10.0, 20.0), camera_pos=(20.0, 22.0, 24.0))
    ui.lineEdit_focusCurvePath.setText(str(tmp_path / "curve.json"))
    with patch(
        "lightsheet.gui.panels.stack_panel.load_focus_curve",
        return_value=expected,
    ) as mock_load:
        ui.pushButton_focusLoad.click()
    assert mock_load.called
    curve = ctrl.stack_panel.build_focus_curve()
    assert curve is expected, "build_focus_curve did not return the armed curve"
    # Unchecked returns None even though a curve is still armed.
    ui.checkBox_focusEnable.setChecked(False)
    assert ctrl.stack_panel.build_focus_curve() is None


# ================================================================= #
# D-11.6 telemetry UI: focus trajectory dock, badge, worker wiring,
# E-stop freeze, and pre-sampling. RED tests for the Task 3 contract.
# ================================================================= #

EMPTY_FOCUS_COPY = (
    "No focus run yet. Enable Camera focus compensation in the Stack panel, "
    "load a calibration file, and start a stack to see the focus trajectory."
)


def _focus_trajectory_widget(qtbot: QtBot) -> Any:
    """Construct a FocusTrajectoryWidget headless for unit testing.

    Imported lazily so collection succeeds in the RED state.
    """
    try:
        from lightsheet.gui.widgets.focus_trajectory import FocusTrajectoryWidget
    except ImportError as exc:
        pytest.fail(f"FocusTrajectoryWidget not importable: {exc}")
    widget = FocusTrajectoryWidget()
    qtbot.addWidget(widget)
    return widget


def test_focus_dock_exists_and_hidden_initially(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """The focus trajectory dock is created and hidden until the
    operator enables focus compensation."""
    ctrl, _ = make_controller(qtbot, request)
    dock = getattr(ctrl, "dockWidget_focusTrajectory", None)
    assert dock is not None, "dockWidget_focusTrajectory must exist on the shell"
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QDockWidget

    assert isinstance(dock, QDockWidget)
    assert dock.allowedAreas() == Qt.DockWidgetArea.NoDockWidgetArea
    assert not dock.isVisible()


def test_enabling_focus_shows_rail_button_not_dock(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """Checking focus enable shows the conditional rail button so the
    operator can open the trajectory dock on demand. The dock itself does
    NOT open automatically."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _focus_ui(ctrl)
    ui.checkBox_focusEnable.setChecked(True)
    ui.checkBox_focusEnable.toggled.emit(True)
    from PySide6.QtWidgets import QApplication

    QApplication.processEvents()
    assert not ctrl.ui.toolButton_railFocus.isHidden(), (
        "rail button must be visible when focus is enabled"
    )
    dock = ctrl.dockWidget_focusTrajectory
    assert dock.isHidden(), (
        "dock must NOT auto-open when focus is enabled; "
        "the operator opens it via the rail button"
    )


def test_focus_rail_button_opens_dock_floating(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """Toggling the focus rail button opens the trajectory dock as a
    standalone floating window (never docked into the main GUI)."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _focus_ui(ctrl)
    ui.checkBox_focusEnable.setChecked(True)
    ui.checkBox_focusEnable.toggled.emit(True)
    from PySide6.QtWidgets import QApplication

    QApplication.processEvents()
    dock = ctrl.dockWidget_focusTrajectory
    assert dock.isHidden()
    ctrl.ui.toolButton_railFocus.setChecked(True)
    ctrl.ui.toolButton_railFocus.toggled.emit(True)
    QApplication.processEvents()
    assert not dock.isHidden(), "dock must open when rail button is checked"
    assert dock.isFloating(), (
        "dock must be a floating window, not docked into the main GUI"
    )
    widget = ctrl.focusTrajectoryWidget
    assert not widget.label_focusTrajectoryEmpty.isHidden()
    assert widget.plotWidget_focusTrajectory.isHidden()


def test_focus_rail_button_closes_dock(qtbot: QtBot, request: FixtureRequest) -> None:
    """Unchecking the focus rail button hides the trajectory dock."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _focus_ui(ctrl)
    ui.checkBox_focusEnable.setChecked(True)
    ui.checkBox_focusEnable.toggled.emit(True)
    from PySide6.QtWidgets import QApplication

    QApplication.processEvents()
    ctrl.ui.toolButton_railFocus.setChecked(True)
    ctrl.ui.toolButton_railFocus.toggled.emit(True)
    QApplication.processEvents()
    assert not ctrl.dockWidget_focusTrajectory.isHidden()
    ctrl.ui.toolButton_railFocus.setChecked(False)
    ctrl.ui.toolButton_railFocus.toggled.emit(False)
    QApplication.processEvents()
    assert ctrl.dockWidget_focusTrajectory.isHidden()


def test_focus_dock_visibility_syncs_rail_button(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """Closing the dock via its close button unchecks the rail button."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _focus_ui(ctrl)
    ui.checkBox_focusEnable.setChecked(True)
    ui.checkBox_focusEnable.toggled.emit(True)
    from PySide6.QtWidgets import QApplication

    QApplication.processEvents()
    ctrl.ui.toolButton_railFocus.setChecked(True)
    ctrl.ui.toolButton_railFocus.toggled.emit(True)
    QApplication.processEvents()
    assert ctrl.ui.toolButton_railFocus.isChecked()
    ctrl.dockWidget_focusTrajectory.close()
    QApplication.processEvents()
    assert not ctrl.ui.toolButton_railFocus.isChecked()


def test_empty_state_label_has_exact_copy(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """The empty-state label carries the exact UI-SPEC copy and is
    word-wrapped."""
    ctrl, _ = make_controller(qtbot, request)
    label = getattr(ctrl, "label_focusTrajectoryEmpty", None)
    assert label is not None, "label_focusTrajectoryEmpty must exist on the shell"
    assert label.wordWrap() is True
    assert EMPTY_FOCUS_COPY in label.text() or "No focus run yet" in label.text()


def test_focus_trajectory_widget_empty_state(qtbot: QtBot) -> None:
    """set_empty shows the empty-state label and hides the plot."""
    w = _focus_trajectory_widget(qtbot)
    w.set_empty()
    assert not w.label_focusTrajectoryEmpty.isHidden()
    assert w.plotWidget_focusTrajectory.isHidden()


def test_focus_trajectory_widget_appends_block(qtbot: QtBot) -> None:
    """append_sample with one block swaps to the plot and draws the
    camera-position curve."""
    w = _focus_trajectory_widget(qtbot)
    w.reset()
    w.append_sample(
        block_idx=0,
        stage_pos_mm=0.01,
        camera_pos_mm=20.0,
        residual_mm=0.0,
        x_axis_value=0.0,
    )
    assert not w.plotWidget_focusTrajectory.isHidden()
    assert w.label_focusTrajectoryEmpty.isHidden()
    curve = w._camera_curve
    assert curve is not None
    xs, ys = curve.getData()
    assert len(xs) == 1 and len(ys) == 1
    assert ys[0] == pytest.approx(20.0)


def test_focus_trajectory_widget_residual_marker(qtbot: QtBot) -> None:
    """A non-zero residual at a block renders a warning-olive diamond
    marker on that block."""
    w = _focus_trajectory_widget(qtbot)
    w.reset()
    w.append_sample(
        block_idx=1,
        stage_pos_mm=0.02,
        camera_pos_mm=21.0,
        residual_mm=0.05,
        x_axis_value=0.0,
    )
    scatter = w._residual_scatter
    assert scatter is not None
    spots = scatter.getData()
    assert len(spots[0]) == 1


def test_focus_trajectory_widget_freeze_blocks_appends(qtbot: QtBot) -> None:
    """After freeze() (E-stop), further append_sample calls are ignored."""
    w = _focus_trajectory_widget(qtbot)
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
        x_axis_value=0.0,
    )
    assert w._camera_curve is not None
    xs, _ys = w._camera_curve.getData()
    assert len(xs) == 1, "post-freeze append must be ignored"


def test_badge_focus_running_string(qtbot: QtBot, request: FixtureRequest) -> None:
    """The badge renders 'FOCUS RUNNING — plane {n}/{N}' with the em-dash."""
    ctrl, _ = make_controller(qtbot, request)
    ctrl.number_of_planes = 50
    ctrl._update_mode_badge("FOCUS", "RUNNING", plane=12, total=50)
    text = ctrl.ui.label_modeBadge.text()
    assert "FOCUS RUNNING" in text
    assert "\u2014" in text
    assert "plane 12/50" in text


def test_badge_focus_aborted_string(qtbot: QtBot, request: FixtureRequest) -> None:
    """E-stop mid-focus-run transitions the badge to 'FOCUS ABORTED'."""
    ctrl, _ = make_controller(qtbot, request)
    ctrl.number_of_planes = 50
    ctrl._update_mode_badge("FOCUS", "ABORTED", plane=12, total=50)
    text = ctrl.ui.label_modeBadge.text()
    assert "FOCUS ABORTED" in text
    assert "plane 12/50" in text


def test_spawn_stack_worker_passes_frozen_focus_cfg_and_curve(
    qtbot: QtBot, request: FixtureRequest, tmp_path: Any
) -> None:
    """`_spawn_stack_worker` pre-samples focus config and curve on the GUI
    thread and passes them as StackWorker constructor args."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _focus_ui(ctrl)
    path = tmp_path / "curve.json"
    path.write_text('{"points": [[0.0, 20.0], [10.0, 22.0], [20.0, 24.0]]}')
    ui.checkBox_focusEnable.setChecked(True)
    ui.lineEdit_focusCurvePath.setText(str(path))
    ui.pushButton_focusLoad.click()
    ctrl.stack_first_plane_set = True
    ctrl.stack_last_plane_set = True
    ctrl.stack_starting_plane = 0.0
    ctrl.stack_ending_plane = 100.0
    ctrl.number_of_planes = 2
    ctrl.saving_allowed = True
    captured: dict[str, Any] = {}
    import lightsheet.gui.workers as workers_mod

    orig_init = workers_mod.StackWorker.__init__

    def capture_init(self: Any, *args: Any, **kwargs: Any) -> None:
        captured["focus_cfg"] = kwargs.get("focus_cfg")
        captured["focus_curve"] = kwargs.get("focus_curve")
        orig_init(self, *args, **kwargs)

    with patch.object(workers_mod.StackWorker, "__init__", capture_init):
        try:
            ctrl.acquisition_panel._spawn_stack_worker()
        finally:
            thread = getattr(ctrl, "_stack_thread", None)
            if thread is not None and thread.isRunning():
                thread.quit()
                thread.wait(2000)

    assert captured.get("focus_cfg") is not None
    assert captured.get("focus_curve") is not None
    assert isinstance(captured["focus_cfg"], FocusConfig)
    assert captured["focus_curve"] == ctrl.stack_panel.build_focus_curve()


def test_spawn_stack_worker_keeps_plot_visible_when_focus_dock_open(
    qtbot: QtBot, request: FixtureRequest, tmp_path: Any
) -> None:
    """When the focus trajectory dock is already open, _spawn_stack_worker
    does not re-hide the plot/legend."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _focus_ui(ctrl)
    path = tmp_path / "curve.json"
    path.write_text('{"points": [[0.0, 20.0], [10.0, 22.0], [20.0, 24.0]]}')
    ui.checkBox_focusEnable.setChecked(True)
    ui.checkBox_focusEnable.toggled.emit(True)
    ui.lineEdit_focusCurvePath.setText(str(path))
    ui.pushButton_focusLoad.click()
    ctrl.stack_first_plane_set = True
    ctrl.stack_last_plane_set = True
    ctrl.stack_starting_plane = 0.0
    ctrl.stack_ending_plane = 100.0
    ctrl.number_of_planes = 2
    ctrl.saving_allowed = True
    from PySide6.QtWidgets import QApplication

    QApplication.processEvents()
    # Open the focus dock via the rail button so the visible branch is taken.
    ctrl.ui.toolButton_railFocus.setChecked(True)
    ctrl.ui.toolButton_railFocus.toggled.emit(True)
    QApplication.processEvents()
    assert not ctrl.dockWidget_focusTrajectory.isHidden()

    try:
        ctrl.acquisition_panel._spawn_stack_worker()
    finally:
        thread = getattr(ctrl, "_stack_thread", None)
        if thread is not None and thread.isRunning():
            thread.quit()
            thread.wait(2000)

    # The plot should still be visible because the dock was already open.
    assert not ctrl.focusTrajectoryWidget.plotWidget_focusTrajectory.isHidden()


def test_estop_freezes_focus_trajectory_and_sets_badge(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """E-stop performs synchronous laser.off() first, then freezes the
    focus trajectory plot and sets the badge to FOCUS ABORTED."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _focus_ui(ctrl)
    # Arm a valid focus curve and enable focus.
    path = Path(str(getattr(ctrl, "save_directory", "/tmp"))) / "focus_curve.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"points": [[0.0, 20.0], [10.0, 22.0], [20.0, 24.0]]}')
    ui.checkBox_focusEnable.setChecked(True)
    ui.checkBox_focusEnable.toggled.emit(True)
    ui.lineEdit_focusCurvePath.setText(str(path))
    ui.pushButton_focusLoad.click()
    from PySide6.QtWidgets import QApplication

    QApplication.processEvents()
    widget = ctrl.focusTrajectoryWidget
    widget.reset()
    widget.append_sample(
        block_idx=0,
        stage_pos_mm=0.0,
        camera_pos_mm=20.0,
        residual_mm=0.0,
        x_axis_value=0.0,
    )
    off_calls: list[int] = []
    real_off = [laser.off for laser in ctrl.lasers]

    def _tracking_off(idx: int) -> Any:
        def _off() -> None:
            if widget._frozen:
                off_calls.append(-1)
            off_calls.append(idx)
            real_off[idx]()

        return _off

    for idx, laser in enumerate(ctrl.lasers):
        laser.off = _tracking_off(idx)
    ctrl.updateUi_estop_pressed()
    QApplication.processEvents()
    assert 0 in off_calls and 1 in off_calls
    assert -1 not in off_calls, "freeze must happen after laser.off()"
    assert widget._frozen is True
    assert "FOCUS ABORTED" in ctrl.ui.label_modeBadge.text()


def test_spawn_stack_worker_sets_focus_mode_flag_when_enabled(
    qtbot: QtBot, request: FixtureRequest, tmp_path: Any
) -> None:
    """When focus is enabled and armed, _spawn_stack_worker sets
    focus_mode_started so the badge shows FOCUS RUNNING."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _focus_ui(ctrl)
    path = tmp_path / "curve.json"
    path.write_text('{"points": [[0.0, 20.0], [10.0, 22.0], [20.0, 24.0]]}')
    ui.checkBox_focusEnable.setChecked(True)
    ui.checkBox_focusEnable.toggled.emit(True)
    ui.lineEdit_focusCurvePath.setText(str(path))
    ui.pushButton_focusLoad.click()
    ctrl.stack_first_plane_set = True
    ctrl.stack_last_plane_set = True
    ctrl.stack_starting_plane = 0.0
    ctrl.stack_ending_plane = 100.0
    ctrl.number_of_planes = 5
    ctrl.saving_allowed = True
    ctrl.acquisition_panel._spawn_stack_worker()
    thread = getattr(ctrl, "_stack_thread", None)
    if thread is not None and thread.isRunning():
        thread.quit()
        thread.wait(2000)
    assert ctrl.focus_mode_started is True


def test_spawn_stack_worker_clears_focus_mode_flag_when_disabled(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """When focus is disabled, _spawn_stack_worker leaves focus_mode_started
    False so the badge stays STACK RUNNING."""
    ctrl, _ = make_controller(qtbot, request)
    _focus_ui(ctrl)
    ctrl.stack_first_plane_set = True
    ctrl.stack_last_plane_set = True
    ctrl.stack_starting_plane = 0.0
    ctrl.stack_ending_plane = 100.0
    ctrl.number_of_planes = 5
    ctrl.saving_allowed = True
    ctrl.acquisition_panel._spawn_stack_worker()
    thread = getattr(ctrl, "_stack_thread", None)
    if thread is not None and thread.isRunning():
        thread.quit()
        thread.wait(2000)
    assert ctrl.focus_mode_started is False


def test_progress_update_shows_focus_running_badge(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """_on_progress_update uses FOCUS mode when focus_mode_started is True."""
    ctrl, _ = make_controller(qtbot, request)
    _focus_ui(ctrl)
    ctrl.stack_mode_started = True
    ctrl.focus_mode_started = True
    ctrl.number_of_planes = 5
    ctrl._on_progress_update(2)
    text = ctrl.ui.label_modeBadge.text()
    assert "FOCUS RUNNING" in text
    assert "2/5" in text


def test_autofocus_group_widgets_exist(qtbot: QtBot, request: FixtureRequest) -> None:
    """The adaptive-autofocus control group and its child widgets exist with
    the UI-SPEC objectNames."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _focus_ui(ctrl)
    for name in AUTOFOCUS_WIDGET_NAMES:
        assert hasattr(ui, name), f"missing autofocus widget {name}"


def test_build_autofocus_config_returns_none_when_disabled(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """build_autofocus_config returns None when adaptive is unchecked."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _focus_ui(ctrl)
    ui.checkBox_adaptiveAutofocus.setChecked(False)
    assert ctrl.stack_panel.build_autofocus_config() is None


def test_build_autofocus_config_returns_frozen_values_when_enabled(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """build_autofocus_config returns a frozen AutofocusConfig with the
    current widget values when adaptive is checked."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _focus_ui(ctrl)
    ui.checkBox_adaptiveAutofocus.setChecked(True)
    ui.checkBox_adaptiveAutofocus.toggled.emit(True)
    ui.doubleSpinBox_autofocusCadence.setValue(5.0)
    ui.doubleSpinBox_autofocusResidualGain.setValue(0.100)
    ui.doubleSpinBox_autofocusMaxResidual.setValue(1.000)
    ui.doubleSpinBox_autofocusSmoothing.setValue(0.250)
    cfg = ctrl.stack_panel.build_autofocus_config()
    assert cfg is not None
    assert isinstance(cfg, AutofocusConfig)
    assert cfg.enabled is True
    assert cfg.cadence == 5
    assert cfg.residual_gain_mm == pytest.approx(0.1)
    assert cfg.max_residual_mm == pytest.approx(1.0)
    assert cfg.smoothing == pytest.approx(0.25)
    assert cfg.use_curve_seed is False
    with pytest.raises(AttributeError):
        setattr(cfg, "cadence", 99)  # noqa: B010


@pytest.mark.parametrize(
    "sb_name,low,high",
    [
        ("doubleSpinBox_autofocusCadence", 1.0, 1000.0),
        ("doubleSpinBox_autofocusResidualGain", 0.0, 1.0),
        ("doubleSpinBox_autofocusMaxResidual", 0.0, 5.0),
        ("doubleSpinBox_autofocusSmoothing", 0.0, 1.0),
    ],
)
def test_autofocus_spinbox_out_of_range_reverts_and_beeps(
    qtbot: QtBot,
    request: FixtureRequest,
    sb_name: str,
    low: float,
    high: float,
) -> None:
    """editingFinished on the four adaptive spinboxes beeps and clamps
    out-of-range values to the FieldSpec bounds."""
    ctrl, _ = make_controller(qtbot, request)
    sb = getattr(_focus_ui(ctrl), sb_name)
    beeps: list[None] = []
    ctrl.sig_beep.connect(lambda: beeps.append(None))
    # Widen the range temporarily so the test can inject an out-of-range value.
    sb.setRange(low - 10, high + 10)
    sb.setValue(low - 1)
    sb.editingFinished.emit()
    assert sb.value() == low, f"expected low bound {low}, got {sb.value()}"
    assert len(beeps) == 1, "out-of-range low must beep"
    beeps.clear()
    sb.setRange(low - 10, high + 10)
    sb.setValue(high + 1)
    sb.editingFinished.emit()
    assert sb.value() == high, f"expected high bound {high}, got {sb.value()}"
    assert len(beeps) == 1, "out-of-range high must beep"


def test_autofocus_use_curve_disabled_when_no_curve_armed(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """checkBox_autofocusUseCurve is disabled and unchecked when no focus
    curve is armed."""
    ctrl, _ = make_controller(qtbot, request)
    # Demo mode may pre-load a sample curve; explicitly disarm it.
    ctrl.stack_panel._clear_focus_armed()
    cb = _focus_ui(ctrl).checkBox_autofocusUseCurve
    assert not cb.isEnabled()
    assert not cb.isChecked()


def test_autofocus_status_label_is_bold(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """label_autofocusStatus uses the bold display weight."""
    ctrl, _ = make_controller(qtbot, request)
    ss = ctrl.stack_panel.ui.label_autofocusStatus.styleSheet() or ""
    assert "bold" in ss.lower(), f"expected bold stylesheet, got {ss!r}"


def test_autofocus_grid_uses_sm_spacing(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """gridLayout_adaptiveAutofocusFields uses the 8 px sm token."""
    from lightsheet.gui.styles import spacing as _s

    ctrl, _ = make_controller(qtbot, request)
    assert (
        ctrl.stack_panel.ui.gridLayout_adaptiveAutofocusFields.spacing() == _s.SM
    )


def test_legacy_residual_checkbox_text_disambiguated(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """The legacy residual checkbox no longer uses the overloaded
    'autofocus residual' label."""
    ctrl, _ = make_controller(qtbot, request)
    text = ctrl.stack_panel.ui.checkBox_focusAutofocusResidual.text().lower()
    assert "per-block residual" in text, f"unexpected checkbox text: {text!r}"
    assert "autofocus residual" not in text


def test_autofocus_no_curve_status_uses_quoted_checkbox_label(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """The no-curve empty-state copy puts the use-curve checkbox label
    in quotation marks."""
    ctrl, _ = make_controller(qtbot, request)
    # Demo mode may pre-load a sample curve; explicitly disarm it.
    ctrl.stack_panel._clear_focus_armed()
    ui = _focus_ui(ctrl)
    ui.checkBox_adaptiveAutofocus.setChecked(True)
    ui.checkBox_adaptiveAutofocus.toggled.emit(True)
    # Force the use-curve checkbox checked so the no-curve branch fires.
    ui.checkBox_autofocusUseCurve.blockSignals(True)
    ui.checkBox_autofocusUseCurve.setChecked(True)
    ui.checkBox_autofocusUseCurve.blockSignals(False)
    from PySide6.QtWidgets import QApplication

    QApplication.processEvents()
    ctrl.stack_panel._update_autofocus_status_label()
    assert '"Use loaded focus curve as seed"' in ui.label_autofocusStatus.text()


def test_set_autofocus_running_toggles_progress_and_disables_controls(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """set_autofocus_running(True) shows the progress bar, disables the
    adaptive controls, and set_autofocus_running(False) reverses it."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _focus_ui(ctrl)
    # The adaptive sub-surface lives inside the Focus Control fields container.
    ui.checkBox_focusEnable.setChecked(True)
    ui.checkBox_focusEnable.toggled.emit(True)
    ui.checkBox_adaptiveAutofocus.setChecked(True)
    ui.checkBox_adaptiveAutofocus.toggled.emit(True)
    ctrl.number_of_planes = 25
    from PySide6.QtWidgets import QApplication

    QApplication.processEvents()
    ctrl.stack_panel.set_autofocus_running(True)
    QApplication.processEvents()
    assert not ui.progressBar_autofocus.isHidden()
    assert ui.progressBar_autofocus.maximum() == 25
    assert not ui.checkBox_adaptiveAutofocus.isEnabled()
    assert not ui.widget_adaptiveAutofocusFields.isEnabled()
    assert not ui.checkBox_autofocusUseCurve.isEnabled()

    ctrl.stack_panel.set_autofocus_running(False)
    QApplication.processEvents()
    assert ui.progressBar_autofocus.isHidden()
    assert ui.checkBox_adaptiveAutofocus.isEnabled()
    assert ui.widget_adaptiveAutofocusFields.isEnabled()


def test_on_autofocus_status_updates_progress_bar(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """_on_autofocus_status mirrors the plane index into the progress bar."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _focus_ui(ctrl)
    ui.checkBox_focusEnable.setChecked(True)
    ui.checkBox_focusEnable.toggled.emit(True)
    ui.checkBox_adaptiveAutofocus.setChecked(True)
    ui.checkBox_adaptiveAutofocus.toggled.emit(True)
    ctrl.number_of_planes = 50
    ctrl.stack_panel.set_autofocus_running(True)
    from PySide6.QtWidgets import QApplication

    QApplication.processEvents()
    ctrl.stack_panel._on_autofocus_status(17, 50, 20.0, 0.0, 1.0, "tracking")
    assert ui.progressBar_autofocus.value() == 17
    assert ui.progressBar_autofocus.maximum() == 50
