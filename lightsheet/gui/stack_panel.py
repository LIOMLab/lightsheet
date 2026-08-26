"""StackPanelWidget — per-panel widget/controller for stack acquisition setup.

Owns the stack updateUi_* slots grouped by concern: stack starting/ending
point selection and number-of-planes calculation. Reads
``self.ui.<objectName>`` for its widgets and ``self._shell.motors`` /
``self._shell.stack_*`` for shell-owned state. Emits through
``self._shell.sig_*``.

The boundary-set boolean migrates from checkboxes to shell flags
``self._shell.stack_first_plane_set`` / ``stack_last_plane_set``. The Set
button populates the spinbox from the motor position; the operator can also
type a value directly. Manual entry validates against the motor travel
limits and rejects with a beep on out-of-range (the worker's per-plane
ValueError catch stays as the physical-safety backstop).
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

    def __init__(self, shell: "Controller_MainWindow") -> None:
        super().__init__()
        self._shell = shell
        self.ui = Ui_StackPanel()
        self.ui.setupUi(self)
        # Seed the spinbox range from the motor travel limits as a soft
        # widget-layer block. The spinbox range is widened so an
        # out-of-range entry is accepted by the widget and then rejected
        # by the editingFinished validation (which mirrors
        # ZaberMotor.move_absolute_position's reject-and-beep). The
        # worker's per-plane ValueError catch is the physical-safety
        # backstop if the soft block slips.
        self._seed_spinbox_ranges()

    def _seed_spinbox_ranges(self) -> None:
        """Seed the first/last plane spinbox ranges from the motor travel
        limits. The range is widened beyond the limits so an out-of-range
        value is accepted by the spinbox (and then rejected by the
        editingFinished validation with a beep)."""
        motors = getattr(self._shell, "motors", None)
        if motors is None:
            # During shell __init__ the motors may not be assigned yet
            # (hardware_init runs on a 100ms timer). Use a permissive
            # default; the editingFinished validation reads the live
            # motor limits at edit time. hardware_init re-calls this.
            return
        try:
            low = float(motors.horizontal.get_limit_low("\u03bcm"))
            high = float(motors.horizontal.get_limit_high("\u03bcm"))
        except (TypeError, ValueError, AttributeError):
            # A Mock shell (structural tests) returns non-numeric values.
            return
        # Widen the range so the spinbox accepts a value just past the
        # limits (the editingFinished handler rejects it with a beep).
        margin = max(1.0, (high - low) * 0.1)
        self.ui.doubleSpinBox_acqFirstPlane.setRange(low - margin, high + margin)
        self.ui.doubleSpinBox_acqLastPlane.setRange(low - margin, high + margin)

    def updateUi_set_stack_mode_starting_point(self) -> None:
        """Defines the starting point where the first plane of the stack volume will be recorded"""  # noqa: E501
        pos = self._shell.motors.horizontal.get_position(
            "\u03bcm"
        )  # Units in micro-meters, because plane step is in micro-meters
        self._shell.stack_starting_plane = pos
        self.ui.doubleSpinBox_acqFirstPlane.setValue(pos)
        self._shell.stack_first_plane_set = True
        self.updateUi_set_number_of_planes()

    def updateUi_set_stack_mode_ending_point(self) -> None:
        """Defines the ending point of the recorded stack volume"""
        pos = self._shell.motors.horizontal.get_position(
            "\u03bcm"
        )  # Units in micro-meters, because plane step is in micro-meters
        self._shell.stack_ending_plane = pos
        self.ui.doubleSpinBox_acqLastPlane.setValue(pos)
        self._shell.stack_last_plane_set = True
        self.updateUi_set_number_of_planes()

    def _on_first_plane_edited(self) -> None:
        """editingFinished on doubleSpinBox_acqFirstPlane: validate the
        typed value against the motor travel limits. In range → update
        the shell flag + starting plane. Out of range → beep + message,
        revert, do NOT move the motor (the worker's per-plane ValueError
        catch is the physical-safety backstop)."""
        value = self.ui.doubleSpinBox_acqFirstPlane.value()
        low = self._shell.motors.horizontal.get_limit_low("\u03bcm")
        high = self._shell.motors.horizontal.get_limit_high("\u03bcm")
        if value < low or value > high:
            self._shell.sig_beep.emit()
            self._shell.sig_message.emit(
                f"Plane {value:.2f} \u03bcm is outside the stage travel limits "
                f"({low:.2f}\u2013{high:.2f} \u03bcm). Not applied \u2014 motor "
                "not moved. Adjust the value or drive the stage to a valid "
                "position."
            )
            # Revert to the last-known starting plane (or the low limit).
            revert = self._shell.stack_starting_plane
            if revert is None or revert < low or revert > high:
                revert = low
            self.ui.doubleSpinBox_acqFirstPlane.setValue(float(revert))
            return
        self._shell.stack_starting_plane = value
        self._shell.stack_first_plane_set = True
        self.updateUi_set_number_of_planes()

    def _on_last_plane_edited(self) -> None:
        """editingFinished on doubleSpinBox_acqLastPlane: same validation
        as the first-plane handler, against the ending plane."""
        value = self.ui.doubleSpinBox_acqLastPlane.value()
        low = self._shell.motors.horizontal.get_limit_low("\u03bcm")
        high = self._shell.motors.horizontal.get_limit_high("\u03bcm")
        if value < low or value > high:
            self._shell.sig_beep.emit()
            self._shell.sig_message.emit(
                f"Plane {value:.2f} \u03bcm is outside the stage travel limits "
                f"({low:.2f}\u2013{high:.2f} \u03bcm). Not applied \u2014 motor "
                "not moved. Adjust the value or drive the stage to a valid "
                "position."
            )
            revert = self._shell.stack_ending_plane
            if revert is None or revert < low or revert > high:
                revert = high
            self.ui.doubleSpinBox_acqLastPlane.setValue(float(revert))
            return
        self._shell.stack_ending_plane = value
        self._shell.stack_last_plane_set = True
        self.updateUi_set_number_of_planes()

    def updateUi_set_number_of_planes(self) -> None:
        """Calculates the number of planes that will be saved in the stack acquisition"""  # noqa: E501
        if self.ui.doubleSpinBox_acqPlaneStepSize.value() != 0:
            if (
                self._shell.stack_first_plane_set
                and self._shell.stack_last_plane_set
            ):
                # Read the boundary values from the spinboxes (the
                # operator may have typed them directly).
                self._shell.stack_starting_plane = (
                    self.ui.doubleSpinBox_acqFirstPlane.value()
                )
                self._shell.stack_ending_plane = (
                    self.ui.doubleSpinBox_acqLastPlane.value()
                )
                self._shell.number_of_planes = int(np.ceil(
                    abs(
                        (self._shell.stack_ending_plane - self._shell.stack_starting_plane)  # noqa: E501
                        / self.ui.doubleSpinBox_acqPlaneStepSize.value()
                    )
                ))
                self._shell.number_of_planes += 1  # Takes into account the initial plane  # noqa: E501
                self.ui.label_acqNumberOfPlanes.setText(str(self._shell.number_of_planes))
        else:
            self._shell.sig_message.emit("Set a non-zero value to plane step")
