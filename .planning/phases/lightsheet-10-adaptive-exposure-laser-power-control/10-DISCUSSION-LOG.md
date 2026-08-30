# Phase 10: Adaptive Exposure & Laser Power Control - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-08-30
**Phase:** 10-adaptive-exposure-laser-power-control
**Areas discussed:** Control variable strategy, Per-channel vs global control, Feedback granularity & control law, Operator UI & bounds

---

## Control variable strategy

| Option | Description | Selected |
|--------|-------------|----------|
| A. Exposure-only | Drive exposed_lines/line_time per-plane; laser power held at fixed safe baseline. Zero per-plane laser writes — safest for the two-layer clamp, non-bleaching (CLEM). PCO driver confirmed supports per-plane exposure changes during recording. Cannot rescue regions where max exposure is insufficient. | |
| B. Laser power only | Exposure fixed; per-plane laser power writes via _write_laser1/2_power. Fast (DAQ AO sub-ms for L1), no scan-timing perturbation, large dynamic range. But photobleaching risk, every plane touches safety-critical clamp path, L2 serial 3s stalls loop. | |
| C. Hybrid (exposure primary, power fallback) | Adjust exposure within bounds first; write laser power only when exposure hits min/max bound. Best SNR/dose balance, per-plane laser writes rare (only at bounds). Most complex control law, two variables interact, largest testing surface. | ✓ |
| D. PCO built-in auto-exposure | Use PCO SDK autoExposureOn with smoothness factor. Vendor-supported, zero control-law code. But black-box target (not 90-95% band), drives exposure_time which is disabled in Lightsheet shutter mode (likely inert), no trajectory emitted, no re-acquire path. | |

**User's choice:** C. Hybrid (exposure primary, power fallback)
**Notes:** The hybrid minimizes photobleaching (exposure absorbs most dynamic range — CLEM principle) while preserving full dynamic range (power rescues regions where max exposure is insufficient). Per-plane laser writes are rare (only at exposure bounds) → less wear on the safety-critical two-layer clamp path. The PCO SDK confirms per-plane exposure changes during recording without re-arming. Rig-confirmation needed: does changing exposed_lines per-plane perturb galvo/ETL scan sync?

---

## Per-channel vs global control

| Option | Description | Selected |
|--------|-------------|----------|
| A. Per-laser independent power (per-plane) | Each fluorophore tracked to its own 90-95% independently per-plane. Maximally reactive but iBeam 3s round-trip blocks per-plane cycle on every L2 write; pylablib "lagging replies" error state; asymmetric latency makes tuning hard. | |
| B. Shared exposure, fixed powers | Single global exposure DOF matches shared camera; fast (no serial); one-laser-energized invariant stays clean; simplest loop state; lowest overhead. Cannot independently target 90-95% per channel — one saturates while other is dim. | |
| C. Hybrid (shared exposure + per-laser power trim per-block) | Shared exposure per-plane (fast, no serial) + per-laser power trim per-N-plane block (slow, amortizes iBeam 3s over N planes). Handles per-fluorophore differences; L1 trims per-plane (fast DAQ), L2 trims per-block; composes with L1→acquire→L2→acquire cycle. | ✓ |
| D. Per-laser power, block-level, fixed exposure | Per-laser loop state, block-level update (amortizes iBeam 3s), fixed exposure. Per-channel targeting but fixed exposure wastes dynamic range; slow response to global per-plane drift. | |

**User's choice:** C. Hybrid (shared exposure + per-laser power trim per-block)
**Notes:** "I also would like both channels to match in intensity." — the per-laser power trim should equalize the two channels to the same target, not just each hitting 90-95% independently. The brighter channel drives the shared exposure (prevents saturation); the per-laser power trim equalizes the dimmer channel to match. Block size N ~5-10 planes amortizes the iBeam 3s round-trip to 0.3-0.6s/plane.

---

## Feedback granularity & control law

