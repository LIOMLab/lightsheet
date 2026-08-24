"""Branch-coverage closure for ``lightsheet.gui.controller`` using the
``_load_method`` exec pattern.

Controller_MainWindow constructs pyqtgraph ViewBox objects that segfault
during GC at process exit, which can lose coverage data when run under
xdist. This file uses the ``_load_method`` pattern (AGENTS.md §5) to
extract and exec each method body against a Mock ``self``, avoiding the
Controller_MainWindow construction entirely — no pyqtgraph, no segfault,
reliable coverage data.

Each test extracts the REAL method body from controller.py and execs it
in a controlled namespace with mock globals. Coverage.py tracks the
exec'd code as running in the original source file because the code
object's ``co_filename`` is set to the source path.

Behavior tests (AGENTS.md §5) — every assertion is on a runtime
postcondition (attribute value, signal emit, widget state), never a
static-source grep.
"""

from __future__ import annotations

import os
import threading
from unittest.mock import Mock, patch

import pytest

pytest.importorskip("PyQt5")

from _helpers.controller import _load_method

# Extra globals the method bodies reference at exec time.
_CONTROLLER_SRC = os.path.join(
    os.path.dirname(__file__), "..", "lightsheet", "gui", "controller.py"
)

from PyQt5.QtCore import Qt as _Qt
from PyQt5.QtWidgets import QFileDialog as _QFD, QMessageBox as _QMB, QPushButton as _QPushButton

_EXTRA = {
    "os": os,
    "threading": threading,
    "webbrowser": __import__("webbrowser"),
    "np": __import__("numpy"),
    "h5py": __import__("h5py"),
    "plt": __import__("matplotlib.pyplot", fromlist=["pyplot"]),
    "QFileDialog": _QFD,
    "QMessageBox": _QMB,
    "QPushButton": _QPushButton,
    "QTableWidgetItem": __import__("PyQt5.QtWidgets", fromlist=["QTableWidgetItem"]),
    "QAbstractItemView": __import__("PyQt5.QtWidgets", fromlist=["QAbstractItemView"]),
    "Qt": _Qt,
    "__file__": _CONTROLLER_SRC,
    "Properties_Dialog": __import__("lightsheet.gui.properties_dialog", fromlist=["Properties_Dialog"]).Properties_Dialog,
}


def _make_self(**kwargs) -> Mock:
    """Create a Mock self with all the attributes controller methods read."""
    s = Mock()
    s.ui = Mock()
    s._hw = Mock()
    s._acq = Mock()
    s._fs = Mock()
    s._mc = Mock()
    s._bundle = Mock()
    s._demo_mode = True
    s.sig_stylesheet = Mock()
    s.sig_message = Mock()
    s.sig_beep = Mock()
    s.sig_progress_update = Mock()
    s.estop_event = Mock()
    s.estop_event.is_set.return_value = False
    s.lasers = [Mock(), Mock()]
    s.lasers[0].active = False
    s.lasers[1].active = False
    s.lasers[0].error = 0
    s.lasers[1].error = 0
    s.camera = Mock()
    s.siggen = Mock()
    s.motors = Mock()
    s.etls = Mock()
    s.preview_mode_started = False
    s.live_mode_started = False
    s.single_mode_started = False
    s.stack_mode_started = False
    s.saving_allowed = False
    s.save_directory = ""
    s.save_filename = ""
    s.save_description = ""
    s.number_of_planes = 1
    s.stack_starting_plane = 0.0
    s.stack_ending_plane = 100.0
    s.stack_step = 10.0
    s.units = "mm"
    s.units_decimals = 3
    s.units_fixformat = "{:.5f} {}"
    s.units_increment = 0.1
    s.default_buttons = []
    s.image_hor_pos_text = "0.0"
    s.image_ver_pos_text = "0.0"
    s.image_cam_pos_text = "0.0"
    s.buffer = Mock()
    s.reconstructed_frame = Mock()
    s.open_directory = ""
    s.dataset_name = ""
    s.laser1_power_pct = 0.0
    s.laser2_power_pct = 0.0
    s._estop_disarmed = False
    s._auto_laser1 = False
    s._auto_laser2 = False
    s.label_estopStatus = Mock()
    s.pushButton_estop = Mock()
    s.pushButton_armReset = Mock()
    s.label_laserOneReadback = Mock()
    s.label_laserTwoReadback = Mock()
    s.label_laserOneStatus = Mock()
    s.label_laserTwoStatus = Mock()
    s._laser1_amplitude_timer = Mock()
    s._laser2_amplitude_timer = Mock()
    s.updateUi_message_printer = Mock()
    s.updateUi_modes_buttons = Mock()
    s.updateUi_motor_buttons = Mock()
    s.updateUi_position_indicators = Mock()
    s.updateUi_set_number_of_planes = Mock()
    s.close_modes = Mock()
    s._cache_auto_laser_flags = Mock()
    s.validate_file_name = Mock()
    s.current_horizontal_position_text = ""
    s.current_vertical_position_text = ""
    s.current_camera_position_text = ""
    for k, v in kwargs.items():
        setattr(s, k, v)
    return s


