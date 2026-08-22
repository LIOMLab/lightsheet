"""
Conformance tests for the Mock* HAL classes against their ABCs.

The Phase 3 tracer slice wires the Camera family end-to-end: a standalone
``MockCamera`` class that implements ``ICamera`` (and through inheritance
``ICameraCore``), constructed with no hardware. These tests prove the ABC
contract holds at runtime — ``isinstance(MockCamera(), ICamera)`` and
``isinstance(MockCamera(), ICameraCore)`` — and that the controller-reachable
HAL error surface (``error`` / ``error_message``) plus the controller-read
attributes (``xsize`` / ``ysize``) are populated.

Wave 2 (Plan 02) extends the conformance suite to the three non-laser device
families: SigGen, Motors (+ per-axis Motor), ETLs (+ Optotune). The same
isinstance + behavior-test pattern applies, plus two safety/fidelity
assertions:

- ``MockMotors`` MUST preserve Zaber travel-limit enforcement
  (``move_absolute_position`` raises ``ValueError`` on over-travel —
  AGENTS.md §2, physical safety).
- ``MockSigGen`` MUST reuse ``lightsheet.waveforms`` so its computed
  waveforms are bit-identical to a real run (D-09 — the TST-03 golden-master
  fidelity property).

Direct import + construct style mirrors ``test/test_motor_limits.py`` and
``test/test_ibeam.py``: mocks construct with no hardware, so no ``__new__``
bypass is needed (the whole point of mocks per AGENTS.md §5).
"""

import numpy as np

from lightsheet.hal import (
    ICamera,
    ICameraCore,
    IETLs,
    IETLsCore,
    IIBeam,
    IIBeamCore,
    ILasers,
    ILasersCore,
    IMotors,
    IMotorsCore,
    IOptotune,
    ISigGen,
    ISigGenCore,
    MockCamera,
    MockETLs,
    MockIBeam,
    MockLasers,
    MockMotors,
    MockSigGen,
)
from lightsheet.waveforms import sawtooth, squarewave, staircase

# --------------------------------------------------------------------------- #
# Camera family (Plan 01)
# --------------------------------------------------------------------------- #


def test_mock_camera_is_icamera() -> None:
    """MockCamera must be an ICamera (and through inheritance an ICameraCore)
    so the controller's HAL-typed seams accept it unchanged."""
    cam = MockCamera()
    assert isinstance(cam, ICamera)
    assert isinstance(cam, ICameraCore)


def test_mock_camera_has_hal_error_surface() -> None:
    """A freshly-constructed MockCamera carries the cross-cutting HAL error
    surface (AGENTS.md §10) in the cleared state — the controller's
    ``if self.camera.error`` checks must see 0 on a healthy construct."""
    cam = MockCamera()
    assert cam.error == 0
    assert cam.error_message == ""


def test_mock_camera_populates_controller_read_attrs() -> None:
    """The controller reads ``camera.xsize`` / ``camera.ysize`` as direct
    attributes (D-04). A MockCamera must populate them on construct (via
    its ``open()`` synthetic defaults) so the controller's image-viewer
    sizing and FrameViewer construction do not receive None."""
    cam = MockCamera()
    assert cam.xsize is not None
    assert cam.ysize is not None


# --------------------------------------------------------------------------- #
# SigGen family (Plan 02)
# --------------------------------------------------------------------------- #


def test_mock_siggen_is_isiggen() -> None:
    """MockSigGen must be an ISigGen (and through inheritance an ISigGenCore)
    so the controller's HAL-typed seams accept it unchanged."""
    siggen = MockSigGen(MockCamera())
    assert isinstance(siggen, ISigGen)
    assert isinstance(siggen, ISigGenCore)


def test_mock_siggen_has_hal_error_surface() -> None:
    siggen = MockSigGen(MockCamera())
    assert siggen.error == 0
    assert siggen.error_message == ""


def test_mock_siggen_populates_controller_read_attrs() -> None:
    """The controller reads ``siggen.galvo_left_amplitude`` /
    ``siggen.etl_left_offset`` / etc. as direct attributes (D-04). A MockSigGen
    must populate them on construct so the controller's waveform-parameter
    reads do not receive None."""
    siggen = MockSigGen(MockCamera())
    assert siggen.galvo_left_amplitude is not None
    assert siggen.galvo_right_amplitude is not None
    assert siggen.galvo_left_offset is not None
    assert siggen.galvo_right_offset is not None
    assert siggen.etl_left_amplitude is not None
    assert siggen.etl_right_amplitude is not None
    assert siggen.etl_left_offset is not None
    assert siggen.etl_right_offset is not None


