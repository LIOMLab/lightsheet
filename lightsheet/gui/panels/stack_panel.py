"""StackPanelWidget — per-panel widget/controller for stack acquisition setup.

Owns the stack updateUi_* slots: stack starting/ending point selection and
number-of-planes calculation. The adaptive configuration group (enable
toggle + 13 bounded spinboxes + shutter hint) is an opt-in overlay on top
of the fixed-exposure stack. Bounds are pre-sampled on the GUI thread in
``build_adaptive_config`` and passed as a frozen ``AdaptiveConfig`` to the
StackWorker constructor — the worker thread never reads ``ui.*``.
"""

from __future__ import annotations

import typing
from typing import ClassVar

import numpy as np
from PySide6.QtWidgets import QWidget

from lightsheet.adaptive.types import AdaptiveConfig
from lightsheet.gui.panels.acquisition_table_manager import AcquisitionTableManager
from lightsheet.gui.panels.ui_stack_panel import Ui_StackPanel
from lightsheet.gui.widgets.field_spec import FIELD_SPECS

if typing.TYPE_CHECKING:
    from lightsheet.gui.shell.controller import Controller_MainWindow


# The exact operator-facing copy for an invalid adaptive bound pair.
# Emitted via sig_message + sig_beep; the offending spinbox reverts to its
# prior value and the latch forces fixed-fallback until a later valid edit.
_ADAPTIVE_BOUND_INVALID_MSG = (
    "Adaptive bound invalid: {field} minimum is greater than maximum. "
    "Not applied — the stack will run with fixed exposure/power. "
    "Adjust the bounds or uncheck Adaptive Control."
)

# The shutter-mode hint copy.
_HINT_ROLLING = "Rolling shutter — exposure bound in milliseconds."
_HINT_LIGHTSHEET = "Lightsheet shutter — exposure bound in exposed lines x line time."


