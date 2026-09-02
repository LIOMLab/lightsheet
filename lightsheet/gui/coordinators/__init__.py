"""Coordinator package barrel.

Re-exports the public surface of the save/reconstruction collaborators
and the new dock presentation controllers.
External call sites use ``from lightsheet.gui.coordinators.frame_saver_controller``
directly; the barrel is available for package-level imports.
"""

from lightsheet.gui.coordinators.adaptive_dock_controller import (
    AdaptiveDockController,
)
from lightsheet.gui.coordinators.dock_utils import (
    FloatingOnlyDock,
    build_no_dbl_click_title_bar,
)
from lightsheet.gui.coordinators.focus_dock_controller import (
    FocusDockController,
)
from lightsheet.gui.coordinators.frame_saver_controller import (
    FrameSaver,
    FrameSaverController,
    FrameSaverWorker,
    FrameViewer,
    ZarrSaver,
)
from lightsheet.gui.coordinators.reconstruction import (
    _position_to_float,
    crop_buffer,
    reconstruct_frame,
    reconstruct_frame_linear_blend,
)

__all__ = [
    "AdaptiveDockController",
    "FloatingOnlyDock",
    "FocusDockController",
    "FrameSaver",
    "FrameSaverController",
    "FrameSaverWorker",
    "FrameViewer",
    "ZarrSaver",
    "_position_to_float",
    "build_no_dbl_click_title_bar",
    "crop_buffer",
    "reconstruct_frame",
    "reconstruct_frame_linear_blend",
]
