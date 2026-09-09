"""Behavior tests for the reactive SaveOptions widget bindings.

The save description line edit and the four exclusive save-mode radios are
projections of ``MicroscopeState.save_options``: widget edits commit through
``set_save_description`` / ``set_save_mode`` and model changes render back
through ``sig_save_options_changed`` under echo guards. The single-image save
path reads the model snapshot instead of widgets or a mutable shell store.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import numpy as np
import pytest

pytest.importorskip("PySide6")

from pytestqt.qtbot import QtBot

from lightsheet.state import SaveMode, SaveOptions

if TYPE_CHECKING:
    from lightsheet.gui.shell.controller import Controller_MainWindow

_MODE_RADIO = {
    SaveMode.STITCH: "radioButton_saveStitch",
    SaveMode.STITCH_BLEND: "radioButton_saveStitchBlend",
    SaveMode.ALL_CROP: "radioButton_saveAllCrop",
    SaveMode.ALL_FULL: "radioButton_saveAllFull",
}


def _checked_modes(ctrl: Controller_MainWindow) -> list[SaveMode]:
    return [
        mode
        for mode, name in _MODE_RADIO.items()
        if getattr(ctrl.save_panel.ui, name).isChecked()
    ]


def test_description_edit_commits_to_model(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """editingFinished on the description line edit commits the exact text
    to the model."""
    ctrl = controller
    edit = ctrl.save_panel.ui.lineEdit_saveDescription
    edit.setText("  sample A  ")
    edit.editingFinished.emit()
    assert ctrl.state.snapshot().save_options.description == "  sample A  "


def test_each_radio_commits_its_save_mode(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """Clicking each exclusive radio stores the matching SaveMode and leaves
    exactly one radio checked."""
    ctrl = controller
    for mode, name in _MODE_RADIO.items():
        getattr(ctrl.save_panel.ui, name).click()
        assert ctrl.state.snapshot().save_options.mode == mode
        assert _checked_modes(ctrl) == [mode]


def test_model_mode_checks_exactly_one_radio(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """set_save_mode(ALL_CROP) checks only radioButton_saveAllCrop and emits
    exactly one model change (no echo loop back into a second commit)."""
    ctrl = controller
    emissions: list[SaveOptions] = []
    ctrl.state.sig_save_options_changed.connect(emissions.append)
    ctrl.state.set_save_mode(SaveMode.ALL_CROP)
    assert len(emissions) == 1
    assert _checked_modes(ctrl) == [SaveMode.ALL_CROP]


def test_model_projection_sets_all_four_modes(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """Every SaveMode projects onto its own radio through the model."""
    ctrl = controller
    for mode in _MODE_RADIO:
        ctrl.state.set_save_options(SaveOptions(description="d", mode=mode))
        assert _checked_modes(ctrl) == [mode]
        assert ctrl.save_panel.ui.lineEdit_saveDescription.text() == "d"


def test_projection_rejects_non_save_options(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """The projection slot ignores wrong-payload emissions."""
    ctrl = controller
    edit = ctrl.save_panel.ui.lineEdit_saveDescription
    before = edit.text()
    ctrl.save_panel.updateUi_save_options_from_state(object())
    ctrl.save_panel.updateUi_save_options_from_state("not options")
    assert edit.text() == before


def test_unchanged_description_does_not_emit(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """Committing the already-current description suppresses the signal."""
    ctrl = controller
    current = ctrl.state.snapshot().save_options.description
    with qtbot.assertNotEmitted(ctrl.state.sig_save_options_changed, wait=100):
        ctrl.state.set_save_description(current)


def test_projection_does_not_echo_back_to_model(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """A model-originated projection updates the widgets without triggering
    a second model write (the blockSignals echo guard)."""
    ctrl = controller
    emissions: list[SaveOptions] = []
    ctrl.state.sig_save_options_changed.connect(emissions.append)
    ctrl.state.set_save_options(
        SaveOptions(description="echo check", mode=SaveMode.STITCH_BLEND)
    )
    assert len(emissions) == 1
    assert ctrl.save_panel.ui.lineEdit_saveDescription.text() == "echo check"
    assert _checked_modes(ctrl) == [SaveMode.STITCH_BLEND]


def test_directory_clear_commits_empty_description(
    qtbot: QtBot, controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """Selecting a directory clears the description field; the empty text is
    committed so model and widget cannot diverge."""
    ctrl = controller
    ctrl.state.set_save_description("leftover")
    assert ctrl.save_panel.ui.lineEdit_saveDescription.text() == "leftover"

    with patch(
        "lightsheet.gui.panels.save_panel.QFileDialog.getExistingDirectory",
        return_value=str(tmp_path),
    ):
        ctrl.save_panel.updateUi_select_directory()

    assert ctrl.save_panel.ui.lineEdit_saveDescription.text() == ""
    assert ctrl.state.snapshot().save_options.description == ""


def test_single_image_save_uses_model_intent(
    qtbot: QtBot, controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """updateUi_save_single_image reads the model snapshot for the sample
    name and save branch — a programmatically stale (signal-blocked) radio
    does not change the selected branch."""
    ctrl = controller
    ctrl.saving_allowed = True
    ctrl.save_directory = str(tmp_path)
    ctrl.save_filepath = str(tmp_path / "img")
    ctrl.save_filename = "img"
    ctrl.image_hor_pos_text = "0.0"
    ctrl.image_ver_pos_text = "0.0"
    ctrl.image_cam_pos_text = "0.0"
    ctrl.buffer = np.zeros((4, 4), dtype=np.uint16)

    # Model intent: description + ALL_CROP. Stale widget: block the radio
    # signals and leave a different radio checked so a widget read would
    # pick the wrong branch.
    ctrl.state.set_save_options(
        SaveOptions(description="model desc", mode=SaveMode.ALL_CROP)
    )
    stale = ctrl.save_panel.ui.radioButton_saveStitch
    was = stale.blockSignals(True)
    stale.setChecked(True)
    stale.blockSignals(was)

    set_files_calls: list[tuple[int, str, str, int, str, list[int] | None]] = []
    real_set_files = ctrl._fs.set_files

    def _spy_set_files(
        number_of_files: int,
        files_name: str,
        scan_type: str,
        number_of_datasets: int,
        datasets_name: str,
        wavelengths: list[int] | None = None,
    ) -> None:
        set_files_calls.append(
            (
                number_of_files,
                files_name,
                scan_type,
                number_of_datasets,
                datasets_name,
                wavelengths,
            )
        )
        real_set_files(
            number_of_files,
            files_name,
            scan_type,
            number_of_datasets,
            datasets_name,
            wavelengths=wavelengths,
        )

    with (
        patch.object(ctrl._fs, "set_files", side_effect=_spy_set_files),
        patch.object(ctrl._fs, "add_sample_name") as add_name,
        patch.object(
            ctrl._fs,
            "crop_buffer",
            return_value=np.zeros((2, 2), dtype=np.uint16),
        ),
        patch.object(ctrl._fs, "enqueue_buffer"),
        patch.object(ctrl._fs, "start_saving"),
        patch.object(ctrl._fs, "stop_saving"),
    ):
        ctrl.save_panel.updateUi_save_single_image()

    add_name.assert_called_once_with("model desc")
    assert len(set_files_calls) == 1
    # set_files(..., "singleImage", 1, "ETLscan", ...) — the ALL_CROP branch.
    assert set_files_calls[0][2] == "singleImage"
    assert set_files_calls[0][4] == "ETLscan"


def test_single_image_save_model_stitch_branch(
    qtbot: QtBot, controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """STITCH mode takes the reconstructed_frame branch."""
    ctrl = controller
    ctrl.saving_allowed = True
    ctrl.save_directory = str(tmp_path)
    ctrl.save_filepath = str(tmp_path / "img")
    ctrl.save_filename = "img"
    ctrl.image_hor_pos_text = "0.0"
    ctrl.image_ver_pos_text = "0.0"
    ctrl.image_cam_pos_text = "0.0"
    ctrl.reconstructed_frame = np.zeros((4, 4), dtype=np.uint16)
    ctrl.state.set_save_options(
        SaveOptions(description="stitch desc", mode=SaveMode.STITCH)
    )

    set_files_calls: list[tuple[int, str, str, int, str, list[int] | None]] = []
    real_set_files = ctrl._fs.set_files

    def _spy_set_files(
        number_of_files: int,
        files_name: str,
        scan_type: str,
        number_of_datasets: int,
        datasets_name: str,
        wavelengths: list[int] | None = None,
    ) -> None:
        set_files_calls.append(
            (
                number_of_files,
                files_name,
                scan_type,
                number_of_datasets,
                datasets_name,
                wavelengths,
            )
        )
        real_set_files(
            number_of_files,
            files_name,
            scan_type,
            number_of_datasets,
            datasets_name,
            wavelengths=wavelengths,
        )

    with (
        patch.object(ctrl._fs, "set_files", side_effect=_spy_set_files),
        patch.object(ctrl._fs, "enqueue_buffer"),
        patch.object(ctrl._fs, "start_saving"),
        patch.object(ctrl._fs, "stop_saving"),
    ):
        ctrl.save_panel.updateUi_save_single_image()

    assert len(set_files_calls) == 1
    assert set_files_calls[0][4] == "reconstructed_frame"


def test_save_description_property_delegates_to_model(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """The ``save_description`` compatibility property reads/writes through
    the model and holds no shadow storage."""
    ctrl = controller
    ctrl.save_description = "via property"
    assert ctrl.state.snapshot().save_options.description == "via property"
    assert ctrl.save_description == "via property"
    assert "save_description" not in ctrl.__dict__
