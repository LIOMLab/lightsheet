"""Module-identity tests for the ``lightsheet.gui.workers`` package split.

These tests fail when the worker classes live in the flat
``lightsheet/gui/workers.py`` module and pass as the classes are moved into
focused submodules. They are intentionally narrow: they only assert package
structure, not worker runtime behavior (which is covered by the worker
behavior tests).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

pytest.importorskip("PySide6")

if TYPE_CHECKING:
    pass

import lightsheet.gui.workers as workers_module


def test_workers_is_package() -> None:
    """``lightsheet.gui.workers`` must be a package, not a single module."""
    assert hasattr(workers_module, "__path__"), (
        "lightsheet.gui.workers must be a package"
    )
    assert workers_module.__name__ == "lightsheet.gui.workers"


def test_preview_worker_not_in_top_level_module() -> None:
    """PreviewWorker must not be defined in the top-level workers module."""
    from lightsheet.gui.workers import PreviewWorker

    assert PreviewWorker.__module__ != "lightsheet.gui.workers"


def test_mixin_and_preview_workers_have_focused_modules() -> None:
    """The shared scan mixin and preview/live/single workers must each live in
    a focused submodule.
    """
    from lightsheet.gui.workers import (
        LiveWorker,
        PreviewWorker,
        SingleWorker,
        _AcquireScanMixin,
    )

    assert _AcquireScanMixin.__module__.endswith("scan_mixin")
    assert PreviewWorker.__module__.endswith("preview_live_single")
    assert LiveWorker.__module__.endswith("preview_live_single")
    assert SingleWorker.__module__.endswith("preview_live_single")


def test_stack_worker_in_stack_module() -> None:
    """StackWorker must live in its own focused submodule."""
    from lightsheet.gui.workers import StackWorker

    assert StackWorker.__module__.endswith("stack")


def test_legacy_monolith_removed() -> None:
    """The transitional legacy.py monolith must be removed."""
    from pathlib import Path

    from lightsheet.gui.workers import __path__ as workers_paths

    for path in workers_paths:
        assert not Path(path, "legacy.py").exists()
