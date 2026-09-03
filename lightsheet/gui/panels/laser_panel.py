"""LaserPanelWidget — per-panel widget/controller for the laser controls.

Owns the laser updateUi_* slots. Holds a shell reference, reads
``self._shell.ui.<objectName>`` for its widgets, emits through
``self._shell.sig_*``, and delegates HAL writes to ``self._shell._hw``.

The 4 laser daemon ``threading.Thread`` spawns stay ``threading.Thread``
per the lock-free E-stop kill path contract. They are NOT migrated to
QThread — a queued slot dispatch window between ``estop_event.set()`` and
the slot's first estop poll would re-energize a Class IIIB laser past the
kill path.

The E-stop kill path itself (``updateUi_estop_pressed``) stays in the thin
shell — it is NOT in this panel.
"""

from __future__ import annotations

import threading
import typing

from PySide6.QtCore import Slot
from PySide6.QtWidgets import QLabel, QMessageBox, QWidget

from lightsheet.gui.panels.ui_laser_panel import Ui_LaserPanel
from lightsheet.gui.styles import colors as _c
from lightsheet.gui.styles import symbols as _sym
from lightsheet.gui.styles import typography as _t
from lightsheet.gui.widgets.field_spec import FIELD_SPECS

if typing.TYPE_CHECKING:
    from lightsheet.gui.shell.controller import Controller_MainWindow