def test_mock_siggen_waveforms_match_waveforms_module() -> None:
    """MockSigGen.compute_scan_waveforms() must produce arrays bit-identical
    to the direct ``lightsheet.waveforms`` output for the same parameters
    (D-09 — the TST-03 golden-master fidelity property). The mock reuses the
    pure-numpy waveform generators rather than re-implementing them, so a
    real run and a demo run produce identical scan ramps."""
    siggen = MockSigGen(MockCamera())
    siggen.compute_scan_waveforms()

    # Recompute the expected waveforms directly from waveforms.py using the
    # same parameters the mock used. The mock's compute_scan_waveforms mirrors
    # the real SigGen's parameter derivation (camera shutter mode, sample
    # rate, galvo/etl amplitudes/offsets, etl_steps). We assert the arrays
    # equal the direct generator output for those same derived params.
    # Camera shutter mode is "Rolling" (MockCamera default).
    # The mock stores the derived sample counts on itself, mirroring the
    # real SigGen; we read them back to recompute the expected waveforms.
    assert siggen.waveform_camera is not None
    assert siggen.waveform_galvo_left is not None
    assert siggen.waveform_galvo_right is not None
    assert siggen.waveform_etl_left is not None
    assert siggen.waveform_etl_right is not None

    # Bit-identical: same dtype, same shape, same values.
    for arr in (
        siggen.waveform_camera,
        siggen.waveform_galvo_left,
        siggen.waveform_galvo_right,
        siggen.waveform_etl_left,
        siggen.waveform_etl_right,
    ):
        assert isinstance(arr, np.ndarray)

    # Recompute the camera squarewave from the derived params and compare.
    # The mock exposes the derived counts so the test does not re-derive
    # them (which would duplicate the production logic under test).
    expected_camera = squarewave(
        pre_samples=siggen._camera_pre_samples,
        active_samples=siggen._camera_active_samples,
        post_samples=siggen._camera_post_samples,
        shift=0,
        repeat=siggen.waveform_cycles,
        inverted=False,
    )
    np.testing.assert_array_equal(siggen.waveform_camera, expected_camera)

    expected_galvo_left = sawtooth(
        activated=siggen.galvo_activated,
        pre_samples=siggen._galvo_pre_samples,
        trace_samples=siggen._galvo_scan_samples,
        retrace_samples=siggen._galvo_reset_samples,
        post_samples=siggen._galvo_post_samples,
        shift=siggen._galvo_shift,
        repeat=siggen.waveform_cycles,
        amplitude=siggen.galvo_left_amplitude,
        offset=siggen.galvo_left_offset,
        inverted=siggen.galvo_inverted,
        filtered=True,
    )
    np.testing.assert_array_equal(siggen.waveform_galvo_left, expected_galvo_left)

    expected_galvo_right = sawtooth(
        activated=siggen.galvo_activated,
        pre_samples=siggen._galvo_pre_samples,
        trace_samples=siggen._galvo_scan_samples,
        retrace_samples=siggen._galvo_reset_samples,
        post_samples=siggen._galvo_post_samples,
        shift=siggen._galvo_shift,
        repeat=siggen.waveform_cycles,
        amplitude=siggen.galvo_right_amplitude,
        offset=siggen.galvo_right_offset,
        inverted=siggen.galvo_inverted,
        filtered=True,
    )
    np.testing.assert_array_equal(siggen.waveform_galvo_right, expected_galvo_right)

    expected_etl_left = staircase(
        activated=siggen.etl_activated,
        step_samples=siggen._etl_step_samples,
        nbr_steps=siggen.waveform_cycles,
        shift=siggen._etl_shift,
        amplitude=siggen.etl_left_amplitude,
        offset=siggen.etl_left_offset,
        direction="down",
        filtered=True,
    )
    np.testing.assert_array_equal(siggen.waveform_etl_left, expected_etl_left)

    expected_etl_right = staircase(
        activated=siggen.etl_activated,
        step_samples=siggen._etl_step_samples,
        nbr_steps=siggen.waveform_cycles,
        shift=siggen._etl_shift,
        amplitude=siggen.etl_right_amplitude,
        offset=siggen.etl_right_offset,
        direction="up",
        filtered=True,
    )
    np.testing.assert_array_equal(siggen.waveform_etl_right, expected_etl_right)


def test_mock_siggen_lifecycle_methods_are_no_ops_returning_none() -> None:
    """MockSigGen lifecycle verbs (create/start/stop/delete scanner) are
    no-ops ending with ``return None`` (AGENTS.md §10) so the controller's
    call sites are unchanged between real and demo runs."""
    siggen = MockSigGen(MockCamera())
    assert siggen.create_scanner() is None
    assert siggen.start_scanner() is None
    assert siggen.monitor_scanner() is None
    assert siggen.stop_scanner() is None
    assert siggen.delete_scanner() is None


# --------------------------------------------------------------------------- #
# Motors family (Plan 02)
# --------------------------------------------------------------------------- #


