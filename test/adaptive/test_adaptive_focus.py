"""Unit tests for the per-plane adaptive focus controller.

Pure logic and numpy — no Qt, no HAL, no hardware.
"""

from __future__ import annotations

from typing import Any

import pytest

from lightsheet.focus.adaptive_controller import (
    AdaptiveFocusController,
    AutofocusConfig,
)
from lightsheet.focus.types import FocusCurve


def _cfg(**overrides: Any) -> AutofocusConfig:
    defaults: dict[str, Any] = dict(
        enabled=True,
        cadence=1,
        residual_gain_mm=0.05,
        max_residual_mm=0.5,
        smoothing=0.5,
        use_curve_seed=False,
    )
    defaults.update(overrides)
    return AutofocusConfig(**defaults)


def test_autofocus_config_defaults() -> None:
    cfg = AutofocusConfig()
    assert cfg.enabled is False
    assert cfg.cadence == 1
    assert cfg.residual_gain_mm == pytest.approx(0.05)
    assert cfg.max_residual_mm == pytest.approx(0.5)
    assert cfg.smoothing == pytest.approx(0.5)
    assert cfg.update_threshold == pytest.approx(0.0)
    assert cfg.use_curve_seed is False


def test_autofocus_config_rejects_out_of_range() -> None:
    with pytest.raises(ValueError):
        AutofocusConfig(cadence=0)
    with pytest.raises(ValueError):
        AutofocusConfig(cadence=1001)
    with pytest.raises(ValueError):
        AutofocusConfig(residual_gain_mm=-0.01)
    with pytest.raises(ValueError):
        AutofocusConfig(residual_gain_mm=1.01)
    with pytest.raises(ValueError):
        AutofocusConfig(max_residual_mm=-0.01)
    with pytest.raises(ValueError):
        AutofocusConfig(max_residual_mm=5.01)
    with pytest.raises(ValueError):
        AutofocusConfig(smoothing=-0.01)
    with pytest.raises(ValueError):
        AutofocusConfig(smoothing=1.01)


def test_adaptive_controller_constant_seed_target() -> None:
    cfg = AutofocusConfig()
    ctrl = AdaptiveFocusController(
        cfg,
        cam_lo_mm=0.0,
        cam_hi_mm=35.0,
        seed_camera_pos_mm=20.0,
    )
    assert ctrl.target(5.0) == pytest.approx(20.0)
    assert ctrl.target(5.0) >= 0.0
    assert ctrl.target(5.0) <= 35.0


def test_adaptive_controller_curve_seed_target() -> None:
    cfg = AutofocusConfig(use_curve_seed=True)
    curve = FocusCurve(stage_pos=(0.0, 10.0), camera_pos=(20.0, 22.0))
    ctrl = AdaptiveFocusController(
        cfg,
        cam_lo_mm=0.0,
        cam_hi_mm=35.0,
        curve=curve,
        seed_camera_pos_mm=20.0,
    )
    # Linear interpolation at stage 5.0 is 21.0, clamped inside [0.0, 35.0].
    assert ctrl.target(5.0) == pytest.approx(21.0)
    assert ctrl.target(5.0) >= 0.0
    assert ctrl.target(5.0) <= 35.0


def test_adaptive_controller_update_clamps_residual() -> None:
    cfg = _cfg(
        enabled=True,
        residual_gain_mm=0.05,
        max_residual_mm=0.5,
        smoothing=0.5,
    )
    ctrl = AdaptiveFocusController(
        cfg,
        cam_lo_mm=0.0,
        cam_hi_mm=35.0,
        seed_camera_pos_mm=0.0,
    )
    # First call establishes the reference sharpness.
    ctrl.update(1.0, 1.0)
    assert ctrl.residual_mm == pytest.approx(0.0)
    # Repeated higher sharpness steps the residual by residual_gain_mm and clamps.
    for _ in range(15):
        ctrl.update(1.0, 2.0)
    assert abs(ctrl.residual_mm) <= cfg.max_residual_mm
    # Repeated calls cannot grow beyond the maximum residual.
    assert pytest.approx(abs(ctrl.residual_mm)) == cfg.max_residual_mm


