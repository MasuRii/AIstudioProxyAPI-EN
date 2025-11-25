"""
Request Processor Module
Contains core request processing logic
"""

import asyncio
import json
import os
import random
import time
from typing import Optional, Tuple, Callable, AsyncGenerator, List, Any
from asyncio import Event, Future

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from playwright.async_api import Page as AsyncPage, Locator, Error as PlaywrightAsyncError, expect as expect_async

# --- Configuration Module Imports ---
from config import (
    MODEL_NAME,
    SUBMIT_BUTTON_SELECTOR,
)
from config import ONLY_COLLECT_CURRENT_USER_ATTACHMENTS, UPLOAD_FILES_DIR
from config.global_state import GlobalState

# --- models Module Imports ---
from models import ChatCompletionRequest, ClientDisconnectedError, QuotaExceededError

# --- browser_utils Module Imports ---
from browser_utils import (
    switch_ai_studio_model,
    save_error_snapshot
)

# --- api_utils Module Imports ---
from .utils import (
    validate_chat_request,
    prepare_combined_prompt,
    use_stream_response,
    calculate_usage_stats,
    maybe_execute_tools,
)
from api_utils.utils_ext.usage_tracker import increment_profile_usage
from browser_utils.page_controller import PageController
from .context_types import RequestContext
from .response_generators import gen_sse_from_aux_stream, gen_sse_from_playwright
from .response_payloads import build_chat_completion_response_json
from .model_switching import analyze_model_requirements as ms_analyze, handle_model_switching as ms_switch, handle_parameter_cache as ms_param_cache
from .page_response import locate_response_elements

from .common_utils import random_id as _random_id
from .client_connection import (
    test_client_connection as _test_client_connection,
    setup_disconnect_monitoring as _setup_disconnect_monitoring,
)
from .context_init import initialize_request_context as _init_request_context

_initialize_request_context = _init_request_context

# Error helpers
from .error_utils import (
    bad_request,
    client_disconnected,
    upstream_error,
    server_error,
)


async def _analyze_model_requirements(req_id: str, context: RequestContext, request: ChatCompletionRequest) -> RequestContext:
    """Proxy to model_switching.analyze_model_requirements"""
    return await ms_analyze(req_id, context, request.model, MODEL_NAME)


# Use imported implementation directly

# Use imported implementation directly


async def _validate_page_status(req_id: str, context: RequestContext, check_client_disconnected: Callable) -> None:
    """Validate page status"""
    page = context['page']
    is_page_ready = context['is_page_ready']
    
    if not page or page.is_closed() or not is_page_ready:
        raise HTTPException(status_code=503, detail=f"[{req_id}] AI Studio page missing or not ready.", headers={"Retry-After": "30"})
    
    check_client_disconnected("Initial Page Check")


async def _handle_model_switching(req_id: str, context: RequestContext, check_client_disconnected: Callable) -> RequestContext:
    """Proxy to model_switching.handle_model_switching"""
    return await ms_switch(req_id, context)


async def _handle_model_switch_failure(req_id: str, page: AsyncPage, model_id_to_use: str, model_before_switch: str, logger) -> None:
    """Handle model switch failure"""
    import server
    
    logger.warning(f"[{req_id}] Failed to switch model to {model_id_to_use}.")
    # Attempt to restore global state
    server.current_ai_studio_model_id = model_before_switch
    
    raise HTTPException(
        status_code=422,
        detail=f"[{req_id}] Failed to switch to model '{model_id_to_use}'. Ensure model is available."
    )


async def _handle_parameter_cache(req_id: str, context: RequestContext) -> None:
    """Proxy to model_switching.handle_parameter_cache"""
    await ms_param_cache(req_id, context)


