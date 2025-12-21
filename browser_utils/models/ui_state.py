"""
UI State Management
"""

import asyncio
import json
import logging

from playwright.async_api import Page as AsyncPage

from logging_utils import set_request_id

logger = logging.getLogger("AIStudioProxyServer")


async def _verify_ui_state_settings(page: AsyncPage, req_id: str = "unknown") -> dict:
    """
    Verify if the UI state settings are correct.

    Args:
        page: Playwright page object.
        req_id: Request ID for logging.

    Returns:
        dict: A dictionary containing the validation result.
    """
    # Don't set lifecycle phase names as request IDs - they appear as ghost prefixes
    # Only set actual request IDs (7-char alphanumerics)
    if req_id not in ("initial", "set_mod", "set_model", "reload", "unknown", ""):
        set_request_id(req_id)
    try:
        logger.debug("[State] Verifying UI state...")

        # Get current localStorage settings
        prefs_str = await page.evaluate(
            "() => localStorage.getItem('aiStudioUserPreference')"
        )

        if not prefs_str:
            logger.warning("localStorage.aiStudioUserPreference does not exist")
            return {
                "exists": False,
                "isAdvancedOpen": None,
                "areToolsOpen": None,
                "needsUpdate": True,
                "error": "localStorage not found",
            }

        try:
            prefs = json.loads(prefs_str)
            is_advanced_open = prefs.get("isAdvancedOpen")
            are_tools_open = prefs.get("areToolsOpen")

            # Check if update is needed
            needs_update = (is_advanced_open is not True) or (
                are_tools_open is not True
            )

            result = {
                "exists": True,
                "isAdvancedOpen": is_advanced_open,
                "areToolsOpen": are_tools_open,
                "needsUpdate": needs_update,
                "prefs": prefs,
            }

            if needs_update:
                logger.debug(
                    f"[State] State mismatch: adv={is_advanced_open}, tools={are_tools_open} (update needed)"
                )
            # No log needed when state is correct
            return result

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse localStorage JSON: {e}")
            return {
                "exists": False,
                "isAdvancedOpen": None,
                "areToolsOpen": None,
                "needsUpdate": True,
                "error": f"JSON parse failed: {e}",
            }

    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"Error verifying UI state settings: {e}")
        return {
            "exists": False,
            "isAdvancedOpen": None,
            "areToolsOpen": None,
            "needsUpdate": True,
            "error": f"Verification failed: {e}",
        }


async def _force_ui_state_settings(page: AsyncPage, req_id: str = "unknown") -> bool:
    """
    Forcefully set the UI state.

    Args:
        page: Playwright page object.
        req_id: Request ID for logging.

    Returns:
        bool: Whether the setting was successful.
    """
    try:
        logger.debug("[State] Forcefully setting UI state...")

        # First verify current state
        current_state = await _verify_ui_state_settings(page, req_id)

        if not current_state["needsUpdate"]:
            logger.debug("[State] State is already correct, no update needed")
            return True

        # Get existing preferences or create new ones
        prefs = current_state.get("prefs", {})

        # Force key configurations
        prefs["isAdvancedOpen"] = True
        prefs["areToolsOpen"] = True

        # Save to localStorage
        prefs_str = json.dumps(prefs)
        await page.evaluate(
            "(prefsStr) => localStorage.setItem('aiStudioUserPreference', prefsStr)",
            prefs_str,
        )

        logger.debug("[State] Set: isAdvancedOpen=true, areToolsOpen=true")

        # Verify if setting was successful
        verify_state = await _verify_ui_state_settings(page, req_id)
        if not verify_state["needsUpdate"]:
            logger.debug("[State] Setting verification successful")
            return True
        else:
            logger.warning("UI state setting verification failed, may need to retry")
            return False

    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"Error forcefully setting UI state: {e}")
        return False


async def _force_ui_state_with_retry(
    page: AsyncPage,
    req_id: str = "unknown",
    max_retries: int = 3,
    retry_delay: float = 1.0,
) -> bool:
    """
    Forcefully set UI state with retry mechanism.

    Args:
        page: Playwright page object.
        req_id: Request ID for logging.
        max_retries: Maximum number of retries.
        retry_delay: Retry delay (seconds).

    Returns:
        bool: Whether the setting was ultimately successful.
    """
    for attempt in range(1, max_retries + 1):
        success = await _force_ui_state_settings(page, req_id)
        if success:
            return True

        if attempt < max_retries:
            logger.debug(f"[State] Retrying {attempt}/{max_retries}...")
            await asyncio.sleep(retry_delay)
        else:
            logger.warning(f"[State] Still failed after {max_retries} attempts")

    return False


async def _verify_and_apply_ui_state(page: AsyncPage, req_id: str = "unknown") -> bool:
    """
    Full process of verifying and applying UI state settings.

    Args:
        page: Playwright page object.
        req_id: Request ID for logging.

    Returns:
        bool: Whether the operation was successful.
    """
    try:
        logger.debug("[State] Starting to verify and apply UI state...")

        # First verify current state
        state = await _verify_ui_state_settings(page, req_id)

        if state["needsUpdate"]:
            logger.debug("[State] Update needed, applying forced settings...")
            return await _force_ui_state_with_retry(page, req_id)
        else:
            return True

    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"Error during verifying and applying UI state: {e}")
        return False
