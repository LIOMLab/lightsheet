"""Pure + pytest-qt tests for the reactive microscope state model.

Covers frozen-snapshot validation, model mutators, changed-only signals,
worker-applied snapshot folding, and snapshot independence.
"""

from __future__ import annotations

import dataclasses

import pytest
from PySide6.QtCore import QCoreApplication
from pytestqt.qtbot import QtBot

from lightsheet.state import (
    AppliedMicroscopeSnapshot,
    MicroscopeSnapshot,
    MicroscopeState,
    SaveMode,
    SaveOptions,
)


def test_save_mode_enum() -> None:
    """SaveMode exposes the four exclusive save-mode values."""
    assert {m.value for m in SaveMode} == {
        "stitch",
        "stitch_blend",
        "all_crop",
        "all_full",
    }


def test_save_options_defaults() -> None:
    """SaveOptions has an empty description and STITCH mode by default."""
    opts = SaveOptions()
    assert opts.description == ""
    assert opts.mode == SaveMode.STITCH


def test_save_options_frozen() -> None:
    """SaveOptions is frozen and can be replaced with dataclasses.replace."""
    opts = SaveOptions(description="old")
    new = dataclasses.replace(opts, description="new")
    assert new.description == "new"
    assert opts.description == "old"
    with pytest.raises(dataclasses.FrozenInstanceError):
        opts.description = "mutated"  # type: ignore[misc]  # ty: ignore[invalid-assignment]


def test_microscope_snapshot_defaults() -> None:
    """MicroscopeSnapshot validates and freezes default intent."""
    snap = MicroscopeSnapshot(lightsheet_line_time_s=1e-5)
    assert snap.lightsheet_line_time_s == 1e-5
    assert snap.laser_power_pct == (0.0, 0.0)
    assert snap.laser_enabled == (False, False)
    assert snap.auto_lasers == (False, False)
    assert snap.save_options == SaveOptions()
    with pytest.raises(dataclasses.FrozenInstanceError):
        snap.lightsheet_line_time_s = 2e-5  # type: ignore[misc]  # ty: ignore[invalid-assignment]


def test_microscope_snapshot_validates_line_time() -> None:
    """Non-positive or non-finite line time raises ValueError."""
    with pytest.raises(ValueError, match="positive"):
        MicroscopeSnapshot(lightsheet_line_time_s=0.0)
    with pytest.raises(ValueError, match="finite"):
        MicroscopeSnapshot(lightsheet_line_time_s=float("nan"))
    with pytest.raises(ValueError, match="positive"):
        MicroscopeSnapshot(lightsheet_line_time_s=-1e-5)


def test_microscope_snapshot_validates_laser_power_tuple() -> None:
    """Laser power pct must be a 2-tuple of finite [0, 100] values."""
    with pytest.raises(ValueError, match="2-tuple"):
        MicroscopeSnapshot(
            lightsheet_line_time_s=1e-5,
            laser_power_pct=(50.0,),  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]
        )
    with pytest.raises(ValueError, match=r"\[0, 100\]"):
        MicroscopeSnapshot(
            lightsheet_line_time_s=1e-5,
            laser_power_pct=(50.0, 101.0),
        )
    with pytest.raises(ValueError, match="finite"):
        MicroscopeSnapshot(
            lightsheet_line_time_s=1e-5,
            laser_power_pct=(float("inf"), 50.0),
        )


def test_microscope_snapshot_validates_auto_lasers() -> None:
    """Auto-laser and laser-enabled tuples must be 2-tuples of bools."""
    with pytest.raises(ValueError, match="2-tuple"):
        MicroscopeSnapshot(
            lightsheet_line_time_s=1e-5,
            auto_lasers=(True,),  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]
        )
    with pytest.raises(ValueError, match="bool"):
        MicroscopeSnapshot(
            lightsheet_line_time_s=1e-5,
            auto_lasers=(True, 1),  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]
        )


