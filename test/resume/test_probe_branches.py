"""Branch-coverage tests for ``lightsheet/resume/probe.py``.

Targets the branches left uncovered by ``test_probe.py`` (the happy paths):

- ``probe_hdf5``: no image datasets -> 0; 3-D dataset small-region read;
  non-final unreadable dataset -> ``ResumeProbeError``; torn final dataset
  -> counted short; non-Dataset member -> ``ValueError``.
- ``truncate_hdf5_tail`` / ``reopen_hdf5_append``: unopenable file ->
  ``ResumeProbeError``.
- ``probe_zarr``: non-group root, missing/non-array ``0`` node, rank != 4,
  channel token without ``ch`` prefix, channel index out of range,
  zero-plane store, missing ``nchunks_initialized``, multi-channel count.
- ``reopen_zarr_l0``: unopenable store, non-group root, missing/non-array
  ``0`` node, shape mismatch.
- ``manifest_dir_contains``: mixed relative/absolute paths -> commonpath
  ``ValueError`` re-raised as the containment error.

Pure-Python — no Qt, no HAL, no hardware.
"""

from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np
import pytest
import zarr

import lightsheet.resume.probe as probe_mod
from lightsheet.resume.probe import (
    ResumeProbeError,
    _read_small_region,
    manifest_dir_contains,
    probe_hdf5,
    probe_zarr,
    reopen_hdf5_append,
    reopen_zarr_l0,
    truncate_hdf5_tail,
)


def _hdf5_with_datasets(path: Path, n: int) -> None:
    with h5py.File(str(path), "w") as f:
        for i in range(1, n + 1):
            f.create_dataset(
                f"reconstructed_frame{i:03d}",
                data=np.full((4, 4), i, dtype=np.uint16),
            )


# --------------------------------------------------------------------- #
# probe_hdf5
# --------------------------------------------------------------------- #


def test_probe_hdf5_no_image_datasets_returns_zero(tmp_path: Path) -> None:
    """A file with only non-image datasets (rank 0/1) yields 0 planes."""
    path = tmp_path / "empty.hdf5"
    with h5py.File(str(path), "w") as f:
        f.create_dataset("meta", data=np.array([1, 2, 3], dtype=np.uint16))
    assert probe_hdf5(path) == 0


def test_probe_hdf5_3d_dataset_counts(tmp_path: Path) -> None:
    """Rank-3 datasets are image planes; the small-region read uses the
    3-D corner slice."""
    path = tmp_path / "vol.hdf5"
    with h5py.File(str(path), "w") as f:
        f.create_dataset(
            "reconstructed_frame001",
            data=np.zeros((2, 4, 4), dtype=np.uint16),
        )
    assert probe_hdf5(path) == 1


def test_read_small_region_rejects_unsupported_rank(tmp_path: Path) -> None:
    """Direct call with a rank-1 dataset raises the unsupported-rank
    ValueError (defensive — the probe only feeds it rank 2/3)."""
    path = tmp_path / "rank1.hdf5"
    with h5py.File(str(path), "w") as f:
        f.create_dataset("vec", data=np.arange(4, dtype=np.uint16))
    with (
        h5py.File(str(path), "r") as f,
        pytest.raises(ValueError, match="unsupported rank"),
    ):
        _read_small_region(f["vec"])  # ty: ignore[invalid-argument-type]


