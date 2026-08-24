"""Behavior tests for the ChannelMap wiring in lightsheet/hal/real/siggen.py.

These tests exercise the four ``np.stack((...))`` channel-ordering sites in
``SigGen`` (``update_all`` / ``update_galvos`` / ``update_etls`` /
``create_scanner``) through the config-driven ``ChannelMap`` mechanism built in
``lightsheet.channel_map`` (Phase 5 plan 02).

Coverage (per the plan's ``<behavior>`` block):

1. ``SigGen.__init__`` with ``config.ini``'s default ``Galvo Left Right Swap``
   value (``False``) sets ``self.galvo_left_right_swap is False`` and
   ``self.channel_map.galvo_left_right_swap is False``.
2. With ``galvo_left_right_swap=False`` (default), ``update_galvos(1.0, 2.0)``
   produces the identical ``np.stack`` array today's pre-mechanism code
   produces for the same inputs — ``np.stack((np.array([2.0]),
   np.array([1.0])))`` (right first, left second, matching the pre-mechanism
   literal order) — proving the wiring is behavior-preserving by default.
3. A ``SigGen`` with ``channel_map.galvo_left_right_swap=True`` (constructed
   directly, bypassing config, to unit-test the swap in isolation) produces
   the swapped stack order for the same call.
4. ``update_galvos(15.0, -15.0)`` (both out of the +/-10 V range) results in a
   captured write array where both values are clamped to ``[-10.0, 10.0]``
   regardless of the swap flag (the per-channel clamp is unconditional,
   threat T-05-12 mitigation).

The DAQ write is captured by patching ``nidaqmx.Task`` in the siggen module
namespace with a fake ``Task`` whose ``write`` records its first argument on
the instance — the same capture pattern used by ``test_daqlaser.py``'s
conftest-stub path, but here we replace the raising stub with a recording
stub so the write actually reaches the assertion. ``SigGen`` is constructed
with a ``MockCamera`` (the ``SigGen(camera)`` dependency only stores the
reference; ``cfg_load_ini`` reads no camera state).

This is a BEHAVIOR test (AGENTS.md §5) — it executes the real ``SigGen``
method bodies and asserts on the runtime write payload.
"""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pytest

from lightsheet.hal import MockCamera, SigGen
from lightsheet.hal.real import siggen as siggen_module


class _RecordingTask:
    """Fake nidaqmx.Task that records the array passed to ``write``.

    Mirrors the surface ``SigGen.update_galvos`` / ``update_etls`` /
    ``update_all`` touch: ``__enter__`` / ``__exit__`` (the ``with`` block),
    ``ao_channels.add_ao_voltage_chan`` (no-op), and ``write`` (records the
    first positional arg on ``self.written``). Does NOT raise — the real
    conftest stub raises to exercise the typed-except path; here we want the
    write to succeed so the recorded array can be asserted on.
    """

    written: np.ndarray | None = None

    def __init__(self, *args: object, **kwargs: object) -> None:
        self.written = None
        # Re-bind ao_channels/timing so attribute chains don't blow up.
        self.ao_channels = _AoChannels()
        self.timing = _Timing()

    def __enter__(self) -> _RecordingTask:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def write(self, data: np.ndarray, auto_start: bool = True) -> int:
        self.written = np.array(data)
        return 0

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None

    def close(self) -> None:
        return None


class _AoChannels:
    def add_ao_voltage_chan(self, *args: object, **kwargs: object) -> None:
        return None

    def add_do_chan(self, *args: object, **kwargs: object) -> None:
        return None


class _Timing:
    def cfg_samp_clk_timing(self, *args: object, **kwargs: object) -> None:
        return None


class _Triggers:
    def __init__(self) -> None:
        self.start_trigger = _StartTrigger()


class _StartTrigger:
    def cfg_dig_edge_start_trig(self, *args: object, **kwargs: object) -> None:
        return None


def _make_siggen() -> SigGen:
    """Construct a real ``SigGen(MockCamera())``.

    ``SigGen.__init__`` only stores the camera reference and calls
    ``cfg_load_ini``; no camera state is read at construction time, so a
    ``MockCamera`` is sufficient. The conftest nidaqmx stub lets the module
    import (``from nidaqmx.constants import ...``) without the driver
    runtime; ``Task()`` is never called during construction.
    """
    return SigGen(MockCamera())


