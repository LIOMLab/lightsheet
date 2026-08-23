"""Manual Laser 1 V->mW calibration sweep utility (operator-run, rig only).

This is NOT a pytest test — it is a manual calibration utility in the same
convention as the legacy ``test/daqmx.py`` / ``test/h5test.py`` scripts
(AGENTS.md Sec.5). It is NOT imported by the app and NOT collected by pytest
(the filename lacks the ``test_`` prefix).

Purpose
-------
Sweep the Laser 1 DAQ analog output (``/Dev7/ao0``) from 0 V to 5 V in
configurable steps. At each voltage the operator reads a power meter and
enters the measured mW. The (V, mW) pairs are written to a CSV that the
follow-up quick task parses into a ``Laser1 Calibration Curve`` config value,
which makes the L1 readback label switch from the unverified
linear-through-origin estimate ("(est.)") to a rig-measured calibration
("(cal.)").

Why this exists
---------------
The diode label says 300 mW but the lab test measured 236.6 mW average at
max — the current ``mW = V * mW_per_volt`` (60 mW/V) model overstates power
by ~27% at full scale. The LRS-0561-PFO-00200-03 is a DPSS laser whose
optical output vs pump current has a threshold knee and possible saturation,
so a single linear slope cannot capture the real V->mW relationship. Only a
measured sweep resolves it.

Safety (AGENTS.md Sec.2 — Class IIIB laser)
-------------------------------------------
- Starts at 0 V and ends at 0 V (laser off).
- Every DAQ write is clamped to [0, 5] V.
- The operator presses Enter before EACH energization — there is no
  automated sweep. The operator is in the loop with the power meter and PPE.
- A clear header warns this is a Class IIIB laser calibration.

Usage (on the rig, with LIGHTSHEET_HW=1)
----------------------------------------
    uv run python test/laser1_calibration_sweep.py
    uv run python test/laser1_calibration_sweep.py --step 0.5 --max-volts 5.0
    uv run python test/laser1_calibration_sweep.py --output test/laser1_calibration.csv

On the Mac (no hardware), exits 1 with a message to run on the rig — the
conftest nidaqmx stub makes ``Task()`` raise, which this script detects.
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime

import numpy as np

# nidaqmx is imported here (not inside main) so the Mac guard fires on
# import-attempt / first Task() construction with a clear message rather
# than a cryptic traceback. On the rig this is the real SDK; on the Mac the
# conftest stub makes Task() raise (intentionally — see AGENTS.md Sec.5).
try:
    import nidaqmx
except Exception as exc:  # pragma: no cover — environment-dependent
    print(
        "ERROR: nidaqmx is not available. This script must be run on the rig "
        "with LIGHTSHEET_HW=1 (real NI-DAQmx SDK installed). On the Mac the "
        "conftest stub makes Task() raise — there is no real DAQ hardware to "
        f"drive. Cause: {exc}",
        file=sys.stderr,
    )
    sys.exit(1)

MAX_VOLTS_HARD_LIMIT = 5.0
DEFAULT_TERMINAL = "/Dev7/ao0"


def _write_voltage(terminal: str, volts: float) -> None:
    """Write ``volts`` (clamped to [0, 5]) to the DAQ AO channel.

    Opens a fresh nidaqmx.Task per write (same pattern as
    DAQLaser._write_volts) so there is no persistent task to clean up.
    """
    volts = max(0.0, min(float(volts), MAX_VOLTS_HARD_LIMIT))
    with nidaqmx.Task(new_task_name="laser1_calibration") as task:
        task.ao_channels.add_ao_voltage_chan(terminal)
        task.write(np.array([volts]), auto_start=True)


def _prompt_reading(volts: float) -> float | None:
    """Prompt the operator for the power-meter mW reading at ``volts``.

    Returns the float mW, or None to skip this step, or raises
    KeyboardInterrupt to quit early. Empty input = skip.
    """
    while True:
        raw = input(
            f"  V={volts:.3f}  enter power-meter mW (Enter=skip, s=skip, "
            f"q=quit): "
        ).strip()
        if raw.lower() in ("q", "quit"):
            raise KeyboardInterrupt
        if raw == "" or raw.lower() in ("s", "skip"):
            return None
        try:
            value = float(raw)
        except ValueError:
            print("    not a number — try again (or q to quit)")
            continue
        if value < 0:
            print("    negative mW — try again")
            continue
        return value


def run_sweep(
    terminal: str,
    step: float,
    max_volts: float,
    output: str,
) -> int:
    """Run the interactive sweep. Returns 0 on success, 1 on abort."""
    max_volts = max(0.0, min(float(max_volts), MAX_VOLTS_HARD_LIMIT))
    step = max(0.05, float(step))
    voltages = list(np.arange(0.0, max_volts + 1e-9, step))
    # Always include the exact max-volts endpoint even if float rounding
    # from arange drops it.
    if voltages and not abs(voltages[-1] - max_volts) < 1e-6:
        voltages.append(max_volts)

    print("=" * 70)
    print("LASER 1 V->mW CALIBRATION SWEEP — CLASS IIIB LASER")
    print("=" * 70)
    print("  Diode:  LRS-0561-PFO-00200-03 (561 nm DPSS)")
    print("  PSU:    Laserglow PSU-H-LED (0-5 V analog modulation)")
    print(f"  DAQ AO: {terminal}")
    print(f"  Steps:  {len(voltages)} points, 0.000 V to {max_volts:.3f} V "
          f"(step {step:.3f} V)")
    print(f"  Output: {output}")
    print()
    print("  WARNING: Class IIIB laser. Wear appropriate PPE. The laser")
    print("  energizes at each step — confirm the beam path is clear and")
    print("  the power meter is positioned BEFORE pressing Enter.")
    print()
    input("  Press Enter when ready to begin (Ctrl-C to abort)... ")
    print()

    # Start at 0 V (laser off) so the sweep begins from a known-safe state.
    _write_voltage(terminal, 0.0)

    pairs: list[tuple[float, float]] = []
    try:
        for volts in voltages:
            print(f"  -> {volts:.3f} V")
            input("     Press Enter to energize, then read the power meter...")
            _write_voltage(terminal, volts)
            reading = _prompt_reading(volts)
            if reading is None:
                print("     (skipped)")
                # Zero the laser between steps so it is not left energized
                # while the operator prepares the next reading.
                _write_voltage(terminal, 0.0)
                continue
            pairs.append((round(float(volts), 6), round(reading, 6)))
            print(f"     recorded: {volts:.3f} V -> {reading:.3f} mW")
            # Zero between steps (re-energize at the next step).
            _write_voltage(terminal, 0.0)
    except KeyboardInterrupt:
        print("\n  Sweep aborted by operator. Writing partial results.")
    finally:
        # Always end at 0 V (laser off) — even on abort.
        _write_voltage(terminal, 0.0)
        print("  Laser driven to 0 V (off).")

    if not pairs:
        print("  No readings recorded — nothing to write.")
        return 1

    pairs.sort(key=lambda p: p[0])
    _write_csv(output, pairs)
    print(f"\n  Wrote {len(pairs)} (V, mW) pairs to {output}")
    print("  Next: run /gsd-quick to fit this CSV into a "
          "'Laser1 Calibration Curve' config value.")
    return 0


def _write_csv(output: str, pairs: list[tuple[float, float]]) -> None:
    """Write the (V, mW) pairs to ``output`` as CSV with a comment header.

    The comment header line (prefixed ``#``) records the date and hardware
    so the follow-up parsing task has provenance. The data rows are
    ``voltage_v,power_mw`` sorted by voltage.
    """
    with open(output, "w", newline="") as f:
        f.write(
            f"# Laser 1 V->mW calibration sweep — {datetime.now().isoformat()}\n"
            f"# Diode: LRS-0561-PFO-00200-03 (561 nm DPSS)\n"
            f"# PSU: Laserglow PSU-H-LED (0-5 V analog modulation)\n"
            f"# Generated by test/laser1_calibration_sweep.py\n"
        )
        writer = csv.writer(f)
        writer.writerow(["voltage_v", "power_mw"])
        for v, mw in pairs:
            writer.writerow([f"{v:.6f}", f"{mw:.6f}"])


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Manual Laser 1 V->mW calibration sweep (rig only). "
        "Sweeps the DAQ AO voltage and records operator-entered power-meter "
        "readings to a CSV.",
    )
    parser.add_argument(
        "--terminal",
        default=DEFAULT_TERMINAL,
        help=f"DAQ AO terminal (default: {DEFAULT_TERMINAL})",
    )
    parser.add_argument(
        "--step",
        type=float,
        default=0.25,
        help="Voltage step in V (default: 0.25, min: 0.05)",
    )
    parser.add_argument(
        "--max-volts",
        type=float,
        default=5.0,
        help="Maximum voltage in V, clamped to 5.0 (default: 5.0)",
    )
    parser.add_argument(
        "--output",
        default="test/laser1_calibration.csv",
        help="Output CSV path (default: test/laser1_calibration.csv)",
    )
    args = parser.parse_args()

    # Mac guard: the conftest stub makes Task() raise. Probe it here with a
    # clear message rather than letting the first _write_voltage crash
    # mid-sweep. On the rig this constructs and tears down cleanly.
    try:
        with nidaqmx.Task(new_task_name="laser1_calibration_probe") as _probe:
            _probe.ao_channels.add_ao_voltage_chan(args.terminal)
    except Exception as exc:
        print(
            "ERROR: could not open a nidaqmx Task on the DAQ AO channel. "
            "This script must be run on the rig with LIGHTSHEET_HW=1 (real "
            f"NI-DAQmx SDK + DAQ hardware). Cause: {exc}",
            file=sys.stderr,
        )
        return 1

    return run_sweep(
        terminal=args.terminal,
        step=args.step,
        max_volts=args.max_volts,
        output=args.output,
    )


if __name__ == "__main__":
    sys.exit(main())
