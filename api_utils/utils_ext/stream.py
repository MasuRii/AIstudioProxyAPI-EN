import asyncio
import json
import queue
import re
import time
from typing import Any, AsyncGenerator, Callable, List, Optional, Tuple

from logging_utils import set_request_id

# [REFAC-01] Structural Boundary Pattern
TOOL_STRUCTURE_PATTERN = re.compile(
    r"(?:^|\n)\s*(?:```[a-zA-Z0-9]*\s*)?<[a-zA-Z0-9_\-]+(?:\s|>)"
)


async def use_stream_response(
    req_id: str,
    timeout: float = 5.0,
    silence_threshold: float = 60.0,
    page: Any = None,
    check_client_disconnected: Optional[Callable] = None,
    stream_start_time: float = 0.0,
    enable_silence_detection: bool = True,
) -> AsyncGenerator[Any, None]:
    """Enhanced stream response handler with UI-based generation active checks."""
    from api_utils.server_state import state

    STREAM_QUEUE = state.STREAM_QUEUE
    logger = state.logger
    from browser_utils.page_controller import PageController
    from config import (
        CHAT_SESSION_CONTENT_SELECTOR,
        LAST_CHAT_TURN_SELECTOR,
        SCROLL_CONTAINER_SELECTOR,
        UI_GENERATION_WAIT_TIMEOUT_MS,
    )
    from config.global_state import GlobalState
    from models import (
        ClientDisconnectedError,
        QuotaExceededError,
        UpstreamError,
    )

    set_request_id(req_id)
    if STREAM_QUEUE is None:
        logger.warning(f"[{req_id}] STREAM_QUEUE is None, cannot use stream response")
        return

    if stream_start_time == 0.0:
        stream_start_time = time.time() - 10.0

    accumulated_body = ""
    accumulated_reason_len = 0
    total_reason_processed = 0
    total_body_processed = 0
    boundary_transitions = 0
    boundary_buffer = ""

    acc_reason_state = ""
    acc_body_state = ""
    force_body_mode = False
    split_index = -1
    empty_count = 0
    initial_wait_limit = int(timeout * 10)
    silence_wait_limit = int(silence_threshold * 10)
    max_empty_retries = max(silence_wait_limit, initial_wait_limit)
    hard_timeout_limit = int(timeout * 10 * 3)

    _data_received = False
    has_content = False
    has_seen_functions = False
    received_items_count = 0
    stale_done_ignored = False
    last_ui_check_time = 0
    ui_check_interval = int(UI_GENERATION_WAIT_TIMEOUT_MS / 100)
    if ui_check_interval <= 0:
        ui_check_interval = 1

    last_packet_time = time.time()
    min_items_before_silence_check = 10

    async def check_ui_generation_active():
        if not page:
            return False
        try:
            stop_button = page.locator('button[aria-label="Stop generating"]')
            if await stop_button.is_visible(timeout=1000):
                return True
            from config.selectors import SUBMIT_BUTTON_SELECTOR

            submit_button = page.locator(SUBMIT_BUTTON_SELECTOR)
            if await submit_button.count() > 0:
                try:
                    if await submit_button.first.is_disabled(timeout=2000):
                        return True
                except Exception:
                    return False
            return False
        except Exception:
            return False

    try:
        while True:
            if (
                GlobalState.CURRENT_STREAM_REQ_ID
                and GlobalState.CURRENT_STREAM_REQ_ID != req_id
            ):
                logger.warning(f"[{req_id}] Zombie Stream detected. Terminating.")
                yield {
                    "done": True,
                    "reason": "zombie_stream_aborted",
                    "body": "",
                    "function": [],
                }
                return

            if page:
                try:
                    await page.evaluate(
                        """([scrollSel, contentSel, lastTurnSel]) => {
                        const scrollContainer = document.querySelector(scrollSel);
                        if (scrollContainer) scrollContainer.scrollTop = scrollContainer.scrollHeight;
                        const sessionContent = document.querySelector(contentSel);
                        if (sessionContent) sessionContent.scrollTop = sessionContent.scrollHeight;
                        const lastTurn = document.querySelector(lastTurnSel);
                        if (lastTurn) lastTurn.scrollIntoView({behavior: "instant", block: "end"});
                        window.scrollTo(0, document.body.scrollHeight);
                    }""",
                        [
                            SCROLL_CONTAINER_SELECTOR,
                            CHAT_SESSION_CONTENT_SELECTOR,
                            LAST_CHAT_TURN_SELECTOR,
                        ],
                    )
                except Exception:
                    pass

            if GlobalState.IS_QUOTA_EXCEEDED and not GlobalState.IS_RECOVERING:
                logger.warning(f"[{req_id}] Quota detected. Pausing...")
                try:
                    start_wait = time.time()
                    while time.time() - start_wait < 2.0:
                        if GlobalState.IS_RECOVERING:
                            break
                        await asyncio.sleep(0.2)
                except Exception:
                    pass

                if GlobalState.IS_RECOVERING:
                    logger.info(f"[{req_id}] 🔄 Recovery mode detected. Holding...")
                elif not GlobalState.IS_QUOTA_EXCEEDED:
                    logger.info(f"[{req_id}] ✅ Recovery completed. Resuming...")
                else:
                    logger.warning(f"[{req_id}] ⛔ Quota exceeded, waiting...")
                    await asyncio.sleep(1.0)
                    continue

            if GlobalState.IS_SHUTTING_DOWN.is_set():
                logger.warning(f"[{req_id}] 🛑 Global Shutdown. Aborting.")
                yield {
                    "done": True,
                    "reason": "global_shutdown",
                    "body": "",
                    "function": [],
                }
                return

            try:
                data = STREAM_QUEUE.get_nowait()
                if data is None:
                    logger.info(f"[{req_id}] 🔴 Received termination signal.")
                    break

                if isinstance(data, dict) and data.get("done") is True:
                    logger.info(f"[{req_id}] ✅ Explicit DONE received.")
                    yield data
                    break

                empty_count = 0
                _data_received = True
                received_items_count += 1
                last_packet_time = time.time()

                actual_data = data
                if isinstance(data, str):
                    try:
                        parsed_wrapper = json.loads(data)
                        if (
                            isinstance(parsed_wrapper, dict)
                            and "ts" in parsed_wrapper
                            and "data" in parsed_wrapper
                        ):
                            if parsed_wrapper["ts"] < stream_start_time:
                                logger.warning(f"[{req_id}] 🗑️ Stale data ignored.")
                                continue
                            actual_data = parsed_wrapper["data"]
                        else:
                            actual_data = parsed_wrapper
                    except json.JSONDecodeError:
                        pass

                if isinstance(actual_data, dict):
                    if actual_data.get("error"):
                        status = actual_data.get("status", 500)
                        message = actual_data.get("message", "Unknown error")
                        if status == 429 or "quota" in message.lower():
                            raise QuotaExceededError(
                                f"AI Studio quota exceeded: {message}", req_id=req_id
                            )
                        else:
                            raise UpstreamError(
                                f"AI Studio error: {message}",
                                status_code=status,
                            )

                    parsed_data = actual_data
                    p_reason = str(parsed_data.get("reason", ""))
                    p_body = str(parsed_data.get("body", ""))

                    if (
                        p_reason
                        and acc_reason_state
                        and p_reason.startswith(acc_reason_state)
                    ):
                        new_reason_delta = p_reason[len(acc_reason_state) :]
                        acc_reason_state = p_reason
                    else:
                        acc_reason_state += p_reason
                        new_reason_delta = p_reason

                    if p_body and acc_body_state and p_body.startswith(acc_body_state):
                        acc_body_state = p_body
                    else:
                        acc_body_state += p_body

                    if force_body_mode:
                        parsed_data["reason"] = acc_reason_state[:split_index]
                        parsed_data["body"] = (
                            acc_body_state + acc_reason_state[split_index:]
                        )
                    else:
                        text_to_check = boundary_buffer + new_reason_delta
                        match = TOOL_STRUCTURE_PATTERN.search(text_to_check)
                        if match:
                            offset = len(acc_reason_state) - len(text_to_check)
                            split_index = offset + match.start()
                            force_body_mode = True
                            boundary_transitions += 1
                            parsed_data["reason"] = acc_reason_state[:split_index]
                            parsed_data["body"] = (
                                acc_body_state + acc_reason_state[split_index:]
                            )
                            logger.info(f"[{req_id}] ✂️ Boundary Split Applied.")
                        else:
                            parsed_data["reason"] = acc_reason_state
                            parsed_data["body"] = acc_body_state
                            boundary_buffer = (boundary_buffer + new_reason_delta)[
                                -100:
                            ]

                    accumulated_body += str(parsed_data.get("body", ""))
                    accumulated_reason_len += len(str(parsed_data.get("reason", "")))
                    total_body_processed += len(str(parsed_data.get("body", "")))
                    total_reason_processed += len(str(parsed_data.get("reason", "")))

                    if parsed_data.get("body") or parsed_data.get("reason"):
                        has_content = True

                    if parsed_data.get("function"):
                        has_seen_functions = True
                        # Track if any function call has empty arguments (potential parse failure)
                        for fc in parsed_data.get("function", []):
                            fc_params = fc.get("params") or fc.get("arguments") or {}
                            if not fc_params:
                                logger.warning(
                                    f"[{req_id}] ⚠️ Wire format returned '{fc.get('name')}' with empty args - will try DOM fallback"
                                )
                                has_seen_functions = False  # Force DOM fallback
                                break

                    if parsed_data.get("done") is True:
                        if GlobalState.IS_QUOTA_EXCEEDED or GlobalState.IS_RECOVERING:
                            logger.info(
                                f"[{req_id}] 🛡️ Quota/Recovery active: Holding stream open."
                            )
                            continue
                        just_rotated = (
                            time.time() - GlobalState.LAST_ROTATION_TIMESTAMP < 15.0
                        )
                        recently_recovered = (
                            time.time() - GlobalState.LAST_ROTATION_TIMESTAMP < 30.0
                        )
                        if (
                            not has_content
                            and received_items_count == 1
                            and not stale_done_ignored
                            and not GlobalState.IS_QUOTA_EXCEEDED
                            and (just_rotated or recently_recovered)
                        ):
                            logger.info(
                                f"[{req_id}] 🔄 Post-rotation empty DONE detected. Ignoring."
                            )
                            stale_done_ignored = True
                            continue
                    if (
                        parsed_data.get("done") is True
                        and not has_seen_functions
                        and page
                    ):
                        # Retry loop for DOM function call detection - UI elements may not render immediately
                        # Similar to body text retry loop below, but shorter timeout for function calls
                        dom_functions = []
                        dom_text = ""
                        max_fc_retries = 10  # 10 retries * 0.3s = 3 seconds max wait
                        for fc_retry in range(max_fc_retries):
                            (
                                dom_functions,
                                dom_text,
                            ) = await detect_function_calls_from_dom(
                                page, req_id, logger
                            )
                            if dom_functions:
                                logger.info(
                                    f"[{req_id}] ✅ DOM captured function calls after {fc_retry + 1} attempts"
                                )
                                break
                            # Only retry if we haven't found functions and body is also empty
                            # (indicates potential race condition with UI rendering)
                            if accumulated_body:
                                break  # We have body text, no need to wait for functions
                            await asyncio.sleep(0.3)

                        if dom_functions:
                            parsed_data["function"] = dom_functions
                            has_seen_functions = True

                        # If we have DOM text and accumulated body is empty, inject it to final chunk
                        if dom_text and not accumulated_body:
                            parsed_data["body"] = dom_text
                            accumulated_body = dom_text

                    yield parsed_data
                    if parsed_data.get("done") is True:
                        if (
                            accumulated_reason_len > 0
                            and len(accumulated_body) == 0
                            and not has_seen_functions
                        ):
                            logger.info(
                                f"[{req_id}] ⚠️ Thinking-Only response detected. Waiting for DOM..."
                            )
                            try:
                                if page:
                                    pc = PageController(page, logger, req_id)
                                    for _ in range(20):
                                        await asyncio.sleep(0.5)
                                        dom_text = (
                                            await pc.get_body_text_only_from_dom()
                                        )
                                        if dom_text and len(dom_text.strip()) > 0:
                                            logger.info(
                                                f"[{req_id}] ✅ DOM captured body: {len(dom_text)} chars"
                                            )
                                            yield {
                                                "body": dom_text,
                                                "reason": "",
                                                "done": False,
                                            }
                                            break
                            except Exception as e:
                                logger.error(f"[{req_id}] DOM Wait Error: {e}")
                        break
                    else:
                        stale_done_ignored = False
                continue
            except (queue.Empty, asyncio.QueueEmpty):
                empty_count += 1
                if (
                    enable_silence_detection
                    and received_items_count >= min_items_before_silence_check
                    and time.time() - last_packet_time > silence_threshold
                ):
                    logger.info(f"[{req_id}] 🔇 Stream silence detected.")
                    yield {
                        "done": True,
                        "reason": "silence_detected",
                        "body": "",
                        "function": [],
                    }
                    return
                if empty_count % 50 == 0:
                    logger.info(
                        f"[{req_id}] Waiting for data... ({empty_count}/{max_empty_retries})"
                    )
                if empty_count >= max_empty_retries:
                    if GlobalState.IS_RECOVERING:
                        empty_count = 0
                        continue
                    if (
                        await check_ui_generation_active()
                        and empty_count < hard_timeout_limit
                    ):
                        logger.warning(f"[{req_id}] Timeout but UI active. Snoozing...")
                        empty_count = max(0, empty_count - int(max_empty_retries * 0.5))
                        continue
                    elif empty_count >= hard_timeout_limit:
                        logger.error(f"[{req_id}] HARD TIMEOUT REACHED!")
                        yield {
                            "done": True,
                            "reason": "hard_timeout",
                            "body": "",
                            "function": [],
                        }
                        return
                    yield {
                        "done": True,
                        "reason": "internal_timeout",
                        "body": "",
                        "function": [],
                    }
                    return
                if check_client_disconnected:
                    try:
                        check_client_disconnected(f"Stream Queue Wait ({req_id})")
                    except ClientDisconnectedError:
                        raise
                if received_items_count == 0 and empty_count >= initial_wait_limit:
                    logger.error(f"[{req_id}] Stream has no data (TTFB Timeout).")
                    try:
                        from api_utils.server_state import state

                        page_instance = state.page_instance
                        if page_instance:
                            await page_instance.reload()
                    except Exception:
                        pass
                    yield {
                        "done": True,
                        "reason": "ttfb_timeout",
                        "body": "",
                        "function": [],
                    }
                    return
                if empty_count - last_ui_check_time >= ui_check_interval:
                    if await check_ui_generation_active():
                        logger.info(f"[{req_id}] UI detected still generating...")
                    last_ui_check_time = empty_count
                await asyncio.sleep(0.1)
                continue
    except asyncio.CancelledError:
        raise
    except Exception as e:
        if isinstance(e, ClientDisconnectedError):
            raise e
        logger.error(f"[{req_id}] Error in stream generator: {e}", exc_info=True)
        raise
    finally:
        logger.info(
            f"[{req_id}] Stream response completed. Items: {received_items_count}"
        )
        await clear_stream_queue()


