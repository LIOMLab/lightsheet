#!/usr/bin/env python3
"""Prepend a project generated-file marker to Qt generator output.

Checked-in pyside6-uic / pyside6-rcc output carries only the stock Qt banner,
which reads as a warning about recompilation rather than an explicit "do not
hand-edit" marker for this repository. This post-processor inserts a project
header naming the regeneration command, and the generation pipeline re-emits
it on every run so the marker cannot silently disappear.

The insertion is idempotent and PEP 263-safe: a shebang or ``# -*- coding:``
cookie stays on line 1/2 and the header lands immediately after it. Files that
do not carry a known Qt generator signature are refused, so the pipeline can
never tag hand-written code.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from pathlib import Path

GENERATED_HEADER = (
    "# GENERATED FILE — DO NOT HAND-EDIT.\n"
    "# Regenerate: bash scripts/compile_ui.sh (pyside6-uic + "
    "fix_generated_ui_enums + tokenize_forms) or pyside6-rcc / "
    "scripts/build-breeze.sh for resources.\n"
)

_HEADER_MARKER = "GENERATED FILE — DO NOT HAND-EDIT"

# Stock banner lines emitted by each generator. A file only qualifies as
# generated when every signature of one set is present — the same
# content-based recognition ``fix_generated_ui_enums`` relies on, so inserting
# the header can never break detection.
_UIC_SIGNATURES = (
    "Form generated from reading UI file",
    "Created by: Qt User Interface Compiler version",
)
_RCC_SIGNATURES = (
    "Resource object code",
    "Created by: The Resource Compiler for Qt",
)

_CODING_COOKIE_RE = re.compile(r"^[ \t]*#.*coding[:=]")


def is_generated_file(content: str) -> bool:
    """Return True if *content* carries a known Qt generator signature."""
    return any(
        all(signature in content for signature in signatures)
        for signatures in (_UIC_SIGNATURES, _RCC_SIGNATURES)
    )


def _insertion_index(lines: list[str]) -> int:
    """Return the line index the header goes at, honoring PEP 263.

    A shebang stays on line 1 and a ``coding`` cookie stays within the first
    two lines; the header is inserted right after that prefix, else at line 1.
    """
    index = 0
    if lines and lines[0].startswith("#!"):
        index = 1
    if index < len(lines) and index < 2 and _CODING_COOKIE_RE.match(lines[index]):
        index += 1
    return index


def add_header(path: Path) -> bool:
    """Insert :data:`GENERATED_HEADER` into a generated ``.py`` file in place.

    Returns ``True`` when the file was written, ``False`` when the marker was
    already present (idempotent no-op).

    Raises:
        ValueError: If the path is not a ``.py`` file or does not carry a
            known Qt generator signature — never tag hand-written code.
    """
    if path.suffix != ".py":
        raise ValueError(f"expected a .py generated file, got {path.suffix!r}")

    content = path.read_text(encoding="utf-8")
    if _HEADER_MARKER in content:
        return False
    if not is_generated_file(content):
        raise ValueError(
            f"{path} does not contain a Qt generator signature; refusing to tag"
        )

    lines = content.splitlines(keepends=True)
    index = _insertion_index(lines)
    lines[index:index] = [GENERATED_HEADER]
    path.write_text("".join(lines), encoding="utf-8")
    return True


def main(argv: Sequence[str] | None = None) -> int:
    """CLI: prepend the project header to each explicit generated ``.py`` path.

    Prints a summary and returns 0 when every path is a valid generated file.
    Returns a non-zero status if any path is missing, unreadable, or not
    generated — the pipeline must not silently tag source files.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Prepend the project generated-file header to pyside6-uic / "
            "pyside6-rcc generated .py files."
        )
    )
    parser.add_argument("paths", nargs="+", type=Path, help="generated .py files")
    args = parser.parse_args(argv[1:] if argv else None)

    changed = 0
    unchanged = 0
    invalid = 0

    for path in args.paths:
        try:
            if add_header(path):
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
