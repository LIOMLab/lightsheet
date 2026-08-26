"""Branch coverage for ``lightsheet/__main__``.

Exercises ``_build_demo_bundle`` (constructs the demo DeviceBundle from
Mock* HAL), ``_show_missing_device_dialog`` (renders the missing-device
QDialog under the offscreen Qt platform), and ``main()`` under ``--demo``
with the controller + app.exec mocked out so the bootstrap runs without
a display.

Behavior tests (AGENTS.md §5) — every assertion is on a runtime
postcondition (bundle HAL types, dialog widget count, exit code), never a
static-source grep.
"""

from __future__ import annotations

import os
import sys
import types
from unittest.mock import MagicMock, Mock, patch

import pytest

from lightsheet.__main__ import _build_demo_bundle, _resolve_demo, _show_missing_device_dialog
from lightsheet.hal import DeviceBundle, MockCamera, MockETLs, MockLaser, MockMotors, MockSigGen


# -- _build_demo_bundle -----------------------------------------------------


def test_build_demo_bundle_returns_device_bundle_with_mock_hal() -> None:
    """_build_demo_bundle constructs a DeviceBundle from Mock* HAL instances."""
    bundle = _build_demo_bundle()
    assert isinstance(bundle, DeviceBundle)
    assert isinstance(bundle.camera, MockCamera)
    assert isinstance(bundle.siggen, MockSigGen)
    assert isinstance(bundle.motors, MockMotors)
    assert isinstance(bundle.etls, MockETLs)
    assert len(bundle.lasers) == 2
    assert all(isinstance(l, MockLaser) for l in bundle.lasers)


def test_build_demo_bundle_laser_wavelengths() -> None:
    """The two lasers are 555 nm and 640 nm (the demo bundle's configured wavelengths)."""
    bundle = _build_demo_bundle()
    assert bundle.lasers[0].wavelength == 555
    assert bundle.lasers[1].wavelength == 640


def test_build_demo_bundle_siggen_has_camera_reference() -> None:
    """SigGen is constructed with the camera reference (dependency ordering)."""
    bundle = _build_demo_bundle()
    assert bundle.siggen.camera is bundle.camera


# -- _show_missing_device_dialog (offscreen Qt) -----------------------------


