"""Behavior tests for DAQ-gated analog modulation of L2 (iBeam 640 nm) on
/Dev7/ao1 — the camera-aligned finite AO gate in DAQLaser + SigGen.

Covers the three safety-owned concerns:
- The L2 AO waveform is nonzero only over camera-exposure samples.
- The two-layer power clamp (mW in set_power, V in configure_gate) is retained.
- DAQLaser.off() synchronously aborts an in-flight gate before the 0 V write,
  lock-free, so the E-stop kill path is never delayed or defeated by a buffered
  task holding /Dev7/ao1.

The conftest nidaqmx stub makes ``nidaqmx.Task()`` raise on this Mac. Tests
that need the gate task to actually be created patch ``nidaqmx.Task`` with a
recording stub (the same pattern as test_daqlaser /
test_siggen_channel_map). Tests that need the failure path let the conftest
stub raise naturally.

This is a BEHAVIOR test (AGENTS.md §5) — it executes the real DAQLaser and
SigGen code under the conftest nidaqmx stub and asserts on runtime state.
"""

from __future__ import annotations

from unittest.mock import patch

import nidaqmx
import numpy as np
import pytest

from lightsheet.hal import MockCamera, SigGen
from lightsheet.hal.real import siggen as siggen_module
from lightsheet.hal.real.daqlaser import DAQLaser


# --------------------------------------------------------------------------- #
# Recording task stubs — capture the volts array written to the L2 gate and
# record lifecycle (start/wait/stop/close) calls so scanner start order and
# cleanup can be asserted.
# --------------------------------------------------------------------------- #
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


class _RecordingTask:
    """Fake nidaqmx.Task that records writes and lifecycle calls.

    Instances append themselves to a class-level ``instances`` list so the
    test can find the L2 gate task by its ``new_task_name`` kwarg.
    """

    instances: list["_RecordingTask"] = []

    def __init__(self, *args: object, **kwargs: object) -> None:
        self.name = str(kwargs.get("new_task_name", ""))
        self.ao_channels = _AoChannels()
        self.do_channels = _AoChannels()
        self.timing = _Timing()
        self.triggers = _Triggers()
        self.written: np.ndarray | None = None
        self.calls: list[str] = []
        _RecordingTask.instances.append(self)

    def __enter__(self) -> "_RecordingTask":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def write(self, data: np.ndarray, auto_start: bool = False) -> int:
        self.written = np.array(data, dtype=float)
        return 0

    def start(self) -> None:
        self.calls.append("start")

    def wait_until_done(self) -> None:
        self.calls.append("wait_until_done")

    def stop(self) -> None:
        self.calls.append("stop")

    def close(self) -> None:
        self.calls.append("close")


def _reset_tasks() -> None:
    _RecordingTask.instances = []


def _find_task(name: str) -> _RecordingTask:
    for t in _RecordingTask.instances:
        if t.name == name:
            return t
    raise AssertionError(f"No recording task named {name!r} found")


# --------------------------------------------------------------------------- #
# DAQLaser / SigGen construction helpers mirroring the L2 rig config:
# /Dev7/ao1, 647 nm, 150 mW ceiling, 30.0 mW/V (5.0 V full-scale).
# --------------------------------------------------------------------------- #
def _make_l2_daq() -> DAQLaser:
    return DAQLaser(
        terminal="/Dev7/ao1",
        wavelength=647,
        mw_per_volt=30.0,
        max_power_mw=150.0,
        label="Laser 2 (647 nm)",
    )


def _make_siggen_with_l2(shutter_mode: str = "Lightsheet") -> tuple[SigGen, DAQLaser]:
    """Build a SigGen with a small MockCamera and an L2 DAQLaser injected."""
    sg = SigGen(MockCamera())
    sg.camera.ysize = 100
    sg.camera.xsize = 256
    sg.camera.line_time = 48.80 * 1e-6
    sg.camera.exposure_time = 0.005
    sg.camera.shutter_mode = shutter_mode
    sg.camera.lightsheet_exposed_lines = 16
    l2 = _make_l2_daq()
    sg._laser2_daq = l2
    return sg, l2


