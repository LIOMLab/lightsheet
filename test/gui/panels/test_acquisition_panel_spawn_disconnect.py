"""Regression test: repeated stack-worker spawn/teardown must not emit a
libpyside ``RuntimeWarning``.

PySide6 emits a ``RuntimeWarning`` (not an exception) when ``disconnect()``
is called on a signal with no live connection. ``_spawn_stack_worker``'s
thread-reuse path disconnects the previous run's signal connections before
reconnecting; every site must be receivers-guarded or suppressed so a
spawn → finish → respawn cycle stays silent — a stray warning masks real
signal-wiring bugs in production logs.
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING

import pytest
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

pytest.importorskip("PySide6")

from test.helpers.cleanup import _quit_thread_draining

if TYPE_CHECKING:
    from lightsheet.gui.shell.controller import Controller_MainWindow


def _drain_stack_thread(ctrl: Controller_MainWindow) -> None:
    """Wait for the current stack worker's QThread to stop, then spin a
    real event loop so the queued finished-slot delivery and the worker's
    deleteLater land (``processEvents()`` does not deliver DeferredDelete).
    """
    _quit_thread_draining(getattr(ctrl, "_stack_thread", None))
    app = QApplication.instance()
    if app is None:
        return
    loop = QEventLoop()
    QTimer.singleShot(100, loop.quit)
    loop.exec()


def test_repeated_stack_spawn_emits_no_disconnect_runtimewarning(
    controller: Controller_MainWindow,
) -> None:
    """A spawn → teardown → respawn cycle on the reused QThread emits no
    disconnect RuntimeWarning.

    ``saving_allowed`` stays False so the worker takes the no-save path and
    nothing touches the filesystem; ``stack_mode_started`` stays False so
    the worker's plane loop breaks at the first poll and each run finishes
    in milliseconds. All the signal wiring the second spawn disconnects is
    established at spawn time, so the fast break still exercises the full
    reuse-branch disconnect guard set.
    """
    ctrl = controller
    ctrl.saving_allowed = False
    ctrl.stack_mode_started = False
    ctrl.number_of_planes = 2

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")

        worker1 = ctrl.acquisition_panel._spawn_stack_worker()
        assert worker1 is not None
        _drain_stack_thread(ctrl)
        ctrl.acquisition_panel.updateUi_post_stack_mode()

        # Second spawn takes the prev_thread reuse branch with all its
        # prev-worker / prev-signal disconnect guards.
        worker2 = ctrl.acquisition_panel._spawn_stack_worker()
        assert worker2 is not None
        assert worker2 is not worker1
        _drain_stack_thread(ctrl)
        ctrl.acquisition_panel.updateUi_post_stack_mode()

    bad = [
        w
        for w in caught
        if issubclass(w.category, RuntimeWarning)
        and "disconnect" in str(w.message).lower()
    ]
    assert not bad, (
        "disconnect RuntimeWarning(s) during spawn/teardown/spawn: "
        + "; ".join(str(w.message) for w in bad)
    )
