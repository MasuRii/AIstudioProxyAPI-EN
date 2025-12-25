# Function Calling Debug Logging Architecture

**Version:** 1.0  
**Date:** 2025-12-25  
**Status:** Draft  
**Author:** Architect Agent

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Problem Statement](#problem-statement)
3. [Design Goals](#design-goals)
4. [Architecture Overview](#architecture-overview)
5. [Environment Configuration](#environment-configuration)
6. [Module Structure](#module-structure)
7. [FunctionCallingDebugLogger Class Design](#functioncallingdebuglogger-class-design)
8. [Payload Truncation Strategy](#payload-truncation-strategy)
9. [Log File Organization](#log-file-organization)
10. [Integration Patterns](#integration-patterns)
11. [Example Usage](#example-usage)
12. [Migration Guide](#migration-guide)
13. [Implementation Checklist](#implementation-checklist)

---

## Executive Summary

This document defines a modular, configurable debug logging architecture for the Function Calling (FC) subsystem. The architecture enables granular control over logging for each FC component, with separate log files per module, configurable log levels, payload truncation, and request correlation.

### Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Logger per module | Yes | Independent enable/disable, separate log files |
| Separate log files | `logs/fc_debug/{module}.log` | Avoid 1000+ line logs, easier debugging |
| Configuration | `.env` variables | Consistent with existing config pattern |
| Payload truncation | Configurable max length | Tool definitions can be 10KB+ |
| Request correlation | `request_id` in all logs | Trace full request flow across modules |

---

## Problem Statement

### Current State
- Function calling logs are scattered across a single `logs/app.log` file
- Logs can reach 1500+ lines, making it hard to debug specific issues
- All FC components log at the same level (controlled by `FUNCTION_CALLING_DEBUG`)
- No way to isolate logs for specific components (e.g., only DOM parsing)
- Large payloads (tool definitions, arguments) clutter logs

### Existing FC Log Prefixes
```
[FC:Cache]  - Cache hits/misses/invalidation
[FC:UI]     - Browser UI automation
[FC:Perf]   - Performance metrics
[FC:Wire]   - Wire format parsing
```

### Missing Prefix
```
[FC:DOM]    - DOM response parser (currently no prefix)
```

---

## Design Goals

1. **Modular Logging** - Each component can be enabled/disabled independently
2. **Separate Log Files** - One file per module to avoid huge single files
3. **Configurable Levels** - DEBUG, INFO, WARNING, ERROR per module
4. **Request Correlation** - All logs include `request_id` for tracing
5. **Payload Truncation** - Configurable truncation for large objects
6. **Minimal Performance Impact** - Lazy evaluation, no logging if disabled
7. **Backward Compatibility** - Works alongside existing Grid Logger

---

## Architecture Overview

```
+------------------------------------------------------------------+
|                    FunctionCallingDebugLogger                     |
|                         (Singleton)                               |
+------------------------------------------------------------------+
|  - _modules: Dict[FCModule, ModuleConfig]                        |
|  - _file_handlers: Dict[FCModule, RotatingFileHandler]           |
|  - _truncation_config: TruncationConfig                          |
+------------------------------------------------------------------+
         |              |              |              |
         v              v              v              v
+------------+  +------------+  +------------+  +------------+
| ORCHESTR.  |  |   CACHE    |  |    UI      |  |   WIRE     |
| Logger     |  |   Logger   |  |   Logger   |  |   Logger   |
| (fc_orch.) |  | (fc_cache) |  |  (fc_ui)   |  |  (fc_wire) |
+------------+  +------------+  +------------+  +------------+
         |              |              |              |
         v              v              v              v
+------------+  +------------+  +------------+  +------------+
| fc_orch.   |  | fc_cache.  |  |  fc_ui.    |  | fc_wire.   |
|   .log     |  |   log      |  |   log      |  |   .log     |
+------------+  +------------+  +------------+  +------------+

+------------+  +------------+  +------------+
|    DOM     |  |  SCHEMA    |  |  RESPONSE  |
|   Logger   |  |   Logger   |  |   Logger   |
|  (fc_dom)  |  |(fc_schema) |  |(fc_resp)   |
+------------+  +------------+  +------------+
         |              |              |
         v              v              v
+------------+  +------------+  +------------+
|  fc_dom.   |  | fc_schema. |  | fc_resp.   |
|   log      |  |   log      |  |   log      |
+------------+  +------------+  +------------+
```

---

## Environment Configuration

### New `.env` Variables

Add the following to `.env.example` under the Function Calling section:

```bash
# =============================================================================
# Function Calling Debug Logging Configuration
# =============================================================================

# Master switch for FC debug logging (default: false)
# When false, all FC debug logging is disabled regardless of module settings
FC_DEBUG_ENABLED=false

# Per-module enable/disable (default: false for all)
FC_DEBUG_ORCHESTRATOR=false
FC_DEBUG_UI=false
FC_DEBUG_CACHE=false
FC_DEBUG_WIRE=false
FC_DEBUG_DOM=false
FC_DEBUG_SCHEMA=false
FC_DEBUG_RESPONSE=false

# Per-module log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
# Only affects enabled modules
FC_DEBUG_LEVEL_ORCHESTRATOR=DEBUG
FC_DEBUG_LEVEL_UI=DEBUG
FC_DEBUG_LEVEL_CACHE=DEBUG
FC_DEBUG_LEVEL_WIRE=DEBUG
FC_DEBUG_LEVEL_DOM=DEBUG
FC_DEBUG_LEVEL_SCHEMA=DEBUG
FC_DEBUG_LEVEL_RESPONSE=DEBUG

# Log file rotation settings
FC_DEBUG_LOG_MAX_BYTES=5242880
FC_DEBUG_LOG_BACKUP_COUNT=3

# Payload truncation settings
FC_DEBUG_TRUNCATE_ENABLED=true
FC_DEBUG_TRUNCATE_MAX_TOOL_DEF=500
FC_DEBUG_TRUNCATE_MAX_ARGS=1000
FC_DEBUG_TRUNCATE_MAX_RESPONSE=2000

# Combined log option (also write to single fc_combined.log)
FC_DEBUG_COMBINED_LOG=false
```

### Configuration Priority

1. `FC_DEBUG_ENABLED=false` - Disables ALL FC debug logging (master kill switch)
2. `FUNCTION_CALLING_DEBUG=true` - Legacy compatibility, enables ORCHESTRATOR module
3. Per-module `FC_DEBUG_*` - Fine-grained control

---

## Module Structure

### File Layout

```
logging_utils/
    __init__.py                    # Export FC debug utilities
    core/
        ...existing files...
    fc_debug/                      # NEW: FC debug logging module
        __init__.py                # Module exports
        config.py                  # FCDebugConfig dataclass
        logger.py                  # FunctionCallingDebugLogger class
        modules.py                 # FCModule enum and ModuleConfig
        truncation.py              # TruncationConfig and helpers
        formatters.py              # FCDebugFormatter class
```

### Module Enum

```python
# logging_utils/fc_debug/modules.py

from enum import Enum

class FCModule(Enum):
    """Function Calling debug logging modules."""
    
    ORCHESTRATOR = "fc_orchestrator"   # Mode selection, fallback logic, high-level flow
    UI = "fc_ui"                        # Browser UI automation (toggle, dialog, paste)
    CACHE = "fc_cache"                  # Cache hits/misses/invalidation
    WIRE = "fc_wire"                    # Wire format parsing from network
    DOM = "fc_dom"                      # DOM-based function call extraction
    SCHEMA = "fc_schema"                # Schema conversion and validation
    RESPONSE = "fc_response"            # Response formatting for OpenAI compatibility

    @property
    def prefix(self) -> str:
        """Get the log prefix for this module."""
        return f"[FC:{self.name.upper()}]"
    
    @property
    def env_enabled_key(self) -> str:
        """Get the environment variable key for enabling this module."""
        return f"FC_DEBUG_{self.name.upper()}"
    
    @property
    def env_level_key(self) -> str:
        """Get the environment variable key for log level."""
        return f"FC_DEBUG_LEVEL_{self.name.upper()}"
    
    @property
    def log_filename(self) -> str:
        """Get the log filename for this module."""
        return f"{self.value}.log"
```

---

## FunctionCallingDebugLogger Class Design

### Core Class

```python
# logging_utils/fc_debug/logger.py

import logging
import logging.handlers
import os
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Optional, Callable

from .modules import FCModule
from .config import FCDebugConfig
from .truncation import TruncationConfig, truncate_payload
from .formatters import FCDebugFormatter


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
        
        # Get a module-specific logger
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
        self._config = FCDebugConfig.from_env()
        self._truncation = TruncationConfig.from_env()
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
        
        # Create log directory
        log_dir = Path("logs/fc_debug")
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize combined handler if enabled
        if self._config.combined_log_enabled:
            self._combined_handler = self._create_file_handler(
                log_dir / "fc_combined.log"
            )
        
        # Initialize per-module loggers
        for module in FCModule:
            self._module_loggers[module] = self._create_module_logger(module, log_dir)
        
        self._initialized = True
    
    def _create_module_logger(
        self, 
        module: FCModule, 
        log_dir: Path
    ) -> ModuleLogger:
        """Create a logger for a specific module."""
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
            file_handler = self._create_file_handler(log_dir / module.log_filename)
            file_handler.setLevel(level)
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
    
    def _create_file_handler(
        self, 
        log_path: Path
    ) -> logging.handlers.RotatingFileHandler:
        """Create a rotating file handler with FC debug formatter."""
        handler = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=self._config.log_max_bytes,
            backupCount=self._config.log_backup_count,
            encoding="utf-8",
        )
        handler.setFormatter(FCDebugFormatter())
        return handler
    
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
            module, logging.ERROR, message, req_id, payload, 
            exc_info=exc_info, **kwargs
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
        if not self._truncation.enabled:
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
```

### Configuration Class

```python
# logging_utils/fc_debug/config.py

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
        # Master switch
        master = os.environ.get("FC_DEBUG_ENABLED", "false").lower() in ("true", "1", "yes")
        
        # Legacy compatibility: FUNCTION_CALLING_DEBUG enables ORCHESTRATOR
        legacy_debug = os.environ.get("FUNCTION_CALLING_DEBUG", "false").lower() in ("true", "1", "yes")
        
        # Per-module enabled
        module_enabled: Dict[FCModule, bool] = {}
        for module in FCModule:
            env_val = os.environ.get(module.env_enabled_key, "false").lower()
            module_enabled[module] = env_val in ("true", "1", "yes")
        
        # Legacy: enable ORCHESTRATOR if FUNCTION_CALLING_DEBUG is set
        if legacy_debug and not master:
            master = True
            module_enabled[FCModule.ORCHESTRATOR] = True
        
        # Per-module levels
        module_levels: Dict[FCModule, int] = {}
        for module in FCModule:
            level_str = os.environ.get(module.env_level_key, "DEBUG").upper()
            module_levels[module] = getattr(logging, level_str, logging.DEBUG)
        
        # Rotation settings
        max_bytes = int(os.environ.get("FC_DEBUG_LOG_MAX_BYTES", str(5 * 1024 * 1024)))
        backup_count = int(os.environ.get("FC_DEBUG_LOG_BACKUP_COUNT", "3"))
        
        # Combined log
        combined = os.environ.get("FC_DEBUG_COMBINED_LOG", "false").lower() in ("true", "1", "yes")
        
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
```

### Truncation Utilities

```python
# logging_utils/fc_debug/truncation.py

import json
import os
from dataclasses import dataclass
from typing import Any, Optional

from .modules import FCModule


@dataclass
class TruncationConfig:
    """Configuration for payload truncation."""
    
    enabled: bool = True
    max_tool_definition: int = 500
    max_arguments: int = 1000
    max_response: int = 2000
    max_default: int = 500
    
    @classmethod
    def from_env(cls) -> "TruncationConfig":
        """Load truncation config from environment."""
        return cls(
            enabled=os.environ.get(
                "FC_DEBUG_TRUNCATE_ENABLED", "true"
            ).lower() in ("true", "1", "yes"),
            max_tool_definition=int(
                os.environ.get("FC_DEBUG_TRUNCATE_MAX_TOOL_DEF", "500")
            ),
            max_arguments=int(
                os.environ.get("FC_DEBUG_TRUNCATE_MAX_ARGS", "1000")
            ),
            max_response=int(
                os.environ.get("FC_DEBUG_TRUNCATE_MAX_RESPONSE", "2000")
            ),
        )
    
    def get_max_length(self, payload: Any, module: FCModule) -> int:
        """Get the max length for a payload based on module and content type."""
        # Module-specific defaults
        if module == FCModule.SCHEMA:
            return self.max_tool_definition
        elif module in (FCModule.WIRE, FCModule.DOM):
            return self.max_arguments
        elif module == FCModule.RESPONSE:
            return self.max_response
        return self.max_default


def truncate_payload(payload: Any, max_length: int) -> str:
    """
    Truncate a payload for logging.
    
    Handles dicts, lists, and strings intelligently:
    - Shows structure summary for truncated objects
    - Preserves enough context to be useful
    """
    try:
        if isinstance(payload, str):
            if len(payload) <= max_length:
                return payload
            return f"{payload[:max_length]}... [truncated, total={len(payload)}]"
        
        if isinstance(payload, (dict, list)):
            json_str = json.dumps(payload, indent=2, default=str)
            if len(json_str) <= max_length:
                return json_str
            
            # Show truncated with summary
            truncated = json_str[:max_length]
            
            # Add summary
            if isinstance(payload, dict):
                summary = f"{{...}} [keys={list(payload.keys())[:5]}, truncated={len(json_str)}]"
            else:
                summary = f"[...] [length={len(payload)}, truncated={len(json_str)}]"
            
            return f"{truncated}\n... {summary}"
        
        # For other types, convert to string and truncate
        str_val = str(payload)
        if len(str_val) <= max_length:
            return str_val
        return f"{str_val[:max_length]}... [truncated]"
    
    except Exception as e:
        return f"[Error formatting payload: {e}]"


def summarize_tools(tools: list) -> str:
    """Create a summary of tool definitions without full schemas."""
    if not tools:
        return "[]"
    
    summaries = []
    for tool in tools[:10]:  # Max 10 tools in summary
        if isinstance(tool, dict):
            func = tool.get("function", tool)
            name = func.get("name", "unknown")
            params = func.get("parameters", {})
            param_count = len(params.get("properties", {})) if isinstance(params, dict) else 0
            summaries.append(f"{name}({param_count} params)")
    
    result = ", ".join(summaries)
    if len(tools) > 10:
        result += f", ... +{len(tools) - 10} more"
    
    return f"[{result}]"
```

### Formatter

```python
# logging_utils/fc_debug/formatters.py

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
        self._tz = ZoneInfo("America/Chicago")
    
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
```

---

## Payload Truncation Strategy

### Problem
- Tool definitions can be 10KB+ with full JSON schemas
- Function arguments can contain large file contents
- Wire payloads include full response bodies

### Solution

| Payload Type | Default Max | Truncation Strategy |
|--------------|-------------|---------------------|
| Tool Definitions | 500 chars | Summarize: `tool_name(N params)` |
| Function Arguments | 1000 chars | First N chars + `[truncated, total=X]` |
| Wire Payloads | 2000 chars | First N chars + key count |
| DOM Content | 1000 chars | First N chars |
| Response Body | 2000 chars | First N chars + size |

### Truncation Examples

**Tool Definition:**
```
Before: {"type": "function", "function": {"name": "read_file", "parameters": {...500 lines...}}}
After:  [read_file(3 params), write_file(2 params), ... +5 more]
```

**Function Arguments:**
```
Before: {"content": "...10000 chars of file content..."}
After:  {"content": "first 500 chars of file content...
         ... [truncated, total=10000]
```

---

## Log File Organization

### Directory Structure

```
logs/
    app.log                    # Existing main log (unchanged)
    fc_debug/                  # New FC debug logs
        fc_orchestrator.log    # Mode selection, fallback logic
        fc_ui.log              # Browser UI automation
        fc_cache.log           # Cache hits/misses
        fc_wire.log            # Wire format parsing
        fc_dom.log             # DOM extraction
        fc_schema.log          # Schema conversion
        fc_response.log        # Response formatting
        fc_combined.log        # Optional: all modules combined
```

### Log Rotation

- **Max Size:** 5MB per file (configurable)
- **Backups:** 3 files (e.g., `fc_cache.log.1`, `fc_cache.log.2`, `fc_cache.log.3`)
- **Total Max:** ~20MB per module = 140MB max for all FC debug logs

### Log Format

```
2025-12-25 14:32:15.123 | DEBUG   | [abc123] [FC:CACHE] HIT - digest=a1b2c3d4..., age=5.2s
2025-12-25 14:32:15.456 | INFO    | [abc123] [FC:UI] Toggle enabled successfully (245ms)
2025-12-25 14:32:15.789 | WARNING | [abc123] [FC:WIRE] Function 'read_file' parsed with empty args
```

---

## Integration Patterns

### Pattern 1: Replace Existing FC Logs in Orchestrator

**Before:**
```python
self.logger.info(
    f"[{req_id}] [FC:Cache] HIT - skipping native FC setup "
    f"(digest={state.tools_digest[:8]}...)"
)
```

**After:**
```python
from logging_utils.fc_debug import get_fc_logger, FCModule

fc_logger = get_fc_logger()
fc_logger.log_cache_hit(req_id, state.tools_digest, cache_age)
```

### Pattern 2: DOM Parser Integration

**Before (no prefix):**
```python
self.logger.debug(
    f"[{self.req_id}] Found {len(native_calls)} native function call chunk(s)"
)
```

**After:**
```python
from logging_utils.fc_debug import get_fc_logger, FCModule

fc_logger = get_fc_logger()
fc_logger.log_dom_extraction(self.req_id, len(native_calls), "native_chunk")
```

### Pattern 3: Wire Parser Integration

**Before:**
```python
self.logger.warning(
    f"[FC:Wire] Function '{func_name}' parsed with empty args - "
    f"may indicate wire format parsing failure."
)
```

**After:**
```python
from logging_utils.fc_debug import get_fc_logger, FCModule

fc_logger = get_fc_logger()
fc_logger.log_wire_parse(req_id, func_name, params={}, success=False)
fc_logger.warning(
    FCModule.WIRE,
    f"Function '{func_name}' parsed with empty args - possible parsing failure",
    req_id=req_id,
    payload={"raw": raw_data[:200]},
)
```

### Pattern 4: UI Controller Integration

**Before:**
```python
self.logger.debug(
    f"[{self.req_id}] [FC:UI] Toggle check complete in {elapsed:.3f}s: "
    f"enabled={enabled}"
)
```

**After:**
```python
from logging_utils.fc_debug import get_fc_logger, FCModule

fc_logger = get_fc_logger()
fc_logger.log_ui_action(
    self.req_id,
    action="check_toggle",
    element=f"enabled={enabled}",
    elapsed_ms=elapsed * 1000,
)
```

### Pattern 5: Conditional Logging (Performance)

```python
fc_logger = get_fc_logger()

# Skip expensive operations if logging is disabled
if fc_logger.is_enabled(FCModule.SCHEMA):
    fc_logger.debug(
        FCModule.SCHEMA,
        "Tool schema details",
        req_id=req_id,
        payload=expensive_to_serialize_object,
    )
```

---

## Example Usage

### Enabling Specific Module Debugging

**Scenario:** Debug cache issues only

```bash
# .env
FC_DEBUG_ENABLED=true
FC_DEBUG_CACHE=true
FC_DEBUG_LEVEL_CACHE=DEBUG
```

**Result:** Only `logs/fc_debug/fc_cache.log` is populated:
```
2025-12-25 14:32:15.123 | DEBUG   | [req001] [FC:CACHE] Checking cache validity
2025-12-25 14:32:15.124 | DEBUG   | [req001] [FC:CACHE] HIT - digest=a1b2c3d4..., age=5.2s
2025-12-25 14:32:15.125 | DEBUG   | [req001] [FC:CACHE] Skipping UI operations
```

### Enabling All Modules for Full Debug

```bash
# .env
FC_DEBUG_ENABLED=true
FC_DEBUG_ORCHESTRATOR=true
FC_DEBUG_UI=true
FC_DEBUG_CACHE=true
FC_DEBUG_WIRE=true
FC_DEBUG_DOM=true
FC_DEBUG_SCHEMA=true
FC_DEBUG_RESPONSE=true
FC_DEBUG_COMBINED_LOG=true
```

### Programmatic Usage in Component

```python
# In function_calling_orchestrator.py

from logging_utils.fc_debug import get_fc_logger, FCModule

class FunctionCallingOrchestrator:
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger("AIStudioProxyServer")
        self._fc_logger = get_fc_logger()
    
    async def prepare_request(
        self,
        tools: Optional[List[Dict[str, Any]]],
        req_id: str,
        ...
    ) -> FunctionCallingState:
        # Log mode selection
        self._fc_logger.log_mode_selection(
            req_id,
            mode=self._config.mode.value,
            reason="tools present" if tools else "no tools",
        )
        
        # Check cache
        if self._cache.is_valid(tools_digest, model_id):
            self._fc_logger.log_cache_hit(req_id, tools_digest, cache_age)
            return state
        
        self._fc_logger.log_cache_miss(req_id, "digest mismatch")
        
        # ... rest of logic
```

---

## Migration Guide

### Phase 1: Add Infrastructure (Non-Breaking)

1. Create `logging_utils/fc_debug/` module structure
2. Implement `FunctionCallingDebugLogger` class
3. Add new `.env` variables to `.env.example`
4. Write unit tests for new logging infrastructure

### Phase 2: Gradual Integration

1. Add FC logger alongside existing logs (don't remove)
2. Start with one component (e.g., Cache)
3. Verify logs appear in new files
4. Iterate through remaining components

### Phase 3: Cleanup (Optional)

1. Remove duplicate logging calls
2. Standardize all FC logs through new system
3. Update documentation

---

## Implementation Checklist

### Files to Create

- [ ] `logging_utils/fc_debug/__init__.py`
- [ ] `logging_utils/fc_debug/modules.py`
- [ ] `logging_utils/fc_debug/config.py`
- [ ] `logging_utils/fc_debug/logger.py`
- [ ] `logging_utils/fc_debug/truncation.py`
- [ ] `logging_utils/fc_debug/formatters.py`

### Files to Modify

- [ ] `.env.example` - Add new FC debug variables
- [ ] `api_utils/utils_ext/function_calling_orchestrator.py` - Integrate FC logger
- [ ] `api_utils/utils_ext/function_calling_cache.py` - Integrate FC logger
- [ ] `api_utils/utils_ext/function_call_response_parser.py` - Add [FC:DOM] prefix
- [ ] `browser_utils/page_controller_modules/function_calling.py` - Integrate FC logger
- [ ] `stream/interceptors.py` - Integrate FC logger for [FC:Wire]

### Tests to Write

- [ ] `tests/logging_utils/fc_debug/test_logger.py`
- [ ] `tests/logging_utils/fc_debug/test_truncation.py`
- [ ] `tests/logging_utils/fc_debug/test_config.py`

---

## Appendix: Quick Reference

### Environment Variable Summary

| Variable | Default | Description |
|----------|---------|-------------|
| `FC_DEBUG_ENABLED` | `false` | Master switch |
| `FC_DEBUG_ORCHESTRATOR` | `false` | Enable orchestrator logging |
| `FC_DEBUG_UI` | `false` | Enable UI logging |
| `FC_DEBUG_CACHE` | `false` | Enable cache logging |
| `FC_DEBUG_WIRE` | `false` | Enable wire parser logging |
| `FC_DEBUG_DOM` | `false` | Enable DOM parser logging |
| `FC_DEBUG_SCHEMA` | `false` | Enable schema converter logging |
| `FC_DEBUG_RESPONSE` | `false` | Enable response formatter logging |
| `FC_DEBUG_LEVEL_*` | `DEBUG` | Per-module log level |
| `FC_DEBUG_LOG_MAX_BYTES` | `5242880` | Max log file size |
| `FC_DEBUG_LOG_BACKUP_COUNT` | `3` | Rotation backup count |
| `FC_DEBUG_TRUNCATE_ENABLED` | `true` | Enable payload truncation |
| `FC_DEBUG_TRUNCATE_MAX_*` | varies | Truncation limits |
| `FC_DEBUG_COMBINED_LOG` | `false` | Write to combined log |

### Module Prefix Mapping

| Module | Prefix | Log File |
|--------|--------|----------|
| ORCHESTRATOR | `[FC:ORCH]` | `fc_orchestrator.log` |
| UI | `[FC:UI]` | `fc_ui.log` |
| CACHE | `[FC:CACHE]` | `fc_cache.log` |
| WIRE | `[FC:WIRE]` | `fc_wire.log` |
| DOM | `[FC:DOM]` | `fc_dom.log` |
| SCHEMA | `[FC:SCHEMA]` | `fc_schema.log` |
| RESPONSE | `[FC:RESP]` | `fc_response.log` |

---

*End of Architecture Design Document*
