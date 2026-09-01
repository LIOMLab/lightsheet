"""
Mock-serial unit tests for the Optotune ETL driver (lightsheet/etls.py).

Behavior tests for Optotune._send_cmd serial framing and the full Optotune
command surface (mode, current, gain, limits, firmware queries). These run on
Mac with no physical device: the serial port is a MagicMock attached after
constructing the Optotune via __new__ (bypassing connect()), so the pure
protocol logic in _send_cmd and the command methods is exercised in isolation.

The protocol assumptions (115200 8-N-1, `\\r\\n` terminator, CRC-16 with
polynomial 0xA001, `E`-prefixed firmware error replies) follow the Optotune
EL-10-30 serial protocol.
"""

from unittest.mock import MagicMock

import pytest

import lightsheet.hal.real.etls as etls_mod


def _make_optotune(
    read_until_value: bytes = b"",
) -> tuple[etls_mod.Optotune, MagicMock]:
    """Construct an Optotune without connecting, with a fake serial port.

    Returns (optotune, fake_ser). The fake serial's read_until returns the
    supplied bytes regardless of the terminator argument (MagicMock ignores
    args), so tests can assert on the terminator PASSED to read_until rather
    than on blocking behavior.
    """
    o = etls_mod.Optotune.__new__(etls_mod.Optotune)
    o.port = "COM5"
    o.crc_table = o._init_crc_table()
    o.ser = MagicMock()
    o.ser.read_until.return_value = read_until_value
    o._current = None
    o._current_max = 292.84
    return o, o.ser


def _make_optotune_with_reply(
    reply: bytes,
    include_crc: bool = True,
) -> tuple[etls_mod.Optotune, MagicMock]:
    """Construct an Optotune whose fake serial returns a valid reply.

    If include_crc is True, the reply bytes are padded with a valid CRC
    (computed from the reply content) so the CRC check in _send_cmd passes.
    """
    o, ser = _make_optotune()
    if include_crc:
        content = reply
        crc = o.calc_crc(content)
        ser.read_until.return_value = content + crc + b"\r\n"
    else:
        ser.read_until.return_value = reply
    return o, ser


# --------------------------------------------------------------------------- #
# B-01: read_until must receive a bytes terminator, not str.
# pyserial's read_until compares incoming bytes to the terminator; a str
# terminator never matches, so every command blocks until the 1s serial
# timeout instead of returning on \r\n.
# --------------------------------------------------------------------------- #
def test_send_cmd_passes_bytes_terminator_to_read_until() -> None:
    o, ser = _make_optotune(read_until_value=b"Ready\r\n")
    o.handshake()  # sends b"Start" with include_crc=False, waits for resp
    terminator = ser.read_until.call_args.args[0]
    assert isinstance(terminator, bytes), (
        f"read_until terminator must be bytes, got {type(terminator).__name__}"
    )
    assert terminator == b"\r\n"


# --------------------------------------------------------------------------- #
# B-02: the firmware error-prefix check must detect an 'E' error reply.
# resp_content[0] returns an int on Python 3, so `== b"E"` (bytes) was always
# False — the error check was dead code, silently swallowing device rejections.
# The fix compares the first byte as a bytes slice.
# --------------------------------------------------------------------------- #
def test_send_cmd_raises_on_firmware_error_prefix() -> None:
    o, _ser = _make_optotune(read_until_value=b"Error\r\n")
    # handshake uses include_crc=False, so resp_content = resp = b"Error\r\n"
    # and the error-prefix check must fire on the leading b"E".
    raised = False
    try:
        o.handshake()
    except etls_mod.serial.SerialException:
        raised = True
    assert raised, "firmware error-prefix reply b'E...' was not detected"


# --------------------------------------------------------------------------- #
# Regression: a normal (non-error) reply is returned, not raised on.
# --------------------------------------------------------------------------- #
def test_send_cmd_returns_normal_reply_content() -> None:
    o, _ser = _make_optotune(read_until_value=b"Ready\r\n")
    r = o.handshake()  # include_crc=False -> resp_content = resp
    assert r == b"Ready\r\n"


