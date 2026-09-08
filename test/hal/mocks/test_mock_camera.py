"""Behavior tests for ``MockCamera.simulate_timing`` (demo-mode
observability) and the ``_build_demo_bundle`` wiring.

``simulate_timing`` defaults to ``False`` so the test suite (which
constructs ``MockCamera(verbose=False)`` without setting the flag) is
unaffected. When ``True``, ``monitor_recorder`` sleeps for
``self.exposure_time`` before setting ``new_data_ready`` — making the
L1->L2 per-plane/per-frame sequencing observable in the ``--demo`` GUI
launch. The delay is demo-only: ``MockCamera`` is never used on the
real rig.

``_build_demo_bundle`` in ``lightsheet/__main__.py`` is the ONLY place
``simulate_timing`` is set to ``True`` — the test helper
``make_bundle`` in ``test/helpers/factories.py`` does NOT set
it, keeping tests fast.

The module also covers the ``frame_source`` hook: when set to
``callable(camera, plane_index) -> np.ndarray``, ``copy_recorder_images``
delegates full-frame generation to it — converting the returned float
density to uint16 via ``np.clip(raw * 65535, 0, 65535)`` and
broadcasting to the ``(N, ysize, xsize)`` buffer. ``frame_source``
takes precedence over ``scripted_intensity_fn``, still respects the
``new_data_ready`` silent-data-loss gate, and is attached only by
``_build_demo_bundle`` (``make_bundle`` keeps ``frame_source is None``).
"""

from __future__ import annotations

import time
from typing import cast

import numpy as np
import pytest

pytest.importorskip("PySide6")


def test_monitor_recorder_no_delay_by_default() -> None:
    """MockCamera with simulate_timing=False (the default) returns
    immediately from monitor_recorder — no sleep, no test-suite
    slowdown. Verifiable by measuring elapsed time < 10ms."""
    from lightsheet.hal.mocks.mock_camera import MockCamera

    camera = MockCamera(verbose=False)
    assert camera.simulate_timing is False, (
        "simulate_timing must default to False so the test suite is not slowed"
    )
    # Use a non-trivial exposure_time so a stray sleep would be
    # detectable; the default is 100ms which would blow the 10ms
    # budget if the flag were ignored.
    camera.exposure_time = 0.1

    start = time.perf_counter()
    camera.monitor_recorder(number_of_images=1)
    elapsed = time.perf_counter() - start

    assert elapsed < 0.01, (
        f"monitor_recorder must not sleep when simulate_timing=False; "
        f"elapsed {elapsed * 1000:.1f}ms (budget 10ms)"
    )
    assert camera.new_data_ready is True


def test_monitor_recorder_delays_when_simulate_timing_true() -> None:
    """MockCamera with simulate_timing=True and exposure_time=0.05
    (50ms) sleeps for ~50ms in monitor_recorder before setting
    new_data_ready — making the L1->L2 per-plane sequencing observable
    in demo mode. Verifiable by measuring elapsed time >= 45ms."""
    from lightsheet.hal.mocks.mock_camera import MockCamera

    camera = MockCamera(verbose=False)
    camera.simulate_timing = True
    camera.exposure_time = 0.05  # 50ms — small but measurable

    start = time.perf_counter()
    camera.monitor_recorder(number_of_images=1)
    elapsed = time.perf_counter() - start

    assert elapsed >= 0.045, (
        f"monitor_recorder must sleep ~exposure_time when "
        f"simulate_timing=True; elapsed {elapsed * 1000:.1f}ms "
        f"(expected >= 45ms)"
    )
    assert camera.new_data_ready is True


def test_build_demo_bundle_sets_simulate_timing_true() -> None:
    """``_build_demo_bundle`` in ``lightsheet/__main__.py`` constructs a
    ``MockCamera`` with ``simulate_timing=True`` so the ``--demo`` GUI
    launch shows observable acquisition timing (the L1->L2 per-plane
    cycle at a realistic pace). This is the ONLY place the flag is set
    to True."""
    from lightsheet.__main__ import _build_demo_bundle

    bundle = _build_demo_bundle()
    camera = bundle.camera
    assert getattr(camera, "simulate_timing", None) is True, (
        "_build_demo_bundle must set camera.simulate_timing=True so "
        "the --demo GUI launch shows observable acquisition timing"
    )


def test_make_bundle_does_not_set_simulate_timing() -> None:
    """The test helper ``make_bundle`` in
    ``test/helpers/factories.py`` constructs
    ``MockCamera(verbose=False)`` with ``simulate_timing=False`` (the
    default) — tests are not slowed by the demo-only timing delay."""
    from test.helpers.factories import make_bundle

    bundle = make_bundle()
    camera = bundle.camera
    assert camera.simulate_timing is False, (  # ty: ignore[unresolved-attribute]
        "make_bundle must NOT set simulate_timing — the test suite "
        "must not be slowed by the demo-only timing delay"
    )


