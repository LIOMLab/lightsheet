"""Tracer canary: prove the new controller fixture tears down completely.

The second test intentionally does *not* request the ``controller`` fixture;
it relies on the first test's teardown (plus the global autouse cleanup) to
leave the Qt application with no top-level widgets.
"""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from lightsheet.gui.shell.controller import Controller_MainWindow


def test_controller_fixture_constructs_and_teardowns(
    controller: Controller_MainWindow,
) -> None:
    """The fixture builds a real Controller_MainWindow with all collaborators."""
    assert controller is not None
    assert controller._fs is not None
    assert controller._hw is not None
    assert controller._acq is not None
    assert controller._mc is not None


def test_no_top_level_widgets_after_teardown() -> None:
    """Teardown reaps the full controller widget tree."""
    app = QApplication.instance()
    assert app is not None
    try:
        widgets = app.topLevelWidgets()
    except RuntimeError:
        widgets = []
    assert widgets == []
