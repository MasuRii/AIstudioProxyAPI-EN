"""
API Utilities Module
Provides FastAPI application initialization, route handlers, and utility functions
"""

# Application initialization
from .app import create_app

# Queue worker
from .queue_worker import queue_worker

# Request processor
from .request_processor import (
    _process_request_refactored,  # pyright: ignore[reportPrivateUsage]
)

# Route handlers (aggregated from routers)
from .routers import (
    cancel_request,
    chat_completions,
    get_api_info,
    get_queue_status,
    health_check,
    list_models,
    read_index,
    websocket_log_endpoint,
)
from .sse import (
    generate_sse_chunk,
    generate_sse_error_chunk,
    generate_sse_stop_chunk,
)

# Utility functions
from .utils import prepare_combined_prompt
from .utils_ext.helper import use_helper_get_response
from .utils_ext.stream import (
    clear_stream_queue,
    use_stream_response,
)
from .utils_ext.tokens import (
    calculate_usage_stats,
    estimate_tokens,
)
from .utils_ext.validation import validate_chat_request

__all__ = [
    # Application initialization
    "create_app",
    # Route handlers
    "read_index",
    "get_api_info",
    "health_check",
    "list_models",
    "chat_completions",
    "cancel_request",
    "get_queue_status",
    "websocket_log_endpoint",
    # Utility functions
    "generate_sse_chunk",
    "generate_sse_stop_chunk",
    "generate_sse_error_chunk",
    "use_stream_response",
    "clear_stream_queue",
    "use_helper_get_response",
    "validate_chat_request",
    "prepare_combined_prompt",
    "estimate_tokens",
    "calculate_usage_stats",
    # Request processor
    "_process_request_refactored",
    # Queue worker
    "queue_worker",
]
