"""Behavior tests for lightsheet/hal/real/pm100d.py — the real PM100D
backend, exercised on Mac WITHOUT the TLPMX DLL.

The TLPMX DLL is Windows-only and absent on this Mac, so ``PM100D.__init__``
is safe (it only stores attrs — the DLL is loaded lazily in ``open()``).
For methods that hit the DLL (``open`` / ``_find_resource`` / ``read_power``
/ ``zero`` / ``_set_wavelength``) we either rely on the Mac guard inside
``_load_dll`` (which raises ``PM100DError`` on non-Windows) or attach a
fake DLL (a ``MagicMock`` standing in for the ``ctypes.CDLL``) to exercise
the status-code branches in isolation.

The ``__new__`` bypass is NOT needed for ``PM100D`` — ``__init__`` does not
probe hardware (the DLL load is deferred to ``open()``). We construct real
``PM100D`` instances directly.

This is a BEHAVIOR test (AGENTS.md §5).
"""

import sys
from unittest.mock import MagicMock

import pytest

from lightsheet.hal.real.pm100d import (
    PM100D,
    PM100DError,
    PM100DNotConnected,
    is_pm100d_available,
)


def test_exception_hierarchy() -> None:
    """PM100DNotConnected subclasses PM100DError (so callers can catch the
    base class)."""
    assert issubclass(PM100DNotConnected, PM100DError)
    assert issubclass(PM100DError, Exception)


def test_construction_defaults() -> None:
    """__init__ clears the HAL error surface and stores the wavelength /
    dll_path / reset flag without touching the DLL."""
    meter = PM100D(wavelength_nm=488.0)
    assert meter.error == 0
    assert meter.error_message == ""
    assert meter._wavelength_nm == 488.0
    assert meter._reset is False
    assert meter._dll is None
    assert meter._session == 0


def test_load_dll_raises_on_non_windows() -> None:
    """_load_dll raises PM100DError on non-Windows platforms (the
    ``sys.platform != 'win32'`` branch). On Mac this is the first guard."""
    meter = PM100D()
    with pytest.raises(PM100DError, match="only supported on Windows"):
        meter._load_dll()


def test_open_raises_pm100d_error_on_mac() -> None:
    """open() on Mac propagates the PM100DError from _load_dll (the
    non-Windows guard). The error surface is NOT set by open() on this
    path (the exception fires before the error-setting lines)."""
    meter = PM100D()
    with pytest.raises(PM100DError, match="only supported on Windows"):
        meter.open()
    # _load_dll raised before open() could assign self._dll.
    assert meter._dll is None


def test_is_pm100d_available_false_on_mac() -> None:
    """is_pm100d_available() returns False on non-Windows platforms (the
    ``sys.platform != 'win32'`` early return)."""
    if sys.platform == "win32":
        pytest.skip("Windows-only guard test")
    assert is_pm100d_available() is False


def test_read_power_mw_converts_watts_to_milliwatts() -> None:
    """read_power_mw() returns read_power() * 1000.0. Patch read_power to
    a known value so no DLL is touched (covers the mW conversion line)."""
    meter = PM100D()
    meter.read_power = MagicMock(return_value=0.0025)
    assert meter.read_power_mw() == pytest.approx(2.5)
    meter.read_power.assert_called_once()


def test_read_power_raises_when_session_not_open() -> None:
    """read_power() raises PM100DError when the session is not open
    (the ``self._session == 0`` guard). A fake DLL is attached so the
    ``assert self._dll is not None`` passes and the session guard is
    reached."""
    meter = PM100D()
    meter._dll = MagicMock()  # bypass the assert
    assert meter._session == 0
    with pytest.raises(PM100DError, match="session not open"):
        meter.read_power()


def test_read_power_raises_on_nonzero_status() -> None:
    """read_power() sets error=1 / error_message and raises PM100DError
    when TLPMX_measPower returns a non-zero status (the ``status != 0``
    branch)."""
    meter = PM100D()
    meter._dll = MagicMock()
    meter._session = 1  # session open
    meter._dll.TLPMX_measPower.return_value = 1  # non-zero status
    with pytest.raises(PM100DError, match="TLPMX_measPower failed"):
        meter.read_power()
    assert meter.error == 1
    assert "TLPMX_measPower failed" in meter.error_message


def test_read_power_returns_value_on_success() -> None:
    """read_power() returns the measured power (watts) when the DLL call
    succeeds (status == 0). The fake DLL writes into the c_double out-param."""
    meter = PM100D()
    meter._dll = MagicMock()
    meter._session = 1

    def fake_meas_power(session, power_ref, channel):
        power_ref._obj.value = 0.0042
        return 0

    meter._dll.TLPMX_measPower.side_effect = fake_meas_power
    assert meter.read_power() == pytest.approx(0.0042)
    assert meter.error == 0


