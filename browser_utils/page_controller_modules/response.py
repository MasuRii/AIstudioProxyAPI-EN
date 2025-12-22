import asyncio
from typing import Callable, Optional

from playwright.async_api import expect as expect_async

from browser_utils.operations import (
    _get_final_response_content,
    _wait_for_response_completion,
    save_error_snapshot,
)
from config import (
    EDIT_MESSAGE_BUTTON_SELECTOR,
    PROMPT_TEXTAREA_SELECTOR,
    RESPONSE_CONTAINER_SELECTOR,
    RESPONSE_TEXT_SELECTOR,
    SUBMIT_BUTTON_SELECTOR,
)
from logging_utils import set_request_id
from models import ClientDisconnectedError

from .base import BaseController


class ResponseController(BaseController):
    """Handles retrieval of AI responses."""

    async def get_response(
        self,
        check_client_disconnected: Callable,
        prompt_length: int = 0,
        timeout: Optional[float] = None,
    ) -> str:
        """Retrieve response content."""
        set_request_id(self.req_id)
        self.logger.debug("[Response] Waiting for and retrieving response...")

        try:
            # Wait for response container
            response_container_locator = self.page.locator(
                RESPONSE_CONTAINER_SELECTOR
            ).last
            response_element_locator = response_container_locator.locator(
                RESPONSE_TEXT_SELECTOR
            )

            self.logger.debug(
                "[Response] Waiting for response element to be attached to DOM..."
            )
            await expect_async(response_element_locator).to_be_attached(timeout=90000)
            await self._check_disconnect(
                check_client_disconnected,
                "Retrieve Response - Response element attached",
            )

            # Wait for response completion
            submit_button_locator = self.page.locator(SUBMIT_BUTTON_SELECTOR)
            edit_button_locator = self.page.locator(EDIT_MESSAGE_BUTTON_SELECTOR)
            input_field_locator = self.page.locator(PROMPT_TEXTAREA_SELECTOR)

            self.logger.debug("[Response] Waiting for response completion...")
            completion_detected = await _wait_for_response_completion(
                self.page,
                input_field_locator,
                submit_button_locator,
                edit_button_locator,
                self.req_id,
                check_client_disconnected,
                None,
                prompt_length=prompt_length,
                timeout=timeout,
            )

            if not completion_detected:
                self.logger.warning(
                    "Response completion detection failed, attempting to retrieve current content"
                )
            else:
                self.logger.debug("[Response] Response completion detection successful")

            # Get final response content
            final_content = await _get_final_response_content(
                self.page, self.req_id, check_client_disconnected
            )

            if not final_content or not final_content.strip():
                self.logger.warning("Retrieved response content is empty")
                await save_error_snapshot(f"empty_response_{self.req_id}")
                # Do not raise exception, return empty content to let caller handle
                return ""

            self.logger.debug(
                f"[Response] Successfully retrieved content ({len(final_content)} chars)"
            )
            return final_content

        except Exception as e:
            if isinstance(e, asyncio.CancelledError):
                self.logger.info("Retrieve response task cancelled")
                raise
            self.logger.error(f"Error retrieving response: {e}")
            if not isinstance(e, ClientDisconnectedError):
                await save_error_snapshot(f"get_response_error_{self.req_id}")
            raise

    async def ensure_generation_stopped(
        self, check_client_disconnected: Callable
    ) -> None:
        """
        Ensure generation has stopped.
        If submit button is still enabled, click it to stop generation.
        Wait until submit button becomes disabled.
        """
        submit_button_locator = self.page.locator(SUBMIT_BUTTON_SELECTOR)

        # Check client connection status
        check_client_disconnected("Ensure generation stopped - pre-check")
        await asyncio.sleep(0.5)  # Give UI time to update

        # Check if button is still enabled, if so click to stop
        try:
            is_button_enabled = await submit_button_locator.is_enabled(timeout=2000)

            if is_button_enabled:
                # Button still enabled after stream completion, click to stop
                self.logger.debug(
                    "[Cleanup] Submit button state: ENABLED -> Clicking stop"
                )
                await submit_button_locator.click(timeout=5000, force=True)
            else:
                self.logger.debug(
                    "[Cleanup] Submit button state: DISABLED (no action needed)"
                )
        except Exception as button_check_err:
            if isinstance(button_check_err, asyncio.CancelledError):
                raise
            self.logger.warning(f"Failed to check button state: {button_check_err}")

        # Wait for button to be disabled
        try:
            await expect_async(submit_button_locator).to_be_disabled(timeout=30000)
        except Exception as e:
            if isinstance(e, asyncio.CancelledError):
                raise
            self.logger.warning(f"Timeout or error ensuring generation stopped: {e}")
            # Do not raise even on timeout as this is just a cleanup step
