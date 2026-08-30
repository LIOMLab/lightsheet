---
phase: lightsheet-10
phase_name: adaptive-exposure-laser-power-control
context_type: discuss
status: complete
calibration_tier: full_maturity
advisor_mode: true
advisor_model: glm-5.2
areas_discussed: 4
decisions: 4
context_gathered: 2026-08-30
---

# Phase 10: Adaptive Exposure & Laser Power Control - Context

**Gathered:** 2026-08-30 (D-01..D-04, advisor mode, full_maturity tier)
**Status:** Ready for planning

<domain>
## Phase Boundary

During a stack acquisition the controller adds a closed-loop intensity
feedback path: per plane it reads back the captured frame intensity and
adjusts exposure time and/or laser power for the next plane within
operator-configurable bounds, so the brainstem (high signal, saturates
easily) and the brain centre (low signal, under-exposed) are both captured
well in a single run. The adaptive mode is an **opt-in toggle on top of the
existing fixed-exposure/fixed-power stack** — the default stack behavior is
unchanged when adaptive is off.

In scope:
- **Closed-loop intensity feedback (SC-1):** per plane, read back the
  captured frame's intensity (a frame statistic — mean or high-percentile),
  compute an adjustment to exposure time and/or laser power for the next
  plane, apply it within operator-configurable bounds (min/max exposure,
  min/max power, target intensity band lo/hi %, default 90-95%). The loop
  composes with the Phase 9 per-plane stack cycle (`StackWorker.run`:
  move → `select_laser(0)` → acquire → `select_laser(1)` → acquire → next
  plane for multi-channel; move → acquire → next plane for single-channel).
- **Hybrid control variable (D-01):** exposure is the primary actuator
  (adjust `exposed_lines`/`line_time` within bounds first — non-bleaching,
  CLEM principle); laser power is the fallback (write power only when
  exposure hits its min/max bound and the target is still not met). This
  minimizes photobleaching (exposure absorbs most dynamic range) while
  preserving full dynamic range (power rescues regions where max exposure
  is insufficient).
- **Per-channel hybrid with cross-channel balancing (D-02):** in
  multi-channel mode, the shared exposure adjusts per-plane based on the
  **brighter channel's** intensity (prevents saturation); each laser's
  power trim then equalizes the dimmer channel to match the brighter one,
  so both channels converge to the same 90-95% target. Power trim runs
  per-N-plane block (amortizes the iBeam serial 3s round-trip over N
  planes). In single-channel mode, the loop drives the one active
  channel's exposure + power.
- **Pilot feedforward + per-plane PI residual control law (D-03):** a few
  sparse pilot frames at the start of the stack fit a smooth
  exposure/power-vs-depth trajectory for the monotonic-ish iDISCO+
  brainstem→centre signal drop (feedforward); per-plane PI (P+I, D=0)
  corrects residual error against the 90-95% target (feedback); a
  re-acquire fallback re-shoots a plane when its intensity deviates beyond
  a configurable threshold from expectation. The pilot trajectory
  eliminates oscillation on the monotonic trend; the PI handles
  sample-local deviations; the fallback handles large excursions.
