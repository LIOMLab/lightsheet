"""Unit tests for per-format resume probe and truncation helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import h5py
import numpy as np
import pytest
import zarr

from lightsheet.resume.probe import (
    ResumeProbeError,
    manifest_dir_contains,
    probe_hdf5,
    probe_zarr,
    reopen_hdf5_append,
    reopen_zarr_l0,
    truncate_hdf5_tail,
)


def _hdf5_with_datasets(path: Path, n: int, prefix: str = "reconstructed_frame") -> None:
    with h5py.File(path, "w") as f:
        for i in range(1, n + 1):
            f.create_dataset(f"{prefix}{i:03d}", data=np.full((4, 4), i, dtype=np.uint16))


def _partial_hdf5(path: Path, n: int) -> None:
    """Create an HDF5 with the first n-1 datasets complete and the n-th torn."""
    with h5py.File(path, "w") as f:
        for i in range(1, n):
            f.create_dataset(f"reconstructed_frame{i:03d}", data=np.full((4, 4), i, dtype=np.uint16))
        # Create a torn dataset: declare the shape but do not write any data.
        f.create_dataset(
            f"reconstructed_frame{n:03d}",
            shape=(4, 4),
            dtype=np.uint16,
            fillvalue=0,
        )


def _zarr_with_planes(path: Path, n_planes: int, n_channels: int = 1) -> Any:
    root = zarr.open(str(path), mode="w")
    shape = (n_channels, n_planes, 4, 4)
    chunks = (1, 1, 4, 4)
    arr = root.create_array(
        "0",
        shape=shape,
        chunks=chunks,
        dtype=np.uint16,
    )
    for z in range(n_planes):
        for c in range(n_channels):
            arr[c, z, :, :] = np.full((4, 4), z + 1, dtype=np.uint16)
    return root


def _partial_zarr(path: Path, n_written: int, n_planes: int) -> Any:
    root = zarr.open(str(path), mode="w")
    shape = (1, n_planes, 4, 4)
    chunks = (1, 1, 4, 4)
    arr = root.create_array(
        "0",
        shape=shape,
        chunks=chunks,
        dtype=np.uint16,
    )
    for z in range(n_written):
        arr[0, z, :, :] = np.full((4, 4), z + 1, dtype=np.uint16)
    return root, arr


def test_probe_hdf5_counts_datasets(tmp_path: Path) -> None:
    path = tmp_path / "test.hdf5"
    _hdf5_with_datasets(path, 3)
    assert probe_hdf5(path) == 3


def test_probe_hdf5_raises_on_corrupt_file(tmp_path: Path) -> None:
    path = tmp_path / "corrupt.hdf5"
    path.write_bytes(b"not an hdf5 file")
    with pytest.raises(ResumeProbeError):
        probe_hdf5(path)


def test_probe_hdf5_counts_only_full_datasets(tmp_path: Path) -> None:
    path = tmp_path / "two.hdf5"
    _hdf5_with_datasets(path, 2)
    assert probe_hdf5(path) == 2


def test_truncate_hdf5_tail_removes_last_n(tmp_path: Path) -> None:
    path = tmp_path / "tail.hdf5"
    _hdf5_with_datasets(path, 5)
    truncate_hdf5_tail(path, 3)
    assert probe_hdf5(path) == 3
    with h5py.File(path, "r") as f:
        names = [k for k in f.keys() if k.startswith("reconstructed_frame")]
        assert sorted(names) == [
            "reconstructed_frame001",
            "reconstructed_frame002",
            "reconstructed_frame003",
        ]


def test_truncate_hdf5_tail_noop_when_keep_is_full(tmp_path: Path) -> None:
    path = tmp_path / "keep.hdf5"
    _hdf5_with_datasets(path, 2)
    truncate_hdf5_tail(path, 2)
    assert probe_hdf5(path) == 2


def test_reopen_hdf5_append(tmp_path: Path) -> None:
    path = tmp_path / "append.hdf5"
    _hdf5_with_datasets(path, 1)
    f = reopen_hdf5_append(path)
    assert isinstance(f, h5py.File)
    f.create_dataset("reconstructed_frame002", data=np.full((4, 4), 2, dtype=np.uint16))
    f.close()
    assert probe_hdf5(path) == 2


def test_probe_zarr_counts_written_planes(tmp_path: Path) -> None:
    path = tmp_path / "partial.zarr"
    _partial_zarr(path, 3, 5)
    assert probe_zarr(path, channel="ch0") == 3


def test_probe_zarr_raises_on_missing_store(tmp_path: Path) -> None:
    with pytest.raises(ResumeProbeError):
        probe_zarr(tmp_path / "missing.zarr")


def test_reopen_zarr_l0_matches_shape_and_dtype(tmp_path: Path) -> None:
    path = tmp_path / "resume.zarr"
    _zarr_with_planes(path, 5)
    arr = reopen_zarr_l0(path, (1, 5, 4, 4), np.uint16)
    assert arr.shape == (1, 5, 4, 4)
    assert arr.dtype == np.uint16


def test_reopen_zarr_l0_raises_on_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "mismatch.zarr"
    _zarr_with_planes(path, 5)
    with pytest.raises(ResumeProbeError):
        reopen_zarr_l0(path, (1, 5, 4, 4), np.float32)


def test_manifest_dir_contains_accepts_inside(tmp_path: Path) -> None:
    save_dir = tmp_path / "save"
    save_dir.mkdir()
    target = save_dir / "sub" / "acq.hdf5"
    target.parent.mkdir()
    manifest_dir_contains(str(save_dir), str(target))


def test_manifest_dir_contains_rejects_outside(tmp_path: Path) -> None:
    save_dir = tmp_path / "save"
    save_dir.mkdir()
    outside = tmp_path / "outside.hdf5"
    with pytest.raises(ValueError):
        manifest_dir_contains(str(save_dir), str(outside))
