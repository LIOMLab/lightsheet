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
        opts.description = "mutated"  # type: ignore[misc]


def test_microscope_snapshot_defaults() -> None:
    """MicroscopeSnapshot validates and freezes default intent."""
    snap = MicroscopeSnapshot(lightsheet_line_time_s=1e-5)
    assert snap.lightsheet_line_time_s == 1e-5
    assert snap.laser_power_pct == (0.0, 0.0)
    assert snap.laser_enabled == (False, False)
    assert snap.auto_lasers == (False, False)
    assert snap.save_options == SaveOptions()
    with pytest.raises(dataclasses.FrozenInstanceError):
        snap.lightsheet_line_time_s = 2e-5  # type: ignore[misc]


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
            laser_power_pct=(50.0,),
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
            auto_lasers=(True,),
        )
    with pytest.raises(ValueError, match="bool"):
        MicroscopeSnapshot(
            lightsheet_line_time_s=1e-5,
            auto_lasers=(True, 1),
        )


def test_snapshot_replace_produces_independent_copy() -> None:
    """dataclasses.replace creates a new frozen snapshot and leaves the
    original unchanged."""
    snap = MicroscopeSnapshot(lightsheet_line_time_s=1e-5)
    new = dataclasses.replace(snap, laser_power_pct=(50.0, 50.0))
    assert new.laser_power_pct == (50.0, 50.0)
    assert snap.laser_power_pct == (0.0, 0.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        new.laser_power_pct = (60.0, 60.0)  # type: ignore[misc]


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
        state.set_laser_power_pct(0, "bad")  # type: ignore[arg-type]


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
        AppliedMicroscopeSnapshot(laser_power_pct=(50.0,))
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