def test_snapshot_replace_produces_independent_copy() -> None:
    """dataclasses.replace creates a new frozen snapshot and leaves the
    original unchanged."""
    snap = MicroscopeSnapshot(lightsheet_line_time_s=1e-5)
    new = dataclasses.replace(snap, laser_power_pct=(50.0, 50.0))
    assert new.laser_power_pct == (50.0, 50.0)
    assert snap.laser_power_pct == (0.0, 0.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        new.laser_power_pct = (60.0, 60.0)  # type: ignore[misc]  # ty: ignore[invalid-assignment]


def test_model_snapshot_returns_frozen_copy(qtbot: QtBot) -> None:
    """MicroscopeState.snapshot() returns the current frozen snapshot."""
    _ = QCoreApplication.instance() or QCoreApplication()
    state = MicroscopeState(lightsheet_line_time_s=1e-5)
    snap = state.snapshot()
    assert isinstance(snap, MicroscopeSnapshot)
    assert snap.lightsheet_line_time_s == 1e-5


def test_model_set_laser_power_emits_once(qtbot: QtBot) -> None:
    """set_laser_power_pct emits sig_laser_power_changed only for a real change."""
    _ = QCoreApplication.instance() or QCoreApplication()
    state = MicroscopeState(lightsheet_line_time_s=1e-5)
    state.set_laser_power_pct(0, 50.0)
    with qtbot.waitSignal(state.sig_laser_power_changed, timeout=100):
        state.set_laser_power_pct(0, 75.0)
    assert state.laser_power_pct == (75.0, 0.0)


def test_model_set_laser_power_suppresses_unchanged(qtbot: QtBot) -> None:
    """Setting the same percent does not re-emit the change signal."""
    _ = QCoreApplication.instance() or QCoreApplication()
    state = MicroscopeState(lightsheet_line_time_s=1e-5)
    state.set_laser_power_pct(0, 50.0)
    with qtbot.assertNotEmitted(state.sig_laser_power_changed, wait=100):
        state.set_laser_power_pct(0, 50.0)


def test_model_set_laser_power_validates(qtbot: QtBot) -> None:
    """set_laser_power_pct rejects out-of-range and non-numeric inputs."""
    _ = QCoreApplication.instance() or QCoreApplication()
    state = MicroscopeState(lightsheet_line_time_s=1e-5)
    with pytest.raises(ValueError, match=r"\[0, 100\]"):
        state.set_laser_power_pct(0, 150.0)
    with pytest.raises(ValueError, match=r"\[0, 100\]"):
        state.set_laser_power_pct(1, -1.0)
    with pytest.raises(ValueError, match="numeric"):
        state.set_laser_power_pct(0, "bad")  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]


def test_model_apply_worker_snapshot_folds_non_none_fields(qtbot: QtBot) -> None:
    """apply_worker_snapshot merges only the non-None fields from the applied
    snapshot and emits the changed-domain signal.
    """
    _ = QCoreApplication.instance() or QCoreApplication()
    state = MicroscopeState(lightsheet_line_time_s=1e-5)
    state.set_laser_power_pct(0, 25.0)
    state.set_laser_power_pct(1, 25.0)

    applied = AppliedMicroscopeSnapshot(laser_power_pct=(50.0, 75.0))
    with qtbot.waitSignal(state.sig_laser_power_changed, timeout=100):
        state.apply_worker_snapshot(applied)

    assert state.laser_power_pct == (50.0, 75.0)
    assert state.lightsheet_line_time_s == 1e-5  # unchanged


def test_model_apply_worker_snapshot_rejects_wrong_type(qtbot: QtBot) -> None:
    """apply_worker_snapshot raises TypeError for non-AppliedMicroscopeSnapshot
    payloads.
    """
    _ = QCoreApplication.instance() or QCoreApplication()
    state = MicroscopeState(lightsheet_line_time_s=1e-5)
    with pytest.raises(TypeError, match="AppliedMicroscopeSnapshot"):
        state.apply_worker_snapshot({"laser_power_pct": (50.0, 50.0)})


def test_applied_snapshot_validates() -> None:
    """AppliedMicroscopeSnapshot validates non-None fields."""
    with pytest.raises(ValueError, match="2-tuple"):
        AppliedMicroscopeSnapshot(laser_power_pct=(50.0,))  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]
    with pytest.raises(ValueError, match="positive"):
        AppliedMicroscopeSnapshot(lightsheet_line_time_s=-1.0)


def test_model_set_save_options_emits_on_change(qtbot: QtBot) -> None:
    """set_save_options emits sig_save_options_changed only when changed."""
    _ = QCoreApplication.instance() or QCoreApplication()
    state = MicroscopeState(lightsheet_line_time_s=1e-5)
    new_opts = SaveOptions(description="test", mode=SaveMode.ALL_CROP)
    with qtbot.waitSignal(state.sig_save_options_changed, timeout=100):
        state.set_save_options(new_opts)
    assert state.save_options == new_opts


def test_model_set_save_options_suppresses_unchanged(qtbot: QtBot) -> None:
    """Applying an equal SaveOptions does not re-emit the change signal."""
    _ = QCoreApplication.instance() or QCoreApplication()
    state = MicroscopeState(lightsheet_line_time_s=1e-5)
    with qtbot.assertNotEmitted(state.sig_save_options_changed, wait=100):
        state.set_save_options(SaveOptions())


