import json
import time
from typing import Any, Dict, Optional


def generate_sse_chunk(delta: str, req_id: str, model: str) -> str:
    chunk_data: Dict[str, Any] = {
        "id": f"chatcmpl-{req_id}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": {"content": delta}, "finish_reason": None}],
    }
    return f"data: {json.dumps(chunk_data)}\n\n"


def generate_sse_stop_chunk(
    req_id: str,
    model: str,
    reason: str = "stop",
    usage: Optional[Dict[str, int]] = None,
) -> str:
    stop_chunk_data: Dict[str, Any] = {
        "id": f"chatcmpl-{req_id}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": reason}],
    }
    if usage:
        stop_chunk_data["usage"] = usage
    return f"data: {json.dumps(stop_chunk_data)}\n\ndata: [DONE]\n\n"


def generate_sse_error_chunk(
    message: str, req_id: str, error_type: str = "server_error"
) -> str:
    error_chunk = {
        "error": {"message": message, "type": error_type, "param": None, "code": req_id}
    }
    return f"data: {json.dumps(error_chunk)}\n\n"
