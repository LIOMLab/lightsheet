"""StackPanelWidget — per-panel widget/controller for stack acquisition setup.

Owns the stack updateUi_* slots grouped by concern (D-01 gui modularization):
stack starting/ending point selection and number-of-planes calculation. Reads
``self._shell.ui.<objectName>`` for its widgets and ``self._shell.motors`` /
``self._shell.stack_*`` for shell-owned state. Emits through
``self._shell.sig_*``.
"""

from __future__ import annotations

import typing

import numpy as np
from PySide6.QtWidgets import QWidget

from lightsheet.gui.ui_stack_panel import Ui_StackPanel

if typing.TYPE_CHECKING:
    from lightsheet.gui.controller import Controller_MainWindow


class StackPanelWidget(QWidget):
    """Stack acquisition setup panel — owns stack starting/ending point
    and number-of-planes calculation slots."""

    def __init__(self, shell: Controller_MainWindow) -> None:
        super().__init__()
        self._shell = shell
        self.ui = Ui_StackPanel()
        self.ui.setupUi(self)

    def updateUi_set_stack_mode_starting_point(self) -> None:
        """Defines the starting point where the first plane of the stack volume will be recorded"""  # noqa: E501
        self._shell.stack_starting_plane = self._shell.motors.horizontal.get_position(
            "\u03bcm"
        )  # Units in micro-meters, because plane step is in micro-meters
        self._shell.ui.checkBox_acqFirstPlaneSet.setChecked(True)
        self.updateUi_set_number_of_planes()

    def updateUi_set_stack_mode_ending_point(self) -> None:
        """Defines the ending point of the recorded stack volume"""
        self._shell.stack_ending_plane = self._shell.motors.horizontal.get_position(
            "\u03bcm"
        )  # Units in micro-meters, because plane step is in micro-meters
        self._shell.ui.checkBox_acqLastPlaneSet.setChecked(True)
        self.updateUi_set_number_of_planes()

    def updateUi_set_number_of_planes(self) -> None:
        """Calculates the number of planes that will be saved in the stack acquisition"""  # noqa: E501
        if self._shell.ui.doubleSpinBox_acqPlaneStepSize.value() != 0:
            if (
                self._shell.ui.checkBox_acqFirstPlaneSet.isChecked()
                and self._shell.ui.checkBox_acqLastPlaneSet.isChecked()
            ):
                self._shell.number_of_planes = np.ceil(
                    abs(
                        (self._shell.stack_ending_plane - self._shell.stack_starting_plane)  # noqa: E501
                        / self._shell.ui.doubleSpinBox_acqPlaneStepSize.value()
                    )
                )
                self._shell.number_of_planes += 1  # Takes into account the initial plane  # noqa: E501
                self._shell.ui.label_acqNumberOfPlanes.setText(str(self._shell.number_of_planes))
        else:
            self._shell.sig_message.emit("Set a non-zero value to plane step")
