"""
Grid-Based Professional Logging System v2.0
============================================
A verbose but clean logging system with:
- Fixed-width grid layout for perfect column alignment
- Hierarchical ASCII tree structure for nested operations
- Semantic syntax highlighting for values and tokens
- Burst suppression (deduplication) for repeated messages
- Progress indicators that update on the same line
- Thread-safe context variables for request tracking

Author: AI Studio Proxy API
License: MIT
"""

from __future__ import annotations

import logging
import re
import sys
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from typing import Any, Dict, Generator, List, Optional, Tuple

# Cross-platform color support
from colorama import Fore, Style
from colorama import init as colorama_init

# =============================================================================
# Initialize colorama for Windows compatibility
# =============================================================================
colorama_init(autoreset=False)

# Enable Windows 10+ ANSI support
if sys.platform == "win32":
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except Exception:
        pass  # Graceful fallback


# =============================================================================
# Context Variables (Thread-safe request tracking)
# =============================================================================

# Request ID for the current context (e.g., 'akvdate')
request_id_var: ContextVar[str] = ContextVar("request_id", default="       ")

# Source identifier for the current context (e.g., 'SERVER', 'PROXY')
source_var: ContextVar[str] = ContextVar("source", default="SYS")

# Tree depth for hierarchical logging (0 = root level)
tree_depth_var: ContextVar[int] = ContextVar("tree_depth", default=0)

# Stack tracking whether each tree level continues (for proper pipe rendering)
tree_stack_var: ContextVar[List[bool]] = ContextVar("tree_stack", default=[])

# Flag indicating if current log is the last in a context block
is_last_in_context_var: ContextVar[bool] = ContextVar(
    "is_last_in_context", default=False
)


# =============================================================================
# Source Mapping (Normalize to 5-letter codes)
# =============================================================================

SOURCE_MAP: Dict[str, str] = {
    # API/Server sources
    "api": "API  ",
    "server": "SERVR",
    "system": "SYS  ",
    "sys": "SYS  ",
    # Worker/Queue sources
    "worker": "WORKR",
    "workr": "WORKR",
    "processo": "WORKR",
    "processor": "WORKR",
    "queue": "QUEUE",
    "queue_worker": "WORKR",
    # Proxy/Stream sources
    "proxy": "PROXY",
    "proxy_server": "PROXY",
    "proxyserver": "PROXY",
    "stream": "STRM ",
    "inter": "INTER",
    "http_interceptor": "INTER",
    "interceptor": "INTER",
    # Browser sources
    "browser": "BROWR",
    "browr": "BROWR",
    "page": "PAGE ",
    "ui": "UI   ",
    # Launcher sources
    "launcher": "LNCHR",
    "lnchr": "LNCHR",
    "camoufoxlauncher": "LNCHR",
    # Auth sources
    "auth": "AUTH ",
    # Config sources
    "config": "CONFG",
    # Network sources
    "net": "NET  ",
    "network": "NET  ",
    # Model management
    "model": "MODEL",
    # Debug
    "debug": "DEBUG",
}


def normalize_source(source: str) -> str:
    """Normalize source name to fixed 5-letter code."""
    key = source.lower().replace(" ", "_").replace("-", "_")
    if key in SOURCE_MAP:
        return SOURCE_MAP[key]
    # Try partial match
    for map_key, map_val in SOURCE_MAP.items():
        if map_key in key or key in map_key:
            return map_val
    # Default: first 5 chars, uppercase, padded
    return source[:5].upper().ljust(5)


# =============================================================================
# Column Configuration
# =============================================================================


class Columns:
    """Fixed column widths for grid alignment."""

    TIME = 12  # HH:MM:SS.mmm
    LEVEL = 3  # INF, WRN, ERR, DBG, CRT
    SOURCE = 5  # Fixed 5-letter source code
    ID = 7  # Request ID (truncated/padded)
    TREE_INDENT = 3  # Each tree level width


# =============================================================================
# Color Definitions
# =============================================================================


