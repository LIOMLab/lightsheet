"""AcquisitionCoordinator — god-object split collaborator.

Owns the four acquisition worker bodies (``preview_mode_worker``,
``live_mode_worker``, ``single_mode_worker``, ``stack_mode_worker``) plus
``acquire_scan``. The shell (``Controller_MainWindow``) delegates through
``self._acq`` and spawns its worker threads targeting
``self._acq.<mode>_mode_worker``.

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

The ONE tolerated cross-tier read in this collaborator lives here:
``acquire_scan`` reads ``self._shell.ui.*`` widgets (save-option
checkboxes, save-description line edit) directly. The golden harness's
existing ``standin.ui.lineEdit_saveDescription.text.return_value`` seam
depends on this access pattern surviving. Refactoring it into a
shell-side pre-sampled arg is a larger change than this extraction's
scope and is deferred.
"""

from __future__ import annotations

import datetime
import logging
import threading
from typing import TYPE_CHECKING

import numpy as np

from lightsheet.hal.bundle import DeviceBundle

if TYPE_CHECKING:
    from lightsheet.gui.controller import Controller_MainWindow
    from lightsheet.gui.hardware_manager import HardwareManager

logger = logging.getLogger(__name__)


class AcquisitionCoordinator:
    """Acquisition worker + scan orchestration collaborator.

    All five method bodies (``preview_mode_worker``, ``live_mode_worker``,
    ``single_mode_worker``, ``stack_mode_worker``, ``acquire_scan``) are
    moved verbatim from ``Controller_MainWindow`` — only the
    attribute-access prefix changes (``self.`` ->
    ``self._shell.`` for shell-owned state; ``self.camera`` /
    ``self.siggen`` / ``self.motors`` stay as the coordinator's own
    attributes; ``self.start_lasers()`` / ``self.stop_lasers()`` ->
    ``self._hw.start_lasers()`` / ``self._hw.stop_lasers()``). Every
    existing ``try``/``except``/``finally`` shape (E-stop poll before each
    frame, ``sig_message`` on exception, ``sig_*_mode_finished`` exactly
    once in ``finally``) is preserved verbatim.
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

    def preview_mode_worker(self) -> None:
        """This thread allows the visualization and manual control of the
        parameters of the beams in the UI. There is no scan here,
        beams only changes when parameters are changed. This the preferred
        mode for beam calibration"""
        try:
            # Setting the camera for self triggered acquisition
            self.camera.set_trigger_mode("auto_trigger")
            self.camera.set_exposure_time(
                int(self._shell.ui.doubleSpinBox_cameraExposureTime.value())
            )
            self.camera.arm()

            # Start the auto-selected lasers after camera.arm() and before
            # the preview loop, mirroring live_mode_worker's shape. Preview
            # mode now drives the lasers so the operator can see the beam
            # while adjusting parameters — the previous shape left the
            # lasers dark during preview, defeating the mode's purpose for
            # beam calibration. start_lasers/stop_lasers read the cached
            # auto-laser flags sampled on the GUI thread by
            # _cache_auto_laser_flags() in updateUi_preview_mode_button.
            self._hw.start_lasers()

            while self._shell.preview_mode_started:
                # E-stop poll point — checked at the top of each iteration
                # before any frame acquisition work. The lasers are already
                # dark (driven off synchronously on the GUI thread in
                # updateUi_estop_pressed); this break just stops acquiring
                # new frames. Preview mode does not drive lasers or scan
                # generation, but the camera stays armed and grabbing until
                # the operator manually stops — polling estop_event aligns
                # preview_mode_worker with live/single/stack per the
                # AGENTS.md §2 rule that E-stop is polled in all acquisition
                # worker loops.
                if self._shell.estop_event.is_set():
                    break

                # # Updating Galvo and ETL voltages
                # self.siggen.update_all()

                # Recording a single image
                self.camera.start_recorder(1)
                self.camera.monitor_recorder(1)
                self.camera.stop_recorder()
                cam_images = self.camera.copy_recorder_images(1)
                self.camera.delete_recorder()

                # Sending first (and should be only) image to display port
                frame = cam_images[0]
                self._shell._fs.enqueue_frame(frame)

            # Stop the lasers before camera.disarm(), mirroring
            # live_mode_worker's cleanup shape. The lasers were started after
            # camera.arm() above; stopping them here ensures no laser is left
            # energized when the camera is disarmed and the mode exits.
            self._hw.stop_lasers()

            # Stopping camera
            self.camera.disarm()
        except Exception as e:
            self._shell.sig_message.emit(
                f"Preview acquisition failed — the run was aborted. Cause: {e}"
            )
            logger.exception("Preview mode worker failed")
        finally:
            # The finished signal must fire exactly once whether the method
            # completes normally or an exception propagates from
            # start_lasers()/acquire_scan()/camera.disarm()/anything else in
            # the body. Without this, a worker that dies mid-cleanup leaves
            # the UI stuck on "Stop Preview Mode" with no slot to re-enable it.
            self._shell.sig_preview_mode_finished.emit()

    def live_mode_worker(self) -> None:
        """This thread allows the execution of scan_mode while modifying
        parameters in the UI"""
        try:
            # Moving the camera to focus
            ##self.move_camera_to_focus()

            #        # Setting the camera for scan acquisition
            #        self.camera.arm_scan()

            # Starting lasers
            self._hw.start_lasers()

            while self._shell.live_mode_started:
                # E-stop poll point — checked at the top of each iteration before
                # any frame acquisition work. The lasers are already dark (driven
                # off synchronously on the GUI thread in updateUi_estop_pressed);
                # this break just stops acquiring new frames.
                if self._shell.estop_event.is_set():
                    break

                # Setting the camera for scan acquisition
                self.camera.arm_scan()

                # Refresh scan waveforms every loop (live mode)
                self.siggen.compute_scan_waveforms()
                # Get single image
                self.acquire_scan()

            # Put ETLs in standby mode: 2.5V corresponds no current through coil (mid 0-5V adjustable range)  # noqa: E501
            self.siggen.update_etls(left_etl=2.5, right_etl=2.5)

            # Stopping lasers
            self._hw.stop_lasers()

            # Stopping camera
            self.camera.disarm()
        except Exception as e:
            self._shell.sig_message.emit(
                f"Live acquisition failed — the run was aborted. Cause: {e}"
            )
            logger.exception("Live mode worker failed")
        finally:
            # The finished signal must fire exactly once whether the method
            # completes normally, breaks out of the loop on E-stop, or an
            # exception propagates from start_lasers()/acquire_scan()/
            # stop_lasers()/camera.disarm()/anything else in the body.
            # Without this, a worker that dies mid-cleanup leaves the UI
            # stuck on "Stop Live Mode" with no slot to re-enable it.
            self._shell.sig_live_mode_finished.emit()

    def single_mode_worker(self) -> None:
        """Generates and display a single scan which can be saved afterwards"""
        try:
            # Moving the camera to focus
            ##self.move_camera_to_focus()

            # Getting positions for the image
            self._shell.image_hor_pos_text = self._shell.current_horizontal_position_text
            self._shell.image_ver_pos_text = self._shell.current_vertical_position_text
            self._shell.image_cam_pos_text = self._shell.current_camera_position_text

            # Setting the camera for scan acquisition
            self.camera.arm_scan()

            # Start lasers
            self._hw.start_lasers()

            # E-stop poll point — checked before acquire_scan so a mid-acquisition
            # E-stop (pressed between mode start and the single frame grab) aborts
            # without acquiring the frame. The lasers are already dark from the
            # synchronous GUI-thread zeroing in updateUi_estop_pressed.
            if self._shell.estop_event.is_set():
                # Put ETLs in standby and stop lasers/camera before exiting so the
                # post-mode cleanup matches the normal single_mode_worker exit.
                self.siggen.update_etls(left_etl=2.5, right_etl=2.5)
                self._hw.stop_lasers()
                self.camera.disarm()
                return

            # Refresh scan waveforms with current settings
            self.siggen.compute_scan_waveforms()

            # Acquire a single scan
            self.acquire_scan()

            # Put ETLs in standby mode
            # 2.5V corresponds no current through coil (mid 0-5V adjustable range)
            self.siggen.update_etls(left_etl=2.5, right_etl=2.5)

            # Stop lasers
            self._hw.stop_lasers()

            # Stop camera
            self.camera.disarm()
        except Exception as e:
            self._shell.sig_message.emit(
                f"Single image acquisition failed — the run was aborted. Cause: {e}"
            )
            logger.exception("Single image mode worker failed")
        finally:
            # The finished signal must fire exactly once whether the method
            # returns early (E-stop), completes normally, or an exception
            # propagates from stop_lasers()/camera.disarm()/anything else.
            # Without this, a worker that dies mid-cleanup leaves the UI
            # stuck on "Acquiring..." with no slot to re-enable it.
            self._shell.sig_single_mode_finished.emit()

    def acquire_scan(self) -> None:
        """
        Generate scan tasks using previously computed waveforms and
        acquire a single reconstructed frame
        """

        # TODO - thread lock siggen and camera while we acquire

        # Store metadata about buffer to be acquired
        self._shell.buffer_metadata_general = {}
        self._shell.buffer_metadata_general["Date"] = str(datetime.date.today())
        self._shell.buffer_metadata_general["Sample Name"] = str(
            self._shell.ui.lineEdit_saveDescription.text()
        )

        self._shell.buffer_metadata_waveforms = {}
        self._shell.buffer_metadata_waveforms = self.siggen.waveform_metadata

        # TODO - motors and lasers and camera (?) metadata
        self._shell.buffer_metadata_motors = {}
        self._shell.buffer_metadata_lasers = {}
        self._shell.buffer_metadata_camera = {}

        # self.buffer_metadata['Horizontal Position']  = self.motors.horizontal.get_position('mm')  # noqa: E501
        # self.buffer_metadata['Vertical Position']  = self.motors.vertical.get_position('mm')  # noqa: E501
        # self.buffer_metadata['Camera Position']  = self.motors.camera.get_position('mm')  # noqa: E501

        # Number of images to be acquired from the camera
        number_of_images = self.siggen.waveform_cycles

        # Creating acquisition tasks
        # Clear any error left over from a previous acquisition so the check
        # below reflects this create_scanner() call only.
        self.siggen.error = 0
        self.siggen.create_scanner()
        # create_scanner() wraps its DAQ task creation in a bare except that
        # sets self.siggen.error = 1 + a generic 'create_scan error' message
        # but never raises. Without this check a failed create_scanner()
        # leaves task_galvo_etl / task_camera as None, start_scanner() /
        # monitor_scanner() become no-ops, and the camera waits out its full
        # recorder timeout with nothing to report — a silent 15 s timeout
        # that is impossible to diagnose. Surface it here, before the
        # recorder is primed, so the operator sees the real DAQ fault
        # instead of a camera timeout. The recorder is never primed on this
        # path, so there is no recorder to delete; the scanner task objects
        # are None so delete_scanner() is a safe no-op, and disarm() returns
        # the camera to a consistent state. Do NOT clear self.siggen.error
        # here — the stack worker inspects it to decide whether to abort the
        # remaining planes, and the reset above clears it at the start of
        # the next acquisition.
        if self.siggen.error:
            self._shell.sig_message.emit(
                f"Scan task creation failed — the acquisition was aborted before the camera was triggered. Check the NI DAQ connection (Dev1). Cause: {self.siggen.error_message}"  # noqa: E501
            )
            logger.warning("SigGen create_scanner failed during acquire_scan")
            self.siggen.delete_scanner()
            self.camera.disarm()
            return

        # Prime the camera recorder before we start the acquisition taks
        self.camera.start_recorder(number_of_images)
        self.siggen.start_scanner()

        # Monitor completion of acquisition tasks and camera recorder
        self.camera.monitor_recorder(number_of_images)
        self.siggen.monitor_scanner()

        # Stop tasks and recorder
        self.camera.stop_recorder()
        self.siggen.stop_scanner()

        # Abort on recorder timeout — never copy zero-filled frames to disk.
        # The recorder timeout flag is set by monitor_recorder when the camera
        # did not return the expected frames in time. Returning here before
        # copy_recorder_images ensures a timed-out plane is not mistaken for
        # a real (dark) frame on disk.
        if self.camera.recorder_timeout_status:
            self._shell.sig_message.emit(
                "Camera timeout — plane was not recorded (camera did not return frames in time). "  # noqa: E501
                "The acquisition was aborted. Reduce the number of images per plane or check the camera USB connection, then restart the run."  # noqa: E501
            )
            logger.warning("Camera recorder timeout during acquire_scan")
            self.camera.delete_recorder()
            # Delete the DAQ scanner task. The scanner was already stopped
            # above (before the timeout check) — NI-DAQmx Task.stop() is
            # idempotent, so a second stop_scanner() here was redundant and
            # is omitted. delete_scanner() tears down the task so the DAQ
            # hardware is left in a consistent state.
            self.siggen.delete_scanner()
            # Disarm the camera before returning. Camera.disarm() is
            # idempotent (it only issues the SDK stop-recording call when
            # the camera reports recording state == 'on'), so calling it
            # here and again from a caller that reaches its own disarm()
            # is safe. This ensures a camera left mid-timeout is always
            # disarmed before any worker that might die afterward gets a
            # chance to skip its own cleanup.
            self.camera.disarm()
            return

        # Recover images from the recorder
        # Note: Images must be recovered before deleting the recorder
        recorded_images = self.camera.copy_recorder_images(number_of_images)
        self._shell.buffer = np.asarray(recorded_images)

        # Delete tasks and recorder
        self.camera.delete_recorder()
        self.siggen.delete_scanner()

        # Frame reconstruction options
        if self._shell.ui.checkBox_saveStitchBlend.isChecked():
            self._shell.reconstructed_frame = self._shell._fs.reconstruct_frame_linear_blend(
                self._shell.buffer
            )
        else:
            self._shell.reconstructed_frame = self._shell._fs.reconstruct_frame(self._shell.buffer)

        # Send reconstructed frame to display port
        self._shell._fs.enqueue_frame(self._shell.reconstructed_frame)

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
