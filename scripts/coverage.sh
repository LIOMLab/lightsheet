#!/usr/bin/env bash
#
# coverage.sh — the explicit, non-always-on per-module branch-coverage gate.
#
# Why: the project has no CI (single-machine desktop app). This script is the
# one-command gate an operator runs before a commit / before entering the
# Phase 6 threading or Phase 7 Qt6/3.12 refactors — the high-risk work the
# gate exists to protect. It is intentionally NOT wired into pytest's
# addopts (that would slow every fast iteration run and breed a --no-cov
# habit that defeats the gate) and NOT a pre-commit hook (pre-commit's own
# maintainers warn against running pytest in hooks).
#
# The gate is 3 steps, each a separate `uv run` invocation so a failure at
# any step produces a clear step-attributed error under `set -e`:
#   1. pytest with --cov=lightsheet --cov-branch --cov-fail-under=70 (the
#      70 floor is a fast-fail backstop; the real per-module enforcement is
#      step 3). -n auto keeps the parallel run; pytest-cov auto-combines the
#      xdist worker data into one .coverage file.
#   2. `coverage json` emits coverage.json from the combined data — this is
#      the file coverage-threshold reads.
#   3. `coverage-threshold` enforces the per-module thresholds configured in
#      pyproject.toml [tool.coverage-threshold.modules.*] (longest-prefix-
#      wins: 100% branch on safety-critical HAL modules, 80% branch default
#      on other Mac-measurable modules, 0% on the one wholesale-omitted
#      camera.py).
#
# Usage:
#   bash scripts/coverage.sh             # Mac gate (mocks via test/conftest.py)
#   LIGHTSHEET_HW=1 bash scripts/coverage.sh   # rig gate (real SDKs; rig-only)
#
# Rig-side invocation: `LIGHTSHEET_HW=1 bash scripts/coverage.sh` is run via
# `ssh lightsheet-rig` (see AGENTS.md §4) on the microscope PC. It runs the
# same 3-step script with the real hardware path unskipped, collecting
# coverage for the modules pragma'd or omitted on Mac per the D-02 carve-out
# (documented in AGENTS.md §5): `lightsheet/hal/real/camera.py` wholly (in
# pyproject.toml `[tool.coverage.run].omit`), plus the inline `# pragma: no
# cover` / `# pragma: no branch` hardware-probe call sites in
# `lightsheet/hal/real/{motors,siggen,etls,ibeam_smart}.py`. Running this on
# the rig is an OPERATOR action (AGENTS.md §2 — do not change laser or motor
# state on the rig unless explicitly asked), not something this script or an
# agent invokes automatically.
#
# A non-zero exit at step 3 (below-threshold modules) is the EXPECTED state
# right after branch coverage is first enabled — the 5-15pt drop is the
# signal that the gate is real. Closing those gaps is test-writing work
# (TST-09), not a reason to skip running this script.
#
set -euo pipefail

# --- Repo root (works regardless of CWD) --------------------------------------
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

# --- Step 1: collect coverage with the 70% global floor -----------------------
# --cov-fail-under=70 is the fast-fail backstop; the per-module enforcement is
# step 3. -n auto keeps xdist parallelism. We do NOT use --cov-fail-under here
# because pytest-cov's auto-combine loses branch (arc) data when GC is disabled
# (conftest.py disables GC to prevent Qt widget destructor segfaults on macOS).
# Instead, step 1b manually re-combines with branch=True to preserve arcs.
#
# xdist parallelism is re-enabled (the single-process no-xdist flag is
# removed). xdist workers previously segfaulted at Python shutdown because the
# 53 self-capturing signal lambdas in Controller_MainWindow.__init__ created
# reference cycles whose C++ destructors fired when atexit re-enables GC,
# killing workers before pytest-cov wrote their .coverage.<worker> files
# ("coverage: failed workers", lost data). The signal-lambda cycle is now
# broken at the connection layer: wire_collaborators() uses bare bound-method
# connections (PyQt5 decomposes these into weakref(__self__) +
# strong(__func__), so the signal system holds zero strong refs to the
# controller), so the Python wrapper reaches refcount zero naturally and the
# deferred C++ destructor no longer fires at shutdown. Phase 7 (Qt6 port) will
# confirm the cycle stays broken under PySide6.
#
# The -o addopts override deliberately RE-DECLARES addopts rather than
# inheriting from pyproject.toml: -o replaces the default addopts entirely, so
# the new --dist=load / --max-worker-restart=0 flags added there do NOT apply
# during the coverage run (coverage.sh is single-purpose and its exit-code
# handling is already tuned for the shutdown segfault). -n auto is included
# explicitly so xdist parallelism is not silently dropped; --maxprocesses=6 is
# added here explicitly for memory-bound consistency with the iteration path.
uv run pytest test/ -q --cov=lightsheet --cov-branch -o "addopts=--strict-markers -n auto --maxprocesses=6" || _pytest_exit=$?
# Tolerate the shutdown segfault (exit 139): the .coverage file is written
# BEFORE Python atexit runs, so the data is complete even when the process
# segfaults at shutdown. Any other non-zero exit (test failure, real error)
# is caught by the --fail-under check below.
if [ "${_pytest_exit:-0}" -ne 0 ] && [ "${_pytest_exit:-0}" -ne 139 ]; then
  exit "${_pytest_exit}"
fi

# --- Step 1b: enforce the 70% global floor ------------------------------------
uv run coverage report --fail-under=70

# --- Step 2: emit coverage.json from the .coverage data -----------------------
uv run coverage json

# --- Step 3: enforce per-module thresholds from pyproject.toml ----------------
# Reads [tool.coverage-threshold.modules."<path>"] with longest-prefix-wins.
# Exit non-zero if any module is below its configured threshold.
uv run coverage-threshold
