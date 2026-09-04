"""Rig-only test: does PySide6 + nidaqmx interaction cause the access violation?

Every plain-Python repro passes. The GUI runs inside QApplication.exec()
with a 100ms QTimer and the laser toggle spawned from a Qt slot on a daemon
thread. This test mirrors that: constructs the full HAL inside a QApplication,
starts the event loop, and triggers a laser Task creation from a QTimer
slot (and from a daemon thread, as the GUI does).

Rig-only: skipped when the real nidaqmx driver is absent (Mac stub).
"""

import contextlib
import importlib.util
import os
import sys
import threading

import pytest


def _real_nidaqmx_available() -> bool:
    try:
        spec = importlib.util.find_spec("nidaqmx")
    except ValueError:
        return False
    if spec is None:
        return False
    try:
        import nidaqmx

        task = nidaqmx.Task()
        task.close()
        return True
    except Exception:
        return False


pytestmark = [
    pytest.mark.skipif(
        not _real_nidaqmx_available(),
        reason="rig-only: requires the real NI-DAQmx driver runtime",
    ),
    pytest.mark.xdist_group("rig_hardware"),
]


def _have_pyside6() -> bool:
    try:
        import PySide6  # noqa: F401

        return True
    except Exception:
        return False


def _laser_terminals() -> str:
    import configparser

    cfg = configparser.ConfigParser()
    cfg.optionxform = str  # ty: ignore[invalid-assignment]
    cfg.read("config.ini")
    return cfg["Lasers"]["Lasers Terminals"]


def _do_laser_write(voltage: float, errors: list[tuple[str, str]], tag: str) -> None:
    import nidaqmx
    import numpy as np

    try:
        with nidaqmx.Task(new_task_name="lasers_setpoint") as task:
            task.ao_channels.add_ao_voltage_chan(_laser_terminals())
            task.write(
                np.stack((np.array([voltage]), np.array([0.0]))), auto_start=True
            )
    except BaseException as e:
        errors.append((tag, repr(e)))


def test_laser_task_from_qtimer_slot() -> None:
    """Laser Task created from a QTimer slot inside QApplication.exec.

    Mirrors the GUI: the laser write fires from a Qt slot (the debounce
    timeout / toggle button) while the event loop is running. Gated on
    RIG_LASER_VOLTAGE.
    """
    if not _have_pyside6():
        pytest.skip("PySide6 not available")
    voltage = float(os.environ.get("RIG_LASER_VOLTAGE", "0"))

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)

    errors = []
    results = []

    def fire() -> None:
        _do_laser_write(voltage, errors, tag="qtimer_slot")
        results.append("done")
        app.quit()

    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(fire)
    timer.start(500)
    app.exec()

    assert not errors, "Laser Task from QTimer slot crashed:\n" + "\n".join(
        f"{t}: {e}" for t, e in errors
    )
    assert results == ["done"]


def test_laser_task_from_daemon_thread_under_qapp() -> None:
    """Laser Task from a daemon thread spawned by a Qt slot (exact GUI path).

    The GUI's _toggle_laser1 spawns a daemon thread from the toggle-button
    slot. This reproduces that: a QTimer slot spawns a daemon thread that
    does the laser write while the event loop runs. Gated on
    RIG_LASER_VOLTAGE.
    """
    if not _have_pyside6():
        pytest.skip("PySide6 not available")
    voltage = float(os.environ.get("RIG_LASER_VOLTAGE", "0"))

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)

    errors = []
    done = threading.Event()

    def worker() -> None:
        _do_laser_write(voltage, errors, tag="daemon_thread")
        done.set()

    def spawn() -> None:
        t = threading.Thread(target=worker, daemon=True)
        t.start()

        # Poll from the GUI thread until the worker is done, then quit.
        def check() -> None:
            if done.is_set():
                app.quit()
            else:
                QTimer.singleShot(50, check)

        QTimer.singleShot(50, check)

    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(spawn)
    timer.start(500)
    app.exec()

    assert not errors, (
        "Laser Task from daemon thread under QApp crashed:\n"
        + "\n".join(f"{t}: {e}" for t, e in errors)
    )


def test_laser_task_with_full_hal_under_qapp() -> None:
    """Full hardware_init + laser Task from a QTimer slot under QApp.

    The closest repro to the GUI: construct Camera/SigGen/Motors/
    DAQLaser/ETLs/IBeam as hardware_init does, start the event loop, then
    fire the laser write from a QTimer slot. Gated on RIG_LASER_VOLTAGE.
    """
    if not _have_pyside6():
        pytest.skip("PySide6 not available")
    voltage = float(os.environ.get("RIG_LASER_VOLTAGE", "0"))

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)

    # Construct the full HAL as hardware_init does. The controller holds
    # list[ILaser] — index 0 is the DAQLaser (DAQ AO), index 1 is the
    # IBeamSmartLaser wrapping the IBeam serial engine.
    from lightsheet.hal import (
        Camera,
        DAQLaser,
        ETLs,
        IBeam,
        Motors,
        SigGen,
    )

    camera = Camera()
    siggen = SigGen(camera)  # noqa: F841 -- constructed for hardware-init side effects
    motors = Motors()  # noqa: F841 -- constructed for hardware-init side effects
    ibeam = IBeam()
    with contextlib.suppress(Exception):
        ibeam.open()
    laser1 = DAQLaser(
        terminal="/Dev7/ao0",
        wavelength=555,
        mw_per_volt=60.0,
        max_power_mw=300.0,
        label="Laser 1 (555 nm)",
    )
    etls = ETLs()
    etls.open()
    etls.set_analog_mode()

    errors = []
    results = []

    def fire() -> None:
        # The exact GUI laser-write path: set_power(mw) + on(), on the GUI
        # thread (this slot). voltage is a fraction of max_power (300 mW).
        mw = voltage / 5.0 * laser1.max_power
        laser1.set_power(mw)
        laser1.on()
        if laser1.error:
            errors.append(("laser1_on", laser1.error_message))
        laser1.off()
        results.append("done")
        app.quit()

    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(fire)
    timer.start(800)  # give hardware init a moment to settle
    app.exec()

    assert not errors, "Full-HAL laser write under QApp crashed:\n" + "\n".join(
        f"{t}: {e}" for t, e in errors
    )
    assert results == ["done"]
