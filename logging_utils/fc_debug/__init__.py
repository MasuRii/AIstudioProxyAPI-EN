"""
FC Debug Logging Module.

Provides modular, configurable debug logging for Function Calling components.

Usage:
    from logging_utils.fc_debug import get_fc_logger, FCModule

    fc_logger = get_fc_logger()

    # Log to specific modules
    fc_logger.debug(FCModule.CACHE, "Cache hit", req_id="abc123")
    fc_logger.info(FCModule.UI, "Toggle enabled", req_id="abc123")

    # Use convenience methods
    fc_logger.log_cache_hit(req_id, digest, age_seconds)
    fc_logger.log_ui_action(req_id, "click", "toggle_button", elapsed_ms=45.2)

    # Check if module is enabled (for performance-sensitive logging)
    if fc_logger.is_enabled(FCModule.SCHEMA):
        fc_logger.debug(FCModule.SCHEMA, "Converting tools", payload=tools)

Environment Variables:
    FC_DEBUG_ENABLED=true           # Master switch
    FC_DEBUG_CACHE=true             # Enable cache module
    FC_DEBUG_UI=true                # Enable UI module
    FC_DEBUG_LEVEL_CACHE=DEBUG      # Set log level for cache
    FC_DEBUG_COMBINED_LOG=true      # Also write to fc_combined.log
"""

from .config import FCDebugConfig
from .formatters import FCDebugFormatter
from .handlers import create_rotating_file_handler, ensure_log_directory
from .logger import FunctionCallingDebugLogger, ModuleLogger, get_fc_logger
from .modules import FCModule
from .truncation import TruncationConfig, summarize_tools, truncate_payload

__all__ = [
    # Main logger
    "FunctionCallingDebugLogger",
    "get_fc_logger",
    "ModuleLogger",
    # Modules
    "FCModule",
    # Configuration
    "FCDebugConfig",
    "TruncationConfig",
    # Formatters
    "FCDebugFormatter",
    # Handlers
    "create_rotating_file_handler",
    "ensure_log_directory",
    # Truncation utilities
    "truncate_payload",
    "summarize_tools",
]
