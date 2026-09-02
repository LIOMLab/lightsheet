"""Branch-coverage closure for ``lightsheet.gui.shell.controller`` GUI-thread
slots, via real construction.

The real ``Controller_MainWindow`` is constructed via ``make_controller``
(see ``test/_helpers/controller_fixture.py``), which mirrors
``lightsheet/__main__.main()``'s composition root: a mock ``DeviceBundle``
is built, the controller is constructed with ``demo=True``, all four
collaborators (``FrameSaverController`` / ``HardwareManager`` /
``AcquisitionCoordinator`` / ``MotorController``) are wired, and
``hardware_init`` is called so ``self.lasers`` / ``self.camera`` /
``self.siggen`` / ``self.motors`` / ``self.etls`` and the display/status
timers are populated. Each test calls the REAL method on the real
controller and asserts on real attributes / Qt widget state.

Behavior tests — every assertion is on a runtime postcondition (attribute
value, signal emit, widget state), never a static-source grep.
"""

from __future__ import annotations

import os
from unittest.mock import Mock, patch

import pytest
from pytest import FixtureRequest
from pytestqt.qtbot import QtBot

pytest.importorskip("PySide6")

from _helpers.controller_fixture import make_controller

# -- Simple slots -----------------------------------------------------------


def test_updateUi_light_theme_emits_stylesheet(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    received: list[str] = []
    ctrl.sig_stylesheet.connect(lambda v: received.append(v))
    ctrl.updateUi_light_theme()
    assert received == ["light"]


def test_updateUi_dark_theme_emits_stylesheet(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    received: list[str] = []
    ctrl.sig_stylesheet.connect(lambda v: received.append(v))
    ctrl.updateUi_dark_theme()
    assert received == ["dark"]


def test_updateUi_show_hide_images_pane_toggles_both_ways(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    ctrl.show()
    qtbot.waitExposed(ctrl)
    # The images pane starts visible (splitter size > 0).
    assert ctrl.ui.splitter.sizes()[0] > 0
    # Toggle off — hides the pane via splitter.setSizes([0, total]); the
    # splitter size is the authoritative signal (audit #7).
    ctrl.updateUi_show_hide_images_pane()
    assert ctrl.ui.splitter.sizes()[0] == 0
    assert ctrl.ui.action_ShowHideImagesPane.isChecked() is False
    # Toggle back on — restores the pane.
    ctrl.updateUi_show_hide_images_pane()
    assert ctrl.ui.splitter.sizes()[0] > 0
    assert ctrl.ui.action_ShowHideImagesPane.isChecked() is True


def test_updateUi_show_hide_controls_pane_toggles_both_ways(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    ctrl.show()
    qtbot.waitExposed(ctrl)
    # The controls pane starts visible (splitter size > 0). controlsPane is
    # the SECOND widget (index 1).
    assert ctrl.ui.splitter.sizes()[1] > 0
    ctrl.updateUi_show_hide_controls_pane()
    assert ctrl.ui.splitter.sizes()[1] == 0
    assert ctrl.ui.action_ShowHideControlsPane.isChecked() is False
    ctrl.updateUi_show_hide_controls_pane()
    assert ctrl.ui.splitter.sizes()[1] > 0
    assert ctrl.ui.action_ShowHideControlsPane.isChecked() is True


def test_updateUi_show_hide_message_log_toggles_both_ways(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    ctrl.show()
    qtbot.waitExposed(ctrl)
    splitter = ctrl.ui.message_splitter
    # Log starts visible (splitter section > 0).
    assert splitter.sizes()[1] > 0
    # After toggling, the log section is 0 (hidden via splitter sizes).
    ctrl.updateUi_show_hide_message_log()
    assert splitter.sizes()[1] == 0
    assert ctrl.ui.action_ShowHideMessageLog.isChecked() is False
    # Toggle again to show.
    ctrl.updateUi_show_hide_message_log()
    assert splitter.sizes()[1] > 0
    assert ctrl.ui.action_ShowHideMessageLog.isChecked() is True


def test_open_help_calls_webbrowser(qtbot: QtBot, request: FixtureRequest) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    with patch("lightsheet.gui.shell.controller.webbrowser.open_new") as mock_open:
        ctrl.open_help()
    mock_open.assert_called_once()


def test_open_properties_dialog(qtbot: QtBot, request: FixtureRequest) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    with patch("lightsheet.gui.shell.controller.Properties_Dialog") as MockDialog:
        ctrl.open_properties_dialog()
    mock_dlg = MockDialog.return_value
    mock_dlg.setAttribute.assert_called_once()
    mock_dlg.open.assert_called_once()
    mock_dlg.get_properties.assert_called_once()


# -- Motor/mode button helpers ----------------------------------------------


def test_updateUi_motor_buttons_disable(qtbot: QtBot, request: FixtureRequest) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    ctrl.motor_panel.updateUi_motor_buttons(disable_button=True)
    # All buttons should have setEnabled(False) called
    assert ctrl.motor_panel.ui.pushButton_sampleStepUp.isEnabled() is False


def test_updateUi_motor_buttons_enable(qtbot: QtBot, request: FixtureRequest) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    ctrl.motor_panel.updateUi_motor_buttons(disable_button=False)
    assert ctrl.motor_panel.ui.pushButton_sampleStepUp.isEnabled() is True


def test_updateUi_modes_buttons(qtbot: QtBot, request: FixtureRequest) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    # Use the same button object that's in ctrl.ui so the `in` check works.
    btn_enable = ctrl.acquisition_panel.ui.pushButton_acqStartPreviewMode
    ctrl.acquisition_panel.updateUi_modes_buttons([btn_enable])
    assert btn_enable.isEnabled() is True
    assert ctrl.acquisition_panel.ui.pushButton_acqStartLiveMode.isEnabled() is False


def test_updateUi_enable_buttons(qtbot: QtBot, request: FixtureRequest) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    btn = ctrl.acquisition_panel.ui.pushButton_acqStartPreviewMode
    btn.setEnabled(False)
    ctrl.acquisition_panel.updateUi_enable_buttons([btn])
    assert btn.isEnabled() is True


def test_updateUi_disable_buttons(qtbot: QtBot, request: FixtureRequest) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    btn = ctrl.acquisition_panel.ui.pushButton_acqStartPreviewMode
    btn.setEnabled(True)
    ctrl.acquisition_panel.updateUi_disable_buttons([btn])
    assert btn.isEnabled() is False


def test_cache_auto_laser_flags(qtbot: QtBot, request: FixtureRequest) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    ctrl.laser_panel.ui.checkBox_laserOneAutomatic.setChecked(True)
    ctrl.laser_panel.ui.checkBox_laserTwoAutomatic.setChecked(False)
    ctrl._cache_auto_laser_flags()
    assert ctrl._auto_laser1 is True
    assert ctrl._auto_laser2 is False


def test_close_modes_all_active(qtbot: QtBot, request: FixtureRequest) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    ctrl.preview_mode_started = True
    ctrl.live_mode_started = True
    ctrl.stack_mode_started = True
    ctrl.lasers[0].active = True
    ctrl.lasers[1].active = True
    with patch.object(ctrl._hw, "stop_lasers") as mock_stop:
        ctrl.close_modes()
    assert ctrl.preview_mode_started is False
    assert ctrl.live_mode_started is False
    assert ctrl.stack_mode_started is False
    mock_stop.assert_called_once()


def test_close_modes_no_lasers_active(qtbot: QtBot, request: FixtureRequest) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    ctrl.preview_mode_started = True
    ctrl.lasers[0].active = False
    ctrl.lasers[1].active = False
    with patch.object(ctrl._hw, "stop_lasers") as mock_stop:
        ctrl.close_modes()
    assert ctrl.preview_mode_started is False
    mock_stop.assert_not_called()


# -- E-stop / arm-reset -----------------------------------------------------


def test_updateUi_arm_reset_pressed_first_press(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    ctrl._estop_disarmed = False
    ctrl.updateUi_arm_reset_pressed()
    assert ctrl._estop_disarmed is True
    assert ctrl.estop_event.is_set() is False
    # First press transitions to DISARMED; the button label reflects the
    # NEXT action available — "Arm Lasers" (the second press of the
    # two-press re-arm sequence, audit #6).
    assert ctrl.pushButton_armReset.text() == "Arm Lasers"


def test_updateUi_arm_reset_pressed_second_press(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    ctrl._estop_disarmed = True
    ctrl.updateUi_arm_reset_pressed()
    assert ctrl._estop_disarmed is False
    assert ctrl.pushButton_armReset.text() == "Arm/Reset"


# -- Laser readback / status ------------------------------------------------


def test_updateUi_laser_readback(qtbot: QtBot, request: FixtureRequest) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    ctrl.laser_panel.updateUi_laser_readback(0, "100 mW", "")
    assert ctrl.laser_panel.ui.label_laserOneReadback.text() == "100 mW"
    ctrl.laser_panel.updateUi_laser_readback(1, "50 mW", "stale")
    assert ctrl.laser_panel.ui.label_laserTwoReadback.text() == "50 mW"


def test_updateUi_laser2_refresh_clicked(qtbot: QtBot, request: FixtureRequest) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    with patch.object(ctrl._hw, "_refresh_laser2_readback_async") as mock_refresh, \
         patch.object(ctrl._hw, "_poll_laser_status") as mock_poll:
        ctrl.laser_panel.updateUi_laser2_refresh_clicked()
    mock_refresh.assert_called_once()
    mock_poll.assert_called_once_with([1])


def test_updateUi_laser_status_active(qtbot: QtBot, request: FixtureRequest) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    ctrl.laser_panel.updateUi_laser_status(0, "active")
    assert ctrl.laser_panel.ui.label_laserOneStatus.text() == "● ON"


def test_updateUi_laser_status_inactive(qtbot: QtBot, request: FixtureRequest) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    ctrl.laser_panel.updateUi_laser_status(1, "inactive")
    assert ctrl.laser_panel.ui.label_laserTwoStatus.text() == "○ OFF"


def test_updateUi_laser_status_error(qtbot: QtBot, request: FixtureRequest) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    ctrl.laser_panel.updateUi_laser_status(0, "error")
    assert ctrl.laser_panel.ui.label_laserOneStatus.text() == "⚠ FAULT"


# -- Position indicators (fixed mm display unit) ---------------------------


def test_updateUi_position_horizontal(qtbot: QtBot, request: FixtureRequest) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    # Clear the label first — hardware_init already populated it, so a bare
    # `!= ""` assertion would pass even if the method were a no-op. Asserting
    # the method re-writes the expected formatted value proves it ran.
    ctrl.motor_panel.ui.label_sampleCurrentHPosition.setText("")
    expected = "{:.5f} mm".format(ctrl.motors.horizontal.get_position("mm"))
    ctrl.motor_panel.updateUi_position_horizontal()
    assert ctrl.motor_panel.ui.label_sampleCurrentHPosition.text() == expected
    assert ctrl.current_horizontal_position_text == expected


def test_updateUi_position_vertical(qtbot: QtBot, request: FixtureRequest) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    ctrl.motor_panel.ui.label_sampleCurrentVPosition.setText("")
    expected = "{:.5f} mm".format(ctrl.motors.vertical.get_position("mm"))
    ctrl.motor_panel.updateUi_position_vertical()
    assert ctrl.motor_panel.ui.label_sampleCurrentVPosition.text() == expected
    assert ctrl.current_vertical_position_text == expected


def test_updateUi_position_camera(qtbot: QtBot, request: FixtureRequest) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    ctrl.motor_panel.ui.label_cameraCurrentPosition.setText("")
    expected = "{:.5f} mm".format(ctrl.motors.camera.get_position("mm"))
    ctrl.motor_panel.updateUi_position_camera()
    assert ctrl.motor_panel.ui.label_cameraCurrentPosition.text() == expected
    assert ctrl.current_camera_position_text == expected


# -- Laser amplitude / toggle -----------------------------------------------


def test_updateUi_laser1_amplitude(qtbot: QtBot, request: FixtureRequest) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    ctrl.laser_panel.ui.doubleSpinBox_laserOneAmplitude.setValue(50.0)
    with patch.object(ctrl._laser1_amplitude_timer, "start") as mock_start:
        ctrl.laser_panel.updateUi_laser1_amplitude()
    assert ctrl.laser1_power_pct == 50.0
    mock_start.assert_called_with(300)


def test_updateUi_laser2_amplitude(qtbot: QtBot, request: FixtureRequest) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    ctrl.laser_panel.ui.doubleSpinBox_laserTwoAmplitude.setValue(75.0)
    with patch.object(ctrl._laser2_amplitude_timer, "start") as mock_start:
        ctrl.laser_panel.updateUi_laser2_amplitude()
    assert ctrl.laser2_power_pct == 75.0
    mock_start.assert_called_with(300)


def test_apply_laser1_amplitude(qtbot: QtBot, request: FixtureRequest) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    ctrl.laser_panel.ui.doubleSpinBox_laserOneAmplitude.setValue(50.0)
    with patch("lightsheet.gui.panels.laser_panel.threading.Thread") as MockThread:
        MockThread.return_value.start = Mock()
        ctrl.laser_panel._apply_laser1_amplitude()
        MockThread.return_value.start.assert_called_once()


def test_apply_laser2_amplitude(qtbot: QtBot, request: FixtureRequest) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    ctrl.laser_panel.ui.doubleSpinBox_laserTwoAmplitude.setValue(75.0)
    with patch("lightsheet.gui.panels.laser_panel.threading.Thread") as MockThread:
        MockThread.return_value.start = Mock()
        ctrl.laser_panel._apply_laser2_amplitude()
        MockThread.return_value.start.assert_called_once()


def test_laser1_toggle_button(qtbot: QtBot, request: FixtureRequest) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    with patch("lightsheet.gui.panels.laser_panel.threading.Thread") as MockThread:
        MockThread.return_value.start = Mock()
        ctrl.laser_panel.laser1_toggle_button()
        MockThread.return_value.start.assert_called_once()


def test_laser2_toggle_button(qtbot: QtBot, request: FixtureRequest) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    with patch("lightsheet.gui.panels.laser_panel.threading.Thread") as MockThread:
        MockThread.return_value.start = Mock()
        ctrl.laser_panel.laser2_toggle_button()
        MockThread.return_value.start.assert_called_once()


# -- Mode button slots ------------------------------------------------------


def test_updateUi_preview_mode_button_start(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    ctrl.preview_mode_started = False
    with patch.object(ctrl, "close_modes") as mock_close, \
         patch.object(ctrl, "_cache_auto_laser_flags") as mock_cache:
        ctrl.acquisition_panel.updateUi_preview_mode_button()
    assert ctrl.preview_mode_started is True
    mock_close.assert_called_once()
    mock_cache.assert_called_once()


def test_updateUi_preview_mode_button_stop(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    ctrl.preview_mode_started = True
    ctrl.acquisition_panel.updateUi_preview_mode_button()
    assert ctrl.preview_mode_started is False
    assert (
        ctrl.acquisition_panel.ui.pushButton_acqStartPreviewMode.text()
        == "Start Preview Mode"
    )


def test_updateUi_post_preview_mode(qtbot: QtBot, request: FixtureRequest) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    with patch.object(ctrl.acquisition_panel, "updateUi_modes_buttons") as mock_modes, \
         patch.object(ctrl, "updateUi_message_printer") as mock_msg:
        ctrl.acquisition_panel.updateUi_post_preview_mode()
    mock_modes.assert_called_once()
    mock_msg.assert_called_with("->Preview mode stopped")


def test_updateUi_live_mode_button_start(qtbot: QtBot, request: FixtureRequest) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    ctrl.live_mode_started = False
    with patch.object(ctrl, "close_modes") as mock_close:
        ctrl.acquisition_panel.updateUi_live_mode_button()
    assert ctrl.live_mode_started is True
    mock_close.assert_called_once()


def test_updateUi_live_mode_button_stop(qtbot: QtBot, request: FixtureRequest) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    ctrl.live_mode_started = True
    ctrl.acquisition_panel.updateUi_live_mode_button()
    assert ctrl.live_mode_started is False
    assert (
        ctrl.acquisition_panel.ui.pushButton_acqStartLiveMode.text()
        == "Start Live Mode"
    )


def test_updateUi_post_live_mode(qtbot: QtBot, request: FixtureRequest) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    with patch.object(ctrl.acquisition_panel, "updateUi_modes_buttons"), \
         patch.object(ctrl, "updateUi_message_printer") as mock_msg:
        ctrl.acquisition_panel.updateUi_post_live_mode()
    mock_msg.assert_called_with("->Live mode stopped")


def test_updateUi_single_mode_button_start(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    ctrl.single_mode_started = False
    with patch.object(ctrl, "close_modes") as mock_close:
        ctrl.acquisition_panel.updateUi_single_mode_button()
    assert ctrl.single_mode_started is True
    mock_close.assert_called_once()


def test_updateUi_post_single_mode(qtbot: QtBot, request: FixtureRequest) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    ctrl.acquisition_panel.updateUi_post_single_mode()
    assert ctrl.single_mode_started is False
    assert (
        ctrl.acquisition_panel.ui.pushButton_acqGetSingleImage.text()
        == "Get Single Image"
    )


def test_updateUi_post_stack_mode(qtbot: QtBot, request: FixtureRequest) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    ctrl.acquisition_panel.updateUi_post_stack_mode()
    assert ctrl.stack_mode_started is False
    assert ctrl.stack_panel.ui.pushButton_acqStartStackMode.text() == "Start Stack Mode"


# -- Stack mode button (both branches) --------------------------------------


def test_updateUi_stack_mode_button_stop(qtbot: QtBot, request: FixtureRequest) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    ctrl.stack_mode_started = True
    ctrl.acquisition_panel.updateUi_stack_mode_button()
    assert ctrl.stack_mode_started is False


def test_updateUi_stack_mode_button_start_valid(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    ctrl.stack_mode_started = False
    ctrl.saving_allowed = True
    ctrl.stack_starting_plane = 0.0
    ctrl.stack_ending_plane = 100.0
    ctrl.stack_first_plane_set = True
    ctrl.stack_last_plane_set = True
    ctrl.stack_panel.ui.doubleSpinBox_acqPlaneStepSize.setValue(10.0)
    with patch("lightsheet.gui.panels.acquisition_panel.QMessageBox"):
        ctrl.acquisition_panel.updateUi_stack_mode_button()
    assert ctrl.stack_mode_started is True


def test_updateUi_stack_mode_button_start_invalid(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    ctrl.stack_mode_started = False
    ctrl.stack_first_plane_set = False
    messages: list[str] = []
    beeps: list[None] = []
    ctrl.sig_message.connect(lambda msg: messages.append(msg))
    ctrl.sig_beep.connect(lambda: beeps.append(None))
    with patch("lightsheet.gui.panels.acquisition_panel.QMessageBox") as MockMsg:
        MockMsg.Ok = 1
        MockMsg.warning.return_value = MockMsg.Ok
        ctrl.acquisition_panel.updateUi_stack_mode_button()
    assert ctrl.stack_mode_started is False
    assert len(messages) == 1
    assert len(beeps) == 1


def test_updateUi_stack_mode_button_start_reverse_direction(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    ctrl.stack_mode_started = False
    ctrl.saving_allowed = True
    ctrl.stack_starting_plane = 100.0
    ctrl.stack_ending_plane = 0.0
    ctrl.stack_first_plane_set = True
    ctrl.stack_last_plane_set = True
    # Stack plane positions + step are in µm (the fixed stack-display
    # unit; the global units toggle is gone). Set the spinbox values
    # directly without a units toggle.
    ctrl.stack_panel.ui.doubleSpinBox_acqFirstPlane.setValue(100.0)
    ctrl.stack_panel.ui.doubleSpinBox_acqLastPlane.setValue(0.0)
    ctrl.stack_panel.ui.doubleSpinBox_acqPlaneStepSize.setValue(10.0)
    with patch("lightsheet.gui.panels.acquisition_panel.QMessageBox"):
        ctrl.acquisition_panel.updateUi_stack_mode_button()
    assert ctrl.stack_step == -10.0


def test_updateUi_stack_mode_button_start_nosave_yes(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    ctrl.stack_mode_started = False
    ctrl.saving_allowed = False
    ctrl.stack_starting_plane = 0.0
    ctrl.stack_ending_plane = 100.0
    ctrl.stack_first_plane_set = True
    ctrl.stack_last_plane_set = True
    ctrl.stack_panel.ui.doubleSpinBox_acqPlaneStepSize.setValue(10.0)
    with patch("lightsheet.gui.panels.acquisition_panel.QMessageBox") as MockMsg:
        MockMsg.Yes = 1
        MockMsg.No = 0
        MockMsg.question.return_value = MockMsg.Yes
        ctrl.acquisition_panel.updateUi_stack_mode_button()
    assert ctrl.stack_mode_started is True


# -- validate_file_name -----------------------------------------------------


def test_validate_file_name_valid(qtbot: QtBot, request: FixtureRequest) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    ctrl.save_panel.ui.lineEdit_saveFilename.setText("test_file")
    ctrl.save_directory = "/tmp"
    ctrl.save_panel.validate_file_name()
    assert ctrl.saving_allowed is True


def test_validate_file_name_empty(qtbot: QtBot, request: FixtureRequest) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    ctrl.save_panel.ui.lineEdit_saveFilename.setText("")
    ctrl.save_directory = ""
    ctrl.save_panel.validate_file_name()
    assert ctrl.saving_allowed is False


def test_validate_file_name_special_chars(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    ctrl.save_panel.ui.lineEdit_saveFilename.setText("test@file#name")
    ctrl.save_directory = "/tmp"
    ctrl.save_panel.validate_file_name()
    assert ctrl.saving_allowed is True
    # Special chars should be replaced with _
    assert "_" in ctrl.save_filename


# -- save_single_image ------------------------------------------------------


def test_updateUi_save_single_image_saving_allowed_crop(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    ctrl.saving_allowed = True
    ctrl.save_directory = "/tmp"
    ctrl.save_filename = "test"
    ctrl.image_hor_pos_text = "0.0"
    ctrl.image_ver_pos_text = "0.0"
    ctrl.image_cam_pos_text = "0.0"
    ctrl.buffer = Mock()
    ctrl.save_panel.ui.radioButton_saveAllCrop.setChecked(True)
    ctrl.save_panel.ui.radioButton_saveAllFull.setChecked(False)
    ctrl._fs.reinit = Mock()
    ctrl._fs.set_files = Mock()
    ctrl._fs.crop_buffer = Mock(return_value=Mock())
    ctrl._fs.enqueue_buffer = Mock()
    ctrl._fs.start_saving = Mock()
    ctrl._fs.stop_saving = Mock()
    ctrl._fs.add_sample_name = Mock()
    ctrl._fs.add_motor_parameters = Mock()
    ctrl.save_panel.updateUi_save_single_image()
    ctrl._fs.reinit.assert_called_with(1)
    ctrl._fs.set_files.assert_called_with(
        1, ctrl.save_filepath, "singleImage", 1, "ETLscan", wavelengths=[555]
    )
    ctrl._fs.start_saving.assert_called_once()
    ctrl._fs.stop_saving.assert_called_once()


def test_updateUi_save_single_image_saving_allowed_full(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    ctrl.saving_allowed = True
    ctrl.save_directory = "/tmp"
    ctrl.save_filename = "test"
    ctrl.image_hor_pos_text = "0.0"
    ctrl.image_ver_pos_text = "0.0"
    ctrl.image_cam_pos_text = "0.0"
    ctrl.buffer = Mock()
    ctrl.save_panel.ui.radioButton_saveAllCrop.setChecked(False)
    ctrl.save_panel.ui.radioButton_saveAllFull.setChecked(True)
    ctrl._fs.reinit = Mock()
    ctrl._fs.set_files = Mock()
    ctrl._fs.enqueue_buffer = Mock()
    ctrl._fs.start_saving = Mock()
    ctrl._fs.stop_saving = Mock()
    ctrl._fs.add_sample_name = Mock()
    ctrl._fs.add_motor_parameters = Mock()
    ctrl.save_panel.updateUi_save_single_image()
    ctrl._fs.set_files.assert_called_with(
        1, ctrl.save_filepath, "singleImage", 1, "FullETLscan", wavelengths=[555]
    )


def test_updateUi_save_single_image_saving_allowed_reconstructed(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    ctrl.saving_allowed = True
    ctrl.save_directory = "/tmp"
    ctrl.save_filename = "test"
    ctrl.image_hor_pos_text = "0.0"
    ctrl.image_ver_pos_text = "0.0"
    ctrl.image_cam_pos_text = "0.0"
    ctrl.reconstructed_frame = Mock()
    ctrl.save_panel.ui.radioButton_saveAllCrop.setChecked(False)
    ctrl.save_panel.ui.radioButton_saveAllFull.setChecked(False)
    ctrl._fs.reinit = Mock()
    ctrl._fs.set_files = Mock()
    ctrl._fs.enqueue_buffer = Mock()
    ctrl._fs.start_saving = Mock()
    ctrl._fs.stop_saving = Mock()
    ctrl._fs.add_sample_name = Mock()
    ctrl._fs.add_motor_parameters = Mock()
    ctrl.save_panel.updateUi_save_single_image()
    ctrl._fs.set_files.assert_called_with(
        1,
        ctrl.save_filepath,
        "singleImage",
        1,
        "reconstructed_frame",
        wavelengths=[555],
    )


def test_updateUi_save_single_image_not_allowed(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    ctrl.saving_allowed = False
    ctrl.save_directory = ""
    ctrl.save_filename = ""
    ctrl.save_panel.ui.lineEdit_saveFilename.setText("")
    messages: list[str] = []
    beeps: list[None] = []
    ctrl.sig_message.connect(lambda msg: messages.append(msg))
    ctrl.sig_beep.connect(lambda: beeps.append(None))
    with patch("lightsheet.gui.panels.save_panel.QMessageBox") as MockMsg:
        MockMsg.Ok = 1
        MockMsg.warning.return_value = MockMsg.Ok
        ctrl.save_panel.updateUi_save_single_image()
    assert len(beeps) == 1
    assert len(messages) == 1


# -- Stack set points / number of planes ------------------------------------


def test_updateUi_set_stack_mode_starting_point(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    with patch.object(
        ctrl.stack_panel, "updateUi_set_number_of_planes"
    ) as mock_set_planes:
        ctrl.stack_panel.updateUi_set_stack_mode_starting_point()
    assert ctrl.stack_starting_plane == ctrl.motors.horizontal.get_position("\u03bcm")
    assert ctrl.stack_first_plane_set is True
    assert (
        ctrl.stack_panel.ui.doubleSpinBox_acqFirstPlane.value()
        == ctrl.stack_starting_plane
    )
    mock_set_planes.assert_called_once()


def test_updateUi_set_stack_mode_ending_point(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    with patch.object(
        ctrl.stack_panel, "updateUi_set_number_of_planes"
    ) as mock_set_planes:
        ctrl.stack_panel.updateUi_set_stack_mode_ending_point()
    assert ctrl.stack_ending_plane == ctrl.motors.horizontal.get_position("\u03bcm")
    assert ctrl.stack_last_plane_set is True
    assert (
        ctrl.stack_panel.ui.doubleSpinBox_acqLastPlane.value()
        == ctrl.stack_ending_plane
    )
    mock_set_planes.assert_called_once()


def test_updateUi_set_number_of_planes_valid(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    ctrl.stack_starting_plane = 0.0
    ctrl.stack_ending_plane = 100.0
    ctrl.stack_panel.ui.doubleSpinBox_acqPlaneStepSize.setValue(10.0)
    ctrl.stack_first_plane_set = True
    ctrl.stack_last_plane_set = True
    ctrl.stack_panel.updateUi_set_number_of_planes()
    assert ctrl.number_of_planes > 0
    assert ctrl.stack_panel.ui.label_acqNumberOfPlanes.text() != ""


def test_updateUi_set_number_of_planes_zero_step(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    # The spinbox has a default minimum of 0.25; lower it so 0 is accepted.
    ctrl.stack_panel.ui.doubleSpinBox_acqPlaneStepSize.setMinimum(0)
    ctrl.stack_panel.ui.doubleSpinBox_acqPlaneStepSize.setValue(0)
    messages: list[str] = []
    ctrl.sig_message.connect(lambda msg: messages.append(msg))
    ctrl.stack_panel.updateUi_set_number_of_planes()
    assert any("non-zero" in m for m in messages)


def test_updateUi_set_number_of_planes_planes_not_set(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    ctrl.stack_panel.ui.doubleSpinBox_acqPlaneStepSize.setValue(10.0)
    ctrl.stack_first_plane_set = False
    ctrl.stack_last_plane_set = True
    messages: list[str] = []
    ctrl.sig_message.connect(lambda msg: messages.append(msg))
    ctrl.stack_panel.updateUi_set_number_of_planes()
    # Should not set number_of_planes or emit message
    assert len(messages) == 0


# -- select_directory -------------------------------------------------------


def test_updateUi_select_directory_valid(qtbot: QtBot, request: FixtureRequest) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    ctrl.save_directory = "/tmp"
    with patch(
        "lightsheet.gui.panels.save_panel.QFileDialog.getExistingDirectory",
        return_value="/new/dir",
    ):
        ctrl.save_panel.updateUi_select_directory()
    assert ctrl.save_directory == os.path.normpath("/new/dir")


def test_updateUi_select_directory_empty(qtbot: QtBot, request: FixtureRequest) -> None:
    ctrl, _bundle = make_controller(qtbot, request)
    ctrl.save_directory = ""
    with patch(
        "lightsheet.gui.panels.save_panel.QFileDialog.getExistingDirectory",
        return_value="",
    ):
        ctrl.save_panel.updateUi_select_directory()
    assert ctrl.save_panel.ui.lineEdit_saveFilename.isEnabled() is False


# --------------------------------------------------------------------------- #
# Branch-coverage closure: defensive / alternate-path branches not hit by
# the tests above.
# --------------------------------------------------------------------------- #


def test_updateUi_single_mode_button_already_started_is_noop(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """updateUi_single_mode_button: when single_mode_started is already
    True, the method is a no-op (does not call close_modes, does not
    spawn a worker thread). Covers the 1674->exit branch."""
    ctrl, _bundle = make_controller(qtbot, request)
    ctrl.single_mode_started = True
    with patch.object(ctrl, "close_modes") as mock_close:
        ctrl.acquisition_panel.updateUi_single_mode_button()
    mock_close.assert_not_called()
    assert ctrl.single_mode_started is True


def test_updateUi_initial_hardware_state_lightsheet_shutter_mode(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """updateUi_initial_hardware_state: when the camera shutter_mode is
    'Lightsheet', the shutter-mode combo is set to index 1 (Lightsheet).
    Covers the 1205->1206 branch (the existing wavelength-labels test
    covers the Rolling else branch)."""
    ctrl, _bundle = make_controller(qtbot, request)
    # Set the camera's shutter_mode to Lightsheet so the
    # `if self.camera.shutter_mode == "Lightsheet"` branch fires and
    # sets the combo to index 1. Block signals on the combo so the
    # insertItems / setCurrentIndex calls do not fire currentTextChanged,
    # which would invoke _acq.updateUi_camera_shutter_mode and overwrite
    # camera.shutter_mode from the combo text before the branch check.
    ctrl.camera.shutter_mode = "Lightsheet"
    ctrl.acquisition_panel.ui.comboBox_cameraShutterMode.blockSignals(True)
    try:
        ctrl.updateUi_initial_hardware_state()
    finally:
        ctrl.acquisition_panel.ui.comboBox_cameraShutterMode.blockSignals(False)
    assert ctrl.acquisition_panel.ui.comboBox_cameraShutterMode.currentIndex() == 1


def test_hardware_init_non_demo_shows_ready_status(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """hardware_init: when _demo_mode is False, the statusbar shows
    'Ready' (not the demo-mode message). Covers the 836 else branch.
    Re-calling hardware_init on the already-initialised mock bundle is
    safe — the mock HAL re-inits idempotently and the fixture teardown
    stops the timers and sip.deletes the controller."""
    ctrl, _bundle = make_controller(qtbot, request)
    ctrl._demo_mode = False
    ctrl.hardware_init()
    assert "Ready" in ctrl.ui.statusbar.currentMessage()
    # Restore demo mode so teardown's closeEvent does not persist stack
    # params to the real config.ini.
    ctrl._demo_mode = True

