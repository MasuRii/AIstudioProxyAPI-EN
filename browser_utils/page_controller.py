"""
PageController Module
Encapsulates all complex logic for direct interaction with Playwright pages.
"""

import asyncio
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from playwright.async_api import Page as AsyncPage
from playwright.async_api import expect as expect_async

from config import (
    CLEAR_CHAT_BUTTON_SELECTOR,
    CLEAR_CHAT_CONFIRM_BUTTON_SELECTOR,
    CLICK_TIMEOUT_MS,
    DEFAULT_MAX_OUTPUT_TOKENS,
    DEFAULT_STOP_SEQUENCES,
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_P,
    EDIT_MESSAGE_BUTTON_SELECTOR,
    ENABLE_URL_CONTEXT,
    PROMPT_TEXTAREA_SELECTOR,
    SUBMIT_BUTTON_SELECTOR,
    UPLOAD_BUTTON_SELECTOR,
)
from models import ClientDisconnectedError, QuotaExceededError

from .initialization import enable_temporary_chat_mode
from .operations import (
    _get_final_response_content,
    _wait_for_response_completion,
    check_quota_limit,
    get_response_via_copy_button,
    get_response_via_edit_button,
)
from .page_controller_modules.base import BaseController
from .page_controller_modules.chat import ChatController
from .page_controller_modules.function_calling import FunctionCallingController
from .page_controller_modules.input import InputController
from .page_controller_modules.parameters import ParameterController
from .page_controller_modules.response import ResponseController
from .page_controller_modules.thinking import ThinkingController


