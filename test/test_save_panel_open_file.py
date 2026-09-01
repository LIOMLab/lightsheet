"""Behavior tests for the SavePanelWidget open-file path (HDF5 + Zarr).

The "Open File" panel must accept BOTH HDF5 files (.hdf5) and OME-Zarr
stores (.ome.zarr folders). Zarr stores are directories, so the panel
branches on ``os.path.isdir``: directory → Zarr store, file → HDF5. The
dataset listing and per-dataset read paths handle both formats.

These tests construct a real ``Controller_MainWindow`` via
``make_controller``, write a real HDF5 file and a real OME-Zarr store to
``tmp_path``, and exercise the panel's listing + read helpers directly
(no file-dialog interaction — the helpers take a path).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from pytest import FixtureRequest
from pytestqt.qtbot import QtBot

pytest.importorskip("PySide6")


def _write_hdf5(path: Path, datasets: dict[str, np.ndarray]) -> None:
    import h5py

    with h5py.File(path, "w") as f:  # ty: ignore[invalid-argument-type]
        for name, arr in datasets.items():
            f.create_dataset(name, data=arr)


def _write_zarr_store(
    path: Path,
    data: np.ndarray,
    n_channels: int = 1,
    with_acquisition: bool = True,
) -> None:
    """Write a minimal (c, z, y, x) OME-Zarr L0 array plus an
    /acquisition group with the scan metadata attrs the panel reads
    (mirrors what ZarrSaver._write_acquisition_group writes)."""
    import zarr

    root = zarr.open_group(path, mode="w")
    root.create_array("0", data=data)
    if with_acquisition:
        acq = root.create_group("acquisition")
        acq.attrs["Sample Name"] = "test-sample"
        acq.attrs["exposure_time_s"] = 0.05
        acq.attrs["sample_rate"] = 100000.0


def test_list_hdf5_datasets(
    qtbot: QtBot, request: FixtureRequest, tmp_path: Path
) -> None:
    """_list_hdf5_datasets returns the top-level dataset names."""
    from _helpers.controller_fixture import (
        make_controller,
    )

    ctrl, _ = make_controller(qtbot, request)
    h5_path = tmp_path / "sample_555nm.hdf5"
    _write_hdf5(
        h5_path,
        {
            "reconstructed_frame001": np.zeros((4, 4), dtype=np.uint16),
            "reconstructed_frame002": np.zeros((4, 4), dtype=np.uint16),
        },
    )
    names = ctrl.save_panel._list_hdf5_datasets(str(h5_path))
    assert names == ["reconstructed_frame001", "reconstructed_frame002"], names


def test_list_zarr_datasets_single_channel(
    qtbot: QtBot, request: FixtureRequest, tmp_path: Path
) -> None:
    """_list_zarr_datasets for a (1, z, y, x) store returns plane_NNNN
    labels (one per plane), matching the HDF5 reconstructed_frameNNN UX."""
    from _helpers.controller_fixture import (
        make_controller,
    )

    ctrl, _ = make_controller(qtbot, request)
    zarr_path = tmp_path / "sample_555nm.ome.zarr"
    _write_zarr_store(
        zarr_path,
        np.zeros((1, 3, 4, 4), dtype=np.uint16),
        n_channels=1,
    )
    labels = ctrl.save_panel._list_zarr_datasets(str(zarr_path))
    assert labels == ["plane_0001", "plane_0002", "plane_0003"], labels


def test_list_zarr_datasets_multi_channel(
    qtbot: QtBot, request: FixtureRequest, tmp_path: Path
) -> None:
    """_list_zarr_datasets for a (2, z, y, x) store returns
    chN_plane_NNNN labels so the operator can view any (channel, plane)."""
    from _helpers.controller_fixture import (
        make_controller,
    )

    ctrl, _ = make_controller(qtbot, request)
    zarr_path = tmp_path / "sample.ome.zarr"
    _write_zarr_store(
        zarr_path,
        np.zeros((2, 3, 4, 4), dtype=np.uint16),
        n_channels=2,
    )
    labels = ctrl.save_panel._list_zarr_datasets(str(zarr_path))
    assert labels == [
        "ch0_plane_0001", "ch0_plane_0002", "ch0_plane_0003",
        "ch1_plane_0001", "ch1_plane_0002", "ch1_plane_0003",
    ], labels


def test_read_hdf5_dataset_returns_data_and_attrs(
    qtbot: QtBot, request: FixtureRequest, tmp_path: Path
) -> None:
    """_read_hdf5_dataset returns (data, attrs) for the named dataset."""
    from _helpers.controller_fixture import (
        make_controller,
    )

    ctrl, _ = make_controller(qtbot, request)
    h5_path = tmp_path / "sample_555nm.hdf5"
    arr = np.zeros((4, 4), dtype=np.uint16)
    arr[0, 0] = 42
    _write_hdf5(h5_path, {"reconstructed_frame001": arr})
    data, attrs = ctrl.save_panel._read_hdf5_dataset(
        str(h5_path), "reconstructed_frame001"
    )
    assert data[0, 0] == 42
    assert isinstance(attrs, dict)


def test_read_zarr_dataset_single_channel(
    qtbot: QtBot, request: FixtureRequest, tmp_path: Path
) -> None:
    """_read_zarr_dataset returns the (y, x) slice for plane_NNNN from
    the L0 (1, z, y, x) array, with the correct pixel values."""
    from _helpers.controller_fixture import (
        make_controller,
    )

    ctrl, _ = make_controller(qtbot, request)
    zarr_path = tmp_path / "sample_555nm.ome.zarr"
    data = np.zeros((1, 3, 4, 4), dtype=np.uint16)
    data[0, 1, 0, 0] = 99  # plane 2 (0-based index 1)
    _write_zarr_store(zarr_path, data, n_channels=1)
    slice_, attrs = ctrl.save_panel._read_zarr_dataset(
        str(zarr_path), "plane_0002"
    )
    assert slice_.shape == (4, 4)
    assert slice_[0, 0] == 99
    # Attrs come from the /acquisition group (the Zarr analog of the
    # HDF5 dataset attrs).
    assert attrs.get("Sample Name") == "test-sample"
    assert attrs.get("exposure_time_s") == 0.05


def test_read_zarr_dataset_multi_channel(
    qtbot: QtBot, request: FixtureRequest, tmp_path: Path
) -> None:
    """_read_zarr_dataset returns the (y, x) slice for chN_plane_NNNN
    from the L0 (2, z, y, x) array, indexing the correct channel."""
    from _helpers.controller_fixture import (
        make_controller,
    )

    ctrl, _ = make_controller(qtbot, request)
    zarr_path = tmp_path / "sample.ome.zarr"
    data = np.zeros((2, 3, 4, 4), dtype=np.uint16)
    data[1, 2, 0, 0] = 77  # channel 1, plane 3 (0-based index 2)
    _write_zarr_store(zarr_path, data, n_channels=2)
    slice_, attrs = ctrl.save_panel._read_zarr_dataset(
        str(zarr_path), "ch1_plane_0003"
    )
    assert slice_.shape == (4, 4)
    assert slice_[0, 0] == 77
    # Attrs come from the /acquisition group.
    assert attrs.get("Sample Name") == "test-sample"


def test_list_zarr_datasets_rejects_no_l0_array(
    qtbot: QtBot, request: FixtureRequest, tmp_path: Path
) -> None:
    """_list_zarr_datasets raises ValueError for a store with no L0
    '0' array so the caller's except path surfaces a clear message."""
    import zarr
    from _helpers.controller_fixture import (
        make_controller,
    )

    ctrl, _ = make_controller(qtbot, request)
    zarr_path = tmp_path / "empty.ome.zarr"
    zarr.open_group(str(zarr_path), mode="w")  # no arrays
    with pytest.raises(ValueError):
        ctrl.save_panel._list_zarr_datasets(str(zarr_path))
