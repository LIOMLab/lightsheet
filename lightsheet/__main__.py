"""Lightsheet microscope controller -- application entry point."""

from __future__ import annotations

import argparse
import contextlib
import logging
import os
import sys
import warnings
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lightsheet.hal.bundle import DeviceBundle

logger = logging.getLogger(__name__)


# Theme helpers — BreezeStyleSheets (vendored) + Qt6 system-default detection.
# Module-level so they are unit-testable without Controller_MainWindow.


def _load_breeze_stylesheet(theme: str) -> str:
    """Load the Breeze .qss for the given theme code from the compiled Qt resource."""
    # Deferred import so the module stays import-light.
    from PySide6.QtCore import QFile, QIODevice

    from lightsheet.gui import (
        breeze_pyside6,  # noqa: F401  # side effect: qRegisterResourceData
    )

    path = f":/{theme}/stylesheet.qss"
    f = QFile(path)
    if not f.open(QIODevice.OpenModeFlag.ReadOnly | QIODevice.OpenModeFlag.Text):
        raise FileNotFoundError(
            f"Breeze stylesheet resource not found: {path} "
            f"(open error: {f.errorString()})"
        )
    return bytes(f.readAll()).decode("utf-8")  # ty: ignore[invalid-argument-type]


def _color_scheme_to_theme(scheme: object) -> str:
    """Map a ``Qt.ColorScheme`` value to a Breeze theme code ("light"/"dark")."""
    from PySide6.QtCore import Qt

    if scheme == Qt.ColorScheme.Light:
        return "light"
    # Dark or Unknown -> dark (safer default for a dim microscope room).
    return "dark"


def _system_theme() -> str:
    """Resolve the OS light/dark preference via Qt6
    ``QGuiApplication.styleHints().colorScheme()``."""
    from PySide6.QtGui import QGuiApplication

    scheme = QGuiApplication.styleHints().colorScheme()
    return _color_scheme_to_theme(scheme)


def _resolve_theme(cfg_theme: str) -> str:
    """Map the persisted ``[Controller] Theme`` config value to a theme
    code. Unrecognized values fall back to system resolution."""
    if cfg_theme == "light" or cfg_theme == "dark":
        return cfg_theme
    # "system", "", None, or any unrecognized value -> system resolution.
    return _system_theme()


# Holder for the persisted operator theme choice; read by the
# colorSchemeChanged handler.
_persisted_theme_holder: dict[str, str] = {"theme": "system"}


def _on_color_scheme_changed(app: object) -> None:
    """Re-resolve the theme only if the persisted choice is still "system"."""
    if _persisted_theme_holder["theme"] != "system":
        return
    resolved = _system_theme()
    app.setStyleSheet(_load_breeze_stylesheet(resolved))  # ty: ignore[unresolved-attribute]


def set_app_stylesheet(
    stylesheet_code: str,
    app: object | None = None,
    persisted_theme: str | None = None,
) -> None:
    """Apply the Breeze stylesheet for the chosen theme code
    ("light"/"dark"/"system")."""
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication

    if app is None:
        app = QApplication.instance()
    if persisted_theme is None:
        # Called from the controller's sig_stylesheet signal -- the code
        # IS the new choice.
        persisted_theme = stylesheet_code
    _persisted_theme_holder["theme"] = persisted_theme

    if stylesheet_code == "system":
        resolved = _system_theme()
        app.setStyleSheet(_load_breeze_stylesheet(resolved))  # ty: ignore[unresolved-attribute]
        # Follow mid-session OS theme changes only while persisted choice is "system".
        hints = QGuiApplication.styleHints()
        # Disconnect any prior follower to avoid stacking handlers.
        # PySide6 emits a RuntimeWarning (not an exception) when
        # disconnecting a signal with no connections.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            with contextlib.suppress(RuntimeError, TypeError):
                hints.colorSchemeChanged.disconnect()
        hints.colorSchemeChanged.connect(lambda _scheme: _on_color_scheme_changed(app))
    else:
        # Explicit light/dark — load directly and stop following the OS.
        theme = stylesheet_code if stylesheet_code in ("light", "dark") else "dark"
        app.setStyleSheet(_load_breeze_stylesheet(theme))  # ty: ignore[unresolved-attribute]
        hints = QGuiApplication.styleHints()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            with contextlib.suppress(RuntimeError, TypeError):
                hints.colorSchemeChanged.disconnect()


def _resolve_demo(cli_demo: bool, env: str | None) -> bool:
    """Merge the ``--demo`` CLI flag and ``LIGHTSHEET_DEMO`` env var.
    CLI overrides env."""
    return bool(cli_demo or env == "1")


