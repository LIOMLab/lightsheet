"""Unit tests for ``Camera.set_lightsheet_mode`` SDK write/readback sync.

``Camera.__init__`` calls ``pco.Camera()`` which raises on a dev machine
without the PCO SDK, so instances are built via ``Camera.__new__`` with a
fake ``.camera.sdk`` — the same hardware-probe bypass used by
``test_camera_timeout.py``. No real hardware SDK constructor or
power/motion operation runs.
"""

from unittest.mock import Mock, call

import pytest

from lightsheet.hal import Camera


def _make_camera() -> Camera:
    """Build a Camera-like instance without running __init__'s pco.Camera()
    hardware probe (fails on Mac without the PCO SDK)."""
    cam = Camera.__new__(Camera)
    cam.verbose = False
    cam.shutter_mode = "Lightsheet"
    cam.exposure_time = 0.1  # 100 ms (stored in seconds)
    cam.lightsheet_line_time = 0.005  # requested 5 ms per line (seconds)
    cam.lightsheet_exposed_lines = 16
    cam.lightsheet_delay_lines = 2
    cam.line_time = 0.003  # stale applied value the readback must overwrite
    cam.camera = Mock()
    return cam


def test_set_lightsheet_mode_call_order_and_readback_sync() -> None:
    """set_lightsheet_mode pushes the requested line time first, then the
    exposed/delay lines, then reads the applied timing back. Both
    ``line_time`` and ``lightsheet_line_time`` take the SDK-readback
    (possibly quantized) value so waveform computation and applied-state
    publication use the applied truth."""
    cam = _make_camera()
    sdk = cam.camera.sdk
    sdk.get_cmos_line_timing.return_value = {"line time": 0.0049}
    sdk.get_cmos_line_exposure_delay.return_value = {
        "lines exposure": 16,
        "lines delay": 2,
    }

    result = cam.set_lightsheet_mode()

    assert result is None
    assert sdk.mock_calls == [
        call.set_cmos_line_timing("on", 0.005),
        call.set_cmos_line_exposure_delay(16, 2),
        call.get_cmos_line_timing(),
        call.get_cmos_line_exposure_delay(),
    ]
    assert cam.line_time == pytest.approx(0.0049)
    assert cam.lightsheet_line_time == pytest.approx(0.0049)
    # The Rolling/Global exposure register is a separate contract — the
    # Lightsheet branch must not write it.
    assert cam.exposure_time == pytest.approx(0.1)


def test_set_lightsheet_mode_missing_readback_leaves_attrs() -> None:
    """When the SDK readback carries no 'line time' key, the previously
    applied timing attributes are left untouched (the request value stays
    the best-known intent)."""
    cam = _make_camera()
    sdk = cam.camera.sdk
    sdk.get_cmos_line_timing.return_value = {"parameter": "on"}
    sdk.get_cmos_line_exposure_delay.return_value = {
        "lines exposure": 16,
        "lines delay": 2,
    }

    assert cam.set_lightsheet_mode() is None
    assert cam.line_time == pytest.approx(0.003)
    assert cam.lightsheet_line_time == pytest.approx(0.005)


def test_set_lightsheet_mode_without_hardware_is_noop() -> None:
    """With ``camera is None`` (no PCO SDK present) the method is a no-op
    and returns None — no SDK call is attempted."""
    cam = _make_camera()
    cam.camera = None

    assert cam.set_lightsheet_mode() is None
    assert cam.line_time == pytest.approx(0.003)
    assert cam.lightsheet_line_time == pytest.approx(0.005)
