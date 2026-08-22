"""HAL subpackage re-export shim (D-02).

This is the deliberate exception to the repo's no-barrel-files rule
(AGENTS.md §12): the ``lightsheet/hal/`` subpackage move (D-01) would
otherwise force every import site from ``from lightsheet.camera import Camera``
to a deeper ``from lightsheet.hal.real.camera import Camera`` path. The shim
absorbs that churn in one place so downstream code and tests import from the
``lightsheet.hal`` namespace:

    from lightsheet.hal import Camera, MockCamera, ICamera, ICameraCore

Wave 1 (this plan) re-exports only the Camera family. Wave 2 expands the
shim to cover the remaining 5 device families (SigGen, Motors, Lasers, ETLs,
IBeam) as they are moved into ``hal/real/`` and their mocks are written.

Explicit ``__all__`` avoids leaking private symbols from ``interfaces.py``
and the ``real/`` / ``mocks/`` subpackages.
"""

from lightsheet.hal.interfaces import ICamera, ICameraCore
from lightsheet.hal.mocks.mock_camera import MockCamera
from lightsheet.hal.real.camera import Camera

__all__ = [
    "Camera",
    "ICamera",
    "ICameraCore",
    "MockCamera",
]
