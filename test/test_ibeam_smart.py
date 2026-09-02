"""Mock-serial behavior tests for the IBeamSmartLaser adapter
(lightsheet/hal/real/ibeam_smart.py).

``IBeamSmartLaser`` is the ``ILaser``-shaped adapter that wraps the existing,
rig-confirmed ``IBeam`` serial driver. This is a **re-wrap, not a rewrite**:
every serial round-trip is delegated to the unmodified inner ``IBeam`` engine
(per-instance lock, 50 ms inter-command gap, input-buffer flush — the reply-lag
mitigations validated at 0/12 misattribution at 1 s and 0.5 s cadence on COM4).

These tests run on Mac with no physical device: ``lightsheet.hal.real.ibeam_smart.
serial.Serial`` is patched the same way ``test_ibeam.py`` patches it, so the
inner ``IBeam``'s serial I/O is captured against MagicMocks. The adapter's
mW<->µW conversion, lock identity, synchronous ``off()``, and error-surface
mirroring are asserted on the adapter surface the controller will actually
call.

**Safety (AGENTS.md §2):**
- ``off()`` MUST be synchronous — set ``active=False`` and ``power=0.0`` and
  return ``None`` immediately, no thread/queue offload. The E-stop kill path
  drives ``laser.off()`` on the GUI thread.
- ``set_power`` MUST clamp to ``max_power`` at the HAL boundary (mW canonical
  at the adapter, µW clamp still applies independently inside the inner
  ``IBeam`` — two-layer clamp).

This is a BEHAVIOR test (AGENTS.md §5) — no static-source grep.
"""

import threading
from unittest.mock import MagicMock, patch

import pytest

import lightsheet.hal.real.ibeam_smart as ibeam_smart_mod


def _make_open_ibeam_smart(
    readline_value: bytes | None = None,
    readline_side_effect: list[bytes] | None = None,
) -> tuple[ibeam_smart_mod.IBeamSmartLaser, MagicMock]:
    """Construct ``IBeamSmartLaser()`` and open its inner ``IBeam`` against a
    mocked ``serial.Serial``.

    Returns ``(adapter, mock_ser)``. During the inner ``open()`` the mock
    serial's readline returns the ``[OK]`` terminator so the echo-off +
    enable-channel handshake exits cleanly; the optional ``readline_side_effect``
    is applied AFTER ``open()`` so it is available for the test's own
    adapter-method calls (otherwise open()'s handshake would consume the
    side_effect list).

    ``IBeam.__init__`` does not call ``open()`` — the adapter constructs the
    inner ``IBeam`` but does not open the serial port. The test calls
    ``adapter._ibeam.open()`` under the patch so the inner engine's serial
    I/O is mocked for the subsequent adapter-method round-trips.
    """
    with patch("lightsheet.hal.real.ibeam_smart.serial.Serial") as MockSerial:
        mock_ser = MagicMock()
        MockSerial.return_value = mock_ser
        mock_ser.readline.return_value = b"[OK]\r\n"
        adapter = ibeam_smart_mod.IBeamSmartLaser()
        adapter._ibeam.open()
    # Swap in the test-specific readline behaviour for the adapter calls.
    if readline_side_effect is not None:
        mock_ser.readline.side_effect = readline_side_effect
    elif readline_value is not None:
        mock_ser.readline.return_value = readline_value
    return adapter, mock_ser


def _last_write_text(mock_ser: MagicMock) -> str:
    """Return the most recent bytes written to the mocked serial as a str."""
    assert mock_ser.write.called, "serial.Serial.write was never called"
    written = mock_ser.write.call_args_list[-1].args[0]
    return written.decode("ascii")  # ty: ignore[unsound-return-statement]


class _ToggleEvent(threading.Event):
    """threading.Event that returns a canned is_set() sequence for tests.

    Each call to ``is_set()`` pops the next value from the reversed list.
    After the sequence is exhausted it returns ``False``.
    """

    def __init__(self, values: list[bool]) -> None:
        super().__init__()
        self._values = list(reversed(values))

    def is_set(self) -> bool:
        if not self._values:
            return False
        return self._values.pop()


