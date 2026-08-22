"""TST-04 conformance suite — Lasers family (D-15).

Parametrized over ``[real, mock]`` with one assertion body behind both paths.
The real id (``Lasers``) is skipped on Mac; the mock id (``MockLasers``)
always runs. ``LASERS_CONTRACT`` is the single source of truth for the
2-channel on/off + read-attr surface.

**Safety (AGENTS.md §2):** ``set_power`` MUST clamp to the configured
``Max Power`` at the HAL boundary. This is asserted for the mock path here
and for the real path on the rig (HW2-01). The conformance contract's
``assert_lifecycle`` exercises only the safe idempotent verbs (``open`` /
``close`` are not in the Lasers lifecycle — the on/off verbs have side
effects, so the contract checks existence, not call). The safety behavior
check (power clamping) runs on both paths.

This is a BEHAVIOR test (AGENTS.md §5).
"""

import os

import pytest

from lightsheet.hal import Lasers, MockLasers
from lightsheet.hal.conformance import LASERS_CONTRACT

# Module-level hardware gate (D-15). Mirrors conftest._has_hardware but
# defined inline so the test file is self-contained at collection time
# (parametrize marks are evaluated before fixtures resolve). Set
# LIGHTSHEET_HW=1 on the rig to run the real conformance path.
_has_hardware: bool = os.environ.get("LIGHTSHEET_HW", "0") == "1"


@pytest.mark.parametrize(
    "device_factory",
    [
        pytest.param(
            lambda: Lasers(),
            marks=pytest.mark.skipif(not _has_hardware, reason="rig only"),
            id="real",
        ),
        pytest.param(lambda: MockLasers(), id="mock"),
    ],
)
def test_lasers_conformance(device_factory: object) -> None:
    """One assertion body behind both [real, mock] — the structural
    divergence catch (D-15). The Lasers lifecycle verbs (laser1_on/off,
    laser2_on/off) have side effects (DAQ writes), so the contract checks
    existence via assert_lifecycle (hasattr) and exercises only the safe
    open/close if present. The power-clamp safety check runs separately
    below on both paths."""
    dev = device_factory()
    LASERS_CONTRACT.assert_lifecycle(dev)
    LASERS_CONTRACT.assert_error_surface(dev)
    LASERS_CONTRACT.assert_read_attrs(dev)


@pytest.mark.parametrize(
    "device_factory",
    [
        pytest.param(
            lambda: Lasers(),
            marks=pytest.mark.skipif(not _has_hardware, reason="rig only"),
            id="real",
        ),
        pytest.param(lambda: MockLasers(), id="mock"),
    ],
)
def test_lasers_set_power_clamps_to_max(device_factory: object) -> None:
    """SAFETY (AGENTS.md §2): set_power MUST clamp the commanded power to
    the configured Max Power at the HAL boundary. A mock that removed the
    clamp would let the controller's safety checks atrophy under demo mode,
    masking a regression that would over-drive the laser AO channels on
    the rig. This assertion runs behind both [real, mock] — the same
    safety invariant the Mock* tests check."""
    dev = device_factory()
    dev.set_power(1, 999999)
    assert dev.laser1_power == dev.laser1_max_power, (
        "set_power must clamp to laser1_max_power at the HAL boundary "
        "(AGENTS.md §2 — Class IIIB laser safety)"
    )
    dev.set_power(2, 999999)
    assert dev.laser2_power == dev.laser2_max_power