def test_copy_recorder_images_returns_intentional_array_when_ready() -> None:
    """MockCamera continues returning deliberate synthetic image arrays when
    data is ready and clears new_data_ready, preserving the mock's explicit
    synthetic path."""
    from lightsheet.hal.mocks.mock_camera import MockCamera

    camera = MockCamera(verbose=False)
    camera.new_data_ready = True
    result = camera.copy_recorder_images(1)
    assert isinstance(result, np.ndarray)
    assert result.shape == (1, camera.ysize, camera.xsize)
    assert result.dtype == np.uint16
    assert camera.new_data_ready is False


# -- frame_source hook contract -------------------------------------------


def test_frame_source_takes_precedence_over_scripted_intensity() -> None:
    """With both hooks set and new_data_ready True, the frame_source
    branch runs and the returned frames carry the frame_source content
    (uint16-converted), not the scripted scalar fill."""
    from lightsheet.hal.mocks.mock_camera import MockCamera

    camera = MockCamera(verbose=False)
    camera.set_scripted_intensity_fn(lambda _i, _e: 40000)
    assert camera.ysize is not None and camera.xsize is not None
    source = np.full((camera.ysize, camera.xsize), 0.5)
    camera.set_frame_source(lambda _cam, _i: source)
    camera.new_data_ready = True

    result = camera.copy_recorder_images(1)

    expected = np.clip(source * 65535.0, 0, 65535).astype(np.uint16)
    assert np.array_equal(result[0], expected)
    assert not np.all(result == 40000)


def test_frame_source_floats_convert_to_uint16() -> None:
    """A frame_source returning floats in [0, 1] produces uint16 via
    np.clip(raw * 65535, 0, 65535) — 0.5 lands at ~32767 and values
    above 1.0 clip to 65535 rather than wrapping."""
    from lightsheet.hal.mocks.mock_camera import MockCamera

    camera = MockCamera(verbose=False)
    assert camera.ysize is not None and camera.xsize is not None
    shape = (camera.ysize, camera.xsize)
    camera.set_frame_source(lambda _cam, _i: np.full(shape, 0.5))
    camera.new_data_ready = True
    half = camera.copy_recorder_images(1)
    assert half.dtype == np.uint16
    assert np.all(half == int(np.clip(0.5 * 65535.0, 0, 65535)))

    camera.set_frame_source(lambda _cam, _i: np.full(shape, 2.0))
    camera.new_data_ready = True
    over = camera.copy_recorder_images(1)
    assert np.all(over == 65535)


def test_frame_source_none_preserves_fallback_order() -> None:
    """frame_source=None falls back to scripted_intensity_fn, then to
    zero-fill — the pre-existing precedence is unchanged."""
    from lightsheet.hal.mocks.mock_camera import MockCamera

    camera = MockCamera(verbose=False)
    assert camera.frame_source is None

    camera.set_scripted_intensity_fn(lambda _i, _e: 12345)
    camera.new_data_ready = True
    scripted = camera.copy_recorder_images(1)
    assert np.all(scripted == 12345)

    camera.set_scripted_intensity_fn(None)
    camera.new_data_ready = True
    zero = camera.copy_recorder_images(1)
    assert np.all(zero == 0)


def test_frame_source_respects_new_data_ready_gate() -> None:
    """With new_data_ready False, copy_recorder_images returns zeros even
    when frame_source is set — the hook must not bypass the
    silent-data-loss guard."""
    from lightsheet.hal.mocks.mock_camera import MockCamera

    calls: list[int] = []

    def source(_cam: object, index: int) -> np.ndarray:
        calls.append(index)
        return np.ones((2048, 2048))

    camera = MockCamera(verbose=False)
    camera.set_frame_source(source)
    camera.new_data_ready = False

    result = camera.copy_recorder_images(1)

    assert np.all(result == 0)
    assert calls == [], "frame_source must not run when new_data_ready is False"


def test_frame_source_broadcasts_to_n_images() -> None:
    """copy_recorder_images(3) with frame_source returns (3, ysize,
    xsize) with all three images identical to the converted source."""
    from lightsheet.hal.mocks.mock_camera import MockCamera

    camera = MockCamera(verbose=False)
    assert camera.ysize is not None and camera.xsize is not None
    source = np.full((camera.ysize, camera.xsize), 0.25)
    camera.set_frame_source(lambda _cam, _i: source)
    camera.new_data_ready = True

    result = camera.copy_recorder_images(3)

    assert result.shape == (3, camera.ysize, camera.xsize)
    expected = np.clip(source * 65535.0, 0, 65535).astype(np.uint16)
    for i in range(3):
        assert np.array_equal(result[i], expected)


