"""Automated Laser 1 V->mW calibration sweep (PM100D auto-read, rig only).

This is NOT a pytest test — it is a manual calibration utility in the same
convention as the legacy ``test/daqmx.py`` / ``test/h5test.py`` scripts
(AGENTS.md Sec.5). It is NOT imported by the app and NOT collected by pytest
(the filename lacks the ``test_`` prefix).

Purpose
-------
Sweep the Laser 1 DAQ analog output (``/Dev7/ao0``) from 0 V to 5 V in
fine-grained steps. At each voltage the power is read AUTOMATICALLY from a
Thorlabs PM100D power meter (with S245C thermal sensor) via the HAL
``IPowerMeter`` ABC. The (V, mW, direction) rows are written to a CSV that
the follow-up task parses into a ``Laser1 Calibration Curve`` config value.

This is the v4 protocol — uses the HAL-layer PM100D driver and adds a
zero/dark-offset step before the sweep. The v3 protocol used a standalone
ctypes wrapper in test/pm100d.py; v4 moves the driver into the HAL layer
(``lightsheet/hal/real/pm100d.py``) for consistency with the other device
families.

Protocol (v4 — HAL PM100D + zero)
---------------------------------
1. **Zero/dark offset**: before the sweep, with the laser at 0V, the
   operator blocks the sensor and the script calls ``meter.zero()`` to
   perform a dark offset adjustment. This subtracts ambient light and
   sensor dark current from all subsequent readings.
2. **Warm-up phase**: energize the laser at 3V for 180s before sweeping
   (DPSS crystal thermal stabilization). Configurable.
3. **Settling time**: after writing each voltage, wait 2s before reading
   (S245C thermal sensor has ~0.6s response time; 2s is conservative).
4. **Multi-sample averaging**: 5 samples per point, first discarded, rest
   averaged. The S245C thermal sensor has some noise at low power; averaging
   reduces it.
5. **Hysteresis check**: ascending 0->max then descending max->0, with a
   direction column in the CSV.

Power meter: Thorlabs PM100D + S245C thermal surface absorber
--------------------------------------------------------------
- S245C: thermal pile, flat spectral response 190nm-20um, no saturation
  (unlike the 818-SL photodiode which saturated at ~75mW). The S245C gives
  the TRUE absolute power.
- Aperture: large enough to catch the full beam at <1cm distance.
- Wavelength set to 561nm (minimal effect on thermal sensor, but correct).
- The PM100D is accessed via the HAL ``IPowerMeter`` ABC
  (``lightsheet/hal/real/pm100d.py``), which wraps the TLPMX DLL via ctypes.

Safety (AGENTS.md Sec.2 — Class IIIB laser)
-------------------------------------------
- Starts at 0V and ends at 0V (laser off).
- Every DAQ write is clamped to [0, 5] V.
- The operator confirms before the zero, warm-up, and sweep begins;
  after that the sweep is automated but the operator is present with PPE.
- Ctrl-C at any time aborts safely (laser driven to 0V in finally).

Usage (on the rig, with LIGHTSHEET_HW=1)
----------------------------------------
    uv run python test/laser1_calibration_sweep.py
    uv run python test/laser1_calibration_sweep.py --step 0.1 --samples 5
    uv run python test/laser1_calibration_sweep.py --warmup-secs 300
    uv run python test/laser1_calibration_sweep.py --no-descending
    uv run python test/laser1_calibration_sweep.py --output test/laser1_calibration.csv
    uv run python test/laser1_calibration_sweep.py --skip-zero

On the Mac (no hardware), exits 1 with a message to run on the rig.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from datetime import datetime

import numpy as np

# nidaqmx: Mac guard (conftest stub makes Task() raise on Mac).
try:
    import nidaqmx
except Exception as exc:  # pragma: no cover — environment-dependent
    print(
        "ERROR: nidaqmx is not available. This script must be run on the rig "
        f"with LIGHTSHEET_HW=1. Cause: {exc}",
        file=sys.stderr,
    )
    sys.exit(1)

# HAL-layer PM100D driver. Rig-only — the DLL is Windows-only and the
# PM100D must be physically connected. The import succeeds on the Mac
# (ctypes is stdlib) but open() fails clearly on non-Windows.
from lightsheet.hal import PM100D, PM100DError, PM100DNotConnected
from lightsheet.hal.real.pm100d import is_pm100d_available

MAX_VOLTS_HARD_LIMIT = 5.0
DEFAULT_TERMINAL = "/Dev7/ao0"


def _write_voltage(terminal: str, volts: float) -> None:
    """Write ``volts`` (clamped to [0, 5]) to the DAQ AO channel."""
    volts = max(0.0, min(float(volts), MAX_VOLTS_HARD_LIMIT))
    with nidaqmx.Task(new_task_name="laser1_calibration") as task:
        task.ao_channels.add_ao_voltage_chan(terminal)
        task.write(np.array([volts]), auto_start=True)


def _run_pass(
    terminal: str,
    voltages: list[float],
    direction: str,
    n_samples: int,
    settle_secs: float,
    meter: PM100D,
    pairs: list[tuple[float, float, str]],
) -> None:
    """Run one sweep pass (ascending or descending), auto-reading the PM100D."""
    print(f"\n  === {direction.upper()} pass: {len(voltages)} points ===\n")
    for i, volts in enumerate(voltages):
        pct = (i + 1) / len(voltages) * 100
        print(
            f"  [{pct:5.1f}%] {direction} V={volts:.3f} ... ",
            end="",
            flush=True,
        )
        _write_voltage(terminal, volts)
        if settle_secs > 0:
            time.sleep(settle_secs)
        try:
            power_w = meter.read_averaged(n_samples, delay_s=0.5)
        except PM100DError as exc:
            print(f"METER ERROR: {exc}")
            _write_voltage(terminal, 0.0)
            continue
        power_mw = power_w * 1000.0
        pairs.append(
            (round(float(volts), 6), round(power_mw, 6), direction)
        )
        print(f"{power_mw:7.2f} mW")
        # Zero between points so the laser is not left energized while the
        # thermal sensor settles to the next voltage.
        _write_voltage(terminal, 0.0)


def _warmup(terminal: str, warmup_volts: float, warmup_secs: float) -> None:
    """Energize the laser at ``warmup_volts`` for ``warmup_secs``."""
    if warmup_secs <= 0 or warmup_volts <= 0:
        print("  Warm-up skipped.")
        return
    print(
        f"\n  WARM-UP: {warmup_volts:.2f} V for {warmup_secs:.0f} s "
        f"(DPSS crystal thermal stabilization).\n"
    )
    input("  Press Enter to start the warm-up (Ctrl-C to abort)... ")
    _write_voltage(terminal, warmup_volts)
    print(f"  Laser at {warmup_volts:.2f} V. Warm-up: {warmup_secs:.0f} s.")
    try:
        remaining = warmup_secs
        while remaining > 0:
            chunk = min(10.0, remaining)
            time.sleep(chunk)
            remaining -= chunk
            if remaining > 0:
                print(f"    {remaining:.0f} s remaining ...")
    except KeyboardInterrupt:
        print("\n  Warm-up aborted. Proceeding to sweep.")
    finally:
        _write_voltage(terminal, 0.0)
        print("  Warm-up complete. Laser at 0 V.")


def _do_zero(meter: PM100D) -> None:
    """Perform a zero/dark offset adjustment on the PM100D.

    The operator must block the sensor (cap it or block the beam path)
    before pressing Enter. The meter measures the dark current and
    subtracts it from all subsequent readings.
    """
    print("\n  ZERO/DARK OFFSET ADJUSTMENT")
    print("  Block the sensor (cap it or block the beam path) so no light")
    print("  reaches the detector. The meter will measure the dark current")
    print("  and subtract it from all subsequent readings.")
    print()
    input("  Press Enter when the sensor is blocked (Ctrl-C to abort)... ")
    try:
        meter.zero()
        print("  Dark offset adjustment complete.")
    except PM100DError as exc:
        print(f"  WARNING: zero adjustment failed: {exc}")
        print("  Continuing without zero — readings may have an offset.")
    print("  Unblock the sensor for the sweep.")
    input("  Press Enter when the sensor is unblocked and ready ... ")


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
    wavelength_nm: float,
    skip_zero: bool,
) -> int:
    """Run the automated sweep. Returns 0 on success, 1 on abort."""
    max_volts = max(0.0, min(float(max_volts), MAX_VOLTS_HARD_LIMIT))
    step = max(0.01, float(step))
    ascending = list(np.arange(0.0, max_volts + 1e-9, step))
    if ascending and not abs(ascending[-1] - max_volts) < 1e-6:
        ascending.append(max_volts)
    ascending = [round(float(v), 6) for v in ascending]
    descending_v = (
        [round(float(v), 6) for v in reversed(ascending[1:-1])]
        if descending and len(ascending) > 2
        else []
    )

    print("=" * 70)
    print("LASER 1 V->mW CALIBRATION SWEEP (v4 auto, HAL PM100D) — CLASS IIIB")
    print("=" * 70)
    print("  Diode:  LRS-0561-PFO-00200-03 (561 nm DPSS)")
    print("  PSU:    Laserglow PSU-H-LED (0-5 V analog modulation)")
    print(f"  Meter:  Thorlabs PM100D + S245C thermal (lambda={wavelength_nm}nm)")
    print(f"  DAQ AO: {terminal}")
    print(f"  Steps:  {len(ascending)} ascending, 0.000 V to "
          f"{max_volts:.3f} V (step {step:.3f} V)")
    if descending_v:
        print(f"          + {len(descending_v)} descending (hysteresis check)")
    print(f"  Warmup: {warmup_volts:.2f} V for {warmup_secs:.0f} s")
    print(f"  Sample: {n_samples} per point, {settle_secs:.1f} s settle, "
          f"first thrown away")
    print(f"  Zero:   {'skipped' if skip_zero else 'dark offset before sweep'}")
    print(f"  Output: {output}")
    print()
    print("  WARNING: Class IIIB laser. Wear PPE. The sweep is automated")
    print("  but the laser energizes at each step. Ctrl-C aborts safely")
    print("  (laser -> 0 V).")
    print()
    input("  Press Enter when ready to begin (Ctrl-C to abort)... ")

    _write_voltage(terminal, 0.0)

    # Open the PM100D session.
    print(f"\n  Opening PM100D session (wavelength={wavelength_nm}nm) ...")
    try:
        meter = PM100D(wavelength_nm=wavelength_nm, reset=False)
        meter.open()
    except PM100DNotConnected as exc:
        print(f"\n  ERROR: {exc}")
        return 1
    except PM100DError as exc:
        print(f"\n  ERROR: {exc}")
        return 1
    print("  PM100D connected.")

    # Sanity check: read ambient/zero power before zeroing.
    ambient = meter.read_power_mw()
    print(f"  Ambient reading (laser at 0V, pre-zero): {ambient:.3f} mW")

    pairs: list[tuple[float, float, str]] = []
    try:
        # Zero/dark offset adjustment (before warm-up so the sensor is cold
        # and stable, and the laser is definitely off).
        if not skip_zero:
            _do_zero(meter)
            # Re-check ambient after zeroing.
            post_zero = meter.read_power_mw()
            print(f"  Ambient reading (post-zero): {post_zero:.3f} mW")

        # Warm-up phase.
        _warmup(terminal, warmup_volts, warmup_secs)

        # Sweep passes.
        _run_pass(
            terminal, ascending, "ascending",
            n_samples, settle_secs, meter, pairs,
        )
        if descending_v:
            _run_pass(
                terminal, descending_v, "descending",
                n_samples, settle_secs, meter, pairs,
            )
    except KeyboardInterrupt:
        print("\n\n  Sweep aborted by operator. Writing partial results.")
    finally:
        _write_voltage(terminal, 0.0)
        print("  Laser driven to 0 V (off).")
        meter.close()
        print("  PM100D session closed.")

    if not pairs:
        print("  No readings recorded — nothing to write.")
        return 1

    _write_csv(output, pairs)
    print(f"\n  Wrote {len(pairs)} (V, mW, direction) rows to {output}")
    print("  Next: fit the curve and update config.ini "
          "'Laser1 Calibration Curve'.")
    return 0


def _write_csv(
    output: str, pairs: list[tuple[float, float, str]]
) -> None:
    """Write the (V, mW, direction) rows to ``output`` as CSV."""
    with open(output, "w", newline="") as f:
        f.write(
            f"# Laser 1 V->mW calibration sweep (v4 auto, HAL PM100D) - "
            f"{datetime.now().isoformat()}\n"
            f"# Diode: LRS-0561-PFO-00200-03 (561 nm DPSS)\n"
            f"# PSU: Laserglow PSU-H-LED (0-5 V analog modulation)\n"
            f"# Meter: Thorlabs PM100D + S245C thermal sensor\n"
            f"# Generated by test/laser1_calibration_sweep.py (v4)\n"
        )
        writer = csv.writer(f)
        writer.writerow(["voltage_v", "power_mw", "direction"])
        for v, mw, direction in pairs:
            writer.writerow([f"{v:.6f}", f"{mw:.6f}", direction])


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Automated Laser 1 V->mW calibration sweep (v4, HAL "
        "PM100D auto-read). Sweeps the DAQ AO voltage and reads power from "
        "a Thorlabs PM100D + S245C thermal sensor via the HAL IPowerMeter "
        "ABC.",
    )
    parser.add_argument(
        "--terminal", default=DEFAULT_TERMINAL,
        help=f"DAQ AO terminal (default: {DEFAULT_TERMINAL})",
    )
    parser.add_argument(
        "--step", type=float, default=0.1,
        help="Voltage step in V (default: 0.1, min: 0.01)",
    )
    parser.add_argument(
        "--max-volts", type=float, default=5.0,
        help="Maximum voltage in V, clamped to 5.0 (default: 5.0)",
    )
    parser.add_argument(
        "--output", default="test/laser1_calibration.csv",
        help="Output CSV path (default: test/laser1_calibration.csv)",
    )
    parser.add_argument(
        "--warmup-volts", type=float, default=3.0,
        help="Warm-up voltage in V (default: 3.0, 0 = skip)",
    )
    parser.add_argument(
        "--warmup-secs", type=float, default=180.0,
        help="Warm-up duration in s (default: 180, 0 = skip)",
    )
    parser.add_argument(
        "--samples", type=int, default=5,
        help="Samples per point (default: 5, first thrown away)",
    )
    parser.add_argument(
        "--settle-secs", type=float, default=2.0,
        help="Settling delay after each voltage write (default: 2.0)",
    )
    parser.add_argument(
        "--no-descending", action="store_true",
        help="Skip the descending hysteresis-check pass",
    )
    parser.add_argument(
        "--wavelength", type=float, default=561.0,
        help="Wavelength in nm for the PM100D (default: 561.0)",
    )
    parser.add_argument(
        "--skip-zero", action="store_true",
        help="Skip the dark offset adjustment before the sweep",
    )
    args = parser.parse_args()

    # Mac guard: probe the DAQ.
    try:
        with nidaqmx.Task(new_task_name="laser1_calibration_probe") as _probe:
            _probe.ao_channels.add_ao_voltage_chan(args.terminal)
    except Exception as exc:
        print(
            "ERROR: could not open a nidaqmx Task on the DAQ AO channel. "
            f"Run on the rig with LIGHTSHEET_HW=1. Cause: {exc}",
            file=sys.stderr,
        )
        return 1

    # PM100D guard: check the meter is available before starting.
    if not is_pm100d_available():
        print(
            "ERROR: Thorlabs PM100D not found. Install the Thorlabs OPM "
            "software (which installs TLPMX_64.dll) and connect the PM100D "
            "via USB. The Thorlabs OPM GUI should be able to connect to it.",
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
        wavelength_nm=args.wavelength,
        skip_zero=args.skip_zero,
    )


if __name__ == "__main__":
    sys.exit(main())