async def _prepare_and_validate_request(
    req_id: str,
    request: ChatCompletionRequest,
    check_client_disconnected: Callable,
) -> Tuple[str, List[Optional[str]]]:
    """Prepare and validate request, return (combined prompt, image path list)."""
    try:
        validate_chat_request(request.messages, req_id)
    except ValueError as e:
        raise bad_request(req_id, f"Invalid request: {e}")
    
    prepared_prompt, images_list = prepare_combined_prompt(request.messages, req_id, getattr(request, 'tools', None), getattr(request, 'tool_choice', None))
    # Active function execution based on tools/tool_choice (supports per-request MCP endpoints)
    try:
        # Inject mcp_endpoint into utils.maybe_execute_tools registration logic
        if hasattr(request, 'mcp_endpoint') and request.mcp_endpoint:
            from .tools_registry import register_runtime_tools
            register_runtime_tools(getattr(request, 'tools', None), request.mcp_endpoint)
        tool_exec_results = await maybe_execute_tools(request.messages, request.tools, getattr(request, 'tool_choice', None))
    except Exception:
        tool_exec_results = None
    check_client_disconnected("After Prompt Prep")
    # Inline results at the end of the prompt for submission together
    if tool_exec_results:
        try:
            for res in tool_exec_results:
                name = res.get('name')
                args = res.get('arguments')
                result_str = res.get('result')
                prepared_prompt += f"\n---\nTool Execution: {name}\nArguments:\n{args}\nResult:\n{result_str}\n"
        except Exception:
            pass
    # If configured to only collect current user attachments, filter here
    try:
        if ONLY_COLLECT_CURRENT_USER_ATTACHMENTS:
            latest_user = None
            for msg in reversed(request.messages or []):
                if getattr(msg, 'role', None) == 'user':
                    latest_user = msg
                    break
            if latest_user is not None:
                filtered: List[str] = []
                from api_utils.utils import extract_data_url_to_local
                from urllib.parse import urlparse, unquote
                import os
                # Collect data:/file:/absolute paths (existing) on this user message
                content = getattr(latest_user, 'content', None)
                # Extract uniformly from messages attachment fields
                for key in ('attachments', 'images', 'files', 'media'):
                    arr = getattr(latest_user, key, None)
                    if not isinstance(arr, list):
                        continue
                    for it in arr:
                        url_value = None
                        if isinstance(it, str):
                            url_value = it
                        elif isinstance(it, dict):
                            url_value = it.get('url') or it.get('path')
                        url_value = (url_value or '').strip()
                        if not url_value:
                            continue
                        if url_value.startswith('data:'):
                            fp = extract_data_url_to_local(url_value)
                            if fp:
                                filtered.append(fp)
                        elif url_value.startswith('file:'):
                            parsed = urlparse(url_value)
                            lp = unquote(parsed.path)
                            if os.path.exists(lp):
                                filtered.append(lp)
                        elif os.path.isabs(url_value) and os.path.exists(url_value):
                            filtered.append(url_value)
                images_list = filtered
    except Exception:
        pass

    return prepared_prompt, images_list

async def _handle_response_processing(
    req_id: str,
    request: ChatCompletionRequest,
    page: AsyncPage,
    context: RequestContext,
    result_future: Future,
    submit_button_locator: Locator,
    check_client_disconnected: Callable,
    prompt_length: int,
    timeout: float,
) -> Optional[Tuple[Event, Locator, Callable]]:
    """Handle response generation"""
    from server import logger
    
    is_streaming = request.stream
    current_ai_studio_model_id = context.get('current_ai_studio_model_id')
    
    # Check if auxiliary stream is used
    from config import get_environment_variable
    stream_port = get_environment_variable('STREAM_PORT')
    use_stream = stream_port != '0'
    
    if use_stream:
        return await _handle_auxiliary_stream_response(req_id, request, context, result_future, submit_button_locator, check_client_disconnected, timeout=timeout)
    else:
        return await _handle_playwright_response(req_id, request, page, context, result_future, submit_button_locator, check_client_disconnected, prompt_length, timeout=timeout)


