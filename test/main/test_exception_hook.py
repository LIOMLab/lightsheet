"""Verify the module-level ``_exception_hook`` is safe under ``pythonw``.

Under a no-console launch ``sys.stderr`` is ``None``; the hook must never
``print()``, must log to the rotating file, and must fall back to a crash
file when logging is not configured.
"""

import logging
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest


def test_hook_logs_to_root_logger_when_handlers_configured(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """With root handlers present, the hook emits a CRITICAL log and exits 1."""
    import lightsheet.__main__

    # Ensure at least one handler exists so the logging branch is taken.
    root = logging.getLogger()
    handler = logging.StreamHandler()
    handler.setLevel(logging.CRITICAL)
    root.addHandler(handler)
    try:
        original = Mock()
        monkeypatch.setattr(lightsheet.__main__, "_original_excepthook", original)
        exits: list[int] = []
        monkeypatch.setattr(sys, "exit", lambda code: exits.append(code))
        with caplog.at_level(logging.CRITICAL):
            lightsheet.__main__._exception_hook(
                ValueError, ValueError("boom"), None
            )
        assert 1 in exits
        assert "boom" in caplog.text
        assert original.called, "exception hook did not forward to original excepthook"
    finally:
        root.removeHandler(handler)


def test_hook_writes_crash_file_when_no_handlers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """With no root handlers, the hook writes a crash file and exits 1."""
    import lightsheet.__main__
    import lightsheet.logging_setup

    monkeypatch.setattr(logging.getLogger(), "handlers", [])
    monkeypatch.setattr(
        lightsheet.logging_setup, "_default_log_dir", lambda: tmp_path
    )
    exits: list[int] = []
    monkeypatch.setattr(sys, "exit", lambda code: exits.append(code))

    lightsheet.__main__._exception_hook(ValueError, ValueError("boom"), None)

    crash = tmp_path / "lightsheet-crash.log"
    assert crash.is_file(), "crash file not written"
    assert "ValueError" in crash.read_text(encoding="utf-8")
    assert 1 in exits


def test_hook_forwards_only_when_stderr_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The original excepthook is invoked only when ``sys.stderr`` exists."""
    import lightsheet.__main__

    original = Mock()
    monkeypatch.setattr(lightsheet.__main__, "_original_excepthook", original)
    exits: list[int] = []
    monkeypatch.setattr(sys, "exit", lambda code: exits.append(code))

    # sys.stderr = None -> original hook must not be called.
    monkeypatch.setattr(sys, "stderr", None)
    lightsheet.__main__._exception_hook(ValueError, ValueError("silent"), None)
    assert not original.called

    # sys.stderr present -> original hook IS forwarded.
    monkeypatch.setattr(sys, "stderr", sys.__stderr__)
    lightsheet.__main__._exception_hook(ValueError, ValueError("forwarded"), None)
    assert original.called
    assert 1 in exits
