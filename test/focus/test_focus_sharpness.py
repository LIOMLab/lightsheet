"""Pure-logic tests for the focus sharpness metric.

Mirrors the ``test_adaptive_intensity.py`` style: direct import + call +
assert, no Qt, no hardware.
"""

from __future__ import annotations

import numpy as np

from lightsheet.focus import frame_sharpness_variance


def test_frame_sharpness_variance_none_returns_zero() -> None:
    assert frame_sharpness_variance(None) == 0.0


def test_frame_sharpness_variance_empty_array_returns_zero() -> None:
    assert frame_sharpness_variance(np.array([], dtype=np.float64)) == 0.0


def test_frame_sharpness_variance_zero_for_flat_frame() -> None:
    assert frame_sharpness_variance(np.zeros((4, 4), dtype=np.uint16)) == 0.0


def test_frame_sharpness_variance_checkerboard_returns_positive() -> None:
    frame = np.zeros((8, 8), dtype=np.uint16)
    frame[::2, ::2] = 65535
    frame[1::2, 1::2] = 65535
    value = frame_sharpness_variance(frame)
    assert value > 0.0
