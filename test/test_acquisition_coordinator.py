"""AcquisitionCoordinator extraction tests (god-object split).

``AcquisitionCoordinator`` is a plain-Python collaborator that owns the
four acquisition worker bodies (``preview_mode_worker``,
``live_mode_worker``, ``single_mode_worker``, ``stack_mode_worker``) plus
``acquire_scan``. The shell delegates through ``self._acq``. The
coordinator reads shell-owned state (``sig_message``, ``estop_event``,
``<mode>_mode_started`` flags, ``_fs``, ``ui.*`` widgets) via an injected
``self._shell`` reference and reads its own ``self.camera`` /
``self.siggen`` / ``self.motors`` / ``self._hw`` attributes.

Behavior covered (per the plan's ``<behavior>`` block):

1. ``AcquisitionCoordinator(bundle, hw, shell)`` exposes the five methods
   as callable attributes.
2. The golden-master replay (``default.json`` + ``siggen_create_scanner_fail.json``)
   is unchanged after the extraction — verified by the existing replay
   tests in ``test_golden_acquisition.py`` passing without regenerating
   the fixtures.
"""

from __future__ import annotations

from unittest.mock import Mock

from lightsheet.gui.acquisition_coordinator import AcquisitionCoordinator
from lightsheet.hal import DeviceBundle, MockCamera, MockETLs, MockLaser, MockMotors, MockSigGen


def _make_bundle() -> DeviceBundle:
    """Build a demo DeviceBundle with two MockLaser instances."""
    camera = MockCamera(verbose=True)
    siggen = MockSigGen(camera)
    motors = MockMotors()
    lasers = (
        MockLaser(wavelength=555, max_power_mw=300.0, label="Laser 1 (555 nm)"),
        MockLaser(wavelength=640, max_power_mw=150.0, label="Laser 2 (640 nm)"),
    )
    etls = MockETLs()
    return DeviceBundle(camera=camera, siggen=siggen, motors=motors, etls=etls, lasers=lasers)


def test_acquisition_coordinator_exposes_five_worker_methods() -> None:
    """AcquisitionCoordinator(bundle, hw, shell) constructed with Mock
    bundle/hw/shell exposes single_mode_worker, live_mode_worker,
    stack_mode_worker, preview_mode_worker, acquire_scan as callable
    methods."""
    bundle = _make_bundle()
    hw = Mock()
    shell = Mock()
    acq = AcquisitionCoordinator(bundle, hw, shell)

    for name in (
        "single_mode_worker",
        "live_mode_worker",
        "stack_mode_worker",
        "preview_mode_worker",
        "acquire_scan",
    ):
        method = getattr(acq, name, None)
        assert callable(method), (
            f"AcquisitionCoordinator must expose {name} as a callable method "
            f"(got {method!r})"
        )


def test_acquisition_coordinator_stores_bundle_handles_and_collaborators() -> None:
    """The coordinator stores the bundle's HAL handles as its own
    attributes (self.camera / self.siggen / self.motors) and the hw +
    shell references for delegation."""
    bundle = _make_bundle()
    hw = Mock()
    shell = Mock()
    acq = AcquisitionCoordinator(bundle, hw, shell)

    assert acq.camera is bundle.camera
    assert acq.siggen is bundle.siggen
    assert acq.motors is bundle.motors
    assert acq._hw is hw
    assert acq._shell is shell
