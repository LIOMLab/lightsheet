"""Phase 7 (PySide6/Qt6 migration) Nyquist invariant tests.

Four safety-critical / structural invariants that the Phase 7 migration must
preserve, asserted as behavioral and source-assert unit tests:

1. MIG-05 — the E-stop kill-path SLOT ``updateUi_estop_pressed`` is defined
   ONLY in the shell (``lightsheet/gui/controller.py``), NOT in any of the 7
   per-panel widget modules. The lock-free GUI-thread kill path must keep a
   single owner; a panel defining the slot would be a safety regression.
   (``test_panel_structure.py`` only guards the BUTTON WIDGET subtree — it
   does NOT guard against a panel *defining the slot method*.)

2. MIG-05 — the monolithic ``ui_controller`` files are DELETED and the 7
   per-panel modules + ``ui_shell`` + native ``image_view`` (MIG-08) EXIST.

3. MIG-07 — the controller's ``estop_event`` attribute is a
   ``threading.Event`` instance (NOT a QThread interruption API).
   ``test_estop.py`` tests a FRESH ``threading.Event()`` in isolation; this
   test verifies the REAL controller's ``estop_event`` stays
   ``threading.Event`` under the QThread migration.

4. MIG-07 — (a) ``requestInterruption`` is NOT referenced anywhere in
   ``lightsheet/`` (the QThread interruption API is intentionally NOT
   adopted — ``estop_event`` is the cooperative-abort mechanism); (b)
   ``laser_panel.py`` creates the 4 laser toggle/power daemon threads as
   ``threading.Thread`` (not QThread) to preserve the lock-free E-stop kill
   path.

GAP 1, 2, 4 are pure-Python (importlib, pathlib, threading, source reads).
GAP 3 needs the ``make_controller`` fixture which requires qtbot + PySide6.
The panel modules import PySide6 transitively (importing ``laser_panel``
triggers ``from PySide6...``), so the module-level
``pytest.importorskip("PySide6")`` mirrors ``test_panel_structure.py``.
"""

from __future__ import annotations

import importlib
import threading
from pathlib import Path

import pytest

# Importing any panel module pulls in PySide6 transitively, so gate the whole
# module on PySide6 being importable — mirrors test_panel_structure.py.
pytest.importorskip("PySide6")

# Repository root (test/ is one level below it) → lightsheet/gui/...
_REPO_ROOT = Path(__file__).resolve().parent.parent
_GUI_DIR = _REPO_ROOT / "lightsheet" / "gui"
_LIGHTSHEET_DIR = _REPO_ROOT / "lightsheet"

# The 7 per-panel widget modules produced by the 7B modularization split.
_PANEL_MODULE_NAMES = (
    "laser_panel",
    "motor_panel",
    "acquisition_panel",
    "save_panel",
    "stack_panel",
    "scan_panel",
    "calibration_panel",
)


# --------------------------------------------------------------------------- #
# GAP 1 — MIG-05 (SAFETY-CRITICAL): the E-stop kill-path SLOT lives ONLY in
# the shell. No per-panel module may define ``updateUi_estop_pressed``.
# --------------------------------------------------------------------------- #


def test_estop_slot_lives_only_in_shell() -> None:
    """The E-stop kill-path SLOT ``updateUi_estop_pressed`` is defined on the
    shell's ``Controller_MainWindow`` and on NONE of the 7 per-panel widget
    modules.

    ``test_panel_structure.py::test_estop_button_in_shell`` only asserts the
    E-stop BUTTON WIDGET (``pushButton_estop``) is not in any panel's widget
    subtree — it does NOT guard against a panel *defining the kill-path slot
    method*. A panel defining ``updateUi_estop_pressed`` would be a safety
    regression: the lock-free GUI-thread kill path must have a single owner
    (the shell), per AGENTS.md §2.
    """
    from lightsheet.gui.shell.controller import Controller_MainWindow

    # Positive control — the shell MUST own the kill-path slot.
    assert hasattr(Controller_MainWindow, "updateUi_estop_pressed"), (
        "Controller_MainWindow must define updateUi_estop_pressed "
        "(the E-stop kill-path slot, AGENTS.md §2)."
    )

    # Negative control — no per-panel module may define the kill-path slot.
    for name in _PANEL_MODULE_NAMES:
        mod = importlib.import_module(f"lightsheet.gui.panels.{name}")
        assert not hasattr(mod, "updateUi_estop_pressed"), (
            f"lightsheet.gui.panels.{name} defines updateUi_estop_pressed — the "
            "E-stop kill-path slot must live ONLY in the shell "
            "(lightsheet/gui/shell/controller.py), lock-free on the GUI thread "
            "(AGENTS.md §2). A panel owning the kill path is a safety "
            "regression."
        )


# --------------------------------------------------------------------------- #
# GAP 2 — MIG-05 (structural): the monolithic ui_controller files are DELETED
# and the 7 per-panel modules + ui_shell + native image_view (MIG-08) EXIST.
# --------------------------------------------------------------------------- #


