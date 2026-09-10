"""Plain-Python save-worker loops for ``FrameSaver``.

The consume loops moved out of ``frame_saver_controller.py`` verbatim:
each ``run_*_save_loop(saver)`` takes the owning ``FrameSaver`` and reads
every attribute through it — no collaborator state, no HAL handles
(hardware is reached only through ``saver.parent``), same shape as the
``ZarrSaver`` / ``ManifestRecorder`` sibling collaborators.

``FrameSaver`` keeps one-line delegates under the original method names
(``frame_saver_worker``, ``zarr_save_worker``, ``both_save_worker``) so
``FrameSaverWorker.start_saving``'s format dispatch and every existing
test patch target resolve unchanged.

The ``except queue.Empty`` (poll/timeout) and ``except Exception``
(write failure) branches are a deliberate pairing in every loop: a
timeout is polling, never failure state; a write error must surface on
``sig_status_message``, flip ``saving_started``, and exit the loop —
collapsing them would silently retry against a potentially corrupt HDF5
file.
"""

from __future__ import annotations

import contextlib
import datetime
import logging
import queue
from pathlib import Path
from typing import TYPE_CHECKING, cast

import h5py
import numpy as np

from lightsheet.gui.coordinators.reconstruction import _position_to_float
from lightsheet.resume import ResumeProbeError

if TYPE_CHECKING:
    from lightsheet.gui.coordinators.frame_saver_controller import FrameSaver
    from lightsheet.gui.shell.controller import Controller_MainWindow

logger = logging.getLogger(__name__)


