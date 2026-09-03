"""MotorController — sample/vertical/camera motor-move slots + focus
calibration display methods. Plain-Python collaborator (not a QObject);
emits through the shell reference. MotorController is a motion collaborator,
NOT a safety kill-path owner — E-stop stays in the shell.
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
    from lightsheet.gui.shell.controller import Controller_MainWindow

logger = logging.getLogger(__name__)


class MotorController:
    """Motor-move + focus/interpolation-display collaborator."""

    def __init__(self, bundle: DeviceBundle, shell: Controller_MainWindow) -> None:
        self._bundle = bundle
        self._shell = shell
        self.motors = bundle.motors

    # ------------------------------------------------------------------ #
    # Sample / vertical / camera absolute-move slots.
    # ------------------------------------------------------------------ #

    def updateUi_move_to_horizontal_position(self) -> None:
        """Moves the sample to a specified horizontal position"""
        if (
            self._shell.motor_panel.ui.doubleSpinBox_sampleSetHPosition.value()
            >= self.motors.horizontal.get_limit_low("mm")
        ) and (
            self._shell.motor_panel.ui.doubleSpinBox_sampleSetHPosition.value()
            <= self.motors.horizontal.get_limit_high("mm")
        ):
            try:
                self.motors.horizontal.move_absolute_position(
                    self._shell.motor_panel.ui.doubleSpinBox_sampleSetHPosition.value(),
                    "mm",
                )
            except ValueError:
                self._shell.sig_message.emit(
                    "Move rejected — horizontal would exceed travel limits. Move the stage closer to the travel range and retry."  # noqa: E501
                )
                self._shell.sig_beep.emit()
            else:
                self._shell.updateUi_message_printer(
                    "Sample moving to horizontal position"
                )
            self._shell.motor_panel.updateUi_position_horizontal()
        else:
            self._shell.updateUi_message_printer("Out of boundaries")
            self._shell.sig_beep.emit()

    def updateUi_move_to_vertical_position(self) -> None:
        """Moves the sample to a specified vertical position"""
        if (
            self._shell.motor_panel.ui.doubleSpinBox_sampleSetVPosition.value()
            >= self.motors.vertical.get_limit_low("mm")
        ) and (
            self._shell.motor_panel.ui.doubleSpinBox_sampleSetVPosition.value()
            <= self.motors.vertical.get_limit_high("mm")
        ):
            try:
                self.motors.vertical.move_absolute_position(
                    self._shell.motor_panel.ui.doubleSpinBox_sampleSetVPosition.value(),
                    "mm",
                )
            except ValueError:
                self._shell.sig_message.emit(
                    "Move rejected — vertical would exceed travel limits. Move the stage closer to the travel range and retry."  # noqa: E501
                )
                self._shell.sig_beep.emit()
            else:
                self._shell.updateUi_message_printer(
                    "Sample moving to vertical position"
                )
            self._shell.motor_panel.updateUi_position_vertical()
        else:
            self._shell.updateUi_message_printer("Out of boundaries")
            self._shell.sig_beep.emit()

    def updateUi_move_sample_to_origin(self) -> None:
        """Moves vertical and horizontal sample motors to origin position"""
        if (
            self.motors.horizontal.get_origin("mm")
            <= self.motors.horizontal.get_limit_high("mm")
        ) and (
            self.motors.horizontal.get_origin("mm")
            >= self.motors.horizontal.get_limit_low("mm")
        ):
            try:
                self.motors.horizontal.move_absolute_position(
                    self.motors.horizontal.get_origin("mm"),
                    "mm",
                )
            except ValueError:
                self._shell.sig_message.emit(
                    "Move rejected — horizontal would exceed travel limits. Move the stage closer to the travel range and retry."  # noqa: E501
                )
                self._shell.sig_beep.emit()
            else:
                self._shell.updateUi_message_printer("Moving to horizontal origin")
            self._shell.motor_panel.updateUi_position_horizontal()
        else:
            self._shell.sig_beep.emit()
            self._shell.updateUi_message_printer("Horizontal origin out of boundaries")

        if (
            self.motors.vertical.get_origin("mm")
            <= self.motors.vertical.get_limit_high("mm")
        ) and (
            self.motors.vertical.get_origin("mm")
            >= self.motors.vertical.get_limit_low("mm")
        ):
            try:
                self.motors.vertical.move_absolute_position(
                    self.motors.vertical.get_origin("mm"),
                    "mm",
                )
            except ValueError:
                self._shell.sig_message.emit(
                    "Move rejected — vertical would exceed travel limits. Move the stage closer to the travel range and retry."  # noqa: E501
                )
                self._shell.sig_beep.emit()
            else:
                self._shell.updateUi_message_printer("Moving to vertical origin")
            self._shell.motor_panel.updateUi_position_vertical()
        else:
            self._shell.sig_beep.emit()
            self._shell.updateUi_message_printer("Vertical origin out of boundaries")

    def updateUi_move_camera_to_position(self) -> None:
        """Moves the sample to a specified vertical position"""
        if (
            self._shell.motor_panel.ui.doubleSpinBox_cameraSetPosition.value()
            >= self.motors.camera.get_limit_low("mm")
        ) and (
            self._shell.motor_panel.ui.doubleSpinBox_cameraSetPosition.value()
            <= self.motors.camera.get_limit_high("mm")
        ):
            try:
                self.motors.camera.move_absolute_position(
                    self._shell.motor_panel.ui.doubleSpinBox_cameraSetPosition.value(),
                    "mm",
                )
            except ValueError:
                self._shell.sig_message.emit(
                    "Move rejected — camera would exceed travel limits. Move the stage closer to the travel range and retry."  # noqa: E501
                )
                self._shell.sig_beep.emit()
            else:
                self._shell.updateUi_message_printer("Camera moving to position")
            self._shell.motor_panel.updateUi_position_camera()
        else:
            self._shell.updateUi_message_printer("Out of boundaries")
            self._shell.sig_beep.emit()

    def updateUi_move_camera_to_focus(self) -> None:
        """Moves camera to focus position"""
        if self._shell.focus_selected:
            cam_origin = self.motors.camera.get_origin("mm")
            if cam_origin > self.motors.camera.get_limit_high(
                "mm"
            ) or cam_origin < self.motors.camera.get_limit_low("mm"):
                self._shell.updateUi_message_printer("Focus out of boundaries")
                self._shell.sig_beep.emit()
                self._shell.motor_panel.updateUi_position_camera()
            else:
                try:
                    self.motors.camera.move_absolute_position(
                        self.motors.camera.get_origin("mm"),
                        "mm",
                    )
                except ValueError:
                    self._shell.sig_message.emit(
                        "Move rejected — camera would exceed travel limits. Move the stage closer to the travel range and retry."  # noqa: E501
                    )
                    self._shell.sig_beep.emit()
                else:
                    self._shell.updateUi_message_printer("Moving to focus")
                self._shell.motor_panel.updateUi_position_camera()
        else:
            try:
                self.motors.camera.move_absolute_position(
                    self.motors.camera.get_origin("mm"),
                    "mm",
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
            self._shell.motor_panel.updateUi_position_camera()

    # ------------------------------------------------------------------ #
    # Sample / camera relative-move slots (step buttons).
    # ------------------------------------------------------------------ #

    def updateUi_move_sample_backward(self) -> None:
        """Sample motor backward horizontal motion"""
        if (
            self.motors.horizontal.get_position("mm")
            - self._shell.motor_panel.ui.doubleSpinBox_sampleHStepSize.value()
            >= self.motors.horizontal.get_limit_low("mm")
        ):
            try:
                self.motors.horizontal.move_relative_position(
                    -self._shell.motor_panel.ui.doubleSpinBox_sampleHStepSize.value(),
                    "mm",
                )
            except ValueError:
                self._shell.sig_message.emit(
                    "Move rejected — horizontal would exceed travel limits. Move the stage closer to the travel range and retry."  # noqa: E501
                )
                self._shell.sig_beep.emit()
            else:
                self._shell.updateUi_message_printer("Sample moving backward")
            self._shell.motor_panel.updateUi_position_horizontal()
        else:
            self._shell.updateUi_message_printer("Out of boundaries")
            self._shell.sig_beep.emit()
            self._shell.motor_panel.updateUi_position_horizontal()

    def updateUi_move_sample_forward(self) -> None:
        """Sample motor forward horizontal motion"""
        if (
            self.motors.horizontal.get_position("mm")
            + self._shell.motor_panel.ui.doubleSpinBox_sampleHStepSize.value()
            <= self.motors.horizontal.get_limit_high("mm")
        ):
            try:
                self.motors.horizontal.move_relative_position(
                    self._shell.motor_panel.ui.doubleSpinBox_sampleHStepSize.value(),
                    "mm",
                )
            except ValueError:
                self._shell.sig_message.emit(
                    "Move rejected — horizontal would exceed travel limits. Move the stage closer to the travel range and retry."  # noqa: E501
                )
                self._shell.sig_beep.emit()
            else:
                self._shell.updateUi_message_printer("Sample moving forward")
            self._shell.motor_panel.updateUi_position_horizontal()
        else:
            self._shell.updateUi_message_printer("Out of boundaries")
            self._shell.sig_beep.emit()
            self._shell.motor_panel.updateUi_position_horizontal()

    def updateUi_move_sample_up(self) -> None:
        """Sample motor upward vertical motion"""
        if (
            self.motors.vertical.get_position("mm")
            - self._shell.motor_panel.ui.doubleSpinBox_sampleVStepSize.value()
            >= self.motors.vertical.get_limit_low("mm")
        ):
            try:
                self.motors.vertical.move_relative_position(
                    -self._shell.motor_panel.ui.doubleSpinBox_sampleVStepSize.value(),
                    "mm",
                )
            except ValueError:
                self._shell.sig_message.emit(
                    "Move rejected — vertical would exceed travel limits. Move the stage closer to the travel range and retry."  # noqa: E501
                )
                self._shell.sig_beep.emit()
            else:
                self._shell.updateUi_message_printer("Sample stepping up")
            self._shell.motor_panel.updateUi_position_vertical()
        else:
            self._shell.updateUi_message_printer("Out of boundaries")
            self._shell.sig_beep.emit()
            self._shell.motor_panel.updateUi_position_vertical()

    def updateUi_move_sample_down(self) -> None:
        """Sample motor downward vertical motion"""
        if (
            self.motors.vertical.get_position("mm")
            + self._shell.motor_panel.ui.doubleSpinBox_sampleVStepSize.value()
            <= self.motors.vertical.get_limit_high("mm")
        ):
            try:
                self.motors.vertical.move_relative_position(
                    self._shell.motor_panel.ui.doubleSpinBox_sampleVStepSize.value(),
                    "mm",
                )
            except ValueError:
                self._shell.sig_message.emit(
                    "Move rejected — vertical would exceed travel limits. Move the stage closer to the travel range and retry."  # noqa: E501
                )
                self._shell.sig_beep.emit()
            else:
                self._shell.updateUi_message_printer("Sample stepping down")
            self._shell.motor_panel.updateUi_position_vertical()
        else:
            self._shell.updateUi_message_printer("Out of boundaries")
            self._shell.sig_beep.emit()
            self._shell.motor_panel.updateUi_position_vertical()

    def updateUi_move_camera_backward(self) -> None:
        """Camera motor backward horizontal motion"""
        if (
            self.motors.camera.get_position("mm")
            - self._shell.motor_panel.ui.doubleSpinBox_cameraStepSize.value()
            >= self.motors.camera.get_limit_low("mm")
        ):
            try:
                self.motors.camera.move_relative_position(
                    -self._shell.motor_panel.ui.doubleSpinBox_cameraStepSize.value(),
                    "mm",
                )
            except ValueError:
                self._shell.sig_message.emit(
                    "Move rejected — camera would exceed travel limits. Move the stage closer to the travel range and retry."  # noqa: E501
                )
                self._shell.sig_beep.emit()
            else:
                self._shell.updateUi_message_printer("Camera stepping backward")
            self._shell.motor_panel.updateUi_position_camera()
        else:
            self._shell.updateUi_message_printer("Out of boundaries")
            self._shell.sig_beep.emit()
            self._shell.motor_panel.updateUi_position_camera()

    def updateUi_move_camera_forward(self) -> None:
        """Camera motor forward horizontal motion"""
        if (
            self.motors.camera.get_position("mm")
            + self._shell.motor_panel.ui.doubleSpinBox_cameraStepSize.value()
            <= self.motors.camera.get_limit_high("mm")
        ):
            try:
                self.motors.camera.move_relative_position(
                    self._shell.motor_panel.ui.doubleSpinBox_cameraStepSize.value(),
                    "mm",
                )
            except ValueError:
                self._shell.sig_message.emit(
                    "Move rejected — camera would exceed travel limits. Move the stage closer to the travel range and retry."  # noqa: E501
                )
                self._shell.sig_beep.emit()
            else:
                self._shell.updateUi_message_printer("Camera stepping forward")
            self._shell.motor_panel.updateUi_position_camera()
        else:
            self._shell.updateUi_message_printer("Out of boundaries")
            self._shell.sig_beep.emit()
            self._shell.motor_panel.updateUi_position_camera()

    # ------------------------------------------------------------------ #
    # Boundary / origin / focus set slots (calibration-tab buttons).
    # ------------------------------------------------------------------ #

    def updateUi_reset_boundaries(self) -> None:
        """Reset variables for setting sample's horizontal motion range"""
        self._shell.calibration_panel.ui.pushButton_calHorizontalStartRangeSelection.setEnabled(
            False
        )
        self._shell.calibration_panel.ui.pushButton_calHorizontalSetForwardLimit.setEnabled(
            True
        )
        self._shell.calibration_panel.ui.pushButton_calHorizontalSetBackwardLimit.setEnabled(
            True
        )
        self._shell.calibration_panel.ui.label_calibrateRange.setText(
            "Move Horizontal Position"
        )
        self.motors.horizontal.set_limit_low(0, "mm")
        self.motors.horizontal.set_limit_high(0, "mm")
        self._shell.motor_panel.updateUi_position_indicators()

    def updateUi_set_horizontal_backward_boundary(self) -> None:
        """Set lower limit of sample's horizontal motion"""
        self.motors.horizontal.set_limit_low(
            self.motors.horizontal.get_position("mm"),
            "mm",
        )
        self._shell.motor_panel.updateUi_position_indicators()
        self._shell.horizontal_backward_boundary_selected = True
        self._shell.calibration_panel.ui.pushButton_calHorizontalSetBackwardLimit.setEnabled(
            False
        )
        if self._shell.horizontal_forward_boundary_selected:
            self._shell.calibration_panel.ui.pushButton_calHorizontalStartRangeSelection.setEnabled(
                True
            )
            self._shell.calibration_panel.ui.label_calibrateRange.setText(
                "Press Calibrate Range To Start"
            )

    def updateUi_set_horizontal_forward_boundary(self) -> None:
        """Set upper limit of sample's horizontal motion"""
        self.motors.horizontal.set_limit_high(
            self.motors.horizontal.get_position("mm"),
            "mm",
        )
        self._shell.motor_panel.updateUi_position_indicators()
        self._shell.horizontal_forward_boundary_selected = True
        self._shell.calibration_panel.ui.pushButton_calHorizontalSetForwardLimit.setEnabled(
            False
        )
        if self._shell.horizontal_backward_boundary_selected:
            self._shell.calibration_panel.ui.pushButton_calHorizontalStartRangeSelection.setEnabled(
                True
            )
            self._shell.calibration_panel.ui.label_calibrateRange.setText(
                "Press Calibrate Range To Start"
            )

    def updateUi_set_sample_origin(self) -> None:
        """Modifies the sample origin position"""
        self.motors.horizontal.set_origin(
            self.motors.horizontal.get_position("mm"),
            "mm",
        )
        self.motors.vertical.set_origin(
            self.motors.vertical.get_position("mm"),
            "mm",
        )
        origin_text = f"Sample origin set at ({self.motors.horizontal.get_origin('mm')}, {self.motors.vertical.get_origin('mm')}) {'mm'}"  # noqa: E501
        self._shell.updateUi_message_printer(origin_text)

    def updateUi_set_camera_focus(self) -> None:
        """Modifies manually the camera focus position"""
        self._shell.focus_selected = True
        self.motors.camera.set_origin(
            self.motors.camera.get_position("mm"),
            "mm",
        )
        focus_text = (
            f"Camera focus manually set at {self.motors.camera.get_origin('mm')} {'mm'}"
        )
        self._shell.updateUi_message_printer(focus_text)

    # ------------------------------------------------------------------ #
    # Focus-calculation + interpolation-display methods (calibration tab)
    # ------------------------------------------------------------------ #

    def calculate_camera_focus(self) -> None:
        """Interpolates the camera focus position"""
        current_position = self.motors.horizontal.get_position("mm")
        focus_regression = (
            self._shell.slope_camera * current_position + self._shell.intercept_camera
        )
        self.motors.camera.set_origin(focus_regression, "mm")
        logger.debug("focus_regression: %s", focus_regression)
        self._shell.focus_selected = True
        self._shell.updateUi_message_printer("Focus automatically set")

    def show_camera_interpolation(self) -> None:
        """Shows the camera focus interpolation"""
        x = self._shell.camera_focus_relation[:, 0]
        y = self._shell.camera_focus_relation[:, 1]

        xnew = np.linspace(
            self._shell.camera_focus_relation[0, 0],
            self._shell.camera_focus_relation[-1, 0],
            1000,
        )
        (
            self._shell.slope_camera,
            self._shell.intercept_camera,
            r_value,
            p_value,
            std_err,
        ) = (
            stats.linregress(x, y)
        )
        logger.debug("r_value: %s", r_value)
        logger.debug("p_value: %s", p_value)
        logger.debug("std_err: %s", std_err)
        yreg = self._shell.slope_camera * xnew + self._shell.intercept_camera

        xstart = self.motors.horizontal.get_limit_low("mm")
        xend = self.motors.horizontal.get_limit_high("mm")
        ystart = self._shell.focus_forward_boundary
        yend = self._shell.focus_backward_boundary
        transp = copy.deepcopy(self._shell.donnees)
        for q in range(int(self._shell.number_of_calibration_planes)):
            transp[q, :] = np.flip(transp[q, :])
        transp = np.transpose(transp)

        plt.figure(1)
        plt.title("Camera Focus Regression")
        plt.xlabel(f"Sample Horizontal Position ({'mm'})")
        plt.ylabel(f"Camera Position ({'mm'})")
        plt.imshow(transp, cmap="gray", extent=[xstart, xend, ystart, yend])  # ty: ignore[invalid-argument-type]
        plt.plot(x, y, "o")
        plt.plot(xnew, yreg)
        plt.show(block=False)

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
        xlnew = np.linspace(
            self._shell.etl_l_relation[0, 0],
            self._shell.etl_l_relation[-1, 0],
            1000,
        )
        lslope, lintercept, r_value, p_value, std_err = stats.linregress(xl, yl)
        logger.debug("r_value: %s", r_value)
        logger.debug("p_value: %s", p_value)
        logger.debug("std_err: %s", std_err)
        ylnew = lslope * xlnew + lintercept

        xr = self._shell.etl_r_relation[:, 0]
        yr = self._shell.etl_r_relation[:, 1]
        xrnew = np.linspace(
            self._shell.etl_r_relation[0, 0],
            self._shell.etl_r_relation[-1, 0],
            1000,
        )
        rslope, rintercept, r_value, p_value, std_err = stats.linregress(xr, yr)
        logger.debug("r_value: %s", r_value)
        logger.debug("p_value: %s", p_value)
        logger.debug("std_err: %s", std_err)
        yrnew = rslope * xrnew + rintercept

        plt.figure(1)
        plt.title("ETL Focus Regression")
        plt.xlabel("ETL Voltage (V)")
        plt.ylabel("Focal Point Horizontal Position (column)")
        plt.plot(xl, yl, "o", label="Left ETL")
        plt.plot(xlnew, ylnew)
        plt.plot(xr, yr, "o", label="Right ETL")
        plt.plot(xrnew, yrnew)
        plt.legend()
        plt.show(block=False)

        # debugging
        for g in range(int(self._shell.number_of_etls_points)):
            plt.figure(g + 2)
            plt.plot(self._shell.xdata[g], self._shell.ydata[g], ".")
            plt.plot(
                self._shell.xdata[g],
                func(self._shell.xdata[g], *self._shell.popt[g]),
                "r-",
            )
            plt.show(block=False)
