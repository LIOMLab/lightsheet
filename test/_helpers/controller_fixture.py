"""Shared real-construction fixture for ``Controller_MainWindow`` and its
collaborators (AGENTS.md §5).

``Controller_MainWindow`` IS constructable on Mac: ``uv run lightsheet
--demo`` does exactly that via ``_build_demo_bundle()`` in
``lightsheet/__main__.py``. ``QT_QPA_PLATFORM=offscreen`` + the conftest
SDK stubs + the offscreen Qt platform make real
construction work on the Mac dev box. Real construction produces genuine
branch (arc) coverage and exercises the real signal/slot wiring, Qt
widget state, and collaborator interactions — the foundation the test
suite builds on.
This module mirrors the composition root in ``lightsheet/__main__.main()``:
build a mock ``DeviceBundle``, construct ``Controller_MainWindow`` with
``demo=True``, then wire the four collaborators
(``FrameSaverController`` / ``HardwareManager`` / ``AcquisitionCoordinator``
/ ``MotorController``) in the same two-phase order ``main()`` uses.

Usage in a test file::

    from _helpers.controller_fixture import make_controller

    def test_thing(qtbot):
        ctrl, bundle = make_controller(qtbot)
        ctrl.updateUi_light_theme()
        ...

``qtbot`` is the pytest-qt fixture; it provides the ``QApplication`` and
ensures widgets are cleaned up safely between tests (no ViewBox GC
segfault, no leaked ``QApplication``). Tests that need the bare
collaborators without the shell can call ``make_bundle()`` directly.
"""

from __future__ import annotations

import contextlib
from typing import Any

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from lightsheet.hal import (
    DeviceBundle,
    MockCamera,
    MockETLs,
    MockLaser,
    MockMotors,
    MockSigGen,
)


def _quit_thread_draining(thread: Any | None, timeout_ms: int = 2000) -> None:
    """Quit a worker ``QThread`` and pump the event loop until it stops.

    Unlike ``QThread.wait()`` (which blocks the calling thread without
    processing events), this polls ``isRunning()`` while flushing the
    ``QApplication`` event queue at each tick. That lets a queued
    ``quit()`` reach the thread's event loop and the thread reap
    deterministically — the blocking ``wait()`` form stalls the main
    event loop and, under xdist with many controllers per worker,
    stacks into an apparent hang when ``quit()`` races ahead of the
    thread's ``exec()`` (quit-before-exec is a no-op, the thread then
    runs unattended and the blocking wait never observes it stop).

    A thread that already self-quit (``isRunning()`` is False on entry)
    is a no-op. The poll is capped at ``timeout_ms`` so a genuinely
    stuck worker cannot hang teardown — matching the prior ``wait(2000)``
    bound.
    """
    if thread is None or not thread.isRunning():
        return
    thread.quit()
    app = QApplication.instance()
    deadline = timeout_ms
    step_ms = 20
    while thread.isRunning() and deadline > 0:
        if app is not None:
            app.processEvents()
        thread.wait(step_ms)
        deadline -= step_ms


def make_bundle() -> DeviceBundle:
    """Build a mock ``DeviceBundle`` mirroring ``_build_demo_bundle()`` in
    ``lightsheet/__main__.py`` (Laser 1 = 555 nm / 300 mW, Laser 2 = 647 nm
    / 150 mW, mock camera/siggen/motors/etls). The camera-before-siggen
    dependency ordering is preserved."""
    camera = MockCamera(verbose=False)
    siggen = MockSigGen(camera)
    motors = MockMotors()
    lasers = (
        MockLaser(
            wavelength=555,
            max_power_mw=300.0,
            mw_per_volt=60.0,
            label="Laser 1 (555 nm)",
            calibration_curve=None,
        ),
        MockLaser(
            wavelength=647,
            max_power_mw=150.0,
            label="Laser 2 (647 nm)",
        ),
    )
    etls = MockETLs()
    return DeviceBundle(
        camera=camera,
        siggen=siggen,
        motors=motors,
        etls=etls,
        lasers=lasers,
    )


