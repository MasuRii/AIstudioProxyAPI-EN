"""
GUI Launcher Environment Manager

Manages reading/writing .env file settings with hot reload support.
"""

import os
import re
import shutil
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


class EnvManager:
    """
    Manages .env file operations with structured parsing and hot reload support.

    Features:
    - Preserves comments and file structure when writing
    - Tracks modified values for dirty state detection
    - Supports hot reload callbacks
    - Validates values based on type hints
    """

    # Type definitions for env variables
    # Format: (default_value, type, description, category)
    ENV_SCHEMA: Dict[str, Tuple[Any, str, str, str]] = {
        # Server Configuration
        "PORT": (2048, "int", "FastAPI Main Service Port", "server"),
        "STREAM_PORT": (
            3120,
            "int",
            "Streaming Proxy Service Port (0 to disable)",
            "server",
        ),
        "DEFAULT_FASTAPI_PORT": (2048, "int", "GUI Default FastAPI Port", "server"),
        "DEFAULT_CAMOUFOX_PORT": (9222, "int", "GUI Default Camoufox Port", "server"),
        # Logging & Debugging
        "SERVER_LOG_LEVEL": (
            "INFO",
            "choice:DEBUG,INFO,WARNING,ERROR,CRITICAL",
            "Server Log Level",
            "logging",
        ),
        "SERVER_REDIRECT_PRINT": (
            False,
            "bool",
            "Redirect print output to logs",
            "logging",
        ),
        "DEBUG_LOGS_ENABLED": (False, "bool", "Enable Debug Logs", "logging"),
        "TRACE_LOGS_ENABLED": (False, "bool", "Enable Trace Logs", "logging"),
        "JSON_LOGS": (False, "bool", "JSON Structured Logging", "logging"),
        "LOG_FILE_MAX_BYTES": (10485760, "int", "Log File Max Size (bytes)", "logging"),
        "LOG_FILE_BACKUP_COUNT": (5, "int", "Log Backup File Count", "logging"),
        # Authentication
        "AUTO_SAVE_AUTH": (False, "bool", "Auto-save Authentication", "auth"),
        "AUTH_SAVE_TIMEOUT": (30, "int", "Auth Save Timeout (seconds)", "auth"),
        "AUTO_ROTATE_AUTH_PROFILE": (True, "bool", "Auto Rotate Auth Profile", "auth"),
        "AUTO_AUTH_ROTATION_ON_STARTUP": (
            False,
            "bool",
            "Auto Auth Rotation on Startup",
            "auth",
        ),
        "AUTO_CONFIRM_LOGIN": (True, "bool", "Auto Confirm Login", "auth"),
        "QUOTA_SOFT_LIMIT": (850000, "int", "Quota Soft Limit (tokens)", "auth"),
        "QUOTA_HARD_LIMIT": (950000, "int", "Quota Hard Limit (tokens)", "auth"),
        # Cookie Refresh
        "COOKIE_REFRESH_ENABLED": (True, "bool", "Enable Cookie Refresh", "cookie"),
        "COOKIE_REFRESH_INTERVAL_SECONDS": (
            1800,
            "int",
            "Cookie Refresh Interval (seconds)",
            "cookie",
        ),
        "COOKIE_REFRESH_ON_REQUEST_ENABLED": (
            True,
            "bool",
            "Cookie Refresh on Request",
            "cookie",
        ),
        "COOKIE_REFRESH_REQUEST_INTERVAL": (
            10,
            "int",
            "Cookie Refresh Request Interval",
            "cookie",
        ),
        "COOKIE_REFRESH_ON_SHUTDOWN": (
            True,
            "bool",
            "Cookie Refresh on Shutdown",
            "cookie",
        ),
        # Browser & Model
        "LAUNCH_MODE": (
            "normal",
            "choice:normal,debug,headless,virtual_display,direct_debug_no_browser",
            "Launch Mode",
            "browser",
        ),
        "DIRECT_LAUNCH": (
            False,
            "bool",
            "Quick Launch (Skip Launcher Menu)",
            "browser",
        ),
        "ONLY_COLLECT_CURRENT_USER_ATTACHMENTS": (
            False,
            "bool",
            "Only Collect Current User Attachments",
            "browser",
        ),
        "ENDPOINT_CAPTURE_TIMEOUT": (
            45,
            "int",
            "Camoufox Endpoint Capture Timeout (seconds)",
            "browser",
        ),
        # API Defaults
        "DEFAULT_TEMPERATURE": (1.0, "float", "Default Temperature", "api"),
        "DEFAULT_MAX_OUTPUT_TOKENS": (65536, "int", "Default Max Output Tokens", "api"),
        "DEFAULT_TOP_P": (0.95, "float", "Default Top P", "api"),
        "ENABLE_THINKING_BUDGET": (True, "bool", "Enable Thinking Budget", "api"),
        "DEFAULT_THINKING_BUDGET": (
            8192,
            "int",
            "Default Thinking Budget (tokens)",
            "api",
        ),
        "THINKING_BUDGET_LOW": (10923, "int", "Thinking Budget Low Level", "api"),
        "THINKING_BUDGET_MEDIUM": (21845, "int", "Thinking Budget Medium Level", "api"),
        "THINKING_BUDGET_HIGH": (32768, "int", "Thinking Budget High Level", "api"),
        "DEFAULT_THINKING_LEVEL_PRO": (
            "high",
            "choice:low,medium,high",
            "Default Thinking Level (Pro)",
            "api",
        ),
        "DEFAULT_THINKING_LEVEL_FLASH": (
            "high",
            "choice:low,medium,high",
            "Default Thinking Level (Flash)",
            "api",
        ),
        "DISABLE_THINKING_BUDGET_ON_STREAMING_DISABLE": (
            False,
            "bool",
            "Disable Thinking on Streaming Disable",
            "api",
        ),
        "ENABLE_GOOGLE_SEARCH": (False, "bool", "Enable Google Search", "api"),
        "ENABLE_URL_CONTEXT": (False, "bool", "Enable URL Context", "api"),
        # Function Calling
        "FUNCTION_CALLING_MODE": (
            "auto",
            "choice:auto,native,emulated",
            "Function Calling Mode",
            "function_calling",
        ),
        "FUNCTION_CALLING_NATIVE_FALLBACK": (
            True,
            "bool",
            "Native Mode Fallback to Emulated",
            "function_calling",
        ),
        "FUNCTION_CALLING_UI_TIMEOUT": (
            10000,
            "int",
            "Function Calling UI Timeout (ms)",
            "function_calling",
        ),
        "FUNCTION_CALLING_NATIVE_RETRY_COUNT": (
            3,
            "int",
            "Native Mode Retry Count",
            "function_calling",
        ),
        "FUNCTION_CALLING_CLEAR_BETWEEN_REQUESTS": (
            True,
            "bool",
            "Clear Functions Between Requests",
            "function_calling",
        ),
        "FUNCTION_CALLING_DEBUG": (
            False,
            "bool",
            "Function Calling Debug (Master Switch)",
            "function_calling",
        ),
        "FUNCTION_CALLING_CACHE_ENABLED": (
            True,
            "bool",
            "Function Calling Cache Enabled",
            "function_calling",
        ),
        "FUNCTION_CALLING_CACHE_TTL": (
            0,
            "int",
            "Function Calling Cache TTL (seconds)",
            "function_calling",
        ),
        # Timeouts
        "RESPONSE_COMPLETION_TIMEOUT": (
            600000,
            "int",
            "Response Completion Timeout (ms)",
            "timeouts",
        ),
        "INITIAL_WAIT_MS_BEFORE_POLLING": (
            500,
            "int",
            "Initial Wait Before Polling (ms)",
            "timeouts",
        ),
        "POLLING_INTERVAL": (300, "int", "Polling Interval (ms)", "timeouts"),
        "POLLING_INTERVAL_STREAM": (
            180,
            "int",
            "Streaming Polling Interval (ms)",
            "timeouts",
        ),
        "SILENCE_TIMEOUT_MS": (60000, "int", "Silence Timeout (ms)", "timeouts"),
        "CLICK_TIMEOUT_MS": (3000, "int", "Click Timeout (ms)", "timeouts"),
        "WAIT_FOR_ELEMENT_TIMEOUT_MS": (
            10000,
            "int",
            "Wait for Element Timeout (ms)",
            "timeouts",
        ),
        "PSEUDO_STREAM_DELAY": (
            0.01,
            "float",
            "Pseudo Stream Delay (seconds)",
            "timeouts",
        ),
        # Miscellaneous
        "SKIP_FRONTEND_BUILD": (False, "bool", "Skip Frontend Build Check", "misc"),
        "ENABLE_SCRIPT_INJECTION": (
            False,
            "bool",
            "Enable Script Injection (Deprecated)",
            "misc",
        ),
    }

    # Category display order and names
    CATEGORIES: Dict[str, str] = {
        "server": "Server Configuration",
        "logging": "Logging & Debugging",
        "auth": "Authentication",
        "cookie": "Cookie Refresh",
        "browser": "Browser & Model",
        "api": "API Defaults",
        "function_calling": "Function Calling",
        "timeouts": "Timeouts",
        "misc": "Miscellaneous",
    }

    def __init__(self, env_path: Path, example_path: Optional[Path] = None):
        """
        Initialize the EnvManager.

        Args:
            env_path: Path to the .env file
            example_path: Path to .env.example (used for initialization)
        """
        self.env_path = env_path
        self.example_path = example_path
        self._values: Dict[str, str] = {}
        self._original_values: Dict[str, str] = {}
        self._file_lines: List[str] = []
        self._hot_reload_callbacks: List[Callable[[Dict[str, str]], None]] = []

        # Load the file
        self.load()

    def load(self) -> None:
        """Load and parse the .env file."""
        self._values = {}
        self._file_lines = []

        # If .env doesn't exist, try to copy from .env.example
        if not self.env_path.exists():
            if self.example_path and self.example_path.exists():
                shutil.copy(self.example_path, self.env_path)
            else:
                # Create an empty .env
                self.env_path.touch()

        # Read the file
        try:
            with open(self.env_path, "r", encoding="utf-8") as f:
                self._file_lines = f.readlines()
        except Exception as e:
            print(f"Error reading .env file: {e}")
            self._file_lines = []

        # Parse key-value pairs
        for line in self._file_lines:
            stripped = line.strip()

            # Skip empty lines and comments
            if not stripped or stripped.startswith("#"):
                continue

            # Parse key=value
            match = re.match(
                r"^([A-Z_][A-Z0-9_]*)\s*=\s*(.*)$", stripped, re.IGNORECASE
            )
            if match:
                key = match.group(1)
                value = match.group(2)

                # Remove surrounding quotes if present
                if (value.startswith('"') and value.endswith('"')) or (
                    value.startswith("'") and value.endswith("'")
                ):
                    value = value[1:-1]

                self._values[key] = value

        # Store original values for dirty detection
        self._original_values = self._values.copy()

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a value from the env, with type conversion.

        Args:
            key: Environment variable name
            default: Default value if not found

        Returns:
            The typed value
        """
        raw_value = self._values.get(key)

        if raw_value is None:
            # Return schema default if available
            if key in self.ENV_SCHEMA:
                return self.ENV_SCHEMA[key][0]
            return default

        # Get type from schema
        if key in self.ENV_SCHEMA:
            _, type_hint, _, _ = self.ENV_SCHEMA[key]
            return self._convert_value(raw_value, type_hint)

        return raw_value

    def get_raw(self, key: str) -> Optional[str]:
        """Get raw string value without type conversion."""
        return self._values.get(key)

    def set(self, key: str, value: Any) -> None:
        """
        Set a value in the env.

        Args:
            key: Environment variable name
            value: Value to set (will be converted to string)
        """
        # Convert boolean to lowercase string
        if isinstance(value, bool):
            str_value = "true" if value else "false"
        else:
            str_value = str(value)

        self._values[key] = str_value

    def is_dirty(self) -> bool:
        """Check if any values have been modified since last load/save."""
        return self._values != self._original_values

    def get_modified_keys(self) -> List[str]:
        """Get list of keys that have been modified."""
        modified = []
        for key in self._values:
            if (
                key not in self._original_values
                or self._values[key] != self._original_values[key]
            ):
                modified.append(key)
        for key in self._original_values:
            if key not in self._values:
                modified.append(key)
        return list(set(modified))

    def save(self) -> bool:
        """
        Save changes to the .env file.

        Preserves comments and structure, only updating changed values.

        Returns:
            True if save was successful
        """
        try:
            new_lines = []
            keys_written = set()

            for line in self._file_lines:
                stripped = line.strip()

                # Keep empty lines and comments
                if not stripped or stripped.startswith("#"):
                    new_lines.append(line)
                    continue

                # Check if this is a key=value line
                match = re.match(r"^([A-Z_][A-Z0-9_]*)\s*=", stripped, re.IGNORECASE)
                if match:
                    key = match.group(1)
                    if key in self._values:
                        # Update the value, preserve comment if any
                        comment_match = re.search(r"#.*$", line)
                        comment = comment_match.group(0) if comment_match else ""

                        value = self._values[key]
                        # Quote values with spaces
                        if " " in value and not (
                            value.startswith('"') or value.startswith("'")
                        ):
                            value = f'"{value}"'

                        new_line = f"{key}={value}"
                        if comment:
                            new_line += f"  {comment}"
                        new_lines.append(new_line + "\n")
                        keys_written.add(key)
                    else:
                        new_lines.append(line)
                else:
                    new_lines.append(line)

            # Add any new keys at the end
            for key, value in self._values.items():
                if key not in keys_written:
                    new_lines.append(f"\n{key}={value}\n")

            # Write the file
            with open(self.env_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)

            # Reload to update line cache
            self.load()
            return True

        except Exception as e:
            print(f"Error saving .env file: {e}")
            return False

    def reset_to_defaults(self) -> None:
        """Reset all values to their schema defaults."""
        for key, (default, _, _, _) in self.ENV_SCHEMA.items():
            self.set(key, default)

    def discard_changes(self) -> None:
        """Discard all unsaved changes."""
        self._values = self._original_values.copy()

    def get_category_keys(self, category: str) -> List[str]:
        """Get all keys belonging to a category."""
        return [
            key for key, (_, _, _, cat) in self.ENV_SCHEMA.items() if cat == category
        ]

    def get_schema_info(self, key: str) -> Optional[Tuple[Any, str, str, str]]:
        """Get schema info for a key: (default, type, description, category)."""
        return self.ENV_SCHEMA.get(key)

    def register_hot_reload_callback(
        self, callback: Callable[[Dict[str, str]], None]
    ) -> None:
        """
        Register a callback for hot reload notifications.

        Args:
            callback: Function that receives dict of changed keys and values
        """
        self._hot_reload_callbacks.append(callback)

    def unregister_hot_reload_callback(
        self, callback: Callable[[Dict[str, str]], None]
    ) -> None:
        """Unregister a hot reload callback."""
        if callback in self._hot_reload_callbacks:
            self._hot_reload_callbacks.remove(callback)

    def trigger_hot_reload(self) -> None:
        """Trigger hot reload callbacks with modified values."""
        modified = {key: self._values.get(key, "") for key in self.get_modified_keys()}
        for callback in self._hot_reload_callbacks:
            try:
                callback(modified)
            except Exception as e:
                print(f"Hot reload callback error: {e}")

    def apply_to_environment(self) -> None:
        """Apply current values to os.environ for hot reload."""
        for key, value in self._values.items():
            os.environ[key] = value

    def _convert_value(self, value: str, type_hint: str) -> Any:
        """Convert a string value based on type hint."""
        try:
            if type_hint == "bool":
                return value.lower() in ("true", "1", "yes", "on")
            elif type_hint == "int":
                return int(value)
            elif type_hint == "float":
                return float(value)
            elif type_hint.startswith("choice:"):
                # Return as-is, validation is done elsewhere
                return value
            else:
                return value
        except (ValueError, TypeError):
            # Return schema default on conversion error
            if type_hint == "bool":
                return False
            elif type_hint == "int":
                return 0
            elif type_hint == "float":
                return 0.0
            return value


# Singleton instance
_env_manager: Optional[EnvManager] = None


def get_env_manager(
    env_path: Optional[Path] = None, example_path: Optional[Path] = None
) -> EnvManager:
    """
    Get the singleton EnvManager instance.

    Args:
        env_path: Path to .env file (only used on first call)
        example_path: Path to .env.example (only used on first call)

    Returns:
        The EnvManager singleton
    """
    global _env_manager
    if _env_manager is None:
        if env_path is None:
            raise ValueError("env_path must be provided on first call")
        _env_manager = EnvManager(env_path, example_path)
    return _env_manager


def reset_env_manager() -> None:
    """Reset the singleton (mainly for testing)."""
    global _env_manager
    _env_manager = None
