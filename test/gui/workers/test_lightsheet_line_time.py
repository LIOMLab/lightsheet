"""Behavior tests for adaptive Lightsheet line-time conversion and the
changed-only DAQ waveform refresh.

``AdaptiveCommand.exposure_s`` is the total per-plane integration time in
seconds. In Lightsheet shutter mode it maps to a per-line time via
``_lightsheet_line_time_from_exposure(exposure_s,
camera.lightsheet_exposed_lines)`` — the exposed-line count is always the
divisor source and is never varied by adaptive control.

The worker-level tests use the minimal shell stand-in pattern from
``test_stack_adaptive.py`` and assert on call order and runtime
postconditions, never on static source.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import Mock

import pytest
from pytestqt.qtbot import QtBot

pytest.importorskip("PySide6")

from lightsheet.adaptive.types import AdaptiveCommand
from lightsheet.gui.workers import StackWorker
from lightsheet.gui.workers.stack_adaptive import (
    _lightsheet_line_time_from_exposure,
)

# -- pure conversion helper ------------------------------------------------


def test_lightsheet_line_time_from_exposure_exact_mapping() -> None:
    """The canonical case: 80 ms total integration over 16 exposed lines
    is 5 ms per line. The divisor is camera.lightsheet_exposed_lines."""
    assert _lightsheet_line_time_from_exposure(0.080, 16) == pytest.approx(0.005)


def test_lightsheet_line_time_from_exposure_varies_with_exposed_lines() -> None:
    """Same total exposure over 20 exposed lines yields 4 ms per line —
    the exposed-line count is the divisor, not a fixed constant."""
    assert _lightsheet_line_time_from_exposure(0.080, 20) == pytest.approx(0.004)


@pytest.mark.parametrize(
    "exposure_s",
    [0.0, -0.001, float("nan"), float("inf"), -float("inf")],
)
def test_lightsheet_line_time_from_exposure_rejects_bad_exposure(
    exposure_s: float,
) -> None:
    """Non-finite or non-positive total exposure would produce an unsafe
    acquisition timing — rejected loudly with ValueError."""
    with pytest.raises(ValueError, match="exposure_s"):
        _lightsheet_line_time_from_exposure(exposure_s, 16)


@pytest.mark.parametrize("exposed_lines", [0, -4])
def test_lightsheet_line_time_from_exposure_rejects_bad_line_count(
    exposed_lines: int,
) -> None:
    """A non-positive exposed-line divisor is rejected loudly."""
    with pytest.raises(ValueError, match="exposed_lines"):
        _lightsheet_line_time_from_exposure(0.080, exposed_lines)


# -- worker application -----------------------------------------------------


def _make_worker(qtbot: QtBot, shutter_mode: str = "Lightsheet") -> StackWorker:
    """Build a real StackWorker on the mock bundle with a minimal shell."""
    from test.helpers.factories import make_bundle

    bundle = make_bundle()
    shell = Mock()
    shell.lasers = bundle.lasers
    shell.saving_allowed = False
    shell._fs = Mock()
    shell.sig_message = Mock()
    shell.reconstructed_frame = None
    shell.reconstructed_frames = {}

    worker = StackWorker(bundle, Mock(), shell, multi_channel=False)
    worker.camera.shutter_mode = shutter_mode
    return worker


def _ordered_calls(worker: StackWorker) -> list[str]:
    """Instrument the camera/siggen/acquire path with call-order recorders."""
    calls: list[str] = []

    camera = worker.camera
    orig_set_lightsheet_mode = camera.set_lightsheet_mode
    orig_set_exposure_time = camera.set_exposure_time

    def _set_lightsheet_mode() -> None:
        calls.append("set_lightsheet_mode")
        orig_set_lightsheet_mode()

    def _set_exposure_time(ms: int) -> None:
        calls.append(f"set_exposure_time:{ms}")
        orig_set_exposure_time(ms)

    camera.set_lightsheet_mode = _set_lightsheet_mode  # type: ignore[assignment]  # ty: ignore[invalid-assignment]
    camera.set_exposure_time = _set_exposure_time  # type: ignore[assignment]  # ty: ignore[invalid-assignment]
    worker.siggen.compute_scan_waveforms = (  # type: ignore[assignment]  # ty: ignore[invalid-assignment]
        lambda: calls.append("compute_scan_waveforms")
    )
    worker.acquire_scan = (  # type: ignore[assignment]  # ty: ignore[invalid-assignment]
        lambda: calls.append("acquire_scan") or True
    )
    return calls


def test_lightsheet_apply_order_and_changed_only_recompute(qtbot: QtBot) -> None:
    """A changed applied line time triggers exactly one waveform recompute,
    ordered set_lightsheet_mode -> compute_scan_waveforms -> acquire_scan."""
    worker = _make_worker(qtbot)
    worker.camera.lightsheet_exposed_lines = 16
    worker.camera.lightsheet_line_time = 0.001
    worker.camera.line_time = 0.001
    calls = _ordered_calls(worker)

    emitted: list[Any] = []
    worker.sig_applied_state.connect(emitted.append)

    cmd = AdaptiveCommand.fixed(exposure_s=0.080, laser1_mw=0.0, laser2_mw=0.0)
    worker._apply_adaptive_command(cmd)
    worker.acquire_scan()

    assert calls == [
        "set_lightsheet_mode",
        "compute_scan_waveforms",
        "acquire_scan",
    ]
    assert worker.camera.line_time == pytest.approx(0.005)
    assert worker.camera.lightsheet_line_time == pytest.approx(0.005)
    # The effective mock exposure tracks the applied line time.
    assert worker.camera.exposure_time == pytest.approx(0.080)
    # The applied snapshot carries the line-time readback to the model.
    assert emitted[-1].lightsheet_line_time_s == pytest.approx(0.005)


def test_unchanged_line_time_does_not_recompute_waveforms(qtbot: QtBot) -> None:
    """When the applied line time is already the requested value, the
    Lightsheet mode is still applied but no second waveform buffer is
    allocated."""
    worker = _make_worker(qtbot)
    worker.camera.lightsheet_exposed_lines = 16
    worker.camera.lightsheet_line_time = 0.005
    worker.camera.line_time = 0.005
    calls = _ordered_calls(worker)

    cmd = AdaptiveCommand.fixed(exposure_s=0.080, laser1_mw=0.0, laser2_mw=0.0)
    worker._apply_adaptive_command(cmd)
    worker.acquire_scan()

    assert calls == ["set_lightsheet_mode", "acquire_scan"]


def test_rolling_mode_still_uses_ms_exposure_register(qtbot: QtBot) -> None:
    """Rolling-shutter regression: the adaptive exposure is written to the
    delay/exposure register in whole milliseconds via set_exposure_time,
    the Lightsheet line-time path is untouched, and no waveform recompute
    runs."""
    worker = _make_worker(qtbot, shutter_mode="Rolling")
    worker.camera.lightsheet_line_time = 0.001
    worker.camera.line_time = 0.0005
    calls = _ordered_calls(worker)

    emitted: list[Any] = []
    worker.sig_applied_state.connect(emitted.append)

    cmd = AdaptiveCommand.fixed(exposure_s=0.05, laser1_mw=0.0, laser2_mw=0.0)
    worker._apply_adaptive_command(cmd)
    worker.acquire_scan()

    assert calls == ["set_exposure_time:50", "acquire_scan"]
    assert worker.camera.exposure_time == pytest.approx(0.05)
    assert worker.camera.lightsheet_line_time == pytest.approx(0.001)
    assert worker.camera.line_time == pytest.approx(0.0005)
    # No Lightsheet line-time readback is published outside Lightsheet mode.
    assert emitted[-1].lightsheet_line_time_s is None
