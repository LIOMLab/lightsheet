"""FrameSaverController — god-object split collaborator.

Owns the ``FrameSaver`` + ``FrameViewer`` QObject instances and routes the
shell's save/enqueue calls through to them. The shell delegates through
``self._fs``. Plain-Python object (NOT a ``QObject``); emits through the
shell reference. The ``FrameSaver.sig_status_message`` →
``shell.updateUi_message_printer`` connection is preserved on the owned
``FrameSaver`` instance.
"""

from __future__ import annotations

import contextlib
import datetime
import logging
import queue
from pathlib import Path
from typing import TYPE_CHECKING

import h5py
import numpy as np
from PySide6.QtCore import QObject, QThread, Signal, Slot

from lightsheet.gui.coordinators.frame_viewer import FrameViewer
from lightsheet.gui.coordinators.reconstruction import (
    _position_to_float,
    crop_buffer,
    reconstruct_frame,
    reconstruct_frame_linear_blend,
)
from lightsheet.gui.coordinators.zarr_saver import ZarrSaver
from lightsheet.hal.bundle import DeviceBundle

if TYPE_CHECKING:
    from lightsheet.gui.shell.controller import Controller_MainWindow

logger = logging.getLogger(__name__)


class FrameSaverWorker(QObject):
    """Worker QObject for the save loop, affined to a dedicated QThread.

    The save loop body stays on ``FrameSaver``; this worker's
    ``start_saving`` slot invokes the appropriate loop method on the
    worker thread and emits ``sig_finished`` when it returns. The
    ``sig_finished`` → ``thread.quit`` connection ensures the thread
    exits after the save loop completes (the close-ordering contract).
    """

    sig_finished = Signal()

    def __init__(self, saver: FrameSaver) -> None:
        super().__init__()
        self._saver = saver

    @Slot()
    def start_saving(self) -> None:
        """Run the save loop on the worker thread, then signal completion."""
        try:
            fmt = self._saver.parent.save_format  # ty: ignore[unresolved-attribute]
            if fmt == "hdf5":
                self._saver.frame_saver_worker()
            elif fmt == "zarr":
                self._saver.zarr_save_worker()
            elif fmt == "both":
                # Single consume loop writing each frame to BOTH formats.
                self._saver.both_save_worker()
            else:
                self._saver.frame_saver_worker()
        finally:
            self.sig_finished.emit()


