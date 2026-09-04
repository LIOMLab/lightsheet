"""Root pytest config — loaded before test/conftest.py.

This needs to live at the repo root (not under test/) so it runs as part of
the initial conftests, before pytest-xdist computes the worker count.
test/conftest.py is loaded later and handles the rig/mock gating and stubs.
"""

import os

import pytest

# Re-export the hardware-stub flags that the test suite imports as
# `from conftest import _nidaqmx_is_stub, _pco_is_stub` (the module search
# now finds this root conftest first).
from test.conftest import _has_hardware, _nidaqmx_is_stub, _pco_is_stub

__all__ = ["_has_hardware", "_nidaqmx_is_stub", "_pco_is_stub"]

# Use xdist's auto env override so the worker count is set before xdist's
# command-line handling. On the rig (LIGHTSHEET_HW=1) use 14 workers; on the
# dev machine default to 8. setdefault lets an explicit env var win.
if os.environ.get("LIGHTSHEET_HW", "0") == "1":
    os.environ["PYTEST_XDIST_AUTO_NUM_WORKERS"] = "14"
else:
    os.environ.setdefault("PYTEST_XDIST_AUTO_NUM_WORKERS", "8")


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config: pytest.Config) -> None:
    """Mirror the env-driven worker cap in config.option so the help text is right."""
    if os.environ.get("LIGHTSHEET_HW", "0") == "1":
        config.option.numprocesses = "auto"
        config.option.maxprocesses = 14
    else:
        config.option.numprocesses = "auto"
        config.option.maxprocesses = 8
