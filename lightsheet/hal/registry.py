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
    InvertedVoltMap,
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
        motors = Motors(port=resolved["Zaber motor stages"])
        etls = ETLs(
            port_etl_left=resolved["ETL left"],
            port_etl_right=resolved["ETL right"],
        )

        # Laser config from config.ini [Lasers].
        _l_cfg = cfg_read(
            self._config_path,
            "Lasers",
            {
                "Laser1 Wavelength": 555,
                "Laser1 Power": 0.0,
                "Laser1 Max Power": 107.5,
                "Laser1 mW per Volt": 60.0,
                "Laser1 Calibration Curve": "",
                "Lasers Terminals": "/Dev7/ao0:1",
                "Laser2 Wavelength": 647,
                "Laser2 Power": 0.0,
                "Laser2 Max Power": 150.0,
                "Laser2 mW per Volt": 30.0,
            },  # ty: ignore[invalid-argument-type]
        )

        # Parse the two-channel Lasers Terminals range (e.g. /Dev7/ao0:1)
        # into individual AO channel terminals. Fail clearly on a malformed
        # or non-two-channel range before HAL construction.
        l1_terminal, l2_terminal = _parse_laser_terminals(
            str(_l_cfg["Lasers Terminals"])
        )

        # Laser 1 (DAQ AO /Dev7/ao0, 555 nm) -- mW-native constructor
        # args from config.ini [Lasers].
        # Optional V->mW calibration curve (display-only). Empty/absent -> None.
        # DAQLaser validates strictly-increasing V + non-negative mW on construct.
        _curve_raw = str(_l_cfg.get("Laser1 Calibration Curve", "")).strip()
        _calibration_curve = _parse_calibration_curve(_curve_raw)
        l1 = DAQLaser(
            terminal=l1_terminal,
            wavelength=int(_l_cfg["Laser1 Wavelength"]),
            mw_per_volt=float(_l_cfg["Laser1 mW per Volt"]),
            max_power_mw=float(_l_cfg["Laser1 Max Power"])
            * float(_l_cfg["Laser1 mW per Volt"]),
            label="Laser 1 (555 nm)",
            calibration_curve=_calibration_curve,
        )

        # Laser 2: DAQ-primary on /Dev7/ao1 (0-5 V analog modulation).
        # The rig-measured iBeam analog modulation transfer function is
        # INVERTED: 0 mW -> 5 V (true-off), max_power -> 0 V (max output).
        # Higher requested power = LOWER voltage. InvertedVoltMap encodes
        # this polarity and provides off_volts=5.0 V so the synchronous
        # E-stop off() writes 5 V (true-off), NOT 0 V (which would drive
        # the laser to MAXIMUM power on an inverted L2).
        #
        # Laser2 Max Power is the SOLE L2 ceiling: it supplies both the
        # DAQLaser mW ceiling (InvertedVoltMap.max_power_mw) AND the CH2
        # serial ceiling (IBeamSmartLaser.analog_ceiling_mw). A single
        # config value bounds both the DAQ and serial paths.
        #
        # The retained iBeam serial backend is attached as the
        # readback_backend — used for channel enable at open (via the
        # analog-modulation setup sequence: CH1=0, CH2=ceiling, enable 1,
        # enable 2, laser on, en ext) and power/status readback only,
        # never for on/off or power writes. The analog-mode-enable
        # prerequisite (TOPAS GUI, one-time manual) is documented in
        # config.ini; there is no serial command for it.
        _l2_max_power_mw = float(_l_cfg["Laser2 Max Power"])
        l2_readback = IBeamSmartLaser(
            label="Laser 2 (647 nm)",
            analog_ceiling_mw=_l2_max_power_mw,
            port=resolved["Toptica iBeam Smart 640nm laser"],
        )
        l2 = DAQLaser(
            terminal=l2_terminal,
            wavelength=int(_l_cfg["Laser2 Wavelength"]),
            max_power_mw=_l2_max_power_mw,
            label="Laser 2 (647 nm)",
            readback_backend=l2_readback,
            volt_map=InvertedVoltMap(
                max_volts=5.0,
                max_power_mw=_l2_max_power_mw,
            ),
        )

        siggen = SigGen(camera)

        lasers = (l1, l2)

        return DeviceBundle(
            camera=camera,
            siggen=siggen,
            motors=motors,
            etls=etls,
            lasers=lasers,
        )


def _parse_laser_terminals(terminals: str) -> tuple[str, str]:
    """Parse a two-channel Lasers Terminals range into individual terminals.

    ``/Dev7/ao0:1`` -> ``(/Dev7/ao0, /Dev7/ao1)``. Raises ``ValueError`` on a
    malformed or non-two-channel range so the operator gets a clear error
    before HAL construction rather than a cryptic DAQ channel failure.
    """
    try:
        device, channel_range = terminals.rsplit("/", 1)
    except ValueError:
        raise ValueError(
            f"Lasers Terminals {terminals!r} is malformed — expected "
            f"'/Dev7/ao0:1' (device + two-channel range)"
        ) from None
    if not channel_range.startswith("ao"):
        raise ValueError(
            f"Lasers Terminals {terminals!r} channel part does not start "
            f"with 'ao' — expected '/Dev7/ao0:1'"
        )
    parts = channel_range[2:].split(":")
    if len(parts) != 2:
        raise ValueError(
            f"Lasers Terminals {terminals!r} is not a two-channel range — "
            f"expected '/Dev7/ao0:1'"
        )
    try:
        ch_start, ch_end = int(parts[0]), int(parts[1])
    except ValueError:
        raise ValueError(
            f"Lasers Terminals {terminals!r} channel indices are not integers"
        ) from None
    if ch_end - ch_start != 1:
        raise ValueError(
            f"Lasers Terminals {terminals!r} is not a two-channel range — "
            f"expected exactly two consecutive channels (e.g. ao0:1)"
        )
    return f"{device}/ao{ch_start}", f"{device}/ao{ch_end}"
