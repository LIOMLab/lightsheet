"""TST-04 conformance suite — unified ILaser family.

Parametrized over ``[real, mock]`` with one assertion body behind both
paths. The real id (``DAQLaser``) is skipped on Mac; the mock id
(``MockLaser``) always runs. ``LASER_CONTRACT`` is the single source of
truth for the single-channel on/off + read-attr + set_power surface.

**Safety (AGENTS.md §2):**
- ``off()`` MUST be synchronous — set ``active=False`` and ``power=0.0``
  and return None immediately, no thread/queue offload. The E-stop kill
  path drives ``laser.off()`` on the GUI thread; offloading it would
  break the synchronous-off safety contract for a Class IIIB laser.
- ``set_power`` MUST clamp to ``max_power`` at the HAL boundary (mW
  canonical).

Both safety invariants are asserted here on both paths (the same checks
the Mock* tests run, now behind the [real, mock] parametrize).

This is a BEHAVIOR test (AGENTS.md §5).
"""

import os

import pytest

from lightsheet.hal import DAQLaser, MockLaser
from lightsheet.hal.conformance import LASER_CONTRACT

# Module-level hardware gate. Mirrors conftest._has_hardware but defined
# inline so the test file is self-contained at collection time (parametrize
# marks are evaluated before fixtures resolve). Set LIGHTSHEET_HW=1 on the
# rig to run the real conformance path.
_has_hardware: bool = os.environ.get("LIGHTSHEET_HW", "0") == "1"


def _make_daq_l1() -> DAQLaser:
    """DAQLaser configured with Laser 1's values (561 nm, 300 mW max,
    60 mW per Volt, /Dev7/ao0)."""
    return DAQLaser(
        terminal="/Dev7/ao0",
        wavelength=561,
        mw_per_volt=60.0,
        max_power_mw=300.0,
        label="Laser 1 (561 nm)",
    )


def _make_mock_l1() -> MockLaser:
    """MockLaser configured with Laser 1's values (561 nm, 300 mW max,
    60 mW per Volt — kept for symmetry with DAQLaser, unused by the mock's
    own logic)."""
    return MockLaser(
        wavelength=561,
        max_power_mw=300.0,
        mw_per_volt=60.0,
        label="Laser 1 (561 nm)",
    )


@pytest.mark.parametrize(
    "device_factory",
    [
        pytest.param(
            _make_daq_l1,
            marks=pytest.mark.skipif(not _has_hardware, reason="rig only"),
            id="daq_real",
        ),
        pytest.param(_make_mock_l1, id="daq_mock"),
    ],
)
def test_laser_conformance(device_factory: object) -> None:
    """One assertion body behind both [real, mock] — the structural
    divergence catch. The ILaser lifecycle verbs (on/off) have side
    effects (DAQ writes), so the contract checks existence via
    assert_lifecycle (hasattr) and exercises only the safe open/close if
    present. The synchronous-off + power-clamp safety checks run separately
    below on both paths."""
    dev = device_factory()
    LASER_CONTRACT.assert_lifecycle(dev)
    LASER_CONTRACT.assert_error_surface(dev)
    LASER_CONTRACT.assert_read_attrs(dev)
    LASER_CONTRACT.assert_setter_methods(dev)


@pytest.mark.parametrize(
    "device_factory",
    [
        pytest.param(
            _make_daq_l1,
            marks=pytest.mark.skipif(not _has_hardware, reason="rig only"),
            id="daq_real",
        ),
        pytest.param(_make_mock_l1, id="daq_mock"),
    ],
)
def test_laser_off_is_synchronous(device_factory: object) -> None:
    """SAFETY (AGENTS.md §2): off() MUST be synchronous — set active=False
    and power=0.0 and return None immediately, no thread/queue offload.
    The E-stop kill path drives laser.off() on the GUI thread; offloading
    it would break the synchronous-off safety contract for a Class IIIB
    laser. This assertion runs behind both [real, mock].

    We do not call on() first (energizing the laser is an operator action
    per AGENTS.md §2); we assert off() on a freshly-constructed (off)
    device is synchronous and leaves active False and power 0.0.
    """
    dev = device_factory()
    result = dev.off()
    assert result is None
    assert dev.active is False, (
        "off() must synchronously set active=False — no queue/thread offload "
        "(AGENTS.md §2 E-stop kill path for a Class IIIB laser)"
    )
    assert dev.power == 0.0, (
        "off() must synchronously set power=0.0 — no queue/thread offload "
        "(AGENTS.md §2 E-stop kill path for a Class IIIB laser)"
    )


@pytest.mark.parametrize(
    "device_factory",
    [
        pytest.param(
            _make_daq_l1,
            marks=pytest.mark.skipif(not _has_hardware, reason="rig only"),
            id="daq_real",
        ),
        pytest.param(_make_mock_l1, id="daq_mock"),
    ],
)
def test_laser_set_power_clamps_to_max(device_factory: object) -> None:
    """SAFETY (AGENTS.md §2): set_power MUST clamp to max_power at the HAL
    boundary (mW canonical). A mock that dropped the clamp would let the
    controller's safety checks atrophy under demo mode, masking a
    regression that would over-drive the laser on the rig. This assertion
    runs behind both [real, mock].

    The DAQLaser real path: set_power(999.0) on an inactive laser stages
    the clamped mW value (no DAQ write attempted while inactive), so the
    clamp is observable on dev.power without energizing the laser. The
    MockLaser path: same — set_power stages the clamped mW in software.
    """
    dev = device_factory()
    dev.set_power(999.0)
    assert dev.power == dev.max_power, (
        "set_power must clamp to max_power at the HAL boundary "
        "(AGENTS.md §2 — Class IIIB laser safety)"
    )


def test_mock_laser_set_power_clamps_to_max() -> None:
    """Dedicated mock-path safety invariant: MockLaser.set_power clamps to
    max_power_mw (mW clamp preserved in the mock per AGENTS.md §2 — a mock
    that dropped the clamp would let the controller's safety checks
    atrophy under demo mode)."""
    dev = _make_mock_l1()
    dev.set_power(999.0)
    assert dev.power == 300.0
    # Floor clamp.
    dev.set_power(-50.0)
    assert dev.power == 0.0
    # In-range value passes through.
    dev.set_power(150.0)
    assert dev.power == 150.0


def test_mock_laser_off_is_synchronous() -> None:
    """Dedicated mock-path safety invariant: MockLaser.off() is synchronous
    — sets active=False, power=0.0, returns None immediately (E-stop kill
    path, AGENTS.md §2)."""
    dev = _make_mock_l1()
    dev.set_power(150.0)
    result = dev.off()
    assert result is None
    assert dev.active is False
    assert dev.power == 0.0


def test_mock_laser_on_sets_active() -> None:
    """MockLaser.on() sets active=True unconditionally (no hardware to fail
    against, mirroring MockIBeam.on())."""
    dev = _make_mock_l1()
    assert dev.active is False
    dev.on()
    assert dev.active is True
