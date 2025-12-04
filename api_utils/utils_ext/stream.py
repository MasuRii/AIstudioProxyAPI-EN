import asyncio
import json
import re
import time
from typing import Any, AsyncGenerator, Optional, Callable

from logging_utils import set_request_id

# [REFAC-01] Structural Boundary Pattern
# Detects the inception of an XML tool block based on structure:
# 1. Anchor: Start of string (^) or Newline (\n)
# 2. Whitespace: Any indentation (\s*)
# 3. Optional Fence: ``` followed by any language tag (alphanumeric) or empty, plus whitespace
# 4. Trigger: XML Tag Start (<tagname) followed by Space (for attributes) or > (immediate close)
TOOL_STRUCTURE_PATTERN = re.compile(r'(?:^|\n)\s*(?:```[a-zA-Z0-9]*\s*)?<[a-zA-Z0-9_\-]+(?:\s|>)')

async def use_stream_response(req_id: str, timeout: float = 5.0, silence_threshold: float = 60.0, page=None, check_client_disconnected: Optional[Callable] = None, stream_start_time: float = 0.0, enable_silence_detection: bool = True) -> AsyncGenerator[Any, None]:
    """Enhanced stream response handler with UI-based generation active checks.
    
    Args:
        req_id: Request identifier for logging
        timeout: TTFB timeout in seconds
        silence_threshold: Dynamic silence detection threshold in seconds (how long to wait without data before assuming stream is dead)
        page: Playwright page instance for UI state checks
        check_client_disconnected: Optional callback to check if client disconnected
        stream_start_time: Timestamp when this specific stream request was initiated. Used to filter out stale queue data.
        enable_silence_detection: Whether to enable the silence watchdog that terminates streams if no data is received for a set duration.
    """
    from server import STREAM_QUEUE, logger
    from models import ClientDisconnectedError, QuotaExceededError
    from config.global_state import GlobalState
    from config import (
        SCROLL_CONTAINER_SELECTOR,
        CHAT_SESSION_CONTENT_SELECTOR,
        LAST_CHAT_TURN_SELECTOR,
        UI_GENERATION_WAIT_TIMEOUT_MS,
        SILENCE_TIMEOUT_MS,
    )
    import queue

    from api_utils.server_state import state
    from server import STREAM_QUEUE, logger

    set_request_id(req_id)
    if STREAM_QUEUE is None:
        logger.warning(f"[{req_id}] STREAM_QUEUE is None, cannot use stream response")
        return
        
    # Import PageController for DOM fallback
    from browser_utils.page_controller import PageController

    if stream_start_time == 0.0:
        stream_start_time = time.time() - 10.0 # Fallback: 10s buffer if not provided

    logger.info(f"[{req_id}] Starting stream response (TTFB Timeout: {timeout:.2f}s, Silence Threshold: {silence_threshold:.2f}s, Max Retries: {max_empty_retries}, Start Time: {stream_start_time})")

    accumulated_body = ""
    accumulated_reason_len = 0
    total_reason_processed = 0
    total_body_processed = 0
    boundary_transitions = 0
    boundary_buffer = ""  # [REFAC-03] Sliding window for boundary detection
    
    # [REFAC-04] Internal Accumulators for robustness
    # We maintain full state here to ensure downstream consumers (like response_generators)
    # receive the Cumulative data they expect, regardless of whether upstream sends Deltas or Cumulative.
    acc_reason_state = ""
    acc_body_state = ""
    
    # [FIX-11] Flag to track if we have forcefully switched to body mode
    force_body_mode = False
    
    # Track where the split happened in the accumulated reason stream
    split_index = -1

    # Enhanced timeout settings for thinking models
    empty_count = 0
    initial_wait_limit = int(timeout * 10)  # TTFB timeout in ticks (0.1s each)
    
    # [STREAM-FIX] Dynamic max_empty_retries based on silence_threshold
    # Convert silence_threshold (seconds) to ticks (0.1s each)
    # Ensure it's at least as long as initial_wait_limit to prevent general timeout from undercutting TTFB
    silence_wait_limit = int(silence_threshold * 10)
    max_empty_retries = max(silence_wait_limit, initial_wait_limit)
    
    # [STREAM-FIX] Hard timeout limit (3x the dynamic timeout) to prevent infinite zombie loops
    hard_timeout_limit = int(timeout * 10 * 3)
    
    data_received = False
    has_content = False
    received_items_count = 0
    stale_done_ignored = False
    last_ui_check_time = 0
    # [CONF-01] Use configured interval instead of hardcoded 30
    ui_check_interval = int(UI_GENERATION_WAIT_TIMEOUT_MS / 100)  # Check UI state based on config (loop is 0.1s)
    if ui_check_interval <= 0: ui_check_interval = 1
    
    # [LOGIC-FIX] Last Packet Watchdog for silence detection
    last_packet_time = time.time()
    silence_detection_threshold = silence_threshold  # Use passed dynamic silence threshold
    min_items_before_silence_check = 10  # Only check silence after receiving some data
    
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
        except Exception as e:
            # [FIX-ZOMBIE] If target closed, definitely not generating
            if "Target closed" in str(e) or "Connection closed" in str(e):
                return False
            # If UI check fails, assume generation is not active
            return False

    try:
        while True:
            # [CONCURRENCY-FIX] Enhanced Zombie Stream Check with Graceful Termination
            if GlobalState.CURRENT_STREAM_REQ_ID and GlobalState.CURRENT_STREAM_REQ_ID != req_id:
                logger.warning(f"[{req_id}] 🧟 Zombie Stream detected in wait loop (Active: {GlobalState.CURRENT_STREAM_REQ_ID}). Aborting gracefully.")
                
                # Add a small delay to allow the old stream to clean up properly
                await asyncio.sleep(0.1)
                
                # Send termination signal and yield final state
                yield {"done": True, "reason": "zombie_stream_aborted", "body": "", "function": []}
                
                # Force immediate return to avoid any further processing
                return

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
            if GlobalState.IS_QUOTA_EXCEEDED and not GlobalState.IS_RECOVERING:
                 # [ID-03] Wait briefly to see if recovery is initiated (by Queue Worker or other trigger)
                 logger.warning(f"[{req_id}] ⛔ Quota detected during wait loop. Pausing briefly to check for recovery...")
                 try:
                     # Wait up to 2 seconds for recovery to start
                     start_wait = time.time()
                     while time.time() - start_wait < 2.0:
                         if GlobalState.IS_RECOVERING:
                             break
                         await asyncio.sleep(0.2)
                 except Exception:
                     pass
                 
                 # [FIX-BRITTLE] Check if recovery is active OR if quota is no longer exceeded (success)
                 if GlobalState.IS_RECOVERING:
                     logger.info(f"[{req_id}] 🔄 Recovery mode detected. Continuing wait loop (Holding Pattern).")
                 elif not GlobalState.IS_QUOTA_EXCEEDED:
                     logger.info(f"[{req_id}] ✅ Recovery completed successfully (Quota cleared). Resuming stream.")
                     # Loop back, the condition at top of loop will now pass
                 else:
                     # [FIX-HOLD] If Quota exceeded but recovery not yet started, DO NOT ABORT.
                     # The worker needs time to loop around and pick up the rotation.
                     logger.warning(f"[{req_id}] ⛔ Quota exceeded, waiting for recovery initiation (Infinite Hold)...")
                     await asyncio.sleep(1.0)
                     continue
 
             # [FIX-SHUTDOWN] Check for Global Shutdown
            if GlobalState.IS_SHUTTING_DOWN.is_set():
                logger.warning(f"[{req_id}] 🛑 Global Shutdown detected during wait loop. Aborting stream.")
                yield {"done": True, "reason": "global_shutdown", "body": "", "function": []}
                return

            try:
                data = STREAM_QUEUE.get_nowait()
                # [SYNC-FIX] CRITICAL: DONE signal forces immediate exit, ignoring all other conditions
                if data is None:
                    logger.info(f"[{req_id}] 🔴 CRITICAL: Received stream termination signal (None). Forcing immediate exit.")
                    break
                
                # Check for explicit done signal in dictionary format
                if isinstance(data, dict) and data.get("done") is True:
                    logger.info(f"[{req_id}] ✅ Explicit dictionary DONE signal received. Treating as EOF.")
                    # Ensure we yield this final state to flush buffer
                    yield data
                    break

                empty_count = 0
                data_received = True
                received_items_count += 1
                # [LOGIC-FIX] Update last packet time for silence detection
                last_packet_time = time.time()
                logger.debug(f"[{req_id}] Received stream data [#{received_items_count}]: {type(data)} - {str(data)[:200]}...")

                # [FIX-TIMESTAMP] Handle wrapped data with timestamp
                actual_data = data
                data_ts = 0.0
                
                if isinstance(data, str):
                    try:
                        parsed_wrapper = json.loads(data)
                        # Check if it's the new wrapped format: {"ts": float, "data": ...}
                        if isinstance(parsed_wrapper, dict) and "ts" in parsed_wrapper and "data" in parsed_wrapper:
                            data_ts = parsed_wrapper["ts"]
                            # Filter out stale data from previous requests
                            if data_ts < stream_start_time:
                                logger.warning(f"[{req_id}] 🗑️ Ignoring stale stream data (Timestamp: {data_ts} < Start: {stream_start_time})")
                                continue
                            actual_data = parsed_wrapper["data"]
                        else:
                            # Legacy format (direct data) - accept but warn? Or just accept.
                            actual_data = parsed_wrapper
                    except json.JSONDecodeError:
                        pass # Handle as raw string below if needed

                # Process the actual data payload
                if isinstance(actual_data, dict):
                    # It was already a dict (from wrapper or raw dict in queue)
                    parsed_data = actual_data
                    
                    # [REFAC-05] Robust Accumulation & Switching Logic (Dict)
                    p_reason = parsed_data.get("reason", "")
                    p_body = parsed_data.get("body", "")
                    
                    # 1. Update Accumulators
                    if p_reason and acc_reason_state and p_reason.startswith(acc_reason_state):
                            acc_reason_state = p_reason
                            new_reason_delta = p_reason[len(acc_reason_state):]
                    else:
                            acc_reason_state += p_reason
                            new_reason_delta = p_reason
                            
                    if p_body and acc_body_state and p_body.startswith(acc_body_state):
                            acc_body_state = p_body
                    else:
                            acc_body_state += p_body

                    # 2. Apply Boundary Logic
                    if force_body_mode:
                        thought_part = acc_reason_state[:split_index]
                        overflow_tool_part = acc_reason_state[split_index:]
                        
                        parsed_data["reason"] = thought_part
                        parsed_data["body"] = acc_body_state + overflow_tool_part
                    else:
                        text_to_check = boundary_buffer + new_reason_delta
                        match = TOOL_STRUCTURE_PATTERN.search(text_to_check)
                        
                        if match:
                            offset = len(acc_reason_state) - len(text_to_check)
                            absolute_split_index = offset + match.start()
                            
                            split_index = absolute_split_index
                            force_body_mode = True
                            boundary_transitions += 1
                            
                            thought_part = acc_reason_state[:split_index]
                            overflow_tool_part = acc_reason_state[split_index:]
                            
                            parsed_data["reason"] = thought_part
                            parsed_data["body"] = acc_body_state + overflow_tool_part
                            logger.info(f"[{req_id}] ✂️ Dict Boundary Split Applied.")
                        else:
                            parsed_data["reason"] = acc_reason_state
                            parsed_data["body"] = acc_body_state
                            boundary_buffer = (boundary_buffer + new_reason_delta)[-100:]

                    body = parsed_data.get("body", "")
                    reason = parsed_data.get("reason", "")
                    
                    # Update totals with detailed logging
                    body_increment = len(body)
                    reason_increment = len(reason)
                    accumulated_body += body
                    accumulated_reason_len += len(reason)
                    total_body_processed += body_increment
                    total_reason_processed += reason_increment
                    
                    if body or reason:
                        has_content = True
                    stale_done_ignored = False
                    
                    # [FIX-QUOTA-HOLD] Check quota BEFORE yielding done signal to prevent "Backfill" in response_generators
                    if parsed_data.get("done") is True:
                        if GlobalState.IS_QUOTA_EXCEEDED or GlobalState.IS_RECOVERING:
                             logger.info(f"[{req_id}] 🛡️ Quota/Recovery active: Ignoring DONE signal. Holding stream open.")
                             continue

                        # [ZOMBIE-PRE-CHECK] Check for post-rotation zombie state BEFORE yielding
                        just_rotated = (time.time() - GlobalState.LAST_ROTATION_TIMESTAMP < 15.0)
                        recently_recovered = (time.time() - GlobalState.LAST_ROTATION_TIMESTAMP < 30.0)
                        
                        post_rotation_zombie_state = (
                            not has_content and
                            received_items_count == 1 and
                            not stale_done_ignored and
                            not GlobalState.IS_QUOTA_EXCEEDED and
                            (just_rotated or recently_recovered)
                        )

                        if post_rotation_zombie_state:
                             logger.info(f"[{req_id}] 🔄 Post-rotation empty DONE detected (Rotation: {just_rotated}, Recent: {recently_recovered}). Ignoring as stale zombie packet (Pre-Yield).")
                             stale_done_ignored = True
                             continue

                    yield parsed_data
                    
                    # [SYNC-FIX] CRITICAL: Dict DONE signal forces immediate exit, ignoring UI state
                    if parsed_data.get("done") is True:
                        logger.info(f"[{req_id}] ✅ [Latch] Dict DONE received. Body={len(body)}, Reason={len(reason)}. Forcing stream completion (Intentional).")
                        
                        # [FIX-06] Thinking-to-Answer Handover Protocol (Copied from string branch)
                        if accumulated_reason_len > 0 and len(accumulated_body) == 0:
                             logger.info(f"[{req_id}] ⚠️ [Dict Path] Thinking-Only response detected. Starting DOM Body-Wait protocol...")
                             try:
                                if page:
                                    pc = PageController(page, logger, req_id)
                                    wait_attempts = 20
                                    dom_body_found = False
                                    for wait_i in range(wait_attempts):
                                        await asyncio.sleep(0.5)
                                        dom_text = await pc.get_body_text_only_from_dom()
                                        if dom_text and len(dom_text.strip()) > 0:
                                            logger.info(f"[{req_id}] ✅ [Dict Path] DOM captured body: {len(dom_text)} chars")
                                            yield {"body": dom_text, "reason": "", "done": False}
                                            dom_body_found = True
                                            break
                                    if not dom_body_found:
                                        logger.warning(f"[{req_id}] ⚠️ [Dict Path] DOM wait timed out.")
                             except Exception as e:
                                 logger.error(f"[{req_id}] ❌ [Dict Path] DOM Wait Error: {e}")

                        # [FIX-QUOTA-STALL] If Quota is exceeded, this is a legitimate fast-fail, not stale data.
                        # [FIX-ROTATION-STALL] Also check if we just rotated auth (allow empty done).
                        # [ZOMBIE-FIX] Enhanced detection for post-rotation scenarios
                        just_rotated = (time.time() - GlobalState.LAST_ROTATION_TIMESTAMP < 15.0)
                        recently_recovered = (time.time() - GlobalState.LAST_ROTATION_TIMESTAMP < 30.0)
                        
                        # Check if we might be in a post-rotation zombie state
                        # This handles the case where quota exceeded triggered rotation, 
                        # rotation completed successfully, but stream handler receives empty DONE
                        post_rotation_zombie_state = (
                            not has_content and 
                            received_items_count == 1 and 
                            not stale_done_ignored and 
                            not GlobalState.IS_QUOTA_EXCEEDED and 
                            (just_rotated or recently_recovered)
                        )
                        
                        if post_rotation_zombie_state:
                            logger.info(f"[{req_id}] 🔄 Post-rotation empty DONE detected (Rotation: {just_rotated}, Recent: {recently_recovered}). Ignoring as stale zombie packet.")
                            stale_done_ignored = True
                            continue
                        elif not has_content and received_items_count == 1 and not stale_done_ignored and not GlobalState.IS_QUOTA_EXCEEDED:
                            # Enhanced check: if rotation happened recently, treat as zombie even if just_rotated is False
                            # This handles edge cases where timestamp tracking might be slightly off
                            time_since_rotation = time.time() - GlobalState.LAST_ROTATION_TIMESTAMP
                            is_recent_rotation = time_since_rotation < 45.0  # Extended window
                            
                            if is_recent_rotation:
                                logger.info(f"[{req_id}] 🔄 Recent rotation detected ({time_since_rotation:.2f}s ago). Treating empty DONE as stale zombie packet.")
                                stale_done_ignored = True
                                continue
                            else:
                                logger.warning(f"[{req_id}] ⚠️ Received done=True but no content, and this is the first item! Possibly stale data, ignoring and waiting...")
                                stale_done_ignored = True
                                continue
                        break
                    else:
                        stale_done_ignored = False
                        
                elif isinstance(actual_data, str):
                    # Fallback for string data that wasn't JSON or wasn't handled above
                    # (This branch is mostly legacy/fallback now as everything comes as dict or wrapped dict)
                    pass

                # Removed the large duplicate 'if isinstance(data, str)' block as we handle it via parsing above
                # and treating result as dict.
                
                continue # Loop back for next item

                # [Legacy Code Block - Kept for reference but unreachable due to 'continue' above and logic refactor]
                # The following block was the original string handling logic.
                # We have integrated it into the unified flow above.
                
                if isinstance(data, str):
                    try:
                        parsed_data = json.loads(data)
                        p_reason = parsed_data.get("reason", "")
                        p_body = parsed_data.get("body", "")
                        
                        # 1. Update Accumulators (Handle Delta vs Cumulative Input)
                        # Detect if input is cumulative (starts with current state) or delta
                        if p_reason and acc_reason_state and p_reason.startswith(acc_reason_state):
                             # Input is cumulative, just update state
                             acc_reason_state = p_reason
                             new_reason_delta = p_reason[len(acc_reason_state):] # effective delta for buffer
                        else:
                             # Input is delta, append to state
                             acc_reason_state += p_reason
                             new_reason_delta = p_reason
                             
                        if p_body and acc_body_state and p_body.startswith(acc_body_state):
                             acc_body_state = p_body
                        else:
                             acc_body_state += p_body

                        # 2. Apply Boundary Logic
                        if force_body_mode:
                            # We have already split.
                            # reason = accumulated thought up to split
                            # body = accumulated body + (accumulated reason - thought)
                            
                            thought_part = acc_reason_state[:split_index]
                            overflow_tool_part = acc_reason_state[split_index:]
                            
                            parsed_data["reason"] = thought_part
                            parsed_data["body"] = acc_body_state + overflow_tool_part
                            
                        else:
                            # Check for boundary in the *new* content (plus context)
                            # We use boundary_buffer (last 100 chars) + new_reason_delta
                            text_to_check = boundary_buffer + new_reason_delta
                            match = TOOL_STRUCTURE_PATTERN.search(text_to_check)
                            
                            if match:
                                # Found the boundary!
                                logger.info(f"[{req_id}] 🔍 Detected Tool Structure: {match.group(0).strip()!r}")
                                
                                # Calculate absolute split index in acc_reason_state
                                # match.start() is relative to text_to_check
                                # text_to_check start corresponds to (len(acc_reason_state) - len(text_to_check))
                                offset = len(acc_reason_state) - len(text_to_check)
                                absolute_split_index = offset + match.start()
                                
                                split_index = absolute_split_index
                                force_body_mode = True
                                boundary_transitions += 1
                                
                                # Apply split immediately
                                thought_part = acc_reason_state[:split_index]
                                overflow_tool_part = acc_reason_state[split_index:]
                                
                                parsed_data["reason"] = thought_part
                                parsed_data["body"] = acc_body_state + overflow_tool_part
                                
                                logger.info(f"[{req_id}] ✂️ Boundary Split Applied. Thought len: {len(thought_part)}")
                            else:
                                # No match, pass through accumulated states as is
                                parsed_data["reason"] = acc_reason_state
                                parsed_data["body"] = acc_body_state
                                
                                # Update sliding window buffer for next check
                                boundary_buffer = (boundary_buffer + new_reason_delta)[-100:]

                        # [SYNC-FIX] CRITICAL: JSON DONE signal forces immediate exit, ignoring UI state
                        if parsed_data.get("done") is True:
                            body = parsed_data.get("body", "")
                            reason = parsed_data.get("reason", "")
                            
                            # Update totals with detailed logging
                            body_increment = len(body)
                            reason_increment = len(reason)
                            accumulated_body += body
                            accumulated_reason_len += len(reason)
                            total_body_processed += body_increment
                            total_reason_processed += reason_increment
                            boundary_transitions += 1 if force_body_mode else 0
                            
                            if body or reason:
                                has_content = True
                            
                            logger.info(f"[{req_id}] 🔴 CRITICAL: JSON DONE received. Body={len(body)}, Reason={len(reason)}. Forcing immediate stream completion.")
                            
                            # [FIX-06] Thinking-to-Answer Handover Protocol
                            # Detect if only thinking process was output without body (Thinking > 0, Body == 0)
                            if accumulated_reason_len > 0 and len(accumulated_body) == 0:
                                logger.info(f"[{req_id}] ⚠️ Thinking-Only response detected (Total Reason: {accumulated_reason_len}, Body: 0). Starting DOM Body-Wait protocol...")
                                
                                try:
                                    if page:
                                        pc = PageController(page, logger, req_id)
                                        # Try waiting for body to appear, max 10 seconds (20 * 0.5s)
                                        wait_attempts = 20
                                        dom_body_found = False
                                        
                                        for wait_i in range(wait_attempts):
                                            await asyncio.sleep(0.5)
                                            # Use newly added get_body_text_only_from_dom method
                                            dom_text = await pc.get_body_text_only_from_dom()
                                            
                                            if dom_text and len(dom_text.strip()) > 0:
                                                logger.info(f"[{req_id}] ✅ Captured body via DOM on attempt {wait_i+1}: {len(dom_text)} chars")
                                                
                                                # [Sanity Check] Prevent Duplication
                                                # If stream sent partial content (checking for robustness)
                                                final_text_to_yield = dom_text
                                                if len(accumulated_body) > 0:
                                                    if dom_text.startswith(accumulated_body):
                                                        final_text_to_yield = dom_text[len(accumulated_body):]
                                                        logger.info(f"[{req_id}] Deduplication: Removed {len(accumulated_body)} sent chars")
                                                
                                                if final_text_to_yield:
                                                    # Construct a new body chunk
                                                    new_chunk = {
                                                        "body": final_text_to_yield,
                                                        "reason": "",
                                                        "done": False
                                                    }
                                                    yield new_chunk
                                                    accumulated_body += final_text_to_yield
                                                    total_body_processed += len(final_text_to_yield)
                                                    dom_body_found = True
                                                    break
                                        
                                        if not dom_body_found:
                                            logger.warning(f"[{req_id}] ⚠️ DOM wait timed out, still no body. Executing Fallback (copying thinking content or error prompt).")
                                    else:
                                        logger.warning(f"[{req_id}] ⚠️ Cannot execute DOM Wait (Page object is None).")
                                except Exception as dom_wait_err:
                                    logger.error(f"[{req_id}] ❌ DOM Body-Wait Protocol Error: {dom_wait_err}")

                            # [FIX-QUOTA-STALL] If Quota is exceeded, this is a legitimate fast-fail, not stale data.
                            # [FIX-ROTATION-STALL] Also check if we just rotated auth.
                            # [ZOMBIE-FIX] Enhanced detection for post-rotation scenarios
                            just_rotated = (time.time() - GlobalState.LAST_ROTATION_TIMESTAMP < 15.0)
                            recently_recovered = (time.time() - GlobalState.LAST_ROTATION_TIMESTAMP < 30.0)
                            
                            # Check if we might be in a post-rotation zombie state
                            # This handles the case where quota exceeded triggered rotation, 
                            # rotation completed successfully, but stream handler receives empty DONE
                            post_rotation_zombie_state = (
                                not has_content and 
                                received_items_count == 1 and 
                                not stale_done_ignored and 
                                not GlobalState.IS_QUOTA_EXCEEDED and 
                                (just_rotated or recently_recovered)
                            )
                            
                            if post_rotation_zombie_state:
                                logger.info(f"[{req_id}] 🔄 Post-rotation empty DONE detected (Rotation: {just_rotated}, Recent: {recently_recovered}). Ignoring as stale zombie packet.")
                                stale_done_ignored = True
                                continue
                            elif not has_content and received_items_count == 1 and not stale_done_ignored and not GlobalState.IS_QUOTA_EXCEEDED:
                                # Enhanced check: if rotation happened recently, treat as zombie even if just_rotated is False
                                # This handles edge cases where timestamp tracking might be slightly off
                                time_since_rotation = time.time() - GlobalState.LAST_ROTATION_TIMESTAMP
                                is_recent_rotation = time_since_rotation < 45.0  # Extended window
                                
                                if is_recent_rotation:
                                    logger.info(f"[{req_id}] 🔄 Recent rotation detected ({time_since_rotation:.2f}s ago). Treating empty DONE as stale zombie packet.")
                                    stale_done_ignored = True
                                    continue
                                else:
                                    logger.warning(f"[{req_id}] ⚠️ Received done=True but no content, and this is the first item! Possibly stale data, ignoring and waiting...")
                                    stale_done_ignored = True
                                    continue
                            yield parsed_data
                            break
                        else:
                            body = parsed_data.get("body", "")
                            reason = parsed_data.get("reason", "")
                            
                            # Update totals with detailed logging
                            body_increment = len(body)
                            reason_increment = len(reason)
                            accumulated_body += body
                            accumulated_reason_len += len(reason)
                            total_body_processed += body_increment
                            total_reason_processed += reason_increment
                            
                            if body or reason:
                                has_content = True
                            stale_done_ignored = False
                            
                            # Log significant content updates
                            if body_increment > 0 or reason_increment > 0:
                                logger.debug(f"[{req_id}] 📝 Data Increment: Body +{body_increment}, Reason +{reason_increment}, State: ForceBody={force_body_mode}")
                            
                            yield parsed_data
                    except json.JSONDecodeError:
                        logger.debug(f"[{req_id}] Returning non-JSON string data")
                        has_content = True
                        stale_done_ignored = False
                        yield data
                else:
                    # Handle Dict data with enhanced boundary logic
                    if isinstance(data, dict):
                        p_reason = data.get("reason", "")
                        p_body = data.get("body", "")
                        
                        # [REFAC-05] Robust Accumulation & Switching Logic (Dict)
                        p_reason = data.get("reason", "")
                        p_body = data.get("body", "")
                        
                        # 1. Update Accumulators
                        if p_reason and acc_reason_state and p_reason.startswith(acc_reason_state):
                             acc_reason_state = p_reason
                             new_reason_delta = p_reason[len(acc_reason_state):]
                        else:
                             acc_reason_state += p_reason
                             new_reason_delta = p_reason
                             
                        if p_body and acc_body_state and p_body.startswith(acc_body_state):
                             acc_body_state = p_body
                        else:
                             acc_body_state += p_body

                        # 2. Apply Boundary Logic
                        if force_body_mode:
                            thought_part = acc_reason_state[:split_index]
                            overflow_tool_part = acc_reason_state[split_index:]
                            
                            data["reason"] = thought_part
                            data["body"] = acc_body_state + overflow_tool_part
                        else:
                            text_to_check = boundary_buffer + new_reason_delta
                            match = TOOL_STRUCTURE_PATTERN.search(text_to_check)
                            
                            if match:
                                offset = len(acc_reason_state) - len(text_to_check)
                                absolute_split_index = offset + match.start()
                                
                                split_index = absolute_split_index
                                force_body_mode = True
                                boundary_transitions += 1
                                
                                thought_part = acc_reason_state[:split_index]
                                overflow_tool_part = acc_reason_state[split_index:]
                                
                                data["reason"] = thought_part
                                data["body"] = acc_body_state + overflow_tool_part
                                logger.info(f"[{req_id}] ✂️ Dict Boundary Split Applied.")
                            else:
                                data["reason"] = acc_reason_state
                                data["body"] = acc_body_state
                                boundary_buffer = (boundary_buffer + new_reason_delta)[-100:]

                        body = data.get("body", "")
                        reason = data.get("reason", "")
                        if body or reason:
                            has_content = True
                        
                        # [FIX-QUOTA-HOLD] Check quota BEFORE yielding done signal
                        if data.get("done") is True:
                            if GlobalState.IS_QUOTA_EXCEEDED or GlobalState.IS_RECOVERING:
                                 logger.info(f"[{req_id}] 🛡️ Quota/Recovery active: Ignoring DONE signal. Holding stream open.")
                                 continue

                        yield data
                        
                        # [SYNC-FIX] CRITICAL: Dict DONE signal forces immediate exit, ignoring UI state
                        if data.get("done") is True:
                            logger.info(f"[{req_id}] ✅ [Latch] Dict DONE received. Body={len(body)}, Reason={len(reason)}. Forcing stream completion (Intentional).")
                            # [FIX-QUOTA-STALL] If Quota is exceeded, this is a legitimate fast-fail, not stale data.
                            # [FIX-ROTATION-STALL] Also check if we just rotated auth.
                            # [ZOMBIE-FIX] Enhanced detection for post-rotation scenarios
                            just_rotated = (time.time() - GlobalState.LAST_ROTATION_TIMESTAMP < 15.0)
                            recently_recovered = (time.time() - GlobalState.LAST_ROTATION_TIMESTAMP < 30.0)
                            
                            # Check if we might be in a post-rotation zombie state
                            # This handles the case where quota exceeded triggered rotation, 
                            # rotation completed successfully, but stream handler receives empty DONE
                            post_rotation_zombie_state = (
                                not has_content and 
                                received_items_count == 1 and 
                                not stale_done_ignored and 
                                not GlobalState.IS_QUOTA_EXCEEDED and 
                                (just_rotated or recently_recovered)
                            )
                            
                            if post_rotation_zombie_state:
                                logger.info(f"[{req_id}] 🔄 Post-rotation empty DONE detected (Rotation: {just_rotated}, Recent: {recently_recovered}). Ignoring as stale zombie packet.")
                                stale_done_ignored = True
                                continue
                            elif not has_content and received_items_count == 1 and not stale_done_ignored and not GlobalState.IS_QUOTA_EXCEEDED:
                                # Enhanced check: if rotation happened recently, treat as zombie even if just_rotated is False
                                # This handles edge cases where timestamp tracking might be slightly off
                                time_since_rotation = time.time() - GlobalState.LAST_ROTATION_TIMESTAMP
                                is_recent_rotation = time_since_rotation < 45.0  # Extended window
                                
                                if is_recent_rotation:
                                    logger.info(f"[{req_id}] 🔄 Recent rotation detected ({time_since_rotation:.2f}s ago). Treating empty DONE as stale zombie packet.")
                                    stale_done_ignored = True
                                    continue
                                else:
                                    logger.warning(f"[{req_id}] ⚠️ Received done=True but no content, and this is the first item! Possibly stale data, ignoring and waiting...")
                                    stale_done_ignored = True
                                    continue
                            break
                        else:
                            stale_done_ignored = False
            except (queue.Empty, asyncio.QueueEmpty):
                empty_count += 1

                # [LOGIC-FIX] Silence Detection: Check if stream has been silent for too long
                if (enable_silence_detection and
                    received_items_count >= min_items_before_silence_check and
                    time.time() - last_packet_time > silence_detection_threshold):
                    logger.info(f"[{req_id}] 🔇 Stream silence detected ({silence_detection_threshold}s). Assuming generation complete.")
                    yield {"done": True, "reason": "silence_detected", "body": "", "function": []}
                    return

                # Check for disconnect during wait
                if check_client_disconnected:
                    try:
                        check_client_disconnected(f"Stream Queue Wait ({req_id})")
                    except ClientDisconnectedError:
                        logger.warning(f"[{req_id}] Client disconnected during stream queue wait.")
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

                # [STREAM-FIX] Smart Timeout Logic: Distinguish between TTFB Phase and Streaming Phase
                # Determine which timeout limit to use based on whether we've received data
                effective_timeout_limit = initial_wait_limit if received_items_count == 0 else max_empty_retries
                
                if empty_count >= effective_timeout_limit:
                    # [ID-03] Dynamic Timeout Extension during Recovery
                    if GlobalState.IS_RECOVERING:
                        logger.info(f"[{req_id}] ⏳ Stream timeout reached, but system is RECOVERING. Extending wait...")
                        empty_count = 0 # Reset counter to give more time
                        continue

                    # [STREAM-FIX] Restore UI Trust ("Thinking" Fix)
                    # Check if UI reports active generation
                    is_thinking = await check_ui_generation_active()
                    
                    if is_thinking and empty_count < hard_timeout_limit:
                        # UI reports active generation and we haven't hit hard limit yet
                        # "Snooze" the timeout by resetting counter
                        logger.warning(f"[{req_id}] ⏰ Timeout reached ({empty_count}/{effective_timeout_limit}) but UI active. Snoozing timeout (Hard limit: {hard_timeout_limit})...")
                        empty_count = max(0, empty_count - int(effective_timeout_limit * 0.5))  # Reduce by 50% instead of full reset
                        continue
                    elif empty_count >= hard_timeout_limit:
                        # Hit hard timeout limit - force termination even if UI is active
                        logger.error(f"[{req_id}] 🚨 HARD TIMEOUT REACHED ({hard_timeout_limit} ticks)! Forcing stream completion despite UI state.")
                        yield {"done": True, "reason": "hard_timeout", "body": "", "function": []}
                        return
                    else:
                        # Timeout reached and UI is not active
                        logger.warning(f"[{req_id}] ⏰ Stream timeout reached ({empty_count}/{effective_timeout_limit}). UI not active. Ending stream.")
                    
                    if not data_received:
                        logger.error(f"[{req_id}] Stream timeout: no data received, likely auxiliary stream failed")
                    yield {"done": True, "reason": "internal_timeout", "body": "", "function": []}
                    return

                # Periodic logging and UI checks
                if empty_count % 50 == 0:
                    elapsed_seconds = empty_count * 0.1
                    logger.info(f"[{req_id}] Waiting for stream data... ({empty_count}/{max_empty_retries}, Received:{received_items_count} items, Elapsed:{elapsed_seconds:.1f}s)")
                
                # UI-based generation check every 3 seconds
                if empty_count - last_ui_check_time >= ui_check_interval:
                    ui_generation_active = await check_ui_generation_active()
                    last_ui_check_time = empty_count
                    
                    if ui_generation_active:
                        logger.info(f"[{req_id}] UI detected model is still generating, continuing wait... (Waited {empty_count * 0.1:.1f}s)")
                    else:
                        logger.debug(f"[{req_id}] UI detected model is NOT generating (Waited {empty_count * 0.1:.1f}s)")

                await asyncio.sleep(0.1)
                continue
    except asyncio.CancelledError:
        raise
    except Exception as e:
        if isinstance(e, ClientDisconnectedError):
             logger.info(f"[{req_id}] Stopping stream response: Client disconnected.")
             raise e
        logger.error(f"[{req_id}] Error using stream response: {e}")
        raise
    finally:
        logger.info(
            f"[{req_id}] ✅ Stream response usage stats:\n"
            f"  📊 Data Received: {data_received}, Has Content: {has_content}, Item Count: {received_items_count}\n"
            f"  📝 Content Stats: Body={total_body_processed} chars, Reason={total_reason_processed} chars\n"
            f"  🔄 Boundary Transitions: {boundary_transitions}, Force Body Mode: {force_body_mode}\n"
            f"  ⏱️ Timeout Handling: Ignored Stale Done={stale_done_ignored}, Initial Wait Limit={initial_wait_limit}\n"
            f"  🧹 Starting queue cleanup..."
        )
        # Trigger queue cleanup to prevent residual data
        await clear_stream_queue()


async def clear_stream_queue():
    import queue

    from server import STREAM_QUEUE, logger

    if STREAM_QUEUE is None:
        logger.info("Stream queue not initialized or disabled, skipping cleanup.")
        return

    cleared_count = 0
    while True:
        try:
            data_chunk = await asyncio.to_thread(STREAM_QUEUE.get_nowait)
            cleared_count += 1
            if cleared_count <= 3:
                logger.debug(f"Clearing stream queue item #{cleared_count}: {type(data_chunk)} - {str(data_chunk)[:100]}...")
        except queue.Empty:
            logger.info(f"Stream queue cleared (caught queue.Empty). Cleared items: {cleared_count}")
            break
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error clearing stream queue (Cleared {cleared_count} items): {e}", exc_info=True)
            break

    if cleared_count > 0:
        logger.warning(f"⚠️ Stream queue cache cleared, cleaned {cleared_count} residual items!")
    else:
        logger.info("Stream queue cache cleared (queue was empty).")