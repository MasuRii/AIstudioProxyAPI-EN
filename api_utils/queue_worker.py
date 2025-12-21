"""
Queue Worker Module
Handles tasks in the request queue
"""

import asyncio
import logging
import time
from asyncio import Event, Future, Lock, Queue, Task
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union, cast

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from playwright.async_api import Locator, expect as expect_async

from api_utils.context_types import QueueItem
from .client_connection import check_client_connection
from logging_utils import set_request_id, set_source
from models import ChatCompletionRequest, QuotaExceededError


async def queue_worker() -> None:
    """Queue worker, processes tasks in the request queue"""
    # Delayed imports to avoid circularity
    import server
    from server import (
        logger,
        request_queue,
        processing_lock,
        model_switching_lock,
        params_cache_lock,
        RESPONSE_COMPLETION_TIMEOUT,
    )
    from config.global_state import GlobalState

    # Internal imports for queue worker logic
    from .request_processor import (
        _test_client_connection,
        ClientDisconnectedError,
        save_error_snapshot,
        _process_request_refactored,
    )
    from .error_utils import (
        client_cancelled,
        client_disconnected,
        server_error,
        processing_timeout,
    )
    from .utils_ext.stream import clear_stream_queue
    from browser_utils.auth_rotation import perform_auth_rotation
    from browser_utils.page_controller import PageController

    logger.info("--- Queue Worker Started ---")

    # Validate that required globals are initialized
    if request_queue is None:
        logger.critical("FATAL: request_queue is None! Initialization failed.")
        raise RuntimeError("request_queue not initialized")

    if processing_lock is None:
        logger.critical("FATAL: processing_lock is None! Initialization failed.")
        raise RuntimeError("processing_lock not initialized")

    if model_switching_lock is None:
        logger.critical("FATAL: model_switching_lock is None! Initialization failed.")
        raise RuntimeError("model_switching_lock not initialized")

    if params_cache_lock is None:
        logger.critical("FATAL: params_cache_lock is None! Initialization failed.")
        raise RuntimeError("params_cache_lock not initialized")

    logger.debug(
        f"Queue worker initialized with queue={request_queue}, lock={processing_lock}"
    )

    was_last_request_streaming = False
    last_request_completion_time = 0.0
    shutdown_check_interval = 0.1

    while True:
        request_item: Optional[QueueItem] = None
        result_future: Optional[Future] = None
        http_request: Optional[Request] = None
        req_id: str = "UNKNOWN"
        completion_event: Optional[Event] = None
        submit_btn_loc: Optional[Locator] = None
        client_disco_checker: Optional[Callable[[str], bool]] = None
        disconnect_monitor_task: Optional[Task] = None
        client_disconnected_early: bool = False

        try:
            # [SHUTDOWN] Check shutdown signal
            if GlobalState.IS_SHUTTING_DOWN.is_set():
                logger.info("🚨 Queue Worker detected shutdown signal, exiting.")
                break

            # Clean up disconnected requests in queue
            queue_size = request_queue.qsize()
            if queue_size > 0:
                checked_count = 0
                items_to_requeue = []
                processed_ids = set()

                while checked_count < queue_size and checked_count < 10:
                    if GlobalState.IS_SHUTTING_DOWN.is_set():
                        break
                    try:
                        item = request_queue.get_nowait()
                        item_req_id = item.get("req_id", "unknown")
                        if item_req_id in processed_ids:
                            items_to_requeue.append(item)
                            continue
                        processed_ids.add(item_req_id)

                        if not item.get("cancelled", False):
                            item_http_req = item.get("http_request")
                            if item_http_req:
                                try:
                                    if not await check_client_connection(
                                        item_req_id, item_http_req
                                    ):
                                        logger.info(
                                            f"[{item_req_id}] (Worker Queue Check) Client disconnect detected."
                                        )
                                        item["cancelled"] = True
                                        item_fut = item.get("result_future")
                                        if item_fut and not item_fut.done():
                                            item_fut.set_exception(
                                                client_disconnected(
                                                    item_req_id,
                                                    "Client disconnected while queued.",
                                                )
                                            )
                                except Exception as e:
                                    logger.error(
                                        f"[{item_req_id}] (Worker Queue Check) Error: {e}"
                                    )

                        items_to_requeue.append(item)
                        checked_count += 1
                    except asyncio.QueueEmpty:
                        break

                for item in items_to_requeue:
                    await request_queue.put(item)

            # [AUTH-ROTATION] Handle quota or rotation needs
            if GlobalState.IS_QUOTA_EXCEEDED or GlobalState.NEEDS_ROTATION:
                reason = (
                    "Quota Exceeded"
                    if GlobalState.IS_QUOTA_EXCEEDED
                    else "Graceful Rotation Pending"
                )
                logger.info(f"⏸️ Pausing worker for Auth Rotation ({reason})...")
                GlobalState.start_recovery()
                try:
                    current_model_id = cast(
                        Optional[str],
                        getattr(server, "current_ai_studio_model_id", None),
                    )
                    rotation_success = await perform_auth_rotation(
                        target_model_id=current_model_id or ""
                    )
                    if rotation_success:
                        GlobalState.NEEDS_ROTATION = False
                        logger.info("✅ Auth rotation completed successfully.")
                    else:
                        logger.error("❌ Auth rotation failed.")
                        await asyncio.sleep(1)
                finally:
                    GlobalState.finish_recovery()
                if not rotation_success:
                    continue

            if GlobalState.IS_SHUTTING_DOWN.is_set():
                break

            # Get next request
            try:
                current_timeout = (
                    shutdown_check_interval
                    if GlobalState.IS_SHUTTING_DOWN.is_set()
                    else 5.0
                )
                request_item = await asyncio.wait_for(
                    request_queue.get(), timeout=current_timeout
                )
            except asyncio.TimeoutError:
                continue

            if request_item is None:
                continue

            req_id = request_item["req_id"]
            request_data = request_item["request_data"]
            http_request = request_item["http_request"]
            result_future = request_item["result_future"]

            GlobalState.CURRENT_STREAM_REQ_ID = req_id
            logger.info(f"[{req_id}] (Worker) Processing request dequeued.")

            if GlobalState.IS_QUOTA_EXCEEDED:
                logger.warning(f"[{req_id}] (Worker) ⛔ Quota exceeded, re-queueing.")
                await request_queue.put(request_item)
                request_queue.task_done()
                continue

            if request_item.get("cancelled", False):
                if result_future and not result_future.done():
                    result_future.set_exception(
                        client_cancelled(req_id, "Request cancelled by user")
                    )
                request_queue.task_done()
                continue

            is_streaming_request = request_data.stream

            # Initial connection check
            if not await _test_client_connection(req_id, http_request):
                if result_future and not result_future.done():
                    result_future.set_exception(
                        HTTPException(status_code=499, detail="Client disconnected")
                    )
                request_queue.task_done()
                continue

            # Streaming delay
            current_time = time.time()
            if (
                was_last_request_streaming
                and is_streaming_request
                and (current_time - last_request_completion_time < 1.0)
            ):
                await asyncio.sleep(
                    max(0.5, 1.0 - (current_time - last_request_completion_time))
                )

            # Wait for lock
            async with processing_lock:
                logger.info(f"[{req_id}] (Worker) Lock acquired.")

                if not await _test_client_connection(req_id, http_request):
                    if result_future and not result_future.done():
                        result_future.set_exception(
                            HTTPException(status_code=499, detail="Client disconnected")
                        )
                elif result_future and result_future.done():
                    logger.info(f"[{req_id}] (Worker) Future already done.")
                else:
                    try:
                        returned_value = await _process_request_refactored(
                            req_id, request_data, http_request, result_future
                        )

                        if (
                            isinstance(returned_value, tuple)
                            and len(returned_value) == 3
                        ):
                            completion_event, submit_btn_loc, client_disco_checker = (
                                returned_value
                            )

                        if completion_event:
                            if isinstance(completion_event, dict):
                                if (
                                    completion_event.get("done")
                                    and is_streaming_request
                                ):
                                    if server.STREAM_QUEUE:
                                        await server.STREAM_QUEUE.put(completion_event)
                                if result_future and not result_future.done():
                                    result_future.set_result(completion_event)
                                client_disconnected_early = False
                            elif hasattr(completion_event, "wait"):
                                client_disconnected_early = False
                                comp_ev = cast(Event, completion_event)

                                async def enhanced_disconnect_monitor_fn():
                                    nonlocal client_disconnected_early
                                    disco_count = 0
                                    while not comp_ev.is_set():
                                        if GlobalState.IS_SHUTTING_DOWN.is_set():
                                            comp_ev.set()
                                            break
                                        if (
                                            GlobalState.IS_QUOTA_EXCEEDED
                                            and not GlobalState.IS_RECOVERING
                                        ):
                                            # Abort if quota exceeded and not recovering
                                            client_disconnected_early = True
                                            comp_ev.set()
                                            break

                                        if not await _test_client_connection(
                                            req_id, http_request
                                        ):
                                            disco_count += 1
                                            if disco_count >= 3:
                                                client_disconnected_early = True
                                                comp_ev.set()
                                                break
                                        else:
                                            disco_count = 0
                                        await asyncio.sleep(0.2)

                                disconnect_monitor_task = asyncio.create_task(
                                    enhanced_disconnect_monitor_fn()
                                )
                                await asyncio.wait_for(
                                    comp_ev.wait(),
                                    timeout=RESPONSE_COMPLETION_TIMEOUT / 1000 + 60,
                                )
                        else:
                            # Non-streaming
                            client_disconnected_early = False
                            res_fut = cast(Future, result_future)

                            async def non_streaming_monitor_fn():
                                nonlocal client_disconnected_early
                                while not res_fut.done():
                                    if GlobalState.IS_SHUTTING_DOWN.is_set():
                                        res_fut.cancel()
                                        break
                                    if not await _test_client_connection(
                                        req_id, http_request
                                    ):
                                        client_disconnected_early = True
                                        res_fut.set_exception(
                                            HTTPException(
                                                status_code=499,
                                                detail="Client disconnected",
                                            )
                                        )
                                        break
                                    await asyncio.sleep(0.3)

                            disconnect_monitor_task = asyncio.create_task(
                                non_streaming_monitor_fn()
                            )
                            await asyncio.wait_for(
                                asyncio.shield(res_fut),
                                timeout=RESPONSE_COMPLETION_TIMEOUT / 1000 + 60,
                            )

                        # Post-processing button handling
                        if client_disconnected_early:
                            if submit_btn_loc:
                                try:
                                    if await submit_btn_loc.is_enabled(timeout=2000):
                                        await submit_btn_loc.click(
                                            timeout=5000, force=True
                                        )
                                except Exception:
                                    pass
                        elif (
                            submit_btn_loc and client_disco_checker and completion_event
                        ):
                            try:
                                client_disco_checker("Post-stream check")
                                await asyncio.sleep(0.5)
                                client_disco_checker("Post-sleep check")
                                if await submit_btn_loc.is_enabled(timeout=2000):
                                    await submit_btn_loc.click(timeout=5000, force=True)
                                await expect_async(submit_btn_loc).to_be_disabled(
                                    timeout=10000
                                )
                            except ClientDisconnectedError:
                                pass
                            except Exception as e:
                                await save_error_snapshot(f"button_timeout_{req_id}")

                    except QuotaExceededError:
                        raise
                    except Exception as e:
                        logger.error(f"[{req_id}] (Worker) Error: {e}")
                        if result_future and not result_future.done():
                            result_future.set_exception(
                                server_error(req_id, f"Error: {e}")
                            )
                    finally:
                        if (
                            disconnect_monitor_task
                            and not disconnect_monitor_task.done()
                        ):
                            disconnect_monitor_task.cancel()
                            try:
                                await disconnect_monitor_task
                            except asyncio.CancelledError:
                                pass

            # [ROTATION] Post-request rotation check
            just_rotated = False
            if GlobalState.NEEDS_ROTATION:
                current_model_id_rot = cast(
                    Optional[str], getattr(server, "current_ai_studio_model_id", None)
                )
                if await perform_auth_rotation(
                    target_model_id=current_model_id_rot or ""
                ):
                    GlobalState.NEEDS_ROTATION = False
                    just_rotated = True

            # [CLEANUP]
            try:
                await clear_stream_queue()
                if (
                    not GlobalState.IS_QUOTA_EXCEEDED
                    and not just_rotated
                    and not GlobalState.IS_SHUTTING_DOWN.is_set()
                ):
                    if submit_btn_loc and client_disco_checker:
                        from server import (
                            page_instance as s_page,
                            is_page_ready as s_ready,
                            browser_instance as s_browser,
                        )

                        if (
                            s_page
                            and s_ready
                            and s_browser
                            and s_browser.is_connected()
                        ):
                            try:
                                controller = PageController(s_page, logger, req_id)
                                await controller.clear_chat_history(lambda stage: False)
                            except Exception:
                                try:
                                    await s_page.reload()
                                except Exception:
                                    pass
            except Exception as e:
                logger.error(f"[{req_id}] Cleanup error: {e}")

            was_last_request_streaming = is_streaming_request
            last_request_completion_time = time.time()

        except asyncio.CancelledError:
            if result_future and not result_future.done():
                result_future.cancel()
            break
        except QuotaExceededError:
            try:
                if await _test_client_connection(req_id, http_request):
                    request_queue.put_nowait(request_item)
                elif result_future and not result_future.done():
                    result_future.set_exception(
                        HTTPException(
                            status_code=499, detail="Disconnected during quota error"
                        )
                    )
            except Exception:
                pass
        except Exception as e:
            logger.error(f"[{req_id}] Unexpected error: {e}", exc_info=True)
            if result_future and not result_future.done():
                result_future.set_exception(server_error(req_id, f"Error: {e}"))
        finally:
            if request_item:
                request_queue.task_done()

    logger.info("--- Queue Worker Stopped ---")
