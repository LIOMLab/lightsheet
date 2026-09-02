"""Shared scan lifecycle for the acquisition worker QObjects.

This module owns the ``_AcquireScanMixin`` helper used by LiveWorker,
SingleWorker, and StackWorker to run one galvo/ETL/camera scan, reconstruct
the frame, and handle recorder/DAQ timeouts.
"""

from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class _AcquireScanMixin:
    """Shared ``acquire_scan`` helper for the worker QObjects.

    Relocated from ``AcquisitionCoordinator.acquire_scan`` with two
    attribute-access changes: the save-description and stitch-blend reads
    become ``self._save_description`` / ``self._save_stitch_blend``
    (pre-sampled on the GUI thread and passed as constructor args, so the
    worker thread never reaches into the shell's UI widgets).

    ``SingleWorker`` and ``StackWorker`` both inherit this mixin so the
    scan-acquisition body stays in one place.
    """

    def acquire_scan(self) -> bool:
        """
        Generate scan tasks using previously computed waveforms and
        acquire a single reconstructed frame.

        Returns ``True`` only after the frame is reconstructed and queued
        for display. Returns ``False`` after any pre-frame or no-data
        abort, after deleting the recorder/scanner and disarming the
        camera so the caller can stop lasers and finish cleanly.
        """

        # Store metadata about buffer to be acquired
        self._shell.buffer_metadata_general = {}  # ty: ignore[unresolved-attribute]
        self._shell.buffer_metadata_general["Date"] = str(datetime.date.today())  # ty: ignore[unresolved-attribute]
        self._shell.buffer_metadata_general["Sample Name"] = str(self._save_description)  # ty: ignore[unresolved-attribute]

        self._shell.buffer_metadata_waveforms = {}  # ty: ignore[unresolved-attribute]
        self._shell.buffer_metadata_waveforms = self.siggen.waveform_metadata  # ty: ignore[unresolved-attribute]

        self._shell.buffer_metadata_motors = {}  # ty: ignore[unresolved-attribute]
        self._shell.buffer_metadata_lasers = {}  # ty: ignore[unresolved-attribute]
        self._shell.buffer_metadata_camera = {}  # ty: ignore[unresolved-attribute]

        # Number of images to be acquired from the camera
        number_of_images = self.siggen.waveform_cycles  # ty: ignore[unresolved-attribute]

        # Creating acquisition tasks
        # Clear any error left over from a previous acquisition so the check
        # below reflects this create_scanner() call only.
        self.siggen.error = 0  # ty: ignore[unresolved-attribute]
        self.siggen.create_scanner()  # ty: ignore[unresolved-attribute]
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
        if self.siggen.error:  # ty: ignore[unresolved-attribute]
            self._shell.sig_message.emit(
                f"Scan task creation failed — the acquisition was aborted before the camera was triggered. Check the NI DAQ connection (Dev1). Cause: {self.siggen.error_message}"  # noqa: E501
            )
            logger.warning("SigGen create_scanner failed during acquire_scan")
            self.siggen.delete_scanner()
            self.camera.disarm()
            return False

        # Prime the camera recorder before we start the acquisition taks
        self.camera.start_recorder(number_of_images)  # ty: ignore[unresolved-attribute]
        self.siggen.start_scanner()  # ty: ignore[unresolved-attribute]

        # Monitor completion of acquisition tasks and camera recorder
        self.camera.monitor_recorder(number_of_images)  # ty: ignore[unresolved-attribute]
        self.siggen.monitor_scanner()  # ty: ignore[unresolved-attribute]

        # Stop tasks and recorder
        self.camera.stop_recorder()  # ty: ignore[unresolved-attribute]
        self.siggen.stop_scanner()  # ty: ignore[unresolved-attribute]

        # Abort on recorder timeout — never copy zero-filled frames to disk.
        # The recorder timeout flag is set by monitor_recorder when the camera
        # did not return the expected frames in time. Returning here before
        # copy_recorder_images ensures a timed-out plane is not mistaken for
        # a real (dark) frame on disk.
        if self.camera.recorder_timeout_status:  # ty: ignore[unresolved-attribute]
            self._shell.sig_message.emit(  # ty: ignore[unresolved-attribute]
                "Camera timeout — plane was not recorded (camera did not return frames in time). "  # noqa: E501
                "The acquisition was aborted. Reduce the number of images per plane or check the camera USB connection, then restart the run."  # noqa: E501
            )
            logger.warning("Camera recorder timeout during acquire_scan")
            self.camera.delete_recorder()  # ty: ignore[unresolved-attribute]
            # Delete the DAQ scanner task. The scanner was already stopped
            # above (before the timeout check) — NI-DAQmx Task.stop() is
            # idempotent, so a second stop_scanner() here was redundant and
            # is omitted. delete_scanner() tears down the task so the DAQ
            # hardware is left in a consistent state.
            self.siggen.delete_scanner()  # ty: ignore[unresolved-attribute]
            # Disarm the camera before returning. Camera.disarm() is
            # idempotent (it only issues the SDK stop-recording call when
            # the camera reports recording state == 'on'), so calling it
            # here and again from a caller that reaches its own disarm()
            # is safe. This ensures a camera left mid-timeout is always
            # disarmed before any worker that might die afterward gets a
            # chance to skip its own cleanup.
            self.camera.disarm()  # ty: ignore[unresolved-attribute]
            return False

        # Recover images from the recorder
        # Note: Images must be recovered before deleting the recorder
        recorded_images = self.camera.copy_recorder_images(number_of_images)  # ty: ignore[unresolved-attribute]

        # If the recorder has no data, make the absence explicit instead of
        # treating a synthetic zero-filled array as a real frame. Clean up
        # the recorder and scanner and disarm before returning so the caller
        # can stop lasers and emit finished.
        if recorded_images is None:
            self._shell.sig_message.emit(  # ty: ignore[unresolved-attribute]
                "Camera recorder returned no data — the acquisition was "
                "aborted before a frame could be reconstructed. "
                "Check the camera trigger, exposure, and USB connection, "
                "then restart the run."
            )
            logger.warning("Camera recorder returned no data during acquire_scan")
            self.camera.delete_recorder()  # ty: ignore[unresolved-attribute]
            self.siggen.delete_scanner()  # ty: ignore[unresolved-attribute]
            self.camera.disarm()  # ty: ignore[unresolved-attribute]
            return False

        self._shell.buffer = np.asarray(recorded_images)  # ty: ignore[unresolved-attribute]

        # Delete tasks and recorder
        self.camera.delete_recorder()  # ty: ignore[unresolved-attribute]
        self.siggen.delete_scanner()  # ty: ignore[unresolved-attribute]

        # Frame reconstruction options
        if self._save_stitch_blend:  # ty: ignore[unresolved-attribute]
            self._shell.reconstructed_frame = (  # ty: ignore[unresolved-attribute]
                self._shell._fs.reconstruct_frame_linear_blend(self._shell.buffer)  # ty: ignore[unresolved-attribute]
            )
        else:
            self._shell.reconstructed_frame = self._shell._fs.reconstruct_frame(  # ty: ignore[unresolved-attribute]
                self._shell.buffer  # ty: ignore[unresolved-attribute]
            )

        # Send reconstructed frame to display port
        self._shell._fs.enqueue_frame(self._shell.reconstructed_frame)  # ty: ignore[unresolved-attribute]
        return True


