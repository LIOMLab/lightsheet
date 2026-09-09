"""Unit tests for the ``MockStage`` / ``MockSample`` sphere world model.

Verified behaviours:

- Lateral cross-section: the frame peaks at the sensor centre and the
  half-max region covers the expected FOV fraction.
- Axial intensity: the finite-thickness light sheet makes the frame
  p99 a Gaussian in ``h - light_sheet_x_mm`` across the 3-14 mm span,
  with the effective axial sigma widened by the sheet convolution.
- Focus model: the ideal camera focus is
  ``light_sheet_x_mm + lensing_shift(h)`` (a Gaussian bump of the axial
  sample position); camera defocus applies a 2D Gaussian PSF blur that
  measurably drops ``frame_sharpness_variance``, with a deadband that
  skips the blur for near-focus planes.
- Scaling: frame amplitude follows the first active laser's
  ``power / max_power`` and the camera ``exposure_time``; the brightest
  slice's uint16 p99 lands near the 0.90-0.95 adaptive target band.
- Determinism: identical state yields bit-exact frames (no RNG).

Default-is-off invariant: ``test/helpers/factories.py:make_bundle()``
does NOT attach a stage — ``bundle.camera.frame_source is None``; only
``_build_demo_bundle()`` wires it.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pytest

pytest.importorskip("PySide6")

_UM = "µm"  # µm — motor moves are issued in micrometres
_SENSOR = (512, 512)


def _make_stage(
    sample_kwargs: dict[str, Any] | None = None,
    lasers: tuple[Any, ...] | None = None,
    sensor_shape: tuple[int, int] = _SENSOR,
) -> tuple[Any, Any, Any, tuple[Any, ...]]:
    """Construct a MockStage + MockCamera pair with a single active
    laser at full power (unless ``lasers`` overrides)."""
    from lightsheet.hal.mocks.mock_camera import MockCamera
    from lightsheet.hal.mocks.mock_laser import MockLaser
    from lightsheet.hal.mocks.mock_motors import MockMotors
    from lightsheet.hal.mocks.mock_stage import MockSample, MockStage

    kwargs: dict[str, Any] = {"sensor_shape": sensor_shape}
    if sample_kwargs:
        kwargs.update(sample_kwargs)
    sample = MockSample(**kwargs)
    motors = MockMotors()
    if lasers is None:
        lasers = (MockLaser(wavelength=555, max_power_mw=300.0),)
        lasers[0].set_power(300.0)
        lasers[0].on()
    stage = MockStage(sample, motors, lasers)
    camera = MockCamera(verbose=False)
    camera.xsize, camera.ysize = sensor_shape[1], sensor_shape[0]
    camera.exposure_time = 0.1
    return stage, camera, motors, lasers


def _move_h(motors: Any, h_mm: float) -> None:
    motors.horizontal.move_absolute_position(h_mm * 1000.0, _UM)


def _move_cam(motors: Any, mm: float) -> None:
    motors.camera.move_absolute_position(mm * 1000.0, _UM)


def _focus_at_ideal(stage: Any, motors: Any, h_mm: float) -> float:
    """Park the camera axis at the (lensing-shifted) ideal focus."""
    ideal_mm = stage._ideal_focus_mm(h_mm)
    _move_cam(motors, ideal_mm)
    return float(ideal_mm)


def test_mock_stage_lateral_cross_section_centered() -> None:
    """At h = light_sheet_x_mm the texture-free frame peaks at the
    sensor centre and the half-max region spans the expected ~75 % FOV
    diameter (computed from sigma/pixel_size, not a hardcoded count)."""
    # FOV = 512 px * 6.5 um = 3.328 mm; choose sigma so the half-max
    # diameter (2 * sigma * sqrt(2 ln 2)) is ~75 % of the FOV.
    sigma_mm = 0.75 * (_SENSOR[0] * 6.5e-3) / (2 * math.sqrt(2 * math.log(2)))
    stage, camera, motors, _ = _make_stage(
        {"sigma_y_mm": sigma_mm, "sigma_z_mm": sigma_mm, "texture_amplitude": 0.0}
    )
    _move_h(motors, stage.sample.light_sheet_x_mm)
    _focus_at_ideal(stage, motors, stage.sample.light_sheet_x_mm)

    frame = stage.frame(camera, 0)

    assert frame.shape == _SENSOR
    peak = np.unravel_index(np.argmax(frame), frame.shape)
    centre = (_SENSOR[0] / 2.0, _SENSOR[1] / 2.0)
    assert abs(peak[0] - centre[0]) <= 2 and abs(peak[1] - centre[1]) <= 2, (
        f"frame must peak at the sensor centre, got argmax {peak}"
    )

    half_max_count = int(np.count_nonzero(frame >= frame.max() / 2.0))
    radius_px = sigma_mm * math.sqrt(2 * math.log(2)) / (6.5e-3)
    expected = math.pi * radius_px**2
    assert abs(half_max_count - expected) / expected < 0.10, (
        f"half-max area {half_max_count} px vs expected {expected:.0f} px "
        "(~75 % FOV diameter)"
    )


def test_mock_stage_axial_intensity_gaussian_profile() -> None:
    """p99 falls off as a Gaussian in h - light_sheet_x_mm across the
    3-14 mm span, symmetric on both sides of the sheet."""
    stage, camera, motors, _ = _make_stage({"texture_amplitude": 0.0})
    _focus_at_ideal(stage, motors, stage.sample.light_sheet_x_mm)

    def p99_at(h_mm: float) -> float:
        _move_h(motors, h_mm)
        return float(np.percentile(stage.frame(camera, 0), 99))

    at_sheet = p99_at(8.5)
    near = p99_at(5.5)
    far = p99_at(3.0)
    assert at_sheet > near > far, (
        f"axial profile must be Gaussian in h - sheet_x: "
        f"p99 {at_sheet:.4f} @8.5, {near:.4f} @5.5, {far:.4f} @3.0"
    )
    mirror = p99_at(11.5)
    assert abs(mirror - near) / near < 0.05, (
        f"profile must be symmetric: p99 {mirror:.4f} @11.5 vs {near:.4f} @5.5"
    )


def test_mock_stage_finite_sheet_widens_axial_profile() -> None:
    """The effective axial sigma is sqrt(sigma_x^2 + sigma_sheet^2): the
    measured fall-off is shallower than a sheet-free model predicts."""
    # Use a thin sample and an exaggerated sheet so the widening is
    # measurable rather than a 1e-6 perturbation.
    stage, camera, motors, _ = _make_stage(
        {
            "sigma_x_mm": 0.5,
            "light_sheet_fwhm_um": 2000.0,
            "texture_amplitude": 0.0,
        }
    )
    _focus_at_ideal(stage, motors, stage.sample.light_sheet_x_mm)

    sheet_x = stage.sample.light_sheet_x_mm
    _move_h(motors, sheet_x)
    peak = float(np.percentile(stage.frame(camera, 0), 99))

    # Sheet-free half-max offset: delta = sigma_x * sqrt(2 ln 2).
    delta_mm = stage.sample.sigma_x_mm * math.sqrt(2 * math.log(2))
    _move_h(motors, sheet_x - delta_mm)
    ratio = float(np.percentile(stage.frame(camera, 0), 99)) / peak

    assert ratio > 0.5, (
        f"finite sheet must widen the profile: at the sheet-free "
        f"half-max offset the ratio is {ratio:.3f} (> 0.5)"
    )


def test_mock_stage_defocus_blur_drops_sharpness() -> None:
    """frame_sharpness_variance at the lensing-shifted ideal focus
    strictly exceeds the value at +1 mm camera defocus, giving the
    focus residual a directionally meaningful gradient."""
    from lightsheet.focus.sharpness import frame_sharpness_variance

    stage, camera, motors, _ = _make_stage()
    h_mm = stage.sample.light_sheet_x_mm
    _move_h(motors, h_mm)
    ideal_mm = _focus_at_ideal(stage, motors, h_mm)

    sharp_in = frame_sharpness_variance(stage.frame(camera, 0))
    _move_cam(motors, ideal_mm + 1.0)
    sharp_out = frame_sharpness_variance(stage.frame(camera, 0))

    assert sharp_in > sharp_out, (
        f"in-focus sharpness {sharp_in} must exceed defocused {sharp_out}"
    )
    assert (sharp_in - sharp_out) / sharp_in > 0.10, (
        "sharpness gradient must be strong enough to move a focus "
        f"residual (got {(sharp_in - sharp_out) / sharp_in:.1%})"
    )


def test_mock_stage_blur_deadband_returns_unblurred_slice() -> None:
    """Camera positions inside ``blur_deadband_mm`` of the ideal focus
    return a slice bit-identical to the unblurred lateral reference."""
    stage, camera, motors, _ = _make_stage()
    h_mm = stage.sample.light_sheet_x_mm
    _move_h(motors, h_mm)
    ideal_mm = _focus_at_ideal(stage, motors, h_mm)
    f_ref = stage.frame(camera, 0)

    # +0.01 mm: inside the default 0.02 mm deadband even after motor
    # microstep quantization.
    _move_cam(motors, ideal_mm + 0.01)
    f_deadband = stage.frame(camera, 0)
    assert np.array_equal(f_ref, f_deadband), (
        "defocus inside blur_deadband_mm must return the unblurred slice"
    )

    # +0.05 mm: past the deadband but the mapped sigma (~0.15 px) is
    # below the 0.3 px floor, so the slice is still unblurred.
    _move_cam(motors, ideal_mm + 0.05)
    f_subpixel = stage.frame(camera, 0)
    assert np.array_equal(f_ref, f_subpixel), (
        "sub-0.3-px blur sigma must return the unblurred slice"
    )

    # The blur path is reachable: 1 mm defocus changes the frame.
    _move_cam(motors, ideal_mm + 1.0)
    f_blurred = stage.frame(camera, 0)
    assert not np.array_equal(f_ref, f_blurred), (
        "1 mm defocus must apply the Gaussian PSF blur"
    )


def test_mock_stage_lensing_shift_varies_with_h() -> None:
    """The ideal focus plane shifts with axial sample position: the
    Gaussian-bump lensing term peaks at the sample centre and decays
    away from it."""
    stage, _, _, _ = _make_stage()
    sample = stage.sample

    at_centre = stage._ideal_focus_mm(sample.center_x_mm)
    far = stage._ideal_focus_mm(3.0)

    assert at_centre == pytest.approx(
        sample.light_sheet_x_mm + sample.lensing_amplitude_mm
    )
    assert at_centre - far > 0.2, (
        f"lensing shift must decay off-centre: ideal {at_centre:.3f} mm "
        f"at centre vs {far:.3f} mm at h=3.0"
    )


def test_mock_stage_laser_power_scaling() -> None:
    """Frame p99 scales with the active laser's power/max_power; with no
    laser active the frame is dark; the FIRST active laser wins when
    several are present."""
    from lightsheet.hal.mocks.mock_laser import MockLaser

    stage, camera, motors, lasers = _make_stage()
    h_mm = stage.sample.light_sheet_x_mm
    _move_h(motors, h_mm)
    _focus_at_ideal(stage, motors, h_mm)

    full = float(np.percentile(stage.frame(camera, 0), 99))
    lasers[0].set_power(150.0)  # half of max_power 300
    half = float(np.percentile(stage.frame(camera, 0), 99))
    assert half == pytest.approx(full / 2.0, rel=0.05), (
        f"half power must halve the frame: p99 {half} vs {full}"
    )

    # No active laser -> dark frame.
    lasers[0].off()
    assert np.all(stage.frame(camera, 0) == 0.0), (
        "frame must be all-zero when no laser is active"
    )

    # First active laser wins: L0 inactive, L1 active at half power.
    l0 = MockLaser(wavelength=555, max_power_mw=300.0)
    l1 = MockLaser(wavelength=647, max_power_mw=200.0)
    l1.set_power(100.0)  # frac 0.5
    l1.on()
    stage2, camera2, motors2, _ = _make_stage(lasers=(l0, l1))
    _move_h(motors2, h_mm)
    _focus_at_ideal(stage2, motors2, h_mm)
    p_l1 = float(np.percentile(stage2.frame(camera2, 0), 99))
    assert p_l1 == pytest.approx(half, rel=0.05), (
        f"only the active laser drives amplitude: p99 {p_l1} vs {half}"
    )


def test_mock_stage_exposure_time_scaling() -> None:
    """Halving camera.exposure_time roughly halves the frame p99."""
    stage, camera, motors, _ = _make_stage()
    h_mm = stage.sample.light_sheet_x_mm
    _move_h(motors, h_mm)
    _focus_at_ideal(stage, motors, h_mm)

    camera.exposure_time = 0.1
    full = float(np.percentile(stage.frame(camera, 0), 99))
    camera.exposure_time = 0.05
    half = float(np.percentile(stage.frame(camera, 0), 99))
    assert half == pytest.approx(full / 2.0, rel=0.05), (
        f"halving exposure must halve the frame: p99 {half} vs {full}"
    )


def test_mock_stage_brightest_slice_hits_target_band() -> None:
    """At h = light_sheet_x_mm, exposure 0.1 s, full power, the uint16
    frame reconstructed through copy_recorder_images lands in the
    ~0.90-0.95 adaptive target band (asserted as [0.85, 1.0] for
    model-constant headroom)."""
    from lightsheet.adaptive.intensity import frame_intensity_pct

    stage, camera, motors, _ = _make_stage(sensor_shape=(2048, 2048))
    h_mm = stage.sample.light_sheet_x_mm
    _move_h(motors, h_mm)
    _focus_at_ideal(stage, motors, h_mm)
    camera.set_frame_source(stage.frame)
    camera.new_data_ready = True

    imgs = camera.copy_recorder_images(1)
    pct = frame_intensity_pct(imgs[0])
    assert 0.85 <= pct <= 1.0, (
        f"brightest-slice p99 fraction {pct:.3f} must sit near the "
        "0.90-0.95 target band"
    )


def test_mock_stage_determinism() -> None:
    """Two identical frame() calls return bit-equal arrays — the model
    contains no unseeded randomness or time dependence."""
    stage, camera, motors, _ = _make_stage()
    _move_h(motors, 7.0)
    _focus_at_ideal(stage, motors, 7.0)

    a = stage.frame(camera, 0)
    b = stage.frame(camera, 1)
    assert np.array_equal(a, b), "identical state must yield identical frames"


def test_mock_stage_sample_post_init_validation() -> None:
    """MockSample.__post_init__ rejects non-positive sigmas, malformed
    sensor shapes, and invalid focus/texture parameters."""
    from lightsheet.hal.mocks.mock_stage import MockSample

    with pytest.raises(ValueError, match="sigma_x_mm"):
        MockSample(sigma_x_mm=0.0)
    with pytest.raises(ValueError, match="sigma_y_mm"):
        MockSample(sigma_y_mm=-1.0)
    with pytest.raises(ValueError, match="sensor_shape"):
        MockSample(sensor_shape=(512,))  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]
    with pytest.raises(ValueError, match="sensor_shape"):
        MockSample(sensor_shape=(512, 0))
    with pytest.raises(ValueError, match="pixel_size_um"):
        MockSample(pixel_size_um=0.0)
    with pytest.raises(ValueError, match="light_sheet_fwhm_um"):
        MockSample(light_sheet_fwhm_um=-1.0)
    with pytest.raises(ValueError, match="lensing_sigma_mm"):
        MockSample(lensing_sigma_mm=0.0)
    with pytest.raises(ValueError, match="texture_period_px"):
        MockSample(texture_period_px=-4.0)
    with pytest.raises(ValueError, match="defocus_scale"):
        MockSample(defocus_scale=-0.1)


def test_mock_stage_dark_frame_with_no_lasers() -> None:
    """An empty lasers tuple and an active laser with max_power <= 0
    both yield a zero frame (the _active_power_fraction guards)."""
    stage, camera, motors, _ = _make_stage(lasers=())
    _move_h(motors, stage.sample.light_sheet_x_mm)
    assert np.all(stage.frame(camera, 0) == 0.0)

    from lightsheet.hal.mocks.mock_laser import MockLaser

    dead = MockLaser(wavelength=555, max_power_mw=0.0)
    dead.on()
    stage2, camera2, motors2, _ = _make_stage(lasers=(dead,))
    _move_h(motors2, stage2.sample.light_sheet_x_mm)
    assert np.all(stage2.frame(camera2, 0) == 0.0)


def test_mock_stage_missing_exposure_attribute_is_dark() -> None:
    """A camera without an exposure_time attribute falls back to 0.0 s,
    producing a zero frame rather than raising."""
    stage, _, motors, _ = _make_stage()
    _move_h(motors, stage.sample.light_sheet_x_mm)
    assert np.all(stage.frame(object(), 0) == 0.0)


def test_mock_stage_make_bundle_isolation() -> None:
    """make_bundle() keeps camera.frame_source is None — the stage is
    opt-in and never attached by the shared test factory."""
    from test.helpers.factories import make_bundle

    bundle = make_bundle()
    assert bundle.camera.frame_source is None  # ty: ignore[unresolved-attribute]
