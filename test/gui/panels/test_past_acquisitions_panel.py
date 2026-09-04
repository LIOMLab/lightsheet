"""Tests for the dedicated PastAcquisitionsPanel (left-rail index 6).

The past-acquisitions browser was moved out of the Stack panel's
Acquisition Queue group into a dedicated left-rail panel so it has room
to breathe. These tests verify the dedicated panel is composed into
stackedPanels at index 6, the Planned/Past toggle + Refresh button live
in the dedicated panel (not the Stack panel), the Planned queue +
add/edit/remove controls stay in the Stack panel, and the async-scan
pattern (QThread + moveToThread + _ScanWorker) is intact.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QScrollArea
from pytestqt.qtbot import QtBot

if TYPE_CHECKING:
    from lightsheet.gui.shell.controller import Controller_MainWindow


def test_past_panel_at_stacked_index_6(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """The dedicated PastAcquisitionsPanel is at stackedPanels index 6,
    wrapped in a QScrollArea(widgetResizable=True)."""
    ctrl = controller
    sp = ctrl.ui.stackedPanels
    assert sp.count() == 8

    page = sp.widget(6)
    assert isinstance(page, QScrollArea), (
        f"page 6 is not a QScrollArea (got {type(page).__name__})"
    )
    assert page.widgetResizable() is True, (
        "page 6 scroll area must have widgetResizable=True"
    )
    # The scroll area's widget is the PastAcquisitionsPanel.
    inner = page.widget()
    assert inner is ctrl.past_panel, (
        "page 6's scroll area widget is not the PastAcquisitionsPanel"
    )


def test_past_panel_has_browser_table_toggle_refresh(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """The dedicated Past panel owns the past table, the Planned/Past
    toggle, and the Refresh button (moved from the Stack panel)."""
    ctrl = controller
    panel = ctrl.past_panel

    # The past-acquisitions table is in the dedicated panel.
    assert panel.findChild(QObject, "tableWidget_pastAcquisitions") is not None
    # The Planned/Past toggle is in the dedicated panel.
    assert panel.findChild(QObject, "radioButton_viewPlanned") is not None
    assert panel.findChild(QObject, "radioButton_viewPast") is not None
    # The Refresh button is in the dedicated panel.
    assert panel.findChild(QObject, "pushButton_refreshPast") is not None
    # The status label is in the dedicated panel.
    assert panel.findChild(QObject, "label_pastStatus") is not None


def test_past_panel_toggle_and_refresh_not_in_stack_panel(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """The Planned/Past toggle + Refresh button + past table are NOT in
    the Stack panel's AcquisitionTableManager (they moved to the
    dedicated Past panel)."""
    ctrl = controller
    stack_panel = ctrl.stack_panel
    table_manager = stack_panel.table_manager

    # The AcquisitionTableManager no longer owns the past widgets.
    assert not hasattr(table_manager, "tableWidget_pastAcquisitions"), (
        "AcquisitionTableManager still owns tableWidget_pastAcquisitions — "
        "the past table should have moved to the dedicated Past panel"
    )
    assert not hasattr(table_manager, "radioButton_viewPlanned"), (
        "AcquisitionTableManager still owns radioButton_viewPlanned — "
        "the toggle should have moved to the dedicated Past panel"
    )
    assert not hasattr(table_manager, "pushButton_refreshPast"), (
        "AcquisitionTableManager still owns pushButton_refreshPast — "
        "the Refresh button should have moved to the dedicated Past panel"
    )
    assert not hasattr(table_manager, "_past_browser"), (
        "AcquisitionTableManager still owns _past_browser — "
        "the browser should have moved to the dedicated Past panel"
    )


def test_planned_queue_stays_in_stack_panel(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """The Planned queue QTableWidget + add/edit/remove/start-queue
    controls stay in the Stack panel's AcquisitionTableManager."""
    ctrl = controller
    table_manager = ctrl.stack_panel.table_manager

    # The Planned queue table is still in the table manager.
    assert table_manager.findChild(QObject, "tableWidget_acquisitionQueue") is not None
    # The add/remove/move/start buttons are still in the table manager.
    assert table_manager.findChild(QObject, "pushButton_addStack") is not None
    assert table_manager.findChild(QObject, "pushButton_removeStack") is not None
    assert table_manager.findChild(QObject, "pushButton_moveUp") is not None
    assert table_manager.findChild(QObject, "pushButton_moveDown") is not None
    assert table_manager.findChild(QObject, "pushButton_startQueue") is not None


