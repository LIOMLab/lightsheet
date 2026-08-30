"""Tests for the past-acquisitions browser (D-05).

The browser parses both HDF5 and OME-Zarr acquisitions under the save
directory, normalizes the iBeam 640 nm wavelength label to the 647 nm
capture wavelength (display-only — the underlying file is NOT modified),
and degrades gracefully on missing root attrs (pre-Phase-4 files infer
the wavelength from the filename).
"""

from __future__ import annotations

from lightsheet.gui.panels.past_acquisitions_browser import (
    PastAcquisitionsBrowser,
)

from _helpers.controller_fixture import make_controller


def test_past_acquisitions_browser_parses_hdf5_and_zarr(
    qtbot, request, tmp_path
) -> None:
    """D-05: the browser lists both HDF5 and OME-Zarr acquisitions under
    the save directory. The iBeam 640 nm wavelength label is normalized to
    647 nm (the rig-confirmed capture wavelength) in the parsed entry —
    DISPLAY only, the underlying filename is NOT modified (Pitfall 6)."""
    import h5py
    import numpy as np
    import zarr

    ctrl, _ = make_controller(qtbot, request)

    data_dir = tmp_path / "LightSheetData"
    data_dir.mkdir()

    # Synthetic HDF5 acquisition with a 640 nm wavelength root attr (the
    # iBeam label that must normalize to 647 nm). The filename carries the
    # 640nm token too — both sources agree on 640, the display shows 647.
    # Laser2 is the active laser (640nm iBeam) — Laser1 (555nm) is inactive.
    h5_path = data_dir / "S01_640nm_stack_plane_00001.hdf5"
    with h5py.File(h5_path, "w") as f:
        f.attrs["Laser1 Wavelength"] = 555
        f.attrs["Laser1 Active"] = False
        f.attrs["Laser2 Wavelength"] = 640
        f.attrs["Laser2 Active"] = True
        f.create_dataset(
            "reconstructed_frame001", data=np.zeros((4, 8, 8), dtype=np.uint16)
        )

    # Synthetic OME-Zarr acquisition (555 nm). The writer nests omero
    # inside the "ome" attrs key (verified against the real writer).
    zarr_path = data_dir / "S02_555nm.ome.zarr"
    root = zarr.open_group(str(zarr_path), mode="w")
    root.require_array(
        "0", shape=(1, 4, 8, 8), chunks=(1, 1, 8, 8), dtype=np.uint16
    )
    root.attrs["ome"] = {
        "omero": {
            "channels": [
                {"wavelength": 555, "label": "Laser 1 (555 nm)", "color": "00FF00"}
            ]
        },
        "version": "0.5",
        "multiscales": [{"datasets": [{"path": "0"}]}],
    }

    browser = PastAcquisitionsBrowser(ctrl, data_dir=str(data_dir))
    entries = browser.list_acquisitions()
    assert len(entries) == 2

    by_format = {e.format_label: e for e in entries}
    assert "HDF5" in by_format, [e.format_label for e in entries]
    assert "OME-Zarr" in by_format, [e.format_label for e in entries]

    hdf5_entry = by_format["HDF5"]
    zarr_entry = by_format["OME-Zarr"]

    # 640 -> 647 display normalization (Pitfall 6: display only).
    assert hdf5_entry.wavelength == 647, hdf5_entry.wavelength
    assert zarr_entry.wavelength == 555, zarr_entry.wavelength

    # The underlying HDF5 filename is NOT modified (still contains 640nm).
    assert "640nm" in str(hdf5_entry.source_path)

    # #planes: HDF5 = len(f.keys()) = 1; Zarr = L0 shape[1] = 4.
    assert hdf5_entry.n_planes == 1, hdf5_entry.n_planes
    assert zarr_entry.n_planes == 4, zarr_entry.n_planes