class FrameSaver(QObject):
    """Class for storing buffers (images) in its queue and saving them
    afterwards in a specified directory in a HDF5 format"""

    sig_status_message = Signal(str)

    def __init__(self, parent: Controller_MainWindow, block_size: int = 1) -> None:
        QObject.__init__(self, parent)
        self.parent = parent  # ty: ignore[invalid-assignment]
        self.sig_status_message.connect(self.parent.updateUi_message_printer)
        self.file_format = self.parent.save_format

        self.saving_started = False
        self.block_size = block_size
        self.queue = queue.Queue(2 * block_size)

        self.sample_name = ""
        self.number_of_files = 1
        self.filenames_list = []
        # Per-channel filename lists. set_files populates one list per
        # channel; single-channel mode has one list (filenames_list mirrors
        # filenames_lists[0]).
        self.filenames_lists: list[list[str]] = []
        self.horizontal_positions_list = []
        self.vertical_positions_list = []
        self.camera_positions_list = []

        # ZarrSaver is a plain-Python sibling collaborator (NOT a QObject).
        self._zarr_saver = ZarrSaver(parent)

        # Adaptive trajectory samples. Cleared in reinit.
        self.adaptive_trajectory: list = []  # ty: ignore[missing-type-argument]
        self._adaptive_enabled: bool = False
        # Frozen AdaptiveConfig (bounds + gains). Stored when
        # configure_adaptive is called so the writers can publish config
        # attrs alongside the trajectory. None in fixed mode.
        self._adaptive_config: object | None = None

        # Focus trajectory samples. Cleared in reinit.
        self.focus_trajectory: list = []  # ty: ignore[missing-type-argument]
        self._focus_enabled: bool = False
        # Frozen FocusConfig. Stored when configure_focus is called so the
        # writers can publish config attrs alongside the trajectory. None
        # in fixed mode.
        self._focus_config: object | None = None

    def reinit(self, block_size: int) -> None:
        if self.saving_started:
            self.saving_started = False

        # Re-read save_format so a per-acquisition format change takes effect.
        self.file_format = self.parent.save_format  # ty: ignore[unresolved-attribute]
        # Reset the ZarrSaver for the next acquisition.
        self._zarr_saver = ZarrSaver(self.parent)  # ty: ignore[invalid-argument-type]

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
        # Clear adaptive trajectory state so a re-run does not carry over.
        self.adaptive_trajectory = []
        self._adaptive_enabled = False
        self._adaptive_config = None

        # Clear focus trajectory state so a re-run does not carry over.
        self.focus_trajectory = []
        self._focus_enabled = False
        self._focus_config = None

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
        """Set the number and name of files to save, ensuring unique filenames.

        Filename convention: ``<files_name>_<wavelength>nm`` with a
        per-channel sequential counter (no suffix on the first file, then
        ``_01``, ``_02``, ...). Collision avoidance increments past
        existing files on disk.

        ``wavelengths`` is required — passing ``None`` raises
        ``ValueError``. ``self.filenames_lists`` is built as a list of
        lists (one per channel). Single-channel mode also populates
        ``self.filenames_list`` from ``filenames_lists[0]``.
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

        save_dir = Path(getattr(self.parent, "save_directory", "") or "")
        width = max(2, len(str(self.number_of_files)))

        self.filenames_lists = []
        for wl in wavelengths:
            channel_list: list[str] = []
            counter = 0
            for _plane in range(self.number_of_files):
                base = self.files_name + f"_{wl}nm"
                if counter == 0:
                    candidate = base + ".hdf5"
                else:
                    candidate = f"{base}_{counter:0{width}d}.hdf5"
                full = str(save_dir / candidate)
                while Path(full).is_file():
                    counter += 1
                    candidate = f"{base}_{counter:0{width}d}.hdf5"
                    full = str(save_dir / candidate)
                channel_list.append(full)
                counter += 1
            self.filenames_lists.append(channel_list)

        # Single-channel back-compat: populate filenames_list from
        # filenames_lists[0] so the single-channel save worker path works.
        if len(self.filenames_lists) == 1:
            self.filenames_list = list(self.filenames_lists[0])
        else:
            # Multi-channel: clear so the multi-channel worker branch is taken.
            self.filenames_list = []

    # Saving methods

    def enqueue_buffer(self, buffer: np.ndarray | tuple[int, np.ndarray]) -> None:
        """Put an image in the save queue. Accepts a bare ``np.ndarray``
        (single-channel) or a ``(channel_idx, frame)`` tuple (multi-channel).
        """
        self.queue.put(item=buffer, block=True)

    def start_saving(self) -> None:
        """Initiates the save worker on a dedicated QThread. The worker's
        ``start_saving`` slot runs the save loop on the worker thread;
        ``sig_finished`` quits the thread's event loop so ``stop_saving``'s
        ``wait(10000)`` unblocks only after ``h5py.File.close()`` has
        returned (the close-ordering contract).
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
        for i, laser in enumerate(self.parent.lasers):  # ty: ignore[unresolved-attribute]
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
        motors = self.parent.motors  # ty: ignore[unresolved-attribute]
        outfile.attrs["Horizontal Position"] = motors.horizontal.get_position("mm")  # ty: ignore[unresolved-attribute]
        outfile.attrs["Vertical Position"] = motors.vertical.get_position("mm")  # ty: ignore[unresolved-attribute]
        outfile.attrs["Camera Position"] = motors.camera.get_position("mm")  # ty: ignore[unresolved-attribute]

        sg = self.parent.siggen  # ty: ignore[unresolved-attribute]
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
        outfile.attrs["Sample Rate"] = sg.sample_rate  # ty: ignore[unresolved-attribute]

        cam = self.parent.camera  # ty: ignore[unresolved-attribute]
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
        . It may be omitted in fixed
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
            sample.plane_index,  # ty: ignore[unresolved-attribute]
            sample.exposure_s,  # ty: ignore[unresolved-attribute]
            sample.laser_power_mw[0],  # ty: ignore[unresolved-attribute]
            sample.laser_power_mw[1],  # ty: ignore[unresolved-attribute]
            sample.control_variable_active,  # ty: ignore[unresolved-attribute]
            sample.reacquired,  # ty: ignore[unresolved-attribute]
            sample.power_fallback,  # ty: ignore[unresolved-attribute]
        )

    def configure_focus(self, enabled: bool, config: object | None = None) -> None:
        """Configure the focus trajectory recorder for this acquisition.

        When ``enabled`` is True, the per-plane loop calls
        ``record_focus_sample`` once per focus block boundary, and the
        HDF5 writer writes the ``/focus_trajectory`` group before file
        close while the Zarr writer writes ``/acquisition/focus`` during
        finalize. When False, no trajectory is recorded or written and
        no focus group is created in either format.

        ``config`` is the frozen ``FocusConfig`` whose block size and
        residual settings are published as group attrs alongside the
        per-block trajectory. It may be omitted in fixed mode
        (``enabled=False``); when ``enabled=True`` the config attrs are
        required so the saved trajectory is self-describing.
        """
        self._focus_enabled = bool(enabled)
        self.focus_trajectory = []
        self._focus_config = config if enabled else None

    def record_focus_sample(self, sample: object) -> None:
        """Append a frozen FocusSample to the focus trajectory list.

        Called by the StackWorker once per focus block boundary, before
        the block's frames are enqueued for saving. The sample is logged
        and held for the HDF5 writer (``_write_focus_hdf5``) which
        serializes the full trajectory before file close.
        """
        if not self._focus_enabled:
            return
        self.focus_trajectory.append(sample)
        logger.info(
            "focus sample: block=%d stage=%.4fmm feedforward=%.4fmm "
            "residual=%.4fmm applied=%.4fmm sharpness=%s",
            sample.block_index,  # ty: ignore[unresolved-attribute]
            sample.stage_pos_mm,  # ty: ignore[unresolved-attribute]
            sample.feedforward_camera_pos_mm,  # ty: ignore[unresolved-attribute]
            sample.residual_mm,  # ty: ignore[unresolved-attribute]
            sample.applied_camera_pos_mm,  # ty: ignore[unresolved-attribute]
            sample.sharpness_metric,  # ty: ignore[unresolved-attribute]
        )

    def _adaptive_config_attrs(self) -> dict:  # ty: ignore[missing-type-argument]
        """Build the AdaptiveConfig attrs dict from the frozen
        ``self._adaptive_config``. Returns an empty dict when no config
        is set (fixed mode) so the caller can decide whether to write
        the group at all.
        """
        cfg = self._adaptive_config
        if cfg is None:
            return {}
        return {
            "enabled": bool(cfg.enabled),  # ty: ignore[unresolved-attribute]
            "min_exposure_s": float(cfg.min_exposure_s),  # ty: ignore[unresolved-attribute]
            "max_exposure_s": float(cfg.max_exposure_s),  # ty: ignore[unresolved-attribute]
            # Store as a Python list (not np.array) so the HDF5 attrs
            # match the Zarr attrs type (Zarr v3 attrs are JSON-serialised
            # and cannot store np.array). The schema-a contract requires
            # identical field names AND types across both formats; a
            # downstream tool reading both gets a list in either case.
            "min_power_mw": list(cfg.min_power_mw),  # ty: ignore[unresolved-attribute]
            "max_power_mw": list(cfg.max_power_mw),  # ty: ignore[unresolved-attribute]
            "target_band_lo": float(cfg.target_band_lo),  # ty: ignore[unresolved-attribute]
            "target_band_hi": float(cfg.target_band_hi),  # ty: ignore[unresolved-attribute]
            "reacquire_threshold": float(cfg.reacquire_threshold),  # ty: ignore[unresolved-attribute]
            "block_size_n": int(cfg.block_size_n),  # ty: ignore[unresolved-attribute]
            "kp": float(cfg.kp),  # ty: ignore[unresolved-attribute]
            "ki": float(cfg.ki),  # ty: ignore[unresolved-attribute]
            "pilot_count": int(cfg.pilot_count),  # ty: ignore[unresolved-attribute]
            "sensor_max": int(cfg.sensor_max),  # ty: ignore[unresolved-attribute]
            "max_reacquire_attempts": int(cfg.max_reacquire_attempts),  # ty: ignore[unresolved-attribute]
        }

    def _write_adaptive_hdf5(
        self,
        outfile: h5py.File,
        samples: list | None = None,  # ty: ignore[missing-type-argument]
    ) -> None:
        """Write the /adaptive_trajectory group  to an open
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
        (convention). The frozen AdaptiveConfig bounds + gains
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
        n_datasets_per_file: int = 1,
        actual_n_datasets: int | None = None,
    ) -> None:
        """Write the adaptive trajectory group for a specific file's
        plane subset. Stitch (``n_files == 1``) writes the full
        trajectory; per-plane (``n_files > 1``) writes the rows for the
        planes this file contains. No-op when adaptive is disabled or
        the plane range is out of range. Raises on write failure — the
        caller's try/except surfaces it.

        ``n_datasets_per_file`` is the number of datasets (planes) each
        file holds. For the per-plane layout (``n_files > 1``,
        ``n_datasets_per_file == 1``) each file holds one plane and the
        row written is ``trajectory[file_idx]`` — the historical
        behaviour. For the multi-file multi-dataset layout
        (``n_files > 1``, ``n_datasets_per_file > 1``) each file holds
        ``n_datasets_per_file`` planes and the rows written are
        ``trajectory[file_idx * n_datasets_per_file :
        (file_idx + 1) * n_datasets_per_file]`` — one trajectory row
        per plane in the file, aligned with the image data.

        ``actual_n_datasets`` caps the number of trajectory rows
        written to this file to the number of image datasets actually
        written. When a save aborts mid-file (E-stop, write error,
        queue empty), the file contains K < ``n_datasets_per_file``
        image datasets; without this cap the trajectory write would
        emit ``n_datasets_per_file`` rows, leaving the file with more
        trajectory rows than image datasets (a metadata misalignment —
        extra rows reference planes whose image data is absent). When
        ``None`` (the default) the historical full-slice behaviour is
        preserved. The cap is applied as ``min(actual_n_datasets,
        n_datasets_per_file)`` so a caller that passes a count larger
        than the per-file capacity cannot over-write.
        """
        if not self._adaptive_enabled or not self.adaptive_trajectory:
            return
        if n_files > 1:
            # Cap the row count to the datasets actually written to
            # this file when the caller reports a partial fill.
            row_count = n_datasets_per_file
            if actual_n_datasets is not None:
                row_count = min(actual_n_datasets, n_datasets_per_file)
            start = file_idx * n_datasets_per_file
            end = start + row_count
            if start < len(self.adaptive_trajectory):
                rows = self.adaptive_trajectory[
                    start:min(end, len(self.adaptive_trajectory))
                ]
                self._write_adaptive_hdf5(outfile, samples=rows)
        else:
            self._write_adaptive_hdf5(outfile)

    def _focus_config_attrs(self) -> dict:  # ty: ignore[missing-type-argument]
        """Build the FocusConfig attrs dict from the frozen
        ``self._focus_config``. Returns an empty dict when no config is set
        (fixed mode) so the caller can decide whether to write the group at
        all.
        """
        cfg = self._focus_config
        if cfg is None:
            return {}
        return {
            "enabled": bool(cfg.enabled),  # ty: ignore[unresolved-attribute]
            "block_size_n": int(cfg.block_size_n),  # ty: ignore[unresolved-attribute]
            "autofocus_residual": bool(cfg.autofocus_residual),  # ty: ignore[unresolved-attribute]
            "curve_path": str(cfg.curve_path),  # ty: ignore[unresolved-attribute]
            "residual_gain_mm": float(cfg.residual_gain_mm),  # ty: ignore[unresolved-attribute]
            "max_residual_mm": float(cfg.max_residual_mm),  # ty: ignore[unresolved-attribute]
        }

    def _write_focus_hdf5(
        self,
        outfile: h5py.File,
        samples: list | None = None,  # ty: ignore[missing-type-argument]
    ) -> None:
        """Write the ``/focus_trajectory`` group to an open HDF5 file.

        ``samples`` defaults to the full ``self.focus_trajectory``. Per-file
        layouts pass a subset so the file carries only its own block rows.

        The group carries one row per focus block with the approved field
        names: block_index, stage_pos_mm, feedforward_camera_pos_mm,
        residual_mm, applied_camera_pos_mm, sharpness_metric. The frozen
        FocusConfig block size + residual settings are published as group
        attrs.
        """
        if not self._focus_enabled:
            return
        traj = samples if samples is not None else self.focus_trajectory
        if not traj:
            return
        grp = outfile.create_group("focus_trajectory")
        for k, v in self._focus_config_attrs().items():
            grp.attrs[k] = v
        grp.create_dataset(
            "block_index",
            data=np.array([s.block_index for s in traj], dtype=int),
        )
        grp.create_dataset(
            "stage_pos_mm",
            data=np.array([s.stage_pos_mm for s in traj], dtype=float),
        )
        grp.create_dataset(
            "feedforward_camera_pos_mm",
            data=np.array([s.feedforward_camera_pos_mm for s in traj], dtype=float),
        )
        grp.create_dataset(
            "residual_mm",
            data=np.array([s.residual_mm for s in traj], dtype=float),
        )
        grp.create_dataset(
            "applied_camera_pos_mm",
            data=np.array([s.applied_camera_pos_mm for s in traj], dtype=float),
        )
        # sharpness_metric is None for the first block (no prior frame) and
        # a float thereafter. Store None as NaN so the dataset stays numeric.
        sharpness = [
            s.sharpness_metric if s.sharpness_metric is not None else float("nan")
            for s in traj
        ]
        grp.create_dataset(
            "sharpness_metric",
            data=np.array(sharpness, dtype=float),
        )

    def _write_focus_hdf5_for_file(
        self,
        outfile: h5py.File,
        file_idx: int,
        n_files: int,
        n_datasets_per_file: int = 1,
        actual_n_datasets: int | None = None,
    ) -> None:
        """Write the focus trajectory group for a specific file's plane
        range.

        One ``FocusSample`` is recorded per focus block. The block's row is
        included in every file that contains planes within that block. For
        stitch (``n_files == 1``) the full trajectory is written. For
        per-plane/multi-dataset layouts, a row is included when the block
        overlaps the file's plane span, using ``block_size_n`` from the
        frozen FocusConfig. Fixed mode is a no-op.
        """
        if not self._focus_enabled or not self.focus_trajectory:
            return
        if n_files == 1:
            self._write_focus_hdf5(outfile)
            return
        cfg = self._focus_config
        block_size = int(getattr(cfg, "block_size_n", 1)) if cfg is not None else 1
        file_start = file_idx * n_datasets_per_file
        row_count = n_datasets_per_file
        if actual_n_datasets is not None:
            row_count = min(actual_n_datasets, n_datasets_per_file)
        file_end = file_start + row_count
        rows = []
        for s in self.focus_trajectory:
            block_start = s.block_index * block_size
            block_end = block_start + block_size
            if block_start < file_end and block_end > file_start:
                rows.append(s)
        if rows:
            self._write_focus_hdf5(outfile, samples=rows)

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
            # Write the adaptive trajectory group before file close.
            # Only writes when adaptive was enabled and samples were
            # recorded. Stitch (1 file) writes the full trajectory;
            # per-plane (N files) writes this file's plane rows
            # (file_idx * n_datasets .. file_idx * n_datasets + n_datasets).
            # Cap the row count to the datasets actually written
            # (counter - 1) so a file aborted mid-fill does not end up
            # with more trajectory rows than image datasets.
            try:
                self._write_adaptive_hdf5_for_file(
                    outfile,
                    idx,
                    len(self.filenames_list),
                    int(self.number_of_datasets),
                    actual_n_datasets=counter - 1,
                )
                self._write_focus_hdf5_for_file(
                    outfile,
                    idx,
                    len(self.filenames_list),
                    int(self.number_of_datasets),
                    actual_n_datasets=counter - 1,
                )
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
        outfiles: list = [None] * n_channels  # ty: ignore[missing-type-argument]
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
                    # Write the adaptive trajectory group before close.
                    # Stitch (1 file/channel) writes the full trajectory;
                    # per-plane (N files/channel) writes this file's rows.
                    # The file is full here (ds_counter just exceeded
                    # n_datasets_per_file), so the actual dataset count
                    # equals n_datasets_per_file. Wrapped in a local
                    # try/except matching the single-channel pattern so
                    # an adaptive-write error surfaces to the operator
                    # instead of propagating to the outer catch.
                    try:
                        self._write_adaptive_hdf5_for_file(
                            outfile,
                            file_idx[channel_idx],
                            n_files_per_channel,
                            n_datasets_per_file,
                        )
                        self._write_focus_hdf5_for_file(
                            outfile,
                            file_idx[channel_idx],
                            n_files_per_channel,
                            n_datasets_per_file,
                        )
                    except Exception as e:
                        self.sig_status_message.emit(f"Save error: {e}")
                        self.saving_started = False
                        outfile.close()
                        break
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
                        # close. Uses the channel's current file_idx —
                        # the file that was still open when the loop
                        # exited (stitch: 0; per-plane: the file that
                        # was being filled). Cap the row count to the
                        # datasets actually written (ds_counter[ch] - 1)
                        # so a file aborted mid-fill does not end up with
                        # more trajectory rows than image datasets.
                        # Surface write errors to the operator instead
                        # of silently swallowing them (the previous
                        # `except Exception: pass` hid adaptive-write
                        # failures from the operator).
                        self._write_adaptive_hdf5_for_file(
                            outfile,
                            file_idx[ch],
                            n_files_per_channel,
                            n_datasets_per_file,
                            actual_n_datasets=ds_counter[ch] - 1,
                        )
                        self._write_focus_hdf5_for_file(
                            outfile,
                            file_idx[ch],
                            n_files_per_channel,
                            n_datasets_per_file,
                            actual_n_datasets=ds_counter[ch] - 1,
                        )
                        outfile.close()
                    except Exception as e:
                        self.sig_status_message.emit(f"Save error: {e}")
                        with contextlib.suppress(Exception):
                            outfile.close()

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
        store_path = str(
            Path(self.parent.save_directory) / (self.files_name + ".ome.zarr")  # ty: ignore[unresolved-attribute]
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
                    self._zarr_saver.set_focus_trajectory(
                        self.focus_trajectory, self._focus_config
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
        store_path = str(
            Path(self.parent.save_directory) / (self.files_name + ".ome.zarr")  # ty: ignore[unresolved-attribute]
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
                # Write the adaptive trajectory group before close.
                # Stitch (1 file) writes the full trajectory; per-plane
                # (N files) writes this file's plane rows. Cap the row
                # count to the datasets actually written (counter - 1)
                # so a file aborted mid-fill does not end up with more
                # trajectory rows than image datasets.
                try:
                    self._write_adaptive_hdf5_for_file(
                        outfile,
                        idx,
                        len(self.filenames_list),
                        int(self.number_of_datasets),
                        actual_n_datasets=counter - 1,
                    )
                    self._write_focus_hdf5_for_file(
                        outfile,
                        idx,
                        len(self.filenames_list),
                        int(self.number_of_datasets),
                        actual_n_datasets=counter - 1,
                    )
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
                    self._zarr_saver.set_focus_trajectory(
                        self.focus_trajectory, self._focus_config
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
        store_path = str(
            Path(self.parent.save_directory) / (self.files_name + ".ome.zarr")  # ty: ignore[unresolved-attribute]
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
        outfiles: list = [None] * n_channels  # ty: ignore[missing-type-argument]
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
                    # The file is full here, so the actual dataset
                    # count equals n_datasets_per_file. Wrapped in a
                    # local try/except matching the single-channel
                    # pattern so an adaptive-write error surfaces to
                    # the operator instead of propagating to the outer
                    # catch.
                    try:
                        self._write_adaptive_hdf5_for_file(
                            outfile,
                            file_idx[channel_idx],
                            n_files_per_channel,
                            n_datasets_per_file,
                        )
                        self._write_focus_hdf5_for_file(
                            outfile,
                            file_idx[channel_idx],
                            n_files_per_channel,
                            n_datasets_per_file,
                        )
                    except Exception as e:
                        self.sig_status_message.emit(f"Save error: {e}")
                        self.saving_started = False
                        outfile.close()
                        break
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
            # an open handle that must be closed here. Cap the trajectory
            # row count to the datasets actually written (ds_counter[ch]
            # - 1) so a file aborted mid-fill does not end up with more
            # trajectory rows than image datasets. Surface write errors
            # to the operator instead of silently swallowing them.
            for ch in range(n_channels):
                if outfiles[ch] is not None:
                    try:
                        self._write_adaptive_hdf5_for_file(
                            outfiles[ch],
                            file_idx[ch],
                            n_files_per_channel,
                            n_datasets_per_file,
                            actual_n_datasets=ds_counter[ch] - 1,
                        )
                        self._write_focus_hdf5_for_file(
                            outfiles[ch],
                            file_idx[ch],
                            n_files_per_channel,
                            n_datasets_per_file,
                            actual_n_datasets=ds_counter[ch] - 1,
                        )
                        outfiles[ch].close()
                    except Exception as e:
                        self.sig_status_message.emit(f"Save error: {e}")
                        with contextlib.suppress(Exception):
                            outfiles[ch].close()

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
                    self._zarr_saver.set_focus_trajectory(
                        self.focus_trajectory, self._focus_config
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
            shell, rows=bundle.camera.ysize, columns=bundle.camera.xsize  # ty: ignore[invalid-argument-type]
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

    # Focus trajectory recorder — outer delegation to the inner FrameSaver.

    @property
    def focus_trajectory(self) -> list:  # ty: ignore[missing-type-argument]
        """Read-only view of the inner FrameSaver's focus trajectory."""
        return self.frame_saver.focus_trajectory

    def configure_focus(self, enabled: bool, config: object | None = None) -> None:
        self.frame_saver.configure_focus(enabled, config=config)

    def record_focus_sample(self, sample: object) -> None:
        self.frame_saver.record_focus_sample(sample)

    # -- pass-through to the wrapped FrameViewer ---------------------------

    def enqueue_frame(self, frame: np.ndarray) -> None:
        self.frame_viewer.enqueue_frame(frame)

    # -- pure-numpy image reconstruction -----------------------------------
    # Delegates to focused helpers in ``lightsheet.gui.coordinators.reconstruction``.

    def crop_buffer(self, buffer: np.ndarray) -> np.ndarray:
        return crop_buffer(buffer)

    def reconstruct_frame(self, buffer: np.ndarray) -> np.ndarray:
        return reconstruct_frame(buffer)

    def reconstruct_frame_linear_blend(self, buffer: np.ndarray) -> np.ndarray:
        return reconstruct_frame_linear_blend(buffer)
