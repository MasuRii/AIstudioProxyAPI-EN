"""
Request Processor Module
Contains core request processing logic
"""

import asyncio
import json
import os
import shutil
from asyncio import Event, Future
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from playwright.async_api import (
    Error as PlaywrightAsyncError,
)
from playwright.async_api import (
    Locator,
)
from playwright.async_api import (
    Page as AsyncPage,
)

# --- browser_utils Module Imports ---
from browser_utils import (
    save_error_snapshot,
)
from browser_utils.page_controller import PageController

# --- Configuration Module Imports ---
from config import (
    MODEL_NAME,
    RESPONSE_COMPLETION_TIMEOUT,
    SUBMIT_BUTTON_SELECTOR,
    UPLOAD_FILES_DIR,
    get_environment_variable,
)
from config.global_state import GlobalState

# --- logging_utils Module Imports ---
from logging_utils import log_context

# --- models Module Imports ---
from models import (
    ChatCompletionRequest,
    ClientDisconnectedError,
    QuotaExceededError,
    QuotaExceededRetry,
)

from .client_connection import (
    check_client_connection as _check_client_connection,
)
from .client_connection import (
    setup_disconnect_monitoring as _setup_disconnect_monitoring,
)
from .common_utils import random_id as _random_id
from .context_init import initialize_request_context as _init_request_context
from .context_types import RequestContext
from .error_utils import (
    bad_request,
    client_disconnected,
    server_error,
    upstream_error,
)
from .model_switching import (
    analyze_model_requirements as ms_analyze,
)
from .model_switching import (
    handle_model_switching as ms_switch,
)
from .model_switching import (
    handle_parameter_cache as ms_param_cache,
)
from .page_response import locate_response_elements
from .response_generators import (
    gen_sse_from_aux_stream,
    gen_sse_from_playwright,
    resilient_stream_generator,
)
from .response_payloads import build_chat_completion_response_json

# --- api_utils Module Imports ---
from .utils import (
    maybe_execute_tools,
    prepare_combined_prompt,
)
from .utils_ext.files import collect_and_validate_attachments
from .utils_ext.stream import use_stream_response
from .utils_ext.tokens import calculate_usage_stats
from .utils_ext.usage_tracker import increment_profile_usage
from .utils_ext.validation import validate_chat_request

_initialize_request_context = _init_request_context


# Wrapper function for backward compatibility
async def _test_client_connection(req_id: str, http_request) -> bool:
    """Test if client is still connected - wrapper for _check_client_connection"""
    return await _check_client_connection(req_id, http_request)


async def _analyze_model_requirements(
    req_id: str, context: RequestContext, request: ChatCompletionRequest
) -> RequestContext:
    """Proxy to model_switching.analyze_model_requirements"""
    return await ms_analyze(req_id, context, request.model, MODEL_NAME)


async def _validate_page_status(
    req_id: str, context: RequestContext, check_client_disconnected: Callable
) -> None:
    """Validate page status"""
    page = context["page"]
    is_page_ready = context["is_page_ready"]

    if not page or page.is_closed() or not is_page_ready:
        raise HTTPException(
            status_code=503,
            detail=f"[{req_id}] AI Studio page lost or not ready.",
            headers={"Retry-After": "30"},
        )

    check_client_disconnected("Initial Page Check")


async def _handle_model_switching(
    req_id: str, context: RequestContext, check_client_disconnected: Callable
) -> RequestContext:
    """Proxy to model_switching.handle_model_switching"""
    return await ms_switch(req_id, context)


async def _handle_model_switch_failure(
    req_id: str, page: AsyncPage, model_id_to_use: str, model_before_switch: str, logger
) -> None:
    """Handle model switch failure"""
    from api_utils.server_state import state

    logger.warning(f"[{req_id}] Failed to switch model to {model_id_to_use}.")
    # Attempt to restore global state
    state.current_ai_studio_model_id = model_before_switch

    raise HTTPException(
        status_code=422,
        detail=f"[{req_id}] Failed to switch to model '{model_id_to_use}'. Ensure model is available.",
    )


async def _handle_parameter_cache(req_id: str, context: RequestContext) -> None:
    """Proxy to model_switching.handle_parameter_cache"""
    await ms_param_cache(req_id, context)


