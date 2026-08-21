'''
Mock-serial unit tests for the Toptica iBeam Smart HAL driver (src/ibeam.py).

These tests run on Mac with no physical device: `serial.Serial` is patched so
the IBeam class's serial I/O is captured against MagicMocks. The protocol
assumptions (115200 8-N-1, `laser on`/`laser off`, `channel <ch> power <uW>
micro`, `[OK]`/`CMD>` terminators) were confirmed against the physical rig on
COM4 (iBeam Smart 640, SN iBEAM-SMART-640-S-G1-15601).
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


# --------------------------------------------------------------------------- #
# Test 1: on() writes `laser on` with CRLF terminator
# --------------------------------------------------------------------------- #
def test_ibeam_on_writes_laser_on_command():
    ib, mock_ser = _make_open_ibeam()
    ib.on()
    text = _last_write_text(mock_ser)
    assert 'laser on' in text
    assert text.endswith('\r\n')


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
