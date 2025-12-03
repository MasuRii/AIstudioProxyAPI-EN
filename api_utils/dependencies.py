"""
FastAPI 依赖项模块
"""

import logging
from asyncio import Event, Lock, Queue
from typing import Any, Dict, List, Set

from api_utils.context_types import QueueItem


def get_logger() -> logging.Logger:
    from server import logger

    return logger


def get_log_ws_manager():
    from server import log_ws_manager

    return log_ws_manager


def get_request_queue() -> "Queue[QueueItem]":
    from server import request_queue

    return request_queue


def get_processing_lock() -> Lock:
    from server import processing_lock

    return processing_lock


def get_worker_task():
    from server import worker_task

    return worker_task


def get_server_state() -> Dict[str, Any]:
    from server import (
        is_browser_connected,
        is_initializing,
        is_page_ready,
        is_playwright_ready,
    )

    # 返回不可变快照，避免下游修改全局引用
    return dict(
        is_initializing=is_initializing,
        is_playwright_ready=is_playwright_ready,
        is_browser_connected=is_browser_connected,
        is_page_ready=is_page_ready,
    )


def get_page_instance():
    from server import page_instance

    return page_instance


def get_model_list_fetch_event() -> Event:
    from server import model_list_fetch_event

    return model_list_fetch_event


def get_parsed_model_list() -> List[Dict[str, Any]]:
    from server import parsed_model_list

    return parsed_model_list


def get_excluded_model_ids() -> Set[str]:
    from server import excluded_model_ids

    return excluded_model_ids


def get_current_ai_studio_model_id() -> str:
    from server import current_ai_studio_model_id

    return current_ai_studio_model_id

async def ensure_request_lock():
    """
    Dependency that acts as a 'Parking Lot' for requests.
    If Auth Rotation is in progress (Lock is cleared) or Quota is Exceeded (Rotation imminent),
    this will pause the request until the system is ready.
    """
    from config.global_state import GlobalState
    import asyncio
    from server import logger

    # A request is considered "queued" if it has to wait for the lock.
    is_waiting = GlobalState.IS_QUOTA_EXCEEDED or not GlobalState.AUTH_ROTATION_LOCK.is_set()
    if is_waiting:
        GlobalState.queued_request_count += 1
    
    try:
        # Wait loop to handle both Lock and Quota states
        # We wait if:
        # 1. Lock is NOT set (Rotation in progress)
        # 2. Quota IS exceeded (Rotation about to start, or we need to wait for it)
        while GlobalState.IS_QUOTA_EXCEEDED or not GlobalState.AUTH_ROTATION_LOCK.is_set():
            if not GlobalState.AUTH_ROTATION_LOCK.is_set():
                 # Rotation in progress. Wait for lock to open with timeout.
                 try:
                     await asyncio.wait_for(GlobalState.AUTH_ROTATION_LOCK.wait(), timeout=30.0)
                 except asyncio.TimeoutError:
                     logger.warning("🚨 Lock wait timeout after 30s. Service may be unavailable.")
                     from fastapi import HTTPException
                     raise HTTPException(status_code=503, detail="Service temporarily unavailable - timeout waiting for system lock")
            else:
                 # Lock is Open, but Quota is still marked Exceeded.
                 # This implies the Watchdog is about to rotate, or we are in a race.
                 # We wait briefly to allow the state to resolve.
                 await asyncio.sleep(0.1)
    finally:
        if is_waiting:
            GlobalState.queued_request_count -= 1
