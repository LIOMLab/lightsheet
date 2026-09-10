"""Branch-coverage tests for ``lightsheet/resume/gate.py``.

Targets the branches left uncovered by ``test_safety_gate.py``:

- ``collect_safety_config``: baseline present but unloadable -> ``{}``.
- ``from_manifest`` config diff: ``live_config=None`` load success and
  failure; fingerprint key absent from the live section; empty live
  config with a recorded fingerprint -> "could not be compared".
- Probe loop: legacy save-mode HDF5 cursor key resolution (resolved /
  unresolvable), zarr cursor probing, unknown format skipped.
- Motor readback: ``motors=None`` with and without recorded positions,
  ``get_positions`` raising, a recorded axis missing from the live
  readback, no comparable axes.
- Travel limits: no ``horizontal`` readback; limit getters raising.

Pure-Python — no Qt, no HAL, no hardware.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import h5py
import numpy as np
import pytest
import zarr

import lightsheet.resume.gate as gate_mod
from lightsheet.config_schema.validation import ConfigValidationResult
from lightsheet.resume.gate import (
    ResumeSafetyGate,
    collect_safety_config,
)
from lightsheet.resume.manifest import ResumeManifest


def _manifest(**overrides: object) -> ResumeManifest:
    base: dict[str, Any] = dict(
        uuid="deadbeef" * 4,
        state="interrupted",
        n_planes=4,
        stack_starting_plane=3000.0,
        stack_ending_plane=3030.0,
        stack_step=10.0,
        save_mode="stitch",
        created_at="2026-09-08T00:00:00+00:00",
    )
    base.update(overrides)
    return ResumeManifest(**base)


class _FakeMotor:
    def __init__(self, low: float, high: float) -> None:
        self._low = low
        self._high = high

    def get_limit_low(self, units: str) -> float:
        return self._low

    def get_limit_high(self, units: str) -> float:
        return self._high


class _FakeMotors:
    """Minimal IMotors stand-in: get_positions + horizontal limits."""

    def __init__(
        self,
        positions: dict[str, float],
        limit_low_um: float = -1000.0,
        limit_high_um: float = 200000.0,
    ) -> None:
        self._positions = positions
        self.horizontal = _FakeMotor(limit_low_um, limit_high_um)

    def get_positions(self) -> dict[str, float]:
        return dict(self._positions)


class _PositionsOnlyMotors:
    """Motor stand-in with positions but NO horizontal limit readback."""

    def __init__(self, positions: dict[str, float]) -> None:
        self._positions = positions

    def get_positions(self) -> dict[str, float]:
        return dict(self._positions)


class _RaisingMotors:
    """Motor stand-in whose get_positions always fails."""

    horizontal = _FakeMotor(-1000.0, 200000.0)

    def get_positions(self) -> dict[str, float]:
        raise RuntimeError("daq offline")


class _RaisingLimitMotors(_FakeMotors):
    """Motor stand-in whose horizontal limit getters raise."""

    def __init__(self) -> None:
        super().__init__({})
        self.horizontal = _RaisingMotor()


class _RaisingMotor:
    def get_limit_low(self, units: str) -> float:
        raise TypeError("no such axis")

    def get_limit_high(self, units: str) -> float:
        raise TypeError("no such axis")


def _no_config_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        gate_mod,
        "collect_config_errors",
        lambda sections: ConfigValidationResult(),
    )


# --------------------------------------------------------------------- #
# collect_safety_config
# --------------------------------------------------------------------- #


def test_collect_safety_config_unreadable_returns_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A baseline that exists but fails to parse yields {} and a logged
    warning — never a raised error."""
    ini = tmp_path / "config.ini"
    ini.write_text("not an ini", encoding="utf-8")
    monkeypatch.setattr(
        gate_mod,
        "load_sections_from_ini",
        lambda *a: (_ for _ in ()).throw(ValueError("bad ini")),
    )
    assert collect_safety_config(str(ini), None) == {}


# --------------------------------------------------------------------- #
# from_manifest — live_config loading and fingerprint edge cases
# --------------------------------------------------------------------- #