async def clear_stream_queue():
    import queue

    from api_utils.server_state import state

    STREAM_QUEUE = state.STREAM_QUEUE
    logger = state.logger

    if STREAM_QUEUE is None:
        return
    cleared_count = 0
    while True:
        try:
            await asyncio.to_thread(STREAM_QUEUE.get_nowait)
            cleared_count += 1
        except queue.Empty:
            break
        except Exception:
            break
    if cleared_count > 0:
        logger.info(f"Stream queue cleared. Items: {cleared_count}")


async def detect_function_calls_from_dom(
    page: Any,
    req_id: str,
    logger: Any,
) -> Tuple[List[dict], str]:
    """Fallback function call detection using DOM parsing.

    This is used when the network interceptor doesn't capture function calls
    (e.g., due to timing issues or format changes).

    Args:
        page: Playwright page instance.
        req_id: Request ID for logging.
        logger: Logger instance.

    Returns:
        Tuple of (List of function call dicts, text content).
    """
    if not page:
        return [], ""

    try:
        from api_utils.utils_ext.function_call_response_parser import (
            FunctionCallResponseParser,
        )

        parser = FunctionCallResponseParser(page, logger, req_id)
        result = await parser.parse_function_calls()

        function_calls: List[dict] = []
        if result.has_function_calls and result.function_calls:
            # Convert ParsedFunctionCall objects to dict format expected by stream
            for fc in result.function_calls:
                function_calls.append({"name": fc.name, "params": fc.arguments})

            logger.info(
                f"[{req_id}] DOM fallback detected {len(function_calls)} function call(s)"
            )

        return function_calls, result.text_content

    except Exception as e:
        logger.debug(f"[{req_id}] DOM function call detection failed: {e}")

    return [], ""