def test_model_set_save_options_validates_type(qtbot: QtBot) -> None:
    """set_save_options rejects non-SaveOptions payloads."""
    _ = QCoreApplication.instance() or QCoreApplication()
    state = MicroscopeState(lightsheet_line_time_s=1e-5)
    with pytest.raises(ValueError, match="SaveOptions"):
        state.set_save_options({"description": "x"})  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]


def test_model_set_save_mode_and_description(qtbot: QtBot) -> None:
    """set_save_mode and set_save_description fold one field through
    set_save_options and validate their argument types."""
    _ = QCoreApplication.instance() or QCoreApplication()
    state = MicroscopeState(lightsheet_line_time_s=1e-5)

    with qtbot.waitSignal(state.sig_save_options_changed, timeout=100):
        state.set_save_mode(SaveMode.ALL_FULL)
    assert state.save_options.mode == SaveMode.ALL_FULL
    assert state.save_options.description == ""

    with qtbot.waitSignal(state.sig_save_options_changed, timeout=100):
        state.set_save_description("new desc")
    assert state.save_options.description == "new desc"
    assert state.save_options.mode == SaveMode.ALL_FULL

    # Unchanged values do not re-emit.
    with qtbot.assertNotEmitted(state.sig_save_options_changed, wait=100):
        state.set_save_mode(SaveMode.ALL_FULL)
        state.set_save_description("new desc")

    with pytest.raises(ValueError, match="SaveMode"):
        state.set_save_mode("stitch")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="str"):
        state.set_save_description(5)  # type: ignore[arg-type]


def test_model_set_laser_enabled_emits_and_validates(qtbot: QtBot) -> None:
    """set_laser_enabled validates index/type, emits on change, and
    suppresses an unchanged write."""
    _ = QCoreApplication.instance() or QCoreApplication()
    state = MicroscopeState(lightsheet_line_time_s=1e-5)
    assert state.laser_enabled == (False, False)

    with qtbot.waitSignal(state.sig_laser_enabled_changed, timeout=100):
        state.set_laser_enabled(1, True)
    assert state.laser_enabled == (False, True)

    with qtbot.assertNotEmitted(state.sig_laser_enabled_changed, wait=100):
        state.set_laser_enabled(1, True)

    with pytest.raises(IndexError, match="0 or 1"):
        state.set_laser_enabled(2, True)
    with pytest.raises(IndexError, match="0 or 1"):
        state.set_laser_enabled(-1, False)
    with pytest.raises(ValueError, match="bool"):
        state.set_laser_enabled(0, 1)  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]


def test_model_set_laser_power_rejects_bad_index_and_nonfinite(
    qtbot: QtBot,
) -> None:
    """set_laser_power_pct rejects out-of-range indices and non-finite
    percentages."""
    _ = QCoreApplication.instance() or QCoreApplication()
    state = MicroscopeState(lightsheet_line_time_s=1e-5)
    with pytest.raises(IndexError, match="0 or 1"):
        state.set_laser_power_pct(5, 10.0)
    with pytest.raises(IndexError, match="0 or 1"):
        state.set_laser_power_pct(-1, 10.0)
    with pytest.raises(ValueError, match="finite"):
        state.set_laser_power_pct(0, float("nan"))
    with pytest.raises(ValueError, match="finite"):
        state.set_laser_power_pct(1, float("inf"))
    with pytest.raises(ValueError, match="numeric"):
        state.set_laser_power_pct(0, True)  # type: ignore[arg-type]


def test_model_set_auto_lasers_validates_bools(qtbot: QtBot) -> None:
    """set_auto_lasers rejects non-bool arguments and emits on change."""
    _ = QCoreApplication.instance() or QCoreApplication()
    state = MicroscopeState(lightsheet_line_time_s=1e-5)
    with pytest.raises(ValueError, match="bool"):
        state.set_auto_lasers(True, 1)  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]
    with pytest.raises(ValueError, match="bool"):
        state.set_auto_lasers("yes", False)  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]

    with qtbot.waitSignal(state.sig_auto_lasers_changed, timeout=100):
        state.set_auto_lasers(True, False)
    assert state.auto_laser1 is True
    assert state.auto_laser2 is False

    with qtbot.assertNotEmitted(state.sig_auto_lasers_changed, wait=100):
        state.set_auto_lasers(True, False)


