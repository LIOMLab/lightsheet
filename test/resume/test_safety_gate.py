"""ResumeSafetyGate unit tests (Qt-free).

The gate is report-then-confirm: it collects findings — config-fingerprint
diffs and motor drift are warnings, a remaining-range travel-limit
violation is an error, and per-format probes feed the authoritative
``resume_plane``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import h5py
import numpy as np
import pytest

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


def _no_config_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bypass strict live-config schema validation for diff-focused tests."""
    monkeypatch.setattr(
        gate_mod,
        "collect_config_errors",
        lambda sections: ConfigValidationResult(),
    )


def test_clean_manifest_produces_no_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    _no_config_validation(monkeypatch)
    findings = ResumeSafetyGate.from_manifest(_manifest(), {}, _FakeMotors({}))
    assert findings.errors == []
    assert findings.resume_plane == 0


def test_config_fingerprint_diff_is_a_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    _no_config_validation(monkeypatch)
    manifest = _manifest(safety_config={"iBeam": {"Max Power": "100000"}})
    live = {"iBeam": {"Max Power": "120000"}}
    findings = ResumeSafetyGate.from_manifest(manifest, live, _FakeMotors({}))
    assert findings.errors == []
    assert any("Max Power" in w for w in findings.warnings)


def test_matching_fingerprint_produces_no_diff_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _no_config_validation(monkeypatch)
    manifest = _manifest(safety_config={"iBeam": {"Max Power": "100000"}})
    live = {"iBeam": {"Max Power": "100000"}}
    findings = ResumeSafetyGate.from_manifest(manifest, live, _FakeMotors({}))
    assert not any("Max Power" in w for w in findings.warnings)


def test_live_config_errors_block_resume(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        gate_mod,
        "collect_config_errors",
        lambda sections: ConfigValidationResult(
            errors=["[iBeam] Max Power = 200000: out of range."]
        ),
    )
    findings = ResumeSafetyGate.from_manifest(
        _manifest(), {"iBeam": {}}, _FakeMotors({})
    )
    assert any("Max Power" in e for e in findings.errors)


def test_motor_drift_is_a_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    _no_config_validation(monkeypatch)
    manifest = _manifest(last_motor_positions={"horizontal position": 5.0})
    motors = _FakeMotors({"horizontal position": 5.2})
    findings = ResumeSafetyGate.from_manifest(manifest, {}, motors)
    assert findings.errors == []
    assert any("drifted" in w for w in findings.warnings)


def test_motor_drift_within_tolerance_is_quiet(monkeypatch: pytest.MonkeyPatch) -> None:
    _no_config_validation(monkeypatch)
    manifest = _manifest(last_motor_positions={"horizontal position": 5.0})
    motors = _FakeMotors({"horizontal position": 5.05})
    findings = ResumeSafetyGate.from_manifest(manifest, {}, motors)
    assert not any("drifted" in w for w in findings.warnings)


def test_travel_limit_violation_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _no_config_validation(monkeypatch)
    manifest = _manifest(stack_ending_plane=250000.0)
    motors = _FakeMotors({}, limit_high_um=200000.0)
    findings = ResumeSafetyGate.from_manifest(manifest, {}, motors)
    assert any("travel limits" in e for e in findings.errors)


def test_probe_records_observed_and_resume_plane(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _no_config_validation(monkeypatch)
    target = tmp_path / "acq_488nm.hdf5"
    with h5py.File(str(target), "w") as f:
        for i in (1, 2):
            f.create_dataset(
                f"reconstructed_frame{i:03d}",
                data=np.zeros((4, 4), dtype=np.uint16),
            )
    manifest = _manifest(cursors={"hdf5": {str(target): 3}})
    findings = ResumeSafetyGate.from_manifest(manifest, {}, _FakeMotors({}))
    assert findings.observed_planes[str(target)] == 2
    # min(cursor=3, observed=2) — the torn tail is re-acquired.
    assert findings.resume_plane == 2


def test_unopenable_file_warns_and_falls_back(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _no_config_validation(monkeypatch)
    missing = tmp_path / "gone_488nm.hdf5"
    manifest = _manifest(cursors={"hdf5": {str(missing): 5}})
    findings = ResumeSafetyGate.from_manifest(manifest, {}, _FakeMotors({}))
    # Not fatal: set_files' _partN fallback covers the missing fileset;
    # the missing observation counts as 0 committed planes.
    assert findings.errors == []
    assert any("_partN" in w for w in findings.warnings)
    assert findings.resume_plane == 0


def test_collect_safety_config_extracts_safety_keys(tmp_path: Path) -> None:
    ini = tmp_path / "config.ini"
    ini.write_text(
        "[iBeam]\nMax Power = 150000\nPort = COM1\n"
        "[Motors]\nHorizontal Limit High = 41.0\n",
        encoding="utf-8",
    )
    result = collect_safety_config(str(ini), None)
    assert result["iBeam"] == {"Max Power": "150000"}
    assert result["Motors"] == {"Horizontal Limit High": "41.0"}


def test_collect_safety_config_missing_file_returns_empty(
    tmp_path: Path,
) -> None:
    assert collect_safety_config(str(tmp_path / "nope.ini"), None) == {}
