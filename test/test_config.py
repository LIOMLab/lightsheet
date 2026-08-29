"""
TST-02 pure-logic characterization tests for lightsheet.config.

Captures today's behavior of the configparser helpers (cfg_read /
cfg_write / cfg_str2bool) so the Phase 5 god-object split and Phase 7
Qt6 migration cannot silently change the config contract: case-sensitive
keys (cfg.optionxform = str), cfg_read ignores extraneous keys, cfg_write
updates without erasing, cfg_str2bool's true-word set.

Tests execute the real helpers against tmp_path ini files (AGENTS.md §5).
Mirrors test/test_gaussian.py style: direct import, single-assert tests.
"""

from pathlib import Path

import pytest

from lightsheet.config import cfg_read, cfg_str2bool, cfg_write


def test_cfg_read_updates_defaults(tmp_path: Path) -> None:
    """cfg_read returns the defaults dict with values updated from the ini."""
    ini = tmp_path / "test.ini"
    ini.write_text("[HwDAQ]\nSample Rate = 20000\n", encoding="utf-8")
    defaults = {"Sample Rate": "10000", "Galvo Left Amplitude": "2"}
    out = cfg_read(str(ini), "HwDAQ", defaults)
    assert out["Sample Rate"] == "20000"  # updated from ini
    assert out["Galvo Left Amplitude"] == "2"  # unchanged (not in ini)


def test_cfg_read_ignores_extraneous_keys(tmp_path: Path) -> None:
    """cfg_read only updates keys present in defaults_dict — extraneous ini
    keys are ignored (never added to the returned dict)."""
    ini = tmp_path / "test.ini"
    ini.write_text(
        "[HwDAQ]\nSample Rate = 20000\nUnknown Key = surprise\n",
        encoding="utf-8",
    )
    defaults = {"Sample Rate": "10000"}
    out = cfg_read(str(ini), "HwDAQ", defaults)
    assert "Unknown Key" not in out
    assert out == {"Sample Rate": "20000"}


def test_cfg_read_missing_section_returns_defaults(tmp_path: Path) -> None:
    """EDGE: section absent from ini → defaults returned unchanged."""
    ini = tmp_path / "test.ini"
    ini.write_text("[OtherSection]\nFoo = bar\n", encoding="utf-8")
    defaults = {"Sample Rate": "10000"}
    out = cfg_read(str(ini), "HwDAQ", defaults)
    assert out == {"Sample Rate": "10000"}


def test_cfg_read_preserves_case(tmp_path: Path) -> None:
    """cfg_read uses cfg.optionxform = str — INI keys keep their case
    (AGENTS.md §9). A Title Case key in the ini updates the matching
    Title Case key in defaults; lowercasing would break the match."""
    ini = tmp_path / "test.ini"
    ini.write_text("[HwDAQ]\nGalvo Left Amplitude = 3.5\n", encoding="utf-8")
    defaults = {"Galvo Left Amplitude": "2"}
    out = cfg_read(str(ini), "HwDAQ", defaults)
    assert out["Galvo Left Amplitude"] == "3.5"
    # The original Title Case key is present, not a lowercased variant.
    assert "Galvo Left Amplitude" in out


def test_cfg_write_updates_without_erasing(tmp_path: Path) -> None:
    """cfg_write writes/updates keys without erasing others in the section."""
    ini = tmp_path / "test.ini"
    cfg_write(str(ini), "HwDAQ", {"Key A": "1"})
    cfg_write(str(ini), "HwDAQ", {"Key B": "2"})
    # Both keys must survive the second write.
    out = cfg_read(str(ini), "HwDAQ", {"Key A": "", "Key B": ""})
    assert out["Key A"] == "1"
    assert out["Key B"] == "2"


def test_cfg_write_creates_section(tmp_path: Path) -> None:
    """cfg_write creates the section if it does not exist."""
    ini = tmp_path / "test.ini"
    ini.write_text("[Other]\nX = 1\n", encoding="utf-8")
    cfg_write(str(ini), "NewSection", {"Foo": "bar"})
    out = cfg_read(str(ini), "NewSection", {"Foo": ""})
    assert out["Foo"] == "bar"


@pytest.mark.parametrize(
    "value", ["true", "t", "yes", "1", "True", "TRUE", "Yes", "YES"]
)
def test_cfg_str2bool_true_cases(value: str) -> None:
    """cfg_str2bool returns True for the true-word set (case-insensitive)."""
    assert cfg_str2bool(value) is True


