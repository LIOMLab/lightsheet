"""Branch-coverage closure for ``lightsheet.gui.coordinators.acquisition_coordinator``
worker bodies.

The worker methods (preview/live/single/stack mode workers + acquire_scan)
are tested by constructing the real worker QObjects (PreviewWorker /
LiveWorker / SingleWorker / StackWorker from workers.py) against a mock
shell with all the attributes the workers read, and exercising the key
branches: normal path, E-stop early exit, siggen error, camera timeout,
motor ValueError, and saving-allowed vs not-allowed.

Behavior tests (AGENTS.md §5) — every assertion is on a runtime
postcondition (signal emit calls, HAL method calls, shell attribute writes),
never a static-source grep.
"""

from __future__ import annotations

from unittest.mock import Mock

import numpy as np
import pytest

pytest.importorskip("PySide6")

from lightsheet.gui.coordinators.acquisition_coordinator import AcquisitionCoordinator
from lightsheet.gui.workers import LiveWorker, PreviewWorker, SingleWorker, StackWorker
from lightsheet.hal import DeviceBundle, MockCamera, MockETLs, MockLaser, MockMotors, MockSigGen


def _make_bundle() -> DeviceBundle:
    camera = MockCamera(verbose=False)
    siggen = MockSigGen(camera)
    motors = MockMotors()
    lasers = (
        MockLaser(wavelength=555, max_power_mw=300.0, label="L1"),
        MockLaser(wavelength=647, max_power_mw=150.0, label="L2"),
    )
    etls = MockETLs()
    return DeviceBundle(camera=camera, siggen=siggen, motors=motors, etls=etls, lasers=lasers)


class _WorkerShell:
    """Shell stand-in with all attributes the worker bodies read/write."""

    def __init__(self) -> None:
        self.ui = Mock()
        # Hybrid ownership: PreviewWorker reads the camera exposure spinbox
        # via shell.acquisition_panel.ui.<name> (panel-internal widget, no
        # longer on the flat shell.ui namespace).
        self.acquisition_panel = Mock()
        self.acquisition_panel.ui.doubleSpinBox_cameraExposureTime.value.return_value = 100
        self.ui.lineEdit_saveDescription.text.return_value = "test sample"
        self.ui.radioButton_saveStitchBlend.isChecked.return_value = False
        self.ui.radioButton_saveAllCrop.isChecked.return_value = False
        self.ui.radioButton_saveAllFull.isChecked.return_value = False

        # Mode started flags — set to False so workers exit immediately.
        self.preview_mode_started = False
        self.live_mode_started = False
        self.single_mode_started = False
        self.stack_mode_started = False

        # E-stop event — Mock with is_set() returning False by default.
        self.estop_event = Mock()
        self.estop_event.is_set.return_value = False

        # Signals
        self.sig_message = Mock()
        self.sig_preview_mode_finished = Mock()
        self.sig_live_mode_finished = Mock()
        self.sig_single_mode_finished = Mock()
        self.sig_stack_mode_finished = Mock()
        self.sig_progress_update = Mock()
        self.sig_beep = Mock()
        self.sig_refresh_position_horizontal = Mock()
        self.sig_refresh_position_vertical = Mock()
        self.sig_refresh_position_camera = Mock()

        # Frame saver
        self._fs = Mock()

        # Position / metadata attributes
        self.current_horizontal_position_text = "0.0"
        self.current_vertical_position_text = "0.0"
        self.current_camera_position_text = "0.0"
        self.image_hor_pos_text = ""
        self.image_ver_pos_text = ""
        self.image_cam_pos_text = ""

        # Buffer / reconstructed frame
        self.buffer = None
        self.reconstructed_frame = None

        # Metadata dicts
        self.buffer_metadata_general = {}
        self.buffer_metadata_waveforms = {}
        self.buffer_metadata_motors = {}
        self.buffer_metadata_lasers = {}
        self.buffer_metadata_camera = {}

        # Saving attributes
        self.saving_allowed = False
        self.number_of_planes = 1
        self.save_filename = "test.hdf5"
        self.save_filepath = "test.hdf5"
        self.save_description = "test sample"
        self.stack_starting_plane = 0.0
        self.stack_step = 10.0

        # updateUi_position_horizontal is called from stack worker
        self.updateUi_position_horizontal = Mock()


def _make_acq() -> tuple[AcquisitionCoordinator, _WorkerShell, Mock]:
    bundle = _make_bundle()
    shell = _WorkerShell()
    hw = Mock()
    acq = AcquisitionCoordinator(bundle, hw, shell)
    return acq, shell, hw


