"""AcquisitionCoordinator extraction tests (god-object split).

``AcquisitionCoordinator`` is a plain-Python collaborator that owns the
four acquisition worker bodies (``preview_mode_worker``,
``live_mode_worker``, ``single_mode_worker``, ``stack_mode_worker``) plus
``acquire_scan``. The shell delegates through ``self._acq``. The
coordinator reads shell-owned state (``sig_message``, ``estop_event``,
``<mode>_mode_started`` flags, ``_fs``, ``ui.*`` widgets) via an injected
``self._shell`` reference and reads its own ``self.camera`` /
``self.siggen`` / ``self.motors`` / ``self._hw`` attributes.

Behavior covered (per the plan's ``<behavior>`` block):

1. ``AcquisitionCoordinator(bundle, hw, shell)`` exposes the five methods
   as callable attributes.
2. The golden-master replay (``default.json`` + ``siggen_create_scanner_fail.json``)
   is unchanged after the extraction — verified by the existing replay
   tests in ``test_golden_acquisition.py`` passing without regenerating
   the fixtures.
3. The preview-auto-laser fold: ``preview_mode_worker`` calls
   ``self._hw.start_lasers()`` after ``camera.arm()`` and
   ``self._hw.stop_lasers()`` before ``camera.disarm()``, mirroring
   ``live_mode_worker``'s shape.
4. ``updateUi_preview_mode_button`` calls
   ``self._cache_auto_laser_flags()`` before spawning the preview thread,
   mirroring ``updateUi_single_mode_button``.
"""

from __future__ import annotations

import datetime
import logging
import os
import re
import threading
from collections.abc import Callable
from typing import Any
from unittest.mock import Mock

import numpy as np

from lightsheet.gui.acquisition_coordinator import AcquisitionCoordinator
from lightsheet.hal import DeviceBundle, MockCamera, MockETLs, MockLaser, MockMotors, MockSigGen

_CONTROLLER_SRC = os.path.join(
    os.path.dirname(__file__), "..", "lightsheet", "gui", "controller.py"
)
_ACQ_SRC = os.path.join(
    os.path.dirname(__file__), "..", "lightsheet", "gui", "acquisition_coordinator.py"
)


def _read_source(path: str) -> str:
    with open(path) as f:
        return f.read()


def _slice_method(src: str, method_sig: str) -> str:
    """Return the body of a method, from its `def <sig>:` line up to the
    next top-level def/@pyqtSlot decorator."""
    m = re.search(r"def " + re.escape(method_sig) + r":", src)
    assert m, f"{method_sig} is missing"
    body = src[m.start() :]
    end = re.search(r"\n    def |\n    @pyqtSlot", body[1:])
    if end:
        body = body[: end.start() + 1]
    return body


def _load_method(method_sig: str, src_path: str = _ACQ_SRC) -> Callable[..., Any]:
    """Extract a method body from the given source file and return a
    callable that executes the real source (the established no-Qt exec
    pattern, see test_laser_controls.py / test_controller_behavior.py).
    Seeds the exec namespace with the module-level names the body
    references (``datetime``, ``logger``, ``np``, ``threading``)."""
    src = _read_source(src_path)
    body = _slice_method(src, method_sig)
    namespace: dict[str, Any] = {
        "datetime": datetime,
        "logger": logging.getLogger("test_acquisition_coordinator"),
        "np": np,
        "threading": threading,
    }
    exec(compile(body, src_path, "exec"), namespace)
    func_name = method_sig.split("(")[0].strip()
    return namespace[func_name]


def _make_bundle() -> DeviceBundle:
    """Build a demo DeviceBundle with two MockLaser instances."""
    camera = MockCamera(verbose=True)
    siggen = MockSigGen(camera)
    motors = MockMotors()
    lasers = (
        MockLaser(wavelength=555, max_power_mw=300.0, label="Laser 1 (555 nm)"),
        MockLaser(wavelength=640, max_power_mw=150.0, label="Laser 2 (640 nm)"),
    )
    etls = MockETLs()
    return DeviceBundle(camera=camera, siggen=siggen, motors=motors, etls=etls, lasers=lasers)


def test_acquisition_coordinator_exposes_five_worker_methods() -> None:
    """AcquisitionCoordinator(bundle, hw, shell) constructed with Mock
    bundle/hw/shell exposes single_mode_worker, live_mode_worker,
    stack_mode_worker, preview_mode_worker, acquire_scan as callable
    methods."""
    bundle = _make_bundle()
    hw = Mock()
    shell = Mock()
    acq = AcquisitionCoordinator(bundle, hw, shell)

    for name in (
        "single_mode_worker",
        "live_mode_worker",
        "stack_mode_worker",
        "preview_mode_worker",
        "acquire_scan",
    ):
        method = getattr(acq, name, None)
        assert callable(method), (
            f"AcquisitionCoordinator must expose {name} as a callable method "
            f"(got {method!r})"
        )


def test_acquisition_coordinator_stores_bundle_handles_and_collaborators() -> None:
    """The coordinator stores the bundle's HAL handles as its own
    attributes (self.camera / self.siggen / self.motors) and the hw +
    shell references for delegation."""
    bundle = _make_bundle()
    hw = Mock()
    shell = Mock()
    acq = AcquisitionCoordinator(bundle, hw, shell)

    assert acq.camera is bundle.camera
    assert acq.siggen is bundle.siggen
    assert acq.motors is bundle.motors
    assert acq._hw is hw
    assert acq._shell is shell


# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
# Preview-auto-laser fold.
# --------------------------------------------------------------------------- #


def test_preview_mode_worker_calls_start_lasers_after_arm_and_stop_before_disarm() -> None:
    """preview_mode_worker now calls self._hw.start_lasers()
    immediately after self.camera.arm() (before the while loop) and
    self._hw.stop_lasers() immediately before self.camera.disarm() —
    mirroring live_mode_worker's existing shape. Verified by running the
    real extracted body against a Mock stand-in and asserting the
    call order via a shared call log."""
    preview_mode_worker = _load_method("preview_mode_worker(self) -> None")

    call_log: list[str] = []
    estop_event = threading.Event()
    # Set estop so the while loop breaks immediately after start_lasers —
    # we only need to observe the arm -> start_lasers ordering and the
    # stop_lasers -> disarm ordering in the cleanup tail.
    estop_event.set()

    camera = Mock()
    camera.arm.side_effect = lambda: call_log.append("camera.arm")
    camera.disarm.side_effect = lambda: call_log.append("camera.disarm")
    # set_trigger_mode / set_exposure_time are called before arm; no-ops.
    camera.set_trigger_mode = Mock()
    camera.set_exposure_time = Mock()

    hw = Mock()
    hw.start_lasers.side_effect = lambda: call_log.append("hw.start_lasers")
    hw.stop_lasers.side_effect = lambda: call_log.append("hw.stop_lasers")

    shell = Mock()
    shell.estop_event = estop_event
    shell.preview_mode_started = True
    shell.ui = Mock()
    # doubleSpinBox_cameraExposureTime.value() is wrapped in int() before
    # being passed to camera.set_exposure_time — must return a real int.
    shell.ui.doubleSpinBox_cameraExposureTime.value.return_value = 100
    shell._fs = Mock()
    shell.sig_message = Mock()
    shell.sig_preview_mode_finished = Mock()

    standin = Mock()
    standin.camera = camera
    standin._hw = hw
    standin._shell = shell

    preview_mode_worker(standin)

    # start_lasers called after camera.arm.
    assert "camera.arm" in call_log, "camera.arm must be called"
    assert "hw.start_lasers" in call_log, "hw.start_lasers must be called (start_lasers)"
    assert call_log.index("camera.arm") < call_log.index("hw.start_lasers"), (
        "start_lasers: start_lasers must come AFTER camera.arm"
    )
    # stop_lasers called before camera.disarm.
    assert "hw.stop_lasers" in call_log, "hw.stop_lasers must be called (start_lasers)"
    assert "camera.disarm" in call_log, "camera.disarm must be called"
    assert call_log.index("hw.stop_lasers") < call_log.index("camera.disarm"), (
        "start_lasers: stop_lasers must come BEFORE camera.disarm"
    )


def test_updateUi_preview_mode_button_caches_auto_laser_flags_before_thread_spawn() -> None:
    """updateUi_preview_mode_button: updateUi_preview_mode_button must call
    self._cache_auto_laser_flags() before spawning the preview worker
    thread, mirroring updateUi_single_mode_button. Verified by running
    the real extracted body (it stays on the shell, reading self.ui.*)
    via the _load_method exec pattern against a Mock standin whose
    _cache_auto_laser_flags records the call, and asserting the cache
    call happens before the thread spawn."""
    updateUi_preview_mode_button = _load_method(
        "updateUi_preview_mode_button(self) -> None", src_path=_CONTROLLER_SRC
    )

    call_log: list[str] = []
    standin = Mock()
    standin.preview_mode_started = False  # the else: branch (start path)
    standin.ui = Mock()
    # close_modes is called on the start path; mock it to record + no-op.
    standin.close_modes = Mock(side_effect=lambda: call_log.append("close_modes"))
    # _cache_auto_laser_flags records the call.
    standin._cache_auto_laser_flags = Mock(
        side_effect=lambda: call_log.append("_cache_auto_laser_flags")
    )
    # updateUi_modes_buttons / updateUi_message_printer are no-ops.
    standin.updateUi_modes_buttons = Mock()
    standin.updateUi_message_printer = Mock()
    # Capture the thread spawn via patching threading.Thread so no real
    # thread is started. Record the target to confirm it points at the
    # coordinator's preview_mode_worker.
    spawned_targets: list = []

    class _FakeThread:
        def __init__(self, target=None, args=(), kwargs=None) -> None:
            spawned_targets.append(target)
            call_log.append("thread_spawn")

        def start(self) -> None:
            pass

    # Inject the fake Thread into the exec namespace. The extracted body
    # references `threading.Thread` — patch via the namespace globals.
    src = _read_source(_CONTROLLER_SRC)
    body = _slice_method(src, "updateUi_preview_mode_button(self) -> None")
    namespace: dict[str, Any] = {"threading": Mock(Thread=_FakeThread)}
    exec(compile(body, _CONTROLLER_SRC, "exec"), namespace)
    updateUi_preview_mode_button = namespace["updateUi_preview_mode_button"]

    updateUi_preview_mode_button(standin)

    assert "_cache_auto_laser_flags" in call_log, (
        "updateUi_preview_mode_button: updateUi_preview_mode_button must call "
        "_cache_auto_laser_flags before spawning the preview thread"
    )
    assert "thread_spawn" in call_log, "the preview thread must be spawned"
    assert call_log.index("_cache_auto_laser_flags") < call_log.index("thread_spawn"), (
        "cache-flags: _cache_auto_laser_flags must be called BEFORE the thread spawn"
    )

