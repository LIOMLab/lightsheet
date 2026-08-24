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
writes 0 V, sets ``active=False`` and ``power=0.0``, and returns ``None``
immediately — no thread/queue offload. It is **lock-free**: the per-write
``nidaqmx.Task`` is opened and closed inside ``_write_volts`` and is
independent of any concurrent write, so a daemon ``set_power`` holding
the ``RLock`` on another thread can never delay the E-stop kill path.
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

**Optional V->mW calibration curve (control + display):** an optional list of
``(V, mW)`` breakpoints measured on the rig with a power meter. When loaded,
the calibration curve is used in **both** the control path and the display:

- **Control path**: ``set_power(mw)`` uses the *inverse* curve
  (``np.interp(mw, curve_mw, curve_v)``) to find the voltage that produces
  the desired optical power, instead of the linear ``mw / mw_per_volt``.
  This means the operator's percentage slider maps linearly to actual
  optical power: 0% = off (0 mW), 100% = max measured power (e.g. 107.5 mW),
  50% = half the max power. Without the curve, the slider maps linearly to
  voltage (0% = 0V, 100% = 5V), which is non-linear in optical power due to
  the DPSS threshold knee.

- **max_power override**: when calibrated, ``max_power`` is set to the
  curve's max mW (e.g. 107.5) instead of ``Max Power * mW per Volt`` (300).
  This makes the percentage slider map to the actual optical power range.
  The ``_max_volts`` attribute is set to the curve's max V (5.0) for the
  native-unit V clamp.

- **Display**: ``get_output_power()`` returns ``self.power`` (the commanded
  mW), since the inverse curve ensures the voltage produces that power.