async def _handle_auxiliary_stream_response(
    req_id: str,
    request: ChatCompletionRequest,
    context: RequestContext,
    result_future: Future,
    submit_button_locator: Locator,
    check_client_disconnected: Callable,
    timeout: float,
) -> Optional[Tuple[Event, Locator, Callable]]:
    """Auxiliary stream response processing path"""
    from server import logger
    
    is_streaming = request.stream
    current_ai_studio_model_id = context.get('current_ai_studio_model_id')
    
    if is_streaming:
        try:
            completion_event = Event()
            page = context['page']
            
            # [FIXED] Removed duplicate call.
            # Ensure we use the one that passes 'page=page'
            stream_gen_func = gen_sse_from_aux_stream(
                req_id,
                request,
                current_ai_studio_model_id or MODEL_NAME,
                check_client_disconnected,
                completion_event,
                timeout=timeout,
                page=page,  # <--- CRITICAL: This enables the auto-scroll logic in stream.py
            )
            
            if not result_future.done():
                result_future.set_result(StreamingResponse(stream_gen_func, media_type="text/event-stream"))
            else:
                if not completion_event.is_set():
                    completion_event.set()
            
            return completion_event, submit_button_locator, check_client_disconnected

        except Exception as e:
            logger.error(f"[{req_id}] Error getting stream data from queue: {e}", exc_info=True)
            # Fallback to non-streaming if stream setup fails...
            page = context['page']
            async for raw_data in use_stream_response(req_id, page=page, check_client_disconnected=check_client_disconnected):
                if completion_event and not completion_event.is_set():
                    completion_event.set()
            raise

    else:  # Non-streaming logic
        content = None
        reasoning_content = None
        functions = None
        final_data_from_aux_stream = None

        # Pass page here too for non-streaming requests so they don't time out
        page = context['page']
        async for raw_data in use_stream_response(req_id, page=page, check_client_disconnected=check_client_disconnected, timeout=timeout):
            check_client_disconnected(f"Non-streaming aux stream - loop ({req_id}): ")
            
            if isinstance(raw_data, str):
                try:
                    data = json.loads(raw_data)
                except json.JSONDecodeError:
                    logger.warning(f"[{req_id}] Failed to parse non-stream data JSON: {raw_data}")
                    continue
            elif isinstance(raw_data, dict):
                data = raw_data
            else:
                continue
            
            if not isinstance(data, dict):
                continue
                
            final_data_from_aux_stream = data
            if data.get("done"):
                content = data.get("body")
                reasoning_content = data.get("reason")
                functions = data.get("function")
                break
        
        # ... (Rest of non-streaming logic remains unchanged) ...
        if final_data_from_aux_stream and final_data_from_aux_stream.get("reason") == "internal_timeout":
            logger.error(f"[{req_id}] Non-stream request failed via aux stream: Internal Timeout")
            raise HTTPException(status_code=502, detail=f"[{req_id}] Aux stream processing error (Internal Timeout)")

        if final_data_from_aux_stream and final_data_from_aux_stream.get("done") is True and content is None:
             logger.error(f"[{req_id}] Non-stream request completed via aux stream but no content provided")
             raise HTTPException(status_code=502, detail=f"[{req_id}] Aux stream completed but no content provided")

        model_name_for_json = current_ai_studio_model_id or MODEL_NAME
        
        # Consolidate reasoning content with body content
        consolidated_content = ""
        if reasoning_content and reasoning_content.strip():
            consolidated_content += reasoning_content.strip()
        if content and content.strip():
            if consolidated_content:
                consolidated_content += "\n\n"
            consolidated_content += content.strip()
        
        message_payload = {"role": "assistant", "content": consolidated_content}
        finish_reason_val = "stop"

        if functions and len(functions) > 0:
            tool_calls_list = []
            for func_idx, function_call_data in enumerate(functions):
                tool_calls_list.append({
                    "id": f"call_{_random_id()}",
                    "index": func_idx,
                    "type": "function",
                    "function": {
                        "name": function_call_data["name"],
                        "arguments": json.dumps(function_call_data["params"]),
                    },
                })
            message_payload["tool_calls"] = tool_calls_list
            finish_reason_val = "tool_calls"
            message_payload["content"] = None

        usage_stats = calculate_usage_stats(
            [msg.model_dump() for msg in request.messages],
            consolidated_content or "",
            "",  # No separate reasoning content since it's consolidated
        )
        
        # Update global token count
        total_tokens = usage_stats.get("total_tokens", 0)
        GlobalState.increment_token_count(total_tokens)

        # Update profile usage stats
        import server
        if hasattr(server, 'current_auth_profile_path') and server.current_auth_profile_path:
            await increment_profile_usage(server.current_auth_profile_path, total_tokens)

        response_payload = build_chat_completion_response_json(
            req_id,
            model_name_for_json,
            message_payload,
            finish_reason_val,
            usage_stats,
            system_fingerprint="camoufox-proxy",
            seed=request.seed if hasattr(request, 'seed') else None,
            response_format=(request.response_format if hasattr(request, 'response_format') else None),
        )

        if not result_future.done():
            # Check if response is large and needs efficient chunking
            response_json_str = json.dumps(response_payload, ensure_ascii=False)
            if len(response_json_str) > 10000:  # 10KB threshold
                logger.info(f"[{req_id}] Large response detected ({len(response_json_str)} chars), using efficient chunking")
                
                async def generate_json_chunks():
                    chunk_size = 8192  # 8KB chunks
                    for i in range(0, len(response_json_str), chunk_size):
                        chunk = response_json_str[i:i + chunk_size]
                        yield chunk
                        await asyncio.sleep(0.01)  # Small delay to prevent overwhelming clients
                
                result_future.set_result(StreamingResponse(generate_json_chunks(), media_type="application/json"))
            else:
                result_future.set_result(JSONResponse(content=response_payload))
        return response_payload


