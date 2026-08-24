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
# step 3. -n auto keeps xdist parallelism; pytest-cov auto-combines workers.
uv run pytest test/ -q --cov=lightsheet --cov-branch --cov-fail-under=70 -n auto

# --- Step 2: emit coverage.json from the combined .coverage data --------------
uv run coverage json

# --- Step 3: enforce per-module thresholds from pyproject.toml ----------------
# Reads [tool.coverage-threshold.modules."<path>"] with longest-prefix-wins.
# Exit non-zero if any module is below its configured threshold.
uv run coverage-threshold