def _make_preview_worker(qtbot) -> tuple[PreviewWorker, _WorkerShell, Mock]:
    """Construct a PreviewWorker (QObject) against the mock shell + hw.
    Requires qtbot for the QApplication."""
    bundle = _make_bundle()
    shell = _WorkerShell()
    hw = Mock()
    worker = PreviewWorker(bundle, hw, shell)
    return worker, shell, hw


def _make_live_worker(qtbot) -> tuple[LiveWorker, _WorkerShell, Mock]:
    """Construct a LiveWorker (QObject) against the mock shell + hw.
    Requires qtbot for the QApplication."""
    bundle = _make_bundle()
    shell = _WorkerShell()
    hw = Mock()
    worker = LiveWorker(bundle, hw, shell)
    return worker, shell, hw


def _make_single_worker(qtbot) -> tuple[SingleWorker, _WorkerShell, Mock]:
    """Construct a SingleWorker (QObject) against the mock shell + hw.
    Requires qtbot for the QApplication."""
    bundle = _make_bundle()
    shell = _WorkerShell()
    hw = Mock()
    worker = SingleWorker(
        bundle, hw, shell, save_description="test sample", save_stitch_blend=False
    )
    return worker, shell, hw


def _make_stack_worker(qtbot) -> tuple[StackWorker, _WorkerShell, Mock]:
    """Construct a StackWorker (QObject) against the mock shell + hw.
    Requires qtbot for the QApplication."""
    bundle = _make_bundle()
    shell = _WorkerShell()
    hw = Mock()
    worker = StackWorker(
        bundle,
        hw,
        shell,
        save_description="test sample",
        save_stitch_blend=False,
        save_all_crop=False,
        save_all_full=False,
    )
    return worker, shell, hw


# -- PreviewWorker.run ------------------------------------------------------


def test_preview_worker_normal_exit(qtbot) -> None:
    """PreviewWorker.run with preview_mode_started=False exits the loop
    immediately, calls stop_lasers + disarm, emits finished signal."""
    worker, shell, hw = _make_preview_worker(qtbot)
    shell.preview_mode_started = False  # loop doesn't execute
    finished_emits: list[None] = []
    worker.finished.connect(lambda: finished_emits.append(None))
    worker.run()
    # stop_lasers was called
    hw.stop_lasers.assert_called_once()
    # finished signal emitted exactly once
    assert len(finished_emits) == 1


def test_preview_worker_estop_break(qtbot) -> None:
    """PreviewWorker.run with estop_event set breaks out of the loop."""
    worker, shell, hw = _make_preview_worker(qtbot)
    shell.preview_mode_started = True
    shell.estop_event.is_set.return_value = True  # E-stop on first iteration
    finished_emits: list[None] = []
    worker.finished.connect(lambda: finished_emits.append(None))
    worker.run()
    hw.stop_lasers.assert_called_once()
    assert len(finished_emits) == 1


def test_preview_worker_exception_emits_message(qtbot) -> None:
    """PreviewWorker.run catches exceptions and emits sig_message."""
    worker, shell, hw = _make_preview_worker(qtbot)
    # Make camera.arm() raise to trigger the except block.
    worker.camera.arm = Mock(side_effect=RuntimeError("camera error"))
    finished_emits: list[None] = []
    worker.finished.connect(lambda: finished_emits.append(None))
    worker.run()
    shell.sig_message.emit.assert_called_once()
    assert "Preview acquisition failed" in shell.sig_message.emit.call_args[0][0]
    assert len(finished_emits) == 1


# -- LiveWorker.run ---------------------------------------------------------


def test_live_mode_worker_normal_exit(qtbot) -> None:
    """LiveWorker.run with live_mode_started=False exits immediately."""
    worker, shell, hw = _make_live_worker(qtbot)
    shell.live_mode_started = False
    finished_emits: list[None] = []
    worker.finished.connect(lambda: finished_emits.append(None))
    worker.run()
    hw.stop_lasers.assert_called_once()
    assert len(finished_emits) == 1


def test_live_mode_worker_estop_break(qtbot) -> None:
    """LiveWorker.run with estop_event set breaks out of the loop."""
    worker, shell, hw = _make_live_worker(qtbot)
    shell.live_mode_started = True
    shell.estop_event.is_set.return_value = True
    finished_emits: list[None] = []
    worker.finished.connect(lambda: finished_emits.append(None))
    worker.run()
    hw.stop_lasers.assert_called_once()
    assert len(finished_emits) == 1


