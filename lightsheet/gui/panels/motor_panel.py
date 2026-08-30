"""MotorPanelWidget — per-panel widget/controller for motor/position controls.

Owns the motor updateUi_* slots grouped by concern. Delegates move
operations to ``self._shell._mc`` (MotorController). Reads
``self._shell.ui.<objectName>`` for its widgets and ``self._shell.motors``
for shell-owned HAL state. Motor travel is displayed in millimetres (the
fixed motor-display unit; the global units toggle is gone).
"""

from __future__ import annotations

import typing

from PySide6.QtWidgets import QWidget

from lightsheet.gui.panels.ui_motor_panel import Ui_MotorPanel
from lightsheet.gui.widgets.field_spec import FIELD_SPECS

if typing.TYPE_CHECKING:
    from lightsheet.gui.shell.controller import Controller_MainWindow


class MotorPanelWidget(QWidget):
    """Motor/position controls panel — owns motor button enable/disable and
    position indicator refresh slots."""

    def __init__(self, shell: Controller_MainWindow) -> None:
        super().__init__()
        self._shell = shell
        self.ui = Ui_MotorPanel()
        self.ui.setupUi(self)
        # Apply the declarative FieldSpec policy table to every promoted
        # FieldSpecSpinBox by objectName (suffix/decimals/step/soft min-max).
        # Panels with no matching widgets skip the loop (getattr → None).
        for obj_name, spec in FIELD_SPECS.items():
            w = getattr(self.ui, obj_name, None)
            if w is not None and hasattr(w, "applySpec"):
                w.applySpec(spec)

    def updateUi_motor_buttons(self, disable_button: bool = True) -> None:
        """Enable or disable all motor buttons"""
        buttons_to_disable = [
            self.ui.pushButton_sampleStepUp,
            self.ui.pushButton_sampleGotoOrigin,
            self.ui.pushButton_sampleStepDown,
            self.ui.pushButton_sampleStepBackward,
            self.ui.pushButton_sampleStepForward,
            self.ui.pushButton_sampleGotoHPosition,
            self.ui.pushButton_sampleGotoVPosition,
            self.ui.pushButton_cameraStepBackward,
            self.ui.pushButton_cameraStepForward,
            # self.ui.pushButton_cameraGotoFocus,
            self.ui.pushButton_cameraGotoPosition,
        ]
        for button in buttons_to_disable:
            if disable_button:
                button.setEnabled(False)
            else:
                button.setEnabled(True)

    # The motor-display unit is fixed at millimetres. The global units
    # toggle that re-rendered the spinboxes + position labels on a unit
    # switch is gone; per-field suffix/decimals are applied via FieldSpec
    # in a later plan. The spinboxes keep their .ui defaults in this
    # intermediate state.
    _MOTOR_UNIT = "mm"
    _MOTOR_FORMAT = "{:.5f} mm"

    def updateUi_units(self) -> None:
        """No-op retained for backward compatibility.

        The global units toggle is gone — motor travel is always displayed
        in millimetres. Per-field suffix/decimals are applied via
        FieldSpec in a later plan. This method is kept as a no-op so
        existing call sites (e.g. updateUi_initial_hardware_state) do not
        break during the intermediate state.
        """
        return

    def updateUi_position_indicators(self) -> None:
        """Refreshes the position indicators"""
        self.updateUi_position_horizontal()
        self.updateUi_position_vertical()
        self.updateUi_position_camera()

    def updateUi_position_horizontal(self) -> None:
        """Updates the current horizontal sample position displayed"""
        self._shell.current_horizontal_position_text = self._MOTOR_FORMAT.format(
            self._shell.motors.horizontal.get_position(self._MOTOR_UNIT)
        )
        self.ui.label_sampleCurrentHPosition.setText(
            self._shell.current_horizontal_position_text
        )

    def updateUi_position_vertical(self) -> None:
        """Updates the current vertical sample position displayed"""
        self._shell.current_vertical_position_text = self._MOTOR_FORMAT.format(
            self._shell.motors.vertical.get_position(self._MOTOR_UNIT)
        )
        self.ui.label_sampleCurrentVPosition.setText(
            self._shell.current_vertical_position_text
        )

    def updateUi_position_camera(self) -> None:
        """Updates the current camera position displayed"""
        self._shell.current_camera_position_text = self._MOTOR_FORMAT.format(
            self._shell.motors.camera.get_position(self._MOTOR_UNIT)
        )
        self.ui.label_cameraCurrentPosition.setText(self._shell.current_camera_position_text)
