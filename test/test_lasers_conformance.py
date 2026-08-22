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

import contextlib
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
    LASERS_CONTRACT.assert_setter_methods(dev)


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
    """SAFETY (AGENTS.md §2): the commanded laser power MUST clamp to the
    configured Max Power at the HAL boundary. A mock that removed the
    clamp would let the controller's safety checks atrophy under demo
    mode, masking a regression that would over-drive the laser AO
    channels on the rig.

    The real and mock Lasers classes expose DIFFERENT clamp surfaces, so
    the test body branches on the device type to call the correct surface
    and assert on the correct target:

    - Real path: the real ``Lasers`` class has no ``set_power`` method —
      the controller sets ``laser1_power`` directly and calls
      ``laser1_on()``, which sets ``_laser1_setpoint = min(laser1_power,
      laser1_max_power)`` and then ``_update_setpoints`` re-clamps before
      the DAQ write. So the real path sets ``laser1_power = 999999``,
      calls ``laser1_on()``, and asserts
      ``_laser1_setpoint == laser1_max_power`` (the real clamp path
      inside ``_update_setpoints``). ``laser1_off()`` in the finally
      block reverts the setpoint to 0 and the active flag to False so
      the test does not leave the laser staged on. Same for channel 2.

    - Mock path: ``MockLasers.set_power`` is a mock-only convenience
      method that clamps ``laser1_power`` directly in software. The mock
      path keeps calling ``set_power`` and asserting on ``laser1_power``
      because that is the mock's clamp surface.

    Both paths verify the AGENTS.md §2 HAL-boundary clamp; they differ
    in surface because the real and mock clamp surfaces differ (the
    real clamp lives inside ``_update_setpoints``, invoked by
    ``laser1_on``; the mock's ``set_power`` is a mock-only extra). The
    real Lasers class is NOT given a ``set_power`` method — the clamp
    already exists at the HAL boundary in ``_update_setpoints``, and
    adding a method the controller does not call would be test-driven
    surface addition.

    Real-path energization note: calling ``laser1_on()`` on the rig
    drives the DAQ AO write of the clamped max value (5.0 V). This
    energizes the laser AO channels. The operator explicitly ran
    ``LIGHTSHEET_HW=1`` to run the real conformance path, so this is
    operator-opted-in per AGENTS.md §2. The clamped value (5.0 V =
    ``laser1_max_power``) is the configured safe max, so the test
    verifies the clamp by driving the safe max value. The
    finally-cleanup (``laser1_off``) reverts to 0 V.
    """
    dev = device_factory()
    is_mock = isinstance(dev, MockLasers)
    if is_mock:
        # Mock path — MockLasers.set_power is the mock's clamp surface.
        dev.set_power(1, 999999)
        assert dev.laser1_power == dev.laser1_max_power, (
            "set_power must clamp to laser1_max_power at the HAL boundary "
            "(AGENTS.md §2 — Class IIIB laser safety)"
        )
        dev.set_power(2, 999999)
        assert dev.laser2_power == dev.laser2_max_power, (
            "set_power must clamp to laser2_max_power at the HAL boundary "
            "(AGENTS.md §2 — Class IIIB laser safety)"
        )
        return
    # Real path — the real Lasers class clamps inside _update_setpoints
    # (invoked by laser1_on), so set laser1_power + call laser1_on and
    # assert on _laser1_setpoint. laser1_off() in finally reverts the
    # setpoint to 0 and the active flag to False so the test does not
    # leave the laser staged on.
    try:
        dev.laser1_power = 999999
        dev.laser1_on()
        assert dev._laser1_setpoint == dev.laser1_max_power, (
            "laser1_on must clamp _laser1_setpoint to laser1_max_power at "
            "the HAL boundary (AGENTS.md §2 — Class IIIB laser safety)"
        )
        dev.laser2_power = 999999
        dev.laser2_on()
        assert dev._laser2_setpoint == dev.laser2_max_power, (
            "laser2_on must clamp _laser2_setpoint to laser2_max_power at "
            "the HAL boundary (AGENTS.md §2 — Class IIIB laser safety)"
        )
    finally:
        # Cleanup — revert setpoints to 0 and active flags to False.
        # Guard each off() so a failure in one does not skip the other.
        with contextlib.suppress(Exception):
            dev.laser1_off()
        with contextlib.suppress(Exception):
            dev.laser2_off()
