"""GUI-thread-owned observable model for live microscope intent.

A thin ``QObject`` wrapper around an immutable ``MicroscopeSnapshot``. All
mutators run on the GUI thread, validate before replacing the frozen
snapshot, and emit per-domain signals only when the affected value actually
changes. Workers never mutate the model directly; they emit
``AppliedMicroscopeSnapshot`` instances on queued signals that land on
``apply_worker_snapshot``.
"""

from __future__ import annotations

import dataclasses
import logging
import math

from PySide6.QtCore import QObject, Signal, Slot

from lightsheet.state.types import (
    AppliedMicroscopeSnapshot,
    MicroscopeSnapshot,
    SaveMode,
    SaveOptions,
)

logger = logging.getLogger(__name__)


class MicroscopeState(QObject):
    """GUI-thread-owned observable model. Stores one frozen snapshot and
    emits narrow domain signals when intent changes.
    """

    # Per-domain queued-signal contract. Widgets/projections connect to these
    # with bare bound methods; workers publish back through apply_worker_snapshot.
    sig_laser_power_changed = Signal(int, float)
    sig_laser_enabled_changed = Signal(int, bool)
    sig_auto_lasers_changed = Signal(bool, bool)
    sig_save_options_changed = Signal(object)
    sig_lightsheet_line_time_changed = Signal(float)

    def __init__(
        self,
        lightsheet_line_time_s: float | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        line_time = lightsheet_line_time_s
        if (
            not isinstance(line_time, (int, float))
            or isinstance(line_time, bool)
            or not math.isfinite(line_time)
            or line_time <= 0
        ):
            # A non-positive or non-finite source value (bad config key,
            # test double, partially opened camera) would otherwise raise
            # ValueError out of MicroscopeSnapshot.__post_init__ during
            # shell construction — crash at startup. Fall back to a safe
            # positive default and log so the divergence is visible.
            if line_time is not None:
                logger.warning(
                    "Invalid lightsheet_line_time_s %r at construction; "
                    "falling back to 1.0 s",
                    line_time,
                )
            line_time = 1.0
        self._snapshot = MicroscopeSnapshot(lightsheet_line_time_s=line_time)

    # ------------------------------------------------------------------ #
    # Read-only view
    # ------------------------------------------------------------------ #

    def snapshot(self) -> MicroscopeSnapshot:
        """Return the current frozen snapshot (safe to hand to a worker)."""
        return self._snapshot

    @property
    def laser_power_pct(self) -> tuple[float, float]:
        return self._snapshot.laser_power_pct

    @property
    def laser_enabled(self) -> tuple[bool, bool]:
        return self._snapshot.laser_enabled

    @property
    def auto_laser1(self) -> bool:
        return self._snapshot.auto_lasers[0]

    @property
    def auto_laser2(self) -> bool:
        return self._snapshot.auto_lasers[1]

    @property
    def save_options(self) -> SaveOptions:
        return self._snapshot.save_options

    @property
    def lightsheet_line_time_s(self) -> float:
        return self._snapshot.lightsheet_line_time_s

    # ------------------------------------------------------------------ #
    # GUI-thread mutators
    # ------------------------------------------------------------------ #

    def set_laser_power_pct(self, idx: int, pct: float) -> None:
        """Set the staged percent for one laser and emit if it changed."""
        if idx not in (0, 1):
            raise IndexError(f"laser index must be 0 or 1; got {idx}")
        if not isinstance(pct, (int, float)) or isinstance(pct, bool):
            raise ValueError(f"laser power pct must be numeric; got {type(pct)}")
        if not math.isfinite(pct):
            raise ValueError(f"laser power pct must be finite; got {pct}")
        if pct < 0.0 or pct > 100.0:
            raise ValueError(f"laser power pct must be in [0, 100]; got {pct}")

        old = self._snapshot.laser_power_pct[idx]
        if math.isclose(old, pct, rel_tol=1e-9, abs_tol=1e-9):
            return

        new_pcts = list(self._snapshot.laser_power_pct)
        new_pcts[idx] = float(pct)
        self._snapshot = dataclasses.replace(
            self._snapshot,
            laser_power_pct=(new_pcts[0], new_pcts[1]),
        )
        self.sig_laser_power_changed.emit(idx, float(pct))

    def set_laser_enabled(self, idx: int, enabled: bool) -> None:
        """Set the on/off intent for one laser."""
        if idx not in (0, 1):
            raise IndexError(f"laser index must be 0 or 1; got {idx}")
        if not isinstance(enabled, bool):
            raise ValueError(f"laser enabled must be a bool; got {type(enabled)}")

        old = self._snapshot.laser_enabled[idx]
        if old is enabled:
            return

        new_enabled = list(self._snapshot.laser_enabled)
        new_enabled[idx] = enabled
        self._snapshot = dataclasses.replace(
            self._snapshot,
            laser_enabled=(new_enabled[0], new_enabled[1]),
        )
        self.sig_laser_enabled_changed.emit(idx, enabled)

    def set_auto_lasers(self, auto1: bool, auto2: bool) -> None:
        """Set the auto-laser intent pair (sampled on GUI thread at spawn)."""
        if not isinstance(auto1, bool) or not isinstance(auto2, bool):
            raise ValueError(
                f"auto_lasers must be bools; got {type(auto1)}, {type(auto2)}"
            )

        old = self._snapshot.auto_lasers
        if old == (auto1, auto2):
            return

        self._snapshot = dataclasses.replace(
            self._snapshot,
            auto_lasers=(auto1, auto2),
        )
        self.sig_auto_lasers_changed.emit(auto1, auto2)

    def set_save_options(self, save_options: SaveOptions) -> None:
        """Replace the frozen save options; emit if they changed."""
        if not isinstance(save_options, SaveOptions):
            raise ValueError(
                f"save_options must be a SaveOptions instance; got {type(save_options)}"
            )
        if self._snapshot.save_options == save_options:
            return

        self._snapshot = dataclasses.replace(
            self._snapshot,
            save_options=save_options,
        )
        self.sig_save_options_changed.emit(save_options)

    def set_save_mode(self, mode: SaveMode) -> None:
        """Replace only the save mode, preserving the description."""
        if not isinstance(mode, SaveMode):
            raise ValueError(f"mode must be a SaveMode; got {type(mode)}")
        if self._snapshot.save_options.mode == mode:
            return
        self.set_save_options(
            dataclasses.replace(self._snapshot.save_options, mode=mode)
        )

    def set_save_description(self, description: str) -> None:
        """Replace only the save description, preserving the mode."""
        if not isinstance(description, str):
            raise ValueError(
                f"description must be a str; got {type(description)}"
            )
        if self._snapshot.save_options.description == description:
            return
        self.set_save_options(
            dataclasses.replace(
                self._snapshot.save_options,
                description=description,
            )
        )

    def set_lightsheet_line_time_s(self, line_time_s: float) -> None:
        """Set the target camera line time (seconds) and emit if it changed."""
        if not isinstance(line_time_s, (int, float)) or isinstance(line_time_s, bool):
            raise ValueError(
                f"lightsheet_line_time_s must be numeric; got {type(line_time_s)}"
            )
        if not math.isfinite(line_time_s):
            raise ValueError(
                f"lightsheet_line_time_s must be finite; got {line_time_s}"
            )
        if line_time_s <= 0:
            raise ValueError(
                f"lightsheet_line_time_s must be positive; got {line_time_s}"
            )

        old = self._snapshot.lightsheet_line_time_s
        if math.isclose(old, float(line_time_s), rel_tol=1e-9, abs_tol=1e-9):
            return

        self._snapshot = dataclasses.replace(
            self._snapshot,
            lightsheet_line_time_s=float(line_time_s),
        )
        self.sig_lightsheet_line_time_changed.emit(float(line_time_s))

    # ------------------------------------------------------------------ #
    # Worker-applied state slot
    # ------------------------------------------------------------------ #

    @Slot(object)
    def apply_worker_snapshot(self, snapshot: object) -> None:
        """GUI-thread slot for a worker's applied-state readback. Rejects
        wrong payload types and folds only non-None applied fields into the
        live model, emitting per-domain signals for the changed values.
        """
        if not isinstance(snapshot, AppliedMicroscopeSnapshot):
            raise TypeError(
                f"apply_worker_snapshot expects AppliedMicroscopeSnapshot; "
                f"got {type(snapshot)}"
            )

        new = self._snapshot
        power_emits: list[tuple[int, float]] = []
        enabled_emits: list[tuple[int, bool]] = []

        if snapshot.laser_power_pct is not None:
            new = dataclasses.replace(new, laser_power_pct=snapshot.laser_power_pct)
            for idx in (0, 1):
                old = self._snapshot.laser_power_pct[idx]
                new_val = snapshot.laser_power_pct[idx]
                if not math.isclose(old, new_val, rel_tol=1e-9, abs_tol=1e-9):
                    power_emits.append((idx, new_val))

        if snapshot.laser_enabled is not None:
            new = dataclasses.replace(new, laser_enabled=snapshot.laser_enabled)
            for idx in (0, 1):
                old = self._snapshot.laser_enabled[idx]
                new_val = snapshot.laser_enabled[idx]
                if old is not new_val:
                    enabled_emits.append((idx, new_val))

        if snapshot.lightsheet_line_time_s is not None:
            new = dataclasses.replace(
                new,
                lightsheet_line_time_s=snapshot.lightsheet_line_time_s,
            )

        if new == self._snapshot:
            return

        line_time_changed = (
            snapshot.lightsheet_line_time_s is not None
            and not math.isclose(
                self._snapshot.lightsheet_line_time_s,
                snapshot.lightsheet_line_time_s,
                rel_tol=1e-9,
                abs_tol=1e-9,
            )
        )

        self._snapshot = new

        for idx, val in power_emits:
            self.sig_laser_power_changed.emit(idx, val)
        for idx, val in enabled_emits:
            self.sig_laser_enabled_changed.emit(idx, val)

        if line_time_changed:
            self.sig_lightsheet_line_time_changed.emit(
                self._snapshot.lightsheet_line_time_s
            )