def test_live_mode_worker_acquire_scan_does_not_skip_cleanup(qtbot) -> None:
    """LiveWorker.run must call stop_lasers even when acquire_scan() runs.

    Regression guard: acquire_scan() reads self._save_description and
    self._save_stitch_blend. If LiveWorker.__init__ does not set them,
    acquire_scan() raises AttributeError inside the try block and the
    stop_lasers() / camera.disarm() cleanup is skipped — leaving Class IIIB
    lasers energized. The loop must execute one acquire_scan() iteration and
    still reach stop_lasers().
    """
    worker, shell, hw = _make_live_worker(qtbot)
    shell.live_mode_started = True
    shell.estop_event.is_set.return_value = False
    # Flip live_mode_started to False after the first acquire_scan() so the
    # loop runs exactly one iteration then exits normally.
    original_acquire = worker.acquire_scan

    def _acquire_then_stop() -> None:
        original_acquire()
        shell.live_mode_started = False

    worker.acquire_scan = _acquire_then_stop  # type: ignore[method-assign]
    # Spy on camera.disarm (MockCamera is a real instance, not a Mock).
    disarm_spy = Mock(wraps=worker.camera.disarm)
    worker.camera.disarm = disarm_spy  # type: ignore[method-assign]
    finished_emits: list[None] = []
    worker.finished.connect(lambda: finished_emits.append(None))
    worker.run()
    # The safety-critical assertion: cleanup ran despite acquire_scan() executing.
    hw.stop_lasers.assert_called_once()
    disarm_spy.assert_called_once()
    assert len(finished_emits) == 1



# -- SingleWorker.run -------------------------------------------------------


def test_single_mode_worker_estop_early_return(qtbot) -> None:
    """SingleWorker.run with estop_event set returns early after
    ETL standby + stop_lasers + disarm (line 251-257)."""
    worker, shell, hw = _make_single_worker(qtbot)
    shell.estop_event.is_set.return_value = True
    finished_emits: list[None] = []
    worker.finished.connect(lambda: finished_emits.append(None))
    worker.run()
    hw.stop_lasers.assert_called_once()
    assert len(finished_emits) == 1


def test_single_mode_worker_normal_path(qtbot) -> None:
    """SingleWorker.run normal path: arm_scan, start_lasers, compute_scan,
    acquire_scan, ETL standby, stop_lasers, disarm, emit finished."""
    worker, shell, hw = _make_single_worker(qtbot)
    # Mock acquire_scan to avoid running the full scan logic.
    worker.acquire_scan = Mock()
    finished_emits: list[None] = []
    worker.finished.connect(lambda: finished_emits.append(None))
    worker.run()
    hw.start_lasers.assert_called_once()
    hw.stop_lasers.assert_called_once()
    assert len(finished_emits) == 1


def test_single_mode_worker_exception_emits_message(qtbot) -> None:
    """SingleWorker.run catches exceptions and emits sig_message."""
    worker, shell, hw = _make_single_worker(qtbot)
    worker.camera.arm_scan = Mock(side_effect=RuntimeError("arm failed"))
    finished_emits: list[None] = []
    worker.finished.connect(lambda: finished_emits.append(None))
    worker.run()
    shell.sig_message.emit.assert_called_once()
    assert "Single image acquisition failed" in shell.sig_message.emit.call_args[0][0]
    assert len(finished_emits) == 1


# -- acquire_scan (via SingleWorker / _AcquireScanMixin) --------------------


def test_acquire_scan_siggen_error_aborts(qtbot) -> None:
    """acquire_scan with siggen.error set after create_scanner emits
    message + returns early (lines 337-344)."""
    worker, shell, hw = _make_single_worker(qtbot)
    # Make create_scanner set error=1.
    def _fake_create_scanner():
        worker.siggen.error = 1
        worker.siggen.error_message = "DAQ error"
    worker.siggen.create_scanner = _fake_create_scanner
    worker.acquire_scan()
    shell.sig_message.emit.assert_called_once()
    assert "Scan task creation failed" in shell.sig_message.emit.call_args[0][0]


def test_acquire_scan_camera_timeout_aborts(qtbot) -> None:
    """acquire_scan with camera.recorder_timeout_status set after monitor
    emits timeout message + returns early (lines 363-384)."""
    worker, shell, hw = _make_single_worker(qtbot)
    # Make monitor_recorder set recorder_timeout_status.
    def _fake_monitor(n):
        worker.camera.recorder_timeout_status = True
    worker.camera.monitor_recorder = _fake_monitor
    worker.acquire_scan()
    shell.sig_message.emit.assert_called_once()
    assert "Camera timeout" in shell.sig_message.emit.call_args[0][0]


