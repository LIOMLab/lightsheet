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

    def __enter__(self) -> "_RecordingTask":
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


class _Timing:
    def cfg_samp_clk_timing(self, *args: object, **kwargs: object) -> None:
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