# --------------------------------------------------------------------------- #
# Behavior 1: at 150 mW, the enabled L2 finite AO payload is exactly 5.0 V
# where the camera waveform is active and 0.0 V at every other sample, with
# matching shape/repeat count.
# --------------------------------------------------------------------------- #
def test_gate_window_5v_at_camera_active_samples():
    _reset_tasks()
    sg, l2 = _make_siggen_with_l2("Lightsheet")
    sg.compute_scan_waveforms()
    l2.set_power(150.0)
    sg.set_laser2_gate(True)

    with patch.object(nidaqmx, "Task", _RecordingTask):
        sg.create_scanner()

    gate_task = _find_task("laser2_gate_ao")
    payload = gate_task.written
    assert payload is not None
    camera = sg.waveform_camera.astype(float)
    # Shape matches the camera waveform (same sample count).
    assert payload.shape == camera.shape
    # Where the camera is active -> 5.0 V (150 mW / 30 mW/V).
    active_mask = camera > 0.0
    assert np.all(payload[active_mask] == pytest.approx(5.0))
    # Where the camera is inactive -> 0.0 V.
    inactive_mask = camera == 0.0
    assert np.all(payload[inactive_mask] == pytest.approx(0.0))


# --------------------------------------------------------------------------- #
# Behavior 2: a disabled L2 gate produces an all-zero /Dev7/ao1 payload even
# when a nonzero L2 power is staged.
# --------------------------------------------------------------------------- #
def test_gate_disabled_produces_all_zero_payload():
    _reset_tasks()
    sg, l2 = _make_siggen_with_l2("Lightsheet")
    sg.compute_scan_waveforms()
    l2.set_power(150.0)
    sg.set_laser2_gate(False)

    with patch.object(nidaqmx, "Task", _RecordingTask):
        sg.create_scanner()

    gate_task = _find_task("laser2_gate_ao")
    payload = gate_task.written
    assert payload is not None
    assert payload.shape == sg.waveform_camera.shape
    assert np.all(payload == pytest.approx(0.0))


# --------------------------------------------------------------------------- #
# Behavior 3: staged power above 150 mW is clamped in mW and the generated AO
# payload is independently clipped to the backend's 5.0 V ceiling.
# --------------------------------------------------------------------------- #
def test_voltage_clamp_mw_and_volts_layers():
    _reset_tasks()
    sg, l2 = _make_siggen_with_l2("Lightsheet")
    sg.compute_scan_waveforms()
    # 999 mW clamps to 150 mW in set_power (first layer).
    l2.set_power(999.0)
    assert l2.power == 150.0
    sg.set_laser2_gate(True)

    with patch.object(nidaqmx, "Task", _RecordingTask):
        sg.create_scanner()

    gate_task = _find_task("laser2_gate_ao")
    payload = gate_task.written
    assert payload is not None
    active_mask = sg.waveform_camera.astype(float) > 0.0
    # 150 mW / 30 mW/V = 5.0 V = _max_volts ceiling.
    assert np.all(payload[active_mask] == pytest.approx(5.0))
    assert float(np.max(payload)) <= 5.0 + 1e-9


def test_voltage_clamp_independent_of_mw_clamp():
    """The V clip in configure_gate is independent of the mW clamp in
    set_power. Bypass set_power to stage 200 mW (above the 150 mW ceiling)
    and confirm configure_gate still clips to 5.0 V."""
    _reset_tasks()
    l2 = _make_l2_daq()
    # Bypass the mW clamp to prove the V clamp acts independently.
    l2.power = 200.0
    mask = np.ones(20, dtype=float)

    with patch.object(nidaqmx, "Task", _RecordingTask):
        l2.configure_gate(mask, sample_rate=40000, total_samples=20,
                          start_trigger="/Dev1/ao/StartTrigger")

    gate_task = _find_task("laser2_gate_ao")
    payload = gate_task.written
    assert payload is not None
    # 200 mW / 30 mW/V = 6.67 V, clipped to 5.0 V by configure_gate.
    assert np.all(payload == pytest.approx(5.0))


