"""TST-04 conformance suite — SigGen family (D-15).

Parametrized over ``[real, mock]`` with one assertion body behind both paths.
The real id (``SigGen``) is skipped on Mac; the mock id (``MockSigGen``)
always runs. ``SIGGEN_CONTRACT`` is the single source of truth.

SigGen takes a camera dependency (``SigGen(camera)``). The real factory
constructs a real ``Camera(verbose=False)`` first (skipped on Mac via
skipif); the mock factory constructs ``MockSigGen(MockCamera())``.

This is a BEHAVIOR test (AGENTS.md §5).
"""

import os

import pytest

from lightsheet.hal import Camera, MockCamera, MockSigGen, SigGen
from lightsheet.hal.conformance import SIGGEN_CONTRACT

# Module-level hardware gate (D-15). Mirrors conftest._has_hardware but
# defined inline so the test file is self-contained at collection time
# (parametrize marks are evaluated before fixtures resolve). Set
# LIGHTSHEET_HW=1 on the rig to run the real conformance path.
_has_hardware: bool = os.environ.get("LIGHTSHEET_HW", "0") == "1"


@pytest.mark.parametrize(
    "device_factory",
    [
        pytest.param(
            lambda: SigGen(Camera(verbose=False)),
            marks=pytest.mark.skipif(not _has_hardware, reason="rig only"),
            id="real",
        ),
        pytest.param(lambda: MockSigGen(MockCamera()), id="mock"),
    ],
)
def test_siggen_conformance(device_factory: object) -> None:
    """One assertion body behind both [real, mock] — the structural
    divergence catch (D-15). SigGen takes a camera dependency; the real
    factory builds a real Camera (skipped on Mac), the mock builds a
    MockSigGen(MockCamera())."""
    dev = device_factory()
    SIGGEN_CONTRACT.assert_lifecycle(dev)
    SIGGEN_CONTRACT.assert_error_surface(dev)
    SIGGEN_CONTRACT.assert_read_attrs(dev)
