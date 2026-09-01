"""Branch-coverage closure for the three remaining mock HAL modules:
``mock_camera``, ``mock_etls``, ``mock_siggen``.

Exercises the lifecycle idempotency guards, the verbose print branches, the
copy_recorder_images new_data_ready True/False arcs, the MockOptotune
_not_implemented raise + the connect/close/handshake/mode no-op arcs, the
MockETLs set_analog_mode / set_current_mode / get_mode / get_temperature
branches, and MockSigGen's Lightsheet / Global / unsupported-shutter branches
plus the update_* / cfg_* no-op stubs.

Behavior tests (AGENTS.md §5) — every assertion is on a runtime
postcondition (raised NotImplementedError, returned sentinel, set flag),
never a static-source grep.
"""

from __future__ import annotations

import numpy as np
import pytest

from lightsheet.hal.mocks.mock_camera import MockCamera
from lightsheet.hal.mocks.mock_etls import MockETLs, MockOptotune
from lightsheet.hal.mocks.mock_siggen import MockSigGen

# -- MockCamera -------------------------------------------------------------


def test_mock_camera_open_is_idempotent_and_sets_sentinel() -> None:
    """open() is idempotent — the second call hits the `else` branch
    (camera is not None) and does not re-set xsize/ysize."""
    cam = MockCamera(verbose=False)
    assert cam.camera == "mock"
    xsize_before = cam.xsize
    cam.open()
    assert cam.xsize == xsize_before
    assert cam.camera == "mock"


def test_mock_camera_verbose_open_prints(capsys: pytest.CaptureFixture) -> None:  # ty: ignore[missing-type-argument]
    """The verbose=True branch in open() prints the opening messages."""
    MockCamera(verbose=True)
    out = capsys.readouterr().out
    assert "Opening mock camera" in out
    assert "Mock camera opened" in out


def test_mock_camera_close_clears_sentinel_and_verbose_prints(
    capsys: pytest.CaptureFixture,  # ty: ignore[missing-type-argument]
) -> None:
    """close() clears the camera sentinel; the verbose branch prints."""
    cam = MockCamera(verbose=True)
    capsys.readouterr()  # drain open() prints
    assert cam.camera == "mock"
    cam.close()
    assert cam.camera is None
    out = capsys.readouterr().out
    assert "Mock camera closed" in out


def test_mock_camera_close_when_already_closed_is_noop() -> None:
    """The `if self.camera is not None` guard in close() skips the body
    when already closed (the False branch)."""
    cam = MockCamera(verbose=False)
    cam.close()
    # Second close — camera is None, body skipped, no error.
    cam.close()
    assert cam.camera is None


def test_mock_camera_arm_scan_resets_timeout_flag() -> None:
    cam = MockCamera()
    cam.recorder_timeout_status = True
    cam.arm_scan()
    assert cam.recorder_timeout_status is False


def test_mock_camera_recorder_lifecycle_sets_flags() -> None:
    cam = MockCamera()
    cam.start_recorder(5)
    assert cam.is_recording is True
    assert cam.recorder_timeout_status is False
    cam.monitor_recorder(5)
    assert cam.new_data_ready is True
    cam.stop_recorder()
    assert cam.is_recording is False
    cam.delete_recorder()
    assert cam.new_data_ready is False


def test_mock_camera_copy_recorder_images_new_data_ready_arc() -> None:
    """When new_data_ready is True, copy_recorder_images returns the
    synthetic frames and clears the flag (the True branch)."""
    cam = MockCamera()
    cam.new_data_ready = True
    imgs = cam.copy_recorder_images(3)
    assert imgs.shape == (3, cam.ysize, cam.xsize)
    assert cam.new_data_ready is False


def test_mock_camera_copy_recorder_images_no_new_data_arc() -> None:
    """When new_data_ready is False, copy_recorder_images returns
    zero-filled frames without clearing the flag (the False branch —
    mirrors the real Camera's silent-data-loss fallback)."""
    cam = MockCamera()
    cam.new_data_ready = False
    imgs = cam.copy_recorder_images(2)
    assert imgs.shape == (2, cam.ysize, cam.xsize)
    assert cam.new_data_ready is False


