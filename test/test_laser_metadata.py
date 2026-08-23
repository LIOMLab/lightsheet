"""FrameSaver file-level HDF5 laser metadata tests (LSD-03).

Verifies that FrameSaver._write_laser_metadata writes the five per-laser
root attrs (Wavelength / Power / Max Power / Active / Label) once per
file, for ALL configured lasers (including inactive ones with power=0 /
active=False), read from the live list[ILaser] the controller holds —
never re-parsed from config.ini (fixes the config-drift metadata bug).

FrameSaver inherits QObject and cannot be constructed without PyQt5, so
the real _write_laser_metadata method body is extracted from
lightsheet/gui/frame_saver_controller.py (where FrameSaver is defined
after the god-object split) and exec'd in a controlled namespace, then
called against a minimal stand-in self whose .parent.lasers holds the
live list[ILaser]. This exercises the real method body — the same code
that runs on the rig — without needing the Qt runtime.
"""

import h5py
import os
import re
from types import SimpleNamespace
from unittest.mock import Mock

from lightsheet.hal.mocks.mock_laser import MockLaser

_FRAME_SAVER_SRC = os.path.join(
    os.path.dirname(__file__), "..", "lightsheet", "gui", "frame_saver_controller.py"
)


def _read_controller_source() -> str:
    with open(_FRAME_SAVER_SRC, encoding="utf-8") as f:
        return f.read()


def _slice_method(src: str, method_sig: str) -> str:
    """Return the body of a method, from its `def <sig>:` line up to the
    next top-level def / @pyqtSlot / class boundary."""
    m = re.search(r"def " + re.escape(method_sig) + r":", src)
    assert m, f"{method_sig} is missing"
    body = src[m.start():]
    # Stop at the next method def at the same indent (4 spaces) or a
    # class-level boundary (no indent).
    end = re.search(r"\n    def |\n    @pyqtSlot|\nclass ", body[1:])
    if end:
        body = body[: end.start() + 1]
    return body


def _load_method(method_sig: str):
    """Extract a method body from lightsheet/gui/frame_saver_controller.py
    and return a callable `func(self, outfile)` that executes the real
    source."""
    src = _read_controller_source()
    body = _slice_method(src, method_sig)
    # Seed the exec namespace with modules the method body references
    # (the type hint `h5py.File` is evaluated at function definition time
    # inside the exec — h5py must be present in the namespace).
    namespace = {"h5py": h5py}
    exec(compile(body, _FRAME_SAVER_SRC, "exec"), namespace)
    func_name = method_sig.split("(")[0].strip()
    return namespace[func_name]


def _make_standin(lasers: list) -> Mock:
    """Build a stand-in self for _write_laser_metadata. The method reads
    self.parent.lasers (the live list[ILaser])."""
    standin = Mock()
    standin.parent = SimpleNamespace(lasers=lasers)
    return standin


def test_write_laser_metadata_writes_all_five_attrs_per_laser(
    tmp_path,
) -> None:
    """_write_laser_metadata writes Wavelength / Power / Max Power / Active
    / Label as h5py.File ROOT attrs once per file, for ALL configured
    lasers (one active, one inactive). The attrs round-trip correctly
    through h5py.File(path, 'r')."""
    write_meta = _load_method(
        "_write_laser_metadata(self, outfile: h5py.File) -> None"
    )

    lasers = [
        MockLaser(
            wavelength=555,
            max_power_mw=300.0,
            mw_per_volt=60.0,
            label="Laser 1 (555 nm)",
        ),
        MockLaser(
            wavelength=640,
            max_power_mw=150.0,
            label="Laser 2 (640 nm)",
        ),
    ]
    # Make laser 1 active with a staged power; laser 2 stays inactive.
    lasers[0].active = True
    lasers[0].power = 150.0

    standin = _make_standin(lasers)

    outfile_path = tmp_path / "test_meta.hdf5"
    with h5py.File(outfile_path, "a") as outfile:
        write_meta(standin, outfile)

    with h5py.File(outfile_path, "r") as f:
        # Laser 1 (active, 150 mW staged, 555 nm, 300 mW max)
        assert f.attrs["Laser1 Wavelength"] == 555
        assert f.attrs["Laser1 Power"] == 150.0
        assert f.attrs["Laser1 Max Power"] == 300.0
        assert f.attrs["Laser1 Active"] == True
        assert f.attrs["Laser1 Label"] == "Laser 1 (555 nm)"

        # Laser 2 (inactive, 0 mW, 640 nm, 150 mW max) — included even
        # though it did not fire (reproducibility context).
        assert f.attrs["Laser2 Wavelength"] == 640
        assert f.attrs["Laser2 Power"] == 0.0
        assert f.attrs["Laser2 Max Power"] == 150.0
        assert f.attrs["Laser2 Active"] == False
        assert f.attrs["Laser2 Label"] == "Laser 2 (640 nm)"


def test_write_laser_metadata_includes_inactive_laser(tmp_path) -> None:
    """An inactive laser (active=False, power=0) is NOT skipped — its
    attrs are written with whatever the live instance holds. This is the
    reproducibility contract: 'which lasers were configured but did not
    fire' is metadata context."""
    write_meta = _load_method(
        "_write_laser_metadata(self, outfile: h5py.File) -> None"
    )

    lasers = [
        MockLaser(
            wavelength=555,
            max_power_mw=300.0,
            label="Laser 1 (555 nm)",
        ),
        MockLaser(
            wavelength=640,
            max_power_mw=150.0,
            label="Laser 2 (640 nm)",
        ),
    ]
    # Both inactive — neither fired.
    lasers[0].active = False
    lasers[1].active = False

    standin = _make_standin(lasers)

    outfile_path = tmp_path / "test_inactive.hdf5"
    with h5py.File(outfile_path, "a") as outfile:
        write_meta(standin, outfile)

    with h5py.File(outfile_path, "r") as f:
        # Both lasers present in the metadata even though neither fired.
        assert "Laser1 Wavelength" in f.attrs
        assert "Laser2 Wavelength" in f.attrs
        assert f.attrs["Laser1 Active"] == False
        assert f.attrs["Laser2 Active"] == False
        assert f.attrs["Laser1 Power"] == 0.0
        assert f.attrs["Laser2 Power"] == 0.0


def test_write_laser_metadata_reads_live_instance_not_config(
    tmp_path,
) -> None:
    """The metadata values match the live ILaser instance state at save
    time, not a config.ini value. If the live instance's power was
    changed at runtime (e.g. via set_power), the saved attr reflects the
    live value, not the config default."""
    write_meta = _load_method(
        "_write_laser_metadata(self, outfile: h5py.File) -> None"
    )

    lasers = [
        MockLaser(
            wavelength=555,
            max_power_mw=300.0,
            label="Laser 1 (555 nm)",
        ),
    ]
    # Mutate the live instance after construction — the saved metadata
    # must reflect this mutation, not a config-parsed default.
    lasers[0].power = 42.0
    lasers[0].active = True

    standin = _make_standin(lasers)

    outfile_path = tmp_path / "test_live.hdf5"
    with h5py.File(outfile_path, "a") as outfile:
        write_meta(standin, outfile)

    with h5py.File(outfile_path, "r") as f:
        assert f.attrs["Laser1 Power"] == 42.0
        assert f.attrs["Laser1 Active"] == True
