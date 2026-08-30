---
gsd_state_version: 1.0
milestone: v2022.9
milestone_name: Brownfield Modernization
current_phase: 10 — Adaptive Exposure & Laser Power Control
current_phase_name: Adaptive Exposure & Laser Power Control
current_plan: Not started
status: planning
stopped_at: Phase 10 context gathered
last_updated: "2026-08-30T23:43:25.019Z"
last_activity: 2026-08-30
progress:
  total_phases: 15
  completed_phases: 13
  total_plans: 100
  completed_plans: 100
last_activity_desc: Phase lightsheet-09 complete, transitioned to Phase 10
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-08-25)

**Core value:** The operator can reliably acquire light-sheet image stacks with safe, GUI-driven control of all hardware — including lasers — and the codebase can be developed and tested without the physical microscope present.
**Current focus:** Phase 10 — Adaptive Exposure & Laser Power Control

## Current Position

Phase: lightsheet-09 (multi-channel-sequential-acquisition) — EXECUTING
Plan: Not started
Status: Ready to plan
Last activity: 2026-08-30

Note: Phase 05.1 (testing-suite-redesign) is COMPLETE — 7/7 plans executed, VERIFICATION.md status=passed (7/7 must-haves verified). Phase 06 is COMPLETE: 06-01 (preview → PreviewWorker QThread), 06-02 (live+single → LiveWorker/SingleWorker QThread + _AcquireScanMixin + B-03 elimination for acquire_scan), 06-03 (StackWorker + sig_refresh_position_horizontal queued signal + full B-03 elimination + uniform closeEvent), 06-04 (wire_collaborators reference-cycle break), and 06-05 (test-workaround revert — D-06: sip.delete teardown, pytest_runtest_teardown hook, and -p no:xdist all removed and verified stable with 3 consecutive green runs per step) executed. Code review gate (06-REVIEW.md) found a Critical safety bug — LiveWorker.__init__ did not set _save_description/_save_stitch_blend that acquire_scan() reads, so the first live-mode frame raised AttributeError inside the try block and skipped stop_lasers() cleanup (Class IIIB lasers left energized); fixed inline (workers.py:330-333) with regression test test_live_mode_worker_acquire_scan_does_not_skip_cleanup. Verification gate (06-VERIFICATION.md) verdict PASSED — all 8 goal components verified (QThread+moveToThread model, quit()+wait(5000) shutdown, signal-lambda cycle broken, segfault eliminated/xdist re-enabled, safety invariants preserved, golden masters byte-identical, suite 882 green, review finding resolved). RFR-03 and all six ROADMAP Phase 6 success criteria are satisfied.

Progress: [██████████] 100% (Phases 1-8 + 05.1 + 07.1 complete; Phase 08.1 context gathered, ready to plan)

## Performance Metrics

**Velocity:**

- Total plans completed: 31
- Average duration: —
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| lightsheet-04 | 5 | - | - |
| lightsheet-06 | 5 | - | - |
| lightsheet-08 | 7 | - | - |
| 08.1 | 6 | - | - |
| lightsheet-09 | 8 | - | - |

**Recent Trend:**

- Last 5 plans: —
- Trend: —

*Updated after each plan completion*
**Per-Plan Metrics:**