# --------------------------------------------------------------------------- #
# Construction: mW-canonical attrs, lock identity, default state.
# --------------------------------------------------------------------------- #
def test_ibeam_smart_construction_mw_canonical_and_lock_identity() -> None:
    """``IBeamSmartLaser()`` constructs the inner ``IBeam`` and exposes the
    mW-canonical ``ILaser`` surface: ``wavelength`` (647 nm, the recorded
    capture wavelength from the inner iBeam self-report), ``max_power``
    (150.0 mW = 150000 uW / 1000), ``power``
    (0.0 mW), ``active`` (False), ``error`` (0). The adapter's ``_lock`` IS
    the inner ``IBeam._lock`` (lock identity — not a new lock) so the
    daemon-thread write paths that acquire ``self.lasers[i]._lock`` and the
    inner ``_send_cmd`` lock are the same object.
    """
    adapter = ibeam_smart_mod.IBeamSmartLaser()
    # mW-canonical surface (D-01).
    assert adapter.wavelength == 647
    assert adapter.max_power == 150.0  # 150000 uW / 1000
    assert adapter.power == 0.0
    assert adapter.active is False
    assert adapter.error == 0
    assert adapter.error_message == ""
    assert adapter.label == "Laser 2 (647 nm)"
    # Lock identity: the adapter's lock IS the inner IBeam's lock (D-02).
    # Not a new lock — the daemon-thread write path acquires the same lock
    # the inner _send_cmd acquires.
    assert adapter._lock is adapter._ibeam._lock, (
        "IBeamSmartLaser._lock must be the SAME object as the inner "
        "IBeam._lock (lock identity requirement) — not a new lock"
    )


# --------------------------------------------------------------------------- #
# set_power: mW -> uW conversion, two-layer clamp, error-guarded state mirror.
# --------------------------------------------------------------------------- #
def test_ibeam_smart_set_power_converts_mw_to_uw_and_mirrors_on_success() -> None:
    """``set_power(75.0)`` calls the inner ``IBeam.set_power(75000)`` (mW * 1000
    -> µW). On success (inner ``error == 0``) the adapter mirrors
    ``self.power = 75.0`` (mW canonical)."""
    adapter, mock_ser = _make_open_ibeam_smart(readline_side_effect=[b"[OK]\r\n"])
    adapter.set_power(75.0)
    text = _last_write_text(mock_ser)
    assert "channel 1 power 75000 micro" in text, (
        f"set_power(75.0 mW) must issue 'channel 1 power 75000 micro' "
        f"(mW * 1000 -> uW); got {text!r}"
    )
    assert adapter._ibeam.error == 0
    assert adapter.power == 75.0, (
        "set_power must mirror self.power = mw (mW) on a successful inner write"
    )


def test_ibeam_smart_set_power_clamps_mw_at_adapter_layer() -> None:
    """``set_power(999.0)`` clamps at the adapter's mW layer to
    ``max_power`` (150.0 mW) BEFORE converting to µW. The clamped 150.0 mW
    converts to 150000 µW, which is exactly the inner ``IBeam``'s
    ``max_power`` — so the inner µW clamp is a no-op here but still applies
    independently (two-layer clamp). The adapter mirrors ``power == 150.0``."""
    adapter, mock_ser = _make_open_ibeam_smart(readline_side_effect=[b"[OK]\r\n"])
    adapter.set_power(999.0)
    text = _last_write_text(mock_ser)
    # The adapter clamped 999.0 mW -> 150.0 mW -> 150000 uW before issuing.
    assert "150000" in text, (
        f"set_power(999.0 mW) must clamp to 150.0 mW and issue 150000 micro; "
        f"got {text!r}"
    )
    assert "999000" not in text, (
        "the unclamped 999.0 mW -> 999000 uW must not reach the serial line"
    )
    assert adapter.power == 150.0, (
        "adapter must mirror self.power = 150.0 (clamped mW) on success"
    )


