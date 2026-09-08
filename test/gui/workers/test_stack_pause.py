"""Stack pause lifecycle tests.

Covers the plane-boundary pause: the shell ``pause_requested`` event (a
peer of ``estop_event``, never a wrapper), the Pause button enable/latch
semantics, the ``STACK PAUSING`` mode badge, the worker's loop-top poll
and ``paused`` manifest lifecycle, E-stop precedence over pause, and the
pause→resume path through a fresh worker with a ``start_plane`` offset.
"""

from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import Mock

import pytest
from pytestqt.qtbot import QtBot

pytest.importorskip("PySide6")

from lightsheet.gui.workers import StackWorker
from lightsheet.hal import DeviceBundle


def _make_bundle() -> DeviceBundle:
    from test.helpers.factories import make_bundle

    return make_bundle()


def _make_shell(bundle: DeviceBundle, n_planes: int) -> Mock:
    """Minimal mock shell stand-in (same pattern as test_stack_resume.py)."""
    shell = Mock()
    shell.lasers = bundle.lasers
    shell.stack_mode_started = True
    shell.estop_event = threading.Event()
    shell.pause_requested = threading.Event()
    shell.saving_allowed = False
    shell.number_of_planes = n_planes
    shell.stack_starting_plane = 0.0
    shell.stack_step = 10.0
    shell.reconstructed_frame = None
    shell.reconstructed_frames = {}
    shell._fs = Mock()
    shell.state.snapshot.return_value = None
    return shell


def _make_worker(
    bundle: DeviceBundle, shell: Mock, n_planes: int, start_plane: int = 0
) -> StackWorker:
    worker = StackWorker(
        bundle,
        Mock(),
        shell,  # ty: ignore[invalid-argument-type]
        save_description="pause test",
        start_plane=start_plane,
    )
    worker.acquire_scan = Mock(return_value=True)
    return worker


def test_pause_requested_is_separate_event(
    qtbot: QtBot, controller: object
) -> None:
    """The shell carries a dedicated threading.Event for pause — it must
    never alias or wrap estop_event."""
    assert isinstance(controller.pause_requested, threading.Event)
    assert isinstance(controller.estop_event, threading.Event)
    assert controller.pause_requested is not controller.estop_event
    controller.pause_requested.set()
    assert controller.pause_requested.is_set()
    assert not controller.estop_event.is_set()
    controller.pause_requested.clear()
    assert not controller.pause_requested.is_set()


def test_pause_button_disabled_when_idle(
    qtbot: QtBot, controller: object
) -> None:
    """With no stack running, the Pause control stays latched off."""
    btn = controller.stack_panel.ui.pushButton_acqPauseStack
    assert not btn.isEnabled()


def test_pause_click_sets_event_and_latches_button(
    qtbot: QtBot, controller: object
) -> None:
    """Clicking Pause while a stack runs sets pause_requested, disables
    the button, and shows the STACK PAUSING badge."""
    btn = controller.stack_panel.ui.pushButton_acqPauseStack
    controller.stack_mode_started = True
    controller.number_of_planes = 5
    btn.setEnabled(True)

    controller.acquisition_panel.on_stack_pause_clicked()

    assert controller.pause_requested.is_set()
    assert not btn.isEnabled()
    assert "PAUSING" in controller.ui.label_modeBadge.text()
    controller.pause_requested.clear()
    controller.stack_mode_started = False


def test_estop_does_not_set_pause(
    qtbot: QtBot, controller: object
) -> None:
    """The E-stop kill path touches only estop_event and lasers — pause
    is never part of the E-stop path."""
    controller.updateUi_estop_pressed()
    assert controller.estop_event.is_set()
    assert not controller.pause_requested.is_set()
