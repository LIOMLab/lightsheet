"""Pure-logic tests for the adaptive frame-intensity statistic.

Mirrors the ``test_gaussian.py`` / ``test_channel_map.py`` style: direct
import + call + assert, no Qt, no hardware, no static-source grep.

The intensity statistic is the per-plane feedback signal the adaptive
controller consumes. A very high percentile (default 99.99) is used
because it tracks sensor saturation risk better than the mean: a few
saturated pixels (bright brainstem) push the tail percentile to the
sensor max even when the mean is moderate.
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
    # Full-scale uint16 → 99.99th percentile is 65535 → fraction 1.0.
    frame = np.full((4, 4), 65535, dtype=np.uint16)
    assert frame_intensity_pct(frame) == pytest.approx(1.0)


def test_intensity_half_scale_returns_half() -> None:
    frame = np.full((4, 4), 32768, dtype=np.uint16)
    assert frame_intensity_pct(frame) == pytest.approx(32768.0 / 65535.0)


def test_intensity_uses_tail_percentile_not_mean() -> None:
    # A frame where 98% of pixels are dark and 2% are saturated: the
    # mean would under-report saturation risk; the tail percentile
    # catches the saturated tail. With 100 pixels, the 99.99th percentile
    # is the largest pixel (numpy's linear interpolation lands near the
    # top sample).
    frame = np.zeros(100, dtype=np.uint16)
    frame[-2:] = 65535  # last 2 pixels saturated
    pct = frame_intensity_pct(frame)
    assert pct > 0.9, (
        f"tail percentile must catch the saturated tail; got {pct} (mean "
        f"would be ~{2 * 65535 / 100 / 65535:.3f})"
    )


def test_intensity_custom_sensor_max() -> None:
    frame = np.full((4, 4), 200, dtype=np.uint16)
    assert frame_intensity_pct(frame, sensor_max=400) == pytest.approx(0.5)


def test_intensity_benchmark_under_50ms() -> None:
    """A 2048x2048 frame's 99.99th percentile must compute in under
    50 ms on the dev machine (the per-plane budget)."""
    rng = np.random.default_rng(42)
    frame = rng.integers(0, 65536, size=(2048, 2048), dtype=np.uint16)
    # Warm up to avoid first-call overhead skewing the measurement.
    frame_intensity_pct(frame)
    start = time.perf_counter()
    frame_intensity_pct(frame)
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    assert elapsed_ms < 50.0, (
        f"p99.99 on 2048x2048 took {elapsed_ms:.1f} ms (budget 50 ms)"
    )


def test_intensity_catches_small_saturated_feature() -> None:
    """A small bright feature that covers << 1% of a large frame must
    still be visible to the tail percentile used for adaptive control.

    Regression: the old 99th percentile missed small saturated brain
    pieces and measured the dark background, causing the controller to
    increase exposure and oversaturate.
    """
    size = 1024
    feature = 30
    background_value = 13107  # ~0.20 fraction of 65535
    frame = np.full((size, size), background_value, dtype=np.uint16)
    start = (size - feature) // 2
    frame[start : start + feature, start : start + feature] = 65535

    p99 = frame_intensity_pct(frame, percentile=99.0)
    p9999 = frame_intensity_pct(frame, percentile=99.99)

    assert p99 < 0.3, (
        f"p99 should measure the background for a {feature}x{feature} "
        f"feature in a {size}x{size} frame; got {p99:.3f}"
    )
    assert p9999 > 0.9, (
        f"p99.99 must catch the saturated {feature}x{feature} feature; got {p9999:.3f}"
    )
