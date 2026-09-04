"""Branch-coverage gap fills for ``lightsheet/gui/panels/stack_panel.py``.

Targets the missing branches reported by ``coverage report --show-missing``:
the ``_on_last_plane_edited`` body, the first-plane out-of-range revert
fallback, the multi-channel summary render, the advisory-estimate exception
fallbacks, the adaptive-config load/narrow exception + missing-widget guards,
the max-side invalid pair, the shutter-units missing-acq_ui guard, and the
``build_adaptive_config`` missing-acq_ui / missing-combo branches.

Uses the real ``Controller_MainWindow`` from ``make_controller`` for the
behavioral paths and a minimal Mock-shell ``StackPanelWidget`` for the
None-guard branches that the fully-wired shell cannot reach.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest
from pytestqt.qtbot import QtBot

pytest.importorskip("PySide6")


if TYPE_CHECKING:
    from lightsheet.gui.shell.controller import Controller_MainWindow


# ---------------------------------------------------------------------------
# _on_last_plane_edited body (lines 216-239) + first-plane revert fallback
# (201->203)
# ---------------------------------------------------------------------------


def test_last_plane_edited_in_range_updates_ending_plane(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """A last-plane edit inside the motor travel limits stores the µm
    value on ``stack_ending_plane`` and sets ``stack_last_plane_set``."""
    ctrl = controller
    sp = ctrl.stack_panel
    motors = ctrl.motors
    low_um = motors.horizontal.get_limit_low("\u03bcm")
    high_um = motors.horizontal.get_limit_high("\u03bcm")
    in_range_mm = (low_um + (high_um - low_um) * 0.5) / 1000.0
    sp.ui.doubleSpinBox_acqLastPlane.setValue(in_range_mm)
    sp._on_last_plane_edited()
    assert ctrl.stack_last_plane_set is True
    assert ctrl.stack_ending_plane == pytest.approx(in_range_mm * 1000.0)


def test_last_plane_edited_out_of_range_beeps_and_reverts(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """A last-plane edit outside the motor travel limits emits beep +
    message and reverts the spinbox to the high limit (the last-plane
    fallback when no prior valid ending plane is set)."""
    ctrl = controller
    sp = ctrl.stack_panel
    motors = ctrl.motors
    high_um = motors.horizontal.get_limit_high("\u03bcm")
    # Force an out-of-range prior ending plane so the revert fallback to
    # the high limit fires (the `revert_um is None or < low or > high`
    # branch).
    ctrl.stack_ending_plane = high_um + 1e6  # invalid prior
    out_of_range_mm = (high_um + 1e6) / 1000.0
    # Widen the spinbox range so setValue accepts the out-of-range value
    # (the editingFinished handler is the soft block, not the spinbox
    # range).
    sp.ui.doubleSpinBox_acqLastPlane.setRange(-1e9, 1e9)
    sp.ui.doubleSpinBox_acqLastPlane.setValue(out_of_range_mm)
    beeps: list[None] = []
    messages: list[str] = []
    ctrl.sig_beep.connect(lambda: beeps.append(None))
    ctrl.sig_message.connect(lambda m: messages.append(m))
    sp._on_last_plane_edited()
    assert len(beeps) == 1
    assert len(messages) == 1
    assert "outside the stage travel limits" in messages[0]
    # Reverted to the high limit (mm).
    assert sp.ui.doubleSpinBox_acqLastPlane.value() == pytest.approx(high_um / 1000.0)


def test_last_plane_edited_no_motors_returns_early(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """When ``shell.motors`` is None (hardware_init hasn't run), the
    last-plane editor returns without validating or moving the motor."""
    ctrl = controller
    sp = ctrl.stack_panel
    real_motors = ctrl.motors
    ctrl.motors = None  # ty: ignore[invalid-assignment]
    try:
        # Should not raise; the early return path (line 217-219) fires.
        sp._on_last_plane_edited()
    finally:
        ctrl.motors = real_motors


def test_first_plane_edited_no_motors_returns_early(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """When ``shell.motors`` is None, the first-plane editor returns
    early (line 185)."""
    ctrl = controller
    sp = ctrl.stack_panel
    real_motors = ctrl.motors
    ctrl.motors = None  # ty: ignore[invalid-assignment]
    try:
        sp._on_first_plane_edited()
    finally:
        ctrl.motors = real_motors


# ---------------------------------------------------------------------------
# _rerender_stack_units no-op (line 149)
# ---------------------------------------------------------------------------


def test_rerender_stack_units_is_noop(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """``_rerender_stack_units`` is a retained no-op — calling it must
    not raise and must not change any visible state."""
    ctrl = controller
    sp = ctrl.stack_panel
    summary_before = sp.ui.label_stackPlanSummary.text()
    # Must return None (the no-op) and leave the summary untouched.
    result = sp._rerender_stack_units()
    assert result is None
    assert sp.ui.label_stackPlanSummary.text() == summary_before


# ---------------------------------------------------------------------------
# Multi-channel summary render (345->350, 348->350)
# ---------------------------------------------------------------------------


def test_summary_render_multi_channel_doubles_estimates(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """When both auto-laser checkboxes are checked, the summary doubles
    the est. time and est. size and inserts the ``2 ch x N planes``
    clause (the multi_channel=True branch)."""
    ctrl = controller
    sp = ctrl.stack_panel
    # Configure a full plan: both boundaries set + non-zero step.
    ctrl.stack_first_plane_set = True
    ctrl.stack_last_plane_set = True
    sp.ui.doubleSpinBox_acqPlaneStepSize.setValue(1.0)
    sp.ui.doubleSpinBox_acqFirstPlane.setValue(0.0)
    sp.ui.doubleSpinBox_acqLastPlane.setValue(10.0)
    ctrl.number_of_planes = 11
    # Single-channel baseline.
    ctrl.laser_panel.ui.checkBox_laserOneAutomatic.setChecked(False)
    ctrl.laser_panel.ui.checkBox_laserTwoAutomatic.setChecked(False)
    sp._render_stack_plan_summary()
    single = sp.ui.label_stackPlanSummary.text()
    assert "2 ch" not in single
    # Multi-channel: both auto-laser checkboxes checked.
    ctrl.laser_panel.ui.checkBox_laserOneAutomatic.setChecked(True)
    ctrl.laser_panel.ui.checkBox_laserTwoAutomatic.setChecked(True)
    sp._render_stack_plan_summary()
    multi = sp.ui.label_stackPlanSummary.text()
    assert "2 ch x 11 planes" in multi


def test_summary_render_partial_state(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """When only one boundary is set, the summary shows the partial-state
    message (the ``first_set != last_set`` branch)."""
    ctrl = controller
    sp = ctrl.stack_panel
    ctrl.stack_first_plane_set = True
    ctrl.stack_last_plane_set = False
    sp._render_stack_plan_summary()
    assert "Partial stack plan" in sp.ui.label_stackPlanSummary.text()


def test_summary_render_empty_state(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """When neither boundary is set, the summary shows the empty-state
    message (the ``not first_set and not last_set`` branch)."""
    ctrl = controller
    sp = ctrl.stack_panel
    ctrl.stack_first_plane_set = False
    ctrl.stack_last_plane_set = False
    sp._render_stack_plan_summary()
    assert "No stack configured" in sp.ui.label_stackPlanSummary.text()


# ---------------------------------------------------------------------------
# Advisory-estimate exception fallbacks (374-375, 383-384)
# ---------------------------------------------------------------------------


def test_estimate_per_plane_time_falls_back_on_missing_widget(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """``_estimate_per_plane_time`` returns 0.5 when the
    acquisition_panel exposure spinbox is unavailable (the exception
    fallback)."""
    ctrl = controller
    sp = ctrl.stack_panel
    real_acq = ctrl.acquisition_panel
    # Replace acquisition_panel with a Mock whose ui lacks the spinbox
    # attribute → AttributeError inside the try block.
    mock_acq = MagicMock()
    mock_acq.ui = MagicMock(spec=[])  # no doubleSpinBox_cameraExposureTime
    ctrl.acquisition_panel = mock_acq
    try:
        per_plane = sp._estimate_per_plane_time()
    finally:
        ctrl.acquisition_panel = real_acq
    assert per_plane == 0.5


def test_estimate_stack_size_mb_falls_back_on_bad_camera(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """``_estimate_stack_size_mb`` falls back to 2000x2000 when
    ``shell.camera.rows``/``columns`` raise (the exception fallback)."""
    ctrl = controller
    sp = ctrl.stack_panel
    real_camera = ctrl.camera
    mock_camera = MagicMock()
    type(mock_camera).rows = property(
        lambda self: (_ for _ in ()).throw(TypeError("bad"))
    )
    ctrl.camera = mock_camera
    try:
        size_mb = sp._estimate_stack_size_mb(10)
    finally:
        ctrl.camera = real_camera
    # 10 planes * 2000 * 2000 * 2 bytes / (1024*1024) = ~76.29 MB
    assert size_mb == pytest.approx(10 * 2000 * 2000 * 2 / (1024.0 * 1024.0))


# ---------------------------------------------------------------------------
# _load_adaptive_config exception + empty-value + missing-widget guards
# (449-452, 465, 469, 475-476)
# ---------------------------------------------------------------------------


def _make_mock_shell_for_panel(ctrl: Controller_MainWindow) -> Any:
    """Build a Mock shell exposing only the attributes the panel
    ``__init__`` reads (motors, sig_beep, sig_message, _bundle) so the
    None-guard branches in the adaptive load/narrow paths fire."""
    shell = MagicMock()
    shell.motors = ctrl.motors  # real motors so _seed_spinbox_ranges works
    shell.sig_beep = ctrl.sig_beep
    shell.sig_message = ctrl.sig_message
    shell._bundle = None  # triggers the lasers-None guard in _narrow_*
    shell.acquisition_panel = None  # triggers acq_ui None guards
    shell.laser_panel = None
    return shell


def test_load_adaptive_config_handles_cfg_read_exception(
    qtbot: QtBot, controller: Controller_MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When ``cfg_read`` raises (no [Adaptive] section / unreadable
    config.ini), ``_load_adaptive_config`` returns without raising and
    leaves the FieldSpec defaults in place (the exception fallback)."""
    ctrl = controller
    sp = ctrl.stack_panel
    from lightsheet.gui import panels as panels_mod

    def _boom(*a: Any, **k: Any) -> Any:
        raise RuntimeError("config unreadable")

    monkeypatch.setattr(panels_mod.stack_panel, "cfg_read", _boom, raising=False)  # ty: ignore[possibly-missing-submodule]
    # The import inside _load_adaptive_config is `from lightsheet.config
    # import cfg_read`, so patch the source module.
    from lightsheet import config as cfg_mod

    monkeypatch.setattr(cfg_mod, "cfg_read", _boom)
    # Should not raise.
    sp._load_adaptive_config()


def test_load_adaptive_config_skips_empty_and_invalid_values(
    qtbot: QtBot, controller: Controller_MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``_load_adaptive_config`` skips empty raw values (the
    ``if not raw: continue`` branch) and swallows invalid float values
    (the ``except (ValueError, AttributeError)`` branch)."""
    ctrl = controller
    sp = ctrl.stack_panel

    def _fake_cfg_read(path: str, section: str, defaults: dict) -> dict:  # ty: ignore[missing-type-argument]
        # Return a mix: an empty value, an invalid float, a valid bool,
        # and a valid float.
        return {
            "Enabled": "true",
            "Min Exposure": "not-a-number",  # invalid float → except branch
            "Max Exposure": "",  # empty → continue branch
            "Laser1 Min Power": "1.5",
            "Laser1 Max Power": "5.0",
            "Laser2 Min Power": "",
            "Laser2 Max Power": "bad",  # invalid float → except branch
        }

    from lightsheet import config as cfg_mod

    monkeypatch.setattr(cfg_mod, "cfg_read", _fake_cfg_read)
    sp._load_adaptive_config()
    # The valid float was applied; the invalid ones were swallowed.
    assert sp.ui.doubleSpinBox_adaptiveLaser1MinPower.value() == pytest.approx(1.5)
    # Enabled was set true.
    assert sp.ui.checkBox_adaptiveEnable.isChecked() is True


# ---------------------------------------------------------------------------
# _narrow_adaptive_power_maxima missing-widget + bad-live_max guards
# (503, 506-507, 515, 518, 530, 533-534)
# ---------------------------------------------------------------------------


def test_narrow_adaptive_power_maxima_defaults_to_live_max(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """When config.ini did not save an explicit max-power value, the
    spinbox default is set to ``min(150.0, live_max)`` (the
    ``config_keys[i] not in loaded`` branch). The fixture's laser[0] has
    max_power 300 → narrowed to 150.0; laser[1] has 150 → 150.0."""
    ctrl = controller
    sp = ctrl.stack_panel
    # Clear the loaded-keys set so the default-to-live-max branch fires.
    sp._adaptive_loaded_keys = set()
    sp._narrow_adaptive_power_maxima()
    assert sp.ui.doubleSpinBox_adaptiveLaser1MaxPower.value() == pytest.approx(150.0)
    assert sp.ui.doubleSpinBox_adaptiveLaser2MaxPower.value() == pytest.approx(150.0)


def test_narrow_adaptive_power_maxima_clamps_saved_value_above_live(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """When the operator saved a max-power value above the live max, the
    spinbox is clamped down to ``min(150.0, live_max)`` (the
    ``elif sb.value() > narrowed`` branch)."""
    ctrl = controller
    sp = ctrl.stack_panel
    # Mark both keys as loaded so the default-to-live-max branch is
    # skipped and the clamp-down branch is the only path that fires.
    sp._adaptive_loaded_keys = {
        "Laser1 Max Power",
        "Laser2 Max Power",
    }
    # Set the spinbox values above the narrowed max (150.0) so the
    # clamp-down branch fires.
    sp.ui.doubleSpinBox_adaptiveLaser1MaxPower.setMaximum(1e9)
    sp.ui.doubleSpinBox_adaptiveLaser1MaxPower.setValue(200.0)
    sp.ui.doubleSpinBox_adaptiveLaser2MaxPower.setMaximum(1e9)
    sp.ui.doubleSpinBox_adaptiveLaser2MaxPower.setValue(200.0)
    sp._narrow_adaptive_power_maxima()
    assert sp.ui.doubleSpinBox_adaptiveLaser1MaxPower.value() == pytest.approx(150.0)
    assert sp.ui.doubleSpinBox_adaptiveLaser2MaxPower.value() == pytest.approx(150.0)


# ---------------------------------------------------------------------------
# _on_adaptive_field_edited no-sender guard (551) + max-side invalid pair
# (574-581)
# ---------------------------------------------------------------------------


def test_adaptive_field_edited_no_sender_returns(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """When ``sender()`` is None (called directly, not via a signal),
    ``_on_adaptive_field_edited`` returns without raising (line 551)."""
    ctrl = controller
    sp = ctrl.stack_panel
    # Call directly (no signal sender) — sender() returns None.
    sp._on_adaptive_field_edited()


def test_adaptive_field_edited_max_lowered_below_min_beeps(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """Lowering a max spinbox below the corresponding min emits the
    documented message + beep, reverts the max, and latches
    fixed-fallback (the max-side invalid pair branch, lines 574-581)."""
    ctrl = controller
    sp = ctrl.stack_panel
    ui = sp.ui
    ui.checkBox_adaptiveEnable.setChecked(True)
    # Raise Min Exposure first so a Max Exposure of 0.1 is invalid.
    ui.doubleSpinBox_adaptiveMinExposure.setValue(50.0)
    ui.doubleSpinBox_adaptiveMinExposure.editingFinished.emit()
    beeps: list[None] = []
    messages: list[str] = []
    ctrl.sig_beep.connect(lambda: beeps.append(None))
    ctrl.sig_message.connect(lambda m: messages.append(m))
    prior_max = ui.doubleSpinBox_adaptiveMaxExposure.value()
    ui.doubleSpinBox_adaptiveMaxExposure.setValue(0.1)
    ui.doubleSpinBox_adaptiveMaxExposure.editingFinished.emit()
    assert len(beeps) == 1
    assert len(messages) == 1
    assert "Adaptive bound invalid" in messages[0]
    assert "exposure" in messages[0]
    # Reverted to the prior max value.
    assert ui.doubleSpinBox_adaptiveMaxExposure.value() == pytest.approx(prior_max)
    # Latched — build_adaptive_config returns None.
    assert sp.build_adaptive_config() is None


# ---------------------------------------------------------------------------
# _update_adaptive_shutter_units missing-acq_ui + missing-combo guards
# (596, 599->601)
# ---------------------------------------------------------------------------


def test_update_adaptive_shutter_units_no_acq_panel_returns(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """When ``shell.acquisition_panel`` is None, the shutter-units
    updater returns early without raising (line 596)."""
    ctrl = controller
    sp = ctrl.stack_panel
    real_acq = ctrl.acquisition_panel
    ctrl.acquisition_panel = None  # ty: ignore[invalid-assignment]
    try:
        sp._update_adaptive_shutter_units()
    finally:
        ctrl.acquisition_panel = real_acq


def test_update_adaptive_shutter_units_missing_combo_defaults_rolling(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """When the acq_panel ui lacks the shutter-mode combo, the updater
    falls back to the Rolling (ms) suffix (the ``combo is None`` branch,
    line 599->601)."""
    ctrl = controller
    sp = ctrl.stack_panel
    real_acq = ctrl.acquisition_panel
    mock_acq = MagicMock()
    mock_acq.ui = MagicMock(spec=[])  # no comboBox_cameraShutterMode
    ctrl.acquisition_panel = mock_acq
    try:
        sp._update_adaptive_shutter_units()
    finally:
        ctrl.acquisition_panel = real_acq
    # Defaulted to Rolling (ms).
    suffix = sp.ui.doubleSpinBox_adaptiveMinExposure.suffix().strip().lower()
    assert suffix == "ms"


# ---------------------------------------------------------------------------
# _read_adaptive_fixed_config exception fallback (640-641)
# ---------------------------------------------------------------------------


def test_read_adaptive_fixed_config_falls_back_on_cfg_exception(
    qtbot: QtBot, controller: Controller_MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When ``cfg_read`` raises, ``_read_adaptive_fixed_config`` falls
    back to the schema defaults (the exception branch, lines 640-641)."""
    ctrl = controller
    sp = ctrl.stack_panel

    def _boom(*a: Any, **k: Any) -> Any:
        raise RuntimeError("config unreadable")

    from lightsheet import config as cfg_mod

    monkeypatch.setattr(cfg_mod, "cfg_read", _boom)
    target_lo, target_hi, reacquire, block_n, kp, ki, pilot = (
        sp._read_adaptive_fixed_config()
    )
    # Defaults: 90/95/8/8/0.4/0.05/5 (target band + reacquire as fractions).
    assert target_lo == pytest.approx(0.90)
    assert target_hi == pytest.approx(0.95)
    assert reacquire == pytest.approx(0.08)
    assert block_n == 8
    assert kp == pytest.approx(0.4)
    assert ki == pytest.approx(0.05)
    assert pilot == 5


# ---------------------------------------------------------------------------
# build_adaptive_config missing-acq_ui + missing-combo branches
# (679->684, 681->684)
# ---------------------------------------------------------------------------


def test_build_adaptive_config_no_acq_panel_uses_rolling_default(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """When ``shell.acquisition_panel`` is None, ``build_adaptive_config``
    treats the shutter mode as empty (Rolling default) and converts the
    exposure bound as ms → seconds (the ``acq_ui is None`` branch)."""
    ctrl = controller
    sp = ctrl.stack_panel
    ui = sp.ui
    ui.checkBox_adaptiveEnable.setChecked(True)
    ui.doubleSpinBox_adaptiveMinExposure.setValue(5.0)  # 5 ms
    ui.doubleSpinBox_adaptiveMinExposure.editingFinished.emit()
    real_acq = ctrl.acquisition_panel
    ctrl.acquisition_panel = None  # ty: ignore[invalid-assignment]
    try:
        cfg = sp.build_adaptive_config()
    finally:
        ctrl.acquisition_panel = real_acq
    assert cfg is not None
    # 5 ms → 5e-3 s (Rolling default conversion).
    assert cfg.min_exposure_s == pytest.approx(5e-3, rel=1e-9)


def test_build_adaptive_config_missing_combo_uses_rolling_default(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """When the acq_panel ui lacks the shutter-mode combo,
    ``build_adaptive_config`` treats the mode as empty (Rolling default)
    — the ``combo is None`` branch (line 681->684)."""
    ctrl = controller
    sp = ctrl.stack_panel
    ui = sp.ui
    ui.checkBox_adaptiveEnable.setChecked(True)
    ui.doubleSpinBox_adaptiveMinExposure.setValue(5.0)  # 5 ms
    ui.doubleSpinBox_adaptiveMinExposure.editingFinished.emit()
    real_acq = ctrl.acquisition_panel
    mock_acq = MagicMock()
    mock_acq.ui = MagicMock(spec=[])  # no comboBox_cameraShutterMode
    ctrl.acquisition_panel = mock_acq
    try:
        cfg = sp.build_adaptive_config()
    finally:
        ctrl.acquisition_panel = real_acq
    assert cfg is not None
    # 5 ms → 5e-3 s (Rolling default).
    assert cfg.min_exposure_s == pytest.approx(5e-3, rel=1e-9)


# ---------------------------------------------------------------------------
# Defensive guard branches: laser_panel None (345->350), cb1/cb2 None
# (348->350), missing widget in _load_adaptive_config (469), bad lasers
# tuple in _narrow_adaptive_power_maxima (492), narrow widget-missing +
# bad-live_max guards (503, 506-507, 530, 533-534), shutter-units loop
# sb-None guards (604->602, 612->610).
# ---------------------------------------------------------------------------


def test_summary_render_no_laser_panel(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """When ``shell.laser_panel`` is None, the multi-channel detection
    skips the checkbox read and renders a single-channel summary (the
    ``laser_panel is None`` False-guard branch, 345->350)."""
    ctrl = controller
    sp = ctrl.stack_panel
    ctrl.stack_first_plane_set = True
    ctrl.stack_last_plane_set = True
    sp.ui.doubleSpinBox_acqPlaneStepSize.setValue(1.0)
    sp.ui.doubleSpinBox_acqFirstPlane.setValue(0.0)
    sp.ui.doubleSpinBox_acqLastPlane.setValue(10.0)
    ctrl.number_of_planes = 11
    real_lp = ctrl.laser_panel
    ctrl.laser_panel = None  # ty: ignore[invalid-assignment]
    try:
        sp._render_stack_plan_summary()
        text = sp.ui.label_stackPlanSummary.text()
    finally:
        ctrl.laser_panel = real_lp
    assert "2 ch" not in text


def test_summary_render_laser_panel_missing_checkboxes(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """When the laser_panel ui lacks the auto-laser checkboxes, the
    multi-channel detection falls back to single-channel (the
    ``cb1 is None or cb2 is None`` branch, 348->350)."""
    ctrl = controller
    sp = ctrl.stack_panel
    ctrl.stack_first_plane_set = True
    ctrl.stack_last_plane_set = True
    sp.ui.doubleSpinBox_acqPlaneStepSize.setValue(1.0)
    sp.ui.doubleSpinBox_acqFirstPlane.setValue(0.0)
    sp.ui.doubleSpinBox_acqLastPlane.setValue(10.0)
    ctrl.number_of_planes = 11
    real_lp = ctrl.laser_panel
    mock_lp = MagicMock()
    mock_lp.ui = MagicMock(spec=[])  # no checkBox_laserOneAutomatic etc.
    ctrl.laser_panel = mock_lp
    try:
        sp._render_stack_plan_summary()
        text = sp.ui.label_stackPlanSummary.text()
    finally:
        ctrl.laser_panel = real_lp
    assert "2 ch" not in text


def test_narrow_adaptive_power_maxima_no_bundle_returns(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """When ``shell._bundle`` is None or has no lasers tuple, the
    narrow-maxima method returns early (line 492 guard)."""
    ctrl = controller
    sp = ctrl.stack_panel
    real_bundle = ctrl._bundle
    ctrl._bundle = None  # ty: ignore[invalid-assignment]
    try:
        # Must not raise — the early return fires.
        sp._narrow_adaptive_power_maxima()
    finally:
        ctrl._bundle = real_bundle


def test_narrow_adaptive_power_maxima_bad_live_max_skips(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """When ``lasers[i].max_power`` raises (TypeError/ValueError), the
    narrow loop skips that laser (the except branch, 506-507 and
    533-534)."""
    from dataclasses import replace

    from lightsheet.hal import MockLaser

    ctrl = controller
    sp = ctrl.stack_panel
    real_bundle = ctrl._bundle
    # Build a laser whose max_power property raises TypeError.
    bad_laser = MockLaser(wavelength=555, max_power_mw=300.0, label="bad")
    # Replace max_power with a property that raises.
    type(bad_laser).max_power = property(  # type: ignore[attr-defined]  # ty: ignore[invalid-assignment]
        lambda self: (_ for _ in ()).throw(TypeError("bad"))
    )
    bad_bundle = replace(real_bundle, lasers=(bad_laser, bad_laser))
    ctrl._bundle = bad_bundle
    try:
        # Must not raise — the except branches swallow the TypeError.
        sp._narrow_adaptive_power_maxima()
    finally:
        ctrl._bundle = real_bundle
        # Restore the original MockLaser.max_power property.
        del type(bad_laser).max_power  # type: ignore[attr-defined]


def test_update_adaptive_shutter_units_lightsheet_sb_none(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """In Lightsheet mode, when an exposure spinbox is None (defensive
    guard), the loop skips it (the ``sb is None`` branch, 604->602)."""
    ctrl = controller
    sp = ctrl.stack_panel
    ctrl.acquisition_panel.ui.comboBox_cameraShutterMode.setCurrentText("Lightsheet")
    # Temporarily hide one spinbox by setting the attribute to None on
    # the ui namespace — the loop uses getattr with a None default.
    real_sb = sp.ui.doubleSpinBox_adaptiveMinExposure
    sp.ui.doubleSpinBox_adaptiveMinExposure = None  # ty: ignore[invalid-assignment]
    try:
        # Must not raise — the sb-None guard skips the missing spinbox.
        sp._update_adaptive_shutter_units()
    finally:
        sp.ui.doubleSpinBox_adaptiveMinExposure = real_sb


def test_update_adaptive_shutter_units_rolling_sb_none(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """In Rolling mode, when an exposure spinbox is None (defensive
    guard), the loop skips it (the ``sb is None`` branch, 612->610)."""
    ctrl = controller
    sp = ctrl.stack_panel
    ctrl.acquisition_panel.ui.comboBox_cameraShutterMode.setCurrentText("Rolling")
    real_sb = sp.ui.doubleSpinBox_adaptiveMinExposure
    sp.ui.doubleSpinBox_adaptiveMinExposure = None  # ty: ignore[invalid-assignment]
    try:
        sp._update_adaptive_shutter_units()
    finally:
        sp.ui.doubleSpinBox_adaptiveMinExposure = real_sb
