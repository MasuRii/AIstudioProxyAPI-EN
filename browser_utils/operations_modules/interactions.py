# --- browser_utils/operations_modules/interactions.py ---
import asyncio
import logging
import time
from typing import Callable, Optional

from playwright.async_api import (
    Error as PlaywrightAsyncError,
)
from playwright.async_api import (
    Locator,
)
from playwright.async_api import (
    Page as AsyncPage,
)

from browser_utils.operations_modules.errors import save_error_snapshot
from config import (
    CHAT_TURN_SELECTOR,
    CLICK_TIMEOUT_MS,
    DEBUG_LOGS_ENABLED,
    INITIAL_WAIT_MS_BEFORE_POLLING,
    RESPONSE_COMPLETION_TIMEOUT,
)
from models import ClientDisconnectedError

logger = logging.getLogger("AIStudioProxyServer")


async def get_raw_text_content(
    response_element: Locator, previous_text: str, req_id: str
) -> str:
    """Get raw text content from the response element."""
    raw_text = previous_text
    try:
        await response_element.wait_for(state="attached", timeout=1000)
        pre_element = response_element.locator("pre").last
        pre_found_and_visible = False
        try:
            await pre_element.wait_for(state="visible", timeout=250)
            pre_found_and_visible = True
        except PlaywrightAsyncError:
            pass

        if pre_found_and_visible:
            try:
                raw_text = await pre_element.inner_text(timeout=500)
            except PlaywrightAsyncError as pre_err:
                if DEBUG_LOGS_ENABLED:
                    logger.debug(
                        f"(GetRawText) Failed to get inner text of pre element: {pre_err}"
                    )
        else:
            try:
                raw_text = await response_element.inner_text(timeout=500)
            except PlaywrightAsyncError as e_parent:
                if DEBUG_LOGS_ENABLED:
                    logger.debug(
                        f"(GetRawText) Failed to get inner text of response element: {e_parent}"
                    )
    except PlaywrightAsyncError as e_parent:
        if DEBUG_LOGS_ENABLED:
            logger.debug(f"(GetRawText) Response element not ready: {e_parent}")
    except asyncio.CancelledError:
        raise
    except Exception as e_unexpected:
        logger.warning(f"(GetRawText) Unexpected error: {e_unexpected}")

    if raw_text != previous_text:
        if DEBUG_LOGS_ENABLED:
            preview = raw_text[:100].replace("\n", "\\n")
            logger.debug(
                f"(GetRawText) Text updated, length: {len(raw_text)}, Preview: '{preview}...'"
            )
    return raw_text


