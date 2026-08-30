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

from unittest.mock import Mock, patch

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
        # Multi-channel per-channel frames dict (MCA-01/D-07). Populated
        # by SingleWorker.run multi-channel branch keyed by laser
        # wavelength; reconstructed_frame stays as an alias to the last
        # channel's frame for back-compat.
        self.reconstructed_frames: dict[int, np.ndarray] = {}

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

        # Auto-laser flags pre-sampled on the GUI thread by
        # _cache_auto_laser_flags() before the worker is spawned. The D-04
        # continuous-mode guard in PreviewWorker/LiveWorker reads these to
        # decide whether to suppress L2 for the start_lasers call. Defaults
        # to False/False so the existing preview/live tests (which use a
        # Mock hw and never reach start_lasers' flag-reading branch) are
        # unaffected.
        self._auto_laser1 = False
        self._auto_laser2 = False
        # Power percentages read by HardwareManager.start_lasers when the
        # D-04 tests use a real HardwareManager.
        self.laser1_power_pct = 50.0
        self.laser2_power_pct = 50.0
        # Signals read by HardwareManager._poll_laser_status /
        # _refresh_laser_readback when the D-04 tests use a real
        # HardwareManager.
        self.sig_laser_status = Mock()
        self.sig_laser_readback = Mock()

        # Lasers tuple — SingleWorker.run multi-channel branch reads
        # self.lasers[0/1].wavelength to key reconstructed_frames.
        bundle = _make_bundle()
        self.lasers = bundle.lasers

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


def _make_single_worker_multi(
    qtbot, multi_channel: bool = True
) -> tuple[SingleWorker, _WorkerShell, Mock]:
    """Construct a SingleWorker with the multi_channel constructor arg set.
    The mock shell's reconstructed_frames dict is initialized so the
    multi-channel run can store both channel frames."""
    bundle = _make_bundle()
    shell = _WorkerShell()
    shell.reconstructed_frames = {}
    hw = Mock()
    worker = SingleWorker(
        bundle,
        hw,
        shell,
        save_description="test sample",
        save_stitch_blend=False,
        multi_channel=multi_channel,
    )
    return worker, shell, hw