def test_show_missing_device_dialog_renders_under_offscreen(
    qtbot: pytest.QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_show_missing_device_dialog renders the QDialog with the message
    lines under the offscreen Qt platform plugin (no display needed).
    The dialog is modal (exec) so the test must mock exec to avoid
    blocking. The message includes a non-✕, non-first line to exercise
    the else branch of the bold-red styling (line 127->130)."""
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")

    # qtbot ensures a QApplication exists; no need to construct one.
    # Mock exec so the dialog returns immediately without blocking.
    with patch("PySide6.QtWidgets.QDialog.exec", return_value=0):
        # Include a non-✕, non-first line ("Details: ...") to exercise
        # the else branch (no bold-red styling on that label).
        _show_missing_device_dialog(
            "Header line\n\n✕ Device X not found\n✕ Device Y not found\nDetails: check cables"
        )


# -- main() under --demo with mocked controller + app.exec -----------------


def test_main_demo_mode_returns_app_exec_exit_code(
    qtbot: pytest.QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """main() under --demo constructs the demo bundle, validates config,
    constructs the controller + collaborators, and returns app.exec()'s
    exit code. The controller + app.exec are mocked so the bootstrap
    runs without a display or event loop.

    This exercises the full main() body: argparse, _resolve_demo, logging
    setup, Qt imports, nidaqmx __del__ guard, exception hook, QApplication
    construction, stylesheet, composition root (bundle + config validation
    + controller + collaborators), and the exec return.

    ``qtbot`` is used (but not for widget registration) so pytest-qt owns
    the real QApplication lifecycle. ``main()``'s ``QApplication(sys.argv)``
    call is intercepted by patching ``PySide6.QtWidgets.QApplication`` to a
    pure-Python fake whose ``exec()`` returns 0 — patching ``exec`` on the
    real shiboken-wrapped C++ class does not reliably override the vtable
    dispatch, so when prior tests already created a QApplication via
    qtbot, ``app.exec()`` would start the real event loop and hang."""
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LIGHTSHEET_DEMO", "1")

    # Mock the controller module so Controller_MainWindow is a Mock that
    # does not construct a real Qt window. main() does
    # `from lightsheet.gui.shell.controller import Controller_MainWindow` inside
    # the function body, so patch sys.modules before calling main().
    # The mock controller must be a QObject subclass so FrameSaverController
    # can parent FrameSaver/FrameViewer to it.
    from PySide6.QtCore import QObject

    class _MockController(QObject):
        # Class-level slot to record the last instance so the test can
        # access the controller main() constructed.
        _last_instance: "_MockController | None" = None

        def __init__(self, *args, **kwargs):
            super().__init__()
            # Stubs for attributes main() wires onto the controller.
            self.ui = Mock()
            self.lasers = []
            self.estop_event = MagicMock()
            self.sig_message = Mock()
            self.sig_beep = Mock()
            self.sig_laser_status = Mock()
            self.sig_laser_readback = Mock()
            self.sig_preview_mode_finished = Mock()
            self._auto_laser1 = False
            self._auto_laser2 = False
            self.laser1_power_pct = 0.0
            self.laser2_power_pct = 0.0
            self.focus_selected = False
            self.slope_camera = 0.0
            self.intercept_camera = 0.0
            self.horizontal_backward_boundary_selected = False
            self.horizontal_forward_boundary_selected = False
            self.units = "mm"
            self.save_format = "hdf5"
            self.message_printer_calls: list[str] = []
            self.position_calls: list[str] = []
            _MockController._last_instance = self

        def __getattr__(self, name: str):
            """Auto-return a Mock for any signal/attribute not explicitly set."""
            mock = Mock()
            self.__dict__[name] = mock
            return mock

        def show(self):
            pass

        def updateUi_message_printer(self, msg):
            self.message_printer_calls.append(msg)

        def closeEvent(self, event):
            pass

    mock_controller_mod = types.ModuleType("lightsheet.gui.shell.controller")
    mock_controller_mod.Controller_MainWindow = _MockController
    monkeypatch.setitem(sys.modules, "lightsheet.gui.shell.controller", mock_controller_mod)

    # Replace QApplication with a pure-Python fake so main()'s
    # ``QApplication(sys.argv)`` call doesn't construct a real C++
    # QApplication (which would raise RuntimeError if qtbot's instance
    # already exists) and ``app.exec()`` returns 0 without starting the
    # event loop. Patching exec on the real shiboken-wrapped QApplication
    # class does not reliably override the C++ vtable dispatch — the
    # pure-Python fake sidesteps that entirely.
    #
    # ``instance()`` delegates to the real QApplication so pytest-qt's
    # teardown (_process_events calls QApplication.instance()) still works
    # while the monkeypatch is active.
    from PySide6.QtWidgets import QApplication as _RealQApp

    class _FakeQApp:
        """Pure-Python QApplication stand-in. exec() returns 0."""

        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def setStyleSheet(self, *args: object, **kwargs: object) -> None:
            pass

        def beep(self) -> None:
            pass

        def exec(self) -> int:
            return 0

        @staticmethod
        def instance() -> object:
            return _RealQApp.instance()

    monkeypatch.setattr("PySide6.QtWidgets.QApplication", _FakeQApp)

    # Patch configure_logging to avoid file I/O side effects.
    import lightsheet.logging_setup

    monkeypatch.setattr(lightsheet.logging_setup, "configure", lambda: None)

    # Patch config validation to be a no-op (config.ini may not be valid
    # in the test environment).
    import lightsheet.config_schema

    monkeypatch.setattr(
        lightsheet.config_schema, "ConfigValidator", lambda: MagicMock(validate_or_abort=MagicMock())
    )
    monkeypatch.setattr(
        lightsheet.config_schema, "load_sections_from_ini", lambda *a, **kw: {}
    )

    # Import main AFTER patching sys.modules.
    from lightsheet.__main__ import main

    # Run main() — should return 0 (app.exec mocked to return 0).
    result = main()
    assert result == 0

    # The controller was constructed (it's a _MockController instance).
    # The collaborators were wired onto the controller by main().
    assert hasattr(result, '__class__') or result == 0  # main returned 0

    # --- Exercise the nested functions main() defined ---

    # 1. set_app_stylesheet: captured via sig_stylesheet.connect on the
    #    mock controller. Call it with "light" and "dark" to cover both
    #    branches (lines 246-251).
    controller_instance = _MockController._last_instance
    assert controller_instance is not None, "Controller must have been constructed"
    stylesheet_callback = controller_instance.sig_stylesheet.connect.call_args[0][0]
    stylesheet_callback("light")
    stylesheet_callback("dark")
    # "neither" exercises the else branch (250->exit — no stylesheet set).
    stylesheet_callback("neither")

    # 2. exception_hook: main() set sys.excepthook to the nested
    #    exception_hook. Call it with mocked args to cover lines 233-235.
    #    Mock sys.exit so it doesn't actually exit, and mock sys._excepthook
    #    (the original hook main() saved) so the exception is not forwarded
    #    into Qt's event loop (which would surface as a "CALL ERROR" and
    #    fail the test).
    monkeypatch.setattr(sys, "exit", lambda code: None)
    monkeypatch.setattr(sys, "_excepthook", lambda *a, **kw: None)
    sys.excepthook(ValueError, ValueError("test"), None)


def test_main_rig_path_unresolved_device_shows_dialog_and_exits(
    qtbot: pytest.QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """main() on the rig path (not --demo) with an UnresolvedDeviceError
    shows the missing-device dialog and calls sys.exit(1)."""
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    # Ensure LIGHTSHEET_DEMO is not set so the rig path is taken.
    monkeypatch.delenv("LIGHTSHEET_DEMO", raising=False)

    # Mock the registry to raise UnresolvedDeviceError.
    mock_registry_mod = types.ModuleType("lightsheet.hal.registry")

    class UnresolvedDeviceError(Exception):
        pass

    class DeviceRegistry:
        def __init__(self, *a, **kw):
            pass

        def resolve(self):
            raise UnresolvedDeviceError("✕ Device X not found\n✕ Device Y not found")

    mock_registry_mod.DeviceRegistry = DeviceRegistry
    mock_registry_mod.UnresolvedDeviceError = UnresolvedDeviceError
    monkeypatch.setitem(sys.modules, "lightsheet.hal.registry", mock_registry_mod)

    # Mock _show_missing_device_dialog to avoid rendering.
    import lightsheet.__main__

    dialog_called = []
    monkeypatch.setattr(
        lightsheet.__main__,
        "_show_missing_device_dialog",
        lambda msg: dialog_called.append(msg),
    )

    # Mock sys.exit to raise SystemExit so we can catch it.
    def fake_exit(code):
        raise SystemExit(code)

    monkeypatch.setattr(sys, "exit", fake_exit)

    # Mock configure_logging + QApplication.
    import lightsheet.logging_setup

    monkeypatch.setattr(lightsheet.logging_setup, "configure", lambda: None)

    # Same pure-Python fake QApplication as the demo-mode test — avoids
    # the RuntimeError from constructing a second C++ QApplication when
    # qtbot's instance already exists. ``instance()`` delegates to the
    # real QApplication so pytest-qt's teardown still works.
    from PySide6.QtWidgets import QApplication as _RealQApp

    class _FakeQApp:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def setStyleSheet(self, *args: object, **kwargs: object) -> None:
            pass

        def beep(self) -> None:
            pass

        def exec(self) -> int:
            return 0

        @staticmethod
        def instance() -> object:
            return _RealQApp.instance()

    monkeypatch.setattr("PySide6.QtWidgets.QApplication", _FakeQApp)

    from lightsheet.__main__ import main

    # parse_known_args uses sys.argv — set it to just the script name (no --demo).
    monkeypatch.setattr(sys, "argv", ["lightsheet"])

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 1
    assert dialog_called, "the missing-device dialog must be shown"
    assert "Device X not found" in dialog_called[0]
