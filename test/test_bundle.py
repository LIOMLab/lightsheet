"""TDD tests for the frozen DeviceBundle dataclass (RED phase).

DeviceBundle is the immutable value object that the Phase 5 composition root
will hand to the controller / AcquisitionCoordinator in place of the god
object's ad-hoc ``self.camera`` / ``self.siggen`` / ... attributes. It is a
``@dataclass(frozen=True)`` so a re-bound laser handle cannot silently fail
to kill a live laser on E-stop (the safety invariant: the kill path iterates
``self.lasers`` and calls ``off()``; if a caller swapped the tuple after
construction the kill path would miss the live handle).

These tests assert the contract before the implementation exists. Run them
now — they fail with ImportError / AttributeError. After the GREEN commit
they pass.
"""

import dataclasses
from unittest.mock import Mock

import pytest


def test_device_bundle_construct_and_read_fields() -> None:
    """Constructing DeviceBundle with the five HAL handles succeeds and each
    field is readable back unchanged."""
    from lightsheet.hal.bundle import DeviceBundle

    camera = Mock(name="camera")
    siggen = Mock(name="siggen")
    motors = Mock(name="motors")
    etls = Mock(name="etls")
    laser1 = Mock(name="laser1")
    laser2 = Mock(name="laser2")

    bundle = DeviceBundle(
        camera=camera,
        siggen=siggen,
        motors=motors,
        etls=etls,
        lasers=(laser1, laser2),
    )

    assert bundle.camera is camera
    assert bundle.siggen is siggen
    assert bundle.motors is motors
    assert bundle.etls is etls
    assert bundle.lasers == (laser1, laser2)


def test_device_bundle_is_frozen_dataclass() -> None:
    """DeviceBundle is a frozen dataclass — mutating any field raises
    FrozenInstanceError (the E-stop safety invariant)."""
    from lightsheet.hal.bundle import DeviceBundle

    assert dataclasses.is_dataclass(DeviceBundle)
    # frozen=True sets __dataclass_params__.frozen
    params = getattr(DeviceBundle, "__dataclass_params__", None)
    assert params is not None and params.frozen is True

    bundle = DeviceBundle(
        camera=Mock(),
        siggen=Mock(),
        motors=Mock(),
        etls=Mock(),
        lasers=(Mock(),),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        bundle.lasers = (Mock(),)  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        bundle.camera = Mock()  # type: ignore[misc]


def test_device_bundle_barrel_reexport() -> None:
    """``from lightsheet.hal import DeviceBundle`` resolves to the same class
    object as the direct module import (barrel re-export smoke test)."""
    from lightsheet.hal import DeviceBundle as barrel_reexport
    from lightsheet.hal.bundle import DeviceBundle as direct

    assert barrel_reexport is direct
