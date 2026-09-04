#!/usr/bin/env python3
"""Idempotent post-processor that converts pyside6-uic output to design tokens."""

import argparse
import difflib
import re
import typing
from pathlib import Path


def _group_str(m: re.Match[str], idx: int) -> str:
    """Return a regex capture group as a concrete ``str``.

    PySide6/ty stubs type ``re.Match.__getitem__`` as ``Any``, which causes
    ``unsound-return-statement`` errors in functions that concatenate groups.
    The group is always a string in this module, so the cast is safe.
    """
    return typing.cast(str, m[idx])


_SPACING_REMAP = {
    0: "_s.ZERO",
    4: "_s.XS",
    6: "_s.SM",
    8: "_s.SM",
    10: "_s.MD",
    12: "_s.MD",
    16: "_s.LG",
    20: "_s.LG + _s.XS",
    24: "_s.XL",
    32: "_s.XXL",
    40: "_s.XXL + _s.SM",
    48: "_s.RAIL",
    60: "_s.RAIL + _s.LG",
    64: "_s.RAIL + _s.LG",
    72: "_s.RAIL + _s.XL",
    76: "_s.RAIL + _s.XL + _s.XS",
    80: "_s.RAIL + _s.XXL",
    96: "_s.RAIL * 2",
    120: "_s.RAIL * 2 + _s.XL",
    126: "_s.PANEL_FLOOR",
    140: "_s.RAIL * 2 + _s.XL + _s.LG + _s.XS",
}
_SENTINEL = 16777215
_IMPORT_LINE = "from lightsheet.gui.styles import spacing as _s"

_PYSIDE_BLOCK_RE = re.compile(
    r"^(from PySide6\.[^\n]*\n(?:^    [^\n]*\n)*)+",
    re.MULTILINE,
)
_ALREADY_RE = re.compile(r"\b_s\.")

_SET_SPACING_RE = re.compile(r"\.setSpacing\((\d+)\)")
_SET_CONTENTS_RE = re.compile(
    r"\.setContentsMargins\((-?\d+),\s*(-?\d+),\s*(-?\d+),\s*(-?\d+)\)"
)
_SET_FIXED_RE = re.compile(r"\.setFixed(Height|Width)\((\d+)\)")
_QSIZE_RE = re.compile(r"QSize\((-?\d+),\s*(-?\d+)\)")
_SPACER_RE = re.compile(r"QSpacerItem\((\d+),\s*(\d+)")

# Style-sheet insertion regexes: these are only meant to run on pyside6-uic output
# for files that lack the tokenized style calls.  If the calls are already present,
# the "setMinimumSize ... setStyleSheet" pattern no longer matches and the patch is
# a no-op.
_SHELL_ESTOP_STATUS_RE = re.compile(
    r"(        self\.label_estopStatus\.setMinimumSize\(QSize\([^)]+\)\))\n"
    r"(        self\.toolBar_estop\.addWidget\(self\.label_estopStatus\))"
)
_SHELL_ESTOP_BTN_RE = re.compile(
    r"(        self\.pushButton_estop\.setMinimumSize\(QSize\([^)]+\)\))\n"
    r"(        self\.pushButton_estop\.setCheckable\(True\))"
)
_SHELL_MODE_BADGE_RE = re.compile(
    r"(        self\.label_modeBadge\.setMinimumSize\(QSize\([^)]+\)\))\n"
    r"(        self\.toolBar_estop\.addWidget\(self\.label_modeBadge\))"
)
_LASER1_STATUS_STYLE_RE = re.compile(
    r"(        self\.label_laserOneStatus\.setMinimumSize\(QSize\([^)]+\)\))\n\n"
    r"(        self\.verticalLayout_43\.addWidget\(self\.label_laserOneStatus\))"
)
_LASER2_STATUS_STYLE_RE = re.compile(
    r"(        self\.label_laserTwoStatus\.setMinimumSize\(QSize\([^)]+\)\))\n\n"
    r"(        self\.verticalLayout_44\.addWidget\(self\.label_laserTwoStatus\))"
)


def _token(value: str) -> str:
    n = int(value)
    if n == _SENTINEL:
        return value
    return _SPACING_REMAP.get(n, value)


def _is_tokenized(text: str) -> bool:
    return _IMPORT_LINE in text or _ALREADY_RE.search(text) is not None


def _add_import(text: str) -> str:
    match = _PYSIDE_BLOCK_RE.search(text)
    if not match:
        return text
    end = match.end()
    return text[:end] + _IMPORT_LINE + "\n" + text[end:]


def _replace_set_spacing(m: re.Match[str]) -> str:
    return f".setSpacing({_token(_group_str(m, 1))})"


