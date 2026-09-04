"""DAQLaser -- single-channel NI-DAQ AO laser backend behind the unified
``ILaser`` ABC (mW-canonical).

One instance wraps one DAQ AO channel. mW -> V conversion is owned by an
injectable voltage-map strategy (``LinearVoltMap`` for normal-polarity L1,
``InvertedVoltMap`` for the rig-measured inverted L2 analog modulation
transfer function). Two-layer power clamp: ``set_power`` clamps mW to
``[0, max_power]``; ``_write_volts`` clamps V to ``[0, volt_map.max_volts]``.
``off()`` is synchronous and lock-free (E-stop kill path) — it writes
``volt_map.off_volts`` (0 V for linear, 5 V for inverted) before clearing
state. Optional V->mW calibration curve overrides the linear conversion for
both control and display.
"""

import logging
import threading
from collections.abc import Sequence
from typing import Protocol

import nidaqmx
import numpy as np

from lightsheet.hal.interfaces import ILaser

logger = logging.getLogger(__name__)


class VoltMap(Protocol):
    """Injectable mW-to-V conversion strategy.

    ``max_volts`` is the V ceiling used by ``_write_volts`` as the
    independent native-unit clamp. ``off_volts`` is the true-off voltage
    written by the synchronous, lock-free ``off()`` (0 V for linear
    normal-polarity lasers, 5 V for inverted-polarity analog modulation
    where 0 V would mean MAXIMUM power). ``to_volts(mw)`` converts desired
    optical power (mW) to the DAQ voltage. ``error`` / ``error_message``
    surface construction-time validation failures (e.g. malformed
    calibration curve, invalid mw_per_volt) so DAQLaser can inherit them
    onto its own HAL error surface.
    """

    max_volts: float
    off_volts: float
    calibrated: bool
    error: int
    error_message: str

    def to_volts(self, mw: float) -> float: ...


class LinearVoltMap:
    """Normal-polarity linear mW-to-V map: ``V = mw / mw_per_volt``.

    The optional V->mW calibration curve overrides the linear conversion
    (inverse ``np.interp``) and overrides ``max_volts`` / the curve-derived
    max power. ``off_volts`` is 0.0 V (normal polarity: 0 V = off).

    Malformed calibration curves surface on the ``error`` / ``error_message``
    attributes and fall back to the linear model — never raises.
    """

    def __init__(
        self,
        mw_per_volt: float,
        max_volts: float,
        calibration_curve: Sequence[tuple[float, float]] | None = None,
        label: str = "",
    ) -> None:
        self.mw_per_volt = mw_per_volt
        self.max_volts = max_volts
        self.off_volts = 0.0
        self.calibrated = False
        self.error = 0
        self.error_message = ""
        self.label = label
        self._curve_v: np.ndarray | None = None
        self._curve_mw: np.ndarray | None = None
        # Curve-derived max power (mW); None when uncalibrated.
        self.max_power_mw: float | None = None

        # Validate mw_per_volt before any conversion; a config typo (e.g. 0)
        # would cause ZeroDivisionError on first write.
        if mw_per_volt <= 0:
            self.error = 1
            self.error_message = f"mw_per_volt must be > 0, got {mw_per_volt!r}"
            logger.error(
                "LinearVoltMap(%s) constructed with invalid mw_per_volt=%r",
                label,
                mw_per_volt,
            )

        # Optional V->mW calibration curve. Malformed curve is surfaced on
        # the error surface and falls back to None.
        if calibration_curve:
            self._parse_calibration_curve(calibration_curve)

    def _parse_calibration_curve(
        self,
        calibration_curve: Sequence[tuple[float, float]],
    ) -> None:
        """Validate and store the calibration curve, overriding max_volts
        and max_power_mw on success. Surfaces errors on self.error."""
        try:
            pairs = [(float(v), float(mw)) for v, mw in calibration_curve]
        except (TypeError, ValueError) as exc:
            self.error = 1
            self.error_message = f"calibration_curve has non-numeric entries: {exc}"
            logger.error(
                "LinearVoltMap(%s) calibration_curve non-numeric: %r",
                self.label,
                calibration_curve,
            )
            return

        vs = [v for v, _ in pairs]
        mws = [mw for _, mw in pairs]
        if len(vs) < 2 or vs != sorted(vs) or vs[0] == vs[-1]:
            self.error = 1
            self.error_message = (
                "calibration_curve must have >= 2 points with strictly-increasing V"
            )
            logger.error(
                "LinearVoltMap(%s) calibration_curve not strictly increasing: %r",
                self.label,
                vs,
            )
            return

        if any(mw < 0 for mw in mws):
            self.error = 1
            self.error_message = "calibration_curve has negative mW entries"
            logger.error(
                "LinearVoltMap(%s) calibration_curve negative mW: %r",
                self.label,
                mws,
            )
            return

        self._curve_v = np.array(vs)
        self._curve_mw = np.array(mws)
        self.calibrated = True
        # Override max_volts and max_power to the curve's endpoints so the
        # slider maps to the actual optical power range.
        self.max_volts = float(self._curve_v[-1])
        self.max_power_mw = float(self._curve_mw[-1])

    def to_volts(self, mw: float) -> float:
        """Convert desired optical power (mW) to DAQ voltage (V).

        When calibrated, uses the inverse calibration curve. When
        uncalibrated, uses the linear model (mw / mw_per_volt). mw <= 0
        always returns 0.0 V (off).
        """
        if mw <= 0:
            return 0.0
        if self.calibrated and self._curve_v is not None and self._curve_mw is not None:
            return float(np.interp(mw, self._curve_mw, self._curve_v))
        if self.mw_per_volt <= 0:
            return 0.0
        return mw / self.mw_per_volt