def test_ibeam_smart_set_power_rounds_mw_to_uw_not_truncates() -> None:
    """``set_power(mw)`` converts mW to µW via ``round(mw * 1000)`` rather
    than ``int(mw * 1000)``. A value like 149.9999 mW must convert to
    150000 µW (round-to-nearest), not 149999 µW (truncate toward zero).
    The sub-µW precision difference is below the diode's practical
    resolution and not a safety issue, but round() is the more correct
    conversion for a value (vs an index computation)."""
    adapter, mock_ser = _make_open_ibeam_smart(readline_side_effect=[b"[OK]\r\n"])
    # 149.9999 mW * 1000 = 149999.9 -> round() = 150000, int() = 149999.
    adapter.set_power(149.9999)
    text = _last_write_text(mock_ser)
    assert "150000" in text, (
        f"set_power(149.9999 mW) must round to 150000 uW, not truncate to "
        f"149999 uW; got {text!r}"
    )
    assert "149999" not in text


def test_ibeam_smart_set_power_inner_uw_clamp_still_applies() -> None:
    """Two-layer clamp: even if the adapter's mW clamp is bypassed by a
    subclass or a future refactor, the inner ``IBeam.set_power``'s own µW
    clamp still applies independently. Verify by constructing an adapter
    whose ``max_power`` is artificially raised (so the adapter mW clamp
    lets a too-large value through) and confirming the inner ``IBeam``
    clamps the µW value to its own ``max_power`` (150000 µW)."""
    adapter, mock_ser = _make_open_ibeam_smart(readline_side_effect=[b"[OK]\r\n"])
    # Raise the adapter's mW ceiling so the adapter clamp does not fire.
    adapter.max_power = 999.0
    # 200.0 mW -> 200000 uW; inner IBeam max_power is 150000 uW, so the
    # inner clamp must cut it to 150000 uW.
    adapter.set_power(200.0)
    text = _last_write_text(mock_ser)
    assert "150000" in text, (
        f"inner IBeam.set_power must clamp 200000 uW to its own max_power "
        f"(150000 uW) even when the adapter mW clamp lets the value through; "
        f"got {text!r}"
    )
    assert "200000" not in text


def test_ibeam_smart_set_power_does_not_mirror_on_rejection() -> None:
    """On a firmware rejection (``%SYS-E`` reply -> inner ``error == 1``)
    the adapter MUST NOT update ``self.power`` — the inner ``IBeam.set_power``
    already guards its own ``_power`` on the error surface; the adapter
    mirrors that guard on the mW side so a failed write does not leave the
    adapter believing the commanded power was applied."""
    adapter, _ = _make_open_ibeam_smart(
        readline_side_effect=[b"%SYS-E-00025, parameter error\r\n", b"[OK]\r\n"]
    )
    adapter.power = 12.0  # pre-seed a known prior power
    adapter.set_power(75.0)
    assert adapter._ibeam.error == 1, "inner IBeam should surface the rejection"
    assert adapter.power == 12.0, (
        "set_power must NOT mirror self.power when the inner write was rejected "
        "(the adapter would otherwise believe the commanded power was applied "
        "while the firmware refused — Class IIIB laser safety)"
    )


# --------------------------------------------------------------------------- #
# on(): delegates to inner IBeam.on(), mirrors active/error/error_message.
# --------------------------------------------------------------------------- #
def test_ibeam_smart_on_mirrors_active_on_success() -> None:
    """``on()`` calls ``self._ibeam.on()`` then mirrors ``active`` from the
    inner ``_is_on``. On success (inner ``error == 0``) ``active`` becomes
    ``True``."""
    adapter, _ = _make_open_ibeam_smart(
        readline_side_effect=[b"[OK]\r\n", b"[OK]\r\n", b"[OK]\r\n", b"[OK]\r\n"]
    )
    assert adapter.active is False
    adapter.on()
    assert adapter._ibeam.error == 0
    assert adapter._ibeam._is_on is True
    assert adapter.active is True
    assert adapter.error == 0


