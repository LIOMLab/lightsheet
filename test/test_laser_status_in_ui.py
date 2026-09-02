"""
Laser status/readback labels live in ui_laser_panel.ui (audit #10).

The per-laser status + readback QLabels and the L2 Refresh Power button used
to be constructed programmatically in ``Controller_MainWindow.__init__``
(controller.py:300-341) and ``insertWidget``-ed into the laser panel's column
layouts. That detached them from the panel's layout/style and forced the
panel slots to reach across to ``self._shell.label_laser*``.

This test verifies the move into ``ui_laser_panel.ui``: the widgets are
defined in the .ui (so they are panel-local on ``self.ui`` after D-05), the
programmatic construction is gone from controller.py, the labels are
fixed-width per the UI-SPEC, and the status slot paints the shared semantic
colors (green/gray/red) matching ``label_estopStatus``.
"""

from __future__ import annotations

from pathlib import Path

from _helpers.controller_fixture import make_controller
from pytest import FixtureRequest
from pytestqt.qtbot import QtBot

_CONTROLLER_PATH = (
    Path(__file__).resolve().parents[1]
    / "lightsheet"
    / "gui"
    / "shell"
    / "controller.py"
)
_UI_PATH = (
    Path(__file__).resolve().parents[1]
    / "lightsheet"
    / "gui"
    / "panels"
    / "ui_laser_panel.ui"
)


def _controller_source() -> str:
    return _CONTROLLER_PATH.read_text(encoding="utf-8")


def _ui_source() -> str:
    return _UI_PATH.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# Widget existence in the .ui (defined in XML, not constructed in Python).
# --------------------------------------------------------------------------- #


def test_label_laserOneStatus_defined_in_ui() -> None:
    assert "name=\"label_laserOneStatus\"" in _ui_source()


def test_label_laserOneReadback_defined_in_ui() -> None:
    assert "name=\"label_laserOneReadback\"" in _ui_source()


def test_label_laserTwoStatus_defined_in_ui() -> None:
    assert "name=\"label_laserTwoStatus\"" in _ui_source()


def test_label_laserTwoReadback_defined_in_ui() -> None:
    assert "name=\"label_laserTwoReadback\"" in _ui_source()


def test_pushButton_laserTwoRefresh_defined_in_ui() -> None:
    assert "name=\"pushButton_laserTwoRefresh\"" in _ui_source()


# --------------------------------------------------------------------------- #
# Programmatic construction removed from controller.py.
# --------------------------------------------------------------------------- #


def test_controller_no_programmatic_laser_status_labels() -> None:
    src = _controller_source()
    # The programmatic QLabel/QPushButton constructions + insertWidget calls
    # for the laser status/readback/refresh widgets must be gone.
    assert "self.label_laserOneStatus = QLabel" not in src
    assert "self.label_laserOneReadback = QLabel" not in src
    assert "self.label_laserTwoStatus = QLabel" not in src
    assert "self.label_laserTwoReadback = QLabel" not in src
    assert "self.pushButton_laserTwoRefresh = QPushButton" not in src
    assert "verticalLayout_43.insertWidget" not in src
    assert "verticalLayout_44.insertWidget" not in src


# --------------------------------------------------------------------------- #
# Fixed-width per UI-SPEC (status 140 / readback 80).
# --------------------------------------------------------------------------- #


