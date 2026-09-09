"""Frozen value/snapshot contracts for the reactive microscope state model.

Pure-Python, no Qt / no HAL imports — testable with direct import + call
+ assert. The frozen property mirrors the ``AdaptiveConfig`` / ``FocusConfig``
convention: a worker cannot mutate a snapshot mid-run, and any attempted
mutation raises ``FrozenInstanceError``.
"""

from __future__ import annotations

import dataclasses
import math
from enum import StrEnum
from typing import Any


class SaveMode(StrEnum):
    """Mutually-exclusive save-mode selections from the save panel."""

    STITCH = "stitch"
    STITCH_BLEND = "stitch_blend"
    ALL_CROP = "all_crop"
    ALL_FULL = "all_full"


@dataclasses.dataclass(frozen=True)
class SaveOptions:
    """Frozen save-option intent: description + one exclusive save mode."""

    description: str = ""
    mode: SaveMode = SaveMode.STITCH

    def __post_init__(self) -> None:
        if not isinstance(self.description, str):
            raise ValueError(
                f"SaveOptions.description must be a str; got {type(self.description)}"
            )
        if not isinstance(self.mode, SaveMode):
            raise ValueError(f"SaveOptions.mode must be a SaveMode; got {self.mode!r}")


@dataclasses.dataclass(frozen=True)
class MicroscopeSnapshot:
    """Frozen operator-intent snapshot sampled on the GUI thread and handed
    to workers at spawn time.

    Workers read only this snapshot during a run; the live model is the
    GUI-thread source of truth for intent, and the applied readback from the
    worker is folded back via ``AppliedMicroscopeSnapshot``.
    """

    lightsheet_line_time_s: float
    laser_power_pct: tuple[float, float] = (0.0, 0.0)
    laser_enabled: tuple[bool, bool] = (False, False)
    auto_lasers: tuple[bool, bool] = (False, False)
    save_options: SaveOptions = dataclasses.field(default_factory=SaveOptions)

    def __post_init__(self) -> None:
        if not math.isfinite(self.lightsheet_line_time_s):
            raise ValueError(
                "lightsheet_line_time_s must be finite; "
                f"got {self.lightsheet_line_time_s}"
            )
        if self.lightsheet_line_time_s <= 0:
            raise ValueError(
                "lightsheet_line_time_s must be positive; "
                f"got {self.lightsheet_line_time_s}"
            )
        _validate_two_tuple(
            self.laser_power_pct,
            "laser_power_pct",
            _valid_percentage,
        )
        _validate_two_tuple(
            self.laser_enabled,
            "laser_enabled",
            _valid_bool,
        )
        _validate_two_tuple(
            self.auto_lasers,
            "auto_lasers",
            _valid_bool,
        )
        if not isinstance(self.save_options, SaveOptions):
            raise ValueError(
                "save_options must be a SaveOptions instance; "
                f"got {type(self.save_options)}"
            )


@dataclasses.dataclass(frozen=True)
class AppliedMicroscopeSnapshot:
    """Frozen worker-to-GUI applied-state readback. Only non-None fields are
    folded into the live model by ``MicroscopeState.apply_worker_snapshot``.
    """

    laser_power_pct: tuple[float, float] | None = None
    laser_enabled: tuple[bool, bool] | None = None
    lightsheet_line_time_s: float | None = None

    def __post_init__(self) -> None:
        if self.laser_power_pct is not None:
            _validate_two_tuple(
                self.laser_power_pct,
                "laser_power_pct",
                _valid_percentage,
            )
        if self.laser_enabled is not None:
            _validate_two_tuple(
                self.laser_enabled,
                "laser_enabled",
                _valid_bool,
            )
        if self.lightsheet_line_time_s is not None:
            if not math.isfinite(self.lightsheet_line_time_s):
                raise ValueError(
                    "lightsheet_line_time_s must be finite; "
                    f"got {self.lightsheet_line_time_s}"
                )
            if self.lightsheet_line_time_s <= 0:
                raise ValueError(
                    "lightsheet_line_time_s must be positive; "
                    f"got {self.lightsheet_line_time_s}"
                )


def _valid_percentage(value: Any, field_name: str, idx: int) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{field_name}[{idx}] must be a number; got {type(value)}")
    if not math.isfinite(value):
        raise ValueError(f"{field_name}[{idx}] must be finite; got {value}")
    if value < 0.0 or value > 100.0:
        raise ValueError(f"{field_name}[{idx}] must be in [0, 100]; got {value}")


def _valid_bool(value: Any, field_name: str, idx: int) -> None:
    if not isinstance(value, bool):
        raise ValueError(f"{field_name}[{idx}] must be a bool; got {type(value)}")


def _validate_two_tuple(
    value: tuple[Any, Any],
    field_name: str,
    validator: Any,
) -> None:
    if not isinstance(value, tuple):
        raise ValueError(f"{field_name} must be a tuple; got {type(value)}")
    if len(value) != 2:
        raise ValueError(f"{field_name} must be a 2-tuple; got length {len(value)}")
    for idx, item in enumerate(value):
        validator(item, field_name, idx)
