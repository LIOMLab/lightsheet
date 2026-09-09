"""Verify package-root path anchoring in ``lightsheet/__main__.py``.

The entry point must resolve startup config/inventory files from
``__file__`` so the operator can launch from a desktop shortcut with an
arbitrary current working directory.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest


def test_package_root_and_config_constants() -> None:
    """The package-root constants are absolute and point to the tracked files."""
    import lightsheet.__main__

    expected_root = Path(lightsheet.__main__.__file__).resolve().parents[1]
    assert expected_root == lightsheet.__main__._PACKAGE_ROOT
    assert lightsheet.__main__.CONFIG_PATH.name == "config.ini"
    assert lightsheet.__main__.CONFIG_PATH.is_file()
    assert lightsheet.__main__.CONFIG_PATH.is_absolute()
    assert lightsheet.__main__.HARDWARE_INVENTORY_PATH.is_file()
    assert lightsheet.__main__.HARDWARE_INVENTORY_PATH.is_absolute()
    assert lightsheet.__main__.RIG_SPECIFIC_PATH.is_absolute()


def test_main_threads_absolute_config_paths(
    qtbot: pytest.QtBot,  # ty: ignore[unresolved-attribute]
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``main()`` passes package-root absolute paths into ``cfg_read``,
    ``DeviceRegistry``, and ``load_sections_from_ini``.

    Replicates the ``test_main_bootstrap.py`` harness with recording
    stubs for the two config helpers.
    """
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LIGHTSHEET_DEMO", "1")
    # Mock the controller module so Controller_MainWindow is a no-op QObject.
    from PySide6.QtCore import QObject

    import lightsheet.__main__

    class _MockController(QObject):
        _last_instance: _MockController | None = None

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__()
            self.ui = Mock()
            self.lasers = []
            self.estop_event = Mock()
            self.sig_message = Mock()
            self.sig_beep = Mock()
            self.sig_stylesheet = Mock()
            self._auto_laser1 = False
            self._auto_laser2 = False
            self.laser1_power_pct = 0.0
            self.laser2_power_pct = 0.0
            self.focus_selected = False
            _MockController._last_instance = self

        def show(self) -> None:
            pass

    mock_controller_mod = types.ModuleType("lightsheet.gui.shell.controller")
    mock_controller_mod.Controller_MainWindow = _MockController  # ty: ignore[unresolved-attribute]
    monkeypatch.setitem(
        sys.modules, "lightsheet.gui.shell.controller", mock_controller_mod
    )

    from PySide6.QtWidgets import QApplication as _RealQApp

    class _FakeQApp:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def setStyleSheet(self, *args: object, **kwargs: object) -> None:
            pass

        def beep(self) -> None:
            pass

        def exec(self) -> int:
            return 0

        @staticmethod
        def setOverrideCursor(*args: object, **kwargs: object) -> None:
            pass

        @staticmethod
        def restoreOverrideCursor(*args: object, **kwargs: object) -> None:
            pass

        @staticmethod
        def instance() -> object:
            return _RealQApp.instance()

    monkeypatch.setattr("PySide6.QtWidgets.QApplication", _FakeQApp)

    import lightsheet.config
    import lightsheet.config_schema
    import lightsheet.logging_setup

    monkeypatch.setattr(lightsheet.logging_setup, "configure", lambda **kw: None)

    # Record cfg_read calls and return the input defaults (theme = "system").
    cfg_calls: list[str] = []

    def recording_cfg_read(
        path: str, section: str, defaults: dict[str, str]
    ) -> dict[str, str]:
        cfg_calls.append(path)
        return defaults

    monkeypatch.setattr(lightsheet.config, "cfg_read", recording_cfg_read)

    # Record load_sections_from_ini calls and return an empty schema.
    loader_calls: list[tuple[str, str | None]] = []

    def recording_loader(
        baseline_path: str,
        overlay_path: str | None = None,
    ) -> dict[str, dict[str, str]]:
        loader_calls.append((baseline_path, overlay_path))
        return {}

    monkeypatch.setattr(
        lightsheet.config_schema, "load_sections_from_ini", recording_loader
    )
    monkeypatch.setattr(
        lightsheet.config_schema,
        "ConfigValidator",
        lambda: Mock(validate_or_abort=Mock()),
    )

    # Patch sys.excepthook to a no-op so the closure install does not fire
    # the real hook (which would surface a "CALL ERROR" into Qt's loop).
    monkeypatch.setattr(sys, "excepthook", lambda *a, **kw: None)

    result = lightsheet.__main__.main()
    assert result == 0

    expected_theme_path = str(lightsheet.__main__.CONFIG_PATH)
    assert cfg_calls and cfg_calls[0] == expected_theme_path, (
        f"theme cfg_read expected {expected_theme_path}, got {cfg_calls}"
    )

    expected_baseline = str(lightsheet.__main__.CONFIG_PATH)
    expected_overlay = (
        str(lightsheet.__main__.RIG_SPECIFIC_PATH)
        if lightsheet.__main__.RIG_SPECIFIC_PATH.exists()
        else None
    )
    assert loader_calls == [(expected_baseline, expected_overlay)], (
        f"load_sections_from_ini called with {loader_calls}, expected "
        f"{(expected_baseline, expected_overlay)}"
    )
