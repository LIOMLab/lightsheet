"""Camera binning readback conformance (D-02).

The binning_x/binning_y HAL readback provides the XY voxel-size source for
the ZarrSaver's base_res assembly. MockCamera exposes 1x1 defaults (the
rig's current state); the real Camera reads sdk.get_binning() in open()
and arm(). The CAMERA_CONTRACT.read_attrs includes binning_x/binning_y so
the structural drift catch fires if a mock drops them.
"""

from __future__ import annotations

import os

import pytest

from lightsheet.hal import Camera, MockCamera
from lightsheet.hal.conformance import CAMERA_CONTRACT

_has_hardware: bool = os.environ.get("LIGHTSHEET_HW", "0") == "1"


def test_mock_camera_binning_defaults_to_one() -> None:
    """D-02: MockCamera defaults binning_x == binning_y == 1 (no binning).
    The mock populates the same binning attributes the real Camera exposes
    via ``sdk.get_binning()`` so the controller's read path is unchanged
    between real and demo runs."""
    cam = MockCamera()
    assert cam.binning_x == 1
    assert cam.binning_y == 1


@pytest.mark.parametrize(
    "device_factory",
    [
        pytest.param(
            lambda: Camera(verbose=False),
            marks=[
                pytest.mark.skipif(not _has_hardware, reason="rig only"),
                pytest.mark.xdist_group("rig_hardware"),
            ],
            id="real",
        ),
        pytest.param(lambda: MockCamera(), id="mock"),
    ],
)
def test_camera_binning_in_conformance_read_attrs(device_factory: object) -> None:
    """D-02: the CAMERA_CONTRACT.assert_read_attrs passes for both [real,
    mock] once ``binning_x`` / ``binning_y`` are added to the contract's
    read_attrs. The contract is the structural drift catch — adding the
    binning attrs here means a mock that drops them fails the same
    assertion the real path fails."""
    dev = device_factory()  # ty: ignore[call-non-callable]
    CAMERA_CONTRACT.assert_read_attrs(dev)
    # Explicit binning presence check (the contract extension will add
    # these to read_attrs; assert directly as well for clarity).
    assert hasattr(dev, "binning_x")
    assert hasattr(dev, "binning_y")
