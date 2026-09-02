"""Presentation-only controller for the focus-trajectory QDockWidget.

Mirrors ``AdaptiveDockController`` for focus telemetry. It does not hold any
HAL state — all hardware references stay in ``Controller_MainWindow``.
"""

from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDockWidget

from lightsheet.gui.coordinators.dock_utils import (
    FloatingOnlyDock,
    build_no_dbl_click_title_bar,
)
from lightsheet.gui.widgets.focus_trajectory import FocusTrajectoryWidget

if TYPE_CHECKING:
    from lightsheet.gui.shell.controller import Controller_MainWindow

logger = logging.getLogger(__name__)


class FocusDockController:
    """Build/restore/save/toggle/append/freeze operations for focus telemetry.

    The controller is constructed with a reference to the shell
    (``Controller_MainWindow``) so it can access the QMainWindow
    ``addDockWidget`` / ``saveState`` / ``restoreState`` surface and the
    mode-badge helper. It does not own lasers, motors, camera, workers, or
    the E-stop event.
    """

    def __init__(self, shell: Controller_MainWindow) -> None:
        self._shell = shell
        self._state_key = "ui/focusTrajectoryDockState"
        self._last_block = 0
        self._build_dock()

    # ------------------------------------------------------------------ #
    # Dock construction and alias attributes
    # ------------------------------------------------------------------ #

    def _build_dock(self) -> None:
        """Create the focus trajectory QDockWidget in the
        RightDockWidgetArea. Mirrors the adaptive dock pattern: a floating
        standalone window, hidden at construction, opened by the operator
        via the conditional left-rail focus button."""
        self.dock = FloatingOnlyDock("Focus Trajectory", self._shell)
        self.dock.setObjectName("dockWidget_focusTrajectory")

        title_bar = build_no_dbl_click_title_bar(
            "Focus Trajectory",
            "Close focus trajectory dock",
            self.dock,
        )
        self.dock.setTitleBarWidget(title_bar)
        self.dock.setAllowedAreas(Qt.DockWidgetArea.NoDockWidgetArea)
        self.dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable)

        self.widget = FocusTrajectoryWidget(self.dock)
        self.dock.setWidget(self.widget)
        self.plotWidget_focusTrajectory = self.widget.plotWidget_focusTrajectory
        self.label_focusTrajectoryEmpty = self.widget.label_focusTrajectoryEmpty

        self._shell.addDockWidget(
            Qt.DockWidgetArea.RightDockWidgetArea,
            self.dock,
        )
        QDockWidget.setFloating(self.dock, True)
        self.dock.resize(720, 480)
        self.dock.hide()
        self.dock.visibilityChanged.connect(self._on_dock_visibility_changed)

    # ------------------------------------------------------------------ #
    # QSettings persistence
    # ------------------------------------------------------------------ #

    def restore_state(self) -> None:
        """Restore the persisted focus dock geometry from QSettings."""
        from PySide6.QtCore import QSettings

        settings = QSettings("lightsheet", "shell")
        state = settings.value(self._state_key)
        if state is not None:
            with contextlib.suppress(TypeError, RuntimeError):
                self._shell.restoreState(state)

    def save_state(self) -> None:
        """Persist the focus dock geometry to QSettings."""
        if getattr(self._shell, "_demo_mode", False):
            return
        from PySide6.QtCore import QSettings

        settings = QSettings("lightsheet", "shell")
        settings.setValue(self._state_key, self._shell.saveState())

    # ------------------------------------------------------------------ #
    # Rail / enable toggle handlers
    # ------------------------------------------------------------------ #

    def on_focus_enabled_toggled(self, enabled: bool) -> None:
        """Show/hide the conditional focus rail button when the focus
        enable checkbox is toggled. The dock itself does NOT open
        automatically — the operator opens it via the rail button so the
        focus trajectory plot is opt-in even when focus compensation is on.
        When disabled, the dock + rail button are hidden entirely."""
        self._shell.ui.toolButton_railFocus.setVisible(enabled)
        if not enabled:
            self.dock.hide()
            self._shell.ui.toolButton_railFocus.setChecked(False)

    def on_rail_focus_toggled(self, checked: bool) -> None:
        """Toggle the focus trajectory dock visibility from the
        conditional rail button. The dock opens as a standalone floating
        window (never docked into the main GUI). Historical plot data is
        preserved across close/reopen so the operator can review a
        finished acquisition after closing the dock; data is only
        cleared when a new stack acquisition starts."""
        if checked:
            self.dock.show()
            QDockWidget.setFloating(self.dock, True)
            if not self.widget.has_data():
                self.widget.set_empty()
            else:
                self.widget.show_plot()
        else:
            self.dock.hide()

    def _on_dock_visibility_changed(self, visible: bool) -> None:
        """Keep the rail toggle's checked state in sync with the dock's
        actual visibility. Fires when the user closes the dock via its
        own close button — the rail button unchecks so the two stay
        consistent. Guarded against feedback loops with blockSignals."""
        btn = self._shell.ui.toolButton_railFocus
        if btn.isChecked() != visible:
            btn.blockSignals(True)
            btn.setChecked(visible)
            btn.blockSignals(False)

    # ------------------------------------------------------------------ #
    # Trajectory append / freeze
    # ------------------------------------------------------------------ #

    def append_sample(
        self,
        block_idx: int,
        stage_pos_mm: float,
        feedforward_camera_pos_mm: float,
        residual_mm: float,
        applied_camera_pos_mm: float,
    ) -> None:
        """Append one per-block sample to the focus trajectory plot.

        The worker emits ``sig_focus_trajectory`` (a queued ``Signal``);
        this method is called from the GUI-thread slot on the shell. The
        worker NEVER calls pyqtgraph directly. The X-axis is hardcoded to
        the block index ("Block") in this phase.
        """
        self._last_block = block_idx
        x_axis_value = float(block_idx)
        self.widget.append_sample(
            block_idx=block_idx,
            stage_pos_mm=stage_pos_mm,
            camera_pos_mm=applied_camera_pos_mm,
            residual_mm=residual_mm,
            x_axis_value=x_axis_value,
        )

    def freeze(self) -> None:
        """Freeze the focus trajectory plot and set the badge to
        FOCUS ABORTED. Called from the E-stop handler AFTER the
        synchronous laser-off kill path completes."""
        self.widget.freeze()
        block = int(self._last_block)
        total = int(getattr(self._shell, "number_of_planes", 0))
        self._shell.focus_mode_started = False
        self._shell._update_mode_badge("FOCUS", "ABORTED", plane=block, total=total)
