"""
Extended utility submodules extracted from api_utils.utils.
This package groups stream, helper, validation, files, and tokens utilities.
"""

from .files import (
    _extension_for_mime,
    collect_and_validate_attachments,
    extract_data_url_to_local,
    save_blob_to_local,
)
from .function_call_response_parser import (
    FunctionCallParseResult,
    FunctionCallResponseParser,
    format_function_calls_to_openai,
)
from .function_calling import (
    CallIdManager,
    FunctionCallingConfig,
    FunctionCallingMode,
    ParsedFunctionCall,
    PendingCall,
    ResponseFormatter,
    SchemaConversionError,
    SchemaConverter,
    build_assistant_message_with_tool_calls,
    convert_openai_tools_to_gemini,
    create_tool_calls_response,
    get_finish_reason,
)
from .function_calling_cache import (
    FunctionCallingCache,
    FunctionCallingCacheEntry,
)
from .function_calling_orchestrator import (
    FunctionCallingOrchestrator,
    FunctionCallingState,
    NativeFunctionCallingError,
    get_effective_function_calling_mode,
    get_function_calling_orchestrator,
    reset_orchestrator,
    should_skip_tool_injection,
)
from .helper import use_helper_get_response
from .prompts import prepare_combined_prompt
from .stream import clear_stream_queue, use_stream_response
from .string_utils import extract_json_from_text, get_latest_user_text
from .tokens import calculate_usage_stats, estimate_tokens
from .tools_execution import maybe_execute_tools
from .validation import validate_chat_request

__all__ = [
    "use_stream_response",
    "clear_stream_queue",
    "use_helper_get_response",
    "validate_chat_request",
    "_extension_for_mime",
    "extract_data_url_to_local",
    "save_blob_to_local",
    "collect_and_validate_attachments",
    "estimate_tokens",
    "calculate_usage_stats",
    "prepare_combined_prompt",
    "maybe_execute_tools",
    "extract_json_from_text",
    "get_latest_user_text",
    # Function Calling utilities
    "FunctionCallingMode",
    "FunctionCallingConfig",
    "SchemaConverter",
    "SchemaConversionError",
    "CallIdManager",
    "PendingCall",
    "ParsedFunctionCall",
    "ResponseFormatter",
    "build_assistant_message_with_tool_calls",
    "get_finish_reason",
    "convert_openai_tools_to_gemini",
    "create_tool_calls_response",
    # Function Calling Cache
    "FunctionCallingCache",
    "FunctionCallingCacheEntry",
    # Function Calling Orchestrator
    "FunctionCallingOrchestrator",
    "FunctionCallingState",
    "NativeFunctionCallingError",
    "get_function_calling_orchestrator",
    "reset_orchestrator",
    "should_skip_tool_injection",
    "get_effective_function_calling_mode",
    # Function Call Response Parser
    "FunctionCallResponseParser",
    "FunctionCallParseResult",
    "format_function_calls_to_openai",
]
