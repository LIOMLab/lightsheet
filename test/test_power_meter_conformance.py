"""TST-04 conformance suite — IPowerMeter family.

Parametrized over ``[real, mock]`` with one assertion body behind both paths.
The real id (``PM100D``) is skipped on Mac (the TLPMX DLL is Windows-only);
the mock id (``MockPowerMeter``) always runs. ``POWER_METER_CONTRACT`` is the
single source of truth for the power-meter surface (open/close/zero +
read_power/read_power_mw/read_averaged + error attrs).

``open`` / ``close`` are exercised by ``assert_lifecycle`` (no-op on the
mock, real open/close on the rig). ``zero`` and the read getters are
existence checks only — ``zero`` has side effects (dark offset) and the
getters issue DLL calls on the real path.

This is a BEHAVIOR test (AGENTS.md §5).
"""

import os

import pytest

from lightsheet.hal import PM100D, MockPowerMeter
from lightsheet.hal.conformance import POWER_METER_CONTRACT

# Module-level hardware gate. Set LIGHTSHEET_HW=1 on the rig to run the
# real conformance path (the TLPMX DLL + a physical PM100D are required).
_has_hardware: bool = os.environ.get("LIGHTSHEET_HW", "0") == "1"


@pytest.mark.parametrize(
    "device_factory",
    [
        pytest.param(
            lambda: PM100D(wavelength_nm=488.0),
            marks=[
                pytest.mark.skipif(not _has_hardware, reason="rig only"),
                pytest.mark.xdist_group("rig_hardware"),
            ],
            id="real",
        ),
        pytest.param(
            lambda: MockPowerMeter(wavelength_nm=488.0),
            id="mock",
        ),
    ],
)
def test_power_meter_conformance(device_factory: object) -> None:
    """One assertion body behind both [real, mock] — the structural
    divergence catch. Covers the IPowerMeter surface (open/close/zero +
    read getters + error attrs)."""
    dev = device_factory()
    POWER_METER_CONTRACT.assert_lifecycle(dev)
    POWER_METER_CONTRACT.assert_error_surface(dev)
    POWER_METER_CONTRACT.assert_read_attrs(dev)
    POWER_METER_CONTRACT.assert_setter_methods(dev)
    POWER_METER_CONTRACT.assert_getter_methods(dev)
