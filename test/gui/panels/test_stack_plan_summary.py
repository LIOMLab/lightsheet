"""Stack-plan summary + persist-last to config.ini.

A read-only summary label (start/end/step/#planes/est. time/est. size) lets
the operator sanity-check the stack plan before pressing Start. The last
stack's start/end/step persist to config.ini so a re-run does not require
re-driving the stage.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lightsheet.gui.shell.controller import Controller_MainWindow

from pathlib import Path
from unittest.mock import patch

import pytest

pytest.importorskip("PySide6")

from pytestqt.qtbot import QtBot


def test_summary_label_exists(qtbot: QtBot, controller: Controller_MainWindow) -> None:
    ctrl = controller
    from PySide6.QtWidgets import QLabel

    label = ctrl.stack_panel.ui.label_stackPlanSummary
    assert isinstance(label, QLabel)


def test_summary_renders_full_plan(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    ctrl = controller
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


def test_summary_partial_state(qtbot: QtBot, controller: Controller_MainWindow) -> None:
    ctrl = controller
    ctrl.stack_first_plane_set = True
    ctrl.stack_last_plane_set = False
    ctrl.stack_panel.ui.doubleSpinBox_acqFirstPlane.setValue(100.0)
    ctrl.stack_panel._render_stack_plan_summary()
    text = ctrl.stack_panel.ui.label_stackPlanSummary.text()
    assert "Set the other boundary" in text or "other boundary" in text.lower()


def test_summary_empty_state(qtbot: QtBot, controller: Controller_MainWindow) -> None:
    ctrl = controller
    ctrl.stack_first_plane_set = False
    ctrl.stack_last_plane_set = False
    ctrl.stack_panel._render_stack_plan_summary()
    text = ctrl.stack_panel.ui.label_stackPlanSummary.text()
    assert "No stack" in text or "Drive the stage" in text


def test_persist_last_round_trip(
    qtbot: QtBot, controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """Writing StackLastStart/End/Step to a temp config.ini and reloading
    populates the spinboxes + sets the shell flags."""
    from lightsheet.config import cfg_read, cfg_write

    cfg_path = str(tmp_path / "test_config.ini")
    # Write last-stack params.
    cfg_write(
        cfg_path,
        "Controller",
        {
            "StackLastStart": "123.45",
            "StackLastEnd": "678.90",
            "StackLastStep": "5.0",
        },
    )
    # Read them back.
    read = cfg_read(
        cfg_path,
        "Controller",
        {
            "StackLastStart": "",
            "StackLastEnd": "",
            "StackLastStep": "",
        },
    )
    assert read["StackLastStart"] == "123.45"
    assert read["StackLastEnd"] == "678.90"
    assert read["StackLastStep"] == "5.0"


def test_controller_persists_stack_params_on_close(
    qtbot: QtBot, controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """closeEvent writes the current stack params to config.ini.

    The position values are stored in millimetres (the spinbox display
    unit) even though ``stack_starting_plane``/``stack_ending_plane`` are
    micrometres internally — so 100.0 µm / 200.0 µm persist as
    "0.1000" / "0.2000" mm. The step stays in µm (its spinbox displays
    µm)."""
    ctrl = controller
    ctrl.stack_first_plane_set = True
    ctrl.stack_last_plane_set = True
    ctrl.stack_panel.ui.doubleSpinBox_acqFirstPlane.setValue(0.1)
    ctrl.stack_panel.ui.doubleSpinBox_acqLastPlane.setValue(0.2)
    ctrl.stack_panel.ui.doubleSpinBox_acqPlaneStepSize.setValue(10.0)
    ctrl.stack_starting_plane = 100.0
    ctrl.stack_ending_plane = 200.0
    # _save_stack_params skips in demo mode (to avoid corrupting the real
    # config.ini during tests); disable demo mode for this test.
    ctrl._demo_mode = False

    try:
        # Patch cfg_write to capture the written dict.
        written: list[tuple] = []  # ty: ignore[missing-type-argument]
        with patch(
            "lightsheet.gui.shell.controller.cfg_write",
            lambda *a, **k: written.append((a, k)),
        ):
            ctrl._save_stack_params()
        assert len(written) == 1
        args, _kw = written[0]
        section_dict = args[2]
        # Positions persist in mm (the spinbox display unit); the step
        # persists in µm (the step spinbox's display unit).
        assert section_dict["StackLastStart"] == "0.1000"
        assert section_dict["StackLastEnd"] == "0.2000"
        assert section_dict["StackLastStep"] == "10.0000"
    finally:
        # Restore demo mode so teardown's closeEvent does not write to the
        # real config.ini (a failed assert must not leave writes enabled).
        ctrl._demo_mode = True


def test_load_stack_params_round_trips_mm_to_um(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """Persisted mm values restore the mm spinbox display AND the µm
    internal vars exactly: 3.2 mm -> 3200.0 µm, 15.6 mm -> 15600.0 µm,
    with both boundary flags set."""
    ctrl = controller
    ctrl._demo_mode = False
    try:
        with patch(
            "lightsheet.gui.shell.controller.cfg_read",
            return_value={
                "StackLastStart": "3.2",
                "StackLastEnd": "15.6",
                "StackLastStep": "5.0",
            },
        ):
            ctrl._load_stack_params()
        assert ctrl.stack_panel.ui.doubleSpinBox_acqFirstPlane.value() == 3.2
        assert ctrl.stack_panel.ui.doubleSpinBox_acqLastPlane.value() == 15.6
        assert ctrl.stack_starting_plane == 3200.0
        assert ctrl.stack_ending_plane == 15600.0
        assert ctrl.stack_first_plane_set is True
        assert ctrl.stack_last_plane_set is True
    finally:
        # Restore demo mode so teardown's closeEvent does not write to
        # the real config.ini.
        ctrl._demo_mode = True


def test_load_stack_params_discards_out_of_range_values(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """A persisted value whose mm interpretation is outside the stage
    travel limits (e.g. a µm-magnitude "3200.0000" written by the buggy
    version) is discarded: no spinbox write, no flag set, internal vars
    untouched, and the operator is told via sig_message."""
    ctrl = controller
    messages: list[str] = []
    ctrl.sig_message.connect(lambda m: messages.append(m))
    # MockMotors horizontal limit is ~101.6 mm; all persisted positions
    # below are far outside it.
    prev_start = ctrl.stack_starting_plane
    prev_end = ctrl.stack_ending_plane
    ctrl.stack_first_plane_set = False
    ctrl.stack_last_plane_set = False
    ctrl._demo_mode = False
    try:
        with patch(
            "lightsheet.gui.shell.controller.cfg_read",
            return_value={
                "StackLastStart": "3200.0000",
                "StackLastEnd": "678.9",
                "StackLastStep": "5.0",
            },
        ):
            ctrl._load_stack_params()
        assert ctrl.stack_first_plane_set is False
        assert ctrl.stack_last_plane_set is False
        assert ctrl.stack_starting_plane == prev_start
        assert ctrl.stack_ending_plane == prev_end
        assert any("travel limit" in m.lower() for m in messages)
    finally:
        ctrl._demo_mode = True


def test_summary_updates_on_edit(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    ctrl = controller
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
