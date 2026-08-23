"""
Pytest auto-loaded configuration.

Stubs the absent hardware SDKs (nidaqmx, pco, and serial as a fallback) into
sys.modules BEFORE pytest collects any test/test_*.py file. This lets every
test module's `from lightsheet.hal import DAQLaser, IBeam, Motors, Camera` (and
the deeper `import lightsheet.hal.real.ibeam_smart` for mock-serial patch paths)
succeed on this Mac, where the vendor SDKs are not installed.

Each stub is gated by importlib.util.find_spec: if a real package is already
importable, the stub is skipped so the real driver is used on the rig.

The ``has_hardware`` fixture + module-level ``_has_hardware`` bool gate the
TST-04 conformance suite's ``[real, mock]`` parametrize: the real id is
skipped on Mac (``LIGHTSHEET_HW`` unset) via
``pytest.param(marks=pytest.mark.skipif(not _has_hardware, ...))`` and runs
on the rig when ``LIGHTSHEET_HW=1``. The module-level bool is needed because
parametrize marks are evaluated at collection time, not at fixture-resolution
time, so the fixture cannot be used inside ``skipif``.
"""

import os
import sys
import types
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

import pytest

if TYPE_CHECKING:
    # pyserial is installed on the Mac dev box (and types-pyserial provides
    # the stubs ty reads). Importing under TYPE_CHECKING gives ty the real
    # serial types for static analysis of the stub builder below, while the
    # runtime stub injection (_make_serial_stub, gated by find_spec) still
    # runs so the Mac path stubs at runtime if the real import ever fails.
    import serial  # noqa: F401  # ty static-analysis only; not used at runtime

# Module-level hardware gate (D-15). Parametrize marks are evaluated at
# collection time, before any fixture resolves, so the conformance tests'
# ``pytest.param(real, marks=pytest.mark.skipif(not _has_hardware, ...))``
# needs a module-level bool, not a fixture. Set LIGHTSHEET_HW=1 on the rig
# to run the real conformance path; leave it unset on the Mac dev box.
_has_hardware: bool = os.environ.get("LIGHTSHEET_HW", "0") == "1"


@pytest.fixture(scope="session")
def has_hardware() -> bool:
    """Session fixture exposing the hardware-gate bool to tests that want
    to read it at runtime (e.g. to assert the skipif gate logic). Mirrors
    the module-level ``_has_hardware`` but resolves at fixture-call time."""
    return os.environ.get("LIGHTSHEET_HW", "0") == "1"


