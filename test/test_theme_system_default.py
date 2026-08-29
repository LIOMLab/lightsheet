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

import os
import sys

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication


# ---------------------------------------------------------------------------
# Helpers — import the theme resolution + stylesheet loading helpers from
# __main__. They are module-level functions (not the closure form) so they
# are unit-testable without constructing the full Controller_MainWindow.
# ---------------------------------------------------------------------------


def _import_theme_module():
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


def test_load_breeze_stylesheet_light_non_empty(qtbot) -> None:
    m = _import_theme_module()
    sheet = m._load_breeze_stylesheet("light")
    assert isinstance(sheet, str)
    assert len(sheet) > 1000, "light stylesheet is suspiciously small"
    assert "Breeze" in sheet or "breeze" in sheet.lower()


def test_load_breeze_stylesheet_dark_non_empty(qtbot) -> None:
    m = _import_theme_module()
    sheet = m._load_breeze_stylesheet("dark")
    assert isinstance(sheet, str)
    assert len(sheet) > 1000, "dark stylesheet is suspiciously small"


def test_load_breeze_stylesheet_light_distinct_from_dark(qtbot) -> None:
    m = _import_theme_module()
    light = m._load_breeze_stylesheet("light")
    dark = m._load_breeze_stylesheet("dark")
    assert light != dark, "light and dark stylesheets must differ"


# ---------------------------------------------------------------------------
# set_app_stylesheet — applies the chosen theme to the QApplication.
# ---------------------------------------------------------------------------


def test_set_app_stylesheet_dark_applied(qtbot) -> None:
    m = _import_theme_module()
    app = QApplication.instance()
    _reset_app_stylesheet(app)
    m.set_app_stylesheet("dark", app=app)
    assert app.styleSheet() != "", "dark stylesheet was not applied"
    # Sanity: the applied sheet is the Breeze dark sheet, not qdarkstyle.
    assert "Breeze" in app.styleSheet() or "breeze" in app.styleSheet().lower()


def test_set_app_stylesheet_light_applied(qtbot) -> None:
    m = _import_theme_module()
    app = QApplication.instance()
    _reset_app_stylesheet(app)
    m.set_app_stylesheet("light", app=app)
    assert app.styleSheet() != "", "light stylesheet was not applied"


def test_set_app_stylesheet_light_distinct_from_dark(qtbot) -> None:
    m = _import_theme_module()
    app = QApplication.instance()
    _reset_app_stylesheet(app)
    m.set_app_stylesheet("dark", app=app)
    dark_sheet = app.styleSheet()
    m.set_app_stylesheet("light", app=app)
    light_sheet = app.styleSheet()
    assert dark_sheet != light_sheet, "light/dark must produce different app sheets"


# ---------------------------------------------------------------------------
# System-default resolution — _system_theme reads colorScheme.
# ---------------------------------------------------------------------------


def test_system_theme_dark(qtbot) -> None:
    m = _import_theme_module()
    QGuiApplication.styleHints().setColorScheme(Qt.ColorScheme.Dark)
    assert m._system_theme() == "dark"


def test_system_theme_light(qtbot) -> None:
    m = _import_theme_module()
    QGuiApplication.styleHints().setColorScheme(Qt.ColorScheme.Light)
    assert m._system_theme() == "light"


def test_system_theme_unknown_falls_back_to_dark(qtbot) -> None:
    m = _import_theme_module()
    QGuiApplication.styleHints().setColorScheme(Qt.ColorScheme.Unknown)
    assert m._system_theme() == "dark"


def test_set_app_stylesheet_system_follows_dark(qtbot) -> None:
    m = _import_theme_module()
    app = QApplication.instance()
    _reset_app_stylesheet(app)
    QGuiApplication.styleHints().setColorScheme(Qt.ColorScheme.Dark)
    m.set_app_stylesheet("system", app=app, persisted_theme="system")
    assert app.styleSheet() != ""
    # The applied sheet must be the Breeze dark sheet.
    assert app.styleSheet() == m._load_breeze_stylesheet("dark")


def test_set_app_stylesheet_system_follows_light(qtbot) -> None:
    m = _import_theme_module()
    app = QApplication.instance()
    _reset_app_stylesheet(app)
    QGuiApplication.styleHints().setColorScheme(Qt.ColorScheme.Light)
    m.set_app_stylesheet("system", app=app, persisted_theme="system")
    assert app.styleSheet() == m._load_breeze_stylesheet("light")