def test_frame_source_index_progression_and_reset() -> None:
    """scripted_frame_index increments by exactly 1 per
    copy_recorder_images call, the callback sees the pre-increment
    index, and set_frame_source resets the index to 0."""
    from lightsheet.hal.mocks.mock_camera import MockCamera

    camera = MockCamera(verbose=False)
    assert camera.ysize is not None and camera.xsize is not None
    shape = (camera.ysize, camera.xsize)
    seen: list[int] = []
    camera.set_frame_source(lambda _cam, i: seen.append(i) or np.zeros(shape))
    assert camera.scripted_frame_index == 0

    camera.new_data_ready = True
    camera.copy_recorder_images(1)
    assert seen == [0]
    assert camera.scripted_frame_index == 1

    camera.new_data_ready = True
    camera.copy_recorder_images(1)
    assert seen == [0, 1]
    assert camera.scripted_frame_index == 2

    camera.set_frame_source(lambda _cam, _i: np.zeros(shape))
    assert camera.scripted_frame_index == 0


def test_build_demo_bundle_attaches_frame_source() -> None:
    """_build_demo_bundle wires a callable frame_source onto the demo
    MockCamera, and an end-to-end mock acquisition (horizontal at the
    light sheet, laser on at max power, data ready) yields a non-zero
    uint16 frame."""
    from lightsheet.__main__ import _build_demo_bundle
    from lightsheet.hal.mocks.mock_camera import MockCamera

    bundle = _build_demo_bundle()
    camera = cast(MockCamera, bundle.camera)
    assert camera.frame_source is not None
    assert callable(camera.frame_source)

    bundle.motors.horizontal.move_absolute_position(8500.0, "µm")
    bundle.lasers[0].set_power(bundle.lasers[0].max_power)
    bundle.lasers[0].on()
    camera.new_data_ready = True
    imgs = camera.copy_recorder_images(1)

    assert imgs.shape == (1, camera.ysize, camera.xsize)
    assert imgs.dtype == np.uint16
    assert float(np.percentile(imgs[0], 99)) > 0


def test_make_bundle_does_not_attach_frame_source() -> None:
    """make_bundle keeps frame_source=None so existing tests retain the
    zero-fill/scalar-hook default path."""
    from test.helpers.factories import make_bundle

    bundle = make_bundle()
    assert bundle.camera.frame_source is None  # ty: ignore[unresolved-attribute]


# -- set_lightsheet_mode applied-timing contract -------------------------


def test_set_lightsheet_mode_applies_line_time_and_effective_exposure() -> None:
    """With ``lightsheet_line_time = 0.005`` s and
    ``lightsheet_exposed_lines = 16``, ``set_lightsheet_mode`` leaves
    ``line_time == 0.005`` and sets the mock's effective
    ``exposure_time == line_time * exposed_lines`` (0.08 s) so the
    scripted-intensity / frame_source paths respond to Lightsheet
    exposure changes."""
    from lightsheet.hal.mocks.mock_camera import MockCamera

    camera = MockCamera(verbose=False)
    camera.lightsheet_line_time = 0.005
    camera.lightsheet_exposed_lines = 16

    assert camera.set_lightsheet_mode() is None
    assert camera.line_time == pytest.approx(0.005)
    assert camera.exposure_time == pytest.approx(0.005 * 16)


def test_set_lightsheet_mode_effective_exposure_tracks_line_time() -> None:
    """A second ``set_lightsheet_mode`` call after changing the requested
    line time re-derives the effective exposure from the new applied
    value — the mock has no stale-exposure path."""
    from lightsheet.hal.mocks.mock_camera import MockCamera

    camera = MockCamera(verbose=False)
    camera.lightsheet_exposed_lines = 16

    camera.lightsheet_line_time = 0.001
    camera.set_lightsheet_mode()
    assert camera.exposure_time == pytest.approx(0.016)

    camera.lightsheet_line_time = 0.002
    camera.set_lightsheet_mode()
    assert camera.line_time == pytest.approx(0.002)
    assert camera.exposure_time == pytest.approx(0.032)


def test_set_lightsheet_mode_rejects_non_positive_exposed_lines() -> None:
    """A non-positive ``lightsheet_exposed_lines`` would silently produce a
    zero or negative effective exposure — the mock must fail loudly."""
    from lightsheet.hal.mocks.mock_camera import MockCamera

    camera = MockCamera(verbose=False)
    camera.lightsheet_exposed_lines = 0
    with pytest.raises(ValueError, match="lightsheet_exposed_lines"):
        camera.set_lightsheet_mode()

    camera.lightsheet_exposed_lines = -4
    with pytest.raises(ValueError, match="lightsheet_exposed_lines"):
        camera.set_lightsheet_mode()


def test_set_lightsheet_mode_rejects_invalid_line_time() -> None:
    """A None / non-positive / non-finite ``lightsheet_line_time`` must
    raise ValueError, never a TypeError mid-worker on the exposure
    multiply."""
    from lightsheet.hal.mocks.mock_camera import MockCamera

    camera = MockCamera(verbose=False)
    for bad in (None, 0.0, -1e-5, float("inf"), float("nan"), "x"):
        camera.lightsheet_line_time = bad  # type: ignore[assignment]  # ty: ignore[invalid-assignment]
        with pytest.raises(ValueError, match="lightsheet_line_time"):
            camera.set_lightsheet_mode()
