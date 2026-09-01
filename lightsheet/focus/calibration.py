"""JSON calibration-file loader for the focus control loop."""

from __future__ import annotations

import json
from pathlib import Path

from lightsheet.focus.types import FocusCurve


def load_focus_curve(
    path: str, camera_limit_low_mm: float, camera_limit_high_mm: float
) -> FocusCurve:
    """Load and validate a JSON calibration file.

    The file must contain a top-level ``"points"`` list, where each entry is a
    ``[stage_mm, camera_mm]`` pair. Raises ``ValueError`` (naming the reason)
    on missing/malformed JSON, a missing/short ``points`` list, non-numeric
    entries, or any camera position outside the supplied travel limits.
    """
    try:
        data = json.loads(Path(path).read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed JSON in calibration file: {exc}") from exc

    pts = data.get("points")
    if not isinstance(pts, list) or len(pts) < 2:
        raise ValueError(
            "calibration file must have a 'points' list with >= 2 entries"
        )

    try:
        stage = tuple(float(p[0]) for p in pts)
        cam = tuple(float(p[1]) for p in pts)
    except (TypeError, ValueError, IndexError) as exc:
        raise ValueError(
            "calibration points must be numeric [stage_mm, camera_mm] pairs"
        ) from exc

    for c in cam:
        if c < camera_limit_low_mm or c > camera_limit_high_mm:
            raise ValueError(
                f"camera position {c} mm outside travel limits "
                f"[{camera_limit_low_mm}, {camera_limit_high_mm}]"
            )

    return FocusCurve(stage_pos=stage, camera_pos=cam)