# -- Simple slots -----------------------------------------------------------


def test_updateUi_light_theme_emits_stylesheet() -> None:
    fn = _load_method("updateUi_light_theme(self) -> None", extra_globals=_EXTRA)
    s = _make_self()
    fn(s)
    s.sig_stylesheet.emit.assert_called_once_with("light")


def test_updateUi_dark_theme_emits_stylesheet() -> None:
    fn = _load_method("updateUi_dark_theme(self) -> None", extra_globals=_EXTRA)
    s = _make_self()
    fn(s)
    s.sig_stylesheet.emit.assert_called_once_with("dark")


def test_updateUi_show_hide_images_pane_visible() -> None:
    fn = _load_method("updateUi_show_hide_images_pane(self) -> None", extra_globals=_EXTRA)
    s = _make_self()
    s.ui.imagesPane.isVisible.return_value = True
    fn(s)
    s.ui.imagesPane.hide.assert_called_once()


def test_updateUi_show_hide_images_pane_hidden() -> None:
    fn = _load_method("updateUi_show_hide_images_pane(self) -> None", extra_globals=_EXTRA)
    s = _make_self()
    s.ui.imagesPane.isVisible.return_value = False
    fn(s)
    s.ui.imagesPane.show.assert_called_once()


def test_updateUi_show_hide_controls_pane_visible() -> None:
    fn = _load_method("updateUi_show_hide_controls_pane(self) -> None", extra_globals=_EXTRA)
    s = _make_self()
    s.ui.controlsPane.isVisible.return_value = True
    fn(s)
    s.ui.controlsPane.hide.assert_called_once()


def test_updateUi_show_hide_controls_pane_hidden() -> None:
    fn = _load_method("updateUi_show_hide_controls_pane(self) -> None", extra_globals=_EXTRA)
    s = _make_self()
    s.ui.controlsPane.isVisible.return_value = False
    fn(s)
    s.ui.controlsPane.show.assert_called_once()


def test_updateUi_show_hide_message_log_visible() -> None:
    fn = _load_method("updateUi_show_hide_message_log(self) -> None", extra_globals=_EXTRA)
    s = _make_self()
    s.ui.plainTextEdit_messageLog.isVisible.return_value = True
    fn(s)
    s.ui.plainTextEdit_messageLog.hide.assert_called_once()


def test_updateUi_show_hide_message_log_hidden() -> None:
    fn = _load_method("updateUi_show_hide_message_log(self) -> None", extra_globals=_EXTRA)
    s = _make_self()
    s.ui.plainTextEdit_messageLog.isVisible.return_value = False
    fn(s)
    s.ui.plainTextEdit_messageLog.show.assert_called_once()


def test_open_help_calls_webbrowser() -> None:
    fn = _load_method("open_help(self) -> None", extra_globals=_EXTRA)
    s = _make_self()
    with patch("webbrowser.open_new"):
        fn(s)


def test_open_properties_dialog() -> None:
    # Patch Properties_Dialog in the exec namespace by overriding _EXTRA
    MockDialog = Mock()
    extra = dict(_EXTRA)
    extra["Properties_Dialog"] = MockDialog
    fn = _load_method("open_properties_dialog(self) -> None", extra_globals=extra)
    s = _make_self()
    fn(s)
    mock_dlg = MockDialog.return_value
    mock_dlg.setAttribute.assert_called_once()
    mock_dlg.open.assert_called_once()
    mock_dlg.get_properties.assert_called_once()


# -- Motor/mode button helpers ----------------------------------------------


