"""Worker signal contract tests for PreviewWorker.

Verifies that ``PreviewWorker.run`` emits its ``finished`` signal exactly
once (whether the run completes normally, breaks on E-stop, or an
exception propagates) and that the worker NEVER accesses
``self._shell.ui.*`` widgets directly (AGENTS.md §11 — cross-thread UI
mutation is forbidden; all cross-thread effects flow through queued
signal/slot connections).
"""

from __future__ import annotations

import threading
from unittest.mock import Mock

import pytest

pytest.importorskip("PyQt5")

from lightsheet.gui.workers import PreviewWorker
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


class _PreviewShell:
    """Minimal shell stand-in exposing only the attributes PreviewWorker.run
    reads — no ui.* widget access (the worker must not touch widgets)."""

    def __init__(self) -> None:
        self.ui = Mock()
        self.ui.doubleSpinBox_cameraExposureTime.value.return_value = 100
        self.preview_mode_started = False  # skip the frame-grab loop
        self.estop_event = threading.Event()
        self._fs = Mock()
        self.sig_message = Mock()


def test_preview_worker_finished_emits_exactly_once_normal(qtbot) -> None:
    """PreviewWorker.run with preview_mode_started=False completes
    normally and emits finished exactly once."""
    bundle = _make_bundle()
    shell = _PreviewShell()
    hw = Mock()
    worker = PreviewWorker(bundle, hw, shell)

    finished_count: list[int] = []
    worker.finished.connect(lambda: finished_count.append(1))

    worker.run()

    assert len(finished_count) == 1, "finished must emit exactly once on normal exit"


def test_preview_worker_finished_emits_exactly_once_estop(qtbot) -> None:
    """PreviewWorker.run with estop_event set breaks out of the loop and
    emits finished exactly once."""
    bundle = _make_bundle()
    shell = _PreviewShell()
    shell.preview_mode_started = True
    shell.estop_event.set()
    hw = Mock()
    worker = PreviewWorker(bundle, hw, shell)

    finished_count: list[int] = []
    worker.finished.connect(lambda: finished_count.append(1))

    worker.run()

    assert len(finished_count) == 1, "finished must emit exactly once on E-stop break"


def test_preview_worker_finished_emits_exactly_once_exception(qtbot) -> None:
    """PreviewWorker.run with a camera.arm() exception catches it, emits
    sig_message, and still emits finished exactly once from finally."""
    bundle = _make_bundle()
    shell = _PreviewShell()
    hw = Mock()
    worker = PreviewWorker(bundle, hw, shell)
    worker.camera.arm = Mock(side_effect=RuntimeError("camera fault"))

    finished_count: list[int] = []
    worker.finished.connect(lambda: finished_count.append(1))

    worker.run()

    shell.sig_message.emit.assert_called_once()
    assert "Preview acquisition failed" in shell.sig_message.emit.call_args[0][0]
    assert len(finished_count) == 1, "finished must emit exactly once on exception"


def test_preview_worker_never_accesses_ui_widgets(qtbot) -> None:
    """PreviewWorker.run must NOT access any self._shell.ui.* widget beyond
    the exposure-time spinbox read at arm time (which happens on the
    worker thread but is a read of a cached value, not a mutation). The
    worker never mutates widgets — all cross-thread UI effects flow
    through queued signals (AGENTS.md §11).

    Verified by giving the shell a Mock ui and asserting no ui.* attribute
    other than doubleSpinBox_cameraExposureTime was accessed after run()."""
    bundle = _make_bundle()
    shell = _PreviewShell()
    hw = Mock()
    worker = PreviewWorker(bundle, hw, shell)

    worker.run()

    # The only permitted ui.* access is doubleSpinBox_cameraExposureTime
    # (the exposure-time read at arm time). No other widget should be
    # touched.
    ui_mock = shell.ui
    accessed_children = [name for name, child in ui_mock._mock_children.items()]
    # doubleSpinBox_cameraExposureTime is accessed via .value() — that's
    # the one permitted read. No other widget attributes should appear.
    for child_name in accessed_children:
        assert child_name == "doubleSpinBox_cameraExposureTime", (
            f"PreviewWorker must not access ui.{child_name} — "
            f"only doubleSpinBox_cameraExposureTime is permitted (AGENTS.md §11)"
        )