def _replace_contents_margins(m: re.Match[str]) -> str:
    return (
        f".setContentsMargins({_token(_group_str(m, 1))}, "
        f"{_token(_group_str(m, 2))}, {_token(m[3])}, {_token(m[4])})"
    )


def _replace_fixed(m: re.Match[str]) -> str:
    return f".setFixed{_group_str(m, 1)}({_token(_group_str(m, 2))})"


def _replace_qsize(m: re.Match[str]) -> str:
    return f"QSize({_token(_group_str(m, 1))}, {_token(_group_str(m, 2))})"


def _replace_spacer(m: re.Match[str]) -> str:
    return f"QSpacerItem({_token(_group_str(m, 1))}, {_token(_group_str(m, 2))}"


def _transform(text: str) -> str:
    text = _SET_SPACING_RE.sub(_replace_set_spacing, text)
    text = _SET_CONTENTS_RE.sub(_replace_contents_margins, text)
    text = _SET_FIXED_RE.sub(_replace_fixed, text)
    text = _QSIZE_RE.sub(_replace_qsize, text)
    text = _SPACER_RE.sub(_replace_spacer, text)
    return text


def _ensure_imports(text: str, imports: list[tuple[str, str]], anchor: str) -> str:
    """Insert missing lightsheet.gui.styles imports after the anchor line."""
    missing = [
        (module, alias)
        for module, alias in imports
        if f"from lightsheet.gui.styles import {module} as {alias}" not in text
    ]
    if not missing:
        return text

    if anchor in text:
        lines = text.splitlines(keepends=True)
        for i, line in enumerate(lines):
            if line.rstrip("\n") == anchor:
                inserted = [
                    f"from lightsheet.gui.styles import {module} as {alias}\n"
                    for module, alias in missing
                ]
                return "".join(lines[: i + 1] + inserted + lines[i + 1 :])

    # Fallback to end of the PySide6 import block.
    match = _PYSIDE_BLOCK_RE.search(text)
    if match:
        end = match.end()
        inserted = "".join(
            f"from lightsheet.gui.styles import {module} as {alias}\n"
            for module, alias in missing
        )
        return text[:end] + inserted + text[end:]

    return text


def _replace_shell_estop_status(m: re.Match[str]) -> str:
    return (
        _group_str(m, 1)
        + "\n        self.label_estopStatus.setStyleSheet("
        + 'f"color: {_c.SUCCESS}; {_t.BOLD}")\n'
        + _group_str(m, 2)
    )


def _replace_shell_estop_btn(m: re.Match[str]) -> str:
    return (
        _group_str(m, 1)
        + "\n"
        + "        self.pushButton_estop.setStyleSheet(\n"
        + '            f"QPushButton {{ background-color: {_c.DANGER}; "\n'
        + '            f"color: {_c.ON_DANGER}; {_t.HEADING} "\n'
        + '            f"border: 2px solid {_c.BREEZE_BG}; }}"\n'
        + "        )\n"
        + _group_str(m, 2)
    )


def _replace_shell_mode_badge(m: re.Match[str]) -> str:
    return (
        _group_str(m, 1)
        + '\n        self.label_modeBadge.setStyleSheet(f"{_t.BOLD}")\n'
        + _group_str(m, 2)
    )


def _replace_laser1_status_style(m: re.Match[str]) -> str:
    return (
        _group_str(m, 1)
        + "\n        self.label_laserOneStatus.setStyleSheet("
        + 'f"color: {_c.DISABLED}; {_t.BOLD}")\n\n'
        + _group_str(m, 2)
    )


def _replace_laser2_status_style(m: re.Match[str]) -> str:
    return (
        _group_str(m, 1)
        + "\n        self.label_laserTwoStatus.setStyleSheet("
        + 'f"color: {_c.DISABLED}; {_t.BOLD}")\n\n'
        + _group_str(m, 2)
    )


def _patch_shell(text: str) -> str:
    text = _ensure_imports(
        text,
        [("colors", "_c"), ("typography", "_t")],
        "from lightsheet.gui.panels.levels_bar import LevelsBar",
    )
    text = _SHELL_ESTOP_STATUS_RE.sub(_replace_shell_estop_status, text)
    text = _SHELL_ESTOP_BTN_RE.sub(_replace_shell_estop_btn, text)
    text = _SHELL_MODE_BADGE_RE.sub(_replace_shell_mode_badge, text)
    return text