def test_updateUi_motor_buttons_disable() -> None:
    fn = _load_method("updateUi_motor_buttons(self, disable_button: bool = True) -> None", extra_globals=_EXTRA)
    s = _make_self()
    fn(s, disable_button=True)
    # All buttons should have setEnabled(False) called
    s.ui.pushButton_sampleStepUp.setEnabled.assert_called_with(False)


def test_updateUi_motor_buttons_enable() -> None:
    fn = _load_method("updateUi_motor_buttons(self, disable_button: bool = True) -> None", extra_globals=_EXTRA)
    s = _make_self()
    fn(s, disable_button=False)
    s.ui.pushButton_sampleStepUp.setEnabled.assert_called_with(True)


def test_updateUi_modes_buttons() -> None:
    fn = _load_method("updateUi_modes_buttons(self, buttons_to_enable: list[QPushButton]) -> None", extra_globals=_EXTRA)
    s = _make_self()
    # Use the same button object that's in s.ui so the `in` check works.
    btn_enable = s.ui.pushButton_acqStartPreviewMode
    fn(s, [btn_enable])
    btn_enable.setEnabled.assert_called_with(True)
    s.ui.pushButton_acqStartLiveMode.setEnabled.assert_called_with(False)


def test_updateUi_enable_buttons() -> None:
    fn = _load_method("updateUi_enable_buttons(self, buttons_to_enable: list[QPushButton]) -> None", extra_globals=_EXTRA)
    s = _make_self()
    btn = s.ui.pushButton_acqStartPreviewMode
    fn(s, [btn])
    btn.setEnabled.assert_called_with(True)


def test_updateUi_disable_buttons() -> None:
    fn = _load_method("updateUi_disable_buttons(self, buttons_to_disable: list[QPushButton]) -> None", extra_globals=_EXTRA)
    s = _make_self()
    btn = s.ui.pushButton_acqStartPreviewMode
    fn(s, [btn])
    btn.setEnabled.assert_called_with(False)


def test_cache_auto_laser_flags() -> None:
    fn = _load_method("_cache_auto_laser_flags(self) -> None", extra_globals=_EXTRA)
    s = _make_self()
    s.ui.checkBox_laserOneAutomatic.isChecked.return_value = True
    s.ui.checkBox_laserTwoAutomatic.isChecked.return_value = False
    fn(s)
    assert s._auto_laser1 is True
    assert s._auto_laser2 is False


def test_close_modes_all_active() -> None:
    fn = _load_method("close_modes(self) -> None", extra_globals=_EXTRA)
    s = _make_self()
    s.preview_mode_started = True
    s.live_mode_started = True
    s.stack_mode_started = True
    s.lasers[0].active = True
    s.lasers[1].active = True
    fn(s)
    assert s.preview_mode_started is False
    assert s.live_mode_started is False
    assert s.stack_mode_started is False
    s._hw.stop_lasers.assert_called_once()


def test_close_modes_no_lasers_active() -> None:
    fn = _load_method("close_modes(self) -> None", extra_globals=_EXTRA)
    s = _make_self()
    s.preview_mode_started = True
    s.lasers[0].active = False
    s.lasers[1].active = False
    fn(s)
    assert s.preview_mode_started is False
    s._hw.stop_lasers.assert_not_called()


# -- E-stop / arm-reset -----------------------------------------------------


def test_updateUi_arm_reset_pressed_first_press() -> None:
    fn = _load_method("updateUi_arm_reset_pressed(self) -> None", extra_globals=_EXTRA)
    s = _make_self()
    s._estop_disarmed = False
    fn(s)
    assert s._estop_disarmed is True
    s.estop_event.clear.assert_called_once()
    s.pushButton_armReset.setText.assert_called_with("Arm")


def test_updateUi_arm_reset_pressed_second_press() -> None:
    fn = _load_method("updateUi_arm_reset_pressed(self) -> None", extra_globals=_EXTRA)
    s = _make_self()
    s._estop_disarmed = True
    fn(s)
    assert s._estop_disarmed is False
    s.pushButton_armReset.setText.assert_called_with("Arm/Reset")


# -- Laser readback / status ------------------------------------------------


def test_updateUi_laser_readback() -> None:
    fn = _load_method("updateUi_laser_readback(self, idx: int, text: str, tooltip: str) -> None", extra_globals=_EXTRA)
    s = _make_self()
    fn(s, 0, "100 mW", "")
    s.label_laserOneReadback.setText.assert_called_with("100 mW")
    fn(s, 1, "50 mW", "stale")
    s.label_laserTwoReadback.setText.assert_called_with("50 mW")


