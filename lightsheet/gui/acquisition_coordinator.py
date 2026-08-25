"""AcquisitionCoordinator — god-object split collaborator.

Owns the ~15 GUI-thread galvo/ETL/camera-setting slots. All four
acquisition worker bodies (``preview_mode_worker``, ``live_mode_worker``,
``single_mode_worker``, ``stack_mode_worker``) and ``acquire_scan`` have
relocated to ``PreviewWorker`` / ``LiveWorker`` / ``SingleWorker`` /
``StackWorker`` / ``_AcquireScanMixin`` in ``lightsheet/gui/workers.py``
as steps of the threading-vehicle migration to ``QThread`` + worker
``QObject`` (``moveToThread``). The shell (``Controller_MainWindow``)
delegates through ``self._acq`` for the GUI-thread galvo/ETL slots still
hosted here and spawns its worker threads targeting the worker QObjects
in ``workers.py`` for all four modes.

This is a plain-Python object (NOT a ``QObject``) per the plain-Python
collaborator pattern: collaborators emit through a shell reference, never
declare their own ``Signal``, and never call ``.connect()``. The
shell-owned state (``sig_message``, ``sig_progress_update``,
``sig_*_mode_finished``, ``estop_event``, the ``<mode>_mode_started``
flags, ``_fs``, ``ui.*`` widgets, ``buffer`` / ``reconstructed_frame`` /
``buffer_metadata_*`` / ``saving_allowed`` / ``number_of_planes`` /
``save_filename`` / ``save_description`` / ``stack_starting_plane`` /
``stack_step`` / ``image_*_pos_text`` / ``current_*_position_text`` /
``sig_beep``) is read off the shell reference. The coordinator's own
attributes are ``self.camera`` / ``self.siggen`` / ``self.motors`` (the
bundle's HAL handles) and ``self._hw`` (the HardwareManager, for
``start_lasers`` / ``stop_lasers``).

The E-stop kill path stays in the thin shell — the coordinator's worker
bodies only *poll* ``self._shell.estop_event`` cooperatively; they never
drive a laser off directly.

All six tolerated cross-tier Qt widget reads have been eliminated — the
relocated worker QObjects in ``workers.py`` read pre-sampled constructor
args (``self._save_description`` / ``self._save_stitch_blend`` /
``self._save_all_crop`` / ``self._save_all_full``) instead of reaching
into ``self._shell.ui.*`` from the worker thread (AGENTS.md §11). The
one direct cross-thread widget mutation (``stack_mode_worker``'s
``self._shell.updateUi_position_horizontal()`` call) has been replaced
with ``self._shell.sig_refresh_position_horizontal.emit()`` (a queued
signal already declared and connected on the shell).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from lightsheet.hal.bundle import DeviceBundle
from lightsheet.gui.workers import _AcquireScanMixin

if TYPE_CHECKING:
    from lightsheet.gui.controller import Controller_MainWindow
    from lightsheet.gui.hardware_manager import HardwareManager

logger = logging.getLogger(__name__)


class AcquisitionCoordinator(_AcquireScanMixin):
    """Acquisition worker + scan orchestration collaborator.

    All four acquisition worker bodies (``preview_mode_worker``,
    ``live_mode_worker``, ``single_mode_worker``, ``stack_mode_worker``)
    and ``acquire_scan`` have relocated to ``PreviewWorker`` /
    ``LiveWorker`` / ``SingleWorker`` / ``StackWorker`` /
    ``_AcquireScanMixin`` in ``lightsheet/gui/workers.py`` as steps of
    the threading migration. This class now hosts only the ~15 GUI-thread
    galvo/ETL/camera-setting slots, which read ``self._shell.ui.*``
    spinboxes/checkboxes and write ``self.siggen.*`` / ``self.camera.*``
    HAL attributes — these slots MUST run on the GUI thread.
    """

    def __init__(
        self,
        bundle: DeviceBundle,
        hw: "HardwareManager",
        shell: "Controller_MainWindow",
    ) -> None:
        self._bundle = bundle
        self._hw = hw
        self._shell = shell
        self.camera = bundle.camera
        self.siggen = bundle.siggen
        self.motors = bundle.motors

    # ------------------------------------------------------------------ #
    # Galvo / ETL / camera-setting GUI-driven update slots
    #
    # Moved verbatim from Controller_MainWindow. Each method reads
    # self._shell.ui.* spinbox/checkbox widgets and writes self.siggen.*
    # / self.camera.* HAL attributes (the coordinator's own bundle-derived
    # handles) plus sibling widgets (the left/right sync feature mirrors
    # the edited side's amplitude/offset onto the opposite side's
    # spinboxes before propagating to the HAL). The ChannelMap-wired
    # siggen attribute writes (galvo_left_amplitude etc.) feed the
    # downstream voltage-clamp / galvo_left_right_swap mechanism in
    # siggen.py — these slots only stage the values; the clamp/swap call
    # sites are untouched by this relocation.
    # ------------------------------------------------------------------ #

    def updateUi_galvo_left_amplitude(self) -> None:
        # Propagate Ui changes to hardware instance
        self.siggen.galvo_left_amplitude = (
            self._shell.ui.doubleSpinBox_galvoLeftAmplitude.value()
        )
        # Adjust Min and Max to prevent amplitude + offset being <-10V or > 10V
        self._shell.ui.doubleSpinBox_galvoLeftOffset.setMinimum(
            -10 + self._shell.ui.doubleSpinBox_galvoLeftAmplitude.value()
        )
        self._shell.ui.doubleSpinBox_galvoLeftOffset.setMaximum(
            10 - self._shell.ui.doubleSpinBox_galvoLeftAmplitude.value()
        )
        if self._shell.ui.checkBox_galvoSync.isChecked():
            # Set opposite galvo amplitude and offset
            self._shell.ui.doubleSpinBox_galvoRightAmplitude.setValue(
                self._shell.ui.doubleSpinBox_galvoLeftAmplitude.value()
            )
            self._shell.ui.doubleSpinBox_galvoRightOffset.setValue(
                self._shell.ui.doubleSpinBox_galvoLeftOffset.value()
            )
            # Adjust Min and Max to prevent amplitude + offset being <-10V or > 10V
            self._shell.ui.doubleSpinBox_galvoRightOffset.setMinimum(
                self._shell.ui.doubleSpinBox_galvoLeftOffset.minimum()
            )
            self._shell.ui.doubleSpinBox_galvoRightOffset.setMaximum(
                self._shell.ui.doubleSpinBox_galvoLeftOffset.maximum()
            )
            # Propagate Ui changes to hardware instance
            self.siggen.galvo_right_amplitude = (
                self._shell.ui.doubleSpinBox_galvoRightAmplitude.value()
            )
            self.siggen.galvo_right_offset = (
                self._shell.ui.doubleSpinBox_galvoRightOffset.value()
            )

    def updateUi_galvo_right_amplitude(self) -> None:
        # Propagate Ui changes to hardware instance
        self.siggen.galvo_right_amplitude = (
            self._shell.ui.doubleSpinBox_galvoRightAmplitude.value()
        )
        # Adjust Min and Max to prevent amplitude + offset being <-10V or > 10V
        self._shell.ui.doubleSpinBox_galvoRightOffset.setMinimum(
            -10 + self._shell.ui.doubleSpinBox_galvoRightAmplitude.value()
        )
        self._shell.ui.doubleSpinBox_galvoRightOffset.setMaximum(
            10 - self._shell.ui.doubleSpinBox_galvoRightAmplitude.value()
        )
        if self._shell.ui.checkBox_galvoSync.isChecked():
            # Set opposite galvo amplitude and offset
            self._shell.ui.doubleSpinBox_galvoLeftAmplitude.setValue(
                self._shell.ui.doubleSpinBox_galvoRightAmplitude.value()
            )
            self._shell.ui.doubleSpinBox_galvoLeftOffset.setValue(
                self._shell.ui.doubleSpinBox_galvoRightOffset.value()
            )
            # Adjust Min and Max to prevent amplitude + offset being <-10V or > 10V
            self._shell.ui.doubleSpinBox_galvoLeftOffset.setMinimum(
                self._shell.ui.doubleSpinBox_galvoRightOffset.minimum()
            )
            self._shell.ui.doubleSpinBox_galvoLeftOffset.setMaximum(
                self._shell.ui.doubleSpinBox_galvoRightOffset.maximum()
            )
            # Propagate Ui changes to hardware instance
            self.siggen.galvo_left_amplitude = (
                self._shell.ui.doubleSpinBox_galvoLeftAmplitude.value()
            )
            self.siggen.galvo_left_offset = (
                self._shell.ui.doubleSpinBox_galvoLeftOffset.value()
            )

    def updateUi_galvo_left_offset(self) -> None:
        # Propagate Ui changes to hardware instance
        self.siggen.galvo_left_offset = self._shell.ui.doubleSpinBox_galvoLeftOffset.value()
        if self._shell.ui.checkBox_galvoSync.isChecked():
            # Set opposite galvo amplitude and offset
            self._shell.ui.doubleSpinBox_galvoRightAmplitude.setValue(
                self._shell.ui.doubleSpinBox_galvoLeftAmplitude.value()
            )
            self._shell.ui.doubleSpinBox_galvoRightOffset.setValue(
                self._shell.ui.doubleSpinBox_galvoLeftOffset.value()
            )
            self._shell.ui.doubleSpinBox_galvoRightOffset.setMinimum(
                self._shell.ui.doubleSpinBox_galvoLeftOffset.minimum()
            )
            self._shell.ui.doubleSpinBox_galvoRightOffset.setMaximum(
                self._shell.ui.doubleSpinBox_galvoLeftOffset.maximum()
            )
            # Propagate Ui changes to hardware instance
            self.siggen.galvo_right_amplitude = (
                self._shell.ui.doubleSpinBox_galvoRightAmplitude.value()
            )
            self.siggen.galvo_right_offset = (
                self._shell.ui.doubleSpinBox_galvoRightOffset.value()
            )

    def updateUi_galvo_right_offset(self) -> None:
        # Propagate Ui changes to hardware instance
        self.siggen.galvo_right_offset = self._shell.ui.doubleSpinBox_galvoRightOffset.value()
        if self._shell.ui.checkBox_galvoSync.isChecked():
            # Set opposite galvo amplitude and offset
            self._shell.ui.doubleSpinBox_galvoLeftAmplitude.setValue(
                self._shell.ui.doubleSpinBox_galvoRightAmplitude.value()
            )
            self._shell.ui.doubleSpinBox_galvoLeftOffset.setValue(
                self._shell.ui.doubleSpinBox_galvoRightOffset.value()
            )
            self._shell.ui.doubleSpinBox_galvoLeftOffset.setMinimum(
                self._shell.ui.doubleSpinBox_galvoRightOffset.minimum()
            )
            self._shell.ui.doubleSpinBox_galvoLeftOffset.setMaximum(
                self._shell.ui.doubleSpinBox_galvoRightOffset.maximum()
            )
            # Propagate Ui changes to hardware instance
            self.siggen.galvo_left_amplitude = (
                self._shell.ui.doubleSpinBox_galvoLeftAmplitude.value()
            )
            self.siggen.galvo_left_offset = (
                self._shell.ui.doubleSpinBox_galvoLeftOffset.value()
            )

    def updateUi_galvo_sync(self) -> None:
        if self._shell.ui.checkBox_galvoSync.isChecked():
            # Set left galvo amplitude and offset to right galvo
            self._shell.ui.doubleSpinBox_galvoRightAmplitude.setValue(
                self._shell.ui.doubleSpinBox_galvoLeftAmplitude.value()
            )
            self._shell.ui.doubleSpinBox_galvoRightOffset.setValue(
                self._shell.ui.doubleSpinBox_galvoLeftOffset.value()
            )
            self._shell.ui.doubleSpinBox_galvoRightOffset.setMinimum(
                self._shell.ui.doubleSpinBox_galvoLeftOffset.minimum()
            )
            self._shell.ui.doubleSpinBox_galvoRightOffset.setMaximum(
                self._shell.ui.doubleSpinBox_galvoLeftOffset.maximum()
            )
            # Propagate Ui changes to hardware instance
            self.siggen.galvo_right_amplitude = (
                self._shell.ui.doubleSpinBox_galvoRightAmplitude.value()
            )
            self.siggen.galvo_right_offset = (
                self._shell.ui.doubleSpinBox_galvoRightOffset.value()
            )

    def updateUi_galvo_activate(self) -> None:
        # Propagate Ui changes to hardware instance
        self.siggen.galvo_activated = self._shell.ui.checkBox_galvoActivate.isChecked()

    def updateUi_galvo_invert(self) -> None:
        # Propagate Ui changes to hardware instance
        self.siggen.galvo_inverted = self._shell.ui.checkBox_galvoInvert.isChecked()

    def updateUi_etl_left_amplitude(self) -> None:
        # Propagate Ui changes to hardware instance
        self.siggen.etl_left_amplitude = self._shell.ui.doubleSpinBox_etlLeftAmplitude.value()
        # Adjust Min and Max to prevent amplitude + offset being <-5V or > 5V
        self._shell.ui.doubleSpinBox_etlLeftOffset.setMinimum(
            -5 + self._shell.ui.doubleSpinBox_etlLeftAmplitude.value()
        )
        self._shell.ui.doubleSpinBox_etlLeftOffset.setMaximum(
            5 - self._shell.ui.doubleSpinBox_etlLeftAmplitude.value()
        )
        if self._shell.ui.checkBox_etlSync.isChecked():
            # Set opposite etl amplitude and offset
            self._shell.ui.doubleSpinBox_etlRightAmplitude.setValue(
                self._shell.ui.doubleSpinBox_etlLeftAmplitude.value()
            )
            self._shell.ui.doubleSpinBox_etlRightOffset.setValue(
                self._shell.ui.doubleSpinBox_etlLeftOffset.value()
            )
            # Adjust Min and Max to prevent amplitude + offset being <-5V or > 5V
            self._shell.ui.doubleSpinBox_etlRightOffset.setMinimum(
                self._shell.ui.doubleSpinBox_etlLeftOffset.minimum()
            )
            self._shell.ui.doubleSpinBox_etlRightOffset.setMaximum(
                self._shell.ui.doubleSpinBox_etlLeftOffset.maximum()
            )
            # Propagate Ui changes to hardware instance
            self.siggen.etl_right_amplitude = (
                self._shell.ui.doubleSpinBox_etlRightAmplitude.value()
            )
            self.siggen.etl_right_offset = self._shell.ui.doubleSpinBox_etlRightOffset.value()

    def updateUi_etl_right_amplitude(self) -> None:
        # Propagate Ui changes to hardware instance
        self.siggen.etl_right_amplitude = (
            self._shell.ui.doubleSpinBox_etlRightAmplitude.value()
        )
        # Adjust Min and Max to prevent amplitude + offset being <-5V or > 5V
        self._shell.ui.doubleSpinBox_etlRightOffset.setMinimum(
            -5 + self._shell.ui.doubleSpinBox_etlRightAmplitude.value()
        )
        self._shell.ui.doubleSpinBox_etlRightOffset.setMaximum(
            5 - self._shell.ui.doubleSpinBox_etlRightAmplitude.value()
        )
        if self._shell.ui.checkBox_etlSync.isChecked():
            # Set opposite etl amplitude and offset
            self._shell.ui.doubleSpinBox_etlLeftAmplitude.setValue(
                self._shell.ui.doubleSpinBox_etlRightAmplitude.value()
            )
            self._shell.ui.doubleSpinBox_etlLeftOffset.setValue(
                self._shell.ui.doubleSpinBox_etlRightOffset.value()
            )
            # Adjust Min and Max to prevent amplitude + offset being <-5V or > 5V
            self._shell.ui.doubleSpinBox_etlLeftOffset.setMinimum(
                self._shell.ui.doubleSpinBox_etlRightOffset.minimum()
            )
            self._shell.ui.doubleSpinBox_etlLeftOffset.setMaximum(
                self._shell.ui.doubleSpinBox_etlRightOffset.maximum()
            )
            # Propagate Ui changes to hardware instance
            self.siggen.etl_left_amplitude = (
                self._shell.ui.doubleSpinBox_etlLeftAmplitude.value()
            )
            self.siggen.etl_left_offset = self._shell.ui.doubleSpinBox_etlLeftOffset.value()

    def updateUi_etl_left_offset(self) -> None:
        # Propagate Ui changes to hardware instance
        self.siggen.etl_left_offset = self._shell.ui.doubleSpinBox_etlLeftOffset.value()
        if self._shell.ui.checkBox_etlSync.isChecked():
            self._shell.ui.doubleSpinBox_etlRightAmplitude.setValue(
                self._shell.ui.doubleSpinBox_etlLeftAmplitude.value()
            )
            self._shell.ui.doubleSpinBox_etlRightOffset.setValue(
                self._shell.ui.doubleSpinBox_etlLeftOffset.value()
            )
            self._shell.ui.doubleSpinBox_etlRightOffset.setMinimum(
                self._shell.ui.doubleSpinBox_etlLeftOffset.minimum()
            )
            self._shell.ui.doubleSpinBox_etlRightOffset.setMaximum(
                self._shell.ui.doubleSpinBox_etlLeftOffset.maximum()
            )
            # Propagate Ui changes to hardware instance
            self.siggen.etl_right_amplitude = (
                self._shell.ui.doubleSpinBox_etlRightAmplitude.value()
            )
            self.siggen.etl_right_offset = self._shell.ui.doubleSpinBox_etlRightOffset.value()

    def updateUi_etl_right_offset(self) -> None:
        # Propagate Ui changes to hardware instance
        self.siggen.etl_right_offset = self._shell.ui.doubleSpinBox_etlRightOffset.value()
        if self._shell.ui.checkBox_etlSync.isChecked():
            self._shell.ui.doubleSpinBox_etlLeftAmplitude.setValue(
                self._shell.ui.doubleSpinBox_etlRightAmplitude.value()
            )
            self._shell.ui.doubleSpinBox_etlLeftOffset.setValue(
                self._shell.ui.doubleSpinBox_etlRightOffset.value()
            )
            self._shell.ui.doubleSpinBox_etlLeftOffset.setMinimum(
                self._shell.ui.doubleSpinBox_etlRightOffset.minimum()
            )
            self._shell.ui.doubleSpinBox_etlLeftOffset.setMaximum(
                self._shell.ui.doubleSpinBox_etlRightOffset.maximum()
            )
            # Propagate Ui changes to hardware instance
            self.siggen.etl_left_amplitude = (
                self._shell.ui.doubleSpinBox_etlLeftAmplitude.value()
            )
            self.siggen.etl_left_offset = self._shell.ui.doubleSpinBox_etlLeftOffset.value()

    def updateUi_etl_sync(self) -> None:
        # Propagate Ui changes to hardware instance
        if self._shell.ui.checkBox_etlSync.isChecked():
            self._shell.ui.doubleSpinBox_etlRightAmplitude.setValue(
                self._shell.ui.doubleSpinBox_etlLeftAmplitude.value()
            )
            self._shell.ui.doubleSpinBox_etlRightOffset.setValue(
                self._shell.ui.doubleSpinBox_etlLeftOffset.value()
            )
            self._shell.ui.doubleSpinBox_etlRightOffset.setMinimum(
                self._shell.ui.doubleSpinBox_etlLeftOffset.minimum()
            )
            self._shell.ui.doubleSpinBox_etlRightOffset.setMaximum(
                self._shell.ui.doubleSpinBox_etlLeftOffset.maximum()
            )
            # Propagate Ui changes to hardware instance
            self.siggen.etl_right_amplitude = (
                self._shell.ui.doubleSpinBox_etlRightAmplitude.value()
            )
            self.siggen.etl_right_offset = self._shell.ui.doubleSpinBox_etlRightOffset.value()

    def updateUi_etl_steps(self) -> None:
        # Propagate Ui changes to hardware instance
        self.siggen.etl_steps = int(self._shell.ui.doubleSpinBox_etlSteps.value())

    def updateUi_etl_activate(self) -> None:
        # Propagate Ui changes to hardware instance
        self.siggen.etl_activated = self._shell.ui.checkBox_etlActivate.isChecked()

    def updateUi_camera_shutter_mode(self) -> None:
        # Propagate Ui changes to hardware instance
        self.camera.shutter_mode = self._shell.ui.comboBox_cameraShutterMode.currentText()
        # Update enabled settings
        if self.camera.shutter_mode == "Rolling":
            self._shell.ui.label_doubleSpinBox_cameraExposureTime.setEnabled(True)
            self._shell.ui.doubleSpinBox_cameraExposureTime.setEnabled(True)
            self._shell.ui.label_doubleSpinBox_cameraLineTime.setEnabled(False)
            self._shell.ui.doubleSpinBox_cameraLineTime.setEnabled(False)
            self._shell.ui.label_doubleSpinBox_cameraExposedLines.setEnabled(False)
            self._shell.ui.doubleSpinBox_cameraExposedLines.setEnabled(False)
            self._shell.ui.label_doubleSpinBox_cameraDelayLines.setEnabled(False)
            self._shell.ui.doubleSpinBox_cameraDelayLines.setEnabled(False)
        elif self.camera.shutter_mode == "Lightsheet":
            self._shell.ui.label_doubleSpinBox_cameraExposureTime.setEnabled(False)
            self._shell.ui.doubleSpinBox_cameraExposureTime.setEnabled(False)
            self._shell.ui.label_doubleSpinBox_cameraLineTime.setEnabled(True)
            self._shell.ui.doubleSpinBox_cameraLineTime.setEnabled(True)
            self._shell.ui.label_doubleSpinBox_cameraExposedLines.setEnabled(True)
            self._shell.ui.doubleSpinBox_cameraExposedLines.setEnabled(True)
            self._shell.ui.label_doubleSpinBox_cameraDelayLines.setEnabled(True)
            self._shell.ui.doubleSpinBox_cameraDelayLines.setEnabled(True)
        else:
            self._shell.ui.label_doubleSpinBox_cameraExposureTime.setEnabled(True)
            self._shell.ui.doubleSpinBox_cameraExposureTime.setEnabled(True)
            self._shell.ui.label_doubleSpinBox_cameraLineTime.setEnabled(False)
            self._shell.ui.doubleSpinBox_cameraLineTime.setEnabled(False)
            self._shell.ui.label_doubleSpinBox_cameraExposedLines.setEnabled(False)
            self._shell.ui.doubleSpinBox_cameraExposedLines.setEnabled(False)
            self._shell.ui.label_doubleSpinBox_cameraDelayLines.setEnabled(False)
            self._shell.ui.doubleSpinBox_cameraDelayLines.setEnabled(False)

    def updateUi_camera_exposure_time(self) -> None:
        # Propagate Ui changes to hardware instance
        self.camera.exposure_time = (
            self._shell.ui.doubleSpinBox_cameraExposureTime.value() * 1e-3
        )  # ui(ms) to camera(s)

    def updateUi_camera_line_time(self) -> None:
        # Propagate Ui changes to Camera instance
        self.camera.lightsheet_line_time = (
            self._shell.ui.doubleSpinBox_cameraLineTime.value() * 1e-6
        )  # ui(us) to camera(s)

    def updateUi_camera_exposed_lines(self) -> None:
        # Propagate Ui changes to Camera instance
        self.camera.lightsheet_exposed_lines = int(
            self._shell.ui.doubleSpinBox_cameraExposedLines.value()
        )

    def updateUi_camera_delay_lines(self) -> None:
        # Propagate Ui changes to Camera instance
        self.camera.lightsheet_delay_lines = int(
            self._shell.ui.doubleSpinBox_cameraDelayLines.value()
        )