def _patch_laser(text: str) -> str:
    text = _ensure_imports(
        text,
        [("colors", "_c"), ("symbols", "_sym"), ("typography", "_t")],
        "from lightsheet.gui.styles import spacing as _s",
    )
    text = _LASER1_STATUS_STYLE_RE.sub(_replace_laser1_status_style, text)
    text = _LASER2_STATUS_STYLE_RE.sub(_replace_laser2_status_style, text)
    text = text.replace(
        (
            r'self.label_72.setText(QCoreApplication.translate("LaserPanel", '
            r'u"Laser1", None))'
        ),
        (
            r'self.label_72.setText(QCoreApplication.translate("LaserPanel", '
            r'f"<html><head/><body><p><span style=\"{_t.POWER}\">'
            r'Laser1</span></p></body></html>", None))'
        ),
    )
    text = text.replace(
        (
            r'self.label_73.setText(QCoreApplication.translate("LaserPanel", '
            r'u"Laser2", None))'
        ),
        (
            r'self.label_73.setText(QCoreApplication.translate("LaserPanel", '
            r'f"<html><head/><body><p><span style=\"{_t.POWER}\">'
            r'Laser2</span></p></body></html>", None))'
        ),
    )
    text = text.replace(
        r'self.label_laserOneStatus.setText(QCoreApplication.translate("LaserPanel", '
        r'u"\u25cb OFF", None))',
        r'self.label_laserOneStatus.setText(QCoreApplication.translate("LaserPanel", '
        r'f"{_sym.LASER_OFF} OFF", None))',
    )
    text = text.replace(
        r'self.label_laserTwoStatus.setText(QCoreApplication.translate("LaserPanel", '
        r'u"\u25cb OFF", None))',
        r'self.label_laserTwoStatus.setText(QCoreApplication.translate("LaserPanel", '
        r'f"{_sym.LASER_OFF} OFF", None))',
    )
    return text


def _patch_scan(text: str) -> str:
    text = _ensure_imports(
        text,
        [("typography", "_t")],
        "from lightsheet.gui.styles import spacing as _s",
    )
    for label, inner in [
        ("label_76", "Left ETL"),
        ("label_80", "Right ETL"),
        ("label_69", "Left Galvo"),
        ("label_70", "Right Galvo"),
    ]:
        old = (
            f'self.{label}.setText(QCoreApplication.translate("ScanPanel", '
            f'u"{inner}", None))'
        )
        new = (
            f'self.{label}.setText(QCoreApplication.translate("ScanPanel", '
            f'f\'<html><head/><body><p><span style="{{_t.POWER}}">'
            f"{inner}</span></p></body></html>', None))"
        )
        text = text.replace(old, new)
    return text


def _style_patches(text: str, path: Path) -> str:
    name = path.name
    if name == "ui_shell.py":
        return _patch_shell(text)
    if name == "ui_laser_panel.py":
        return _patch_laser(text)
    if name == "ui_scan_panel.py":
        return _patch_scan(text)
    return text


def _process(path: Path, dry_run: bool, show_diff: bool) -> bool:
    original = path.read_text(encoding="utf-8")
    if _is_tokenized(original):
        return False
    transformed = _transform(original)
    transformed = _add_import(transformed)
    transformed = _style_patches(transformed, path)
    if transformed == original:
        return False
    if dry_run or show_diff:
        if dry_run:
            print(f"would change: {path}")
        if show_diff:
            print(
                "".join(
                    difflib.unified_diff(
                        original.splitlines(keepends=True),
                        transformed.splitlines(keepends=True),
                        fromfile=str(path),
                        tofile=str(path),
                    )
                )
            )
        return True
    path.write_text(transformed, encoding="utf-8")
    print(f"tokenized: {path}")
    return True


def _target_files(repo_root: Path) -> list[Path]:
    gui = repo_root / "lightsheet" / "gui"
    files: set[Path] = set()
    for p in gui.rglob("ui_*.py"):
        if p.name.endswith("_rc.py"):
            continue
        files.add(p)
    shell = gui / "shell" / "ui_shell.py"
    if shell.is_file():
        files.add(shell)
    return sorted(files)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Map pyside6-uic output to _s/_c/_t/_sym design tokens."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="repository root (defaults to parent of this script)",
    )
    parser.add_argument(
        "--check", action="store_true", help="list files that would change"
    )
    parser.add_argument(
        "--diff", action="store_true", help="print diffs of files that would change"
    )
    parser.add_argument("--dry-run", action="store_true", help="do not write any files")
    args = parser.parse_args(argv)
    if args.repo_root is None:
        args.repo_root = Path(__file__).resolve().parent.parent
    dry_run = args.check or args.diff or args.dry_run
    show_diff = args.diff
    changed = 0
    for path in _target_files(args.repo_root):
        if _process(path, dry_run, show_diff):
            changed += 1
    print(f"changed={changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