async def _prepare_and_validate_request(
    req_id: str,
    request: ChatCompletionRequest,
    check_client_disconnected: Callable,
) -> Tuple[str, List[str]]:
    """Prepare and validate request, return (combined prompt, attachment path list)."""
    try:
        validate_chat_request(request.messages, req_id)
    except ValueError as e:
        raise bad_request(req_id, f"Invalid request: {e}")

    prepared_prompt, attachments_list = prepare_combined_prompt(
        request.messages,
        req_id,
        getattr(request, "tools", None),
        getattr(request, "tool_choice", None),
    )
    # Active function execution based on tools/tool_choice (supports per-request MCP endpoints)
    try:
        # Inject mcp_endpoint into utils.maybe_execute_tools registration logic
        if hasattr(request, "mcp_endpoint") and request.mcp_endpoint:
            from .tools_registry import register_runtime_tools

            register_runtime_tools(
                getattr(request, "tools", None), request.mcp_endpoint
            )
        tool_exec_results = await maybe_execute_tools(
            request.messages, request.tools, getattr(request, "tool_choice", None)
        )
    except asyncio.CancelledError:
        raise
    except Exception:
        tool_exec_results = None

    check_client_disconnected("After Prompt Prep")
    # Inline results at the end of the prompt for submission together
    if tool_exec_results:
        try:
            for res in tool_exec_results:
                name = res.get("name")
                args = res.get("arguments")
                result_str = res.get("result")
                prepared_prompt += f"\n---\nTool Execution: {name}\nArguments:\n{args}\nResult:\n{result_str}\n"
        except Exception:
            pass

    # Process and validate attachments
    # Acceptance criteria: Only accept data:/file:/absolute paths provided by current request
    final_attachments = collect_and_validate_attachments(
        request, req_id, attachments_list
    )

    return prepared_prompt, final_attachments


async def _handle_response_processing(
    req_id: str,
    request: ChatCompletionRequest,
    page: Optional[AsyncPage],
    context: RequestContext,
    result_future: Future,
    submit_button_locator: Locator,
    check_client_disconnected: Callable,
    prompt_length: int,
    timeout: float,
    silence_threshold: float = 60.0,
) -> Optional[Tuple[Event, Locator, Callable]]:
    """Handle response generation"""
    stream_port = get_environment_variable("STREAM_PORT")
    use_stream = stream_port != "0"

    if use_stream:
        return await _handle_auxiliary_stream_response(
            req_id,
            request,
            context,
            result_future,
            submit_button_locator,
            check_client_disconnected,
            timeout=timeout,
            silence_threshold=silence_threshold,
        )
    else:
        return await _handle_playwright_response(
            req_id,
            request,
            page,
            context,
            result_future,
            submit_button_locator,
            check_client_disconnected,
            prompt_length,
            timeout=timeout,
        )