| Option | Description | Selected |
|--------|-------------|----------|
| Per-plane reactive, bang-bang (deadband) | Simplest, no gain tuning, deterministic clamp steps, easy to mock-test. Quantised jumps cause visible banding; 5%-wide band vs sensor noise → frequent toggling; no trend memory, fights monotonic drop. | |
| Per-plane reactive, PI (P+I, D=0) | Smooth tracking of gradual 6.5µm/step change; integral removes steady-state offset; standard scanning-microscopy choice. Requires gain tuning; integral windup clamped to two-layer limits; L2 3s round-trip infeasible per-plane. | |
| Per-N-plane block, PI (block-smoothed) | Block period ≥ iBeam 3s so L2 joins loop; averaging suppresses noise-driven oscillation; fewer serial writes. Coarser correction — up to N planes off-target; must pick N vs stack speed. | |
| Pilot-frame-then-track (feedforward) | Acquire sparse pilot frames, fit smooth trajectory for monotonic iDISCO+ drop, replay open-loop. Zero per-plane serial round-trips, no oscillation, trivially mock-testable. No correction for sample-local deviations; bad fit uncorrected except by re-acquire. | |
| Hybrid: pilot feedforward + per-plane PI (FF+FB) | Pilot feedforward handles monotonic trend (small predictable deltas, no oscillation); per-plane PI only corrects residual (small safe gains); re-acquire fallback handles large deviations. Best tracking for mock-test criterion. Most code surface; two parameter sets to tune. | ✓ |

**User's choice:** Hybrid: pilot feedforward + per-plane PI (FF+FB)
**Notes:** "I think option D, it seems the most complete. I will install a trigger cable for L2 soon, so then that speed issue can be resolved." — the operator plans to install a trigger cable (iBeam "Analog In" SMB → spare DAQ AO line) which eliminates the iBeam 3s serial latency and unblocks per-plane L2 analog modulation. MVP ships with L2 power via serial (block-level, every N planes); the post-cable upgrade is a drop-in adapter at the _write_laser2_power call site. The loop architecture composes with either L2 actuator path.

---

## Operator UI & bounds

| Option | Description | Selected |
|--------|-------------|----------|
| 1. Stack panel group + summary/badge readout (MVP) | Collapsible QGroupBox in existing Stack panel: enable toggle + FieldSpecSpinBox bounds. Trajectory = one-line readout in stack-plan summary + mode badge "ADAPTIVE RUNNING". Reuses 2 existing artifacts, no nav change, no new dep, lowest surface. Text-only — no trend visualization; trajectory invisible when switching panels. | |
| 2. Dedicated 9th Adaptive panel + embedded plot | New QToolButton + QStackedWidget page: enable toggle, bounds, embedded pyqtgraph PlotWidget. All adaptive concerns in one place, rich trend viz. But trajectory disappears when switching panels (QStackedWidget = one page) — hurts "watch during run"; 9th nav button; pyqtgraph dep. | |
| 3. Stack panel group + dockable trajectory (full-maturity) | Config (toggle + bounds) in collapsible group inside Stack panel; trajectory in QDockWidget (pyqtgraph PlotWidget) in QMainWindow dock area, floatable to 2nd monitor, visible across all left-rail pages. Matches AareDAQ/BEC mature pattern. Requires shell dock-area wiring; pyqtgraph dep; dock state persistence. | ✓ |
| 4. Acquisition panel config + summary readout | Toggle + bounds in Acquisition panel where exposure/power already live (DRY via FieldSpecSpinBox); Stack start reads sampled bounds; trajectory via summary readout. Bounds next to fields they constrain. But operator must visit Acquisition to configure and Stack to start — split workflow; exposure disabled in Lightsheet shutter mode → co-locating adaptive exposure bound with exposure ms field can mislead. | |

