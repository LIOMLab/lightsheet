"""TST-04 conformance suite — SigGen family (D-15).

Parametrized over ``[real, mock]`` with one assertion body behind both paths.
The real id (``SigGen``) is skipped on Mac; the mock id (``MockSigGen``)
always runs. ``SIGGEN_CONTRACT`` is the single source of truth.

SigGen takes a camera dependency (``SigGen(camera)``). The real factory
constructs a real ``Camera(verbose=False)`` first (skipped on Mac via
skipif); the mock factory constructs ``MockSigGen(MockCamera())``.

The real factory wraps ``Camera`` construction with a ``pytest.skip`` on
``RuntimeError`` / ``OSError`` so the test SKIPS (not fails) when the
camera is not connected or powered on the rig. The PCO SDK raises
``RuntimeError`` when the camera is absent and ``OSError`` on a missing
device; without the wrapper the real path would fail instead of skipping,
conflating hardware-availability with a conformance regression. The mock
path (``MockSigGen(MockCamera())``) is unaffected — ``MockCamera`` never
raises.

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


def _real_siggen_factory() -> SigGen:
    """Build a real ``SigGen(Camera(verbose=False))``, skipping gracefully
    when the camera is not connected/powered.

    The PCO SDK raises ``RuntimeError`` when the camera is absent and
    ``OSError`` on a missing device. Without this wrapper the real
    conformance path would FAIL instead of skipping when the camera is
    unavailable, conflating hardware-availability with a conformance
    regression. The skip reason names the camera-absent condition so the
    rig operator knows to connect/power the PCO camera before re-running
    the real conformance path.
    """
    try:
        camera = Camera(verbose=False)
    except (RuntimeError, OSError) as e:
        pytest.skip(
            f"camera not available ({e}) — connect/power the PCO camera "
            "to run the real SigGen conformance path"
        )
    return SigGen(camera)


@pytest.mark.parametrize(
    "device_factory",
    [
        pytest.param(
            _real_siggen_factory,
            marks=pytest.mark.skipif(not _has_hardware, reason="rig only"),
            id="real",
        ),
        pytest.param(lambda: MockSigGen(MockCamera()), id="mock"),
    ],
)
def test_siggen_conformance(device_factory: object) -> None:
    """One assertion body behind both [real, mock] — the structural
    divergence catch (D-15). SigGen takes a camera dependency; the real
    factory builds a real Camera (skipped on Mac, and skips gracefully on
    the rig when the camera is absent), the mock builds a
    MockSigGen(MockCamera())."""
    dev = device_factory()
    SIGGEN_CONTRACT.assert_lifecycle(dev)
    SIGGEN_CONTRACT.assert_error_surface(dev)
    SIGGEN_CONTRACT.assert_read_attrs(dev)
    SIGGEN_CONTRACT.assert_setter_methods(dev)
