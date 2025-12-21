"""
API utility function module
Contains utility functions for SSE generation, stream processing, token statistics, and request validation
(Refactored: logic moved to api_utils.utils_ext submodules)
"""

from typing import Dict, List, Optional, Tuple, Union, Any, cast
import json
import base64

from .sse import generate_sse_stop_chunk
from .utils_ext import (
    _extension_for_mime,
    calculate_usage_stats,
    clear_stream_queue,
    collect_and_validate_attachments,
    estimate_tokens,
    extract_data_url_to_local,
    extract_json_from_text,
    get_latest_user_text,
    maybe_execute_tools,
    prepare_combined_prompt,
    save_blob_to_local,
    use_helper_get_response,
    use_stream_response,
    validate_chat_request,
)

# For backward compatibility with existing code that might import these private functions
_extract_json_from_text = extract_json_from_text
_get_latest_user_text = get_latest_user_text


def generate_sse_stop_chunk_with_usage(req_id: str, model: str, usage_stats: dict, reason: str = "stop") -> str:
    """Generate SSE stop chunk with usage statistics"""
    return generate_sse_stop_chunk(req_id, model, reason, usage_stats)


__all__ = [
    "generate_sse_stop_chunk_with_usage",
    "extract_data_url_to_local",
    "save_blob_to_local",
    "collect_and_validate_attachments",
    "prepare_combined_prompt",
    "maybe_execute_tools",
    "extract_json_from_text",
    "get_latest_user_text",
    "use_stream_response",
    "clear_stream_queue",
    "use_helper_get_response",
    "validate_chat_request",
    "estimate_tokens",
    "calculate_usage_stats",
    "_extension_for_mime",
]