- **L2 actuator phasing (D-03):** the MVP ships with L2 power via serial
  `set_power` (block-level, every N planes — the iBeam 3s round-trip is
  amortized). When the operator installs a trigger cable (iBeam "Analog
  In" SMB → spare DAQ AO line, e.g. Dev7/ao1), L2 upgrades to per-plane
  analog modulation (µs-scale DAQ AO writes, zero serial round-trips). The
  loop architecture composes with either L2 actuator path — the
  serial-block path is the MVP, the analog-per-plane path is the post-cable
  upgrade. This is the DAQ-gated analog modulation path deferred from
  Phase 9 D-01.
- **Safety invariants preserved (SC-2, SC-3):** the adaptive loop never
  violates the two-layer laser power clamp (`ILaser.set_power` + backend
  clamp) or the config-schema `Max Power` startup gate — all power writes
  route through the existing `_write_laser1/2_power` estop-guarded,
  RLock-protected, two-layer-clamped path. The E-stop kill path stays
  synchronous and lock-free; the loop checks `estop_event` before every
  laser write and aborts on set (no re-energize past the kill path).
- **Per-plane trajectory logging + metadata (SC-4):** the per-plane
  intensity reading, chosen exposure, chosen power (per laser), and
  control-variable-active flag (exposure vs power-fallback) are logged
  per plane and embedded in saved HDF5 + OME-Zarr metadata, so a stack's
  adaptive trajectory is reproducible and auditable.
- **Operator UI (D-04):** a collapsible adaptive config group in the
  existing Stack panel (enable toggle + FieldSpecSpinBox bounds: min/max
  exposure, min/max power, target band lo/hi %) + a dockable pyqtgraph
  trajectory widget (QDockWidget in the QMainWindow dock area, visible
  across all left-rail panels, floatable to a 2nd monitor) showing
  per-plane intensity vs target band with twin-axis exposure/power, and
  re-acquire fallback events as markers. The mode/state badge shows
  "ADAPTIVE RUNNING". Bounds are pre-sampled on the GUI thread and passed
  as `StackWorker` constructor args (AGENTS.md §11 — no cross-thread
  `ui.*` reads from the QThread worker).
- **Mock-stack end-to-end test (SC-5):** a mock stack on macOS exercises
  the adaptive loop end-to-end with a synthetic intensity profile
  (bright → dim, simulating brainstem → centre) and asserts the
  exposure/power trajectory tracks the profile within bounds without
  saturating or stalling.

Out of scope:
- **Phase 11 (Camera Focus Compensation for Brain Lensing)** — depends on
  Phase 9, independent of this phase, not part of this phase.
- **DAQ-gated analog modulation hardware wiring** (the iBeam "Analog In"
  SMB → Dev7/ao1 cable installation) — this is an operator rig task, not
  a software deliverable. The software architecture composes with the
  analog path when the cable is installed, but the cable itself is out of
  scope. The MVP ships with the serial-block L2 path.
- **Real-hardware UAT** — per the PROJECT.md note (2026-08-21), all
  hardware UAT testing is delayed until the milestone is finished. Mock-
  based verification is the per-phase gate. Rig-confirmation items (see
  Research flag in ROADMAP.md) are for the planner/researcher to document,
  not for this phase to resolve.
- **Per-line / interleaved (within-frame) adaptive exposure** — this phase
  is per-plane (or per-block) only.
- **Adaptive mode for continuous modes (live/preview)** — adaptive is
  stack-mode only (live/preview have no per-plane boundary to feedback
  over).

**Carrying forward from earlier phases (locked, not re-asking):**
- **Phase 4 / §2 (laser safety):** `ILaser` ABC — mW-canonical at the
  interface, two-layer clamp (interface `set_power` + backend native unit),
  `Max Power` from `config.ini` is safety-critical. `list[ILaser]` =
  (L1=555 nm DAQLaser on Dev7/ao0, L2=640 nm IBeamSmartLaser on COM4).
  Adaptive power writes MUST route through the existing clamped path — no
  new clamp bypass.
- **Phase 1 / §2 (E-stop):** `updateUi_estop_pressed` iterates
  `self.lasers` calling `.off()` synchronously on the GUI thread,
  lock-free. `off()` is synchronous, returns `None` immediately, never
  offloaded. Every laser write re-checks `estop_event` before energizing
  and re-checks before the HAL write. Adaptive writes inherit this —
  re-check before every exposure/power write, abort on set.
- **Phase 6 / §11 (threading):** `QThread`+`moveToThread` workers;
  `estop_event` cooperative polling at all loop sites; close-ordering
  contract (`sig_finished` → `thread.quit` → `wait`). No cross-thread
  `ui.*` reads from workers — bounds pre-sampled on the GUI thread and
  passed as worker constructor args.
- **Phase 9 (multi-channel):** `StackWorker.run` per-plane cycle
  (`select_laser(0)`→acquire→capture frame1→`select_laser(1)`→acquire→
  capture frame2→enqueue both for multi-channel; single acquire for
  single-channel). One-laser-energized invariant via
  `HardwareManager.select_laser(idx)`. The adaptive loop composes with
  this cycle — intensity readback happens after each channel's acquire,
  exposure/power adjustments apply before the next plane's cycle.
- **Phase 8 (metadata):** HDF5 per-plane attrs + Zarr `omero` metadata
  read from live instances — the per-plane exposure/power trajectory
  extends this via `_write_laser_metadata` / `_write_acquisition_metadata`.
- **Phase 08.1 (shell):** left-rail QToolButton + QStackedWidget shell
  with 8 per-panel widget modules. Stack-plan summary (REQ-07.1-16) and
  mode/state badge (Phase 07.1) are reusable feedback artifacts. The
  adaptive config group lands in the Stack panel; the trajectory widget
  lands as a QDockWidget (visible across panels).
- **Phase 7 (PySide6/Qt6 + Python 3.12):** codebase on PySide6/Qt6,
  Python 3.12. `pco` caps at `<3.13` so 3.14 is blocked.
</domain>

<decisions>
## Implementation Decisions

### Control variable strategy

- **D-01: Hybrid — exposure primary, laser power fallback.** The adaptive
  loop adjusts exposure (via `exposed_lines`/`line_time` in Lightsheet
  shutter mode — the exposure_time spinbox is disabled there but the
  underlying mechanism is the same, quantized to line-time steps) within
  operator-configured bounds first. Laser power is written only when
  exposure hits its min or max bound and the target intensity is still not
  met — power acts as the last-resort gain at the exposure dynamic-range
  extremes. This minimizes photobleaching (exposure absorbs most dynamic
  range — raising exposure increases dose linearly without raising peak
  irradiance, per the CLEM principle) while preserving full dynamic range
  (power rescues regions where even max exposure is insufficient). The
  PCO SDK explicitly confirms per-plane exposure changes during recording
  without re-arming (settle latency ~1 frame, which per-plane reactive
  feedback already accommodates). Per-plane laser writes are rare (only
  at exposure bounds) → less wear on the safety-critical two-layer clamp
  path than a power-only approach. The two control variables interact
  (exposure changes frame time → photon flux per frame shifts
  independently of power) → the control law must decouple them (see D-03).
  — **Reversibility:** costly — the StackWorker per-plane loop body is
  restructured around the exposure-then-power-fallback decision tree;
  switching to exposure-only or power-only later restructures it again
  (but the hybrid composes with either, so the controller seam survives a
  variable-swap).

### Per-channel vs global control

- **D-02: Hybrid — shared exposure per-plane (fast) + per-laser power trim
  per-N-plane block (slow), brighter channel drives exposure, both
  channels match in intensity.** The single shared camera makes exposure
  an inherently global DOF — it cannot be set per-channel within the
  sequential `select_laser(0)→acquire→select_laser(1)→acquire` cycle.
  The shared exposure adjusts per-plane based on the **brighter
  channel's** intensity (prevents saturation — if either channel is at
  the target ceiling, exposure decreases). Each laser's power trim then
  equalizes the dimmer channel to match the brighter one, so both
  channels converge to the same 90-95% target (cross-channel balancing —
  the operator wants both channels to match in intensity, not just each
  hitting the target independently). Power trim runs per-N-plane block
  (amortizes the iBeam serial ~3s `set_power` round-trip over N planes;
  block size N ~5-10 planes → 0.3-0.6s/plane iBeam amortized). L1 (fast
  DAQ AO, sub-ms) can trim per-plane if needed; L2 (iBeam serial, 3s)
  trims per-block. In single-channel mode, the loop drives the one active
  channel's exposure + power (no cross-channel balancing needed). The
  per-plane cycle composes naturally: compute one exposure update per
  plane from the brighter channel's intensity, apply L1 power trim
  per-plane (if exposure is at bound), apply L2 power trim only at block
  boundaries, log both loop trajectories per plane in metadata. —
  **Reversibility:** costly — the loop state struct carries per-stack
  exposure + per-laser power + block counter; switching to shared-only
  or per-laser-only restructures the state and the per-plane update
  logic.

