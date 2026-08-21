'''
Mock-serial unit tests for the Toptica iBeam Smart HAL driver (src/ibeam.py).

These tests run on Mac with no physical device: `serial.Serial` is patched so
the IBeam class's serial I/O is captured against MagicMocks. The protocol
assumptions (115200 8-N-1, `laser on`/`laser off`, `channel <ch> power <uW>
micro`, `enable <ch>` per-channel enable, `[OK]`/`CMD>` terminators, `%SYS-E`
firmware error replies) were confirmed against the physical rig on COM4
(iBeam Smart 640, SN iBEAM-SMART-640-S-G1-15601).
'''

import sys
sys.path.append(".")

from unittest.mock import patch, MagicMock

import src.ibeam as ibeam_mod


def _make_open_ibeam(readline_value=None, readline_side_effect=None):
    """Construct IBeam(port='COM4') and open() it against a mocked serial.Serial.

    Returns (ibeam, mock_ser). During open() the mock serial's readline returns
    the [OK] terminator so the echo-off handshake exits cleanly; the optional
    readline_side_effect is applied AFTER open() so it is available for the
    test's own _send_cmd / status calls (otherwise open()'s echo-off would
    consume the side_effect list).
    """
    with patch('src.ibeam.serial.Serial') as MockSerial:
        mock_ser = MagicMock()
        MockSerial.return_value = mock_ser
        mock_ser.readline.return_value = b'[OK]\r\n'
        ib = ibeam_mod.IBeam(port='COM4')
        ib.open()
    # Now that open() is done, swap in the test-specific readline behaviour.
    if readline_side_effect is not None:
        mock_ser.readline.side_effect = readline_side_effect
    elif readline_value is not None:
        mock_ser.readline.return_value = readline_value
    return ib, mock_ser


def _last_write_text(mock_ser):
    """Return the most recent bytes written to the mocked serial as a str."""
    assert mock_ser.write.called, "serial.Serial.write was never called"
    written = mock_ser.write.call_args_list[-1].args[0]
    return written.decode('ascii')


def _write_sequence(mock_ser):
    """Return the full decoded write sequence, in issue order, as a list of str."""
    return [c.args[0].decode('ascii') for c in mock_ser.write.call_args_list]


# --------------------------------------------------------------------------- #
# Test 1: on() writes `laser on` (and now `enable <ch>`) with CRLF terminators.
# After the channel-enable wiring, the LAST write from on() is `enable 1`, not
# `laser on`, so this asserts on the full write sequence instead of the last
# write.
# --------------------------------------------------------------------------- #
def test_ibeam_on_writes_laser_on_command():
    ib, mock_ser = _make_open_ibeam()
    ib.on()
    writes = _write_sequence(mock_ser)
    # The writes issued by on() are those after the open() handshake. The
    # open() handshake itself writes `echo off` then `enable 1`, so filter to
    # the laser-on / enable pair that on() appends.
    on_writes = [w for w in writes if 'laser on' in w or w.startswith('enable ')]
    assert any('laser on' in w for w in on_writes), f"no laser on write: {on_writes}"
    assert all(w.endswith('\r\n') for w in on_writes), f"missing CRLF: {on_writes}"


# --------------------------------------------------------------------------- #
# Test 2: off() writes `laser off` and toggles _is_on
# --------------------------------------------------------------------------- #
def test_ibeam_off_writes_laser_off_command():
    ib, mock_ser = _make_open_ibeam()
    ib.on()
    assert ib._is_on is True
    ib.off()
    text = _last_write_text(mock_ser)
    assert 'laser off' in text
    assert text.endswith('\r\n')
    assert ib._is_on is False


# --------------------------------------------------------------------------- #
# Test 3: set_power formats `channel <ch> power <uW> micro`
# --------------------------------------------------------------------------- #
def test_ibeam_set_power_formats_micro_command():
    ib, mock_ser = _make_open_ibeam()
    ib.set_power(5000)
    text = _last_write_text(mock_ser)
    assert 'channel 1 power 5000 micro' in text
    assert text.endswith('\r\n')


