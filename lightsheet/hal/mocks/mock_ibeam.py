"""Standalone mock IBeam HAL for demo mode (D-08).

``MockIBeam`` implements ``IIBeam`` from scratch — fully decoupled from
the real ``IBeam`` class internals so real-class refactors cannot break
the mock and the mock's behavior is explicit and auditable (D-08). It
constructs with no serial dependency and tracks the laser state
(``_is_on`` bool + ``_power`` int) in software.

**Synchronous ``off()`` is preserved (AGENTS.md §2 — Class IIIB laser
safety).** ``MockIBeam.off()`` sets ``_is_on=False`` and ``_power=0`` and
returns ``None`` immediately — no thread/queue offload. The E-stop kill
path (``updateUi_estop_pressed`` → ``ibeam.off()``) drives the laser off
synchronously on the GUI thread; a mock that queued ``off()`` would let
the controller's E-stop path atrophy under demo mode, masking a
regression that would delay laser shutdown on the rig.

**Max Power clamping is preserved (AGENTS.md §2).** ``MockIBeam.set_power``
clamps the commanded power to ``max_power`` at the HAL boundary, exactly
as the real ``IBeam.set_power`` does.

The controller-read attributes (``wavelength`` / ``max_power``) and the
internal state (``_power`` / ``_is_on``) are declared as plain class-level
defaults so they override the abstract ``@property`` slots on
``IIBeamCore`` (Python's ABC check runs at instantiation, before
``__init__`` sets instance attributes — same fix as MockCamera in Plan
01). ``__init__`` then sets the real synthetic values as instance
attributes, which is the surface the controller reads (D-04).

The lifecycle verbs (``open`` / ``close`` / ``on`` / ``off`` /
``enable_channel``) are no-ops (no serial I/O) ending with ``return None``
(AGENTS.md §10) so the controller's call sites are unchanged between real
and demo runs. The WR-01 iBeam fix (the ``on()`` error-between-sub-
commands guard) is a separate Wave 4 plan for the REAL class; the mock
tracks state directly (``on()`` sets ``_is_on=True`` unconditionally
because there is no firmware to reject the command).
"""

import logging

from lightsheet.hal.interfaces import IIBeam

logger = logging.getLogger(__name__)


class MockIBeam(IIBeam):
    """Mock Toptica iBeam Smart serial laser for demo mode — implements
    IIBeam with no serial I/O.

    Tracks ``_is_on`` (bool) and ``_power`` (int, microwatts) in software.
    ``off()`` is synchronous (E-stop kill path — AGENTS.md §2).
    ``set_power`` clamps to ``max_power`` (AGENTS.md §2).
    """

    # Override the IIBeamCore @property abstract slots with plain class
    # attributes so the class is concrete (instantiable). __init__ sets the
    # real synthetic values as instance attributes.
    wavelength: int = 0
    max_power: int = 0
    _power: int = 0
    _is_on: bool = False

    def __init__(self, port: str | None = None) -> None:
        # HAL error surface (AGENTS.md §10) — cleared on construct.
        self.error = 0
        self.error_message = ""

        # Synthetic defaults mirroring the real IBeam config.ini defaults
        # (lightsheet/hal/real/ibeam.py _cfg_settings). Hardcoded so the
        # mock constructs with no config.ini read (D-09 — deterministic).
        self.port = port if port is not None else "COM4"
        self.baud_rate = 115200
        self.channel = 1
        self.wavelength = 640  # In nm (iBeam Smart 640)
        self.max_power = 150000  # In uW (150 mW diode limit, rig-confirmed)

        # Laser state — tracked in software (no serial I/O).
        self._power = 0
        self._is_on = False

    # ------------------------------------------------------------------ #
    # Lifecycle verbs — no-ops (no serial I/O) ending with ``return None``
    # (AGENTS.md §10). off() is synchronous — E-stop kill path (AGENTS.md §2).
    # ------------------------------------------------------------------ #

    def open(self) -> None:
        # The real IBeam.open() opens the serial port, disables echo, and
        # enables the configured channel. The mock has no serial port, so
        # just record that open() was called (no-op).
        return None

    def close(self) -> None:
        # The real IBeam.close() turns the laser off and releases the
        # serial port. The mock just ensures the laser is off.
        self._is_on = False
        return None

    def on(self) -> None:
        # The real IBeam.on() sends `laser on` then re-enables the channel,
        # guarding _is_on on the error surface (WR-01 fix is Wave 4 for the
        # real class). The mock has no firmware to reject the command, so
        # it sets _is_on=True directly.
        self._is_on = True
        return None

    def off(self) -> None:
        # E-stop kill path (AGENTS.md §2): MUST be synchronous — set
        # _is_on=False and _power=0 and return None immediately, with no
        # thread/queue offload. The GUI-thread E-stop handler calls this
        # directly; offloading it would break the synchronous-off safety
        # contract for a Class IIIB laser.
        self._is_on = False
        self._power = 0
        return None

    def enable_channel(self, channel: int | None = None) -> None:
        # The real IBeam.enable_channel() sends `enable <ch>` so channel
        # power commands take effect. The mock has no firmware gating, so
        # this is a no-op.
        return None

    # ------------------------------------------------------------------ #
    # Setters (IIBeamCore surface).
    # ------------------------------------------------------------------ #

    def set_power(self, power_uw: int) -> None:
        """Set channel power in microwatts, clamped to [0, max_power].

        The clamp is a physical-safety control (AGENTS.md §2): it bounds
        the maximum power any caller can command, protecting the diode
        against a typo or tamper. The mock preserves the clamp in
        software so the controller's safety checks do not atrophy under
        demo mode.
        """
        power_uw = max(0, min(int(power_uw), self.max_power))
        self._power = power_uw
        return None

    # ------------------------------------------------------------------ #
    # Extended surface (IIBeam).
    # ------------------------------------------------------------------ #

    def reboot(self) -> None:
        # The real IBeam.reboot() sends `reset system` to recover from
        # protocol desync. The mock has no protocol to desync, so no-op.
        return None

    def get_output_power(self) -> int:
        # The real IBeam.get_output_power() sends `show level power` and
        # parses the reply. The mock returns the last commanded power.
        return self._power

    def is_enabled(self) -> bool:
        # The real IBeam.is_enabled() sends `status laser` and parses ON/OFF.
        # The mock returns the tracked _is_on state.
        return self._is_on

    def status_laser(self) -> bool:
        # Alias for is_enabled() — the controller's status-poll path.
        return self._is_on

    def show_level_power(self) -> list[str]:
        # The real IBeam.show_level_power() sends `show level power` and
        # returns the reply lines. The mock returns a synthetic reply
        # matching the real format so any future reply-parsing test has a
        # deterministic fixture.
        return [f"CH{self.channel}, PWR: {self._power / 1000.0:.3f} mW", "[OK]"]
