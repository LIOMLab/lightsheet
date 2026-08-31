"""Toptica iBeam Smart serial HAL — engine + ``ILaser`` adapter.

- ``IBeam`` — the serial engine that drives the red Toptica iBeam Smart laser
  over its virtual COM port (FTDI USB-to-serial). The protocol is ASCII text:
  commands are terminated with CRLF, and the device replies with one or more
  lines followed by a ``CMD> `` prompt.
- ``IBeamSmartLaser`` — the ``ILaser``-shaped adapter that wraps ``IBeam``,
  converting mW <-> µW and mirroring ``active`` / ``error`` / ``error_message``.

The iBeam Smart has a known reply-lag firmware quirk: rapid command sequences
can cause response misattribution. Mitigations: a per-instance lock serializing
all serial access, an inter-command gap, and an input-buffer flush before every
command.

This is a Class IIIB laser. ``set_power`` clamps to ``max_power`` (from
config.ini `[iBeam] Max Power`) as a physical-safety control enforced inside
the HAL so any caller is bounded. Two-layer clamp: the adapter clamps mW, the
inner ``IBeam.set_power`` clamps µW independently.

``off()`` is synchronous — no thread/queue offload. The GUI-thread E-stop
handler calls this directly; offloading would break the synchronous-off safety
contract.

``self._lock`` IS ``self._ibeam._lock`` — the same object, not a new lock, so
a daemon write holding the adapter lock excludes a concurrent ``_send_cmd``
round-trip on the same engine.
"""

import contextlib
import copy
import logging
import threading
import time

import serial

from lightsheet.config import cfg_read
from lightsheet.hal.interfaces import ILaser

logger = logging.getLogger(__name__)