def test_past_panel_owns_async_scan_worker(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """The PastAcquisitionsPanel owns a PastAcquisitionsBrowser with the
    async-scan pattern intact (QThread + moveToThread + _ScanWorker).
    The browser's start_scan_async + _clear_thread_refs teardown are
    present."""
    from lightsheet.gui.panels.past_acquisitions_browser import (
        PastAcquisitionsBrowser,
        _ScanWorker,
    )

    ctrl = controller
    panel = ctrl.past_panel

    # The panel owns a PastAcquisitionsBrowser.
    assert isinstance(panel.browser, PastAcquisitionsBrowser)
    # The async-scan pattern is intact: start_scan_async + _clear_thread_refs.
    assert hasattr(panel.browser, "start_scan_async")
    assert hasattr(panel.browser, "_clear_thread_refs")
    # The _ScanWorker class exists (the QThread + moveToThread worker).
    assert _ScanWorker is not None


def test_refresh_button_triggers_start_scan_async(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """Clicking the Refresh button triggers the browser's
    start_scan_async (the async scan is offloaded to a QThread so the
    GUI thread + E-stop kill path stay responsive)."""
    from unittest.mock import patch

    ctrl = controller
    panel = ctrl.past_panel

    # Patch start_scan_async to record the call without spawning a real
    # QThread (the scan would hit an empty/missing save directory and
    # emit sig_scan_finished([]) — harmless, but patching avoids the
    # thread lifecycle entirely).
    with patch.object(panel.browser, "start_scan_async") as mock_start:
        panel.ui.pushButton_refreshPast.click()
        assert mock_start.called, (
            "Refresh button click did not trigger browser.start_scan_async()"
        )


def test_past_panel_scan_finished_populates_table(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """When the browser emits sig_scan_finished, the panel populates the
    past table in one batch and emits past_acquisitions_scan_finished."""
    from lightsheet.gui.panels.past_acquisitions_browser import (
        PastAcquisitionEntry,
    )

    ctrl = controller
    panel = ctrl.past_panel

    entries = [
        PastAcquisitionEntry(
            sample="sample_a",
            wavelength=647,
            n_planes=10,
            size_bytes=1024,
            date_str="2026-01-01",
            format_label="HDF5",
            source_path="/tmp/sample_a.hdf5",
        ),
        PastAcquisitionEntry(
            sample="sample_b",
            wavelength=555,
            n_planes=20,
            size_bytes=2048,
            date_str="2026-01-02",
            format_label="OME-Zarr",
            source_path="/tmp/sample_b.ome.zarr",
        ),
    ]

    received: list = []  # ty: ignore[missing-type-argument]
    panel.past_acquisitions_scan_finished.connect(received.extend)

    # Emit sig_scan_finished directly (simulates the async worker
    # completing on the GUI thread).
    panel.browser.sig_scan_finished.emit(entries)
    qtbot.wait(50)

    # The table has 2 rows.
    assert panel.ui.tableWidget_pastAcquisitions.rowCount() == 2
    # The table's effective visibility flag is True (setVisible(True) was
    # called because there are rows). isVisibleTo(panel) checks the
    # widget's own visibility flag without requiring the parent stacked
    # page to be the current page.
    assert panel.ui.tableWidget_pastAcquisitions.isVisibleTo(panel), (
        "table should be marked visible when it has rows"
    )
    # The status label is hidden (has rows).
    assert not panel.ui.label_pastStatus.isVisibleTo(panel), (
        "status label should be hidden when the table has rows"
    )
    # The re-emit fired.
    assert len(received) == 2


def test_past_panel_empty_scan_shows_empty_copy(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """When the browser emits sig_scan_finished with no entries, the
    panel shows the empty-state copy and hides the table."""
    ctrl = controller
    panel = ctrl.past_panel

    panel.browser.sig_scan_finished.emit([])
    qtbot.wait(50)

    assert panel.ui.tableWidget_pastAcquisitions.rowCount() == 0
    assert not panel.ui.tableWidget_pastAcquisitions.isVisibleTo(panel), (
        "table should be marked hidden when it has no rows"
    )
    assert panel.ui.label_pastStatus.isVisibleTo(panel), (
        "status label should be visible when the table is empty"
    )
    assert "No past acquisitions" in panel.ui.label_pastStatus.text()


def test_past_panel_wavelength_normalization(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """The past table normalizes 640 -> 647 in the Channel column
    (display only — the underlying file is unchanged)."""
    from lightsheet.gui.panels.past_acquisitions_browser import (
        PastAcquisitionEntry,
    )

    ctrl = controller
    panel = ctrl.past_panel

    entry = PastAcquisitionEntry(
        sample="sample_c",
        wavelength=640,  # normalized to 647 in display
        n_planes=5,
        size_bytes=512,
        date_str="2026-01-03",
        format_label="HDF5",
        source_path="/tmp/sample_c.hdf5",
    )

    panel.browser.sig_scan_finished.emit([entry])
    qtbot.wait(50)

    # The Channel column (index 1) shows 647 (normalized from 640).
    channel_item = panel.ui.tableWidget_pastAcquisitions.item(0, 1)
    assert channel_item is not None
    assert channel_item.text() == "647"