class InvertedVoltMap:
    """Inverted-polarity mW-to-V map for the rig-measured iBeam analog
    modulation transfer function: ``V = max_volts * (1 - mw / max_power_mw)``.

    0 mW -> max_volts (5 V = true-off), max_power_mw -> 0 V (maximum output).
    Higher requested power = LOWER voltage. ``off_volts`` is ``max_volts``
    (5 V) — writing 0 V on an inverted L2 would drive it to MAXIMUM power
    during E-stop (Class IIIB laser safety).

    Hostile mW inputs are clamped to ``[0, max_power_mw]`` BEFORE the V
    formula, and the V result is independently clamped to ``[0.0, 5.0]`` so
    negative voltage can never reach the iBeam analog input (negative V
    trips the current-clip latch — a documented near-miss).
    """

    def __init__(self, max_volts: float = 5.0, max_power_mw: float = 0.0) -> None:
        self.max_volts = max_volts
        self.max_power_mw = max_power_mw
        self.off_volts = max_volts
        self.calibrated = False
        self.error = 0
        self.error_message = ""
        # No linear mW/V factor for inverted polarity.
        self.mw_per_volt: float | None = None
        self.max_power_mw_curve: float | None = None

    def to_volts(self, mw: float) -> float:
        """Convert desired optical power (mW) to DAQ voltage (V) with
        inverted polarity and double clamping (mW then V)."""
        # Clamp mW to [0, max_power_mw] before the formula.
        mw = max(0.0, min(mw, self.max_power_mw))
        if self.max_power_mw <= 0:
            return self.max_volts  # safe: off
        v = self.max_volts * (1.0 - mw / self.max_power_mw)
        # Clamp V to [0.0, 5.0] — NEVER negative (current-clip latch).
        return max(0.0, min(v, 5.0))


