"""Standalone laser music-sync demo for the lightsheet microscope.

Plays a WAV file and fires the selected laser for a ~2 s window around the
"Laser" vocal hits, while the galvos and ETLs run a free Lissajous-like
pattern. Designed to be run on the Windows rig; use ``--demo`` to smoke-test
the timing and patterns on macOS without hardware.

Example (real hardware, laser 1, 10 mW):
    uv run python scripts/laser_music_sync_demo.py --yes --laser-power 10

Example (mock hardware, no audio, 4x fast timing for quick iteration):
    uv run python scripts/laser_music_sync_demo.py --demo --dry-run
"""

from __future__ import annotations

import argparse
import logging
import math
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lightsheet.hal.bundle import DeviceBundle
    from lightsheet.hal.interfaces import ILaser, ISigGen

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("laser_music_sync_demo")

# Default "Laser" vocal hits in Ray Volpe - Laserbeam (ÆON_MODE Remix)
DEFAULT_WAV = "/Users/frans/Downloads/Ray Volpe - Laserbeam (ÆON_MODE Remix).wav"
DEFAULT_LASER_START = 44.5
DEFAULT_LASER_END = 46.5


def build_bundle(demo: bool) -> DeviceBundle:
    """Resolve the real HAL bundle, or the mock bundle in demo mode."""
    if demo:
        from lightsheet.__main__ import _build_demo_bundle

        return _build_demo_bundle()

    if sys.platform != "win32":
        raise RuntimeError(
            "Real hardware mode is only supported on Windows. "
            "Run with --demo to exercise the script on this platform."
        )

    from lightsheet.hal.registry import DeviceRegistry

    return DeviceRegistry("hardware_inventory.yaml", "config.ini").resolve()


def confirm_real_mode(args: argparse.Namespace) -> None:
    """Require explicit acknowledgement before energizing the laser."""
    if args.demo or args.dry_run or args.yes:
        return
    print(
        "\n"
        "WARNING: This script energizes a Class IIIB laser and moves galvos/ETLs.\n"
        "         Use --yes to proceed, --dry-run to simulate, or --demo for mock.\n"
    )
    # No interactive input path in automated use; require --yes.
    raise SystemExit("Aborting: re-run with --yes after reading the safety note above.")


def initialize_hardware(
    bundle: DeviceBundle, laser_index: int
) -> tuple[ILaser, ISigGen]:
    """Open ETLs and the selected laser; return (laser, siggen)."""
    laser = bundle.lasers[laser_index]
    siggen = bundle.siggen
    bundle.etls.open()
    bundle.etls.set_analog_mode()
    laser.open()
    logger.info("Hardware initialized: %s", laser.label)
    return laser, siggen


def shutdown_hardware(bundle: DeviceBundle, laser: ILaser) -> None:
    """Synchronously kill the laser and close ETLs."""
    laser.off()
    laser.close()
    bundle.etls.close()
    logger.info("Hardware shutdown complete.")


def play_audio(
    wav_path: Path, dry_run: bool, start_offset: float = 0.0
) -> tuple[float, float]:
    """Load the WAV and start playback. Returns (start_timestamp, duration).

    In dry-run the clock is fast-forwarded by ``start_offset`` song seconds so
    the laser window is reached in roughly (window + 1) real seconds.
    """
    if dry_run:
        logger.info(
            "[dry-run] Skipping audio playback; song time starts at %.2f s",
            start_offset,
        )
        return time.perf_counter() - start_offset, 0.0

    import sounddevice as sd
    import soundfile as sf

    data, samplerate = sf.read(str(wav_path), dtype="float32")
    duration = len(data) / samplerate
    sd.play(data, samplerate)
    logger.info("Playing %s (%.2f s, %d Hz)", wav_path, duration, samplerate)
    return time.perf_counter(), duration


def run_pattern(
    siggen: ISigGen, now: float, elapsed: float, args: argparse.Namespace
) -> None:
    """Compute and write one galvo/ETL setpoint for the current time."""
    t = elapsed
    left_g = args.galvo_offset + args.galvo_amp * math.sin(
        2 * math.pi * args.pattern_freq * t
    )
    right_g = args.galvo_offset + args.galvo_amp * math.cos(
        2 * math.pi * args.pattern_freq * t
    )
    left_e = args.etl_offset + args.etl_amp * math.sin(
        2 * math.pi * args.pattern_freq * 0.3 * t + 0.25
    )
    right_e = args.etl_offset + args.etl_amp * math.cos(
        2 * math.pi * args.pattern_freq * 0.3 * t + 0.25
    )
    siggen.update_galvos(left_g, right_g)
    siggen.update_etls(left_e, right_e)
    logger.debug(
        "pattern @ %.3f s: galvo=(%.2f, %.2f) etl=(%.2f, %.2f)",
        now,
        left_g,
        right_g,
        left_e,
        right_e,
    )


