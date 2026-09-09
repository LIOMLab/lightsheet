"""Mock-serial unit tests for the DeviceRegistry VID/PID resolver
(lightsheet/hal/registry.py).

These tests run on Mac with no physical device: ``serial.tools.list_ports.
comports`` is patched so the registry's USB-serial enumeration is captured
against MagicMocks standing in for ``ListPortInfo`` entries. The protocol
assumptions (VID/PID + serial_number matching for serial-numbered devices,
config.ini ``[Motors] Port`` disambiguation for the null-serial Prolific/Zaber
adapter, strict collect-all abort on any unresolved role) follow RFR-02 and
the Phase 5 threat model (T-05-09 / T-05-10).

The registry's role-resolution seam is exposed as ``_resolve_ports()`` which
returns a ``dict[role, port]`` mapping BEFORE any HAL class is constructed.
Tests exercise that seam so no real hardware I/O is attempted on the Mac
dev box — the ``resolve()`` method that wraps ``_resolve_ports()`` + HAL
construction is wired by the 05-05-PLAN composition root on the rig path
only (D-02: the registry is never imported on the ``--demo`` path).
"""

from unittest.mock import MagicMock, patch

import pytest

from lightsheet.hal.registry import DeviceRegistry, UnresolvedDeviceError

# ---------------------------------------------------------------------------
# Manifest constants — verbatim from hardware_inventory.yaml serial_devices.
# Tests point DeviceRegistry at the real hardware_inventory.yaml + config.ini
# in the repo root (read-only fixtures — never modified by these tests).
# ---------------------------------------------------------------------------
INVENTORY_PATH = "hardware_inventory.yaml"
CONFIG_PATH = "config.ini"

# The four vid_pid-bearing serial_devices roles (the 5th entry — the
# motherboard serial port — has no vid_pid key and must be skipped).
ROLE_IBEAM = "Toptica iBeam Smart 640nm laser"
ROLE_ZABER = "Zaber motor stages"
ROLE_ETL_LEFT = "ETL left"
ROLE_ETL_RIGHT = "ETL right"

# (vid, pid, serial_number, device) tuples for the mocked comports() list.
_IBEAM_PORT = (0x0403, 0x6001, "FTESFCRWA", "COM4")
_ETL_LEFT_PORT = (0x03EB, 0x2018, "75738303238351109060", "COM5")
_ETL_RIGHT_PORT = (0x03EB, 0x2018, "75738303238351916161", "COM6")
_ZABER_PORT = (0x067B, 0x2303, None, "COM7")


def _fake_port(
    vid: int | None, pid: int | None, sn: str | None, device: str
) -> MagicMock:
    """Build a MagicMock stand-in for a serial.tools.list_ports.ListPortInfo."""
    p = MagicMock()
    p.vid = vid
    p.pid = pid
    p.serial_number = sn
    p.device = device
    p.hwid = (
        f"USB VID:PID={vid:04X}:{pid:04X}" if vid is not None else "ACPI\\PNP0501\\0"
    )
    return p


def _resolve_ports(ports: list[tuple]) -> dict[str, str]:  # ty: ignore[missing-type-argument]
    """Build a DeviceRegistry against a mocked comports() list and run
    ``_resolve_ports()`` while the patch is active.

    ``ports`` is a list of ``(vid, pid, serial_number, device)`` tuples.
    Returns the role→port mapping the registry computed. Raises
    ``UnresolvedDeviceError`` verbatim from the registry when resolution
    fails — tests assert on that exception's message.
    """
    fake_ports = [_fake_port(v, p, s, d) for (v, p, s, d) in ports]
    with patch(
        "lightsheet.hal.registry.serial.tools.list_ports.comports",
        return_value=fake_ports,
    ):
        registry = DeviceRegistry(INVENTORY_PATH, CONFIG_PATH)
        return registry._resolve_ports()


def _expect_unresolved(ports: list[tuple]) -> UnresolvedDeviceError:  # ty: ignore[missing-type-argument]
    """Run ``_resolve_ports()`` against ``ports`` and return the raised
    ``UnresolvedDeviceError`` (fails the test if no exception is raised)."""
    with pytest.raises(UnresolvedDeviceError) as exc_info:
        _resolve_ports(ports)
    return exc_info.value


# --------------------------------------------------------------------------- #
# Test 1: serial-numbered device (iBeam 0403:6001 SN FTESFCRWA) resolves by
# VID/PID + serial alone — config.ini's Port value is never consulted as a
# fallback for serial-numbered devices (the RFR-02 bug this registry exists
# to fix).


def test_ibeam_resolves_by_vid_pid_serial() -> None:
    # All 4 vid_pid-bearing ports present — the iBeam must resolve by
    # VID/PID + serial alone (config.ini Port never consulted for it).
    ports = [_IBEAM_PORT, _ETL_LEFT_PORT, _ETL_RIGHT_PORT, _ZABER_PORT]
    resolved = _resolve_ports(ports)
    assert resolved[ROLE_IBEAM] == "COM4"


