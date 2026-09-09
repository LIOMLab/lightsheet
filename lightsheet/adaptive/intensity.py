"""Frame intensity statistic for the adaptive feedback loop.

The 99th-percentile is chosen because it tracks sensor saturation risk
better than the mean: a few saturated pixels (bright brainstem) push
the 99th percentile to the sensor max even when the mean is moderate.
This is the per-plane feedback signal the adaptive controller consumes.

Pure-numpy, no Qt, no HAL, no SDK — mirrors the ``lightsheet.gaussian``
/ ``lightsheet.waveforms`` pattern: module-level function, numpy in /
scalar out, no class.
"""

from __future__ import annotations

import numpy as np


def frame_intensity_pct(frame: np.ndarray | None, sensor_max: int = 65535) -> float:
    """Return the 99th-percentile of ``frame`` as a fraction of
    ``sensor_max`` (0.0 to 1.0).

    Returns 0.0 for ``None``, empty arrays, or all-zero frames so the
    adaptive loop sees a "too dark" signal rather than crashing on a
    missing frame (e.g. a camera timeout that produced no data).

    The 99th-percentile (not the mean) is used because it catches the
    saturated tail — a few saturated pixels in a bright region push p99
    to the sensor max even when the mean is moderate, giving the loop
    an early saturation-warning signal.
    """
    if frame is None:
        return 0.0
    arr = np.asarray(frame)
    if arr.size == 0:
        return 0.0
    p99 = float(np.percentile(arr, 99))
    if sensor_max <= 0:
        return 0.0
    return p99 / float(sensor_max)
