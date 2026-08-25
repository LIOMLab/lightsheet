"""AcquisitionCoordinator — god-object split collaborator.

Owns the remaining acquisition worker body (``stack_mode_worker``) plus
the ~15 GUI-thread galvo/ETL/camera-setting slots.
``preview_mode_worker``, ``live_mode_worker``, ``single_mode_worker``,
and ``acquire_scan`` have relocated to ``PreviewWorker`` /
``LiveWorker`` / ``SingleWorker`` / ``_AcquireScanMixin`` in
``lightsheet/gui/workers.py`` as steps of the threading-vehicle
migration to ``QThread`` + worker ``QObject`` (``moveToThread``);
``stack_mode_worker`` relocates in a later plan. The shell
(``Controller_MainWindow``) delegates through ``self._acq`` for the
GUI-thread galvo/ETL slots still hosted here and spawns its worker
threads targeting the worker QObjects in ``workers.py`` for the
migrated modes.

This is a plain-Python object (NOT a ``QObject``) per the plain-Python
collaborator pattern: collaborators emit through a shell reference, never
declare their own ``pyqtSignal``, and never call ``.connect()``. The
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

The tolerated cross-tier Qt widget reads in this collaborator live in
``stack_mode_worker`` (reading widgets from a non-GUI thread is undefined
behavior per Qt's threading model / AGENTS.md §11; these are
pre-existing, moved verbatim from the original controller, and
refactoring them into shell-side pre-sampled args is a larger change
than this extraction's scope and is deferred):

* ``stack_mode_worker`` reads five widgets directly from the worker
  thread: ``self._shell.ui.lineEdit_saveDescription.text()`` (line ~389),
  ``self._shell.ui.checkBox_saveAllCrop.isChecked()`` (lines ~395, ~522),
  and ``self._shell.ui.checkBox_saveAllFull.isChecked()`` (lines ~403,
  ~528).

The ``acquire_scan`` cross-tier reads (``lineEdit_saveDescription``,
``checkBox_saveStitchBlend``) have been eliminated — the relocated
``_AcquireScanMixin.acquire_scan`` in ``workers.py`` reads
``self._save_description`` / ``self._save_stitch_blend`` (constructor
args pre-sampled on the GUI thread). A future maintainer eliminating the
remaining cross-tier reads must address the five ``stack_mode_worker``
sites.
"""

from __future__ import annotations

import datetime
import logging
import threading
from typing import TYPE_CHECKING

import numpy as np

from lightsheet.hal.bundle import DeviceBundle
from lightsheet.gui.workers import _AcquireScanMixin

if TYPE_CHECKING:
    from lightsheet.gui.controller import Controller_MainWindow
    from lightsheet.gui.hardware_manager import HardwareManager

logger = logging.getLogger(__name__)


