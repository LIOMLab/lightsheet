"""Adaptive power/exposure method mixin for StackWorker.

The two adaptive helper methods are kept as methods on ``StackWorker``
through inheritance so callers still invoke them on the worker instance.
"""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING, cast

from lightsheet.adaptive.types import AdaptiveCommand, AdaptiveConfig
from lightsheet.resume import ManifestUpdate
from lightsheet.state import AppliedMicroscopeSnapshot

if TYPE_CHECKING:
    from lightsheet.gui.workers.stack import StackWorker

logger = logging.getLogger(__name__)


def _lightsheet_line_time_from_exposure(exposure_s: float, exposed_lines: int) -> float:
    """Convert a total per-plane integration time (seconds) into the
    per-line time (seconds) the camera applies in Lightsheet mode.

    The divisor is always the camera's ``lightsheet_exposed_lines`` —
    adaptive control varies only the line time, never the exposed/delay
    line counts. Non-finite or non-positive inputs would produce an
    unsafe acquisition timing, so they are rejected loudly.
    """
    if not isinstance(exposure_s, (int, float)) or isinstance(exposure_s, bool):
        raise ValueError(f"exposure_s must be numeric; got {type(exposure_s)}")
    if not math.isfinite(exposure_s) or exposure_s <= 0:
        raise ValueError(f"exposure_s must be finite and positive; got {exposure_s}")
    if not isinstance(exposed_lines, int) or isinstance(exposed_lines, bool):
        raise ValueError(f"exposed_lines must be an int; got {type(exposed_lines)}")
    if exposed_lines <= 0:
        raise ValueError(f"exposed_lines must be positive; got {exposed_lines}")
    return exposure_s / exposed_lines


