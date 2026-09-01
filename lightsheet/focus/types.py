"""Frozen dataclass contracts for the camera focus compensation loop.

Pure-logic, frozen dataclasses, no Qt / no HAL / no SDK imports. The frozen
property mirrors the adaptive types safety contract: a frozen config cannot be
mutated mid-run by a worker thread, and a frozen sample is immutable proof of
what the loop decided and what was saved.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FocusConfig:
    """Frozen operator-configurable bounds for the focus loop.

    All fields are pre-sampled on the GUI thread and passed as a constructor
    arg to StackWorker — the worker thread never reads ui.*. The frozen
    property prevents a worker thread from mutating bounds mid-run.

    Validation in ``__post_init__`` rejects out-of-range or ill-ordered bounds
    with ``ValueError`` so a misconfigured spinbox fails loudly at construction,
    not silently mid-acquisition.
    """

    enabled: bool = False
    block_size_n: int = 8
    autofocus_residual: bool = True
    curve_path: str = ""
    residual_gain_mm: float = 0.05
    max_residual_mm: float = 0.5

    def __post_init__(self) -> None:
        if self.block_size_n < 1 or self.block_size_n > 100:
            raise ValueError(
                f"block_size_n must be between 1 and 100; got {self.block_size_n}"
            )
        if self.residual_gain_mm < 0 or self.residual_gain_mm > 1:
            raise ValueError(
                f"residual_gain_mm must be in [0, 1]; got {self.residual_gain_mm}"
            )
        if self.max_residual_mm < 0 or self.max_residual_mm > 5:
            raise ValueError(
                f"max_residual_mm must be in [0, 5]; got {self.max_residual_mm}"
            )


@dataclass(frozen=True)
class FocusCurve:
    """Frozen per-sample calibration curve: (stage_pos_mm, camera_pos_mm)."""

    stage_pos: tuple[float, ...]
    camera_pos: tuple[float, ...]

    def __post_init__(self) -> None:
        if len(self.stage_pos) != len(self.camera_pos):
            raise ValueError("stage_pos and camera_pos must have equal length")
        if len(self.stage_pos) < 2:
            raise ValueError("calibration curve needs >= 2 points")
        for a, b in zip(self.stage_pos, self.stage_pos[1:], strict=False):
            if not a < b:
                raise ValueError(
                    f"stage_pos must be monotonic increasing; got {a} >= {b}"
                )


@dataclass(frozen=True)
class FocusSample:
    """Frozen per-block focus trajectory sample (storage contract).

    One row per focus block. The HDF5 /focus_trajectory group and the Zarr
    /acquisition/focus group carry identical field names and units — this
    dataclass is the canonical in-memory representation both writers serialize.
    """

    block_index: int
    stage_pos_mm: float
    feedforward_camera_pos_mm: float
    residual_mm: float
    applied_camera_pos_mm: float
    sharpness_metric: float | None = None
