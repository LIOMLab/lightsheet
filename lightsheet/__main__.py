"""Lightsheet microscope controller — application entry point.

Exposes ``main()`` so the package can be launched via the ``lightsheet``
console script (``[project.scripts] lightsheet = lightsheet.__main__:main``)
or as a debug fallback with ``python -m lightsheet``.

The bootstrap body is relocated verbatim from the legacy ``main/main.py``;
the only structural change is wrapping it in ``main()`` so the QApplication
and controller live as function locals rather than module globals. The
theme helpers (``_load_breeze_stylesheet``, ``_system_theme``,
``_resolve_theme``, ``set_app_stylesheet``) are module-level so they are
unit-testable without constructing the full ``Controller_MainWindow`` and
so the controller's ``sig_stylesheet`` signal can connect to
``set_app_stylesheet`` directly.
"""

import argparse
import logging
import os
import sys
import warnings
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Theme helpers — BreezeStyleSheets (vendored) + Qt6 system-default detection.
#
# BreezeStyleSheets is NOT on PyPI; the source is vendored under
# lightsheet/gui/_vendor/breezestylesheets/ and compiled into
# lightsheet/gui/breeze_pyside6.py via scripts/build-breeze.sh (pyside6-rcc).
# Importing the compiled module registers the Qt resource tree
# (:/light/stylesheet.qss, :/dark/stylesheet.qss) so the stylesheets load via
# QFile at runtime. The compiled resource is committed (same pattern as the
# ui_*_rc.py files) so the rig needs no configure.py run.
#
# These helpers are module-level (not the closure form) so they are unit-
# testable without constructing the full Controller_MainWindow.
# ---------------------------------------------------------------------------


def _load_breeze_stylesheet(theme: str) -> str:
    """Load the Breeze .qss for the given theme code ("light" or "dark")
    from the compiled Qt resource.

    The compiled resource (lightsheet/gui/breeze_pyside6.py) registers the
    stylesheets under ``:/<theme>/stylesheet.qss``. Returns the stylesheet
    text. Raises FileNotFoundError if the resource path is absent (a build
    or import failure).
    """
    # Importing the compiled module registers the resource tree. Deferred so
    # the module stays import-light on paths that never load a stylesheet.
    from lightsheet.gui import breeze_pyside6  # noqa: F401  # side effect: qRegisterResourceData
    from PySide6.QtCore import QFile, QIODevice

    path = f":/{theme}/stylesheet.qss"
    f = QFile(path)
    if not f.open(QIODevice.OpenModeFlag.ReadOnly | QIODevice.OpenModeFlag.Text):
        raise FileNotFoundError(
            f"Breeze stylesheet resource not found: {path} "
            f"(open error: {f.errorString()})"
        )
    return bytes(f.readAll()).decode("utf-8")


def _color_scheme_to_theme(scheme: "object") -> str:
    """Map a ``Qt.ColorScheme`` value to a Breeze theme code.

    - ``Qt.ColorScheme.Light`` -> "light"
    - ``Qt.ColorScheme.Dark`` -> "dark"
    - ``Qt.ColorScheme.Unknown`` (or anything else) -> "dark" (the fallback
      — a dark microscope-room GUI is the safer default for an operator
      working in a dim environment).

    Pure function over the scheme value so it is unit-testable without
    relying on the platform honoring ``setColorScheme`` (the offscreen
    platform on macOS always reports Unknown).
    """
    from PySide6.QtCore import Qt

    if scheme == Qt.ColorScheme.Light:
        return "light"
    # Dark or Unknown -> dark (the fallback for Unknown).
    return "dark"


def _system_theme() -> str:
    """Resolve the OS light/dark preference via Qt6
    ``QGuiApplication.styleHints().colorScheme()`` (available since Qt 6.5).

    Returns "dark" for Dark, "light" for Light, and "dark" for Unknown (the
    fallback — a dark microscope-room GUI is the safer default for an
    operator working in a dim environment).
    """
    from PySide6.QtGui import QGuiApplication

    scheme = QGuiApplication.styleHints().colorScheme()
    return _color_scheme_to_theme(scheme)


