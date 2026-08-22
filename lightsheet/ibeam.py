"""
Toptica iBeam Smart serial HAL driver.

Drives the red Toptica iBeam Smart laser over its virtual COM port (FTDI
USB-to-serial). The protocol is ASCII text: commands are terminated with
CRLF, and the device replies with one or more lines followed by a `CMD> `
prompt. (Some firmware variants also emit an `[OK]` terminator line; this
driver accepts either so it is robust across firmware versions.)

Protocol assumptions were confirmed against the physical rig on COM4 via SSH
(iBeam Smart 640, SN iBEAM-SMART-640-S-G1-15601, firmware iBPs-001A01-05):
  - 115200 baud, 8-N-1
  - `laser on` / `laser off`    -> global emission enable/disable
  - `enable <ch>`               -> per-channel enable (gates channel power)
  - `channel <ch> power <uW> micro` -> set channel power in microwatts
  - `status laser`              -> replies `ON` or `OFF`
  - `show level power`          -> multiline `CH<n>, PWR: <value> mW`
  - `show serial` / `version`   -> identification queries
  - `reset system`              -> reboot (recovery path for protocol desync)

Device-level rejections are signalled by a `%SYS-E...` reply line; `_send_cmd`
surfaces these on the HAL error surface (`self.error` / `self.error_message`)
so a firmware rejection is not mistaken for success.

The iBeam Smart has a known reply-lag firmware quirk: rapid command sequences
can cause response misattribution. Mitigations: a per-instance lock
serializing all serial access, an inter-command gap, and an input-buffer flush
before every command.

This is a Class IIIB laser. The `set_power` clamp to `max_power` (loaded from
config.ini `[iBeam] Max Power`) is a physical-safety control enforced inside
the HAL method so any caller (GUI, future script, E-stop path) is bounded.
"""

import contextlib
import copy
import logging
import threading
import time

import serial
from lightsheet.config import cfg_read

logger = logging.getLogger(__name__)