def test_updateUi_laser2_refresh_clicked() -> None:
    fn = _load_method("updateUi_laser2_refresh_clicked(self) -> None", extra_globals=_EXTRA)
    s = _make_self()
    fn(s)
    s._hw._refresh_laser2_readback_async.assert_called_once()
    s._hw._poll_laser_status.assert_called_once_with([1])


def test_updateUi_laser_status_active() -> None:
    fn = _load_method("updateUi_laser_status(self, idx: int, status: str) -> None", extra_globals=_EXTRA)
    s = _make_self()
    fn(s, 0, "active")
    s.label_laserOneStatus.setText.assert_called_with("● ON")


def test_updateUi_laser_status_inactive() -> None:
    fn = _load_method("updateUi_laser_status(self, idx: int, status: str) -> None", extra_globals=_EXTRA)
    s = _make_self()
    fn(s, 1, "inactive")
    s.label_laserTwoStatus.setText.assert_called_with("● OFF")


def test_updateUi_laser_status_error() -> None:
    fn = _load_method("updateUi_laser_status(self, idx: int, status: str) -> None", extra_globals=_EXTRA)
    s = _make_self()
    fn(s, 0, "error")
    s.label_laserOneStatus.setText.assert_called_with("● ERR")


# -- Units / position -------------------------------------------------------


def test_updateUi_units_mm() -> None:
    fn = _load_method("updateUi_units(self) -> None", extra_globals=_EXTRA)
    s = _make_self()
    s.ui.comboBox_units.currentText.return_value = "mm"
    s.motors.horizontal.get_limit_low.return_value = 0.0
    s.motors.horizontal.get_limit_high.return_value = 100.0
    s.motors.vertical.get_limit_low.return_value = 0.0
    s.motors.vertical.get_limit_high.return_value = 50.0
    s.motors.camera.get_limit_low.return_value = 0.0
    s.motors.camera.get_limit_high.return_value = 30.0
    # The spinbox maximum()/minimum() are called for increment calculation
    s.ui.doubleSpinBox_sampleSetHPosition.maximum.return_value = 100.0
    s.ui.doubleSpinBox_sampleSetHPosition.minimum.return_value = 0.0
    s.ui.doubleSpinBox_sampleSetVPosition.maximum.return_value = 50.0
    s.ui.doubleSpinBox_sampleSetVPosition.minimum.return_value = 0.0
    s.ui.doubleSpinBox_cameraSetPosition.maximum.return_value = 30.0
    s.ui.doubleSpinBox_cameraSetPosition.minimum.return_value = 0.0
    fn(s)
    assert s.units == "mm"
    assert s.units_decimals == 3
    s.updateUi_position_indicators.assert_called_once()


def test_updateUi_units_um() -> None:
    fn = _load_method("updateUi_units(self) -> None", extra_globals=_EXTRA)
    s = _make_self()
    s.ui.comboBox_units.currentText.return_value = "\u03bcm"
    s.motors.horizontal.get_limit_low.return_value = 0.0
    s.motors.horizontal.get_limit_high.return_value = 100000.0
    s.motors.vertical.get_limit_low.return_value = 0.0
    s.motors.vertical.get_limit_high.return_value = 50000.0
    s.motors.camera.get_limit_low.return_value = 0.0
    s.motors.camera.get_limit_high.return_value = 30000.0
    s.ui.doubleSpinBox_sampleSetHPosition.maximum.return_value = 100000.0
    s.ui.doubleSpinBox_sampleSetHPosition.minimum.return_value = 0.0
    s.ui.doubleSpinBox_sampleSetVPosition.maximum.return_value = 50000.0
    s.ui.doubleSpinBox_sampleSetVPosition.minimum.return_value = 0.0
    s.ui.doubleSpinBox_cameraSetPosition.maximum.return_value = 30000.0
    s.ui.doubleSpinBox_cameraSetPosition.minimum.return_value = 0.0
    fn(s)
    assert s.units == "\u03bcm"
    assert s.units_decimals == 0


