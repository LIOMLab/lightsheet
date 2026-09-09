"""Adaptive exposure + laser power control loop package.

Pure-Python control law (pilot feedforward + per-plane PI residual +
power fallback + cross-channel balance + re-acquire) with frozen
dataclass contracts. No Qt, no HAL, no SDK imports — unit-testable
with plain numpy arrays.

The worker integration (StackWorker) and save metadata (FrameSaver)
live in the GUI layer; this package owns only the control-law
decisions and the immutable command/sample representations.
"""

from lightsheet.adaptive.controller import (
    AdaptiveController,
    fit_pilot_trajectory,
    pi_residual,
    should_reacquire,
)
from lightsheet.adaptive.intensity import frame_intensity_pct
from lightsheet.adaptive.types import (
    AdaptiveCommand,
    AdaptiveConfig,
    AdaptiveSample,
)

__all__ = [
    "AdaptiveCommand",
    "AdaptiveConfig",
    "AdaptiveController",
    "AdaptiveSample",
    "fit_pilot_trajectory",
    "frame_intensity_pct",
    "pi_residual",
    "should_reacquire",
]
