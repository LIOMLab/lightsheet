"""Branch-coverage tests for ``lightsheet/focus/adaptive_controller.py``.

Targets the branches left uncovered by ``test_adaptive_focus.py`` (the
update/clamp happy paths) and ``test_focus_resume.py`` (the
checkpoint/restore round-trip and rejections):

- ``has_reference`` / ``residual_unchanged`` properties.
- ``feedforward`` when ``use_curve_seed`` is set but no curve is supplied.
- The ``update`` deadband early return (relative error within
  ``update_threshold`` of the smoothed reference).
- The ``s <= 0`` arm of the proportional-scale ternary (a non-positive
  smoothed reference disables relative scaling).
- ``checkpoint`` with no reference / no command yet (``None`` arms).
- ``restore`` validation rejects: non-dict state, bool/non-finite
  residuals, non-numeric predicted sharpness, non-numeric and non-finite
  travel-bounded fields, and an explicit ``None`` seed (keeps the
  constructed seed).

Pure-Python — no Qt, no HAL, no hardware.
"""

from __future__ import annotations

import pytest

from lightsheet.focus.adaptive_controller import (
    AdaptiveFocusController,
    AutofocusConfig,
)


def _cfg(**overrides: object) -> AutofocusConfig:
    defaults: dict[str, object] = dict(
        enabled=True,
        cadence=1,
        residual_gain_mm=0.05,
        max_residual_mm=0.5,
        smoothing=0.5,
        update_threshold=0.0,
        use_curve_seed=False,
    )
    defaults.update(overrides)
    return AutofocusConfig(**defaults)  # ty: ignore[invalid-argument-type]


def _ctrl(cfg: AutofocusConfig | None = None) -> AdaptiveFocusController:
    return AdaptiveFocusController(
        cfg if cfg is not None else _cfg(),
        cam_lo_mm=0.0,
        cam_hi_mm=35.0,
        seed_camera_pos_mm=10.0,
    )


# --------------------------------------------------------------------- #
# Read-only properties
# --------------------------------------------------------------------- #


def test_has_reference_tracks_first_update() -> None:
    """``has_reference`` is False until the first update stores the
    reference sharpness."""
    ctrl = _ctrl()
    assert ctrl.has_reference is False
    ctrl.update(1.0, 100.0)
    assert ctrl.has_reference is True


def test_residual_unchanged_reports_no_step() -> None:
    """``residual_unchanged`` is True before any step and False once the
    residual moves."""
    ctrl = _ctrl()
    assert ctrl.residual_unchanged is True
    ctrl.update(1.0, 100.0)  # reference only — still no step
    assert ctrl.residual_unchanged is True
    ctrl.update(2.0, 200.0)  # takes a residual step
    assert ctrl.residual_unchanged is False


# --------------------------------------------------------------------- #
# feedforward: use_curve_seed without a curve
# --------------------------------------------------------------------- #


def test_feedforward_curve_seed_without_curve_uses_seed() -> None:
    """``use_curve_seed=True`` with ``curve=None`` falls back to the
    constant seed."""
    cfg = _cfg(use_curve_seed=True)
    ctrl = _ctrl(cfg)
    assert ctrl.feedforward(5.0) == pytest.approx(10.0)
    assert ctrl.target(5.0) == pytest.approx(10.0)


# --------------------------------------------------------------------- #
# update(): deadband and s <= 0 scale arm
# --------------------------------------------------------------------- #


def test_update_within_deadband_takes_no_step() -> None:
    """A relative error inside ``update_threshold`` leaves the residual
    untouched (deadband early return)."""
    cfg = _cfg(update_threshold=0.10)
    ctrl = _ctrl(cfg)
    ctrl.update(1.0, 100.0)  # reference
    ctrl.update(2.0, 105.0)  # |error|/s ≈ 0.048 < 0.10 → deadband
    assert ctrl.residual_mm == pytest.approx(0.0)
    assert ctrl.residual_unchanged is True


