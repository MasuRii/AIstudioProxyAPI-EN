import logging
import logging.handlers
import os
import sys
from typing import Tuple

class SSLWarningFilter(logging.Filter):
    def filter(self, record):
        return "APPLICATION_DATA_AFTER_CLOSE_NOTIFY" not in record.getMessage()

from config import LOG_DIR, ACTIVE_AUTH_DIR, SAVED_AUTH_DIR, APP_LOG_FILE_PATH
from models import StreamToLogger, WebSocketLogHandler, WebSocketConnectionManager


def setup_server_logging(
    logger_instance: logging.Logger,
    log_ws_manager: WebSocketConnectionManager,
    log_level_name: str = "INFO",
    redirect_print_str: str = "false"
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
    redirect_print = redirect_print_str.lower() in ('true', '1', 'yes')
    
    # Create necessary directories
    os.makedirs(LOG_DIR, exist_ok=True)
    os.makedirs(ACTIVE_AUTH_DIR, exist_ok=True)
    os.makedirs(SAVED_AUTH_DIR, exist_ok=True)
    
    # Setup file log formatter
    file_log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(name)s:%(funcName)s:%(lineno)d] - %(message)s')
    
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
            print(f"Warning (setup_server_logging): Failed to remove old app.log file '{APP_LOG_FILE_PATH}': {e}. Will rely on mode='w' for truncation.", file=sys.__stderr__)
    
    # Add file handler
    file_handler = logging.handlers.RotatingFileHandler(
        APP_LOG_FILE_PATH, maxBytes=5*1024*1024, backupCount=5, encoding='utf-8', mode='w'
    )
    file_handler.setFormatter(file_log_formatter)
    logger_instance.addHandler(file_handler)
    
    # Add WebSocket handler
    if log_ws_manager is None:
        print("Critical Warning (setup_server_logging): log_ws_manager not initialized! WebSocket logging will be unavailable.", file=sys.__stderr__)
    else:
        ws_handler = WebSocketLogHandler(log_ws_manager)
        ws_handler.setLevel(logging.INFO)
        logger_instance.addHandler(ws_handler)
    
    # Add console handler
    console_server_log_formatter = logging.Formatter('%(asctime)s - %(levelname)s [SERVER] - %(message)s')
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(console_server_log_formatter)
    console_handler.setLevel(log_level)
    logger_instance.addHandler(console_handler)
    
    # Save original streams
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    
    # Redirect print output (if needed)
    if redirect_print:
        print("--- Note: server.py is redirecting its print output to the logging system (File, WebSocket, and Console logger) ---", file=original_stderr)
        stdout_redirect_logger = logging.getLogger("AIStudioProxyServer.stdout")
        stdout_redirect_logger.setLevel(logging.INFO)
        stdout_redirect_logger.propagate = True
        sys.stdout = StreamToLogger(stdout_redirect_logger, logging.INFO)
        stderr_redirect_logger = logging.getLogger("AIStudioProxyServer.stderr")
        stderr_redirect_logger.setLevel(logging.ERROR)
        stderr_redirect_logger.propagate = True
        sys.stderr = StreamToLogger(stderr_redirect_logger, logging.ERROR)
    else:
        print("--- server.py print output is NOT redirected to logging system (using original stdout/stderr) ---", file=original_stderr)
    
    # Configure third-party library log levels
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("websockets").setLevel(logging.WARNING)
    logging.getLogger("playwright").setLevel(logging.WARNING)
    
    # Suppress asyncio/SSL warnings
    asyncio_logger = logging.getLogger("asyncio")
    asyncio_logger.setLevel(logging.CRITICAL)
    asyncio_logger.addFilter(SSLWarningFilter())
    
    # Log initialization info
    logger_instance.info("=" * 5 + " AIStudioProxyServer Logging System Initialized in lifespan " + "=" * 5)
    logger_instance.info(f"Log level set to: {logging.getLevelName(log_level)}")
    logger_instance.info(f"Log file path: {APP_LOG_FILE_PATH}")
    logger_instance.info(f"Console log handler added.")
    logger_instance.info(f"Print Redirection (controlled by SERVER_REDIRECT_PRINT env var): {'Enabled' if redirect_print else 'Disabled'}")
    
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
    print("Restored server.py original stdout and stderr streams.", file=sys.__stderr__)