def test_ibeam_smart_on_keeps_active_false_on_rejection() -> None:
    """If the inner ``laser on`` is rejected (``%SYS-E``), ``on()`` MUST NOT
    set ``active = True`` — the inner ``IBeam.on()`` guards ``_is_on`` on the
    error surface, and the adapter mirrors that guard on ``active`` so the
    GUI never shows the laser as energized when the firmware refused."""
    adapter, _ = _make_open_ibeam_smart(
        readline_side_effect=[
            b"%SYS-E-00030, laser locked\r\n",
            b"[OK]\r\n",
            b"%SYS-E-00030, laser locked\r\n",
            b"[OK]\r\n",
        ]
    )
    assert adapter.active is False
    adapter.on()
    assert adapter._ibeam.error == 1
    assert adapter.active is False, (
        "on() must keep active=False when the inner 'laser on' was rejected "
        "(Class IIIB laser safety — GUI must not show energized when firmware refused)"
    )
    assert adapter.error == 1
    assert "%SYS-E" in adapter.error_message


# --------------------------------------------------------------------------- #
# off(): synchronous, no thread/queue offload (E-stop kill path).
# --------------------------------------------------------------------------- #
def test_ibeam_smart_off_is_synchronous() -> None:
    """``off()`` is synchronous (AGENTS.md §2 — E-stop kill path): calls
    ``self._ibeam.off()``, sets ``active = False`` and ``power = 0.0``, and
    returns ``None`` immediately — no thread/queue offload. The GUI-thread
    E-stop handler calls this directly; offloading it would break the
    synchronous-off safety contract for a Class IIIB laser."""
    adapter, _ = _make_open_ibeam_smart(readline_side_effect=[b"[OK]\r\n"])
    adapter.active = True
    adapter.power = 75.0
    result = adapter.off()
    assert result is None
    assert adapter.active is False
    assert adapter.power == 0.0
    # The inner IBeam's _is_on must also be False (delegated off()).
    assert adapter._ibeam._is_on is False


# --------------------------------------------------------------------------- #
# get_output_power(): mW readback, None on error, preserves CH<channel> filter.
# --------------------------------------------------------------------------- #
def test_ibeam_smart_get_output_power_returns_mw() -> None:
    """``get_output_power()`` calls the inner ``IBeam.get_output_power()``
    (which returns µW and already filters by ``CH{channel}``), then divides
    by 1000.0 to return mW. Rig-confirmed reply: ``CH1, PWR: 75.000 mW`` ->
    inner returns 75000 µW -> adapter returns 75.0 mW."""
    adapter, _ = _make_open_ibeam_smart(
        readline_side_effect=[
            b"CH1, PWR: 75.000 mW\r\n",
            b"CH2, PWR: 150.000 mW\r\n",
            b"CMD>\r\n",
        ]
    )
    result = adapter.get_output_power()
    assert result == 75.0, (
        f"get_output_power must return 75.0 mW (75000 uW / 1000) from the "
        f"CH1 line; got {result!r}"
    )
    assert adapter._ibeam.error == 0


def test_ibeam_smart_get_output_power_preserves_channel_filter() -> None:
    """The adapter MUST NOT re-implement the ``CH{channel}`` parse — it
    delegates to the inner ``IBeam.get_output_power()`` which already filters
    by ``CH{self.channel}``. A multi-channel reply (CH1 + CH2) must not be
    misread: the inner filter selects this driver's channel (CH1) and the
    adapter only converts the µW result to mW. Verify by checking the adapter
    returns the CH1 value (75.0 mW), not the CH2 value (150.0 mW)."""
    adapter, _ = _make_open_ibeam_smart(
        readline_side_effect=[
            b"CH1, PWR: 75.000 mW\r\n",
            b"CH2, PWR: 150.000 mW\r\n",
            b"CMD>\r\n",
        ]
    )
    result = adapter.get_output_power()
    assert result == 75.0, (
        "get_output_power must return the CH1 value (75.0 mW), not the CH2 "
        "value (150.0 mW) — the inner IBeam's CH{channel} filter is preserved"
    )


