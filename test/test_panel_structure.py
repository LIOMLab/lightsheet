"""Structural-assert widget-tree smoke test for the .ui split.

The golden-master characterization test (``test/golden/``) is structurally
blind: it captures ``sig_message`` / ``sig_progress`` emission sequences
against a Mock stand-in ``self``, so it cannot detect a broken panel layout
(a missing child widget does not change the emission sequence until a slot
that reads it is exercised). This module is the structural backstop — it
asserts the widget *tree* is intact after the panel split:

1. Each of the per-panel widgets instantiates and exposes its key child
   widgets by ``objectName`` (``findChild(QObject, name)``).
2. The thin shell composes the 8 panels into ``stackedPanels`` (a
   QStackedWidget driven by the left-rail QButtonGroup) and exposes
   them as ``ctrl.<panel>_panel`` attributes.
3. The E-stop toolbar (``pushButton_estop``, ``label_estopStatus``,
   ``pushButton_armReset``) lives in the shell — NOT in any panel — so the
   lock-free GUI-thread kill path (AGENTS.md §2) keeps a single owner.
4. The ImageView (``imageView``) lives in the shell.

Runs headless on Mac via ``QT_QPA_PLATFORM=offscreen`` (set by conftest).
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QObject  # noqa: E402


# ---------------------------------------------------------------------------
# Standalone panel instantiation — each panel builds its own widget tree
# from its ``Ui_*`` class. The shell is only stored as ``self._shell`` and
# read inside slot bodies, so a ``Mock`` stand-in is sufficient for
# construction-time structural assertions.
# ---------------------------------------------------------------------------


def test_laser_panel_instantiates(qtbot) -> None:
    """LaserPanelWidget exposes the per-laser toggle + amplitude controls."""
    from lightsheet.gui.panels.laser_panel import LaserPanelWidget

    panel = LaserPanelWidget(Mock())
    qtbot.addWidget(panel)

    # Per-laser toggle buttons (the .ui names are laserOne/laserTwo, not
    # laser1/laser2 — the plan's draft names were aspirational).
    assert panel.findChild(QObject, "pushButton_laserOneToggle") is not None
    assert panel.findChild(QObject, "pushButton_laserTwoToggle") is not None
    # Per-laser amplitude spinboxes.
    assert panel.findChild(QObject, "doubleSpinBox_laserOneAmplitude") is not None
    assert panel.findChild(QObject, "doubleSpinBox_laserTwoAmplitude") is not None
    # Auto-laser checkboxes (used by _cache_auto_laser_flags before workers).
    assert panel.findChild(QObject, "checkBox_laserOneAutomatic") is not None
    assert panel.findChild(QObject, "checkBox_laserTwoAutomatic") is not None


def test_motor_panel_instantiates(qtbot) -> None:
    """MotorPanelWidget exposes the sample + camera movement group boxes."""
    from lightsheet.gui.panels.motor_panel import MotorPanelWidget

    panel = MotorPanelWidget(Mock())
    qtbot.addWidget(panel)

    assert panel.findChild(QObject, "groupBox_SampleMovement") is not None
    assert panel.findChild(QObject, "groupBox_CameraMovement") is not None
    # A representative motor button (used by updateUi_motor_buttons).
    assert panel.findChild(QObject, "pushButton_sampleStepForward") is not None
    assert panel.findChild(QObject, "pushButton_cameraStepForward") is not None


def test_acquisition_panel_instantiates(qtbot) -> None:
    """AcquisitionPanelWidget exposes the four mode buttons."""
    from lightsheet.gui.panels.acquisition_panel import AcquisitionPanelWidget

    panel = AcquisitionPanelWidget(Mock())
    qtbot.addWidget(panel)

    assert panel.findChild(QObject, "pushButton_acqGetSingleImage") is not None
    assert panel.findChild(QObject, "pushButton_acqStartLiveMode") is not None
    assert panel.findChild(QObject, "pushButton_acqStartPreviewMode") is not None
    # Camera shutter/exposure controls (read by the acquisition workers).
    assert panel.findChild(QObject, "comboBox_cameraShutterMode") is not None
    assert panel.findChild(QObject, "doubleSpinBox_cameraExposureTime") is not None


def test_save_panel_instantiates(qtbot) -> None:
    """SavePanelWidget exposes the file-manager group box + directory picker."""
    from lightsheet.gui.panels.save_panel import SavePanelWidget

    panel = SavePanelWidget(Mock())
    qtbot.addWidget(panel)

    # groupBox_5 is the save-directory group; the dataset group is groupBox_16.
    assert panel.findChild(QObject, "groupBox_5") is not None
    assert panel.findChild(QObject, "groupBox_16") is not None
    assert panel.findChild(QObject, "pushButton_saveSelectDirectory") is not None
    assert panel.findChild(QObject, "pushButton_selectDataset") is not None
    assert panel.findChild(QObject, "lineEdit_saveDirectory") is not None


def test_stack_panel_instantiates(qtbot) -> None:
    """StackPanelWidget exposes the stack setup controls."""
    from lightsheet.gui.panels.stack_panel import StackPanelWidget

    panel = StackPanelWidget(Mock())
    qtbot.addWidget(panel)

    assert panel.findChild(QObject, "pushButton_acqStartStackMode") is not None
    assert panel.findChild(QObject, "pushButton_acqSetFirstPlane") is not None
    assert panel.findChild(QObject, "pushButton_acqSetLastPlane") is not None
    assert panel.findChild(QObject, "doubleSpinBox_acqPlaneStepSize") is not None
    assert panel.findChild(QObject, "doubleSpinBox_acqFirstPlane") is not None
    assert panel.findChild(QObject, "doubleSpinBox_acqLastPlane") is not None
    # The boundary-set checkboxes are gone (migrated to editable spinboxes).
    assert panel.findChild(QObject, "checkBox_acqFirstPlaneSet") is None
    assert panel.findChild(QObject, "checkBox_acqLastPlaneSet") is None


def test_scan_panel_instantiates(qtbot) -> None:
    """ScanPanelWidget exposes the ETL/Galvo settings container."""
    from lightsheet.gui.panels.scan_panel import ScanPanelWidget

    panel = ScanPanelWidget(Mock())
    qtbot.addWidget(panel)

    # The scan panel is a container; assert it constructs and is non-null.
    assert panel is not None
    # It must have a top-level objectName from its .ui.
    assert panel.findChild(QObject, "scanPanel") is not None or panel.objectName() == "scanPanel"


def test_calibration_panel_instantiates(qtbot) -> None:
    """CalibrationPanelWidget exposes the calibration controls container."""
    from lightsheet.gui.panels.calibration_panel import CalibrationPanelWidget

    panel = CalibrationPanelWidget(Mock())
    qtbot.addWidget(panel)

    assert panel is not None
    assert panel.findChild(QObject, "calibrationPanel") is not None or panel.objectName() == "calibrationPanel"


# ---------------------------------------------------------------------------
# Shell composition — the thin shell composes the 8 panels into
# stackedPanels (a QStackedWidget driven by the left-rail QButtonGroup)
# and exposes them as attributes. Uses the real-construction fixture.
# ---------------------------------------------------------------------------


def test_shell_composes_panels(qtbot, request) -> None:
    """The shell instantiates and exposes all per-panel widgets."""
    from _helpers.controller_fixture import make_controller

    ctrl, _ = make_controller(qtbot, request)

    # All per-panel widgets are composed onto the shell. The panel widget
    # classes are preserved (no deletion) — each lives in its own
    # QScrollArea page in stackedPanels.
    assert ctrl.laser_panel is not None
    assert ctrl.motor_panel is not None
    assert ctrl.acquisition_panel is not None
    assert ctrl.save_panel is not None
    assert ctrl.stack_panel is not None
    assert ctrl.scan_panel is not None
    assert ctrl.calibration_panel is not None


def test_stacked_panels_has_eight_pages(qtbot, request) -> None:
    """The shell's stackedPanels holds 8 pages (one per left-rail button).

    Page order matches the left-rail button order: Motion(0), Acquire(1),
    Stack(2), Scan(3), Lasers(4), Files(5), Past(6), Calibrate(7). The
    placeholder page shipped by the .ui is removed; the Past page is a
    placeholder QWidget until the dedicated browser panel is built.
    """
    from _helpers.controller_fixture import make_controller

    ctrl, _ = make_controller(qtbot, request)
    assert ctrl.ui.stackedPanels.count() == 8


def test_stacked_page_order(qtbot, request) -> None:
    """Each stacked page hosts the panel for its left-rail index:
    Motion(0), Acquire(1), Stack(2), Scan(3), Lasers(4), Files(5),
    Past(6), Calibrate(7)."""
    from _helpers.controller_fixture import make_controller

    ctrl, _ = make_controller(qtbot, request)
    sp = ctrl.ui.stackedPanels

    # Index 0 — Motion (motor panel)
    assert sp.widget(0).findChild(QObject, "pushButton_sampleStepForward") is not None
    # Index 1 — Acquire (acquisition panel)
    assert sp.widget(1).findChild(QObject, "pushButton_acqGetSingleImage") is not None
    # Index 2 — Stack (stack panel)
    assert sp.widget(2).findChild(QObject, "pushButton_acqStartStackMode") is not None
    # Index 3 — Scan (scan panel)
    assert sp.widget(3).findChild(QObject, "checkBox_etlSync") is not None
    # Index 4 — Lasers (laser panel)
    assert sp.widget(4).findChild(QObject, "pushButton_laserOneToggle") is not None
    # Index 5 — Files (save panel)
    assert sp.widget(5).findChild(QObject, "pushButton_saveSelectDirectory") is not None
    # Index 6 — Past (placeholder QWidget; no panel-specific child yet)
    assert sp.widget(6) is not None
    # Index 7 — Calibrate (calibration panel)
    assert sp.widget(7).findChild(QObject, "pushButton_calCameraComputeFocus") is not None


def test_all_panels_wrapped_in_scroll_area(qtbot, request) -> None:
    """Each panel page (except the Past placeholder) is a QScrollArea with
    widgetResizable=True (UI-SPEC QScrollArea Wrapping Rules) so the panel
    overflows gracefully on small screens."""
    from PySide6.QtWidgets import QScrollArea

    from _helpers.controller_fixture import make_controller

    ctrl, _ = make_controller(qtbot, request)
    sp = ctrl.ui.stackedPanels

    # Pages 0-4 and 5, 7 are QScrollArea instances wrapping their panel.
    # Page 6 (Past) is a bare placeholder QWidget until the dedicated
    # browser panel is built.
    for idx in (0, 1, 2, 3, 4, 5, 7):
        page = sp.widget(idx)
        assert isinstance(page, QScrollArea), (
            f"page {idx} is not a QScrollArea (got {type(page).__name__})"
        )
        assert page.widgetResizable() is True, (
            f"page {idx} scroll area must have widgetResizable=True"
        )


def test_estop_button_in_shell(qtbot, request) -> None:
    """The E-stop button lives in the shell, NOT in any panel.

    This is the safety-critical structural assertion (AGENTS.md §2): the
    lock-free GUI-thread kill path (``updateUi_estop_pressed``) is owned by
    the shell. If the .ui split accidentally moved the E-stop button into a
    panel, the kill path would lose its single owner and the safety
    invariant would be broken.
    """
    from _helpers.controller_fixture import make_controller

    ctrl, _ = make_controller(qtbot, request)

    # The E-stop button, status label, and arm-reset button are in the shell.
    assert ctrl.findChild(QObject, "pushButton_estop") is not None
    assert ctrl.findChild(QObject, "label_estopStatus") is not None
    assert ctrl.findChild(QObject, "pushButton_armReset") is not None

    # The E-stop button is NOT in any panel — findChild on each panel must
    # return None (the panel's widget subtree does not contain it).
    panels = (
        ctrl.laser_panel,
        ctrl.motor_panel,
        ctrl.acquisition_panel,
        ctrl.save_panel,
        ctrl.stack_panel,
        ctrl.scan_panel,
        ctrl.calibration_panel,
    )
    for panel in panels:
        assert panel.findChild(QObject, "pushButton_estop") is None, (
            f"E-stop button leaked into {type(panel).__name__} — "
            "the kill path must stay in the shell (AGENTS.md §2)."
        )


def test_image_view_in_shell(qtbot, request) -> None:
    """The ImageView lives in the shell (not in any panel)."""
    from _helpers.controller_fixture import make_controller

    ctrl, _ = make_controller(qtbot, request)

    assert ctrl.findChild(QObject, "imageView") is not None
