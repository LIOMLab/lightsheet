"""Wave-0 test: StackWorker per-plane position update reaches the GUI
thread only via the queued ``sig_refresh_position_horizontal`` signal,
never a direct ``updateUi_position_horizontal`` method call.

This is the AGENTS.md §11 legacy cross-thread widget-mutation violation
fix — the old ``stack_mode_worker`` called
``self._shell.updateUi_position_horizontal()`` directly from the worker
thread (undefined behavior per Qt's threading model). The relocated
``StackWorker.run`` emits ``self._shell.sig_refresh_position_horizontal``
(a queued ``Signal`` already declared on the shell and connected to
the GUI-thread ``updateUi_position_horizontal`` slot) instead.

The test constructs a ``StackWorker`` against a mock-shell stand-in
(mirroring ``test_acquisition_coordinator_workers.py``'s mock-shell
pattern) with ``number_of_planes=1``, calls ``worker.run()``, and
asserts:
  - ``shell.sig_refresh_position_horizontal.emit`` was called at least
    once (the per-plane position update fired).
  - ``shell.updateUi_position_horizontal`` was NEVER called directly
    (the legacy cross-thread widget mutation is gone).
"""

from __future__ import annotations

from unittest.mock import Mock

import numpy as np
import pytest

pytest.importorskip("PySide6")

from lightsheet.gui.workers import StackWorker
from lightsheet.hal import DeviceBundle, MockCamera, MockETLs, MockLaser, MockMotors, MockSigGen


def _make_bundle() -> DeviceBundle:
    camera = MockCamera(verbose=False)
    siggen = MockSigGen(camera)
    motors = MockMotors()
    lasers = (
        MockLaser(wavelength=555, max_power_mw=300.0, label="L1"),
        MockLaser(wavelength=640, max_power_mw=150.0, label="L2"),
    )
    etls = MockETLs()
    return DeviceBundle(camera=camera, siggen=siggen, motors=motors, etls=etls, lasers=lasers)


class _PositionEmitShell:
    """Minimal mock shell with the attributes StackWorker.run reads/writes."""

    def __init__(self) -> None:
        self.ui = Mock()
        # Mode started flag — set True so the loop body executes.
        self.stack_mode_started = True
        # E-stop event — Mock with is_set() returning False.
        self.estop_event = Mock()
        self.estop_event.is_set.return_value = False

        # Signals
        self.sig_message = Mock()
        self.sig_progress_update = Mock()
        self.sig_beep = Mock()
        self.sig_refresh_position_horizontal = Mock()

        # The legacy direct method — must NEVER be called from the worker.
        self.updateUi_position_horizontal = Mock()

        # Frame saver
        self._fs = Mock()

        # Position / metadata attributes
        self.current_horizontal_position_text = "0.0"
        self.current_vertical_position_text = "0.0"
        self.current_camera_position_text = "0.0"

        # Buffer / reconstructed frame
        self.buffer = None
        self.reconstructed_frame = None

        # Metadata dicts
        self.buffer_metadata_general = {}
        self.buffer_metadata_waveforms = {}
        self.buffer_metadata_motors = {}
        self.buffer_metadata_lasers = {}
        self.buffer_metadata_camera = {}

        # Saving attributes
        self.saving_allowed = False
        self.number_of_planes = 1
        self.save_filename = "test.hdf5"
        self.save_description = "test sample"
        self.stack_starting_plane = 0.0
        self.stack_step = 10.0


def test_stack_worker_position_emit_uses_signal_not_direct_call(qtbot) -> None:
    """StackWorker.run emits sig_refresh_position_horizontal after the motor
    move and NEVER calls updateUi_position_horizontal directly."""
    bundle = _make_bundle()
    shell = _PositionEmitShell()
    hw = Mock()
    worker = StackWorker(
        bundle, hw, shell,
        save_description="test sample",
        save_stitch_blend=False,
        save_all_crop=False,
        save_all_full=False,
    )
    # Mock acquire_scan so we don't run the full scan logic.
    worker.acquire_scan = Mock()
    worker.camera.recorder_timeout_status = False
    worker.siggen.error = 0

    finished_emits: list[None] = []
    worker.finished.connect(lambda: finished_emits.append(None))

    worker.run()

    # The per-plane position update must reach the GUI via the queued signal.
    assert shell.sig_refresh_position_horizontal.emit.called, (
        "StackWorker.run must emit sig_refresh_position_horizontal "
        "after the motor move"
    )
    # The legacy direct cross-thread widget mutation must NOT happen.
    assert not shell.updateUi_position_horizontal.called, (
        "StackWorker.run must NOT call updateUi_position_horizontal "
        "directly — the position update must go through the queued signal"
    )
    # finished signal emitted exactly once.
    assert len(finished_emits) == 1
