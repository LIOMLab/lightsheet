'''Rig-only test: does main.py's nidaqmx.Task.__del__ patch cause the crash?

main.py patches nidaqmx.Task.__del__ to guard _saved_name (a workaround for
a 0.6.x Task.__del__ AttributeError). The pytest repros do NOT apply this
patch and never crash. This test applies the exact patch from main.py and
then runs the laser write path — if the patch interacts with the C library
during GC and causes the access violation, this reproduces it.

Rig-only: skipped when the real nidaqmx driver is absent (Mac stub).
'''

import importlib.util
import os
import threading
import warnings

import pytest


def _real_nidaqmx_available():
    try:
        spec = importlib.util.find_spec('nidaqmx')
    except ValueError:
        return False
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


def _apply_main_py_task_del_patch():
    '''Apply the exact nidaqmx.Task.__del__ patch from main/main.py.'''
    import nidaqmx
    try:
        from nidaqmx.errors import DaqResourceWarning

        def _safe_task_del(self):
            saved_name = getattr(self, '_saved_name', None)
            if saved_name:
                warnings.warn(
                    'Task "{}" was not explicitly closed and may still be '
                    'reserved.'.format(saved_name), DaqResourceWarning)

        nidaqmx.Task.__del__ = _safe_task_del
        return True
    except Exception:
        return False


def _laser_terminals():
    import configparser
    cfg = configparser.ConfigParser()
    cfg.optionxform = str
    cfg.read('config.ini')
    return cfg['Lasers']['Lasers Terminals']


def test_laser_write_with_task_del_patch_nonzero():
    '''Laser write at nonzero V WITH the main.py __del__ patch applied.

    If the access violation only reproduces with the patch, the patch is
    the cause. Gated on RIG_LASER_VOLTAGE.
    '''
    import gc
    import nidaqmx
    import numpy as np

    voltage = os.environ.get('RIG_LASER_VOLTAGE')
    if not voltage:
        pytest.skip('set RIG_LASER_VOLTAGE (e.g. 0.5) to run; energizes laser 1')
    voltage = float(voltage)

    assert _apply_main_py_task_del_patch(), 'failed to apply __del__ patch'

    errors = []
    for i in range(20):
        try:
            with nidaqmx.Task(new_task_name='lasers_setpoint') as task:
                task.ao_channels.add_ao_voltage_chan(_laser_terminals())
                task.write(np.stack((np.array([voltage]), np.array([0.0]))),
                           auto_start=True)
        except BaseException as e:  # noqa: BLE001
            errors.append((f'iter_{i}', repr(e)))
            break
        # Force GC so __del__ runs on the just-closed Task while the next
        # iteration creates a new one — the race the patch might trigger.
        gc.collect()
        if errors:
            break

    assert not errors, (
        'Laser write crashed WITH the main.py __del__ patch applied:\n'
        + '\n'.join(f'{t}: {e}' for t, e in errors))


def test_laser_write_with_patch_daemon_thread_nonzero():
    '''Laser write on a daemon thread WITH the __del__ patch — exact GUI.

    The GUI runs _toggle_laser1 on a daemon thread with the patch active.
    Gated on RIG_LASER_VOLTAGE.
    '''
    import nidaqmx
    import numpy as np

    voltage = os.environ.get('RIG_LASER_VOLTAGE')
    if not voltage:
        pytest.skip('set RIG_LASER_VOLTAGE (e.g. 0.5) to run; energizes laser 1')
    voltage = float(voltage)

    assert _apply_main_py_task_del_patch(), 'failed to apply __del__ patch'

    errors = []
    done = threading.Event()

    def worker():
        import gc
        try:
            for _ in range(10):
                with nidaqmx.Task(new_task_name='lasers_setpoint') as task:
                    task.ao_channels.add_ao_voltage_chan(_laser_terminals())
                    task.write(np.stack((np.array([voltage]),
                                         np.array([0.0]))),
                               auto_start=True)
                gc.collect()
        except BaseException as e:  # noqa: BLE001
            errors.append(('worker', repr(e)))
        done.set()

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    done.wait(timeout=20)
    t.join(timeout=5)
    assert not errors, (
        'Daemon-thread laser write crashed WITH __del__ patch:\n'
        + '\n'.join(f'{t}: {e}' for t, e in errors))