def test_acquire_scan_normal_path_no_stitch(qtbot) -> None:
    """acquire_scan normal path with stitch blend unchecked -> reconstruct_frame
    (line 401)."""
    worker, shell, hw = _make_single_worker(qtbot)
    worker.siggen.waveform_cycles = 1
    # Mock camera copy_recorder_images to return a simple array.
    worker.camera.copy_recorder_images = Mock(return_value=np.zeros((1, 100, 100)))
    worker.camera.recorder_timeout_status = False
    shell._fs.reconstruct_frame.return_value = np.zeros((100, 100))
    worker.acquire_scan()
    shell._fs.reconstruct_frame.assert_called_once()
    shell._fs.enqueue_frame.assert_called_once()


def test_acquire_scan_normal_path_with_stitch(qtbot) -> None:
    """acquire_scan normal path with stitch blend checked -> reconstruct_frame_linear_blend
    (lines 396-399)."""
    worker, shell, hw = _make_single_worker(qtbot)
    worker._save_stitch_blend = True
    worker.siggen.waveform_cycles = 1
    worker.camera.copy_recorder_images = Mock(return_value=np.zeros((1, 100, 100)))
    worker.camera.recorder_timeout_status = False
    shell._fs.reconstruct_frame_linear_blend.return_value = np.zeros((100, 100))
    worker.acquire_scan()
    shell._fs.reconstruct_frame_linear_blend.assert_called_once()
    shell._fs.enqueue_frame.assert_called_once()


# -- StackWorker.run --------------------------------------------------------


def test_stack_mode_worker_estop_before_start(qtbot) -> None:
    """StackWorker.run with estop_event set before start -> no lasers
    started, loop breaks immediately."""
    worker, shell, hw = _make_stack_worker(qtbot)
    shell.estop_event.is_set.return_value = True
    finished_emits: list[None] = []
    worker.finished.connect(lambda: finished_emits.append(None))
    worker.run()
    # start_lasers NOT called (estop was set before the guard).
    hw.start_lasers.assert_not_called()
    hw.stop_lasers.assert_called_once()
    assert len(finished_emits) == 1


def test_stack_mode_worker_normal_path_no_saving(qtbot) -> None:
    """StackWorker.run normal path with saving_allowed=False, 1 plane,
    no E-stop -> acquires 1 plane, emits progress, stop_lasers, disarm."""
    worker, shell, hw = _make_stack_worker(qtbot)
    shell.stack_mode_started = True
    shell.saving_allowed = False
    shell.number_of_planes = 1
    worker.acquire_scan = Mock()
    worker.camera.recorder_timeout_status = False
    worker.siggen.error = 0
    finished_emits: list[None] = []
    worker.finished.connect(lambda: finished_emits.append(None))
    worker.run()
    hw.start_lasers.assert_called_once()
    hw.stop_lasers.assert_called_once()
    assert len(finished_emits) == 1


def test_stack_mode_worker_saving_crop(qtbot) -> None:
    """StackWorker.run with saving_allowed + save_all_crop ->
    set_files with 'ETLscan' + enqueue_buffer with cropped."""
    worker, shell, hw = _make_stack_worker(qtbot)
    shell.stack_mode_started = True
    shell.saving_allowed = True
    shell.number_of_planes = 1
    worker._save_all_crop = True
    worker.acquire_scan = Mock()
    worker.camera.recorder_timeout_status = False
    worker.siggen.error = 0
    shell._fs.crop_buffer.return_value = np.zeros((100, 100))
    finished_emits: list[None] = []
    worker.finished.connect(lambda: finished_emits.append(None))
    worker.run()
    shell._fs.set_files.assert_called_once_with(1, "test.hdf5", "stack", 1, "ETLscan")
    shell._fs.crop_buffer.assert_called_once()


def test_stack_mode_worker_saving_full(qtbot) -> None:
    """StackWorker.run with saving_allowed + save_all_full ->
    set_files with 'FullETLscan' + enqueue_buffer with full."""
    worker, shell, hw = _make_stack_worker(qtbot)
    shell.stack_mode_started = True
    shell.saving_allowed = True
    shell.number_of_planes = 1
    worker._save_all_full = True
    worker.acquire_scan = Mock()
    worker.camera.recorder_timeout_status = False
    worker.siggen.error = 0
    finished_emits: list[None] = []
    worker.finished.connect(lambda: finished_emits.append(None))
    worker.run()
    shell._fs.set_files.assert_called_once_with(1, "test.hdf5", "stack", 1, "FullETLscan")


