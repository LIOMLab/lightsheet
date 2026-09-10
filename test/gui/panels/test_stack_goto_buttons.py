"""Stack 'go to plane' buttons + motor jog-step defaults.

pushButton_acqGoToFirstPlane / pushButton_acqGoToLastPlane drive the
horizontal stage to the stored stack boundary positions (µm) via
MotorController.updateUi_move_to_stack_start / _end. The slots keep the
reject-and-beep safety contract: unset-boundary guard, travel-limit
pre-check, and the HAL ValueError backstop. The three motor jog-step
spinboxes default to 0.1 via the .ui value property (applySpec never
calls setValue, so the .ui value survives).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lightsheet.gui.shell.controller import Controller_MainWindow

from unittest.mock import patch

import pytest
from pytestqt.qtbot import QtBot

pytest.importorskip("PySide6")


def test_goto_buttons_exist(qtbot: QtBot, controller: Controller_MainWindow) -> None:
    ctrl = controller
    from PySide6.QtWidgets import QPushButton

    assert isinstance(ctrl.stack_panel.ui.pushButton_acqGoToFirstPlane, QPushButton)
    assert isinstance(ctrl.stack_panel.ui.pushButton_acqGoToLastPlane, QPushButton)


def test_goto_start_calls_move_absolute_with_um(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """In-range stored boundary → move_absolute_position(plane_um, "μm").

    The stored stack_starting_plane is µm (the worker + motor HAL unit);
    the units argument is asserted so a mm conversion seam (1000x
    over-travel) cannot slip in.
    """
    ctrl = controller
    ctrl.stack_starting_plane = 5000.0
    ctrl.stack_first_plane_set = True
    with patch.object(ctrl.motors.horizontal, "move_absolute_position") as mock_move:
        ctrl.stack_panel.ui.pushButton_acqGoToFirstPlane.click()
    mock_move.assert_called_once_with(5000.0, "μm")


def test_goto_start_moves_stage_end_to_end(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """Real signal path: click → slot → MockMotor move. 5000.0 µm is
    inside the MockMotor horizontal range (0-~101,600 µm). Microstep
    int-truncation makes an exact match impossible — tolerance ~1 µm."""
    ctrl = controller
    ctrl.stack_starting_plane = 5000.0
    ctrl.stack_first_plane_set = True
    ctrl.stack_panel.ui.pushButton_acqGoToFirstPlane.click()
    assert ctrl.motors.horizontal.get_position("μm") == pytest.approx(5000.0, abs=1.0)


def test_goto_start_unset_boundary_beeps_and_does_not_move(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    ctrl = controller
    beeps: list[None] = []
    ctrl.sig_beep.connect(lambda: beeps.append(None))
    ctrl.stack_first_plane_set = False
    ctrl.stack_starting_plane = None
    with patch.object(ctrl.motors.horizontal, "move_absolute_position") as mock_move:
        ctrl.stack_panel.ui.pushButton_acqGoToFirstPlane.click()
    mock_move.assert_not_called()
    assert len(beeps) == 1


def test_goto_end_unset_boundary_beeps_and_does_not_move(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    ctrl = controller
    beeps: list[None] = []
    ctrl.sig_beep.connect(lambda: beeps.append(None))
    ctrl.stack_last_plane_set = False
    ctrl.stack_ending_plane = None
    with patch.object(ctrl.motors.horizontal, "move_absolute_position") as mock_move:
        ctrl.stack_panel.ui.pushButton_acqGoToLastPlane.click()
    mock_move.assert_not_called()
    assert len(beeps) == 1


def test_goto_end_out_of_range_beeps_and_does_not_move(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """A stored boundary past the travel limits is rejected by the
    pre-check — beep, no move, position unchanged."""
    ctrl = controller
    beeps: list[None] = []
    ctrl.sig_beep.connect(lambda: beeps.append(None))
    ctrl.stack_ending_plane = ctrl.motors.horizontal.get_limit_high("μm") + 1000.0
    ctrl.stack_last_plane_set = True
    pos_before = ctrl.motors.horizontal.get_position("μm")
    ctrl.stack_panel.ui.pushButton_acqGoToLastPlane.click()
    assert len(beeps) == 1
    assert ctrl.motors.horizontal.get_position("μm") == pytest.approx(pos_before)


def test_jog_step_spinboxes_default_to_point_one(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """The .ui value property (0.1) survives applySpec — FieldSpec has no
    value field by design and applySpec never calls setValue. The spec
    minimum of 0.0 admits 0.1."""
    ctrl = controller
    ui = ctrl.motor_panel.ui
    assert ui.doubleSpinBox_sampleHStepSize.value() == pytest.approx(0.1)
    assert ui.doubleSpinBox_sampleVStepSize.value() == pytest.approx(0.1)
    assert ui.doubleSpinBox_cameraStepSize.value() == pytest.approx(0.1)
