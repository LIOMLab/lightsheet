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

import pytest

from _helpers.controller_fixture import make_controller

_WAVE0_REESTIMATE = "Wave 0 RED scaffold — Est. Size re-estimate lands with the acquisition-table expansion"


def test_save_format_radio_sets_save_format(qtbot, request) -> None:
    """D-03: the save-format radio slot sets ``self.save_format``. The
    initial value is ``'hdf5'`` (the config-driven default in the test
    fixture); calling the slot with the OME-Zarr radio button updates the
    attribute to ``'zarr'``."""
    ctrl, _ = make_controller(qtbot, request)
    assert ctrl.save_format == "hdf5"
    zarr_radio = ctrl.save_panel.ui.radioButton_saveFormat_zarr
    ctrl.updateUi_save_format_changed(zarr_radio)
    assert ctrl.save_format == "zarr"


@pytest.mark.xfail(reason=_WAVE0_REESTIMATE, strict=False)
def test_save_format_radio_re_estimates_table(qtbot, request) -> None:
    """D-05: switching the save-format radio re-estimates the Est. Size
    cell in the acquisition table (Zarr vs HDF5 have different per-plane
    footprints). The table's Est. Size value changes after the slot fires."""
    ctrl, _ = make_controller(qtbot, request)
    # Capture the Est. Size cell value before the format switch.
    table = ctrl.acquisition_panel.acquisition_table
    before = table.get_est_size()
    ctrl.updateUi_save_format_changed(ctrl.save_panel.ui.radioButton_saveFormat_zarr)
    after = table.get_est_size()
    assert before != after
