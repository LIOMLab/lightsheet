"""Tests for the NI-DAQmx laser watchdog.

On the dev machine the nidaqmx stub has no ``system.watchdog`` submodule,
so ``arm()`` logs a warning and returns without arming — the class must
never raise. On the rig (LIGHTSHEET_HW=1) the real nidaqmx is used.
"""

import logging
from types import SimpleNamespace

import pytest

from lightsheet.hal.real.laser_watchdog import LaserWatchdog


class _FakeLaser:
    """Minimal DAQLaser-shaped double with a terminal and off_volts."""

    def __init__(self, terminal: str, off_volts: float) -> None:
        self.terminal = terminal
        self.off_volts = off_volts


def test_arm_on_dev_machine_is_noop(caplog: pytest.LogCaptureFixture) -> None:
    """On the dev machine, nidaqmx is present but the NI-DAQmx runtime is
    not supported on macOS — arm() must log and return without raising."""
    watchdog = LaserWatchdog([_FakeLaser("/Dev7/ao0", 0.0)])
    with caplog.at_level(logging.WARNING):
        watchdog.arm()
    assert caplog.text  # either "disabled" (import failed) or "failed" (runtime absent)
    assert not watchdog._watchdogs
    # reset/disarm are safe no-ops when nothing was armed.
    watchdog.reset()
    watchdog.disarm()


def test_reset_and_disarm_are_safe_when_unarmed() -> None:
    """reset()/disarm() on an unarmed watchdog must not raise."""
    watchdog = LaserWatchdog([])
    watchdog.reset()
    watchdog.disarm()


def test_arm_groups_channels_by_device(monkeypatch: pytest.MonkeyPatch) -> None:
    """Lasers on the same DAQ device share one WatchdogTask."""
    created = []

    class MockWatchdogTask:
        def __init__(self, device: str, timeout: float = 10) -> None:
            self.device = device
            self.states = []
            created.append(self)

        def cfg_watchdog_ao_expir_states(self, states: list[object]) -> None:
            self.states = states

        def start(self) -> None:
            pass

        def reset_timer(self) -> None:
            pass

        def close(self) -> None:
            pass

    monkeypatch.setattr(
        "lightsheet.hal.real.laser_watchdog._nidaqmx_watchdog",
        SimpleNamespace(WatchdogTask=MockWatchdogTask),
    )
    monkeypatch.setattr(
        "lightsheet.hal.real.laser_watchdog._nidaqmx_constants",
        SimpleNamespace(WatchdogAOExpirState=SimpleNamespace(VOLTAGE=1)),
    )
    monkeypatch.setattr(
        "lightsheet.hal.real.laser_watchdog._nidaqmx_types",
        SimpleNamespace(AOExpirationState=lambda **kw: kw),
    )

    watchdog = LaserWatchdog(
        [
            _FakeLaser("/Dev7/ao0", 0.0),
            _FakeLaser("/Dev7/ao1", 5.0),
        ]
    )
    watchdog.arm()
    assert len(created) == 1
    assert created[0].device == "Dev7"
    assert len(created[0].states) == 2


def test_arm_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Calling arm() twice does not create a second WatchdogTask."""
    created = []

    class MockWatchdogTask:
        def __init__(self, device: str, timeout: float = 10) -> None:
            created.append(device)

        def cfg_watchdog_ao_expir_states(self, states: list[object]) -> None:
            pass

        def start(self) -> None:
            pass

        def reset_timer(self) -> None:
            pass

        def close(self) -> None:
            pass

    monkeypatch.setattr(
        "lightsheet.hal.real.laser_watchdog._nidaqmx_watchdog",
        SimpleNamespace(WatchdogTask=MockWatchdogTask),
    )
    monkeypatch.setattr(
        "lightsheet.hal.real.laser_watchdog._nidaqmx_constants",
        SimpleNamespace(WatchdogAOExpirState=SimpleNamespace(VOLTAGE=1)),
    )
    monkeypatch.setattr(
        "lightsheet.hal.real.laser_watchdog._nidaqmx_types",
        SimpleNamespace(AOExpirationState=lambda **kw: kw),
    )

    watchdog = LaserWatchdog([_FakeLaser("/Dev7/ao0", 0.0)])
    watchdog.arm()
    watchdog.arm()
    assert created == ["Dev7"]


def test_reset_calls_reset_timer(monkeypatch: pytest.MonkeyPatch) -> None:
    """reset() forwards to each armed WatchdogTask."""
    calls = []

    class MockWatchdogTask:
        def __init__(self, device: str, timeout: float = 10) -> None:
            pass

        def cfg_watchdog_ao_expir_states(self, states: list[object]) -> None:
            pass

        def start(self) -> None:
            pass

        def reset_timer(self) -> None:
            calls.append("reset")

        def close(self) -> None:
            pass

    monkeypatch.setattr(
        "lightsheet.hal.real.laser_watchdog._nidaqmx_watchdog",
        SimpleNamespace(WatchdogTask=MockWatchdogTask),
    )
    monkeypatch.setattr(
        "lightsheet.hal.real.laser_watchdog._nidaqmx_constants",
        SimpleNamespace(WatchdogAOExpirState=SimpleNamespace(VOLTAGE=1)),
    )
    monkeypatch.setattr(
        "lightsheet.hal.real.laser_watchdog._nidaqmx_types",
        SimpleNamespace(AOExpirationState=lambda **kw: kw),
    )

    watchdog = LaserWatchdog([_FakeLaser("/Dev7/ao0", 0.0)])
    watchdog.arm()
    watchdog.reset()
    assert calls == ["reset"]


def test_disarm_closes_tasks(monkeypatch: pytest.MonkeyPatch) -> None:
    """disarm() closes every armed WatchdogTask."""
    calls = []

    class MockWatchdogTask:
        def __init__(self, device: str, timeout: float = 10) -> None:
            pass

        def cfg_watchdog_ao_expir_states(self, states: list[object]) -> None:
            pass

        def start(self) -> None:
            pass

        def reset_timer(self) -> None:
            pass

        def close(self) -> None:
            calls.append("close")

    monkeypatch.setattr(
        "lightsheet.hal.real.laser_watchdog._nidaqmx_watchdog",
        SimpleNamespace(WatchdogTask=MockWatchdogTask),
    )
    monkeypatch.setattr(
        "lightsheet.hal.real.laser_watchdog._nidaqmx_constants",
        SimpleNamespace(WatchdogAOExpirState=SimpleNamespace(VOLTAGE=1)),
    )
    monkeypatch.setattr(
        "lightsheet.hal.real.laser_watchdog._nidaqmx_types",
        SimpleNamespace(AOExpirationState=lambda **kw: kw),
    )

    watchdog = LaserWatchdog([_FakeLaser("/Dev7/ao0", 0.0)])
    watchdog.arm()
    watchdog.disarm()
    assert calls == ["close"]
    # disarm clears the list so a second disarm is a no-op.
    watchdog.disarm()
    assert calls == ["close"]