# --------------------------------------------------------------------------- #
# Test 4: set_power clamps to max_power (HAL-boundary safety control)
# --------------------------------------------------------------------------- #
def test_ibeam_set_power_clamps_to_max_power():
    ib, mock_ser = _make_open_ibeam()
    # Default max_power from config defaults is 150000 uW (150 mW, rig-confirmed).
    assert ib.max_power == 150000
    ib.set_power(300000)
    text = _last_write_text(mock_ser)
    assert '150000' in text
    assert '300000' not in text
    assert 'channel 1 power 150000 micro' in text
    assert ib._power == 150000


# --------------------------------------------------------------------------- #
# Test 5: _send_cmd returns without raising on [OK] terminator and
#         is_enabled() parses an ON/OFF status line.
# --------------------------------------------------------------------------- #
def test_ibeam_response_parsing_ok_terminator():
    # status laser reply: a status line then the [OK] terminator.
    ib, mock_ser = _make_open_ibeam(
        readline_side_effect=[b'ON\r\n', b'[OK]\r\n'])
    # _send_cmd should return the collected lines without raising.
    lines = ib._send_cmd('status laser')
    assert '[OK]' in lines
    assert 'ON' in lines
    # is_enabled() parses the ON line.
    mock_ser.readline.side_effect = [b'ON\r\n', b'[OK]\r\n']
    assert ib.is_enabled() is True
    mock_ser.readline.side_effect = [b'OFF\r\n', b'[OK]\r\n']
    assert ib.is_enabled() is False


# --------------------------------------------------------------------------- #
# Test 6: calling on() with no serial connection sets error state, no raise
# --------------------------------------------------------------------------- #
def test_ibeam_no_serial_connection_sets_error():
    ib = ibeam_mod.IBeam()  # no open() -> self.ser is None
    assert ib.ser is None
    # Must not raise.
    ib.on()
    assert ib.error == 1
    assert ib.error_message != ''
    assert ib._is_on is False


# --------------------------------------------------------------------------- #
# Test 7: open() sends `echo off` then `enable <ch>` (channel live before any
#         power command can be issued).
# --------------------------------------------------------------------------- #
def test_ibeam_open_sends_enable_channel():
    with patch('src.ibeam.serial.Serial') as MockSerial:
        mock_ser = MagicMock()
        MockSerial.return_value = mock_ser
        mock_ser.readline.return_value = b'[OK]\r\n'
        ib = ibeam_mod.IBeam(port='COM4')
        ib.open()
    writes = _write_sequence(mock_ser)
    decoded = [w.rstrip('\r\n') for w in writes]
    assert 'echo off' in decoded, f"no echo off: {decoded}"
    assert 'enable 1' in decoded, f"no enable 1: {decoded}"
    # The channel enable must come AFTER echo off so the channel is live
    # before any subsequent power command reaches the output.
    assert decoded.index('echo off') < decoded.index('enable 1'), decoded


# --------------------------------------------------------------------------- #
# Test 8: on() sends `laser on` then `enable <ch>` (channel re-enabled with
#         each emission enable).
# --------------------------------------------------------------------------- #
def test_ibeam_on_sends_enable_channel():
    ib, mock_ser = _make_open_ibeam()
    # Snapshot the write count after open() so we can isolate on()'s writes.
    pre_count = len(mock_ser.write.call_args_list)
    ib.on()
    on_writes = _write_sequence(mock_ser)[pre_count:]
    decoded = [w.rstrip('\r\n') for w in on_writes]
    assert 'laser on' in decoded, f"no laser on: {decoded}"
    assert 'enable 1' in decoded, f"no enable 1: {decoded}"
    # `laser on` must precede `enable 1` so the global emission is on before
    # the channel enable is (re)asserted.
    assert decoded.index('laser on') < decoded.index('enable 1'), decoded
    assert ib._is_on is True
    assert ib.error == 0


# --------------------------------------------------------------------------- #
# Test 9: a `%SYS-E` firmware rejection sets the HAL error surface naming the
#         rejected command, without raising.
# --------------------------------------------------------------------------- #
def test_ibeam_sys_error_response_sets_error():
    ib, mock_ser = _make_open_ibeam(
        readline_side_effect=[b'%SYS-E-00025, parameter error\r\n', b'[OK]\r\n'])
    # Must not raise; the call simply returns.
    ib.set_power(5000)
    assert ib.error == 1
    assert '%SYS-E' in ib.error_message
    # The error message names the rejected command so the operator can see
    # which write the firmware refused.
    assert 'channel 1 power 5000 micro' in ib.error_message
