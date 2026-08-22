"""
Behavior tests for lightsheet.logging_setup.configure.

Exercises the real configure() at runtime — no source-text inspection
(AGENTS.md §5). Each test runs in an isolated CWD (tmp_path) so the
cfg_read('config.ini', ...) call inside configure() reads from the temp
directory. An autouse fixture snapshots and restores the root logger's
handlers and level so no handler leaks across tests.
"""

import logging
import logging.handlers
from pathlib import Path

import pytest

from lightsheet.logging_setup import configure


@pytest.fixture(autouse=True)
def _save_root_logger() -> object:
    """Snapshot and restore the root logger around every test.

    configure() mutates the root logger's handlers and level. Without
    restoration, handlers attached in one test (a RotatingFileHandler
    holding an open file descriptor to tmp_path) would leak into the
    next test and into the rest of the suite.
    """
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_level = root.level
    yield
    for handler in list(root.handlers):
        root.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass
    for handler in saved_handlers:
        root.addHandler(handler)
    root.setLevel(saved_level)


def test_configure_attaches_rotating_file_and_stream_handlers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no config.ini present (defaults apply), configure() leaves the
    root logger with at least one RotatingFileHandler and one StreamHandler."""
    monkeypatch.chdir(tmp_path)
    configure()
    root = logging.getLogger()
    has_rotating = any(isinstance(h, logging.handlers.RotatingFileHandler) for h in root.handlers)
    has_stream = any(isinstance(h, logging.StreamHandler) for h in root.handlers)
    assert has_rotating, f"no RotatingFileHandler in {root.handlers}"
    assert has_stream, f"no StreamHandler in {root.handlers}"


def test_configure_sets_root_level_from_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A config.ini with [Logging] Level = DEBUG sets the root logger to DEBUG."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.ini").write_text(
        "[Logging]\nLevel = DEBUG\nLog Dir = \n",
        encoding="utf-8",
    )
    configure()
    assert logging.getLogger().level == logging.DEBUG


def test_configure_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Calling configure() twice does not duplicate handlers on the root logger."""
    monkeypatch.chdir(tmp_path)
    configure()
    count_after_one = len(logging.getLogger().handlers)
    configure()
    count_after_two = len(logging.getLogger().handlers)
    assert count_after_two == count_after_one


def test_logger_exception_writes_to_log_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A logger.exception(...) call writes a timestamped entry containing the
    message text to a *.log file under tmp_path/logs/."""
    monkeypatch.chdir(tmp_path)
    configure()
    test_logger = logging.getLogger("test_module")
    try:
        raise RuntimeError("synthetic failure for log-file test")
    except RuntimeError:
        test_logger.exception("boom")
    for handler in logging.getLogger().handlers:
        handler.flush()
    log_files = list((tmp_path / "logs").glob("*.log"))
    assert log_files, f"no *.log file under {tmp_path / 'logs'}"
    contents = "\n".join(p.read_text(encoding="utf-8") for p in log_files)
    assert "boom" in contents
