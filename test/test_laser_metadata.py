"""FrameSaver file-level HDF5 laser metadata tests (LSD-03).

Verifies that FrameSaver._write_laser_metadata writes the five per-laser
root attrs (Wavelength / Power / Max Power / Active / Label) once per
file, for ALL configured lasers (including inactive ones with power=0 /
active=False), read from the live list[ILaser] the controller holds —
never re-parsed from config.ini (fixes the config-drift metadata bug).

The real FrameSaver is constructed via ``make_controller`` (which builds
the full ``Controller_MainWindow`` with all collaborators wired and
``hardware_init`` already called). The real FrameSaver lives at
``ctrl._fs.frame_saver`` and its ``.parent`` is the controller, which
holds ``ctrl.lasers`` (the live list[ILaser]). This exercises the real
method on the real object — the same code that runs on the rig.
"""

import h5py
import pytest

from _helpers.controller_fixture import make_controller
from lightsheet.hal.mocks.mock_laser import MockLaser


def test_write_laser_metadata_writes_all_five_attrs_per_laser(
    qtbot, request, tmp_path
) -> None:
    """_write_laser_metadata writes Wavelength / Power / Max Power / Active
    / Label as h5py.File ROOT attrs once per file, for ALL configured
    lasers (one active, one inactive). The attrs round-trip correctly
    through h5py.File(path, 'r')."""
    ctrl, _ = make_controller(qtbot, request)

    # Make laser 1 active with a staged power; laser 2 stays inactive.
    ctrl.lasers[0].active = True
    ctrl.lasers[0].power = 150.0

    outfile_path = tmp_path / "test_meta.hdf5"
    with h5py.File(outfile_path, "a") as outfile:
        ctrl._fs.frame_saver._write_laser_metadata(outfile)

    with h5py.File(outfile_path, "r") as f:
        # Laser 1 (active, 150 mW staged, 555 nm, 300 mW max)
        assert f.attrs["Laser1 Wavelength"] == 555
        assert f.attrs["Laser1 Power"] == 150.0
        assert f.attrs["Laser1 Max Power"] == 300.0
        assert f.attrs["Laser1 Active"] == True
        assert f.attrs["Laser1 Label"] == "Laser 1 (555 nm)"

        # Laser 2 (inactive, 0 mW, 647 nm, 150 mW max) — included even
        # though it did not fire (reproducibility context).
        assert f.attrs["Laser2 Wavelength"] == 647
        assert f.attrs["Laser2 Power"] == 0.0
        assert f.attrs["Laser2 Max Power"] == 150.0
        assert f.attrs["Laser2 Active"] == False
        assert f.attrs["Laser2 Label"] == "Laser 2 (647 nm)"


def test_write_laser_metadata_includes_inactive_laser(
    qtbot, request, tmp_path
) -> None:
    """An inactive laser (active=False, power=0) is NOT skipped — its
    attrs are written with whatever the live instance holds. This is the
    reproducibility contract: 'which lasers were configured but did not
    fire' is metadata context."""
    ctrl, _ = make_controller(qtbot, request)

    # Both inactive — neither fired.
    ctrl.lasers[0].active = False
    ctrl.lasers[1].active = False

    outfile_path = tmp_path / "test_inactive.hdf5"
    with h5py.File(outfile_path, "a") as outfile:
        ctrl._fs.frame_saver._write_laser_metadata(outfile)

    with h5py.File(outfile_path, "r") as f:
        # Both lasers present in the metadata even though neither fired.
        assert "Laser1 Wavelength" in f.attrs
        assert "Laser2 Wavelength" in f.attrs
        assert f.attrs["Laser1 Active"] == False
        assert f.attrs["Laser2 Active"] == False
        assert f.attrs["Laser1 Power"] == 0.0
        assert f.attrs["Laser2 Power"] == 0.0


def test_write_laser_metadata_reads_live_instance_not_config(
    qtbot, request, tmp_path
) -> None:
    """The metadata values match the live ILaser instance state at save
    time, not a config.ini value. If the live instance's power was
    changed at runtime (e.g. via set_power), the saved attr reflects the
    live value, not the config default."""
    ctrl, _ = make_controller(qtbot, request)

    # Replace the controller's laser list with a single laser whose live
    # state has been mutated after construction — the saved metadata must
    # reflect this mutation, not a config-parsed default. Restore the
    # original 2-laser list afterwards so teardown's closeEvent (which
    # accesses self.lasers[1]) does not IndexError.
    single_laser = MockLaser(
        wavelength=555,
        max_power_mw=300.0,
        label="Laser 1 (555 nm)",
    )
    single_laser.power = 42.0
    single_laser.active = True
    original_lasers = list(ctrl.lasers)
    try:
        ctrl.lasers = [single_laser]

        outfile_path = tmp_path / "test_live.hdf5"
        with h5py.File(outfile_path, "a") as outfile:
            ctrl._fs.frame_saver._write_laser_metadata(outfile)

        with h5py.File(outfile_path, "r") as f:
            assert f.attrs["Laser1 Power"] == 42.0
            assert f.attrs["Laser1 Active"] == True
    finally:
        ctrl.lasers = original_lasers


