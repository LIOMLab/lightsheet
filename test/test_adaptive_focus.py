"""Wave 0 RED stubs for the adaptive focus controller.

These tests pin the public API and expected behavior of ``AutofocusConfig``
and ``AdaptiveFocusController`` before the production implementation is
written. They are marked ``xfail`` so pytest stays green while the symbols do
not yet exist.

No Qt, no HAL, no hardware — pure logic and numpy only.
"""

from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=False, reason="Wave 0 stub")
def test_autofocus_config_defaults() -> None:
    from lightsheet.focus.adaptive_controller import AutofocusConfig

    cfg = AutofocusConfig()
    assert cfg.enabled is False
    assert cfg.cadence == 1
    assert cfg.residual_gain_mm == pytest.approx(0.05)
    assert cfg.max_residual_mm == pytest.approx(0.5)
    assert cfg.smoothing == pytest.approx(0.5)
    assert cfg.use_curve_seed is False


@pytest.mark.xfail(strict=False, reason="Wave 0 stub")
def test_autofocus_config_rejects_out_of_range() -> None:
    from lightsheet.focus.adaptive_controller import AutofocusConfig

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


@pytest.mark.xfail(strict=False, reason="Wave 0 stub")
def test_adaptive_controller_constant_seed_target() -> None:
    from lightsheet.focus.adaptive_controller import (
        AdaptiveFocusController,
        AutofocusConfig,
    )

    cfg = AutofocusConfig()
    ctrl = AdaptiveFocusController(
        cfg,
        cam_lo=0.0,
        cam_hi=35.0,
        seed_camera_pos_mm=20.0,
    )
    assert ctrl.target(5.0) == pytest.approx(20.0)
    assert ctrl.target(5.0) >= 0.0
    assert ctrl.target(5.0) <= 35.0


@pytest.mark.xfail(strict=False, reason="Wave 0 stub")
def test_adaptive_controller_curve_seed_target() -> None:
    from lightsheet.focus.adaptive_controller import (
        AdaptiveFocusController,
        AutofocusConfig,
    )

    from lightsheet.focus.types import FocusCurve

    cfg = AutofocusConfig(use_curve_seed=True)
    curve = FocusCurve(stage_pos=(0.0, 10.0), camera_pos=(20.0, 22.0))
    ctrl = AdaptiveFocusController(
        cfg,
        cam_lo=0.0,
        cam_hi=35.0,
        curve=curve,
        seed_camera_pos_mm=20.0,
    )
    # Linear interpolation at stage 5.0 is 21.0, clamped inside [0.0, 35.0].
    assert ctrl.target(5.0) == pytest.approx(21.0)
    assert ctrl.target(5.0) >= 0.0
    assert ctrl.target(5.0) <= 35.0


@pytest.mark.xfail(strict=False, reason="Wave 0 stub")
def test_adaptive_controller_update_clamps_residual() -> None:
    from lightsheet.focus.adaptive_controller import (
        AdaptiveFocusController,
        AutofocusConfig,
    )

    cfg = AutofocusConfig(
        enabled=True,
        residual_gain_mm=0.05,
        max_residual_mm=0.5,
        smoothing=0.5,
    )
    ctrl = AdaptiveFocusController(
        cfg,
        cam_lo=0.0,
        cam_hi=35.0,
        seed_camera_pos_mm=0.0,
    )
    # First call establishes the reference sharpness.
    ctrl.update(1.0)
    assert ctrl.residual_mm == pytest.approx(0.0)
    # Subsequent calls step the residual by residual_gain_mm and clamp.
    for _ in range(15):
        ctrl.update(0.0)
    assert abs(ctrl.residual_mm) <= cfg.max_residual_mm
    # Repeated calls cannot grow beyond the maximum residual.
    assert pytest.approx(abs(ctrl.residual_mm)) == cfg.max_residual_mm


@pytest.mark.xfail(strict=False, reason="Wave 0 stub")
def test_sign_based_update_reverses_on_lower_sharpness() -> None:
    from lightsheet.focus.adaptive_controller import (
        AdaptiveFocusController,
        AutofocusConfig,
    )

    cfg = AutofocusConfig(
        enabled=True,
        residual_gain_mm=0.05,
        max_residual_mm=0.5,
        smoothing=0.5,
    )
    ctrl = AdaptiveFocusController(
        cfg,
        cam_lo=0.0,
        cam_hi=35.0,
        seed_camera_pos_mm=0.0,
    )
    ctrl.update(1.0)
    ctrl.update(2.0)  # higher than reference -> move one way
    before = ctrl.residual_mm
    ctrl.update(0.0)  # lower than reference -> reverse
    assert ctrl.residual_mm != before or abs(ctrl.residual_mm) >= cfg.max_residual_mm


@pytest.mark.xfail(strict=False, reason="Wave 0 stub")
def test_cadence_holds_residual_between_planes() -> None:
    from lightsheet.focus.adaptive_controller import (
        AdaptiveFocusController,
        AutofocusConfig,
    )

    cfg = AutofocusConfig(enabled=True, cadence=2)
    ctrl = AdaptiveFocusController(
        cfg,
        cam_lo=0.0,
        cam_hi=35.0,
        seed_camera_pos_mm=0.0,
    )
    ctrl.update(1.0)
    ctrl.update(0.0)
    residual = ctrl.residual_mm
    # Calling target() without update() must not change the residual.
    _ = ctrl.target(1.0)
    _ = ctrl.target(2.0)
    assert ctrl.residual_mm == pytest.approx(residual)