def run_sync_loop(
    laser: ILaser,
    siggen: ISigGen,
    t0: float,
    duration: float,
    args: argparse.Namespace,
) -> None:
    """Main timing loop: laser ramps/strobes before/after the main window."""
    laser_on = False
    laser_done = False
    in_main = False
    last_update = 0.0
    main_start = args.laser_window_start - args.laser_delay
    main_end = args.laser_window_end - args.laser_delay
    event_start = main_start - args.pre_time
    event_end = main_end + args.post_time
    stop_time = event_end + 0.5 if duration == 0.0 else duration
    base_power = laser.power

    while True:
        now_song = time.perf_counter() - t0
        elapsed = now_song - event_start

        if not laser_on and not laser_done and now_song >= event_start:
            laser.set_power(0.0)
            laser.on()
            laser_on = True
            logger.info("LASER EVENT START @ %.3f s (song)", now_song)

        if laser_on and now_song >= event_end:
            laser.off()
            laser_on = False
            laser_done = True
            logger.info("LASER EVENT END @ %.3f s (song)", now_song)

        if laser_on:
            if not in_main and now_song >= main_start:
                laser.set_power(base_power)
                in_main = True
                logger.info("LASER DROP @ %.3f s (song)", now_song)

            if (now_song - last_update) >= args.pattern_interval:
                if now_song < main_start:
                    t = elapsed
                    ramp = t / args.pre_time
                    strobe = 0.5 + 0.5 * math.sin(2 * math.pi * 6.0 * t)
                    power = base_power * ramp * (0.5 + 0.5 * strobe)
                elif now_song < main_end:
                    power = base_power
                else:
                    t = now_song - main_end
                    ramp = 1.0 - t / args.post_time
                    strobe = 0.5 + 0.5 * math.sin(2 * math.pi * 4.0 * t)
                    power = base_power * ramp * (0.5 + 0.5 * strobe)
                laser.set_power(power)
                run_pattern(siggen, now_song, elapsed, args)
                last_update = now_song

        if now_song >= stop_time:
            break
        time.sleep(0.01 if args.dry_run and args.demo else 0.001)

    if laser_on:
        laser.off()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync microscope laser to a music cue."
    )
    parser.add_argument(
        "--wav", type=Path, default=Path(DEFAULT_WAV), help="WAV file to play"
    )
    parser.add_argument(
        "--demo", action="store_true", help="Use mock HAL (no hardware)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not play audio or energize hardware; print schedule",
    )
    parser.add_argument(
        "--yes", action="store_true", help="Acknowledge real laser emission and proceed"
    )
    parser.add_argument(
        "--laser-index",
        type=int,
        default=0,
        choices=[0, 1],
        help="Laser index (0 or 1)",
    )
    parser.add_argument(
        "--laser-power",
        type=float,
        default=10.0,
        help="Laser power in mW (clamped to max_power)",
    )
    parser.add_argument(
        "--laser-window-start",
        type=float,
        default=DEFAULT_LASER_START,
        help="Song time (s) to start laser window",
    )
    parser.add_argument(
        "--laser-window-end",
        type=float,
        default=DEFAULT_LASER_END,
        help="Song time (s) to end laser window",
    )
    parser.add_argument(
        "--laser-delay",
        type=float,
        default=0.0,
        help="Command offset (s): positive turns on earlier to compensate latency",
    )
    parser.add_argument(
        "--pre-time",
        type=float,
        default=2.0,
        help="Seconds of ramp/strobe before the laser window",
    )
    parser.add_argument(
        "--post-time",
        type=float,
        default=2.0,
        help="Seconds of ramp/strobe after the laser window",
    )
    parser.add_argument(
        "--pattern-interval",
        type=float,
        default=0.05,
        help="Galvo/ETL update interval (s)",
    )
    parser.add_argument(
        "--pattern-freq", type=float, default=2.0, help="Pattern frequency (Hz)"
    )
    parser.add_argument(
        "--galvo-amp", type=float, default=0.5, help="Galvo pattern amplitude (V)"
    )
    parser.add_argument(
        "--galvo-offset", type=float, default=0.5, help="Galvo pattern offset (V)"
    )
    parser.add_argument(
        "--etl-amp", type=float, default=0.3, help="ETL pattern amplitude (V)"
    )
    parser.add_argument(
        "--etl-offset", type=float, default=0.5, help="ETL pattern offset (V)"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    confirm_real_mode(args)

    if not args.dry_run and not args.wav.exists():
        logger.error("WAV file not found: %s", args.wav)
        return 1

    bundle = build_bundle(args.demo)
    laser, siggen = initialize_hardware(bundle, args.laser_index)
    laser.set_power(args.laser_power)
    logger.info(
        "Staged %s at %.3f mW (max %.3f mW)", laser.label, laser.power, laser.max_power
    )

    try:
        event_start = args.laser_window_start - args.pre_time - args.laser_delay
        start_offset = max(0.0, event_start) if args.dry_run else 0.0
        t0, duration = play_audio(args.wav, args.dry_run, start_offset)
        run_sync_loop(laser, siggen, t0, duration, args)
    except Exception:
        logger.exception("Demo aborted")
        return 1
    finally:
        shutdown_hardware(bundle, laser)
        if not args.dry_run:
            import sounddevice as sd

            sd.stop()

    logger.info("Demo finished.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
