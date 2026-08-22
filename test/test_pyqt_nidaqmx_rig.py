'''Rig-only test: does PyQt5 + nidaqmx interaction cause the access violation?

Every plain-Python repro passes. The GUI runs inside QApplication.exec_()
with a 100ms QTimer and the laser toggle spawned from a Qt slot on a daemon
thread. This test mirrors that: constructs the full HAL inside a QApplication,
starts the event loop, and triggers a laser Task creation from a QTimer
slot (and from a daemon thread, as the GUI does).

Rig-only: skipped when the real nidaqmx driver is absent (Mac stub).
'''

import importlib.util
import os
import sys
import threading
import time

import pytest

sys.path.append('.')


def _real_nidaqmx_available():
    spec = importlib.util.find_spec('nidaqmx')
    if spec is None:
        return False
    try:
        import nidaqmx
        nidaqmx.Task()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _real_nidaqmx_available(),
    reason='rig-only: requires the real NI-DAQmx driver runtime',
)


def _have_pyqt5():
    try:
        import PyQt5  # noqa: F401
        return True
    except Exception:
        return False


def _laser_terminals():
    import configparser
    cfg = configparser.ConfigParser()
    cfg.optionxform = str
    cfg.read('config.ini')
    return cfg['Lasers']['Lasers Terminals']


def _do_laser_write(voltage, errors, tag):
    import nidaqmx
    import numpy as np
    try:
        with nidaqmx.Task(new_task_name='lasers_setpoint') as task:
            task.ao_channels.add_ao_voltage_chan(_laser_terminals())
            task.write(np.stack((np.array([voltage]), np.array([0.0]))),
                       auto_start=True)
    except BaseException as e:  # noqa: BLE001
        errors.append((tag, repr(e)))


def test_laser_task_from_qtimer_slot():
    '''Laser Task created from a QTimer slot inside QApplication.exec_.

    Mirrors the GUI: the laser write fires from a Qt slot (the debounce
    timeout / toggle button) while the event loop is running. Gated on
    RIG_LASER_VOLTAGE.
    '''
    if not _have_pyqt5():
        pytest.skip('PyQt5 not available')
    voltage = os.environ.get('RIG_LASER_VOLTAGE')
    if not voltage:
        pytest.skip('set RIG_LASER_VOLTAGE (e.g. 0.5) to run; energizes laser 1')
    voltage = float(voltage)

    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)

    errors = []
    results = []

    def fire():
        _do_laser_write(voltage, errors, tag='qtimer_slot')
        results.append('done')
        app.quit()

    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(fire)
    timer.start(500)
    app.exec_()

    assert not errors, (
        'Laser Task from QTimer slot crashed:\n'
        + '\n'.join(f'{t}: {e}' for t, e in errors))
    assert results == ['done']


def test_laser_task_from_daemon_thread_under_qapp():
    '''Laser Task from a daemon thread spawned by a Qt slot (exact GUI path).

    The GUI's _toggle_laser1 spawns a daemon thread from the toggle-button
    slot. This reproduces that: a QTimer slot spawns a daemon thread that
    does the laser write while the event loop runs. Gated on
    RIG_LASER_VOLTAGE.
    '''
    if not _have_pyqt5():
        pytest.skip('PyQt5 not available')
    voltage = os.environ.get('RIG_LASER_VOLTAGE')
    if not voltage:
        pytest.skip('set RIG_LASER_VOLTAGE (e.g. 0.5) to run; energizes laser 1')
    voltage = float(voltage)

    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)

    errors = []
    done = threading.Event()

    def worker():
        _do_laser_write(voltage, errors, tag='daemon_thread')
        done.set()

    def spawn():
        t = threading.Thread(target=worker, daemon=True)
        t.start()
        # Poll from the GUI thread until the worker is done, then quit.
        def check():
            if done.is_set():
                app.quit()
            else:
                QTimer.singleShot(50, check)
        QTimer.singleShot(50, check)

    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(spawn)
    timer.start(500)
    app.exec_()

    assert not errors, (
        'Laser Task from daemon thread under QApp crashed:\n'
        + '\n'.join(f'{t}: {e}' for t, e in errors))


def test_laser_task_with_full_hal_under_qapp():
    '''Full hardware_init + laser Task from a QTimer slot under QApp.

    The closest repro to the GUI: construct Camera/SigGen/Motors/Lasers/
    ETLs/IBeam as hardware_init does, start the event loop, then fire the
    laser write from a QTimer slot. Gated on RIG_LASER_VOLTAGE.
    '''
    if not _have_pyqt5():
        pytest.skip('PyQt5 not available')
    voltage = os.environ.get('RIG_LASER_VOLTAGE')
    if not voltage:
        pytest.skip('set RIG_LASER_VOLTAGE (e.g. 0.5) to run; energizes laser 1')
    voltage = float(voltage)

    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)

    # Construct the full HAL as hardware_init does.
    from src.camera import Camera
    from src.siggen import SigGen
    from src.motors import Motors
    from src.lasers import Lasers
    from src.etls import ETLs
    from src.ibeam import IBeam
    camera = Camera()
    siggen = SigGen(camera)
    motors = Motors()
    lasers = Lasers()
    etls = ETLs()
    etls.open()
    etls.set_analog_mode()
    ibeam = IBeam()
    try:
        ibeam.open()
    except Exception:
        pass

    errors = []
    results = []

    def fire():
        # The exact GUI laser-write path: real Lasers._update_setpoints
        # via laser1_on, on the GUI thread (this slot).
        lasers.laser1_power = voltage
        lasers.laser1_on()
        if lasers.error:
            errors.append(('laser1_on', lasers.error_message))
        lasers.laser1_off()
        results.append('done')
        app.quit()

    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(fire)
    timer.start(800)  # give hardware init a moment to settle
    app.exec_()

    assert not errors, (
        'Full-HAL laser write under QApp crashed:\n'
        + '\n'.join(f'{t}: {e}' for t, e in errors))
    assert results == ['done']