def test_model_set_lightsheet_line_time_emits_and_validates(
    qtbot: QtBot,
) -> None:
    """set_lightsheet_line_time_s rejects non-numeric, non-finite, and
    non-positive values and emits only on a real change."""
    _ = QCoreApplication.instance() or QCoreApplication()
    state = MicroscopeState(lightsheet_line_time_s=1e-5)

    with pytest.raises(ValueError, match="numeric"):
        state.set_lightsheet_line_time_s("fast")  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]
    with pytest.raises(ValueError, match="numeric"):
        state.set_lightsheet_line_time_s(True)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="finite"):
        state.set_lightsheet_line_time_s(float("nan"))
    with pytest.raises(ValueError, match="finite"):
        state.set_lightsheet_line_time_s(float("inf"))
    with pytest.raises(ValueError, match="positive"):
        state.set_lightsheet_line_time_s(0.0)
    with pytest.raises(ValueError, match="positive"):
        state.set_lightsheet_line_time_s(-1e-5)

    with qtbot.waitSignal(state.sig_lightsheet_line_time_changed, timeout=100):
        state.set_lightsheet_line_time_s(2e-5)
    assert state.lightsheet_line_time_s == 2e-5

    with qtbot.assertNotEmitted(state.sig_lightsheet_line_time_changed, wait=100):
        state.set_lightsheet_line_time_s(2e-5)


def test_model_apply_worker_snapshot_partial_changes(qtbot: QtBot) -> None:
    """apply_worker_snapshot emits only for the elements that actually
    changed — an unchanged applied value is folded but not re-emitted."""
    _ = QCoreApplication.instance() or QCoreApplication()
    state = MicroscopeState(lightsheet_line_time_s=1e-5)
    state.set_laser_power_pct(0, 50.0)
    state.set_laser_power_pct(1, 50.0)
    state.set_laser_enabled(0, True)

    # Only index 1 changes; index 0 is isclose-equal to the live value.
    applied = AppliedMicroscopeSnapshot(laser_power_pct=(50.0, 75.0))
    emissions: list[tuple[int, float]] = []
    state.sig_laser_power_changed.connect(lambda idx, val: emissions.append((idx, val)))
    state.apply_worker_snapshot(applied)
    assert state.laser_power_pct == (50.0, 75.0)
    assert emissions == [(1, 75.0)]

    # Only index 1 changes on the enabled pair as well.
    enabled_emissions: list[tuple[int, bool]] = []
    state.sig_laser_enabled_changed.connect(
        lambda idx, val: enabled_emissions.append((idx, val))
    )
    state.apply_worker_snapshot(AppliedMicroscopeSnapshot(laser_enabled=(True, True)))
    assert state.laser_enabled == (True, True)
    assert enabled_emissions == [(1, True)]


def test_model_apply_worker_snapshot_no_change_returns_early(
    qtbot: QtBot,
) -> None:
    """An applied snapshot equal to the live model takes the early-return
    path and emits nothing."""
    _ = QCoreApplication.instance() or QCoreApplication()
    state = MicroscopeState(lightsheet_line_time_s=1e-5)
    emissions: list[object] = []
    state.sig_laser_power_changed.connect(lambda i, v: emissions.append((i, v)))
    state.sig_lightsheet_line_time_changed.connect(lambda v: emissions.append(v))

    state.apply_worker_snapshot(
        AppliedMicroscopeSnapshot(
            laser_power_pct=(0.0, 0.0),
            laser_enabled=(False, False),
            lightsheet_line_time_s=1e-5,
        )
    )
    assert emissions == []


def test_model_apply_worker_snapshot_folds_line_time(qtbot: QtBot) -> None:
    """An applied line-time change updates the model and emits the
    line-time signal; an unchanged line time emits nothing."""
    _ = QCoreApplication.instance() or QCoreApplication()
    state = MicroscopeState(lightsheet_line_time_s=1e-5)
    emissions: list[float] = []
    state.sig_lightsheet_line_time_changed.connect(emissions.append)

    state.apply_worker_snapshot(AppliedMicroscopeSnapshot(lightsheet_line_time_s=3e-5))
    assert state.lightsheet_line_time_s == 3e-5
    assert emissions == [3e-5]

    emissions.clear()
    state.apply_worker_snapshot(AppliedMicroscopeSnapshot(lightsheet_line_time_s=3e-5))
    assert emissions == []


def test_model_construction_sanitizes_bad_line_time(qtbot: QtBot) -> None:
    """A non-positive or non-finite ``lightsheet_line_time_s`` at
    construction (bad config key, test double, partially opened camera)
    falls back to a positive default instead of raising ``ValueError``
    out of ``MicroscopeSnapshot.__post_init__`` — a bad HAL attribute
    must not crash the shell at startup."""
    _ = QCoreApplication.instance() or QCoreApplication()
    for bad in (0.0, -1e-5, float("inf"), float("nan"), "x"):
        state = MicroscopeState(lightsheet_line_time_s=bad)  # ty: ignore[invalid-argument-type]
        assert state.lightsheet_line_time_s == 1.0

    # Valid values pass through untouched.
    state = MicroscopeState(lightsheet_line_time_s=2e-5)
    assert state.lightsheet_line_time_s == 2e-5
