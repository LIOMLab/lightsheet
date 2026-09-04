"""AcquisitionCoordinator galvo/ETL/camera UI slot branch coverage.

The 18 ``updateUi_*`` slots at the tail of ``acquisition_coordinator.py``
(lines 610-952) are plain-Python: each reads ``self._shell.ui.*`` widgets
and writes ``self.siggen.*`` / ``self.camera.*`` HAL attributes. They are
tested here by constructing the real ``AcquisitionCoordinator`` against a
Mock shell + a real ``MockSigGen`` / ``MockCamera`` bundle and asserting on
the propagated HAL attribute writes and the sibling-widget sync calls.

Behavior tests (AGENTS.md §5) — every assertion is on a runtime
postcondition (HAL attribute value, sibling-widget setValue call), never a
static-source grep.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

pytest.importorskip("PySide6")

from lightsheet.gui.coordinators.acquisition_coordinator import AcquisitionCoordinator
from lightsheet.hal import (
    DeviceBundle,
)


def _make_bundle() -> DeviceBundle:
    from test.helpers.factories import make_bundle

    return make_bundle()


class _Shell:
    """Minimal shell stand-in exposing the ui widgets + siggen/camera refs
    the slots read/write."""

    def __init__(self) -> None:
        self.ui = Mock()
        # Hybrid ownership: the coordinator slots reach panel-internal
        # widgets via self._shell.<panel>.ui.<name>. Expose the panels
        # the slots read (scan_panel for galvo/ETL, acquisition_panel for
        # camera) as Mocks so their .ui.<widget> attrs auto-create.
        self.scan_panel = Mock()
        self.acquisition_panel = Mock()
        # Default widget values used by the slots.
        self.scan_panel.ui.doubleSpinBox_galvoLeftAmplitude.value.return_value = 1.5
        self.scan_panel.ui.doubleSpinBox_galvoRightAmplitude.value.return_value = 1.0
        self.scan_panel.ui.doubleSpinBox_galvoLeftOffset.value.return_value = 0.5
        self.scan_panel.ui.doubleSpinBox_galvoRightOffset.value.return_value = 0.5
        self.scan_panel.ui.doubleSpinBox_etlLeftAmplitude.value.return_value = 1.0
        self.scan_panel.ui.doubleSpinBox_etlRightAmplitude.value.return_value = 1.0
        self.scan_panel.ui.doubleSpinBox_etlLeftOffset.value.return_value = 2.5
        self.scan_panel.ui.doubleSpinBox_etlRightOffset.value.return_value = 2.5
        self.scan_panel.ui.doubleSpinBox_etlSteps.value.return_value = 5
        exposure_spinbox = self.acquisition_panel.ui.doubleSpinBox_cameraExposureTime
        exposure_spinbox.value.return_value = 100
        line_time_spinbox = self.acquisition_panel.ui.doubleSpinBox_cameraLineTime
        line_time_spinbox.value.return_value = 48.8
        exposed_spinbox = self.acquisition_panel.ui.doubleSpinBox_cameraExposedLines
        exposed_spinbox.value.return_value = 16
        self.acquisition_panel.ui.doubleSpinBox_cameraDelayLines.value.return_value = 0
        shutter_combo = self.acquisition_panel.ui.comboBox_cameraShutterMode
        shutter_combo.currentText.return_value = "Rolling"
        # Sync checkboxes — default unchecked (the no-sync branch).
        self.scan_panel.ui.checkBox_galvoSync.isChecked.return_value = False
        self.scan_panel.ui.checkBox_etlSync.isChecked.return_value = False
        self.scan_panel.ui.checkBox_galvoActivate.isChecked.return_value = True
        self.scan_panel.ui.checkBox_galvoInvert.isChecked.return_value = False
        self.scan_panel.ui.checkBox_etlActivate.isChecked.return_value = True
        # Offset min/max are read inside the sync branches — provide real floats.
        self.scan_panel.ui.doubleSpinBox_galvoLeftOffset.minimum.return_value = -10.0
        self.scan_panel.ui.doubleSpinBox_galvoLeftOffset.maximum.return_value = 10.0
        self.scan_panel.ui.doubleSpinBox_galvoRightOffset.minimum.return_value = -10.0
        self.scan_panel.ui.doubleSpinBox_galvoRightOffset.maximum.return_value = 10.0
        self.scan_panel.ui.doubleSpinBox_etlLeftOffset.minimum.return_value = -5.0
        self.scan_panel.ui.doubleSpinBox_etlLeftOffset.maximum.return_value = 5.0
        self.scan_panel.ui.doubleSpinBox_etlRightOffset.minimum.return_value = -5.0
        self.scan_panel.ui.doubleSpinBox_etlRightOffset.maximum.return_value = 5.0


def _make_acq() -> tuple[AcquisitionCoordinator, _Shell]:
    bundle = _make_bundle()
    shell = _Shell()
    hw = Mock()
    acq = AcquisitionCoordinator(bundle, hw, shell)  # ty: ignore[invalid-argument-type]
    return acq, shell


# -- Galvo amplitude/offset slots (sync + no-sync branches) ------------------


def test_galvo_amplitude_slots_propagate_and_sync() -> None:
    """The four galvo amplitude arcs (left/right x sync/no-sync) in one
    test: no-sync propagates the widget value to siggen; sync mirrors the
    value to the sibling widget via setValue. Mock's setValue does not
    update value.return_value, so the siggen reads the sibling's
    pre-existing value after the mirror — asserted verbatim."""
    # Left, no-sync.
    acq, shell = _make_acq()
    acq.updateUi_galvo_left_amplitude()
    assert acq.siggen.galvo_left_amplitude == 1.5
    shell.scan_panel.ui.doubleSpinBox_galvoLeftOffset.setMinimum.assert_called()
    shell.scan_panel.ui.doubleSpinBox_galvoLeftOffset.setMaximum.assert_called()

    # Left, sync -> mirrors to right.
    acq, shell = _make_acq()
    shell.scan_panel.ui.checkBox_galvoSync.isChecked.return_value = True
    acq.updateUi_galvo_left_amplitude()
    shell.scan_panel.ui.doubleSpinBox_galvoRightAmplitude.setValue.assert_called_with(
        1.5
    )
    shell.scan_panel.ui.doubleSpinBox_galvoRightOffset.setValue.assert_called_with(0.5)
    assert acq.siggen.galvo_right_amplitude == 1.0

    # Right, no-sync.
    acq, shell = _make_acq()
    acq.updateUi_galvo_right_amplitude()
    assert acq.siggen.galvo_right_amplitude == 1.0

    # Right, sync -> mirrors to left.
    acq, shell = _make_acq()
    shell.scan_panel.ui.checkBox_galvoSync.isChecked.return_value = True
    acq.updateUi_galvo_right_amplitude()
    shell.scan_panel.ui.doubleSpinBox_galvoLeftAmplitude.setValue.assert_called_with(
        1.0
    )
    assert acq.siggen.galvo_left_amplitude == 1.5


def test_galvo_offset_slots_propagate_and_sync() -> None:
    """The four galvo offset arcs (left/right x sync/no-sync) in one test."""
    # Left, no-sync.
    acq, _shell = _make_acq()
    acq.updateUi_galvo_left_offset()
    assert acq.siggen.galvo_left_offset == 0.5

    # Left, sync -> mirrors to right.
    acq, shell = _make_acq()
    shell.scan_panel.ui.checkBox_galvoSync.isChecked.return_value = True
    acq.updateUi_galvo_left_offset()
    shell.scan_panel.ui.doubleSpinBox_galvoRightOffset.setValue.assert_called_with(0.5)
    assert acq.siggen.galvo_right_offset == 0.5

    # Right, no-sync.
    acq, _shell = _make_acq()
    acq.updateUi_galvo_right_offset()
    assert acq.siggen.galvo_right_offset == 0.5

    # Right, sync -> mirrors to left.
    acq, shell = _make_acq()
    shell.scan_panel.ui.checkBox_galvoSync.isChecked.return_value = True
    acq.updateUi_galvo_right_offset()
    shell.scan_panel.ui.doubleSpinBox_galvoLeftOffset.setValue.assert_called_with(0.5)
    assert acq.siggen.galvo_left_offset == 0.5


def test_galvo_sync_checked_mirrors_left_to_right() -> None:
    """updateUi_galvo_sync mirrors left -> right when the sync checkbox
    is checked (the if-branch)."""
    acq, shell = _make_acq()
    shell.scan_panel.ui.checkBox_galvoSync.isChecked.return_value = True
    acq.updateUi_galvo_sync()
    shell.scan_panel.ui.doubleSpinBox_galvoRightAmplitude.setValue.assert_called_with(
        1.5
    )
    shell.scan_panel.ui.doubleSpinBox_galvoRightOffset.setValue.assert_called_with(0.5)
    # siggen.galvo_right_amplitude reads the right widget's .value() after
    # setValue — Mock's setValue does not update value.return_value, so the
    # siggen reads the right widget's pre-existing value (1.0).
    assert acq.siggen.galvo_right_amplitude == 1.0


def test_galvo_sync_unchecked_is_noop_on_siggen() -> None:
    """updateUi_galvo_sync with sync unchecked does not mirror (the
    else-branch — no siggen write)."""
    acq, _shell = _make_acq()
    acq.siggen.galvo_right_amplitude = 0.0
    acq.updateUi_galvo_sync()
    # No right-amplitude write occurred.
    assert acq.siggen.galvo_right_amplitude == 0.0


def test_galvo_activate_propagates_to_siggen() -> None:
    acq, shell = _make_acq()
    shell.scan_panel.ui.checkBox_galvoActivate.isChecked.return_value = True
    acq.updateUi_galvo_activate()
    assert acq.siggen.galvo_activated is True


def test_galvo_invert_propagates_to_siggen() -> None:
    acq, shell = _make_acq()
    shell.scan_panel.ui.checkBox_galvoInvert.isChecked.return_value = True
    acq.updateUi_galvo_invert()
    assert acq.siggen.galvo_inverted is True


# -- ETL amplitude/offset slots (sync + no-sync branches) --------------------


def test_etl_amplitude_slots_propagate_and_sync() -> None:
    """The four ETL amplitude arcs (left/right x sync/no-sync) in one test."""
    # Left, no-sync.
    acq, shell = _make_acq()
    acq.updateUi_etl_left_amplitude()
    assert acq.siggen.etl_left_amplitude == 1.0
    shell.scan_panel.ui.doubleSpinBox_etlLeftOffset.setMinimum.assert_called()
    shell.scan_panel.ui.doubleSpinBox_etlLeftOffset.setMaximum.assert_called()

    # Left, sync -> mirrors to right.
    acq, shell = _make_acq()
    shell.scan_panel.ui.checkBox_etlSync.isChecked.return_value = True
    acq.updateUi_etl_left_amplitude()
    shell.scan_panel.ui.doubleSpinBox_etlRightAmplitude.setValue.assert_called_with(1.0)
    assert acq.siggen.etl_right_amplitude == 1.0

    # Right, no-sync.
    acq, _shell = _make_acq()
    acq.updateUi_etl_right_amplitude()
    assert acq.siggen.etl_right_amplitude == 1.0

    # Right, sync -> mirrors to left.
    acq, shell = _make_acq()
    shell.scan_panel.ui.checkBox_etlSync.isChecked.return_value = True
    acq.updateUi_etl_right_amplitude()
    shell.scan_panel.ui.doubleSpinBox_etlLeftAmplitude.setValue.assert_called_with(1.0)
    assert acq.siggen.etl_left_amplitude == 1.0


def test_etl_offset_slots_propagate_and_sync() -> None:
    """The four ETL offset arcs (left/right x sync/no-sync) in one test."""
    # Left, no-sync.
    acq, _shell = _make_acq()
    acq.updateUi_etl_left_offset()
    assert acq.siggen.etl_left_offset == 2.5

    # Left, sync -> mirrors to right.
    acq, shell = _make_acq()
    shell.scan_panel.ui.checkBox_etlSync.isChecked.return_value = True
    acq.updateUi_etl_left_offset()
    shell.scan_panel.ui.doubleSpinBox_etlRightOffset.setValue.assert_called_with(2.5)
    assert acq.siggen.etl_right_offset == 2.5

    # Right, no-sync.
    acq, _shell = _make_acq()
    acq.updateUi_etl_right_offset()
    assert acq.siggen.etl_right_offset == 2.5

    # Right, sync -> mirrors to left.
    acq, shell = _make_acq()
    shell.scan_panel.ui.checkBox_etlSync.isChecked.return_value = True
    acq.updateUi_etl_right_offset()
    shell.scan_panel.ui.doubleSpinBox_etlLeftOffset.setValue.assert_called_with(2.5)
    assert acq.siggen.etl_left_offset == 2.5


def test_etl_sync_checked_mirrors_left_to_right() -> None:
    acq, shell = _make_acq()
    shell.scan_panel.ui.checkBox_etlSync.isChecked.return_value = True
    acq.updateUi_etl_sync()
    shell.scan_panel.ui.doubleSpinBox_etlRightAmplitude.setValue.assert_called_with(1.0)
    shell.scan_panel.ui.doubleSpinBox_etlRightOffset.setValue.assert_called_with(2.5)
    assert acq.siggen.etl_right_amplitude == 1.0


def test_etl_sync_unchecked_is_noop_on_siggen() -> None:
    acq, _shell = _make_acq()
    acq.siggen.etl_right_amplitude = 0.0
    acq.updateUi_etl_sync()
    assert acq.siggen.etl_right_amplitude == 0.0


def test_etl_steps_propagates_to_siggen_as_int() -> None:
    acq, _shell = _make_acq()
    acq.updateUi_etl_steps()
    assert acq.siggen.etl_steps == 5
    assert isinstance(acq.siggen.etl_steps, int)


def test_etl_activate_propagates_to_siggen() -> None:
    acq, shell = _make_acq()
    shell.scan_panel.ui.checkBox_etlActivate.isChecked.return_value = True
    acq.updateUi_etl_activate()
    assert acq.siggen.etl_activated is True


# -- Camera shutter mode + setting slots ------------------------------------


def test_camera_shutter_mode_rolling_enables_exposure_disables_lightsheet_widgets() -> (
    None
):
    acq, shell = _make_acq()
    shutter = shell.acquisition_panel.ui.comboBox_cameraShutterMode
    shutter.currentText.return_value = "Rolling"
    acq.updateUi_camera_shutter_mode()
    assert acq.camera.shutter_mode == "Rolling"
    exposure = shell.acquisition_panel.ui.doubleSpinBox_cameraExposureTime
    exposure.setEnabled.assert_any_call(True)
    line_time = shell.acquisition_panel.ui.doubleSpinBox_cameraLineTime
    line_time.setEnabled.assert_any_call(False)


def test_camera_shutter_mode_lightsheet_enables_lightsheet_widgets() -> None:
    acq, shell = _make_acq()
    shutter = shell.acquisition_panel.ui.comboBox_cameraShutterMode
    shutter.currentText.return_value = "Lightsheet"
    acq.updateUi_camera_shutter_mode()
    assert acq.camera.shutter_mode == "Lightsheet"
    line_time = shell.acquisition_panel.ui.doubleSpinBox_cameraLineTime
    line_time.setEnabled.assert_any_call(True)
    exposure = shell.acquisition_panel.ui.doubleSpinBox_cameraExposureTime
    exposure.setEnabled.assert_any_call(False)


def test_camera_shutter_mode_else_branch_enables_exposure_only() -> None:
    """The else branch (e.g. 'Global') enables exposure + disables the
    lightsheet-specific widgets."""
    acq, shell = _make_acq()
    shutter = shell.acquisition_panel.ui.comboBox_cameraShutterMode
    shutter.currentText.return_value = "Global"
    acq.updateUi_camera_shutter_mode()
    assert acq.camera.shutter_mode == "Global"
    exposure = shell.acquisition_panel.ui.doubleSpinBox_cameraExposureTime
    exposure.setEnabled.assert_any_call(True)
    line_time = shell.acquisition_panel.ui.doubleSpinBox_cameraLineTime
    line_time.setEnabled.assert_any_call(False)


def test_camera_exposure_time_converts_ms_to_seconds() -> None:
    acq, _shell = _make_acq()
    acq.updateUi_camera_exposure_time()
    assert acq.camera.exposure_time == pytest.approx(0.1)


def test_camera_line_time_converts_us_to_seconds() -> None:
    acq, _shell = _make_acq()
    acq.updateUi_camera_line_time()
    assert acq.camera.lightsheet_line_time == pytest.approx(48.8e-6)


def test_camera_exposed_lines_propagates_as_int() -> None:
    acq, _shell = _make_acq()
    acq.updateUi_camera_exposed_lines()
    assert acq.camera.lightsheet_exposed_lines == 16


def test_camera_delay_lines_propagates_as_int() -> None:
    acq, _shell = _make_acq()
    acq.updateUi_camera_delay_lines()
    assert acq.camera.lightsheet_delay_lines == 0