class Colors:
    """Centralized color definitions for consistent theming."""

    # Reset
    RESET = Style.RESET_ALL

    # Time column - dim/subtle (dark grey)
    TIME = Style.DIM + Fore.WHITE

    # Level colors (high contrast)
    LEVELS: Dict[str, str] = {
        "DEBUG": Style.DIM + Fore.CYAN,
        "INFO": Fore.WHITE,
        "WARNING": Fore.YELLOW + Style.BRIGHT,
        "ERROR": Fore.RED + Style.BRIGHT,
        "CRITICAL": Fore.RED + Style.BRIGHT,
    }

    # Level abbreviations
    LEVEL_ABBREV: Dict[str, str] = {
        "DEBUG": "DBG",
        "INFO": "INF",
        "WARNING": "WRN",
        "ERROR": "ERR",
        "CRITICAL": "CRT",
    }

    # Source colors (distinct, pastel-ish)
    SOURCES: Dict[str, str] = {
        "API  ": Fore.LIGHTBLUE_EX,
        "SERVR": Fore.MAGENTA,
        "SYS  ": Style.DIM + Fore.WHITE,
        "WORKR": Fore.LIGHTYELLOW_EX,
        "QUEUE": Fore.YELLOW,
        "PROXY": Fore.BLUE,
        "STRM ": Fore.GREEN,
        "INTER": Fore.LIGHTCYAN_EX,
        "BROWR": Fore.CYAN,
        "PAGE ": Fore.CYAN,
        "UI   ": Fore.LIGHTMAGENTA_EX,
        "LNCHR": Fore.LIGHTGREEN_EX,
        "AUTH ": Fore.LIGHTRED_EX,
        "CONFG": Style.DIM + Fore.WHITE,
        "NET  ": Fore.LIGHTCYAN_EX,
        "MODEL": Fore.LIGHTMAGENTA_EX,
        "DEBUG": Style.DIM + Fore.CYAN,
    }

    # Request ID - dim
    REQUEST_ID = Style.DIM + Fore.WHITE

    # Tree structure - dim
    TREE = Style.DIM + Fore.WHITE

    # Message - default white
    MESSAGE = Fore.WHITE

    # Semantic highlighting (updated for new scheme)
    STRING = Fore.CYAN  # Strings/IDs: Cyan
    NUMBER = Fore.MAGENTA  # Numbers: Magenta
    BOOLEAN_TRUE = Fore.GREEN  # True: Green
    BOOLEAN_FALSE = Fore.RED  # False: Red
    BOOLEAN_NONE = Style.DIM + Fore.WHITE  # None: Dim
    URL = Style.DIM + Fore.BLUE  # URLs: Faint Blue
    KEY = Fore.LIGHTBLUE_EX  # Keys in key:value
    TAG = Style.BRIGHT + Fore.WHITE  # Tags like [UI]

    # Key phrases (Bold)
    PHRASE_ERROR = Style.BRIGHT + Fore.RED
    PHRASE_FAILED = Style.BRIGHT + Fore.RED
    PHRASE_SUCCESS = Style.BRIGHT + Fore.GREEN
    PHRASE_WARNING = Style.BRIGHT + Fore.YELLOW

    # Burst count indicator
    BURST_COUNT = Fore.YELLOW

    # Separator (unused now)
    SEPARATOR = Style.DIM + Fore.WHITE


# =============================================================================
# Tree Structure Builder
# =============================================================================


class TreeBuilder:
    """Builds ASCII tree structure for hierarchical logging."""

    # Unicode box-drawing characters for cleaner look
    PIPE = "\u2502"  # │
    BRANCH = "\u251c\u2500"  # ├─
    LAST_BRANCH = "\u2514\u2500"  # └─
    SPACE = " "

    @classmethod
    def get_prefix(cls) -> str:
        """Generate tree prefix for current depth and context."""
        try:
            depth = tree_depth_var.get()
        except LookupError:
            depth = 0

        if depth == 0:
            return ""

        try:
            stack = tree_stack_var.get()
        except LookupError:
            stack = []

        try:
            is_last = is_last_in_context_var.get()
        except LookupError:
            is_last = False

        # Special case: Depth 1 is just a pipe (no branch)
        if depth == 1:
            return f"{Colors.TREE}{cls.PIPE} {Colors.RESET}"

        prefix_parts: List[str] = []

        # Build prefix based on stack (whether parent levels continue)
        for i in range(min(depth - 1, len(stack))):
            if i < len(stack) and stack[i]:
                prefix_parts.append(f"{cls.PIPE}  ")
            else:
                prefix_parts.append("   ")

        # Add the current level's branch character (depth >= 2)
        if is_last:
            prefix_parts.append(f"{cls.LAST_BRANCH} ")
        else:
            prefix_parts.append(f"{cls.BRANCH} ")

        result = "".join(prefix_parts)
        return f"{Colors.TREE}{result}{Colors.RESET}"


# =============================================================================
# Semantic Highlighter (Enhanced)
# =============================================================================


