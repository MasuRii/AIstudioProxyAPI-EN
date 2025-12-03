"""
Modular FastAPI routers for api_utils.
Each module defines focused endpoint handlers. This package aggregates them.
"""

# Re-export handlers for convenient imports
from .api_keys import add_api_key, delete_api_key, get_api_keys, test_api_key
from .chat import chat_completions
from .health import health_check
from .info import get_api_info
from .logs_ws import websocket_log_endpoint
from .models import list_models
from .queue import cancel_request, get_queue_status
from .static import get_css, get_js, read_index

__all__ = [
    "read_index",
    "get_css",
    "get_js",
    "get_api_info",
    "health_check",
    "list_models",
    "chat_completions",
    "cancel_request",
    "get_queue_status",
    "websocket_log_endpoint",
    "get_api_keys",
    "add_api_key",
    "test_api_key",
    "delete_api_key",
]
