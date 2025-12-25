import asyncio
import json
import logging
import random
import re
import time
from asyncio import Event
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, cast

from playwright.async_api import Page as AsyncPage

from api_utils.utils_ext.usage_tracker import increment_profile_usage
from config import CHAT_COMPLETION_ID_PREFIX
from config.global_state import GlobalState
from logging_utils import set_request_id
from models import (
    ChatCompletionRequest,
    ClientDisconnectedError,
    QuotaExceededError,
    QuotaExceededRetry,
)

from .common_utils import random_id
from .sse import generate_sse_chunk, generate_sse_stop_chunk
from .utils_ext.stream import use_stream_response
from .utils_ext.tokens import calculate_usage_stats

# Pattern to strip emulated function call text from body content
# This prevents "Request function call: ..." from being sent as text content
_FUNCTION_CALL_TEXT_PATTERN = re.compile(
    r"Request\s+function\s+call:\s*[^\n]+(?:\n(?:Parameters:\s*)?\s*\{[\s\S]*?\})?",
    re.IGNORECASE,
)

# Pattern to strip control characters like <ctrl46> from body content
# These appear in AI Studio's wire format as string delimiters
# Also captures trailing } or { that may follow control chars (JSON leak artifacts)
_CONTROL_CHAR_PATTERN = re.compile(r"<ctrl\d+>[\}\{]?")


def _clean_body_text(body: str) -> str:
    """Clean body text by removing control characters and JSON artifacts."""
    if not body:
        return body
    return _CONTROL_CHAR_PATTERN.sub("", body)


async def resilient_stream_generator(
    req_id: str,
    model_name: str,
    generator_factory: Callable[[Event], AsyncGenerator[str, None]],
    completion_event: Event,
) -> AsyncGenerator[str, None]:
    """
    Wraps a stream generator with resiliency logic.
    Handles QuotaExceededError by triggering auth rotation and retrying.
    """
    from api_utils.server_state import state

    logger = state.logger
    from browser_utils.auth_rotation import perform_auth_rotation

    max_retries = 3
    retry_count = 0

    inner_event = Event()

    try:
        while retry_count <= max_retries:
            try:
                if inner_event.is_set():
                    inner_event.clear()

                async for chunk in generator_factory(inner_event):
                    yield chunk

                return

            except (QuotaExceededError, QuotaExceededRetry) as e:
                retry_count += 1
                if retry_count > max_retries:
                    logger.error(
                        f"[{req_id}] Max retries ({max_retries}) exhausted for quota recovery."
                    )
                    yield f"data: {json.dumps({'error': 'Max retries exhausted for quota recovery.'}, ensure_ascii=False)}\n\n"
                    return

                logger.warning(
                    f"[{req_id}] Quota limit hit during stream: {str(e)}. Initiating rotation (Attempt {retry_count}/{max_retries})..."
                )
                yield f": processing auth rotation (attempt {retry_count})...\n\n"

                rotation_task = asyncio.create_task(
                    perform_auth_rotation(target_model_id=model_name)
                )

                rotation_start = time.time()
                while not rotation_task.done():
                    if time.time() - rotation_start > 120:
                        logger.error(f"[{req_id}] Rotation timed out.")
                        yield f"data: {json.dumps({'error': 'Auth rotation timed out.'}, ensure_ascii=False)}\n\n"
                        return

                    yield ": processing auth rotation...\n\n"
                    await asyncio.sleep(2)

                success = await rotation_task
                if success:
                    logger.info(
                        f"[{req_id}] Auth rotation successful. Retrying stream generation..."
                    )
                    yield ": auth rotation complete, retrying...\n\n"
                    continue
                else:
                    logger.error(f"[{req_id}] Auth rotation failed.")
                    yield f"data: {json.dumps({'error': 'Auth rotation failed.'}, ensure_ascii=False)}\n\n"
                    return
            except Exception:
                raise
    finally:
        if not completion_event.is_set():
            completion_event.set()
            logger.info(f"[{req_id}] Resilient stream completion event set")