async def _handle_playwright_response(req_id: str, request: ChatCompletionRequest, page: AsyncPage,
                                    context: dict, result_future: Future, submit_button_locator: Locator,
                                    check_client_disconnected: Callable, prompt_length: int, timeout: float) -> Optional[Tuple[Event, Locator, Callable]]:
    """Handle response using Playwright - Enhanced version, supports hybrid response and integrity verification"""
    from server import logger
    
    is_streaming = request.stream
    current_ai_studio_model_id = context.get('current_ai_studio_model_id')
    
    await locate_response_elements(page, req_id, logger, check_client_disconnected)

    check_client_disconnected("After Response Element Located: ")

    if is_streaming:
        completion_event = Event()
        stream_gen_func = gen_sse_from_playwright(
            page,
            logger,
            req_id,
            current_ai_studio_model_id or MODEL_NAME,
            request,
            check_client_disconnected,
            completion_event,
            prompt_length=prompt_length,
            timeout=timeout,
        )
        if not result_future.done():
            result_future.set_result(StreamingResponse(stream_gen_func, media_type="text/event-stream"))
        
        return completion_event, submit_button_locator, check_client_disconnected
    else:
        # Use enhanced PageController to get response (supports integrity verification)
        page_controller = PageController(page, logger, req_id)
        
        # Get response content (including integrity verification logic)
        response_data = await page_controller.get_response_with_integrity_check(
            check_client_disconnected,
            prompt_length,
            timeout=timeout
        )
        
        final_content = response_data.get("content", "")
        reasoning_content = response_data.get("reasoning_content", "")
        recovery_method = response_data.get("recovery_method", "direct")
        
        if recovery_method == "integrity_verification":
            logger.info(f"[{req_id}] Successfully recovered response content using integrity verification ({len(final_content)} chars)")
            # Save debug info
            await save_error_snapshot(
                f"integrity_recovery_success_{req_id}",
                extra_context={
                    "content_length": len(final_content),
                    "reasoning_length": len(reasoning_content),
                    "recovery_trigger": response_data.get("trigger_reason", "")
                }
            )
        elif recovery_method == "direct":
            logger.info(f"[{req_id}] Successfully retrieved response content directly ({len(final_content)} chars)")
        
        # Consolidate reasoning content with body content for usage stats
        consolidated_content_for_usage = ""
        if reasoning_content and reasoning_content.strip():
            consolidated_content_for_usage += reasoning_content.strip()
        if final_content and final_content.strip():
            if consolidated_content_for_usage:
                consolidated_content_for_usage += "\n\n"
            consolidated_content_for_usage += final_content.strip()
        
        # Calculate token usage stats (using consolidated content)
        usage_stats = calculate_usage_stats(
            [msg.model_dump() for msg in request.messages],
            consolidated_content_for_usage,
            ""  # No separate reasoning content since it's consolidated
        )
        logger.info(f"[{req_id}] Playwright non-stream token usage stats: {usage_stats}")
        
        # Update global token count
        total_tokens = usage_stats.get("total_tokens", 0)
        GlobalState.increment_token_count(total_tokens)

        # Update profile usage stats
        import server
        if hasattr(server, 'current_auth_profile_path') and server.current_auth_profile_path:
            await increment_profile_usage(server.current_auth_profile_path, total_tokens)

        # Use unified constructor to generate OpenAI compatible response
        model_name_for_json = current_ai_studio_model_id or MODEL_NAME
        
        # Consolidate reasoning content with body content
        consolidated_content = ""
        if reasoning_content and reasoning_content.strip():
            consolidated_content += reasoning_content.strip()
        if final_content and final_content.strip():
            if consolidated_content:
                consolidated_content += "\n\n"
            consolidated_content += final_content.strip()
        
        message_payload = {"role": "assistant", "content": consolidated_content}
        finish_reason_val = "stop"
        response_payload = build_chat_completion_response_json(
            req_id,
            model_name_for_json,
            message_payload,
            finish_reason_val,
            usage_stats,
            system_fingerprint="camoufox-proxy",
            seed=request.seed if hasattr(request, 'seed') else None,
            response_format=(request.response_format if hasattr(request, 'response_format') else None),
        )
        
        if not result_future.done():
            from server import logger
            logger.info(f"[{req_id}] [DEBUG] Setting non-stream result on future. Payload keys: {list(response_payload.keys())}")
            if "choices" in response_payload and len(response_payload["choices"]) > 0:
                 content_len = len(response_payload["choices"][0]["message"].get("content", "") or "")
                 logger.info(f"[{req_id}] [DEBUG] Payload content length: {content_len}")
             
            # Check if response is large and needs efficient chunking
            response_json_str = json.dumps(response_payload, ensure_ascii=False)
            if len(response_json_str) > 10000:  # 10KB threshold
                logger.info(f"[{req_id}] Large response detected ({len(response_json_str)} chars), using efficient chunking")
                
                async def generate_json_chunks():
                    chunk_size = 8192  # 8KB chunks
                    for i in range(0, len(response_json_str), chunk_size):
                        chunk = response_json_str[i:i + chunk_size]
                        yield chunk
                        await asyncio.sleep(0.01)  # Small delay to prevent overwhelming clients
                
                result_future.set_result(StreamingResponse(generate_json_chunks(), media_type="application/json"))
            else:
                result_future.set_result(JSONResponse(content=response_payload))
        else:
            from server import logger
            logger.warning(f"[{req_id}] [DEBUG] Could not set result, future already done/cancelled.")
        
        return response_payload


