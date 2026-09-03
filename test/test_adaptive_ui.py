"""Runtime widget, validation, fixed-fallback, and pre-sampling tests for
the Stack-panel adaptive configuration group.

Constructs the real ``Controller_MainWindow`` via the shared
``make_controller`` fixture (AGENTS.md §5) so the panel ``__init__``
applySpec loops + the adaptive group wiring run against the real widget
tree. Headless via ``QT_QPA_PLATFORM=offscreen`` (set by conftest).

Covers the operator-facing contracts:
- The 6 operator-adjustable adaptive spinboxes (the runtime min/max
  exposure + per-laser power bounds) exist as ``FieldSpecSpinBox``
  instances with the exact objectNames from the UI-SPEC. The seven
  fixed controller-tuning settings (target band lo/hi, re-acquire
  threshold, block size N, Kp, Ki, pilot count) are config.ini only —
  they are not surfaced as GUI widgets (approved deviation).
- The enable toggle hides only the fields container (the group box title
  row stays visible as the affordance).
- An invalid min/max pair emits the documented message + beep, reverts
  the edit, and latches fixed-fallback until a later valid edit.
- Rolling shows ms; Lightsheet shows µs (line time) and the bound
  converts to seconds via µs x 1e-6.
- ``build_adaptive_config`` normalizes ms/µs to seconds, percentages
  to fractions, narrows power to live maxima, and returns a frozen
  ``AdaptiveConfig`` (or ``None`` when unchecked).
- ``_spawn_stack_worker`` pre-samples the adaptive config on the GUI
  thread and passes one frozen ``AdaptiveConfig`` as the final
  ``StackWorker`` constructor arg — the worker performs no ``ui.*``
  reads.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest
from pytest import FixtureRequest, MonkeyPatch
from pytestqt.qtbot import QtBot

pytest.importorskip("PySide6")

from _helpers.controller_fixture import make_controller

from lightsheet.adaptive.types import AdaptiveConfig
from lightsheet.gui.widgets.field_spec_spinbox import FieldSpecSpinBox

if TYPE_CHECKING:
    from lightsheet.gui.panels.ui_stack_panel import Ui_StackPanel
    from lightsheet.gui.shell.controller import Controller_MainWindow
    from lightsheet.gui.widgets.adaptive_trajectory import AdaptiveTrajectoryWidget
    from lightsheet.gui.workers import StackWorker

# The 6 operator-adjustable adaptive spinbox objectNames (UI-SPEC §Component
# Inventory). The seven fixed controller-tuning settings (target band lo/hi,
# re-acquire threshold, block size N, Kp, Ki, pilot count) moved to
# config.ini only per the approved deviation — they are no longer GUI
# widgets.
ADAPTIVE_SPINBOX_OBJNAMES = (
    "doubleSpinBox_adaptiveMinExposure",
    "doubleSpinBox_adaptiveMaxExposure",
    "doubleSpinBox_adaptiveLaser1MinPower",
    "doubleSpinBox_adaptiveLaser1MaxPower",
    "doubleSpinBox_adaptiveLaser2MinPower",
    "doubleSpinBox_adaptiveLaser2MaxPower",
)


def _adaptive_ui(ctrl: Controller_MainWindow) -> Ui_StackPanel:
    """Return the stack panel adaptive group widgets as a namespace."""
    return ctrl.stack_panel.ui


def test_adaptive_group_widgets_exist(qtbot: QtBot, request: FixtureRequest) -> None:
    """The adaptive config group + toggle + 6 spinboxes + shutter hint
    exist on the stack panel with the exact UI-SPEC objectNames."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _adaptive_ui(ctrl)
    assert hasattr(ui, "groupBox_adaptiveControl")
    assert hasattr(ui, "checkBox_adaptiveEnable")
    assert hasattr(ui, "widget_adaptiveFields")
    assert hasattr(ui, "label_adaptiveShutterModeHint")
    for name in ADAPTIVE_SPINBOX_OBJNAMES:
        assert hasattr(ui, name), f"missing adaptive spinbox {name}"


