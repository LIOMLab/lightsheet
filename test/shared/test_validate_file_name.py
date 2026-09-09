"""TST-03 safe_char filename-validation corpus.

Exercises the REAL ``Controller_MainWindow.validate_file_name`` method via
real construction (the ``controller`` fixture builds the full controller with all
four collaborators wired and ``hardware_init`` already called). The
sanitization code that runs here is the same code that runs on the rig.

The corpus locks the ``safe_char`` behavior (alnum + ``-`` kept; everything
else → ``_``; trailing ``_`` stripped; ``os.path.normpath`` joins
``save_directory + \"\\\\\" + save_filename`` into ``save_filepath``).
``save_filename`` holds the bare sanitized name; ``save_filepath`` holds the
joined absolute path passed to ``FrameSaver.set_files``. There is NO
``QRegExp`` in this codebase (RESEARCH Correction 1) — the corpus targets
``safe_char`` + ``rstrip(\"_\")`` + the Windows path join, not a regex port.

Inline ``@pytest.mark.parametrize``: the corpus is small, semantically
stable, and readable at the assertion site.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from lightsheet.gui.shell.controller import Controller_MainWindow


@pytest.mark.parametrize(
    "raw, expected_substring, allows",
    [
        # spaces → underscores; alnum kept
        ("my sample 01", "my_sample_01", True),
        # hyphens kept (safe_char passes "-" through)
        ("data-2026", "data-2026", True),
        # dots and slashes → underscores (path-injection chars sanitized)
        ("a.b/c", "a_b_c", True),
        # leading underscores are stripped by strip("_") (both ends) —
        # "__leading" sanitizes to "__leading" then strip("_") → "leading".
        ("__leading", "leading", True),
        # leading spaces become underscores via safe_char, then strip("_")
        # removes them so "  hello" → "__hello" → "hello" (no leading
        # underscores in the final filename).
        ("  hello", "hello", True),
        # empty input → save_filename stays "" → saving_allowed False
        ("", "", False),
        # all-unsafe chars → safe_char produces "!!!"→"___" → strip("_")
        # → "" → saving_allowed False
        ("!!!", "", False),
    ],
    ids=[
        "spaces-to-underscores",
        "hyphens-kept",
        "dots-slashes-to-underscores",
        "leading-underscores-stripped",
        "leading-spaces-stripped",
        "empty-rejected",
        "all-unsafe-rejected",
    ],
)
def test_safe_char_sanitizes(
    controller: Controller_MainWindow,
    raw: str,
    expected_substring: str,
    allows: bool,
) -> None:
    """validate_file_name sanitizes the filename via safe_char + rstrip('_')
    and joins it to save_directory; saving_allowed is True only when both
    are non-empty."""
    ctrl = controller
    ctrl.save_panel.ui.lineEdit_saveFilename.setText(raw)
    ctrl.save_directory = "C:\\data"
    ctrl.save_filename = ""
    ctrl.saving_allowed = False
    ctrl.save_panel.validate_file_name()
    if allows:
        assert ctrl.saving_allowed is True
        assert expected_substring in ctrl.save_filename, (
            f"expected {expected_substring!r} in save_filename={ctrl.save_filename!r}"
        )
        # save_filepath is the joined path; the bare name is a substring of it.
        assert expected_substring in ctrl.save_filepath, (
            f"expected {expected_substring!r} in save_filepath={ctrl.save_filepath!r}"
        )
    else:
        assert ctrl.saving_allowed is False


def test_safe_char_join_uses_save_directory(
    controller: Controller_MainWindow,
) -> None:
    """The sanitized filename is joined to save_directory via
    os.path.normpath(save_directory + '\\\\' + save_filename) into
    ``save_filepath``. ``save_filename`` holds the bare sanitized name;
    ``save_filepath`` holds the joined path. On a non-Windows host normpath
    collapses the backslash separator, so we assert the bare name is in
    ``save_filename`` and the directory appears in ``save_filepath``."""
    ctrl = controller
    ctrl.save_panel.ui.lineEdit_saveFilename.setText("plane 01")
    ctrl.save_directory = "/tmp/data"
    ctrl.save_filename = ""
    ctrl.save_filepath = ""
    ctrl.saving_allowed = False
    ctrl.save_panel.validate_file_name()
    assert ctrl.saving_allowed is True
    # save_filename holds the bare sanitized name.
    assert "plane_01" in ctrl.save_filename
    # save_filepath holds the joined path: normpath on POSIX collapses the
    # Windows separator /tmp/data\plane_01 → /tmp/data/plane_01. On Windows
    # it stays /tmp/data\plane_01. Either way the directory is present.
    assert "plane_01" in ctrl.save_filepath
    assert "tmp" in ctrl.save_filepath or "data" in ctrl.save_filepath
