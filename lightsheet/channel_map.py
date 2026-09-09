"""Channel-reversal mechanism for galvo/ETL scan channels.

Pure-logic, frozen dataclass. No Qt, no numpy, no SDK imports — testable with
a direct import + call + assert.

Hardware limits:
- Galvo AO: ±10 V (NI-6363 AO range)
- ETL drive: 0-5 V (Optotune EL-10-30 analog input; the lens driver maps
  this to its 0-292.84 mA coil-current range internally)
"""

import typing
from dataclasses import dataclass
from enum import Enum


class Channel(Enum):
    """The four galvo/ETL scan channels written by the SigGen AO task."""

    GALVO_LEFT = "galvo_left"
    GALVO_RIGHT = "galvo_right"
    ETL_LEFT = "etl_left"
    ETL_RIGHT = "etl_right"


@dataclass(frozen=True)
class ChannelMap:
    """Frozen channel-reversal + per-channel clamp policy.

    ``galvo_left_right_swap`` is the one-line flip; ``order_galvos`` is the
    only call site that needs to change. The clamp methods hard-cap output
    to the datasheet-verified range regardless of input magnitude.
    """

    galvo_left_right_swap: bool = False
    # Per-channel voltage clamps. Both operate in volts — the galvo AO
    # writes ±10 V directly, and the ETL AO writes 0-5 V which the lens
    # driver maps to its coil-current range internally.
    galvo_voltage_limit: float = 10.0  # ±10 V (NI-6363 AO range)
    etl_voltage_limit: float = 5.0  # 0-5 V (EL-10-30 analog input range)

    def order_galvos(
        self, left: typing.Any, right: typing.Any
    ) -> tuple[typing.Any, typing.Any]:
        """Return galvo (left, right) setpoints, swapped if configured."""
        return (right, left) if self.galvo_left_right_swap else (left, right)

    def clamp_galvo(self, v: float) -> float:
        """Clamp a galvo voltage to ±galvo_voltage_limit."""
        return max(-self.galvo_voltage_limit, min(self.galvo_voltage_limit, v))

    def clamp_etl(self, v: float) -> float:
        """Clamp an ETL drive voltage to [0, etl_voltage_limit] V."""
        return max(0.0, min(self.etl_voltage_limit, v))
