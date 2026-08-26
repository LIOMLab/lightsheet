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
