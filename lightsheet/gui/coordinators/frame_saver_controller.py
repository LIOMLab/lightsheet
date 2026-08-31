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
import time
from typing import TYPE_CHECKING

import h5py
import numpy as np
import zarr
from liom_toolkit.utils.zarr_writer import AnalysisOmeZarrWriter
from PySide6.QtCore import QObject, QThread, Signal, Slot

from lightsheet.hal.bundle import DeviceBundle
from lightsheet.wavelength_color import wavelength_to_hex

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

    def __init__(self, saver: FrameSaver) -> None:
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
        # Set one pixel to trick histogram initial range (0-20000)
        frame_init[0, 0] = 20000
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
        # Per-channel filename lists. set_files always populates this
        # with one list per channel — single-channel mode has one
        # channel list (and filenames_list mirrors filenames_lists[0]
        # so the single-channel frame_saver_worker path is unchanged);
        # multi-channel mode has one list per channel. The
        # wavelengths=None back-compat branch is retired.
        self.filenames_lists: list[list[str]] = []
        self.horizontal_positions_list = []
        self.vertical_positions_list = []
        self.camera_positions_list = []

        # ZarrSaver is a plain-Python sibling collaborator (NOT a
        # QObject) — no QObject parenting needed. Constructed once per
        # FrameSaver; reinit resets it so a per-acquisition format
        # change takes effect without controller reconstruction.
        self._zarr_saver = ZarrSaver(parent)

        # Adaptive trajectory samples (schema-a). Cleared in reinit.
        # Populated by record_adaptive_sample() during the per-plane
        # loop; written to HDF5 /adaptive_trajectory by
        # _write_adaptive_hdf5() before file close, and to Zarr
        # /acquisition/adaptive by ZarrSaver._write_adaptive_group()
        # during finalize.
        self.adaptive_trajectory: list = []
        self._adaptive_enabled: bool = False
        # Frozen AdaptiveConfig (schema-a bounds + gains). Stored when
        # configure_adaptive(enabled, config=...) is called so the
        # HDF5 / Zarr writers can publish the full config attrs
        # alongside the per-plane trajectory. None in fixed mode.
        self._adaptive_config: object | None = None

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
        self.filenames_lists: list[list[str]] = []
        self.horizontal_positions_list = []
        self.vertical_positions_list = []
        self.camera_positions_list = []
        # Clear adaptive trajectory state so a re-run does not carry
        # over the previous run's samples.
        self.adaptive_trajectory = []
        self._adaptive_enabled = False
        self._adaptive_config = None

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
        wavelengths: list[int] | None = None,
    ) -> None:
        """Set the number and name of files to save and makes sure the filenames
        are unique in the path to avoid overwrite on other files.

        Filename convention (compact, aligned with the Zarr store name
        ``<files_name>.ome.zarr``): ``<files_name>_<wavelength>nm`` with
        a per-channel sequential counter — NO suffix on the first file,
        then ``_01``, ``_02``, ... (2-digit, width scales with the file
        count so lexicographic sort is stable). The scan_type segment is
        NOT included in the filename (it stays available as
        ``self.scan_type`` for metadata). The old ``_plane_00001`` and
        ``_stack`` segments are dropped — the former was always ``00001``
        for stitch (one file per channel) and redundant with the dataset
        name inside the file for crop/full, and the latter duplicated the
        Zarr store name's role. Collision avoidance: if a candidate name
        already exists on disk, the counter increments past it until a
        free name is found (so a re-run in the same directory produces
        ``_01``, ``_02``, ... instead of overwriting).

        ``wavelengths`` is required — every caller passes a non-None
        list. Multi-channel callers pass ``[wl1, wl2]``;
        single-channel callers pass ``[active_wavelength]``. The
        ``wavelengths=None`` back-compat branch is retired: passing
        ``None`` raises ``ValueError`` so a stale caller that forgets
        to pass wavelengths fails loudly instead of producing an
        unsuffixed file.

        ``self.filenames_lists`` is built as a list of lists — one per
        channel, each with ``number_of_files`` entries — where each
        filename ends in ``_{wavelength}nm.hdf5`` (plus the sequential
        suffix for files after the first). The wavelength values are
        read from the live ``ILaser`` instance by the caller and passed
        in here; they are never hardcoded inside this method. The
        collision-avoidance counter runs independently per channel.

        When there is exactly one channel (single-channel mode),
        ``self.filenames_list`` (singular) is also populated from
        ``filenames_lists[0]`` so the single-channel
        ``frame_saver_worker`` (which reads ``filenames_list``, not
        ``filenames_lists``) is byte-identical except for the filename
        suffix.
        """
        if wavelengths is None:
            raise ValueError(
                "set_files requires a non-None wavelengths list — the "
                "single-channel None branch is retired. Pass "
                "[active_wavelength] for single-channel or [wl1, wl2] "
                "for multi-channel."
            )

        self.number_of_files = int(number_of_files)
        self.files_name = str(files_name)
        self.scan_type = str(scan_type)
        self.number_of_datasets = int(number_of_datasets)
        self.datasets_name = str(datasets_name)

        # Sequential-suffix width: 2-digit minimum, scales with the file
        # count so lexicographic sort stays stable (e.g. 100 files →
        # 3-digit _001.._100). The first file in each channel has NO
        # suffix; subsequent files get _01, _02, ... Collision avoidance
        # increments the counter past any name that already exists on
        # disk, so a re-run in the same directory shifts to _01, _02, ...
        # instead of overwriting.
        width = max(2, len(str(self.number_of_files)))

        # Build one filename list per channel, each with the
        # _{wavelength}nm suffix and the per-channel sequential counter.
        self.filenames_lists = []
        for wl in wavelengths:
            channel_list: list[str] = []
            counter = 0  # 0 → no suffix; 1 → _01; 2 → _02; ...
            for _plane in range(self.number_of_files):
                base = self.files_name + f"_{wl}nm"
                if counter == 0:
                    candidate = base + ".hdf5"
                else:
                    candidate = f"{base}_{counter:0{width}d}.hdf5"
                # Collision avoidance: bump the counter until the name is
                # free (and recompute the suffix once counter > 0).
                while os.path.isfile(candidate):
                    counter += 1
                    candidate = f"{base}_{counter:0{width}d}.hdf5"
                channel_list.append(candidate)
                counter += 1
            self.filenames_lists.append(channel_list)

        # Single-channel back-compat: populate filenames_list (singular)
        # from filenames_lists[0] so the single-channel frame_saver_worker
        # (which reads filenames_list, not filenames_lists) is
        # byte-identical except for the filename suffix.
        if len(self.filenames_lists) == 1:
            self.filenames_list = list(self.filenames_lists[0])
        else:
            # Multi-channel: clear filenames_list so the multi-channel
            # worker branch (filenames_lists populated) is taken.
            self.filenames_list = []

    # Saving methods

    def enqueue_buffer(self, buffer: np.ndarray | tuple[int, np.ndarray]) -> None:
        """Put an image in the save queue.

        Accepts either a bare ``np.ndarray`` (the existing single-channel
        form — back-compat) or a ``(channel_idx, frame)`` tuple (the
        multi-channel channel-tagged form). The single-consumer save
        workers (``frame_saver_worker`` / ``zarr_save_worker`` /
        ``both_save_worker``) branch on the tag in a later plan; this
        method only makes the queue accept the tagged form without
        raising, so the multi-channel producer (``SingleWorker.run`` /
        ``StackWorker.run``) can enqueue per-channel frames now.
        """
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
            outfile.attrs[f"Laser{i + 1} Wavelength"] = laser.wavelength
            outfile.attrs[f"Laser{i + 1} Power"] = laser.power
            outfile.attrs[f"Laser{i + 1} Max Power"] = laser.max_power
            outfile.attrs[f"Laser{i + 1} Active"] = bool(laser.active)
            outfile.attrs[f"Laser{i + 1} Label"] = laser.label

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

    def configure_adaptive(self, enabled: bool, config: object | None = None) -> None:
        """Configure the adaptive trajectory recorder for this acquisition.

        When ``enabled`` is True, the per-plane loop calls
        ``record_adaptive_sample`` once per main plane, and the HDF5
        writer writes the ``/adaptive_trajectory`` group before file
        close while the Zarr writer writes ``/acquisition/adaptive``
        during finalize. When False, no trajectory is recorded or
        written and no adaptive group is created in either format.

        ``config`` is the frozen ``AdaptiveConfig`` whose bounds + gains
        are published as group attrs alongside the per-plane trajectory
        (schema-a reproducibility contract). It may be omitted in fixed
        mode (``enabled=False``); when ``enabled=True`` the config attrs
        are required so the saved trajectory is self-describing.
        """
        self._adaptive_enabled = bool(enabled)
        self.adaptive_trajectory = []
        self._adaptive_config = config if enabled else None

    def record_adaptive_sample(self, sample: object) -> None:
        """Append a frozen AdaptiveSample to the trajectory list.

        Called by the StackWorker per main plane, before the frame is
        enqueued for saving. The sample is logged and held for the
        HDF5 writer (``_write_adaptive_hdf5``) which serializes the
        full trajectory before file close.
        """
        if not self._adaptive_enabled:
            return
        self.adaptive_trajectory.append(sample)
        logger.info(
            "adaptive sample: plane=%d exposure=%.4fs power=(%.1f,%.1f) "
            "cva=%s reacquired=%s fallback=%s",
            sample.plane_index,
            sample.exposure_s,
            sample.laser_power_mw[0],
            sample.laser_power_mw[1],
            sample.control_variable_active,
            sample.reacquired,
            sample.power_fallback,
        )

    def _adaptive_config_attrs(self) -> dict:
        """Build the schema-a AdaptiveConfig attrs dict from the frozen
        ``self._adaptive_config``. Returns an empty dict when no config
        is set (fixed mode) so the caller can decide whether to write
        the group at all.
        """
        cfg = self._adaptive_config
        if cfg is None:
            return {}
        return {
            "enabled": bool(cfg.enabled),
            "min_exposure_s": float(cfg.min_exposure_s),
            "max_exposure_s": float(cfg.max_exposure_s),
            "min_power_mw": np.array(cfg.min_power_mw, dtype=float),
            "max_power_mw": np.array(cfg.max_power_mw, dtype=float),
            "target_band_lo": float(cfg.target_band_lo),
            "target_band_hi": float(cfg.target_band_hi),
            "reacquire_threshold": float(cfg.reacquire_threshold),
            "block_size_n": int(cfg.block_size_n),
            "kp": float(cfg.kp),
            "ki": float(cfg.ki),
            "pilot_count": int(cfg.pilot_count),
            "sensor_max": int(cfg.sensor_max),
            "max_reacquire_attempts": int(cfg.max_reacquire_attempts),
        }

    def _write_adaptive_hdf5(
        self,
        outfile: h5py.File,
        samples: list | None = None,
    ) -> None:
        """Write the /adaptive_trajectory group (schema-a) to an open
        HDF5 file. Called before file close in every HDF5 save path
        (single-channel stitch, per-plane crop/full, multi-channel).

        ``samples`` defaults to the full ``self.adaptive_trajectory``.
        Per-plane layouts pass a one-row subset (the file's global plane
        index) so each file carries exactly its own row without
        duplicating the full trajectory. Multi-channel and stitch
        layouts pass the full trajectory (every channel file carries
        the same complete record).

        The group carries one row per main plane with the approved
        field names: plane_index, intensity_fraction, exposure_s,
        laser_power_mw, control_variable_active, reacquired,
        power_fallback. Inactive-channel intensity entries are NaN
        (schema-a convention). The frozen AdaptiveConfig bounds + gains
        are published as group attrs so the saved trajectory is
        self-describing.
        """
        if not self._adaptive_enabled:
            return
        traj = samples if samples is not None else self.adaptive_trajectory
        if not traj:
            return
        grp = outfile.create_group("adaptive_trajectory")
        for k, v in self._adaptive_config_attrs().items():
            grp.attrs[k] = v
        grp.create_dataset(
            "plane_index",
            data=np.array([s.plane_index for s in traj], dtype=int),
        )
        grp.create_dataset(
            "intensity_fraction",
            data=np.array([list(s.intensity_fraction) for s in traj], dtype=float),
        )
        grp.create_dataset(
            "exposure_s",
            data=np.array([s.exposure_s for s in traj], dtype=float),
        )
        grp.create_dataset(
            "laser_power_mw",
            data=np.array([list(s.laser_power_mw) for s in traj], dtype=float),
        )
        grp.create_dataset(
            "control_variable_active",
            data=np.array(
                [s.control_variable_active.encode("utf-8") for s in traj],
                dtype=h5py.string_dtype(encoding="utf-8"),
            ),
        )
        grp.create_dataset(
            "reacquired",
            data=np.array([s.reacquired for s in traj], dtype=bool),
        )
        grp.create_dataset(
            "power_fallback",
            data=np.array([s.power_fallback for s in traj], dtype=bool),
        )

    def _write_adaptive_hdf5_for_file(
        self,
        outfile: h5py.File,
        file_idx: int,
        n_files: int,
    ) -> None:
        """Write the adaptive trajectory group for a specific file's
        plane subset. Stitch (``n_files == 1``) writes the full
        trajectory; per-plane (``n_files > 1``) writes only the row at
        ``file_idx`` (the file's global plane index). No-op when
        adaptive is disabled or the plane index is out of range.
        Raises on write failure — the caller's try/except surfaces it.
        """
        if not self._adaptive_enabled or not self.adaptive_trajectory:
            return
        if n_files > 1:
            if file_idx < len(self.adaptive_trajectory):
                self._write_adaptive_hdf5(
                    outfile, samples=[self.adaptive_trajectory[file_idx]]
                )
        else:
            self._write_adaptive_hdf5(outfile)

    def frame_saver_worker(self) -> None:
        """Thread for saving 3D arrays (or 2D arrays).
        The number of datasets per file is the number of 2D arrays.

        In multi-channel mode (``self.filenames_lists`` has more than one
        channel list), the worker branches on the channel tag from the
        dequeued ``(channel_idx, frame)`` tuple to select the correct
        per-channel filename list and plane index. The single-consumer
        queue contract is preserved — one queue, one consume loop, one
        ``sig_finished`` → ``thread.quit`` → ``wait(10000)``. Single-
        channel mode (one channel list) uses the existing
        ``self.filenames_list`` path unchanged — ``set_files`` populates
        ``filenames_list`` from ``filenames_lists[0]`` so the single-
        channel save loop is byte-identical except for the filename
        suffix.
        """
        if len(self.filenames_lists) > 1:
            self._frame_saver_worker_multi_channel()
            return
        aborted = False
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

                            # Guard against empty/short position lists —
                            # the multi-channel and both paths already guard
                            # the same access. Without this, a save started
                            # before add_motor_parameters has populated the
                            # lists aborts the whole stack with an
                            # IndexError on the first dataset.
                            if pos_index < len(self.horizontal_positions_list):
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
                        # Timeout waiting for a buffer — stop_saving()
                        # may have flipped the flag. If so, drain any
                        # remaining frames with a non-blocking get before
                        # exiting — in demo mode (and on fast rigs) the
                        # acquisition queues all frames near-instantly,
                        # then stop_saving() flips the flag while frames
                        # are still in the queue. Only break if the queue
                        # is truly empty (genuine abort or all frames
                        # consumed).
                        if not self.saving_started:
                            try:
                                buffer = self.queue.get_nowait()
                            except queue.Empty:
                                aborted = True
                                break
                        else:
                            continue
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
                        aborted = True
                        break
                if aborted:
                    break
            # Write the adaptive trajectory group before file close
            # (schema-a). Only writes when adaptive was enabled and
            # samples were recorded. Stitch (1 file) writes the full
            # trajectory; per-plane (N files) writes only this file's
            # plane row so the trajectory is not duplicated across files.
            # A write error surfaces to the operator and stops the worker
            # — the file is still closed so no handle leaks.
            try:
                if len(self.filenames_list) > 1 and idx < len(self.adaptive_trajectory):
                    self._write_adaptive_hdf5(
                        outfile, samples=[self.adaptive_trajectory[idx]]
                    )
                else:
                    self._write_adaptive_hdf5(outfile)
            except Exception as e:
                self.sig_status_message.emit(f"Save error: {e}")
                self.saving_started = False
                outfile.close()
                break
            outfile.close()
            self.sig_status_message.emit("File " + self.filenames_list[idx] + " saved")
            if aborted:
                break
        logger.info(
            "frame_saver_worker exited (saving_started=%s)", self.saving_started
        )

    def _frame_saver_worker_multi_channel(self) -> None:
        """Multi-channel HDF5 save loop body.

        Consumes channel-tagged ``(channel_idx, frame)`` tuples from the
        single save queue and writes each frame as a dataset into the
        correct per-channel HDF5 file. The file/dataset convention is
        driven by ``number_of_files`` and ``number_of_datasets`` — the
        same two conventions as single-channel mode:

        - Stitch (``number_of_files=1``, ``number_of_datasets=n_planes``):
          ONE file per channel containing all planes as datasets
          (``reconstructed_frame001``.. ``reconstructed_frameNNN``).
        - Crop/Full (``number_of_files=n_planes``,
          ``number_of_datasets=1``): one file per (channel, plane), each
          holding one dataset.

        Frames arrive interleaved across channels (L1 plane0, L2 plane0,
        L1 plane1, ...), so the loop opens the first file per channel up
        front and advances each channel's (file_idx, dataset_counter)
        state independently as that channel's tagged frames arrive. When
        a channel's current file fills (``dataset_counter >
        number_of_datasets``), the file is closed, the channel's file
        index advances, and the next file (if any) is opened.

        The single-consumer queue contract is preserved: one queue, one
        consume loop, one ``sig_finished`` → ``thread.quit`` →
        ``wait(10000)``. Termination is on frames consumed
        (``n_channels * number_of_files * number_of_datasets``), NOT
        files written. Both channels of the same plane share the same
        motor position (``add_motor_parameters`` is called once per
        plane by the acquisition worker).
        """
        n_channels = len(self.filenames_lists)
        n_files_per_channel = self.number_of_files
        n_datasets_per_file = int(self.number_of_datasets)
        total_frames = n_channels * n_files_per_channel * n_datasets_per_file
        # Per-channel state: file index (0-based into filenames_lists[ch]),
        # dataset counter (1-based for naming), and the open file handle.
        file_idx = [0] * n_channels
        ds_counter = [1] * n_channels
        outfiles: list = [None] * n_channels
        frames_written = 0

        try:
            # Open the first file for each channel and write root metadata.
            for ch in range(n_channels):
                filename = self.filenames_lists[ch][0]
                logger.info("File created: %s", filename)
                outfile = h5py.File(filename, "a")
                self._write_laser_metadata(outfile)
                self._write_acquisition_metadata(outfile)
                outfiles[ch] = outfile

            while frames_written < total_frames:
                try:
                    item = self.queue.get(True, 1)
                except queue.Empty:
                    if not self.saving_started:
                        try:
                            item = self.queue.get_nowait()
                        except queue.Empty:
                            break
                    else:
                        continue

                # Branch on the channel tag: a tagged tuple routes to
                # the correct per-channel file; a bare ndarray falls back
                # to channel 0 (back-compat for any producer that has not
                # migrated to the tagged form).
                if isinstance(item, tuple):
                    channel_idx, frame = item
                else:
                    channel_idx = 0
                    frame = item

                if channel_idx < 0 or channel_idx >= n_channels:
                    self.sig_status_message.emit(
                        f"Save error: channel index {channel_idx} out of "
                        f"range (0..{n_channels - 1})"
                    )
                    self.saving_started = False
                    break

                if outfiles[channel_idx] is None:
                    # Channel already filled all its files — producer
                    # over-ran. Drop the extra frame without counting it
                    # (counting would let frames_written reach
                    # total_frames while other channels still have queued
                    # frames, exiting early and dropping them).
                    continue

                outfile = outfiles[channel_idx]
                # 0-based dataset index within the current file, and the
                # global plane index within the channel (for motor
                # positions — one snapshot per plane, shared by both
                # channels of the same plane).
                ds_idx = ds_counter[channel_idx] - 1
                pos_index = file_idx[channel_idx] * n_datasets_per_file + ds_idx
                try:
                    if frame.ndim == 2:
                        frame = np.expand_dims(frame, axis=0)
                    for f_idx in range(frame.shape[0]):
                        path_root = (
                            self.datasets_name + f"{ds_counter[channel_idx]:03d}"
                        )
                        self.dataset = outfile.create_dataset(
                            path_root, data=frame[f_idx, :, :]
                        )
                        logger.info(
                            "Dataset created: %s (channel %d plane %d)",
                            path_root,
                            channel_idx,
                            pos_index,
                        )
                        self.dataset.attrs["Sample Name"] = self.sample_name
                        self.dataset.attrs["Date"] = str(datetime.date.today())
                        if pos_index < len(self.horizontal_positions_list):
                            self.dataset.attrs["Horizontal Position"] = (
                                self.horizontal_positions_list[pos_index]
                            )
                            self.dataset.attrs["Vertical Position"] = (
                                self.vertical_positions_list[pos_index]
                            )
                            self.dataset.attrs["Camera Position"] = (
                                self.camera_positions_list[pos_index]
                            )
                        ds_counter[channel_idx] += 1
                        frames_written += 1
                except Exception as e:
                    self.sig_status_message.emit(f"Save error: {e}")
                    self.saving_started = False
                    break

                # If the current file is full, close it and open the
                # next file for this channel (if any).
                if ds_counter[channel_idx] > n_datasets_per_file:
                    # Write the adaptive trajectory group before close
                    # (schema-a). Stitch (1 file/channel) writes the
                    # full trajectory; per-plane (N files/channel)
                    # writes only this file's plane row.
                    self._write_adaptive_hdf5_for_file(
                        outfile, file_idx[channel_idx], n_files_per_channel
                    )
                    outfile.close()
                    self.sig_status_message.emit(
                        "File "
                        + self.filenames_lists[channel_idx][file_idx[channel_idx]]
                        + " saved"
                    )
                    file_idx[channel_idx] += 1
                    if file_idx[channel_idx] < n_files_per_channel:
                        next_filename = self.filenames_lists[channel_idx][
                            file_idx[channel_idx]
                        ]
                        logger.info("File created: %s", next_filename)
                        next_outfile = h5py.File(next_filename, "a")
                        self._write_laser_metadata(next_outfile)
                        self._write_acquisition_metadata(next_outfile)
                        outfiles[channel_idx] = next_outfile
                        ds_counter[channel_idx] = 1
                    else:
                        # Channel exhausted its files — no more opens.
                        outfiles[channel_idx] = None
        except Exception as e:
            self.sig_status_message.emit(f"Save error: {e}")
            self.saving_started = False
        finally:
            for ch in range(n_channels):
                outfile = outfiles[ch]
                if outfile is not None:
                    try:
                        # Write the adaptive trajectory group before
                        # close (schema-a). Uses the channel's current
                        # file_idx — the file that was still open when
                        # the loop exited (stitch: 0; per-plane: the
                        # file that was being filled).
                        self._write_adaptive_hdf5_for_file(
                            outfile, file_idx[ch], n_files_per_channel
                        )
                        outfile.close()
                    except Exception:
                        pass

        logger.info(
            "frame_saver_worker (multi-channel) exited "
            "(saving_started=%s, frames_written=%d)",
            self.saving_started,
            frames_written,
        )

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
        # Derive the channel count from the per-channel filename lists
        # built by set_files(wavelengths=...). When set_files was called
        # with wavelengths (multi-channel mode), filenames_lists has one
        # list per channel; otherwise it is empty and the writer is
        # shaped (1, n_planes, y, x) (single-channel back-compat). The
        # writer MUST be sized to the channel count before any
        # write_plane(channel_idx, ...) call — otherwise a channel-1
        # write indexes past the channel axis (size 1) and raises
        # IndexError.
        n_channels = len(self.filenames_lists) if self.filenames_lists else 1
        try:
            self._zarr_saver.start_stack(store_path, n_planes, n_channels=n_channels)
        except Exception as e:
            self.sig_status_message.emit(f"Save error: {e}")
            self.saving_started = False
            return

        # Per-channel plane counter: each channel fills planes 0..n_planes-1
        # independently (NGFF v0.5 channel dimension). Channel 0 is the
        # canonical motor-position recorder (write_plane guards the append
        # on channel_idx == 0), so its z_idx also serves as the per-plane
        # position-list index.
        #
        # Two exit modes: (1) natural completion — saving_started is still
        # True (the producer has not called stop_saving) and channel 0 has
        # filled all its planes, so the single-channel stack is done; this
        # is the production path where the worker is started, the producer
        # enqueues exactly n_planes frames, and the worker exits without
        # waiting for stop_saving. This natural-completion exit is ONLY
        # used in single-channel mode (n_channels == 1): in multi-channel
        # mode the producer enqueues (0, frame1) then (1, frame2) per
        # plane, so after the last plane's channel-0 frame is processed
        # channel 0 has filled but the channel-1 frame is still in the
        # queue — breaking on channel-0-full would drop the final
        # channel-1 plane (data loss). (2) drain — stop_saving() flipped
        # saving_started to False, so drain every remaining frame (across
        # ALL channels) then exit on the empty queue; this is the
        # multi-channel path where all frames are pre-loaded and the flag
        # is flipped before the worker drains.
        z_idx_per_channel: dict[int, int] = {}
        try:
            while True:
                # Natural completion (single-channel production only): the
                # producer is still active but channel 0 filled its planes.
                # In multi-channel mode this break is skipped — the drain
                # path (stop_saving) is the only exit, so the last
                # channel-1 frame is never dropped.
                if (
                    self.saving_started
                    and n_channels == 1
                    and z_idx_per_channel.get(0, 0) >= n_planes
                ):
                    break
                try:
                    item = self.queue.get(True, 1)
                except queue.Empty:
                    # stop_saving() may have flipped the flag. If so,
                    # drain any remaining frames with a non-blocking get
                    # before exiting — in demo mode (and on fast rigs)
                    # the acquisition queues all frames near-instantly,
                    # then stop_saving() flips the flag while frames are
                    # still in the queue. Only break if the queue is
                    # truly empty (genuine abort or all frames consumed).
                    if not self.saving_started:
                        try:
                            item = self.queue.get_nowait()
                        except queue.Empty:
                            break
                    else:
                        continue

                # Branch on the channel tag: a tagged (channel_idx, frame)
                # tuple routes to that channel's axis index; a bare ndarray
                # falls back to channel 0 (single-channel back-compat).
                if isinstance(item, tuple):
                    channel_idx, frame = item
                else:
                    channel_idx = 0
                    frame = item

                if frame.ndim == 2:
                    frame = np.expand_dims(frame, axis=0)
                for f_idx in range(frame.shape[0]):
                    cz = z_idx_per_channel.get(channel_idx, 0)
                    if cz >= n_planes:
                        # This channel's plane slots are full — drop any
                        # extra frames for it (a producer that over-ran).
                        break
                    # Motor positions: one entry per plane, collected by
                    # add_motor_parameters during the acquisition loop.
                    # The entries are the shell's formatted display strings
                    # (e.g. "99.82 μm"); _position_to_float strips the unit
                    # suffix for the Zarr numeric datasets. Channel 0's
                    # z_idx == plane index, so pos_index = cz. Guard against
                    # a short list (defensive).
                    pos_index = cz
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
                        channel_idx, cz, frame[f_idx, :, :], hor, ver, cam
                    )
                    z_idx_per_channel[channel_idx] = cz + 1
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
            # Gate on channel 0's plane count, NOT on saving_started:
            # stop_saving() flips saving_started=False on NORMAL completion
            # too. Channel 0 is the canonical recorder; if it reached
            # n_planes the stack completed and the store MUST be finalized
            # so napari/ome-zarr readers find the multiscales + omero
            # metadata. Only skip finalize when channel 0 exited early
            # (cz < n_planes) — a genuine abort leaving a partial store.
            ch0_z = z_idx_per_channel.get(0, 0)
            if ch0_z < n_planes:
                logger.info(
                    "zarr_save_worker exiting before finalize "
                    "(ch0_z=%d < n_planes=%d) — partial store left on disk",
                    ch0_z,
                    n_planes,
                )
            else:
                try:
                    self._zarr_saver.set_adaptive_trajectory(
                        self.adaptive_trajectory, self._adaptive_config
                    )
                    self._zarr_saver.finalize()
                    self.sig_status_message.emit("Zarr store " + store_path + " saved")
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

        In multi-channel mode (``self.filenames_lists`` has more than one
        channel list), the HDF5 half branches on the channel tag from the
        dequeued ``(channel_idx, frame)`` tuple to write to the correct
        per-channel wavelength-suffixed file. The Zarr half keeps the
        existing ``write_plane(z_idx, frame, ...)`` call unchanged
        (channel 0 only) — the ``write_plane`` signature does not yet
        accept a ``channel_idx`` param, so multi-channel Zarr
        channel-tag branching is deferred to a later plan. The
        single-consumer queue contract is preserved. Single-channel mode
        (one channel list) uses the existing ``self.filenames_list`` path
        — ``set_files`` populates ``filenames_list`` from
        ``filenames_lists[0]``.
        """
        if len(self.filenames_lists) > 1:
            self._both_save_worker_multi_channel()
            return

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
        aborted = False
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
                                    h5_pos_index = dataset + idx * int(
                                        self.number_of_datasets
                                    )
                                else:
                                    h5_pos_index = idx
                                # Guard against empty/short position lists —
                                # the multi-channel both path and the Zarr
                                # writes below already guard; the single-
                                # channel HDF5 path must too so a save
                                # started before add_motor_parameters has
                                # populated the lists does not abort the
                                # whole stack with an IndexError.
                                if h5_pos_index < len(self.horizontal_positions_list):
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
                                    _position_to_float(
                                        self.horizontal_positions_list[zarr_pos_index]
                                    )
                                    if zarr_pos_index
                                    < len(self.horizontal_positions_list)
                                    else 0.0
                                )
                                ver = (
                                    _position_to_float(
                                        self.vertical_positions_list[zarr_pos_index]
                                    )
                                    if zarr_pos_index
                                    < len(self.vertical_positions_list)
                                    else 0.0
                                )
                                cam = (
                                    _position_to_float(
                                        self.camera_positions_list[zarr_pos_index]
                                    )
                                    if zarr_pos_index < len(self.camera_positions_list)
                                    else 0.0
                                )
                                self._zarr_saver.write_plane(
                                    0, z_idx, buffer[frame, :, :], hor, ver, cam
                                )
                                z_idx += 1
                                zarr_pos_index += 1
                            break
                        except queue.Empty:
                            # stop_saving() may have flipped the flag.
                            # If so, drain any remaining frames with a
                            # non-blocking get before exiting — in demo
                            # mode (and on fast rigs) the acquisition
                            # queues all frames near-instantly, then
                            # stop_saving() flips the flag while frames
                            # are still in the queue. Only break if the
                            # queue is truly empty (genuine abort or all
                            # frames consumed).
                            if not self.saving_started:
                                try:
                                    buffer = self.queue.get_nowait()
                                except queue.Empty:
                                    aborted = True
                                    break
                            else:
                                continue
                        except Exception as e:
                            self.sig_status_message.emit(f"Save error: {e}")
                            self.saving_started = False
                            aborted = True
                            break
                    if aborted or z_idx >= n_planes:
                        break
                # Write the adaptive trajectory group before close
                # (schema-a). Stitch (1 file) writes the full
                # trajectory; per-plane (N files) writes only this
                # file's plane row. A write error surfaces and stops
                # the worker — the file is still closed.
                try:
                    if len(self.filenames_list) > 1 and idx < len(
                        self.adaptive_trajectory
                    ):
                        self._write_adaptive_hdf5(
                            outfile, samples=[self.adaptive_trajectory[idx]]
                        )
                    else:
                        self._write_adaptive_hdf5(outfile)
                except Exception as e:
                    self.sig_status_message.emit(f"Save error: {e}")
                    self.saving_started = False
                    outfile.close()
                    aborted = True
                    break
                outfile.close()
                self.sig_status_message.emit(
                    "File " + self.filenames_list[idx] + " saved"
                )
                if aborted or z_idx >= n_planes:
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
                    z_idx,
                    n_planes,
                )
            else:
                try:
                    self._zarr_saver.set_adaptive_trajectory(
                        self.adaptive_trajectory, self._adaptive_config
                    )
                    self._zarr_saver.finalize()
                    self.sig_status_message.emit("Zarr store " + store_path + " saved")
                except Exception as e:
                    self.sig_status_message.emit(f"Save error: {e}")
                    self.saving_started = False
        except Exception as e:
            self.sig_status_message.emit(f"Save error: {e}")
            self.saving_started = False
        logger.info("both_save_worker exited (saving_started=%s)", self.saving_started)

    def _both_save_worker_multi_channel(self) -> None:
        """Multi-channel both-save loop body.

        Consumes channel-tagged ``(channel_idx, frame)`` tuples from the
        single save queue and writes each frame to BOTH the correct
        per-channel HDF5 file AND the Zarr store in one pass.

        HDF5 half: same file/dataset convention as
        ``_frame_saver_worker_multi_channel`` — stitch (1 file/channel,
        N datasets) or crop/full (N files/channel, 1 dataset each),
        driven by ``number_of_files`` / ``number_of_datasets``. Frames
        arrive interleaved across channels; the loop opens the first
        file per channel up front and advances each channel's
        (file_idx, dataset_counter) state independently, closing and
        opening files as each fills.

        Zarr half: branches on the same channel tag to call
        ``write_plane(channel_idx, cz, frame, ...)`` with a per-channel
        plane counter (``cz``) — each channel fills planes 0..n_planes-1
        on its own channel-axis slice (NGFF v0.5 channel dimension).
        Channel 0 is the canonical motor-position recorder (write_plane
        guards the append on ``channel_idx == 0``).

        Termination is on frames consumed (``n_channels * n_planes``),
        NOT files written. The single-consumer queue contract is
        preserved: one queue, one consume loop, one ``sig_finished`` →
        ``thread.quit`` → ``wait(10000)``.
        """
        n_planes = self.number_of_files * int(self.number_of_datasets)
        store_path = os.path.normpath(
            os.path.join(self.parent.save_directory, self.files_name + ".ome.zarr")
        )
        # Compute the channel count BEFORE start_stack so the Zarr writer
        # is shaped (n_channels, n_planes, y, x) — a channel-1 write_plane
        # call would otherwise index past a size-1 channel axis and raise
        # IndexError. The channel count comes from the per-channel
        # filename lists built by set_files(wavelengths=...).
        n_channels = len(self.filenames_lists)
        try:
            self._zarr_saver.start_stack(store_path, n_planes, n_channels=n_channels)
        except Exception as e:
            self.sig_status_message.emit(f"Save error: {e}")
            self.saving_started = False
            return

        n_files_per_channel = self.number_of_files
        n_datasets_per_file = int(self.number_of_datasets)
        total_frames = n_channels * n_files_per_channel * n_datasets_per_file
        # Per-channel state: file index (0-based into filenames_lists[ch]),
        # dataset counter (1-based for naming), and the open file handle.
        file_idx = [0] * n_channels
        ds_counter = [1] * n_channels
        outfiles: list = [None] * n_channels
        frames_written = 0
        z_idx_per_channel: dict[int, int] = {}

        try:
            # Open the first file for each channel and write root metadata.
            for ch in range(n_channels):
                filename = self.filenames_lists[ch][0]
                logger.info("File created: %s", filename)
                outfile = h5py.File(filename, "a")
                self._write_laser_metadata(outfile)
                self._write_acquisition_metadata(outfile)
                outfiles[ch] = outfile

            while frames_written < total_frames:
                try:
                    item = self.queue.get(True, 1)
                except queue.Empty:
                    if not self.saving_started:
                        try:
                            item = self.queue.get_nowait()
                        except queue.Empty:
                            break
                    else:
                        continue

                if isinstance(item, tuple):
                    channel_idx, frame = item
                else:
                    channel_idx = 0
                    frame = item

                if channel_idx < 0 or channel_idx >= n_channels:
                    self.sig_status_message.emit(
                        f"Save error: channel index {channel_idx} out of range "
                        f"(0..{n_channels - 1})"
                    )
                    self.saving_started = False
                    break

                if outfiles[channel_idx] is None:
                    # Channel exhausted its files — producer over-ran.
                    # Drop the extra frame without counting it (see
                    # _frame_saver_worker_multi_channel for the rationale).
                    continue

                outfile = outfiles[channel_idx]
                ds_idx = ds_counter[channel_idx] - 1
                pos_index = file_idx[channel_idx] * n_datasets_per_file + ds_idx
                try:
                    if frame.ndim == 2:
                        frame = np.expand_dims(frame, axis=0)
                    for f_idx in range(frame.shape[0]):
                        # --- HDF5 write (one dataset per plane per channel) ---
                        path_root = (
                            self.datasets_name + f"{ds_counter[channel_idx]:03d}"
                        )
                        self.dataset = outfile.create_dataset(
                            path_root, data=frame[f_idx, :, :]
                        )
                        logger.info(
                            "Dataset %s created: %s (channel %d plane %d)",
                            f_idx,
                            path_root,
                            channel_idx,
                            pos_index,
                        )
                        self.dataset.attrs["Sample Name"] = self.sample_name
                        self.dataset.attrs["Date"] = str(datetime.date.today())
                        if pos_index < len(self.horizontal_positions_list):
                            self.dataset.attrs["Horizontal Position"] = (
                                self.horizontal_positions_list[pos_index]
                            )
                            self.dataset.attrs["Vertical Position"] = (
                                self.vertical_positions_list[pos_index]
                            )
                            self.dataset.attrs["Camera Position"] = (
                                self.camera_positions_list[pos_index]
                            )
                        ds_counter[channel_idx] += 1
                        frames_written += 1

                        # --- Zarr write (per-channel — write_plane routes
                        # the frame to the channel-axis slice; channel 0
                        # records the motor positions via its guarded append) ---
                        cz = z_idx_per_channel.get(channel_idx, 0)
                        if cz < n_planes:
                            # Zarr motor positions use cz (the per-channel
                            # Zarr z-index, which increments per f_idx) —
                            # NOT pos_index. For a multi-dataset frame
                            # (frame.shape[0] > 1) each sub-frame must get
                            # its own motor position; using pos_index would
                            # give every sub-frame the same position.
                            zarr_pos_index = cz
                            hor = (
                                _position_to_float(
                                    self.horizontal_positions_list[zarr_pos_index]
                                )
                                if zarr_pos_index < len(self.horizontal_positions_list)
                                else 0.0
                            )
                            ver = (
                                _position_to_float(
                                    self.vertical_positions_list[zarr_pos_index]
                                )
                                if zarr_pos_index < len(self.vertical_positions_list)
                                else 0.0
                            )
                            cam = (
                                _position_to_float(
                                    self.camera_positions_list[zarr_pos_index]
                                )
                                if zarr_pos_index < len(self.camera_positions_list)
                                else 0.0
                            )
                            self._zarr_saver.write_plane(
                                channel_idx, cz, frame[f_idx, :, :], hor, ver, cam
                            )
                            z_idx_per_channel[channel_idx] = cz + 1
                except Exception as e:
                    self.sig_status_message.emit(f"Save error: {e}")
                    self.saving_started = False
                    break

                # If the current file is full, close it and open the
                # next file for this channel (if any).
                if ds_counter[channel_idx] > n_datasets_per_file:
                    self._write_adaptive_hdf5_for_file(
                        outfile, file_idx[channel_idx], n_files_per_channel
                    )
                    outfile.close()
                    self.sig_status_message.emit(
                        "File "
                        + self.filenames_lists[channel_idx][file_idx[channel_idx]]
                        + " saved"
                    )
                    file_idx[channel_idx] += 1
                    if file_idx[channel_idx] < n_files_per_channel:
                        next_filename = self.filenames_lists[channel_idx][
                            file_idx[channel_idx]
                        ]
                        logger.info("File created: %s", next_filename)
                        next_outfile = h5py.File(next_filename, "a")
                        self._write_laser_metadata(next_outfile)
                        self._write_acquisition_metadata(next_outfile)
                        outfiles[channel_idx] = next_outfile
                        ds_counter[channel_idx] = 1
                    else:
                        outfiles[channel_idx] = None

            # Close any per-channel HDF5 file still open (the consume loop
            # is done — either all frames consumed or aborted). A channel
            # whose last file filled via the in-loop close path has
            # outfiles[ch] = None; a channel aborted mid-file still has
            # an open handle that must be closed here.
            for ch in range(n_channels):
                if outfiles[ch] is not None:
                    try:
                        self._write_adaptive_hdf5_for_file(
                            outfiles[ch], file_idx[ch], n_files_per_channel
                        )
                        outfiles[ch].close()
                    except Exception:
                        pass

            # Finalize the Zarr store after all HDF5 files are closed.
            # Gate on channel 0's plane count (canonical recorder): if it
            # did not reach n_planes the stack is partial — skip finalize.
            ch0_z = z_idx_per_channel.get(0, 0)
            if ch0_z < n_planes:
                logger.info(
                    "both_save_worker (multi-channel) exiting before finalize "
                    "(ch0_z=%d < n_planes=%d) — partial store left on disk",
                    ch0_z,
                    n_planes,
                )
            else:
                try:
                    self._zarr_saver.set_adaptive_trajectory(
                        self.adaptive_trajectory, self._adaptive_config
                    )
                    self._zarr_saver.finalize()
                    self.sig_status_message.emit("Zarr store " + store_path + " saved")
                except Exception as e:
                    self.sig_status_message.emit(f"Save error: {e}")
                    self.saving_started = False
        except Exception as e:
            self.sig_status_message.emit(f"Save error: {e}")
            self.saving_started = False
        finally:
            for outfile in outfiles:
                if outfile is not None:
                    with contextlib.suppress(Exception):
                        outfile.close()
        logger.info(
            "both_save_worker (multi-channel) exited "
            "(saving_started=%s, frames_written=%d)",
            self.saving_started,
            frames_written,
        )

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

    def __init__(self, shell: Controller_MainWindow) -> None:
        self.parent = shell
        self._writer: AnalysisOmeZarrWriter | None = None
        self.saving_started = False
        self._finalized = False
        self._n_channels = 1
        self._horizontal_positions: list[float] = []
        self._vertical_positions: list[float] = []
        self._camera_positions: list[float] = []
        # Adaptive trajectory (schema-a). Set by set_adaptive_trajectory
        # before finalize so _write_adaptive_group can publish the
        # /acquisition/adaptive group. Empty list + None config = fixed
        # mode (no adaptive group written).
        self._adaptive_trajectory: list = []
        self._adaptive_config: object | None = None
        # ``write_empty_chunks`` global-config override state. Set in
        # start_stack, restored in finalize. Defaults to False here so
        # _restore_write_empty_chunks is a no-op if start_stack never ran
        # or finalize is entered without a prior override.
        self._write_empty_chunks_overridden = False
        self._prev_write_empty_chunks: bool = False

    def start_stack(self, store_path: str, n_planes: int, n_channels: int = 1) -> None:
        """Construct the OME-Zarr writer for a new stack.

        ``store_path`` is a PLAIN filesystem path (NOT ``file://`` — the
        writer raises ``ValueError`` on a ``file://`` prefix). The path
        is asserted to live inside the operator-selected save directory
        so a path-traversal attempt cannot write outside it. The L0
        array is shaped ``(n_channels, n_planes, ysize, xsize)`` — a 4D
        store whose leading axis is the OME-NGFF channel dimension — and
        chunked one channel/plane per chunk so each streaming write
        touches exactly one chunk (peak RAM = one frame + one chunk).
        ``n_channels`` defaults to 1 so the single-channel path stays
        byte-identical to the Phase 8 ``(1, n_planes, y, x)`` shape.
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
        n_channels = int(n_channels)
        shape = (n_channels, int(n_planes), int(cam.ysize), int(cam.xsize))
        chunk_shape = (1, 1, int(cam.ysize), int(cam.xsize))

        # Force zarr v3 to persist all-zero chunks (write_empty_chunks=True).
        # zarr v3 (3.3.0) defaults ``array.write_empty_chunks`` to False, so
        # all-zero chunks — MockCamera demo frames and dark real-rig frames
        # — are silently skipped, producing a metadata-only store with zero
        # data chunk files (the store appears valid but contains no data).
        # ``write_empty_chunks`` is a RUNTIME config only: it is NOT persisted
        # to the on-disk zarr.json, so an array re-fetched from the store
        # loses any config injected at creation time. The writer's
        # ``__setitem__`` -> ``_level0_array()`` -> ``self.root["0"]``
        # re-fetches the L0 array on EVERY write, so a creation-time config
        # injection (e.g. patching ``require_array``) is discarded before the
        # first frame is written. The only mechanism that survives the
        # re-fetch is zarr's GLOBAL config — the fallback used when a
        # re-fetched array builds its ArrayConfig. Set the global for the
        # duration of this ZarrSaver's write phase and restore it in
        # finalize() (and on any finalize-path raise). The app is
        # single-operator (one save at a time), so no concurrent zarr writer
        # conflicts with this transient global override.
        self._prev_write_empty_chunks = bool(
            zarr.config.get("array.write_empty_chunks", False)
        )
        zarr.config.set({"array.write_empty_chunks": True})
        self._write_empty_chunks_overridden = True

        self._writer = AnalysisOmeZarrWriter(
            store_path=resolved,
            shape=shape,
            chunk_shape=chunk_shape,
            dtype=np.uint16,
            overwrite=True,
            unit="micrometer",
        )

        self._n_channels = n_channels
        self.saving_started = True
        self._finalized = False
        self._horizontal_positions = []
        self._vertical_positions = []
        self._camera_positions = []

    def write_plane(
        self,
        channel_idx: int,
        z_idx: int,
        frame: np.ndarray,
        hor_pos: float,
        ver_pos: float,
        cam_pos: float,
    ) -> None:
        """Stream one reconstructed 2D frame into the L0 array.

        The writer indexes a 4D array ``(c, z, y, x)``; ``channel_idx``
        selects the channel-axis slice the frame lands in (NGFF v0.5
        channel dimension). The per-plane frame is 2D ``(y, x)``. Motor
        positions are recorded ONCE per plane — both channels of the
        same plane share the same motor position (the acquisition
        worker records it once per plane), so the append is guarded by
        ``channel_idx == 0`` to avoid duplicating the entry per channel.
        """
        if self._writer is None:
            raise RuntimeError("ZarrSaver.write_plane called before start_stack")
        self._writer[channel_idx, z_idx, :, :] = frame
        if channel_idx == 0:
            self._horizontal_positions.append(float(hor_pos))
            self._vertical_positions.append(float(ver_pos))
            self._camera_positions.append(float(cam_pos))

    def _build_omero_channels(self, lasers) -> list[dict]:
        """Build the omero.channels list from the lasers that were
        actually used in this acquisition.

        Only lasers whose auto-laser flag was set at acquisition start
        (``self.parent._auto_laser1`` / ``_auto_laser2``) are included.
        The flags are cached on the GUI thread by
        ``_cache_auto_laser_flags()`` before the worker spawns, so they
        reflect the operator's intent at start-of-run — not the live
        ``laser.active`` state, which is False by finalize time because
        ``stop_lasers()`` runs in the acquisition worker's cleanup
        before the save worker drains the queue and finalizes.

        Each channel dict carries ``label`` / ``color`` / ``active`` /
        ``wavelength`` — the color is a 6-char hex string with no ``#``
        prefix.
        """
        channels: list[dict] = []
        for idx, laser in enumerate(lasers):
            # idx 0 -> _auto_laser1, idx 1 -> _auto_laser2
            flag_attr = f"_auto_laser{idx + 1}"
            if not getattr(self.parent, flag_attr, False):
                continue
            channels.append(
                {
                    "label": laser.label,
                    "color": wavelength_to_hex(laser.wavelength),
                    "active": True,
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
            raise RuntimeError(
                "ZarrSaver._write_acquisition_group called with no writer"
            )
        root = self._writer.root
        grp = root.create_group("acquisition")
        motor = grp.create_group("motor")
        motor.create_array(
            "horizontal", data=np.array(self._horizontal_positions, dtype=float)
        )
        motor.create_array(
            "vertical", data=np.array(self._vertical_positions, dtype=float)
        )
        motor.create_array("camera", data=np.array(self._camera_positions, dtype=float))

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

    def set_adaptive_trajectory(
        self,
        trajectory: list,
        config: object | None,
    ) -> None:
        """Provide the adaptive trajectory samples + frozen config so
        ``finalize`` can publish the ``/acquisition/adaptive`` group
        (schema-a). Called by the save worker before finalize when
        adaptive is enabled. An empty trajectory or None config means
        fixed mode — no adaptive group is written.
        """
        self._adaptive_trajectory = list(trajectory) if trajectory else []
        self._adaptive_config = config

    def _write_adaptive_group(self) -> None:
        """Write the ``/acquisition/adaptive`` group (schema-a) via the
        writer's public ``root`` handle.

        Called AFTER ``finalize_with_resolutions`` and after
        ``_write_acquisition_group`` so the adaptive group is a sibling
        under ``/acquisition``. The group carries one row per main plane
        with the same field names as the HDF5 ``/adaptive_trajectory``
        group: plane_index, intensity_fraction, exposure_s,
        laser_power_mw, control_variable_active, reacquired,
        power_fallback. The frozen AdaptiveConfig bounds + gains are
        published as group attrs. No-op when the trajectory is empty
        (fixed mode).
        """
        if not self._adaptive_trajectory:
            return
        if self._writer is None:
            raise RuntimeError("ZarrSaver._write_adaptive_group called with no writer")
        root = self._writer.root
        acq = root["acquisition"]
        grp = acq.create_group("adaptive")
        traj = self._adaptive_trajectory
        cfg = self._adaptive_config

        # AdaptiveConfig attrs (schema-a reproducibility contract).
        # zarr v3 attrs are JSON-serialised, so tuple fields are stored
        # as lists (not np.array, which is not JSON serialisable).
        if cfg is not None:
            grp.attrs["enabled"] = bool(cfg.enabled)
            grp.attrs["min_exposure_s"] = float(cfg.min_exposure_s)
            grp.attrs["max_exposure_s"] = float(cfg.max_exposure_s)
            grp.attrs["min_power_mw"] = list(cfg.min_power_mw)
            grp.attrs["max_power_mw"] = list(cfg.max_power_mw)
            grp.attrs["target_band_lo"] = float(cfg.target_band_lo)
            grp.attrs["target_band_hi"] = float(cfg.target_band_hi)
            grp.attrs["reacquire_threshold"] = float(cfg.reacquire_threshold)
            grp.attrs["block_size_n"] = int(cfg.block_size_n)
            grp.attrs["kp"] = float(cfg.kp)
            grp.attrs["ki"] = float(cfg.ki)
            grp.attrs["pilot_count"] = int(cfg.pilot_count)
            grp.attrs["sensor_max"] = int(cfg.sensor_max)
            grp.attrs["max_reacquire_attempts"] = int(cfg.max_reacquire_attempts)

        grp.create_array(
            "plane_index",
            data=np.array([s.plane_index for s in traj], dtype=int),
        )
        grp.create_array(
            "intensity_fraction",
            data=np.array([list(s.intensity_fraction) for s in traj], dtype=float),
        )
        grp.create_array(
            "exposure_s",
            data=np.array([s.exposure_s for s in traj], dtype=float),
        )
        grp.create_array(
            "laser_power_mw",
            data=np.array([list(s.laser_power_mw) for s in traj], dtype=float),
        )
        # zarr v3 does not support object-dtype arrays; use a fixed-width
        # unicode dtype (U32 is ample for "exposure"/"power"/"fixed").
        cva = np.array([s.control_variable_active for s in traj], dtype="U32")
        grp.create_array("control_variable_active", data=cva)
        grp.create_array(
            "reacquired",
            data=np.array([s.reacquired for s in traj], dtype=bool),
        )
        grp.create_array(
            "power_fallback",
            data=np.array([s.power_fallback for s in traj], dtype=bool),
        )

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

        try:
            self._finalize_body()
        finally:
            # Always restore the global write_empty_chunks config, even if
            # the pyramid build or acquisition-group write raised — the
            # override was scoped to this ZarrSaver's write phase and must
            # not leak to unrelated zarr usage in the process. The flag
            # makes this a no-op when start_stack never overrode it.
            self._restore_write_empty_chunks()

    def _restore_write_empty_chunks(self) -> None:
        """Restore zarr's global ``array.write_empty_chunks`` to the value
        captured in ``start_stack``. Idempotent: a second call (e.g. a
        double-finalize from the worker error path) is a no-op because the
        flag is cleared on the first restore.
        """
        if not self._write_empty_chunks_overridden:
            return
        zarr.config.set({"array.write_empty_chunks": self._prev_write_empty_chunks})
        self._write_empty_chunks_overridden = False

    def _finalize_body(self) -> None:
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

        # Caller-sync guard: the writer's L0 channel axis was sized by
        # start_stack's n_channels, and omero_channels is built from the
        # auto-laser flags the operator set at run start. A mismatch would
        # write NGFF metadata inconsistent with the array shape. The
        # writer itself does not validate this; the ZarrSaver layer adds
        # the check as defense-in-depth. Two failure modes:
        #   - overflow: more omero channels declared than axis slots
        #     (len(omero) > n_channels) — would index past the channel axis.
        #   - multi-channel undercount: n_channels > 1 but fewer omero
        #     channels than axis slots — a 2-channel writer with 1 omero
        #     channel leaves a channel unlabeled.
        # The single-channel no-flags case (n_channels=1, omero=0) is the
        # Phase 8 back-compat path — no auto-laser flag was set so no
        # channel is listed, but the writer still has its 1 channel axis.
        # That is allowed: finalize_with_resolutions accepts an empty
        # omero.channels list for a single-channel store.
        if len(omero_channels) > self._n_channels or (
            self._n_channels > 1 and len(omero_channels) != self._n_channels
        ):
            raise RuntimeError(
                f"ZarrSaver.finalize: omero_channels length "
                f"({len(omero_channels)}) inconsistent with writer "
                f"channel axis ({self._n_channels}) — caller passed "
                f"n_channels to start_stack that does not match the "
                f"auto-laser flags"
            )

        t0 = time.time()
        self._writer.finalize_with_resolutions(
            base_res=base_res,
            target_resolutions_um=(10, 25, 50, 100),
            make_isotropic=True,
            omero_channels=omero_channels,
        )
        logger.info("Zarr finalize_with_resolutions took %.2fs", time.time() - t0)
        self._write_acquisition_group()
        # Write the adaptive trajectory group after /acquisition so it
        # is a sibling under /acquisition/adaptive (schema-a). No-op
        # when the trajectory is empty (fixed mode).
        self._write_adaptive_group()
        self._finalized = True
        self.saving_started = False


class FrameSaverController:
    """Owns the FrameSaver + FrameViewer QObjects and routes save/enqueue
    calls to them.

    The shell delegates through ``self._fs``. The wrapped QObjects are
    parented to the shell (their QObject parent), so they are destroyed
    with the shell and their thread-affinity is the GUI thread.
    """

    def __init__(self, bundle: DeviceBundle, shell: Controller_MainWindow) -> None:
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
        wavelengths: list[int] | None = None,
    ) -> None:
        self.frame_saver.set_files(
            number_of_files,
            files_name,
            scan_type,
            number_of_datasets,
            datasets_name,
            wavelengths=wavelengths,
        )

    def enqueue_buffer(self, buffer: np.ndarray | tuple[int, np.ndarray]) -> None:
        # Accepts bare np.ndarray (single-channel) or (channel_idx, frame)
        # tuple (multi-channel) — passes through to FrameSaver.
        self.frame_saver.enqueue_buffer(buffer)

    def start_saving(self) -> None:
        self.frame_saver.start_saving()

    def stop_saving(self) -> None:
        self.frame_saver.stop_saving()

    def configure_adaptive(self, enabled: bool, config: object | None = None) -> None:
        self.frame_saver.configure_adaptive(enabled, config=config)

    def record_adaptive_sample(self, sample: object) -> None:
        self.frame_saver.record_adaptive_sample(sample)

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
