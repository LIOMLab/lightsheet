"""Plain-Python OME-Zarr streaming collaborator.

Streams reconstructed frames into an OME-Zarr store and finalizes the
analysis pyramid + NGFF metadata. This module owns the entire Zarr-only
concern; the HDF5 saver stays in ``frame_saver_controller``.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import zarr
from liom_toolkit.utils.zarr_writer import AnalysisOmeZarrWriter

from lightsheet.wavelength_color import wavelength_to_hex

if TYPE_CHECKING:
    from lightsheet.gui.shell.controller import Controller_MainWindow

logger = logging.getLogger(__name__)


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
        # Adaptive trajectory. Set by set_adaptive_trajectory
        # before finalize so _write_adaptive_group can publish the
        # /acquisition/adaptive group. Empty list + None config = fixed
        # mode (no adaptive group written).
        self._adaptive_trajectory: list = []  # ty: ignore[missing-type-argument]
        self._adaptive_config: object | None = None

        # Focus trajectory. Set by set_focus_trajectory before finalize
        # so _write_focus_group can publish the /acquisition/focus group.
        self._focus_trajectory: list = []  # ty: ignore[missing-type-argument]
        self._focus_config: object | None = None
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
        byte-identical to the ``(1, n_planes, y, x)`` shape.
        """
        # Path-traversal guard: the resolved store_path must be inside
        # the operator-selected save directory. realpath() is applied to both
        # so a symlink that points outside the save directory cannot bypass
        # the check.
        save_dir = os.path.realpath(os.path.normpath(self.parent.save_directory))
        resolved = os.path.realpath(os.path.normpath(store_path))
        try:
            common = os.path.commonpath([save_dir, str(Path(resolved).parent)])
        except ValueError:
            common = ""
        if common != save_dir:
            msg = f"Zarr store_path {resolved!r} is outside save directory {save_dir!r}"
            self.parent.sig_message.emit(msg)
            raise ValueError(msg)

        cam = self.parent.camera
        n_channels = int(n_channels)
        shape = (n_channels, int(n_planes), int(cam.ysize), int(cam.xsize))  # ty: ignore[invalid-argument-type]
        chunk_shape = (1, 1, int(cam.ysize), int(cam.xsize))  # ty: ignore[invalid-argument-type]

        # Force zarr v3 to persist all-zero chunks (write_empty_chunks=True).
        # zarr v3 defaults ``write_empty_chunks`` to False, so all-zero chunks
        # (MockCamera demo frames, dark real-rig frames) are silently skipped,
        # producing a metadata-only store with zero data chunk files.
        # ``write_empty_chunks`` is a runtime config only (not persisted to
        # zarr.json), and the writer re-fetches the L0 array on every write,
        # so the only mechanism that survives is zarr's GLOBAL config.
        # Set it for the write phase and restore in finalize().
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

    def _build_omero_channels(self, lasers: tuple) -> list[dict]:  # ty: ignore[missing-type-argument]
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
        channels: list[dict] = []  # ty: ignore[missing-type-argument]
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
        # mock sets it at construct time; the real SigGen reads it from config
        # at construct time).
        grp.attrs["sample_rate"] = siggen.sample_rate  # ty: ignore[unresolved-attribute]
        grp.attrs["binning_x"] = cam.binning_x
        grp.attrs["binning_y"] = cam.binning_y

    def set_adaptive_trajectory(
        self,
        trajectory: list,  # ty: ignore[missing-type-argument]
        config: object | None,
    ) -> None:
        """Provide the adaptive trajectory samples + frozen config so
        ``finalize`` can publish the ``/acquisition/adaptive`` group
        . Called by the save worker before finalize when
        adaptive is enabled. An empty trajectory or None config means
        fixed mode — no adaptive group is written.
        """
        self._adaptive_trajectory = list(trajectory) if trajectory else []
        self._adaptive_config = config

    def _write_adaptive_group(self) -> None:
        """Write the ``/acquisition/adaptive`` group via the
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
        grp = acq.create_group("adaptive")  # ty: ignore[unresolved-attribute]
        traj = self._adaptive_trajectory
        cfg = self._adaptive_config

        # AdaptiveConfig attrs.
        # zarr v3 attrs are JSON-serialised, so tuple fields are stored
        # as lists (not np.array, which is not JSON serialisable).
        if cfg is not None:
            grp.attrs["enabled"] = bool(cfg.enabled)  # ty: ignore[unresolved-attribute]
            grp.attrs["min_exposure_s"] = float(cfg.min_exposure_s)  # ty: ignore[unresolved-attribute]
            grp.attrs["max_exposure_s"] = float(cfg.max_exposure_s)  # ty: ignore[unresolved-attribute]
            grp.attrs["min_power_mw"] = list(cfg.min_power_mw)  # ty: ignore[unresolved-attribute]
            grp.attrs["max_power_mw"] = list(cfg.max_power_mw)  # ty: ignore[unresolved-attribute]
            grp.attrs["target_band_lo"] = float(cfg.target_band_lo)  # ty: ignore[unresolved-attribute]
            grp.attrs["target_band_hi"] = float(cfg.target_band_hi)  # ty: ignore[unresolved-attribute]
            grp.attrs["reacquire_threshold"] = float(cfg.reacquire_threshold)  # ty: ignore[unresolved-attribute]
            grp.attrs["block_size_n"] = int(cfg.block_size_n)  # ty: ignore[unresolved-attribute]
            grp.attrs["kp"] = float(cfg.kp)  # ty: ignore[unresolved-attribute]
            grp.attrs["ki"] = float(cfg.ki)  # ty: ignore[unresolved-attribute]
            grp.attrs["pilot_count"] = int(cfg.pilot_count)  # ty: ignore[unresolved-attribute]
            grp.attrs["sensor_max"] = int(cfg.sensor_max)  # ty: ignore[unresolved-attribute]
            grp.attrs["max_reacquire_attempts"] = int(cfg.max_reacquire_attempts)  # ty: ignore[unresolved-attribute]

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

    def set_focus_trajectory(
        self,
        trajectory: list,  # ty: ignore[missing-type-argument]
        config: object | None,
    ) -> None:
        """Provide the focus trajectory samples + frozen config so
        ``finalize`` can publish the ``/acquisition/focus`` group. Called
        by the save worker before finalize when focus is enabled. An empty
        trajectory or None config means fixed mode — no focus group is
        written.
        """
        self._focus_trajectory = list(trajectory) if trajectory else []
        self._focus_config = config

    def _write_focus_group(self) -> None:
        """Write the ``/acquisition/focus`` group via the writer's public
        ``root`` handle.

        Called AFTER ``finalize_with_resolutions`` and after
        ``_write_adaptive_group`` so the focus group is a sibling under
        ``/acquisition``. The group carries one row per focus block with
        the same field names as the HDF5 ``/focus_trajectory`` group:
        block_index, stage_pos_mm, feedforward_camera_pos_mm,
        residual_mm, applied_camera_pos_mm, sharpness_metric. The frozen
        FocusConfig block size + residual settings are published as group
        attrs. No-op when the trajectory is empty (fixed mode).
        """
        if not self._focus_trajectory:
            return
        if self._writer is None:
            raise RuntimeError("ZarrSaver._write_focus_group called with no writer")
        root = self._writer.root
        acq = root["acquisition"]
        grp = acq.create_group("focus")  # ty: ignore[unresolved-attribute]
        traj = self._focus_trajectory
        cfg = self._focus_config

        if cfg is not None:
            grp.attrs["enabled"] = bool(cfg.enabled)  # ty: ignore[unresolved-attribute]
            grp.attrs["block_size_n"] = int(cfg.block_size_n)  # ty: ignore[unresolved-attribute]
            grp.attrs["autofocus_residual"] = bool(cfg.autofocus_residual)  # ty: ignore[unresolved-attribute]
            grp.attrs["curve_path"] = str(cfg.curve_path)  # ty: ignore[unresolved-attribute]
            grp.attrs["residual_gain_mm"] = float(cfg.residual_gain_mm)  # ty: ignore[unresolved-attribute]
            grp.attrs["max_residual_mm"] = float(cfg.max_residual_mm)  # ty: ignore[unresolved-attribute]

        grp.create_array(
            "block_index",
            data=np.array([s.block_index for s in traj], dtype=int),
        )
        grp.create_array(
            "stage_pos_mm",
            data=np.array([s.stage_pos_mm for s in traj], dtype=float),
        )
        grp.create_array(
            "feedforward_camera_pos_mm",
            data=np.array([s.feedforward_camera_pos_mm for s in traj], dtype=float),
        )
        grp.create_array(
            "residual_mm",
            data=np.array([s.residual_mm for s in traj], dtype=float),
        )
        grp.create_array(
            "applied_camera_pos_mm",
            data=np.array([s.applied_camera_pos_mm for s in traj], dtype=float),
        )
        sharpness = [
            s.sharpness_metric if s.sharpness_metric is not None else float("nan")
            for s in traj
        ]
        grp.create_array(
            "sharpness_metric",
            data=np.array(sharpness, dtype=float),
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
        omero_channels = self._build_omero_channels(self.parent.lasers)  # ty: ignore[invalid-argument-type]

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
        # back-compat path — no auto-laser flag was set so no
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
        self._writer.finalize_with_resolutions(  # ty: ignore[unresolved-attribute]
            base_res=base_res,
            target_resolutions_um=(10, 25, 50, 100),
            make_isotropic=True,
            omero_channels=omero_channels,
        )
        logger.info("Zarr finalize_with_resolutions took %.2fs", time.time() - t0)
        self._write_acquisition_group()
        # Write the adaptive trajectory group after /acquisition so it
        # is a sibling under /acquisition/adaptive. No-op
        # when the trajectory is empty (fixed mode).
        self._write_adaptive_group()
        # Write the focus trajectory group after /acquisition/adaptive so
        # it is a sibling under /acquisition/focus. No-op when the
        # trajectory is empty (fixed mode).
        self._write_focus_group()
        self._finalized = True
        self.saving_started = False