### Feedback granularity & control law

- **D-03: Hybrid pilot feedforward + per-plane PI residual (FF+FB), with
  re-acquire fallback; L2 serial-block MVP, analog-per-plane post-cable.**
  A few sparse pilot frames at the start of the stack fit a smooth
  exposure/power-vs-depth trajectory for the monotonic-ish iDISCO+
  brainstem→centre signal drop (feedforward — eliminates oscillation on
  the monotonic trend by replaying pre-computed per-plane deltas). Per-
  plane PI (P+I, D=0 — the standard scanning-microscopy choice, D
  suppressed to avoid noise amplification) corrects residual error
  against the 90-95% target (feedback — smooth proportional tracking of
  the gradual 6.5 µm/step signal change, integral removes steady-state
  offset). A re-acquire fallback re-shoots a plane when its intensity
  deviates beyond a configurable threshold from expectation (handles
  large excursions — the "wrong frame" is re-shot, per the operator's
  vision). Integral windup is clamped to the two-layer power limits.
  **L2 actuator phasing:** the MVP ships with L2 power via serial
  `set_power` (block-level, every N planes — the 3s round-trip is
  amortized). When the operator installs a trigger cable (iBeam "Analog
  In" SMB → spare DAQ AO line, e.g. Dev7/ao1 — the DAQ-gated analog
  modulation path deferred from Phase 9 D-01), L2 upgrades to per-plane
  analog modulation (µs-scale DAQ AO writes, zero serial round-trips).
  The loop architecture composes with either L2 actuator path — the
  adapter seam is at the `_write_laser2_power` call site (serial vs DAQ
  AO), and the pilot+PI control law is actuator-agnostic. —
  **Reversibility:** one-way — the pilot+PI+fallback control law and the
  per-plane trajectory logging schema are a published contract; the L2
  actuator adapter seam is reversible (serial ↔ analog) but the control-
  law shape and metadata schema are not without a migration.

