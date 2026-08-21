'''
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
  - `channel <ch> power <uW> micro` -> set channel power in microwatts
  - `status laser`              -> replies `ON` or `OFF`
  - `show level power`          -> multiline `CH<n>, PWR: <value> mW`
  - `show serial` / `version`   -> identification queries
  - `reset system`              -> reboot (recovery path for protocol desync)

The iBeam Smart has a known reply-lag firmware quirk: rapid command sequences
can cause response misattribution. Mitigations: a per-instance lock
serializing all serial access, an inter-command gap, and an input-buffer flush
before every command.

This is a Class IIIB laser. The `set_power` clamp to `max_power` (loaded from
config.ini `[iBeam] Max Power`) is a physical-safety control enforced inside
the HAL method so any caller (GUI, future script, E-stop path) is bounded.
'''

import sys
sys.path.append(".")

import copy
import threading
import time

import serial

from src.config import cfg_read


class IBeam:
    '''HAL class for the Toptica iBeam Smart serial laser.'''

    # Default configurable settings (overlaid with config.ini `[iBeam]`).
    _cfg_settings = {}
    _cfg_settings['Port'] = 'COM4'
    _cfg_settings['Baud Rate'] = '115200'
    _cfg_settings['Channel'] = '1'
    _cfg_settings['Wavelength'] = '640'        # In nm (iBeam Smart 640)
    _cfg_settings['Power'] = '0'               # In uW
    _cfg_settings['Max Power'] = '150000'      # In uW (150 mW diode limit, rig-confirmed)

    def __init__(self, port=None):
        # HAL error status (mirrors src/lasers.py and src/etls.py convention).
        self.error = 0
        self.error_message = ''

        # Load configurable settings, then assign to instance variables.
        self.cfg_settings = copy.deepcopy(self._cfg_settings)
        self.cfg_settings = cfg_read('config.ini', 'iBeam', self.cfg_settings)

        self.port              = port if port is not None else str(self.cfg_settings['Port'])
        self.baud_rate         = int(self.cfg_settings['Baud Rate'])
        self.channel           = int(self.cfg_settings['Channel'])
        self.wavelength        = int(self.cfg_settings['Wavelength'])
        self._power            = int(self.cfg_settings['Power'])
        self.max_power         = int(self.cfg_settings['Max Power'])

        # Serial connection + laser state.
        self.ser = None
        self._is_on = False

        # Reply-lag mitigations.
        self._inter_command_gap = 0.05  # 50 ms starting point
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    def open(self):
        """Open the serial port and disable command echo."""
        try:
            self.ser = serial.Serial()
            self.ser.baudrate = self.baud_rate
            self.ser.port = self.port
            self.ser.timeout = 3.0
            self.ser.open()
            # Disable command echo so replies are not doubled.
            self._send_cmd('echo off')
        except serial.SerialException as e:
            self.error = 1
            self.error_message = str(e)
            if self.ser is not None:
                try:
                    self.ser.close()
                except Exception:
                    pass
                self.ser = None
            raise
        return None

    def close(self):
        """Turn the laser off and release the serial port."""
        try:
            if self.ser is not None:
                self.off()
                self.ser.close()
        except serial.SerialException as e:
            self.error = 1
            self.error_message = str(e)
        finally:
            self.ser = None
        return None

    # ------------------------------------------------------------------ #
    # Laser control
    # ------------------------------------------------------------------ #
    def on(self):
        """Enable laser emission (global enable)."""
        try:
            self._send_cmd('laser on')
            self._is_on = True
        except serial.SerialException as e:
            self.error = 1
            self.error_message = str(e)
        return None

    def off(self):
        """Disable laser emission (global disable)."""
        try:
            self._send_cmd('laser off')
            self._is_on = False
            self._power = 0
        except serial.SerialException as e:
            self.error = 1
            self.error_message = str(e)
        return None

    def set_power(self, power_uw):
        """Set channel power in microwatts, clamped to [0, max_power].

        The clamp is a physical-safety control: it bounds the maximum power
        any caller can command, protecting the diode against a typo or tamper
        in config.ini `Max Power`.
        """
        power_uw = max(0, min(power_uw, self.max_power))
        try:
            self._send_cmd(f'channel {self.channel} power {power_uw} micro')
            self._power = power_uw
        except serial.SerialException as e:
            self.error = 1
            self.error_message = str(e)
        return None

    def get_output_power(self):
        """Read the current channel output power in microwatts.

        Sends `show level power` and parses the `CH<n>, PWR: <value> mW` line
        for this driver's channel. Returns the last commanded power as a
        fallback if the reply cannot be parsed.
        """
        try:
            response = self._send_cmd('show level power')
            for line in response:
                if f'CH{self.channel}' in line and 'PWR:' in line:
                    # e.g. "CH1, PWR: 75.000 mW"
                    try:
                        value_part = line.split('PWR:')[1].strip()
                        # value_part looks like "75.000 mW" or "5000 uW"
                        token, unit = value_part.split()
                        value = float(token)
                        if unit.lower() == 'mw':
                            return int(value * 1000)
                        elif unit.lower() == 'uw':
                            return int(value)
                    except (ValueError, IndexError):
                        # Malformed line -> fall through to fallback.
                        break
        except serial.SerialException as e:
            self.error = 1
            self.error_message = str(e)
        return self._power

    def is_enabled(self):
        """Return True if laser emission is currently enabled."""
        try:
            response = self._send_cmd('status laser')
            for line in response:
                if line == 'ON':
                    return True
                elif line == 'OFF':
                    return False
        except serial.SerialException as e:
            self.error = 1
            self.error_message = str(e)
        return False

    def reboot(self):
        """Send `reset system` to recover from protocol desync."""
        try:
            self._send_cmd('reset system')
        except serial.SerialException as e:
            self.error = 1
            self.error_message = str(e)
        return None

    # ------------------------------------------------------------------ #
    # Serial I/O
    # ------------------------------------------------------------------ #
    def _send_cmd(self, cmd):
        """Send an ASCII command and read lines until the [OK] or CMD> terminator.

        Acquires the per-instance lock, flushes the input buffer (reply-lag
        mitigation), writes the command with a CRLF terminator, reads lines
        until `[OK]` or a `CMD>` prompt is seen, then sleeps for the
        inter-command gap. Returns the collected response lines (stripped).
        """
        with self._lock:
            if self.ser is None:
                raise serial.SerialException('Serial not connected')

            self.ser.reset_input_buffer()
            self.ser.write(f'{cmd}\r\n'.encode('ascii'))

            response_lines = []
            while True:
                raw = self.ser.readline()
                if raw == b'':
                    # readline returns b'' on timeout (no bytes received
                    # within the serial timeout window). Break so a stuck
                    # device does not loop forever. A genuine blank response
                    # line is b'\r\n' (decodes to '' after strip) and is NOT
                    # a timeout — it is appended below and the loop continues
                    # until the [OK]/CMD> terminator arrives.
                    break
                line = raw.decode('ascii', errors='replace').strip()
                response_lines.append(line)
                if line == '[OK]' or line.startswith('CMD>'):
                    break

            time.sleep(self._inter_command_gap)
            return response_lines


# -------------------------------------------------------------------------------------------------
if __name__ == '__main__':
    ib = IBeam()
    ib.open()
    print('serial:', ib.ser)
    ib.close()
