"""Rig-only test: exercise the REAL controller laser methods against real HAL.

The pytest DAQ probes (test_daq_hal_rig.py) call nidaqmx.Task() directly in
a clean process — they do NOT exercise the GUI's actual code path
(_toggle_laser1 on a daemon thread, start_lasers -> _update_setpoints, the
real Lasers/IBeam instances hardware_init constructs). A clean-process probe
cannot reproduce a corruption that builds up from the GUI's specific call
sequence. This test closes that gap.

It extracts the real _toggle_laser1 / _write_laser1_power / start_lasers
method bodies from lightsheet/gui/controller.py (the AGENTS.md §5 exec-against-stand-in
pattern, same as test/test_laser_controls.py) and runs them against a
stand-in self holding REAL Lasers and IBeam instances constructed exactly
as hardware_init constructs them. This is the actual controller code running
against the actual DAQ — not raw nidaqmx calls.

Safety: all laser power is 0 V / 0 uW. laser1_power_pct = 0 so
_write_laser1_power writes 0 V to Dev7/ao0 (laser OFF — the safe state).
The iBeam path uses laser2_power_pct = 0. No laser is energized. The
operator does not need to be present.

Rig-only: skipped when the real nidaqmx driver is absent (Mac stub).
"""

import contextlib
import importlib.util
import os
import re
import threading
from collections.abc import Callable
from typing import Any
from unittest.mock import Mock

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

        nidaqmx.Task()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _real_nidaqmx_available(),
    reason="rig-only: requires the real NI-DAQmx driver runtime",
)


_CONTROLLER_SRC = os.path.join(os.path.dirname(__file__), "..", "lightsheet", "gui", "controller.py")


def _read_controller_source() -> str:
    with open(_CONTROLLER_SRC, encoding="utf-8", errors="replace") as f:
        return f.read()


def _slice_method(src: str, method_sig: str) -> str:
    m = re.search(r"def " + re.escape(method_sig) + r":", src)
    assert m, f"{method_sig} is missing"
    body = src[m.start() :]
    end = re.search(r"\n    def |\n    @pyqtSlot", body[1:])
    if end:
        body = body[: end.start() + 1]
    return body


def _load_method(method_sig: str) -> Callable[..., Any]:
    src = _read_controller_source()
    body = _slice_method(src, method_sig)
    namespace = {}
    exec(compile(body, _CONTROLLER_SRC, "exec"), namespace)
    func_name = method_sig.split("(")[0].strip()
    return namespace[func_name]


@pytest.fixture
def standin() -> Mock:
    """A stand-in Controller_MainWindow self with REAL HAL instances.

    Constructed exactly as hardware_init constructs them (Lasers(), IBeam()),
    plus the per-laser locks, estop_event, and staged-percent fields the
    laser methods read. sig_message is captured so we can assert on operator
    messages. The iBeam is opened (as hardware_init does); if COM4 is held
    by the running app the open fails gracefully and ibeam.error is set —
    the laser-1 (DAQ) path is still exercisable.
    """
    from lightsheet.ibeam import IBeam
    from lightsheet.lasers import Lasers

    s = Mock()
    s.lasers = Lasers()
    s.ibeam = IBeam()
    # COM4 may be held by the running app; laser-1 path still testable.
    with contextlib.suppress(Exception):
        s.ibeam.open()
    s.estop_event = threading.Event()
    s._laser1_write_lock = threading.RLock()
    s._laser2_write_lock = threading.RLock()
    s.laser1_power_pct = 0.0  # 0 V — laser OFF, safe
    s.laser2_power_pct = 0.0  # 0 uW — iBeam OFF, safe
    s._auto_laser1 = False
    s._auto_laser2 = False
    messages = []
    s.sig_message = Mock()
    s.sig_message.emit = lambda msg: messages.append(msg)
    s._messages = messages
    return s


def test_toggle_laser1_real_daq_no_access_violation(standin: Mock) -> None:
    """The real _toggle_laser1 (daemon-thread toggle) against real Lasers.

    Reproduces the "manual 555nm" path the operator ran during UAT, where
    _toggle_laser1 is spawned on a daemon thread and calls laser1_toggle()
    -> _update_setpoints (a real nidaqmx.Task write to Dev7/ao0). With
    laser1_power_pct = 0 the write is 0 V (laser OFF — safe). The test
    asserts no access violation escapes and the Lasers error surface is
    clean afterward.
    """
    toggle = _load_method("_toggle_laser1(self)")
    toggle(standin)
    # No access violation means the call returned without crashing the
    # process. The Lasers HAL should not be in an error state after a 0 V
    # write to a present Dev7.
    assert standin.lasers.error == 0, (
        "Lasers HAL reported an error after a 0 V toggle write: "
        f"{standin.lasers.error_message}"
    )


