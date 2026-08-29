"""FrameSaverController — god-object split collaborator.

Owns the ``FrameSaver`` + ``FrameViewer`` QObject instances and routes the
shell's save/enqueue calls through to them. The ``FrameSaver`` and
``FrameViewer`` QObject classes are DEFINED in this module (moved verbatim
from ``lightsheet/gui/controller.py`` — a behavior-preserving mechanical
relocation). The shell delegates through ``self._fs``.

This is a plain-Python object (NOT a ``QObject``) per the plain-Python collaborator pattern
1: collaborators emit through a shell reference, never declare their own
``Signal``, and never call ``.connect()``. The one exception is the
``FrameSaver.sig_status_message`` → ``shell.updateUi_message_printer``
connection, which is preserved verbatim from the pre-extraction
``hardware_init`` — ``FrameSaver`` runs its save worker on a thread and
its status messages must cross to the GUI thread via the signal/slot
queue (AGENTS.md §11). That connection is made on the owned ``FrameSaver``
instance, not on this collaborator.
"""

from __future__ import annotations

import contextlib
import datetime
import logging
import os
import queue
import threading
import time
from typing import TYPE_CHECKING

import h5py
import numpy as np
from PySide6.QtCore import QObject, QThread, Signal, Slot

from lightsheet.hal.bundle import DeviceBundle

from liom_toolkit.utils.zarr_writer import AnalysisOmeZarrWriter

if TYPE_CHECKING:
    from lightsheet.gui.shell.controller import Controller_MainWindow

logger = logging.getLogger(__name__)


def _position_to_float(value: str | float) -> float:
    """Coerce a motor-position entry to ``float``.

    ``add_motor_parameters`` stores the shell's formatted display strings
    (e.g. ``"99.82 μm"`` from ``units_fixformat``) so the HDF5 per-dataset
    attr path can write them verbatim. The Zarr ``/acquisition/motor``
    datasets need numeric values, so this helper strips the trailing unit
    suffix. A bare numeric string or an already-numeric value is passed
    through. Raises ``ValueError`` if the leading token is not numeric —
    the caller's try/except surfaces it as a save error rather than
    writing a malformed store.
    """
    if isinstance(value, (int, float)):
        return float(value)
    token = str(value).strip().split()[0]
    return float(token)


class FrameSaverWorker(QObject):
    """Worker ``QObject`` for the save loop, affined to a dedicated
    ``QThread`` via ``moveToThread``.

    The save loop body itself stays on ``FrameSaver`` — this worker's
    ``start_saving`` slot invokes the appropriate loop method on the
    worker thread and emits ``sig_finished`` when it returns. The
    ``sig_finished`` → ``thread.quit`` connection ensures the thread's
    event loop exits after the save loop completes, so ``thread.wait()``
    unblocks only after the save loop (HDF5 close OR Zarr finalize) has
    returned on the worker thread (the load-bearing close-ordering
    contract — preserved verbatim for both formats).

    The format branch selects the loop body based on
    ``self._saver.parent.save_format``: ``hdf5`` -> the existing
    ``frame_saver_worker`` (byte-identical); ``zarr`` -> the new
    ``zarr_save_worker`` (ZarrSaver-driven); ``both`` ->
    ``both_save_worker`` (a single consume loop that writes each frame
    to BOTH formats, then finalizes Zarr — the previous two-loop design
    drained the shared queue twice and produced empty HDF5 files). The
    ``try/finally`` + ``sig_finished.emit()`` shape is preserved verbatim
    — the finally gate fires after the branched loop returns, so a Zarr
    finalize completes before the join.
    """

    sig_finished = Signal()

    def __init__(self, saver: "FrameSaver") -> None:
        super().__init__()
        self._saver = saver

    @Slot()
    def start_saving(self) -> None:
        """Run the save loop on the worker thread, then signal completion.

        The format branch is inside the ``try`` so a finalize/write
        failure propagates to the worker's error handler; the
        ``finally: sig_finished.emit()`` gate is UNCHANGED and fires
        after the branched loop returns (the close-ordering contract).
        """
        try:
            fmt = self._saver.parent.save_format
            if fmt == "hdf5":
                self._saver.frame_saver_worker()
            elif fmt == "zarr":
                self._saver.zarr_save_worker()
            elif fmt == "both":
                # Single consume loop writing each frame to BOTH zarr and
                # hdf5, then finalizes zarr. The previous two-loop design
                # (zarr_save_worker then frame_saver_worker) drained the
                # shared single-consumer self.queue twice — the Zarr loop
                # consumed every frame, leaving the HDF5 loop with an
                # empty queue and producing empty (metadata-only) HDF5
                # files. both_save_worker consumes each buffer once and
                # writes it to both formats. Never concurrent — all
                # writes are on this single worker thread, serialized
                # per-frame. sig_finished still emits once in the finally
                # gate after both formats are fully closed/finalized.
                self._saver.both_save_worker()
            else:
                # Default to HDF5 for "tiff" legacy + unknown — matches
                # the controller's save_format parse else branch.
                self._saver.frame_saver_worker()
        finally:
            self.sig_finished.emit()


class FrameViewer(QObject):
    """Class for queueing and displaying images"""

    def __init__(self, parent: Controller_MainWindow, rows: int, columns: int) -> None:
        QObject.__init__(self, parent)
        self.parent = parent
        self.queue = queue.Queue(3)

        # Default frame size is 2000x2000 if no valid size provided
        if rows is not None:
            self.rows = int(rows)
        else:
            self.rows = 2000
        if columns is not None:
            self.columns = int(columns)
        else:
            self.columns = 2000

        # Empty frame
        frame_init = np.zeros((self.rows, self.columns), dtype=np.uint16)
        # Set one pixel to trick histogram initial range (0-2000)
        frame_init[0, 0] = 2000
        # Transpose since setImage is column-major
        frame_init = np.transpose(frame_init)
        # Set initial view
        self.parent.ui.imageView.setImage(frame_init)
        # Live min/max readout (actual pixel range, not the display window).
        # Guarded so a minimal shell stand-in without the helper does not
        # break FrameViewer construction.
        _readout = getattr(self.parent, "_update_levels_readout", None)
        if _readout is not None:
            _readout(frame_init)

    def enqueue_frame(self, frame: np.ndarray) -> None:
        with contextlib.suppress(queue.Full):
            self.queue.put(frame, block=False)

    def updateUi_refresh_view(self) -> None:
        try:
            frame = self.queue.get(block=False)
        except queue.Empty:
            pass
        else:
            # setImage is column-major
            frame = np.transpose(frame)
            self.parent.ui.imageView.setImage(
                frame, autoRange=False, autoLevels=False, autoHistogramRange=False
            )
            # Live min/max readout (actual pixel range, not the display window).
            _readout = getattr(self.parent, "_update_levels_readout", None)
            if _readout is not None:
                _readout(frame)