def test_update_outside_deadband_steps() -> None:
    """A relative error beyond ``update_threshold`` steps the residual by
    at most ``residual_gain_mm`` (proportional scale)."""
    cfg = _cfg(update_threshold=0.10)
    ctrl = _ctrl(cfg)
    ctrl.update(1.0, 100.0)
    ctrl.update(2.0, 200.0)  # |error|/s large → step
    assert ctrl.residual_mm != pytest.approx(0.0)
    assert abs(ctrl.residual_mm) <= cfg.residual_gain_mm


def test_update_nonpositive_reference_uses_unit_scale() -> None:
    """When the smoothed reference is <= 0 the proportional scale is 1.0
    (the ``s <= 0.0`` arm) and the deadband guard is skipped."""
    cfg = _cfg(update_threshold=0.10, smoothing=0.5)
    ctrl = _ctrl(cfg)
    ctrl.update(1.0, -100.0)  # reference sharpness negative
    ctrl.update(2.0, -50.0)  # s = 0.5*-100 + 0.5*-50 = -75 <= 0 → scale 1.0
    assert ctrl.residual_mm == pytest.approx(cfg.residual_gain_mm)


# --------------------------------------------------------------------- #
# checkpoint(): None arms
# --------------------------------------------------------------------- #


def test_checkpoint_before_any_update_emits_nulls() -> None:
    """A fresh controller checkpoints ``predicted_sharpness`` and
    ``last_command`` as None."""
    ctrl = _ctrl()
    state = ctrl.checkpoint()
    assert state["predicted_sharpness"] is None
    assert state["last_command"] is None
    assert state["residual_mm"] == pytest.approx(0.0)
    assert state["seed_camera_pos_mm"] == pytest.approx(10.0)


# --------------------------------------------------------------------- #
# restore() validation rejects not covered by the round-trip tests
# --------------------------------------------------------------------- #


def test_restore_rejects_non_dict_state() -> None:
    with pytest.raises(ValueError, match="must be a dict"):
        _ctrl().restore(["not", "a", "dict"])  # ty: ignore[invalid-argument-type]


def test_restore_rejects_bool_residual() -> None:
    """A bool is not a valid residual (bool is an int subclass — the
    explicit isinstance(raw, bool) guard rejects it)."""
    with pytest.raises(ValueError, match="residual_mm must be a number"):
        _ctrl().restore({"residual_mm": True})


def test_restore_rejects_nonfinite_residual() -> None:
    with pytest.raises(ValueError, match="residual_mm must be finite"):
        _ctrl().restore({"residual_mm": float("nan")})
    with pytest.raises(ValueError, match="prev_residual_mm must be finite"):
        _ctrl().restore({"prev_residual_mm": float("inf")})


def test_restore_rejects_nonnumeric_predicted_sharpness() -> None:
    with pytest.raises(ValueError, match="predicted_sharpness must be a number"):
        _ctrl().restore({"predicted_sharpness": "loud"})


def test_restore_rejects_nonnumeric_travel_fields() -> None:
    with pytest.raises(ValueError, match="seed_camera_pos_mm must be a number"):
        _ctrl().restore({"seed_camera_pos_mm": "ten"})
    with pytest.raises(ValueError, match="last_command must be a number"):
        _ctrl().restore({"last_command": [1.0]})


def test_restore_rejects_nonfinite_travel_fields() -> None:
    with pytest.raises(ValueError, match="seed_camera_pos_mm must be finite"):
        _ctrl().restore({"seed_camera_pos_mm": float("nan")})
    with pytest.raises(ValueError, match="last_command must be finite"):
        _ctrl().restore({"last_command": float("inf")})


def test_restore_none_seed_keeps_constructed_seed() -> None:
    """An explicit ``None`` seed in the checkpoint leaves the constructed
    seed in place (the ``raw is None`` early return)."""
    ctrl = _ctrl()
    ctrl.restore({"seed_camera_pos_mm": None})
    assert ctrl.target(0.0) == pytest.approx(10.0)


def test_restore_none_last_command_clears_command() -> None:
    """An explicit ``None`` last_command restores cleanly."""
    ctrl = _ctrl()
    ctrl.target(0.0)
    ctrl.restore({"last_command": None})
    assert ctrl.checkpoint()["last_command"] is None