# --------------------------------------------------------------------------- #
# _send_cmd branch coverage: include_crc default True, wait_for_resp False,
# CRC mismatch, and the no-serial guard.
# --------------------------------------------------------------------------- #
def test_send_cmd_no_serial_raises() -> None:
    """When ser is None, _send_cmd raises SerialException immediately."""
    o, _ = _make_optotune()
    o.ser = None
    with pytest.raises(etls_mod.serial.SerialException):
        o._send_cmd(b"test")


def test_send_cmd_wait_for_resp_false_returns_none() -> None:
    """When wait_for_resp=False, _send_cmd writes and returns None without
    reading a response."""
    o, ser = _make_optotune()
    r = o._send_cmd(b"Aw\x00\x00", wait_for_resp=False)
    assert r is None
    ser.write.assert_called_once()
    ser.read_until.assert_not_called()


def test_send_cmd_crc_mismatch_raises() -> None:
    """When include_crc=True and the response CRC doesn't match the
    computed CRC of the response content, a SerialException is raised."""
    o, ser = _make_optotune()
    # Reply with a bad CRC (0xFF 0xFF won't match the computed CRC).
    ser.read_until.return_value = b"OK" + b"\xff\xff" + b"\r\n"
    with pytest.raises(etls_mod.serial.SerialException, match="CRC mismatch"):
        o._send_cmd(b"test")


def test_send_cmd_include_crc_false_no_crc_check() -> None:
    """When include_crc=False, the response is returned as-is without CRC
    verification (the else branch at line 188)."""
    o, ser = _make_optotune()
    ser.read_until.return_value = b"OK\r\n"
    r = o._send_cmd(b"Start", include_crc=False)
    assert r == b"OK\r\n"


# --------------------------------------------------------------------------- #
# close() branch coverage: soft_close True/False, ser truthy/falsy,
# _current truthy/falsy.
# --------------------------------------------------------------------------- #
def test_close_no_ser_is_noop() -> None:
    """When ser is None/falsy, close() is a no-op."""
    o, _ = _make_optotune()
    o.ser = None
    o.close()  # should not raise
    o.close(soft_close=True)  # should not raise


def test_close_soft_close_false_just_closes_port() -> None:
    """When soft_close=False (default), close() closes the port without
    stepping down current."""
    o, ser = _make_optotune()
    o._current = 100.0
    o.close(soft_close=False)
    ser.close.assert_called_once()
    assert not hasattr(o, "ser") or o.ser is None or ser.close.called


def test_close_soft_close_true_steps_down_current() -> None:
    """When soft_close=True and _current is set, close() steps the current
    down to 0 in 5 halvings before closing the port."""
    o, ser = _make_optotune_with_reply(b"\x00\x00")
    o._current = 100.0
    # The current() calls inside close() use wait_for_resp=False (write
    # path), so no reply is needed for those. The ser.close at the end
    # is the postcondition.
    o.close(soft_close=True)
    ser.close.assert_called_once()
    # After step-down, current(0) is called — verify write was called
    # multiple times (5 halvings + 1 zero + the close).
    assert ser.write.call_count >= 6


def test_close_soft_close_true_no_current_just_closes() -> None:
    """When soft_close=True but _current is None/falsy, the step-down loop
    is skipped and the port is closed directly."""
    o, ser = _make_optotune()
    o._current = None
    o.close(soft_close=True)
    ser.close.assert_called_once()


# --------------------------------------------------------------------------- #
# mode() branch coverage: all 6 set-mode strings, the get-mode path, and
# the invalid-mode raise.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "mode_str,expected_cmd",
    [
        ("sinusoidal", b"MwSA"),
        ("rectangular", b"MwQA"),
        ("current", b"MwDA"),
        ("triangular", b"MwTA"),
        ("focal", b"MwCA"),
        ("analog", b"MwAA"),
    ],
)
def test_mode_set_sends_correct_command(mode_str: str, expected_cmd: bytes) -> None:
    """Each valid mode string sends the correct command bytes and records
    the mode on self._mode."""
    o, ser = _make_optotune()
    # Set path uses _send_cmd with default wait_for_resp=True, so a reply
    # is needed. The reply content doesn't matter for the set path (it
    # doesn't parse the response).
    ser.read_until.return_value = (
        b"\x00\x00\x00\x00" + o.calc_crc(b"\x00\x00\x00\x00") + b"\r\n"
    )
    result = o.mode(mode_str)
    assert result == mode_str
    assert o._mode == mode_str
    # The command bytes were written (with CRC appended).
    written = ser.write.call_args[0][0]
    assert written.startswith(expected_cmd)


