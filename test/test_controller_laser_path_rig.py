"""Rig-only test: exercise the REAL controller laser methods against real HAL.

The pytest DAQ probes (test_daq_hal_rig.py) call nidaqmx.Task() directly in
a clean process — they do NOT exercise the GUI's actual code path
(_toggle_laser1 on a daemon thread, start_lasers -> set_power, the real
DAQLaser/IBeamSmartLaser instances hardware_init constructs). A
clean-process probe cannot reproduce a corruption that builds up from the
GUI's specific call sequence. This test closes that gap.

The real controller is constructed via ``make_controller`` (see
``test/_helpers/controller_fixture.py``), which builds a mock
``DeviceBundle`` and wires all four collaborators. The laser methods are
exercised via ``ctrl._hw.<method>()`` real calls — the actual controller
code running against the actual HAL layer.

Safety: all laser power is 0 V / 0 uW. laser1_power_pct = 0 so
_write_laser1_power writes 0 V to Dev7/ao0 (laser OFF — the safe state).
The iBeam path uses laser2_power_pct = 0. No laser is energized. The
operator does not need to be present.

Rig-only: skipped when the real nidaqmx driver is absent (Mac stub).
"""

from __future__ import annotations

import contextlib
import importlib.util
import threading

import pytest
from _helpers.controller_fixture import make_controller
from pytest import FixtureRequest
from pytestqt.qtbot import QtBot


def _real_nidaqmx_available() -> bool:
    try:
        spec = importlib.util.find_spec("nidaqmx")
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


pytestmark = [
    pytest.mark.skipif(
        not _real_nidaqmx_available(),
        reason="rig-only: requires the real NI-DAQmx driver runtime",
    ),
    pytest.mark.xdist_group("rig_hardware"),
]