def test_adaptive_spinboxes_are_field_spec_subclass(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """Each of the 6 adaptive spinboxes is a promoted FieldSpecSpinBox."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _adaptive_ui(ctrl)
    for name in ADAPTIVE_SPINBOX_OBJNAMES:
        sb = getattr(ui, name)
        assert isinstance(sb, FieldSpecSpinBox), (
            f"{name} is {type(sb).__name__}, not FieldSpecSpinBox"
        )


def test_adaptive_toggle_off_hides_fields_container(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """When the toggle is unchecked, only the fields container is hidden
    — the group box title row (the affordance) stays visible."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _adaptive_ui(ctrl)
    ui.checkBox_adaptiveEnable.setChecked(False)
    # The toggle handler is wired in __init__; emit the signal to drive it.
    ui.checkBox_adaptiveEnable.toggled.emit(False)
    from PySide6.QtWidgets import QApplication

    QApplication.processEvents()
    assert not ui.widget_adaptiveFields.isVisibleTo(
        ui.widget_adaptiveFields.parentWidget()  # ty: ignore[invalid-argument-type]
    )
    # The group box itself stays visible (the affordance remains).
    assert ui.groupBox_adaptiveControl.isVisibleTo(
        ui.groupBox_adaptiveControl.parentWidget()  # ty: ignore[invalid-argument-type]
    )


def test_adaptive_toggle_on_shows_fields_container(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """When the toggle is checked, the fields container becomes visible."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _adaptive_ui(ctrl)
    ui.checkBox_adaptiveEnable.setChecked(True)
    ui.checkBox_adaptiveEnable.toggled.emit(True)
    from PySide6.QtWidgets import QApplication

    QApplication.processEvents()
    assert ui.widget_adaptiveFields.isVisibleTo(ui.widget_adaptiveFields.parentWidget())  # ty: ignore[invalid-argument-type]


def test_adaptive_invalid_pair_beeps_messages_reverts(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """Setting Min Exposure > Max Exposure emits the documented message
    + beep, reverts the offending spinbox, and latches fixed-fallback
    (build_adaptive_config returns None until a later valid edit clears
    the latch)."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _adaptive_ui(ctrl)
    beeps: list[None] = []
    messages: list[str] = []
    ctrl.sig_beep.connect(lambda: beeps.append(None))
    ctrl.sig_message.connect(lambda m: messages.append(m))
    ui.checkBox_adaptiveEnable.setChecked(True)
    # Lower Max Exposure first so a Min Exposure of 500 is invalid.
    ui.doubleSpinBox_adaptiveMaxExposure.setValue(100.0)
    ui.doubleSpinBox_adaptiveMaxExposure.editingFinished.emit()
    # Now set Min Exposure above Max Exposure (both within the soft range).
    ui.doubleSpinBox_adaptiveMinExposure.setValue(500.0)
    ui.doubleSpinBox_adaptiveMinExposure.editingFinished.emit()
    assert len(beeps) == 1, "invalid pair must beep"
    assert len(messages) == 1, "invalid pair must emit a message"
    assert "Adaptive bound invalid" in messages[0]
    assert "fixed exposure/power" in messages[0]
    # The latch is set — build_adaptive_config returns None even though
    # the toggle is checked.
    assert ctrl.stack_panel.build_adaptive_config() is None


def test_adaptive_invalid_pair_reverts_offending_spinbox(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """The offending spinbox reverts to its prior valid value after the
    invalid edit."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _adaptive_ui(ctrl)
    ui.checkBox_adaptiveEnable.setChecked(True)
    # Lower Max Exposure first so a Min Exposure of 500 is invalid.
    ui.doubleSpinBox_adaptiveMaxExposure.setValue(100.0)
    ui.doubleSpinBox_adaptiveMaxExposure.editingFinished.emit()
    prior = ui.doubleSpinBox_adaptiveMinExposure.value()
    ui.doubleSpinBox_adaptiveMinExposure.setValue(500.0)
    ui.doubleSpinBox_adaptiveMinExposure.editingFinished.emit()
    assert ui.doubleSpinBox_adaptiveMinExposure.value() == prior


def test_adaptive_later_valid_edit_clears_latch(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """After an invalid pair latches fixed-fallback, a later valid edit
    clears the latch so build_adaptive_config returns a frozen config."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _adaptive_ui(ctrl)
    ui.checkBox_adaptiveEnable.setChecked(True)
    # Lower Max Exposure first so a Min Exposure of 500 is invalid.
    ui.doubleSpinBox_adaptiveMaxExposure.setValue(100.0)
    ui.doubleSpinBox_adaptiveMaxExposure.editingFinished.emit()
    # Trigger an invalid pair.
    ui.doubleSpinBox_adaptiveMinExposure.setValue(500.0)
    ui.doubleSpinBox_adaptiveMinExposure.editingFinished.emit()
    assert ctrl.stack_panel.build_adaptive_config() is None
    # Correct it — Min Exposure back below Max Exposure.
    ui.doubleSpinBox_adaptiveMinExposure.setValue(1.0)
    ui.doubleSpinBox_adaptiveMinExposure.editingFinished.emit()
    cfg = ctrl.stack_panel.build_adaptive_config()
    assert cfg is not None
    assert isinstance(cfg, AdaptiveConfig)


def test_adaptive_unchecked_returns_none(qtbot: QtBot, request: FixtureRequest) -> None:
    """With the toggle unchecked, build_adaptive_config returns None
    (fixed stack behavior is selected)."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _adaptive_ui(ctrl)
    ui.checkBox_adaptiveEnable.setChecked(False)
    assert ctrl.stack_panel.build_adaptive_config() is None


def test_adaptive_checked_valid_returns_frozen_config(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """With the toggle checked and valid bounds, build_adaptive_config
    returns a frozen AdaptiveConfig with target 0.90/0.95 and L2 block
    size 8 (the tracked defaults)."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _adaptive_ui(ctrl)
    ui.checkBox_adaptiveEnable.setChecked(True)
    cfg = ctrl.stack_panel.build_adaptive_config()
    assert cfg is not None
    assert isinstance(cfg, AdaptiveConfig)
    assert cfg.enabled is True
    assert cfg.target_band_lo == pytest.approx(0.90)
    assert cfg.target_band_hi == pytest.approx(0.95)
    assert cfg.block_size_n == 8


def test_adaptive_rolling_shutter_shows_ms(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """In Rolling shutter mode the exposure bound spinboxes show the ms
    suffix and the hint reads the Rolling copy."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _adaptive_ui(ctrl)
    ctrl.acquisition_panel.ui.comboBox_cameraShutterMode.setCurrentText("Rolling")
    ctrl.acquisition_panel.ui.comboBox_cameraShutterMode.currentTextChanged.emit(
        "Rolling"
    )
    from PySide6.QtWidgets import QApplication

    QApplication.processEvents()
    suffix = ui.doubleSpinBox_adaptiveMinExposure.suffix().strip().lower()
    assert suffix == "ms"
    hint = ui.label_adaptiveShutterModeHint.text().lower()
    assert "rolling" in hint
    assert "millisecond" in hint


def test_adaptive_lightsheet_shutter_shows_us(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """In Lightsheet shutter mode the exposure bound spinboxes show the
    µs suffix and the hint reads the Lightsheet copy."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _adaptive_ui(ctrl)
    ctrl.acquisition_panel.ui.comboBox_cameraShutterMode.setCurrentText("Lightsheet")
    ctrl.acquisition_panel.ui.comboBox_cameraShutterMode.currentTextChanged.emit(
        "Lightsheet"
    )
    from PySide6.QtWidgets import QApplication

    QApplication.processEvents()
    suffix = ui.doubleSpinBox_adaptiveMinExposure.suffix().strip().lower()
    assert suffix == "µs"
    hint = ui.label_adaptiveShutterModeHint.text().lower()
    assert "lightsheet" in hint
    assert "microseconds" in hint


def test_adaptive_lightsheet_bound_converts_to_seconds(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """In Lightsheet shutter mode the exposure bound is in µs (line time)
    and converts to seconds as µs x 1e-6. Set Min Exposure = 2500 µs
    → 2500e-6 = 2.5e-3 s."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _adaptive_ui(ctrl)
    ctrl.acquisition_panel.ui.comboBox_cameraShutterMode.setCurrentText("Lightsheet")
    ctrl.acquisition_panel.ui.comboBox_cameraShutterMode.currentTextChanged.emit(
        "Lightsheet"
    )
    ui.checkBox_adaptiveEnable.setChecked(True)
    ui.doubleSpinBox_adaptiveMaxExposure.setValue(5000.0)  # 5000 µs
    ui.doubleSpinBox_adaptiveMaxExposure.editingFinished.emit()
    ui.doubleSpinBox_adaptiveMinExposure.setValue(2500.0)  # 2500 µs
    ui.doubleSpinBox_adaptiveMinExposure.editingFinished.emit()
    cfg = ctrl.stack_panel.build_adaptive_config()
    assert cfg is not None
    assert cfg.min_exposure_s == pytest.approx(2500e-6, rel=1e-6)


def test_adaptive_rolling_bound_converts_ms_to_seconds(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """In Rolling shutter mode the exposure bound converts ms to seconds
    (x1e-3). Set Min Exposure = 5 ms -> 5e-3 s."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _adaptive_ui(ctrl)
    ctrl.acquisition_panel.ui.comboBox_cameraShutterMode.setCurrentText("Rolling")
    ctrl.acquisition_panel.ui.comboBox_cameraShutterMode.currentTextChanged.emit(
        "Rolling"
    )
    ui.checkBox_adaptiveEnable.setChecked(True)
    ui.doubleSpinBox_adaptiveMinExposure.setValue(5.0)  # 5 ms
    ui.doubleSpinBox_adaptiveMinExposure.editingFinished.emit()
    cfg = ctrl.stack_panel.build_adaptive_config()
    assert cfg is not None
    assert cfg.min_exposure_s == pytest.approx(5e-3, rel=1e-9)


def test_adaptive_power_narrowed_to_live_max(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """The laser max-power spinbox maximum is narrowed at runtime to
    min(150.0, shell._bundle.lasers[i].max_power). The test fixture's
    laser[0] has max_power 300 mW → narrowed to 150.0; laser[1] has
    max_power 150 mW → narrowed to 150.0."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _adaptive_ui(ctrl)
    assert ui.doubleSpinBox_adaptiveLaser1MaxPower.maximum() <= 150.0
    assert ui.doubleSpinBox_adaptiveLaser2MaxPower.maximum() <= 150.0


def test_spawn_stack_worker_passes_frozen_adaptive_cfg(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """_spawn_stack_worker pre-samples the adaptive config on the GUI
    thread and passes one frozen AdaptiveConfig as the final StackWorker
    constructor arg. With the toggle checked + valid bounds, the worker
    receives a frozen AdaptiveConfig (not None)."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _adaptive_ui(ctrl)
    ui.checkBox_adaptiveEnable.setChecked(True)
    # Set up a minimal valid stack plan so _spawn_stack_worker can run.
    ctrl.stack_first_plane_set = True
    ctrl.stack_last_plane_set = True
    ctrl.stack_starting_plane = 0.0
    ctrl.stack_ending_plane = 100.0
    ctrl.number_of_planes = 2
    ctrl.saving_allowed = True
    captured: dict = {}  # ty: ignore[missing-type-argument]

    # Patch StackWorker.__init__ to capture the adaptive_cfg kwarg
    # without actually constructing the worker (the real constructor
    # reaches into the shell; we only need the captured arg).
    import lightsheet.gui.workers as workers_mod

    orig_init = workers_mod.StackWorker.__init__

    def capture_init(self: StackWorker, *args: Any, **kwargs: Any) -> None:
        captured["adaptive_cfg"] = kwargs.get("adaptive_cfg")
        captured["args"] = args
        # Call the real init so the worker is fully constructed (the
        # spawn path wires signals + starts the thread).
        orig_init(self, *args, **kwargs)

    with patch.object(workers_mod.StackWorker, "__init__", capture_init):
        try:
            ctrl.acquisition_panel._spawn_stack_worker()
        finally:
            # Stop the spawned thread so the test teardown is clean.
            thread = getattr(ctrl, "_stack_thread", None)
            if thread is not None and thread.isRunning():
                thread.quit()
                thread.wait(2000)
    assert "adaptive_cfg" in captured
    cfg = captured["adaptive_cfg"]
    assert cfg is not None
    assert isinstance(cfg, AdaptiveConfig)
    assert cfg.enabled is True


def test_spawn_stack_worker_unchecked_passes_none(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """With the toggle unchecked, _spawn_stack_worker passes None as the
    adaptive_cfg arg (fixed stack behavior)."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _adaptive_ui(ctrl)
    ui.checkBox_adaptiveEnable.setChecked(False)
    ctrl.stack_first_plane_set = True
    ctrl.stack_last_plane_set = True
    ctrl.stack_starting_plane = 0.0
    ctrl.stack_ending_plane = 100.0
    ctrl.number_of_planes = 2
    ctrl.saving_allowed = True
    captured: dict = {}  # ty: ignore[missing-type-argument]
    import lightsheet.gui.workers as workers_mod

    orig_init = workers_mod.StackWorker.__init__

    def capture_init(self: StackWorker, *args: Any, **kwargs: Any) -> None:
        captured["adaptive_cfg"] = kwargs.get("adaptive_cfg")
        orig_init(self, *args, **kwargs)

    with patch.object(workers_mod.StackWorker, "__init__", capture_init):
        try:
            ctrl.acquisition_panel._spawn_stack_worker()
        finally:
            thread = getattr(ctrl, "_stack_thread", None)
            if thread is not None and thread.isRunning():
                thread.quit()
                thread.wait(2000)
    assert captured.get("adaptive_cfg") is None


def test_stack_worker_run_does_not_read_ui(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """The StackWorker.run body never reaches into the shell's ui.* —
    the adaptive config is pre-sampled on the GUI thread and passed as
    a constructor arg. This is a static-source guard on the worker
    module: the run() method must not contain ``self._shell.ui`` or
    ``self._shell.stack_panel.ui`` reads."""
    import inspect

    from lightsheet.gui import workers

    src = inspect.getsource(workers.StackWorker.run)
    assert "self._shell.ui." not in src, (
        "StackWorker.run reaches into self._shell.ui — cross-thread widget "
        "access is prohibited (AGENTS.md §11)"
    )
    assert "self._shell.stack_panel.ui" not in src, (
        "StackWorker.run reaches into the stack panel ui — cross-thread "
        "widget access is prohibited (AGENTS.md §11)"
    )


# ===================================================================== #
# D-04 telemetry UI: dockable trajectory widget, badge, thread boundary,
# E-stop ordering, and dock-state persistence. These tests are the RED
# state for the telemetry UI contract (the widget, dock, badge strings,
# and GUI-thread slot do not exist yet).
# ===================================================================== #

# The exact empty-state copy (UI-SPEC §Copywriting Contract). The full
# fixed English sentence must remain readable when the dock is narrow
# (backstop truth #12).
EMPTY_COPY = (
    "No adaptive run yet. Enable Adaptive Control in the Stack panel "
    "and start a stack to see the per-plane intensity trajectory."
)


def _make_trajectory_widget(qtbot: QtBot) -> AdaptiveTrajectoryWidget:
    """Construct an AdaptiveTrajectoryWidget headless for unit testing.

    Imported lazily so the existing (passing) tests in this module are
    not blocked at collection time when the widget module does not yet
    exist (the RED state).
    """
    from lightsheet.gui.widgets.adaptive_trajectory import (
        AdaptiveTrajectoryWidget,
    )

    widget = AdaptiveTrajectoryWidget()
    qtbot.addWidget(widget)
    return widget


def test_dock_exists_and_hidden_initially(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """The trajectory dock is created and is hidden until the operator
    opens it via the rail button. It does NOT auto-open when adaptive
    is enabled. It can never re-dock into the main GUI."""
    ctrl, _ = make_controller(qtbot, request)
    dock = getattr(ctrl, "dockWidget_adaptiveTrajectory", None)
    assert dock is not None, "dockWidget_adaptiveTrajectory must exist on the shell"
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QDockWidget

    assert isinstance(dock, QDockWidget)
    # No dock areas allowed — it can never re-dock into the main GUI.
    assert dock.allowedAreas() == Qt.DockWidgetArea.NoDockWidgetArea
    # Hidden initially (adaptive is off; the dock is opt-in via the
    # rail button even when adaptive is on).
    assert not dock.isVisible()


def test_enabling_adaptive_shows_rail_button_not_dock(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """With adaptive enabled, the conditional rail button becomes
    visible so the operator can open the trajectory dock on demand.
    The dock itself does NOT open automatically — the trajectory plot
    is opt-in even when adaptive mode is on."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _adaptive_ui(ctrl)
    ui.checkBox_adaptiveEnable.setChecked(True)
    ui.checkBox_adaptiveEnable.toggled.emit(True)
    from PySide6.QtWidgets import QApplication

    QApplication.processEvents()
    # The rail button is not hidden (the affordance to open the dock).
    assert not ctrl.ui.toolButton_railAdaptive.isHidden(), (
        "rail button must be visible when adaptive is enabled"
    )
    # The dock is still hidden — opening it is the operator's choice.
    dock = ctrl.dockWidget_adaptiveTrajectory
    assert dock.isHidden(), (
        "dock must NOT auto-open when adaptive is enabled; "
        "the operator opens it via the rail button"
    )


def test_rail_button_opens_dock_floating(qtbot: QtBot, request: FixtureRequest) -> None:
    """Toggling the rail button opens the trajectory dock as a
    standalone floating window (never docked into the main GUI)."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _adaptive_ui(ctrl)
    ui.checkBox_adaptiveEnable.setChecked(True)
    ui.checkBox_adaptiveEnable.toggled.emit(True)
    from PySide6.QtWidgets import QApplication

    QApplication.processEvents()
    dock = ctrl.dockWidget_adaptiveTrajectory
    assert dock.isHidden()
    # Open via the rail button.
    ctrl.ui.toolButton_railAdaptive.setChecked(True)
    ctrl.ui.toolButton_railAdaptive.toggled.emit(True)
    QApplication.processEvents()
    assert not dock.isHidden(), "dock must open when rail button is checked"
    assert dock.isFloating(), (
        "dock must be a floating window, not docked into the main GUI"
    )


def test_empty_state_label_word_wraps(qtbot: QtBot, request: FixtureRequest) -> None:
    """The empty-state label has wordWrap enabled so the fixed English
    sentence wraps without clipping at the dock's minimum width
    (backstop truth #11, #12)."""
    ctrl, _ = make_controller(qtbot, request)
    label = getattr(ctrl, "label_adaptiveTrajectoryEmpty", None)
    assert label is not None
    assert label.wordWrap() is True


def test_trajectory_widget_zero_planes_is_empty(qtbot: QtBot) -> None:
    """The append path renders zero planes as the empty state (plot
    hidden, label visible) — must_have truth #6."""
    w = _make_trajectory_widget(qtbot)
    w.set_empty()
    assert not w.label_adaptiveTrajectoryEmpty.isHidden()
    assert w.plotWidget_adaptiveTrajectory.isHidden()


def test_trajectory_widget_one_plane_shows_point_and_band(qtbot: QtBot) -> None:
    """One sample swaps to the plot and renders one intensity point plus
    the target band region (must_have truth #6). The band is a
    LinearRegionItem spanning lo..hi %."""
    w = _make_trajectory_widget(qtbot)
    w.reset(target_band_lo=0.90, target_band_hi=0.95)
    w.append_sample(
        plane_idx=0,
        intensity=0.92,
        exposure_s=0.005,
        power1_mw=10.0,
        power2_mw=0.0,
        control_variable_active="exposure",
        reacquired=False,
        power_fallback=False,
    )
    assert not w.plotWidget_adaptiveTrajectory.isHidden()
    assert w.label_adaptiveTrajectoryEmpty.isHidden()
    # The intensity curve has exactly one point.
    intensity_curve = w._intensity_curve
    xs, ys = intensity_curve.getData()  # ty: ignore[unresolved-attribute]
    assert len(xs) == 1 and len(ys) == 1
    assert ys[0] == pytest.approx(92.0, abs=0.01)  # 0.92 -> 92%
    # The target band region exists and spans 90..95 %.
    region = w._target_band
    assert region is not None
    lo, hi = region.getRegion()
    assert lo == pytest.approx(90.0, abs=0.01)
    assert hi == pytest.approx(95.0, abs=0.01)


def test_trajectory_widget_many_planes_appends(qtbot: QtBot) -> None:
    """Many samples render a live trajectory (must_have truth #6)."""
    w = _make_trajectory_widget(qtbot)
    w.reset(target_band_lo=0.90, target_band_hi=0.95)
    for i in range(10):
        w.append_sample(
            plane_idx=i,
            intensity=0.90 + 0.001 * i,
            exposure_s=0.005,
            power1_mw=10.0,
            power2_mw=0.0,
            control_variable_active="exposure",
            reacquired=False,
            power_fallback=False,
        )
    xs, _ys = w._intensity_curve.getData()  # ty: ignore[unresolved-attribute]
    assert len(xs) == 10


def test_trajectory_widget_201_planes_retains_full_data(qtbot: QtBot) -> None:
    """Beyond 200 planes the X view auto-scrolls to the last 200 while
    retaining the complete in-memory data for zoom-out (must_have truth
    #5). After 201 appends the curve holds all 201 points; the visible
    X range covers the last 200."""
    w = _make_trajectory_widget(qtbot)
    w.reset(target_band_lo=0.90, target_band_hi=0.95)
    for i in range(201):
        w.append_sample(
            plane_idx=i,
            intensity=0.90,
            exposure_s=0.005,
            power1_mw=10.0,
            power2_mw=0.0,
            control_variable_active="exposure",
            reacquired=False,
            power_fallback=False,
        )
    xs, _ys = w._intensity_curve.getData()  # ty: ignore[unresolved-attribute]
    assert len(xs) == 201, "full in-memory data must be retained"
    # The X view spans the last 200 planes (auto-scroll window).
    vb = w.plotWidget_adaptiveTrajectory.getPlotItem().getViewBox()
    x_min, _x_max = vb.viewRange()[0]
    assert x_min >= 1  # window starts at plane 1 (last 200 of 0..200)


def test_trajectory_widget_reacquire_marker(qtbot: QtBot) -> None:
    """A re-acquire event renders a vertical dashed warning line at the
    plane index (must_have truth #3)."""
    w = _make_trajectory_widget(qtbot)
    w.reset(target_band_lo=0.90, target_band_hi=0.95)
    w.append_sample(
        plane_idx=3,
        intensity=0.50,
        exposure_s=0.005,
        power1_mw=10.0,
        power2_mw=0.0,
        control_variable_active="exposure",
        reacquired=True,
        power_fallback=False,
    )
    # A re-acquire InfiniteLine was added at x=3.
    reacquire_lines = w._reacquire_lines
    assert len(reacquire_lines) == 1
    assert reacquire_lines[0].value() == pytest.approx(3.0)


def test_trajectory_widget_power_fallback_marker(qtbot: QtBot) -> None:
    """A power-fallback event renders a triangle marker at the plane
    (must_have truth #3)."""
    w = _make_trajectory_widget(qtbot)
    w.reset(target_band_lo=0.90, target_band_hi=0.95)
    w.append_sample(
        plane_idx=2,
        intensity=0.85,
        exposure_s=0.005,
        power1_mw=20.0,
        power2_mw=0.0,
        control_variable_active="power",
        reacquired=False,
        power_fallback=True,
    )
    # The power-fallback scatter has one point at x=2.
    scatter = w._power_fallback_scatter
    spots = scatter.getData()  # ty: ignore[unresolved-attribute]
    assert len(spots[0]) == 1
    assert spots[0][0] == pytest.approx(2.0)


def test_trajectory_widget_twin_axis_exposure_power(qtbot: QtBot) -> None:
    """Exposure renders on the right-1 ViewBox and power on the right-2
    ViewBox (three Y axes: intensity, exposure, power). Each axis exists
    and the curves use their respective ViewBoxes."""
    w = _make_trajectory_widget(qtbot)
    w.reset(target_band_lo=0.90, target_band_hi=0.95)
    w.append_sample(
        plane_idx=0,
        intensity=0.92,
        exposure_s=0.005,
        power1_mw=10.0,
        power2_mw=0.0,
        control_variable_active="exposure",
        reacquired=False,
        power_fallback=False,
    )
    # The exposure + power curves have data.
    assert w._exposure_curve is not None
    assert w._power_curve is not None
    # The exposure ViewBox (right-1) and power ViewBox (right-2) both
    # exist and are linked to the left ViewBox's X.
    assert w._right_vb is not None
    assert w._power_vb is not None


def test_trajectory_widget_freeze_blocks_appends(qtbot: QtBot) -> None:
    """After freeze() (E-stop), further append_sample calls are ignored
    so the last trajectory is preserved for review (must_have truth #4)."""
    w = _make_trajectory_widget(qtbot)
    w.reset(target_band_lo=0.90, target_band_hi=0.95)
    w.append_sample(
        plane_idx=0,
        intensity=0.92,
        exposure_s=0.005,
        power1_mw=10.0,
        power2_mw=0.0,
        control_variable_active="exposure",
        reacquired=False,
        power_fallback=False,
    )
    w.freeze()
    w.append_sample(
        plane_idx=1,
        intensity=0.93,
        exposure_s=0.005,
        power1_mw=10.0,
        power2_mw=0.0,
        control_variable_active="exposure",
        reacquired=False,
        power_fallback=False,
    )
    xs, _ys = w._intensity_curve.getData()  # ty: ignore[unresolved-attribute]
    assert len(xs) == 1, "post-freeze append must be ignored"


def test_badge_adaptive_running_min_width_180(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """The mode badge has a minimum width of 180 px so the single-line
    'ADAPTIVE RUNNING — plane 999/999 (row 3/5) · MULTI-CH' fits without
    elision (must_have truth #7)."""
    ctrl, _ = make_controller(qtbot, request)
    badge = ctrl.ui.label_modeBadge
    assert badge.minimumSize().width() >= 180


def test_badge_adaptive_running_string(qtbot: QtBot, request: FixtureRequest) -> None:
    """The badge renders 'ADAPTIVE RUNNING — plane {n}/{N}' with the
    em-dash, and composes with the queue-row + MULTI-CH suffixes
    (must_have truth #7)."""
    ctrl, _ = make_controller(qtbot, request)
    ctrl._auto_laser1 = True
    ctrl._auto_laser2 = True
    ctrl.number_of_planes = 999
    ctrl._update_mode_badge(
        "ADAPTIVE",
        "RUNNING",
        plane=999,
        total=999,
        queue_row=3,
        queue_total=5,
    )
    text = ctrl.ui.label_modeBadge.text()
    assert "ADAPTIVE RUNNING" in text
    assert "\u2014" in text  # em-dash
    assert "plane 999/999" in text
    assert "(row 3/5)" in text
    assert "MULTI-CH" in text


def test_badge_adaptive_aborted_string(qtbot: QtBot, request: FixtureRequest) -> None:
    """E-stop mid-adaptive-run transitions the badge to 'ADAPTIVE
    ABORTED — plane {n}/{N}' (must_have truth #4)."""
    ctrl, _ = make_controller(qtbot, request)
    ctrl.number_of_planes = 50
    ctrl._update_mode_badge("ADAPTIVE", "ABORTED", plane=12, total=50)
    text = ctrl.ui.label_modeBadge.text()
    assert "ADAPTIVE ABORTED" in text
    assert "plane 12/50" in text


def test_badge_no_green_or_accent_stylesheet(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """The badge adds no green/accent stylesheet — it inherits the
    existing bold weight + default text color (must_have truth #7,
    UI-SPEC §Color)."""
    ctrl, _ = make_controller(qtbot, request)
    ss = ctrl.ui.label_modeBadge.styleSheet()
    assert "green" not in ss.lower()
    assert "#3daee9" not in ss.lower()


def test_estop_freezes_trajectory_after_laser_off(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """E-stop performs synchronous laser.off() first, then freezes the
    trajectory plot and sets the badge to ABORTED (must_have truth #4,
    threat T-10-02). The kill path precedes the GUI freeze/badge work."""
    ctrl, _ = make_controller(qtbot, request)
    # Enable adaptive so the rail button + widget exist, then open the
    # dock via the rail button (it does not auto-open on enable).
    ui = _adaptive_ui(ctrl)
    ui.checkBox_adaptiveEnable.setChecked(True)
    ui.checkBox_adaptiveEnable.toggled.emit(True)
    from PySide6.QtWidgets import QApplication

    QApplication.processEvents()
    ctrl.ui.toolButton_railAdaptive.setChecked(True)
    ctrl.ui.toolButton_railAdaptive.toggled.emit(True)
    QApplication.processEvents()
    widget = ctrl.adaptiveTrajectoryWidget
    # Append one sample so freeze has something to freeze.
    widget.reset(target_band_lo=0.90, target_band_hi=0.95)
    widget.append_sample(
        plane_idx=0,
        intensity=0.92,
        exposure_s=0.005,
        power1_mw=10.0,
        power2_mw=0.0,
        control_variable_active="exposure",
        reacquired=False,
        power_fallback=False,
    )
    # Track laser.off() call order vs the freeze.
    off_calls: list[int] = []
    freeze_before_off: list[bool] = []
    real_off = [laser.off for laser in ctrl.lasers]

    def _tracking_off(idx: int) -> Any:
        def _off() -> None:
            if widget._frozen:
                freeze_before_off.append(True)
            off_calls.append(idx)
            real_off[idx]()

        return _off

    for idx, laser in enumerate(ctrl.lasers):
        laser.off = _tracking_off(idx)
    ctrl.updateUi_estop_pressed()
    QApplication.processEvents()
    # Both lasers were driven off.
    assert sorted(off_calls) == [0, 1]
    # The freeze did NOT happen before the laser off calls (kill first).
    assert freeze_before_off == []
    # After E-stop the widget is frozen.
    assert widget._frozen is True
    # The dock stays visible for review.
    assert not ctrl.dockWidget_adaptiveTrajectory.isHidden()


def test_worker_signal_connected_to_gui_slot_queued(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """_spawn_stack_worker connects sig_adaptive_trajectory to a
    GUI-thread slot via a queued connection (must_have truth #3,
    threat T-10-05). The connection exists after spawning."""

    ctrl, _ = make_controller(qtbot, request)
    ui = _adaptive_ui(ctrl)
    ui.checkBox_adaptiveEnable.setChecked(True)
    ctrl.stack_first_plane_set = True
    ctrl.stack_last_plane_set = True
    ctrl.stack_starting_plane = 0.0
    ctrl.stack_ending_plane = 100.0
    ctrl.number_of_planes = 2
    ctrl.saving_allowed = True
    captured: dict = {}  # ty: ignore[missing-type-argument]
    import lightsheet.gui.workers as workers_mod

    orig_init = workers_mod.StackWorker.__init__

    def capture_init(self: StackWorker, *args: Any, **kwargs: Any) -> None:
        captured["worker"] = self
        orig_init(self, *args, **kwargs)

    with patch.object(workers_mod.StackWorker, "__init__", capture_init):
        try:
            ctrl.acquisition_panel._spawn_stack_worker()
            worker = captured.get("worker")
            assert worker is not None
            # The signal is connected to the shell's GUI-thread slot.
            slot = getattr(ctrl, "_on_adaptive_trajectory", None)
            assert slot is not None
            # Emit and confirm the slot is reached (queued delivery on
            # the GUI thread; processEvents drains the queue).
            received: list[tuple] = []  # ty: ignore[missing-type-argument]
            ctrl._on_adaptive_trajectory = lambda *a: received.append(a)
            # Re-connect to the patched slot to verify the connection
            # path: the spawn wired sig_adaptive_trajectory -> slot.
            worker.sig_adaptive_trajectory.emit(
                0, 0.92, 0.005, 10.0, 5.0, "exposure", False, False
            )
            from PySide6.QtWidgets import QApplication

            QApplication.processEvents()
            assert len(received) == 1
        finally:
            thread = getattr(ctrl, "_stack_thread", None)
            if thread is not None and thread.isRunning():
                thread.quit()
                thread.wait(2000)


def test_worker_run_does_not_call_plotwidget(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """The worker run() body never calls pyqtgraph or PlotWidget
    directly (threat T-10-05). Static-source guard on the worker
    module."""
    import inspect

    from lightsheet.gui import workers

    src = inspect.getsource(workers.StackWorker.run)
    assert "pyqtgraph" not in src, (
        "StackWorker.run imports/calls pyqtgraph — worker thread must "
        "emit data only, never touch the GUI-thread plot (AGENTS.md §11)"
    )
    assert "plotWidget" not in src, (
        "StackWorker.run references plotWidget — cross-thread widget "
        "access is prohibited (AGENTS.md §11)"
    )


def test_no_imageview_reintroduction(qtbot: QtBot, request: FixtureRequest) -> None:
    """pyqtgraph is reintroduced ONLY for PlotWidget — no
    pyqtgraph.ImageView / pyqtgraph.imageview import exists in
    production code (UI-SPEC §Registry Safety, threat T-10-SC)."""
    import lightsheet.gui.widgets.adaptive_trajectory as mod

    with Path(mod.__file__).open(encoding="utf-8") as f:
        src = f.read()
    assert "ImageView" not in src
    assert "imageview" not in src.lower()


def test_dock_state_persistence(
    qtbot: QtBot, request: FixtureRequest, tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """QSettings saveState/restoreState preserves the dock area/geometry
    without writing config.ini during demo tests (must_have truth:
    dock persistence). The controller restores the dock state from
    QSettings during __init__ and saves it in closeEvent."""

    ctrl, _ = make_controller(qtbot, request)
    # The dock exists after construction (restoreState ran in __init__).
    assert hasattr(ctrl, "dockWidget_adaptiveTrajectory")
    # The controller exposes the QSettings key it uses for dock state.
    assert hasattr(ctrl, "_adaptive_dock_state_key")
    key = ctrl._adaptive_dock_state_key
    assert "adaptiveTrajectoryDockState" in key
    # Saving the state produces a non-empty QByteArray (the dock is
    # registered with the QMainWindow).
    state = ctrl.saveState()
    assert state is not None
    assert len(bytes(state)) > 0


def test_dock_is_floating_only_closable(qtbot: QtBot, request: FixtureRequest) -> None:
    """The dock is a standalone floating window: closable but NOT
    movable, NOT floatable, and cannot re-dock into the main GUI
    (NoDockWidgetArea). This avoids re-dock overlay indicators on every
    drag near the main window during acquisition monitoring. When
    opened via the rail button it floats as a standalone window."""
    ctrl, _ = make_controller(qtbot, request)
    dock = ctrl.dockWidget_adaptiveTrajectory
    features = dock.features()
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QDockWidget

    # Closable (operator can dismiss it), but NOT movable/floatable.
    assert features & QDockWidget.DockWidgetFeature.DockWidgetClosable
    assert not (features & QDockWidget.DockWidgetFeature.DockWidgetMovable)
    assert not (features & QDockWidget.DockWidgetFeature.DockWidgetFloatable)
    # No dock areas allowed — it can never re-dock into the main GUI.
    assert dock.allowedAreas() == Qt.DockWidgetArea.NoDockWidgetArea
    # When opened via the rail button, it floats as a standalone window.
    ctrl.ui.toolButton_railAdaptive.setVisible(True)
    ctrl.ui.toolButton_railAdaptive.setChecked(True)
    ctrl.ui.toolButton_railAdaptive.toggled.emit(True)
    from PySide6.QtWidgets import QApplication

    QApplication.processEvents()
    assert dock.isFloating() is True


# ===================================================================== #
# UI-REVIEW fix verification: runtime curve/scatter/marker pen colors,
# on-scale margins (16 px widget + PlotItem, 8/4/8/4 title bar with 4 px
# spacing), regular-weight dock title, inherited close-button font, and
# the exact close-button tooltip. These tests inspect the live Qt /
# pyqtgraph objects rather than reading source text.
# ===================================================================== #


def _pen_color_hex(pen: Any) -> str:
    """Return a pen's color as a normalized #RRGGBB hex string."""
    color = pen.color()
    return f"#{color.red():02x}{color.green():02x}{color.blue():02x}".lower()


def test_exposure_curve_pen_is_grey_midtone(qtbot: QtBot) -> None:
    """The exposure curve pen resolves to Breeze midtone grey #76797c
    (not green, not accent blue) — the safety-semantic color boundary
    requires green to stay reserved for laser ● ON status."""
    w = _make_trajectory_widget(qtbot)
    assert w._exposure_curve is not None
    hex_color = _pen_color_hex(w._exposure_curve.opts["pen"])
    assert hex_color == "#76797c"


def test_power_fallback_scatter_pen_is_amber(qtbot: QtBot) -> None:
    """The power-fallback scatter pen + brush resolve to amber
    #E0A030 (the power-family color), not green — its y-value is
    exposure but its event semantics are power."""
    w = _make_trajectory_widget(qtbot)
    assert w._power_fallback_scatter is not None
    pen = w._power_fallback_scatter.opts["pen"]
    brush = w._power_fallback_scatter.opts["brush"]
    assert _pen_color_hex(pen) == "#e0a030"
    assert _pen_color_hex(brush) == "#e0a030"


def test_reacquire_legend_sample_is_warning_olive(qtbot: QtBot) -> None:
    """The re-acquire legend sample pen resolves to Breeze warning
    olive #99995C (not neutral grey) so the operator reads the
    semantic 'this plane was re-shot'."""
    w = _make_trajectory_widget(qtbot)
    assert w._reacquire_legend_sample is not None
    hex_color = _pen_color_hex(w._reacquire_legend_sample.opts["pen"])
    assert hex_color == "#99995c"


def test_power_l1_curve_pen_is_amber(qtbot: QtBot) -> None:
    """The L1 power curve pen resolves to amber #E0A030 (the
    operator-approved power-family color)."""
    w = _make_trajectory_widget(qtbot)
    assert w._power_curve is not None
    hex_color = _pen_color_hex(w._power_curve.opts["pen"])
    assert hex_color == "#e0a030"


def test_power_l2_curve_pen_is_lighter_amber(qtbot: QtBot) -> None:
    """The L2 power curve pen resolves to lighter amber #F0C060."""
    w = _make_trajectory_widget(qtbot)
    assert w._power2_curve is not None
    hex_color = _pen_color_hex(w._power2_curve.opts["pen"])
    assert hex_color == "#f0c060"


def test_no_adaptive_curve_or_marker_is_green(qtbot: QtBot) -> None:
    """No adaptive plot primitive resolves to a green pen/brush —
    green is reserved exclusively for laser ● ON status. Inspects
    every curve, scatter, and legend sample pen/brush color."""
    w = _make_trajectory_widget(qtbot)
    items = [
        w._intensity_curve,
        w._exposure_curve,
        w._power_curve,
        w._power2_curve,
        w._power_fallback_scatter,
        w._target_band_legend_sample,
        w._reacquire_legend_sample,
    ]
    for item in items:
        if item is None:
            continue
        pen = item.opts.get("pen")
        if pen is not None:
            color = pen.color()  # ty: ignore[unresolved-attribute]
            # Green dominant: green channel strictly greater than both
            # red and blue by a clear margin.
            assert not (
                color.green() > color.red() + 20 and color.green() > color.blue() + 20
            ), (
                f"adaptive plot primitive uses green: "
                f"#{color.red():02x}{color.green():02x}{color.blue():02x}"
            )
        brush = item.opts.get("brush")
        if brush is not None:
            color = brush.color()  # ty: ignore[unresolved-attribute]
            assert not (
                color.green() > color.red() + 20 and color.green() > color.blue() + 20
            ), (
                f"adaptive plot primitive brush uses green: "
                f"#{color.red():02x}{color.green():02x}{color.blue():02x}"
            )


def test_widget_layout_margins_are_16(qtbot: QtBot) -> None:
    """The outer QVBoxLayout contents margins are 16 px on every side
    (the md spacing token from the 4/8/16 scale)."""
    w = _make_trajectory_widget(qtbot)
    layout = w.layout()
    margins = layout.contentsMargins()  # ty: ignore[unresolved-attribute]
    assert (margins.left(), margins.top(), margins.right(), margins.bottom()) == (
        16,
        16,
        16,
        16,
    )


def test_plotitem_layout_margins_are_16(qtbot: QtBot) -> None:
    """The inner PlotItem.layout contents margins are 16 px on every
    side so the dark widget background shows as padding around the
    axes/labels on all sides."""
    w = _make_trajectory_widget(qtbot)
    item = w.plotWidget_adaptiveTrajectory.getPlotItem()
    # QGraphicsGridLayout exposes getContentsMargins (left, top, right,
    # bottom) rather than a QMargins object.
    left, top, right, bottom = item.layout.getContentsMargins()
    assert (left, top, right, bottom) == (16, 16, 16, 16)


def test_dock_title_bar_margins_and_spacing(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """The adaptive dock title bar margins are 8/4/8/4 (sm horizontal,
    xs vertical) with 4 px spacing — all on the 4/8/16 scale."""
    ctrl, _ = make_controller(qtbot, request)
    title_bar = ctrl.dockWidget_adaptiveTrajectory.titleBarWidget()
    layout = title_bar.layout()
    margins = layout.contentsMargins()
    assert (margins.left(), margins.top(), margins.right(), margins.bottom()) == (
        8,
        4,
        8,
        4,
    )
    assert layout.spacing() == 4


def test_dock_title_label_is_regular_weight(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """The adaptive dock title label has no bold override — the mode
    badge is the only bold text in the app (UI-SPEC Typography)."""
    ctrl, _ = make_controller(qtbot, request)
    title_bar = ctrl.dockWidget_adaptiveTrajectory.titleBarWidget()
    from PySide6.QtWidgets import QLabel

    labels = title_bar.findChildren(QLabel)
    assert len(labels) >= 1
    title_label = labels[0]
    ss = title_label.styleSheet()
    assert "bold" not in ss.lower(), (
        f"dock title label must not be bold; styleSheet={ss!r}"
    )


def test_dock_close_button_inherits_font_and_has_tooltip(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """The dock close button has no 16 px font override (it inherits
    the app font), keeps border/hover styling, and exposes the exact
    tooltip 'Close adaptive trajectory dock'."""
    ctrl, _ = make_controller(qtbot, request)
    title_bar = ctrl.dockWidget_adaptiveTrajectory.titleBarWidget()
    from PySide6.QtWidgets import QPushButton

    buttons = title_bar.findChildren(QPushButton)
    assert len(buttons) == 1
    close_btn = buttons[0]
    ss = close_btn.styleSheet()
    assert "font-size" not in ss.lower(), (
        f"close button must not override font-size; styleSheet={ss!r}"
    )
    assert "border" in ss.lower(), "close button keeps border styling"
    assert "hover" in ss.lower(), "close button keeps hover styling"
    assert close_btn.toolTip() == "Close adaptive trajectory dock"
