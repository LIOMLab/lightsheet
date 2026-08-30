"""Per-mode acquisition worker QObjects for the threading migration.

This module owns the worker ``QObject`` classes introduced by the
threading-vehicle migration from ``threading.Thread`` to ``QThread`` +
``moveToThread``. Each acquisition mode's worker body relocates here from
``AcquisitionCoordinator`` (which stays plain-Python and keeps its
GUI-thread galvo/ETL slots).

``PreviewWorker``, ``LiveWorker``, ``SingleWorker``, and
``StackWorker`` are all present in this file. The shell
(``Controller_MainWindow``) constructs a worker ``QObject`` +
a ``QThread``, calls ``worker.moveToThread(thread)``, connects
``thread.started -> worker.run`` and
``worker.finished -> shell.updateUi_post_<mode>`` /
``worker.finished -> thread.quit``, then ``thread.start()``. Shutdown in
``closeEvent`` calls ``thread.quit()`` + ``thread.wait(5000)``.

The cooperative cancellation model (``*_mode_started`` bool flag +
``estop_event`` ``threading.Event``) is preserved verbatim — the workers
poll ``self._shell.estop_event.is_set()`` at the same loop sites. The
E-stop kill path stays lock-free on the GUI thread; the workers only
*poll* the event. No QThread interruption API is adopted — the
``estop_event`` ``threading.Event`` is the sole cancellation mechanism.

Workers never touch the shell's ``ui.*`` widgets directly (AGENTS.md
§11) — all cross-thread UI effects flow through the shell's queued
``Signal`` connections (``sig_message``, ``sig_progress_update``,
``sig_refresh_position_horizontal``, ``sig_*_mode_finished``) plus this
worker's own ``finished`` signal. The save-option widgets
(``lineEdit_saveDescription``, ``radioButton_saveStitchBlend``,
``radioButton_saveAllCrop``, ``radioButton_saveAllFull``) are pre-sampled on
the GUI thread in the mode-button slot and passed as worker constructor
args, so ``_AcquireScanMixin.acquire_scan`` and ``StackWorker.run`` read
``self._save_description`` / ``self._save_stitch_blend`` /
``self._save_all_crop`` / ``self._save_all_full`` instead of reaching
into the shell's ``ui.*`` from the worker thread.
"""

from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING

import numpy as np
from PySide6.QtCore import QObject, Signal, Slot

from lightsheet.hal.bundle import DeviceBundle