async def _cleanup_request_resources(req_id: str, disconnect_check_task: Optional[asyncio.Task],
                                   completion_event: Optional[Event], result_future: Future,
                                   is_streaming: bool) -> None:
    """Cleanup request resources"""
    from server import logger
    from config import UPLOAD_FILES_DIR
    import os, shutil
    
    if disconnect_check_task and not disconnect_check_task.done():
        disconnect_check_task.cancel()
        try:
            await disconnect_check_task
        except asyncio.CancelledError:
            pass
        except Exception as task_clean_err:
            logger.error(f"[{req_id}] Error during task cleanup: {task_clean_err}")
    
    logger.info(f"[{req_id}] Processing completed.")

    # Clean up upload subdirectory for this request to avoid disk accumulation
    try:
        req_dir = os.path.join(UPLOAD_FILES_DIR, req_id)
        if os.path.isdir(req_dir):
            shutil.rmtree(req_dir, ignore_errors=True)
            logger.info(f"[{req_id}] Cleaned up request upload directory: {req_dir}")
    except Exception as clean_err:
        logger.warning(f"[{req_id}] Failed to clean up upload directory: {clean_err}")
    
    if is_streaming and completion_event and not completion_event.is_set() and (result_future.done() and result_future.exception() is not None):
         logger.warning(f"[{req_id}] Stream request exception, ensuring completion event is set.")
         completion_event.set()