### Operator UI & bounds

- **D-04: Stack panel config group + dockable pyqtgraph trajectory widget
  (QDockWidget).** A collapsible adaptive config group in the existing
  Stack panel: enable toggle + FieldSpecSpinBox bounds (min/max exposure,
  min/max power per laser, target intensity band lo/hi %, default 90-95%,
  re-acquire deviation threshold, block size N for L2 power trim). The
  trajectory is shown in a dockable pyqtgraph `PlotWidget` placed in a
  `QMainWindow` dock area (not on a stacked panel — the left-rail
  `QStackedWidget` shows one page at a time, so a plot on any stacked
  panel vanishes when the operator switches to Laser/Motor; the dock
  stays visible across all panels and is floatable to a 2nd monitor,
  matching the mature AareDAQ/BEC Widgets pattern of stacked-nav +
  docked-live-telemetry). The plot shows per-plane intensity vs target
  band with twin-axis exposure/power, and re-acquire fallback events as
  markers. The mode/state badge (Phase 07.1) shows "ADAPTIVE RUNNING".
  Bounds are pre-sampled on the GUI thread and passed as `StackWorker`
  constructor args (AGENTS.md §11 — no cross-thread `ui.*` reads from the
  QThread worker). The adaptive group is hidden when the toggle is off
  (opt-in-on-top-of-fixed-default — the default stack behavior is
  unchanged). — **Reversibility:** costly — the QDockWidget requires
  shell dock-area wiring (the shell must expose `QMainWindow` dock areas)
  and dock-state persistence; reverting to a summary-readout-only
  approach touches the same shell wiring.

