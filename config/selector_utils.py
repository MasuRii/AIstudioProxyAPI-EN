# --- config/selector_utils.py ---
"""
Selector Utilities Module
Provides fallback logic for handling dynamic UI structures
"""

import asyncio
import logging
from typing import List, Optional, Tuple

from playwright.async_api import Locator, Page

from config.timeouts import (
    SELECTOR_EXISTENCE_CHECK_TIMEOUT_MS,
    SELECTOR_VISIBILITY_TIMEOUT_MS,
)

logger = logging.getLogger("AIStudioProxyServer")


# --- Input area container selectors (sorted by priority) ---
# Google AI Studio periodically changes UI structure, this list contains all known container selectors
# Priority: try current UI first, fall back to older UIs
# Note: Order matters! First selector is tried first, each failed selector adds to startup time
INPUT_WRAPPER_SELECTORS: List[str] = [
    # Current UI structure (confirmed working 2024-12)
    "ms-chunk-editor",
    # Fallback UI structure (may work in other versions or regions)
    "ms-prompt-input-wrapper .prompt-input-wrapper",
    "ms-prompt-input-wrapper",
    # Transitional UI (ms-prompt-box) - legacy version, kept as fallback
    "ms-prompt-box .prompt-box-container",
    "ms-prompt-box",
]

# --- Autosize wrapper selectors ---
AUTOSIZE_WRAPPER_SELECTORS: List[str] = [
    # Current UI structure
    "ms-prompt-input-wrapper .text-wrapper",
    "ms-prompt-input-wrapper ms-autosize-textarea",
    "ms-chunk-input .text-wrapper",
    "ms-autosize-textarea",
    # Transitional UI (ms-prompt-box) - deprecated but kept as fallback
    "ms-prompt-box .text-wrapper",
    "ms-prompt-box ms-autosize-textarea",
]


async def find_first_visible_locator(
    page: Page,
    selectors: List[str],
    description: str = "element",
    timeout_per_selector: int = SELECTOR_VISIBILITY_TIMEOUT_MS,
    existence_check_timeout: int = SELECTOR_EXISTENCE_CHECK_TIMEOUT_MS,  # kept for API compat
    fallback_timeout_per_selector: int = SELECTOR_VISIBILITY_TIMEOUT_MS,  # kept for API compat
) -> Tuple[Optional[Locator], Optional[str]]:
    """
    Try multiple selectors and return the Locator of the first visible element.

    Uses active DOM listening strategy (Playwright MutationObserver):
    - Uses longer timeout for first selector (primary, most likely to succeed)
    - Uses shorter timeout for subsequent selectors as fallbacks

    Args:
        page: Playwright page instance
        selectors: List of selectors to try (sorted by priority)
        description: Element description (for logging)
        timeout_per_selector: Timeout for primary selector (milliseconds)

    Returns:
        Tuple[Optional[Locator], Optional[str]]:
            - Locator of visible element, or None if all failed
            - Successful selector string, or None if all failed
    """
    from playwright.async_api import expect as expect_async

    if not selectors:
        logger.warning(f"[Selector] {description}: No selectors provided")
        return None, None

    # Primary selector uses longer timeout (most likely to succeed, worth waiting for)
    primary_selector = selectors[0]
    primary_timeout = timeout_per_selector

    # Fallback selectors use shorter timeout
    fallback_timeout = min(2000, timeout_per_selector // 2)

    logger.debug(
        f"[Selector] {description}: Starting active listening for '{primary_selector}' (timeout: {primary_timeout}ms)"
    )

    # Try primary selector (using Playwright's MutationObserver active listening)
    try:
        locator = page.locator(primary_selector)
        await expect_async(locator).to_be_visible(timeout=primary_timeout)
        logger.debug(f"[Selector] {description}: '{primary_selector}' element visible")
        return locator, primary_selector
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.debug(
            f"[Selector] {description}: '{primary_selector}' timeout ({primary_timeout}ms) - {type(e).__name__}"
        )

    # Fall back to other selectors
    if len(selectors) > 1:
        logger.debug(
            f"[Selector] {description}: Trying {len(selectors) - 1} fallback selectors (timeout: {fallback_timeout}ms)"
        )
        for idx, selector in enumerate(selectors[1:], 2):
            try:
                locator = page.locator(selector)
                await expect_async(locator).to_be_visible(timeout=fallback_timeout)
                logger.debug(
                    f"[Selector] {description}: '{selector}' element visible (fallback {idx}/{len(selectors)})"
                )
                return locator, selector
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.debug(
                    f"[Selector] {description}: '{selector}' timeout (fallback {idx}/{len(selectors)})"
                )

    logger.warning(
        f"[Selector] {description}: No visible element found for any selector "
        f"(tried {len(selectors)} selectors)"
    )
    return None, None


def build_combined_selector(selectors: List[str]) -> str:
    """
    Combine multiple selectors into a single CSS selector string (comma-separated).

    This is useful for creating selectors that can match multiple UI structures.

    Args:
        selectors: List of selectors to combine

    Returns:
        str: Combined selector string

    Example:
        combined = build_combined_selector([
            "ms-prompt-box .text-wrapper",
            "ms-prompt-input-wrapper .text-wrapper"
        ])
        # Returns: "ms-prompt-box .text-wrapper, ms-prompt-input-wrapper .text-wrapper"
    """
    return ", ".join(selectors)