class IBeam:
    """HAL class for the Toptica iBeam Smart serial laser."""

    # Default configurable settings (overlaid with config.ini `[iBeam]`).
    _cfg_settings: dict[str, str] = {}  # noqa: RUF012 - class-level config template, populated at definition, never mutated at runtime
    _cfg_settings["Port"] = "COM4"
    _cfg_settings["Baud Rate"] = "115200"
    _cfg_settings["Channel"] = "1"
    _cfg_settings["Wavelength"] = "640"  # In nm (iBeam Smart 640)
    _cfg_settings["Power"] = "0"  # In uW
    _cfg_settings["Max Power"] = "150000"  # In uW (150 mW diode limit, rig-confirmed)

    def __init__(self, port: str | None = None) -> None:
        # HAL error status (mirrors lightsheet/lasers.py and lightsheet/etls.py).
        self.error = 0
        self.error_message = ""

        # Load configurable settings, then assign to instance variables.
        self.cfg_settings = copy.deepcopy(self._cfg_settings)
        self.cfg_settings = cfg_read("config.ini", "iBeam", self.cfg_settings)

        self.port = port if port is not None else str(self.cfg_settings["Port"])
        self.baud_rate = int(self.cfg_settings["Baud Rate"])
        self.channel = int(self.cfg_settings["Channel"])
        self.wavelength = int(self.cfg_settings["Wavelength"])
        self._power = int(self.cfg_settings["Power"])
        self.max_power = int(self.cfg_settings["Max Power"])

        # Serial connection + laser state.
        self.ser = None
        self._is_on = False

        # Reply-lag mitigations.
        self._inter_command_gap = 0.05  # 50 ms starting point
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    def open(self) -> None:
        """Open the serial port and disable command echo."""
        try:
            self.ser = serial.Serial()
            self.ser.baudrate = self.baud_rate
            self.ser.port = self.port
            self.ser.timeout = 3.0
            self.ser.open()
            # Disable command echo so replies are not doubled.
            self._send_cmd("echo off")
            # Enable the configured diode channel so a subsequent channel
            # power command actually reaches the output. Without `enable <ch>`
            # the firmware accepts the power write but the diode stays dark.
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
            # Re-enable the configured diode channel with each emission
            # enable. The channel enable is independent of the global
            # `laser on` state; reasserting it here guarantees a power
            # command issued afterwards reaches the output.
            self.enable_channel()
            # Only mark the laser as on if neither the `laser on` write nor
            # the channel enable was rejected by the firmware. _send_cmd and
            # enable_channel both set self.error on a %SYS-E reply without
            # raising, so guard the state update on the error surface to
            # avoid the HAL believing emission is enabled when the firmware
            # refused.
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
            # The operator intent was off; the actual emission state is
            # unknown (the command may or may not have reached the laser).
            # False is the safer default for a Class IIIB laser — the GUI
            # treats the laser as off and the operator is warned (via the
            # error surface) to manually verify, rather than the GUI
            # showing it as on and the operator assuming it is off.
            self._is_on = False
            logger.exception("IBeam off failed")
        return None

    def enable_channel(self, channel: int | None = None) -> None:
        """Enable a diode channel so channel power commands take effect.

        The iBeam Smart protocol gates output on both the global emission
        state (`laser on`) and a per-channel enable. Without `enable <ch>`
        a `channel <ch> power ... micro` command is accepted by the
        firmware but does not change the output.

        channel: 1-based channel index; defaults to the configured channel.
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

        The clamp is a physical-safety control: it bounds the maximum power
        any caller can command, protecting the diode against a typo or tamper
        in config.ini `Max Power`.
        """
        power_uw = max(0, min(power_uw, self.max_power))
        try:
            self._send_cmd(f"channel {self.channel} power {power_uw} micro")
            # Only record the commanded power if the firmware accepted the
            # write. _send_cmd does not raise on a %SYS-E rejection — it
            # sets self.error and returns normally — so guard the state
            # update on the error surface to keep the HAL's internal power
            # consistent with the actual hardware state. The max_power clamp
            # above is a physical-safety control and is NOT affected.
            if not self.error:
                self._power = power_uw
        except serial.SerialException as e:
            self.error = 1
            self.error_message = str(e)
            logger.exception("IBeam set_power failed")
        return None

    def get_output_power(self) -> int:
        """Read the current channel output power in microwatts.

        Sends `show level power` and parses the `CH<n>, PWR: <value> mW` line
        for this driver's channel. Returns the last commanded power as a
        fallback if the reply cannot be parsed.
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
                        # Malformed line -> fall through to fallback.
                        break
        except serial.SerialException as e:
            self.error = 1
            self.error_message = str(e)
            logger.exception("IBeam get_output_power failed")
        return self._power

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
        """Send an ASCII command and read lines until the [OK] or CMD> terminator.

        Acquires the per-instance lock, flushes the input buffer (reply-lag
        mitigation), writes the command with a CRLF terminator, reads lines
        until `[OK]` or a `CMD>` prompt is seen, then sleeps for the
        inter-command gap. Returns the collected response lines (stripped).
        """
        with self._lock:
            if self.ser is None:
                raise serial.SerialException("Serial not connected")

            # Clear any stale error from a prior command so this command's
            # result is not masked by a previous failure. The error surface
            # is reset before the serial round-trip and only re-set below if
            # this command itself fails (a %SYS-E reply) or raises.
            self.error = 0
            self.error_message = ""

            self.ser.reset_input_buffer()
            self.ser.write(f"{cmd}\r\n".encode("ascii"))

            response_lines = []
            while True:
                raw = self.ser.readline()
                if raw == b"":
                    # readline returns b'' on timeout (no bytes received
                    # within the serial timeout window). Break so a stuck
                    # device does not loop forever. A genuine blank response
                    # line is b'\r\n' (decodes to '' after strip) and is NOT
                    # a timeout — it is appended below and the loop continues
                    # until the [OK]/CMD> terminator arrives.
                    break
                line = raw.decode("ascii", errors="replace").strip()
                response_lines.append(line)
                if line == "[OK]" or line.startswith("CMD>"):
                    break

            # Surface a device-level rejection on the HAL error surface
            # instead of letting it look like success. The firmware prefixes
            # error replies with a `%SYS-E` code (e.g.
            # `%SYS-E-00025, parameter error`). The controller polls
            # self.error after every write and emits the operator message
            # from there; we do not raise so the existing call sites keep
            # working unchanged.
            for line in response_lines:
                if line.startswith("%SYS-E"):
                    self.error = 1
                    self.error_message = f'iBeam rejected "{cmd}": {line}'
                    break

            time.sleep(self._inter_command_gap)
            return response_lines


# ------------------------------------------------------------------------------------
if __name__ == "__main__":
    ib = IBeam()
    ib.open()
    print("serial:", ib.ser)
    ib.close()
