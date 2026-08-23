"""
RFR-04 pure-logic tests for lightsheet.channel_map.

ChannelMap is the channel-reversal MECHANISM (RFR-04): a frozen, pure-logic
dataclass that swaps galvo left/right ordering and clamps per-channel
voltage/current to the AGENTS.md §2 hardware limits (±10 V galvos /
0–292.84 mA ETLs). The actual flip against real hardware is rig-verification
work (HW2-02) and is explicitly NOT attempted here.

Mirrors the established test/test_waveforms.py style: direct import, no
fixtures, no mocks, single-assert tests with docstrings. No static-source
grep (AGENTS.md §5).
"""

import dataclasses

import pytest

from lightsheet.channel_map import Channel, ChannelMap


# --------------------------------------------------------------------------- #
# Channel enum
# --------------------------------------------------------------------------- #


def test_channel_enum_members() -> None:
    """Channel enum exposes GALVO_LEFT, GALVO_RIGHT, ETL_LEFT, ETL_RIGHT."""
    assert Channel.GALVO_LEFT is not None
    assert Channel.GALVO_RIGHT is not None
    assert Channel.ETL_LEFT is not None
    assert Channel.ETL_RIGHT is not None
    names = {c.name for c in Channel}
    assert names == {"GALVO_LEFT", "GALVO_RIGHT", "ETL_LEFT", "ETL_RIGHT"}


# --------------------------------------------------------------------------- #
# order_galvos — channel-reversal mechanism
# --------------------------------------------------------------------------- #


def test_order_galvos_no_swap() -> None:
    """galvo_left_right_swap=False leaves left/right order unchanged."""
    cm = ChannelMap(galvo_left_right_swap=False)
    assert cm.order_galvos(left=1.0, right=2.0) == (1.0, 2.0)


def test_order_galvos_swap() -> None:
    """galvo_left_right_swap=True swaps left/right."""
    cm = ChannelMap(galvo_left_right_swap=True)
    assert cm.order_galvos(left=1.0, right=2.0) == (2.0, 1.0)


# --------------------------------------------------------------------------- #
# clamp_galvo — ±10 V (NI-6363 AO range, AGENTS.md §2)
# --------------------------------------------------------------------------- #


def test_clamp_galvo() -> None:
    """Galvo voltage clamped to ±galvo_voltage_limit; in-range unchanged."""
    cm = ChannelMap()
    assert cm.clamp_galvo(12.5) == 10.0
    assert cm.clamp_galvo(-12.5) == -10.0
    assert cm.clamp_galvo(5.0) == 5.0


# --------------------------------------------------------------------------- #
# clamp_etl — 0–292.84 mA (Optotune EL-10-30 datasheet, AGENTS.md §2)
# --------------------------------------------------------------------------- #


def test_clamp_etl() -> None:
    """ETL current clamped to [0, etl_current_limit_ma]; in-range unchanged."""
    cm = ChannelMap()
    assert cm.clamp_etl(300.0) == 292.84
    assert cm.clamp_etl(-5.0) == 0.0
    assert cm.clamp_etl(150.0) == 150.0


# --------------------------------------------------------------------------- #
# frozen dataclass
# --------------------------------------------------------------------------- #


def test_channel_map_frozen() -> None:
    """ChannelMap is frozen: replace() works, direct assignment raises."""
    cm = ChannelMap(galvo_left_right_swap=False)
    new_cm = dataclasses.replace(cm, galvo_left_right_swap=True)
    assert new_cm.galvo_left_right_swap is True
    assert cm.galvo_left_right_swap is False  # original unchanged
    with pytest.raises(dataclasses.FrozenInstanceError):
        cm.galvo_left_right_swap = True  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# default constructor
# --------------------------------------------------------------------------- #


def test_channel_map_defaults() -> None:
    """Default ChannelMap() has swap=False, galvo 10V, ETL 292.84 mA."""
    cm = ChannelMap()
    assert cm.galvo_left_right_swap is False
    assert cm.galvo_voltage_limit == 10.0
    assert cm.etl_current_limit_ma == 292.84
