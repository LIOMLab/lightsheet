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
  (write-failure revert, mirroring the legacy Lasers._update_setpoints).
- ``off()`` is synchronous: returns ``None`` and leaves ``active == False``
  and ``power == 0.0`` immediately (no thread/queue offload — E-stop kill
  path).
- the native-unit clamp inside ``_write_volts`` bounds volts to
  ``[0, max_power / mw_per_volt]`` independently of the mW-layer clamp in
  ``set_power`` (two-layer clamp).

This is a BEHAVIOR test (AGENTS.md §5) — it executes the real DAQLaser
code under the conftest nidaqmx stub and asserts on its runtime state.
"""

import os
import threading

import pytest
from conftest import _nidaqmx_is_stub

from lightsheet.hal.real.daqlaser import DAQLaser

# Module-level hardware gate — the on()-write-failure test depends on the
# Mac nidaqmx stub making Task() raise; on the rig the real DAQ write
# succeeds (and would energize the laser, a safety concern per AGENTS.md §2).
_has_hardware: bool = os.environ.get("LIGHTSHEET_HW", "0") == "1"

# Whether the nidaqmx stub is active (dev machine) vs the real nidaqmx (rig).
# The write-failure tests below assert the stub's "Task() raises" behavior;
# they must skip when the real nidaqmx is active (the real write succeeds).
# On the rig the real nidaqmx is active even for the mock-suite run (without
# LIGHTSHEET_HW=1), so gating on the stub — not the env var — is correct.


def _make_l1() -> DAQLaser:
    """Construct a DAQLaser mirroring Laser 1's config (555 nm, 300 mW max,
    60 mW per Volt, /Dev7/ao0)."""
    return DAQLaser(
        terminal="/Dev7/ao0",
        wavelength=555,
        mw_per_volt=60.0,
        max_power_mw=300.0,
        label="Laser 1 (555 nm)",
    )


class _ToggleEvent(threading.Event):
    """threading.Event that returns a canned is_set() sequence for tests.

    Each call to ``is_set()`` pops the next value from the reversed list.
    After the sequence is exhausted it returns ``False``.
    """

    def __init__(self, values: list[bool]) -> None:
        super().__init__()
        self._values = list(reversed(values))

    def is_set(self) -> bool:
        if not self._values:
            return False
        return self._values.pop()


def test_construction_defaults() -> None:
    """DAQLaser constructs with power=0.0, active=False, error=0, label set
    verbatim, and a per-instance threading.RLock bound to self._lock."""
    laser = _make_l1()
    assert laser.power == 0.0
    assert laser.active is False
    assert laser.error == 0
    assert laser.error_message == ""
    assert laser.label == "Laser 1 (555 nm)"
    assert laser.wavelength == 555
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
    False (write-failure revert, mirroring the legacy Lasers._update_setpoints).

    Skipped on the rig: the real DAQmx write succeeds (no stub to raise),
    and on() would energize the laser — a power-setting command that
    requires explicit operator action per AGENTS.md §2."""
    if not _nidaqmx_is_stub:
        pytest.skip(
            "Stub-only failure path -- the real nidaqmx is active, so the "
            "DAQ write succeeds instead of raising"
        )
    laser = _make_l1()
    laser.set_power(150.0)
    assert laser.power == 150.0
    laser.on()
    # Write failed -> error surface populated, active reverted to False.
    assert laser.error == 1
    assert isinstance(laser.error_message, str) and laser.error_message != ""
    assert laser.active is False


def test_set_power_active_writes_via_write_volts() -> None:
    """set_power on an ACTIVE laser writes via _write_volts (the if
    self.active branch). The conftest nidaqmx stub makes nidaqmx.Task()
    raise nidaqmx.errors.Error, so the typed-except path fires: error==1,
    active==False after the write-failure revert. This is the DISTINCT
    active=True arc from the inactive arc (test_set_power_inactive_no_write)
    — both must be exercised for 100% branch coverage of set_power.

    Skipped on the rig: the real DAQmx write succeeds (no stub to raise),
    and set_power on an active laser energizes it — a power-setting
    command that requires explicit operator action per AGENTS.md §2."""
    if not _nidaqmx_is_stub:
        pytest.skip(
            "Stub-only failure path -- the real nidaqmx is active, so the "
            "DAQ write succeeds instead of raising"
        )
    laser = _make_l1()
    # Energize the laser (on() attempts a 0 V write which fails on the
    # stub, reverting active=False). Set active=True directly to simulate
    # the post-energization state where a daemon set_power adjusts power.
    laser.active = True
    laser.set_power(150.0)
    # set_power staged the clamped mW value.
    assert laser.power == 150.0
    # The active=True branch called _write_volts -> stub raised -> error
    # surface populated, active reverted to False (write-failure revert).
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


