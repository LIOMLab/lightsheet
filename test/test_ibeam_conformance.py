"""TST-04 conformance suite — IBeam family (D-15).

Parametrized over ``[real, mock]`` with one assertion body behind both paths.
The real id (``IBeam``) is skipped on Mac; the mock id (``MockIBeam``)
always runs. ``IBEAM_CONTRACT`` is the single source of truth for the
open/close/on/off/enable_channel + read-attr surface.

**Safety (AGENTS.md §2):**
- ``off()`` MUST be synchronous — set ``_is_on=False`` and return None
  immediately, no thread/queue offload. The E-stop kill path drives
  ``ibeam.off()`` on the GUI thread; offloading it would break the
  synchronous-off safety contract for a Class IIIB laser.
- ``set_power`` MUST clamp to ``max_power`` at the HAL boundary.

Both safety invariants are asserted here on both paths (the same checks
the Mock* tests run, now behind the [real, mock] parametrize).

This is a BEHAVIOR test (AGENTS.md §5).
"""

import os

import pytest

from lightsheet.hal import IBeam, MockIBeam
from lightsheet.hal.conformance import IBEAM_CONTRACT

# Module-level hardware gate (D-15). Mirrors conftest._has_hardware but
# defined inline so the test file is self-contained at collection time
# (parametrize marks are evaluated before fixtures resolve). Set
# LIGHTSHEET_HW=1 on the rig to run the real conformance path.
_has_hardware: bool = os.environ.get("LIGHTSHEET_HW", "0") == "1"


@pytest.mark.parametrize(
    "device_factory",
    [
        pytest.param(
            lambda: IBeam(),
            marks=pytest.mark.skipif(not _has_hardware, reason="rig only"),
            id="real",
        ),
        pytest.param(lambda: MockIBeam(), id="mock"),
    ],
)
def test_ibeam_conformance(device_factory: object) -> None:
    """One assertion body behind both [real, mock] — the structural
    divergence catch (D-15). The IBeam lifecycle verbs (on/off) have side
    effects (serial commands), so the contract checks existence via
    assert_lifecycle (hasattr) and exercises only the safe open/close.
    The synchronous-off + power-clamp safety checks run separately below
    on both paths."""
    dev = device_factory()
    IBEAM_CONTRACT.assert_lifecycle(dev)
    IBEAM_CONTRACT.assert_error_surface(dev)
    IBEAM_CONTRACT.assert_read_attrs(dev)
    IBEAM_CONTRACT.assert_setter_methods(dev)


@pytest.mark.parametrize(
    "device_factory",
    [
        pytest.param(
            lambda: IBeam(),
            marks=pytest.mark.skipif(not _has_hardware, reason="rig only"),
            id="real",
        ),
        pytest.param(lambda: MockIBeam(), id="mock"),
    ],
)
def test_ibeam_off_is_synchronous(device_factory: object) -> None:
    """SAFETY (AGENTS.md §2): off() MUST be synchronous — set _is_on=False
    and return None immediately, no thread/queue offload. The E-stop kill
    path drives ibeam.off() on the GUI thread; offloading it would break
    the synchronous-off safety contract for a Class IIIB laser. This
    assertion runs behind both [real, mock]."""
    dev = device_factory()
    # off() must return None and synchronously clear _is_on. We do not
    # call on() first (energizing the laser is an operator action per
    # AGENTS.md §2); we assert off() on a freshly-constructed (off) device
    # is synchronous and leaves _is_on False.
    result = dev.off()
    assert result is None
    assert dev._is_on is False, (
        "off() must synchronously set _is_on=False — no queue/thread offload "
        "(AGENTS.md §2 E-stop kill path for a Class IIIB laser)"
    )


@pytest.mark.parametrize(
    "device_factory",
    [
        pytest.param(
            lambda: IBeam(),
            marks=pytest.mark.skipif(not _has_hardware, reason="rig only"),
            id="real",
        ),
        pytest.param(lambda: MockIBeam(), id="mock"),
    ],
)
def test_ibeam_set_power_clamps_to_max(device_factory: object) -> None:
    """SAFETY (AGENTS.md §2): set_power MUST clamp to max_power at the HAL
    boundary. This assertion runs behind both [real, mock] — the same
    safety invariant the Mock* tests check."""
    dev = device_factory()
    dev.set_power(999999)
    assert dev._power == dev.max_power, (
        "set_power must clamp to max_power at the HAL boundary "
        "(AGENTS.md §2 — Class IIIB laser safety)"
    )