class SemanticHighlighter:
    """Applies semantic coloring to log message content."""

    # Compiled regex patterns for efficiency
    TAG_PATTERN = re.compile(r"^\[([A-Z]{2,10})\]\s*")
    STRING_PATTERN = re.compile(r"'([^']*)'|\"([^\"]*)\"")
    BOOLEAN_PATTERN = re.compile(r"\b(True|False|None)\b")
    NUMBER_PATTERN = re.compile(r"\b(\d+\.?\d*(?:ms|s|kb|mb|gb|KB|MB|GB|%|px)?)\b")
    HEX_PATTERN = re.compile(r"\b(0x[0-9a-fA-F]+)\b")
    URL_PATTERN = re.compile(
        r"(https?://[^\s]+|[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?::\d+)?(?:/[^\s]*)?)"
    )
    # Key phrases to bold
    PHRASE_ERROR = re.compile(r"\b(Error|ERROR|error)\b")
    PHRASE_FAILED = re.compile(r"\b(Failed|FAILED|failed|Failure|failure)\b")
    PHRASE_SUCCESS = re.compile(
        r"\b(Success|SUCCESS|success|Successful|successful|Complete|complete|Completed|completed)\b"
    )
    PHRASE_WARNING = re.compile(r"\b(Warning|WARNING|warning)\b")
    # Status phrases - Success patterns (Green)
    PHRASE_MATCHES = re.compile(r"\((Matches page|Cached|Matches)\)")
    # Status phrases - Action patterns (Yellow)
    PHRASE_UPDATING = re.compile(r"\((Updating|Toggling|Loading)\.\.\.\)")
    # Model IDs (gemini-*, claude-*, etc.)
    MODEL_ID_PATTERN = re.compile(
        r"\b(gemini-[\w.-]+|claude-[\w.-]+|gpt-[\w.-]+|veo-[\w.-]+)\b"
    )
    # Request IDs (7-char alphanumeric)
    REQ_ID_PATTERN = re.compile(r"\b([a-z0-9]{7})\b")

    @classmethod
    def highlight(cls, text: str, colorize: bool = True) -> str:
        """Apply semantic highlighting to text."""
        if not colorize:
            return text

        result = text

        # Handle tags at the start (e.g., [UI], [NET], [SYS])
        tag_match = cls.TAG_PATTERN.match(result)
        if tag_match:
            full_tag = tag_match.group(0)
            tag_name = tag_match.group(1)
            # Use source color if available, otherwise use TAG color
            normalized = normalize_source(tag_name)
            tag_color = Colors.SOURCES.get(normalized, Colors.TAG)
            colored_tag = f"{tag_color}[{tag_name}]{Colors.RESET} "
            result = colored_tag + result[len(full_tag) :]

        # Highlight URLs first (before strings, to avoid conflict)
        def replace_url(match: re.Match[str]) -> str:
            return f"{Colors.URL}{Style.DIM}{match.group(1)}{Colors.RESET}"

        result = cls.URL_PATTERN.sub(replace_url, result)

        # Highlight model IDs
        def replace_model_id(match: re.Match[str]) -> str:
            return f"{Colors.STRING}{match.group(1)}{Colors.RESET}"

        result = cls.MODEL_ID_PATTERN.sub(replace_model_id, result)

        # Highlight quoted strings
        def replace_string(match: re.Match[str]) -> str:
            # Match group 1 is single-quote, group 2 is double-quote
            content = match.group(1) if match.group(1) else match.group(2)
            quote = "'" if match.group(1) else '"'
            return f"{Colors.STRING}{quote}{content}{quote}{Colors.RESET}"

        result = cls.STRING_PATTERN.sub(replace_string, result)

        # Highlight booleans with distinct colors
        def replace_boolean(match: re.Match[str]) -> str:
            val = match.group(1)
            if val == "True":
                return f"{Colors.BOOLEAN_TRUE}{val}{Colors.RESET}"
            elif val == "False":
                return f"{Colors.BOOLEAN_FALSE}{val}{Colors.RESET}"
            else:  # None
                return f"{Colors.BOOLEAN_NONE}{val}{Colors.RESET}"

        result = cls.BOOLEAN_PATTERN.sub(replace_boolean, result)

        # Highlight numbers (avoid matching inside ANSI codes)
        def replace_number(match: re.Match[str]) -> str:
            return f"{Colors.NUMBER}{match.group(1)}{Colors.RESET}"

        result = cls.NUMBER_PATTERN.sub(replace_number, result)

        # Highlight hex numbers
        def replace_hex(match: re.Match[str]) -> str:
            return f"{Colors.NUMBER}{match.group(1)}{Colors.RESET}"

        result = cls.HEX_PATTERN.sub(replace_hex, result)

        # Bold key phrases
        def replace_error(match: re.Match[str]) -> str:
            return f"{Colors.PHRASE_ERROR}{match.group(1)}{Colors.RESET}"

        result = cls.PHRASE_ERROR.sub(replace_error, result)

        def replace_failed(match: re.Match[str]) -> str:
            return f"{Colors.PHRASE_FAILED}{match.group(1)}{Colors.RESET}"

        result = cls.PHRASE_FAILED.sub(replace_failed, result)

        def replace_success(match: re.Match[str]) -> str:
            return f"{Colors.PHRASE_SUCCESS}{match.group(1)}{Colors.RESET}"

        result = cls.PHRASE_SUCCESS.sub(replace_success, result)

        def replace_warning(match: re.Match[str]) -> str:
            return f"{Colors.PHRASE_WARNING}{match.group(1)}{Colors.RESET}"

        result = cls.PHRASE_WARNING.sub(replace_warning, result)

        # Highlight status phrases - Success (Green)
        def replace_matches(match: re.Match[str]) -> str:
            return f"{Colors.PHRASE_SUCCESS}{match.group(0)}{Colors.RESET}"

        result = cls.PHRASE_MATCHES.sub(replace_matches, result)

        # Highlight status phrases - Action (Yellow)
        def replace_updating(match: re.Match[str]) -> str:
            return f"{Colors.PHRASE_WARNING}{match.group(0)}{Colors.RESET}"

        result = cls.PHRASE_UPDATING.sub(replace_updating, result)

        return result


