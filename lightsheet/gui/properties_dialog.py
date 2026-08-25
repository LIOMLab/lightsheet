"""Properties_Dialog — camera + motor properties dialog.

Moved verbatim from ``lightsheet/gui/controller.py`` (a behavior-preserving
mechanical relocation). The dialog is a self-contained ``QDialog`` subclass
with no cross-tier coupling: it reads camera/motor properties from the
parent shell's HAL handles and displays them via the generated
``Ui_Properties`` form. The shell constructs it through
``open_properties_dialog`` (``Controller_MainWindow.open_properties_dialog``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QDialog

from lightsheet.gui.ui_properties import Ui_Properties

if TYPE_CHECKING:
    from lightsheet.gui.controller import Controller_MainWindow


class Properties_Dialog(QDialog):
    """Class for Properties Dialog"""

    sig_status_message = Signal(str)

    def __init__(self, parent: Controller_MainWindow) -> None:
        QDialog.__init__(self, parent)
        self.parent = parent
        self.camera = self.parent.camera
        self.motors = self.parent.motors

        self.ui = Ui_Properties()
        self.ui.setupUi(self)
        self.ui.pushButton_refresh.clicked.connect(self.refresh_properties)
        self.sig_status_message.connect(self.parent.updateUi_message_printer)

        self.get_properties()

    def get_properties(self) -> None:
        # Read properties from the camera
        camera_properties = {}
        camera_properties = self.camera.get_properties()
        self.ui.label_cameraName.setText(f"{camera_properties.get('camera name', '-')}")
        self.ui.label_imageSize.setText(
            f"{camera_properties.get('x', '0')} X {camera_properties.get('y', '0')}"
        )
        self.ui.label_cameraTemperature.setText(
            f"{camera_properties.get('camera temperature', 0):.1f} \u2103"
        )
        self.ui.label_sensorTemperature.setText(
            f"{camera_properties.get('sensor temperature', 0):.1f} \u2103"
        )
        self.ui.label_powerTemperature.setText(
            f"{camera_properties.get('power temperature', 0):.1f} \u2103"
        )
        self.ui.label_triggerMode.setText(
            f"{camera_properties.get('trigger mode', '-')}"
        )
        self.ui.label_delayTime.setText(
            f"{camera_properties.get('delay', '-')}  {camera_properties.get('delay timebase', 'ms')}"  # noqa: E501
        )
        self.ui.label_exposureTime.setText(
            f"{camera_properties.get('exposure', '-')}  {camera_properties.get('exposure timebase', 'ms')}"  # noqa: E501
        )
        self.ui.label_acquireMode.setText(
            f"{camera_properties.get('acquire mode', '-')}"
        )
        self.ui.label_storageMode.setText(
            f"{camera_properties.get('storage mode', '-')}"
        )
        if camera_properties.get("storage mode", "-") == "Recorder":
            self.ui.label_recorderMode.setText(
                f"{camera_properties.get('recorder submode', '-')}"
            )
        else:
            self.ui.label_recorderMode.setText("-")

        # Read properties from the motors
        motors_properties = {}
        motors_properties = self.motors.get_properties()
        self.ui.label_horizontalMotorName.setText(
            f"{motors_properties.get('horizontal name', '-')}"
        )
        self.ui.label_verticalMotorName.setText(
            f"{motors_properties.get('vertical name', '-')}"
        )
        self.ui.label_cameraMotorName.setText(
            f"{motors_properties.get('camera name', '-')}"
        )

    def refresh_properties(self) -> None:
        """Refresh system properties"""
        self.get_properties()
        self.sig_status_message.emit("System Properties Refreshed")