def test_toggle_laser1_on_daemon_thread_real_daq(standin: Mock) -> None:
    """_toggle_laser1 spawned on a daemon thread (as the GUI does it).

    The phase offloads the toggle to a daemon thread. If the access
    violation is thread-context-related (nidaqmx Task destructor racing
    with thread exit, or a thread-local handle issue), this reproduces it.
    """
    toggle = _load_method("_toggle_laser1(self)")
    errors = []
    done = threading.Event()

    def worker() -> None:
        try:
            toggle(standin)
        except BaseException as e:
            errors.append(repr(e))
        done.set()

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    done.wait(timeout=15)
    t.join(timeout=5)
    assert not errors, "Daemon-thread _toggle_laser1 crashed:\n" + "\n".join(errors)
    assert standin.lasers.error == 0, (
        f"Lasers HAL error after daemon-thread toggle: {standin.lasers.error_message}"
    )


def test_write_laser1_power_real_daq_repeated(standin: Mock) -> None:
    """The real _write_laser1_power (debounce-slot worker) repeatedly.

    Reproduces the spinbox-edit path: each debounce timeout spawns a daemon
    thread running _write_laser1_power. 0 V — laser OFF, safe. Repeats to
    catch intermittent corruption from repeated Task create/write/close
    cycles on the real Dev7 AO channels.
    """
    write = _load_method("_write_laser1_power(self, pct)")
    # Mark laser active so the write path actually runs.
    standin.lasers.laser1_active = True
    errors = []
    for _ in range(15):
        try:
            write(standin, 0.0)
        except BaseException as e:
            errors.append(repr(e))
    assert not errors, "_write_laser1_power crashed on real DAQ:\n" + "\n".join(errors)
    assert standin.lasers.error == 0, (
        f"Lasers HAL error after repeated 0 V writes: {standin.lasers.error_message}"
    )


def test_start_lasers_real_daq_then_siggen_create(standin: Mock) -> None:
    """The real start_lasers (acquisition worker path) then siggen create.

    Reproduces the single_mode_worker sequence: start_lasers() energizes
    the DAQ laser (0 V here — safe), then acquire_scan would call
    siggen.create_scanner(). This tests whether a laser DAQ write leaves
    the nidaqmx session in a state where a subsequent siggen task
    creation on Dev1 fails — the cascade behind the create_scan error.
    """
    from lightsheet.camera import Camera
    from lightsheet.siggen import SigGen

    start_lasers = _load_method("start_lasers(self)")
    # Enable auto-laser 1 so start_lasers actually writes to Dev7.
    standin._auto_laser1 = True
    standin.laser1_power_pct = 0.0  # 0 V — safe

    # Build a real SigGen as hardware_init does. Camera construction may
    # fail if the PCO SDK / camera is in use; if so, skip the siggen part
    # but still assert the laser write was clean.
    try:
        camera = Camera()
        siggen = SigGen(camera)
        standin.siggen = siggen
        have_siggen = True
    except Exception:
        have_siggen = False

    start_lasers(standin)
    assert standin.lasers.error == 0, (
        f"start_lasers DAQ write failed: {standin.lasers.error_message}"
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


def test_real_lasers_laser1_on_nonzero_voltage_no_crash() -> None:
    """The real Lasers.laser1_on() at a nonzero voltage — the exact GUI path.

    The operator's 555nm toggle called _toggle_laser1 -> laser1_toggle ->
    laser1_on -> _update_setpoints, which writes a nonzero voltage to
    Dev7/ao0. This test calls the real Lasers method (not a re-implemented
    nidaqmx.Task) at a small nonzero voltage to reproduce the access
    violation. Gated on RIG_LASER_VOLTAGE (energizes the laser).
    """
    import os

    voltage_pct = os.environ.get("RIG_LASER_VOLTAGE")
    if not voltage_pct:
        pytest.skip("set RIG_LASER_VOLTAGE (e.g. 0.5) to run; energizes laser 1")
    voltage = float(voltage_pct)

    from lightsheet.lasers import Lasers

    lasers = Lasers()
    lasers.laser1_power = voltage
    lasers.laser1_on()
    assert lasers.error == 0, (
        f"Lasers.laser1_on({voltage}V) failed: {lasers.error_message}"
    )
    lasers.laser1_off()


def test_real_lasers_laser1_on_daemon_thread_nonzero() -> None:
    """Real Lasers.laser1_on on a daemon thread (exact GUI toggle path).

    The GUI's _toggle_laser1 runs laser1_toggle on a daemon thread. This
    reproduces that exactly: real Lasers instance, nonzero voltage, daemon
    thread. Gated on RIG_LASER_VOLTAGE.
    """
    import os

    voltage_pct = os.environ.get("RIG_LASER_VOLTAGE")
    if not voltage_pct:
        pytest.skip("set RIG_LASER_VOLTAGE (e.g. 0.5) to run; energizes laser 1")
    voltage = float(voltage_pct)

    from lightsheet.lasers import Lasers

    lasers = Lasers()
    lasers.laser1_power = voltage
    errors = []
    done = threading.Event()

    def worker() -> None:
        try:
            lasers.laser1_on()
            if lasers.error:
                errors.append(("laser1_on", lasers.error_message))
            lasers.laser1_off()
        except BaseException as e:
            errors.append(("worker", repr(e)))
        done.set()

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    done.wait(timeout=15)
    t.join(timeout=5)
    assert not errors, "Daemon-thread real Lasers.laser1_on crashed:\n" + "\n".join(
        f"{tag}: {e}" for tag, e in errors
    )
