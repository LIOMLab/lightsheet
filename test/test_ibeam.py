"""
Mock-serial unit tests for the Toptica iBeam Smart HAL driver (lightsheet/ibeam.py).

These tests run on Mac with no physical device: `serial.Serial` is patched so
the IBeam class's serial I/O is captured against MagicMocks. The protocol
assumptions (115200 8-N-1, `laser on`/`laser off`, `channel <ch> power <uW>
micro`, `enable <ch>` per-channel enable, `[OK]`/`CMD>` terminators, `%SYS-E`
firmware error replies) were confirmed against the physical rig on COM4
(iBeam Smart 640, SN iBEAM-SMART-640-S-G1-15601).
"""

from unittest.mock import MagicMock, patch

import lightsheet.hal.real.ibeam as ibeam_mod


def _make_open_ibeam(
    readline_value: bytes | None = None,
    readline_side_effect: list[bytes] | None = None,
) -> tuple[ibeam_mod.IBeam, MagicMock]:
    """Construct IBeam(port='COM4') and open() it against a mocked serial.Serial.

    Returns (ibeam, mock_ser). During open() the mock serial's readline returns
    the [OK] terminator so the echo-off handshake exits cleanly; the optional
    readline_side_effect is applied AFTER open() so it is available for the
    test's own _send_cmd / status calls (otherwise open()'s echo-off would
    consume the side_effect list).
    """
    with patch("lightsheet.hal.real.ibeam.serial.Serial") as MockSerial:
        mock_ser = MagicMock()
        MockSerial.return_value = mock_ser
        mock_ser.readline.return_value = b"[OK]\r\n"
        ib = ibeam_mod.IBeam(port="COM4")
        ib.open()
    # Now that open() is done, swap in the test-specific readline behaviour.
    if readline_side_effect is not None:
        mock_ser.readline.side_effect = readline_side_effect
    elif readline_value is not None:
        mock_ser.readline.return_value = readline_value
    return ib, mock_ser


def _last_write_text(mock_ser: MagicMock) -> str:
    """Return the most recent bytes written to the mocked serial as a str."""
    assert mock_ser.write.called, "serial.Serial.write was never called"
    written = mock_ser.write.call_args_list[-1].args[0]
    return written.decode("ascii")


def _write_sequence(mock_ser: MagicMock) -> list[str]:
    """Return the full decoded write sequence, in issue order, as a list of str."""
    return [c.args[0].decode("ascii") for c in mock_ser.write.call_args_list]


# --------------------------------------------------------------------------- #
# Test 1: on() writes `laser on` (and now `enable <ch>`) with CRLF terminators.
# After the channel-enable wiring, the LAST write from on() is `enable 1`, not
# `laser on`, so this asserts on the full write sequence instead of the last
# write.
# --------------------------------------------------------------------------- #
def test_ibeam_on_writes_laser_on_command() -> None:
    ib, mock_ser = _make_open_ibeam()
    ib.on()
    writes = _write_sequence(mock_ser)
    # The writes issued by on() are those after the open() handshake. The
    # open() handshake itself writes `echo off` then `enable 1`, so filter to
    # the laser-on / enable pair that on() appends.
    on_writes = [w for w in writes if "laser on" in w or w.startswith("enable ")]
    assert any("laser on" in w for w in on_writes), f"no laser on write: {on_writes}"
    assert all(w.endswith("\r\n") for w in on_writes), f"missing CRLF: {on_writes}"


# --------------------------------------------------------------------------- #
# Test 2: off() writes `laser off` and toggles _is_on
# --------------------------------------------------------------------------- #
def test_ibeam_off_writes_laser_off_command() -> None:
    ib, mock_ser = _make_open_ibeam()
    ib.on()
    assert ib._is_on is True
    ib.off()
    text = _last_write_text(mock_ser)
    assert "laser off" in text
    assert text.endswith("\r\n")
    assert ib._is_on is False


# --------------------------------------------------------------------------- #
# Test 3: set_power formats `channel <ch> power <uW> micro`
# --------------------------------------------------------------------------- #
def test_ibeam_set_power_formats_micro_command() -> None:
    ib, mock_ser = _make_open_ibeam()
    ib.set_power(5000)
    text = _last_write_text(mock_ser)
    assert "channel 1 power 5000 micro" in text
    assert text.endswith("\r\n")


# --------------------------------------------------------------------------- #
# Test 4: set_power clamps to max_power (HAL-boundary safety control)
# --------------------------------------------------------------------------- #
def test_ibeam_set_power_clamps_to_max_power() -> None:
    ib, mock_ser = _make_open_ibeam()
    # Default max_power from config defaults is 150000 uW (150 mW, rig-confirmed).
    assert ib.max_power == 150000
    ib.set_power(300000)
    text = _last_write_text(mock_ser)
    assert "150000" in text
    assert "300000" not in text
    assert "channel 1 power 150000 micro" in text
    assert ib._power == 150000


