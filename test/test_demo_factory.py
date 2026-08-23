"""
Demo-mode factory tests for the Phase 3 tracer slice.

Covers two concerns:

1. ``_resolve_demo(cli_demo, env)`` — the pure flag-resolution helper in
   ``lightsheet.__main__`` that merges the ``--demo`` CLI flag and the
   ``LIGHTSHEET_DEMO`` env var with CLI-overrides-env precedence (D-10).

2. The ``hardware_init`` Camera factory branch — extracted from
   ``lightsheet/gui/controller.py`` and exec'd against a ``Mock`` stand-in
   ``self`` (the established no-Qt pattern, see ``test_laser_controls.py``).
   Asserts the demo branch constructs ``MockCamera`` and the real branch
   constructs ``Camera``, and that ``SigGen`` receives the camera reference
   (dependency ordering preserved, Pitfall 2).

``Controller_MainWindow`` cannot be instantiated on this Mac (needs a PyQt5
display), so the real ``hardware_init`` source is extracted and exec'd
against a minimal stand-in. The exec namespace is seeded with the real
``lightsheet.gui.controller`` module globals (``QApplication``, ``Qt``,
``FrameViewer``, ``FrameSaver``, ``QTimer``, the HAL classes) so the method
body's module-level name lookups resolve. This runs the real factory code —
the same code that runs on the rig — without instantiating the Qt window.
"""

import os
import re
from collections.abc import Callable
from typing import Any
from unittest.mock import Mock