# --------------------------------------------------------------------------- #
# SAV-03: motor + scan-param root attrs (the motor + scan-param half of
# the config-drift metadata fix; the laser half shipped in Phase 4 D-04).
#
# ``_write_acquisition_metadata`` writes the motor positions + scan params
# + camera params as HDF5 root attrs, read from the live controller
# instances (no config re-parse). The attr names mirror the Zarr
# /acquisition group from the sibling ZarrSaver plan so both formats
# carry the same provenance.
# --------------------------------------------------------------------------- #


def test_motor_and_scan_params_in_hdf5_metadata(
    qtbot, request, tmp_path
) -> None:
    """SAV-03: ``_write_acquisition_metadata`` writes the motor positions
    (horizontal/vertical/camera) + scan params (galvo/ETL amplitudes +
    offsets, sample rate) + camera params (exposure, shutter mode,
    binning, x/y size) as HDF5 root attrs, matching the live
    ``ctrl.motors`` / ``ctrl.siggen`` / ``ctrl.camera`` values."""
    ctrl, _ = make_controller(qtbot, request)

    outfile_path = tmp_path / "test_motor_meta.hdf5"
    with h5py.File(outfile_path, "a") as outfile:
        ctrl._fs.frame_saver._write_laser_metadata(outfile)
        ctrl._fs.frame_saver._write_acquisition_metadata(outfile)

    with h5py.File(outfile_path, "r") as f:
        # Motor position root attrs — current snapshot from live motors.
        assert f.attrs["Horizontal Position"] == ctrl.motors.horizontal.get_position("mm")
        assert f.attrs["Vertical Position"] == ctrl.motors.vertical.get_position("mm")
        assert f.attrs["Camera Position"] == ctrl.motors.camera.get_position("mm")
        # Scan-parameter root attrs from the live siggen.
        assert f.attrs["Galvo Left Amplitude"] == ctrl.siggen.galvo_left_amplitude
        assert f.attrs["Galvo Right Amplitude"] == ctrl.siggen.galvo_right_amplitude
        assert f.attrs["Galvo Left Offset"] == ctrl.siggen.galvo_left_offset
        assert f.attrs["Galvo Right Offset"] == ctrl.siggen.galvo_right_offset
        assert f.attrs["ETL Left Amplitude"] == ctrl.siggen.etl_left_amplitude
        assert f.attrs["ETL Right Amplitude"] == ctrl.siggen.etl_right_amplitude
        assert f.attrs["ETL Left Offset"] == ctrl.siggen.etl_left_offset
        assert f.attrs["ETL Right Offset"] == ctrl.siggen.etl_right_offset
        assert f.attrs["Sample Rate"] == ctrl.siggen.sample_rate
        # Camera params from the live camera.
        assert f.attrs["Exposure Time (s)"] == ctrl.camera.exposure_time
        assert f.attrs["Shutter Mode"] == ctrl.camera.shutter_mode
        assert f.attrs["Binning X"] == ctrl.camera.binning_x
        assert f.attrs["Binning Y"] == ctrl.camera.binning_y
        assert f.attrs["X Size"] == ctrl.camera.xsize
        assert f.attrs["Y Size"] == ctrl.camera.ysize


def test_no_config_reparse(qtbot, request, tmp_path) -> None:
    """SAV-03: the motor-position root attr reflects the LIVE motor value,
    not a config-parsed default. Mutating a siggen amplitude after
    construction is reflected in the saved attr — the saver reads the live
    instance, never re-parses config.ini at save time (the config-drift
    bug this fixes)."""
    ctrl, _ = make_controller(qtbot, request)

    # Mutate a siggen amplitude after construction — the saved attr must
    # reflect the live mutated value, not the config default.
    original = ctrl.siggen.galvo_left_amplitude
    try:
        ctrl.siggen.galvo_left_amplitude = original + 0.123
        outfile_path = tmp_path / "test_no_reparse.hdf5"
        with h5py.File(outfile_path, "a") as outfile:
            ctrl._fs.frame_saver._write_laser_metadata(outfile)
            ctrl._fs.frame_saver._write_acquisition_metadata(outfile)

        with h5py.File(outfile_path, "r") as f:
            assert f.attrs["Galvo Left Amplitude"] == original + 0.123
    finally:
        ctrl.siggen.galvo_left_amplitude = original