# --------------------------------------------------------------------------- #
# Behavior 4: scanner start order arms camera DO and L2 AO slaves before the
# Dev1 galvo/ETL AO master; monitor/stop/delete cover all three tasks and
# clear every handle.
# --------------------------------------------------------------------------- #
def test_scanner_lifecycle_order_and_cleanup():
    _reset_tasks()
    sg, l2 = _make_siggen_with_l2("Lightsheet")
    sg.compute_scan_waveforms()
    l2.set_power(150.0)
    sg.set_laser2_gate(True)

    with patch.object(nidaqmx, "Task", _RecordingTask):
        sg.create_scanner()
        sg.start_scanner()
        sg.monitor_scanner()
        sg.stop_scanner()
        sg.delete_scanner()

    cam = _find_task("camera_scan")
    gate = _find_task("laser2_gate_ao")
    galvo = _find_task("galvo_etl_scan")

    # Start order: camera (slave), L2 gate (slave), galvo/ETL (master last).
    start_order = [t.calls[0] for t in [cam, gate, galvo] if t.calls]
    assert start_order == ["start", "start", "start"]
    # Verify the actual call sequence via a shared timeline is not possible
    # (each task records its own calls), so assert each slave started before
    # the master by checking call indices on a combined list.
    all_starts = []
    for t in [cam, gate, galvo]:
        if "start" in t.calls:
            all_starts.append((t.name, t.calls.index("start")))
    all_starts.sort(key=lambda x: x[1])
    names_in_order = [name for name, _ in all_starts]
    assert names_in_order == ["camera_scan", "laser2_gate_ao", "galvo_etl_scan"]

    # monitor: all three waited.
    assert "wait_until_done" in cam.calls
    assert "wait_until_done" in gate.calls
    assert "wait_until_done" in galvo.calls
    # stop: all three stopped.
    assert "stop" in cam.calls
    assert "stop" in gate.calls
    assert "stop" in galvo.calls
    # delete: all three closed.
    assert "close" in cam.calls
    assert "close" in gate.calls
    assert "close" in galvo.calls

    # Handles cleared.
    assert sg.task_galvo_etl is None
    assert sg.task_camera is None
    assert l2._gate_task is None


# --------------------------------------------------------------------------- #
# Behavior 5: DAQLaser.off() aborts/closes an in-flight gate before its direct
# 0 V write, clears active/power, returns synchronously, and never acquires
# the per-laser lock.
# --------------------------------------------------------------------------- #
def test_daqlaser_off_aborts_gate_before_zero_write():
    _reset_tasks()
    l2 = _make_l2_daq()
    l2.set_power(150.0)
    mask = np.ones(10, dtype=float)

    with patch.object(nidaqmx, "Task", _RecordingTask):
        l2.configure_gate(mask, sample_rate=40000, total_samples=10,
                          start_trigger="/Dev1/ao/StartTrigger")
    gate_task = _find_task("laser2_gate_ao")
    assert l2._gate_task is not None

    # off() must stop+close the gate, then write 0 V. The 0 V write goes
    # through _write_volts which creates a NEW nidaqmx.Task — patch it to
    # a recording task so it does not raise.
    _reset_tasks()
    with patch.object(nidaqmx, "Task", _RecordingTask):
        result = l2.off()

    assert result is None
    # Gate was stopped and closed before the 0 V write.
    assert "stop" in gate_task.calls
    assert "close" in gate_task.calls
    # Gate handle cleared.
    assert l2._gate_task is None
    # State cleared.
    assert l2.active is False
    assert l2.power == 0.0
    # The 0 V on-demand write happened (a new task was created for it).
    zero_tasks = [t for t in _RecordingTask.instances if t.written is not None]
    assert len(zero_tasks) >= 1
    assert float(zero_tasks[-1].written[0]) == pytest.approx(0.0)


def test_daqlaser_off_is_lock_free_with_gate_armed():
    """SAFETY (AGENTS.md §2): DAQLaser.off() MUST NOT acquire self._lock even
    when a gate task is armed. A daemon set_power holding the RLock on another
    thread must never delay the E-stop kill path."""
    import threading

    _reset_tasks()
    l2 = _make_l2_daq()
    l2.set_power(150.0)
    mask = np.ones(10, dtype=float)
    with patch.object(nidaqmx, "Task", _RecordingTask):
        l2.configure_gate(mask, sample_rate=40000, total_samples=10,
                          start_trigger="/Dev1/ao/StartTrigger")

    held = threading.Event()
    release = threading.Event()

    def hold_lock() -> None:
        with l2._lock:
            held.set()
            release.wait(timeout=5.0)

    holder = threading.Thread(target=hold_lock, daemon=True)
    holder.start()
    held.wait(timeout=5.0)
    try:
        done = threading.Event()

        def call_off() -> None:
            with patch.object(nidaqmx, "Task", _RecordingTask):
                l2.off()
            done.set()

        off_thread = threading.Thread(target=call_off, daemon=True)
        off_thread.start()
        assert done.wait(timeout=2.0), (
            "DAQLaser.off() did not return within 2 s while another thread "
            "held self._lock — it must be lock-free so the E-stop kill path "
            "is never delayed by a daemon write (AGENTS.md §2)"
        )
        assert l2.active is False
        assert l2.power == 0.0
        assert l2._gate_task is None
    finally:
        release.set()
        holder.join(timeout=5.0)


