"""ChannelRadio — a compact L1/L2 display-selector widget for the
ImageView area.

A ``QButtonGroup`` (exclusive) wrapping two checkable ``QToolButton``s,
labeled ``L1 {wl1}`` / ``L2 {wl2}`` from the live ``ILaser`` instances.
Shown only when both auto-laser checkboxes are checked (the multi-channel
activator); hidden otherwise (single-channel back-compat — the radio is
HIDDEN, not disabled, so the ImageView area stays visually identical to
today's single-channel experience).

The widget is expected to live inside a fixed-height container (created
by the shell at hardware_init) so its show/hide toggles do NOT reflow the
parent layout — the container reserves the layout slot regardless of the
radio's visibility, and only the inner radio shows/hides.

The widget uses QDarkStyle default text color + regular weight (matching
other widget labels). It does NOT use the green accent (#34C759) — that
token is reserved exclusively for laser ``\u25cf ON`` status, the
one-laser-energized invariant's visual corollary.

The widget stores NO per-channel levels state. The shell slot connected
to ``idClicked`` reads ``reconstructed_frames[wavelength]`` and resets
the LevelsBar to the displayed frame's min/max on switch (avoids the
RGB-overlay levels-bar conflict).
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QToolButton,
    QWidget,
)

from lightsheet.gui.styles import spacing as _s


class ChannelRadio(QWidget):
    """L1/L2 channel display selector (two checkable QToolButtons in an
    exclusive QButtonGroup)."""

    # Re-emitted from the underlying QButtonGroup.idClicked so the shell
    # can connect to ``channel_radio.idClicked`` without reaching into the
    # internal group. The int payload is the channel index (0 = L1, 1 = L2).
    idClicked = Signal(int)

    def __init__(
        self,
        parent: QWidget | None = None,
        wl1: int | None = None,
        wl2: int | None = None,
    ) -> None:
        super().__init__(parent)
        # Compact horizontal pair: sm (8px) gap between the two buttons,
        # no outer margins (the widget sits inside the existing
        # ImageView-area container layout).
        layout = QHBoxLayout(self)
        layout.setContentsMargins(_s.ZERO, _s.ZERO, _s.ZERO, _s.ZERO)
        layout.setSpacing(_s.SM)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        self._btn1 = QToolButton(self)
        self._btn1.setCheckable(True)
        self._btn2 = QToolButton(self)
        self._btn2.setCheckable(True)
        # Channel indices as QButtonGroup ids (0 = L1, 1 = L2).
        self._group.addButton(self._btn1, 0)
        self._group.addButton(self._btn2, 1)

        layout.addWidget(self._btn1)
        layout.addWidget(self._btn2)

        # Re-emit the group's idClicked so the shell connects to a
        # single, stable signal on the widget itself.
        self._group.idClicked.connect(self.idClicked)

        self.set_wavelengths(wl1, wl2)

        # L1 (channel index 0) is the default selection — keeps the
        # display consistent with what is actually being acquired in
        # continuous modes (the first-checked laser is energized for the
        # session) and with the first half of the per-plane sequential
        # cycle in stack/single.
        self._btn1.setChecked(True)

        # Hidden by default; shown only when both auto-laser checkboxes
        # are checked (single-channel back-compat).
        self.hide()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def set_wavelengths(self, wl1: int | None, wl2: int | None) -> None:
        """Update the button labels from the live laser wavelengths.

        Falls back to ``L1`` / ``L2`` (index only) when a wavelength is
        unavailable (e.g. a mock without a configured wavelength)."""
        self._btn1.setText(f"L1 {wl1}" if wl1 is not None else "L1")
        self._btn2.setText(f"L2 {wl2}" if wl2 is not None else "L2")

    def show_for_multi_channel(self) -> None:
        """Show the radio group — both auto-laser checkboxes are checked,
        so the operator can switch between the two channel displays."""
        self.show()

    def hide_for_single_channel(self) -> None:
        """Hide the radio group — single-channel mode (zero or one
        auto-laser checked). Hiding (not disabling) keeps the ImageView
        area visually identical to today's single-channel experience."""
        self.hide()

    def button_text(self, idx: int) -> str:
        """Return the label text of the button at channel index ``idx``."""
        return self._group.button(idx).text()

    def is_checked(self, idx: int) -> bool:
        """Return True if the button at channel index ``idx`` is checked."""
        btn = self._group.button(idx)
        return bool(btn is not None and btn.isChecked())

    def click_button(self, idx: int) -> None:
        """Programmatically click the button at channel index ``idx``.

        Emits ``idClicked(idx)`` through the underlying group (the
        exclusive group unchecks the other button). Used by tests; the
        operator triggers the same path by clicking the on-screen button."""
        btn = self._group.button(idx)
        if btn is not None:
            btn.click()