def test_mock_camera_grab_image_returns_correct_shape() -> None:
    cam = MockCamera(verbose=False)
    img = cam.grab_image()
    assert img.shape == (cam.ysize, cam.xsize)
    assert img.dtype == np.uint16


def test_mock_camera_grab_image_verbose_prints(
    capsys: pytest.CaptureFixture,  # ty: ignore[missing-type-argument]
) -> None:
    cam = MockCamera(verbose=True)
    capsys.readouterr()
    cam.grab_image()
    assert "Grabbing a synthetic image" in capsys.readouterr().out


def test_mock_camera_temperature_getters_return_20c() -> None:
    cam = MockCamera()
    assert cam.get_camera_temperature() == 20.0
    assert cam.get_sensor_temperature() == 20.0
    assert cam.get_power_temperature() == 20.0


def test_mock_camera_size_and_extended_getters() -> None:
    cam = MockCamera()
    assert cam.get_xsize() == cam.xsize
    assert cam.get_ysize() == cam.ysize
    assert cam.get_name() == "MockCamera"
    # Extended stubs return None.
    assert cam.get_trigger_mode() is None
    assert cam.get_acquire_mode() is None
    assert cam.get_storage_mode() is None
    assert cam.get_recorder_submode() is None
    assert cam.get_exposure_time() is None
    assert cam.get_exposure_timebase() is None
    assert cam.get_delay_time() is None
    assert cam.get_delay_timebase() is None
    assert cam.get_pixel_rate() is None
    assert cam.get_readout_format() is None
    assert cam.get_pixel_rates() == {}


def test_mock_camera_set_exposure_time_converts_ms_to_seconds() -> None:
    cam = MockCamera()
    cam.set_exposure_time(50)
    assert cam.exposure_time == pytest.approx(0.050)


def test_mock_camera_noop_stubs_return_none() -> None:
    """The four no-op stubs on MockCamera are consolidated into one collected
    test. Each method is still called and its return asserted, so the branch
    coverage arc for every stub is preserved (the 70% branch gate backstop)."""
    cam = MockCamera()
    # set_trigger_mode / set_lightsheet_mode are no-op stubs — assert only
    # "did not raise" (their return is unspecified).
    cam.set_trigger_mode("auto_trigger")
    cam.set_lightsheet_mode()
    # cfg_load_ini / cfg_save_ini return None.
    assert cam.cfg_load_ini() is None
    assert cam.cfg_save_ini() is None


def test_mock_camera_get_properties_returns_synthetic_dict() -> None:
    cam = MockCamera()
    props = cam.get_properties()
    assert props["camera name"] == "MockCamera"
    assert props["x"] == cam.xsize
    assert props["y"] == cam.ysize
    assert props["storage mode"] == "Recorder"


# -- MockOptotune / MockETLs ------------------------------------------------


def test_mock_optotune_connect_close_handshake_are_noops() -> None:
    lens = MockOptotune(port="COM5")
    assert lens.connect() is None
    assert lens.close() is None
    assert lens.handshake() == b"Ready\r\n"


def test_mock_optotune_mode_set_returns_mode_str() -> None:
    """mode(mode_str="analog") returns the mode string (the set-case
    branch — used by MockETLs.set_analog_mode)."""
    lens = MockOptotune()
    assert lens.mode("analog") == "analog"
    assert lens.mode("current") == "current"


def test_mock_optotune_mode_get_raises_not_implemented() -> None:
    """mode(mode_str=None) raises NotImplementedError (the get-case
    branch — the CRC protocol cannot be verified on Mac)."""
    lens = MockOptotune()
    with pytest.raises(NotImplementedError):
        lens.mode(None)


@pytest.mark.parametrize(
    "method_name",
    [
        "firmwaretype",
        "firmwarebranch",
        "firmwareversion",
        "deviceid",
        "serialnumber",
        "temp_reading",
        "get_status",
        "eeprom_contents",
        "analog_input",
    ],
)
def test_mock_optotune_unimplemented_methods_raise(method_name: str) -> None:
    """The ~30 CRC-protected serial commands raise NotImplementedError
    (D-06 — cannot verify against real hardware on Mac)."""
    lens = MockOptotune()
    method = getattr(lens, method_name)
    with pytest.raises(NotImplementedError):
        method()


