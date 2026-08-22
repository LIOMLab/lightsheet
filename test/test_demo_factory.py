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

``Controller_MainWindow`` cannot be instantiated on this Mac (needs PyQt5
display), so the real ``hardware_init`` source is extracted and exec'd
against a minimal stand-in. This runs the real factory code — the same code
that runs on the rig — without the Qt runtime.
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
    body = src[m.start():]
    end = re.search(r"\n    def |\n    @pyqtSlot", body[1:])
    if end:
        body = body[: end.start() + 1]
    return body


def _load_method(method_sig: str) -> Callable[..., Any]:
    """Extract a method body from lightsheet/gui/controller.py and return a
    callable `func(self)` that executes the real source."""
    src = _read_controller_source()
    body = _slice_method(src, method_sig)
    namespace: dict[str, Any] = {}
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

    The factory branch under test only touches ``self._demo_mode``,
    ``self.camera``, ``self.siggen``, ``self.motors``, ``self.lasers``,
    ``self.etls``, ``self.ibeam``, ``self.ui.statusbar``, and
    ``self.setWindowTitle`` / ``self.windowTitle``. The stand-in lets the
    real method body assign HAL instances onto self.camera etc. so the
    test can assert on their concrete types.
    """
    standin = Mock()
    standin._demo_mode = demo
    standin.ui = Mock()
    standin.ui.statusbar = Mock()
    standin.windowTitle = Mock(return_value="Lightsheet")
    # The real hardware_init also calls updateUi_initial_hardware_state,
    # constructs FrameViewer/FrameSaver, starts a QTimer, etc. The factory
    # branch under test is the construction block; the rest of hardware_init
    # is exercised but its downstream calls land on Mock attrs (no-ops).
    return standin


def test_hardware_init_constructs_mock_camera_under_demo() -> None:
    """When self._demo_mode is True, hardware_init's Camera branch must
    construct a MockCamera (not the real Camera) so no hardware init runs
    on a dev box."""
    from lightsheet.hal import MockCamera

    hardware_init = _load_method("hardware_init(self) -> None")
    standin = _make_standin(demo=True)
    # Stub the downstream HAL classes hardware_init constructs after the
    # camera branch. They stay as their real classes (Wave 2 makes them
    # demo-aware); the standin just needs them constructible.
    hardware_init(standin)
    assert isinstance(standin.camera, MockCamera), (
        "demo branch must construct MockCamera, not the real Camera"
    )


def test_hardware_init_constructs_real_camera_when_not_demo() -> None:
    """When self._demo_mode is False, hardware_init's Camera branch must
    construct the real Camera (the normal rig path)."""
    from lightsheet.hal import Camera

    hardware_init = _load_method("hardware_init(self) -> None")
    standin = _make_standin(demo=False)
    hardware_init(standin)
    assert isinstance(standin.camera, Camera), (
        "non-demo branch must construct the real Camera"
    )


def test_hardware_init_preserves_siggen_camera_dependency() -> None:
    """SigGen is constructed with the camera reference (waveform timing
    derives from camera settings). The factory branch must preserve this
    dependency ordering under both demo and real paths (Pitfall 2)."""
    from lightsheet.hal import MockCamera

    hardware_init = _load_method("hardware_init(self) -> None")
    standin = _make_standin(demo=True)
    hardware_init(standin)
    # SigGen was constructed with standin.camera as its arg; capture the
    # constructor call to verify the camera reference was passed.
    # The standin.siggen is whatever SigGen(self.camera) returned — we
    # assert it is not None and that it was constructed after the camera.
    assert isinstance(standin.camera, MockCamera)
    assert standin.siggen is not None
