"""
Queue Worker Module
Handles tasks in the request queue
"""

import asyncio
import time
from fastapi import HTTPException
from typing import Any, Dict, Optional, Tuple
from .error_utils import (
    client_disconnected,
    client_cancelled,
    processing_timeout,
    server_error,
)
from models import QuotaExceededError



async def queue_worker() -> None:
    """Queue worker, processes tasks in the request queue"""
    # Import global variables
    from server import (
        logger, request_queue, processing_lock, model_switching_lock,
        params_cache_lock
    )
    from config.global_state import GlobalState
    
    logger.info("--- Queue Worker Started ---")
    
    # Check and initialize global variables
    if request_queue is None:
        logger.info("Initializing request_queue...")
        from asyncio import Queue
        request_queue = Queue()
    
    if processing_lock is None:
        logger.info("Initializing processing_lock...")
        from asyncio import Lock
        processing_lock = Lock()
    
    if model_switching_lock is None:
        logger.info("Initializing model_switching_lock...")
        from asyncio import Lock
        model_switching_lock = Lock()
    
    if params_cache_lock is None:
        logger.info("Initializing params_cache_lock...")
        from asyncio import Lock
        params_cache_lock = Lock()
    
    was_last_request_streaming = False
    last_request_completion_time = 0
    
    # [SHUTDOWN-01] Immediate shutdown detection
    shutdown_check_interval = 0.1

    while True:
        request_item = None
        result_future = None
        req_id = "UNKNOWN"
        completion_event = None
        submit_btn_loc = None
        client_disco_checker = None
        
        try:
            # [SHUTDOWN-02] Check shutdown status immediately at loop start
            if GlobalState.IS_SHUTTING_DOWN.is_set():
                logger.info("🚨 Queue Worker detected shutdown signal, exiting immediately.")
                break

            # Check items in queue, clean up disconnected requests
            queue_size = request_queue.qsize()
            if queue_size > 0:
                checked_count = 0
                items_to_requeue = []
                processed_ids = set()
                
                while checked_count < queue_size and checked_count < 10:
                    # [SHUTDOWN-03] Check shutdown during queue processing
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
                            item_http_request = item.get("http_request")
                            if item_http_request:
                                try:
                                    if await item_http_request.is_disconnected():
                                        logger.info(f"[{item_req_id}] (Worker Queue Check) Client disconnect detected, marking as cancelled.")
                                        item["cancelled"] = True
                                        item_future = item.get("result_future")
                                        if item_future and not item_future.done():
                                            item_future.set_exception(client_disconnected(item_req_id, "Client disconnected while queued."))
                                except Exception as check_err:
                                    logger.error(f"[{item_req_id}] (Worker Queue Check) Error checking disconnect: {check_err}")
                        
                        items_to_requeue.append(item)
                        checked_count += 1
                    except asyncio.QueueEmpty:
                        break
                
                for item in items_to_requeue:
                    await request_queue.put(item)
            
            # [CRIT-01] Gatekeeper Check: BEFORE getting next request, check quota exceeded OR Soft Rotation
            # [GR-03] Pre-Flight Rotation Check
            if GlobalState.IS_QUOTA_EXCEEDED or GlobalState.NEEDS_ROTATION:
                reason = "Quota Exceeded" if GlobalState.IS_QUOTA_EXCEEDED else "Graceful Rotation Pending"
                logger.info(f"⏸️ Pausing worker for Auth Rotation ({reason})...")
                
                # [ID-01] Signal Start of Recovery
                GlobalState.start_recovery()
                
                try:
                    # Get current model ID for smart rotation
                    import server
                    current_model_id = getattr(server, 'current_ai_studio_model_id', None)
                    from browser_utils.auth_rotation import perform_auth_rotation
                    rotation_success = await perform_auth_rotation(target_model_id=current_model_id)
                    if rotation_success:
                        GlobalState.NEEDS_ROTATION = False
                        logger.info("✅ Auth rotation completed successfully. Resuming request processing.")
                    else:
                        logger.error("❌ Auth rotation failed. System may be exhausted.")
                        # Continue to check again after a short delay
                        await asyncio.sleep(1)
                        # Do NOT finish recovery here if failed, keep system locked or retry?
                        # For now, we finish to allow retries or error propagation
                finally:
                    # [ID-01] Signal End of Recovery (Successful or not, we unblock streams)
                    GlobalState.finish_recovery()

                if not rotation_success:
                    continue

            # [SHUTDOWN-05] Check shutdown before getting new request
            if GlobalState.IS_SHUTTING_DOWN.is_set():
                logger.info("🚨 Queue Worker detected shutdown before getting request, exiting immediately.")
                break

            # Get next request
            try:
                # [SHUTDOWN-06] Use shorter timeout during shutdown for faster response
                current_timeout = shutdown_check_interval if GlobalState.IS_SHUTTING_DOWN.is_set() else 5.0
                request_item = await asyncio.wait_for(request_queue.get(), timeout=current_timeout)
            except asyncio.TimeoutError:
                # [SHUTDOWN-07] Check if we timed out due to shutdown
                if GlobalState.IS_SHUTTING_DOWN.is_set():
                    break
                # If no new request within 5 seconds, continue loop check
                continue
            
            req_id = request_item["req_id"]
            request_data = request_item["request_data"]
            http_request = request_item["http_request"]
            result_future = request_item["result_future"]

            # [CONCURRENCY-FIX] Set the current active request ID
            # This invalidates any previous stream consumers still running
            GlobalState.CURRENT_STREAM_REQ_ID = req_id
            logger.info(f"[{req_id}] (Worker) Set GLOBAL CURRENT_STREAM_REQ_ID. Previous streams should terminate.")

            # [CRIT-01] Secondary quota check after getting request (defense in depth)
            if GlobalState.IS_QUOTA_EXCEEDED:
                logger.warning(f"[{req_id}] (Worker) ⛔ Quota exceeded flag detected after getting request. Re-queueing request to hold for rotation.")
                # Re-queue the request to the front (or back) to be processed after rotation
                # We use items_to_requeue logic or just put it back
                try:
                     await request_queue.put(request_item)
                     request_queue.task_done()
                     # Trigger rotation logic immediately in next loop iteration
                     continue
                except Exception as requeue_err:
                    logger.error(f"[{req_id}] Failed to re-queue request during quota hold: {requeue_err}")
                    if not result_future.done():
                        result_future.set_exception(HTTPException(status_code=429, detail="Quota exceeded. Please restart with a new profile."))
                    request_queue.task_done()
                    continue

            if request_item.get("cancelled", False):
                logger.info(f"[{req_id}] (Worker) Request cancelled, skipping.")
                if not result_future.done():
                    result_future.set_exception(client_cancelled(req_id, "Request cancelled by user"))
                request_queue.task_done()
                continue

            is_streaming_request = request_data.stream
            logger.info(f"[{req_id}] (Worker) Request dequeued. Mode: {'Streaming' if is_streaming_request else 'Non-streaming'}")

            # Optimize: Proactively check client connection status before starting processing to avoid unnecessary work
            from api_utils.request_processor import _test_client_connection
            is_connected = await _test_client_connection(req_id, http_request)
            if not is_connected:
                logger.info(f"[{req_id}] (Worker) ✅ Proactively detected client disconnection, skipping processing to save resources")
                if not result_future.done():
                    result_future.set_exception(HTTPException(status_code=499, detail=f"[{req_id}] Client disconnected before processing"))
                request_queue.task_done()
                continue
            
            # Stream request interval control
            current_time = time.time()
            if was_last_request_streaming and is_streaming_request and (current_time - last_request_completion_time < 1.0):
                delay_time = max(0.5, 1.0 - (current_time - last_request_completion_time))
                logger.info(f"[{req_id}] (Worker) Consecutive streaming request, adding {delay_time:.2f}s delay...")
                await asyncio.sleep(delay_time)
            
            # Check client connection again before waiting for lock
            is_connected = await _test_client_connection(req_id, http_request)
            if not is_connected:
                logger.info(f"[{req_id}] (Worker) ✅ Detected client disconnect while waiting for lock, cancelling processing")
                if not result_future.done():
                    result_future.set_exception(HTTPException(status_code=499, detail=f"[{req_id}] Client closed the request"))
                request_queue.task_done()
                continue
            
            logger.info(f"[{req_id}] (Worker) Waiting for processing lock...")
            async with processing_lock:
                logger.info(f"[{req_id}] (Worker) Processing lock acquired. Starting core processing...")
                
                # Final client connection check after acquiring lock
                is_connected = await _test_client_connection(req_id, http_request)
                if not is_connected:
                    logger.info(f"[{req_id}] (Worker) ✅ Detected client disconnect after acquiring lock, cancelling processing")
                    if not result_future.done():
                        result_future.set_exception(HTTPException(status_code=499, detail=f"[{req_id}] Client closed the request"))
                elif result_future.done():
                    logger.info(f"[{req_id}] (Worker) Future already done/cancelled before processing. Skipping.")
                else:
                    # Call actual request processing function
                    try:
                        from api_utils import _process_request_refactored
                        returned_value = await _process_request_refactored(
                            req_id, request_data, http_request, result_future
                        )
                        
                        completion_event, submit_btn_loc, client_disco_checker = None, None, None
                        current_request_was_streaming = False

                        if isinstance(returned_value, tuple) and len(returned_value) == 3:
                            completion_event, submit_btn_loc, client_disco_checker = returned_value
                            if completion_event is not None:
                                current_request_was_streaming = True
                                logger.info(f"[{req_id}] (Worker) _process_request_refactored returned stream info (event, locator, checker).")
                            else:
                                current_request_was_streaming = False
                                logger.warning(f"[{req_id}] (Worker) _process_request_refactored returned a tuple, but completion_event is None (likely non-stream or early exit).")
                                # [OP-01] Enhanced Logging for Debugging
                                logger.warning(f"[{req_id}] Tuple Dump: Index 0 (Event) Type: {type(returned_value[0])}")
                                logger.warning(f"[{req_id}] Tuple Dump: Index 1 (Locator) Type: {type(returned_value[1])}")
                                logger.warning(f"[{req_id}] Future Status: Done={result_future.done()}")
                        elif returned_value is None:
                            current_request_was_streaming = False
                            logger.info(f"[{req_id}] (Worker) _process_request_refactored returned non-stream completion (None).")
                        else:
                            current_request_was_streaming = False
                            logger.warning(f"[{req_id}] (Worker) _process_request_refactored returned unexpected type: {type(returned_value)}")

                        # Unified client disconnect detection and response handling
                        if completion_event:
                            if isinstance(completion_event, dict):
                                logger.info(f"[{req_id}] (Worker) Received direct dictionary response. Skipping wait.")
                                
                                # [STREAM-FIX] If we get a done signal for a streaming request, ensure stream is terminated
                                if completion_event.get("done") is True and is_streaming_request:
                                    logger.info(f"[{req_id}] (Worker) Done signal received for streaming request. Ensuring stream termination.")
                                    from server import STREAM_QUEUE
                                    if STREAM_QUEUE:
                                        await STREAM_QUEUE.put(completion_event)

                                client_disconnected_early = False
                                # Ensure future is set if not done
                                if not result_future.done():
                                    result_future.set_result(completion_event)
                            elif hasattr(completion_event, 'wait'):
                                # Streaming mode: Wait for stream generator completion signal
                                logger.info(f"[{req_id}] (Worker) Waiting for stream generator completion signal...")

                                # Create an enhanced client disconnect detector supporting early done signal triggering
                                client_disconnected_early = False

                                async def enhanced_disconnect_monitor():
                                    nonlocal client_disconnected_early
                                    while not completion_event.is_set():
                                        try:
                                            # [SHUTDOWN-08] Cooperative cancellation in stream monitor
                                            if GlobalState.IS_SHUTTING_DOWN.is_set():
                                                logger.info(f"[{req_id}] (Worker) 🚨 Shutdown detected in stream monitor. Aborting wait.")
                                                if not completion_event.is_set():
                                                    completion_event.set()
                                                break

                                            # Check Global Quota State
                                            if GlobalState.IS_QUOTA_EXCEEDED:
                                                # [ID-04] Enhanced Quota Handling in Worker
                                                if GlobalState.IS_RECOVERING:
                                                    # If recovering, we do NOT abort. We wait.
                                                    # The stream generator handles the pause. The worker just needs to NOT kill it.
                                                    # We log occasionally to show we are alive.
                                                    if int(time.time()) % 5 == 0:
                                                        logger.info(f"[{req_id}] (Worker) 🔄 Recovery in progress... Worker holding position.")
                                                    await asyncio.sleep(0.5)
                                                    continue
                                                else:
                                                    # [FIX-RACE] Check if we just finished recovering
                                                    # If rotation happened recently (< 10s), ignore the quota flag (it might be stale or transient)
                                                    # and allow the worker to continue waiting.
                                                    time_since_rotation = time.time() - GlobalState.LAST_ROTATION_TIMESTAMP
                                                    if time_since_rotation < 10.0:
                                                        logger.info(f"[{req_id}] (Worker) 🛡️ Quota signal ignored - Rotation completed {time_since_rotation:.2f}s ago. Resuming wait.")
                                                        await asyncio.sleep(0.5)
                                                        continue

                                                    # Quota is exceeded but Recovery hasn't signaled yet.
                                                    # It might be starting momentarily. Give it a grace period.
                                                    # [DEBUG-LOG] detailed state diagnosis
                                                    logger.warning(f"[{req_id}] (Worker) ⛔ Quota signal detected. State: Recovering={GlobalState.IS_RECOVERING}, Lock={GlobalState.AUTH_ROTATION_LOCK.is_set()}")
                                                    logger.warning(f"[{req_id}] (Worker) ⛔ Waiting for recovery initiation...")
                                                    
                                                    await asyncio.sleep(2.0)
                                                    
                                                    if GlobalState.IS_RECOVERING:
                                                        logger.info(f"[{req_id}] (Worker) 🔄 Recovery caught after wait. Resuming loop.")
                                                        continue # Loop back to recovery handling
                                                    
                                                    # [FIX-BRITTLE] Check if quota cleared during wait
                                                    if not GlobalState.IS_QUOTA_EXCEEDED:
                                                        logger.info(f"[{req_id}] (Worker) ✅ Recovery completed successfully (Quota cleared) after wait. Resuming.")
                                                        continue
                                                    
                                                    # Double check race condition after wait
                                                    time_since_rotation = time.time() - GlobalState.LAST_ROTATION_TIMESTAMP
                                                    if time_since_rotation < 10.0:
                                                        logger.info(f"[{req_id}] (Worker) 🛡️ Quota signal ignored after wait - Rotation completed {time_since_rotation:.2f}s ago.")
                                                        continue

                                                    # If still no recovery, THEN abort.
                                                    logger.critical(f"[{req_id}] (Worker) ⛔ Quota Exceeded and no recovery! Aborting worker wait.")
                                                    logger.critical(f"[{req_id}] (Worker) ⛔ Final State: Recovering={GlobalState.IS_RECOVERING}, Lock={GlobalState.AUTH_ROTATION_LOCK.is_set()}")
                                                    client_disconnected_early = True # Treat as early exit to skip button handling
                                                    if not completion_event.is_set():
                                                        completion_event.set()
                                                    break

                                            # Proactively check if client is disconnected
                                            is_connected = await _test_client_connection(req_id, http_request)
                                            if not is_connected:
                                                logger.info(f"[{req_id}] (Worker) ✅ Client disconnect detected during streaming, triggering done signal early")
                                                client_disconnected_early = True
                                                # Set completion_event immediately to end wait early
                                                if not completion_event.is_set():
                                                    completion_event.set()
                                                break
                                            await asyncio.sleep(0.3)  # More frequent check interval
                                        except Exception as e:
                                            logger.error(f"[{req_id}] (Worker) Enhanced disconnect monitor error: {e}")
                                            break

                                # Start enhanced disconnect monitoring
                                disconnect_monitor_task = asyncio.create_task(enhanced_disconnect_monitor())
                            else:
                                logger.error(f"[{req_id}] (Worker) Unknown completion event type: {type(completion_event)}")
                                client_disconnected_early = False
                        else:
                            # Non-streaming mode: Wait for processing completion and check for client disconnect
                            logger.info(f"[{req_id}] (Worker) Non-streaming mode, waiting for processing completion...")

                            client_disconnected_early = False

                            async def non_streaming_disconnect_monitor():
                                nonlocal client_disconnected_early
                                while not result_future.done():
                                    try:
                                        # [SHUTDOWN-09] Cooperative cancellation in non-stream monitor
                                        if GlobalState.IS_SHUTTING_DOWN.is_set():
                                            logger.info(f"[{req_id}] (Worker) 🚨 Shutdown detected in non-stream monitor. Cancelling future.")
                                            if not result_future.done():
                                                result_future.cancel()
                                            break

                                        # Proactively check if client is disconnected
                                        is_connected = await _test_client_connection(req_id, http_request)
                                        if not is_connected:
                                            logger.info(f"[{req_id}] (Worker) ✅ Client disconnect detected during non-streaming processing, cancelling")
                                            client_disconnected_early = True
                                            # Cancel result_future
                                            if not result_future.done():
                                                result_future.set_exception(HTTPException(status_code=499, detail=f"[{req_id}] Client disconnected during non-streaming processing"))
                                            break
                                        await asyncio.sleep(0.3)  # More frequent check interval
                                    except Exception as e:
                                        logger.error(f"[{req_id}] (Worker) Non-streaming disconnect monitor error: {e}")
                                        break

                            # Start non-streaming disconnect monitoring
                            disconnect_monitor_task = asyncio.create_task(non_streaming_disconnect_monitor())

                        # Wait for processing completion (streaming or non-streaming)
                        try:
                            if completion_event:
                                if isinstance(completion_event, dict):
                                    pass
                                elif hasattr(completion_event, 'wait'):
                                    # Streaming mode: Wait for completion_event
                                    from server import RESPONSE_COMPLETION_TIMEOUT
                                    await asyncio.wait_for(completion_event.wait(), timeout=RESPONSE_COMPLETION_TIMEOUT/1000 + 60)
                                    logger.info(f"[{req_id}] (Worker) ✅ Stream generator completion signal received. Client early disconnect: {client_disconnected_early}")
                            else:
                                # Non-streaming mode: Wait for result_future
                                from server import RESPONSE_COMPLETION_TIMEOUT
                                await asyncio.wait_for(asyncio.shield(result_future), timeout=RESPONSE_COMPLETION_TIMEOUT/1000 + 60)
                                logger.info(f"[{req_id}] (Worker) ✅ Non-streaming processing completed. Client early disconnect: {client_disconnected_early}")

                            # If client disconnected early, try clicking stop button to abort generation
                            if client_disconnected_early:
                                logger.info(f"[{req_id}] (Worker) Client disconnected early, attempting to stop generation...")
                                if submit_btn_loc:
                                    try:
                                        # [AUTO-01] Harden Stop Button Logic
                                        # Use try/except block to handle potential UI changes or detachments
                                        is_button_enabled = await submit_btn_loc.is_enabled(timeout=2000)
                                        if is_button_enabled:
                                            logger.info(f"[{req_id}] (Worker) Stop button found enabled, clicking to abort generation...")
                                            await submit_btn_loc.click(timeout=5000, force=True)
                                            logger.info(f"[{req_id}] (Worker) ✅ Stop button clicked.")
                                        else:
                                            logger.info(f"[{req_id}] (Worker) Stop button not enabled, no action needed.")
                                    except Exception as stop_err:
                                        logger.warning(f"[{req_id}] (Worker) Error trying to stop generation: {stop_err}")

                            if submit_btn_loc and client_disco_checker and completion_event and not client_disconnected_early:
                                    # Wait for send button disable to confirm stream response fully ended
                                    logger.info(f"[{req_id}] (Worker) Stream response completed, checking and handling send button status...")
                                    wait_timeout_ms = 30000  # 30 seconds
                                    try:
                                        from playwright.async_api import expect as expect_async
                                        from api_utils.request_processor import ClientDisconnectedError

                                        # Check client connection status
                                        client_disco_checker("Post-stream button status check - Pre-check: ")
                                        await asyncio.sleep(0.5)  # Give UI some time to update

                                        # Check if button is still enabled, if so click stop directly
                                        logger.info(f"[{req_id}] (Worker) Checking send button status...")
                                        try:
                                            # [AUTO-01] Harden Submit Button Logic
                                            is_button_enabled = await submit_btn_loc.is_enabled(timeout=2000)
                                            logger.info(f"[{req_id}] (Worker) Send button enabled status: {is_button_enabled}")

                                            if is_button_enabled:
                                                # Button still enabled after stream completion, click stop
                                                logger.info(f"[{req_id}] (Worker) Stream completed but button still enabled, clicking stop to end generation...")
                                                await submit_btn_loc.click(timeout=5000, force=True)
                                                logger.info(f"[{req_id}] (Worker) ✅ Send button click completed.")
                                            else:
                                                logger.info(f"[{req_id}] (Worker) Send button disabled, no click needed.")
                                        except Exception as button_check_err:
                                            logger.warning(f"[{req_id}] (Worker) Failed to check button status: {button_check_err}")

                                        # Wait for button to be finally disabled
                                        logger.info(f"[{req_id}] (Worker) Waiting for send button to be finally disabled...")
                                        await expect_async(submit_btn_loc).to_be_disabled(timeout=wait_timeout_ms)
                                        logger.info(f"[{req_id}] ✅ Send button disabled.")

                                    except Exception as e_pw_disabled:
                                        logger.warning(f"[{req_id}] ⚠️ Stream post-response button status handling timeout or error: {e_pw_disabled}")
                                        from api_utils.request_processor import save_error_snapshot
                                        await save_error_snapshot(f"stream_post_submit_button_handling_timeout_{req_id}")
                                    except ClientDisconnectedError:
                                        logger.info(f"[{req_id}] Client disconnected during stream post-response button status handling.")
                            elif completion_event and current_request_was_streaming:
                                logger.warning(f"[{req_id}] (Worker) Streaming request but submit_btn_loc or client_disco_checker missing. Skipping button disable wait.")

                        except asyncio.TimeoutError:
                            logger.warning(f"[{req_id}] (Worker) ⚠️ Processing completion wait timed out.")
                            if not result_future.done():
                                result_future.set_exception(processing_timeout(req_id, "Processing timed out waiting for completion."))
                        except Exception as ev_wait_err:
                            logger.error(f"[{req_id}] (Worker) ❌ Error waiting for completion: {ev_wait_err}")
                            if not result_future.done():
                                result_future.set_exception(server_error(req_id, f"Error waiting for completion: {ev_wait_err}"))
                        finally:
                            # Cleanup disconnect monitor task
                            if 'disconnect_monitor_task' in locals() and not disconnect_monitor_task.done():
                                disconnect_monitor_task.cancel()
                                try:
                                    await disconnect_monitor_task
                                except asyncio.CancelledError:
                                    pass

                    except QuotaExceededError as qe:
                        # Re-raise to be caught by the handler below which handles re-queueing
                        raise qe
                    except Exception as process_err:
                        logger.error(f"[{req_id}] (Worker) _process_request_refactored execution error: {process_err}")
                        if not result_future.done():
                            result_future.set_exception(server_error(req_id, f"Request processing error: {process_err}"))
            
            logger.info(f"[{req_id}] (Worker) Processing lock released.")

            # [GR-02] Post-Request Graceful Rotation Check
            # Must happen AFTER releasing the lock but BEFORE processing next request
            just_rotated = False
            if GlobalState.NEEDS_ROTATION:
                logger.info(f"[{req_id}] 🔄 Graceful Rotation Triggered after request completion.")
                # Get current model ID for smart rotation
                import server
                current_model_id = getattr(server, 'current_ai_studio_model_id', None)
                from browser_utils.auth_rotation import perform_auth_rotation
                rotation_success = await perform_auth_rotation(target_model_id=current_model_id)
                if rotation_success:
                    GlobalState.NEEDS_ROTATION = False
                    just_rotated = True
                    logger.info(f"[{req_id}] ✅ Graceful Rotation completed.")
                else:
                    logger.error(f"[{req_id}] ❌ Graceful Rotation failed. Flag remains set for next retry.")

            # Execute cleanup immediately after releasing lock
            try:
                # Clear stream queue cache
                from api_utils import clear_stream_queue
                await clear_stream_queue()

                # [FIX-03] Worker Cleanup Short-Circuit - Enhanced browser shutdown detection
                if GlobalState.IS_QUOTA_EXCEEDED:
                    logger.warning(f"[{req_id}] (Worker) ⛔ Quota Exceeded flag detected! Skipping chat history cleanup to allow immediate rotation.")
                elif just_rotated:
                    logger.info(f"[{req_id}] (Worker) 🔄 Just rotated credentials. Skipping chat history cleanup (session is fresh).")
                elif GlobalState.IS_SHUTTING_DOWN.is_set():
                    logger.warning(f"[{req_id}] (Worker) 🚨 Shutdown detected, skipping all browser operations.")
                elif submit_btn_loc and client_disco_checker:
                    # Enhanced browser availability check
                    from server import page_instance, is_page_ready, browser_instance
                    browser_available = (page_instance and is_page_ready and
                                       hasattr(page_instance, 'context') and
                                       page_instance.context is not None and
                                       browser_instance and browser_instance.is_connected())
                    
                    if browser_available:
                        try:
                            from browser_utils.page_controller import PageController
                            page_controller = PageController(page_instance, logger, req_id)
                            logger.info(f"[{req_id}] (Worker) Clearing chat history ({'streaming' if completion_event else 'non-streaming'} mode)...")
                            
                            # Use dummy checker to ensure cleanup is not affected by client disconnect
                            dummy_checker = lambda stage: False
                            
                            try:
                                await page_controller.clear_chat_history(dummy_checker)
                                logger.info(f"[{req_id}] (Worker) ✅ Chat history cleared.")
                            except Exception as clear_chat_err:
                                # Check if browser is still available before attempting recovery
                                if GlobalState.IS_SHUTTING_DOWN.is_set():
                                    logger.warning(f"[{req_id}] (Worker) 🚨 Shutdown detected during cleanup, skipping page reload recovery.")
                                else:
                                    # Double-check browser availability before reload attempt
                                    from server import browser_instance
                                    if browser_instance and browser_instance.is_connected():
                                        logger.warning(f"[{req_id}] (Worker) Attempting page reload to recover state...")
                                        try:
                                            await page_instance.reload()
                                            logger.info(f"[{req_id}] (Worker) ✅ Page reload successful.")
                                        except Exception as reload_err:
                                            logger.error(f"[{req_id}] (Worker) ❌ Page reload failed: {reload_err}")
                                    else:
                                        logger.warning(f"[{req_id}] (Worker) Browser no longer available during cleanup recovery, skipping reload.")
                        except Exception as controller_err:
                            logger.warning(f"[{req_id}] (Worker) PageController initialization failed: {controller_err}")
                    else:
                        logger.info(f"[{req_id}] (Worker) Skipping chat history cleanup: Browser unavailable or closed")

                else:
                    logger.info(f"[{req_id}] (Worker) Skipping chat history cleanup: Missing required params (submit_btn_loc: {bool(submit_btn_loc)}, client_disco_checker: {bool(client_disco_checker)})")
            except Exception as clear_err:
                logger.error(f"[{req_id}] (Worker) Error during cleanup: {clear_err}", exc_info=True)

            was_last_request_streaming = is_streaming_request
            last_request_completion_time = time.time()
            
        except asyncio.CancelledError:
            logger.info("--- Queue Worker Cancelled ---")
            if result_future and not result_future.done():
                result_future.cancel("Worker cancelled")
            break
        except QuotaExceededError as qe:
            logger.error(f"[{req_id}] ⛔ CRITICAL: {qe}")
            # [FINAL-FIX] If QuotaExceededError bubbles up here, it means it happened MID-PROCESSING.
            
            # 1. Check if client is still connected before re-queuing
            try:
                # Ensure we have the function available
                from api_utils.request_processor import _test_client_connection
                is_connected = await _test_client_connection(req_id, http_request)
            except Exception:
                is_connected = False # Assume disconnected on error to be safe
                
            if not is_connected:
                logger.info(f"[{req_id}] Client disconnected during Quota Exception. Dropping request (NOT re-queuing).")
                if result_future and not result_future.done():
                    result_future.set_exception(HTTPException(status_code=499, detail="Client disconnected during Quota Error"))
            
            # 2. Only Re-queue if connected
            elif result_future and not result_future.done():
                logger.info(f"[{req_id}] 🔄 Re-queueing failed request due to Quota Exceeded mid-processing (Client Connected)...")
                try:
                    request_queue.put_nowait(request_item)
                    # IMPORTANT: Do NOT set exception on future, keep it pending!
                    # The client is still connected and waiting on this future.
                    # By putting it back in queue, it will be picked up again by worker loop
                    # which will then see GlobalState.IS_QUOTA_EXCEEDED and hold it until rotation.
                except Exception as requeue_err:
                    logger.error(f"[{req_id}] Failed to re-queue mid-processing request: {requeue_err}")
                    result_future.set_exception(HTTPException(status_code=429, detail="Quota exceeded. Please retry."))
            
        except Exception as e:
            logger.error(f"[{req_id}] (Worker) ❌ Unexpected error processing request: {e}", exc_info=True)
            if result_future and not result_future.done():
                result_future.set_exception(server_error(req_id, f"Internal Server Error: {e}"))
        finally:
            if request_item:
                request_queue.task_done()
    
    logger.info("--- Queue Worker Stopped ---")