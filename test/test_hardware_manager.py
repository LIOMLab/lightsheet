"""HardwareManager extraction tests (god-object split).

``HardwareManager`` is a plain-Python collaborator that owns the laser
write/toggle daemon threads, the per-laser RLock-guarded write paths,
both status-poll methods, and ``start_lasers``/``stop_lasers`` — but does
NOT own an ``estop()``/kill-path method of any kind (safety anti-pattern,
the pitfall). The E-stop kill path (``updateUi_estop_pressed``) stays in
the thin shell with a direct ``list[ILaser]`` ref, lock-free, on the GUI
thread.

Behavior covered (per the plan's ``<behavior>`` block):

1. ``HardwareManager(bundle, shell).start_lasers()`` with
   ``shell._auto_laser1 = True`` calls ``.set_power(...)`` then ``.on()``
   on ``bundle.lasers[0]`` (a Mock ILaser), mirroring the pre-extraction
   ``start_lasers`` behavior exactly.
2. ``hw._toggle_laser1()`` with ``shell.estop_event.is_set() -> True``
   returns immediately without calling ``.on()``/``.off()`` on
   ``bundle.lasers[0]`` — the E-stop cooperative-skip survives the
   extraction.
3. (regression) ``HardwareManager`` has NO ``estop`` method
   (``hasattr(HardwareManager, "estop")`` is False); the shell's
   ``updateUi_estop_pressed`` still calls ``laser.off()`` directly on
   ``self.lasers`` (a plain list, not routed through ``self._hw``) with
   no ``threading.Thread``/``QTimer.singleShot``/queue in its body.
"""

from __future__ import annotations

import os
import re
import threading
from collections.abc import Callable
from typing import Any
from unittest.mock import Mock

from lightsheet.gui.hardware_manager import HardwareManager
from lightsheet.hal import DeviceBundle, MockCamera, MockETLs, MockLaser, MockMotors, MockSigGen

_CONTROLLER_SRC = os.path.join(
    os.path.dirname(__file__), "..", "lightsheet", "gui", "controller.py"
)


def _read_controller_source() -> str:
    with open(_CONTROLLER_SRC) as f:
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


def _load_method(method_sig: str) -> Callable[..., Any]:
    """Extract a method body from lightsheet/gui/controller.py and return a
    callable that executes the real source (the established no-Qt exec
    pattern, see test_laser_controls.py / test_demo_factory.py)."""
    src = _read_controller_source()
    body = _slice_method(src, method_sig)
    namespace: dict[str, Any] = {}
    exec(compile(body, _CONTROLLER_SRC, "exec"), namespace)
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


def _make_shell(bundle: DeviceBundle) -> Mock:
    """Build a Mock stand-in shell exposing the attributes HardwareManager
    reads off the shell reference: ``sig_message``, ``_auto_laser1``,
    ``_auto_laser2``, ``laser1_power_pct``, ``laser2_power_pct``,
    ``estop_event``."""
    shell = Mock()
    shell.sig_message = Mock()
    shell._auto_laser1 = False
    shell._auto_laser2 = False
    shell.laser1_power_pct = 0.0
    shell.laser2_power_pct = 0.0
    shell.estop_event = threading.Event()
    return shell


# --------------------------------------------------------------------------- #
# Test 1 — start_lasers drives the auto-selected lasers via the bundle.
# --------------------------------------------------------------------------- #


def test_start_lasers_drives_auto_laser1_via_bundle() -> None:
    """HardwareManager(bundle, shell).start_lasers() with
    shell._auto_laser1 = True calls .set_power(mw) then .on() on
    bundle.lasers[0] — mirroring the pre-extraction start_lasers behavior
    exactly (set_power before on so the DAQ backend writes the staged
    power when it energizes the AO channel)."""
    bundle = _make_bundle()
    shell = _make_shell(bundle)
    shell._auto_laser1 = True
    shell._auto_laser2 = False
    shell.laser1_power_pct = 50.0
    hw = HardwareManager(bundle, shell)

    # Substitute Mock lasers so the calls are observable. The bundle's
    # lasers are MockLaser instances; swap them for plain Mocks with the
    # attributes start_lasers reads (.max_power, .error, .error_message,
    # .label, .set_power, .on, .get_output_power, .power, .active).
    laser1 = Mock()
    laser1.max_power = 300.0
    laser1.error = 0
    laser1.error_message = ""
    laser1.label = "Laser 1 (555 nm)"
    laser1._lock = threading.RLock()
    laser1.active = False
    laser1.power = 0.0
    laser1.get_output_power = Mock(return_value=0.0)
    laser2 = Mock()
    laser2._lock = threading.RLock()
    laser2.error = 0
    laser2.power = 0.0
    laser2.get_output_power = Mock(return_value=0.0)
    hw.lasers = [laser1, laser2]

    hw.start_lasers()

    # 50 % of 300 mW = 150 mW, staged before .on().
    laser1.set_power.assert_called_once_with(150.0)
    laser1.on.assert_called_once()


