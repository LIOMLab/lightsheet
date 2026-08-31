"""Obsolete sub-panel / button pruning regression test (audit #8).

The Guide.pdf flags several "désuet" (obsolete) items. Each was audited
against the current HAL wiring before this test was written:

* ``pushButton_calCameraStartCalibration`` — the camera-calibration
  *worker* that populated ``camera_focus_relation`` was deleted in an
  earlier phase; the Start button was left in the .ui but never wired to
  a slot (grep ``controller.py`` for ``calCameraStartCalibration``
  returns no ``clicked.connect``). Dead → deleted.
* ``pushButton_calEtlStartCalibration`` — same story for the ETL
  calibration worker; the Start button was never wired. Dead → deleted.
* ``pushButton_resetSettings`` (scan panel) — never connected to any
  handler (the scan-panel module docstring recorded it as
  "currently unconnected"). Dead → deleted.

The live calibration buttons (Compute Camera Focus, Show Camera/ETL
Interpolation, Horizontal Range Selection) ARE wired to MotorController
slots and remain — they get tooltips explaining their current function.

This test is the structural backstop: it asserts the dead buttons are
absent from the constructed widget tree AND the live ones are present
with a non-empty tooltip. It runs headless on Mac via
``QT_QPA_PLATFORM=offscreen`` (set by conftest).
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from PySide6.QtCore import QObject
from pytestqt.qtbot import QtBot

pytest.importorskip("PySide6")


# --------------------------------------------------------------------------- #
# Dead buttons — must be absent from the constructed widget tree.
# --------------------------------------------------------------------------- #


def test_calCameraStartCalibration_button_is_deleted(qtbot: QtBot) -> None:
    """The dead 'Start Camera Calibration' button is pruned from the .ui."""
    from lightsheet.gui.panels.calibration_panel import CalibrationPanelWidget

    panel = CalibrationPanelWidget(Mock())
    qtbot.addWidget(panel)
    assert panel.findChild(QObject, "pushButton_calCameraStartCalibration") is None, (
        "pushButton_calCameraStartCalibration is dead (never wired to a slot; "
        "the camera-calibration worker was deleted) and must be pruned."
    )


def test_calEtlStartCalibration_button_is_deleted(qtbot: QtBot) -> None:
    """The dead 'Start ETL Calibration' button is pruned from the .ui."""
    from lightsheet.gui.panels.calibration_panel import CalibrationPanelWidget

    panel = CalibrationPanelWidget(Mock())
    qtbot.addWidget(panel)
    assert panel.findChild(QObject, "pushButton_calEtlStartCalibration") is None, (
        "pushButton_calEtlStartCalibration is dead (never wired to a slot; "
        "the ETL-calibration worker was deleted) and must be pruned."
    )


def test_resetSettings_button_is_deleted(qtbot: QtBot) -> None:
    """The dead 'Reset Settings' button is pruned from the scan panel .ui."""
    from lightsheet.gui.panels.scan_panel import ScanPanelWidget

    panel = ScanPanelWidget(Mock())
    qtbot.addWidget(panel)
    assert panel.findChild(QObject, "pushButton_resetSettings") is None, (
        "pushButton_resetSettings is dead (never connected to a handler) "
        "and must be pruned."
    )


# --------------------------------------------------------------------------- #
# Live-but-undocumented calibration buttons — must be present + have a
# non-empty tooltip explaining their current function.
# --------------------------------------------------------------------------- #


def test_live_calibration_buttons_have_tooltips(qtbot: QtBot) -> None:
    """The live calibration buttons remain and carry a non-empty tooltip."""
    from lightsheet.gui.panels.calibration_panel import CalibrationPanelWidget

    panel = CalibrationPanelWidget(Mock())
    qtbot.addWidget(panel)

    live_buttons = (
        "pushButton_calCameraComputeFocus",
        "pushButton_calCameraShowInterpolation",
        "pushButton_calEtlShowInterpolation",
        "pushButton_calHorizontalStartRangeSelection",
        "pushButton_calHorizontalSetForwardLimit",
        "pushButton_calHorizontalSetBackwardLimit",
    )
    for name in live_buttons:
        btn = panel.findChild(QObject, name)
        assert btn is not None, f"{name} is live and must remain in the .ui"
        tip = btn.toolTip()
        assert tip and tip.strip(), (
            f"{name} is live-but-undocumented and must carry a non-empty "
            "tooltip explaining its current function."
        )


def test_live_calibration_spinboxes_have_tooltips(qtbot: QtBot) -> None:
    """The live calibration numeric inputs carry a non-empty tooltip."""
    from lightsheet.gui.panels.calibration_panel import CalibrationPanelWidget

    panel = CalibrationPanelWidget(Mock())
    qtbot.addWidget(panel)

    live_spinboxes = (
        "doubleSpinBox_calNumberOfPlanes",
        "doubleSpinBox_calNumberOfCameraPositions",
        "doubleSpinBox_calNumberOfEtlVoltages",
    )
    for name in live_spinboxes:
        sb = panel.findChild(QObject, name)
        assert sb is not None, f"{name} is live and must remain in the .ui"
        tip = sb.toolTip()
        assert tip and tip.strip(), (
            f"{name} must carry a non-empty tooltip (unit + range + effect)."
        )