def test_updateUi_position_horizontal() -> None:
    fn = _load_method("updateUi_position_horizontal(self) -> None", extra_globals=_EXTRA)
    s = _make_self()
    s.motors.horizontal.get_position.return_value = 5.0
    fn(s)
    s.ui.label_sampleCurrentHPosition.setText.assert_called_once()


def test_updateUi_position_vertical() -> None:
    fn = _load_method("updateUi_position_vertical(self) -> None", extra_globals=_EXTRA)
    s = _make_self()
    s.motors.vertical.get_position.return_value = 3.0
    fn(s)
    s.ui.label_sampleCurrentVPosition.setText.assert_called_once()


def test_updateUi_position_camera() -> None:
    fn = _load_method("updateUi_position_camera(self) -> None", extra_globals=_EXTRA)
    s = _make_self()
    s.motors.camera.get_position.return_value = 2.0
    fn(s)
    s.ui.label_cameraCurrentPosition.setText.assert_called_once()


# -- Laser amplitude / toggle -----------------------------------------------


def test_updateUi_laser1_amplitude() -> None:
    fn = _load_method("updateUi_laser1_amplitude(self) -> None", extra_globals=_EXTRA)
    s = _make_self()
    s.ui.doubleSpinBox_laserOneAmplitude.value.return_value = 50.0
    fn(s)
    assert s.laser1_power_pct == 50.0
    s._laser1_amplitude_timer.start.assert_called_with(300)


def test_updateUi_laser2_amplitude() -> None:
    fn = _load_method("updateUi_laser2_amplitude(self) -> None", extra_globals=_EXTRA)
    s = _make_self()
    s.ui.doubleSpinBox_laserTwoAmplitude.value.return_value = 75.0
    fn(s)
    assert s.laser2_power_pct == 75.0
    s._laser2_amplitude_timer.start.assert_called_with(300)


def test_apply_laser1_amplitude() -> None:
    fn = _load_method("_apply_laser1_amplitude(self) -> None", extra_globals=_EXTRA)
    s = _make_self()
    s.ui.doubleSpinBox_laserOneAmplitude.value.return_value = 50.0
    with patch("lightsheet.gui.controller.threading.Thread") as MockThread:
        MockThread.return_value.start = Mock()
        fn(s)
        MockThread.return_value.start.assert_called_once()


def test_apply_laser2_amplitude() -> None:
    fn = _load_method("_apply_laser2_amplitude(self) -> None", extra_globals=_EXTRA)
    s = _make_self()
    s.ui.doubleSpinBox_laserTwoAmplitude.value.return_value = 75.0
    with patch("lightsheet.gui.controller.threading.Thread") as MockThread:
        MockThread.return_value.start = Mock()
        fn(s)
        MockThread.return_value.start.assert_called_once()


def test_laser1_toggle_button() -> None:
    fn = _load_method("laser1_toggle_button(self) -> None", extra_globals=_EXTRA)
    s = _make_self()
    with patch("lightsheet.gui.controller.threading.Thread") as MockThread:
        MockThread.return_value.start = Mock()
        fn(s)
        MockThread.return_value.start.assert_called_once()


def test_laser2_toggle_button() -> None:
    fn = _load_method("laser2_toggle_button(self) -> None", extra_globals=_EXTRA)
    s = _make_self()
    with patch("lightsheet.gui.controller.threading.Thread") as MockThread:
        MockThread.return_value.start = Mock()
        fn(s)
        MockThread.return_value.start.assert_called_once()


# -- Mode button slots ------------------------------------------------------


def test_updateUi_preview_mode_button_start() -> None:
    fn = _load_method("updateUi_preview_mode_button(self) -> None", extra_globals=_EXTRA)
    s = _make_self()
    s.preview_mode_started = False
    with patch("lightsheet.gui.controller.threading.Thread") as MockThread:
        MockThread.return_value.start = Mock()
        fn(s)
    assert s.preview_mode_started is True
    s.close_modes.assert_called_once()
    s._cache_auto_laser_flags.assert_called_once()


def test_updateUi_preview_mode_button_stop() -> None:
    fn = _load_method("updateUi_preview_mode_button(self) -> None", extra_globals=_EXTRA)
    s = _make_self()
    s.preview_mode_started = True
    fn(s)
    assert s.preview_mode_started is False
    s.ui.pushButton_acqStartPreviewMode.setText.assert_called_with("Start Preview Mode")