async def gen_sse_from_aux_stream(
    req_id: str,
    request: ChatCompletionRequest,
    model_name_for_stream: str,
    check_client_disconnected: Callable[[str], bool],
    event_to_set: Event,
    timeout: float,
    silence_threshold: float = 60.0,
    page: Optional[AsyncPage] = None,
    stream_state: Optional[Dict[str, Any]] = None,
) -> AsyncGenerator[str, None]:
    """Auxiliary stream queue -> OpenAI compatible SSE generator."""
    logger = logging.getLogger("AIStudioProxyServer")
    set_request_id(req_id)

    last_reason_pos = 0
    last_body_pos = 0
    chat_completion_id = f"{CHAT_COMPLETION_ID_PREFIX}{req_id}-{int(time.time())}-{random.randint(100, 999)}"
    created_timestamp = int(time.time())

    full_reasoning_content = ""
    full_body_content = ""
    data_receiving = False
    is_response_finalized = False
    finish_reason = "stop"

    has_started_body = False

    try:
        async for raw_data in use_stream_response(
            req_id,
            timeout=timeout,
            silence_threshold=silence_threshold,
            page=page,
            check_client_disconnected=check_client_disconnected,
            enable_silence_detection=True,
        ):
            data_receiving = True

            if (
                GlobalState.CURRENT_STREAM_REQ_ID
                and GlobalState.CURRENT_STREAM_REQ_ID != req_id
            ):
                logger.warning(f"[{req_id}] 🧟 Zombie Stream Detected! Terminating.")
                break

            if GlobalState.QUOTA_EXCEEDED_EVENT.is_set():
                raise QuotaExceededRetry("Quota exceeded detected mid-stream.")

            if is_response_finalized:
                logger.warning(
                    f"[{req_id}] ⚠️ Extraneous message received after response finalization. Ignoring."
                )
                continue

            # Holding Pattern for Recovery
            if GlobalState.IS_RECOVERING:
                logger.info(
                    f"[{req_id}] ⏸️ System in Recovery Mode. Holding stream open..."
                )
                recovery_wait_start = time.time()
                while GlobalState.IS_RECOVERING:
                    if time.time() - recovery_wait_start > 120.0:
                        logger.error(f"[{req_id}] ❌ Recovery Timed Out. Aborting.")
                        yield generate_sse_chunk(
                            "\n\n[SYSTEM: Service Recovery Failed. Please retry.]",
                            req_id,
                            model_name_for_stream,
                        )
                        yield generate_sse_stop_chunk(req_id, model_name_for_stream)
                        break
                    yield ": heartbeat\n\n"
                    await asyncio.sleep(1.0)

                if GlobalState.IS_RECOVERING:
                    break
                logger.info(f"[{req_id}] ▶️ Recovery Complete. Resuming stream.")

            if GlobalState.IS_QUOTA_EXCEEDED and not GlobalState.IS_RECOVERING:
                logger.warning(
                    f"[{req_id}] ⚠️ Quota exceeded detected. Waiting for recovery initiation..."
                )
                await asyncio.sleep(1)
                if GlobalState.IS_RECOVERING:
                    continue
                logger.warning(
                    f"[{req_id}] ⛔ Quota exceeded, waiting for worker to pick up signal..."
                )
                await asyncio.sleep(2)
                continue

            try:
                check_client_disconnected(f"Stream generator loop ({req_id}): ")
            except ClientDisconnectedError:
                logger.info(
                    f"[{req_id}] Client disconnected, terminating stream generation"
                )
                if data_receiving and not event_to_set.is_set():
                    event_to_set.set()
                break

            data: Any
            if isinstance(raw_data, str):
                try:
                    data = json.loads(raw_data)
                except json.JSONDecodeError:
                    logger.warning(
                        f"[{req_id}] Failed to parse stream data JSON: {raw_data}"
                    )
                    continue
            elif isinstance(raw_data, dict):
                data = cast(Dict[str, Any], raw_data)
            else:
                continue

            if not isinstance(data, dict):
                continue

            typed_data: Dict[str, Any] = cast(Dict[str, Any], data)
            reason = str(typed_data.get("reason", ""))
            body = _clean_body_text(str(typed_data.get("body", "")))
            done = bool(typed_data.get("done", False))
            function = cast(List[Any], typed_data.get("function", []))

            if reason:
                full_reasoning_content = reason
            if body:
                full_body_content = body

            # The Latch: Reasoning Handling
            if len(reason) > last_reason_pos:
                reason_delta = reason[last_reason_pos:]
                if not has_started_body:
                    output = {
                        "id": chat_completion_id,
                        "object": "chat.completion.chunk",
                        "model": model_name_for_stream,
                        "created": created_timestamp,
                        "choices": [
                            {
                                "index": 0,
                                "delta": {
                                    "role": "assistant",
                                    "content": None,
                                    "reasoning_content": reason_delta,
                                },
                                "finish_reason": None,
                            }
                        ],
                    }
                    yield f"data: {json.dumps(output, ensure_ascii=False, separators=(',', ':'))}\n\n"
                last_reason_pos = len(reason)

            # The Latch: Body Handling
            # ALWAYS strip "Request function call:..." text from body
            # This prevents emulated FC text from appearing as content to clients
            # even when function call detection fails (race condition protection)
            original_body = body
            if body:
                body = _FUNCTION_CALL_TEXT_PATTERN.sub("", body).strip()
                if body != original_body:
                    full_body_content = body
                    # If we stripped FC text but function is empty, try parsing from the original
                    if not function:
                        from api_utils.utils_ext.function_call_response_parser import (
                            parse_emulated_function_calls_static,
                        )

                        parsed_fc = parse_emulated_function_calls_static(original_body)
                        if parsed_fc:
                            function = parsed_fc
                            # Demoted from INFO to DEBUG - this is normal fallback behavior
                            # when model outputs text format instead of native FC
                            logger.debug(
                                f"[{req_id}] Recovered function calls from emulated text"
                            )

            if len(body) > last_body_pos:
                body_delta = body[last_body_pos:]
                # Only stream body content if there's actual content after stripping
                if body_delta.strip():
                    has_started_body = True
                    output = {
                        "id": chat_completion_id,
                        "object": "chat.completion.chunk",
                        "model": model_name_for_stream,
                        "created": created_timestamp,
                        "choices": [
                            {
                                "index": 0,
                                "delta": {
                                    "role": "assistant",
                                    "content": body_delta,
                                },
                                "finish_reason": None,
                            }
                        ],
                    }
                    yield f"data: {json.dumps(output, ensure_ascii=False, separators=(',', ':'))}\n\n"
                last_body_pos = len(body)

            if done:
                is_recovering = GlobalState.IS_RECOVERING
                is_quota_exceeded = GlobalState.IS_QUOTA_EXCEEDED

                if (
                    done
                    and not has_started_body
                    and not is_recovering
                    and not is_quota_exceeded
                ):
                    try:
                        from browser_utils.operations import check_quota_limit

                        if page:
                            await check_quota_limit(page, req_id)
                    except Exception:
                        pass
                    await asyncio.sleep(2.0)
                    is_quota_exceeded = GlobalState.IS_QUOTA_EXCEEDED
                    is_recovering = GlobalState.IS_RECOVERING

                if (
                    not has_started_body
                    and not is_recovering
                    and not is_quota_exceeded
                    and not function
                ):
                    # Only show synthetic message when there's truly no content AND no function calls
                    # In native FC mode, empty body with function calls is expected
                    fallback_text = (
                        "\n\n*(Model finished thinking but generated no output.)*"
                    )
                    output = {
                        "id": chat_completion_id,
                        "object": "chat.completion.chunk",
                        "model": model_name_for_stream,
                        "created": created_timestamp,
                        "choices": [
                            {
                                "index": 0,
                                "delta": {
                                    "role": "assistant",
                                    "content": fallback_text,
                                },
                                "finish_reason": None,
                            }
                        ],
                    }
                    yield f"data: {json.dumps(output, ensure_ascii=False, separators=(',', ':'))}\n\n"
                    full_body_content += fallback_text
                    has_started_body = True
                elif is_recovering or is_quota_exceeded:
                    while GlobalState.IS_QUOTA_EXCEEDED or GlobalState.IS_RECOVERING:
                        yield ": heartbeat\n\n"
                        await asyncio.sleep(1.0)

                if function:
                    finish_reason = "tool_calls"
                    tool_calls_list = []
                    for func_idx, function_call_data in enumerate(function):
                        if isinstance(function_call_data, dict):
                            tool_calls_list.append(
                                {
                                    "id": f"call_{random_id()}",
                                    "index": func_idx,
                                    "type": "function",
                                    "function": {
                                        "name": function_call_data.get("name", ""),
                                        "arguments": json.dumps(
                                            function_call_data.get("params", {})
                                        ),
                                    },
                                }
                            )
                    choice_item = {
                        "index": 0,
                        "delta": {
                            "tool_calls": tool_calls_list,
                        },
                        "finish_reason": None,
                    }
                else:
                    finish_reason = "stop"
                    choice_item = {
                        "index": 0,
                        "delta": {},
                        "finish_reason": None,
                    }

                output = {
                    "id": chat_completion_id,
                    "object": "chat.completion.chunk",
                    "model": model_name_for_stream,
                    "created": created_timestamp,
                    "choices": [choice_item],
                }
                yield f"data: {json.dumps(output, ensure_ascii=False, separators=(',', ':'))}\n\n"
                is_response_finalized = True
                break

    except (QuotaExceededError, QuotaExceededRetry):
        raise
    except ClientDisconnectedError:
        logger.info(f"[{req_id}] Client disconnected in stream generator")
        if data_receiving and not event_to_set.is_set():
            event_to_set.set()
    except asyncio.CancelledError:
        if not event_to_set.is_set():
            event_to_set.set()
        raise
    except Exception as e:
        logger.error(f"[{req_id}] Error in stream generator: {e}", exc_info=True)
        try:
            error_chunk = {
                "id": chat_completion_id,
                "object": "chat.completion.chunk",
                "model": model_name_for_stream,
                "created": created_timestamp,
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "role": "assistant",
                            "content": f"\n\n[Error: {str(e)}]",
                        },
                        "finish_reason": "stop",
                    }
                ],
            }
            yield f"data: {json.dumps(error_chunk, ensure_ascii=False, separators=(',', ':'))}\n\n"
        except Exception:
            pass
    finally:
        try:
            usage_stats = calculate_usage_stats(
                [msg.model_dump() for msg in request.messages],
                full_body_content,
                full_reasoning_content,
            )
            total_tokens = usage_stats.get("total_tokens", 0)
            GlobalState.increment_token_count(total_tokens)
            from api_utils.server_state import state

            if (
                hasattr(state, "current_auth_profile_path")
                and state.current_auth_profile_path
            ):
                await increment_profile_usage(
                    state.current_auth_profile_path, total_tokens
                )

            final_chunk = {
                "id": chat_completion_id,
                "object": "chat.completion.chunk",
                "model": model_name_for_stream,
                "created": created_timestamp,
                "choices": [{"index": 0, "delta": {}, "finish_reason": finish_reason}],
                "usage": usage_stats,
            }
            yield f"data: {json.dumps(final_chunk, ensure_ascii=False, separators=(',', ':'))}\n\n"
        except Exception as usage_err:
            logger.error(f"[{req_id}] Error sending usage stats: {usage_err}")

        yield "data: [DONE]\n\n"
        if not event_to_set.is_set():
            event_to_set.set()

        if stream_state is not None:
            stream_state["has_content"] = bool(
                full_body_content or full_reasoning_content
            )