class _StackAdaptiveMixin:
    """Mixin providing the per-plane adaptive power/exposure methods.

    Kept as methods on StackWorker through inheritance so callers still
    invoke ``self._apply_adaptive_command`` and ``self._record_adaptive_step``.
    """

    def _apply_adaptive_command(self: StackWorker, cmd: AdaptiveCommand) -> None:
        """Apply an AdaptiveCommand to the hardware before acquiring.

        Sets the camera exposure and writes the laser power through the
        existing safe HAL paths. The E-stop check lives inside
        ``_write_laser1_power`` (cooperative-skip) — a mid-write E-stop
        zeroes the power and the loop-top poll on the next iteration
        breaks.

        Applied values are published back to the GUI-thread model as one
        frozen ``AppliedMicroscopeSnapshot`` on the queued
        ``sig_applied_state`` signal — the worker never mutates the model
        or the widgets directly. The mock camera's scripted-intensity hook
        reads the HAL-applied ``ILaser.power`` after ``set_power``, so the
        staged-percent update lands on the worker thread before the next
        plane's intensity measurement and no cross-thread sharing is
        needed.
        """
        # Set camera exposure. This lives OUTSIDE the per-laser exception
        # handlers below — a laser write failure must not skip the camera
        # exposure for this plane (the next plane's loop-top E-stop poll
        # is the abort point).
        #
        # Rolling/Global: cmd.exposure_s is the frame exposure; convert
        # seconds to ms for the HAL set_exposure_time register.
        #
        # Lightsheet: cmd.exposure_s is the total per-plane integration
        # time; the per-line time is exposure_s / lightsheet_exposed_lines.
        # Writing set_exposure_time here would poke the separate
        # Rolling/Global delay/exposure register and break external-trigger
        # timing, so the Lightsheet path instead assigns
        # camera.lightsheet_line_time and applies it through
        # set_lightsheet_mode(), which synchronizes the applied line_time
        # from the SDK/mock readback. A changed applied line time
        # invalidates the DAQ waveforms (they embed the per-line timing),
        # so compute_scan_waveforms is re-run before the plane is acquired
        # — but only on an actual change, so an unchanged command does not
        # allocate a second waveform buffer.
        shutter_mode = getattr(self.camera, "shutter_mode", "Rolling")
        applied_line_time_s: float | None = None
        if shutter_mode == "Lightsheet":
            previous_line_time = getattr(self.camera, "line_time", None)
            previous_intent = self.camera.lightsheet_line_time
            self.camera.lightsheet_line_time = _lightsheet_line_time_from_exposure(
                cmd.exposure_s, self.camera.lightsheet_exposed_lines
            )
            try:
                self.camera.set_lightsheet_mode()
            except Exception:
                # A rejected set_lightsheet_mode must not leave the
                # refused candidate assigned to lightsheet_line_time —
                # every later arm_scan re-submits that attribute and
                # would wedge the session on the same firmware rejection.
                # Restore the pre-assignment intent, then re-raise so the
                # run still aborts loudly.
                self.camera.lightsheet_line_time = previous_intent
                raise
            applied_line_time_s = self.camera.line_time
            if applied_line_time_s is not None and (
                previous_line_time is None
                or not math.isclose(
                    previous_line_time,
                    applied_line_time_s,
                    rel_tol=1e-9,
                    abs_tol=1e-9,
                )
            ):
                self.siggen.compute_scan_waveforms()
        else:
            self.camera.set_exposure_time(max(1, int(cmd.exposure_s * 1000)))
        # Write laser powers through the safe HAL paths. The percent is
        # computed from the command's mW value and the laser's max_power.
        # Each laser write is wrapped in its own except handler so a
        # single HAL write failure emits the mandated per-laser safety
        # copy and returns control to the stack loop — the next plane
        # retries. The two-layer HAL clamp (ILaser.set_power + backend
        # native clamp) held the power at the safe limit; the loop does
        # NOT abort (the outer StackWorker.run failure handler is
        # bypassed). The operator can press E-stop (F12) to abort.
        # Read back the applied percent per laser. The readback is
        # cosmetic, so it must never abort the run: a backend clamp
        # mismatch or a lowered max_power could derive a value outside
        # [0, 100] (or NaN) whose ValueError out of
        # AppliedMicroscopeSnapshot would abort the whole stack — clamp
        # to the contract range. A laser that was not writable this plane
        # stays None so the emit preserves the staged intent percent
        # instead of overwriting it with 0.
        applied_pct: list[float | None] = [None, None]
        if self._shell.lasers[0].max_power > 0:
            pct1 = cmd.laser1_mw / self._shell.lasers[0].max_power * 100.0
            try:
                self._hw._write_laser1_power(pct1)
            except Exception as e:
                logger.exception(
                    "Adaptive power write for L1 failed: cmd=%s error=%s", cmd, e
                )
                self._shell.sig_message.emit(
                    f"Adaptive power write failed for L1: {e}. The "
                    f"two-layer clamp held — laser power was NOT "
                    f"changed past the safe limit. The loop will retry "
                    f"on the next plane; press E-stop (F12) to abort."
                )
            raw1 = self._shell.lasers[0].power / self._shell.lasers[0].max_power * 100.0
            applied_pct[0] = min(100.0, max(0.0, raw1)) if math.isfinite(raw1) else 0.0
        if self._shell.lasers[1].max_power > 0:
            pct2 = cmd.laser2_mw / self._shell.lasers[1].max_power * 100.0
            try:
                self._hw._write_laser2_power(pct2)
            except Exception as e:
                logger.exception(
                    "Adaptive power write for L2 failed: cmd=%s error=%s", cmd, e
                )
                self._shell.sig_message.emit(
                    f"Adaptive power write failed for L2: {e}. The "
                    f"two-layer clamp held — laser power was NOT "
                    f"changed past the safe limit. The loop will retry "
                    f"on the next plane; press E-stop (F12) to abort."
                )
            raw2 = self._shell.lasers[1].power / self._shell.lasers[1].max_power * 100.0
            applied_pct[1] = min(100.0, max(0.0, raw2)) if math.isfinite(raw2) else 0.0

        emitted_pct = (
            None
            if applied_pct[0] is None and applied_pct[1] is None
            else (
                applied_pct[0]
                if applied_pct[0] is not None
                else self._snapshot.laser_power_pct[0],
                applied_pct[1]
                if applied_pct[1] is not None
                else self._snapshot.laser_power_pct[1],
            )
        )
        self.sig_applied_state.emit(
            AppliedMicroscopeSnapshot(
                laser_power_pct=emitted_pct,
                lightsheet_line_time_s=applied_line_time_s,
            )
        )

    def _record_adaptive_step(self: StackWorker, plane_idx: int) -> None:
        """Measure this plane's intensity, record the trajectory sample,
        emit the signal, and compute the next plane's command.

        Called once per main plane after the frame(s) are acquired and
        enqueued. When adaptive is off (no controller), nothing is
        emitted — the trajectory dock stays empty for fixed stacks (a
        fixed run is not adaptive and plotting computed power for lasers
        that are not under automatic control would be misleading). When
        adaptive is on, both channels' intensities are measured; the
        brighter channel drives the shared exposure.
        """
        from lightsheet.adaptive.intensity import frame_intensity_pct
        from lightsheet.adaptive.types import AdaptiveSample

        # Adaptive-off: no trajectory emission — the fixed stack path
        # runs unchanged (no measurement, no computation, no hardware
        # writes) and the GUI trajectory dock stays empty.
        if self._adaptive_controller is None:
            return

        # The controller is only constructed when both the config and the
        # current command are non-None; the casts assert that invariant to
        # the type checker without adding runtime branches.
        cfg = cast(AdaptiveConfig, self._adaptive_cfg)
        cmd = cast(AdaptiveCommand, self._adaptive_current_cmd)

        # Measure intensity from the acquired frame(s). The percentile
        # statistic drives the PI feedback; a separate higher percentile
        # (default max) drives the hard saturation guard so a single
        # saturated pixel trips it even when the PI percentile is low.
        if self._multi_channel:
            frames = self._shell.reconstructed_frames
            intensities = []
            sat_intensities = []
            for laser in self._shell.lasers:
                frame = frames.get(int(laser.wavelength)) if frames else None
                intensities.append(
                    frame_intensity_pct(frame, cfg.sensor_max, cfg.intensity_percentile)
                )
                sat_intensities.append(
                    frame_intensity_pct(frame, cfg.sensor_max, cfg.saturation_percentile)
                )
            # The brighter channel drives the shared exposure.
            brighter_idx = max(
                range(len(intensities)),
                key=lambda i: intensities[i],
            )
            saturation_intensity = sat_intensities[brighter_idx]
        else:
            frame = self._shell.reconstructed_frame
            intensities = [frame_intensity_pct(frame, cfg.sensor_max, cfg.intensity_percentile)]
            brighter_idx = 0
            saturation_intensity = frame_intensity_pct(
                frame, cfg.sensor_max, cfg.saturation_percentile
            )

        # Record the trajectory sample.
        sample = AdaptiveSample(
            plane_index=plane_idx,
            intensity_fraction=intensities,
            exposure_s=cmd.exposure_s,
            laser_power_mw=(cmd.laser1_mw, cmd.laser2_mw),
            control_variable_active=cmd.control_variable_active,
            reacquired=cmd.reacquire,
            power_fallback=cmd.power_fallback,
        )
        if self._shell.saving_allowed:
            self._shell._fs.record_adaptive_sample(sample)
            # Stage the trajectory row and the controller checkpoint on
            # the manifest update queue. The save worker drains these and
            # persists them with the sidecar manifest so a crash or pause
            # can resume the exposure/power trajectory.
            self._shell._fs.manifest_update_queue.put_nowait(
                ManifestUpdate(
                    kind="checkpoint",
                    payload=self._adaptive_controller.checkpoint(),
                    plane_index=plane_idx,
                )
            )
            self._shell._fs.manifest_update_queue.put_nowait(
                ManifestUpdate(
                    kind="trajectory",
                    payload=sample.as_dict(),
                    plane_index=plane_idx,
                )
            )

        # Emit the trajectory signal for the GUI-thread plot.
        self.sig_adaptive_trajectory.emit(
            plane_idx,
            intensities[brighter_idx],
            cmd.exposure_s,
            cmd.laser1_mw,
            cmd.laser2_mw,
            cmd.control_variable_active,
            cmd.reacquire,
            cmd.power_fallback,
        )

        # Compute the next plane's command from this plane's intensity.
        current_powers = (cmd.laser1_mw, cmd.laser2_mw)
        self._adaptive_current_cmd = self._adaptive_controller.update(
            intensities=intensities,
            brighter_idx=brighter_idx,
            current_exposure_s=cmd.exposure_s,
            current_powers_mw=current_powers,
            plane_idx=plane_idx,
            saturation_intensity=saturation_intensity,
        )
        # Re-acquire exhaustion: when the next command carries
        # reacquire_exhausted=True, the controller has spent its
        # re-acquire budget and the latest observation still deviates
        # from the feedforward expectation. Emit the mandated
        # plane/deviation operator message so the operator knows the
        # re-shot still deviates without watching the trajectory plot
        # mid-run. The defensive getattr accepts legacy command-like
        # objects constructed before the field was added. The deviation
        # is the absolute difference between the brighter channel's
        # observed intensity fraction and the target midpoint, as a
        # rounded percentage. This is a derived notification — it does
        # NOT change AdaptiveSample storage schema or the trajectory
        # signal (exhaustion is not a saved decision).
        if getattr(self._adaptive_current_cmd, "reacquire_exhausted", False):
            dev_pct = abs(intensities[brighter_idx] - cfg.target_midpoint) * 100.0
            self._shell.sig_message.emit(
                f"Re-acquire fallback exhausted at plane {plane_idx}: "
                f"intensity still deviates {dev_pct:.0f}% from target "
                f"after re-shot. The loop will continue with the "
                f"re-shot frame; review the trajectory after the run."
            )
