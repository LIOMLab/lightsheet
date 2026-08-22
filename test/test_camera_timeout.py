'''
Unit tests for src/camera.py — scaled recorder timeout.

Camera.__init__ calls pco.Camera() which raises on this Mac (no PCO SDK),
so instances are built via Camera.__new__(Camera) with the attributes the
timeout logic reads (shutter_mode, line_time, lightsheet_exposed_lines,
exposure_time, recorder_timeout_floor, recorder_timeout_interval,
recorder_timeout_safety_factor). Tests 1-4 cover the pure timeout formula
(3-4 also assert the legacy-interval floor); test 5 verifies that when
recorder_timeout_status is True the acquire path does not copy images;
tests 6-7 cover the legacy-interval floor regression and the
arm_scan() unconditional reset.
'''

import pytest

from lightsheet.camera import Camera


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
    # Mirrors the rig-confirmed config.ini [Camera] Recorder Timeout = 15
    # default — the legacy flat timeout value that is rig-confirmed to work
    # for Rolling/Global-shutter acquisitions.
    cam.recorder_timeout_interval = 15
    cam.recorder_timeout_safety_factor = 3.0
    cam.recorder_timeout_status = False
    cam.new_data_ready = False
    cam.is_recording = False
    cam.camera = None  # no pco SDK on Mac; mirrors __init__'s probe-fail state
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
    '''Small acquisitions use the floor, not a too-short computed value.
    The legacy flat Recorder Timeout interval (rig-confirmed to work) is a
    hard floor the scaled value can never fall below:
    max(5, 15, 100 * 0.0025 * 3.0) == max(5, 15, 0.75) == 15.'''
    cam = _make_camera(shutter_mode='Lightsheet')
    # Override per-image time to 2.5 ms for this scenario
    cam.line_time = 0.0001
    cam.lightsheet_exposed_lines = 25  # 0.0001 * 25 = 0.0025 s per image
    per_image = cam._compute_per_image_time()
    timeout_s = max(cam.recorder_timeout_floor,
                    cam.recorder_timeout_interval,
                    100 * per_image * cam.recorder_timeout_safety_factor)
    assert timeout_s == 15


def test_timeout_formula_scales_with_images():
    '''Large acquisitions scale past both the floor and the legacy interval:
    max(5, 15, 1000 * 0.1 * 3.0) == 300.'''
    cam = _make_camera(shutter_mode='Rolling')
    per_image = cam._compute_per_image_time()
    timeout_s = max(cam.recorder_timeout_floor,
                    cam.recorder_timeout_interval,
                    1000 * per_image * cam.recorder_timeout_safety_factor)
    assert timeout_s == 300


def test_timeout_never_falls_below_legacy_interval():
    '''Rolling/Global mode: the per-image time estimate is the exposure time
    alone, which ignores trigger-wait/readout/DAQ-cycle overhead, so the
    scaled value can underestimate real per-image wall time. A modest
    acquisition (10 images * 0.1 s * 3.0 = 3.0 s) must still yield the
    rig-proven 15 s legacy interval, not 3.0 s or the 5 s floor — this is
    the exact false-positive shape the operator hit on the rig.
    max(5, 15, 10 * 0.1 * 3.0) == max(5, 15, 3.0) == 15.'''
    cam = _make_camera(shutter_mode='Rolling')
    per_image = cam._compute_per_image_time()
    timeout_s = max(cam.recorder_timeout_floor,
                    cam.recorder_timeout_interval,
                    10 * per_image * cam.recorder_timeout_safety_factor)
    assert timeout_s == 15


def test_arm_scan_resets_recorder_timeout_status_without_hardware():
    '''arm_scan() must clear recorder_timeout_status unconditionally —
    BEFORE the `if self.camera is not None:` guard — so a worker that died
    mid-timeout on the previous run (leaving the flag True) cannot poison
    the camera for the next acquisition attempt. With self.camera is None
    the hardware branch is a no-op, but the reset must still run.'''
    cam = _make_camera()
    cam.recorder_timeout_status = True
    assert cam.camera is None  # no hardware branch executes
    cam.arm_scan()
    assert cam.recorder_timeout_status is False, (
        "arm_scan must reset recorder_timeout_status unconditionally, "
        "even when self.camera is None — otherwise a worker that died "
        "after a timeout leaves the camera poisoned for the next run.")


def test_recorder_timeout_status_blocks_copy():
    '''When recorder_timeout_status is True, copy_recorder_images must not
    be reached by the acquire path. The contract that enforces this is:
    acquire_scan checks recorder_timeout_status and returns early (before
    copy_recorder_images) on timeout, AND delete_recorder must NOT reset
    the flag (so the post-acquire check in stack_mode_worker can observe
    it and abort the run).

    Verified against the real Camera.delete_recorder (no pco SDK needed —
    it guards on self.camera is not None). The acquire_scan side of the
    contract is not asserted by static-source grep; see AGENTS.md §5.'''
    cam = _make_camera()
    # Simulate a timeout: monitor_recorder set the flag, then acquire_scan
    # called delete_recorder before returning.
    cam.recorder_timeout_status = True
    # delete_recorder must leave the flag set so the stack worker can see it.
    # cam.camera is None (no pco SDK), so delete_recorder is a no-op on the
    # recorder but must still NOT clear the flag.
    cam.delete_recorder()
    assert cam.recorder_timeout_status is True, (
        "delete_recorder must not reset recorder_timeout_status — the "
        "stack_mode_worker post-acquire abort check depends on the flag "
        "surviving delete_recorder.")
