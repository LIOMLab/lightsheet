"""Branch-coverage tests for ``lightsheet/gui/coordinators/motor_controller.py``.

Targets the missing arcs reported by ``coverage json`` (missing_branches /
missing_lines) against the real ``Controller_MainWindow`` fixture (real
``MotorController`` at ``ctrl._mc``, real ``MockMotors`` HAL, real
``motor_panel`` widgets):

- ``updateUi_move_sample_to_origin`` — the vertical ValueError reject arm
  (132-136).
- ``updateUi_move_to_stack_start`` — the out-of-bounds arm (232->246) and
  the HAL ValueError arm (237-241).
- ``updateUi_move_to_stack_end`` — the in-range try/except/else body
  (266->269: success + ValueError).
- ``updateUi_move_sample_backward`` — the in-bounds move arm (290->295)
  and its ValueError reject (300-304).
- ``updateUi_move_sample_up`` / ``_down`` / ``move_camera_backward`` /
  ``_forward`` — the ValueError reject arms (350-354, 375-379, 400-404,
  425-429).
- ``show_camera_interpolation`` / ``show_etl_interpolation`` — the whole
  display bodies including the per-plane figure loops (543-588, 592-638).

The ValueError arms are forced by patching the mock axis's move method to
raise — the same over-travel contract the real Zaber HAL enforces BEFORE
any serial write (AGENTS.md §2 reject-and-beep). ``plt`` is patched at the
module boundary so the interpolation display paths run without creating
real matplotlib windows under offscreen Qt.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, Mock

import numpy as np
import pytest
from pytestqt.qtbot import QtBot

pytest.importorskip("PySide6")

if TYPE_CHECKING:
    from lightsheet.gui.shell.controller import Controller_MainWindow


def _collect_shell_signals(
    ctrl: Controller_MainWindow,
) -> tuple[list[str], list[None]]:
    """Attach collectors to the shell's sig_message / sig_beep signals.

    Note the two message channels: ``sig_message.emit`` (collected here)
    vs ``updateUi_message_printer`` which writes directly to the
    plainTextEdit message log — assert those via ``_log_contains``.
    """
    messages: list[str] = []
    beeps: list[None] = []
    ctrl.sig_message.connect(lambda m: messages.append(m))
    ctrl.sig_beep.connect(lambda: beeps.append(None))
    return messages, beeps


def _log_contains(ctrl: Controller_MainWindow, needle: str) -> bool:
    """True if the shell's message log (updateUi_message_printer's sink)
    contains ``needle``."""
    return needle in ctrl.ui.plainTextEdit_messageLog.toPlainText()


# ---------------------------------------------------------------------------
# updateUi_move_sample_to_origin — vertical ValueError arm (132-136)
# ---------------------------------------------------------------------------


def test_move_sample_to_origin_vertical_valueerror_aborts(
    qtbot: QtBot,
    controller: Controller_MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the vertical origin move raises ValueError (over-travel at
    the HAL), the slot emits the reject-and-beep pair — and the
    horizontal block has already run its real in-range origin move."""
    ctrl = controller
    monkeypatch.setattr(
        ctrl.motors.vertical,
        "move_absolute_position",
        Mock(side_effect=ValueError("over-travel")),
    )
    messages, beeps = _collect_shell_signals(ctrl)

    ctrl._mc.updateUi_move_sample_to_origin()

    assert any("travel limits" in m for m in messages), messages
    assert len(beeps) == 1


# ---------------------------------------------------------------------------
# updateUi_move_to_stack_start — out-of-bounds (232->246) + ValueError
# (237-241)
# ---------------------------------------------------------------------------


