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

    def updateUi_select_file(self) -> None:
        """Allows the selection of a file (.hdf5), opens it and displays its datasets"""

        # Retrieve File
        self._shell.open_directory = QFileDialog.getOpenFileName(
            self._shell, "Choose File", "", "Hierarchical files (*.hdf5)"
        )[0]

        if self._shell.open_directory != "":  # If file directory specified
            self.ui.label_currentFileDirectory.setText(self._shell.open_directory)
            self.ui.listWidget_fileDatasets.clear()

            # Open the file and display its datasets. A corrupt or
            # non-HDF5 file (e.g. a truncated download) raises OSError
            # or h5py.h5o.KeyError from h5py.File — handle it gracefully
            # with a user-facing message instead of crashing the GUI
            # thread (mirrors past_acquisitions_browser.py:242-253).
            import h5py

            try:
                with h5py.File(self._shell.open_directory, "r") as f:
                    dataset_names = list(f.keys())
                    for item in range(len(dataset_names)):
                        self.ui.listWidget_fileDatasets.insertItem(
                            item, dataset_names[item]
                        )
            except (OSError, KeyError) as exc:
                self._shell.sig_message.emit(
                    f"Could not open {self._shell.open_directory}: {exc}"
                )
                self.ui.label_currentFileDirectory.setText("None Specified")
                return
            self.ui.listWidget_fileDatasets.setCurrentRow(0)
            self._shell.updateUi_message_printer("File " + self._shell.open_directory + " opened")  # noqa: E501
            self.ui.pushButton_selectDataset.setEnabled(True)
        else:
            self.ui.label_currentFileDirectory.setText("None Specified")

    def updateUi_select_dataset(self) -> None:
        """
        Opens one or many HDF5 datasets and displays its attributes and data as an image
        """
        if (self._shell.open_directory != "") and (
            self.ui.listWidget_fileDatasets.count() != 0
        ):
            import h5py
            from matplotlib import pyplot as plt

            for item in range(len(self.ui.listWidget_fileDatasets.selectedItems())):  # noqa: E501
                self._shell.dataset_name = self.ui.listWidget_fileDatasets.selectedItems()[  # noqa: E501
                    item
                ].text()
                # Wrap the h5py open + dataset access in try/except — a
                # corrupt or non-HDF5 file (or a missing dataset key)
                # raises OSError / KeyError from h5py.File or the dataset
                # lookup. Emit a user-facing message and skip this item
                # instead of crashing the GUI thread.
                try:
                    with h5py.File(self._shell.open_directory, "r") as f:
                        dataset = f[self._shell.dataset_name]

                        # Display attributes of the first selected dataset
                        if item == 0:
                            self.ui.label_currentDataset.setText(self._shell.dataset_name)
                            attribute_names = list(dataset.attrs.keys())
                            attribute_values = list(dataset.attrs.values())
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
                        data = dataset[()]
                        plt.figure(self._shell.open_directory + " (" + self._shell.dataset_name + ")")  # noqa: E501
                        plt.imshow(data, cmap="gray")
                        plt.show(
                            block=False
                        )  # Prevents the plot from blocking the execution of the code...
                except (OSError, KeyError) as exc:
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
        tmp_string = "".join(safe_char(c) for c in tmp_string).rstrip("_")

        if tmp_string != "":
            self._shell.save_filename = tmp_string

        if (self._shell.save_directory != "") and (self._shell.save_filename != ""):
            self._shell.save_filename = os.path.normpath(
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
                    1, self._shell.save_filename, "singleImage", 1, "ETLscan"
                )
                cropped_buffer = self._shell._fs.crop_buffer(self._shell.buffer)
                self._shell._fs.enqueue_buffer(cropped_buffer)
                self._shell.updateUi_message_printer(
                    "Saving Images (one for each ETL scan, cropped)"
                )
            elif self.ui.radioButton_saveAllFull.isChecked():
                self._shell._fs.set_files(
                    1, self._shell.save_filename, "singleImage", 1, "FullETLscan"
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
                self._shell._fs.set_files(
                    1, self._shell.save_filename, "singleImage", 1, "reconstructed_frame"  # noqa: E501
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
