from __future__ import annotations

from pathlib import Path

import pytest

_RIG_ROOT = Path(__file__).parent


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Group all real DAQ tests onto a single xdist worker.

    The NI-DAQmx laser / siggen tasks reserve the same physical AO/DO
    channels. Running these tests in parallel across xdist workers causes
    -50103 resource-reserved failures. Keep them serial but still allow the
    rest of the suite to run in parallel.
    """
    for item in items:
        if item.path.is_relative_to(_RIG_ROOT):
            item.add_marker(pytest.mark.xdist_group("daq"))
