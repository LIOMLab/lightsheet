"""Camera focus compensation control law package.

Pure-Python focus control law: frozen config/calibration/sample contracts,
feedforward interpolation, per-block residual, and an image-sharpness metric.
No Qt, no HAL, no SDK imports — unit-testable with plain numpy arrays.
"""

from lightsheet.focus.calibration import load_focus_curve
from lightsheet.focus.controller import FocusController
from lightsheet.focus.sharpness import frame_sharpness_variance
from lightsheet.focus.types import FocusConfig, FocusCurve, FocusSample

__all__ = [
    "FocusConfig",
    "FocusController",
    "FocusCurve",
    "FocusSample",
    "frame_sharpness_variance",
    "load_focus_curve",
]
