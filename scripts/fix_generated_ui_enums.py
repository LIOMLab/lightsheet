#!/usr/bin/env python3
# ruff: noqa: E501
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
    # QAbstractItemView.EditTrigger
    "QAbstractItemView.NoEditTriggers": "QAbstractItemView.EditTrigger.NoEditTriggers",
    "QAbstractItemView.CurrentChanged": "QAbstractItemView.EditTrigger.CurrentChanged",
    "QAbstractItemView.DoubleClicked": "QAbstractItemView.EditTrigger.DoubleClicked",
    "QAbstractItemView.SelectedClicked": "QAbstractItemView.EditTrigger.SelectedClicked",
    "QAbstractItemView.EditKeyPressed": "QAbstractItemView.EditTrigger.EditKeyPressed",
    "QAbstractItemView.AnyKeyPressed": "QAbstractItemView.EditTrigger.AnyKeyPressed",
    "QAbstractItemView.AllEditTriggers": "QAbstractItemView.EditTrigger.AllEditTriggers",
    # QAbstractItemView.SelectionBehavior
    "QAbstractItemView.SelectItems": "QAbstractItemView.SelectionBehavior.SelectItems",
    "QAbstractItemView.SelectRows": "QAbstractItemView.SelectionBehavior.SelectRows",
    "QAbstractItemView.SelectColumns": "QAbstractItemView.SelectionBehavior.SelectColumns",
    # QAbstractItemView.SelectionMode
    "QAbstractItemView.NoSelection": "QAbstractItemView.SelectionMode.NoSelection",
    "QAbstractItemView.SingleSelection": "QAbstractItemView.SelectionMode.SingleSelection",
    "QAbstractItemView.MultiSelection": "QAbstractItemView.SelectionMode.MultiSelection",
    "QAbstractItemView.ExtendedSelection": "QAbstractItemView.SelectionMode.ExtendedSelection",
    "QAbstractItemView.ContiguousSelection": "QAbstractItemView.SelectionMode.ContiguousSelection",
    # QComboBox.SizeAdjustPolicy
    "QComboBox.AdjustToContents": "QComboBox.SizeAdjustPolicy.AdjustToContents",
    "QComboBox.AdjustToContentsOnFirstShow": "QComboBox.SizeAdjustPolicy.AdjustToContentsOnFirstShow",
    "QComboBox.AdjustToMinimumContentsLengthWithIcon": "QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon",
    # QFormLayout.FieldGrowthPolicy
    "QFormLayout.FieldsStayAtSizeHint": "QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint",
    "QFormLayout.ExpandingFieldsGrow": "QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow",
    "QFormLayout.AllNonFixedFieldsGrow": "QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow",
    # QStyle.StandardPixmap (PySide6 .pyi stubs only expose the scoped form).
    "QStyle.SP_TitleBarMenuButton": "QStyle.StandardPixmap.SP_TitleBarMenuButton",
    "QStyle.SP_TitleBarMinButton": "QStyle.StandardPixmap.SP_TitleBarMinButton",
    "QStyle.SP_TitleBarMaxButton": "QStyle.StandardPixmap.SP_TitleBarMaxButton",
    "QStyle.SP_TitleBarCloseButton": "QStyle.StandardPixmap.SP_TitleBarCloseButton",
    "QStyle.SP_TitleBarNormalButton": "QStyle.StandardPixmap.SP_TitleBarNormalButton",
    "QStyle.SP_TitleBarShadeButton": "QStyle.StandardPixmap.SP_TitleBarShadeButton",
    "QStyle.SP_TitleBarUnshadeButton": "QStyle.StandardPixmap.SP_TitleBarUnshadeButton",
    "QStyle.SP_TitleBarContextHelpButton": "QStyle.StandardPixmap.SP_TitleBarContextHelpButton",
    "QStyle.SP_DockWidgetCloseButton": "QStyle.StandardPixmap.SP_DockWidgetCloseButton",
    "QStyle.SP_MessageBoxInformation": "QStyle.StandardPixmap.SP_MessageBoxInformation",
    "QStyle.SP_MessageBoxWarning": "QStyle.StandardPixmap.SP_MessageBoxWarning",
    "QStyle.SP_MessageBoxCritical": "QStyle.StandardPixmap.SP_MessageBoxCritical",
    "QStyle.SP_MessageBoxQuestion": "QStyle.StandardPixmap.SP_MessageBoxQuestion",
    "QStyle.SP_DesktopIcon": "QStyle.StandardPixmap.SP_DesktopIcon",
    "QStyle.SP_TrashIcon": "QStyle.StandardPixmap.SP_TrashIcon",
    "QStyle.SP_ComputerIcon": "QStyle.StandardPixmap.SP_ComputerIcon",
    "QStyle.SP_DriveFDIcon": "QStyle.StandardPixmap.SP_DriveFDIcon",
    "QStyle.SP_DriveHDIcon": "QStyle.StandardPixmap.SP_DriveHDIcon",
    "QStyle.SP_DriveCDIcon": "QStyle.StandardPixmap.SP_DriveCDIcon",
    "QStyle.SP_DriveDVDIcon": "QStyle.StandardPixmap.SP_DriveDVDIcon",
    "QStyle.SP_DriveNetIcon": "QStyle.StandardPixmap.SP_DriveNetIcon",
    "QStyle.SP_DirOpenIcon": "QStyle.StandardPixmap.SP_DirOpenIcon",
    "QStyle.SP_DirClosedIcon": "QStyle.StandardPixmap.SP_DirClosedIcon",
    "QStyle.SP_DirLinkIcon": "QStyle.StandardPixmap.SP_DirLinkIcon",
    "QStyle.SP_DirLinkOpenIcon": "QStyle.StandardPixmap.SP_DirLinkOpenIcon",
    "QStyle.SP_FileIcon": "QStyle.StandardPixmap.SP_FileIcon",
    "QStyle.SP_FileLinkIcon": "QStyle.StandardPixmap.SP_FileLinkIcon",
    "QStyle.SP_ToolBarHorizontalExtensionButton": "QStyle.StandardPixmap.SP_ToolBarHorizontalExtensionButton",
    "QStyle.SP_ToolBarVerticalExtensionButton": "QStyle.StandardPixmap.SP_ToolBarVerticalExtensionButton",
    "QStyle.SP_FileDialogStart": "QStyle.StandardPixmap.SP_FileDialogStart",
    "QStyle.SP_FileDialogEnd": "QStyle.StandardPixmap.SP_FileDialogEnd",
    "QStyle.SP_FileDialogToParent": "QStyle.StandardPixmap.SP_FileDialogToParent",
    "QStyle.SP_FileDialogNewFolder": "QStyle.StandardPixmap.SP_FileDialogNewFolder",
    "QStyle.SP_FileDialogDetailedView": "QStyle.StandardPixmap.SP_FileDialogDetailedView",
    "QStyle.SP_FileDialogInfoView": "QStyle.StandardPixmap.SP_FileDialogInfoView",
    "QStyle.SP_FileDialogContentsView": "QStyle.StandardPixmap.SP_FileDialogContentsView",
    "QStyle.SP_FileDialogListView": "QStyle.StandardPixmap.SP_FileDialogListView",
    "QStyle.SP_FileDialogBack": "QStyle.StandardPixmap.SP_FileDialogBack",
    "QStyle.SP_DirIcon": "QStyle.StandardPixmap.SP_DirIcon",
    "QStyle.SP_DialogOkButton": "QStyle.StandardPixmap.SP_DialogOkButton",
    "QStyle.SP_DialogCancelButton": "QStyle.StandardPixmap.SP_DialogCancelButton",
    "QStyle.SP_DialogHelpButton": "QStyle.StandardPixmap.SP_DialogHelpButton",
    "QStyle.SP_DialogOpenButton": "QStyle.StandardPixmap.SP_DialogOpenButton",
    "QStyle.SP_DialogSaveButton": "QStyle.StandardPixmap.SP_DialogSaveButton",
    "QStyle.SP_DialogCloseButton": "QStyle.StandardPixmap.SP_DialogCloseButton",
    "QStyle.SP_DialogApplyButton": "QStyle.StandardPixmap.SP_DialogApplyButton",
    "QStyle.SP_DialogResetButton": "QStyle.StandardPixmap.SP_DialogResetButton",
    "QStyle.SP_DialogDiscardButton": "QStyle.StandardPixmap.SP_DialogDiscardButton",
    "QStyle.SP_DialogYesButton": "QStyle.StandardPixmap.SP_DialogYesButton",
    "QStyle.SP_DialogNoButton": "QStyle.StandardPixmap.SP_DialogNoButton",
    "QStyle.SP_ArrowUp": "QStyle.StandardPixmap.SP_ArrowUp",
    "QStyle.SP_ArrowDown": "QStyle.StandardPixmap.SP_ArrowDown",
    "QStyle.SP_ArrowLeft": "QStyle.StandardPixmap.SP_ArrowLeft",
    "QStyle.SP_ArrowRight": "QStyle.StandardPixmap.SP_ArrowRight",
    "QStyle.SP_ArrowBack": "QStyle.StandardPixmap.SP_ArrowBack",
    "QStyle.SP_ArrowForward": "QStyle.StandardPixmap.SP_ArrowForward",
    "QStyle.SP_DirHomeIcon": "QStyle.StandardPixmap.SP_DirHomeIcon",
    "QStyle.SP_CommandLink": "QStyle.StandardPixmap.SP_CommandLink",
    "QStyle.SP_VistaShield": "QStyle.StandardPixmap.SP_VistaShield",
    "QStyle.SP_BrowserReload": "QStyle.StandardPixmap.SP_BrowserReload",
    "QStyle.SP_BrowserStop": "QStyle.StandardPixmap.SP_BrowserStop",
    "QStyle.SP_MediaPlay": "QStyle.StandardPixmap.SP_MediaPlay",
    "QStyle.SP_MediaStop": "QStyle.StandardPixmap.SP_MediaStop",
    "QStyle.SP_MediaPause": "QStyle.StandardPixmap.SP_MediaPause",
    "QStyle.SP_MediaSkipForward": "QStyle.StandardPixmap.SP_MediaSkipForward",
    "QStyle.SP_MediaSkipBackward": "QStyle.StandardPixmap.SP_MediaSkipBackward",
    "QStyle.SP_MediaSeekForward": "QStyle.StandardPixmap.SP_MediaSeekForward",
    "QStyle.SP_MediaSeekBackward": "QStyle.StandardPixmap.SP_MediaSeekBackward",
    "QStyle.SP_MediaVolume": "QStyle.StandardPixmap.SP_MediaVolume",
    "QStyle.SP_MediaVolumeMuted": "QStyle.StandardPixmap.SP_MediaVolumeMuted",
}