### Claude's Discretion
- The exact frame intensity statistic (mean vs 99th-percentile vs max) —
  Claude may pick the statistic that best correlates with sensor
  saturation risk, as long as it is computed from the reconstructed frame
  numpy array and is mock-testable with a synthetic profile.
- The exact pilot-frame count and spacing for the feedforward trajectory
  fit — Claude may choose a count that balances upfront time vs fit
  quality, as long as it is operator-configurable with a sensible default.
- The exact PI gain defaults (Kp, Ki) — Claude may pick defaults that
  track the 6.5 µm/step gradual change without oscillation, as long as
  they are operator-configurable and the integral windup is clamped to
  the two-layer power limits.
- The exact block size N default for L2 power trim — Claude may pick a
  default that amortizes the iBeam 3s round-trip acceptably (~5-10
  planes), as long as it is operator-configurable.
- The exact re-acquire deviation threshold default — Claude may pick a
  default that distinguishes real excursions from sensor noise, as long
  as it is operator-configurable.
- The exact pyqtgraph plot layout (axes, colors, marker styles) — Claude
  may match the existing GUI visual language.
- The trajectory fit model (linear vs spline vs polynomial) for the
  feedforward — Claude may pick the model that best fits the monotonic
  iDISCO+ profile without overfitting, as long as it is mock-testable.
- Whether the L2 analog-modulation adapter (post-cable) is a new
  `DAQLaser`-shaped L2 backend or an extension of `IBeamSmartLaser` —
  Claude may pick the architecture that best composes with the existing
  `ILaser` ABC and the DAQ-gated path, as long as the two-layer clamp
  and E-stop invariants are preserved.

### Folded Todos
None folded. The two pending todos matched by `todo.match-phase 10`
(`phase6-cross-thread-ui-widget-reads.md` and
`preview-mode-auto-laser-control.md`) are both stale — already resolved in
prior phases (Phase 6 eliminated cross-thread widget reads via
`_cache_auto_laser_flags` + pre-sampled worker args; PreviewWorker now
auto-starts lasers per the Phase 1 gap-closure work). See Reviewed Todos.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Safety contracts (read first)
- `AGENTS.md` §2 — laser power clamping (two-layer), E-stop synchronous
  GUI-thread laser-off (lock-free, `off()` synchronous never offloaded),
  frozen `DeviceBundle` safety property, "do not send power-setting
  commands to the rig unless explicitly asked."
- `AGENTS.md` §11 — no cross-thread Qt widget reads from workers;
  pre-sample on the GUI thread, pass as worker constructor args.
- `lightsheet/hal/interfaces.py` — `ILaser` ABC (mW-canonical, `off()`
  synchronous contract, per-instance `_lock` RLock), `ICameraCore`
  (`exposure_time`, `shutter_mode`, `lightsheet_exposed_lines`,
  `lightsheet_delay_lines`, `line_time` attributes; `set_exposure_time`,
  `arm_scan`, `start_recorder`, `monitor_recorder`, `copy_recorder_images`
  methods).
- `lightsheet/config_schema.py` — `[iBeam] Max Power` startup gate
  (rejects > 150000 µW), `[Camera] Exposure Time` warning on negative;
  safety-critical vs non-safety validation tiers.

### Acquisition + laser orchestration (the code Phase 10 extends)
- `lightsheet/gui/workers.py` — `StackWorker.run` (the per-plane loop at
  lines 732-1019 — the integration point for the adaptive feedback hook),
  `_AcquireScanMixin.acquire_scan` (the per-frame grab, reusable as-is),
  `PreviewWorker`/`LiveWorker`/`SingleWorker` (continuous modes — adaptive
  is stack-only, but the exposure/power write patterns are shared).
