"""
FastAPI Dependencies Module
"""

import logging
from asyncio import Event, Lock, Queue
from typing import Any, Dict, List, Set

from api_utils.context_types import QueueItem


def get_logger() -> logging.Logger:
    from api_utils.server_state import state

    return state.logger


def get_log_ws_manager():
    from api_utils.server_state import state

    return state.log_ws_manager


def get_request_queue() -> "Queue[QueueItem]":
    from typing import cast

    from api_utils.server_state import state

    return cast("Queue[QueueItem]", state.request_queue)


def get_processing_lock() -> Lock:
    from typing import cast

    from api_utils.server_state import state

    return cast(Lock, state.processing_lock)


def get_worker_task():
    from api_utils.server_state import state

    return state.worker_task


def get_server_state() -> Dict[str, Any]:
    from api_utils.server_state import state

    # Return immutable snapshot to prevent downstream modifications to global references
    return dict(
        is_initializing=state.is_initializing,
        is_playwright_ready=state.is_playwright_ready,
        is_browser_connected=state.is_browser_connected,
        is_page_ready=state.is_page_ready,
    )


def get_page_instance():
    from api_utils.server_state import state

    return state.page_instance


def get_model_list_fetch_event() -> Event:
    from typing import cast

    from api_utils.server_state import state

    return cast(Event, state.model_list_fetch_event)


def get_parsed_model_list() -> List[Dict[str, Any]]:
    from api_utils.server_state import state

    return state.parsed_model_list


def get_excluded_model_ids() -> Set[str]:
    from api_utils.server_state import state

    return state.excluded_model_ids


def get_current_ai_studio_model_id() -> str:
    from typing import cast

    from api_utils.server_state import state

    return cast(str, state.current_ai_studio_model_id)


async def ensure_request_lock():
    """
    Dependency that acts as a 'Parking Lot' for requests.
    If Auth Rotation is in progress (Lock is cleared) or Quota is Exceeded (Rotation imminent),
    this will pause the request until the system is ready.
    """
    import asyncio
    import time

    from api_utils.server_state import state as server_state
    from config.global_state import GlobalState

    logger = server_state.logger

    # A request is considered "queued" if it has to wait for the lock.
    is_waiting = (
        GlobalState.IS_QUOTA_EXCEEDED or not GlobalState.AUTH_ROTATION_LOCK.is_set()
    )
    if is_waiting:
        GlobalState.queued_request_count += 1

    start_time = time.time()
    max_total_wait = 60.0  # 60 second hard timeout for request parking

    try:
        # Wait loop to handle both Lock and Quota states
        # We wait if:
        # 1. Lock is NOT set (Rotation in progress)
        # 2. Quota IS exceeded (Rotation about to start, or we need to wait for it)
        while (
            GlobalState.IS_QUOTA_EXCEEDED or not GlobalState.AUTH_ROTATION_LOCK.is_set()
        ):
            # Check for total timeout
            if time.time() - start_time > max_total_wait:
                logger.error(
                    f"🚨 Request parking timeout after {max_total_wait}s. Quota={GlobalState.IS_QUOTA_EXCEEDED}, LockSet={GlobalState.AUTH_ROTATION_LOCK.is_set()}"
                )
                from fastapi import HTTPException

                raise HTTPException(
                    status_code=530,  # Custom code for state resolution timeout
                    detail="System state resolution timeout - please try again later",
                )

            if not GlobalState.AUTH_ROTATION_LOCK.is_set():
                # Rotation in progress. Wait for lock to open with timeout.
                try:
                    await asyncio.wait_for(
                        GlobalState.AUTH_ROTATION_LOCK.wait(), timeout=30.0
                    )
                except asyncio.TimeoutError:
                    logger.warning(
                        "🚨 Lock wait timeout after 30s. Service may be unavailable."
                    )
                    from fastapi import HTTPException

                    raise HTTPException(
                        status_code=503,
                        detail="Service temporarily unavailable - timeout waiting for system lock",
                    )
            else:
                # Lock is Open, but Quota is still marked Exceeded.
                # This implies the Watchdog is about to rotate, or we are in a race.
                # We wait for the recovery event which signals rotation completion.
                try:
                    if GlobalState.IS_RECOVERING:
                        # If recovery is active, wait for it to finish
                        await asyncio.wait_for(
                            GlobalState.RECOVERY_EVENT.wait(), timeout=30.0
                        )
                    else:
                        # Watchdog hasn't started yet, wait briefly
                        await asyncio.sleep(0.1)
                except asyncio.TimeoutError:
                    await asyncio.sleep(0.1)
    finally:
        if is_waiting:
            GlobalState.queued_request_count -= 1