def run_hdf5_save_loop(saver: FrameSaver) -> None:
    """Thread for saving 3D arrays (or 2D arrays).
    The number of datasets per file is the number of 2D arrays.

    In multi-channel mode (``saver.filenames_lists`` has more than one
    channel list), the worker branches on the channel tag from the
    dequeued ``(channel_idx, frame)`` tuple to select the correct
    per-channel filename list and plane index. The single-consumer
    queue contract is preserved — one queue, one consume loop, one
    ``sig_finished`` → ``thread.quit`` → ``wait(10000)``. Single-
    channel mode (one channel list) uses the existing
    ``saver.filenames_list`` path unchanged — ``set_files`` populates
    ``filenames_list`` from ``filenames_lists[0]`` so the single-
    channel save loop is byte-identical except for the filename
    suffix.
    """
    if len(saver.filenames_lists) > 1:
        saver._frame_saver_worker_multi_channel()
        return
    aborted = False
    # set_files may not have run (direct-worker tests); the offset
    # math only applies once a fileset exists.
    n_ds = int(getattr(saver, "number_of_datasets", 1) or 1)
    # Resume offset: split the common resume plane into the starting
    # file index and the 1-based dataset counter within that file,
    # so appended datasets continue the torn file's numbering.
    resume_offset = saver._common_resume_plane
    start_file_idx = resume_offset // n_ds if n_ds else 0
    for idx in range(start_file_idx, len(saver.filenames_list)):
        logger.info("File created: %s", saver.filenames_list[idx])
        outfile: h5py.File | None = None
        try:
            # Create file
            outfile = h5py.File(saver.filenames_list[idx], "a")
            # Write per-laser metadata as file-level root attrs once per
            # file, read from the live list[ILaser] the controller holds
            # (never re-parsed from config.ini — fixes the config-drift
            # metadata bug). All configured lasers are included, even
            # inactive ones (power=0, active=False), for reproducibility.
            saver._write_laser_metadata(outfile)
            # Write motor + scan-param + camera root attrs from the
            # live IMotor / SigGen / camera instances (the motor +
            # scan-param half of SAV-03). Same config-drift contract:
            # live instances only, never re-parse config.ini.
            saver._write_acquisition_metadata(outfile)
        except Exception as e:
            # A file-creation or metadata-write error (disk full,
            # permission denied, HDF5 corruption at open) must surface
            # to the operator and stop the worker — same IN-04 contract
            # as the per-dataset error handler below. Without this, a
            # failure to open the file would propagate out of the worker
            # thread as an unhandled exception and the operator would
            # see no message, just a silently-dead save worker.
            # Close the partially opened file before leaving so the
            # descriptor is not leaked.
            if outfile is not None:
                with contextlib.suppress(Exception):
                    outfile.close()
            saver.sig_status_message.emit(f"Save error: {e}")
            saver.saving_started = False
            break

        counter = (resume_offset % n_ds) + 1 if idx == start_file_idx else 1
        for dataset in range(counter - 1, n_ds):
            while True:
                try:
                    # Retrieve buffer
                    buffer: np.ndarray = saver.queue.get(True, 1)
                    if buffer.ndim == 2:
                        buffer = np.expand_dims(
                            buffer, axis=0
                        )  # To consider 2D arrays as a 3D array
                    for frame in range(buffer.shape[0]):  # For each 2D frame
                        # Create dataset
                        path_root = saver.datasets_name + f"{counter:03d}"
                        saver.dataset = outfile.create_dataset(
                            path_root, data=buffer[frame, :, :]
                        )
                        logger.info(
                            "Dataset %s/%s created: %s",
                            dataset,
                            int(saver.number_of_datasets),
                            path_root,
                        )

                        # Add attributes
                        saver.dataset.attrs["Sample Name"] = saver.sample_name
                        saver.dataset.attrs["Date"] = str(datetime.date.today())

                        if buffer.shape[0] == 1:
                            pos_index = dataset + idx * int(saver.number_of_datasets)
                        else:
                            pos_index = idx

                        # Guard against empty/short position lists —
                        # the multi-channel and both paths already guard
                        # the same access. Without this, a save started
                        # before add_motor_parameters has populated the
                        # lists aborts the whole stack with an
                        # IndexError on the first dataset.
                        if pos_index < len(saver.horizontal_positions_list):
                            saver.dataset.attrs["Horizontal Position"] = (
                                saver.horizontal_positions_list[pos_index]
                            )
                            saver.dataset.attrs["Vertical Position"] = (
                                saver.vertical_positions_list[pos_index]
                            )
                            saver.dataset.attrs["Camera Position"] = (
                                saver.camera_positions_list[pos_index]
                            )

                        counter += 1
                        # The committed-plane cursor advances only
                        # after create_dataset + attrs have returned —
                        # it is the durable-on-disk truth, not the
                        # count of frames the producer enqueued. The
                        # cursor is keyed by the channel's first file
                        # path (same convention as the multi-channel
                        # worker) so the resume resolution layer can
                        # find the torn fileset.
                        saver._commit_manifest_cursor(
                            "hdf5",
                            saver.filenames_list[0],
                            idx * n_ds + counter - 1,
                        )
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
                    if not saver.saving_started:
                        try:
                            buffer = saver.queue.get_nowait()
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
                    saver.sig_status_message.emit(f"Save error: {e}")
                    saver.saving_started = False
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
            saver._write_adaptive_hdf5_for_file(
                outfile,
                idx,
                len(saver.filenames_list),
                int(saver.number_of_datasets),
                actual_n_datasets=counter - 1,
            )
            saver._write_focus_hdf5_for_file(
                outfile,
                idx,
                len(saver.filenames_list),
                int(saver.number_of_datasets),
                actual_n_datasets=counter - 1,
            )
        except Exception as e:
            saver.sig_status_message.emit(f"Save error: {e}")
            saver.saving_started = False
            outfile.close()
            break
        outfile.close()
        saver.sig_status_message.emit("File " + saver.filenames_list[idx] + " saved")
        if aborted:
            break
    saver._finalize_manifest()
    logger.info(
        "frame_saver_worker exited (saving_started=%s)", saver.saving_started
    )


