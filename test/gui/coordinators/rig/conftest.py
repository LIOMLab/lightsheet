from __future__ import annotations

from pathlib import Path

import pytest

_RIG_GUI_ROOT = Path(__file__).parent


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Group all real DAQ coordinator tests onto the same xdist worker.

    These tests exercise the same DAQ laser channels as test/hal/rig/.
    Marking them with the same xdist_group keeps them from racing with
    other DAQ tests on the rig.
    """
    for item in items:
        if item.path.is_relative_to(_RIG_GUI_ROOT):
            item.add_marker(pytest.mark.xdist_group("daq"))
