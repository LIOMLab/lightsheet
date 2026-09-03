"""AcquisitionCoordinator — GUI-thread galvo/ETL/camera-setting slots.

The shell delegates through ``self._acq``. Acquisition worker bodies live
in ``lightsheet/gui/workers.py``. The E-stop kill path stays in the shell;
this coordinator only polls ``estop_event`` cooperatively.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from lightsheet.gui.workers import _AcquireScanMixin
from lightsheet.hal.bundle import DeviceBundle

if TYPE_CHECKING:
    from lightsheet.gui.coordinators.hardware_manager import HardwareManager
    from lightsheet.gui.shell.controller import Controller_MainWindow

logger = logging.getLogger(__name__)


class AcquisitionCoordinator(_AcquireScanMixin):
    """Hosts the ~15 GUI-thread galvo/ETL/camera-setting slots that read
    ``self._shell.ui.*`` widgets and write ``self.siggen.*`` / ``self.camera.*``
    HAL attributes. These slots MUST run on the GUI thread.
    """

    def __init__(
        self,
        bundle: DeviceBundle,
        hw: HardwareManager,
        shell: Controller_MainWindow,
    ) -> None:
        self._bundle = bundle
        self._hw = hw
        self._shell = shell
        self.camera = bundle.camera
        self.siggen = bundle.siggen
        self.motors = bundle.motors

    # ------------------------------------------------------------------ #
    # Galvo / ETL / camera-setting GUI-driven update slots
    # ------------------------------------------------------------------ #

    def updateUi_galvo_left_amplitude(self) -> None:
        self.siggen.galvo_left_amplitude = (
            self._shell.scan_panel.ui.doubleSpinBox_galvoLeftAmplitude.value()
        )
        self._shell.scan_panel.ui.doubleSpinBox_galvoLeftOffset.setMinimum(
            -10 + self._shell.scan_panel.ui.doubleSpinBox_galvoLeftAmplitude.value()
        )
        self._shell.scan_panel.ui.doubleSpinBox_galvoLeftOffset.setMaximum(
            10 - self._shell.scan_panel.ui.doubleSpinBox_galvoLeftAmplitude.value()
        )
        if self._shell.scan_panel.ui.checkBox_galvoSync.isChecked():
            self._shell.scan_panel.ui.doubleSpinBox_galvoRightAmplitude.setValue(
                self._shell.scan_panel.ui.doubleSpinBox_galvoLeftAmplitude.value()
            )
            self._shell.scan_panel.ui.doubleSpinBox_galvoRightOffset.setValue(
                self._shell.scan_panel.ui.doubleSpinBox_galvoLeftOffset.value()
            )
            self._shell.scan_panel.ui.doubleSpinBox_galvoRightOffset.setMinimum(
                self._shell.scan_panel.ui.doubleSpinBox_galvoLeftOffset.minimum()
            )
            self._shell.scan_panel.ui.doubleSpinBox_galvoRightOffset.setMaximum(
                self._shell.scan_panel.ui.doubleSpinBox_galvoLeftOffset.maximum()
            )
            self.siggen.galvo_right_amplitude = (
                self._shell.scan_panel.ui.doubleSpinBox_galvoRightAmplitude.value()
            )
            self.siggen.galvo_right_offset = (
                self._shell.scan_panel.ui.doubleSpinBox_galvoRightOffset.value()
            )

    def updateUi_galvo_right_amplitude(self) -> None:
        self.siggen.galvo_right_amplitude = (
            self._shell.scan_panel.ui.doubleSpinBox_galvoRightAmplitude.value()
        )
        self._shell.scan_panel.ui.doubleSpinBox_galvoRightOffset.setMinimum(
            -10 + self._shell.scan_panel.ui.doubleSpinBox_galvoRightAmplitude.value()
        )
        self._shell.scan_panel.ui.doubleSpinBox_galvoRightOffset.setMaximum(
            10 - self._shell.scan_panel.ui.doubleSpinBox_galvoRightAmplitude.value()
        )
        if self._shell.scan_panel.ui.checkBox_galvoSync.isChecked():
            self._shell.scan_panel.ui.doubleSpinBox_galvoLeftAmplitude.setValue(
                self._shell.scan_panel.ui.doubleSpinBox_galvoRightAmplitude.value()
            )
            self._shell.scan_panel.ui.doubleSpinBox_galvoLeftOffset.setValue(
                self._shell.scan_panel.ui.doubleSpinBox_galvoRightOffset.value()
            )
            self._shell.scan_panel.ui.doubleSpinBox_galvoLeftOffset.setMinimum(
                self._shell.scan_panel.ui.doubleSpinBox_galvoRightOffset.minimum()
            )
            self._shell.scan_panel.ui.doubleSpinBox_galvoLeftOffset.setMaximum(
                self._shell.scan_panel.ui.doubleSpinBox_galvoRightOffset.maximum()
            )
            self.siggen.galvo_left_amplitude = (
                self._shell.scan_panel.ui.doubleSpinBox_galvoLeftAmplitude.value()
            )
            self.siggen.galvo_left_offset = (
                self._shell.scan_panel.ui.doubleSpinBox_galvoLeftOffset.value()
            )

    def updateUi_galvo_left_offset(self) -> None:
        self.siggen.galvo_left_offset = (
            self._shell.scan_panel.ui.doubleSpinBox_galvoLeftOffset.value()
        )
        if self._shell.scan_panel.ui.checkBox_galvoSync.isChecked():
            self._shell.scan_panel.ui.doubleSpinBox_galvoRightAmplitude.setValue(
                self._shell.scan_panel.ui.doubleSpinBox_galvoLeftAmplitude.value()
            )
            self._shell.scan_panel.ui.doubleSpinBox_galvoRightOffset.setValue(
                self._shell.scan_panel.ui.doubleSpinBox_galvoLeftOffset.value()
            )
            self._shell.scan_panel.ui.doubleSpinBox_galvoRightOffset.setMinimum(
                self._shell.scan_panel.ui.doubleSpinBox_galvoLeftOffset.minimum()
            )
            self._shell.scan_panel.ui.doubleSpinBox_galvoRightOffset.setMaximum(
                self._shell.scan_panel.ui.doubleSpinBox_galvoLeftOffset.maximum()
            )
            self.siggen.galvo_right_amplitude = (
                self._shell.scan_panel.ui.doubleSpinBox_galvoRightAmplitude.value()
            )
            self.siggen.galvo_right_offset = (
                self._shell.scan_panel.ui.doubleSpinBox_galvoRightOffset.value()
            )

    def updateUi_galvo_right_offset(self) -> None:
        self.siggen.galvo_right_offset = (
            self._shell.scan_panel.ui.doubleSpinBox_galvoRightOffset.value()
        )
        if self._shell.scan_panel.ui.checkBox_galvoSync.isChecked():
            self._shell.scan_panel.ui.doubleSpinBox_galvoLeftAmplitude.setValue(
                self._shell.scan_panel.ui.doubleSpinBox_galvoRightAmplitude.value()
            )
            self._shell.scan_panel.ui.doubleSpinBox_galvoLeftOffset.setValue(
                self._shell.scan_panel.ui.doubleSpinBox_galvoRightOffset.value()
            )
            self._shell.scan_panel.ui.doubleSpinBox_galvoLeftOffset.setMinimum(
                self._shell.scan_panel.ui.doubleSpinBox_galvoRightOffset.minimum()
            )
            self._shell.scan_panel.ui.doubleSpinBox_galvoLeftOffset.setMaximum(
                self._shell.scan_panel.ui.doubleSpinBox_galvoRightOffset.maximum()
            )
            self.siggen.galvo_left_amplitude = (
                self._shell.scan_panel.ui.doubleSpinBox_galvoLeftAmplitude.value()
            )
            self.siggen.galvo_left_offset = (
                self._shell.scan_panel.ui.doubleSpinBox_galvoLeftOffset.value()
            )

    def updateUi_galvo_sync(self) -> None:
        if self._shell.scan_panel.ui.checkBox_galvoSync.isChecked():
            self._shell.scan_panel.ui.doubleSpinBox_galvoRightAmplitude.setValue(
                self._shell.scan_panel.ui.doubleSpinBox_galvoLeftAmplitude.value()
            )
            self._shell.scan_panel.ui.doubleSpinBox_galvoRightOffset.setValue(
                self._shell.scan_panel.ui.doubleSpinBox_galvoLeftOffset.value()
            )
            self._shell.scan_panel.ui.doubleSpinBox_galvoRightOffset.setMinimum(
                self._shell.scan_panel.ui.doubleSpinBox_galvoLeftOffset.minimum()
            )
            self._shell.scan_panel.ui.doubleSpinBox_galvoRightOffset.setMaximum(
                self._shell.scan_panel.ui.doubleSpinBox_galvoLeftOffset.maximum()
            )
            self.siggen.galvo_right_amplitude = (
                self._shell.scan_panel.ui.doubleSpinBox_galvoRightAmplitude.value()
            )
            self.siggen.galvo_right_offset = (
                self._shell.scan_panel.ui.doubleSpinBox_galvoRightOffset.value()
            )

    def updateUi_galvo_activate(self) -> None:
        self.siggen.galvo_activated = (  # ty: ignore[unresolved-attribute]
            self._shell.scan_panel.ui.checkBox_galvoActivate.isChecked()
        )

    def updateUi_galvo_invert(self) -> None:
        self.siggen.galvo_inverted = (  # ty: ignore[unresolved-attribute]
            self._shell.scan_panel.ui.checkBox_galvoInvert.isChecked()
        )

    def updateUi_etl_left_amplitude(self) -> None:
        self.siggen.etl_left_amplitude = (
            self._shell.scan_panel.ui.doubleSpinBox_etlLeftAmplitude.value()
        )
        self._shell.scan_panel.ui.doubleSpinBox_etlLeftOffset.setMinimum(
            -5 + self._shell.scan_panel.ui.doubleSpinBox_etlLeftAmplitude.value()
        )
        self._shell.scan_panel.ui.doubleSpinBox_etlLeftOffset.setMaximum(
            5 - self._shell.scan_panel.ui.doubleSpinBox_etlLeftAmplitude.value()
        )
        if self._shell.scan_panel.ui.checkBox_etlSync.isChecked():
            self._shell.scan_panel.ui.doubleSpinBox_etlRightAmplitude.setValue(
                self._shell.scan_panel.ui.doubleSpinBox_etlLeftAmplitude.value()
            )
            self._shell.scan_panel.ui.doubleSpinBox_etlRightOffset.setValue(
                self._shell.scan_panel.ui.doubleSpinBox_etlLeftOffset.value()
            )
            self._shell.scan_panel.ui.doubleSpinBox_etlRightOffset.setMinimum(
                self._shell.scan_panel.ui.doubleSpinBox_etlLeftOffset.minimum()
            )
            self._shell.scan_panel.ui.doubleSpinBox_etlRightOffset.setMaximum(
                self._shell.scan_panel.ui.doubleSpinBox_etlLeftOffset.maximum()
            )
            self.siggen.etl_right_amplitude = (
                self._shell.scan_panel.ui.doubleSpinBox_etlRightAmplitude.value()
            )
            self.siggen.etl_right_offset = (
                self._shell.scan_panel.ui.doubleSpinBox_etlRightOffset.value()
            )

    def updateUi_etl_right_amplitude(self) -> None:
        self.siggen.etl_right_amplitude = (
            self._shell.scan_panel.ui.doubleSpinBox_etlRightAmplitude.value()
        )
        self._shell.scan_panel.ui.doubleSpinBox_etlRightOffset.setMinimum(
            -5 + self._shell.scan_panel.ui.doubleSpinBox_etlRightAmplitude.value()
        )
        self._shell.scan_panel.ui.doubleSpinBox_etlRightOffset.setMaximum(
            5 - self._shell.scan_panel.ui.doubleSpinBox_etlRightAmplitude.value()
        )
        if self._shell.scan_panel.ui.checkBox_etlSync.isChecked():
            self._shell.scan_panel.ui.doubleSpinBox_etlLeftAmplitude.setValue(
                self._shell.scan_panel.ui.doubleSpinBox_etlRightAmplitude.value()
            )
            self._shell.scan_panel.ui.doubleSpinBox_etlLeftOffset.setValue(
                self._shell.scan_panel.ui.doubleSpinBox_etlRightOffset.value()
            )
            self._shell.scan_panel.ui.doubleSpinBox_etlLeftOffset.setMinimum(
                self._shell.scan_panel.ui.doubleSpinBox_etlRightOffset.minimum()
            )
            self._shell.scan_panel.ui.doubleSpinBox_etlLeftOffset.setMaximum(
                self._shell.scan_panel.ui.doubleSpinBox_etlRightOffset.maximum()
            )
            self.siggen.etl_left_amplitude = (
                self._shell.scan_panel.ui.doubleSpinBox_etlLeftAmplitude.value()
            )
            self.siggen.etl_left_offset = (
                self._shell.scan_panel.ui.doubleSpinBox_etlLeftOffset.value()
            )

    def updateUi_etl_left_offset(self) -> None:
        self.siggen.etl_left_offset = (
            self._shell.scan_panel.ui.doubleSpinBox_etlLeftOffset.value()
        )
        if self._shell.scan_panel.ui.checkBox_etlSync.isChecked():
            self._shell.scan_panel.ui.doubleSpinBox_etlRightAmplitude.setValue(
                self._shell.scan_panel.ui.doubleSpinBox_etlLeftAmplitude.value()
            )
            self._shell.scan_panel.ui.doubleSpinBox_etlRightOffset.setValue(
                self._shell.scan_panel.ui.doubleSpinBox_etlLeftOffset.value()
            )
            self._shell.scan_panel.ui.doubleSpinBox_etlRightOffset.setMinimum(
                self._shell.scan_panel.ui.doubleSpinBox_etlLeftOffset.minimum()
            )
            self._shell.scan_panel.ui.doubleSpinBox_etlRightOffset.setMaximum(
                self._shell.scan_panel.ui.doubleSpinBox_etlLeftOffset.maximum()
            )
            self.siggen.etl_right_amplitude = (
                self._shell.scan_panel.ui.doubleSpinBox_etlRightAmplitude.value()
            )
            self.siggen.etl_right_offset = (
                self._shell.scan_panel.ui.doubleSpinBox_etlRightOffset.value()
            )

    def updateUi_etl_right_offset(self) -> None:
        self.siggen.etl_right_offset = (
            self._shell.scan_panel.ui.doubleSpinBox_etlRightOffset.value()
        )
        if self._shell.scan_panel.ui.checkBox_etlSync.isChecked():
            self._shell.scan_panel.ui.doubleSpinBox_etlLeftAmplitude.setValue(
                self._shell.scan_panel.ui.doubleSpinBox_etlRightAmplitude.value()
            )
            self._shell.scan_panel.ui.doubleSpinBox_etlLeftOffset.setValue(
                self._shell.scan_panel.ui.doubleSpinBox_etlRightOffset.value()
            )
            self._shell.scan_panel.ui.doubleSpinBox_etlLeftOffset.setMinimum(
                self._shell.scan_panel.ui.doubleSpinBox_etlRightOffset.minimum()
            )
            self._shell.scan_panel.ui.doubleSpinBox_etlLeftOffset.setMaximum(
                self._shell.scan_panel.ui.doubleSpinBox_etlRightOffset.maximum()
            )
            self.siggen.etl_left_amplitude = (
                self._shell.scan_panel.ui.doubleSpinBox_etlLeftAmplitude.value()
            )
            self.siggen.etl_left_offset = (
                self._shell.scan_panel.ui.doubleSpinBox_etlLeftOffset.value()
            )

    def updateUi_etl_sync(self) -> None:
        if self._shell.scan_panel.ui.checkBox_etlSync.isChecked():
            self._shell.scan_panel.ui.doubleSpinBox_etlRightAmplitude.setValue(
                self._shell.scan_panel.ui.doubleSpinBox_etlLeftAmplitude.value()
            )
            self._shell.scan_panel.ui.doubleSpinBox_etlRightOffset.setValue(
                self._shell.scan_panel.ui.doubleSpinBox_etlLeftOffset.value()
            )
            self._shell.scan_panel.ui.doubleSpinBox_etlRightOffset.setMinimum(
                self._shell.scan_panel.ui.doubleSpinBox_etlLeftOffset.minimum()
            )
            self._shell.scan_panel.ui.doubleSpinBox_etlRightOffset.setMaximum(
                self._shell.scan_panel.ui.doubleSpinBox_etlLeftOffset.maximum()
            )
            self.siggen.etl_right_amplitude = (
                self._shell.scan_panel.ui.doubleSpinBox_etlRightAmplitude.value()
            )
            self.siggen.etl_right_offset = (
                self._shell.scan_panel.ui.doubleSpinBox_etlRightOffset.value()
            )

    def updateUi_etl_steps(self) -> None:
        self.siggen.etl_steps = int(  # ty: ignore[unresolved-attribute]
            self._shell.scan_panel.ui.doubleSpinBox_etlSteps.value()
        )

    def updateUi_etl_activate(self) -> None:
        self.siggen.etl_activated = (  # ty: ignore[unresolved-attribute]
            self._shell.scan_panel.ui.checkBox_etlActivate.isChecked()
        )

    def updateUi_camera_shutter_mode(self) -> None:
        self.camera.shutter_mode = (
            self._shell.acquisition_panel.ui.comboBox_cameraShutterMode.currentText()
        )
        if self.camera.shutter_mode == "Rolling":
            self._shell.acquisition_panel.ui.label_doubleSpinBox_cameraExposureTime.setEnabled(
                True
            )
            self._shell.acquisition_panel.ui.doubleSpinBox_cameraExposureTime.setEnabled(
                True
            )
            self._shell.acquisition_panel.ui.label_doubleSpinBox_cameraLineTime.setEnabled(
                False
            )
            self._shell.acquisition_panel.ui.doubleSpinBox_cameraLineTime.setEnabled(
                False
            )
            self._shell.acquisition_panel.ui.label_doubleSpinBox_cameraExposedLines.setEnabled(
                False
            )
            self._shell.acquisition_panel.ui.doubleSpinBox_cameraExposedLines.setEnabled(
                False
            )
            self._shell.acquisition_panel.ui.label_doubleSpinBox_cameraDelayLines.setEnabled(
                False
            )
            self._shell.acquisition_panel.ui.doubleSpinBox_cameraDelayLines.setEnabled(
                False
            )
        elif self.camera.shutter_mode == "Lightsheet":
            self._shell.acquisition_panel.ui.label_doubleSpinBox_cameraExposureTime.setEnabled(
                False
            )
            self._shell.acquisition_panel.ui.doubleSpinBox_cameraExposureTime.setEnabled(
                False
            )
            self._shell.acquisition_panel.ui.label_doubleSpinBox_cameraLineTime.setEnabled(
                True
            )
            self._shell.acquisition_panel.ui.doubleSpinBox_cameraLineTime.setEnabled(
                True
            )
            self._shell.acquisition_panel.ui.label_doubleSpinBox_cameraExposedLines.setEnabled(
                True
            )
            self._shell.acquisition_panel.ui.doubleSpinBox_cameraExposedLines.setEnabled(
                True
            )
            self._shell.acquisition_panel.ui.label_doubleSpinBox_cameraDelayLines.setEnabled(
                True
            )
            self._shell.acquisition_panel.ui.doubleSpinBox_cameraDelayLines.setEnabled(
                True
            )
        else:
            self._shell.acquisition_panel.ui.label_doubleSpinBox_cameraExposureTime.setEnabled(
                True
            )
            self._shell.acquisition_panel.ui.doubleSpinBox_cameraExposureTime.setEnabled(
                True
            )
            self._shell.acquisition_panel.ui.label_doubleSpinBox_cameraLineTime.setEnabled(
                False
            )
            self._shell.acquisition_panel.ui.doubleSpinBox_cameraLineTime.setEnabled(
                False
            )
            self._shell.acquisition_panel.ui.label_doubleSpinBox_cameraExposedLines.setEnabled(
                False
            )
            self._shell.acquisition_panel.ui.doubleSpinBox_cameraExposedLines.setEnabled(
                False
            )
            self._shell.acquisition_panel.ui.label_doubleSpinBox_cameraDelayLines.setEnabled(
                False
            )
            self._shell.acquisition_panel.ui.doubleSpinBox_cameraDelayLines.setEnabled(
                False
            )

    def updateUi_camera_exposure_time(self) -> None:
        self.camera.exposure_time = (
            self._shell.acquisition_panel.ui.doubleSpinBox_cameraExposureTime.value()
            * 1e-3
        )  # ui(ms) to camera(s)

    def updateUi_camera_line_time(self) -> None:
        self.camera.lightsheet_line_time = (  # ty: ignore[unresolved-attribute]
            self._shell.acquisition_panel.ui.doubleSpinBox_cameraLineTime.value() * 1e-6
        )  # ui(us) to camera(s)

    def updateUi_camera_exposed_lines(self) -> None:
        self.camera.lightsheet_exposed_lines = int(
            self._shell.acquisition_panel.ui.doubleSpinBox_cameraExposedLines.value()
        )

    def updateUi_camera_delay_lines(self) -> None:
        self.camera.lightsheet_delay_lines = int(
            self._shell.acquisition_panel.ui.doubleSpinBox_cameraDelayLines.value()
        )
