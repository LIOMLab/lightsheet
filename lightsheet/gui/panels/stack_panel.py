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
from pathlib import Path
from typing import ClassVar

import numpy as np
from PySide6.QtWidgets import QDoubleSpinBox, QFileDialog, QWidget

from lightsheet.adaptive.types import AdaptiveConfig
from lightsheet.focus.calibration import load_focus_curve
from lightsheet.focus.types import AutofocusConfig, FocusConfig, FocusCurve
from lightsheet.gui.panels.acquisition_table_manager import AcquisitionTableManager
from lightsheet.gui.panels.ui_stack_panel import Ui_StackPanel
from lightsheet.gui.styles import spacing as _s
from lightsheet.gui.styles import typography as _t
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
_HINT_LIGHTSHEET = "Lightsheet shutter — exposure bound in microseconds (line time)."


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

        # --- Focus configuration group wiring ---
        # The armed focus curve and its file path are populated by
        # pushButton_focusLoad after a successful validating JSON parse.
        # Until then build_focus_config/build_focus_curve return None so
        # the stack runs with fixed camera focus.
        self._armed_focus_curve: FocusCurve | None = None
        self._armed_focus_curve_path: str = ""
        # Load the validated [Focus] defaults from config.ini into the
        # toggle, spinbox, residual checkbox, and cached residual tuning
        # values. The schema already rejected out-of-range values at
        # startup, so the loaded values are safe.
        self._load_focus_config()
        # Wire the enable toggle → fields-container visibility. The group
        # box title row stays visible (the affordance) while only the
        # fields container is hidden on toggle-off.
        self.ui.checkBox_focusEnable.toggled.connect(self._on_focus_toggled)
        self.ui.widget_focusFields.setVisible(self.ui.checkBox_focusEnable.isChecked())
        # Wire Browse to a JSON-only file chooser, Load to the validating
        # curve loader, and the block-size spinbox to the hard 1..100 guard.
        self.ui.pushButton_focusBrowse.clicked.connect(self._on_focus_browse)
        self.ui.pushButton_focusLoad.clicked.connect(self._on_focus_load)
        self.ui.doubleSpinBox_focusBlockSize.editingFinished.connect(
            self._on_focus_block_size_edited
        )
        # Render the initial empty state and block-size hint.
        self._update_focus_status_label()

        # --- Adaptive autofocus configuration group wiring ---
        # The per-plane predictive focus loop. Its widgets are pre-sampled
        # on the GUI thread into a frozen AutofocusConfig; the worker
        # receives the immutable snapshot and never reads ui.*.
        self._load_autofocus_config()
        self.ui.checkBox_adaptiveAutofocus.toggled.connect(self._on_autofocus_toggled)
        self.ui.checkBox_autofocusUseCurve.toggled.connect(
            self._on_autofocus_use_curve_toggled
        )
        self.ui.doubleSpinBox_autofocusCadence.editingFinished.connect(
            self._on_autofocus_cadence_edited
        )
        self.ui.doubleSpinBox_autofocusResidualGain.editingFinished.connect(
            self._on_autofocus_residual_gain_edited
        )
        self.ui.doubleSpinBox_autofocusMaxResidual.editingFinished.connect(
            self._on_autofocus_max_residual_edited
        )
        self.ui.doubleSpinBox_autofocusSmoothing.editingFinished.connect(
            self._on_autofocus_smoothing_edited
        )
        self._on_autofocus_toggled(self.ui.checkBox_adaptiveAutofocus.isChecked())

        # --- Adaptive-autofocus UI review fixes ---
        # The live status label is the primary focal point and must be bold.
        # The design uses exactly two weights: regular body and bold status.
        self.ui.label_autofocusStatus.setStyleSheet(f"{_t.BOLD}")
        # The adaptive parameter grid uses the 8 px spacing token, not the
        # QGridLayout default.
        self.ui.gridLayout_adaptiveAutofocusFields.setSpacing(_s.SM)
        # The progress bar takes its chunk color from the active theme's
        # Breeze QSS (slider:foreground ≈ accent) — no per-widget override.

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

    # The 6 operator-adjustable adaptive spinbox objectNames (the fixed
    # controller-tuning settings — target band, reacquire threshold,
    # block size, Kp, Ki, pilot count — moved to config.ini only).
    # Used to wire editingFinished + track prior values uniformly.
    _ADAPTIVE_SPINBOX_NAMES: ClassVar[tuple[str, ...]] = (
        "doubleSpinBox_adaptiveMinExposure",
        "doubleSpinBox_adaptiveMaxExposure",
        "doubleSpinBox_adaptiveLaser1MinPower",
        "doubleSpinBox_adaptiveLaser1MaxPower",
        "doubleSpinBox_adaptiveLaser2MinPower",
        "doubleSpinBox_adaptiveLaser2MaxPower",
    )

    # The three min/max bound pairs validated on editingFinished. Each
    # entry maps the min spinbox name to (max spinbox name, field label
    # for the error message). Target band is config-only now.
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
        section leaves the spinboxes at their FieldSpec defaults. Records
        which keys were loaded so _narrow_adaptive_power_maxima can set
        the laser max-power defaults to the calibrated max_power only
        when the operator did not save an explicit value."""
        from lightsheet.config import cfg_read

        self._adaptive_loaded_keys: set[str] = set()
        defaults = {
            "Enabled": "",
            "Min Exposure": "",
            "Max Exposure": "",
            "Laser1 Min Power": "",
            "Laser1 Max Power": "",
            "Laser2 Min Power": "",
            "Laser2 Max Power": "",
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
        }
        for key, (widget_name, kind) in _set.items():
            raw = str(cfg.get(key, "")).strip()
            if not raw:
                continue
            self._adaptive_loaded_keys.add(key)
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
        the live laser's maximum. When the operator did not save an
        explicit max-power value in config.ini, the spinbox default is
        set to the laser's calibrated max_power (rather than the stale
        FieldSpec placeholder) so the bound reflects the real hardware."""
        bundle = getattr(self._shell, "_bundle", None)
        lasers = getattr(bundle, "lasers", None) if bundle is not None else None
        # Guard against a Mock shell (structural tests) or a bundle
        # without a lasers tuple yet — skip narrowing in that case.
        if not isinstance(lasers, (tuple, list)) or len(lasers) < 2:
            return
        loaded = getattr(self, "_adaptive_loaded_keys", set())
        config_keys = ("Laser1 Max Power", "Laser2 Max Power")
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
            sb.setMaximum(narrowed)
            # If config.ini did not provide an explicit max-power value,
            # default the bound to the laser's calibrated max_power so
            # the operator sees the real hardware ceiling, not the
            # FieldSpec placeholder (5.0 mW).
            if config_keys[i] not in loaded:
                sb.setValue(narrowed)
            elif sb.value() > narrowed:
                # Operator saved a value above the live max — clamp down.
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
            if max_sb is not None and sb.value() > max_sb.value():  # ty: ignore[unresolved-attribute]
                # Invalid pair — beep + message + revert + latch.
                self._shell.sig_beep.emit()
                self._shell.sig_message.emit(
                    _ADAPTIVE_BOUND_INVALID_MSG.format(field=field_label)
                )
                revert = self._adaptive_prior_values.get(name, max_sb.value())
                sb.setValue(revert)  # ty: ignore[unresolved-attribute]
                self._adaptive_latched = True
                return
        # Also check whether this spinbox is the max of a bound pair
        # (the operator may have lowered the max below the min).
        for min_name, (max_name, field_label) in self._ADAPTIVE_BOUND_PAIRS.items():
            if name == max_name:
                min_sb = getattr(self.ui, min_name, None)
                if min_sb is not None and min_sb.value() > sb.value():  # ty: ignore[unresolved-attribute]
                    self._shell.sig_beep.emit()
                    self._shell.sig_message.emit(
                        _ADAPTIVE_BOUND_INVALID_MSG.format(field=field_label)
                    )
                    revert = self._adaptive_prior_values.get(name, min_sb.value())
                    sb.setValue(revert)  # ty: ignore[unresolved-attribute]
                    self._adaptive_latched = True
                    return
        # Valid edit — track the new prior value and clear the latch.
        self._adaptive_prior_values[name] = sb.value()  # ty: ignore[unresolved-attribute]
        self._adaptive_latched = False

    def _update_adaptive_shutter_units(self) -> None:
        """Swap the exposure-bound spinbox suffix/decimals/range between
        Rolling (ms) and Lightsheet (µs, line time) shutter modes, and update
        the shutter-mode hint label. The physical value is preserved
        across the swap (a 5 ms bound stays 5 when switching to µs);
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
                    sb.setSuffix(" µs")
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

    def _read_adaptive_fixed_config(
        self,
    ) -> tuple[float, float, float, int, float, float, int]:
        """Read the fixed controller-tuning settings from config.ini
        (target band lo/hi %, reacquire threshold %, block size N, Kp,
        Ki, pilot count). These were removed from the GUI — they are
        config-only because they rarely change per experiment. Falls
        back to the schema defaults if the [Adaptive] section or
        individual keys are absent.
        """
        from lightsheet.config import cfg_read

        defaults = {
            "Target Band Lo": "90.0",
            "Target Band Hi": "95.0",
            "Reacquire Threshold": "8.0",
            "Block Size N": "8",
            "Kp": "0.4",
            "Ki": "0.05",
            "Pilot Count": "5",
        }
        try:
            cfg = cfg_read("config.ini", "Adaptive", defaults)
        except Exception:
            cfg = defaults
        # The schema validator rejects malformed [Adaptive] values at
        # startup, but this method re-reads config.ini at stack-start
        # time (every call to build_adaptive_config). If config.ini is
        # edited between startup and stack-start, a malformed value
        # (e.g. "Kp = abc") would raise ValueError out of float()/int()
        # and propagate up through the Qt slot handler, crashing the GUI
        # thread. Wrap the conversions and fall back to the defaults
        # dict on any conversion error so a bad edit degrades gracefully
        # instead of crashing the Start button.
        try:
            target_lo = float(cfg.get("Target Band Lo", "90.0")) / 100.0
            target_hi = float(cfg.get("Target Band Hi", "95.0")) / 100.0
            reacquire = float(cfg.get("Reacquire Threshold", "8.0")) / 100.0
            block_n = int(float(cfg.get("Block Size N", "8")))
            kp = float(cfg.get("Kp", "0.4"))
            ki = float(cfg.get("Ki", "0.05"))
            pilot = int(float(cfg.get("Pilot Count", "5")))
        except (ValueError, TypeError):
            target_lo = float(defaults["Target Band Lo"]) / 100.0
            target_hi = float(defaults["Target Band Hi"]) / 100.0
            reacquire = float(defaults["Reacquire Threshold"]) / 100.0
            block_n = int(float(defaults["Block Size N"]))
            kp = float(defaults["Kp"])
            ki = float(defaults["Ki"])
            pilot = int(float(defaults["Pilot Count"]))
        return target_lo, target_hi, reacquire, block_n, kp, ki, pilot

    def build_adaptive_config(self) -> AdaptiveConfig | None:
        """Pre-sample the adaptive configuration on the GUI thread and
        return a frozen ``AdaptiveConfig`` (or ``None`` when the toggle
        is unchecked or the fixed-fallback latch is set).

        Normalizes the GUI values to the worker's canonical units:
        - Exposure: ms → seconds (x1e-3) in Rolling; µs x 1e-6 →
          seconds in Lightsheet.
        - Power: mW, narrowed to the live laser maxima.
        - Target band / reacquire threshold: % → fraction (x1e-2),
          read from config.ini (config-only, not in the GUI).
        - Block size N, Kp, Ki, Pilot Count: pass-through, read from
          config.ini (config-only, not in the GUI).

        The frozen dataclass is safe to share across threads (immutable)
        — the worker thread receives one snapshot and never reads
        ``ui.*``.
        """
        if not self.ui.checkBox_adaptiveEnable.isChecked():
            return None
        if self._adaptive_latched:
            return None
        # Resolve the shutter mode for the exposure normalization. In
        # Lightsheet mode the bound is already in µs (line time); in
        # Rolling it is in ms.
        acq_ui = getattr(self._shell, "acquisition_panel", None)
        acq_ui = getattr(acq_ui, "ui", None) if acq_ui is not None else None
        mode = ""
        if acq_ui is not None:
            combo = getattr(acq_ui, "comboBox_cameraShutterMode", None)
            if combo is not None:
                mode = str(combo.currentText()).strip()

        def _exposure_to_seconds(sb_name: str) -> float:
            sb = getattr(self.ui, sb_name)
            v = float(sb.value())
            if mode == "Lightsheet":
                # µs x 1e-6 = seconds (the bound is already in line time µs)
                return v * 1e-6
            # Rolling — ms x 1e-3 = seconds
            return v * 1e-3

        min_exp_s = _exposure_to_seconds("doubleSpinBox_adaptiveMinExposure")
        max_exp_s = _exposure_to_seconds("doubleSpinBox_adaptiveMaxExposure")
        l1_min = float(self.ui.doubleSpinBox_adaptiveLaser1MinPower.value())
        l1_max = float(self.ui.doubleSpinBox_adaptiveLaser1MaxPower.value())
        l2_min = float(self.ui.doubleSpinBox_adaptiveLaser2MinPower.value())
        l2_max = float(self.ui.doubleSpinBox_adaptiveLaser2MaxPower.value())
        # The fixed controller-tuning settings (target band, reacquire
        # threshold, block size, Kp, Ki, pilot count) are config-only —
        # read from config.ini, not from the UI (they were removed from
        # the GUI to reduce clutter; they rarely change per experiment).
        target_lo, target_hi, reacquire, block_n, kp, ki, pilot = (
            self._read_adaptive_fixed_config()
        )
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

    # --- Focus configuration group (opt-in camera focus compensation) -------

    def _load_focus_config(self) -> None:
        """Load the validated [Focus] defaults from config.ini into the
        widget state. The schema already rejected out-of-range values at
        startup, so the loaded values are safe. A missing [Focus] section
        leaves the widget defaults in place and falls back to the
        documented residual tuning values.
        """
        from lightsheet.config import cfg_read

        defaults = {
            "Enabled": "",
            "Block Size N": "",
            "Autofocus Residual Enabled": "",
            "Residual Gain Mm": "0.05",
            "Max Residual Mm": "0.5",
        }
        try:
            cfg = cfg_read("config.ini", "Focus", defaults)
        except Exception:
            cfg = defaults
        _set = {
            "Enabled": ("checkBox_focusEnable", "bool"),
            "Block Size N": ("doubleSpinBox_focusBlockSize", "float"),
            "Autofocus Residual Enabled": (
                "checkBox_focusAutofocusResidual",
                "bool",
            ),
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
        # Residual tuning is config-only (no GUI widgets); cache it for
        # build_focus_config. Parsing failures fall back to the defaults.
        try:
            self._focus_residual_gain_mm = float(
                cfg.get("Residual Gain Mm", "0.05") or "0.05"
            )
        except ValueError:
            self._focus_residual_gain_mm = 0.05
        try:
            self._focus_max_residual_mm = float(
                cfg.get("Max Residual Mm", "0.5") or "0.5"
            )
        except ValueError:
            self._focus_max_residual_mm = 0.5

    def _on_focus_toggled(self, checked: bool) -> None:
        """Toggle the focus fields container visibility. The group box
        title row stays visible (the affordance) while only the fields
        container is hidden on toggle-off."""
        self.ui.widget_focusFields.setVisible(checked)

    def _on_focus_browse(self) -> None:
        """Open a JSON-only file dialog and, if the operator confirms,
        write the chosen path into lineEdit_focusCurvePath."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Focus Calibration",
            "",
            "Calibration files (*.json);;All files (*.*)",
        )
        if path:
            self.ui.lineEdit_focusCurvePath.setText(path)

    def _on_focus_load(self) -> None:
        """Validate the file chosen in lineEdit_focusCurvePath and, if
        valid, arm the focus group. On failure emit sig_beep + sig_message
        with the documented invalid-file copy and keep the group unarmed.
        """
        path = self.ui.lineEdit_focusCurvePath.text().strip()
        if not path:
            self._clear_focus_armed()
            self._shell.sig_beep.emit()
            self._shell.sig_message.emit(
                "No focus calibration file selected. Load a file or uncheck "
                "Camera focus compensation."
            )
            self.ui.label_focusStatus.setText("Invalid file — no path")
            return

        # Read the camera travel limits from the live HAL for the
        # validating loader; fall back to the documented 0-35 mm Zaber
        # T-LS camera mechanical limits if the bundle is not yet available.
        cam_lo_mm = 0.0
        cam_hi_mm = 35.0
        motors = getattr(self._shell, "motors", None)
        if motors is not None:
            try:
                cam_lo_mm = float(motors.camera.get_limit_low("mm"))
            except (TypeError, ValueError, AttributeError):
                cam_lo_mm = 0.0
            try:
                cam_hi_mm = float(motors.camera.get_limit_high("mm"))
            except (TypeError, ValueError, AttributeError):
                cam_hi_mm = 35.0

        try:
            curve = load_focus_curve(path, cam_lo_mm, cam_hi_mm)
        except ValueError as exc:
            self._clear_focus_armed()
            self._shell.sig_beep.emit()
            reason = str(exc)
            self._shell.sig_message.emit(
                f"Focus calibration file invalid: {path}. {reason}. "
                "The stack will run without focus compensation. "
                "Load a valid file or uncheck Camera focus compensation."
            )
            self.ui.label_focusStatus.setText(f"Invalid file — {reason}")
            return

        self._armed_focus_curve = curve
        self._armed_focus_curve_path = path
        self._update_focus_status_label()
        self._refresh_autofocus_use_curve_state()

    def _load_demo_focus_curve(self) -> None:
        """Arm the bundled sample focus curve when running in demo mode.

        The sample lives in ``lightsheet/resources/`` next to the demo
        image so it is packaged and present on any checkout. A missing
        sample is silently ignored; the operator can still browse for a
        custom file.
        """
        sample = (
            Path(__file__).resolve().parents[2]
            / "resources"
            / "focus_sample_calibration.json"
        )
        if not sample.exists():
            return
        self.ui.lineEdit_focusCurvePath.setText(str(sample))
        self._on_focus_load()

    def _clear_focus_armed(self) -> None:
        """Disarm the focus curve. build_focus_config/build_focus_curve
        will return None until a new file is loaded."""
        self._armed_focus_curve = None
        self._armed_focus_curve_path = ""
        self._refresh_autofocus_use_curve_state()

    def _update_focus_status_label(self) -> None:
        """Render label_focusStatus and label_focusBlockHint from the
        current armed state and block-size widget."""
        block_size = int(self.ui.doubleSpinBox_focusBlockSize.value())
        self.ui.label_focusBlockHint.setText(
            f"Camera focus is updated once every {block_size} planes. "
            "The last applied position is held between blocks."
        )
        if self._armed_focus_curve is None:
            self.ui.label_focusStatus.setText("Not armed — no file loaded")
            return
        n_points = len(self._armed_focus_curve.stage_pos)
        residual = (
            "on" if self.ui.checkBox_focusAutofocusResidual.isChecked() else "off"
        )
        self.ui.label_focusStatus.setText(
            f"Armed: {n_points} points | block size {block_size} "
            f"| per-block residual {residual}"
        )

    def _on_focus_block_size_edited(self) -> None:
        """editingFinished on doubleSpinBox_focusBlockSize: reject values
        outside the 1..100 schema range with beep + revert to the nearest
        bound. Valid edits update the block-size hint."""
        sb = self.ui.doubleSpinBox_focusBlockSize
        value = sb.value()
        if value < 1.0 or value > 100.0:
            self._shell.sig_beep.emit()
            new_value = 1.0 if value < 1.0 else 100.0
            sb.setValue(new_value)
        self._update_focus_status_label()

    def build_focus_config(self) -> FocusConfig | None:
        """Pre-sample the focus configuration on the GUI thread and return
        a frozen ``FocusConfig`` (or ``None`` when the toggle is unchecked
        or no calibration file is armed).

        The frozen dataclass is safe to share across threads (immutable)
        — the worker thread receives one snapshot and never reads
        ``ui.*``.
        """
        if not self.ui.checkBox_focusEnable.isChecked():
            return None
        if self._armed_focus_curve is None or not self._armed_focus_curve_path:
            return None
        return FocusConfig(
            enabled=True,
            block_size_n=int(self.ui.doubleSpinBox_focusBlockSize.value()),
            autofocus_residual=self.ui.checkBox_focusAutofocusResidual.isChecked(),
            curve_path=self._armed_focus_curve_path,
            residual_gain_mm=self._focus_residual_gain_mm,
            max_residual_mm=self._focus_max_residual_mm,
        )

    def build_focus_curve(self) -> FocusCurve | None:
        """Return the armed ``FocusCurve`` object (or ``None`` when the
        toggle is unchecked or no file is armed)."""
        if not self.ui.checkBox_focusEnable.isChecked():
            return None
        return self._armed_focus_curve

    def _load_autofocus_config(self) -> None:
        """Load the validated [Autofocus] defaults from config.ini into the
        adaptive-autofocus widgets. A missing [Autofocus] section leaves the
        widgets at their FieldSpec defaults. If no focus curve is armed, the
        use-curve seed checkbox is disabled and unchecked.
        """
        from lightsheet.config import cfg_read

        defaults = {
            "Enabled": "",
            "Cadence": "",
            "Residual Gain Mm": "",
            "Max Residual Mm": "",
            "Smoothing": "",
            "Use Curve Seed": "",
        }
        try:
            cfg = cfg_read("config.ini", "Autofocus", defaults)
        except Exception:
            cfg = defaults
        _set = {
            "Enabled": ("checkBox_adaptiveAutofocus", "bool"),
            "Cadence": ("doubleSpinBox_autofocusCadence", "float"),
            "Residual Gain Mm": ("doubleSpinBox_autofocusResidualGain", "float"),
            "Max Residual Mm": ("doubleSpinBox_autofocusMaxResidual", "float"),
            "Smoothing": ("doubleSpinBox_autofocusSmoothing", "float"),
            "Use Curve Seed": ("checkBox_autofocusUseCurve", "bool"),
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
        self._refresh_autofocus_use_curve_state()

    def _refresh_autofocus_use_curve_state(self) -> None:
        """Enable the use-curve seed checkbox only when a focus curve is
        armed, and uncheck it if none is available."""
        cb = self.ui.checkBox_autofocusUseCurve
        if self._armed_focus_curve is None:
            cb.blockSignals(True)
            cb.setChecked(False)
            cb.setEnabled(False)
            cb.blockSignals(False)
        else:
            cb.setEnabled(True)

    def _on_autofocus_toggled(self, checked: bool) -> None:
        """Toggle the adaptive-autofocus sub-surface. The group title and
        master checkbox remain visible; the parameter container, status,
        hint, and progress bar are shown only when adaptive is enabled."""
        self.ui.widget_adaptiveAutofocusFields.setVisible(checked)
        self.ui.line_autofocusSeparator.setVisible(checked)
        self.ui.label_autofocusStatus.setVisible(checked)
        self.ui.label_autofocusHint.setVisible(checked)
        self.ui.progressBar_autofocus.setVisible(False)
        self._update_autofocus_status_label()

    def _on_autofocus_use_curve_toggled(self, checked: bool) -> None:
        """Enable the use-curve checkbox only when a focus curve is armed.
        If the user checks it without an armed curve, beep and reject."""
        if self._armed_focus_curve is None:
            if checked:
                self._shell.sig_beep.emit()
            self.ui.checkBox_autofocusUseCurve.blockSignals(True)
            self.ui.checkBox_autofocusUseCurve.setChecked(False)
            self.ui.checkBox_autofocusUseCurve.setEnabled(False)
            self.ui.checkBox_autofocusUseCurve.blockSignals(False)
        self._update_autofocus_status_label()

    def _update_autofocus_status_label(self) -> None:
        """Render label_autofocusStatus and the fixed hint label from the
        current adaptive state."""
        self.ui.label_autofocusHint.setText(
            "Predicted camera position = feedforward + running residual. "
            "The residual is updated from the saved frame's sharpness and "
            "applied to the next plane."
        )
        if not self.ui.checkBox_adaptiveAutofocus.isChecked():
            self.ui.label_autofocusStatus.setText(
                "Adaptive focus disabled. Enable it to update the camera focus "
                "on the fly during the stack."
            )
            return
        cadence = int(self.ui.doubleSpinBox_autofocusCadence.value())
        gain = self.ui.doubleSpinBox_autofocusResidualGain.value()
        max_res = self.ui.doubleSpinBox_autofocusMaxResidual.value()
        smooth = self.ui.doubleSpinBox_autofocusSmoothing.value()
        using_curve = (
            " · using curve seed"
            if self._armed_focus_curve is not None
            and self.ui.checkBox_autofocusUseCurve.isChecked()
            else ""
        )
        use_curve = self.ui.checkBox_autofocusUseCurve.isChecked()
        if self._armed_focus_curve is None and use_curve:
            self.ui.label_autofocusStatus.setText(
                "No focus curve loaded. Browse and load a curve, or uncheck "
                '"Use loaded focus curve as seed" to start from the current '
                "camera position."
            )
            return
        self.ui.label_autofocusStatus.setText(
            f"Adaptive focus armed · cadence {cadence} · gain {gain:.3f} mm · "
            f"max {max_res:.3f} mm · smoothing {smooth:.2f}{using_curve}"
        )

    def _clamp_autofocus_spinbox(
        self, sb: QDoubleSpinBox, low: float, high: float
    ) -> None:
        """Reject an out-of-schema edit on an adaptive-autofocus spinbox:
        clamp to the nearest bound, beep + emit the documented message,
        and show the out-of-range copy in the status label until the next
        valid edit refreshes it."""
        value = sb.value()
        if value < low or value > high:
            sb.setValue(low if value < low else high)
            self._shell.sig_beep.emit()
            self._shell.sig_message.emit(
                "Autofocus parameter out of range; value reset to the "
                "nearest valid bound."
            )
            self.ui.label_autofocusStatus.setText(
                "Autofocus parameter out of range; value reset to the "
                "nearest valid bound."
            )
            return
        self._update_autofocus_status_label()

    def _on_autofocus_cadence_edited(self) -> None:
        """editingFinished on cadence: clamp to the 1..1000 schema range."""
        self._clamp_autofocus_spinbox(
            self.ui.doubleSpinBox_autofocusCadence, 1.0, 1000.0
        )

    def _on_autofocus_residual_gain_edited(self) -> None:
        """editingFinished on residual gain: clamp to the 0..1 range."""
        self._clamp_autofocus_spinbox(
            self.ui.doubleSpinBox_autofocusResidualGain, 0.0, 1.0
        )

    def _on_autofocus_max_residual_edited(self) -> None:
        """editingFinished on max residual: clamp to the 0..5 range."""
        self._clamp_autofocus_spinbox(
            self.ui.doubleSpinBox_autofocusMaxResidual, 0.0, 5.0
        )

    def _on_autofocus_smoothing_edited(self) -> None:
        """editingFinished on smoothing: clamp to the 0..1 range."""
        self._clamp_autofocus_spinbox(
            self.ui.doubleSpinBox_autofocusSmoothing, 0.0, 1.0
        )

    def build_autofocus_config(self) -> AutofocusConfig | None:
        """Pre-sample the adaptive autofocus configuration on the GUI thread
        and return a frozen ``AutofocusConfig`` (or ``None`` when the toggle is
        unchecked).

        The frozen dataclass is safe to share across threads (immutable) — the
        worker thread receives one snapshot and never reads ``ui.*``.
        """
        if not self.ui.checkBox_adaptiveAutofocus.isChecked():
            return None
        return AutofocusConfig(
            enabled=True,
            cadence=int(self.ui.doubleSpinBox_autofocusCadence.value()),
            residual_gain_mm=self.ui.doubleSpinBox_autofocusResidualGain.value(),
            max_residual_mm=self.ui.doubleSpinBox_autofocusMaxResidual.value(),
            smoothing=self.ui.doubleSpinBox_autofocusSmoothing.value(),
            use_curve_seed=self.ui.checkBox_autofocusUseCurve.isChecked(),
        )

    def _on_autofocus_status(
        self,
        plane: int,
        n_planes: int,
        predicted: float | None,
        residual: float,
        sharp: float,
        state: str,
    ) -> None:
        """GUI-thread slot for queued worker autofocus status updates.

        Renders the documented live status copy for tracking, holding,
        clamped, waiting, and over-travel error states, and mirrors the
        per-plane progress into ``progressBar_autofocus``.
        """
        if n_planes > 0 and not self.ui.progressBar_autofocus.isHidden():
            self.ui.progressBar_autofocus.setRange(0, n_planes)
            self.ui.progressBar_autofocus.setValue(plane)

        if state == "waiting" or predicted is None:
            self.ui.label_autofocusStatus.setText(
                f"Plane {plane}/{n_planes} · acquiring first frames"
            )
            return
        if state == "error":
            self.ui.label_autofocusStatus.setText(
                f"Focus move rejected at plane {plane}: camera target "
                f"{predicted:.3f} mm is outside travel limits. "
                "Stack acquisition aborted."
            )
            self.ui.progressBar_autofocus.setVisible(False)
            return
        self.ui.label_autofocusStatus.setText(
            f"Plane {plane}/{n_planes} · pred {predicted:.3f} mm · "
            f"res {residual:+.3f} mm · sharp {sharp:.2e} · {state}"
        )

    def set_autofocus_running(self, running: bool) -> None:
        """Update the adaptive-autofocus UI for stack start/stop.

        When a stack starts, the adaptive config widgets are disabled so the
        operator cannot edit the pre-sampled ``AutofocusConfig``, and the
        per-plane progress bar is shown. When the stack finishes or aborts,
        the widgets are re-enabled and the progress bar is hidden.
        """
        if not self.ui.checkBox_adaptiveAutofocus.isChecked():
            self.ui.progressBar_autofocus.setVisible(False)
            return

        if running:
            n_planes = int(getattr(self._shell, "number_of_planes", 0) or 0)
            self.ui.progressBar_autofocus.setRange(0, n_planes)
            self.ui.progressBar_autofocus.setValue(0)
            self.ui.progressBar_autofocus.setVisible(True)
            self.ui.checkBox_adaptiveAutofocus.setEnabled(False)
            self.ui.widget_adaptiveAutofocusFields.setEnabled(False)
            self.ui.checkBox_autofocusUseCurve.setEnabled(False)
        else:
            self.ui.progressBar_autofocus.setVisible(False)
            self.ui.checkBox_adaptiveAutofocus.setEnabled(True)
            # Re-enable the parameter container only when adaptive is on; the
            # use-curve checkbox follows the armed-curve policy.
            self.ui.widget_adaptiveAutofocusFields.setEnabled(
                self.ui.checkBox_adaptiveAutofocus.isChecked()
            )
            self._refresh_autofocus_use_curve_state()