def test_from_manifest_loads_live_config_when_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """live_config=None triggers a load_sections_from_ini call for the
    fingerprint diff."""
    _no_config_validation(monkeypatch)
    monkeypatch.setattr(
        gate_mod,
        "load_sections_from_ini",
        lambda *a: {"iBeam": {"Max Power": "100000"}},
    )
    manifest = _manifest(safety_config={"iBeam": {"Max Power": "100000"}})
    findings = ResumeSafetyGate.from_manifest(manifest, None, None)
    assert findings.errors == []
    assert any("matches the live config" in c for c in findings.check_results)


def test_from_manifest_live_config_load_failure_warns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the live config cannot be loaded, the diff is reported as a
    warning and the comparison is skipped."""
    monkeypatch.setattr(
        gate_mod,
        "load_sections_from_ini",
        lambda *a: (_ for _ in ()).throw(OSError("no config")),
    )
    manifest = _manifest(safety_config={"iBeam": {"Max Power": "100000"}})
    findings = ResumeSafetyGate.from_manifest(manifest, None, None)
    assert findings.errors == []
    assert any("could not be loaded" in w for w in findings.warnings)
    assert any("could not be compared" in c for c in findings.check_results)


def test_fingerprint_key_absent_from_live_section_warns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fingerprinted key missing from the live config is a warning and
    sets has_differences."""
    _no_config_validation(monkeypatch)
    manifest = _manifest(safety_config={"Motors": {"Limit High": "41.0"}})
    findings = ResumeSafetyGate.from_manifest(manifest, {"Motors": {}}, _FakeMotors({}))
    assert findings.errors == []
    assert findings.has_differences is True
    assert any("absent from the live config" in w for w in findings.warnings)


def test_empty_live_config_with_fingerprint_warns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty live config (loaded but without sections) plus a recorded
    fingerprint reports 'could not be compared'."""
    _no_config_validation(monkeypatch)
    manifest = _manifest(safety_config={"iBeam": {"Max Power": "100000"}})
    findings = ResumeSafetyGate.from_manifest(manifest, {}, _FakeMotors({}))
    assert findings.errors == []
    assert any("could not be compared" in w for w in findings.warnings)


# --------------------------------------------------------------------- #
# Probe loop — legacy HDF5 cursor keys, zarr, unknown formats
# --------------------------------------------------------------------- #


def test_legacy_hdf5_cursor_key_resolves_via_save_filepath(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A legacy save-mode cursor key ('stitch') resolves to
    ``{save_filepath}_{wl}nm.hdf5`` and is probed."""
    _no_config_validation(monkeypatch)
    base = tmp_path / "acq"
    target = Path(f"{base}_488nm.hdf5")
    with h5py.File(str(target), "w") as f:
        f.create_dataset(
            "reconstructed_frame001",
            data=np.zeros((4, 4), dtype=np.uint16),
        )
    manifest = _manifest(
        cursors={"hdf5": {"stitch": 2}},
        save_filepath=str(base),
        wavelengths=[488],
    )
    findings = ResumeSafetyGate.from_manifest(manifest, {}, _FakeMotors({}))
    assert findings.observed_planes[str(target)] == 1
    assert findings.resume_plane == 1