def test_off_is_lock_free() -> None:
    """SAFETY (AGENTS.md §2): DAQLaser.off() MUST NOT acquire self._lock.
    The E-stop kill path is the most safety-critical operation in the
    system; a daemon set_power holding the RLock on another thread must
    never delay the kill path. The per-write nidaqmx.Task is independent
    of any concurrent write, so the lock is not needed for the 0 V write.

    Verify by pre-acquiring the lock on the test thread (simulating a
    daemon write holding it on another thread — RLock is reentrant so
    acquiring it here would NOT block a lock-acquiring off() on the same
    thread, but a lock-acquiring off() on a DIFFERENT thread would block).
    The decisive check is that off() completes while the lock is held by
    a different thread: spawn a worker that holds the lock, then call
    off() from the main thread and assert it returns within a tight
    timeout. A lock-acquiring off() would deadlock/timeout.
    """
    import threading

    laser = _make_l1()
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
        # off() must complete even though another thread holds the lock.
        # Use a bounded join to detect a lock-acquiring regression: if
        # off() tried to acquire self._lock, it would block until
        # release.set() and the call would not return promptly.
        done = threading.Event()

        def call_off() -> None:
            laser.off()
            done.set()

        off_thread = threading.Thread(target=call_off, daemon=True)
        off_thread.start()
        assert done.wait(timeout=2.0), (
            "DAQLaser.off() did not return within 2 s while another thread "
            "held self._lock — it must be lock-free so the E-stop kill path "
            "is never delayed by a daemon write (AGENTS.md §2)"
        )
        assert laser.active is False
        assert laser.power == 0.0
    finally:
        release.set()
        holder.join(timeout=5.0)


def test_open_is_noop_returning_none() -> None:
    """open() is a no-op lifecycle verb (AGENTS.md §10): DAQLaser opens its
    nidaqmx.Task per-write inside _write_volts, so there is no persistent
    connection to open here. Returns None and leaves the error surface
    clean so the controller can call self.lasers[i].open() uniformly
    across backends."""
    laser = _make_l1()
    result = laser.open()
    assert result is None
    # No-op -> error surface unchanged from construction.
    assert laser.error == 0
    assert laser.error_message == ""


def test_close_is_noop_returning_none() -> None:
    """close() is a no-op lifecycle verb (AGENTS.md §10): mirrors open() —
    DAQLaser holds no persistent DAQ connection. Returns None."""
    laser = _make_l1()
    result = laser.close()
    assert result is None
    assert laser.error == 0
    assert laser.error_message == ""


def test_get_output_power_returns_staged_power() -> None:
    """get_output_power() returns the staged self.power (mW) — DAQ analog
    output has no hardware readback channel, so the controller's L2
    readback field degrades gracefully to the commanded value. Never
    returns None (the staged value is always available)."""
    laser = _make_l1()
    # Freshly constructed -> staged power is 0.0.
    assert laser.get_output_power() == 0.0
    # After set_power, the staged value is reflected.
    laser.set_power(150.0)
    assert laser.get_output_power() == 150.0
    # Clamp is reflected in the readback too.
    laser.set_power(999.0)
    assert laser.get_output_power() == 300.0
    # off() resets staged power to 0.0 -> readback follows.
    laser.off()
    assert laser.get_output_power() == 0.0


def test_construction_rejects_zero_mw_per_volt() -> None:
    """A config.ini typo (``Laser1 mW per Volt = 0``) must surface on the
    HAL error surface in __init__ rather than crash later with a
    ZeroDivisionError inside _write_volts (AGENTS.md §10 — surface
    misconfiguration rather than crash). The laser is constructed but
    flagged ``error == 1`` with a non-empty message naming the bad value.
    """
    laser = DAQLaser(
        terminal="/Dev7/ao0",
        wavelength=555,
        mw_per_volt=0.0,
        max_power_mw=300.0,
        label="Laser 1 (555 nm)",
    )
    assert laser.error == 1, (
        "mw_per_volt=0 must set the HAL error surface in __init__ rather "
        "than crash on the first _write_volts division"
    )
    assert "mw_per_volt" in laser.error_message
    assert "0" in laser.error_message


def test_construction_rejects_negative_mw_per_volt() -> None:
    """A negative mw_per_volt is equally invalid (would invert the mW->V
    mapping and produce a negative clamp ceiling). Surface on the HAL
    error surface in __init__."""
    laser = DAQLaser(
        terminal="/Dev7/ao0",
        wavelength=555,
        mw_per_volt=-60.0,
        max_power_mw=300.0,
        label="Laser 1 (555 nm)",
    )
    assert laser.error == 1
    assert "mw_per_volt" in laser.error_message


