"""Typography style tokens for the lightsheet GUI.

Reusable CSS fragments for font weight/size so the codebase has one
source of truth for common text styles. The role sizes follow the UI
design contract: Body 13 px /400, Label 14 px /400, Heading 18 px /700,
Display 24 px /700.
"""

from __future__ import annotations

from PySide6.QtGui import QFont

from lightsheet.gui.styles import spacing as _s

BOLD = "font-weight: bold;"
BODY = "font-size: 13px; font-weight: 400;"
LABEL = "font-size: 14px; font-weight: 400;"
HEADING = "font-size: 18px; font-weight: bold;"
DISPLAY = "font-size: 24px; font-weight: bold;"
POWER = "font-weight: 600; font-size: 18px;"
PLACEHOLDER = f"font-size: {_s.LG}px;"

BODY_PX = 13
LABEL_PX = 14


def body_font(*, italic: bool = False) -> QFont:
    """QFont for the Body role (13 px /400).

    ``italic`` is used to mark resume rows in the acquisition queue so the
    italic treatment stays traceable to this module instead of ad-hoc
    ``QFont().setItalic(True)`` call sites.
    """
    font = QFont()
    font.setPixelSize(BODY_PX)
    font.setItalic(italic)
    return font


def label_font() -> QFont:
    """QFont for the Label role (14 px /400) — state chips, status text."""
    font = QFont()
    font.setPixelSize(LABEL_PX)
    return font
