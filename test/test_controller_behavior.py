"""
Behavioral regression tests for Phase 01 controller methods that cannot be
exercised by importing Controller_MainWindow on the Mac dev box (PyQt5 is not
installed, so `from gui.controller import Controller_MainWindow` raises
ModuleNotFoundError).

Each test extracts the REAL method body from gui/controller.py and exec's it
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
       Lasers/IBeam instances, not hardcoded numbers (LSR-05)
"""

import datetime
import logging
import os
import re
import threading
from collections.abc import Callable
from typing import Any
from unittest.mock import Mock

_CONTROLLER_SRC = os.path.join(os.path.dirname(__file__), "..", "gui", "controller.py")


def _read_controller_source() -> str:
    with open(_CONTROLLER_SRC) as f:
        return f.read()


def _slice_method(src: str, method_sig: str) -> str:
    """Return the body of a method, from its `def <sig>:` line up to the
    next top-level def/@pyqtSlot decorator."""
    m = re.search(r"def " + re.escape(method_sig) + r":", src)
    assert m, f"{method_sig} is missing"
    body = src[m.start() :]
    end = re.search(r"\n    def |\n    @pyqtSlot", body[1:])
    if end:
        body = body[: end.start() + 1]
    return body


def _load_method(
    method_sig: str, extra_globals: dict[str, Any] | None = None
) -> Callable[..., Any]:
    """Extract a method body from gui/controller.py and return a callable
    that executes the real source. `extra_globals` seeds the exec namespace
    with module-level names the body references (datetime, logging, logger,
    ...). `logger` is the module-level logger gui/controller.py declares;
    seeding it here lets the migrated logger.* calls resolve when the body
    is exec'd in isolation."""
    src = _read_controller_source()
    body = _slice_method(src, method_sig)
    namespace = {
        "datetime": datetime,
        "logging": logging,
        "logger": logging.getLogger("test_controller_behavior"),
    }
    if extra_globals:
        namespace.update(extra_globals)
    exec(compile(body, _CONTROLLER_SRC, "exec"), namespace)
    func_name = method_sig.split("(")[0].strip()
    return namespace[func_name]


# --------------------------------------------------------------------------- #
# G1 — start_lasers surfaces a laser-1 DAQ write failure (LSR-01 / G-01-1)
# --------------------------------------------------------------------------- #