def test_mock_motors_is_imotors() -> None:
    """MockMotors must be an IMotors (and through inheritance an IMotorsCore)
    so the controller's HAL-typed seams accept it unchanged."""
    motors = MockMotors()
    assert isinstance(motors, IMotors)
    assert isinstance(motors, IMotorsCore)


def test_mock_motors_has_hal_error_surface() -> None:
    motors = MockMotors()
    assert motors.error == 0
    assert motors.error_message == ""


def test_mock_motors_populates_per_axis_attrs() -> None:
    """The controller reads ``motors.vertical`` / ``motors.horizontal`` /
    ``motors.camera`` as the per-axis motor handles. A MockMotors must
    populate them on construct so the controller's per-axis call sites do
    not receive None."""
    motors = MockMotors()
    assert motors.vertical is not None
    assert motors.horizontal is not None
    assert motors.camera is not None


def test_mock_motors_enforces_travel_limits() -> None:
    """MockMotors MUST preserve Zaber travel-limit enforcement (AGENTS.md §2
    — physical safety). ``move_absolute_position`` past the high travel
    limit must raise ``ValueError`` BEFORE any state change, exactly as the
    real ZaberMotor does. A mock that silently accepted an over-travel
    target would let the controller's safety checks atrophy under demo
    mode, masking a regression that would damage hardware on the rig."""
    motors = MockMotors()
    # The vertical axis has a finite travel range; pick a target far beyond
    # its high limit. The mock's per-axis motor carries the same
    # limit_high_microsteps / limit_low_microsteps surface as the real
    # ZaberMotor, so an out-of-range target must raise.
    axis = motors.vertical
    # 9999 mm is far beyond any T-LS stage travel.
    with __import__("pytest").raises(ValueError):
        axis.move_absolute_position(9999, "mm")


def test_mock_motors_relative_move_enforces_travel_limits() -> None:
    """A relative move whose resulting position would exceed the high
    travel limit must also raise ValueError (the resulting-position check,
    matching the real ZaberMotor.move_relative_position contract)."""
    import pytest

    motors = MockMotors()
    axis = motors.vertical
    # Move near the top, then attempt a +large relative move past the limit.
    # The mock tracks position in software (position_microsteps); place it
    # near the high limit so a +50 mm delta would push past it.
    axis.position_microsteps = axis.limit_high_microsteps - 1
    with pytest.raises(ValueError):
        axis.move_relative_position(50, "mm")


# --------------------------------------------------------------------------- #
# ETLs family (Plan 02)
# --------------------------------------------------------------------------- #


def test_mock_etls_is_ietls() -> None:
    """MockETLs must be an IETLs (and through inheritance an IETLsCore)
    so the controller's HAL-typed seams accept it unchanged."""
    etls = MockETLs()
    assert isinstance(etls, IETLs)
    assert isinstance(etls, IETLsCore)


def test_mock_etls_has_hal_error_surface() -> None:
    etls = MockETLs()
    assert etls.error == 0
    assert etls.error_message == ""


def test_mock_etls_open_is_noop_returning_none() -> None:
    """MockETLs.open() is a no-op returning None (AGENTS.md §10) — the
    controller's ``self.etls.open(); self.etls.set_analog_mode()`` call
    sites are unchanged between real and demo runs."""
    etls = MockETLs()
    assert etls.open() is None
    assert etls.set_analog_mode() is None
    assert etls.close() is None


def test_mock_etls_optotune_crc_commands_raise_not_implemented() -> None:
    """MockOptotune's ~30 CRC-protected serial commands raise
    ``NotImplementedError`` (D-06). They cannot be verified against real
    hardware on the Mac; rig-verification task HW2-01 covers them. A mock
    that silently succeeded would mask a real-device protocol regression."""
    etls = MockETLs()
    # The mock exposes its per-lens Optotune instances.
    assert etls.etl_left is not None
    with __import__("pytest").raises(NotImplementedError):
        etls.etl_left.current(100.0)
    with __import__("pytest").raises(NotImplementedError):
        etls.etl_left.focalpower(2.0)


def test_mock_optotune_is_ioptotune() -> None:
    """MockOptotune must be an IOptotune so the per-lens seam is typed
    against the ABC, not the concrete class."""
    etls = MockETLs()
    assert isinstance(etls.etl_left, IOptotune)


# --------------------------------------------------------------------------- #
# Lasers family (Plan 03)
# --------------------------------------------------------------------------- #


def test_mock_lasers_is_ilasers() -> None:
    """MockLasers must be an ILasers (and through inheritance an ILasersCore)
    so the controller's HAL-typed seams accept it unchanged."""
    lasers = MockLasers()
    assert isinstance(lasers, ILasers)
    assert isinstance(lasers, ILasersCore)


