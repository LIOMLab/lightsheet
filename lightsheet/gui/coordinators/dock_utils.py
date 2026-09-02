"""Shared presentation primitives for floating-only trajectory docks.

The trajectory docks are intentionally standalone floating windows — they
never re-dock into the main QMainWindow. The custom title bar swallows
double-clicks so the operator cannot accidentally un-float the dock.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QSize
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStyle,
)

from lightsheet.gui.styles import colors as _c

logger = logging.getLogger(__name__)


class FloatingOnlyDock(QDockWidget):
    """QDockWidget that is always floating.

    setFloating() is a no-op so double-clicking the title bar (which Qt
    wires to setFloating(False)) cannot un-float or re-dock the window.
    isFloating() always reports True. The one-time base-class
    ``QDockWidget.setFloating(dock, True)`` is used at creation to open the
    window as a standalone floater.
    """

    def setFloating(self, _floating: bool) -> None:
        """Ignore all setFloating calls — the dock stays floating."""

    def isFloating(self) -> bool:
        return True


class _NoDblClickTitleBar(QFrame):
    """Title bar frame whose mouseDoubleClickEvent is a no-op."""

    def mouseDoubleClickEvent(self, _ev: object) -> None:
        return  # swallow — no re-dock on double-click


def build_no_dbl_click_title_bar(
    title: str,
    close_tooltip: str,
    dock: QDockWidget,
) -> QFrame:
    """Build a custom title bar with a title label and close button.

    The frame swallows double-clicks so the native title-bar handler never
    fires. The close button calls ``dock.close()``.
    """
    title_bar = _NoDblClickTitleBar(dock)
    title_bar.setFrameShape(QFrame.Shape.NoFrame)
    title_bar.setObjectName(f"{dock.objectName()}TitleBar")
    tb_layout = QHBoxLayout(title_bar)
    tb_layout.setContentsMargins(8, 4, 8, 4)
    tb_layout.setSpacing(4)
    title_label = QLabel(title, title_bar)
    tb_layout.addWidget(title_label)
    tb_layout.addStretch(1)
    close_btn = QPushButton("\u00d7", title_bar)
    close_btn.setFixedSize(20, 20)
    close_btn.setFlat(True)
    close_btn.setIcon(QApplication.style().standardIcon(QStyle.SP_DialogCloseButton))
    close_btn.setIconSize(QSize(16, 16))
    close_btn.setAccessibleName("Close")
    close_btn.setToolTip(close_tooltip)
    close_btn.setStyleSheet(
        f"QPushButton {{ border: none; color: {_c.BREEZE_FG}; }}"
        f"QPushButton:hover {{ background: {_c.HOVER}; }}"
        f"QPushButton:pressed {{ background: {_c.PRESSED}; }}"
    )
    close_btn.clicked.connect(dock.close)
    tb_layout.addWidget(close_btn)
    return title_bar
