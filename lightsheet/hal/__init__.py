"""HAL subpackage re-export shim.

Downstream code and tests import from the ``lightsheet.hal`` namespace
rather than the deeper ``lightsheet.hal.real.*`` / ``lightsheet.hal.mocks.*``
paths. Explicit ``__all__`` avoids leaking private symbols.
"""

from typing import Any

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
    IPowerMeter,
    ISigGen,
    ISigGenCore,
)
from lightsheet.hal.mocks.mock_camera import MockCamera
from lightsheet.hal.mocks.mock_etls import MockETLs
from lightsheet.hal.mocks.mock_laser import MockLaser
from lightsheet.hal.mocks.mock_motors import MockMotors
from lightsheet.hal.mocks.mock_power_meter import MockPowerMeter
from lightsheet.hal.mocks.mock_siggen import MockSigGen
from lightsheet.hal.real.camera import Camera
from lightsheet.hal.real.daqlaser import DAQLaser, InvertedVoltMap, LinearVoltMap
from lightsheet.hal.real.etls import ETLs
from lightsheet.hal.real.ibeam_smart import IBeam, IBeamSmartLaser
from lightsheet.hal.real.motors import Motors
from lightsheet.hal.real.pm100d import PM100D, PM100DError, PM100DNotConnected
from lightsheet.hal.real.siggen import SigGen

# DeviceRegistry / UnresolvedDeviceError are NOT imported at barrel load
# time: the registry module imports pyserial + pyyaml at module top, and
# the invariant is that the registry is never imported on the --demo path.
# The composition root imports DeviceRegistry directly inside the not-demo
# branch. They remain in __all__ and are resolved lazily via __getattr__.

__all__ = [
    "PM100D",
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
    "IPowerMeter",
    "ISigGen",
    "ISigGenCore",
    "InvertedVoltMap",
    "LinearVoltMap",
    "MockCamera",
    "MockETLs",
    "MockLaser",
    "MockMotors",
    "MockPowerMeter",
    "MockSigGen",
    "Motors",
    "PM100DError",
    "PM100DNotConnected",
    "SigGen",
    "UnresolvedDeviceError",
]

_LAZY_REGISTRY_NAMES = {"DeviceRegistry", "UnresolvedDeviceError"}


def __getattr__(name: str) -> Any:
    """Lazily import DeviceRegistry / UnresolvedDeviceError on first
    attribute access so the registry module is not loaded on the --demo path."""
    if name in _LAZY_REGISTRY_NAMES:
        from lightsheet.hal.registry import DeviceRegistry, UnresolvedDeviceError

        globals()["DeviceRegistry"] = DeviceRegistry
        globals()["UnresolvedDeviceError"] = UnresolvedDeviceError
        return globals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
