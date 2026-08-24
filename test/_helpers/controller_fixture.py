"""Shared real-construction fixture for ``Controller_MainWindow`` and its
collaborators — the sanctioned replacement for the ``_load_method`` exec
pattern (AGENTS.md §5).

``Controller_MainWindow`` IS constructable on Mac: ``uv run lightsheet
--demo`` does exactly that via ``_build_demo_bundle()`` in
``lightsheet/__main__.py``. The earlier belief that the class could not be
instantiated without a live Qt display / real hardware was wrong —
``QT_QPA_PLATFORM=offscreen`` + the conftest SDK stubs + the
``pyqtgraph.ImageView`` QWidget stub make real construction work on the
Mac dev box. Real construction produces genuine branch (arc) coverage
that the exec pattern structurally cannot (the exec'd code object's
arcs do not map back to the source file), and it exercises the real
``__init__`` signal/attribute wiring the exec pattern skipped entirely.

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

from typing import Any

from lightsheet.hal import (
    DeviceBundle,
    MockCamera,
    MockETLs,
    MockLaser,
    MockMotors,
    MockSigGen,
)


def make_bundle() -> DeviceBundle:
    """Build a mock ``DeviceBundle`` mirroring ``_build_demo_bundle()`` in
    ``lightsheet/__main__.py`` (Laser 1 = 555 nm / 300 mW, Laser 2 = 640 nm
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
            wavelength=640,
            max_power_mw=150.0,
            label="Laser 2 (640 nm)",
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
    from lightsheet.gui.acquisition_coordinator import AcquisitionCoordinator
    from lightsheet.gui.controller import Controller_MainWindow
    from lightsheet.gui.frame_saver_controller import FrameSaverController
    from lightsheet.gui.hardware_manager import HardwareManager
    from lightsheet.gui.motor_controller import MotorController

    bundle = make_bundle()
    # Start the QMessageBox.question patch WITHOUT a `with` block so it
    # stays active through teardown. A request finalizer stops it after
    # the widget is closed.
    qm_patch = patch_qmessage_question()
    qm_patch.start()

    controller = Controller_MainWindow(bundle, demo=True)
    qtbot.addWidget(controller)

    fs = FrameSaverController(bundle, controller)
    controller._fs = fs
    hw = HardwareManager(bundle, controller)
    controller._hw = hw
    acq = AcquisitionCoordinator(bundle, hw, controller)
    controller._acq = acq
    mc = MotorController(bundle, controller)
    controller._mc = mc

    # Run hardware_init synchronously (production defers it to a 100ms
    # QTimer so the event loop is pumping first; in tests we call it
    # directly so self.lasers / timers are populated before the test
    # exercises any method that reads them).
    controller.hardware_init()

    def _teardown() -> None:
        # Stop the hardware_init timers so no pending callback fires
        # after the test returns (the 100ms imageview timer + the L2
        # status poll). Guard with getattr — a test that tore these down
        # itself should not fail teardown.
        for timer_attr in ("timer_imageview", "timer_laser2_status"):
            timer = getattr(controller, timer_attr, None)
            if timer is not None:
                timer.stop()
        qm_patch.stop()

    request.addfinalizer(_teardown)
    return controller, bundle


def patch_qmessage_question():
    """Return a context manager (unittest.mock.patch) that patches
    ``PyQt5.QtWidgets.QMessageBox.question`` to return ``QMessageBox.Yes``
    without showing a modal dialog. ``make_controller`` starts it for the
    whole test so the teardown ``closeEvent`` does not block the test
    runner on an exit confirmation popup. Tests that exercise
    ``closeEvent`` directly can also use this as a ``with``-block to
    control the dialog's return value."""
    from unittest.mock import patch

    from PyQt5.QtWidgets import QMessageBox

    return patch(
        "PyQt5.QtWidgets.QMessageBox.question",
        return_value=QMessageBox.Yes,
    )
