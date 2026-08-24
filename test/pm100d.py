"""Thorlabs PM100D power meter driver via the TLPMX DLL (ctypes wrapper).

The PM100D uses a custom Thorlabs USB driver (``ThorlabsUSBDevice`` class,
not standard USBTMC), so NI-VISA / pyvisa-py cannot enumerate it. The
Thorlabs OPM software installs ``TLPMX_64.dll`` (the IVI Power Meter X
driver) in ``C:\\Program Files\\IVI Foundation\\VISA\\Win64\\Bin\\``, which
provides the C API:

    TLPMX_findRsrc  -> count available power meters
    TLPMX_getRsrcName -> get resource string by index
    TLPMX_init       -> open a session
    TLPMX_measPower  -> read current power (watts)
    TLPMX_setWavelength / TLPMX_getWavelength -> set/get wavelength (nm)
    TLPMX_close      -> close session

This module wraps the ctypes calls in a clean Python context manager. It is
rig-only (the DLL is Windows-only and the PM100D must be physically
connected). On the Mac the import fails gracefully (no DLL) so the sweep
script's Mac guard fires.

Usage:
    with PM100D(wavelength_nm=561) as meter:
        power_w = meter.read_power()
        power_mw = power_w * 1000.0

The S245C is a thermal surface absorber (flat spectral response 190nm-20um),
so the wavelength setting has minimal effect on accuracy, but we set it
anyway for correctness.
"""

from __future__ import annotations

import ctypes
import logging
import os
import sys
import time

logger = logging.getLogger(__name__)

# The DLL is installed by the Thorlabs OPM software. On 64-bit Windows it
# lands in the NI-VISA Win64 Bin directory. This path is the standard
# install location; if it moves in a future version, the user can set the
# TLPMX_DLL_PATH env var.
_DEFAULT_DLL_PATH = os.environ.get(
    "TLPMX_DLL_PATH",
    r"C:\Program Files\IVI Foundation\VISA\Win64\Bin\TLPMX_64.dll",
)


class PM100DError(Exception):
    """TLPMX driver error (non-zero status code from a DLL call)."""


class PM100DNotConnected(PM100DError):
    """No PM100D resource found by TLPMX_findRsrc."""


