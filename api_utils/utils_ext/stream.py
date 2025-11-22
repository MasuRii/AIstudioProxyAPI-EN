import asyncio
import json
import re
from typing import Any, AsyncGenerator


from typing import Any, AsyncGenerator, Optional, Callable

# Universal Pattern: Detects the start of XML tags (<name...) or Code Blocks (```)
# This signals that the model has stopped "thinking" and started "outputting".
STRUCTURE_BOUNDARY = re.compile(r'(?:^|\n)\s*(<[a-zA-Z_]+|```)')

async def use_stream_response(req_id: str, timeout: float = 5.0, page=None, check_client_disconnected: Optional[Callable] = None) -> AsyncGenerator[Any, None]:
    """Enhanced stream response handler with UI-based generation active checks.
    
    Args:
        req_id: Request identifier for logging
        timeout: TTFB timeout in seconds
        page: Playwright page instance for UI state checks
        check_client_disconnected: Optional callback to check if client disconnected
    """
    from server import STREAM_QUEUE, logger
    from models import ClientDisconnectedError, QuotaExceededError
    from config.global_state import GlobalState
    from config import (
        SCROLL_CONTAINER_SELECTOR,
        CHAT_SESSION_CONTENT_SELECTOR,
        LAST_CHAT_TURN_SELECTOR,
    )
    import queue

    if STREAM_QUEUE is None:
        logger.warning(f"[{req_id}] STREAM_QUEUE is None, 无法使用流响应")
        return
        
    # 引入 PageController 用于 DOM 兜底
    from browser_utils.page_controller import PageController

    logger.info(f"[{req_id}] 开始使用流响应 (TTFB Timeout: {timeout:.2f}s)")

    accumulated_body = ""
    accumulated_reason_len = 0
    
    # [FIX-11] Flag to track if we have forcefully switched to body mode
    force_body_mode = False

    # Enhanced timeout settings for thinking models
    empty_count = 0
    max_empty_retries = 900  # Increased to 90 seconds (900 * 0.1s)
    initial_wait_limit = int(timeout * 10)
    data_received = False
    has_content = False
    received_items_count = 0
    stale_done_ignored = False
    last_ui_check_time = 0
    ui_check_interval = 30  # Check UI state every 30 empty reads (3 seconds)
    
    # UI-based generation check helper
    async def check_ui_generation_active():
        """Check if the AI is still generating based on UI state."""
        if not page:
            return False
            
        try:
            # Check for "Stop generating" button (indicates active generation)
            stop_button = page.locator('button[aria-label="Stop generating"]')
            if await stop_button.is_visible(timeout=1000):
                return True
                
            # Check if submit button is disabled (generation in progress)
            submit_button = page.locator('button[aria-label="Run"].run-button, ms-run-button button[type="submit"].run-button')
            if await submit_button.count() > 0:
                is_disabled = await submit_button.first.is_disabled(timeout=1000)
                if is_disabled:
                    return True
                    
            return False
        except Exception:
            # If UI check fails, assume generation is not active
            return False

    try:
        while True:
            # [FIX-SCROLL] Active Viewport Tracking (Auto-Scroll)
            # Force the viewport to the bottom to prevent DOM virtualization from unloading elements
            if page:
                try:
                    await page.evaluate("""([scrollSel, contentSel, lastTurnSel]) => {
                        // 1. Target the specific AI Studio scroll container (Primary)
                        const scrollContainer = document.querySelector(scrollSel);
                        if (scrollContainer) {
                            scrollContainer.scrollTop = scrollContainer.scrollHeight;
                        }

                        // 2. Target the specific chat turn container (Backup)
                        const sessionContent = document.querySelector(contentSel);
                        if (sessionContent) {
                             // Some versions might scroll this wrapper instead
                             sessionContent.scrollTop = sessionContent.scrollHeight;
                        }
                        
                        // 3. Force the absolute last turn into view (Crucial for Virtual Scroll)
                        // This tells the virtualizer "I am looking at the bottom, please render these elements"
                        const lastTurn = document.querySelector(lastTurnSel);
                        if (lastTurn) {
                            lastTurn.scrollIntoView({behavior: "instant", block: "end"});
                        }
                        
                        // 4. Generic Window scroll (Safety net)
                        window.scrollTo(0, document.body.scrollHeight);
                    }""", [SCROLL_CONTAINER_SELECTOR, CHAT_SESSION_CONTENT_SELECTOR, LAST_CHAT_TURN_SELECTOR])
                except Exception:
                    pass

            # [ROBUST-02] Check for Quota Exceeded
            if GlobalState.IS_QUOTA_EXCEEDED:
                logger.warning(f"[{req_id}] ⛔ Quota detected during wait loop. Aborting request immediately.")
                raise QuotaExceededError("Global Quota Limit Reached during stream wait.")

            try:
                data = STREAM_QUEUE.get_nowait()
                if data is None:
                    logger.info(f"[{req_id}] 接收到流结束标志 (None)")
                    break
                empty_count = 0
                data_received = True
                received_items_count += 1
                logger.debug(f"[{req_id}] 接收到流数据[#{received_items_count}]: {type(data)} - {str(data)[:200]}...")

                if isinstance(data, str):
                    try:
                        parsed_data = json.loads(data)
                        
                        # [FIX-11] Generic Content Boundary Detector
                        # Logic: Determine if this is Thinking or Body based on content structure
                        p_reason = parsed_data.get("reason", "")
                        p_body = parsed_data.get("body", "")
                        
                        if force_body_mode:
                            # We already detected a boundary, treat all reason as body
                            if p_reason:
                                parsed_data["body"] = p_body + p_reason
                                parsed_data["reason"] = ""
                        elif p_reason:
                             # Check for boundary in thinking content
                             match = STRUCTURE_BOUNDARY.search(p_reason)
                             if match:
                                 logger.info(f"[{req_id}] 🔄 Detected Structural Boundary ('{match.group(1)}'). Switching to Body.")
                                 split_idx = match.start()
                                 
                                 thought_part = p_reason[:split_idx]
                                 body_part = p_reason[split_idx:]
                                 
                                 parsed_data["reason"] = thought_part
                                 parsed_data["body"] = p_body + body_part
                                 force_body_mode = True

                        if parsed_data.get("done") is True:
                            body = parsed_data.get("body", "")
                            reason = parsed_data.get("reason", "")
                            accumulated_body += body
                            accumulated_reason_len += len(reason)
                            
                            if body or reason:
                                has_content = True
                            logger.info(f"[{req_id}] 接收到JSON格式的完成标志 (body长度:{len(body)}, reason长度:{len(reason)}, 已收到项目数:{received_items_count})")
                            
                            # [FIX-06] Thinking-to-Answer Handover Protocol
                            # 检测是否只输出了思考过程而没有正文 (Thinking > 0, Body == 0)
                            if accumulated_reason_len > 0 and len(accumulated_body) == 0:
                                logger.info(f"[{req_id}] ⚠️ 检测到 Thinking-Only 响应 (Reason: {accumulated_reason_len}, Body: 0)。启动 DOM Body-Wait 协议...")
                                
                                try:
                                    if page:
                                        pc = PageController(page, logger, req_id)
                                        # 尝试等待正文出现，最多等 10 秒 (20 * 0.5s)
                                        wait_attempts = 20
                                        dom_body_found = False
                                        
                                        for wait_i in range(wait_attempts):
                                            await asyncio.sleep(0.5)
                                            # 使用新添加的 get_body_text_only_from_dom 方法
                                            dom_text = await pc.get_body_text_only_from_dom()
                                            
                                            if dom_text and len(dom_text.strip()) > 0:
                                                logger.info(f"[{req_id}] ✅ 在第 {wait_i+1} 次尝试中通过 DOM 捕获到正文: {len(dom_text)} chars")
                                                
                                                # [Sanity Check] Prevent Duplication
                                                # 如果 stream 发送了部分内容（虽然这里是 body==0 的分支，但为了代码健壮性保留检查逻辑）
                                                final_text_to_yield = dom_text
                                                if len(accumulated_body) > 0:
                                                    if dom_text.startswith(accumulated_body):
                                                        final_text_to_yield = dom_text[len(accumulated_body):]
                                                        logger.info(f"[{req_id}] 去重: 剔除已发送的 {len(accumulated_body)} 字符")
                                                
                                                if final_text_to_yield:
                                                    # 构造一个新的 body chunk
                                                    new_chunk = {
                                                        "body": final_text_to_yield,
                                                        "reason": "",
                                                        "done": False
                                                    }
                                                    yield new_chunk
                                                    accumulated_body += final_text_to_yield
                                                    dom_body_found = True
                                                    break
                                        
                                        if not dom_body_found:
                                            logger.warning(f"[{req_id}] ⚠️ DOM 等待超时，仍未获取到正文。将执行 Fallback (复制思考内容或提示错误)。")
                                    else:
                                        logger.warning(f"[{req_id}] ⚠️ 无法执行 DOM Wait (Page 对象为空)。")
                                except Exception as dom_wait_err:
                                    logger.error(f"[{req_id}] ❌ DOM Body-Wait 协议执行出错: {dom_wait_err}")

                            if not has_content and received_items_count == 1 and not stale_done_ignored:
                                logger.warning(f"[{req_id}] ⚠️ 收到done=True但没有任何内容，且这是第一个接收的项目！可能是队列残留的旧数据，尝试忽略并继续等待...")
                                stale_done_ignored = True
                                continue
                            yield parsed_data
                            break
                        else:
                            body = parsed_data.get("body", "")
                            reason = parsed_data.get("reason", "")
                            accumulated_body += body
                            accumulated_reason_len += len(reason)
                            
                            if body or reason:
                                has_content = True
                            stale_done_ignored = False
                            yield parsed_data
                    except json.JSONDecodeError:
                        logger.debug(f"[{req_id}] 返回非JSON字符串数据")
                        has_content = True
                        stale_done_ignored = False
                        yield data
                else:
                    # Handle Dict data with same boundary logic
                    if isinstance(data, dict):
                        # [FIX-11] Generic Content Boundary Detector
                        p_reason = data.get("reason", "")
                        p_body = data.get("body", "")
                        
                        if force_body_mode:
                            if p_reason:
                                data["body"] = p_body + p_reason
                                data["reason"] = ""
                        elif p_reason:
                             match = STRUCTURE_BOUNDARY.search(p_reason)
                             if match:
                                 logger.info(f"[{req_id}] 🔄 Detected Structural Boundary ('{match.group(1)}'). Switching to Body.")
                                 split_idx = match.start()
                                 
                                 thought_part = p_reason[:split_idx]
                                 body_part = p_reason[split_idx:]
                                 
                                 data["reason"] = thought_part
                                 data["body"] = p_body + body_part
                                 force_body_mode = True

                        body = data.get("body", "")
                        reason = data.get("reason", "")
                        if body or reason:
                            has_content = True
                        
                        yield data
                        
                        if data.get("done") is True:
                            logger.info(f"[{req_id}] 接收到字典格式的完成标志 (body长度:{len(body)}, reason长度:{len(reason)}, 已收到项目数:{received_items_count})")
                            if not has_content and received_items_count == 1 and not stale_done_ignored:
                                logger.warning(f"[{req_id}] ⚠️ 收到done=True但没有任何内容，且这是第一个接收的项目！可能是队列残留的旧数据，尝试忽略并继续等待...")
                                stale_done_ignored = True
                                continue
                            break
                        else:
                            stale_done_ignored = False
            except (queue.Empty, asyncio.QueueEmpty):
                empty_count += 1

                # Check for disconnect during wait
                if check_client_disconnected:
                    try:
                        check_client_disconnected(f"Stream Queue Wait ({req_id})")
                    except ClientDisconnectedError:
                        logger.warning(f"[{req_id}] 客户端在流式队列等待期间断开连接。")
                        raise

                # Fail-Fast TTFB Check
                if received_items_count == 0 and empty_count >= initial_wait_limit:
                    logger.error(f"[{req_id}] Stream has no data after {empty_count * 0.1:.1f} seconds, aborting (TTFB Timeout).")

                    # Trigger Fail-Fast Browser Reload
                    try:
                        from server import page_instance
                        if page_instance:
                            logger.info(f"[{req_id}] Triggering fail-fast browser reload due to TTFB timeout...")
                            await page_instance.reload()
                    except Exception as reload_err:
                        logger.error(f"[{req_id}] Failed to reload page during TTFB timeout: {reload_err}")

                    yield {"done": True, "reason": "ttfb_timeout", "body": "", "function": []}
                    return

                # Enhanced timeout check with UI-based generation detection
                if empty_count >= max_empty_retries:
                    # Check UI state before declaring timeout
                    ui_generation_active = await check_ui_generation_active()
                    
                    if ui_generation_active:
                        logger.info(f"[{req_id}] Stream timeout reached but UI shows active generation. Extending timeout by 30s...")
                        max_empty_retries += 300  # Add 30 more seconds
                        # Reset empty count to continue waiting
                        empty_count = 0
                        continue
                    else:
                        if not data_received:
                            logger.error(f"[{req_id}] 流响应队列空读取次数达到上限且未收到任何数据，可能是辅助流未启动或出错")
                        else:
                            logger.warning(f"[{req_id}] 流响应队列空读取次数达到上限 ({max_empty_retries})，结束读取")
                        yield {"done": True, "reason": "internal_timeout", "body": "", "function": []}
                        return

                # Periodic logging and UI checks
                if empty_count % 50 == 0:
                    elapsed_seconds = empty_count * 0.1
                    logger.info(f"[{req_id}] 等待流数据... ({empty_count}/{max_empty_retries}, 已收到:{received_items_count}项, 耗时:{elapsed_seconds:.1f}s)")
                
                # UI-based generation check every 3 seconds
                if empty_count - last_ui_check_time >= ui_check_interval:
                    ui_generation_active = await check_ui_generation_active()
                    last_ui_check_time = empty_count
                    
                    if ui_generation_active:
                        logger.info(f"[{req_id}] UI检测到模型仍在生成中，继续等待... (已等待 {empty_count * 0.1:.1f}s)")
                    else:
                        logger.debug(f"[{req_id}] UI检测到模型未在生成 (已等待 {empty_count * 0.1:.1f}s)")

                await asyncio.sleep(0.1)
                continue
    except Exception as e:
        if isinstance(e, ClientDisconnectedError):
             logger.info(f"[{req_id}] 停止流响应: 客户端已断开。")
             raise e
        logger.error(f"[{req_id}] 使用流响应时出错: {e}")
        raise
    finally:
        logger.info(
            f"[{req_id}] 流响应使用完成，数据接收状态: {data_received}, 有内容: {has_content}, 收到项目数: {received_items_count}, "
            f"曾忽略空done: {stale_done_ignored}. 开始清理队列..."
        )
        # Trigger queue cleanup to prevent residual data
        await clear_stream_queue()


async def clear_stream_queue():
    from server import STREAM_QUEUE, logger
    import queue

    if STREAM_QUEUE is None:
        logger.info("流队列未初始化或已被禁用，跳过清空操作。")
        return

    cleared_count = 0
    while True:
        try:
            data_chunk = await asyncio.to_thread(STREAM_QUEUE.get_nowait)
            cleared_count += 1
            if cleared_count <= 3:
                logger.debug(f"清空流式队列项 #{cleared_count}: {type(data_chunk)} - {str(data_chunk)[:100]}...")
        except queue.Empty:
            logger.info(f"流式队列已清空 (捕获到 queue.Empty)。清空项数: {cleared_count}")
            break
        except Exception as e:
            logger.error(f"清空流式队列时发生意外错误 (已清空{cleared_count}项): {e}", exc_info=True)
            break
    
    if cleared_count > 0:
        logger.warning(f"⚠️ 流式队列缓存清空完毕，共清理了 {cleared_count} 个残留项目！")
    else:
        logger.info("流式队列缓存清空完毕（队列为空）。")