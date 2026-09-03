"""Tests for the save-format radio group (D-03 / D-05).

``test_save_format_radio_sets_save_format`` is owned by the save-panel UI
plan: the ``updateUi_save_format_changed`` slot on the controller maps the
clicked format radio button to a lowercase constant and sets
``self.save_format``.

``test_save_format_radio_re_estimates_table`` is a Wave 0 RED scaffold
owned by the Est. Size re-estimate plan (the acquisition-table expansion):
switching the format radio re-estimates the Est. Size cell. It stays
``xfail`` until the recompute-all-rows subscription + format-aware
estimation land.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pytestqt.qtbot import QtBot

if TYPE_CHECKING:
    from lightsheet.gui.shell.controller import Controller_MainWindow


def test_save_format_radio_sets_save_format(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """D-03: the save-format radio slot sets ``self.save_format``. The
    initial value is ``'hdf5'`` (the config-driven default in the test
    fixture); calling the slot with the OME-Zarr radio button updates the
    attribute to ``'zarr'``."""
    ctrl = controller
    assert ctrl.save_format == "hdf5"
    zarr_radio = ctrl.save_panel.ui.radioButton_saveFormat_zarr
    ctrl.updateUi_save_format_changed(zarr_radio)
    assert ctrl.save_format == "zarr"


def test_save_format_radio_re_estimates_table(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """D-05: switching the save-format radio re-estimates the Est. Size
    cell in the acquisition table (Zarr vs HDF5 have different per-plane
    footprints). The table's Est. Size value changes after the slot fires."""
    ctrl = controller
    table = ctrl.stack_panel.table_manager
    ctrl.stack_step = 5.0
    table.add_stack()
    row = table.table.rowCount() - 1
    table.set_cell(row, 1, "0")
    table.set_cell(row, 2, "1000")
    table.set_cell(row, 3, "5")

    ctrl.save_format = "hdf5"
    table.recompute_all_rows()
    before = table.table.item(row, 6).text()
    ctrl.save_panel.ui.radioButton_saveFormat_zarr.click()
    after = table.table.item(row, 6).text()
    assert before != after
    assert "(OME-Zarr)" in after, after