class IBeam:
    """HAL class for the Toptica iBeam Smart serial laser."""

    # Default configurable settings (overlaid with config.ini `[iBeam]`).
    _cfg_settings: dict[str, str] = {}  # noqa: RUF012 - class-level config template, populated at definition, never mutated at runtime
    _cfg_settings["Port"] = "COM4"
    _cfg_settings["Baud Rate"] = "115200"
    _cfg_settings["Channel"] = "1"
    # Capture/detection wavelength in nm (physical diode emits at 640 nm;
    # 647 nm is the recorded capture wavelength)
    _cfg_settings["Wavelength"] = "647"
    _cfg_settings["Power"] = "0"  # In uW
    _cfg_settings["Max Power"] = "150000"  # In uW (150 mW diode limit, rig-confirmed)
    # Per-readline timeout. The firmware sends data/error lines in <30ms but
    # takes ~3s to send the CMD> prompt. A short timeout per readline lets
    # data lines arrive; a timeout (b"") signals the response is complete.
    # The late CMD> prompt is flushed by reset_input_buffer on the next command.
    _cfg_settings["Read Timeout"] = "0.2"  # seconds per readline

    def __init__(self, port: str | None = None) -> None:
        # HAL error status (mirrors lightsheet/lasers.py and lightsheet/etls.py).
        self.error = 0
        self.error_message = ""

        self.cfg_settings = copy.deepcopy(self._cfg_settings)
        self.cfg_settings = cfg_read("config.ini", "iBeam", self.cfg_settings)

        self.port = port if port is not None else str(self.cfg_settings["Port"])
        self.baud_rate = int(self.cfg_settings["Baud Rate"])
        self.channel = int(self.cfg_settings["Channel"])
        self.wavelength = int(self.cfg_settings["Wavelength"])
        self._power = int(self.cfg_settings["Power"])
        self.max_power = int(self.cfg_settings["Max Power"])
        self._read_timeout = float(self.cfg_settings["Read Timeout"])

        self.ser = None
        self._is_on = False

        # Reply-lag mitigations.
        self._inter_command_gap = 0.05  # 50 ms starting point
        # Reentrant (RLock) so the controller's nested acquisition pattern
        # (adapter lock -> inner _send_cmd lock, both aliased) does not deadlock.
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    def open(self) -> None:
        """Open the serial port and disable command echo."""
        try:
            # serial.Serial open unreachable on Mac; set_power/off/_send_cmd
            # stay measured (mock-serial via test_ibeam.py)
            self.ser = serial.Serial()  # pragma: no cover
            self.ser.baudrate = self.baud_rate
            self.ser.port = self.port
            self.ser.timeout = 3.0
            self.ser.open()
            # Disable command echo so replies are not doubled.
            self._send_cmd("echo off")
            # Enable the configured diode channel — without `enable <ch>` the
            # firmware accepts the power write but the diode stays dark.
            self.enable_channel()
        except serial.SerialException as e:
            self.error = 1
            self.error_message = str(e)
            if self.ser is not None:
                with contextlib.suppress(Exception):
                    self.ser.close()
                self.ser = None
            logger.exception("IBeam open failed")
            raise
        return None

    def close(self) -> None:
        """Turn the laser off and release the serial port."""
        try:
            if self.ser is not None:
                self.off()
                self.ser.close()
        except serial.SerialException as e:
            self.error = 1
            self.error_message = str(e)
            logger.exception("IBeam close failed")
        finally:
            self.ser = None
        return None

    # ------------------------------------------------------------------ #
    # Laser control
    # ------------------------------------------------------------------ #
    def on(self) -> None:
        """Enable laser emission (global enable)."""
        try:
            self._send_cmd("laser on")
            # Bail before re-enabling the channel if the global emission enable
            # was rejected — _send_cmd resets self.error=0 at the top of every
            # round-trip, so a subsequent enable_channel() would clear the
            # rejection (Class IIIB laser safety).
            if self.error:
                return
            # Re-enable the configured diode channel with each emission enable.
            self.enable_channel()
            # Only mark the laser as on if neither sub-command was rejected.
            if not self.error:
                self._is_on = True
        except serial.SerialException as e:
            self.error = 1
            self.error_message = str(e)
            logger.exception("IBeam on failed")
        return None

    def off(self) -> None:
        """Disable laser emission (global disable)."""
        try:
            self._send_cmd("laser off")
            self._is_on = False
            self._power = 0
        except serial.SerialException as e:
            self.error = 1
            self.error_message = str(e)
            # False is the safer default for a Class IIIB laser — the GUI treats
            # the laser as off and the operator is warned to manually verify.
            self._is_on = False
            logger.exception("IBeam off failed")
        return None

    def enable_channel(self, channel: int | None = None) -> None:
        """Enable a diode channel so channel power commands take effect.

        Without `enable <ch>` a power command is accepted but does not change
        the output. channel: 1-based index; defaults to the configured channel.
        """
        ch = self.channel if channel is None else int(channel)
        try:
            self._send_cmd(f"enable {ch}")
        except serial.SerialException as e:
            self.error = 1
            self.error_message = str(e)
            logger.exception("IBeam enable_channel failed")
        return None

    def set_power(self, power_uw: int) -> None:
        """Set channel power in microwatts, clamped to [0, max_power].

        The clamp is a physical-safety control bounding the maximum power any
        caller can command, protecting the diode against a config.ini typo.
        """
        power_uw = max(0, min(power_uw, self.max_power))
        try:
            self._send_cmd(f"channel {self.channel} power {power_uw} micro")
            # Only record the commanded power if the firmware accepted the
            # write. _send_cmd sets self.error on rejection without raising.
            if not self.error:
                self._power = power_uw
        except serial.SerialException as e:
            self.error = 1
            self.error_message = str(e)
            logger.exception("IBeam set_power failed")
        return None

    def get_output_power(self) -> int | None:
        """Read the current channel output power in microwatts.

        Sends `show level power` and parses the `CH<n>, PWR: <value> mW` line.
        Returns ``None`` when no matching line is found or on a serial error.
        """
        try:
            response = self._send_cmd("show level power")
            for line in response:
                if f"CH{self.channel}" in line and "PWR:" in line:
                    # e.g. "CH1, PWR: 75.000 mW"
                    try:
                        value_part = line.split("PWR:")[1].strip()
                        # value_part looks like "75.000 mW" or "5000 uW"
                        token, unit = value_part.split()
                        value = float(token)
                        if unit.lower() == "mw":
                            return int(value * 1000)
                        elif unit.lower() == "uw":
                            return int(value)
                    except (ValueError, IndexError):
                        # Malformed line -> fall through to None fallback.
                        break
            # No matching CH line found — return None so the adapter surfaces
            # "no reading" instead of the stale commanded value.
            return None
        except serial.SerialException as e:
            self.error = 1
            self.error_message = str(e)
            logger.exception("IBeam get_output_power failed")
            return None

    def is_enabled(self) -> bool:
        """Return True if laser emission is currently enabled."""
        try:
            response = self._send_cmd("status laser")
            for line in response:
                if line == "ON":
                    return True
                elif line == "OFF":
                    return False
        except serial.SerialException as e:
            self.error = 1
            self.error_message = str(e)
            logger.exception("IBeam is_enabled failed")
        return False

    def reboot(self) -> None:
        """Send `reset system` to recover from protocol desync."""
        try:
            self._send_cmd("reset system")
        except serial.SerialException as e:
            self.error = 1
            self.error_message = str(e)
            logger.exception("IBeam reboot failed")
        return None

    # ------------------------------------------------------------------ #
    # Serial I/O
    # ------------------------------------------------------------------ #
    def _send_cmd(self, cmd: str) -> list[str]:
        """Send an ASCII command and read the response lines.

        Acquires the per-instance lock, flushes the input buffer, writes the
        command with CRLF, reads lines until a per-readline timeout fires or
        the ``[OK]`` / ``CMD>`` terminator is seen, then sleeps for the
        inter-command gap. Uses a short per-readline timeout to avoid waiting
        ~3s for the CMD> prompt.
        """
        with self._lock:
            if self.ser is None:
                raise serial.SerialException("Serial not connected")

            # Clear any stale error from a prior command so this command's
            # result is not masked by a previous failure.
            self.error = 0
            self.error_message = ""

            self.ser.reset_input_buffer()
            self.ser.write(f"{cmd}\r\n".encode("ascii"))

            # Use the short per-readline timeout; save/restore the original so
            # the serial port's configured timeout is not permanently changed.
            original_timeout = self.ser.timeout
            self.ser.timeout = self._read_timeout
            try:
                response_lines = []
                while True:
                    raw = self.ser.readline()
                    if raw == b"":
                        # readline returns b'' on timeout — the response is
                        # complete. The CMD> prompt arrives ~3s later and is
                        # flushed by reset_input_buffer on the next command.
                        # A genuine blank line is b'\r\n' (decodes to '') and
                        # is NOT a timeout — it is appended and the loop continues.
                        break
                    line = raw.decode("ascii", errors="replace").strip()
                    response_lines.append(line)
                    if line == "[OK]" or line.startswith("CMD>"):
                        break
            finally:
                self.ser.timeout = original_timeout

            # Surface a device-level rejection on the HAL error surface.
            # The firmware prefixes error replies with `%SYS-E`; we do not
            # raise so existing call sites keep working unchanged.
            for line in response_lines:
                if line.startswith("%SYS-E"):
                    self.error = 1
                    self.error_message = f'iBeam rejected "{cmd}": {line}'
                    break

            time.sleep(self._inter_command_gap)
            return response_lines