def _resolve_theme(cfg_theme: str) -> str:
    """Map the persisted ``[Controller] Theme`` config value to the theme
    code that ``set_app_stylesheet`` consumes.

    - "system" (or any unrecognized/empty value) -> resolved via
      ``_system_theme()`` against the current OS color scheme.
    - "light" / "dark" -> returned verbatim (explicit override).

    Defensive against malformed persisted values ("" or "purple"): an
    unrecognized value falls back to the system resolution rather than
    crashing. The config_schema Literal rejects "purple" at load time; this
    guard is a second line of defense for direct cfg_read callers.
    """
    if cfg_theme == "light" or cfg_theme == "dark":
        return cfg_theme
    # "system", "", None, or any unrecognized value -> system resolution.
    return _system_theme()


# Module-level holder for the persisted operator theme choice. The
# colorSchemeChanged handler reads this to decide whether to follow a
# mid-session OS theme switch (only when the choice is "system"). main()
# initializes it from config.ini at startup; set_app_stylesheet updates it
# on each call so the handler sees the latest operator choice.
_persisted_theme_holder: dict[str, str] = {"theme": "system"}


def _on_color_scheme_changed(app: "object") -> None:
    """colorSchemeChanged slot — re-resolve the theme only if the
    persisted operator choice is still "system". An explicit light/dark
    choice must hold across an OS theme switch.

    Module-level so set_app_stylesheet can connect it without nesting
    closures (and so tests can call set_app_stylesheet directly).
    """
    if _persisted_theme_holder["theme"] != "system":
        return
    resolved = _system_theme()
    app.setStyleSheet(_load_breeze_stylesheet(resolved))


def set_app_stylesheet(
    stylesheet_code: str,
    app: "Optional[object]" = None,
    persisted_theme: "Optional[str]" = None,
) -> None:
    """Apply the Breeze stylesheet for the chosen theme code.

    - "light" / "dark": load that Breeze sheet directly and disconnect the
      colorSchemeChanged follower (an explicit choice does not follow
      mid-session OS theme switches).
    - "system": resolve via QGuiApplication.styleHints().colorScheme() and
      connect colorSchemeChanged so a mid-session OS theme switch
      re-resolves only while the persisted choice stays "system".

    ``app`` defaults to QApplication.instance() (the production path and
    the test path both have a QApplication active). ``persisted_theme``
    defaults to the module-level holder's current value; passing it
    explicitly is how the controller's sig_stylesheet signal communicates
    the new operator choice on a menu click, and how tests pin the
    persisted choice without going through main().
    """
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication

    if app is None:
        app = QApplication.instance()
    if persisted_theme is None:
        # When called from the controller's sig_stylesheet signal (an
        # operator menu click), persisted_theme is not passed — the
        # stylesheet_code IS the new operator choice, so the holder must
        # track it. This is what makes an explicit light/dark menu choice
        # stop the colorSchemeChanged follower (the holder flips from
        # "system" to "light"/"dark"). Tests pass persisted_theme
        # explicitly to pin the choice independent of the signal.
        persisted_theme = stylesheet_code
    # Update the holder so the colorSchemeChanged handler sees the latest
    # operator choice.
    _persisted_theme_holder["theme"] = persisted_theme

    if stylesheet_code == "system":
        resolved = _system_theme()
        app.setStyleSheet(_load_breeze_stylesheet(resolved))
        # Follow mid-session OS theme changes — but only while the persisted
        # choice is still "system". The guard in _on_color_scheme_changed
        # prevents an explicit light/dark choice from being overridden.
        hints = QGuiApplication.styleHints()
        # Disconnect any prior follower so we never stack handlers across
        # repeated set_app_stylesheet calls. PySide6 emits a RuntimeWarning
        # (not an exception) when disconnecting a signal with no
        # connections, so suppress warnings around the call rather than
        # relying on a receivers() guard (SignalInstance has none).
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            try:
                hints.colorSchemeChanged.disconnect()
            except (RuntimeError, TypeError):
                pass  # no handler connected yet
        hints.colorSchemeChanged.connect(
            lambda _scheme: _on_color_scheme_changed(app)
        )
    else:
        # Explicit light/dark — load directly and stop following the OS.
        theme = stylesheet_code if stylesheet_code in ("light", "dark") else "dark"
        app.setStyleSheet(_load_breeze_stylesheet(theme))
        hints = QGuiApplication.styleHints()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            try:
                hints.colorSchemeChanged.disconnect()
            except (RuntimeError, TypeError):
                pass


