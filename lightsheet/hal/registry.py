"""DeviceRegistry — USB-serial device role resolver for the rig path.

The registry replaces implicit "open config.ini ports and hope" with explicit
VID/PID + serial-number matching against ``hardware_inventory.yaml``. COM ports
reorder on replug, so a config.ini ``Port`` value alone is not reliable identity.

Resolution rules:
- Serial-numbered devices match on ``(vid, pid, serial_number)`` alone.
  config.ini's ``Port`` is never consulted as a fallback for these.
- Null-serial devices use config.ini's ``[Motors] Port`` as a second factor.
  Ambiguity triggers strict abort rather than picking the first match.
- Every unresolved role is collected into one ``UnresolvedDeviceError`` listing
  every missing device, then raised once.
- The registry is never imported on the ``--demo`` path.
- The motherboard serial port entry (``hwid`` only, no ``vid_pid``) is skipped.
"""

import logging
from pathlib import Path

import serial.tools.list_ports  # pyserial 3.5 -- comports() + ListPortInfo
import yaml

from lightsheet.config import cfg_read
from lightsheet.hal import (
    Camera,
    DAQLaser,
    ETLs,
    IBeamSmartLaser,
    Motors,
    SigGen,
)
from lightsheet.hal.bundle import DeviceBundle

logger = logging.getLogger(__name__)


def _parse_calibration_curve(
    raw: str,
) -> list[tuple[float, float]] | None:
    """Parse a ``Laser1 Calibration Curve`` config string into ``(V, mW)``
    breakpoint pairs. Empty/whitespace-only -> ``None``. Malformed entries
    reject the whole curve -> ``None``. Strictly-increasing V + non-negative
    mW validation happens in ``DAQLaser.__init__``."""
    if not raw:
        return None
    pairs: list[tuple[float, float]] = []
    for chunk in raw.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = [p.strip() for p in chunk.split(",")]
        if len(parts) != 2:
            logger.error(
                "calibration curve entry %r is not a 'V,mW' pair — "
                "rejecting the whole curve",
                chunk,
            )
            return None
        try:
            pairs.append((float(parts[0]), float(parts[1])))
        except ValueError:
            logger.error(
                "calibration curve entry %r has non-numeric values — "
                "rejecting the whole curve",
                chunk,
            )
            return None
    return pairs or None


class UnresolvedDeviceError(Exception):
    """Raised when one or more manifest devices cannot be resolved on the
    USB-serial bus. Lists every unresolved role (collect-all, not fail-fast)."""