async def get_response_via_edit_button(
    page: AsyncPage, req_id: str, check_client_disconnected: Callable
) -> Optional[str]:
    """Get response via the edit button."""
    logger.info("(Helper) Attempting to get response via edit button...")
    last_message_container = page.locator(CHAT_TURN_SELECTOR).last
    edit_button = last_message_container.get_by_label("Edit")
    finish_edit_button = last_message_container.get_by_label("Stop editing")
    autosize_textarea_locator = last_message_container.locator("ms-autosize-textarea")
    actual_textarea_locator = last_message_container.locator("textarea")

    try:
        logger.info(
            "- Attempting to hover over the last message to show 'Edit' button..."
        )
        try:
            # Perform hover on message container
            await last_message_container.hover(
                timeout=CLICK_TIMEOUT_MS / 2
            )  # Use half click timeout for hover
            await asyncio.sleep(0.3)  # Wait for hover effect
            check_client_disconnected("Edit Response - after hover: ")
        except asyncio.CancelledError:
            raise
        except ClientDisconnectedError:
            raise
        except Exception as hover_err:
            logger.warning(
                f"   - (get_response_via_edit_button) Hover over last message failed (ignoring): {type(hover_err).__name__}"
            )

        logger.info("- Locating and clicking 'Edit' button...")
        try:
            from playwright.async_api import expect as expect_async

            await expect_async(edit_button).to_be_visible(timeout=CLICK_TIMEOUT_MS)
            check_client_disconnected("Edit Response - 'Edit' button visible: ")
            await edit_button.click(timeout=CLICK_TIMEOUT_MS)
            logger.info("- 'Edit' button clicked.")
        except asyncio.CancelledError:
            raise
        except Exception as edit_btn_err:
            logger.error(
                f"   - 'Edit' button not visible or click failed: {edit_btn_err}",
                exc_info=True,
            )
            await save_error_snapshot(f"edit_response_edit_button_failed_{req_id}")
            return None

        check_client_disconnected("Edit Response - after clicking 'Edit' button: ")
        await asyncio.sleep(0.3)
        check_client_disconnected(
            "Edit Response - after delay following 'Edit' click: "
        )

        logger.info("- Retrieving content from textarea...")
        response_content = None
        textarea_failed = False

        try:
            target_locator = autosize_textarea_locator
            if await target_locator.count() == 0:
                target_locator = actual_textarea_locator

            if await target_locator.count() == 0:
                raise RuntimeError("No editable textarea found")

            await expect_async(target_locator).to_be_visible(timeout=CLICK_TIMEOUT_MS)
            check_client_disconnected("Edit Response - textarea visible: ")

            if await autosize_textarea_locator.count() > 0 and response_content is None:
                try:
                    data_value_content = await autosize_textarea_locator.get_attribute(
                        "data-value"
                    )
                    check_client_disconnected(
                        "Edit Response - after get_attribute data-value: "
                    )
                    if data_value_content is not None:
                        response_content = str(data_value_content)
                        logger.info("- Successfully obtained content from data-value.")
                except asyncio.CancelledError:
                    raise
                except Exception as data_val_err:
                    logger.warning(f"- Failed to get data-value: {data_val_err}")
                    check_client_disconnected(
                        "Edit Response - after get_attribute data-value error: "
                    )

            if response_content is None and await actual_textarea_locator.count() > 0:
                logger.info(
                    "   - data-value retrieval failed or does not exist, attempting input_value from textarea..."
                )
                try:
                    await expect_async(actual_textarea_locator).to_be_visible(
                        timeout=CLICK_TIMEOUT_MS / 2
                    )
                    input_val_content = await actual_textarea_locator.input_value(
                        timeout=CLICK_TIMEOUT_MS / 2
                    )
                    check_client_disconnected("Edit Response - after input_value: ")
                    response_content = str(input_val_content)
                    logger.info("- Successfully obtained content from input_value.")
                except asyncio.CancelledError:
                    raise
                except Exception as input_val_err:
                    logger.warning(
                        f"- Failed to get input_value as well: {input_val_err}"
                    )
                    check_client_disconnected(
                        "Edit Response - after input_value error: "
                    )

            if response_content is not None:
                response_content = response_content.strip()
                content_preview = response_content[:100].replace("\\n", "\\\\n")
                logger.info(
                    f"   - Final content retrieved (length={len(response_content)}): '{content_preview}...'"
                )
            else:
                logger.warning(
                    "   - All content retrieval methods (data-value, input_value) failed or returned None."
                )
                textarea_failed = True

        except asyncio.CancelledError:
            raise
        except Exception as textarea_err:
            logger.error(
                f"   - Failed to locate or process textarea: {textarea_err}",
                exc_info=True,
            )
            textarea_failed = True
            response_content = None
            check_client_disconnected("Edit Response - after textarea error: ")

        if not textarea_failed:
            logger.info("- Locating and clicking 'Stop editing' button...")
            try:
                await expect_async(finish_edit_button).to_be_visible(
                    timeout=CLICK_TIMEOUT_MS
                )
                check_client_disconnected(
                    "Edit Response - 'Stop editing' button visible: "
                )
                await finish_edit_button.click(timeout=CLICK_TIMEOUT_MS)
                logger.info("- 'Stop editing' button clicked.")
            except asyncio.CancelledError:
                raise
            except Exception as finish_btn_err:
                logger.warning(
                    f"   - 'Stop editing' button not visible or click failed: {finish_btn_err}"
                )
                await save_error_snapshot(
                    f"edit_response_finish_button_failed_{req_id}"
                )
            check_client_disconnected("Edit Response - after clicking 'Stop editing': ")
            await asyncio.sleep(0.2)
            check_client_disconnected(
                "Edit Response - after delay following 'Stop editing' click: "
            )
        else:
            logger.info(
                "- Skipping 'Stop editing' button click due to textarea read failure."
            )

        return response_content

    except ClientDisconnectedError:
        logger.info("(Helper Edit) Client disconnected.")
        raise
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Unexpected error during response retrieval via edit button")
        await save_error_snapshot(f"edit_response_unexpected_error_{req_id}")
        return None


