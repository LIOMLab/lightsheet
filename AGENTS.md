# AGENTS.md — Instructions for AI agents working in this repo

This is an instruction set, not a reference dump. Read it before making changes.
The rules below exist because hardware damage and operator injury are real
risks on this project, not just code-quality concerns.

For deeper reference (architecture, full file map, concerns catalog) see the
codebase map (ARCHITECTURE.md, CONCERNS.md, CONVENTIONS.md) in the project's
planning docs. This file is the rules; that is the map.

**Reading PDFs:** the `markitdown` MCP server (`convert_to_markdown` tool,
accepts a `file:`/`http:`/`https:` URI) is available for converting PDF
manuals/datasheets (e.g. PCO camera, iBeam Smart, Optotune ETL, Zaber, NI-DAQ)
to markdown so you can read them. Use it when a task references a PDF doc
instead of skipping it or guessing at its contents.

## 1. What this project is

**Lightsheet Microscope Controller** — a PySide6/Qt6 desktop app that drives a
custom light-sheet fluorescence microscope: PCO camera, NI-DAQmx galvo/ETL scan
generation + laser power control, Zaber motor stages, Optotune tunable lenses,
and a Toptica iBeam Smart laser. Single-machine Windows app run by the operator
during live experiments. Inherited codebase, originally loosely based on
mesoSPIM-control, now substantially diverged.

Core value: the operator reliably acquires light-sheet image stacks with safe
GUI control of all hardware — including lasers — and the codebase can be
developed and tested on macOS without the physical microscope.

## 2. Safety rules (read first, always)

These are physical-safety constraints, not style preferences:

- **Motor limits**: Never disable or relax Zaber travel-limit enforcement. A
  stage driven past mechanical limits damages hardware. Reject-and-beep on
  over-travel must stay intact (`ZaberMotor.move_absolute_position` /
  `move_relative_position` in `lightsheet/hal/real/motors.py` raise `ValueError`
  BEFORE any serial command). `stack_mode_worker` catches the `ValueError` and
  aborts the stack with a beep + message.
- **Laser power clamping (two-layer)**: `ILaser.set_power(mw)` clamps mW to
  `[0, max_power]` at the interface layer; each backend clamps again in its
  native unit (`DAQLaser._write_volts` clamps V; inner `IBeam.set_power` clamps
  µW). `max_power` is loaded from `config.ini` (`Max Power` key) — treat that
  key as safety-critical. Do not remove a clamp to "fix" a power issue —
  escalate instead.
- **E-stop**: The E-stop (toolbar button / F12) must synchronously drive every
  laser off on the GUI thread (`updateUi_estop_pressed` in
  `lightsheet/gui/shell/controller.py`: `estop_event.set()` →
  `for laser in self.lasers: laser.off()` → poll `laser.error` and warn if an
  `off()` failed) and be polled in **all** acquisition worker loops
  (`preview`/`live`/`single`/`stack`). `off()` MUST return `None` immediately
  with no thread/queue offload (the `ILaser.off` contract in
  `lightsheet/hal/interfaces.py`). Do not move laser-off logic off the GUI
  thread or behind a queue. The E-stop path is intentionally lock-free — a
  stuck toggle thread must never delay the kill path. A queued/offloaded toggle
  or amplitude write must check `estop_event` before energizing and re-check
  before the HAL write — a Class IIIB laser must not be re-energized past the
  kill path.
- **Config-schema rejection tier (startup gate):** `lightsheet/config_schema.py`
  (pydantic-settings, two tiers: 8 strict `extra='forbid'` + 8 overlay
  `extra='ignore'`) runs in `__main__.py` on BOTH the demo and rig paths
  before the controller is constructed. Safety-critical keys are **rejected**,
  not clamped, at this tier: `[iBeam] Max Power` > 150000 and `[Motors]`
  `* Limit High` beyond 41.0 / 18.8 / 35.0 mm abort startup with a modal
  dialog listing every error in one pass (`ConfigValidator.validate_or_abort`).
  The two-layer runtime clamp in §10 is the defense during a session; the
  schema is the defense at startup. Do not relax these validators to "fix" a
  config that won't load — the value is out of range for a physical-safety
  reason; escalate.
- **Frozen `DeviceBundle` is a safety property:** the composition root hands
  the controller a single `@dataclass(frozen=True)` `DeviceBundle` whose
  `lasers` field is a `tuple`. The E-stop kill path iterates `self.lasers`
  (derived from the bundle) — if a caller could re-bind a laser handle after
  construction, the kill path would miss the live handle and fail to
  de-energize a Class IIIB laser. `frozen=True` turns a swap into a
  `FrozenInstanceError` at the swap site instead of a silent kill-path miss.
  Do not make the bundle mutable, do not store a `list` of lasers on it, and
  do not reassign `self.lasers` from anywhere but `hardware_init`
  (`self.lasers = list(self._bundle.lasers)` once, at startup).
- **Do not send power-setting commands to the rig unless explicitly asked.**
  Read-only status queries are fine for verification; changing laser emission
  state or motor position on the real rig is an operator action, not an agent
  action. If a task seems to require it, stop and ask.

## 3. Two execution environments — know which one you are in

| | Dev machine (no hardware) | Rig (microscope PC) |
|---|---|---|
| OS | macOS / Linux | Windows |
| Python | 3.12 (uv `.venv` from `uv.lock`) | 3.12 (uv `.venv` from `uv.lock`) |
| Hardware SDKs | NOT installed — stubbed by `test/conftest.py` | Real `nidaqmx`, `pco`, `pyserial` |
| What runs | Pure-logic + mock-serial tests, static checks, `--demo` GUI | Full app, integration tests, real hardware |
| Qt | PySide6/Qt6 | PySide6/Qt6 |

**Default assumption: you are on a dev machine without the hardware SDKs.**
Everything you write must be mock-testable there first. Only reach for the rig
(next section) when a task genuinely needs real hardware.

**Demo mode:** `--demo` CLI flag or `LIGHTSHEET_DEMO=1` env var makes
`main()` build a `DeviceBundle` from `Mock*` HAL instances via
`_build_demo_bundle()` (in `lightsheet/__main__.py`) instead of calling
`DeviceRegistry.resolve()` — the registry is not even imported on the demo
path. On a dev machine this is how the GUI launches with no hardware.
`MockLaser.off()` is synchronous and `set_power` clamps to `max_power` so the
E-stop and safety paths do not atrophy under demo — preserve that.

The PySide6/Qt6 + Python 3.12 migration is COMPLETE (done in the Qt6 port and
its follow-up). The current floor is Python 3.12; the next interpreter move
(3.13+) is still blocked by the `pco` package (`<3.13` cap). Do not "upgrade"
the interpreter or Qt bindings as part of an unrelated task — that is a
dedicated migration, not a drive-by fix.

## 4. Connecting to the rig

The microscope PC ("the rig") is the Windows machine with the real hardware
SDKs attached. Use it to verify things or run tests that cannot run on a dev
machine without hardware (real-hardware integration checks, protocol probes,
deployment smoke tests).

**Personal rig connection details** (SSH alias, host, jump host, user, rig
repo path) live in `AGENTS.local.md` — a gitignored, local-only file that
Devin Next auto-loads alongside this one. If you do not have that file, you do
not have rig access: develop on the mock path (`--demo` / `LIGHTSHEET_DEMO=1`)
per §3.

`uv` must be installed on the rig (same `uv.lock` as the dev machine). Sync
before running anything so the rig's `.venv` matches the locked dependencies.

Example rig session (read-only probe pattern — fill in your own SSH alias and
rig repo path from `AGENTS.local.md`):
```bash
# On the rig (over SSH, however you connect):
uv sync
uv run pytest test/ -q                       # mock path (conftest stubs the SDKs)
LIGHTSHEET_HW=1 uv run pytest test/ -q       # real-path conformance + rig-only tests
```

Rules for rig use:
- Prefer read-only / query commands. Confirm before running anything that
  moves a motor, changes laser state, or starts an acquisition.
- The rig is a shared physical instrument — an operator may be using it. If a
  command could interfere with an experiment, ask first.
- Pull the repo state you need with `git` on the rig; do not push from the rig
  unless asked.
- If the rig is unreachable (network, jump host down), fall back to mock-only
  development and tell the user — do not retry in a loop.

## 5. Running tests on a dev machine

Sync dependencies first (creates/updates the uv `.venv` from `uv.lock`,
including the `dev` group with pytest/ruff/ty):
```bash
uv sync
```

Then run the suite:
```bash
uv run pytest test/ -q
```

