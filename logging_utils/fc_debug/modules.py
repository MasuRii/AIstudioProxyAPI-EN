"""
FC Debug Module Definitions.

Defines the FCModule enum representing different function calling components
that can be independently logged and configured.
"""

from enum import Enum


class FCModule(Enum):
    """Function Calling debug logging modules."""

    ORCHESTRATOR = "fc_orchestrator"  # Mode selection, fallback logic, high-level flow
    UI = "fc_ui"  # Browser UI automation (toggle, dialog, paste)
    CACHE = "fc_cache"  # Cache hits/misses/invalidation
    WIRE = "fc_wire"  # Wire format parsing from network
    DOM = "fc_dom"  # DOM-based function call extraction
    SCHEMA = "fc_schema"  # Schema conversion and validation
    RESPONSE = "fc_response"  # Response formatting for OpenAI compatibility

    @property
    def prefix(self) -> str:
        """Get the log prefix for this module."""
        # Use shorter prefixes for some modules
        prefix_map = {
            "ORCHESTRATOR": "ORCH",
            "RESPONSE": "RESP",
        }
        name = prefix_map.get(self.name, self.name)
        return f"[FC:{name}]"

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
