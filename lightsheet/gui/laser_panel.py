"""LaserPanelWidget — per-panel widget/controller for the laser controls.

Owns the laser updateUi_* slots grouped by concern (D-01 gui modularization).
Follows the plain-Python collaborator pattern extended to a QWidget: holds a
shell reference, reads ``self._shell.ui.<objectName>`` for its widgets, emits
through ``self._shell.sig_*``, and delegates HAL writes to
``self._shell._hw``.

The 4 laser daemon ``threading.Thread`` spawns (targeting
``self._shell._hw._write_laser*_power`` / ``self._shell._hw._toggle_laser*``)
stay ``threading.Thread`` per the lock-free E-stop kill path contract
(AGENTS.md §2). They are NOT migrated to QThread — a queued slot dispatch
window between ``estop_event.set()`` and the slot's first estop poll would
re-energize a Class IIIB laser past the kill path.

The E-stop kill path itself (``updateUi_estop_pressed``) stays in the thin
shell — it is NOT in this panel.
"""

from __future__ import annotations

import threading
import typing

from PySide6.QtCore import Slot
from PySide6.QtWidgets import QWidget

from lightsheet.gui.ui_laser_panel import Ui_LaserPanel

if typing.TYPE_CHECKING:
    from lightsheet.gui.controller import Controller_MainWindow


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
        self._shell._hw._refresh_laser2_readback_async()
        self._shell._hw._poll_laser_status([1])

    @Slot(int, str)
    def updateUi_laser_status(self, idx: int, status: str) -> None:
        """GUI-thread slot — maps a (idx, status) emit from
        sig_laser_status to the per-laser QLabel text + semantic color.
        status is 'active' / 'inactive' / 'error' (set by
        _poll_laser_status). The label list is indexed by laser index.
        """
        labels = [self.ui.label_laserOneStatus, self.ui.label_laserTwoStatus]
        if status == "active":
            labels[idx].setText("● ON")
            labels[idx].setStyleSheet(
                "color: #34C759; font-weight: bold;"
            )
        elif status == "inactive":
            labels[idx].setText("● OFF")
            labels[idx].setStyleSheet(
                "color: #8E8E93; font-weight: bold;"
            )
        else:  # "error"
            labels[idx].setText("● ERR")
            labels[idx].setStyleSheet(
                "color: #FF3B30; font-weight: bold;"
            )

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
        self._shell.laser1_power_pct = self.ui.doubleSpinBox_laserOneAmplitude.value()  # noqa: E501
        self._shell._laser1_amplitude_timer.start(300)

    def updateUi_laser2_amplitude(self) -> None:
        # Debounce-only slot for laser 2 (iBeam). See updateUi_laser1_amplitude.
        # Capture the staged percentage now for the same reason as laser 1:
        # _toggle_laser2's just-on path reads laser2_power_pct.
        self._shell.laser2_power_pct = self.ui.doubleSpinBox_laserTwoAmplitude.value()  # noqa: E501
        self._shell._laser2_amplitude_timer.start(300)

    def _apply_laser1_amplitude(self) -> None:
        """Debounce timeout slot (GUI thread): store the staged percentage
        and offload the scaled DAQ write to a worker thread so the GUI event
        loop is never blocked on a DAQ round-trip. The write itself moved
        to HardwareManager._write_laser1_power — the slot just spawns the
        thread targeting the collaborator method."""
        pct = self.ui.doubleSpinBox_laserOneAmplitude.value()
        self._shell.laser1_power_pct = pct
        threading.Thread(
            target=self._shell._hw._write_laser1_power, args=(pct,), daemon=True
        ).start()

    def _apply_laser2_amplitude(self) -> None:
        """Debounce timeout slot (GUI thread): store the staged percentage
        and offload the scaled iBeam serial write to a worker thread
        targeting HardwareManager._write_laser2_power."""
        pct = self.ui.doubleSpinBox_laserTwoAmplitude.value()
        self._shell.laser2_power_pct = pct
        threading.Thread(
            target=self._shell._hw._write_laser2_power, args=(pct,), daemon=True
        ).start()

    def laser1_toggle_button(self) -> None:
        # Slot only spawns a worker thread — the DAQ toggle (and the
        # immediate scaled-power application when turning on) happens off
        # the GUI thread so the event loop is never blocked on a DAQ
        # round-trip. The toggle body moved to HardwareManager._toggle_laser1.
        threading.Thread(target=self._shell._hw._toggle_laser1, daemon=True).start()

    def laser2_toggle_button(self) -> None:
        # Slot only spawns a worker thread — the iBeam serial on/off (and
        # the immediate scaled-power application when turning on) happens
        # off the GUI thread so the event loop is never blocked on a
        # serial round-trip. The toggle body moved to HardwareManager._toggle_laser2.
        threading.Thread(target=self._shell._hw._toggle_laser2, daemon=True).start()
