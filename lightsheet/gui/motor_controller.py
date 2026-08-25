"""MotorController — god-object split collaborator.

Owns all sample/vertical/camera motor-move GUI-thread slots plus the
focus-calibration-display methods (``calculate_camera_focus``,
``show_camera_interpolation``, ``show_etl_interpolation``) moved verbatim
from ``Controller_MainWindow``. Every motor move's ``try/except ValueError``
-> ``sig_message.emit`` + ``sig_beep.emit`` abort survives the move verbatim
(AGENTS.md §2 travel-limit enforcement — only the ``self.``-prefix on
shell-owned attributes changes to ``self._shell.``).

Does NOT own an ``estop()``/kill-path method of any kind (safety
anti-pattern, mirroring the HardwareManager anti-pattern check). The E-stop
kill path (``Controller_MainWindow.updateUi_estop_pressed``) stays in the
thin shell with a direct ``list[ILaser]`` ref, lock-free, on the GUI thread.
A future maintainer who sees ``MotorController.estop()`` will be tempted to
queue/thread it — the single most safety-critical regression risk.
MotorController is a motion collaborator, NOT a safety kill-path owner.

This is a plain-Python object (NOT a ``QObject``) per the plain-Python
collaborator pattern: collaborators emit through a shell reference, never
declare their own ``Signal``, and never call ``.connect()``. The
shell-owned state (``ui`` widgets, ``sig_message``/``sig_beep``, ``units``,
``updateUi_position_*`` / ``updateUi_message_printer`` / ``updateUi_units``
thin GUI-state setters, ``focus_selected`` /
``horizontal_backward_boundary_selected`` /
``horizontal_forward_boundary_selected`` /
``camera_focus_relation`` / ``slope_camera`` / ``intercept_camera`` /
``donnees`` / ``popt`` / ``xdata`` / ``ydata`` /
``focus_forward_boundary`` / ``focus_backward_boundary`` /
``number_of_calibration_planes`` / ``number_of_camera_positions`` /
``number_of_etls_points`` / ``etl_l_relation`` / ``etl_r_relation``) is read
off the shell reference. The controller holds its own ``self.motors =
bundle.motors`` reference (identical objects to ``shell.motors``); the camera
HAL stays ``self._shell.camera`` since MotorController does not own the
camera HAL.
"""

from __future__ import annotations

import copy
import logging
from typing import TYPE_CHECKING

import numpy as np
from matplotlib import pyplot as plt
from scipy import stats

from lightsheet.gaussian import func, gaussian
from lightsheet.hal.bundle import DeviceBundle

if TYPE_CHECKING:
    from lightsheet.gui.controller import Controller_MainWindow

logger = logging.getLogger(__name__)