def test_past_acquisitions_hdf5_picks_active_laser_wavelength(
    qtbot, request, tmp_path
) -> None:
    """The HDF5 wavelength parser must return the ACTIVE laser's
    wavelength, not just the first one found. When only Laser2 (647nm)
    is active, the browser must show 647nm — not 555nm from Laser1."""
    import h5py
    import numpy as np

    ctrl, _ = make_controller(qtbot, request)

    data_dir = tmp_path / "LightSheetData"
    data_dir.mkdir()

    # Laser1 (555nm) inactive, Laser2 (647nm) active.
    h5_path = data_dir / "test_active_laser.hdf5"
    with h5py.File(h5_path, "w") as f:
        f.attrs["Laser1 Wavelength"] = 555
        f.attrs["Laser1 Active"] = False
        f.attrs["Laser2 Wavelength"] = 647
        f.attrs["Laser2 Active"] = True
        f.create_dataset(
            "reconstructed_frame001", data=np.zeros((4, 8, 8), dtype=np.uint16)
        )

    browser = PastAcquisitionsBrowser(ctrl, data_dir=str(data_dir))
    entries = browser.list_acquisitions()
    assert len(entries) == 1
    assert entries[0].wavelength == 647, (
        f"expected 647 (active laser), got {entries[0].wavelength}"
    )


def test_past_acquisitions_browser_degrades_on_missing_attrs(
    qtbot, request, tmp_path
) -> None:
    """D-05: an HDF5 file with no root attrs (pre-Phase-4 style) degrades
    gracefully — the wavelength is inferred from the filename token and
    the entry is listed without raising."""
    import h5py
    import numpy as np

    ctrl, _ = make_controller(qtbot, request)

    data_dir = tmp_path / "LightSheetData"
    data_dir.mkdir()
    # No root attrs; the wavelength must come from the _647nm_ filename token.
    h5_path = data_dir / "S10_647nm_stack_plane_00001.hdf5"
    with h5py.File(h5_path, "w") as f:
        f.create_dataset(
            "reconstructed_frame001", data=np.zeros((2, 4, 4), dtype=np.uint16)
        )

    browser = PastAcquisitionsBrowser(ctrl, data_dir=str(data_dir))
    entries = browser.list_acquisitions()
    assert len(entries) == 1
    entry = entries[0]
    assert entry.wavelength is not None
    # 647nm filename token -> display 647 (already normalized; 640 would
    # also normalize to 647).
    assert entry.wavelength == 647, entry.wavelength
    assert entry.format_label == "HDF5"
    assert entry.n_planes == 1


def test_past_acquisitions_browser_parses_compact_naming(
    qtbot, request, tmp_path
) -> None:
    """The compact filename convention (no _plane_00001 segment; no
    suffix on the first file, then _01, _02) must parse correctly — the
    wavelength is inferred from the _<wl>nm token (followed by '.' for
    the first file or '_' for suffixed files) and the sample name is
    recovered by stripping the _<scan_type> segment.

    Covers both the first-file form (foo_stack_555nm.hdf5) and the
    suffixed form (foo_stack_555nm_01.hdf5) with no root attrs (so the
    filename fallback path is exercised).
    """
    import h5py
    import numpy as np

    ctrl, _ = make_controller(qtbot, request)

    data_dir = tmp_path / "LightSheetData"
    data_dir.mkdir()
    # No root attrs — wavelength must come from the filename token.
    h5_path1 = data_dir / "tes1_stack_555nm.hdf5"
    with h5py.File(h5_path1, "w") as f:
        f.create_dataset(
            "reconstructed_frame001", data=np.zeros((2, 4, 4), dtype=np.uint16)
        )
    h5_path2 = data_dir / "tes1_stack_647nm_01.hdf5"
    with h5py.File(h5_path2, "w") as f:
        f.create_dataset(
            "reconstructed_frame001", data=np.zeros((2, 4, 4), dtype=np.uint16)
        )

    browser = PastAcquisitionsBrowser(ctrl, data_dir=str(data_dir))
    entries = browser.list_acquisitions()
    assert len(entries) == 2
    by_wl = {e.wavelength: e for e in entries}
    assert 555 in by_wl, "555nm first-file (no suffix) must parse"
    assert 647 in by_wl, "647nm suffixed file must parse"
    # Sample name strips the _stack scan-type segment.
    assert by_wl[555].sample == "tes1", by_wl[555].sample
    assert by_wl[647].sample == "tes1", by_wl[647].sample
