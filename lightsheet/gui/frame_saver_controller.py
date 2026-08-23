"""FrameSaverController — god-object split collaborator.

Owns the ``FrameSaver`` + ``FrameViewer`` QObject instances and routes the
shell's save/enqueue calls through to them. The ``FrameSaver`` and
``FrameViewer`` QObject classes are DEFINED in this module (moved verbatim
from ``lightsheet/gui/controller.py`` — a behavior-preserving mechanical
relocation). The shell delegates through ``self._fs``.

This is a plain-Python object (NOT a ``QObject``) per the plain-Python collaborator pattern
1: collaborators emit through a shell reference, never declare their own
``pyqtSignal``, and never call ``.connect()``. The one exception is the
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
from typing import TYPE_CHECKING

import h5py
import numpy as np
from PyQt5.QtCore import QObject, pyqtSignal

from lightsheet.hal.bundle import DeviceBundle

if TYPE_CHECKING:
    from lightsheet.gui.controller import Controller_MainWindow

logger = logging.getLogger(__name__)


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

    def enqueue_frame(self, frame: np.uint16) -> None:
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


class FrameSaver(QObject):
    """Class for storing buffers (images) in its queue and saving them
    afterwards in a specified directory in a HDF5 format"""

    sig_status_message = pyqtSignal(str)

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

    def reinit(self, block_size: int) -> None:
        if self.saving_started:
            self.saving_started = False

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
        are unique in the path to avoid overwrite on other files"""
        self.number_of_files = int(number_of_files)
        self.files_name = str(files_name)
        self.scan_type = str(scan_type)
        self.number_of_datasets = int(number_of_datasets)
        self.datasets_name = str(datasets_name)

        counter = 0
        for _ in range(self.number_of_files):
            while True:
                counter += 1
                new_filename = (
                    self.files_name
                    + "_"
                    + scan_type
                    + "_plane_"
                    + f"{counter:05d}"
                    + ".hdf5"
                )
                if not os.path.isfile(new_filename):  # Check for existing files
                    self.filenames_list.append(new_filename)
                    break

    # Saving methods

    def enqueue_buffer(self, buffer: np.ndarray) -> None:
        """Put an image in the save queue"""
        self.queue.put(item=buffer, block=True)

    def start_saving(self) -> None:
        """Initiates saving thread"""
        self.saving_started = True
        self.frame_saver_thread = threading.Thread(target=self.frame_saver_worker)
        self.frame_saver_thread.start()

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

    def frame_saver_worker(self) -> None:
        """Thread for saving 3D arrays (or 2D arrays).
        The number of datasets per file is the number of 2D arrays"""
        for idx in range(len(self.filenames_list)):
            print("File created:" + str(self.filenames_list[idx]))  # debugging
            # Create file
            outfile = h5py.File(self.filenames_list[idx], "a")
            # Write per-laser metadata as file-level root attrs once per
            # file, read from the live list[ILaser] the controller holds
            # (never re-parsed from config.ini — fixes the config-drift
            # metadata bug). All configured lasers are included, even
            # inactive ones (power=0, active=False), for reproducibility.
            self._write_laser_metadata(outfile)

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
                            print(
                                "Dataset "
                                + str(dataset)
                                + "/"
                                + str(int(self.number_of_datasets))
                                + " created:"
                                + str(path_root)
                            )  # debugging

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
                    except Exception:
                        if not self.saving_started:
                            break
                if not self.saving_started:
                    break
            outfile.close()
            self.sig_status_message.emit("File " + self.filenames_list[idx] + " saved")
            if not self.saving_started:
                break

    def stop_saving(self) -> None:
        """Changes the flag status to end the saving thread"""
        self.saving_started = False
        # self.frame_saver_thread.join()


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