async def gen_sse_from_playwright(
    page: AsyncPage,
    logger: logging.Logger,
    req_id: str,
    model_name_for_stream: str,
    request: ChatCompletionRequest,
    check_client_disconnected: Callable[[str], bool],
    completion_event: Event,
    prompt_length: int,
    timeout: float,
) -> AsyncGenerator[str, None]:
    """Playwright response -> OpenAI compatible SSE generator."""
    from browser_utils.page_controller import PageController
    from models import ClientDisconnectedError

    set_request_id(req_id)
    data_receiving = False
    try:
        page_controller = PageController(page, logger, req_id)
        # Use get_response_with_function_calls which handles both content and functions
        response_data = await page_controller.get_response_with_function_calls(
            check_client_disconnected, prompt_length=prompt_length, timeout=timeout
        )
        final_content = response_data.get("content", "")
        function_calls = response_data.get("function_calls", [])

        data_receiving = True
        lines = final_content.split("\n")
        for line_idx, line in enumerate(lines):
            try:
                check_client_disconnected(
                    f"Playwright stream generator loop ({req_id}): "
                )
            except ClientDisconnectedError:
                if data_receiving and not completion_event.is_set():
                    completion_event.set()
                break
            if line:
                chunk_size = 5
                for i in range(0, len(line), chunk_size):
                    yield generate_sse_chunk(
                        line[i : i + chunk_size], req_id, model_name_for_stream
                    )
                    await asyncio.sleep(0.03)
            if line_idx < len(lines) - 1:
                yield generate_sse_chunk("\n", req_id, model_name_for_stream)
                await asyncio.sleep(0.01)

        usage_stats = calculate_usage_stats(
            [msg.model_dump() for msg in request.messages], final_content, ""
        )
        total_tokens = usage_stats.get("total_tokens", 0)
        GlobalState.increment_token_count(total_tokens)
        from api_utils.server_state import state

        if (
            hasattr(state, "current_auth_profile_path")
            and state.current_auth_profile_path
        ):
            await increment_profile_usage(state.current_auth_profile_path, total_tokens)

        if function_calls:
            from api_utils.utils_ext.function_calling_orchestrator import (
                get_function_calling_orchestrator,
            )

            orchestrator = get_function_calling_orchestrator()
            tool_calls_deltas = orchestrator.format_streaming_tool_calls(function_calls)
            for delta in tool_calls_deltas:
                chunk = {
                    "id": f"chatcmpl-{req_id}",
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": model_name_for_stream,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"tool_calls": [delta]},
                            "finish_reason": None,
                        }
                    ],
                }
                yield f"data: {json.dumps(chunk, ensure_ascii=False, separators=(',', ':'))}\n\n"

            yield generate_sse_stop_chunk(
                req_id, model_name_for_stream, "tool_calls", usage_stats
            )
        else:
            yield generate_sse_stop_chunk(
                req_id, model_name_for_stream, "stop", usage_stats
            )
    except (QuotaExceededError, QuotaExceededRetry):
        raise
    except ClientDisconnectedError:
        if data_receiving and not completion_event.is_set():
            completion_event.set()
    except asyncio.CancelledError:
        if not completion_event.is_set():
            completion_event.set()
        raise
    except Exception as e:
        logger.error(
            f"[{req_id}] Error in Playwright stream generator: {e}", exc_info=True
        )
        try:
            yield generate_sse_chunk(
                f"\n\n[Error: {str(e)}]", req_id, model_name_for_stream
            )
            yield generate_sse_stop_chunk(req_id, model_name_for_stream)
        except Exception:
            pass
    finally:
        if not completion_event.is_set():
            completion_event.set()