async def get_response_via_copy_button(
    page: AsyncPage, req_id: str, check_client_disconnected: Callable
) -> Optional[str]:
    """Get response via the copy button."""
    logger.info("(Helper) Attempting to get response via copy button...")
    last_message_container = page.locator(CHAT_TURN_SELECTOR).last
    more_options_button = last_message_container.get_by_label("Open options")
    copy_markdown_button = page.get_by_role("menuitem", name="Copy markdown")

    try:
        logger.info("- Attempting to hover over the last message to show options...")
        await last_message_container.hover(timeout=CLICK_TIMEOUT_MS)
        check_client_disconnected("Copy Response - after hover: ")
        await asyncio.sleep(0.5)
        check_client_disconnected("Copy Response - after hover delay: ")
        logger.info("- Hovered.")

        logger.info("- Locating and clicking 'More options' button...")
        try:
            from playwright.async_api import expect as expect_async

            await expect_async(more_options_button).to_be_visible(
                timeout=CLICK_TIMEOUT_MS
            )
            check_client_disconnected("Copy Response - 'More options' button visible: ")
            await more_options_button.click(timeout=CLICK_TIMEOUT_MS)
            logger.info("- 'More options' clicked (via get_by_label).")
        except asyncio.CancelledError:
            raise
        except Exception as more_opts_err:
            logger.error(
                f"   - 'More options' button (via get_by_label) not visible or click failed: {more_opts_err}"
            )
            await save_error_snapshot(f"copy_response_more_options_failed_{req_id}")
            return None

        check_client_disconnected("Copy Response - after clicking more options: ")
        await asyncio.sleep(0.5)
        check_client_disconnected(
            "Copy Response - after delay following more options click: "
        )

        logger.info("- Locating and clicking 'Copy markdown' button...")
        copy_success = False
        try:
            await expect_async(copy_markdown_button).to_be_visible(
                timeout=CLICK_TIMEOUT_MS
            )
            check_client_disconnected("Copy Response - copy button visible: ")
            await copy_markdown_button.click(timeout=CLICK_TIMEOUT_MS, force=True)
            copy_success = True
            logger.info("- 'Copy markdown' clicked (via get_by_role).")
        except asyncio.CancelledError:
            raise
        except Exception as copy_err:
            logger.error(
                f"   - 'Copy markdown' button (via get_by_role) click failed: {copy_err}"
            )
            await save_error_snapshot(f"copy_response_copy_button_failed_{req_id}")
            return None

        if not copy_success:
            logger.error("- Failed to click 'Copy markdown' button.")
            return None

        check_client_disconnected("Copy Response - after clicking copy button: ")
        await asyncio.sleep(0.5)
        check_client_disconnected(
            "Copy Response - after delay following copy button click: "
        )

        logger.info("- Reading clipboard content...")
        try:
            clipboard_content = await page.evaluate("navigator.clipboard.readText()")
            check_client_disconnected("Copy Response - after reading clipboard: ")
            if clipboard_content:
                content_preview = clipboard_content[:100].replace("\n", "\\\\n")
                logger.info(
                    f"   - Successfully obtained clipboard content (length={len(clipboard_content)}): '{content_preview}...'"
                )
                return clipboard_content
            else:
                logger.error("- Clipboard content is empty.")
                return None
        except asyncio.CancelledError:
            raise
        except Exception as clipboard_err:
            if "clipboard-read" in str(clipboard_err):
                logger.error(
                    f"   - Clipboard read failed: possible permissions issue. Error: {clipboard_err}"
                )
            else:
                logger.error(f"- Clipboard read failed: {clipboard_err}", exc_info=True)
            await save_error_snapshot(f"copy_response_clipboard_read_failed_{req_id}")
            return None

    except ClientDisconnectedError:
        logger.info("(Helper Copy) Client disconnected.")
        raise
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Unexpected error during response retrieval via copy button")
        await save_error_snapshot(f"copy_response_unexpected_error_{req_id}")
        return None


