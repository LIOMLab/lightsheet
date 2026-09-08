"""Frozen-spawn-snapshot contract tests for all acquisition workers.

Every preview/live/single/stack worker receives one ``MicroscopeSnapshot``
at construction; save metadata, save branches, and auto-laser selection come
from that snapshot, so GUI/model edits made after spawn cannot reach the
running worker.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import Mock, patch

import numpy as np
import pytest

pytest.importorskip("PySide6")

from pytestqt.qtbot import QtBot

from lightsheet.gui.panels import acquisition_panel
from lightsheet.gui.workers import (
    LiveWorker,
    PreviewWorker,
    SingleWorker,
    StackWorker,
)
from lightsheet.state import MicroscopeSnapshot, SaveMode, SaveOptions

if TYPE_CHECKING:
    from lightsheet.gui.shell.controller import Controller_MainWindow


def _spawn_snapshot(
    ctrl: Controller_MainWindow,
    *,
    description: str = "spawn desc",
    mode: SaveMode = SaveMode.STITCH,
    auto: tuple[bool, bool] = (True, False),
) -> MicroscopeSnapshot:
    """Commit intent to the model and return the resulting frozen snapshot."""
    ctrl.state.set_save_options(SaveOptions(description=description, mode=mode))
    ctrl.state.set_auto_lasers(*auto)
    return ctrl.state.snapshot()


def test_preview_worker_holds_spawn_snapshot(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """PreviewWorker stores the exact snapshot object; post-spawn model
    edits do not change it."""
    ctrl = controller
    snap = _spawn_snapshot(ctrl, auto=(True, True))
    worker = PreviewWorker(ctrl._bundle, ctrl._hw, ctrl, snapshot=snap)
    assert worker._snapshot is snap
    ctrl.state.set_auto_lasers(False, False)
    assert worker._snapshot.auto_lasers == (True, True)


def test_live_worker_holds_spawn_snapshot(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """LiveWorker stores the exact snapshot object; post-spawn model edits
    do not change it."""
    ctrl = controller
    snap = _spawn_snapshot(ctrl, auto=(False, True))
    worker = LiveWorker(ctrl._bundle, ctrl._hw, ctrl, snapshot=snap)
    assert worker._snapshot is snap
    ctrl.state.set_auto_lasers(True, True)
    assert worker._snapshot.auto_lasers == (False, True)


def test_single_worker_save_metadata_frozen_at_spawn(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """SingleWorker derives _save_description/_save_stitch_blend from the
    snapshot; post-spawn model edits leave them unchanged."""
    ctrl = controller
    snap = _spawn_snapshot(ctrl, description="single spawn", mode=SaveMode.STITCH_BLEND)
    worker = SingleWorker(ctrl._bundle, ctrl._hw, ctrl, snapshot=snap)
    assert worker._save_description == "single spawn"
    assert worker._save_stitch_blend is True
    assert worker._multi_channel is False

    ctrl.state.set_save_options(SaveOptions("edited later", SaveMode.ALL_FULL))
    assert worker._save_description == "single spawn"
    assert worker._save_stitch_blend is True


def test_single_worker_multi_channel_from_snapshot(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """_multi_channel is derived from snapshot.auto_lasers (both checked),
    not a separate mutable flag."""
    ctrl = controller
    snap = _spawn_snapshot(ctrl, auto=(True, True))
    worker = SingleWorker(ctrl._bundle, ctrl._hw, ctrl, snapshot=snap)
    assert worker._multi_channel is True
    ctrl.state.set_auto_lasers(False, False)
    assert worker._multi_channel is True


def test_single_worker_legacy_args_fold_into_snapshot(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """The legacy save_description/save_stitch_blend positional adapter is
    converted to a frozen snapshot at construction."""
    ctrl = controller
    worker = SingleWorker(
        ctrl._bundle,
        ctrl._hw,
        ctrl,
        save_description="legacy desc",
        save_stitch_blend=True,
    )
    assert worker._save_description == "legacy desc"
    assert worker._save_stitch_blend is True
    assert worker._snapshot.save_options.mode == SaveMode.STITCH_BLEND


def test_single_worker_acquire_scan_metadata_uses_spawn_snapshot(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """acquire_scan stamps the frozen spawn description into the buffer
    metadata even after the model is edited post-spawn."""
    ctrl = controller
    snap = _spawn_snapshot(ctrl, description="run-start name")
    worker = SingleWorker(ctrl._bundle, ctrl._hw, ctrl, snapshot=snap)
    ctrl.state.set_save_description("post-spawn edit")

    worker.siggen.waveform_cycles = 1
    worker.camera.copy_recorder_images = Mock(
        return_value=np.zeros((1, 8, 8), dtype=np.uint16)
    )
    worker.camera.recorder_timeout_status = False
    with patch.object(
        ctrl._fs,
        "reconstruct_frame",
        return_value=np.zeros((8, 8), dtype=np.uint16),
    ):
        assert worker.acquire_scan() is True
    assert (
        ctrl.buffer_metadata_general[  # ty: ignore[unresolved-attribute]
            "Sample Name"
        ] == "run-start name"
    )


def test_stack_worker_save_mode_branches_frozen_at_spawn(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """StackWorker derives all four SaveMode branch flags and the sample
    description from the snapshot; post-spawn model edits leave them
    unchanged."""
    ctrl = controller
    snap = _spawn_snapshot(ctrl, description="stack spawn", mode=SaveMode.ALL_FULL)
    worker = StackWorker(ctrl._bundle, ctrl._hw, ctrl, snapshot=snap)
    assert worker._save_description == "stack spawn"
    assert worker._save_all_full is True
    assert worker._save_all_crop is False
    assert worker._save_stitch_blend is False

    ctrl.state.set_save_options(SaveOptions("edited", SaveMode.ALL_CROP))
    assert worker._save_description == "stack spawn"
    assert worker._save_all_full is True
    assert worker._save_all_crop is False


def test_stack_worker_all_modes_project(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """Each SaveMode maps to exactly one stack save branch flag set."""
    ctrl = controller
    expected = {
        SaveMode.STITCH: (False, False, False),
        SaveMode.STITCH_BLEND: (True, False, False),
        SaveMode.ALL_CROP: (False, True, False),
        SaveMode.ALL_FULL: (False, False, True),
    }
    for mode, (blend, crop, full) in expected.items():
        snap = _spawn_snapshot(ctrl, mode=mode)
        worker = StackWorker(ctrl._bundle, ctrl._hw, ctrl, snapshot=snap)
        assert worker._save_stitch_blend is blend
        assert worker._save_all_crop is crop
        assert worker._save_all_full is full


def test_stack_worker_multi_channel_and_wavelengths_from_snapshot(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """Multi-channel + per-channel wavelengths come from the snapshot's
    auto_lasers, and run() passes the snapshot description to
    add_sample_name (never writes shell.save_description)."""
    ctrl = controller
    snap = _spawn_snapshot(ctrl, description="mc spawn", auto=(True, True))
    worker = StackWorker(ctrl._bundle, ctrl._hw, ctrl, snapshot=snap)
    assert worker._multi_channel is True
    assert worker._wavelengths == [
        int(ctrl.lasers[0].wavelength),
        int(ctrl.lasers[1].wavelength),
    ]

    ctrl.state.set_save_description("post-spawn edit")
    ctrl.saving_allowed = True
    ctrl.number_of_planes = 1
    # stack_mode_started stays False so no laser/loop work runs; the save
    # branch still executes and consumes the frozen metadata.
    add_name = Mock()
    with (
        patch.object(ctrl._fs, "add_sample_name", add_name),
        patch.object(ctrl._fs, "set_files") as set_files,
        patch.object(ctrl._fs, "start_saving"),
    ):
        worker.run()
    add_name.assert_called_once_with("mc spawn")
    set_files.assert_called_once()
    assert ctrl.save_description == "post-spawn edit"  # worker never wrote it


def test_spawn_sites_pass_frozen_snapshot(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """updateUi_single_mode_button passes one MicroscopeSnapshot to
    SingleWorker (the GUI-thread freeze point)."""
    ctrl = controller
    ctrl.state.set_save_options(SaveOptions("spawn-site desc", SaveMode.STITCH_BLEND))

    captured: dict[str, object] = {}

    def _capture(*args: object, **kwargs: object) -> Mock:
        captured["snapshot"] = kwargs.get("snapshot")
        worker = Mock()
        worker.finished = Mock()
        worker.moveToThread = Mock()
        return worker

    with (
        patch.object(acquisition_panel, "SingleWorker", side_effect=_capture),
        patch.object(acquisition_panel, "QThread") as thread_cls,
    ):
        ctrl.acquisition_panel.updateUi_single_mode_button()

    snap = captured.get("snapshot")
    assert isinstance(snap, MicroscopeSnapshot)
    assert snap.save_options.description == "spawn-site desc"
    assert snap.save_options.mode == SaveMode.STITCH_BLEND
    thread_cls.return_value.start.assert_called_once()