@pytest.mark.parametrize(
    "method_name,args",
    [
        ("partnumber", ()),
        ("current_upper", (None,)),
        ("current_lower", (None,)),
        ("gain", (None,)),
        ("current", (None,)),
        ("siggen_upper", (None,)),
        ("siggen_lower", (None,)),
        ("siggen_freq", (None,)),
        ("temp_limits", (None,)),
        ("focalpower", (None,)),
        ("current_max", (None,)),
        ("eeprom_read", (0,)),
        ("eeprom_write", (0, 0)),
    ],
)
def test_mock_optotune_unimplemented_arg_methods_raise(
    method_name: str, args: tuple  # ty: ignore[missing-type-argument]
) -> None:
    lens = MockOptotune()
    method = getattr(lens, method_name)
    with pytest.raises(NotImplementedError):
        method(*args)


def test_mock_etls_lifecycle_and_analog_mode() -> None:
    etls = MockETLs()
    assert etls.open() is None
    # set_analog_mode calls etl_left.mode("analog") + etl_right.mode("analog")
    # (both not None — the True branch of the guard).
    etls.set_analog_mode()
    assert etls.close() is None


def test_mock_etls_set_current_mode_calls_mode_current() -> None:
    etls = MockETLs()
    etls.set_current_mode()
    # No assertion beyond "did not raise" — mode("current") is a no-op set.


def test_mock_etls_get_mode_and_get_temperature_are_noops() -> None:
    etls = MockETLs()
    assert etls.get_mode() is None
    assert etls.get_temperature() is None


def test_mock_etls_set_analog_mode_with_none_lens_skips_body() -> None:
    """The `if self.etl_left is not None` guard's False branch — when a
    lens is None the mode() call is skipped. Construct then null out the
    lenses to exercise the guard."""
    etls = MockETLs()
    etls.etl_left = None  # ty: ignore[invalid-assignment]
    etls.etl_right = None  # ty: ignore[invalid-assignment]
    # Must not raise — both guards skip the body.
    etls.set_analog_mode()
    etls.set_current_mode()


# -- MockSigGen -------------------------------------------------------------


def _make_siggen(shutter_mode: str = "Rolling") -> MockSigGen:
    """Build a MockSigGen against a MockCamera with the given shutter mode."""
    cam = MockCamera(verbose=False)
    cam.shutter_mode = shutter_mode
    return MockSigGen(cam)


def test_mock_siggen_lifecycle_noops() -> None:
    sg = _make_siggen()
    assert sg.open() is None
    assert sg.close() is None
    assert sg.create_scanner() is None
    assert sg.start_scanner() is None
    assert sg.monitor_scanner() is None
    assert sg.stop_scanner() is None
    assert sg.delete_scanner() is None


def test_mock_siggen_compute_waveforms_lightsheet_branch() -> None:
    """The Lightsheet shutter branch in compute_scan_waveforms derives
    galvo_scan_time from line_time * ysize."""
    sg = _make_siggen(shutter_mode="Lightsheet")
    sg.compute_scan_waveforms()
    assert sg.waveform_cycles == sg.etl_steps
    assert sg.waveform_camera is not None
    assert sg.waveform_galvo_left is not None
    assert sg.waveform_etl_left is not None


def test_mock_siggen_compute_waveforms_global_branch() -> None:
    """The Global shutter branch derives galvo_scan_time from exposure_time."""
    sg = _make_siggen(shutter_mode="Global")
    sg.compute_scan_waveforms()
    assert sg.waveform_cycles == sg.etl_steps
    assert sg.waveform_camera is not None


def test_mock_siggen_compute_waveforms_unsupported_shutter_raises() -> None:
    """The else branch raises Exception for an unsupported shutter mode."""
    sg = _make_siggen(shutter_mode="Bogus")
    with pytest.raises(Exception, match="camera shutter mode not supported"):
        sg.compute_scan_waveforms()


def test_mock_siggen_update_and_cfg_methods_are_noops() -> None:
    sg = _make_siggen()
    assert sg.update_all(1.0, 1.0, 2.5, 2.5) is None
    assert sg.update_galvos(1.0, 1.0) is None
    assert sg.update_etls(2.5, 2.5) is None
    assert sg.cfg_load_ini() is None
    assert sg.cfg_save_ini() is None
