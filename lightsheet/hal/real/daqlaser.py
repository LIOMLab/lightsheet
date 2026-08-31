"""DAQLaser -- single-channel NI-DAQ AO laser backend behind the unified
``ILaser`` ABC (mW-canonical).

One instance wraps one DAQ AO channel. mW -> V conversion via ``mw_per_volt``.
Two-layer power clamp: ``set_power`` clamps mW to [0, max_power]; ``_write_volts``
clamps V to [0, max_power/mw_per_volt]. ``off()`` is synchronous (E-stop kill path).
Optional V->mW calibration curve overrides the linear conversion for both control
and display.
"""

import logging
import threading
from collections.abc import Sequence

import nidaqmx
import numpy as np

from lightsheet.hal.interfaces import ILaser

logger = logging.getLogger(__name__)


class DAQLaser(ILaser):
    """Single-channel NI-DAQ AO laser backend (mW-canonical)."""

    def __init__(
        self,
        terminal: str,
        wavelength: int,
        mw_per_volt: float,
        max_power_mw: float,
        label: str,
        calibration_curve: Sequence[tuple[float, float]] | None = None,
    ) -> None:
        # HAL error surface — cleared on construct.
        self.error = 0
        self.error_message = ""

        # Validate mw_per_volt before storing; a config typo (e.g. 0) would
        # cause ZeroDivisionError on first write.
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

        # DAQ AO channel + calibration.
        self.terminal = terminal
        self.wavelength = wavelength
        self.mw_per_volt = mw_per_volt
        self.max_power = max_power_mw  # mW (canonical)
        self.label = label

        # Optional V->mW calibration curve. Malformed curve is surfaced on
        # the HAL error surface and falls back to None.
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
                    # Override max_power to curve's max mW so slider maps to
                    # actual optical power range.
                    self.max_power = float(self._curve_mw[-1])
                    self._max_volts = float(self._curve_v[-1])

        # Laser state — mW canonical.
        self.power = 0.0
        self.active = False

        # Native-unit V clamp ceiling. Used by _write_volts as the
        # independent V safety clamp.
        if not self.calibrated:
            self._max_volts = (
                self.max_power / self.mw_per_volt
                if self.mw_per_volt > 0
                else 0.0
            )

        # Per-instance reentrant lock. RLock so controller's daemon write
        # paths can re-acquire without deadlocking.
        self._lock = threading.RLock()

    def _mw_to_volts(self, mw: float) -> float:
        """Convert desired optical power (mW) to DAQ voltage (V).

        When calibrated, uses the inverse calibration curve. When uncalibrated,
        uses the linear model (mw / mw_per_volt). mw <= 0 always returns 0.0 V.
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
        [0.0, _max_volts] (native-unit V safety clamp).

        Do not remove this clamp — it is the second, independent safety layer.
        On DAQ write failure, sets error=1, reverts active=False, and logs.
        """
        # Native-unit clamp (V) — independent of the mW clamp in set_power.
        volts = max(0.0, min(volts, self._max_volts))
        try:
            with nidaqmx.Task(new_task_name="laser_ao") as task:
                task.ao_channels.add_ao_voltage_chan(self.terminal)
                task.write(np.array([volts]), auto_start=True)
        except (nidaqmx.errors.Error, RuntimeError, OSError) as e:
            # DAQ write failed — revert active and surface on HAL error surface.
            self.error = 1
            self.error_message = str(e)
            self.active = False
            logger.exception("DAQLaser write failed")

    def on(self) -> None:
        """Energize the laser -- write staged mW power to DAQ AO channel.

        Write failure reverts active=False.
        """
        with self._lock:
            self.active = True
            self._write_volts(self._mw_to_volts(self.power))

    def off(self) -> None:
        """Synchronous E-stop kill path.

        Writes 0 V, sets active=False, power=0.0, returns None immediately.

        No thread/queue offload — offloading would break the synchronous-off
        safety contract for a Class IIIB laser. Lock-free: the per-write
        nidaqmx.Task is independent of any concurrent write.
        """
        self._write_volts(0.0)
        self.active = False
        self.power = 0.0

    def open(self) -> None:
        """No-op lifecycle verb -- DAQLaser opens its nidaqmx.Task per-write
        inside _write_volts."""
        return None

    def close(self) -> None:
        """No-op lifecycle verb — DAQLaser holds no persistent DAQ connection."""
        return None

    def get_output_power(self) -> float | None:
        """Return the output power in milliwatts (mW) — the commanded power.

        NI-DAQ AO has no hardware power readback. When calibrated, the inverse
        curve ensures the voltage produces this optical power. When uncalibrated,
        the staged value is a linear estimate. Never returns None.
        """
        return self.power

    def set_power(self, mw: float) -> None:
        """Set the staged laser power in milliwatts (mW canonical).

        Clamps mw to [0.0, max_power] (mW) as the first safety layer — do not
        remove this clamp. If active, also writes converted V to DAQ AO channel
        (_write_volts applies the second, native-unit V clamp).
        """
        mw = max(0.0, min(mw, self.max_power))
        with self._lock:
            self.power = mw
            if self.active:
                self._write_volts(self._mw_to_volts(mw))
