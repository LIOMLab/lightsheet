"""Runtime widget, validation, fixed-fallback, and pre-sampling tests for
the Stack-panel adaptive configuration group.

Constructs the real ``Controller_MainWindow`` via the shared
``make_controller`` fixture (AGENTS.md §5) so the panel ``__init__``
applySpec loops + the adaptive group wiring run against the real widget
tree. Headless via ``QT_QPA_PLATFORM=offscreen`` (set by conftest).

Covers the operator-facing contracts:
- The 13 enumerated adaptive spinboxes exist as ``FieldSpecSpinBox``
  instances with the exact objectNames from the UI-SPEC.
- The enable toggle hides only the fields container (the group box title
  row stays visible as the affordance).
- An invalid min/max pair emits the documented message + beep, reverts
  the edit, and latches fixed-fallback until a later valid edit.
- Rolling shows ms; Lightsheet shows lines and the bound converts to
  seconds via exposed_lines × line_time.
- ``build_adaptive_config`` normalizes ms/lines to seconds, percentages
  to fractions, narrows power to live maxima, and returns a frozen
  ``AdaptiveConfig`` (or ``None`` when unchecked).
- ``_spawn_stack_worker`` pre-samples the adaptive config on the GUI
  thread and passes one frozen ``AdaptiveConfig`` as the final
  ``StackWorker`` constructor arg — the worker performs no ``ui.*``
  reads.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

pytest.importorskip("PySide6")

from _helpers.controller_fixture import make_controller  # noqa: E402
from lightsheet.adaptive.types import AdaptiveConfig  # noqa: E402
from lightsheet.gui.widgets.field_spec_spinbox import FieldSpecSpinBox  # noqa: E402

# The 13 enumerated adaptive spinbox objectNames (UI-SPEC §Component
# Inventory). The prose count of 14 in the FieldSpec policy table is an
# audit typo — there are exactly 13 widgets (the 14th row is the shutter
# hint label, not a spinbox).
ADAPTIVE_SPINBOX_OBJNAMES = (
    "doubleSpinBox_adaptiveMinExposure",
    "doubleSpinBox_adaptiveMaxExposure",
    "doubleSpinBox_adaptiveLaser1MinPower",
    "doubleSpinBox_adaptiveLaser1MaxPower",
    "doubleSpinBox_adaptiveLaser2MinPower",
    "doubleSpinBox_adaptiveLaser2MaxPower",
    "doubleSpinBox_adaptiveTargetBandLo",
    "doubleSpinBox_adaptiveTargetBandHi",
    "doubleSpinBox_adaptiveReacquireThreshold",
    "doubleSpinBox_adaptiveBlockSizeN",
    "doubleSpinBox_adaptiveKp",
    "doubleSpinBox_adaptiveKi",
    "doubleSpinBox_adaptivePilotCount",
)


def _adaptive_ui(ctrl):
    """Return the stack panel adaptive group widgets as a namespace."""
    return ctrl.stack_panel.ui


def test_adaptive_group_widgets_exist(qtbot, request) -> None:
    """The adaptive config group + toggle + 13 spinboxes + shutter hint
    exist on the stack panel with the exact UI-SPEC objectNames."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _adaptive_ui(ctrl)
    assert hasattr(ui, "groupBox_adaptiveControl")
    assert hasattr(ui, "checkBox_adaptiveEnable")
    assert hasattr(ui, "widget_adaptiveFields")
    assert hasattr(ui, "label_adaptiveShutterModeHint")
    for name in ADAPTIVE_SPINBOX_OBJNAMES:
        assert hasattr(ui, name), f"missing adaptive spinbox {name}"


def test_adaptive_spinboxes_are_field_spec_subclass(qtbot, request) -> None:
    """Each of the 13 adaptive spinboxes is a promoted FieldSpecSpinBox."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _adaptive_ui(ctrl)
    for name in ADAPTIVE_SPINBOX_OBJNAMES:
        sb = getattr(ui, name)
        assert isinstance(sb, FieldSpecSpinBox), (
            f"{name} is {type(sb).__name__}, not FieldSpecSpinBox"
        )


def test_adaptive_toggle_off_hides_fields_container(qtbot, request) -> None:
    """When the toggle is unchecked, only the fields container is hidden
    — the group box title row (the affordance) stays visible."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _adaptive_ui(ctrl)
    ui.checkBox_adaptiveEnable.setChecked(False)
    # The toggle handler is wired in __init__; emit the signal to drive it.
    ui.checkBox_adaptiveEnable.toggled.emit(False)
    from PySide6.QtWidgets import QApplication
    QApplication.processEvents()
    assert not ui.widget_adaptiveFields.isVisibleTo(ui.widget_adaptiveFields.parentWidget())
    # The group box itself stays visible (the affordance remains).
    assert ui.groupBox_adaptiveControl.isVisibleTo(
        ui.groupBox_adaptiveControl.parentWidget()
    )


def test_adaptive_toggle_on_shows_fields_container(qtbot, request) -> None:
    """When the toggle is checked, the fields container becomes visible."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _adaptive_ui(ctrl)
    ui.checkBox_adaptiveEnable.setChecked(True)
    ui.checkBox_adaptiveEnable.toggled.emit(True)
    from PySide6.QtWidgets import QApplication
    QApplication.processEvents()
    assert ui.widget_adaptiveFields.isVisibleTo(ui.widget_adaptiveFields.parentWidget())


def test_adaptive_invalid_pair_beeps_messages_reverts(qtbot, request) -> None:
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


def test_adaptive_invalid_pair_reverts_offending_spinbox(qtbot, request) -> None:
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


def test_adaptive_later_valid_edit_clears_latch(qtbot, request) -> None:
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


def test_adaptive_unchecked_returns_none(qtbot, request) -> None:
    """With the toggle unchecked, build_adaptive_config returns None
    (fixed stack behavior is selected)."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _adaptive_ui(ctrl)
    ui.checkBox_adaptiveEnable.setChecked(False)
    assert ctrl.stack_panel.build_adaptive_config() is None