def test_default_swap_flag_is_false() -> None:
    """``SigGen.__init__`` with ``config.ini``'s default ``Galvo Left Right
    Swap = False`` sets ``self.galvo_left_right_swap is False`` and
    ``self.channel_map.galvo_left_right_swap is False``."""
    sg = _make_siggen()
    assert sg.galvo_left_right_swap is False
    assert sg.channel_map.galvo_left_right_swap is False


def test_update_galvos_default_order_is_right_then_left() -> None:
    """With ``galvo_left_right_swap=False`` (default), ``update_galvos(1.0,
    2.0)`` writes ``np.stack((np.array([2.0]), np.array([1.0])))`` — right
    first, left second — matching the pre-mechanism literal stack order
    exactly (behavior-preserving by default)."""
    sg = _make_siggen()
    assert sg.galvo_left_right_swap is False
    with patch.object(siggen_module, "nidaqmx") as fake_nidaqmx:
        fake_nidaqmx.Task = _RecordingTask
        sg.update_galvos(left_galvo=1.0, right_galvo=2.0)
    # The recording task is created inside the with block; pull the written
    # array off the most recently constructed instance by re-patching and
    # capturing the instance directly.
    captured: list[np.ndarray] = []

    class _CaptureTask(_RecordingTask):
        def __init__(self, *a: object, **k: object) -> None:
            super().__init__(*a, **k)
            captured.append(self)

    with patch.object(siggen_module, "nidaqmx") as fake_nidaqmx2:
        fake_nidaqmx2.Task = _CaptureTask
        sg.update_galvos(left_galvo=1.0, right_galvo=2.0)
    assert len(captured) == 1
    expected = np.stack((np.array([2.0]), np.array([1.0])))
    np.testing.assert_array_equal(captured[0].written, expected)


def test_update_galvos_swapped_order_when_swap_true() -> None:
    """A ``SigGen`` with ``channel_map.galvo_left_right_swap=True``
    (constructed directly, bypassing config) produces the swapped stack
    order for ``update_galvos(1.0, 2.0)`` — ``np.stack((np.array([1.0]),
    np.array([2.0])))`` (left first, right second)."""
    sg = _make_siggen()
    # Bypass config to unit-test the swap in isolation.
    from lightsheet.channel_map import ChannelMap

    sg.channel_map = ChannelMap(galvo_left_right_swap=True)
    sg.galvo_left_right_swap = True
    captured: list[np.ndarray] = []

    class _CaptureTask(_RecordingTask):
        def __init__(self, *a: object, **k: object) -> None:
            super().__init__(*a, **k)
            captured.append(self)

    with patch.object(siggen_module, "nidaqmx") as fake_nidaqmx:
        fake_nidaqmx.Task = _CaptureTask
        sg.update_galvos(left_galvo=1.0, right_galvo=2.0)
    assert len(captured) == 1
    expected = np.stack((np.array([1.0]), np.array([2.0])))
    np.testing.assert_array_equal(captured[0].written, expected)


@pytest.mark.parametrize("swap", [False, True])
def test_update_galvos_clamps_out_of_range_regardless_of_swap(swap: bool) -> None:
    """``update_galvos(15.0, -15.0)`` (both out of the +/-10 V range) results
    in a captured write array where both values are clamped to
    ``[-10.0, 10.0]`` regardless of the swap flag (threat T-05-12)."""
    sg = _make_siggen()
    from lightsheet.channel_map import ChannelMap

    sg.channel_map = ChannelMap(galvo_left_right_swap=swap)
    sg.galvo_left_right_swap = swap
    captured: list[np.ndarray] = []

    class _CaptureTask(_RecordingTask):
        def __init__(self, *a: object, **k: object) -> None:
            super().__init__(*a, **k)
            captured.append(self)

    with patch.object(siggen_module, "nidaqmx") as fake_nidaqmx:
        fake_nidaqmx.Task = _CaptureTask
        sg.update_galvos(left_galvo=15.0, right_galvo=-15.0)
    assert len(captured) == 1
    written = captured[0].written
    # Both channels must be within [-10.0, 10.0] regardless of order.
    flat = written.flatten()
    assert flat.min() >= -10.0
    assert flat.max() <= 10.0
    # The two clamped values are 10.0 and -10.0 (in some order).
    assert set(flat.tolist()) == {10.0, -10.0}


