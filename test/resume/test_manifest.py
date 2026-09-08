"""Unit tests for the resume-manifest value type and atomic sidecar I/O.

Pure-Python (no Qt): direct import + call + assert, mirroring the
``lightsheet/state/types.py`` test convention.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from lightsheet.resume import (
    ManifestUpdate,
    ResumeManifest,
    apply_manifest_update,
    manifest_path_for,
    read_manifest,
    write_manifest,
)


def _manifest(**overrides: object) -> ResumeManifest:
    """Build a minimal valid manifest; overrides applied on top."""
    kwargs: dict = {  # ty: ignore[missing-type-argument]
        "uuid": uuid.uuid4().hex,
        "state": "in_progress",
        "n_planes": 5,
        "stack_starting_plane": 0.0,
        "stack_ending_plane": 40.0,
        "stack_step": 10.0,
        "save_mode": "stitch",
        "wavelengths": [555],
        "created_at": "2026-09-08T00:00:00+00:00",
    }
    kwargs.update(overrides)
    return ResumeManifest(**kwargs)


def test_manifest_round_trip(tmp_path: Path) -> None:
    """write_manifest + read_manifest round-trips every field."""
    m = _manifest(
        cursors={"hdf5": {"stitch": 3}},
        last_motor_positions={"horizontal": 12.5, "camera": 4.0},
        trajectory_samples=[{"plane_index": 0, "exposure_s": 0.01}],
        controller_checkpoints=[{"plane_index": 0, "residual_mm": 0.1}],
        adaptive_cfg={"enabled": True, "kp": 0.5},
        row_index=2,
    )
    path = tmp_path / "acq_555nm.resume.json"
    write_manifest(path, m)
    loaded = read_manifest(path)
    assert loaded == m


def test_write_manifest_atomic_no_tmp_left(tmp_path: Path) -> None:
    """The temp-file + os.replace write leaves only the target file."""
    path = tmp_path / "a.resume.json"
    write_manifest(path, _manifest())
    write_manifest(path, _manifest(state="completed"))
    remaining = [p.name for p in tmp_path.iterdir()]
    assert remaining == ["a.resume.json"]
    loaded = read_manifest(path)
    assert loaded is not None and loaded.state == "completed"


def test_uuid_retained(tmp_path: Path) -> None:
    m = _manifest()
    path = tmp_path / "b.resume.json"
    write_manifest(path, m)
    loaded = read_manifest(path)
    assert loaded is not None and loaded.uuid == m.uuid


def test_unknown_state_rejected() -> None:
    with pytest.raises(ValueError, match="state"):
        _manifest(state="bogus")


def test_n_planes_must_be_positive() -> None:
    with pytest.raises(ValueError, match="n_planes"):
        _manifest(n_planes=0)


def test_start_plane_must_be_below_n_planes() -> None:
    with pytest.raises(ValueError, match="start_plane"):
        _manifest(start_plane=5)


def test_unknown_cursor_format_rejected() -> None:
    with pytest.raises(ValueError, match="cursors"):
        _manifest(cursors={"tiff": {"stitch": 1}})


def test_cursor_value_must_be_int() -> None:
    with pytest.raises(ValueError):
        _manifest(cursors={"hdf5": {"stitch": "three"}})


def test_read_manifest_corrupt_returns_none(tmp_path: Path) -> None:
    path = tmp_path / "c.resume.json"
    path.write_text("{not json", encoding="utf-8")
    assert read_manifest(path) is None


def test_read_manifest_unknown_state_returns_none(tmp_path: Path) -> None:
    """A hand-edited manifest fails closed (never resumes into a bad state)."""
    path = tmp_path / "d.resume.json"
    path.write_text(
        json.dumps({"uuid": "x", "state": "bogus", "n_planes": 3}),
        encoding="utf-8",
    )
    assert read_manifest(path) is None


def test_read_manifest_missing_returns_none(tmp_path: Path) -> None:
    assert read_manifest(tmp_path / "nope.resume.json") is None


def test_json_safe_wavelengths_and_cursors(tmp_path: Path) -> None:
    m = _manifest(wavelengths=[555, 647], cursors={"hdf5": {"stitch": 0}})
    path = tmp_path / "e.resume.json"
    write_manifest(path, m)
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["wavelengths"] == [555, 647]
    assert raw["cursors"] == {"hdf5": {"stitch": 0}}


def test_numpy_values_rejected() -> None:
    np = pytest.importorskip("numpy")
    with pytest.raises(ValueError, match="numpy"):
        _manifest(last_motor_positions={"horizontal": np.float64(1.0)})


def test_manifest_update_validation() -> None:
    with pytest.raises(ValueError, match="kind"):
        ManifestUpdate(kind="bogus", payload={})
    with pytest.raises(ValueError):
        ManifestUpdate(kind="cursor", payload="not-a-dict")  # ty: ignore[invalid-argument-type]


def test_manifest_update_picklable_and_json_safe() -> None:
    import pickle

    u = ManifestUpdate(
        kind="cursor",
        payload={"format": "hdf5", "key": "stitch", "value": 4},
    )
    assert pickle.loads(pickle.dumps(u)) == u
    json.dumps(u.payload)


def test_apply_cursor_update() -> None:
    m = _manifest()
    m2 = apply_manifest_update(
        m,
        ManifestUpdate(
            kind="cursor",
            payload={"format": "hdf5", "key": "stitch", "value": 3},
        ),
    )
    assert m2.cursors == {"hdf5": {"stitch": 3}}
    # Original is untouched (frozen).
    assert m.cursors == {}


def test_apply_lifecycle_sets_completed_at() -> None:
    m = _manifest()
    m2 = apply_manifest_update(
        m, ManifestUpdate(kind="lifecycle", payload={"state": "completed"})
    )
    assert m2.state == "completed"
    assert m2.completed_at is not None


def test_apply_motor_position_and_checkpoint() -> None:
    m = _manifest()
    m = apply_manifest_update(
        m,
        ManifestUpdate(
            kind="motor_position", payload={"horizontal": 10.0}
        ),
    )
    m = apply_manifest_update(
        m,
        ManifestUpdate(
            kind="checkpoint",
            payload={"residual_mm": 0.2},
            plane_index=4,
        ),
    )
    assert m.last_motor_positions == {"horizontal": 10.0}
    assert m.controller_checkpoints == [{"residual_mm": 0.2, "plane_index": 4}]


def test_manifest_path_for() -> None:
    assert manifest_path_for("/tmp/x_555nm.hdf5").name == "x_555nm.resume.json"
