"""
Behavioral regression tests for Phase 01 controller methods that cannot be
exercised by importing Controller_MainWindow on the Mac dev box (PyQt5 is not
installed, so `from lightsheet.gui.controller import Controller_MainWindow` raises
ModuleNotFoundError).

Each test extracts the REAL method body from lightsheet/gui/controller.py and exec's it
in a controlled namespace, then calls the resulting function against a minimal
Mock stand-in `self`. This runs the same code that runs on the rig — proving
runtime behavior, not a string match on the source. See AGENTS.md §5: never
write static-source grep tests; exercise the real method via exec of its
extracted body when the class cannot be instantiated.

The `_read_controller_source` / `_slice_method` / `_load_method` helpers mirror
test/test_laser_controls.py. `_load_method` seeds the exec namespace with the
module-level globals the extracted body references (datetime, logging) so the
function can resolve them at runtime.

Coverage (Phase 01 gaps left after commit 3483180 removed the static-source
tests):
  G1 — start_lasers surfaces a laser-1 DAQ write failure (LSR-01 / G-01-1)
  G2 — acquire_scan aborts on recorder timeout before copy_recorder_images
       (BUG-01)
  G3 — acquire_scan surfaces a siggen create_scanner failure before the
       recorder is primed (BUG-01 / G-01-5)
  G4 — start_lasers reads cached auto-laser flags, never a Qt widget
       (BUG-01 / G-01-5)
  G5 — preview_mode_worker polls estop_event and breaks before frame
       acquisition; the finished signal still fires exactly once (LSR-04 / CR-01)
  G6 — updateUi_initial_hardware_state sets wavelength labels from the live
       list[ILaser] instances, not hardcoded numbers (LSR-05)
"""

import threading
from unittest.mock import Mock

from _helpers.controller import _ACQ_SRC, _HW_SRC, _load_method


# --------------------------------------------------------------------------- #
# G1 — start_lasers surfaces a laser-1 DAQ write failure (LSR-01 / G-01-1)
# --------------------------------------------------------------------------- #


def test_start_lasers_surfaces_laser1_daq_error() -> None:
    """When self.lasers[0].on() leaves .error set, start_lasers must emit
    an operator message naming the cause and reset the flag — a failed
    laser-1 DAQ start is no longer a silent no-op (G-01-1)."""
    start_lasers = _load_method("start_lasers(self) -> None", src_path=_HW_SRC)

    laser1 = Mock()
    laser1.label = "Laser 1 (555 nm)"
    laser1.max_power = 300.0
    laser1.error = 1  # .on() "failed" the DAQ write
    laser1.error_message = "daq write failed"
    laser1.power = 0.0
    laser1.get_output_power = Mock(return_value=0.0)

    standin = Mock()
    standin._auto_laser1 = True
    standin._auto_laser2 = False
    standin.laser1_power_pct = 50
    standin.lasers = [laser1, Mock()]
    standin.sig_message = Mock()
    standin.sig_laser_status = Mock()
    standin.sig_laser_readback = Mock()
    # HardwareManager reads shell-owned state via self._shell.*
    standin._shell = standin

    start_lasers(standin)

    # An operator message was emitted naming the failure.
    assert standin.sig_message.emit.called, (
        "start_lasers must emit sig_message when self.lasers[0].error is "
        "set after .on() — a silent no-op is the G-01-1 regression."
    )
    msg = standin.sig_message.emit.call_args[0][0]
    assert "daq write failed" in msg
    # The flag is reset so the warning fires once per failure.
    assert laser1.error == 0


# --------------------------------------------------------------------------- #
# G2 — acquire_scan aborts on recorder timeout before copy_recorder_images
#      (BUG-01)
# --------------------------------------------------------------------------- #


def test_acquire_scan_aborts_on_recorder_timeout_before_copy() -> None:
    """When camera.recorder_timeout_status is True after monitor_recorder,
    acquire_scan must emit the timeout warning, tear down the recorder and
    scanner, disarm the camera, and return BEFORE copy_recorder_images is
    ever reached — a timed-out plane can never be saved as zero-filled
    frames (BUG-01)."""
    acquire_scan = _load_method("acquire_scan(self) -> None", src_path=_ACQ_SRC)

    siggen = Mock()
    siggen.error = 0
    siggen.error_message = ""
    siggen.waveform_cycles = 1
    siggen.waveform_metadata = {}

    camera = Mock()
    camera.recorder_timeout_status = True  # the recorder timed out

    standin = Mock()
    standin.siggen = siggen
    standin.camera = camera
    # acquire_scan now lives on AcquisitionCoordinator and reads shell-owned
    # state via self._shell.* (sig_message, ui.*, _fs, buffer, etc.).
    shell = Mock()
    shell.sig_message = Mock()
    # acquire_scan reads self._shell.ui.lineEdit_saveDescription.text() for
    # metadata before the timeout check; a Mock ui satisfies that without
    # exercising Qt.
    shell.ui = Mock()
    standin._shell = shell

    acquire_scan(standin)

    # The defining assertion: copy_recorder_images must NOT be called.
    camera.copy_recorder_images.assert_not_called()
    # The operator was warned.
    assert shell.sig_message.emit.called
    msg = shell.sig_message.emit.call_args[0][0]
    assert "Camera timeout" in msg
    # Teardown ran and the camera was disarmed before returning.
    camera.delete_recorder.assert_called_once()
    siggen.delete_scanner.assert_called_once()
    camera.disarm.assert_called_once()