def test_sign_based_update_reverses_on_lower_sharpness() -> None:
    cfg = _cfg(
        enabled=True,
        residual_gain_mm=0.05,
        max_residual_mm=0.5,
        smoothing=0.5,
    )
    ctrl = AdaptiveFocusController(
        cfg,
        cam_lo_mm=0.0,
        cam_hi_mm=35.0,
        seed_camera_pos_mm=0.0,
    )
    ctrl.update(1.0, 1.0)
    ctrl.update(2.0, 2.0)  # higher than reference -> move one way
    before = ctrl.residual_mm
    ctrl.update(3.0, 0.0)  # lower than reference -> reverse
    assert ctrl.residual_mm != before or abs(ctrl.residual_mm) >= cfg.max_residual_mm


def test_cadence_holds_residual_between_planes() -> None:
    cfg = _cfg(enabled=True, cadence=2)
    ctrl = AdaptiveFocusController(
        cfg,
        cam_lo_mm=0.0,
        cam_hi_mm=35.0,
        seed_camera_pos_mm=0.0,
    )
    ctrl.update(1.0, 1.0)
    ctrl.update(2.0, 2.0)
    residual = ctrl.residual_mm
    # Calling target() without update() must not change the residual.
    _ = ctrl.target(1.0)
    _ = ctrl.target(2.0)
    assert ctrl.residual_mm == pytest.approx(residual)


def test_target_clamps_feedforward_plus_residual() -> None:
    # A +1 mm residual pushes the 34 mm seed exactly to the 35 mm high limit.
    cfg = _cfg(residual_gain_mm=1.0, max_residual_mm=1.0)
    ctrl = AdaptiveFocusController(
        cfg,
        cam_lo_mm=0.0,
        cam_hi_mm=35.0,
        seed_camera_pos_mm=34.0,
    )
    ctrl.update(1.0, 1.0)  # establish reference
    ctrl.update(2.0, 2.0)  # one +1 mm step
    assert ctrl.residual_mm == pytest.approx(1.0)
    assert ctrl.target(5.0) == pytest.approx(35.0)


def test_target_uses_curve_endpoints_outside_range() -> None:
    curve = FocusCurve(stage_pos=(0.0, 10.0), camera_pos=(20.0, 22.0))
    cfg = _cfg(use_curve_seed=True)
    ctrl = AdaptiveFocusController(
        cfg,
        cam_lo_mm=0.0,
        cam_hi_mm=35.0,
        curve=curve,
        seed_camera_pos_mm=100.0,
    )
    # np.interp returns the left endpoint below the curve and the right above.
    assert ctrl.target(-5.0) == pytest.approx(20.0)
    assert ctrl.target(15.0) == pytest.approx(22.0)


def test_update_first_call_leaves_residual_zero() -> None:
    cfg = _cfg()
    ctrl = AdaptiveFocusController(
        cfg,
        cam_lo_mm=0.0,
        cam_hi_mm=35.0,
        seed_camera_pos_mm=10.0,
    )
    ctrl.update(1.0, 1.0)
    assert ctrl.residual_mm == pytest.approx(0.0)


def test_zero_residual_gain_keeps_residual_zero() -> None:
    cfg = _cfg(residual_gain_mm=0.0)
    ctrl = AdaptiveFocusController(
        cfg,
        cam_lo_mm=0.0,
        cam_hi_mm=35.0,
        seed_camera_pos_mm=0.0,
    )
    ctrl.update(1.0, 1.0)
    for _ in range(10):
        ctrl.update(1.0, 2.0)
    assert ctrl.residual_mm == pytest.approx(0.0)


def test_disabled_controller_does_not_update_residual() -> None:
    cfg = _cfg(enabled=False)
    ctrl = AdaptiveFocusController(
        cfg,
        cam_lo_mm=0.0,
        cam_hi_mm=35.0,
        seed_camera_pos_mm=0.0,
    )
    ctrl.update(1.0, 1.0)
    ctrl.update(2.0, 2.0)
    assert ctrl.residual_mm == pytest.approx(0.0)
    # The constant seed is still clamped and returned.
    assert ctrl.target(1.0) == pytest.approx(0.0)


def test_residual_mm_is_read_only() -> None:
    cfg = _cfg()
    ctrl = AdaptiveFocusController(
        cfg,
        cam_lo_mm=0.0,
        cam_hi_mm=35.0,
        seed_camera_pos_mm=0.0,
    )
    with pytest.raises(AttributeError):
        ctrl.residual_mm = 1.0  # ty: ignore[invalid-assignment]
