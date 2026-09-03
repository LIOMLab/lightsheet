"""Pure-logic tests for the adaptive frame-intensity statistic.

Mirrors the ``test_gaussian.py`` / ``test_channel_map.py`` style: direct
import + call + assert, no Qt, no hardware, no static-source grep.

The intensity statistic is the per-plane feedback signal the adaptive
controller consumes. The 99th-percentile is chosen because it tracks
sensor saturation risk better than the mean: a few saturated pixels
(bright brainstem) push the 99th percentile to the sensor max even when
the mean is moderate.
"""

from __future__ import annotations

import time

import numpy as np
import pytest

from lightsheet.adaptive.intensity import frame_intensity_pct


def test_intensity_none_returns_zero() -> None:
    assert frame_intensity_pct(None) == 0.0


def test_intensity_empty_array_returns_zero() -> None:
    assert frame_intensity_pct(np.array([], dtype=np.uint16)) == 0.0


def test_intensity_black_frame_returns_zero() -> None:
    assert frame_intensity_pct(np.zeros((4, 4), dtype=np.uint16)) == 0.0


def test_intensity_full_scale_returns_one() -> None:
    # Full-scale uint16 → 99th percentile is 65535 → fraction 1.0.
    frame = np.full((4, 4), 65535, dtype=np.uint16)
    assert frame_intensity_pct(frame) == pytest.approx(1.0)


def test_intensity_half_scale_returns_half() -> None:
    frame = np.full((4, 4), 32768, dtype=np.uint16)
    assert frame_intensity_pct(frame) == pytest.approx(32768.0 / 65535.0)


def test_intensity_uses_p99_not_mean() -> None:
    # A frame where 99% of pixels are dark and 1% are saturated: the
    # mean would under-report saturation risk; the 99th percentile
    # catches the saturated tail. With 100 pixels, the 99th percentile
    # is the largest pixel (numpy's linear interpolation lands on the
    # top sample for p99 of n=100).
    frame = np.zeros(100, dtype=np.uint16)
    frame[-2:] = 65535  # last 2 pixels saturated
    pct = frame_intensity_pct(frame)
    assert pct > 0.9, (
        f"p99 must catch the saturated tail; got {pct} (mean would be "
        f"~{2 * 65535 / 100 / 65535:.3f})"
    )


def test_intensity_custom_sensor_max() -> None:
    frame = np.full((4, 4), 200, dtype=np.uint16)
    assert frame_intensity_pct(frame, sensor_max=400) == pytest.approx(0.5)


def test_intensity_benchmark_under_50ms() -> None:
    """A 2048x2048 frame's p99 must compute in under 50 ms on the dev
    machine (the per-plane budget)."""
    rng = np.random.default_rng(42)
    frame = rng.integers(0, 65536, size=(2048, 2048), dtype=np.uint16)
    # Warm up to avoid first-call overhead skewing the measurement.
    frame_intensity_pct(frame)
    start = time.perf_counter()
    frame_intensity_pct(frame)
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    assert elapsed_ms < 50.0, (
        f"p99 on 2048x2048 took {elapsed_ms:.1f} ms (budget 50 ms)"
    )