class DeviceRegistry:
    """Resolves ``hardware_inventory.yaml`` serial-device roles to live
    USB-serial COM ports by VID/PID + serial-number matching, then constructs
    the real HAL bundle. Constructed only on the rig path."""

    def __init__(self, inventory_path: str, config_path: str) -> None:
        with Path(inventory_path).open() as f:
            self._inventory = yaml.safe_load(f)
        self._config_path = config_path

    def _resolve_ports(self) -> dict[str, str]:
        """Resolve every ``serial_devices`` manifest entry to a COM port.
        Raises ``UnresolvedDeviceError`` listing every unresolved role if any
        device is missing or ambiguous (collect-all, not fail-fast)."""
        ports = list(serial.tools.list_ports.comports())

        # Index live ports by (vid, pid, serial_number) and by (vid, pid).
        by_vid_pid_serial: dict[tuple[int, int, str], str] = {}
        by_vid_pid: dict[tuple[int, int], list[str]] = {}
        for p in ports:
            if p.vid is None:
                continue  # motherboard / non-USB port — no vid_pid to match
            if p.serial_number:
                by_vid_pid_serial[(p.vid, p.pid, p.serial_number)] = p.device
            else:
                by_vid_pid.setdefault((p.vid, p.pid), []).append(p.device)

        unresolved: list[str] = []
        resolved: dict[str, str] = {}

        for dev in self._inventory["devices"]["serial_devices"]:
            # Skip the motherboard serial port entry — no vid_pid, no role.
            if "vid_pid" not in dev:
                continue

            role = dev["role"]
            vid_hex, pid_hex = dev["vid_pid"].split(":")
            vid, pid = int(vid_hex, 16), int(pid_hex, 16)

            if dev["serial_number"] is not None:
                # Serial-numbered device — match on (vid, pid, serial) alone.
                # config.ini's Port is NEVER consulted as a fallback. Coerce
                # to str: YAML parses all-digit serial numbers as ints.
                sn_str = str(dev["serial_number"])
                port = by_vid_pid_serial.get((vid, pid, sn_str))
                if port is None:
                    unresolved.append(
                        f"✕ {role} (VID {vid:04X} PID {pid:04X} "
                        f"SN {sn_str}) not found on any COM "
                        f"port. Expected on a USB-serial adapter."
                    )
                else:
                    resolved[role] = port
            else:
                # Null-serial device — disambiguate by config.ini [Motors] Port.
                cfg_port = str(
                    cfg_read(self._config_path, "Motors", {"Port": "COM7"})["Port"]
                )
                candidates = by_vid_pid.get((vid, pid), [])
                if cfg_port in candidates:
                    resolved[role] = cfg_port
                elif len(candidates) == 1:
                    resolved[role] = candidates[0]
                elif len(candidates) == 0:
                    unresolved.append(
                        f"✕ {role} (VID {vid:04X} PID {pid:04X}, no serial "
                        f"number) — no match on the configured COM port "
                        f"{cfg_port}. Connect the device to {cfg_port}, or "
                        f"update [Motors] Port in config.ini to the port it "
                        f"is now on."
                    )
                else:
                    port_list = ", ".join(candidates)
                    unresolved.append(
                        f"✕ {role} (VID {vid:04X} PID {pid:04X}, no serial "
                        f"number) — multiple matching adapters found "
                        f"({port_list}). Update [Motors] Port in config.ini "
                        f"to disambiguate."
                    )

        if unresolved:
            raise UnresolvedDeviceError(
                "Missing device — startup aborted\n"
                "The following device(s) were not found on the USB-serial "
                "bus. The microscope cannot run without all of its "
                "sub-systems — a missing motor, lens driver, camera, or "
                "laser makes any acquisition meaningless. Connect the "
                "missing device(s) and restart the application.\n"
                + "\n".join(unresolved)
            )

        return resolved

    def resolve(self) -> DeviceBundle:
        """Resolve all manifest devices and construct the real HAL bundle.

        Calls ``_resolve_ports()`` first (raises on any miss), then constructs
        the real HAL classes at their resolved ports. Validating presence on
        the USB bus before opening serial connections surfaces a clear
        operator-facing error rather than a cryptic serial-open failure.
        """
        resolved = self._resolve_ports()
        logger.debug("DeviceRegistry resolved ports: %s", resolved)

        camera = Camera(verbose=True)
        siggen = SigGen(camera)
        motors = Motors()
        etls = ETLs()

        # Laser 1 (DAQ AO /Dev7/ao0, 555 nm) -- mW-native constructor
        # args from config.ini [Lasers].
        _l1_cfg = cfg_read(
            self._config_path,
            "Lasers",
            {
                "Laser1 Wavelength": 555,
                "Laser1 Power": 0.0,
                "Laser1 Max Power": 5.0,
                "Laser1 mW per Volt": 60.0,
                "Laser1 Calibration Curve": "",
            },
        )
        # Optional V->mW calibration curve (display-only). Empty/absent -> None.
        # DAQLaser validates strictly-increasing V + non-negative mW on construct.
        _curve_raw = str(_l1_cfg.get("Laser1 Calibration Curve", "")).strip()
        _calibration_curve = _parse_calibration_curve(_curve_raw)
        lasers = (
            DAQLaser(
                terminal="/Dev7/ao0",
                wavelength=int(_l1_cfg["Laser1 Wavelength"]),
                mw_per_volt=float(_l1_cfg["Laser1 mW per Volt"]),
                max_power_mw=float(_l1_cfg["Laser1 Max Power"])
                * float(_l1_cfg["Laser1 mW per Volt"]),
                label="Laser 1 (555 nm)",
                calibration_curve=_calibration_curve,
            ),
            IBeamSmartLaser(label="Laser 2 (647 nm)"),
        )

        return DeviceBundle(
            camera=camera,
            siggen=siggen,
            motors=motors,
            etls=etls,
            lasers=lasers,
        )
