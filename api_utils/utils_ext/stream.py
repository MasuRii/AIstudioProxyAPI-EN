import asyncio
import json
from typing import Any, AsyncGenerator


async def use_stream_response(req_id: str, timeout: float = 5.0, page=None) -> AsyncGenerator[Any, None]:
    """Enhanced stream response handler with UI-based generation active checks.
    
    Args:
        req_id: Request identifier for logging
        timeout: TTFB timeout in seconds  
        page: Playwright page instance for UI state checks
    """
    from server import STREAM_QUEUE, logger
    import queue

    if STREAM_QUEUE is None:
        logger.warning(f"[{req_id}] STREAM_QUEUE is None, 无法使用流响应")
        return

    logger.info(f"[{req_id}] 开始使用流响应 (TTFB Timeout: {timeout:.2f}s)")

    # Enhanced timeout settings for thinking models
    empty_count = 0
    # Dynamic timeout calculation: Ensure loop persists at least as long as the calculated timeout
    # Minimum 3000 iterations (300s) or timeout * 10 (timeout is in seconds, loop sleep is 0.1s)
    dynamic_retries = int(timeout * 10)
    max_empty_retries = max(3000, dynamic_retries)
    initial_wait_limit = dynamic_retries # TTFB should match the dynamic timeout
    
    logger.info(f"[{req_id}] Stream Loop Config: Max Empty Retries={max_empty_retries}, TTFB Limit={initial_wait_limit}")

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
            try:
                data = STREAM_QUEUE.get_nowait()
                if data is None:
                    logger.info(f"[{req_id}] 接收到流结束标志 (None)")
                    break
                empty_count = 0
                data_received = True
                received_items_count += 1
                logger.debug(f"[{req_id}] 接收到流数据[#{received_items_count}]: {type(data)} - {str(data)[:200]}...")

                # Identify and parse data
                parsed_item = None
                if isinstance(data, str):
                    try:
                        parsed_item = json.loads(data)
                    except json.JSONDecodeError:
                        logger.debug(f"[{req_id}] Received non-JSON string data, yielding raw.")
                        has_content = True
                        yield data
                        continue
                elif isinstance(data, dict):
                    parsed_item = data
                
                # Filter by Request ID if present (Zombie Stream Protection)
                if parsed_item and isinstance(parsed_item, dict):
                    item_req_id = parsed_item.get("req_id")
                    
                    # If item has a req_id and it doesn't match current req_id
                    if item_req_id and item_req_id != req_id and item_req_id != "unknown":
                        logger.warning(f"[{req_id}] 🛑 Dropped Zombie/Cross-talk data packet intended for [{item_req_id}]")
                        # Decrement received count as this wasn't for us
                        received_items_count -= 1
                        # Do NOT reset empty_count here, or we might loop forever on zombie data
                        # Actually, if we pulled it, it's gone from queue.
                        continue
                    
                    # Unwrap 'data' if it exists (new format)
                    if "data" in parsed_item:
                        real_data = parsed_item["data"]
                    else:
                        real_data = parsed_item # Old format fallback
                else:
                    real_data = data

                # Process the actual payload
                if isinstance(real_data, dict):
                    body = real_data.get("body", "")
                    reason = real_data.get("reason", "")
                    if body or reason:
                        has_content = True
                    
                    if real_data.get("done") is True:
                        logger.info(f"[{req_id}] Received DONE signal (body_len:{len(body)}, reason_len:{len(reason)}, items:{received_items_count})")
                        if not has_content and received_items_count == 1 and not stale_done_ignored:
                            logger.warning(f"[{req_id}] ⚠️ Received DONE with no content on first item. Likely stale data. Ignoring...")
                            stale_done_ignored = True
                            continue
                        yield real_data
                        break
                    else:
                        stale_done_ignored = False
                        yield real_data
                else:
                    # Fallback for non-dict data (rare)
                    has_content = True
                    yield real_data
            except (queue.Empty, asyncio.QueueEmpty):
                empty_count += 1

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
        logger.error(f"[{req_id}] 使用流响应时出错: {e}")
        raise
    finally:
        logger.info(
            f"[{req_id}] 流响应使用完成，数据接收状态: {data_received}, 有内容: {has_content}, 收到项目数: {received_items_count}, "
            f"曾忽略空done: {stale_done_ignored}"
        )


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