def make_controller(qtbot: Any, request: Any) -> tuple[Any, DeviceBundle]:
    """Construct the real ``Controller_MainWindow`` with all four
    collaborators wired, mirroring ``lightsheet/__main__.main()``'s
    composition root. Returns ``(controller, bundle)``.

    ``qtbot`` is the pytest-qt fixture; it owns the ``QApplication`` and
    handles widget cleanup. ``request`` is the pytest ``request`` fixture;
    its ``addfinalizer`` is used to stop the QMessageBox patch + the
    hardware_init timers at teardown (pytest-qt's QtBot has no finalizer
    API of its own). The controller is registered with qtbot so it is
    cleaned up at test teardown (``qtbot.addWidget``).

    The two-phase init matches ``main()``: shell first (with fs/hw/acq/mc
    = None), then each collaborator constructed against the shell and
    assigned onto it. This preserves the parent/child QObject
    relationships and the shell→collaborator delegation the production
    code relies on.

    ``hardware_init`` is called after the collaborators are wired (it
    reads ``self._hw`` and ``self._fs``), so ``self.lasers`` /
    ``self.camera`` / ``self.siggen`` / ``self.motors`` / ``self.etls``
    and the display/status timers are populated — the same state the
    production app reaches after its 100ms ``timer_hardware_init``
    callback fires.

    ``QMessageBox.question`` is patched for the whole test (via a request
    finalizer that stops the patch at teardown) so ``closeEvent``
    (triggered when qtbot closes the widget at teardown) does not pop a
    modal exit-confirmation dialog that blocks the test runner. The
    hardware_init timers are also stopped at teardown so no pending
    timer callbacks fire after the test returns.
    """
    from lightsheet.gui.coordinators.acquisition_coordinator import (
        AcquisitionCoordinator,
    )
    from lightsheet.gui.coordinators.frame_saver_controller import FrameSaverController
    from lightsheet.gui.coordinators.hardware_manager import HardwareManager
    from lightsheet.gui.coordinators.motor_controller import MotorController
    from lightsheet.gui.shell.controller import Controller_MainWindow

    bundle = make_bundle()
    # Start the QMessageBox.question patch WITHOUT a `with` block so it
    # stays active through teardown. A request finalizer stops it after
    # the widget is closed.
    qm_patch = patch_qmessage_question()
    qm_patch.start()

    controller = Controller_MainWindow(bundle, demo=True)
    qtbot.addWidget(controller)

    # The shell's __init__ composes the per-panel widgets (laser_panel,
    # motor_panel, acquisition_panel, stack_panel, scan_panel,
    # save_panel, calibration_panel) into 8 stackedPanels pages (one
    # per left-rail button). The structural-assert smoke test
    # (test_panel_structure.py) verifies these attributes are non-None
    # and the panels are composed into the right containers. Panel
    # verification is NOT done here because adding assertions to the
    # fixture amplifies a pre-existing timer/signal leak under xdist
    # (timers fire after controller teardown, flooding stderr with
    # "Signal source has been deleted" errors that cause cross-test
    # contamination in xdist workers).
    #
    # Hybrid widget ownership: panel-internal widgets live on their
    # owning panel's ``ui`` (``controller.<panel>.ui.<name>``), NOT on
    # the flat ``controller.ui`` namespace. The shell's
    # ``vars(panel.ui)`` merge loop is trimmed to shell-owned widgets
    # only (E-stop toolbar, status bar, message log, left-rail
    # navigation, controlsPane), so tests reach panel-internal widgets
    # via the panel-qualified path. Cross-panel reads use
    # ``controller.<owner_panel>.ui.<name>``. Shell-owned widgets stay
    # on ``controller.ui.<name>``. See test_hybrid_ownership.py for the
    # regression gate.
    fs = FrameSaverController(bundle, controller)
    controller._fs = fs
    hw = HardwareManager(bundle, controller)
    controller._hw = hw
    acq = AcquisitionCoordinator(bundle, hw, controller)
    controller._acq = acq
    mc = MotorController(bundle, controller)
    controller._mc = mc

    # Wire the collaborator-dependent signal connections (MotorController
    # / AcquisitionCoordinator delegates). These were previously lambda
    # connections in __init__ that created a reference cycle; they now
    # live in wire_collaborators() as bare bound-method connections,
    # called here after all four collaborators are assigned.
    controller.wire_collaborators()

    # Run hardware_init synchronously (production defers it to a 100ms
    # QTimer so the event loop is pumping first; in tests we call it
    # directly so self.lasers / timers are populated before the test
    # exercises any method that reads them).
    controller.hardware_init()
    # Stop the deferred timer_hardware_init (started in __init__) so it
    # cannot fire a SECOND hardware_init during a test's QEventLoop spin
    # (e.g. the queue's loop.exec). A double-call clobbers stack params:
    # _load_stack_params' step-spinbox setValue triggers
    # updateUi_set_number_of_planes, which re-reads the first-plane
    # spinbox and overwrites stack_starting_plane. On Mac the mock init
    # is fast and the timer fires between tests (harmless); on the rig
    # the real init is slow so the pending timer fires mid-test.
    controller.timer_hardware_init.stop()

    def _stop_worker_threads() -> None:
        # Mirror closeEvent's quit()+wait() shutdown so no worker QThread
        # outlives a test. Mock HAL calls are non-blocking, so the
        # cooperative poll exits within one iteration after close_modes()
        # clears the mode-started flags. A shorter bound than production's
        # 5000 is acceptable here (2000 ms) for the same reason.
        controller.close_modes()
        # Stop the frame_saver QThread (quit()+wait with the h5py quiesce
        # timeout) — no-op if no save was started.
        controller._fs.frame_saver.stop_saving()  # ty: ignore[unresolved-attribute]
        # Stop the laser2 readback QThread if one is in flight. The
        # readback worker self-quits via sig_finished→thread.quit
        # (DirectConnection, fires on the worker thread), so the thread
        # always exits on its own once the worker's start_readback slot
        # runs. The teardown only needs to nudge a still-running thread
        # and pump the event loop while it drains — a blocking
        # QThread.wait() here would stall the main event loop and, under
        # xdist with ~50 controllers per worker, stack into an apparent
        # hang when quit() races ahead of the thread's exec() (quit
        # before exec is a no-op, the thread then runs unattended). The
        # non-blocking poll below pumps events so a queued quit reaches
        # the thread's event loop and the thread reaps deterministically.
        _quit_thread_draining(getattr(controller._hw, "_readback_thread", None))
        for attr in (
            "_preview_thread",
            "_live_thread",
            "_single_thread",
            "_stack_thread",
        ):
            _quit_thread_draining(getattr(controller, attr, None))

    def _teardown() -> None:
        # Deterministic teardown so no controller-owned widget tree
        # survives between tests. Cyclic GC is disabled for the whole
        # session (a Qt widget destructor segfault guard), so the C++
        # QWidget objects are NOT collected by refcount-on-zero alone —
        # the Python wrappers reach refcount zero (the signal-lambda
        # cycle is broken at the connection layer via bare bound-method
        # connections in wire_collaborators), but the underlying C++
        # widgets only get destroyed when Qt's DeferredDelete events are
        # actually delivered. processEvents() does NOT drain
        # DeferredDelete; only a real QEventLoop.exec() spin does.
        #
        # Order matters: timers and worker threads MUST stop before any
        # deleteLater() call, otherwise a queued timer callback (the
        # 100ms imageview poll / the ~1s laser2 status poll) fires into
        # the controller's signals while the C++ tree is being torn
        # down, raising "RuntimeError: Signal source has been deleted".

        # (a) Stop every shell-owned timer. The two recurring timers
        # (timer_imageview 100ms, timer_laser2_status ~1s) drive
        # HardwareManager._poll_laser_status / _refresh_laser_readback
        # / _poll_laser2_status_gated, which emit on shell signals —
        # they must be stopped before deletion. The three single-shot
        # timers (timer_hardware_init, _laser1_amplitude_timer,
        # _laser2_amplitude_timer) are stopped for hygiene so a
        # pending one-shot cannot fire during the deletion spin.
        # Guard with getattr — a test that tore a timer down itself
        # should not fail teardown.
        for timer_attr in (
            "timer_hardware_init",
            "timer_imageview",
            "timer_laser2_status",
            "_laser1_amplitude_timer",
            "_laser2_amplitude_timer",
        ):
            timer = getattr(controller, timer_attr, None)
            if timer is not None:
                timer.stop()

        # (b) Drain every worker QThread (frame saver, laser readback,
        # acquisition preview/live/single/stack) before any QObject is
        # scheduled for deletion, mirroring closeEvent's quit()+wait()
        # shutdown so no worker outlives the test.
        _stop_worker_threads()

        # (c) Snapshot the controller-owned top-level widgets while the
        # controller is still valid. Only reap the controller itself and
        # top-level widgets for which controller.isAncestorOf(widget) is
        # True — never sweep unrelated QApplication top-levels (other
        # tests' widgets, qtbot's own scaffolding, etc.).
        app = QApplication.instance()
        owned_toplevels: list = []  # ty: ignore[missing-type-argument]
        if app is not None:
            for widget in app.topLevelWidgets():  # ty: ignore[unresolved-attribute]
                if widget is controller:
                    continue
                try:
                    if controller.isAncestorOf(widget):
                        owned_toplevels.append(widget)
                except RuntimeError:
                    # widget already invalidated — nothing to reap.
                    pass

        # (d) Schedule deferred deletion of owned top-levels first, then
        # the controller itself so child deletion cascades. Keep the
        # message-box patch active through this phase so a closeEvent
        # triggered during the spin does not pop a modal exit dialog
        # that blocks the test runner.
        for widget in owned_toplevels:
            with contextlib.suppress(RuntimeError):
                widget.deleteLater()
        controller.deleteLater()

        # (e) Drain DeferredDelete events via a bounded REAL
        # QEventLoop.exec() spin. QApplication.processEvents() does
        # NOT deliver DeferredDelete events (proven by probe), so it
        # cannot substitute for this. The single-shot quit is the hard
        # upper bound. The ~60ms per-controller teardown cost is the
        # accepted tradeoff (~3s/worker across ~50 tests) for removing
        # the observed up-to-28s stylesheet restyle spike and the
        # intermittent deleted-signal failures that accumulated when
        # controller-owned widget trees persisted across tests.
        loop = QEventLoop()
        QTimer.singleShot(60, loop.quit)
        loop.exec()

        # (f) Stop the message-box patch only after the bounded loop
        # returns, so closeEvent during deletion stays non-modal.
        qm_patch.stop()

    request.addfinalizer(_teardown)
    return controller, bundle


def patch_qmessage_question() -> Any:
    """Return a context manager (unittest.mock.patch) that patches
    ``PySide6.QtWidgets.QMessageBox.question`` to return
    ``QMessageBox.StandardButton.Yes`` without showing a modal dialog.
    ``make_controller`` starts it for the whole test so the teardown
    ``closeEvent`` does not block the test runner on an exit confirmation
    popup. Tests that exercise ``closeEvent`` directly can also use this
    as a ``with``-block to control the dialog's return value."""
    from unittest.mock import patch

    from PySide6.QtWidgets import QMessageBox

    return patch(
        "PySide6.QtWidgets.QMessageBox.question",
        return_value=QMessageBox.StandardButton.Yes,
    )