# =============================================================================
# Logging Filters
# =============================================================================


class BrowserNoiseFilter(logging.Filter):
    """Filter out benign browser noise (AbortError, CORS, Google logging, SSL)."""

    # Patterns to filter out
    NOISE_PATTERNS = [
        "AbortError: The operation was aborted",  # Playwright navigation cancellation
        "Cross-Origin Request Blocked",  # CORS errors (usually harmless)
        "play.google.com/log",  # Google's internal logging endpoint
        "APPLICATION_DATA_AFTER_CLOSE_NOTIFY",  # SSL shutdown warning (harmless)
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        """Return False to drop the log record, True to keep it."""
        message = record.getMessage()
        for pattern in self.NOISE_PATTERNS:
            if pattern in message:
                return False
        return True


# Legacy alias for backwards compatibility
AbortErrorFilter = BrowserNoiseFilter


# =============================================================================
# Burst Suppression State (Thread-safe)
# =============================================================================


class BurstBuffer:
    """
    Thread-safe buffer for burst suppression.

    Tracks duplicate log messages and suppresses them, appending
    a count like (x3) when a different message arrives.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._last_key: Optional[str] = None
        self._last_formatted: Optional[str] = None
        self._count: int = 0

    def process(
        self, key: str, formatted_line: str
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Process a log entry for burst suppression.

        Args:
            key: Unique key for the log (source + message)
            formatted_line: The fully formatted log line

        Returns:
            Tuple of (line_to_print_now, deferred_line_if_any)
            - If same as last: returns (None, None) - suppressed
            - If different: returns (last_with_count_if_needed, current_line)
        """
        with self._lock:
            if self._last_key is None:
                # First message
                self._last_key = key
                self._last_formatted = formatted_line
                self._count = 1
                return (formatted_line, None)

            if key == self._last_key:
                # Duplicate - suppress and increment counter
                self._count += 1
                return (None, None)
            else:
                # Different message - flush previous with count
                prev_line = self._last_formatted
                prev_count = self._count

                # Update to new message
                self._last_key = key
                self._last_formatted = formatted_line
                self._count = 1

                if prev_count > 1 and prev_line:
                    # Create a dim footnote line instead of appending count
                    # Extract timestamp/level/source/id columns from prev_line to align properly
                    # Format: "                  └─ (Repeated N times)"
                    indent = (
                        " " * 31
                    )  # Align with message column (timestamp + level + source + id + spaces)
                    count_line = f"{indent}{Colors.TREE}\u2514\u2500 {Colors.BURST_COUNT}(Repeated {prev_count} times){Colors.RESET}"
                    # Return previous line (without count), count line, and current line
                    return (f"{prev_line}\n{count_line}", formatted_line)
                else:
                    # Previous was single, just print current
                    return (formatted_line, None)

    def flush(self) -> Optional[str]:
        """Flush any remaining buffered message."""
        with self._lock:
            if self._last_formatted and self._count > 1:
                # Create footnote line for repeated message
                indent = " " * 31
                count_line = f"{indent}{Colors.TREE}\u2514\u2500 {Colors.BURST_COUNT}(Repeated {self._count} times){Colors.RESET}"
                result = f"{self._last_formatted}\n{count_line}"
                self._last_key = None
                self._last_formatted = None
                self._count = 0
                return result
            # Don't return anything if count <= 1 (no repetition to report)
            self._last_key = None
            self._last_formatted = None
            self._count = 0
            return None


# Global burst buffer instance
_burst_buffer = BurstBuffer()


# =============================================================================
# Grid Formatter
# =============================================================================


class GridFormatter(logging.Formatter):
    """
    Fixed-width grid formatter with semantic highlighting and burst suppression.

    Format: TIME | LVL | SOURCE | ID | TREE | MESSAGE

    Example output:
    22:47:51.690 INF API   y74ebn9 Received /v1/chat/completions request
    22:47:51.692 INF WORKR y74ebn9 │ Processing request logic...
    22:47:51.695 INF WORKR y74ebn9 │ ├─ UI State Validation
    22:47:51.700 INF PROXY         │ └─ Sniff HTTPS requests (x5)
    """

    def __init__(
        self,
        show_tree: bool = True,
        colorize: bool = True,
        burst_suppression: bool = True,
    ):
        super().__init__()
        self.show_tree = show_tree
        self.colorize = colorize
        self.burst_suppression = burst_suppression

    def format(self, record: logging.LogRecord) -> str:
        """Format log record into grid layout."""

        # Extract context variables with defaults
        try:
            req_id = request_id_var.get()
        except LookupError:
            req_id = "       "

        try:
            source = source_var.get()
        except LookupError:
            source = "SYS"

        # Normalize source to 5-letter code
        source_normalized = normalize_source(source)

        # Column 1: Time (HH:MM:SS.mmm) - no date
        now = datetime.now()
        timestamp = now.strftime("%H:%M:%S.") + f"{int(now.microsecond / 1000):03d}"
        if self.colorize:
            time_col = f"{Colors.TIME}{timestamp}{Colors.RESET}"
        else:
            time_col = timestamp

        # Column 2: Level (3 chars)
        level_abbrev = Colors.LEVEL_ABBREV.get(
            record.levelname, record.levelname[:3].upper()
        )
        if self.colorize:
            level_color = Colors.LEVELS.get(record.levelname, Fore.WHITE)
            level_col = f"{level_color}{level_abbrev}{Colors.RESET}"
        else:
            level_col = level_abbrev

        # Column 3: Source (fixed 5-char width)
        if self.colorize:
            source_color = Colors.SOURCES.get(source_normalized, Fore.WHITE)
            source_col = f"{source_color}{source_normalized}{Colors.RESET}"
        else:
            source_col = source_normalized

        # Column 4: Request ID (fixed 7-char width)
        id_display = req_id[: Columns.ID].ljust(Columns.ID)
        if self.colorize:
            id_col = f"{Colors.REQUEST_ID}{id_display}{Colors.RESET}"
        else:
            id_col = id_display

        # Column 5: Tree prefix
        if self.show_tree:
            tree_prefix = TreeBuilder.get_prefix()
        else:
            tree_prefix = ""

        # Column 6: Message with semantic highlighting
        message = record.getMessage()

        # Skip separator lines (dashed lines)
        if message.strip().startswith("---") or message.strip().startswith("==="):
            # Skip separator lines entirely
            return ""

        if self.colorize:
            message = SemanticHighlighter.highlight(message)

        # Combine all columns
        line = f"{time_col} {level_col} {source_col} {id_col} {tree_prefix}{message}"

        # Apply burst suppression
        if self.burst_suppression:
            # Create key from source + original message (pre-highlight)
            burst_key = f"{source_normalized}:{record.getMessage()}"
            prev_line, current_line = _burst_buffer.process(burst_key, line)

            if prev_line is None and current_line is None:
                # Suppressed - return empty string (won't be printed)
                return ""
            elif current_line is None:
                # Just the previous (with count if needed)
                return prev_line or ""
            elif prev_line:
                # Both lines - print previous then current
                return f"{prev_line}\n{current_line}"
            else:
                # Just current
                return current_line

        return line


# =============================================================================
# Plain Formatter (for file/WebSocket - no ANSI codes)
# =============================================================================


class PlainGridFormatter(logging.Formatter):
    """Plain-text grid formatter for file/WebSocket logging (no ANSI codes)."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record into plain text grid layout."""
        try:
            req_id = request_id_var.get()
        except LookupError:
            req_id = "       "

        try:
            source = source_var.get()
        except LookupError:
            source = "SYS"

        source_normalized = normalize_source(source)

        now = datetime.now()
        timestamp = now.strftime("%H:%M:%S.") + f"{int(now.microsecond / 1000):03d}"

        level_abbrev = Colors.LEVEL_ABBREV.get(
            record.levelname, record.levelname[:3].upper()
        )

        id_display = req_id[: Columns.ID].ljust(Columns.ID)
        message = record.getMessage()

        # Skip separator lines
        if message.strip().startswith("---") or message.strip().startswith("==="):
            return ""

        return f"{timestamp} {level_abbrev} {source_normalized} {id_display} {message}"


# =============================================================================
# Context Managers
# =============================================================================


@contextmanager
def log_context(
    name: str,
    logger: Optional[logging.Logger] = None,
    source: Optional[str] = None,
    silent: bool = False,
) -> Generator[None, None, None]:
    """
    Context manager for hierarchical log grouping.

    Usage:
        with log_context("Processing request", logger):
            logger.info("Step 1")
            with log_context("Nested operation", logger):
                logger.info("Nested step")

    With silent=True, increases depth without logging a header:
        with log_context("", logger, silent=True):
            logger.info("This appears at depth 1")

    Produces:
        22:47:51.689 INF WORKR y74ebn9 ├─ Processing request
        22:47:51.690 INF WORKR y74ebn9 │  ├─ Step 1
        22:47:51.691 INF WORKR y74ebn9 │  │  ├─ Nested operation
        22:47:51.692 INF WORKR y74ebn9 │  │  └─ Nested step
    """
    if logger is None:
        logger = logging.getLogger()

    # Get current depth and stack
    try:
        current_depth = tree_depth_var.get()
    except LookupError:
        current_depth = 0

    try:
        current_stack = list(tree_stack_var.get())
    except LookupError:
        current_stack = []

    # Handle optional source change
    source_token = None
    if source is not None:
        source_token = source_var.set(source)

    # Log the context entry (unless silent)
    if not silent:
        logger.info(name)

    # Increase depth and update stack (True = this level continues)
    new_depth = current_depth + 1
    new_stack = current_stack + [True]

    depth_token = tree_depth_var.set(new_depth)
    stack_token = tree_stack_var.set(new_stack)

    try:
        yield
    finally:
        # Restore previous state
        tree_depth_var.reset(depth_token)
        tree_stack_var.reset(stack_token)
        if source_token is not None:
            source_var.reset(source_token)


@contextmanager
def request_context(
    request_id: str, source: str = "WORKR"
) -> Generator[None, None, None]:
    """
    Context manager for request lifecycle.

    Sets request ID and source for all logs within the context.

    Usage:
        with request_context("akvdate", source="WORKR"):
            logger.info("Processing...")
    """
    # Set context variables
    id_token = request_id_var.set(request_id)
    source_token = source_var.set(source)
    depth_token = tree_depth_var.set(0)
    stack_token = tree_stack_var.set([])

    try:
        yield
    finally:
        # Reset context variables
        request_id_var.reset(id_token)
        source_var.reset(source_token)
        tree_depth_var.reset(depth_token)
        tree_stack_var.reset(stack_token)


# =============================================================================
# Object Dumper (YAML-style)
# =============================================================================


def format_object(obj: Any, indent: int = 0, colorize: bool = True) -> str:
    """
    Format an object in YAML-style for clean logging.

    Args:
        obj: The object to format (dict, list, or primitive)
        indent: Current indentation level
        colorize: Whether to apply colors

    Returns:
        Formatted string representation
    """
    lines: List[str] = []
    prefix = "  " * indent

    if isinstance(obj, dict):
        for key, value in obj.items():  # pyright: ignore[reportUnknownVariableType]
            key_str = (
                f"{Colors.KEY}{key}{Colors.RESET}" if colorize else str(key)  # pyright: ignore[reportUnknownArgumentType]
            )
            if isinstance(value, (dict, list)) and value:
                lines.append(f"{prefix}{key_str}:")
                lines.append(format_object(value, indent + 1, colorize))
            else:
                formatted_value = _format_value(value, colorize)
                lines.append(f"{prefix}{key_str}: {formatted_value}")
    elif isinstance(obj, list):
        for item in obj:  # pyright: ignore[reportUnknownVariableType]
            if isinstance(item, (dict, list)) and item:
                lines.append(f"{prefix}-")
                lines.append(format_object(item, indent + 1, colorize))
            else:
                formatted_value = _format_value(item, colorize)
                lines.append(f"{prefix}- {formatted_value}")
    else:
        lines.append(f"{prefix}{_format_value(obj, colorize)}")

    return "\n".join(lines)


def _format_value(value: Any, colorize: bool = True) -> str:
    """Format a single value with appropriate coloring."""
    if not colorize:
        if isinstance(value, str):
            return f"'{value}'"
        return str(value)

    if isinstance(value, bool):
        if value:
            return f"{Colors.BOOLEAN_TRUE}{value}{Colors.RESET}"
        else:
            return f"{Colors.BOOLEAN_FALSE}{value}{Colors.RESET}"
    elif isinstance(value, (int, float)):
        return f"{Colors.NUMBER}{value}{Colors.RESET}"
    elif isinstance(value, str):
        # Truncate long strings
        if len(value) > 50:
            truncated = value[:47] + "..."
            return f"{Colors.STRING}'{truncated}'{Colors.RESET}"
        return f"{Colors.STRING}'{value}'{Colors.RESET}"
    elif value is None:
        return f"{Colors.BOOLEAN_NONE}None{Colors.RESET}"
    else:
        return f"{Colors.STRING}{repr(value)}{Colors.RESET}"


def log_object(
    logger: logging.Logger, obj: Any, label: str = "Data", level: int = logging.INFO
) -> None:
    """
    Log an object with YAML-style formatting.

    Args:
        logger: Logger instance to use
        obj: Object to dump (dict, list, etc.)
        label: Label for the data block
        level: Logging level to use
    """
    logger.log(level, f"{label}:")
    formatted = format_object(obj, indent=1)
    for line in formatted.split("\n"):
        if line.strip():
            logger.log(level, f"  {line}")


# =============================================================================
# Progress Indicator
# =============================================================================


class ProgressLine:
    """
    Progress indicator that updates on the same line.

    Uses carriage return (\\r) to overwrite the previous output
    instead of creating new log lines.

    Usage:
        progress = ProgressLine("Waiting for stream")
        for i in range(100):
            progress.update(i + 1, 100, f"chunks: {i + 1}")
            time.sleep(0.05)
        progress.finish("Complete")
    """

    def __init__(self, message: str, source: Optional[str] = None):
        """
        Initialize progress indicator.

        Args:
            message: Base message to display
            source: Optional source override (uses context var if None)
        """
        self.message = message
        self.source = source
        self.last_update = 0.0
        self._started = False
        self._min_interval = 0.05  # Minimum time between updates (50ms)

    def update(self, current: int, total: int, extra: str = "") -> None:
        """
        Update progress on the same line.

        Args:
            current: Current progress value
            total: Total value for 100%
            extra: Additional info to display after progress bar
        """
        now = time.time()

        # Rate limit updates to avoid flickering
        if now - self.last_update < self._min_interval and current < total:
            return

        self.last_update = now
        self._started = True

        # Get context
        try:
            req_id = request_id_var.get()
        except LookupError:
            req_id = "       "

        source = self.source
        if source is None:
            try:
                source = source_var.get()
            except LookupError:
                source = "SYS"

        source_normalized = normalize_source(source)

        # Build timestamp
        timestamp = (
            datetime.now().strftime("%H:%M:%S.") + f"{int(now * 1000) % 1000:03d}"
        )

        # Calculate progress
        percentage = (current / total * 100) if total > 0 else 0
        bar_width = 20
        filled = int(bar_width * current / total) if total > 0 else 0
        bar = "#" * filled + "-" * (bar_width - filled)

        extra_text = f" {extra}" if extra else ""

        # Build the line with colors
        source_color = Colors.SOURCES.get(source_normalized, Fore.WHITE)
        line = (
            f"\r{Colors.TIME}{timestamp}{Colors.RESET} "
            f"{Colors.LEVELS['INFO']}INF{Colors.RESET} "
            f"{source_color}{source_normalized}{Colors.RESET} "
            f"{Colors.REQUEST_ID}{req_id:<{Columns.ID}}{Colors.RESET} "
            f"{Colors.MESSAGE}{self.message} [{bar}] "
            f"{Colors.NUMBER}{current}{Colors.RESET}/{Colors.NUMBER}{total}{Colors.RESET} "
            f"({Colors.NUMBER}{percentage:.0f}%{Colors.RESET}){extra_text}"
        )

        # Clear to end of line and print
        sys.stdout.write(f"{line}\033[K")
        sys.stdout.flush()

    def finish(self, message: Optional[str] = None) -> None:
        """
        Complete the progress and move to new line.

        Args:
            message: Optional completion message
        """
        if self._started:
            if message:
                sys.stdout.write(f" - {Colors.STRING}{message}{Colors.RESET}")
            sys.stdout.write("\n")
            sys.stdout.flush()


# =============================================================================
# Convenience Functions
# =============================================================================


def set_source(source: str) -> None:
    """Set the source identifier for subsequent logs."""
    source_var.set(source)


def set_request_id(request_id: str) -> None:
    """Set the request ID for subsequent logs."""
    request_id_var.set(request_id)


def get_source() -> str:
    """Get the current source identifier."""
    try:
        return source_var.get()
    except LookupError:
        return "SYS"


def get_request_id() -> str:
    """Get the current request ID."""
    try:
        return request_id_var.get()
    except LookupError:
        return "       "


def flush_burst_buffer() -> None:
    """Flush any remaining burst-suppressed messages."""
    result = _burst_buffer.flush()
    if result:
        print(result)


# =============================================================================
# Logger Setup
# =============================================================================


def setup_grid_logging(
    level: int = logging.DEBUG,
    show_tree: bool = True,
    colorize: bool = True,
    burst_suppression: bool = True,
    logger_name: Optional[str] = None,
) -> logging.Logger:
    """
    Configure the logging system with grid formatting.

    Args:
        level: Logging level (default: DEBUG)
        show_tree: Whether to show tree structure (default: True)
        colorize: Whether to apply colors (default: True)
        burst_suppression: Whether to suppress duplicate messages (default: True)
        logger_name: Optional logger name (default: root logger)

    Returns:
        Configured logger instance
    """
    # Initialize colorama
    colorama_init(autoreset=False)

    # Get logger
    if logger_name:
        logger = logging.getLogger(logger_name)
    else:
        logger = logging.getLogger()

    logger.setLevel(level)

    # Remove existing handlers to avoid duplicates
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)

    # Apply grid formatter
    formatter = GridFormatter(
        show_tree=show_tree, colorize=colorize, burst_suppression=burst_suppression
    )
    console_handler.setFormatter(formatter)

    logger.addHandler(console_handler)

    return logger


