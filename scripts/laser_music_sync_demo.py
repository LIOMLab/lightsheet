"""Standalone laser music-sync demo for the lightsheet microscope.

Plays a WAV file and drives the two lasers through a promotional sequence
aligned to the "Laser" vocal hits in *Ray Volpe - Laserbeam (ÆON_MODE Remix)*.
The sequence is: L1 active just before the first hit, L2 (red) on the first
hit, L1 on the second, L2 on the third, and L2 continuing after the fourth.
Galvos and ETLs run a free Lissajous-like pattern through the whole event.

Use ``--demo`` to smoke-test the timing and patterns on macOS without hardware.

Example (real hardware, 10 mW per laser, cue at 44.89s):
    uv run python scripts/laser_music_sync_demo.py --yes

Example (mock hardware, no audio, fast-forward to the event):
    uv run python scripts/laser_music_sync_demo.py --demo --dry-run --stop-after-event
"""

from __future__ import annotations

import argparse
import logging
import math
import sys
import time
from pathlib import Path

from lightsheet.hal.bundle import DeviceBundle
from lightsheet.hal.interfaces import ILaser, ISigGen

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("laser_music_sync_demo")

# Default WAV and cue timings for Ray Volpe - Laserbeam (ÆON_MODE Remix)
DEFAULT_WAV = "/Users/frans/Downloads/Ray Volpe - Laserbeam (ÆON_MODE Remix).wav"
DEFAULT_LASER_START = 44.5
DEFAULT_LASER_END = 47.0
DEFAULT_LASER_CUES = [44.89, 45.16, 46.30, 46.31]


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
        "WARNING: This script energizes Class IIIB lasers and moves galvos/ETLs.\n"
        "         Use --yes to proceed, --dry-run to simulate, or --demo for mock.\n"
    )
    raise SystemExit("Aborting: re-run with --yes after reading the safety note above.")


def initialize_hardware(bundle: DeviceBundle) -> None:
    """Open ETLs and both lasers."""
    bundle.etls.open()
    bundle.etls.set_analog_mode()
    for laser in bundle.lasers:
        laser.open()
        if laser.error:
            logger.warning("%s open warning: %s", laser.label, laser.error_message)
    logger.info("Hardware initialized")


def shutdown_hardware(bundle: DeviceBundle) -> None:
    """Synchronously kill both lasers and close ETLs."""
    for laser in bundle.lasers:
        laser.off()
        laser.close()
    bundle.etls.close()
    logger.info("Hardware shutdown complete.")


def play_audio(
    wav_path: Path, dry_run: bool, start_offset: float = 0.0
) -> tuple[float, float]:
    """Load the WAV and start playback. Returns (start_timestamp, duration).

    In dry-run the clock is fast-forwarded by ``start_offset`` song seconds so
    the laser event is reached in a few real seconds.
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
    siggen: ISigGen, now: float, t: float, args: argparse.Namespace
) -> None:
    """Compute and write one galvo/ETL setpoint for the current time."""
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
    bundle: DeviceBundle,
    t0: float,
    duration: float,
    args: argparse.Namespace,
) -> None:
    """Switch lasers through the cue sequence: L1, L2, L1, L2, L2."""
    active_laser: ILaser | None = None
    pattern_last = 0.0
    delay = args.laser_delay
    phase_times = [
        args.laser_window_start - delay,
        *(cue - delay for cue in args.laser_cues),
        args.laser_window_end - delay,
    ]
    laser_sequence = [0, 1, 0, 1, 1]
    stop_time = (
        phase_times[-1] + 0.5 if duration == 0.0 or args.stop_after_event else duration
    )
    phase = -10

    while True:
        now_song = time.perf_counter() - t0
        new_phase = -2
        for i, boundary in enumerate(phase_times):
            if now_song < boundary:
                new_phase = i - 1
                break

        if new_phase == -1:
            pass
        elif new_phase == -2:
            if active_laser is not None:
                active_laser.off()
                active_laser = None
                logger.info("LASER EVENT END @ %.3f s", now_song)
        elif new_phase != phase:
            next_laser = bundle.lasers[laser_sequence[new_phase]]
            if next_laser is not active_laser:
                if active_laser is not None:
                    active_laser.off()
                active_laser = next_laser
                active_laser.on()
            else:
                active_laser = next_laser
            phase = new_phase
            logger.info(
                "PHASE %d @ %.3f s: %s",
                phase,
                now_song,
                active_laser.label,
            )

        if (
            active_laser is not None
            and (now_song - pattern_last) >= args.pattern_interval
        ):
            run_pattern(
                bundle.siggen,
                now_song,
                now_song - (args.laser_window_start - delay),
                args,
            )
            pattern_last = now_song

        if now_song >= stop_time:
            break
        time.sleep(0.01 if args.dry_run and args.demo else 0.001)

    if active_laser is not None:
        active_laser.off()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync microscope lasers to music cues."
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
        "--laser1-power", type=float, default=10.0, help="L1 (555 nm) power in mW"
    )
    parser.add_argument(
        "--laser2-power", type=float, default=10.0, help="L2 (647 nm) power in mW"
    )
    parser.add_argument(
        "--laser-cues",
        type=float,
        nargs="+",
        default=DEFAULT_LASER_CUES,
        help="Song times (s) for each 'Laser' vocal hit",
    )
    parser.add_argument(
        "--laser-window-start",
        type=float,
        default=DEFAULT_LASER_START,
        help="Song time (s) to start the laser event (L1 pre-period)",
    )
    parser.add_argument(
        "--laser-window-end",
        type=float,
        default=DEFAULT_LASER_END,
        help="Song time (s) to end the final L2 post-period",
    )
    parser.add_argument(
        "--laser-delay",
        type=float,
        default=0.0,
        help="Command offset (s): positive turns on earlier to compensate latency",
    )
    parser.add_argument(
        "--stop-after-event",
        action="store_true",
        help="Exit after the laser event instead of playing the whole song",
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
    initialize_hardware(bundle)
    laser1, laser2 = bundle.lasers[0], bundle.lasers[1]
    laser1.set_power(args.laser1_power)
    laser2.set_power(args.laser2_power)
    logger.info(
        "Staged %s at %.3f mW (max %.3f mW)",
        laser1.label,
        laser1.power,
        laser1.max_power,
    )
    logger.info(
        "Staged %s at %.3f mW (max %.3f mW)",
        laser2.label,
        laser2.power,
        laser2.max_power,
    )

    try:
        start_offset = max(0.0, args.laser_window_start - 1.0) if args.dry_run else 0.0
        t0, duration = play_audio(args.wav, args.dry_run, start_offset)
        run_sync_loop(bundle, t0, duration, args)
    except Exception:
        logger.exception("Demo aborted")
        return 1
    finally:
        shutdown_hardware(bundle)
        if not args.dry_run:
            import sounddevice as sd

            sd.stop()

    logger.info("Demo finished.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