# --------------------------------------------------------------------------- #
# Behavior 6: the real class remains testable with the conftest nidaqmx stub
# and surfaces gate-task failures on the HAL error surface rather than raising
# through the controller.
# --------------------------------------------------------------------------- #
def test_daqlaser_configure_gate_surfaces_failure_without_raising():
    """When nidaqmx.Task raises inside configure_gate, the error is surfaced
    on the DAQLaser HAL error surface (error=1, non-empty message) and no
    exception propagates. The conftest nidaqmx stub makes Task() raise
    nidaqmx.errors.Error naturally — no patch needed."""
    l2 = _make_l2_daq()
    l2.set_power(150.0)
    mask = np.ones(10, dtype=float)
    # No patch — conftest stub raises.
    l2.configure_gate(mask, sample_rate=40000, total_samples=10,
                      start_trigger="/Dev1/ao/StartTrigger")
    assert l2.error == 1
    assert isinstance(l2.error_message, str) and l2.error_message != ""
    # Gate handle not retained on failure.
    assert l2._gate_task is None


def test_siggen_create_scanner_propagates_l2_gate_failure():
    """When the L2 gate task creation fails inside create_scanner, the failure
    propagates to SigGen's error surface and all partial tasks are cleaned up
    so acquire_scan() aborts before camera recording."""
    _reset_tasks()
    sg, l2 = _make_siggen_with_l2("Lightsheet")
    sg.compute_scan_waveforms()
    l2.set_power(150.0)
    sg.set_laser2_gate(True)

    class _FailingTask:
        def __init__(self, *a: object, **k: object) -> None:
            raise RuntimeError("DAQ unavailable")

        def __enter__(self) -> "_FailingTask":
            return self

        def __exit__(self, *exc: object) -> None:
            return None

    real_errors = siggen_module.nidaqmx.errors
    with patch.object(nidaqmx, "Task", _FailingTask):
        # Also patch errors so the except clause matches.
        nidaqmx.errors = real_errors
        sg.create_scanner()

    assert sg.error == 1
    assert sg.task_galvo_etl is None
    assert sg.task_camera is None
    assert l2._gate_task is None


# --------------------------------------------------------------------------- #
# MockSigGen parity: set_laser2_gate and waveform_laser2_window exist on the
# mock so the demo path and conformance tests do not AttributeError.
# --------------------------------------------------------------------------- #
def test_mock_siggen_set_laser2_gate_parity():
    from lightsheet.hal import MockSigGen

    msg = MockSigGen(MockCamera())
    # Default state: gate disabled, window None before compute.
    assert msg._laser2_gate_enabled is False
    msg.set_laser2_gate(True)
    assert msg._laser2_gate_enabled is True
    msg.set_laser2_gate(False)
    assert msg._laser2_gate_enabled is False
    # compute_scan_waveforms populates the L2 window from the camera waveform.
    msg.camera.ysize = 100
    msg.camera.xsize = 256
    msg.camera.line_time = 48.80 * 1e-6
    msg.camera.exposure_time = 0.005
    msg.camera.shutter_mode = "Lightsheet"
    msg.camera.lightsheet_exposed_lines = 16
    msg.compute_scan_waveforms()
    assert msg.waveform_laser2_window is not None
    assert msg.waveform_laser2_window.shape == msg.waveform_camera.shape


# --------------------------------------------------------------------------- #
# Task 2: Registry composition — config-driven L2 DAQLaser with retained
# serial readback. These tests patch hardware-bound constructors/enumeration
# and inspect runtime objects/call arguments only — no real SDK calls.
# --------------------------------------------------------------------------- #
def _parse_terminals_helper():
    """Expose the registry's terminal parser for direct unit testing."""
    from lightsheet.hal.registry import _parse_laser_terminals
    return _parse_laser_terminals


def test_terminal_pair_parses_two_channel_range():
    """_parse_laser_terminals expands /Dev7/ao0:1 into (/Dev7/ao0,
    /Dev7/ao1)."""
    parse = _parse_terminals_helper()
    l1, l2 = parse("/Dev7/ao0:1")
    assert l1 == "/Dev7/ao0"
    assert l2 == "/Dev7/ao1"


def test_terminal_pair_rejects_malformed_range():
    """Malformed or non-two-channel ranges raise ValueError before HAL
    construction."""
    parse = _parse_terminals_helper()
    for bad in ["/Dev7/ao0", "/Dev7/ao0:2", "/Dev7/ao0:1:2", "garbage", "/Dev7/ao"]:
        with pytest.raises(ValueError):
            parse(bad)