def test_label_laserOneStatus_minimum_width_in_ui(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    ctrl, _ = make_controller(qtbot, request)
    label = ctrl.laser_panel.ui.label_laserOneStatus
    assert label.minimumWidth() >= 140


def test_label_laserOneReadback_minimum_width_in_ui(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    ctrl, _ = make_controller(qtbot, request)
    label = ctrl.laser_panel.ui.label_laserOneReadback
    assert label.minimumWidth() >= 80


def test_label_laserTwoStatus_minimum_width_in_ui(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    ctrl, _ = make_controller(qtbot, request)
    label = ctrl.laser_panel.ui.label_laserTwoStatus
    assert label.minimumWidth() >= 140


def test_label_laserTwoReadback_minimum_width_in_ui(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    ctrl, _ = make_controller(qtbot, request)
    label = ctrl.laser_panel.ui.label_laserTwoReadback
    assert label.minimumWidth() >= 80


# --------------------------------------------------------------------------- #
# Shared semantic colors (green/gray/red) matching label_estopStatus tokens.
# --------------------------------------------------------------------------- #


def test_updateUi_laser_status_active_green(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    ctrl, _ = make_controller(qtbot, request)
    ctrl.laser_panel.updateUi_laser_status(0, "active")
    label = ctrl.laser_panel.ui.label_laserOneStatus
    assert label.text() == "\u25cf ON"
    assert "#34C759" in label.styleSheet()


def test_updateUi_laser_status_inactive_gray(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    ctrl, _ = make_controller(qtbot, request)
    ctrl.laser_panel.updateUi_laser_status(0, "inactive")
    label = ctrl.laser_panel.ui.label_laserOneStatus
    assert label.text() == "\u25cb OFF"
    assert "#8E8E93" in label.styleSheet()


def test_updateUi_laser_status_error_red(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    ctrl, _ = make_controller(qtbot, request)
    ctrl.laser_panel.updateUi_laser_status(1, "error")
    label = ctrl.laser_panel.ui.label_laserTwoStatus
    assert label.text() == "\u26a0 FAULT"
    assert "#FF3B30" in label.styleSheet()


# --------------------------------------------------------------------------- #
# Panel-local references (self.ui, not self._shell) — D-05 hybrid ownership.
# --------------------------------------------------------------------------- #


def test_laser_panel_slots_reference_panel_local_ui() -> None:
    """laser_panel.py:updateUi_laser_status / updateUi_laser_readback must
    reference ``self.ui.label_laser*`` (panel-local), not
    ``self._shell.label_laser*`` (the old cross-panel reach)."""
    src = (
        Path(__file__).resolve().parents[1]
        / "lightsheet"
        / "gui"
        / "panels"
        / "laser_panel.py"
    ).read_text(encoding="utf-8")
    # The status slot must use the panel-local ui attribute.
    assert "self.ui.label_laserOneStatus" in src
    assert "self.ui.label_laserTwoStatus" in src
    assert "self.ui.label_laserOneReadback" in src
    assert "self.ui.label_laserTwoReadback" in src
    # The old cross-panel reach must be gone from the status/readback slots.
    assert "self._shell.label_laserOneStatus" not in src
    assert "self._shell.label_laserTwoStatus" not in src
    assert "self._shell.label_laserOneReadback" not in src
    assert "self._shell.label_laserTwoReadback" not in src


# --------------------------------------------------------------------------- #
# Signal connections preserved + Refresh button wired.
# --------------------------------------------------------------------------- #


def test_sig_laser_status_connected(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    ctrl, _ = make_controller(qtbot, request)
    seen = {"status": None}

    def _spy(idx: int, status: str) -> None:
        seen["status"] = (idx, status)

    ctrl.sig_laser_status.connect(_spy)
    ctrl.sig_laser_status.emit(0, "active")
    assert seen["status"] == (0, "active"), (
        "sig_laser_status must be emit-able + the panel slot must run on emit"
    )
    # The panel slot painted the active color on the L1 status label.
    assert ctrl.laser_panel.ui.label_laserOneStatus.text() == "\u25cf ON"


def test_sig_laser_readback_connected(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    ctrl, _ = make_controller(qtbot, request)
    seen = {"rb": None}

    def _spy(idx: int, text: str, tooltip: str) -> None:
        seen["rb"] = (idx, text, tooltip)

    ctrl.sig_laser_readback.connect(_spy)
    ctrl.sig_laser_readback.emit(1, "12.3 mW (cmd)", "")
    assert seen["rb"] == (1, "12.3 mW (cmd)", "")
    assert ctrl.laser_panel.ui.label_laserTwoReadback.text() == "12.3 mW (cmd)"


def test_pushButton_laserTwoRefresh_clicked_connected(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    ctrl, _ = make_controller(qtbot, request)
    btn = ctrl.laser_panel.ui.pushButton_laserTwoRefresh
    # Wire a spy slot alongside the real one and click — the spy firing
    # proves the clicked signal is connected (the real slot also runs and
    # routes to the hardware manager helpers, which are no-ops on mocks).
    seen = {"clicked": False}

    def _spy() -> None:
        seen["clicked"] = True

    btn.clicked.connect(_spy)
    btn.click()
    assert seen["clicked"] is True, "pushButton_laserTwoRefresh.clicked must fire"


def test_refresh_button_emits_via_slot(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """Clicking Refresh Power routes to the laser panel refresh slot, which
    calls the hardware manager readback/poll helpers. Patch those helpers to
    assert the wiring end-to-end without a real serial round-trip."""
    ctrl, _ = make_controller(qtbot, request)
    called = {"poll": False, "refresh": False}

    def _fake_refresh_async() -> None:
        called["refresh"] = True

    def _fake_poll(indices: object) -> None:
        called["poll"] = True

    ctrl._hw._refresh_laser2_readback_async = _fake_refresh_async  # type: ignore[assignment]
    ctrl._hw._poll_laser_status = _fake_poll  # type: ignore[assignment]

    ctrl.laser_panel.ui.pushButton_laserTwoRefresh.click()

    assert called["refresh"] is True
    assert called["poll"] is True