# --------------------------------------------------------------------------- #
# G3 — acquire_scan surfaces a siggen create_scanner failure before the
#      recorder is primed (BUG-01 / G-01-5)
# --------------------------------------------------------------------------- #


def test_acquire_scan_surfaces_siggen_error_before_recorder() -> None:
    """When create_scanner() sets self.siggen.error (its bare-except on DAQ
    task creation failure), acquire_scan must emit an operator message,
    delete the scanner, disarm the camera, and return BEFORE
    start_recorder() is ever called — a DAQ scan-task failure is no longer
    masked as a silent 15 s camera timeout (G-01-5)."""
    acquire_scan = _load_method("acquire_scan(self) -> None", src_path=_ACQ_SRC)

    siggen = Mock()
    siggen.error = 0
    siggen.error_message = ""
    siggen.waveform_cycles = 1
    siggen.waveform_metadata = {}

    def _fail_create_scanner() -> None:
        # create_scanner() sets siggen.error without raising.
        siggen.error = 1
        siggen.error_message = "create_scan error"

    siggen.create_scanner.side_effect = _fail_create_scanner

    camera = Mock()
    camera.recorder_timeout_status = False

    standin = Mock()
    standin.siggen = siggen
    standin.camera = camera
    # acquire_scan now lives on AcquisitionCoordinator and reads shell-owned
    # state via self._shell.* (sig_message, ui.*, _fs, buffer, etc.).
    shell = Mock()
    shell.sig_message = Mock()
    shell.ui = Mock()
    standin._shell = shell

    acquire_scan(standin)

    # The recorder was never primed — the failure surfaced before it.
    camera.start_recorder.assert_not_called()
    # The operator saw the real DAQ cause.
    assert shell.sig_message.emit.called
    msg = shell.sig_message.emit.call_args[0][0]
    assert "Scan task creation failed" in msg
    assert "create_scan error" in msg
    # Teardown ran.
    siggen.delete_scanner.assert_called_once()
    camera.disarm.assert_called_once()


# --------------------------------------------------------------------------- #
# G4 — start_lasers reads cached auto-laser flags, never a Qt widget
#      (BUG-01 / G-01-5)
# --------------------------------------------------------------------------- #


class _WidgetRaisingUI:
    """A stand-in for self.ui whose laser auto-checkboxes raise
    AttributeError on access. If start_lasers ever reverts to reading
    checkBox_laserOneAutomatic / checkBox_laserTwoAutomatic directly, the
    method raises and this test fails — proving the worker reads the cached
    bools (self._auto_laser1 / self._auto_laser2), not Qt widgets."""

    def __getattr__(self, name: str) -> Mock:
        if name in ("checkBox_laserOneAutomatic", "checkBox_laserTwoAutomatic"):
            raise AttributeError(
                f"start_lasers must not read Qt widget {name} from a worker "
                f"thread — use the cached self._auto_laser* flag "
                f"(AGENTS.md §11)."
            )
        return Mock()


def test_start_lasers_reads_cached_flags_not_widgets() -> None:
    """start_lasers runs on an acquisition worker thread and must read only
    the cached auto-laser flags sampled on the GUI thread — never a Qt
    widget (AGENTS.md §11 cross-thread rule, G-01-5). With the auto-laser1
    flag True and a UI that raises on checkbox access, start_lasers must
    energize laser 1 without touching the widget."""
    start_lasers = _load_method("start_lasers(self) -> None", src_path=_HW_SRC)

    laser1 = Mock()
    laser1.label = "Laser 1 (555 nm)"
    laser1.max_power = 300.0
    laser1.error = 0
    laser1.power = 0.0
    laser1.get_output_power = Mock(return_value=0.0)

    standin = Mock()
    standin.ui = _WidgetRaisingUI()
    standin._auto_laser1 = True
    standin._auto_laser2 = False
    standin.laser1_power_pct = 50
    standin.lasers = [laser1, Mock()]
    standin.sig_message = Mock()
    standin.sig_laser_status = Mock()
    standin.sig_laser_readback = Mock()
    standin._shell = standin  # HardwareManager reads shell-owned state via self._shell.*

    # Must not raise — if it read the widget, _WidgetRaisingUI raises.
    start_lasers(standin)

    laser1.on.assert_called_once()


