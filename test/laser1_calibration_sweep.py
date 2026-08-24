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

Protocol (v2 — improved after the first sweep showed DPSS thermal-transient
noise and a 2.5x max-power gap vs the lab test)
---------------------------------------------------------------
1. **Warm-up phase**: energize the laser at a moderate voltage (default 3 V)
   for a configurable duration (default 180 s) before sweeping. The
   LRS-0561 DPSS crystal warms up from pump-diode heat dissipation during
   *emission* — "PSU on at 0 V for days" leaves the crystal cold. A cold
   crystal causes thermal-lensing drift during the sweep (non-monotonic
   points, rolloff at high V). 2-3 min at 3 V is enough; the spec sheet's
   10-15 min is conservative.
2. **Settling time**: after writing each voltage, wait a configurable delay
   (default 2 s) before prompting for the reading, so the power meter
   averaging and the DPSS thermal response settle.
3. **Multi-sample averaging**: take N readings per voltage (default 3),
   discard the first (let the meter settle further), average the rest.
   Reduces single-reading noise (the first sweep had a 3.0 V dip + 3.25 V
   jump that looked like un-settled readings).
4. **Hysteresis check (ascending + descending)**: sweep 0 -> max, then
   max -> 0, recording the direction. DPSS thermal behavior often shows
   hysteresis (ascending != descending at the same V) — the CSV's
   ``direction`` column lets the follow-up fit detect and handle it.

Power-meter setup (Newport 1918-C + 818-SL) — check BEFORE running
------------------------------------------------------------------
- Set the 1918-C wavelength to 561 nm (Lambda key -> custom wavelength).
  A wrong wavelength applies the wrong responsivity correction.
- Center the beam on the 818-SL crosshair; the clear aperture is only
  10.3 mm. A beam that overfills or drifts off-center at high power
  under-reads systematically (the first sweep's 95 mW peak vs 236.6 mW
  lab test is consistent with ~63% of the beam hitting the sensor).