async def _wait_for_response_completion(
    page: AsyncPage,
    prompt_textarea_locator: Locator,
    submit_button_locator: Locator,
    edit_button_locator: Locator,
    req_id: str,
    check_client_disconnected_func: Callable,
    timeout_ms=RESPONSE_COMPLETION_TIMEOUT,
    initial_wait_ms=INITIAL_WAIT_MS_BEFORE_POLLING,
) -> bool:
    """Wait for response completion."""
    from playwright.async_api import TimeoutError

    logger.info(
        f"(WaitV3) Waiting for response completion... (Timeout: {timeout_ms}ms)"
    )
    await asyncio.sleep(initial_wait_ms / 1000)

    start_time = time.time()
    wait_timeout_ms_short = 3000

    consecutive_empty_input_submit_disabled_count = 0

    while True:
        try:
            check_client_disconnected_func("Wait for completion - loop start")
        except ClientDisconnectedError:
            logger.info("(WaitV3) Client disconnected, aborting wait.")
            return False

        current_time_elapsed_ms = (time.time() - start_time) * 1000
        if current_time_elapsed_ms > timeout_ms:
            logger.error(
                f"(WaitV3) Timed out waiting for response completion ({timeout_ms}ms)."
            )
            await save_error_snapshot(f"wait_completion_v3_overall_timeout_{req_id}")
            return False

        try:
            check_client_disconnected_func("Wait for completion - after timeout check")
        except ClientDisconnectedError:
            return False

        # --- Primary conditions: Input empty & Submit disabled ---
        is_input_empty = await prompt_textarea_locator.input_value() == ""
        is_submit_disabled = False
        try:
            is_submit_disabled = await submit_button_locator.is_disabled(
                timeout=wait_timeout_ms_short
            )
        except TimeoutError:
            logger.warning(
                "(WaitV3) Timed out checking if submit button is disabled. Assuming not disabled for this check."
            )

        try:
            check_client_disconnected_func(
                "Wait for completion - after button status check"
            )
        except ClientDisconnectedError:
            return False

        if is_input_empty and is_submit_disabled:
            consecutive_empty_input_submit_disabled_count += 1
            if DEBUG_LOGS_ENABLED:
                logger.debug(
                    f"(WaitV3) Primary conditions met: Input empty, submit disabled (count: {consecutive_empty_input_submit_disabled_count})."
                )

            # --- Final confirmation: Edit button visible ---
            try:
                if await edit_button_locator.is_visible(timeout=wait_timeout_ms_short):
                    logger.info(
                        "(WaitV3) Response complete: Input empty, submit disabled, edit button visible."
                    )
                    return True
            except TimeoutError:
                if DEBUG_LOGS_ENABLED:
                    logger.debug(
                        "(WaitV3) After primary conditions met, check for edit button visibility timed out."
                    )

            try:
                check_client_disconnected_func(
                    "Wait for completion - after edit button check"
                )
            except ClientDisconnectedError:
                return False

            # Heuristic completion
            if consecutive_empty_input_submit_disabled_count >= 3:
                logger.warning(
                    f"(WaitV3) Response might be complete (heuristic): Input empty, submit disabled, but edit button still has not appeared after {consecutive_empty_input_submit_disabled_count} checks. Assuming complete."
                )
                return True
        else:
            consecutive_empty_input_submit_disabled_count = 0
            if DEBUG_LOGS_ENABLED:
                reasons = []
                if not is_input_empty:
                    reasons.append("input not empty")
                if not is_submit_disabled:
                    reasons.append("submit button not disabled")
                logger.debug(
                    f"(WaitV3) Primary conditions not met ({', '.join(reasons)}). Continuing polling..."
                )

        await asyncio.sleep(0.5)


async def _get_final_response_content(
    page: AsyncPage, req_id: str, check_client_disconnected: Callable
) -> Optional[str]:
    """Get final response content."""
    logger.info("(Helper GetContent) Starting to get final response content...")
    response_content = await get_response_via_edit_button(
        page, req_id, check_client_disconnected
    )
    if response_content is not None:
        logger.info(
            "(Helper GetContent) Successfully obtained content via edit button."
        )
        return response_content

    logger.warning(
        "(Helper GetContent) Edit button method failed or returned empty, falling back to copy button method..."
    )
    response_content = await get_response_via_copy_button(
        page, req_id, check_client_disconnected
    )
    if response_content is not None:
        logger.info(
            "(Helper GetContent) Successfully obtained content via copy button."
        )
        return response_content

    logger.error("(Helper GetContent) All response content retrieval methods failed.")
    await save_error_snapshot(f"get_content_all_methods_failed_{req_id}")
    return None
