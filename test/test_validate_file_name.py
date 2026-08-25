"""TST-03 safe_char filename-validation corpus.

Exercises the REAL ``Controller_MainWindow.validate_file_name`` method via
real construction (``make_controller`` builds the full controller with all
four collaborators wired and ``hardware_init`` already called). The
sanitization code that runs here is the same code that runs on the rig.

The corpus locks the ``safe_char`` behavior (alnum + ``-`` kept; everything
else → ``_``; trailing ``_`` stripped; ``os.path.normpath`` joins
``save_directory + \"\\\\\" + save_filename``) before the Phase 5 god-object
split. There is NO ``QRegExp`` in this codebase (RESEARCH Correction 1) —
the corpus targets ``safe_char`` + ``rstrip(\"_\")`` + the Windows path
join, not a regex port.

Inline ``@pytest.mark.parametrize`` (D-13 — no JSON/YAML data file): the
corpus is small, semantically stable, and readable at the assertion site.
"""

import pytest

from _helpers.controller_fixture import make_controller


@pytest.mark.parametrize(
    "raw, expected_substring, allows",
    [
        # spaces → underscores; alnum kept
        ("my sample 01", "my_sample_01", True),
        # hyphens kept (safe_char passes "-" through)
        ("data-2026", "data-2026", True),
        # dots and slashes → underscores (path-injection chars sanitized)
        ("a.b/c", "a_b_c", True),
        # leading underscores survive safe_char (they become "_" which
        # rstrip("_") only strips from the RIGHT) — but the corpus case
        # "__leading" sanitizes to "__leading" then rstrip("_") →
        # "__leading" has no trailing "_", so it stays. The substring
        # "leading" must be present in the final save_filename.
        ("__leading", "leading", True),
        # empty input → save_filename stays "" → saving_allowed False
        ("", "", False),
        # all-unsafe chars → safe_char produces "!!!"→"___" → rstrip("_")
        # → "" → saving_allowed False
        ("!!!", "", False),
    ],
    ids=[
        "spaces-to-underscores",
        "hyphens-kept",
        "dots-slashes-to-underscores",
        "leading-underscores",
        "empty-rejected",
        "all-unsafe-rejected",
    ],
)
def test_safe_char_sanitizes(
    qtbot, request, raw: str, expected_substring: str, allows: bool
) -> None:
    """validate_file_name sanitizes the filename via safe_char + rstrip('_')
    and joins it to save_directory; saving_allowed is True only when both
    are non-empty."""
    ctrl, _ = make_controller(qtbot, request)
    ctrl.ui.lineEdit_saveFilename.setText(raw)
    ctrl.save_directory = "C:\\data"
    ctrl.save_filename = ""
    ctrl.saving_allowed = False
    ctrl.save_panel.validate_file_name()
    if allows:
        assert ctrl.saving_allowed is True
        assert expected_substring in ctrl.save_filename, (
            f"expected {expected_substring!r} in save_filename={ctrl.save_filename!r}"
        )
    else:
        assert ctrl.saving_allowed is False


def test_safe_char_join_uses_save_directory(qtbot, request) -> None:
    """The sanitized filename is joined to save_directory via
    os.path.normpath(save_directory + '\\\\' + save_filename). On a
    non-Windows host normpath collapses the backslash separator, so we
    assert the sanitized name is present and the directory appears in the
    joined path."""
    ctrl, _ = make_controller(qtbot, request)
    ctrl.ui.lineEdit_saveFilename.setText("plane 01")
    ctrl.save_directory = "/tmp/data"
    ctrl.save_filename = ""
    ctrl.saving_allowed = False
    ctrl.save_panel.validate_file_name()
    assert ctrl.saving_allowed is True
    # normpath on POSIX collapses the Windows separator: /tmp/data\plane_01
    # → /tmp/data/plane_01. On Windows it stays /tmp/data\plane_01. Either
    # way the sanitized name and the directory are both present.
    assert "plane_01" in ctrl.save_filename
    assert "tmp" in ctrl.save_filename or "data" in ctrl.save_filename
