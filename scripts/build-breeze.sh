#!/usr/bin/env bash
# Build the BreezeStyleSheets PySide6 compiled resource.
#
# BreezeStyleSheets is NOT published on PyPI — it is a GitHub source
# distribution (github.com/Alexhuszagh/BreezeStyleSheets, MIT) that must be
# built via `configure.py --compiled` with `pyside6-rcc`. The vendored source
# tree lives at lightsheet/gui/_vendor/breezestylesheets/ and is pinned to the
# commit below. Running this script regenerates
# lightsheet/gui/breeze_pyside6.py (the committed build artifact the rig needs
# without a configure.py run — same pattern as the committed ui_*_rc.py files).
#
# Usage:
#   bash scripts/build-breeze.sh
#
# Requires: pyside6-rcc on PATH (ships with the project's PySide6 dep).
# Run from the repository root.

set -euo pipefail

# Pin the exact upstream commit the vendored tree was imported from.
# Update this + re-vendor the tree when bumping BreezeStyleSheets.
BREEZE_COMMIT="37199e3bd52ba6aa31bd82e33c6202c0c0f0b180"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENDOR_DIR="${REPO_ROOT}/lightsheet/gui/_vendor/breezestylesheets"
OUTPUT_PY="${REPO_ROOT}/lightsheet/gui/breeze_pyside6.py"

if [ ! -d "${VENDOR_DIR}" ]; then
    echo "ERROR: vendored BreezeStyleSheets not found at ${VENDOR_DIR}" >&2
    echo "Vendor it first (commit ${BREEZE_COMMIT}) before running this script." >&2
    exit 1
fi

# Verify the vendored tree matches the pinned commit. The .git directory is
# NOT vendored (git archive strips it), so this is a documentation check —
# the pinned commit is the source of record.
echo "Building BreezeStyleSheets PySide6 compiled resource"
echo "  vendored from commit: ${BREEZE_COMMIT}"
echo "  vendor dir: ${VENDOR_DIR}"
echo "  output:     ${OUTPUT_PY}"

# Build the compiled resource directly into lightsheet/gui/. configure.py
# emits the compiled-resource module + a sibling dist/ tree of .qss/.svg
# assets; only the compiled .py is needed at runtime (the .qss/.svg are
# embedded inside it as Qt resources).
TMP_OUT="$(mktemp -d)"
trap 'rm -rf "${TMP_OUT}"' EXIT

cd "${VENDOR_DIR}"
# configure.py shells out to `pyside6-rcc`, which lives in the lightsheet
# project's uv-managed .venv/bin — NOT necessarily on PATH. Resolve the rcc
# binary explicitly and pass it via --rcc so configure.py does not depend on
# PATH lookup. Falls back to PATH lookup if the venv binary is absent.
RCC_FLAG=""
RCC_BIN="${REPO_ROOT}/.venv/bin/pyside6-rcc"
if [ -x "${RCC_BIN}" ]; then
    RCC_FLAG="--rcc ${RCC_BIN}"
elif command -v pyside6-rcc >/dev/null 2>&1; then
    : # rely on PATH lookup inside configure.py
else
    echo "ERROR: pyside6-rcc not found (looked in ${RCC_BIN} and on PATH)" >&2
    exit 1
fi

# Run configure.py with the lightsheet project's Python (so the rcc binary
# above resolves to the same PySide6 install). `uv run --project` points uv
# at the lightsheet pyproject.toml rather than the vendored tree's own.
if command -v uv >/dev/null 2>&1; then
    PY="uv run --project ${REPO_ROOT} python3"
else
    PY="python3"
fi
${PY} configure.py \
    --framework pyside6 \
    ${RCC_FLAG} \
    --styles light-blue dark-blue \
    --resource "${TMP_OUT}/breeze.qrc" \
    --compiled "${TMP_OUT}/breeze_pyside6.py" \
    --output "${TMP_OUT}"

cp "${TMP_OUT}/breeze_pyside6.py" "${OUTPUT_PY}"
echo "Wrote ${OUTPUT_PY}"
