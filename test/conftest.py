"""
Pytest auto-loaded configuration.

Stubs the absent hardware SDKs (nidaqmx, pco, and serial as a fallback) into
sys.modules BEFORE pytest collects any test/test_*.py file. This lets every
test module's `from lightsheet.lasers import Lasers` /
`from lightsheet.ibeam import IBeam` / `from lightsheet.motors import Motors` /
`from lightsheet.camera import Camera` succeed on this Mac, where the vendor
SDKs are not installed.

Each stub is gated by importlib.util.find_spec: if a real package is already
importable, the stub is skipped so the real driver is used on the rig.
"""

import sys
import types
from collections.abc import Callable


def _make_nidaqmx_stub() -> types.ModuleType:
    """Build a nidaqmx stub that imports fine but raises on Task() creation.

    Reproduces the "imports fine, Task() raises" behavior that the laser
    tests rely on when no NI-DAQmx driver runtime is available.
    """
    nidaqmx = types.ModuleType("nidaqmx")

    errors = types.ModuleType("nidaqmx.errors")

    class Error(Exception):
        """Base nidaqmx error (mirrors nidaqmx.errors.Error)."""

        pass

    class DaqError(Error):
        """DAQ-specific error subclass."""

        pass

    errors.Error = Error
    errors.DaqError = DaqError
    nidaqmx.errors = errors

    class Task:
        """Stub Task — raises on construction (no driver runtime)."""

        def __init__(self, *args: object, **kwargs: object) -> None:
            raise Error("no NI-DAQmx driver runtime available on this platform")

        # Common API surface used by src/lasers.py and src/siggen.py —
        # these are never reached because __init__ raises, but defining
        # them keeps attribute lookups on the class from blowing up if a
        # test inspects the type.
        ao_channels = None
        timing = None
        write = None
        start = None
        stop = None
        close = None

    nidaqmx.Task = Task
    return nidaqmx


def _make_pco_stub() -> types.ModuleType:
    """Build a pco stub whose Camera() raises on construction."""
    pco = types.ModuleType("pco")

    class Camera:
        """Stub Camera — raises on construction (no PCO SDK)."""

        def __init__(self, *args: object, **kwargs: object) -> None:
            raise RuntimeError("no PCO camera SDK available on this platform")

    pco.Camera = Camera
    return pco


def _make_serial_stub() -> types.ModuleType:
    """Build a serial stub mirroring the pyserial public surface used by
    src/etls.py and src/motors.py. Only used as a fallback when the real
    pyserial package is not importable."""
    serial = types.ModuleType("serial")

    EIGHTBITS = 8
    PARITY_NONE = "N"
    STOPBITS_ONE = 1

    class SerialException(Exception):
        pass

    class Serial:
        def __init__(self, *args: object, **kwargs: object) -> None:
            raise SerialException("no serial port available on this platform")

        def open(self) -> None:
            raise SerialException("no serial port available")

        def close(self) -> None:
            pass

        def write(self, data: bytes) -> int:
            return 0

        def read(self, size: int = 1) -> bytes:
            return b""

        def readline(self) -> bytes:
            return b""

        def reset_input_buffer(self) -> None:
            pass

    serial.Serial = Serial
    serial.SerialException = SerialException
    serial.EIGHTBITS = EIGHTBITS
    serial.PARITY_NONE = PARITY_NONE
    serial.STOPBITS_ONE = STOPBITS_ONE
    return serial


def _ensure_stub(
    name: str,
    builder: Callable[[], types.ModuleType],
    real_check: Callable[[types.ModuleType], None] | None = None,
) -> None:
    """Register a stub module for `name` if the real package is not usable.

    A package may be installed but broken on this platform (e.g. nidaqmx
    missing transitive deps, pco using Windows-only ctypes.windll). We try
    to import the real package and, if `real_check` is provided, run it
    against the imported module; if either raises, we fall back to the stub
    so the HAL modules that depend on it can still be imported for testing.
    """
    usable = False
    try:
        mod = __import__(name)
        if real_check is not None:
            real_check(mod)
        usable = True
    except Exception:
        usable = False

    if not usable:
        # A failed import may leave a partially-initialized module (or its
        # submodules) in sys.modules. Clear any such entries before
        # registering the stub so a later `import <name>` returns the stub.
        for key in list(sys.modules.keys()):
            if key == name or key.startswith(name + "."):
                del sys.modules[key]
        sys.modules[name] = builder()


def _nidaqmx_real_check(mod: types.ModuleType) -> None:
    """Smoke check: nidaqmx is only usable if Task() can be constructed
    (i.e. the driver runtime is present)."""
    mod.Task()


def _pco_real_check(mod: types.ModuleType) -> None:
    """Smoke check: pco is only usable if Camera() can be constructed
    (i.e. the PCO SDK + Windows DLLs are present)."""
    mod.Camera()


# Inject stubs before any test module is collected. pytest loads conftest.py
# prior to collection, so these sys.modules entries are visible to every
# `from lightsheet.* import ...` line in test/test_*.py.
_ensure_stub("nidaqmx", _make_nidaqmx_stub, real_check=_nidaqmx_real_check)
_ensure_stub("pco", _make_pco_stub, real_check=_pco_real_check)
_ensure_stub("serial", _make_serial_stub)
