"""
Function Calling Debug Logger.

Centralized singleton logger for all Function Calling components.
Provides per-module logging with separate log files, configurable
log levels, payload truncation, and request ID correlation.
"""

import logging
import logging.handlers
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Optional

from .config import FCDebugConfig
from .handlers import create_rotating_file_handler, ensure_log_directory
from .modules import FCModule
from .truncation import TruncationConfig, truncate_payload


@dataclass
class ModuleLogger:
    """Wrapper for a module-specific logger with configuration."""

    module: FCModule
    logger: logging.Logger
    enabled: bool
    level: int
    file_handler: Optional[logging.handlers.RotatingFileHandler] = None


class FunctionCallingDebugLogger:
    """
    Centralized debug logger for Function Calling components.

    Thread-safe singleton that manages per-module loggers with:
    - Independent enable/disable per module
    - Separate log files per module
    - Configurable log levels
    - Payload truncation
    - Request ID correlation

    Usage:
        fc_logger = FunctionCallingDebugLogger.get_instance()

        # Log with specific module
        fc_logger.debug(FCModule.CACHE, "Cache hit", req_id="abc123")
        fc_logger.info(FCModule.UI, "Opening dialog", req_id="abc123")

        # Log with payload truncation
        fc_logger.debug(
            FCModule.SCHEMA,
            "Converting tools",
            req_id="abc123",
            payload={"tools": large_tool_list}
        )
    """

    _instance: Optional["FunctionCallingDebugLogger"] = None
    _lock: Lock = Lock()

    def __init__(self) -> None:
        """Initialize the logger. Use get_instance() instead."""
        self._config: Optional[FCDebugConfig] = None
        self._truncation: Optional[TruncationConfig] = None
        self._module_loggers: Dict[FCModule, ModuleLogger] = {}
        self._combined_handler: Optional[logging.handlers.RotatingFileHandler] = None
        self._initialized = False

    @classmethod
    def get_instance(cls) -> "FunctionCallingDebugLogger":
        """Get the singleton instance, creating if needed."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
                    cls._instance._initialize()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton instance (for testing)."""
        with cls._lock:
            if cls._instance is not None:
                cls._instance._cleanup()
                cls._instance = None

    def _initialize(self) -> None:
        """Initialize all module loggers based on configuration."""
        if self._initialized:
            return

        try:
            self._config = FCDebugConfig.from_env()
            self._truncation = TruncationConfig.from_env()
        except Exception:
            # Graceful degradation: use defaults if config loading fails
            self._config = FCDebugConfig()
            self._truncation = TruncationConfig()

        # Create log directory
        log_dir = Path("logs/fc_debug")
        ensure_log_directory(log_dir)

        # Initialize combined handler if enabled
        if self._config.combined_log_enabled:
            self._combined_handler = create_rotating_file_handler(
                log_dir / "fc_combined.log",
                max_bytes=self._config.log_max_bytes,
                backup_count=self._config.log_backup_count,
            )

        # Initialize per-module loggers
        for module in FCModule:
            self._module_loggers[module] = self._create_module_logger(module, log_dir)

        self._initialized = True

    def _create_module_logger(
        self,
        module: FCModule,
        log_dir: Path,
    ) -> ModuleLogger:
        """Create a logger for a specific module."""
        assert self._config is not None

        # Get module-specific config
        enabled = self._config.is_module_enabled(module)
        level = self._config.get_module_level(module)

        # Create logger with unique name
        logger_name = f"AIStudioProxyServer.FC.{module.name}"
        logger = logging.getLogger(logger_name)
        logger.setLevel(level if enabled else logging.CRITICAL + 1)
        logger.propagate = False  # Don't propagate to root logger

        # Clear existing handlers
        logger.handlers.clear()

        file_handler = None
        if enabled and self._config.master_enabled:
            # Create file handler
            file_handler = create_rotating_file_handler(
                log_dir / module.log_filename,
                max_bytes=self._config.log_max_bytes,
                backup_count=self._config.log_backup_count,
                level=level,
            )
            logger.addHandler(file_handler)

            # Add to combined log if enabled
            if self._combined_handler:
                logger.addHandler(self._combined_handler)

        return ModuleLogger(
            module=module,
            logger=logger,
            enabled=enabled and self._config.master_enabled,
            level=level,
            file_handler=file_handler,
        )

    def _cleanup(self) -> None:
        """Clean up all handlers."""
        for module_logger in self._module_loggers.values():
            if module_logger.file_handler:
                module_logger.file_handler.close()
                module_logger.logger.removeHandler(module_logger.file_handler)

        if self._combined_handler:
            self._combined_handler.close()

        self._module_loggers.clear()
        self._initialized = False

    # =========================================================================
    # Public Logging Methods
    # =========================================================================

    def is_enabled(self, module: FCModule) -> bool:
        """Check if a module is enabled for logging."""
        if module not in self._module_loggers:
            return False
        return self._module_loggers[module].enabled

    def debug(
        self,
        module: FCModule,
        message: str,
        req_id: str = "",
        payload: Optional[Any] = None,
        **kwargs: Any,
    ) -> None:
        """Log a DEBUG message for a module."""
        self._log(module, logging.DEBUG, message, req_id, payload, **kwargs)

    def info(
        self,
        module: FCModule,
        message: str,
        req_id: str = "",
        payload: Optional[Any] = None,
        **kwargs: Any,
    ) -> None:
        """Log an INFO message for a module."""
        self._log(module, logging.INFO, message, req_id, payload, **kwargs)

    def warning(
        self,
        module: FCModule,
        message: str,
        req_id: str = "",
        payload: Optional[Any] = None,
        **kwargs: Any,
    ) -> None:
        """Log a WARNING message for a module."""
        self._log(module, logging.WARNING, message, req_id, payload, **kwargs)

    def error(
        self,
        module: FCModule,
        message: str,
        req_id: str = "",
        payload: Optional[Any] = None,
        exc_info: bool = False,
        **kwargs: Any,
    ) -> None:
        """Log an ERROR message for a module."""
        self._log(
            module, logging.ERROR, message, req_id, payload, exc_info=exc_info, **kwargs
        )

    def _log(
        self,
        module: FCModule,
        level: int,
        message: str,
        req_id: str = "",
        payload: Optional[Any] = None,
        exc_info: bool = False,
        **kwargs: Any,
    ) -> None:
        """Internal logging method."""
        if module not in self._module_loggers:
            return

        module_logger = self._module_loggers[module]
        if not module_logger.enabled:
            return

        # Build the full message
        prefix = module.prefix
        req_prefix = f"[{req_id}] " if req_id else ""

        # Handle payload truncation
        payload_str = ""
        if payload is not None:
            payload_str = self._format_payload(payload, module)

        full_message = f"{req_prefix}{prefix} {message}"
        if payload_str:
            full_message += f"\n{payload_str}"

        # Log it
        module_logger.logger.log(level, full_message, exc_info=exc_info)

    def _format_payload(self, payload: Any, module: FCModule) -> str:
        """Format and optionally truncate a payload for logging."""
        if self._truncation is None or not self._truncation.enabled:
            return str(payload)

        # Determine max length based on payload type
        max_length = self._truncation.get_max_length(payload, module)
        return truncate_payload(payload, max_length)

    # =========================================================================
    # Convenience Methods for Specific Modules
    # =========================================================================

    def log_cache_hit(self, req_id: str, digest: str, age_seconds: float) -> None:
        """Log a cache hit event."""
        self.debug(
            FCModule.CACHE,
            f"HIT - digest={digest[:8]}..., age={age_seconds:.1f}s",
            req_id=req_id,
        )

    def log_cache_miss(self, req_id: str, reason: str) -> None:
        """Log a cache miss event."""
        self.debug(
            FCModule.CACHE,
            f"MISS - reason={reason}",
            req_id=req_id,
        )

    def log_ui_action(
        self,
        req_id: str,
        action: str,
        element: str,
        elapsed_ms: Optional[float] = None,
    ) -> None:
        """Log a UI action."""
        timing = f" ({elapsed_ms:.0f}ms)" if elapsed_ms else ""
        self.debug(
            FCModule.UI,
            f"{action} {element}{timing}",
            req_id=req_id,
        )

    def log_wire_parse(
        self,
        req_id: str,
        func_name: str,
        params: Dict[str, Any],
        success: bool = True,
    ) -> None:
        """Log wire format parsing."""
        status = "parsed" if success else "FAILED"
        self.debug(
            FCModule.WIRE,
            f"Function '{func_name}' {status}",
            req_id=req_id,
            payload=params if params else None,
        )

    def log_dom_extraction(
        self,
        req_id: str,
        call_count: int,
        strategy: str,
    ) -> None:
        """Log DOM-based function call extraction."""
        self.debug(
            FCModule.DOM,
            f"Extracted {call_count} call(s) via {strategy}",
            req_id=req_id,
        )

    def log_schema_conversion(
        self,
        req_id: str,
        tool_count: int,
        elapsed_ms: float,
    ) -> None:
        """Log schema conversion."""
        self.info(
            FCModule.SCHEMA,
            f"Converted {tool_count} tools in {elapsed_ms:.2f}ms",
            req_id=req_id,
        )

    def log_response_format(
        self,
        req_id: str,
        call_count: int,
        finish_reason: str,
    ) -> None:
        """Log response formatting."""
        self.debug(
            FCModule.RESPONSE,
            f"Formatted {call_count} tool calls, finish_reason={finish_reason}",
            req_id=req_id,
        )

    def log_mode_selection(
        self,
        req_id: str,
        mode: str,
        reason: str,
    ) -> None:
        """Log mode selection decision."""
        self.info(
            FCModule.ORCHESTRATOR,
            f"Mode={mode}, reason={reason}",
            req_id=req_id,
        )


# Global convenience function
def get_fc_logger() -> FunctionCallingDebugLogger:
    """Get the FC debug logger instance."""
    return FunctionCallingDebugLogger.get_instance()
