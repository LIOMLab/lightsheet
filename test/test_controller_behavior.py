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
    from lightsheet.gui.workers import SingleWorker

    ctrl, _bundle = make_controller(qtbot, request)
    # Construct a SingleWorker to exercise the relocated acquire_scan
    # (now on _AcquireScanMixin in workers.py). The save-option args are
    # pre-sampled on the GUI thread in production; here we pass defaults.
    worker = SingleWorker(
        ctrl._bundle, ctrl._hw, ctrl, save_description="", save_stitch_blend=False
    )
    # waveform_cycles must be set so number_of_images is a valid int.
    worker.siggen.waveform_cycles = 1

    # Simulate a recorder timeout: monitor_recorder sets the timeout flag
    # (the real MockCamera.monitor_recorder never times out, so we wrap it
    # to inject the timeout the real Camera would surface).
    _real_monitor = worker.camera.monitor_recorder

    def _timeout_monitor(n: int) -> None:
        _real_monitor(n)
        worker.camera.recorder_timeout_status = True

    worker.camera.monitor_recorder = _timeout_monitor

    # Track whether copy_recorder_images is reached.
    copy_called: list[int] = []
    _real_copy = worker.camera.copy_recorder_images

    def _tracking_copy(n: int):
        copy_called.append(n)
        return _real_copy(n)

    worker.camera.copy_recorder_images = _tracking_copy

    # Track teardown calls.
    delete_recorder_called: list[bool] = []
    _real_delete_recorder = worker.camera.delete_recorder

    def _tracking_delete_recorder() -> None:
        delete_recorder_called.append(True)
        _real_delete_recorder()

    worker.camera.delete_recorder = _tracking_delete_recorder

    delete_scanner_called: list[bool] = []
    _real_delete_scanner = worker.siggen.delete_scanner

    def _tracking_delete_scanner() -> None:
        delete_scanner_called.append(True)
        _real_delete_scanner()

    worker.siggen.delete_scanner = _tracking_delete_scanner

    disarm_called: list[bool] = []
    _real_disarm = worker.camera.disarm

    def _tracking_disarm() -> None:
        disarm_called.append(True)
        _real_disarm()

    worker.camera.disarm = _tracking_disarm

    messages: list[str] = []
    ctrl.sig_message.connect(lambda msg: messages.append(msg))

    worker.acquire_scan()

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
    from lightsheet.gui.workers import SingleWorker

    ctrl, _bundle = make_controller(qtbot, request)
    # Construct a SingleWorker to exercise the relocated acquire_scan.
    worker = SingleWorker(
        ctrl._bundle, ctrl._hw, ctrl, save_description="", save_stitch_blend=False
    )
    worker.siggen.waveform_cycles = 1

    # Simulate a create_scanner DAQ failure: the real MockSigGen.create_scanner
    # is a no-op that never errors, so we wrap it to inject the error the real
    # SigGen would surface on a DAQ task creation fault.
    def _fail_create_scanner() -> None:
        worker.siggen.error = 1
        worker.siggen.error_message = "create_scan error"

    worker.siggen.create_scanner = _fail_create_scanner

    # Track whether start_recorder is reached.
    start_recorder_called: list[int] = []
    _real_start_recorder = worker.camera.start_recorder

    def _tracking_start_recorder(n: int) -> None:
        start_recorder_called.append(n)
        _real_start_recorder(n)

    worker.camera.start_recorder = _tracking_start_recorder

    delete_scanner_called: list[bool] = []
    _real_delete_scanner = worker.siggen.delete_scanner

    def _tracking_delete_scanner() -> None:
        delete_scanner_called.append(True)
        _real_delete_scanner()

    worker.siggen.delete_scanner = _tracking_delete_scanner

    disarm_called: list[bool] = []
    _real_disarm = worker.camera.disarm

    def _tracking_disarm() -> None:
        disarm_called.append(True)
        _real_disarm()

    worker.camera.disarm = _tracking_disarm

    messages: list[str] = []
    ctrl.sig_message.connect(lambda msg: messages.append(msg))

    worker.acquire_scan()

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
    assert not ctrl.laser_panel.ui.checkBox_laserOneAutomatic.isChecked(), (
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
# G5 — PreviewWorker.run polls estop_event and breaks before frame
#      acquisition; the finished signal fires exactly once (LSR-04 / CR-01)
# --------------------------------------------------------------------------- #


def test_preview_worker_breaks_on_estop_before_frame_acquisition(qtbot, request) -> None:
    """With estop_event set before the worker loop starts, the E-stop poll
    at the top of PreviewWorker.run's while loop must break before any
    per-frame acquisition work (start_recorder / copy_recorder_images), and
    the finished signal must still fire exactly once from the finally block
    (CR-01 — preview now aligns with live/single/stack per AGENTS.md §2)."""
    from lightsheet.gui.workers import PreviewWorker

    ctrl, bundle = make_controller(qtbot, request)

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

    # Construct the PreviewWorker and track its finished signal.
    worker = PreviewWorker(bundle, ctrl._hw, ctrl)
    finished_emits: list[None] = []
    worker.finished.connect(lambda: finished_emits.append(None))

    worker.run()

    # No per-frame acquisition work ran — the estop poll broke first.
    assert not start_recorder_called, (
        "PreviewWorker must not call start_recorder when estop is set"
    )
    assert not copy_called, (
        "PreviewWorker must not call copy_recorder_images when estop is set"
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

    # The fixture's bundle has Laser 1 = 555 nm, Laser 2 = 647 nm.
    assert ctrl.lasers[0].wavelength == 555
    assert ctrl.lasers[1].wavelength == 647

    ctrl.updateUi_initial_hardware_state()

    label_72_text = ctrl.laser_panel.ui.label_72.text()
    label_73_text = ctrl.laser_panel.ui.label_73.text()
    assert "555" in label_72_text, (
        "label_72 must show the live lasers[0].wavelength (555), not a "
        "hardcoded number."
    )
    assert "647" in label_73_text, (
        "label_73 must show the live lasers[1].wavelength (647), not a hardcoded number."
    )
    # Toggle buttons are relabeled with the live wavelengths too.
    toggle1_text = ctrl.laser_panel.ui.pushButton_laserOneToggle.text()
    toggle2_text = ctrl.laser_panel.ui.pushButton_laserTwoToggle.text()
    assert "555" in toggle1_text
    assert "647" in toggle2_text


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
        if "Laser 2 (647 nm)" in m and "daq write failed" in m
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


# --------------------------------------------------------------------------- #
# MCA-01 — MULTI-CH badge pill + stack-plan summary 2ch re-render + tooltip
# --------------------------------------------------------------------------- #


def _set_valid_stack_plan(ctrl) -> None:
    """Set a valid full stack plan (both boundaries + step + n_planes)."""
    ctrl.stack_first_plane_set = True
    ctrl.stack_last_plane_set = True
    ctrl.stack_panel.ui.doubleSpinBox_acqFirstPlane.setValue(100.0)
    ctrl.stack_panel.ui.doubleSpinBox_acqLastPlane.setValue(200.0)
    ctrl.stack_panel.ui.doubleSpinBox_acqPlaneStepSize.setValue(10.0)
    ctrl.stack_panel.updateUi_set_number_of_planes()


def test_multi_ch_badge_pill_shown_when_both_checked(qtbot, request) -> None:
    """When both auto-laser checkboxes are checked, _update_mode_badge
    appends ' · MULTI-CH' to the badge text (the persistent multi-channel
    pill tied to the checkbox-pair state). SINGLE mode is used because it
    renders as a clean mode name (no RUNNING suffix), matching the UI-SPEC
    'SINGLE · MULTI-CH' composition example."""
    ctrl, _bundle = make_controller(qtbot, request)
    ctrl.laser_panel.ui.checkBox_laserOneAutomatic.setChecked(True)
    ctrl.laser_panel.ui.checkBox_laserTwoAutomatic.setChecked(True)
    ctrl._cache_auto_laser_flags()

    ctrl._update_mode_badge("SINGLE")

    text = ctrl.ui.label_modeBadge.text()
    assert text == "SINGLE · MULTI-CH", (
        f"badge must read 'SINGLE · MULTI-CH' when both auto-lasers "
        f"checked; got {text!r}"
    )
    # The pill must NOT apply a green accent stylesheet — the green token
    # is reserved exclusively for laser ON status. The badge inherits the
    # existing QDarkStyle default text color + bold weight.
    assert "34C759" not in ctrl.ui.label_modeBadge.styleSheet().upper()


def test_multi_ch_badge_pill_hidden_when_one_checked(qtbot, request) -> None:
    """When only one (or zero) auto-laser checkbox is checked, the badge
    text is exactly today's mode text — no pill, no separator."""
    ctrl, _bundle = make_controller(qtbot, request)
    ctrl.laser_panel.ui.checkBox_laserOneAutomatic.setChecked(True)
    ctrl.laser_panel.ui.checkBox_laserTwoAutomatic.setChecked(False)
    ctrl._cache_auto_laser_flags()

    ctrl._update_mode_badge("SINGLE")

    text = ctrl.ui.label_modeBadge.text()
    assert text == "SINGLE", (
        f"badge must read exactly 'SINGLE' (no pill) when only one "
        f"auto-laser checked; got {text!r}"
    )

    # Zero checked → also no pill.
    ctrl.laser_panel.ui.checkBox_laserOneAutomatic.setChecked(False)
    ctrl._cache_auto_laser_flags()
    ctrl._update_mode_badge("STACK")
    assert "MULTI-CH" not in ctrl.ui.label_modeBadge.text()


def test_cache_auto_laser_flags_triggers_summary_refresh(qtbot, request) -> None:
    """_cache_auto_laser_flags triggers a stack-plan summary re-render
    after setting the cached flags, so the 2ch re-estimate appears
    synchronously with the checkbox change."""
    from unittest.mock import patch

    ctrl, _bundle = make_controller(qtbot, request)
    _set_valid_stack_plan(ctrl)

    with patch.object(
        ctrl.stack_panel, "_render_stack_plan_summary",
        wraps=ctrl.stack_panel._render_stack_plan_summary,
    ) as spy:
        ctrl.laser_panel.ui.checkBox_laserOneAutomatic.setChecked(True)
        ctrl.laser_panel.ui.checkBox_laserTwoAutomatic.setChecked(True)
        ctrl._cache_auto_laser_flags()

    assert spy.called, (
        "_cache_auto_laser_flags must call stack_panel._render_stack_plan_summary"
    )


def test_stack_plan_summary_2ch_doubles_time_and_size(qtbot, request) -> None:
    """When both auto-laser checkboxes are checked AND a valid stack plan
    exists, the summary inserts '2 ch × {N} planes' after the Planes clause
    and doubles BOTH Est. time and Est. size."""
    ctrl, _bundle = make_controller(qtbot, request)
    _set_valid_stack_plan(ctrl)

    # Single-channel baseline (one auto-laser).
    ctrl.laser_panel.ui.checkBox_laserOneAutomatic.setChecked(True)
    ctrl.laser_panel.ui.checkBox_laserTwoAutomatic.setChecked(False)
    ctrl.stack_panel._render_stack_plan_summary()
    single_text = ctrl.stack_panel.ui.label_stackPlanSummary.text()

    # Multi-channel (both checked).
    ctrl.laser_panel.ui.checkBox_laserTwoAutomatic.setChecked(True)
    ctrl.stack_panel._render_stack_plan_summary()
    multi_text = ctrl.stack_panel.ui.label_stackPlanSummary.text()

    assert "2 ch ×" in multi_text, (
        f"multi-channel summary must contain '2 ch ×'; got {multi_text!r}"
    )
    # The 2ch clause is inserted after the Planes clause.
    assert "Planes:" in multi_text
    planes_idx = multi_text.index("Planes:")
    ch_idx = multi_text.index("2 ch ×")
    assert ch_idx > planes_idx, "2 ch clause must come after the Planes clause"

    # Est. time doubled: extract the M:SS field from both and compare.
    def _est_time_seconds(text: str) -> int:
        marker = "Est. time: "
        i = text.index(marker) + len(marker)
        rest = text[i:]
        mss = rest.split("|")[0].strip()
        mm, ss = mss.split(":")
        return int(mm) * 60 + int(ss)

    def _est_size_mb(text: str) -> float:
        marker = "Est. size: "
        i = text.index(marker) + len(marker)
        rest = text[i:]
        num = rest.split("MB")[0].strip()
        return float(num)

    # Est. time is rendered as int(seconds) M:SS, so doubling the float
    # before the int truncation can differ by up to 1s from 2x the
    # truncated single-channel seconds. Allow a 2s tolerance.
    single_s = _est_time_seconds(single_text)
    multi_s = _est_time_seconds(multi_text)
    assert abs(multi_s - 2 * single_s) <= 2, (
        f"multi-channel Est. time must be ~2x single-channel; "
        f"single={single_s}s multi={multi_s}s "
        f"single={single_text!r} multi={multi_text!r}"
    )
    assert abs(_est_size_mb(multi_text) - 2 * _est_size_mb(single_text)) < 0.1, (
        f"multi-channel Est. size must be 2x single-channel; "
        f"single={single_text!r} multi={multi_text!r}"
    )


def test_stack_plan_summary_single_channel_byte_identical(qtbot, request) -> None:
    """When only one auto-laser checkbox is checked, the summary is
    byte-identical to today's single-channel render (no '2 ch' clause,
    no doubling). The baseline is captured with zero auto-lasers checked
    (the default 'today' state) and the one-checked render must match it
    byte-for-byte."""
    ctrl, _bundle = make_controller(qtbot, request)
    _set_valid_stack_plan(ctrl)

    # Baseline: zero auto-lasers checked (today's default single-channel
    # state — the summary does not branch on the checkbox pair).
    ctrl.laser_panel.ui.checkBox_laserOneAutomatic.setChecked(False)
    ctrl.laser_panel.ui.checkBox_laserTwoAutomatic.setChecked(False)
    ctrl.stack_panel._render_stack_plan_summary()
    baseline = ctrl.stack_panel.ui.label_stackPlanSummary.text()

    # One auto-laser checked — must be byte-identical to the baseline.
    ctrl.laser_panel.ui.checkBox_laserOneAutomatic.setChecked(True)
    ctrl.stack_panel._render_stack_plan_summary()
    one_checked = ctrl.stack_panel.ui.label_stackPlanSummary.text()

    assert one_checked == baseline, (
        f"single-channel (one auto-laser) summary must be byte-identical "
        f"to the zero-auto-laser baseline; baseline={baseline!r} "
        f"one_checked={one_checked!r}"
    )
    assert "2 ch" not in baseline
    assert "2 ch" not in one_checked
    # Sanity: the baseline has the expected clause shape (no doubling
    # marker, single Planes clause).
    assert baseline.count("Planes:") == 1
    assert baseline.count("Est. time:") == 1
    assert baseline.count("Est. size:") == 1


def test_auto_laser_tooltip_updated(qtbot, request) -> None:
    """Both auto-laser checkbox tooltips contain the multi-channel
    consequence sentence ('When BOTH auto-laser boxes are checked')."""
    ctrl, _bundle = make_controller(qtbot, request)
    tip1 = ctrl.laser_panel.ui.checkBox_laserOneAutomatic.toolTip()
    tip2 = ctrl.laser_panel.ui.checkBox_laserTwoAutomatic.toolTip()
    assert "When BOTH auto-laser boxes are checked" in tip1, (
        f"L1 auto-laser tooltip must contain the multi-channel "
        f"consequence sentence; got {tip1!r}"
    )
    assert "When BOTH auto-laser boxes are checked" in tip2, (
        f"L2 auto-laser tooltip must contain the multi-channel "
        f"consequence sentence; got {tip2!r}"
    )
    # The first sentence preserves the per-laser on/off explanation.
    assert "automatically during acquisition" in tip1
    assert "automatically during acquisition" in tip2
