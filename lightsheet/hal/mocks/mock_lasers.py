"""Standalone mock Lasers HAL for demo mode (D-08).

``MockLasers`` implements ``ILasers`` from scratch — fully decoupled from
the real ``Lasers`` class internals so real-class refactors cannot break
the mock and the mock's behavior is explicit and auditable (D-08). It
constructs with no NI-DAQmx dependency and tracks the 2-channel laser
state (``laser1_active`` / ``laser2_active`` flags + ``laser1_power`` /
``laser2_power`` floats) in software.

**Max Power clamping is preserved (AGENTS.md §2 — physical safety).**
``MockLasers.set_power(channel, value)`` clamps the commanded power to the
configured ``Max Power`` for that channel at the HAL boundary, exactly as
the real ``Lasers._update_setpoints`` does. A mock that removed the clamp
would let the controller's safety checks atrophy under demo mode, masking
a regression that would over-drive the laser AO channels on the rig.

The controller-read attributes (``laser1_wavelength`` /
``laser1_max_power`` / ``laser1_power`` / ``laser1_active`` / and the
channel-2 counterparts) are declared as plain class-level defaults so
they override the abstract ``@property`` slots on ``ILasersCore`` (Python's
ABC check runs at instantiation, before ``__init__`` sets instance
attributes — same fix as MockCamera in Plan 01). ``__init__`` then sets
the real synthetic values as instance attributes, which is the surface
the controller reads (D-04).

The lifecycle verbs (``laser1_on`` / ``laser1_off`` / ``laser2_on`` /
``laser2_off``) toggle the active flags in software (no DAQ write) and
end with ``return None`` (AGENTS.md §10) so the controller's call sites
are unchanged between real and demo runs.
"""

import logging

from lightsheet.hal.interfaces import ILasers

logger = logging.getLogger(__name__)


class MockLasers(ILasers):
    """Mock 2-channel NI-DAQ AO laser power control for demo mode —
    implements ILasers with no DAQ hardware.

    Tracks ``laser1_active`` / ``laser2_active`` (bool) and
    ``laser1_power`` / ``laser2_power`` (float) in software.
    ``set_power(channel, value)`` clamps to the configured ``Max Power``
    for that channel (AGENTS.md §2 — physical-safety control preserved
    through the mock refactor).
    """

    # Override the ILasersCore @property abstract slots with plain class
    # attributes so the class is concrete (instantiable). __init__ sets the
    # real synthetic values as instance attributes.
    laser1_wavelength: int = 0
    laser2_wavelength: int = 0
    laser1_max_power: float = 0.0
    laser2_max_power: float = 0.0
    laser1_power: float = 0.0
    laser2_power: float = 0.0
    laser1_active: bool = False
    laser2_active: bool = False

    def __init__(self) -> None:
        # HAL error surface (AGENTS.md §10) — cleared on construct.
        self.error = 0
        self.error_message = ""

        # Synthetic defaults mirroring the real Lasers config.ini defaults
        # (lightsheet/hal/real/lasers.py _cfg_settings). Hardcoded so the
        # mock constructs with no config.ini read (D-09 — deterministic).
        # The real defaults are 405 nm / 5.0 V max for both channels; the
        # rig's config.ini overlays the actual wavelengths (e.g. 488/640).
        # The mock picks 488/640 so the GUI's wavelength labels show the
        # two real lasers' wavelengths under demo (more useful for a dev
        # box than two identical 405 nm labels).
        self.ao_terminals = "/Dev7/ao0:1"
        self.laser1_wavelength = 488
        self.laser2_wavelength = 640
        self.laser1_max_power = 5.0  # In Volts — HAL-boundary clamp
        self.laser2_max_power = 5.0  # In Volts — HAL-boundary clamp
        self.laser1_power = 0.0
        self.laser2_power = 0.0
        self.laser1_active = False
        self.laser2_active = False

        # Internal setpoints (mirror the real Lasers surface). The mock
        # keeps them in sync with the active/power state so a future
        # conformance test can compare the two paths.
        self._laser1_setpoint = 0
        self._laser2_setpoint = 0

    # ------------------------------------------------------------------ #
    # Lifecycle verbs — toggle active flags in software (no DAQ write).
    # End with ``return None`` (AGENTS.md §10).
    # ------------------------------------------------------------------ #

    def laser1_on(self) -> None:
        self.laser1_active = True
        # Stage the clamped setpoint (mirrors the real Lasers.laser1_on
        # clamp expression — AGENTS.md §2).
        self._laser1_setpoint = min(self.laser1_power, self.laser1_max_power)
        self._update_setpoints()
        return None

    def laser1_off(self) -> None:
        self.laser1_active = False
        self._laser1_setpoint = 0
        self._update_setpoints()
        return None

    def laser1_toggle(self) -> None:
        if self.laser1_active:
            self.laser1_off()
        else:
            self.laser1_on()
        return None

    def laser2_on(self) -> None:
        self.laser2_active = True
        self._laser2_setpoint = min(self.laser2_power, self.laser2_max_power)
        self._update_setpoints()
        return None

    def laser2_off(self) -> None:
        self.laser2_active = False
        self._laser2_setpoint = 0
        self._update_setpoints()
        return None

    def laser2_toggle(self) -> None:
        if self.laser2_active:
            self.laser2_off()
        else:
            self.laser2_on()
        return None

    # ------------------------------------------------------------------ #
    # Setters / internal update (ILasers extended surface).
    # ------------------------------------------------------------------ #

    def set_power(self, channel: int, value: float) -> None:
        """Set the staged power for a channel, clamped to [0, max_power].

        The clamp is a physical-safety control (AGENTS.md §2): it bounds
        the maximum power any caller can command, protecting the laser AO
        channels against a typo or tamper. The mock preserves the clamp
        in software so the controller's safety checks do not atrophy
        under demo mode.
        """
        if channel == 1:
            self.laser1_power = max(0.0, min(float(value), self.laser1_max_power))
            if self.laser1_active:
                self._laser1_setpoint = self.laser1_power
        elif channel == 2:
            self.laser2_power = max(0.0, min(float(value), self.laser2_max_power))
            if self.laser2_active:
                self._laser2_setpoint = self.laser2_power
        else:
            raise ValueError(f"invalid laser channel {channel!r} (expected 1 or 2)")
        self._update_setpoints()
        return None

    def _update_setpoints(self) -> None:
        # Clamp setpoints to [0, Max Power] at the HAL boundary before any
        # DAQ write attempt — physical-safety control (AGENTS.md §2). The
        # mock has no DAQ write, but keeps the clamp so the staged
        # setpoints reflect what the real HAL would actually drive.
        self._laser1_setpoint = max(
            0, min(self._laser1_setpoint, self.laser1_max_power)
        )
        self._laser2_setpoint = max(
            0, min(self._laser2_setpoint, self.laser2_max_power)
        )
        return None
