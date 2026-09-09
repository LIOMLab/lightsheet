"""Theme system-default + persisted override tests.

Verifies the BreezeStyleSheets integration that replaced qdarkstyle:
- ``set_app_stylesheet("light"|"dark")`` loads the Breeze stylesheet for
  that theme (non-empty, distinct between themes).
- ``set_app_stylesheet("system")`` resolves via
  ``QGuiApplication.styleHints().colorScheme()`` (Dark -> dark, Light ->
  light, Unknown -> dark fallback).
- The persisted ``[Controller] Theme`` choice (light/dark/system; default
  system) is honored at startup via ``_resolve_theme``.
- ``colorSchemeChanged`` triggers a reload only when the persisted choice
  is "system".
- ``config_schema`` ``ControllerSettings``/``ControllerSettingsOverlay``
  gain a ``theme`` field (Literal light/dark/system, default system) so an
  unknown value is rejected by the strict tier and a missing/empty value
  maps to "system" in the overlay tier.
- qdarkstyle is no longer a project dependency.
"""

from __future__ import annotations

from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any

import pytest
from pytest import MonkeyPatch
from pytestqt.qtbot import QtBot

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

if TYPE_CHECKING:
    from lightsheet.gui.shell.controller import Controller_MainWindow


def _construct_model(model_cls: Any, **kwargs: Any) -> Any:
    """Construct a pydantic-settings model, bypassing ty's strict alias checks."""
    return model_cls(**kwargs)


# ---------------------------------------------------------------------------
# Helpers — import the theme resolution + stylesheet loading helpers from
# __main__. They are module-level functions (not the closure form) so they
# are unit-testable without constructing the full Controller_MainWindow.
# ---------------------------------------------------------------------------


def _import_theme_module() -> ModuleType:
    """Import the lightsheet.__main__ module and return it.

    ``lightsheet.__main__`` defers its PySide6 / controller imports to inside
    ``main()`` so importing the module does not trigger Qt initialization.
    The theme helpers (``_resolve_theme``, ``_system_theme``,
    ``_load_breeze_stylesheet``) live at module scope.
    """
    import lightsheet.__main__ as m

    return m


def _reset_app_stylesheet(app: QApplication) -> None:
    """Clear the QApplication stylesheet so each test starts from a known
    empty state."""
    app.setStyleSheet("")


# ---------------------------------------------------------------------------
# Breeze stylesheet loading — light/dark produce non-empty, distinct sheets.
# ---------------------------------------------------------------------------


def test_load_breeze_stylesheet_light_non_empty(qtbot: QtBot) -> None:
    m = _import_theme_module()
    sheet = m._load_breeze_stylesheet("light")
    assert isinstance(sheet, str)
    assert len(sheet) > 1000, "light stylesheet is suspiciously small"
    assert "Breeze" in sheet or "breeze" in sheet.lower()


def test_load_breeze_stylesheet_dark_non_empty(qtbot: QtBot) -> None:
    m = _import_theme_module()
    sheet = m._load_breeze_stylesheet("dark")
    assert isinstance(sheet, str)
    assert len(sheet) > 1000, "dark stylesheet is suspiciously small"


# ---------------------------------------------------------------------------
# set_app_stylesheet — applies the chosen theme to the QApplication.
# ---------------------------------------------------------------------------


def test_set_app_stylesheet_dark_applied(qtbot: QtBot) -> None:
    m = _import_theme_module()
    app = QApplication.instance()
    _reset_app_stylesheet(app)  # ty: ignore[invalid-argument-type]
    m.set_app_stylesheet("dark", app=app)
    assert app.styleSheet() != "", "dark stylesheet was not applied"  # ty: ignore[unresolved-attribute]
    # Sanity: the applied sheet is the Breeze dark sheet, not qdarkstyle.
    assert "Breeze" in app.styleSheet() or "breeze" in app.styleSheet().lower()  # ty: ignore[unresolved-attribute]


def test_set_app_stylesheet_light_applied(qtbot: QtBot) -> None:
    m = _import_theme_module()
    app = QApplication.instance()
    _reset_app_stylesheet(app)  # ty: ignore[invalid-argument-type]
    m.set_app_stylesheet("light", app=app)
    assert app.styleSheet() != "", "light stylesheet was not applied"  # ty: ignore[unresolved-attribute]