def _build_demo_bundle() -> DeviceBundle:
    """Construct a ``DeviceBundle`` from ``Mock*`` HAL instances for demo mode."""
    from lightsheet.hal import (
        DeviceBundle,
        MockCamera,
        MockETLs,
        MockLaser,
        MockMotors,
        MockSigGen,
    )

    camera = MockCamera(verbose=True)
    # Simulate exposure-time delay so demo UAT shows realistic per-plane pacing.
    camera.simulate_timing = True
    # SigGen needs camera settings for waveform timing.
    siggen = MockSigGen(camera)
    motors = MockMotors()
    lasers = (
        MockLaser(
            wavelength=555,
            max_power_mw=300.0,
            mw_per_volt=60.0,
            label="Laser 1 (555 nm)",
            calibration_curve=None,
        ),
        MockLaser(
            wavelength=647,
            max_power_mw=150.0,
            label="Laser 2 (647 nm)",
        ),
    )
    etls = MockETLs()
    return DeviceBundle(
        camera=camera,
        siggen=siggen,
        motors=motors,
        etls=etls,
        lasers=lasers,
    )


def _show_missing_device_dialog(message: str) -> None:
    """Show the missing-device strict-abort QDialog."""
    from PySide6.QtWidgets import (
        QDialog,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QVBoxLayout,
    )

    dlg = QDialog()
    dlg.setWindowTitle("Missing device — startup aborted")
    dlg.setMinimumWidth(480)
    layout = QVBoxLayout(dlg)

    lines = message.split("\n")
    first_rendered = True
    for line in lines:
        if not line.strip():
            continue
        label = QLabel(line)
        label.setWordWrap(True)
        # First non-empty line is the header — render it bold red.
        if first_rendered or line.startswith("✕"):
            label.setStyleSheet("color: #FF3B30; font-weight: bold;")
            first_rendered = False
        layout.addWidget(label)

    btn_layout = QHBoxLayout()
    btn_layout.addStretch()
    exit_btn = QPushButton("Exit")
    exit_btn.setDefault(True)
    exit_btn.clicked.connect(dlg.accept)
    btn_layout.addWidget(exit_btn)
    layout.addLayout(btn_layout)

    dlg.setModal(True)
    dlg.exec()


