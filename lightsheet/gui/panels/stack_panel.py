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

from lightsheet.gui.panels.acquisition_table_manager import AcquisitionTableManager
from lightsheet.gui.panels.ui_stack_panel import Ui_StackPanel
from lightsheet.gui.widgets.field_spec import FIELD_SPECS

if typing.TYPE_CHECKING:
    from lightsheet.gui.shell.controller import Controller_MainWindow


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
        # Apply the declarative FieldSpec policy table AFTER
        # _seed_spinbox_ranges so the spec's soft min/max are the final
        # widget-layer block. The editingFinished validation and the HAL
        # motor travel-limit validator stay as the safety backstops.
        for obj_name, spec in FIELD_SPECS.items():
            w = getattr(self.ui, obj_name, None)
            if w is not None and hasattr(w, "applySpec"):
                w.applySpec(spec)

    def _seed_spinbox_ranges(self) -> None:
        """Seed the first/last plane spinbox ranges from the motor travel
        limits. The spinbox displays in millimetres (the FieldSpec unit for
        acqFirstPlane/acqLastPlane); the range is widened beyond the limits
        so an out-of-range value is accepted by the spinbox (and then
        rejected by the editingFinished validation with a beep). The
        internal ``stack_starting_plane``/``stack_ending_plane`` stay in
        micrometres (the worker + motor HAL unit) — the mm→µm conversion
        happens in ``_position_display_to_um``."""
        motors = getattr(self._shell, "motors", None)
        if motors is None:
            # During shell __init__ the motors may not be assigned yet
            # (hardware_init runs on a 100ms timer). Use a permissive
            # default; the editingFinished validation reads the live
            # motor limits at edit time. hardware_init re-calls this.
            return
        try:
            low = float(motors.horizontal.get_limit_low("mm"))
            high = float(motors.horizontal.get_limit_high("mm"))
        except (TypeError, ValueError, AttributeError):
            # A Mock shell (structural tests) returns non-numeric values.
            return
        # Widen the range so the spinbox accepts a value just past the
        # limits (the editingFinished handler rejects it with a beep).
        margin = max(0.001, (high - low) * 0.1)
        self.ui.doubleSpinBox_acqFirstPlane.setRange(low - margin, high + margin)
        self.ui.doubleSpinBox_acqLastPlane.setRange(low - margin, high + margin)

    def _rerender_stack_units(self) -> None:
        """No-op retained for backward compatibility.

        The global units toggle is gone — stack plane positions and the
        plane step are displayed in micrometres (the fixed stack-display
        unit; the worker + motor HAL operate in µm regardless). Per-field
        suffix/decimals are applied via FieldSpec in a later plan. This
        method is kept as a no-op so existing call sites do not break
        during the intermediate state.
        """
        return

    def updateUi_set_stack_mode_starting_point(self) -> None:
        """Defines the starting point where the first plane of the stack volume will be recorded"""  # noqa: E501
        # The motor HAL reports position in micrometres; the internal
        # stack_starting_plane stays in µm (the worker + motor HAL unit).
        # The spinbox displays in mm (FieldSpec unit), so convert µm→mm
        # for setValue only.
        pos_um = self._shell.motors.horizontal.get_position("\u03bcm")
        self._shell.stack_starting_plane = pos_um
        self.ui.doubleSpinBox_acqFirstPlane.setValue(pos_um / 1000.0)
        self._shell.stack_first_plane_set = True
        self.updateUi_set_number_of_planes()

    def updateUi_set_stack_mode_ending_point(self) -> None:
        """Defines the ending point of the recorded stack volume"""
        pos_um = self._shell.motors.horizontal.get_position("\u03bcm")
        self._shell.stack_ending_plane = pos_um
        self.ui.doubleSpinBox_acqLastPlane.setValue(pos_um / 1000.0)
        self._shell.stack_last_plane_set = True
        self.updateUi_set_number_of_planes()

    def _on_first_plane_edited(self) -> None:
        """editingFinished on doubleSpinBox_acqFirstPlane: validate the
        typed value against the motor travel limits. The spinbox displays
        in mm; the motor limits are read in µm and the typed mm value is
        converted to µm for the comparison + storage (safety-critical:
        stack_starting_plane MUST stay µm). In range → update the shell
        flag + starting plane. Out of range → beep + message, revert, do
        NOT move the motor (the worker's per-plane ValueError catch is the
        physical-safety backstop)."""
        motors = getattr(self._shell, "motors", None)
        if motors is None:
            # hardware_init hasn't run yet (100ms single-shot timer) —
            # nothing to validate against. _seed_spinbox_ranges documents
            # the same race.
            return
        value_mm = self.ui.doubleSpinBox_acqFirstPlane.value()
        value_um = value_mm * 1000.0
        low = motors.horizontal.get_limit_low("\u03bcm")
        high = motors.horizontal.get_limit_high("\u03bcm")
        if value_um < low or value_um > high:
            self._shell.sig_beep.emit()
            self._shell.sig_message.emit(
                f"Plane {value_mm:.3f} mm is outside the stage travel limits "
                f"({low / 1000.0:.3f}\u2013{high / 1000.0:.3f} mm). Not applied "
                "\u2014 motor not moved. Adjust the value or drive the stage "
                "to a valid position."
            )
            # Revert to the last-known starting plane (µm) or the low
            # limit, converted back to mm for display.
            revert_um = self._shell.stack_starting_plane
            if revert_um is None or revert_um < low or revert_um > high:
                revert_um = low
            self.ui.doubleSpinBox_acqFirstPlane.setValue(revert_um / 1000.0)
            return
        # Safety-critical: stack_starting_plane stays µm (the worker +
        # motor HAL unit) — store the µm-converted value, NOT the mm
        # display value.
        self._shell.stack_starting_plane = value_um
        self._shell.stack_first_plane_set = True
        self.updateUi_set_number_of_planes()

    def _on_last_plane_edited(self) -> None:
        """editingFinished on doubleSpinBox_acqLastPlane: same validation
        as the first-plane handler, against the ending plane. The spinbox
        displays in mm; stack_ending_plane stays µm (safety-critical)."""
        motors = getattr(self._shell, "motors", None)
        if motors is None:
            # hardware_init hasn't run yet — nothing to validate against.
            return
        value_mm = self.ui.doubleSpinBox_acqLastPlane.value()
        value_um = value_mm * 1000.0
        low = motors.horizontal.get_limit_low("\u03bcm")
        high = motors.horizontal.get_limit_high("\u03bcm")
        if value_um < low or value_um > high:
            self._shell.sig_beep.emit()
            self._shell.sig_message.emit(
                f"Plane {value_mm:.3f} mm is outside the stage travel limits "
                f"({low / 1000.0:.3f}\u2013{high / 1000.0:.3f} mm). Not applied "
                "\u2014 motor not moved. Adjust the value or drive the stage "
                "to a valid position."
            )
            revert_um = self._shell.stack_ending_plane
            if revert_um is None or revert_um < low or revert_um > high:
                revert_um = high
            self.ui.doubleSpinBox_acqLastPlane.setValue(revert_um / 1000.0)
            return
        self._shell.stack_ending_plane = value_um
        self._shell.stack_last_plane_set = True
        self.updateUi_set_number_of_planes()

    def _position_display_to_um(self, value: float) -> float:
        """Convert a plane-position spinbox value (displayed in mm per the
        FieldSpec) to micrometres (the internal unit the worker + motor HAL
        use). Safety-critical: ``stack_starting_plane`` /
        ``stack_ending_plane`` MUST stay µm — a missing conversion here is a
        1000× motor over-travel error."""
        return value * 1000.0

    def _step_display_to_um(self, value: float) -> float:
        """Convert a plane-step spinbox value to micrometres. The step
        FieldSpec unit is µm, so the spinbox value is already in µm and no
        conversion is needed — pass-through. Kept as a named method so the
        position/step conversion seams are explicit and symmetric."""
        return value

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
                # Positions display in mm → ×1000; the step displays in
                # µm → pass-through. Mixing the two converters would feed
                # a mm value to the worker as µm (1000× motor error).
                self._shell.stack_starting_plane = self._position_display_to_um(
                    self.ui.doubleSpinBox_acqFirstPlane.value()
                )
                self._shell.stack_ending_plane = self._position_display_to_um(
                    self.ui.doubleSpinBox_acqLastPlane.value()
                )
                step_um = self._step_display_to_um(
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
        # Positions display in mm (FieldSpec unit); the plane step displays
        # in µm. Separate unit labels so the summary does not relabel a mm
        # value as µm (the pre-reconciliation 1000× display error).
        pos_unit = "mm"
        step_unit = "\u03bcm"

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
        # Multi-channel: when both auto-laser checkboxes are checked the
        # stack runs a sequential per-plane cycle (laser 1 then laser 2),
        # so both Est. time and Est. size double, and a "2 ch x N planes"
        # clause is inserted after the Planes clause. This is a GUI-thread
        # slot — reading the checkbox widgets is allowed. Single-channel
        # (zero or one auto-laser checked) is byte-identical to today's
        # render: no 2ch clause, no doubling.
        multi_channel = False
        laser_panel = getattr(self._shell, "laser_panel", None)
        if laser_panel is not None:
            cb1 = getattr(laser_panel.ui, "checkBox_laserOneAutomatic", None)
            cb2 = getattr(laser_panel.ui, "checkBox_laserTwoAutomatic", None)
            if cb1 is not None and cb2 is not None:
                multi_channel = bool(cb1.isChecked() and cb2.isChecked())
        if multi_channel:
            est_time_s = est_time_s * 2
            est_size_mb = est_size_mb * 2
            ch_clause = f"2 ch × {n_planes} planes | "
        else:
            ch_clause = ""
        mm, ss = divmod(int(est_time_s), 60)
        self.ui.label_stackPlanSummary.setText(
            f"Start: {start:.3f} {pos_unit} | End: {end:.3f} {pos_unit} | "
            f"Step: {step:.2f} {step_unit} | Planes: {n_planes} | "
            f"{ch_clause}"
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