# --------------------------------------------------------------------------- #
# Test 5: _send_cmd returns without raising on [OK] terminator and
#         is_enabled() parses an ON/OFF status line.
# --------------------------------------------------------------------------- #
def test_ibeam_response_parsing_ok_terminator() -> None:
    # status laser reply: a status line then the [OK] terminator.
    ib, mock_ser = _make_open_ibeam(readline_side_effect=[b"ON\r\n", b"[OK]\r\n"])
    # _send_cmd should return the collected lines without raising.
    lines = ib._send_cmd("status laser")
    assert "[OK]" in lines
    assert "ON" in lines
    # is_enabled() parses the ON line.
    mock_ser.readline.side_effect = [b"ON\r\n", b"[OK]\r\n"]
    assert ib.is_enabled() is True
    mock_ser.readline.side_effect = [b"OFF\r\n", b"[OK]\r\n"]
    assert ib.is_enabled() is False


# --------------------------------------------------------------------------- #
# Test 6: calling on() with no serial connection sets error state, no raise
# --------------------------------------------------------------------------- #
def test_ibeam_no_serial_connection_sets_error() -> None:
    ib = ibeam_mod.IBeam()  # no open() -> self.ser is None
    assert ib.ser is None
    # Must not raise.
    ib.on()
    assert ib.error == 1
    assert ib.error_message != ""
    assert ib._is_on is False


# --------------------------------------------------------------------------- #
# Test 7: open() sends `echo off` then `enable <ch>` (channel live before any
#         power command can be issued).
# --------------------------------------------------------------------------- #
def test_ibeam_open_sends_enable_channel() -> None:
    with patch("lightsheet.hal.real.ibeam.serial.Serial") as MockSerial:
        mock_ser = MagicMock()
        MockSerial.return_value = mock_ser
        mock_ser.readline.return_value = b"[OK]\r\n"
        ib = ibeam_mod.IBeam(port="COM4")
        ib.open()
    writes = _write_sequence(mock_ser)
    decoded = [w.rstrip("\r\n") for w in writes]
    assert "echo off" in decoded, f"no echo off: {decoded}"
    assert "enable 1" in decoded, f"no enable 1: {decoded}"
    # The channel enable must come AFTER echo off so the channel is live
    # before any subsequent power command reaches the output.
    assert decoded.index("echo off") < decoded.index("enable 1"), decoded


# --------------------------------------------------------------------------- #
# Test 8: on() sends `laser on` then `enable <ch>` (channel re-enabled with
#         each emission enable).
# --------------------------------------------------------------------------- #
def test_ibeam_on_sends_enable_channel() -> None:
    ib, mock_ser = _make_open_ibeam()
    # Snapshot the write count after open() so we can isolate on()'s writes.
    pre_count = len(mock_ser.write.call_args_list)
    ib.on()
    on_writes = _write_sequence(mock_ser)[pre_count:]
    decoded = [w.rstrip("\r\n") for w in on_writes]
    assert "laser on" in decoded, f"no laser on: {decoded}"
    assert "enable 1" in decoded, f"no enable 1: {decoded}"
    # `laser on` must precede `enable 1` so the global emission is on before
    # the channel enable is (re)asserted.
    assert decoded.index("laser on") < decoded.index("enable 1"), decoded
    assert ib._is_on is True
    assert ib.error == 0


# --------------------------------------------------------------------------- #
# Test 9: a `%SYS-E` firmware rejection sets the HAL error surface naming the
#         rejected command, without raising.
# --------------------------------------------------------------------------- #
def test_ibeam_sys_error_response_sets_error() -> None:
    ib, _ = _make_open_ibeam(
        readline_side_effect=[b"%SYS-E-00025, parameter error\r\n", b"[OK]\r\n"]
    )
    # Must not raise; the call simply returns.
    ib.set_power(5000)
    assert ib.error == 1
    assert "%SYS-E" in ib.error_message
    # The error message names the rejected command so the operator can see
    # which write the firmware refused.
    assert "channel 1 power 5000 micro" in ib.error_message