if TYPE_CHECKING:
    from lightsheet.gui.shell.controller import Controller_MainWindow
    from lightsheet.gui.coordinators.hardware_manager import HardwareManager

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

    finished = Signal()

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
        # Live mode never saves, but acquire_scan() reads these to populate
        # buffer metadata. Empty/False defaults keep the metadata field
        # well-typed without implying a save will occur.
        self._save_description = ""
        self._save_stitch_blend = False
        # B-03: pre-sample the camera exposure time on the GUI thread (the
        # constructor runs on the GUI thread before moveToThread) so run()
        # never reaches into the shell's ui.* from the worker thread
        # (AGENTS.md §11).
        self._camera_exposure_time = int(
            shell.acquisition_panel.ui.doubleSpinBox_cameraExposureTime.value()
        )

    @Slot()
    def run(self) -> None:
        """This thread allows the visualization and manual control of the
        parameters of the beams in the UI. There is no scan here,
        beams only changes when parameters are changed. This the preferred
        mode for beam calibration"""
        try:
            # Setting the camera for self triggered acquisition
            self.camera.set_trigger_mode("auto_trigger")
            self.camera.set_exposure_time(
                self._camera_exposure_time
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
            #
            # Continuous-mode first-laser-only guard: when both auto-laser
            # checkboxes are checked, preview (a continuous mode with no
            # per-plane boundary to sequence over) energizes ONLY L1 for
            # the session and holds L2 off. Alternating L1<->L2 per frame
            # would double frame time and flicker; instead the operator
            # switches which single laser is live by unchecking one
            # auto-laser checkbox and checking the other (the existing
            # _cache_auto_laser_flags() resampling path). The guard passes
            # a local (l1, l2=False) tuple to start_lasers so it energizes
            # only L1 for this call without mutating the shared
            # _auto_laser2 attribute — the cached flag stays at its
            # GUI-thread value, so stop_lasers at the end still reads the
            # original value (L2 was never energized, so stop_lasers's L2
            # .off() is a safe no-op). The strict one-laser-energized
            # invariant holds trivially. Passing the flag as a local
            # argument (instead of the prior save/restore of _auto_laser2)
            # avoids a data race with the GUI thread's
            # _cache_auto_laser_flags() resampling.
            if self._shell._auto_laser1 and self._shell._auto_laser2:
                energize_lasers = (True, False)
            else:
                energize_lasers = None
            self._hw.start_lasers(energize_lasers=energize_lasers)

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

        # Store metadata about buffer to be acquired
        self._shell.buffer_metadata_general = {}
        self._shell.buffer_metadata_general["Date"] = str(datetime.date.today())
        self._shell.buffer_metadata_general["Sample Name"] = str(
            self._save_description
        )

        self._shell.buffer_metadata_waveforms = {}
        self._shell.buffer_metadata_waveforms = self.siggen.waveform_metadata

        self._shell.buffer_metadata_motors = {}
        self._shell.buffer_metadata_lasers = {}
        self._shell.buffer_metadata_camera = {}

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

    finished = Signal()

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
        # Live mode never saves, but acquire_scan() reads these to populate
        # buffer metadata. Empty/False defaults keep the metadata field
        # well-typed without implying a save will occur.
        self._save_description = ""
        self._save_stitch_blend = False

    @Slot()
    def run(self) -> None:
        """This thread allows the execution of scan_mode while modifying
        parameters in the UI"""
        try:
            # Starting lasers.
            #
            # Continuous-mode first-laser-only guard: when both auto-laser
            # checkboxes are checked, live (a continuous mode with no
            # per-plane boundary to sequence over) energizes ONLY L1 for
            # the session and holds L2 off. Alternating L1<->L2 per frame
            # would double frame time and flicker; instead the operator
            # switches which single laser is live by unchecking one
            # auto-laser checkbox and checking the other (the existing
            # _cache_auto_laser_flags() resampling path). The guard passes
            # a local (l1, l2=False) tuple to start_lasers so it energizes
            # only L1 for this call without mutating the shared
            # _auto_laser2 attribute — see PreviewWorker.run for the full
            # rationale (avoids the data race with the GUI thread's
            # _cache_auto_laser_flags() resampling).
            if self._shell._auto_laser1 and self._shell._auto_laser2:
                energize_lasers = (True, False)
            else:
                energize_lasers = None
            self._hw.start_lasers(energize_lasers=energize_lasers)

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
    ``radioButton_saveStitchBlend``) are pre-sampled on the GUI thread in
    ``updateUi_single_mode_button`` and passed as constructor args
    (``save_description``, ``save_stitch_blend``) so
    ``_AcquireScanMixin.acquire_scan`` reads ``self._save_description``
    / ``self._save_stitch_blend`` instead of reaching into
    the shell's ``ui.*`` from the worker thread (AGENTS.md §11).
    """

    finished = Signal()

    def __init__(
        self,
        bundle: DeviceBundle,
        hw: "HardwareManager",
        shell: "Controller_MainWindow",
        save_description: str,
        save_stitch_blend: bool,
        multi_channel: bool = False,
    ) -> None:
        super().__init__()
        self.camera = bundle.camera
        self.siggen = bundle.siggen
        self.motors = bundle.motors
        self._hw = hw
        self._shell = shell
        # Save-option widgets are pre-sampled on the GUI thread before
        # spawning the worker so the worker thread never reaches into the
        # shell's ui.* (cross-thread widget access). acquire_scan() reads
        # these to populate buffer metadata.
        self._save_description = save_description
        self._save_stitch_blend = save_stitch_blend
        # Multi-channel flag pre-sampled on the GUI thread in
        # updateUi_single_mode_button as (_auto_laser1 and _auto_laser2)
        # immediately after _cache_auto_laser_flags() (AGENTS.md §11 —
        # no cross-thread widget reads from workers). When True, run()
        # executes the per-channel cycle: select_laser(0) -> acquire_scan
        # -> capture frame1 -> select_laser(1) -> acquire_scan -> capture
        # frame2, storing both in self._shell.reconstructed_frames dict
        # keyed by laser wavelength. When False, run() is byte-for-byte
        # the existing single-channel path (back-compat).
        self._multi_channel = multi_channel

    @Slot()
    def run(self) -> None:
        """Generates and display a single scan which can be saved afterwards"""
        try:
            # Clear the prior run's frame so a failed acquire_scan (siggen
            # error / camera timeout early-return) cannot leave a stale
            # buffer that updateUi_save_single_image would silently save as
            # this run's data. acquire_scan repopulates these only on a
            # successful scan; the save button is gated on buffer being
            # non-None in updateUi_post_single_mode.
            self._shell.buffer = None
            self._shell.reconstructed_frame = None

            # Getting positions for the image
            self._shell.image_hor_pos_text = self._shell.current_horizontal_position_text
            self._shell.image_ver_pos_text = self._shell.current_vertical_position_text
            self._shell.image_cam_pos_text = self._shell.current_camera_position_text

            # Setting the camera for scan acquisition
            self.camera.arm_scan()

            if self._multi_channel:
                # Multi-channel per-channel cycle (MCA-01/D-07): energize
                # L1 -> acquire -> capture frame1 -> energize L2 -> acquire
                # -> capture frame2. select_laser(idx) is the
                # one-laser-energized invariant choke point (MCA-02) — it
                # de-energizes the other laser before energizing the
                # target, so only one laser is active at any instant. Do
                # NOT call start_lasers here (it would energize both at
                # once, violating the invariant); select_laser per channel
                # instead. stop_lasers at the end is safety — ensures
                # both off regardless of the last select_laser state.
                #
                # Pitfall #3 (09-RESEARCH.md): acquire_scan overwrites
                # self._shell.reconstructed_frame. Capture frame1
                # immediately after the first acquire_scan (before the
                # second select_laser + acquire_scan overwrites it).
                self._hw.select_laser(0)
                if self._shell.estop_event.is_set():
                    self.siggen.update_etls(left_etl=2.5, right_etl=2.5)
                    self._hw.stop_lasers()
                    self.camera.disarm()
                    return
                # Refresh scan waveforms with current settings (once,
                # before the first channel — the second channel reuses
                # the same waveform).
                self.siggen.compute_scan_waveforms()
                self.acquire_scan()
                if self.camera.recorder_timeout_status or self.siggen.error:
                    self.siggen.update_etls(left_etl=2.5, right_etl=2.5)
                    self._hw.stop_lasers()
                    self.camera.disarm()
                    return
                # Capture frame1 immediately — the next acquire_scan
                # overwrites reconstructed_frame (pitfall #3).
                frame1 = (
                    None
                    if self._shell.reconstructed_frame is None
                    else self._shell.reconstructed_frame.copy()
                )

                self._hw.select_laser(1)
                if self._shell.estop_event.is_set():
                    self.siggen.update_etls(left_etl=2.5, right_etl=2.5)
                    self._hw.stop_lasers()
                    self.camera.disarm()
                    return
                self.acquire_scan()
                if self.camera.recorder_timeout_status or self.siggen.error:
                    self.siggen.update_etls(left_etl=2.5, right_etl=2.5)
                    self._hw.stop_lasers()
                    self.camera.disarm()
                    return
                frame2 = (
                    None
                    if self._shell.reconstructed_frame is None
                    else self._shell.reconstructed_frame.copy()
                )

                # Store both frames in the per-channel dict keyed by
                # laser wavelength (D-07). reconstructed_frame stays as
                # an alias to the last channel's frame for back-compat
                # with existing single-field consumers (save_panel,
                # display).
                wl1 = int(self._shell.lasers[0].wavelength)
                wl2 = int(self._shell.lasers[1].wavelength)
                self._shell.reconstructed_frames = {}
                if frame1 is not None:
                    self._shell.reconstructed_frames[wl1] = frame1
                if frame2 is not None:
                    self._shell.reconstructed_frames[wl2] = frame2
                    # Alias to the last channel's frame for back-compat.
                    self._shell.reconstructed_frame = frame2

                # Enqueue both tagged frames for saving (D-06 channel-
                # tagged save queue). The tagged form (channel_idx,
                # frame) is accepted by enqueue_buffer; the
                # single-consumer save worker branches on the tag in a
                # later plan. Only enqueue when saving is allowed and
                # both frames were captured.
                if (
                    self._shell.saving_allowed
                    and frame1 is not None
                    and frame2 is not None
                ):
                    self._shell._fs.enqueue_buffer((0, frame1))
                    self._shell._fs.enqueue_buffer((1, frame2))
            else:
                # Single-channel path (unchanged — back-compat).

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

            # Stop lasers — safety: ensures both lasers off regardless of
            # mode (multi-channel's last select_laser may have left L2 on;
            # single-channel's start_lasers may have left the auto-selected
            # laser on).
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


class StackWorker(QObject, _AcquireScanMixin):
    """Worker ``QObject`` for stack mode (volume acquisition + saving).

    Relocated verbatim from ``AcquisitionCoordinator.stack_mode_worker``.
    The body arms the camera for scan acquisition, starts the auto-selected
    lasers (guarded by a pre-stop check), computes scan waveforms once,
    then loops over ``self._shell.number_of_planes`` planes — moving the
    horizontal motor, acquiring a scan, and saving the frame. The
    ``finished`` signal fires exactly once in ``finally`` so the
    GUI-thread slot (``updateUi_post_stack_mode``) re-enables the UI
    whether the run completes normally, breaks on E-stop/Stop, or an
    exception propagates.

    The save-option widgets (``lineEdit_saveDescription``,
    ``radioButton_saveStitchBlend``, ``radioButton_saveAllCrop``,
    ``radioButton_saveAllFull``) are pre-sampled on the GUI thread in
    ``updateUi_stack_mode_button`` and passed as constructor args
    (``save_description``, ``save_stitch_blend``, ``save_all_crop``,
    ``save_all_full``) so the worker thread never reaches into
    the shell's ``ui.*`` (AGENTS.md §11).

    The per-plane position update reaches the GUI thread via the queued
    ``sig_refresh_position_horizontal`` signal (already declared on the
    shell and connected to the GUI-thread position-refresh slot) instead
    of a legacy direct cross-thread widget mutation — closing the last
    AGENTS.md §11 direct-widget-mutation violation.

    Known limitation: stack mode does not adjust camera focus between
    planes (the single-frame worker does). Adding per-plane focus
    adjustment here is a future enhancement, not a regression.
    """

    finished = Signal()

    def __init__(
        self,
        bundle: DeviceBundle,
        hw: "HardwareManager",
        shell: "Controller_MainWindow",
        save_description: str,
        save_stitch_blend: bool,
        save_all_crop: bool,
        save_all_full: bool,
        multi_channel: bool = False,
    ) -> None:
        super().__init__()
        self.camera = bundle.camera
        self.siggen = bundle.siggen
        self.motors = bundle.motors
        self._hw = hw
        self._shell = shell
        # Save-option widgets are pre-sampled on the GUI thread before
        # spawning the worker so the worker thread never reaches into the
        # shell's ui.* (cross-thread widget access). acquire_scan() reads
        # these to populate buffer metadata.
        self._save_description = save_description
        self._save_stitch_blend = save_stitch_blend
        self._save_all_crop = save_all_crop
        self._save_all_full = save_all_full
        # Multi-channel flag pre-sampled on the GUI thread in
        # _spawn_stack_worker as (_auto_laser1 and _auto_laser2)
        # immediately after _cache_auto_laser_flags() (AGENTS.md §11 —
        # no cross-thread widget reads from workers). When True, run()
        # executes the per-plane sequential cycle: for each plane,
        # move -> select_laser(0) -> acquire -> capture frame1 ->
        # select_laser(1) -> acquire -> capture frame2 -> enqueue both
        # tagged frames. When False, run() is byte-for-byte the existing
        # single-channel path (back-compat): start_lasers once at top,
        # one acquire_scan per plane, one bare-ndarray enqueue per plane.
        self._multi_channel = multi_channel
        # Pre-sample the configured laser wavelengths on the GUI thread
        # (the constructor runs on the GUI thread inside
        # _spawn_stack_worker) so the worker thread never reaches into
        # the live ILaser instances from run() (AGENTS.md §11 — no
        # cross-thread reads of shared HAL state from workers). The
        # wavelengths are read from the live ILaser instances here, never
        # hardcoded. In multi-channel mode these are passed to
        # set_files(wavelengths=...) so the save side builds one
        # per-channel filename list (and the Zarr writer allocates a
        # channel axis); in single-channel mode this stays None and the
        # existing single-filename-list path is used unchanged.
        if multi_channel:
            self._wavelengths: list[int] | None = [
                int(self._shell.lasers[0].wavelength),
                int(self._shell.lasers[1].wavelength),
            ]
        else:
            self._wavelengths = None

    @Slot()
    def run(self) -> None:
        """Thread for volume acquisition and saving"""
        try:
            # Making sure saving is allowed and filename isn't empty
            if self._shell.saving_allowed:
                # Getting sample name
                self._shell.save_description = str(
                    self._save_description
                )

                # Setting frame saver
                self._shell._fs.reinit(3)
                self._shell._fs.add_sample_name(self._shell.save_description)
                # In multi-channel mode, pass the pre-sampled wavelengths
                # to set_files so the save side builds one per-channel
                # filename list (HDF5) and the Zarr writer allocates a
                # channel axis sized to the channel count. Without this,
                # filenames_lists stays empty and the multi-channel save
                # workers crash (HDF5/both: AttributeError on tuple.ndim;
                # Zarr: IndexError on channel-1 write_plane).
                if self._multi_channel and self._wavelengths:
                    set_files_kwargs = {"wavelengths": self._wavelengths}
                else:
                    set_files_kwargs = {}
                if self._save_all_crop:
                    self._shell._fs.set_files(
                        self._shell.number_of_planes,
                        self._shell.save_filepath,
                        "stack",
                        1,
                        "ETLscan",
                        **set_files_kwargs,
                    )
                elif self._save_all_full:
                    self._shell._fs.set_files(
                        self._shell.number_of_planes,
                        self._shell.save_filepath,
                        "stack",
                        1,
                        "FullETLscan",
                        **set_files_kwargs,
                    )
                else:
                    self._shell._fs.set_files(
                        1,
                        self._shell.save_filepath,
                        "stack",
                        self._shell.number_of_planes,
                        "reconstructed_frame",
                        **set_files_kwargs,
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
            #
            # Multi-channel mode (MCA-01 stack) MUST NOT call start_lasers
            # here — it would energize both lasers simultaneously, violating
            # the one-laser-energized invariant (MCA-02). The per-plane
            # cycle below uses select_laser(0/1) per channel instead, which
            # de-energizes the other laser before energizing the target.
            # stop_lasers at the end of run() is safety — ensures both off
            # regardless of the last select_laser state.
            if (
                not self._multi_channel
                and self._shell.stack_mode_started
                and not self._shell.estop_event.is_set()
            ):
                self._hw.start_lasers()

            # Set progress bar
            progress_value = 0
            # Defensive guard: a zero plane count (e.g. a queue row that
            # slipped past validation, or a future code path/race) would
            # divide by zero below. Abort with a status message instead of
            # raising ZeroDivisionError. The single-stack path ensures
            # >=1 via updateUi_set_number_of_planes; this guard is the
            # backstop for the queue path and any unexpected zero.
            n_planes = int(self._shell.number_of_planes)
            if n_planes <= 0:
                self._shell.sig_message.emit(
                    "Stack acquisition aborted: number of planes is 0"
                )
                self._shell.sig_beep.emit()
                return
            progress_increment = 100 / n_planes
            self._shell.sig_progress_update.emit(0)  # To reset progress bar

            # Compute scan waveforms only once before we start the stack acquisition
            # Changes to settings won't be effective until we stop/restart mode
            self.siggen.compute_scan_waveforms()

            for plane in range(n_planes):
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
                    # Per-plane position update reaches the GUI thread via the
                    # queued sig_refresh_position_horizontal signal (already
                    # declared on the shell and connected to
                    # updateUi_position_horizontal) instead of a direct
                    # cross-thread widget mutation (AGENTS.md §11).
                    self._shell.sig_refresh_position_horizontal.emit()

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

                    if self._multi_channel:
                        # Multi-channel per-plane sequential cycle (MCA-01
                        # stack): energize L1 -> acquire -> capture frame1 ->
                        # energize L2 -> acquire -> capture frame2 -> enqueue
                        # both tagged frames. select_laser(idx) is the
                        # one-laser-energized invariant choke point (MCA-02)
                        # — it de-energizes the other laser before energizing
                        # the target, so only one laser is active at any
                        # instant. Do NOT call start_lasers here (it would
                        # energize both at once, violating the invariant);
                        # select_laser per channel instead.
                        #
                        # Pitfall #3 (09-RESEARCH.md): acquire_scan overwrites
                        # self._shell.reconstructed_frame. Capture frame1
                        # immediately after the first acquire_scan (before
                        # the second select_laser + acquire_scan overwrites
                        # it).
                        self._hw.select_laser(0)
                        # E-stop poll point — checked after select_laser(0)
                        # and before acquire_scan so a mid-plane E-stop
                        # (pressed between the channel-0 energize and the
                        # channel-0 frame grab) aborts without acquiring.
                        # The lasers are already dark (driven off
                        # synchronously on the GUI thread); select_laser(0)
                        # self-skips the energize when estop is set, and this
                        # break stops the per-plane cycle.
                        if self._shell.estop_event.is_set():
                            break
                        self.acquire_scan()
                        # Abort the stack if the camera timed out or the DAQ
                        # scan task failed on this channel — acquire_scan
                        # already emitted the warning and cleaned up the
                        # recorder/scanner; do not attempt channel 2 or the
                        # next plane.
                        if self.camera.recorder_timeout_status or self.siggen.error:
                            break
                        # Capture frame1 immediately — the next acquire_scan
                        # overwrites reconstructed_frame (pitfall #3).
                        frame1 = (
                            None
                            if self._shell.reconstructed_frame is None
                            else self._shell.reconstructed_frame.copy()
                        )

                        self._hw.select_laser(1)
                        # E-stop poll point — checked after select_laser(1)
                        # and before the channel-1 acquire_scan.
                        if self._shell.estop_event.is_set():
                            break
                        self.acquire_scan()
                        if self.camera.recorder_timeout_status or self.siggen.error:
                            break
                        frame2 = (
                            None
                            if self._shell.reconstructed_frame is None
                            else self._shell.reconstructed_frame.copy()
                        )

                        # Store both frames in the per-channel dict keyed by
                        # laser wavelength (D-07). reconstructed_frame stays
                        # as an alias to the last channel's frame for
                        # back-compat with existing single-field consumers.
                        wl1 = int(self._shell.lasers[0].wavelength)
                        wl2 = int(self._shell.lasers[1].wavelength)
                        self._shell.reconstructed_frames = {}
                        if frame1 is not None:
                            self._shell.reconstructed_frames[wl1] = frame1
                        if frame2 is not None:
                            self._shell.reconstructed_frames[wl2] = frame2
                            # Alias to the last channel's frame for back-compat.
                            self._shell.reconstructed_frame = frame2

                        # Enqueue both tagged frames for saving (D-06
                        # channel-tagged save queue). The tagged form
                        # (channel_idx, frame) is accepted by enqueue_buffer;
                        # the single-consumer save worker branches on the
                        # tag in a later plan. Only enqueue when saving is
                        # allowed and both frames were captured.
                        if (
                            self._shell.saving_allowed
                            and frame1 is not None
                            and frame2 is not None
                        ):
                            self._shell._fs.enqueue_buffer((0, frame1))
                            self._shell._fs.enqueue_buffer((1, frame2))
                    else:
                        # Single-channel path (unchanged — back-compat).

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
                            if self._save_all_crop:
                                cropped_buffer = self._shell._fs.crop_buffer(self._shell.buffer)
                                self._shell._fs.enqueue_buffer(cropped_buffer)
                                self._shell.sig_message.emit(
                                    "Saving All Images (one for each ETL step, cropped)"
                                )
                            elif self._save_all_full:
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

            # Stopping laser — safety: ensures both lasers off regardless
            # of mode. In multi-channel mode the last select_laser(1) may
            # have left L2 on; in single-channel mode start_lasers may
            # have left the auto-selected laser on. stop_lasers reads the
            # cached auto-laser flags and drives .off() on each active
            # laser (AGENTS.md §2 — both off before camera disarm).
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
            self.finished.emit()
