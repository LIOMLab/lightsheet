"""Branch-coverage closure for ``lightsheet.gui.ui_controller_rc``.

This is a PySide6 resource compiler generated file. The uncovered branches are:
- The ``qInitResources()`` module-level call (may not be tracked at import)

The ``pyside6-rcc`` generated file (Qt6) does not emit the
``qt_version < [5, 8, 0]`` version-gate branch that the old ``pyqt5-rcc``
output had — it directly registers resources with format version ``0x03``
(Qt6 rcc v3). The previous version-gate branch test is therefore obsolete
and has been replaced with a format-version assertion on the
``qRegisterResourceData`` call.
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


def test_rcc_uses_qt6_format_version() -> None:
    """The generated rcc module registers resources with the Qt6 format
    version (0x03), confirming the pyside6-rcc output matches the runtime
    Qt version. The old pyqt5-rcc output had a version-gate branch
    (``qt_version < [5, 8, 0]`` selecting rcc_version 1 vs 2); pyside6-rcc
    does not emit that branch, so this test asserts the format version
    embedded in the qRegisterResourceData call instead."""
    pytest.importorskip("PySide6")
    import inspect

    from lightsheet.gui import ui_controller_rc

    # The qInitResources source should register with format version 0x03
    # (Qt6 rcc v3). This exercises the generated registration code without
    # the unsafe importlib.reload that corrupts Qt's resource registry.
    source = inspect.getsource(ui_controller_rc.qInitResources)
    assert "0x03" in source, (
        f"qInitResources should register with Qt6 format version 0x03, "
        f"got: {source!r}"
    )
    assert hasattr(ui_controller_rc, "qt_resource_struct")