def test_read_averaged_short_circuits_for_few_than_two_samples() -> None:
    """read_averaged(n<2) returns a single read_power() call (the
    ``n_samples < 2`` branch)."""
    meter = PM100D()
    meter.read_power = MagicMock(return_value=0.001)
    assert meter.read_averaged(1, delay_s=0.0) == pytest.approx(0.001)
    assert meter.read_averaged(0, delay_s=0.0) == pytest.approx(0.001)


def test_read_averaged_discards_first_and_averages() -> None:
    """read_averaged(n>=2) takes n readings, discards the first, and
    returns the mean of the rest. With a constant mock value the mean
    equals the value. delay_s=0 skips the sleep branch (``i > 0`` True
    but the ``time.sleep`` is skipped because delay_s is falsy — wait,
    the real code sleeps unconditionally when i > 0; use a tiny delay)."""
    meter = PM100D()
    meter.read_power = MagicMock(return_value=0.003)
    result = meter.read_averaged(4, delay_s=0.0)
    assert result == pytest.approx(0.003)
    # 4 readings taken (first discarded, mean of 3).
    assert meter.read_power.call_count == 4


def test_read_averaged_sleeps_between_readings() -> None:
    """read_averaged with delay_s > 0 sleeps between readings (the
    ``i > 0`` True branch with a real sleep). Use a tiny delay."""
    meter = PM100D()
    meter.read_power = MagicMock(return_value=0.003)
    result = meter.read_averaged(3, delay_s=0.001)
    assert result == pytest.approx(0.003)
    assert meter.read_power.call_count == 3


def test_zero_raises_when_session_not_open() -> None:
    """zero() raises PM100DError when the session is not open (the
    ``self._session == 0`` guard). A fake DLL is attached so the assert
    passes."""
    meter = PM100D()
    meter._dll = MagicMock()
    assert meter._session == 0
    with pytest.raises(PM100DError, match="session not open"):
        meter.zero()


def test_zero_raises_on_nonzero_status() -> None:
    """zero() sets error=1 / error_message and raises PM100DError when
    TLPMX_startDarkAdjust returns a non-zero status (the ``status != 0``
    branch)."""
    meter = PM100D()
    meter._dll = MagicMock()
    meter._session = 1
    meter._dll.TLPMX_startDarkAdjust.return_value = 1
    with pytest.raises(PM100DError, match="TLPMX_startDarkAdjust failed"):
        meter.zero()
    assert meter.error == 1
    assert "TLPMX_startDarkAdjust failed" in meter.error_message


def test_zero_succeeds_on_zero_status() -> None:
    """zero() completes without raising when TLPMX_startDarkAdjust returns
    0 (the success branch)."""
    meter = PM100D()
    meter._dll = MagicMock()
    meter._session = 1
    meter._dll.TLPMX_startDarkAdjust.return_value = 0
    meter.zero()  # should not raise
    assert meter.error == 0


def test_zero_wraps_unexpected_exception() -> None:
    """zero() catches a non-PM100DError exception from the DLL call and
    re-raises it as PM100DError with the error surface set (the
    ``except Exception`` branch)."""
    meter = PM100D()
    meter._dll = MagicMock()
    meter._session = 1
    meter._dll.TLPMX_startDarkAdjust.side_effect = RuntimeError("DLL crash")
    with pytest.raises(PM100DError, match="PM100D zero error"):
        meter.zero()
    assert meter.error == 1
    assert "DLL crash" in meter.error_message


def test_close_noop_when_no_session() -> None:
    """close() is a no-op when there is no DLL / no session (the False
    branch of ``self._dll is not None and self._session != 0``)."""
    meter = PM100D()
    assert meter._dll is None
    assert meter._session == 0
    meter.close()  # should not raise
    assert meter._session == 0


def test_close_calls_dll_when_session_open() -> None:
    """close() calls TLPMX_close when a session is open (the True branch
    of the guard), then resets _session to 0."""
    meter = PM100D()
    meter._dll = MagicMock()
    meter._session = 42
    meter.close()
    meter._dll.TLPMX_close.assert_called_once()
    assert meter._session == 0


def test_close_swallows_dll_exception() -> None:
    """close() logs but does not raise when TLPMX_close raises (the
    ``except Exception`` branch inside close)."""
    meter = PM100D()
    meter._dll = MagicMock()
    meter._session = 42
    meter._dll.TLPMX_close.side_effect = RuntimeError("close failed")
    meter.close()  # should not raise
    assert meter._session == 0


def test_context_manager_enter_returns_self_and_exit_closes() -> None:
    """__enter__ returns self; __exit__ calls close(). Patch open/close so
    no DLL is loaded."""
    meter = PM100D()
    meter.open = MagicMock()
    meter.close = MagicMock()
    with meter as ctx:
        assert ctx is meter
    meter.open.assert_called_once()
    meter.close.assert_called_once()


def test_find_resource_raises_when_find_rsrc_fails() -> None:
    """_find_resource raises PM100DError when TLPMX_findRsrc returns a
    non-zero status (the ``status != 0`` branch)."""
    meter = PM100D()
    meter._dll = MagicMock()
    meter._dll.TLPMX_findRsrc.return_value = 1
    with pytest.raises(PM100DError, match="TLPMX_findRsrc failed"):
        meter._find_resource()


