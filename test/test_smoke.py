"""Smoke test: proves the conftest.py hardware-SDK stubs let the HAL modules
import on this Mac (where nidaqmx/pyserial/pco are not installed for real).

If this test passes, every test module's ``from lightsheet.* import ...`` will
also succeed at collection time.
"""

import os

import pytest

_has_hardware: bool = os.environ.get("LIGHTSHEET_HW", "0") == "1"


def test_lasers_imports() -> None:
    from lightsheet.hal import DAQLaser, IBeamSmartLaser, MockLaser

    assert DAQLaser is not None
    assert IBeamSmartLaser is not None
    assert MockLaser is not None


def test_motors_imports() -> None:
    from lightsheet.hal import Motors

    assert Motors is not None


def test_camera_imports() -> None:
    from lightsheet.hal import Camera

    assert Camera is not None


def test_nidaqmx_stub_raises_on_task() -> None:
    """The nidaqmx stub imports fine but Task() raises — mirrors the
    "no driver runtime" behavior the laser tests rely on. Mac-only: on
    the rig the real nidaqmx.Task() succeeds."""
    if _has_hardware:
        pytest.skip("Mac-only stub-raises check — real nidaqmx on the rig")
    import nidaqmx

    with pytest.raises(nidaqmx.errors.Error):
        nidaqmx.Task()


def test_pco_stub_raises_on_camera() -> None:
    """The pco stub imports fine but Camera() raises. Mac-only: on the
    rig the real pco.Camera() succeeds."""
    if _has_hardware:
        pytest.skip("Mac-only stub-raises check — real pco on the rig")
    import pco

    with pytest.raises(RuntimeError):
        pco.Camera()


def test_device_bundle_barrel_reexport_smoke() -> None:
    """``from lightsheet.hal import DeviceBundle`` resolves to the same class
    object as the direct module import — the barrel re-export is wired."""
    from lightsheet.hal import DeviceBundle as barrel_reexport
    from lightsheet.hal.bundle import DeviceBundle as direct

    assert barrel_reexport is direct


def test_dead_calibration_symbols_absent() -> None:
    """The dead Camera/ETL calibration worker stubs, their start buttons,
    their ``*_calibration_started`` flags, and the ``sig_calibrate_*_finished``
    signals have been deleted from ``Controller_MainWindow``.

    This is an import-level ``hasattr`` assertion (AGENTS.md §5 — no
    static-source grep): it proves the symbols are gone from the live class
    object, not just absent from a text scan. ``Controller_MainWindow``
    cannot be instantiated on the Mac (needs PySide6 display), so the check
    runs against the class itself — ``hasattr(cls, name)`` is true for any
    name declared as a class attribute (Signal, method, instance-attr
    initialized in ``__init__`` is NOT visible here, but the deleted
    symbols were either Signal class attrs or method defs, both of
    which ``hasattr`` on the class catches).
    """
    from lightsheet.gui.shell.controller import Controller_MainWindow

    for name in (
        "calibrate_camera_worker",
        "calibrate_etls_worker",
        "camera_calibration_started",
        "etls_calibration_started",
        "sig_calibrate_camera_finished",
        "sig_calibrate_etl_finished",
    ):
        assert not hasattr(Controller_MainWindow, name), (
            f"Controller_MainWindow still exposes dead calibration symbol "
            f"{name!r} — the god-object split's Task 2 deletion was "
            f"incomplete."
        )
