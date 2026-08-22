"""Behavior tests for the editable install (PKG-01).

Proves that ``lightsheet.*`` (physical ``src/``) and ``gui`` resolve as
installed top-level packages from any CWD — i.e. via the editable install,
not via a ``sys.path.append`` hack or CWD-relative resolution. Also locks
in the registered ``lightsheet`` console-script entry point.

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
    present) imports ``lightsheet.config`` and ``gui`` successfully —
    proving resolution comes from the installed distribution, not from
    the CWD."""
    result = subprocess.run(
        [sys.executable, "-c", "import lightsheet.config, gui"],
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
    """``gui.controller.Controller_MainWindow`` imports where PyQt5 is
    available; skipped otherwise (PyQt5 is not stubbed by conftest)."""
    try:
        from gui.controller import Controller_MainWindow  # noqa: F401
    except ImportError as exc:
        pytest.skip(f"PyQt5 not installed: {exc}")