def test_set_app_stylesheet_light_distinct_from_dark(qtbot: QtBot) -> None:
    m = _import_theme_module()
    app = QApplication.instance()
    _reset_app_stylesheet(app)  # ty: ignore[invalid-argument-type]
    m.set_app_stylesheet("dark", app=app)
    dark_sheet = app.styleSheet()  # ty: ignore[unresolved-attribute]
    # Sanity: the applied dark sheet is non-empty and a Breeze sheet (carried
    # over from the deleted test_load_breeze_stylesheet_light_distinct_from_dark
    # so the non-empty + Breeze marker assertion is not lost).
    assert dark_sheet != "", "dark stylesheet was not applied"
    assert "Breeze" in dark_sheet or "breeze" in dark_sheet.lower()
    m.set_app_stylesheet("light", app=app)
    light_sheet = app.styleSheet()  # ty: ignore[unresolved-attribute]
    assert dark_sheet != light_sheet, "light/dark must produce different app sheets"


# ---------------------------------------------------------------------------
# System-default resolution — _color_scheme_to_theme maps Qt.ColorScheme to
# a Breeze theme code. _system_theme reads colorScheme() and delegates.
# ---------------------------------------------------------------------------


def test_color_scheme_to_theme_mapping(qtbot: QtBot) -> None:
    """The pure 1-line mapping function covers all three Qt.ColorScheme
    inputs in a single collected test (Dark -> dark, Light -> light,
    Unknown -> dark fallback)."""
    m = _import_theme_module()
    assert m._color_scheme_to_theme(Qt.ColorScheme.Dark) == "dark"
    assert m._color_scheme_to_theme(Qt.ColorScheme.Light) == "light"
    assert m._color_scheme_to_theme(Qt.ColorScheme.Unknown) == "dark"


def test_system_theme_reads_color_scheme(
    qtbot: QtBot, monkeypatch: MonkeyPatch
) -> None:
    # _system_theme delegates to _color_scheme_to_theme after reading
    # QGuiApplication.styleHints().colorScheme(). Patch the reader to verify
    # the delegation without depending on the platform honoring
    # setColorScheme (the offscreen platform on macOS always reports
    # Unknown).
    m = _import_theme_module()
    monkeypatch.setattr(
        "PySide6.QtGui.QGuiApplication.styleHints",
        lambda: type(
            "FakeHints",
            (),
            {"colorScheme": staticmethod(lambda: Qt.ColorScheme.Light)},
        )(),
    )
    assert m._system_theme() == "light"


def test_set_app_stylesheet_system_follows_dark(
    qtbot: QtBot, monkeypatch: MonkeyPatch
) -> None:
    m = _import_theme_module()
    app = QApplication.instance()
    _reset_app_stylesheet(app)  # ty: ignore[invalid-argument-type]
    monkeypatch.setattr(m, "_system_theme", lambda: "dark")
    m.set_app_stylesheet("system", app=app, persisted_theme="system")
    assert app.styleSheet() != ""  # ty: ignore[unresolved-attribute]
    # The applied sheet must be the Breeze dark sheet.
    assert app.styleSheet() == m._load_breeze_stylesheet("dark")  # ty: ignore[unresolved-attribute]


def test_set_app_stylesheet_system_follows_light(
    qtbot: QtBot, monkeypatch: MonkeyPatch
) -> None:
    m = _import_theme_module()
    app = QApplication.instance()
    _reset_app_stylesheet(app)  # ty: ignore[invalid-argument-type]
    monkeypatch.setattr(m, "_system_theme", lambda: "light")
    m.set_app_stylesheet("system", app=app, persisted_theme="system")
    assert app.styleSheet() == m._load_breeze_stylesheet("light")  # ty: ignore[unresolved-attribute]


# ---------------------------------------------------------------------------
# Startup resolution — _resolve_theme maps the persisted config value to the
# theme code that set_app_stylesheet consumes.
# ---------------------------------------------------------------------------


def test_resolve_theme_system_uses_color_scheme(
    qtbot: QtBot, monkeypatch: MonkeyPatch
) -> None:
    m = _import_theme_module()
    monkeypatch.setattr(m, "_system_theme", lambda: "dark")
    assert m._resolve_theme("system") == "dark"
    monkeypatch.setattr(m, "_system_theme", lambda: "light")
    assert m._resolve_theme("system") == "light"


def test_resolve_theme_explicit_dark(qtbot: QtBot, monkeypatch: MonkeyPatch) -> None:
    m = _import_theme_module()
    # An explicit "dark" persisted choice is honored regardless of OS scheme.
    monkeypatch.setattr(m, "_system_theme", lambda: "light")
    assert m._resolve_theme("dark") == "dark"