# --------------------------------------------------------------------------- #
# Test 2 — _toggle_laser1 cooperative-skip on E-stop survives the extraction.
# --------------------------------------------------------------------------- #


def test_toggle_laser1_skips_when_estop_set() -> None:
    """hw._toggle_laser1() with shell.estop_event.is_set() -> True returns
    immediately without calling .on()/.off() on bundle.lasers[0] — the
    E-stop cooperative-skip survives the extraction (the E-stop cooperative-skip mitigation)."""
    bundle = _make_bundle()
    shell = _make_shell(bundle)
    shell.estop_event.set()
    shell.laser1_power_pct = 50.0
    hw = HardwareManager(bundle, shell)

    laser1 = Mock()
    laser1.max_power = 300.0
    laser1.error = 0
    laser1.error_message = ""
    laser1.label = "Laser 1 (555 nm)"
    laser1._lock = threading.RLock()
    laser1.active = False
    hw.lasers = [laser1, Mock()]

    hw._toggle_laser1()

    laser1.on.assert_not_called()
    laser1.off.assert_not_called()


# --------------------------------------------------------------------------- #
# Test 3 — regression: no HardwareManager.estop; shell kill path
# stays direct + lock-free.
# --------------------------------------------------------------------------- #


def test_hardware_manager_has_no_estop_method() -> None:
    """HardwareManager must NOT declare an estop/kill/e_stop method — the
    E-stop kill path stays in the shell (safety anti-pattern check).
    A future maintainer who sees HardwareManager.estop() will be tempted to
    queue/thread it — the single most safety-critical regression risk."""
    assert not hasattr(HardwareManager, "estop"), (
        "HardwareManager must NOT declare an estop method (safety anti-pattern)"
    )
    assert not hasattr(HardwareManager, "kill"), (
        "HardwareManager must NOT declare a kill method"
    )
    assert not hasattr(HardwareManager, "e_stop"), (
        "HardwareManager must NOT declare an e_stop method"
    )


def test_shell_estop_pressed_calls_laser_off_directly_not_via_hw() -> None:
    """The shell's updateUi_estop_pressed must still call laser.off()
    directly on self.lasers (a plain list, not routed through self._hw)
    with no threading.Thread / QTimer.singleShot / queue in its body —
    the kill path is lock-free and synchronous on the GUI thread
    (AGENTS.md §2). Asserted via the _load_method exec pattern on the
    real shell method body (AGENTS.md §5 — not a static-source grep)."""
    updateUi_estop_pressed = _load_method(
        "updateUi_estop_pressed(self) -> None"
    )
    src = _read_controller_source()
    body = _slice_method(src, "updateUi_estop_pressed(self) -> None")
    # The kill path must NOT offload through a thread/timer/queue, and must
    # NOT route the laser-off kill loop through HardwareManager (safety
    # anti-pattern). The refresh-after-action polls (self._hw._poll_laser_status
    # / self._hw._refresh_laser_readback) ARE allowed — they are not the
    # kill path, just status-label refreshes.
    forbidden = ["threading.Thread", "QTimer.singleShot", "queue.Queue", "self._hw.stop_lasers", "self._hw._toggle_laser", "self._hw._write_laser"]
    found = [p for p in forbidden if p in body]
    assert not found, (
        f"updateUi_estop_pressed must not offload the kill path through "
        f"HardwareManager write/toggle/stop — found forbidden patterns: {found}"
    )
    # The body must call laser.off() directly on self.lasers (the kill loop).
    assert "for laser in self.lasers" in body, (
        "updateUi_estop_pressed must iterate self.lasers directly (not self._hw)"
    )
    assert "laser.off()" in body, (
        "updateUi_estop_pressed must call laser.off() directly"
    )

    # Behavioral: run the real body against a Mock stand-in and confirm
    # both lasers' .off() is called synchronously.
    laser1 = Mock()
    laser1.error = 0
    laser1.error_message = ""
    laser1.label = "Laser 1 (555 nm)"
    laser2 = Mock()
    laser2.error = 0
    laser2.error_message = ""
    laser2.label = "Laser 2 (640 nm)"

    standin = Mock()
    standin.lasers = [laser1, laser2]
    standin.estop_event = threading.Event()
    standin.sig_message = Mock()
    # The refresh-after-action calls route through the shell's own poll
    # methods (Mocked here — the kill path itself is what matters).
    standin._poll_laser_status = Mock()
    standin._refresh_laser_readback = Mock()
    # Qt widget mutations land on Mock attrs (no-ops).
    standin.label_estopStatus = Mock()
    standin.pushButton_estop = Mock()

    updateUi_estop_pressed(standin)

    laser1.off.assert_called_once()
    laser2.off.assert_called_once()


