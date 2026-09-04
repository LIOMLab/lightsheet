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