def main() -> int:
    # Parse --demo / LIGHTSHEET_DEMO before any hardware preload.
    # CLI flag overrides env.
    parser = argparse.ArgumentParser(description="Lightsheet microscope controller")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="run with mock HAL (no hardware init); overrides LIGHTSHEET_DEMO",
    )
    args, _ = parser.parse_known_args()
    demo = _resolve_demo(args.demo, os.environ.get("LIGHTSHEET_DEMO"))

    # Preload nicaiu.dll before Qt DLLs load -- Qt corrupts the
    # NI-DAQmx driver's internal state if loaded first. Windows-only;
    # skipped in demo mode (no DAQmx task is ever created).
    if sys.platform == "win32" and not demo:
        try:
            import ctypes

            ctypes.WinDLL("nicaiu.dll")
        except (OSError, FileNotFoundError, ImportError):
            pass

    # Configure root logger before hardware init and Qt import.
    from lightsheet.logging_setup import configure as configure_logging

    configure_logging()

    # Deferred imports so the nicaiu preload above runs first.
    from PySide6.QtWidgets import QApplication

    from lightsheet.config import cfg_read
    from lightsheet.gui.shell.controller import Controller_MainWindow

    # Workaround for a nidaqmx 0.6.x Task.__del__ bug: after the context manager
    # closes a Task (close() -> clear()), the internal _saved_name attribute is
    # removed, but __del__ still runs during garbage collection and tries to
    # format a DaqResourceWarning using self._saved_name — raising AttributeError
    # ("Exception ignored in <function Task.__del__>"). The exception is swallowed
    # by Python (exceptions in __del__ are ignored) but printed to stderr, which
    # surfaces as confusing noise during safety-critical actions like E-stop.
    # Guard the attribute access so the resource-leak warning still fires for
    # genuinely unclosed tasks (where _saved_name survives) while silencing the
    # spurious AttributeError for properly-closed ones.
    try:
        import nidaqmx
        from nidaqmx.errors import DaqResourceWarning

        def _safe_task_del(self: object) -> None:
            saved_name = getattr(self, "_saved_name", None)
            if saved_name:
                warnings.warn(
                    f'Task "{saved_name}" was not explicitly closed and may still be '
                    "reserved.",
                    DaqResourceWarning,
                    stacklevel=2,
                )

        nidaqmx.Task.__del__ = _safe_task_del  # type: ignore[attr-defined]
    except Exception:
        # nidaqmx not installed (macOS dev path uses the conftest stub) — skip.
        pass

    # This block permits messages display of errors occurring in all the files.
    # Capture the original hook in a closure variable rather than on the sys
    # module — sys._excepthook is not a documented API and could be overwritten
    # by another library or reserved by a future CPython.
    _original_excepthook = sys.excepthook

    def exception_hook(exctype: type, value: BaseException, traceback: object) -> None:
        """Permits messages display of errors occurring in all the files."""
        print(exctype, value, traceback)
        _original_excepthook(exctype, value, traceback)  # ty: ignore[invalid-argument-type]
        sys.exit(1)

    sys.excepthook = exception_hook

    # Initializing the app, controller (class which connects GUI to features)
    app = QApplication(sys.argv)

    # Read the persisted [Controller] Theme override (light/dark/system;
    # default system) and apply the Breeze stylesheet at startup.
    cfg_theme = cfg_read("config.ini", "Controller", {"Theme": "system"})["Theme"]
    # Initialize the module-level persisted-theme holder so the
    # colorSchemeChanged handler (connected inside set_app_stylesheet)
    # can decide whether to follow a mid-session OS theme switch.
    _persisted_theme_holder["theme"] = cfg_theme
    # Apply the startup theme. set_app_stylesheet is module-level so the
    # controller's sig_stylesheet signal can connect to it directly and
    # the test suite can call it without constructing main().
    set_app_stylesheet(cfg_theme, app=app, persisted_theme=cfg_theme)

    # --- Composition root: build the DeviceBundle, validate config, then
    # construct the shell. The E-stop kill path stays in the thin shell
    # with a direct list[ILaser] ref, lock-free on the GUI thread.
    if demo:
        bundle = _build_demo_bundle()
    else:
        # DeviceRegistry is imported ONLY on the rig path (not-demo) —
        # never on the --demo path (an empty Mac USB-serial port list
        # would abort every device). The QApplication already exists
        # above so the missing-device QDialog can render.
        from lightsheet.hal.registry import (
            DeviceRegistry,
            UnresolvedDeviceError,
        )

        try:
            bundle = DeviceRegistry("hardware_inventory.yaml", "config.ini").resolve()
        except UnresolvedDeviceError as e:
            _show_missing_device_dialog(str(e))
            sys.exit(1)

    # Config-schema validation runs AFTER the bundle exists but BEFORE
    # any collaborator/shell is constructed. A REJECT-classified error
    # aborts via sys.exit(1) before any Qt window shows. Runs on both
    # demo and rig paths.
    from lightsheet.config_schema import (
        ConfigValidator,
        load_sections_from_ini,
    )

    overlay_path = (
        "config.rig-specific.ini"
        if Path("config.rig-specific.ini").exists()
        else None
    )
    ConfigValidator().validate_or_abort(
        load_sections_from_ini("config.ini", overlay_path)
    )

    # Construct the collaborators before the shell's hardware_init runs.
    # A two-phase init avoids the circular dependency (collaborators need
    # shell as parent/ref, shell needs collaborators for hardware_init).
    from lightsheet.gui.coordinators.acquisition_coordinator import (
        AcquisitionCoordinator,
    )
    from lightsheet.gui.coordinators.frame_saver_controller import FrameSaverController
    from lightsheet.gui.coordinators.hardware_manager import HardwareManager
    from lightsheet.gui.coordinators.motor_controller import MotorController

    controller = Controller_MainWindow(bundle, demo=demo)
    fs = FrameSaverController(bundle, controller)
    controller._fs = fs
    hw = HardwareManager(bundle, controller)
    controller._hw = hw
    # AcquisitionCoordinator needs hw and the shell — built last of the
    # three collaborators.
    acq = AcquisitionCoordinator(bundle, hw, controller)
    controller._acq = acq
    # MotorController owns the motor-move + focus/interpolation-display
    # slots. Built after the shell so it can hold a shell reference.
    mc = MotorController(bundle, controller)
    controller._mc = mc
    # Wire the collaborator-dependent signal connections as bare
    # bound-method connections — breaks the signal-lambda reference cycle
    # at the connection layer.
    controller.wire_collaborators()
    controller.sig_beep.connect(app.beep)  # connection for beep sounds
    controller.sig_stylesheet.connect(set_app_stylesheet)  # stylesheet selection

    # Show controller UI and execute main event loop
    controller.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
