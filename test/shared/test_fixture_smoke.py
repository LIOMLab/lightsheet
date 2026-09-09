"""Smoke test: verify the real-construction fixture builds the controller
and a real method call works + produces branch coverage."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

pytest.importorskip("PySide6")

if TYPE_CHECKING:
    from lightsheet.gui.shell.controller import Controller_MainWindow


def test_fixture_constructs_controller(
    controller: Controller_MainWindow,
) -> None:
    assert controller is not None
    assert controller._hw is not None
    assert controller._acq is not None
    assert controller._fs is not None
    assert controller._mc is not None
    assert len(controller.lasers) == 2


def test_real_method_call_works(controller: Controller_MainWindow) -> None:
    controller.updateUi_light_theme()
    controller.updateUi_dark_theme()
    # exercise a branch: show/hide pane
    controller.ui.imagesPane.isVisible = lambda: True
    controller.updateUi_show_hide_images_pane()