# =============================================================================
# Demo / Test
# =============================================================================

if __name__ == "__main__":
    import random
    import string

    # Setup logging
    logger = setup_grid_logging(level=logging.DEBUG)

    print()
    print("=" * 70)
    print(" GRID LOGGING SYSTEM v2.0 - DEMONSTRATION")
    print("=" * 70)
    print()

    # Generate a random request ID (like your existing system)
    req_id = "".join(random.choices(string.ascii_lowercase + string.digits, k=7))

    # =========================================================================
    # Test 1: Basic logging with tree structure
    # =========================================================================

    set_request_id(req_id)
    set_source("API")

    logger.info("Received /v1/chat/completions request (Stream=True)")

    set_source("WORKR")

    with log_context("Processing request logic", logger):
        logger.info("Dequeued request from queue")

        with log_context("UI State Validation", logger):
            logger.info("Temperature matches (0.0). No update needed.")
            logger.info("Max tokens: 8192, Top-P: 0.95")

        with log_context("Model Switching", logger, source="BROWR"):
            logger.info("Current model: 'gemini-1.5-flash'")
            logger.info("Target model: 'gemini-2.0-flash-exp'")
            logger.info("Model switch completed in 1.2s")

    # =========================================================================
    # Test 2: Burst suppression
    # =========================================================================

    print()
    print("-" * 70)
    print(" BURST SUPPRESSION DEMO")
    print("-" * 70)
    print()

    set_source("PROXY")
    set_request_id("       ")

    # Simulate repeated messages
    for _ in range(5):
        logger.info("Sniff HTTPS requests to: aistudio.google.com:443")

    logger.info("Different message - this triggers flush")

    for _ in range(3):
        logger.error("[UPSTREAM ERROR] 429 Too Many Requests")

    logger.warning("Another different message")

    # =========================================================================
    # Test 3: Semantic highlighting
    # =========================================================================

    print()
    print("-" * 70)
    print(" SEMANTIC HIGHLIGHTING DEMO")
    print("-" * 70)
    print()

    set_source("SYS")

    logger.info("Processing True and False values with None")
    logger.info("Temperature: 0.95, max_tokens: 2048, top_p: 0.9")
    logger.info("Loaded model 'gemini-2.0-flash-exp' successfully")
    logger.info("URL: https://aistudio.google.com/prompts")
    logger.warning("Warning: Rate limit approaching")
    logger.error("Error: Connection failed after 3 retries")
    logger.info("Success: Request completed in 150ms")

    # =========================================================================
    # Test 4: Object dumping
    # =========================================================================

    print()
    print("-" * 70)
    print(" OBJECT DUMP DEMO")
    print("-" * 70)
    print()

    data = {
        "model": "gemini-2.0-flash-exp",
        "temperature": 0.7,
        "stream": True,
        "messages": [
            {"role": "user", "content": "Hello!"},
            {"role": "assistant", "content": "Hi there!"},
        ],
    }
    log_object(logger, data, "Request Parameters")

    print()
    print("=" * 70)
    print(" DEMONSTRATION COMPLETE")
    print("=" * 70)
    print()

    # Flush any remaining burst buffer
    flush_burst_buffer()