def test_start_lasers_surfaces_laser1_daq_error() -> None:
    """When Lasers.laser1_on() leaves self.lasers.error set, start_lasers
    must emit an operator message naming the cause and reset the flag — a
    failed laser-1 DAQ start is no longer a silent no-op (G-01-1)."""
    start_lasers = _load_method("start_lasers(self)")

    lasers = Mock()
    lasers.laser1_max_power = 5.0
    lasers.error = 1  # laser1_on() "failed" the DAQ write
    lasers.error_message = "daq write failed"

    standin = Mock()
    standin._auto_laser1 = True
    standin._auto_laser2 = False
    standin.laser1_power_pct = 50
    standin.lasers = lasers
    standin.sig_message = Mock()

    start_lasers(standin)

    # An operator message was emitted naming the failure.
    assert standin.sig_message.emit.called, (
        "start_lasers must emit sig_message when self.lasers.error is set "
        "after laser1_on() — a silent no-op is the G-01-1 regression."
    )
    msg = standin.sig_message.emit.call_args[0][0]
    assert "Laser write failed" in msg
    assert "daq write failed" in msg
    # The flag is reset so the warning fires once per failure.
    assert lasers.error == 0


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
    acquire_scan = _load_method("acquire_scan(self)")

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
    standin.sig_message = Mock()
    # acquire_scan reads self.ui.lineEdit_saveDescription.text() for metadata
    # before the timeout check; a Mock ui satisfies that without exercising Qt.
    standin.ui = Mock()

    acquire_scan(standin)

    # The defining assertion: copy_recorder_images must NOT be called.
    camera.copy_recorder_images.assert_not_called()
    # The operator was warned.
    assert standin.sig_message.emit.called
    msg = standin.sig_message.emit.call_args[0][0]
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
    acquire_scan = _load_method("acquire_scan(self)")

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
    standin.sig_message = Mock()
    standin.ui = Mock()

    acquire_scan(standin)

    # The recorder was never primed — the failure surfaced before it.
    camera.start_recorder.assert_not_called()
    # The operator saw the real DAQ cause.
    assert standin.sig_message.emit.called
    msg = standin.sig_message.emit.call_args[0][0]
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
    start_lasers = _load_method("start_lasers(self)")

    lasers = Mock()
    lasers.laser1_max_power = 5.0
    lasers.error = 0

    standin = Mock()
    standin.ui = _WidgetRaisingUI()
    standin._auto_laser1 = True
    standin._auto_laser2 = False
    standin.laser1_power_pct = 50
    standin.lasers = lasers
    standin.sig_message = Mock()

    # Must not raise — if it read the widget, _WidgetRaisingUI raises.
    start_lasers(standin)

    lasers.laser1_on.assert_called_once()


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
    preview_mode_worker = _load_method("preview_mode_worker(self)")

    estop_event = threading.Event()
    estop_event.set()  # E-stop actuated before the loop starts

    camera = Mock()

    standin = Mock()
    standin.estop_event = estop_event
    standin.preview_mode_started = True
    standin.camera = camera
    standin.ui = Mock()  # doubleSpinBox_cameraExposureTime.value() for setup
    standin.frame_viewer = Mock()
    standin.sig_message = Mock()
    standin.sig_preview_mode_finished = Mock()

    preview_mode_worker(standin)

    # No per-frame acquisition work ran — the estop poll broke first.
    camera.start_recorder.assert_not_called()
    camera.copy_recorder_images.assert_not_called()
    # The finished signal fired exactly once (the finally block).
    assert standin.sig_preview_mode_finished.emit.call_count == 1


# --------------------------------------------------------------------------- #
# G6 — updateUi_initial_hardware_state sets wavelength labels from the live
#      Lasers/IBeam instances (LSR-05)
# --------------------------------------------------------------------------- #


def test_wavelength_labels_set_from_live_instances() -> None:
    """updateUi_initial_hardware_state must set the wavelength labels from
    the live self.lasers.laser1_wavelength and self.ibeam.wavelength
    instances — not hardcoded numbers — so the operator sees the real
    configured wavelength (LSR-05)."""
    updateUi_initial_hardware_state = _load_method(
        "updateUi_initial_hardware_state(self)"
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

    lasers = Mock()
    lasers.laser1_wavelength = 555  # green DAQ laser

    ibeam = Mock()
    ibeam.wavelength = 640  # red iBeam

    standin = Mock()
    standin.ui = Mock()
    standin.siggen = siggen
    standin.camera = camera
    standin.lasers = lasers
    standin.ibeam = ibeam
    standin.laser1_power_pct = 0
    standin.laser2_power_pct = 0
    # updateUi_initial_hardware_state calls these two helpers at the end;
    # as auto-Mock callables they are no-ops here.
    standin.updateUi_camera_shutter_mode = Mock()
    standin.updateUi_units = Mock()

    updateUi_initial_hardware_state(standin)

    label_72_text = standin.ui.label_72.setText.call_args[0][0]
    label_73_text = standin.ui.label_73.setText.call_args[0][0]
    assert "555" in label_72_text, (
        "label_72 must show the live lasers.laser1_wavelength (555), not a "
        "hardcoded number."
    )
    assert "640" in label_73_text, (
        "label_73 must show the live ibeam.wavelength (640), not a hardcoded number."
    )
    # Toggle buttons are relabeled with the live wavelengths too.
    toggle1_text = standin.ui.pushButton_laserOneToggle.setText.call_args[0][0]
    toggle2_text = standin.ui.pushButton_laserTwoToggle.setText.call_args[0][0]
    assert "555" in toggle1_text
    assert "640" in toggle2_text
