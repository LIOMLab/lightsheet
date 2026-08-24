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

# DeviceRegistry / UnresolvedDeviceError are NOT imported at barrel load
# time. The registry module imports pyserial's serial.tools.list_ports and
# pyyaml at module top, and the documented invariant (registry.py
# docstring) is that the registry is never imported on the --demo /
# LIGHTSHEET_DEMO=1 path. A barrel-level import would load the registry
# module on every ``from lightsheet.hal import ...`` — including the demo
# branch in __main__._build_demo_bundle — defeating that invariant. The
# composition root imports DeviceRegistry directly inside the not-demo
# branch (lightsheet/__main__.py), so no in-tree caller needs the barrel
# re-export. They remain in __all__ and are resolved lazily via
# __getattr__ below for any out-of-tree caller that still imports them
# from the lightsheet.hal namespace.

__all__ = [
    "Camera",
    "DAQLaser",
    "DeviceBundle",
    "DeviceRegistry",
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
    "UnresolvedDeviceError",
]

_LAZY_REGISTRY_NAMES = {"DeviceRegistry", "UnresolvedDeviceError"}


def __getattr__(name: str):
    """Lazily import DeviceRegistry / UnresolvedDeviceError on first
    attribute access so the registry module (and its pyserial / pyyaml
    imports) is not loaded when the barrel is imported on the --demo
    path. Other names raise AttributeError as usual."""
    if name in _LAZY_REGISTRY_NAMES:
        from lightsheet.hal.registry import DeviceRegistry, UnresolvedDeviceError

        globals()["DeviceRegistry"] = DeviceRegistry
        globals()["UnresolvedDeviceError"] = UnresolvedDeviceError
        return globals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
