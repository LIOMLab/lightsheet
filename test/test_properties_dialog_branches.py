"""Branch-coverage closure for ``lightsheet.gui.properties_dialog``.

The Properties_Dialog is a QDialog subclass that reads camera + motor
properties and displays them via Ui_Properties. The tests use the
``__new__`` bypass pattern to construct the dialog without calling
``QDialog.__init__`` (avoiding Qt parenting issues), mock ``Ui_Properties``
to avoid the generated ``setupUi`` call, and exercise ``get_properties``
and ``refresh_properties`` directly.

Behavior tests (AGENTS.md §5) — every assertion is on a runtime
postcondition (label text, emitted signal), never a static-source grep.
"""

from __future__ import annotations

from unittest.mock import MagicMock, Mock, patch

import pytest


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


def _make_dialog(parent: Mock):
    """Construct Properties_Dialog via __new__ bypass — no QDialog.__init__,
    no setupUi. The ui attribute is a Mock so label.setText calls are captured."""
    pytest.importorskip("PyQt5")
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])

    from lightsheet.gui.properties_dialog import Properties_Dialog

    # Bypass __init__ entirely — populate the attributes the methods read.
    dlg = Properties_Dialog.__new__(Properties_Dialog)
    dlg.parent = parent
    dlg.camera = parent.camera
    dlg.motors = parent.motors
    dlg.ui = Mock()
    # Mock the signal — emit just calls connected slots.
    dlg.sig_status_message = Mock()
    return dlg


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
