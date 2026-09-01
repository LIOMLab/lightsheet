"""Branch coverage for ``lightsheet.hal.registry``.

Exercises ``_parse_calibration_curve`` (empty, valid, malformed, non-numeric,
wrong-arity entries) and ``DeviceRegistry._resolve_ports`` (serial-numbered
match/miss, null-serial config-port match, single-candidate, zero-candidate,
multi-candidate ambiguous, motherboard-skip, vid-None skip).

The ``resolve()`` method constructs real HAL classes (Camera, SigGen, Motors,
ETLs, DAQLaser, IBeamSmartLaser) and is only callable on the rig — it is
covered by the rig-side ``LIGHTSHEET_HW=1`` run, not here.

Behavior tests (AGENTS.md §5) — every assertion is on a runtime
postcondition (returned dict, raised UnresolvedDeviceError with expected
message), never a static-source grep.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from lightsheet.hal.registry import (
    DeviceRegistry,
    UnresolvedDeviceError,
    _parse_calibration_curve,
)

# -- _parse_calibration_curve -----------------------------------------------


def test_parse_calibration_curve_empty_returns_none() -> None:
    """Empty string -> None (no curve, linear mode)."""
    assert _parse_calibration_curve("") is None


def test_parse_calibration_curve_whitespace_only_returns_none() -> None:
    """Whitespace-only string -> None."""
    assert _parse_calibration_curve("   ") is None


def test_parse_calibration_curve_valid_pairs() -> None:
    """Valid semicolon-separated V,mW pairs -> list of tuples."""
    result = _parse_calibration_curve("0,0;0.8,0;1.5,30;5,236.6")
    assert result == [(0.0, 0.0), (0.8, 0.0), (1.5, 30.0), (5.0, 236.6)]


def test_parse_calibration_curve_whitespace_tolerated() -> None:
    """Whitespace around pairs and the comma is tolerated."""
    result = _parse_calibration_curve(" 0 , 0 ; 5 , 236.6 ")
    assert result == [(0.0, 0.0), (5.0, 236.6)]


def test_parse_calibration_curve_empty_chunks_skipped() -> None:
    """Empty chunks (from leading/trailing/double semicolons) are skipped."""
    result = _parse_calibration_curve(";0,0;;5,236.6;")
    assert result == [(0.0, 0.0), (5.0, 236.6)]


def test_parse_calibration_curve_only_empty_chunks_returns_none() -> None:
    """All chunks empty -> None (no valid pairs)."""
    assert _parse_calibration_curve(";;;") is None


def test_parse_calibration_curve_wrong_arity_returns_none() -> None:
    """A entry with != 2 parts rejects the whole curve -> None."""
    assert _parse_calibration_curve("0,0,0;5,236.6") is None
    assert _parse_calibration_curve("0;5,236.6") is None


def test_parse_calibration_curve_non_numeric_returns_none() -> None:
    """Non-numeric values reject the whole curve -> None."""
    assert _parse_calibration_curve("0,abc;5,236.6") is None
    assert _parse_calibration_curve("xyz,0;5,236.6") is None


# -- DeviceRegistry._resolve_ports ------------------------------------------


def _make_port(
    device: str,
    vid: int | None,
    pid: int | None,
    serial_number: str | None = None,
) -> Mock:
    """Build a mock ListPortInfo object."""
    p = Mock()
    p.device = device
    p.vid = vid
    p.pid = pid
    p.serial_number = serial_number
    return p


def _make_registry(inventory: dict, tmp_path: Path) -> DeviceRegistry:  # ty: ignore[missing-type-argument]
    """Build a DeviceRegistry with a mock inventory YAML."""
    import yaml

    inv_path = tmp_path / "hardware_inventory.yaml"
    with inv_path.open("w") as f:
        yaml.safe_dump(inventory, f)
    config_path = tmp_path / "config.ini"
    # Write a minimal config.ini with a [Motors] Port.
    with config_path.open("w") as f:
        f.write("[Motors]\nPort = COM7\n")
    return DeviceRegistry(str(inv_path), str(config_path))


def test_resolve_ports_serial_numbered_match(tmp_path: Path) -> None:
    """A serial-numbered device matching (vid, pid, sn) resolves to its port."""
    inv = {
        "devices": {
            "serial_devices": [
                {
                    "role": "etl_left",
                    "vid_pid": "10C4:EA60",
                    "serial_number": "AB1234",
                },
            ]
        }
    }
    reg = _make_registry(inv, tmp_path)
    ports = [_make_port("COM5", 0x10C4, 0xEA60, "AB1234")]
    with patch(
        "lightsheet.hal.registry.serial.tools.list_ports.comports",
        return_value=ports,
    ):
        result = reg._resolve_ports()
    assert result == {"etl_left": "COM5"}


def test_resolve_ports_serial_numbered_miss_raises(tmp_path: Path) -> None:
    """A serial-numbered device not on the bus raises UnresolvedDeviceError."""
    inv = {
        "devices": {
            "serial_devices": [
                {
                    "role": "etl_left",
                    "vid_pid": "10C4:EA60",
                    "serial_number": "AB1234",
                },
            ]
        }
    }
    reg = _make_registry(inv, tmp_path)
    ports = []  # No ports at all
    with (
        patch(
            "lightsheet.hal.registry.serial.tools.list_ports.comports",
            return_value=ports,
        ),
        pytest.raises(UnresolvedDeviceError) as exc_info,
    ):
        reg._resolve_ports()
    assert "etl_left" in str(exc_info.value)
    assert "not found" in str(exc_info.value)


def test_resolve_ports_null_serial_config_port_match(tmp_path: Path) -> None:
    """A null-serial device matching config.ini [Motors] Port resolves."""
    inv = {
        "devices": {
            "serial_devices": [
                {
                    "role": "motors",
                    "vid_pid": "067B:2303",
                    "serial_number": None,
                },
            ]
        }
    }
    reg = _make_registry(inv, tmp_path)
    # Two candidates with the same vid/pid, but COM7 matches config.ini.
    ports = [
        _make_port("COM7", 0x067B, 0x2303, None),
        _make_port("COM8", 0x067B, 0x2303, None),
    ]
    with patch(
        "lightsheet.hal.registry.serial.tools.list_ports.comports",
        return_value=ports,
    ):
        result = reg._resolve_ports()
    assert result == {"motors": "COM7"}


def test_resolve_ports_null_serial_single_candidate(tmp_path: Path) -> None:
    """A null-serial device with exactly one candidate resolves to it
    (the elif len(candidates) == 1 branch, line 186)."""
    inv = {
        "devices": {
            "serial_devices": [
                {
                    "role": "motors",
                    "vid_pid": "067B:2303",
                    "serial_number": None,
                },
            ]
        }
    }
    reg = _make_registry(inv, tmp_path)
    # One candidate, but config.ini says COM7 and the candidate is COM3.
    # Since there's only one candidate, it resolves to COM3.
    ports = [_make_port("COM3", 0x067B, 0x2303, None)]
    with patch(
        "lightsheet.hal.registry.serial.tools.list_ports.comports",
        return_value=ports,
    ):
        result = reg._resolve_ports()
    assert result == {"motors": "COM3"}


def test_resolve_ports_null_serial_zero_candidates_raises(tmp_path: Path) -> None:
    """A null-serial device with no candidates raises UnresolvedDeviceError."""
    inv = {
        "devices": {
            "serial_devices": [
                {
                    "role": "motors",
                    "vid_pid": "067B:2303",
                    "serial_number": None,
                },
            ]
        }
    }
    reg = _make_registry(inv, tmp_path)
    ports = []
    with (
        patch(
            "lightsheet.hal.registry.serial.tools.list_ports.comports",
            return_value=ports,
        ),
        pytest.raises(UnresolvedDeviceError) as exc_info,
    ):
        reg._resolve_ports()
    assert "motors" in str(exc_info.value)
    assert "no match" in str(exc_info.value)


def test_resolve_ports_null_serial_multi_candidates_no_config_match_raises(
    tmp_path: Path,
) -> None:
    """A null-serial device with 2+ candidates, none matching config.ini,
    raises UnresolvedDeviceError (ambiguous — strict abort)."""
    inv = {
        "devices": {
            "serial_devices": [
                {
                    "role": "motors",
                    "vid_pid": "067B:2303",
                    "serial_number": None,
                },
            ]
        }
    }
    reg = _make_registry(inv, tmp_path)
    # Two candidates, neither is COM7 (config.ini port).
    ports = [
        _make_port("COM3", 0x067B, 0x2303, None),
        _make_port("COM8", 0x067B, 0x2303, None),
    ]
    with (
        patch(
            "lightsheet.hal.registry.serial.tools.list_ports.comports",
            return_value=ports,
        ),
        pytest.raises(UnresolvedDeviceError) as exc_info,
    ):
        reg._resolve_ports()
    assert "motors" in str(exc_info.value)
    assert (
        "multiple" in str(exc_info.value).lower()
        or "ambiguous" in str(exc_info.value).lower()
    )


def test_resolve_ports_skips_motherboard_entry(tmp_path: Path) -> None:
    """A manifest entry without vid_pid (motherboard serial port) is skipped."""
    inv = {
        "devices": {
            "serial_devices": [
                {
                    "hwid": "PCI\\VEN_8086",
                    "role": "motherboard",
                },
                {
                    "role": "etl_left",
                    "vid_pid": "10C4:EA60",
                    "serial_number": "AB1234",
                },
            ]
        }
    }
    reg = _make_registry(inv, tmp_path)
    ports = [_make_port("COM5", 0x10C4, 0xEA60, "AB1234")]
    with patch(
        "lightsheet.hal.registry.serial.tools.list_ports.comports",
        return_value=ports,
    ):
        result = reg._resolve_ports()
    # Only etl_left resolved; motherboard entry skipped.
    assert "etl_left" in result
    assert "motherboard" not in result


def test_resolve_ports_skips_vid_none_ports(tmp_path: Path) -> None:
    """Ports with vid=None (motherboard/non-USB) are skipped during indexing
    (line 141)."""
    inv = {
        "devices": {
            "serial_devices": [
                {
                    "role": "etl_left",
                    "vid_pid": "10C4:EA60",
                    "serial_number": "AB1234",
                },
            ]
        }
    }
    reg = _make_registry(inv, tmp_path)
    ports = [
        _make_port("COM1", None, None, None),  # motherboard — skipped
        _make_port("COM5", 0x10C4, 0xEA60, "AB1234"),
    ]
    with patch(
        "lightsheet.hal.registry.serial.tools.list_ports.comports",
        return_value=ports,
    ):
        result = reg._resolve_ports()
    assert result == {"etl_left": "COM5"}
