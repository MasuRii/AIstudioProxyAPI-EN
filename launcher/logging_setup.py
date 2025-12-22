import logging
import logging.handlers
import os
import sys

from launcher.config import LAUNCHER_LOG_FILE_PATH, LOG_DIR
from logging_utils import GridFormatter, PlainGridFormatter, set_source

logger = logging.getLogger("CamoufoxLauncher")


def setup_launcher_logging(log_level: int = logging.INFO) -> None:
    """
    Set up launcher logging system (using GridFormatter)

    Args:
        log_level: Log level
    """
    os.makedirs(LOG_DIR, exist_ok=True)

    # Set source to LAUNCHER
    set_source("LAUNCHER")

    # Use PlainGridFormatter for file logging
    file_log_formatter = PlainGridFormatter()

    # Use GridFormatter for console (colored output)
    console_log_formatter = GridFormatter(show_tree=True, colorize=True)

    if logger.hasHandlers():
        logger.handlers.clear()
    logger.setLevel(log_level)
    logger.propagate = False

    if os.path.exists(LAUNCHER_LOG_FILE_PATH):
        try:
            os.remove(LAUNCHER_LOG_FILE_PATH)
        except OSError:
            pass

    file_handler = logging.handlers.RotatingFileHandler(
        LAUNCHER_LOG_FILE_PATH,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding="utf-8",
        mode="w",
    )
    file_handler.setFormatter(file_log_formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setFormatter(console_log_formatter)
    logger.addHandler(stream_handler)

    logger.info(f"Log level set to: {logging.getLevelName(logger.getEffectiveLevel())}")
    logger.debug(f"Log file path: {LAUNCHER_LOG_FILE_PATH}")
