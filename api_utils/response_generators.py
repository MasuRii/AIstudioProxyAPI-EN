import asyncio
import json
import logging
import random
import time
from asyncio import Event
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, cast

from playwright.async_api import Page as AsyncPage

from models import ClientDisconnectedError, ChatCompletionRequest, QuotaExceededRetry, QuotaExceededError
from config import CHAT_COMPLETION_ID_PREFIX
from config.global_state import GlobalState
from .common_utils import random_id
from .sse import generate_sse_chunk, generate_sse_stop_chunk
from .utils_ext.stream import use_stream_response
from .utils_ext.tokens import calculate_usage_stats
from api_utils.utils_ext.usage_tracker import increment_profile_usage

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
    import json
    from server import logger
    from browser_utils.auth_rotation import perform_auth_rotation
    
    max_retries = 3
    retry_count = 0
    
    # Create a dummy event for the inner generator to control/signal
    # We manage the real completion_event ourselves in the finally block
    inner_event = Event()
    
    try:
        while retry_count <= max_retries:
            try:
                # Clear inner event for each attempt
                if inner_event.is_set():
                    inner_event.clear()
                
                async for chunk in generator_factory(inner_event):
                    yield chunk
                
                # If we get here, the stream finished normally
                return
                
            except (QuotaExceededError, QuotaExceededRetry) as e:
                retry_count += 1
                if retry_count > max_retries:
                    logger.error(f"[{req_id}] Max retries ({max_retries}) exhausted for quota recovery.")
                    yield f"data: {json.dumps({'error': 'Max retries exhausted for quota recovery.'}, ensure_ascii=False)}\n\n"
                    return

                logger.warning(f"[{req_id}] Quota limit hit during stream: {str(e)}. Initiating rotation (Attempt {retry_count}/{max_retries})...")
                
                # Yield keep-alive
                yield f": processing auth rotation (attempt {retry_count})...\n\n"
                
                # Trigger Rotation
                rotation_task = asyncio.create_task(perform_auth_rotation(target_model_id=model_name))
                
                # Wait for rotation while yielding heartbeats
                rotation_start = time.time()
                while not rotation_task.done():
                    if time.time() - rotation_start > 120: # 120s timeout for rotation
                        logger.error(f"[{req_id}] Rotation timed out.")
                        yield f"data: {json.dumps({'error': 'Auth rotation timed out.'}, ensure_ascii=False)}\n\n"
                        return
                        
                    yield ": processing auth rotation...\n\n"
                    await asyncio.sleep(2)
                
                success = await rotation_task
                
                if success:
                    logger.info(f"[{req_id}] Auth rotation successful. Retrying stream generation...")
                    yield f": auth rotation complete, retrying...\n\n"
                    continue # Retry loop
                else:
                    logger.error(f"[{req_id}] Auth rotation failed.")
                    yield f"data: {json.dumps({'error': 'Auth rotation failed.'}, ensure_ascii=False)}\n\n"
                    return
            except Exception:
                # Re-raise other exceptions to be handled by the caller/FastAPI
                raise
    finally:
        # Ensure completion event is set when we are truly done
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
    page: AsyncPage = None,
) -> AsyncGenerator[str, None]:
    """辅助流队列 -> OpenAI 兼容 SSE 生成器。

    产出增量、tool_calls、最终 usage 与 [DONE]。

    Args:
        stream_state: 可选的状态字典，用于向调用者报告流状态。
                      如果提供，将设置 'has_content' 键表示是否收到内容。
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

    loop_count = 0

    try:
        # [FIX] Enable silence detection for streaming requests to prevent stuck connections
        async for raw_data in use_stream_response(req_id, timeout=timeout, silence_threshold=silence_threshold, page=page, check_client_disconnected=check_client_disconnected, enable_silence_detection=True):
            # [CONCURRENCY-FIX] Zombie Kill Switch
            # If the global active request ID has changed, this generator is a zombie. Die immediately.
            if GlobalState.CURRENT_STREAM_REQ_ID and GlobalState.CURRENT_STREAM_REQ_ID != req_id:
                logger.warning(f"[{req_id}] 🧟 Zombie Stream Detected! Current Global ID: {GlobalState.CURRENT_STREAM_REQ_ID}. Terminating.")
                break

            if GlobalState.QUOTA_EXCEEDED_EVENT.is_set():
                raise QuotaExceededRetry("Quota exceeded detected mid-stream.")

            # [FIX] Check state flag before processing
            if is_response_finalized:
                logger.warning(f"[{req_id}] ⚠️ Extraneous message received after response finalization. Ignoring.")
                continue

            # [ID-02] Holding Pattern for Recovery
            if GlobalState.IS_RECOVERING:
                logger.info(f"[{req_id}] ⏸️ System in Recovery Mode. Holding stream open...")
                
                # Wait for recovery signal loop with heartbeats
                recovery_wait_start = time.time()
                recovery_wait_timeout = 120.0
                
                while GlobalState.IS_RECOVERING:
                    if time.time() - recovery_wait_start > recovery_wait_timeout:
                        logger.error(f"[{req_id}] ❌ Recovery Timed Out (120s). Aborting.")
                        yield generate_sse_chunk("\n\n[SYSTEM: Service Recovery Failed. Please retry.]", req_id, model_name_for_stream)
                        yield generate_sse_stop_chunk(req_id, model_name_for_stream)
                        break
                    
                    # [FIX-KEEPALIVE] Send heartbeat to keep client connection alive
                    yield ": heartbeat\n\n"
                    await asyncio.sleep(1.0)
                
                if GlobalState.IS_RECOVERING: # Timeout break
                    break
                
                logger.info(f"[{req_id}] ▶️ Recovery Complete. Resuming stream.")
                # [ID-03] Trigger Browser Resubmit Logic handled by loop
                try:
                     await asyncio.wait_for(GlobalState.RECOVERY_EVENT.wait(), timeout=120.0)
                     logger.info(f"[{req_id}] ▶️ Recovery Complete. Resuming stream.")
                     
                     # [ID-03] Trigger Browser Resubmit Logic
                     # We need to tell the worker (via some mechanism) to resubmit the prompt.
                     # Since we are in the generator, we rely on `use_stream_response` to handle the actual
                     # re-entry into the browser logic, OR we signal it here.
                     # For now, we just continue, assuming the underlying `use_stream_response`
                     # loop will pick up the new data flow after rotation.
                except asyncio.TimeoutError:
                     logger.error(f"[{req_id}] ❌ Recovery Timed Out (120s). Aborting.")
                     yield generate_sse_chunk("\n\n[SYSTEM: Service Recovery Failed. Please retry.]", req_id, model_name_for_stream)
                     yield generate_sse_stop_chunk(req_id, model_name_for_stream)
                     break

            if GlobalState.IS_QUOTA_EXCEEDED and not GlobalState.IS_RECOVERING:
                 # If Quota is exceeded but Recovery hasn't started yet, we should wait a moment
                 # to see if the Queue Worker initiates recovery.
                 logger.warning(f"[{req_id}] ⚠️ Quota exceeded detected. Waiting for recovery initiation...")
                 await asyncio.sleep(1)
                 if GlobalState.IS_RECOVERING:
                     continue # Loop back to hit the holding pattern above
                 
                 # [FIX-HOLD] Even if recovery hasn't started yet (race condition), we should NOT abort.
                 # We should signal the worker (via exception or event) to take over, OR we just hold.
                 # Aborting here breaks the "infinite hold" requirement.
                 logger.warning(f"[{req_id}] ⛔ Quota exceeded, waiting for worker to pick up signal...")
                 # Yield nothing, just loop. The worker watchdog will eventually see the flag and kill/restart us or handle it.
                 # But to prevent tight loop, sleep.
                 await asyncio.sleep(2)
                 continue

            data_receiving = True

            try:
                check_client_disconnected(f"Stream generator loop ({req_id}): ")
            except ClientDisconnectedError:
                logger.info(f"[{req_id}] Client disconnected, terminating stream generation")
                if data_receiving and not event_to_set.is_set():
                    logger.info(f"[{req_id}] Client disconnected during data reception, setting done signal immediately")
                    event_to_set.set()
                break

            data: Any
            if isinstance(raw_data, str):
                try:
                    data = json.loads(raw_data)
                except json.JSONDecodeError:
                    logger.warning(f"[{req_id}] Failed to parse stream data JSON: {raw_data}")
                    continue
            elif isinstance(raw_data, dict):
                data = cast(Dict[str, Any], raw_data)
            else:
                logger.warning(f"[{req_id}] Unknown stream data type: {type(raw_data)}")
                continue

            if not isinstance(data, dict):
                logger.warning(f"[{req_id}] Data is not a dict: {data}")
                continue

            # After isinstance check, data is confirmed to be dict - use cast for type narrowing
            typed_data: Dict[str, Any] = cast(Dict[str, Any], data)

            reason_raw: Any = typed_data.get("reason", "")
            reason: str = reason_raw if isinstance(reason_raw, str) else ""
            body_raw: Any = typed_data.get("body", "")
            body: str = body_raw if isinstance(body_raw, str) else ""
            done_raw: Any = typed_data.get("done", False)
            done: bool = done_raw if isinstance(done_raw, bool) else False
            function_raw: Any = typed_data.get("function", [])
            function: List[Any] = (
                cast(List[Any], function_raw) if isinstance(function_raw, list) else []
            )

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
                # [ID-04] Suppress Backfill on Recovery
                # If the stream ended because of an internal timeout triggered by a quota event
                # (which should ideally be caught by the Holding Pattern, but safety first),
                # we do NOT want to send synthetic content if recovery is intended.
                
                is_recovering = GlobalState.IS_RECOVERING
                
                # [ID-02] The Backfill: Synthetic Content if no body
                # Only trigger backfill if NOT recovering AND Quota is not exceeded.
                is_quota_exceeded = GlobalState.IS_QUOTA_EXCEEDED
                
                # [FIX-RACE] Add a small delay and re-check for quota flag on empty responses
                # to mitigate race conditions where 'done' arrives before the quota flag is processed.
                if done and not has_started_body and not is_recovering and not is_quota_exceeded:
                    # [FIX-QUOTA-RACE] Force a check for quota limit before giving up
                    try:
                        from browser_utils.operations import check_quota_limit
                        if page:
                            await check_quota_limit(page, req_id)
                    except Exception as e:
                        # check_quota_limit raises QuotaExceededError if detected, which sets the Global flag
                        # We just catch generic Exception to be safe and proceed to re-check flags
                        logger.warning(f"[{req_id}] Quota check during done-handling triggered exception: {e}")

                    # [FIX-DELAY] Increased grace period from 0.5s to 2.0s to allow network interceptor
                    # to catch late-arriving 'jserror' signals (seen taking ~550ms in logs).
                    logger.info(f"[{req_id}] Empty response detected. Waiting 2.0s for potential delayed Quota/Error signals...")
                    await asyncio.sleep(2.0)
                    is_quota_exceeded = GlobalState.IS_QUOTA_EXCEEDED # Re-check
                    is_recovering = GlobalState.IS_RECOVERING # Re-check recovery status too

                if not has_started_body and not is_recovering and not is_quota_exceeded:
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
                elif is_recovering or is_quota_exceeded:
                     reason = "active recovery mode" if is_recovering else "quota exceeded"
                     logger.info(f"[{req_id}] 🔇 Backfill suppressed due to {reason}. Entering holding pattern.")
                     
                     # [FIX-HOLD] If we detect quota/recovery at the very end of the stream,
                     # we MUST NOT finish the stream (which would close the connection).
                     # We must hold here to allow the queue worker to rotate auth and restart us.
                     while GlobalState.IS_QUOTA_EXCEEDED or GlobalState.IS_RECOVERING:
                         yield ": heartbeat\n\n"
                         await asyncio.sleep(1.0)

                # Handle Tool Calls or Stop
                if function and len(function) > 0:
                    tool_calls_list: List[Dict[str, Any]] = []
                    for func_idx, function_call_data in enumerate(function):
                        if isinstance(function_call_data, dict):
                            typed_func_data: Dict[str, Any] = cast(
                                Dict[str, Any], function_call_data
                            )
                            tool_calls_list.append(
                                {
                                    "id": f"call_{random_id()}",
                                    "index": func_idx,
                                    "type": "function",
                                    "function": {
                                        "name": typed_func_data.get("name", ""),
                                        "arguments": json.dumps(
                                            typed_func_data.get("params", {})
                                        ),
                                    },
                                }
                            )
                    delta_content: Dict[str, Any] = {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": tool_calls_list,
                    }
                    choice_item: Dict[str, Any] = {
                        "index": 0,
                        "delta": delta_content,
                        "finish_reason": "tool_calls",
                        "native_finish_reason": "tool_calls",
                    }
                else:
                    choice_item: Dict[str, Any] = {
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

    except (QuotaExceededError, QuotaExceededRetry):
        # Propagate Quota exceptions for resilient wrapper to handle
        raise
    except ClientDisconnectedError:
        logger.info(f"[{req_id}] Client disconnection detected in stream generator")
        if data_receiving and not event_to_set.is_set():
            logger.info(f"[{req_id}] Setting done signal immediately in client disconnect handler")
            event_to_set.set()
    except asyncio.CancelledError:
        logger.info("流式生成器被取消")
        if not event_to_set.is_set():
            event_to_set.set()
        raise
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
        logger.info("SSE 响应流生成结束")
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
                "choices": [
                    {
                        "index": 0,
                        "delta": {},
                        "finish_reason": "stop",
                        "native_finish_reason": "stop",
                    }
                ],
                "usage": usage_stats,
            }
            yield f"data: {json.dumps(final_chunk, ensure_ascii=False, separators=(',', ':'))}\n\n"
        except asyncio.CancelledError:
            raise
        except Exception as usage_err:
            logger.error(f"[{req_id}] Error calculating or sending usage stats: {usage_err}")
        try:
            logger.info(f"[{req_id}] Stream generator completed, sending [DONE] marker")
            yield "data: [DONE]\n\n"
        except asyncio.CancelledError:
            raise
        except Exception as done_err:
            logger.error(f"[{req_id}] Error sending [DONE] marker: {done_err}")
        if not event_to_set.is_set():
            event_to_set.set()
            logger.info(f"[{req_id}] Stream generator completion event set")


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
    """Playwright 最终响应 -> OpenAI 兼容 SSE 生成器。"""
    # Reuse already-imported helpers from utils to avoid repeated imports
    from browser_utils.page_controller import PageController
    from models import ClientDisconnectedError

    set_request_id(req_id)
    data_receiving = False
    try:
        page_controller = PageController(page, logger, req_id)
        final_content = await page_controller.get_response(check_client_disconnected, prompt_length=prompt_length, timeout=timeout)
        data_receiving = True
        lines = final_content.split("\n")
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
                    chunk = line[i : i + chunk_size]
                    yield generate_sse_chunk(chunk, req_id, model_name_for_stream)
                    await asyncio.sleep(0.03)
            if line_idx < len(lines) - 1:
                yield generate_sse_chunk("\n", req_id, model_name_for_stream)
                await asyncio.sleep(0.01)
        usage_stats = calculate_usage_stats(
            [msg.model_dump() for msg in request.messages],
            final_content,
            "",
        )
        logger.info(f"Playwright非流式计算的token使用统计: {usage_stats}")
        yield generate_sse_stop_chunk(
            req_id, model_name_for_stream, "stop", usage_stats
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
    except (QuotaExceededError, QuotaExceededRetry):
        # Propagate Quota exceptions for resilient wrapper to handle
        raise
    except ClientDisconnectedError:
        logger.info(f"[{req_id}] Client disconnection detected in Playwright stream generator")
        if data_receiving and not completion_event.is_set():
            logger.info(f"[{req_id}] Setting done signal immediately in Playwright client disconnect handler")
            completion_event.set()
    except asyncio.CancelledError:
        logger.info("Playwright流式生成器被取消")
        if not completion_event.is_set():
            completion_event.set()
        raise
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