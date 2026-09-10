"""NI-DAQmx hardware watchdog for laser AO channels.

Arms a ``nidaqmx.system.watchdog.WatchdogTask`` per DAQ device that
carries the laser AO channels. Each watched channel is configured to
expire to the laser's ``off_volts`` (0 V for normal polarity, max_volts
for inverted polarity). The acquisition worker calls ``reset()`` once
per plane; if the worker hangs or the process crashes, the DAQ hardware
expires the timer and writes the safe voltage to the laser AO channels.

The watchdog is armed only while an acquisition worker is running so a
long idle period at the GUI cannot trip it. A hard crash (segfault,
interpreter death) or a worker hang longer than the timeout will let
the DAQ device de-energize the lasers.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)

# nidaqmx is absent on the dev machine (conftest stub); the watchdog
# classes are imported lazily so this module still loads. ``None`` marks
# the watchdog path as unavailable.
try:
    import nidaqmx.constants as _nidaqmx_constants
    import nidaqmx.system.watchdog as _nidaqmx_watchdog
    import nidaqmx.types as _nidaqmx_types
except Exception:  # pragma: no cover - exercised on the dev machine
    _nidaqmx_constants = None  # type: ignore[assignment]
    _nidaqmx_watchdog = None  # type: ignore[assignment]
    _nidaqmx_types = None  # type: ignore[assignment]


class LaserWatchdog:
    """Hardware watchdog that drives laser AO channels to their safe
    off-voltage when the acquisition worker stops resetting it.

    ``lasers`` is a list of ``DAQLaser``-like objects that expose a
    ``terminal`` (e.g. ``/Dev7/ao1``) and ``off_volts`` (the voltage that
    turns the laser off). Channels are grouped by DAQ device name so a
    single ``WatchdogTask`` covers all AO channels on that device.

    ``arm()`` is called by the acquisition worker at run start; it creates
    and starts the NI-DAQmx watchdog task. ``disarm()`` is called in the
    worker's ``finally`` so a normal stop/E-stop/pause releases the task
    cleanly. ``reset()`` is called once per plane to keep the watchdog
    from expiring during a healthy run.
    """

    def __init__(self, lasers: list[Any], timeout_s: float = 5.0) -> None:
        self._lasers = lasers
        self._timeout_s = timeout_s
        self._watchdogs: list[Any] = []
        self._lock = threading.Lock()

    def arm(self) -> None:
        """Create and start one WatchdogTask per DAQ device.

        Failures are logged and swallowed so a missing driver, a device
        that does not support watchdog timers, or a stale terminal name
        cannot abort the acquisition.
        """
        with self._lock:
            if self._watchdogs:
                return
            if (
                _nidaqmx_watchdog is None
                or _nidaqmx_constants is None
                or _nidaqmx_types is None
            ):
                logger.warning(
                    "LaserWatchdog disabled: nidaqmx watchdog unavailable"
                )
                return

            by_device: dict[str, list[tuple[str, float]]] = {}
            for laser in self._lasers:
                terminal = getattr(laser, "terminal", None)
                off_volts = getattr(laser, "off_volts", None)
                if not terminal or off_volts is None:
                    continue
                device = str(terminal).strip("/").split("/")[0]
                by_device.setdefault(device, []).append((terminal, off_volts))

            for device, entries in by_device.items():
                try:
                    wt = _nidaqmx_watchdog.WatchdogTask(
                        device, timeout=self._timeout_s
                    )
                    states = [
                        _nidaqmx_types.AOExpirationState(
                            physical_channel=term,
                            expiration_state=volts,
                            output_type=_nidaqmx_constants.WatchdogAOExpirState.VOLTAGE,
                        )
                        for term, volts in entries
                    ]
                    wt.cfg_watchdog_ao_expir_states(states)
                    wt.start()
                    self._watchdogs.append(wt)
                    logger.info(
                        "LaserWatchdog armed on %s (timeout %.1f s, %d channel%s)",
                        device,
                        self._timeout_s,
                        len(entries),
                        "" if len(entries) == 1 else "s",
                    )
                except Exception as exc:
                    logger.warning("LaserWatchdog failed on %s: %s", device, exc)

    def reset(self) -> None:
        """Reset every armed watchdog timer."""
        with self._lock:
            for wt in self._watchdogs:
                try:
                    wt.reset_timer()
                except Exception as exc:
                    logger.warning("LaserWatchdog reset failed: %s", exc)

    def disarm(self) -> None:
        """Stop and release every watchdog task."""
        with self._lock:
            for wt in self._watchdogs:
                try:
                    wt.close()
                except Exception as exc:
                    logger.warning("LaserWatchdog disarm failed: %s", exc)
            self._watchdogs.clear()