| Plan | Duration | Tasks | Files |
|------|----------|-------|-------|
| Phase 01 P01 | 12m | 3 tasks | 6 files |
| Phase 01 P02 | 10m | 2 tasks | 5 files |
| Phase 01 P03 | ~8 min | 2 tasks | 4 files |
| Phase 01 P04 | ~14 min | 3 tasks | 6 files |
| Phase lightsheet-01 P05 | 45min | 2 tasks | 2 files |
| Phase 01 P06 | ~6 min | 1 tasks | 2 files |
| Phase 01 P07 | 4min | 3 tasks | 2 files |
| Phase 01 P08 | 4min | 3 tasks | 2 files |
| Phase 01 P09 | 3min | 3 tasks | 2 files |
| Phase 01 P10 | ~6 min | 3 tasks | 2 files |
| Phase 01 P11 | 5min | 3 tasks | 2 files |
| Phase lightsheet-02 P01 | ~12 min | 3 tasks | 5 files |
| Phase lightsheet-02 P08 | ~12 min | 3 tasks | 1 files |
| Phase lightsheet-02 P02 | ~10 min | 2 tasks | 7 files |
| Phase lightsheet-02 P03 | ~8 min | 2 tasks | 3 files |
| Phase lightsheet-02 P04 | ~6 min | 1 tasks | 2 files |
| Phase lightsheet-02 P04 | ~10 min (Task 1: ~6 min, Task 2 operator capture: ~4 min) | 2 tasks | 3 (.gitignore, scripts/snapshot-rig-config.sh, config.rig-specific.ini gitignored) files |
| Phase lightsheet-02 P05 | ~25 min | 3 tasks | 12 files |
| Phase lightsheet-02 P06 | ~15 min | 2 tasks | 5 files |
| Phase lightsheet-02 P07 | ~12 min | 2 tasks | 9 files |
| Phase lightsheet-02 P09 | ~14 min | 1 of 3 (Task 2 checkpoint pending) tasks | 11 files |
| Phase 02 P09 | ~34 min | 3 tasks | 14 files |
| Phase lightsheet-02.1 P01 | ~6 min | 3 tasks | 4 modified + 2 dirs renamed files |
| Phase lightsheet-02.1 P02 | ~5 min | 3 tasks | 8 files |
| Phase 03 P01 | ~6 min | 2 tasks | 14 files |
| Phase lightsheet-03 P02 | ~6 min | 2 tasks | 3 files |
| Phase lightsheet-03 P03 | ~5 min | 2 tasks | 13 files |
| Phase 03 P04 | 25m | 2 tasks | 9 files |
| Phase lightsheet-03 P05 | ~20 min | 2 tasks | 9 files |
| Phase lightsheet-03 P06 | ~12 min | 2 tasks | 5 files |
| Phase lightsheet-03 P07 | 25min | 3 tasks | 14 files |
| Phase lightsheet-03 P08 | ~2 min | 3 tasks | 3 files |
| Phase lightsheet-04 P01 | ~25 min | 3 tasks | 8 files |
| Phase 04 P03 | 45min | 3 tasks | 6 files |
| Phase lightsheet-04 P04 | ~30min | 3 tasks | 3 files |
| Phase lightsheet-04 P05 | ~25min | 2 tasks | 22 files |
| Phase lightsheet-05 P01 | ~12 min | 3 tasks | 9 files |
| Phase lightsheet-05 P02 | ~6 min | 2 tasks | 2 files |
| Phase lightsheet-05 P06 | ~3 min | 1 tasks | 2 files |
| Phase lightsheet-05 P03 | ~10 min | 2 tasks | 2 files |
| Phase lightsheet-05 P04 | ~12 min | 2 tasks | 3 files |
| Phase lightsheet-05 P05 | ~8 min | 2 tasks | 4 files |
| Phase lightsheet-05 P07 | ~10 min | 2 tasks | 4 files |
| Phase 05 P08 | 13min | 2 tasks | 10 files |
| Phase 05 P09 | 25min | 4 tasks | 9 files |
| Phase lightsheet-05 P10 | ~10 min | 1 tasks | 4 files |
| Phase lightsheet-05 P11 | ~12 min | 2 tasks | 5 files |
| Phase lightsheet-05 P12 | ~14 min | 1 tasks | 5 files |
| Phase lightsheet-05 P13 | ~10 min | 1 tasks | 3 files |
| Phase lightsheet-05 P14 | ~12 min | 2 tasks | 4 files |
| Phase 05.1 P01 | ~12 min | 2 tasks | 4 files |
| Phase 05.1 P02 | ~10 min | 2 tasks | 10 files |
| Phase 05.1 P03 | ~5 min | 2 tasks | 4 files |
| Phase 05.1 P04 | ~15 min | 3 tasks | 4 files |
| Phase 05.1 P05 | 25m | 2 tasks | 4 files |
| Phase 05.1 P07 | ~8 min | 2 tasks | 2 files |
| Phase 06 P01 | ~30 min | 3 tasks | 7 files |
| Phase 06 P02 | ~45 min | 3 tasks | 5 files |
| Phase 06 P03 | ~20 min | 2 tasks | 7 files |
| Phase 06 P04 | ~15 min | 2 tasks | 4 files |
| Phase 06 P05 | ~30 min | 3 tasks | 3 files |
| Phase 07 P01 | ~6 min | 2 tasks | 2 files |
| Phase 07 P02 | ~12 min | 2 tasks | 8 files |
| Phase 07 P03 | ~15 min | 3 tasks | 8 files |
| Phase 07 P04 | ~2 min | 2 tasks | 11 files |
| Phase 07 P05 | ~16 min | 2 tasks | 14 files |
| Phase 07 P06 | 25 | 3 tasks | 7 files |
| Phase 07 P07 | 30m | 3 tasks | 18 files |
| Phase 07.1 P02 | 35min | 3 tasks | 6 files |
| Phase 07.1 P01 | 35min | 3 tasks | 6 files |
| Phase 07.1 P03 | 35min | 3 tasks | 21 files |
| Phase 07.1 P04 | 45min | 3 tasks | 17 files |
| Phase 07.1 P05 | 45min | 3 tasks | 8 files |
| Phase 07.1 P07 | 35min | 2 tasks | 12 files |
| Phase 07.1 P08 | 35min | 2 tasks | 8 files |
| Phase lightsheet-08 P01 | ~5 min | 2 tasks | 6 files |
| Phase lightsheet-08 P02 | ~4 min | 2 tasks | 5 files |
| Phase lightsheet-08 P03 | ~2 min | 2 tasks | 3 files |
| Phase lightsheet-08 P04 | ~8 min | 2 tasks | 9 files |
| Phase lightsheet-08 P05 | ~4 min | 2 tasks | 2 files |
| Phase lightsheet-08 P06 | ~2 min | 1 tasks | 3 modified files |
| Phase lightsheet-08 P07 | ~7 min | 2 tasks | 6 files |
| Phase 08.1 P01 | ~10 min | 1 tasks | 4 files |
| Phase 08.1 P02 | 35min | 2 tasks | 162 files |
| Phase 08.1 P04 | 6m | 2 tasks | 7 files |
| Phase 08.1 P06 | 25m | 2 tasks | 8 files |
| Phase 08.1 P05 | 25m | 2 tasks | 14 files |
| Phase 9 P01 | 25min | 2 tasks | 7 files |
| Phase 9 P02 | 20min | 2 tasks | 3 files |
| Phase lightsheet-09 P03 | ~15min | 2 tasks | 3 files |
| Phase lightsheet-09 P04 | ~45min | 1 tasks | 3 files |
| Phase 9 P05 | ~9min | 2 tasks | 6 files |
| Phase lightsheet-09 P06 | 18min | 2 tasks | 8 files |
| Phase lightsheet-09 P07 | 22min | 2 tasks | 5 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Roadmap]: Ship laser GUI on Qt5/3.10 first (Phase 1), rework during Qt6 migration (Phase 7) — experiments come first.
- [Roadmap]: God-object split (Phase 5) and Qt6 migration (Phase 7) kept separate — bundling = unreviewable diff.
- [Roadmap]: Threading migration (Phase 6) sits between split and Qt6 — stable threading model before the port touches it.
- [Roadmap]: Channel-reversal ships mechanism only (Phase 5); the flip is rig-verification work (out of scope).
- [Roadmap]: Zarr saving (Phase 8) and multi-channel sequential acquisition (Phase 9) land after the migration chain as post-migration enhancements. Phase 9 was rescoped 2026-08-23 from Laser Differentiators (DIF-01/02 dropped — both lasers' OEM PSUs handle soft-start/warm-up internally, software ramping/timer added no real value) to Multi-Channel Acquisition (MCA-01..04 — one-movement-cycle dual-channel stack, one-laser-energized invariant, per-channel HDF5 wavelength-suffix + OME-Zarr channel-dimension merge).
- [Roadmap]: Phases 10 (Adaptive Exposure & Laser Power Control) and 11 (Camera Focus Compensation for Brain Lensing) added 2026-08-24 as post-migration acquisition enhancements for cleared iDISCO+ whole-brain imaging; both depend on Phase 9 and are independent of each other.
- [Phase 01]: Stub gating uses try-import + smoke-check (construct Task()/Camera()) instead of find_spec, because nidaqmx and pco are installed-but-broken on Mac
- [Phase 01]: gaussian.fwhm returns 0 (not NaN) on flat/empty/all-below-half-max input; added min==max flat-input guard beyond plan's Pattern 8 logic
- [Phase 01]: Rig SSH probe confirmed iBeam Smart 640 (SN iBEAM-SMART-640-S-G1-15601) on COM4 @ 115200 8-N-1; wavelength is 640 nm not 636 nm; device emits CMD> prompt only (no [OK] terminator)
- [Phase 01]: IBeam driver locks only in _send_cmd (not in public methods) to avoid reentrant-lock deadlock; open() failure in hardware_init is non-fatal so DAQ laser path still works
- [Phase 01]: Laser state revert is conditional on active flag — inactive lasers keep clamped pre-staged setpoint across failed write; active lasers revert to 0V (closes shows-on-is-off hazard)
- [Phase 01]: iBeam operator warning copy reconciled to 640 nm (rig-confirmed) instead of UI-SPEC's 636 nm — only the wavelength number changed, acceptance grep still holds
- [Phase 01]: Camera timeout warning copy uses plane-agnostic wording (acquire_scan has no plane number in live/single mode); substantive warning preserved verbatim from UI-SPEC.
- [Phase 01]: stack_mode_worker breaks the stack loop on a timed-out plane after acquire_scan cleans up, rather than enqueuing a nonexistent frame.
- [Phase 01]: Dead calibration worker bodies reduced to return None (restorable from git history); slot methods and signal connections kept for a scoped rebuild.
- [Phase 01]: E-stop drives both lasers off synchronously on the GUI thread (DAQ AO zero-volt + iBeam serial off) before any worker reaches its next poll point
- [Phase 01]: Wavelength labels read from live self.lasers.laser1_wavelength / self.ibeam.wavelength instances at startup — no hardcoded numbers in the GUI
- [Phase 01]: Floor scaled recorder timeout at the rig-proven legacy flat Recorder Timeout interval (15s), not just the configurable floor — Rolling/Global per-image estimate ignores trigger-wait/readout/DAQ overhead and would otherwise false-positive-time-out real acquisitions.
- [Phase 01]: Reset recorder_timeout_status at the start of arm_scan (before the hardware-present guard), not only in start_recorder — a worker that dies mid-timeout cannot then poison the next acquisition attempt that never reaches start_recorder.
- [Phase 01]: Guard start_lasers() with a conditional rather than an early return so the per-plane loop's existing first-iteration poll handles the break and the end-of-method cleanup runs unchanged
- [Phase 01]: closeEvent logs a thread-that-did-not-join warning via logging.warning rather than sig_message.emit because the UI is being torn down during shutdown
- [Phase 01]: Worker bodies (single_mode_worker, stack_mode_worker) wrapped in try/finally with the finished signal moved into finally so it fires exactly once on early return, normal completion, or exception
- [Phase 01]: Per-laser write locks are RLock (reentrant) so _toggle_laser* can call _write_laser*_power under the same lock without deadlocking; E-stop path never acquires them
- [Phase 01]: Laser amplitude edits debounced 300ms then offloaded to daemon threads; %-to-absolute scaling at HAL boundary, existing HAL clamp stays as second safety layer
- [Phase 01]: Laser spinboxes restored to 0-100 % persistent staged setpoints (laser1_power_pct/laser2_power_pct), decoupled from HAL state so staged % survives on/off + E-stop cycles
- [Phase 01]: TDD ordering for plan 09: wrote both regression tests first as a single RED commit, then implemented Task 1 and Task 2 as separate GREEN commits; Task 3 (test-addition) was satisfied by the RED commit since MVP+TDD mode requires RED before GREEN for behavior-adding tasks.
- [Phase 01]: start_lasers now reads self.lasers.error after laser1_on() and emits the same operator message the other three laser-1 call sites use, closing the last silent-no-op laser-1 call site; all four acquisition workers gained an except Exception as e: before finally that emits a cause message via sig_message and logs the traceback.
- [Phase 01]: iBeam enable_channel() called from open() and on() only — never off()/close(); carries no power value so set_power max_power clamp stays the single power-bearing path
- [Phase 01]: iBeam %SYS-E firmware rejections detected in _send_cmd and surfaced on self.error/self.error_message without raising — controller's existing poll-and-emit path unchanged
- [Phase 01]: Auto-laser checkbox states sampled on the GUI thread by _cache_auto_laser_flags() at all four worker entry points; start_lasers/stop_lasers read only cached bools — closes the AGENTS.md §11 cross-thread widget-read violation that was the highest-probability cause of G-01-5's silent 15 s camera timeout.
- [Phase 01]: acquire_scan surfaces siggen.error after create_scanner() and returns before start_recorder() is primed; stack_mode_worker breaks the loop on the first scan-task failure. src/siggen.py untouched — surfacing the state it already sets is the highest-value Mac-mockable change; replacing its bare except with typed handlers is deferred.
- [Phase lightsheet-02]: Plan 02-01: packaging seam landed — pyproject.toml with setuptools package-dir remap (src->lightsheet) + explicit packages [lightsheet, gui]; uv pip install -e . succeeded on Mac .venv (pulled PyQt5 5.15.11); lightsheet.* + gui import from /tmp; console script lightsheet = lightsheet.__main__:main installed; main/main.py deleted; bootstrap relocated into src/__main__.py:main() with nicaiu preload first; AGENTS.md launch docs updated (local-only, gitignored).
- [Phase lightsheet-02]: Plan 02-08: branch reconciliation — master renamed to main (GitHub remote default), master deleted from remote, develop branched from v2022.9 head; auto_focus inspected and left as-is (older parallel HAL split, largely superseded); v2022.9-rig-baseline tag pushed as immutable recovery point; rig stays on tag until post-phase smoke test
- [Phase lightsheet-02]: Plan 02-02: production import migration — six HAL modules + gui/controller.py repointed at lightsheet.* with zero import-time sys.path mutation; gui/ui_controller.py path-mutation line retained per plan fallback (generated bare 'import ui_controller_rc' cannot resolve from foreign CWD; regeneration with pyuic5 --from-imports flagged for a future phase).
- [Phase lightsheet-02]: Plan 02-03: uv.lock generated via 'uv lock' against the 11 declared runtime deps for both win32 + darwin required-environments; no platform-marker fallback needed (pco ships a universal wheel — 2.2.1 on darwin, 2.6.0 on win32; nidaqmx 1.6.0 universal). requirements.txt + requirements_old.txt deleted via git rm; pyproject.toml + uv.lock are the sole dependency sources. Two obsolete transitive deps (pycparser, wincertstore) dropped out of the lock — current resolved versions no longer require them and the source never imports them. Rig will receive major version jumps (numpy 1.x→2.x, nidaqmx 0.6→1.6, pco 0.1.3→2.6, scipy 1.8→1.15, matplotlib 3.5→3.10) when plan 02-09 installs this lock.
- [Phase lightsheet-02]: Plan 02-04 Task 1: kept SSH alias as literal 'lightsheet-rig' in capture script (not a variable) so the rig->local scp direction is grep-verifiable; long remote path stays a one-line variable. Reachability precheck is BatchMode + ConnectTimeout with no retry loop. Non-empty diff vs tracked baseline is the expected normal outcome.
- [Phase lightsheet-02]: Plan 02-04 Task 2: rig capture succeeded — config.rig-specific.ini written (1949 bytes, git-ignored). Calibration delta is effectively ZERO: content is byte-identical to tracked config.ini; the only difference is line endings (rig uses Windows CRLF, tracked baseline uses Unix LF). diff -u --strip-trailing-cr exits 0. All galvo amplitudes, ETL offsets, motor travel limits, COM ports, and laser wavelengths match the tracked baseline exactly.
- [Phase lightsheet-02]: Plan 02-04 Task 2: scp -O deviation — initial capture failed because OpenSSH 9+ defaults to the SFTP subsystem, where the MINGW64 /c/Users/... path does not resolve (rig login shell is Git Bash). Fix: added scp -O (legacy SCP protocol, runs via the remote login shell) to scripts/snapshot-rig-config.sh. Re-run succeeded. Committed as c650adc.
- [Phase lightsheet-02]: Plan 02-05: test suite migration — twelve test modules repointed at lightsheet.* with zero import-time sys.path mutation; conftest find_spec-gated stub injection preserved (prose updated to name lightsheet.*); ruff safe-fixes + format applied (SIM105/RUF059/UP031/F841 resolved by hand); full ANN annotation pass with no blanket suppressions; collected-test count unchanged at 86; suite green from repo root and foreign CWD.
- [Phase lightsheet-02]: Plan 02-06: logging infrastructure landed — lightsheet.logging_setup.configure() attaches RotatingFileHandler (5MBx5) + StreamHandler to root logger with mesoSPIM timestamped format, driven by [Logging] section in config.ini via cfg_read; wired into main() after nicaiu preload and before first Qt import; platform-aware default log dir (Windows: Documents/LightSheetData/logs, macOS: ./logs); idempotent handler replacement; 4 behavior tests (handler attachment, level config, idempotency, log-file write) green; full suite 67 passed 23 skipped.
- [Phase lightsheet-02]: Plan 02-06: hardcoded 5MBx5 rotation bounds rather than making Max Bytes/Backup Count configurable — keeps [Logging] config surface minimal (Level + Log Dir only); a later phase can widen it. Autouse root-logger fixture in test prevents handler leakage across tests.
- [Phase lightsheet-02]: Plan 02-07: per-module loggers + print/logging migration — logger = logging.getLogger(__name__) added to all 8 src/ HAL modules + gui/controller.py; print() in except blocks migrated to logger.exception() (8 migrations across camera/siggen/motors/etls); 9 new logger.exception() calls added to ibeam except blocks (no prints to migrate); 8 logging.* calls in controller migrated to logger.* for module-name attribution; HAL error surface (self.error/self.error_message) preserved — logging supplements it; verbose-gated except-block prints in camera un-gated (log level config controls verbosity); 13 #debugging prints + __main__ prints deferred; _load_method test helper seeded with logger so migrated logger.* calls resolve in exec'd method bodies; suite green (67 passed, 23 skipped).
- [Phase lightsheet-02]: Plan 02-09 Task 1: ruff safe-fix + format pass on production tree — 49 automated safe fixes + manual fixes for 171 non-ANN findings (E402/E722/E712/RUF012/B007/SIM105/UP031/B028/RUF059/E501); D-09a pytest gate passed (67 passed, 23 skipped) at every step; D-09c escape hatch NOT needed; safety-path diff review confirmed E-stop/laser/motor-limit/worker-join behaviorally unchanged; 337 ANN findings remain for Task 3
- [Phase lightsheet-02.1]: Phase 02.1 Plan 01: tracer slice landed — git mv src->lightsheet + gui->lightsheet/gui; pyproject.toml [tool.setuptools] declares the real tree (no package-dir, packages=[lightsheet, lightsheet.gui]); 3 production from gui.X imports repointed to from lightsheet.gui.X; editable reinstall regenerated the finder; 42 of 43 baseline ty lightsheet.* unresolved-import cleared (D-01 success); import-smoke + console-script green.
- [Phase lightsheet-02.1]: Phase 02.1 Plan 01 Rule 3 deviation: repointed stale sys.path.append('./gui') path string in lightsheet/gui/ui_controller.py to './lightsheet/gui' so the retained bare 'import ui_controller_rc' resolves after the dir move; hack structure preserved for Wave 2 (D-05 pyuic5 --from-imports regen) to remove.
- [Phase lightsheet-02.1]: Phase 02.1 Plan 01 gate-semantics finding: the plan's ty=0 and 'safety tests MUST pass' gates are phase gates (post-Wave-2), not per-plan gates. The 2 remaining ty unresolved-import (ui_controller_rc bare import + test_packaging.py:71 from gui.controller) and the 10 exec-source safety-test failures (stale ../gui/controller.py path) are the explicitly-deferred Wave-2 items (D-05 regen + test path repoints); safety logic verified intact by test_motor_limits + test_ibeam (20 tests) all passing.
- [Phase lightsheet-02.1]: Phase 02.1 Plan 02: D-05 delivered — pyuic5 --from-imports regen of lightsheet/gui/ui_controller.py emits 'from . import ui_controller_rc' at the tail, eliminating the inherited sys.path.append('./gui') path hack (the exact non-Pythonic artifact this phase exists to remove); the Wave-1 Rule 3 deviation that repointed the hack to './lightsheet/gui' is overwritten by the regen as expected.
- [Phase lightsheet-02.1]: Phase 02.1 Plan 02: 4 test files repointed — test_packaging.py imports lightsheet.gui + lightsheet.gui.controller (gui is now a subpackage, not a top-level package); 3 path-string test files (test_controller_behavior, test_laser_controls, test_controller_laser_path_rig) repointed from '..', 'gui', 'controller.py' to '..', 'lightsheet', 'gui', 'controller.py' (two segments now). Fixes the 11 deferred pytest failures from Wave 1 (1 test_packaging + 10 exec-source safety tests). test/ stays top-level (D-08 respected).
- [Phase lightsheet-06]: Phase 06 Plan 05: All three D-06 test-infrastructure workaround reverts landed and verified stable — no step segfaulted, so none was deferred to Phase 7. The make_controller fixture's sip.delete(controller) teardown was replaced by _stop_worker_threads() (mirrors closeEvent's quit()+wait() shutdown shape, 2000 ms bound); the pytest_runtest_teardown hook in conftest.py was removed; the -p no:xdist single-process flag in scripts/coverage.sh was removed (xdist parallelism restored, addopts override changed to '--strict-markers -n auto' so the override does not silently drop -n auto). Each step verified with 3 consecutive green runs (pytest -q for Tasks 1-2, bash scripts/coverage.sh for Task 3) per the D-06 non-deterministic-segfault stability requirement. Phase 6 is complete — RFR-03 and all six ROADMAP Phase 6 success criteria satisfied.
- [Phase lightsheet-06]: Phase 06 code review gate (06-REVIEW.md, STANDARD depth, 15 files) found a Critical safety bug: LiveWorker.__init__ (workers.py:318-329) never set self._save_description / self._save_stitch_blend that _AcquireScanMixin.acquire_scan reads (lines 192, 289). The first live-mode frame raised AttributeError inside the try block, so the post-loop cleanup (stop_lasers, camera.disarm, update_etls) was skipped — leaving Class IIIB lasers energized when live mode aborted. The existing LiveWorker tests missed it because they exit the loop before acquire_scan() runs (live_mode_started=False or estop_event set). Fixed inline by setting self._save_description = "" and self._save_stitch_blend = False in LiveWorker.__init__ (live mode never saves, so empty/False defaults match the pre-migration cross-thread UI read returning ""/False for a non-saving mode). Regression test test_live_mode_worker_acquire_scan_does_not_skip_cleanup added — runs one acquire_scan() iteration in the live loop and asserts stop_lasers + camera.disarm still run; verified to fail without the fix and pass with it. All 8 safety invariants confirmed preserved. 4 advisory Info findings (stale docstrings/comments, 2 pre-existing controller.py issues) left for follow-up. Suite 882 passed, 34 skipped after fix.
- [Phase lightsheet-06]: Phase 06 verification gate (06-VERIFICATION.md) verdict PASSED — all 8 goal components verified with file:line evidence: (1) QThread+moveToThread model — 4 worker QObjects in workers.py, 4 QThread spawn sites + 4 moveToThread calls in controller.py, 0 threading.Thread(target=self._acq remain; (2) quit()+wait(5000) shutdown — uniform closeEvent loop, 0 terminate() in production, 0 time.sleep in controller; (3) signal-lambda cycle broken — wire_collaborators() uses bare bound-method connections, 0 functools.partial, 0 lambda:self._mc/self._acq in __init__ (2 documented timer lambdas out of scope); (4) segfault eliminated/xdist re-enabled — sip.delete teardown → _stop_worker_threads, pytest_runtest_teardown hook removed, -p no:xdist removed; (5) safety invariants preserved — E-stop lock-free on GUI thread, 0 requestInterruption, workers only poll estop_event (13 sites), motor ValueError+beep+abort preserved, 0 self._shell.ui. in workers.py, frozen DeviceBundle intact; (6) golden masters byte-identical (git diff --exit-code 0 on all 3 fixtures); (7) suite 882 passed 34 skipped; (8) review Critical finding resolved inline.

> **Recovery note (2026-08-25):** STATE.md and ROADMAP.md were accidentally deleted and reconstructed from conversation memory. The detailed per-phase decision entries for Phases 03–05.1 (originally ~90 lines between this section and Roadmap Evolution) were not recoverable verbatim — the entries above are the subset preserved in memory. The authoritative per-phase decision detail now lives in each phase's `*-SUMMARY.md` and `PROJECT.md` Key Decisions table; re-derive from there if a specific entry is needed.

- [Phase 7]: Plan 07-01: PySide6>=6.8 broad pin (resolved to 6.11.2) — empirically verified by uv lock resolving both darwin universal2 + win_amd64 wheels; pin broad enough for bugfixes, narrow enough to avoid untested major bumps
- [Phase 7]: Plan 07-01: Did NOT run uv sync after uv lock — dep-swap-only foundation; production code still imports PyQt5 (ported in 07-03), syncing now would break the venv; ROADMAP accepts red period 07-02..07-05; lockfile is source of truth, venv catches up in 07-02+
- [Phase 7]: Plan 07-01: Task 2 (mint MIG-05..MIG-08) already satisfied during planning — REQUIREMENTS.md definitions + traceability + phase load + coverage count and ROADMAP.md SC5/SC6/SC7 + research flag all present on disk; all acceptance grep criteria pass; no edits required
- [Phase 7]: uv sync run at 07-02 start — venv catches up to lockfile here (PySide6 6.11.2 installed, PyQt5/pyqtgraph uninstalled); accepted red period 07-02..07-05 begins (4 production files now import PySide6, 7 hand-written files + test suite still import PyQt5, ported in 07-03/07-04)
- [Phase 7]: Native Qt6 ImageView(QGraphicsView) with fixed 0-2000 levels window replaces plotting-library ImageView (D-05); pyside6-uic/pyside6-rcc regen of ui_controller.py/ui_properties.py/ui_controller_rc.py auto-fixes PyQt5→PySide6 imports + scopes enums + switches to relative resource import (kills the Phase 02.1 sys.path.append hack)
- [Phase 7]: Rule 1 auto-fix: PySide6 6.11.2 rejects setRenderHints(0) (requires QPainter.RenderHint enum, not int); fixed to QPainter.RenderHint(0). SC2 render smoke test passes (1 passed in 1.19s).
- [Phase 7]: QShortcut moved from QtWidgets to QtGui in Qt6 — fixed during import smoke test (ImportError); not called out in PATTERNS/RESEARCH docs
- [Phase 7]: Three docstring-only pyqtSignal references in plain-Python collaborator modules (hardware_manager, acquisition_coordinator, motor_controller) updated to Signal to satisfy the MIG-01 production gate (zero pyqtSignal across lightsheet/)
- [Phase 7]: Updated stale PyQt5 token references in test_frame_saver_controller.py docstring/comments (4 sites) in addition to the import + importorskip lines — Rule 2 correctness cleanup so future readers see consistent PySide6 references.
- [Phase 7]: Verified runtime behavior of the 10 ported test files (181 tests pass under PySide6, offscreen, single-process) — not just the static grep gates. Confirms the patch-target rename (QDialog.exec_ -> exec) did not regress the safety-adjacent closeEvent and config-schema rejection-tier tests.
- [Phase 7]: PySide6 QApplication singleton: PySide6 raises RuntimeError on second QApplication construction (PyQt5 was idempotent). Fixed test-side with _IdempotentQApplication subclass whose __new__ returns existing instance; production main() is correct (runs once at entry point).
- [Phase 7]: pyside6-rcc generated file has no version-gate branch (unlike pyqt5-rcc) — replaced obsolete rcc_version/qt_resource_struct_v2 test with Qt6 format-version (0x03) assertion.
- [Phase 7]: D-02 exception resolved at 07-05: golden master re-verified green (883 passed, 34 skipped, 0 failed, 3 golden_acquisition scenarios byte-identical). Zero PyQt5 references in entire codebase.
- [Phase 7]: D-06 resolved: no shutdown segfault under PySide6/Qt6 (exit code 0, clean shutdown — PyQt5 sipQApplication destructor segfault is gone)
- [Phase 7]: LaserReadbackWorker uses Qt.DirectConnection for fire-and-forget sig_finished→thread.quit (thread self-quits without main-thread event loop)
- [Phase 7]: 7 panels (not 5) for .ui split — user expanded scope to include Scan + Calibration panels
- [Phase 7]: E-stop toolbar declared in ui_shell.ui (not constructed programmatically) — E-stop is a true UI element; lock-free kill contract preserved
- [Phase 7]: Scrollbar AlwaysOff on QGraphicsView prevents resize->fitInView recursion without a re-entrancy guard
- [Phase 7]: Drop setMaximumSize where max==min (pinning); keep setMinimumSize for the readability/touch-target floor
- [Phase 7]: Defer only the E-stop post-kill refresh via QTimer.singleShot(0,...); the kill loop (estop_event.set() + laser.off()) stays synchronous and lock-free on the GUI thread (AGENTS.md §2)
- [Phase 7]: Arm/Reset button label reflects the NEXT action available (Clear E-stop / Arm Lasers / Arm/Reset), not the current state — makes the two-press sequence discoverable
- [Phase 7]: View-menu hide uses minimumWidth=0 + maximumWidth=0 + setSizes([0, total]) because the panes have non-zero minimum widths (320/360 px) that block the splitter from reaching 0
- [Phase 7]: LevelsBar is a stock-Qt6 QWidget (paintEvent + mouse events) — no pyqtgraph
- [Phase 7]: Stack boundary-set boolean migrated from checkBox.isChecked() to shell flags stack_first_plane_set/stack_last_plane_set
- [Phase 7]: Used QSplitter for resizable message log with childrenCollapsible=False (handle-drag-to-zero blocked; hiding via View-menu setSizes min/max)
- [Phase 7]: Stack plane spinbox values in display unit; shell flags (stack_starting_plane/ending_plane) in μm via _display_to_um helper so worker + motor HAL receive μm regardless of display unit
- [Phase 7]: Mode badge uses QDarkStyle default text + bold weight (no accent color) — informational, not a safety indicator
- [Phase 7]: Pruned dead désuet widgets (Start Camera/ETL Calibration buttons, Reset Settings button) after grep audit confirmed no slot wiring; added tooltips to every numeric input + toggle across all 7 panels; renamed Help menu action to actionGuidePdf and made open_help cross-platform
- [Phase 7]: Queue execution loop uses a non-blocking QEventLoop (quit connected to worker finished) on the GUI thread instead of threading.Event.wait so the GUI stays responsive and the E-stop kill path can abort the queue synchronously
- [Phase lightsheet-08]: Phase 08-01: liom-toolkit[io]>=1.1 added as runtime dep (>=1.1 lower bound avoids v1.0 heavy core; only no-op [io] extra requested). zarr 3.3.0/ome-zarr 0.18.0/dask 2026.8.0 arrive as transitive deps. scikit-image 0.26.0 enters via ome-zarr/zarr/dask ecosystem, not via a liom-toolkit extra.
- [Phase lightsheet-08]: Phase 08-01: Wave 0 RED scaffolds use xfail(strict=False) so the suite stays GREEN while tests are collected (Nyquist contract). Module-level ImportError guards set not-yet-implemented classes to None; xfail body asserts non-None, absorbing the AssertionError.
- [Phase lightsheet-08]: Declared binning_x/binning_y as class-level annotations on ICameraCore (not @property+@abstractmethod) — the real Camera sets them as plain instance attributes, which does not satisfy an abstract property descriptor at instantiation time (same form as xsize/ysize).
- [Phase lightsheet-08]: Camera.__init__ sets binning_x=1/binning_y=1 defaults (Pitfall 3 guard) so the attrs exist even if open() fails — the ZarrSaver finalize path reads them for the XY voxel-size source. arm() re-reads sdk.get_binning() (operator may change binning between open and arm).
- [Phase lightsheet-08]: Used pydantic Literal[hdf5/zarr/both/tiff] for image_file_format (rejects unknown values at startup via collect-all gate); before-validator lowercases for case-insensitive acceptance; both strict + overlay tiers mirror the field
- [Phase lightsheet-08]: Controller save_format parse widened to tiff/hdf5/zarr/both (else defaults to hdf5 so rig's current HDF5 config stays valid); default save dir changed from ~/Documents/LightSheetData to ~/Desktop/LightSheetData (rig's actual acquisitions folder)
- [Phase lightsheet-08]: Save-panel format radio group: second exclusive QButtonGroup on the controller for the 3 format radios; @Slot(QAbstractButton) slot maps clicked radio to lowercase constant; startup reflection of config-driven default (tiff/legacy -> HDF5 radio); disable-on-acquisition extended updateUi_modes_buttons to toggle the 7 radios.
- [Phase lightsheet-08]: ZarrSaver uses zarr v3 Group.create_array (not create_dataset) for /acquisition/motor 1D datasets — zarr 3.3.0 renamed create_dataset to create_array
- [Phase lightsheet-08]: ZarrSaver.write_plane prepends a channel axis (frame[np.newaxis, :, :]) for the 4D writer[:, z, :, :] assignment — the writer indexes the underlying 4D (c,z,y,x) array and the value must be 3D
- [Phase lightsheet-08]: FrameSaverWorker.start_saving branches on save_format (hdf5/zarr/both); both serializes (zarr then hdf5); try/finally + sig_finished.emit() preserved verbatim (single emit gate); FrameSaver.reinit re-reads save_format + resets ZarrSaver for per-acquisition format changes
- [Phase lightsheet-08]: HDF5 SAV-03: added _write_acquisition_metadata helper (motor + scan-param + camera root attrs from live IMotor/SigGen/ICamera instances — never re-parses config.ini); schema mirrors 08-05 Zarr /acquisition group; 2 RED stubs turned GREEN (test_motor_and_scan_params_in_hdf5_metadata + test_no_config_reparse)
- [Phase lightsheet-08]: 08-07: past-acquisitions browser widgets added programmatically in AcquisitionTableManager (not ui_acquisition_panel.ui) — the Acquisition Queue group box lives in ui_stack_panel.ui with an empty layout populated programmatically by the manager; the plan's ui_acquisition_panel.ui reference is a file-path mismatch (Rule 3 deviation).
- [Phase lightsheet-08]: 08-07: zarr pyramid multiplier uses the geometric sum from the live base_res target-validity filter (count targets in (10,25,50,100) >= max(base_res)), NOT hardcoded 4 levels — the estimate tracks the real on-disk pyramid.
- [Phase lightsheet-08]: 08-07: OME-Zarr parser reads omero from root.attrs["ome"]["omero"]["channels"] (the real writer's nested layout) with a top-level omero fallback; #planes = root["0"].shape[1] (L0 z-dim of the 4D array).
- [Phase 08.1]: FIELD_SPECS contains 23 entries (not 22) — UI-SPEC table has 23 rows; plan prose off-by-one
- [Phase 08.1]: BreezeStyleSheets vendored in-tree (not submodule) under lightsheet/gui/_vendor/breezestylesheets/; compiled breeze_pyside6.py committed (mirrors ui_*_rc.py); set_app_stylesheet refactored to module-level for testability; Unknown color scheme falls back to dark
- [Phase 08.1]: LevelsBar redesigned to 5-handle two-slider-set (RANGE + WINDOW + central handle) with data-following range; levels_min/levels_max kept as window aliases
- [Phase 08.1]: set_data_range no-ops on unchanged range so per-frame calls do not reset operator RANGE adjustments
- [Phase 08.1]: Slider sync deferred for stack first/last plane fields: pre-existing µm-units convention conflicts with FieldSpec mm range; slider widgets present but not wired.
- [Phase 08.1]: FieldSpec soft min/max overridden by pre-existing runtime mechanisms for 6 fields (4 dynamically-coupled offsets + 2 stack widened-range); suffix/decimals/step still authoritative.
- [Phase 08.1]: Planned/Past toggle's 'Planned' radio switches the left-rail to the Stack page (index 2) instead of toggling a table in-place
- [Phase 08.1]: E-stop toolbar floatable=False enforced both in .ui and programmatically in controller (belt-and-suspenders safety guard)
- [Phase 08.1]: Flaky resize tests reworked to assert remediation targets (cap gone, pin gone) instead of exact pixel values that Qt's layout engine can override under xdist
- [Phase 9]: select_laser(idx) de-energizes-then-energizes with per-laser RLocks never held simultaneously — deadlock-free, E-stop lock-free contract preserved
- [Phase 9]: SingleWorker multi-channel branch uses select_laser per channel (not start_lasers) and stop_lasers at end; reconstructed_frame kept as alias to last channel for back-compat
- [Phase 9]: StackWorker multi-channel branch does NOT call start_lasers at the top (energizes both simultaneously, violating MCA-02); uses select_laser per plane per channel instead
- [Phase 9]: D-04 continuous-mode guard suppresses _auto_laser2 temporarily for start_lasers then restores it (reuses start_lasers verbatim, no per-frame L1<->L2 alternation)
- [Phase 9]: Multi-channel single-mode Save button writes two wavelength-suffixed HDF5 files (one per channel); wavelengths read from live ILaser instances, never hardcoded
- [Phase 9]: Channel-tag branching lives inside the existing single frame_saver_worker consume loop (isinstance tuple check) — no queue split, close-ordering contract preserved
- [Phase 9]: both_save_worker Zarr write_plane stays on channel 0 in 09-03; 09-04 extends write_plane signature to accept channel_idx
- [Phase 9]: MULTI-CH pill is a text suffix on the existing badge (no separate widget, no green accent); channel-radio placed above ImageView viewport; radio visibility driven through _cache_auto_laser_flags single sync path; LevelsBar window reset sets window_max before window_min to avoid setter clamp-down; channel-radio hidden (not disabled) for single-channel back-compat
- [Phase lightsheet-09]: Lifted _wavelength_to_hex to shared lightsheet/wavelength_color.py module (display + metadata single source of truth)
- [Phase lightsheet-09]: ImageView tint modulation computed in uint16 before uint8 cast to avoid (frame_scaled * 255) // 255 overflow
- [Phase lightsheet-09]: Fixed-height (32px) container wraps ChannelRadio so show/hide does not reflow ImageView or LevelsBar
- [Phase lightsheet-09]: Branched StackWorker.run stitch set_files call on _multi_channel (multi-channel: number_of_files=number_of_planes, number_of_datasets=1; single-channel: existing convention unchanged) — closes the multi-channel stack-save deadlock in stitch mode
- [Phase lightsheet-09]: MockCamera.simulate_timing (default False) delays monitor_recorder by exposure_time when True; enabled only in _build_demo_bundle so demo UAT shows realistic per-plane timing without slowing tests

### Pending Todos

[From .planning/todos/pending/ — ideas captured during sessions]

None yet.

### Blockers/Concerns

None yet.

### Roadmap Evolution

- Phase 02.1 inserted after Phase 2: Pythonic Package Restructure — unify the flat module layout spread across src/ and gui/ into a single Pythonic package before the HAL rework in Phase 3 (URGENT)
- Phase 05.1 inserted after Phase 5: Testing suite redesign with 80% per-module coverage gates and unified Mac/rig test architecture (URGENT)
- Phase 10 added: Adaptive Exposure & Laser Power Control — closed-loop per-plane intensity feedback (exposure and/or laser power) compensating for the signal drop from brainstem to brain centre in cleared iDISCO+ whole-brain acquisitions; depends on Phase 9, independent of Phase 11
- Phase 11 added: Camera Focus Compensation for Brain Lensing — move the camera along the acquisition axis during a stack to refocus against the refractive-index lensing of the dibenzyl-ether-cleared brain across the brainstem-to-olfactory-bulb span; depends on Phase 9, independent of Phase 10
- Milestone v2022.9 scope extended from Phases 1-9 to Phases 1-11 to cover these post-migration acquisition enhancements
- Phase 07.1 inserted after Phase 7: Audit and remake GUI layout for responsive resizing across screen sizes (URGENT)
- Phase 08.1 inserted after Phase 8: UI Overhaul — Responsive Resize, Scrollbox Redesign, and Phase 8 UAT Gap Fixes (URGENT)

## Deferred Items

Items acknowledged and carried forward (v2, see REQUIREMENTS.md):

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| Python | 3.12 → 3.14 (gated on `pco` lifting `<3.13` cap, ~2027) | v2 | Roadmap creation |
| Saving | Full OME-Zarr migration (replace HDF5 entirely) | v2 | Roadmap creation |
| Hardware | Real-hardware conformance run on LIOMW18 | v2 | Roadmap creation |
| Hardware | Galvo/ETL channel-reversal flip (rig verification) | v2 | Roadmap creation |
| Hardware | Toptica iBeam hardware confirmation | v2 | Roadmap creation |

## Session Continuity

Last session: 2026-08-30T23:43:24.958Z
Stopped at: Phase 10 context gathered
Resume file: .planning/phases/lightsheet-10-adaptive-exposure-laser-power-control/10-CONTEXT.md
Current Plan: Not started
Total Plans in Phase: 8
Current Phase: 10 — Adaptive Exposure & Laser Power Control

## Graduation Backlog

```yaml

- cluster_id: "cc6a9da3118c5b71fdf64d2f23085af3b71256af2ba65fc0d44253a797be438e"
  status: "dismissed"
  cluster_title: "Orchestrator/executor crashed mid-phase"
```

## Quick Tasks Completed

| Slug | Date | Description | Commit |
|------|------|-------------|--------|
| 260826-hwp | 2026-08-26 | Rename laser 2 from 640 nm (emission) to 647 nm (capture wavelength) for consistency with laser 1 (555 nm capture) | d35057e |
| 260829-j72 | 2026-08-29 | Align pytest/xdist config with liom-toolkit (cap workers at 6, --dist=load, --max-worker-restart=0, -ra, minversion) | 90dfe34 |
| 260829-u6o | 2026-08-29 | Rewrite AGENTS.md to be current after phase 8.1 (PySide6/Qt6, Python 3.12, shell/coordinators/panels/widgets layout, power meter, Zarr, layout convention); track AGENTS.md, move personal SSH details to gitignored AGENTS.local.md | f530f24 |
| 260829-rsx | 2026-08-29 | Analyse testing suite for problems, optimize for speed, reduce test count (1207→1174, slowest test 10.75s→1.6s, fix stale PyQt5 refs + libpyside warning + 2s thread-wait timeout, delete 9 cross-file duplicates, merge 24 symmetric slot tests) | 94a7c16 |
| 260830-09m | 2026-08-30 | Fix all 08.1-UI-REVIEW.md findings (3 blockers + 10 warnings): E-stop stays red in DISARMED, theme persistence+hint, rail icons/tooltips, QActionGroup, toolbar spacing; stack panel mm display / µm internal units reconciliation (safety-critical: fixes 1000× motor over-travel from pass-through _display_to_um); laser FAULT text; past-acquisitions copy; FieldSpec tooltips; levels central handle neutral gray; scan checkbox max-size pins removed | 7642f30 db2965f eba7233 |
| 260830-ui2 | 2026-08-30 | Post-review UI fixes: contrast bar handles pinned to edge (coordinate mapping used RANGE set as span — split to fixed data bounds), range drag reset by per-frame set_data_range (added _range_user_owned), window handles jumping mid-drag (deferred clamp to release), hit-test grabbing wrong row (tightened y-radius), live readout; image viewer border removed + wheel-zoom + drag-pan + preserve transform across contrast changes + symmetric scene-rect padding for pan-beyond-edges; default levels window 0-2000→0-20000; rail icon centering (custom paintEvent, HiDPI-safe), uniform buttons, tighter rail; layout polish (panel margins zeroed for message-log alignment, symmetric splitter margins, centered contrast bar) | 2e50756 |