- `test/conftest.py` auto-stubs `nidaqmx`, `pco`, and (as fallback) `serial`
  into `sys.modules` before collection, gated by `find_spec` + a smoke check
  (`nidaqmx.Task()` / `pco.Camera()` must construct). Real SDKs are used on the
  rig (`LIGHTSHEET_HW=1`); stubs are used on a dev machine. The nidaqmx stub exposes
  `errors.Error` / `errors.DaqError` / `constants.*` (as `enum.IntEnum`) so
  `from nidaqmx.constants import ...` at module load succeeds, and the stub
  `Task.__init__` raises `Error` so the typed-except path in
  `DAQLaser._write_volts` fires naturally — no extra mocking required. Do not
  break this gating.
- pytest config lives in `pyproject.toml` under `[tool.pytest.ini_options]`
  (`testpaths = ["test"]`, `python_files = ["test_*.py"]`, `minversion = "9.1"`,
  and `addopts` as a list: `-ra --strict-markers -n auto --maxprocesses=6
  --dist=load --max-worker-restart=0` for parallel execution via pytest-xdist).
  `--maxprocesses=6` caps workers to bound PySide6 worker memory on high-core
  machines; `--max-worker-restart=0` disables silent worker-restart-on-crash so
  a segfaulted worker's tests surface as failures instead of being hidden
  (lightsheet has a known shutdown segfault — see the segfault note below);
  `--dist=load` is the explicit xdist distribution mode (`xdist_group` still
  works under any dist mode). Only `test/test_*.py` files are collected.