class IBeamSmartLaser(ILaser):
    """``ILaser`` adapter for the Toptica iBeam Smart (L2, COM4 serial).

    Wraps the ``IBeam`` serial engine. mW -> µW (x 1000). ``off()`` is
    synchronous (E-stop kill path). ``_lock`` is the same object as the inner
    ``IBeam._lock`` (lock identity).

    **Readback-backend role:** when L2 emission is driven by DAQ-gated analog
    modulation (``DAQLaser`` on ``/Dev7/ao1``), this adapter is retained as
    the ``readback_backend`` on the ``DAQLaser``. In that role, ONLY
    ``open()``, ``close()``, and ``get_output_power()`` are called by the
    controller — for channel enable at startup, serial port release at
    shutdown, and live power/status readback respectively. The
    ``on()``/``off()``/``set_power()`` methods are NOT called by the
    controller in the DAQ-gated configuration; the DAQ AO channel is the
    sole emission-control path. The serial path is read-only for emission
    control. The methods remain present for ILaser conformance and for any
    standalone serial-only usage path.
    """

    def __init__(self, label: str = "Laser 2 (647 nm)") -> None:
        # The inner serial engine. __init__ does NOT open the serial port —
        # the controller's hardware_init is responsible for calling open().
        self._ibeam = IBeam()

        # mW-canonical ILaser surface. The inner IBeam reports wavelength in
        # nm and max_power in µW; the adapter converts max_power to mW.
        self.label = label
        self.wavelength = self._ibeam.wavelength  # 647 (nm)
        self.max_power = self._ibeam.max_power / 1000.0  # uW -> mW
        self.power = 0.0  # mW
        self.active = False
        self.error = 0
        self.error_message = ""

        # Lock identity: the adapter's lock IS the inner IBeam's lock — the
        # same object, not a new lock, so daemon writes exclude concurrent
        # _send_cmd round-trips on the same engine.
        self._lock = self._ibeam._lock

    def on(self) -> None:
        """Energize the laser — delegates to ``IBeam.on()``, then mirrors
        ``active`` and ``error`` / ``error_message`` from the inner engine.
        If the inner ``laser on`` was rejected, ``active`` stays ``False``."""
        self._ibeam.on()
        self.active = self._ibeam._is_on
        self.error = self._ibeam.error
        self.error_message = self._ibeam.error_message

    def open(self) -> None:
        """Open the inner iBeam serial port and enable the configured diode
        channel. Mirrors the inner error surface onto the adapter."""
        self._ibeam.open()
        self.error = self._ibeam.error
        self.error_message = self._ibeam.error_message

    def close(self) -> None:
        """Release the inner iBeam serial port. Mirrors the inner error
        surface onto the adapter."""
        self._ibeam.close()
        self.error = self._ibeam.error
        self.error_message = self._ibeam.error_message

    def off(self) -> None:
        """Synchronous E-stop kill path.

        Sets ``active = False`` and ``power = 0.0``, returns ``None``
        immediately — no thread/queue offload. Offloading would break the
        synchronous-off safety contract for a Class IIIB laser.
        """
        self._ibeam.off()
        self.active = False
        self.power = 0.0

    def set_power(self, mw: float) -> None:
        """Set the staged laser power in milliwatts (mW canonical).

        Clamps ``mw`` to ``[0.0, max_power]`` (mW) at the adapter layer (first
        safety layer), converts to µW, and delegates to ``IBeam.set_power``
        which clamps µW independently (second safety layer). On a firmware
        rejection the adapter does NOT update ``self.power``.
        """
        mw = max(0.0, min(mw, self.max_power))
        # mW -> uW. round() rather than int() so 149.9999 mW converts to
        # 150000 uW (not 149999). The inner IBeam.set_power clamp still applies.
        self._ibeam.set_power(round(mw * 1000))
        if not self._ibeam.error:
            self.power = mw

    def get_output_power(self) -> float | None:
        """Read the current channel output power in milliwatts (mW).

        Delegates to ``IBeam.get_output_power()`` (returns µW) and divides by
        1000.0. Returns ``None`` on an inner error or when no matching channel
        line is found in the response.
        """
        uw = self._ibeam.get_output_power()
        if uw is None or self._ibeam.error:
            return None
        return uw / 1000.0


# ------------------------------------------------------------------------------------
if __name__ == "__main__":
    ib = IBeam()
    ib.open()
    print("serial:", ib.ser)
    ib.close()
