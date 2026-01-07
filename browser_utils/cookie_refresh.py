# --- browser_utils/cookie_refresh.py ---
"""
Cookie Refresh Module

Provides functionality to automatically refresh and persist browser cookies
back to the auth profile files, keeping them up-to-date during runtime.

Features:
- Periodic background refresh
- On-demand refresh after successful API requests
- Graceful shutdown save
"""

import asyncio
import json
import logging
import os
import time
from typing import Optional

from config.settings import (
    COOKIE_REFRESH_ENABLED,
    COOKIE_REFRESH_INTERVAL_SECONDS,
    COOKIE_REFRESH_ON_REQUEST_ENABLED,
    COOKIE_REFRESH_ON_SHUTDOWN,
    COOKIE_REFRESH_REQUEST_INTERVAL,
)

logger = logging.getLogger("CookieRefresh")

# Module-level state
_last_refresh_time: float = 0
_request_count_since_refresh: int = 0
_refresh_lock = asyncio.Lock()
_periodic_task: Optional[asyncio.Task] = None


async def save_current_cookies_to_profile() -> bool:
    """
    Save the current browser cookies back to the active auth profile file.

    Returns:
        True if cookies were saved successfully, False otherwise.
    """
    global _last_refresh_time

    if not COOKIE_REFRESH_ENABLED:
        logger.debug("Cookie refresh is disabled, skipping save")
        return False

    try:
        from api_utils.server_state import state

        # Check if we have a valid page instance
        if not state.page_instance or state.page_instance.is_closed():
            logger.debug("No active page instance, skipping cookie save")
            return False

        # Get the current auth profile path
        profile_path = state.current_auth_profile_path
        if not profile_path:
            profile_path = os.environ.get("ACTIVE_AUTH_JSON_PATH")

        if not profile_path or not os.path.exists(profile_path):
            logger.debug(f"No valid auth profile path found: {profile_path}")
            return False

        # Use lock to prevent concurrent saves
        async with _refresh_lock:
            context = state.page_instance.context

            # Get current storage state (cookies + origins/localStorage)
            storage_state = await context.storage_state()

            # Read existing profile to preserve any custom data
            try:
                with open(profile_path, "r", encoding="utf-8") as f:
                    existing_data = json.load(f)
            except (json.JSONDecodeError, OSError):
                existing_data = {}

            # Update cookies and origins
            existing_data["cookies"] = storage_state.get("cookies", [])
            existing_data["origins"] = storage_state.get("origins", [])

            # Write back to file
            with open(profile_path, "w", encoding="utf-8") as f:
                json.dump(existing_data, f, indent=2, ensure_ascii=False)

            _last_refresh_time = time.time()
            cookie_count = len(storage_state.get("cookies", []))
            logger.info(
                f"🍪 Cookies saved to '{os.path.basename(profile_path)}' "
                f"({cookie_count} cookies)"
            )
            return True

    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"Failed to save cookies: {e}")
        return False


async def maybe_refresh_on_request() -> bool:
    """
    Called after successful API requests. Saves cookies if enough requests
    have been processed since the last save.

    Returns:
        True if cookies were saved, False otherwise.
    """
    global _request_count_since_refresh

    if not COOKIE_REFRESH_ON_REQUEST_ENABLED:
        return False

    _request_count_since_refresh += 1

    if _request_count_since_refresh >= COOKIE_REFRESH_REQUEST_INTERVAL:
        _request_count_since_refresh = 0
        logger.debug(
            f"Request-based cookie refresh triggered "
            f"(every {COOKIE_REFRESH_REQUEST_INTERVAL} requests)"
        )
        return await save_current_cookies_to_profile()

    return False


async def save_cookies_on_shutdown() -> bool:
    """
    Save cookies during graceful shutdown.

    Returns:
        True if cookies were saved successfully, False otherwise.
    """
    if not COOKIE_REFRESH_ON_SHUTDOWN:
        logger.debug("Cookie save on shutdown is disabled")
        return False

    logger.info("💾 Saving cookies before shutdown...")
    return await save_current_cookies_to_profile()


async def _periodic_refresh_loop():
    """
    Background task that periodically saves cookies.
    """
    global _last_refresh_time

    logger.info(
        f"🔄 Periodic cookie refresh started "
        f"(interval: {COOKIE_REFRESH_INTERVAL_SECONDS}s)"
    )

    # Initial delay before first save
    await asyncio.sleep(COOKIE_REFRESH_INTERVAL_SECONDS)

    while True:
        try:
            elapsed = time.time() - _last_refresh_time
            if elapsed >= COOKIE_REFRESH_INTERVAL_SECONDS:
                logger.debug("Periodic cookie refresh triggered")
                await save_current_cookies_to_profile()

            # Sleep until next check
            await asyncio.sleep(min(60, COOKIE_REFRESH_INTERVAL_SECONDS // 2))

        except asyncio.CancelledError:
            logger.info("🔄 Periodic cookie refresh task cancelled")
            raise
        except Exception as e:
            logger.error(f"Error in periodic cookie refresh: {e}")
            # Continue running despite errors
            await asyncio.sleep(60)


def start_periodic_refresh() -> Optional[asyncio.Task]:
    """
    Start the periodic cookie refresh background task.

    Returns:
        The created asyncio task, or None if refresh is disabled.
    """
    global _periodic_task

    if not COOKIE_REFRESH_ENABLED:
        logger.info("Cookie refresh is disabled, not starting periodic task")
        return None

    if _periodic_task is not None and not _periodic_task.done():
        logger.warning("Periodic refresh task already running")
        return _periodic_task

    _periodic_task = asyncio.create_task(_periodic_refresh_loop())
    return _periodic_task


async def stop_periodic_refresh():
    """
    Stop the periodic cookie refresh background task.
    """
    global _periodic_task

    if _periodic_task is not None and not _periodic_task.done():
        _periodic_task.cancel()
        try:
            await _periodic_task
        except asyncio.CancelledError:
            pass
        _periodic_task = None
        logger.info("🔄 Periodic cookie refresh stopped")


def get_refresh_stats() -> dict:
    """
    Get statistics about cookie refresh operations.

    Returns:
        Dict with refresh statistics.
    """
    return {
        "enabled": COOKIE_REFRESH_ENABLED,
        "last_refresh_time": _last_refresh_time,
        "requests_since_refresh": _request_count_since_refresh,
        "refresh_interval_seconds": COOKIE_REFRESH_INTERVAL_SECONDS,
        "request_interval": COOKIE_REFRESH_REQUEST_INTERVAL,
        "periodic_task_running": _periodic_task is not None
        and not _periodic_task.done(),
    }
