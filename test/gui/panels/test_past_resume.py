"""Tests for the Past Acquisitions resume surface (16-08).

Covers manifest discovery, state chips, the Resume action, the startup
notification, and the resumed mode badge / progress bar offset.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
import numpy as np
import h5py
from PySide6.QtWidgets import QMessageBox
from pytestqt.qtbot import QtBot

from lightsheet.gui.panels.acquisition_table_manager import _COL_NPLANES as _QM_COL_NPLANES
from lightsheet.gui.panels.past_acquisitions_browser import (
    PastAcquisitionsBrowser,
    _PAST_COL_RESUME,
    _PAST_COL_STATE,
)
from lightsheet.resume import ResumeManifest, manifest_path_for, write_manifest

if TYPE_CHECKING:
    from lightsheet.gui.shell.controller import Controller_MainWindow


def _make_hdf5(path: Path) -> Path:
    """Create a minimal HDF5 file the past browser will parse."""
    with h5py.File(path, "w") as f:  # ty: ignore[invalid-argument-type]
        f.attrs["Laser1 Wavelength"] = 555
        f.attrs["Laser1 Active"] = True
        f.create_dataset(
            "reconstructed_frame001", data=np.zeros((2, 4, 4), dtype=np.uint16)
        )
    return path


def _write_resume_manifest(
    h5_path: Path,
    *,
    state: str,
    n_planes: int = 4,
    start_plane: int = 2,
) -> Path:
    """Write a sidecar resume manifest for an HDF5 acquisition."""
    sidecar = manifest_path_for(h5_path)
    manifest = ResumeManifest(
        uuid="test-uuid-0000",
        state=state,
        n_planes=n_planes,
        stack_starting_plane=0.0,
        stack_ending_plane=30.0,
        stack_step=10.0,
        save_mode="stitch",
        created_at="2026-09-08T00:00:00+00:00",
        start_plane=start_plane,
        save_filepath=str(h5_path),
        cursors={"hdf5": {"0": start_plane}},
    )
    write_manifest(sidecar, manifest)
    return sidecar


def _make_case(tmp_path: Path, state: str) -> Path:
    """Create an HDF5 + sidecar for a lifecycle state and return the h5 path."""
    h5_path = tmp_path / f"{state}_555nm_stack.hdf5"
    _make_hdf5(h5_path)
    _write_resume_manifest(h5_path, state=state)
    return h5_path


def test_browser_scans_manifests_and_marks_states(
    qtbot: QtBot, controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """The browser reads *.resume.json sidecars and marks entries with the
    correct state and resumable flag."""
    controller.save_directory = str(tmp_path)

    for state in ("completed", "in_progress", "paused", "interrupted"):
        _make_case(tmp_path, state)

    browser = PastAcquisitionsBrowser(controller, data_dir=str(tmp_path))
    entries = browser.list_acquisitions()
    assert len(entries) == 4, [e.source_path for e in entries]

    by_state = {e.state: e for e in entries}
    assert by_state["completed"].resumable is False
    assert by_state["completed"].manifest_path is not None
    for state in ("in_progress", "paused", "interrupted"):
        assert by_state[state].resumable is True, state
        assert by_state[state].manifest_path is not None


def test_past_panel_state_chips_and_resume_button(
    qtbot: QtBot, controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """The panel renders colored state chips and a Resume button only for
    resumable rows."""
    controller.save_directory = str(tmp_path)

    _make_case(tmp_path, "interrupted")
    _make_case(tmp_path, "completed")

    panel = controller.past_panel
    entries = panel.browser.list_acquisitions()
    panel._on_scan_finished(entries)
    qtbot.wait(50)

    table = panel.ui.tableWidget_pastAcquisitions
    assert table.rowCount() == 2

    # Find each row by its state chip text.
    interrupted_row = next(
        i
        for i in range(table.rowCount())
        if table.item(i, _PAST_COL_STATE).text() == "INTERRUPTED"
    )
    interrupted_item = table.item(interrupted_row, _PAST_COL_STATE)
    assert interrupted_item is not None
    assert interrupted_item.text() == "INTERRUPTED"
    assert table.cellWidget(interrupted_row, _PAST_COL_RESUME) is not None

    completed_row = next(
        i
        for i in range(table.rowCount())
        if table.item(i, _PAST_COL_STATE).text() == "Completed"
    )
    completed_item = table.item(completed_row, _PAST_COL_STATE)
    assert completed_item.text() == "Completed"
    assert table.cellWidget(completed_row, _PAST_COL_RESUME) is None


def test_resume_action_enqueues_a_resume_row(
    qtbot: QtBot, controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """Clicking Resume in the Past table enqueues a resume row with the
    correct start-plane offset, name prefix, and RESUME badge."""
    controller.save_directory = str(tmp_path)
    h5_path = _make_case(tmp_path, "paused")

    panel = controller.past_panel
    entries = panel.browser.list_acquisitions()
    panel._on_scan_finished(entries)
    qtbot.wait(50)

    btn = panel.ui.tableWidget_pastAcquisitions.cellWidget(0, _PAST_COL_RESUME)
    assert btn is not None
    assert btn.text() == "Resume"

    btn.click()
    qtbot.wait(50)

    table_manager = controller.stack_panel.table_manager
    assert table_manager.table.rowCount() == 1

    name_item = table_manager.table.item(0, 0)
    assert name_item is not None
    assert name_item.text().startswith("Resume:")

    planes_item = table_manager.table.item(0, _QM_COL_NPLANES)
    assert planes_item is not None
    assert planes_item.text() == "RESUME 2/4", planes_item.text()


def test_startup_notification_shows_for_incomplete_acquisitions(
    qtbot: QtBot, controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """After hardware_init the startup scan shows a notification-only
    dialog when an incomplete acquisition exists."""
    controller.save_directory = str(tmp_path)
    _make_case(tmp_path, "in_progress")

    with patch.object(
        QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok
    ) as mock_info:
        controller._check_startup_incomplete_acquisitions()
        qtbot.waitUntil(lambda: mock_info.called, timeout=3000)

    mock_info.assert_called_once()
    call_args = mock_info.call_args[0]
    assert call_args[1] == "Incomplete acquisition"
    assert "Past acquisitions" in call_args[2]


def test_resuming_mode_badge_and_progress(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """The mode badge shows STACK RESUMING and the progress bar fills when
    sig_progress_update is emitted during a resumed run."""
    controller.stack_mode_started = True
    controller.number_of_planes = 100
    controller._start_plane = 10
    controller.pause_requested.clear()

    controller.sig_progress_update.emit(50)
    qtbot.wait(50)

    assert controller.ui.statusBar_progress.value() == 50
    badge = controller.ui.label_modeBadge.text()
    assert "RESUMING" in badge, badge
    assert "100" in badge
