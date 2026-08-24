"""
Demo-mode factory tests for the Phase 3 tracer slice.

Covers two concerns:

1. ``_resolve_demo(cli_demo, env)`` — the pure flag-resolution helper in
   ``lightsheet.__main__`` that merges the ``--demo`` CLI flag and the
   ``LIGHTSHEET_DEMO`` env var with CLI-overrides-env precedence.

2. The ``hardware_init`` HAL-assignment branch — tested via real
   construction: ``make_controller`` builds the real
   ``Controller_MainWindow`` with a mock ``DeviceBundle`` (Laser 1 = 555 nm
   / 300 mW, Laser 2 = 640 nm / 150 mW, mock camera/siggen/motors/etls),
   wires all four collaborators, and calls ``hardware_init``. Asserts the
   demo branch assigns ``MockCamera`` from the bundle, that ``SigGen``
   receives the camera reference (dependency ordering preserved), and that
   the demo indicator is emitted via the status bar (not ``sig_message``).

The real controller is constructed via ``make_controller`` (see
``test/_helpers/controller_fixture.py``) — ``QT_QPA_PLATFORM=offscreen``
plus the conftest SDK stubs make real construction work on the Mac dev box,
producing genuine branch coverage that the exec pattern structurally cannot.
"""

from unittest.mock import Mock

from _helpers.controller_fixture import make_controller
from lightsheet.__main__ import _resolve_demo


# --------------------------------------------------------------------------- #
# _resolve_demo: CLI-overrides-env precedence.
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
# hardware_init HAL-assignment branch — tested via real construction.
# make_controller builds the real Controller_MainWindow with a mock
# DeviceBundle, wires all four collaborators, and calls hardware_init.
# Asserts the bundle's HAL handles are assigned onto the controller and
# the demo indicator is emitted via the status bar (not sig_message).
# --------------------------------------------------------------------------- #


def test_hardware_init_assigns_mock_camera_from_bundle_under_demo(
    qtbot, request
) -> None:
    """When demo=True (bundle built from Mock* by _build_demo_bundle),
    hardware_init assigns the bundle's MockCamera onto self.camera — no
    hardware init runs on a dev box. Verified via real construction."""
    from lightsheet.hal import MockCamera

    ctrl, bundle = make_controller(qtbot, request)
    assert isinstance(ctrl.camera, MockCamera), (
        "demo bundle's camera must be a MockCamera"
    )
    assert ctrl.camera is bundle.camera, (
        "hardware_init must assign from the bundle, not construct"
    )


def test_hardware_init_preserves_siggen_camera_dependency(
    qtbot, request
) -> None:
    """The bundle's SigGen was constructed with the bundle's camera
    reference (waveform timing derives from camera settings). After
    hardware_init assigns from the bundle, the dependency is preserved
    by identity. Verified via real construction."""
    ctrl, bundle = make_controller(qtbot, request)
    assert ctrl.siggen is bundle.siggen
    assert ctrl.camera is bundle.camera


def test_hardware_init_demo_indicator_emitted_via_statusbar_not_sigmessage(
    qtbot, request
) -> None:
    """Under demo mode the indicator (window-title suffix + status-bar
    message) must go through QStatusBar.showMessage directly, NOT via
    sig_message.emit, so it does not pollute the future golden-master
    sig_message sequence. Verified via real construction: re-run
    hardware_init with spies on both emission channels."""
    ctrl, _bundle = make_controller(qtbot, request)

    # hardware_init already ran during make_controller. To observe the
    # demo indicator routing, stop the existing timers, reset the window
    # title, set up spies on both channels, and re-run hardware_init.
    ctrl.timer_imageview.stop()
    ctrl.timer_laser2_status.stop()
    ctrl.setWindowTitle("Lightsheet")

    # Spy on statusbar.showMessage (replace with a Mock that records calls).
    statusbar_show = Mock()
    ctrl.ui.statusbar.showMessage = statusbar_show

    # Spy on sig_message.emit (connect a recorder slot).
    sig_messages: list[str] = []
    ctrl.sig_message.connect(lambda msg: sig_messages.append(msg))

    ctrl.hardware_init()

    # The window-title suffix was set.
    assert "[DEMO]" in ctrl.windowTitle(), (
        "window-title must carry the [DEMO] suffix"
    )
    # The demo status-bar message was emitted via showMessage (not
    # sig_message.emit).
    statusbar_calls = [str(c) for c in statusbar_show.call_args_list]
    assert any("Demo mode" in c for c in statusbar_calls), (
        "demo indicator must be emitted via statusbar.showMessage"
    )
    # sig_message.emit must not carry the demo indicator (keep the
    # golden-master sig_message sequence clean).
    assert not any("Demo mode" in msg for msg in sig_messages), (
        "demo indicator must not be emitted via sig_message.emit"
    )


# --------------------------------------------------------------------------- #
# Bundle-consuming hardware_init — post-composition-root tests.
# After the main() composition root lands, hardware_init no longer branches
# on _demo_mode to construct HAL; it assigns from the injected DeviceBundle.
# --------------------------------------------------------------------------- #


def test_hardware_init_assigns_from_bundle(qtbot, request) -> None:
    """hardware_init must assign HAL handles from the injected bundle,
    not construct them itself. After execution, ctrl.camera IS
    bundle.camera (identity, not a new instance). Verified via real
    construction."""
    ctrl, bundle = make_controller(qtbot, request)
    assert ctrl.camera is bundle.camera, (
        "hardware_init must assign self.camera from the bundle, not construct"
    )
    assert ctrl.siggen is bundle.siggen
    assert ctrl.motors is bundle.motors
    assert ctrl.etls is bundle.etls
    assert ctrl.lasers == list(bundle.lasers), (
        "hardware_init must assign self.lasers as a list copy of the bundle tuple"
    )


def test_hardware_init_does_not_construct_hal_classes(qtbot, request) -> None:
    """hardware_init must NOT import or construct MockCamera/Camera/SigGen/
    Motors/DAQLaser/IBeamSmartLaser/ETLs/Mock* — those constructions moved
    to main()'s _build_demo_bundle / DeviceRegistry. Verified via real
    construction: after hardware_init, every HAL handle on the controller
    IS the bundle's handle (identity) and each is a Mock* type — proving
    hardware_init assigned from the bundle rather than constructing a new
    instance."""
    from lightsheet.hal import MockCamera, MockETLs, MockLaser, MockMotors, MockSigGen

    ctrl, bundle = make_controller(qtbot, request)
    # Identity: hardware_init assigned from the bundle, not constructed.
    assert ctrl.camera is bundle.camera
    assert ctrl.siggen is bundle.siggen
    assert ctrl.motors is bundle.motors
    assert ctrl.etls is bundle.etls
    assert ctrl.lasers == list(bundle.lasers)
    # Type: every handle is a Mock* instance (no real HAL construction).
    assert isinstance(ctrl.camera, MockCamera)
    assert isinstance(ctrl.siggen, MockSigGen)
    assert isinstance(ctrl.motors, MockMotors)
    assert isinstance(ctrl.etls, MockETLs)
    assert all(isinstance(l, MockLaser) for l in ctrl.lasers), (
        "every laser handle must be a MockLaser (no real HAL construction)"
    )