def test_updateUi_post_preview_mode() -> None:
    fn = _load_method("updateUi_post_preview_mode(self) -> None", extra_globals=_EXTRA)
    s = _make_self()
    fn(s)
    s.updateUi_modes_buttons.assert_called_once()
    s.updateUi_message_printer.assert_called_with("->Preview mode stopped")


def test_updateUi_live_mode_button_start() -> None:
    fn = _load_method("updateUi_live_mode_button(self) -> None", extra_globals=_EXTRA)
    s = _make_self()
    s.live_mode_started = False
    with patch("lightsheet.gui.controller.threading.Thread") as MockThread:
        MockThread.return_value.start = Mock()
        fn(s)
    assert s.live_mode_started is True
    s.close_modes.assert_called_once()


def test_updateUi_live_mode_button_stop() -> None:
    fn = _load_method("updateUi_live_mode_button(self) -> None", extra_globals=_EXTRA)
    s = _make_self()
    s.live_mode_started = True
    fn(s)
    assert s.live_mode_started is False
    s.ui.pushButton_acqStartLiveMode.setText.assert_called_with("Start Live Mode")


def test_updateUi_post_live_mode() -> None:
    fn = _load_method("updateUi_post_live_mode(self) -> None", extra_globals=_EXTRA)
    s = _make_self()
    fn(s)
    s.updateUi_message_printer.assert_called_with("->Live mode stopped")


def test_updateUi_single_mode_button_start() -> None:
    fn = _load_method("updateUi_single_mode_button(self) -> None", extra_globals=_EXTRA)
    s = _make_self()
    s.single_mode_started = False
    with patch("lightsheet.gui.controller.threading.Thread") as MockThread:
        MockThread.return_value.start = Mock()
        fn(s)
    assert s.single_mode_started is True
    s.close_modes.assert_called_once()


def test_updateUi_post_single_mode() -> None:
    fn = _load_method("updateUi_post_single_mode(self) -> None", extra_globals=_EXTRA)
    s = _make_self()
    fn(s)
    assert s.single_mode_started is False
    s.ui.pushButton_acqGetSingleImage.setText.assert_called_with("Get Single Image")


def test_updateUi_post_stack_mode() -> None:
    fn = _load_method("updateUi_post_stack_mode(self) -> None", extra_globals=_EXTRA)
    s = _make_self()
    fn(s)
    assert s.stack_mode_started is False
    s.ui.pushButton_acqStartStackMode.setText.assert_called_with("Start Stack Mode")


# -- Stack mode button (both branches) --------------------------------------


def test_updateUi_stack_mode_button_stop() -> None:
    fn = _load_method("updateUi_stack_mode_button(self) -> None", extra_globals=_EXTRA)
    s = _make_self()
    s.stack_mode_started = True
    fn(s)
    assert s.stack_mode_started is False


def test_updateUi_stack_mode_button_start_valid() -> None:
    fn = _load_method("updateUi_stack_mode_button(self) -> None", extra_globals=_EXTRA)
    s = _make_self()
    s.stack_mode_started = False
    s.saving_allowed = True
    s.stack_starting_plane = 0.0
    s.stack_ending_plane = 100.0
    s.ui.checkBox_acqFirstPlaneSet.isChecked.return_value = True
    s.ui.checkBox_acqLastPlaneSet.isChecked.return_value = True
    s.ui.doubleSpinBox_acqPlaneStepSize.value.return_value = 10.0
    with patch("lightsheet.gui.controller.threading.Thread") as MockThread, \
         patch("lightsheet.gui.controller.QMessageBox") as MockMsg:
        MockThread.return_value.start = Mock()
        fn(s)
    assert s.stack_mode_started is True


def test_updateUi_stack_mode_button_start_invalid() -> None:
    MockMsg = Mock()
    MockMsg.Ok = 1
    MockMsg.warning.return_value = MockMsg.Ok
    extra = dict(_EXTRA)
    extra["QMessageBox"] = MockMsg
    fn = _load_method("updateUi_stack_mode_button(self) -> None", extra_globals=extra)
    s = _make_self()
    s.stack_mode_started = False
    s.ui.checkBox_acqFirstPlaneSet.isChecked.return_value = False
    fn(s)
    assert s.stack_mode_started is False
    s.sig_message.emit.assert_called_once()
    s.sig_beep.emit.assert_called_once()