def test_ibeam_smart_get_output_power_returns_none_on_error() -> None:
    """On a parse failure / firmware rejection (inner ``error != 0``),
    ``get_output_power()`` returns ``None`` — not a stale or fabricated
    value — so the Wave 4 GUI readback field can distinguish "no reading"
    from "reading is 0"."""
    adapter, _ = _make_open_ibeam_smart(
        readline_side_effect=[b"%SYS-E-00099, rejected\r\n", b"[OK]\r\n"]
    )
    result = adapter.get_output_power()
    assert result is None, (
        "get_output_power must return None when the inner IBeam surfaces an "
        "error (parse failure / firmware rejection) — the GUI readback field "
        "must distinguish 'no reading' from 'reading is 0'"
    )


def test_ibeam_smart_get_output_power_returns_none_on_unmatched_response() -> None:
    """When the ``show level power`` reply contains no line matching
    ``CH{channel}`` (e.g. the firmware returned an unexpected format or
    an empty reply after the terminator), ``get_output_power()`` MUST
    return ``None`` — not the stale commanded ``self.power``. Returning
    the stale commanded value would present it as a live readback to the
    operator, potentially stale by minutes. The inner ``IBeam.error``
    stays 0 (no ``%SYS-E`` and no SerialException), so the adapter must
    check for ``None`` explicitly rather than relying on the error
    surface alone."""
    adapter, _ = _make_open_ibeam_smart(
        # Reply with no CH1 line — e.g. a truncated/unexpected format.
        readline_side_effect=[b"CMD>\r\n"]
    )
    # Pre-seed a known commanded power so we can prove it is NOT returned.
    adapter.power = 75.0
    adapter._ibeam._power = 75000
    result = adapter.get_output_power()
    assert result is None, (
        "get_output_power must return None when no CH{channel} line is "
        "found in the response — returning the stale commanded power would "
        "present it as a live readback (potentially stale by minutes)"
    )
    # The inner error surface stays clean (no %SYS-E, no SerialException),
    # so the None return is the only signal the adapter has.
    assert adapter._ibeam.error == 0


def test_ibeam_smart_get_output_power_returns_none_on_empty_response() -> None:
    """When the ``show level power`` reply is empty (readline times out
    immediately, returning b'' which _send_cmd treats as a terminator),
    ``get_output_power()`` MUST return ``None`` — not the stale commanded
    value. This is the firmware-desync / unresponsive-device case."""
    adapter, _ = _make_open_ibeam_smart(
        # readline returns b'' immediately (timeout) -> _send_cmd breaks
        # with an empty response_lines list.
        readline_side_effect=[b""]
    )
    adapter.power = 50.0
    adapter._ibeam._power = 50000
    result = adapter.get_output_power()
    assert result is None, (
        "get_output_power must return None on an empty response — the "
        "device is unresponsive or desynced, not reporting the last "
        "commanded power"
    )


# --------------------------------------------------------------------------- #
# open() / close(): delegate to inner IBeam, mirror error surface onto adapter.
# --------------------------------------------------------------------------- #
def test_ibeam_smart_open_delegates_to_inner_and_mirrors_error() -> None:
    """``open()`` delegates to ``self._ibeam.open()`` (which opens the
    serial port, disables echo, and enables the configured diode channel)
    and then mirrors the inner engine's error surface onto the adapter's
    ``self.error`` / ``self.error_message`` — so the controller can read
    ``self.lasers[1].error`` uniformly instead of reaching through to
    ``self.lasers[1]._ibeam.error``.

    On a successful open the inner ``error == 0`` and the adapter mirrors
    ``error == 0``. The serial port is opened and the echo-off +
    enable-channel handshake runs (the mock serial returns ``[OK]`` for
    each sub-command)."""
    with patch("lightsheet.hal.real.ibeam_smart.serial.Serial") as MockSerial:
        mock_ser = MagicMock()
        MockSerial.return_value = mock_ser
        mock_ser.readline.return_value = b"[OK]\r\n"
        adapter = ibeam_smart_mod.IBeamSmartLaser()
        adapter.open()
    # Inner engine opened successfully -> error surface clean on both.
    assert adapter._ibeam.error == 0
    assert adapter.error == 0, (
        "open() must mirror the inner error surface onto the adapter so the "
        "controller reads self.lasers[1].error uniformly"
    )
    assert adapter.error_message == ""
    # The inner serial port was actually opened (delegation, not a no-op).
    assert mock_ser.open.called


