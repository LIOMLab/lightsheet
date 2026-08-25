"""Per-mode acquisition worker QObjects for the threading migration.

This module owns the worker ``QObject`` classes introduced by the
threading-vehicle migration from ``threading.Thread`` to ``QThread`` +
``moveToThread``. Each acquisition mode's worker body relocates here from
``AcquisitionCoordinator`` (which stays plain-Python and keeps its
GUI-thread galvo/ETL slots).

``PreviewWorker``, ``LiveWorker``, and ``SingleWorker`` are present in
this file; ``StackWorker`` lands in a later plan as its body relocates.
The shell (``Controller_MainWindow``) constructs a worker ``QObject`` +
a ``QThread``, calls ``worker.moveToThread(thread)``, connects
``thread.started -> worker.run`` and
``worker.finished -> shell.updateUi_post_<mode>`` /
``worker.finished -> thread.quit``, then ``thread.start()``. Shutdown in
``closeEvent`` calls ``thread.quit()`` + ``thread.wait(5000)``.

The cooperative cancellation model (``*_mode_started`` bool flag +
``estop_event`` ``threading.Event``) is preserved verbatim — the workers
poll ``self._shell.estop_event.is_set()`` at the same loop sites. The
E-stop kill path stays lock-free on the GUI thread; the workers only
*poll* the event. ``QThread.requestInterruption()`` is NOT adopted.

Workers never touch ``self._shell.ui.*`` widgets directly (AGENTS.md
§11) — all cross-thread UI effects flow through the shell's queued
``pyqtSignal`` connections (``sig_message``, ``sig_progress_update``,
``sig_*_mode_finished``) plus this worker's own ``finished`` signal.
The save-option widgets (``lineEdit_saveDescription``,
``checkBox_saveStitchBlend``) are pre-sampled on the GUI thread in the
mode-button slot and passed as ``SingleWorker`` constructor args, so
``_AcquireScanMixin.acquire_scan`` reads ``self._save_description`` /
``self._save_stitch_blend`` instead of reaching into ``self._shell.ui.*``
from the worker thread.
"""

from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING

import numpy as np
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot

from lightsheet.hal.bundle import DeviceBundle

if TYPE_CHECKING:
    from lightsheet.gui.controller import Controller_MainWindow
    from lightsheet.gui.hardware_manager import HardwareManager

logger = logging.getLogger(__name__)


class PreviewWorker(QObject):
    """Worker ``QObject`` for preview mode (beam-calibration visualization).

    Relocated verbatim from ``AcquisitionCoordinator.preview_mode_worker``.
    The body arms the camera, starts the auto-selected lasers, grabs
    frames in a loop while ``self._shell.preview_mode_started`` is set,
    polls ``self._shell.estop_event`` at each iteration, then stops the
    lasers and disarms the camera. The ``finished`` signal fires exactly
    once in ``finally`` so the GUI-thread slot
    (``updateUi_post_preview_mode``) re-enables the UI whether the run
    completes normally, breaks on E-stop, or an exception propagates.
    """

    finished = pyqtSignal()

    def __init__(
        self,
        bundle: DeviceBundle,
        hw: "HardwareManager",
        shell: "Controller_MainWindow",
    ) -> None:
        super().__init__()
        self.camera = bundle.camera
        self._hw = hw
        self._shell = shell

    @pyqtSlot()
    def run(self) -> None:
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
            self.finished.emit()


class _AcquireScanMixin:
    """Shared ``acquire_scan`` helper for the worker QObjects.

    Relocated verbatim from ``AcquisitionCoordinator.acquire_scan`` with
    exactly two attribute-access changes: the save-description widget read
    becomes ``self._save_description``, and the stitch-blend checkbox read
    becomes ``self._save_stitch_blend``. Both are pre-sampled on the GUI
    thread in the mode-button slot and passed as worker constructor args,
    so the worker thread never reaches into the shell's UI widgets
    (AGENTS.md §11).

    ``SingleWorker`` and (later) ``StackWorker`` both inherit this mixin
    so the single shared scan-acquisition body stays in one place. The
    mixin is a plain class (no ``QObject`` base) — the worker QObjects
    provide the ``QObject`` base and the ``finished`` signal.
    """

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
            self._save_description
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
        if self._save_stitch_blend:
            self._shell.reconstructed_frame = self._shell._fs.reconstruct_frame_linear_blend(
                self._shell.buffer
            )
        else:
            self._shell.reconstructed_frame = self._shell._fs.reconstruct_frame(self._shell.buffer)

        # Send reconstructed frame to display port
        self._shell._fs.enqueue_frame(self._shell.reconstructed_frame)


class LiveWorker(QObject, _AcquireScanMixin):
    """Worker ``QObject`` for live mode (continuous scan acquisition).

    Relocated verbatim from ``AcquisitionCoordinator.live_mode_worker``.
    The body starts the auto-selected lasers, grabs scan frames in a loop
    while ``self._shell.live_mode_started`` is set, polls
    ``self._shell.estop_event`` at each iteration, then puts the ETLs in
    standby, stops the lasers, and disarms the camera. The ``finished``
    signal fires exactly once in ``finally`` so the GUI-thread slot
    (``updateUi_post_live_mode``) re-enables the UI whether the run
    completes normally, breaks on E-stop, or an exception propagates.

    Live mode never reads save-option widgets, so the constructor takes
    no B-03 args (mirroring ``PreviewWorker``'s shape).
    """

    finished = pyqtSignal()

    def __init__(
        self,
        bundle: DeviceBundle,
        hw: "HardwareManager",
        shell: "Controller_MainWindow",
    ) -> None:
        super().__init__()
        self.camera = bundle.camera
        self.siggen = bundle.siggen
        self.motors = bundle.motors
        self._hw = hw
        self._shell = shell

    @pyqtSlot()
    def run(self) -> None:
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
            self.finished.emit()


class SingleWorker(QObject, _AcquireScanMixin):
    """Worker ``QObject`` for single-image mode (one scan acquisition).

    Relocated verbatim from ``AcquisitionCoordinator.single_mode_worker``.
    The body records the current motor positions, arms the camera for
    scan acquisition, starts the auto-selected lasers, polls
    ``self._shell.estop_event`` before acquiring (aborting with ETL
    standby + laser stop + camera disarm if set), then acquires a single
    scan, puts the ETLs in standby, stops the lasers, and disarms the
    camera. The ``finished`` signal fires exactly once in ``finally``.

    The save-option widgets (``lineEdit_saveDescription``,
    ``checkBox_saveStitchBlend``) are pre-sampled on the GUI thread in
    ``updateUi_single_mode_button`` and passed as constructor args
    (``save_description``, ``save_stitch_blend``) so
    ``_AcquireScanMixin.acquire_scan`` reads ``self._save_description``
    / ``self._save_stitch_blend`` instead of reaching into
    ``self._shell.ui.*`` from the worker thread (AGENTS.md §11).
    """

    finished = pyqtSignal()

    def __init__(
        self,
        bundle: DeviceBundle,
        hw: "HardwareManager",
        shell: "Controller_MainWindow",
        save_description: str,
        save_stitch_blend: bool,
    ) -> None:
        super().__init__()
        self.camera = bundle.camera
        self.siggen = bundle.siggen
        self.motors = bundle.motors
        self._hw = hw
        self._shell = shell
        # B-03: pre-sampled on the GUI thread before spawning the worker.
        self._save_description = save_description
        self._save_stitch_blend = save_stitch_blend

    @pyqtSlot()
    def run(self) -> None:
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
            self.finished.emit()