- Verify the Beam Attenuator setting matches the physical OD3 attenuator
  (likely ON — you're reading mW, not uW).

Safety (AGENTS.md Sec.2 — Class IIIB laser)
-------------------------------------------
- Starts at 0 V and ends at 0 V (laser off).
- Every DAQ write is clamped to [0, 5] V.
- The operator confirms before the warm-up and before the sweep begins;
  after that the sweep is semi-automated (settling delays + repeated
  prompts) but the operator is present with the power meter and PPE.
- Ctrl-C at any prompt aborts safely (laser driven to 0 V in finally).

Usage (on the rig, with LIGHTSHEET_HW=1)
----------------------------------------
    uv run python test/laser1_calibration_sweep.py
    uv run python test/laser1_calibration_sweep.py --step 0.5 --max-volts 5.0
    uv run python test/laser1_calibration_sweep.py --warmup-volts 3.0 --warmup-secs 180
    uv run python test/laser1_calibration_sweep.py --samples 5 --settle-secs 3
    uv run python test/laser1_calibration_sweep.py --no-descending   # ascending only
    uv run python test/laser1_calibration_sweep.py --output test/laser1_calibration.csv

On the Mac (no hardware), exits 1 with a message to run on the rig — the
conftest nidaqmx stub makes ``Task()`` raise, which this script detects.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
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


def _prompt_reading(volts: float, sample: int, n_samples: int) -> float | None:
    """Prompt the operator for one power-meter mW reading at ``volts``.

    Returns the float mW, or None to skip this sample, or raises
    KeyboardInterrupt to quit early. Empty input = skip this sample.
    """
    label = f"sample {sample}/{n_samples}" if n_samples > 1 else "reading"
    while True:
        raw = input(
            f"  V={volts:.3f}  {label}: enter power-meter mW "
            f"(Enter=skip, s=skip, q=quit): "
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


def _collect_point(
    terminal: str,
    volts: float,
    n_samples: int,
    settle_secs: float,
) -> float | None:
    """Energize at ``volts``, settle, collect ``n_samples`` readings, return
    the average (discarding the first sample as a further-settling throwaway
    when n_samples > 1). Returns None if all samples are skipped.

    The laser stays energized across the samples (no zeroing between them) so
    the DPSS thermal state is consistent within a point. The caller zeros the
    laser after the point is recorded.
    """
    _write_voltage(terminal, volts)
    if settle_secs > 0:
        print(f"     settling {settle_secs:.1f} s ...")
        time.sleep(settle_secs)
    readings: list[float] = []
    for i in range(1, n_samples + 1):
        reading = _prompt_reading(volts, i, n_samples)
        if reading is None:
            print(f"     (sample {i} skipped)")
            continue
        readings.append(reading)
        if i < n_samples:
            print(f"     recorded sample {i}: {reading:.3f} mW")
    if not readings:
        return None
    # Discard the first reading as a further-settling throwaway when we have
    # more than one — the first reading after the settle delay still catches
    # the tail of the thermal/meter transient.
    if len(readings) > 1:
        discarded = readings.pop(0)
        print(f"     (discarded first sample {discarded:.3f} mW as throwaway)")
    avg = float(np.mean(readings))
    print(
        f"     -> averaged {len(readings)} sample(s): {avg:.3f} mW "
        f"(raw: {', '.join(f'{r:.3f}' for r in readings)})"
    )
    return avg


def _run_pass(
    terminal: str,
    voltages: list[float],
    direction: str,
    n_samples: int,
    settle_secs: float,
    pairs: list[tuple[float, float, str]],
) -> None:
    """Run one sweep pass (ascending or descending) over ``voltages``,
    appending (V, mW, direction) tuples to ``pairs``."""
    print(f"\n  === {direction.upper()} pass: {len(voltages)} points ===\n")
    for volts in voltages:
        print(f"  -> {volts:.3f} V ({direction})")
        try:
            reading = _collect_point(terminal, volts, n_samples, settle_secs)
        except KeyboardInterrupt:
            raise
        if reading is None:
            print("     (point skipped entirely)")
            _write_voltage(terminal, 0.0)
            continue
        pairs.append((round(float(volts), 6), round(reading, 6), direction))
        print(f"     recorded: {volts:.3f} V -> {reading:.3f} mW ({direction})")
        # Zero between points so the laser is not left energized while the
        # operator prepares the next reading. Re-energize at the next point.
        _write_voltage(terminal, 0.0)


def _warmup(
    terminal: str,
    warmup_volts: float,
    warmup_secs: float,
) -> None:
    """Energize the laser at ``warmup_volts`` for ``warmup_secs`` to
    thermally stabilize the DPSS crystal before sweeping. The operator
    confirms before the warm-up begins (Class IIIB safety)."""
    if warmup_secs <= 0 or warmup_volts <= 0:
        print("  Warm-up skipped (warmup-volts or warmup-secs is 0).")
        return
    print(
        f"\n  WARM-UP: energizing at {warmup_volts:.2f} V for "
        f"{warmup_secs:.0f} s to thermally stabilize the DPSS crystal.\n"
        f"  (The LRS-0561 crystal warms up from pump-diode heat during "
        f"emission;\n   'PSU on at 0 V' leaves it cold. 2-3 min at 3 V is "
        f"enough.)\n"
    )
    input("  Press Enter to start the warm-up (Ctrl-C to abort)... ")
    _write_voltage(terminal, warmup_volts)
    print(f"  Laser at {warmup_volts:.2f} V. Warm-up timer: {warmup_secs:.0f} s.")
    try:
        # Countdown so the operator sees progress and can abort with Ctrl-C.
        remaining = warmup_secs
        while remaining > 0:
            chunk = min(10.0, remaining)
            time.sleep(chunk)
            remaining -= chunk
            if remaining > 0:
                print(f"    {remaining:.0f} s remaining ...")
    except KeyboardInterrupt:
        print("\n  Warm-up aborted by operator. Proceeding to sweep.")
    finally:
        _write_voltage(terminal, 0.0)
        print("  Warm-up complete. Laser at 0 V.")


def run_sweep(
    terminal: str,
    step: float,
    max_volts: float,
    output: str,
    warmup_volts: float,
    warmup_secs: float,
    n_samples: int,
    settle_secs: float,
    descending: bool,
) -> int:
    """Run the interactive sweep. Returns 0 on success, 1 on abort."""
    max_volts = max(0.0, min(float(max_volts), MAX_VOLTS_HARD_LIMIT))
    step = max(0.05, float(step))
    ascending = list(np.arange(0.0, max_volts + 1e-9, step))
    # Always include the exact max-volts endpoint even if float rounding
    # from arange drops it.
    if ascending and not abs(ascending[-1] - max_volts) < 1e-6:
        ascending.append(max_volts)
    ascending = [round(float(v), 6) for v in ascending]
    # Descending pass: max -> 0, excluding the endpoints already covered by
    # the ascending pass (avoid double-measuring 0 and max). Reversed inner
    # points only.
    descending_v = (
        [round(float(v), 6) for v in reversed(ascending[1:-1])]
        if descending and len(ascending) > 2
        else []
    )

    print("=" * 70)
    print("LASER 1 V->mW CALIBRATION SWEEP (v2) — CLASS IIIB LASER")
    print("=" * 70)
    print("  Diode:  LRS-0561-PFO-00200-03 (561 nm DPSS)")
    print("  PSU:    Laserglow PSU-H-LED (0-5 V analog modulation)")
    print("  Meter:  Newport 1918-C + 818-SL (set lambda=561nm, center beam)")
    print(f"  DAQ AO: {terminal}")
    print(f"  Steps:  {len(ascending)} ascending points, 0.000 V to "
          f"{max_volts:.3f} V (step {step:.3f} V)")
    if descending_v:
        print(f"          + {len(descending_v)} descending points "
              f"(hysteresis check)")
    print(f"  Warmup: {warmup_volts:.2f} V for {warmup_secs:.0f} s")
    print(f"  Sample: {n_samples} per point, {settle_secs:.1f} s settle, "
          f"first thrown away")
    print(f"  Output: {output}")
    print()
    print("  WARNING: Class IIIB laser. Wear appropriate PPE. Confirm the")
    print("  beam path is clear and the power meter is positioned BEFORE")
    print("  pressing Enter. Ctrl-C at any prompt aborts safely (laser -> 0 V).")
    print()
    input("  Press Enter when ready to begin (Ctrl-C to abort)... ")

    # Start at 0 V (laser off) so the sweep begins from a known-safe state.
    _write_voltage(terminal, 0.0)

    # Warm-up phase (thermally stabilize the DPSS crystal).
    _warmup(terminal, warmup_volts, warmup_secs)

    pairs: list[tuple[float, float, str]] = []
    try:
        _run_pass(terminal, ascending, "ascending", n_samples, settle_secs, pairs)
        if descending_v:
            _run_pass(
                terminal, descending_v, "descending", n_samples, settle_secs, pairs
            )
    except KeyboardInterrupt:
        print("\n  Sweep aborted by operator. Writing partial results.")
    finally:
        # Always end at 0 V (laser off) — even on abort.
        _write_voltage(terminal, 0.0)
        print("  Laser driven to 0 V (off).")

    if not pairs:
        print("  No readings recorded — nothing to write.")
        return 1

    _write_csv(output, pairs)
    print(f"\n  Wrote {len(pairs)} (V, mW, direction) rows to {output}")
    print("  Next: run /gsd-quick to fit this CSV into a "
          "'Laser1 Calibration Curve' config value.")
    return 0


def _write_csv(
    output: str, pairs: list[tuple[float, float, str]]
) -> None:
    """Write the (V, mW, direction) rows to ``output`` as CSV with a comment
    header. The comment header records the date and hardware so the
    follow-up parsing task has provenance. The data rows are
    ``voltage_v,power_mw,direction`` — direction is 'ascending' or
    'descending' so the fit can detect/handle hysteresis.

    ASCII-only header (the v1 script's em-dash got mangled on the Windows
    codepage, producing a non-UTF8 byte in the CSV).
    """
    with open(output, "w", newline="") as f:
        f.write(
            f"# Laser 1 V->mW calibration sweep - {datetime.now().isoformat()}\n"
            f"# Diode: LRS-0561-PFO-00200-03 (561 nm DPSS)\n"
            f"# PSU: Laserglow PSU-H-LED (0-5 V analog modulation)\n"
            f"# Meter: Newport 1918-C + 818-SL (lambda=561nm)\n"
            f"# Generated by test/laser1_calibration_sweep.py (v2)\n"
        )
        writer = csv.writer(f)
        writer.writerow(["voltage_v", "power_mw", "direction"])
        for v, mw, direction in pairs:
            writer.writerow([f"{v:.6f}", f"{mw:.6f}", direction])


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Manual Laser 1 V->mW calibration sweep (rig only, v2). "
        "Sweeps the DAQ AO voltage with a warm-up phase, settling delays, "
        "multi-sample averaging, and an optional descending hysteresis "
        "check. Records operator-entered power-meter readings to a CSV.",
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
    parser.add_argument(
        "--warmup-volts",
        type=float,
        default=3.0,
        help="Warm-up voltage in V (default: 3.0, 0 = skip warm-up)",
    )
    parser.add_argument(
        "--warmup-secs",
        type=float,
        default=180.0,
        help="Warm-up duration in s (default: 180, 0 = skip warm-up)",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=3,
        help="Samples per point (default: 3, first thrown away as throwaway)",
    )
    parser.add_argument(
        "--settle-secs",
        type=float,
        default=2.0,
        help="Settling delay after each voltage write, before prompting "
        "(default: 2.0)",
    )
    parser.add_argument(
        "--no-descending",
        action="store_true",
        help="Skip the descending hysteresis-check pass (ascending only)",
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
        warmup_volts=args.warmup_volts,
        warmup_secs=args.warmup_secs,
        n_samples=max(1, args.samples),
        settle_secs=max(0.0, args.settle_secs),
        descending=not args.no_descending,
    )


if __name__ == "__main__":
    sys.exit(main())
