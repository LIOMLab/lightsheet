"""Source-contract tests for ``scripts/create-desktop-shortcut.ps1``.

The installer uses ``WScript.Shell`` COM, which cannot execute on the dev
Mac, so these tests pin the script's field contract by reading the
committed source. Runtime verification (running the script and
double-clicking the shortcuts) is a rig-side manual check.

Pinned contract:

- a ``-SkipSync`` switch guards a ``uv sync`` preflight;
- shortcuts are created via ``New-Object -ComObject WScript.Shell`` /
  ``CreateShortcut``;
- exactly ``Lightsheet.lnk`` and ``Lightsheet Demo.lnk`` are written under
  both the ``SpecialFolders("Desktop")`` base and a Start Menu base
  containing ``Start Menu\\Programs\\Lightsheet``;
- the demo shortcut's ``Arguments`` is ``--demo`` and the real one's is
  empty;
- every shortcut targets ``.venv\\Scripts\\lightsheetw.exe`` joined to
  ``$RepoRoot``, sets ``WorkingDirectory = $RepoRoot``, and points
  ``IconLocation`` at ``lightsheet\\resources\\lightsheet.ico``;
- the script ``Test-Path``-guards the exe and the icon and ``throw``s a
  clear error when either is missing.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "create-desktop-shortcut.ps1"


def _script_text() -> str:
    assert SCRIPT.is_file(), f"missing installer script: {SCRIPT}"
    return SCRIPT.read_text(encoding="utf-8")


def test_script_exists() -> None:
    """The committed PowerShell installer exists."""
    assert SCRIPT.is_file()


def test_sksync_switch_guards_uv_sync_preflight() -> None:
    """``-SkipSync`` is declared and ``uv sync`` runs only when it is absent
    and the run is not a ``-WhatIf`` dry run."""
    text = _script_text()
    assert re.search(r"\[switch\]\$SkipSync", text)
    assert "uv sync" in text
    assert re.search(
        r"if\s*\(\s*-not\s+\$SkipSync\s*-and\s*-not\s+\$WhatIf\s*\)", text
    )


def test_whatif_is_side_effect_free() -> None:
    """``-WhatIf`` must not mutate the machine: ``New-Item`` for the Start
    Menu folder runs only in the non-WhatIf branch."""
    text = _script_text()
    assert re.search(
        r"if\s*\(\s*\$WhatIf\s*\)\s*\{\s*Write-Output[^}]*\}\s*else\s*\{[^}]*"
        r"New-Item\s+-ItemType\s+Directory",
        text,
        re.DOTALL,
    )


def test_wscript_shell_com_and_createshortcut() -> None:
    """The script resolves ``WScript.Shell`` and calls ``CreateShortcut``."""
    text = _script_text()
    assert "New-Object -ComObject WScript.Shell" in text
    assert "CreateShortcut" in text


def test_four_shortcut_names_and_two_bases() -> None:
    """Both shortcut names are written under the Desktop special folder and
    a Start Menu ``Programs\\Lightsheet`` folder."""
    text = _script_text()
    assert 'SpecialFolders("Desktop")' in text
    assert re.search(r"Start Menu\\Programs\\Lightsheet", text)
    assert '"Lightsheet.lnk"' in text
    assert '"Lightsheet Demo.lnk"' in text


def test_demo_arguments_and_empty_real_arguments() -> None:
    """The demo entry passes ``--demo``; the real entry's Arguments is empty."""
    text = _script_text()
    assert '"--demo"' in text
    assert re.search(r'@\(\s*"Lightsheet\.lnk",\s*""', text)
    assert re.search(r'@\(\s*"Lightsheet Demo\.lnk",\s*"--demo"', text)
    # The demo shortcut carries a distinguishing Description so the operator
    # can tell the two .lnk files apart in the same folder.
    assert "demo mode" in text.lower()


def test_shortcut_field_values() -> None:
    """``TargetPath``, ``WorkingDirectory``, and ``IconLocation`` are pinned
    to the repo-root ``.venv`` launcher and the committed icon."""
    text = _script_text()
    assert re.search(
        r'Join-Path\s+\$RepoRoot\s+"\.venv\\Scripts\\lightsheetw\.exe"', text
    )
    assert re.search(r"\.WorkingDirectory\s*=\s*\$RepoRoot", text)
    assert re.search(
        r'Join-Path\s+\$RepoRoot\s+"lightsheet\\resources\\lightsheet\.ico"', text
    )
    assert re.search(r"\.IconLocation\s*=", text)


def test_missing_target_and_icon_are_guarded() -> None:
    """The script ``Test-Path``-guards the exe and icon and ``throw``s a
    clear error rather than writing a broken shortcut."""
    text = _script_text()
    test_path_count = len(re.findall(r"Test-Path", text))
    assert test_path_count >= 2, (
        f"expected >=2 Test-Path guards, found {test_path_count}"
    )
    assert re.search(r"throw\s+", text)