class PM100D:
    """Thorlabs PM100D power meter driver via the TLPMX DLL.

    Context manager: ``with PM100D(wavelength_nm=561) as meter: ...``
    On exit, the session is closed even if an exception is raised.

    The S245C thermal sensor has a flat spectral response, so the wavelength
    setting has minimal effect on accuracy, but it is set for correctness
    and for future use with photodiode sensors.
    """

    def __init__(
        self,
        wavelength_nm: float = 561.0,
        dll_path: str = _DEFAULT_DLL_PATH,
        reset: bool = False,
    ) -> None:
        self._wavelength_nm = float(wavelength_nm)
        self._dll_path = dll_path
        self._reset = reset
        self._dll: ctypes.CDLL | None = None
        self._session: int = 0

    def _load_dll(self) -> ctypes.CDLL:
        """Load the TLPMX DLL. Raises PM100DError if the DLL is missing."""
        if not os.path.exists(self._dll_path):
            raise PM100DError(
                f"TLPMX DLL not found at {self._dll_path}. Install the "
                "Thorlabs OPM software (which installs TLPMX_64.dll in the "
                "NI-VISA Bin directory), or set the TLPMX_DLL_PATH env var."
            )
        try:
            return ctypes.cdll.LoadLibrary(self._dll_path)
        except OSError as exc:
            raise PM100DError(
                f"Failed to load TLPMX DLL at {self._dll_path}: {exc}"
            ) from exc

    def _find_resource(self) -> str:
        """Find the first PM100D resource via TLPMX_findRsrc + getRsrcName."""
        assert self._dll is not None
        count = ctypes.c_uint32(0)
        status = self._dll.TLPMX_findRsrc(None, ctypes.byref(count))
        if status != 0:
            raise PM100DError(f"TLPMX_findRsrc failed: status={status}")
        if count.value == 0:
            raise PM100DNotConnected(
                "No Thorlabs power meter found. Check the USB connection "
                "and that the Thorlabs OPM driver is installed."
            )
        buf = ctypes.create_string_buffer(256)
        status = self._dll.TLPMX_getRsrcName(
            None, ctypes.c_uint32(0), buf
        )
        if status != 0:
            raise PM100DError(f"TLPMX_getRsrcName failed: status={status}")
        return buf.value.decode("ascii")

    def _open(self) -> None:
        """Load the DLL, find the resource, open a session, set wavelength."""
        self._dll = self._load_dll()
        rsrc = self._find_resource()
        logger.info("PM100D resource: %s", rsrc)

        session = ctypes.c_uint32(0)
        status = self._dll.TLPMX_init(
            rsrc.encode("utf-8"),
            True,  # ID query
            self._reset,  # reset device
            ctypes.byref(session),
        )
        if status != 0:
            raise PM100DError(
                f"TLPMX_init failed for {rsrc}: status={status}"
            )
        self._session = session.value
        logger.info("PM100D session opened: %d", self._session)

        # Set wavelength (minimal effect on the S245C thermal sensor, but
        # correct for photodiode sensors and for provenance).
        self._set_wavelength(self._wavelength_nm)

    def _close(self) -> None:
        """Close the session."""
        if self._dll is not None and self._session != 0:
            try:
                self._dll.TLPMX_close(ctypes.c_uint32(self._session))
                logger.info("PM100D session closed: %d", self._session)
            except Exception as exc:
                logger.warning("PM100D close error: %s", exc)
        self._session = 0

    def _set_wavelength(self, wavelength_nm: float) -> None:
        """Set the measurement wavelength (nm)."""
        assert self._dll is not None
        try:
            # TLPMX_setWavelength(ViSession vi, ViReal64 wavelength)
            self._dll.TLPMX_setWavelength(
                ctypes.c_uint32(self._session),
                ctypes.c_double(float(wavelength_nm)),
            )
            logger.info("PM100D wavelength set to %.1f nm", wavelength_nm)
        except Exception as exc:
            logger.warning("PM100D setWavelength error: %s", exc)

    def read_power(self) -> float:
        """Read the current optical power in watts.

        Returns the power as a float (watts). Raises PM100DError on a
        non-zero status from TLPMX_measPower.
        """
        assert self._dll is not None
        if self._session == 0:
            raise PM100DError("PM100D session not open")
        power = ctypes.c_double(0.0)
        status = self._dll.TLPMX_measPower(
            ctypes.c_uint32(self._session), ctypes.byref(power)
        )
        if status != 0:
            raise PM100DError(f"TLPMX_measPower failed: status={status}")
        return float(power.value)

    def read_power_mw(self) -> float:
        """Read the current optical power in milliwatts (convenience)."""
        return self.read_power() * 1000.0

    def read_averaged(
        self, n_samples: int, delay_s: float = 0.5
    ) -> float:
        """Take ``n_samples`` readings with ``delay_s`` between them,
        discard the first (settling throwaway), return the mean in watts.

        The S245C thermal sensor has a ~0.6s response time, so a delay of
        0.5-1.0s between readings is appropriate for the thermal response
        to settle.
        """
        if n_samples < 2:
            return self.read_power()
        readings: list[float] = []
        for i in range(n_samples):
            if i > 0:  # no delay before the first reading
                time.sleep(delay_s)
            readings.append(self.read_power())
        # Discard the first reading (settling throwaway).
        readings = readings[1:]
        mean = sum(readings) / len(readings)
        logger.debug(
            "PM100D averaged %d samples (discarded 1): %.6f W = %.3f mW",
            len(readings),
            mean,
            mean * 1000.0,
        )
        return mean

    def __enter__(self) -> PM100D:
        self._open()
        return self

    def __exit__(self, *args: object) -> None:
        self._close()


def is_pm100d_available() -> bool:
    """Check if the TLPMX DLL and a PM100D device are available.

    Returns True if the DLL can be loaded and TLPMX_findRsrc finds at least
    one resource. Rig-only — always False on the Mac (no DLL).
    """
    if sys.platform != "win32":
        return False
    if not os.path.exists(_DEFAULT_DLL_PATH):
        return False
    try:
        dll = ctypes.cdll.LoadLibrary(_DEFAULT_DLL_PATH)
        count = ctypes.c_uint32(0)
        status = dll.TLPMX_findRsrc(None, ctypes.byref(count))
        return status == 0 and count.value > 0
    except Exception:
        return False