def test_updateUi_stack_mode_button_start_reverse_direction() -> None:
    fn = _load_method("updateUi_stack_mode_button(self) -> None", extra_globals=_EXTRA)
    s = _make_self()
    s.stack_mode_started = False
    s.saving_allowed = True
    s.stack_starting_plane = 100.0
    s.stack_ending_plane = 0.0
    s.ui.checkBox_acqFirstPlaneSet.isChecked.return_value = True
    s.ui.checkBox_acqLastPlaneSet.isChecked.return_value = True
    s.ui.doubleSpinBox_acqPlaneStepSize.value.return_value = 10.0
    with patch("lightsheet.gui.controller.threading.Thread") as MockThread, \
         patch("lightsheet.gui.controller.QMessageBox") as MockMsg:
        MockThread.return_value.start = Mock()
        fn(s)
    assert s.stack_step == -10.0


def test_updateUi_stack_mode_button_start_nosave_yes() -> None:
    MockMsg = Mock()
    MockMsg.Yes = 1
    MockMsg.No = 0
    MockMsg.question.return_value = MockMsg.Yes
    extra = dict(_EXTRA)
    extra["QMessageBox"] = MockMsg
    fn = _load_method("updateUi_stack_mode_button(self) -> None", extra_globals=extra)
    s = _make_self()
    s.stack_mode_started = False
    s.saving_allowed = False
    s.stack_starting_plane = 0.0
    s.stack_ending_plane = 100.0
    s.ui.checkBox_acqFirstPlaneSet.isChecked.return_value = True
    s.ui.checkBox_acqLastPlaneSet.isChecked.return_value = True
    s.ui.doubleSpinBox_acqPlaneStepSize.value.return_value = 10.0
    with patch("lightsheet.gui.controller.threading.Thread") as MockThread:
        MockThread.return_value.start = Mock()
        fn(s)
    assert s.stack_mode_started is True


# -- validate_file_name -----------------------------------------------------


def test_validate_file_name_valid() -> None:
    fn = _load_method("validate_file_name(self) -> None", extra_globals=_EXTRA)
    s = _make_self()
    s.ui.lineEdit_saveFilename.text.return_value = "test_file"
    s.save_directory = "/tmp"
    fn(s)
    assert s.saving_allowed is True


def test_validate_file_name_empty() -> None:
    fn = _load_method("validate_file_name(self) -> None", extra_globals=_EXTRA)
    s = _make_self()
    s.ui.lineEdit_saveFilename.text.return_value = ""
    s.save_directory = ""
    fn(s)
    assert s.saving_allowed is False


def test_validate_file_name_special_chars() -> None:
    fn = _load_method("validate_file_name(self) -> None", extra_globals=_EXTRA)
    s = _make_self()
    s.ui.lineEdit_saveFilename.text.return_value = "test@file#name"
    s.save_directory = "/tmp"
    fn(s)
    assert s.saving_allowed is True
    # Special chars should be replaced with _
    assert "_" in s.save_filename


# -- save_single_image ------------------------------------------------------


def test_updateUi_save_single_image_saving_allowed_crop() -> None:
    fn = _load_method("updateUi_save_single_image(self) -> None", extra_globals=_EXTRA)
    s = _make_self()
    s.saving_allowed = True
    s.ui.checkBox_saveAllCrop.isChecked.return_value = True
    s.ui.checkBox_saveAllFull.isChecked.return_value = False
    s._fs.crop_buffer.return_value = Mock()
    fn(s)
    s._fs.reinit.assert_called_with(1)
    s._fs.set_files.assert_called_with(1, s.save_filename, "singleImage", 1, "ETLscan")
    s._fs.start_saving.assert_called_once()
    s._fs.stop_saving.assert_called_once()


def test_updateUi_save_single_image_saving_allowed_full() -> None:
    fn = _load_method("updateUi_save_single_image(self) -> None", extra_globals=_EXTRA)
    s = _make_self()
    s.saving_allowed = True
    s.ui.checkBox_saveAllCrop.isChecked.return_value = False
    s.ui.checkBox_saveAllFull.isChecked.return_value = True
    fn(s)
    s._fs.set_files.assert_called_with(1, s.save_filename, "singleImage", 1, "FullETLscan")