def test_mode_get_returns_current_mode() -> None:
    """mode(None) reads the current mode from the device and maps the
    integer response to a mode string."""
    o, ser = _make_optotune()
    # MMA response: r[3] is the mode index. Build a reply where byte 3 = 6
    # (analog mode).
    resp_content = b"\x00\x00\x00\x06"
    crc = o.calc_crc(resp_content)
    ser.read_until.return_value = resp_content + crc + b"\r\n"
    result = o.mode()
    assert result == "analog"
    assert o._mode == "analog"


def test_mode_invalid_raises_value_error() -> None:
    """An unrecognized mode string raises ValueError."""
    o, _ = _make_optotune()
    with pytest.raises(ValueError):
        o.mode("not_a_real_mode")


# --------------------------------------------------------------------------- #
# current() branch coverage: get (value=None) and set (value=float).
# --------------------------------------------------------------------------- #
def test_current_get_reads_current_value() -> None:
    """current(None) sends Ar command and parses the response into mA."""
    o, ser = _make_optotune()
    # Response: r[1:] is 2 bytes, signed big-endian. Set a known value.
    # current = int.from_bytes(r[1:], 'big', signed=True) * _current_max / 4095
    # For 100 mA: data = 100 * 4095 / 292.84 ≈ 1399 → 0x0577
    data = int(100 * 4095 / 292.84)
    resp_content = b"\x00" + data.to_bytes(2, byteorder="big", signed=True)
    crc = o.calc_crc(resp_content)
    ser.read_until.return_value = resp_content + crc + b"\r\n"
    result = o.current()
    assert result == pytest.approx(100.0, rel=0.01)


def test_current_set_writes_and_records_value() -> None:
    """current(value) sends Aw command (no response wait) and records the
    value on self._current."""
    o, ser = _make_optotune()
    ser.read_until.return_value = b""
    result = o.current(50.0)
    assert result == 50.0
    assert o._current == 50.0
    # Aw command was written (with CRC).
    written = ser.write.call_args[0][0]
    assert written.startswith(b"Aw")


# --------------------------------------------------------------------------- #
# current_upper / current_lower: get + set + over-limit raise.
# --------------------------------------------------------------------------- #
def test_current_upper_get_reads_value() -> None:
    o, ser = _make_optotune()
    resp_content = b"\x00\x00\x00" + int(100 * 4095 / 292.84).to_bytes(
        2, byteorder="big", signed=True
    )
    crc = o.calc_crc(resp_content)
    ser.read_until.return_value = resp_content + crc + b"\r\n"
    result = o.current_upper()
    assert result == pytest.approx(100.0, rel=0.01)


def test_current_upper_set_writes_value() -> None:
    o, ser = _make_optotune()
    resp_content = b"\x00\x00\x00" + int(100 * 4095 / 292.84).to_bytes(
        2, byteorder="big", signed=True
    )
    crc = o.calc_crc(resp_content)
    ser.read_until.return_value = resp_content + crc + b"\r\n"
    o.current_upper(100.0)
    written = ser.write.call_args[0][0]
    assert written.startswith(b"CwUA")


def test_current_upper_over_limit_raises() -> None:
    o, _ = _make_optotune()
    with pytest.raises(ValueError, match="maximum output current"):
        o.current_upper(300.0)


def test_current_lower_get_reads_value() -> None:
    o, ser = _make_optotune()
    resp_content = b"\x00\x00\x00" + int(50 * 4095 / 292.84).to_bytes(
        2, byteorder="big", signed=True
    )
    crc = o.calc_crc(resp_content)
    ser.read_until.return_value = resp_content + crc + b"\r\n"
    result = o.current_lower()
    assert result == pytest.approx(50.0, rel=0.01)


def test_current_lower_set_writes_value() -> None:
    o, ser = _make_optotune()
    resp_content = b"\x00\x00\x00" + int(50 * 4095 / 292.84).to_bytes(
        2, byteorder="big", signed=True
    )
    crc = o.calc_crc(resp_content)
    ser.read_until.return_value = resp_content + crc + b"\r\n"
    o.current_lower(50.0)
    written = ser.write.call_args[0][0]
    assert written.startswith(b"CwLA")


