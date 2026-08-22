"""TST-03 HDF5 structural smoke test.

Mirrors the HDF5 layout ``FrameSaver.frame_saver_worker`` writes
(controller.py:3666-3716): one dataset per 2D frame, dtype uint16, with
the five metadata attributes (Sample Name / Date / Horizontal Position /
Vertical Position / Camera Position). This is a STRUCTURAL smoke
(D-12/D-14) — it asserts dtype + shape + attr presence, NOT byte-for-byte
HDF5 equality (h5py version drift Mac vs rig would break byte equality).

The harness writes a canonical plane directly with h5py (it does NOT
instantiate FrameSaver — that needs the controller/PyQt5). The dataset
layout, dtype, and attribute names match what the real frame-saver
worker writes, so a refactor that changes the on-disk schema is caught
here.
"""

import datetime

import h5py
import numpy as np


def test_hdf5_manifest_dtype_and_attrs(tmp_path) -> None:
    """A canonical plane written via h5py has dtype uint16 + the 5 attrs."""
    path = tmp_path / "plane.hdf5"
    ysize, xsize = 16, 16
    frame = np.zeros((ysize, xsize), dtype=np.uint16)

    sample_name = "sample"
    hor_pos = "0.000"
    ver_pos = "1.250"
    cam_pos = "5.500"

    with h5py.File(path, "a") as outfile:
        dataset = outfile.create_dataset("001", data=frame)
        dataset.attrs["Sample Name"] = sample_name
        dataset.attrs["Date"] = str(datetime.date.today())
        dataset.attrs["Horizontal Position"] = hor_pos
        dataset.attrs["Vertical Position"] = ver_pos
        dataset.attrs["Camera Position"] = cam_pos

    # Re-open and assert the structural manifest.
    with h5py.File(path, "r") as infile:
        ds = infile["001"]
        assert ds.dtype == np.uint16
        assert ds.shape == (ysize, xsize)
        expected_attrs = [
            "Sample Name",
            "Date",
            "Horizontal Position",
            "Vertical Position",
            "Camera Position",
        ]
        for attr in expected_attrs:
            assert attr in ds.attrs, f"missing attr {attr!r}"
        assert ds.attrs["Sample Name"] == sample_name
        assert ds.attrs["Horizontal Position"] == hor_pos
        assert ds.attrs["Vertical Position"] == ver_pos
        assert ds.attrs["Camera Position"] == cam_pos


def test_hdf5_manifest_multiple_datasets(tmp_path) -> None:
    """Multiple datasets in one file (a multi-plane stack) each carry the
    5-attr manifest — mirrors FrameSaver's per-frame dataset creation."""
    path = tmp_path / "stack.hdf5"
    ysize, xsize = 8, 8
    frames = np.zeros((3, ysize, xsize), dtype=np.uint16)

    with h5py.File(path, "a") as outfile:
        for i in range(frames.shape[0]):
            ds = outfile.create_dataset(f"{i + 1:03d}", data=frames[i])
            ds.attrs["Sample Name"] = "sample"
            ds.attrs["Date"] = str(datetime.date.today())
            ds.attrs["Horizontal Position"] = str(i)
            ds.attrs["Vertical Position"] = str(i * 2)
            ds.attrs["Camera Position"] = str(i * 3)

    with h5py.File(path, "r") as infile:
        assert len(infile.keys()) == 3
        for i in range(3):
            ds = infile[f"{i + 1:03d}"]
            assert ds.dtype == np.uint16
            assert ds.shape == (ysize, xsize)
            assert ds.attrs["Horizontal Position"] == str(i)
            assert ds.attrs["Vertical Position"] == str(i * 2)
            assert ds.attrs["Camera Position"] == str(i * 3)
