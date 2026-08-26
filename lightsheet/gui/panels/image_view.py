"""Native Qt6 image-display widget for uint16 grayscale numpy arrays.

A minimal ``QGraphicsView``-based grayscale image viewer. The app only
ever calls ``setImage(frame, autoRange=False, autoLevels=False,
autoHistogramRange=False)`` — no histogram, LUT, ROI, or auto-range is
used — so a ~100-line native widget is sufficient. This removes a
moving-target plotting dependency from the PySide6/Qt6 combo matrix and
eliminates the ViewBox C++ destructor segfault that dependency caused
during garbage collection at process exit.

The fixed 0-2000 levels window replaces the historical
seed-one-pixel-to-2000 trick that worked around an auto-detected
histogram range: the seed pixel is still set by callers
(``frame_saver_controller.py``), but the levels window is now explicit
in the widget, not implicit in an external library's auto-detection.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
)


class ImageView(QGraphicsView):
    """Native Qt6 grayscale image display widget for uint16 numpy arrays.

    Displays uint16 numpy arrays as grayscale images with a fixed
    levels window (0-2000). No histogram, LUT, ROI, or auto-range —
    only ``setImage`` is used.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._pixmap_item: QGraphicsPixmapItem | None = None
        # Fixed levels window: 0-2000. The seed-one-pixel-to-2000 trick
        # the historical callers used to fix an auto-detected histogram
        # range is now redundant — the window is explicit here.
        self._levels_min = 0
        self._levels_max = 2000
        # QGraphicsView adds a default 4px margin that can cause blank
        # rendering in tight layouts; the SC2 exit criterion requires
        # this padding fix.
        self.setStyleSheet("QGraphicsView { padding: 0px; }")
        # No antialiasing — pixel-accurate display of grayscale frames.
        # QPainter.RenderHint(0) is the "no hints" value (Antialiasing
        # and friends all default to off, but set it explicitly so the
        # widget's render state is deterministic).
        self.setRenderHints(QPainter.RenderHint(0))
        # Scrollbar policy AlwaysOff on both axes: prevents the
        # resize→fitInView→scrollbar-show/hide→resize recursion pitfall.
        # With scrollbars always off the viewport size only changes on
        # real resizes, so fitInView in resizeEvent is non-reentrant.
        self.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        # Non-empty sceneRect at construction so fitInView has geometry
        # before the first frame (otherwise the view shows a tiny black
        # square until setImage populates the scene). 320x240 matches
        # the pane floor.
        self._scene.setSceneRect(0, 0, 320, 240)
        # The most recent frame (raw uint16), kept so set_levels can
        # re-render with a new display window without the caller having
        # to re-supply the frame. The clamp is applied to a COPY for
        # display — this attribute holds the raw frame.
        self._last_frame: np.ndarray | None = None

    def set_levels(self, levels_min: int, levels_max: int) -> None:
        """Update the display levels window and re-render the current
        frame (if any) clamped to the new window.

        The clamp is on the DISPLAY buffer only — the raw frame stored
        for save paths is never clamped. Callers (the LevelsBar drag
        slot) invoke this on a handle drag.
        """
        self._levels_min = int(levels_min)
        self._levels_max = int(levels_max)
        if self._last_frame is not None:
            self.setImage(self._last_frame)

    def resizeEvent(self, event) -> None:
        """Re-call fitInView on every resize so the pixmap fills the
        viewport (KeepAspectRatio). With scrollbar policy AlwaysOff the
        viewport size only changes on real resizes, so this is
        non-reentrant — no re-entrancy guard needed."""
        super().resizeEvent(event)
        if self._pixmap_item is not None:
            self.fitInView(
                self._pixmap_item, Qt.AspectRatioMode.KeepAspectRatio
            )

    def setImage(
        self,
        frame: np.ndarray,
        autoRange: bool = False,
        autoLevels: bool = False,
        autoHistogramRange: bool = False,
    ) -> None:
        """Display a uint16 numpy array as a grayscale image.

        The ``auto*`` kwargs are accepted for call-signature
        compatibility with the historical call sites in
        ``frame_saver_controller.py`` but are ignored — this widget has
        no auto-range, auto-levels, or histogram. The frame is expected
        to be already-transposed (column-major) by the caller.

        The frame is clamped to the fixed levels window [0, 2000] and
        scaled to uint8 [0, 255] for display. Values above 2000 clamp to
        255; values below 0 clamp to 0.
        """
        # Fixed levels window: scale uint16 [0, 2000] to uint8 [0, 255].
        # np.clip + linear scaling; values outside the window saturate.
        # The raw frame is retained for set_levels re-render and for the
        # save path (which receives the unclamped frame separately).
        self._last_frame = frame
        frame_clamped = np.clip(frame, self._levels_min, self._levels_max)
        # Guard against a degenerate levels window where both LevelsBar
        # handles coincide (levels_max == levels_min). The LevelsBar
        # setters permit equality, so this state is reachable by normal
        # handle dragging; without the guard the division yields nan/inf
        # and the uint8 cast produces garbage. Fall back to a binary
        # threshold at levels_min so the display stays sane (pixels above
        # the threshold render white, at-or-below render black).
        span = self._levels_max - self._levels_min
        if span <= 0:
            frame_scaled = (frame > self._levels_min).astype(np.uint8) * 255
        else:
            frame_scaled = (
                (frame_clamped - self._levels_min) / span * 255
            ).astype(np.uint8)

        # Build a QImage over the uint8 buffer. Format_Grayscale8 is
        # cross-platform safe (QPixmap is typically backed by 32-bit
        # ARGB on screen, so 16-bit grayscale would not survive the
        # QPixmap round-trip reliably). The SC2 smoke test asserts
        # non-zero pixel data, not 16-bit fidelity.
        #
        # The bytes buffer MUST stay alive until QPixmap.fromImage
        # completes the copy — QImage does not copy the data, it just
        # wraps the pointer. Binding tobytes() to an instance attribute
        # keeps the buffer alive across the fromImage call and until the
        # next setImage replaces it.
        height, width = frame_scaled.shape
        bytes_per_line = width
        self._image_buffer = frame_scaled.tobytes()
        qimage = QImage(
            self._image_buffer,
            width,
            height,
            bytes_per_line,
            QImage.Format.Format_Grayscale8,
        )

        # Convert to QPixmap and place on the scene. First call adds the
        # pixmap item and sets the scene rect; subsequent calls update
        # the existing item's pixmap in place (no scene rect change —
        # the frame size is constant per session).
        pixmap = QPixmap.fromImage(qimage)
        if self._pixmap_item is None:
            self._pixmap_item = self._scene.addPixmap(pixmap)
            self._scene.setSceneRect(0, 0, width, height)
        else:
            self._pixmap_item.setPixmap(pixmap)
        self.fitInView(self._pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)