def test_monolithic_ui_controller_deleted_and_panels_exist() -> None:
    """The monolithic ``ui_controller`` files are gone and the 7 per-panel
    modules + ``ui_shell`` import cleanly; the native ``image_view`` (MIG-08)
    exists on disk."""
    # The monolithic ui_controller files MUST be deleted.
    assert not (_GUI_DIR / "ui_controller.py").exists(), (
        "lightsheet/gui/ui_controller.py must be deleted — the monolithic "
        "controller was split into 7 per-panel modules + ui_shell."
    )
    assert not (_GUI_DIR / "ui_controller.ui").exists(), (
        "lightsheet/gui/ui_controller.ui must be deleted."
    )
    assert not (_GUI_DIR / "ui_controller_rc.py").exists(), (
        "lightsheet/gui/ui_controller_rc.py must be deleted."
    )

    # The 7 per-panel modules + the shell must import cleanly.
    for name in _PANEL_MODULE_NAMES:
        importlib.import_module(f"lightsheet.gui.panels.{name}")
    importlib.import_module("lightsheet.gui.shell.ui_shell")

    # The native ImageView (MIG-08) must exist on disk.
    assert (_GUI_DIR / "panels" / "image_view.py").exists(), (
        "lightsheet/gui/panels/image_view.py must exist — the native Qt6 "
        "ImageView replaced the dropped pyqtgraph ImageView (MIG-08)."
    )


# --------------------------------------------------------------------------- #
# GAP 3 — MIG-07 (SAFETY-CRITICAL, behavior): the REAL controller's
# estop_event is a threading.Event instance (NOT a QThread interruption API).
# test_estop.py tests a FRESH threading.Event() in isolation; this verifies
# the real controller's attribute stays threading.Event under the QThread
# migration.
# --------------------------------------------------------------------------- #


def test_controller_estop_event_is_threading_event(qtbot, request) -> None:
    """The real controller's ``estop_event`` is a ``threading.Event``
    instance — the MIG-07 invariant that the cooperative-abort mechanism
    stays ``threading.Event`` under the QThread migration (NOT replaced by
    the QThread interruption API). Uses the real-construction fixture (same
    pattern as ``test_panel_structure.py::test_shell_composes_panels``)."""
    from _helpers.controller_fixture import make_controller

    ctrl, _ = make_controller(qtbot, request)

    assert isinstance(ctrl.estop_event, threading.Event), (
        f"ctrl.estop_event must be a threading.Event instance, got "
        f"{type(ctrl.estop_event).__name__} — the cooperative-abort "
        "mechanism must stay threading.Event under the QThread migration "
        "(MIG-07)."
    )


# --------------------------------------------------------------------------- #
# GAP 4 — MIG-07 (source-assert): (a) requestInterruption is NOT referenced
# anywhere in lightsheet/ (the QThread interruption API is intentionally NOT
# adopted — estop_event is the cooperative-abort mechanism); (b) laser_panel
# creates the 4 laser toggle/power daemon threads as threading.Thread (not
# QThread) to preserve the lock-free E-stop kill path.
# --------------------------------------------------------------------------- #


def test_no_request_interruption_in_lightsheet() -> None:
    """``requestInterruption`` (the QThread interruption API) does NOT appear
    anywhere in ``lightsheet/`` source. The cooperative-abort mechanism is
    ``estop_event`` (a ``threading.Event``), polled at the top of every
    acquisition worker loop — the QThread interruption API is intentionally
    NOT adopted (MIG-07)."""
    offenders: list[str] = []
    for py_file in _LIGHTSHEET_DIR.rglob("*.py"):
        # Skip __pycache__ bytecode cache files (none are .py, but be safe).
        if "__pycache__" in py_file.parts:
            continue
        try:
            text = py_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if "requestInterruption" in text:
            offenders.append(str(py_file.relative_to(_REPO_ROOT)))

    assert not offenders, (
        "requestInterruption (the QThread interruption API) must NOT appear "
        "anywhere in lightsheet/ — estop_event (threading.Event) is the "
        "cooperative-abort mechanism (MIG-07). Offending files: "
        + ", ".join(offenders)
    )


def test_laser_panel_daemons_are_threading_thread() -> None:
    """``laser_panel.py`` creates the 4 laser toggle/power daemon threads as
    ``threading.Thread`` (not QThread) — preserving the lock-free E-stop kill
    path. A queued/QThread-offloaded toggle would have to be checked against
    ``estop_event`` before energizing, and a stuck toggle thread must never
    delay the kill path (AGENTS.md §2). The 4 daemons are: laser1 amplitude
    write, laser2 amplitude write, laser1 toggle, laser2 toggle."""
    source = (_GUI_DIR / "panels" / "laser_panel.py").read_text(encoding="utf-8")
    count = source.count("threading.Thread(")
    assert count >= 4, (
        f"laser_panel.py must create the 4 laser daemon threads via "
        f"threading.Thread (not QThread) to preserve the lock-free E-stop "
        f"kill path (MIG-07 / AGENTS.md §2). Found only {count} "
        f"threading.Thread( call(s); expected >= 4."
    )