def test_current_lower_over_limit_raises() -> None:
    o, _ = _make_optotune()
    with pytest.raises(ValueError, match="maximum output current"):
        o.current_lower(300.0)


# --------------------------------------------------------------------------- #
# gain(): get + set + out-of-range raise.
# --------------------------------------------------------------------------- #
def test_gain_get_reads_value() -> None:
    o, ser = _make_optotune()
    # gain = int.from_bytes(r[2:], 'big') / 100. For gain=2.5: data=250
    resp_content = b"\x00\x00" + (250).to_bytes(2, byteorder="big", signed=False)
    crc = o.calc_crc(resp_content)
    ser.read_until.return_value = resp_content + crc + b"\r\n"
    result = o.gain()
    assert result == pytest.approx(2.5, rel=0.01)


def test_gain_set_returns_status_tuple() -> None:
    o, ser = _make_optotune()
    # Set path returns (status, focal_max, focal_min) from the response.
    resp_content = (
        b"\x00\x01"
        + (1000).to_bytes(2, byteorder="big")
        + (500).to_bytes(2, byteorder="big")
    )
    crc = o.calc_crc(resp_content)
    ser.read_until.return_value = resp_content + crc + b"\r\n"
    result = o.gain(2.0)
    assert isinstance(result, tuple)
    assert len(result) == 3


def test_gain_out_of_range_raises() -> None:
    o, _ = _make_optotune()
    with pytest.raises(ValueError, match="Gain must be between 0 and 5"):
        o.gain(6.0)
    with pytest.raises(ValueError, match="Gain must be between 0 and 5"):
        o.gain(-1.0)


# --------------------------------------------------------------------------- #
# current_max(): get + set + clamp at 292.84.
# --------------------------------------------------------------------------- #
def test_current_max_get_reads_value() -> None:
    o, ser = _make_optotune()
    # current_max = int.from_bytes(r[3:5], 'big', signed=True) / 100
    resp_content = b"\x00\x00\x00" + (29284).to_bytes(2, byteorder="big", signed=True)
    crc = o.calc_crc(resp_content)
    ser.read_until.return_value = resp_content + crc + b"\r\n"
    result = o.current_max()
    assert result == pytest.approx(292.84, rel=0.01)


def test_current_max_set_clamps_to_292_84() -> None:
    o, _ser = _make_optotune_with_reply(b"\x00\x00\x00\x00")
    # Values > 292.84 are clamped to 292.84.
    o.current_max(300.0)
    assert o._current_max == 292.84


def test_current_max_set_normal_value() -> None:
    o, ser = _make_optotune_with_reply(b"\x00\x00\x00\x00")
    o.current_max(200.0)
    assert o._current_max == 200.0
    written = ser.write.call_args[0][0]
    assert written.startswith(b"CwMA")


# --------------------------------------------------------------------------- #
# siggen_upper / siggen_lower / siggen_freq: get + set paths.
# --------------------------------------------------------------------------- #
def test_siggen_upper_get_reads_value() -> None:
    o, ser = _make_optotune()
    resp_content = b"\x00\x00\x00" + int(100 * 4095 / 292.84).to_bytes(
        2, byteorder="big", signed=True
    )
    crc = o.calc_crc(resp_content)
    ser.read_until.return_value = resp_content + crc + b"\r\n"
    result = o.siggen_upper()
    assert result == pytest.approx(100.0, rel=0.01)


def test_siggen_upper_set_writes_value() -> None:
    o, ser = _make_optotune()
    o.siggen_upper(100.0)
    assert o._siggen_upper == 100.0
    written = ser.write.call_args[0][0]
    assert written.startswith(b"PwUA")


def test_siggen_lower_get_reads_value() -> None:
    o, ser = _make_optotune()
    resp_content = b"\x00\x00\x00" + int(50 * 4095 / 292.84).to_bytes(
        2, byteorder="big", signed=True
    )
    crc = o.calc_crc(resp_content)
    ser.read_until.return_value = resp_content + crc + b"\r\n"
    result = o.siggen_lower()
    assert result == pytest.approx(50.0, rel=0.01)


def test_siggen_lower_set_writes_value() -> None:
    o, ser = _make_optotune()
    o.siggen_lower(50.0)
    assert o._siggen_lower == 50.0
    written = ser.write.call_args[0][0]
    assert written.startswith(b"PwLA")