class PageController(
    ParameterController,
    InputController,
    ChatController,
    ResponseController,
    ThinkingController,
    FunctionCallingController,
    BaseController,
):
    """Encapsulates all operations for interacting with the AI Studio page."""

    def __init__(self, page: AsyncPage, logger, req_id: str):
        self.page = page
        self.logger = logger
        self.req_id = req_id

    async def _check_disconnect(self, check_client_disconnected: Callable, stage: str):
        if check_client_disconnected(stage):
            raise ClientDisconnectedError(
                f"[{self.req_id}] Client disconnected at stage: {stage}"
            )

    async def adjust_parameters(
        self,
        request_params: Dict[str, Any],
        page_params_cache: Dict[str, Any],
        params_cache_lock: asyncio.Lock,
        model_id_to_use: Optional[str],
        parsed_model_list: List[Dict[str, Any]],
        check_client_disconnected: Callable,
        is_streaming: bool = True,
    ):
        self.logger.info(f"[{self.req_id}] Adjusting parameters...")
        await self._check_disconnect(
            check_client_disconnected, "Start Parameter Adjustment"
        )
        temp = request_params.get("temperature", DEFAULT_TEMPERATURE)
        await self._adjust_temperature(
            temp, page_params_cache, params_cache_lock, check_client_disconnected
        )
        max_tokens = request_params.get("max_output_tokens", DEFAULT_MAX_OUTPUT_TOKENS)
        await self._adjust_max_tokens(
            max_tokens,
            page_params_cache,
            params_cache_lock,
            model_id_to_use,
            parsed_model_list,
            check_client_disconnected,
        )
        stop = request_params.get("stop", DEFAULT_STOP_SEQUENCES)
        await self._adjust_stop_sequences(
            stop, page_params_cache, params_cache_lock, check_client_disconnected
        )
        top_p = request_params.get("top_p", DEFAULT_TOP_P)
        await self._adjust_top_p(top_p, check_client_disconnected)
        await self._ensure_tools_panel_expanded(check_client_disconnected)

        # Force disable URL context if function calling is active
        is_fc_enabled = await self.is_function_calling_enabled(
            check_client_disconnected
        )
        if is_fc_enabled:
            await self._adjust_url_context(False, check_client_disconnected)
        elif ENABLE_URL_CONTEXT:
            await self._adjust_url_context(True, check_client_disconnected)

        await self._handle_thinking_budget(
            request_params,
            page_params_cache,
            params_cache_lock,
            model_id_to_use,
            check_client_disconnected,
            is_streaming,
        )
        await self._adjust_google_search(
            request_params, model_id_to_use, check_client_disconnected
        )

    async def clear_chat_history(self, check_client_disconnected: Callable):
        """Clear chat history."""
        self.logger.info(f"[{self.req_id}] Clearing chat history...")
        btn = self.page.locator(CLEAR_CHAT_BUTTON_SELECTOR)
        if await btn.is_enabled(timeout=5000):
            await btn.click(timeout=CLICK_TIMEOUT_MS)
            confirm = self.page.locator(CLEAR_CHAT_CONFIRM_BUTTON_SELECTOR)
            if await confirm.is_visible(timeout=2000):
                await confirm.click(timeout=CLICK_TIMEOUT_MS)
            await enable_temporary_chat_mode(self.page)

    async def submit_prompt(
        self, prompt: str, image_list: List, check_client_disconnected: Callable
    ):
        """Submit prompt to the page with retries and keyboard fallbacks."""
        max_retries = 2
        for attempt in range(max_retries):
            try:
                self.logger.info(
                    f"[{self.req_id}] Filling and submitting prompt (Attempt {attempt + 1}/{max_retries})..."
                )
                textarea = self.page.locator(PROMPT_TEXTAREA_SELECTOR)
                await expect_async(textarea).to_be_visible(timeout=10000)
                await self._check_disconnect(
                    check_client_disconnected, "After Input Visible"
                )

                # Fill textarea using centralized logic (inherited from InputController if possible, or direct)
                await textarea.evaluate(
                    "(el, t) => { el.value = t; el.dispatchEvent(new Event('input', {bubbles:true})); el.dispatchEvent(new Event('change', {bubbles:true})); }",
                    prompt,
                )
                await self._check_disconnect(
                    check_client_disconnected, "After Input Fill"
                )

                if image_list:
                    await self._open_upload_menu_and_choose_file(image_list)

                # Wait for submit button to be enabled
                submit = self.page.locator(SUBMIT_BUTTON_SELECTOR)
                button_clicked = False
                is_btn_enabled = False
                try:
                    await expect_async(submit).to_be_enabled(timeout=10000)
                    is_btn_enabled = True
                except Exception:
                    self.logger.warning(
                        f"[{self.req_id}] Submit button not enabled within timeout, trying keyboard fallback."
                    )

                await self._check_disconnect(
                    check_client_disconnected, "After Submit Button Check"
                )

                if is_btn_enabled:
                    try:
                        # Defensive workarounds before click: handle dialogs, backdrops and tooltips
                        await self._handle_post_upload_dialog()
                        await self._dismiss_backdrops()
                        if hasattr(self, "_dismiss_tooltip_overlays"):
                            await self._dismiss_tooltip_overlays()

                        await submit.click(timeout=5000)
                        button_clicked = True
                        self.logger.info(f"[{self.req_id}] Submit button clicked.")
                        await check_quota_limit(self.page, self.req_id)
                    except QuotaExceededError:
                        raise
                    except Exception as click_err:
                        self.logger.warning(
                            f"[{self.req_id}] Button click failed: {click_err}. Trying keyboard fallback."
                        )

                if not button_clicked:
                    # Keyboard fallbacks (using logic inherited from InputController)
                    self.logger.info(
                        f"[{self.req_id}] Attempting Enter key submission..."
                    )
                    if await self._try_enter_submit(
                        textarea, check_client_disconnected
                    ):
                        button_clicked = True
                    else:
                        self.logger.info(
                            f"[{self.req_id}] Attempting Combo key submission..."
                        )
                        if await self._try_combo_submit(
                            textarea, check_client_disconnected
                        ):
                            button_clicked = True

                if not button_clicked:
                    raise Exception(
                        "Failed to submit prompt via button or keyboard shortcuts."
                    )

                await self._check_disconnect(check_client_disconnected, "After Submit")
                return
            except QuotaExceededError:
                raise
            except Exception as e:
                self.logger.warning(
                    f"[{self.req_id}] Error during submit (Attempt {attempt + 1}): {e}"
                )
                if attempt < max_retries - 1:
                    await self._safe_reload_page()
                    await asyncio.sleep(2)
                else:
                    raise e

    async def _open_upload_menu_and_choose_file(self, files_list: List[str]) -> bool:
        """Upload files via menu."""
        await self.page.locator(UPLOAD_BUTTON_SELECTOR).first.click()
        btn = self.page.locator("div[role='menu'] button[role='menuitem']").filter(
            has_text="Upload File"
        )
        if await btn.count() == 0:
            btn = self.page.locator("div[role='menu'] button[role='menuitem']").filter(
                has_text="Upload a file"
            )
        async with self.page.expect_file_chooser() as fc_info:
            await btn.first.click()
        await (await fc_info.value).set_files(files_list)
        return True

    async def _safe_reload_page(self):
        """Reload page safely."""
        await self.page.reload(timeout=30000)
        await self.page.wait_for_load_state("domcontentloaded", timeout=30000)

    async def get_response(
        self,
        check_client_disconnected: Callable,
        prompt_length: int = 0,
        timeout: Optional[float] = None,
    ) -> str:
        """Retrieve response content."""
        submit_btn = self.page.locator(SUBMIT_BUTTON_SELECTOR)
        edit_btn = self.page.locator(EDIT_MESSAGE_BUTTON_SELECTOR)
        input_field = self.page.locator(PROMPT_TEXTAREA_SELECTOR)
        await _wait_for_response_completion(
            self.page,
            input_field,
            submit_btn,
            edit_btn,
            self.req_id,
            check_client_disconnected,
            None,
            prompt_length=prompt_length,
            timeout=timeout,
        )
        content = await _get_final_response_content(
            self.page, self.req_id, check_client_disconnected
        )
        if not content or not content.strip():
            verified = await self.verify_response_integrity(check_client_disconnected)
            return verified.get("content", "")
        return content

    async def verify_response_integrity(
        self, check_client_disconnected: Callable, trigger_reason: str = ""
    ) -> Dict[str, str]:
        """Verify integrity via DOM."""
        await asyncio.sleep(1)
        final = await self._extract_complete_response_content()
        content, reasoning = self._separate_thinking_and_response(final)
        return {"content": content, "reasoning_content": reasoning}

    async def get_response_with_integrity_check(
        self,
        check_client_disconnected: Callable,
        prompt_length: int = 0,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Retrieve response content with full integrity check and function calls."""
        content = await self.get_response(
            check_client_disconnected, prompt_length, timeout
        )

        # Parse function calls from DOM as well
        has_fc, function_calls, text_content = await self.parse_function_calls(
            check_client_disconnected
        )

        c, r = self._separate_thinking_and_response(content)

        result = {
            "content": c,
            "reasoning_content": r,
            "recovery_method": "direct",
            "has_function_calls": has_fc,
            "function_calls": function_calls,
        }

        if has_fc:
            # If function calls found, use the text content (with calls removed) as content
            # But we need to separate thinking from it too
            c_fc, r_fc = self._separate_thinking_and_response(text_content)
            result["content"] = c_fc
            # Keep original reasoning if not found in text_content
            if r_fc:
                result["reasoning_content"] = r_fc

        return result

    def _separate_thinking_and_response(self, content: str) -> Tuple[str, str]:
        """Separate thinking and response."""
        if not content:
            return "", ""
        m = re.findall(r"\[THINKING\](.*?)\[/THINKING\]", content, re.DOTALL)
        r = "\n".join(m).strip()
        c = re.sub(
            r"\[THINKING\](.*?)\[/THINKING\]", "", content, flags=re.DOTALL
        ).strip()
        return c, r

    async def _emergency_stability_wait(
        self, check_client_disconnected: Callable
    ) -> bool:
        """Wait for DOM stability."""
        await asyncio.sleep(2)
        return True

    async def _check_generation_activity(self) -> bool:
        """Check if generation is in progress."""
        stop_btn = self.page.locator('button[aria-label="Stop generating"]')
        return await stop_btn.is_visible(timeout=500)

    async def _extract_dom_content(self) -> str:
        """Extract content from DOM."""
        from config.selectors import FINAL_RESPONSE_SELECTOR

        elem = self.page.locator(FINAL_RESPONSE_SELECTOR).last
        return await elem.inner_text() if await elem.count() > 0 else ""

    async def _extract_complete_response_content(self) -> str:
        """Extract complete response content."""
        c = await get_response_via_edit_button(self.page, self.req_id, lambda x: None)
        if not c:
            c = await get_response_via_copy_button(
                self.page, self.req_id, lambda x: None
            )
        return c if c else await self._extract_dom_content()

    async def get_body_text_only_from_dom(self) -> str:
        """Extract body text only."""
        return await self._extract_dom_content()
