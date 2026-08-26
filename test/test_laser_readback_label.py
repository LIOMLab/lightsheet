"""Behavior tests for the L1 readback label honesty (est./cal. suffix).

The L1 (DAQLaser) readback label must distinguish an unverified
linear-through-origin estimate ("(est.)") from a rig-measured calibration
("(cal.)"). The label formatter lives in
``HardwareManager._refresh_laser_readback``, which branches on
``laser.calibrated`` for idx=0 (L1/DAQLaser, no hardware readback).

Behavior covered:
- L1 uncalibrated (no curve) -> emits "{value:.1f} mW (est.)" with a
  tooltip mentioning the 107.5 mW rig-measured max.
- L1 calibrated (curve loaded) -> emits "{value:.1f} mW (cal.)" with a
  tooltip mentioning the measured curve.
- L2 (iBeam) path unchanged -> emits "{value:.1f} mW" with empty tooltip
  (it has a real serial readback, no estimate suffix).
- L2 None readback -> emits "{power:.1f} mW (cmd)" fallback (unchanged).

This is a BEHAVIOR test (AGENTS.md §5) — it executes the real
``_refresh_laser_readback`` method body against Mock laser/shell stand-ins
and asserts on the emitted (idx, text, tooltip) tuples.
"""

from __future__ import annotations

import threading
from unittest.mock import Mock

from lightsheet.gui.coordinators.hardware_manager import HardwareManager
from lightsheet.hal import DeviceBundle, MockCamera, MockETLs, MockMotors, MockSigGen


def _make_bundle() -> DeviceBundle:
    """Build a demo DeviceBundle (lasers replaced per-test below)."""
    camera = MockCamera(verbose=True)
    siggen = MockSigGen(camera)
    motors = MockMotors()
    etls = MockETLs()
    lasers = (Mock(spec=["_lock"]), Mock(spec=["_lock"]))
    return DeviceBundle(
        camera=camera, siggen=siggen, motors=motors, etls=etls, lasers=lasers
    )


def _make_shell() -> Mock:
    """Mock stand-in shell exposing sig_laser_readback (the signal the
    formatter emits through)."""
    shell = Mock()
    shell.sig_laser_readback = Mock()
    shell.sig_message = Mock()
    shell.estop_event = threading.Event()
    return shell


def _make_laser_mock(*, calibrated: bool, power: float, output: float | None) -> Mock:
    """Build a Mock laser stand-in with a real RLock (the formatter probes
    it with acquire(blocking=False)) and the attributes get_output_power /
    calibrated / power that _refresh_laser_readback reads."""
    laser = Mock()
    laser._lock = threading.RLock()
    laser.calibrated = calibrated
    laser.power = power
    laser.get_output_power = Mock(return_value=output)
    return laser


def test_l1_uncalibrated_emits_est_suffix() -> None:
    """L1 (idx=0) with calibrated=False -> emits '{value:.1f} mW (est.)'
    with a tooltip mentioning the 107.5 mW rig-measured max."""
    bundle = _make_bundle()
    shell = _make_shell()
    hw = HardwareManager(bundle, shell)
    laser = _make_laser_mock(calibrated=False, power=150.0, output=150.0)
    hw.lasers = [laser, Mock()]

    hw._refresh_laser_readback(0)

    shell.sig_laser_readback.emit.assert_called_once()
    idx, text, tooltip = shell.sig_laser_readback.emit.call_args.args
    assert idx == 0
    assert text == "150.0 mW (est.)"
    assert "107.5 mW" in tooltip
    assert "Unverified" in tooltip or "unverified" in tooltip


def test_l1_calibrated_emits_cal_suffix() -> None:
    """L1 (idx=0) with calibrated=True -> emits '{value:.1f} mW (cal.)'
    with a tooltip mentioning the measured curve."""
    bundle = _make_bundle()
    shell = _make_shell()
    hw = HardwareManager(bundle, shell)
    laser = _make_laser_mock(calibrated=True, power=300.0, output=236.6)
    hw.lasers = [laser, Mock()]

    hw._refresh_laser_readback(0)

    shell.sig_laser_readback.emit.assert_called_once()
    idx, text, tooltip = shell.sig_laser_readback.emit.call_args.args
    assert idx == 0
    assert text == "236.6 mW (cal.)"
    assert "Calibrated" in tooltip or "calibrated" in tooltip.lower()
    # Must NOT carry the unverified-estimate warning.
    assert "107.5 mW, not" not in tooltip


def test_l2_path_unchanged_no_suffix() -> None:
    """L2 (idx=1, iBeam) has a real serial readback -> emits '{value:.1f}
    mW' with an EMPTY tooltip (no est./cal. suffix — that suffix is L1-only
    because only DAQLaser lacks hardware readback)."""
    bundle = _make_bundle()
    shell = _make_shell()
    hw = HardwareManager(bundle, shell)
    laser = _make_laser_mock(calibrated=False, power=120.0, output=120.0)
    hw.lasers = [Mock(), laser]

    hw._refresh_laser_readback(1)

    shell.sig_laser_readback.emit.assert_called_once()
    idx, text, tooltip = shell.sig_laser_readback.emit.call_args.args
    assert idx == 1
    assert text == "120.0 mW"
    assert tooltip == ""


def test_l2_none_readback_emits_cmd_fallback() -> None:
    """L2 (idx=1) with get_output_power() -> None (parse failure) emits
    '{power:.1f} mW (cmd)' with a stale-value tooltip (unchanged fallback
    path)."""
    bundle = _make_bundle()
    shell = _make_shell()
    hw = HardwareManager(bundle, shell)
    laser = _make_laser_mock(calibrated=False, power=120.0, output=None)
    hw.lasers = [Mock(), laser]

    hw._refresh_laser_readback(1)

    shell.sig_laser_readback.emit.assert_called_once()
    idx, text, tooltip = shell.sig_laser_readback.emit.call_args.args
    assert idx == 1
    assert text == "120.0 mW (cmd)"
    assert "stale" in tooltip or "unavailable" in tooltip


def test_l1_zero_power_emits_est_zero() -> None:
    """L1 at 0 mW (freshly constructed / off) -> '0.0 mW (est.)' so the
    label is honest before the first power command."""
    bundle = _make_bundle()
    shell = _make_shell()
    hw = HardwareManager(bundle, shell)
    laser = _make_laser_mock(calibrated=False, power=0.0, output=0.0)
    hw.lasers = [laser, Mock()]

    hw._refresh_laser_readback(0)

    idx, text, _tooltip = shell.sig_laser_readback.emit.call_args.args
    assert idx == 0
    assert text == "0.0 mW (est.)"
