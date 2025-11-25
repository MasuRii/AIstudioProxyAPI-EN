import asyncio
import json
import time
import random
from typing import Any, AsyncGenerator, Callable
from asyncio import Event

from playwright.async_api import Page as AsyncPage

from models import ClientDisconnectedError, ChatCompletionRequest
from config import CHAT_COMPLETION_ID_PREFIX
from config.global_state import GlobalState
from .utils import use_stream_response, calculate_usage_stats, generate_sse_chunk, generate_sse_stop_chunk
from .common_utils import random_id
from api_utils.utils_ext.usage_tracker import increment_profile_usage


async def gen_sse_from_aux_stream(
    req_id: str,
    request: ChatCompletionRequest,
    model_name_for_stream: str,
    check_client_disconnected: Callable,
    event_to_set: Event,
    timeout: float,
    page: AsyncPage = None,
) -> AsyncGenerator[str, None]:
    """辅助流队列 -> OpenAI 兼容 SSE 生成器。

    产出增量、tool_calls、最终 usage 与 [DONE]。
    """
    import server
    from server import logger

    last_reason_pos = 0
    last_body_pos = 0
    chat_completion_id = f"{CHAT_COMPLETION_ID_PREFIX}{req_id}-{int(time.time())}-{random.randint(100, 999)}"
    created_timestamp = int(time.time())

    full_reasoning_content = ""
    full_body_content = ""
    data_receiving = False
    is_response_finalized = False  # [FIX] State flag to enforce one-response rule

    # [ID-01] Latch & Backfill State Variables
    has_started_body = False
    has_sent_reasoning = False

    try:
        async for raw_data in use_stream_response(req_id, timeout=timeout, page=page, check_client_disconnected=check_client_disconnected):
            # [FIX] Check state flag before processing
            if is_response_finalized:
                logger.warning(f"[{req_id}] ⚠️ Extraneous message received after response finalization. Ignoring.")
                continue

            if GlobalState.IS_QUOTA_EXCEEDED:
                logger.error(f"[{req_id}] ⛔ Quota exceeded detected during stream! Aborting.")
                yield generate_sse_chunk("\n\n[SYSTEM: Quota Exceeded. Stopping.]", req_id, model_name_for_stream)
                yield generate_sse_stop_chunk(req_id, model_name_for_stream)
                if not event_to_set.is_set():
                    event_to_set.set()
                break

            data_receiving = True

            try:
                check_client_disconnected(f"Stream generator loop ({req_id}): ")
            except ClientDisconnectedError:
                logger.info(f"[{req_id}] Client disconnected, terminating stream generation")
                if data_receiving and not event_to_set.is_set():
                    logger.info(f"[{req_id}] Client disconnected during data reception, setting done signal immediately")
                    event_to_set.set()
                break

            if isinstance(raw_data, str):
                try:
                    data = json.loads(raw_data)
                except json.JSONDecodeError:
                    logger.warning(f"[{req_id}] Failed to parse stream data JSON: {raw_data}")
                    continue
            elif isinstance(raw_data, dict):
                data = raw_data
            else:
                logger.warning(f"[{req_id}] Unknown stream data type: {type(raw_data)}")
                continue

            if not isinstance(data, dict):
                logger.warning(f"[{req_id}] Data is not a dict: {data}")
                continue

            reason = data.get("reason", "")
            body = data.get("body", "")
            done = data.get("done", False)
            function = data.get("function", [])

            if reason:
                full_reasoning_content = reason
            if body:
                full_body_content = body

            # [ID-01] The Latch: Reasoning Handling
            if len(reason) > last_reason_pos:
                reason_delta = reason[last_reason_pos:]
                if has_started_body:
                    # Drop reasoning if body has started
                    logger.debug(f"[{req_id}] 🛑 Latch active: Dropping late reasoning: {len(reason_delta)} chars")
                else:
                    output = {
                        "id": chat_completion_id,
                        "object": "chat.completion.chunk",
                        "model": model_name_for_stream,
                        "created": created_timestamp,
                        "choices": [{
                            "index": 0,
                            "delta": {
                                "role": "assistant",
                                "content": None,
                                "reasoning_content": reason_delta,
                            },
                            "finish_reason": None,
                            "native_finish_reason": None,
                        }],
                    }
                    has_sent_reasoning = True
                    logger.debug(f"[{req_id}] 🧠 Sent reasoning content: {len(reason_delta)} chars")
                    yield f"data: {json.dumps(output, ensure_ascii=False, separators=(',', ':'))}\n\n"
                
                last_reason_pos = len(reason)

            # [ID-01] The Latch: Body Handling
            if len(body) > last_body_pos:
                body_delta = body[last_body_pos:]
                has_started_body = True
                
                # Yield content immediately
                output = {
                    "id": chat_completion_id,
                    "object": "chat.completion.chunk",
                    "model": model_name_for_stream,
                    "created": created_timestamp,
                    "choices": [{
                        "index": 0,
                        "delta": {
                            "role": "assistant",
                            "content": body_delta,
                        },
                        "finish_reason": None,
                        "native_finish_reason": None,
                    }],
                }
                last_body_pos = len(body)
                logger.debug(f"[{req_id}] 📝 Sent body content: {len(body_delta)} chars")
                yield f"data: {json.dumps(output, ensure_ascii=False, separators=(',', ':'))}\n\n"

            if done:
                # [ID-02] The Backfill: Synthetic Content if no body
                if not has_started_body:
                    fallback_text = "\n\n*(Model finished thinking but generated no code/text output.)*"
                    logger.info(f"[{req_id}] ⚠️ Backfill triggered: Sending synthetic content.")
                    
                    output = {
                        "id": chat_completion_id,
                        "object": "chat.completion.chunk",
                        "model": model_name_for_stream,
                        "created": created_timestamp,
                        "choices": [{
                            "index": 0,
                            "delta": {
                                "role": "assistant",
                                "content": fallback_text,
                            },
                            "finish_reason": None,
                            "native_finish_reason": None,
                        }],
                    }
                    yield f"data: {json.dumps(output, ensure_ascii=False, separators=(',', ':'))}\n\n"
                    full_body_content += fallback_text
                    # Mark as started so we don't do it again if logic changes
                    has_started_body = True

                # Handle Tool Calls or Stop
                if function and len(function) > 0:
                    tool_calls_list = []
                    for func_idx, function_call_data in enumerate(function):
                        tool_calls_list.append({
                            "id": f"call_{random_id()}",
                            "index": func_idx,
                            "type": "function",
                            "function": {
                                "name": function_call_data["name"],
                                "arguments": json.dumps(function_call_data["params"]),
                            },
                        })
                    delta_content = {"role": "assistant", "content": None, "tool_calls": tool_calls_list}
                    choice_item = {
                        "index": 0,
                        "delta": delta_content,
                        "finish_reason": "tool_calls",
                        "native_finish_reason": "tool_calls",
                    }
                else:
                    choice_item = {
                        "index": 0,
                        "delta": {"role": "assistant"},
                        "finish_reason": "stop",
                        "native_finish_reason": "stop",
                    }

                output = {
                    "id": chat_completion_id,
                    "object": "chat.completion.chunk",
                    "model": model_name_for_stream,
                    "created": created_timestamp,
                    "choices": [choice_item],
                }
                yield f"data: {json.dumps(output, ensure_ascii=False, separators=(',', ':'))}\n\n"
                
                # [FIX] Mark response as finalized
                is_response_finalized = True
                logger.info(f"[{req_id}] ✅ Response finalized. Subsequent messages will be ignored.")

    except ClientDisconnectedError:
        logger.info(f"[{req_id}] Client disconnection detected in stream generator")
        if data_receiving and not event_to_set.is_set():
            logger.info(f"[{req_id}] Setting done signal immediately in client disconnect handler")
            event_to_set.set()
    except Exception as e:
        logger.error(f"[{req_id}] Error in stream generator processing: {e}", exc_info=True)
        try:
            error_chunk = {
                "id": chat_completion_id,
                "object": "chat.completion.chunk",
                "model": model_name_for_stream,
                "created": created_timestamp,
                "choices": [{
                    "index": 0,
                    "delta": {"role": "assistant", "content": f"\n\n[错误: {str(e)}]"},
                    "finish_reason": "stop",
                    "native_finish_reason": "stop",
                }],
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
            logger.info(f"[{req_id}] Calculated token usage stats: {usage_stats}")
            
            # Update global token count
            total_tokens = usage_stats.get("total_tokens", 0)
            GlobalState.increment_token_count(total_tokens)

            # Update profile usage stats
            # [FIX] Re-import server to ensure availability in finally block
            import server
            if hasattr(server, 'current_auth_profile_path') and server.current_auth_profile_path:
                await increment_profile_usage(server.current_auth_profile_path, total_tokens)

            final_chunk = {
                "id": chat_completion_id,
                "object": "chat.completion.chunk",
                "model": model_name_for_stream,
                "created": created_timestamp,
                "choices": [{
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop",
                    "native_finish_reason": "stop",
                }],
                "usage": usage_stats,
            }
            yield f"data: {json.dumps(final_chunk, ensure_ascii=False, separators=(',', ':'))}\n\n"
        except Exception as usage_err:
            logger.error(f"[{req_id}] Error calculating or sending usage stats: {usage_err}")
        try:
            logger.info(f"[{req_id}] Stream generator completed, sending [DONE] marker")
            yield "data: [DONE]\n\n"
        except Exception as done_err:
            logger.error(f"[{req_id}] Error sending [DONE] marker: {done_err}")
        if not event_to_set.is_set():
            event_to_set.set()
            logger.info(f"[{req_id}] Stream generator completion event set")


async def gen_sse_from_playwright(
    page: AsyncPage,
    logger: Any,
    req_id: str,
    model_name_for_stream: str,
    request: ChatCompletionRequest,
    check_client_disconnected: Callable,
    completion_event: Event,
    prompt_length: int,
    timeout: float,
) -> AsyncGenerator[str, None]:
    """Playwright 最终响应 -> OpenAI 兼容 SSE 生成器。"""
    # Reuse already-imported helpers from utils to avoid repeated imports
    from models import ClientDisconnectedError
    from browser_utils.page_controller import PageController

    data_receiving = False
    try:
        page_controller = PageController(page, logger, req_id)
        final_content = await page_controller.get_response(check_client_disconnected, prompt_length=prompt_length, timeout=timeout)
        data_receiving = True
        lines = final_content.split('\n')
        for line_idx, line in enumerate(lines):
            try:
                check_client_disconnected(f"Playwright stream generator loop ({req_id}): ")
            except ClientDisconnectedError:
                logger.info(f"[{req_id}] Client disconnection detected in Playwright stream generator")
                if data_receiving and not completion_event.is_set():
                    logger.info(f"[{req_id}] Client disconnected during Playwright data reception, setting done signal immediately")
                    completion_event.set()
                break
            if line:
                chunk_size = 5
                for i in range(0, len(line), chunk_size):
                    chunk = line[i:i+chunk_size]
                    yield generate_sse_chunk(chunk, req_id, model_name_for_stream)
                    await asyncio.sleep(0.03)
            if line_idx < len(lines) - 1:
                yield generate_sse_chunk('\n', req_id, model_name_for_stream)
                await asyncio.sleep(0.01)
        usage_stats = calculate_usage_stats(
            [msg.model_dump() for msg in request.messages], final_content, "",
        )
        logger.info(f"[{req_id}] Playwright non-stream calculated token usage stats: {usage_stats}")
        
        # Update global token count
        total_tokens = usage_stats.get("total_tokens", 0)
        GlobalState.increment_token_count(total_tokens)

        # Update profile usage stats
        import server
        if hasattr(server, 'current_auth_profile_path') and server.current_auth_profile_path:
            await increment_profile_usage(server.current_auth_profile_path, total_tokens)

        yield generate_sse_stop_chunk(req_id, model_name_for_stream, "stop", usage_stats)
    except ClientDisconnectedError:
        logger.info(f"[{req_id}] Client disconnection detected in Playwright stream generator")
        if data_receiving and not completion_event.is_set():
            logger.info(f"[{req_id}] Setting done signal immediately in Playwright client disconnect handler")
            completion_event.set()
    except Exception as e:
        logger.error(f"[{req_id}] Error in Playwright stream generator processing: {e}", exc_info=True)
        try:
            yield generate_sse_chunk(f"\n\n[Error: {str(e)}]", req_id, model_name_for_stream)
            yield generate_sse_stop_chunk(req_id, model_name_for_stream)
        except Exception:
            pass
    finally:
        if not completion_event.is_set():
            completion_event.set()
            logger.info(f"[{req_id}] Playwright stream generator completion event set")