async def _process_request_refactored(
    req_id: str,
    request: ChatCompletionRequest,
    http_request: Request,
    result_future: Future
) -> Optional[Tuple[Event, Locator, Callable[[str], bool]]]:
    """Core Request Processing Function - Refactored Version"""

    # Optimize: Proactively check client connection status before starting any processing
    from server import logger
    from config import get_environment_variable

    # 0. Check Auth Rotation Lock
    if not GlobalState.AUTH_ROTATION_LOCK.is_set():
        logger.info(f"[{req_id}] [INFO] Request held: Waiting for auth rotation...")
        await GlobalState.AUTH_ROTATION_LOCK.wait()
        logger.info(f"[{req_id}] ▶️ Resuming after Auth Rotation.")

    # [GR-03] Pre-Flight Graceful Rotation Check
    # Handles edge case where limit was hit while server was idle
    if GlobalState.NEEDS_ROTATION:
        logger.info(f"[{req_id}] 🔄 Graceful Rotation Pending. Initiating rotation before processing request...")
        from browser_utils.auth_rotation import perform_auth_rotation
        if await perform_auth_rotation():
             GlobalState.NEEDS_ROTATION = False
             logger.info(f"[{req_id}] ✅ Pre-flight rotation complete.")

    is_connected = await _test_client_connection(req_id, http_request)
    if not is_connected:
        logger.info(f"[{req_id}] Client disconnection detected before core processing, exiting early to save resources")
        if not result_future.done():
            result_future.set_exception(HTTPException(status_code=499, detail=f"[{req_id}] Client disconnected before processing started"))
        return None

    stream_port = get_environment_variable('STREAM_PORT')
    use_stream = stream_port != '0'
    if use_stream:
        logger.info(f"[{req_id}] Clearing stream queue before request (preventing residual data)...")
        try:
            from api_utils import clear_stream_queue
            await clear_stream_queue()
            logger.info(f"[{req_id}] Stream queue cleared")
        except Exception as clear_err:
            logger.warning(f"[{req_id}] Error clearing stream queue: {clear_err}")

    context = await _initialize_request_context(req_id, request)
    context = await _analyze_model_requirements(req_id, context, request)
    
    client_disconnected_event, disconnect_check_task, check_client_disconnected = await _setup_disconnect_monitoring(
        req_id, http_request, result_future
    )
    
    page = context['page']
    submit_button_locator = page.locator(SUBMIT_BUTTON_SELECTOR) if page else None
    completion_event = None
    
    try:
        await _validate_page_status(req_id, context, check_client_disconnected)
        
        page_controller = PageController(page, context['logger'], req_id)

        await _handle_model_switching(req_id, context, check_client_disconnected)
        await _handle_parameter_cache(req_id, context)
        
        prepared_prompt,image_list = await _prepare_and_validate_request(req_id, request, check_client_disconnected)
        # Extra merge of top-level and message-level attachments/files (compatibility history) handled below; ensure path exists here
        try:
            import os
            valid_images = []
            for p in image_list:
                if isinstance(p, str) and p and os.path.isabs(p) and os.path.exists(p):
                    valid_images.append(p)
            if len(valid_images) != len(image_list):
                from server import logger
                logger.warning(f"[{req_id}] Filtered out non-existent attachment paths: {set(image_list) - set(valid_images)}")
            image_list = valid_images
        except Exception:
            pass
        # Compatibility: Merge top-level and message-level attachment fields into upload list (only data:/file:/absolute path)
        # Attachment source strategy: Only accept data:/file:/absolute paths explicitly provided by current request
        try:
            from api_utils.utils import extract_data_url_to_local
            from urllib.parse import urlparse, unquote
            import os
            # Top-level attachments
            top_level_atts = getattr(request, 'attachments', None)
            if isinstance(top_level_atts, list) and len(top_level_atts) > 0:
                for it in top_level_atts:
                    url_value = None
                    if isinstance(it, str):
                        url_value = it
                    elif isinstance(it, dict):
                        url_value = it.get('url') or it.get('path')
                    url_value = (url_value or '').strip()
                    if not url_value:
                        continue
                    if url_value.startswith('data:'):
                        fp = extract_data_url_to_local(url_value, req_id=req_id)
                        if fp:
                            image_list.append(fp)
                    elif url_value.startswith('file:'):
                        parsed = urlparse(url_value)
                        lp = unquote(parsed.path)
                        if os.path.exists(lp):
                            image_list.append(lp)
                    elif os.path.isabs(url_value) and os.path.exists(url_value):
                        image_list.append(url_value)
            # Message-level attachments/images/files/media (full collection, but only keep valid local/data)
            for msg in (request.messages or []):
                for key in ('attachments', 'images', 'files', 'media'):
                    arr = getattr(msg, key, None)
                    if not isinstance(arr, list):
                        continue
                    for it in arr:
                        url_value = None
                        if isinstance(it, str):
                            url_value = it
                        elif isinstance(it, dict):
                            url_value = it.get('url') or it.get('path')
                        url_value = (url_value or '').strip()
                        if not url_value:
                            continue
                        if url_value.startswith('data:'):
                            fp = extract_data_url_to_local(url_value, req_id=req_id)
                            if fp:
                                image_list.append(fp)
                        elif url_value.startswith('file:'):
                            parsed = urlparse(url_value)
                            lp = unquote(parsed.path)
                            if os.path.exists(lp):
                                image_list.append(lp)
                        elif os.path.isabs(url_value) and os.path.exists(url_value):
                            image_list.append(url_value)
        except Exception:
            pass

        # Use PageController to handle page interaction
        # Note: Chat history clearing has been moved to execute after queue processing lock release

        await page_controller.adjust_parameters(
            request.model_dump(exclude_none=True), # Use exclude_none=True to avoid passing None values
            context['page_params_cache'],
            context['params_cache_lock'],
            context['model_id_to_use'],
            context['parsed_model_list'],
            check_client_disconnected,
            request.stream
        )

        # Optimize: Check client connection again before submitting prompt to avoid unnecessary background requests
        check_client_disconnected("Final check before submitting prompt")

        await page_controller.submit_prompt(prepared_prompt,image_list, check_client_disconnected)
        
        # Refresh page reference because submit_prompt might update page during recovery
        if page_controller.page != page:
            context['logger'].info(f"[{req_id}] Page instance updated (Tab Recovery) detected, syncing references...")
            page = page_controller.page
            context['page'] = page
            submit_button_locator = page.locator(SUBMIT_BUTTON_SELECTOR)

        # DYNAMIC TIMEOUT: Calculate timeout based on prompt length
        # Formula: 5s base + 1s for every 1000 characters
        dynamic_timeout = 5.0 + (len(prepared_prompt) / 1000.0)
        logger.info(f"[{req_id}] Calculated dynamic TTFB timeout: {dynamic_timeout:.2f}s")

        # Response processing is still needed here as it determines if it's streaming or non-streaming, and sets future
        response_result = await _handle_response_processing(
            req_id, request, page, context, result_future, submit_button_locator, check_client_disconnected, len(prepared_prompt),
            timeout=dynamic_timeout
        )
        
        if response_result:
            # [FIX] Handle dictionary return (non-streaming payload)
            if isinstance(response_result, dict):
                # [STREAM-FIX] Explicitly check for Done signal in dictionary response
                if response_result.get("done") is True:
                     logger.info(f"[{req_id}] Dictionary DONE signal received in process_request. Treating as EOF.")
                return response_result, submit_button_locator, check_client_disconnected
            
            # Handle tuple return (streaming event/loc/checker)
            if isinstance(response_result, tuple):
                completion_event, _, _ = response_result
                return completion_event, submit_button_locator, check_client_disconnected

        return completion_event, submit_button_locator, check_client_disconnected
        
    except ClientDisconnectedError as disco_err:
        context['logger'].info(f"[{req_id}] Caught client disconnection signal: {disco_err}")
        if not result_future.done():
             result_future.set_exception(client_disconnected(req_id, "Client disconnected during processing."))
    except HTTPException as http_err:
        context['logger'].warning(f"[{req_id}] Caught HTTP exception: {http_err.status_code} - {http_err.detail}")
        if not result_future.done():
            result_future.set_exception(http_err)
    except QuotaExceededError as quota_err:
        context['logger'].warning(f"[{req_id}] 🚫 Quota Exceeded detected: {quota_err}. Waiting for Watchdog to rotate...")
        
        # [FINAL-01] Enforce Flag Ownership: Do NOT trigger rotation here.
        # We let the Watchdog handle the rotation to ensure the flag is managed correctly.
        # We simply ensure the flag is set (in case it wasn't already) and return 503.
        if not GlobalState.IS_QUOTA_EXCEEDED:
             GlobalState.set_quota_exceeded(message=str(quota_err))
            
        if not result_future.done():
            result_future.set_exception(
                HTTPException(
                    status_code=503,
                    detail=f"[{req_id}] Quota Exceeded. System is rotating credentials. Please retry in a few seconds.",
                    headers={"Retry-After": "5"}
                )
            )
    except PlaywrightAsyncError as pw_err:
        context['logger'].error(f"[{req_id}] Caught Playwright error: {pw_err}")
        await save_error_snapshot(f"process_playwright_error_{req_id}")
        if not result_future.done():
            result_future.set_exception(upstream_error(req_id, f"Playwright interaction failed: {pw_err}"))
    except Exception as e:
        context['logger'].exception(f"[{req_id}] Caught unexpected error")
        await save_error_snapshot(f"process_unexpected_error_{req_id}")
        if not result_future.done():
            result_future.set_exception(server_error(req_id, f"Unexpected server error: {e}"))
    finally:
        await _cleanup_request_resources(req_id, disconnect_check_task, completion_event, result_future, request.stream)