async def _handle_auxiliary_stream_response(
    req_id: str,
    request: ChatCompletionRequest,
    context: RequestContext,
    result_future: Future[Union[StreamingResponse, JSONResponse]],
    submit_button_locator: Locator,
    check_client_disconnected: Callable,
    timeout: float,
    silence_threshold: float = 60.0,
) -> Optional[Tuple[Event, Locator, Callable]]:
    """Auxiliary stream response processing path"""
    from api_utils.server_state import state

    logger = state.logger

    is_streaming = request.stream
    current_ai_studio_model_id = context.get("current_ai_studio_model_id")

    if is_streaming:
        try:
            completion_event = Event()
            page = context["page"]

            # [RESILIENT-WRAPPER] Wrap the stream generator with retry/rotation logic
            def aux_stream_factory(event_to_signal: Event):
                return gen_sse_from_aux_stream(
                    req_id,
                    request,
                    current_ai_studio_model_id or MODEL_NAME,
                    check_client_disconnected,
                    event_to_signal,
                    timeout=timeout,
                    silence_threshold=silence_threshold,
                    page=page,  # <--- CRITICAL: This enables the auto-scroll logic in stream.py
                )

            resilient_gen = resilient_stream_generator(
                req_id,
                current_ai_studio_model_id or MODEL_NAME,
                aux_stream_factory,
                completion_event,
            )

            if not result_future.done():
                result_future.set_result(
                    StreamingResponse(resilient_gen, media_type="text/event-stream")
                )
            else:
                if not completion_event.is_set():
                    completion_event.set()

            return (
                completion_event,
                submit_button_locator,
                check_client_disconnected,
            )

        except asyncio.CancelledError:
            if completion_event and not completion_event.is_set():
                completion_event.set()
            raise
        except Exception as e:
            logger.error(
                f"[{req_id}] Error getting stream data from queue: {e}", exc_info=True
            )
            raise
    else:
        # Non-streaming logic using auxiliary stream
        content = None
        reasoning_content = None
        functions = None
        final_data_from_aux_stream = None

        page = context["page"]
        # Disable silence detection for non-streaming requests to prevent premature timeouts
        async for raw_data in use_stream_response(
            req_id,
            page=page,
            check_client_disconnected=check_client_disconnected,
            timeout=timeout,
            silence_threshold=silence_threshold,
            enable_silence_detection=False,
        ):
            check_client_disconnected(f"Non-streaming aux stream - loop ({req_id}): ")

            if isinstance(raw_data, str):
                try:
                    data = json.loads(raw_data)
                except json.JSONDecodeError:
                    logger.warning(
                        f"[{req_id}] Failed to parse non-stream data JSON: {raw_data}"
                    )
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

        if (
            final_data_from_aux_stream
            and final_data_from_aux_stream.get("reason") == "internal_timeout"
        ):
            logger.error(
                f"[{req_id}] Non-stream request failed via aux stream: Internal Timeout"
            )
            raise HTTPException(
                status_code=502,
                detail=f"[{req_id}] Aux stream processing error (Internal Timeout)",
            )

        if (
            final_data_from_aux_stream
            and final_data_from_aux_stream.get("done") is True
            and content is None
        ):
            logger.error(
                f"[{req_id}] Non-stream request completed via aux stream but no content provided"
            )
            raise HTTPException(
                status_code=502,
                detail=f"[{req_id}] Aux stream completed but no content provided",
            )

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
            tool_calls_list: List[Dict[str, Any]] = []
            for func_idx, function_call_data in enumerate(functions):
                tool_calls_list.append(
                    {
                        "id": f"call_{_random_id()}",
                        "index": func_idx,
                        "type": "function",
                        "function": {
                            "name": function_call_data["name"],
                            "arguments": json.dumps(function_call_data["params"]),
                        },
                    }
                )
            message_payload["tool_calls"] = tool_calls_list
            finish_reason_val = "tool_calls"
            message_payload["content"] = None

        usage_stats = calculate_usage_stats(
            [msg.model_dump() for msg in request.messages],
            consolidated_content or "",
            "",
        )

        total_tokens = usage_stats.get("total_tokens", 0)
        GlobalState.increment_token_count(total_tokens)

        from api_utils.server_state import state

        if (
            hasattr(state, "current_auth_profile_path")
            and state.current_auth_profile_path
        ):
            await increment_profile_usage(state.current_auth_profile_path, total_tokens)

        response_payload = build_chat_completion_response_json(
            req_id,
            model_name_for_json,
            message_payload,
            finish_reason_val,
            usage_stats,
            system_fingerprint="camoufox-proxy",
            seed=request.seed
            if hasattr(request, "seed") and request.seed is not None
            else 0,
            response_format=(
                request.response_format
                if hasattr(request, "response_format")
                and isinstance(request.response_format, dict)
                else {}
            ),
        )

        if not result_future.done():
            response_json_str = json.dumps(response_payload, ensure_ascii=False)
            if len(response_json_str) > 10000:  # 10KB threshold
                logger.info(
                    f"[{req_id}] Large response detected ({len(response_json_str)} chars), using efficient chunking"
                )

                async def generate_json_chunks():
                    chunk_size = 8192  # 8KB chunks
                    for i in range(0, len(response_json_str), chunk_size):
                        chunk = response_json_str[i : i + chunk_size]
                        yield chunk
                        await asyncio.sleep(0.01)

                result_future.set_result(
                    StreamingResponse(
                        generate_json_chunks(), media_type="application/json"
                    )
                )
            else:
                result_future.set_result(JSONResponse(content=response_payload))
        return response_payload


