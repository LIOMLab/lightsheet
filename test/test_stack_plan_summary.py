"""Stack-plan summary + persist-last to config.ini.

A read-only summary label (start/end/step/#planes/est. time/est. size) lets
the operator sanity-check the stack plan before pressing Start. The last
stack's start/end/step persist to config.ini so a re-run does not require
re-driving the stage.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

pytest.importorskip("PySide6")

from _helpers.controller_fixture import make_controller
from pytestqt.qtbot import QtBot


def test_summary_label_exists(
    qtbot: QtBot, request: pytest.FixtureRequest
) -> None:
    ctrl, _ = make_controller(qtbot, request)
    from PySide6.QtWidgets import QLabel

    label = ctrl.stack_panel.ui.label_stackPlanSummary
    assert isinstance(label, QLabel)


def test_summary_renders_full_plan(
    qtbot: QtBot, request: pytest.FixtureRequest
) -> None:
    ctrl, _ = make_controller(qtbot, request)
    ctrl.stack_first_plane_set = True
    ctrl.stack_last_plane_set = True
    ctrl.stack_panel.ui.doubleSpinBox_acqFirstPlane.setValue(100.0)
    ctrl.stack_panel.ui.doubleSpinBox_acqLastPlane.setValue(200.0)
    ctrl.stack_panel.ui.doubleSpinBox_acqPlaneStepSize.setValue(10.0)
    ctrl.stack_panel.updateUi_set_number_of_planes()
    text = ctrl.stack_panel.ui.label_stackPlanSummary.text()
    assert "Start" in text
    assert "End" in text
    assert "Step" in text
    assert "Plane" in text
    assert "Est" in text


def test_summary_partial_state(
    qtbot: QtBot, request: pytest.FixtureRequest
) -> None:
    ctrl, _ = make_controller(qtbot, request)
    ctrl.stack_first_plane_set = True
    ctrl.stack_last_plane_set = False
    ctrl.stack_panel.ui.doubleSpinBox_acqFirstPlane.setValue(100.0)
    ctrl.stack_panel._render_stack_plan_summary()
    text = ctrl.stack_panel.ui.label_stackPlanSummary.text()
    assert "Set the other boundary" in text or "other boundary" in text.lower()


def test_summary_empty_state(
    qtbot: QtBot, request: pytest.FixtureRequest
) -> None:
    ctrl, _ = make_controller(qtbot, request)
    ctrl.stack_first_plane_set = False
    ctrl.stack_last_plane_set = False
    ctrl.stack_panel._render_stack_plan_summary()
    text = ctrl.stack_panel.ui.label_stackPlanSummary.text()
    assert "No stack" in text or "Drive the stage" in text


def test_persist_last_round_trip(
    qtbot: QtBot, request: pytest.FixtureRequest, tmp_path: Path
) -> None:
    """Writing StackLastStart/End/Step to a temp config.ini and reloading
    populates the spinboxes + sets the shell flags."""
    from lightsheet.config import cfg_read, cfg_write

    cfg_path = str(tmp_path / "test_config.ini")
    # Write last-stack params.
    cfg_write(cfg_path, "Controller", {
        "StackLastStart": "123.45",
        "StackLastEnd": "678.90",
        "StackLastStep": "5.0",
    })
    # Read them back.
    read = cfg_read(cfg_path, "Controller", {
        "StackLastStart": "",
        "StackLastEnd": "",
        "StackLastStep": "",
    })
    assert read["StackLastStart"] == "123.45"
    assert read["StackLastEnd"] == "678.90"
    assert read["StackLastStep"] == "5.0"


def test_controller_persists_stack_params_on_close(
    qtbot: QtBot, request: pytest.FixtureRequest, tmp_path: Path
) -> None:
    """closeEvent writes the current stack params to config.ini."""
    ctrl, _ = make_controller(qtbot, request)
    ctrl.stack_first_plane_set = True
    ctrl.stack_last_plane_set = True
    ctrl.stack_panel.ui.doubleSpinBox_acqFirstPlane.setValue(100.0)
    ctrl.stack_panel.ui.doubleSpinBox_acqLastPlane.setValue(200.0)
    ctrl.stack_panel.ui.doubleSpinBox_acqPlaneStepSize.setValue(10.0)
    ctrl.stack_starting_plane = 100.0
    ctrl.stack_ending_plane = 200.0
    # _save_stack_params skips in demo mode (to avoid corrupting the real
    # config.ini during tests); disable demo mode for this test.
    ctrl._demo_mode = False

    # Patch cfg_write to capture the written dict.
    written: list[tuple] = []  # ty: ignore[missing-type-argument]
    with patch("lightsheet.gui.shell.controller.cfg_write",
               lambda *a, **k: written.append((a, k))):
        ctrl._save_stack_params()
    assert len(written) == 1
    args, _kw = written[0]
    section_dict = args[2]
    assert "StackLastStart" in section_dict
    assert "StackLastEnd" in section_dict
    assert "StackLastStep" in section_dict
    # Restore demo mode so teardown's closeEvent does not write to the
    # real config.ini.
    ctrl._demo_mode = True


def test_summary_updates_on_edit(
    qtbot: QtBot, request: pytest.FixtureRequest
) -> None:
    ctrl, _ = make_controller(qtbot, request)
    ctrl.stack_first_plane_set = True
    ctrl.stack_last_plane_set = True
    # Stack plane positions + step are in µm (the fixed stack-display
    # unit; the global units toggle is gone). Set the spinbox values
    # directly without a units toggle.
    ctrl.stack_panel.ui.doubleSpinBox_acqFirstPlane.setValue(50.0)
    ctrl.stack_panel.ui.doubleSpinBox_acqLastPlane.setValue(150.0)
    ctrl.stack_panel.ui.doubleSpinBox_acqPlaneStepSize.setValue(5.0)
    # Trigger the number-of-planes recalc (which renders the summary).
    ctrl.stack_panel.updateUi_set_number_of_planes()
    text1 = ctrl.stack_panel.ui.label_stackPlanSummary.text()
    # Change the step and re-render; the summary must update.
    ctrl.stack_panel.ui.doubleSpinBox_acqPlaneStepSize.setValue(2.0)
    ctrl.stack_panel.updateUi_set_number_of_planes()
    text2 = ctrl.stack_panel.ui.label_stackPlanSummary.text()
    assert text1 != text2, "summary did not update on edit"