# --------------------------------------------------------------------------- #
# Scanner lifecycle guards: start_scanner / monitor_scanner / stop_scanner /
# delete_scanner each gate on `task_galvo_etl is not None and task_camera is
# not None`. Both the None (no-op) and non-None (delegating) branches must be
# exercised so the guard's two arcs are both covered.
# --------------------------------------------------------------------------- #
class _StubTask:
    """Minimal task stub recording the lifecycle calls invoked on it."""

    def __init__(self, name: str, calls: list[str]) -> None:
        self.name = name
        self._calls = calls

    def start(self) -> None:
        self._calls.append(f"{self.name}.start")

    def wait_until_done(self) -> None:
        self._calls.append(f"{self.name}.wait_until_done")

    def stop(self) -> None:
        self._calls.append(f"{self.name}.stop")

    def close(self) -> None:
        self._calls.append(f"{self.name}.close")


def test_scanner_lifecycle_noop_when_tasks_are_none() -> None:
    """When both tasks are None (the post-construct state), the four
    lifecycle methods are no-ops — the guard's False arc."""
    sg = _make_siggen()
    assert sg.task_galvo_etl is None
    assert sg.task_camera is None
    # None of these should raise or set the error surface.
    sg.start_scanner()
    sg.monitor_scanner()
    sg.stop_scanner()
    sg.delete_scanner()
    assert sg.error == 0
    assert sg.task_galvo_etl is None
    assert sg.task_camera is None


def test_scanner_lifecycle_delegates_when_tasks_present() -> None:
    """When both tasks are non-None, the four lifecycle methods delegate to
    the underlying task objects — the guard's True arc. delete_scanner
    additionally nulls the handles."""
    sg = _make_siggen()
    calls: list[str] = []
    sg.task_galvo_etl = _StubTask("galvo_etl", calls)
    sg.task_camera = _StubTask("camera", calls)

    sg.start_scanner()
    sg.monitor_scanner()
    sg.stop_scanner()
    sg.delete_scanner()

    # start_scanner starts camera first (master last), then galvo_etl.
    assert calls[0] == "camera.start"
    assert calls[1] == "galvo_etl.start"
    # monitor_scanner waits on camera then galvo_etl.
    assert "camera.wait_until_done" in calls
    assert "galvo_etl.wait_until_done" in calls
    # stop_scanner stops both.
    assert "camera.stop" in calls
    assert "galvo_etl.stop" in calls
    # delete_scanner closes both and nulls the handles.
    assert "camera.close" in calls
    assert "galvo_etl.close" in calls
    assert sg.task_galvo_etl is None
    assert sg.task_camera is None


# --------------------------------------------------------------------------- #
# compute_scan_waveforms: the shutter_mode dispatch (Lightsheet / Rolling /
# Global / unsupported) and the diag flag inside Rolling each contribute
# branch arcs that line coverage does not close. Each test asserts a concrete
# runtime postcondition (a computed waveform array's shape / a raised
# exception), not merely that the method returned.
#
# A small ``ysize`` is used so the Rolling/Global readout-time asserts
# (galvo_pre + reset + post >= camera_data_readout_time) hold against the
# config.ini defaults (pre=1ms, reset=25ms, post=1ms → 27ms; with ysize=100
# and line_time≈48.8us the readout is ~2.4ms, well under 27ms).
# --------------------------------------------------------------------------- #
def _make_siggen_small_camera(shutter_mode: str) -> SigGen:
    """Build a SigGen whose MockCamera has a small ysize so the
    Rolling/Global readout-time asserts hold, and the requested shutter_mode."""
    sg = _make_siggen()
    sg.camera.ysize = 100
    sg.camera.xsize = 256
    sg.camera.line_time = 48.80 * 1e-6
    sg.camera.exposure_time = 0.005  # 5 ms
    sg.camera.shutter_mode = shutter_mode
    sg.camera.lightsheet_exposed_lines = 16
    return sg


def test_compute_scan_waveforms_lightsheet_mode() -> None:
    """In Lightsheet shutter mode, galvo_scan_time is derived from the
    camera line time and FOV, and the camera waveform is a squarewave of
    the right sample length."""
    sg = _make_siggen_small_camera("Lightsheet")
    sg.compute_scan_waveforms()
    expected_scan_time = sg.camera.line_time * sg.camera.ysize
    assert sg.galvo_scan_time == pytest.approx(expected_scan_time)
    # All four waveforms are 1-D numpy arrays of equal length.
    assert sg.waveform_camera.ndim == 1
    assert sg.waveform_galvo_left.shape == sg.waveform_camera.shape
    assert sg.waveform_galvo_right.shape == sg.waveform_camera.shape
    assert sg.waveform_etl_left.shape == sg.waveform_camera.shape
    assert sg.waveform_etl_right.shape == sg.waveform_camera.shape
    # Metadata records the shutter mode actually used.
    assert sg.waveform_metadata["Camera Shutter Mode"] == "Lightsheet"


