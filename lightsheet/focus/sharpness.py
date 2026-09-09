"""Image-sharpness metric for the focus feedback loop."""

from __future__ import annotations

import numpy as np


def frame_sharpness_variance(frame: np.ndarray | None) -> float:
    """Image-sharpness metric: normalized variance of the frame.

    Higher = sharper (more in-focus). Returns ``0.0`` for ``None``, empty
    arrays, or frames with zero standard deviation so the focus loop sees a
    "no signal" value rather than crashing on a missing frame.
    """
    if frame is None:
        return 0.0
    arr = np.asarray(frame, dtype=float)
    if arr.size == 0:
        return 0.0
    if arr.std() == 0:
        return 0.0
    return float(arr.var() / (arr.mean() + 1e-9))
