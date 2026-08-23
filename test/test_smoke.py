"""Smoke test: proves the conftest.py hardware-SDK stubs let the HAL modules
import on this Mac (where nidaqmx/pyserial/pco are not installed for real).

If this test passes, every test module's ``from lightsheet.* import ...`` will
also succeed at collection time.
"""


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
    "no driver runtime" behavior the laser tests rely on."""
    import nidaqmx
    import pytest

    with pytest.raises(nidaqmx.errors.Error):
        nidaqmx.Task()


def test_pco_stub_raises_on_camera() -> None:
    """The pco stub imports fine but Camera() raises."""
    import pco
    import pytest

    with pytest.raises(RuntimeError):
        pco.Camera()