def test_mock_lasers_has_hal_error_surface() -> None:
    lasers = MockLasers()
    assert lasers.error == 0
    assert lasers.error_message == ""


def test_mock_lasers_populates_controller_read_attrs() -> None:
    """The controller reads ``lasers.laser1_wavelength`` /
    ``lasers.laser1_max_power`` / ``lasers.laser1_active`` etc. as direct
    attributes (D-04). A MockLasers must populate them on construct so the
    controller's startup reads (wavelength labels, max-power spinbox
    bounds) do not receive None."""
    lasers = MockLasers()
    assert lasers.laser1_wavelength is not None
    assert lasers.laser2_wavelength is not None
    assert lasers.laser1_max_power is not None
    assert lasers.laser2_max_power is not None
    assert lasers.laser1_active is False
    assert lasers.laser2_active is False


def test_mock_lasers_set_power_clamps_to_max() -> None:
    """MockLasers.set_power MUST clamp the commanded power to the configured
    Max Power at the HAL boundary (AGENTS.md §2 — physical-safety control
    for a Class IIIB laser). A mock that removed the clamp would let the
    controller's safety checks atrophy under demo mode, masking a
    regression that would over-drive the laser AO channels on the rig."""
    lasers = MockLasers()
    # set_power(channel=1, value way above max) must reduce to laser1_max_power.
    lasers.set_power(1, 999999)
    assert lasers.laser1_power == lasers.laser1_max_power, (
        "set_power must clamp to laser1_max_power at the HAL boundary "
        "(AGENTS.md §2) — a mock that removed the clamp would mask a "
        "real-device over-power regression"
    )
    # And channel 2.
    lasers.set_power(2, 999999)
    assert lasers.laser2_power == lasers.laser2_max_power


def test_mock_lasers_lifecycle_toggles_active_flag() -> None:
    """laser1_on/laser1_off toggle the laser1_active flag (no DAQ write).
    The controller reads laser1_active to decide whether to show the laser
    as energized, so the mock must keep the flag in sync with the on/off
    calls just like the real Lasers does."""
    lasers = MockLasers()
    assert lasers.laser1_active is False
    lasers.laser1_on()
    assert lasers.laser1_active is True
    lasers.laser1_off()
    assert lasers.laser1_active is False
    lasers.laser2_on()
    assert lasers.laser2_active is True
    lasers.laser2_off()
    assert lasers.laser2_active is False


# --------------------------------------------------------------------------- #
# IBeam family (Plan 03)
# --------------------------------------------------------------------------- #


def test_mock_ibeam_is_iibeam() -> None:
    """MockIBeam must be an IIBeam (and through inheritance an IIBeamCore)
    so the controller's HAL-typed seams accept it unchanged."""
    ibeam = MockIBeam()
    assert isinstance(ibeam, IIBeam)
    assert isinstance(ibeam, IIBeamCore)


def test_mock_ibeam_has_hal_error_surface() -> None:
    ibeam = MockIBeam()
    assert ibeam.error == 0
    assert ibeam.error_message == ""


def test_mock_ibeam_populates_controller_read_attrs() -> None:
    """The controller reads ``ibeam.wavelength`` / ``ibeam.max_power`` as
    direct attributes (D-04) — wavelength for the GUI label, max_power for
    the spinbox upper bound. A MockIBeam must populate them on construct."""
    ibeam = MockIBeam()
    assert ibeam.wavelength is not None
    assert ibeam.max_power is not None
    assert ibeam.error == 0


def test_mock_ibeam_off_is_synchronous() -> None:
    """MockIBeam.off() MUST be synchronous — set ``_is_on=False`` and
    ``_power=0`` and return None immediately, with no thread/queue offload
    (AGENTS.md §2 — the E-stop kill path drives ``ibeam.off()`` on the GUI
    thread; offloading it would break the synchronous-off safety contract
    for a Class IIIB laser). A mock that queued off() would let the
    controller's E-stop path atrophy under demo mode, masking a regression
    that would delay laser shutdown on the rig."""
    ibeam = MockIBeam()
    ibeam.on()
    assert ibeam._is_on is True
    # off() must return None and synchronously clear _is_on.
    result = ibeam.off()
    assert result is None
    assert ibeam._is_on is False, (
        "off() must synchronously set _is_on=False — no queue/thread offload "
        "(AGENTS.md §2 E-stop kill path)"
    )
    assert ibeam._power == 0


def test_mock_ibeam_set_power_clamps_to_max() -> None:
    """MockIBeam.set_power MUST clamp to max_power at the HAL boundary
    (AGENTS.md §2 — physical-safety control for a Class IIIB laser)."""
    ibeam = MockIBeam()
    ibeam.set_power(999999)
    assert ibeam._power == ibeam.max_power, (
        "set_power must clamp to max_power at the HAL boundary (AGENTS.md §2)"
    )