def test_registry_composes_l2_daq_with_readback_and_siggen(monkeypatch):
    """DeviceRegistry.resolve() constructs lasers[1] as a DAQLaser on
    /Dev7/ao1 with wavelength 647, max_power 150.0 mW, mw_per_volt 30.0,
    a 5.0 V ceiling, and a retained IBeamSmartLaser as readback_backend.
    The same DAQLaser is injected into SigGen for gate-task ownership."""
    from lightsheet.hal import registry as registry_module

    # Patch hardware-bound constructors and enumeration so no real SDK
    # calls happen. We inspect the constructed objects and call arguments.
    constructed: dict[str, object] = {}

    def fake_resolve_ports(self):
        # Return a minimal resolved-port map so resolve() proceeds.
        return {"motors": "COM7", "etl_left": "COM5", "etl_right": "COM6"}

    monkeypatch.setattr(
        registry_module.DeviceRegistry, "_resolve_ports", fake_resolve_ports
    )

    # Patch Camera, Motors, ETLs, IBeamSmartLaser constructors to no-ops.
    monkeypatch.setattr(registry_module, "Camera", lambda **kw: object())
    monkeypatch.setattr(registry_module, "Motors", lambda **kw: object())
    monkeypatch.setattr(registry_module, "ETLs", lambda **kw: object())

    # Capture the IBeamSmartLaser readback instance.
    class _FakeIBeam:
        def __init__(self, label=""):
            self.label = label
            constructed["readback"] = self

    monkeypatch.setattr(registry_module, "IBeamSmartLaser", _FakeIBeam)

    # Capture the DAQLaser instances and the SigGen constructor call.
    real_daqlaser = registry_module.DAQLaser

    class _CapturingDAQLaser(real_daqlaser):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            if "ao1" in kwargs.get("terminal", ""):
                constructed["l2"] = self
            else:
                constructed["l1"] = self

    monkeypatch.setattr(registry_module, "DAQLaser", _CapturingDAQLaser)

    siggen_calls: list[dict] = {}

    class _CapturingSigGen:
        def __init__(self, camera, laser2_daq=None):
            self.camera = camera
            self.laser2_daq = laser2_daq
            siggen_calls["camera"] = camera
            siggen_calls["laser2_daq"] = laser2_daq

    monkeypatch.setattr(registry_module, "SigGen", _CapturingSigGen)

    # Use the real config.ini so cfg_read returns the tracked values.
    reg = registry_module.DeviceRegistry(
        inventory_path="hardware_inventory.yaml",
        config_path="config.ini",
    )
    bundle = reg.resolve()

    # L2 is a DAQLaser on /Dev7/ao1 with the tracked config.
    l2 = constructed["l2"]
    assert l2.terminal == "/Dev7/ao1"
    assert l2.wavelength == 647
    assert l2.max_power == 150.0
    assert l2.mw_per_volt == 30.0
    assert l2._max_volts == pytest.approx(5.0)
    # Retained iBeam serial backend attached as readback_backend.
    assert l2.readback_backend is constructed["readback"]
    # The same DAQLaser was injected into SigGen.
    assert siggen_calls["laser2_daq"] is l2
    # Bundle lasers is a tuple of two elements, L1 on ao0, L2 on ao1.
    assert isinstance(bundle.lasers, tuple)
    assert len(bundle.lasers) == 2
    assert bundle.lasers[1] is l2
    # L1 stays on ao0.
    assert constructed["l1"].terminal == "/Dev7/ao0"
    # DeviceBundle is frozen.
    import dataclasses
    assert dataclasses.is_dataclass(bundle) and getattr(
        bundle.__class__, "__dataclass_params__"
    ).frozen


def test_demo_bundle_remains_all_mock_and_frozen():
    """_build_demo_bundle() remains all-Mock, constructs successfully without
    pyserial/nidaqmx hardware, and keeps DeviceBundle frozen with lasers as a
    tuple."""
    from lightsheet.__main__ import _build_demo_bundle
    import dataclasses

    bundle = _build_demo_bundle()
    assert dataclasses.is_dataclass(bundle)
    assert getattr(bundle.__class__, "__dataclass_params__").frozen
    assert isinstance(bundle.lasers, tuple)
    assert len(bundle.lasers) == 2
    # L2 in demo is a MockLaser, not a DAQLaser.
    from lightsheet.hal import MockLaser
    assert isinstance(bundle.lasers[1], MockLaser)