def test_resolve_theme_explicit_light(qtbot: QtBot, monkeypatch: MonkeyPatch) -> None:
    m = _import_theme_module()
    monkeypatch.setattr(m, "_system_theme", lambda: "dark")
    assert m._resolve_theme("light") == "light"


def test_resolve_theme_unknown_value_falls_back_to_system(
    qtbot: QtBot, monkeypatch: MonkeyPatch
) -> None:
    # A malformed persisted value (e.g. "" or "purple") resolves to system
    # rather than crashing — the config_schema Literal rejects "purple" at
    # load time, but _resolve_theme must still be defensive.
    m = _import_theme_module()
    monkeypatch.setattr(m, "_system_theme", lambda: "dark")
    assert m._resolve_theme("") == "dark"  # "" -> system -> dark


# ---------------------------------------------------------------------------
# colorSchemeChanged follow — only when persisted choice is "system".
#
# The offscreen platform on macOS does not honor setColorScheme, so these
# tests drive the colorSchemeChanged signal's connected handler directly by
# calling _on_color_scheme_changed (the slot set_app_stylesheet connects).
# This verifies the follow-logic without depending on platform color-scheme
# support.
# ---------------------------------------------------------------------------


def test_colorSchemeChanged_follows_when_system(
    qtbot: QtBot, monkeypatch: MonkeyPatch
) -> None:
    """When the persisted choice is "system", a mid-session OS theme switch
    triggers a reload of the matching Breeze sheet.

    The follow-semantics ("the sheet changed to the new theme") is provable
    without re-loading the Breeze resource in the assertions — capturing the
    applied sheet from ``app.styleSheet()`` is enough. This avoids two
    redundant resource re-opens that just compare against the applied sheet."""
    m = _import_theme_module()
    app = QApplication.instance()
    _reset_app_stylesheet(app)  # ty: ignore[invalid-argument-type]
    monkeypatch.setattr(m, "_system_theme", lambda: "dark")
    m.set_app_stylesheet("system", app=app, persisted_theme="system")
    dark_sheet = app.styleSheet()  # ty: ignore[unresolved-attribute]
    assert dark_sheet != "", "dark sheet was not applied"
    assert "Breeze" in dark_sheet or "breeze" in dark_sheet.lower()
    # Simulate the OS switching to Light mid-session — the connected handler
    # re-resolves via _system_theme.
    monkeypatch.setattr(m, "_system_theme", lambda: "light")
    m._on_color_scheme_changed(app)
    light_sheet = app.styleSheet()  # ty: ignore[unresolved-attribute]
    assert light_sheet != "", "light sheet was not applied after the switch"
    assert light_sheet != dark_sheet, (
        "the follow-semantics did not reload the sheet on OS theme switch"
    )


def test_colorSchemeChanged_ignored_when_explicit(
    qtbot: QtBot, monkeypatch: MonkeyPatch
) -> None:
    """When the persisted choice is explicitly "dark" or "light", a
    mid-session OS theme switch must NOT reload the stylesheet."""
    m = _import_theme_module()
    app = QApplication.instance()
    _reset_app_stylesheet(app)  # ty: ignore[invalid-argument-type]
    monkeypatch.setattr(m, "_system_theme", lambda: "dark")
    m.set_app_stylesheet("dark", app=app, persisted_theme="dark")
    dark_sheet = app.styleSheet()  # ty: ignore[unresolved-attribute]
    # OS switches to Light — the explicit "dark" choice must hold. The
    # handler short-circuits because the persisted choice is "dark", not
    # "system".
    monkeypatch.setattr(m, "_system_theme", lambda: "light")
    m._on_color_scheme_changed(app)
    assert app.styleSheet() == dark_sheet, (  # ty: ignore[unresolved-attribute]
        "explicit dark choice was overridden by an OS theme switch"
    )


# ---------------------------------------------------------------------------
# config_schema theme field — both tiers.
# ---------------------------------------------------------------------------


def test_controller_settings_theme_default_system() -> None:
    from lightsheet.config_schema import ControllerSettings

    # The "Theme" alias is optional with default "system"; the other
    # required Controller keys (Units, Image File Format) are supplied.
    s = ControllerSettings(Units="mm", **{"Image File Format": "hdf5"})  # ty: ignore[invalid-argument-type]
    assert s.theme == "system"


