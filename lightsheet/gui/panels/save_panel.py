"""SavePanelWidget — per-panel widget/controller for save/file-manager controls.

Owns the save updateUi_* slots grouped by concern (D-01 gui modularization):
file/dataset/directory selection and single-image save. Reads
``self._shell.ui.<objectName>`` for its widgets (the shell's composed widget
tree) and ``self._shell._fs`` / ``self._shell.save_*`` for shell-owned
state. Emits through ``self._shell.sig_*``.
"""

from __future__ import annotations

import os
import typing

from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QMessageBox,
    QTableWidgetItem,
    QWidget,
)

from lightsheet.gui.panels.ui_save_panel import Ui_SavePanel
from lightsheet.gui.widgets.field_spec import FIELD_SPECS

if typing.TYPE_CHECKING:
    from lightsheet.gui.shell.controller import Controller_MainWindow


class SavePanelWidget(QWidget):
    """Save/file-manager controls panel — owns file selection and
    single-image save slots."""

    def __init__(self, shell: Controller_MainWindow) -> None:
        super().__init__()
        self._shell = shell
        self.ui = Ui_SavePanel()
        self.ui.setupUi(self)
        # Apply the declarative FieldSpec policy table to every promoted
        # FieldSpecSpinBox by objectName. save_panel has no
        # FieldSpecSpinBox widgets, so the loop is a no-op (getattr →
        # None for every key); it is kept for mechanical consistency
        # across all 7 panels.
        for obj_name, spec in FIELD_SPECS.items():
            w = getattr(self.ui, obj_name, None)
            if w is not None and hasattr(w, "applySpec"):
                w.applySpec(spec)

    def _active_single_channel_wavelength(self) -> int:
        """Return the active laser wavelength for single-channel mode.

        Reads the cached ``_auto_laser1`` / ``_auto_laser2`` flags on the
        shell (sampled at acquisition start by
        ``_cache_auto_laser_flags``) and returns the wavelength of the
        laser that will actually fire:

        - ``_auto_laser1`` -> ``lasers[0].wavelength``
        - ``_auto_laser2`` (only L2 checked) -> ``lasers[1].wavelength``
        - neither checked (manual mode / edge case) -> ``lasers[0].wavelength``
          as the fallback

        The wavelength is read from the live ``ILaser`` instance set at
        startup from ``config.ini`` — a trusted value, never hardcoded.
        Single-channel callers pass ``[this]`` to ``set_files`` so the
        saved HDF5 filename carries the ``_{wavelength}nm`` suffix.
        """
        shell = self._shell
        if getattr(shell, "_auto_laser1", False):
            return int(shell.lasers[0].wavelength)
        if getattr(shell, "_auto_laser2", False):
            return int(shell.lasers[1].wavelength)
        return int(shell.lasers[0].wavelength)

    def updateUi_select_file(self) -> None:
        """Allows the selection of an HDF5 file OR an OME-Zarr store
        folder, opens it, and lists its datasets/planes.

        A single non-native file dialog in Directory mode with
        ``ShowDirsOnly=False`` lets the operator pick EITHER a file
        (HDF5, .hdf5) OR a folder (OME-Zarr store, .ome.zarr) in one
        step — the documented Qt way to allow both files and
        directories in a single dialog. A single combined name filter
        lists both formats. The open logic branches on
        ``os.path.isdir``: directory → Zarr store, file → HDF5. A
        corrupt or wrong-format path raises OSError / KeyError /
        ValueError — handled gracefully with a user-facing message
        instead of crashing the GUI thread.
        """

        # Non-native dialog in Directory mode (ShowDirsOnly NOT set) so
        # the operator can select either a file or a folder in one
        # step. ExistingFile mode cannot select a folder (Open navigates
        # into it); Directory mode with ShowDirsOnly=False is the only
        # single-dialog way to accept both.
        dlg = QFileDialog(
            self._shell,
            "Choose HDF5 file or OME-Zarr store",
            self._shell.save_directory or "",
        )
        dlg.setFileMode(QFileDialog.FileMode.Directory)
        dlg.setOption(QFileDialog.Option.ShowDirsOnly, False)
        dlg.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        dlg.setNameFilters([
            "Lightsheet acquisition files (*.hdf5 *.ome.zarr *.zarr)",
            "HDF5 (*.hdf5)",
            "OME-Zarr (*.ome.zarr *.zarr)",
        ])
        if not dlg.exec():
            self.ui.label_currentFileDirectory.setText("None Specified")
            return
        selected = dlg.selectedFiles()
        if not selected:
            self.ui.label_currentFileDirectory.setText("None Specified")
            return
        path = selected[0]

        self._shell.open_directory = path
        self.ui.label_currentFileDirectory.setText(path)
        self.ui.listWidget_fileDatasets.clear()

        # Branch on type: directory → Zarr store, file → HDF5.
        try:
            if os.path.isdir(path):
                dataset_names = self._list_zarr_datasets(path)
            else:
                dataset_names = self._list_hdf5_datasets(path)
        except (OSError, KeyError, ValueError) as exc:
            self._shell.sig_message.emit(
                f"Could not open {path}: {exc}"
            )
            self.ui.label_currentFileDirectory.setText("None Specified")
            return

        for item in range(len(dataset_names)):
            self.ui.listWidget_fileDatasets.insertItem(
                item, dataset_names[item]
            )
        self.ui.listWidget_fileDatasets.setCurrentRow(0)
        self._shell.updateUi_message_printer("File " + path + " opened")
        self.ui.pushButton_selectDataset.setEnabled(True)

    def _list_hdf5_datasets(self, path: str) -> list[str]:
        """Open an HDF5 file and return its top-level dataset names."""
        import h5py

        with h5py.File(path, "r") as f:
            return list(f.keys())

    def _list_zarr_datasets(self, path: str) -> list[str]:
        """Open an OME-Zarr store and return a list of selectable
        plane labels for the L0 multiscale array.

        The writer produces a 4D ``(c, z, y, x)`` L0 array at
        ``root["0"]``. For multi-channel stores (c > 1) the labels are
        ``ch0_plane_0001``, ``ch1_plane_0001``, ... so the operator can
        view any (channel, plane); for single-channel stores (c == 1)
        the labels are just ``plane_0001``, ``plane_0002``, ...
        (matching the HDF5 ``reconstructed_frameNNN`` UX). Raises
        ``ValueError`` if the store has no L0 array or an unexpected
        shape so the caller's except path surfaces a clear message.
        """
        import zarr

        root = zarr.open_group(path, mode="r")
        arr = root.get("0")
        if arr is None:
            raise ValueError("OME-Zarr store has no multiscale '0' array")
        shape = getattr(arr, "shape", None)
        if not shape or len(shape) < 3:
            raise ValueError(
                f"OME-Zarr L0 array has unexpected shape {shape!r} "
                f"(expected (c, z, y, x) or (z, y, x))"
            )
        # 4D (c, z, y, x) — channel-aware labels. 3D (z, y, x) —
        # single-channel fallback (treat as c=1).
        if len(shape) == 4:
            n_channels, n_planes = int(shape[0]), int(shape[1])
        else:
            n_channels, n_planes = 1, int(shape[0])
        labels: list[str] = []
        for ch in range(n_channels):
            for z in range(n_planes):
                if n_channels > 1:
                    labels.append(f"ch{ch}_plane_{z + 1:04d}")
                else:
                    labels.append(f"plane_{z + 1:04d}")
        return labels

    def updateUi_select_dataset(self) -> None:
        """
        Opens one or many datasets (HDF5 or OME-Zarr) and displays the
        attributes and image of each.
        """
        if (self._shell.open_directory != "") and (
            self.ui.listWidget_fileDatasets.count() != 0
        ):
            from matplotlib import pyplot as plt

            is_zarr = os.path.isdir(self._shell.open_directory)
            for item in range(len(self.ui.listWidget_fileDatasets.selectedItems())):  # noqa: E501
                self._shell.dataset_name = self.ui.listWidget_fileDatasets.selectedItems()[  # noqa: E501
                    item
                ].text()
                # Wrap the open + dataset access in try/except — a
                # corrupt file/store or a missing dataset key raises
                # OSError / KeyError / ValueError. Emit a user-facing
                # message and skip this item instead of crashing the GUI
                # thread.
                try:
                    if is_zarr:
                        data, attrs = self._read_zarr_dataset(
                            self._shell.open_directory,
                            self._shell.dataset_name,
                        )
                    else:
                        data, attrs = self._read_hdf5_dataset(
                            self._shell.open_directory,
                            self._shell.dataset_name,
                        )

                    # Display attributes of the first selected dataset
                    if item == 0:
                        self.ui.label_currentDataset.setText(self._shell.dataset_name)
                        attribute_names = list(attrs.keys())
                        attribute_values = list(attrs.values())
                        self.ui.tableWidget_fileAttributes.setColumnCount(2)
                        self.ui.tableWidget_fileAttributes.setRowCount(
                            len(attribute_names)
                        )
                        self.ui.tableWidget_fileAttributes.setHorizontalHeaderItem(
                            0, QTableWidgetItem("Attributes")
                        )
                        self.ui.tableWidget_fileAttributes.setHorizontalHeaderItem(
                            1, QTableWidgetItem("Values")
                        )
                        for attribute in range(0, len(attribute_names)):
                            self.ui.tableWidget_fileAttributes.setItem(
                                attribute,
                                0,
                                QTableWidgetItem(attribute_names[attribute]),
                            )
                            self.ui.tableWidget_fileAttributes.setItem(
                                attribute,
                                1,
                                QTableWidgetItem(str(attribute_values[attribute])),
                            )
                        self.ui.tableWidget_fileAttributes.resizeColumnsToContents()
                        self.ui.tableWidget_fileAttributes.setEditTriggers(
                            QAbstractItemView.NoEditTriggers
                        )  # No editing possible

                    # Display image
                    plt.figure(self._shell.open_directory + " (" + self._shell.dataset_name + ")")  # noqa: E501
                    plt.imshow(data, cmap="gray")
                    plt.show(
                        block=False
                    )  # Prevents the plot from blocking the execution of the code...
                except (OSError, KeyError, ValueError) as exc:
                    self._shell.sig_message.emit(
                        f"Could not open dataset {self._shell.dataset_name} "
                        f"in {self._shell.open_directory}: {exc}"
                    )
                    continue

                self._shell.updateUi_message_printer(
                    "Dataset "
                    + self._shell.dataset_name
                    + " of file "
                    + self._shell.open_directory
                    + " displayed"
                )

    def _read_hdf5_dataset(self, path: str, name: str):
        """Open an HDF5 file, return ``(data, attrs)`` for the named
        top-level dataset."""
        import h5py

        with h5py.File(path, "r") as f:
            dataset = f[name]
            return dataset[()], dict(dataset.attrs)

    def _read_zarr_dataset(self, path: str, label: str):
        """Open an OME-Zarr store, return ``(data, attrs)`` for the
        plane identified by ``label`` (``plane_NNNN`` or
        ``chN_plane_NNNN`` as produced by ``_list_zarr_datasets``).

        Returns the 2D ``(y, x)`` slice for the requested (channel,
        plane) from the L0 multiscale array, plus the L0 array's attrs
        (Zarr stores per-plane metadata at the group/array level, not
        per-slice, so the attrs panel shows the array-level metadata).
        """
        import re

        import zarr

        m = re.match(r"(?:ch(\d+)_)?plane_(\d+)", label)
        if not m:
            raise ValueError(f"unrecognized zarr plane label: {label}")
        ch = int(m.group(1)) if m.group(1) is not None else 0
        z = int(m.group(2)) - 1  # label is 1-based; array index is 0-based
        root = zarr.open_group(path, mode="r")
        arr = root["0"]
        shape = arr.shape
        if len(shape) == 4:
            data = arr[ch, z, :, :]
        else:
            data = arr[z, :, :]
        return data, dict(arr.attrs)

    def updateUi_select_directory(self) -> None:
        """Allows the selection of a directory for single scan or stack saving"""
        options = (
            QFileDialog.Option.DontResolveSymlinks
            | QFileDialog.Option.ShowDirsOnly
        )
        tmp_directory = QFileDialog.getExistingDirectory(
            self._shell, "Choose Directory", self._shell.save_directory, options
        )
        if tmp_directory != "":
            self._shell.save_directory = os.path.normpath(tmp_directory)

        if self._shell.save_directory != "":
            self.ui.lineEdit_saveDirectory.setText(self._shell.save_directory)
            self.ui.lineEdit_saveFilename.setText("")
            self.ui.lineEdit_saveFilename.setEnabled(True)
            self.ui.lineEdit_saveDescription.setText("")
            self.ui.lineEdit_saveDescription.setEnabled(True)
        else:
            self.ui.lineEdit_saveDirectory.setText("")
            self.ui.lineEdit_saveFilename.setPlaceholderText(
                "Filename - Select Save Directory First"
            )
            self.ui.lineEdit_saveFilename.setEnabled(False)
            self.ui.lineEdit_saveDescription.setPlaceholderText(
                "Description - Select Save Directory First"
            )
            self.ui.lineEdit_saveDescription.setEnabled(False)

    def validate_file_name(self) -> None:
        """Validate filename set by the user"""

        # To validate individual char. Only alphanumeric, - and _ characters are permitted  # noqa: E501
        def safe_char(c: str) -> str:
            if c.isalnum() or c == "-":
                return c
            else:
                return "_"

        tmp_string = self.ui.lineEdit_saveFilename.text()
        # safe_char maps every non-alnum/non-"-" char (including spaces)
        # to "_". Strip leading/trailing underscores so leading spaces
        # don't produce a "__hello" filename (rstrip would only clear the
        # trailing end).
        tmp_string = "".join(safe_char(c) for c in tmp_string).strip("_")

        if tmp_string != "":
            self._shell.save_filename = tmp_string

        # save_filename holds the bare sanitized name; save_filepath holds
        # the joined absolute path passed to FrameSaver.set_files (whose
        # ``files_name`` arg is a path prefix, not a bare filename — see
        # frame_saver_controller.py:278-285). Keeping the two separate
        # avoids the lineEdit restore at controller.py:427 ever showing a
        # full path in the filename field.
        if (self._shell.save_directory != "") and (self._shell.save_filename != ""):
            self._shell.save_filepath = os.path.normpath(
                os.path.join(self._shell.save_directory, self._shell.save_filename)
            )
            self._shell.saving_allowed = True
        else:
            self._shell.saving_allowed = False

    def updateUi_save_single_image(self) -> None:
        """Saves the frame generated by self.get_single_image()"""

        # Check that filename is valid and saving is allowed
        self.validate_file_name()

        if self._shell.saving_allowed:
            # Getting sample name
            self._shell.save_description = str(self.ui.lineEdit_saveDescription.text())  # noqa: E501

            """Setting up frame saver"""
            self._shell._fs.reinit(1)
            self._shell._fs.add_sample_name(self._shell.save_description)
            self._shell._fs.add_motor_parameters(
                self._shell.image_hor_pos_text,
                self._shell.image_ver_pos_text,
                self._shell.image_cam_pos_text,
            )

            """Saving frame"""
            if self.ui.radioButton_saveAllCrop.isChecked():
                self._shell._fs.set_files(
                    1, self._shell.save_filepath, "singleImage", 1, "ETLscan",
                    wavelengths=[self._active_single_channel_wavelength()],
                )
                cropped_buffer = self._shell._fs.crop_buffer(self._shell.buffer)
                self._shell._fs.enqueue_buffer(cropped_buffer)
                self._shell.updateUi_message_printer(
                    "Saving Images (one for each ETL scan, cropped)"
                )
            elif self.ui.radioButton_saveAllFull.isChecked():
                self._shell._fs.set_files(
                    1, self._shell.save_filepath, "singleImage", 1, "FullETLscan",
                    wavelengths=[self._active_single_channel_wavelength()],
                )
                self._shell._fs.enqueue_buffer(self._shell.buffer)
                self._shell.updateUi_message_printer(
                    "Saving Images (one for each ETL scan, full)"
                )
            else:
                # radioButton_saveStitch (the default "Stitched - No blend"
                # option) falls through to this branch — it is the
                # reconstructed_frame save mode. The radio is in the
                # exclusive save_option_button_group but is not explicitly
                # checked here because it is the implicit default (the
                # else branch covers it).
                #
                # Multi-channel single mode (both auto-laser checkboxes
                # checked): write TWO wavelength-suffixed HDF5 files, one
                # per channel. The wavelengths are read from the live
                # ILaser instances so a rig with different lasers produces
                # the correct suffixes. The per-channel frames come from
                # the reconstructed_frames dict (keyed by laser
                # wavelength, populated by the single-mode acquisition
                # worker). The two tagged (channel_idx, frame) tuples go
                # through the same enqueue_buffer → single save queue →
                # single frame_saver_worker consumer; the worker branches
                # on the channel tag to pick the per-channel filename
                # list. Single-channel mode (one auto-laser checked, or
                # neither) passes wavelengths=[active_wavelength] so the
                # saved file carries the _{wavelength}nm suffix; the
                # frame is enqueued as a bare ndarray.
                multi_channel = (
                    self._shell._auto_laser1 and self._shell._auto_laser2
                )
                if multi_channel:
                    wl1 = self._shell.lasers[0].wavelength
                    wl2 = self._shell.lasers[1].wavelength
                    # Guard against a partial acquisition: the single-mode
                    # multi-channel worker only adds a wavelength key to
                    # reconstructed_frames when that channel's frame was
                    # captured (a camera timeout or siggen error on one
                    # channel leaves the dict missing that key). Indexing
                    # the dict directly would raise KeyError; use .get()
                    # and abort the save with an operator message instead.
                    frame1 = self._shell.reconstructed_frames.get(wl1)
                    frame2 = self._shell.reconstructed_frames.get(wl2)
                    if frame1 is None or frame2 is None:
                        self._shell.updateUi_message_printer(
                            "Cannot save — one or both channel frames are "
                            "missing. Re-run the acquisition."
                        )
                        return
                    self._shell._fs.set_files(
                        1, self._shell.save_filepath, "singleImage", 1,
                        "reconstructed_frame", wavelengths=[wl1, wl2],
                    )
                    self._shell._fs.enqueue_buffer((0, frame1))
                    self._shell._fs.enqueue_buffer((1, frame2))
                    self._shell.updateUi_message_printer(
                        "Saving Reconstructed Images (multi-channel)"
                    )
                else:
                    self._shell._fs.set_files(
                        1, self._shell.save_filepath, "singleImage", 1,
                        "reconstructed_frame",
                        wavelengths=[self._active_single_channel_wavelength()],
                    )
                    self._shell._fs.enqueue_buffer(self._shell.reconstructed_frame)
                    self._shell.updateUi_message_printer("Saving Reconstructed Image")

            self._shell._fs.start_saving()
            self._shell._fs.stop_saving()
        else:
            self._shell.sig_beep.emit()
            QMessageBox.warning(
                self._shell,
                "Save Warning",
                "Select a directory and enter a valid filename before saving",
                QMessageBox.StandardButton.Ok,
                QMessageBox.StandardButton.Ok,
            )
            self._shell.sig_message.emit(
                "Select a directory and enter a valid filename before saving"
            )