class FrameSaver(QObject):
    """Class for storing buffers (images) in its queue and saving them
    afterwards in a specified directory in a HDF5 format"""

    sig_status_message = Signal(str)

    def __init__(self, parent: Controller_MainWindow, block_size: int = 1) -> None:
        QObject.__init__(self, parent)
        self.parent = parent
        self.sig_status_message.connect(self.parent.updateUi_message_printer)
        self.file_format = self.parent.save_format

        self.saving_started = False
        self.block_size = block_size
        self.queue = queue.Queue(2 * block_size)

        self.sample_name = ""
        self.number_of_files = 1
        self.filenames_list = []
        self.horizontal_positions_list = []
        self.vertical_positions_list = []
        self.camera_positions_list = []

        # ZarrSaver is a plain-Python sibling collaborator (NOT a
        # QObject) — no QObject parenting needed. Constructed once per
        # FrameSaver; reinit resets it so a per-acquisition format
        # change takes effect without controller reconstruction.
        self._zarr_saver = ZarrSaver(parent)

    def reinit(self, block_size: int) -> None:
        if self.saving_started:
            self.saving_started = False

        # Re-read save_format so a per-acquisition format change (set
        # by the save-panel format radio) takes effect without
        # controller reconstruction.
        self.file_format = self.parent.save_format
        # Reset the ZarrSaver so a per-acquisition format change takes
        # effect (a fresh writer is constructed on the next
        # zarr_save_worker call).
        self._zarr_saver = ZarrSaver(self.parent)

        self.block_size = block_size
        self.queue = queue.Queue(
            2 * block_size
        )  # Set up queue of maxsize 2*block_size (frames)

        self.sample_name = ""
        self.number_of_files = 1
        self.filenames_list = []
        self.horizontal_positions_list = []
        self.vertical_positions_list = []
        self.camera_positions_list = []

    def add_sample_name(self, sample_name: str) -> None:
        """Add to a list the different motor positions"""
        self.sample_name = sample_name

    def add_motor_parameters(
        self,
        current_hor_position_txt: str,
        current_ver_position_txt: str,
        current_cam_position_txt: str,
    ) -> None:
        """Add to a list the different motor positions"""
        self.horizontal_positions_list.append(current_hor_position_txt)
        self.vertical_positions_list.append(current_ver_position_txt)
        self.camera_positions_list.append(current_cam_position_txt)

    def set_files(
        self,
        number_of_files: int,
        files_name: str,
        scan_type: str,
        number_of_datasets: int,
        datasets_name: str,
    ) -> None:
        """Set the number and name of files to save and makes sure the filenames
        are unique in the path to avoid overwrite on other files.

        Plane numbers in filenames are sequential and 1-based (plane_00001,
        plane_00002, ...) so they correspond to the actual plane index in
        the stack — downstream analysis tools that expect sequential
        numbering are not confused by gaps. If a sequential filename
        already exists (e.g. from a previous run in the same directory),
        a ``_vNN`` collision-avoidance suffix is appended so the plane
        number stays meaningful while the filename stays unique.
        """
        self.number_of_files = int(number_of_files)
        self.files_name = str(files_name)
        self.scan_type = str(scan_type)
        self.number_of_datasets = int(number_of_datasets)
        self.datasets_name = str(datasets_name)

        for plane in range(self.number_of_files):
            base = (
                self.files_name
                + "_"
                + scan_type
                + "_plane_"
                + f"{plane + 1:05d}"
            )
            new_filename = base + ".hdf5"
            # Collision avoidance: if the sequential filename already
            # exists, append a _vNN suffix (starting at v2) until a free
            # name is found. The plane number in the base stays sequential
            # so downstream tools can still parse it; only the suffix
            # carries the collision count.
            if os.path.isfile(new_filename):
                version = 2
                while True:
                    candidate = f"{base}_v{version:02d}.hdf5"
                    if not os.path.isfile(candidate):
                        new_filename = candidate
                        break
                    version += 1
            self.filenames_list.append(new_filename)

    # Saving methods

    def enqueue_buffer(self, buffer: np.ndarray) -> None:
        """Put an image in the save queue"""
        self.queue.put(item=buffer, block=True)

    def start_saving(self) -> None:
        """Initiates the save worker on a dedicated QThread.

        The worker ``QObject`` is moved to the thread via ``moveToThread``;
        the thread's ``started`` signal invokes the worker's ``start_saving``
        slot, which runs the save loop on the worker thread. When the save
        loop exits, the worker emits ``sig_finished`` which quits the
        thread's event loop — so ``stop_saving``'s ``wait(10000)`` unblocks
        only after ``h5py.File.close()`` has returned on the worker thread
        (the h5py close-ordering contract).
        """
        self.saving_started = True
        self._saver_thread = QThread()
        self._saver_worker = FrameSaverWorker(self)
        self._saver_worker.moveToThread(self._saver_thread)
        self._saver_thread.started.connect(self._saver_worker.start_saving)
        self._saver_worker.sig_finished.connect(self._saver_thread.quit)
        self._saver_thread.finished.connect(self._saver_worker.deleteLater)
        self._saver_thread.start()

    def _write_laser_metadata(self, outfile: h5py.File) -> None:
        """Write per-laser metadata as h5py.File ROOT attrs once per file.

        For each configured laser (ALL lasers, including inactive ones
        with power=0 / active=False — reproducibility context), writes:
        Laser{i+1} Wavelength (nm), Laser{i+1} Power (mW, canonical),
        Laser{i+1} Max Power (mW), Laser{i+1} Active (bool),
        Laser{i+1} Label (str). Read exclusively from the live
        self.parent.lasers instances — never re-parsed from config.ini
        at save time (fixes the config-drift metadata bug). Uniform mW
        units mean no per-laser unit attr is needed.
        """
        for i, laser in enumerate(self.parent.lasers):
            outfile.attrs[f"Laser{i+1} Wavelength"] = laser.wavelength
            outfile.attrs[f"Laser{i+1} Power"] = laser.power
            outfile.attrs[f"Laser{i+1} Max Power"] = laser.max_power
            outfile.attrs[f"Laser{i+1} Active"] = bool(laser.active)
            outfile.attrs[f"Laser{i+1} Label"] = laser.label

    def _write_acquisition_metadata(self, outfile: h5py.File) -> None:
        """Write motor + scan-param + camera metadata as HDF5 root attrs,
        read from the live IMotor / SigGen / camera instances (completes
        SAV-03 alongside the existing laser attrs).

        This is the motor + scan-param half of the config-drift metadata
        fix — the laser half already shipped. The attrs are read
        exclusively from the live ``self.parent.motors`` /
        ``self.parent.siggen`` / ``self.parent.camera`` instances, never
        re-parsed from config.ini at save time (the frozen DeviceBundle
        guarantees handle stability). The attr-name schema mirrors the
        Zarr ``/acquisition`` group so both formats carry the same
        provenance.

        The motor positions are the CURRENT snapshot at save start (one
        read per axis); the per-plane motor positions are already written
        as dataset attrs in ``frame_saver_worker`` — this adds the
        root-level snapshot, not per-plane.
        """
        motors = self.parent.motors
        outfile.attrs["Horizontal Position"] = motors.horizontal.get_position("mm")
        outfile.attrs["Vertical Position"] = motors.vertical.get_position("mm")
        outfile.attrs["Camera Position"] = motors.camera.get_position("mm")

        sg = self.parent.siggen
        outfile.attrs["Galvo Left Amplitude"] = sg.galvo_left_amplitude
        outfile.attrs["Galvo Right Amplitude"] = sg.galvo_right_amplitude
        outfile.attrs["Galvo Left Offset"] = sg.galvo_left_offset
        outfile.attrs["Galvo Right Offset"] = sg.galvo_right_offset
        outfile.attrs["ETL Left Amplitude"] = sg.etl_left_amplitude
        outfile.attrs["ETL Right Amplitude"] = sg.etl_right_amplitude
        outfile.attrs["ETL Left Offset"] = sg.etl_left_offset
        outfile.attrs["ETL Right Offset"] = sg.etl_right_offset
        # sample_rate is a live instance attribute on the SigGen (the mock
        # sets it at construct time; the real SigGen reads it from config
        # at construct time).
        outfile.attrs["Sample Rate"] = sg.sample_rate

        cam = self.parent.camera
        outfile.attrs["Exposure Time (s)"] = cam.exposure_time
        outfile.attrs["Shutter Mode"] = cam.shutter_mode
        outfile.attrs["Binning X"] = cam.binning_x
        outfile.attrs["Binning Y"] = cam.binning_y
        outfile.attrs["X Size"] = cam.xsize
        outfile.attrs["Y Size"] = cam.ysize

    def frame_saver_worker(self) -> None:
        """Thread for saving 3D arrays (or 2D arrays).
        The number of datasets per file is the number of 2D arrays"""
        for idx in range(len(self.filenames_list)):
            logger.info("File created: %s", self.filenames_list[idx])
            try:
                # Create file
                outfile = h5py.File(self.filenames_list[idx], "a")
                # Write per-laser metadata as file-level root attrs once per
                # file, read from the live list[ILaser] the controller holds
                # (never re-parsed from config.ini — fixes the config-drift
                # metadata bug). All configured lasers are included, even
                # inactive ones (power=0, active=False), for reproducibility.
                self._write_laser_metadata(outfile)
                # Write motor + scan-param + camera root attrs from the
                # live IMotor / SigGen / camera instances (the motor +
                # scan-param half of SAV-03). Same config-drift contract:
                # live instances only, never re-parse config.ini.
                self._write_acquisition_metadata(outfile)
            except Exception as e:
                # A file-creation or metadata-write error (disk full,
                # permission denied, HDF5 corruption at open) must surface
                # to the operator and stop the worker — same IN-04 contract
                # as the per-dataset error handler below. Without this, a
                # failure to open the file would propagate out of the worker
                # thread as an unhandled exception and the operator would
                # see no message, just a silently-dead save worker.
                self.sig_status_message.emit(f"Save error: {e}")
                self.saving_started = False
                break

            counter = 1
            for dataset in range(int(self.number_of_datasets)):
                while True:
                    try:
                        # Retrieve buffer
                        buffer: np.ndarray = self.queue.get(True, 1)
                        if buffer.ndim == 2:
                            buffer = np.expand_dims(
                                buffer, axis=0
                            )  # To consider 2D arrays as a 3D array
                        for frame in range(buffer.shape[0]):  # For each 2D frame
                            # Create dataset
                            path_root = self.datasets_name + f"{counter:03d}"
                            self.dataset = outfile.create_dataset(
                                path_root, data=buffer[frame, :, :]
                            )
                            logger.info(
                                "Dataset %s/%s created: %s",
                                dataset,
                                int(self.number_of_datasets),
                                path_root,
                            )

                            # Add attributes
                            self.dataset.attrs["Sample Name"] = self.sample_name
                            self.dataset.attrs["Date"] = str(datetime.date.today())

                            if buffer.shape[0] == 1:
                                pos_index = dataset + idx * int(self.number_of_datasets)
                            else:
                                pos_index = idx

                            self.dataset.attrs["Horizontal Position"] = (
                                self.horizontal_positions_list[pos_index]
                            )
                            self.dataset.attrs["Vertical Position"] = (
                                self.vertical_positions_list[pos_index]
                            )
                            self.dataset.attrs["Camera Position"] = (
                                self.camera_positions_list[pos_index]
                            )

                            counter += 1
                        break
                    except queue.Empty:
                        # Timeout waiting for a buffer — stop_saving() may
                        # have flipped the flag; if so, exit the inner loop.
                        # Otherwise keep waiting for the next buffer.
                        if not self.saving_started:
                            break
                    except Exception as e:
                        # A non-timeout exception (e.g. h5py write error:
                        # disk full, HDF5 corruption) must not be swallowed
                        # and silently retried — surface it to the operator
                        # and stop saving so we do not keep writing to a
                        # corrupted file. The pre-extraction code caught
                        # all exceptions here and treated them as timeouts,
                        # which let a write error pass silently and the
                        # worker proceeded to the next dataset on a
                        # potentially corrupt file.
                        self.sig_status_message.emit(f"Save error: {e}")
                        self.saving_started = False
                        break
                if not self.saving_started:
                    break
            outfile.close()
            self.sig_status_message.emit("File " + self.filenames_list[idx] + " saved")
            if not self.saving_started:
                break
        logger.info("frame_saver_worker exited (saving_started=%s)", self.saving_started)

    def zarr_save_worker(self) -> None:
        """ZarrSaver-driven save loop body — streams reconstructed frames
        into the L0 OME-Zarr array, then finalizes the pyramid + NGFF
        metadata + /acquisition group on the worker thread BEFORE the
        method returns (so ``sig_finished`` emits after finalize — the
        close-ordering contract).

        Mirrors ``frame_saver_worker``'s queue-consume shape: buffers
        come off ``self.queue`` (2D or 3D), each frame is written via
        ``self._zarr_saver.write_plane`` with the per-plane motor
        positions from ``self.horizontal_positions_list`` etc. The
        store_path is built from ``self.parent.save_directory`` +
        ``self.files_name`` + ``.ome.zarr`` (PLAIN path,
        ``os.path.normpath``); the filename is already sanitized by
        ``save_panel.validate_file_name`` before ``set_files`` is
        called.

        A finalize failure propagates to the worker's try/except (NOT a
        silent HDF5 fallback — the prohibition): the error surfaces via
        ``sig_status_message``, ``saving_started`` flips to False, and
        ``sig_finished`` still emits in the worker's ``finally`` (the
        join completes; the partial zarr store is left on disk for the
        operator to inspect/delete).
        """
        n_planes = self.number_of_files * int(self.number_of_datasets)
        store_path = os.path.normpath(
            os.path.join(self.parent.save_directory, self.files_name + ".ome.zarr")
        )
        try:
            self._zarr_saver.start_stack(store_path, n_planes)
        except Exception as e:
            self.sig_status_message.emit(f"Save error: {e}")
            self.saving_started = False
            return

        z_idx = 0
        pos_index = 0
        try:
            while self.saving_started and z_idx < n_planes:
                try:
                    buffer: np.ndarray = self.queue.get(True, 1)
                except queue.Empty:
                    # stop_saving() may have flipped the flag; if so,
                    # exit the loop. Otherwise keep waiting for the
                    # next buffer.
                    continue

                if buffer.ndim == 2:
                    buffer = np.expand_dims(buffer, axis=0)
                for frame in range(buffer.shape[0]):
                    if z_idx >= n_planes:
                        break
                    # Motor positions: one entry per plane, collected
                    # by add_motor_parameters during the acquisition
                    # loop. The entries are the shell's formatted display
                    # strings (e.g. "99.82 μm"); _position_to_float strips
                    # the unit suffix for the Zarr numeric datasets. Guard
                    # against a short list (defensive).
                    hor = (
                        _position_to_float(self.horizontal_positions_list[pos_index])
                        if pos_index < len(self.horizontal_positions_list)
                        else 0.0
                    )
                    ver = (
                        _position_to_float(self.vertical_positions_list[pos_index])
                        if pos_index < len(self.vertical_positions_list)
                        else 0.0
                    )
                    cam = (
                        _position_to_float(self.camera_positions_list[pos_index])
                        if pos_index < len(self.camera_positions_list)
                        else 0.0
                    )
                    self._zarr_saver.write_plane(
                        z_idx, buffer[frame, :, :], hor, ver, cam
                    )
                    z_idx += 1
                    pos_index += 1
        except Exception as e:
            self.sig_status_message.emit(f"Save error: {e}")
            self.saving_started = False
        else:
            # Finalize builds the pyramid + NGFF metadata + /acquisition
            # group on the worker thread BEFORE the method returns, so
            # sig_finished emits after finalize (the close-ordering
            # contract). A finalize failure propagates to the except
            # above (NOT a silent HDF5 fallback).
            #
            # Gate on z_idx < n_planes, NOT on saving_started: stop_saving()
            # flips saving_started=False on NORMAL completion too (it is the
            # winding-down path for both abort and success). If all planes
            # were written (z_idx >= n_planes) the stack completed and the
            # store MUST be finalized so napari/ome-zarr readers find the
            # multiscales + omero metadata. Only skip finalize when the loop
            # exited early (z_idx < n_planes) — a genuine abort leaving a
            # partial store on disk.
            if z_idx < n_planes:
                logger.info(
                    "zarr_save_worker exiting before finalize "
                    "(z_idx=%d < n_planes=%d) — partial store left on disk",
                    z_idx, n_planes,
                )
            else:
                try:
                    self._zarr_saver.finalize()
                    self.sig_status_message.emit(
                        "Zarr store " + store_path + " saved"
                    )
                except Exception as e:
                    self.sig_status_message.emit(f"Save error: {e}")
                    self.saving_started = False
        logger.info("zarr_save_worker exited (saving_started=%s)", self.saving_started)

    def both_save_worker(self) -> None:
        """Single queue-consume loop writing each frame to BOTH the
        OME-Zarr store and the HDF5 files, then finalizes Zarr.

        Replaces the broken two-loop pattern (``zarr_save_worker`` then
        ``frame_saver_worker``) that drained the shared single-consumer
        ``self.queue`` twice — the Zarr loop consumed every frame, leaving
        the HDF5 loop with an empty queue so it produced metadata-only
        HDF5 files (no image datasets). This method consumes each buffer
        exactly once and writes every frame to both formats from the same
        consume pass.

        Close-ordering contract preserved: the single
        ``sig_finished.emit()`` in ``FrameSaverWorker.start_saving``'s
        finally gate fires AFTER this method returns (all HDF5 files
        closed + Zarr finalized). HDF5 files are opened/closed
        one-at-a-time inside the loop (matching ``frame_saver_worker``'s
        per-file pattern so at most one h5py handle is open); the Zarr
        store is finalized once after the loop. Never concurrent — all
        writes are on the single worker thread, serialized per-frame.

        Error handling mirrors the existing workers: a start_stack
        failure returns early; a per-file open/metadata error breaks the
        file loop; a per-dataset write error surfaces via
        ``sig_status_message`` and flips ``saving_started`` to False so
        the inner loop exits; a finalize failure surfaces the same way.
        ``sig_finished`` still emits in the worker's finally gate.
        """
        n_planes = self.number_of_files * int(self.number_of_datasets)
        store_path = os.path.normpath(
            os.path.join(self.parent.save_directory, self.files_name + ".ome.zarr")
        )
        try:
            self._zarr_saver.start_stack(store_path, n_planes)
        except Exception as e:
            self.sig_status_message.emit(f"Save error: {e}")
            self.saving_started = False
            return

        z_idx = 0
        zarr_pos_index = 0
        try:
            for idx in range(len(self.filenames_list)):
                logger.info("File created: %s", self.filenames_list[idx])
                try:
                    outfile = h5py.File(self.filenames_list[idx], "a")
                    self._write_laser_metadata(outfile)
                    self._write_acquisition_metadata(outfile)
                except Exception as e:
                    self.sig_status_message.emit(f"Save error: {e}")
                    self.saving_started = False
                    break

                counter = 1
                for dataset in range(int(self.number_of_datasets)):
                    while True:
                        try:
                            buffer: np.ndarray = self.queue.get(True, 1)
                            if buffer.ndim == 2:
                                buffer = np.expand_dims(buffer, axis=0)
                            for frame in range(buffer.shape[0]):
                                if z_idx >= n_planes:
                                    break
                                # --- HDF5 write (mirrors frame_saver_worker) ---
                                path_root = self.datasets_name + f"{counter:03d}"
                                self.dataset = outfile.create_dataset(
                                    path_root, data=buffer[frame, :, :]
                                )
                                logger.info(
                                    "Dataset %s/%s created: %s",
                                    dataset,
                                    int(self.number_of_datasets),
                                    path_root,
                                )
                                self.dataset.attrs["Sample Name"] = self.sample_name
                                self.dataset.attrs["Date"] = str(datetime.date.today())

                                if buffer.shape[0] == 1:
                                    h5_pos_index = (
                                        dataset + idx * int(self.number_of_datasets)
                                    )
                                else:
                                    h5_pos_index = idx
                                self.dataset.attrs["Horizontal Position"] = (
                                    self.horizontal_positions_list[h5_pos_index]
                                )
                                self.dataset.attrs["Vertical Position"] = (
                                    self.vertical_positions_list[h5_pos_index]
                                )
                                self.dataset.attrs["Camera Position"] = (
                                    self.camera_positions_list[h5_pos_index]
                                )
                                counter += 1

                                # --- Zarr write (mirrors zarr_save_worker) ---
                                hor = (
                                    _position_to_float(self.horizontal_positions_list[zarr_pos_index])
                                    if zarr_pos_index < len(self.horizontal_positions_list)
                                    else 0.0
                                )
                                ver = (
                                    _position_to_float(self.vertical_positions_list[zarr_pos_index])
                                    if zarr_pos_index < len(self.vertical_positions_list)
                                    else 0.0
                                )
                                cam = (
                                    _position_to_float(self.camera_positions_list[zarr_pos_index])
                                    if zarr_pos_index < len(self.camera_positions_list)
                                    else 0.0
                                )
                                self._zarr_saver.write_plane(
                                    z_idx, buffer[frame, :, :], hor, ver, cam
                                )
                                z_idx += 1
                                zarr_pos_index += 1
                            break
                        except queue.Empty:
                            # stop_saving() may have flipped the flag; if
                            # so, exit the inner loop. Otherwise keep
                            # waiting for the next buffer.
                            if not self.saving_started:
                                break
                        except Exception as e:
                            self.sig_status_message.emit(f"Save error: {e}")
                            self.saving_started = False
                            break
                    if not self.saving_started:
                        break
                outfile.close()
                self.sig_status_message.emit(
                    "File " + self.filenames_list[idx] + " saved"
                )
                if not self.saving_started:
                    break

            # Finalize the Zarr store after all HDF5 files are closed.
            # Gate on z_idx < n_planes, NOT on saving_started: stop_saving()
            # flips saving_started=False on normal completion too. If all
            # planes were written the store MUST be finalized so readers find
            # the multiscales + omero metadata. See zarr_save_worker for the
            # full rationale.
            if z_idx < n_planes:
                logger.info(
                    "both_save_worker exiting before finalize "
                    "(z_idx=%d < n_planes=%d) — partial store left on disk",
                    z_idx, n_planes,
                )
            else:
                try:
                    self._zarr_saver.finalize()
                    self.sig_status_message.emit(
                        "Zarr store " + store_path + " saved"
                    )
                except Exception as e:
                    self.sig_status_message.emit(f"Save error: {e}")
                    self.saving_started = False
        except Exception as e:
            self.sig_status_message.emit(f"Save error: {e}")
            self.saving_started = False
        logger.info("both_save_worker exited (saving_started=%s)", self.saving_started)

    def stop_saving(self) -> None:
        """Signal the save worker to stop and join it with a bounded timeout.

        The flag flip tells the worker to exit its inner loop after the
        current buffer; ``quit()`` + ``wait(10000)`` ensures the HDF5 file
        is fully closed and h5py's native state is quiesced BEFORE the
        caller proceeds to disarm the camera / emit the finished signal /
        reinit for the next run. The ordering chain: ``saving_started``
        flips to False → the worker's inner loop exits →
        ``h5py.File.close()`` returns on the worker thread →
        ``frame_saver_worker()`` returns → ``sig_finished`` emits →
        ``thread.quit()`` → the event loop exits → ``wait(10000)`` unblocks.

        Without the wait, the saver thread outlives the acquisition cleanup
        and a subsequent reinit (which replaces self.queue) or closeEvent
        can race with an in-flight h5py write/close — h5py's native library
        is not thread-safe across concurrent file handles, and the race can
        corrupt HDF5 state and crash the process with a native segfault.
        """
        self.saving_started = False
        worker_thread = getattr(self, "_saver_thread", None)
        if worker_thread is not None and worker_thread.isRunning():
            worker_thread.quit()
            if not worker_thread.wait(10000):
                logger.warning(
                    "frame_saver_thread still alive after 10s wait timeout "
                    "in stop_saving — proceeding anyway (HDF5 state may be "
                    "indeterminate)."
                )


