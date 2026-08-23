"""HAL subpackage re-export shim (D-02).

This is the deliberate exception to the repo's no-barrel-files rule
(AGENTS.md §12): the ``lightsheet/hal/`` subpackage move (D-01) would
otherwise force every import site from ``from lightsheet.camera import Camera``
to a deeper ``from lightsheet.hal.real.camera import Camera`` path. The shim
absorbs that churn in one place so downstream code and tests import from the
``lightsheet.hal`` namespace:

    from lightsheet.hal import Camera, MockCamera, ICamera, ICameraCore
    from lightsheet.hal import SigGen, MockSigGen, ISigGen, ISigGenCore
    from lightsheet.hal import Motors, MockMotors, IMotors, IMotorsCore, IMotor
    from lightsheet.hal import ETLs, MockETLs, IETLs, IETLsCore, IOptotune
    from lightsheet.hal import ILaser, DAQLaser, IBeamSmartLaser, MockLaser, IBeam

Wave 1 (Plan 01) re-exported only the Camera family. Wave 2 (Plan 02)
expanded the shim to cover SigGen, Motors, and ETLs. Wave 3 (Plan 03)
added Lasers and IBeam. Wave 5 (Plan 05) retired the legacy 2-channel
laser container and mock classes along with their ABCs — the unified
``ILaser`` family (``DAQLaser`` / ``IBeamSmartLaser`` / ``MockLaser``)
is now the sole laser architecture. ``IBeam`` remains importable as the
internal serial engine ``IBeamSmartLaser`` wraps.

Explicit ``__all__`` avoids leaking private symbols from ``interfaces.py``
and the ``real/`` / ``mocks/`` subpackages.
"""

from lightsheet.hal.bundle import DeviceBundle
from lightsheet.hal.interfaces import (
    ICamera,
    ICameraCore,
    IETLs,
    IETLsCore,
    ILaser,
    IMotor,
    IMotorCore,
    IMotors,
    IMotorsCore,
    IOptotune,
    ISigGen,
    ISigGenCore,
)
from lightsheet.hal.mocks.mock_camera import MockCamera
from lightsheet.hal.mocks.mock_etls import MockETLs
from lightsheet.hal.mocks.mock_laser import MockLaser
from lightsheet.hal.mocks.mock_motors import MockMotors
from lightsheet.hal.mocks.mock_siggen import MockSigGen
from lightsheet.hal.real.camera import Camera
from lightsheet.hal.real.daqlaser import DAQLaser
from lightsheet.hal.real.etls import ETLs
from lightsheet.hal.real.ibeam_smart import IBeam, IBeamSmartLaser
from lightsheet.hal.real.motors import Motors
from lightsheet.hal.real.siggen import SigGen

__all__ = [
    "Camera",
    "DAQLaser",
    "DeviceBundle",
    "ETLs",
    "IBeam",
    "IBeamSmartLaser",
    "ICamera",
    "ICameraCore",
    "IETLs",
    "IETLsCore",
    "ILaser",
    "IMotor",
    "IMotorCore",
    "IMotors",
    "IMotorsCore",
    "IOptotune",
    "ISigGen",
    "ISigGenCore",
    "MockCamera",
    "MockETLs",
    "MockLaser",
    "MockMotors",
    "MockSigGen",
    "Motors",
    "SigGen",
]
