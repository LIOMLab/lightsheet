"""TST-04 conformance suite — ETLs family (D-15).

Parametrized over ``[real, mock]`` with one assertion body behind both paths.
The real id (``ETLs``) is skipped on Mac; the mock id (``MockETLs``)
always runs. ``ETLS_CONTRACT`` is the single source of truth for the
container surface (open/close/set_analog_mode + error attrs).

The per-lens ``IOptotune`` ~30 CRC-protected serial commands raise
``NotImplementedError`` in the mock (D-06) and are rig-verified at HW2-01;
they are out of scope for this container-surface conformance test.

This is a BEHAVIOR test (AGENTS.md §5).
"""

import os
from unittest.mock import MagicMock

import pytest

from lightsheet.hal import ETLs, MockETLs
from lightsheet.hal.conformance import ETLS_CONTRACT

# Module-level hardware gate (D-15). Mirrors conftest._has_hardware but
# defined inline so the test file is self-contained at collection time
# (parametrize marks are evaluated before fixtures resolve). Set
# LIGHTSHEET_HW=1 on the rig to run the real conformance path.
_has_hardware: bool = os.environ.get("LIGHTSHEET_HW", "0") == "1"


@pytest.mark.parametrize(
    "device_factory",
    [
        pytest.param(
            lambda: ETLs(),
            marks=[
                pytest.mark.skipif(not _has_hardware, reason="rig only"),
                pytest.mark.xdist_group("rig_hardware"),
            ],
            id="real",
        ),
        pytest.param(lambda: MockETLs(), id="mock"),
    ],
)
def test_etls_conformance(device_factory: object) -> None:
    """One assertion body behind both [real, mock] — the structural
    divergence catch (D-15). Covers the ETLs container surface
    (open/close/set_analog_mode + error attrs). Per-lens Optotune CRC
    commands are rig-verified at HW2-01 (D-06)."""
    dev = device_factory()
    ETLS_CONTRACT.assert_lifecycle(dev)
    ETLS_CONTRACT.assert_error_surface(dev)
    ETLS_CONTRACT.assert_read_attrs(dev)
    ETLS_CONTRACT.assert_setter_methods(dev)


# --------------------------------------------------------------------------- #
# ETLs container branch coverage: set_analog_mode / set_current_mode /
# get_mode / get_temperature / close each guard on `etl_left is not None`
# and `etl_right is not None`. Both the None (no-op) and non-None
# (delegating) branches must be exercised.
# --------------------------------------------------------------------------- #
def _make_etls() -> ETLs:
    """Construct a real ETLs() — __init__ reads config.ini and sets ports,
    leaving etl_left/etl_right as None (no hardware on Mac)."""
    return ETLs()


def test_etls_setters_noop_when_both_etls_none() -> None:
    """When both etl_left and etl_right are None (post-construct state),
    set_analog_mode / set_current_mode / get_mode / get_temperature / close
    are all no-ops — the False arcs of the guard conditionals."""
    etls = _make_etls()
    assert etls.etl_left is None
    assert etls.etl_right is None
    # None of these should raise.
    etls.set_analog_mode()
    etls.set_current_mode()
    etls.get_mode()
    etls.get_temperature()
    etls.close()


def test_etls_set_analog_mode_delegates_to_both_etls() -> None:
    """When both etl_left and etl_right are present, set_analog_mode
    delegates to both — the True arcs of both guards."""
    etls = _make_etls()
    left = MagicMock()
    right = MagicMock()
    etls.etl_left = left
    etls.etl_right = right
    etls.set_analog_mode()
    left.mode.assert_called_once_with("analog")
    right.mode.assert_called_once_with("analog")


def test_etls_set_current_mode_delegates_to_both_etls() -> None:
    """When both etls are present, set_current_mode delegates to both."""
    etls = _make_etls()
    left = MagicMock()
    right = MagicMock()
    etls.etl_left = left
    etls.etl_right = right
    etls.set_current_mode()
    left.mode.assert_called_once_with("current")
    right.mode.assert_called_once_with("current")


def test_etls_close_delegates_to_both_etls() -> None:
    """When both etls are present, close calls handshake + close on both."""
    etls = _make_etls()
    left = MagicMock()
    right = MagicMock()
    etls.etl_left = left
    etls.etl_right = right
    etls.close()
    left.handshake.assert_called_once()
    left.close.assert_called_once()
    right.handshake.assert_called_once()
    right.close.assert_called_once()


def test_etls_get_mode_delegates_to_both_etls() -> None:
    """When both etls are present, get_mode queries both (the True arc)."""
    etls = _make_etls()
    left = MagicMock()
    left.mode.return_value = "analog"
    right = MagicMock()
    right.mode.return_value = "current"
    etls.etl_left = left
    etls.etl_right = right
    # get_mode prints — just verify it doesn't raise and both are queried.
    etls.get_mode()
    left.mode.assert_called_once_with()
    right.mode.assert_called_once_with()


def test_etls_get_temperature_delegates_to_both_etls() -> None:
    """When both etls are present, get_temperature queries both."""
    etls = _make_etls()
    left = MagicMock()
    left.temp_reading.return_value = 20.0
    right = MagicMock()
    right.temp_reading.return_value = 21.0
    etls.etl_left = left
    etls.etl_right = right
    etls.get_temperature()
    left.temp_reading.assert_called_once()
    right.temp_reading.assert_called_once()


def test_etls_setters_delegate_with_only_one_etl() -> None:
    """When only etl_left is present (etl_right is None), the setters
    delegate to the left and skip the right — the mixed-branch arc."""
    etls = _make_etls()
    left = MagicMock()
    etls.etl_left = left
    etls.etl_right = None
    etls.set_analog_mode()
    left.mode.assert_called_once_with("analog")
    etls.set_current_mode()
    left.mode.assert_called_with("current")
    etls.close()
    left.handshake.assert_called_once()
    left.close.assert_called_once()
