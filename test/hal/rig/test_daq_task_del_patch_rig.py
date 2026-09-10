"""Regression test for the REMOVED nidaqmx Task.__del__ workaround.

The application no longer monkeypatches ``nidaqmx.Task.__del__``. The old
guard worked around a nidaqmx 0.6.x bug where a partially-constructed
Task's ``__del__`` raised AttributeError reading ``_saved_name``; pinned
nidaqmx 1.6.0 initializes every field ``__del__`` reads (``_handle``,
``_close_on_exit``, ``_saved_name``, ``_grpc_options``, ``_event_handlers``)
before any fallible call, so the guard is dead code.

This file guards the removal:

- ``test_task_del_patch_absent`` carries no mark of its own and asserts
  the ``Task.__del__`` the DAQ laser consumes carries no lightsheet
  provenance. It reads the module object through
  ``lightsheet.hal.real.daqlaser`` — never a bare ``import nidaqmx``
  re-lookup — so a stale sys.modules entry cannot mask a live patch.
  Everything under ``test/hal/rig/`` is collection-skipped without
  ``LIGHTSHEET_HW=1`` (the directory name puts "rig" in item.keywords),
  so the dev-side copy of this assertion lives in
  ``test/main/test_main_bootstrap.py``.
- The real-DAQ churn legs (``_RIG_ONLY``) keep the original ~20x
  task-creation + ``gc.collect()`` churn and the daemon-thread leg,
  proving repeated Task construction/close/GC stays clean without the
  patch.
- ``test_partially_constructed_task_del_is_quiet`` forces a mid-init
  construction failure on the rig and asserts GC of the half-built Task
  is silent — the exact shape the removed guard existed for. The dev
  mirror (conftest stub) also lives in test_main_bootstrap.py.
"""

import gc
import importlib.util
import os
import sys
import threading
import time
import types
import warnings

import pytest

# DAQ channel-release delay: unique names and a short retry avoid -50103
# "resource is reserved" spurious failures under rapid Task creation.
_DAQ_RETRY_DELAY_S = 0.2
_DAQ_RETRY_COUNT = 3


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


# Probed once at import: the mark decorators below are evaluated at
# collection time, before fixtures run.
_REAL_NIDAQMX = _real_nidaqmx_available()

# Per-test gating: only the legs that need the real NI-DAQmx driver carry
# this mark. The patch-absence assertion carries no mark of its own —
# though every test under test/hal/rig/ is still collection-skipped on a
# dev machine by the conftest hook (the directory name puts "rig" in
# item.keywords); the dev-side coverage lives in test_main_bootstrap.py.
_RIG_ONLY = pytest.mark.skipif(
    not _REAL_NIDAQMX,
    reason="rig-only: requires the real NI-DAQmx driver runtime",
)


def _laser_terminals() -> str:
    import configparser

    cfg = configparser.ConfigParser()
    cfg.optionxform = str  # ty: ignore[invalid-assignment]
    cfg.read("config.ini")
    return cfg["Lasers"]["Lasers Terminals"]


def test_task_del_patch_absent() -> None:
    """The nidaqmx Task.__del__ bound to the consumer module carries no
    lightsheet provenance.

    Under the dev stub, Task defines no ``__del__`` at all (``object`` has
    none) — unpatched by construction. On the rig, it is nidaqmx's own
    method. Either way the attribute must not resolve to lightsheet code.
    """
    import lightsheet.hal.real.daqlaser as daqlaser_mod

    task_cls = daqlaser_mod.nidaqmx.Task
    del_attr = getattr(task_cls, "__del__", None)
    if del_attr is None:
        return  # stub Task has no __del__ — unpatched by construction
    qualname = getattr(del_attr, "__qualname__", "")
    module = getattr(del_attr, "__module__", "") or ""
    assert "_safe_task_del" not in qualname
    assert not module.startswith("lightsheet"), (
        "nidaqmx.Task.__del__ resolves to lightsheet code "
        f"({module}.{qualname}) — a monkeypatch is still applied"
    )


