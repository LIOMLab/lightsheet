"""MotorController behavior tests — motor-move + focus/interpolation-display
slots moved out of the ``Controller_MainWindow`` god object.

``MotorController`` is a plain-Python collaborator (NOT a ``QObject``) per the
established god-object-split pattern: it holds a typed shell reference and
emits through ``self._shell.sig_message`` / ``self._shell.sig_beep``, never
declaring its own ``pyqtSignal`` or calling ``.connect()``. The shell-owned
state (``ui`` widgets, ``sig_message``/``sig_beep``, ``units``,
``updateUi_position_*`` / ``updateUi_message_printer``) is read off the shell
reference; the manager holds its own ``self.motors = bundle.motors`` reference.

These tests exercise the real ``MotorController`` methods against a Mock shell
and a demo ``DeviceBundle`` (real ``MockMotors`` HAL with software-tracked
travel limits that raise ``ValueError`` on over-travel BEFORE any state
change — AGENTS.md §2). They are NOT static-source tests; they run the real
method bodies and assert on runtime behavior.
"""

from __future__ import annotations

from unittest.mock import MagicMock, Mock

import pytest

pytest.importorskip("PyQt5")  # MotorController is constructed with a QObject shell

from lightsheet.gui.motor_controller import MotorController
from lightsheet.hal import DeviceBundle, MockCamera, MockETLs, MockLaser, MockMotors, MockSigGen


class _ShellStandin:
    """Minimal shell stand-in exposing the attributes MotorController reads.

    MotorController reads ``shell.ui`` (Qt widgets), ``shell.sig_message`` /
    ``shell.sig_beep`` (signals), ``shell.units``, and the shell-owned
    ``updateUi_position_horizontal`` / ``updateUi_position_vertical`` /
    ``updateUi_position_camera`` / ``updateUi_message_printer`` /
    ``updateUi_units`` thin GUI-state setters (which stay on the shell).
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
        self.units = "mm"
        # Shell-owned GUI-state setters — record calls for assertion.
        self.message_printer_calls: list[str] = []
        self.position_calls: list[str] = []

    def updateUi_message_printer(self, message: str) -> None:
        self.message_printer_calls.append(message)

    def updateUi_position_horizontal(self) -> None:
        self.position_calls.append("horizontal")

    def updateUi_position_vertical(self) -> None:
        self.position_calls.append("vertical")

    def updateUi_position_camera(self) -> None:
        self.position_calls.append("camera")

    def updateUi_units(self) -> None:
        self.position_calls.append("units")


def _make_bundle() -> DeviceBundle:
    camera = MockCamera(verbose=True)
    siggen = MockSigGen(camera)
    motors = MockMotors()
    lasers = (
        MockLaser(wavelength=555, max_power_mw=300.0, label="Laser 1 (555 nm)"),
        MockLaser(wavelength=640, max_power_mw=150.0, label="Laser 2 (640 nm)"),
    )
    etls = MockETLs()
    return DeviceBundle(camera=camera, siggen=siggen, motors=motors, etls=etls, lasers=lasers)


def _make_mc() -> tuple[MotorController, _ShellStandin]:
    bundle = _make_bundle()
    shell = _ShellStandin()
    mc = MotorController(bundle, shell)
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
    mc.motors.horizontal.move_absolute_position = Mock(side_effect=ValueError("over-travel"))
    # The pre-move boundary check uses get_limit_low/high; provide permissive
    # values so the move is attempted (the ValueError is the gate under test).
    mc.motors.horizontal.get_limit_low = Mock(return_value=0.0)
    mc.motors.horizontal.get_limit_high = Mock(return_value=100.0)

    mc.updateUi_move_to_horizontal_position()

    # sig_message emitted with a "travel limits" message.
    assert shell.sig_message.emit.called, "sig_message.emit must be called on ValueError"
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
    shell.ui.doubleSpinBox_sampleHStepSize.value.return_value = 1.0
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
