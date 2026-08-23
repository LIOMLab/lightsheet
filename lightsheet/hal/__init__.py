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
    from lightsheet.hal import Lasers, MockLasers, ILasers, ILasersCore
    from lightsheet.hal import IBeam, MockIBeam, IIBeam, IIBeamCore

Wave 1 (Plan 01) re-exported only the Camera family. Wave 2 (Plan 02)
expanded the shim to cover SigGen, Motors, and ETLs. Wave 3 (Plan 03)
adds Lasers and IBeam — all 6 device families now route through this
shim, and the top-level ``from lightsheet.<device> import ...`` paths no
longer exist.

Explicit ``__all__`` avoids leaking private symbols from ``interfaces.py``
and the ``real/`` / ``mocks/`` subpackages.
"""

from lightsheet.hal.interfaces import (
    ICamera,
    ICameraCore,
    IETLs,
    IETLsCore,
    IIBeam,
    IIBeamCore,
    ILaser,
    ILasers,
    ILasersCore,
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
from lightsheet.hal.mocks.mock_ibeam import MockIBeam
from lightsheet.hal.mocks.mock_laser import MockLaser
from lightsheet.hal.mocks.mock_lasers import MockLasers
from lightsheet.hal.mocks.mock_motors import MockMotors
from lightsheet.hal.mocks.mock_siggen import MockSigGen
from lightsheet.hal.real.camera import Camera
from lightsheet.hal.real.daqlaser import DAQLaser
from lightsheet.hal.real.etls import ETLs
from lightsheet.hal.real.ibeam import IBeam
from lightsheet.hal.real.lasers import Lasers
from lightsheet.hal.real.motors import Motors
from lightsheet.hal.real.siggen import SigGen

__all__ = [
    "Camera",
    "DAQLaser",
    "ETLs",
    "IBeam",
    "ICamera",
    "ICameraCore",
    "IETLs",
    "IETLsCore",
    "IIBeam",
    "IIBeamCore",
    "ILaser",
    "ILasers",
    "ILasersCore",
    "IMotor",
    "IMotorCore",
    "IMotors",
    "IMotorsCore",
    "IOptotune",
    "ISigGen",
    "ISigGenCore",
    "Lasers",
    "MockCamera",
    "MockETLs",
    "MockIBeam",
    "MockLaser",
    "MockLasers",
    "MockMotors",
    "MockSigGen",
    "Motors",
    "SigGen",
]
