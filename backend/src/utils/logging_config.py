"""Centralized logging configuration for OctoAgent backend.

Usage:
    # In gateway/app.py (called once at startup):
    from src.utils.logging_config import setup_logging
    setup_logging()

    # In any module:
    import logging
    logger = logging.getLogger(__name__)
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_LOG_FORMAT = "%(asctime)s.%(msecs)03d - %(name)s - %(levelname)s - %(message)s"
_LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"

# Defaults — override via environment variables
_DEFAULT_LOG_LEVEL = "INFO"
_DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10 MB per file
_DEFAULT_BACKUP_COUNT = 5  # keep 5 rotated copies

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_log_dir() -> Path:
    """Return the project ``logs/`` directory, creating it if needed."""
    log_dir = Path(__file__).resolve().parents[3] / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def _make_file_handler(
    log_path: Path,
    level: int,
    max_bytes: int,
    backup_count: int,
) -> RotatingFileHandler:
    handler = RotatingFileHandler(
        log_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_LOG_DATEFMT))
    return handler


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def setup_logging() -> None:
    """Configure the root logger with console + rotating file handlers.

    Environment variables:
        ``LOG_LEVEL``        – root log level (default ``INFO``)
        ``LOG_MAX_BYTES``    – max bytes per log file before rotation (default 10 MB)
        ``LOG_BACKUP_COUNT`` – number of rotated backups to keep (default 5)
    """
    level_name = os.environ.get("LOG_LEVEL", _DEFAULT_LOG_LEVEL).upper()
    level = getattr(logging, level_name, logging.INFO)
    max_bytes = int(os.environ.get("LOG_MAX_BYTES", _DEFAULT_MAX_BYTES))
    backup_count = int(os.environ.get("LOG_BACKUP_COUNT", _DEFAULT_BACKUP_COUNT))

    root = logging.getLogger()

    # Avoid duplicate handler registration on reload / double-import
    if any(
        isinstance(h, RotatingFileHandler)
        and getattr(h, "_octoagent_marker", False)
        for h in root.handlers
    ):
        return

    root.setLevel(level)

    # ---- Console handler (stdout) ----
    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_LOG_DATEFMT))
    root.addHandler(console)

    # ---- Rotating file handler: gateway.log ----
    log_dir = _resolve_log_dir()
    file_handler = _make_file_handler(
        log_dir / "gateway.log",
        level=level,
        max_bytes=max_bytes,
        backup_count=backup_count,
    )
    file_handler._octoagent_marker = True  # type: ignore[attr-defined]
    root.addHandler(file_handler)

    # Quieten noisy third-party loggers
    for name in (
        "httpcore",
        "httpx",
        "urllib3",
        "watchfiles",
        "uvicorn.access",
    ):
        logging.getLogger(name).setLevel(logging.WARNING)

    logging.getLogger(__name__).info(
        "Logging initialised  level=%s  file=%s  maxBytes=%s  backups=%d",
        level_name,
        log_dir / "gateway.log",
        max_bytes,
        backup_count,
    )
