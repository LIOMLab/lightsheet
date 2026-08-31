#!/usr/bin/env bash
# Run the test suite single-process (NO xdist) — for debugging only.
#
# This is ~10x slower than scripts/test.sh (xdist-parallel) because it
# runs every test in one process. Use it only when you need:
#   - a clean traceback without xdist worker prefixes ([gwN])
#   - --durations without xdist scheduling noise
#   - a reproducible single-process hang/segfault
#
# Both flags are required: -p no:xdist disables the plugin, and
# -o addopts=... clears the xdist flags in pyproject.toml's addopts
# that would otherwise be "unrecognized arguments" once the plugin is
# gone. Either flag alone breaks. See AGENTS.md §5 "Running tests".
#
# Usage:
#   bash scripts/test-serial.sh                      # full suite, single-process
#   bash scripts/test-serial.sh test/test_foo.py      # one file
#   bash scripts/test-serial.sh -x                    # stop on first failure
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
# If the caller passes test paths, use them; otherwise default to test/.
if [ $# -gt 0 ]; then
  exec uv run pytest "$@" -q -p no:xdist -o addopts="-ra --strict-markers"
else
  exec uv run pytest test/ -q -p no:xdist -o addopts="-ra --strict-markers"
fi
