"""Channel-reversal mechanism for galvo/ETL scan channels (RFR-04).

Pure-logic, frozen dataclass. No Qt, no numpy, no SDK imports — testable with
a direct import + call + assert (mirrors ``lightsheet.waveforms``).

The mechanism ships here; the actual left/right flip against real hardware is
rig-verification work (HW2-02) and is NOT attempted from the dev Mac
(AGENTS.md §13). A future plan wires this into ``lightsheet.hal.real.siggen``'s
four ``np.stack((...))`` write sites — this module only defines the contract.

Hardware limits enforced per AGENTS.md §2:
- Galvo AO: ±10 V (NI-6363 AO range)
- ETL current: 0–292.84 mA (Optotune EL-10-30 datasheet)
"""

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

    ``galvo_left_right_swap`` is the one-line flip the rig-verification task
    (HW2-02) toggles; ``order_galvos`` is the only call site that needs to
    change. The clamp methods hard-cap output to the datasheet-verified range
    regardless of input magnitude, so a future siggen write site inherits a
    pre-tested clamp rather than hand-rolling one at the write site
    (threat T-05-03 mitigation).
    """

    galvo_left_right_swap: bool = False
    # Per-channel voltage/current clamps (AGENTS.md §2 / RFR-04)
    galvo_voltage_limit: float = 10.0  # ±10 V (NI-6363 AO range)
    etl_current_limit_ma: float = 292.84  # 0–292.84 mA (Optotune EL-10-30)

    def order_galvos(self, left: float, right: float) -> tuple[float, float]:
        """Return galvo (left, right) setpoints, swapped if configured."""
        return (right, left) if self.galvo_left_right_swap else (left, right)

    def clamp_galvo(self, v: float) -> float:
        """Clamp a galvo voltage to ±galvo_voltage_limit."""
        return max(-self.galvo_voltage_limit, min(self.galvo_voltage_limit, v))

    def clamp_etl(self, v: float) -> float:
        """Clamp an ETL current (mA) to [0, etl_current_limit_ma]."""
        return max(0.0, min(self.etl_current_limit_ma, v))
