#!/usr/bin/env bash
#
# snapshot-rig-config.sh — capture the rig's live, calibrated config.ini into a
# gitignored config.rig-specific.ini sitting next to the tracked baseline.
#
# Why: the calibrated values (galvo amplitudes, ETL offsets, motor travel
# limits, COM ports, laser wavelengths) exist in exactly one place — the
# microscope PC's working copy of config.ini. Losing them costs a recalibration
# session on a physical instrument. This script pulls a verbatim copy off the
# rig and prints the diff against the tracked baseline so the calibration delta
# is visible.
#
# This script is READ-ONLY with respect to the rig. It never writes to the rig,
# never runs a command that moves a motor, changes laser emission, or starts an
# acquisition. Its only remote operations are a `true` reachability probe and a
# single scp of one file from the rig to this machine.
#
# Safe to re-run: an existing config.rig-specific.ini is overwritten, because
# the rig is the source of truth.
#
# Usage:  bash scripts/snapshot-rig-config.sh
#
set -euo pipefail

# --- Locations (edit here if the rig moves) ----------------------------------
# SSH alias configured in ~/.ssh/config (jump host + rig host). Kept as a
# literal so the rig->local scp direction is grep-verifiable in the source.
# Remote config.ini path in MINGW64 / Git Bash form (as used on the rig).
REMOTE_CONFIG="/c/Users/liomlight/Documents/GitHub/lightsheet/config.ini"

# --- Local paths -------------------------------------------------------------
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TRACKED_CONFIG="${REPO_ROOT}/config.ini"
SNAPSHOT="${REPO_ROOT}/config.rig-specific.ini"

# --- Reachability precheck (no interactive hang) -----------------------------
# BatchMode=yes refuses to prompt for a password, so an unreachable rig or a
# missing key fails fast instead of hanging the operator. ConnectTimeout caps
# the wait. We do NOT retry in a loop — per AGENTS.md §4, a rig that is down
# means "defer to a later operator session", not "hammer the jump host".
if ! ssh -o BatchMode=yes -o ConnectTimeout=10 lightsheet-rig true 2>/dev/null; then
    echo "snapshot: rig 'lightsheet-rig' is unreachable (network or jump host down)." >&2
    echo "snapshot: skipped — no file written. Re-run this script in a later" >&2
    echo "snapshot: operator session once the rig is back. Do not retry in a loop." >&2
    exit 1
fi
echo "snapshot: rig 'lightsheet-rig' reachable."

# --- Capture (rig -> local only) ---------------------------------------------
# Pull the remote file into a temp next to the destination, then atomically
# move it into place. Never scp in the other direction.
#
# -O forces the legacy SCP protocol (runs the transfer through the remote
# login shell) instead of the SFTP subsystem that OpenSSH 9+ defaults to.
# This matters because the rig's login shell is MINGW64/Git Bash, where the
# /c/Users/... path form resolves; the SFTP subsystem interprets /c/... as a
# literal Unix absolute path and reports "No such file or directory". -O keeps
# the single rig->local scp transfer grep-verifiable while working on the rig.
TMP_CAPTURE="$(mktemp "${SNAPSHOT}.XXXXXX")"
trap 'rm -f "${TMP_CAPTURE}"' EXIT

if ! scp -O -o BatchMode=yes -o ConnectTimeout=10 "lightsheet-rig:${REMOTE_CONFIG}" "${TMP_CAPTURE}"; then
    echo "snapshot: scp of '${REMOTE_CONFIG}' from the rig failed." >&2
    echo "snapshot: no file written." >&2
    exit 1
fi

# --- Diff against the tracked baseline ---------------------------------------
# A non-empty diff is the EXPECTED, normal outcome — the rig's calibrated
# values drift from the checked-in baseline. We do NOT treat a diff as an
# error. Print a header so the operator can tell which side is which.
if [ -f "${TRACKED_CONFIG}" ]; then
    echo
    echo "--- diff: tracked config.ini (baseline) vs rig config.rig-specific.ini (live) ---"
    # diff exits 1 when the files differ — that is normal here. Use `|| true`
    # so set -e does not turn an expected diff into a script abort.
    diff -u "${TRACKED_CONFIG}" "${TMP_CAPTURE}" || true
    echo "--- end diff ---"
    echo
else
    echo "snapshot: warning — tracked '${TRACKED_CONFIG}' not found; skipping diff." >&2
fi

# --- Commit the capture locally ---------------------------------------------
# Overwrite any prior snapshot — the rig is the source of truth.
mv -f "${TMP_CAPTURE}" "${SNAPSHOT}"

# --- Self-verify git containment --------------------------------------------
# If the ignore rule is missing or ineffective, the captured file would be
# visible to a later `git add` and could leak rig COM ports + calibration
# values into history. Refuse to leave the file in place in that case: delete
# it and exit non-zero so the operator fixes .gitignore before re-running.
if ! git -C "${REPO_ROOT}" check-ignore -q "${SNAPSHOT}"; then
    echo "snapshot: FATAL — git does not ignore '${SNAPSHOT}'." >&2
    echo "snapshot: deleting the captured file to prevent a leak." >&2
    echo "snapshot: add 'config.rig-specific.ini' to .gitignore and re-run." >&2
    rm -f "${SNAPSHOT}"
    exit 1
fi

echo "snapshot: wrote '${SNAPSHOT}' (git-ignored)."

# --- Closing reminder --------------------------------------------------------
echo
echo "snapshot: reminder — re-run this script after every rig recalibration"
echo "snapshot: so config.rig-specific.ini tracks the live calibrated values."
