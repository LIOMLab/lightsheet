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

import pytest

from lightsheet.config import cfg_read, cfg_str2bool, cfg_write


def test_cfg_read_updates_defaults(tmp_path) -> None:
    """cfg_read returns the defaults dict with values updated from the ini."""
    ini = tmp_path / "test.ini"
    ini.write_text("[HwDAQ]\nSample Rate = 20000\n", encoding="utf-8")
    defaults = {"Sample Rate": "10000", "Galvo Left Amplitude": "2"}
    out = cfg_read(str(ini), "HwDAQ", defaults)
    assert out["Sample Rate"] == "20000"          # updated from ini
    assert out["Galvo Left Amplitude"] == "2"     # unchanged (not in ini)


def test_cfg_read_ignores_extraneous_keys(tmp_path) -> None:
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


def test_cfg_read_missing_section_returns_defaults(tmp_path) -> None:
    """EDGE: section absent from ini → defaults returned unchanged."""
    ini = tmp_path / "test.ini"
    ini.write_text("[OtherSection]\nFoo = bar\n", encoding="utf-8")
    defaults = {"Sample Rate": "10000"}
    out = cfg_read(str(ini), "HwDAQ", defaults)
    assert out == {"Sample Rate": "10000"}


def test_cfg_read_preserves_case(tmp_path) -> None:
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


def test_cfg_write_updates_without_erasing(tmp_path) -> None:
    """cfg_write writes/updates keys without erasing others in the section."""
    ini = tmp_path / "test.ini"
    cfg_write(str(ini), "HwDAQ", {"Key A": "1"})
    cfg_write(str(ini), "HwDAQ", {"Key B": "2"})
    # Both keys must survive the second write.
    out = cfg_read(str(ini), "HwDAQ", {"Key A": "", "Key B": ""})
    assert out["Key A"] == "1"
    assert out["Key B"] == "2"


def test_cfg_write_creates_section(tmp_path) -> None:
    """cfg_write creates the section if it does not exist."""
    ini = tmp_path / "test.ini"
    ini.write_text("[Other]\nX = 1\n", encoding="utf-8")
    cfg_write(str(ini), "NewSection", {"Foo": "bar"})
    out = cfg_read(str(ini), "NewSection", {"Foo": ""})
    assert out["Foo"] == "bar"


@pytest.mark.parametrize("value", ["true", "t", "yes", "1",
                                   "True", "TRUE", "Yes", "YES"])
def test_cfg_str2bool_true_cases(value: str) -> None:
    """cfg_str2bool returns True for the true-word set (case-insensitive)."""
    assert cfg_str2bool(value) is True


@pytest.mark.parametrize("value", ["false", "f", "no", "0",
                                   "False", "FALSE", "No", "NO", ""])
def test_cfg_str2bool_false_cases(value: str) -> None:
    """cfg_str2bool returns False for anything outside the true-word set."""
    assert cfg_str2bool(value) is False
