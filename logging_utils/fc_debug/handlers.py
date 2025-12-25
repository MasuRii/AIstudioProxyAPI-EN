"""
FC Debug File Handlers.

Factory functions for creating RotatingFileHandler instances
for each FC debug module.
"""

import logging
import logging.handlers
from pathlib import Path
from typing import Optional

from .formatters import FCDebugFormatter


def create_rotating_file_handler(
    log_path: Path,
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 3,
    level: int = logging.DEBUG,
    formatter: Optional[logging.Formatter] = None,
) -> logging.handlers.RotatingFileHandler:
    """
    Create a rotating file handler for FC debug logs.

    Args:
        log_path: Path to the log file
        max_bytes: Maximum file size before rotation (default 5MB)
        backup_count: Number of backup files to keep (default 3)
        level: Log level for the handler
        formatter: Custom formatter (defaults to FCDebugFormatter)

    Returns:
        Configured RotatingFileHandler
    """
    handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )

    if formatter is None:
        formatter = FCDebugFormatter()

    handler.setFormatter(formatter)
    handler.setLevel(level)

    return handler


def ensure_log_directory(log_dir: Path) -> None:
    """
    Ensure the log directory exists.

    Args:
        log_dir: Path to the log directory
    """
    log_dir.mkdir(parents=True, exist_ok=True)