def test_compute_scan_waveforms_rolling_diag_on() -> None:
    """In Rolling shutter mode with diag=True, galvo_scan_time is set to
    the camera exposure_time (the diag branch prints and uses a simpler
    readout-time formula)."""
    sg = _make_siggen_small_camera("Rolling")
    sg.diag = True
    sg.compute_scan_waveforms()
    assert sg.galvo_scan_time == pytest.approx(sg.camera.exposure_time)
    assert sg.waveform_metadata["Camera Shutter Mode"] == "Rolling"
    assert sg.waveform_camera.ndim == 1


def test_compute_scan_waveforms_rolling_diag_off() -> None:
    """In Rolling shutter mode with diag=False (the production else
    branch), galvo_scan_time is exposure_time plus half a frame of line
    times."""
    sg = _make_siggen_small_camera("Rolling")
    sg.diag = False
    sg.compute_scan_waveforms()
    expected = sg.camera.exposure_time + (sg.camera.line_time * 0.5 * sg.camera.ysize)
    assert sg.galvo_scan_time == pytest.approx(expected)
    assert sg.waveform_metadata["Camera Shutter Mode"] == "Rolling"


def test_compute_scan_waveforms_global_mode() -> None:
    """In Global shutter mode, galvo_scan_time equals the exposure time
    and the camera active time equals the galvo scan time."""
    sg = _make_siggen_small_camera("Global")
    sg.compute_scan_waveforms()
    assert sg.galvo_scan_time == pytest.approx(sg.camera.exposure_time)
    assert sg.waveform_metadata["Camera Shutter Mode"] == "Global"
    assert sg.waveform_camera.ndim == 1


def test_compute_scan_waveforms_unsupported_mode_raises() -> None:
    """An unsupported shutter mode raises Exception with the documented
    message — the else branch of the shutter_mode dispatch."""
    sg = _make_siggen_small_camera("NotARealShutterMode")
    with pytest.raises(Exception, match="camera shutter mode not supported"):
        sg.compute_scan_waveforms()


# --------------------------------------------------------------------------- #
# update_all / update_etls: the remaining two ChannelMap wiring sites not
# yet exercised. Each builds an np.stack of clamped setpoints and writes it
# through a nidaqmx.Task. The recording-task capture pattern verifies both
# the channel ordering (order_galvos for update_all) and the per-channel
# clamps (clamp_galvo / clamp_etl).
# --------------------------------------------------------------------------- #
def test_update_all_writes_clamped_swapped_stack() -> None:
    """update_all builds a 4-channel stack (galvo_first, galvo_second,
    etl_left, etl_right) with per-channel clamps applied. With the default
    swap=False, order_galvos(right, left) returns (right, left) unchanged."""
    sg = _make_siggen()
    captured: list[np.ndarray] = []

    class _CaptureTask(_RecordingTask):
        def __init__(self, *a: object, **k: object) -> None:
            super().__init__(*a, **k)
            captured.append(self)

    with patch.object(siggen_module, "nidaqmx") as fake_nidaqmx:
        fake_nidaqmx.Task = _CaptureTask
        sg.update_all(left_galvo=15.0, right_galvo=-15.0, left_etl=7.0, right_etl=-1.0)
    assert len(captured) == 1
    written = captured[0].written.flatten()
    # galvo channels clamped to ±10, etl channels clamped to [0, 5].
    # With swap=False: order_galvos(right=-15, left=15) → (-15, 15).
    # galvo_first=-15 → clamp → -10; galvo_second=15 → clamp → 10.
    # etl_left=7 → clamp → 5; etl_right=-1 → clamp → 0.
    assert written.tolist() == [-10.0, 10.0, 5.0, 0.0]


def test_update_etls_writes_clamped_pair() -> None:
    """update_etls builds a 2-channel stack (etl_left, etl_right) with the
    ETL clamp applied (no galvo swap — ETL channels are not swapped)."""
    sg = _make_siggen()
    captured: list[np.ndarray] = []

    class _CaptureTask(_RecordingTask):
        def __init__(self, *a: object, **k: object) -> None:
            super().__init__(*a, **k)
            captured.append(self)

    with patch.object(siggen_module, "nidaqmx") as fake_nidaqmx:
        fake_nidaqmx.Task = _CaptureTask
        sg.update_etls(left_etl=7.0, right_etl=-1.0)
    assert len(captured) == 1
    written = captured[0].written.flatten()
    # etl_left=7 → clamp to 5; etl_right=-1 → clamp to 0.
    assert written.tolist() == [5.0, 0.0]


