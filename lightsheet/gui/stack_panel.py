"""StackPanelWidget — per-panel widget/controller for stack acquisition setup.

Owns the stack updateUi_* slots grouped by concern: stack starting/ending
point selection and number-of-planes calculation. Reads
``self.ui.<objectName>`` for its widgets and ``self._shell.motors`` /
``self._shell.stack_*`` for shell-owned state. Emits through
``self._shell.sig_*``.

The boundary-set boolean migrates from checkboxes to shell flags
``self._shell.stack_first_plane_set`` / ``stack_last_plane_set``. The Set
button populates the spinbox from the motor position; the operator can also
type a value directly. Manual entry validates against the motor travel
limits and rejects with a beep on out-of-range (the worker's per-plane
ValueError catch stays as the physical-safety backstop).
"""

from __future__ import annotations

import typing

import numpy as np
from PySide6.QtWidgets import QWidget

from lightsheet.gui.acquisition_table_manager import AcquisitionTableManager
from lightsheet.gui.ui_stack_panel import Ui_StackPanel

if typing.TYPE_CHECKING:
    from lightsheet.gui.controller import Controller_MainWindow


class StackPanelWidget(QWidget):
    """Stack acquisition setup panel — owns stack starting/ending point
    and number-of-planes calculation slots."""

    def __init__(self, shell: "Controller_MainWindow") -> None:
        super().__init__()
        self._shell = shell
        self.ui = Ui_StackPanel()
        self.ui.setupUi(self)
        # Compose the AcquisitionTableManager (a QTableWidget queue of
        # z-stacks by position/range/step) into the Acquisition Queue
        # group box. The single-stack Set-button workflow above stays
        # alongside the table for one-off stacks; the table is for
        # multi-stack sequences without re-driving the stage.
        self.table_manager = AcquisitionTableManager(shell)
        self.ui.verticalLayout_acquisitionQueue.addWidget(self.table_manager)
        # Seed the spinbox range from the motor travel limits as a soft
        # widget-layer block. The spinbox range is widened so an
        # out-of-range entry is accepted by the widget and then rejected
        # by the editingFinished validation (which mirrors
        # ZaberMotor.move_absolute_position's reject-and-beep). The
        # worker's per-plane ValueError catch is the physical-safety
        # backstop if the soft block slips.
        self._seed_spinbox_ranges()

    def _seed_spinbox_ranges(self) -> None:
        """Seed the first/last plane spinbox ranges from the motor travel
        limits. The range is widened beyond the limits so an out-of-range
        value is accepted by the spinbox (and then rejected by the
        editingFinished validation with a beep)."""
        motors = getattr(self._shell, "motors", None)
        if motors is None:
            # During shell __init__ the motors may not be assigned yet
            # (hardware_init runs on a 100ms timer). Use a permissive
            # default; the editingFinished validation reads the live
            # motor limits at edit time. hardware_init re-calls this.
            return
        try:
            low = float(motors.horizontal.get_limit_low("\u03bcm"))
            high = float(motors.horizontal.get_limit_high("\u03bcm"))
        except (TypeError, ValueError, AttributeError):
            # A Mock shell (structural tests) returns non-numeric values.
            return
        # Widen the range so the spinbox accepts a value just past the
        # limits (the editingFinished handler rejects it with a beep).
        margin = max(1.0, (high - low) * 0.1)
        self.ui.doubleSpinBox_acqFirstPlane.setRange(low - margin, high + margin)
        self.ui.doubleSpinBox_acqLastPlane.setRange(low - margin, high + margin)

    def _rerender_stack_units(self) -> None:
        """Re-render the Stack plane spinboxes + suffix on a unit change.

        The stack plane positions (doubleSpinBox_acqFirstPlane /
        doubleSpinBox_acqLastPlane) and the plane step
        (doubleSpinBox_acqPlaneStepSize) are stored internally in
        micrometres (the worker + the motor HAL operate in μm regardless of
        the display unit). When the display unit changes, the spinbox
        suffix is updated and the displayed value is converted between μm
        (internal) and the display unit (μm or mm):

        - μm display: value shown as-is, suffix " μm".
        - mm display: value ÷ 1000, suffix " mm".

        The internal ``stack_starting_plane`` / ``stack_ending_plane``
        shell flags stay in μm — only the displayed value + suffix change.
        The ``number_of_planes`` computation reads the spinbox values via
        ``updateUi_set_number_of_planes`` which uses the spinbox values
        directly, so the conversion must be consistent: the step spinbox
        is also converted so the ratio (end-start)/step stays the same.
        """
        unit = self._shell.ui.comboBox_units.currentText()
        sb_first = self.ui.doubleSpinBox_acqFirstPlane
        sb_last = self.ui.doubleSpinBox_acqLastPlane
        sb_step = self.ui.doubleSpinBox_acqPlaneStepSize

        # The spinbox values are in the CURRENT display unit (tracked by
        # the suffix). Convert to the NEW display unit and update the
        # suffix. Block signals during the conversion so the valueChanged
        # signal does not re-trigger updateUi_set_number_of_planes
        # mid-conversion.
        if unit == "mm":
            decimals = 5
        else:  # μm (the default)
            decimals = 2

        for sb in (sb_first, sb_last, sb_step):
            sb.blockSignals(True)
            current_suffix = sb.suffix().strip()
            current_value = sb.value()
            if current_suffix == unit or not current_suffix:
                # No conversion needed (same unit or initial render where
                # the value is already in the target unit).
                new_value = current_value
            elif current_suffix == "\u03bcm" and unit == "mm":
                # μm → mm: divide by 1000.
                new_value = current_value / 1000.0
            elif current_suffix == "mm" and unit == "\u03bcm":
                # mm → μm: multiply by 1000.
                new_value = current_value * 1000.0
            else:
                new_value = current_value
            sb.setValue(new_value)
            sb.setSuffix(f" {unit}")
            sb.setDecimals(decimals)
            sb.blockSignals(False)

        # Re-render the summary so the unit label in the summary text
        # matches the display unit.
        self._render_stack_plan_summary()

    def updateUi_set_stack_mode_starting_point(self) -> None:
        """Defines the starting point where the first plane of the stack volume will be recorded"""  # noqa: E501
        pos = self._shell.motors.horizontal.get_position(
            "\u03bcm"
        )  # Units in micro-meters, because plane step is in micro-meters
        self._shell.stack_starting_plane = pos
        self.ui.doubleSpinBox_acqFirstPlane.setValue(pos)
        self._shell.stack_first_plane_set = True
        self.updateUi_set_number_of_planes()

    def updateUi_set_stack_mode_ending_point(self) -> None:
        """Defines the ending point of the recorded stack volume"""
        pos = self._shell.motors.horizontal.get_position(
            "\u03bcm"
        )  # Units in micro-meters, because plane step is in micro-meters
        self._shell.stack_ending_plane = pos
        self.ui.doubleSpinBox_acqLastPlane.setValue(pos)
        self._shell.stack_last_plane_set = True
        self.updateUi_set_number_of_planes()

    def _on_first_plane_edited(self) -> None:
        """editingFinished on doubleSpinBox_acqFirstPlane: validate the
        typed value against the motor travel limits. In range → update
        the shell flag + starting plane. Out of range → beep + message,
        revert, do NOT move the motor (the worker's per-plane ValueError
        catch is the physical-safety backstop)."""
        value = self.ui.doubleSpinBox_acqFirstPlane.value()
        low = self._shell.motors.horizontal.get_limit_low("\u03bcm")
        high = self._shell.motors.horizontal.get_limit_high("\u03bcm")
        if value < low or value > high:
            self._shell.sig_beep.emit()
            self._shell.sig_message.emit(
                f"Plane {value:.2f} \u03bcm is outside the stage travel limits "
                f"({low:.2f}\u2013{high:.2f} \u03bcm). Not applied \u2014 motor "
                "not moved. Adjust the value or drive the stage to a valid "
                "position."
            )
            # Revert to the last-known starting plane (or the low limit).
            revert = self._shell.stack_starting_plane
            if revert is None or revert < low or revert > high:
                revert = low
            self.ui.doubleSpinBox_acqFirstPlane.setValue(float(revert))
            return
        self._shell.stack_starting_plane = value
        self._shell.stack_first_plane_set = True
        self.updateUi_set_number_of_planes()

    def _on_last_plane_edited(self) -> None:
        """editingFinished on doubleSpinBox_acqLastPlane: same validation
        as the first-plane handler, against the ending plane."""
        value = self.ui.doubleSpinBox_acqLastPlane.value()
        low = self._shell.motors.horizontal.get_limit_low("\u03bcm")
        high = self._shell.motors.horizontal.get_limit_high("\u03bcm")
        if value < low or value > high:
            self._shell.sig_beep.emit()
            self._shell.sig_message.emit(
                f"Plane {value:.2f} \u03bcm is outside the stage travel limits "
                f"({low:.2f}\u2013{high:.2f} \u03bcm). Not applied \u2014 motor "
                "not moved. Adjust the value or drive the stage to a valid "
                "position."
            )
            revert = self._shell.stack_ending_plane
            if revert is None or revert < low or revert > high:
                revert = high
            self.ui.doubleSpinBox_acqLastPlane.setValue(float(revert))
            return
        self._shell.stack_ending_plane = value
        self._shell.stack_last_plane_set = True
        self.updateUi_set_number_of_planes()

    def _display_to_um(self, value: float) -> float:
        """Convert a spinbox value from the current display unit to
        micrometres (the internal unit the worker + motor HAL use)."""
        unit = self._shell.ui.comboBox_units.currentText()
        if unit == "mm":
            return value * 1000.0
        return value  # μm (no conversion needed)

    def updateUi_set_number_of_planes(self) -> None:
        """Calculates the number of planes that will be saved in the stack acquisition"""  # noqa: E501
        if self.ui.doubleSpinBox_acqPlaneStepSize.value() != 0:
            if (
                self._shell.stack_first_plane_set
                and self._shell.stack_last_plane_set
            ):
                # Read the boundary values from the spinboxes (the
                # operator may have typed them directly) and convert to
                # μm (the internal unit the worker + motor HAL use).
                self._shell.stack_starting_plane = self._display_to_um(
                    self.ui.doubleSpinBox_acqFirstPlane.value()
                )
                self._shell.stack_ending_plane = self._display_to_um(
                    self.ui.doubleSpinBox_acqLastPlane.value()
                )
                # The step spinbox is also in the display unit — convert
                # to μm for the ratio so the number-of-planes computation
                # is unit-independent.
                step_um = self._display_to_um(
                    self.ui.doubleSpinBox_acqPlaneStepSize.value()
                )
                self._shell.number_of_planes = int(np.ceil(
                    abs(
                        (self._shell.stack_ending_plane - self._shell.stack_starting_plane)  # noqa: E501
                        / step_um
                    )
                ))
                self._shell.number_of_planes += 1  # Takes into account the initial plane  # noqa: E501
                self.ui.label_acqNumberOfPlanes.setText(str(self._shell.number_of_planes))
        else:
            self._shell.sig_message.emit("Set a non-zero value to plane step")
        # Always re-render the summary so the operator sees the current
        # plan state (empty / partial / full).
        self._render_stack_plan_summary()

    def _render_stack_plan_summary(self) -> None:
        """Render the read-only stack plan summary: start/end/step/#planes/
        est. time/est. size. Handles empty and partial states."""
        first_set = bool(getattr(self._shell, "stack_first_plane_set", False))
        last_set = bool(getattr(self._shell, "stack_last_plane_set", False))
        step = self.ui.doubleSpinBox_acqPlaneStepSize.value()
        unit = self._shell.ui.comboBox_units.currentText()

        if not first_set and not last_set:
            self.ui.label_stackPlanSummary.setText(
                "No stack configured. Drive the stage to the start position "
                "and press Set, or type start/end positions and a step."
            )
            return

        if first_set != last_set:
            # Only one boundary is set — partial state.
            self.ui.label_stackPlanSummary.setText(
                "Partial stack plan: one boundary is set. "
                "Set the other boundary to compute the plan."
            )
            return

        # Both boundaries set — full plan.
        start = self.ui.doubleSpinBox_acqFirstPlane.value()
        end = self.ui.doubleSpinBox_acqLastPlane.value()
        n_planes = int(getattr(self._shell, "number_of_planes", 0))
        # Estimated time: per-plane time × #planes. The per-plane time is
        # advisory — read from the camera exposure if available, else a
        # sensible default. Estimates are advisory (the actual acquisition
        # time depends on real hardware behavior).
        per_plane_s = self._estimate_per_plane_time()
        est_time_s = n_planes * per_plane_s
        est_size_mb = self._estimate_stack_size_mb(n_planes)
        mm, ss = divmod(int(est_time_s), 60)
        self.ui.label_stackPlanSummary.setText(
            f"Start: {start:.2f} {unit} | End: {end:.2f} {unit} | "
            f"Step: {step:.2f} {unit} | Planes: {n_planes} | "
            f"Est. time: {mm}:{ss:02d} | Est. size: {est_size_mb:.1f} MB"
        )

    def _estimate_per_plane_time(self) -> float:
        """Advisory per-plane acquisition time in seconds. Falls back to a
        sensible default when the camera/exposure is unavailable."""
        try:
            exposure = float(self._shell.acquisition_panel.ui
                             .doubleSpinBox_cameraExposureTime.value())
            # Exposure is in ms; add overhead for galvo/ETL scan + motor
            # settle. 1.5x exposure is a rough advisory factor.
            return exposure / 1000.0 * 1.5
        except (AttributeError, ValueError, TypeError):
            return 0.5

    def _estimate_stack_size_mb(self, n_planes: int) -> float:
        """Advisory stack size in MB. Uses the camera frame dims × 2 bytes
        (uint16) when available; falls back to a 2000×2000 default."""
        try:
            rows = int(getattr(self._shell.camera, "rows", 2000))
            cols = int(getattr(self._shell.camera, "columns", 2000))
        except (AttributeError, TypeError, ValueError):
            rows, cols = 2000, 2000
        bytes_per_frame = rows * cols * 2
        return (n_planes * bytes_per_frame) / (1024.0 * 1024.0)