def test_find_resource_raises_when_no_resources() -> None:
    """_find_resource raises PM100DNotConnected when TLPMX_findRsrc finds
    zero resources (the ``count.value == 0`` branch)."""
    meter = PM100D()
    meter._dll = MagicMock()

    def fake_find_rsrc(_vi, count_ref):
        count_ref._obj.value = 0
        return 0

    meter._dll.TLPMX_findRsrc.side_effect = fake_find_rsrc
    with pytest.raises(PM100DNotConnected, match="No Thorlabs power meter"):
        meter._find_resource()


def test_find_resource_returns_name_on_success() -> None:
    """_find_resource returns the decoded resource name when both DLL calls
    succeed (the success branch)."""
    meter = PM100D()
    meter._dll = MagicMock()

    def fake_find_rsrc(_vi, count_ref):
        count_ref._obj.value = 1
        return 0

    def fake_get_rsrc_name(_vi, _idx, buf):
        # buf is a ctypes string buffer; write the resource name into it.
        name = b"USB0::0x1313::PM100D"
        buf.raw = name + b"\x00" * (len(buf.raw) - len(name))
        return 0

    meter._dll.TLPMX_findRsrc.side_effect = fake_find_rsrc
    meter._dll.TLPMX_getRsrcName.side_effect = fake_get_rsrc_name
    rsrc = meter._find_resource()
    assert "PM100D" in rsrc


def test_find_resource_raises_when_get_rsrc_name_fails() -> None:
    """_find_resource raises PM100DError when TLPMX_getRsrcName returns a
    non-zero status (the second ``status != 0`` branch)."""
    meter = PM100D()
    meter._dll = MagicMock()

    def fake_find_rsrc(_vi, count_ref):
        count_ref._obj.value = 1
        return 0

    meter._dll.TLPMX_findRsrc.side_effect = fake_find_rsrc
    meter._dll.TLPMX_getRsrcName.return_value = 1
    with pytest.raises(PM100DError, match="TLPMX_getRsrcName failed"):
        meter._find_resource()


def test_open_sets_error_on_init_failure() -> None:
    """open() sets error=1 / error_message and raises PM100DError when
    TLPMX_init returns a non-zero status (the ``status != 0`` branch in
    open). The DLL load + findRsrc are mocked to succeed."""
    meter = PM100D()
    # Bypass _load_dll by patching it to return a fake DLL.
    fake_dll = MagicMock()
    meter._load_dll = MagicMock(return_value=fake_dll)
    # _find_resource returns a valid resource string.
    meter._find_resource = MagicMock(return_value="USB0::PM100D")
    fake_dll.TLPMX_init.return_value = 1  # non-zero status
    with pytest.raises(PM100DError, match="TLPMX_init failed"):
        meter.open()
    assert meter.error == 1
    assert "TLPMX_init failed" in meter.error_message


def test_open_succeeds_and_sets_wavelength() -> None:
    """open() succeeds when TLPMX_init returns 0, stores the session, and
    calls _set_wavelength (the success branch). The error surface is
    cleared at the end of a successful open."""
    meter = PM100D(wavelength_nm=561.0)
    fake_dll = MagicMock()
    meter._load_dll = MagicMock(return_value=fake_dll)
    meter._find_resource = MagicMock(return_value="USB0::PM100D")

    def fake_init(_rsrc, _id_query, _reset, session_ref):
        session_ref._obj.value = 99
        return 0

    fake_dll.TLPMX_init.side_effect = fake_init
    fake_dll.TLPMX_setWavelength.return_value = 0
    meter.open()
    assert meter._session == 99
    fake_dll.TLPMX_setWavelength.assert_called_once()
    # Error surface cleared on successful open.
    assert meter.error == 0
    assert meter.error_message == ""


def test_set_wavelength_logs_on_nonzero_status() -> None:
    """_set_wavelength logs a warning (does not raise) when
    TLPMX_setWavelength returns a non-zero status (the ``status != 0``
    branch)."""
    meter = PM100D()
    meter._dll = MagicMock()
    meter._session = 1
    meter._dll.TLPMX_setWavelength.return_value = 1
    # Should not raise.
    meter._set_wavelength(561.0)


def test_set_wavelength_succeeds_on_zero_status() -> None:
    """_set_wavelength logs info (does not raise) when
    TLPMX_setWavelength returns 0 (the success branch)."""
    meter = PM100D()
    meter._dll = MagicMock()
    meter._session = 1
    meter._dll.TLPMX_setWavelength.return_value = 0
    meter._set_wavelength(561.0)


def test_set_wavelength_wraps_exception() -> None:
    """_set_wavelength catches a non-PM100DError exception from the DLL
    call and logs it (does not raise — the ``except Exception`` branch)."""
    meter = PM100D()
    meter._dll = MagicMock()
    meter._session = 1
    meter._dll.TLPMX_setWavelength.side_effect = RuntimeError("DLL crash")
    # Should not raise.
    meter._set_wavelength(561.0)