async def _handle_playwright_response(
    req_id: str,
    request: ChatCompletionRequest,
    page: AsyncPage,
    context: dict,
    result_future: Future,
    submit_button_locator: Locator,
    check_client_disconnected: Callable,
    prompt_length: int,
    timeout: float,
) -> Optional[Tuple[Event, Locator, Callable]]:
    """Handle response using Playwright - Enhanced version with integrity verification"""
    from api_utils.server_state import state

    logger = state.logger

    is_streaming = request.stream
    current_ai_studio_model_id = context.get("current_ai_studio_model_id")

    await locate_response_elements(page, req_id, logger, check_client_disconnected)
    check_client_disconnected("After Response Element Located: ")

    if is_streaming:
        completion_event = Event()

        def playwright_stream_factory(event_to_signal: Event):
            return gen_sse_from_playwright(
                page,
                logger,
                req_id,
                current_ai_studio_model_id or MODEL_NAME,
                request,
                check_client_disconnected,
                event_to_signal,
                prompt_length=prompt_length,
                timeout=timeout,
            )

        resilient_gen = resilient_stream_generator(
            req_id,
            current_ai_studio_model_id or MODEL_NAME,
            playwright_stream_factory,
            completion_event,
        )

        if not result_future.done():
            result_future.set_result(
                StreamingResponse(resilient_gen, media_type="text/event-stream")
            )

        return completion_event, submit_button_locator, check_client_disconnected
    else:
        page_controller = PageController(page, logger, req_id)
        response_data = await page_controller.get_response_with_integrity_check(
            check_client_disconnected, prompt_length, timeout=timeout
        )

        final_content = response_data.get("content", "")
        reasoning_content = response_data.get("reasoning_content", "")
        recovery_method = response_data.get("recovery_method", "direct")

        if recovery_method == "integrity_verification":
            logger.info(
                f"[{req_id}] Successfully recovered content via integrity verification ({len(final_content)} chars)"
            )
            await save_error_snapshot(
                f"integrity_recovery_success_{req_id}",
                extra_context={
                    "content_length": len(final_content),
                    "reasoning_length": len(reasoning_content),
                    "recovery_trigger": response_data.get("trigger_reason", ""),
                },
            )
        elif recovery_method == "direct":
            logger.info(
                f"[{req_id}] Successfully retrieved content directly ({len(final_content)} chars)"
            )

        consolidated_content = ""
        if reasoning_content and reasoning_content.strip():
            consolidated_content += reasoning_content.strip()
        if final_content and final_content.strip():
            if consolidated_content:
                consolidated_content += "\n\n"
            consolidated_content += final_content.strip()

        usage_stats = calculate_usage_stats(
            [msg.model_dump() for msg in request.messages],
            consolidated_content,
            "",
        )
        logger.info(f"[{req_id}] Token usage stats: {usage_stats}")

        total_tokens = usage_stats.get("total_tokens", 0)
        GlobalState.increment_token_count(total_tokens)

        from api_utils.server_state import state

        if (
            hasattr(state, "current_auth_profile_path")
            and state.current_auth_profile_path
        ):
            await increment_profile_usage(state.current_auth_profile_path, total_tokens)

        model_name_for_json = current_ai_studio_model_id or MODEL_NAME
        message_payload = {"role": "assistant", "content": consolidated_content}
        finish_reason_val = "stop"

        response_payload = build_chat_completion_response_json(
            req_id,
            model_name_for_json,
            message_payload,
            finish_reason_val,
            usage_stats,
            system_fingerprint="camoufox-proxy",
            seed=request.seed
            if hasattr(request, "seed") and request.seed is not None
            else 0,
            response_format=(
                request.response_format
                if hasattr(request, "response_format")
                and isinstance(request.response_format, dict)
                else {}
            ),
        )

        if not result_future.done():
            response_json_str = json.dumps(response_payload, ensure_ascii=False)
            if len(response_json_str) > 10000:

                async def generate_json_chunks():
                    chunk_size = 8192
                    for i in range(0, len(response_json_str), chunk_size):
                        yield response_json_str[i : i + chunk_size]
                        await asyncio.sleep(0.01)

                result_future.set_result(
                    StreamingResponse(
                        generate_json_chunks(), media_type="application/json"
                    )
                )
            else:
                result_future.set_result(JSONResponse(content=response_payload))

        return response_payload


