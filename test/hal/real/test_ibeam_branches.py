"""Branch-coverage closure for ``lightsheet.hal.real.ibeam_smart``.

Exercises the remaining uncovered branches:
- ``open()`` SerialException with ser not None (close + null out)
- ``close()`` with ser not None + SerialException handler
- ``on()`` SerialException handler
- ``enable_channel()`` SerialException handler
- ``get_output_power()`` mW/uW parsing + ValueError/IndexError + SerialException
- ``is_enabled()`` loop continuation (neither ON nor OFF) + SerialException
- ``reboot()`` SerialException handler

Mock-serial pattern: ``patch("lightsheet.hal.real.ibeam_smart.serial.Serial")``
so the tests run on Mac with no physical iBeam.

Behavior tests (AGENTS.md §5) — every assertion is on a runtime
postcondition (error flag, error message, returned value), never a
static-source grep.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import serial

import lightsheet.hal.real.ibeam_smart as ibeam_mod


def _make_open_ibeam(
    readline_value: bytes | None = None,
    readline_side_effect: list[bytes] | None = None,
) -> tuple[ibeam_mod.IBeam, MagicMock]:
    """Construct IBeam(port='COM4') and open() it against a mocked serial.Serial."""
    with patch("lightsheet.hal.real.ibeam_smart.serial.Serial") as MockSerial:
        mock_ser = MagicMock()
        MockSerial.return_value = mock_ser
        mock_ser.readline.return_value = b"[OK]\r\n"
        ib = ibeam_mod.IBeam(port="COM4")
        ib.open()
    if readline_side_effect is not None:
        mock_ser.readline.side_effect = readline_side_effect
    elif readline_value is not None:
        mock_ser.readline.return_value = readline_value
    return ib, mock_ser


# -- open() SerialException with ser not None -------------------------------


def test_open_serial_exception_with_ser_closes_and_nulls() -> None:
    """open() SerialException when ser is not None -> close ser + set None
    + re-raise (lines 177-181, True branch). The exception must come from
    _send_cmd inside open()'s try block (not from enable_channel, which
    catches its own SerialException)."""
    import pytest

    with patch("lightsheet.hal.real.ibeam_smart.serial.Serial") as MockSerial:
        mock_ser = MagicMock()
        MockSerial.return_value = mock_ser
        mock_ser.readline.return_value = b"[OK]\r\n"
        # First write (echo off) raises — this propagates to open()'s except.
        mock_ser.write.side_effect = serial.SerialException("echo off failed")
        ib = ibeam_mod.IBeam(port="COM4")
        with pytest.raises(serial.SerialException):
            ib.open()
        assert ib.error == 1
        assert ib.ser is None  # nulled out in the except handler


def test_open_serial_exception_with_ser_none_skips_close() -> None:
    """open() SerialException when serial.Serial() itself raises -> ser is
    None -> skip close, just log + re-raise (lines 177->181, False branch)."""
    import pytest

    with patch("lightsheet.hal.real.ibeam_smart.serial.Serial") as MockSerial:
        MockSerial.side_effect = serial.SerialException("port not available")
        ib = ibeam_mod.IBeam(port="COM4")
        with pytest.raises(serial.SerialException):
            ib.open()
        assert ib.error == 1
        assert ib.ser is None  # never set


# -- close() branches -------------------------------------------------------


def test_close_with_ser_calls_off_and_closes() -> None:
    """close() with ser not None calls off() + ser.close() (lines 188-190)."""
    ib, mock_ser = _make_open_ibeam()
    ib.close()
    mock_ser.close.assert_called_once()
    assert ib.ser is None  # nulled in finally


def test_close_serial_exception_sets_error() -> None:
    """close() SerialException sets error + nulls ser (lines 191-196)."""
    ib, mock_ser = _make_open_ibeam()
    mock_ser.close.side_effect = serial.SerialException("close failed")
    ib.close()
    assert ib.error == 1
    assert ib.ser is None  # nulled in finally


def test_close_with_ser_none_is_noop() -> None:
    """close() with ser=None skips the try body (line 188 False branch)."""
    ib, _ = _make_open_ibeam()
    ib.ser = None
    ib.close()  # must not raise
    assert ib.ser is None


# -- on() SerialException handler -------------------------------------------


def test_on_serial_exception_sets_error() -> None:
    """on() SerialException sets error (lines 228-231)."""
    ib, mock_ser = _make_open_ibeam()
    mock_ser.write.side_effect = serial.SerialException("write failed")
    ib.on()
    assert ib.error == 1
    assert "write failed" in ib.error_message


def test_on_laser_ok_but_enable_rejected_does_not_set_is_on() -> None:
    """on() where 'laser on' succeeds but 'enable 1' is rejected (%SYS-E)
    -> error stays set -> `if not self.error:` is False -> skip _is_on=True
    (branch 226->232)."""
    ib, _ = _make_open_ibeam(
        readline_side_effect=[
            b"[OK]\r\n",  # laser on succeeds
            b"%SYS-E-00030, laser locked\r\n",  # enable 1 rejected
            b"[OK]\r\n",
        ]
    )
    ib._is_on = False
    ib.on()
    assert ib.error == 1, "enable rejection should set error"
    assert ib._is_on is False, "on() must not set _is_on when enable_channel rejected"


# -- enable_channel() SerialException handler -------------------------------


def test_enable_channel_serial_exception_sets_error() -> None:
    """enable_channel() SerialException sets error (lines 266-269)."""
    ib, mock_ser = _make_open_ibeam()
    mock_ser.write.side_effect = serial.SerialException("enable failed")
    ib.enable_channel()
    assert ib.error == 1
    assert "enable failed" in ib.error_message


# -- get_output_power() parsing branches -------------------------------------


def test_get_output_power_parses_mw_value() -> None:
    """get_output_power parses 'CH1, PWR: 75.000 mW' -> 75000 µW (line 318-319)."""
    ib, _mock_ser = _make_open_ibeam(
        readline_side_effect=[
            b"CH1, PWR: 75.000 mW\r\n",
            b"[OK]\r\n",
        ]
    )
    result = ib.get_output_power()
    assert result == 75000


def test_get_output_power_parses_uw_value() -> None:
    """get_output_power parses 'CH1, PWR: 5000 uW' -> 5000 µW (line 320-321)."""
    ib, _mock_ser = _make_open_ibeam(
        readline_side_effect=[
            b"CH1, PWR: 5000 uW\r\n",
            b"[OK]\r\n",
        ]
    )
    result = ib.get_output_power()
    assert result == 5000


def test_get_output_power_malformed_line_returns_none() -> None:
    """A malformed PWR line (ValueError/IndexError) -> break -> None
    (lines 322-324)."""
    ib, _mock_ser = _make_open_ibeam(
        readline_side_effect=[
            b"CH1, PWR: garbage\r\n",
            b"[OK]\r\n",
        ]
    )
    result = ib.get_output_power()
    assert result is None


def test_get_output_power_unknown_unit_continues_loop_returns_none() -> None:
    """A CH line with an unknown unit (neither 'mW' nor 'uW') -> neither
    return fires -> for loop continues -> no matching line -> None
    (branch 320->310)."""
    ib, _mock_ser = _make_open_ibeam(
        readline_side_effect=[
            b"CH1, PWR: 75.000 nW\r\n",  # unknown unit
            b"[OK]\r\n",
        ]
    )
    result = ib.get_output_power()
    assert result is None


def test_get_output_power_serial_exception_returns_none() -> None:
    """get_output_power SerialException -> error + None (lines 329-333)."""
    ib, mock_ser = _make_open_ibeam()
    mock_ser.write.side_effect = serial.SerialException("read failed")
    result = ib.get_output_power()
    assert result is None
    assert ib.error == 1


# -- is_enabled() branches --------------------------------------------------


def test_is_enabled_returns_true_on_on() -> None:
    """is_enabled() with 'ON' line returns True (line 340-341)."""
    ib, _mock_ser = _make_open_ibeam(
        readline_side_effect=[
            b"ON\r\n",
            b"[OK]\r\n",
        ]
    )
    assert ib.is_enabled() is True


def test_is_enabled_returns_false_on_off() -> None:
    """is_enabled() with 'OFF' line returns False (line 342-343)."""
    ib, _mock_ser = _make_open_ibeam(
        readline_side_effect=[
            b"OFF\r\n",
            b"[OK]\r\n",
        ]
    )
    assert ib.is_enabled() is False


def test_is_enabled_returns_false_on_unknown_lines() -> None:
    """is_enabled() with neither ON nor OFF -> loop exhausts -> False
    (line 342->339 continuation + line 348)."""
    ib, _mock_ser = _make_open_ibeam(
        readline_side_effect=[
            b"UNKNOWN\r\n",
            b"[OK]\r\n",
        ]
    )
    assert ib.is_enabled() is False


def test_is_enabled_serial_exception_returns_false() -> None:
    """is_enabled() SerialException -> error + False (lines 344-348)."""
    ib, mock_ser = _make_open_ibeam()
    mock_ser.write.side_effect = serial.SerialException("status failed")
    assert ib.is_enabled() is False
    assert ib.error == 1


# -- reboot() SerialException handler ---------------------------------------


def test_reboot_serial_exception_sets_error() -> None:
    """reboot() SerialException sets error (lines 352-358)."""
    ib, mock_ser = _make_open_ibeam()
    mock_ser.write.side_effect = serial.SerialException("reset failed")
    ib.reboot()
    assert ib.error == 1
    assert "reset failed" in ib.error_message


def test_reboot_sends_reset_system() -> None:
    """reboot() sends 'reset system' command on success."""
    ib, mock_ser = _make_open_ibeam(readline_side_effect=[b"[OK]\r\n"])
    ib.reboot()
    writes = [c.args[0].decode("ascii") for c in mock_ser.write.call_args_list]
    assert any("reset system" in w for w in writes)