def test_legacy_hdf5_cursor_key_unresolvable_warns(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A legacy cursor key whose resolved file does not exist warns and
    falls back to a _partN fileset."""
    _no_config_validation(monkeypatch)
    manifest = _manifest(
        cursors={"hdf5": {"stitch": 3}},
        save_filepath=str(tmp_path / "missing"),
        wavelengths=[488],
    )
    findings = ResumeSafetyGate.from_manifest(manifest, {}, _FakeMotors({}))
    assert findings.errors == []
    assert any("_partN" in w for w in findings.warnings)
    assert findings.resume_plane == 0


def test_zarr_cursor_is_probed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A zarr cursor entry is probed per channel and feeds resume_plane."""
    _no_config_validation(monkeypatch)
    store = tmp_path / "acq.zarr"
    root = zarr.open(str(store), mode="w")
    assert isinstance(root, zarr.Group)
    arr = root.create_array(
        "0", shape=(1, 5, 4, 4), chunks=(1, 1, 4, 4), dtype=np.uint16
    )
    for z in range(3):
        arr[0, z, :, :] = np.ones((4, 4), dtype=np.uint16)
    manifest = _manifest(cursors={"zarr": {str(store): 4}}, wavelengths=[488])
    findings = ResumeSafetyGate.from_manifest(manifest, {}, _FakeMotors({}))
    assert findings.observed_planes[str(store)] == 3
    assert findings.resume_plane == 3


# --------------------------------------------------------------------- #
# Motor readback branches
# --------------------------------------------------------------------- #


def test_no_motors_with_recorded_positions_warns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """motors=None with recorded positions: drift check skipped, warning."""
    _no_config_validation(monkeypatch)
    manifest = _manifest(last_motor_positions={"x": 5.0})
    findings = ResumeSafetyGate.from_manifest(manifest, {}, None)
    assert findings.errors == []
    assert any("drift" in w and "skipped" in w for w in findings.warnings)
    assert any("check skipped" in c for c in findings.check_results)


def test_no_motors_without_recorded_positions_quiet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """motors=None with no recorded positions: nothing to compare."""
    _no_config_validation(monkeypatch)
    findings = ResumeSafetyGate.from_manifest(_manifest(), {}, None)
    assert findings.errors == []
    assert any("no recorded positions" in c for c in findings.check_results)


def test_motor_readback_failure_warns(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_positions raising yields a warning and an unavailable readback
    result — never an error."""
    _no_config_validation(monkeypatch)
    manifest = _manifest(last_motor_positions={"x": 5.0})
    findings = ResumeSafetyGate.from_manifest(manifest, {}, _RaisingMotors())
    assert findings.errors == []
    assert any("readback failed" in w for w in findings.warnings)
    assert any("readback unavailable" in c for c in findings.check_results)


def test_recorded_axis_missing_from_live_readback_warns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A recorded axis with no live counterpart warns per-axis."""
    _no_config_validation(monkeypatch)
    manifest = _manifest(last_motor_positions={"x": 5.0})
    motors = _FakeMotors({"y": 1.0})
    findings = ResumeSafetyGate.from_manifest(manifest, {}, motors)
    assert findings.errors == []
    assert any("live" in w and "unavailable" in w for w in findings.warnings)
    assert any("no recorded positions" in c for c in findings.check_results)


# --------------------------------------------------------------------- #
# Travel-limit branches
# --------------------------------------------------------------------- #


def test_no_horizontal_readback_skips_limit_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A motor bundle without ``horizontal`` warns and skips the
    travel-limit re-validation."""
    _no_config_validation(monkeypatch)
    motors = _PositionsOnlyMotors({})
    findings = ResumeSafetyGate.from_manifest(_manifest(), {}, motors)
    assert findings.errors == []
    assert any("limits could not be read" in w for w in findings.warnings)
    assert any("check skipped" in c for c in findings.check_results)


def test_limit_read_failure_warns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Limit getters raising a typed error produce a warning, not an
    exception."""
    _no_config_validation(monkeypatch)
    findings = ResumeSafetyGate.from_manifest(_manifest(), {}, _RaisingLimitMotors())
    assert findings.errors == []
    assert any("re-validation failed" in w for w in findings.warnings)
    assert any("re-validation failed" in c for c in findings.check_results)


def test_explicit_drift_tolerance_is_used(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The drift_tolerance_mm keyword is honoured by the gate."""
    _no_config_validation(monkeypatch)
    manifest = _manifest(last_motor_positions={"x": 5.0})
    motors = _FakeMotors({"x": 5.05})
    findings = ResumeSafetyGate.from_manifest(
        manifest, {}, motors, drift_tolerance_mm=0.01
    )
    assert findings.errors == []
    assert any("drifted" in w for w in findings.warnings)
