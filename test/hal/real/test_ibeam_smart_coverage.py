"""Branch-coverage closure for ``lightsheet.hal.real.ibeam_smart``.

Covers the remaining early-return branches in
``IBeam.open_for_analog_setup`` (lines 158, 163, 172, 175, 180, 187) and
the ``except serial.SerialException`` handler (lines 190-198).

The analog-modulation setup sequence sends seven commands in order:
``echo off``, ``channel 1 power 0 micro``, ``channel 2 power <ceil> micro``,
``enable 1``, ``enable 2``, ``laser on``, ``en ext``. After each
``_send_cmd``, ``if self.error: return`` aborts the sequence before the
next energizing command. The existing ``test_ibeam.py`` covers the CH2
rejection (line 168); this file covers the OTHER five early-return
branches plus the SerialException handler.

Mock-serial pattern: ``patch("lightsheet.hal.real.ibeam_smart.serial.Serial")``
so the tests run on Mac with no physical iBeam (AGENTS.md §3).

Behavior tests (AGENTS.md §5) — every assertion is on a runtime
postcondition (error flag, error message, command sequence, _is_on),
never a static-source grep.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import serial

import lightsheet.hal.real.ibeam_smart as ibeam_mod

# The seven commands open_for_analog_setup sends, in order. Each
# parametrized case rejects one of them (except CH2, already covered by
# test_ibeam.py) and asserts the sequence aborted before the NEXT
# command. The "next" command is the one that must NOT appear in the
# write sequence — it is the first energizing/setup step after the
# rejected one.
_ANALOG_SETUP_COMMANDS = [
    "echo off",
    "channel 1 power 0 micro",
    "channel 2 power 150000 micro",
    "enable 1",
    "enable 2",
    "laser on",
    "en ext",
]


def _write_sequence(mock_ser: MagicMock) -> list[str]:
    """Return the decoded (CRLF-stripped) commands written to mock_ser."""
    return [
        c.args[0].decode("ascii").rstrip("\r\n") for c in mock_ser.write.call_args_list
    ]


def _rejection_at_step(reject_step: int) -> list[bytes]:
    """Build a readline side_effect that returns [OK] for steps before
    ``reject_step`` (0-indexed), a %SYS-E rejection for step
    ``reject_step``, then an [OK] terminator."""
    side_effect: list[bytes] = []
    for _i in range(reject_step):
        side_effect.append(b"[OK]\r\n")
    side_effect.append(b"%SYS-E-00025, parameter error\r\n")
    side_effect.append(b"[OK]\r\n")  # terminator after the rejection line
    return side_effect


@pytest.mark.parametrize(
    "reject_step, must_not_appear_after",
    [
        # echo off rejected -> return at line 158 -> nothing after echo off
        (0, "channel 1 power 0 micro"),
        # channel 1 power 0 micro rejected -> return at line 163
        (1, "channel 2 power 150000 micro"),
        # enable 1 rejected -> return at line 172
        (3, "enable 2"),
        # enable 2 rejected -> return at line 175
        (4, "laser on"),
        # laser on rejected -> return at line 180
        (5, "en ext"),
        # en ext rejected -> return at line 187 (no _is_on=True)
        (6, "__en_ext_is_last__"),
    ],
    ids=[
        "echo_off_rejected",
        "ch1_power_rejected",
        "enable_1_rejected",
        "enable_2_rejected",
        "laser_on_rejected",
        "en_ext_rejected",
    ],
)
def test_open_for_analog_setup_aborts_at_each_step(
    reject_step: int, must_not_appear_after: str
) -> None:
    """A firmware rejection at each setup step (except CH2, already
    covered) aborts the sequence before the next command. The rejected
    command IS sent; every command AFTER it is NOT. ``_is_on`` stays
    False because the sequence did not complete."""
    with patch("lightsheet.hal.real.ibeam_smart.serial.Serial") as MockSerial:
        mock_ser = MagicMock()
        MockSerial.return_value = mock_ser
        mock_ser.readline.side_effect = _rejection_at_step(reject_step)
        ib = ibeam_mod.IBeam(port="COM4")
        ib.open_for_analog_setup(ch2_power_uw=150000)
    writes = _write_sequence(mock_ser)
    decoded = [w.rstrip("\r\n") for w in writes]

    # The rejected command itself was sent.
    assert _ANALOG_SETUP_COMMANDS[reject_step] in decoded, (
        f"rejected command {_ANALOG_SETUP_COMMANDS[reject_step]!r} must be sent"
    )
    # The next command after the rejected one must NOT appear.
    if must_not_appear_after != "__en_ext_is_last__":
        assert must_not_appear_after not in decoded, (
            f"sequence must abort after step {reject_step} — "
            f"{must_not_appear_after!r} must not be issued"
        )
    # _is_on stays False — the sequence did not complete.
    assert ib._is_on is False, (
        "open_for_analog_setup must not set _is_on when a step was rejected"
    )
    assert ib.error == 1
    assert "%SYS-E" in ib.error_message


def test_open_for_analog_setup_serial_exception_handler() -> None:
    """A ``serial.SerialException`` raised inside the try block (e.g. the
    serial port open fails) is caught by the ``except
    serial.SerialException`` handler (lines 190-198): error is set, the
    serial port is closed + nulled out, the exception is logged and
    re-raised.

    The exception is raised by making ``serial.Serial()`` itself raise
    (the port open fails before any command is sent), so the handler's
    close+null+re-raise path is exercised."""
    with patch("lightsheet.hal.real.ibeam_smart.serial.Serial") as MockSerial:
        mock_ser = MagicMock()
        MockSerial.return_value = mock_ser
        # The serial port open() raises -> the except handler fires.
        mock_ser.open.side_effect = serial.SerialException("port open failed")
        ib = ibeam_mod.IBeam(port="COM4")
        with pytest.raises(serial.SerialException):
            ib.open_for_analog_setup(ch2_power_uw=150000)
    assert ib.error == 1
    assert "port open failed" in ib.error_message
    # The handler closes + nulls the serial port.
    assert ib.ser is None


def test_open_for_analog_setup_serial_exception_ser_none() -> None:
    """The ``except serial.SerialException`` handler's FALSE branch of
    ``if self.ser is not None:`` (line 193->197) — when the
    ``SerialException`` is raised by ``serial.Serial()`` itself (before
    ``self.ser`` is assigned), ``self.ser`` is still ``None`` from
    ``__init__`` so the close+null block is skipped and the handler
    falls straight to ``logger.exception`` + re-raise.

    This is the branch the sibling test
    (test_open_for_analog_setup_serial_exception_handler) does NOT cover:
    that test makes ``open()`` raise AFTER ``self.ser`` is assigned, so
    the TRUE branch (close+null) fires. Here ``serial.Serial()`` itself
    raises, so ``self.ser`` stays ``None`` and the FALSE branch fires."""
    with patch("lightsheet.hal.real.ibeam_smart.serial.Serial") as MockSerial:
        # serial.Serial() itself raises — self.ser is never assigned,
        # so it stays None (from __init__) when the handler runs.
        MockSerial.side_effect = serial.SerialException("no such port: COM4")
        ib = ibeam_mod.IBeam(port="COM4")
        # Sanity: __init__ leaves ser as None.
        assert ib.ser is None
        with pytest.raises(serial.SerialException):
            ib.open_for_analog_setup(ch2_power_uw=150000)
    # The handler sets the error surface and re-raises; with ser already
    # None, the close+null block is skipped (FALSE branch 193->197).
    assert ib.error == 1
    assert "no such port: COM4" in ib.error_message
    # ser was never assigned, so it is still None — no close attempted.
    assert ib.ser is None
