"""Plain-Python save-worker loops for ``FrameSaver``.

The single-channel HDF5 consume loop moved out of
``frame_saver_controller.py`` verbatim: ``run_hdf5_save_loop(saver)``
takes the owning ``FrameSaver`` and reads every attribute through it —
no collaborator state, no HAL handles (hardware is reached only through
``saver.parent``), same shape as the ``ZarrSaver`` / ``ManifestRecorder``
sibling collaborators.

``FrameSaver.frame_saver_worker`` remains as a one-line delegate so
``FrameSaverWorker.start_saving``'s format dispatch and every existing
test patch target resolve unchanged.

The ``except queue.Empty`` (poll/timeout) and ``except Exception``
(write failure) branches are a deliberate pairing: a timeout is polling,
never failure state; a write error must surface on
``sig_status_message``, flip ``saving_started``, and exit the loop —
collapsing them would silently retry against a potentially corrupt HDF5
file.
"""

from __future__ import annotations

import contextlib
import datetime
import logging
import queue
from typing import TYPE_CHECKING

import h5py
import numpy as np

if TYPE_CHECKING:
    from lightsheet.gui.coordinators.frame_saver_controller import FrameSaver

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
