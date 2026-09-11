"""UI-only delegate slots split out of ``controller.py``.

The shell's safety-critical surface (E-stop kill path, hardware bring-up,
shutdown ordering) stays in ``controller.py``; this module carries the
pure presentation delegates — theme toggles, pane show/hide, mode-badge
and progress mirroring, channel tint, and the stack-param persistence
helpers — as a plain mixin so ``Controller_MainWindow`` reads as
safety + lifecycle code only.

The mixin has no ``__init__`` and no ``QObject`` base: methods resolve on
the shell instance through the MRO, and ``self.`` attribute reads work
identically to their former in-class form. ``@Slot`` decorators are kept
verbatim so every bound-method ``connect`` site is unchanged.

Receivers of signals that workers emit from their ``QThread``
(``sig_message``, ``sig_progress_update``, ``sig_*_trajectory``) must
stay declared in ``Controller_MainWindow``'s own class body: PySide6
classifies a bound method as a real queued slot only while it is defined
on the receiver's class, and a mixin-inherited method would run on the
emitting worker thread instead.
"""

from __future__ import annotations

import contextlib
import logging
import webbrowser
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import QAbstractButton

from lightsheet import CONFIG_PATH
from lightsheet.config import cfg_read, cfg_write
from lightsheet.gui.panels.properties_dialog import Properties_Dialog
from lightsheet.wavelength_color import wavelength_to_hex

if TYPE_CHECKING:
    from lightsheet.gui.shell.controller import Controller_MainWindow

logger = logging.getLogger(__name__)


