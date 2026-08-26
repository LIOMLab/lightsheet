"""closeEvent shutdown tests for the preview worker QThread.

Verifies that ``closeEvent`` shuts the preview worker ``QThread`` down via
``quit()`` + ``wait(5000)`` (the QThread vehicle replacement for
``join(timeout=5.0)``), with no ``join()`` call on the preview thread and
no ``time.sleep``. The real ``Controller_MainWindow`` is constructed via
``make_controller``; preview mode is started via
``updateUi_preview_mode_button`` (which spawns the ``QThread``), then
``closeEvent`` is triggered and the thread is asserted to no longer be
running.
"""

from __future__ import annotations

from unittest.mock import patch

from _helpers.controller_fixture import make_controller, patch_qmessage_question


def test_close_event_quits_preview_thread(qtbot, request) -> None:
    """closeEvent quits + waits the preview QThread (not join). Starting
    preview mode spawns ``self._preview_thread`` (a QThread); closeEvent
    must call ``quit()`` + ``wait(5000)`` on it and the thread must no
    longer be running afterward."""
    ctrl, _bundle = make_controller(qtbot, request)

    # Start preview mode — this constructs PreviewWorker + QThread and
    # calls thread.start(). The worker's while loop runs with
    # preview_mode_started=True, but the mock camera's recorder calls are
    # non-blocking so the loop iterates quickly.
    ctrl.preview_mode_started = False  # else: branch (start path)
    ctrl.acquisition_panel.updateUi_preview_mode_button()

    # The preview thread should now exist and be running.
    assert hasattr(ctrl, "_preview_thread"), "preview thread must be spawned"
    assert ctrl._preview_thread.isRunning(), "preview thread must be running after start"

    # Trigger closeEvent with a real QCloseEvent. The QMessageBox.question
    # patch (started by make_controller) returns Yes so shutdown proceeds.
    from PySide6.QtGui import QCloseEvent

    event = QCloseEvent()
    ctrl.closeEvent(event)
    assert event.isAccepted(), "closeEvent must accept the event on Yes"

    # The preview thread must no longer be running after quit()+wait().
    assert not ctrl._preview_thread.isRunning(), (
        "preview thread must not be running after closeEvent"
    )


def test_close_event_no_join_on_preview_thread(qtbot, request) -> None:
    """closeEvent must NOT call join() on the preview thread — the QThread
    vehicle uses quit() + wait() instead. Verified by asserting the
    _preview_thread attribute is a QThread (which has no join method)."""
    from PySide6.QtCore import QThread

    ctrl, _bundle = make_controller(qtbot, request)

    ctrl.preview_mode_started = False
    ctrl.acquisition_panel.updateUi_preview_mode_button()

    assert isinstance(ctrl._preview_thread, QThread), (
        "_preview_thread must be a QThread, not a threading.Thread"
    )
    assert not hasattr(ctrl._preview_thread, "join"), (
        "QThread must not have a join method — closeEvent uses quit()+wait()"
    )

    # Clean up: quit the thread so it doesn't outlive the test.
    ctrl.preview_mode_started = False
    ctrl._preview_thread.quit()
    ctrl._preview_thread.wait(2000)


def test_close_event_preview_timeout_logs_warning(qtbot, request) -> None:
    """closeEvent with the preview thread not exiting within 5s: the
    wait() timeout fires and logger.warning is emitted (log-only, no
    sig_message — the UI is tearing down). Verified by patching
    QThread.wait to return False (simulating a timeout) and asserting the
    warning was logged."""
    import logging

    from PySide6.QtCore import QThread
    from PySide6.QtGui import QCloseEvent

    ctrl, _bundle = make_controller(qtbot, request)

    ctrl.preview_mode_started = False
    ctrl.acquisition_panel.updateUi_preview_mode_button()

    # Patch wait to return False (timeout) so the warning path fires.
    # Also patch quit so it doesn't actually stop the thread (the mock
    # camera loop is non-blocking so the real thread would exit anyway,
    # but we want to deterministically exercise the timeout branch).
    with (
        patch.object(QThread, "wait", return_value=False),
        patch.object(QThread, "quit", lambda self: None),
    ):
        with patch.object(
            logging.getLogger("lightsheet.gui.shell.controller"),
            "warning",
        ) as mock_warning:
            event = QCloseEvent()
            ctrl.closeEvent(event)
            assert event.isAccepted()
            mock_warning.assert_called()
            # The warning message mentions _preview_thread and the timeout.
            warning_msg = " ".join(str(a) for a in mock_warning.call_args[0])
            assert "_preview_thread" in warning_msg
            assert "5s" in warning_msg

    # Clean up: stop the thread for real.
    ctrl.preview_mode_started = False
    ctrl._preview_thread.quit()
    ctrl._preview_thread.wait(2000)