def test_probe_hdf5_torn_tail_counts_short(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the LAST dataset fails the small-region read the probe counts
    the file short (torn tail is truncatable) instead of raising."""
    path = tmp_path / "torn.hdf5"
    _hdf5_with_datasets(path, 3)

    def _fail_last(ds: h5py.Dataset) -> None:
        if ds.name.endswith("003"):
            raise OSError("torn chunk")
        _read_small_region(ds)

    monkeypatch.setattr(probe_mod, "_read_small_region", _fail_last)
    assert probe_hdf5(path) == 2


def test_probe_hdf5_nonfinal_read_failure_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A read failure on a NON-final dataset is a real corruption —
    ``ResumeProbeError``, not a torn tail."""
    path = tmp_path / "corrupt_mid.hdf5"
    _hdf5_with_datasets(path, 3)

    def _fail_middle(ds: h5py.Dataset) -> None:
        if ds.name.endswith("002"):
            raise RuntimeError("bad chunk")
        _read_small_region(ds)

    monkeypatch.setattr(probe_mod, "_read_small_region", _fail_middle)
    with pytest.raises(ResumeProbeError, match="unreadable"):
        probe_hdf5(path)


def test_probe_hdf5_non_dataset_member_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If a top-level member that passed the image filter turns out not to
    be a Dataset on re-lookup, probe_hdf5 raises ValueError."""
    path = tmp_path / "grp.hdf5"
    with h5py.File(str(path), "w") as f:
        f.create_group("reconstructed_frame001")

    monkeypatch.setattr(probe_mod, "_is_image_dataset", lambda ds: True)
    with pytest.raises(ValueError, match="not a dataset"):
        probe_hdf5(path)


# --------------------------------------------------------------------- #
# truncate_hdf5_tail / reopen_hdf5_append error paths
# --------------------------------------------------------------------- #


def test_truncate_hdf5_tail_unopenable_raises(tmp_path: Path) -> None:
    path = tmp_path / "bad.hdf5"
    path.write_bytes(b"not hdf5")
    with pytest.raises(ResumeProbeError, match="cannot truncate"):
        truncate_hdf5_tail(path, 1)


def test_reopen_hdf5_append_unopenable_raises(tmp_path: Path) -> None:
    path = tmp_path / "bad.hdf5"
    path.write_bytes(b"not hdf5")
    with pytest.raises(ResumeProbeError, match="cannot reopen"):
        reopen_hdf5_append(path)


# --------------------------------------------------------------------- #
# probe_zarr rejection branches
# --------------------------------------------------------------------- #


def test_probe_zarr_root_not_group_raises(tmp_path: Path) -> None:
    """A store whose root is a bare array is rejected."""
    path = tmp_path / "arr.zarr"
    zarr.open_array(str(path), mode="w", shape=(4, 4), chunks=(4, 4), dtype=np.uint16)
    with pytest.raises(ResumeProbeError, match="root is not a group"):
        probe_zarr(path)


def test_probe_zarr_missing_l0_raises(tmp_path: Path) -> None:
    path = tmp_path / "no_l0.zarr"
    root = zarr.open(str(path), mode="w")
    assert isinstance(root, zarr.Group)
    root.create_array("1", shape=(1, 1, 4, 4), chunks=(1, 1, 4, 4), dtype=np.uint16)
    with pytest.raises(ResumeProbeError, match="no level-0 array"):
        probe_zarr(path)


def test_probe_zarr_l0_not_array_raises(tmp_path: Path) -> None:
    path = tmp_path / "grp0.zarr"
    root = zarr.open(str(path), mode="w")
    assert isinstance(root, zarr.Group)
    root.create_group("0")
    with pytest.raises(ResumeProbeError, match="not an array"):
        probe_zarr(path)


def test_probe_zarr_wrong_rank_raises(tmp_path: Path) -> None:
    path = tmp_path / "rank2.zarr"
    root = zarr.open(str(path), mode="w")
    assert isinstance(root, zarr.Group)
    root.create_array("0", shape=(4, 4), chunks=(4, 4), dtype=np.uint16)
    with pytest.raises(ResumeProbeError, match="rank 2"):
        probe_zarr(path)


def test_probe_zarr_channel_out_of_range_raises(tmp_path: Path) -> None:
    path = tmp_path / "one_ch.zarr"
    root = zarr.open(str(path), mode="w")
    assert isinstance(root, zarr.Group)
    root.create_array("0", shape=(1, 3, 4, 4), chunks=(1, 1, 4, 4), dtype=np.uint16)
    with pytest.raises(ResumeProbeError, match="out of range"):
        probe_zarr(path, channel="ch5")


def test_probe_zarr_numeric_channel_token(tmp_path: Path) -> None:
    """A channel token without the ``ch`` prefix is parsed as an int."""
    path = tmp_path / "num_tok.zarr"
    root = zarr.open(str(path), mode="w")
    assert isinstance(root, zarr.Group)
    arr = root.create_array(
        "0", shape=(1, 3, 4, 4), chunks=(1, 1, 4, 4), dtype=np.uint16
    )
    arr[0, 0, :, :] = np.ones((4, 4), dtype=np.uint16)
    assert probe_zarr(path, channel="0") == 1


def test_probe_zarr_zero_plane_store_returns_zero(tmp_path: Path) -> None:
    path = tmp_path / "zero.zarr"
    root = zarr.open(str(path), mode="w")
    assert isinstance(root, zarr.Group)
    root.create_array("0", shape=(1, 0, 4, 4), chunks=(1, 1, 4, 4), dtype=np.uint16)
    assert probe_zarr(path) == 0


def test_probe_zarr_missing_nchunks_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An L0 array without ``nchunks_initialized`` is rejected."""
    path = tmp_path / "nochunks.zarr"
    root = zarr.open(str(path), mode="w")
    assert isinstance(root, zarr.Group)
    arr = root.create_array(
        "0", shape=(1, 3, 4, 4), chunks=(1, 1, 4, 4), dtype=np.uint16
    )
    arr[0, 0, :, :] = np.ones((4, 4), dtype=np.uint16)
    monkeypatch.setattr(zarr.Array, "nchunks_initialized", None)
    with pytest.raises(ResumeProbeError, match="nchunks_initialized"):
        probe_zarr(path)


def test_probe_zarr_multichannel_divides_by_channels(tmp_path: Path) -> None:
    """With >1 channel the initialized-chunk count is divided by the
    channel count to get per-channel planes."""
    path = tmp_path / "two_ch.zarr"
    root = zarr.open(str(path), mode="w")
    assert isinstance(root, zarr.Group)
    arr = root.create_array(
        "0", shape=(2, 5, 4, 4), chunks=(1, 1, 4, 4), dtype=np.uint16
    )
    # 3 planes written on ch0, 2 on ch1 -> 5 chunks total -> min(5//2, 5) = 2.
    for z in range(3):
        arr[0, z, :, :] = np.ones((4, 4), dtype=np.uint16)
    for z in range(2):
        arr[1, z, :, :] = np.ones((4, 4), dtype=np.uint16)
    assert probe_zarr(path, channel="ch0") == 2
    assert probe_zarr(path, channel="ch1") == 2


# --------------------------------------------------------------------- #
# reopen_zarr_l0 rejection branches
# --------------------------------------------------------------------- #


def test_reopen_zarr_l0_missing_store_raises(tmp_path: Path) -> None:
    with pytest.raises(ResumeProbeError, match="cannot reopen"):
        reopen_zarr_l0(tmp_path / "gone.zarr", (1, 1, 4, 4), np.uint16)


def test_reopen_zarr_l0_root_not_group_raises(tmp_path: Path) -> None:
    path = tmp_path / "arr.zarr"
    zarr.open_array(str(path), mode="w", shape=(4, 4), chunks=(4, 4), dtype=np.uint16)
    with pytest.raises(ResumeProbeError, match="root is not a group"):
        reopen_zarr_l0(path, (4, 4), np.uint16)


def test_reopen_zarr_l0_missing_node_raises(tmp_path: Path) -> None:
    path = tmp_path / "empty_grp.zarr"
    zarr.open(str(path), mode="w")
    with pytest.raises(ResumeProbeError, match="no level-0 array"):
        reopen_zarr_l0(path, (1, 1, 4, 4), np.uint16)


def test_reopen_zarr_l0_node_not_array_raises(tmp_path: Path) -> None:
    path = tmp_path / "grp_node.zarr"
    root = zarr.open(str(path), mode="w")
    assert isinstance(root, zarr.Group)
    root.create_group("0")
    with pytest.raises(ResumeProbeError, match="not an array"):
        reopen_zarr_l0(path, (1, 1, 4, 4), np.uint16)


def test_reopen_zarr_l0_shape_mismatch_raises(tmp_path: Path) -> None:
    path = tmp_path / "shape.zarr"
    root = zarr.open(str(path), mode="w")
    assert isinstance(root, zarr.Group)
    root.create_array("0", shape=(1, 5, 4, 4), chunks=(1, 1, 4, 4), dtype=np.uint16)
    with pytest.raises(ResumeProbeError, match="shape mismatch"):
        reopen_zarr_l0(path, (1, 4, 4, 4), np.uint16)


# --------------------------------------------------------------------- #
# manifest_dir_contains
# --------------------------------------------------------------------- #


def test_manifest_dir_contains_relative_outside_rejected(
    tmp_path: Path,
) -> None:
    """A relative save directory resolves to an absolute path under CWD;
    an unrelated absolute target is still rejected by the containment
    check."""
    with pytest.raises(ValueError, match="outside save directory"):
        manifest_dir_contains("relative/save", str(tmp_path / "abs.hdf5"))
