"""Tests for the format-aware Est. Size column on the acquisition table.

The Est. Size cell re-estimates when the save-format radio group selection
changes (D-05): HDF5 = raw bytes; OME-Zarr = raw L0 + multiscale pyramid
overhead with a stack_step-dependent level count; Both = sum. The cell
shows a format-suffixed human-readable value (e.g. "16.9 GB (HDF5)").
"""

from __future__ import annotations

from _helpers.controller_fixture import make_controller
from pytest import FixtureRequest
from pytestqt.qtbot import QtBot

from lightsheet.gui.panels.acquisition_table_manager import AcquisitionTableManager


def _add_valid_row(table: AcquisitionTableManager) -> int:
    """Add a planned-queue row with a non-zero range so it computes >0
    planes, then return the row index. Start/End cells display in mm;
    Step stays µm. start=0 mm, end=1 mm (1000 µm), step=5 µm → 201 planes."""
    table.add_stack()
    row = table.table.rowCount() - 1
    table.set_cell(row, 1, "0")  # Start (mm)
    table.set_cell(row, 2, "1")  # End (mm) = 1000 µm
    table.set_cell(row, 3, "5")  # Step (µm)
    return row


def test_est_size_suffix_reflects_save_format(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """The Est. Size cell text carries the format suffix and changes when
    the save format changes (HDF5 -> OME-Zarr -> Both)."""
    ctrl, _ = make_controller(qtbot, request)
    table = ctrl.stack_panel.table_manager
    # stack_step is read for the zarr pyramid level count (base_res Z);
    # set a non-zero value so the level count is well-defined.
    ctrl.stack_step = 5.0
    row = _add_valid_row(table)

    ctrl.save_format = "hdf5"
    table.recompute_all_rows()
    hdf5_text = table.table.item(row, 6).text()
    assert "(HDF5)" in hdf5_text, hdf5_text

    ctrl.save_format = "zarr"
    table.recompute_all_rows()
    zarr_text = table.table.item(row, 6).text()
    assert "(OME-Zarr)" in zarr_text, zarr_text

    ctrl.save_format = "both"
    table.recompute_all_rows()
    both_text = table.table.item(row, 6).text()
    assert "(Both)" in both_text, both_text


def test_zarr_estimate_is_larger_than_hdf5(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """The OME-Zarr estimate includes the multiscale pyramid overhead, so
    it is strictly larger than the raw-bytes HDF5 estimate for the same
    stack. Both = hdf5 + zarr (sum)."""
    ctrl, _ = make_controller(qtbot, request)
    table = ctrl.stack_panel.table_manager
    ctrl.stack_step = 5.0
    row = _add_valid_row(table)

    def _mb(text: str) -> float:
        # "16.9 GB (HDF5)" -> 16.9 GB -> 17305.6 MB; "200.0 MB (HDF5)" -> 200.0
        s = text.split(" (")[0]
        val, unit = s.split(" ")
        val = float(val)
        if unit == "GB":
            return val * 1024.0
        if unit == "TB":
            return val * 1024.0 * 1024.0
        return val  # MB

    ctrl.save_format = "hdf5"
    table.recompute_all_rows()
    hdf5_mb = _mb(table.table.item(row, 6).text())

    ctrl.save_format = "zarr"
    table.recompute_all_rows()
    zarr_mb = _mb(table.table.item(row, 6).text())

    assert zarr_mb > hdf5_mb, (hdf5_mb, zarr_mb)

    ctrl.save_format = "both"
    table.recompute_all_rows()
    both_mb = _mb(table.table.item(row, 6).text())
    assert abs(both_mb - (hdf5_mb + zarr_mb)) < 1.0, (hdf5_mb, zarr_mb, both_mb)


def test_format_radio_re_estimates_table(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """Switching the save-format radio re-estimates the Est. Size cell via
    the controller subscription (the buttonClicked signal is wired to
    recompute_all_rows)."""
    ctrl, _ = make_controller(qtbot, request)
    table = ctrl.stack_panel.table_manager
    ctrl.stack_step = 5.0
    row = _add_valid_row(table)

    ctrl.save_format = "hdf5"
    table.recompute_all_rows()
    before = table.table.item(row, 6).text()

    # Click the OME-Zarr radio — fires the button group's buttonClicked
    # signal, which runs updateUi_save_format_changed (sets save_format)
    # then recompute_all_rows (re-estimates every row) in connection order.
    ctrl.save_panel.ui.radioButton_saveFormat_zarr.click()
    after = table.table.item(row, 6).text()

    assert before != after
    assert "(OME-Zarr)" in after, after
