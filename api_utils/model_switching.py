from typing import Tuple
from fastapi import HTTPException
from playwright.async_api import Page as AsyncPage

from .context_types import RequestContext


async def analyze_model_requirements(req_id: str, context: RequestContext, requested_model: str, proxy_model_name: str) -> RequestContext:
    logger = context['logger']
    current_ai_studio_model_id = context['current_ai_studio_model_id']
    parsed_model_list = context['parsed_model_list']

    if requested_model and requested_model != proxy_model_name:
        requested_model_id = requested_model.split('/')[-1]
        logger.info(f"[{req_id}] Requesting model: {requested_model_id}")

        if parsed_model_list:
            valid_model_ids = [m.get("id") for m in parsed_model_list]
            if requested_model_id not in valid_model_ids:
                from .error_utils import bad_request
                raise bad_request(req_id, f"Invalid model '{requested_model_id}'. Available models: {', '.join(valid_model_ids)}")

        context['model_id_to_use'] = requested_model_id
        if current_ai_studio_model_id != requested_model_id:
            context['needs_model_switching'] = True
            logger.info(f"[{req_id}] Model switch needed: Current={current_ai_studio_model_id} -> Target={requested_model_id}")

    return context


async def handle_model_switching(req_id: str, context: RequestContext) -> RequestContext:
    if not context['needs_model_switching']:
        return context

    logger = context['logger']
    page = context['page']
    model_switching_lock = context['model_switching_lock']
    model_id_to_use = context['model_id_to_use']

    import server
    async with model_switching_lock:
        if server.current_ai_studio_model_id != model_id_to_use:
            logger.info(f"[{req_id}] Preparing to switch model: {server.current_ai_studio_model_id} -> {model_id_to_use}")
            from browser_utils import switch_ai_studio_model
            switch_success = await switch_ai_studio_model(page, model_id_to_use, req_id)
            if switch_success:
                server.current_ai_studio_model_id = model_id_to_use
                context['model_actually_switched'] = True
                context['current_ai_studio_model_id'] = model_id_to_use
                logger.info(f"[{req_id}] ✅ Model switched successfully: {server.current_ai_studio_model_id}")
            else:
                await _handle_model_switch_failure(req_id, page, model_id_to_use, server.current_ai_studio_model_id, logger)

    return context


async def _handle_model_switch_failure(req_id: str, page: AsyncPage, model_id_to_use: str, model_before_switch: str, logger) -> None:
    import server
    logger.warning(f"[{req_id}] ❌ Failed to switch to model {model_id_to_use}.")
    server.current_ai_studio_model_id = model_before_switch
    from .error_utils import http_error
    raise http_error(422, f"[{req_id}] Failed to switch to model '{model_id_to_use}'. Ensure model is available.")


async def handle_parameter_cache(req_id: str, context: RequestContext) -> None:
    logger = context['logger']
    params_cache_lock = context['params_cache_lock']
    page_params_cache = context['page_params_cache']
    current_ai_studio_model_id = context['current_ai_studio_model_id']
    model_actually_switched = context['model_actually_switched']

    async with params_cache_lock:
        cached_model_for_params = page_params_cache.get("last_known_model_id_for_params")
        if model_actually_switched or (current_ai_studio_model_id != cached_model_for_params):
            logger.info(f"[{req_id}] Model changed, parameter cache invalidated.")
            page_params_cache.clear()
            page_params_cache["last_known_model_id_for_params"] = current_ai_studio_model_id
