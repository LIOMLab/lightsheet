"""Shared test factory functions promoted verbatim from their per-file origins.

These were previously defined inline in individual test modules. Promoting
them here gives the test-writing-to-green plans (05.1-04/05/06) one canonical
import path for device factories, instead of divergent per-file copies.

Each function is copied VERBATIM from its origin (body + docstring unchanged):
- ``_make_daq_l1`` / ``_make_mock_l1`` / ``_make_ibeam_smart_l2`` /
  ``_make_mock_l2`` <- ``test/test_laser_conformance.py``
- ``_make_motor`` <- ``test/test_motor_limits.py`` (the ``ZaberMotor.__new__``
  bypass that avoids the serial hardware probe)
- ``_make_write_laser`` <- ``test/test_laser_controls.py`` (the Mock ILaser
  stand-in for the ``_write_laser*_power`` paths)
"""

import threading
from unittest.mock import Mock

from lightsheet.hal import DAQLaser, IBeamSmartLaser, MockLaser
from lightsheet.hal.real.motors import ZaberMotor


def _make_daq_l1() -> DAQLaser:
    """DAQLaser configured with Laser 1's values (555 nm, 300 mW max,
    60 mW per Volt, /Dev7/ao0)."""
    return DAQLaser(
        terminal="/Dev7/ao0",
        wavelength=555,
        mw_per_volt=60.0,
        max_power_mw=300.0,
        label="Laser 1 (555 nm)",
    )


def _make_mock_l1() -> MockLaser:
    """MockLaser configured with Laser 1's values (555 nm, 300 mW max,
    60 mW per Volt — kept for symmetry with DAQLaser, unused by the mock's
    own logic)."""
    return MockLaser(
        wavelength=555,
        max_power_mw=300.0,
        mw_per_volt=60.0,
        label="Laser 1 (555 nm)",
    )


def _make_ibeam_smart_l2() -> IBeamSmartLaser:
    """IBeamSmartLaser configured with Laser 2's values (640 nm, 150 mW
    max, COM4 serial). The inner ``IBeam`` is constructed but NOT opened
    (``IBeam.__init__`` does not call ``open()``), so this is safe to run
    on Mac without a physical device — no serial port is touched. The real
    conformance path (rig only) is responsible for calling ``open()`` on
    the inner engine before exercising the serial round-trips."""
    return IBeamSmartLaser(label="Laser 2 (640 nm)")


def _make_mock_l2() -> MockLaser:
    """MockLaser configured with Laser 2's values (640 nm, 150 mW max) —
    the same MockLaser class used for the L1 mock leg, configured for the
    iBeam's wavelength and max power so the L2 conformance id exercises
    the same ILaser surface behind a mock."""
    return MockLaser(
        wavelength=640,
        max_power_mw=150.0,
        mw_per_volt=None,
        label="Laser 2 (640 nm)",
    )


def _make_motor() -> ZaberMotor:
    """Build a ZaberMotor-like instance without running __init__'s serial
    hardware probe. Attributes match a T-LSM050A (id 6210)."""
    motor = ZaberMotor.__new__(ZaberMotor)
    motor.id = 6210
    motor.name = "T-LSM050A"
    motor.microstep_size = 0.047625
    motor.microsteps_max = 1066666
    motor.units = "mm"
    motor.inverted = False
    motor.homed = False
    motor.limit_low_microsteps = 0
    motor.limit_high_microsteps = 1066666
    motor.origin_microsteps = 0
    motor.error = 0
    motor.error_message = ""
    motor.port = "COM3"
    motor.device_number = 1
    return motor


def _make_write_laser(
    label: str,
    active: bool = True,
    max_power: float = 5.0,
    error: int = 0,
    error_message: str = "",
) -> Mock:
    """Build a Mock ILaser stand-in for the _write_laser*_power paths.

    The write paths read .active, .max_power, .error, .error_message,
    .label, and call .set_power(mw). The per-instance RLock lives on
    ._lock (the daemon-thread write path acquires it).
    """
    laser = Mock()
    laser.label = label
    laser.active = active
    laser.max_power = max_power
    laser.error = error
    laser.error_message = error_message
    laser._lock = threading.RLock()
    return laser
