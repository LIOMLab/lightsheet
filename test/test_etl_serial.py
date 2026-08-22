"""
Mock-serial unit tests for the Optotune ETL driver (lightsheet/etls.py).

Behavior tests for Optotune._send_cmd serial framing. These run on Mac with
no physical device: the serial port is a MagicMock attached after constructing
the Optotune via __new__ (bypassing connect()), so the pure protocol logic in
_send_cmd is exercised in isolation.

The protocol assumptions (115200 8-N-1, `\\r\\n` terminator, CRC-16 with
polynomial 0xA001, `E`-prefixed firmware error replies) follow the Optotune
EL-10-30 serial protocol.
"""

from unittest.mock import MagicMock

import lightsheet.etls as etls_mod


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