async def _cleanup_request_resources(
    req_id: str,
    disconnect_check_task: Optional[asyncio.Task],
    completion_event: Optional[Event],
    result_future: Future,
    is_streaming: bool,
) -> None:
    """Cleanup request resources"""
    from api_utils.server_state import state

    logger = state.logger

    if disconnect_check_task and not disconnect_check_task.done():
        disconnect_check_task.cancel()
        try:
            await disconnect_check_task
        except asyncio.CancelledError:
            pass

    # Clean up upload subdirectory
    try:
        req_dir = os.path.join(UPLOAD_FILES_DIR, req_id)
        if os.path.isdir(req_dir):
            shutil.rmtree(req_dir, ignore_errors=True)
            logger.debug(f"Cleaned up request upload directory: {req_dir}")
    except asyncio.CancelledError:
        raise
    except Exception as clean_err:
        logger.warning(f"[{req_id}] Failed to clean up upload directory: {clean_err}")

    if (
        is_streaming
        and completion_event
        and not completion_event.is_set()
        and (result_future.done() and result_future.exception() is not None)
    ):
        logger.warning(
            f"[{req_id}] Stream request exception, ensuring completion event is set."
        )
        completion_event.set()


async def process_request_with_retry(
    req_id: str,
    request: ChatCompletionRequest,
    http_request: Request,
    result_future: Future,
) -> Optional[Tuple[Event, Locator, Callable[[str], bool]]]:
    """Wrapper around _process_request_refactored with retry mechanism for quota"""
    from api_utils.server_state import state

    logger = state.logger

    max_retries = 3
    attempt = 0
    while attempt < max_retries:
        attempt += 1
        try:
            return await _process_request_refactored(
                req_id, request, http_request, result_future
            )
        except QuotaExceededRetry:
            logger.warning(
                f"[{req_id}] Quota wall hit (attempt {attempt}/{max_retries}). Waiting for rotation..."
            )
            await GlobalState.rotation_complete_event.wait()
            logger.info(f"[{req_id}] Rotation complete. Retrying request.")
            continue
    logger.error(f"[{req_id}] Request failed after {max_retries} retries due to quota.")
    raise Exception(f"Request failed after {max_retries} retries due to quota issues.")


async def process_request(
    req_id: str,
    request: ChatCompletionRequest,
    http_request: Request,
    result_future: Future,
) -> Optional[Tuple[Event, Locator, Callable[[str], bool]]]:
    """Main entry point for request processing"""
    return await process_request_with_retry(
        req_id, request, http_request, result_future
    )


