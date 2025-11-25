"""
Thinking Mode Parameter Normalization Module
Normalizes the reasoning_effort parameter into a standardized thinking directive.

This module is responsible for converting various formats of the reasoning_effort parameter into a unified internal directive structure.
"""

from typing import Optional, Any, Dict
from dataclasses import dataclass
from config import ENABLE_THINKING_BUDGET, DEFAULT_THINKING_BUDGET
from config.settings import (
    DISABLE_THINKING_BUDGET_ON_STREAMING_DISABLE,
    THINKING_BUDGET_LOW,
    THINKING_BUDGET_MEDIUM,
    THINKING_BUDGET_HIGH
)


@dataclass
class ThinkingDirective:
    """Standardized thinking directive

    Attributes:
        thinking_enabled: Whether thinking mode is enabled (master switch)
        budget_enabled: Whether to limit thinking budget
        budget_value: Budget token count (valid only when budget_enabled=True)
        original_value: Original reasoning_effort value (for logging)
    """
    thinking_enabled: bool
    budget_enabled: bool
    budget_value: Optional[int]
    original_value: Any


def normalize_reasoning_effort(reasoning_effort: Optional[Any], is_streaming: bool = True) -> ThinkingDirective:
    """Normalize reasoning_effort parameter into a standardized thinking directive

    Args:
        reasoning_effort: reasoning_effort parameter in API request, possible values:
            - None: Use default configuration
            - 0 or "0": Disable thinking mode
            - Positive integer: Enable thinking, set specific budget value
            - "low"/"medium"/"high": Enable thinking, use preset budget
            - "none" or "-1" or -1: Enable thinking, unlimited budget
        is_streaming: Whether it is a streaming request (affects DISABLE_THINKING_BUDGET_ON_STREAMING_DISABLE config)

    Returns:
        ThinkingDirective: Standardized thinking directive

    Example:
        >>> normalize_reasoning_effort(None)
        ThinkingDirective(thinking_enabled=False, budget_enabled=False, budget_value=None, ...)

        >>> normalize_reasoning_effort(0)
        ThinkingDirective(thinking_enabled=False, budget_enabled=False, budget_value=None, ...)

        >>> normalize_reasoning_effort("medium")
        ThinkingDirective(thinking_enabled=True, budget_enabled=True, budget_value=8000, ...)

        >>> normalize_reasoning_effort("none")
        ThinkingDirective(thinking_enabled=True, budget_enabled=False, budget_value=None, ...)
    """

    # Scenario 1: User unspecified, use default configuration
    if reasoning_effort is None:
        return ThinkingDirective(
            thinking_enabled=ENABLE_THINKING_BUDGET,
            budget_enabled=ENABLE_THINKING_BUDGET,
            budget_value=DEFAULT_THINKING_BUDGET if ENABLE_THINKING_BUDGET else None,
            original_value=None
        )

    # Scenario 2: Disable thinking mode (reasoning_effort = 0 or "0")
    if reasoning_effort == 0 or (isinstance(reasoning_effort, str) and reasoning_effort.strip() == "0"):
        return ThinkingDirective(
            thinking_enabled=False,
            budget_enabled=False,
            budget_value=None,
            original_value=reasoning_effort
        )

    # Scenario 3: Enable thinking but unlimited budget (reasoning_effort = "none" / "-1" / -1)
    if isinstance(reasoning_effort, str):
        reasoning_str = reasoning_effort.strip().lower()
        if reasoning_str in ["none", "-1"]:
            return ThinkingDirective(
                thinking_enabled=True,
                budget_enabled=False,
                budget_value=None,
                original_value=reasoning_effort
            )
    elif reasoning_effort == -1:
        return ThinkingDirective(
            thinking_enabled=True,
            budget_enabled=False,
            budget_value=None,
            original_value=reasoning_effort
        )

    # Scenario 4: Enable thinking and limit budget (specific number or preset value)
    budget_value = _parse_budget_value(reasoning_effort)

    if budget_value is not None and budget_value > 0:
        return ThinkingDirective(
            thinking_enabled=True,
            budget_enabled=True,
            budget_value=budget_value,
            original_value=reasoning_effort
        )

    # Invalid value: Use default configuration
    return ThinkingDirective(
        thinking_enabled=ENABLE_THINKING_BUDGET,
        budget_enabled=ENABLE_THINKING_BUDGET,
        budget_value=DEFAULT_THINKING_BUDGET if ENABLE_THINKING_BUDGET else None,
        original_value=reasoning_effort
    )


def normalize_reasoning_effort_with_stream_check(reasoning_effort: Optional[Any], is_streaming: bool = True) -> ThinkingDirective:
    """Normalize thinking directive with stream check
    
    Decides whether to disable thinking budget in non-streaming mode based on DISABLE_THINKING_BUDGET_ON_STREAMING_DISABLE configuration.
    
    Args:
        reasoning_effort: reasoning_effort parameter from API request
        is_streaming: Whether it is a streaming request
        
    Returns:
        ThinkingDirective: Standardized thinking directive
    """
    # First get the basic thinking directive
    directive = normalize_reasoning_effort(reasoning_effort, is_streaming)
    
    # If not streaming and configured to disable budget on streaming disable, then disable
    if not is_streaming and DISABLE_THINKING_BUDGET_ON_STREAMING_DISABLE:
        return ThinkingDirective(
            thinking_enabled=False,
            budget_enabled=False,
            budget_value=None,
            original_value=reasoning_effort
        )
    
    # Otherwise return original directive (allowing thinking budget to remain enabled in non-streaming mode)
    return directive


def _parse_budget_value(reasoning_effort: Any) -> Optional[int]:
    """Parse budget value

    Args:
        reasoning_effort: reasoning_effort parameter value

    Returns:
        int: Budget token count, or None if parsing fails
    """
    # If integer, return directly
    if isinstance(reasoning_effort, int) and reasoning_effort > 0:
        return reasoning_effort

    # If string, try to parse as number
    if isinstance(reasoning_effort, str):
        effort_str = reasoning_effort.strip().lower()

        # Preset value mapping - use values from environment configuration
        effort_map = {
            "low": THINKING_BUDGET_LOW,
            "medium": THINKING_BUDGET_MEDIUM,
            "high": THINKING_BUDGET_HIGH,
        }

        # Try preset values first
        if effort_str in effort_map:
            return effort_map[effort_str]

        # Then try parsing as number
        try:
            value = int(effort_str)
            if value > 0:
                return value
        except (ValueError, TypeError):
            pass

    return None


def format_directive_log(directive: ThinkingDirective) -> str:
    """Format thinking directive as log string

    Args:
        directive: Thinking directive

    Returns:
        str: Formatted log string
    """
    if not directive.thinking_enabled:
        return f"Thinking mode disabled (Original: {directive.original_value})"
    elif directive.budget_enabled and directive.budget_value is not None:
        return f"Thinking enabled with budget: {directive.budget_value} tokens (Original: {directive.original_value})"
    else:
        return f"Thinking enabled, unlimited budget (Original: {directive.original_value})"