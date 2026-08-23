"""Mock-serial behavior tests for the IBeamSmartLaser adapter
(lightsheet/hal/real/ibeam_smart.py).

``IBeamSmartLaser`` is the ``ILaser``-shaped adapter that wraps the existing,
rig-confirmed ``IBeam`` serial driver. This is a **re-wrap, not a rewrite**:
every serial round-trip is delegated to the unmodified inner ``IBeam`` engine
(per-instance lock, 50 ms inter-command gap, input-buffer flush — the reply-lag
mitigations validated at 0/12 misattribution at 1 s and 0.5 s cadence on COM4).

These tests run on Mac with no physical device: ``lightsheet.hal.real.ibeam.
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

from unittest.mock import MagicMock, patch

import lightsheet.hal.real.ibeam as ibeam_mod
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
    with patch("lightsheet.hal.real.ibeam.serial.Serial") as MockSerial:
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
    return written.decode("ascii")


# --------------------------------------------------------------------------- #
# Construction: mW-canonical attrs, lock identity, default state.
# --------------------------------------------------------------------------- #
def test_ibeam_smart_construction_mw_canonical_and_lock_identity() -> None:
    """``IBeamSmartLaser()`` constructs the inner ``IBeam`` and exposes the
    mW-canonical ``ILaser`` surface: ``wavelength`` (640 nm, from the inner
    iBeam self-report), ``max_power`` (150.0 mW = 150000 µW / 1000), ``power``
    (0.0 mW), ``active`` (False), ``error`` (0). The adapter's ``_lock`` IS
    the inner ``IBeam._lock`` (lock identity — not a new lock) so the
    daemon-thread write paths that acquire ``self.lasers[i]._lock`` and the
    inner ``_send_cmd`` lock are the same object.
    """
    adapter = ibeam_smart_mod.IBeamSmartLaser()
    # mW-canonical surface (D-01).
    assert adapter.wavelength == 640
    assert adapter.max_power == 150.0  # 150000 uW / 1000
    assert adapter.power == 0.0
    assert adapter.active is False
    assert adapter.error == 0
    assert adapter.error_message == ""
    assert adapter.label == "Laser 2 (640 nm)"
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
    assert "999000" not in text, "the unclamped 999.0 mW -> 999000 uW must not reach the serial line"
    assert adapter.power == 150.0, (
        "adapter must mirror self.power = 150.0 (clamped mW) on success"
    )


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
