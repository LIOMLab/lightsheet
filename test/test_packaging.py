"""Behavior tests for the editable install (PKG-01).

Proves that ``lightsheet`` (with ``lightsheet.gui`` as a subpackage)
resolves as an installed top-level package from any CWD — i.e. via the
editable install, not via a ``sys.path.append`` hack or CWD-relative
resolution. Also locks in the registered ``lightsheet`` console-script
entry point.

These are runtime behavior tests: they execute real imports (including a
subprocess rooted in an empty temp directory) and assert on the installed
distribution metadata. No source file is read as text and ``sys.path`` is
not manipulated.
"""

import importlib.metadata
import subprocess
import sys
from pathlib import Path

import pytest


def test_lightsheet_pure_modules_import() -> None:
    """The pure-logic lightsheet modules import as installed packages and
    expose their public callables."""
    from lightsheet.config import cfg_read
    from lightsheet.gaussian import func, fwhm, gaussian
    from lightsheet.waveforms import sawtooth, squarewave, staircase

    assert callable(cfg_read)
    assert callable(fwhm)
    assert callable(func)
    assert callable(gaussian)
    assert callable(sawtooth)
    assert callable(squarewave)
    assert callable(staircase)


def test_lightsheet_imports_from_foreign_cwd(tmp_path: Path) -> None:
    """A subprocess rooted in an empty temp directory (no repo files
    present) imports ``lightsheet.config`` and ``lightsheet.gui``
    successfully — proving resolution comes from the installed
    distribution, not from the CWD."""
    result = subprocess.run(
        [sys.executable, "-c", "import lightsheet.config, lightsheet.gui"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"subprocess import failed from foreign CWD {tmp_path}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_console_script_entry_point_registered() -> None:
    """The ``console_scripts`` entry point named ``lightsheet`` exists and
    points at ``lightsheet.__main__:main``."""
    eps = importlib.metadata.entry_points(group="console_scripts")
    matches = [
        e
        for e in eps
        if e.name == "lightsheet" and e.value == "lightsheet.__main__:main"
    ]
    assert matches, "lightsheet = lightsheet.__main__:main entry point not registered"


def test_gui_controller_imports() -> None:
    """``lightsheet.gui.controller.Controller_MainWindow`` imports where
    PyQt5 is available; skipped otherwise (PyQt5 is not stubbed by
    conftest)."""
    try:
        from lightsheet.gui.controller import Controller_MainWindow  # noqa: F401
    except ImportError as exc:
        pytest.skip(f"PyQt5 not installed: {exc}")


def test_gui_controller_imports_from_foreign_cwd(tmp_path: Path) -> None:
    """A subprocess rooted in an empty temp directory (no repo files
    present) imports ``lightsheet.gui.controller`` — which transitively
    imports ``lightsheet.gui.ui_controller``, whose tail runs
    ``from . import ui_controller_rc`` (the package-relative resource
    import emitted by ``pyuic5 --from-imports``).

    With the package-relative import this succeeds from a foreign CWD.
    If the inherited ``sys.path.append("./gui")`` + bare
    ``import ui_controller_rc`` hack were re-introduced, this subprocess
    would fail with ``ModuleNotFoundError: No module named 'ui_controller_rc'``
    (because ``./lightsheet/gui`` does not exist in the empty CWD). This is
    the adversarial can-fail test for the path-hack elimination (D-05)."""
    result = subprocess.run(
        [sys.executable, "-c", "import lightsheet.gui.controller"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"subprocess import failed from foreign CWD {tmp_path}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_lightsheet_hal_modules_import_as_top_level(tmp_path: Path) -> None:
    """The HAL modules import via the installed ``lightsheet`` package from
    a foreign CWD. After the Phase 3 Wave 3 reorg (D-01), all 6 device
    families (``camera``, ``siggen``, ``motors``, ``etls``, ``lasers``,
    ``ibeam``) live under ``lightsheet.hal`` (re-exported from
    ``lightsheet.hal.real.*``); ``logging_setup`` stays top-level
    permanently.

    A subprocess rooted in an empty temp directory imports the full set.
    The real nidaqmx / pco / pyserial packages are installed in the venv
    (they just cannot construct hardware objects on the Mac), so the
    imports succeed in the subprocess."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from lightsheet.hal import ("
            "Camera, SigGen, Motors, ETLs, IBeam, "
            "DAQLaser, IBeamSmartLaser, MockLaser"
            "); "
            "from lightsheet import logging_setup",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"subprocess import failed from foreign CWD {tmp_path}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
