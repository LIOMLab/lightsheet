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
    assert hasattr(workers_module, "__path__"), "lightsheet.gui.workers must be a package"
    assert workers_module.__name__ == "lightsheet.gui.workers"


def test_preview_worker_not_in_top_level_module() -> None:
    """PreviewWorker must not be defined in the top-level workers module."""
    from lightsheet.gui.workers import PreviewWorker

    assert PreviewWorker.__module__ != "lightsheet.gui.workers"
