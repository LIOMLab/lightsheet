"""Rig-only test: probe the actual DAQ operations the HAL classes perform.

Isolates whether the laser-safety phase's failures are:
  (a) a pre-existing Dev7 laser-DAQ access violation that was silently
      swallowed by the old bare except and is now surfaced, OR
  (b) a Dev1 siggen task-creation failure, OR
  (c) a session-corruption cascade where a laser-write crash leaves
      nidaqmx in a bad state so subsequent siggen task creation fails.

Rig-only: skipped when the real nidaqmx driver is absent (Mac stub).

Safety: writes 0 V only. Dev7/ao0:1 (laser AO) at 0 V = laser OFF — the
safe state, never energizes the laser. Dev1 galvo/ETL at 0 V = rest. No
operator presence required.
"""

import contextlib
import importlib.util

import pytest


def _real_nidaqmx_available() -> bool:
    try:
        spec = importlib.util.find_spec("nidaqmx")
    except ValueError:
        # Stub module in sys.modules (Mac conftest) has __spec__ = None.
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
    reason="rig-only: requires the real NI-DAQmx driver runtime",
)


# Terminal strings matching config.ini (read from the real config so the
# test exercises the exact channels the app uses).
def _read_config_terminals() -> tuple[str, str, str]:
    import configparser

    cfg = configparser.ConfigParser()
    cfg.optionxform = str  # case-sensitive keys, like src/config.py
    cfg.read("config.ini")
    lasers_terminals = cfg["Lasers"]["Lasers Terminals"]
    ao_terminals = cfg["SigGen"]["AO Terminals"]
    do_terminals = cfg["SigGen"]["DO Terminals"]
    return lasers_terminals, ao_terminals, do_terminals


def _laser_ao_write_0v(terminals: str, errors: list[tuple[str, str]]) -> None:
    """Replicate Lasers._update_setpoints exactly, writing 0 V."""
    import nidaqmx
    import numpy as np

    try:
        with nidaqmx.Task(new_task_name="probe_laser") as task:
            task.ao_channels.add_ao_voltage_chan(terminals)
            task.write(np.stack((np.array([0.0]), np.array([0.0]))), auto_start=True)
    except BaseException as e:
        errors.append(("laser_write", repr(e)))


def _siggen_create_scanner(
    ao_terminals: str, do_terminals: str, errors: list[tuple[str, str]]
) -> None:
    """Replicate SigGen.create_scanner exactly (AO + DO tasks), 0 V / low."""
    import nidaqmx
    import numpy as np
    from nidaqmx.constants import AcquisitionType, Edge, LineGrouping

    task_ao = None
    task_do = None
    try:
        total_samples = 400
        # AO scan task
        task_ao = nidaqmx.Task(new_task_name="probe_siggen_ao")
        task_ao.ao_channels.add_ao_voltage_chan(ao_terminals)
        task_ao.timing.cfg_samp_clk_timing(
            rate=40000, sample_mode=AcquisitionType.FINITE, samps_per_chan=total_samples
        )
        # DO camera trigger task
        task_do = nidaqmx.Task(new_task_name="probe_siggen_do")
        task_do.do_channels.add_do_chan(
            do_terminals, line_grouping=LineGrouping.CHAN_PER_LINE
        )
        task_do.timing.cfg_samp_clk_timing(
            rate=40000, sample_mode=AcquisitionType.FINITE, samps_per_chan=total_samples
        )
        ao_device = ao_terminals.rsplit("/", 1)[0]
        do_start_trigger = ao_device + "/ao/StartTrigger"
        task_do.triggers.start_trigger.cfg_dig_edge_start_trig(
            do_start_trigger, trigger_edge=Edge.RISING
        )
        task_do.write(np.zeros(total_samples, dtype=bool), auto_start=False)
        task_ao.write(np.zeros((4, total_samples)), auto_start=False)
    except BaseException as e:
        errors.append(("siggen_create", repr(e)))
    finally:
        for t in (task_do, task_ao):
            if t is not None:
                with contextlib.suppress(Exception):
                    t.close()


def test_siggen_create_scanner_standalone() -> None:
    """Dev1 siggen task creation (AO + DO + start trigger) must succeed alone.

    If this fails, the create_scan error is a standalone Dev1 problem,
    not a cascade from the laser write.
    """
    _, ao_terminals, do_terminals = _read_config_terminals()
    errors = []
    _siggen_create_scanner(ao_terminals, do_terminals, errors)
    assert not errors, "Standalone siggen create_scanner failed on Dev1:\n" + "\n".join(
        repr(e) for _, e in errors[:5]
    )


def test_laser_ao_write_0v_standalone() -> None:
    """Dev7 laser AO write at 0 V (laser OFF) must succeed alone.

    If this fails with an access violation, the laser DAQ write was
    ALREADY broken before this phase — the old bare except just swallowed
    it silently. The phase's typed catch now surfaces it.
    """
    lasers_terminals, _, _ = _read_config_terminals()
    errors = []
    _laser_ao_write_0v(lasers_terminals, errors)
    assert not errors, "Standalone laser AO write (0 V) failed on Dev7:\n" + "\n".join(
        repr(e) for _, e in errors[:5]
    )


def test_siggen_after_laser_write_no_cascade() -> None:
    """Siggen task creation must still succeed after a laser write.

    Tests the cascade hypothesis: if the laser write crashes and corrupts
    the nidaqmx session, subsequent siggen task creation fails. If the
    laser write succeeds (0 V), siggen must still work afterward.
    """
    lasers_terminals, ao_terminals, do_terminals = _read_config_terminals()
    errors = []
    _laser_ao_write_0v(lasers_terminals, errors)
    _siggen_create_scanner(ao_terminals, do_terminals, errors)
    assert not errors, "Laser write -> siggen create cascade failed:\n" + "\n".join(
        repr(e) for _, e in errors[:5]
    )


def test_laser_ao_write_0v_repeated_no_intermittent_failure() -> None:
    """Laser AO write at 0 V must succeed repeatedly (intermittency check).

    The access violation the operator saw during UAT may have been
    transient or caused by prior crashed-task state. If 0 V writes succeed
    reliably across many iterations, the DAQ write path itself is sound
    and the earlier failure was state-related, not a code defect.
    """
    lasers_terminals, _, _ = _read_config_terminals()
    errors = []
    for _ in range(25):
        _laser_ao_write_0v(lasers_terminals, errors)
    assert not errors, (
        "Repeated laser AO write (0 V) failed intermittently:\n"
        + "\n".join(repr(e) for _, e in errors[:5])
    )


def test_laser_write_on_daemon_thread_mimics_toggle() -> None:
    """Laser AO write from a daemon thread (mimics _toggle_laser1) must work.

    The phase offloads laser writes to daemon threads. If the access
    violation is thread-related (e.g. nidaqmx Task destructor racing with
    thread exit), this reproduces it. Writes 0 V (laser OFF — safe).
    """
    import threading

    lasers_terminals, _, _ = _read_config_terminals()
    errors = []
    done = threading.Event()

    def worker() -> None:
        for _ in range(20):
            _laser_ao_write_0v(lasers_terminals, errors)
        done.set()

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    done.wait(timeout=30)
    t.join(timeout=5)
    assert not errors, "Daemon-thread laser AO write (0 V) failed:\n" + "\n".join(
        repr(e) for _, e in errors[:5]
    )
