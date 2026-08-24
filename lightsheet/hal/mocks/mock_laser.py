"""Standalone mock laser HAL for demo mode — implements the unified
``ILaser`` ABC (mW-canonical).

``MockLaser`` implements ``ILaser`` from scratch — fully decoupled from
the real ``DAQLaser`` / ``IBeamSmartLaser`` class internals so real-class
refactors cannot break the mock and the mock's behavior is explicit and
auditable. It constructs with no hardware dependency and tracks the laser
state (``active`` bool + ``power`` float, mW) in software.

**Synchronous ``off()`` is preserved (AGENTS.md §2 — Class IIIB laser
safety).** ``MockLaser.off()`` sets ``active=False`` and ``power=0.0`` and
returns ``None`` immediately — no thread/queue offload. The E-stop kill
path (``updateUi_estop_pressed`` → ``laser.off()``) drives the laser off
synchronously on the GUI thread; a mock that queued ``off()`` would let
the controller's E-stop path atrophy under demo mode, masking a
regression that would delay laser shutdown on the rig.

**Max Power clamping is preserved (AGENTS.md §2).** ``MockLaser.set_power``
clamps the commanded mW power to ``max_power`` at the HAL boundary, exactly
as the real ``DAQLaser.set_power`` does. A mock that dropped the clamp
would let the controller's safety checks atrophy under demo mode.

The controller-read attributes (``wavelength`` / ``power`` / ``max_power``
/ ``active`` / ``label``) are declared as plain class-level defaults so
they have sensible values before ``__init__`` runs (the ABC declares them
as annotations, so the override is not required for ABC satisfaction, but
the defaults are kept for consistency with the other mock families).
``__init__`` then sets the real synthetic values as instance attributes,
which is the surface the controller reads.

The lifecycle verbs (``on`` / ``off``) are no-ops over hardware (no DAQ
write, no serial I/O) ending with ``return None`` (AGENTS.md §10) so the
controller's call sites are unchanged between real and demo runs.
``mw_per_volt`` is accepted for symmetry with ``DAQLaser`` but is unused
by the mock's own logic (the mock tracks mW directly).
"""

import logging
import threading

from lightsheet.hal.interfaces import ILaser

logger = logging.getLogger(__name__)


class MockLaser(ILaser):
    """Mock single-channel laser for demo mode — implements ILaser with no
    hardware I/O.

    Tracks ``active`` (bool) and ``power`` (float, mW) in software.
    ``off()`` is synchronous (E-stop kill path — AGENTS.md §2).
    ``set_power`` clamps to ``max_power`` (mW, AGENTS.md §2).
    """

    # Class-level defaults provide pre-__init__ synthetic values (the ABC
    # declares these as annotations, so the override is no longer required
    # for ABC satisfaction, but the defaults are kept so the mock has
    # sensible values before __init__ runs). __init__ sets the real
    # synthetic values as instance attributes.
    wavelength: int = 0
    power: float = 0.0
    max_power: float = 0.0
    active: bool = False
    label: str = ""
    # Mirrors DAQLaser.calibrated — False on the mock (demo path has no
    # measured curve). Declared as a class default so the attribute exists
    # pre-__init__ (the ABC declares it as an annotation).
    calibrated: bool = False

    def __init__(
        self,
        wavelength: int,
        max_power_mw: float,
        mw_per_volt: float | None = None,
        label: str = "",
        calibration_curve: object | None = None,
    ) -> None:
        # HAL error surface (AGENTS.md §10) — cleared on construct.
        self.error = 0
        self.error_message = ""

        # Synthetic values mirroring the configured laser. Hardcoded so
        # the mock constructs with no config.ini read (deterministic).
        self.wavelength = wavelength
        self.max_power = max_power_mw  # mW (canonical)
        # Kept for symmetry with DAQLaser; unused by the mock's own logic
        # (the mock tracks mW directly, no V conversion).
        self.mw_per_volt = mw_per_volt
        self.label = label
        # Kept for symmetry with DAQLaser; unused by the mock's own logic.
        # The mock tracks mW directly (no V conversion), so a calibration
        # curve would have no effect — accepted but ignored, and
        # `calibrated` stays False so the demo readback label shows the
        # "(est.)" suffix consistent with an uncalibrated rig.
        self.calibrated = False

        # Laser state — tracked in software (no hardware I/O).
        self.power = 0.0
        self.active = False

        # Per-instance RLock — the controller's daemon-thread write paths
        # (_write_laser*_power, _toggle_laser*) and the L2 gated status
        # poll acquire self.lasers[i]._lock. The lock must live on every
        # ILaser instance (D-02 lock relocation), including the mock, so
        # demo mode exercises the same lock-acquisition paths as the rig.
        # Reentrant (RLock) so _toggle_laser* can call _write_laser*_power
        # under the same lock without deadlocking.
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ #
    # Lifecycle verbs — no-ops over hardware (no DAQ write, no serial I/O).
    # End with ``return None`` (AGENTS.md §10). off() is synchronous —
    # E-stop kill path (AGENTS.md §2).
    # ------------------------------------------------------------------ #

    def on(self) -> None:
        # The real DAQLaser.on() writes the staged power to the DAQ AO
        # channel. The mock has no hardware to fail against, so it sets
        # active=True unconditionally (the mock has no failure mode).
        self.active = True
        return None

    def off(self) -> None:
        # E-stop kill path (AGENTS.md §2): MUST be synchronous — set
        # active=False and power=0.0 and return None immediately, with no
        # thread/queue offload. The GUI-thread E-stop handler calls this
        # directly; offloading it would break the synchronous-off safety
        # contract for a Class IIIB laser.
        self.active = False
        self.power = 0.0
        return None

    def open(self) -> None:
        # No-op lifecycle verb (AGENTS.md §10). MockLaser has no hardware
        # to open — the controller's ``self.lasers[i].open()`` call site
        # works uniformly across real and demo backends. Returns None so
        # the ILaser open() contract is satisfied.
        return None

    def close(self) -> None:
        # No-op lifecycle verb (AGENTS.md §10). MockLaser has no hardware
        # to release — mirrors ``open()``. Returns None.
        return None

    def get_output_power(self) -> float | None:
        # MockLaser has no hardware readback. Returns the staged
        # ``self.power`` (mW) so the controller's L2 readback field works
        # uniformly in demo mode (degrades to the commanded value, same as
        # DAQLaser). Never returns None — the staged value is always
        # available; the None return is part of the ILaser contract for
        # backends with a real readback that can fail.
        return self.power

    # ------------------------------------------------------------------ #
    # Setters (ILaser surface).
    # ------------------------------------------------------------------ #

    def set_power(self, mw: float) -> None:
        """Set the staged laser power in milliwatts, clamped to
        ``[0.0, max_power]``.

        The clamp is a physical-safety control (AGENTS.md §2): it bounds
        the maximum power any caller can command, protecting the diode
        against a typo or tamper. The mock preserves the clamp in software
        so the controller's safety checks do not atrophy under demo mode.
        """
        mw = max(0.0, min(float(mw), self.max_power))
        self.power = mw
        return None
