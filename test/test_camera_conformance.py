"""TST-04 conformance suite — Camera family (D-15).

Parametrized over ``[real, mock]`` with one assertion body behind both paths.
The real id (``Camera``) is skipped on Mac via
``pytest.param(marks=pytest.mark.skipif(not _has_hardware, ...))`` and runs
on the rig when ``LIGHTSHEET_HW=1``. The mock id (``MockCamera``) always
runs. ``CAMERA_CONTRACT`` (from ``lightsheet.hal.conformance``) is the
single source of truth for the lifecycle/read-attr/setter surface — both
paths call the same ``assert_lifecycle`` / ``assert_error_surface`` /
``assert_read_attrs`` so mock-vs-real drift is structurally caught.

This is a BEHAVIOR test (AGENTS.md §5): it constructs the device and exercises
its runtime surface, not a static-source grep.
"""

import os

import pytest

from lightsheet.hal import Camera, MockCamera
from lightsheet.hal.conformance import CAMERA_CONTRACT

# Module-level hardware gate (D-15). Mirrors conftest._has_hardware but
# defined inline so the test file is self-contained at collection time
# (parametrize marks are evaluated before fixtures resolve). Set
# LIGHTSHEET_HW=1 on the rig to run the real conformance path.
_has_hardware: bool = os.environ.get("LIGHTSHEET_HW", "0") == "1"


@pytest.mark.parametrize(
    "device_factory",
    [
        pytest.param(
            lambda: Camera(verbose=False),
            marks=pytest.mark.skipif(not _has_hardware, reason="rig only"),
            id="real",
        ),
        pytest.param(lambda: MockCamera(), id="mock"),
    ],
)
def test_camera_conformance(device_factory: object) -> None:
    """One assertion body behind both [real, mock] — the structural
    divergence catch (D-15). The real path is skipped on Mac; the mock
    path runs and exercises the contract."""
    dev = device_factory()
    CAMERA_CONTRACT.assert_lifecycle(dev)
    CAMERA_CONTRACT.assert_error_surface(dev)
    CAMERA_CONTRACT.assert_read_attrs(dev)


def test_camera_conformance_empty_config_flagged_unverified() -> None:
    """EDGE (TST-04 empty): conformance with empty/zero-config device
    behavior is flagged-unverified (probe-surfaced, deferred to rig UAT).

    MockCamera constructs with synthetic defaults (no config.ini read),
    so the empty-config path is the mock's default path — already covered
    by ``test_camera_conformance[mock]``. The real Camera's empty-config
    behavior (missing config.ini → cfg_read defaults) is rig-verified at
    HW2-01. This test documents the deferral: it asserts the mock's
    empty-config construct succeeds (the mock path) and records that the
    real path is unverified on Mac.
    """
    dev = MockCamera()
    # The mock constructs with no config.ini — empty-config is its default.
    assert dev.error == 0
    assert dev.xsize is not None  # synthetic default populated
    # Real-path empty-config behavior is deferred to rig UAT (HW2-01).
