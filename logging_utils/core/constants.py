"""
Logging Constants
"""

import sys
from typing import Dict

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
