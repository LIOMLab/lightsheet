"""Frozen dataclass contracts for the adaptive exposure + laser power
control loop.

Mirrors the ``lightsheet.channel_map`` pattern: pure-logic, frozen
dataclasses, no Qt / no HAL / no SDK imports — testable with a direct
import + call + assert. The frozen property mirrors the ChannelMap /
FieldSpec safety contract: a frozen config cannot be mutated mid-run
by a worker thread, and a frozen command/sample is immutable proof of
what the loop decided and what was saved.

Schema-a (the approved one-way storage contract):
- AdaptiveSample carries plane_index, intensity_fraction[channels]
  (NaN for inactive), exposure_s, laser_power_mw[2],
  control_variable_active, reacquired, power_fallback.
- HDF5 /adaptive_trajectory and Zarr /acquisition/adaptive share the
  identical field names and units.
- ``reacquired`` records the controller's re-acquire *decision* (not
  whether the plane was actually re-acquired — see the field note).
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class AdaptiveConfig:
    """Frozen operator-configurable bounds + gains for the adaptive loop.

    All fields are pre-sampled on the GUI thread and passed as a
    constructor arg to StackWorker — the worker thread never reads
    ui.* (the cross-thread widget-access prohibition). The frozen
    property prevents a worker thread from mutating bounds mid-run.

    Validation in ``__post_init__`` rejects out-of-range or
    ill-ordered bounds with ``ValueError`` so a misconfigured spinbox
    fails loudly at construction, not silently mid-acquisition.
    """

    enabled: bool = False
    min_exposure_s: float = 5e-3
    max_exposure_s: float = 200e-3
    min_power_mw: tuple[float, float] = (0.0, 0.0)
    max_power_mw: tuple[float, float] = (100.0, 100.0)
    target_band_lo: float = 0.90
    target_band_hi: float = 0.95
    reacquire_threshold: float = 0.08
    block_size_n: int = 8
    kp: float = 0.4
    ki: float = 0.05
    pilot_count: int = 5
    sensor_max: int = 65535
    max_reacquire_attempts: int = 1

    def __post_init__(self) -> None:
        if self.min_exposure_s > self.max_exposure_s:
            raise ValueError(
                f"min_exposure_s ({self.min_exposure_s}) must be <= "
                f"max_exposure_s ({self.max_exposure_s})"
            )
        if self.min_power_mw[0] > self.max_power_mw[0]:
            raise ValueError(
                f"min_power_mw[0] ({self.min_power_mw[0]}) must be <= "
                f"max_power_mw[0] ({self.max_power_mw[0]})"
            )
        if self.min_power_mw[1] > self.max_power_mw[1]:
            raise ValueError(
                f"min_power_mw[1] ({self.min_power_mw[1]}) must be <= "
                f"max_power_mw[1] ({self.max_power_mw[1]})"
            )
        if self.block_size_n <= 0:
            raise ValueError(f"block_size_n must be positive; got {self.block_size_n}")
        if self.target_band_lo > self.target_band_hi:
            raise ValueError(
                f"target_band_lo ({self.target_band_lo}) must be <= "
                f"target_band_hi ({self.target_band_hi})"
            )
        if self.pilot_count <= 0:
            raise ValueError(f"pilot_count must be positive; got {self.pilot_count}")

    def clamp_exposure(self, exposure_s: float) -> float:
        """Clamp an exposure in seconds to [min_exposure_s, max_exposure_s]."""
        return max(self.min_exposure_s, min(self.max_exposure_s, exposure_s))

    def clamp_power(self, powers_mw: tuple[float, float]) -> tuple[float, float]:
        """Clamp per-laser power in mW to [min_power_mw, max_power_mw] per
        laser. Mirrors the ChannelMap.clamp_* shape: hard-cap before
        returning so the worker inherits a pre-tested clamp."""
        p1 = max(self.min_power_mw[0], min(self.max_power_mw[0], powers_mw[0]))
        p2 = max(self.min_power_mw[1], min(self.max_power_mw[1], powers_mw[1]))
        return (p1, p2)

    @property
    def target_midpoint(self) -> float:
        """The midpoint of the target intensity band — the PI setpoint."""
        return (self.target_band_lo + self.target_band_hi) / 2.0


@dataclass(frozen=True)
class AdaptiveCommand:
    """Frozen per-plane command from the adaptive controller.

    The worker reads this immutable record and applies it through the
    existing HAL paths (camera.set_exposure_time / HardwareManager
    percent adapters → ILaser.set_power). The worker never mutates it.

    ``reacquire`` is the controller's *decision* to re-acquire this
    plane — a request flag, NOT a record that re-acquisition happened.
    The current worker does not implement re-grab logic, so a True
    value means the controller decided a re-acquire would be warranted,
    not that the plane was actually re-acquired. ``AdaptiveSample.
    reacquired`` mirrors this decision flag for the saved trajectory.

    ``control_variable_active`` is one of:
    - ``"fixed"``: adaptive is off; the command is a constant
      passthrough of the current exposure/power.
    - ``"exposure"``: exposure is the active actuator (within bounds).
    - ``"power"``: power fallback is active (exposure hit a bound).
    """

    exposure_s: float
    laser1_mw: float
    laser2_mw: float
    reacquire: bool
    control_variable_active: str
    power_fallback: bool

    @staticmethod
    def fixed(exposure_s: float, laser1_mw: float, laser2_mw: float) -> AdaptiveCommand:
        """Construct a constant fixed-mode command (adaptive off).

        The caller applies the same fixed command every plane — zero
        extra per-plane actuator writes beyond the existing stack
        cycle. ``reacquire`` and ``power_fallback`` are both False.
        """
        return AdaptiveCommand(
            exposure_s=exposure_s,
            laser1_mw=laser1_mw,
            laser2_mw=laser2_mw,
            reacquire=False,
            control_variable_active="fixed",
            power_fallback=False,
        )


@dataclass(frozen=True)
class AdaptiveSample:
    """Frozen per-plane trajectory sample (storage contract).

    One row per saved main plane. ``intensity_fraction`` is a list
    with one entry per active channel; inactive channels are NaN
    . ``laser_power_mw`` is a 2-tuple (L1, L2) in mW.

    The HDF5 /adaptive_trajectory group and the Zarr
    /acquisition/adaptive group carry identical field names and units
    — this dataclass is the canonical in-memory representation both
    writers serialize.
    """

    plane_index: int
    intensity_fraction: list[float]
    exposure_s: float
    laser_power_mw: tuple[float, float]
    control_variable_active: str
    reacquired: bool
    power_fallback: bool

    def __post_init__(self) -> None:
        # Normalize inactive-channel entries to NaN so the saved
        # trajectory carries the convention regardless of
        # what the caller passed. Use object.__setattr__ because the
        # dataclass is frozen.
        normalized = [
            v if v is not None else float("nan") for v in self.intensity_fraction
        ]
        object.__setattr__(self, "intensity_fraction", normalized)


# NOTE on the ``reacquired`` field name: it is kept for schema-a
# (identical field names across HDF5 /adaptive_trajectory and Zarr
# /acquisition/adaptive). Despite the name, it records the
# controller's *decision* to re-acquire (mirroring AdaptiveCommand.
# reacquire), NOT whether the plane was actually re-acquired — the
# current worker does not implement re-grab logic. Downstream tools
# should treat a True value as "the controller requested a re-acquire",
# not as proof that a re-acquired frame is present. Renaming the stored
# field would break the schema-a contract and existing saved data.


def nan_inactive(intensities: list[float], active_mask: list[bool]) -> list[float]:
    """Return a copy of ``intensities`` with inactive channels replaced
    by NaN (convention for the saved trajectory)."""
    return [
        v if active else float("nan")
        for v, active in zip(intensities, active_mask, strict=False)
    ]


def is_nan(value: float) -> bool:
    """NaN check that works on Python 3.12 (math.isnan)."""
    return isinstance(value, float) and math.isnan(value)
