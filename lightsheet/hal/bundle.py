"""Frozen DeviceBundle — the immutable value object for HAL handle injection.

The composition root constructs a single ``DeviceBundle`` from the resolved
HAL instances (real on the rig, mock under ``--demo``) and hands it to the
controller in place of ad-hoc ``self.camera`` / ``self.siggen`` / etc.
attributes. The frozen invariant is a safety property: the E-stop kill path
iterates ``self.lasers`` and calls ``off()`` on each; if a caller could swap
the laser tuple after construction, the kill path would miss the live handle
and fail to de-energize a Class IIIB laser. ``frozen=True`` turns that into a
``FrozenInstanceError`` at the swap site instead of a silent kill-path miss.
``lasers`` is a ``tuple`` so the sequence itself is immutable.
"""

from dataclasses import dataclass

from lightsheet.hal.interfaces import ICamera, IETLs, ILaser, IMotors, ISigGen


@dataclass(frozen=True)
class DeviceBundle:
    """Immutable bundle of the five HAL device handles.

    Fields:
        camera: the camera HAL instance (real ``Camera`` or ``MockCamera``).
        siggen: the signal-generator HAL instance -- drives
        galvo/ETL AO + camera trigger DO.
        motors: the motors container HAL instance — three Zaber axes.
        etls: the ETLs container HAL instance — two Optotune EL-10-30 lenses.
        lasers: the laser HAL instances as an immutable tuple. The E-stop
            kill path iterates this tuple; mutating it after construction
            is forbidden by the frozen dataclass (safety invariant).
    """

    camera: ICamera
    siggen: ISigGen
    motors: IMotors
    etls: IETLs
    lasers: tuple[ILaser, ...]
