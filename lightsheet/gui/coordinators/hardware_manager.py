"""HardwareManager — laser write/toggle/poll collaborator.

Owns the laser daemon threads, per-laser RLock-guarded write paths, status
poll methods, and ``start_lasers``/``stop_lasers``. Does NOT own an
``estop()`` method — the E-stop kill path stays in the shell (lock-free,
GUI-thread, synchronous ``.off()``).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot

from lightsheet.hal.bundle import DeviceBundle

if TYPE_CHECKING:
    from lightsheet.gui.shell.controller import Controller_MainWindow

logger = logging.getLogger(__name__)


class LaserReadbackWorker(QObject):
    """Worker QObject for the iBeam L2 serial readback on a dedicated QThread."""

    sig_finished = Signal()

    def __init__(self, hw: HardwareManager) -> None:
        super().__init__()
        self._hw = hw

    @Slot()
    def start_readback(self) -> None:
        """Runs the L2 readback (idx=1) on the worker thread, then
        signals completion."""
        try:
            self._hw._refresh_laser_readback(1)
        finally:
            self.sig_finished.emit()


class HardwareManager:
    """Laser write/toggle/poll collaborator."""

    def __init__(self, bundle: DeviceBundle, shell: Controller_MainWindow) -> None:
        self._bundle = bundle
        self._shell = shell
        self.lasers = list(bundle.lasers)
        # Tracks the in-flight async iBeam readback QThread so the 1s status
        # timer cannot stack readback threads when the serial round-trip
        # (~3s firmware latency) exceeds the timer interval.
        self._readback_thread: QThread | None = None
        self._readback_worker: LaserReadbackWorker | None = None
        # __init__ performs NO laser HAL lifecycle calls — it runs
        # synchronously before controller.show() and would block the GUI
        # on the serial round-trip.

    # ------------------------------------------------------------------ #
    # iBeam serial-open lifecycle (called post-show from hardware_init).
    # ------------------------------------------------------------------ #

    def open_laser2(self) -> None:
        """Open the L2 laser (self.lasers[1], a DAQLaser on /Dev7/ao1 with
        a retained iBeam serial readback backend).

        The DAQLaser.open() delegates to the iBeam serial open + channel
        enable so the readback path is live. The DAQ AO channel is opened
        per-write inside _write_volts (no persistent connection). Failure is
        non-fatal — the DAQ laser emission path still works if the iBeam
        serial is offline (readback will report None). Called from
        ``hardware_init`` (post-show), NOT from ``__init__`` — calling it in
        ``__init__`` would block on the serial round-trip.
        """
        try:
            self.lasers[1].open()
            if self.lasers[1].error:
                self._shell.sig_message.emit(
                    f"iBeam opened but channel enable failed: "
                    f"{self.lasers[1].error_message}"
                )
                self.lasers[1].error = 0
        except Exception as e:
            self._shell.sig_message.emit(f"iBeam open failed: {e}")

    # ------------------------------------------------------------------ #
    # Laser power write paths (worker-thread HAL writes).
    # ------------------------------------------------------------------ #

    def _write_laser1_power(self, pct: float) -> None:
        """Worker-thread HAL write for laser 1. Scales pct to mW at the HAL
        boundary. Checks estop_event before the HAL write and skips if set.
        """
        with self.lasers[0]._lock:
            if self._shell.estop_event.is_set():
                return
            if self.lasers[0].active:
                mw = pct / 100.0 * self.lasers[0].max_power
                # Re-check E-stop before the HAL write — E-stop is lock-free
                # so it can fire between the top-of-method check and here.
                # Force mw=0 so the write cannot re-energize past the kill path.
                if self._shell.estop_event.is_set():
                    mw = 0.0
                self.lasers[0].set_power(mw)
                if self.lasers[0].error:
                    self._shell.sig_message.emit(
                        f"{self.lasers[0].label} write failed — laser "
                        f"reverted to OFF. Check the hardware connection "
                        f"and re-enable the laser. Cause: "
                        f"{self.lasers[0].error_message}"
                    )
                    self.lasers[0].error = 0
                self._poll_laser_status([0])
                self._refresh_laser_readback(0)

    def _write_laser2_power(self, pct: float) -> None:
        """Worker-thread HAL write for laser 2. Scales pct to mW at the HAL
        boundary. Checks estop_event before the HAL write.
        """
        with self.lasers[1]._lock:
            if self._shell.estop_event.is_set():
                return
            if self.lasers[1].active:
                mw = pct / 100.0 * self.lasers[1].max_power
                if self._shell.estop_event.is_set():
                    mw = 0.0
                self.lasers[1].set_power(mw)
                if self.lasers[1].error:
                    self._shell.sig_message.emit(
                        f"{self.lasers[1].label} write failed — laser "
                        f"reverted to OFF. Check the COM4 USB cable and the "
                        f"iBeam power, then re-enable. Cause: "
                        f"{self.lasers[1].error_message}"
                    )
                    self.lasers[1].error = 0
                self._poll_laser_status([1])
                self._refresh_laser_readback(1)

    # ------------------------------------------------------------------ #
    # Laser toggle paths (worker-thread on/off).
    # ------------------------------------------------------------------ #

    def _toggle_laser1(self) -> None:
        """Worker-thread toggle for laser 1. When energizing, L2 is
        de-energized first (one-laser-energized invariant). The L2 .off()
        runs outside L1's lock so the two locks are never held simultaneously.
        E-stop is re-checked before .on() so a Class IIIB laser is never
        re-energized past the kill path.
        """
        # Cross-deenergize L2 outside L1's lock before energizing L1.
        if (
            not self._shell.estop_event.is_set()
            and not self.lasers[0].active
            and self.lasers[1].active
        ):
            self.lasers[1].off()
            if self.lasers[1].error:
                self._shell.sig_message.emit(
                    f"{self.lasers[1].label} off failed during "
                    f"L1 toggle -- may STILL BE ON. Cause: "
                    f"{self.lasers[1].error_message}"
                )
                self.lasers[1].error = 0
        with self.lasers[0]._lock:
            # Do NOT energize if E-stop fired while this toggle was in flight.
            if self._shell.estop_event.is_set():
                return
            if self.lasers[0].active:
                self.lasers[0].off()
            else:
                self.lasers[0].on()
            # Force off if E-stop fired mid-toggle.
            if self._shell.estop_event.is_set():
                self.lasers[0].off()
                return
            if self.lasers[0].error:
                self._shell.sig_message.emit(
                    f"{self.lasers[0].label} write failed — laser reverted "
                    f"to OFF. Check the hardware connection and re-enable "
                    f"the laser. Cause: {self.lasers[0].error_message}"
                )
                self.lasers[0].error = 0
            elif self.lasers[0].active:
                self._write_laser1_power(self._shell.laser1_power_pct)
            self._poll_laser_status([0])
            self._refresh_laser_readback(0)

    def _toggle_laser2(self) -> None:
        """Worker-thread toggle for laser 2. Symmetric with _toggle_laser1.
        Cross-deenergizes L1 before energizing L2 (one-laser-energized
        invariant); L1 .off() runs outside L2's lock (deadlock-free).
        E-stop is re-checked before .on().
        """
        # Cross-deenergize L1 first, OUTSIDE L2's lock, only when
        # about to energize L2.
        if (
            not self._shell.estop_event.is_set()
            and not self.lasers[1].active
            and self.lasers[0].active
        ):
            self.lasers[0].off()
            if self.lasers[0].error:
                self._shell.sig_message.emit(
                    f"{self.lasers[0].label} off failed during "
                    f"L2 toggle -- may STILL BE ON. Cause: "
                    f"{self.lasers[0].error_message}"
                )
                self.lasers[0].error = 0
        with self.lasers[1]._lock:
            # Do NOT energize if E-stop was pressed while this toggle was in flight.
            if self._shell.estop_event.is_set():
                return
            if self.lasers[1].active:
                self.lasers[1].off()
                if self.lasers[1].error:
                    self._shell.sig_message.emit(
                        f"{self.lasers[1].label} off failed — the laser may "
                        f"STILL BE ON. Manually verify the laser is off "
                        f"before approaching the microscope. Cause: "
                        f"{self.lasers[1].error_message}"
                    )
                    self.lasers[1].error = 0
            else:
                # Re-check before energizing — E-stop may have fired while
                # waiting on the lock or inside the off() branch above.
                if self._shell.estop_event.is_set():
                    return
                self.lasers[1].on()
                if self.lasers[1].error:
                    self._shell.sig_message.emit(
                        f"{self.lasers[1].label} on failed — laser stays "
                        f"OFF. Check COM4 and the iBeam power. Cause: "
                        f"{self.lasers[1].error_message}"
                    )
                    self.lasers[1].error = 0
                    self._poll_laser_status([1])
                    return
                # Apply the staged percentage (scaled to mW).
                self._write_laser2_power(self._shell.laser2_power_pct)
                if self.lasers[1].error:
                    self.lasers[1].off()
            # Refresh status immediately (the gated poll would otherwise lag).
            self._poll_laser_status([1])
            self._refresh_laser_readback(1)

    # ------------------------------------------------------------------ #
    # Acquisition-worker laser start/stop.
    # ------------------------------------------------------------------ #

    def start_lasers(self, energize_lasers: tuple[bool, bool] | None = None) -> None:
        """Start the lasers at staged power. Called from acquisition worker
        threads. Stages power via .set_power(mw) BEFORE .on() so the backend
        writes the staged power when energizing.

        ``energize_lasers`` overrides the cached auto-laser flags for THIS
        call only — used by continuous-mode workers to suppress L2 when both
        checkboxes are checked. When None, the cached flags are read.
        """
        if energize_lasers is not None:
            energize_l1, energize_l2 = energize_lasers
        else:
            energize_l1 = self._shell._auto_laser1
            energize_l2 = self._shell._auto_laser2
        if energize_l1:
            mw = self._shell.laser1_power_pct / 100.0 * self.lasers[0].max_power
            self.lasers[0].set_power(mw)
            self.lasers[0].on()
            # Surface a HAL write failure (backend sets .error, does not raise).
            if self.lasers[0].error:
                self._shell.sig_message.emit(
                    f"{self.lasers[0].label} on failed — laser reverted to "
                    f"OFF. Check the NI DAQ connection (Dev7) and re-enable "
                    f"the laser. Cause: {self.lasers[0].error_message}"
                )
                self.lasers[0].error = 0
        if energize_l2:
            mw = self._shell.laser2_power_pct / 100.0 * self.lasers[1].max_power
            self.lasers[1].set_power(mw)
            self.lasers[1].on()
            if self.lasers[1].error:
                self._shell.sig_message.emit(
                    f"{self.lasers[1].label} on failed — laser reverted to "
                    f"OFF. Check COM4 and the iBeam power. Cause: "
                    f"{self.lasers[1].error_message}"
                )
                self.lasers[1].error = 0
        # Refresh both status labels immediately.
        self._poll_laser_status([0, 1])
        self._refresh_laser_readback(0)
        self._refresh_laser_readback(1)

    def stop_lasers(self) -> None:
        """Stop the lasers. Called from acquisition worker threads. Drives
        both lasers via .off(), reading only the cached auto-laser flags.
        """
        if self._shell._auto_laser1:
            self.lasers[0].off()
            if self.lasers[0].error:
                self._shell.sig_message.emit(
                    f"{self.lasers[0].label} off failed — the laser may "
                    f"STILL BE ON. Manually verify before approaching the "
                    f"microscope. Cause: {self.lasers[0].error_message}"
                )
                self.lasers[0].error = 0
        if self._shell._auto_laser2:
            self.lasers[1].off()
            if self.lasers[1].error:
                self._shell.sig_message.emit(
                    f"{self.lasers[1].label} off failed — the laser may "
                    f"STILL BE ON. Manually verify before approaching the "
                    f"microscope. Cause: {self.lasers[1].error_message}"
                )
                self.lasers[1].error = 0
        # Refresh both status labels immediately.
        self._poll_laser_status([0, 1])
        # Skip L2 readback (~3s serial) — stop_lasers() is called from
        # close_modes() on the GUI thread during E-stop/closeEvent where a
        # 3s GUI freeze is a safety-adjacent UX concern. The periodic timer
        # will refresh L2 readback on its next tick.
        self._refresh_laser_readback(0)

    # ------------------------------------------------------------------ #
    # One-laser-energized invariant choke point.
    # ------------------------------------------------------------------ #

    def select_laser(self, idx: int) -> None:
        """Energize laser ``idx`` and de-energize the other, enforcing the
        one-laser-energized invariant. Called from acquisition worker
        threads in multi-channel mode.

        Sequencing (de-energize-then-energize, with E-stop re-checks):
        1. De-energize the other laser under its own lock.
        2. Re-check estop_event before energizing — do not re-energize
           a Class IIIB laser past the kill path.
        3. Energize the target under its own lock; re-check estop_event
           inside. Stage power before .on().
        4. Refresh both status labels.

        Lock ordering: independent per-instance RLocks, never held
        simultaneously — deadlock-free. E-stop kill path never acquires
        either lock. Out-of-range ``idx`` raises ``IndexError`` before
        any HAL write.
        """
        if idx not in (0, 1):
            raise IndexError(
                f"select_laser: idx={idx} out of range (only two lasers, 0..1)"
            )
        other = 1 - idx
        # 1. De-energize the other laser under its own lock.
        with self.lasers[other]._lock:
            if self.lasers[other].active:
                self.lasers[other].off()
                if self.lasers[other].error:
                    self._shell.sig_message.emit(
                        f"{self.lasers[other].label} off failed during "
                        f"select_laser — may STILL BE ON. Cause: "
                        f"{self.lasers[other].error_message}"
                    )
                    self.lasers[other].error = 0
        # 2. E-stop re-check before energizing.
        if self._shell.estop_event.is_set():
            return
        # 3. Energize the target laser under its own lock.
        with self.lasers[idx]._lock:
            if self._shell.estop_event.is_set():
                return
            if not self.lasers[idx].active:
                # Stage power before .on() so the backend writes staged power.
                pct = (
                    self._shell.laser1_power_pct
                    if idx == 0
                    else self._shell.laser2_power_pct
                )
                mw = pct / 100.0 * self.lasers[idx].max_power
                self.lasers[idx].set_power(mw)
                self.lasers[idx].on()
                if self.lasers[idx].error:
                    self._shell.sig_message.emit(
                        f"{self.lasers[idx].label} on failed during "
                        f"select_laser — laser stays OFF. Cause: "
                        f"{self.lasers[idx].error_message}"
                    )
                    self.lasers[idx].error = 0
        # 4. Refresh both status labels.
        self._poll_laser_status([0, 1])

    # ------------------------------------------------------------------ #
    # Status poll + readback refresh (emit through shell signals).
    # ------------------------------------------------------------------ #

    def _poll_laser_status(self, indices: list[int]) -> None:
        """Emit sig_laser_status(idx, status) on the shell. Status
        precedence: error > active > inactive. The emit crosses the Qt
        signal/slot queue so QLabel mutation happens on the GUI thread.
        """
        for i in indices:
            laser = self.lasers[i]
            if laser.error:
                status = "error"
            elif laser.active:
                status = "active"
            else:
                status = "inactive"
            self._shell.sig_laser_status.emit(i, status)

    def _poll_laser2_status_gated(self) -> None:
        """Gated L2 status + readback poll driven by the ~1s iBeam QTimer.

        Probes self.lasers[1]._lock with acquire(blocking=False): if held
        by an in-progress power write, skip this cycle. The readback
        refresh is offloaded to a daemon thread so the ~3s serial
        round-trip never blocks the GUI event loop.
        """
        if not self.lasers[1]._lock.acquire(blocking=False):
            return
        self.lasers[1]._lock.release()
        self._poll_laser_status([1])
        self._refresh_laser2_readback_async()

    def _refresh_laser2_readback_async(self) -> None:
        """Offload the iBeam (L2) serial readback to a QThread + worker.

        The iBeam serial round-trip takes ~3s; running it on the GUI
        thread would freeze the UI. A guard on self._readback_thread
        prevents stacking when the 1s timer fires faster than the
        round-trip completes.
        """
        if self._readback_thread is not None and self._readback_thread.isRunning():
            return
        self._readback_thread = QThread()
        self._readback_worker = LaserReadbackWorker(self)
        self._readback_worker.moveToThread(self._readback_thread)
        self._readback_thread.started.connect(
            self._readback_worker.start_readback, Qt.DirectConnection  # ty: ignore[unresolved-attribute]
        )
        self._readback_worker.sig_finished.connect(
            self._readback_thread.quit, Qt.DirectConnection  # ty: ignore[unresolved-attribute]
        )
        self._readback_thread.finished.connect(self._readback_worker.deleteLater)
        self._readback_thread.start()

    def _refresh_laser_readback(self, idx: int) -> None:
        """Query get_output_power() and emit readback text + tooltip via
        sig_laser_readback. Acquires the laser's lock with
        acquire(blocking=False): if held, returns silently. Thread-safe
        by design — the QLabel mutation is deferred to the GUI-thread slot.

        L1 (DAQLaser, idx=0) has no hardware readback — get_output_power()
        returns a staged or curve-interpolated mW estimate. The label
        suffix distinguishes calibrated ('(cal.)') from unverified linear
        estimate ('(est.)'). L2 (DAQLaser on /Dev7/ao1 with retained iBeam
        serial readback, idx=1) delegates to the iBeam serial readback
        (show level power) and may return None (fallback to commanded value)
        when the serial is offline or the parse fails.
        """
        laser = self.lasers[idx]
        if not laser._lock.acquire(blocking=False):
            return
        try:
            value = laser.get_output_power()
            if value is not None:
                if idx == 0:
                    # L1 (DAQLaser) — no hardware readback; flag estimate vs calibrated.
                    if getattr(laser, "calibrated", False):
                        self._shell.sig_laser_readback.emit(
                            idx,
                            f"{value:.1f} mW (cal.)",
                            "Calibrated estimate from a measured V→mW "
                            "curve. (DAQLaser has no live hardware "
                            "readback; this is the curve-interpolated "
                            "value at the commanded voltage.)",
                        )
                    else:
                        self._shell.sig_laser_readback.emit(
                            idx,
                            f"{value:.1f} mW (est.)",
                            "Linear-through-origin estimate "
                            "(mW = V * mW_per_volt). Unverified — the "
                            "linear model predicts 300 mW at 5V, but "
                            "the rig-measured output is ~107.5 mW at 5V. "
                            "Run the rig calibration sweep to load a "
                            "measured V->mW curve.",
                        )
                else:
                    self._shell.sig_laser_readback.emit(idx, f"{value:.1f} mW", "")
            else:
                self._shell.sig_laser_readback.emit(
                    idx,
                    f"{laser.power:.1f} mW (cmd)",
                    "Power readback unavailable (parse failure or this "
                    "variant does not support readback). Showing last "
                    "commanded value may be stale.",
                )
        finally:
            laser._lock.release()