def test_ibeam_smart_open_mirrors_inner_failure_onto_adapter() -> None:
    """If the inner ``IBeam.open()`` raises (e.g. serial port in use), the
    adapter's ``open()`` propagates the exception (matching the inner
    engine's raise-on-open-failure contract) — the controller's
    ``try/except`` around ``self.lasers[1].open()`` catches it. We verify
    the raise propagates through the adapter so the controller's existing
    except clause fires."""
    with patch("lightsheet.hal.real.ibeam_smart.serial.Serial") as MockSerial:
        import serial as real_serial_mod

        mock_ser = MagicMock()
        MockSerial.return_value = mock_ser
        # ser.open() raises SerialException -> inner IBeam.open() catches
        # it, sets self.error=1, and re-raises (per IBeam.open contract).
        mock_ser.open.side_effect = real_serial_mod.SerialException(
            "port in use"
        )
        adapter = ibeam_smart_mod.IBeamSmartLaser()
        with pytest.raises(real_serial_mod.SerialException):
            adapter.open()
    # The inner engine surfaced the failure on its error surface before
    # re-raising; the adapter did not get to mirror (the raise preempted
    # the mirror lines), which is fine — the controller's except clause
    # emits the message and the operator is notified.
    assert adapter._ibeam.error == 1


def test_ibeam_smart_close_delegates_to_inner() -> None:
    """``close()`` delegates to ``self._ibeam.close()`` (which turns the
    laser off and releases the serial port) and mirrors the inner error
    surface onto the adapter. Replaces the controller's
    ``self.lasers[1]._ibeam.close()`` reach-through."""
    adapter, mock_ser = _make_open_ibeam_smart(readline_side_effect=[b"[OK]\r\n"])
    assert mock_ser.close is not None
    adapter.close()
    # Inner IBeam.close() calls ser.close() — verify delegation reached the
    # serial port.
    assert mock_ser.close.called
    # Adapter mirrors the inner error surface (clean on a successful close).
    assert adapter.error == adapter._ibeam.error


# --------------------------------------------------------------------------- #
# open() / close() are part of the ILaser contract — verify the adapter
# satisfies the ABC (instantiation would raise TypeError otherwise). This
# is a structural check that complements the behavior tests above.
# --------------------------------------------------------------------------- #
def test_ibeam_smart_satisfies_ilaser_abc() -> None:
    """IBeamSmartLaser implements the full ILaser ABC surface
    (on/off/open/close/set_power/get_output_power + the read attrs and
    _lock). Instantiation succeeds — if a required abstract method were
    missing, ABCMeta would raise TypeError at construction."""
    adapter = ibeam_smart_mod.IBeamSmartLaser()
    for method in ("on", "off", "open", "close", "set_power", "get_output_power"):
        assert callable(getattr(adapter, method)), (
            f"IBeamSmartLaser must expose ILaser method {method!r}"
        )
    for attr in ("_lock", "error", "error_message", "wavelength", "power",
                 "max_power", "active", "label"):
        assert hasattr(adapter, attr), (
            f"IBeamSmartLaser must expose ILaser attribute {attr!r}"
        )


