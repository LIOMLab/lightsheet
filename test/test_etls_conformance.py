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
