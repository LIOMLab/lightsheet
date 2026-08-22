'''Rig-only test: does a laser Task write+close corrupt the nidaqmx session
so a subsequent siggen Task creation hangs or crashes?

Reproduces the exact GUI failure sequence from the rig console log:
  1. Laser toggle: nidaqmx.Task('lasers_setpoint') + add_ao_voltage_chan
     + write + close (context manager __exit__ -> DAQmxClearTask).
  2. Get Single Image: camera.arm_scan() then start_lasers() then
     siggen.create_scanner() -> nidaqmx.Task('galvo_etl_scan') on Dev1.

The console log showed the laser write surfaced "access violation reading
0x0000000000000000" (a null-pointer deref inside the nidaqmx C library on
Task close — a use-after-free of the task handle), and the subsequent
single-image acquisition hung silently after camera arm with no further
log output — i.e. create_scanner() never returned.

This test reproduces both steps against the real DAQ with a NONZERO laser
voltage (the operator's 555nm toggle used a nonzero spinbox %). 0 V did
not reproduce the crash in earlier probes. The nonzero voltage exercises
the same write path the GUI used.

Safety: writes a small voltage (0.5 V) to Dev7/ao0 (laser 1, 555nm). This
IS a real laser emission — only safe if the beam path is clear / blocked.
The test is gated on an env var RIG_LASER_VOLTAGE so it cannot run by
accident; without the env var it skips.

Rig-only: skipped when the real nidaqmx driver is absent (Mac stub).
'''

import importlib.util
import os
import threading
import time

import pytest


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


def _laser_terminals():
    import configparser
    cfg = configparser.ConfigParser()
    cfg.optionxform = str
    cfg.read('config.ini')
    return cfg['Lasers']['Lasers Terminals']


def _siggen_terminals():
    import configparser
    cfg = configparser.ConfigParser()
    cfg.optionxform = str
    cfg.read('config.ini')
    return cfg['SigGen']['AO Terminals'], cfg['SigGen']['DO Terminals']


def _laser_write(voltage, errors, tag='laser'):
    '''Replicate Lasers._update_setpoints exactly: Task + chan + write + close.'''
    import nidaqmx
    import numpy as np
    try:
        with nidaqmx.Task(new_task_name='lasers_setpoint') as task:
            task.ao_channels.add_ao_voltage_chan(_laser_terminals())
            task.write(np.stack((np.array([voltage]), np.array([0.0]))),
                       auto_start=True)
    except BaseException as e:  # noqa: BLE001
        errors.append((tag, repr(e)))


def _siggen_create(errors, tag='siggen'):
    '''Replicate SigGen.create_scanner: AO + DO tasks + start trigger + write.'''
    import nidaqmx
    import numpy as np
    from nidaqmx.constants import AcquisitionType, LineGrouping, Edge
    ao_term, do_term = _siggen_terminals()
    task_ao = None
    task_do = None
    try:
        total = 400
        task_ao = nidaqmx.Task(new_task_name='galvo_etl_scan')
        task_ao.ao_channels.add_ao_voltage_chan(ao_term)
        task_ao.timing.cfg_samp_clk_timing(
            rate=40000, sample_mode=AcquisitionType.FINITE,
            samps_per_chan=total)
        task_do = nidaqmx.Task(new_task_name='camera_scan')
        task_do.do_channels.add_do_chan(
            do_term, line_grouping=LineGrouping.CHAN_PER_LINE)
        task_do.timing.cfg_samp_clk_timing(
            rate=40000, sample_mode=AcquisitionType.FINITE,
            samps_per_chan=total)
        ao_device = ao_term.rsplit('/', 1)[0]
        task_do.triggers.start_trigger.cfg_dig_edge_start_trig(
            ao_device + '/ao/StartTrigger', trigger_edge=Edge.RISING)
        task_do.write(np.zeros(total, dtype=bool), auto_start=False)
        task_ao.write(np.zeros((4, total)), auto_start=False)
    except BaseException as e:  # noqa: BLE001
        errors.append((tag, repr(e)))
    finally:
        for t in (task_do, task_ao):
            if t is not None:
                try:
                    t.close()
                except Exception:
                    pass


def test_laser_write_then_siggen_create_no_corruption():
    '''Laser write (nonzero V) + close, then siggen create — must not hang/crash.

    This is the exact GUI sequence that hung the rig. Without the env var
    RIG_LASER_VOLTAGE set it skips (the nonzero write energizes the laser).
    '''
    voltage = os.environ.get('RIG_LASER_VOLTAGE')
    if not voltage:
        pytest.skip('set RIG_LASER_VOLTAGE (e.g. 0.5) to run; energizes laser 1')
    voltage = float(voltage)

    errors = []
    _laser_write(voltage, errors, tag='laser_toggle')
    # If the laser write itself crashed, the session may already be corrupt.
    # Still attempt the siggen create to see if it hangs.
    _siggen_create(errors, tag='siggen_after_laser')

    assert not errors, (
        'Laser write -> siggen create sequence produced errors (session '
        'corruption):\n' + '\n'.join(f'{t}: {e}' for t, e in errors[:5]))


def test_laser_write_daemon_thread_then_siggen_main_thread():
    '''Laser write on a daemon thread (as the GUI does), siggen on main.

    Reproduces the GUI's threading: _toggle_laser1 spawns a daemon thread
    that writes+closes the laser Task, while the single_mode_worker (main
    acquisition thread) later calls create_scanner. If the daemon thread's
    Task close races with the main thread's Task create, the session
    corrupts and create_scanner hangs.
    '''
    voltage = os.environ.get('RIG_LASER_VOLTAGE')
    if not voltage:
        pytest.skip('set RIG_LASER_VOLTAGE (e.g. 0.5) to run; energizes laser 1')
    voltage = float(voltage)

    errors = []
    done = threading.Event()

    def laser_worker():
        _laser_write(voltage, errors, tag='laser_daemon')
        done.set()

    t = threading.Thread(target=laser_worker, daemon=True)
    t.start()
    # Don't wait for the daemon thread to fully finish — mimic the GUI where
    # the toggle thread and the acquisition worker overlap. Give it a moment
    # to start the write, then immediately start the siggen create.
    time.sleep(0.05)
    _siggen_create(errors, tag='siggen_main')
    done.wait(timeout=10)
    t.join(timeout=5)

    assert not errors, (
        'Daemon-thread laser write + main-thread siggen create produced '
        'errors (thread-race session corruption):\n'
        + '\n'.join(f'{t}: {e}' for t, e in errors[:5]))
