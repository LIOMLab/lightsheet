"""Wave 0 RED scaffolds for the past-acquisitions browser (D-05).

Defines the expected behavior of the past-acquisitions browser that lands
in a later wave (parses both HDF5 and OME-Zarr acquisitions under the
``LightSheetData`` folder, normalizes the iBeam 640 nm wavelength label
to the 647 nm capture wavelength, and degrades gracefully on missing
root attrs). Marked ``xfail`` (strict=False) during Wave 0 so the suite
stays GREEN: the browser does not exist yet, so the tests fail at
import/construction and xfail records the expected failure.
"""

from __future__ import annotations

import pytest

# Module-level import guard: the browser does not exist yet (Wave 0).
try:  # pragma: no cover - import guard for not-yet-implemented class
    from lightsheet.gui.panels.past_acquisitions_browser import (
        PastAcquisitionsBrowser,
    )
except ImportError:  # pragma: no cover - Wave 0
    PastAcquisitionsBrowser = None  # type: ignore[assignment,misc]

from _helpers.controller_fixture import make_controller

_WAVE0 = "Wave 0 RED scaffold — past-acquisitions browser implemented in a later wave"


@pytest.mark.xfail(reason=_WAVE0, strict=False)
def test_past_acquisitions_browser_parses_hdf5_and_zarr(
    qtbot, request, tmp_path
) -> None:
    """D-05: the browser lists both HDF5 and OME-Zarr acquisitions under
    the ``LightSheetData`` folder. The iBeam 640 nm wavelength label is
    normalized to the 647 nm capture wavelength (the rig-confirmed value)
    in the parsed entry."""
    import h5py
    import numpy as np
    import zarr

    ctrl, _ = make_controller(qtbot, request)
    assert PastAcquisitionsBrowser is not None, "browser not yet implemented"

    data_dir = tmp_path / "LightSheetData"
    data_dir.mkdir()

    # Synthetic HDF5 acquisition with a 640 nm wavelength root attr (the
    # iBeam label that must normalize to 647 nm).
    h5_path = data_dir / "stack_001.hdf5"
    with h5py.File(h5_path, "w") as f:
        f.attrs["Laser1 Wavelength"] = 640
        ds = f.create_dataset("data", data=np.zeros((4, 8, 8), dtype=np.uint16))
        ds.attrs["dummy"] = 0

    # Synthetic OME-Zarr acquisition.
    zarr_path = data_dir / "stack_002.ome.zarr"
    store = zarr.open(str(zarr_path), mode="w")
    store.attrs["omero"] = {
        "channels": [{"wavelength": 647, "label": "Laser 1 (647 nm)"}]
    }

    browser = PastAcquisitionsBrowser(ctrl, data_dir=str(data_dir))
    entries = browser.list_acquisitions()
    assert len(entries) == 2
    wavelengths = {e.wavelength for e in entries}
    # 640 nm normalized to 647 nm; the zarr entry is already 647.
    assert 647 in wavelengths
    assert 640 not in wavelengths


@pytest.mark.xfail(reason=_WAVE0, strict=False)
def test_past_acquisitions_browser_degrades_on_missing_attrs(
    qtbot, request, tmp_path
) -> None:
    """D-05: an HDF5 file with no root attrs degrades gracefully — the
    wavelength is inferred from the filename (best-effort) and the entry
    is listed without raising."""
    import h5py
    import numpy as np

    ctrl, _ = make_controller(qtbot, request)
    assert PastAcquisitionsBrowser is not None, "browser not yet implemented"

    data_dir = tmp_path / "LightSheetData"
    data_dir.mkdir()
    h5_path = data_dir / "647nm_stack.hdf5"
    with h5py.File(h5_path, "w") as f:
        f.create_dataset("data", data=np.zeros((2, 4, 4), dtype=np.uint16))

    browser = PastAcquisitionsBrowser(ctrl, data_dir=str(data_dir))
    entries = browser.list_acquisitions()
    assert len(entries) == 1
    # No root attrs → wavelength inferred from filename; must not raise.
    assert entries[0].wavelength is not None