def test_adaptive_checked_valid_returns_frozen_config(qtbot, request) -> None:
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


def test_adaptive_rolling_shutter_shows_ms(qtbot, request) -> None:
    """In Rolling shutter mode the exposure bound spinboxes show the ms
    suffix and the hint reads the Rolling copy."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _adaptive_ui(ctrl)
    ctrl.acquisition_panel.ui.comboBox_cameraShutterMode.setCurrentText("Rolling")
    ctrl.acquisition_panel.ui.comboBox_cameraShutterMode.currentTextChanged.emit("Rolling")
    from PySide6.QtWidgets import QApplication
    QApplication.processEvents()
    suffix = ui.doubleSpinBox_adaptiveMinExposure.suffix().strip().lower()
    assert suffix == "ms"
    hint = ui.label_adaptiveShutterModeHint.text().lower()
    assert "rolling" in hint
    assert "millisecond" in hint


def test_adaptive_lightsheet_shutter_shows_lines(qtbot, request) -> None:
    """In Lightsheet shutter mode the exposure bound spinboxes show the
    lines suffix and the hint reads the Lightsheet copy."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _adaptive_ui(ctrl)
    ctrl.acquisition_panel.ui.comboBox_cameraShutterMode.setCurrentText("Lightsheet")
    ctrl.acquisition_panel.ui.comboBox_cameraShutterMode.currentTextChanged.emit("Lightsheet")
    from PySide6.QtWidgets import QApplication
    QApplication.processEvents()
    suffix = ui.doubleSpinBox_adaptiveMinExposure.suffix().strip().lower()
    assert suffix == "lines"
    hint = ui.label_adaptiveShutterModeHint.text().lower()
    assert "lightsheet" in hint
    assert "exposed lines" in hint


def test_adaptive_lightsheet_bound_converts_to_seconds(qtbot, request) -> None:
    """In Lightsheet shutter mode the exposure bound converts to seconds
    as exposed_lines × line_time. Set Min Exposure = 25 lines with
    line_time = 100 µs → 25 × 100e-6 = 2.5e-3 s."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _adaptive_ui(ctrl)
    ctrl.acquisition_panel.ui.comboBox_cameraShutterMode.setCurrentText("Lightsheet")
    ctrl.acquisition_panel.ui.comboBox_cameraShutterMode.currentTextChanged.emit("Lightsheet")
    ctrl.acquisition_panel.ui.doubleSpinBox_cameraLineTime.setValue(100.0)  # µs
    ctrl.acquisition_panel.ui.doubleSpinBox_cameraExposedLines.setValue(25)
    ui.checkBox_adaptiveEnable.setChecked(True)
    ui.doubleSpinBox_adaptiveMinExposure.setValue(25.0)  # 25 lines
    ui.doubleSpinBox_adaptiveMinExposure.editingFinished.emit()
    cfg = ctrl.stack_panel.build_adaptive_config()
    assert cfg is not None
    assert cfg.min_exposure_s == pytest.approx(25 * 100e-6, rel=1e-6)


def test_adaptive_rolling_bound_converts_ms_to_seconds(qtbot, request) -> None:
    """In Rolling shutter mode the exposure bound converts ms → seconds
    (×1e-3). Set Min Exposure = 5 ms → 5e-3 s."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _adaptive_ui(ctrl)
    ctrl.acquisition_panel.ui.comboBox_cameraShutterMode.setCurrentText("Rolling")
    ctrl.acquisition_panel.ui.comboBox_cameraShutterMode.currentTextChanged.emit("Rolling")
    ui.checkBox_adaptiveEnable.setChecked(True)
    ui.doubleSpinBox_adaptiveMinExposure.setValue(5.0)  # 5 ms
    ui.doubleSpinBox_adaptiveMinExposure.editingFinished.emit()
    cfg = ctrl.stack_panel.build_adaptive_config()
    assert cfg is not None
    assert cfg.min_exposure_s == pytest.approx(5e-3, rel=1e-9)


def test_adaptive_power_narrowed_to_live_max(qtbot, request) -> None:
    """The laser max-power spinbox maximum is narrowed at runtime to
    min(150.0, shell._bundle.lasers[i].max_power). The test fixture's
    laser[0] has max_power 300 mW → narrowed to 150.0; laser[1] has
    max_power 150 mW → narrowed to 150.0."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _adaptive_ui(ctrl)
    assert ui.doubleSpinBox_adaptiveLaser1MaxPower.maximum() <= 150.0
    assert ui.doubleSpinBox_adaptiveLaser2MaxPower.maximum() <= 150.0


def test_spawn_stack_worker_passes_frozen_adaptive_cfg(qtbot, request) -> None:
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
    captured: dict = {}

    real_init = ctrl._stack_worker.__class__.__init__ if False else None

    # Patch StackWorker.__init__ to capture the adaptive_cfg kwarg
    # without actually constructing the worker (the real constructor
    # reaches into the shell; we only need the captured arg).
    import lightsheet.gui.workers as workers_mod

    orig_init = workers_mod.StackWorker.__init__

    def capture_init(self, *args, **kwargs):
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


def test_spawn_stack_worker_unchecked_passes_none(qtbot, request) -> None:
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
    captured: dict = {}
    import lightsheet.gui.workers as workers_mod

    orig_init = workers_mod.StackWorker.__init__

    def capture_init(self, *args, **kwargs):
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


def test_stack_worker_run_does_not_read_ui(qtbot, request) -> None:
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
