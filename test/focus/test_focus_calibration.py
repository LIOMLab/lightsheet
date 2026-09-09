"""Pure-logic tests for the focus calibration-file loader.

Mirrors the ``test_adaptive_intensity.py`` style: direct import + call +
assert, no Qt, no hardware. Temp files use ``tmp_path``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lightsheet.focus import FocusCurve, load_focus_curve


def test_load_focus_curve_returns_valid_focus_curve(tmp_path: Path) -> None:
    path = tmp_path / "curve.json"
    path.write_text(json.dumps({"points": [[0.0, 20.0], [10.0, 22.0], [20.0, 25.0]]}))
    curve = load_focus_curve(
        str(path), camera_limit_low_mm=0.0, camera_limit_high_mm=35.0
    )
    assert isinstance(curve, FocusCurve)
    assert curve.stage_pos == (0.0, 10.0, 20.0)
    assert curve.camera_pos == (20.0, 22.0, 25.0)


def test_load_focus_curve_rejects_malformed_json(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("not json")
    with pytest.raises(ValueError):
        load_focus_curve(str(path), 0.0, 35.0)


def test_load_focus_curve_rejects_short_points(tmp_path: Path) -> None:
    path = tmp_path / "short.json"
    path.write_text(json.dumps({"points": [[0.0, 20.0]]}))
    with pytest.raises(ValueError):
        load_focus_curve(str(path), 0.0, 35.0)


def test_load_focus_curve_rejects_out_of_range_camera_position(tmp_path: Path) -> None:
    path = tmp_path / "out_of_range.json"
    path.write_text(json.dumps({"points": [[0.0, 20.0], [10.0, 36.0]]}))
    with pytest.raises(ValueError, match="outside"):
        load_focus_curve(str(path), 0.0, 35.0)


def test_load_focus_curve_rejects_missing_points(tmp_path: Path) -> None:
    path = tmp_path / "missing.json"
    path.write_text(json.dumps({"other": []}))
    with pytest.raises(ValueError):
        load_focus_curve(str(path), 0.0, 35.0)


def test_load_focus_curve_rejects_non_numeric_entries(tmp_path: Path) -> None:
    path = tmp_path / "nan.json"
    path.write_text(json.dumps({"points": [["a", "b"], [1.0, 2.0]]}))
    with pytest.raises(ValueError):
        load_focus_curve(str(path), 0.0, 35.0)
