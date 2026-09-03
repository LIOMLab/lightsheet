"""Real-construction pytest fixtures for ``Controller_MainWindow``."""

from __future__ import annotations

import contextlib
from typing import Any

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox
from pytestqt.qtbot import QtBot

from lightsheet.gui.coordinators.acquisition_coordinator import (
    AcquisitionCoordinator,
)
from lightsheet.gui.coordinators.frame_saver_controller import FrameSaverController
from lightsheet.gui.coordinators.hardware_manager import HardwareManager
from lightsheet.gui.coordinators.motor_controller import MotorController
from lightsheet.gui.shell.controller import Controller_MainWindow
from lightsheet.hal import DeviceBundle
from test.helpers.cleanup import _pump_deferred_delete, _quit_thread_draining
from test.helpers.factories import make_bundle


@pytest.fixture
def bundle() -> DeviceBundle:
    """Return a fresh mock ``DeviceBundle``."""
    return make_bundle()


def _build_controller(
    bundle: DeviceBundle, qtbot: QtBot, request: Any
) -> Controller_MainWindow:
    """Construct ``Controller_MainWindow`` with all collaborators wired.

    Mirrors the composition root in ``lightsheet/__main__.py:main()``:
    shell first, then the four collaborators, ``wire_collaborators()``,
    and ``hardware_init()`` (with the deferred ``timer_hardware_init``
    stopped so it cannot fire mid-test).
    """
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

    controller.wire_collaborators()
    controller.hardware_init()
    controller.timer_hardware_init.stop()

    def _finalizer() -> None:
        # (a) Stop every shell-owned timer before any QObject is deleted.
        for timer_attr in (
            "timer_hardware_init",
            "timer_imageview",
            "timer_laser2_status",
            "_laser1_amplitude_timer",
            "_laser2_amplitude_timer",
        ):
            timer = getattr(controller, timer_attr, None)
            if timer is not None:
                with contextlib.suppress(RuntimeError):
                    timer.stop()

        # (b) Stop active modes and drain worker threads.
        with contextlib.suppress(RuntimeError):
            controller.close_modes()
        with contextlib.suppress(RuntimeError):
            controller._fs.frame_saver.stop_saving()
        _quit_thread_draining(getattr(controller._hw, "_readback_thread", None))
        for attr in (
            "_preview_thread",
            "_live_thread",
            "_single_thread",
            "_stack_thread",
        ):
            _quit_thread_draining(getattr(controller, attr, None))

        # (c) Schedule owned top-level widgets and the controller for deletion.
        app = QApplication.instance()
        if app is not None:
            owned_toplevels: list = []
            for widget in app.topLevelWidgets():
                if widget is controller:
                    continue
                try:
                    if controller.isAncestorOf(widget):
                        owned_toplevels.append(widget)
                except RuntimeError:
                    pass
            for widget in owned_toplevels:
                with contextlib.suppress(RuntimeError):
                    widget.deleteLater()
        with contextlib.suppress(RuntimeError):
            controller.deleteLater()

        # (d) Pump DeferredDelete until the widget tree is gone.
        _pump_deferred_delete(500)

        # (e) Stop the message-box patch only after deletion is complete.
        qm_patch.stop()

    request.addfinalizer(_finalizer)
    return controller


@pytest.fixture
def controller(
    bundle: DeviceBundle, qtbot: QtBot, request: Any
) -> Controller_MainWindow:
    """Return a fully constructed ``Controller_MainWindow`` with teardown."""
    return _build_controller(bundle, qtbot, request)


def patch_qmessage_question() -> Any:
    """Return a patch that makes ``QMessageBox.question`` always return Yes."""
    from unittest.mock import patch

    return patch(
        "PySide6.QtWidgets.QMessageBox.question",
        return_value=QMessageBox.StandardButton.Yes,
    )


__all__ = ["bundle", "controller", "patch_qmessage_question"]
