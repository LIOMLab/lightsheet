"""ResumeSafetyGate — Qt-free pre-resume validation (D-06).

Pure Python, no Qt / no HAL imports: a resume discovered from anywhere must
pass this gate before hardware moves. The gate collects findings — it never
decides; the GUI layer's ``show_resume_safety_dialog`` reports every finding
to the operator and only an explicit Resume click lets the run proceed
(report-then-confirm; Cancel is the safe default).

Findings use ``ConfigValidationResult`` semantics:

- **errors** block resume outright (live config fails schema validation,
  remaining stack range exceeds stage travel limits, corrupt manifest data).
- **warnings** are reported but resumable (config-fingerprint diffs, motor
  drift, unopenable files that fall back to a ``_partN`` fileset).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from lightsheet.config_schema.validation import (
    ConfigValidationResult,
    collect_config_errors,
    load_sections_from_ini,
)
from lightsheet.resume.probe import (
    ResumeProbeError,
    _common_resume_plane,
    probe_hdf5,
    probe_zarr,
)

if TYPE_CHECKING:
    from lightsheet.hal.interfaces import IMotors
    from lightsheet.resume.manifest import ResumeManifest

logger = logging.getLogger(__name__)

DEFAULT_DRIFT_TOLERANCE_MM = 0.1

# Keys whose values are safety-relevant for the config-fingerprint diff:
# laser power ceilings and motor travel limits.
_SAFETY_KEY_MARKERS = ("max power", "limit high", "limit low")


@dataclass
class GateFindings(ConfigValidationResult):
    """``ConfigValidationResult`` plus the probe observations.

    ``observed_planes`` maps output-file path -> readable plane count.
    ``resume_plane`` is the common durable plane index across all formats
    (``min(cursor, observed)`` per cursor key), the value the resumed
    worker must start from.
    """

    observed_planes: dict[str, int] = field(default_factory=dict)
    resume_plane: int = 0


def collect_safety_config(
    baseline_path: str = "config.ini",
    overlay_path: str | None = "config.rig-specific.ini",
) -> dict[str, dict[str, str]]:
    """Snapshot the safety-relevant config keys for the manifest fingerprint.

    Extracts keys whose names carry a safety marker (laser max power,
    motor limit high/low) from the merged baseline+overlay sections.
    Returns ``{}`` when the baseline file is absent or unreadable.
    """
    if not Path(baseline_path).is_file():
        return {}
    try:
        sections = load_sections_from_ini(baseline_path, overlay_path)
    except Exception as e:
        logger.warning("collect_safety_config failed to load config: %s", e)
        return {}
    out: dict[str, dict[str, str]] = {}
    for section, entries in sections.items():
        keep = {
            k: v
            for k, v in entries.items()
            if v != "" and any(m in k.lower() for m in _SAFETY_KEY_MARKERS)
        }
        if keep:
            out[section] = keep
    return out


class ResumeSafetyGate:
    """Collects config-diff, motor-drift, travel-limit, and probe findings.

    Instantiated with a drift tolerance; ``from_manifest`` is the
    single-shot entry point the resume path calls.
    """

    def __init__(
        self, *, drift_tolerance_mm: float = DEFAULT_DRIFT_TOLERANCE_MM
    ) -> None:
        self.drift_tolerance_mm = float(drift_tolerance_mm)

    @classmethod
    def from_manifest(
        cls,
        manifest: ResumeManifest,
        live_config: dict[str, dict[str, Any]] | None,
        motors: IMotors | None,
        *,
        drift_tolerance_mm: float = DEFAULT_DRIFT_TOLERANCE_MM,
    ) -> GateFindings:
        """Collect every finding for a candidate resume.

        ``live_config`` is the merged sections dict from
        ``load_sections_from_ini``; ``None`` loads ``config.ini`` +
        ``config.rig-specific.ini`` from the working directory. ``motors``
        is the live motor bundle (``get_positions`` + ``horizontal``
        limit readback); ``None`` downgrades the hardware checks to
        warnings rather than errors — an unreadable readback is reported,
        never silently skipped.
        """
        findings = GateFindings()

        # --- (a) config-fingerprint diff -------------------------------
        if live_config is None:
            try:
                live_config = load_sections_from_ini(
                    "config.ini", "config.rig-specific.ini"
                )
            except Exception as e:
                findings.warnings.append(
                    f"Live config could not be loaded for the fingerprint "
                    f"diff: {e}"
                )
                live_config = {}
        if live_config:
            live_result = collect_config_errors(live_config)
            findings.errors.extend(
                f"[live config] {e}" for e in live_result.errors
            )
            findings.warnings.extend(
                f"[live config] {w}" for w in live_result.warnings
            )
            for section, entries in manifest.safety_config.items():
                live_section = live_config.get(section, {})
                for key, saved in entries.items():
                    live_val = live_section.get(key)
                    if live_val is None:
                        findings.warnings.append(
                            f"[{section}] {key}: manifest fingerprint "
                            f"recorded {saved!r} but the key is absent from "
                            f"the live config"
                        )
                    elif str(live_val) != str(saved):
                        findings.warnings.append(
                            f"[{section}] {key} changed since the "
                            f"acquisition: {saved!r} -> {live_val!r}"
                        )
        elif manifest.safety_config:
            findings.warnings.append(
                "Safety-config fingerprint could not be compared — the "
                "live config is unavailable"
            )

        # --- (d) per-format probes (before limits so resume_plane is
        # computed from the durable cursor, not the nominal one) ---------
        probes: dict[str, dict[str, int]] = {}
        for fmt, group in manifest.cursors.items():
            observed: dict[str, int] = {}
            for path in group:
                try:
                    if fmt == "hdf5":
                        n = probe_hdf5(path)
                    elif fmt == "zarr":
                        n_channels = max(1, len(manifest.wavelengths or []))
                        n = min(
                            probe_zarr(path, f"ch{c}")
                            for c in range(n_channels)
                        )
                    else:
                        continue
                except ResumeProbeError as e:
                    # Unopenable files are not fatal: set_files falls back
                    # to a _partN continuation fileset automatically. The
                    # missing observation still counts as 0 committed
                    # planes, which drives resume_plane to 0 — matching
                    # the fallback's fresh start.
                    findings.warnings.append(
                        f"{path} cannot be reopened ({e}) — resume falls "
                        f"back to a _partN continuation fileset"
                    )
                    continue
                observed[path] = n
                findings.observed_planes[path] = n
            probes[fmt] = observed
        if manifest.cursors:
            resume_plane, _ = _common_resume_plane(manifest, probes)
        else:
            resume_plane = manifest.start_plane
        findings.resume_plane = max(0, int(resume_plane))

        # --- (b) motor position readback vs recorded positions ---------
        if motors is None:
            if manifest.last_motor_positions:
                findings.warnings.append(
                    "Motor positions could not be read back — the drift "
                    "check was skipped"
                )
        else:
            try:
                positions = {
                    str(k): float(v) for k, v in motors.get_positions().items()
                }
            except Exception as e:
                positions = {}
                findings.warnings.append(
                    f"Motor position readback failed: {e}"
                )
            for key, saved in manifest.last_motor_positions.items():
                live = positions.get(key)
                if live is None:
                    findings.warnings.append(
                        f"{key}: recorded {saved:.3f} mm but the live "
                        f"readback is unavailable"
                    )
                    continue
                drift = live - saved
                if abs(drift) > drift_tolerance_mm:
                    findings.warnings.append(
                        f"{key} drifted {drift:+.3f} mm since the "
                        f"interruption (recorded {saved:.3f} mm, live "
                        f"{live:.3f} mm)"
                    )

        # --- (c) travel-limit re-validation of the remaining range -----
        horizontal = getattr(motors, "horizontal", None) if motors else None
        if horizontal is None:
            findings.warnings.append(
                "Horizontal stage limits could not be read — the "
                "travel-limit check was skipped"
            )
        else:
            try:
                low = float(horizontal.get_limit_low("µm"))
                high = float(horizontal.get_limit_high("µm"))
            except (TypeError, ValueError, AttributeError) as e:
                findings.warnings.append(
                    f"Travel-limit re-validation failed: {e}"
                )
            else:
                resume_start = (
                    manifest.stack_starting_plane
                    + findings.resume_plane * manifest.stack_step
                )
                lo = min(resume_start, manifest.stack_ending_plane)
                hi = max(resume_start, manifest.stack_ending_plane)
                if lo < low or hi > high:
                    findings.errors.append(
                        f"Remaining stack range {lo:.1f}-{hi:.1f} µm "
                        f"exceeds the stage travel limits "
                        f"[{low:.1f}, {high:.1f}] \u03bcm"
                    )

        return findings