def test_siggen_freq_get_reads_value() -> None:
    o, ser = _make_optotune()
    resp_content = b"\x00\x00\x00" + (1000).to_bytes(4, byteorder="big")
    crc = o.calc_crc(resp_content)
    ser.read_until.return_value = resp_content + crc + b"\r\n"
    result = o.siggen_freq()
    assert result == 1000


def test_siggen_freq_set_writes_value() -> None:
    o, ser = _make_optotune()
    o.siggen_freq(500.0)
    assert o._siggen_freq == 500.0
    written = ser.write.call_args[0][0]
    assert written.startswith(b"PwFA")


# --------------------------------------------------------------------------- #
# temp_limits(): get + set + invalid (value[0] > value[1]) raise.
# --------------------------------------------------------------------------- #
def test_temp_limits_get_returns_tuple() -> None:
    o, ser = _make_optotune()
    # Returns (upper, lower) from r[5:7] and r[3:5], each /200 - 5.
    resp_content = (
        b"\x00\x00\x00"
        + (1000).to_bytes(2, byteorder="big", signed=True)
        + (2000).to_bytes(2, byteorder="big", signed=True)
    )
    crc = o.calc_crc(resp_content)
    ser.read_until.return_value = resp_content + crc + b"\r\n"
    result = o.temp_limits()
    assert isinstance(result, tuple)
    assert len(result) == 2


def test_temp_limits_set_writes_and_returns_tuple() -> None:
    o, ser = _make_optotune()
    resp_content = (
        b"\x00\x00\x00"
        + (1000).to_bytes(2, byteorder="big", signed=True)
        + (2000).to_bytes(2, byteorder="big", signed=True)
    )
    crc = o.calc_crc(resp_content)
    ser.read_until.return_value = resp_content + crc + b"\r\n"
    # Use int values — the set path multiplies by 16 and calls to_bytes,
    # which requires int (a pre-existing constraint of the protocol code).
    result = o.temp_limits((10, 20))
    assert isinstance(result, tuple)


def test_temp_limits_invalid_order_raises() -> None:
    o, _ = _make_optotune()
    with pytest.raises(ValueError):
        o.temp_limits((20.0, 10.0))  # upper > lower


# --------------------------------------------------------------------------- #
# focalpower(): get + set paths.
# --------------------------------------------------------------------------- #
def test_focalpower_get_reads_value() -> None:
    o, ser = _make_optotune()
    # focalpower = int.from_bytes(r[2:4], 'big', signed=True) / 200 - 5
    # For 0.0 diopters: data = (0 + 5) * 200 = 1000
    resp_content = b"\x00\x00" + (1000).to_bytes(2, byteorder="big", signed=True)
    crc = o.calc_crc(resp_content)
    ser.read_until.return_value = resp_content + crc + b"\r\n"
    result = o.focalpower()
    assert result == pytest.approx(0.0, abs=0.01)


def test_focalpower_set_writes_value() -> None:
    o, ser = _make_optotune_with_reply(b"\x00\x00\x00\x00")
    o.focalpower(2.0)
    assert o._focalpower == 2.0
    written = ser.write.call_args[0][0]
    assert written.startswith(b"PwDA")


# --------------------------------------------------------------------------- #
# Firmware query methods: handshake, firmwaretype, firmwarebranch,
# partnumber, firmwareversion, deviceid, serialnumber, temp_reading,
# get_status, analog_input.
# --------------------------------------------------------------------------- #
def test_firmwaretype_reads_value() -> None:
    o, ser = _make_optotune()
    resp_content = b"\x00\x03"
    crc = o.calc_crc(resp_content)
    ser.read_until.return_value = resp_content + crc + b"\r\n"
    result = o.firmwaretype()
    assert result == 3


def test_firmwarebranch_reads_value() -> None:
    o, ser = _make_optotune()
    resp_content = b"\x00\x02"
    crc = o.calc_crc(resp_content)
    ser.read_until.return_value = resp_content + crc + b"\r\n"
    result = o.firmwarebranch()
    assert result == 2


def test_partnumber_reads_value() -> None:
    o, ser = _make_optotune()
    resp_content = b"\x00\x01\x02\x03"
    crc = o.calc_crc(resp_content)
    ser.read_until.return_value = resp_content + crc + b"\r\n"
    result = o.partnumber()
    assert result == b"\x01\x02\x03"