# --------------------------------------------------------------------------- #
# Test 4 — open_laser2 drives the iBeam serial open + surfaces channel-
# enable failure via sig_message; __init__ does NOT call .open() (regression
# gate proving the composition root stays non-blocking).
# --------------------------------------------------------------------------- #


def test_open_laser2_calls_open_on_laser2_and_surfaces_error() -> None:
    """HardwareManager.open_laser2() calls .open() on self.lasers[1] and,
    when .error is set afterward (channel-enable failure caught inside
    enable_channel()), emits sig_message on the shell with the error
    message and clears the error flag — mirroring the pre-extraction
    hardware_init inline block verbatim."""
    bundle = _make_bundle()
    shell = _make_shell(bundle)
    hw = HardwareManager(bundle, shell)

    laser2 = Mock()
    laser2.error = 1
    laser2.error_message = "enable_channel rejected: %SYS-E"
    laser2._lock = threading.RLock()
    hw.lasers = [Mock(), laser2]

    hw.open_laser2()

    laser2.open.assert_called_once()
    shell.sig_message.emit.assert_called_once()
    args, _ = shell.sig_message.emit.call_args
    assert "iBeam opened but channel enable failed" in args[0]
    assert "enable_channel rejected: %SYS-E" in args[0]
    assert laser2.error == 0


def test_open_laser2_surfaces_open_exception_via_sig_message() -> None:
    """If self.lasers[1].open() raises, open_laser2() catches it and emits
    sig_message with the exception text — the operator is told the red
    laser is unavailable, but the failure is non-fatal (no re-raise)."""
    bundle = _make_bundle()
    shell = _make_shell(bundle)
    hw = HardwareManager(bundle, shell)

    laser2 = Mock()
    laser2.open.side_effect = OSError("COM4 not available")
    laser2._lock = threading.RLock()
    hw.lasers = [Mock(), laser2]

    # Must not raise — failure is non-fatal.
    hw.open_laser2()

    laser2.open.assert_called_once()
    shell.sig_message.emit.assert_called_once()
    args, _ = shell.sig_message.emit.call_args
    assert "iBeam open failed" in args[0]
    assert "COM4 not available" in args[0]


def test_hardware_manager_init_does_not_call_open_on_laser2() -> None:
    """Regression gate: constructing HardwareManager(bundle, shell) must
    NOT call .open() on bundle.lasers[1]. __init__ runs synchronously in
    main()'s composition root BEFORE controller.show() — calling the iBeam
    serial open there would block the GUI window on the serial round-trip
    (a startup-latency regression). The open is driven post-show from
    hardware_init via open_laser2()."""
    bundle = _make_bundle()
    # Replace the bundle's laser 2 with a Mock whose .open() is observable.
    laser1 = Mock()
    laser1._lock = threading.RLock()
    laser2 = Mock()
    laser2._lock = threading.RLock()
    bundle = DeviceBundle(
        camera=bundle.camera,
        siggen=bundle.siggen,
        motors=bundle.motors,
        etls=bundle.etls,
        lasers=(laser1, laser2),
    )
    shell = _make_shell(bundle)

    hw = HardwareManager(bundle, shell)

    # __init__ must not have triggered any HAL lifecycle call on laser 2.
    laser2.open.assert_not_called()
    laser2.on.assert_not_called()
    laser2.set_power.assert_not_called()
    # Sanity: the manager did take a lasers reference (so the test isn't
    # trivially passing because the attribute was never assigned).
    assert hw.lasers[1] is laser2
