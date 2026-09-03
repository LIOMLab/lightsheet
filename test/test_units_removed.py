"""Units selector removal regression test.

The global units toggle (``comboBox_units`` + ``label_units``) was removed
from the shell. Per-field units are now fixed (motor travel in mm, plane
step in µm); per-field suffix/decimals land via FieldSpec in a later plan.
This module is the regression gate that asserts the removal is complete:

- ``comboBox_units`` is absent from ``ui_shell.ui`` and from the generated
  ``ui_shell.py``.
- The constructed controller has no ``comboBox_units`` widget on ``ui``.
- The controller has no ``units`` attribute (the global toggle's backing
  attribute is gone).
- The shell reference exposes no ``units`` attribute.
- No ``self._shell.units`` reads remain in ``motor_panel`` / ``stack_panel``.

Runs headless on Mac via ``QT_QPA_PLATFORM=offscreen`` (set by conftest).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pytest import FixtureRequest
from pytestqt.qtbot import QtBot

pytest.importorskip("PySide6")

from _helpers.controller_fixture import make_controller

_REPO_ROOT = Path(__file__).resolve().parent.parent
_UI_SHELL_UI = _REPO_ROOT / "lightsheet" / "gui" / "shell" / "ui_shell.ui"
_UI_SHELL_PY = _REPO_ROOT / "lightsheet" / "gui" / "shell" / "ui_shell.py"
_MOTOR_PANEL = _REPO_ROOT / "lightsheet" / "gui" / "panels" / "motor_panel.py"
_STACK_PANEL = _REPO_ROOT / "lightsheet" / "gui" / "panels" / "stack_panel.py"


def test_comboBox_units_absent_from_ui_file() -> None:
    """comboBox_units is not declared in ui_shell.ui."""
    text = _UI_SHELL_UI.read_text(encoding="utf-8")
    assert "comboBox_units" not in text, (
        "comboBox_units still declared in ui_shell.ui — the units selector "
        "was not removed from the .ui file"
    )


def test_comboBox_units_absent_from_generated_ui_py() -> None:
    """comboBox_units is not in the generated ui_shell.py."""
    text = _UI_SHELL_PY.read_text(encoding="utf-8")
    assert "comboBox_units" not in text, (
        "comboBox_units still present in ui_shell.py — the .ui was not "
        "regenerated after the units selector removal"
    )


def test_label_units_absent_from_ui_file() -> None:
    """label_units is not declared in ui_shell.ui."""
    text = _UI_SHELL_UI.read_text(encoding="utf-8")
    assert 'name="label_units"' not in text, "label_units still declared in ui_shell.ui"


def test_controller_ui_has_no_comboBox_units(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """The constructed controller's ui has no comboBox_units attribute."""
    ctrl, _ = make_controller(qtbot, request)
    assert not hasattr(ctrl.ui, "comboBox_units"), (
        "controller.ui still has a comboBox_units attribute — the shell "
        "merge loop or the .ui is still surfacing the removed widget"
    )


def test_controller_has_no_units_attribute(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """The controller has no ``units`` attribute (the global toggle's
    backing attribute is gone)."""
    ctrl, _ = make_controller(qtbot, request)
    assert not hasattr(ctrl, "units"), (
        "controller still has a 'units' attribute — the global units "
        "toggle's backing attribute was not removed"
    )


def test_controller_has_no_units_fixformat(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """The controller has no ``units_fixformat`` / ``units_decimals`` /
    ``units_increment`` attributes (set by the old updateUi_units)."""
    ctrl, _ = make_controller(qtbot, request)
    assert not hasattr(ctrl, "units_fixformat")
    assert not hasattr(ctrl, "units_decimals")
    assert not hasattr(ctrl, "units_increment")


def test_motor_panel_has_no_shell_units_reads() -> None:
    """motor_panel.py has no ``self._shell.units`` reads."""
    text = _MOTOR_PANEL.read_text(encoding="utf-8")
    assert "_shell.units" not in text, (
        "motor_panel.py still reads self._shell.units — the units removal "
        "left a stale read site"
    )


def test_stack_panel_has_no_shell_units_reads() -> None:
    """stack_panel.py has no ``self._shell.units`` reads and no
    comboBox_units reads."""
    text = _STACK_PANEL.read_text(encoding="utf-8")
    assert "_shell.units" not in text, (
        "stack_panel.py still reads self._shell.units — the units removal "
        "left a stale read site"
    )
    assert "comboBox_units" not in text, (
        "stack_panel.py still reads comboBox_units — the units removal "
        "left a stale read site"
    )