def _resolve_demo(cli_demo: bool, env: str | None) -> bool:
    """Merge the ``--demo`` CLI flag and the ``LIGHTSHEET_DEMO`` env var into
    a single demo-mode boolean with CLI-overrides-env precedence.

    - ``--demo`` set -> demo active regardless of env.
    - ``LIGHTSHEET_DEMO=1`` -> demo active (env opt-in).
    - ``LIGHTSHEET_DEMO=0`` or unset -> demo inactive unless ``--demo``.

    Under demo mode ``main()``'s composition root builds a ``DeviceBundle``
    from ``Mock*`` HAL instances (no hardware init) and this bootstrap skips
    the ``nicaiu.dll`` preload (no DAQmx task is ever created in demo mode).
    """
    return bool(cli_demo or env == "1")


def _build_demo_bundle():
    """Construct a ``DeviceBundle`` from ``Mock*`` HAL instances for the
    ``--demo`` / ``LIGHTSHEET_DEMO=1`` path.

    Replicates the exact ``MockCamera`` / ``MockSigGen`` / ``MockMotors`` /
    ``MockLaser`` x2 / ``MockETLs`` construction that previously lived
    inline in ``Controller_MainWindow.hardware_init``'s demo branch. The
    camera-before-siggen dependency ordering is preserved (the mock camera
    still carries the xsize/ysize/line_time the SigGen waveform timing
    derives from).

    Imports are deferred to inside this function so the module stays
    import-light — the HAL barrel is not loaded until ``main()`` calls this
    on the demo path.
    """
    from lightsheet.hal import (
        DeviceBundle,
        MockCamera,
        MockETLs,
        MockLaser,
        MockMotors,
        MockSigGen,
    )

    camera = MockCamera(verbose=True)
    # Demo-mode timing observability: simulate the real camera's
    # exposure-time delay in monitor_recorder so the operator sees the
    # L1->L2 per-plane cycle at a realistic pace during demo UAT
    # (without this the mock completes instantly and the per-plane
    # sequencing is unobservable). MockCamera is never used on the
    # real rig, so this delay never reaches safety-critical code. This
    # is the ONLY place simulate_timing is set to True — the test
    # fixture (make_bundle) does not set it, keeping the suite fast.
    camera.simulate_timing = True
    # SigGen needs to know about Camera settings to generate proper scan
    # waveforms — dependency ordering preserved (the mock camera still
    # carries the xsize/ysize/line_time the SigGen waveform timing derives
    # from).
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
    """Show the missing-device strict-abort QDialog (D-02 / RFR-02).

    The ``UnresolvedDeviceError`` message already contains the full dialog
    body (header + intro + per-device entries, formatted per the UI-SPEC
    copy template). This function splits it into lines and renders each as
    a QLabel in a modal QDialog with a single Exit button. The
    QApplication must already exist so the dialog can render.
    """
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
        # The first non-empty line is the header — render it bold red.
        # Track the first rendered line separately rather than relying on
        # the enumerate index, because message.split("\n")[0] may be an
        # empty line that is skipped above (leaving the first non-empty
        # line at index > 0, which would miss the bold-red styling if we
        # checked `i == 0`).
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
    # Parse --demo and read LIGHTSHEET_DEMO=1 before any hardware preload.
    # CLI flag overrides env var (D-10): --demo forces demo mode even if
    # LIGHTSHEET_DEMO is unset or "0"; without --demo, LIGHTSHEET_DEMO=1
    # opts in. One read site for the demo flag.
    parser = argparse.ArgumentParser(description="Lightsheet microscope controller")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="run with mock HAL (no hardware init); overrides LIGHTSHEET_DEMO",
    )
    args, _ = parser.parse_known_args()
    demo = _resolve_demo(args.demo, os.environ.get("LIGHTSHEET_DEMO"))

    # Preload the NI-DAQmx C library before any PySide6/Qt6 import. PySide6
    # loads Qt DLLs that corrupt the NI-DAQmx driver's internal
    # state when loaded first — every subsequent nidaqmx.Task() call crashes
    # with "OSError: exception: access violation reading 0x0000000000000000"
    # inside DAQmxCreateTask. Preloading nicaiu.dll maps the driver into the
    # process before Qt's DLLs load, so the driver initializes correctly.
    # This is a Windows-only DLL-conflict workaround; on macOS ctypes has no
    # WinDLL attribute and the stub nidaqmx is used instead, so the preload
    # is guarded to win32 only. Skipped under demo mode — no DAQmx task is
    # ever created in demo mode, so the preload is unnecessary and a demo
    # session on the rig cannot accidentally energize hardware via a stale
    # DAQ task.
    if sys.platform == "win32" and not demo:
        try:
            import ctypes

            ctypes.WinDLL("nicaiu.dll")
        except (OSError, FileNotFoundError, ImportError):
            pass

    # Configure the root logger before any hardware init and before the GUI
    # starts: a RotatingFileHandler (5 MB x 5) + StreamHandler with the
    # mesoSPIM timestamped format, driven by the [Logging] section of
    # config.ini. Replaces the bare one-shot logging setup that used to live
    # here. Must run after the nicaiu preload above and before the first Qt
    # import below.
    from lightsheet.logging_setup import configure as configure_logging

    configure_logging()

    # PySide6 / controller imports are deferred to inside main() so the
    # nicaiu preload above runs first. ruff's E402 (module-level
    # import-not-at-top) is suppressed for this file via per-file-ignores.
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
        _original_excepthook(exctype, value, traceback)
        sys.exit(1)

    sys.excepthook = exception_hook

    # Initializing the app, controller (class which connects GUI to features)
    app = QApplication(sys.argv)

    # Read the persisted [Controller] Theme override (light/dark/system;
    # default system) and apply the Breeze stylesheet at startup. The
    # config_schema ControllerSettings.theme field validates the value at
    # the startup gate above; here cfg_read returns the raw string with the
    # "system" default for an absent key.
    cfg_theme = cfg_read(
        "config.ini", "Controller", {"Theme": "system"}
    )["Theme"]
    # Initialize the module-level persisted-theme holder so the
    # colorSchemeChanged handler (connected inside set_app_stylesheet)
    # can decide whether to follow a mid-session OS theme switch.
    _persisted_theme_holder["theme"] = cfg_theme
    # Apply the startup theme. set_app_stylesheet is module-level so the
    # controller's sig_stylesheet signal can connect to it directly and
    # the test suite can call it without constructing main().
    set_app_stylesheet(cfg_theme, app=app, persisted_theme=cfg_theme)

    # --- Composition root: build the DeviceBundle, validate config, then
    # construct the shell. main() is the SOLE composition root —
    # Controller_MainWindow receives a pre-built bundle and no longer
    # constructs HAL classes itself. The E-stop kill path stays in the
    # thin shell with a direct list[ILaser] ref (self.lasers =
    # list(bundle.lasers)), lock-free on the GUI thread.
    if demo:
        bundle = _build_demo_bundle()
    else:
        # DeviceRegistry is imported ONLY on the rig path (not-demo) —
        # never on the --demo path (Pitfall 6: an empty Mac USB-serial
        # port list would abort every device). The QApplication already
        # exists above so the missing-device QDialog can render.
        from lightsheet.hal.registry import (
            DeviceRegistry,
            UnresolvedDeviceError,
        )

        try:
            bundle = DeviceRegistry(
                "hardware_inventory.yaml", "config.ini"
            ).resolve()
        except UnresolvedDeviceError as e:
            _show_missing_device_dialog(str(e))
            sys.exit(1)

    # Config-schema validation runs AFTER the bundle exists but BEFORE
    # any collaborator/shell is constructed (UI-SPEC order-of-operations).
    # A REJECT-classified error aborts via sys.exit(1) inside
    # validate_or_abort before any Qt window shows. This runs on both
    # demo and rig paths — config validation is not a hardware carve-out.
    from lightsheet.config_schema import (
        ConfigValidator,
        load_sections_from_ini,
    )

    overlay_path = (
        "config.rig-specific.ini"
        if os.path.exists("config.rig-specific.ini")
        else None
    )
    ConfigValidator().validate_or_abort(
        load_sections_from_ini("config.ini", overlay_path)
    )

    # Construct the FrameSaverController + HardwareManager collaborators
    # before the shell's hardware_init runs. They own the FrameSaver/
    # FrameViewer QObjects (parented to the shell) and the laser
    # write/toggle/poll logic respectively. The shell delegates through
    # self._fs / self._hw. The shell is constructed first with fs/hw=None,
    # then the collaborators are wired and assigned on the shell before
    # the 100ms hardware_init timer fires — FrameSaver/FrameViewer need
    # the shell as their QObject parent, and the shell needs the
    # collaborators for hardware_init. A two-phase init avoids the
    # circular dependency (collaborators need shell as parent/ref, shell
    # needs collaborators for hardware_init).
    from lightsheet.gui.coordinators.acquisition_coordinator import AcquisitionCoordinator
    from lightsheet.gui.coordinators.frame_saver_controller import FrameSaverController
    from lightsheet.gui.coordinators.hardware_manager import HardwareManager
    from lightsheet.gui.coordinators.motor_controller import MotorController

    controller = Controller_MainWindow(bundle, demo=demo)
    fs = FrameSaverController(bundle, controller)
    controller._fs = fs
    hw = HardwareManager(bundle, controller)
    controller._hw = hw
    # AcquisitionCoordinator needs hw (for start_lasers/stop_lasers) and
    # the shell (for sig_message, estop_event, _fs, ui.* widgets) — built
    # last of the three collaborators, after hw and fs are wired onto the
    # shell.
    acq = AcquisitionCoordinator(bundle, hw, controller)
    controller._acq = acq
    # MotorController owns the motor-move + focus/interpolation-display
    # slots. Built after the shell so it can hold a shell reference; wired
    # before hardware_init's dependent timers/connections run so the
    # .clicked.connect(self._mc.<method>) call sites in __init__ resolve.
    mc = MotorController(bundle, controller)
    controller._mc = mc
    # Wire the collaborator-dependent signal connections (MotorController
    # / AcquisitionCoordinator delegates) as bare bound-method connections
    # — called after all four collaborators are assigned so the bound
    # methods resolve. Breaks the signal-lambda reference cycle at the
    # connection layer (PySide6 weakref-to-__self__ decomposition).
    controller.wire_collaborators()
    controller.sig_beep.connect(app.beep)  # connection for beep sounds
    controller.sig_stylesheet.connect(set_app_stylesheet)  # stylesheet selection

    # Show controller UI and execute main event loop
    controller.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