**User's choice:** 3. Stack panel group + dockable trajectory (full-maturity)
**Notes:** The dockable trajectory widget stays visible across all left-rail panel switches (unlike a stacked-panel plot which vanishes when the operator switches to Laser/Motor) and is floatable to a 2nd monitor — matching the mature AareDAQ/BEC Widgets pattern of stacked-nav + docked-live-telemetry. Config is co-located with the stack it modifies (avoiding the Lightsheet-shutter-mode exposure-field confusion that hurts option 4). Bounds pre-sampled on GUI thread, passed as StackWorker constructor args (AGENTS.md §11).

---

## Follow-up: Exposure driver channel

| Option | Description | Selected |
|--------|-------------|----------|
| Brighter channel drives exposure | The shared exposure adjusts based on the brighter channel's intensity. Prevents saturation — if either channel is at 95%, exposure decreases. The dimmer channel is then rescued by its per-laser power trim. | ✓ |
| Dimmer channel drives exposure | The shared exposure adjusts based on the dimmer channel's intensity. Prevents under-exposure — if either channel is below 90%, exposure increases. The brighter channel is then held back by its per-laser power trim. | |
| Average of both channels | The shared exposure adjusts based on the average of both channels' intensities. Both channels converge toward the target together; per-laser power trim corrects the residual difference. | |
| Min of both (most conservative) | The shared exposure adjusts based on the min of both channels' intensities. Both channels must be ≥90% before exposure decreases. | |

**User's choice:** Brighter channel drives exposure
**Notes:** Prevents sensor saturation — the brighter channel is the one at risk of hitting the ceiling. The dimmer channel is rescued by its per-laser power trim (raised independently to match the brighter channel's intensity).

---

## Follow-up: MVP phasing for L2 power adaptation

| Option | Description | Selected |
|--------|-------------|----------|
| Ship now with L2 serial (block), upgrade after cable | Ship the full hybrid (pilot+PI) now with L2 power via serial (block-level, every N planes). When the trigger cable is installed, upgrade L2 to per-plane analog modulation (DAQ AO). The loop architecture composes with either L2 actuator path. | ✓ |
| Ship MVP with L2 fixed, add L2 adaptation after cable | The MVP ships with L2 power held fixed (no per-plane or per-block L2 writes) and only L1 + exposure adapt per-plane. L2 joins the loop in a follow-up after the cable is in. | |
| Wait for cable, build analog L2 path only | Build the full per-plane analog L2 path now (DAQ AO to iBeam Analog In) and ship only after the cable is installed. The serial L2 path is not used for adaptive power at all. | |

**User's choice:** Ship now with L2 serial (block), upgrade after cable
**Notes:** The loop architecture is built to compose with either L2 actuator path — the serial-block path is the MVP, the analog-per-plane path is the post-cable upgrade. This unblocks MVP testing on the mock path immediately. The adapter seam is at the _write_laser2_power call site.

---

## Claude's Discretion

- The exact frame intensity statistic (mean vs 99th-percentile vs max)
- The exact pilot-frame count and spacing for the feedforward trajectory fit
- The exact PI gain defaults (Kp, Ki) — operator-configurable with sensible defaults
- The exact block size N default for L2 power trim (~5-10 planes)
- The exact re-acquire deviation threshold default
- The exact pyqtgraph plot layout (axes, colors, marker styles)
- The trajectory fit model (linear vs spline vs polynomial) for the feedforward
- Whether the L2 analog-modulation adapter (post-cable) is a new DAQLaser-shaped L2 backend or an extension of IBeamSmartLaser

## Deferred Ideas

- L2 DAQ-gated analog modulation hardware wiring (iBeam "Analog In" SMB → Dev7/ao1 cable) — operator rig task, not a software deliverable
- Per-line / interleaved (within-frame) adaptive exposure — future phase
- Adaptive mode for continuous modes (live/preview) — future phase
- PCO built-in auto-exposure (autoExposureOn) — ruled out for this phase; could be revisited if rig-confirmation shows it is active in shutter mode AND the operator accepts PCO's internal setpoint
