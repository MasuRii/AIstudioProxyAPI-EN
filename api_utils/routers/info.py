from fastapi import Depends, Request
from fastapi.responses import JSONResponse

from config import MODEL_NAME, get_environment_variable

from ..dependencies import get_current_ai_studio_model_id


async def get_api_info(
    request: Request,
    current_ai_studio_model_id: str = Depends(get_current_ai_studio_model_id),
) -> JSONResponse:
    from .. import auth_utils

    server_port = request.url.port or get_environment_variable(
        "SERVER_PORT_INFO", "8000"
    )
    host = request.headers.get("host") or f"127.0.0.1:{server_port}"
    scheme = request.headers.get("x-forwarded-proto") or request.url.scheme or "http"
    base_url = f"{scheme}://{host}"
    api_base = f"{base_url}/v1"
    effective_model_name = current_ai_studio_model_id or MODEL_NAME

    api_key_required = bool(auth_utils.API_KEYS)
    api_key_count = len(auth_utils.API_KEYS)

    message = (
        f"API Key is required. {api_key_count} valid key(s) configured."
        if api_key_required
        else "API Key is not required."
    )

    return JSONResponse(
        content={
            "model_name": effective_model_name,
            "api_base_url": api_base,
            "server_base_url": base_url,
            "api_key_required": api_key_required,
            "api_key_count": api_key_count,
            "auth_header": "Authorization: Bearer <token> or X-API-Key: <token>"
            if api_key_required
            else None,
            "openai_compatible": True,
            "supported_auth_methods": ["Authorization: Bearer", "X-API-Key"]
            if api_key_required
            else [],
            "message": message,
        }
    )
