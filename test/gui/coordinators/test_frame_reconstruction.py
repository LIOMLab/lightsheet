"""Frame reconstruction pure-numpy behavior tests.

``crop_buffer`` / ``reconstruct_frame`` / ``reconstruct_frame_linear_blend``
are pure-numpy image-reconstruction functions moved out of the
``Controller_MainWindow`` god object into ``FrameSaverController``. They
take a 3D buffer ``(tile_count, ysize, xsize)`` and return a cropped
buffer or a reconstructed 2D frame. They read NO shell/HAL/Qt state —
only ``buffer.shape`` — so they are exercised here with direct
input-array -> output-array assertions (the AGENTS.md §5 pure-logic
pattern), not via the golden-master characterization net.

The tests construct a real ``FrameSaverController`` (the methods are
instance methods on it) with a QObject shell stand-in and a demo
``DeviceBundle``, mirroring the ``_ShellStandin`` pattern in
``test_frame_saver_controller.py``.
"""

from __future__ import annotations

from unittest.mock import Mock

import numpy as np
import pytest
from PySide6.QtCore import QObject

pytest.importorskip("PySide6")  # FrameSaverController wraps QObjects

from lightsheet.gui.coordinators.frame_saver_controller import FrameSaverController
from lightsheet.hal import (
    DeviceBundle,
)


class _ShellStandin(QObject):
    """Minimal QObject shell stand-in.

    ``FrameSaverController.__init__`` parents ``FrameSaver`` /
    ``FrameViewer`` to the shell (so it must be a QObject) and reads
    ``shell.save_format``. The reconstruction methods under test do not
    read any shell attribute, but the controller is still constructed
    normally to exercise the real ownership path.
    """

    def __init__(self) -> None:
        super().__init__()
        self.message_printer_calls: list[str] = []
        self.sig_message = Mock()
        self.ui = Mock()
        self.save_format = "hdf5"

    def updateUi_message_printer(self, message: str) -> None:
        self.message_printer_calls.append(message)


def _make_bundle() -> DeviceBundle:
    from test.helpers.factories import make_bundle

    return make_bundle()


def _make_fs() -> FrameSaverController:
    return FrameSaverController(_make_bundle(), _ShellStandin())  # ty: ignore[invalid-argument-type]


# -- crop_buffer -----------------------------------------------------------


def test_crop_buffer_single_tile_returns_buffer_unchanged() -> None:
    """With a single tile (tile_count == 1) crop_buffer returns the
    buffer verbatim — no overlap cropping is applied."""
    fs = _make_fs()
    buffer = np.arange(1 * 4 * 5, dtype=np.uint16).reshape(1, 4, 5)
    out = fs.crop_buffer(buffer)
    np.testing.assert_array_equal(out, buffer)


def test_crop_buffer_multi_tile_shape_reflects_20pct_overlap() -> None:
    """With tile_count > 1, crop_buffer returns a buffer whose last
    dimension is tile_width + 2 * (0.2 * tile_width) per tile.

    For xsize=300, tile_count=3: tile_width=100, overlap=20, so each
    cropped tile has width 100 + 40 = 140. Output shape is
    (3, ysize, 140).
    """
    fs = _make_fs()
    ysize = 4
    xsize = 300
    tile_count = 3
    buffer = np.zeros((tile_count, ysize, xsize), dtype=np.uint16)
    out = fs.crop_buffer(buffer)
    assert out.shape == (tile_count, ysize, 140), (
        f"crop_buffer multi-tile shape {out.shape} != expected "
        f"(3, {ysize}, 140) (tile_width=100 + 2*overlap=20)"
    )
    assert out.dtype == np.uint16


# -- reconstruct_frame -----------------------------------------------------


def test_reconstruct_frame_single_tile_returns_first_plane() -> None:
    """With tile_count == 1, reconstruct_frame returns buffer[0, :, :]
    (the single 2D plane)."""
    fs = _make_fs()
    plane = np.arange(4 * 5, dtype=np.uint16).reshape(4, 5)
    buffer = plane[np.newaxis, :, :]  # shape (1, 4, 5)
    out = fs.reconstruct_frame(buffer)
    assert out.shape == (4, 5)
    assert out.dtype == np.uint16
    np.testing.assert_array_equal(out, plane)


def test_reconstruct_frame_multi_tile_shape_and_dtype() -> None:
    """With tile_count > 1, reconstruct_frame returns a 2D frame of
    shape (ysize, xsize) by tiling non-overlapping tile_width slices."""
    fs = _make_fs()
    ysize = 4
    xsize = 300
    tile_count = 3
    buffer = np.zeros((tile_count, ysize, xsize), dtype=np.uint16)
    out = fs.reconstruct_frame(buffer)
    assert out.shape == (ysize, xsize), (
        f"reconstruct_frame shape {out.shape} != expected ({ysize}, {xsize})"
    )
    assert out.dtype == np.uint16


def test_reconstruct_frame_multi_tile_places_tile_slices_correctly() -> None:
    """reconstruct_frame with tile_count=3 places each tile's
    tile_width-wide slice at the correct column offset. Fill each tile
    with a distinct constant and confirm the reconstructed frame's
    column bands carry those constants."""
    fs = _make_fs()
    ysize = 2
    xsize = 30
    tile_count = 3
    tile_width = xsize // tile_count  # 10
    buffer = np.zeros((tile_count, ysize, xsize), dtype=np.uint16)
    for t in range(tile_count):
        buffer[t, :, :] = (t + 1) * 100  # tile 0 -> 100, tile 1 -> 200, ...
    out = fs.reconstruct_frame(buffer)
    # Each tile's slice is buffer[t, :, t*tile_width : (t+1)*tile_width]
    # which equals (t+1)*100 across that band.
    for t in range(tile_count):
        band = out[:, t * tile_width : (t + 1) * tile_width]
        assert np.all(band == (t + 1) * 100), (
            f"tile {t} band expected all {(t + 1) * 100}, "
            f"got min={band.min()} max={band.max()}"
        )


