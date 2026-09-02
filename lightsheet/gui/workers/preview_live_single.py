"""Preview, live, and single-image acquisition worker QObjects.

These three workers use the shared ``_AcquireScanMixin`` for live/single
acquisition; PreviewWorker runs a beam-calibration loop without a scan.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal, Slot

from lightsheet.gui.workers.scan_mixin import _AcquireScanMixin
from lightsheet.hal.bundle import DeviceBundle

if TYPE_CHECKING:
    from lightsheet.gui.coordinators.hardware_manager import HardwareManager
    from lightsheet.gui.shell.controller import Controller_MainWindow

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
        hw: HardwareManager,
        shell: Controller_MainWindow,
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
        # Pre-sample the camera exposure time on the GUI thread so run()
        # never reaches into the shell's ui.* from the worker thread.
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
            self.camera.set_exposure_time(self._camera_exposure_time)
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

            # E-stop guard before energizing. If the operator pressed E-stop
            # between the worker spawn and this point, short-circuit to the
            # normal cleanup path without turning any laser on.
            if self._shell.estop_event.is_set():
                self._hw.stop_lasers()
                self.camera.disarm()
                return

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
                # rule that E-stop is polled in all acquisition
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

                # If the recorder has no data, stop the preview cleanly.
                # The post-loop cleanup below stops the lasers and disarms
                # the camera; breaking here ensures no stale/fake frame is
                # enqueued.
                if cam_images is None:
                    self._shell.sig_message.emit(
                        "Preview camera returned no data — the preview was stopped. "
                        "Check the camera trigger, exposure, and USB "
                        "connection, then restart."
                    )
                    break

                # Sending first (and should be only) image to display port
                frame = cam_images[0]
                self._shell._fs.enqueue_frame(frame)  # ty: ignore[unresolved-attribute]

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
        hw: HardwareManager,
        shell: Controller_MainWindow,
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

            # E-stop guard before energizing. If the operator pressed E-stop
            # between the worker spawn and this point, short-circuit to the
            # normal cleanup path without turning any laser on.
            if self._shell.estop_event.is_set():
                self.siggen.update_etls(left_etl=2.5, right_etl=2.5)
                self._hw.stop_lasers()
                self.camera.disarm()
                return

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
                if not self.acquire_scan():
                    break

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
    the shell's ``ui.*`` from the worker thread.
    """

    finished = Signal()

    def __init__(
        self,
        bundle: DeviceBundle,
        hw: HardwareManager,
        shell: Controller_MainWindow,
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
        # Multi-channel flag pre-sampled on the GUI thread.
        # When True, run() executes the per-channel cycle:
        # select_laser(0) -> acquire_scan -> capture frame1 ->
        # select_laser(1) -> acquire_scan -> capture frame2.
        # When False, the single-channel path runs (back-compat).
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
            self._shell.image_hor_pos_text = (
                self._shell.current_horizontal_position_text  # ty: ignore[unresolved-attribute]
            )
            self._shell.image_ver_pos_text = self._shell.current_vertical_position_text  # ty: ignore[unresolved-attribute]
            self._shell.image_cam_pos_text = self._shell.current_camera_position_text  # ty: ignore[unresolved-attribute]

            # Setting the camera for scan acquisition
            self.camera.arm_scan()

            if self._multi_channel:
                # Multi-channel per-channel cycle: energize L1 -> acquire
                # -> capture frame1 -> energize L2 -> acquire -> capture
                # frame2. select_laser(idx) is the one-laser-energized
                # invariant choke point — it de-energizes the other laser
                # before energizing the target, so only one laser is
                # active at any instant. Do NOT call start_lasers here (it
                # would energize both at once, violating the invariant);
                # select_laser per channel instead. stop_lasers at the end
                # is safety — ensures both off regardless of the last
                # select_laser state.
                #
                # Capture-frame-before-next-acquire pitfall: acquire_scan
                # overwrites self._shell.reconstructed_frame. Capture
                # frame1 immediately after the first acquire_scan (before
                # the second select_laser + acquire_scan overwrites it).
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
                if not self.acquire_scan():
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
                if not self.acquire_scan():
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
                # laser wavelength. reconstructed_frame stays as an alias
                # to the last channel's frame for back-compat with
                # existing single-field consumers (save_panel, display).
                wl1 = int(self._shell.lasers[0].wavelength)
                wl2 = int(self._shell.lasers[1].wavelength)
                self._shell.reconstructed_frames = {}
                if frame1 is not None:
                    self._shell.reconstructed_frames[wl1] = frame1
                if frame2 is not None:
                    self._shell.reconstructed_frames[wl2] = frame2
                    # Alias to the last channel's frame for back-compat.
                    self._shell.reconstructed_frame = frame2

                # Enqueue both tagged frames for saving. The tagged form
                # (channel_idx, frame) is accepted by enqueue_buffer; the
                # single-consumer save worker branches on the tag to pick
                # the per-channel filename list. Only enqueue when saving
                # is allowed and both frames were captured.
                if (
                    self._shell.saving_allowed
                    and frame1 is not None
                    and frame2 is not None
                ):
                    self._shell._fs.enqueue_buffer((0, frame1))
                    self._shell._fs.enqueue_buffer((1, frame2))
            else:
                # Single-channel path (unchanged — back-compat).

                # E-stop guard before energizing. If the operator pressed E-stop
                # between the worker spawn and this point, short-circuit to the
                # normal cleanup path without turning any laser on.
                if self._shell.estop_event.is_set():
                    self.siggen.update_etls(left_etl=2.5, right_etl=2.5)
                    self._hw.stop_lasers()
                    self.camera.disarm()
                    return

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
                if not self.acquire_scan():
                    self.siggen.update_etls(left_etl=2.5, right_etl=2.5)
                    self._hw.stop_lasers()
                    self.camera.disarm()
                    return

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
