"""Presentation-only controller for the adaptive-trajectory QDockWidget.

This module owns the adaptive trajectory dock lifecycle, persistence, and
plot updates. It does not hold any HAL state — all hardware references stay
in ``Controller_MainWindow``.
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
from lightsheet.gui.widgets.adaptive_trajectory import AdaptiveTrajectoryWidget

if TYPE_CHECKING:
    from lightsheet.gui.shell.controller import Controller_MainWindow

logger = logging.getLogger(__name__)


class AdaptiveDockController:
    """Build/restore/save/toggle/append/freeze operations for adaptive telemetry.

    The controller is constructed with a reference to the shell
    (``Controller_MainWindow``) so it can access the QMainWindow
    ``addDockWidget`` / ``saveState`` / ``restoreState`` surface and the
    mode-badge helper. It does not own lasers, motors, camera, workers, or
    the E-stop event.
    """

    def __init__(self, shell: Controller_MainWindow) -> None:
        self._shell = shell
        self._state_key = "ui/adaptiveTrajectoryDockState"
        self._last_plane = 0
        self._build_dock()

    # ------------------------------------------------------------------ #
    # Dock construction and alias attributes
    # ------------------------------------------------------------------ #

    def _build_dock(self) -> None:
        """Create the adaptive trajectory QDockWidget in the
        RightDockWidgetArea. The dock is movable + floatable (operator
        can drag it to a 2nd monitor) and hidden initially — shown when
        adaptive is enabled. The plot widget is GUI-thread-only."""
        self.dock = FloatingOnlyDock("Adaptive Trajectory", self._shell)
        self.dock.setObjectName("dockWidget_adaptiveTrajectory")

        title_bar = build_no_dbl_click_title_bar(
            "Adaptive Trajectory",
            "Close adaptive trajectory dock",
            self.dock,
        )
        self.dock.setTitleBarWidget(title_bar)
        # No allowed dock areas — the trajectory plot opens as a
        # standalone floating window, never docked into the main GUI.
        self.dock.setAllowedAreas(Qt.DockWidgetArea.NoDockWidgetArea)
        # Closable so the operator can dismiss it and re-open via the rail
        # button; not movable/floatable (the subclass keeps it floating).
        self.dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable)

        self.widget = AdaptiveTrajectoryWidget(self.dock)
        self.dock.setWidget(self.widget)
        # Expose the plot + label on the controller for shell alias wiring
        # and test reachability.
        self.plotWidget_adaptiveTrajectory = self.widget.plotWidget_adaptiveTrajectory
        self.label_adaptiveTrajectoryEmpty = self.widget.label_adaptiveTrajectoryEmpty

        # Register as a dock widget, then float it once via the base class
        # (the subclass's setFloating is a no-op to prevent double-click
        # un-floating). NoDockWidgetArea means it can never re-dock.
        self._shell.addDockWidget(
            Qt.DockWidgetArea.RightDockWidgetArea,
            self.dock,
        )
        QDockWidget.setFloating(self.dock, True)
        # Sensible default size for the floating trajectory window so it is
        # usable on first spawn (the operator can resize afterwards; Qt
        # persists the size).
        self.dock.resize(720, 480)
        # Hidden until the operator opens it via the rail button. It does
        # NOT open automatically when adaptive is enabled.
        self.dock.hide()
        # Keep the rail toggle in sync with dock visibility so closing the
        # dock via its close button unchecks the rail button.
        self.dock.visibilityChanged.connect(self._on_dock_visibility_changed)

    # ------------------------------------------------------------------ #
    # QSettings persistence
    # ------------------------------------------------------------------ #

    def restore_state(self) -> None:
        """Restore the persisted dock geometry from QSettings.

        No-op if no saved state exists (first run). Uses QSettings (not
        config.ini) so demo tests do not write config.ini.
        """
        from PySide6.QtCore import QSettings

        settings = QSettings("lightsheet", "shell")
        state = settings.value(self._state_key)
        if state is not None:
            with contextlib.suppress(TypeError, RuntimeError):
                self._shell.restoreState(state)

    def save_state(self) -> None:
        """Persist the dock geometry to QSettings.

        Skipped in demo mode so the test suite does not persist dock state
        across test runs.
        """
        if getattr(self._shell, "_demo_mode", False):
            return
        from PySide6.QtCore import QSettings

        settings = QSettings("lightsheet", "shell")
        settings.setValue(self._state_key, self._shell.saveState())

    # ------------------------------------------------------------------ #
    # Rail / enable toggle handlers
    # ------------------------------------------------------------------ #

    def on_adaptive_enabled_toggled(self, enabled: bool) -> None:
        """Show/hide the conditional rail button when the adaptive enable
        checkbox is toggled. The dock itself does NOT open automatically —
        the operator opens it via the rail button so the trajectory plot is
        opt-in even when adaptive mode is on."""
        self._shell.ui.toolButton_railAdaptive.setVisible(enabled)
        if not enabled:
            self.dock.hide()
            self._shell.ui.toolButton_railAdaptive.setChecked(False)

    def on_rail_adaptive_toggled(self, checked: bool) -> None:
        """Toggle the trajectory dock visibility from the conditional rail
        button. The dock opens as a standalone floating window (never
        docked into the main GUI). Historical plot data is preserved across
        close/reopen so the operator can review a finished acquisition after
        closing the dock; data is only cleared when a new stack acquisition
        starts."""
        if checked:
            # Show first, then float via the base class (the subclass's
            # setFloating is a no-op to prevent double-click un-floating).
            # setFloating(True) on a visible dock reliably opens it as a
            # standalone floating window; on a hidden dock Qt may keep it
            # docked until the next show.
            self.dock.show()
            QDockWidget.setFloating(self.dock, True)
            # Only show the empty state if there's no existing data to
            # restore (first open, or after a reset). If the widget already
            # has data, keep it visible so the operator can review it.
            if not self.widget.has_data():
                self.widget.set_empty()
            else:
                self.widget.show_plot()
        else:
            self.dock.hide()

    def _on_dock_visibility_changed(self, visible: bool) -> None:
        """Keep the rail toggle's checked state in sync with the dock's
        actual visibility. Fires when the user closes the dock via its own
        close button — the rail button unchecks so the two stay consistent.
        Guarded against feedback loops with blockSignals."""
        btn = self._shell.ui.toolButton_railAdaptive
        if btn.isChecked() != visible:
            btn.blockSignals(True)
            btn.setChecked(visible)
            btn.blockSignals(False)

    # ------------------------------------------------------------------ #
    # Trajectory append / freeze
    # ------------------------------------------------------------------ #

    def append_sample(
        self,
        plane_idx: int,
        intensity: float,
        exposure_s: float,
        power1_mw: float,
        power2_mw: float,
        control_variable_active: str,
        reacquired: bool,
        power_fallback: bool,
    ) -> None:
        """Append one per-plane sample to the adaptive trajectory plot.

        The worker emits a queued Signal; this method is called from the
        GUI-thread slot on the shell. The worker NEVER calls pyqtgraph
        directly. Samples are always appended so the plot has the full
        history when the operator opens the dock mid-run — the widget
        handles its own visibility.
        """
        self._last_plane = plane_idx
        self.widget.append_sample(
            plane_idx=plane_idx,
            intensity=intensity,
            exposure_s=exposure_s,
            power1_mw=power1_mw,
            power2_mw=power2_mw,
            control_variable_active=control_variable_active,
            reacquired=reacquired,
            power_fallback=power_fallback,
        )

    def freeze(self) -> None:
        """Freeze the trajectory plot and set the badge to ADAPTIVE ABORTED.

        Called from the E-stop handler AFTER the synchronous laser-off kill
        path completes."""
        self.widget.freeze()
        plane = int(self._last_plane)
        total = int(getattr(self._shell, "number_of_planes", 0))
        self._shell._update_mode_badge("ADAPTIVE", "ABORTED", plane=plane, total=total)