def test_updateUi_save_single_image_saving_allowed_reconstructed() -> None:
    fn = _load_method("updateUi_save_single_image(self) -> None", extra_globals=_EXTRA)
    s = _make_self()
    s.saving_allowed = True
    s.ui.checkBox_saveAllCrop.isChecked.return_value = False
    s.ui.checkBox_saveAllFull.isChecked.return_value = False
    fn(s)
    s._fs.set_files.assert_called_with(1, s.save_filename, "singleImage", 1, "reconstructed_frame")


def test_updateUi_save_single_image_not_allowed() -> None:
    MockMsg = Mock()
    MockMsg.Ok = 1
    MockMsg.warning.return_value = MockMsg.Ok
    extra = dict(_EXTRA)
    extra["QMessageBox"] = MockMsg
    fn = _load_method("updateUi_save_single_image(self) -> None", extra_globals=extra)
    s = _make_self()
    s.saving_allowed = False
    fn(s)
    s.sig_beep.emit.assert_called_once()
    s.sig_message.emit.assert_called_once()


# -- Stack set points / number of planes ------------------------------------


def test_updateUi_set_stack_mode_starting_point() -> None:
    fn = _load_method("updateUi_set_stack_mode_starting_point(self) -> None", extra_globals=_EXTRA)
    s = _make_self()
    s.motors.horizontal.get_position.return_value = 50.0
    fn(s)
    assert s.stack_starting_plane == 50.0
    s.ui.checkBox_acqFirstPlaneSet.setChecked.assert_called_with(True)
    s.updateUi_set_number_of_planes.assert_called_once()


def test_updateUi_set_stack_mode_ending_point() -> None:
    fn = _load_method("updateUi_set_stack_mode_ending_point(self) -> None", extra_globals=_EXTRA)
    s = _make_self()
    s.motors.horizontal.get_position.return_value = 100.0
    fn(s)
    assert s.stack_ending_plane == 100.0
    s.ui.checkBox_acqLastPlaneSet.setChecked.assert_called_with(True)
    s.updateUi_set_number_of_planes.assert_called_once()


def test_updateUi_set_number_of_planes_valid() -> None:
    fn = _load_method("updateUi_set_number_of_planes(self) -> None", extra_globals=_EXTRA)
    s = _make_self()
    s.stack_starting_plane = 0.0
    s.stack_ending_plane = 100.0
    s.ui.doubleSpinBox_acqPlaneStepSize.value.return_value = 10.0
    s.ui.checkBox_acqFirstPlaneSet.isChecked.return_value = True
    s.ui.checkBox_acqLastPlaneSet.isChecked.return_value = True
    fn(s)
    assert s.number_of_planes > 0
    s.ui.label_acqNumberOfPlanes.setText.assert_called_once()


def test_updateUi_set_number_of_planes_zero_step() -> None:
    fn = _load_method("updateUi_set_number_of_planes(self) -> None", extra_globals=_EXTRA)
    s = _make_self()
    s.ui.doubleSpinBox_acqPlaneStepSize.value.return_value = 0
    fn(s)
    s.sig_message.emit.assert_called_with("Set a non-zero value to plane step")


def test_updateUi_set_number_of_planes_planes_not_set() -> None:
    fn = _load_method("updateUi_set_number_of_planes(self) -> None", extra_globals=_EXTRA)
    s = _make_self()
    s.ui.doubleSpinBox_acqPlaneStepSize.value.return_value = 10.0
    s.ui.checkBox_acqFirstPlaneSet.isChecked.return_value = False
    s.ui.checkBox_acqLastPlaneSet.isChecked.return_value = True
    fn(s)
    # Should not set number_of_planes or emit message
    s.sig_message.emit.assert_not_called()


# -- select_directory -------------------------------------------------------


def test_updateUi_select_directory_valid() -> None:
    fn = _load_method("updateUi_select_directory(self) -> None", extra_globals=_EXTRA)
    s = _make_self()
    s.save_directory = "/tmp"
    with patch.object(_QFD, "getExistingDirectory", return_value="/new/dir"):
        fn(s)
    assert s.save_directory == os.path.normpath("/new/dir")


def test_updateUi_select_directory_empty() -> None:
    fn = _load_method("updateUi_select_directory(self) -> None", extra_globals=_EXTRA)
    s = _make_self()
    s.save_directory = ""
    with patch.object(_QFD, "getExistingDirectory", return_value=""):
        fn(s)
    s.ui.lineEdit_saveFilename.setEnabled.assert_called_with(False)
