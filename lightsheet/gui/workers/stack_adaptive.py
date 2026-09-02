"""Adaptive power/exposure method mixin for StackWorker.

The two adaptive helper methods are kept as methods on ``StackWorker``
through inheritance so callers still invoke them on the worker instance.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from lightsheet.adaptive.types import AdaptiveCommand, AdaptiveConfig

if TYPE_CHECKING:
    from lightsheet.gui.workers.stack import StackWorker


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

        The staged power percent is also written back to
        ``self._shell.laser1_power_pct`` / ``laser2_power_pct`` so the
        mock camera's scripted-intensity hook (which reads the staged
        percent) sees the updated power — mirroring real physics where
        more laser power produces more fluorescence.

        Cross-thread attribute sharing (intentional): these shell
        attributes are read by the GUI-thread laser readback refresh
        and by ``_toggle_laser*`` (which re-applies the staged percent
        when toggling a laser on). The worker also READS them at
        adaptive-prime time (the initial command's power is derived
        from the staged percent). Python float assignment is GIL-atomic
        so there is no torn-read corruption; the GUI readback may
        transiently show a value that is one refresh cycle behind the
        hardware state, which is acceptable for a best-effort readback.
        This mirrors the existing non-adaptive stack path, which also
        reads shell attributes from the worker. The E-stop kill path
        does NOT read these attributes — it calls ``laser.off()``
        directly on the GUI thread — so this sharing does not affect
        the lock-free kill path. Routing the write through a queued
        signal would defer the staged-percent update past the next
        plane's mock-camera intensity measurement and break the
        scripted-intensity hook's timing, so the direct write is kept.
        """
        # Set camera exposure (convert seconds to ms for the HAL). This
        # lives OUTSIDE the per-laser exception handlers below — a laser
        # write failure must not skip the camera exposure for this plane
        # (the next plane's loop-top E-stop poll is the abort point).
        #
        # In Lightsheet shutter mode the adaptive exposure bounds are in
        # microseconds (line times), so the requested exposure_s is
        # typically sub-millisecond. The set_exposure_time interface takes
        # an integer millisecond value, and int() truncates toward zero —
        # int(1e-6 * 1000) == 0 — which would write 0 ms every plane and
        # effectively disable the exposure actuator. Round to the nearest
        # ms and clamp to a minimum of 1 ms so a sub-ms Lightsheet exposure
        # is never silently dropped to zero. The Rolling path is unchanged
        # (exposures are 1-1000 ms, all >= 1 after truncation).
        shutter_mode = getattr(self.camera, "shutter_mode", "Rolling")
        if shutter_mode == "Lightsheet":
            self.camera.set_exposure_time(max(1, round(cmd.exposure_s * 1000)))
        else:
            self.camera.set_exposure_time(int(cmd.exposure_s * 1000))
        # Write laser powers through the safe HAL paths. The percent is
        # computed from the command's mW value and the laser's max_power.
        # Each laser write is wrapped in its own except handler so a
        # single HAL write failure emits the mandated per-laser safety
        # copy and returns control to the stack loop — the next plane
        # retries. The two-layer HAL clamp (ILaser.set_power + backend
        # native clamp) held the power at the safe limit; the loop does
        # NOT abort (the outer StackWorker.run failure handler is
        # bypassed). The operator can press E-stop (F12) to abort.
        if self._shell.lasers[0].max_power > 0:
            pct1 = cmd.laser1_mw / self._shell.lasers[0].max_power * 100.0
            self._shell.laser1_power_pct = pct1
            try:
                self._hw._write_laser1_power(pct1)
            except Exception as e:
                self._shell.sig_message.emit(
                    f"Adaptive power write failed for L1: {e}. The "
                    f"two-layer clamp held — laser power was NOT "
                    f"changed past the safe limit. The loop will retry "
                    f"on the next plane; press E-stop (F12) to abort."
                )
        if self._multi_channel and self._shell.lasers[1].max_power > 0:
            pct2 = cmd.laser2_mw / self._shell.lasers[1].max_power * 100.0
            self._shell.laser2_power_pct = pct2
            try:
                self._hw._write_laser2_power(pct2)
            except Exception as e:
                self._shell.sig_message.emit(
                    f"Adaptive power write failed for L2: {e}. The "
                    f"two-layer clamp held — laser power was NOT "
                    f"changed past the safe limit. The loop will retry "
                    f"on the next plane; press E-stop (F12) to abort."
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

        # Measure intensity from the acquired frame(s).
        if self._multi_channel:
            frames = self._shell.reconstructed_frames
            intensities = []
            for laser in self._shell.lasers:
                frame = frames.get(int(laser.wavelength)) if frames else None
                intensities.append(frame_intensity_pct(frame, cfg.sensor_max))
            # The brighter channel drives the shared exposure.
            brighter_idx = max(
                range(len(intensities)),
                key=lambda i: intensities[i],
            )
        else:
            frame = self._shell.reconstructed_frame
            intensities = [frame_intensity_pct(frame, cfg.sensor_max)]
            brighter_idx = 0

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
            from lightsheet.gui.coordinators.frame_saver_controller import (
                FrameSaverController,
            )

            fs = cast(FrameSaverController, self._shell._fs)
            fs.record_adaptive_sample(sample)

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
            dev_pct = abs(
                intensities[brighter_idx] - cfg.target_midpoint
            ) * 100.0
            self._shell.sig_message.emit(
                f"Re-acquire fallback exhausted at plane {plane_idx}: "
                f"intensity still deviates {dev_pct:.0f}% from target "
                f"after re-shot. The loop will continue with the "
                f"re-shot frame; review the trajectory after the run."
            )
