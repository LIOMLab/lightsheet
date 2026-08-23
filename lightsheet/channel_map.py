"""Channel-reversal mechanism for galvo/ETL scan channels (RFR-04).

Pure-logic, frozen dataclass. No Qt, no numpy, no SDK imports — testable with
a direct import + call + assert (mirrors ``lightsheet.waveforms``).

The mechanism ships here; the actual left/right flip against real hardware is
rig-verification work (HW2-02) and is NOT attempted from the dev Mac
(AGENTS.md §13). A future plan wires this into ``lightsheet.hal.real.siggen``'s
four ``np.stack((...))`` write sites — this module only defines the contract.

Hardware limits enforced per AGENTS.md §2:
- Galvo AO: ±10 V (NI-6363 AO range)
- ETL drive: 0–5 V (Optotune EL-10-30 analog input range; the DAQ AO
  channel drives the ETL's 0–5 V analog input, which the lens driver
  maps to its 0–292.84 mA coil-current range internally)
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
    # Per-channel voltage clamps (AGENTS.md §2 / RFR-04). Both clamps
    # operate in the volts the DAQ AO channel writes — the galvo AO
    # channel writes ±10 V directly, and the ETL AO channel writes the
    # 0–5 V analog input that the EL-10-30 lens driver maps to its
    # 0–292.84 mA coil-current range internally. The call sites
    # (SigGen.update_etls / update_all / create_scanner) all pass volts,
    # so the ETL clamp must be a volt-range clamp, not a mA clamp.
    galvo_voltage_limit: float = 10.0  # ±10 V (NI-6363 AO range)
    etl_voltage_limit: float = 5.0  # 0–5 V (EL-10-30 analog input range)

    def order_galvos(self, left: float, right: float) -> tuple[float, float]:
        """Return galvo (left, right) setpoints, swapped if configured."""
        return (right, left) if self.galvo_left_right_swap else (left, right)

    def clamp_galvo(self, v: float) -> float:
        """Clamp a galvo voltage to ±galvo_voltage_limit."""
        return max(-self.galvo_voltage_limit, min(self.galvo_voltage_limit, v))

    def clamp_etl(self, v: float) -> float:
        """Clamp an ETL drive voltage to [0, etl_voltage_limit] V.

        The EL-10-30 analog input range is 0–5 V; the DAQ AO channel
        writes volts, and the lens driver maps that to its 0–292.84 mA
        coil-current range internally. Call sites pass volts (e.g.
        ``update_etls(left_etl=2.5, right_etl=2.5)`` where 2.5 V is the
        mid-range no-current drive), so the clamp ceiling is the 5 V
        analog input limit, not the 292.84 mA coil-current limit.
        """
        return max(0.0, min(self.etl_voltage_limit, v))