# -- reconstruct_frame_linear_blend ---------------------------------------


def test_reconstruct_frame_linear_blend_single_tile_returns_first_plane() -> None:
    """With tile_count == 1, linear-blend returns buffer[0, :, :]."""
    fs = _make_fs()
    plane = np.arange(4 * 5, dtype=np.uint16).reshape(4, 5)
    buffer = plane[np.newaxis, :, :]
    out = fs.reconstruct_frame_linear_blend(buffer)
    np.testing.assert_array_equal(out, plane)


def test_reconstruct_frame_linear_blend_overlap_is_weighted_combination() -> None:
    """In the overlap region between two adjacent tiles, the linear-blend
    output is a weighted combination of the two contributing planes.

    Setup: tile_count=2, xsize=20, tile_width=10, overlap=2. Fill tile 0
    with constant A=1000 and tile 1 with constant B=2000 across the
    overlap columns. The blend weight at overlap-column ``c`` (0-indexed
    within the 2*overlap-wide blend) is ``c * weight_step`` for the
    current tile and ``1 - c * weight_step`` for the previous tile,
    where ``weight_step = 1 / (2 * overlap) = 1/4``.

    The overlap region spans columns [tile_width - overlap, tile_width +
    overlap) = [8, 12) in the reconstructed frame (4 columns wide). At
    each such column the blended value is
    ``w * B + (1 - w) * A`` where w goes 0.0, 0.25, 0.5, 0.75.

    We assert the exact blended values at those four columns for row 0.
    """
    fs = _make_fs()
    ysize = 1
    xsize = 20
    tile_count = 2
    tile_width = xsize // tile_count  # 10
    overlap = int(tile_width * 0.2)  # 2
    A = 1000
    B = 2000
    buffer = np.zeros((tile_count, ysize, xsize), dtype=np.uint16)
    buffer[0, :, :] = A
    buffer[1, :, :] = B

    out = fs.reconstruct_frame_linear_blend(buffer)
    assert out.shape == (ysize, xsize), (
        f"linear-blend shape {out.shape} != expected ({ysize}, {xsize})"
    )

    weight_step = 1 / (2 * overlap)  # 0.25
    # The blend loop iterates `column in range(2 * overlap)` (4 iters),
    # frame_column = column + previous_last_center_column
    # where previous_last_center_column = frame*tile_width - overlap
    # for frame=1 -> 10 - 2 = 8. So frame_column = 8, 9, 10, 11.
    for c in range(2 * overlap):
        frame_column = c + (tile_width - overlap)
        w = c * weight_step  # weight on current tile (B)
        expected = w * B + (1 - w) * A
        actual = float(out[0, frame_column])
        assert abs(actual - expected) < 1.0, (
            f"overlap column {frame_column}: expected blended ~{expected} "
            f"(w={w}, A={A}, B={B}), got {actual}"
        )

    # Non-overlap bands: tile 0's left band [0, 8) is pure A, tile 1's
    # right band [12, 20) is pure B.
    assert np.all(out[0, 0 : tile_width - overlap] == A), (
        "tile 0 left non-overlap band must be pure A"
    )
    assert np.all(out[0, tile_width + overlap :] == B), (
        "tile 1 right non-overlap band must be pure B"
    )


# -- module split identity ---------------------------------------------------


def test_reconstruction_functions_and_frame_viewer_have_focused_modules() -> None:
    """After D-12.2.1, the pure-numpy reconstruction helpers and the
    FrameViewer QObject live in focused modules while legacy imports from
    ``frame_saver_controller`` remain object-identical."""
    from lightsheet.gui.coordinators.frame_saver_controller import FrameViewer as old_fv
    from lightsheet.gui.coordinators.frame_saver_controller import (
        _position_to_float as old_pos,
    )
    from lightsheet.gui.coordinators.frame_saver_controller import (
        crop_buffer as old_crop,
    )
    from lightsheet.gui.coordinators.frame_saver_controller import (
        reconstruct_frame as old_recon,
    )
    from lightsheet.gui.coordinators.frame_saver_controller import (
        reconstruct_frame_linear_blend as old_blend,
    )
    from lightsheet.gui.coordinators.frame_viewer import FrameViewer as new_fv
    from lightsheet.gui.coordinators.reconstruction import (
        _position_to_float as new_pos,
    )
    from lightsheet.gui.coordinators.reconstruction import (
        crop_buffer as new_crop,
    )
    from lightsheet.gui.coordinators.reconstruction import (
        reconstruct_frame as new_recon,
    )
    from lightsheet.gui.coordinators.reconstruction import (
        reconstruct_frame_linear_blend as new_blend,
    )

    assert new_fv is old_fv
    assert new_crop is old_crop
    assert new_recon is old_recon
    assert new_blend is old_blend
    assert new_pos is old_pos
    assert new_fv.__module__.endswith("frame_viewer")
    assert new_crop.__module__.endswith("reconstruction")
    assert new_pos.__module__.endswith("reconstruction")
