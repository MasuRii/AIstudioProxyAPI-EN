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

    try:
        async for raw_data in use_stream_response(req_id, timeout=timeout, page=page, check_client_disconnected=check_client_disconnected):
            if GlobalState.IS_QUOTA_EXCEEDED:
                logger.error(f"[{req_id}] ⛔ Quota exceeded detected during stream! Aborting.")
                yield generate_sse_chunk("\n\n[SYSTEM: Quota Exceeded. Stopping.]", req_id, model_name_for_stream)
                yield generate_sse_stop_chunk(req_id, model_name_for_stream)
                if not event_to_set.is_set():
                    event_to_set.set()
                break

            data_receiving = True

            try:
                check_client_disconnected(f"流式生成器循环 ({req_id}): ")
            except ClientDisconnectedError:
                logger.info(f"[{req_id}] 客户端断开连接，终止流式生成")
                if data_receiving and not event_to_set.is_set():
                    logger.info(f"[{req_id}] 数据接收中客户端断开，立即设置done信号")
                    event_to_set.set()
                break

            if isinstance(raw_data, str):
                try:
                    data = json.loads(raw_data)
                except json.JSONDecodeError:
                    logger.warning(f"[{req_id}] 无法解析流数据JSON: {raw_data}")
                    continue
            elif isinstance(raw_data, dict):
                data = raw_data
            else:
                logger.warning(f"[{req_id}] 未知的流数据类型: {type(raw_data)}")
                continue

            if not isinstance(data, dict):
                logger.warning(f"[{req_id}] 数据不是字典类型: {data}")
                continue

            reason = data.get("reason", "")
            body = data.get("body", "")
            done = data.get("done", False)
            function = data.get("function", [])

            if reason:
                full_reasoning_content = reason
            if body:
                full_body_content = body

            # Enhanced content sequencing: Send thinking first, then body content
            if len(reason) > last_reason_pos:
                reason_delta = reason[last_reason_pos:]
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
                last_reason_pos = len(reason)
                logger.debug(f"[{req_id}] 🧠 Sent reasoning content: {len(reason_delta)} chars")
                yield f"data: {json.dumps(output, ensure_ascii=False, separators=(',', ':'))}\n\n"

            # Smart body content sequencing - only send after thinking is complete
            if len(body) > last_body_pos:
                body_delta = body[last_body_pos:]
                finish_reason_val = None
                if done:
                    finish_reason_val = "stop"

                # Only send body content if we have substantial body content or we're done
                should_send_body = len(body_delta) > 0 and (
                    len(full_reasoning_content) == 0 or  # No thinking content, safe to send
                    last_reason_pos >= len(reason)       # Thinking content is up to date
                )
                
                if should_send_body:
                    delta_content = {"role": "assistant", "content": body_delta}
                    choice_item = {
                        "index": 0,
                        "delta": delta_content,
                        "finish_reason": finish_reason_val,
                        "native_finish_reason": finish_reason_val,
                    }

                    if done and function and len(function) > 0:
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
                        delta_content["tool_calls"] = tool_calls_list
                        choice_item["finish_reason"] = "tool_calls"
                        choice_item["native_finish_reason"] = "tool_calls"
                        delta_content["content"] = None

                    output = {
                        "id": chat_completion_id,
                        "object": "chat.completion.chunk",
                        "model": model_name_for_stream,
                        "created": created_timestamp,
                        "choices": [choice_item],
                    }
                    last_body_pos = len(body)
                    logger.debug(f"[{req_id}] 📝 Sent body content: {len(body_delta)} chars")
                    yield f"data: {json.dumps(output, ensure_ascii=False, separators=(',', ':'))}\n\n"
                else:
                    # Accumulate body content for later transmission
                    logger.debug(f"[{req_id}] ⏸️ Holding body content ({len(body_delta)} chars) until thinking complete")
            elif done:
                # Enhanced body content flushing when thinking is complete
                if len(full_body_content) > last_body_pos:
                    # Flush any remaining body content
                    remaining_body = full_body_content[last_body_pos:]
                    if remaining_body:
                        logger.info(f"[{req_id}] 📨 Flushing accumulated body content: {len(remaining_body)} chars")
                        delta_content = {"role": "assistant", "content": remaining_body}
                        choice_item = {
                            "index": 0,
                            "delta": delta_content,
                            "finish_reason": None,
                            "native_finish_reason": None,
                        }
                        output = {
                            "id": chat_completion_id,
                            "object": "chat.completion.chunk",
                            "model": model_name_for_stream,
                            "created": created_timestamp,
                            "choices": [choice_item],
                        }
                        yield f"data: {json.dumps(output, ensure_ascii=False, separators=(',', ':'))}\n\n"
                        last_body_pos = len(full_body_content)
                
                # [FIX-07] Client Compatibility Fallback (The "Saved You" Fix)
                # 如果到最后 body 还是空的，但有思考内容，强制填充 body 以防止客户端报错
                if len(full_body_content) == 0 and len(full_reasoning_content) > 0:
                    fallback_text = "\n\n(Model finished thinking but produced no text output.)"
                    
                    delta_content = {"role": "assistant", "content": fallback_text}
                    choice_item = {
                        "index": 0,
                        "delta": delta_content,
                        "finish_reason": None,
                        "native_finish_reason": None,
                    }
                    output = {
                        "id": chat_completion_id,
                        "object": "chat.completion.chunk",
                        "model": model_name_for_stream,
                        "created": created_timestamp,
                        "choices": [choice_item],
                    }
                    yield f"data: {json.dumps(output, ensure_ascii=False, separators=(',', ':'))}\n\n"
                    full_body_content += fallback_text

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

    except ClientDisconnectedError:
        logger.info(f"[{req_id}] 流式生成器中检测到客户端断开连接")
        if data_receiving and not event_to_set.is_set():
            logger.info(f"[{req_id}] 客户端断开异常处理中立即设置done信号")
            event_to_set.set()
    except Exception as e:
        logger.error(f"[{req_id}] 流式生成器处理过程中发生错误: {e}", exc_info=True)
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
            logger.info(f"[{req_id}] 计算的token使用统计: {usage_stats}")
            
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
            logger.error(f"[{req_id}] 计算或发送usage统计时出错: {usage_err}")
        try:
            logger.info(f"[{req_id}] 流式生成器完成，发送 [DONE] 标记")
            yield "data: [DONE]\n\n"
        except Exception as done_err:
            logger.error(f"[{req_id}] 发送 [DONE] 标记时出错: {done_err}")
        if not event_to_set.is_set():
            event_to_set.set()
            logger.info(f"[{req_id}] 流式生成器完成事件已设置")


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
                check_client_disconnected(f"Playwright流式生成器循环 ({req_id}): ")
            except ClientDisconnectedError:
                logger.info(f"[{req_id}] Playwright流式生成器中检测到客户端断开连接")
                if data_receiving and not completion_event.is_set():
                    logger.info(f"[{req_id}] Playwright数据接收中客户端断开，立即设置done信号")
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
        logger.info(f"[{req_id}] Playwright非流式计算的token使用统计: {usage_stats}")
        
        # Update global token count
        total_tokens = usage_stats.get("total_tokens", 0)
        GlobalState.increment_token_count(total_tokens)

        # Update profile usage stats
        import server
        if hasattr(server, 'current_auth_profile_path') and server.current_auth_profile_path:
            await increment_profile_usage(server.current_auth_profile_path, total_tokens)

        yield generate_sse_stop_chunk(req_id, model_name_for_stream, "stop", usage_stats)
    except ClientDisconnectedError:
        logger.info(f"[{req_id}] Playwright流式生成器中检测到客户端断开连接")
        if data_receiving and not completion_event.is_set():
            logger.info(f"[{req_id}] Playwright客户端断开异常处理中立即设置done信号")
            completion_event.set()
    except Exception as e:
        logger.error(f"[{req_id}] Playwright流式生成器处理过程中发生错误: {e}", exc_info=True)
        try:
            yield generate_sse_chunk(f"\n\n[错误: {str(e)}]", req_id, model_name_for_stream)
            yield generate_sse_stop_chunk(req_id, model_name_for_stream)
        except Exception:
            pass
    finally:
        if not completion_event.is_set():
            completion_event.set()
            logger.info(f"[{req_id}] Playwright流式生成器完成事件已设置")