# Pre-compile a single regex that matches any known unscoped token. The pattern
# uses word-boundary anchors so it only replaces whole tokens and never a
# substring of a larger, already-scoped name.
_TOKEN_PATTERN = re.compile(
    r"\b("
    + "|".join(re.escape(token) for token in sorted(_TOKEN_MAP, key=len, reverse=True))
    + r")\b"
)

# pyside6-uic generated code calls ``setText`` on the result of
# ``QTableWidget.horizontalHeaderItem`` without checking for ``None``. The stub
# types this return as ``QTableWidgetItem | None``, so we insert a None guard.
_HEADER_ITEM_SETTEXT_RE = re.compile(
    r"^(        ([A-Za-z0-9_]+) = (self\.[A-Za-z0-9_]+\.horizontalHeaderItem\(\d+\))\n)"
    r"^(        \2\.setText\(.*\))$",
    re.MULTILINE,
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


def _guard_header_item_settext(match: re.Match[str]) -> str:
    """Wrap a QTableWidget horizontalHeaderItem setText call in a None guard."""
    indent = "        "
    return (
        f"{match.group(1)}"
        f"{indent}if {match.group(2)} is not None:\n"
        f"{indent}    {match.group(4)}\n"
    )


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
    rewritten = _HEADER_ITEM_SETTEXT_RE.sub(_guard_header_item_settext, rewritten)
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