- `lightsheet/gui/coordinators/hardware_manager.py` —
  `_write_laser1_power`/`_write_laser2_power` (estop-guarded,
  RLock-protected, two-layer-clamped power write paths — the adaptive
  power writes route through these), `select_laser(idx)` (the
  one-laser-energized invariant choke point), `start_lasers`/`stop_lasers`,
  `_toggle_laser1`/`_toggle_laser2` (cross-deenergization pattern).
- `lightsheet/gui/shell/controller.py` — `updateUi_estop_pressed` (the
  E-stop kill path — MUST stay lock-free and unchanged),
  `_cache_auto_laser_flags` (GUI-thread auto-laser flag sampling pattern
  to mirror for adaptive bounds sampling).

### Camera exposure + shutter mode (the exposure actuator path)
- `lightsheet/gui/coordinators/acquisition_coordinator.py` —
  `updateUi_camera_shutter_mode` (lines 391-418 — the shutter-mode-
  dependent enable/disable of `doubleSpinBox_cameraExposureTime`; in
  Lightsheet shutter mode the exposure spinbox is DISABLED and exposure
  is driven via `line_time` + `exposed_lines` instead),
  `updateUi_camera_exposure_time` (lines 420-424 — propagates UI exposure
  to `camera.exposure_time`).
- `lightsheet/gui/panels/ui_acquisition_panel.py` —
  `doubleSpinBox_cameraExposureTime` (range 25-1000 ms, disabled in
  Lightsheet shutter mode), `doubleSpinBox_cameraLineTime`,
  `doubleSpinBox_cameraExposedLines`.
- `lightsheet/gui/widgets/field_spec.py` — `FieldSpecSpinBox` convention
  with unit/range/step metadata (the adaptive bounds spinboxes follow
  this pattern).
- `lightsheet/hal/real/camera.py` — PCO camera implementation (63
  exposure-related references; `set_exposure_time`, `arm_scan`,
  `start_recorder`, `monitor_recorder`, `copy_recorder_images`).

### Save pipeline (the metadata extension point)
- `lightsheet/gui/coordinators/frame_saver_controller.py` —
  `_write_laser_metadata` / `_write_acquisition_metadata` (HDF5 per-plane
  attrs + Zarr `omero` metadata from live instances — the per-plane
  exposure/power trajectory extends these), `cam.exposure_time` readback
  (lines 465, 1631).

### GUI shell + panels (the UI integration point)
- `lightsheet/gui/panels/stack_panel.py` — the Stack panel (where the
  adaptive config group lands), `acquisition_table_manager.py` (the
  table acquisition manager — adaptive bounds may apply per-row).