def test_move_to_stack_start_out_of_boundaries_beeps(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """A stored starting plane outside the horizontal travel limits takes
    the else arm: 'Out of boundaries' + beep + position refresh, and the
    motor does not move."""
    ctrl = controller
    ctrl.stack_first_plane_set = True
    # Below the 0 µm low limit.
    ctrl.stack_starting_plane = -5.0
    start_pos = ctrl.motors.horizontal.get_position("μm")
    _, beeps = _collect_shell_signals(ctrl)

    ctrl._mc.updateUi_move_to_stack_start()

    assert _log_contains(ctrl, "Out of boundaries")
    assert len(beeps) == 1
    assert ctrl.motors.horizontal.get_position("μm") == pytest.approx(start_pos)


def test_move_to_stack_start_valueerror_aborts(
    qtbot: QtBot,
    controller: Controller_MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An in-range starting plane whose HAL move raises ValueError hits
    the reject-and-beep arm."""
    ctrl = controller
    ctrl.stack_first_plane_set = True
    ctrl.stack_starting_plane = 50000.0  # µm, within the mock range
    monkeypatch.setattr(
        ctrl.motors.horizontal,
        "move_absolute_position",
        Mock(side_effect=ValueError("over-travel")),
    )
    messages, beeps = _collect_shell_signals(ctrl)

    ctrl._mc.updateUi_move_to_stack_start()

    assert any("travel limits" in m for m in messages), messages
    assert len(beeps) == 1


# ---------------------------------------------------------------------------
# updateUi_move_to_stack_end — in-range try/except/else (266->269)
# ---------------------------------------------------------------------------


def test_move_to_stack_end_in_range_moves_and_reports(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """A stored ending plane inside the travel limits performs the real
    µm move and reports 'Moving to stack end'."""
    ctrl = controller
    ctrl.stack_last_plane_set = True
    ctrl.stack_ending_plane = 50000.0  # µm
    _, _ = _collect_shell_signals(ctrl)

    ctrl._mc.updateUi_move_to_stack_end()

    assert ctrl.motors.horizontal.get_position("μm") == pytest.approx(
        50000.0, rel=1e-3
    )
    assert _log_contains(ctrl, "Moving to stack end")


def test_move_to_stack_end_valueerror_aborts(
    qtbot: QtBot,
    controller: Controller_MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An in-range ending plane whose HAL move raises ValueError hits
    the reject-and-beep arm."""
    ctrl = controller
    ctrl.stack_last_plane_set = True
    ctrl.stack_ending_plane = 50000.0
    monkeypatch.setattr(
        ctrl.motors.horizontal,
        "move_absolute_position",
        Mock(side_effect=ValueError("over-travel")),
    )
    messages, beeps = _collect_shell_signals(ctrl)

    ctrl._mc.updateUi_move_to_stack_end()

    assert any("travel limits" in m for m in messages), messages
    assert len(beeps) == 1


# ---------------------------------------------------------------------------
# updateUi_move_sample_backward — in-bounds move (290->295) + ValueError
# (300-304)
# ---------------------------------------------------------------------------


def test_move_sample_backward_in_range_moves(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """With the stage away from the low limit, the pre-flight check passes
    and the real relative move executes ('Sample moving backward')."""
    ctrl = controller
    ctrl.motors.horizontal.move_absolute_position(5.0, "mm")
    ctrl.motor_panel.ui.doubleSpinBox_sampleHStepSize.setValue(1.0)
    _, _ = _collect_shell_signals(ctrl)

    ctrl._mc.updateUi_move_sample_backward()

    # Microstep quantization: 5 mm and the 1 mm step snap to whole
    # microsteps, so the resulting position is within ~1e-3 mm of 4.0.
    assert ctrl.motors.horizontal.get_position("mm") == pytest.approx(4.0, rel=1e-3)
    assert _log_contains(ctrl, "Sample moving backward")


def test_move_sample_backward_valueerror_aborts(
    qtbot: QtBot,
    controller: Controller_MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An in-bounds pre-flight check followed by a HAL ValueError hits
    the reject-and-beep arm."""
    ctrl = controller
    ctrl.motors.horizontal.move_absolute_position(5.0, "mm")
    ctrl.motor_panel.ui.doubleSpinBox_sampleHStepSize.setValue(1.0)
    monkeypatch.setattr(
        ctrl.motors.horizontal,
        "move_relative_position",
        Mock(side_effect=ValueError("over-travel")),
    )
    messages, beeps = _collect_shell_signals(ctrl)

    ctrl._mc.updateUi_move_sample_backward()

    assert any("travel limits" in m for m in messages), messages
    assert len(beeps) == 1


# ---------------------------------------------------------------------------
# ValueError arms on the remaining relative-move slots
# (350-354, 375-379, 400-404, 425-429)
# ---------------------------------------------------------------------------


def test_move_sample_up_valueerror_aborts(
    qtbot: QtBot,
    controller: Controller_MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """move_sample_up pre-flight: position - step >= limit_low. With the
    stage moved up and the HAL move raising, the reject arm fires."""
    ctrl = controller
    ctrl.motors.vertical.move_absolute_position(5.0, "mm")
    ctrl.motor_panel.ui.doubleSpinBox_sampleVStepSize.setValue(1.0)
    monkeypatch.setattr(
        ctrl.motors.vertical,
        "move_relative_position",
        Mock(side_effect=ValueError("over-travel")),
    )
    messages, beeps = _collect_shell_signals(ctrl)

    ctrl._mc.updateUi_move_sample_up()

    assert any("travel limits" in m for m in messages), messages
    assert len(beeps) == 1


def test_move_sample_down_valueerror_aborts(
    qtbot: QtBot,
    controller: Controller_MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """move_sample_down pre-flight (position + step <= limit_high) passes
    from the default position; the HAL ValueError hits the reject arm."""
    ctrl = controller
    ctrl.motor_panel.ui.doubleSpinBox_sampleVStepSize.setValue(1.0)
    monkeypatch.setattr(
        ctrl.motors.vertical,
        "move_relative_position",
        Mock(side_effect=ValueError("over-travel")),
    )
    messages, beeps = _collect_shell_signals(ctrl)

    ctrl._mc.updateUi_move_sample_down()

    assert any("travel limits" in m for m in messages), messages
    assert len(beeps) == 1


def test_move_camera_backward_valueerror_aborts(
    qtbot: QtBot,
    controller: Controller_MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """move_camera_backward with the stage moved off the low limit and a
    raising HAL move hits the reject arm."""
    ctrl = controller
    ctrl.motors.camera.move_absolute_position(5.0, "mm")
    ctrl.motor_panel.ui.doubleSpinBox_cameraStepSize.setValue(1.0)
    monkeypatch.setattr(
        ctrl.motors.camera,
        "move_relative_position",
        Mock(side_effect=ValueError("over-travel")),
    )
    messages, beeps = _collect_shell_signals(ctrl)

    ctrl._mc.updateUi_move_camera_backward()

    assert any("travel limits" in m for m in messages), messages
    assert len(beeps) == 1


def test_move_camera_forward_valueerror_aborts(
    qtbot: QtBot,
    controller: Controller_MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """move_camera_forward pre-flight passes from the default position;
    a raising HAL move hits the reject arm."""
    ctrl = controller
    ctrl.motor_panel.ui.doubleSpinBox_cameraStepSize.setValue(1.0)
    monkeypatch.setattr(
        ctrl.motors.camera,
        "move_relative_position",
        Mock(side_effect=ValueError("over-travel")),
    )
    messages, beeps = _collect_shell_signals(ctrl)

    ctrl._mc.updateUi_move_camera_forward()

    assert any("travel limits" in m for m in messages), messages
    assert len(beeps) == 1


# ---------------------------------------------------------------------------
# show_camera_interpolation (543-588) + show_etl_interpolation (592-638)
# ---------------------------------------------------------------------------


def test_show_camera_interpolation_regresses_and_plots(
    qtbot: QtBot,
    controller: Controller_MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The camera-focus interpolation computes the linregress on
    ``camera_focus_relation``, stores slope/intercept on the shell,
    flips/transposes ``donnees`` per calibration plane, and draws the
    overview + per-plane figures (plt patched at the module boundary)."""
    import lightsheet.gui.coordinators.motor_controller as mc_mod

    ctrl = controller
    # Perfectly linear relation: y = 0.4 x + 1.
    ctrl.camera_focus_relation = np.array(
        [[0.0, 1.0], [5.0, 3.0], [10.0, 5.0]]
    )
    ctrl.donnees = np.arange(20, dtype=float).reshape(2, 10)
    ctrl.number_of_calibration_planes = 2
    ctrl.number_of_camera_positions = 10
    # gaussian(x, a, x0, sigma) — 3 fit params per plane.
    ctrl.popt = [(1.0, 5.0, 2.0), (1.0, 5.0, 2.0)]
    ctrl.focus_forward_boundary = 10.0
    ctrl.focus_backward_boundary = 0.0

    fake_plt = MagicMock()
    monkeypatch.setattr(mc_mod, "plt", fake_plt)

    ctrl._mc.show_camera_interpolation()

    assert ctrl.slope_camera == pytest.approx(0.4)
    assert ctrl.intercept_camera == pytest.approx(1.0)
    # figure(1) overview + one figure per calibration plane (g + 2).
    assert fake_plt.figure.call_count == 1 + 2
    assert fake_plt.imshow.called
    assert fake_plt.show.called


def test_show_etl_interpolation_regresses_and_plots(
    qtbot: QtBot,
    controller: Controller_MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ETL interpolation runs both linregress calls (left + right),
    draws the overview figure plus one debug figure per ETL point."""
    import lightsheet.gui.coordinators.motor_controller as mc_mod

    ctrl = controller
    ctrl.etl_l_relation = np.array([[0.0, 0.0], [1.0, 1.0], [2.0, 2.0]])
    ctrl.etl_r_relation = np.array([[0.0, 2.0], [1.0, 3.0], [2.0, 4.0]])
    ctrl.number_of_etls_points = 2
    ctrl.xdata = [np.arange(10, dtype=float), np.arange(10, dtype=float)]
    ctrl.ydata = [np.zeros(10), np.zeros(10)]
    # func(x, w0, x0, xR, offset) — 4 fit params per point.
    ctrl.popt = [(1.0, 0.0, 1.0, 0.0), (1.0, 0.0, 1.0, 0.0)]

    fake_plt = MagicMock()
    monkeypatch.setattr(mc_mod, "plt", fake_plt)

    ctrl._mc.show_etl_interpolation()

    assert fake_plt.figure.call_count == 1 + 2
    assert fake_plt.plot.called
    assert fake_plt.legend.called
    assert fake_plt.show.called
