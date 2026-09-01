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

from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest
from pytest import FixtureRequest
from pytestqt.qtbot import QtBot

pytest.importorskip("PySide6")

from _helpers.controller_fixture import make_controller
from lightsheet.focus.types import FocusConfig, FocusCurve
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
    "comboBox_focusXAxisVariable",
    "label_focusStatus",
    "label_focusBlockHint",
    "label_focusXAxisVariable",
)


def _focus_ui(ctrl: Controller_MainWindow) -> Ui_StackPanel:
    """Return the stack panel focus group widgets as a namespace."""
    return ctrl.stack_panel.ui


def _valid_calibration_json() -> str:
    """A 3-point calibration curve with camera positions inside the mock
    0-35 mm travel range."""
    return '{"points": [[0.0, 20.0], [10.0, 22.0], [20.0, 24.0]]}'


def test_focus_group_widgets_exist(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """The focus control group and its child widgets exist on the stack
    panel with the exact UI-SPEC objectNames."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _focus_ui(ctrl)
    for name in FOCUS_WIDGET_NAMES:
        assert hasattr(ui, name), f"missing focus widget {name}"


def test_focus_block_size_is_field_spec_subclass(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """The focus block-size spinbox is a promoted FieldSpecSpinBox."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _focus_ui(ctrl)
    sb = ui.doubleSpinBox_focusBlockSize
    assert isinstance(sb, FieldSpecSpinBox), (
        f"doubleSpinBox_focusBlockSize is {type(sb).__name__}, "
        "not FieldSpecSpinBox"
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
    assert not ui.widget_focusFields.isVisibleTo(
        ui.widget_focusFields.parentWidget()  # ty: ignore[invalid-argument-type]
    )
    assert ui.groupBox_focusControl.isVisibleTo(
        ui.groupBox_focusControl.parentWidget()  # ty: ignore[invalid-argument-type]
    )


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
    assert ui.widget_focusFields.isVisibleTo(
        ui.widget_focusFields.parentWidget()  # ty: ignore[invalid-argument-type]
    )


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
    assert "autofocus residual on" in status.lower(), (
        f"unexpected status: {status!r}"
    )


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
    # Camera position 100 mm is outside the mock 0-35 mm camera limits.
    path.write_text('{"points": [[0.0, 100.0], [1.0, 101.0]]}')
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
    # Checked but no file loaded -> None.
    ui.checkBox_focusEnable.setChecked(True)
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
        cfg.block_size_n = 99  # type: ignore[misc]


def test_build_focus_curve_returns_loaded_curve_object(
    qtbot: QtBot, request: FixtureRequest, tmp_path: Any
) -> None:
    """build_focus_curve returns the exact FocusCurve object produced by
    a successful pushButton_focusLoad call, or None when unchecked or
    unarmed."""
    ctrl, _ = make_controller(qtbot, request)
    ui = _focus_ui(ctrl)
    ui.checkBox_focusEnable.setChecked(True)
    expected = FocusCurve(
        stage_pos=(0.0, 10.0, 20.0), camera_pos=(20.0, 22.0, 24.0)
    )
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
