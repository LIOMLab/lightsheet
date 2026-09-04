"""
Mock-serial unit tests for the Toptica iBeam Smart HAL driver
(lightsheet/hal/real/ibeam_smart.py).

These tests run on Mac with no physical device: `serial.Serial` is patched so
the IBeam class's serial I/O is captured against MagicMocks. The protocol
assumptions (115200 8-N-1, `laser on`/`laser off`, `channel <ch> power <uW>
micro`, `enable <ch>` per-channel enable, `[OK]`/`CMD>` terminators, `%SYS-E`
firmware error replies) were confirmed against the physical rig on COM4
(iBeam Smart 640, SN iBEAM-SMART-640-S-G1-15601).
"""

from unittest.mock import MagicMock, patch

import lightsheet.hal.real.ibeam_smart as ibeam_mod


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
    with patch("lightsheet.hal.real.ibeam_smart.serial.Serial") as MockSerial:
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
    return written.decode("ascii")  # ty: ignore[unsound-return-statement]


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
    with patch("lightsheet.hal.real.ibeam_smart.serial.Serial") as MockSerial:
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
# Test 13b: on() must NOT set self._is_on = True when 'laser on' is rejected
# but the subsequent 'enable 1' succeeds. This is the WR-01 mixed-rejection
# case: _send_cmd resets self.error=0 at the top of every round-trip, so a
# successful 'enable 1' would clear the 'laser on' rejection and leave the
# HAL believing emission is enabled when the global enable was refused. on()
# must check self.error BETWEEN 'laser on' and enable_channel() and bail
# before re-enabling if 'laser on' was rejected. Safety-relevant (Class IIIB).
# --------------------------------------------------------------------------- #
def test_ibeam_on_rejected_laser_on_but_enable_succeeds() -> None:
    # 'laser on' is rejected (%SYS-E then [OK] terminator); the subsequent
    # 'enable 1' succeeds ([OK]). Today the enable-1 round-trip clears the
    # laser-on rejection (self.error reset to 0 at the top of _send_cmd),
    # so the `if not self.error: self._is_on = True` guard flips _is_on to
    # True even though the global emission enable was refused — the bug.
    ib, _ = _make_open_ibeam(
        readline_side_effect=[
            b"%SYS-E-00030, laser locked\r\n",
            b"[OK]\r\n",
            b"[OK]\r\n",
            b"[OK]\r\n",
        ]
    )
    ib._is_on = False
    ib.on()
    assert ib.error == 1, (
        "on() must surface the 'laser on' rejection on the error surface "
        "even when the subsequent 'enable 1' succeeds — the between-sub-"
        "commands error check must bail before re-enabling"
    )
    assert ib._is_on is False, (
        "on() must not set self._is_on = True when 'laser on' was rejected "
        "but 'enable 1' succeeded — the enable-1 stale-clear must not mask "
        "the laser-on rejection (Class IIIB laser safety)"
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


# --------------------------------------------------------------------------- #
# Test 16: get_output_power() must return None (not the stale commanded
# self._power) when no CH{channel} line is found in the response. Returning
# the stale value would present it as a live readback to the operator. The
# error surface stays 0 (no %SYS-E, no SerialException), so None is the only
# signal the adapter has that the parse did not match.
# --------------------------------------------------------------------------- #
def test_ibeam_get_output_power_returns_none_on_unmatched_response() -> None:
    ib, _ = _make_open_ibeam(readline_side_effect=[b"CMD>\r\n"])
    ib._power = 75000  # pre-seed a known prior power
    result = ib.get_output_power()
    assert result is None, (
        "get_output_power must return None when no CH{channel} line is "
        "found — returning self._power would present the stale commanded "
        "value as a live readback"
    )
    assert ib.error == 0, (
        "no %SYS-E and no SerialException -> error surface stays clean; "
        "the None return is the only parse-failure signal"
    )


def test_ibeam_get_output_power_returns_none_on_empty_response() -> None:
    """An empty reply (readline timeout -> b'' terminator) must return
    None, not the stale commanded value."""
    ib, _ = _make_open_ibeam(readline_side_effect=[b""])
    ib._power = 50000
    result = ib.get_output_power()
    assert result is None
    assert ib.error == 0


def test_ibeam_get_output_power_returns_value_on_matching_line() -> None:
    """Regression guard: the happy path (matching CH1 line) must still
    return the parsed µW value, not None."""
    ib, _ = _make_open_ibeam(
        readline_side_effect=[
            b"CH1, PWR: 75.000 mW\r\n",
            b"CH2, PWR: 150.000 mW\r\n",
            b"CMD>\r\n",
        ]
    )
    result = ib.get_output_power()
    assert result == 75000, (
        f"get_output_power must return 75000 uW from the CH1 line; got {result!r}"
    )


# --------------------------------------------------------------------------- #
# Test 17: set_power clamps to 0 uW on negative input (floor clamp arc).
# --------------------------------------------------------------------------- #
def test_ibeam_set_power_clamps_floor_zero() -> None:
    """set_power(-100) clamps to 0 µW — the floor side of the
    max(0, min(power_uw, max_power)) clamp. The commanded write must
    contain 'channel 1 power 0 micro', not '-100'."""
    ib, mock_ser = _make_open_ibeam(readline_side_effect=[b"[OK]\r\n"])
    ib.set_power(-100)
    text = _last_write_text(mock_ser)
    assert "channel 1 power 0 micro" in text
    assert "-100" not in text
    assert ib._power == 0


# --------------------------------------------------------------------------- #
# Test 18: off() sets _is_on=False and _power=0 even when the serial
# round-trip raises SerialException (the safer-default arc, lines 240-250).
# A Class IIIB laser's off-intent must not be reversed by a serial failure.
# --------------------------------------------------------------------------- #
def test_ibeam_off_sets_safe_defaults_on_serial_exception() -> None:
    """When _send_cmd('laser off') raises serial.SerialException, off()
    must still set _is_on=False (the safer default for a Class IIIB laser
    — the GUI treats the laser as off and the operator is warned to
    manually verify) and set error=1 with the exception message."""
    ib, mock_ser = _make_open_ibeam()
    # Configure the serial to raise SerialException on the next write
    # (the 'laser off' round-trip).
    import serial as serial_mod

    mock_ser.write.side_effect = serial_mod.SerialException("port closed")
    ib._is_on = True
    ib._power = 50000
    ib.off()
    # Safer-default arc: _is_on stays False even though the round-trip
    # failed (operator intent was off).
    assert ib._is_on is False, (
        "off() must set _is_on=False even on a SerialException — the "
        "safer default for a Class IIIB laser is to treat it as off"
    )
    assert ib.error == 1, (
        "off() must set error=1 when the serial round-trip raises so "
        "the operator is warned to manually verify the laser state"
    )
    assert "port closed" in ib.error_message


# --------------------------------------------------------------------------- #
# Test 19: set_power sets error surface on serial exception (lines 290-293).
# The except-SerialException arc in set_power must surface the failure
# rather than let the HAL believe the commanded power was applied.
# --------------------------------------------------------------------------- #
def test_ibeam_set_power_sets_error_on_serial_exception() -> None:
    """When _send_cmd raises serial.SerialException during set_power,
    the except block must set error=1 with the exception message and
    must NOT update _power (the rejection guard on the error surface)."""
    ib, mock_ser = _make_open_ibeam()
    import serial as serial_mod

    mock_ser.write.side_effect = serial_mod.SerialException("port closed")
    ib._power = 12345  # pre-seed a known prior power
    ib.set_power(5000)
    assert ib.error == 1, (
        "set_power must set error=1 when the serial round-trip raises "
        "SerialException — the failure must surface on the HAL error surface"
    )
    assert "port closed" in ib.error_message
    # _power must NOT advance to the rejected 5000 uW.
    assert ib._power == 12345, (
        "set_power must not update self._power when the serial round-trip "
        "raised — the HAL would otherwise believe the commanded power was "
        "applied when the diode state is unknown"
    )


# --------------------------------------------------------------------------- #
# Task 2: Analog modulation setup — exact command sequence, abort-on-rejection.
#
# The rig-measured recipe: CH1=0, CH2=ceiling, enable 1, enable 2, laser on,
# en ext. Every command goes through _send_cmd (RLock, flush, 50ms gap). A
# firmware rejection at any step aborts before later energizing commands.
# --------------------------------------------------------------------------- #
def test_ibeam_analog_setup_command_sequence() -> None:
    """setup_analog_modulation(ch2_power_uw=150000) emits exactly:
    echo off, channel 1 power 0 micro, channel 2 power 150000 micro,
    enable 1, enable 2, laser on, en ext — in that order. Every command
    reaches _send_cmd (RLock, flush, 50ms gap retained)."""
    with patch("lightsheet.hal.real.ibeam_smart.serial.Serial") as MockSerial:
        mock_ser = MagicMock()
        MockSerial.return_value = mock_ser
        mock_ser.readline.return_value = b"[OK]\r\n"
        ib = ibeam_mod.IBeam(port="COM4")
        ib.open_for_analog_setup(ch2_power_uw=150000)
    writes = _write_sequence(mock_ser)
    decoded = [w.rstrip("\r\n") for w in writes]
    # The exact seven-command sequence (echo off is part of open, then the
    # six setup commands).
    assert decoded == [
        "echo off",
        "channel 1 power 0 micro",
        "channel 2 power 150000 micro",
        "enable 1",
        "enable 2",
        "laser on",
        "en ext",
    ], f"analog setup sequence mismatch: {decoded}"
    # No digital-modulation command issued.
    assert not any("modulation" in w for w in decoded), (
        "digital modulation command must not be issued — this unit has no "
        "pulse board (analog modulation is via en ext, not modulation on)"
    )
    # _is_on is set only after the full sequence succeeds.
    assert ib._is_on is True
    assert ib.error == 0


def test_ibeam_analog_setup_aborts_on_rejection() -> None:
    """A firmware rejection at any setup step stops the sequence before
    later energizing commands. If 'channel 2 power 150000 micro' is
    rejected, 'enable 2', 'laser on', and 'en ext' must NOT be issued.
    The error remains visible on the HAL error surface."""
    with patch("lightsheet.hal.real.ibeam_smart.serial.Serial") as MockSerial:
        mock_ser = MagicMock()
        MockSerial.return_value = mock_ser
        # echo off -> [OK], channel 1 power 0 -> [OK], channel 2 power ->
        # %SYS-E rejection, then [OK] terminator.
        mock_ser.readline.side_effect = [
            b"[OK]\r\n",  # echo off
            b"[OK]\r\n",  # channel 1 power 0 micro
            b"%SYS-E-00025, parameter error\r\n",  # channel 2 power rejected
            b"[OK]\r\n",  # terminator
        ]
        ib = ibeam_mod.IBeam(port="COM4")
        ib.open_for_analog_setup(ch2_power_uw=150000)
    writes = _write_sequence(mock_ser)
    decoded = [w.rstrip("\r\n") for w in writes]
    # The sequence aborted after the CH2 rejection — no enable/laser/en ext.
    assert "channel 2 power 150000 micro" in decoded
    assert "enable 2" not in decoded, (
        "setup must abort after CH2 rejection — enable 2 must not be issued"
    )
    assert "laser on" not in decoded, (
        "setup must abort after CH2 rejection — laser on must not be issued"
    )
    assert "en ext" not in decoded, (
        "setup must abort after CH2 rejection — en ext must not be issued"
    )
    assert ib.error == 1
    assert "%SYS-E" in ib.error_message
    # _is_on must NOT be set — the sequence did not complete.
    assert ib._is_on is False


def test_ibeam_smart_laser_forwards_resolved_port() -> None:
    """IBeamSmartLaser accepts an optional port and forwards it to the
    inner IBeam serial engine so DeviceRegistry can supply a resolved port."""
    with patch("lightsheet.hal.real.ibeam_smart.IBeam") as MockIBeam:
        mock_engine = MagicMock()
        MockIBeam.return_value = mock_engine
        # Mock the attributes IBeamSmartLaser reads from the inner engine.
        mock_engine.wavelength = 647
        mock_engine.max_power = 150000
        adapter = ibeam_mod.IBeamSmartLaser(label="Laser 2 (647 nm)", port="COM9")
        assert MockIBeam.call_args.kwargs.get("port") == "COM9"
        assert adapter._ibeam is mock_engine


def test_ibeam_set_channel_power_delegates_to_send_cmd() -> None:
    """set_channel_power(channel=2, power_uw=150000) issues
    'channel 2 power 150000 micro' via _send_cmd and clamps to max_power.
    set_power delegates to set_channel_power without changing standalone
    behavior (channel 1 power <uW> micro)."""
    # Three [OK] responses for the three set_channel_power/set_power calls.
    ib, mock_ser = _make_open_ibeam(
        readline_side_effect=[b"[OK]\r\n", b"[OK]\r\n", b"[OK]\r\n"]
    )
    ib.set_channel_power(channel=2, power_uw=150000)
    text = _last_write_text(mock_ser)
    assert "channel 2 power 150000 micro" in text
    # Clamp still applies.
    ib.set_channel_power(channel=2, power_uw=999999)
    text = _last_write_text(mock_ser)
    assert "150000" in text  # clamped to max_power
    # set_power delegates to set_channel_power with the configured channel.
    ib.set_power(5000)
    text = _last_write_text(mock_ser)
    assert "channel 1 power 5000 micro" in text
