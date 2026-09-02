#!/usr/bin/env python3
"""Idempotent post-processor for pyside6-uic generated Python.

pyside6-uic emits unscoped Qt/QFrame enum names that are not recognised by
static type checkers. This script rewrites the known unscoped forms to their
scoped PySide6 equivalents, preserving the generated file header and any
unknown content.

Use it as part of the generated-file build step, after ``pyside6-uic`` and
before the type checker sees the output.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from pathlib import Path

# Each key is an exact unscoped token produced by pyside6-uic. The value is the
# scoped PySide6 form. Only known tokens are rewritten; anything else is left
# untouched.
_TOKEN_MAP: dict[str, str] = {
    # Qt.Orientation
    "Qt.Horizontal": "Qt.Orientation.Horizontal",
    "Qt.Vertical": "Qt.Orientation.Vertical",
    # Qt.AlignmentFlag
    "Qt.AlignLeft": "Qt.AlignmentFlag.AlignLeft",
    "Qt.AlignRight": "Qt.AlignmentFlag.AlignRight",
    "Qt.AlignHCenter": "Qt.AlignmentFlag.AlignHCenter",
    "Qt.AlignJustify": "Qt.AlignmentFlag.AlignJustify",
    "Qt.AlignTop": "Qt.AlignmentFlag.AlignTop",
    "Qt.AlignBottom": "Qt.AlignmentFlag.AlignBottom",
    "Qt.AlignVCenter": "Qt.AlignmentFlag.AlignVCenter",
    "Qt.AlignCenter": "Qt.AlignmentFlag.AlignCenter",
    "Qt.AlignLeading": "Qt.AlignmentFlag.AlignLeading",
    "Qt.AlignTrailing": "Qt.AlignmentFlag.AlignTrailing",
    "Qt.AlignAbsolute": "Qt.AlignmentFlag.AlignAbsolute",
    # Qt.ScrollBarPolicy
    "Qt.ScrollBarAsNeeded": "Qt.ScrollBarPolicy.ScrollBarAsNeeded",
    "Qt.ScrollBarAlwaysOff": "Qt.ScrollBarPolicy.ScrollBarAlwaysOff",
    "Qt.ScrollBarAlwaysOn": "Qt.ScrollBarPolicy.ScrollBarAlwaysOn",
    # Qt.TextInteractionFlag
    "Qt.TextSelectableByMouse": "Qt.TextInteractionFlag.TextSelectableByMouse",
    "Qt.TextSelectableByKeyboard": "Qt.TextInteractionFlag.TextSelectableByKeyboard",
    "Qt.LinksAccessibleByMouse": "Qt.TextInteractionFlag.LinksAccessibleByMouse",
    "Qt.LinksAccessibleByKeyboard": "Qt.TextInteractionFlag.LinksAccessibleByKeyboard",
    "Qt.TextEditable": "Qt.TextInteractionFlag.TextEditable",
    "Qt.TextEditorInteraction": "Qt.TextInteractionFlag.TextEditorInteraction",
    "Qt.TextBrowserInteraction": "Qt.TextInteractionFlag.TextBrowserInteraction",
    # Qt.ToolButtonStyle
    "Qt.ToolButtonIconOnly": "Qt.ToolButtonStyle.ToolButtonIconOnly",
    "Qt.ToolButtonTextOnly": "Qt.ToolButtonStyle.ToolButtonTextOnly",
    "Qt.ToolButtonTextBesideIcon": "Qt.ToolButtonStyle.ToolButtonTextBesideIcon",
    "Qt.ToolButtonTextUnderIcon": "Qt.ToolButtonStyle.ToolButtonTextUnderIcon",
    "Qt.ToolButtonFollowStyle": "Qt.ToolButtonStyle.ToolButtonFollowStyle",
    # Qt.ShortcutContext
    "Qt.WidgetShortcut": "Qt.ShortcutContext.WidgetShortcut",
    "Qt.WindowShortcut": "Qt.ShortcutContext.WindowShortcut",
    "Qt.ApplicationShortcut": "Qt.ShortcutContext.ApplicationShortcut",
    "Qt.WidgetWithChildrenShortcut": "Qt.ShortcutContext.WidgetWithChildrenShortcut",
    # QFrame.Shadow
    "QFrame.Plain": "QFrame.Shadow.Plain",
    "QFrame.Raised": "QFrame.Shadow.Raised",
    "QFrame.Sunken": "QFrame.Shadow.Sunken",
    # QFrame.Shape
    "QFrame.NoFrame": "QFrame.Shape.NoFrame",
    "QFrame.StyledPanel": "QFrame.Shape.StyledPanel",
    "QFrame.Panel": "QFrame.Shape.Panel",
    "QFrame.WinPanel": "QFrame.Shape.WinPanel",
    "QFrame.HLine": "QFrame.Shape.HLine",
    "QFrame.VLine": "QFrame.Shape.VLine",
    # Qt.LayoutDirection
    "Qt.LeftToRight": "Qt.LayoutDirection.LeftToRight",
    "Qt.RightToLeft": "Qt.LayoutDirection.RightToLeft",
    "Qt.LayoutDirectionAuto": "Qt.LayoutDirection.LayoutDirectionAuto",
    # Qt.SortOrder
    "Qt.AscendingOrder": "Qt.SortOrder.AscendingOrder",
    "Qt.DescendingOrder": "Qt.SortOrder.DescendingOrder",
    # Qt.CheckState
    "Qt.Unchecked": "Qt.CheckState.Unchecked",
    "Qt.PartiallyChecked": "Qt.CheckState.PartiallyChecked",
    "Qt.Checked": "Qt.CheckState.Checked",
    # Qt.ItemFlag
    "Qt.ItemIsSelectable": "Qt.ItemFlag.ItemIsSelectable",
    "Qt.ItemIsEditable": "Qt.ItemFlag.ItemIsEditable",
    "Qt.ItemIsDragEnabled": "Qt.ItemFlag.ItemIsDragEnabled",
    "Qt.ItemIsDropEnabled": "Qt.ItemFlag.ItemIsDropEnabled",
    "Qt.ItemIsUserCheckable": "Qt.ItemFlag.ItemIsUserCheckable",
    "Qt.ItemIsEnabled": "Qt.ItemFlag.ItemIsEnabled",
    "Qt.ItemIsTristate": "Qt.ItemFlag.ItemIsTristate",
    # Qt.ItemDataRole
    "Qt.DisplayRole": "Qt.ItemDataRole.DisplayRole",
    "Qt.DecorationRole": "Qt.ItemDataRole.DecorationRole",
    "Qt.EditRole": "Qt.ItemDataRole.EditRole",
    "Qt.ToolTipRole": "Qt.ItemDataRole.ToolTipRole",
    "Qt.StatusTipRole": "Qt.ItemDataRole.StatusTipRole",
    "Qt.WhatsThisRole": "Qt.ItemDataRole.WhatsThisRole",
    "Qt.SizeHintRole": "Qt.ItemDataRole.SizeHintRole",
    "Qt.FontRole": "Qt.ItemDataRole.FontRole",
    "Qt.TextAlignmentRole": "Qt.ItemDataRole.TextAlignmentRole",
    "Qt.BackgroundRole": "Qt.ItemDataRole.BackgroundRole",
    "Qt.ForegroundRole": "Qt.ItemDataRole.ForegroundRole",
    "Qt.CheckStateRole": "Qt.ItemDataRole.CheckStateRole",
    "Qt.AccessibleTextRole": "Qt.ItemDataRole.AccessibleTextRole",
    "Qt.AccessibleDescriptionRole": "Qt.ItemDataRole.AccessibleDescriptionRole",
    "Qt.UserRole": "Qt.ItemDataRole.UserRole",
    # Qt.TextElideMode
    "Qt.ElideLeft": "Qt.TextElideMode.ElideLeft",
    "Qt.ElideRight": "Qt.TextElideMode.ElideRight",
    "Qt.ElideMiddle": "Qt.TextElideMode.ElideMiddle",
    "Qt.ElideNone": "Qt.TextElideMode.ElideNone",
    # Qt.MouseButton
    "Qt.LeftButton": "Qt.MouseButton.LeftButton",
    "Qt.RightButton": "Qt.MouseButton.RightButton",
    "Qt.MiddleButton": "Qt.MouseButton.MiddleButton",
    "Qt.BackButton": "Qt.MouseButton.BackButton",
    "Qt.ForwardButton": "Qt.MouseButton.ForwardButton",
}


# Pre-compile a single regex that matches any known unscoped token. The pattern
# uses word-boundary anchors so it only replaces whole tokens and never a
# substring of a larger, already-scoped name.
_TOKEN_PATTERN = re.compile(
    r"\b("
    + "|".join(
        re.escape(token) for token in sorted(_TOKEN_MAP, key=len, reverse=True)
    )
    + r")\b"
)


_GENERATED_SIGNATURES = (
    "Form generated from reading UI file",
    "Created by: Qt User Interface Compiler version",
)


def _is_generated_file(path: Path, content: str) -> bool:
    """Return True only if *content* looks like pyside6-uic output."""
    return all(signature in content for signature in _GENERATED_SIGNATURES)


def _replace_token(match: re.Match[str]) -> str:
    """Lookup a single matched token and return its scoped replacement."""
    return _TOKEN_MAP[match.group(0)]


def rewrite_generated_ui(path: Path) -> bool:
    """Rewrite known unscoped enum tokens in a pyside6-uic generated file.

    The file is rewritten in place. Returns ``True`` if any bytes were changed,
    ``False`` if the file already contained only scoped forms.

    Raises:
        ValueError: If the path is not a Python file or does not look like a
            generated PySide6 UI file.
    """
    if path.suffix != ".py":
        raise ValueError(f"expected a .py generated file, got {path.suffix!r}")

    original = path.read_text(encoding="utf-8")
    if not _is_generated_file(path, original):
        raise ValueError(
            f"{path} does not contain a pyside6-uic generated header; refusing to edit"
        )

    rewritten = _TOKEN_PATTERN.sub(_replace_token, original)
    if rewritten == original:
        return False

    path.write_text(rewritten, encoding="utf-8")
    return True


def main(argv: Sequence[str] | None = None) -> int:
    """CLI: rewrite each explicit generated ``.py`` path.

    Prints a summary and returns 0 when every file is a valid generated Python
    file. Returns a non-zero status if any path is missing, unreadable, or not
    a pyside6-uic generated file.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Rewrite unscoped Qt/QFrame enum tokens in pyside6-uic generated .py files."
        )
    )
    parser.add_argument("paths", nargs="+", type=Path, help="generated .py files")
    args = parser.parse_args(argv[1:] if argv else None)

    changed = 0
    unchanged = 0
    invalid = 0

    for path in args.paths:
        try:
            if rewrite_generated_ui(path):
                changed += 1
            else:
                unchanged += 1
        except (ValueError, OSError) as e:
            invalid += 1
            print(f"skip: {path}: {e}", file=sys.stderr)

    print(f"changed={changed} unchanged={unchanged} invalid={invalid}")
    if invalid:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
