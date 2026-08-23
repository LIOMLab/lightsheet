"""Frozen DeviceBundle — the immutable value object for HAL handle injection.

The Phase 5 composition root constructs a single ``DeviceBundle`` from the
resolved HAL instances (real on the rig, mock under ``--demo``) and hands it
to the controller / AcquisitionCoordinator in place of the god object's
ad-hoc ``self.camera`` / ``self.siggen`` / ``self.motors`` / ``self.etls`` /
``self.lasers`` attributes. Bundling the five device handles in one frozen
dataclass makes the dependency explicit and prevents a caller from silently
re-binding a handle after construction.

The frozen invariant is a safety property: the E-stop kill path
(``Controller_MainWindow.updateUi_estop_pressed``) iterates ``self.lasers``
and calls ``off()`` on each. If a caller could swap the laser tuple after
construction (e.g. ``bundle.lasers = (other,)``), the kill path would miss
the live handle and fail to de-energize a Class IIIB laser. ``frozen=True``
turns that into a ``dataclasses.FrozenInstanceError`` at the swap site
instead of a silent kill-path miss.

The ``lasers`` field is a ``tuple`` (not ``list``) so the sequence itself is
immutable alongside the frozen dataclass — a ``bundle.lasers.append(...)``
is not even syntactically available.

The five field types are the core HAL ABCs (``ICamera`` / ``ISigGen`` /
``IMotors`` / ``IETLs`` / ``ILaser``) so a type checker can verify the
composition root hands in real or mock instances that satisfy the contract.
"""

from dataclasses import dataclass

from lightsheet.hal.interfaces import ICamera, IETLs, ILaser, IMotors, ISigGen


@dataclass(frozen=True)
class DeviceBundle:
    """Immutable bundle of the five HAL device handles.

    Fields:
        camera: the camera HAL instance (real ``Camera`` or ``MockCamera``).
        siggen: the signal-generator HAL instance (real ``SigGen`` or
            ``MockSigGen``) — drives galvo/ETL AO + camera trigger DO.
        motors: the motors container HAL instance (real ``Motors`` or
            ``MockMotors``) — three Zaber axes.
        etls: the ETLs container HAL instance (real ``ETLs`` or
            ``MockETLs``) — two Optotune EL-10-30 lenses.
        lasers: the laser HAL instances (``DAQLaser`` / ``IBeamSmartLaser``
            / ``MockLaser``) as an immutable tuple. The E-stop kill path
            iterates this tuple; mutating it after construction is forbidden
            by the frozen dataclass (safety invariant).
    """

    camera: ICamera
    siggen: ISigGen
    motors: IMotors
    etls: IETLs
    lasers: tuple[ILaser, ...]
