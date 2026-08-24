"""TST-04 conformance suite — IPowerMeter family.

Parametrized over ``[real, mock]`` with one assertion body behind both paths.
The real id (``PM100D``) runs ONLY when a physical PM100D is connected — the
PM100D is a calibration/diagnostic instrument that is not permanently attached
to the rig, so ``is_pm100d_available()`` (DLL load + findRsrc probe) is the
gate, not just ``LIGHTSHEET_HW``. The mock id (``MockPowerMeter``) always
runs. ``POWER_METER_CONTRACT`` is the single source of truth for the
power-meter surface (open/close/zero + read_power/read_power_mw/
read_averaged + error attrs).

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
from lightsheet.hal.real.pm100d import is_pm100d_available

# Module-level hardware gate. ``LIGHTSHEET_HW=1`` selects the rig path, but
# the PM100D is an optional calibration instrument — ``is_pm100d_available()``
# does a read-only DLL + findRsrc probe and returns False when the device is
# not connected (and always False on Mac, where the TLPMX DLL is absent).
# Evaluated once at collection time (a single read-only probe, safe per
# AGENTS.md §4).
_has_hardware: bool = os.environ.get("LIGHTSHEET_HW", "0") == "1"
_pm100d_connected: bool = _has_hardware and is_pm100d_available()


@pytest.mark.parametrize(
    "device_factory",
    [
        pytest.param(
            lambda: PM100D(wavelength_nm=488.0),
            marks=[
                pytest.mark.skipif(
                    not _pm100d_connected,
                    reason="rig only and PM100D must be connected",
                ),
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
    read getters + error attrs). The real id is skipped unless a physical
    PM100D is connected (the device is optional on the rig)."""
    dev = device_factory()
    POWER_METER_CONTRACT.assert_lifecycle(dev)
    POWER_METER_CONTRACT.assert_error_surface(dev)
    POWER_METER_CONTRACT.assert_read_attrs(dev)
    POWER_METER_CONTRACT.assert_setter_methods(dev)
    POWER_METER_CONTRACT.assert_getter_methods(dev)
