"""Branch coverage for the ``lightsheet.hal`` barrel re-export shim.

Exercises the lazy ``__getattr__`` for ``DeviceRegistry`` /
``UnresolvedDeviceError`` (the registry-is-not-imported-on-demo invariant)
and the ``AttributeError`` raise for an unknown name.
"""

from __future__ import annotations

import importlib

import pytest


def test_barrel_getattr_lazy_loads_deviceregistry() -> None:
    """Accessing ``DeviceRegistry`` via the barrel triggers the lazy
    import (the if-branch of __getattr__)."""
    import lightsheet.hal as hal

    # Ensure the lazy attrs are not yet cached (reload to reset).
    for name in ("DeviceRegistry", "UnresolvedDeviceError"):
        if name in hal.__dict__:
            del hal.__dict__[name]
    hal = importlib.reload(hal)  # ty: ignore[invalid-assignment]
    dr = hal.DeviceRegistry
    from lightsheet.hal.registry import DeviceRegistry as RealDR

    assert dr is RealDR


def test_barrel_getattr_lazy_loads_unresolved_device_error() -> None:
    import lightsheet.hal as hal

    if "UnresolvedDeviceError" in hal.__dict__:
        del hal.__dict__["UnresolvedDeviceError"]
    hal = importlib.reload(hal)  # ty: ignore[invalid-assignment]
    ude = hal.UnresolvedDeviceError
    from lightsheet.hal.registry import UnresolvedDeviceError as RealUDE

    assert ude is RealUDE


def test_barrel_getattr_raises_attribute_error_for_unknown_name() -> None:
    """The else-branch raises AttributeError for an unknown name."""
    import lightsheet.hal as hal

    with pytest.raises(AttributeError):
        hal.nonexistent_symbol  # noqa: B018
