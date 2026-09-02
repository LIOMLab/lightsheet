"""Typography style tokens for the lightsheet GUI.

Reusable CSS fragments for font weight/size so the codebase has one
source of truth for common text styles.
"""

from __future__ import annotations

from lightsheet.gui.styles import spacing as _s

BOLD = "font-weight: bold;"
HEADING = "font-size: 18px; font-weight: bold;"
POWER = "font-weight: 600; font-size: 18px;"
PLACEHOLDER = f"font-size: {_s.LG}px;"