@pytest.mark.parametrize(
    "value", ["false", "f", "no", "0", "False", "FALSE", "No", "NO", ""]
)
def test_cfg_str2bool_false_cases(value: str) -> None:
    """cfg_str2bool returns False for anything outside the true-word set."""
    assert cfg_str2bool(value) is False


# --------------------------------------------------------------------------- #
# D-03: Image File Format enum. ``Image File Format`` is an enum accepting
# hdf5 / zarr / both / tiff (case-insensitive) and rejecting unknown values
# with a validation error at startup (the PKG-04 collect-all gate).
# --------------------------------------------------------------------------- #


def test_image_file_format_enum(tmp_path: Path) -> None:
    """D-03: ``Image File Format`` accepts the four documented values
    (hdf5 / zarr / both / tiff, case-insensitive) and rejects unknown
    values with a ValidationError. The rig's current "HDF5" stays valid."""
    from pydantic import ValidationError

    from lightsheet.config import cfg_read
    from lightsheet.config_schema import (
        ControllerSettings,
        ControllerSettingsOverlay,
    )

    # cfg_read uses the defaults dict keys (case-sensitive) to capture ini
    # values; the alias keys match the Field aliases on the model.
    defaults = {"Image File Format": "both", "Units": "mm"}

    # Valid values — accepted by BOTH tiers (strict + overlay in sync).
    for fmt in ("hdf5", "zarr", "both", "tiff"):
        ini = tmp_path / f"test_{fmt}.ini"
        ini.write_text(
            f"[Controller]\nImage File Format = {fmt}\nUnits = mm\n",
            encoding="utf-8",
        )
        data = cfg_read(str(ini), "Controller", dict(defaults))
        settings = ControllerSettings(**data)
        assert settings.image_file_format == fmt
        overlay = ControllerSettingsOverlay(**data)
        assert overlay.image_file_format == fmt

    # Case-insensitivity: the rig's Title-Case "HDF5" stays valid.
    ini_hdf5 = tmp_path / "test_HDF5_upper.ini"
    ini_hdf5.write_text(
        "[Controller]\nImage File Format = HDF5\nUnits = mm\n",
        encoding="utf-8",
    )
    data = cfg_read(str(ini_hdf5), "Controller", dict(defaults))
    assert ControllerSettings(**data).image_file_format == "hdf5"

    # Unknown value is rejected with a validation error (both tiers).
    bad_ini = tmp_path / "test_bad.ini"
    bad_ini.write_text(
        "[Controller]\nImage File Format = fits\nUnits = mm\n",
        encoding="utf-8",
    )
    data = cfg_read(str(bad_ini), "Controller", dict(defaults))
    with pytest.raises(ValidationError):
        ControllerSettings(**data)
    with pytest.raises(ValidationError):
        ControllerSettingsOverlay(**data)


def test_image_file_format_missing_key_defaults_to_hdf5(tmp_path: Path) -> None:
    """Regression: when ``Image File Format`` is absent from config.ini,
    ``load_sections_from_ini`` builds the cfg_read defaults dict with "" for
    every alias, so the key arrives at the model as "" (not as a missing
    kwarg). The pydantic ``default="both"`` never fires for that path; the
    before-validator must map the "" sentinel to the operator-facing default
    "hdf5" (matching ``controller._cfg_defaults`` and the rig's historical
    behavior) instead of letting the Literal reject it. This is the
    startup-blocker root cause — a config.ini without the key must validate
    clean, not abort startup with "Input should be one of ..."."""
    from lightsheet.config import cfg_read
    from lightsheet.config_schema import (
        ControllerSettings,
        ControllerSettingsOverlay,
    )

    # cfg_read defaults dict mirrors load_sections_from_ini: every alias
    # seeded with "" so absent keys return "" (the sentinel under test).
    defaults = {"Image File Format": "", "Units": "mm"}

    # config.ini with NO Image File Format line — the rig's actual state.
    ini = tmp_path / "no_format_key.ini"
    ini.write_text("[Controller]\nUnits = mm\n", encoding="utf-8")
    data = cfg_read(str(ini), "Controller", dict(defaults))
    assert data["Image File Format"] == ""  # sentinel, not a real value

    # Both tiers resolve the empty sentinel to "hdf5" — no ValidationError.
    assert ControllerSettings(**data).image_file_format == "hdf5"
    assert ControllerSettingsOverlay(**data).image_file_format == "hdf5"

    # End-to-end: the real startup gate path must not surface an error.
    from lightsheet.config_schema import collect_config_errors

    sections = {"Controller": data}
    result = collect_config_errors(sections)
    assert not result.errors
