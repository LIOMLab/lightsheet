"""Branch-coverage closure for ``lightsheet.gui.ui_controller_rc``.

This is a PyQt5 resource compiler generated file. The uncovered branches are:
- The ``qt_version < [5, 8, 0]`` True branch (rcc_version=1 path)
- The ``qInitResources()`` module-level call (may not be tracked at import)

The tests mock ``QtCore.qVersion()`` and reload the module to exercise the
version-check branch, and call ``qInitResources`` / ``qCleanupResources``
directly.
"""

from __future__ import annotations

import importlib
from unittest.mock import patch

import pytest


def test_qinit_resources_and_qcleanup_resources_callable() -> None:
    """qInitResources() and qCleanupResources() can be called directly
    without raising (covers the function bodies)."""
    from lightsheet.gui import ui_controller_rc

    # These should not raise — they register/unregister resource data.
    ui_controller_rc.qInitResources()
    ui_controller_rc.qCleanupResources()


def test_qt_version_below_5_8_uses_v1_struct() -> None:
    """When QtCore.qVersion() returns < 5.8.0, the module sets rcc_version=1
    and uses qt_resource_struct_v1 (the True branch of the version check).

    This test mocks qVersion and reloads the module to exercise the branch."""
    pytest.importorskip("PyQt5")
    from PyQt5 import QtCore

    with patch.object(QtCore, "qVersion", return_value="5.7.0"):
        # Reload the module so the version check runs with the mocked value.
        import lightsheet.gui.ui_controller_rc as mod
        importlib.reload(mod)
        try:
            assert mod.rcc_version == 1
            assert mod.qt_resource_struct is mod.qt_resource_struct_v1
        finally:
            # Restore the real module state.
            with patch.object(QtCore, "qVersion", return_value=QtCore.qVersion()):
                importlib.reload(mod)
