"""Per-format resume probe and truncation helpers.

Pure-Python file I/O utilities that validate partial acquisitions before
append. All path checks use realpath + os.path.commonpath to keep the
resume target inside the operator-selected save directory.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

import h5py
import numpy as np
import zarr

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class ResumeProbeError(Exception):
    """Raised when an HDF5/Zarr file cannot be probed for resumption."""


# Names are written as ``{datasets_name}{counter:03d}`` (e.g.
# ``reconstructed_frame001``). The suffix is at least three digits.
_DATASET_INDEX_RE = re.compile(r"(\d{3,})$")


def _dataset_index(name: str) -> int:
    m = _DATASET_INDEX_RE.search(name)
    return int(m.group(1)) if m else -1


def _read_small_region(ds: h5py.Dataset) -> None:
    """Touch a tiny corner of the dataset to verify the chunk is readable.

    Torn or partially-written datasets often exist as metadata entries but
    fail when their storage is actually read, so a 1x1 slice at the origin
    is the cheapest integrity probe that catches a torn tail.
    """
    if ds.ndim == 2:
        ds[0, 0]
    elif ds.ndim == 3:
        ds[0, 0, 0]
    else:
        raise ValueError(
            f"dataset {ds.name!r} has unsupported rank {ds.ndim}"
        )


def _is_image_dataset(ds: Any) -> bool:
    return isinstance(ds, h5py.Dataset) and ds.ndim in (2, 3)


def probe_hdf5(path: Path | str) -> int:
    """Return the number of fully readable datasets in an HDF5 file.

    Top-level datasets whose rank is 2 or 3 are treated as image planes.
    The file is opened read-only; if it cannot be opened or a non-final
    dataset fails the small-region read, ``ResumeProbeError`` is raised.
    A torn final dataset is not counted — the caller should truncate it
    before appending.
    """
    path = Path(path)
    try:
        with h5py.File(path, "r") as f:
            names = [
                k for k in f.keys() if _is_image_dataset(f[k])
            ]
            if not names:
                return 0
            names.sort(key=_dataset_index)
            good = 0
            for i, name in enumerate(names):
                ds = f[name]
                try:
                    _read_small_region(ds)
                except (OSError, RuntimeError, ValueError) as e:
                    if i == len(names) - 1:
                        # Torn tail: the last dataset is unreadable.
                        logger.warning(
                            "HDF5 %s last dataset %s is torn (%s); truncatable",
                            path,
                            name,
                            e,
                        )
                        break
                    raise ResumeProbeError(
                        f"HDF5 {path} dataset {name} is unreadable: {e}"
                    ) from e
                good += 1
            return good
    except (OSError, RuntimeError) as e:
        raise ResumeProbeError(f"cannot open HDF5 {path}: {e}") from e


def truncate_hdf5_tail(path: Path | str, keep_datasets: int) -> None:
    """Remove all image datasets with index >= ``keep_datasets`` in place.

    The file is opened in append mode and top-level image datasets
    whose 1-based index is greater than ``keep_datasets`` are deleted.
    Any datasets at index ``1..keep_datasets`` are left untouched.
    """
    path = Path(path)
    try:
        with h5py.File(path, "a") as f:
            to_remove = [
                k
                for k in f.keys()
                if _is_image_dataset(f[k]) and _dataset_index(k) > keep_datasets
            ]
            # Remove in reverse index order so earlier keys' indices stay
            # stable during deletion.
            to_remove.sort(key=_dataset_index, reverse=True)
            for name in to_remove:
                del f[name]
    except (OSError, RuntimeError) as e:
        raise ResumeProbeError(
            f"cannot truncate HDF5 tail {path}: {e}"
        ) from e


def reopen_hdf5_append(path: Path | str) -> h5py.File:
    """Open an existing HDF5 file in append mode for resume writing.

    The caller owns closing the returned handle. If the file cannot be
    opened, ``ResumeProbeError`` is raised.
    """
    path = Path(path)
    try:
        return h5py.File(path, "a")
    except (OSError, RuntimeError) as e:
        raise ResumeProbeError(
            f"cannot reopen HDF5 {path} for append: {e}"
        ) from e


def probe_zarr(path: Path | str, channel: str = "ch0") -> int:
    """Return the number of Z planes with committed chunks for a channel.

    The store is opened read-only. The level-0 array (node ``"0"``) is
    read. If ``nchunks_initialized`` is available it is used directly;
    because the L0 chunk grid is ``(1, 1, y, x)`` each initialized chunk
    corresponds to one ``(channel, z)`` plane, so the per-channel count
    is the total initialized chunks divided by the number of channels.
    Unopenable stores raise ``ResumeProbeError``.
    """
    path = Path(path)
    try:
        root = zarr.open(str(path), mode="r")
    except Exception as e:
        raise ResumeProbeError(f"cannot open zarr store {path}: {e}") from e

    try:
        arr = root["0"]
    except Exception as e:
        raise ResumeProbeError(
            f"zarr store {path} has no level-0 array: {e}"
        ) from e

    if not isinstance(arr, zarr.Array):
        raise ResumeProbeError(f"zarr node 0 in {path} is not an array")

    if arr.ndim != 4:
        raise ResumeProbeError(
            f"zarr L0 in {path} has rank {arr.ndim}, expected 4"
        )

    # Map the caller's channel token to an axis-0 index. Current saves use
    # the integer channel index (0, 1, ...); accept "ch0"/"ch1" tokens too.
    if channel.startswith("ch"):
        channel_idx = int(channel[2:])
    else:
        channel_idx = int(channel)
    if not (0 <= channel_idx < arr.shape[0]):
        raise ResumeProbeError(
            f"channel index {channel_idx} out of range for zarr shape {arr.shape}"
        )

    n_planes = int(arr.shape[1])
    if n_planes == 0:
        return 0

    n_initialized = getattr(arr, "nchunks_initialized", None)
    if n_initialized is None:
        raise ResumeProbeError(
            f"zarr L0 in {path} does not expose nchunks_initialized"
        )

    total = int(n_initialized)
    if arr.shape[0] == 1:
        return min(total, n_planes)
    # The chunk grid is one chunk per (channel, z) plane.
    return min(total // arr.shape[0], n_planes)


def reopen_zarr_l0(
    path: Path | str,
    shape: tuple[int, ...],
    dtype: Any,
    channel: str = "ch0",
) -> zarr.Array:
    """Open an existing Zarr level-0 array for resume writing.

    The store is opened in read/write mode. The existing array at node
    ``"0"`` must match the requested ``shape`` and ``dtype`` exactly.
    Mismatches raise ``ResumeProbeError`` so the caller can fall back to
    a new fileset.
    """
    path = Path(path)
    try:
        root = zarr.open(str(path), mode="r+")
    except Exception as e:
        raise ResumeProbeError(
            f"cannot reopen zarr store {path} for append: {e}"
        ) from e

    try:
        arr = root["0"]
    except Exception as e:
        raise ResumeProbeError(
            f"zarr store {path} has no level-0 array: {e}"
        ) from e

    if not isinstance(arr, zarr.Array):
        raise ResumeProbeError(f"zarr node 0 in {path} is not an array")

    if arr.shape != tuple(shape):
        raise ResumeProbeError(
            f"zarr L0 shape mismatch: {arr.shape} != {shape}"
        )

    if arr.dtype != dtype:
        raise ResumeProbeError(
            f"zarr L0 dtype mismatch: {arr.dtype} != {dtype}"
        )

    return arr


def manifest_dir_contains(save_directory: str, target: str) -> None:
    """Raise ``ValueError`` if ``target`` is not contained in ``save_directory``.

    Both paths are resolved with ``realpath`` / ``normpath`` before the
    comparison, so symlinks that point outside the save directory are
    rejected.
    """
    save_dir = Path(os.path.realpath(os.path.normpath(save_directory)))
    resolved = Path(os.path.realpath(os.path.normpath(target)))
    try:
        common = os.path.commonpath([str(save_dir), str(resolved)])
    except ValueError as e:
        raise ValueError(
            f"target {resolved!r} is outside save directory {save_dir!r}"
        ) from e
    if Path(common) != save_dir:
        raise ValueError(
            f"target {resolved!r} is outside save directory {save_dir!r}"
        )