class MotorController:
    """Motor-move + focus/interpolation-display collaborator.

    All 19 motor-move / focus-calibration-display methods moved verbatim from
    ``Controller_MainWindow`` — only the attribute-access prefix changes
    (``self.`` -> ``self._shell.`` for shell-owned state; ``self.motors``
    stays ``self.motors`` since the controller holds its own bundle.motors
    reference). Every existing ``except ValueError:`` -> ``sig_message.emit``
    + ``sig_beep.emit`` abort path survives unchanged (AGENTS.md §2
    travel-limit enforcement).
    """

    def __init__(self, bundle: DeviceBundle, shell: "Controller_MainWindow") -> None:
        self._bundle = bundle
        self._shell = shell
        # Direct IMotors reference — identical objects to shell.motors (the
        # shell's bundle.motors). MotorController owns the motor-move call
        # graph; the camera HAL stays on the shell (self._shell.camera) since
        # MotorController does not own the camera HAL.
        self.motors = bundle.motors

    # ------------------------------------------------------------------ #
    # Sample / vertical / camera absolute-move slots.
    # ------------------------------------------------------------------ #

    def updateUi_move_to_horizontal_position(self) -> None:
        """Moves the sample to a specified horizontal position"""
        if (
            self._shell.ui.doubleSpinBox_sampleSetHPosition.value()
            >= self.motors.horizontal.get_limit_low(self._shell.units)
        ) and (
            self._shell.ui.doubleSpinBox_sampleSetHPosition.value()
            <= self.motors.horizontal.get_limit_high(self._shell.units)
        ):
            try:
                self.motors.horizontal.move_absolute_position(
                    self._shell.ui.doubleSpinBox_sampleSetHPosition.value(),
                    self._shell.units,
                )
            except ValueError:
                self._shell.sig_message.emit(
                    "Move rejected — horizontal would exceed travel limits. Move the stage closer to the travel range and retry."  # noqa: E501
                )
                self._shell.sig_beep.emit()
            else:
                self._shell.updateUi_message_printer("Sample moving to horizontal position")
            self._shell.updateUi_position_horizontal()
        else:
            self._shell.updateUi_message_printer("Out of boundaries")
            self._shell.sig_beep.emit()

    def updateUi_move_to_vertical_position(self) -> None:
        """Moves the sample to a specified vertical position"""
        if (
            self._shell.ui.doubleSpinBox_sampleSetVPosition.value()
            >= self.motors.vertical.get_limit_low(self._shell.units)
        ) and (
            self._shell.ui.doubleSpinBox_sampleSetVPosition.value()
            <= self.motors.vertical.get_limit_high(self._shell.units)
        ):
            try:
                self.motors.vertical.move_absolute_position(
                    self._shell.ui.doubleSpinBox_sampleSetVPosition.value(),
                    self._shell.units,
                )
            except ValueError:
                self._shell.sig_message.emit(
                    "Move rejected — vertical would exceed travel limits. Move the stage closer to the travel range and retry."  # noqa: E501
                )
                self._shell.sig_beep.emit()
            else:
                self._shell.updateUi_message_printer("Sample moving to vertical position")
            self._shell.updateUi_position_vertical()
        else:
            self._shell.updateUi_message_printer("Out of boundaries")
            self._shell.sig_beep.emit()

    def updateUi_move_sample_to_origin(self) -> None:
        """Moves vertical and horizontal sample motors to origin position"""
        if (
            self.motors.horizontal.get_origin(self._shell.units)
            <= self.motors.horizontal.get_limit_high(self._shell.units)
        ) and (
            self.motors.horizontal.get_origin(self._shell.units)
            >= self.motors.horizontal.get_limit_low(self._shell.units)
        ):
            # Moving sample to horizontal origin
            try:
                self.motors.horizontal.move_absolute_position(
                    self.motors.horizontal.get_origin(self._shell.units),
                    self._shell.units,
                )
            except ValueError:
                self._shell.sig_message.emit(
                    "Move rejected — horizontal would exceed travel limits. Move the stage closer to the travel range and retry."  # noqa: E501
                )
                self._shell.sig_beep.emit()
            else:
                self._shell.updateUi_message_printer("Moving to horizontal origin")
            self._shell.updateUi_position_horizontal()
        else:
            self._shell.sig_beep.emit()
            self._shell.updateUi_message_printer("Horizontal origin out of boundaries")

        if (
            self.motors.vertical.get_origin(self._shell.units)
            <= self.motors.vertical.get_limit_high(self._shell.units)
        ) and (
            self.motors.vertical.get_origin(self._shell.units)
            >= self.motors.vertical.get_limit_low(self._shell.units)
        ):
            # Moving sample to vertical origin
            try:
                self.motors.vertical.move_absolute_position(
                    self.motors.vertical.get_origin(self._shell.units),
                    self._shell.units,
                )
            except ValueError:
                self._shell.sig_message.emit(
                    "Move rejected — vertical would exceed travel limits. Move the stage closer to the travel range and retry."  # noqa: E501
                )
                self._shell.sig_beep.emit()
            else:
                self._shell.updateUi_message_printer("Moving to vertical origin")
            self._shell.updateUi_position_vertical()
        else:
            self._shell.sig_beep.emit()
            self._shell.updateUi_message_printer("Vertical origin out of boundaries")

    def updateUi_move_camera_to_position(self) -> None:
        """Moves the sample to a specified vertical position"""
        if (
            self._shell.ui.doubleSpinBox_cameraSetPosition.value()
            >= self.motors.camera.get_limit_low(self._shell.units)
        ) and (
            self._shell.ui.doubleSpinBox_cameraSetPosition.value()
            <= self.motors.camera.get_limit_high(self._shell.units)
        ):
            try:
                self.motors.camera.move_absolute_position(
                    self._shell.ui.doubleSpinBox_cameraSetPosition.value(),
                    self._shell.units,
                )
            except ValueError:
                self._shell.sig_message.emit(
                    "Move rejected — camera would exceed travel limits. Move the stage closer to the travel range and retry."  # noqa: E501
                )
                self._shell.sig_beep.emit()
            else:
                self._shell.updateUi_message_printer("Camera moving to position")
            self._shell.updateUi_position_camera()
        else:
            self._shell.updateUi_message_printer("Out of boundaries")
            self._shell.sig_beep.emit()

    def updateUi_move_camera_to_focus(self) -> None:
        """Moves camera to focus position"""
        if self._shell.focus_selected:
            if self.motors.camera.get_origin(
                self._shell.units
            ) > self.motors.camera.get_limit_high(self._shell.units):
                # self.motors.camera.move_absolute_position(self.motors.camera.get_limit_high(self._shell.units), self._shell.units)  # noqa: E501
                # rather only report out of boundaries
                self._shell.updateUi_message_printer("Focus out of boundaries")
                self._shell.sig_beep.emit()
                self._shell.updateUi_position_camera()
            elif self.motors.camera.get_origin(
                self._shell.units
            ) < self.motors.camera.get_limit_low(self._shell.units):
                # self.motors.camera.move_absolute_position(self.motors.camera.get_limit_low(self._shell.units), self._shell.units)  # noqa: E501
                # rather only report out of boundaries
                self._shell.updateUi_message_printer("Focus out of boundaries")
                self._shell.sig_beep.emit()
                self._shell.updateUi_position_camera()
            else:
                try:
                    self.motors.camera.move_absolute_position(
                        self.motors.camera.get_origin(self._shell.units),
                        self._shell.units,
                    )
                except ValueError:
                    self._shell.sig_message.emit(
                        "Move rejected — camera would exceed travel limits. Move the stage closer to the travel range and retry."  # noqa: E501
                    )
                    self._shell.sig_beep.emit()
                else:
                    self._shell.updateUi_message_printer("Moving to focus")
                self._shell.updateUi_position_camera()
        else:
            try:
                self.motors.camera.move_absolute_position(
                    self.motors.camera.get_origin(self._shell.units),
                    self._shell.units,
                )
            except ValueError:
                self._shell.sig_message.emit(
                    "Move rejected — camera would exceed travel limits. Move the stage closer to the travel range and retry."  # noqa: E501
                )
                self._shell.sig_beep.emit()
            else:
                self._shell.updateUi_message_printer(
                    "Focus not yet set. Moving camera to default focus"
                )
            self._shell.updateUi_position_camera()

    # ------------------------------------------------------------------ #
    # Sample / camera relative-move slots (step buttons).
    # ------------------------------------------------------------------ #

    def updateUi_move_sample_backward(self) -> None:
        """Sample motor backward horizontal motion"""
        if (
            self.motors.horizontal.get_position(self._shell.units)
            - self._shell.ui.doubleSpinBox_sampleHStepSize.value()
            >= self.motors.horizontal.get_limit_low(self._shell.units)
        ):
            try:
                self.motors.horizontal.move_relative_position(
                    -self._shell.ui.doubleSpinBox_sampleHStepSize.value(),
                    self._shell.units,
                )
            except ValueError:
                self._shell.sig_message.emit(
                    "Move rejected — horizontal would exceed travel limits. Move the stage closer to the travel range and retry."  # noqa: E501
                )
                self._shell.sig_beep.emit()
            else:
                self._shell.updateUi_message_printer("Sample moving backward")
            self._shell.updateUi_position_horizontal()
        else:
            # self.motors.horizontal.move_absolute_position(self.motors.horizontal.get_limit_low(self._shell.units), self._shell.units)  # noqa: E501
            # rather only report out of boundaries
            self._shell.updateUi_message_printer("Out of boundaries")
            self._shell.sig_beep.emit()
            self._shell.updateUi_position_horizontal()

    def updateUi_move_sample_forward(self) -> None:
        """Sample motor forward horizontal motion"""
        if (
            self.motors.horizontal.get_position(self._shell.units)
            + self._shell.ui.doubleSpinBox_sampleHStepSize.value()
            <= self.motors.horizontal.get_limit_high(self._shell.units)
        ):
            try:
                self.motors.horizontal.move_relative_position(
                    self._shell.ui.doubleSpinBox_sampleHStepSize.value(),
                    self._shell.units,
                )
            except ValueError:
                self._shell.sig_message.emit(
                    "Move rejected — horizontal would exceed travel limits. Move the stage closer to the travel range and retry."  # noqa: E501
                )
                self._shell.sig_beep.emit()
            else:
                self._shell.updateUi_message_printer("Sample moving forward")
            self._shell.updateUi_position_horizontal()
        else:
            # self.motors.horizontal.move_absolute_position(self.motors.horizontal.get_limit_high(self._shell.units), self._shell.units)  # noqa: E501
            # rather only report out of boundaries
            self._shell.updateUi_message_printer("Out of boundaries")
            self._shell.sig_beep.emit()
            self._shell.updateUi_position_horizontal()

    def updateUi_move_sample_up(self) -> None:
        """Sample motor upward vertical motion"""
        if (
            self.motors.vertical.get_position(self._shell.units)
            - self._shell.ui.doubleSpinBox_sampleVStepSize.value()
            >= self.motors.vertical.get_limit_low(self._shell.units)
        ):
            try:
                self.motors.vertical.move_relative_position(
                    -self._shell.ui.doubleSpinBox_sampleVStepSize.value(),
                    self._shell.units,
                )
            except ValueError:
                self._shell.sig_message.emit(
                    "Move rejected — vertical would exceed travel limits. Move the stage closer to the travel range and retry."  # noqa: E501
                )
                self._shell.sig_beep.emit()
            else:
                self._shell.updateUi_message_printer("Sample stepping up")
            self._shell.updateUi_position_vertical()
        else:
            # self.motors.vertical.move_absolute_position(self.motors.vertical.get_limit_low(self._shell.units), self._shell.units)  # noqa: E501
            # rather only report out of boundaries
            self._shell.updateUi_message_printer("Out of boundaries")
            self._shell.sig_beep.emit()
            self._shell.updateUi_position_vertical()

    def updateUi_move_sample_down(self) -> None:
        """Sample motor downward vertical motion"""
        if (
            self.motors.vertical.get_position(self._shell.units)
            + self._shell.ui.doubleSpinBox_sampleVStepSize.value()
            <= self.motors.vertical.get_limit_high(self._shell.units)
        ):
            try:
                self.motors.vertical.move_relative_position(
                    self._shell.ui.doubleSpinBox_sampleVStepSize.value(),
                    self._shell.units,
                )
            except ValueError:
                self._shell.sig_message.emit(
                    "Move rejected — vertical would exceed travel limits. Move the stage closer to the travel range and retry."  # noqa: E501
                )
                self._shell.sig_beep.emit()
            else:
                self._shell.updateUi_message_printer("Sample stepping down")
            self._shell.updateUi_position_vertical()
        else:
            # self.motors.vertical.move_absolute_position(self.motors.vertical.get_limit_high(self._shell.units), self._shell.units)  # noqa: E501
            # rather only report out of boundaries
            self._shell.updateUi_message_printer("Out of boundaries")
            self._shell.sig_beep.emit()
            self._shell.updateUi_position_vertical()

    def updateUi_move_camera_backward(self) -> None:
        """Camera motor backward horizontal motion"""
        if (
            self.motors.camera.get_position(self._shell.units)
            - self._shell.ui.doubleSpinBox_cameraStepSize.value()
            >= self.motors.camera.get_limit_low(self._shell.units)
        ):
            try:
                self.motors.camera.move_relative_position(
                    -self._shell.ui.doubleSpinBox_cameraStepSize.value(),
                    self._shell.units,
                )
            except ValueError:
                self._shell.sig_message.emit(
                    "Move rejected — camera would exceed travel limits. Move the stage closer to the travel range and retry."  # noqa: E501
                )
                self._shell.sig_beep.emit()
            else:
                self._shell.updateUi_message_printer("Camera stepping backward")
            self._shell.updateUi_position_camera()
        else:
            # self.motors.camera.move_absolute_position(self.motors.camera.get_limit_low(self._shell.units), self._shell.units)  # noqa: E501
            # In case of a communication glitch with motor, this was bringing the stage back to min position  # noqa: E501
            # rather only report out of boundaries
            self._shell.updateUi_message_printer("Out of boundaries")
            self._shell.sig_beep.emit()
            self._shell.updateUi_position_camera()

    def updateUi_move_camera_forward(self) -> None:
        """Camera motor forward horizontal motion"""
        if (
            self.motors.camera.get_position(self._shell.units)
            + self._shell.ui.doubleSpinBox_cameraStepSize.value()
            <= self.motors.camera.get_limit_high(self._shell.units)
        ):
            try:
                self.motors.camera.move_relative_position(
                    self._shell.ui.doubleSpinBox_cameraStepSize.value(),
                    self._shell.units,
                )
            except ValueError:
                self._shell.sig_message.emit(
                    "Move rejected — camera would exceed travel limits. Move the stage closer to the travel range and retry."  # noqa: E501
                )
                self._shell.sig_beep.emit()
            else:
                self._shell.updateUi_message_printer("Camera stepping forward")
            self._shell.updateUi_position_camera()
        else:
            # self.motors.camera.move_absolute_position(self.motors.camera.get_limit_high(self._shell.units), self._shell.units)  # noqa: E501
            # In case of a communication glitch with motor, this was bringing the stage back to max position  # noqa: E501
            # rather only report out of boundaries
            self._shell.updateUi_message_printer("Out of boundaries")
            self._shell.sig_beep.emit()
            self._shell.updateUi_position_camera()

    # ------------------------------------------------------------------ #
    # Boundary / origin / focus set slots (calibration-tab buttons).
    # ------------------------------------------------------------------ #

    def updateUi_reset_boundaries(self) -> None:
        """Reset variables for setting sample's horizontal motion range"""
        self._shell.ui.pushButton_calHorizontalStartRangeSelection.setEnabled(False)
        self._shell.ui.pushButton_calHorizontalSetForwardLimit.setEnabled(True)
        self._shell.ui.pushButton_calHorizontalSetBackwardLimit.setEnabled(True)
        self._shell.ui.label_calibrateRange.setText("Move Horizontal Position")
        # Default boundaries
        self.motors.horizontal.set_limit_low(0, self._shell.units)
        self.motors.horizontal.set_limit_high(0, self._shell.units)
        self._shell.updateUi_units()

    def updateUi_set_horizontal_backward_boundary(self) -> None:
        """Set lower limit of sample's horizontal motion"""
        self.motors.horizontal.set_limit_low(
            self.motors.horizontal.get_position(self._shell.units), self._shell.units
        )
        self._shell.updateUi_units()
        self._shell.horizontal_backward_boundary_selected = True
        self._shell.ui.pushButton_calHorizontalSetBackwardLimit.setEnabled(False)
        if self._shell.horizontal_forward_boundary_selected:
            self._shell.ui.pushButton_calHorizontalStartRangeSelection.setEnabled(True)
            self._shell.ui.label_calibrateRange.setText("Press Calibrate Range To Start")

    def updateUi_set_horizontal_forward_boundary(self) -> None:
        """Set upper limit of sample's horizontal motion"""
        self.motors.horizontal.set_limit_high(
            self.motors.horizontal.get_position(self._shell.units), self._shell.units
        )
        self._shell.updateUi_units()
        self._shell.horizontal_forward_boundary_selected = True
        self._shell.ui.pushButton_calHorizontalSetForwardLimit.setEnabled(False)
        if self._shell.horizontal_backward_boundary_selected:
            self._shell.ui.pushButton_calHorizontalStartRangeSelection.setEnabled(True)
            self._shell.ui.label_calibrateRange.setText("Press Calibrate Range To Start")

    def updateUi_set_sample_origin(self) -> None:
        """Modifies the sample origin position"""
        self.motors.horizontal.set_origin(
            self.motors.horizontal.get_position(self._shell.units), self._shell.units
        )
        self.motors.vertical.set_origin(
            self.motors.vertical.get_position(self._shell.units), self._shell.units
        )
        origin_text = f"Sample origin set at ({self.motors.horizontal.get_origin(self._shell.units)}, {self.motors.vertical.get_origin(self._shell.units)}) {self._shell.units}"  # noqa: E501
        self._shell.updateUi_message_printer(origin_text)

    def updateUi_set_camera_focus(self) -> None:
        """Modifies manually the camera focus position"""
        self._shell.focus_selected = True
        self.motors.camera.set_origin(
            self.motors.camera.get_position(self._shell.units), self._shell.units
        )
        focus_text = f"Camera focus manually set at {self.motors.camera.get_origin(self._shell.units)} {self._shell.units}"  # noqa: E501
        self._shell.updateUi_message_printer(focus_text)

    # ------------------------------------------------------------------ #
    # Focus-calculcation + interpolation-display methods (calibration-tab
    # compute/show buttons). Cohesive with the move methods — the camera
    # focus relation is motor-position-driven. The calibration *workers*
    # that used to populate this data were deleted (D-01); these three
    # display/compute methods remain live and move here for cohesion.
    # ------------------------------------------------------------------ #

    def calculate_camera_focus(self) -> None:
        """Interpolates the camera focus position"""
        # Current sample position
        current_position = self.motors.horizontal.get_position(self._shell.units)
        # Compute corresponding optimal focus position
        focus_regression = (
            self._shell.slope_camera * current_position + self._shell.intercept_camera
        )
        self.motors.camera.set_origin(focus_regression, self._shell.units)
        logger.debug("focus_regression: %s", focus_regression)
        self._shell.focus_selected = True
        self._shell.updateUi_message_printer("Focus automatically set")

    def show_camera_interpolation(self) -> None:
        """Shows the camera focus interpolation"""
        x = self._shell.camera_focus_relation[:, 0]
        y = self._shell.camera_focus_relation[:, 1]

        # Calculating linear regression
        xnew = np.linspace(
            self._shell.camera_focus_relation[0, 0],
            self._shell.camera_focus_relation[-1, 0],
            1000,
        )  ##1000 points
        self._shell.slope_camera, self._shell.intercept_camera, r_value, p_value, std_err = (
            stats.linregress(x, y)
        )
        logger.debug("r_value: %s", r_value)
        logger.debug("p_value: %s", p_value)
        logger.debug("std_err: %s", std_err)
        yreg = self._shell.slope_camera * xnew + self._shell.intercept_camera

        # Setting colormap
        xstart = self.motors.horizontal.get_limit_low(self._shell.units)
        xend = self.motors.horizontal.get_limit_high(self._shell.units)
        ystart = self._shell.focus_forward_boundary
        yend = self._shell.focus_backward_boundary
        transp = copy.deepcopy(self._shell.donnees)
        for q in range(int(self._shell.number_of_calibration_planes)):
            transp[q, :] = np.flip(transp[q, :])
        transp = np.transpose(transp)

        # Showing interpolation graph
        plt.figure(1)
        plt.title("Camera Focus Regression")
        plt.xlabel(f"Sample Horizontal Position ({self._shell.units})")
        plt.ylabel(f"Camera Position ({self._shell.units})")
        plt.imshow(transp, cmap="gray", extent=[xstart, xend, ystart, yend])  # Colormap
        plt.plot(x, y, "o")  # Raw data
        plt.plot(xnew, yreg)  # Linear regression
        plt.show(
            block=False
        )  # Prevents the plot from blocking the execution of the code...

        # debugging
        n = int(self._shell.number_of_camera_positions)
        x = np.arange(n)
        for g in range(int(self._shell.number_of_calibration_planes)):
            plt.figure(g + 2)
            plt.plot(self._shell.donnees[g, :])
            plt.plot(x, gaussian(x, *self._shell.popt[g]), "ro:", label="fit")
            plt.show(block=False)

    def show_etl_interpolation(self) -> None:
        """Shows the etl focus interpolation"""
        xl = self._shell.etl_l_relation[:, 0]
        yl = self._shell.etl_l_relation[:, 1]
        # Left linear regression
        xlnew = np.linspace(
            self._shell.etl_l_relation[0, 0], self._shell.etl_l_relation[-1, 0], 1000
        )  # 1000 points
        lslope, lintercept, r_value, p_value, std_err = stats.linregress(xl, yl)
        logger.debug("r_value: %s", r_value)
        logger.debug("p_value: %s", p_value)
        logger.debug("std_err: %s", std_err)
        ylnew = lslope * xlnew + lintercept

        xr = self._shell.etl_r_relation[:, 0]
        yr = self._shell.etl_r_relation[:, 1]
        # Right linear regression
        xrnew = np.linspace(
            self._shell.etl_r_relation[0, 0], self._shell.etl_r_relation[-1, 0], 1000
        )  # 1000 points
        rslope, rintercept, r_value, p_value, std_err = stats.linregress(xr, yr)
        logger.debug("r_value: %s", r_value)
        logger.debug("p_value: %s", p_value)
        logger.debug("std_err: %s", std_err)
        yrnew = rslope * xrnew + rintercept

        # Showing interpolation graph
        plt.figure(1)
        plt.title("ETL Focus Regression")
        plt.xlabel("ETL Voltage (V)")
        plt.ylabel("Focal Point Horizontal Position (column)")
        plt.plot(xl, yl, "o", label="Left ETL")  # Raw left data
        plt.plot(xlnew, ylnew)  # Left regression
        plt.plot(xr, yr, "o", label="Right ETL")  # Raw right data
        plt.plot(xrnew, yrnew)  # Right regression
        plt.legend()
        plt.show(
            block=False
        )  # Prevents the plot from blocking the execution of the code...

        # debugging
        for g in range(int(self._shell.number_of_etls_points)):
            plt.figure(g + 2)
            plt.plot(self._shell.xdata[g], self._shell.ydata[g], ".")
            plt.plot(self._shell.xdata[g], func(self._shell.xdata[g], *self._shell.popt[g]), "r-")
            plt.show(block=False)
