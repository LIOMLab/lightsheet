"""Branch-coverage closure for ``lightsheet.gui.widgets.channel_radio``.

The single missing branch is ``129->exit`` in ``click_button``: the
``if btn is not None:`` False arc — i.e. clicking a button at an
out-of-range channel index is a no-op (no AttributeError, no signal
emission). This is the defensive guard for an invalid ``idx`` argument.

Behavior test (AGENTS.md §5) — runs the real widget under
``QT_QPA_PLATFORM=offscreen`` and asserts on the runtime postcondition
(no exception, no signal emitted, no button state change).
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from lightsheet.gui.widgets.channel_radio import ChannelRadio


def test_click_button_with_invalid_idx_is_noop(qtbot) -> None:  # noqa: ANN001
    """click_button(idx) where idx is out of range -> btn is None -> the
    ``if btn is not None:`` guard is False -> no click, no signal, no
    exception (branch 129->exit).

    The QButtonGroup only has ids 0 and 1; idx=99 returns None from
    ``button(99)``. The guard must short-circuit cleanly.
    """
    radio = ChannelRadio(wl1=555, wl2=647)
    qtbot.addWidget(radio)

    # L1 (idx 0) is checked by default; capture the idClicked signal to
    # prove no emission fires for the invalid click.
    emitted: list[int] = []
    radio.idClicked.connect(lambda i: emitted.append(i))

    # Sanity: a valid click DOES emit (proves the signal wiring is live
    # and the no-emit below is due to the guard, not a broken signal).
    radio.click_button(1)
    assert emitted == [1], "valid click must emit idClicked"

    # The invalid-index call must not raise and must not emit.
    radio.click_button(99)
    assert emitted == [1], "invalid idx must not emit idClicked"
    # L1 selection state unchanged by the invalid click.
    assert radio.is_checked(0) is False
    assert radio.is_checked(1) is True
