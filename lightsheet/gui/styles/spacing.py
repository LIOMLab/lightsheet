"""Spacing tokens for the lightsheet GUI (px).

A shared 4 px base grid so hand-written widgets and re-exported forms
stay on a consistent rhythm.  Generated `.ui` files should use the
numeric values here; Python modules can import them directly.
"""

from __future__ import annotations

ZERO = 0  # explicit zero padding / margins
XS = 4    # tight, e.g. title-bar button padding
SM = 8    # standard widget/element spacing
MD = 12   # between form rows
LG = 16   # panel padding
XL = 24   # toolbar/section spacing
XXL = 32  # large gaps
RAIL = 48 # rail icon/button floor
