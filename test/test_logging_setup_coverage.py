"""Branch-coverage closure for ``lightsheet.logging_setup.configure``.

Covers the OSError fallback chain (lines 77-97) and the
``if log_dir is not None:`` False branch (112->122) — the stream-only
fallback when every candidate log directory is unwritable.

The fallback ladder inside ``configure()``:
  1. configured Log Dir .mkdir() raises OSError
  2. _default_log_dir() .mkdir() raises OSError
  3. tempfile.gettempdir()/lightsheet-logs .mkdir() raises OSError
     -> log_dir = None -> stream-only (no RotatingFileHandler attached)

Each test forces a specific rung of the ladder by making the targeted
``Path.mkdir`` raise (via a read-only parent or a monkeypatched mkdir),
then asserts on the runtime postcondition (which handlers are attached).

Behavior tests (AGENTS.md §5) — runs the real ``configure()`` and
asserts on the root logger's handler set, never a static-source grep.
"""

import contextlib
import logging
import logging.handlers
from pathlib import Path

import pytest

from lightsheet.logging_setup import configure
from lightsheet import logging_setup as logging_setup_mod


@pytest.fixture(autouse=True)
def _save_root_logger() -> object:
    """Snapshot and restore the root logger around every test (mirrors
    test_logging_setup.py — configure() mutates root handlers/level)."""
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_level = root.level
    yield
    for handler in list(root.handlers):
        root.removeHandler(handler)
        with contextlib.suppress(Exception):
            handler.close()
    for handler in saved_handlers:
        root.addHandler(handler)
    root.setLevel(saved_level)


def test_configure_falls_back_to_default_when_configured_dir_unwritable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Configured Log Dir is unwritable -> fall back to _default_log_dir()
    (lines 77-81). The default dir succeeds -> a RotatingFileHandler is
    still attached (under the default path), and the warning is emitted.

    The configured dir is a child of a read-only parent so
    ``mkdir(parents=True, exist_ok=True)`` raises OSError trying to
    create the child inside the read-only parent."""
    monkeypatch.chdir(tmp_path)
    # A read-only parent whose child cannot be created.
    ro_parent = tmp_path / "ro_parent"
    ro_parent.mkdir()
    ro_parent.chmod(0o555)
    bad_dir = ro_parent / "child"
    (tmp_path / "config.ini").write_text(
        f"[Logging]\nLevel = INFO\nLog Dir = {bad_dir}\n",
        encoding="utf-8",
    )
    # _default_log_dir() returns ./logs relative to CWD (tmp_path) on Mac;
    # that succeeds, so the fallback ladder stops at rung 2.
    configure()
    root = logging.getLogger()
    has_rotating = any(
        isinstance(h, logging.handlers.RotatingFileHandler) for h in root.handlers
    )
    has_stream = any(isinstance(h, logging.StreamHandler) for h in root.handlers)
    assert has_rotating, "fallback to default dir must still attach a file handler"
    assert has_stream


def test_configure_falls_back_to_temp_when_default_also_unwritable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both configured Log Dir AND _default_log_dir() are unwritable ->
    fall back to tempfile.gettempdir()/lightsheet-logs (lines 82-87).
    The temp dir succeeds -> a RotatingFileHandler is attached under the
    temp path, and the warning is emitted.

    _default_log_dir() is monkeypatched to return a child of a read-only
    parent so its mkdir raises; the configured Log Dir is empty so the
    default is the first candidate (rung 1 fails -> rung 2 fails -> rung 3
    succeeds)."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.ini").write_text(
        "[Logging]\nLevel = INFO\nLog Dir = \n",
        encoding="utf-8",
    )
    # _default_log_dir() returns a child of a read-only parent so rung 2
    # fails (mkdir parents=True tries to create the child inside the RO
    # parent and raises OSError).
    ro_parent = tmp_path / "ro_default_parent"
    ro_parent.mkdir()
    ro_parent.chmod(0o555)
    bad_default = ro_parent / "default_child"
    monkeypatch.setattr(
        logging_setup_mod, "_default_log_dir", lambda: bad_default
    )
    configure()
    root = logging.getLogger()
    has_rotating = any(
        isinstance(h, logging.handlers.RotatingFileHandler) for h in root.handlers
    )
    has_stream = any(isinstance(h, logging.StreamHandler) for h in root.handlers)
    assert has_rotating, "temp fallback must still attach a file handler"
    assert has_stream


def test_configure_stream_only_when_all_dirs_unwritable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """All three candidate dirs are unwritable (configured, default, AND
    temp) -> log_dir = None -> stream-only (lines 88-94 + branch
    112->122 False). No RotatingFileHandler is attached; the
    StreamHandler is, so the GUI still starts. The warning is emitted.

    ``Path.mkdir`` is monkeypatched to always raise OSError so every
    rung of the fallback ladder fails, forcing log_dir=None."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.ini").write_text(
        "[Logging]\nLevel = INFO\nLog Dir = \n",
        encoding="utf-8",
    )

    def _always_fail(self, *args, **kwargs):
        raise OSError("read-only filesystem (test fixture)")

    monkeypatch.setattr(Path, "mkdir", _always_fail)
    configure()
    root = logging.getLogger()
    has_rotating = any(
        isinstance(h, logging.handlers.RotatingFileHandler) for h in root.handlers
    )
    has_stream = any(isinstance(h, logging.StreamHandler) for h in root.handlers)
    assert not has_rotating, (
        "all dirs unwritable -> log_dir=None -> no RotatingFileHandler "
        "(branch 112->122 False)"
    )
    assert has_stream, "stream-only fallback must still attach a StreamHandler"