def run_zarr_save_loop(saver: FrameSaver) -> None:
    """ZarrSaver-driven save loop body — streams reconstructed frames
    into the L0 OME-Zarr array, then finalizes the pyramid + NGFF
    metadata + /acquisition group on the worker thread BEFORE the
    method returns (so ``sig_finished`` emits after finalize — the
    close-ordering contract).

    Mirrors ``frame_saver_worker``'s queue-consume shape: buffers
    come off ``saver.queue`` (2D or 3D), each frame is written via
    ``saver._zarr_saver.write_plane`` with the per-plane motor
    positions from ``saver.horizontal_positions_list`` etc. The
    store_path is built from ``saver.parent.save_directory`` +
    ``saver.files_name`` + ``.ome.zarr`` (PLAIN path,
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
    if saver.datasets_name in ("ETLscan", "FullETLscan"):
        frames_per_buffer = int(
            getattr(getattr(saver, "parent"), "waveform_cycles", 1) or 1  # noqa: B009
        )
    else:
        frames_per_buffer = 1
    n_planes = (
        saver.number_of_files * int(saver.number_of_datasets) * frames_per_buffer
    )
    store_path = str(
        Path(saver.parent.save_directory) / (saver.files_name + ".ome.zarr")  # ty: ignore[unresolved-attribute]
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
    n_channels = len(saver.filenames_lists) if saver.filenames_lists else 1
    resume_cursors = (
        saver.resume_manifest.cursors.get("zarr", {}) if saver.resume_manifest else {}
    )
    try:
        if store_path in resume_cursors and saver.resume_manifest is not None:
            saver._zarr_saver.resume_stack(
                store_path,
                n_planes,
                n_channels,
                saver.resume_manifest.uuid,
                start_plane=saver._common_resume_plane,
            )
        else:
            saver._zarr_saver.start_stack(
                store_path,
                n_planes,
                n_channels=n_channels,
                acquisition_uuid=saver.acquisition_uuid,
            )
    except ResumeProbeError:
        logger.warning("Zarr resume failed; falling back to _partN store")
        base = saver.files_name + "_part2"
        counter = 2
        while True:
            candidate = f"{base}.ome.zarr"
            save_dir = cast("Controller_MainWindow", saver.parent).save_directory
            fallback_path = str(Path(save_dir) / candidate)
            if not Path(fallback_path).exists():
                break
            counter += 1
            base = f"{saver.files_name}_part{counter}"
        try:
            saver._zarr_saver.start_stack(
                fallback_path,
                n_planes,
                n_channels=n_channels,
                acquisition_uuid=saver.acquisition_uuid,
            )
        except Exception as e:
            saver.sig_status_message.emit(f"Save error: {e}")
            saver.saving_started = False
            return
        store_path = fallback_path
    except Exception as e:
        saver.sig_status_message.emit(f"Save error: {e}")
        saver.saving_started = False
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
    z_idx_per_channel: dict[int, int] = {
        c: saver._zarr_saver.resume_offset(c) for c in range(n_channels)
    }
    try:
        while True:
            # Natural completion (single-channel production only): the
            # producer is still active but channel 0 filled its planes.
            # In multi-channel mode this break is skipped — the drain
            # path (stop_saving) is the only exit, so the last
            # channel-1 frame is never dropped.
            if (
                saver.saving_started
                and n_channels == 1
                and z_idx_per_channel.get(0, 0) >= n_planes
            ):
                break
            try:
                item = saver.queue.get(True, 1)
            except queue.Empty:
                # stop_saving() may have flipped the flag. If so,
                # drain any remaining frames with a non-blocking get
                # before exiting — in demo mode (and on fast rigs)
                # the acquisition queues all frames near-instantly,
                # then stop_saving() flips the flag while frames are
                # still in the queue. Only break if the queue is
                # truly empty (genuine abort or all frames consumed).
                if not saver.saving_started:
                    try:
                        item = saver.queue.get_nowait()
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
                # suffix for the Zarr numeric datasets. cz is the
                # sub-frame z-index; for ETL scans it advances
                # frames_per_buffer times per plane, so use the plane
                # index (cz // frames_per_buffer) when looking up
                # positions. Guard against a short list (defensive).
                # For resumed runs, subtract the existing plane count so
                # the new frames index the new motor-position list.
                pos_index = (
                    cz - saver._zarr_saver.resume_offset(channel_idx)
                ) // frames_per_buffer
                hor = (
                    _position_to_float(saver.horizontal_positions_list[pos_index])
                    if pos_index < len(saver.horizontal_positions_list)
                    else 0.0
                )
                ver = (
                    _position_to_float(saver.vertical_positions_list[pos_index])
                    if pos_index < len(saver.vertical_positions_list)
                    else 0.0
                )
                cam = (
                    _position_to_float(saver.camera_positions_list[pos_index])
                    if pos_index < len(saver.camera_positions_list)
                    else 0.0
                )
                saver._zarr_saver.write_plane(
                    channel_idx, cz, frame[f_idx, :, :], hor, ver, cam
                )
                z_idx_per_channel[channel_idx] = cz + 1
                saver._commit_manifest_cursor(
                    "zarr", store_path, z_idx_per_channel[channel_idx]
                )
    except Exception as e:
        saver.sig_status_message.emit(f"Save error: {e}")
        saver.saving_started = False
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
                saver._zarr_saver.set_adaptive_trajectory(
                    saver.adaptive_trajectory, saver._adaptive_config
                )
                saver._zarr_saver.set_focus_trajectory(
                    saver.focus_trajectory, saver._focus_config
                )
                saver._zarr_saver.finalize()
                saver.sig_status_message.emit("Zarr store " + store_path + " saved")
            except Exception as e:
                saver.sig_status_message.emit(f"Save error: {e}")
                saver.saving_started = False
    saver._finalize_manifest()
    logger.info("zarr_save_worker exited (saving_started=%s)", saver.saving_started)


def run_both_save_loop(saver: FrameSaver) -> None:
    """Single queue-consume loop writing each frame to BOTH the
    OME-Zarr store and the HDF5 files, then finalizes Zarr.

    Replaces the broken two-loop pattern (``zarr_save_worker`` then
    ``frame_saver_worker``) that drained the shared single-consumer
    ``saver.queue`` twice — the Zarr loop consumed every frame, leaving
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

    In multi-channel mode (``saver.filenames_lists`` has more than one
    channel list), the HDF5 half branches on the channel tag from the
    dequeued ``(channel_idx, frame)`` tuple to write to the correct
    per-channel wavelength-suffixed file. The Zarr half keeps the
    existing ``write_plane(z_idx, frame, ...)`` call unchanged
    (channel 0 only) — the ``write_plane`` signature does not yet
    accept a ``channel_idx`` param, so multi-channel Zarr
    channel-tag branching is deferred to a later plan. The
    single-consumer queue contract is preserved. Single-channel mode
    (one channel list) uses the existing ``saver.filenames_list`` path
    — ``set_files`` populates ``filenames_list`` from
    ``filenames_lists[0]``.
    """
    if len(saver.filenames_lists) > 1:
        saver._both_save_worker_multi_channel()
        return

    if saver.datasets_name in ("ETLscan", "FullETLscan"):
        frames_per_buffer = int(
            getattr(getattr(saver, "parent"), "waveform_cycles", 1) or 1  # noqa: B009
        )
    else:
        frames_per_buffer = 1
    n_planes = (
        saver.number_of_files * int(saver.number_of_datasets) * frames_per_buffer
    )
    store_path = str(
        Path(saver.parent.save_directory) / (saver.files_name + ".ome.zarr")  # ty: ignore[unresolved-attribute]
    )
    try:
        saver._zarr_saver.start_stack(store_path, n_planes)
    except Exception as e:
        saver.sig_status_message.emit(f"Save error: {e}")
        saver.saving_started = False
        return

    z_idx = 0
    zarr_pos_index = 0
    aborted = False
    try:
        for idx in range(len(saver.filenames_list)):
            logger.info("File created: %s", saver.filenames_list[idx])
            try:
                outfile = h5py.File(saver.filenames_list[idx], "a")
                saver._write_laser_metadata(outfile)
                saver._write_acquisition_metadata(outfile)
            except Exception as e:
                saver.sig_status_message.emit(f"Save error: {e}")
                saver.saving_started = False
                break

            counter = 1
            for dataset in range(int(saver.number_of_datasets)):
                while True:
                    try:
                        buffer: np.ndarray = saver.queue.get(True, 1)
                        if buffer.ndim == 2:
                            buffer = np.expand_dims(buffer, axis=0)
                        for frame in range(buffer.shape[0]):
                            if z_idx >= n_planes:
                                break
                            # --- HDF5 write (mirrors frame_saver_worker) ---
                            path_root = saver.datasets_name + f"{counter:03d}"
                            saver.dataset = outfile.create_dataset(
                                path_root, data=buffer[frame, :, :]
                            )
                            logger.info(
                                "Dataset %s/%s created: %s",
                                dataset,
                                int(saver.number_of_datasets),
                                path_root,
                            )
                            saver.dataset.attrs["Sample Name"] = saver.sample_name
                            saver.dataset.attrs["Date"] = str(datetime.date.today())

                            if buffer.shape[0] == 1:
                                h5_pos_index = dataset + idx * int(
                                    saver.number_of_datasets
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
                            if h5_pos_index < len(saver.horizontal_positions_list):
                                saver.dataset.attrs["Horizontal Position"] = (
                                    saver.horizontal_positions_list[h5_pos_index]
                                )
                                saver.dataset.attrs["Vertical Position"] = (
                                    saver.vertical_positions_list[h5_pos_index]
                                )
                                saver.dataset.attrs["Camera Position"] = (
                                    saver.camera_positions_list[h5_pos_index]
                                )
                            counter += 1
                            # Committed-plane cursor: only after the
                            # HDF5 dataset write returned (durable
                            # truth, not frames enqueued). Keyed by
                            # the channel's first file path — the same
                            # convention as the HDF5 workers — so the
                            # resume layer can find the torn fileset.
                            saver._commit_manifest_cursor(
                                "hdf5",
                                saver.filenames_list[0],
                                idx * int(saver.number_of_datasets) + counter - 1,
                            )

                            # --- Zarr write (mirrors zarr_save_worker) ---
                            pos_index = zarr_pos_index // frames_per_buffer
                            hor = (
                                _position_to_float(
                                    saver.horizontal_positions_list[pos_index]
                                )
                                if pos_index < len(saver.horizontal_positions_list)
                                else 0.0
                            )
                            ver = (
                                _position_to_float(
                                    saver.vertical_positions_list[pos_index]
                                )
                                if pos_index < len(saver.vertical_positions_list)
                                else 0.0
                            )
                            cam = (
                                _position_to_float(
                                    saver.camera_positions_list[pos_index]
                                )
                                if pos_index < len(saver.camera_positions_list)
                                else 0.0
                            )
                            saver._zarr_saver.write_plane(
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
                        if not saver.saving_started:
                            try:
                                buffer = saver.queue.get_nowait()
                            except queue.Empty:
                                aborted = True
                                break
                        else:
                            continue
                    except Exception as e:
                        saver.sig_status_message.emit(f"Save error: {e}")
                        saver.saving_started = False
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
                saver._write_adaptive_hdf5_for_file(
                    outfile,
                    idx,
                    len(saver.filenames_list),
                    int(saver.number_of_datasets),
                    actual_n_datasets=counter - 1,
                )
                saver._write_focus_hdf5_for_file(
                    outfile,
                    idx,
                    len(saver.filenames_list),
                    int(saver.number_of_datasets),
                    actual_n_datasets=counter - 1,
                )
            except Exception as e:
                saver.sig_status_message.emit(f"Save error: {e}")
                saver.saving_started = False
                outfile.close()
                aborted = True
                break
            outfile.close()
            saver.sig_status_message.emit(
                "File " + saver.filenames_list[idx] + " saved"
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
                saver._zarr_saver.set_adaptive_trajectory(
                    saver.adaptive_trajectory, saver._adaptive_config
                )
                saver._zarr_saver.set_focus_trajectory(
                    saver.focus_trajectory, saver._focus_config
                )
                saver._zarr_saver.finalize()
                saver.sig_status_message.emit("Zarr store " + store_path + " saved")
            except Exception as e:
                saver.sig_status_message.emit(f"Save error: {e}")
                saver.saving_started = False
    except Exception as e:
        saver.sig_status_message.emit(f"Save error: {e}")
        saver.saving_started = False
    saver._finalize_manifest()
    logger.info("both_save_worker exited (saving_started=%s)", saver.saving_started)