def _make_stack_worker(
    qtbot, multi_channel: bool = False
) -> tuple[StackWorker, _WorkerShell, Mock]:
    """Construct a StackWorker (QObject) against the mock shell + hw.
    Requires qtbot for the QApplication. The ``multi_channel`` arg is the
    final StackWorker constructor arg pre-sampled on the GUI thread in
    _spawn_stack_worker as (_auto_laser1 and _auto_laser2)."""
    bundle = _make_bundle()
    shell = _WorkerShell()
    shell.reconstructed_frames = {}
    hw = Mock()
    worker = StackWorker(
        bundle,
        hw,
        shell,
        save_description="test sample",
        save_stitch_blend=False,
        save_all_crop=False,
        save_all_full=False,
        multi_channel=multi_channel,
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
    shell._fs.set_files.assert_called_once_with(1, "test.hdf5", "stack", 1, "ETLscan", wavelengths=[555])
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
    shell._fs.set_files.assert_called_once_with(1, "test.hdf5", "stack", 1, "FullETLscan", wavelengths=[555])


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
    shell._fs.set_files.assert_called_once_with(1, "test.hdf5", "stack", 1, "reconstructed_frame", wavelengths=[555])


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


# -- SingleWorker multi-channel per-channel cycle (MCA-01) -------------------


def test_single_worker_multi_channel_both_frames(qtbot) -> None:
    """SingleWorker.run with multi_channel=True executes
    select_laser(0) -> acquire_scan -> capture frame1 -> select_laser(1)
    -> acquire_scan -> capture frame2, storing both in
    self._shell.reconstructed_frames dict keyed by laser wavelength
    (555 and 647 from MockLaser), with reconstructed_frame kept as an
    alias equal to the last channel's frame."""
    worker, shell, hw = _make_single_worker_multi(qtbot, multi_channel=True)
    # Make acquire_scan populate reconstructed_frame with a distinct
    # array per channel so we can verify both are captured.
    call_count = {"n": 0}

    def _fake_acquire_scan():
        call_count["n"] += 1
        # Each call produces a distinct frame.
        shell.reconstructed_frame = np.full((4, 4), call_count["n"], dtype=np.uint16)

    worker.acquire_scan = _fake_acquire_scan  # type: ignore[method-assign]
    worker.camera.recorder_timeout_status = False
    worker.siggen.error = 0
    finished_emits: list[None] = []
    worker.finished.connect(lambda: finished_emits.append(None))
    worker.run()

    # select_laser(0) then select_laser(1) called in order.
    assert hw.select_laser.call_count == 2
    assert hw.select_laser.call_args_list[0].args == (0,)
    assert hw.select_laser.call_args_list[1].args == (1,)
    # acquire_scan called twice (once per channel).
    assert call_count["n"] == 2
    # reconstructed_frames dict has 2 entries keyed by wavelength.
    assert isinstance(shell.reconstructed_frames, dict)
    assert len(shell.reconstructed_frames) == 2
    assert 555 in shell.reconstructed_frames
    assert 647 in shell.reconstructed_frames
    # frame1 (channel 0, 555 nm) == array of 1s; frame2 (channel 1, 647 nm) == array of 2s.
    assert (shell.reconstructed_frames[555] == 1).all()
    assert (shell.reconstructed_frames[647] == 2).all()
    # reconstructed_frame is an alias equal to the last channel's frame.
    assert (shell.reconstructed_frame == 2).all()
    # stop_lasers called at the end (safety — both off regardless).
    hw.stop_lasers.assert_called_once()
    # start_lasers NOT called in multi-channel branch (select_laser per channel instead).
    hw.start_lasers.assert_not_called()
    assert len(finished_emits) == 1


def test_single_worker_single_channel_unchanged(qtbot) -> None:
    """SingleWorker.run with multi_channel=False is byte-for-byte the
    existing single-channel path: select_laser NEVER called,
    start_lasers/stop_lasers called (existing path), acquire_scan called
    once, reconstructed_frame set once (back-compat)."""
    worker, shell, hw = _make_single_worker_multi(qtbot, multi_channel=False)
    acquire_count = {"n": 0}

    def _fake_acquire_scan():
        acquire_count["n"] += 1
        shell.reconstructed_frame = np.zeros((4, 4), dtype=np.uint16)

    worker.acquire_scan = _fake_acquire_scan  # type: ignore[method-assign]
    worker.camera.recorder_timeout_status = False
    worker.siggen.error = 0
    finished_emits: list[None] = []
    worker.finished.connect(lambda: finished_emits.append(None))
    worker.run()

    hw.select_laser.assert_not_called()
    hw.start_lasers.assert_called_once()
    hw.stop_lasers.assert_called_once()
    assert acquire_count["n"] == 1
    # reconstructed_frames dict stays empty (single-channel path does not populate it).
    assert shell.reconstructed_frames == {}
    assert len(finished_emits) == 1


def test_single_worker_multi_channel_estop_after_first_channel(qtbot) -> None:
    """SingleWorker.run multi-channel: if estop_event is set after the
    first channel's acquire_scan, the second channel's acquire_scan is
    skipped and the run exits cleanly via the finally block. Both
    lasers are driven off by stop_lasers at the end. select_laser(1)
    may still be called (it internally checks estop and does not
    energize), but acquire_scan must NOT run for the second channel."""
    worker, shell, hw = _make_single_worker_multi(qtbot, multi_channel=True)
    shell.estop_event.is_set.return_value = False
    acquire_count = {"n": 0}

    def _fake_acquire_scan():
        acquire_count["n"] += 1
        shell.reconstructed_frame = np.zeros((4, 4), dtype=np.uint16)
        # Set estop after the first channel's acquire_scan so the second
        # channel's acquire_scan is skipped.
        shell.estop_event.is_set.return_value = True

    worker.acquire_scan = _fake_acquire_scan  # type: ignore[method-assign]
    worker.camera.recorder_timeout_status = False
    worker.siggen.error = 0
    finished_emits: list[None] = []
    worker.finished.connect(lambda: finished_emits.append(None))
    worker.run()

    # acquire_scan called only once — second channel skipped after estop.
    assert acquire_count["n"] == 1
    # stop_lasers called at the end (safety — both off regardless).
    hw.stop_lasers.assert_called_once()
    assert len(finished_emits) == 1


# -- FrameSaver.enqueue_buffer tagged-tuple acceptance (D-06) ----------------


def test_enqueue_buffer_accepts_tagged_tuple(qtbot, request) -> None:
    """FrameSaver.enqueue_buffer accepts a (channel_idx, frame) tuple in
    addition to a bare np.ndarray; bare-ndarray calls preserve the
    existing single-channel behavior unchanged. This plan only makes
    enqueue_buffer accept the tagged form without raising — the
    single-consumer workers branch on the tag in a later plan."""
    from _helpers.controller_fixture import make_controller

    ctrl, _bundle = make_controller(qtbot, request)
    fs = ctrl._fs.frame_saver
    # Tagged tuple — must not raise.
    tagged = (0, np.zeros((4, 4), dtype=np.uint16))
    fs.enqueue_buffer(tagged)
    # Bare ndarray — back-compat, must not raise.
    fs.enqueue_buffer(np.zeros((4, 4), dtype=np.uint16))


# -- updateUi_single_mode_button multi_channel pre-sampling (AGENTS.md §11) --


def test_single_mode_button_presamples_multi_channel(qtbot, request) -> None:
    """updateUi_single_mode_button with both auto-laser checkboxes
    checked passes multi_channel=True to SingleWorker; with one
    unchecked passes False. Verified by spying on the SingleWorker
    constructor. Pre-sampling happens on the GUI thread after
    _cache_auto_laser_flags() — the worker never reads the checkboxes
    (AGENTS.md §11)."""
    from _helpers.controller_fixture import make_controller
    from lightsheet.gui import panels as panels_module

    # --- Both checked -> multi_channel=True ---
    ctrl, _bundle = make_controller(qtbot, request)
    ctrl._single_thread = None  # attribute exists only after first click
    ctrl._single_worker = None
    ctrl.laser_panel.ui.checkBox_laserOneAutomatic.setChecked(True)
    ctrl.laser_panel.ui.checkBox_laserTwoAutomatic.setChecked(True)
    ctrl.save_panel.ui.lineEdit_saveDescription.setText("test")

    captured: dict[str, object] = {}

    def _capture_worker(*args, **kwargs):
        # The multi_channel kwarg may be positional (last arg) or keyword.
        if "multi_channel" in kwargs:
            captured["multi_channel"] = kwargs["multi_channel"]
        else:
            # Positional: signature is (bundle, hw, shell, save_description,
            # save_stitch_blend, multi_channel).
            captured["multi_channel"] = args[-1]
        # Return a Mock-like object so moveToThread/connect/start are no-ops.
        worker_mock = Mock()
        worker_mock.finished = Mock()
        worker_mock.moveToThread = Mock()
        worker_mock.deleteLater = Mock()
        return worker_mock

    fake_thread = Mock()

    with (
        patch.object(panels_module.acquisition_panel, "SingleWorker", side_effect=_capture_worker),
        patch.object(panels_module.acquisition_panel, "QThread", return_value=fake_thread),
    ):
        ctrl.acquisition_panel.updateUi_single_mode_button()

    assert captured.get("multi_channel") is True, (
        "Both auto-laser checkboxes checked -> multi_channel=True must be "
        "passed to SingleWorker"
    )

    # Reset for the one-unchecked case.
    ctrl.single_mode_started = False
    ctrl._single_thread = None
    ctrl._single_worker = None
    ctrl.laser_panel.ui.checkBox_laserTwoAutomatic.setChecked(False)
    captured.clear()
    fake_thread2 = Mock()

    with (
        patch.object(panels_module.acquisition_panel, "SingleWorker", side_effect=_capture_worker),
        patch.object(panels_module.acquisition_panel, "QThread", return_value=fake_thread2),
    ):
        ctrl.acquisition_panel.updateUi_single_mode_button()

    assert captured.get("multi_channel") is False, (
        "Only one auto-laser checkbox checked -> multi_channel=False must be "
        "passed to SingleWorker"
    )


# -- StackWorker multi-channel per-plane cycle (MCA-01 stack) ---------------


def test_stack_worker_multi_channel_per_plane_cycle(qtbot) -> None:
    """StackWorker.run with multi_channel=True and number_of_planes=2 runs
    the per-plane sequential cycle: for each plane, move motor ->
    select_laser(0) -> acquire_scan -> capture frame1 -> select_laser(1)
    -> acquire_scan -> capture frame2 -> enqueue (0, frame1) and
    (1, frame2). start_lasers is NOT called at the top in multi-channel
    mode (it would energize both lasers simultaneously, violating the
    one-laser-energized invariant). select_laser is called twice per
    plane (once per channel), acquire_scan twice per plane, and
    enqueue_buffer receives 2 tagged tuples per plane (4 total for 2
    planes). stop_lasers is called at the end (safety — both off
    regardless of the last select_laser state)."""
    worker, shell, hw = _make_stack_worker(qtbot, multi_channel=True)
    shell.stack_mode_started = True
    shell.saving_allowed = True
    shell.number_of_planes = 2
    # Distinct frames per acquire_scan so we can verify both channels captured.
    call_count = {"n": 0}

    def _fake_acquire_scan():
        call_count["n"] += 1
        shell.reconstructed_frame = np.full(
            (4, 4), call_count["n"], dtype=np.uint16
        )

    worker.acquire_scan = _fake_acquire_scan  # type: ignore[method-assign]
    worker.camera.recorder_timeout_status = False
    worker.siggen.error = 0
    finished_emits: list[None] = []
    worker.finished.connect(lambda: finished_emits.append(None))
    worker.run()

    # start_lasers MUST NOT be called in multi-channel mode.
    hw.start_lasers.assert_not_called()
    # select_laser called twice per plane (channel 0 then channel 1) -> 4 total.
    assert hw.select_laser.call_count == 4
    # The call order alternates 0, 1, 0, 1 across the two planes.
    select_args = [c.args for c in hw.select_laser.call_args_list]
    assert select_args == [(0,), (1,), (0,), (1,)]
    # acquire_scan called twice per plane -> 4 total.
    assert call_count["n"] == 4
    # enqueue_buffer called with (channel_idx, frame) tagged tuples,
    # 2 per plane -> 4 total.
    assert shell._fs.enqueue_buffer.call_count == 4
    enqueued_args = [c.args[0] for c in shell._fs.enqueue_buffer.call_args_list]
    # Each enqueued item is a (channel_idx, ndarray) tuple.
    for item in enqueued_args:
        assert isinstance(item, tuple)
        assert len(item) == 2
        assert item[0] in (0, 1)
        assert isinstance(item[1], np.ndarray)
    # Channel indices alternate 0, 1, 0, 1 across the two planes.
    assert [item[0] for item in enqueued_args] == [0, 1, 0, 1]
    # stop_lasers called at the end (safety — both off regardless).
    hw.stop_lasers.assert_called_once()
    assert len(finished_emits) == 1


def test_stack_worker_single_channel_unchanged(qtbot) -> None:
    """StackWorker.run with multi_channel=False is byte-for-byte the
    existing single-channel path: start_lasers called once at the top,
    select_laser NEVER called, acquire_scan called once per plane,
    enqueue_buffer called with a bare ndarray once per plane (back-compat
    — no tagged tuple)."""
    worker, shell, hw = _make_stack_worker(qtbot, multi_channel=False)
    shell.stack_mode_started = True
    shell.saving_allowed = True
    shell.number_of_planes = 2
    acquire_count = {"n": 0}

    def _fake_acquire_scan():
        acquire_count["n"] += 1
        shell.reconstructed_frame = np.zeros((4, 4), dtype=np.uint16)

    worker.acquire_scan = _fake_acquire_scan  # type: ignore[method-assign]
    worker.camera.recorder_timeout_status = False
    worker.siggen.error = 0
    finished_emits: list[None] = []
    worker.finished.connect(lambda: finished_emits.append(None))
    worker.run()

    # Single-channel path: start_lasers called once at top.
    hw.start_lasers.assert_called_once()
    # select_laser NEVER called (single-channel back-compat).
    hw.select_laser.assert_not_called()
    # acquire_scan called once per plane -> 2 total.
    assert acquire_count["n"] == 2
    # enqueue_buffer called with a bare ndarray (no tagged tuple) once per
    # plane -> 2 total.
    assert shell._fs.enqueue_buffer.call_count == 2
    for c in shell._fs.enqueue_buffer.call_args_list:
        arg = c.args[0]
        assert isinstance(arg, np.ndarray), (
            "Single-channel stack enqueue_buffer must receive a bare "
            "ndarray, not a tagged tuple (back-compat)"
        )
    # stop_lasers called at the end.
    hw.stop_lasers.assert_called_once()
    assert len(finished_emits) == 1


def test_stack_worker_multi_channel_estop_mid_plane(qtbot) -> None:
    """StackWorker.run multi-channel: if estop_event is set after the
    first select_laser(0) in plane 0, the loop breaks, select_laser(1)
    is NOT called for that plane, and finished.emit fires exactly once.
    Both lasers are driven off by stop_lasers at the end."""
    worker, shell, hw = _make_stack_worker(qtbot, multi_channel=True)
    shell.stack_mode_started = True
    shell.saving_allowed = False
    shell.number_of_planes = 2
    shell.estop_event.is_set.return_value = False
    select_calls: list[int] = []

    def _fake_select_laser(idx):
        select_calls.append(idx)
        # Set estop after the first select_laser(0) of plane 0 so the
        # post-select_laser estop poll breaks the loop before
        # select_laser(1) and acquire_scan run.
        if idx == 0 and select_calls.count(0) == 1:
            shell.estop_event.is_set.return_value = True

    hw.select_laser.side_effect = _fake_select_laser
    worker.acquire_scan = Mock()  # type: ignore[method-assign]
    worker.camera.recorder_timeout_status = False
    worker.siggen.error = 0
    finished_emits: list[None] = []
    worker.finished.connect(lambda: finished_emits.append(None))
    worker.run()

    # Only select_laser(0) was called for plane 0 — select_laser(1) was
    # NOT called because estop was set after select_laser(0).
    assert select_calls == [0], (
        f"Expected only [0] (estop after first select_laser(0)), got {select_calls}"
    )
    # acquire_scan never ran (estop before the first acquire_scan).
    worker.acquire_scan.assert_not_called()
    # stop_lasers called at the end (safety — both off regardless).
    hw.stop_lasers.assert_called_once()
    # finished signal emitted exactly once.
    assert len(finished_emits) == 1


def test_stack_worker_multi_channel_timeout_after_channel0(qtbot) -> None:
    """StackWorker.run multi-channel: if camera.recorder_timeout_status
    is set after the channel-0 acquire_scan, the loop breaks before
    select_laser(1) runs for that plane (the timeout/error check after
    channel 0 aborts the per-plane cycle). finished.emit fires once."""
    worker, shell, hw = _make_stack_worker(qtbot, multi_channel=True)
    shell.stack_mode_started = True
    shell.saving_allowed = False
    shell.number_of_planes = 2
    select_calls: list[int] = []
    hw.select_laser.side_effect = lambda idx: select_calls.append(idx)
    acquire_count = {"n": 0}

    def _fake_acquire_scan():
        acquire_count["n"] += 1
        shell.reconstructed_frame = np.zeros((4, 4), dtype=np.uint16)
        # Set timeout after the first acquire_scan (channel 0 of plane 0).
        worker.camera.recorder_timeout_status = True

    worker.acquire_scan = _fake_acquire_scan  # type: ignore[method-assign]
    worker.camera.recorder_timeout_status = False
    worker.siggen.error = 0
    finished_emits: list[None] = []
    worker.finished.connect(lambda: finished_emits.append(None))
    worker.run()
    # Only select_laser(0) called (channel 0 of plane 0); select_laser(1)
    # never called because the timeout check after channel 0 broke the
    # per-plane cycle.
    assert select_calls == [0]
    assert acquire_count["n"] == 1
    hw.stop_lasers.assert_called_once()
    assert len(finished_emits) == 1


def test_stack_worker_multi_channel_siggen_error_after_channel1(qtbot) -> None:
    """StackWorker.run multi-channel: if siggen.error is set after the
    channel-1 acquire_scan, the loop breaks (the timeout/error check
    after channel 1 aborts before enqueuing). finished.emit fires once."""
    worker, shell, hw = _make_stack_worker(qtbot, multi_channel=True)
    shell.stack_mode_started = True
    shell.saving_allowed = True
    shell.number_of_planes = 2
    hw.select_laser = Mock()
    acquire_count = {"n": 0}

    def _fake_acquire_scan():
        acquire_count["n"] += 1
        shell.reconstructed_frame = np.zeros((4, 4), dtype=np.uint16)
        if acquire_count["n"] == 2:
            # Set siggen error after channel 1 of plane 0.
            worker.siggen.error = 1

    worker.acquire_scan = _fake_acquire_scan  # type: ignore[method-assign]
    worker.camera.recorder_timeout_status = False
    worker.siggen.error = 0
    finished_emits: list[None] = []
    worker.finished.connect(lambda: finished_emits.append(None))
    worker.run()
    # acquire_scan called twice (channel 0 + channel 1 of plane 0); the
    # siggen error after channel 1 broke before enqueuing.
    assert acquire_count["n"] == 2
    # enqueue_buffer NOT called — the error break happened before the
    # enqueue block.
    shell._fs.enqueue_buffer.assert_not_called()
    hw.stop_lasers.assert_called_once()
    assert len(finished_emits) == 1


def test_stack_worker_multi_channel_estop_after_select_laser1(qtbot) -> None:
    """StackWorker.run multi-channel: if estop_event is set after
    select_laser(1) (between channel 1 energize and channel 1
    acquire_scan), the loop breaks before the channel-1 acquire_scan.
    finished.emit fires once."""
    worker, shell, hw = _make_stack_worker(qtbot, multi_channel=True)
    shell.stack_mode_started = True
    shell.saving_allowed = False
    shell.number_of_planes = 2
    shell.estop_event.is_set.return_value = False
    select_calls: list[int] = []

    def _fake_select_laser(idx):
        select_calls.append(idx)
        if idx == 1:
            # E-stop after select_laser(1), before channel-1 acquire_scan.
            shell.estop_event.is_set.return_value = True

    hw.select_laser.side_effect = _fake_select_laser
    acquire_count = {"n": 0}

    def _fake_acquire_scan():
        acquire_count["n"] += 1
        shell.reconstructed_frame = np.zeros((4, 4), dtype=np.uint16)

    worker.acquire_scan = _fake_acquire_scan  # type: ignore[method-assign]
    worker.camera.recorder_timeout_status = False
    worker.siggen.error = 0
    finished_emits: list[None] = []
    worker.finished.connect(lambda: finished_emits.append(None))
    worker.run()
    # select_laser(0) + select_laser(1) called; acquire_scan ran once
    # (channel 0 only — estop before channel 1's acquire_scan).
    assert select_calls == [0, 1]
    assert acquire_count["n"] == 1
    hw.stop_lasers.assert_called_once()
    assert len(finished_emits) == 1


def test_stack_worker_multi_channel_none_frames_skips_enqueue(qtbot) -> None:
    """StackWorker.run multi-channel: when acquire_scan leaves
    reconstructed_frame as None (a failed scan that did not populate the
    frame), frame1/frame2 are captured as None and the enqueue is
    skipped (the `frame1 is not None and frame2 is not None` guard).
    The reconstructed_frames dict stays empty. finished.emit fires once."""
    worker, shell, hw = _make_stack_worker(qtbot, multi_channel=True)
    shell.stack_mode_started = True
    shell.saving_allowed = True
    shell.number_of_planes = 1
    hw.select_laser = Mock()

    def _fake_acquire_scan():
        # Leave reconstructed_frame as None (failed scan path).
        shell.reconstructed_frame = None

    worker.acquire_scan = _fake_acquire_scan  # type: ignore[method-assign]
    worker.camera.recorder_timeout_status = False
    worker.siggen.error = 0
    finished_emits: list[None] = []
    worker.finished.connect(lambda: finished_emits.append(None))
    worker.run()
    # enqueue_buffer NOT called — both frames were None.
    shell._fs.enqueue_buffer.assert_not_called()
    # reconstructed_frames dict stays empty (no non-None frames stored).
    assert shell.reconstructed_frames == {}
    hw.stop_lasers.assert_called_once()
    assert len(finished_emits) == 1


# -- _spawn_stack_worker multi_channel pre-sampling (AGENTS.md §11) ---------


def test_spawn_stack_worker_presamples_multi_channel(qtbot, request) -> None:
    """_spawn_stack_worker with both auto-laser checkboxes checked passes
    multi_channel=True to StackWorker; with one unchecked passes False.
    Verified by spying on the StackWorker constructor. Pre-sampling
    happens on the GUI thread after _cache_auto_laser_flags() — the
    worker never reads the checkboxes (AGENTS.md §11)."""
    from _helpers.controller_fixture import make_controller
    from lightsheet.gui import panels as panels_module

    # --- Both checked -> multi_channel=True ---
    ctrl, _bundle = make_controller(qtbot, request)
    ctrl._stack_thread = None
    ctrl._stack_worker = None
    # Configure a valid stack so updateUi_stack_mode_button reaches
    # _spawn_stack_worker: first/last plane set + non-zero step.
    ctrl.stack_first_plane_set = True
    ctrl.stack_last_plane_set = True
    ctrl.stack_starting_plane = 0.0
    ctrl.stack_ending_plane = 10.0
    ctrl.stack_panel.ui.doubleSpinBox_acqPlaneStepSize.setValue(1.0)
    ctrl.stack_mode_started = False
    # saving_allowed False -> the QMessageBox.question path is taken; the
    # default Yes answer lets the spawn proceed without a save filename.
    ctrl.save_panel.validate_file_name = Mock()
    ctrl.saving_allowed = False
    # Patch QMessageBox.question to auto-answer Yes (proceed without saving).
    with patch.object(
        panels_module.acquisition_panel, "QMessageBox"
    ) as msg_box_mod:
        msg_box_mod.question.return_value = msg_box_mod.StandardButton.Yes
        msg_box_mod.warning = Mock()

        ctrl.laser_panel.ui.checkBox_laserOneAutomatic.setChecked(True)
        ctrl.laser_panel.ui.checkBox_laserTwoAutomatic.setChecked(True)
        ctrl.save_panel.ui.lineEdit_saveDescription.setText("test")

        captured: dict[str, object] = {}

        def _capture_worker(*args, **kwargs):
            if "multi_channel" in kwargs:
                captured["multi_channel"] = kwargs["multi_channel"]
            else:
                # Positional: signature ends with multi_channel.
                captured["multi_channel"] = args[-1]
            worker_mock = Mock()
            worker_mock.finished = Mock()
            worker_mock.moveToThread = Mock()
            worker_mock.deleteLater = Mock()
            return worker_mock

        fake_thread = Mock()
        with (
            patch.object(
                panels_module.acquisition_panel,
                "StackWorker",
                side_effect=_capture_worker,
            ),
            patch.object(
                panels_module.acquisition_panel, "QThread", return_value=fake_thread
            ),
        ):
            ctrl.acquisition_panel.updateUi_stack_mode_button()

    assert captured.get("multi_channel") is True, (
        "Both auto-laser checkboxes checked -> multi_channel=True must be "
        "passed to StackWorker by _spawn_stack_worker"
    )

    # --- One unchecked -> multi_channel=False ---
    ctrl.stack_mode_started = False
    ctrl._stack_thread = None
    ctrl._stack_worker = None
    ctrl.laser_panel.ui.checkBox_laserTwoAutomatic.setChecked(False)
    captured.clear()
    fake_thread2 = Mock()

    with patch.object(
        panels_module.acquisition_panel, "QMessageBox"
    ) as msg_box_mod2:
        msg_box_mod2.question.return_value = msg_box_mod2.StandardButton.Yes
        msg_box_mod2.warning = Mock()
        with (
            patch.object(
                panels_module.acquisition_panel,
                "StackWorker",
                side_effect=_capture_worker,
            ),
            patch.object(
                panels_module.acquisition_panel, "QThread", return_value=fake_thread2
            ),
        ):
            ctrl.acquisition_panel.updateUi_stack_mode_button()

    assert captured.get("multi_channel") is False, (
        "Only one auto-laser checkbox checked -> multi_channel=False must "
        "be passed to StackWorker by _spawn_stack_worker"
    )


# -- PreviewWorker / LiveWorker D-04 first-laser-only guard -----------------
#
# D-04 (09-CONTEXT.md): continuous modes (preview + live) energize ONLY the
# first checked laser for the whole session when both auto-lasers are
# checked. Live/preview have no per-plane boundary to sequence over, so
# alternating L1<->L2 per frame would double frame time and flicker. With
# both checked, the continuous modes energize only L1 and hold L2 off for
# the session — the strict one-laser-energized invariant holds trivially.
#
# The guard suppresses _auto_laser2 temporarily for the start_lasers call
# so start_lasers (which reads the cached flags) energizes only L1, then
# restores the original flag so stop_lasers at the end still reads the
# original value (L2 was never energized, so stop_lasers is a no-op for
# L2, but the restore keeps the flag consistent for any subsequent read).


def _make_d04_shell(auto_laser1: bool, auto_laser2: bool):
    """Build a mock shell + real HardwareManager with MockLaser spies for
    D-04 continuous-mode guard tests. The shell has the attributes
    HardwareManager.start_lasers / stop_lasers / _poll_laser_status /
    _refresh_laser_readback read."""
    from lightsheet.gui.coordinators.hardware_manager import HardwareManager

    bundle = _make_bundle()
    shell = _WorkerShell()
    # Auto-laser flags pre-sampled on the GUI thread (the worker reads
    # these via start_lasers).
    shell._auto_laser1 = auto_laser1
    shell._auto_laser2 = auto_laser2
    hw = HardwareManager(bundle, shell)
    # Spy on the real MockLaser.on / .off so we can assert call counts
    # without changing the real HAL state mutation.
    laser0_on_spy = Mock(wraps=bundle.lasers[0].on)
    laser0_off_spy = Mock(wraps=bundle.lasers[0].off)
    laser1_on_spy = Mock(wraps=bundle.lasers[1].on)
    laser1_off_spy = Mock(wraps=bundle.lasers[1].off)
    bundle.lasers[0].on = laser0_on_spy  # type: ignore[method-assign]
    bundle.lasers[0].off = laser0_off_spy  # type: ignore[method-assign]
    bundle.lasers[1].on = laser1_on_spy  # type: ignore[method-assign]
    bundle.lasers[1].off = laser1_off_spy  # type: ignore[method-assign]
    spies = {
        "laser0_on": laser0_on_spy,
        "laser0_off": laser0_off_spy,
        "laser1_on": laser1_on_spy,
        "laser1_off": laser1_off_spy,
    }
    return bundle, shell, hw, spies


def test_preview_worker_both_checked_energizes_only_l1(qtbot) -> None:
    """PreviewWorker.run with both auto-lasers checked energizes ONLY L1
    for the session (D-04). lasers[0].on is called; lasers[1].on is NEVER
    called. stop_lasers at the end turns both off (L2 was never on, so
    its .off() is a no-op gated by the restored _auto_laser2 flag)."""
    bundle, shell, hw, spies = _make_d04_shell(
        auto_laser1=True, auto_laser2=True
    )
    shell.preview_mode_started = False  # loop doesn't execute
    worker = PreviewWorker(bundle, hw, shell)
    finished_emits: list[None] = []
    worker.finished.connect(lambda: finished_emits.append(None))
    worker.run()
    # L1 energized.
    spies["laser0_on"].assert_called_once()
    # L2 NEVER energized — the D-04 guard suppressed _auto_laser2 for the
    # start_lasers call so start_lasers skipped the L2 branch.
    spies["laser1_on"].assert_not_called()
    # stop_lasers at the end — L1 off called (it was on); L2 off NOT
    # called because the restored _auto_laser2 flag is True but L2 was
    # never energized... actually stop_lasers reads _auto_laser2 (restored
    # to True) and calls .off() unconditionally on L2. That is a safe
    # no-op (L2 is already off). We only assert L1.off was called and L2.on
    # was NOT called (the invariant).
    spies["laser0_off"].assert_called_once()
    assert len(finished_emits) == 1


def test_live_worker_both_checked_energizes_only_l1(qtbot) -> None:
    """LiveWorker.run with both auto-lasers checked energizes ONLY L1
    for the session (D-04). lasers[0].on is called; lasers[1].on is NEVER
    called."""
    bundle, shell, hw, spies = _make_d04_shell(
        auto_laser1=True, auto_laser2=True
    )
    shell.live_mode_started = False  # loop doesn't execute
    worker = LiveWorker(bundle, hw, shell)
    finished_emits: list[None] = []
    worker.finished.connect(lambda: finished_emits.append(None))
    worker.run()
    spies["laser0_on"].assert_called_once()
    spies["laser1_on"].assert_not_called()
    spies["laser0_off"].assert_called_once()
    assert len(finished_emits) == 1


def test_preview_worker_single_laser_unchanged(qtbot) -> None:
    """PreviewWorker.run with _auto_laser1=True, _auto_laser2=False
    energizes only L1 (existing behavior unchanged — the D-04 guard does
    not fire because both flags are not True). lasers[0].on called,
    lasers[1].on NOT called (because _auto_laser2 is False, start_lasers
    skips L2 without the guard)."""
    bundle, shell, hw, spies = _make_d04_shell(
        auto_laser1=True, auto_laser2=False
    )
    shell.preview_mode_started = False
    worker = PreviewWorker(bundle, hw, shell)
    finished_emits: list[None] = []
    worker.finished.connect(lambda: finished_emits.append(None))
    worker.run()
    spies["laser0_on"].assert_called_once()
    spies["laser1_on"].assert_not_called()
    spies["laser0_off"].assert_called_once()
    assert len(finished_emits) == 1
