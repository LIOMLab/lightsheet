"""Branch-coverage tests for CalibrationPanelWidget.

The panel's ``__init__`` loops over ``FIELD_SPECS`` and calls ``applySpec``
on every matching widget. The calibration panel's three FieldSpecSpinBox
widgets (``doubleSpinBox_calNumberOfPlanes`` / ``calNumberOfCameraPositions``
/ ``calNumberOfEtlVoltages``) are NOT in ``FIELD_SPECS`` (they are count
fields with no fixed unit/range contract), so the loop is a no-op for them
in production. The ``if w is not None and hasattr(w, "applySpec")`` True
branch (entering the body and calling ``applySpec``) is therefore only
reachable when a FIELD_SPECS entry matches a widget on the panel.

This test patches ``FIELD_SPECS`` to include one of the calibration panel's
FieldSpecSpinBox widget names so the True branch fires and ``applySpec`` is
actually called — verifying the loop's apply path works on this panel.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from pytestqt.qtbot import QtBot

from _helpers.controller_fixture import make_controller
from lightsheet.gui.widgets.field_spec import FieldSpec


def test_calibration_panel_applies_field_spec_to_matching_widget(
    qtbot: QtBot, request: pytest.FixtureRequest
) -> None:
    """When a FIELD_SPECS entry matches a widget on the calibration panel,
    ``applySpec`` is called on that widget. Patches FIELD_SPECS to include
    the calibration panel's ``doubleSpinBox_calNumberOfPlanes`` widget so
    the loop's True branch (``w is not None and hasattr(w, "applySpec")``)
    fires and the spec is applied."""
    from lightsheet.gui.panels import calibration_panel as mod

    ctrl, _ = make_controller(qtbot, request)
    panel = ctrl.calibration_panel
    spinbox = panel.ui.doubleSpinBox_calNumberOfPlanes
    assert hasattr(spinbox, "applySpec"), (
        "doubleSpinBox_calNumberOfPlanes must be a FieldSpecSpinBox with applySpec"
    )

    spec = FieldSpec(
        unit="",
        decimals=0,
        single_step=1.0,
        page_step=10.0,
        minimum=1.0,
        maximum=500.0,
    )
    patched_specs = {"doubleSpinBox_calNumberOfPlanes": spec}

    with patch.object(mod, "FIELD_SPECS", patched_specs):
        rebuilt = mod.CalibrationPanelWidget(ctrl)
        qtbot.addWidget(rebuilt)

    # applySpec was called: the spinbox's suffix should reflect the spec's
    # unit (empty string here) and the decimals should match.
    assert rebuilt.ui.doubleSpinBox_calNumberOfPlanes.decimals() == 0
    assert rebuilt.ui.doubleSpinBox_calNumberOfPlanes.minimum() == 1.0
    assert rebuilt.ui.doubleSpinBox_calNumberOfPlanes.maximum() == 500.0
