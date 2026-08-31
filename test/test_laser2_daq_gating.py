"""Behavior tests for the L2 (iBeam 647 nm) DAQ-driven laser backend on
/Dev7/ao1.

L2 uses the SAME emission-control path as L1: on-demand held voltage via
``DAQLaser._write_volts`` (no finite waveform task, no start trigger). The
retained iBeam serial backend is attached as ``readback_backend`` and is used
ONLY for channel enable at open, power/status readback, and serial-port
release at close — never for on/off or power writes. The DAQ AO channel is the
sole emission-control path.

Covers:
- L2 behaves like L1: on-demand writes, two-layer power clamp (mW in
  set_power, V in _write_volts), synchronous lock-free off() (E-stop kill path).
- readback delegation: open/close/get_output_power delegate to the iBeam
  serial backend; on/off/set_power NEVER call the readback backend.
- registry composition: lasers[1] is a DAQLaser on /Dev7/ao1 with the tracked
  config and a retained IBeamSmartLaser readback_backend; SigGen is constructed
  without any L2 injection (L2 power is set via DAQLaser.set_power, like L1).

The conftest nidaqmx stub makes ``nidaqmx.Task()`` raise on this Mac, so the
typed-except path in ``DAQLaser._write_volts`` fires naturally — no extra
mocking required for the write-failure arcs.

This is a BEHAVIOR test (AGENTS.md §5) — it executes the real DAQLaser code
under the conftest nidaqmx stub and asserts on runtime state.
"""

import os
import threading

import pytest

from lightsheet.hal.real.daqlaser import DAQLaser

# Module-level hardware gate — the on()-write-failure tests depend on the
# Mac nidaqmx stub making Task() raise; on the rig the real DAQ write
# succeeds (and would energize the laser, a safety concern per AGENTS.md §2).
_has_hardware: bool = os.environ.get("LIGHTSHEET_HW", "0") == "1"


# --------------------------------------------------------------------------- #
# DAQLaser construction helper mirroring the L2 rig config:
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


# --------------------------------------------------------------------------- #
# L1-parity: L2 uses the same on-demand held-voltage path as L1.
# --------------------------------------------------------------------------- #
def test_l2_construction_defaults() -> None:
    """L2 DAQLaser constructs with the L2 rig config and clean state."""
    laser = _make_l2_daq()
    assert laser.power == 0.0
    assert laser.active is False
    assert laser.error == 0
    assert laser.error_message == ""
    assert laser.label == "Laser 2 (647 nm)"
    assert laser.wavelength == 647
    assert laser.max_power == 150.0
    assert laser.mw_per_volt == 30.0
    assert laser.terminal == "/Dev7/ao1"
    assert laser._max_volts == pytest.approx(5.0)
    # No gate task field — the finite-gate machinery was removed.
    assert not hasattr(laser, "_gate_task")
    # No readback backend until one is attached.
    assert laser.readback_backend is None


def test_l2_set_power_inactive_no_write() -> None:
    """set_power on an inactive L2 stages the mW value without a DAQ write."""
    laser = _make_l2_daq()
    laser.set_power(75.0)
    assert laser.power == 75.0
    assert laser.error == 0
    assert laser.active is False


def test_l2_set_power_clamps_to_max_mw() -> None:
    """set_power clamps to max_power (150.0 mW) — first safety layer."""
    laser = _make_l2_daq()
    laser.set_power(999.0)
    assert laser.power == 150.0


def test_l2_set_power_clamps_floor_zero() -> None:
    """set_power clamps negative mW to 0.0."""
    laser = _make_l2_daq()
    laser.set_power(-50.0)
    assert laser.power == 0.0


def test_l2_on_write_failure_reverts_state() -> None:
    """on() attempts a DAQ write; the conftest stub makes it raise so the
    write-failure revert fires (error=1, active=False).

    Skipped on the rig: the real DAQmx write succeeds and would energize the
    laser — a power-setting command requiring explicit operator action."""
    if _has_hardware:
        pytest.skip("Mac-only stub-failure path")
    laser = _make_l2_daq()
    laser.set_power(75.0)
    laser.on()
    assert laser.error == 1
    assert laser.error_message != ""
    assert laser.active is False