class LaserPanelWidget(QWidget):
    """Laser controls panel — owns laser amplitude/toggle/status/readback slots.

    The per-laser status/readback QLabels (``label_laserOneStatus`` etc.) and
    the L2 Refresh Power button are defined in ``ui_laser_panel.ui`` so they
    share the panel's layout/style. The panel slots that update them reference
    ``self.ui.label_laser*`` (panel-local, hybrid ownership).
    """

    def __init__(self, shell: Controller_MainWindow) -> None:
        super().__init__()
        self._shell = shell
        self.ui = Ui_LaserPanel()
        self.ui.setupUi(self)

        # Initialize both laser status labels to the OFF state with a
        # color-blind-safe hollow bullet; the first poll will update if
        # the real state differs.
        self._optimistic_echo(self.ui.label_laserOneStatus, False)
        self._optimistic_echo(self.ui.label_laserTwoStatus, False)

        # Apply the declarative FieldSpec policy table to every promoted
        # FieldSpecSpinBox by objectName. FieldSpec min/max are a SOFT
        # widget-layer block; the two-layer runtime clamp and the
        # config_schema startup gate are the safety-critical clamps.
        for obj_name, spec in FIELD_SPECS.items():
            w = getattr(self.ui, obj_name, None)
            if w is not None and hasattr(w, "applySpec"):
                w.applySpec(spec)

    @Slot(int, str, str)
    def updateUi_laser_readback(self, idx: int, text: str, tooltip: str) -> None:
        """GUI-thread slot — maps a (idx, text, tooltip) emit from
        sig_laser_readback to the per-laser readback QLabel. text is the
        formatted power string ('{value:.1f} mW' or '{power:.1f} mW (cmd)');
        tooltip is the stale-value explanation for the fallback case, or
        '' for a live readback (which clears any prior stale-value
        tooltip). The label list is indexed by laser index.
        """
        labels = [self.ui.label_laserOneReadback, self.ui.label_laserTwoReadback]
        labels[idx].setText(text)
        labels[idx].setToolTip(tooltip)

    @Slot()
    def updateUi_laser2_refresh_clicked(self) -> None:
        """Manual Refresh Power button handler — re-queries the L2 laser
        status + power readback on demand. The readback refresh and the
        status poll each acquire the L2 per-instance lock independently
        with acquire(blocking=False); if a power write is in progress,
        both are silent no-ops (the operator can retry).

        Works uniformly across backends: ``get_output_power()`` is on the
        ILaser contract (IBeamSmartLaser queries the serial engine;
        DAQLaser and the mock laser backend return the staged mW power),
        so no demo-mode gate is needed."""
        self._shell._hw._refresh_laser2_readback_async()  # ty: ignore[unresolved-attribute]
        self._shell._hw._poll_laser_status([1])  # ty: ignore[unresolved-attribute]

    @Slot(int, str)
    def updateUi_laser_status(self, idx: int, status: str) -> None:
        """GUI-thread slot — maps a (idx, status) emit from
        sig_laser_status to the per-laser QLabel text + semantic color,
        and corrects the toggle button checked state to match the HAL
        state. status is 'active' / 'inactive' / 'error' (set by
        _poll_laser_status). The label list is indexed by laser index.

        The button checked-state correction closes the optimistic-echo
        hazard window: the toggle slot sets the label + button
        optimistically on press, and the next poll re-aligns both with
        the real HAL state (e.g. if the toggle failed or the E-stop
        killed the laser between the press and the poll, the label and
        button revert to OFF here).
        """
        labels = [self.ui.label_laserOneStatus, self.ui.label_laserTwoStatus]
        buttons = [
            self.ui.pushButton_laserOneToggle,
            self.ui.pushButton_laserTwoToggle,
        ]
        if status == "active":
            labels[idx].setText(f"{_sym.LASER_ON} ON")
            labels[idx].setStyleSheet(f"color: {_c.SUCCESS}; {_t.BOLD}")
            buttons[idx].setChecked(True)
        elif status == "inactive":
            labels[idx].setText(f"{_sym.LASER_OFF} OFF")
            labels[idx].setStyleSheet(f"color: {_c.DISABLED}; {_t.BOLD}")
            buttons[idx].setChecked(False)
        else:  # "error"
            labels[idx].setText(f"{_sym.LASER_FAULT} FAULT")
            labels[idx].setStyleSheet(f"color: {_c.DANGER}; {_t.BOLD}")
            buttons[idx].setChecked(False)

    def updateUi_laser1_amplitude(self) -> None:
        # Debounce-only slot: restart the 300ms single-shot timer so rapid
        # keystrokes coalesce into a single committed write. The actual
        # (scaled, thread-offloaded) HAL write happens in _apply_laser1_amplitude
        # when the timer fires. No hardware write happens here.
        #
        # Capture the spinbox value into laser1_power_pct NOW (on the GUI
        # thread) rather than only when the debounce timer fires. This keeps
        # the staged percentage current for _toggle_laser1's just-on path,
        # which reads laser1_power_pct — without this, toggling the laser
        # within the 300ms debounce window after a spinbox edit would apply
        # the OLD percentage and the operator would see the wrong power for
        # 300ms until the debounce fires. The debounce timer still governs
        # when the actual DAQ write happens; this only updates the staged
        # value the toggle reads.
        self._shell.laser1_power_pct = self.ui.doubleSpinBox_laserOneAmplitude.value()
        self._shell._laser1_amplitude_timer.start(300)

    def updateUi_laser2_amplitude(self) -> None:
        # Debounce-only slot for laser 2 (iBeam). See updateUi_laser1_amplitude.
        # Capture the staged percentage now for the same reason as laser 1:
        # _toggle_laser2's just-on path reads laser2_power_pct.
        self._shell.laser2_power_pct = self.ui.doubleSpinBox_laserTwoAmplitude.value()
        self._shell._laser2_amplitude_timer.start(300)

    def _apply_laser1_amplitude(self) -> None:
        """Debounce timeout slot (GUI thread): store the staged percentage
        and offload the scaled DAQ write to a worker thread so the GUI event
        loop is never blocked on a DAQ round-trip. The write itself moved
        to HardwareManager._write_laser1_power — the slot just spawns the
        thread targeting the collaborator method."""
        pct = self.ui.doubleSpinBox_laserOneAmplitude.value()
        self._shell.laser1_power_pct = pct
        assert self._shell._hw is not None
        threading.Thread(
            target=self._shell._hw._write_laser1_power,
            args=(pct,),
            daemon=True,
        ).start()

    def _apply_laser2_amplitude(self) -> None:
        """Debounce timeout slot (GUI thread): store the staged percentage
        and offload the scaled iBeam serial write to a worker thread
        targeting HardwareManager._write_laser2_power."""
        pct = self.ui.doubleSpinBox_laserTwoAmplitude.value()
        self._shell.laser2_power_pct = pct
        assert self._shell._hw is not None
        threading.Thread(
            target=self._shell._hw._write_laser2_power,
            args=(pct,),
            daemon=True,
        ).start()

    def laser1_toggle_button(self) -> None:
        """Laser 1 toggle button handler.

        The button is checkable: Qt toggles ``isChecked()`` BEFORE emitting
        ``clicked``, so on entry ``isChecked()`` is the NEW (desired) state.
        The handler:
        1. Optimistically echoes the desired state to the status label
           (ON green / OFF gray) on the GUI thread, BEFORE the toggle
           thread starts — so the label is never stale after a press.
        2. If turning ON and the first-energize flag is not yet set, shows
           a confirmation dialog (Class IIIB laser safety). Cancel reverts
           the button + label and does NOT spawn the toggle thread.
           "Don't warn again this session" sets the per-session flag.
        3. Spawns the toggle thread (threading.Thread, daemon) targeting
           HardwareManager._toggle_laser1 — the threading model is
           unchanged (no QThread migration; the lock-free E-stop kill path
           requires no queued-slot dispatch window).

        The next poll (sig_laser_status → updateUi_laser_status) corrects
        both the label and the button checked state if the HAL state
        differs (e.g. the toggle failed or the E-stop killed the laser
        between the press and the poll).
        """
        btn = self.ui.pushButton_laserOneToggle
        label = self.ui.label_laserOneStatus
        turning_on = btn.isChecked()
        self._optimistic_echo(label, turning_on)
        if turning_on and not self._shell._laser1_first_energize_done:
            choice = self._show_first_energize_dialog(0)
            if choice == "cancel":
                # Revert the optimistic echo + button checked state; do
                # NOT spawn the toggle thread. The per-session flag stays
                # unset so the next energize still warns.
                btn.setChecked(False)
                self._optimistic_echo(label, turning_on=False)
                return
            # Both "energize" and "dont_warn_again" proceed; only the
            # latter sets the per-session flag (energize sets it too so a
            # second energize in the same session does not re-prompt).
            self._shell._laser1_first_energize_done = True
        threading.Thread(target=self._shell._hw._toggle_laser1, daemon=True).start()  # ty: ignore[unresolved-attribute]

    def laser2_toggle_button(self) -> None:
        """Laser 2 toggle button handler — symmetric with laser 1. See
        laser1_toggle_button for the optimistic-echo + first-energize gate
        + threading model rationale."""
        btn = self.ui.pushButton_laserTwoToggle
        label = self.ui.label_laserTwoStatus
        turning_on = btn.isChecked()
        self._optimistic_echo(label, turning_on)
        if turning_on and not self._shell._laser2_first_energize_done:
            choice = self._show_first_energize_dialog(1)
            if choice == "cancel":
                btn.setChecked(False)
                self._optimistic_echo(label, turning_on=False)
                return
            self._shell._laser2_first_energize_done = True
        threading.Thread(target=self._shell._hw._toggle_laser2, daemon=True).start()  # ty: ignore[unresolved-attribute]

    # ------------------------------------------------------------------ #
    # First-energize + optimistic-echo helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _optimistic_echo(label: QLabel, turning_on: bool) -> None:
        """Set the status label to the desired state synchronously on the
        GUI thread (ON green / OFF gray). Called BEFORE the toggle thread
        starts so the label is never stale after a press. The next poll
        corrects it if the HAL state differs."""
        if turning_on:
            label.setText(f"{_sym.LASER_ON} ON")
            label.setStyleSheet(f"color: {_c.SUCCESS}; {_t.BOLD}")
        else:
            label.setText(f"{_sym.LASER_OFF} OFF")
            label.setStyleSheet(f"color: {_c.DISABLED}; {_t.BOLD}")

    def _show_first_energize_dialog(self, idx: int) -> str:
        """Show the Class IIIB first-energize confirmation dialog and return
        the operator's choice: ``"energize"`` / ``"cancel"`` /
        ``"dont_warn_again"``."""
        laser = self._shell.lasers[idx]
        heading = f"Energize {laser.label}?"
        body = (
            f"You are about to energize a Class IIIB laser "
            f"({laser.wavelength} nm, up to {laser.max_power:.0f} mW). "
            f"Confirm eye protection is on and the beam path is clear. "
            f"(Disable this warning for the rest of the session.)"
        )
        # QMessageBox.question is the standard modal helper; the third
        # button is the "Don't warn again this session" affordance. The
        # return value maps to one of the three choices below.

        result = QMessageBox.question(
            self,
            heading,
            body,
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.Cancel
            | QMessageBox.StandardButton.Discard,
            QMessageBox.StandardButton.Yes,
        )
        if result == QMessageBox.StandardButton.Yes:
            return "energize"
        if result == QMessageBox.StandardButton.Discard:
            return "dont_warn_again"
        return "cancel"