# ---------------------------------------------------------------------------
# Startup resolution — _resolve_theme maps the persisted config value to the
# theme code that set_app_stylesheet consumes.
# ---------------------------------------------------------------------------


def test_resolve_theme_system_uses_color_scheme(qtbot) -> None:
    m = _import_theme_module()
    QGuiApplication.styleHints().setColorScheme(Qt.ColorScheme.Dark)
    assert m._resolve_theme("system") == "dark"
    QGuiApplication.styleHints().setColorScheme(Qt.ColorScheme.Light)
    assert m._resolve_theme("system") == "light"


def test_resolve_theme_explicit_dark(qtbot) -> None:
    m = _import_theme_module()
    # An explicit "dark" persisted choice is honored regardless of OS scheme.
    QGuiApplication.styleHints().setColorScheme(Qt.ColorScheme.Light)
    assert m._resolve_theme("dark") == "dark"


def test_resolve_theme_explicit_light(qtbot) -> None:
    m = _import_theme_module()
    QGuiApplication.styleHints().setColorScheme(Qt.ColorScheme.Dark)
    assert m._resolve_theme("light") == "light"


def test_resolve_theme_unknown_value_falls_back_to_system(qtbot) -> None:
    # A malformed persisted value (e.g. "" or "purple") resolves to system
    # rather than crashing — the config_schema Literal rejects "purple" at
    # load time, but _resolve_theme must still be defensive.
    m = _import_theme_module()
    QGuiApplication.styleHints().setColorScheme(Qt.ColorScheme.Dark)
    assert m._resolve_theme("") == "dark"  # "" -> system -> dark


# ---------------------------------------------------------------------------
# colorSchemeChanged follow — only when persisted choice is "system".
# ---------------------------------------------------------------------------


def test_colorSchemeChanged_follows_when_system(qtbot) -> None:
    """When the persisted choice is "system", a mid-session OS theme switch
    triggers a reload of the matching Breeze sheet."""
    m = _import_theme_module()
    app = QApplication.instance()
    _reset_app_stylesheet(app)
    QGuiApplication.styleHints().setColorScheme(Qt.ColorScheme.Dark)
    m.set_app_stylesheet("system", app=app, persisted_theme="system")
    assert app.styleSheet() == m._load_breeze_stylesheet("dark")
    # Simulate the OS switching to Light mid-session.
    QGuiApplication.styleHints().setColorScheme(Qt.ColorScheme.Light)
    # Emit the colorSchemeChanged signal — the connected handler must reload.
    # Use qtbot.waitSignal to ensure the signal fires + handler runs.
    qtbot.waitSignal(
        QGuiApplication.styleHints().colorSchemeChanged, timeout=2000
    )
    # After the signal, the app stylesheet should now be the light sheet.
    assert app.styleSheet() == m._load_breeze_stylesheet("light")


def test_colorSchemeChanged_ignored_when_explicit(qtbot) -> None:
    """When the persisted choice is explicitly "dark" or "light", a
    mid-session OS theme switch must NOT reload the stylesheet."""
    m = _import_theme_module()
    app = QApplication.instance()
    _reset_app_stylesheet(app)
    QGuiApplication.styleHints().setColorScheme(Qt.ColorScheme.Dark)
    m.set_app_stylesheet("dark", app=app, persisted_theme="dark")
    dark_sheet = app.styleSheet()
    # OS switches to Light — the explicit "dark" choice must hold.
    QGuiApplication.styleHints().setColorScheme(Qt.ColorScheme.Light)
    qtbot.waitSignal(
        QGuiApplication.styleHints().colorSchemeChanged, timeout=2000
    )
    assert app.styleSheet() == dark_sheet, (
        "explicit dark choice was overridden by an OS theme switch"
    )


# ---------------------------------------------------------------------------
# config_schema theme field — both tiers.
# ---------------------------------------------------------------------------


def test_controller_settings_theme_default_system() -> None:
    from lightsheet.config_schema import ControllerSettings

    # The "Theme" alias is optional with default "system"; the other
    # required Controller keys (Units, Image File Format) are supplied.
    s = ControllerSettings(Units="mm", **{"Image File Format": "hdf5"})
    assert s.theme == "system"


def test_controller_settings_theme_explicit_dark() -> None:
    from lightsheet.config_schema import ControllerSettings

    s = ControllerSettings(Units="mm", **{"Image File Format": "hdf5"}, Theme="dark")
    assert s.theme == "dark"


