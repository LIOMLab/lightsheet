"""
Behavioral regression tests for Phase 01 controller methods, via real
construction.

The real ``Controller_MainWindow`` is constructed via ``make_controller``
(see ``test/_helpers/controller_fixture.py``), which mirrors
``lightsheet/__main__.main()``'s composition root: a mock ``DeviceBundle``
is built, the controller is constructed with ``demo=True``, all four
collaborators (``FrameSaverController`` / ``HardwareManager`` /
``AcquisitionCoordinator`` / ``MotorController``) are wired, and
``hardware_init`` is called so ``self.lasers`` / ``self.camera`` /
``self.siggen`` / ``self.motors`` / ``self.etls`` and the display/status
timers are populated. Each test calls the REAL method on the real
controller or collaborator and asserts on real attributes/signals.

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

from _helpers.controller_fixture import make_controller


# --------------------------------------------------------------------------- #
# G1 — start_lasers surfaces a laser-1 DAQ write failure (LSR-01 / G-01-1)
# --------------------------------------------------------------------------- #


def test_start_lasers_surfaces_laser1_daq_error(qtbot, request) -> None:
    """When self.lasers[0].on() leaves .error set, start_lasers must emit
    an operator message naming the cause and reset the flag — a failed
    laser-1 DAQ start is no longer a silent no-op (G-01-1)."""
    ctrl, _bundle = make_controller(qtbot, request)
    ctrl._auto_laser1 = True
    ctrl._auto_laser2 = False
    ctrl.laser1_power_pct = 50

    laser1 = ctrl._hw.lasers[0]
    # Simulate a DAQ write failure: on() sets error=1 (the real MockLaser.on()
    # never errors, so we wrap it to inject the failure the DAQLaser backend
    # would surface on a real write fault).
    _real_on = laser1.on

    def _failing_on() -> None:
        _real_on()
        laser1.error = 1
        laser1.error_message = "daq write failed"

    laser1.on = _failing_on

    messages: list[str] = []
    ctrl.sig_message.connect(lambda msg: messages.append(msg))

    ctrl._hw.start_lasers()

    # An operator message was emitted naming the failure.
    assert any("daq write failed" in m for m in messages), (
        "start_lasers must emit sig_message when self.lasers[0].error is "
        "set after .on() — a silent no-op is the G-01-1 regression."
    )
    # The flag is reset so the warning fires once per failure.
    assert laser1.error == 0


# --------------------------------------------------------------------------- #
# G2 — acquire_scan aborts on recorder timeout before copy_recorder_images
#      (BUG-01)
# --------------------------------------------------------------------------- #


def test_acquire_scan_aborts_on_recorder_timeout_before_copy(qtbot, request) -> None:
    """When camera.recorder_timeout_status is True after monitor_recorder,
    acquire_scan must emit the timeout warning, tear down the recorder and
    scanner, disarm the camera, and return BEFORE copy_recorder_images is
    ever reached — a timed-out plane can never be saved as zero-filled
    frames (BUG-01)."""
    ctrl, _bundle = make_controller(qtbot, request)
    acq = ctrl._acq
    # waveform_cycles must be set so number_of_images is a valid int.
    acq.siggen.waveform_cycles = 1

    # Simulate a recorder timeout: monitor_recorder sets the timeout flag
    # (the real MockCamera.monitor_recorder never times out, so we wrap it
    # to inject the timeout the real Camera would surface).
    _real_monitor = acq.camera.monitor_recorder

    def _timeout_monitor(n: int) -> None:
        _real_monitor(n)
        acq.camera.recorder_timeout_status = True

    acq.camera.monitor_recorder = _timeout_monitor

    # Track whether copy_recorder_images is reached.
    copy_called: list[int] = []
    _real_copy = acq.camera.copy_recorder_images

    def _tracking_copy(n: int):
        copy_called.append(n)
        return _real_copy(n)

    acq.camera.copy_recorder_images = _tracking_copy

    # Track teardown calls.
    delete_recorder_called: list[bool] = []
    _real_delete_recorder = acq.camera.delete_recorder

    def _tracking_delete_recorder() -> None:
        delete_recorder_called.append(True)
        _real_delete_recorder()

    acq.camera.delete_recorder = _tracking_delete_recorder

    delete_scanner_called: list[bool] = []
    _real_delete_scanner = acq.siggen.delete_scanner

    def _tracking_delete_scanner() -> None:
        delete_scanner_called.append(True)
        _real_delete_scanner()

    acq.siggen.delete_scanner = _tracking_delete_scanner

    disarm_called: list[bool] = []
    _real_disarm = acq.camera.disarm

    def _tracking_disarm() -> None:
        disarm_called.append(True)
        _real_disarm()

    acq.camera.disarm = _tracking_disarm

    messages: list[str] = []
    ctrl.sig_message.connect(lambda msg: messages.append(msg))

    acq.acquire_scan()

    # The defining assertion: copy_recorder_images must NOT be called.
    assert not copy_called, (
        "acquire_scan must not call copy_recorder_images on recorder timeout"
    )
    # The operator was warned.
    assert any("Camera timeout" in m for m in messages)
    # Teardown ran and the camera was disarmed before returning.
    assert delete_recorder_called
    assert delete_scanner_called
    assert disarm_called


# --------------------------------------------------------------------------- #
# G3 — acquire_scan surfaces a siggen create_scanner failure before the
#      recorder is primed (BUG-01 / G-01-5)
# --------------------------------------------------------------------------- #


def test_acquire_scan_surfaces_siggen_error_before_recorder(qtbot, request) -> None:
    """When create_scanner() sets self.siggen.error (its bare-except on DAQ
    task creation failure), acquire_scan must emit an operator message,
    delete the scanner, disarm the camera, and return BEFORE
    start_recorder() is ever called — a DAQ scan-task failure is no longer
    masked as a silent 15 s camera timeout (G-01-5)."""
    ctrl, _bundle = make_controller(qtbot, request)
    acq = ctrl._acq
    acq.siggen.waveform_cycles = 1

    # Simulate a create_scanner DAQ failure: the real MockSigGen.create_scanner
    # is a no-op that never errors, so we wrap it to inject the error the real
    # SigGen would surface on a DAQ task creation fault.
    def _fail_create_scanner() -> None:
        acq.siggen.error = 1
        acq.siggen.error_message = "create_scan error"

    acq.siggen.create_scanner = _fail_create_scanner

    # Track whether start_recorder is reached.
    start_recorder_called: list[int] = []
    _real_start_recorder = acq.camera.start_recorder

    def _tracking_start_recorder(n: int) -> None:
        start_recorder_called.append(n)
        _real_start_recorder(n)

    acq.camera.start_recorder = _tracking_start_recorder

    delete_scanner_called: list[bool] = []
    _real_delete_scanner = acq.siggen.delete_scanner

    def _tracking_delete_scanner() -> None:
        delete_scanner_called.append(True)
        _real_delete_scanner()

    acq.siggen.delete_scanner = _tracking_delete_scanner

    disarm_called: list[bool] = []
    _real_disarm = acq.camera.disarm

    def _tracking_disarm() -> None:
        disarm_called.append(True)
        _real_disarm()

    acq.camera.disarm = _tracking_disarm

    messages: list[str] = []
    ctrl.sig_message.connect(lambda msg: messages.append(msg))

    acq.acquire_scan()

    # The recorder was never primed — the failure surfaced before it.
    assert not start_recorder_called, (
        "acquire_scan must not call start_recorder when create_scanner fails"
    )
    # The operator saw the real DAQ cause.
    assert any("Scan task creation failed" in m for m in messages)
    assert any("create_scan error" in m for m in messages)
    # Teardown ran.
    assert delete_scanner_called
    assert disarm_called


# --------------------------------------------------------------------------- #
# G4 — start_lasers reads cached auto-laser flags, never a Qt widget
#      (BUG-01 / G-01-5)
# --------------------------------------------------------------------------- #


def test_start_lasers_reads_cached_flags_not_widgets(qtbot, request) -> None:
    """start_lasers runs on an acquisition worker thread and must read only
    the cached auto-laser flags sampled on the GUI thread — never a Qt
    widget (AGENTS.md §11 cross-thread rule, G-01-5). With the auto-laser1
    cached flag True but the Qt checkbox unchecked (its default state),
    start_lasers must energize laser 1 — proving it reads the cached flag,
    not the widget (if it read the checkbox, laser 1 would stay dark)."""
    ctrl, _bundle = make_controller(qtbot, request)

    # The Qt checkbox is unchecked by default (QCheckBox defaults to False).
    # Set the cached flag True — if start_lasers reads the widget instead of
    # the cached flag, laser 1 would NOT be energized.
    assert not ctrl.ui.checkBox_laserOneAutomatic.isChecked(), (
        "checkbox must be unchecked for this test to prove the cached flag "
        "is read, not the widget"
    )
    ctrl._auto_laser1 = True
    ctrl._auto_laser2 = False
    ctrl.laser1_power_pct = 50

    laser1 = ctrl._hw.lasers[0]
    assert not laser1.active  # sanity: laser starts off

    ctrl._hw.start_lasers()

    # Laser 1 was energized — start_lasers read the cached _auto_laser1 flag
    # (True), not the unchecked checkbox.
    assert laser1.active, (
        "start_lasers must energize laser 1 when the cached _auto_laser1 "
        "flag is True, even if the Qt checkbox is unchecked — it must read "
        "the cached flag, not the widget (AGENTS.md §11)."
    )


# --------------------------------------------------------------------------- #
# G5 — preview_mode_worker polls estop_event and breaks before frame
#      acquisition; the finished signal fires exactly once (LSR-04 / CR-01)
# --------------------------------------------------------------------------- #


def test_preview_mode_worker_breaks_on_estop_before_frame_acquisition(qtbot, request) -> None:
    """With estop_event set before the worker loop starts, the E-stop poll
    at the top of preview_mode_worker's while loop must break before any
    per-frame acquisition work (start_recorder / copy_recorder_images), and
    the finished signal must still fire exactly once from the finally block
    (CR-01 — preview now aligns with live/single/stack per AGENTS.md §2)."""
    ctrl, _bundle = make_controller(qtbot, request)

    # E-stop actuated before the loop starts.
    ctrl.estop_event.set()
    ctrl.preview_mode_started = True

    # Track whether per-frame acquisition work runs.
    start_recorder_called: list[int] = []
    _real_start_recorder = ctrl._acq.camera.start_recorder

    def _tracking_start_recorder(n: int) -> None:
        start_recorder_called.append(n)
        _real_start_recorder(n)

    ctrl._acq.camera.start_recorder = _tracking_start_recorder

    copy_called: list[int] = []
    _real_copy = ctrl._acq.camera.copy_recorder_images

    def _tracking_copy(n: int):
        copy_called.append(n)
        return _real_copy(n)

    ctrl._acq.camera.copy_recorder_images = _tracking_copy

    # Track the finished signal.
    finished_emits: list[None] = []
    ctrl.sig_preview_mode_finished.connect(lambda: finished_emits.append(None))

    ctrl._acq.preview_mode_worker()

    # No per-frame acquisition work ran — the estop poll broke first.
    assert not start_recorder_called, (
        "preview_mode_worker must not call start_recorder when estop is set"
    )
    assert not copy_called, (
        "preview_mode_worker must not call copy_recorder_images when estop is set"
    )
    # The finished signal fired exactly once (the finally block).
    assert len(finished_emits) == 1


# --------------------------------------------------------------------------- #
# G6 — updateUi_initial_hardware_state sets wavelength labels from the live
#      list[ILaser] instances (LSR-05)
# --------------------------------------------------------------------------- #


def test_wavelength_labels_set_from_live_instances(qtbot, request) -> None:
    """updateUi_initial_hardware_state must set the wavelength labels from
    the live self.lasers[0].wavelength and self.lasers[1].wavelength
    instances — not hardcoded numbers — so the operator sees the real
    configured wavelength (LSR-05)."""
    ctrl, _bundle = make_controller(qtbot, request)

    # The fixture's bundle has Laser 1 = 555 nm, Laser 2 = 640 nm.
    assert ctrl.lasers[0].wavelength == 555
    assert ctrl.lasers[1].wavelength == 640

    ctrl.updateUi_initial_hardware_state()

    label_72_text = ctrl.ui.label_72.text()
    label_73_text = ctrl.ui.label_73.text()
    assert "555" in label_72_text, (
        "label_72 must show the live lasers[0].wavelength (555), not a "
        "hardcoded number."
    )
    assert "640" in label_73_text, (
        "label_73 must show the live lasers[1].wavelength (640), not a hardcoded number."
    )
    # Toggle buttons are relabeled with the live wavelengths too.
    toggle1_text = ctrl.ui.pushButton_laserOneToggle.text()
    toggle2_text = ctrl.ui.pushButton_laserTwoToggle.text()
    assert "555" in toggle1_text
    assert "640" in toggle2_text


# --------------------------------------------------------------------------- #
# G7 — updateUi_estop_pressed warn branch: fires when a laser's off() leaves
#      error truthy, does NOT fire when all off() calls succeed (AGENTS.md §2).
# --------------------------------------------------------------------------- #


def test_estop_warn_branch_fires_for_failed_laser(qtbot, request) -> None:
    """updateUi_estop_pressed must check laser.error after each off() and
    emit an operator warning naming the failed laser when off() leaves
    error truthy — the D-06 E-stop safety arc. With one laser reporting
    a clean off() (error=0) and one reporting a failed off() (error=1),
    the warn branch must fire EXACTLY ONCE for the failed laser, naming
    its label and error_message, and reset the error flag after warning
    (AGENTS.md §2: never silently show a clean state when a laser may
    still be emitting)."""
    ctrl, _bundle = make_controller(qtbot, request)

    laser_ok = ctrl.lasers[0]
    laser_failed = ctrl.lasers[1]

    # Simulate a failed off() on laser 2: the real MockLaser.off() never
    # errors, so we wrap it to inject the error the real backend would
    # surface on a hardware write fault.
    _real_off = laser_failed.off

    def _failing_off() -> None:
        _real_off()
        laser_failed.error = 1
        laser_failed.error_message = "daq write failed"

    laser_failed.off = _failing_off

    messages: list[str] = []
    ctrl.sig_message.connect(lambda msg: messages.append(msg))

    ctrl.updateUi_estop_pressed()

    # Cooperative-abort Event set on the GUI thread.
    assert ctrl.estop_event.is_set()
    # Both lasers driven off synchronously.
    assert not laser_ok.active
    assert not laser_failed.active
    # The warn branch fired for the failed laser — find the emit call
    # whose message names the failed laser's label and error_message.
    warn_msgs = [
        m for m in messages
        if "Laser 2 (640 nm)" in m and "daq write failed" in m
    ]
    assert len(warn_msgs) == 1, (
        f"warn branch must fire exactly once for the failed laser; "
        f"got {len(warn_msgs)} warn messages in {messages}"
    )
    assert "E-STOP" in warn_msgs[0]
    assert "STILL BE ON" in warn_msgs[0]
    # The error flag is reset after the warn so it fires once per failure.
    assert laser_failed.error == 0


def test_estop_warn_branch_does_not_fire_when_all_off_succeed(qtbot, request) -> None:
    """The control case: when both lasers report error=0 after off(), the
    warn branch must NOT fire — no spurious 'may still be on' warning when
    every off() succeeded cleanly. The method still emits its terminal
    'E-STOP actuated' status message, but no per-laser warning."""
    ctrl, _bundle = make_controller(qtbot, request)

    laser1 = ctrl.lasers[0]
    laser2 = ctrl.lasers[1]

    messages: list[str] = []
    ctrl.sig_message.connect(lambda msg: messages.append(msg))

    ctrl.updateUi_estop_pressed()

    # Both lasers driven off.
    assert not laser1.active
    assert not laser2.active
    # No per-laser warning emitted — every emit message is the terminal
    # "E-STOP actuated" status, none name a laser label or "STILL BE ON".
    warn_msgs = [
        m for m in messages
        if "STILL BE ON" in m or "off command failed" in m
    ]
    assert len(warn_msgs) == 0, (
        f"warn branch must not fire when all off() calls succeed; "
        f"got {warn_msgs} in {messages}"
    )