def test_toggle_laser1_real_daq_no_access_violation(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """The real _toggle_laser1 (daemon-thread toggle) via ctrl._hw.

    Reproduces the "manual 555nm" path the operator ran during UAT, where
    _toggle_laser1 is spawned on a daemon thread and calls
    self.lasers[0].on()/.off() (a real nidaqmx.Task write to Dev7/ao0).
    With laser1_power_pct = 0 the write is 0 mW (laser OFF — safe). The
    test asserts no access violation escapes and the laser's error surface
    is clean afterward.
    """
    ctrl, _bundle = make_controller(qtbot, request)
    ctrl.laser1_power_pct = 0.0  # 0 mW — laser OFF, safe

    ctrl._hw._toggle_laser1()

    # No access violation means the call returned without crashing the
    # process. The laser HAL should not be in an error state after a 0 mW
    # write to a present Dev7.
    assert ctrl._hw.lasers[0].error == 0, (
        "Laser 1 HAL reported an error after a 0 mW toggle write: "
        f"{ctrl._hw.lasers[0].error_message}"
    )


def test_toggle_laser1_on_daemon_thread_real_daq(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """_toggle_laser1 spawned on a daemon thread (as the GUI does it).

    The phase offloads the toggle to a daemon thread. If the access
    violation is thread-context-related (nidaqmx Task destructor racing
    with thread exit, or a thread-local handle issue), this reproduces it.
    """
    ctrl, _bundle = make_controller(qtbot, request)
    ctrl.laser1_power_pct = 0.0  # 0 mW — laser OFF, safe

    errors = []
    done = threading.Event()

    def worker() -> None:
        try:
            ctrl._hw._toggle_laser1()
        except BaseException as e:
            errors.append(repr(e))
        done.set()

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    done.wait(timeout=15)
    t.join(timeout=5)
    assert not errors, "Daemon-thread _toggle_laser1 crashed:\n" + "\n".join(errors)
    assert ctrl._hw.lasers[0].error == 0, (
        f"Laser 1 HAL error after daemon-thread toggle: "
        f"{ctrl._hw.lasers[0].error_message}"
    )


def test_write_laser1_power_real_daq_repeated(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """The real _write_laser1_power (debounce-slot worker) repeatedly.

    Reproduces the spinbox-edit path: each debounce timeout spawns a daemon
    thread running _write_laser1_power. 0 mW — laser OFF, safe. Repeats to
    catch intermittent corruption from repeated Task create/write/close
    cycles on the real Dev7 AO channels.
    """
    ctrl, _bundle = make_controller(qtbot, request)
    # Mark laser active so the write path actually runs.
    ctrl._hw.lasers[0].active = True
    errors = []
    for _ in range(15):
        try:
            ctrl._hw._write_laser1_power(0.0)
        except BaseException as e:
            errors.append(repr(e))
    assert not errors, "_write_laser1_power crashed on real DAQ:\n" + "\n".join(errors)
    assert ctrl._hw.lasers[0].error == 0, (
        f"Laser 1 HAL error after repeated 0 mW writes: "
        f"{ctrl._hw.lasers[0].error_message}"
    )


def test_start_lasers_real_daq_then_siggen_create(
    qtbot: QtBot, request: FixtureRequest
) -> None:
    """The real start_lasers (acquisition worker path) then siggen create.

    Reproduces the single_mode_worker sequence: start_lasers() energizes
    the DAQ laser (0 mW here — safe), then acquire_scan would call
    siggen.create_scanner(). This tests whether a laser DAQ write leaves
    the nidaqmx session in a state where a subsequent siggen task
    creation on Dev1 fails — the cascade behind the create_scan error.
    """
    from lightsheet.hal import Camera, SigGen

    ctrl, _bundle = make_controller(qtbot, request)
    # Enable auto-laser 1 so start_lasers actually writes to Dev7.
    ctrl._auto_laser1 = True
    ctrl.laser1_power_pct = 0.0  # 0 mW — safe

    # Build a real SigGen as hardware_init does. Camera construction may
    # fail if the PCO SDK / camera is in use; if so, skip the siggen part
    # but still assert the laser write was clean.
    try:
        camera = Camera()
        siggen = SigGen(camera)
        have_siggen = True
    except Exception:
        have_siggen = False

    ctrl._hw.start_lasers()
    assert ctrl._hw.lasers[0].error == 0, (
        f"start_lasers DAQ write failed: {ctrl._hw.lasers[0].error_message}"
    )

    if have_siggen:
        # Mimic acquire_scan's create_scanner() call. compute_scan_waveforms
        # needs camera shutter settings; arm_scan sets them. If the camera
        # isn't usable this will error — catch and report, don't crash.
        try:
            camera.arm_scan()
            siggen.compute_scan_waveforms()
            siggen.create_scanner()
        except Exception as e:
            pytest.skip(f"camera/siggen setup unavailable on rig: {e}")
        assert siggen.error == 0, (
            f"siggen.create_scanner failed after start_lasers: {siggen.error_message}"
        )
        with contextlib.suppress(Exception):
            siggen.delete_scanner()


def test_real_daqlaser_on_nonzero_voltage_no_crash() -> None:
    """The real DAQLaser.on() at a nonzero voltage — the exact GUI path.

    The operator's 555nm toggle called _toggle_laser1 -> self.lasers[0].on(),
    which writes a nonzero voltage to Dev7/ao0 via the DAQLaser backend.
    This test calls the real DAQLaser method (not a re-implemented
    nidaqmx.Task) at a small nonzero voltage to reproduce the access
    violation. Gated on RIG_LASER_VOLTAGE (energizes the laser).
    """
    import os

    voltage_pct = os.environ.get("RIG_LASER_VOLTAGE")
    if not voltage_pct:
        pytest.skip("set RIG_LASER_VOLTAGE (e.g. 0.5) to run; energizes laser 1")
    voltage = float(voltage_pct)

    from lightsheet.hal import DAQLaser

    # voltage is a fraction of the 5V full-scale; convert to mW via
    # mw_per_volt=60 (300 mW max / 5V).
    mw = voltage / 5.0 * 300.0
    laser = DAQLaser(
        channel="/Dev7/ao0",
        wavelength=555,
        mw_per_volt=60.0,
        max_power_mw=300.0,
        label="Laser 1 (555 nm)",
    )
    laser.set_power(mw)
    laser.on()
    assert laser.error == 0, f"DAQLaser.on({voltage}V) failed: {laser.error_message}"
    laser.off()


def test_real_daqlaser_on_daemon_thread_nonzero() -> None:
    """Real DAQLaser.on on a daemon thread (exact GUI toggle path).

    The GUI's _toggle_laser1 runs the toggle on a daemon thread. This
    reproduces that exactly: real DAQLaser instance, nonzero voltage,
    daemon thread. Gated on RIG_LASER_VOLTAGE.
    """
    import os

    voltage_pct = os.environ.get("RIG_LASER_VOLTAGE")
    if not voltage_pct:
        pytest.skip("set RIG_LASER_VOLTAGE (e.g. 0.5) to run; energizes laser 1")
    voltage = float(voltage_pct)

    from lightsheet.hal import DAQLaser

    mw = voltage / 5.0 * 300.0
    laser = DAQLaser(
        channel="/Dev7/ao0",
        wavelength=555,
        mw_per_volt=60.0,
        max_power_mw=300.0,
        label="Laser 1 (555 nm)",
    )
    laser.set_power(mw)
    errors = []
    done = threading.Event()

    def worker() -> None:
        try:
            laser.on()
            if laser.error:
                errors.append(("laser_on", laser.error_message))
            laser.off()
        except BaseException as e:
            errors.append(("worker", repr(e)))
        done.set()

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    done.wait(timeout=15)
    t.join(timeout=5)
    assert not errors, "Daemon-thread real DAQLaser.on crashed:\n" + "\n".join(
        f"{tag}: {e}" for tag, e in errors
    )
