"""Frame viewer — queues and displays reconstructed frames in the UI."""

from __future__ import annotations

import contextlib
import logging
import queue
from typing import TYPE_CHECKING

import numpy as np
from PySide6.QtCore import QObject

if TYPE_CHECKING:
    from lightsheet.gui.shell.controller import Controller_MainWindow

logger = logging.getLogger(__name__)


class FrameViewer(QObject):
    """Class for queueing and displaying images"""

    def __init__(self, parent: Controller_MainWindow, rows: int, columns: int) -> None:
        QObject.__init__(self, parent)
        self.parent = parent  # ty: ignore[invalid-assignment]
        self.queue = queue.Queue(3)

        # Default frame size is 2000x2000 if no valid size provided
        if rows is not None:
            self.rows = int(rows)
        else:
            self.rows = 2000
        if columns is not None:
            self.columns = int(columns)
        else:
            self.columns = 2000

        # Empty frame
        frame_init = np.zeros((self.rows, self.columns), dtype=np.uint16)
        # Set one pixel to trick histogram initial range (0-20000)
        frame_init[0, 0] = 20000
        # Transpose since setImage is column-major
        frame_init = np.transpose(frame_init)
        # Set initial view
        self.parent.ui.imageView.setImage(frame_init)
        # Live min/max readout (actual pixel range, not the display window).
        # Guarded so a minimal shell standin without the helper does not
        # break FrameViewer construction.
        _readout = getattr(self.parent, "_update_levels_readout", None)
        if _readout is not None:
            _readout(frame_init)

    def enqueue_frame(self, frame: np.ndarray) -> None:
        with contextlib.suppress(queue.Full):
            self.queue.put(frame, block=False)

    def updateUi_refresh_view(self) -> None:
        try:
            frame = self.queue.get(block=False)
        except queue.Empty:
            pass
        else:
            # setImage is column-major
            frame = np.transpose(frame)
            self.parent.ui.imageView.setImage(  # ty: ignore[unresolved-attribute]
                frame, autoRange=False, autoLevels=False, autoHistogramRange=False
            )
            # Live min/max readout (actual pixel range, not the display window).
            _readout = getattr(self.parent, "_update_levels_readout", None)
            if _readout is not None:
                _readout(frame)