from lightsheet.__main__ import _resolve_demo

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
    callable `func(self)` that executes the real source.

    The exec namespace is built manually rather than seeded from the
    controller module globals, because importing ``lightsheet.gui.controller``
    transitively imports ``lightsheet.siggen``, whose top-level
    ``from nidaqmx.constants import ...`` fails on this Mac (the conftest
    nidaqmx stub has no ``constants`` submodule). Instead we provide the
    module-level names the ``hardware_init`` body references: the real
    ``Camera`` (constructs fine on Mac — the pco failure is caught on the
    HAL error surface), and Mocks for the Qt classes and the other 5 HAL
    classes (which the factory branch constructs but whose real imports
    are not needed to assert on the Camera branch).
    """
    from lightsheet.config import cfg_read
    from lightsheet.hal import Camera

    src = _read_controller_source()
    body = _slice_method(src, method_sig)
    # Build the namespace with the module-level names hardware_init uses.
    # Qt classes and the non-Camera HAL classes are Mocked — the factory
    # branch under test only needs Camera (real) to be constructible so
    # the demo/real branch assignment can be asserted. MockCamera /
    # MockLaser / DAQLaser / IBeamSmartLaser are imported locally inside
    # the branches (`from lightsheet.hal import ...`), so they resolve at
    # runtime without being in the namespace. cfg_read is a module-level
    # import in controller.py and is referenced by the real branch to load
    # Laser 1 calibration from config.ini.
    namespace: dict[str, Any] = {
        "QApplication": Mock(),
        "Qt": Mock(),
        "QTimer": Mock(),
        "FrameViewer": Mock(),
        "FrameSaver": Mock(),
        "SigGen": Mock(),
        "Motors": Mock(),
        "ETLs": Mock(),
        "Camera": Camera,
        "cfg_read": cfg_read,
    }
    exec(compile(body, _CONTROLLER_SRC, "exec"), namespace)
    func_name = method_sig.split("(")[0].strip()
    return namespace[func_name]


# --------------------------------------------------------------------------- #
# _resolve_demo: CLI-overrides-env precedence (D-10).
# --------------------------------------------------------------------------- #


def test_resolve_demo_cli_true_env_unset() -> None:
    """--demo CLI flag True with env unset -> demo active."""
    assert _resolve_demo(cli_demo=True, env=None) is True


def test_resolve_demo_cli_false_env_one() -> None:
    """CLI False + LIGHTSHEET_DEMO=1 -> demo active (env opt-in)."""
    assert _resolve_demo(cli_demo=False, env="1") is True


def test_resolve_demo_cli_false_env_unset() -> None:
    """CLI False + env unset/0 -> demo inactive (normal rig run)."""
    assert _resolve_demo(cli_demo=False, env=None) is False
    assert _resolve_demo(cli_demo=False, env="0") is False


def test_resolve_demo_cli_true_overrides_env_zero() -> None:
    """CLI True overrides env "0" — --demo wins over LIGHTSHEET_DEMO=0."""
    assert _resolve_demo(cli_demo=True, env="0") is True


# --------------------------------------------------------------------------- #
# hardware_init Camera factory branch — exec the real method body against a
# Mock stand-in self. Asserts the demo branch constructs MockCamera, the
# real branch constructs Camera, and SigGen receives the camera reference.
# --------------------------------------------------------------------------- #


def _make_standin(demo: bool) -> Mock:
    """Build a Mock stand-in self with the attributes hardware_init reads.

    The factory branch under test touches ``self._demo_mode``,
    ``self.camera``, ``self.siggen``, ``self.motors``, ``self.lasers``,
    ``self.etls``, ``self.ibeam``, ``self.ui.statusbar``,
    ``self.setWindowTitle`` / ``self.windowTitle``,
    ``self.updateUi_initial_hardware_state``, ``self.frame_viewer``,
    ``self.frame_saver``, ``self.timer_imageview``. The stand-in lets the
    real method body assign HAL instances onto self.camera etc. so the
    test can assert on their concrete types; downstream Qt calls land on
    Mock attrs (no-ops).
    """
    standin = Mock()
    standin._demo_mode = demo
    standin.ui = Mock()
    standin.ui.statusbar = Mock()
    standin.windowTitle = Mock(return_value="Lightsheet")
    return standin


def test_hardware_init_assigns_mock_camera_from_bundle_under_demo() -> None:
    """When self._demo_mode is True (bundle built from Mock* by
    _build_demo_bundle), hardware_init assigns the bundle's MockCamera
    onto self.camera — no hardware init runs on a dev box."""
    from lightsheet.hal import MockCamera

    hardware_init = _load_method("hardware_init(self) -> None")
    standin = _make_bundle_standin(demo=True)
    hardware_init(standin)
    assert isinstance(standin.camera, MockCamera), (
        "demo bundle's camera must be a MockCamera"
    )
    assert standin.camera is standin._bundle.camera, (
        "hardware_init must assign from the bundle, not construct"
    )


def test_hardware_init_preserves_siggen_camera_dependency() -> None:
    """The bundle's SigGen was constructed with the bundle's camera
    reference (waveform timing derives from camera settings). After
    hardware_init assigns from the bundle, the dependency is preserved
    by identity (Pitfall 2)."""
    hardware_init = _load_method("hardware_init(self) -> None")
    standin = _make_bundle_standin(demo=True)
    hardware_init(standin)
    assert standin.siggen is standin._bundle.siggen
    assert standin.camera is standin._bundle.camera


def test_hardware_init_demo_indicator_emitted_via_statusbar_not_sigmessage() -> None:
    """Under demo mode the indicator (window-title suffix + status-bar
    message) must go through QStatusBar.showMessage directly, NOT via
    sig_message.emit, so it does not pollute the future golden-master
    sig_message sequence (UI-SPEC)."""
    hardware_init = _load_method("hardware_init(self) -> None")
    standin = _make_bundle_standin(demo=True)
    hardware_init(standin)
    # The window-title suffix was set.
    standin.setWindowTitle.assert_called_once()
    title_arg = standin.setWindowTitle.call_args.args[0]
    assert "[DEMO]" in title_arg, "window-title must carry the [DEMO] suffix"
    # The demo status-bar message was emitted via showMessage (not
    # sig_message.emit).
    statusbar_calls = [str(c) for c in standin.ui.statusbar.showMessage.call_args_list]
    assert any("Demo mode" in c for c in statusbar_calls), (
        "demo indicator must be emitted via statusbar.showMessage"
    )
    # sig_message.emit must not carry the demo indicator (UI-SPEC: keep
    # the golden-master sig_message sequence clean).
    for call in standin.sig_message.emit.call_args_list:
        assert "Demo mode" not in str(call), (
            "demo indicator must not be emitted via sig_message.emit"
        )


# --------------------------------------------------------------------------- #
# Bundle-consuming hardware_init — post-composition-root tests.
# After the main() composition root lands, hardware_init no longer branches
# on _demo_mode to construct HAL; it assigns from the injected DeviceBundle.
# --------------------------------------------------------------------------- #


def _make_bundle_standin(demo: bool) -> Mock:
    """Build a Mock stand-in self pre-populated with a DeviceBundle built
    from Mock* HAL stand-ins, matching the new bundle-consuming
    hardware_init contract."""
    from lightsheet.hal import (
        DeviceBundle,
        MockCamera,
        MockETLs,
        MockLaser,
        MockMotors,
        MockSigGen,
    )

    camera = MockCamera(verbose=True)
    siggen = MockSigGen(camera)
    motors = MockMotors()
    lasers = (
        MockLaser(
            wavelength=555,
            max_power_mw=300.0,
            mw_per_volt=60.0,
            label="Laser 1 (555 nm)",
        ),
        MockLaser(
            wavelength=640,
            max_power_mw=150.0,
            label="Laser 2 (640 nm)",
        ),
    )
    etls = MockETLs()
    bundle = DeviceBundle(
        camera=camera,
        siggen=siggen,
        motors=motors,
        etls=etls,
        lasers=lasers,
    )

    standin = Mock()
    standin._demo_mode = demo
    standin._bundle = bundle
    standin._fs = Mock()
    standin._hw = Mock()
    standin.ui = Mock()
    standin.ui.statusbar = Mock()
    standin.windowTitle = Mock(return_value="Lightsheet")
    return standin


def test_hardware_init_assigns_from_bundle() -> None:
    """hardware_init must assign HAL handles from the injected bundle,
    not construct them itself. After execution, standin.camera IS
    standin._bundle.camera (identity, not a new instance)."""
    hardware_init = _load_method("hardware_init(self) -> None")
    standin = _make_bundle_standin(demo=True)
    hardware_init(standin)
    assert standin.camera is standin._bundle.camera, (
        "hardware_init must assign self.camera from the bundle, not construct"
    )
    assert standin.siggen is standin._bundle.siggen
    assert standin.motors is standin._bundle.motors
    assert standin.etls is standin._bundle.etls
    assert standin.lasers == list(standin._bundle.lasers), (
        "hardware_init must assign self.lasers as a list copy of the bundle tuple"
    )


def test_hardware_init_does_not_construct_hal_classes() -> None:
    """hardware_init must NOT import or construct MockCamera/Camera/SigGen/
    Motors/DAQLaser/IBeamSmartLaser/ETLs/Mock* — those constructions moved
    to main()'s _build_demo_bundle / DeviceRegistry. Asserts on the
    extracted method source text (the SAME body exec'd by the other tests,
    per AGENTS.md §5 — not a separate static-source grep)."""
    src = _read_controller_source()
    body = _slice_method(src, "hardware_init(self) -> None")
    forbidden = [
        "MockCamera(",
        "MockSigGen(",
        "MockMotors(",
        "MockLaser(",
        "MockETLs(",
        "Camera(",
        "SigGen(",
        "Motors(",
        "DAQLaser(",
        "IBeamSmartLaser(",
        "ETLs(",
        "from lightsheet.hal import",
    ]
    found = [p for p in forbidden if p in body]
    assert not found, (
        f"hardware_init must not construct or import HAL classes — "
        f"found forbidden patterns: {found}"
    )
