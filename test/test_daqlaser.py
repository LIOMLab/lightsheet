"""Unit tests for lightsheet/hal/real/daqlaser.py — DAQLaser real backend.

The conftest.py stub makes ``nidaqmx.Task()`` raise ``nidaqmx.errors.Error``
on this Mac (no NI-DAQmx driver runtime), so the typed-except path in
``DAQLaser._write_volts`` fires naturally — no extra mocking is required.
This mirrors the ``test_lasers.py`` conftest-nidaqmx-stub-raises pattern.

Behavior covered (per the plan's <behavior> block):
- construction sets power=0.0, active=False, error=0, label verbatim, and a
  per-instance ``threading.RLock`` bound to ``self._lock``.
- ``set_power(150.0)`` on a constructed-but-inactive instance sets
  ``power == 150.0`` (mW, no write attempted while inactive).
- ``set_power(999.0)`` clamps to ``power == 300.0`` (mW clamp).
- ``on()`` while ``power == 150.0`` attempts a DAQ write of
  ``150.0 / 60.0 == 2.5`` Volts; on this Mac the conftest nidaqmx stub
  makes ``nidaqmx.Task()`` raise ``nidaqmx.errors.Error``, so ``on()`` must
  set ``error == 1``, a non-empty ``error_message``, and ``active == False``
  (write-failure revert, mirroring ``Lasers._update_setpoints``).
- ``off()`` is synchronous: returns ``None`` and leaves ``active == False``
  and ``power == 0.0`` immediately (no thread/queue offload — E-stop kill
  path).
- the native-unit clamp inside ``_write_volts`` bounds volts to
  ``[0, max_power / mw_per_volt]`` independently of the mW-layer clamp in
  ``set_power`` (two-layer clamp).

This is a BEHAVIOR test (AGENTS.md §5) — it executes the real DAQLaser
code under the conftest nidaqmx stub and asserts on its runtime state.
"""

import threading

import pytest

from lightsheet.hal.real.daqlaser import DAQLaser


def _make_l1() -> DAQLaser:
    """Construct a DAQLaser mirroring Laser 1's config (561 nm, 300 mW max,
    60 mW per Volt, /Dev7/ao0)."""
    return DAQLaser(
        terminal="/Dev7/ao0",
        wavelength=561,
        mw_per_volt=60.0,
        max_power_mw=300.0,
        label="Laser 1 (561 nm)",
    )


def test_construction_defaults() -> None:
    """DAQLaser constructs with power=0.0, active=False, error=0, label set
    verbatim, and a per-instance threading.RLock bound to self._lock."""
    laser = _make_l1()
    assert laser.power == 0.0
    assert laser.active is False
    assert laser.error == 0
    assert laser.error_message == ""
    assert laser.label == "Laser 1 (561 nm)"
    assert laser.wavelength == 561
    assert laser.max_power == 300.0
    assert laser.mw_per_volt == 60.0
    assert laser.terminal == "/Dev7/ao0"
    # Per-instance RLock (reentrant so the controller's daemon write paths
    # can re-acquire under the same lock without deadlocking).
    assert isinstance(laser._lock, type(threading.RLock()))


def test_set_power_inactive_no_write() -> None:
    """set_power(150.0) on a constructed-but-inactive instance sets
    power == 150.0 (mW, no write attempted while inactive)."""
    laser = _make_l1()
    laser.set_power(150.0)
    assert laser.power == 150.0
    # Inactive -> no DAQ write attempted -> error surface stays clean.
    assert laser.error == 0
    assert laser.active is False


def test_set_power_clamps_to_max_mw() -> None:
    """set_power(999.0) clamps to power == 300.0 (mW clamp, max(0, min(mw,
    max_power)))."""
    laser = _make_l1()
    laser.set_power(999.0)
    assert laser.power == 300.0


def test_set_power_clamps_floor_zero() -> None:
    """set_power(-50.0) clamps to power == 0.0 (no negative mW)."""
    laser = _make_l1()
    laser.set_power(-50.0)
    assert laser.power == 0.0


def test_on_write_failure_reverts_state() -> None:
    """on() while power == 150.0 attempts a DAQ write of 150.0/60.0 == 2.5 V.
    The conftest nidaqmx stub makes nidaqmx.Task() raise nidaqmx.errors.Error,
    so on() must set error == 1, a non-empty error_message, and active ==
    False (write-failure revert, mirroring Lasers._update_setpoints)."""
    laser = _make_l1()
    laser.set_power(150.0)
    assert laser.power == 150.0
    laser.on()
    # Write failed -> error surface populated, active reverted to False.
    assert laser.error == 1
    assert isinstance(laser.error_message, str) and laser.error_message != ""
    assert laser.active is False


def test_off_is_synchronous() -> None:
    """off() is synchronous: returns None and leaves active == False and
    power == 0.0 immediately (no thread/queue offload — E-stop kill path)."""
    laser = _make_l1()
    laser.set_power(150.0)
    # off() on a freshly-constructed (inactive) laser — the E-stop path
    # calls off() without first energizing (AGENTS.md §2: no energization
    # without explicit operator action).
    result = laser.off()
    assert result is None
    assert laser.active is False
    assert laser.power == 0.0


def test_native_unit_volts_clamp_in_write_volts() -> None:
    """The native-unit clamp inside _write_volts bounds volts to
    [0, max_power / mw_per_volt] independently of the mW-layer clamp in
    set_power (two-layer clamp).

    We exercise _write_volts directly with over-range volts values and
    confirm the clamp reduces them before the DAQ write. The conftest
    nidaqmx stub makes nidaqmx.Task() raise, which would mask the clamped
    value (the error path runs before we can observe what was written), so
    we patch nidaqmx.Task with a capturing stub that records the volts
    array passed to task.write. The clamp inside _write_volts runs before
    the Task is constructed, so the captured value reflects the clamp.
    """
    import nidaqmx

    laser = _make_l1()
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
        # 999 V is far above max_power/mw_per_volt = 300/60 = 5.0 V.
        laser._write_volts(999.0)
        written = captured["volts"]
        # _write_volts writes np.array([volts]); the single element is the
        # clamped value.
        assert float(written[0]) == pytest.approx(5.0)
        # Floor clamp: -10 V -> 0 V.
        laser._write_volts(-10.0)
        written = captured["volts"]
        assert float(written[0]) == pytest.approx(0.0)
        # In-range value passes through unchanged.
        laser._write_volts(2.5)
        written = captured["volts"]
        assert float(written[0]) == pytest.approx(2.5)
        # Terminal passed through to add_ao_voltage_chan unchanged.
        assert captured["terminal"] == "/Dev7/ao0"
    finally:
        nidaqmx.Task = original_task  # type: ignore[attr-defined]
