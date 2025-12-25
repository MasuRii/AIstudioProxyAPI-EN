"""
FC Debug Payload Truncation Utilities.

Provides intelligent truncation of large payloads (tool definitions,
function arguments, responses) for readable logging without excessive output.
"""

import json
import os
from dataclasses import dataclass
from typing import Any, List

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
            enabled=os.environ.get("FC_DEBUG_TRUNCATE_ENABLED", "true").lower()
            in ("true", "1", "yes"),
            max_tool_definition=int(
                os.environ.get("FC_DEBUG_TRUNCATE_MAX_TOOL_DEF", "500")
            ),
            max_arguments=int(os.environ.get("FC_DEBUG_TRUNCATE_MAX_ARGS", "1000")),
            max_response=int(os.environ.get("FC_DEBUG_TRUNCATE_MAX_RESPONSE", "2000")),
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

    Args:
        payload: The payload to truncate
        max_length: Maximum allowed length

    Returns:
        Truncated string representation
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
                keys = list(payload.keys())[:5]
                summary = f"{{...}} [keys={keys}, truncated={len(json_str)}]"
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


def summarize_tools(tools: List[Any]) -> str:
    """
    Create a summary of tool definitions without full schemas.

    Args:
        tools: List of tool definition dicts

    Returns:
        Concise summary string
    """
    if not tools:
        return "[]"

    summaries = []
    for tool in tools[:10]:  # Max 10 tools in summary
        if isinstance(tool, dict):
            func = tool.get("function", tool)
            name = func.get("name", "unknown")
            params = func.get("parameters", {})
            param_count = (
                len(params.get("properties", {})) if isinstance(params, dict) else 0
            )
            summaries.append(f"{name}({param_count} params)")

    result = ", ".join(summaries)
    if len(tools) > 10:
        result += f", ... +{len(tools) - 10} more"

    return f"[{result}]"