class DAQLaser(ILaser):
    """Single-channel NI-DAQ AO laser backend (mW-canonical).

    Accepts an injectable ``volt_map`` strategy (``LinearVoltMap`` or
    ``InvertedVoltMap``) that owns the mW-to-V conversion and the off-voltage.
    For backwards compatibility, the legacy ``mw_per_volt`` +
    ``calibration_curve`` constructor path builds a ``LinearVoltMap``
    internally.
    """

    def __init__(
        self,
        terminal: str,
        wavelength: int,
        max_power_mw: float = 0.0,
        label: str = "",
        mw_per_volt: float | None = None,
        calibration_curve: Sequence[tuple[float, float]] | None = None,
        readback_backend: ILaser | None = None,
        volt_map: VoltMap | None = None,
    ) -> None:
        # HAL error surface — cleared on construct; inherited from the map.
        self.error = 0
        self.error_message = ""

        self.terminal = terminal
        self.wavelength = wavelength
        self.label = label

        # Build or accept the voltage-map strategy.
        if volt_map is not None:
            self._volt_map = volt_map
        else:
            # Backwards-compatible L1 fallback: build a LinearVoltMap from
            # mw_per_volt + calibration_curve. Compute the V ceiling safely
            # (avoid ZeroDivisionError when mw_per_volt <= 0 — the map
            # validates and surfaces the error itself).
            computed_max_volts = (
                max_power_mw / mw_per_volt
                if mw_per_volt is not None and mw_per_volt > 0
                else 0.0
            )
            self._volt_map = LinearVoltMap(
                mw_per_volt=mw_per_volt if mw_per_volt is not None else 0.0,
                max_volts=computed_max_volts,
                calibration_curve=calibration_curve,
                label=label,
            )

        # Inherit calibration/error state from the map so the existing
        # compatibility surfaces (calibrated, mw_per_volt, _max_volts) work.
        self.calibrated = self._volt_map.calibrated
        self.error = self._volt_map.error
        self.error_message = self._volt_map.error_message
        self.mw_per_volt = getattr(self._volt_map, "mw_per_volt", None)

        # max_power: the curve-derived max overrides the constructor arg
        # when calibrated; otherwise the constructor arg is the mW ceiling.
        curve_max = getattr(self._volt_map, "max_power_mw", None)
        if self.calibrated and curve_max is not None:
            self.max_power = float(curve_max)
        else:
            self.max_power = max_power_mw  # mW (canonical)

        self._max_volts = self._volt_map.max_volts

        # Laser state — mW canonical.
        self.power = 0.0
        self.active = False

        # Per-instance reentrant lock. RLock so controller's daemon write
        # paths can re-acquire without deadlocking.
        self._lock = threading.RLock()

        # Optional reference to the shell's E-stop event. on() re-checks this
        # before writing so a kill that fires between the worker's estop poll
        # and the HAL write cannot re-energize the laser.
        self._estop_event: threading.Event | None = None

        # Optional serial readback backend (e.g. retained IBeamSmartLaser).
        # Used for channel enable at open, power/status readback, and
        # disconnect — NEVER for on/off/set_power emission control. The DAQ
        # AO channel is the sole emission-control path.
        self.readback_backend = readback_backend

    def _mw_to_volts(self, mw: float) -> float:
        """Convert desired optical power (mW) to DAQ voltage (V).

        Delegates to the injectable voltage-map strategy. Preserved as a
        compatibility surface for existing callers/tests.
        """
        return self._volt_map.to_volts(mw)

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

        Re-checks the optional E-stop event before acquiring the lock, right
        before the DAQ write, and again after the write. If E-stop fires in
        any of those windows the channel is driven back to ``off_volts`` and
        ``active`` stays ``False``; off() itself remains lock-free as the
        kill contract requires.
        """
        if self._estop_event is not None and self._estop_event.is_set():
            return
        with self._lock:
            if self._estop_event is not None and self._estop_event.is_set():
                self._write_volts(self._volt_map.off_volts)
                self.active = False
                self.power = 0.0
                return
            self.active = True
            self._write_volts(self._mw_to_volts(self.power))
            if self._estop_event is not None and self._estop_event.is_set():
                self._write_volts(self._volt_map.off_volts)
                self.active = False
                self.power = 0.0

    def off(self) -> None:
        """Synchronous E-stop kill path.

        Writes ``volt_map.off_volts`` to the DAQ AO channel (0 V for linear
        L1, 5 V for inverted L2 — true-off in both cases), sets
        active=False, power=0.0, and returns None immediately — no
        thread/queue offload and no RLock acquisition. Offloading or
        blocking on a daemon write would break the lock-free E-stop kill
        contract for a Class IIIB laser.

        The on() / set_power() critical sections re-check the optional
        ``_estop_event`` before the actual DAQ write and again after it; if
        E-stop fired in flight they drive the channel back to off_volts,
        so the final channel state is always the true-off voltage.

        For inverted L2, writing 0 V would mean MAXIMUM power — off_volts
        is 5 V so E-stop drives the laser to true-off, not to max emission.
        """
        self._write_volts(self._volt_map.off_volts)
        self.active = False
        self.power = 0.0

    def open(self) -> None:
        """Open the DAQ laser for emission.

        When a serial readback backend is attached (e.g. the retained iBeam
        for L2), writes the map's off-voltage to the DAQ AO channel FIRST
        (5 V for inverted L2) so the analog input is at the true-off state
        before any serial setup, then delegates to the readback backend's
        ``open()`` so the serial port is opened and the analog-modulation
        setup sequence runs. If the DAQ off-voltage write fails, serial
        setup is NOT attempted — driving ``laser on`` while the analog
        input is at 0 V on an inverted L2 would command maximum output.

        L1 (no readback backend) open() remains a no-op: the DAQ AO channel
        is opened per-write inside ``_write_volts`` (no persistent DAQ
        connection), so there is nothing to open here. The serial open is
        NOT an emission-control path — the DAQ AO channel is the sole
        emission-control path.
        """
        if self.readback_backend is None:
            # L1 path — no persistent DAQ connection, no serial backend.
            return None
        # L2 path — establish the true-off DAQ state before serial setup.
        # The _write_volts clamp and error surface apply. Save/restore the
        # prior error state so a pre-existing construction error is not
        # masked by a successful off-write.
        prior_error = self.error
        prior_msg = self.error_message
        self._write_volts(self._volt_map.off_volts)
        if self.error:
            # DAQ off-voltage write failed — do not attempt serial setup.
            return None
        # Restore the prior error state so a successful off-write does not
        # mask a pre-existing error from construction (e.g. bad calibration).
        self.error = prior_error
        self.error_message = prior_msg
        self.readback_backend.open()
        # Mirror the readback backend's error surface so the controller
        # can surface channel-enable failures via sig_message.
        self.error = self.readback_backend.error
        self.error_message = self.readback_backend.error_message
        return None

    def close(self) -> None:
        """Close the DAQ laser.

        Delegates to the readback backend's ``close()`` when present so the
        serial port is released. The DAQ AO channel holds no persistent
        connection to close.
        """
        if self.readback_backend is not None:
            self.readback_backend.close()
            self.error = self.readback_backend.error
            self.error_message = self.readback_backend.error_message
        return None

    def get_output_power(self) -> float | None:
        """Return the output power in milliwatts (mW).

        When a serial readback backend is attached (e.g. the retained iBeam),
        delegates to its ``get_output_power()`` for real hardware readback
        (the iBeam reports actual diode output via ``show level power``).
        When no readback backend is present (L1 DAQLaser), returns the
        commanded/staged power — NI-DAQ AO has no hardware power readback.
        When calibrated, the inverse curve ensures the voltage produces this
        optical power. When uncalibrated, the staged value is a linear
        estimate.
        """
        if self.readback_backend is not None:
            value = self.readback_backend.get_output_power()
            if value is not None and not self.readback_backend.error:
                return value
            return None
        return self.power

    def set_power(self, mw: float) -> None:
        """Set the staged laser power in milliwatts (mW canonical).

        Clamps mw to [0.0, max_power] (mW) as the first safety layer — do not
        remove this clamp. If active, also writes converted V to the DAQ AO
        channel (_write_volts applies the second, native-unit V clamp).
        Re-checks the E-stop event so a kill cannot be overwritten by a
        queued power update.
        """
        mw = max(0.0, min(mw, self.max_power))
        with self._lock:
            if self._estop_event is not None and self._estop_event.is_set():
                return
            self.power = mw
            if self.active:
                self._write_volts(self._mw_to_volts(mw))
