"""Wave 0 RED scaffolds for the save-format radio (D-03 / D-05).

Defines the expected behavior of the save-format radio group that lands
in a later wave (the ``updateUi_save_format_changed`` slot sets
``self.save_format`` and re-estimates the Est. Size table cell). Marked
``xfail`` (strict=False) during Wave 0 so the suite stays GREEN: the slot
and the ``save_format`` attribute do not exist yet, so the assertions
fail with ``AttributeError`` and xfail records the expected failure.
"""

from __future__ import annotations

import pytest

from _helpers.controller_fixture import make_controller

_WAVE0 = "Wave 0 RED scaffold — save-format radio implemented in a later wave"


@pytest.mark.xfail(reason=_WAVE0, strict=False)
def test_save_format_radio_sets_save_format(qtbot, request) -> None:
    """D-03: the save-format radio slot sets ``self.save_format``. The
    initial value is ``'hdf5'``; calling the slot with ``'zarr'`` updates
    the attribute."""
    ctrl, _ = make_controller(qtbot, request)
    assert ctrl.save_format == "hdf5"
    ctrl.save_panel.updateUi_save_format_changed("zarr")
    assert ctrl.save_format == "zarr"


@pytest.mark.xfail(reason=_WAVE0, strict=False)
def test_save_format_radio_re_estimates_table(qtbot, request) -> None:
    """D-05: switching the save-format radio re-estimates the Est. Size
    cell in the acquisition table (Zarr vs HDF5 have different per-plane
    footprints). The table's Est. Size value changes after the slot fires."""
    ctrl, _ = make_controller(qtbot, request)
    # Capture the Est. Size cell value before the format switch.
    table = ctrl.acquisition_panel.acquisition_table
    before = table.get_est_size()
    ctrl.save_panel.updateUi_save_format_changed("zarr")
    after = table.get_est_size()
    assert before != after
