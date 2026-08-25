"""AcquisitionCoordinator extraction tests (god-object split).

``AcquisitionCoordinator`` is a plain-Python collaborator that owns the
three remaining acquisition worker bodies (``live_mode_worker``,
``single_mode_worker``, ``stack_mode_worker``) plus ``acquire_scan``.
``preview_mode_worker`` has relocated to ``PreviewWorker`` in
``lightsheet/gui/workers.py``. The shell delegates through ``self._acq``.
The coordinator reads shell-owned state (``sig_message``, ``estop_event``,
``<mode>_mode_started`` flags, ``_fs``, ``ui.*`` widgets) via an injected
``self._shell`` reference and reads its own ``self.camera`` /
``self.siggen`` / ``self.motors`` / ``self._hw`` attributes.

The real ``AcquisitionCoordinator`` is constructed via
``make_controller`` (which builds the full ``Controller_MainWindow`` with
all collaborators wired and ``hardware_init`` already called). The real
coordinator lives at ``ctrl._acq``. This exercises the real methods on
the real object — the same code that runs on the rig.

Behavior covered (per the plan's ``<behavior>`` block):

1. ``AcquisitionCoordinator(bundle, hw, shell)`` exposes the four
   remaining methods as callable attributes.
2. The golden-master replay (``default.json`` + ``siggen_create_scanner_fail.json``)
   is unchanged after the extraction — verified by the existing replay
   tests in ``test_golden_acquisition.py`` passing without regenerating
   the fixtures.
3. The preview-auto-laser fold: ``PreviewWorker.run`` calls
   ``self._hw.start_lasers()`` after ``camera.arm()`` and
   ``self._hw.stop_lasers()`` before ``camera.disarm()``, mirroring
   ``live_mode_worker``'s shape.
4. ``updateUi_preview_mode_button`` calls
   ``self._cache_auto_laser_flags()`` before spawning the preview worker,
   mirroring ``updateUi_single_mode_button``.
"""

from __future__ import annotations

from unittest.mock import patch

from _helpers.controller_fixture import make_controller


def test_acquisition_coordinator_exposes_four_worker_methods(
    qtbot, request
) -> None:
    """AcquisitionCoordinator(bundle, hw, shell) constructed via
    make_controller exposes single_mode_worker, live_mode_worker,
    stack_mode_worker, acquire_scan as callable methods. preview_mode_worker
    has relocated to PreviewWorker in lightsheet/gui/workers.py."""
    ctrl, _ = make_controller(qtbot, request)
    acq = ctrl._acq

    for name in (
        "single_mode_worker",
        "live_mode_worker",
        "stack_mode_worker",
        "acquire_scan",
    ):
        method = getattr(acq, name, None)
        assert callable(method), (
            f"AcquisitionCoordinator must expose {name} as a callable method "
            f"(got {method!r})"
        )


def test_acquisition_coordinator_stores_bundle_handles_and_collaborators(
    qtbot, request
) -> None:
    """The coordinator stores the bundle's HAL handles as its own
    attributes (self.camera / self.siggen / self.motors) and the hw +
    shell references for delegation."""
    ctrl, bundle = make_controller(qtbot, request)
    acq = ctrl._acq

    assert acq.camera is bundle.camera
    assert acq.siggen is bundle.siggen
    assert acq.motors is bundle.motors
    assert acq._hw is ctrl._hw
    assert acq._shell is ctrl


# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
# Preview-auto-laser fold.
# --------------------------------------------------------------------------- #


