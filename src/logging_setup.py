"""Root-logger configuration for the lightsheet microscope controller.

``configure()`` is called once from ``lightsheet.__main__.main()`` BEFORE
the first hardware init, replacing the bare one-shot logging setup that
the entry point used to call. It attaches a size-bounded
``RotatingFileHandler`` (5 MB x 5, ~25 MB disk ceiling) and a
``StreamHandler`` to the root logger, both using the mesoSPIM timestamped
format, and reads its level + log directory from the ``[Logging]`` section
of ``config.ini`` via the ``cfg_read`` helper.

This is the infrastructure that per-module ``logger = logging.getLogger(__name__)``
calls (added to every HAL module) propagate up to. A HAL error logged via
``logger.exception(...)`` therefore leaves a persistent, timestamped,
module-attributed entry on disk — the forensic trail the project requires.
"""

import logging
import logging.handlers
import sys
from pathlib import Path

from lightsheet.config import cfg_read

# Defaults declared here so cfg_read overlays INI values onto them. cfg_read
# only updates keys present in this dict, so any key read at runtime MUST be
# declared here or it is silently ignored.
_LOG_DEFAULTS = {
    "Level": "INFO",  # Logging level: INFO or DEBUG
    "Log Dir": "",  # Empty = platform-aware default (see _default_log_dir)
}

# mesoSPIM-style timestamped format: time - logger name - level - message.
_LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


def _default_log_dir() -> Path:
    """Platform-aware default log directory.

    On Windows the rig stores logs under the operator's Documents folder
    (alongside the LightSheetData acquisition directory). On macOS dev the
    default is a local ``./logs`` directory in the CWD.
    """
    if sys.platform == "win32":
        return Path.home() / "Documents" / "LightSheetData" / "logs"
    return Path("./logs")


def configure() -> None:
    """Configure the root logger with a RotatingFileHandler + StreamHandler.

    Reads ``[Logging] Level`` and ``[Logging] Log Dir`` from ``config.ini``
    (relative to the current working directory) via ``cfg_read``, falling
    back to ``_LOG_DEFAULTS`` when the file or section is absent. Idempotent:
    repeated calls remove existing handlers before attaching fresh ones, so
    the root logger never accumulates duplicate handlers.
    """
    cfg = cfg_read("config.ini", "Logging", dict(_LOG_DEFAULTS))

    level_name = cfg["Level"].upper()
    level = getattr(logging, level_name, logging.INFO)

    log_dir_value = cfg["Log Dir"].strip()
    log_dir = Path(log_dir_value) if log_dir_value else _default_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(level)

    # Remove existing handlers so repeated configure() calls do not duplicate
    # them. We attach handlers explicitly rather than relying on the
    # logging module's one-shot basic-config helper, which is a no-op once
    # handlers exist and would not let us replace them cleanly.
    for handler in list(root.handlers):
        root.removeHandler(handler)

    formatter = logging.Formatter(_LOG_FORMAT)

    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "lightsheet.log",
        maxBytes=5_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)
