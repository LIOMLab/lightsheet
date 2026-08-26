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
