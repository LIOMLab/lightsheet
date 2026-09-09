"""Verify ``logging_setup.configure`` behaves safely when ``sys.stderr``
is ``None`` (as it is under a ``pythonw`` no-console launch).
"""

import logging
import logging.handlers
import sys
from collections.abc import Generator
from pathlib import Path
from typing import TextIO

import pytest

from lightsheet.logging_setup import configure


@pytest.fixture
def _restore_root_handlers() -> Generator[None, None, None]:
    """Save root handlers before a test and restore them after.

    ``configure()`` clears root handlers; without this fixture every test
    in the session after the first would lose pytest's capture/logging.
    """
    root = logging.getLogger()
    before = list(root.handlers)
    yield
    for h in list(root.handlers):
        root.removeHandler(h)
    for h in before:
        root.addHandler(h)


def _write_config(tmp_path: Path, level: str = "INFO", log_dir: str = "") -> str:
    """Write a minimal ``[Logging]`` INI and return its path."""
    path = tmp_path / "logging.ini"
    text = f"[Logging]\nLevel = {level}\n"
    if log_dir:
        text += f"Log Dir = {log_dir}\n"
    path.write_text(text, encoding="utf-8")
    return str(path)


def _stream_handlers() -> list[logging.StreamHandler[TextIO]]:
    """Return the current root plain ``StreamHandler`` instances."""
    return [h for h in logging.getLogger().handlers if type(h) is logging.StreamHandler]  # ty: ignore[invalid-return-type]


def _file_handlers() -> list[logging.handlers.RotatingFileHandler]:
    """Return the current root ``RotatingFileHandler`` instances."""
    return [
        h
        for h in logging.getLogger().handlers
        if type(h) is logging.handlers.RotatingFileHandler
    ]


def _cwd_logs_untouched() -> tuple[bool, set[Path]]:
    """Return whether ``logs/`` exists in CWD and the files it currently holds."""
    logs_dir = Path("logs")
    if not logs_dir.exists():
        return False, set()
    return True, set(logs_dir.iterdir())


def test_configure_skips_stream_handler_when_stderr_is_none(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    _restore_root_handlers: None,
) -> None:
    """When ``sys.stderr`` is ``None`` no ``StreamHandler`` is attached."""
    monkeypatch.setattr(sys, "stderr", None)
    log_dir = tmp_path / "logs"
    config_path = _write_config(tmp_path, level="INFO", log_dir=str(log_dir))

    configure(config_path=config_path)

    assert not _stream_handlers(), (
        "StreamHandler attached even though sys.stderr is None"
    )
    # Sanity check that the file handler was still attached.
    assert _file_handlers(), "RotatingFileHandler not attached with no stderr"


def test_configure_attaches_stream_handler_when_stderr_present(
    tmp_path: Path,
    _restore_root_handlers: None,
) -> None:
    """With a real ``sys.stderr`` exactly one ``StreamHandler`` is attached."""
    log_dir = tmp_path / "logs"
    config_path = _write_config(tmp_path, level="INFO", log_dir=str(log_dir))

    configure(config_path=config_path)

    stream_handlers = _stream_handlers()
    assert len(stream_handlers) == 1, (
        f"expected one StreamHandler, got {len(stream_handlers)}"
    )


def test_configure_reads_level_and_log_dir_from_explicit_config_path(
    tmp_path: Path,
    _restore_root_handlers: None,
) -> None:
    """``configure(config_path=...)`` reads from the supplied file, not CWD."""
    log_dir = tmp_path / "configured-logs"
    config_path = _write_config(tmp_path, level="DEBUG", log_dir=str(log_dir))
    pre_existed, pre_files = _cwd_logs_untouched()

    configure(config_path=config_path)

    assert logging.getLogger().level == logging.DEBUG
    expected_log = log_dir / "lightsheet.log"
    assert expected_log.is_file(), (
        "RotatingFileHandler did not write to the configured log dir"
    )
    # With an explicit Log Dir, configure must not create or touch a CWD logs/ dir.
    if pre_existed:
        assert set(Path("logs").iterdir()) == pre_files, (
            "configure modified the CWD logs dir despite explicit Log Dir"
        )
    else:
        assert not Path("logs").exists(), (
            "configure created a CWD logs dir despite explicit Log Dir"
        )