# --------------------------------------------------------------------------- #
# Test 2: null-serial Zaber/Prolific adapter (067B:2303, serial_number: null)
# resolves by VID/PID + config.ini [Motors] Port disambiguator — the sole
# sanctioned use of a config.ini port as a fallback.


def test_zaber_null_serial_resolves_by_config_port() -> None:
    # All 4 vid_pid-bearing ports present — the null-serial Zaber resolves
    # by VID/PID + config.ini [Motors] Port disambiguator.
    ports = [_IBEAM_PORT, _ETL_LEFT_PORT, _ETL_RIGHT_PORT, _ZABER_PORT]
    resolved = _resolve_ports(ports)
    assert resolved[ROLE_ZABER] == "COM7"


# --------------------------------------------------------------------------- #
# Test 3: TWO 067B:2303 ports present (COM7 + COM9) — config.ini [Motors]
# Port = COM7 disambiguates the ambiguous VID/PID match.


def test_zaber_ambiguous_disambiguated_by_config_port() -> None:
    # All 4 manifest ports + a second 067B:2303 at COM9 — config.ini
    # [Motors] Port = COM7 disambiguates the ambiguous VID/PID match.
    ports = [
        _IBEAM_PORT,
        _ETL_LEFT_PORT,
        _ETL_RIGHT_PORT,
        _ZABER_PORT,
        (0x067B, 0x2303, None, "COM9"),
    ]
    resolved = _resolve_ports(ports)
    assert resolved[ROLE_ZABER] == "COM7"


# --------------------------------------------------------------------------- #
# Test 4: TWO 067B:2303 ports present but NEITHER matches config.ini's
# [Motors] Port = COM7 — strict abort, UnresolvedDeviceError mentions the
# Zaber role.


def test_zaber_ambiguous_no_config_match_raises() -> None:
    # iBeam + ETLs present (they resolve), but TWO 067B:2303 ports at COM8
    # and COM9 — NEITHER matches config.ini [Motors] Port = COM7.
    ports = [
        _IBEAM_PORT,
        _ETL_LEFT_PORT,
        _ETL_RIGHT_PORT,
        (0x067B, 0x2303, None, "COM8"),
        (0x067B, 0x2303, None, "COM9"),
    ]
    err = _expect_unresolved(ports)
    assert "Zaber" in str(err) or ROLE_ZABER in str(err)


# --------------------------------------------------------------------------- #
# Test 5: the iBeam's serial-numbered port is entirely ABSENT from the
# mocked comports() list — UnresolvedDeviceError's message contains the
# VID/PID (0403/6001) or the serial number (FTESFCRWA) so the operator can
# identify which device to reconnect.


def test_missing_serial_numbered_device_raises() -> None:
    # ETLs + Zaber present, iBeam absent — UnresolvedDeviceError must
    # contain the VID/PID (0403/6001) or serial (FTESFCRWA).
    ports = [_ETL_LEFT_PORT, _ETL_RIGHT_PORT, _ZABER_PORT]
    err = _expect_unresolved(ports)
    msg = str(err)
    assert "0403" in msg or "6001" in msg or "FTESFCRWA" in msg


# --------------------------------------------------------------------------- #
# Test 6: TWO devices simultaneously absent (iBeam AND one Optotune ETL) —
# the single raised UnresolvedDeviceError names BOTH missing roles
# (collect-all, not fail-fast-on-first).


def test_collect_all_multiple_missing_raises_one_error() -> None:
    ports = [_ETL_RIGHT_PORT]  # iBeam + ETL left both absent
    err = _expect_unresolved(ports)
    msg = str(err)
    assert ROLE_IBEAM in msg or "iBeam" in msg
    assert ROLE_ETL_LEFT in msg or "ETL left" in msg


# --------------------------------------------------------------------------- #
# Test 7: a fully-populated mocked comports() list matching all 4
# vid_pid-bearing manifest entries resolves with zero exceptions and does
# NOT attempt to resolve the 5th motherboard serial port entry (which has
# no vid_pid key in hardware_inventory.yaml).


def test_full_resolution_skips_motherboard_entry() -> None:
    ports = [_IBEAM_PORT, _ETL_LEFT_PORT, _ETL_RIGHT_PORT, _ZABER_PORT]
    resolved = _resolve_ports(ports)
    # All 4 vid_pid-bearing roles resolved, motherboard role NOT present.
    assert ROLE_IBEAM in resolved
    assert ROLE_ETL_LEFT in resolved
    assert ROLE_ETL_RIGHT in resolved
    assert ROLE_ZABER in resolved
    assert "motherboard serial port" not in resolved
    assert len(resolved) == 4