def test_l2_set_power_active_writes_via_write_volts() -> None:
    """set_power on an ACTIVE L2 writes via _write_volts (the active=True
    branch). The conftest stub raises so the write-failure revert fires.

    Skipped on the rig: the real DAQmx write succeeds and would change
    emission — a power-setting command requiring explicit operator action."""
    if _has_hardware:
        pytest.skip("Mac-only stub-failure path")
    laser = _make_l2_daq()
    laser.active = True
    laser.set_power(75.0)
    assert laser.power == 75.0
    assert laser.error == 1
    assert laser.active is False


def test_l2_off_is_synchronous() -> None:
    """off() is synchronous: returns None, active=False, power=0.0
    immediately (E-stop kill path — no thread/queue offload)."""
    laser = _make_l2_daq()
    laser.set_power(75.0)
    result = laser.off()
    assert result is None
    assert laser.active is False
    assert laser.power == 0.0


def test_l2_off_is_lock_free() -> None:
    """SAFETY (AGENTS.md §2): DAQLaser.off() MUST NOT acquire self._lock.
    The E-stop kill path must never be delayed by a daemon write holding the
    lock. Verify by holding the lock on another thread and asserting off()
    completes within a tight timeout."""
    laser = _make_l2_daq()
    held = threading.Event()
    release = threading.Event()

    def hold_lock() -> None:
        with laser._lock:
            held.set()
            release.wait(timeout=5.0)

    holder = threading.Thread(target=hold_lock, daemon=True)
    holder.start()
    held.wait(timeout=5.0)
    try:
        done = threading.Event()

        def call_off() -> None:
            laser.off()
            done.set()

        off_thread = threading.Thread(target=call_off, daemon=True)
        off_thread.start()
        assert done.wait(timeout=2.0), (
            "DAQLaser.off() did not return within 2 s while another thread "
            "held self._lock — it must be lock-free (AGENTS.md §2)"
        )
        assert laser.active is False
        assert laser.power == 0.0
    finally:
        release.set()
        holder.join(timeout=5.0)


def test_l2_native_unit_volts_clamp_in_write_volts() -> None:
    """The native-unit V clamp inside _write_volts is the second safety layer,
    independent of the mW clamp in set_power. 999 V -> 5.0 V (150/30)."""
    import nidaqmx

    laser = _make_l2_daq()
    captured: dict[str, object] = {}

    class _CapturingTask:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.ao_channels = _CapturingChannels()
            self._volts = None

        def write(self, data, auto_start: bool = True) -> None:  # noqa: ANN001
            self._volts = data
            captured["volts"] = data

        def __enter__(self) -> "_CapturingTask":
            return self

        def __exit__(self, *args: object) -> None:
            return None

    class _CapturingChannels:
        def add_ao_voltage_chan(self, terminal: str) -> None:
            captured["terminal"] = terminal

    original_task = nidaqmx.Task
    nidaqmx.Task = _CapturingTask  # type: ignore[attr-defined]
    try:
        laser._write_volts(999.0)
        assert float(captured["volts"][0]) == pytest.approx(5.0)
        laser._write_volts(-10.0)
        assert float(captured["volts"][0]) == pytest.approx(0.0)
        laser._write_volts(2.5)
        assert float(captured["volts"][0]) == pytest.approx(2.5)
        assert captured["terminal"] == "/Dev7/ao1"
    finally:
        nidaqmx.Task = original_task  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- #
