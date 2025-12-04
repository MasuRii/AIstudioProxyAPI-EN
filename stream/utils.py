import logging
from typing import Optional, Tuple
from urllib.parse import urlparse

from logging_utils.grid_logger import GridFormatter


def is_generate_content_endpoint(url: str) -> bool:
    """
    Check if the URL is a GenerateContent endpoint
    """
    return "GenerateContent" in url


def parse_proxy_url(
    proxy_url: Optional[str],
) -> Tuple[Optional[str], Optional[str], Optional[int], Optional[str], Optional[str]]:
    """
    Parse a proxy URL into its components

    Returns:
        tuple: (scheme, host, port, username, password)
    """
    if not proxy_url:
        return None, None, None, None, None

    parsed = urlparse(proxy_url)

    scheme = parsed.scheme
    host = parsed.hostname
    port = parsed.port
    username = parsed.username
    password = parsed.password

    return scheme, host, port, username, password


def setup_logger(
    name: str, log_file: Optional[str] = None, level: int = logging.INFO
) -> logging.Logger:
    """
    Set up a logger with the specified name and configuration

    Args:
        name (str): Logger name
        log_file (str, optional): Path to log file
        level (int, optional): Logging level

    Returns:
        logging.Logger: Configured logger
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Console handler with colored output
    console_formatter = ColoredFormatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s", use_color=True
    )
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # Add file handler if specified (plain formatter for files)
    if log_file:
        file_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    return logger