# --------------------------------------------------------------------------- #
# Task 2: analog_ceiling_mw constructor — routes open() to the analog-modulation
# setup sequence (CH1=0, CH2=ceiling, enable 1, enable 2, laser on, en ext).
# --------------------------------------------------------------------------- #
def test_ibeam_smart_analog_ceiling_routes_open_to_analog_setup() -> None:
    """When analog_ceiling_mw is set, IBeamSmartLaser.open() runs the
    analog-modulation setup sequence via IBeam.open_for_analog_setup. The
    CH2 ceiling is the configured mW value (clamped to max_power). The
    default open (enable configured channel) is NOT issued."""
    with patch("lightsheet.hal.real.ibeam_smart.serial.Serial") as MockSerial:
        mock_ser = MagicMock()
        MockSerial.return_value = mock_ser
        mock_ser.readline.return_value = b"[OK]\r\n"
        adapter = ibeam_smart_mod.IBeamSmartLaser(analog_ceiling_mw=150.0)
        adapter.open()
    writes = [c.args[0].decode("ascii") for c in mock_ser.write.call_args_list]
    decoded = [w.rstrip("\r\n") for w in writes]
    # The analog setup sequence, not the default open+enable_channel.
    assert decoded == [
        "echo off",
        "channel 1 power 0 micro",
        "channel 2 power 150000 micro",
        "enable 1",
        "enable 2",
        "laser on",
        "en ext",
    ], f"analog setup sequence mismatch: {decoded}"
    # The default enable-channel (enable 1 alone, after echo off) is NOT
    # the only enable — both channels are enabled as part of the sequence.
    assert adapter.error == 0
    assert adapter._ibeam._is_on is True


def test_ibeam_smart_analog_ceiling_clamped_to_max_power() -> None:
    """analog_ceiling_mw above max_power (150 mW) is clamped at construct
    time so a config typo cannot command a ceiling above the diode limit."""
    adapter = ibeam_smart_mod.IBeamSmartLaser(analog_ceiling_mw=999.0)
    assert adapter._analog_ceiling_mw == pytest.approx(150.0)


def test_ibeam_smart_no_analog_ceiling_uses_default_open() -> None:
    """Without analog_ceiling_mw, open() uses the default IBeam.open()
    (echo off + enable configured channel) — the standalone serial-only
    usage path is preserved."""
    with patch("lightsheet.hal.real.ibeam_smart.serial.Serial") as MockSerial:
        mock_ser = MagicMock()
        MockSerial.return_value = mock_ser
        mock_ser.readline.return_value = b"[OK]\r\n"
        adapter = ibeam_smart_mod.IBeamSmartLaser()
        adapter.open()
    writes = [c.args[0].decode("ascii") for c in mock_ser.write.call_args_list]
    decoded = [w.rstrip("\r\n") for w in writes]
    # Default open: echo off + enable 1 (configured channel). No CH1=0,
    # no CH2 ceiling, no en ext.
    assert "echo off" in decoded
    assert "enable 1" in decoded
    assert "channel 1 power 0 micro" not in decoded
    assert "en ext" not in decoded


# --------------------------------------------------------------------------- #
# E-stop re-check: on() and set_power() must not re-energize past the kill.
# --------------------------------------------------------------------------- #
def test_ibeam_smart_on_returns_immediately_when_estop_set() -> None:
    """If _estop_event is already set when on() is called, on() must not
    send any serial command and must leave active=False."""
    adapter, _ = _make_open_ibeam_smart(readline_side_effect=[b"[OK]\r\n"])
    adapter._estop_event = _ToggleEvent([True])
    adapter.on()
    assert adapter.active is False
    assert adapter._ibeam._is_on is False


def test_ibeam_smart_on_turns_off_if_estop_set_during_on() -> None:
    """If E-stop fires after the 'laser on' sequence completes, on() must
    immediately turn the laser back off. The final active state must be False."""
    adapter, _ = _make_open_ibeam_smart(
        readline_side_effect=[b"[OK]\r\n", b"[OK]\r\n", b"[OK]\r\n"]
    )
    adapter._estop_event = _ToggleEvent([False, True])
    adapter.on()
    assert adapter.active is False
    assert adapter._ibeam._is_on is False


def test_ibeam_smart_set_power_returns_immediately_when_estop_set() -> None:
    """If _estop_event is already set, set_power() must not issue a serial
    command or update self.power."""
    adapter, _ = _make_open_ibeam_smart(readline_side_effect=[b"[OK]\r\n"])
    adapter._estop_event = _ToggleEvent([True])
    adapter.set_power(75.0)
    assert adapter.power == 0.0
    assert adapter._ibeam._power == 0