def test_write_volts_aborts_on_zero_mw_per_volt() -> None:
    """Defense-in-depth: even if a DAQLaser with mw_per_volt<=0 is
    constructed (e.g. by a subclass or a future refactor that bypasses
    the __init__ guard), _write_volts must NOT raise ZeroDivisionError
    on the clamp division. It sets the error surface, reverts active,
    and returns early — the daemon write thread stays alive.

    Skipped when the real nidaqmx is active: the clamp reduces 2.5 V to 0.0 V
    (max_power/mw_per_volt = 0), and the real DAQ write of 0.0 V succeeds, so
    the error surface stays clean. The ZeroDivisionError guard is still
    verified on the stub path (the write raises, surfacing the error)."""
    if not _nidaqmx_is_stub:
        pytest.skip(
            "Stub-only failure path -- the real nidaqmx writes 0.0 V cleanly"
        )
    laser = DAQLaser(
        terminal="/Dev7/ao0",
        wavelength=555,
        mw_per_volt=0.0,
        max_power_mw=300.0,
        label="Laser 1 (555 nm)",
    )
    assert laser.error == 1  # set by __init__
    # Clear the surface so we can prove _write_volts re-sets it.
    laser.error = 0
    laser.error_message = ""
    laser.active = True
    laser._write_volts(2.5)
    assert laser.error == 1, (
        "_write_volts must surface the invalid mw_per_volt on the HAL "
        "error surface rather than raise ZeroDivisionError"
    )
    assert laser.active is False, (
        "_write_volts must revert active=False when it aborts on an "
        "invalid mw_per_volt (mirrors the write-failure revert)"
    )


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
        # 999 V is far above max_power/mw_per_volt = 300/60 = 5.0 V.
        laser._write_volts(999.0)
        written = captured["volts"]
        # _write_volts writes np.array([volts]); the single element is the
        # clamped value.
        assert float(written[0]) == pytest.approx(5.0)  # ty: ignore[not-subscriptable]
        # Floor clamp: -10 V -> 0 V.
        laser._write_volts(-10.0)
        written = captured["volts"]
        assert float(written[0]) == pytest.approx(0.0)  # ty: ignore[not-subscriptable]
        # In-range value passes through unchanged.
        laser._write_volts(2.5)
        written = captured["volts"]
        assert float(written[0]) == pytest.approx(2.5)  # ty: ignore[not-subscriptable]
        # Terminal passed through to add_ao_voltage_chan unchanged.
        assert captured["terminal"] == "/Dev7/ao0"
    finally:
        nidaqmx.Task = original_task  # type: ignore[attr-defined]


def test_mw_to_volts_zero_mw_per_volt_guard_returns_zero() -> None:
    """Defense-in-depth: _mw_to_volts must return 0.0 (not raise
    ZeroDivisionError) when mw_per_volt<=0 and the laser is uncalibrated.

    __init__ rejects mw_per_volt<=0 and sets error=1, but the guard in
    _mw_to_volts is the second layer: a subclass or future refactor that
    bypasses the __init__ guard, or a calibration-clear path, must not
    let the linear-model division by mw_per_volt raise. The guard returns
    0.0 V (no emission) — the safe default for an invalid conversion
    factor. Mirrors the _write_volts zero-mw_per_volt guard above."""
    laser = DAQLaser(
        terminal="/Dev7/ao0",
        wavelength=555,
        mw_per_volt=0.0,
        max_power_mw=300.0,
        label="Laser 1 (555 nm)",
    )
    # __init__ set error=1; clear it so we prove the guard itself does not
    # raise (the guard is a pure return, not an error-surface setter).
    laser.error = 0
    laser.error_message = ""
    # Uncalibrated (no curve) so the linear-model branch is reached.
    assert laser.calibrated is False
    # mw > 0 so the mw<=0 early return is skipped; mw_per_volt<=0 guard fires.
    assert laser._mw_to_volts(50.0) == 0.0
    # The guard must not raise on negative mw_per_volt either.
    laser.mw_per_volt = -60.0
    assert laser._mw_to_volts(50.0) == 0.0


# --------------------------------------------------------------------------- #
# E-stop re-check: on() and set_power() must not re-energize past the kill.
# --------------------------------------------------------------------------- #
def test_on_returns_immediately_when_estop_set() -> None:
    """If _estop_event is already set when on() is called, on() must not
    acquire the lock, not attempt a DAQ write, and leave active=False."""
    laser = _make_l1()
    laser._estop_event = _ToggleEvent([True])
    laser.on()
    assert laser.active is False
    assert laser.power == 0.0


def test_on_drives_off_volts_when_estop_set_inside_lock() -> None:
    """If E-stop fires between the pre-lock check and the active=True write,
    on() must drive the channel to off_volts and leave active=False."""
    laser = _make_l1()
    laser.power = 150.0
    laser._estop_event = _ToggleEvent([False, True])
    laser.on()
    assert laser.active is False
    assert laser.power == 0.0


def test_on_drives_off_volts_after_power_write_when_estop_fires() -> None:
    """If E-stop fires after the power write has already been issued, on()
    must still drive the channel back to off_volts and set active=False."""
    laser = _make_l1()
    laser.power = 150.0
    laser._estop_event = _ToggleEvent([False, False, True])
    laser.on()
    assert laser.active is False
    assert laser.power == 0.0


def test_set_power_returns_immediately_when_estop_set() -> None:
    """If _estop_event is already set, set_power() must not update self.power
    or attempt a DAQ write."""
    laser = _make_l1()
    laser._estop_event = _ToggleEvent([True])
    laser.set_power(150.0)
    assert laser.power == 0.0
    assert laser.active is False
