"""Frame intensity statistic for the adaptive feedback loop.

A very high percentile (default 99.99) is chosen because it tracks
sensor saturation risk better than the mean: a few saturated pixels
(bright brainstem) push the tail percentile to the sensor max even when
the mean is moderate. The 99.99th percentile catches much smaller bright
features than p99, so a small piece of tissue does not get lost in the
background majority.
This is the per-plane feedback signal the adaptive controller consumes.

Pure-numpy, no Qt, no HAL, no SDK — mirrors the ``lightsheet.gaussian``
/ ``lightsheet.waveforms`` pattern: module-level function, numpy in /
scalar out, no class.
"""

from __future__ import annotations

import numpy as np


def _uint_percentile(arr: np.ndarray, percentile: float) -> float:
    """``np.percentile`` 'linear' equivalent for unsigned-integer arrays.

    Uses a bincount histogram + CDF instead of a sort: O(n + bins)
    instead of O(n log n), which keeps a 2048x2048 uint16 frame near
    ~10 ms rather than ~30 ms. Exact-parity with ``np.percentile`` —
    linear interpolation between the order statistics at positions
    ``floor(h)`` and ``floor(h) + 1`` where ``h = (n - 1) * p / 100``.
    """
    cdf = np.bincount(arr.ravel()).cumsum()
    h = (arr.size - 1) * (percentile / 100.0)
    k = int(h)
    # Sorted position i holds the value of the first bin whose CDF
    # exceeds i — side="right" lands exactly on that bin.
    lo = int(np.searchsorted(cdf, k, side="right"))
    hi = int(np.searchsorted(cdf, k + 1, side="right"))
    return lo + (h - k) * (hi - lo)


def frame_intensity_pct(
    frame: np.ndarray | None,
    sensor_max: int = 65535,
    percentile: float = 99.99,
) -> float:
    """Return the ``percentile``-th percentile of ``frame`` as a
    fraction of ``sensor_max`` (0.0 to 1.0).

    Returns 0.0 for ``None``, empty arrays, or all-zero frames so the
    adaptive loop sees a "too dark" signal rather than crashing on a
    missing frame (e.g. a camera timeout that produced no data).

    The 99.99th percentile (not the mean) is used because it catches the
    saturated tail — a few saturated pixels in a bright region push the
    tail percentile to the sensor max even when the mean is moderate,
    giving the loop an early saturation-warning signal for small bright
    features that would be invisible to the 99th percentile.
    """
    if frame is None:
        return 0.0
    arr = np.asarray(frame)
    if arr.size == 0:
        return 0.0
    if not 0.0 <= percentile <= 100.0:
        raise ValueError("Percentiles must be in the range [0, 100]")
    if np.issubdtype(arr.dtype, np.unsignedinteger):
        tail = _uint_percentile(arr, percentile)
    else:
        tail = float(np.percentile(arr, percentile))
    if sensor_max <= 0:
        return 0.0
    return tail / float(sensor_max)
