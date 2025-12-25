"""
FC Debug Log Formatters.

Provides consistent formatting for FC debug logs with timestamps,
log levels, and proper structure.
"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo


class FCDebugFormatter(logging.Formatter):
    """
    Formatter for FC debug logs.

    Format: YYYY-MM-DD HH:MM:SS.mmm | LEVEL | message

    Uses America/Chicago timezone for consistency with existing Grid Logger.
    """

    def __init__(self) -> None:
        super().__init__()
        try:
            self._tz = ZoneInfo("America/Chicago")
        except Exception:
            # Fallback to UTC if timezone not available
            self._tz = ZoneInfo("UTC")

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record."""
        # Timestamp with milliseconds
        dt = datetime.fromtimestamp(record.created, tz=self._tz)
        timestamp = dt.strftime("%Y-%m-%d %H:%M:%S") + f".{int(record.msecs):03d}"

        # Level name padded to 7 chars
        level = record.levelname.ljust(7)

        # Message
        message = record.getMessage()

        # Base format
        formatted = f"{timestamp} | {level} | {message}"

        # Add exception info if present
        if record.exc_info:
            exc_text = self.formatException(record.exc_info)
            formatted += f"\n{exc_text}"

        return formatted
