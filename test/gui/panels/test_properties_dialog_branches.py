"""Branch-coverage closure for ``lightsheet.gui.panels.properties_dialog``.

The Properties_Dialog is a QDialog subclass that reads camera + motor
properties and displays them via Ui_Properties. The first group of tests
uses the ``__new__`` bypass pattern to construct the dialog without
calling ``QDialog.__init__`` (avoiding Qt parenting issues), mocks
``Ui_Properties`` to avoid the generated ``setupUi`` call, and exercises
``get_properties`` and ``refresh_properties`` directly.

The second group constructs ``Properties_Dialog`` for real through the
``controller`` fixture — covering the ``__init__`` body (camera/motors
binding, setupUi, signal wiring, initial get_properties) that the
``__new__`` bypass skips — and drives the real Refresh button and the
shell's ``open_properties_dialog`` entry point.

Behavior tests (AGENTS.md §5) — every assertion is on a runtime
postcondition (label text, emitted signal), never a static-source grep.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot

    from lightsheet.gui.shell.controller import Controller_MainWindow


def _make_mock_parent() -> Mock:
    """Build a mock parent with camera + motors that return property dicts."""
    parent = Mock()
    parent.camera = Mock()
    parent.camera.get_properties.return_value = {
        "camera name": "PCO Edge",
        "x": 1920,
        "y": 1080,
        "camera temperature": 25.0,
        "sensor temperature": 22.0,
        "power temperature": 30.0,
        "trigger mode": "Auto",
        "delay": 0.001,
        "delay timebase": "ms",
        "exposure": 0.010,
        "exposure timebase": "ms",
        "acquire mode": "Auto",
        "storage mode": "Recorder",
        "recorder submode": "FIFO",
    }
    parent.motors = Mock()
    parent.motors.get_properties.return_value = {
        "horizontal name": "T-LSM100B",
        "vertical name": "T-LSM050A",
        "camera name": "T-LSR150B",
    }
    parent.updateUi_message_printer = Mock()
    return parent


def _make_dialog(parent: Mock) -> Mock:
    """Construct Properties_Dialog via __new__ bypass — no QDialog.__init__,
    no setupUi. The ui attribute is a Mock so label.setText calls are captured."""
    pytest.importorskip("PySide6")
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])

    from lightsheet.gui.panels.properties_dialog import Properties_Dialog

    # Bypass __init__ entirely — populate the attributes the methods read.
    dlg = Properties_Dialog.__new__(Properties_Dialog)
    dlg.parent = parent
    dlg.camera = parent.camera
    dlg.motors = parent.motors
    dlg.ui = Mock()
    # Mock the signal — emit just calls connected slots.
    dlg.sig_status_message = Mock()
    return dlg  # ty: ignore[invalid-return-type]


def test_properties_dialog_get_properties_recorder_mode() -> None:
    """get_properties populates labels from camera + motor properties,
    including the 'Recorder' storage mode branch (line 74-77 True branch)."""
    parent = _make_mock_parent()
    dlg = _make_dialog(parent)
    dlg.get_properties()
    # Verify the camera name label was set.
    dlg.ui.label_cameraName.setText.assert_called_with("PCO Edge")
    # Verify the recorder submode label was set (Recorder branch).
    dlg.ui.label_recorderMode.setText.assert_called_with("FIFO")
    # Verify motor names.
    dlg.ui.label_horizontalMotorName.setText.assert_called_with("T-LSM100B")
    dlg.ui.label_verticalMotorName.setText.assert_called_with("T-LSM050A")
    dlg.ui.label_cameraMotorName.setText.assert_called_with("T-LSR150B")


def test_properties_dialog_get_properties_non_recorder_mode() -> None:
    """get_properties with storage mode != 'Recorder' -> the else branch
    sets label_recorderMode to '-' (line 78-79)."""
    parent = _make_mock_parent()
    parent.camera.get_properties.return_value["storage mode"] = "Sequence"
    dlg = _make_dialog(parent)
    dlg.get_properties()
    dlg.ui.label_recorderMode.setText.assert_called_with("-")


def test_properties_dialog_refresh_properties_emits_signal() -> None:
    """refresh_properties() re-reads properties and emits the status message
    signal (lines 94-97)."""
    parent = _make_mock_parent()
    dlg = _make_dialog(parent)
    dlg.refresh_properties()
    # Verify the signal was emitted with the refresh message.
    dlg.sig_status_message.emit.assert_called_once_with("System Properties Refreshed")


# ---------------------------------------------------------------------------
# Real-construction coverage — the __init__ body (30-40) and the live
# signal wiring that the __new__ bypass skips.
# ---------------------------------------------------------------------------


def test_properties_dialog_real_construction_populates_labels(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """``Properties_Dialog(controller)`` runs the real ``__init__``:
    binds the live camera/motors handles, runs generated ``setupUi``,
    wires the Refresh button and the status-message signal, and performs
    the initial ``get_properties`` — so the labels show the mock HAL's
    real property values."""
    pytest.importorskip("PySide6")
    from lightsheet.gui.panels.properties_dialog import Properties_Dialog

    ctrl = controller
    dlg = Properties_Dialog(ctrl)
    qtbot.addWidget(dlg)
    try:
        ui = dlg.ui
        # Camera fields from MockCamera.get_properties().
        assert ui.label_cameraName.text() == "MockCamera"
        assert ui.label_imageSize.text() == "2048 X 2048"
        # storage mode 'Recorder' -> recorder submode shown (not '-').
        assert ui.label_storageMode.text() == "Recorder"
        assert ui.label_recorderMode.text() == "sequence non blocking"
        # Motor names from MockMotors.get_properties().
        assert ui.label_horizontalMotorName.text() != ""
        assert ui.label_verticalMotorName.text() != ""
        assert ui.label_cameraMotorName.text() != ""
    finally:
        dlg.close()


def test_properties_dialog_refresh_button_routes_to_message_log(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """Clicking the real Refresh button runs refresh_properties, whose
    sig_status_message is wired to the shell's updateUi_message_printer —
    the operator-visible 'System Properties Refreshed' lands in the
    message log."""
    pytest.importorskip("PySide6")
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QAbstractButton

    from lightsheet.gui.panels.properties_dialog import Properties_Dialog

    ctrl = controller
    dlg = Properties_Dialog(ctrl)
    qtbot.addWidget(dlg)
    try:
        refresh = dlg.ui.pushButton_refresh
        assert isinstance(refresh, QAbstractButton)
        qtbot.mouseClick(refresh, Qt.MouseButton.LeftButton)
        assert (
            "System Properties Refreshed"
            in ctrl.ui.plainTextEdit_messageLog.toPlainText()
        )
    finally:
        dlg.close()


def test_open_properties_dialog_entry_point(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """The shell's ``open_properties_dialog`` slot constructs, opens, and
    refreshes the dialog — the real entry point used by the Help menu."""
    pytest.importorskip("PySide6")
    from test.helpers.cleanup import _pump_deferred_delete

    ctrl = controller
    ctrl.open_properties_dialog()
    dlg = ctrl.properties_dialog
    try:
        assert dlg.isVisible() or dlg.isWindow()
        # get_properties ran during __init__ + again via the slot.
        assert dlg.ui.label_cameraName.text() == "MockCamera"
    finally:
        dlg.close()
        _pump_deferred_delete()