def test_preview_worker_calls_start_lasers_after_arm_and_stop_before_disarm(
    qtbot, request
) -> None:
    """PreviewWorker.run now calls self._hw.start_lasers()
    immediately after self.camera.arm() (before the while loop) and
    self._hw.stop_lasers() immediately before self.camera.disarm() —
    mirroring live_mode_worker's existing shape. Verified by calling the
    real PreviewWorker.run (via make_controller) with the camera arm/disarm
    and hw start/stop_lasers methods patched to record the call order, and
    estop_event set so the while loop breaks immediately after
    start_lasers."""
    from lightsheet.gui.workers import PreviewWorker

    ctrl, bundle = make_controller(qtbot, request)

    call_log: list[str] = []
    # Set estop so the while loop breaks immediately after start_lasers —
    # we only need to observe the arm -> start_lasers ordering and the
    # stop_lasers -> disarm ordering in the cleanup tail.
    ctrl.estop_event.set()
    ctrl.preview_mode_started = True

    worker = PreviewWorker(bundle, ctrl._hw, ctrl)

    # Patch the four collaborator methods to record the call order. The
    # real PreviewWorker.run is called — only the collaborator methods are
    # intercepted to observe the ordering.
    with (
        patch.object(worker.camera, "arm", side_effect=lambda: call_log.append("camera.arm")),
        patch.object(
            worker.camera, "disarm", side_effect=lambda: call_log.append("camera.disarm")
        ),
        patch.object(
            ctrl._hw, "start_lasers", side_effect=lambda: call_log.append("hw.start_lasers")
        ),
        patch.object(
            ctrl._hw, "stop_lasers", side_effect=lambda: call_log.append("hw.stop_lasers")
        ),
    ):
        worker.run()

    # start_lasers called after camera.arm.
    assert "camera.arm" in call_log, "camera.arm must be called"
    assert "hw.start_lasers" in call_log, "hw.start_lasers must be called (start_lasers)"
    assert call_log.index("camera.arm") < call_log.index("hw.start_lasers"), (
        "start_lasers: start_lasers must come AFTER camera.arm"
    )
    # stop_lasers called before camera.disarm.
    assert "hw.stop_lasers" in call_log, "hw.stop_lasers must be called (start_lasers)"
    assert "camera.disarm" in call_log, "camera.disarm must be called"
    assert call_log.index("hw.stop_lasers") < call_log.index("camera.disarm"), (
        "start_lasers: stop_lasers must come BEFORE camera.disarm"
    )


def test_updateUi_preview_mode_button_caches_auto_laser_flags_before_thread_spawn(
    qtbot, request
) -> None:
    """updateUi_preview_mode_button: updateUi_preview_mode_button must call
    self._cache_auto_laser_flags() before spawning the preview worker
    QThread, mirroring updateUi_single_mode_button. Verified by calling the
    real updateUi_preview_mode_button on the real controller (via
    make_controller) with _cache_auto_laser_flags patched to record the
    call and QThread.start patched so no real thread is started,
    asserting the cache call happens before the thread spawn."""
    from PyQt5.QtCore import QThread

    ctrl, _ = make_controller(qtbot, request)

    call_log: list[str] = []
    ctrl.preview_mode_started = False  # the else: branch (start path)

    # _cache_auto_laser_flags records the call.
    with (
        patch.object(
            ctrl,
            "_cache_auto_laser_flags",
            side_effect=lambda: call_log.append("_cache_auto_laser_flags"),
        ),
        patch.object(ctrl, "close_modes", side_effect=lambda: call_log.append("close_modes")),
        # Patch QThread.start so no real thread is started. The real QThread
        # is constructed, the worker is moveToThread'd, and the signal
        # connections are wired — only start() is intercepted to record the
        # spawn timing without launching a worker thread.
        patch.object(QThread, "start", side_effect=lambda: call_log.append("thread_spawn")),
    ):
        ctrl.updateUi_preview_mode_button()

    assert "_cache_auto_laser_flags" in call_log, (
        "updateUi_preview_mode_button: updateUi_preview_mode_button must call "
        "_cache_auto_laser_flags before spawning the preview thread"
    )
    assert "thread_spawn" in call_log, "the preview thread must be spawned"
    assert call_log.index("_cache_auto_laser_flags") < call_log.index("thread_spawn"), (
        "cache-flags: _cache_auto_laser_flags must be called BEFORE the thread spawn"
    )