def test_update_galvos_sets_error_surface_on_task_failure() -> None:
    """When nidaqmx.Task raises inside update_galvos, the except handler
    sets self.error=1 and self.error_message — the HAL error-surface
    contract (AGENTS.md §10)."""
    sg = _make_siggen()

    class _FailingTask:
        def __init__(self, *a: object, **k: object) -> None:
            raise RuntimeError("DAQ unavailable")

        def __enter__(self) -> _FailingTask:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

    with patch.object(siggen_module, "nidaqmx") as fake_nidaqmx:
        fake_nidaqmx.Task = _FailingTask
        sg.update_galvos(left_galvo=1.0, right_galvo=2.0)
    assert sg.error == 1
    assert sg.error_message == "update_galvos error"


# --------------------------------------------------------------------------- #
# create_scanner: the ChannelMap wiring (order_galvos + np.clip + np.stack)
# runs BEFORE the pragma'd nidaqmx.Task probe block. With the conftest stub
# making Task() raise, the except handler fires and nulls the task handles —
# covering the wiring lines and the error-path cleanup. A separate test
# verifies the wiring produces the expected clamped stack by patching Task
# with a recording stub that captures the waveform before raising on a
# second Task call.
# --------------------------------------------------------------------------- #
def test_create_scanner_wiring_clamps_and_orders_waveforms() -> None:
    """create_scanner's pre-try wiring applies order_galvos + np.clip to
    the galvo waveforms and np.clip to the ETL waveforms, then stacks them.
    With a recording Task stub, the written galvo_etl_waveforms array is
    captured and its clamp bounds verified."""
    sg = _make_siggen_small_camera("Lightsheet")
    sg.compute_scan_waveforms()
    # Force out-of-range galvo amplitudes so the clip is observable.
    sg.waveform_galvo_left = np.full(10, 15.0)
    sg.waveform_galvo_right = np.full(10, -15.0)
    sg.waveform_etl_left = np.full(10, 7.0)
    sg.waveform_etl_right = np.full(10, -1.0)

    captured: list[np.ndarray] = []

    class _CaptureTask:
        def __init__(self, *a: object, **k: object) -> None:
            self.ao_channels = _AoChannels()
            self.do_channels = _AoChannels()
            self.timing = _Timing()
            self.triggers = _Triggers()
            captured.append(self)

        def __enter__(self) -> _CaptureTask:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

        def write(self, data: np.ndarray, auto_start: bool = False) -> int:
            self.written = np.array(data)
            return 0

        def start(self) -> None:
            return None

    with patch.object(siggen_module, "nidaqmx") as fake_nidaqmx:
        fake_nidaqmx.Task = _CaptureTask
        fake_nidaqmx.constants = siggen_module.nidaqmx.constants
        sg.create_scanner()
    # Two Task instances created (galvo_etl + camera); the galvo_etl
    # waveform is the one written with the 4-channel stack.
    galvo_writes = [t for t in captured if hasattr(t, "written")]
    assert len(galvo_writes) >= 1
    stacked = galvo_writes[0].written
    # Shape is (4, 10): 4 channels, 10 samples each.
    assert stacked.shape == (4, 10)
    # Galvo channels (rows 0,1) clamped to ±10.
    assert stacked[0].min() >= -10.0 and stacked[0].max() <= 10.0
    assert stacked[1].min() >= -10.0 and stacked[1].max() <= 10.0
    # ETL channels (rows 2,3) clamped to [0, 5].
    assert stacked[2].min() >= 0.0 and stacked[2].max() <= 5.0
    assert stacked[3].min() >= 0.0 and stacked[3].max() <= 5.0


def test_create_scanner_error_path_nulls_tasks() -> None:
    """When nidaqmx.Task raises inside create_scanner's try block, the
    except handler nulls both task handles and sets the error surface."""
    sg = _make_siggen_small_camera("Lightsheet")
    sg.compute_scan_waveforms()

    class _FailingTask:
        def __init__(self, *a: object, **k: object) -> None:
            raise RuntimeError("DAQ unavailable")

        def __enter__(self) -> _FailingTask:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

    with patch.object(siggen_module, "nidaqmx") as fake_nidaqmx:
        fake_nidaqmx.Task = _FailingTask
        fake_nidaqmx.constants = siggen_module.nidaqmx.constants
        sg.create_scanner()
    assert sg.task_galvo_etl is None
    assert sg.task_camera is None
    assert sg.error == 1
    assert sg.error_message == "create_scan error"
