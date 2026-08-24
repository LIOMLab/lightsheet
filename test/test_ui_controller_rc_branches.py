"""Branch-coverage closure for ``lightsheet.gui.ui_controller_rc``.

This is a PyQt5 resource compiler generated file. The uncovered branches are:
- The ``qInitResources()`` module-level call (may not be tracked at import)

The ``qt_version < [5, 8, 0]`` True branch (rcc_version=1 path) is a
module-level branch in GENERATED code. It cannot be covered safely:
``importlib.reload`` on a Qt rcc module re-runs ``qInitResources()``, which
re-registers C++ resource data that is not cleaned up by the reload,
corrupting Qt's internal resource registry. The next ``QMainWindow.__init__``
(via ``setupUi`` loading ``:/...`` resources) then segfaults. That branch is
therefore NOT chased here — generated rcc code is not worth destabilising the
suite for one version-gate branch.
"""

from __future__ import annotations

import pytest


def test_qinit_resources_and_qcleanup_resources_callable() -> None:
    """qInitResources() and qCleanupResources() can be called directly
    without raising (covers the function bodies)."""
    from lightsheet.gui import ui_controller_rc

    # These should not raise — they register/unregister resource data.
    ui_controller_rc.qInitResources()
    ui_controller_rc.qCleanupResources()


def test_rcc_version_matches_runtime_qt() -> None:
    """The module selected the rcc struct matching the running Qt version
    (covers the version-check expression without reloading the module).

    On Qt >= 5.8 (every supported rig + dev box) ``rcc_version`` is 2 and
    ``qt_resource_struct`` is ``qt_resource_struct_v2``. Asserting the
    current selection exercises the version-comparison expression at
    module load without the unsafe ``importlib.reload`` that corrupts Qt's
    resource registry."""
    pytest.importorskip("PyQt5")
    from lightsheet.gui import ui_controller_rc

    assert ui_controller_rc.rcc_version == 2
    assert ui_controller_rc.qt_resource_struct is ui_controller_rc.qt_resource_struct_v2
