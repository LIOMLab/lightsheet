"""HardwareManager — god-object split collaborator.

Owns the laser write/toggle daemon threads, the per-laser RLock-guarded
write paths, both status-poll methods, and ``start_lasers``/``stop_lasers``.

Does NOT own an ``estop()``/kill-path method of any kind (safety
anti-pattern, the pitfall). The E-stop kill path
(``Controller_MainWindow.updateUi_estop_pressed``) stays in the thin shell
with a direct ``list[ILaser]`` ref, lock-free, on the GUI thread. A future
maintainer who sees ``HardwareManager.estop()`` will be tempted to
queue/thread it — the single most safety-critical regression risk.

This is a plain-Python object (NOT a ``QObject``) per the plain-Python collaborator pattern
1: collaborators emit through a shell reference, never declare their own
``Signal``, and never call ``.connect()``. The shell-owned state
(``sig_message``, ``estop_event``, ``_auto_laser1``/``_auto_laser2``,
``laser1_power_pct``/``laser2_power_pct``) is read off the shell reference
— these cached-flag/percentage values are sampled on the GUI thread by
``_cache_auto_laser_flags()`` and the amplitude spinbox slots, which stay
in the shell. The manager holds its own ``self.lasers = bundle.lasers``
reference (identical objects to ``shell.lasers``).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QObject, QThread, Signal, Slot

from lightsheet.hal.bundle import DeviceBundle

if TYPE_CHECKING:
    from lightsheet.gui.controller import Controller_MainWindow

logger = logging.getLogger(__name__)


class LaserReadbackWorker(QObject):
    """Worker ``QObject`` for the iBeam L2 serial readback, affined to a
    dedicated ``QThread`` via ``moveToThread``.

    Fire-and-forget single-shot: ``start_readback`` runs the serial query
    on the worker thread (calling ``HardwareManager._refresh_laser_readback``
    which emits the result via the shell's ``sig_laser_readback`` signal —
    a thread-safe Qt signal that crosses to the GUI thread for the QLabel
    mutation). When the readback completes, ``sig_finished`` emits which
    quits the thread's event loop via a direct connection (so the thread
    exits without waiting for the main thread's event loop to process a
    queued quit).
    """

    sig_finished = Signal()

    def __init__(self, hw: "HardwareManager") -> None:
        super().__init__()
        self._hw = hw

    @Slot()
    def start_readback(self) -> None:
        """Entry point connected to QThread.started — runs the L2 readback
        (idx=1, the iBeam) on the worker thread, then signals completion."""
        try:
            self._hw._refresh_laser_readback(1)
        finally:
            self.sig_finished.emit()


class HardwareManager:
    """Laser write/toggle/poll collaborator.

    All laser write/toggle logic moved verbatim from
    ``Controller_MainWindow`` — only the attribute-access prefix changes
    (``self.`` -> ``self._shell.`` for shell-owned state; ``self.lasers``
    stays ``self.lasers`` since the manager holds its own bundle.lasers
    reference). Every existing ``if self.estop_event.is_set(): return`` /
    ``mw = 0.0`` re-check survives unchanged (the E-stop cooperative-skip mitigation).
    """

    def __init__(self, bundle: DeviceBundle, shell: "Controller_MainWindow") -> None:
        self._bundle = bundle
        self._shell = shell
        # Direct list[ILaser] for daemon-thread writes — identical objects
        # to shell.lasers (the shell's list copy of the bundle's tuple).
        # The per-laser RLock already lives on each ILaser instance.
        self.lasers = list(bundle.lasers)
        # Tracks the in-flight async iBeam readback QThread so the 1s status
        # timer cannot stack readback threads when the serial round-trip
        # (~3s firmware latency) exceeds the timer interval. See
        # _refresh_laser2_readback_async.
        self._readback_thread: QThread | None = None
        self._readback_worker: LaserReadbackWorker | None = None
        # NOTE: __init__ deliberately performs NO laser HAL lifecycle
        # calls (no .open()/.on()/.set_power()). It runs synchronously in
        # main()'s composition root BEFORE controller.show() — calling
        # the iBeam serial open here would block the GUI window on the
        # serial round-trip. The iBeam serial open is driven post-show
        # from hardware_init via open_laser2() (see below), preserving
        # the pre-extraction 100ms-timer-triggered timing exactly.

    # ------------------------------------------------------------------ #
    # iBeam serial-open lifecycle (called post-show from hardware_init).
    # ------------------------------------------------------------------ #

    def open_laser2(self) -> None:
        """Open the Toptica iBeam serial laser (COM4 / self.lasers[1]).

        Moved verbatim from ``Controller_MainWindow.hardware_init``'s inline
        iBeam serial-open try/except block. The IBeamSmartLaser
        adapter constructs the inner IBeam serial engine in ``__init__`` but
        does NOT open the serial port — ``open()`` is a real-hardware
        lifecycle verb driven here, mirroring the pre-rewrite pattern.

        Failure is non-fatal — the DAQ laser path still works if the iBeam
        is offline — but the error is surfaced via ``sig_message`` so the
        operator knows the red laser is unavailable. ``open()`` calls
        ``enable_channel()`` internally; ``enable_channel()`` catches
        ``SerialException`` and sets ``self.error`` without re-raising, so a
        plain ``try/except`` around ``open()`` cannot detect a channel-enable
        failure — the error surface must be inspected after ``open()``
        returns.

        Timing invariant: this method is invoked from ``hardware_init``
        (the 100ms ``timer_hardware_init`` callback), which cannot fire
        until the Qt event loop is pumping via ``app.exec()`` (i.e. after
        ``controller.show()``). It is NOT called from ``__init__`` — that
        would block the composition root on the serial round-trip.
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
        """Worker-thread HAL write for laser 1. Scales the staged percentage
        to mW at the HAL boundary (pct/100 * max_power) and calls
        self.lasers[0].set_power(mw). The DAQLaser backend converts mW -> V
        internally and clamps both units (two-layer safety, AGENTS.md §2).

        Cooperative-skip: checks estop_event immediately before the HAL write
        and skips entirely if set — the E-stop has already driven laser 1 off
        with its own synchronous write, and a queued amplitude write must not
        re-energize or mutate its state after that point. The lock lives on
        the ILaser instance (self.lasers[0]._lock), not the manager.
        """
        with self.lasers[0]._lock:
            if self._shell.estop_event.is_set():
                return
            if self.lasers[0].active:
                mw = pct / 100.0 * self.lasers[0].max_power
                # Re-check E-stop immediately before the HAL write — E-stop
                # is intentionally lock-free (it runs on the GUI thread and
                # zeroes the laser via .off() without taking this lock), so
                # it can fire between the top-of-method check and this
                # point. If it did, force mw = 0 so the HAL write cannot
                # re-energize the laser past the kill path.
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
                # Refresh-after-action: the status label reflects the
                # post-write state immediately, not just on the 100ms
                # timer tick.
                self._poll_laser_status([0])
                self._refresh_laser_readback(0)

    def _write_laser2_power(self, pct: float) -> None:
        """Worker-thread HAL write for laser 2. Scales the staged percentage
        to mW at the HAL boundary (pct/100 * max_power) and calls
        self.lasers[1].set_power(mw). The IBeamSmartLaser adapter converts
        mW -> µW internally and the inner IBeam.set_power clamps µW as a
        second physical-safety layer.

        Cooperative-skip: checks estop_event immediately before the HAL write
        and skips entirely if set — the E-stop has already driven laser 2 off
        with its own synchronous write. The lock lives on the ILaser instance
        (self.lasers[1]._lock, identity-shared with the inner IBeam._lock).
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
                # Refresh-after-action: the iBeam status label reflects
                # the post-write state immediately (the gated ~1s poll
                # would otherwise lag up to a second behind the write).
                self._poll_laser_status([1])
                self._refresh_laser_readback(1)

    # ------------------------------------------------------------------ #
    # Laser toggle paths (worker-thread on/off).
    # ------------------------------------------------------------------ #

    def _toggle_laser1(self) -> None:
        """Worker-thread toggle for laser 1. Toggles self.lasers[0], and if
        it was just turned on, immediately applies the staged percentage
        (scaled to mW) so the operator sees the chosen power, not 0.
        HAL failures are surfaced via sig_message. The lock lives on the
        ILaser instance (self.lasers[0]._lock)."""
        with self.lasers[0]._lock:
            # E-stop cooperative-skip: if E-stop was pressed while this
            # toggle thread was in flight (waiting on the lock or before it
            # was scheduled), do NOT energize. The E-stop path already drove
            # the laser off synchronously on the GUI thread via .off();
            # a queued toggle that calls .on() would re-energize a Class
            # IIIB laser past the kill path. E-stop must be the final word.
            if self._shell.estop_event.is_set():
                return
            if self.lasers[0].active:
                self.lasers[0].off()
            else:
                self.lasers[0].on()
            # Re-check after the toggle — E-stop may have fired mid-toggle
            # (between .on()/.off() returning and this line). If it did,
            # force the laser back off and do not apply the staged power.
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
                # Just turned on — apply the staged percentage (scaled).
                # _write_laser1_power re-acquires the same RLock (reentrant)
                # and checks estop_event before the write.
                self._write_laser1_power(self._shell.laser1_power_pct)
            # Refresh-after-action: the status label reflects the
            # post-toggle state immediately (the 100ms timer would
            # otherwise lag up to 100ms behind the toggle).
            self._poll_laser_status([0])
            self._refresh_laser_readback(0)

    def _toggle_laser2(self) -> None:
        """Worker-thread toggle for laser 2. Symmetric with _toggle_laser1
        — both operate on self.lasers[i] uniformly. The IBeamSmartLaser
        adapter's .on() mirrors active from the inner _is_on and guards on
        the inner error surface, so the controller no longer needs its own
        iBeam-specific verify-before-mark-active branch. The lock lives on
        the ILaser instance (self.lasers[1]._lock, identity-shared with the
        inner IBeam._lock)."""
        with self.lasers[1]._lock:
            # E-stop cooperative-skip: if E-stop was pressed while this
            # toggle thread was in flight, do NOT energize. The E-stop path
            # already drove the laser off synchronously on the GUI thread
            # via .off(); a queued toggle that calls .on() would re-enable
            # emission of a Class IIIB laser past the kill path.
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
                # we were waiting on the lock or inside the off() branch
                # above. Do not call .on() if the kill path has run.
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
                # _write_laser2_power re-acquires the same RLock (reentrant)
                # and checks estop_event before the write.
                self._write_laser2_power(self._shell.laser2_power_pct)
                if self.lasers[1].error:
                    self.lasers[1].off()
            # Refresh-after-action: the iBeam status label reflects the
            # post-toggle state immediately (the gated ~1s poll would
            # otherwise lag up to a second behind the toggle).
            self._poll_laser_status([1])
            self._refresh_laser_readback(1)

    # ------------------------------------------------------------------ #
    # Acquisition-worker laser start/stop.
    # ------------------------------------------------------------------ #

    def start_lasers(self) -> None:
        """Starts the lasers at a certain power. Called from acquisition
        worker threads (not the GUI thread), so no further nested thread is
        needed — only the %-to-absolute scaling at the HAL boundary.

        Drives self.lasers[0] and self.lasers[1] uniformly: stage the
        scaled power via .set_power(mw) BEFORE .on() so the DAQLaser
        backend writes the staged power when it energizes the AO channel,
        and the IBeamSmartLaser adapter stages the channel power before
        enabling global emission.

        The auto-laser flags (self._shell._auto_laser1 / _auto_laser2) are
        sampled on the GUI thread by _cache_auto_laser_flags() before the
        worker is spawned, so this method reads only cached bools and never
        touches a Qt widget (AGENTS.md §11).
        """
        if self._shell._auto_laser1:
            mw = self._shell.laser1_power_pct / 100.0 * self.lasers[0].max_power
            self.lasers[0].set_power(mw)
            self.lasers[0].on()
            # Surface a HAL write failure to the operator. The backend's
            # .on() catches the write failure, sets .error = 1, mirrors
            # .active = False, and deliberately does NOT raise (hardware-
            # absence tolerance). The caller is responsible for reading the
            # flag — a failed laser start during acquisition was previously
            # a silent no-op (PSU dark, no message).
            if self.lasers[0].error:
                self._shell.sig_message.emit(
                    f"{self.lasers[0].label} on failed — laser reverted to "
                    f"OFF. Check the NI DAQ connection (Dev7) and re-enable "
                    f"the laser. Cause: {self.lasers[0].error_message}"
                )
                self.lasers[0].error = 0
        if self._shell._auto_laser2:
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
        # Refresh-after-action: both status labels reflect the post-start
        # state immediately (the periodic timers would otherwise lag).
        self._poll_laser_status([0, 1])
        self._refresh_laser_readback(0)
        self._refresh_laser_readback(1)

    def stop_lasers(self) -> None:
        """Stops the lasers. Called from acquisition worker threads (not the
        GUI thread). Drives self.lasers[0] and self.lasers[1] uniformly via
        .off(). Reads only the cached auto-laser flags sampled on the GUI
        thread by _cache_auto_laser_flags() — never a Qt widget
        (AGENTS.md §11)."""
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
        # Refresh-after-action: both status labels reflect the post-stop
        # state immediately (the periodic timers would otherwise lag).
        self._poll_laser_status([0, 1])
        self._refresh_laser_readback(0)
        self._refresh_laser_readback(1)

    # ------------------------------------------------------------------ #
    # Status poll + readback refresh (emit through shell signals).
    # ------------------------------------------------------------------ #

    def _poll_laser_status(self, indices: list[int]) -> None:
        """Compute a status string per requested laser index and emit
        sig_laser_status(idx, status) on the shell. Called from the L1
        100ms display timer, the L2 gated ~1s iBeam timer, and the
        refresh-after-action call sites (toggle / write / start / stop /
        E-stop).

        Status precedence is error > active > inactive: an errored-but-
        still-active laser shows ERR, not ON (the HAL error surface is
        authoritative — AGENTS.md §10). The emit crosses through the Qt
        signal/slot queue so the QLabel mutation happens on the GUI
        thread (AGENTS.md §11 — no direct widget write from a timer).
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
        """Gated L2 status + readback poll driven by the ~1s iBeam status
        QTimer.

        Probes self.lasers[1]._lock with acquire(blocking=False): if the
        lock is held by an in-progress power write, skip this cycle
        silently (no error surfaced — the operator can retry via the
        Refresh button or wait for the next tick). If the lock is free,
        release it immediately and proceed with the status poll + the
        readback refresh. The status poll reads only instant in-HAL
        attributes (.error / .active — no serial I/O, no misattribution
        risk); the readback refresh is offloaded to a daemon thread via
        _refresh_laser2_readback_async so the ~3s iBeam serial round-trip
        never blocks the GUI event loop. The probe-then-release pattern
        means a write can start between the probe and the readback's own
        acquire, but the readback's acquire(blocking=False) will then
        skip — the operator simply sees the next tick's reading.
        """
        if not self.lasers[1]._lock.acquire(blocking=False):
            return
        self.lasers[1]._lock.release()
        self._poll_laser_status([1])
        self._refresh_laser2_readback_async()

    def _refresh_laser2_readback_async(self) -> None:
        """Offload the iBeam (L2) serial readback to a QThread + worker
        QObject.

        The iBeam serial round-trip (show level power) takes ~3s due to
        firmware response latency. Running it on the GUI thread — as the
        1s status QTimer and the refresh-after-action call sites
        previously did — freezes the UI for the duration of every
        round-trip. This spawns a QThread with a LaserReadbackWorker that
        calls _refresh_laser_readback(1) on the worker thread, which
        performs the serial query and emits the result via
        sig_laser_readback (a thread-safe Qt signal — the QLabel mutation
        happens on the GUI thread in the slot, per AGENTS.md §11).

        A guard on self._readback_thread prevents stacking when the 1s
        timer fires faster than the ~3s round-trip completes: if a prior
        readback thread is still running, this call is a no-op and the
        next timer tick retries. The L1/DAQLaser readback
        (_refresh_laser_readback(0)) stays synchronous — it returns the
        staged mW power with no serial I/O, so there is nothing to
        offload.

        The readback thread is fire-and-forget (single-shot): the worker's
        do_readback slot runs the query, emits sig_finished which quits
        the thread's event loop, and the thread exits.
        """
        if (
            self._readback_thread is not None
            and self._readback_thread.isRunning()
        ):
            return
        self._readback_thread = QThread()
        self._readback_worker = LaserReadbackWorker(self)
        self._readback_worker.moveToThread(self._readback_thread)
        self._readback_thread.started.connect(
            self._readback_worker.start_readback, Qt.DirectConnection
        )
        self._readback_worker.sig_finished.connect(
            self._readback_thread.quit, Qt.DirectConnection
        )
        self._readback_thread.finished.connect(self._readback_worker.deleteLater)
        self._readback_thread.start()

    def _refresh_laser_readback(self, idx: int) -> None:
        """Query self.lasers[idx].get_output_power() and emit the readback
        text + tooltip on the shell's sig_laser_readback for the GUI-thread
        slot to apply. Acquires the laser's per-instance lock with
        acquire(blocking=False): if held by an in-progress write, return
        silently (no-op — the operator can retry). On success, query and
        emit, then release in finally.

        Thread-safe by design: the HAL query (get_output_power) is
        lock-protected and the QLabel mutation is deferred to the
        GUI-thread slot via the signal, so this method is safe to call
        from any thread (QTimer callback or acquisition worker) per
        AGENTS.md §11 — no worker thread ever writes a QLabel directly.

        On a populated readback (float mW): emits text '{value:.1f} mW'
        with an empty tooltip (clears any prior stale-value warning). On a
        None readback (parse failure / unsupported variant): emits text
        '{power:.1f} mW (cmd)' — the last commanded power — with a tooltip
        explaining the fallback so the operator can distinguish a live
        readback from a stale commanded value.

        L1 (DAQLaser, idx=0) has no hardware readback — get_output_power()
        returns either the staged mW (linear-through-origin estimate, no
        calibration curve loaded) or a curve-interpolated mW (calibrated).
        The label suffix distinguishes the two so the operator knows
        whether the number is an unverified linear estimate or a
        rig-measured calibration: '(est.)' when uncalibrated, '(cal.)'
        when a V->mW curve is loaded. The linear model predicts 300 mW
        at 5V, but the rig-measured output is ~107.5 mW at 5V (DPSS
        threshold knee + free-space measurement geometry), so the
        unverified estimate is flagged explicitly.

        Works for both lasers: idx=0 (L1/DAQLaser — staged or
        curve-interpolated mW, never None) and idx=1 (L2/iBeam —
        get_output_power() queries the serial readback, may return None).
        """
        laser = self.lasers[idx]
        if not laser._lock.acquire(blocking=False):
            return
        try:
            value = laser.get_output_power()
            if value is not None:
                if idx == 0:
                    # L1 (DAQLaser) — no hardware readback. Branch on
                    # calibrated to flag unverified linear estimate vs
                    # rig-measured curve interpolation.
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
                    self._shell.sig_laser_readback.emit(
                        idx, f"{value:.1f} mW", ""
                    )
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
