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

import dataclasses
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
    from typing import Protocol

    from lightsheet.resume.manifest import ResumeManifest

    class _MotorReadback(Protocol):
        """Structural surface the gate needs from the live motor bundle.

        Only ``get_positions`` is required for the drift check; the
        horizontal-axis limit readout is reached via ``getattr`` so test
        doubles and partial shells satisfy the same contract.
        """

        def get_positions(self) -> dict[str, float]: ...


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
    worker must start from. ``has_differences`` is set when a check
    measured a concrete divergence (config-fingerprint diff or motor
    drift) so the GUI layer can show the destructive "resume despite
    reported drift" confirmation copy for those runs.
    """

    observed_planes: dict[str, int] = field(default_factory=dict)
    resume_plane: int = 0
    has_differences: bool = False
    check_results: list[str] = field(default_factory=list)


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
        motors: _MotorReadback | None,
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
        fingerprint_diffs = 0
        if live_config is None:
            try:
                live_config = load_sections_from_ini(
                    "config.ini", "config.rig-specific.ini"
                )
            except Exception as e:
                findings.warnings.append(
                    f"Live config could not be loaded for the fingerprint diff: {e}"
                )
                live_config = {}
        if live_config:
            live_result = collect_config_errors(live_config)
            findings.errors.extend(f"[live config] {e}" for e in live_result.errors)
            findings.warnings.extend(f"[live config] {w}" for w in live_result.warnings)
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
                        findings.has_differences = True
                        fingerprint_diffs += 1
                    elif str(live_val) != str(saved):
                        findings.warnings.append(
                            f"[{section}] {key} changed since the "
                            f"acquisition: {saved!r} -> {live_val!r}"
                        )
                        findings.has_differences = True
                        fingerprint_diffs += 1
            findings.check_results.append(
                "Config fingerprint — matches the live config"
                if fingerprint_diffs == 0
                else f"Config fingerprint — {fingerprint_diffs} difference(s) found"
            )
        elif manifest.safety_config:
            findings.warnings.append(
                "Safety-config fingerprint could not be compared — the "
                "live config is unavailable"
            )
            findings.check_results.append(
                "Config fingerprint — could not be compared (live config unavailable)"
            )

        # --- (d) per-format probes (before limits so resume_plane is
        # computed from the durable cursor, not the nominal one) ---------
        probes: dict[str, dict[str, int]] = {}
        norm_cursors: dict[str, dict[str, int]] = {}
        for fmt, group in manifest.cursors.items():
            observed: dict[str, int] = {}
            norm_group: dict[str, int] = {}
            for key, cursor in group.items():
                path = key
                if fmt == "hdf5" and not key.endswith(".hdf5"):
                    # Legacy single-channel manifests keyed the HDF5
                    # cursor by save mode ("stitch"/"all_crop"/
                    # "all_full"); resolve it against the recorded save
                    # filepath so the torn file is still probed.
                    base = manifest.save_filepath or ""
                    wl = (manifest.wavelengths or [0])[0]
                    candidate = f"{base}_{wl}nm.hdf5" if base else ""
                    if not candidate or not Path(candidate).is_file():
                        findings.warnings.append(
                            f"Recorded cursor {key!r} could not be "
                            "resolved to an output file — resume falls "
                            "back to a _partN continuation fileset"
                        )
                        continue
                    path = candidate
                norm_group[path] = cursor
                try:
                    if fmt == "hdf5":
                        n = probe_hdf5(path)
                    elif fmt == "zarr":
                        n_channels = max(1, len(manifest.wavelengths or []))
                        n = min(probe_zarr(path, f"ch{c}") for c in range(n_channels))
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
            norm_cursors[fmt] = norm_group
        if manifest.cursors:
            # Cursors were normalized to resolved file paths above so the
            # per-key observed lookup matches for both the path-keyed
            # schema and legacy save-mode keys.
            norm_manifest = dataclasses.replace(manifest, cursors=norm_cursors)
            resume_plane, _ = _common_resume_plane(norm_manifest, probes)
        else:
            resume_plane = manifest.start_plane
        findings.resume_plane = max(0, int(resume_plane))
        n_probed = sum(len(g) for g in probes.values())
        if manifest.cursors:
            findings.check_results.append(
                f"Output probes — resume plane {findings.resume_plane} "
                f"(durable across {n_probed} file(s))"
            )
        else:
            findings.check_results.append(
                "Output probes — no committed cursors recorded"
            )

        # --- (b) motor position readback vs recorded positions ---------
        drifted_axes = 0
        compared_axes = 0
        if motors is None:
            if manifest.last_motor_positions:
                findings.warnings.append(
                    "Motor positions could not be read back — the drift "
                    "check was skipped"
                )
                findings.check_results.append(
                    "Motor drift — check skipped (no live readback)"
                )
            else:
                findings.check_results.append(
                    "Motor drift — no recorded positions to compare"
                )
        else:
            try:
                positions = {
                    str(k): float(v) for k, v in motors.get_positions().items()
                }
            except Exception as e:
                positions = {}
                findings.warnings.append(f"Motor position readback failed: {e}")
            for key, saved in manifest.last_motor_positions.items():
                live = positions.get(key)
                if live is None:
                    findings.warnings.append(
                        f"{key}: recorded {saved:.3f} mm but the live "
                        f"readback is unavailable"
                    )
                    continue
                compared_axes += 1
                drift = live - saved
                if abs(drift) > drift_tolerance_mm:
                    findings.warnings.append(
                        f"{key} drifted {drift:+.3f} mm since the "
                        f"interruption (recorded {saved:.3f} mm, live "
                        f"{live:.3f} mm)"
                    )
                    findings.has_differences = True
                    drifted_axes += 1
            if compared_axes:
                findings.check_results.append(
                    f"Motor drift — {drifted_axes} of {compared_axes} "
                    "axis(es) beyond tolerance"
                    if drifted_axes
                    else f"Motor drift — {compared_axes} axis(es) within tolerance"
                )
            elif positions:
                findings.check_results.append(
                    "Motor drift — no recorded positions to compare"
                )
            else:
                findings.check_results.append("Motor drift — readback unavailable")

        # --- (c) travel-limit re-validation of the remaining range -----
        horizontal = getattr(motors, "horizontal", None) if motors else None
        if horizontal is None:
            findings.warnings.append(
                "Horizontal stage limits could not be read — the "
                "travel-limit check was skipped"
            )
            findings.check_results.append(
                "Travel limits — check skipped (no limit readback)"
            )
        else:
            try:
                low = float(horizontal.get_limit_low("µm"))
                high = float(horizontal.get_limit_high("µm"))
            except (TypeError, ValueError, AttributeError) as e:
                findings.warnings.append(f"Travel-limit re-validation failed: {e}")
                findings.check_results.append("Travel limits — re-validation failed")
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
                    findings.check_results.append(
                        "Travel limits — remaining range exceeds the stage limits"
                    )
                else:
                    findings.check_results.append(
                        "Travel limits — remaining range validated"
                    )

        return findings