# --------------------------------------------------------------------------- #
# G5 — preview_mode_worker polls estop_event and breaks before frame
#      acquisition; the finished signal fires exactly once (LSR-04 / CR-01)
# --------------------------------------------------------------------------- #


def test_preview_mode_worker_breaks_on_estop_before_frame_acquisition() -> None:
    """With estop_event set before the worker loop starts, the E-stop poll
    at the top of preview_mode_worker's while loop must break before any
    per-frame acquisition work (start_recorder / copy_recorder_images), and
    the finished signal must still fire exactly once from the finally block
    (CR-01 — preview now aligns with live/single/stack per AGENTS.md §2)."""
    preview_mode_worker = _load_method(
        "preview_mode_worker(self) -> None", src_path=_ACQ_SRC
    )

    estop_event = threading.Event()
    estop_event.set()  # E-stop actuated before the loop starts

    camera = Mock()

    standin = Mock()
    standin.camera = camera
    # preview_mode_worker now lives on AcquisitionCoordinator and reads
    # shell-owned state via self._shell.* (estop_event,
    # preview_mode_started, ui.*, _fs, sig_message,
    # sig_preview_mode_finished).
    shell = Mock()
    shell.estop_event = estop_event
    shell.preview_mode_started = True
    shell.ui = Mock()  # doubleSpinBox_cameraExposureTime.value() for setup
    shell._fs = Mock()
    shell.sig_message = Mock()
    shell.sig_preview_mode_finished = Mock()
    standin._shell = shell

    preview_mode_worker(standin)

    # No per-frame acquisition work ran — the estop poll broke first.
    camera.start_recorder.assert_not_called()
    camera.copy_recorder_images.assert_not_called()
    # The finished signal fired exactly once (the finally block).
    assert shell.sig_preview_mode_finished.emit.call_count == 1


# --------------------------------------------------------------------------- #
# G6 — updateUi_initial_hardware_state sets wavelength labels from the live
#      list[ILaser] instances (LSR-05)
# --------------------------------------------------------------------------- #


def test_wavelength_labels_set_from_live_instances() -> None:
    """updateUi_initial_hardware_state must set the wavelength labels from
    the live self.lasers[0].wavelength and self.lasers[1].wavelength
    instances — not hardcoded numbers — so the operator sees the real
    configured wavelength (LSR-05)."""
    updateUi_initial_hardware_state = _load_method(
        "updateUi_initial_hardware_state(self) -> None"
    )

    siggen = Mock()
    siggen.galvo_activated = False
    siggen.galvo_inverted = False
    siggen.galvo_left_amplitude = 0.0
    siggen.galvo_right_amplitude = 0.0
    siggen.galvo_left_offset = 0.0
    siggen.galvo_right_offset = 0.0
    siggen.etl_activated = False
    siggen.etl_left_amplitude = 0.0
    siggen.etl_right_amplitude = 0.0
    siggen.etl_left_offset = 0.0
    siggen.etl_right_offset = 0.0
    siggen.etl_steps = 0

    camera = Mock()
    camera.exposure_time = 0.01
    camera.lightsheet_line_time = 0.0001
    camera.lightsheet_exposed_lines = 1
    camera.lightsheet_delay_lines = 0
    camera.shutter_mode = "Rolling"

    # self.lasers is a list[ILaser] — index 0 = Laser 1 (555 nm DAQ),
    # index 1 = Laser 2 (640 nm iBeam). The wavelength labels read
    # self.lasers[i].wavelength from the live instances.
    laser1 = Mock()
    laser1.wavelength = 555  # green DAQ laser
    laser2 = Mock()
    laser2.wavelength = 640  # red iBeam

    standin = Mock()
    standin.ui = Mock()
    standin.siggen = siggen
    standin.camera = camera
    standin.lasers = [laser1, laser2]
    standin.laser1_power_pct = 0
    standin.laser2_power_pct = 0
    # updateUi_initial_hardware_state calls these helpers at the end;
    # as auto-Mock callables they are no-ops here. updateUi_camera_shutter_mode
    # now lives on the AcquisitionCoordinator (extracted from the shell), so
    # the retargeted call site reads self._acq.updateUi_camera_shutter_mode();
    # a generic Mock sub-attribute satisfies it.
    standin._acq = Mock()
    standin.updateUi_units = Mock()

    updateUi_initial_hardware_state(standin)

    label_72_text = standin.ui.label_72.setText.call_args[0][0]
    label_73_text = standin.ui.label_73.setText.call_args[0][0]
    assert "555" in label_72_text, (
        "label_72 must show the live lasers[0].wavelength (555), not a "
        "hardcoded number."
    )
    assert "640" in label_73_text, (
        "label_73 must show the live lasers[1].wavelength (640), not a hardcoded number."
    )
    # Toggle buttons are relabeled with the live wavelengths too.
    toggle1_text = standin.ui.pushButton_laserOneToggle.setText.call_args[0][0]
    toggle2_text = standin.ui.pushButton_laserTwoToggle.setText.call_args[0][0]
    assert "555" in toggle1_text
    assert "640" in toggle2_text


