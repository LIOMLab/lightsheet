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
from pathlib import Path

import pytest

# Whether the nidaqmx stub is active (dev machine) vs the real nidaqmx (rig).
# The write-failure tests below assert the stub's "Task() raises" behavior;
# they must skip when the real nidaqmx is active (the real write succeeds).
# On the rig the real nidaqmx is active even for the mock-suite run (without
# LIGHTSHEET_HW=1), so gating on the stub — not the env var — is correct.
from conftest import _nidaqmx_is_stub

from lightsheet.hal.real.daqlaser import DAQLaser

# Kept for parity with test_daqlaser.py; not used for skip gating here.
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

    Skipped when the real nidaqmx is active: the real DAQ write succeeds and
    would energize the laser — a power-setting command requiring explicit
    operator action."""
    if not _nidaqmx_is_stub:
        pytest.skip(
            "Stub-only failure path -- the real nidaqmx is active, so the "
            "DAQ write succeeds instead of raising"
        )
    laser = _make_l2_daq()
    laser.set_power(75.0)
    laser.on()
    assert laser.error == 1
    assert laser.error_message != ""
    assert laser.active is False


def test_l2_set_power_active_writes_via_write_volts() -> None:
    """set_power on an ACTIVE L2 writes via _write_volts (the active=True
    branch). The conftest stub raises so the write-failure revert fires.

    Skipped when the real nidaqmx is active: the real DAQ write succeeds and
    would change emission — a power-setting command requiring explicit
    operator action."""
    if not _nidaqmx_is_stub:
        pytest.skip(
            "Stub-only failure path -- the real nidaqmx is active, so the "
            "DAQ write succeeds instead of raising"
        )
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

        def write(self, data: object, auto_start: bool = True) -> None:
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
    nidaqmx.Task = _CapturingTask  # type: ignore[attr-defined]  # ty: ignore[invalid-assignment]
    try:
        laser._write_volts(999.0)
        assert float(captured["volts"][0]) == pytest.approx(5.0)  # ty: ignore[not-subscriptable]
        laser._write_volts(-10.0)
        assert float(captured["volts"][0]) == pytest.approx(0.0)  # ty: ignore[not-subscriptable]
        laser._write_volts(2.5)
        assert float(captured["volts"][0]) == pytest.approx(2.5)  # ty: ignore[not-subscriptable]
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
    tmp_path: Path,
) -> None:
    """DeviceRegistry.resolve() constructs lasers[1] as a DAQLaser on the
    second terminal parsed from `Lasers Terminals`, with a retained
    IBeamSmartLaser readback_backend, and passes resolved serial ports to
    all real HAL constructors. SigGen is constructed with only the camera
    (no L2 injection)."""
    from lightsheet.hal import registry as registry_module
    from lightsheet.hal.real.daqlaser import InvertedVoltMap, LinearVoltMap

    constructed: dict[str, object] = {}
    hal_kwargs: dict[str, dict[str, object]] = {}
    ibeam_kwargs: dict[str, object] = {}

    # A non-default two-channel DAQ range: /Dev1/ao2:3 means L1->ao2, L2->ao3.
    config_path = tmp_path / "config.ini"
    config_path.write_text(
        "[Lasers]\n"
        "Lasers Terminals = /Dev1/ao2:3\n"
        "Laser1 Wavelength = 555\n"
        "Laser1 Max Power = 107.5\n"
        "Laser1 mW per Volt = 60\n"
        "Laser2 Wavelength = 647\n"
        "Laser2 Max Power = 150\n"
    )

    def fake_resolve_ports(self: object) -> dict[str, str]:
        return {
            "Zaber motor stages": "COM7",
            "ETL left": "COM5",
            "ETL right": "COM6",
            "Toptica iBeam Smart 640nm laser": "COM4",
        }

    monkeypatch.setattr(
        registry_module.DeviceRegistry, "_resolve_ports", fake_resolve_ports
    )
    monkeypatch.setattr(registry_module, "Camera", lambda **kw: object())

    class _CaptureMotors:
        def __init__(self, **kwargs: object) -> None:
            hal_kwargs["motors"] = kwargs
            constructed["motors"] = self

    class _CaptureETLs:
        def __init__(self, **kwargs: object) -> None:
            hal_kwargs["etls"] = kwargs
            constructed["etls"] = self

    class _CaptureIBeam:
        def __init__(self, **kwargs: object) -> None:
            self.label = kwargs.get("label", "")
            ibeam_kwargs.update(kwargs)
            constructed["readback"] = self

    monkeypatch.setattr(registry_module, "Motors", _CaptureMotors)
    monkeypatch.setattr(registry_module, "ETLs", _CaptureETLs)
    monkeypatch.setattr(registry_module, "IBeamSmartLaser", _CaptureIBeam)

    real_daqlaser = registry_module.DAQLaser

    class _CapturingDAQLaser(real_daqlaser):
        def __init__(self, **kwargs: object) -> None:
            super().__init__(**kwargs)  # ty: ignore[invalid-argument-type]
            if kwargs.get("wavelength") == 647:
                constructed["l2"] = self
                constructed["l2_kwargs"] = kwargs
            else:
                constructed["l1"] = self
                constructed["l1_kwargs"] = kwargs

    monkeypatch.setattr(registry_module, "DAQLaser", _CapturingDAQLaser)

    siggen_calls: list[object] = []

    class _CapturingSigGen:
        def __init__(self, camera: object) -> None:
            self.camera = camera
            siggen_calls.append(self)

    monkeypatch.setattr(registry_module, "SigGen", _CapturingSigGen)

    reg = registry_module.DeviceRegistry(
        inventory_path="hardware_inventory.yaml",
        config_path=str(config_path),
    )
    bundle = reg.resolve()

    l1 = constructed["l1"]
    l2 = constructed["l2"]
    # Lasers Terminals is live: /Dev1/ao2:3 -> L1 on ao2, L2 on ao3.
    assert l1.terminal == "/Dev1/ao2"  # ty: ignore[unresolved-attribute]
    assert l2.terminal == "/Dev1/ao3"  # ty: ignore[unresolved-attribute]
    assert l2.wavelength == 647  # ty: ignore[unresolved-attribute]
    assert l2.max_power == 150.0  # ty: ignore[unresolved-attribute]
    # L2 uses an InvertedVoltMap; L1 keeps a LinearVoltMap.
    assert isinstance(l2._volt_map, InvertedVoltMap)  # ty: ignore[unresolved-attribute]
    assert l2._volt_map.off_volts == pytest.approx(5.0)  # ty: ignore[unresolved-attribute]
    assert l2._max_volts == pytest.approx(5.0)  # ty: ignore[unresolved-attribute]
    assert isinstance(l1._volt_map, LinearVoltMap)  # ty: ignore[unresolved-attribute]
    assert l2.readback_backend is constructed["readback"]  # ty: ignore[unresolved-attribute]
    # Resolved serial ports are passed to all real HAL constructors.
    assert hal_kwargs.get("motors") == {"port": "COM7"}
    assert hal_kwargs.get("etls") == {
        "port_etl_left": "COM5",
        "port_etl_right": "COM6",
    }
    assert ibeam_kwargs.get("port") == "COM4"
    # The iBeam readback_backend was constructed with analog_ceiling_mw = Laser2
    # Max Power (the sole L2 ceiling source).
    assert ibeam_kwargs.get("analog_ceiling_mw") == pytest.approx(150.0)
    # SigGen was constructed with only the camera — no L2 injection.
    assert len(siggen_calls) == 1
    assert not hasattr(siggen_calls[0], "laser2_daq")
    # Bundle lasers is a frozen tuple of two.
    assert isinstance(bundle.lasers, tuple)
    assert len(bundle.lasers) == 2
    assert bundle.lasers[1] is l2
    import dataclasses
    assert dataclasses.is_dataclass(bundle)
    assert bundle.__class__.__dataclass_params__.frozen


def test_registry_l1_retains_linear_volt_map(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """L1 retains its LinearVoltMap (normal polarity, optional calibration
    curve) — the registry does NOT switch L1 to InvertedVoltMap. L1's
    off_volts is 0.0 V (normal polarity: 0 V = off)."""
    from lightsheet.hal import registry as registry_module
    from lightsheet.hal.real.daqlaser import LinearVoltMap

    constructed: dict[str, object] = {}

    def fake_resolve_ports(self: object) -> dict[str, str]:
        return {
            "Zaber motor stages": "COM7",
            "ETL left": "COM5",
            "ETL right": "COM6",
            "Toptica iBeam Smart 640nm laser": "COM4",
        }

    monkeypatch.setattr(
        registry_module.DeviceRegistry, "_resolve_ports", fake_resolve_ports
    )
    monkeypatch.setattr(registry_module, "Camera", lambda **kw: object())
    monkeypatch.setattr(registry_module, "Motors", lambda **kw: object())
    monkeypatch.setattr(registry_module, "ETLs", lambda **kw: object())

    class _FakeIBeam:
        def __init__(self, **kwargs: object) -> None:
            constructed["readback"] = self

    monkeypatch.setattr(registry_module, "IBeamSmartLaser", _FakeIBeam)

    real_daqlaser = registry_module.DAQLaser

    class _CapturingDAQLaser(real_daqlaser):
        def __init__(self, **kwargs: object) -> None:
            super().__init__(**kwargs)  # ty: ignore[invalid-argument-type]
            if kwargs.get("terminal", "").endswith("ao0"):  # ty: ignore[unsupported-operator]
                constructed["l1"] = self

    monkeypatch.setattr(registry_module, "DAQLaser", _CapturingDAQLaser)
    monkeypatch.setattr(registry_module, "SigGen", lambda camera: object())

    reg = registry_module.DeviceRegistry(
        inventory_path="hardware_inventory.yaml",
        config_path="config.ini",
    )
    reg.resolve()

    l1 = constructed["l1"]
    assert isinstance(l1._volt_map, LinearVoltMap)  # ty: ignore[unresolved-attribute]
    assert l1._volt_map.off_volts == pytest.approx(0.0)  # ty: ignore[unresolved-attribute]
    # L1 still accepts mw_per_volt + calibration_curve (backwards compat).
    assert l1.mw_per_volt is not None  # ty: ignore[unresolved-attribute]
    assert l1.mw_per_volt > 0  # ty: ignore[unresolved-attribute]


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
    """DAQLaser.open() with a readback_backend writes the off-voltage to the
    DAQ AO channel first, then delegates to the iBeam serial open + channel
    enable, and mirrors the readback error surface. The DAQ off-write must
    succeed (using a capturing nidaqmx.Task) so serial setup is attempted."""
    import nidaqmx

    l2 = _make_l2_daq()
    rb = _RecordingReadback()
    l2.readback_backend = rb  # ty: ignore[invalid-assignment]
    CapturingTask, _captured = _capturing_task_factory()
    original = nidaqmx.Task
    nidaqmx.Task = CapturingTask  # type: ignore[attr-defined]  # ty: ignore[invalid-assignment]
    try:
        l2.open()
    finally:
        nidaqmx.Task = original  # type: ignore[attr-defined]
    assert rb.opened is True
    assert l2.error == 0


def test_daqlaser_open_surfaces_readback_error() -> None:
    """When the readback backend's open() sets an error (channel enable
    rejected), DAQLaser.open() mirrors it onto its own error surface. The
    DAQ off-write must succeed (using a capturing nidaqmx.Task) so serial
    setup is attempted and the readback error is surfaced."""
    import nidaqmx

    l2 = _make_l2_daq()
    rb = _RecordingReadback()
    rb.error = 1
    rb.error_message = "enable_channel rejected: %SYS-E"
    l2.readback_backend = rb  # ty: ignore[invalid-assignment]
    CapturingTask, _captured = _capturing_task_factory()
    original = nidaqmx.Task
    nidaqmx.Task = CapturingTask  # type: ignore[attr-defined]  # ty: ignore[invalid-assignment]
    try:
        l2.open()
    finally:
        nidaqmx.Task = original  # type: ignore[attr-defined]
    assert l2.error == 1
    assert "enable_channel rejected" in l2.error_message


def test_daqlaser_close_delegates_to_readback_backend() -> None:
    """DAQLaser.close() with a readback_backend delegates to the iBeam serial
    close so the serial port is released."""
    l2 = _make_l2_daq()
    rb = _RecordingReadback()
    l2.readback_backend = rb  # ty: ignore[invalid-assignment]
    l2.close()
    assert rb.closed is True


def test_daqlaser_get_output_power_delegates_to_readback() -> None:
    """DAQLaser.get_output_power() with a readback_backend delegates to the
    iBeam serial readback (show level power), not the staged DAQ value."""
    l2 = _make_l2_daq()
    l2.set_power(100.0)
    rb = _RecordingReadback(readback_mw=75.0)
    l2.readback_backend = rb  # ty: ignore[invalid-assignment]
    assert l2.get_output_power() == 75.0


def test_daqlaser_get_output_power_returns_none_on_readback_error() -> None:
    """When the readback backend reports an error, get_output_power() returns
    None so the controller falls back to the commanded value label."""
    l2 = _make_l2_daq()
    rb = _RecordingReadback(readback_mw=75.0)
    rb.error = 1
    l2.readback_backend = rb  # ty: ignore[invalid-assignment]
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
    l2.readback_backend = rb  # ty: ignore[invalid-assignment]
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


# --------------------------------------------------------------------------- #
# Task 1: Injectable voltage-map strategies (LinearVoltMap / InvertedVoltMap)
# and polarity-aware synchronous off().
#
# The inverted L2 transfer function (rig-measured): 0 mW -> 5 V (true off),
# 75 mW -> 2.5 V, 150 mW -> 0 V (max output). Polarity is INVERTED: higher
# voltage = lower power. off() MUST write 5 V (true-off), NEVER 0 V — writing
# 0 V on an inverted L2 would drive it to MAXIMUM power during E-stop.
# Every V write clamps to [0.0, 5.0] — NEVER negative (negative V trips the
# iBeam current-clip latch, a documented near-miss).
# --------------------------------------------------------------------------- #
def test_linear_volt_map_maps_mw_to_volts() -> None:
    """LinearVoltMap(mw_per_volt=60.0, max_volts=5.0) maps 0/150/300 mW to
    0/2.5/5 V at 60 mW/V. 0 mW always returns 0.0 V (the off-voltage for
    linear/normal-polarity lasers)."""
    from lightsheet.hal.real.daqlaser import LinearVoltMap

    vm = LinearVoltMap(mw_per_volt=60.0, max_volts=5.0)
    assert vm.off_volts == 0.0
    assert vm.max_volts == pytest.approx(5.0)
    assert vm.to_volts(0.0) == pytest.approx(0.0)
    assert vm.to_volts(150.0) == pytest.approx(2.5)
    assert vm.to_volts(300.0) == pytest.approx(5.0)


def test_inverted_volt_map_maps_and_clamps() -> None:
    """InvertedVoltMap(max_volts=5.0, max_power_mw=150.0) maps 0/75/150 mW
    to 5/2.5/0 V (inverted polarity: higher power = lower voltage). Hostile
    mW inputs are clamped to [0, max_power_mw] BEFORE the V formula, and the
    V result is independently clamped to [0.0, 5.0] so negative voltage can
    never reach the iBeam analog input (negative V trips the current-clip
    latch — a documented near-miss)."""
    from lightsheet.hal.real.daqlaser import InvertedVoltMap

    vm = InvertedVoltMap(max_volts=5.0, max_power_mw=150.0)
    assert vm.off_volts == pytest.approx(5.0), (
        "InvertedVoltMap.off_volts MUST be 5.0 V (true-off) — writing 0 V "
        "on an inverted L2 drives it to MAXIMUM power"
    )
    assert vm.max_volts == pytest.approx(5.0)
    # Inverted mapping: 0 mW -> 5 V (off), 75 mW -> 2.5 V, 150 mW -> 0 V (max).
    assert vm.to_volts(0.0) == pytest.approx(5.0)
    assert vm.to_volts(75.0) == pytest.approx(2.5)
    assert vm.to_volts(150.0) == pytest.approx(0.0)
    # Hostile mW clamped before the formula: below-zero -> 0 mW -> 5 V (off).
    assert vm.to_volts(-10.0) == pytest.approx(5.0)
    # Above-ceiling -> 150 mW -> 0 V (max, not beyond).
    assert vm.to_volts(999.0) == pytest.approx(0.0)


def _make_inverted_l2_daq() -> DAQLaser:
    """Construct an inverted-polarity L2 DAQLaser on /Dev7/ao1 with
    InvertedVoltMap(5.0 V, 150 mW) — the rig-measured transfer function."""
    from lightsheet.hal.real.daqlaser import InvertedVoltMap

    return DAQLaser(
        terminal="/Dev7/ao1",
        wavelength=647,
        max_power_mw=150.0,
        label="Laser 2 (647 nm)",
        volt_map=InvertedVoltMap(max_volts=5.0, max_power_mw=150.0),
    )


def _capturing_task_factory() -> tuple[type, dict[str, object]]:
    """Build a capturing nidaqmx.Task replacement that records the volts
    array passed to task.write. Returns (TaskClass, captured_dict)."""

    captured: dict[str, object] = {}

    class _CapturingChannels:
        def add_ao_voltage_chan(self, terminal: str) -> None:
            captured["terminal"] = terminal

    class _CapturingTask:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.ao_channels = _CapturingChannels()

        def write(self, data: object, auto_start: bool = True) -> None:
            captured["volts"] = data

        def __enter__(self) -> "_CapturingTask":
            return self

        def __exit__(self, *args: object) -> None:
            return None

    return _CapturingTask, captured


def test_inverted_daqlaser_set_power_writes_mapped_voltage() -> None:
    """An active inverted DAQLaser writes the mapped (inverted) voltage for
    set_power: set_power(75.0) -> to_volts(75) = 2.5 V -> _write_volts(2.5).
    The mW clamp in set_power and the V clamp in _write_volts are independent
    safety layers."""
    import nidaqmx

    laser = _make_inverted_l2_daq()
    laser.active = True
    CapturingTask, captured = _capturing_task_factory()
    original = nidaqmx.Task
    nidaqmx.Task = CapturingTask  # type: ignore[attr-defined]  # ty: ignore[invalid-assignment]
    try:
        laser.set_power(75.0)
        assert laser.power == 75.0
        assert float(captured["volts"][0]) == pytest.approx(2.5), (  # ty: ignore[not-subscriptable]
            "set_power(75.0 mW) on an inverted L2 must write 2.5 V "
            "(InvertedVoltMap: 75 mW -> 2.5 V)"
        )
        # set_power(150.0) -> 0 V (max power at min voltage).
        laser.set_power(150.0)
        assert float(captured["volts"][0]) == pytest.approx(0.0)  # ty: ignore[not-subscriptable]
        # set_power(0.0) -> 5 V (off at max voltage).
        laser.set_power(0.0)
        assert float(captured["volts"][0]) == pytest.approx(5.0)  # ty: ignore[not-subscriptable]
    finally:
        nidaqmx.Task = original  # type: ignore[attr-defined]


def test_inverted_daqlaser_write_volts_clamps_hostile_inputs() -> None:
    """Direct hostile V inputs to _write_volts are independently clamped to
    [0.0, 5.0] — the second safety layer, independent of the mW clamp.
    999 V -> 5.0 V, -10 V -> 0.0 V. NEVER negative (current-clip latch)."""
    import nidaqmx

    laser = _make_inverted_l2_daq()
    CapturingTask, captured = _capturing_task_factory()
    original = nidaqmx.Task
    nidaqmx.Task = CapturingTask  # type: ignore[attr-defined]  # ty: ignore[invalid-assignment]
    try:
        laser._write_volts(999.0)
        assert float(captured["volts"][0]) == pytest.approx(5.0), (  # ty: ignore[not-subscriptable]
            "_write_volts must clamp 999 V to 5.0 V (max_volts)"
        )
        laser._write_volts(-10.0)
        assert float(captured["volts"][0]) == pytest.approx(0.0), (  # ty: ignore[not-subscriptable]
            "_write_volts must clamp -10 V to 0.0 V — NEVER negative "
            "(negative V trips the iBeam current-clip latch)"
        )
        laser._write_volts(2.5)
        assert float(captured["volts"][0]) == pytest.approx(2.5)  # ty: ignore[not-subscriptable]
    finally:
        nidaqmx.Task = original  # type: ignore[attr-defined]


def test_inverted_daqlaser_off_writes_five_volts_lock_free() -> None:
    """SAFETY (Class IIIB): inverted DAQLaser.off() MUST write exactly 5 V
    (true-off), NOT 0 V. Writing 0 V on an inverted L2 would drive it to
    MAXIMUM power during E-stop — a potentially blinding misfire. off()
    clears active/power, returns None, and completes while another thread
    holds _lock (lock-free E-stop kill path)."""
    import nidaqmx

    laser = _make_inverted_l2_daq()
    CapturingTask, captured = _capturing_task_factory()
    original = nidaqmx.Task
    nidaqmx.Task = CapturingTask  # type: ignore[attr-defined]  # ty: ignore[invalid-assignment]

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
        laser.set_power(75.0)
        assert laser.power == 75.0

        done = threading.Event()

        def call_off() -> None:
            laser.off()
            done.set()

        off_thread = threading.Thread(target=call_off, daemon=True)
        off_thread.start()
        assert done.wait(timeout=2.0), (
            "inverted DAQLaser.off() did not return within 2 s while "
            "another thread held self._lock — it must be lock-free "
            "(E-stop kill path, AGENTS.md §2)"
        )
        # THE critical safety assertion: 5 V was written, NOT 0 V.
        assert float(captured["volts"][0]) == pytest.approx(5.0), (  # ty: ignore[not-subscriptable]
            "inverted L2 off() MUST write 5.0 V (true-off) — writing 0 V "
            "would drive the laser to MAXIMUM power during E-stop "
            "(Class IIIB laser safety)"
        )
        assert laser.active is False
        assert laser.power == 0.0
    finally:
        nidaqmx.Task = original  # type: ignore[attr-defined]
        release.set()
        holder.join(timeout=5.0)


def test_linear_l1_off_still_writes_zero_volts() -> None:
    """Linear L1 off() still writes 0 V (normal polarity: 0 V = off).
    The polarity-aware off() uses volt_map.off_volts, which is 0.0 for
    LinearVoltMap and 5.0 for InvertedVoltMap."""
    import nidaqmx

    laser = _make_l2_daq()  # linear fallback (mw_per_volt=30, max_power=150)
    CapturingTask, captured = _capturing_task_factory()
    original = nidaqmx.Task
    nidaqmx.Task = CapturingTask  # type: ignore[attr-defined]  # ty: ignore[invalid-assignment]
    try:
        laser.set_power(75.0)
        laser.off()
        assert float(captured["volts"][0]) == pytest.approx(0.0), (  # ty: ignore[not-subscriptable]
            "linear L1 off() must write 0.0 V (normal polarity: 0 V = off)"
        )
        assert laser.active is False
        assert laser.power == 0.0
    finally:
        nidaqmx.Task = original  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- #
# Task 2: DAQLaser.open() preloads the off-voltage before serial setup.
#
# For inverted L2, open() must write 5 V (true-off) BEFORE opening the
# configured serial backend. If the DAQ off-voltage write fails, serial
# setup is not attempted. L1 (no readback backend) open() remains a no-op.
# --------------------------------------------------------------------------- #
def test_inverted_open_preloads_five_volts_before_serial_setup() -> None:
    """inverted DAQLaser.open() writes 5 V before opening the configured
    serial backend. The DAQ off write happens first; the serial open is
    only attempted after the DAQ write succeeds."""
    import nidaqmx

    from lightsheet.hal.real.daqlaser import InvertedVoltMap

    laser = DAQLaser(
        terminal="/Dev7/ao1",
        wavelength=647,
        max_power_mw=150.0,
        label="Laser 2 (647 nm)",
        volt_map=InvertedVoltMap(max_volts=5.0, max_power_mw=150.0),
    )

    # Recording readback that tracks open call order.
    class _OrderedReadback:
        def __init__(self) -> None:
            self.error = 0
            self.error_message = ""
            self.opened = False
            self.opened_after_daq_write = False

        def open(self) -> None:
            self.opened = True
            self.opened_after_daq_write = captured.get("volts") is not None

        def close(self) -> None:
            pass

        def get_output_power(self) -> float | None:
            return None

    rb = _OrderedReadback()
    laser.readback_backend = rb  # ty: ignore[invalid-assignment]

    CapturingTask, captured = _capturing_task_factory()
    original = nidaqmx.Task
    nidaqmx.Task = CapturingTask  # type: ignore[attr-defined]  # ty: ignore[invalid-assignment]
    try:
        laser.open()
        # 5 V was written first (true-off for inverted L2).
        assert float(captured["volts"][0]) == pytest.approx(5.0), (  # ty: ignore[not-subscriptable]
            "inverted L2 open() must write 5.0 V (true-off) before serial "
            "setup — the DAQ input must be at 5 V before laser on / en ext"
        )
        # Serial backend was opened after the DAQ write.
        assert rb.opened is True
        assert rb.opened_after_daq_write is True
        assert laser.error == 0
    finally:
        nidaqmx.Task = original  # type: ignore[attr-defined]


def test_inverted_open_aborts_serial_setup_when_daq_off_fails() -> None:
    """If the DAQ off-voltage write fails (nidaqmx stub raises), serial
    setup is not attempted — the readback backend's open() is NOT called.
    The DAQ failure surfaces on the HAL error surface."""
    from lightsheet.hal.real.daqlaser import InvertedVoltMap

    laser = DAQLaser(
        terminal="/Dev7/ao1",
        wavelength=647,
        max_power_mw=150.0,
        label="Laser 2 (647 nm)",
        volt_map=InvertedVoltMap(max_volts=5.0, max_power_mw=150.0),
    )

    class _TrackingReadback:
        def __init__(self) -> None:
            self.error = 0
            self.error_message = ""
            self.opened = False

        def open(self) -> None:
            self.opened = True

        def close(self) -> None:
            pass

        def get_output_power(self) -> float | None:
            return None

    rb = _TrackingReadback()
    laser.readback_backend = rb  # ty: ignore[invalid-assignment]
    # The conftest nidaqmx stub makes Task() raise — the DAQ off write fails.
    if not _nidaqmx_is_stub:
        pytest.skip("Stub-only failure path -- requires nidaqmx stub")
    laser.open()
    # Serial setup was NOT attempted.
    assert rb.opened is False, (
        "open() must not attempt serial setup when the DAQ off-voltage "
        "write fails — the iBeam analog input must be at 5 V before "
        "laser on / en ext"
    )
    assert laser.error == 1
    assert laser.error_message != ""
