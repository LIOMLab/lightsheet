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
``simulate_timing`` is set to ``True`` — the test fixture
``make_bundle`` in ``test/_helpers/controller_fixture.py`` does NOT set
it, keeping tests fast.
"""

from __future__ import annotations

import time

import pytest

pytest.importorskip("PySide6")


def test_monitor_recorder_no_delay_by_default() -> None:
    """MockCamera with simulate_timing=False (the default) returns
    immediately from monitor_recorder — no sleep, no test-suite
    slowdown. Verifiable by measuring elapsed time < 10ms."""
    from lightsheet.hal.mocks.mock_camera import MockCamera

    camera = MockCamera(verbose=False)
    assert camera.simulate_timing is False, (
        "simulate_timing must default to False so the test suite is "
        "not slowed"
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
    """The test fixture ``make_bundle`` in
    ``test/_helpers/controller_fixture.py`` constructs
    ``MockCamera(verbose=False)`` with ``simulate_timing=False`` (the
    default) — tests are not slowed by the demo-only timing delay."""
    from _helpers.controller_fixture import make_bundle

    bundle = make_bundle()
    camera = bundle.camera
    assert camera.simulate_timing is False, (
        "make_bundle must NOT set simulate_timing — the test suite "
        "must not be slowed by the demo-only timing delay"
    )