# Registry composition: L2 is a DAQLaser on /Dev7/ao1 with an iBeam readback
# backend. SigGen is constructed WITHOUT any L2 injection — L2 power is set
# via DAQLaser.set_power from the laser panel / adaptive loop, exactly like L1.
# --------------------------------------------------------------------------- #
def test_registry_composes_l2_daq_with_readback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DeviceRegistry.resolve() constructs lasers[1] as a DAQLaser on
    /Dev7/ao1 with wavelength 647, max_power 150.0 mW, mw_per_volt 30.0,
    a 5.0 V ceiling, and a retained IBeamSmartLaser as readback_backend.
    SigGen is constructed with only the camera (no L2 injection)."""
    from lightsheet.hal import registry as registry_module

    constructed: dict[str, object] = {}

    def fake_resolve_ports(self: object) -> dict[str, str]:
        return {"motors": "COM7", "etl_left": "COM5", "etl_right": "COM6"}

    monkeypatch.setattr(
        registry_module.DeviceRegistry, "_resolve_ports", fake_resolve_ports
    )
    monkeypatch.setattr(registry_module, "Camera", lambda **kw: object())
    monkeypatch.setattr(registry_module, "Motors", lambda **kw: object())
    monkeypatch.setattr(registry_module, "ETLs", lambda **kw: object())

    class _FakeIBeam:
        def __init__(self, label: str = "") -> None:
            self.label = label
            constructed["readback"] = self

    monkeypatch.setattr(registry_module, "IBeamSmartLaser", _FakeIBeam)

    real_daqlaser = registry_module.DAQLaser

    class _CapturingDAQLaser(real_daqlaser):
        def __init__(self, **kwargs: object) -> None:
            super().__init__(**kwargs)
            if "ao1" in kwargs.get("terminal", ""):
                constructed["l2"] = self
            else:
                constructed["l1"] = self

    monkeypatch.setattr(registry_module, "DAQLaser", _CapturingDAQLaser)

    siggen_calls: list[object] = []

    class _CapturingSigGen:
        def __init__(self, camera: object) -> None:
            self.camera = camera
            siggen_calls.append(self)

    monkeypatch.setattr(registry_module, "SigGen", _CapturingSigGen)

    reg = registry_module.DeviceRegistry(
        inventory_path="hardware_inventory.yaml",
        config_path="config.ini",
    )
    bundle = reg.resolve()

    l2 = constructed["l2"]
    assert l2.terminal == "/Dev7/ao1"
    assert l2.wavelength == 647
    assert l2.max_power == 150.0
    assert l2.mw_per_volt == 30.0
    assert l2._max_volts == pytest.approx(5.0)
    assert l2.readback_backend is constructed["readback"]
    # SigGen was constructed with only the camera — no L2 injection.
    assert len(siggen_calls) == 1
    assert not hasattr(siggen_calls[0], "laser2_daq")
    # Bundle lasers is a frozen tuple of two; L1 on ao0, L2 on ao1.
    assert isinstance(bundle.lasers, tuple)
    assert len(bundle.lasers) == 2
    assert bundle.lasers[1] is l2
    assert constructed["l1"].terminal == "/Dev7/ao0"
    import dataclasses
    assert dataclasses.is_dataclass(bundle)
    assert bundle.__class__.__dataclass_params__.frozen


def test_demo_bundle_remains_all_mock_and_frozen() -> None:
    """_build_demo_bundle() remains all-Mock, constructs successfully without
    pyserial/nidaqmx hardware, and keeps DeviceBundle frozen with lasers as a
    tuple."""
    import dataclasses

    from lightsheet.__main__ import _build_demo_bundle
    from lightsheet.hal import MockLaser

    bundle = _build_demo_bundle()
    assert dataclasses.is_dataclass(bundle)
    assert bundle.__class__.__dataclass_params__.frozen
    assert isinstance(bundle.lasers, tuple)
    assert len(bundle.lasers) == 2
    assert isinstance(bundle.lasers[1], MockLaser)


# --------------------------------------------------------------------------- #
# Readback delegation: open/close/get_output_power delegate to the iBeam
# serial backend; on/off/set_power NEVER call the readback backend.
# --------------------------------------------------------------------------- #
class _RecordingReadback:
    """Fake IBeamSmartLaser readback backend that records calls and returns
    a canned mW value from get_output_power()."""

    def __init__(self, readback_mw: float | None = 75.0) -> None:
        self.label = "Laser 2 (647 nm)"
        self.wavelength = 647
        self.max_power = 150.0
        self.power = 0.0
        self.active = False
        self.error = 0
        self.error_message = ""
        self._lock = threading.RLock()
        self._readback_mw = readback_mw
        self.opened = False
        self.closed = False
        self.on_calls = 0
        self.off_calls = 0
        self.set_power_calls: list[float] = []

    def open(self) -> None:
        self.opened = True

    def close(self) -> None:
        self.closed = True

    def on(self) -> None:
        self.on_calls += 1

    def off(self) -> None:
        self.off_calls += 1

    def set_power(self, mw: float) -> None:
        self.set_power_calls.append(mw)

    def get_output_power(self) -> float | None:
        return self._readback_mw


def test_daqlaser_open_delegates_to_readback_backend() -> None:
    """DAQLaser.open() with a readback_backend delegates to the iBeam serial
    open + channel enable, and mirrors the readback error surface."""
    l2 = _make_l2_daq()
    rb = _RecordingReadback()
    l2.readback_backend = rb
    l2.open()
    assert rb.opened is True
    assert l2.error == 0


def test_daqlaser_open_surfaces_readback_error() -> None:
    """When the readback backend's open() sets an error (channel enable
    rejected), DAQLaser.open() mirrors it onto its own error surface."""
    l2 = _make_l2_daq()
    rb = _RecordingReadback()
    rb.error = 1
    rb.error_message = "enable_channel rejected: %SYS-E"
    l2.readback_backend = rb
    l2.open()
    assert l2.error == 1
    assert "enable_channel rejected" in l2.error_message


def test_daqlaser_close_delegates_to_readback_backend() -> None:
    """DAQLaser.close() with a readback_backend delegates to the iBeam serial
    close so the serial port is released."""
    l2 = _make_l2_daq()
    rb = _RecordingReadback()
    l2.readback_backend = rb
    l2.close()
    assert rb.closed is True


def test_daqlaser_get_output_power_delegates_to_readback() -> None:
    """DAQLaser.get_output_power() with a readback_backend delegates to the
    iBeam serial readback (show level power), not the staged DAQ value."""
    l2 = _make_l2_daq()
    l2.set_power(100.0)
    rb = _RecordingReadback(readback_mw=75.0)
    l2.readback_backend = rb
    assert l2.get_output_power() == 75.0


def test_daqlaser_get_output_power_returns_none_on_readback_error() -> None:
    """When the readback backend reports an error, get_output_power() returns
    None so the controller falls back to the commanded value label."""
    l2 = _make_l2_daq()
    rb = _RecordingReadback(readback_mw=75.0)
    rb.error = 1
    l2.readback_backend = rb
    assert l2.get_output_power() is None


def test_daqlaser_get_output_power_no_readback_returns_staged() -> None:
    """Without a readback backend (L1 DAQLaser), get_output_power() returns
    the staged/commanded power — NI-DAQ AO has no hardware readback."""
    l2 = _make_l2_daq()
    l2.set_power(50.0)
    assert l2.readback_backend is None
    assert l2.get_output_power() == 50.0


def test_daqlaser_on_off_set_power_do_not_call_readback() -> None:
    """The DAQ emission-control path (on/off/set_power) NEVER calls the
    readback backend's on/off/set_power — the serial path is read-only for
    emission control. The DAQ AO channel is the sole emission-control path."""
    l2 = _make_l2_daq()
    rb = _RecordingReadback()
    l2.readback_backend = rb
    l2.set_power(100.0)
    l2.on()
    l2.off()
    assert rb.on_calls == 0
    assert rb.off_calls == 0
    assert rb.set_power_calls == []


def test_ibeam_smart_laser_methods_remain_present() -> None:
    """The IBeamSmartLaser adapter's on/off/set_power methods remain present
    (ILaser conformance) even though they are not called by the controller
    in the DAQ-driven configuration — the serial path is read-only for
    emission control, but the methods exist for conformance and any
    standalone serial-only usage path."""
    from lightsheet.hal.real.ibeam_smart import IBeamSmartLaser

    l2 = IBeamSmartLaser(label="Laser 2 (647 nm)")
    assert callable(l2.on)
    assert callable(l2.off)
    assert callable(l2.set_power)
    assert callable(l2.open)
    assert callable(l2.close)
    assert callable(l2.get_output_power)
