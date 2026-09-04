"""Qt lifecycle cleanup helpers for tests.

These helpers run on the main thread and pump the Qt event loop so
``deleteLater()``-scheduled C++ objects are actually destroyed between
tests under xdist.
"""

from __future__ import annotations

import contextlib
import os
from typing import Any

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

# xdist workers process a subset of tests and exit, so a shorter pump is
# enough and keeps the parallel wall time down. The serial (single-
# process) run needs a longer pump to fully reap deep widget trees and
# avoid leaking C++ objects across the full suite.
_DEFERRED_DELETE_MAX_MS = 100 if os.environ.get("PYTEST_XDIST_WORKER") else 300


def _pump_deferred_delete(max_ms: int = _DEFERRED_DELETE_MAX_MS) -> None:
    """Spin a real ``QEventLoop`` until ``QApplication.topLevelWidgets()``
    is empty or ``max_ms`` expires.

    ``QApplication.processEvents()`` does *not* deliver ``DeferredDelete``
    events; only a real event-loop spin does. A 20 ms poll timer checks
    ``topLevelWidgets()`` and quits early once the tree is reaped, while
    an absolute single-shot deadline guarantees the loop returns.

    The default deadline is 100 ms under xdist (keeps the parallel wall
    time low) and 300 ms for serial runs (lets deep ``Controller_MainWindow``
    widget trees finish deleting and avoids the OOM-and-kill pattern seen
    on long single-process runs).
    """
    app = QApplication.instance()
    if app is None:
        return

    loop = QEventLoop()
    poll = QTimer()
    poll.setInterval(20)
    elapsed = 0

    def _tick() -> None:
        nonlocal elapsed
        elapsed += poll.interval()
        empty = False
        try:
            empty = not app.topLevelWidgets()
        except RuntimeError:
            empty = True
        if empty or elapsed >= max_ms:
            poll.stop()
            loop.quit()

    poll.timeout.connect(_tick)
    poll.start()
    QTimer.singleShot(max_ms, loop.quit)
    loop.exec()


def _quit_thread_draining(thread: Any | None, timeout_ms: int = 2000) -> None:
    """Quit a worker ``QThread`` and pump the event loop until it stops.

    Unlike ``QThread.wait()`` (which blocks without processing events), this
    polls ``isRunning()`` while flushing the ``QApplication`` event queue.
    That lets a queued ``quit()`` reach the thread's event loop and the
    thread reap deterministically under xdist, where a blocking wait can
    stall when ``quit()`` races ahead of the thread's ``exec()``.

    ``requestInterruption()`` is called before ``quit()`` so production
    acquisition worker ``run()`` loops that poll
    ``QThread.currentThread().isInterruptionRequested()`` can exit early
    instead of blocking teardown on a long-running acquisition step.
    """
    if thread is None:
        return
    try:
        if not thread.isRunning():
            return
    except RuntimeError:
        # C++ object already deleted.
        return
    # Set the interruption flag first so any cooperative worker loop that
    # checks ``isInterruptionRequested()`` can break before we ask the event
    # loop to quit.
    with contextlib.suppress(RuntimeError):
        thread.requestInterruption()
    try:
        thread.quit()
    except RuntimeError:
        # C++ object already deleted.
        return

    app = QApplication.instance()
    deadline = timeout_ms
    step_ms = 20
    while deadline > 0:
        try:
            if not thread.isRunning():
                break
        except RuntimeError:
            break
        if app is not None:
            with contextlib.suppress(RuntimeError):
                app.processEvents()
        thread.wait(step_ms)
        deadline -= step_ms
