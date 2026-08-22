'''Rig-only test: concurrent nidaqmx.Task creation corrupts the DAQ session.

This test ONLY runs on the rig (real nidaqmx driver runtime present). On the
Mac the conftest stub makes nidaqmx.Task() raise, so the module-level skip
fires and the test is a no-op.

Hypothesis: the laser-safety phase offloaded laser DAQ writes to daemon
worker threads (gui/controller.py _write_laser1_power / _toggle_laser1 etc.)
that call nidaqmx.Task(...) + AO writes concurrently with the acquisition
worker's siggen.create_scanner() (also nidaqmx.Task). nidaqmx is not
thread-safe for concurrent task creation — two threads creating/using DAQ
tasks simultaneously corrupts the internal task handle table, producing
"access violation reading 0x0000000000000000" on the laser write and a
downstream "create_scan error" when the DAQ session is left corrupt.

This test reproduces the concurrency directly against Dev1 (galvo/ETL AO
channels) at 0 V — galvos sit at their rest position, no laser (Dev7) is
touched, no hardware risk. It runs two threads that each create and write
nidaqmx.Task objects many times concurrently and asserts that no access
violation / null-pointer error escapes the process.

Safety: writes 0 V to /Dev1/ao0:3 (galvo + ETL) only. Never touches
/Dev7/ao0:1 (laser AO). The operator does not need to be present.
'''

import threading
import importlib.util

import pytest


def _real_nidaqmx_available():
    '''True only if the real nidaqmx driver runtime is present (rig).'''
    try:
        spec = importlib.util.find_spec('nidaqmx')
    except ValueError:
        return False
    if spec is None:
        return False
    try:
        import nidaqmx
        nidaqmx.Task()  # conftest uses the same probe
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _real_nidaqmx_available(),
    reason='rig-only: requires the real NI-DAQmx driver runtime (Dev1 present)',
)


# Dev1 galvo + ETL AO terminals (NOT the laser — laser is Dev7/ao0:1).
# 0 V to a galvo holds it at rest; no hardware motion risk.
# Laser-like and siggen-like use NON-overlapping channel ranges so a
# resource-reservation conflict (-50103) is NOT the failure mode — any
# error here is pure concurrency corruption (the access-violation bug).
_LASER_LIKE_TERMINALS = '/Dev1/ao0:1'    # 2 channels, mimics Dev7/ao0:1
_SIGGEN_LIKE_TERMINALS = '/Dev1/ao2:3'   # 2 channels, non-overlapping


def _laser_like_write(errors):
    '''Mimic Lasers._update_setpoints: create a Task, add AO chan, write.

    Uses Dev1 ao0:1 at 0 V instead of Dev7 laser channels — same
    nidaqmx.Task() + add_ao_voltage_chan + write call pattern, no laser.
    '''
    import nidaqmx
    import numpy as np
    try:
        with nidaqmx.Task(new_task_name='concurrency_laser_like') as task:
            task.ao_channels.add_ao_voltage_chan(_LASER_LIKE_TERMINALS)
            task.write(np.stack((np.array([0.0]), np.array([0.0]))),
                       auto_start=True)
    except BaseException as e:  # noqa: BLE001 — capture access violations too
        errors.append(repr(e))


def _siggen_like_create(errors):
    '''Mimic SigGen.create_scanner: create a Task, add AO channels, write.

    Uses Dev1 ao2:3 at 0 V (non-overlapping with the laser-like channels).
    Same nidaqmx.Task() creation pattern as the real create_scanner, no
    laser, no camera trigger. auto_start=True so the write succeeds without
    a separate timing config — the point is concurrent Task() creation.
    '''
    import nidaqmx
    import numpy as np
    task_ao = None
    try:
        task_ao = nidaqmx.Task(new_task_name='concurrency_siggen_ao')
        task_ao.ao_channels.add_ao_voltage_chan(_SIGGEN_LIKE_TERMINALS)
        task_ao.write(np.stack((np.array([0.0]), np.array([0.0]))),
                      auto_start=True)
    except BaseException as e:  # noqa: BLE001 — capture access violations too
        errors.append(repr(e))
    finally:
        if task_ao is not None:
            try:
                task_ao.close()
            except Exception:
                pass


def test_concurrent_daq_task_creation_does_not_corrupt_session():
    '''Two threads creating nidaqmx.Task objects concurrently must not crash.

    This is the reproduction test for the regression introduced by the
    laser-safety phase's offloading of DAQ writes to worker threads. Before
    the fix (a shared DAQ lock serializing all nidaqmx.Task creation), this
    test produces access-violation errors on the rig. After the fix it
    passes cleanly.
    '''
    errors = []
    iterations = 30

    def worker(fn, n):
        for _ in range(n):
            fn(errors)

    t1 = threading.Thread(target=worker, args=(_laser_like_write, iterations))
    t2 = threading.Thread(target=worker, args=(_siggen_like_create, iterations))
    t1.start()
    t2.start()
    t1.join(timeout=60)
    t2.join(timeout=60)

    # An access violation reading 0x0 is the signature of the corruption.
    assert not errors, (
        'Concurrent nidaqmx.Task creation produced errors (DAQ session '
        'corruption):\n' + '\n'.join(errors[:10])
    )


def test_serial_daq_task_creation_is_clean_baseline():
    '''Baseline: the same Task creation pattern run serially must succeed.

    If this fails, the rig's DAQ is broken for a non-concurrency reason
    (device gone offline, driver issue) and the concurrency test above is
    not a valid regression signal.
    '''
    errors = []
    iterations = 20
    for _ in range(iterations):
        _laser_like_write(errors)
        _siggen_like_create(errors)

    assert not errors, (
        'Serial nidaqmx.Task creation produced errors — rig DAQ is broken '
        'independent of concurrency:\n' + '\n'.join(errors[:10])
    )