- **Marker + parametrize dual contract** (rig/mock/slow markers registered in
  `pyproject.toml` under `[tool.pytest.ini_options].markers`, enforced by
  `--strict-markers` so a typo'd marker fails at collection). Two complementary
  mechanisms select what runs in which environment — they are NOT redundant:
  - **`@pytest.mark.rig`** selects FILE-level rig-only tests. The
    `pytest_collection_modifyitems` hook in `test/conftest.py` reads
    `os.environ.get("LIGHTSHEET_HW", "0")` at *collection time* (after every
    test module is imported) and adds a `skip` marker to every item with
    `"rig"` in its keywords when the var is unset (dev machine). The hook exists
    because a bare `@pytest.mark.skipif(os.environ["LIGHTSHEET_HW"] == "1",
    ...)` raises `KeyError` at *import time* when the var is unset — the `[]`
    indexer does not default. On the rig (`LIGHTSHEET_HW=1`) the hook returns
    immediately and every rig test runs. xdist-compatible (env vars are
    inherited per worker).
  - **`skipif(not _has_hardware)` on a `pytest.param` id** selects param
    CASES within a parametrized conformance test (the `[real, mock]` pattern
    above). The module-level `_has_hardware` bool in `test/conftest.py` (set
    from the same env var) gates the `real` id; the `mock` id always runs.
  - The three registered markers are: `rig` (requires real hardware, set
    `LIGHTSHEET_HW=1`), `mock` (mock-only path, default on a dev machine), `slow`
    (auto-deselected from fast iteration by convention).
- **`test/_helpers/` import convention** (resolves via `pythonpath = ["test"]`
  in `pyproject.toml`). The real-construction fixture lives in one importable
  package — import it, do not re-inline:
  - `from _helpers.controller_fixture import make_controller` — the shared
    fixture that constructs a real `Controller_MainWindow` on a dev machine (via
    `QT_QPA_PLATFORM=offscreen` + the conftest SDK stubs), wires all four
    collaborators
    (`FrameSaverController` / `HardwareManager` / `AcquisitionCoordinator`
    / `MotorController`) in the same two-phase order `main()` uses, and calls
    `hardware_init` so `self.lasers` / `self.camera` / `self.siggen` /
    `self.motors` / `self.etls` and the display/status timers are populated.
    Each test calls the REAL method on the real controller and asserts on
    real attributes / Qt widget state / signals. The fixture imports
    `Controller_MainWindow` from `lightsheet.gui.shell.controller`. The
    fixture's `request.addfinalizer` teardown runs `_stop_worker_threads`
    (mirroring `closeEvent`'s `quit()`+`wait()` shutdown so no worker QThread
    outlives a test) and stops the `QMessageBox` patch; the controller is
    registered with `qtbot.addWidget` for Qt-side cleanup. `sip.delete` is
    no longer used — the signal-lambda cycle is broken at the connection
    layer (see the segfault note below). This is a BEHAVIOR test (runs the
    real method body, asserts on runtime postconditions) — NOT the
    static-source/grep test this section forbids.
  - **Why real construction, not exec-against-Mock:** the previous
    `_load_method` exec pattern (extract the method source, `exec` it in a
    controlled namespace, call against a `Mock` stand-in `self`) produced 0%
    branch coverage — the exec'd code object's arcs do not map back to the
    source file — and skipped the real `__init__` signal/attribute wiring
    entirely. Real construction produces genuine branch (arc) coverage and
    exercises the real signal/slot wiring, Qt widget state, and collaborator
    interactions. The exec pattern is gone from the test suite; the only
    remaining `_load_method` use is in `test/golden/_record.py` (the
    golden-master recording tool, which intentionally runs worker methods
    against a Mock stand-in to capture the `sig_message`/`sig_progress`
    emission sequence WITHOUT Qt widget side effects — converting it to real
    construction would change the captured sequence and break the
    characterization contract).
  - **Segfault note (PySide6/shiboken):** historically, 53
    `lambda: self._mc.<slot>()` signal connections in
    `Controller_MainWindow.__init__` each created a reference cycle
    (controller → child widget → signal → lambda → closure cell →
    controller). The Python wrapper never reached refcount zero, so the C++
    `QMainWindow` destructor was deferred to cyclic GC; in the test suite
    (constructs ~50 controllers per process) the deferred destructor fired
    mid-construction of the next controller and segfaulted. **This cycle is
    now broken at the connection layer:** `wire_collaborators()` (added in
    the Phase 6 threading migration) uses bare bound-method connections,
    which the signal system decomposes into weakref(`__self__`) +
    strong(`__func__`) — the signal system holds zero strong refs to the
    controller after disconnect, so the wrapper reaches refcount zero
    naturally. The per-test `pytest_runtest_teardown` hook that `sip.delete`d
    every top-level QWidget, and the `make_controller` fixture's `sip.delete`
    teardown, are both removed (replaced by `_stop_worker_threads`, mirroring
    `closeEvent`'s `quit()`+`wait()` shutdown) — the cycle break makes them
    unnecessary. `conftest.py` still calls `gc.disable()` for the whole
    session (line 312) as a guard against Qt widget destructor segfaults
    during the run. `scripts/coverage.sh` runs xdist-parallel (`-n auto
    --maxprocesses=6` in its `-o addopts` override) — the single-process
    `-p no:xdist` workaround is removed. A separate shutdown-time
    `QApplication` teardown segfault was historical under the legacy Qt5/sip
    binding; whether it still applies under PySide6/shiboken is unverified —
    do not assert it as current. It fires AFTER coverage data is written so it
    does not affect the gate either way.
- **Coverage-gate invocation** (`bash scripts/coverage.sh`) runs the explicit
  3-step gate: `pytest --cov=lightsheet --cov-branch --cov-fail-under=70` →
  `coverage json` → `coverage-threshold`. It is NOT part of the fast
  `uv run pytest test/ -q` iteration path (that stays snappy, no `--cov`).
  Run it before committing a change that touches a safety-critical module
  (see §2), and before any high-risk refactor — the gate exists to protect
  safety-critical modules and high-risk structural work. The completed Phase 6
  threading migration and Phase 7 Qt6/Python 3.12 port are historical examples
  of the kind of work the gate exists to protect, not upcoming work. The
  rig-side invocation is `LIGHTSHEET_HW=1 bash scripts/coverage.sh` (run on
  the rig per §4): it runs the same 3-step script with the real
  hardware path unskipped, collecting coverage for the modules pragma'd or
  omitted on a dev machine (`lightsheet/hal/real/camera.py` wholly, plus the
  hardware-probe call sites in `lightsheet/hal/real/motors.py` /
  `siggen.py` / `etls.py` / `ibeam_smart.py`). Running it on the rig is an
  **operator action** (§2 — do not change laser/motor state on the rig unless
  explicitly asked), not something this script or an agent invokes
  automatically.
- **Per-module threshold tiers** (configured in `pyproject.toml` under
  `[tool.coverage-threshold]` and `[tool.coverage-threshold.modules.*]`,
  enforced by `coverage-threshold` in step 3 of `scripts/coverage.sh` via
  longest-prefix-wins matching on the module-path keys):
  - **80% branch default** (`file_branch_coverage_min = 80`) for every
    dev-machine-measurable module not in a tier below.
  - **100% branch safety tier** on three exact-file keys:
    `lightsheet/hal/real/daqlaser.py`, `lightsheet/hal/real/motors.py`,
    `lightsheet/hal/real/ibeam_smart.py`. This list MUST mirror §2's
    safety-critical module list — the inline comment on the
    `[tool.coverage-threshold.modules.*]` keys says so; keep them in sync
    when either list changes.
  - **0% on the one wholesale omit**: `lightsheet/hal/real/camera.py` (its
    entire `__init__`→`open()`→`pco.Camera()` chain is dev-machine-unreachable with
    no testable logic outside the probe — omitted in
    `[tool.coverage.run].omit`, threshold pinned to 0 so it never appears in
    the below-threshold failure list).
  - **Trade-off note — controller.py E-stop warn branch:** the
    `updateUi_estop_pressed` warn branch (the E-stop laser-off failure path
    that emits a per-laser "STILL BE ON" warning when an `off()` returns
    `error`) is behavior-tested, but is gate-enforced only at the 80%
    `controller.py` default tier, NOT at 100%. `controller.py` is ~1451 lines
    (`lightsheet/gui/shell/controller.py`) with Qt-unreachable code
    (constructors, slot wiring, UI refresh), making 100% module-wide branch
    coverage impractical. The 100% gate enforcement applies ONLY to the 3 HAL
    safety modules above; the E-stop warn branch's ongoing correctness relies
    on its one-time behavior test staying in the suite, not on the coverage
    gate re-verifying it every run. Do not delete that test.
- `test/` also contains legacy standalone scripts (`daqmx.py`, `h5test.py`,
  `hdf5_to_tiff.py`, `axial_resolution.py`, etc.) — these are manual
  calibration/experiment utilities, NOT pytest tests. Don't treat failures in
  them as test failures.
- New tests go in `test/test_<thing>.py` and use one of the established
  **behavior** patterns:
  - **Pure-logic** (`test_waveforms.py`, `test_config.py`, `test_gaussian.py`):
    direct import + call + assert.
  - **HAL logic via `__new__`** (`test_motor_limits.py`,
    `test_camera_timeout.py`): bypass `__init__`'s hardware probe with
    `__new__`, populate only the attrs the logic reads, exercise the method,
    assert on behavior.
  - **Mock-serial HAL** (`test_ibeam.py`, `test_etl_serial.py`):
    `patch("<module>.serial.Serial")`, configure `readline` side effects,
    exercise the real HAL method, assert on captured writes + error surface.
  - **DAQ HAL under conftest stub** (`test_daqlaser.py`): construct the real
    class; the stub makes `Task()` raise, firing the real typed-except path.
  - **Controller methods via real construction** (`test_laser_controls.py`,
    `test_controller_behavior.py`, `test_demo_factory.py`,
    `test_controller_methods.py`, `test_hardware_manager.py`,
    `test_validate_file_name.py`, `test_laser_metadata.py`,
    `test_acquisition_coordinator.py`): construct the real
    `Controller_MainWindow` on a dev machine via `make_controller(qtbot, request)` (see
    `test/_helpers/controller_fixture.py`), which mirrors `main()`'s
    composition root with a mock `DeviceBundle` + all four collaborators
    wired + `hardware_init` called. Call the REAL method on the real
    controller and assert on real attributes / Qt widget state / signals.
    `QT_QPA_PLATFORM=offscreen` + the conftest SDK stubs make this work
    without a display or real hardware.
  - **Conformance (TST-04)** (`test_<device>_conformance.py`): parametrize over
    `[real, mock]` (skip `real` on a dev machine via `skipif(not _has_hardware)`), one
    assertion body calls `XXX_CONTRACT.assert_lifecycle` /
    `assert_error_surface` / `assert_read_attrs` / `assert_setter_methods` /
    `assert_getter_methods` behind both ids. Safety-critical behavior
    (synchronous `off()`, `set_power` clamp) goes in dedicated tests on all
    paths, not in the contract module. The power-meter family has its own
    conformance test (`test_power_meter_conformance.py`) — `IPowerMeter` is
    read-only so the contract asserts the `open`/`close`/`read_power`/`zero`
    lifecycle and the absence of any power-setting method.
  - **Mock ABC conformance** (`test_mock_abc_conformance.py`): asserts
    `Mock*` classes satisfy their ABCs at runtime and preserve safety
    invariants (travel limits, synchronous `off()`, power clamp).
    `MockPowerMeter` is included — it preserves the read-only invariant (no
    `set_power`).
  - **Golden-master replay** (`test_golden_acquisition.py`): asserts the
    ordered `sig_message` / `sig_progress_update` emission sequence of
    `acquire_scan` equals one of the fixtures in `test/golden/`. There are
    three: `default.json` and `preview_auto_laser.json` (both `[]` — the
    genuine silent-happy-path contract; a successful acquisition emits nothing
    on the message channel) and `siggen_create_scanner_fail.json` (non-empty —
    the error-path emission). Regenerate with `uv run python test/golden/_record.py`
    (review the diff before committing; never hand-edit the fixtures). The
    golden master is the safety net for the god-object split — a behavior
    change in the acquisition path shows up as a fixture diff.
  - **Registry / channel-map / config-schema (pure-logic)**:
    `test_device_registry.py` mocks `serial.tools.list_ports.comports()` and
    asserts VID/PID+serial resolution + `UnresolvedDeviceError` collect-all;
    `test_channel_map.py` / `test_siggen_channel_map.py` assert
    `ChannelMap.order_galvos`/`clamp_*` and the 4 siggen wiring sites;
    `test_config_schema.py` asserts the strict/overlay tiers reject unknown
    and out-of-range safety keys and that `collect_config_errors` is
    collect-all.
  - **Collaborator / estop regression**: `test_motor_controller.py` exercises
    the extracted motor slots; `test_estop.py` asserts no collaborator
    (`HardwareManager`/`MotorController`/`FrameSaverController`/
    `AcquisitionCoordinator`) owns an `estop`/`kill` method — the kill path
    stays in the shell.
  - **Rig-only** (`test_*_rig.py`): module-top
    `pytestmark = pytest.mark.skipif(not _real_nidaqmx_available(), ...)`;
    run on the rig with `LIGHTSHEET_HW=1`. Rig tests write 0 V only (laser OFF).
- **Do NOT write static-source tests** — i.e. tests that read a `.py` file as
  text (via `open()`/`re.search`/`in src`) and assert on its string/regex
  content. They are fragile (any whitespace-or-name refactor breaks them) and
  they exercise no code, so a passing test proves nothing about runtime
  behavior. This includes grep-based "method-body slicing" assertions against
  `lightsheet/gui/shell/controller.py`. The `make_controller` real-construction
  fixture above is the sanctioned way to test controller methods — it
  executes the real body on the real controller.

Always run the test suite after non-trivial changes. If you add a feature, add
or extend a `test_*.py` covering it on the dev-machine path — with a behavior test, not
a static-source grep.

## 6. Running the app

```bash
uv sync                           # reconcile .venv against uv.lock (run after pulling)
uv run lightsheet                 # preferred — launches the console script in the uv venv
uv run python -m lightsheet       # debug fallback
uv run lightsheet --demo          # force mock HAL (also via LIGHTSHEET_DEMO=1)
```

The package is installed editable (see `pyproject.toml`); both forms resolve
to `lightsheet.__main__:main` and work from any CWD. `uv run lightsheet` is
preferred because `uv run` reconciles the `.venv` against `uv.lock` before
launching, so the dependencies the app needs are guaranteed present.

`main()` preloads `nicaiu.dll` on Windows BEFORE PySide6 loads Qt DLLs
(guarded to `sys.platform == "win32" and not demo`) — without it every
`nidaqmx.Task()` crashes with an access violation. Do not reorder the preload
ahead of the Qt imports. On a dev machine this is skipped and hardware init fails
gracefully (HAL classes catch SDK errors and set `self.error`). The dev-machine launch
is useful for UI/layout checks, not for real acquisition.

The app theme is the vendored **BreezeStyleSheets** stylesheet (NOT on PyPI;
source vendored under `lightsheet/gui/_vendor/breezestylesheets/`, compiled
into `lightsheet/gui/breeze_pyside6.py` via `scripts/build-breeze.sh` using
`pyside6-rcc`). `main()` loads the Breeze `.qss` matching the system color
scheme (light/dark) and applies it via `app.setStyleSheet(...)`. Do not hand-edit
`breeze_pyside6.py` — it is generated; rebuild it with
`bash scripts/build-breeze.sh` after touching the vendored Breeze source.

## 7. Repo layout

```
lightsheet/                    importable package (importable as `lightsheet`)
  __init__.py                  empty (package marker)
  __main__.py                  Qt bootstrap + SOLE COMPOSITION ROOT: main() builds the
                               DeviceBundle (real via DeviceRegistry, or mock via
                               _build_demo_bundle), runs ConfigValidator, then constructs
                               Controller_MainWindow(bundle, demo, fs, hw, acq, mc) and the
                               4 collaborators (FrameSaverController, HardwareManager,
                               AcquisitionCoordinator, MotorController). QApplication +
                               Breeze stylesheet + nicaiu preload + logging + excepthook.
                               (exposed as lightsheet.__main__:main; launched via the `lightsheet` console script)
  config.py                    cfg_read / cfg_write / cfg_str2bool (case-sensitive configparser helpers)
  config_schema.py             pydantic-settings two-tier schema (8 strict + 8 overlay
                               BaseSettings models) + collect_config_errors + ConfigValidator
                               modal dialog. Startup validation gate (see §2, §9). Also
                               carries the Image File Format / save-format keys
                               (hdf5/zarr/both/tiff) that drive the FrameSaver save path.
  channel_map.py               frozen ChannelMap value object: galvo_left_right_swap flag
                               (default False), order_galvos, clamp_galvo (±10V),
                               clamp_etl (0-5V). Pure stdlib. The channel-reversal
                               MECHANISM (RFR-04); actual flip is rig-verification (HW2-02).
  waveforms.py                 pure-numpy squarewave/sawtooth/staircase generators (no SDK, no Qt)
  gaussian.py                  beam-width model used by ETL calibration fits
  logging_setup.py             configure() — RotatingFileHandler + StreamHandler from [Logging]
  gui/                         Qt UI subpackage (importable as `lightsheet.gui`)
    __init__.py                empty (package marker)
    shell/                     the UI shell — composition-root-facing controller + generated UI
      __init__.py              empty (package marker)
      controller.py            Controller_MainWindow — a THIN UI-WIRING SHELL (~1451 lines).
                               Holds `self._bundle` + `self.lasers`, wires Qt signals/slots,
                               owns the E-stop kill path (stays in the shell by design), and
                               delegates all real work to the 4 collaborators via `self._fs` /
                               `self._hw` / `self._acq` / `self._mc`. No worker bodies, no HAL
                               construction, no image reconstruction, no motor move logic
                               remains here.
      ui_shell.py              GENERATED by pyside6-uic — DO NOT hand-edit
      ui_shell.ui              Qt Designer source for ui_shell.py
      ui_shell.qrc             resource collection source for ui_shell_rc.py
      ui_shell_rc.py           GENERATED by pyside6-rcc — DO NOT hand-edit
    coordinators/              plain-Python collaborators (NOT QObject, except FrameSaver/FrameViewer)
      __init__.py              empty (package marker)
      acquisition_coordinator.py AcquisitionCoordinator — plain-Python (NOT QObject). Owns the
                               galvo/ETL/camera-setting updateUi_* slots and the D-05 auto-laser
                               fold (start_lasers after arm, stop_lasers before disarm). The
                               4 acquisition worker BODIES moved OUT to gui/workers.py.
      hardware_manager.py      HardwareManager — plain-Python. Owns laser write/toggle/poll/
                               readback (start_lasers/stop_lasers/_toggle_laser*/_write_laser*
                               _power/_poll_laser*_status/_refresh_laser_readback) and
                               open_laser2 (iBeam serial-open lifecycle). Owns NO estop/kill
                               method — the kill path stays in the shell (see §2).
      frame_saver_controller.py FrameSaverController + FrameSaver(QObject) + FrameViewer(QObject)
                               + FrameSaverWorker(QObject) + the pure image-reconstruction
                               functions (crop_buffer, reconstruct_frame,
                               reconstruct_frame_linear_blend). The QObjects live here, not in
                               the shell controller. Writes per-laser HDF5 metadata from the
                               live `self.parent.lasers` (no cfg_read at save time). NOW also
                               owns the Zarr save path: ZarrSaver uses
                               liom_toolkit.utils.zarr_writer.AnalysisOmeZarrWriter to write
                               OME-Zarr alongside the existing HDF5 (h5py) path; the active
                               format is driven by config (hdf5/zarr/both/tiff — see §9).
      motor_controller.py      MotorController — plain-Python. Owns the 20 motor move/jog/stop
                               slots + camera-focus / ETL-interpolation helpers. Motor
                               travel-limit ValueError → sig_message + sig_beep abort preserved
                               in every move method.
    panels/                    per-panel widget/controller modules + generated UI
      __init__.py              empty (package marker)
      acquisition_panel.py     AcquisitionPanelWidget
      acquisition_table_manager.py AcquisitionTableManager
      calibration_panel.py     CalibrationPanelWidget — Camera/ETL/Horizontal calibration
                               widget container (slot logic lives in MotorController, wired in
                               wire_collaborators). The OLD calibrate_camera_worker /
                               calibrate_etls_worker are still GONE (see §13).
      image_view.py            QGraphicsView-based native Qt6 image display widget
      laser_panel.py           LaserPanelWidget
      levels_bar.py            LevelsBar (histogram/levels widget)
      motor_panel.py           MotorPanelWidget
      past_acquisitions_browser.py  PastAcquisitionsBrowser
      properties_dialog.py     Properties_Dialog (extracted from the old controller)
      save_panel.py            SavePanelWidget
      scan_panel.py            ScanPanelWidget
      stack_panel.py           StackPanelWidget
      ui_*_panel.py            GENERATED by pyside6-uic — DO NOT hand-edit (one per panel)
      ui_*_panel.ui            Qt Designer source for the matching ui_*_panel.py
      ui_*_panel.qrc           resource collection source for the matching ui_*_panel_rc.py
      ui_*_panel_rc.py         GENERATED by pyside6-rcc — DO NOT hand-edit (one per panel)
      ui_properties.py         GENERATED by pyside6-uic — DO NOT hand-edit
      ui_properties.ui         Qt Designer source for ui_properties.py
    widgets/                   reusable custom widgets
      __init__.py              empty (package marker)
      field_spec.py            declarative FieldSpec policy table for promoted spinboxes
      field_spec_spinbox.py    FieldSpecSpinBox — promoted Qt Designer custom widget
    workers.py                 Per-mode acquisition worker QObjects (PreviewWorker / LiveWorker
                               / SingleWorker / StackWorker, each QObject + QThread +
                               moveToThread) + _AcquireScanMixin. Workers emit
                               sig_refresh_position_horizontal / sig_*_mode_finished for UI
                               updates and read pre-sampled save args (see §11). The
                               cooperative cancellation model (*_mode_started flag +
                               estop_event) is preserved verbatim from the threading migration.
    _vendor/breezestylesheets/ vendored BreezeStyleSheets source (NOT on PyPI) — compiled into
                               breeze_pyside6.py via scripts/build-breeze.sh. Do not hand-edit
                               the compiled module.
    breeze_pyside6.py          GENERATED by pyside6-rcc from the vendored Breeze .qrc —
                               DO NOT hand-edit (rebuild via scripts/build-breeze.sh)
    resources/                 Qt resources (PNGs)
  hal/                         HAL subpackage — interfaces + real + mocks + conformance + registry + bundle
    __init__.py                barrel re-export shim (the deliberate exception to no-barrel-files).
                               DeviceRegistry/UnresolvedDeviceError are lazily exported via
                               __getattr__ so importing the barrel on the --demo path does NOT
                               pull in pyserial. __all__ now includes IPowerMeter, MockPowerMeter,
                               PM100D, PM100DError, PM100DNotConnected.
    interfaces.py              pure-abc HAL contracts (layered IXxxCore/IXxx + unified ILaser).
                               IPowerMeter (read-only optical power ABC) around line 778 —
                               NOT part of DeviceBundle (calibration-only, see §10).
    conformance.py             ConformanceContract dataclass + per-family constants. Includes
                               the power-meter contract.
    bundle.py                  @dataclass(frozen=True) DeviceBundle — the immutable value object
                               for HAL handle injection (camera/siggen/motors/etls/lasers as
                               tuple). Safety property: see §2. NO power_meter field — the
                               power meter is opened on demand by the calibration sweep.
    registry.py                DeviceRegistry + UnresolvedDeviceError — USB-serial device role
                               resolver for the RIG path only. Resolves COM ports by
                               VID/PID + serial_number against hardware_inventory.yaml
                               (RFR-02). PRESENCE-ONLY design: resolved ports validate device
                               identity but are NOT wired into HAL constructors — HAL classes
                               read their own config.ini ports (see §10, §13).
    real/                      vendor-bound concrete implementations (rig path)
      camera.py                Camera (PCO)
      siggen.py                SigGen (NI-DAQmx galvo/ETL AO + camera trigger DO). Uses
                               ChannelMap.order_galvos/clamp_* at all 4 np.stack sites.
      motors.py                Motors container + ZaberMotor (3 axes, shared COM3)
      etls.py                  ETLs container + Optotune (EL-10-30, CRC serial)
      daqlaser.py              DAQLaser (NI-DAQ AO, mW-canonical)
      ibeam_smart.py           IBeamSmartLaser adapter + inner IBeam serial engine. Reply-lag
                               mitigations: per-instance RLock, reset_input_buffer flush, 50ms
                               inter-command gap, reboot() on parse failure. Lock identity
                               IBeamSmartLaser._lock = self._ibeam._lock.
      pm100d.py                PM100D (Thorlabs power meter via TLPMX DLL) + PM100DError /
                               PM100DNotConnected. Read-only: open/close/read_power/
                               read_power_mw/zero. No power-setting method.
    mocks/                     standalone mock implementations (dev machine / --demo path)
      mock_camera.py           MockCamera
      mock_siggen.py           MockSigGen (has parity `channel_map` attr)
      mock_motors.py           MockMotors + MockMotor
      mock_etls.py             MockETLs
      mock_laser.py            MockLaser
      mock_power_meter.py      MockPowerMeter — read-only (open/close/read_power/
                               read_power_mw/zero); preserves the IPowerMeter read-only
                               invariant (no set_power).
config.ini                     runtime hardware config (case-sensitive keys)
config.rig-specific.ini        rig-specific config overlay (gitignored)
hardware_inventory.yaml        static device/wiring manifest — VID/PID + serial_number per
                               USB-serial adapter. Human-readable BUT also parsed by
                               DeviceRegistry at startup (rig path) for port resolution.
scripts/
  build-breeze.sh              rebuild lightsheet/gui/breeze_pyside6.py from the vendored
                               BreezeStyleSheets source via pyside6-rcc — run after touching
                               lightsheet/gui/_vendor/breezestylesheets/. Do NOT hand-edit
                               breeze_pyside6.py.
  coverage.sh                  the 3-step coverage gate (see §5)
  snapshot-rig-config.sh       rig config snapshot helper
docs/
  gui-layout-convention.md     authoritative GUI layout convention (264 lines) — QScrollArea
                               wrap rule, size-policy table, left-rail spec, Phase 9 extension
                               seam. Agents touching GUI layout MUST read this first.
test/                          pytest tests + legacy manual scripts (see §5)
pyproject.toml                 project + tool config (ruff, pytest, ty, project.scripts).
                               requires-python >=3.12,<3.13; PySide6>=6.8, nidaqmx, pco, h5py,
                               liom-toolkit[io]>=1.1.
uv.lock                        uv lockfile (Python 3.12, pinned deps)
```

The legacy root-level `lightsheet/<device>.py` HAL layout no longer exists —
device modules live under `lightsheet/hal/real/`. Import HAL classes through
the `lightsheet.hal` barrel (`from lightsheet.hal import Camera, MockCamera,
ICamera, ILaser, DAQLaser, DeviceBundle, IPowerMeter, MockPowerMeter`) so
import-path churn is absorbed in one place. The god-object
`Controller_MainWindow` was split (phase 05) into a thin shell + 4
plain-Python collaborators; `main()` in `__main__.py` is the sole composition
root — do not construct collaborators or HAL instances anywhere else (see
§10). The flat `gui/controller.py` (~1936 lines) + flat
`acquisition_coordinator.py` / `hardware_manager.py` /
`frame_saver_controller.py` / `motor_controller.py` / `properties_dialog.py`
layout was reorganized (phase 7.1 / 8.1) into the
`gui/{shell,coordinators,panels,widgets}` tree above; the shell controller is
now `lightsheet/gui/shell/controller.py` (~1451 lines).

**GUI layout convention:** `docs/gui-layout-convention.md` is the
authoritative layout convention for the left-rail + QStackedWidget shell
(QScrollArea wrap rule, size-policy table, left-rail spec, Phase 9 extension
seam). Agents touching GUI layout MUST read it first — resize is uniform by
construction only if every panel follows it.

**Breeze stylesheet rebuild:** `scripts/build-breeze.sh` rebuilds
`lightsheet/gui/breeze_pyside6.py` from
`lightsheet/gui/_vendor/breezestylesheets/` via `pyside6-rcc`. Run it after
touching the vendored Breeze source; do NOT hand-edit `breeze_pyside6.py`
(it is generated).

## 8. Generated UI files — never hand-edit

`lightsheet/gui/shell/ui_shell.py`, the per-panel
`lightsheet/gui/panels/ui_*_panel.py`, the per-panel
`lightsheet/gui/panels/ui_*_panel_rc.py`, and
`lightsheet/gui/shell/ui_shell_rc.py` are produced by `pyside6-uic` /
`pyside6-rcc` from the `.ui` / `.qrc` sources. They begin with a
`# WARNING: Any manual changes made to this file will be lost...` header.

- To change the UI, edit the `.ui` file in Qt Designer and regenerate, OR add
  widgets programmatically in `lightsheet/gui/shell/controller.py` (the
  established approach for toolbars and the laser status labels — see the
  E-stop toolbar button wired in `wire_collaborators`).
- Never edit the generated `.py` files directly.

## 9. Config pattern (config.ini)

- All runtime config lives in `config.ini`, parsed by `lightsheet/config.py`.
  `config.rig-specific.ini` is a gitignored rig overlay.
- Keys are **case-sensitive** (`cfg.optionxform = str` disables configparser's
  default lowercasing — `# ty: ignore[invalid-assignment]` on those lines
  because ty stubs the attribute as a method). INI keys are Space-separated
  Title Case: `'Galvo Left Amplitude'`, `'ETL Left Offset'`, `'Max Power'`,
  `'Laser1 mW per Volt'`.
- Use the helpers, do not parse INI directly:
  - `cfg_read(filename, section, defaults_dict)` — reads a section, updates only
    keys in `defaults_dict`, ignores extraneous keys, returns the updated dict.
  - `cfg_write(filename, section, dict)` — writes/updates keys without erasing
    others in the section.
  - `cfg_str2bool(v)` — `'true'`/`'t'`/`'yes'`/`'1'` → `True` (case-insensitive).
- Every HAL class declares a class-level `_cfg_defaults: dict[str, str] = {}`
  (with `# noqa: RUF012` and inline unit comments: `# In volts`, `# [s]`,
  `# Boolean`, `# In uW`), sets `self._cfg_filename = "config.ini"` +
  `self._cfg_section = "<Section>"` in `__init__`, then calls
  `self.cfg_load_ini()` (which calls `cfg_read` and assigns instance attrs).
  `cfg_save_ini()` packs instance vars back and calls `cfg_write`.
- Config-backed instance attributes mirror the INI key lower-cased + underscored:
  `Galvo Left Amplitude` → `self.galvo_left_amplitude`;
  `Laser1 mW per Volt` → `self.mw_per_volt`.
- Treat `Max Power` and `* Limit High` keys as safety-critical — review every
  change to them. They are the only way to raise the software clamp ceiling.
- **Startup schema validation (phase 05):** `lightsheet/config_schema.py`
  defines a pydantic-settings model per INI section — 8 strict
  (`extra='forbid'`, rejects unknown keys) for sections the operator must not
  typo into, and 8 overlay (`extra='ignore'`, tolerates extra keys) for the
  gitignored rig overlay. `settings_customise_sources` returns only the init
  source (no env-var source) so a stray env var can't override a safety key.
  `collect_config_errors` is collect-all — it gathers every section's errors
  in one pass, and `ConfigValidator.validate_or_abort` shows them in a single
  modal QDialog (Exit button default) before the controller is constructed.
  Safety-critical out-of-range values (`[iBeam] Max Power` > 150000, `[Motors]`
  `* Limit High` beyond 41.0/18.8/35.0 mm) are **rejected** at both tiers, not
  clamped. When adding a config key, add it to the matching schema model so it
  is validated; do not let a new key slip through unvalidated. The runtime
  `cfg_read`/`cfg_write` helpers in `config.py` remain the read/write mechanism
  the HAL classes use at construction time — the schema is the gate, not a
  replacement for them.
- **Image File Format / save-format keys:** the schema also carries the
  `Image File Format` key (field `image_file_format`,
  `Literal["hdf5", "zarr", "both", "tiff"]`, default `"both"`) on both the
  strict and overlay tiers, with a `field_validator` that lower-cases the
  value (so `"HDF5"` in `config.ini` normalizes to `"hdf5"`). This key is the
  persisted default save format loaded at startup into `self.save_format` and
  drives the FrameSaver save path: `"hdf5"` → the existing `frame_saver_worker`
  (byte-identical HDF5 via h5py); `"zarr"` → `zarr_save_worker` (OME-Zarr via
  `liom_toolkit.utils.zarr_writer.AnalysisOmeZarrWriter`); `"both"` →
  `both_save_worker` (single consume loop writing each frame to both formats);
  `"tiff"` → falls back to the HDF5 path (legacy). The save-panel radio group
  overrides it per-acquisition. When touching the save path, keep the schema
  validator and the FrameSaver format dispatch in sync.

## 10. HAL architecture — follow it for new device classes

**Composition root & dependency injection (phase 05).** `main()` in
`lightsheet/__main__.py` is the SOLE place that constructs HAL instances and
the controller's collaborators. The flow is:

1. Build a `DeviceBundle` — on the rig, `DeviceRegistry.resolve()` reads
   `hardware_inventory.yaml` + `config.ini` and constructs the real HAL
   instances; under `--demo`, `_build_demo_bundle()` constructs `Mock*`
   instances. `DeviceRegistry` is lazily imported (inside the `else:` branch
   of `if demo:`) so the demo path never imports pyserial.
2. Run `ConfigValidator().validate_or_abort()` — runs on BOTH paths, before
   the controller exists (see §9).
3. Construct `Controller_MainWindow(bundle, demo, fs, hw, acq, mc)` and the
   four collaborators (`FrameSaverController`, `HardwareManager`,
   `AcquisitionCoordinator`, `MotorController`), assigning them to
   `controller._fs` / `._hw` / `._acq` / `._mc`.

The controller stores `self._bundle` and `self.lasers = list(self._bundle.lasers)`
once in `hardware_init`, then delegates. Collaborators hold a `self._shell`
back-reference (typed under `TYPE_CHECKING` to avoid an import cycle) and read
`self._shell.<sig>` / `self._shell.ui.*` / `self._shell.lasers` — they do NOT
own HAL instances. Three collaborators are plain-Python (NOT QObject);
`FrameSaver`/`FrameViewer`/`FrameSaverWorker` are QObjects and live in
`frame_saver_controller.py`. **No collaborator owns an `estop`/`kill` method**
— the E-stop kill path stays in the shell (see §2). When adding logic, put it
in the collaborator that owns the concern (lasers → HardwareManager,
acquisition workers/slots → AcquisitionCoordinator, save/reconstruction →
FrameSaverController, motors → MotorController), and keep the shell method a
thin `self._<collaborator>.<method>()` delegate. Do not reintroduce god-object
logic into the shell controller.

**DeviceRegistry (rig path only, presence-only design).** `registry.py`
resolves USB-serial devices by `(vid, pid, serial_number)` against
`hardware_inventory.yaml`: serial-numbered adapters (iBeam COM4, ETLs
COM5/COM6) match on the serial alone; the null-serial Zaber adapter (COM7)
falls back to `config.ini [Motors] Port` as the sole second factor, with
strict abort on ambiguity. It raises `UnresolvedDeviceError` (collect-all) if
any device is missing. **The resolved ports are NOT wired into the HAL
constructors** — the HAL classes read their own `config.ini` ports. This is a
deliberate presence-only design: the registry validates that the right
physical adapter is on the bus, but on a correctly-wired rig the config.ini
ports already match the resolved ports. The "COM ports reorder on replug" bug
(RFR-02) is therefore only PARTIALLY fixed — a replug that reorders COM ports
will still make the HAL fail to open the old config.ini port. Wiring resolved
ports into the HAL constructors is a deferred follow-up; do not assume the
registry redirects the HAL today.

**ChannelMap (galvo/ETL channel-reversal mechanism).** `channel_map.py` is a
frozen value object with a `galvo_left_right_swap` flag (default `False`,
behavior-preserving), `order_galvos(left, right)`, `clamp_galvo` (±10 V), and
`clamp_etl` (0-5 V). `SigGen` calls it at all four `np.stack` sites, and
`MockSigGen` carries a parity `channel_map` attr. The actual left/right flip
against real galvo wiring is rig-verification work (HW2-02) — the mechanism
ships with `swap=False`. Do not "fix" the channel ordering from a dev machine; flip
it via `config.ini`'s `Galvo Left Right Swap = True` only after rig
verification.

The HAL is split into `lightsheet/hal/{interfaces,conformance,real,mocks}/`.
One class per device family. To add a device:

1. **Interface ABC** in `lightsheet/hal/interfaces.py` — a layered
   `IXxxCore` / `IXxx` pair. `IXxxCore` is the controller's actual call graph
   (direct attributes + lifecycle verbs); `IXxx` is the extended public surface
   (getters, config methods) the Properties dialog and rig tests exercise.
   Declare controller-read attributes as **class-level annotations**, NOT
   `@property` + `@abstractmethod` — Python's ABC check runs at instantiation,
   before `__init__` sets instance attrs, and an abstract property descriptor
   is not satisfied by a plain instance attr. Declare lifecycle verbs as
   `@abstractmethod` returning `None`. `ILaser` is single-channel (no Core
   split) and mW-canonical. `IPowerMeter` is a read-only ABC (no Core split,
   like `ILaser`) — see the power-meter note below.
2. **Real implementation** in `lightsheet/hal/real/<device>.py` — inherits
   `IXxx`. Sets `self.error = 0` / `self.error_message = ""` in `__init__`,
   declares `_cfg_defaults`, calls `cfg_load_ini()`. Imports the real SDKs
   (`nidaqmx`, `pco`, `serial`).
3. **Mock implementation** in `lightsheet/hal/mocks/mock_<device>.py` —
   inherits the same `IXxx` from scratch (NOT subclassing the real class, so
   real-class refactors cannot break the mock). No SDK imports; track state in
   software. Preserve safety invariants (synchronous `off()`, `set_power`
   clamping, travel-limit `ValueError`) so they do not atrophy under demo.
4. **Re-export** in `lightsheet/hal/__init__.py` `__all__` + import block.
5. **Conformance contract** — add a `XXX_CONTRACT = ConformanceContract(...)`
   to `lightsheet/hal/conformance.py` derived from the core ABC, and a
   `test/test_<device>_conformance.py` parametrized `[real, mock]`.

**HAL class shape (real and mock):**
- **Class** named after the device family (`Camera`, `SigGen`, `Motors`,
  `DAQLaser`, `IBeamSmartLaser`, `ETLs`, `PM100D`), constructed with no required args
  (or with a dependency, e.g. `SigGen(camera)`).
- **`__init__`**: set `self.error = 0` and `self.error_message = ''`, load
  config, then open/connect to hardware.
- **Lifecycle verbs**: `open()` / `close()`, `arm()` / `disarm()`,
  `start_*()` / `monitor_*()` / `stop_*()` / `delete_*()`.
- **Setters**: `set_<property>(value)` with a documented unit in the docstring
  (`set_power(mw: float)` → "Set the staged laser power in milliwatts").
- **Getters**: `get_<property>()` returning the value, or `None` when the device
  is not open — use the `if self.device is not None: ... else: return None`
  guard.
- **Return values**: lifecycle/setter methods end with explicit `return None`.
- **Verbose flag**: prefer a `verbose=False` arg gating `print(...)` (as
  `Camera` does) over bare prints in new modules.
- **Error handling**: HAL methods catch SDK errors and record them on the HAL
  error surface (`self.error = 1`, `self.error_message = '...'`) rather than
  raising, so a physically-absent device does not crash the controller. The
  controller is then responsible for polling `self.<hal>.error` after calls
  that matter and surfacing failures to the operator via `sig_message` — every
  laser-energizing call site must do this. Catch specific exceptions where the
  SDK exposes them (e.g. `except (nidaqmx.errors.Error, RuntimeError, OSError)`
  in `DAQLaser._write_volts`; `except serial.SerialException` in `IBeam`);
  reserve bare `except:` for the import/probe guards where any failure means
  "hardware not present". Use `raise Exception(...)` only for unrecoverable
  misconfiguration (e.g. unknown shutter mode). When a HAL command can be
  rejected by the device itself (e.g. iBeam `%SYS-E` firmware responses),
  detect that in `_send_cmd` and set the error surface — and guard HAL-internal
  state updates (`self._power`, `self._is_on`) on `if not self.error` so a
  rejection does not leave the HAL believing a failed write succeeded. Use
  `logger = logging.getLogger(__name__)` at module top and `logger.exception`
  inside `except` blocks.

**Unified `ILaser` (mW-canonical):** the controller holds
`self.lasers: list[ILaser]` (index 0 = `DAQLaser` 555 nm, index 1 =
`IBeamSmartLaser` 640 nm). `set_power(mw)` takes milliwatts; `power` /
`max_power` attrs are mW. Each backend converts to its native unit internally
(`DAQLaser`: mW→V via `mw_per_volt`; `IBeamSmartLaser`: mW→µW via ×1000;
`MockLaser`: tracks mW). `off()` is synchronous. Per-laser write lock
(`threading.RLock`) lives on the `ILaser` instance as `self._lock`. The legacy
2-channel `Lasers` container and `IIBeam`/`ILasersCore` ABCs are RETIRED — do
not reintroduce them.

**iBeam reply-lag mitigations (phase 04):** the inner `IBeam` serial engine
in `ibeam_smart.py` is designed against a firmware quirk where rapid
set/get sequences misattribute replies. Every `_send_cmd` acquires the
per-instance `RLock`, calls `reset_input_buffer()` to flush stale bytes,
waits a 50 ms inter-command gap, and on a parse failure the adapter can
`reboot()` (sends `reset system`) to restore clean command/reply pairing.
Lock identity is preserved: `IBeamSmartLaser._lock = self._ibeam._lock` (the
same object, not a new lock) so external write-path locking and the inner
engine serialize against one lock. `get_output_power()` returns mW or `None`
on parse failure / inner error; the GUI degrades to `'{power:.1f} mW (cmd)'`
+ a tooltip when readback is unavailable. Per-laser status
(`sig_laser_status(int, str)` → `updateUi_laser_status`) uses
error > active > inactive precedence; L1 polls on the existing 100 ms
`timer_imageview`, L2 polls on a gated `timer_laser2_status` at
`[iBeam] Status Poll Interval` with a non-blocking lock-skip. Saved HDF5
metadata is written from the **live** `self.parent.lasers` (5 root attrs per
laser: Wavelength/Power/Max Power/Active/Label) — never re-parsed from
config at save time.

**`IPowerMeter` — read-only optical power ABC (NOT bundled).** The power
meter is a calibration/diagnostic instrument, NOT a real-time control device,
so it is NOT part of `DeviceBundle`. `IPowerMeter` (around line 778 in
`interfaces.py`) is a read-only ABC with four lifecycle verbs: `open()` /
`close()` / `read_power()` (returns watts, SI) / `zero()` (dark-offset
adjustment). The concrete backends are `PM100D` (Thorlabs power meter via the
TLPMX DLL, in `lightsheet/hal/real/pm100d.py`) and `MockPowerMeter` (in
`lightsheet/hal/mocks/mock_power_meter.py`). `PM100D` adds a `read_power_mw()`
convenience (watts → mW); both backends preserve the read-only invariant —
there is NO `set_power` and no power-setting path. The power meter is opened
on demand by the laser-calibration sweep script
(`test/laser1_calibration_sweep.py`, rig-only — see §13), not constructed at
startup. Re-export both backends + `IPowerMeter` through the
`lightsheet.hal` barrel; the conformance contract lives in
`lightsheet/hal/conformance.py` and is exercised by
`test/test_power_meter_conformance.py`.

## 11. GUI / controller conventions

- `Controller_MainWindow` (in `lightsheet/gui/shell/controller.py`) inherits
  `QMainWindow` and uses the explicit `QMainWindow.__init__(self)` form, NOT
  `super().__init__()` — a deliberate choice documented in a comment block
  above the `__init__` (see the `fuhm.org/super-harmful` link there). Follow
  this explicit-base-init form for new Qt subclasses here.
- **Qt signals** are class attributes named `sig_<thing>` (`sig_message`,
  `sig_progress_update`, `sig_beep`, `sig_stylesheet`, `sig_laser_status`,
  `sig_refresh_position_horizontal`, `sig_*_mode_finished`). Declare new
  signals as class attributes at the top of the `Controller_MainWindow` class
  body.
- **Slots** connected to widget signals use the `updateUi_<action>` naming and
  are decorated with `@Slot(<type>)` (PySide6 decorator, imported from
  `PySide6.QtCore`) where practical. New slots that update the UI from a
  widget signal MUST follow the `updateUi_` prefix.
- **Cross-thread UI updates go through signals, never direct widget calls from
  worker threads.** This is a hard rule. (The historical `stack_mode_worker`
  direct-call violation — calling
  `self._shell.updateUi_position_horizontal()` directly — was RESOLVED in the
  threading migration: `StackWorker` now emits
  `sig_refresh_position_horizontal`, which is declared on the shell and
  connected to the slot. Do not reintroduce direct widget calls from workers.)
- **Cross-thread Qt widget READS from a worker are also forbidden** (undefined
  behavior per Qt's threading model). Sample widget state on the GUI thread
  before spawning the worker and pass it as constructor args. The historical
  violations (`acquire_scan` reading `lineEdit_saveDescription` /
  `checkBox_saveStitchBlend`, and `stack_mode_worker` reading
  `lineEdit_saveDescription` / `checkBox_saveAllCrop` / `checkBox_saveAllFull`)
  are RESOLVED via pre-sampling: the shell samples these on the GUI thread and
  passes them to the worker constructor as `self._save_description` /
  `self._save_stitch_blend` / `self._save_all_crop` / `self._save_all_full`,
  which the worker reads instead of reaching into `self._shell.ui.*`. The
  `workers.py` module docstring enumerates the pre-sampled args. Do not add
  more cross-tier widget reads; pre-sample on the GUI thread and pass in.
- **One worker thread per acquisition mode**: `updateUi_*_mode_button` toggles
  a `*_mode_started` flag, samples any GUI-thread-only state the worker will
  need (e.g. auto-laser checkbox states via `_cache_auto_laser_flags()`, and
  the save-description / save-checkbox values), then constructs a worker
  `QObject` + a `QThread`, calls `worker.moveToThread(thread)`, connects
  `thread.started` → `worker.run`, `worker.sig_*_mode_finished` → re-enable
  UI, and starts the thread. The worker bodies live in
  `lightsheet/gui/workers.py` (`PreviewWorker` / `LiveWorker` /
  `SingleWorker` / `StackWorker`, each `QObject` + `QThread` +
  `moveToThread`, plus the shared `_AcquireScanMixin`). Do NOT join the worker
  from the toggle slot — just clear the flag; the worker polls it and exits on
  its own. The worker polls the flag for cancellation and `estop_event.is_set()`
  for E-stop at the top of each iteration, and is wrapped in
  `try / except Exception as e: / finally:` — the `except` emits a cause message
  via `sig_message` and logs the traceback via `logger.exception` so no worker
  death is silent, and the `finally` emits `sig_*_mode_finished` exactly once so
  the UI always re-enables. The `updateUi_post_*_mode` slot re-enables UI. The
  shell slot just samples state, constructs the worker + thread, and wires the
  finished signal → re-enable.
- **Laser power write path**: operator edits
  `doubleSpinBox_laser*Amplitude` → `updateUi_laser*_amplitude` restarts a
  300 ms debounce `QTimer` → `_apply_laser*_amplitude` (GUI thread) spawns a
  daemon thread running `self._hw._write_laser*_power`, which acquires
  `self.lasers[i]._lock`, checks `estop_event` (cooperative-skip), scales
  `pct/100 * max_power` to mW, RE-checks `estop_event` immediately before the
  HAL write (force `mw=0` if set), calls `self.lasers[i].set_power(mw)`, checks
  `laser.error`, refreshes status + readback. The staged percentage
  (`laser1_power_pct` / `laser2_power_pct`) is the single persistent source of
  truth for the spinbox values, decoupled from the HAL's mW/V/µW state.
- **User-facing messages**: route through `self.sig_message.emit(str)` →
  `updateUi_message_printer`. Do NOT call `print()` directly from
  `lightsheet/gui/shell/controller.py` or the collaborator modules.
  (`lightsheet/` HAL modules may use `print`, gated by `verbose=False` where
  present.) Pre-existing `print()` calls moved verbatim into `motor_controller.py`
  (focus/interpolation debug prints) and `frame_saver_controller.py`
  (per-file/per-dataset prints) are inherited violations — do not propagate the
  pattern; convert to `logger.info`/`logger.debug` when you touch that code.
- Hardware init is deferred to a single-shot `QTimer` (100 ms) in `__init__` so
  the UI shows before the slow hardware bring-up blocks. Post-split,
  `hardware_init` is thin: it assigns `self.camera/siggen/motors/etls/lasers`
  from `self._bundle`, calls `self._hw.open_laser2()` (the iBeam serial-open
  lifecycle lives in `HardwareManager`), and wires the status-poll timers.
  `Camera` is constructed before `SigGen(self.camera)` (SigGen derives waveform
  timing from camera `xsize`/`ysize`/`line_time`) — preserve this ordering in
  `DeviceRegistry.resolve()` / `_build_demo_bundle()` under both demo and real
  branches.
- `closeEvent` must shut down with a bounded `thread.quit()` +
  `thread.wait(5000)` for each worker `QThread`, not an unconditional
  `time.sleep`. Log (via `logging.warning`, not `sig_message` — the UI is being
  torn down) any worker thread that did not finish in time. Do not reintroduce
  fixed sleeps.

## 12. Code style

- 4-space indent. Ruff is configured (`[tool.ruff]` in `pyproject.toml`) for
  lint + format; run it via `uv run ruff check` and `uv run ruff format`. Ty
  is configured for type-checking (`[tool.ty]`); run via `uv run ty check`.
  No black/flake8/mypy.
- Ruff `select = ["E", "F", "W", "I", "UP", "B", "SIM", "RUF", "ANN"]`,
  `ignore = ["ANN401"]`. `extend-exclude` skips the generated UI files
  (`lightsheet/gui/shell/ui_shell.py`, the per-panel `ui_*_panel.py` /
  `ui_*_panel_rc.py`, `ui_properties.py`) and legacy manual scripts in
  `test/`. `lightsheet/__main__.py` gets `E402` ignored (deferred PySide6
  imports after the nicaiu preload). `# noqa: RUF012` on class-level mutable
  `_cfg_defaults` templates. `# ty: ignore[invalid-assignment]` for
  `cfg.optionxform = str`.
- Ty: `missing-type-argument = "error"`, `unsound-return-statement = "error"`,
  `error-on-warning = true`.
- Match the surrounding style. In `cfg_load_ini` / `cfg_save_ini` blocks, the
  aligned-whitespace and padded-cast style (`int(  self._cfg['Sample Rate']  )`)
  is deliberate — keep it consistent within those blocks.
- Docstrings: prefer `"""..."""` for new multi-line docstrings. Both `'''...'''`
  and `"""..."""` coexist; don't mass-convert. Replace placeholder
  `'''docstring'''` with real docs when you touch that method.
- Type hints: add to new function signatures; don't backfill existing ones. Use
  modern union syntax (`str | None`, `list[ILaser]`, `dict[str, str]`).
- Imports: absolute, rooted at the `lightsheet` package
  (`from lightsheet.config import cfg_read`,
  `from lightsheet.hal import Camera, MockCamera, ICamera`). No relative
  imports (except inside generated `ui_*.py`). `sys.path.append(".")`
  is legacy; don't add to new modules unless meant to be run as scripts from
  repo root. Ruff `I` (isort) enforces ordering: stdlib → third-party → local.
- Naming: `snake_case` for modules/functions/vars; `PascalCase` for classes;
  `I<Device>`/`I<Device>Core` for HAL ABCs; `Mock<Device>` for mocks;
  `is_`/`_is_` prefixes for boolean flags; `<mode>_mode_started` flags;
  leading `_` for private attrs and config plumbing (`_cfg`, `_cfg_defaults`,
  `_cfg_filename`, `_cfg_section`, `_laser1_setpoint`, `_lock`, `_power`).
  Do not propagate the legacy `Controller_MainWindow` underscore-suffix style
  to new classes.

## 13. Known anti-patterns to avoid repeating

- **Direct UI mutation from a worker thread** — use signals (see §11). The
  historical `stack_mode_worker` → `self._shell.updateUi_position_horizontal()`
  direct-call violation is RESOLVED — `StackWorker` now emits
  `sig_refresh_position_horizontal`. Do not add more direct widget calls from
  workers; emit the declared signal instead.
- **Bare `except:` swallowing all errors silently** — acceptable only for the
  hardware import/probe guards; otherwise catch specific exceptions and surface
  state on the HAL error surface (see §10). Note: `FrameSaver.frame_saver_worker`
  has a bare `except Exception:` that silently retries forever on HDF5 errors
  (disk full, h5py internal) — if you touch the save loop, surface persistent
  failures via `sig_status_message` after N retries and `logger.exception` each
  retry. (The Zarr save path adds a second format but the same
  exception-separation rule applies to its save loop.)
- **`sys.path.append(".")` in every module** — legacy; don't add to new modules
  unless they're meant to be run as scripts from repo root.
- **`Camera.copy_recorder_images` returns a zero-filled array when
  `new_data_ready` is False** (`lightsheet/hal/real/camera.py`) — silent data
  loss. The acquisition path guards against reaching it on timeout
  (`acquire_scan` checks `camera.recorder_timeout_status` before copying), but
  the function itself still falls back to `np.zeros`. If you touch the
  timeout/copy path, make failure explicit (raise or return `None`) rather than
  returning zeros.
- **`closeEvent` blocking shutdown with a fixed `time.sleep`** — fixed; the
  current code uses `thread.quit()` + `thread.wait(5000)` per worker QThread.
  Do not reintroduce a fixed sleep; keep shutdown bounded.
- **Static-source / grep-based tests** — reading a module's source as text and
  asserting on string/regex content. Fragile and exercises no code. Forbidden;
  see §5 for the behavioral alternatives (real construction via
  `make_controller`, `__new__` bypass for HAL logic, mock-serial `patch`, or
  the conformance/golden-master suites).
- **Cross-thread Qt widget reads from a worker** — reading
  `self._shell.ui.checkBox_*` directly from an acquisition worker is undefined
  behavior per Qt's threading model and can stall the worker mid-acquisition.
  Sample widget state on the GUI thread before spawning the worker and pass it
  as constructor args (see §11). The historical violations in
  `acquire_scan` + `stack_mode_worker` (reading save checkboxes directly) are
  RESOLVED via the pre-sampling pattern (`self._save_description` /
  `self._save_stitch_blend` / `self._save_all_crop` / `self._save_all_full`).
  Do not add more cross-tier reads.
- **Galvo/ETL left-vs-right channel reversal** — the four `# FIXME (HARDWARE)`
  comments that used to flag this in `siggen.py` are GONE (phase 05). The
  channel-reversal concern is now addressed by the `ChannelMap` mechanism
  (`lightsheet/channel_map.py`): a frozen value object with a
  `galvo_left_right_swap` flag (default `False`) wired into all four siggen
  `np.stack` sites. The mechanism ships behavior-preserving; the actual flip
  against real galvo wiring is rig-verification work (HW2-02). Do NOT flip the
  ordering from a dev machine — set `Galvo Left Right Swap = True` in `config.ini`
  only after rig verification.
- **Dead calibration workflows — DELETED (phase 05), new laser-power sweep
  added (phase 8.1).** The OLD `calibrate_camera_worker` /
  `calibrate_etls_worker` and their slots, signals, `*_calibration_started`
  flags, and hidden buttons were deleted outright. The restoration seam
  (recovery instructions + the git commit `6c63724` to recover from + the
  safety re-verification requirement) is recorded in `ARCHITECTURE.md`'s
  "Restoration Seams" section. Do not reintroduce the old stubs; if you need
  the camera/ETL calibration workflow, restore it from `6c63724` as a scoped
  task. The `calibration_panel.py` re-added in phase 8.1 is a DIFFERENT
  workflow — a Camera/ETL/Horizontal motor-calibration widget container (slot
  logic in `MotorController`), not the old camera/ETL acquisition-calibration
  workers. Separately, a NEW laser-power calibration sweep exists as the
  rig-only script `test/laser1_calibration_sweep.py`: it uses the `PM100D`
  power meter + S245C thermal sensor (via the `IPowerMeter` HAL ABC — see §10)
  to sweep Laser 1 V→mW and record a calibration curve. That is a laser power
  calibration, not the deleted camera/ETL calibration — do not conflate them.
- **`Lasers Terminals` config key is still dead (location moved)** —
  `config.ini` declares `Lasers Terminals` and `config_schema.py` validates it,
  but `DeviceRegistry.resolve()` hardcodes `terminal="/Dev7/ao0"` when
  constructing `DAQLaser` (`lightsheet/hal/registry.py`). Production and
  the rig-only tests diverge. If you touch the laser DAQ terminal wiring, read
  it from config and align production with what the rig tests assume.
- **DeviceRegistry presence-only design (RFR-02 partial)** — the registry
  resolves USB-serial devices by VID/PID+serial but does NOT pass the resolved
  ports into the HAL constructors (HAL classes read their own `config.ini`
  ports). A COM-port reorder on replug will still make the HAL fail to open the
  old config.ini port. This is deliberate for this phase; wiring resolved ports
  into HAL constructors is a deferred follow-up. Do not assume the registry
  redirects the HAL today (see §10).
- **`frame_saver_worker` non-timeout exceptions** — the inner save loop now
  separates `queue.Empty` (timeout) from other exceptions (phase 05 IN-04 fix):
  an h5py write error emits `sig_status_message` and stops the worker instead
  of silently retrying on a corrupt file. The Zarr save path
  (`zarr_save_worker` / `both_save_worker`) follows the same separation. If you
  touch either save loop, preserve that separation; do not collapse the two
  `except` branches back into one bare `except Exception:`.

## 14. Before you finish a task

1. Run `uv run pytest test/ -q` on a dev machine. Fix failures you caused. If you
   touched style-sensitive code, also run `uv run ruff check` and
   `uv run ruff format`, and `uv run ty check` if you touched types.
2. If the change touches hardware behavior and is verifiable on the rig, say so
   and (if asked) verify on the rig (per §4) with read-only queries first
   (`uv sync` then `LIGHTSHEET_HW=1 uv run pytest test/ -q` on the rig).
3. Re-read §2 — confirm no safety control was weakened (motor limits, two-layer
   laser clamp, synchronous E-stop `off()`, lock-free kill path, frozen
   `DeviceBundle`, config-schema rejection of out-of-range safety keys).
4. Do not commit GSD/planning artifacts, decision IDs, or phase IDs in commit
   messages or code comments. Commits and comments must be self-contained.
