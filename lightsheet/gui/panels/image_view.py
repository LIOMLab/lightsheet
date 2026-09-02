"""Native Qt6 image-display widget for uint16 grayscale numpy arrays.

A minimal ``QGraphicsView``-based grayscale image viewer. The app only
ever calls ``setImage(frame, autoRange=False, autoLevels=False,
autoHistogramRange=False)`` — no histogram, LUT, ROI, or auto-range is
used — so a ~100-line native widget is sufficient. This removes a
moving-target plotting dependency from the PySide6/Qt6 combo matrix and
eliminates the ViewBox C++ destructor segfault that dependency caused
during garbage collection at process exit.

The fixed 0-20000 levels window replaces the historical
seed-one-pixel-to-2000 trick that worked around an auto-detected
histogram range: the seed pixel is still set by callers
(``frame_saver_controller.py``), but the levels window is now explicit
in the widget, not implicit in an external library's auto-detection.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter, QPixmap, QResizeEvent, QWheelEvent
from PySide6.QtWidgets import (
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QLabel,
    QWidget,
)

from lightsheet.gui.styles import colors as _c
from lightsheet.gui.styles import spacing as _s


class _KeepLastTint:
    pass


_KEEP_TINT = _KeepLastTint()


class ImageView(QGraphicsView):
    """Native Qt6 grayscale image display widget for uint16 numpy arrays.

    Displays uint16 numpy arrays as grayscale images with a fixed
    levels window (0-20000). No histogram, LUT, ROI, or auto-range —
    only ``setImage`` is used.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._pixmap_item: QGraphicsPixmapItem | None = None
        # Display levels window (the WINDOW set from the LevelsBar). The
        # ImageView clamps the frame to this window for display. Saved
        # frames are the raw uint16 — the clamp is display-only.
        self._levels_min = 0
        self._levels_max = 20000
        # Colormap scaling range (the RANGE set from the LevelsBar). The
        # grayscale ramp spans this range; the window clamps within it.
        # Defaults to the uint16 range so the widget is sane before the
        # first set_colormap_range call.
        self._colormap_min = 0
        self._colormap_max = 65535
        # QGraphicsView adds a default 4px margin that can cause blank
        # rendering in tight layouts; the SC2 exit criterion requires
        # this padding fix.
        self.setStyleSheet(
            f"QGraphicsView {{ padding: {_s.ZERO}px; border: none; }}"
        )
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
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

        # Placeholder overlay shown before the first real frame. It is a
        # child QLabel so it paints on top of the QGraphicsView without
        # needing scene coordinates, and it is hidden once setImage runs.
        self._placeholder = QLabel(self)
        self._placeholder.setWordWrap(True)
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setText(
            "No image — start Preview, Live, or Single mode to acquire."
        )
        self._placeholder.setStyleSheet(
            f"color: {_c.MUTED_TEXT}; background: transparent; "
            f"font-size: {_s.LG}px; padding: {_s.LG}px;"
        )
        self._placeholder.setGeometry(self.rect())

        # The most recent frame (raw uint16), kept so set_levels can
        # re-render with a new display window without the caller having
        # to re-supply the frame. The clamp is applied to a COPY for
        # display — this attribute holds the raw frame.
        self._last_frame: np.ndarray | None = None
        # The most recent tint (6-char hex, no "#") applied by setImage,
        # kept so set_levels / set_colormap_range can re-render WITH the
        # tint and the operator does not lose the L1/L2 color cue after
        # dragging the levels window. None means grayscale (single-channel
        # back-compat — set_levels re-renders Format_Grayscale8).
        self._last_tint: str | None = None
        # The source QImage built by the most recent setImage (before the
        # QPixmap.fromImage round-trip, which converts to the
        # screen-backed 32-bit format). Exposed so tests can assert the
        # format we actually built (Format_RGB888 vs Format_Grayscale8)
        # without the pixmap conversion masking it.
        self._src_qimage: QImage | None = None
        # Left-click drag pans the image (hand-drag). This is essential
        # for the operator to navigate a zoomed-in frame.
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        # Track whether the operator has zoomed/panned away from the
        # fit-to-view default. Once they have, resizeEvent must NOT
        # reset the view (fitInView) — it would discard their zoom/pan.
        self._user_transformed = False

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
            self.setImage(self._last_frame, tint=self._last_tint)

    def set_colormap_range(self, range_min: int, range_max: int) -> None:
        """Set the colormap scaling range (the LevelsBar RANGE set).

        The grayscale ramp spans ``[range_min, range_max]``; the display
        window (``set_levels``) clamps within it. Dragging the RANGE
        handles inward clamps the levels window into the new range, which
        is the visible effect on the display (a window handle outside the
        new range is pulled back inside). Display-only — saved frames are
        the raw uint16. Re-renders the current frame so the operator sees
        the new scaling immediately.
        """
        self._colormap_min = int(range_min)
        self._colormap_max = int(range_max)
        # Clamp the levels window into the new range so the RANGE handles
        # have a visible effect: a window setpoint outside the new range
        # is pulled back inside, narrowing the display window and changing
        # the contrast.
        new_levels_min = max(
            self._colormap_min, min(self._levels_min, self._colormap_max)
        )
        new_levels_max = max(
            self._colormap_min, min(self._levels_max, self._colormap_max)
        )
        if (new_levels_min, new_levels_max) != (self._levels_min, self._levels_max):
            self._levels_min = new_levels_min
            self._levels_max = new_levels_max
        if self._last_frame is not None:
            self.setImage(self._last_frame, tint=self._last_tint)

    def resizeEvent(self, event: QResizeEvent) -> None:
        """Re-fit the image to the viewport on resize — but ONLY if the
        operator has not zoomed/panned. Once they have, their transform
        is preserved across resizes (fitInView would discard it)."""
        super().resizeEvent(event)
        self._placeholder.setGeometry(self.rect())
        if self._pixmap_item is not None and not self._user_transformed:
            self.fitInView(
                self._pixmap_item, Qt.AspectRatioMode.KeepAspectRatio
            )

    def wheelEvent(self, event: QWheelEvent) -> None:
        """Zoom the view with the mouse wheel, centered on the cursor.

        The base QGraphicsView.wheelEvent scrolls the scene, which with
        scrollbars off drifts the image vertically. Instead, use the
        wheel to zoom in/out around the cursor position — the standard
        image-viewer pattern. Once the operator zooms, mark the view as
        user-transformed so resizeEvent no longer auto-fits (which would
        discard the zoom).
        """
        if self._pixmap_item is None:
            event.accept()
            return
        zoom_factor = 1.15
        if event.angleDelta().y() < 0:
            zoom_factor = 1.0 / zoom_factor
        # Zoom around the cursor position so the point under the mouse
        # stays fixed (the standard image-viewer feel).
        cursor_scene = self.mapToScene(event.position().toPoint())
        self.scale(zoom_factor, zoom_factor)
        # Adjust the view center so the cursor scene point stays put.
        delta = cursor_scene - self.mapToScene(event.position().toPoint())
        self.translate(delta.x(), delta.y())
        self._user_transformed = True
        event.accept()

    def setImage(
        self,
        frame: np.ndarray,
        autoRange: bool = False,
        autoLevels: bool = False,
        autoHistogramRange: bool = False,
        tint: str | None | _KeepLastTint = _KEEP_TINT,
    ) -> None:
        """Display a uint16 numpy array as a grayscale image, optionally
        tinted with a per-channel color.

        The ``auto*`` kwargs are accepted for call-signature
        compatibility with the historical call sites in
        ``frame_saver_controller.py`` but are ignored — this widget has
        no auto-range, auto-levels, or histogram. The frame must be a
        C-contiguous (row-major) uint16 array in ``(H, W)`` order.

        The frame is clamped to the display levels window
        ``[levels_min, levels_max]`` (the LevelsBar WINDOW set) and scaled
        to uint8 ``[0, 255]`` against that same window. Values outside the
        window saturate (below -> black, above -> white). The colormap
        range (RANGE set) frames the data range and constrains the window;
        dragging the RANGE handles inward clamps the window into the new
        range, which is the visible effect on the display.

        ``tint`` is an optional 6-char hex color string (no ``#`` prefix,
        e.g. ``"00FF00"`` for the 555 nm channel), or ``None`` for
        grayscale, or omitted to keep the last tint. When provided, the
        scaled grayscale is modulated per-channel
        (``channel_c = (frame_scaled * color_c) // 255``) and the QImage
        is built as ``Format_RGB888`` so the operator can visually
        distinguish L1 from L2 in demo mode where the frames are
        otherwise identical. When ``tint`` is ``None``, the existing
        ``Format_Grayscale8`` path runs unchanged (single-channel
        back-compat — byte-identical display). The tint is stored on
        ``self._last_tint`` so ``set_levels`` / ``set_colormap_range``
        re-render WITH the tint (the channel color cue survives level
        adjustments) and new frames inherit the current channel color.
        """
        if isinstance(tint, _KeepLastTint):
            tint = self._last_tint

        # Scale uint16 [levels_min, levels_max] to uint8 [0, 255].
        # np.clip + linear scaling; values outside the window saturate.
        # The raw frame is retained for set_levels re-render and for the
        # save path (which receives the unclamped frame separately).
        self._placeholder.hide()
        self._last_frame = frame
        self._last_tint = tint
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
        # When a tint is provided, the grayscale is modulated per-channel
        # (channel_c = (frame_scaled * color_c) // 255) and the QImage is
        # built as Format_RGB888 so the operator can visually distinguish
        # L1 from L2 in demo mode where the frames are otherwise
        # identical. The interleaved RGB buffer is (H, W, 3) uint8.
        #
        # The bytes buffer MUST stay alive until QPixmap.fromImage
        # completes the copy — QImage does not copy the data, it just
        # wraps the pointer. Binding tobytes() to an instance attribute
        # keeps the buffer alive across the fromImage call and until the
        # next setImage replaces it.
        height, width = frame_scaled.shape
        if tint is not None:
            r = int(tint[0:2], 16)
            g = int(tint[2:4], 16)
            b = int(tint[4:6], 16)
            # Modulate per-channel in uint16 to avoid uint8 overflow
            # (frame_scaled * 255 overflows uint8 before the // 255).
            scaled = frame_scaled.astype(np.uint16)
            rgb = np.empty((height, width, 3), dtype=np.uint8)
            rgb[:, :, 0] = (scaled * r) // 255
            rgb[:, :, 1] = (scaled * g) // 255
            rgb[:, :, 2] = (scaled * b) // 255
            bytes_per_line = width * 3
            self._image_buffer = rgb.tobytes()
            qimage = QImage(
                self._image_buffer,
                width,
                height,
                bytes_per_line,
                QImage.Format.Format_RGB888,
            )
        else:
            bytes_per_line = width
            self._image_buffer = frame_scaled.tobytes()
            qimage = QImage(
                self._image_buffer,
                width,
                height,
                bytes_per_line,
                QImage.Format.Format_Grayscale8,
            )
        self._src_qimage = qimage

        # Convert to QPixmap and place on the scene. First call adds the
        # pixmap item and sets the scene rect; subsequent calls update
        # the existing item's pixmap in place (no scene rect change —
        # the frame size is constant per session).
        pixmap = QPixmap.fromImage(qimage)
        if self._pixmap_item is None:
            self._pixmap_item = self._scene.addPixmap(pixmap)
            # A large symmetric scene rect so the operator can pan the
            # image freely beyond every panel edge (the viewport can
            # scroll anywhere within the scene rect). Without this the
            # scene rect starts at (0,0) and the top edge is pinned.
            pad = 8 * max(width, height)
            self._scene.setSceneRect(-pad, -pad, width + 2 * pad, height + 2 * pad)
        else:
            self._pixmap_item.setPixmap(pixmap)
        # Only auto-fit on the first frame. Once the operator has zoomed
        # or panned (_user_transformed), preserve their transform across
        # contrast changes (set_levels / set_colormap_range re-call
        # setImage) and across new frames — fitInView would discard
        # their zoom/pan.
        if not self._user_transformed:
            self.fitInView(self._pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)
