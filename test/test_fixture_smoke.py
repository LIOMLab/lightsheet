"""Smoke test: verify the real-construction fixture builds the controller
and a real method call works + produces branch coverage."""
import pytest

pytest.importorskip("PySide6")

from _helpers.controller_fixture import make_controller


def test_fixture_constructs_controller(qtbot, request):
    ctrl, bundle = make_controller(qtbot, request)
    assert ctrl is not None
    assert ctrl._hw is not None
    assert ctrl._acq is not None
    assert ctrl._fs is not None
    assert ctrl._mc is not None
    assert len(ctrl.lasers) == 2


def test_real_method_call_works(qtbot, request):
    ctrl, _ = make_controller(qtbot, request)
    ctrl.updateUi_light_theme()
    ctrl.updateUi_dark_theme()
    # exercise a branch: show/hide pane
    ctrl.ui.imagesPane.isVisible = lambda: True
    ctrl.updateUi_show_hide_images_pane()
