import logging
import logging.handlers
import os
import sys
from datetime import datetime
from typing import Any, Optional, Tuple
from zoneinfo import ZoneInfo

from config import (
    ACTIVE_AUTH_DIR,
    APP_LOG_FILE_PATH,
    JSON_LOGS_ENABLED,
    LOG_DIR,
    LOG_FILE_BACKUP_COUNT,
    LOG_FILE_MAX_BYTES,
    SAVED_AUTH_DIR,
)
from models import StreamToLogger, WebSocketConnectionManager, WebSocketLogHandler

from .core.error_handler import setup_global_exception_handlers
from .grid_logger import (
    GridFormatter,
    JSONFormatter,
    PlainGridFormatter,
)


class ColoredFormatter(logging.Formatter):
    """Cross-platform colored formatter using ANSI codes (legacy, kept for compatibility)."""

    COLORS = {
        "DEBUG": "\033[36m",
        "INFO": "\033[0m",
        "WARNING": "\033[93m",
        "ERROR": "\033[91m",
        "CRITICAL": "\033[41m\033[97m",
    }
    RESET = "\033[0m"

    def __init__(
        self, fmt: Any = None, datefmt: Any = None, use_color: bool = True
    ) -> None:
        super().__init__(fmt, datefmt)
        self.use_color = use_color

        if use_color and sys.platform == "win32":
            try:
                import ctypes

                kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
                kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
            except Exception:
                self.use_color = False

    def formatTime(self, record: logging.LogRecord, datefmt: Any = None) -> str:
        dt = datetime.fromtimestamp(record.created, tz=ZoneInfo("America/Chicago"))
        if datefmt:
            s = dt.strftime(datefmt)
        else:
            s = dt.strftime("%Y-%m-%d %H:%M:%S")
            s = "%s,%03d" % (s, record.msecs)
        return s

    def format(self, record: logging.LogRecord) -> str:
        if self.use_color and record.levelname in self.COLORS:
            original_levelname = record.levelname
            record.levelname = (
                f"{self.COLORS[record.levelname]}{record.levelname}{self.RESET}"
            )
            result = super().format(record)
            record.levelname = original_levelname
            return result
        return super().format(record)


def setup_server_logging(
    logger_instance: logging.Logger,
    log_ws_manager: Optional[WebSocketConnectionManager],
    log_level_name: str = "INFO",
    redirect_print_str: str = "false",
) -> Tuple[object, object]:
    """
    Setup server logging system

    Args:
        logger_instance: Main logger instance
        log_ws_manager: WebSocket connection manager
        log_level_name: Log level name
        redirect_print_str: Whether to redirect print output

    Returns:
        Tuple[object, object]: Original stdout and stderr streams
    """
    log_level = getattr(logging, log_level_name.upper(), logging.INFO)
    redirect_print = redirect_print_str.lower() in ("true", "1", "yes")

    # Create necessary directories
    os.makedirs(LOG_DIR, exist_ok=True)
    os.makedirs(ACTIVE_AUTH_DIR, exist_ok=True)
    os.makedirs(SAVED_AUTH_DIR, exist_ok=True)

    # Clear existing handlers
    if logger_instance.hasHandlers():
        logger_instance.handlers.clear()
    logger_instance.setLevel(log_level)
    logger_instance.propagate = False

    # Remove old log file
    if os.path.exists(APP_LOG_FILE_PATH):
        try:
            os.remove(APP_LOG_FILE_PATH)
        except OSError as e:
            print(
                f"Warning (setup_server_logging): Failed to remove old app.log file '{APP_LOG_FILE_PATH}': {e}. Will rely on mode='w' for truncation.",
                file=sys.__stderr__,
            )

    # Use JSONFormatter for file logging if JSON_LOGS_ENABLED, otherwise PlainGridFormatter
    if JSON_LOGS_ENABLED:
        file_log_formatter = JSONFormatter()
    else:
        file_log_formatter = PlainGridFormatter()

    file_handler = logging.handlers.RotatingFileHandler(
        APP_LOG_FILE_PATH,
        maxBytes=LOG_FILE_MAX_BYTES,
        backupCount=LOG_FILE_BACKUP_COUNT,
        encoding="utf-8",
        mode="w",
    )
    file_handler.setFormatter(file_log_formatter)
    file_handler.setLevel(log_level)
    logger_instance.addHandler(file_handler)

    # Add WebSocket handler
    if log_ws_manager is None:
        print(
            "Critical Warning (setup_server_logging): log_ws_manager not initialized! WebSocket logging will be unavailable.",
            file=sys.__stderr__,
        )
    else:
        ws_handler = WebSocketLogHandler(log_ws_manager)
        ws_handler.setLevel(log_level)
        ws_handler.setFormatter(PlainGridFormatter())
        logger_instance.addHandler(ws_handler)

    # Add console handler (using GridFormatter with color)
    console_grid_formatter = GridFormatter(show_tree=True, colorize=True)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(console_grid_formatter)
    console_handler.setLevel(log_level)
    logger_instance.addHandler(console_handler)

    # Add AbortError filter (benign errors from Playwright navigation cancellations)
    from logging_utils import AbortErrorFilter

    logger_instance.addFilter(AbortErrorFilter())

    # Save original streams
    original_stdout = sys.stdout
    original_stderr = sys.stderr

    # Redirect print output (if needed)
    if redirect_print:
        print(
            "--- Note: server.py is redirecting its print output to the logging system (File, WebSocket, and Console logger) ---",
            file=original_stderr,
        )
        stdout_redirect_logger = logging.getLogger("AIStudioProxyServer.stdout")
        stdout_redirect_logger.setLevel(logging.INFO)
        stdout_redirect_logger.propagate = True
        sys.stdout = StreamToLogger(stdout_redirect_logger, logging.INFO)
        stderr_redirect_logger = logging.getLogger("AIStudioProxyServer.stderr")
        stderr_redirect_logger.setLevel(logging.ERROR)
        stderr_redirect_logger.propagate = True
        sys.stderr = StreamToLogger(stderr_redirect_logger, logging.ERROR)
    else:
        print(
            "--- server.py print output is NOT redirected to logging system (using original stdout/stderr) ---",
            file=original_stderr,
        )

    # Configure third-party library log levels
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("websockets").setLevel(logging.WARNING)
    logging.getLogger("playwright").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.ERROR)

    # Log initialization info
    logger_instance.info(
        "=" * 5
        + " AIStudioProxyServer Logging System Initialized in lifespan "
        + "=" * 5
    )
    logger_instance.info(f"Log level set to: {logging.getLevelName(log_level)}")
    logger_instance.debug(f"Log file path: {APP_LOG_FILE_PATH}")
    logger_instance.info("Console log handler added.")
    logger_instance.info(
        f"Print Redirection (controlled by SERVER_REDIRECT_PRINT env var): {'Enabled' if redirect_print else 'Disabled'}"
    )

    # Install global exception handlers
    setup_global_exception_handlers()

    return original_stdout, original_stderr


def restore_original_streams(original_stdout: object, original_stderr: object) -> None:
    """
    Restore original stdout and stderr streams

    Args:
        original_stdout: Original stdout stream
        original_stderr: Original stderr stream
    """
    sys.stdout = original_stdout
    sys.stderr = original_stderr
