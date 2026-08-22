"""TST-03 safe_char filename-validation corpus.

Execs the REAL ``Controller_MainWindow.validate_file_name`` body (via the
``_load_method`` exec-against-Mock pattern from
``test/test_laser_controls.py``) against a Mock stand-in ``self`` whose
``ui.lineEdit_saveFilename`` returns the corpus input. This runs the real
sanitization code — the same code that runs on the rig — without needing
a Qt event loop or display (AGENTS.md §5: no static-source grep).

The corpus locks the ``safe_char`` behavior (alnum + ``-`` kept; everything
else → ``_``; trailing ``_`` stripped; ``os.path.normpath`` joins
``save_directory + \"\\\\\" + save_filename``) before the Phase 5 god-object
split. There is NO ``QRegExp`` in this codebase (RESEARCH Correction 1) —
the corpus targets ``safe_char`` + ``rstrip(\"_\")`` + the Windows path
join, not a regex port.

Inline ``@pytest.mark.parametrize`` (D-13 — no JSON/YAML data file): the
corpus is small, semantically stable, and readable at the assertion site.
"""

import os
import re
from collections.abc import Callable
from typing import Any
from unittest.mock import Mock

import pytest

_CONTROLLER_SRC = os.path.join(
    os.path.dirname(__file__), "..", "lightsheet", "gui", "controller.py"
)


def _read_controller_source() -> str:
    with open(_CONTROLLER_SRC) as f:
        return f.read()


def _slice_method(src: str, method_sig: str) -> str:
    m = re.search(r"def " + re.escape(method_sig) + r":", src)
    assert m, f"{method_sig} is missing"
    body = src[m.start():]
    end = re.search(r"\n    def |\n    @pyqtSlot", body[1:])
    if end:
        body = body[: end.start() + 1]
    return body


def _load_method(method_sig: str) -> Callable[..., Any]:
    """Extract a method body from controller.py and return a callable.

    The exec namespace is seeded with ``os`` (the body calls
    ``os.path.normpath``) so the function resolves it at call time.
    """
    src = _read_controller_source()
    body = _slice_method(src, method_sig)
    namespace: dict[str, Any] = {"os": os}
    exec(compile(body, _CONTROLLER_SRC, "exec"), namespace)
    func_name = method_sig.split("(")[0].strip()
    return namespace[func_name]


_validate = _load_method("validate_file_name(self) -> None")


def _standin(text: str, save_dir: str = "C:\\data") -> Mock:
    """Build a Mock stand-in self for validate_file_name.

    The method reads ``self.ui.lineEdit_saveFilename.text()``, sanitizes
    it into ``self.save_filename``, and sets ``self.saving_allowed`` based
    on whether both ``save_directory`` and ``save_filename`` are non-empty.
    """
    s = Mock()
    s.ui.lineEdit_saveFilename.text.return_value = text
    s.save_directory = save_dir
    s.save_filename = ""
    s.saving_allowed = False
    return s


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
def test_safe_char_sanitizes(raw: str, expected_substring: str,
                             allows: bool) -> None:
    """validate_file_name sanitizes the filename via safe_char + rstrip('_')
    and joins it to save_directory; saving_allowed is True only when both
    are non-empty."""
    s = _standin(raw)
    _validate(s)
    if allows:
        assert s.saving_allowed is True
        assert expected_substring in s.save_filename, (
            f"expected {expected_substring!r} in save_filename="
            f"{s.save_filename!r}"
        )
    else:
        assert s.saving_allowed is False


def test_safe_char_join_uses_save_directory() -> None:
    """The sanitized filename is joined to save_directory via
    os.path.normpath(save_directory + '\\\\' + save_filename). On a
    non-Windows host normpath collapses the backslash separator, so we
    assert the sanitized name is present and the directory appears in the
    joined path."""
    s = _standin("plane 01", save_dir="/tmp/data")
    _validate(s)
    assert s.saving_allowed is True
    # normpath on POSIX collapses the Windows separator: /tmp/data\plane_01
    # → /tmp/data/plane_01. On Windows it stays /tmp/data\plane_01. Either
    # way the sanitized name and the directory are both present.
    assert "plane_01" in s.save_filename
    assert "tmp" in s.save_filename or "data" in s.save_filename
