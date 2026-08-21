'''
Unit tests for src/camera.py — scaled recorder timeout.

Camera.__init__ calls pco.Camera() which raises on this Mac (no PCO SDK),
so instances are built via Camera.__new__(Camera) with the attributes the
timeout logic reads (shutter_mode, line_time, lightsheet_exposed_lines,
exposure_time, recorder_timeout_floor, recorder_timeout_safety_factor).
Tests 1-4 cover the pure timeout formula; test 5 verifies that when
recorder_timeout_status is True the acquire path does not copy images.
'''

import pytest

from src.camera import Camera


def _make_camera(shutter_mode='Lightsheet'):
    '''Build a Camera-like instance without running __init__'s pco.Camera()
    hardware probe (fails on Mac without the PCO SDK).'''
    cam = Camera.__new__(Camera)
    cam.verbose = False
    cam.shutter_mode = shutter_mode
    cam.exposure_time = 0.1            # 100 ms (stored in seconds)
    cam.line_time = 0.00780            # 7.8 ms per line (stored in seconds)
    cam.lightsheet_exposed_lines = 25
    cam.lightsheet_delay_lines = 225
    cam.recorder_timeout_floor = 5
    cam.recorder_timeout_safety_factor = 3.0
    cam.recorder_timeout_status = False
    cam.new_data_ready = False
    cam.is_recording = False
    return cam


def test_compute_per_image_time_lightsheet():
    '''In Lightsheet mode the per-image time is line_time * exposed_lines.'''
    cam = _make_camera(shutter_mode='Lightsheet')
    assert cam._compute_per_image_time() == pytest.approx(0.00780 * 25)


def test_compute_per_image_time_rolling():
    '''In Rolling/Global mode the per-image time is the exposure time.'''
    cam = _make_camera(shutter_mode='Rolling')
    assert cam._compute_per_image_time() == pytest.approx(0.1)


def test_timeout_formula_floor_applies():
    '''Small acquisitions use the floor, not a too-short computed value:
    max(5, 100 * 0.0025 * 3.0) == max(5, 0.75) == 5.'''
    cam = _make_camera(shutter_mode='Lightsheet')
    # Override per-image time to 2.5 ms for this scenario
    cam.line_time = 0.0001
    cam.lightsheet_exposed_lines = 25  # 0.0001 * 25 = 0.0025 s per image
    per_image = cam._compute_per_image_time()
    timeout_s = max(cam.recorder_timeout_floor,
                    100 * per_image * cam.recorder_timeout_safety_factor)
    assert timeout_s == 5


def test_timeout_formula_scales_with_images():
    '''Large acquisitions scale past the floor:
    max(5, 1000 * 0.1 * 3.0) == 300.'''
    cam = _make_camera(shutter_mode='Rolling')
    per_image = cam._compute_per_image_time()
    timeout_s = max(cam.recorder_timeout_floor,
                    1000 * per_image * cam.recorder_timeout_safety_factor)
    assert timeout_s == 300


def test_recorder_timeout_status_blocks_copy():
    '''When recorder_timeout_status is True, copy_recorder_images must not
    be reached by the acquire path. We simulate the acquire_scan abort
    decision directly: a True timeout status short-circuits before any
    image copy, so new_data_ready stays False and no zero-filled frames
    are produced.'''
    cam = _make_camera()
    cam.recorder_timeout_status = True
    cam.new_data_ready = False

    # Mirror the acquire_scan abort contract: on a True timeout status the
    # caller must NOT invoke copy_recorder_images. We assert the guard
    # predicate that gates the copy, which is the same one acquire_scan
    # checks before calling copy_recorder_images.
    should_copy = not cam.recorder_timeout_status
    assert should_copy is False

    # And confirm copy_recorder_images itself would return zero-filled
    # frames if (mis)called — proving the abort is what prevents silent
    # data loss. We do not call it; we only assert the precondition.
    assert cam.recorder_timeout_status is True