# --------------------------------------------------------------------------- #
# Test 10: set_power must NOT update self._power after a %SYS-E rejection.
# _send_cmd does not raise on a firmware rejection (it sets self.error and
# returns normally), so set_power must guard the internal state update on
# the error surface. Otherwise the HAL records the commanded power as if
# the write succeeded, masking the rejection from a later get_output_power()
# fallback. The max_power clamp must remain intact regardless of rejection.
# --------------------------------------------------------------------------- #
def test_ibeam_set_power_does_not_update_state_on_rejection() -> None:
    ib, _ = _make_open_ibeam(
        readline_side_effect=[b"%SYS-E-00025, parameter error\r\n", b"[OK]\r\n"]
    )
    # Pre-seed a known prior power so we can prove it is unchanged.
    ib._power = 12345
    ib.set_power(5000)
    assert ib.error == 1, "rejection should set the error surface"
    # The internal power state must NOT advance to the rejected 5000 uW.
    assert ib._power == 12345, (
        "set_power must not update self._power when the firmware rejected "
        "the write — doing so masks the rejection from get_output_power()'s "
        "fallback path"
    )


# --------------------------------------------------------------------------- #
# Test 11: set_power must still update self._power on a successful write
# (regression guard for the WR-01 guard — the happy path must still record).
# --------------------------------------------------------------------------- #
def test_ibeam_set_power_updates_state_on_success() -> None:
    ib, _ = _make_open_ibeam(readline_side_effect=[b"[OK]\r\n"])
    ib._power = 0
    ib.set_power(7500)
    assert ib.error == 0
    assert ib._power == 7500, (
        "set_power must update self._power when the firmware accepts the write"
    )


# --------------------------------------------------------------------------- #
# Test 12: on() must NOT set self._is_on = True when 'laser on' is rejected.
# _send_cmd('laser on') sets self.error on a %SYS-E reply without raising,
# so on() must guard the _is_on update on the error surface to avoid the
# HAL believing emission is enabled when the firmware refused.
# --------------------------------------------------------------------------- #
def test_ibeam_on_does_not_set_is_on_on_rejection() -> None:
    # 'laser on' is rejected; the subsequent enable_channel() also reads a
    # rejection so the error surface stays set across both writes.
    ib, _ = _make_open_ibeam(
        readline_side_effect=[
            b"%SYS-E-00030, laser locked\r\n",
            b"[OK]\r\n",
            b"%SYS-E-00030, laser locked\r\n",
            b"[OK]\r\n",
        ]
    )
    ib._is_on = False
    ib.on()
    assert ib.error == 1, "rejection should set the error surface"
    assert ib._is_on is False, (
        "on() must not set self._is_on = True when 'laser on' was rejected "
        "by the firmware — the HAL would otherwise believe emission is "
        "enabled when the diode is dark"
    )


# --------------------------------------------------------------------------- #
# Test 13: on() must still set self._is_on = True on a successful write
# (regression guard for the WR-02 guard).
# --------------------------------------------------------------------------- #
def test_ibeam_on_sets_is_on_on_success() -> None:
    ib, _ = _make_open_ibeam(readline_side_effect=[b"[OK]\r\n", b"[OK]\r\n"])
    ib._is_on = False
    ib.on()
    assert ib.error == 0
    assert ib._is_on is True, (
        "on() must set self._is_on = True when the firmware accepts 'laser on'"
    )


# --------------------------------------------------------------------------- #
# Test 14: _send_cmd must clear a stale self.error on a successful command.
# Without this, a stale error from a prior failed command persists across
# later successful commands and is mistaken for a current-call failure by
# any caller that checks the error surface after _send_cmd returns.
# --------------------------------------------------------------------------- #
def test_ibeam_send_cmd_clears_stale_error_on_success() -> None:
    ib, _ = _make_open_ibeam(readline_side_effect=[b"[OK]\r\n"])
    # Plant a stale error from a hypothetical prior failed command.
    ib.error = 1
    ib.error_message = "stale prior failure"
    # A successful command must reset the error surface before the round-trip
    # so the post-call error state reflects THIS command only.
    ib._send_cmd("status laser")
    assert ib.error == 0, (
        "_send_cmd must clear a stale self.error at the top of a successful "
        "round-trip so a prior failure does not leak into the current call's "
        "error surface"
    )
    assert ib.error_message == "", (
        "_send_cmd must clear a stale self.error_message on a successful round-trip"
    )


# --------------------------------------------------------------------------- #
# Test 15: _send_cmd must (re)set the error surface when the current command
# is rejected, even if the error surface was previously clear. Regression
# guard pairing with the stale-clear: clearing at the top must not prevent
# a fresh rejection from being recorded.
# --------------------------------------------------------------------------- #
def test_ibeam_send_cmd_sets_error_on_fresh_rejection() -> None:
    ib, _ = _make_open_ibeam(
        readline_side_effect=[b"%SYS-E-00099, rejected\r\n", b"[OK]\r\n"]
    )
    assert ib.error == 0  # precondition: clean surface
    ib._send_cmd("status laser")
    assert ib.error == 1, (
        "_send_cmd must set self.error when the current command is rejected, "
        "even though it clears the surface at the top of the round-trip"
    )
    assert "%SYS-E-00099" in ib.error_message