def test_stack_mode_worker_saving_reconstructed(qtbot) -> None:
    """StackWorker.run with saving_allowed + neither crop nor full ->
    set_files with 'reconstructed_frame' + enqueue_buffer with reconstructed."""
    worker, shell, hw = _make_stack_worker(qtbot)
    shell.stack_mode_started = True
    shell.saving_allowed = True
    shell.number_of_planes = 1
    worker.acquire_scan = Mock()
    worker.camera.recorder_timeout_status = False
    worker.siggen.error = 0
    finished_emits: list[None] = []
    worker.finished.connect(lambda: finished_emits.append(None))
    worker.run()
    shell._fs.set_files.assert_called_once_with(1, "test.hdf5", "stack", 1, "reconstructed_frame")


def test_stack_mode_worker_motor_value_error_aborts(qtbot) -> None:
    """StackWorker.run where motor.move_absolute_position raises ValueError
    -> emits message + beep + break."""
    worker, shell, hw = _make_stack_worker(qtbot)
    shell.stack_mode_started = True
    shell.saving_allowed = False
    shell.number_of_planes = 1
    worker.acquire_scan = Mock()
    # Make the motor raise ValueError on move_absolute_position.
    worker.motors.horizontal.move_absolute_position = Mock(side_effect=ValueError("over limit"))
    finished_emits: list[None] = []
    worker.finished.connect(lambda: finished_emits.append(None))
    worker.run()
    shell.sig_message.emit.assert_any_call(
        "Move rejected — horizontal would exceed travel limits. Stack acquisition aborted."
    )
    shell.sig_beep.emit.assert_called_once()


def test_stack_mode_worker_camera_timeout_breaks(qtbot) -> None:
    """StackWorker.run where camera times out on a plane -> break."""
    worker, shell, hw = _make_stack_worker(qtbot)
    shell.stack_mode_started = True
    shell.saving_allowed = False
    shell.number_of_planes = 1
    worker.acquire_scan = Mock()
    worker.camera.recorder_timeout_status = True  # timeout after acquire_scan
    worker.siggen.error = 0
    finished_emits: list[None] = []
    worker.finished.connect(lambda: finished_emits.append(None))
    worker.run()
    # Should have called acquire_scan once then broken.
    worker.acquire_scan.assert_called_once()


def test_stack_mode_worker_siggen_error_breaks(qtbot) -> None:
    """StackWorker.run where siggen.error is set after acquire_scan -> break."""
    worker, shell, hw = _make_stack_worker(qtbot)
    shell.stack_mode_started = True
    shell.saving_allowed = False
    shell.number_of_planes = 2
    worker.acquire_scan = Mock()
    worker.camera.recorder_timeout_status = False
    worker.siggen.error = 1  # error set
    finished_emits: list[None] = []
    worker.finished.connect(lambda: finished_emits.append(None))
    worker.run()
    # Only 1 plane attempted (break after first), not 2.
    worker.acquire_scan.assert_called_once()


def test_stack_mode_worker_stop_interrupts(qtbot) -> None:
    """StackWorker.run where stack_mode_started is False at loop top ->
    emits 'Interrupted' + break."""
    worker, shell, hw = _make_stack_worker(qtbot)
    shell.stack_mode_started = True  # start True so lasers start
    shell.saving_allowed = False
    shell.number_of_planes = 1
    # Set stack_mode_started to False before the loop body runs.
    # We'll use a side_effect on sig_progress_update to flip it.
    def _flip(*a):
        shell.stack_mode_started = False
    shell.sig_progress_update.side_effect = _flip
    worker.acquire_scan = Mock()
    finished_emits: list[None] = []
    worker.finished.connect(lambda: finished_emits.append(None))
    worker.run()
    # The loop should have been interrupted — the finished signal was emitted.
    assert len(finished_emits) == 1


def test_stack_mode_worker_exception_emits_message(qtbot) -> None:
    """StackWorker.run catches exceptions and emits sig_message."""
    worker, shell, hw = _make_stack_worker(qtbot)
    worker.camera.arm_scan = Mock(side_effect=RuntimeError("arm failed"))
    finished_emits: list[None] = []
    worker.finished.connect(lambda: finished_emits.append(None))
    worker.run()
    shell.sig_message.emit.assert_called_once()
    assert "Stack acquisition failed" in shell.sig_message.emit.call_args[0][0]
    assert len(finished_emits) == 1
