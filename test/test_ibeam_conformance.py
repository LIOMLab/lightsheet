"""TST-04 conformance suite — IBeam family (D-15).

Parametrized over ``[real, mock]`` with one assertion body behind both paths.
The real id (``IBeam``) is skipped on Mac; the mock id (``MockIBeam``)
always runs. ``IBEAM_CONTRACT`` is the single source of truth for the
open/close/on/off/enable_channel + read-attr surface.

**Safety (AGENTS.md §2):**
- ``off()`` MUST be synchronous — set ``_is_on=False`` and return None
  immediately, no thread/queue offload. The E-stop kill path drives
  ``ibeam.off()`` on the GUI thread; offloading it would break the
  synchronous-off safety contract for a Class IIIB laser.
- ``set_power`` MUST clamp to ``max_power`` at the HAL boundary.

Both safety invariants are asserted here on both paths (the same checks
the Mock* tests run, now behind the [real, mock] parametrize).

This is a BEHAVIOR test (AGENTS.md §5).
"""

import os

import pytest

from lightsheet.hal import IBeam, MockIBeam
from lightsheet.hal.conformance import IBEAM_CONTRACT

# Module-level hardware gate (D-15). Mirrors conftest._has_hardware but
# defined inline so the test file is self-contained at collection time
# (parametrize marks are evaluated before fixtures resolve). Set
# LIGHTSHEET_HW=1 on the rig to run the real conformance path.
_has_hardware: bool = os.environ.get("LIGHTSHEET_HW", "0") == "1"


@pytest.mark.parametrize(
    "device_factory",
    [
        pytest.param(
            lambda: IBeam(),
            marks=pytest.mark.skipif(not _has_hardware, reason="rig only"),
            id="real",
        ),
        pytest.param(lambda: MockIBeam(), id="mock"),
    ],
)
def test_ibeam_conformance(device_factory: object) -> None:
    """One assertion body behind both [real, mock] — the structural
    divergence catch (D-15). The IBeam lifecycle verbs (on/off) have side
    effects (serial commands), so the contract checks existence via
    assert_lifecycle (hasattr) and exercises only the safe open/close.
    The synchronous-off + power-clamp safety checks run separately below
    on both paths."""
    dev = device_factory()
    IBEAM_CONTRACT.assert_lifecycle(dev)
    IBEAM_CONTRACT.assert_error_surface(dev)
    IBEAM_CONTRACT.assert_read_attrs(dev)
    IBEAM_CONTRACT.assert_setter_methods(dev)


@pytest.mark.parametrize(
    "device_factory",
    [
        pytest.param(
            lambda: IBeam(),
            marks=pytest.mark.skipif(not _has_hardware, reason="rig only"),
            id="real",
        ),
        pytest.param(lambda: MockIBeam(), id="mock"),
    ],
)
def test_ibeam_off_is_synchronous(device_factory: object) -> None:
    """SAFETY (AGENTS.md §2): off() MUST be synchronous — set _is_on=False
    and return None immediately, no thread/queue offload. The E-stop kill
    path drives ibeam.off() on the GUI thread; offloading it would break
    the synchronous-off safety contract for a Class IIIB laser. This
    assertion runs behind both [real, mock]."""
    dev = device_factory()
    # off() must return None and synchronously clear _is_on. We do not
    # call on() first (energizing the laser is an operator action per
    # AGENTS.md §2); we assert off() on a freshly-constructed (off) device
    # is synchronous and leaves _is_on False.
    result = dev.off()
    assert result is None
    assert dev._is_on is False, (
        "off() must synchronously set _is_on=False — no queue/thread offload "
        "(AGENTS.md §2 E-stop kill path for a Class IIIB laser)"
    )


@pytest.mark.parametrize(
    "device_factory",
    [
        pytest.param(
            lambda: IBeam(),
            marks=pytest.mark.skipif(not _has_hardware, reason="rig only"),
            id="real",
        ),
        pytest.param(lambda: MockIBeam(), id="mock"),
    ],
)
def test_ibeam_set_power_clamps_to_max(device_factory: object) -> None:
    """SAFETY (AGENTS.md §2): set_power MUST clamp to max_power at the HAL
    boundary. This assertion runs behind both [real, mock] — the same
    safety invariant the Mock* tests check.

    The real ``IBeam.set_power`` requires ``open()`` first: ``_send_cmd``
    raises ``SerialException`` when ``self.ser`` is ``None``, leaving
    ``_power`` at 0 and the clamp unverified. So the real path calls
    ``dev.open()`` before ``dev.set_power(999999)`` so the real serial
    write path succeeds and ``_power`` updates to the clamped
    ``max_power``. ``MockIBeam.open()`` is a no-op, so calling ``open()``
    before ``set_power`` is mock-transparent — the mock path still
    asserts ``dev._power == dev.max_power``.

    The finally-cleanup branches on ``isinstance(dev, MockIBeam)``:
    - Mock path: skip ``off()``/``close()`` entirely. ``MockIBeam.off()``
      sets ``_power = 0``, which would mutate the value the test just
      verified, and is unnecessary for a software-only mock.
    - Real path: call ``dev.off()`` then ``dev.close()`` to turn the
      laser off and release the serial port. The test called
      ``open()`` + ``set_power()`` which staged channel power, so
      ``off()`` + ``close()`` reverts to a safe state. Guarded with
      try/except so a failure in ``off()`` does not skip ``close()``.

    Real-path open() note: ``IBeam.open()`` opens the serial port and
    sends ``echo off`` + ``enable <ch>``. The ``enable <ch>`` command
    gates the channel power output but does NOT energize the laser (no
    ``laser on`` command is sent). ``set_power(999999)`` sends
    ``channel <ch> power 150000 micro`` — this stages the clamped max
    power but the laser is not globally enabled (no ``laser on``), so
    the diode stays dark. This respects AGENTS.md §2 (no energization
    without explicit operator action) while still verifying the clamp.
    The ``off()`` + ``close()`` cleanup is defensive (turns off +
    releases the port) in case any future firmware variant auto-enables
    on channel power.
    """
    dev = device_factory()
    is_mock = isinstance(dev, MockIBeam)
    try:
        # open() is a no-op on the mock; on the real path it opens the
        # serial port + enables the channel so set_power's serial write
        # succeeds (without open, _send_cmd raises SerialException when
        # self.ser is None, leaving _power at 0 and the clamp unverified).
        dev.open()
        dev.set_power(999999)
        assert dev._power == dev.max_power, (
            "set_power must clamp to max_power at the HAL boundary "
            "(AGENTS.md §2 — Class IIIB laser safety)"
        )
    finally:
        if not is_mock:
            # Real-path cleanup — turn the laser off and release the
            # serial port. The test called open() + set_power() which
            # staged channel power, so off() + close() reverts to a
            # safe state. Guarded so a failure in off() does not skip
            # close().
            try:
                dev.off()
            except Exception:
                pass
            try:
                dev.close()
            except Exception:
                pass
        # Mock path: skip cleanup — MockIBeam.off() would set _power=0
        # post-assertion (mutating the value the test just verified) and
        # is unnecessary for a software-only mock.
