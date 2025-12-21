import asyncio
from typing import Callable

from playwright.async_api import TimeoutError
from playwright.async_api import expect as expect_async

from browser_utils.initialization import enable_temporary_chat_mode
from browser_utils.operations import save_error_snapshot
from config import (
    CLEAR_CHAT_BUTTON_SELECTOR,
    CLEAR_CHAT_CONFIRM_BUTTON_SELECTOR,
    CLEAR_CHAT_VERIFY_TIMEOUT_MS,
    CLICK_TIMEOUT_MS,
    OVERLAY_SELECTOR,
    RESPONSE_CONTAINER_SELECTOR,
    SUBMIT_BUTTON_SELECTOR,
    WAIT_FOR_ELEMENT_TIMEOUT_MS,
)
from models import ClientDisconnectedError

from .base import BaseController


class ChatController(BaseController):
    """Handles chat history management."""

    async def clear_chat_history(self, check_client_disconnected: Callable):
        """Clear chat history."""
        self.logger.debug("[Chat] Starting to clear chat history")
        await self._check_disconnect(check_client_disconnected, "Start Clear Chat")

        try:
            # Usually encountered when using stream proxy, stream output ended but AI keeps replying on page,
            # locking the clear button while page remains at /new_chat, skipping subsequent clear operation
            # leading to stuck requests, so check and click submit button first (acting as stop feature)
            submit_button_locator = self.page.locator(SUBMIT_BUTTON_SELECTOR)
            try:
                self.logger.debug("[Chat] Checking submit button status...")
                # Use short timeout (1s) to avoid long blocking as this isn't a common step in clear flow
                await expect_async(submit_button_locator).to_be_enabled(timeout=1000)
                self.logger.debug(
                    "[Chat] Submit button available, clicking and waiting 1 second..."
                )
                await submit_button_locator.click(timeout=CLICK_TIMEOUT_MS)
                try:
                    await expect_async(submit_button_locator).to_be_disabled(
                        timeout=1200
                    )
                except Exception:
                    pass
                self.logger.debug("[Chat] Submit button click completed")
            except asyncio.CancelledError:
                raise
            except Exception:
                # If submit button unavailable, timeout, or Playwright error occurs, log and continue
                self.logger.debug(
                    "[Cleanup] Submit button unavailable/Playwright error (expected), continuing to check clear button"
                )

            clear_chat_button_locator = self.page.locator(CLEAR_CHAT_BUTTON_SELECTOR)
            confirm_button_locator = self.page.locator(
                CLEAR_CHAT_CONFIRM_BUTTON_SELECTOR
            )
            overlay_locator = self.page.locator(OVERLAY_SELECTOR)

            can_attempt_clear = False
            try:
                await expect_async(clear_chat_button_locator).to_be_enabled(
                    timeout=3000
                )
                can_attempt_clear = True
                self.logger.debug("[Chat] Clear button available")
            except Exception as e_enable:
                is_new_chat_url = "/prompts/new_chat" in self.page.url.rstrip("/")
                if is_new_chat_url:
                    self.logger.info(
                        '"Clear Chat" button unavailable (expected on new_chat page). Skipping clear operation.'
                    )
                else:
                    self.logger.warning(
                        f'Waiting for "Clear Chat" button to become enabled failed: {e_enable}. Clear operation may not be executed.'
                    )

            await self._check_disconnect(
                check_client_disconnected,
                'Clear Chat - after "Clear Chat" button availability check',
            )

            if can_attempt_clear:
                await self._execute_chat_clear(
                    clear_chat_button_locator,
                    confirm_button_locator,
                    overlay_locator,
                    check_client_disconnected,
                )
                await self._verify_chat_cleared(check_client_disconnected)
                self.logger.debug("[Chat] Re-enabling temporary chat mode")
                await enable_temporary_chat_mode(self.page)

        except Exception as e_clear:
            if isinstance(e_clear, asyncio.CancelledError):
                raise
            self.logger.error(f"Error occurred during clearing chat: {e_clear}")
            error_name = getattr(e_clear, "name", "")
            if not (
                isinstance(e_clear, ClientDisconnectedError)
                or (error_name and "Disconnect" in error_name)
            ):
                # Capture locator states for debugging
                clear_btn_loc = self.page.locator(CLEAR_CHAT_BUTTON_SELECTOR)
                confirm_btn_loc = self.page.locator(CLEAR_CHAT_CONFIRM_BUTTON_SELECTOR)
                submit_btn_loc = self.page.locator(SUBMIT_BUTTON_SELECTOR)
                overlay_loc = self.page.locator(OVERLAY_SELECTOR)

                await save_error_snapshot(
                    f"clear_chat_error_{self.req_id}",
                    error_exception=e_clear,
                    error_stage="Clear chat flow exception",
                    additional_context={
                        "page_url": self.page.url,
                        "is_new_chat_page": "/prompts/new_chat" in self.page.url,
                    },
                    locators={
                        "clear_chat_button": clear_btn_loc,
                        "confirm_button": confirm_btn_loc,
                        "submit_button": submit_btn_loc,
                        "overlay": overlay_loc,
                    },
                )
            raise

    async def _execute_chat_clear(
        self,
        clear_chat_button_locator,
        confirm_button_locator,
        overlay_locator,
        check_client_disconnected: Callable,
    ):
        """Execute clear chat operation"""
        overlay_initially_visible = False
        try:
            if await overlay_locator.is_visible(timeout=1000):
                overlay_initially_visible = True
                self.logger.debug(
                    "[Chat] Confirmation dialog already visible, clicking 'Continue' directly"
                )
        except TimeoutError:
            overlay_initially_visible = False
        except Exception:
            overlay_initially_visible = False
        except Exception as e_vis_check:
            self.logger.warning(
                f"Error checking overlay visibility: {e_vis_check}. Assuming invisible."
            )
            overlay_initially_visible = False

        await self._check_disconnect(
            check_client_disconnected, "Clear Chat - after initial overlay check"
        )

        if overlay_initially_visible:
            self.logger.debug("[Chat] Clicking 'Continue' button")
            await confirm_button_locator.click(timeout=CLICK_TIMEOUT_MS)
        else:
            self.logger.debug("[Chat] Clicking 'Clear Chat' button")
            # If transparent overlays intercept pointer events, try to clear first
            try:
                await self._dismiss_backdrops()
            except asyncio.CancelledError:
                raise
            except Exception:
                pass
            try:
                try:
                    await clear_chat_button_locator.scroll_into_view_if_needed()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    pass
                await clear_chat_button_locator.click(timeout=CLICK_TIMEOUT_MS)
            except asyncio.CancelledError:
                raise
            except Exception as first_click_err:
                self.logger.warning(
                    f"First click on clear button failed, attempting to clear overlay and force click: {first_click_err}"
                )
                try:
                    await self._dismiss_backdrops()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    pass
                try:
                    await clear_chat_button_locator.click(
                        timeout=CLICK_TIMEOUT_MS, force=True
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as force_click_err:
                    self.logger.error(
                        f"Force click on clear button still failed: {force_click_err}"
                    )
                    raise
            await self._check_disconnect(
                check_client_disconnected, 'Clear Chat - after clicking "Clear Chat"'
            )

            try:
                self.logger.debug("[Chat] Waiting for confirmation dialog...")
                await expect_async(overlay_locator).to_be_visible(
                    timeout=WAIT_FOR_ELEMENT_TIMEOUT_MS
                )
            except TimeoutError:
                error_msg = f"Timed out waiting for clear chat confirmation overlay (after clicking clear button). Request ID: {self.req_id}"
                self.logger.error(error_msg)
                await save_error_snapshot(f"clear_chat_overlay_timeout_{self.req_id}")
                raise Exception(error_msg)

            await self._check_disconnect(
                check_client_disconnected, "Clear Chat - after overlay appeared"
            )
            self.logger.debug("[Chat] Clicking 'Continue' button")
            try:
                await confirm_button_locator.scroll_into_view_if_needed()
            except asyncio.CancelledError:
                raise
            except Exception:
                pass
            try:
                await confirm_button_locator.click(timeout=CLICK_TIMEOUT_MS)
            except asyncio.CancelledError:
                raise
            except Exception as confirm_err:
                # Check if button/dialog has disappeared (operation succeeded)
                err_str = str(confirm_err).lower()
                if "detached" in err_str or "not stable" in err_str:
                    try:
                        is_dialog_visible = await overlay_locator.is_visible(
                            timeout=500
                        )
                        if not is_dialog_visible:
                            self.logger.debug(
                                "[Chat] Dialog disappeared upon click, clear operation succeeded"
                            )
                            return  # Success
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        pass
                self.logger.warning(
                    f'First click on "Continue" failed, attempting force click: {confirm_err}'
                )
                try:
                    await confirm_button_locator.click(
                        timeout=CLICK_TIMEOUT_MS, force=True
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as confirm_force_err:
                    # Check again if dialog has disappeared
                    force_err_str = str(confirm_force_err).lower()
                    if "detached" in force_err_str or "not stable" in force_err_str:
                        try:
                            is_dialog_visible = await overlay_locator.is_visible(
                                timeout=500
                            )
                            if not is_dialog_visible:
                                self.logger.debug(
                                    "[Chat] Dialog disappeared upon force click, clear operation succeeded"
                                )
                                return
                        except asyncio.CancelledError:
                            raise
                        except Exception:
                            pass
                    self.logger.error(
                        f'Force click on "Continue" button still failed: {confirm_force_err}'
                    )
                    raise

        await self._check_disconnect(
            check_client_disconnected, 'Clear Chat - after clicking "Continue"'
        )

        # Wait for dialog to disappear
        max_retries_disappear = 3
        for attempt_disappear in range(max_retries_disappear):
            try:
                self.logger.debug(
                    f"[Chat] Waiting for dialog to disappear ({attempt_disappear + 1}/{max_retries_disappear})"
                )
                await expect_async(confirm_button_locator).to_be_hidden(
                    timeout=CLEAR_CHAT_VERIFY_TIMEOUT_MS
                )
                await expect_async(overlay_locator).to_be_hidden(timeout=1000)
                self.logger.debug("[Chat] Dialog disappeared")
                break
            except TimeoutError:
                self.logger.warning(
                    f"Timed out waiting for clear chat confirmation dialog to disappear (attempt {attempt_disappear + 1}/{max_retries_disappear})."
                )
                if attempt_disappear < max_retries_disappear - 1:
                    await self._check_disconnect(
                        check_client_disconnected,
                        f"Clear Chat - before retry disappear check {attempt_disappear + 1}",
                    )
                    continue
                else:
                    error_msg = f"Reached maximum retries. Clear chat confirmation dialog did not disappear. Request ID: {self.req_id}"
                    self.logger.error(error_msg)
                    await save_error_snapshot(
                        f"clear_chat_dialog_disappear_timeout_{self.req_id}"
                    )
                    raise Exception(error_msg)
            except ClientDisconnectedError:
                self.logger.info(
                    "Client disconnected while waiting for clear confirmation dialog to disappear."
                )
                raise
            except Exception as other_err:
                if isinstance(other_err, asyncio.CancelledError):
                    raise
                self.logger.warning(
                    f"Unexpected error waiting for clear confirmation dialog to disappear: {other_err}"
                )
                if attempt_disappear < max_retries_disappear - 1:
                    continue
                else:
                    raise

    async def _dismiss_backdrops(self):
        """Attempt to close potentially remaining cdk transparent overlays to avoid intercepting clicks."""
        try:
            backdrop = self.page.locator(
                "div.cdk-overlay-backdrop.cdk-overlay-backdrop-showing, div.cdk-overlay-backdrop.cdk-overlay-transparent-backdrop.cdk-overlay-backdrop-showing"
            )
            for i in range(3):
                cnt = 0
                try:
                    cnt = await backdrop.count()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    cnt = 0
                if cnt and cnt > 0:
                    self.logger.debug(
                        f"Detected transparent overlay ({cnt}), sending ESC to close (attempt {i + 1}/3)."
                    )
                    try:
                        await self.page.keyboard.press("Escape")
                        try:
                            await expect_async(backdrop).to_be_hidden(timeout=500)
                        except asyncio.CancelledError:
                            raise
                        except Exception:
                            pass
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        pass
                else:
                    break
        except asyncio.CancelledError:
            raise
        except Exception:
            pass

    async def _verify_chat_cleared(self, check_client_disconnected: Callable):
        """Verify chat has been cleared"""
        last_response_container = self.page.locator(RESPONSE_CONTAINER_SELECTOR).last
        await self._check_disconnect(
            check_client_disconnected, "After Clear Post-Check"
        )
        try:
            await expect_async(last_response_container).to_be_hidden(
                timeout=CLEAR_CHAT_VERIFY_TIMEOUT_MS - 500
            )
            self.logger.debug("[Chat] Verification passed, response container hidden")
        except asyncio.CancelledError:
            raise
        except Exception as verify_err:
            self.logger.warning(
                f"Warning: Clear chat verification failed (last response container not hidden): {verify_err}"
            )