async def _process_request_refactored(
    req_id: str,
    request: ChatCompletionRequest,
    http_request: Request,
    result_future: Future,
) -> Optional[Tuple[Event, Locator, Callable[[str], bool]]]:
    """Core Request Processing Function - Refactored Version"""
    from api_utils.server_state import state

    logger = state.logger

    # 0. Check Auth Rotation Lock
    if not GlobalState.AUTH_ROTATION_LOCK.is_set():
        logger.info(f"[{req_id}] Request held: Waiting for auth rotation...")
        await GlobalState.AUTH_ROTATION_LOCK.wait()
        logger.info(f"[{req_id}] ▶️ Resuming after Auth Rotation.")

    # [GR-03] Pre-Flight Graceful Rotation Check
    if GlobalState.NEEDS_ROTATION:
        logger.info(f"[{req_id}] 🔄 Graceful Rotation Pending. Initiating rotation...")
        from api_utils.server_state import state

        current_model_id = state.current_ai_studio_model_id
        from browser_utils.auth_rotation import perform_auth_rotation

        if await perform_auth_rotation(target_model_id=current_model_id):
            GlobalState.NEEDS_ROTATION = False
            logger.info(f"[{req_id}] ✅ Pre-flight rotation complete.")

    is_connected = await _test_client_connection(req_id, http_request)
    if not is_connected:
        logger.info(f"[{req_id}] Client disconnected before processing.")
        if not result_future.done():
            result_future.set_exception(
                HTTPException(status_code=499, detail="Client disconnected")
            )
        return None

    stream_port = get_environment_variable("STREAM_PORT")
    use_stream = stream_port != "0"
    if use_stream:
        try:
            from api_utils import clear_stream_queue

            await clear_stream_queue()
        except asyncio.CancelledError:
            raise
        except Exception as clear_err:
            logger.warning(f"[Stream] Error clearing queue: {clear_err}")

    context = await _initialize_request_context(req_id, request)
    context = await _analyze_model_requirements(req_id, context, request)

    (
        _,
        disconnect_check_task,
        check_client_disconnected,
    ) = await _setup_disconnect_monitoring(req_id, http_request, result_future)

    page = context["page"]
    submit_button_locator = page.locator(SUBMIT_BUTTON_SELECTOR) if page else None
    completion_event = None

    try:
        await _validate_page_status(req_id, context, check_client_disconnected)
        if page is None:
            raise server_error(req_id, "Page is None")

        page_controller = PageController(page, context["logger"], req_id)
        await _handle_model_switching(req_id, context, check_client_disconnected)
        await _handle_parameter_cache(req_id, context)

        prepared_prompt, attachments_list = await _prepare_and_validate_request(
            req_id, request, check_client_disconnected
        )

        request_params = request.model_dump(exclude_none=True)
        if "stop" in request.model_fields_set and request.stop is None:
            request_params["stop"] = None

        with log_context("Adjusting Parameters", context["logger"], silent=True):
            await page_controller.adjust_parameters(
                request_params,
                context["page_params_cache"],
                context["params_cache_lock"],
                context["model_id_to_use"],
                context["parsed_model_list"],
                check_client_disconnected,
            )

        check_client_disconnected("Final check before submitting prompt")

        with log_context("Execution", context["logger"], silent=True):
            await page_controller.submit_prompt(
                prepared_prompt, attachments_list, check_client_disconnected
            )

        # Sync page reference if changed
        if page_controller.page != page:
            logger.info(f"[{req_id}] Page updated, syncing references...")
            page = page_controller.page
            context["page"] = page
            submit_button_locator = page.locator(SUBMIT_BUTTON_SELECTOR)

        calc_timeout = 5.0 + (len(prepared_prompt) / 1000.0)
        config_timeout = RESPONSE_COMPLETION_TIMEOUT / 1000.0
        dynamic_timeout = max(calc_timeout, config_timeout)
        dynamic_silence_threshold = max(60.0, dynamic_timeout / 2.0)

        logger.info(
            f"[{req_id}] Dynamic timeout: {dynamic_timeout:.2f}s, silence threshold: {dynamic_silence_threshold:.2f}s"
        )

        response_result = await _handle_response_processing(
            req_id,
            request,
            page,
            context,
            result_future,
            submit_button_locator,
            check_client_disconnected,
            len(prepared_prompt),
            timeout=dynamic_timeout,
            silence_threshold=dynamic_silence_threshold,
        )

        if response_result:
            if isinstance(response_result, dict):
                return response_result, submit_button_locator, check_client_disconnected
            if isinstance(response_result, tuple):
                completion_event, _, _ = response_result
                return (
                    completion_event,
                    submit_button_locator,
                    check_client_disconnected,
                )

        return completion_event, submit_button_locator, check_client_disconnected

    except ClientDisconnectedError as disco_err:
        logger.info(f"[{req_id}] Client disconnected: {disco_err}")
        if not result_future.done():
            result_future.set_exception(client_disconnected(req_id, "Disconnected"))
        return completion_event, submit_button_locator, check_client_disconnected
    except HTTPException as http_err:
        logger.warning(f"[{req_id}] HTTP exception: {http_err.status_code}")
        if not result_future.done():
            result_future.set_exception(http_err)
        return completion_event, submit_button_locator, check_client_disconnected
    except QuotaExceededError as quota_err:
        logger.warning(f"[{req_id}] Quota Exceeded: {quota_err}")
        if not GlobalState.IS_QUOTA_EXCEEDED:
            GlobalState.set_quota_exceeded(message=str(quota_err))
        raise quota_err
    except PlaywrightAsyncError as pw_err:
        logger.error(f"[{req_id}] Playwright error: {pw_err}")
        await save_error_snapshot(f"process_pw_error_{req_id}")
        if not result_future.done():
            result_future.set_exception(
                upstream_error(req_id, f"Interaction failed: {pw_err}")
            )
        return completion_event, submit_button_locator, check_client_disconnected
    except Exception as e:
        logger.exception(f"[{req_id}] Unexpected error")
        await save_error_snapshot(f"process_error_{req_id}")
        if not result_future.done():
            result_future.set_exception(server_error(req_id, str(e)))
        return completion_event, submit_button_locator, check_client_disconnected
    finally:
        await _cleanup_request_resources(
            req_id,
            disconnect_check_task,
            completion_event,
            result_future,
            request.stream or False,
        )
