"""Pure-logic tests for the focus control law.

Mirrors the ``test_adaptive_controller.py`` style: direct import + call +
assert, no Qt, no HAL, no hardware.
"""

from __future__ import annotations

import pytest

from lightsheet.focus import (
    FocusConfig,
    FocusController,
    FocusCurve,
    FocusSample,
)


def _cfg(**overrides: object) -> FocusConfig:
    defaults: dict[str, object] = dict(
        enabled=True,
        block_size_n=8,
        autofocus_residual=True,
        curve_path="",
        residual_gain_mm=0.05,
        max_residual_mm=0.5,
    )
    defaults.update(overrides)
    return FocusConfig(**defaults)  # type: ignore[arg-type]


def test_focus_config_defaults() -> None:
    cfg = FocusConfig()
    assert cfg.enabled is False
    assert cfg.block_size_n == 8
    assert cfg.autofocus_residual is True
    assert cfg.curve_path == ""
    assert cfg.residual_gain_mm == pytest.approx(0.05)
    assert cfg.max_residual_mm == pytest.approx(0.5)


def test_focus_config_rejects_out_of_range_block_size() -> None:
    with pytest.raises(ValueError):
        FocusConfig(block_size_n=0)
    with pytest.raises(ValueError):
        FocusConfig(block_size_n=101)


def test_focus_config_rejects_negative_residual_bounds() -> None:
    with pytest.raises(ValueError):
        FocusConfig(residual_gain_mm=-0.1)
    with pytest.raises(ValueError):
        FocusConfig(max_residual_mm=-0.1)


def test_focus_curve_rejects_unequal_length() -> None:
    with pytest.raises(ValueError):
        FocusCurve(stage_pos=(1.0, 2.0), camera_pos=(1.0,))


def test_focus_curve_rejects_short() -> None:
    with pytest.raises(ValueError):
        FocusCurve(stage_pos=(1.0,), camera_pos=(1.0,))


def test_focus_curve_rejects_non_monotonic_stage_pos() -> None:
    with pytest.raises(ValueError):
        FocusCurve(stage_pos=(2.0, 1.0), camera_pos=(1.0, 2.0))


def test_focus_sample_is_frozen() -> None:
    sample = FocusSample(
        block_index=0,
        stage_pos_mm=1.0,
        feedforward_camera_pos_mm=2.0,
        residual_mm=0.0,
        applied_camera_pos_mm=2.0,
        sharpness_metric=None,
    )
    assert sample.sharpness_metric is None
    with pytest.raises(AttributeError):
        sample.residual_mm = 1.0  # type: ignore[misc]


def test_target_returns_feedforward_interpolation() -> None:
    curve = FocusCurve(
        stage_pos=(0.0, 10.0, 20.0), camera_pos=(20.0, 22.0, 25.0)
    )
    cfg = _cfg()
    ctrl = FocusController(
        cfg, curve, n_planes=20, cam_lo_mm=0.0, cam_hi_mm=35.0
    )
    assert ctrl.target(0, 0.0) == pytest.approx(20.0)
    assert ctrl.target(0, 10.0) == pytest.approx(22.0)
    assert ctrl.target(0, 20.0) == pytest.approx(25.0)
    assert ctrl.target(0, 5.0) == pytest.approx(21.0)


def test_target_clamps_to_camera_travel_limits() -> None:
    curve = FocusCurve(stage_pos=(0.0, 10.0), camera_pos=(5.0, 7.0))
    cfg = _cfg(max_residual_mm=100.0, residual_gain_mm=100.0)
    # A large positive residual pushes the feedforward target above the limit.
    ctrl_hi = FocusController(
        cfg, curve, n_planes=20, cam_lo_mm=0.0, cam_hi_mm=35.0
    )
    ctrl_hi.update_residual(1.0)
    ctrl_hi.update_residual(0.0)
    assert ctrl_hi.target(0, 0.0) == pytest.approx(35.0)
    # A large negative residual pushes the feedforward target below the limit.
    ctrl_lo = FocusController(
        cfg, curve, n_planes=20, cam_lo_mm=0.0, cam_hi_mm=35.0
    )
    ctrl_lo.update_residual(1.0)
    ctrl_lo.update_residual(2.0)
    assert ctrl_lo.target(0, 0.0) == pytest.approx(0.0)


def test_update_residual_clamps_to_max_residual_mm() -> None:
    curve = FocusCurve(stage_pos=(0.0, 10.0), camera_pos=(0.0, 0.0))
    cfg = _cfg(
        residual_gain_mm=10.0, max_residual_mm=0.5, autofocus_residual=True
    )
    ctrl = FocusController(
        cfg, curve, n_planes=20, cam_lo_mm=0.0, cam_hi_mm=35.0
    )
    # First call establishes the reference sharpness.
    ctrl.update_residual(1.0)
    assert ctrl.target(0, 0.0) == pytest.approx(0.0)
    # A large deviation is clamped to the configured maximum residual.
    ctrl.update_residual(0.0)
    assert ctrl.target(0, 0.0) == pytest.approx(0.5)
    # Repeated calls cannot grow beyond the maximum.
    ctrl.update_residual(0.0)
    assert ctrl.target(0, 0.0) == pytest.approx(0.5)


def test_disabled_controller_pins_residual_at_zero() -> None:
    curve = FocusCurve(stage_pos=(0.0, 10.0), camera_pos=(20.0, 22.0))
    cfg = _cfg(enabled=False, autofocus_residual=True)
    ctrl = FocusController(
        cfg, curve, n_planes=20, cam_lo_mm=0.0, cam_hi_mm=35.0
    )
    ctrl.update_residual(1.0)
    ctrl.update_residual(0.0)
    # When disabled, the residual is not added even if autofocus_residual is on.
    assert ctrl.target(0, 5.0) == pytest.approx(21.0)
