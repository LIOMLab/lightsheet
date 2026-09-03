"""MotorController behavior tests — motor-move + focus/interpolation-display
slots moved out of the ``Controller_MainWindow`` god object.

``MotorController`` is a plain-Python collaborator (NOT a ``QObject``) per the
established god-object-split pattern: it holds a typed shell reference and
emits through ``self._shell.sig_message`` / ``self._shell.sig_beep``, never
declaring its own ``Signal`` or calling ``.connect()``. The shell-owned
state (``ui`` widgets, ``sig_message``/``sig_beep``,
``updateUi_position_*`` / ``updateUi_message_printer`` /
``updateUi_position_indicators``) is read off the shell reference; the
manager holds its own ``self.motors = bundle.motors`` reference. Motor
travel is in millimetres (the fixed motor-display unit; the global units
toggle is gone).

These tests exercise the real ``MotorController`` methods against a Mock shell
and a demo ``DeviceBundle`` (real ``MockMotors`` HAL with software-tracked
travel limits that raise ``ValueError`` on over-travel BEFORE any state
change — AGENTS.md §2). They are NOT static-source tests; they run the real
method bodies and assert on runtime behavior.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

pytest.importorskip("PySide6")  # MotorController is constructed with a QObject shell

from lightsheet.gui.coordinators.motor_controller import MotorController
from lightsheet.hal import (
    DeviceBundle,
)


class _ShellStandin:
    """Minimal shell stand-in exposing the attributes MotorController reads.

    MotorController reads ``shell.ui`` (Qt widgets), ``shell.sig_message`` /
    ``shell.sig_beep`` (signals), and the shell-owned
    ``updateUi_position_horizontal`` / ``updateUi_position_vertical`` /
    ``updateUi_position_camera`` / ``updateUi_position_indicators`` /
    ``updateUi_message_printer`` thin GUI-state setters (which stay on the
    shell). Motor travel is in millimetres (fixed unit).
    """

    def __init__(self) -> None:
        self.ui = Mock()
        # Default widget values used by the move slots.
        self.ui.doubleSpinBox_sampleSetHPosition.value.return_value = 5.0
        self.ui.doubleSpinBox_sampleSetVPosition.value.return_value = 5.0
        self.ui.doubleSpinBox_cameraSetPosition.value.return_value = 5.0
        self.ui.doubleSpinBox_sampleHStepSize.value.return_value = 1.0
        self.ui.doubleSpinBox_sampleVStepSize.value.return_value = 1.0
        self.ui.doubleSpinBox_cameraStepSize.value.return_value = 1.0
        self.sig_message = Mock()
        self.sig_beep = Mock()
        # Shell-owned calibration state — read by the focus/boundary slots.
        self.focus_selected = False
        self.horizontal_backward_boundary_selected = False
        self.horizontal_forward_boundary_selected = False
        self.slope_camera = 0.0
        self.intercept_camera = 0.0
        # Shell-owned GUI-state setters — record calls for assertion.
        self.message_printer_calls: list[str] = []
        self.position_calls: list[str] = []
        # MotorController delegates position/units updates to
        # shell.motor_panel (the per-panel widget module). The stand-in
        # already defines these methods, so motor_panel points to self.
        self.motor_panel = self
        # Hybrid ownership: MotorController reaches calibration_panel
        # widgets (boundary-limit buttons) via
        # self._shell.calibration_panel.ui.<name>.
        self.calibration_panel = Mock()

    def updateUi_message_printer(self, message: str) -> None:
        self.message_printer_calls.append(message)

    def updateUi_position_horizontal(self) -> None:
        self.position_calls.append("horizontal")

    def updateUi_position_vertical(self) -> None:
        self.position_calls.append("vertical")

    def updateUi_position_camera(self) -> None:
        self.position_calls.append("camera")

    def updateUi_position_indicators(self) -> None:
        self.position_calls.append("indicators")


def _make_bundle() -> DeviceBundle:
    from test.helpers.factories import make_bundle

    return make_bundle()


def _make_mc() -> tuple[MotorController, _ShellStandin]:
    bundle = _make_bundle()
    shell = _ShellStandin()
    mc = MotorController(bundle, shell)  # ty: ignore[invalid-argument-type]
    return mc, shell


# -- Test 1: ValueError abort path on absolute move -------------------------


def test_move_to_horizontal_position_valueerror_aborts_with_beep_and_message() -> None:
    """When ``move_absolute_position`` raises ``ValueError`` (over-travel),
    MotorController must emit ``sig_message`` with a "travel limits" message
    AND emit ``sig_beep``, AND the abort must be immediate — no further HAL
    call attempted after the ValueError (AGENTS.md §2 reject-and-beep).

    This is the permanent regression gate for the travel-limit ValueError
    handling: a dropped ``except ValueError`` on any move call site would let
    an over-travel command propagate up and crash the GUI thread instead of
    the safe reject-and-beep the operator expects.
    """
    mc, shell = _make_mc()
    # Force the horizontal motor's move_absolute_position to raise ValueError
    # (over-travel) — and track that it is called exactly once.
    mc.motors.horizontal.move_absolute_position = Mock(
        side_effect=ValueError("over-travel"),
    )
    # The pre-move boundary check uses get_limit_low/high; provide permissive
    # values so the move is attempted (the ValueError is the gate under test).
    mc.motors.horizontal.get_limit_low = Mock(return_value=0.0)
    mc.motors.horizontal.get_limit_high = Mock(return_value=100.0)

    mc.updateUi_move_to_horizontal_position()

    # sig_message emitted with a "travel limits" message.
    assert shell.sig_message.emit.called, (
        "sig_message.emit must be called on ValueError"
    )
    msg = shell.sig_message.emit.call_args.args[0]
    assert "travel limits" in msg, f"message must mention travel limits, got: {msg}"
    # sig_beep emitted (reject-and-beep).
    assert shell.sig_beep.emit.called, "sig_beep.emit must be called on ValueError"
    # The HAL move was attempted exactly once — no retry, no further HAL call.
    assert mc.motors.horizontal.move_absolute_position.call_count == 1


# -- Test 2: pre-flight boundary check gates the relative move --------------


def test_move_sample_backward_preflight_boundary_check_skips_hal_call() -> None:
    """When the pre-move boundary check
    (``get_position(units) - step >= get_limit_low(units)``) evaluates False,
    MotorController must NOT call ``move_relative_position`` at all — the
    pre-flight boundary check (not just the HAL-level ValueError) also gates
    the call. This is the second layer of over-travel protection before the
    HAL is even touched.
    """
    mc, shell = _make_mc()
    # Configure so the pre-flight check fails:
    #   get_position(units) - step < get_limit_low(units)
    # i.e. position=0, step=1, limit_low=0  =>  0 - 1 = -1 < 0  =>  False
    mc.motors.horizontal.get_position = Mock(return_value=0.0)
    mc.motors.horizontal.get_limit_low = Mock(return_value=0.0)
    shell.motor_panel.ui.doubleSpinBox_sampleHStepSize.value.return_value = 1.0
    mc.motors.horizontal.move_relative_position = Mock()

    mc.updateUi_move_sample_backward()

    # The HAL move was never called — the pre-flight check gated it.
    assert not mc.motors.horizontal.move_relative_position.called, (
        "move_relative_position must NOT be called when the pre-flight "
        "boundary check fails"
    )
    # The operator is informed via message_printer ("Out of boundaries") + beep.
    assert any("Out of boundaries" in m for m in shell.message_printer_calls), (
        "operator must be informed the move was out of boundaries"
    )
    assert shell.sig_beep.emit.called


# -- Absolute-move slots: in-range happy path + out-of-boundaries path -------
#
# The three axes (horizontal/vertical/camera) share the same three arcs
# (in-range happy path, ValueError abort, out-of-boundaries beep). The
# horizontal ValueError arc has its own dedicated regression gate above
# (test_move_to_horizontal_position_valueerror_aborts_with_beep_and_message)
# because it carries the full reject-and-beep contract assertion. The
# remaining 8 arcs are covered by three per-condition tests, each
# exercising all three axes.


def test_move_to_position_in_range_emits_moving_message() -> None:
    """In-range absolute move calls move_absolute_position and emits the
    per-axis 'moving to ... position' message (the happy path) for all
    three axes."""
    mc, shell = _make_mc()
    mc.motors.horizontal.move_absolute_position = Mock()
    shell.motor_panel.ui.doubleSpinBox_sampleSetHPosition.value.return_value = 5.0
    mc.updateUi_move_to_horizontal_position()
    mc.motors.horizontal.move_absolute_position.assert_called_once()
    assert any(
        "Sample moving to horizontal position" in m for m in shell.message_printer_calls
    )

    mc, shell = _make_mc()
    mc.motors.vertical.move_absolute_position = Mock()
    shell.motor_panel.ui.doubleSpinBox_sampleSetVPosition.value.return_value = 5.0
    mc.updateUi_move_to_vertical_position()
    mc.motors.vertical.move_absolute_position.assert_called_once()
    assert any(
        "Sample moving to vertical position" in m for m in shell.message_printer_calls
    )

    mc, shell = _make_mc()
    mc.motors.camera.move_absolute_position = Mock()
    shell.motor_panel.ui.doubleSpinBox_cameraSetPosition.value.return_value = 5.0
    mc.updateUi_move_camera_to_position()
    mc.motors.camera.move_absolute_position.assert_called_once()
    assert any("Camera moving to position" in m for m in shell.message_printer_calls)


def test_move_to_position_valueerror_aborts() -> None:
    """ValueError (over-travel) on absolute move emits sig_message + beep
    for the vertical and camera axes. The horizontal axis is covered by
    the dedicated reject-and-beep regression gate above."""
    mc, shell = _make_mc()
    mc.motors.vertical.move_absolute_position = Mock(
        side_effect=ValueError("over-travel"),
    )
    mc.motors.vertical.get_limit_low = Mock(return_value=0.0)
    mc.motors.vertical.get_limit_high = Mock(return_value=100.0)
    mc.updateUi_move_to_vertical_position()
    assert shell.sig_message.emit.called
    assert shell.sig_beep.emit.called

    mc, shell = _make_mc()
    mc.motors.camera.move_absolute_position = Mock(
        side_effect=ValueError("over-travel"),
    )
    mc.motors.camera.get_limit_low = Mock(return_value=0.0)
    mc.motors.camera.get_limit_high = Mock(return_value=100.0)
    mc.updateUi_move_camera_to_position()
    assert shell.sig_message.emit.called
    assert shell.sig_beep.emit.called


def test_move_to_position_out_of_boundaries_beeps() -> None:
    """Out-of-boundaries absolute move skips the HAL call and emits 'Out of
    boundaries' + beep (the else branch of the outer if) for all three
    axes."""
    mc, shell = _make_mc()
    mc.motors.horizontal.move_absolute_position = Mock()
    mc.motors.horizontal.get_limit_low = Mock(return_value=10.0)
    mc.motors.horizontal.get_limit_high = Mock(return_value=20.0)
    shell.motor_panel.ui.doubleSpinBox_sampleSetHPosition.value.return_value = 5.0
    mc.updateUi_move_to_horizontal_position()
    mc.motors.horizontal.move_absolute_position.assert_not_called()
    assert any("Out of boundaries" in m for m in shell.message_printer_calls)
    assert shell.sig_beep.emit.called

    mc, shell = _make_mc()
    mc.motors.vertical.move_absolute_position = Mock()
    mc.motors.vertical.get_limit_low = Mock(return_value=10.0)
    mc.motors.vertical.get_limit_high = Mock(return_value=20.0)
    shell.motor_panel.ui.doubleSpinBox_sampleSetVPosition.value.return_value = 5.0
    mc.updateUi_move_to_vertical_position()
    mc.motors.vertical.move_absolute_position.assert_not_called()
    assert shell.sig_beep.emit.called

    mc, shell = _make_mc()
    mc.motors.camera.move_absolute_position = Mock()
    mc.motors.camera.get_limit_low = Mock(return_value=10.0)
    mc.motors.camera.get_limit_high = Mock(return_value=20.0)
    shell.motor_panel.ui.doubleSpinBox_cameraSetPosition.value.return_value = 5.0
    mc.updateUi_move_camera_to_position()
    mc.motors.camera.move_absolute_position.assert_not_called()
    assert shell.sig_beep.emit.called


# -- move_sample_to_origin: 4 branches (h/v in-range + out-of-boundaries) ----


def test_move_sample_to_origin_both_in_range() -> None:
    """Both horizontal + vertical origins in range -> both moves attempted,
    'Moving to ... origin' messages emitted."""
    mc, shell = _make_mc()
    mc.motors.horizontal.move_absolute_position = Mock()
    mc.motors.vertical.move_absolute_position = Mock()
    mc.motors.horizontal.get_origin = Mock(return_value=5.0)
    mc.motors.vertical.get_origin = Mock(return_value=5.0)
    mc.motors.horizontal.get_limit_low = Mock(return_value=0.0)
    mc.motors.horizontal.get_limit_high = Mock(return_value=100.0)
    mc.motors.vertical.get_limit_low = Mock(return_value=0.0)
    mc.motors.vertical.get_limit_high = Mock(return_value=100.0)
    mc.updateUi_move_sample_to_origin()
    mc.motors.horizontal.move_absolute_position.assert_called_once()
    mc.motors.vertical.move_absolute_position.assert_called_once()
    assert any("Moving to horizontal origin" in m for m in shell.message_printer_calls)
    assert any("Moving to vertical origin" in m for m in shell.message_printer_calls)


def test_move_sample_to_origin_horizontal_out_of_boundaries() -> None:
    """Horizontal origin out of boundaries -> horizontal move skipped,
    'Horizontal origin out of boundaries' message + beep."""
    mc, shell = _make_mc()
    mc.motors.horizontal.move_absolute_position = Mock()
    mc.motors.vertical.move_absolute_position = Mock()
    mc.motors.horizontal.get_origin = Mock(return_value=200.0)
    mc.motors.vertical.get_origin = Mock(return_value=5.0)
    mc.motors.horizontal.get_limit_low = Mock(return_value=0.0)
    mc.motors.horizontal.get_limit_high = Mock(return_value=100.0)
    mc.motors.vertical.get_limit_low = Mock(return_value=0.0)
    mc.motors.vertical.get_limit_high = Mock(return_value=100.0)
    mc.updateUi_move_sample_to_origin()
    mc.motors.horizontal.move_absolute_position.assert_not_called()
    assert any(
        "Horizontal origin out of boundaries" in m for m in shell.message_printer_calls
    )


def test_move_sample_to_origin_vertical_out_of_boundaries() -> None:
    mc, shell = _make_mc()
    mc.motors.horizontal.move_absolute_position = Mock()
    mc.motors.vertical.move_absolute_position = Mock()
    mc.motors.horizontal.get_origin = Mock(return_value=5.0)
    mc.motors.vertical.get_origin = Mock(return_value=200.0)
    mc.motors.horizontal.get_limit_low = Mock(return_value=0.0)
    mc.motors.horizontal.get_limit_high = Mock(return_value=100.0)
    mc.motors.vertical.get_limit_low = Mock(return_value=0.0)
    mc.motors.vertical.get_limit_high = Mock(return_value=100.0)
    mc.updateUi_move_sample_to_origin()
    mc.motors.vertical.move_absolute_position.assert_not_called()
    assert any(
        "Vertical origin out of boundaries" in m for m in shell.message_printer_calls
    )


def test_move_sample_to_origin_horizontal_valueerror_aborts() -> None:
    """ValueError on horizontal origin move emits sig_message + beep."""
    mc, shell = _make_mc()
    mc.motors.horizontal.move_absolute_position = Mock(
        side_effect=ValueError("over-travel"),
    )
    mc.motors.vertical.move_absolute_position = Mock()
    mc.motors.horizontal.get_origin = Mock(return_value=5.0)
    mc.motors.vertical.get_origin = Mock(return_value=5.0)
    mc.motors.horizontal.get_limit_low = Mock(return_value=0.0)
    mc.motors.horizontal.get_limit_high = Mock(return_value=100.0)
    mc.motors.vertical.get_limit_low = Mock(return_value=0.0)
    mc.motors.vertical.get_limit_high = Mock(return_value=100.0)
    mc.updateUi_move_sample_to_origin()
    assert shell.sig_message.emit.called


# -- move_camera_to_focus: focus_selected True/False + 3 sub-branches --------


def test_move_camera_to_focus_focus_selected_in_range() -> None:
    """focus_selected=True and origin within limits -> move attempted,
    'Moving to focus' message."""
    mc, shell = _make_mc()
    mc.motors.camera.move_absolute_position = Mock()
    shell.focus_selected = True
    mc.motors.camera.get_origin = Mock(return_value=5.0)
    mc.motors.camera.get_limit_low = Mock(return_value=0.0)
    mc.motors.camera.get_limit_high = Mock(return_value=100.0)
    mc.updateUi_move_camera_to_focus()
    mc.motors.camera.move_absolute_position.assert_called_once()
    assert any("Moving to focus" in m for m in shell.message_printer_calls)


def test_move_camera_to_focus_focus_selected_above_high_boundary() -> None:
    """focus_selected=True, origin > limit_high -> 'Focus out of boundaries' + beep."""
    mc, shell = _make_mc()
    mc.motors.camera.move_absolute_position = Mock()
    shell.focus_selected = True
    mc.motors.camera.get_origin = Mock(return_value=200.0)
    mc.motors.camera.get_limit_low = Mock(return_value=0.0)
    mc.motors.camera.get_limit_high = Mock(return_value=100.0)
    mc.updateUi_move_camera_to_focus()
    mc.motors.camera.move_absolute_position.assert_not_called()
    assert any("Focus out of boundaries" in m for m in shell.message_printer_calls)


def test_move_camera_to_focus_focus_selected_below_low_boundary() -> None:
    """focus_selected=True, origin < limit_low -> 'Focus out of boundaries' + beep."""
    mc, shell = _make_mc()
    mc.motors.camera.move_absolute_position = Mock()
    shell.focus_selected = True
    mc.motors.camera.get_origin = Mock(return_value=-1.0)
    mc.motors.camera.get_limit_low = Mock(return_value=0.0)
    mc.motors.camera.get_limit_high = Mock(return_value=100.0)
    mc.updateUi_move_camera_to_focus()
    mc.motors.camera.move_absolute_position.assert_not_called()
    assert any("Focus out of boundaries" in m for m in shell.message_printer_calls)


def test_move_camera_to_focus_focus_selected_valueerror_aborts() -> None:
    """focus_selected=True, in-range but HAL raises ValueError -> sig_message + beep."""
    mc, shell = _make_mc()
    mc.motors.camera.move_absolute_position = Mock(
        side_effect=ValueError("over-travel"),
    )
    shell.focus_selected = True
    mc.motors.camera.get_origin = Mock(return_value=5.0)
    mc.motors.camera.get_limit_low = Mock(return_value=0.0)
    mc.motors.camera.get_limit_high = Mock(return_value=100.0)
    mc.updateUi_move_camera_to_focus()
    assert shell.sig_message.emit.called
    assert shell.sig_beep.emit.called


def test_move_camera_to_focus_not_selected_moves_to_default() -> None:
    """focus_selected=False -> move to origin attempted, 'Focus not yet set' message."""
    mc, shell = _make_mc()
    mc.motors.camera.move_absolute_position = Mock()
    shell.focus_selected = False
    mc.motors.camera.get_origin = Mock(return_value=5.0)
    mc.updateUi_move_camera_to_focus()
    mc.motors.camera.move_absolute_position.assert_called_once()
    assert any("Focus not yet set" in m for m in shell.message_printer_calls)


def test_move_camera_to_focus_not_selected_valueerror_aborts() -> None:
    """focus_selected=False, HAL raises ValueError -> sig_message + beep."""
    mc, shell = _make_mc()
    mc.motors.camera.move_absolute_position = Mock(
        side_effect=ValueError("over-travel"),
    )
    shell.focus_selected = False
    mc.motors.camera.get_origin = Mock(return_value=5.0)
    mc.updateUi_move_camera_to_focus()
    assert shell.sig_message.emit.called
    assert shell.sig_beep.emit.called


# -- Relative-move slots: forward/backward/up/down for sample + camera -------


def test_move_sample_forward_in_range_emits_moving_message() -> None:
    mc, shell = _make_mc()
    mc.motors.horizontal.move_relative_position = Mock()
    mc.motors.horizontal.get_position = Mock(return_value=5.0)
    mc.motors.horizontal.get_limit_high = Mock(return_value=100.0)
    shell.motor_panel.ui.doubleSpinBox_sampleHStepSize.value.return_value = 1.0
    mc.updateUi_move_sample_forward()
    mc.motors.horizontal.move_relative_position.assert_called_once()
    assert any("Sample moving forward" in m for m in shell.message_printer_calls)


def test_move_sample_forward_out_of_boundaries_beeps() -> None:
    mc, shell = _make_mc()
    mc.motors.horizontal.move_relative_position = Mock()
    mc.motors.horizontal.get_position = Mock(return_value=99.0)
    mc.motors.horizontal.get_limit_high = Mock(return_value=100.0)
    shell.motor_panel.ui.doubleSpinBox_sampleHStepSize.value.return_value = 5.0
    mc.updateUi_move_sample_forward()
    mc.motors.horizontal.move_relative_position.assert_not_called()
    assert any("Out of boundaries" in m for m in shell.message_printer_calls)


def test_move_sample_forward_valueerror_aborts() -> None:
    mc, shell = _make_mc()
    mc.motors.horizontal.move_relative_position = Mock(
        side_effect=ValueError("over-travel"),
    )
    mc.motors.horizontal.get_position = Mock(return_value=5.0)
    mc.motors.horizontal.get_limit_high = Mock(return_value=100.0)
    shell.motor_panel.ui.doubleSpinBox_sampleHStepSize.value.return_value = 1.0
    mc.updateUi_move_sample_forward()
    assert shell.sig_message.emit.called
    assert shell.sig_beep.emit.called


def test_move_sample_up_in_range_emits_moving_message() -> None:
    mc, shell = _make_mc()
    mc.motors.vertical.move_relative_position = Mock()
    mc.motors.vertical.get_position = Mock(return_value=5.0)
    mc.motors.vertical.get_limit_low = Mock(return_value=0.0)
    shell.motor_panel.ui.doubleSpinBox_sampleVStepSize.value.return_value = 1.0
    mc.updateUi_move_sample_up()
    mc.motors.vertical.move_relative_position.assert_called_once()
    assert any("Sample stepping up" in m for m in shell.message_printer_calls)


def test_move_sample_up_out_of_boundaries_beeps() -> None:
    mc, shell = _make_mc()
    mc.motors.vertical.move_relative_position = Mock()
    mc.motors.vertical.get_position = Mock(return_value=1.0)
    mc.motors.vertical.get_limit_low = Mock(return_value=0.0)
    shell.motor_panel.ui.doubleSpinBox_sampleVStepSize.value.return_value = 5.0
    mc.updateUi_move_sample_up()
    mc.motors.vertical.move_relative_position.assert_not_called()
    assert any("Out of boundaries" in m for m in shell.message_printer_calls)


def test_move_sample_down_in_range_emits_moving_message() -> None:
    mc, shell = _make_mc()
    mc.motors.vertical.move_relative_position = Mock()
    mc.motors.vertical.get_position = Mock(return_value=5.0)
    mc.motors.vertical.get_limit_high = Mock(return_value=100.0)
    shell.motor_panel.ui.doubleSpinBox_sampleVStepSize.value.return_value = 1.0
    mc.updateUi_move_sample_down()
    mc.motors.vertical.move_relative_position.assert_called_once()
    assert any("Sample stepping down" in m for m in shell.message_printer_calls)


def test_move_sample_down_out_of_boundaries_beeps() -> None:
    mc, shell = _make_mc()
    mc.motors.vertical.move_relative_position = Mock()
    mc.motors.vertical.get_position = Mock(return_value=99.0)
    mc.motors.vertical.get_limit_high = Mock(return_value=100.0)
    shell.motor_panel.ui.doubleSpinBox_sampleVStepSize.value.return_value = 5.0
    mc.updateUi_move_sample_down()
    mc.motors.vertical.move_relative_position.assert_not_called()
    assert any("Out of boundaries" in m for m in shell.message_printer_calls)


def test_move_camera_backward_in_range_emits_moving_message() -> None:
    mc, shell = _make_mc()
    mc.motors.camera.move_relative_position = Mock()
    mc.motors.camera.get_position = Mock(return_value=5.0)
    mc.motors.camera.get_limit_low = Mock(return_value=0.0)
    shell.motor_panel.ui.doubleSpinBox_cameraStepSize.value.return_value = 1.0
    mc.updateUi_move_camera_backward()
    mc.motors.camera.move_relative_position.assert_called_once()
    assert any("Camera stepping backward" in m for m in shell.message_printer_calls)


def test_move_camera_backward_out_of_boundaries_beeps() -> None:
    mc, shell = _make_mc()
    mc.motors.camera.move_relative_position = Mock()
    mc.motors.camera.get_position = Mock(return_value=1.0)
    mc.motors.camera.get_limit_low = Mock(return_value=0.0)
    shell.motor_panel.ui.doubleSpinBox_cameraStepSize.value.return_value = 5.0
    mc.updateUi_move_camera_backward()
    mc.motors.camera.move_relative_position.assert_not_called()
    assert any("Out of boundaries" in m for m in shell.message_printer_calls)


def test_move_camera_forward_in_range_emits_moving_message() -> None:
    mc, shell = _make_mc()
    mc.motors.camera.move_relative_position = Mock()
    mc.motors.camera.get_position = Mock(return_value=5.0)
    mc.motors.camera.get_limit_high = Mock(return_value=100.0)
    shell.motor_panel.ui.doubleSpinBox_cameraStepSize.value.return_value = 1.0
    mc.updateUi_move_camera_forward()
    mc.motors.camera.move_relative_position.assert_called_once()
    assert any("Camera stepping forward" in m for m in shell.message_printer_calls)


def test_move_camera_forward_out_of_boundaries_beeps() -> None:
    mc, shell = _make_mc()
    mc.motors.camera.move_relative_position = Mock()
    mc.motors.camera.get_position = Mock(return_value=99.0)
    mc.motors.camera.get_limit_high = Mock(return_value=100.0)
    shell.motor_panel.ui.doubleSpinBox_cameraStepSize.value.return_value = 5.0
    mc.updateUi_move_camera_forward()
    mc.motors.camera.move_relative_position.assert_not_called()
    assert any("Out of boundaries" in m for m in shell.message_printer_calls)


# -- Boundary / origin / focus set slots ------------------------------------


def test_reset_boundaries_resets_limits_and_disables_buttons() -> None:
    mc, shell = _make_mc()
    mc.motors.horizontal.set_limit_low = Mock()
    mc.motors.horizontal.set_limit_high = Mock()
    mc.updateUi_reset_boundaries()
    mc.motors.horizontal.set_limit_low.assert_called_once()
    mc.motors.horizontal.set_limit_high.assert_called_once()
    shell.calibration_panel.ui.pushButton_calHorizontalStartRangeSelection.setEnabled.assert_called_with(
        False
    )
    assert "indicators" in shell.position_calls


def test_set_horizontal_backward_boundary_sets_limit_low() -> None:
    mc, shell = _make_mc()
    mc.motors.horizontal.set_limit_low = Mock()
    mc.motors.horizontal.get_position = Mock(return_value=3.0)
    shell.horizontal_forward_boundary_selected = False
    mc.updateUi_set_horizontal_backward_boundary()
    mc.motors.horizontal.set_limit_low.assert_called_once()
    assert shell.horizontal_backward_boundary_selected is True


def test_set_horizontal_backward_boundary_with_forward_already_set_enables_start() -> (
    None
):
    """When horizontal_forward_boundary_selected is True, setting the
    backward boundary enables the start-range button (the if-branch)."""
    mc, shell = _make_mc()
    mc.motors.horizontal.set_limit_low = Mock()
    mc.motors.horizontal.get_position = Mock(return_value=3.0)
    shell.horizontal_forward_boundary_selected = True
    mc.updateUi_set_horizontal_backward_boundary()
    shell.calibration_panel.ui.pushButton_calHorizontalStartRangeSelection.setEnabled.assert_called_with(
        True
    )


def test_set_horizontal_forward_boundary_sets_limit_high() -> None:
    mc, shell = _make_mc()
    mc.motors.horizontal.set_limit_high = Mock()
    mc.motors.horizontal.get_position = Mock(return_value=7.0)
    shell.horizontal_backward_boundary_selected = False
    mc.updateUi_set_horizontal_forward_boundary()
    mc.motors.horizontal.set_limit_high.assert_called_once()
    assert shell.horizontal_forward_boundary_selected is True


def test_set_horizontal_forward_boundary_with_backward_already_set_enables_start() -> (
    None
):
    mc, shell = _make_mc()
    mc.motors.horizontal.set_limit_high = Mock()
    mc.motors.horizontal.get_position = Mock(return_value=7.0)
    shell.horizontal_backward_boundary_selected = True
    mc.updateUi_set_horizontal_forward_boundary()
    shell.calibration_panel.ui.pushButton_calHorizontalStartRangeSelection.setEnabled.assert_called_with(
        True
    )


def test_set_sample_origin_sets_origin_and_emits_message() -> None:
    mc, shell = _make_mc()
    mc.motors.horizontal.set_origin = Mock()
    mc.motors.vertical.set_origin = Mock()
    mc.motors.horizontal.get_position = Mock(return_value=3.0)
    mc.motors.vertical.get_position = Mock(return_value=4.0)
    mc.motors.horizontal.get_origin = Mock(return_value=3.0)
    mc.motors.vertical.get_origin = Mock(return_value=4.0)
    mc.updateUi_set_sample_origin()
    mc.motors.horizontal.set_origin.assert_called_once()
    mc.motors.vertical.set_origin.assert_called_once()
    assert any("Sample origin set" in m for m in shell.message_printer_calls)


def test_set_camera_focus_sets_origin_and_emits_message() -> None:
    mc, shell = _make_mc()
    mc.motors.camera.set_origin = Mock()
    mc.motors.camera.get_position = Mock(return_value=5.0)
    mc.motors.camera.get_origin = Mock(return_value=5.0)
    mc.updateUi_set_camera_focus()
    mc.motors.camera.set_origin.assert_called_once()
    assert shell.focus_selected is True
    assert any("Camera focus manually set" in m for m in shell.message_printer_calls)


# -- Focus-calculation + interpolation-display methods ----------------------


def test_calculate_camera_focus_sets_origin_and_focus_selected() -> None:
    """calculate_camera_focus computes focus_regression from slope/intercept
    and sets the camera origin + focus_selected flag."""
    mc, shell = _make_mc()
    mc.motors.horizontal.get_position = Mock(return_value=10.0)
    shell.slope_camera = 0.5
    shell.intercept_camera = 1.0
    mc.motors.camera.set_origin = Mock()
    mc.calculate_camera_focus()
    # focus_regression = 0.5 * 10 + 1.0 = 6.0
    mc.motors.camera.set_origin.assert_called_once()
    args, _ = mc.motors.camera.set_origin.call_args
    assert args[0] == pytest.approx(6.0)
    assert shell.focus_selected is True
    assert any("Focus automatically set" in m for m in shell.message_printer_calls)