def test_controller_settings_theme_rejects_unknown() -> None:
    from pydantic import ValidationError

    from lightsheet.config_schema import ControllerSettings

    with pytest.raises(ValidationError):
        ControllerSettings(
            Units="mm", **{"Image File Format": "hdf5"}, Theme="purple"
        )


def test_controller_settings_theme_empty_string_maps_to_system() -> None:
    # load_sections_from_ini builds the cfg_read defaults dict with "" for
    # every alias, so a key absent from config.ini arrives as "". The
    # before-validator must map "" -> "system".
    from lightsheet.config_schema import ControllerSettings

    s = ControllerSettings(Units="mm", **{"Image File Format": "hdf5"}, Theme="")
    assert s.theme == "system"


def test_controller_settings_theme_case_insensitive() -> None:
    # The rig's Title-Case "Dark"/"Light"/"System" config.ini values are
    # accepted via the before-validator lowercasing.
    from lightsheet.config_schema import ControllerSettings

    s = ControllerSettings(
        Units="mm", **{"Image File Format": "hdf5"}, Theme="Dark"
    )
    assert s.theme == "dark"


def test_controller_overlay_theme_default_system() -> None:
    from lightsheet.config_schema import ControllerSettingsOverlay

    s = ControllerSettingsOverlay(Units="mm", **{"Image File Format": "hdf5"})
    assert s.theme == "system"


def test_controller_overlay_theme_empty_string_maps_to_system() -> None:
    from lightsheet.config_schema import ControllerSettingsOverlay

    s = ControllerSettingsOverlay(
        Units="mm", **{"Image File Format": "hdf5"}, Theme=""
    )
    assert s.theme == "system"


def test_controller_overlay_theme_rejects_unknown() -> None:
    from pydantic import ValidationError

    from lightsheet.config_schema import ControllerSettingsOverlay

    with pytest.raises(ValidationError):
        ControllerSettingsOverlay(
            Units="mm", **{"Image File Format": "hdf5"}, Theme="purple"
        )


# ---------------------------------------------------------------------------
# qdarkstyle removal — no longer a project dependency.
# ---------------------------------------------------------------------------


def test_qdarkstyle_absent_from_pyproject() -> None:
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pyproject = os.path.join(project_root, "pyproject.toml")
    with open(pyproject, encoding="utf-8") as f:
        content = f.read()
    assert "qdarkstyle" not in content.lower(), (
        "qdarkstyle must be removed from pyproject.toml"
    )


def test_qdarkstyle_not_imported_in_main() -> None:
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    main_py = os.path.join(project_root, "lightsheet", "__main__.py")
    with open(main_py, encoding="utf-8") as f:
        content = f.read()
    assert "import qdarkstyle" not in content, (
        "lightsheet/__main__.py must not import qdarkstyle"
    )
    assert "qdarkstyle" not in content, (
        "lightsheet/__main__.py must not reference qdarkstyle at all"
    )


def test_breeze_compiled_resource_committed() -> None:
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    breeze_py = os.path.join(
        project_root, "lightsheet", "gui", "breeze_pyside6.py"
    )
    assert os.path.isfile(breeze_py), (
        "lightsheet/gui/breeze_pyside6.py (compiled resource) must be committed"
    )


def test_breeze_vendor_license_retained() -> None:
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    license_path = os.path.join(
        project_root,
        "lightsheet",
        "gui",
        "_vendor",
        "breezestylesheets",
        "LICENSE.md",
    )
    assert os.path.isfile(license_path), (
        "BreezeStyleSheets MIT LICENSE.md must be retained in the vendored tree"
    )
    with open(license_path, encoding="utf-8") as f:
        text = f.read()
    assert "MIT" in text, "Vendored LICENSE.md must be the MIT license"


def test_build_breeze_script_exists() -> None:
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    script = os.path.join(project_root, "scripts", "build-breeze.sh")
    assert os.path.isfile(script), "scripts/build-breeze.sh must exist"
    with open(script, encoding="utf-8") as f:
        content = f.read()
    assert "configure.py" in content, (
        "build-breeze.sh must run configure.py to build the compiled resource"
    )
    assert "BREEZE_COMMIT" in content, (
        "build-breeze.sh must pin the BreezeStyleSheets commit via BREEZE_COMMIT"
    )
