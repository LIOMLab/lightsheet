"""Branch-coverage closure for ``lightsheet.gui.workers.stack_adaptive``.

The _StackAdaptiveMixin methods are exercised with the minimal shell
stand-in pattern used by ``test_stack_worker_position_emit.py``. This
covers the four branch-coverage gaps reported by the rig gate:

- ``shutter_mode == "Lightsheet"`` exposure rounding path (line 76).
- ``_apply_adaptive_command`` skipping laser 1 when max_power <= 0
  (88 -> 103) and laser 2 when max_power <= 0 (103 -> exit).
- ``_record_adaptive_step`` skipping ``record_adaptive_sample`` when
  ``saving_allowed`` is False (173 -> 177).
"""

from __future__ import annotations

from unittest.mock import MagicMock, Mock

import numpy as np
import pytest
from pytestqt.qtbot import QtBot

pytest.importorskip("PySide6")

from lightsheet.adaptive.types import AdaptiveCommand, AdaptiveConfig
from lightsheet.gui.workers import StackWorker


def test_stack_adaptive_mixin_missing_branches(qtbot: QtBot) -> None:
    """Exercise the remaining branch-coverage edges in the adaptive mixin."""
    from test.helpers.factories import make_bundle

    bundle = make_bundle()
    shell = Mock()
    shell.lasers = bundle.lasers
    shell.lasers[0].max_power = 0.0
    shell.lasers[1].max_power = 0.0
    shell.saving_allowed = False
    shell._fs = Mock()
    shell.sig_message = Mock()
    shell.reconstructed_frame = np.zeros((4, 4), dtype=np.uint16)
    shell.reconstructed_frames = {}

    worker = StackWorker(
        bundle,
        Mock(),
        shell,
        save_description="adaptive coverage",
        save_stitch_blend=False,
        save_all_crop=False,
        save_all_full=False,
        multi_channel=False,
    )

    cmd = AdaptiveCommand.fixed(
        exposure_s=0.0001,
        laser1_mw=1.0,
        laser2_mw=2.0,
    )
    worker._adaptive_controller = MagicMock()
    worker._adaptive_controller.update.return_value = cmd
    worker._adaptive_cfg = AdaptiveConfig()
    worker._adaptive_current_cmd = cmd

    # Cover _apply_adaptive_command branches: Lightsheet exposure path and
    # both laser max_power <= 0 skips.
    worker.camera.shutter_mode = "Lightsheet"
    worker._apply_adaptive_command(cmd)

    # Cover _record_adaptive_step: saving_allowed=False skips record.
    worker._multi_channel = False
    worker._record_adaptive_step(0)

    assert worker._adaptive_controller.update.called


def test_apply_adaptive_command_clamps_readback_and_preserves_intent(
    qtbot: QtBot,
) -> None:
    """The applied-percent readback is cosmetic: a backend power value
    above max_power must clamp into [0, 100] instead of raising out of
    AppliedMicroscopeSnapshot and aborting the stack, and a laser that
    was not writable this plane must keep the staged intent percent
    rather than being reported as 0."""
    from lightsheet.state.types import (
        AppliedMicroscopeSnapshot,
        MicroscopeSnapshot,
    )
    from test.helpers.factories import make_bundle

    bundle = make_bundle()
    shell = Mock()
    shell.lasers = bundle.lasers
    shell.lasers[0].max_power = 100.0
    shell.lasers[0].power = 150.0  # readback exceeds max -> clamps to 100
    shell.lasers[1].max_power = 0.0  # not writable -> keeps staged intent
    shell.sig_message = Mock()

    worker = StackWorker(
        bundle,
        Mock(),
        shell,
        snapshot=MicroscopeSnapshot(
            lightsheet_line_time_s=1e-5,
            laser_power_pct=(30.0, 40.0),
        ),
    )
    worker.camera.shutter_mode = "Rolling"
    captured: list[AppliedMicroscopeSnapshot] = []
    worker.sig_applied_state.connect(captured.append)

    cmd = AdaptiveCommand.fixed(
        exposure_s=0.01,
        laser1_mw=50.0,
        laser2_mw=0.0,
    )
    worker._apply_adaptive_command(cmd)

    assert len(captured) == 1
    assert captured[0].laser_power_pct == (100.0, 40.0)