def _wavelength_to_hex(wavelength: int) -> str:
    """Map a laser wavelength (nm) to a 6-char hex color string (no ``#``).

    The mapping covers the wavelengths configured on this rig:
    488 nm -> cyan, 555 nm -> green, 640/647 nm -> red. Any other
    wavelength falls back to white so an unrecognised channel is still
    visible in viewers that honour the omero channel color. The operator
    may override the recorded color at UAT.
    """
    if wavelength == 488:
        return "00FFFF"  # cyan
    if wavelength == 555:
        return "00FF00"  # green
    if wavelength in (640, 647):
        return "FF0000"  # red
    return "FFFFFF"  # white fallback


class ZarrSaver:
    """Plain-Python collaborator that streams reconstructed frames into an
    OME-Zarr store and finalizes the analysis pyramid + NGFF metadata.

    This is NOT a ``QObject``: it mirrors the plain-Python collaborator
    pattern — status messages cross to the GUI thread via
    ``self.parent.sig_message.emit(...)``. It owns a single
    ``liom_toolkit.utils.zarr_writer.AnalysisOmeZarrWriter`` per stack
    (constructed in ``start_stack``); ``finalize`` builds the multiscale
    pyramid out-of-core via Dask and writes the OME-NGFF metadata, then
    the ``/acquisition`` group is appended via the writer's public
    ``root`` handle. ``finalize_with_resolutions`` is called exactly once
    per writer (re-calling raises ``RuntimeError``); the ``_finalized``
    flag guards against a double-finalize from the worker's error path.
    """

    def __init__(self, shell: "Controller_MainWindow") -> None:
        self.parent = shell
        self._writer: AnalysisOmeZarrWriter | None = None
        self.saving_started = False
        self._finalized = False
        self._horizontal_positions: list[float] = []
        self._vertical_positions: list[float] = []
        self._camera_positions: list[float] = []

    def start_stack(self, store_path: str, n_planes: int) -> None:
        """Construct the OME-Zarr writer for a new stack.

        ``store_path`` is a PLAIN filesystem path (NOT ``file://`` — the
        writer raises ``ValueError`` on a ``file://`` prefix). The path
        is asserted to live inside the operator-selected save directory
        so a path-traversal attempt cannot write outside it. The L0
        array is shaped ``(1, n_planes, ysize, xsize)`` — a 4D
        single-channel store — and chunked one plane per chunk so each
        streaming write touches exactly one chunk (peak RAM = one frame
        + one chunk).
        """
        # Path-traversal guard: the resolved store_path must be inside
        # the operator-selected save directory.
        save_dir = os.path.normpath(self.parent.save_directory)
        resolved = os.path.normpath(store_path)
        try:
            common = os.path.commonpath([save_dir, os.path.dirname(resolved)])
        except ValueError:
            common = ""
        if common != save_dir:
            msg = f"Zarr store_path {resolved!r} is outside save directory {save_dir!r}"
            self.parent.sig_message.emit(msg)
            raise ValueError(msg)

        cam = self.parent.camera
        shape = (1, int(n_planes), int(cam.ysize), int(cam.xsize))
        chunk_shape = (1, 1, int(cam.ysize), int(cam.xsize))
        self._writer = AnalysisOmeZarrWriter(
            store_path=resolved,
            shape=shape,
            chunk_shape=chunk_shape,
            dtype=np.uint16,
            overwrite=True,
            unit="micrometer",
        )
        self.saving_started = True
        self._finalized = False
        self._horizontal_positions = []
        self._vertical_positions = []
        self._camera_positions = []

    def write_plane(
        self,
        z_idx: int,
        frame: np.ndarray,
        hor_pos: float,
        ver_pos: float,
        cam_pos: float,
    ) -> None:
        """Stream one reconstructed 2D frame into the L0 array.

        The writer indexes a 4D array ``(c, z, y, x)``; the per-plane
        frame is 2D ``(y, x)`` so a channel axis is prepended for the
        assignment. The motor positions are recorded for the
        ``/acquisition`` group written at finalize time.
        """
        if self._writer is None:
            raise RuntimeError("ZarrSaver.write_plane called before start_stack")
        self._writer[:, z_idx, :, :] = frame[np.newaxis, :, :]
        self._horizontal_positions.append(float(hor_pos))
        self._vertical_positions.append(float(ver_pos))
        self._camera_positions.append(float(cam_pos))

    def _build_omero_channels(self, lasers) -> list[dict]:
        """Build the omero.channels list from the live ``list[ILaser]``.

        Every configured laser is included (active or not) so the saved
        metadata carries the full acquisition provenance. Each channel
        dict carries ``label`` / ``color`` / ``active`` / ``wavelength``
        — the color is a 6-char hex string with no ``#`` prefix.
        """
        channels: list[dict] = []
        for laser in lasers:
            channels.append(
                {
                    "label": laser.label,
                    "color": _wavelength_to_hex(laser.wavelength),
                    "active": bool(laser.active),
                    "wavelength": int(laser.wavelength),
                }
            )
        return channels

    def _write_acquisition_group(self) -> None:
        """Write the ``/acquisition`` group (per-plane motor positions +
        scan params) via the writer's public ``root`` handle.

        Called AFTER ``finalize_with_resolutions`` so the multiscale
        pyramid + NGFF metadata are already on disk; the acquisition
        group is appended as a sibling group under root. Per-plane
        motor positions are 1D datasets under ``/acquisition/motor/``;
        scan params (galvo/ETL amplitudes+offsets, exposure, sample
        rate, shutter mode, binning) are group attrs read from the live
        HAL instances.
        """
        if self._writer is None:
            raise RuntimeError("ZarrSaver._write_acquisition_group called with no writer")
        root = self._writer.root
        grp = root.create_group("acquisition")
        motor = grp.create_group("motor")
        motor.create_array(
            "horizontal", data=np.array(self._horizontal_positions, dtype=float)
        )
        motor.create_array(
            "vertical", data=np.array(self._vertical_positions, dtype=float)
        )
        motor.create_array(
            "camera", data=np.array(self._camera_positions, dtype=float)
        )

        siggen = self.parent.siggen
        cam = self.parent.camera
        grp.attrs["galvo_left_amplitude"] = siggen.galvo_left_amplitude
        grp.attrs["galvo_right_amplitude"] = siggen.galvo_right_amplitude
        grp.attrs["galvo_left_offset"] = siggen.galvo_left_offset
        grp.attrs["galvo_right_offset"] = siggen.galvo_right_offset
        grp.attrs["etl_left_amplitude"] = siggen.etl_left_amplitude
        grp.attrs["etl_right_amplitude"] = siggen.etl_right_amplitude
        grp.attrs["etl_left_offset"] = siggen.etl_left_offset
        grp.attrs["etl_right_offset"] = siggen.etl_right_offset
        grp.attrs["exposure_time_s"] = cam.exposure_time
        grp.attrs["shutter_mode"] = cam.shutter_mode
        # sample_rate is a live instance attribute on the SigGen (the
        # mock sets it at construct time; the real SigGen reads it from
        # config at construct time).
        grp.attrs["sample_rate"] = siggen.sample_rate
        grp.attrs["binning_x"] = cam.binning_x
        grp.attrs["binning_y"] = cam.binning_y

    def finalize(self) -> None:
        """Build the analysis pyramid + NGFF metadata, then the
        ``/acquisition`` group.

        ``finalize_with_resolutions`` is called exactly once per writer
        (re-calling raises ``RuntimeError``); the ``_finalized`` flag
        guards against a double-finalize from the worker's error path.
        The call is timed so the operator can see how long the pyramid
        build took — if the ``frame_saver_thread still alive after 10s
        wait timeout`` warning fires on the rig, the duration log shows
        whether the pyramid build was the cause.
        """
        if self._writer is None:
            raise RuntimeError("ZarrSaver.finalize called before start_stack")
        if self._finalized:
            raise RuntimeError("ZarrSaver.finalize called twice")

        cam = self.parent.camera
        # The ICameraCore contract declares binning_x/binning_y as int
        # (not int | None), and both MockCamera and the real Camera
        # default to 1 (never None). The previous defensive None-guard
        # was dead code given the int contract — removed so the type
        # annotation is authoritative.
        binning_x = int(cam.binning_x)
        binning_y = int(cam.binning_y)
        base_res = (abs(self.parent.stack_step), 6.5 * binning_x, 6.5 * binning_y)
        logger.info("ZarrSaver.finalize base_res=%s", base_res)
        omero_channels = self._build_omero_channels(self.parent.lasers)

        t0 = time.time()
        self._writer.finalize_with_resolutions(
            base_res=base_res,
            target_resolutions_um=(10, 25, 50, 100),
            make_isotropic=True,
            omero_channels=omero_channels,
        )
        logger.info(
            "Zarr finalize_with_resolutions took %.2fs", time.time() - t0
        )
        self._write_acquisition_group()
        self._finalized = True
        self.saving_started = False