@_RIG_ONLY
def test_laser_write_task_del_unpatched_nonzero() -> None:
    """Laser write at nonzero V with NO __del__ patch applied — the
    post-removal contract. 20x create/close + gc.collect() churn must
    stay clean. Gated on RIG_LASER_VOLTAGE for the write amplitude."""
    import nidaqmx
    import numpy as np

    voltage = float(os.environ.get("RIG_LASER_VOLTAGE", "0"))

    errors = []
    for i in range(20):
        for attempt in range(_DAQ_RETRY_COUNT):
            try:
                task_name = f"laser_unpatched_{i}_{attempt}"
                with nidaqmx.Task(new_task_name=task_name) as task:
                    task.ao_channels.add_ao_voltage_chan(_laser_terminals())
                    task.write(
                        np.stack((np.array([voltage]), np.array([0.0]))),
                        auto_start=True,
                    )
                break
            except BaseException as e:
                if "-50103" in repr(e) and attempt < _DAQ_RETRY_COUNT - 1:
                    time.sleep(_DAQ_RETRY_DELAY_S)
                    continue
                errors.append((f"iter_{i}", repr(e)))
                break
        if errors:
            break
        # Force GC so __del__ runs on the just-closed Task while the next
        # iteration creates a new one.
        gc.collect()

    assert not errors, (
        "Laser write crashed with no __del__ patch applied:\n"
        + "\n".join(f"{t}: {e}" for t, e in errors)
    )


@_RIG_ONLY
def test_laser_write_del_unpatched_daemon_thread_nonzero() -> None:
    """Laser write on a daemon thread with no __del__ patch — mirrors the
    GUI's _toggle_laser1 daemon-thread path. Gated on RIG_LASER_VOLTAGE."""
    import nidaqmx
    import numpy as np

    voltage = float(os.environ.get("RIG_LASER_VOLTAGE", "0"))

    errors = []
    done = threading.Event()

    def worker() -> None:
        try:
            for i in range(10):
                for attempt in range(_DAQ_RETRY_COUNT):
                    try:
                        task_name = f"laser_daemon_{i}_{attempt}"
                        with nidaqmx.Task(new_task_name=task_name) as task:
                            task.ao_channels.add_ao_voltage_chan(_laser_terminals())
                            task.write(
                                np.stack((np.array([voltage]), np.array([0.0]))),
                                auto_start=True,
                            )
                        break
                    except BaseException as e:
                        if "-50103" in repr(e) and attempt < _DAQ_RETRY_COUNT - 1:
                            time.sleep(_DAQ_RETRY_DELAY_S)
                            continue
                        errors.append(("worker", repr(e)))
                        break
                if errors:
                    break
                gc.collect()
        except BaseException as e:
            errors.append(("worker", repr(e)))
        done.set()

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    done.wait(timeout=20)
    t.join(timeout=5)
    assert not errors, (
        "Daemon-thread laser write crashed with no __del__ patch:\n"
        + "\n".join(f"{t}: {e}" for t, e in errors)
    )


@_RIG_ONLY
def test_partially_constructed_task_del_is_quiet() -> None:
    """A Task whose __init__ fails mid-construction GCs silently.

    A mismatched gRPC session name raises DaqError AFTER nidaqmx 1.6.0
    has initialized every field __del__ reads — the exact
    partial-construction shape the removed 0.6.x guard existed for.
    A __del__ AttributeError does not surface through the warnings
    machinery, so unraisable exceptions are captured via
    sys.unraisablehook for the duration of the collect.
    """
    import nidaqmx
    from nidaqmx.errors import DaqError

    unraisable: list[sys.UnraisableHookArgs] = []
    orig_unraisable = sys.unraisablehook
    sys.unraisablehook = unraisable.append
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            with pytest.raises(DaqError):
                nidaqmx.Task(
                    new_task_name="partial_construction_probe",
                    grpc_options=types.SimpleNamespace(session_name="mismatched"),
                )
            # The half-built object is out of scope; force GC so __del__
            # runs now rather than at interpreter teardown. __del__ sees
            # _handle=None and an empty _event_handlers -> no warning.
            gc.collect()
    finally:
        sys.unraisablehook = orig_unraisable
    assert not unraisable, (
        "GC of a partially-constructed Task raised in __del__: "
        + "; ".join(repr(u.exc_value) for u in unraisable)
    )
    assert not caught, (
        "GC of a partially-constructed Task emitted warnings: "
        + "; ".join(str(w.message) for w in caught)
    )