def _make_nidaqmx_stub() -> types.ModuleType:
    """Build a nidaqmx stub that imports fine but raises on Task() creation.

    Reproduces the "imports fine, Task() raises" behavior that the laser
    tests rely on when no NI-DAQmx driver runtime is available.
    """
    nidaqmx = types.ModuleType("nidaqmx")
    # Mark the stub as a package so ``from nidaqmx.constants import ...``
    # (used by lightsheet/hal/real/siggen.py at module load time) resolves
    # via sys.modules. A bare ModuleType without __path__ is not a package
    # and submodule imports fail with "nidaqmx is not a package".
    nidaqmx.__path__ = []  # type: ignore[attr-defined]

    errors = types.ModuleType("nidaqmx.errors")

    class Error(Exception):
        """Base nidaqmx error (mirrors nidaqmx.errors.Error)."""

        pass

    class DaqError(Error):
        """DAQ-specific error subclass."""

        pass

    cast(Any, errors).Error = Error
    cast(Any, errors).DaqError = DaqError
    cast(Any, nidaqmx).errors = errors

    class Task:
        """Stub Task — raises on construction (no driver runtime)."""

        def __init__(self, *args: object, **kwargs: object) -> None:
            raise Error("no NI-DAQmx driver runtime available on this platform")

        # Common API surface used by lightsheet/lasers.py and lightsheet/siggen.py —
        # these are never reached because __init__ raises, but defining
        # them keeps attribute lookups on the class from blowing up if a
        # test inspects the type.
        ao_channels: Any = None
        timing: Any = None
        write: Any = None
        start: Any = None
        stop: Any = None
        close: Any = None

    cast(Any, nidaqmx).Task = Task

    # constants submodule — lightsheet/hal/real/siggen.py imports
    # ``from nidaqmx.constants import AcquisitionType, Edge, LineGrouping``
    # at module load time. The real nidaqmx package exposes these as enums;
    # the stub exposes them as simple enum.IntEnum members so the import
    # succeeds on the Mac (the values are never used because Task() raises
    # before any DAQ call reaches them). This keeps the stub minimal (D-11)
    # while letting the hal/real/ modules import for testing.
    import enum

    constants = types.ModuleType("nidaqmx.constants")

    class AcquisitionType(enum.IntEnum):
        FINITE = 1
        CONTINUOUS = 2

    class Edge(enum.IntEnum):
        RISING = 1
        FALLING = 2

    class LineGrouping(enum.IntEnum):
        CHAN_PER_LINE = 1
        CHAN_FOR_ALL_LINES = 2

    cast(Any, constants).AcquisitionType = AcquisitionType
    cast(Any, constants).Edge = Edge
    cast(Any, constants).LineGrouping = LineGrouping
    cast(Any, nidaqmx).constants = constants
    # Register the submodules in sys.modules so ``from nidaqmx.constants
    # import ...`` and ``from nidaqmx.errors import ...`` resolve via the
    # stub when the real nidaqmx is not usable. The parent nidaqmx module
    # is registered by _ensure_stub; the submodules must be registered
    # here because the import machinery looks them up in sys.modules
    # before falling back to the parent's attributes.
    sys.modules["nidaqmx.constants"] = constants
    sys.modules["nidaqmx.errors"] = errors

    return nidaqmx


def _make_pco_stub() -> types.ModuleType:
    """Build a pco stub whose Camera() raises on construction."""
    pco = types.ModuleType("pco")

    class Camera:
        """Stub Camera — raises on construction (no PCO SDK)."""

        def __init__(self, *args: object, **kwargs: object) -> None:
            raise RuntimeError("no PCO camera SDK available on this platform")

    cast(Any, pco).Camera = Camera
    return pco


def _make_serial_stub() -> types.ModuleType:
    """Build a serial stub mirroring the pyserial public surface used by
    lightsheet/etls.py and lightsheet/motors.py. Only used as a fallback when the real
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

    cast(Any, serial).Serial = Serial
    cast(Any, serial).SerialException = SerialException
    cast(Any, serial).EIGHTBITS = EIGHTBITS
    cast(Any, serial).PARITY_NONE = PARITY_NONE
    cast(Any, serial).STOPBITS_ONE = STOPBITS_ONE
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

    Idempotent: if `sys.modules[name]` is already one of our stubs (marked
    with `_lightsheet_stub = True`), return without re-installing. This
    matters because conftest.py runs `_ensure_stub` at module import time,
    and some tests re-import conftest under a bare module name (e.g.
    test_conformance_contract.py reaches `import conftest` via sys.path to
    read `_has_hardware`). Without idempotency, that re-import re-runs
    `_ensure_stub`, which finds the stub's own `Task()` raises (real_check
    fails), deletes the existing stub, and installs a FRESH stub object —
    breaking any module that already bound the old `nidaqmx` reference
    (e.g. daqlaser.py) and any test that monkeypatches `nidaqmx.Task`
    after the re-install.
    """
    existing = sys.modules.get(name)
    if existing is not None and getattr(existing, "_lightsheet_stub", False):
        return

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
        stub = builder()
        # Mark the stub so a re-run of _ensure_stub (e.g. via a re-import of
        # conftest from another test) recognizes it as already-installed
        # and does not replace it with a fresh object — see idempotency
        # note above.
        stub._lightsheet_stub = True  # ty: ignore[unresolved-attribute]
        sys.modules[name] = stub


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
