"""
Regression tests for the signal-lambda reference-cycle break.

The ~39 ``lambda: self._mc.<slot>()`` / ``lambda: self._acq.<slot>()``
signal connections in ``Controller_MainWindow.__init__`` each created a
reference cycle (controller → child widget → signal → lambda → closure
cell → controller). They are replaced with bare bound-method connections
in a new ``wire_collaborators()`` method, called by the composition root
after the collaborators are assigned.

These tests verify:
  1. No ``lambda: self._`` connection pattern remains in ``__init__``
     (source introspection — a secondary check paired with the primary
     behavior assertion below, per AGENTS.md §5's warning against
     grep-only tests).
  2. A converted bound-method connection actually fires the collaborator
     slot when the widget signal is emitted — proving the connection
     resolves and functions post-``wire_collaborators()`` (a behavior
     assertion, not just introspection).
"""

import inspect

from _helpers.controller_fixture import make_controller


def test_init_has_no_lambda_collaborator_connections() -> None:
    """``Controller_MainWindow.__init__`` source contains no
    ``lambda: self._`` pattern in its ``.connect(`` calls — the
    collaborator-delegating lambdas have been moved to
    ``wire_collaborators()`` as bare bound-method connections."""
    import lightsheet.gui.controller as controller_mod

    init_source = inspect.getsource(controller_mod.Controller_MainWindow.__init__)
    # The lambda-collaborator pattern must not appear in __init__.
    assert "lambda: self._mc." not in init_source
    assert "lambda: self._acq." not in init_source


def test_wire_collaborators_exists() -> None:
    """``Controller_MainWindow`` has a ``wire_collaborators`` method."""
    import lightsheet.gui.controller as controller_mod

    assert hasattr(controller_mod.Controller_MainWindow, "wire_collaborators")
    assert callable(
        getattr(controller_mod.Controller_MainWindow, "wire_collaborators")
    )


def test_converted_connection_fires_collaborator_slot(qtbot, request) -> None:
    """A converted bound-method connection (pushButton_sampleStepUp →
    self._mc.updateUi_move_sample_up) actually fires the MotorController
    slot when the button is clicked — proving the bound-method connection
    resolves and functions post-wire_collaborators().

    This is a behavior assertion, not just introspection: the real
    controller is constructed via make_controller (which calls
    wire_collaborators()), the button is clicked via qtbot.mouseClick,
    and the MotorController slot's side effect (a status message via
    updateUi_message_printer) is observed in the message log.
    """
    from PyQt5.QtCore import Qt

    ctrl, _ = make_controller(qtbot, request)

    # Clear any existing messages from hardware_init.
    ctrl.ui.plainTextEdit_messageLog.clear()

    # Click the sample step-up button — wired via wire_collaborators()
    # to self._mc.updateUi_move_sample_up (a bare bound method, no lambda).
    qtbot.mouseClick(ctrl.ui.pushButton_sampleStepUp, Qt.LeftButton)

    # updateUi_move_sample_up always calls updateUi_message_printer with
    # either "Sample stepping up" (move succeeded) or "Out of boundaries"
    # (move rejected by travel-limit guard) — either proves the
    # MotorController slot ran via the bound-method connection.
    log_text = ctrl.ui.plainTextEdit_messageLog.toPlainText()
    assert "Sample stepping up" in log_text or "Out of boundaries" in log_text


def test_converted_acq_connection_fires_collaborator_slot(qtbot, request) -> None:
    """A converted AcquisitionCoordinator bound-method connection
    (doubleSpinBox_etlLeftAmplitude valueChanged →
    self._acq.updateUi_etl_left_amplitude) fires the coordinator slot
    when the spinbox value changes — proving the _acq bound-method
    connections also resolve and function post-wire_collaborators()."""
    ctrl, _ = make_controller(qtbot, request)

    # The updateUi_etl_left_amplitude slot writes to self.siggen.etl_left_amplitude.
    # Record the value before, change the spinbox, and confirm the HAL attr changed.
    siggen = ctrl.siggen
    before = siggen.etl_left_amplitude

    # Set a new value on the spinbox — wired via wire_collaborators() to
    # self._acq.updateUi_etl_left_amplitude (bare bound method).
    new_val = ctrl.ui.doubleSpinBox_etlLeftAmplitude.value() + 0.1
    ctrl.ui.doubleSpinBox_etlLeftAmplitude.setValue(new_val)

    after = siggen.etl_left_amplitude
    assert after != before, (
        "updateUi_etl_left_amplitude did not fire — the bound-method "
        "connection to self._acq is not functioning"
    )