class _ShellUiDelegatesMixin:
    """UI-only delegate slots for ``Controller_MainWindow``.

    Pure presentation methods — no hardware ownership, no lifecycle
    responsibility. Kept as methods on the shell through inheritance so
    every signal ``connect`` site and ``self.<method>`` caller resolves
    through the MRO unchanged.
    """

    def _save_stack_params(self: Controller_MainWindow) -> None:
        """Persist the last stack's start/end/step to config.ini so a
        re-run does not required re-driving the stage. Called on close.
        Skipped in demo mode so the test suite (which constructs many
        controllers with demo=True and tears them down concurrently under
        xdist) does not corrupt the real config.ini.

        Positions are stored in millimetres — the unit the plane spinboxes
        display — even though ``stack_starting_plane``/``stack_ending_plane``
        are micrometres internally. The step stays in µm (its spinbox's
        display unit). Storing the display unit makes stale µm-magnitude
        values written by earlier versions self-healing: interpreted as mm
        they fall outside the travel limits and are discarded on load
        instead of being clamped into the spinbox."""
        if getattr(self, "_demo_mode", False):
            return
        start = self.stack_starting_plane
        end = self.stack_ending_plane
        step = self.stack_panel.ui.doubleSpinBox_acqPlaneStepSize.value()
        cfg_write(
            str(CONFIG_PATH),
            "Controller",
            {
                "StackLastStart": "" if start is None else f"{start / 1000.0:.4f}",
                "StackLastEnd": "" if end is None else f"{end / 1000.0:.4f}",
                "StackLastStep": f"{step:.4f}",
            },
        )

    def _load_stack_params(self: Controller_MainWindow) -> None:
        """Load the last stack's start/end/step from config.ini and
        populate the spinboxes + set the shell flags if present.

        Persisted positions are in millimetres (the spinbox display
        unit); the internal ``stack_starting_plane``/``stack_ending_plane``
        stay in micrometres — safety-critical, a missing conversion is a
        1000x motor over-travel error. Each value is validated against the
        live horizontal travel limits BEFORE touching the widget: an
        out-of-range or unparseable value (including stale µm-magnitude
        values from versions that persisted the internal unit) is
        discarded with an operator message rather than clamped into the
        spinbox.

        Skipped in demo mode so the test suite (which constructs many
        controllers with demo=True and tears them down concurrently under
        xdist) does not inherit persisted state from the real config.ini."""
        if getattr(self, "_demo_mode", False):
            return
        cfg = cfg_read(
            str(CONFIG_PATH),
            "Controller",
            {
                "StackLastStart": "",
                "StackLastEnd": "",
                "StackLastStep": "",
            },
        )
        start_s = str(cfg.get("StackLastStart", "")).strip()
        end_s = str(cfg.get("StackLastEnd", "")).strip()
        step_s = str(cfg.get("StackLastStep", "")).strip()
        # Read the horizontal travel limits once, in the display unit.
        # If they cannot be read (mock shell, missing motor handle) every
        # persisted position is unverifiable and is skipped.
        try:
            low_mm = float(self.motors.horizontal.get_limit_low("mm"))
            high_mm = float(self.motors.horizontal.get_limit_high("mm"))
            limits_ok = True
        except (AttributeError, TypeError, ValueError):
            limits_ok = False
        if start_s and limits_ok:
            try:
                start_mm = float(start_s)
            except ValueError:
                start_mm = None
            if start_mm is not None and low_mm <= start_mm <= high_mm:
                # Programmatic setValue does not emit editingFinished, so
                # _on_first_plane_edited does not re-enter. The spinbox
                # displays mm; the internal var stays µm.
                self.stack_panel.ui.doubleSpinBox_acqFirstPlane.setValue(start_mm)
                self.stack_starting_plane = start_mm * 1000.0
                self.stack_first_plane_set = True
            else:
                self.sig_message.emit(
                    f"Persisted stack start {start_s} mm is outside the "
                    f"stage travel limits ({low_mm:.3f}\u2013{high_mm:.3f} mm) "
                    "and was not restored. Re-drive the stage and press Set."
                )
        if end_s and limits_ok:
            try:
                end_mm = float(end_s)
            except ValueError:
                end_mm = None
            if end_mm is not None and low_mm <= end_mm <= high_mm:
                self.stack_panel.ui.doubleSpinBox_acqLastPlane.setValue(end_mm)
                self.stack_ending_plane = end_mm * 1000.0
                self.stack_last_plane_set = True
            else:
                self.sig_message.emit(
                    f"Persisted stack end {end_s} mm is outside the "
                    f"stage travel limits ({low_mm:.3f}\u2013{high_mm:.3f} mm) "
                    "and was not restored. Re-drive the stage and press Set."
                )
        if step_s:
            with contextlib.suppress(ValueError):
                self.stack_panel.ui.doubleSpinBox_acqPlaneStepSize.setValue(
                    float(step_s)
                )


    @Slot(QAbstractButton)
    def updateUi_save_format_changed(
        self: Controller_MainWindow, button: QAbstractButton
    ) -> None:
        """Map the clicked format radio to a lowercase constant and set
        ``self.save_format`` for the current session. This is session-only
        — it does NOT write config.ini. The config-driven default is
        reflected at startup; the operator override lives until the app
        exits."""
        ui = self.save_panel.ui
        if button is ui.radioButton_saveFormat_hdf5:
            self.save_format = "hdf5"
        elif button is ui.radioButton_saveFormat_zarr:
            self.save_format = "zarr"
        elif button is ui.radioButton_saveFormat_both:
            self.save_format = "both"
        self.sig_message.emit(f"Save format set to {self.save_format} (session only)")

    def open_properties_dialog(self: Controller_MainWindow) -> None:
        """Open the dialog window for showing properties"""
        self.properties_dialog = Properties_Dialog(self)
        self.properties_dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.properties_dialog.open()
        self.properties_dialog.get_properties()

    def open_help(self: Controller_MainWindow) -> None:
        """Open the operator manual (Guide.pdf, French reference).

        The path is built cross-platform so the Help menu works on the
        Mac dev box as well as the Windows rig.
        """
        guide_pdf = Path(__file__).resolve().parent.parent / "Guide.pdf"
        webbrowser.open_new(str(guide_pdf))

    def updateUi_light_theme(self: Controller_MainWindow) -> None:
        self.sig_stylesheet.emit("light")
        # Persist the operator's choice to config.ini under [Controller] Theme.
        # show an ephemeral status-bar hint. Skipped in demo mode so the
        # test suite (which constructs many controllers with demo=True and
        # tears them down concurrently under xdist) does not corrupt the
        # real config.ini — mirrors the _save_stack_params guard. The
        # sig_stylesheet emission and action-checkmark stay outside the
        # guard (in-memory only).
        if not getattr(self, "_demo_mode", False):
            cfg_write(str(CONFIG_PATH), "Controller", {"Theme": "light"})
        self.ui.statusbar.showMessage("Theme: Light (saved).", 3000)
        self.ui.action_lightTheme.setChecked(True)

    def updateUi_dark_theme(self: Controller_MainWindow) -> None:
        self.sig_stylesheet.emit("dark")
        if not getattr(self, "_demo_mode", False):
            cfg_write(str(CONFIG_PATH), "Controller", {"Theme": "dark"})
        self.ui.statusbar.showMessage("Theme: Dark (saved).", 3000)
        self.ui.action_darkTheme.setChecked(True)

    def updateUi_follow_system_theme(self: Controller_MainWindow) -> None:
        """Emit the 'system' stylesheet token so the theme manager follows
        the operating system's light/dark setting. Mirrors
        updateUi_light_theme / updateUi_dark_theme; the theme manager
        resolves 'system' to the current OS appearance and persists the
        override across sessions."""
        self.sig_stylesheet.emit("system")
        if not getattr(self, "_demo_mode", False):
            cfg_write(str(CONFIG_PATH), "Controller", {"Theme": "system"})
        self.ui.statusbar.showMessage("Theme: Follow System (saved).", 3000)
        self.ui.action_followSystemTheme.setChecked(True)

    def updateUi_show_hide_images_pane(self: Controller_MainWindow) -> None:
        """Toggle the images pane via splitter.setSizes() (audit #7).

        The View-menu action and the QSplitter drag are two mechanisms
        that can hide/show a pane. Routing the menu through
        splitter.setSizes() (instead of show()/hide() on the pane widget
        directly) keeps the splitter sizes authoritative — the menu and
        the splitter stay in sync, and childrenCollapsible=False blocks
        handle-drag-to-zero so hiding is via the menu only.

        The pane has a non-zero minimum width (320 px, the floor),
        so setSizes([0, total]) alone cannot shrink it to 0 — Qt's
        splitter respects the widget minimum. Temporarily setting
        minimumWidth=0 + maximumWidth=0 lets the splitter reach 0 (the
        standard Qt pattern for a collapsible section under
        childrenCollapsible=False); restoring both to their defaults
        (minimum 320, maximum 16777215) lets the splitter allocate
        space again on re-show.
        """
        splitter = self.ui.splitter
        images_pane = self.ui.imagesPane
        # imagesPane is the FIRST widget in the splitter (index 0).
        # A pane is "visible" in the splitter sense when its size > 0.
        images_visible = splitter.sizes()[0] > 0
        total = splitter.width() or sum(splitter.sizes()) or 1
        if images_visible:
            images_pane.setMinimumWidth(0)
            images_pane.setMaximumWidth(0)
            splitter.setSizes([0, total])
            self.ui.action_ShowHideImagesPane.setChecked(False)
        else:
            # Restore the floor minimum + the Qt default maximum,
            # then a sensible default (50/50 split) on re-show.
            images_pane.setMinimumWidth(320)
            images_pane.setMaximumWidth(16777215)
            half = total // 2
            splitter.setSizes([half, total - half])
            self.ui.action_ShowHideImagesPane.setChecked(True)

    def updateUi_show_hide_controls_pane(self: Controller_MainWindow) -> None:
        """Toggle the controls pane via splitter.setSizes() (audit #7).

        Mirrors updateUi_show_hide_images_pane — controlsPane is the
        SECOND widget in the splitter (index 1). The pane has a 360 px
        minimum width (the controls floor), so minimumWidth=0 +
        maximumWidth=0 is used to let the splitter reach 0 on hide.
        """
        splitter = self.ui.splitter
        controls_pane = self.ui.controlsPane
        controls_visible = splitter.sizes()[1] > 0
        total = splitter.width() or sum(splitter.sizes()) or 1
        if controls_visible:
            controls_pane.setMinimumWidth(0)
            controls_pane.setMaximumWidth(0)
            splitter.setSizes([total, 0])
            self.ui.action_ShowHideControlsPane.setChecked(False)
        else:
            controls_pane.setMinimumWidth(360)
            controls_pane.setMaximumWidth(16777215)
            half = total // 2
            splitter.setSizes([total - half, half])
            self.ui.action_ShowHideControlsPane.setChecked(True)

    def updateUi_show_hide_message_log(self: Controller_MainWindow) -> None:
        """Toggle the message log via message_splitter.setSizes() (audit #4
        + audit #7 sync pattern).

        Mirrors updateUi_show_hide_images_pane / _controls_pane — the
        message log is now a vertical QSplitter section inside
        controlsPane (message_splitter), not a standalone widget. Routing
        the View-menu toggle through splitter.setSizes() keeps the splitter
        sizes authoritative so the menu and the splitter handle stay in
        sync. childrenCollapsible=False blocks handle-drag-to-zero, so
        hiding is via the menu only (the operator can still drag the log
        taller/shorter, but not collapse it to 0).

        The log has a non-zero minimum height (96 px, ~5 lines), so
        setSizes([total, 0]) alone cannot shrink it to 0 — Qt's splitter
        respects the widget minimum. Temporarily setting minimumHeight=0
        + maximumHeight=0 lets the splitter reach 0 (the standard Qt
        pattern for a collapsible section under
        childrenCollapsible=False); restoring both to their defaults
        (minimum 96, maximum 16777215) lets the splitter allocate space
        again on re-show.

        The log section is the SECOND widget in message_splitter (index
        1). A log section size > 0 means "visible".
        """
        splitter = self.ui.message_splitter
        log = self.ui.plainTextEdit_messageLog
        log_visible = splitter.sizes()[1] > 0
        total = sum(splitter.sizes()) or splitter.height() or 1
        if log_visible:
            log.setMinimumHeight(0)
            log.setMaximumHeight(0)
            splitter.setSizes([total, 0])
            self.ui.action_ShowHideMessageLog.setChecked(False)
        else:
            # Restore the ~5-line default minimum + the Qt default maximum,
            # then a sensible default (96 px log) on re-show.
            log.setMinimumHeight(96)
            log.setMaximumHeight(16777215)
            default_log_height = 96
            splitter.setSizes([total - default_log_height, default_log_height])
            self.ui.action_ShowHideMessageLog.setChecked(True)

    def _update_mode_badge(
        self: Controller_MainWindow,
        mode: str,
        state: str = "",
        plane: int = 0,
        total: int = 0,
        queue_row: int = 0,
        queue_total: int = 0,
    ) -> None:
        """Update the mode/state badge in the E-stop toolbar.

        The badge mirrors the progress bar value into the badge text so
        the operator never has to look at the status bar mid-run. The
        badge uses QDarkStyle default text color + bold weight — no
        accent color.

        Modes:
        - idle → "IDLE"
        - preview → "PREVIEW"
        - live → "LIVE"
        - single → "SINGLE"
        - stack running → "STACK RUNNING — plane {plane}/{total}"
        - stack in a queue → appended " (row {queue_row}/{queue_total})"
        - focus running (legacy or adaptive) → "FOCUS RUNNING — plane {plane}/{total}"
        - focus aborted (legacy or adaptive) → "FOCUS ABORTED — plane {plane}/{total}"
        """
        if mode == "IDLE":
            text = "IDLE"
        elif mode == "PREVIEW":
            text = "PREVIEW"
        elif mode == "LIVE":
            text = "LIVE"
        elif mode == "SINGLE":
            text = "SINGLE"
        elif mode == "STACK":
            n = plane if plane > 0 else 1
            n_total = total if total > 0 else int(getattr(self, "number_of_planes", 0))
            text = (
                f"STACK {state} \u2014 plane {n}/{n_total}"
                if state
                else (f"STACK RUNNING \u2014 plane {n}/{n_total}")
            )
            if queue_row and queue_total:
                text += f" (row {queue_row}/{queue_total})"
        elif mode == "ADAPTIVE":
            n = plane if plane > 0 else 1
            n_total = total if total > 0 else int(getattr(self, "number_of_planes", 0))
            text = f"ADAPTIVE {state} \u2014 plane {n}/{n_total}"
            if queue_row and queue_total:
                text += f" (row {queue_row}/{queue_total})"
        elif mode == "FOCUS":
            n = plane if plane > 0 else 1
            n_total = total if total > 0 else int(getattr(self, "number_of_planes", 0))
            text = f"FOCUS {state} \u2014 plane {n}/{n_total}"
            if queue_row and queue_total:
                text += f" (row {queue_row}/{queue_total})"
        else:
            text = mode
        # MULTI-CH pill: a persistent suffix appended to the mode text
        # when both auto-laser checkboxes are checked (the multi-channel
        # activator). The pill is tied to the checkbox-pair STATE, not to
        # the per-mode behavior, so it appears/disappears synchronously
        # with checking/unchecking the second auto-laser box regardless
        # of mode. The pill inherits the badge's existing QDarkStyle
        # default text color + bold weight — NO green accent (the green
        # token is reserved exclusively for laser ● ON status, the
        # one-laser-energized invariant's visual corollary). The pill reads
        # the current model snapshot — the auto-laser intent source of
        # truth committed by the checkbox-stateChanged path.
        _auto1, _auto2 = self.state.snapshot().auto_lasers
        if _auto1 and _auto2:
            text = text + " · MULTI-CH"
        self.ui.label_modeBadge.setText(text)


    def _cache_auto_laser_flags(self: Controller_MainWindow) -> None:
        """Commit the auto-laser checkboxes to the model. GUI thread only.

        The model is the single source of truth for auto-laser intent:
        acquisition workers receive the pair frozen inside their spawn
        ``MicroscopeSnapshot``, and ``stop_lasers()`` reads the live
        ``laser.active`` state — never these flags. Called at every
        mode-*start* entry point that leads to a worker calling
        start_lasers()/stop_lasers().
        """
        self.state.set_auto_lasers(
            self.laser_panel.ui.checkBox_laserOneAutomatic.isChecked(),
            self.laser_panel.ui.checkBox_laserTwoAutomatic.isChecked(),
        )
        # Re-render the stack-plan summary synchronously with the checkbox
        # change so the 2ch re-estimate (2x time/size + "2 ch x N planes"
        # clause) appears the instant the operator toggles the second
        # auto-laser box. Guarded with hasattr for early-init safety
        # (stack_panel may not be wired yet during two-phase construction).
        stack_panel = getattr(self, "stack_panel", None)
        if stack_panel is not None and hasattr(
            stack_panel, "_render_stack_plan_summary"
        ):
            stack_panel._render_stack_plan_summary()
        # Keep the channel-radio visibility in sync with the checkbox-pair
        # state (the radio is shown only when both auto-lasers are checked).
        self._update_channel_radio_visibility()

    def _update_channel_radio_visibility(self: Controller_MainWindow) -> None:
        """Show the channel-radio when both auto-laser checkboxes are
        checked; hide it otherwise. Single-channel back-compat: the radio
        is HIDDEN (not disabled) so the ImageView area stays visually
        identical to today's single-channel experience. Guarded for
        early-init (channel_radio may not be constructed yet).

        When entering multi-channel, the currently-displayed frame is
        immediately tinted with the selected channel's wavelength color
        (L1 green by default) so the operator sees the L1/L2 cue the
        instant the radio appears — without first clicking a button.
        When leaving multi-channel, the tint is cleared (back to
        grayscale) so the single-channel display matches today's path."""
        radio = getattr(self, "channel_radio", None)
        if radio is None:
            return
        # The checkbox stateChanged slot commits to the model before this
        # runs (via _cache_auto_laser_flags), so one model snapshot is the
        # source of truth for the pair state.
        _a1, _a2 = self.state.snapshot().auto_lasers
        both = _a1 and _a2
        if both:
            radio.show_for_multi_channel()
            # Apply the selected channel's tint to the currently-displayed
            # frame so the color cue is visible immediately on enable.
            # Only the tint is applied — the LevelsBar window is NOT reset
            # here because the displayed frame does not change when
            # enabling multi-channel (it is still the demo image / last
            # live frame), and resetting the window would reflow the
            # ImageView geometry (the LevelsBar window setters trigger a
            # layout recompute). The window reset belongs only in the
            # radio-click path where switching channels changes the frame.
            checked_id = -1
            for idx in (0, 1):
                if radio.is_checked(idx):
                    checked_id = idx
                    break
            if checked_id >= 0:
                self._apply_channel_tint(checked_id, reset_window=False)
        else:
            radio.hide_for_single_channel()
            # Clear the tint so the single-channel display is grayscale.
            frame = self.ui.imageView._last_frame
            if frame is not None:
                self.ui.imageView.setImage(frame, tint=None)

    def _apply_channel_tint(
        self: Controller_MainWindow, channel_idx: int, reset_window: bool = True
    ) -> None:
        """Apply the per-channel LUT tint for ``channel_idx`` to the
        currently-displayed frame. Shared by the radio-click slot and the
        visibility-update path.

        When ``reset_window`` is True (the radio-click path), the LevelsBar
        window is reset to the displayed frame's min/max so a freshly
        switched channel is visible at a sensible contrast. When False
        (the visibility-update path on enabling multi-channel), the window
        is left alone — the displayed frame does not change on enable, and
        resetting the window would reflow the ImageView geometry.

        Falls back to the ImageView's last frame (the demo image at boot,
        or the last live/preview frame) when no acquisition frame exists
        for the channel. No-op if the channel index is out of range, the
        laser has no wavelength, or nothing is displayed."""
        if not (0 <= channel_idx < len(self.lasers)):
            return
        wl = getattr(self.lasers[channel_idx], "wavelength", None)
        if wl is None:
            return
        frame = self.reconstructed_frames.get(wl)
        if frame is None:
            # No acquisition frame for this channel yet — fall back to the
            # frame currently displayed in the ImageView (the boot demo
            # image, or the last live/preview frame) so the operator can
            # still see the per-channel LUT tint without an acquisition.
            frame = self.ui.imageView._last_frame
            if frame is None:
                return
        color = wavelength_to_hex(int(wl))
        self.ui.imageView.setImage(frame, tint=color)
        if not reset_window:
            return
        # Reset the LevelsBar window to the displayed frame's observed
        # min/max so the new channel is visible at a sensible contrast.
        # Set window_max first so the window_min setter (which clamps to
        # [range_min, window_max]) does not clamp the new min down to the
        # old window_max. The LevelsBar setters permit equality (a
        # degenerate window renders as a binary threshold, which is the
        # sane display for a uniform frame).
        try:
            lo = int(frame.min())
            hi = int(frame.max())
        except (ValueError, TypeError):
            return
        if hi >= lo:
            self.ui.levelsBar.window_max = hi
            self.ui.levelsBar.window_min = lo

    def _on_auto_laser_checkbox_changed(
        self: Controller_MainWindow, _state: int
    ) -> None:
        """Auto-laser checkbox stateChanged slot — re-cache the flags
        (so the badge pill + summary re-render + radio visibility track
        the checkbox-pair state synchronously) when the operator toggles
        an auto-laser checkbox outside a mode-start entry point. GUI
        thread only."""
        self._cache_auto_laser_flags()

    @Slot(int)
    def _on_channel_radio_clicked(
        self: Controller_MainWindow, channel_idx: int
    ) -> None:
        """Channel-radio idClicked slot — switch the ImageView to the
        selected channel's frame and reset the LevelsBar window to the
        displayed frame's min/max.

        Delegates to ``_apply_channel_tint`` (shared with the
        visibility-update path) so the tint application logic (frame
        fallback + LevelsBar window reset) is identical whether the
        operator clicks L1/L2 or the tint is auto-applied on enabling
        the second auto-laser."""
        self._apply_channel_tint(channel_idx)