class AcquisitionCoordinator(_AcquireScanMixin):
    """Acquisition worker + scan orchestration collaborator.

    The remaining worker body (``stack_mode_worker``) is moved verbatim
    from ``Controller_MainWindow`` — only the attribute-access prefix
    changes (``self.`` -> ``self._shell.`` for shell-owned state;
    ``self.camera`` / ``self.siggen`` / ``self.motors`` stay as the
    coordinator's own attributes; ``self.start_lasers()`` /
    ``self.stop_lasers()`` -> ``self._hw.start_lasers()`` /
    ``self._hw.stop_lasers()``). Every existing ``try``/``except``/
    ``finally`` shape (E-stop poll before each frame, ``sig_message`` on
    exception, ``sig_*_mode_finished`` exactly once in ``finally``) is
    preserved verbatim.

    ``preview_mode_worker``, ``live_mode_worker``, ``single_mode_worker``,
    and ``acquire_scan`` have relocated to ``PreviewWorker`` /
    ``LiveWorker`` / ``SingleWorker`` / ``_AcquireScanMixin`` in
    ``lightsheet/gui/workers.py`` as steps of the threading migration;
    ``stack_mode_worker`` relocates in a later plan.
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

    def stack_mode_worker(self) -> None:
        """Thread for volume acquisition and saving"""
        try:
            # Making sure saving is allowed and filename isn't empty
            if self._shell.saving_allowed:
                # Getting sample name
                self._shell.save_description = str(
                    self._shell.ui.lineEdit_saveDescription.text()
                )

                # Setting frame saver
                self._shell._fs.reinit(3)
                self._shell._fs.add_sample_name(self._shell.save_description)
                if self._shell.ui.checkBox_saveAllCrop.isChecked():
                    self._shell._fs.set_files(
                        self._shell.number_of_planes,
                        self._shell.save_filename,
                        "stack",
                        1,
                        "ETLscan",
                    )
                elif self._shell.ui.checkBox_saveAllFull.isChecked():
                    self._shell._fs.set_files(
                        self._shell.number_of_planes,
                        self._shell.save_filename,
                        "stack",
                        1,
                        "FullETLscan",
                    )
                else:
                    self._shell._fs.set_files(
                        1,
                        self._shell.save_filename,
                        "stack",
                        self._shell.number_of_planes,
                        "reconstructed_frame",
                    )
                # Starting frame saver
                self._shell._fs.start_saving()

            # Setting the camera for scan acquisition
            self.camera.arm_scan()

            # Pre-stop guard: a Stop or E-stop pressed in the instant between
            # thread start and this line skips energizing the lasers entirely.
            # The per-plane loop's first-iteration poll then breaks immediately
            # and the end-of-method cleanup (stop_lasers/disarm/emit) runs
            # unchanged, so no lasers are left on and the UI re-enables.
            if self._shell.stack_mode_started and not self._shell.estop_event.is_set():
                self._hw.start_lasers()

            # Set progress bar
            progress_value = 0
            progress_increment = 100 / self._shell.number_of_planes
            self._shell.sig_progress_update.emit(0)  # To reset progress bar

            # Pre-sample the save-option widgets acquire_scan reads, so the
            # inherited _AcquireScanMixin.acquire_scan (relocated to
            # workers.py) finds self._save_description /
            # self._save_stitch_blend. These two cross-tier reads are the
            # stack_mode_worker B-03 sites deferred to the later plan that
            # relocates stack_mode_worker into StackWorker; they stay as
            # ui.* reads here (not yet pre-sampled on the GUI thread).
            self._save_description = str(
                self._shell.ui.lineEdit_saveDescription.text()
            )
            self._save_stitch_blend = (
                self._shell.ui.checkBox_saveStitchBlend.isChecked()
            )

            # Compute scan waveforms only once before we start the stack acquisition
            # Changes to settings won't be effective until we stop/restart mode
            self.siggen.compute_scan_waveforms()

            for plane in range(int(self._shell.number_of_planes)):
                if not self._shell.stack_mode_started:
                    self._shell.sig_message.emit("Stack Acquisition Interrupted")
                    break
                elif self._shell.estop_event.is_set():
                    # E-stop poll point — checked alongside the stack_mode_started
                    # flag at each plane boundary. The lasers are already dark
                    # (driven off synchronously on the GUI thread); this break
                    # stops acquiring new planes.
                    self._shell.sig_message.emit("Stack Acquisition Interrupted")
                    break
                else:
                    # Pre-move guard: a Stop or E-stop requested while the worker
                    # was between blocking calls (after the loop-top poll but
                    # before this motor move) must not start a new blocking call.
                    if (
                        not self._shell.stack_mode_started
                        or self._shell.estop_event.is_set()
                    ):
                        break

                    # Moving sample position
                    position = self._shell.stack_starting_plane + (
                        plane * self._shell.stack_step
                    )
                    try:
                        self.motors.horizontal.move_absolute_position(
                            position, "\u03bcm"
                        )  # Position in micro-meters
                    except ValueError:
                        self._shell.sig_message.emit(
                            "Move rejected — horizontal would exceed travel limits. Stack acquisition aborted."  # noqa: E501
                        )
                        self._shell.sig_beep.emit()
                        break
                    # FIXME - updating ui within secondary thread
                    self._shell.updateUi_position_horizontal()

                    # Moving the camera to focus
                    # FIXME - Add focus adjustement to stack mode
                    # self.calculate_camera_focus()
                    # self.move_camera_to_focus()

                    if self._shell.saving_allowed:
                        self._shell._fs.add_motor_parameters(
                            self._shell.current_horizontal_position_text,
                            self._shell.current_vertical_position_text,
                            self._shell.current_camera_position_text,
                        )

                    # Pre-acquire guard: a Stop or E-stop requested while the worker
                    # was between the motor move and this acquisition must not start
                    # the (potentially long, up to recorder-timeout) camera grab.
                    if (
                        not self._shell.stack_mode_started
                        or self._shell.estop_event.is_set()
                    ):
                        break

                    # Getting image
                    self.acquire_scan()

                    # Abort the stack if the camera timed out on this plane —
                    # acquire_scan already emitted the timeout warning and cleaned
                    # up the recorder/scanner; do not enqueue a (nonexistent)
                    # frame for this plane or attempt the next one.
                    if self.camera.recorder_timeout_status:
                        break

                    # A DAQ scan-task failure would recur on every remaining
                    # plane — abort the stack instead of emitting the same
                    # message N times. acquire_scan already emitted the
                    # operator message and cleaned up the scanner/camera for
                    # this plane; the post-loop stop_lasers/disarm cleanup
                    # runs unchanged.
                    if self.siggen.error:
                        break

                    # Saving frame
                    if self._shell.saving_allowed:
                        if self._shell.ui.checkBox_saveAllCrop.isChecked():
                            cropped_buffer = self._shell._fs.crop_buffer(self._shell.buffer)
                            self._shell._fs.enqueue_buffer(cropped_buffer)
                            self._shell.sig_message.emit(
                                "Saving All Images (one for each ETL step, cropped)"
                            )
                        elif self._shell.ui.checkBox_saveAllFull.isChecked():
                            self._shell._fs.enqueue_buffer(self._shell.buffer)
                            self._shell.sig_message.emit(
                                "Saving All Images (one for each ETL step, full)"
                            )
                        else:
                            self._shell._fs.enqueue_buffer(self._shell.reconstructed_frame)
                            self._shell.sig_message.emit("Saving Reconstructed Image")

                    # Update progress bar
                    progress_value += progress_increment
                    self._shell.sig_progress_update.emit(int(progress_value))

            if self._shell.stack_mode_started:
                self._shell.sig_progress_update.emit(
                    100
                )  # In case the number of planes is not a multiple of 100

            if self._shell.saving_allowed:
                self._shell._fs.stop_saving()

            # Put ETLs in standby mode: 2.5V corresponds no current through coil (mid 0-5V adjustable range)  # noqa: E501
            self.siggen.update_etls(left_etl=2.5, right_etl=2.5)

            # Stopping laser
            self._hw.stop_lasers()

            # Stopping camera
            self.camera.disarm()
        except Exception as e:
            self._shell.sig_message.emit(
                f"Stack acquisition failed — the run was aborted. Cause: {e}"
            )
            logger.exception("Stack mode worker failed")
        finally:
            # The finished signal must fire exactly once whether the method
            # completes normally, breaks out of the per-plane loop, or an
            # exception propagates from stop_lasers()/camera.disarm()/
            # anything else in the body. Without this, a worker that dies
            # mid-cleanup leaves the UI stuck on "Stop Stack Mode" with no
            # slot to re-enable it.
            self._shell.sig_stack_mode_finished.emit()

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
