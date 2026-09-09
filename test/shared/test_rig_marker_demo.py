"""Proof test for the ``pytest_collection_modifyitems`` auto-skip contract (TST-07).

This module does NOT test device behavior. It tests the collection hook
itself: when ``LIGHTSHEET_HW`` is unset (the Mac dev box), every
``@pytest.mark.rig`` test in the suite is auto-skipped by the hook in
``test/conftest.py``; an unmarked test in the same module runs normally.

The two functions below are the standing regression for that contract —
if the hook is ever removed or the env-var read breaks, the
``@pytest.mark.rig`` function will start RUNNING (a test-status flip from
SKIPPED to PASSED) and the unmarked control case will keep passing, making
the regression visible in the suite summary.
"""

import pytest


@pytest.mark.rig
def test_placeholder_rig_only_is_skipped_without_hardware() -> None:
    """Carries the ``rig`` marker. On Mac (``LIGHTSHEET_HW`` unset) the
    collection hook skips this before it ever runs; on the rig
    (``LIGHTSHEET_HW=1``) it runs and passes. Its only purpose is to prove
    the skip mechanism — the body is a no-op."""
    pass


def test_placeholder_mock_runs_always() -> None:
    """Unmarked control case — runs on every environment (Mac + rig) and
    passes. Proves the hook does not over-skip unmarked tests."""
    pass