- `lightsheet/gui/shell/controller.py` — the left-rail QToolButton +
  QStackedWidget shell (Phase 08.1), `wire_collaborators` (signal
  wiring pattern), mode/state badge (Phase 07.1 — shows "ADAPTIVE
  RUNNING").
- `lightsheet/gui/panels/ui_acquisition_panel.ui` — the Acquisition panel
  `.ui` file (reference for the Stack panel adaptive group `.ui` pattern).

### Reference docs (from ROADMAP.md — for the planner/researcher)
- `~/Downloads/Voigt et al. - 2019 - The mesoSPIM initiative open-source
  light-sheet m.pdf` — mesoSPIM open-source light-sheet microscope design
  (our rig follows the main design philosophy, concrete implementation
  differs).
- `~/Downloads/CLE7EW3G.pdf` — iDISCO+ protocol (tissue clearing;
  dibenzyl ether refractive index).
- `~/Downloads/Kirst et al. - 2020 - Mapping the Fine-Scale Organization
  and Plasticity.pdf` — application context (cleared-brain imaging).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`StackWorker.run` per-plane loop** (`workers.py:850-1019`): the
  natural integration point for the adaptive feedback hook — intensity
  readback after each channel's `acquire_scan`, exposure/power adjustment
  before the next plane's cycle. The loop already polls `estop_event` and
  `stack_mode_started` at each plane boundary.
- **`_write_laser1/2_power(pct)`** (`hardware_manager.py:144-218`): the
  estop-guarded, RLock-protected, two-layer-clamped power write paths —
  adaptive power writes route through these unchanged. The cooperative-
  skip pattern (check `estop_event` before the HAL write, re-check before
  the write, force `mw=0` if set) is preserved.
- **`_AcquireScanMixin.acquire_scan`** (`workers.py:209-319`): the per-
  frame grab — produces `self._shell.reconstructed_frame` (numpy array),
  the intensity readback source. Reusable as-is inside the adaptive cycle.
- **`select_laser(idx)`** (`hardware_manager.py:477`): the one-laser-
  energgized invariant choke point — the adaptive loop composes with the
  Phase 9 per-plane cycle unchanged.
- **`FrameSaverController._write_laser_metadata` /
  `_write_acquisition_metadata`** (`frame_saver_controller.py`): HDF5 +
  Zarr metadata from live instances — the per-plane exposure/power
  trajectory extends these with new attrs per plane.
- **Stack-plan summary (REQ-07.1-16) + mode/state badge (Phase 07.1)**:
  reusable read-only feedback artifacts — the badge shows "ADAPTIVE
  RUNNING", the summary can carry a one-line intensity readout.
- **`FieldSpecSpinBox`** (`widgets/field_spec.py`): the numeric input
  convention with unit/range/step metadata — the adaptive bounds
  spinboxes follow this pattern.

### Established Patterns
- **GUI-thread pre-sampling → worker constructor args** (AGENTS.md §11):
  all adaptive bounds (min/max exposure, min/max power, target band,
  thresholds, block size N) are pre-sampled on the GUI thread in the
  mode-button slot and passed as `StackWorker` constructor args — the
  worker thread never reaches into `ui.*`.
- **`estop_event` cooperative polling** (Phase 6): the adaptive loop
  checks `estop_event` before every exposure/power write and aborts on
  set — the E-stop kill path stays lock-free and unchanged.
- **Two-layer power clamping** (§2): `ILaser.set_power(mw)` clamps to
  `[0, max_power]` at the interface; each backend clamps again in its
  native unit. Adaptive power writes inherit this — no new clamp bypass.
- **Per-plane loop shape** (Phase 9): move → per-channel cycle → save →
  next plane. The adaptive feedback hook inserts after the per-channel
  acquire(s) and before the next plane's move.
- **QDockWidget for live telemetry** (Phase 08.1 shell pattern): the
  trajectory widget follows the stacked-nav + docked-telemetry pattern.

### Integration Points
- **`StackWorker.__init__`**: gains adaptive config args (bounds, target
  band, thresholds, block size N, pilot frame config) pre-sampled on the
  GUI thread.
- **`StackWorker.run` per-plane loop**: gains an adaptive feedback hook
  after each channel's `acquire_scan` — reads frame intensity, computes
  exposure/power adjustment via the pilot+PI controller, applies it
  before the next plane.
- **`HardwareManager`**: gains an adaptive power write path (routes
  through existing `_write_laser1/2_power` — no new clamp bypass). The
  L2 analog-modulation adapter (post-cable) plugs in here.
- **`FrameSaverController` metadata**: gains per-plane exposure/power
  trajectory attrs (extends `_write_laser_metadata` /
  `_write_acquisition_metadata`).
- **Stack panel**: gains the adaptive config group (QGroupBox with
  toggle + FieldSpecSpinBox bounds).
- **Shell**: gains the QDockWidget dock-area wiring for the trajectory
  plot widget.
- **New module**: a pure-Python adaptive controller module (no Qt) —
  unit-testable against the mock HAL's synthetic bright→dim profile,
  containing the pilot-frame fit, PI controller, and re-acquire fallback
  logic.

</code_context>

<specifics>
## Specific Ideas

- **Operator vision:** "Stay within 90-95% intensity. Because we take
  small steps through the brain (6.5 µm per step) I think we can
  gradually adjust on the fly based on the previous image. Maybe a
  fallback could be added for when the intensity changes too much so
  that the wrong frame can be re-acquired."
- **Cross-channel balancing:** "I also would like both channels to match
  in intensity." — the per-laser power trim should equalize the two
  channels to the same target, not just each hitting 90-95%
  independently.
- **L2 trigger cable plan:** "I will install a trigger cable for L2 soon,
  so then that speed issue can be resolved." — the iBeam "Analog In" SMB
  → spare DAQ AO line cable installation is an operator rig task that
  unblocks per-plane L2 analog modulation (the DAQ-gated path deferred
  from Phase 9 D-01). The MVP ships with L2 serial-block; the post-cable
  upgrade is a drop-in adapter at the `_write_laser2_power` call site.
- **PCO SDK confirmation (from research):** the PCO driver explicitly
  supports per-plane exposure changes during recording without re-arming
  ("The properties `exposure_time` and `delay_time` are the only
  exception. These can be called up during the recording."). Settle
  latency ~1 frame. Exposure is quantized to line-time steps, so the
  Lightsheet-shutter-mode "exposure_time spinbox disabled" constraint is
  a UI/abstraction constraint, not a hardware limit — driving
  `exposed_lines` reaches the same mechanism.
- **Photobleaching literature (from research):** CLEM (Controlled Light
  Exposure Microscopy) and light-sheet dose-metering papers consistently
  favor reducing duration/exposure in bright regions over reducing
  intensity/power, because raising power increases peak irradiance and
  accelerates bleaching. This grounds the exposure-primary hybrid (D-01).

</specifics>

<deferred>
## Deferred Ideas

- **L2 DAQ-gated analog modulation hardware wiring** (iBeam "Analog In"
  SMB → Dev7/ao1 cable) — operator rig task, not a software deliverable.
  The software architecture composes with the analog path when the cable
  is installed; the MVP ships with the serial-block L2 path. Post-cable
  upgrade is a drop-in adapter at the `_write_laser2_power` call site.
- **Per-line / interleaved (within-frame) adaptive exposure** — this
  phase is per-plane (or per-block) only; per-line would be a future
  phase.
- **Adaptive mode for continuous modes (live/preview)** — adaptive is
  stack-mode only; live/preview have no per-plane boundary to feedback
  over. A future phase could add frame-rate adaptive exposure for
  continuous modes if wanted.
- **PCO built-in auto-exposure** (`autoExposureOn` / `configureAutoExposure`
  with smoothness 1-10) — vendor-supported zero-code path, but drives
  `exposure_time` (disabled in Lightsheet shutter mode, likely inert),
  targets PCO's internal setpoint (not the operator-configurable 90-95%
  band), emits no per-plane trajectory, and supports no re-acquire
  fallback. Ruled out for this phase; could be revisited if rig-
  confirmation shows it is active in shutter mode AND the operator
  accepts PCO's internal setpoint.

### Reviewed Todos (not folded)
- `phase6-cross-thread-ui-widget-reads.md` — stale, already resolved in
  Phase 6 (`_cache_auto_laser_flags` + pre-sampled worker args eliminated
  cross-thread widget reads). Not folded — the adaptive bounds sampling
  follows the same established pattern, not a new todo.
- `preview-mode-auto-laser-control.md` — stale, already resolved in
  Phase 1 gap-closure work (PreviewWorker now auto-starts lasers). Not
  folded — adaptive is stack-only, not preview.

</deferred>

---

*Phase: 10-adaptive-exposure-laser-power-control*
*Context gathered: 2026-08-30*
