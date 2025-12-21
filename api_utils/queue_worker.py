"""
Queue Worker Module
Handles tasks in the request queue
"""

import asyncio
import logging
import time
from asyncio import Event, Future, Lock, Queue, Task
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from playwright.async_api import Locator

from api_utils.context_types import QueueItem
from logging_utils import set_request_id, set_source
from models import ChatCompletionRequest, QuotaExceededError


class QueueManager:
    def __init__(self):
        self.logger = logging.getLogger("queue_worker")
        self.was_last_request_streaming = False
        self.last_request_completion_time = 0.0

        # These will be initialized from server.py or created if missing
        self.request_queue: Optional[Queue[QueueItem]] = None
        self.processing_lock: Optional[Lock] = None
        self.model_switching_lock: Optional[Lock] = None
        self.params_cache_lock: Optional[Lock] = None

        # Context for cleanup
        self.current_submit_btn_loc: Optional[Locator] = None
        self.current_client_disco_checker: Optional[Callable[[str], bool]] = None
        self.current_completion_event: Optional[Event] = None
        self.current_req_id: Optional[str] = None

    def initialize_globals(self) -> None:
        """Initialize global variables from server state or create new ones."""
        from api_utils.server_state import state

        # Use state's logger if available, otherwise keep local one
        if hasattr(state, "logger"):
            self.logger = state.logger

        self.logger.info("--- Queue Worker Initializing ---")

        if state.request_queue is None:
            self.logger.info("Initializing request_queue...")
            state.request_queue = Queue()
        self.request_queue = state.request_queue

        if state.processing_lock is None:
            self.logger.info("Initializing processing_lock...")
            state.processing_lock = Lock()
        self.processing_lock = state.processing_lock

        if state.model_switching_lock is None:
            self.logger.info("Initializing model_switching_lock...")
            state.model_switching_lock = Lock()
        self.model_switching_lock = state.model_switching_lock

        if state.params_cache_lock is None:
            self.logger.info("Initializing params_cache_lock...")
            state.params_cache_lock = Lock()
        self.params_cache_lock = state.params_cache_lock

    async def check_queue_disconnects(self) -> None:
        """Check for disconnected clients in the queue."""
        if not self.request_queue:
            return

        queue_size = self.request_queue.qsize()
        if queue_size == 0:
            return

        checked_count = 0
        items_to_requeue: List[QueueItem] = []
        processed_ids: Set[str] = set()

        # Limit check to 10 items or queue size
        limit = min(queue_size, 10)

        while checked_count < limit:
            try:
                item: QueueItem = self.request_queue.get_nowait()
                item_req_id = str(item.get("req_id", "unknown"))

                if item_req_id in processed_ids:
                    items_to_requeue.append(item)
                    continue

                processed_ids.add(item_req_id)

                if not item.get("cancelled", False):
                    item_http_request = item.get("http_request")
                    if item_http_request:
                        try:
                            if await item_http_request.is_disconnected():
                                set_request_id(item_req_id)
                                self.logger.info(
                                    "(Worker Queue Check) Client disconnected, marking cancelled."
                                )
                                item["cancelled"] = True
                                item_future = item.get("result_future")
                                if item_future and not item_future.done():
                                    from .error_utils import client_disconnected
                                    item_future.set_exception(
                                        client_disconnected(
                                            item_req_id,
                                            "Client disconnected while queued.",
                                        )
                                    )
                        except asyncio.CancelledError:
                            raise
                        except Exception as check_err:
                            set_request_id(item_req_id)
                            self.logger.error(
                                f"(Worker Queue Check) Error checking disconnect: {check_err}"
                            )

                items_to_requeue.append(item)
                checked_count += 1
            except asyncio.QueueEmpty:
                break

        for item in items_to_requeue:
            await self.request_queue.put(item)

    async def get_next_request(self) -> Optional[QueueItem]:
        """Get the next request from the queue with timeout."""
        if not self.request_queue:
            await asyncio.sleep(1)
            return None

        try:
            return await asyncio.wait_for(self.request_queue.get(), timeout=5.0)
        except asyncio.TimeoutError:
            return None

    async def handle_streaming_delay(
        self, req_id: str, is_streaming_request: bool
    ) -> None:
        """Handle delay between streaming requests."""
        current_time = time.time()
        if (
            self.was_last_request_streaming
            and is_streaming_request
            and (current_time - self.last_request_completion_time < 1.0)
        ):
            delay_time = max(
                0.5, 1.0 - (current_time - self.last_request_completion_time)
            )
            self.logger.info(
                f"(Worker) Sequential streaming request, adding {delay_time:.2f}s delay..."
            )
            await asyncio.sleep(delay_time)

    async def process_request(self, request_item: QueueItem) -> None:
        """Process a single request item."""
        req_id = str(request_item["req_id"])
        request_data: ChatCompletionRequest = request_item["request_data"]
        http_request: Request = request_item["http_request"]
        result_future: Future[Union[StreamingResponse, JSONResponse]] = request_item[
            "result_future"
        ]

        # Set log context (Grid Logger)
        set_request_id(req_id)
        set_source("WORKER")

        # 1. Check cancellation
        if request_item.get("cancelled", False):
            self.logger.info("(Worker) Request cancelled, skipping.")
            if not result_future.done():
                from .error_utils import client_cancelled
                result_future.set_exception(
                    client_cancelled(req_id, "Request cancelled by user")
                )
            if self.request_queue:
                self.request_queue.task_done()
            return

        is_streaming_request = bool(request_data.stream)
        self.logger.info(
            f"[API] Starting request processing (Streaming: {'Yes' if is_streaming_request else 'No'})"
        )

        # 2. Initial Connection Check
        from api_utils.request_processor import (
            _check_client_connection,  # pyright: ignore[reportPrivateUsage]
        )

        if not await _check_client_connection(req_id, http_request):
            self.logger.info("(Worker) Client disconnected before processing.")
            if not result_future.done():
                result_future.set_exception(
                    HTTPException(
                        status_code=499,
                        detail=f"[{req_id}] Client disconnected before processing",
                    )
                )
            if self.request_queue:
                self.request_queue.task_done()
            return

        # 3. Streaming Delay
        await self.handle_streaming_delay(req_id, is_streaming_request)

        # 4. Connection Check before Lock
        if not await _check_client_connection(req_id, http_request):
            self.logger.info("(Worker) Client disconnected while waiting.")
            if not result_future.done():
                result_future.set_exception(
                    HTTPException(
                        status_code=499, detail=f"[{req_id}] Client disconnected"
                    )
                )
            if self.request_queue:
                self.request_queue.task_done()
            return

        self.logger.debug("[Lock] Waiting for processing lock...")

        if not self.processing_lock:
            self.logger.error("Processing lock is None!")
            if not result_future.done():
                from .error_utils import server_error
                result_future.set_exception(
                    server_error(req_id, "Internal error: Processing lock missing")
                )
            if self.request_queue:
                self.request_queue.task_done()
            return

        async with self.processing_lock:
            self.logger.debug("[Lock] Successfully acquired processing lock")

            # 5. Final Connection Check inside Lock
            if not await _check_client_connection(req_id, http_request):
                self.logger.info("[Client] Client disconnected after acquiring lock")
                if not result_future.done():
                    result_future.set_exception(
                        HTTPException(
                            status_code=499, detail=f"[{req_id}] Client disconnected"
                        )
                    )
            elif result_future.done():
                self.logger.info("(Worker) Future already done. Skipping.")
            else:
                # --- Fast-Fail Tiered Error Recovery Logic ---
                # Optimized recovery strategy (Goal: Switch failed profile within 10-15s)
                # Tier 1: Page Refresh (Fast, ~2-3s)
                # Tier 2: Auth Profile Switch (Skip browser restart, switch profile directly)

                max_attempts = 3  # Attempt 1 (Initial) -> Tier 1 (Refresh) -> Attempt 2 -> Tier 2 (Profile Switch) -> Attempt 3

                for attempt in range(1, max_attempts + 1):
                    try:
                        # Check if result_future is already done (may have been set in previous attempts)
                        # asyncio.Future cannot be reset; once done, it cannot be meaningfully retried
                        if result_future.done():
                            self.logger.warning(
                                f"(Worker) [Attempt {attempt}] result_future already done, "
                                "cannot retry with same future. Breaking retry loop."
                            )
                            break

                        self.logger.debug(
                            f"[Exec] Attempt {attempt}/{max_attempts}: Executing request logic..."
                        )
                        await self._execute_request_logic(
                            req_id, request_data, http_request, result_future
                        )
                        # If successful (no exception raised), break the retry loop
                        break
                    except asyncio.CancelledError:
                        # Check if this is a user-initiated shutdown
                        from api_utils.server_state import state

                        if state.should_exit:
                            self.logger.info("Worker stopped by user.")
                        else:
                            self.logger.warning("[Client] Request cancelled during execution")
                        raise
                    except Exception as e:
                        error_str = str(e).lower()
                        self.logger.error(
                            f"[Exec] Attempt {attempt}/{max_attempts}: Error - {e}"
                        )

                        # Check for quota error - switch profile immediately
                        is_quota_error = any(
                            keyword in error_str
                            for keyword in [
                                "quota",
                                "429",
                                "rate limit",
                                "exceeded",
                                "too many requests",
                            ]
                        )

                        if is_quota_error:
                            self.logger.warning(
                                "[Recovery] Quota/Rate limit error detected, switching profile..."
                            )
                            await self._switch_auth_profile(req_id)
                            continue

                        # If it's the last attempt, re-raise to be handled by outer block
                        if attempt == max_attempts:
                            self.logger.critical(
                                f"[Exec] All {max_attempts} attempts failed"
                            )
                            raise

                        # Tier 1: Page Refresh (Fast recovery, ~2-3s)
                        if attempt == 1:
                            self.logger.debug("[Recovery] Tier 1: Refreshing page...")
                            try:
                                await self._refresh_page(req_id)
                            except asyncio.CancelledError:
                                raise
                            except Exception as refresh_err:
                                self.logger.error(
                                    f"[Recovery] Tier 1 refresh failed: {refresh_err}"
                                )
                            continue

                        # Tier 2: Auth Profile Switch (Skip browser restart, switch profile directly)
                        if attempt == 2:
                            self.logger.warning("[Recovery] Tier 2: Switching auth profile...")
                            try:
                                await self._switch_auth_profile(req_id)
                            except asyncio.CancelledError:
                                raise
                            except Exception as switch_err:
                                self.logger.error(
                                    f"[Recovery] Tier 2 switch failed: {switch_err}"
                                )
                                if "exhausted" in str(switch_err).lower():
                                    self.logger.critical(
                                        "[Recovery] All auth profiles exhausted"
                                    )
                                    raise
                            continue

                # --- End Fast-Fail Tiered Error Recovery Logic ---

            # 6. Cleanup / Post-processing (Clear Stream Queue & Chat History)
            await self._cleanup_after_processing(req_id)

            self.logger.debug("[Lock] Processing lock released")

        # Update state for next iteration
        self.was_last_request_streaming = is_streaming_request
        self.last_request_completion_time = time.time()
        if self.request_queue:
            self.request_queue.task_done()

    async def _execute_request_logic(
        self,
        req_id: str,
        request_data: ChatCompletionRequest,
        http_request: Request,
        result_future: Future[Union[StreamingResponse, JSONResponse]],
    ) -> None:
        """Execute the actual request processing logic."""
        # Ensure log context is set
        set_request_id(req_id)

        try:
            from api_utils import (
                _process_request_refactored,  # pyright: ignore[reportPrivateUsage]
            )

            # Store these for cleanup usage if needed
            self.current_submit_btn_loc = None
            self.current_client_disco_checker = None
            self.current_completion_event = None
            self.current_req_id = req_id

            returned_value: Optional[
                Tuple[Optional[Event], Locator, Callable[[str], bool]]
            ] = await _process_request_refactored(
                req_id, request_data, http_request, result_future
            )

            # Initialize variables that will be set from tuple unpacking
            completion_event: Optional[Event] = None
            submit_btn_loc: Optional[Locator] = None
            client_disco_checker: Optional[Callable[[str], bool]] = None
            current_request_was_streaming = False

            if returned_value is not None:
                # Always expect 3-tuple: (Optional[Event], Locator, Callable)
                completion_event, submit_btn_loc, client_disco_checker = returned_value

                if completion_event is not None:
                    current_request_was_streaming = True
                    self.logger.info("[Streaming] First chunk received")
                else:
                    self.logger.debug("[Stream] Received Tuple but no completion event (Non-streaming)")
            else:
                self.logger.debug("[Stream] Non-streaming completion (None)")

            # Store for cleanup
            self.current_submit_btn_loc = submit_btn_loc
            self.current_client_disco_checker = client_disco_checker
            self.current_completion_event = completion_event

            # Initialize stream_state for monitoring
            stream_state: Optional[Dict[str, Any]] = None

            await self._monitor_completion(
                req_id,
                http_request,
                result_future,
                completion_event,
                submit_btn_loc,
                client_disco_checker,
                current_request_was_streaming,
                stream_state,
            )

        except asyncio.CancelledError:
            self.logger.info("[Client] Execution cancelled")
            raise
        except Exception as process_err:
            self.logger.error(f"[Exec] Execution error: {process_err}")
            if not result_future.done():
                from .error_utils import server_error
                result_future.set_exception(
                    server_error(req_id, f"Request processing error: {process_err}")
                )
            # Re-throw exception to trigger retry mechanism
            raise

    async def _monitor_completion(
        self,
        req_id: str,
        http_request: Request,
        result_future: Future[Union[StreamingResponse, JSONResponse]],
        completion_event: Optional[Event],
        submit_btn_loc: Optional[Locator],
        client_disco_checker: Optional[Callable[[str], bool]],
        current_request_was_streaming: bool,
        stream_state: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Monitor for completion and handle disconnects.

        Args:
            stream_state: Optional stream state dict, containing 'has_content' key.
                          If stream completes without content, an exception is thrown to trigger retry.
        """
        # Ensure log context is set
        set_request_id(req_id)

        from api_utils.client_connection import (
            enhanced_disconnect_monitor,
            non_streaming_disconnect_monitor,
        )

        try:
            from server import RESPONSE_COMPLETION_TIMEOUT
        except ImportError:
            from config import RESPONSE_COMPLETION_TIMEOUT

        disconnect_monitor_task: Optional[Task[bool]] = None
        try:
            if completion_event:
                self.logger.debug("[Stream] Waiting for streaming completion...")
                disconnect_monitor_task = asyncio.create_task(
                    enhanced_disconnect_monitor(
                        req_id, http_request, completion_event, self.logger
                    )
                )

                await asyncio.wait_for(
                    completion_event.wait(),
                    timeout=RESPONSE_COMPLETION_TIMEOUT / 1000 + 60,
                )
            else:
                self.logger.debug("[Stream] Waiting for non-streaming completion...")
                disconnect_monitor_task = asyncio.create_task(
                    non_streaming_disconnect_monitor(
                        req_id, http_request, result_future, self.logger
                    )
                )

                await asyncio.wait_for(
                    asyncio.shield(result_future),
                    timeout=RESPONSE_COMPLETION_TIMEOUT / 1000 + 60,
                )

            # Check if client disconnected early
            client_disconnected_early = False
            if disconnect_monitor_task.done():
                try:
                    client_disconnected_early = disconnect_monitor_task.result()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    pass

            self.logger.debug(
                f"[Stream] Processing complete (Early disconnect: {client_disconnected_early})"
            )

            # Check for content in stream response - throw exception on empty response to trigger retry
            if (
                stream_state is not None
                and completion_event is not None
                and not client_disconnected_early
            ):
                has_content = stream_state.get(
                    "has_content", True
                )  # Default True to avoid false positives
                if not has_content:
                    self.logger.warning(
                        "[Stream] Empty response detected (stream_state.has_content=False), "
                        "possible quota exceeded, triggering retry"
                    )
                    raise RuntimeError(
                        "Stream completed without content (Empty response - possible quota exceeded)"
                    )

            if (
                not client_disconnected_early
                and submit_btn_loc
                and client_disco_checker
                and completion_event
            ):
                await self._handle_post_stream_button(
                    req_id, submit_btn_loc, client_disco_checker, completion_event
                )

        except asyncio.TimeoutError:
            self.logger.warning("[Stream] Processing timeout")
            if not result_future.done():
                from .error_utils import processing_timeout
                result_future.set_exception(
                    processing_timeout(
                        req_id, "Processing timed out waiting for completion."
                    )
                )
        except asyncio.CancelledError:
            self.logger.info("[Client] Completion monitoring cancelled")
            raise
        except Exception as ev_wait_err:
            self.logger.error(f"[Stream] Error waiting for completion: {ev_wait_err}")
            if not result_future.done():
                from .error_utils import server_error
                result_future.set_exception(
                    server_error(req_id, f"Error waiting for completion: {ev_wait_err}")
                )
            # Re-throw exception to trigger retry mechanism (especially for empty response errors)
            raise
        finally:
            if disconnect_monitor_task and not disconnect_monitor_task.done():
                disconnect_monitor_task.cancel()
                try:
                    await disconnect_monitor_task
                except asyncio.CancelledError:
                    pass

    async def _handle_post_stream_button(
        self,
        req_id: str,
        submit_btn_loc: Locator,
        client_disco_checker: Callable[[str], bool],
        completion_event: Event,
    ) -> None:
        """Handle the submit button state after streaming."""
        # Ensure log context is set
        set_request_id(req_id)

        self.logger.debug("[Cleanup] Handling post-stream button state...")
        try:
            from browser_utils.page_controller import PageController
            from server import page_instance

            if page_instance:
                page_controller = PageController(page_instance, self.logger, req_id)
                await page_controller.ensure_generation_stopped(client_disco_checker)
            else:
                self.logger.warning("[Cleanup] page_instance is None")

        except asyncio.CancelledError:
            self.logger.info("[Client] Post-stream button handling cancelled")
            raise
        except Exception as e_ensure_stop:
            self.logger.warning(f"Post-stream button handling error: {e_ensure_stop}")
            # Use comprehensive snapshot for better debugging
            import os

            from browser_utils.debug_utils import (
                save_comprehensive_snapshot,
            )
            from config import PROMPT_TEXTAREA_SELECTOR
            from server import page_instance

            if page_instance:
                await save_comprehensive_snapshot(
                    page=page_instance,
                    error_name="stream_post_submit_button_handling_timeout",
                    req_id=req_id,
                    error_stage="Post-stream response button status handling",
                    additional_context={
                        "headless_mode": os.environ.get("HEADLESS", "true").lower()
                        == "true",
                        "completion_event_set": completion_event.is_set()
                        if completion_event
                        else None,
                        "error_type": type(e_ensure_stop).__name__,
                        "error_message": str(e_ensure_stop),
                    },
                    locators={
                        "submit_button": submit_btn_loc,
                        "input_field": page_instance.locator(PROMPT_TEXTAREA_SELECTOR),
                    },
                    error_exception=e_ensure_stop,
                )

    async def _cleanup_after_processing(self, req_id: str):
        """Clean up stream queue and chat history."""
        # Ensure log context is set
        set_request_id(req_id)

        try:
            from api_utils import clear_stream_queue

            await clear_stream_queue()

            # Clear chat history if we have the necessary context
            if getattr(self, "current_submit_btn_loc", None) and getattr(
                self, "current_client_disco_checker", None
            ):
                from server import is_page_ready, page_instance

                if (
                    page_instance
                    and is_page_ready
                    and self.current_client_disco_checker
                ):
                    from browser_utils.page_controller import PageController

                    page_controller = PageController(page_instance, self.logger, req_id)

                    await page_controller.clear_chat_history(
                        self.current_client_disco_checker
                    )
                    self.logger.info("[Session] Chat history cleared")
        except asyncio.CancelledError:
            self.logger.info("[Client] Cleanup cancelled")
            raise
        except Exception as clear_err:
            self.logger.error(f"[Cleanup] Cleanup error: {clear_err}", exc_info=True)

    async def _refresh_page(self, req_id: str) -> None:
        """Tier 1 Recovery: Fast page refresh (~2-3s)."""
        # Ensure log context is set
        set_request_id(req_id)

        from api_utils.server_state import state

        if state.page_instance is None:
            raise RuntimeError("page_instance is missing")

        page = state.page_instance
        self.logger.info("[Recovery] Performing page refresh...")

        try:
            # Fast page refresh
            await page.reload(wait_until="domcontentloaded", timeout=10000)

            # Wait for key elements to be available (short timeout)
            from config.selectors import PROMPT_TEXTAREA_SELECTOR

            await page.wait_for_selector(PROMPT_TEXTAREA_SELECTOR, timeout=5000)

            self.logger.info("(Recovery) Page refresh complete")
        except asyncio.CancelledError:
            self.logger.info("(Recovery) Page refresh cancelled")
            raise
        except Exception as e:
            self.logger.error(f"(Recovery) Page refresh failed: {e}")
            raise

    async def _switch_auth_profile(self, req_id: str) -> None:
        """Tier 2 Recovery: Completely reinitialize browser connection to avoid state retention."""
        # Ensure log context is set
        set_request_id(req_id)

        from api_utils.auth_manager import auth_manager
        from browser_utils.initialization.core import (
            close_page_logic,
            enable_temporary_chat_mode,
            initialize_page_logic,
        )
        from browser_utils.model_management import (
            _handle_initial_model_state_and_storage,  # pyright: ignore[reportPrivateUsage]
        )
        from config import get_environment_variable

        # Mark current profile as failed
        auth_manager.mark_profile_failed()

        # Get next profile
        next_profile = await auth_manager.get_next_profile()
        self.logger.info(f"(Recovery) Switching to profile: {next_profile}")

        # 1. Close existing page
        await close_page_logic()

        # 2. Close browser connection to get fresh state
        from api_utils.server_state import state

        if state.browser_instance and state.browser_instance.is_connected():
            await state.browser_instance.close()
            state.is_browser_connected = False
            self.logger.info("(Recovery) Browser connection closed")

        # 3. Reconnect to Camoufox
        ws_endpoint = get_environment_variable("CAMOUFOX_WS_ENDPOINT")
        if not ws_endpoint:
            raise RuntimeError("CAMOUFOX_WS_ENDPOINT not available for reconnection")

        if not state.playwright_manager:
            raise RuntimeError("Playwright manager not available")

        self.logger.info("(Recovery) Reconnecting to browser...")
        state.browser_instance = await state.playwright_manager.firefox.connect(
            ws_endpoint, timeout=30000
        )
        state.is_browser_connected = True
        self.logger.info(f"(Recovery) Connected: {state.browser_instance.version}")

        # 4. Initialize page with new profile
        state.page_instance, state.is_page_ready = await initialize_page_logic(
            state.browser_instance,
            storage_state_path=next_profile,
        )

        # 5. Handle initial model state and storage
        if state.is_page_ready and state.page_instance:
            await _handle_initial_model_state_and_storage(state.page_instance)

            # 6. Enable temporary chat mode
            await enable_temporary_chat_mode(state.page_instance)

            self.logger.info("(Recovery) Profile switch complete (Browser fully reinitialized)")
        else:
            raise RuntimeError("(Recovery) Page initialization failed, cannot complete profile switch")


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
                                            from .error_utils import client_disconnected
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
                    from .error_utils import client_cancelled
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
                                    disconnect_detection_count = 0
                                    consecutive_checks = 0
                                    check_interval = 0.2  # More frequent checks for faster detection
                                    
                                    while not completion_event.is_set():
                                        try:
                                            consecutive_checks += 1
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

                                            # Enhanced client disconnect detection with debouncing
                                            is_connected = await _test_client_connection(req_id, http_request)
                                            if not is_connected:
                                                disconnect_detection_count += 1
                                                logger.debug(f"[{req_id}] (Worker) Client disconnect detected (count: {disconnect_detection_count}/3)")
                                                
                                                # Require 3 consecutive disconnects to confirm (debouncing)
                                                if disconnect_detection_count >= 3:
                                                    logger.info(f"[{req_id}] (Worker) ✅ Confirmed client disconnect during streaming (3 consecutive checks), triggering done signal early")
                                                    client_disconnected_early = True
                                                    # Set completion_event immediately to end wait early
                                                    if not completion_event.is_set():
                                                        completion_event.set()
                                                    break
                                            else:
                                                # Reset counter on successful connection
                                                disconnect_detection_count = 0
                                            
                                            # Log status every 50 checks to show we're still monitoring
                                            if consecutive_checks % 50 == 0:
                                                logger.debug(f"[{req_id}] (Worker) Stream monitor still active (checks: {consecutive_checks}, disconnect_count: {disconnect_detection_count})")
                                            
                                            await asyncio.sleep(check_interval)
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
                                    wait_timeout_ms = 10000  # Reduced from 30s to 10s to avoid long waits
                                    try:
                                        from playwright.async_api import expect as expect_async
                                        from api_utils.request_processor import ClientDisconnectedError

                                        # Check client connection status before starting button operations
                                        try:
                                            client_disco_checker("Post-stream button status check - Pre-check: ")
                                        except ClientDisconnectedError:
                                            logger.info(f"[{req_id}] Client disconnected during pre-check, skipping button handling.")
                                            raise
                                        
                                        await asyncio.sleep(0.5)  # Give UI some time to update

                                        # Re-check client connection after the sleep
                                        try:
                                            client_disco_checker("Post-stream button status check - Post-sleep: ")
                                        except ClientDisconnectedError:
                                            logger.info(f"[{req_id}] Client disconnected during post-sleep check, skipping button handling.")
                                            raise

                                        # Check if button is still enabled, if so click stop directly
                                        logger.info(f"[{req_id}] (Worker) Checking send button status...")
                                        try:
                                            # [AUTO-01] Harden Submit Button Logic
                                            is_button_enabled = await submit_btn_loc.is_enabled(timeout=2000)
                                            logger.info(f"[{req_id}] (Worker) Send button enabled status: {is_button_enabled}")

                                            # Check client connection before clicking
                                            try:
                                                client_disco_checker("Post-stream button status check - Before click: ")
                                            except ClientDisconnectedError:
                                                logger.info(f"[{req_id}] Client disconnected before button click, aborting.")
                                                raise

                                            if is_button_enabled:
                                                # Button still enabled after stream completion, click stop
                                                logger.info(f"[{req_id}] (Worker) Stream completed but button still enabled, clicking stop to end generation...")
                                                await submit_btn_loc.click(timeout=5000, force=True)
                                                logger.info(f"[{req_id}] (Worker) ✅ Send button click completed.")
                                            else:
                                                logger.info(f"[{req_id}] (Worker) Send button disabled, no click needed.")
                                        except Exception as button_check_err:
                                            logger.warning(f"[{req_id}] (Worker) Failed to check button status: {button_check_err}")

                                        # Final client connection check before waiting for button disabled
                                        try:
                                            client_disco_checker("Post-stream button status check - Before final wait: ")
                                        except ClientDisconnectedError:
                                            logger.info(f"[{req_id}] Client disconnected before final wait, skipping disable wait.")
                                            raise

                                        # Wait for button to be finally disabled
                                        logger.info(f"[{req_id}] (Worker) Waiting for send button to be finally disabled...")
                                        await expect_async(submit_btn_loc).to_be_disabled(timeout=wait_timeout_ms)
                                        logger.info(f"[{req_id}] ✅ Send button disabled.")

                                    except ClientDisconnectedError:
                                        logger.info(f"[{req_id}] Client disconnected during stream post-response button status handling.")
                                    except Exception as e_pw_disabled:
                                        logger.warning(f"[{req_id}] ⚠️ Stream post-response button status handling timeout or error: {e_pw_disabled}")
                                        from api_utils.request_processor import save_error_snapshot
                                        await save_error_snapshot(f"stream_post_submit_button_handling_timeout_{req_id}")
                            elif completion_event and current_request_was_streaming:
                                logger.warning(f"[{req_id}] (Worker) Streaming request but submit_btn_loc or client_disco_checker missing. Skipping button disable wait.")

                        except asyncio.TimeoutError:
                            logger.warning(f"[{req_id}] (Worker) ⚠️ Processing completion wait timed out.")
                            if not result_future.done():
                                from .error_utils import processing_timeout
                                result_future.set_exception(processing_timeout(req_id, "Processing timed out waiting for completion."))
                        except Exception as ev_wait_err:
                            logger.error(f"[{req_id}] (Worker) ❌ Error waiting for completion: {ev_wait_err}")
                            if not result_future.done():
                                from .error_utils import server_error
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
                            from .error_utils import server_error
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
                result_future.cancel()
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
                from .error_utils import server_error
                result_future.set_exception(server_error(req_id, f"Internal Server Error: {e}"))
        finally:
            if request_item:
                request_queue.task_done()
    
    logger.info("--- Queue Worker Stopped ---")