When no curve is loaded (``calibration_curve=None``), behavior is unchanged
— the linear ``mw / mw_per_volt`` conversion is used, ``max_power`` stays
at the config value, and ``calibrated`` is ``False``. The linear model
predicts 300 mW at 5 V, but the rig-measured output is ~107.5 mW at 5 V
(DPSS threshold knee + free-space measurement geometry), so the linear
estimate is unverified until a curve is loaded.
"""

import logging
import threading
from collections.abc import Sequence

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
        calibration_curve: Sequence[tuple[float, float]] | None = None,
    ) -> None:
        # HAL error surface (AGENTS.md §10) — cleared on construct.
        self.error = 0
        self.error_message = ""

        # Validate the mW->V calibration before storing it. A config.ini
        # typo (e.g. `Laser1 mW per Volt = 0`) would otherwise cause a
        # ZeroDivisionError on the first _write_volts clamp and propagate
        # up through the daemon write thread. Surface the misconfiguration
        # on the HAL error surface per AGENTS.md §10 rather than crashing.
        if mw_per_volt <= 0:
            self.error = 1
            self.error_message = (
                f"mw_per_volt must be > 0, got {mw_per_volt!r}"
            )
            logger.error(
                "DAQLaser(%s) constructed with invalid mw_per_volt=%r",
                label,
                mw_per_volt,
            )

        # DAQ AO channel + calibration (D-01).
        self.terminal = terminal
        self.wavelength = wavelength
        self.mw_per_volt = mw_per_volt
        self.max_power = max_power_mw  # mW (canonical)
        self.label = label

        # Optional V->mW calibration curve (display-only — see class
        # docstring). Validate on construct: a malformed curve (non-empty
        # but not strictly-increasing V, or negative mW) is surfaced on the
        # HAL error surface and falls back to None (linear mode) rather than
        # raising — hardware-absence tolerance (AGENTS.md §10). An empty
        # curve is treated as "no curve" (None), not an error.
        self._curve_v: np.ndarray | None = None
        self._curve_mw: np.ndarray | None = None
        self.calibrated = False
        if calibration_curve:
            try:
                pairs = [(float(v), float(mw)) for v, mw in calibration_curve]
            except (TypeError, ValueError) as exc:
                self.error = 1
                self.error_message = (
                    f"calibration_curve has non-numeric entries: {exc}"
                )
                logger.error(
                    "DAQLaser(%s) calibration_curve non-numeric: %r",
                    label,
                    calibration_curve,
                )
            else:
                vs = [v for v, _ in pairs]
                mws = [mw for _, mw in pairs]
                if len(vs) < 2 or vs != sorted(vs) or vs[0] == vs[-1]:
                    self.error = 1
                    self.error_message = (
                        "calibration_curve must have >= 2 points with "
                        "strictly-increasing V"
                    )
                    logger.error(
                        "DAQLaser(%s) calibration_curve not strictly "
                        "increasing: %r",
                        label,
                        vs,
                    )
                elif any(mw < 0 for mw in mws):
                    self.error = 1
                    self.error_message = (
                        "calibration_curve has negative mW entries"
                    )
                    logger.error(
                        "DAQLaser(%s) calibration_curve negative mW: %r",
                        label,
                        mws,
                    )
                else:
                    self._curve_v = np.array(vs)
                    self._curve_mw = np.array(mws)
                    self.calibrated = True
                    # Override max_power to the curve's max mW so the
                    # percentage slider maps to the actual optical power
                    # range (0 to curve_max_mW), not the linear estimate
                    # (0 to Max Power * mW per Volt). Also set _max_volts
                    # to the curve's max V for the native-unit V clamp.
                    self.max_power = float(self._curve_mw[-1])
                    self._max_volts = float(self._curve_v[-1])

        # Laser state — mW canonical (D-01).
        self.power = 0.0
        self.active = False

        # Native-unit V clamp ceiling. When calibrated, set above to the
        # curve's max V. When uncalibrated, derive from the linear model.
        # Used by _write_volts as the independent V safety clamp
        # (AGENTS.md §2 two-layer clamp — the V layer must not depend on
        # the mW layer's clamp).
        if not self.calibrated:
            self._max_volts = (
                self.max_power / self.mw_per_volt
                if self.mw_per_volt > 0
                else 0.0
            )

        # Per-instance reentrant lock (D-02: lock on the ILaser instance,
        # not the controller). RLock so the controller's daemon write paths
        # can re-acquire under the same lock without deadlocking.
        self._lock = threading.RLock()

    def _mw_to_volts(self, mw: float) -> float:
        """Convert desired optical power (mW) to DAQ voltage (V).

        When calibrated, uses the inverse calibration curve
        (``np.interp(mw, curve_mw, curve_v)``) to find the voltage that
        produces the desired optical power. When uncalibrated, uses the
        linear model (``mw / mw_per_volt``).

        Special case: ``mw <= 0`` always returns 0.0 V — the inverse curve
        has a flat zero-power region (below the DPSS threshold knee) where
        ``np.interp`` would return the rightmost V with mW=0 (e.g. 1.5V),
        but 0 mW means "off" and should drive 0V.
        """
        if mw <= 0:
            return 0.0
        if self.calibrated and self._curve_v is not None and self._curve_mw is not None:
            return float(np.interp(mw, self._curve_mw, self._curve_v))
        if self.mw_per_volt <= 0:
            return 0.0
        return mw / self.mw_per_volt

    def _write_volts(self, volts: float) -> None:
        """Write ``volts`` to the DAQ AO channel, clamped to
        ``[0.0, _max_volts]`` (native-unit V clamp — the
        second, independent safety layer per AGENTS.md §2).

        On a DAQ write failure (``nidaqmx.errors.Error`` / ``RuntimeError``
        / ``OSError``) sets ``error=1``, populates ``error_message``,
        reverts ``active=False``, and logs — mirroring
        ``Lasers._update_setpoints`` so the operator never sees a laser
        shown as energized that is actually dark.
        """
        # Native-unit clamp (V) — independent of the mW clamp in set_power.
        # _max_volts is set in __init__: curve max V when calibrated,
        # max_power / mw_per_volt when uncalibrated.
        volts = max(0.0, min(volts, self._max_volts))
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
            self._write_volts(self._mw_to_volts(self.power))

    def off(self) -> None:
        """Synchronous E-stop kill path (AGENTS.md §2).

        Writes 0 V, sets ``active=False`` and ``power=0.0``, and returns
        ``None`` immediately — no thread/queue offload. The GUI-thread
        E-stop handler calls this directly; offloading it would break the
        synchronous-off safety contract for a Class IIIB laser.

        Lock-free: the per-write ``nidaqmx.Task`` is opened and closed
        inside ``_write_volts`` and is independent of any concurrent
        write, so a daemon ``set_power`` holding ``self._lock`` on
        another thread can never delay the E-stop kill path. The
        ``active`` / ``power`` writes are plain CPython bool / float
        attribute stores (atomic under the GIL); a racing ``set_power``
        may stage a new mW value after this returns, but the 0 V DAQ
        write is what actually drives the laser off and that has already
        been issued. The next ``set_power`` / ``on`` call on a non-E-stop
        path will re-write the staged value under the lock.
        """
        self._write_volts(0.0)
        self.active = False
        self.power = 0.0

    def open(self) -> None:
        """No-op lifecycle verb (AGENTS.md §10).

        DAQLaser opens its ``nidaqmx.Task`` per-write inside
        ``_write_volts`` — there is no persistent DAQ connection to open
        here. Returns ``None`` so the controller can call
        ``self.lasers[i].open()`` uniformly across backends.
        """
        return None

    def close(self) -> None:
        """No-op lifecycle verb (AGENTS.md §10).

        Mirrors ``open()``: DAQLaser holds no persistent DAQ connection
        (the per-write ``nidaqmx.Task`` is closed by its ``with`` block),
        so there is nothing to release here. Returns ``None`` so the
        controller can call ``self.lasers[i].close()`` uniformly.
        """
        return None

    def get_output_power(self) -> float | None:
        """Return the output power in milliwatts (mW).

        NI-DAQ analog output has no hardware power readback channel. Returns
        the staged ``self.power`` (mW) — the commanded power. When
        calibrated, the inverse calibration curve in ``set_power`` ensures
        the voltage written to the DAQ actually produces this optical power,
        so the staged value is the real output. When uncalibrated, the
        staged value is a linear-through-origin estimate
        (``mW = V * mw_per_volt``) — the controller's readback label branches
        on ``self.calibrated`` to flag it as unverified vs calibrated.

        Never returns ``None`` (the staged value is always available); the
        ``None`` return is part of the ``ILaser`` contract for backends
        with a real readback that can fail.
        """
        return self.power

    def set_power(self, mw: float) -> None:
        """Set the staged laser power in milliwatts (mW canonical).

        Clamps ``mw`` to ``[0.0, max_power]`` (mW) as the first safety
        layer (AGENTS.md §2). If the laser is active, also writes the
        converted V value to the DAQ AO channel (``_write_volts`` applies
        the second, native-unit V clamp). If inactive, only stages the mW
        value — no DAQ write attempted.

        When calibrated, ``max_power`` is the curve's max mW (e.g. 107.5),
        and the mW→V conversion uses the inverse calibration curve so the
        commanded mW maps to the voltage that actually produces that optical
        power. When uncalibrated, ``max_power`` is the config value (e.g.
        300) and the conversion is linear (``mw / mw_per_volt``).
        """
        mw = max(0.0, min(mw, self.max_power))
        with self._lock:
            self.power = mw
            if self.active:
                self._write_volts(self._mw_to_volts(mw))
