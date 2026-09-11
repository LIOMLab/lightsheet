"""Branch-coverage tests for ``lightsheet/adaptive/types.py``.

Covers the ``AdaptiveConfig.__post_init__`` validator raise branches —
each out-of-range or ill-ordered bound must fail loudly at construction
with ``ValueError``, not silently mid-acquisition. Also covers the
``AdaptiveSample`` None→NaN normalization and ``as_dict`` serialization,
and ``AdaptiveCommand.fixed`` passthrough defaults.

Pure-Python — no Qt, no HAL, no hardware.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from lightsheet.adaptive.types import (
    AdaptiveCommand,
    AdaptiveConfig,
    AdaptiveSample,
)


@pytest.mark.parametrize(
    "overrides",
    [
        {"min_exposure_s": 0.3, "max_exposure_s": 0.1},  # min > max exposure
        {"min_power_mw": (200.0, 0.0), "max_power_mw": (100.0, 100.0)},
        # min_power_mw[1] > max_power_mw[1] (the [0] pair is above).
        {"min_power_mw": (0.0, 200.0), "max_power_mw": (100.0, 100.0)},
        {"block_size_n": 0},
        {"target_band_lo": 0.99, "target_band_hi": 0.5},
        {"min_power_mw": (0.0, 200.0), "max_power_mw": (100.0, 100.0)},
        {"pilot_count": 0},
        {"intensity_percentile": 0.0},
        {"intensity_percentile": 100.1},
        {"saturation_threshold": 0.0},
        {"saturation_threshold": 1.5},
        {"saturation_drop_factor": 0.0},
        {"dead_band": -0.1},
        {"dead_band": 1.0},
        {"max_step_fraction": 0.0},
        {"saturation_percentile": 0.0},
        {"saturation_percentile": 101.0},
    ],
)
def test_adaptive_config_invalid_bounds_rejected(overrides: dict[str, Any]) -> None:
    """Each out-of-range bound raises ValueError at construction."""
    with pytest.raises(ValueError):
        AdaptiveConfig(**overrides)


def test_adaptive_sample_none_intensity_normalized_to_nan() -> None:
    """A None intensity entry (inactive channel) normalizes to NaN so the
    saved trajectory carries the convention regardless of caller input."""
    sample = AdaptiveSample(
        plane_index=3,
        intensity_fraction=[0.5, None],  # ty: ignore[invalid-argument-type]
        exposure_s=0.01,
        laser_power_mw=(10.0, 20.0),
        control_variable_active="exposure",
        reacquired=False,
        power_fallback=False,
    )
    assert sample.intensity_fraction[0] == 0.5
    assert math.isnan(sample.intensity_fraction[1])


def test_adaptive_sample_as_dict_json_safe() -> None:
    """as_dict returns plain JSON-safe types for manifest storage."""
    sample = AdaptiveSample(
        plane_index=0,
        intensity_fraction=[0.9],
        exposure_s=0.05,
        laser_power_mw=(5.0, 0.0),
        control_variable_active="fixed",
        reacquired=True,
        power_fallback=False,
    )
    d = sample.as_dict()
    assert d == {
        "plane_index": 0,
        "intensity_fraction": [0.9],
        "exposure_s": 0.05,
        "laser_power_mw": [5.0, 0.0],
        "control_variable_active": "fixed",
        "reacquired": True,
        "power_fallback": False,
    }


def test_adaptive_command_fixed_passthrough() -> None:
    """The fixed() constructor passes exposure/powers through with every
    decision flag False (adaptive off)."""
    cmd = AdaptiveCommand.fixed(exposure_s=0.02, laser1_mw=3.0, laser2_mw=4.0)
    assert cmd.exposure_s == 0.02
    assert cmd.laser1_mw == 3.0
    assert cmd.laser2_mw == 4.0
    assert cmd.reacquire is False
    assert cmd.control_variable_active == "fixed"
    assert cmd.power_fallback is False
    assert cmd.reacquire_exhausted is False
