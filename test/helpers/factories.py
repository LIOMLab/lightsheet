"""Shared factory helpers for building HAL objects in tests."""

from __future__ import annotations

from lightsheet.hal import (
    DeviceBundle,
    MockCamera,
    MockETLs,
    MockLaser,
    MockMotors,
    MockSigGen,
)


def make_bundle() -> DeviceBundle:
    """Build a mock ``DeviceBundle`` mirroring ``_build_demo_bundle()`` in
    ``lightsheet/__main__.py``.

    Camera is created with ``verbose=False`` to keep test output clean.
    The two mock lasers cover the demo wavelengths (555 nm / 647 nm).
    """
    camera = MockCamera(verbose=False)
    siggen = MockSigGen(camera)
    motors = MockMotors()
    lasers = (
        MockLaser(
            wavelength=555,
            max_power_mw=300.0,
            mw_per_volt=60.0,
            label="Laser 1 (555 nm)",
            calibration_curve=None,
        ),
        MockLaser(
            wavelength=647,
            max_power_mw=150.0,
            label="Laser 2 (647 nm)",
        ),
    )
    etls = MockETLs()
    return DeviceBundle(
        camera=camera,
        siggen=siggen,
        motors=motors,
        etls=etls,
        lasers=lasers,
    )


__all__ = ["make_bundle"]
