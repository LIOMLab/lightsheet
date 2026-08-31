"""Standalone mock laser HAL for demo mode — implements the ``ILaser`` ABC.

Tracks laser state (``active`` bool + ``power`` float, mW) in software with
no hardware dependency. ``off()`` is synchronous and ``set_power`` clamps to
``max_power`` — both are safety-critical (E-stop path must not atrophy).
"""

import logging
import threading

from lightsheet.hal.interfaces import ILaser

logger = logging.getLogger(__name__)


class MockLaser(ILaser):
    """Mock single-channel laser for demo mode — implements ILaser with no hardware I/O.

    ``off()`` is synchronous (E-stop kill path). ``set_power`` clamps to ``max_power``.
    """

    # Class-level defaults shadow the abstract @property slots before __init__.
    wavelength: int = 0
    power: float = 0.0
    max_power: float = 0.0
    active: bool = False
    label: str = ""
    calibrated: bool = False

    def __init__(
        self,
        wavelength: int,
        max_power_mw: float,
        mw_per_volt: float | None = None,
        label: str = "",
        calibration_curve: object | None = None,
    ) -> None:
        self.error = 0
        self.error_message = ""

        self.wavelength = wavelength
        self.max_power = max_power_mw  # mW (canonical)
        # Kept for symmetry with DAQLaser; unused by the mock (tracks mW directly).
        self.mw_per_volt = mw_per_volt
        self.label = label
        self.calibrated = False

        self.power = 0.0
        self.active = False

        # Per-instance RLock so demo mode exercises the same lock-acquisition
        # paths as the rig. Reentrant so _toggle_laser* can call _write_laser*_power
        # under the same lock without deadlocking.
        self._lock = threading.RLock()

    def on(self) -> None:
        self.active = True
        return None

    def off(self) -> None:
        # E-stop kill path: MUST be synchronous — no thread/queue offload.
        self.active = False
        self.power = 0.0
        return None

    def open(self) -> None:
        return None

    def close(self) -> None:
        return None

    def get_output_power(self) -> float | None:
        # Returns the staged self.power (mW) so L2 readback works in demo mode.
        return self.power

    def set_power(self, mw: float) -> None:
        """Set the staged laser power in milliwatts, clamped to ``[0.0, max_power]``.

        The clamp bounds the maximum power any caller can command, protecting
        the diode against a typo or tamper.
        """
        mw = max(0.0, min(float(mw), self.max_power))
        self.power = mw
        return None
