"""
FC Debug Configuration.

Loads configuration from environment variables for FC debug logging.
Supports master switch, per-module enable/disable, and per-module log levels.
"""

import logging
import os
from dataclasses import dataclass, field
from typing import Dict

from .modules import FCModule


@dataclass
class FCDebugConfig:
    """Configuration for FC debug logging."""

    master_enabled: bool = False
    module_enabled: Dict[FCModule, bool] = field(default_factory=dict)
    module_levels: Dict[FCModule, int] = field(default_factory=dict)
    log_max_bytes: int = 5 * 1024 * 1024  # 5MB
    log_backup_count: int = 3
    combined_log_enabled: bool = False

    @classmethod
    def from_env(cls) -> "FCDebugConfig":
        """Load configuration from environment variables."""
        # Master switch: FUNCTION_CALLING_DEBUG is the primary control
        master = os.environ.get("FUNCTION_CALLING_DEBUG", "false").lower() in (
            "true",
            "1",
            "yes",
        )

        # Allow FC_DEBUG_ENABLED as an alias for granular control
        if not master:
            master = os.environ.get("FC_DEBUG_ENABLED", "false").lower() in (
                "true",
                "1",
                "yes",
            )

        # Per-module enabled
        module_enabled: Dict[FCModule, bool] = {}
        for module in FCModule:
            env_val = os.environ.get(module.env_enabled_key, "").lower()
            if env_val:
                module_enabled[module] = env_val in ("true", "1", "yes")
            else:
                # Default to True if master is enabled, to ensure FUNCTION_CALLING_DEBUG=true
                # enables all logs by default unless specifically disabled.
                module_enabled[module] = True

        # Per-module levels
        module_levels: Dict[FCModule, int] = {}
        for module in FCModule:
            level_str = os.environ.get(module.env_level_key, "DEBUG").upper()
            module_levels[module] = getattr(logging, level_str, logging.DEBUG)

        # Rotation settings
        max_bytes = int(os.environ.get("FC_DEBUG_LOG_MAX_BYTES", str(5 * 1024 * 1024)))
        backup_count = int(os.environ.get("FC_DEBUG_LOG_BACKUP_COUNT", "3"))

        # Combined log
        combined = os.environ.get("FC_DEBUG_COMBINED_LOG", "false").lower() in (
            "true",
            "1",
            "yes",
        )

        return cls(
            master_enabled=master,
            module_enabled=module_enabled,
            module_levels=module_levels,
            log_max_bytes=max_bytes,
            log_backup_count=backup_count,
            combined_log_enabled=combined,
        )

    def is_module_enabled(self, module: FCModule) -> bool:
        """Check if a module is enabled."""
        return self.master_enabled and self.module_enabled.get(module, False)

    def get_module_level(self, module: FCModule) -> int:
        """Get the log level for a module."""
        return self.module_levels.get(module, logging.DEBUG)
