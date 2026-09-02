"""Color-blind-safe status symbols for the lightsheet GUI.

A single source of truth for glyphs that encode state independently of
color.  Both the runtime Python code and the Qt Designer ``.ui`` default
text should use the same symbols so generated forms and live updates stay
in sync.
"""

from __future__ import annotations

# Laser status bullets: filled ON, hollow OFF, warning triangle FAULT.
LASER_ON = "\u25cf"      # ●
LASER_OFF = "\u25cb"     # ○
LASER_FAULT = "\u26a0"   # ⚠

# E-stop status bullets: heavy actuated, filled armed, hollow disarmed.
ESTOP_ACTUATED = "\u2b24"  # ⬤
ESTOP_ARMED = "\u25cf"     # ●
ESTOP_DISARMED = "\u25cb"  # ○