class FrameSaverController:
    """Owns the FrameSaver + FrameViewer QObjects and routes save/enqueue
    calls to them.

    The shell delegates through ``self._fs``. The wrapped QObjects are
    parented to the shell (their QObject parent), so they are destroyed
    with the shell and their thread-affinity is the GUI thread.
    """

    def __init__(self, bundle: DeviceBundle, shell: "Controller_MainWindow") -> None:
        self._shell = shell
        # FrameViewer is sized from the bundle's camera dimensions — the
        # same rows/columns the pre-extraction hardware_init passed.
        self.frame_viewer = FrameViewer(
            shell, rows=bundle.camera.ysize, columns=bundle.camera.xsize
        )
        # FrameSaver is parented to the shell. Its sig_status_message
        # signal is wired to shell.updateUi_message_printer inside
        # FrameSaver.__init__ (self.parent.updateUi_message_printer) —
        # that wiring is preserved verbatim by passing the shell as the
        # parent. Do NOT re-connect here: Qt allows duplicate
        # connections and a second connect would double-fire the slot.
        self.frame_saver = FrameSaver(shell)

    # -- pass-through methods to the wrapped FrameSaver --------------------
    # These route the shell's save calls exactly as the pre-extraction
    # call sites invoked them directly on self.frame_saver.

    def reinit(self, block_size: int) -> None:
        self.frame_saver.reinit(block_size)

    def add_sample_name(self, sample_name: str) -> None:
        self.frame_saver.add_sample_name(sample_name)

    def add_motor_parameters(
        self,
        current_hor_position_txt: str,
        current_ver_position_txt: str,
        current_cam_position_txt: str,
    ) -> None:
        self.frame_saver.add_motor_parameters(
            current_hor_position_txt,
            current_ver_position_txt,
            current_cam_position_txt,
        )

    def set_files(
        self,
        number_of_files: int,
        files_name: str,
        scan_type: str,
        number_of_datasets: int,
        datasets_name: str,
    ) -> None:
        self.frame_saver.set_files(
            number_of_files,
            files_name,
            scan_type,
            number_of_datasets,
            datasets_name,
        )

    def enqueue_buffer(self, buffer: np.ndarray) -> None:
        self.frame_saver.enqueue_buffer(buffer)

    def start_saving(self) -> None:
        self.frame_saver.start_saving()

    def stop_saving(self) -> None:
        self.frame_saver.stop_saving()

    # -- pass-through to the wrapped FrameViewer ---------------------------

    def enqueue_frame(self, frame: np.ndarray) -> None:
        self.frame_viewer.enqueue_frame(frame)

    # -- pure-numpy image reconstruction -----------------------------------
    # Moved verbatim from Controller_MainWindow. These are pure functions
    # of the buffer array (they read only buffer.shape, no shell/HAL/Qt
    # state), so they need no shell reference. Kept as instance methods
    # to match the pre-extraction call shape (self._fs.crop_buffer(buf)).

    def crop_buffer(self, buffer: np.ndarray) -> np.ndarray:
        """Crops each frame of a buffer with 20% frame-to-frame overlap"""

        image_xsize = buffer.shape[2]
        image_ysize = buffer.shape[1]
        tile_count = buffer.shape[0]

        if tile_count == 1:
            cropped_buffer = buffer
        else:
            tile_width = int(image_xsize / tile_count)
            tile_width_overlap = int(tile_width * 0.2)

            # Initializing empty cropped buffer
            cropped_buffer = np.zeros(
                (tile_count, image_ysize, tile_width + (2 * tile_width_overlap)),
                np.uint16,
            )

            # Crop with overlap
            for frame in range(tile_count):
                # NOTE - disabled intensity normalization
                # # Uniformize frame intensities
                # average = np.average(buffer[frame,0:100,:]) #Average the  first rows
                # if frame == 0:
                #     reference_average = average
                # else:
                #     average_ratio = reference_average/average
                #     # buffer[frame,:,:] = buffer[frame,:,:] * average_ratio

                first_column = int(frame * tile_width - tile_width_overlap)
                next_first_column = int(
                    first_column + tile_width + (2 * tile_width_overlap)
                )
                if frame == 0:  # For the first column step
                    cropped_buffer[frame, :, tile_width_overlap:] = buffer[
                        frame, :, 0 : tile_width + tile_width_overlap
                    ]
                elif (
                    frame == tile_count - 1
                ):  # For the last column step (may be different than the others...)
                    last_column_step = int(image_xsize - first_column)
                    cropped_buffer[frame, :, 0:last_column_step] = buffer[
                        frame, :, first_column:
                    ]
                else:
                    cropped_buffer[frame, :, :] = buffer[
                        frame, :, first_column:next_first_column
                    ]
        return cropped_buffer

    def reconstruct_frame(self, buffer: np.ndarray) -> np.ndarray:
        """Reconstructs frame from buffer"""

        image_xsize = buffer.shape[2]
        image_ysize = buffer.shape[1]
        tile_count = buffer.shape[0]

        # Initializing empty frame
        reconstructed_frame = np.zeros((image_ysize, image_xsize), np.uint16)

        # Crops each frame of a buffer with no overlap and merge
        if tile_count == 1:
            reconstructed_frame = buffer[0, :, :]
        else:
            tile_width = int(image_xsize / tile_count)

            for frame in range(tile_count):
                # NOTE - disabled intensity normalization
                # # Uniformize frame intensities
                # average = np.average(buffer[frame,0:100,:]) #Average the  first rows
                # if frame == 0:
                #     reference_average = average
                # else:
                #     average_ratio = reference_average/average
                #     #print('average_ratio:'+str(average_ratio))
                #     # buffer[frame,:,:] = buffer[frame,:,:] * average_ratio

                # Reconstruct frame
                first_column = frame * tile_width
                next_first_column = first_column + tile_width
                if (
                    frame == tile_count - 1
                ):  # For the last column step (may be different than the others...)
                    reconstructed_frame[:, first_column:] = buffer[
                        frame, :, first_column:
                    ]
                else:
                    reconstructed_frame[:, first_column:next_first_column] = buffer[
                        frame, :, first_column:next_first_column
                    ]
        return reconstructed_frame

    def reconstruct_frame_linear_blend(self, buffer: np.ndarray) -> np.ndarray:
        """Reconstructs frame from buffer using linear blend over 20% overlap"""

        image_xsize = buffer.shape[2]
        image_ysize = buffer.shape[1]
        tile_count = buffer.shape[0]

        # Initializing empty output frame
        reconstructed_frame = np.zeros((image_ysize, image_xsize), np.uint16)

        if tile_count == 1:
            reconstructed_frame = buffer[0, :, :]
        else:
            # Crops each frame of a buffer with 20% overlap for futher frame reconstruction  # noqa: E501
            tile_width = int(image_xsize / tile_count)
            tile_width_overlap = int(tile_width * 0.2)

            # Initializing empty cropped buffer
            cropped_buffer = np.zeros(
                (tile_count, image_ysize, tile_width + (2 * tile_width_overlap)),
                np.uint16,
            )

            # Crop with overlap
            for frame in range(tile_count):
                first_column = int(frame * tile_width - tile_width_overlap)
                next_first_column = int(
                    first_column + tile_width + (2 * tile_width_overlap)
                )
                if frame == 0:  # For the first column step
                    cropped_buffer[frame, :, tile_width_overlap:] = buffer[
                        frame, :, 0 : tile_width + tile_width_overlap
                    ]
                elif (
                    frame == tile_count - 1
                ):  # For the last column step (may be different than the others...)
                    last_column_step = int(image_xsize - first_column)
                    cropped_buffer[frame, :, 0:last_column_step] = buffer[
                        frame, :, first_column:
                    ]
                else:
                    cropped_buffer[frame, :, :] = buffer[
                        frame, :, first_column:next_first_column
                    ]

            # Reconstruct frame with linear blend for overlapping region
            weight_step = 1 / (2 * tile_width_overlap)

            for frame in range(tile_count):
                first_center_column = int(frame * tile_width + tile_width_overlap)
                last_center_column = int((frame + 1) * tile_width - tile_width_overlap)
                previous_last_center_column = int(
                    frame * tile_width - tile_width_overlap
                )

                if frame == 0:  # For the first column step
                    reconstructed_frame[:, 0:last_center_column] = cropped_buffer[
                        frame, :, tile_width_overlap:tile_width
                    ]
                else:
                    for column in range(2 * tile_width_overlap):
                        frame_column = column + previous_last_center_column
                        last_buffer_column = column + tile_width
                        buffer_weight = column * weight_step
                        last_buffer_weight = 1 - column * weight_step
                        reconstructed_frame[:, frame_column] = (
                            buffer_weight * cropped_buffer[frame, :, column]
                            + last_buffer_weight
                            * cropped_buffer[(frame - 1), :, last_buffer_column]
                        )
                    if (
                        frame == tile_count - 1
                    ):  # For the last column step (may be different than the others...)
                        last_column_step = int(image_xsize - first_center_column)
                        reconstructed_frame[:, first_center_column:] = cropped_buffer[
                            frame,
                            :,
                            (2 * tile_width_overlap) : (2 * tile_width_overlap)
                            + last_column_step,
                        ]
                    else:
                        reconstructed_frame[
                            :, first_center_column:last_center_column
                        ] = cropped_buffer[
                            frame, :, (2 * tile_width_overlap) : tile_width
                        ]
        return reconstructed_frame