def test_apply_adaptive_command_clamps_line_time_to_camera_ceiling(
    qtbot: QtBot,
) -> None:
    """An adaptive command whose implied line time exceeds the camera's
    configured ceiling is clamped before it reaches the camera — an
    out-of-range line time arms silently but returns zero frames and
    wedges every later acquisition on the persisted intent."""
    from test.helpers.factories import make_bundle

    bundle = make_bundle()
    shell = Mock()
    shell.lasers = bundle.lasers
    shell.lasers[0].max_power = 0.0
    shell.lasers[1].max_power = 0.0
    shell.saving_allowed = False
    shell._fs = Mock()
    shell.sig_message = Mock()

    worker = StackWorker(
        bundle,
        Mock(),
        shell,
        save_description="adaptive clamp",
        save_stitch_blend=False,
        save_all_crop=False,
        save_all_full=False,
        multi_channel=False,
    )
    worker.camera.shutter_mode = "Lightsheet"
    worker.camera.lightsheet_exposed_lines = 16
    # 50 ms total / 16 lines = 3.125 ms per line — above the mock's
    # 500 µs ceiling.
    assert worker.camera.lightsheet_line_time_max_s == pytest.approx(500e-6)

    cmd = AdaptiveCommand.fixed(
        exposure_s=0.05,
        laser1_mw=0.0,
        laser2_mw=0.0,
    )
    worker._apply_adaptive_command(cmd)

    assert worker.camera.lightsheet_line_time == pytest.approx(500e-6)
    # The applied readback takes the clamped value too.
    assert worker.camera.line_time == pytest.approx(500e-6)


def test_run_teardown_restores_baseline_line_time_on_abort(
    qtbot: QtBot,
) -> None:
    """When a run does not complete, teardown restores the line-time
    intent armed at run start — a wedge-causing adaptive value must not
    leak into the next single/stack acquisition. The GUI model resyncs
    via sig_applied_state."""
    from lightsheet.state.types import AppliedMicroscopeSnapshot
    from test.helpers.factories import make_bundle

    bundle = make_bundle()
    shell = Mock()
    shell.lasers = bundle.lasers
    shell.saving_allowed = False
    shell.sig_message = Mock()

    worker = StackWorker(
        bundle,
        Mock(),
        shell,
        save_description="teardown restore",
        save_stitch_blend=False,
        save_all_crop=False,
        save_all_full=False,
        multi_channel=False,
    )
    # Simulate: armed at the 48.8 µs baseline, adaptive pushed the intent
    # to an elevated value, then the run aborted.
    worker._baseline_lightsheet_line_time_s = 48.8e-6
    worker.camera.lightsheet_line_time = 1.5e-3
    worker._run_completed = False
    captured: list[AppliedMicroscopeSnapshot] = []
    worker.sig_applied_state.connect(captured.append)

    worker._run_teardown(None)

    assert worker.camera.lightsheet_line_time == pytest.approx(48.8e-6)
    assert len(captured) == 1
    assert captured[0].lightsheet_line_time_s == pytest.approx(48.8e-6)


def test_run_teardown_keeps_applied_line_time_on_completed_run(
    qtbot: QtBot,
) -> None:
    """A completed run keeps the last-applied line time — the restore
    is only for aborts, where the value may be wedge-causing."""
    from test.helpers.factories import make_bundle

    bundle = make_bundle()
    shell = Mock()
    shell.lasers = bundle.lasers
    shell.saving_allowed = False
    shell.sig_message = Mock()

    worker = StackWorker(
        bundle,
        Mock(),
        shell,
        save_description="teardown keep",
        save_stitch_blend=False,
        save_all_crop=False,
        save_all_full=False,
        multi_channel=False,
    )
    worker._baseline_lightsheet_line_time_s = 48.8e-6
    worker.camera.lightsheet_line_time = 200e-6
    worker._run_completed = True

    worker._run_teardown(None)

    assert worker.camera.lightsheet_line_time == pytest.approx(200e-6)