def test_controller_settings_theme_explicit_dark() -> None:
    from lightsheet.config_schema import ControllerSettings

    s = ControllerSettings(Units="mm", **{"Image File Format": "hdf5"}, Theme="dark")  # ty: ignore[invalid-argument-type]
    assert s.theme == "dark"


def test_controller_settings_theme_rejects_unknown() -> None:
    from pydantic import ValidationError

    from lightsheet.config_schema import ControllerSettings

    with pytest.raises(ValidationError):
        _construct_model(
            ControllerSettings,
            units="mm",
            image_file_format="hdf5",
            theme="purple",
        )


def test_controller_settings_theme_empty_string_maps_to_system() -> None:
    # load_sections_from_ini builds the cfg_read defaults dict with "" for
    # every alias, so a key absent from config.ini arrives as "". The
    # before-validator must map "" -> "system".
    from lightsheet.config_schema import ControllerSettings

    s = _construct_model(
        ControllerSettings,
        units="mm",
        image_file_format="hdf5",
        theme="",
    )
    assert s.theme == "system"


def test_controller_settings_theme_case_insensitive() -> None:
    # The rig's Title-Case "Dark"/"Light"/"System" config.ini values are
    # accepted via the before-validator lowercasing.
    from lightsheet.config_schema import ControllerSettings

    s = _construct_model(
        ControllerSettings,
        units="mm",
        image_file_format="hdf5",
        theme="Dark",
    )
    assert s.theme == "dark"


def test_controller_overlay_theme_default_system() -> None:
    from lightsheet.config_schema import ControllerSettingsOverlay

    s = _construct_model(
        ControllerSettingsOverlay,
        units="mm",
        image_file_format="hdf5",
    )
    assert s.theme == "system"


def test_controller_overlay_theme_empty_string_maps_to_system() -> None:
    from lightsheet.config_schema import ControllerSettingsOverlay

    s = _construct_model(
        ControllerSettingsOverlay,
        units="mm",
        image_file_format="hdf5",
        theme="",
    )
    assert s.theme == "system"


def test_controller_overlay_theme_rejects_unknown() -> None:
    from pydantic import ValidationError

    from lightsheet.config_schema import ControllerSettingsOverlay

    with pytest.raises(ValidationError):
        _construct_model(
            ControllerSettingsOverlay,
            units="mm",
            image_file_format="hdf5",
            theme="purple",
        )


# ---------------------------------------------------------------------------
# qdarkstyle removal — no longer a project dependency.
# ---------------------------------------------------------------------------


def test_qdarkstyle_absent_from_pyproject() -> None:
    project_root = Path(__file__).resolve().parents[2]
    pyproject = project_root / "pyproject.toml"
    with pyproject.open(encoding="utf-8") as f:
        content = f.read()
    assert "qdarkstyle" not in content.lower(), (
        "qdarkstyle must be removed from pyproject.toml"
    )


def test_qdarkstyle_not_imported_in_main() -> None:
    project_root = Path(__file__).resolve().parents[2]
    main_py = project_root / "lightsheet" / "__main__.py"
    with main_py.open(encoding="utf-8") as f:
        content = f.read()
    assert "import qdarkstyle" not in content, (
        "lightsheet/__main__.py must not import qdarkstyle"
    )
    assert "qdarkstyle" not in content, (
        "lightsheet/__main__.py must not reference qdarkstyle at all"
    )


def test_breeze_compiled_resource_committed() -> None:
    project_root = Path(__file__).resolve().parents[2]
    breeze_py = project_root / "lightsheet" / "gui" / "breeze_pyside6.py"
    assert breeze_py.is_file(), (
        "lightsheet/gui/breeze_pyside6.py (compiled resource) must be committed"
    )


def test_breeze_vendor_license_retained() -> None:
    project_root = Path(__file__).resolve().parents[2]
    license_path = (
        project_root
        / "lightsheet"
        / "gui"
        / "_vendor"
        / "breezestylesheets"
        / "LICENSE.md"
    )
    assert license_path.is_file(), (
        "BreezeStyleSheets MIT LICENSE.md must be retained in the vendored tree"
    )
    with license_path.open(encoding="utf-8") as f:
        text = f.read()
    assert "MIT" in text, "Vendored LICENSE.md must be the MIT license"


