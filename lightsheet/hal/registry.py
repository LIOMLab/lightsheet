"""DeviceRegistry — USB-serial device role resolver for the rig path.

The registry replaces the god object's implicit "open config.ini ports and
hope the right device is on the other end" pattern with explicit VID/PID +
serial-number matching against ``hardware_inventory.yaml``. This is the
RFR-02 fix: COM ports reorder on replug, so a config.ini ``Port`` value
alone is not a reliable identity for serial-numbered USB-serial adapters.

Resolution rules (D-02 strict abort):

* **Serial-numbered devices** (Optotune ETLs COM5/COM6, Toptica iBeam COM4)
  match on ``(vid, pid, serial_number)`` alone. ``config.ini``'s ``Port``
  value is **never** consulted as a fallback for these devices — that is
  the exact bug RFR-02 exists to fix.

* **Null-serial devices** (the Prolific/Zaber adapter on COM7,
  ``vid_pid 067B:2303``, ``serial_number: null``) cannot be disambiguated
  by serial number, so ``config.ini``'s ``[Motors] Port`` is used as the
  sole sanctioned second factor. Ambiguity (2+ candidates, no config.ini
  match) triggers strict abort rather than picking the first match
  (T-05-09 mitigation).

* **Strict collect-all abort** (D-02): every unresolved role is collected
  into one ``UnresolvedDeviceError`` listing every missing device, then
  raised once. The microscope cannot function meaningfully with a missing
  sub-system, so failing the whole startup rather than degrading is the
  correct posture (T-05-10 accepted availability trade-off).

* **Demo carve-out**: the registry is never imported or constructed on the
  ``--demo`` / ``LIGHTSHEET_DEMO=1`` path. An empty Mac USB-serial port
  list would otherwise abort every device (Pitfall 6). The ``--demo``
  branch lives in ``main()``, not here — this module contains no
  demo-class reference.

* **Motherboard serial port**: the ``hardware_inventory.yaml`` entry with
  only an ``hwid`` key (no ``vid_pid``) is skipped — it carries no role
  this registry needs to resolve.

The role-resolution seam is exposed as ``_resolve_ports()`` which returns a
``dict[role, port]`` mapping BEFORE any HAL class is constructed. The
05-05-PLAN composition root calls ``resolve()`` (which wraps
``_resolve_ports()`` + HAL construction) on the rig path only.
"""

import logging
import serial.tools.list_ports  # pyserial 3.5 — comports() + ListPortInfo
import yaml  # parse hardware_inventory.yaml

from lightsheet.config import cfg_read
from lightsheet.hal.bundle import DeviceBundle
from lightsheet.hal import (
    Camera,
    DAQLaser,
    ETLs,
    IBeamSmartLaser,
    Motors,
    SigGen,
)

logger = logging.getLogger(__name__)


class UnresolvedDeviceError(Exception):
    """Raised when one or more manifest devices cannot be resolved on the
    USB-serial bus. The message lists every unresolved role (collect-all,
    not fail-fast-on-first) so the operator sees the full set of devices
    to reconnect in one dialog (D-02 strict abort)."""


class DeviceRegistry:
    """Resolves ``hardware_inventory.yaml`` serial-device roles to live
    USB-serial COM ports by VID/PID + serial-number matching, then
    constructs the real HAL bundle.

    Constructed only on the rig path (``main()``'s ``else:`` branch of the
    ``if demo:`` split). Never imported on the ``--demo`` path.
    """

    def __init__(self, inventory_path: str, config_path: str) -> None:
        with open(inventory_path) as f:
            self._inventory = yaml.safe_load(f)
        self._config_path = config_path

    def _resolve_ports(self) -> dict[str, str]:
        """Resolve every ``serial_devices`` manifest entry to a COM port.

        Returns a ``dict[role, port]`` mapping. Raises ``UnresolvedDeviceError``
        listing every unresolved role if any device is missing or ambiguous
        (collect-all, not fail-fast-on-first).
        """
        ports = list(serial.tools.list_ports.comports())

        # Index live ports by (vid, pid, serial_number) for serial-numbered
        # devices, and by (vid, pid) for null-serial devices.
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
            # Skip the motherboard serial port entry — it has no vid_pid key
            # and carries no role this registry needs to resolve.
            if "vid_pid" not in dev:
                continue

            role = dev["role"]
            vid_hex, pid_hex = dev["vid_pid"].split(":")
            vid, pid = int(vid_hex, 16), int(pid_hex, 16)

            if dev["serial_number"] is not None:
                # Serial-numbered device — match on (vid, pid, serial) alone.
                # config.ini's Port value is NEVER consulted as a fallback
                # for these devices (RFR-02). Coerce to str: YAML parses
                # all-digit serial numbers as ints, but ListPortInfo.
                # serial_number is always a string.
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
                # Null-serial device — disambiguate by config.ini [Motors]
                # Port (the sole sanctioned config.ini port fallback).
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

        Calls ``_resolve_ports()`` first (raises ``UnresolvedDeviceError``
        on any miss), then constructs the real HAL classes at their
        resolved ports. The HAL classes read their own config.ini ports
        for opening — on a correctly-wired rig, those match the resolved
        ports. The registry's job is to validate presence on the USB bus
        before the HAL classes attempt to open serial connections, so a
        missing device surfaces as a clear operator-facing error rather
        than a cryptic serial-open failure.
        """
        resolved = self._resolve_ports()
        logger.debug("DeviceRegistry resolved ports: %s", resolved)

        camera = Camera(verbose=True)
        siggen = SigGen(camera)
        motors = Motors()
        etls = ETLs()

        # Laser 1 (DAQ AO /Dev7/ao0, 555 nm) — mW-native constructor args
        # derived from config.ini [Lasers], mirroring the lifted
        # hardware_init factory branch.
        _l1_cfg = cfg_read(
            self._config_path,
            "Lasers",
            {
                "Laser1 Wavelength": 555,
                "Laser1 Power": 0.0,
                "Laser1 Max Power": 5.0,
                "Laser1 mW per Volt": 60.0,
            },
        )
        lasers = (
            DAQLaser(
                terminal="/Dev7/ao0",
                wavelength=int(_l1_cfg["Laser1 Wavelength"]),
                mw_per_volt=float(_l1_cfg["Laser1 mW per Volt"]),
                max_power_mw=float(_l1_cfg["Laser1 Max Power"])
                * float(_l1_cfg["Laser1 mW per Volt"]),
                label="Laser 1 (555 nm)",
            ),
            IBeamSmartLaser(label="Laser 2 (640 nm)"),
        )

        return DeviceBundle(
            camera=camera,
            siggen=siggen,
            motors=motors,
            etls=etls,
            lasers=lasers,
        )
