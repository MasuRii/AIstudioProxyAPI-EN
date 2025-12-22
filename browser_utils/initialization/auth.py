# --- browser_utils/initialization/auth.py ---
"""
Authentication Saving Module - Simplified Version

Handles saving authentication state after login. Automatically saves to SAVED_AUTH_DIR.
"""

import asyncio
import logging
import os
import time

from config import SAVED_AUTH_DIR

logger = logging.getLogger("AIStudioProxyServer")


async def wait_for_model_list_and_handle_auth_save(temp_context, launch_mode, loop):
    """Wait for model list response and handle authentication saving"""
    from api_utils.server_state import state

    # Wait for model list response to confirm login success
    logger.info("Waiting for model list response to confirm login success...")
    try:
        await asyncio.wait_for(state.model_list_fetch_event.wait(), timeout=30.0)
        logger.info("Model list response detected, login confirmed!")
    except asyncio.TimeoutError:
        logger.warning(
            "Timeout waiting for model list response, but continuing with auth save..."
        )

    # Determine filename: env var > auto-generate
    filename = os.environ.get("SAVE_AUTH_FILENAME", "").strip()
    if not filename:
        filename = f"auth_auto_{int(time.time())}"

    await _save_auth_state(temp_context, filename)


async def _save_auth_state(temp_context, filename: str):
    """Unified authentication saving function"""
    os.makedirs(SAVED_AUTH_DIR, exist_ok=True)

    if not filename.endswith(".json"):
        filename += ".json"
    auth_save_path = os.path.join(SAVED_AUTH_DIR, filename)

    print("\n" + "=" * 50, flush=True)
    print("Login successful! Saving authentication state...", flush=True)

    try:
        await temp_context.storage_state(path=auth_save_path)
        logger.info(f"Authentication state saved to: {auth_save_path}")
        print(f"Authentication state saved to: {auth_save_path}", flush=True)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"Failed to save authentication state: {e}", exc_info=True)
        print(f"Failed to save authentication state: {e}", flush=True)

    print("=" * 50 + "\n", flush=True)
