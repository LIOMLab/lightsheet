#!/usr/bin/env bash
# Run the test suite with xdist parallelism (the project default).
#
# xdist is configured via addopts in pyproject.toml (-n auto
# --maxprocesses=6 --dist=load --max-worker-restart=0). This script
# invokes pytest WITHOUT touching addopts so the xdist flags stay
# intact. Do NOT pass -o addopts=... or --override-ini="addopts=..."
# — either silently strips the xdist flags and drops to single-process
# (~10x slower). See AGENTS.md §5 "Running tests".
#
# Usage:
#   bash scripts/test.sh                      # full suite, xdist-parallel
#   bash scripts/test.sh test/test_foo.py     # one file, still xdist
#   bash scripts/test.sh test/test_foo.py::test_bar   # one test, still xdist
#
# For single-process debugging (read a clean traceback, profile without
# xdist scheduling noise), use scripts/test-serial.sh instead.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
# If the caller passes test paths, use them; otherwise default to test/.
if [ $# -gt 0 ]; then
  exec uv run pytest "$@" -q
else
  exec uv run pytest -q
fi
