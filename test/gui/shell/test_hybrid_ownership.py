"""Hybrid widget-ownership regression test.

Asserts the shell's ``vars(panel.ui)`` merge loop is trimmed to shell-owned
widgets only, so panel-internal widgets no longer leak onto ``self.ui``.
Each panel's slots reach their own widgets via ``self.ui.<name>``
(panel-local) and cross-panel reads go through
``self._shell.<panel>.ui.<name>``. The shell-owned widgets (E-stop toolbar,
status bar, message log, left-rail navigation primitives, controlsPane)
stay on ``self.ui`` so the lock-free GUI-thread E-stop kill path
(AGENTS.md §2) is never stranded by a panel-ownership change.

Runs headless on Mac via ``QT_QPA_PLATFORM=offscreen`` (set by conftest).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from lightsheet.gui.shell.controller import Controller_MainWindow

pytest.importorskip("PySide6")


def test_shell_owned_widgets_stay_on_ui(controller: Controller_MainWindow) -> None:
    """Shell-owned widgets stay accessible via ``controller.ui`` after the
    merge-loop trim (E-stop invariant + status bar + message log +
    left-rail navigation)."""
    ctrl = controller

    # E-stop toolbar widgets — the safety-critical invariant.
    assert hasattr(ctrl.ui, "pushButton_estop")
    assert hasattr(ctrl.ui, "pushButton_armReset")
    assert hasattr(ctrl.ui, "label_estopStatus")
    assert hasattr(ctrl.ui, "toolBar_estop")

    # Status bar widgets.
    assert hasattr(ctrl.ui, "statusbar")
    assert hasattr(ctrl.ui, "statusBar_label")
    assert hasattr(ctrl.ui, "statusBar_progress")

    # Message log.
    assert hasattr(ctrl.ui, "plainTextEdit_messageLog")

    # Left-rail navigation primitives (shell-owned, replace the old
    # units selector + tabbed shell).
    assert hasattr(ctrl.ui, "stackedPanels")
    assert hasattr(ctrl.ui, "leftRail")
    assert hasattr(ctrl.ui, "toolButton_railMotion")

    # Controls pane / splitter / image view.
    assert hasattr(ctrl.ui, "splitter")
    assert hasattr(ctrl.ui, "controlsPane")
    assert hasattr(ctrl.ui, "imagesPane")
    assert hasattr(ctrl.ui, "imageView")


def test_panel_internal_widget_not_on_shell_ui(
    controller: Controller_MainWindow,
) -> None:
    """A panel-internal widget is NOT accessible via ``controller.ui`` after
    the merge-loop trim — it lives on its owning panel's ``ui`` only."""
    ctrl = controller

    # doubleSpinBox_acqFirstPlane is a stack_panel-internal widget.
    assert not hasattr(ctrl.ui, "doubleSpinBox_acqFirstPlane"), (
        "panel-internal widget leaked onto controller.ui — the merge loop "
        "must be trimmed to shell-owned widgets only."
    )
    # It IS accessible via the panel-qualified path.
    assert hasattr(ctrl.stack_panel.ui, "doubleSpinBox_acqFirstPlane")


def test_panel_internal_widgets_not_on_shell_ui_sample(
    controller: Controller_MainWindow,
) -> None:
    """Several panel-internal widgets across panels are NOT on controller.ui."""
    ctrl = controller

    # Sample one widget from each panel.
    panel_internal = {
        "laser_panel": "pushButton_laserOneToggle",
        "motor_panel": "pushButton_sampleStepForward",
        "acquisition_panel": "pushButton_acqGetSingleImage",
        "stack_panel": "doubleSpinBox_acqFirstPlane",
        "scan_panel": "checkBox_etlSync",
        "save_panel": "lineEdit_saveDirectory",
        "calibration_panel": "pushButton_calCameraComputeFocus",
    }
    for _panel, name in panel_internal.items():
        assert not hasattr(ctrl.ui, name), (
            f"panel-internal widget {name!r} leaked onto controller.ui"
        )


def test_shell_owned_objectnames_whitelist_exists() -> None:
    """The controller module defines a SHELL_OWNED_OBJECTNAMES whitelist
    driving the trimmed merge loop."""
    from lightsheet.gui.shell import controller

    assert hasattr(controller, "SHELL_OWNED_OBJECTNAMES")
    whitelist = controller.SHELL_OWNED_OBJECTNAMES
    # The E-stop widgets MUST be whitelisted so the kill path's widget
    # references never strand.
    for name in (
        "pushButton_estop",
        "pushButton_armReset",
        "label_estopStatus",
        "toolBar_estop",
        "plainTextEdit_messageLog",
        "stackedPanels",
        "leftRail",
        "buttonGroup_leftRail",
        "action_followSystemTheme",
        "statusbar",
        "splitter",
        "controlsPane",
        "imagesPane",
        "imageView",
    ):
        assert name in whitelist, f"{name!r} must be in SHELL_OWNED_OBJECTNAMES"
    # The removed entries must NOT be in the whitelist.
    for removed in ("comboBox_units", "units_label", "tabControls"):
        assert removed not in whitelist, (
            f"{removed!r} must be removed from SHELL_OWNED_OBJECTNAMES "
            "after the shell re-architecture"
        )


def test_merge_loop_only_sets_shell_owned_widgets(
    controller: Controller_MainWindow,
) -> None:
    """The merge loop only sets shell-owned widgets onto ``self.ui`` — no
    panel-internal widget leaks. Reconstruct the merge by iterating each
    panel's ``vars(panel.ui)`` and asserting every attr that would land on
    ``self.ui`` is in SHELL_OWNED_OBJECTNAMES."""
    from lightsheet.gui.shell import controller as shell_controller

    ctrl = controller
    whitelist = shell_controller.SHELL_OWNED_OBJECTNAMES

    panels = (
        ctrl.laser_panel,
        ctrl.motor_panel,
        ctrl.acquisition_panel,
        ctrl.stack_panel,
        ctrl.scan_panel,
        ctrl.save_panel,
        ctrl.calibration_panel,
    )
    leaked = []
    for panel in panels:
        for attr_name in vars(panel.ui):
            if attr_name.startswith("_"):
                continue
            if hasattr(ctrl.ui, attr_name) and attr_name not in whitelist:
                # A panel-internal widget that landed on self.ui but is not
                # whitelisted is a leak. (Shell-owned widgets from
                # Ui_Shell.setupUi are also on self.ui but are in the
                # whitelist.)
                leaked.append((type(panel).__name__, attr_name))
    assert not leaked, (
        f"merge loop leaked panel-internal widgets onto self.ui: {leaked}"
    )


def test_estop_kill_path_unchanged() -> None:
    """The E-stop kill path (updateUi_estop_pressed) still iterates
    self.lasers and calls laser.off() synchronously — unchanged by the
    merge-loop trim (AGENTS.md §2)."""
    import inspect

    from lightsheet.gui.shell.controller import Controller_MainWindow

    src = inspect.getsource(Controller_MainWindow.updateUi_estop_pressed)
    assert "self.lasers" in src
    assert ".off()" in src
    # The kill loop itself must stay synchronous (no QThread spawn, no
    # queue.put). The post-kill refresh may be deferred via
    # QTimer.singleShot(0, ...) — that is not part of the kill loop.
    assert "QThread(" not in src
    assert "queue.put" not in src
    assert "ThreadPoolExecutor" not in src
