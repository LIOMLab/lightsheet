"""CalibrationPanelWidget — per-panel widget/controller for calibration controls.

A widget container for the Camera Focus Calibration, ETL Calibration, and
Horizontal Range Calibration controls. The signal/slot connections for these
widgets are wired in the shell's ``wire_collaborators()`` to the
MotorController (``self._mc.calculate_camera_focus`` /
``self._mc.show_camera_interpolation`` / ``self._mc.show_etl_interpolation`` /
``self._mc.updateUi_reset_boundaries`` /
``self._mc.updateUi_set_horizontal_forward_boundary`` /
``self._mc.updateUi_set_horizontal_backward_boundary``) — this panel owns no
slots of its own, mirroring the plain-Python collaborator pattern where the
collaborator owns the slot logic and the panel owns the widget tree.
"""

from __future__ import annotations

import typing

from PySide6.QtWidgets import QWidget

from lightsheet.gui.panels.ui_calibration_panel import Ui_CalibrationPanel
from lightsheet.gui.widgets.field_spec import FIELD_SPECS

if typing.TYPE_CHECKING:
    from lightsheet.gui.shell.controller import Controller_MainWindow


class CalibrationPanelWidget(QWidget):
    """Calibration controls panel — Camera/ETL/Horizontal calibration
    widget container.

    The actual slot logic lives in MotorController (wired in
    ``wire_collaborators``). This panel owns only the widget tree.
    """

    def __init__(self, shell: Controller_MainWindow) -> None:
        super().__init__()
        self._shell = shell
        self.ui = Ui_CalibrationPanel()
        self.ui.setupUi(self)
        # Apply the declarative FieldSpec policy table to every promoted
        # FieldSpecSpinBox by objectName. calibration_panel's three
        # FieldSpecSpinBox widgets (calNumberOfPlanes /
        # calNumberOfCameraPositions / calNumberOfEtlVoltages) are not in
        # FIELD_SPECS (no fixed unit/range contract — they are count
        # fields), so the loop is a no-op for them; it is kept for
        # mechanical consistency across all 7 panels.
        for obj_name, spec in FIELD_SPECS.items():
            w = getattr(self.ui, obj_name, None)
            if w is not None and hasattr(w, "applySpec"):
                w.applySpec(spec)