def test_firmwareversion_reads_string() -> None:
    o, ser = _make_optotune()
    resp_content = (
        b"\x00\x01\x02"
        + (3).to_bytes(2, byteorder="big")
        + (4).to_bytes(3, byteorder="big")
    )
    crc = o.calc_crc(resp_content)
    ser.read_until.return_value = resp_content + crc + b"\r\n"
    result = o.firmwareversion()
    assert isinstance(result, str)


def test_deviceid_reads_value() -> None:
    o, ser = _make_optotune()
    resp_content = b"\x00\x00\x01\x02\x03\x04"
    crc = o.calc_crc(resp_content)
    ser.read_until.return_value = resp_content + crc + b"\r\n"
    result = o.deviceid()
    assert result == b"\x01\x02\x03\x04"


def test_serialnumber_reads_value() -> None:
    o, ser = _make_optotune()
    resp_content = b"\x00\x01\x02\x03"
    crc = o.calc_crc(resp_content)
    ser.read_until.return_value = resp_content + crc + b"\r\n"
    result = o.serialnumber()
    assert result == b"\x01\x02\x03"


def test_temp_reading_reads_value() -> None:
    o, ser = _make_optotune()
    # temp = int.from_bytes(r[3:5], 'big', signed=True) * 0.0625
    # For 20°C: 20 / 0.0625 = 320 → 0x0140
    resp_content = b"\x00\x00\x00" + (320).to_bytes(2, byteorder="big", signed=True)
    crc = o.calc_crc(resp_content)
    ser.read_until.return_value = resp_content + crc + b"\r\n"
    result = o.temp_reading()
    assert result == pytest.approx(20.0, abs=0.01)


def test_get_status_reads_value() -> None:
    o, ser = _make_optotune()
    resp_content = b"\x00\x01\x02"
    crc = o.calc_crc(resp_content)
    ser.read_until.return_value = resp_content + crc + b"\r\n"
    result = o.get_status()
    assert result == b"\x01\x02"


def test_analog_input_reads_value() -> None:
    o, ser = _make_optotune()
    resp_content = b"\x00\x00\x00" + (1024).to_bytes(2, byteorder="big", signed=False)
    crc = o.calc_crc(resp_content)
    ser.read_until.return_value = resp_content + crc + b"\r\n"
    result = o.analog_input()
    assert result == 1024


# --------------------------------------------------------------------------- #
# EEPROM read/write: command framing.
# --------------------------------------------------------------------------- #
def test_eeprom_read_returns_byte() -> None:
    o, ser = _make_optotune()
    resp_content = b"\x00\x42"
    crc = o.calc_crc(resp_content)
    ser.read_until.return_value = resp_content + crc + b"\r\n"
    result = o.eeprom_read(0x10)
    assert result == 0x42


def test_eeprom_write_returns_byte() -> None:
    o, ser = _make_optotune()
    resp_content = b"\x00\x42"
    crc = o.calc_crc(resp_content)
    ser.read_until.return_value = resp_content + crc + b"\r\n"
    result = o.eeprom_write(0x10, 0x20)
    assert result == 0x42


def test_eeprom_contents_returns_bytes() -> None:
    o, ser = _make_optotune()
    resp_content = b"\x00\x01\x02\x03"
    crc = o.calc_crc(resp_content)
    ser.read_until.return_value = resp_content + crc + b"\r\n"
    result = o.eeprom_contents()
    assert result == b"\x01\x02\x03"


# --------------------------------------------------------------------------- #
# _send_cmd_resp: the None-response guard raises SerialException.
# --------------------------------------------------------------------------- #
def test_send_cmd_resp_raises_on_none_response() -> None:
    """When _send_cmd returns None (shouldn't happen with wait_for_resp=True
    by default, but the guard exists), _send_cmd_resp raises."""
    o, _ = _make_optotune()
    # Force _send_cmd to return None by using wait_for_resp=False internally
    # — but _send_cmd_resp always passes wait_for_resp=True. Instead, patch
    # _send_cmd to return None directly.
    o._send_cmd = lambda *a, **k: None  # ty: ignore[invalid-assignment]
    with pytest.raises(etls_mod.serial.SerialException, match="no response"):
        o._send_cmd_resp(b"test")
