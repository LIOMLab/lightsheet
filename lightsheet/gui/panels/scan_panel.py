"""ScanPanelWidget — per-panel widget/controller for scan settings (ETL/Galvo).

A widget container for the ETL Settings and Galvanometers controls. The
signal/slot connections for these widgets are wired in the shell's
``wire_collaborators()`` to the AcquisitionCoordinator
(``self._acq.updateUi_etl_*`` / ``self._acq.updateUi_galvo_*``) — this panel
owns no slots of its own, mirroring the plain-Python collaborator pattern
where the collaborator owns the slot logic and the panel owns the widget
tree.
"""

from __future__ import annotations

import typing

from PySide6.QtWidgets import QWidget

from lightsheet.gui.panels.ui_scan_panel import Ui_ScanPanel
from lightsheet.gui.widgets.field_spec import FIELD_SPECS

if typing.TYPE_CHECKING:
    from lightsheet.gui.shell.controller import Controller_MainWindow


class ScanPanelWidget(QWidget):
    """Scan settings panel — ETL/Galvo settings widget container.

    The actual slot logic lives in AcquisitionCoordinator (wired in
    ``wire_collaborators``). This panel owns only the widget tree.
    """

    def __init__(self, shell: Controller_MainWindow) -> None:
        super().__init__()
        self._shell = shell
        self.ui = Ui_ScanPanel()
        self.ui.setupUi(self)
        # Apply the declarative FieldSpec policy table to every promoted
        # FieldSpecSpinBox by objectName (suffix/decimals/step/soft min-max).
        for obj_name, spec in FIELD_SPECS.items():
            w = getattr(self.ui, obj_name, None)
            if w is not None and hasattr(w, "applySpec"):
                w.applySpec(spec)
        # Selective QSlider pairing for the wide-range coarse ETL/galvo
        # amplitude fields. Bare bound-method connections (no lambdas).
        for field_name in (
            "doubleSpinBox_etlLeftAmplitude",
            "doubleSpinBox_etlRightAmplitude",
            "doubleSpinBox_galvoLeftAmplitude",
            "doubleSpinBox_galvoRightAmplitude",
        ):
            spinbox = getattr(self.ui, field_name, None)
            slider = getattr(self.ui, f"slider_{field_name}", None)
            if spinbox is None or slider is None:
                continue
            spec = FIELD_SPECS[field_name]
            slider.setRange(int(spec.minimum), int(spec.maximum))
            slider.setSingleStep(int(spec.page_step))
            slider.setValue(int(spinbox.value()))
            spinbox.valueChanged.connect(slider.setValue)
            slider.valueChanged.connect(spinbox.setValue)
