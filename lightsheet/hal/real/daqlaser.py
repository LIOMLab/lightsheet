"""DAQLaser — single-channel NI-DAQ AO laser backend behind the unified
``ILaser`` ABC (mW-canonical).

One ``DAQLaser`` instance wraps one DAQ AO channel (e.g. ``/Dev7/ao0`` for
Laser 1). The controller holds a ``list[ILaser]``; this is the per-channel
real backend for the DAQ-driven lasers.

**mW -> V conversion (D-01):** ``set_power(mw)`` takes milliwatts;
``power`` / ``max_power`` attrs are in mW. The backend converts mW to
Volts via ``mw_per_volt`` (config key ``Laser1 mW per Volt = 60`` =
300 mW max / 5 V full-scale) and writes the Volts value to the DAQ AO
channel.

**Two-layer clamp (AGENTS.md §2 — Class IIIB laser safety):**
1. ``set_power`` clamps ``mw`` to ``[0.0, max_power]`` (mW) before storing
   or writing — the interface-layer clamp.
2. ``_write_volts`` clamps ``volts`` to ``[0.0, max_power / mw_per_volt]``
   (V) before opening the DAQ Task — the native-unit clamp, independent of
   the mW clamp so a config typo in one unit cannot bypass the other
   layer.

**Synchronous ``off()`` (AGENTS.md §2 — E-stop kill path):** ``off()``
acquires the per-instance ``RLock``, writes 0 V, sets ``active=False`` and
``power=0.0``, and returns ``None`` immediately — no thread/queue offload.
The GUI-thread E-stop handler calls this directly; offloading it would
break the synchronous-off safety contract.

**Write-failure revert (mirrors ``Lasers._update_setpoints``):** a DAQ
write failure (``nidaqmx.errors.Error`` / ``RuntimeError`` / ``OSError``)
sets ``error=1``, populates ``error_message``, reverts ``active=False``,
and logs via ``logger.exception`` — the operator never sees a laser shown
as energized that is actually dark.

**Per-instance ``RLock`` (D-02 lock relocation):** the lock lives on the
``ILaser`` instance, not the controller, so the daemon-thread write paths
acquire ``self.lasers[i]._lock`` (reentrant so the controller's
re-acquire-under-same-lock pattern does not deadlock).
"""

import logging
import threading

import nidaqmx
import numpy as np

from lightsheet.hal.interfaces import ILaser

logger = logging.getLogger(__name__)


class DAQLaser(ILaser):
    """Single-channel NI-DAQ AO laser backend (mW-canonical).

    Wraps one DAQ AO channel. mW -> V via ``mw_per_volt``; two-layer clamp
    (mW in ``set_power``, V in ``_write_volts``). ``off()`` is synchronous
    (E-stop kill path). Write failures revert ``active=False`` and surface
    on the HAL error surface.
    """

    def __init__(
        self,
        terminal: str,
        wavelength: int,
        mw_per_volt: float,
        max_power_mw: float,
        label: str,
    ) -> None:
        # HAL error surface (AGENTS.md §10) — cleared on construct.
        self.error = 0
        self.error_message = ""

        # DAQ AO channel + calibration (D-01).
        self.terminal = terminal
        self.wavelength = wavelength
        self.mw_per_volt = mw_per_volt
        self.max_power = max_power_mw  # mW (canonical)
        self.label = label

        # Laser state — mW canonical (D-01).
        self.power = 0.0
        self.active = False

        # Per-instance reentrant lock (D-02: lock on the ILaser instance,
        # not the controller). RLock so the controller's daemon write paths
        # can re-acquire under the same lock without deadlocking.
        self._lock = threading.RLock()

    def _write_volts(self, volts: float) -> None:
        """Write ``volts`` to the DAQ AO channel, clamped to
        ``[0.0, max_power / mw_per_volt]`` (native-unit V clamp — the
        second, independent safety layer per AGENTS.md §2).

        On a DAQ write failure (``nidaqmx.errors.Error`` / ``RuntimeError``
        / ``OSError``) sets ``error=1``, populates ``error_message``,
        reverts ``active=False``, and logs — mirroring
        ``Lasers._update_setpoints`` so the operator never sees a laser
        shown as energized that is actually dark.
        """
        # Native-unit clamp (V) — independent of the mW clamp in set_power.
        volts = max(0.0, min(volts, self.max_power / self.mw_per_volt))
        try:
            with nidaqmx.Task(new_task_name="laser_ao") as task:
                task.ao_channels.add_ao_voltage_chan(self.terminal)
                task.write(np.array([volts]), auto_start=True)
        except (nidaqmx.errors.Error, RuntimeError, OSError) as e:
            # DAQ write failed (driver runtime absent, device disconnected,
            # or hardware fault). Revert active to reflect reality and
            # surface the failure on the HAL error surface the GUI polls
            # after every write.
            self.error = 1
            self.error_message = str(e)
            self.active = False
            logger.exception("DAQLaser write failed")

    def on(self) -> None:
        """Energize the laser — write the staged mW power (converted to V)
        to the DAQ AO channel. Sets ``active=True`` before the write; a
        write failure reverts ``active=False`` inside ``_write_volts``."""
        with self._lock:
            self.active = True
            self._write_volts(self.power / self.mw_per_volt)

    def off(self) -> None:
        """Synchronous E-stop kill path (AGENTS.md §2).

        Writes 0 V, sets ``active=False`` and ``power=0.0``, and returns
        ``None`` immediately — no thread/queue offload. The GUI-thread
        E-stop handler calls this directly; offloading it would break the
        synchronous-off safety contract for a Class IIIB laser.
        """
        with self._lock:
            self._write_volts(0.0)
            self.active = False
            self.power = 0.0

    def set_power(self, mw: float) -> None:
        """Set the staged laser power in milliwatts (mW canonical).

        Clamps ``mw`` to ``[0.0, max_power]`` (mW) as the first safety
        layer (AGENTS.md §2). If the laser is active, also writes the
        converted V value to the DAQ AO channel (``_write_volts`` applies
        the second, native-unit V clamp). If inactive, only stages the mW
        value — no DAQ write attempted.
        """
        mw = max(0.0, min(mw, self.max_power))
        with self._lock:
            self.power = mw
            if self.active:
                self._write_volts(mw / self.mw_per_volt)
