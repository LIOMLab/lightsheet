"""Stack mode acquisition worker QObject.

This module owns ``StackWorker`` — the volume-acquisition worker that
planes, acquires scans, and saves frames. Adaptive/focus helpers live in
``stack_adaptive.py`` and are mixed in through ``_StackAdaptiveMixin``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np
from PySide6.QtCore import QObject, QThread, Signal, Slot

from lightsheet.gui.workers.scan_mixin import _AcquireScanMixin
from lightsheet.gui.workers.stack_adaptive import _StackAdaptiveMixin
from lightsheet.hal.bundle import DeviceBundle

if TYPE_CHECKING:
    from lightsheet.adaptive.controller import AdaptiveController
    from lightsheet.adaptive.types import AdaptiveCommand, AdaptiveConfig
    from lightsheet.focus.adaptive_controller import AdaptiveFocusController
    from lightsheet.focus.controller import FocusController
    from lightsheet.focus.types import (
        AutofocusConfig,
        FocusConfig,
        FocusCurve,
    )
    from lightsheet.gui.coordinators.hardware_manager import HardwareManager
    from lightsheet.gui.shell.controller import Controller_MainWindow

logger = logging.getLogger(__name__)


class StackWorker(QObject, _AcquireScanMixin, _StackAdaptiveMixin):
    """Worker ``QObject`` for stack mode (volume acquisition + saving).

    Relocated verbatim from ``AcquisitionCoordinator.stack_mode_worker``.
    The body arms the camera for scan acquisition, starts the auto-selected
    lasers (guarded by a pre-stop check), computes scan waveforms once,
    then loops over ``self._shell.number_of_planes`` planes — moving the
    horizontal motor, acquiring a scan, and saving the frame. The
    ``finished`` signal fires exactly once in ``finally`` so the
    GUI-thread slot (``updateUi_post_stack_mode``) re-enables the UI
    whether the run completes normally, breaks on E-stop/Stop, or an
    exception propagates.

    The save-option widgets (``lineEdit_saveDescription``,
    ``radioButton_saveStitchBlend``, ``radioButton_saveAllCrop``,
    ``radioButton_saveAllFull``) are pre-sampled on the GUI thread in
    ``updateUi_stack_mode_button`` and passed as constructor args
    (``save_description``, ``save_stitch_blend``, ``save_all_crop``,
    ``save_all_full``) so the worker thread never reaches into
    the shell's ``ui.*``.

    The per-plane position update reaches the GUI thread via the queued
    ``sig_refresh_position_horizontal`` signal (already declared on the
    shell and connected to the GUI-thread position-refresh slot) instead
    of a legacy direct cross-thread widget mutation — closing the last
    direct-widget-mutation violation.

    Known limitation: stack mode does not adjust camera focus between
    planes (the single-frame worker does). Adding per-plane focus
    adjustment here is a future enhancement, not a regression.
    """

    finished = Signal()
    # Adaptive trajectory signal: plane_idx, intensity, exposure_s,
    # power1_mw, control_variable_active, reacquired, power_fallback.
    # Emitted per main plane for the GUI-thread trajectory plot (the
    # worker NEVER calls pyqtgraph directly). The
    # full power tuple (L1, L2) is recorded in the HDF5 trajectory
    # group via AdaptiveSample; the signal carries L1 power for the
    # live plot.
    sig_adaptive_trajectory = Signal(int, float, float, float, float, str, bool, bool)
    # Focus trajectory signal: block_index, stage_pos_mm,
    # feedforward_camera_pos_mm, residual_mm, applied_camera_pos_mm.
    # Emitted once per focus block boundary for the GUI-thread trajectory
    # plot (the worker NEVER calls pyqtgraph directly).
    sig_focus_trajectory = Signal(int, float, float, float, float)
    # Autofocus status signal: plane, n_planes, predicted_camera_pos_mm,
    # residual_mm, sharpness, state. Emitted once per plane so the
    # GUI-thread status label and progress bar update without the worker
    # touching Qt widgets directly.
    sig_autofocus_status = Signal(int, int, float, float, float, str)

    def __init__(
        self,
        bundle: DeviceBundle,
        hw: HardwareManager | None,
        shell: Controller_MainWindow,
        save_description: str,
        save_stitch_blend: bool,
        save_all_crop: bool,
        save_all_full: bool,
        multi_channel: bool = False,
        adaptive_cfg: AdaptiveConfig | None = None,
        focus_cfg: FocusConfig | None = None,
        focus_curve: FocusCurve | None = None,
        autofocus_cfg: AutofocusConfig | None = None,
        autofocus_curve: FocusCurve | None = None,
    ) -> None:
        super().__init__()
        assert hw is not None
        self.camera = bundle.camera
        self.siggen = bundle.siggen
        self.motors = bundle.motors
        self._hw: HardwareManager = hw
        self._shell = shell
        # Save-option widgets are pre-sampled on the GUI thread before
        # spawning the worker so the worker thread never reaches into the
        # shell's ui.* (cross-thread widget access). acquire_scan() reads
        # these to populate buffer metadata.
        self._save_description = save_description
        self._save_stitch_blend = save_stitch_blend
        self._save_all_crop = save_all_crop
        self._save_all_full = save_all_full
        # Multi-channel flag pre-sampled on the GUI thread.
        # When True, run() executes the per-plane sequential cycle:
        # move -> select_laser(0) -> acquire -> capture frame1 ->
        # select_laser(1) -> acquire -> capture frame2 -> enqueue both.
        # When False, the single-channel path runs (back-compat).
        # one acquire_scan per plane, one bare-ndarray enqueue per plane.
        self._multi_channel = multi_channel
        # Pre-sample the configured laser wavelengths on the GUI thread
        # so the worker thread never reads shared HAL state from run().
        # The wavelengths are read from the live ILaser instances here,
        # never hardcoded. In multi-channel mode these are passed to
        # set_files(wavelengths=...) so the save side builds one
        # per-channel filename list (and the Zarr writer allocates a
        # channel axis); in single-channel mode the active laser's
        # wavelength is pre-sampled (lasers[0] if _auto_laser1,
        # lasers[1] if only _auto_laser2, lasers[0] fallback) so the
        # saved HDF5 filename carries the _{wavelength}nm suffix.
        if multi_channel:
            self._wavelengths: list[int] | None = [
                int(self._shell.lasers[0].wavelength),
                int(self._shell.lasers[1].wavelength),
            ]
        elif getattr(self._shell, "_auto_laser1", False):
            self._wavelengths = [int(self._shell.lasers[0].wavelength)]
        elif getattr(self._shell, "_auto_laser2", False):
            self._wavelengths = [int(self._shell.lasers[1].wavelength)]
        else:
            # Neither auto-laser checked (manual mode / edge case) —
            # fall back to lasers[0].wavelength so the suffix is still
            # written. The wavelength is a trusted value from the live
            # ILaser instance set at startup from config.ini.
            self._wavelengths = [int(self._shell.lasers[0].wavelength)]

        # Adaptive control config (None → adaptive off, fixed stack).
        # Stored as an instance attribute so the run() method can
        # construct the AdaptiveController and the helper methods can
        # read it. The frozen dataclass is safe to share across threads
        # (immutable).
        self._adaptive_cfg: AdaptiveConfig | None = adaptive_cfg
        self._adaptive_controller: AdaptiveController | None = None
        self._adaptive_current_cmd: AdaptiveCommand | None = None
        # Focus compensation config and pre-validated calibration curve.
        # Both are pre-sampled on the GUI thread and passed as constructor
        # args so the worker thread never reads ui.* or loads the
        # calibration file from disk (AGENTS.md §11).
        self._focus_cfg: FocusConfig | None = focus_cfg
        self._focus_curve: FocusCurve | None = focus_curve
        self._focus_controller: FocusController | None = None
        if (
            self._focus_cfg is not None
            and self._focus_cfg.enabled
            and self._focus_curve is None
        ):
            raise ValueError(
                "Focus compensation enabled but no calibration curve was loaded"
            )
        # Per-plane adaptive autofocus config and optional curve seed.
        # The frozen dataclass is safe to share across threads; the curve
        # is only required when ``use_curve_seed`` is True.
        self._autofocus_cfg: AutofocusConfig | None = autofocus_cfg
        self._autofocus_curve: FocusCurve | None = autofocus_curve
        self._autofocus_controller: AdaptiveFocusController | None = None
        if (
            self._autofocus_cfg is not None
            and self._autofocus_cfg.enabled
            and self._autofocus_cfg.use_curve_seed
            and self._autofocus_curve is None
        ):
            raise ValueError("Autofocus curve seed enabled but no curve was loaded")

    @Slot()
    def run(self) -> None:
        """Thread for volume acquisition and saving"""
        try:
            # Making sure saving is allowed and filename isn't empty
            if self._shell.saving_allowed:
                # Getting sample name
                self._shell.save_description = str(self._save_description)

                # Setting frame saver
                self._shell._fs.reinit(3)
                self._shell._fs.add_sample_name(self._shell.save_description)
                # In multi-channel mode, pass the pre-sampled wavelengths
                # to set_files so the save side builds one per-channel
                # filename list (HDF5) and the Zarr writer allocates a
                # channel axis sized to the channel count. Without this,
                # filenames_lists stays empty and the multi-channel save
                # workers crash (HDF5/both: AttributeError on tuple.ndim;
                # Zarr: IndexError on channel-1 write_plane). In
                # single-channel mode the pre-sampled [active_wavelength]
                # is passed so the saved filename carries the
                # _{wavelength}nm suffix.
                if self._wavelengths:
                    set_files_kwargs = {"wavelengths": self._wavelengths}
                else:
                    set_files_kwargs = {}
                if self._save_all_crop:
                    self._shell._fs.set_files(
                        self._shell.number_of_planes,
                        self._shell.save_filepath,
                        "stack",
                        1,
                        "ETLscan",
                        **set_files_kwargs,
                    )
                elif self._save_all_full:
                    self._shell._fs.set_files(
                        self._shell.number_of_planes,
                        self._shell.save_filepath,
                        "stack",
                        1,
                        "FullETLscan",
                        **set_files_kwargs,
                    )
                else:
                    # Stitch (reconstructed_frame) branch — the "1 file
                    # containing N datasets" convention: ONE file holds
                    # all planes as datasets (reconstructed_frame001..
                    # reconstructed_frameNNN). The _plane_00001 segment
                    # in the filename is the collision-avoidance sequence
                    # (number_of_files=1 → only plane_00001), NOT a plane
                    # index. Both single-channel and multi-channel use
                    # set_files(1, ..., number_of_planes, ...) — the only
                    # difference is the wavelengths kwarg (multi-channel
                    # passes [wl1, wl2] so set_files builds one filename
                    # per channel, each a single-file container for all
                    # planes of that channel). The multi-channel save
                    # loop opens ONE file per channel and writes
                    # number_of_planes datasets into each, terminating
                    # on frames consumed (n_channels * n_planes) — not
                    # files written.
                    self._shell._fs.set_files(
                        1,
                        self._shell.save_filepath,
                        "stack",
                        self._shell.number_of_planes,
                        "reconstructed_frame",
                        **set_files_kwargs,
                    )
                # Starting frame saver
                self._shell._fs.start_saving()
                # Configure the adaptive trajectory recorder on the save
                # side. When adaptive is enabled, the per-plane loop
                # records one AdaptiveSample per main plane and the HDF5
                # writer writes the /adaptive_trajectory group before file
                # close (and the Zarr writer writes /acquisition/adaptive
                # during finalize). The frozen AdaptiveConfig is passed
                # through so the writers publish the full bounds + gains
                # as group attrs (reproducibility contract).
                # When disabled, no trajectory is recorded or written.
                adaptive_enabled = (
                    self._adaptive_cfg is not None and self._adaptive_cfg.enabled
                )
                self._shell._fs.configure_adaptive(
                    adaptive_enabled,
                    config=self._adaptive_cfg if adaptive_enabled else None,
                )
                # Configure the focus trajectory recorder on the save side.
                # When focus is enabled, the per-plane loop records one
                # FocusSample per block boundary and the HDF5 writer writes
                # the /focus_trajectory group before file close (and the
                # Zarr writer writes /acquisition/focus during finalize).
                # The frozen FocusConfig is passed through so the writers
                # publish the block size and residual settings as group attrs.
                # When disabled, no focus trajectory is recorded or written.
                focus_enabled = (
                    self._focus_cfg is not None and self._focus_cfg.enabled
                ) or (self._autofocus_cfg is not None and self._autofocus_cfg.enabled)
                # Pass the legacy FocusConfig as attrs when present; the
                # per-plane autofocus path does not change the trajectory
                # recorder schema, so only the legacy config is written.
                self._shell._fs.configure_focus(
                    focus_enabled,
                    config=self._focus_cfg if focus_enabled else None,
                )

            # Setting the camera for scan acquisition
            self.camera.arm_scan()

            # Pre-stop guard: a Stop or E-stop pressed in the instant between
            # thread start and this line skips energizing the lasers entirely.
            # The per-plane loop's first-iteration poll then breaks immediately
            # and the end-of-method cleanup (stop_lasers/disarm/emit) runs
            # unchanged, so no lasers are left on and the UI re-enables.
            #
            # Multi-channel mode MUST NOT call start_lasers here — it
            # would energize both lasers simultaneously, violating the
            # one-laser-energized invariant. The per-plane cycle below
            # uses select_laser(0/1) per channel instead, which
            # de-energizes the other laser before energizing the target.
            # stop_lasers at the end of run() is safety — ensures both
            # off regardless of the last select_laser state.
            if (
                not self._multi_channel
                and self._shell.stack_mode_started
                and not self._shell.estop_event.is_set()
            ):
                self._hw.start_lasers()

            # Set progress bar
            progress_value = 0
            # Defensive guard: a zero plane count (e.g. a queue row that
            # slipped past validation, or a future code path/race) would
            # divide by zero below. Abort with a status message instead of
            # raising ZeroDivisionError. The single-stack path ensures
            # >=1 via updateUi_set_number_of_planes; this guard is the
            # backstop for the queue path and any unexpected zero.
            n_planes = int(self._shell.number_of_planes)
            if n_planes <= 0:
                self._shell.sig_message.emit(
                    "Stack acquisition aborted: number of planes is 0"
                )
                self._shell.sig_beep.emit()
                return
            progress_increment = 100 / n_planes
            self._shell.sig_progress_update.emit(0)  # To reset progress bar

            # Compute scan waveforms only once before we start the stack acquisition
            # Changes to settings won't be effective until we stop/restart mode
            self.siggen.compute_scan_waveforms()

            # Adaptive control setup: construct the controller and prime
            # it with a flat pilot trajectory at the current exposure. The
            # PI residual correction handles the per-depth profile; the
            # feedforward baseline is the current exposure. When adaptive
            # is off (cfg is None or disabled), no controller is
            # constructed and the per-plane loop runs the existing fixed
            # stack path unchanged.
            self._adaptive_controller = None
            self._adaptive_current_cmd = None
            if self._adaptive_cfg is not None and self._adaptive_cfg.enabled:
                from lightsheet.adaptive.controller import AdaptiveController

                self._adaptive_controller = AdaptiveController(
                    self._adaptive_cfg, n_planes
                )
                # Prime with a flat trajectory at the current exposure.
                # The PI correction handles the per-depth profile; the
                # feedforward baseline is the current camera exposure.
                pilot_indices = list(range(self._adaptive_cfg.pilot_count))
                pilot_exposures = [
                    self.camera.exposure_time
                ] * self._adaptive_cfg.pilot_count
                self._adaptive_controller.prime(pilot_indices, pilot_exposures)
                # The initial command for plane 0 is the feedforward
                # baseline (current exposure + current staged powers).
                # The controller's update() will refine it from plane 0's
                # observed intensity for plane 1 onwards.
                current_powers = (
                    self._shell.laser1_power_pct
                    / 100.0
                    * self._shell.lasers[0].max_power,
                    self._shell.laser2_power_pct
                    / 100.0
                    * self._shell.lasers[1].max_power,
                )
                from lightsheet.adaptive.types import AdaptiveCommand

                self._adaptive_current_cmd = AdaptiveCommand.fixed(
                    exposure_s=self.camera.exposure_time,
                    laser1_mw=current_powers[0],
                    laser2_mw=current_powers[1],
                )

            # Focus control setup: read the camera travel limits once,
            # then construct either the block-based legacy FocusController,
            # the per-plane AdaptiveFocusController, or neither. When both
            # are off, the per-plane loop runs the existing fixed stack path.
            self._focus_controller = None
            self._focus_block_count = 0
            self._autofocus_controller = None
            cam_lo_mm = self.motors.camera.get_limit_low("mm")
            cam_hi_mm = self.motors.camera.get_limit_high("mm")
            if self._focus_cfg is not None and self._focus_cfg.enabled:
                if self._focus_curve is None:
                    raise ValueError(
                        "Focus compensation enabled but no calibration curve was loaded"
                    )
                from lightsheet.focus.controller import FocusController

                self._focus_controller = FocusController(
                    self._focus_cfg,
                    self._focus_curve,
                    cam_lo_mm,
                    cam_hi_mm,
                )

            # Per-plane adaptive autofocus setup: construct the
            # controller from the camera travel limits, the optional curve
            # seed, and the current camera position. When autofocus is off,
            # no controller is constructed and the per-plane loop runs the
            # existing fixed or block focus path unchanged.
            if self._autofocus_cfg is not None and self._autofocus_cfg.enabled:
                from lightsheet.focus.adaptive_controller import AdaptiveFocusController

                try:
                    cam_pos_mm = self.motors.camera.get_position("mm")
                except Exception as e:
                    self._shell.sig_message.emit(
                        f"Stack acquisition aborted: could not read current camera "
                        f"position for autofocus seed: {e}"
                    )
                    self._shell.sig_beep.emit()
                    return
                self._autofocus_controller = AdaptiveFocusController(
                    self._autofocus_cfg,
                    cam_lo_mm,
                    cam_hi_mm,
                    curve=self._autofocus_curve,
                    seed_camera_pos_mm=cam_pos_mm,
                )

            for plane in range(n_planes):
                # Cooperative shutdown: if the owning QThread has been asked
                # to quit (e.g. during xdist worker teardown), stop the stack
                # and let the post-loop cleanup run. This is intentionally
                # checked at the loop top alongside the mode-started / E-stop
                # guards so the worker never blocks teardown.
                if QThread.currentThread().isInterruptionRequested():
                    self._shell.sig_message.emit("Stack Acquisition Interrupted")
                    break
                if not self._shell.stack_mode_started:
                    self._shell.sig_message.emit("Stack Acquisition Interrupted")
                    break
                elif self._shell.estop_event.is_set():
                    # E-stop poll point — checked alongside the stack_mode_started
                    # flag at each plane boundary. The lasers are already dark
                    # (driven off synchronously on the GUI thread); this break
                    # stops acquiring new planes.
                    self._shell.sig_message.emit("Stack Acquisition Interrupted")
                    break
                else:
                    # Pre-move guard: a Stop or E-stop requested while the worker
                    # was between blocking calls (after the loop-top poll but
                    # before this motor move) must not start a new blocking call.
                    if (
                        not self._shell.stack_mode_started
                        or self._shell.estop_event.is_set()
                    ):
                        break

                    # Moving sample position. Position is in micrometres;
                    # stage_pos_mm is the sample (horizontal) stage position
                    # used for the focus feedforward curve.
                    position = self._shell.stack_starting_plane + (
                        plane * self._shell.stack_step
                    )  # ty: ignore[unsupported-operator]
                    stage_pos_mm = position / 1000.0  # um -> mm

                    autofocus_focus_pos_mm: float | None = None

                    if self._autofocus_controller is not None:
                        # Per-plane autofocus: compute the camera target,
                        # move both axes in parallel, and let the
                        # post-acquire block record the sample and update
                        # the residual for the next plane.
                        autofocus_focus_pos_mm = self._autofocus_controller.target(
                            stage_pos_mm
                        )

                        if (
                            not self._shell.stack_mode_started
                            or self._shell.estop_event.is_set()
                        ):
                            break

                        try:
                            self.motors.move_axes_parallel(
                                [
                                    ("horizontal", position, "\u03bcm"),
                                    ("camera", autofocus_focus_pos_mm, "mm"),
                                ]
                            )
                        except ValueError:
                            self._shell.sig_message.emit(
                                f"Focus move rejected at plane {plane}: camera target "
                                f"{autofocus_focus_pos_mm:.3f} mm is outside travel "
                                "limits. Stack acquisition aborted."
                            )
                            self._shell.sig_beep.emit()
                            self.sig_autofocus_status.emit(
                                plane,
                                n_planes,
                                autofocus_focus_pos_mm,
                                self._autofocus_controller.residual_mm,
                                0.0,
                                "error",
                            )
                            break

                        self._shell.sig_refresh_position_horizontal.emit()
                        self._shell.sig_refresh_position_camera.emit()

                        if self._shell.saving_allowed:
                            self._shell._fs.add_motor_parameters(
                                self._shell.current_horizontal_position_text,
                                self._shell.current_vertical_position_text,
                                self._shell.current_camera_position_text,
                            )

                    elif (
                        self._focus_controller is not None
                        and self._focus_cfg is not None
                        and self._focus_curve is not None
                        and (plane % self._focus_cfg.block_size_n) == 0
                    ):
                        # Compute the previous block's sharpness before
                        # updating the residual. The first block boundary
                        # has no prior frame, so update_residual is skipped.
                        sharpness_metric: float | None = None
                        if (
                            self._focus_cfg.autofocus_residual
                            and self._focus_block_count > 0
                        ):
                            from lightsheet.focus.sharpness import (
                                frame_sharpness_variance,
                            )

                            sharpness_metric = frame_sharpness_variance(
                                self._shell.reconstructed_frame
                            )
                            self._focus_controller.update_residual(sharpness_metric)

                        feedforward_camera_pos_mm = float(
                            np.interp(
                                stage_pos_mm,
                                self._focus_curve.stage_pos,
                                self._focus_curve.camera_pos,
                            )
                        )
                        focus_pos_mm = self._focus_controller.target(stage_pos_mm)
                        residual_mm = self._focus_controller.residual_mm

                        try:
                            self.motors.move_axes_parallel(
                                [
                                    ("horizontal", position, "\u03bcm"),
                                    ("camera", focus_pos_mm, "mm"),
                                ]
                            )
                        except ValueError:
                            self._shell.sig_message.emit(
                                "Focus compensation move rejected — target outside travel limits. Stack acquisition aborted."  # noqa: E501
                            )
                            self._shell.sig_beep.emit()
                            break

                        # Dual-axis position refresh reaches the GUI thread
                        # through the queued refresh signals so the motor
                        # panel updates current_*_position_text for honest
                        # add_motor_parameters logging.
                        self._shell.sig_refresh_position_horizontal.emit()
                        self._shell.sig_refresh_position_camera.emit()

                        if self._shell.saving_allowed:
                            self._shell._fs.add_motor_parameters(
                                self._shell.current_horizontal_position_text,
                                self._shell.current_vertical_position_text,
                                self._shell.current_camera_position_text,
                            )
                            from lightsheet.focus.types import FocusSample

                            focus_sample = FocusSample(
                                block_index=self._focus_block_count,
                                stage_pos_mm=stage_pos_mm,
                                feedforward_camera_pos_mm=feedforward_camera_pos_mm,
                                residual_mm=residual_mm,
                                applied_camera_pos_mm=focus_pos_mm,
                                sharpness_metric=sharpness_metric
                                if self._focus_block_count > 0
                                else None,
                            )
                            self._shell._fs.record_focus_sample(focus_sample)

                        self.sig_focus_trajectory.emit(
                            self._focus_block_count,
                            stage_pos_mm,
                            feedforward_camera_pos_mm,
                            residual_mm,
                            focus_pos_mm,
                        )
                        self._focus_block_count += 1
                    else:
                        try:
                            self.motors.horizontal.move_absolute_position(
                                position, "\u03bcm"
                            )  # Position in micro-meters
                        except ValueError:
                            self._shell.sig_message.emit(
                                "Move rejected — horizontal would exceed travel limits. Stack acquisition aborted."  # noqa: E501
                            )
                            self._shell.sig_beep.emit()
                            break
                        # Per-plane position update reaches the GUI thread via the
                        # queued sig_refresh_position_horizontal signal (already
                        # declared on the shell and connected to
                        # updateUi_position_horizontal) instead of a direct
                        # cross-thread widget mutation.
                        self._shell.sig_refresh_position_horizontal.emit()

                        if self._shell.saving_allowed:
                            self._shell._fs.add_motor_parameters(
                                self._shell.current_horizontal_position_text,
                                self._shell.current_vertical_position_text,
                                self._shell.current_camera_position_text,
                            )

                    # Pre-acquire guard: a Stop or E-stop requested while the worker
                    # was between the motor move and this acquisition must not start
                    # the (potentially long, up to recorder-timeout) camera grab.
                    if (
                        not self._shell.stack_mode_started
                        or self._shell.estop_event.is_set()
                    ):
                        break

                    # Adaptive: apply the current adaptive command (exposure
                    # + power) before acquiring this plane's frame. The
                    # command was computed from the previous plane's
                    # intensity (or the feedforward baseline for plane 0).
                    # E-stop is re-checked inside _write_laser1_power
                    # (cooperative-skip) — a mid-write E-stop zeroes the
                    # power and the loop-top poll on the next iteration
                    # breaks. When adaptive is off, no hardware changes
                    # are applied — the existing fixed stack path runs
                    # unchanged.
                    if (
                        self._adaptive_controller is not None
                        and self._adaptive_current_cmd is not None
                    ):
                        self._apply_adaptive_command(self._adaptive_current_cmd)

                    if self._multi_channel:
                        # Multi-channel per-plane sequential cycle:
                        # energize L1 -> acquire -> capture frame1 ->
                        # energize L2 -> acquire -> capture frame2 ->
                        # enqueue both tagged frames. select_laser(idx)
                        # is the one-laser-energized invariant choke
                        # point — it de-energizes the other laser before
                        # energizing the target, so only one laser is
                        # active at any instant. Do NOT call start_lasers
                        # here (it would energize both at once, violating
                        # the invariant); select_laser per channel
                        # instead.
                        #
                        # Capture-frame-before-next-acquire pitfall:
                        # acquire_scan overwrites
                        # self._shell.reconstructed_frame. Capture frame1
                        # immediately after the first acquire_scan (before
                        # the second select_laser + acquire_scan
                        # overwrites it).
                        self._hw.select_laser(0)
                        # E-stop poll point — checked after select_laser(0)
                        # and before acquire_scan so a mid-plane E-stop
                        # (pressed between the channel-0 energize and the
                        # channel-0 frame grab) aborts without acquiring.
                        # The lasers are already dark (driven off
                        # synchronously on the GUI thread); select_laser(0)
                        # self-skips the energize when estop is set, and this
                        # break stops the per-plane cycle.
                        if self._shell.estop_event.is_set():
                            break
                        if not self.acquire_scan():
                            # Failed scan on channel 0 — acquire_scan already
                            # emitted a warning and cleaned up the
                            # recorder/scanner. Do not attempt channel 1 or
                            # the next plane.
                            break
                        # Capture frame1 immediately — the next acquire_scan
                        # overwrites reconstructed_frame (pitfall #3).
                        frame1 = (
                            None
                            if self._shell.reconstructed_frame is None
                            else self._shell.reconstructed_frame.copy()
                        )

                        self._hw.select_laser(1)
                        # E-stop poll point — checked after select_laser(1)
                        # and before the channel-1 acquire_scan.
                        if self._shell.estop_event.is_set():
                            break
                        if not self.acquire_scan():
                            # Failed scan on channel 1 — do not enqueue
                            # partial frames or attempt the next plane.
                            break
                        frame2 = (
                            None
                            if self._shell.reconstructed_frame is None
                            else self._shell.reconstructed_frame.copy()
                        )

                        # Store both frames in the per-channel dict keyed
                        # by laser wavelength. reconstructed_frame stays
                        # as an alias to the last channel's frame for
                        # back-compat with existing single-field consumers.
                        wl1 = int(self._shell.lasers[0].wavelength)
                        wl2 = int(self._shell.lasers[1].wavelength)
                        self._shell.reconstructed_frames = {}
                        if frame1 is not None:
                            self._shell.reconstructed_frames[wl1] = frame1
                        if frame2 is not None:
                            self._shell.reconstructed_frames[wl2] = frame2
                            # Alias to the last channel's frame for back-compat.
                            self._shell.reconstructed_frame = frame2

                        # Enqueue both tagged frames for saving. The
                        # tagged form (channel_idx, frame) is accepted by
                        # enqueue_buffer; the single-consumer save worker
                        # branches on the tag to pick the per-channel
                        # filename list. Only enqueue when saving is
                        # allowed and both frames were captured.
                        #
                        # Adaptive sample recording happens BEFORE the
                        # enqueue so the sample is recorded before the
                        # frame enters the save queue — the save worker
                        # writes the /adaptive_trajectory group after
                        # processing all frames, and recording before
                        # enqueue guarantees the sample is present.
                        # Called once here for both the saving and
                        # non-saving branches (hoisted out of the if/else
                        # to avoid the duplicated call).
                        self._record_adaptive_step(plane)
                        if (
                            self._shell.saving_allowed
                            and frame1 is not None
                            and frame2 is not None
                        ):
                            self._shell._fs.enqueue_buffer((0, frame1))
                            self._shell._fs.enqueue_buffer((1, frame2))
                    else:
                        # Single-channel path (unchanged — back-compat).

                        # Getting image
                        if not self.acquire_scan():
                            # Failed scan on this plane — acquire_scan already
                            # emitted a warning and cleaned up the
                            # recorder/scanner. Do not enqueue a nonexistent
                            # frame or attempt the next plane.
                            break

                        # Saving frame — adaptive sample recording happens
                        # BEFORE the enqueue so the sample is recorded
                        # before the frame enters the save queue (the save
                        # worker writes /adaptive_trajectory after
                        # processing all frames; recording before enqueue
                        # guarantees the sample is present).
                        self._record_adaptive_step(plane)
                        if self._shell.saving_allowed:
                            if self._save_all_crop:
                                cropped_buffer = self._shell._fs.crop_buffer(
                                    self._shell.buffer  # ty: ignore[invalid-argument-type]
                                )
                                self._shell._fs.enqueue_buffer(cropped_buffer)
                                self._shell.sig_message.emit(
                                    "Saving All Images (one for each ETL step, cropped)"
                                )
                            elif self._save_all_full:
                                self._shell._fs.enqueue_buffer(self._shell.buffer)  # ty: ignore[invalid-argument-type]
                                self._shell.sig_message.emit(
                                    "Saving All Images (one for each ETL step, full)"
                                )
                            else:
                                self._shell._fs.enqueue_buffer(
                                    self._shell.reconstructed_frame  # ty: ignore[invalid-argument-type]
                                )
                                self._shell.sig_message.emit(
                                    "Saving Reconstructed Image"
                                )

                    # Per-plane autofocus: record the focus sample, emit
                    # the trajectory and status signals, and update the
                    # residual for the next plane. This is intentionally
                    # placed after the frame has been acquired and the
                    # adaptive power sample has been recorded.
                    if (
                        self._autofocus_controller is not None
                        and autofocus_focus_pos_mm is not None
                        and self._autofocus_cfg is not None
                    ):
                        from lightsheet.focus.sharpness import frame_sharpness_variance
                        from lightsheet.focus.types import FocusSample

                        focus_frame = self._shell.reconstructed_frame
                        exposure = (
                            self._adaptive_current_cmd.exposure_s
                            if self._adaptive_current_cmd is not None
                            else self.camera.exposure_time
                        )
                        sharp = frame_sharpness_variance(focus_frame) / max(
                            exposure, 1e-9
                        )

                        feedforward = self._autofocus_controller.feedforward(
                            stage_pos_mm
                        )
                        residual = self._autofocus_controller.residual_mm

                        focus_sample = FocusSample(
                            block_index=plane,
                            stage_pos_mm=stage_pos_mm,
                            feedforward_camera_pos_mm=feedforward,
                            residual_mm=residual,
                            applied_camera_pos_mm=autofocus_focus_pos_mm,
                            sharpness_metric=sharp,
                        )
                        if self._shell.saving_allowed:
                            self._shell._fs.record_focus_sample(focus_sample)
                        self.sig_focus_trajectory.emit(
                            plane,
                            stage_pos_mm,
                            feedforward,
                            residual,
                            autofocus_focus_pos_mm,
                        )

                        max_residual = self._autofocus_cfg.max_residual_mm
                        is_cadence = (plane % self._autofocus_cfg.cadence) == 0
                        if not self._autofocus_controller.has_reference:
                            state = "waiting"
                        elif abs(residual) >= max_residual - 1e-9:
                            state = "clamped"
                        elif (
                            not is_cadence
                            or self._autofocus_controller.residual_unchanged
                        ):
                            state = "holding"
                        else:
                            state = "tracking"
                        self.sig_autofocus_status.emit(
                            plane,
                            n_planes,
                            autofocus_focus_pos_mm,
                            residual,
                            sharp,
                            state,
                        )

                        if (plane % self._autofocus_cfg.cadence) == 0:
                            self._autofocus_controller.update(stage_pos_mm, sharp)

                    # Update progress bar
                    progress_value += progress_increment
                    self._shell.sig_progress_update.emit(int(progress_value))

            if self._shell.stack_mode_started:
                self._shell.sig_progress_update.emit(
                    100
                )  # In case the number of planes is not a multiple of 100
        except Exception as e:
            self._shell.sig_message.emit(
                f"Stack acquisition failed — the run was aborted. Cause: {e}"
            )
            logger.exception("Stack mode worker failed")
        finally:
            # The finished signal must fire exactly once whether the method
            # completes normally, breaks out of the per-plane loop on E-stop
            # or interruption, or an exception propagates from the body. Stop
            # saving (if started), put the ETLs in standby, stop the lasers,
            # and disarm the camera so a worker that exits mid-acquisition
            # does not leave hardware energized; if a cleanup step fails,
            # surface it but always emit finished so the UI can re-enable.
            _cleanup_errors: list[str] = []
            if getattr(self._shell, "saving_allowed", False):
                try:
                    self._shell._fs.stop_saving()
                except Exception as e:
                    logger.exception("Stack worker stop_saving cleanup failed")
                    _cleanup_errors.append(f"stop_saving: {e}")
            try:
                self.siggen.update_etls(left_etl=2.5, right_etl=2.5)
            except Exception as e:
                logger.exception("Stack worker ETL cleanup failed")
                _cleanup_errors.append(f"ETL standby: {e}")
            try:
                self._hw.stop_lasers()
            except Exception as e:
                logger.exception("Stack worker stop_lasers cleanup failed")
                _cleanup_errors.append(f"stop_lasers: {e}")
            try:
                self.camera.disarm()
            except Exception as e:
                logger.exception("Stack worker camera disarm cleanup failed")
                _cleanup_errors.append(f"camera disarm: {e}")
            if _cleanup_errors:
                self._shell.sig_message.emit(
                    "Stack acquisition failed — cleanup could not complete safely. "
                    "Errors: " + "; ".join(_cleanup_errors)
                )
            self.finished.emit()