def test_build_breeze_script_exists() -> None:
    project_root = Path(__file__).resolve().parents[2]
    script = project_root / "scripts" / "build-breeze.sh"
    assert script.is_file(), "scripts/build-breeze.sh must exist"
    with script.open(encoding="utf-8") as f:
        content = f.read()
    assert "configure.py" in content, (
        "build-breeze.sh must run configure.py to build the compiled resource"
    )
    assert "BREEZE_COMMIT" in content, (
        "build-breeze.sh must pin the BreezeStyleSheets commit via BREEZE_COMMIT"
    )


# ---------------------------------------------------------------------------
# Theme slot persistence + QActionGroup exclusivity (UI-SPEC §Theme Contract).
# These tests construct the real Controller_MainWindow via the controller fixture and
# exercise the updateUi_*_theme slots, asserting cfg_write is called with the
# right Theme value and the QActionGroup is exclusive + checkable.
# ---------------------------------------------------------------------------


def test_light_theme_slot_persists_to_config(
    controller: Controller_MainWindow, monkeypatch: MonkeyPatch
) -> None:
    """updateUi_light_theme writes {"Theme": "light"} to config.ini and
    shows the status-bar hint.

    The controller is constructed with demo=True (per the controller fixture), and
    the theme slots skip cfg_write in demo mode to avoid corrupting the real
    config.ini during the test suite. These tests verify the rig-path
    persistence, so they flip _demo_mode off (with cfg_write monkeypatched,
    no real file is touched).
    """
    ctrl = controller
    captured: list[tuple] = []  # ty: ignore[missing-type-argument]
    import lightsheet.gui.shell.controller as ctrl_mod

    monkeypatch.setattr(
        ctrl_mod,
        "cfg_write",
        lambda filename, section, data: captured.append(
            (filename, section, dict(data))
        ),
    )
    ctrl._demo_mode = False
    ctrl.updateUi_light_theme()
    assert any(d.get("Theme") == "light" for _, _, d in captured), (
        f"Expected cfg_write Theme=light, got: {captured}"
    )


def test_dark_theme_slot_persists_to_config(
    controller: Controller_MainWindow, monkeypatch: MonkeyPatch
) -> None:
    ctrl = controller
    captured: list[tuple] = []  # ty: ignore[missing-type-argument]
    import lightsheet.gui.shell.controller as ctrl_mod

    monkeypatch.setattr(
        ctrl_mod,
        "cfg_write",
        lambda filename, section, data: captured.append(
            (filename, section, dict(data))
        ),
    )
    ctrl._demo_mode = False
    ctrl.updateUi_dark_theme()
    assert any(d.get("Theme") == "dark" for _, _, d in captured), (
        f"Expected cfg_write Theme=dark, got: {captured}"
    )


def test_follow_system_theme_slot_persists_to_config(
    controller: Controller_MainWindow, monkeypatch: MonkeyPatch
) -> None:
    ctrl = controller
    captured: list[tuple] = []  # ty: ignore[missing-type-argument]
    import lightsheet.gui.shell.controller as ctrl_mod

    monkeypatch.setattr(
        ctrl_mod,
        "cfg_write",
        lambda filename, section, data: captured.append(
            (filename, section, dict(data))
        ),
    )
    ctrl._demo_mode = False
    ctrl.updateUi_follow_system_theme()
    assert any(d.get("Theme") == "system" for _, _, d in captured), (
        f"Expected cfg_write Theme=system, got: {captured}"
    )


def test_theme_action_group_is_exclusive_with_three_checkable_actions(
    controller: Controller_MainWindow,
) -> None:
    """ctrl._theme_action_group is exclusive with 3 actions, all checkable."""
    from PySide6.QtGui import QActionGroup

    ctrl = controller
    group = ctrl._theme_action_group
    assert isinstance(group, QActionGroup)
    assert group.isExclusive(), "theme QActionGroup must be exclusive"
    actions = group.actions()
    assert len(actions) == 3, (
        f"theme QActionGroup has {len(actions)} actions, expected 3"
    )
    for a in actions:
        assert a.isCheckable(), f"theme action {a.text()!r} must be checkable"


def test_startup_theme_reflected_on_checked_action(
    controller: Controller_MainWindow,
) -> None:
    """The persisted [Controller] Theme is reflected onto the checked
    action of the exclusive group on startup. With the default config.ini
    (no Theme key → 'system'), action_followSystemTheme is checked."""
    ctrl = controller
    # config.ini has no [Controller] Theme key → default 'system'.
    assert ctrl.ui.action_followSystemTheme.isChecked()
    assert not ctrl.ui.action_lightTheme.isChecked()
    assert not ctrl.ui.action_darkTheme.isChecked()
