"""Semantic color tokens for the lightsheet GUI.

All color constants used by GUI widgets live here so the codebase has a
single source of truth for status/safety, Breeze dark, and structural
grayscale palettes.  Hex values are intended for ``setStyleSheet`` calls;
``QColor`` instances are provided for paint/draw operations.
"""

from __future__ import annotations

from PySide6.QtGui import QColor

# ---------------------------------------------------------------------------
# iOS-style safety / status tokens
# ---------------------------------------------------------------------------
DANGER = "#FF3B30"       # E-stop actuated / fault / flagged queue row
SUCCESS = "#34C759"      # armed / laser ON
WARNING = "#FFC107"      # attention border / warning
DISABLED = "#8E8E93"     # off / disarmed / muted text
ON_DANGER = "#FFFFFF"    # text on top of a danger background

# ---------------------------------------------------------------------------
# Breeze dark theme tokens (plotting and dark surfaces)
# ---------------------------------------------------------------------------
BREEZE_BG = "#1d2023"        # plot / dark widget background
BREEZE_FG = "#eff0f1"        # primary foreground text / axes
BREEZE_ACCENT = "#3daee9"    # primary accent (camera, intensity curves)
BREEZE_MIDTONE = "#76797c"   # secondary curve / mid-tone grey
BREEZE_WARNING = "#99995C"   # warning markers (residual, re-acquire)
BREEZE_INFORMATION = "#E0A030"  # information / power L1
BREEZE_POWER2 = "#F0C060"    # power L2

# RGBA tuples for pyqtgraph mkBrush calls
BREEZE_ACCENT_RGBA = (61, 174, 233, 50)

# ---------------------------------------------------------------------------
# Structural grays
# ---------------------------------------------------------------------------
MUTED_TEXT = "#9e9e9e"    # empty-state copy
PANEL_BG = "#31363b"      # title-bar / panel background
PANEL_FG = "#eff0f1"      # on-dark text
HOVER = "#5a5a5a"         # button hover on dark surfaces
PRESSED = "#757575"       # button pressed on dark surfaces

# ---------------------------------------------------------------------------
# QColor paint tokens for draw operations
# ---------------------------------------------------------------------------
Q_FLAG_ERROR = QColor(255, 180, 180)
Q_FLAG_NORMAL = QColor(255, 255, 255)
Q_GRADIENT_START = QColor(0, 0, 0)
Q_GRADIENT_END = QColor(255, 255, 255)
Q_RANGE_BRUSH = QColor(80, 80, 80)
Q_RANGE_PEN = QColor(20, 20, 20)
Q_WINDOW_BRUSH = QColor(180, 180, 180)
Q_WINDOW_PEN = QColor(40, 40, 40)
Q_CENTER_BRUSH = QColor(120, 120, 120)
Q_CENTER_PEN = QColor(60, 60, 60)