# --------------------------------------------------------------------------- #
# G7 — updateUi_estop_pressed warn branch: fires when a laser's off() leaves
#      error truthy, does NOT fire when all off() calls succeed (AGENTS.md §2).
# --------------------------------------------------------------------------- #


def test_estop_warn_branch_fires_for_failed_laser() -> None:
    """updateUi_estop_pressed must check laser.error after each off() and
    emit an operator warning naming the failed laser when off() leaves
    error truthy — the D-06 E-stop safety arc. With one laser reporting
    a clean off() (error=0) and one reporting a failed off() (error=1),
    the warn branch must fire EXACTLY ONCE for the failed laser, naming
    its label and error_message, and reset the error flag after warning
    (AGENTS.md §2: never silently show a clean state when a laser may
    still be emitting)."""
    updateUi_estop_pressed = _load_method(
        "updateUi_estop_pressed(self) -> None"
    )

    laser_ok = Mock()
    laser_ok.error = 0
    laser_ok.label = "Laser 1 (555 nm)"

    laser_failed = Mock()
    laser_failed.error = 1
    laser_failed.error_message = "daq write failed"
    laser_failed.label = "Laser 2 (640 nm)"

    standin = Mock()
    standin.estop_event = Mock()
    standin.lasers = [laser_ok, laser_failed]
    standin.sig_message = Mock()
    standin._hw = Mock()
    standin.label_estopStatus = Mock()
    standin.pushButton_estop = Mock()

    updateUi_estop_pressed(standin)

    # Cooperative-abort Event set on the GUI thread.
    standin.estop_event.set.assert_called_once()
    # Both lasers driven off synchronously.
    laser_ok.off.assert_called_once()
    laser_failed.off.assert_called_once()
    # The warn branch fired for the failed laser — find the emit call
    # whose message names the failed laser's label and error_message.
    emit_calls = [c.args[0] for c in standin.sig_message.emit.call_args_list]
    warn_msgs = [
        m for m in emit_calls
        if "Laser 2 (640 nm)" in m and "daq write failed" in m
    ]
    assert len(warn_msgs) == 1, (
        f"warn branch must fire exactly once for the failed laser; "
        f"got {len(warn_msgs)} warn messages in {emit_calls}"
    )
    assert "E-STOP" in warn_msgs[0]
    assert "STILL BE ON" in warn_msgs[0]
    # The error flag is reset after the warn so it fires once per failure.
    assert laser_failed.error == 0


def test_estop_warn_branch_does_not_fire_when_all_off_succeed() -> None:
    """The control case: when both lasers report error=0 after off(), the
    warn branch must NOT fire — no spurious 'may still be on' warning when
    every off() succeeded cleanly. The method still emits its terminal
    'E-STOP actuated' status message, but no per-laser warning."""
    updateUi_estop_pressed = _load_method(
        "updateUi_estop_pressed(self) -> None"
    )

    laser1 = Mock()
    laser1.error = 0
    laser1.label = "Laser 1 (555 nm)"

    laser2 = Mock()
    laser2.error = 0
    laser2.label = "Laser 2 (640 nm)"

    standin = Mock()
    standin.estop_event = Mock()
    standin.lasers = [laser1, laser2]
    standin.sig_message = Mock()
    standin._hw = Mock()
    standin.label_estopStatus = Mock()
    standin.pushButton_estop = Mock()

    updateUi_estop_pressed(standin)

    # Both lasers driven off.
    laser1.off.assert_called_once()
    laser2.off.assert_called_once()
    # No per-laser warning emitted — every emit message is the terminal
    # "E-STOP actuated" status, none name a laser label or "STILL BE ON".
    emit_calls = [c.args[0] for c in standin.sig_message.emit.call_args_list]
    warn_msgs = [
        m for m in emit_calls
        if "STILL BE ON" in m or "off command failed" in m
    ]
    assert len(warn_msgs) == 0, (
        f"warn branch must not fire when all off() calls succeed; "
        f"got {warn_msgs} in {emit_calls}"
    )