class StackPanelWidget(QWidget):
    """Stack acquisition setup panel — owns stack starting/ending point
    and number-of-planes calculation slots."""

    def __init__(self, shell: Controller_MainWindow) -> None:
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

        # --- Adaptive configuration group wiring ---
        # The fixed-fallback latch: once an invalid min/max pair is
        # edited, build_adaptive_config returns None (fixed stack) until
        # a later valid edit clears the latch. Tracks the prior valid
        # value per spinbox so an invalid edit reverts cleanly.
        self._adaptive_latched: bool = False
        self._adaptive_prior_values: dict[str, float] = {}
        # Load the validated [Adaptive] defaults from config.ini into the
        # spinboxes (the schema already rejected out-of-range values at
        # startup, so the loaded values are safe).
        self._load_adaptive_config()
        # Narrow the laser max-power spinbox maxima to the live HAL
        # max_power (capped at 150.0). The HAL two-layer clamp is the
        # safety backstop; the widget soft-block is a defense-in-depth.
        self._narrow_adaptive_power_maxima()
        # Wire the enable toggle → fields-container visibility. The
        # group box title row stays visible (the affordance) while only
        # the fields container is hidden on toggle-off.
        self.ui.checkBox_adaptiveEnable.toggled.connect(self._on_adaptive_toggled)
        # Initialize the fields container visibility from the toggle
        # state (default unchecked → hidden).
        self.ui.widget_adaptiveFields.setVisible(
            self.ui.checkBox_adaptiveEnable.isChecked()
        )
        # Wire editingFinished on every adaptive spinbox to track prior
        # values and validate min/max pairs. The pair validators run on
        # the four bound pairs (exposure, L1 power, L2 power, target
        # band); the single-field spinboxes only track prior values.
        for name in self._ADAPTIVE_SPINBOX_NAMES:
            sb = getattr(self.ui, name)
            self._adaptive_prior_values[name] = sb.value()
            sb.editingFinished.connect(self._on_adaptive_field_edited)
        # Initialize the shutter-mode units from the current camera
        # shutter mode (the camera may default to Lightsheet).
        self._update_adaptive_shutter_units()

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
        1000x motor over-travel error."""
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
            if self._shell.stack_first_plane_set and self._shell.stack_last_plane_set:
                # Read the boundary values from the spinboxes (the
                # operator may have typed them directly) and convert to
                # μm (the internal unit the worker + motor HAL use).
                # Positions display in mm → x1000; the step displays in
                # µm → pass-through. Mixing the two converters would feed
                # a mm value to the worker as µm (1000x motor error).
                self._shell.stack_starting_plane = self._position_display_to_um(
                    self.ui.doubleSpinBox_acqFirstPlane.value()
                )
                self._shell.stack_ending_plane = self._position_display_to_um(
                    self.ui.doubleSpinBox_acqLastPlane.value()
                )
                step_um = self._step_display_to_um(
                    self.ui.doubleSpinBox_acqPlaneStepSize.value()
                )
                self._shell.number_of_planes = int(
                    np.ceil(
                        abs(
                            (
                                self._shell.stack_ending_plane
                                - self._shell.stack_starting_plane
                            )
                            / step_um
                        )
                    )
                )
                self._shell.number_of_planes += (
                    1  # Takes into account the initial plane
                )
                self.ui.label_acqNumberOfPlanes.setText(
                    str(self._shell.number_of_planes)
                )
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
        # value as µm (the pre-reconciliation 1000x display error).
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
        # Estimated time: per-plane time x #planes. The per-plane time is
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
            ch_clause = f"2 ch x {n_planes} planes | "
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
            exposure = float(
                self._shell.acquisition_panel.ui.doubleSpinBox_cameraExposureTime.value()
            )
            # Exposure is in ms; add overhead for galvo/ETL scan + motor
            # settle. 1.5x exposure is a rough advisory factor.
            return exposure / 1000.0 * 1.5
        except (AttributeError, ValueError, TypeError):
            return 0.5

    def _estimate_stack_size_mb(self, n_planes: int) -> float:
        """Advisory stack size in MB. Uses the camera frame dims x 2 bytes
        (uint16) when available; falls back to a 2000x2000 default."""
        try:
            rows = int(getattr(self._shell.camera, "rows", 2000))
            cols = int(getattr(self._shell.camera, "columns", 2000))
        except (AttributeError, TypeError, ValueError):
            rows, cols = 2000, 2000
        bytes_per_frame = rows * cols * 2
        return (n_planes * bytes_per_frame) / (1024.0 * 1024.0)

    # --- Adaptive configuration group (opt-in overlay on the fixed stack) ---

    # The 13 enumerated adaptive spinbox objectNames, in the order they
    # appear in the form layout. Used to wire editingFinished + track
    # prior values uniformly.
    _ADAPTIVE_SPINBOX_NAMES: ClassVar[tuple[str, ...]] = (
        "doubleSpinBox_adaptiveMinExposure",
        "doubleSpinBox_adaptiveMaxExposure",
        "doubleSpinBox_adaptiveLaser1MinPower",
        "doubleSpinBox_adaptiveLaser1MaxPower",
        "doubleSpinBox_adaptiveLaser2MinPower",
        "doubleSpinBox_adaptiveLaser2MaxPower",
        "doubleSpinBox_adaptiveTargetBandLo",
        "doubleSpinBox_adaptiveTargetBandHi",
        "doubleSpinBox_adaptiveReacquireThreshold",
        "doubleSpinBox_adaptiveBlockSizeN",
        "doubleSpinBox_adaptiveKp",
        "doubleSpinBox_adaptiveKi",
        "doubleSpinBox_adaptivePilotCount",
    )

    # The four min/max bound pairs validated on editingFinished. Each
    # entry maps the min spinbox name to (max spinbox name, field label
    # for the error message).
    _ADAPTIVE_BOUND_PAIRS: ClassVar[dict[str, tuple[str, str]]] = {
        "doubleSpinBox_adaptiveMinExposure": (
            "doubleSpinBox_adaptiveMaxExposure",
            "exposure",
        ),
        "doubleSpinBox_adaptiveLaser1MinPower": (
            "doubleSpinBox_adaptiveLaser1MaxPower",
            "Laser1 power",
        ),
        "doubleSpinBox_adaptiveLaser2MinPower": (
            "doubleSpinBox_adaptiveLaser2MaxPower",
            "Laser2 power",
        ),
        "doubleSpinBox_adaptiveTargetBandLo": (
            "doubleSpinBox_adaptiveTargetBandHi",
            "target band",
        ),
    }

    # The two exposure-bound spinboxes whose unit swaps with shutter mode.
    _ADAPTIVE_EXPOSURE_SPINBOXES: ClassVar[tuple[str, ...]] = (
        "doubleSpinBox_adaptiveMinExposure",
        "doubleSpinBox_adaptiveMaxExposure",
    )

    def _load_adaptive_config(self) -> None:
        """Load the validated [Adaptive] defaults from config.ini into the
        spinboxes. The schema already rejected out-of-range values at
        startup, so the loaded values are safe. A missing [Adaptive]
        section leaves the spinboxes at their FieldSpec defaults."""
        from lightsheet.config import cfg_read

        defaults = {
            "Enabled": "",
            "Min Exposure": "",
            "Max Exposure": "",
            "Laser1 Min Power": "",
            "Laser1 Max Power": "",
            "Laser2 Min Power": "",
            "Laser2 Max Power": "",
            "Target Band Lo": "",
            "Target Band Hi": "",
            "Reacquire Threshold": "",
            "Block Size N": "",
            "Kp": "",
            "Ki": "",
            "Pilot Count": "",
        }
        try:
            cfg = cfg_read("config.ini", "Adaptive", defaults)
        except Exception:
            # No [Adaptive] section or config.ini unreadable — leave the
            # FieldSpec defaults in place.
            return
        _set = {
            "Enabled": ("checkBox_adaptiveEnable", "bool"),
            "Min Exposure": ("doubleSpinBox_adaptiveMinExposure", "float"),
            "Max Exposure": ("doubleSpinBox_adaptiveMaxExposure", "float"),
            "Laser1 Min Power": ("doubleSpinBox_adaptiveLaser1MinPower", "float"),
            "Laser1 Max Power": ("doubleSpinBox_adaptiveLaser1MaxPower", "float"),
            "Laser2 Min Power": ("doubleSpinBox_adaptiveLaser2MinPower", "float"),
            "Laser2 Max Power": ("doubleSpinBox_adaptiveLaser2MaxPower", "float"),
            "Target Band Lo": ("doubleSpinBox_adaptiveTargetBandLo", "float"),
            "Target Band Hi": ("doubleSpinBox_adaptiveTargetBandHi", "float"),
            "Reacquire Threshold": (
                "doubleSpinBox_adaptiveReacquireThreshold",
                "float",
            ),
            "Block Size N": ("doubleSpinBox_adaptiveBlockSizeN", "float"),
            "Kp": ("doubleSpinBox_adaptiveKp", "float"),
            "Ki": ("doubleSpinBox_adaptiveKi", "float"),
            "Pilot Count": ("doubleSpinBox_adaptivePilotCount", "float"),
        }
        for key, (widget_name, kind) in _set.items():
            raw = str(cfg.get(key, "")).strip()
            if not raw:
                continue
            w = getattr(self.ui, widget_name, None)
            if w is None:
                continue
            try:
                if kind == "bool":
                    w.setChecked(raw.lower() in ("true", "1", "yes"))
                else:
                    w.setValue(float(raw))
            except (ValueError, AttributeError):
                pass

    def _narrow_adaptive_power_maxima(self) -> None:
        """Narrow the laser max-power spinbox maxima at runtime to
        ``min(150.0, shell._bundle.lasers[i].max_power)``. The HAL
        two-layer clamp is the safety backstop; the widget soft-block is
        a defense-in-depth so the operator cannot enter a bound above
        the live laser's maximum."""
        bundle = getattr(self._shell, "_bundle", None)
        lasers = getattr(bundle, "lasers", None) if bundle is not None else None
        # Guard against a Mock shell (structural tests) or a bundle
        # without a lasers tuple yet — skip narrowing in that case.
        if not isinstance(lasers, (tuple, list)) or len(lasers) < 2:
            return
        for i, sb_name in enumerate(
            (
                "doubleSpinBox_adaptiveLaser1MaxPower",
                "doubleSpinBox_adaptiveLaser2MaxPower",
            )
        ):
            sb = getattr(self.ui, sb_name, None)
            if sb is None:
                continue
            try:
                live_max = float(lasers[i].max_power)
            except (TypeError, ValueError, AttributeError):
                continue
            narrowed = min(150.0, live_max)
            # Preserve the current value if it is still within the
            # narrowed range; otherwise clamp it down.
            cur = sb.value()
            sb.setMaximum(narrowed)
            if cur > narrowed:
                sb.setValue(narrowed)
        # Also narrow the min-power spinboxes so a min cannot exceed the
        # narrowed max (the pair validator catches it, but the soft
        # range should match).
        for i, sb_name in enumerate(
            (
                "doubleSpinBox_adaptiveLaser1MinPower",
                "doubleSpinBox_adaptiveLaser2MinPower",
            )
        ):
            sb = getattr(self.ui, sb_name, None)
            if sb is None:
                continue
            try:
                live_max = float(lasers[i].max_power)
            except (TypeError, ValueError, AttributeError):
                continue
            sb.setMaximum(min(150.0, live_max))

    def _on_adaptive_toggled(self, checked: bool) -> None:
        """Toggle the fields container visibility. The group box title
        row stays visible (the affordance) while only the fields
        container is hidden on toggle-off."""
        self.ui.widget_adaptiveFields.setVisible(checked)

    def _on_adaptive_field_edited(self) -> None:
        """editingFinished on any adaptive spinbox: track the prior value
        and validate the relevant min/max pair. On an invalid pair,
        beep + emit the documented message + revert the offending
        spinbox + latch fixed-fallback. On a valid edit, clear the
        latch."""
        sb = self.sender()
        if sb is None:
            return
        name = sb.objectName()
        # Check whether this spinbox is the min of a bound pair.
        pair = self._ADAPTIVE_BOUND_PAIRS.get(name)
        if pair is not None:
            max_name, field_label = pair
            max_sb = getattr(self.ui, max_name, None)
            if max_sb is not None and sb.value() > max_sb.value():
                # Invalid pair — beep + message + revert + latch.
                self._shell.sig_beep.emit()
                self._shell.sig_message.emit(
                    _ADAPTIVE_BOUND_INVALID_MSG.format(field=field_label)
                )
                revert = self._adaptive_prior_values.get(name, max_sb.value())
                sb.setValue(revert)
                self._adaptive_latched = True
                return
        # Also check whether this spinbox is the max of a bound pair
        # (the operator may have lowered the max below the min).
        for min_name, (max_name, field_label) in self._ADAPTIVE_BOUND_PAIRS.items():
            if name == max_name:
                min_sb = getattr(self.ui, min_name, None)
                if min_sb is not None and min_sb.value() > sb.value():
                    self._shell.sig_beep.emit()
                    self._shell.sig_message.emit(
                        _ADAPTIVE_BOUND_INVALID_MSG.format(field=field_label)
                    )
                    revert = self._adaptive_prior_values.get(name, min_sb.value())
                    sb.setValue(revert)
                    self._adaptive_latched = True
                    return
        # Valid edit — track the new prior value and clear the latch.
        self._adaptive_prior_values[name] = sb.value()
        self._adaptive_latched = False

    def _update_adaptive_shutter_units(self) -> None:
        """Swap the exposure-bound spinbox suffix/decimals/range between
        Rolling (ms) and Lightsheet (lines) shutter modes, and update
        the shutter-mode hint label. The physical value is preserved
        across the swap (a 5 ms bound stays 5 when switching to lines);
        the build_adaptive_config normalization handles the unit
        conversion to seconds."""
        acq_ui = getattr(self._shell, "acquisition_panel", None)
        acq_ui = getattr(acq_ui, "ui", None) if acq_ui is not None else None
        if acq_ui is None:
            return
        mode = ""
        combo = getattr(acq_ui, "comboBox_cameraShutterMode", None)
        if combo is not None:
            mode = str(combo.currentText()).strip()
        if mode == "Lightsheet":
            for name in self._ADAPTIVE_EXPOSURE_SPINBOXES:
                sb = getattr(self.ui, name, None)
                if sb is not None:
                    sb.setSuffix(" lines")
                    sb.setDecimals(0)
            self.ui.label_adaptiveShutterModeHint.setText(_HINT_LIGHTSHEET)
        else:
            # Rolling (or unknown — default to ms).
            for name in self._ADAPTIVE_EXPOSURE_SPINBOXES:
                sb = getattr(self.ui, name, None)
                if sb is not None:
                    sb.setSuffix(" ms")
                    sb.setDecimals(0)
            self.ui.label_adaptiveShutterModeHint.setText(_HINT_ROLLING)

    def build_adaptive_config(self) -> AdaptiveConfig | None:
        """Pre-sample the adaptive configuration on the GUI thread and
        return a frozen ``AdaptiveConfig`` (or ``None`` when the toggle
        is unchecked or the fixed-fallback latch is set).

        Normalizes the GUI values to the worker's canonical units:
        - Exposure: ms → seconds (x1e-3) in Rolling; lines x line_time
          (µs x 1e-6) → seconds in Lightsheet.
        - Power: mW, narrowed to the live laser maxima.
        - Target band / reacquire threshold: % → fraction (x1e-2).
        - Block size N, Kp, Ki, Pilot Count: pass-through.

        The frozen dataclass is safe to share across threads (immutable)
        — the worker thread receives one snapshot and never reads
        ``ui.*``.
        """
        if not self.ui.checkBox_adaptiveEnable.isChecked():
            return None
        if self._adaptive_latched:
            return None
        # Resolve the shutter mode + line time for the exposure
        # normalization.
        acq_ui = getattr(self._shell, "acquisition_panel", None)
        acq_ui = getattr(acq_ui, "ui", None) if acq_ui is not None else None
        mode = ""
        line_time_us = 100.0
        if acq_ui is not None:
            combo = getattr(acq_ui, "comboBox_cameraShutterMode", None)
            if combo is not None:
                mode = str(combo.currentText()).strip()
            lt = getattr(acq_ui, "doubleSpinBox_cameraLineTime", None)
            if lt is not None:
                try:
                    line_time_us = float(lt.value())
                except (ValueError, TypeError):
                    line_time_us = 100.0

        def _exposure_to_seconds(sb_name: str) -> float:
            sb = getattr(self.ui, sb_name)
            v = float(sb.value())
            if mode == "Lightsheet":
                # lines x line_time(µs) x 1e-6 = seconds
                return v * line_time_us * 1e-6
            # Rolling — ms x 1e-3 = seconds
            return v * 1e-3

        min_exp_s = _exposure_to_seconds("doubleSpinBox_adaptiveMinExposure")
        max_exp_s = _exposure_to_seconds("doubleSpinBox_adaptiveMaxExposure")
        l1_min = float(self.ui.doubleSpinBox_adaptiveLaser1MinPower.value())
        l1_max = float(self.ui.doubleSpinBox_adaptiveLaser1MaxPower.value())
        l2_min = float(self.ui.doubleSpinBox_adaptiveLaser2MinPower.value())
        l2_max = float(self.ui.doubleSpinBox_adaptiveLaser2MaxPower.value())
        target_lo = float(self.ui.doubleSpinBox_adaptiveTargetBandLo.value()) / 100.0
        target_hi = float(self.ui.doubleSpinBox_adaptiveTargetBandHi.value()) / 100.0
        reacquire_sb = self.ui.doubleSpinBox_adaptiveReacquireThreshold
        reacquire = float(reacquire_sb.value()) / 100.0
        block_n = int(self.ui.doubleSpinBox_adaptiveBlockSizeN.value())
        kp = float(self.ui.doubleSpinBox_adaptiveKp.value())
        ki = float(self.ui.doubleSpinBox_adaptiveKi.value())
        pilot = int(self.ui.doubleSpinBox_adaptivePilotCount.value())
        return AdaptiveConfig(
            enabled=True,
            min_exposure_s=min_exp_s,
            max_exposure_s=max_exp_s,
            min_power_mw=(l1_min, l2_min),
            max_power_mw=(l1_max, l2_max),
            target_band_lo=target_lo,
            target_band_hi=target_hi,
            reacquire_threshold=reacquire,
            block_size_n=block_n,
            kp=kp,
            ki=ki,
            pilot_count=pilot,
        )
