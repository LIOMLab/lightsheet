"""Lightsheet microscope controller — application entry point.

Exposes ``main()`` so the package can be launched via the ``lightsheet``
console script (``[project.scripts] lightsheet = lightsheet.__main__:main``)
or as a debug fallback with ``python -m lightsheet``.

The bootstrap body is relocated verbatim from the legacy ``main/main.py``;
the only structural change is wrapping it in ``main()`` so the QApplication
and controller live as function locals rather than module globals, and
``set_app_stylesheet`` becomes a closure over the local ``app``.
"""

import logging
import sys
import warnings

logger = logging.getLogger(__name__)


def main() -> int:
    # Preload the NI-DAQmx C library before any PyQt5 import. PyQt5 (and
    # qdarkstyle) load Qt DLLs that corrupt the NI-DAQmx driver's internal
    # state when loaded first — every subsequent nidaqmx.Task() call crashes
    # with "OSError: exception: access violation reading 0x0000000000000000"
    # inside DAQmxCreateTask. Preloading nicaiu.dll maps the driver into the
    # process before Qt's DLLs load, so the driver initializes correctly.
    # This is a Windows-only DLL-conflict workaround; on macOS the ctypes
    # call fails silently and the stub nidaqmx is used instead.
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
    from PyQt5.QtCore import pyqtSlot
    from PyQt5.QtWidgets import QApplication
    from gui.controller import Controller_MainWindow

    import qdarkstyle
    from qdarkstyle.light.palette import LightPalette
    from qdarkstyle.dark.palette import DarkPalette

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
                    'Task "{}" was not explicitly closed and may still be '
                    "reserved.".format(saved_name),
                    DaqResourceWarning,
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
    app.setStyleSheet(
        qdarkstyle.load_stylesheet(qt_api="pyqt5", palette=LightPalette)
    )

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

    controller = Controller_MainWindow()
    controller.sig_beep.connect(app.beep)  # connection for beep sounds
    controller.sig_stylesheet.connect(set_app_stylesheet)  # stylesheet selection

    # Show controller UI and execute main event loop
    controller.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
