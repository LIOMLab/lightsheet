#!/usr/bin/env python3
"""Idempotent post-processor that converts pyside6-uic spacing literals to tokens."""

import argparse
import difflib
import re
import sys
from pathlib import Path

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
    return f".setSpacing({_token(m[1])})"


def _replace_contents_margins(m: re.Match[str]) -> str:
    return f".setContentsMargins({_token(m[1])}, {_token(m[2])}, {_token(m[3])}, {_token(m[4])})"


def _replace_fixed(m: re.Match[str]) -> str:
    return f".setFixed{m[1]}({_token(m[2])})"


def _replace_qsize(m: re.Match[str]) -> str:
    return f"QSize({_token(m[1])}, {_token(m[2])})"


def _replace_spacer(m: re.Match[str]) -> str:
    return f"QSpacerItem({_token(m[1])}, {_token(m[2])}"


def _transform(text: str) -> str:
    text = _SET_SPACING_RE.sub(_replace_set_spacing, text)
    text = _SET_CONTENTS_RE.sub(_replace_contents_margins, text)
    text = _SET_FIXED_RE.sub(_replace_fixed, text)
    text = _QSIZE_RE.sub(_replace_qsize, text)
    text = _SPACER_RE.sub(_replace_spacer, text)
    return text


def _process(path: Path, dry_run: bool, show_diff: bool) -> bool:
    original = path.read_text(encoding="utf-8")
    if _is_tokenized(original):
        return False
    transformed = _transform(original)
    if transformed == original:
        return False
    transformed = _add_import(transformed)
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
        description="Map pyside6-uic spacing literals to _s tokens in generated forms."
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
    parser.add_argument(
        "--dry-run", action="store_true", help="do not write any files"
    )
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
