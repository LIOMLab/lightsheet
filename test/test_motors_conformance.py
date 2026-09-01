"""TST-04 conformance suite — Motors family (D-15).

Parametrized over ``[real, mock]`` with one assertion body behind both paths.
The real id (``Motors``) is skipped on Mac; the mock id (``MockMotors``)
always runs. ``MOTORS_CONTRACT`` is the single source of truth for the
container surface (open/close + error attrs).

The per-axis ``IMotor`` travel-limit enforcement (AGENTS.md §2 — physical
safety) is covered by ``test/test_mock_abc_conformance.py`` and
``test/test_motor_limits.py``; this conformance test covers the container
surface that the controller's ``self.motors.open()`` / ``self.motors.close()``
call sites depend on.

This is a BEHAVIOR test (AGENTS.md §5).
"""

import os

import pytest

from lightsheet.hal import MockMotors, Motors
from lightsheet.hal.conformance import MOTORS_CONTRACT

# Module-level hardware gate (D-15). Mirrors conftest._has_hardware but
# defined inline so the test file is self-contained at collection time
# (parametrize marks are evaluated before fixtures resolve). Set
# LIGHTSHEET_HW=1 on the rig to run the real conformance path.
_has_hardware: bool = os.environ.get("LIGHTSHEET_HW", "0") == "1"


@pytest.mark.parametrize(
    "device_factory",
    [
        pytest.param(
            lambda: Motors(),
            marks=[
                pytest.mark.skipif(not _has_hardware, reason="rig only"),
                pytest.mark.xdist_group("rig_hardware"),
            ],
            id="real",
        ),
        pytest.param(lambda: MockMotors(), id="mock"),
    ],
)
def test_motors_conformance(device_factory: object) -> None:
    """One assertion body behind both [real, mock] — the structural
    divergence catch (D-15). Covers the Motors container surface
    (open/close + error attrs). Per-axis travel-limit enforcement is
    covered by test_mock_abc_conformance + test_motor_limits."""
    dev = device_factory()  # ty: ignore[call-non-callable]
    MOTORS_CONTRACT.assert_lifecycle(dev)
    MOTORS_CONTRACT.assert_error_surface(dev)
    MOTORS_CONTRACT.assert_read_attrs(dev)
    MOTORS_CONTRACT.assert_setter_methods(dev)


def test_motors_conformance_boundary_state_flagged_unverified() -> None:
    """EDGE (TST-04 adjacency): when a motor state is exactly at a travel
    limit (e.g. position == limit_high_microsteps), conformance behavior
    is flagged-unverified (probe-surfaced, deferred to rig UAT).

    The mock's per-axis motor starts at ``limit_low_microsteps`` (the low
    limit) — an exact-boundary state. The mock accepts this as a valid
    resting position (no over-travel raise). The real Zaber stage's
    at-limit behavior (does the firmware report a limit-switch hit? does
    a move to the exact limit succeed?) is rig-verified at HW2-01. This
    test documents the deferral: it asserts the mock's at-limit construct
    is valid (the mock path) and records that the real path is unverified
    on Mac.
    """
    dev = MockMotors()
    axis = dev.vertical
    # The mock starts at the low limit — an exact-boundary state.
    assert axis.position_microsteps == axis.limit_low_microsteps  # ty: ignore[unresolved-attribute]
    assert axis.error == 0  # ty: ignore[unresolved-attribute]
    # Real-path at-limit behavior is deferred to rig UAT (HW2-01).
