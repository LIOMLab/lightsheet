"""Lightsheet microscope controller — application entry point.

Exposes ``main()`` so the package can be launched via the ``lightsheet``
console script (``[project.scripts] lightsheet = lightsheet.__main__:main``)
or as a debug fallback with ``python -m lightsheet``.

The bootstrap body is relocated verbatim from the legacy ``main/main.py``;
the only structural change is wrapping it in ``main()`` so the QApplication
and controller live as function locals rather than module globals, and
``set_app_stylesheet`` becomes a closure over the local ``app``.
"""

import argparse
import logging
import os
import sys
import warnings

logger = logging.getLogger(__name__)


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
        ),
        MockLaser(
            wavelength=640,
            max_power_mw=150.0,
            label="Laser 2 (640 nm)",
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
    from PyQt5.QtWidgets import (
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
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        label = QLabel(line)
        label.setWordWrap(True)
        # The first non-empty line is the header — render it bold red.
        if i == 0 or line.startswith("✕"):
            label.setStyleSheet("color: #FF3B30; font-weight: bold;")
        layout.addWidget(label)

    btn_layout = QHBoxLayout()
    btn_layout.addStretch()
    exit_btn = QPushButton("Exit")
    exit_btn.setDefault(True)
    exit_btn.clicked.connect(dlg.accept)
    btn_layout.addWidget(exit_btn)
    layout.addLayout(btn_layout)

    dlg.setModal(True)
    dlg.exec_()


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

    # Preload the NI-DAQmx C library before any PyQt5 import. PyQt5 (and
    # qdarkstyle) load Qt DLLs that corrupt the NI-DAQmx driver's internal
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

    # PyQt5 / controller / qdarkstyle imports are deferred to inside main()
    # so the nicaiu preload above runs first. ruff's E402 (module-level
    # import-not-at-top) is suppressed for this file via per-file-ignores.
    import qdarkstyle
    from PyQt5.QtCore import pyqtSlot
    from PyQt5.QtWidgets import QApplication
    from qdarkstyle.dark.palette import DarkPalette
    from qdarkstyle.light.palette import LightPalette

    from lightsheet.gui.controller import Controller_MainWindow

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

    # This block permits messages display of errors occurring in all the files
    sys._excepthook = sys.excepthook

    def exception_hook(exctype: type, value: BaseException, traceback: object) -> None:
        """Permits messages display of errors occurring in all the files."""
        print(exctype, value, traceback)
        sys._excepthook(exctype, value, traceback)
        sys.exit(1)

    sys.excepthook = exception_hook

    # Initializing the app, controller (class which connects GUI to features)
    app = QApplication(sys.argv)
    app.setStyleSheet(qdarkstyle.load_stylesheet(qt_api="pyqt5", palette=LightPalette))

    @pyqtSlot(str)
    def set_app_stylesheet(stylesheet_code: str) -> None:
        """Function that allows stylesheet selection for the app."""
        if stylesheet_code == "light":
            app.setStyleSheet(
                qdarkstyle.load_stylesheet(qt_api="pyqt5", palette=LightPalette)
            )
        elif stylesheet_code == "dark":
            app.setStyleSheet(
                qdarkstyle.load_stylesheet(qt_api="pyqt5", palette=DarkPalette)
            )

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
    from lightsheet.gui.acquisition_coordinator import AcquisitionCoordinator
    from lightsheet.gui.frame_saver_controller import FrameSaverController
    from lightsheet.gui.hardware_manager import HardwareManager

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
    controller.sig_beep.connect(app.beep)  # connection for beep sounds
    controller.sig_stylesheet.connect(set_app_stylesheet)  # stylesheet selection

    # Show controller UI and execute main event loop
    controller.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
