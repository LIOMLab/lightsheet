"""Smoke test proving ``test.fixtures`` and ``test.helpers`` packages import.

Replaces the legacy ``test/_helpers/test_import.py`` smoke test. It validates
that the reorganized fixture and helper packages resolve and expose the
expected public names now that ``test/_helpers/`` is removed.
"""

from __future__ import annotations

import pytest

from lightsheet.hal import (
    DeviceBundle,
    MockCamera,
    MockETLs,
    MockLaser,
    MockMotors,
    MockSigGen,
)
from test.fixtures.controller import bundle, controller
from test.helpers.factories import make_bundle


def test_fixture_package_importable() -> None:
    """The new fixture module exposes callable fixtures for ``bundle`` and
    ``controller``."""
    assert callable(bundle)
    assert callable(controller)


def test_helper_factory_returns_bundle() -> None:
    """``make_bundle`` builds a ``DeviceBundle`` with the expected mock HAL
    instances and two lasers."""
    assert callable(make_bundle)
    device_bundle = make_bundle()
    assert isinstance(device_bundle, DeviceBundle)
    assert isinstance(device_bundle.camera, MockCamera)
    assert isinstance(device_bundle.siggen, MockSigGen)
    assert isinstance(device_bundle.motors, MockMotors)
    assert isinstance(device_bundle.etls, MockETLs)
    assert len(device_bundle.lasers) == 2
    assert all(isinstance(laser, MockLaser) for laser in device_bundle.lasers)


def test_helper_cleanup_callable() -> None:
    """The Qt cleanup helpers are importable and callable when PySide6 is
    present."""
    pytest.importorskip("PySide6")
    from test.helpers.cleanup import _pump_deferred_delete, _quit_thread_draining

    assert callable(_pump_deferred_delete)
    assert callable(_quit_thread_draining)
