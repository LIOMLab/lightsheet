"""Standalone mock power meter HAL for demo mode — implements the
``IPowerMeter`` ABC.

``MockPowerMeter`` implements ``IPowerMeter`` from scratch — fully decoupled
from the real ``PM100D`` class internals so real-class refactors cannot
break the mock. It constructs with no hardware dependency and tracks a
synthetic power reading in software.

The mock returns a configurable synthetic power value (default 0.0 W) so
calibration scripts and tests can exercise the ``IPowerMeter`` surface
without a physical PM100D. ``read_averaged`` is inherited from the mock's
own logic (no DLL, no settling delay needed — but the delay is preserved
for behavioral parity with the real backend).

``zero()`` is a no-op (no hardware to zero). ``open()`` / ``close()`` are
no-ops (no DLL to load, no session to open).
"""

import logging
import time

from lightsheet.hal.interfaces import IPowerMeter

logger = logging.getLogger(__name__)


class MockPowerMeter(IPowerMeter):
    """Mock power meter for demo mode — implements IPowerMeter with no
    hardware I/O.

    Tracks a synthetic ``power_w`` (float, watts) in software. The value
    can be set via ``set_simulated_power`` for test scenarios, or left at
    the default (0.0 W) for a passive ambient reading.
    """

    def __init__(
        self,
        wavelength_nm: float = 561.0,
        simulated_power_w: float = 0.0,
    ) -> None:
        # HAL error surface — cleared on construct.
        self.error = 0
        self.error_message = ""

        self._wavelength_nm = float(wavelength_nm)
        self._simulated_power_w = float(simulated_power_w)
        self._zero_offset = 0.0
        self._opened = False

    def open(self) -> None:
        """No-op lifecycle verb — MockPowerMeter has no DLL to load or
        session to open. Sets ``_opened=True`` so ``read_power`` can
        verify the meter was opened before reading.
        """
        self._opened = True
        return None

    def close(self) -> None:
        """No-op lifecycle verb — MockPowerMeter has no session to close."""
        self._opened = False
        return None

    def read_power(self) -> float:
        """Return the simulated power in watts (SI).

        Subtracts the zero offset if ``zero()`` was called. Returns the
        synthetic value — no hardware I/O.
        """
        if not self._opened:
            logger.warning("MockPowerMeter.read_power called before open()")
        return self._simulated_power_w - self._zero_offset

    def read_power_mw(self) -> float:
        """Read the simulated optical power in milliwatts (convenience)."""
        return self.read_power() * 1000.0

    def read_averaged(
        self, n_samples: int, delay_s: float = 0.5
    ) -> float:
        """Take ``n_samples`` readings, discard the first, return the mean.

        For the mock, all readings are identical (no noise model), so the
        mean equals the simulated value. The delay is preserved for
        behavioral parity with the real backend (so timing-sensitive tests
        behave the same), but can be set to 0 for fast test execution.
        """
        if n_samples < 2:
            return self.read_power()
        readings: list[float] = []
        for i in range(n_samples):
            if i > 0 and delay_s > 0:
                time.sleep(delay_s)
            readings.append(self.read_power())
        readings = readings[1:]
        return sum(readings) / len(readings)

    def zero(self) -> None:
        """No-op zero — records the current simulated power as the zero
        offset so subsequent readings subtract it (simulating a dark
        offset measurement). For the mock this is a software-only
        subtraction.
        """
        self._zero_offset = self._simulated_power_w
        logger.info("MockPowerMeter zero offset set to %.6f W", self._zero_offset)

    def set_simulated_power(self, power_w: float) -> None:
        """Set the simulated power reading (watts). Test helper — not part
        of the ``IPowerMeter`` ABC. Allows a test to inject a known power
        value for assertion scenarios.
        """
        self._simulated_power_w = float(power_w)

    def __enter__(self) -> "MockPowerMeter":
        self.open()
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
