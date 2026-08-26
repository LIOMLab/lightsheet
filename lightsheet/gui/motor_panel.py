"""MotorPanelWidget — per-panel widget/controller for motor/position controls.

Owns the motor updateUi_* slots grouped by concern (D-01 gui modularization).
Delegates move operations to ``self._shell._mc`` (MotorController). Reads
``self._shell.ui.<objectName>`` for its widgets and ``self._shell.motors`` /
``self._shell.units`` for shell-owned HAL/state.
"""

from __future__ import annotations

import typing

from PySide6.QtWidgets import QWidget

from lightsheet.gui.ui_motor_panel import Ui_MotorPanel

if typing.TYPE_CHECKING:
    from lightsheet.gui.controller import Controller_MainWindow


class MotorPanelWidget(QWidget):
    """Motor/position controls panel — owns motor button enable/disable and
    position indicator refresh slots."""

    def __init__(self, shell: Controller_MainWindow) -> None:
        super().__init__()
        self._shell = shell
        self.ui = Ui_MotorPanel()
        self.ui.setupUi(self)

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

    def updateUi_units(self) -> None:
        """Updates all the widgets of the motion tab after a unit change"""
        self._shell.units = self._shell.ui.comboBox_units.currentText()

        if self._shell.units == "mm":
            self._shell.units_decimals = 3
            self._shell.units_fixformat = "{:.5f} {}"
            self._shell.units_increment = 0.1
        elif self._shell.units == "\u03bcm":
            self._shell.units_decimals = 0
            self._shell.units_fixformat = "{:.2f} {}"
            self._shell.units_increment = 100

        # Updates to horizontal position
        self.ui.doubleSpinBox_sampleSetHPosition.setDecimals(self._shell.units_decimals)
        self.ui.doubleSpinBox_sampleSetHPosition.setSuffix(f" {self._shell.units}")  # noqa: E501
        self.ui.doubleSpinBox_sampleSetHPosition.setMinimum(
            self._shell.motors.horizontal.get_limit_low(self._shell.units)
        )
        self.ui.doubleSpinBox_sampleSetHPosition.setMaximum(
            self._shell.motors.horizontal.get_limit_high(self._shell.units)
        )

        # Updates to vertical position
        self.ui.doubleSpinBox_sampleSetVPosition.setDecimals(self._shell.units_decimals)
        self.ui.doubleSpinBox_sampleSetVPosition.setSuffix(f" {self._shell.units}")  # noqa: E501
        self.ui.doubleSpinBox_sampleSetVPosition.setMinimum(
            self._shell.motors.vertical.get_limit_low(self._shell.units)
        )
        self.ui.doubleSpinBox_sampleSetVPosition.setMaximum(
            self._shell.motors.vertical.get_limit_high(self._shell.units)
        )

        # Updates to camera position
        self.ui.doubleSpinBox_cameraSetPosition.setDecimals(self._shell.units_decimals)
        self.ui.doubleSpinBox_cameraSetPosition.setSuffix(f" {self._shell.units}")  # noqa: E501
        self.ui.doubleSpinBox_cameraSetPosition.setMinimum(
            self._shell.motors.camera.get_limit_low(self._shell.units)
        )
        self.ui.doubleSpinBox_cameraSetPosition.setMaximum(
            self._shell.motors.camera.get_limit_high(self._shell.units)
        )

        # Updates to horizontal step size (increment/decrement)
        self.ui.doubleSpinBox_sampleHStepSize.setValue(self._shell.units_increment)
        self.ui.doubleSpinBox_sampleHStepSize.setDecimals(self._shell.units_decimals)
        self.ui.doubleSpinBox_sampleHStepSize.setSuffix(f" {self._shell.units}")
        self.ui.doubleSpinBox_sampleHStepSize.setMinimum(10**-self._shell.units_decimals)
        maximum_horizontal_increment = (
            self.ui.doubleSpinBox_sampleSetHPosition.maximum()
            - self.ui.doubleSpinBox_sampleSetHPosition.minimum()
        )
        self.ui.doubleSpinBox_sampleHStepSize.setMaximum(maximum_horizontal_increment)

        # Updates to vertical step size (increment/decrement)
        self.ui.doubleSpinBox_sampleVStepSize.setValue(self._shell.units_increment)
        self.ui.doubleSpinBox_sampleVStepSize.setDecimals(self._shell.units_decimals)
        self.ui.doubleSpinBox_sampleVStepSize.setSuffix(f" {self._shell.units}")
        self.ui.doubleSpinBox_sampleVStepSize.setMinimum(10**-self._shell.units_decimals)
        maximum_vertical_increment = (
            self.ui.doubleSpinBox_sampleSetVPosition.maximum()
            - self.ui.doubleSpinBox_sampleSetVPosition.minimum()
        )
        self.ui.doubleSpinBox_sampleVStepSize.setMaximum(maximum_vertical_increment)

        # Updates to camera step size (increment/decrement)
        self.ui.doubleSpinBox_cameraStepSize.setValue(self._shell.units_increment)
        self.ui.doubleSpinBox_cameraStepSize.setDecimals(self._shell.units_decimals)
        self.ui.doubleSpinBox_cameraStepSize.setSuffix(f" {self._shell.units}")
        self.ui.doubleSpinBox_cameraStepSize.setMinimum(10**-self._shell.units_decimals)
        maximum_camera_increment = (
            self.ui.doubleSpinBox_cameraSetPosition.maximum()
            - self.ui.doubleSpinBox_cameraSetPosition.minimum()
        )
        self.ui.doubleSpinBox_cameraStepSize.setMaximum(maximum_camera_increment)

        # Update current positions indicators
        self.updateUi_position_indicators()

    def updateUi_position_indicators(self) -> None:
        """Refreshes the position indicators"""
        self.updateUi_position_horizontal()
        self.updateUi_position_vertical()
        self.updateUi_position_camera()

    def updateUi_position_horizontal(self) -> None:
        """Updates the current horizontal sample position displayed"""
        self._shell.current_horizontal_position_text = self._shell.units_fixformat.format(  # noqa: E501
            self._shell.motors.horizontal.get_position(self._shell.units), self._shell.units  # noqa: E501
        )
        self.ui.label_sampleCurrentHPosition.setText(
            self._shell.current_horizontal_position_text
        )

    def updateUi_position_vertical(self) -> None:
        """Updates the current vertical sample position displayed"""
        self._shell.current_vertical_position_text = self._shell.units_fixformat.format(
            self._shell.motors.vertical.get_position(self._shell.units), self._shell.units  # noqa: E501
        )
        self.ui.label_sampleCurrentVPosition.setText(
            self._shell.current_vertical_position_text
        )

    def updateUi_position_camera(self) -> None:
        """Updates the current camera position displayed"""
        self._shell.current_camera_position_text = self._shell.units_fixformat.format(
            self._shell.motors.camera.get_position(self._shell.units), self._shell.units
        )
        self.ui.label_cameraCurrentPosition.setText(self._shell.current_camera_position_text)
