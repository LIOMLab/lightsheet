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


def pytest_collection_modifyitems(config: Any, items: list[Any]) -> None:
    """Auto-skip ``@pytest.mark.rig`` tests when ``LIGHTSHEET_HW`` is unset.

    This is the TST-07 collection-time selection mechanism the coverage
    gate's rig-side invocation depends on. It complements (does NOT
    replace) the module-level ``_has_hardware`` bool + ``has_hardware``
    fixture above, which gate the TST-04 ``[real, mock]`` parametrize ids
    via ``pytest.param(marks=pytest.mark.skipif(not _has_hardware, ...))``.

    Why a collection hook instead of a bare
    ``@pytest.mark.skipif(os.environ["LIGHTSHEET_HW"] == "1", ...)``:
    a bare ``skipif`` reading ``os.environ["LIGHTSHEET_HW"]`` raises
    ``KeyError`` at import time when the var is unset (the ``[]`` indexer
    does not default). The hook reads ``os.environ.get(...)`` (default
    ``"0"``) at collection time, after every test module is imported, so
    there is no import-time hazard.

    xdist-compatible: pytest calls this hook once per worker before that
    worker's share of items is executed; env vars are inherited by every
    worker process, so the rig/mock decision is consistent across workers.
    On the rig (``LIGHTSHEET_HW=1``) the hook returns immediately and every
    ``@pytest.mark.rig`` test runs.
    """
    if os.environ.get("LIGHTSHEET_HW", "0") == "1":
        # Rig mode — run everything (rig tests + mock tests).
        return
    skip_rig = pytest.mark.skip(reason="rig-only: set LIGHTSHEET_HW=1 to run")
    for item in items:
        if "rig" in item.keywords:
            item.add_marker(skip_rig)


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


def _install_imageview_stub() -> None:
    """Replace ``pyqtgraph.ImageView`` with a lightweight QWidget subclass
    before any test imports ``lightsheet.gui.ui_controller``.

    ``pyqtgraph.ImageView`` constructs a ``ViewBox`` whose C++ destructor
    segfaults during garbage collection at process exit. The segfault kills
    the process before pytest-cov writes its coverage data, silently losing
    all branch coverage. Replacing ``ImageView`` with a plain ``QWidget``
    (same Qt widget API the UI setup reads — ``sizePolicy``, etc. — but no
    pyqtgraph C++ objects) eliminates the segfault at the source.

    Requires a QApplication to exist before the stub is used (QWidget
    construction needs one). Tests that construct the controller create
    their own QApplication at module load time.
    """
    import importlib
    import PyQt5.QtWidgets as _QW

    real_pg = importlib.import_module("pyqtgraph")
    if not getattr(real_pg.ImageView, "_lightsheet_imageview_stub", False):
        class _StubImageView(_QW.QWidget):  # noqa: N801
            _lightsheet_imageview_stub = True

            def setImage(self, *args, **kwargs):  # noqa: N802
                """No-op stand-in for pyqtgraph.ImageView.setImage — the
                real method drives the C++ ViewBox that segfaults on GC.
                Tests do not assert on the rendered image; they assert on
                the controller's signal/attribute side-effects."""


        real_pg.ImageView = _StubImageView
        # ui_controller imported the name into its own namespace at module
        # load time; patch that too so the controller picks up the stub.
        try:
            ui_ctrl = importlib.import_module("lightsheet.gui.ui_controller")
            ui_ctrl.ImageView = _StubImageView
        except ModuleNotFoundError:
            pass


# Install the ImageView stub eagerly so any later import of
# lightsheet.gui.ui_controller picks up the QWidget replacement.
try:
    _install_imageview_stub()
except Exception:  # noqa: BLE001
    # If pyqtgraph isn't installed or PyQt5 isn't available, skip the stub —
    # tests that need them will skip themselves via pytest.importorskip.
    pass


# Disable garbage collection for the entire test session. Qt widget
# destructors segfault during garbage collection on macOS, killing xdist
# worker processes before they can send coverage data back to the master.
# The segfault happens during a GC pass triggered by pytest's fixture
# introspection (getfuncargnames → signature → unwrap → GC) or at worker
# exit. Disabling GC prevents the segfault without affecting test behavior
# (test objects are never explicitly collected during the test run).
import gc as _gc
_gc.disable()


# GC is disabled globally (above) to prevent Qt widget destructor
# segfaults during the test run. We do NOT re-enable it or call os._exit()
# in pytest_sessionfinish — xdist workers must exit normally to send
# coverage data back to the master. The gc.disable() prevents the segfault
# during the test run; at exit, Python's normal shutdown may re-enable GC
# and segfault, but by that point pytest-cov has already written coverage
# data and the xdist channel has already sent it to the master.
#
# Root cause of the segfault (a real reference-cycle bug, deferred to the
# Phase 6 threading / Phase 7 Qt6 rework — see ROADMAP.md Phase 6 known
# issue): 53 `lambda: self._mc.<slot>()` signal connections in
# Controller_MainWindow.__init__ each create a cycle
# controller → child widget → signal → lambda → closure cell → controller.
# The Python wrapper never reaches refcount zero, so the C++ QMainWindow
# destructor is deferred to cyclic GC. In the production app (one
# controller, runs until exit) this is a latent leak; in the test suite
# (constructs ~50 controllers per process) the deferred destructor fires
# mid-construction of the next controller and segfaults.
#
# The make_controller fixture (test/_helpers/controller_fixture.py) calls
# sip.delete(controller) in its teardown so each fixture-made controller's
# C++ tree is destroyed deterministically. The pytest_runtest_teardown
# hook below extends that to EVERY test: after each test it sip.deletes
# any remaining top-level widgets (e.g. the _MockController + collaborators
# that test_main_bootstrap constructs via main() without going through the
# fixture or qtbot.addWidget). pytest-qt's own _close_widgets uses
# deleteLater (deferred to the event loop), which races with the next
# test's widget construction; sip.delete forces immediate C++ destruction.


@pytest.hookimpl(trylast=True)
def pytest_runtest_teardown(item, nextitem):
    """Deterministically destroy every top-level QWidget after each test so
    C++ destructors run NOW (under our control) instead of being deferred
    by deleteLater / cyclic GC and racing with the next test's widget
    construction. Runs trylast so pytest-qt's _close_widgets (which uses
    deleteLater) has already run; we clean up whatever it left behind.

    This prevents the mid-run segfault where a prior controller's deferred
    C++ destructor fires inside the next test's QMainWindow.__init__. The
    remaining shutdown-time segfault (Python atexit re-enabling GC and
    collecting the orphaned Python wrapper cycles from the 53
    self-capturing signal lambdas — see ROADMAP.md Phase 6 known issue)
    only kills workers AFTER they have written coverage data and sent
    test results, so it does not affect the gate's pass/fail or coverage
    totals (xdist reports "failed workers" but the data is already
    written; the master combines the per-worker .coverage files).
    """
    try:
        from PyQt5.QtWidgets import QApplication
        import sip
        app = QApplication.instance()
        if app is None:
            return
        for w in list(app.topLevelWidgets()):
            try:
                sip.delete(w)
            except (TypeError, RuntimeError):
                # Already deleted or not sip-managed — skip.
                pass
        app.processEvents()
    except Exception:
        # PyQt5/sip not available (tests skipped) — nothing to clean up.
        pass
