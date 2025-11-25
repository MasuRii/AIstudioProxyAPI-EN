"""
PageController模块
封装了所有与Playwright页面直接交互的复杂逻辑。
"""
import asyncio
import base64
import mimetypes
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from playwright.async_api import Page as AsyncPage
from playwright.async_api import TimeoutError
from playwright.async_api import expect as expect_async

from config import (
    CLEAR_CHAT_BUTTON_SELECTOR,
    CLEAR_CHAT_CONFIRM_BUTTON_SELECTOR,
    CLEAR_CHAT_VERIFY_TIMEOUT_MS,
    CLICK_TIMEOUT_MS,
    DEFAULT_MAX_OUTPUT_TOKENS,
    DEFAULT_STOP_SEQUENCES,
    DEFAULT_TEMPERATURE,
    DEFAULT_THINKING_BUDGET,
    DEFAULT_TOP_P,
    EDIT_MESSAGE_BUTTON_SELECTOR,
    ENABLE_GOOGLE_SEARCH,
    ENABLE_THINKING_BUDGET,
    ENABLE_THINKING_MODE_TOGGLE_SELECTOR,
    ENABLE_URL_CONTEXT,
    GROUNDING_WITH_GOOGLE_SEARCH_TOGGLE_SELECTOR,
    MAT_CHIP_REMOVE_BUTTON_SELECTOR,
    MAX_OUTPUT_TOKENS_SELECTOR,
    OVERLAY_SELECTOR,
    PROMPT_TEXTAREA_SELECTOR,
    RESPONSE_CONTAINER_SELECTOR,
    RESPONSE_TEXT_SELECTOR,
    SET_THINKING_BUDGET_TOGGLE_SELECTOR,
    STOP_SEQUENCE_INPUT_SELECTOR,
    SUBMIT_BUTTON_SELECTOR,
    TEMPERATURE_INPUT_SELECTOR,
    THINKING_BUDGET_INPUT_SELECTOR,
    THINKING_LEVEL_DROPDOWN_SELECTOR,
    THINKING_LEVEL_OPTION_HIGH_SELECTOR,
    THINKING_LEVEL_OPTION_LOW_SELECTOR,
    THINKING_LEVEL_SELECT_SELECTOR,
    TOP_P_INPUT_SELECTOR,
    UPLOAD_BUTTON_SELECTOR,
    USE_URL_CONTEXT_SELECTOR,
    WAIT_FOR_ELEMENT_TIMEOUT_MS,
    AI_STUDIO_URL_PATTERN,
)
from models import ClientDisconnectedError, QuotaExceededError
from .initialization import enable_temporary_chat_mode
from .operations import (
    _get_final_response_content,
    _wait_for_response_completion,
    check_quota_limit,
    save_error_snapshot,
)
from .thinking_normalizer import format_directive_log, normalize_reasoning_effort_with_stream_check


class PageController:
    """封装了与AI Studio页面交互的所有操作。"""

    def __init__(self, page: AsyncPage, logger, req_id: str):
        self.page = page
        self.logger = logger
        self.req_id = req_id

    async def _check_disconnect(self, check_client_disconnected: Callable, stage: str):
        """检查客户端是否断开连接。"""
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
        """Adjust all request parameters."""
        self.logger.info(f"[{self.req_id}] Starting parameter adjustment...")
        await self._check_disconnect(
            check_client_disconnected, "Start Parameter Adjustment"
        )

        # 调整温度
        temp_to_set = request_params.get("temperature", DEFAULT_TEMPERATURE)
        await self._adjust_temperature(
            temp_to_set, page_params_cache, params_cache_lock, check_client_disconnected
        )
        await self._check_disconnect(
            check_client_disconnected, "After Temperature Adjustment"
        )

        # 调整最大Token
        max_tokens_to_set = request_params.get(
            "max_output_tokens", DEFAULT_MAX_OUTPUT_TOKENS
        )
        await self._adjust_max_tokens(
            max_tokens_to_set,
            page_params_cache,
            params_cache_lock,
            model_id_to_use,
            parsed_model_list,
            check_client_disconnected,
        )
        await self._check_disconnect(
            check_client_disconnected, "After Max Tokens Adjustment"
        )

        # 调整停止序列
        stop_to_set = request_params.get("stop", DEFAULT_STOP_SEQUENCES)
        await self._adjust_stop_sequences(
            stop_to_set, page_params_cache, params_cache_lock, check_client_disconnected
        )
        await self._check_disconnect(
            check_client_disconnected, "After Stop Sequences Adjustment"
        )

        # 调整Top P
        top_p_to_set = request_params.get("top_p", DEFAULT_TOP_P)
        await self._adjust_top_p(top_p_to_set, check_client_disconnected)
        await self._check_disconnect(
            check_client_disconnected, "End Parameter Adjustment"
        )

        # 确保工具面板已展开，以便调整高级设置
        await self._ensure_tools_panel_expanded(check_client_disconnected)

        # 调整URL CONTEXT（允许按请求控制）
        if ENABLE_URL_CONTEXT:
            await self._open_url_content(check_client_disconnected)
        else:
            self.logger.info(f"[{self.req_id}] URL Context feature disabled, skipping adjustment.")

        # Adjust "Thinking Budget"
        await self._handle_thinking_budget(
            request_params, model_id_to_use, check_client_disconnected, is_streaming
        )

        # 调整 Google Search 开关
        await self._adjust_google_search(request_params, check_client_disconnected)

    async def _handle_thinking_budget(
        self,
        request_params: Dict[str, Any],
        model_id_to_use: Optional[str],
        check_client_disconnected: Callable,
        is_streaming: bool = True,
    ):
        """处理思考模式和预算的调整逻辑。"""
        reasoning_effort = request_params.get("reasoning_effort")

        directive = normalize_reasoning_effort_with_stream_check(reasoning_effort, is_streaming)
        self.logger.info(f"[{self.req_id}] Reasoning mode directive: {format_directive_log(directive)}")

        uses_level = self._uses_thinking_level(
            model_id_to_use
        ) and await self._has_thinking_dropdown()

        desired_enabled = directive.thinking_enabled

        has_main_toggle = self._model_has_main_thinking_toggle(model_id_to_use)
        if has_main_toggle:
            self.logger.info(
                f"[{self.req_id}] Starting to set main thinking toggle to: {'ON' if desired_enabled else 'OFF'}"
            )
            await self._control_thinking_mode_toggle(
                should_be_enabled=desired_enabled,
                check_client_disconnected=check_client_disconnected,
            )
        else:
            self.logger.info(f"[{self.req_id}] Model has no main thinking toggle, skipping.")

        if not desired_enabled:
            # 跳过无预算开关的模型
            if self._uses_thinking_level(model_id_to_use):
                 return
            # 若关闭思考，则确保预算开关关闭（兼容旧UI）
            await self._control_thinking_budget_toggle(
                should_be_checked=False,
                check_client_disconnected=check_client_disconnected,
            )
            return

        # 2) 已开启思考：根据模型类型设置等级或预算
        if uses_level:
            rv = reasoning_effort
            level_to_set = None
            if isinstance(rv, str):
                rs = rv.strip().lower()
                if rs == "low":
                    level_to_set = "low"
                elif rs in ["high", "none", "-1"]:
                    level_to_set = "high"
                else:
                    try:
                        v = int(rs)
                        level_to_set = "high" if v >= 8000 else "low"
                    except Exception:
                        level_to_set = None
            elif isinstance(rv, int):
                level_to_set = "high" if rv >= 8000 or rv == -1 else "low"

            if level_to_set is None:
                self.logger.info(f"[{self.req_id}] Unable to parse reasoning level, keeping current.")
            else:
                await self._set_thinking_level(level_to_set, check_client_disconnected)
            return

        if not directive.thinking_enabled:
            self.logger.info(f"[{self.req_id}] Attempting to turn off main thinking toggle...")
            success = await self._control_thinking_mode_toggle(
                should_be_enabled=False,
                check_client_disconnected=check_client_disconnected,
            )

            if not success:
                self.logger.warning(f"[{self.req_id}] Main thinking toggle unavailable, using fallback: Setting budget to 0")
                await self._control_thinking_budget_toggle(
                    should_be_checked=True,
                    check_client_disconnected=check_client_disconnected,
                )
                await self._set_thinking_budget_value(0, check_client_disconnected)
            return

        # 场景2和3: 开启思考模式
        self.logger.info(f"[{self.req_id}] Enabling main thinking toggle...")
        await self._control_thinking_mode_toggle(
            should_be_enabled=True, check_client_disconnected=check_client_disconnected
        )

        # --- FIX START: Gemini 3.0 Bypass ---
        # Check if we are on the new Gemini 3.0 UI
        new_thinking_dropdown = self.page.locator(THINKING_LEVEL_DROPDOWN_SELECTOR)
        if await new_thinking_dropdown.is_visible(timeout=500):
            self.logger.info(
                f"[{self.req_id}] Gemini 3.0+ UI detected (Thinking Level Dropdown). Skipping budget slider config."
            )
            return
        # --- FIX END ---

        # 场景2: 开启思考，不限制预算
        if not directive.budget_enabled:
            self.logger.info(f"[{self.req_id}] Disabling manual budget limit...")
            await self._control_thinking_budget_toggle(
                should_be_checked=False,
                check_client_disconnected=check_client_disconnected,
            )

        # 场景3: 开启思考，限制预算
        else:
            value_to_set = directive.budget_value or 0
            model_lower = (model_id_to_use or "").lower()
            if "gemini-2.5-pro" in model_lower:
                value_to_set = min(value_to_set, 32768)
            elif "flash-lite" in model_lower:
                value_to_set = min(value_to_set, 24576)
            elif "flash" in model_lower:
                value_to_set = min(value_to_set, 24576)
            self.logger.info(
                f"[{self.req_id}] Enabling manual budget limit and setting budget value: {value_to_set} tokens"
            )
            await self._control_thinking_budget_toggle(
                should_be_checked=True,
                check_client_disconnected=check_client_disconnected,
            )
            await self._set_thinking_budget_value(
                value_to_set, check_client_disconnected
            )

    async def _has_thinking_dropdown(self) -> bool:
        try:
            locator = self.page.locator(THINKING_LEVEL_SELECT_SELECTOR)
            count = await locator.count()
            if count == 0:
                return False
            try:
                await expect_async(locator.first).to_be_visible(timeout=2000)
                return True
            except Exception:
                return True
        except Exception:
            return False

    def _uses_thinking_level(self, model_id_to_use: Optional[str]) -> bool:
        """Use 'Thinking Level' logic only on Gemini 3 Pro series, otherwise use budget."""
        try:
            mid = (model_id_to_use or "").lower()
            return ("gemini-3" in mid) and ("pro" in mid)
        except Exception:
            return False

    def _model_has_main_thinking_toggle(self, model_id_to_use: Optional[str]) -> bool:
        try:
            mid = (model_id_to_use or "").lower()
            return "flash" in mid
        except Exception:
            return False

    async def _set_thinking_level(
        self, level: str, check_client_disconnected: Callable
    ):
        target_option_selector = (
            THINKING_LEVEL_OPTION_HIGH_SELECTOR
            if level.lower() == "high"
            else THINKING_LEVEL_OPTION_LOW_SELECTOR
        )
        try:
            trigger = self.page.locator(THINKING_LEVEL_SELECT_SELECTOR)
            await expect_async(trigger).to_be_visible(timeout=5000)
            await trigger.scroll_into_view_if_needed()
            await trigger.click(timeout=CLICK_TIMEOUT_MS)
            await self._check_disconnect(
                check_client_disconnected, "Thinking Level 打开后"
            )
            option = self.page.locator(target_option_selector)
            await expect_async(option).to_be_visible(timeout=5000)
            await option.click(timeout=CLICK_TIMEOUT_MS)
            await asyncio.sleep(0.2)
            try:
                await expect_async(
                    self.page.locator(
                        '[role="listbox"][aria-label="Thinking Level"], [role="listbox"][aria-label="Thinking level"]'
                    ).first
                ).to_be_hidden(timeout=2000)
            except Exception:
                try:
                    await self.page.keyboard.press("Escape")
                except Exception:
                    pass
                await asyncio.sleep(0.1)
            value_text = await trigger.locator(
                ".mat-mdc-select-value-text .mat-mdc-select-min-line"
            ).inner_text(timeout=3000)
            if value_text.strip().lower() == level.lower():
                self.logger.info(f"[{self.req_id}] Thinking Level set to {level}")
            else:
                self.logger.warning(
                    f"[{self.req_id}] Thinking Level verification failed, page value: {value_text}, expected: {level}"
                )
        except Exception as e:
            self.logger.error(f"[{self.req_id}] Error setting Thinking Level: {e}")
            if isinstance(e, ClientDisconnectedError):
                raise

    async def _set_thinking_budget_value(
        self, token_budget: int, check_client_disconnected: Callable
    ):
        """Set specific thinking budget value."""
        self.logger.info(f"[{self.req_id}] Setting thinking budget value: {token_budget} tokens")

        budget_input_locator = self.page.locator(THINKING_BUDGET_INPUT_SELECTOR)

        try:
            await expect_async(budget_input_locator).to_be_visible(timeout=5000)
            await self._check_disconnect(check_client_disconnected, "思考预算调整 - 输入框可见后")

            adjusted_budget = token_budget

            try:
                await self.page.evaluate(
                    "([selector, desired]) => {\n"
                    "  const num = Number(desired);\n"
                    "  const el = document.querySelector(selector);\n"
                    "  if (!el) return false;\n"
                    "  const container = el.closest('[data-test-slider]') || el.parentElement;\n"
                    "  const inputs = container ? container.querySelectorAll('input') : [el];\n"
                    "  const ranges = container ? container.querySelectorAll('input[type=\"range\"]') : [];\n"
                    "  inputs.forEach(inp => {\n"
                    "    try {\n"
                    "      if (Number.isFinite(num)) {\n"
                    "        const curMaxAttr = inp.getAttribute('max');\n"
                    "        const curMax = curMaxAttr ? Number(curMaxAttr) : undefined;\n"
                    "        if (curMax !== undefined && curMax < num) {\n"
                    "          inp.setAttribute('max', String(num));\n"
                    "        }\n"
                    "        if (inp.max && Number(inp.max) < num) {\n"
                    "          inp.max = String(num);\n"
                    "        }\n"
                    "        inp.value = String(num);\n"
                    "        inp.dispatchEvent(new Event('input', { bubbles: true }));\n"
                    "        inp.dispatchEvent(new Event('change', { bubbles: true }));\n"
                    "        inp.dispatchEvent(new Event('blur', { bubbles: true }));\n"
                    "      }\n"
                    "    } catch (_) {}\n"
                    "  });\n"
                    "  ranges.forEach(r => {\n"
                    "    try {\n"
                    "      if (Number.isFinite(num)) {\n"
                    "        const curMaxAttr = r.getAttribute('max');\n"
                    "        const curMax = curMaxAttr ? Number(curMaxAttr) : undefined;\n"
                    "        if (curMax !== undefined && curMax < num) {\n"
                    "          r.setAttribute('max', String(num));\n"
                    "        }\n"
                    "        if (r.max && Number(r.max) < num) {\n"
                    "          r.max = String(num);\n"
                    "        }\n"
                    "        r.value = String(num);\n"
                    "        r.dispatchEvent(new Event('input', { bubbles: true }));\n"
                    "        r.dispatchEvent(new Event('change', { bubbles: true }));\n"
                    "      }\n"
                    "    } catch (_) {}\n"
                    "  });\n"
                    "  return true;\n"
                    "}",
                    [THINKING_BUDGET_INPUT_SELECTOR, adjusted_budget],
                )
            except Exception:
                pass

            self.logger.info(f"[{self.req_id}] Setting thinking budget to: {adjusted_budget}")
            await budget_input_locator.fill(str(adjusted_budget), timeout=5000)
            await self._check_disconnect(check_client_disconnected, "Thinking Budget - after fill")

            # Verify
            try:
                await expect_async(budget_input_locator).to_have_value(
                    str(adjusted_budget), timeout=3000
                )
                self.logger.info(f"[{self.req_id}] ✅ Thinking budget successfully updated to: {adjusted_budget}")
            except Exception:
                new_value_str = await budget_input_locator.input_value(timeout=3000)
                try:
                    new_value_int = int(new_value_str)
                except Exception:
                    new_value_int = -1
                if new_value_int == adjusted_budget:
                    self.logger.info(
                        f"[{self.req_id}] ✅ Thinking budget successfully updated to: {new_value_str}"
                    )
                else:
                    # Fallback: if page max is less than requested
                    try:
                        page_max_str = await budget_input_locator.get_attribute("max")
                        page_max_val = (
                            int(page_max_str) if page_max_str is not None else None
                        )
                    except Exception:
                        page_max_val = None
                    if page_max_val is not None and page_max_val < adjusted_budget:
                        self.logger.warning(
                            f"[{self.req_id}] Page max budget is {page_max_val}, requested budget {adjusted_budget} adjusted to {page_max_val}"
                        )
                        try:
                            await self.page.evaluate(
                                "([selector, desired]) => {\n"
                                "  const num = Number(desired);\n"
                                "  const el = document.querySelector(selector);\n"
                                "  if (!el) return false;\n"
                                "  const container = el.closest('[data-test-slider]') || el.parentElement;\n"
                                "  const inputs = container ? container.querySelectorAll('input') : [el];\n"
                                "  inputs.forEach(inp => {\n"
                                "    try { inp.value = String(num); inp.dispatchEvent(new Event('input', { bubbles: true })); inp.dispatchEvent(new Event('change', { bubbles: true })); } catch (_) {}\n"
                                "  });\n"
                                "  return true;\n"
                                "}",
                                [THINKING_BUDGET_INPUT_SELECTOR, page_max_val],
                            )
                        except Exception:
                            pass
                        await budget_input_locator.fill(str(page_max_val), timeout=5000)
                        try:
                            await expect_async(budget_input_locator).to_have_value(
                                str(page_max_val), timeout=2000
                            )
                        except Exception:
                            pass
                    else:
                        self.logger.warning(
                            f"[{self.req_id}] ⚠️ Thinking budget verification failed after update. Page shows: {new_value_str}, expected: {adjusted_budget}"
                        )

        except Exception as e:
            self.logger.error(f"[{self.req_id}] ❌ Error adjusting thinking budget: {e}")
            if isinstance(e, ClientDisconnectedError):
                raise

    def _should_enable_google_search(self, request_params: Dict[str, Any]) -> bool:
        """Decide whether to enable Google Search based on request params or default config."""
        if "tools" in request_params and request_params.get("tools") is not None:
            tools = request_params.get("tools")
            has_google_search_tool = False
            if isinstance(tools, list):
                for tool in tools:
                    if isinstance(tool, dict):
                        if tool.get("google_search_retrieval") is not None:
                            has_google_search_tool = True
                            break
                        if tool.get("function", {}).get("name") == "googleSearch":
                            has_google_search_tool = True
                            break
            self.logger.info(
                f"[{self.req_id}] Request contains 'tools'. Google Search tool detected: {has_google_search_tool}."
            )
            return has_google_search_tool
        else:
            self.logger.info(
                f"[{self.req_id}] Request does not contain 'tools'. Using default config ENABLE_GOOGLE_SEARCH: {ENABLE_GOOGLE_SEARCH}."
            )
            return ENABLE_GOOGLE_SEARCH

    async def _adjust_google_search(
        self, request_params: Dict[str, Any], check_client_disconnected: Callable
    ):
        """Control Google Search toggle bidirectionally based on params or config."""
        self.logger.info(f"[{self.req_id}] Checking and adjusting Google Search toggle...")

        should_enable_search = self._should_enable_google_search(request_params)

        toggle_selector = GROUNDING_WITH_GOOGLE_SEARCH_TOGGLE_SELECTOR

        try:
            toggle_locator = self.page.locator(toggle_selector)
            await expect_async(toggle_locator).to_be_visible(timeout=5000)
            await self._check_disconnect(
                check_client_disconnected, "Google Search Toggle - after visible"
            )

            is_checked_str = await toggle_locator.get_attribute("aria-checked")
            is_currently_checked = is_checked_str == "true"
            self.logger.info(
                f"[{self.req_id}] Google Search toggle current state: '{is_checked_str}'. Expected: {should_enable_search}"
            )

            if should_enable_search != is_currently_checked:
                action = "Enable" if should_enable_search else "Disable"
                self.logger.info(
                    f"[{self.req_id}] Google Search toggle state differs from expected. Clicking to {action}..."
                )
                try:
                    await toggle_locator.scroll_into_view_if_needed()
                except Exception:
                    pass
                await toggle_locator.click(timeout=CLICK_TIMEOUT_MS)
                await self._check_disconnect(
                    check_client_disconnected, f"Google Search Toggle - after click {action}"
                )
                await asyncio.sleep(0.5)  # Wait for UI update
                new_state = await toggle_locator.get_attribute("aria-checked")
                if (new_state == "true") == should_enable_search:
                    self.logger.info(f"[{self.req_id}] ✅ Google Search toggle successfully {action}d.")
                else:
                    self.logger.warning(
                        f"[{self.req_id}] ⚠️ Google Search toggle {action} failed. Current state: '{new_state}'"
                    )
            else:
                self.logger.info(f"[{self.req_id}] Google Search toggle already in expected state.")

        except Exception as e:
            self.logger.error(
                f"[{self.req_id}] ❌ Error operating 'Google Search toggle': {e}"
            )
            if isinstance(e, ClientDisconnectedError):
                raise

    async def _ensure_tools_panel_expanded(self, check_client_disconnected: Callable):
        """Ensure tools panel (URL context, thinking budget, etc.) is expanded."""
        self.logger.info(f"[{self.req_id}] Checking and ensuring tools panel is expanded...")
        try:
            collapse_tools_locator = self.page.locator(
                'button[aria-label="Expand or collapse tools"]'
            )
            await expect_async(collapse_tools_locator).to_be_visible(timeout=5000)

            grandparent_locator = collapse_tools_locator.locator("xpath=../..")
            class_string = await grandparent_locator.get_attribute(
                "class", timeout=3000
            )

            if class_string and "expanded" not in class_string.split():
                self.logger.info(f"[{self.req_id}] Tools panel not expanded, clicking to expand...")
                await collapse_tools_locator.click(timeout=CLICK_TIMEOUT_MS)
                await self._check_disconnect(check_client_disconnected, "After expanding tools panel")
                # Wait for expansion
                await expect_async(grandparent_locator).to_have_class(
                    re.compile(r".*expanded.*"), timeout=5000
                )
                self.logger.info(f"[{self.req_id}] ✅ Tools panel successfully expanded.")
            else:
                self.logger.info(f"[{self.req_id}] Tools panel already expanded.")
        except Exception as e:
            self.logger.error(f"[{self.req_id}] ❌ Error expanding tools panel: {e}")
            # Continue even if error, but log it
            if isinstance(e, ClientDisconnectedError):
                raise

    async def _open_url_content(self, check_client_disconnected: Callable):
        """Enable URL Context toggle, assuming panel is expanded."""
        try:
            self.logger.info(f"[{self.req_id}] Checking and enabling URL Context toggle...")
            use_url_content_selector = self.page.locator(USE_URL_CONTEXT_SELECTOR)
            await expect_async(use_url_content_selector).to_be_visible(timeout=5000)

            is_checked = await use_url_content_selector.get_attribute("aria-checked")
            if "false" == is_checked:
                self.logger.info(f"[{self.req_id}] URL Context toggle not enabled, clicking to enable...")
                await use_url_content_selector.click(timeout=CLICK_TIMEOUT_MS)
                await self._check_disconnect(check_client_disconnected, "After clicking URL Context")
                self.logger.info(f"[{self.req_id}] ✅ URL Context toggle clicked.")
            else:
                self.logger.info(f"[{self.req_id}] URL Context toggle already enabled.")
        except Exception as e:
            self.logger.error(
                f"[{self.req_id}] ❌ Error operating USE_URL_CONTEXT_SELECTOR: {e}."
            )
            if isinstance(e, ClientDisconnectedError):
                raise

    async def _control_thinking_mode_toggle(
        self, should_be_enabled: bool, check_client_disconnected: Callable
    ) -> bool:
        """
        Control main thinking toggle to enable/disable thinking mode.

        Args:
            should_be_enabled: Expected state (True=ON, False=OFF)
            check_client_disconnected: Function to check disconnection

        Returns:
            bool: Success status
        """
        legacy_toggle_selector = ENABLE_THINKING_MODE_TOGGLE_SELECTOR
        new_dropdown_selector = THINKING_LEVEL_DROPDOWN_SELECTOR

        self.logger.info(
            f"[{self.req_id}] Controlling main thinking toggle, expected state: {'ON' if should_be_enabled else 'OFF'}..."
        )

        try:
            # 1. Check for new UI (Gemini 3.0+ Dropdown)
            new_dropdown_locator = self.page.locator(new_dropdown_selector)
            if await new_dropdown_locator.is_visible(timeout=500):
                self.logger.info(
                    f"[{self.req_id}] Gemini 3.0+ UI detected (Thinking Level Dropdown)."
                )
                return True

            # 2. Check for legacy UI (Toggle)
            toggle_locator = self.page.locator(legacy_toggle_selector)

            # Wait for element visible
            await expect_async(toggle_locator).to_be_visible(timeout=5000)
            try:
                await toggle_locator.scroll_into_view_if_needed()
            except Exception:
                pass
            await self._check_disconnect(check_client_disconnected, "Main thinking toggle - after visible")

            is_checked_str = await toggle_locator.get_attribute("aria-checked")
            current_state_is_enabled = is_checked_str == "true"
            self.logger.info(
                f"[{self.req_id}] Main thinking toggle current state: {is_checked_str} (Enabled: {current_state_is_enabled})"
            )

            if current_state_is_enabled != should_be_enabled:
                action = "Enable" if should_be_enabled else "Disable"
                self.logger.info(f"[{self.req_id}] Main thinking toggle needs switching, clicking to {action} thinking mode...")

                try:
                    await toggle_locator.click(timeout=CLICK_TIMEOUT_MS)
                except Exception:
                    try:
                        root = self.page.locator(
                            'mat-slide-toggle[data-test-toggle="enable-thinking"]'
                        )
                        label = root.locator("label.mdc-label")
                        await expect_async(label).to_be_visible(timeout=2000)
                        await label.click(timeout=CLICK_TIMEOUT_MS)
                    except Exception:
                        raise
                await self._check_disconnect(
                    check_client_disconnected, f"Main thinking toggle - after click {action}"
                )

                # Verify new state
                new_state_str = await toggle_locator.get_attribute("aria-checked")
                new_state_is_enabled = new_state_str == "true"

                if new_state_is_enabled == should_be_enabled:
                    self.logger.info(
                        f"[{self.req_id}] ✅ Main thinking toggle successfully {action}d. New state: {new_state_str}"
                    )
                    return True
                else:
                    self.logger.warning(
                        f"[{self.req_id}] ⚠️ Main thinking toggle verification failed after {action}. Expected: {should_be_enabled}, Actual: {new_state_str}"
                    )
                    return False
            else:
                self.logger.info(f"[{self.req_id}] Main thinking toggle already in expected state.")
                return True

        except TimeoutError:
            self.logger.warning(
                f"[{self.req_id}] ⚠️ Main thinking toggle not found or invisible (Model might not support thinking mode)"
            )
            return False
        except Exception as e:
            self.logger.error(f"[{self.req_id}] ❌ Error operating main thinking toggle: {e}")
            await save_error_snapshot(f"thinking_mode_toggle_error_{self.req_id}")
            if isinstance(e, ClientDisconnectedError):
                raise
            return False

    async def _control_thinking_budget_toggle(
        self, should_be_checked: bool, check_client_disconnected: Callable
    ):
        """
        Control 'Thinking Budget' toggle state based on should_be_checked.
        """
        toggle_selector = SET_THINKING_BUDGET_TOGGLE_SELECTOR
        self.logger.info(
            f"[{self.req_id}] Controlling 'Thinking Budget' toggle, expected state: {'Checked' if should_be_checked else 'Unchecked'}..."
        )

        try:
            toggle_locator = self.page.locator(toggle_selector)

            # [Robustness] Check visibility
            try:
                await expect_async(toggle_locator).to_be_visible(timeout=3000)
            except Exception:
                if not should_be_checked:
                    self.logger.info(f"[{self.req_id}] 'Thinking Budget' toggle invisible, assuming disabled/na.")
                    return
                else:
                    self.logger.warning(f"[{self.req_id}] ⚠️ 'Thinking Budget' toggle invisible, cannot enable.")
                    return

            try:
                await toggle_locator.scroll_into_view_if_needed()
            except Exception:
                pass
            await self._check_disconnect(check_client_disconnected, "Thinking Budget toggle - after visible")

            is_checked_str = await toggle_locator.get_attribute("aria-checked")
            current_state_is_checked = is_checked_str == "true"
            self.logger.info(
                f"[{self.req_id}] Thinking Budget toggle current 'aria-checked': {is_checked_str} (Checked: {current_state_is_checked})"
            )

            if current_state_is_checked != should_be_checked:
                action = "Enable" if should_be_checked else "Disable"
                self.logger.info(f"[{self.req_id}] Thinking Budget toggle state mismatch, clicking to {action}...")
                try:
                    await toggle_locator.click(timeout=CLICK_TIMEOUT_MS)
                except Exception:
                    try:
                        root = self.page.locator(
                            'mat-slide-toggle[data-test-toggle="manual-budget"]'
                        )
                        label = root.locator("label.mdc-label")
                        await expect_async(label).to_be_visible(timeout=2000)
                        await label.click(timeout=CLICK_TIMEOUT_MS)
                    except Exception:
                        raise
                await self._check_disconnect(
                    check_client_disconnected, f"Thinking Budget toggle - after click {action}"
                )

                await asyncio.sleep(0.5)
                new_state_str = await toggle_locator.get_attribute("aria-checked")
                new_state_is_checked = new_state_str == "true"

                if new_state_is_checked == should_be_checked:
                    self.logger.info(
                        f"[{self.req_id}] ✅ 'Thinking Budget' toggle successfully {action}d. New state: {new_state_str}"
                    )
                else:
                    self.logger.warning(
                        f"[{self.req_id}] ⚠️ 'Thinking Budget' toggle verification failed after {action}. Expected: '{should_be_checked}', Actual: '{new_state_str}'"
                    )
            else:
                self.logger.info(f"[{self.req_id}] 'Thinking Budget' toggle already in expected state.")

        except Exception as e:
            self.logger.error(
                f"[{self.req_id}] ❌ Error operating 'Thinking Budget toggle': {e}"
            )
            if isinstance(e, ClientDisconnectedError):
                raise

    async def _adjust_temperature(
        self,
        temperature: float,
        page_params_cache: dict,
        params_cache_lock: asyncio.Lock,
        check_client_disconnected: Callable,
    ):
        """Adjust temperature parameter."""
        async with params_cache_lock:
            self.logger.info(f"[{self.req_id}] Checking and adjusting temperature...")
            clamped_temp = max(0.0, min(2.0, temperature))
            if clamped_temp != temperature:
                self.logger.warning(
                    f"[{self.req_id}] Requested temperature {temperature} out of range [0, 2], adjusted to {clamped_temp}"
                )

            cached_temp = page_params_cache.get("temperature")
            if cached_temp is not None and abs(cached_temp - clamped_temp) < 0.001:
                self.logger.info(
                    f"[{self.req_id}] Temperature ({clamped_temp}) matches cached value ({cached_temp}). Skipping page interaction."
                )
                return

            self.logger.info(
                f"[{self.req_id}] Requested temperature ({clamped_temp}) differs from cache ({cached_temp}) or no cache. Interacting with page."
            )
            temp_input_locator = self.page.locator(TEMPERATURE_INPUT_SELECTOR)

            try:
                await expect_async(temp_input_locator).to_be_visible(timeout=5000)
                await self._check_disconnect(check_client_disconnected, "Temperature adjustment - after input visible")

                current_temp_str = await temp_input_locator.input_value(timeout=3000)
                await self._check_disconnect(
                    check_client_disconnected, "Temperature adjustment - after reading input"
                )

                current_temp_float = float(current_temp_str)
                self.logger.info(
                    f"[{self.req_id}] Page current temperature: {current_temp_float}, Target: {clamped_temp}"
                )

                if abs(current_temp_float - clamped_temp) < 0.001:
                    self.logger.info(
                        f"[{self.req_id}] Page temperature ({current_temp_float}) matches target ({clamped_temp}). Updating cache."
                    )
                    page_params_cache["temperature"] = current_temp_float
                else:
                    self.logger.info(
                        f"[{self.req_id}] Updating temperature from {current_temp_float} to {clamped_temp}..."
                    )
                    await temp_input_locator.fill(str(clamped_temp), timeout=5000)
                    await self._check_disconnect(
                        check_client_disconnected, "Temperature adjustment - after fill"
                    )

                    await asyncio.sleep(0.1)
                    new_temp_str = await temp_input_locator.input_value(timeout=3000)
                    new_temp_float = float(new_temp_str)

                    if abs(new_temp_float - clamped_temp) < 0.001:
                        self.logger.info(
                            f"[{self.req_id}] ✅ Temperature successfully updated to: {new_temp_float}. Cache updated."
                        )
                        page_params_cache["temperature"] = new_temp_float
                    else:
                        self.logger.warning(
                            f"[{self.req_id}] ⚠️ Temperature verification failed. Page shows: {new_temp_float}, Expected: {clamped_temp}. Clearing cache."
                        )
                        page_params_cache.pop("temperature", None)
                        await save_error_snapshot(
                            f"temperature_verify_fail_{self.req_id}"
                        )

            except ValueError as ve:
                self.logger.error(f"[{self.req_id}] Error converting temperature to float: {ve}. Clearing cache.")
                page_params_cache.pop("temperature", None)
                await save_error_snapshot(f"temperature_value_error_{self.req_id}")
            except Exception as pw_err:
                self.logger.error(f"[{self.req_id}] ❌ Error operating temperature input: {pw_err}. Clearing cache.")
                page_params_cache.pop("temperature", None)
                await save_error_snapshot(f"temperature_playwright_error_{self.req_id}")
                if isinstance(pw_err, ClientDisconnectedError):
                    raise

    async def _adjust_max_tokens(
        self,
        max_tokens: int,
        page_params_cache: dict,
        params_cache_lock: asyncio.Lock,
        model_id_to_use: Optional[str],
        parsed_model_list: list,
        check_client_disconnected: Callable,
    ):
        """Adjust max output tokens parameter."""
        async with params_cache_lock:
            self.logger.info(f"[{self.req_id}] Checking and adjusting Max Output Tokens...")
            min_val_for_tokens = 1
            max_val_for_tokens_from_model = 65536

            if model_id_to_use and parsed_model_list:
                current_model_data = next(
                    (m for m in parsed_model_list if m.get("id") == model_id_to_use),
                    None,
                )
                if (
                    current_model_data
                    and current_model_data.get("supported_max_output_tokens")
                    is not None
                ):
                    try:
                        supported_tokens = int(
                            current_model_data["supported_max_output_tokens"]
                        )
                        if supported_tokens > 0:
                            max_val_for_tokens_from_model = supported_tokens
                        else:
                            self.logger.warning(
                                f"[{self.req_id}] Model {model_id_to_use} supported_max_output_tokens invalid: {supported_tokens}"
                            )
                    except (ValueError, TypeError):
                        self.logger.warning(
                            f"[{self.req_id}] Failed to parse supported_max_output_tokens for model {model_id_to_use}"
                        )

            clamped_max_tokens = max(
                min_val_for_tokens, min(max_val_for_tokens_from_model, max_tokens)
            )
            if clamped_max_tokens != max_tokens:
                self.logger.warning(
                    f"[{self.req_id}] Requested Max Tokens {max_tokens} out of model range, adjusted to {clamped_max_tokens}"
                )

            cached_max_tokens = page_params_cache.get("max_output_tokens")
            if (
                cached_max_tokens is not None
                and cached_max_tokens == clamped_max_tokens
            ):
                self.logger.info(
                    f"[{self.req_id}] Max Output Tokens ({clamped_max_tokens}) matches cache. Skipping page interaction."
                )
                return

            max_tokens_input_locator = self.page.locator(MAX_OUTPUT_TOKENS_SELECTOR)

            try:
                await expect_async(max_tokens_input_locator).to_be_visible(timeout=5000)
                await self._check_disconnect(
                    check_client_disconnected, "Max Tokens adjustment - after input visible"
                )

                current_max_tokens_str = await max_tokens_input_locator.input_value(
                    timeout=3000
                )
                current_max_tokens_int = int(current_max_tokens_str)

                if current_max_tokens_int == clamped_max_tokens:
                    self.logger.info(
                        f"[{self.req_id}] Page Max Tokens ({current_max_tokens_int}) matches request ({clamped_max_tokens}). Updating cache."
                    )
                    page_params_cache["max_output_tokens"] = current_max_tokens_int
                else:
                    self.logger.info(
                        f"[{self.req_id}] Updating Max Tokens from {current_max_tokens_int} to {clamped_max_tokens}..."
                    )
                    await max_tokens_input_locator.fill(
                        str(clamped_max_tokens), timeout=5000
                    )
                    await self._check_disconnect(
                        check_client_disconnected, "Max Tokens adjustment - after fill"
                    )

                    await asyncio.sleep(0.1)
                    new_max_tokens_str = await max_tokens_input_locator.input_value(
                        timeout=3000
                    )
                    new_max_tokens_int = int(new_max_tokens_str)

                    if new_max_tokens_int == clamped_max_tokens:
                        self.logger.info(
                            f"[{self.req_id}] ✅ Max Output Tokens successfully updated to: {new_max_tokens_int}"
                        )
                        page_params_cache["max_output_tokens"] = new_max_tokens_int
                    else:
                        self.logger.warning(
                            f"[{self.req_id}] ⚠️ Max Tokens verification failed. Page shows: {new_max_tokens_int}, Expected: {clamped_max_tokens}. Clearing cache."
                        )
                        page_params_cache.pop("max_output_tokens", None)
                        await save_error_snapshot(
                            f"max_tokens_verify_fail_{self.req_id}"
                        )

            except (ValueError, TypeError) as ve:
                self.logger.error(f"[{self.req_id}] Error converting Max Tokens value: {ve}. Clearing cache.")
                page_params_cache.pop("max_output_tokens", None)
                await save_error_snapshot(f"max_tokens_value_error_{self.req_id}")
            except Exception as e:
                self.logger.error(f"[{self.req_id}] ❌ Error adjusting Max Output Tokens: {e}. Clearing cache.")
                page_params_cache.pop("max_output_tokens", None)
                await save_error_snapshot(f"max_tokens_error_{self.req_id}")
                if isinstance(e, ClientDisconnectedError):
                    raise

    async def _adjust_stop_sequences(
        self,
        stop_sequences,
        page_params_cache: dict,
        params_cache_lock: asyncio.Lock,
        check_client_disconnected: Callable,
    ):
        """Adjust stop sequences parameter."""
        async with params_cache_lock:
            self.logger.info(f"[{self.req_id}] Checking and setting Stop Sequences...")

            # Normalize input
            normalized_requested_stops = set()
            if stop_sequences is not None:
                if isinstance(stop_sequences, str):
                    if stop_sequences.strip():
                        normalized_requested_stops.add(stop_sequences.strip())
                elif isinstance(stop_sequences, list):
                    for s in stop_sequences:
                        if isinstance(s, str) and s.strip():
                            normalized_requested_stops.add(s.strip())

            cached_stops_set = page_params_cache.get("stop_sequences")

            if (
                cached_stops_set is not None
                and cached_stops_set == normalized_requested_stops
            ):
                self.logger.info(f"[{self.req_id}] Requested Stop Sequences match cache. Skipping page interaction.")
                return

            stop_input_locator = self.page.locator(STOP_SEQUENCE_INPUT_SELECTOR)
            remove_chip_buttons_locator = self.page.locator(
                MAT_CHIP_REMOVE_BUTTON_SELECTOR
            )

            try:
                # Clear existing sequences
                initial_chip_count = await remove_chip_buttons_locator.count()
                removed_count = 0
                max_removals = initial_chip_count + 5

                while (
                    await remove_chip_buttons_locator.count() > 0
                    and removed_count < max_removals
                ):
                    await self._check_disconnect(
                        check_client_disconnected, "Stop Sequences clearing - loop start"
                    )
                    try:
                        await remove_chip_buttons_locator.first.click(timeout=2000)
                        removed_count += 1
                        await asyncio.sleep(0.15)
                    except Exception:
                        break

                # Add new sequences
                if normalized_requested_stops:
                    await expect_async(stop_input_locator).to_be_visible(timeout=5000)
                    for seq in normalized_requested_stops:
                        await stop_input_locator.fill(seq, timeout=3000)
                        await stop_input_locator.press("Enter", timeout=3000)
                        await asyncio.sleep(0.2)

                page_params_cache["stop_sequences"] = normalized_requested_stops
                self.logger.info(f"[{self.req_id}] ✅ Stop Sequences successfully set. Cache updated.")

            except Exception as e:
                self.logger.error(f"[{self.req_id}] ❌ Error setting Stop Sequences: {e}")
                page_params_cache.pop("stop_sequences", None)
                await save_error_snapshot(f"stop_sequence_error_{self.req_id}")
                if isinstance(e, ClientDisconnectedError):
                    raise

    async def _adjust_top_p(self, top_p: float, check_client_disconnected: Callable):
        """Adjust Top P parameter."""
        self.logger.info(f"[{self.req_id}] Checking and adjusting Top P...")
        clamped_top_p = max(0.0, min(1.0, top_p))

        if abs(clamped_top_p - top_p) > 1e-9:
            self.logger.warning(
                f"[{self.req_id}] Requested Top P {top_p} out of range [0, 1], adjusted to {clamped_top_p}"
            )

        top_p_input_locator = self.page.locator(TOP_P_INPUT_SELECTOR)
        try:
            await expect_async(top_p_input_locator).to_be_visible(timeout=5000)
            await self._check_disconnect(check_client_disconnected, "Top P adjustment - after input visible")

            current_top_p_str = await top_p_input_locator.input_value(timeout=3000)
            current_top_p_float = float(current_top_p_str)

            if abs(current_top_p_float - clamped_top_p) > 1e-9:
                self.logger.info(
                    f"[{self.req_id}] Page Top P ({current_top_p_float}) differs from request ({clamped_top_p}), updating..."
                )
                await top_p_input_locator.fill(str(clamped_top_p), timeout=5000)
                await self._check_disconnect(
                    check_client_disconnected, "Top P adjustment - after fill"
                )

                # Verify
                await asyncio.sleep(0.1)
                new_top_p_str = await top_p_input_locator.input_value(timeout=3000)
                new_top_p_float = float(new_top_p_str)

                if abs(new_top_p_float - clamped_top_p) <= 1e-9:
                    self.logger.info(
                        f"[{self.req_id}] ✅ Top P successfully updated to: {new_top_p_float}"
                    )
                else:
                    self.logger.warning(
                        f"[{self.req_id}] ⚠️ Top P verification failed. Page shows: {new_top_p_float}, Expected: {clamped_top_p}"
                    )
                    await save_error_snapshot(f"top_p_verify_fail_{self.req_id}")
            else:
                self.logger.info(
                    f"[{self.req_id}] Page Top P ({current_top_p_float}) matches request ({clamped_top_p}), skipping update."
                )

        except (ValueError, TypeError) as ve:
            self.logger.error(f"[{self.req_id}] Error converting Top P value: {ve}")
            await save_error_snapshot(f"top_p_value_error_{self.req_id}")
        except Exception as e:
            self.logger.error(f"[{self.req_id}] ❌ Error adjusting Top P: {e}")
            await save_error_snapshot(f"top_p_error_{self.req_id}")
            if isinstance(e, ClientDisconnectedError):
                raise

    async def clear_chat_history(self, check_client_disconnected: Callable):
        """Clear chat history."""
        self.logger.info(f"[{self.req_id}] Starting chat history clearing...")
        await self._check_disconnect(check_client_disconnected, "Start Clear Chat")

        try:
            # Handle case where AI is still generating (blocks clear button)
            submit_button_locator = self.page.locator(SUBMIT_BUTTON_SELECTOR)
            try:
                self.logger.info(f"[{self.req_id}] Checking submit button state...")
                # Short timeout to avoid blocking
                await expect_async(submit_button_locator).to_be_enabled(timeout=1000)
                self.logger.info(f"[{self.req_id}] Submit button enabled, attempting click to stop generation...")
                await submit_button_locator.click(timeout=CLICK_TIMEOUT_MS)
                
                try:
                    await expect_async(submit_button_locator).to_be_disabled(
                        timeout=1200
                    )
                except Exception:
                    pass
                self.logger.info(f"[{self.req_id}] Stop generation click attempted.")
            except Exception:
                # Expected if button unavailable or disabled
                pass

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
                self.logger.info(f'[{self.req_id}] "Clear Chat" button enabled, proceeding.')
            except Exception as e_enable:
                is_new_chat_url = "/prompts/new_chat" in self.page.url.rstrip("/")
                if is_new_chat_url:
                    self.logger.info(
                        f'[{self.req_id}] "Clear Chat" button disabled (Expected on new_chat page). Skipping.'
                    )
                else:
                    self.logger.warning(
                        f'[{self.req_id}] Wait for "Clear Chat" button enabled failed: {e_enable}. Clear might fail.'
                    )

            await self._check_disconnect(
                check_client_disconnected, 'Clear Chat - after button check'
            )

            if can_attempt_clear:
                await self._execute_chat_clear(
                    clear_chat_button_locator,
                    confirm_button_locator,
                    overlay_locator,
                    check_client_disconnected,
                )
                await self._verify_chat_cleared(check_client_disconnected)
                self.logger.info(f"[{self.req_id}] Chat cleared, re-enabling 'Temporary Chat' mode...")
                await enable_temporary_chat_mode(self.page)

        except ClientDisconnectedError:
            self.logger.info(f"[{self.req_id}] Client disconnected during chat history cleanup. Session reset.")
        except Exception as e_clear:
            self.logger.error(f"[{self.req_id}] Error during chat clearing: {e_clear}")
            if not (
                isinstance(e_clear, ClientDisconnectedError)
                or (hasattr(e_clear, "name") and "Disconnect" in e_clear.name)
            ):
                await save_error_snapshot(f"clear_chat_error_{self.req_id}")
            raise

    async def _execute_chat_clear(
        self,
        clear_chat_button_locator,
        confirm_button_locator,
        overlay_locator,
        check_client_disconnected: Callable,
    ):
        """执行清空聊天操作"""
        overlay_initially_visible = False
        try:
            if await overlay_locator.is_visible(timeout=1000):
                overlay_initially_visible = True
                self.logger.info(f'[{self.req_id}] 清空聊天确认遮罩层已可见。直接点击"继续"。')
        except TimeoutError:
            self.logger.info(f"[{self.req_id}] 清空聊天确认遮罩层初始不可见 (检查超时或未找到)。")
            overlay_initially_visible = False
        except Exception as e_vis_check:
            self.logger.warning(f"[{self.req_id}] 检查遮罩层可见性时发生错误: {e_vis_check}。假定不可见。")
            overlay_initially_visible = False

        await self._check_disconnect(check_client_disconnected, "清空聊天 - 初始遮罩层检查后")

        if overlay_initially_visible:
            self.logger.info(
                f'[{self.req_id}] 点击"继续"按钮 (遮罩层已存在): {CLEAR_CHAT_CONFIRM_BUTTON_SELECTOR}'
            )
            await confirm_button_locator.click(timeout=CLICK_TIMEOUT_MS)
        else:
            self.logger.info(
                f'[{self.req_id}] 点击"清空聊天"按钮: {CLEAR_CHAT_BUTTON_SELECTOR}'
            )
            # 若存在透明遮罩层拦截指针事件，先尝试清理
            try:
                await self._dismiss_backdrops()
            except Exception:
                pass
            try:
                try:
                    await clear_chat_button_locator.scroll_into_view_if_needed()
                except Exception:
                    pass
                await clear_chat_button_locator.click(timeout=CLICK_TIMEOUT_MS)
            except Exception as first_click_err:
                self.logger.warning(
                    f"[{self.req_id}] 清空按钮第一次点击失败，尝试清理遮罩并强制点击: {first_click_err}"
                )
                try:
                    await self._dismiss_backdrops()
                except Exception:
                    pass
                try:
                    await clear_chat_button_locator.click(
                        timeout=CLICK_TIMEOUT_MS, force=True
                    )
                except Exception as force_click_err:
                    self.logger.error(f"[{self.req_id}] 清空按钮强制点击仍失败: {force_click_err}")
                    raise
            await self._check_disconnect(check_client_disconnected, '清空聊天 - 点击"清空聊天"后')

            try:
                self.logger.info(f"[{self.req_id}] 等待清空聊天确认遮罩层出现: {OVERLAY_SELECTOR}")
                await expect_async(overlay_locator).to_be_visible(
                    timeout=WAIT_FOR_ELEMENT_TIMEOUT_MS
                )
                self.logger.info(f"[{self.req_id}] 清空聊天确认遮罩层已出现。")
            except TimeoutError:
                error_msg = f"等待清空聊天确认遮罩层超时 (点击清空按钮后)。请求 ID: {self.req_id}"
                self.logger.error(error_msg)
                await save_error_snapshot(f"clear_chat_overlay_timeout_{self.req_id}")
                raise Exception(error_msg)

            await self._check_disconnect(check_client_disconnected, "清空聊天 - 遮罩层出现后")
            self.logger.info(
                f'[{self.req_id}] 点击"继续"按钮 (在对话框中): {CLEAR_CHAT_CONFIRM_BUTTON_SELECTOR}'
            )
            try:
                await confirm_button_locator.scroll_into_view_if_needed()
            except Exception:
                pass
            try:
                await confirm_button_locator.click(timeout=CLICK_TIMEOUT_MS)
            except Exception as confirm_err:
                self.logger.warning(
                    f'[{self.req_id}] 首次点击"继续"失败，尝试 force 点击: {confirm_err}'
                )
                try:
                    await confirm_button_locator.click(
                        timeout=CLICK_TIMEOUT_MS, force=True
                    )
                except Exception as confirm_force_err:
                    self.logger.error(
                        f'[{self.req_id}] "继续"按钮 force 点击仍失败: {confirm_force_err}'
                    )
                    raise

        await self._check_disconnect(check_client_disconnected, '清空聊天 - 点击"继续"后')

        # 等待对话框消失
        max_retries_disappear = 3
        for attempt_disappear in range(max_retries_disappear):
            try:
                self.logger.info(
                    f"[{self.req_id}] 等待清空聊天确认按钮/对话框消失 (尝试 {attempt_disappear + 1}/{max_retries_disappear})..."
                )
                await expect_async(confirm_button_locator).to_be_hidden(
                    timeout=CLEAR_CHAT_VERIFY_TIMEOUT_MS
                )
                await expect_async(overlay_locator).to_be_hidden(timeout=1000)
                self.logger.info(f"[{self.req_id}] ✅ 清空聊天确认对话框已成功消失。")
                break
            except TimeoutError:
                self.logger.warning(
                    f"[{self.req_id}] ⚠️ 等待清空聊天确认对话框消失超时 (尝试 {attempt_disappear + 1}/{max_retries_disappear})。"
                )
                if attempt_disappear < max_retries_disappear - 1:
                    await self._check_disconnect(
                        check_client_disconnected,
                        f"清空聊天 - 重试消失检查 {attempt_disappear + 1} 前",
                    )
                    continue
                else:
                    error_msg = f"达到最大重试次数。清空聊天确认对话框未消失。请求 ID: {self.req_id}"
                    self.logger.error(error_msg)
                    await save_error_snapshot(
                        f"clear_chat_dialog_disappear_timeout_{self.req_id}"
                    )
                    raise Exception(error_msg)
            except ClientDisconnectedError:
                self.logger.info(f"[{self.req_id}] 客户端在等待清空确认对话框消失时断开连接。")
                raise
            except Exception as other_err:
                self.logger.warning(f"[{self.req_id}] 等待清空确认对话框消失时发生其他错误: {other_err}")
                if attempt_disappear < max_retries_disappear - 1:
                    continue
                else:
                    raise

            await self._check_disconnect(
                check_client_disconnected, f"清空聊天 - 消失检查尝试 {attempt_disappear + 1} 后"
            )

    async def _dismiss_backdrops(self):
        """尝试关闭可能残留的 cdk 透明遮罩层以避免点击被拦截。"""
        try:
            backdrop = self.page.locator(
                "div.cdk-overlay-backdrop.cdk-overlay-backdrop-showing, div.cdk-overlay-backdrop.cdk-overlay-transparent-backdrop.cdk-overlay-backdrop-showing"
            )
            for i in range(3):
                cnt = 0
                try:
                    cnt = await backdrop.count()
                except Exception:
                    cnt = 0
                if cnt and cnt > 0:
                    self.logger.info(
                        f"[{self.req_id}] 检测到透明遮罩层 ({cnt})，发送 ESC 关闭 (尝试 {i+1}/3)。"
                    )
                    try:
                        await self.page.keyboard.press("Escape")
                        try:
                            await expect_async(backdrop).to_be_hidden(timeout=500)
                        except Exception:
                            pass
                    except Exception:
                        pass
                else:
                    break
        except Exception:
            pass

    async def _verify_chat_cleared(self, check_client_disconnected: Callable):
        """验证聊天已清空"""
        last_response_container = self.page.locator(RESPONSE_CONTAINER_SELECTOR).last
        await self._check_disconnect(
            check_client_disconnected, "After Clear Post-Check"
        )
        try:
            await expect_async(last_response_container).to_be_hidden(
                timeout=CLEAR_CHAT_VERIFY_TIMEOUT_MS - 500
            )
            self.logger.info(f"[{self.req_id}] ✅ 聊天已成功清空 (验证通过 - 最后响应容器隐藏)。")
        except Exception as verify_err:
            self.logger.warning(
                f"[{self.req_id}] ⚠️ 警告: 清空聊天验证失败 (最后响应容器未隐藏): {verify_err}"
            )

    # 已移除直接设置 <input type=file> 的上传路径，统一采用菜单上传方式

    async def _handle_post_upload_dialog(self):
        """处理上传后可能出现的授权/版权确认对话框，优先点击同意类按钮，不主动关闭重要对话框。"""
        try:
            overlay_container = self.page.locator("div.cdk-overlay-container")
            if await overlay_container.count() == 0:
                return

            # 候选同意按钮的文本/属性
            agree_texts = [
                "Agree",
                "I agree",
                "Allow",
                "Continue",
                "OK",
                "确定",
                "同意",
                "继续",
                "允许",
            ]
            # 统一在 overlay 容器内查找可见按钮
            for text in agree_texts:
                try:
                    btn = overlay_container.locator(f"button:has-text('{text}')")
                    if await btn.count() > 0 and await btn.first.is_visible(
                        timeout=300
                    ):
                        await btn.first.click()
                        self.logger.info(f"[{self.req_id}] 上传后对话框: 点击按钮 '{text}'。")
                        await asyncio.sleep(0.3)
                        break
                except Exception:
                    continue
            # 若存在带 aria-label 的版权按钮
            try:
                acknow_btn_locator = self.page.locator(
                    'button[aria-label*="copyright" i], button[aria-label*="acknowledge" i]'
                )
                if (
                    await acknow_btn_locator.count() > 0
                    and await acknow_btn_locator.first.is_visible(timeout=300)
                ):
                    await acknow_btn_locator.first.click()
                    self.logger.info(
                        f"[{self.req_id}] 上传后对话框: 点击版权确认按钮 (aria-label 匹配)。"
                    )
                    await asyncio.sleep(0.3)
            except Exception:
                pass

            # 等待遮罩层消失（尽量不强制 ESC，避免意外取消）
            try:
                overlay_backdrop = self.page.locator(
                    "div.cdk-overlay-backdrop.cdk-overlay-backdrop-showing"
                )
                if await overlay_backdrop.count() > 0:
                    try:
                        await expect_async(overlay_backdrop).to_be_hidden(timeout=3000)
                        self.logger.info(f"[{self.req_id}] 上传后对话框遮罩层已隐藏。")
                    except Exception:
                        self.logger.warning(f"[{self.req_id}] 上传后对话框遮罩层仍存在，后续提交可能被拦截。")
            except Exception:
                pass
        except Exception:
            pass

    async def _ensure_files_attached(
        self, wrapper_locator, expected_min: int = 1, timeout_ms: int = 5000
    ) -> bool:
        """轮询检查输入区域内 file input 的 files 是否 >= 期望数量。"""
        end = asyncio.get_event_loop().time() + (timeout_ms / 1000)
        while asyncio.get_event_loop().time() < end:
            try:
                # NOTE: normalize JS eval string to avoid parser confusion
                counts = await wrapper_locator.evaluate(
                    """
                    (el) => {
                      const result = {inputs:0, chips:0, blobs:0};
                      try { el.querySelectorAll('input[type="file"]').forEach(i => { result.inputs += (i.files ? i.files.length : 0); }); } catch(e){}
                      try { result.chips = el.querySelectorAll('button[aria-label*="Remove" i], button[aria-label*="asset" i]').length; } catch(e){}
                      try { result.blobs = el.querySelectorAll('img[src^="blob:"], video[src^="blob:"]').length; } catch(e){}
                      return result;
                    }
                    """
                )

                total = 0
                if isinstance(counts, dict):
                    total = max(
                        int(counts.get("inputs") or 0),
                        int(counts.get("chips") or 0),
                        int(counts.get("blobs") or 0),
                    )
                if total >= expected_min:
                    self.logger.info(
                        f"[{self.req_id}] 已检测到已附加文件: inputs={counts.get('inputs')}, chips={counts.get('chips')}, blobs={counts.get('blobs')} (>= {expected_min})"
                    )
                    return True
            except Exception:
                pass
            await asyncio.sleep(0.2)
        self.logger.warning(f"[{self.req_id}] 未能在超时内检测到已附加文件 (期望 >= {expected_min})")
        return False

    async def _open_upload_menu_and_choose_file(self, files_list: List[str]) -> bool:
        """通过'Insert assets'菜单选择'上传/Upload'项并打开文件选择器设置文件。"""
        try:
            # 若上一次菜单/对话的透明遮罩仍在，先尝试关闭
            try:
                tb = self.page.locator(
                    "div.cdk-overlay-backdrop.cdk-overlay-transparent-backdrop.cdk-overlay-backdrop-showing"
                )
                if await tb.count() > 0 and await tb.first.is_visible(timeout=300):
                    await self.page.keyboard.press("Escape")
                    await asyncio.sleep(0.2)
            except Exception:
                pass

            trigger = self.page.locator(
                'button[aria-label="Insert assets such as images, videos, files, or audio"]'
            )
            await trigger.click()
            menu_container = self.page.locator("div.cdk-overlay-container")
            # 等待菜单显示
            try:
                await expect_async(
                    menu_container.locator("div[role='menu']").first
                ).to_be_visible(timeout=3000)
            except Exception:
                # 再尝试一次触发
                try:
                    await trigger.click()
                    await expect_async(
                        menu_container.locator("div[role='menu']").first
                    ).to_be_visible(timeout=3000)
                except Exception:
                    self.logger.warning(f"[{self.req_id}] 未能显示上传菜单面板。")
                    return False

            # 仅使用 aria-label='Upload File' 的菜单项
            try:
                upload_btn = menu_container.locator(
                    "div[role='menu'] button[role='menuitem'][aria-label='Upload File']"
                )
                if await upload_btn.count() == 0:
                    # 退化到按文本匹配 Upload File
                    upload_btn = menu_container.locator(
                        "div[role='menu'] button[role='menuitem']:has-text('Upload File')"
                    )
                if await upload_btn.count() == 0:
                    self.logger.warning(f"[{self.req_id}] 未找到 'Upload File' 菜单项。")
                    return False
                btn = upload_btn.first
                await expect_async(btn).to_be_visible(timeout=2000)
                # 优先使用内部隐藏 input[type=file]
                input_loc = btn.locator('input[type="file"]')
                if await input_loc.count() > 0:
                    await input_loc.set_input_files(files_list)
                    self.logger.info(
                        f"[{self.req_id}] ✅ 通过菜单项(Upload File) 隐藏 input 设置文件成功: {len(files_list)} 个"
                    )
                else:
                    # 回退为原生文件选择器
                    async with self.page.expect_file_chooser() as fc_info:
                        await btn.click()
                    file_chooser = await fc_info.value
                    await file_chooser.set_files(files_list)
                    self.logger.info(
                        f"[{self.req_id}] ✅ 通过文件选择器设置文件成功: {len(files_list)} 个"
                    )
            except Exception as e_set:
                self.logger.error(f"[{self.req_id}] 设置文件失败: {e_set}")
                return False
            # 关闭可能残留的菜单遮罩
            try:
                backdrop = self.page.locator(
                    "div.cdk-overlay-backdrop.cdk-overlay-backdrop-showing, div.cdk-overlay-backdrop.cdk-overlay-transparent-backdrop.cdk-overlay-backdrop-showing"
                )
                if await backdrop.count() > 0:
                    await self.page.keyboard.press("Escape")
                    await asyncio.sleep(0.2)
            except Exception:
                pass
            # 处理可能的授权弹窗
            await self._handle_post_upload_dialog()
            return True
        except Exception as e:
            self.logger.error(f"[{self.req_id}] 通过上传菜单设置文件失败: {e}")
            return False

    async def _safe_reload_page(self):
        """
        安全地刷新页面。如果刷新超时，则关闭卡死的标签页并在同一上下文中创建一个新标签页。
        这样可以保留浏览器进程和身份验证状态（存储在上下文中）。
        """
        import server
        from .operations import _handle_model_list_response

        try:
            self.logger.info(f"[{self.req_id}] 尝试重新加载页面...")
            # 尝试标准重新加载
            await self.page.reload(timeout=30000)
            await self.page.wait_for_load_state("domcontentloaded", timeout=30000)
            self.logger.info(f"[{self.req_id}] ✅ 页面重新加载成功。")
        except TimeoutError:
            self.logger.warning(f"[{self.req_id}] ⚠️ 页面重新加载超时。正在启动优化的标签页恢复（软终止）...")
            
            try:
                # 获取当前上下文
                context = self.page.context
                
                # 1. 关闭卡死的页面
                try:
                    await self.page.close()
                    self.logger.info(f"[{self.req_id}] 卡死的标签页已关闭。")
                except Exception as close_err:
                    self.logger.warning(f"[{self.req_id}] 关闭卡死标签页时出错 (可能已关闭): {close_err}")

                # 2. 在同一上下文中创建新页面
                new_page = await context.new_page()
                self.logger.info(f"[{self.req_id}] 新标签页已创建。")

                # 3. 更新 PageController 的页面引用
                self.page = new_page
                
                # 4. 更新全局 server 状态中的页面引用
                server.page_instance = new_page
                
                # 5. 重新附加必要的事件监听器
                self.logger.info(f"[{self.req_id}] 正在重新附加模型列表响应监听器...")
                new_page.on("response", _handle_model_list_response)

                # 6. 导航到 AI Studio
                target_url = f"https://{AI_STUDIO_URL_PATTERN}prompts/new_chat"
                self.logger.info(f"[{self.req_id}] 正在导航到: {target_url}")
                await new_page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
                
                self.logger.info(f"[{self.req_id}] ✅ 标签页恢复成功！已在同一上下文中加载新页面。")

            except Exception as recovery_err:
                self.logger.error(f"[{self.req_id}] ❌ 标签页恢复失败: {recovery_err}")
                raise recovery_err

    async def submit_prompt(self, prompt: str, image_list: List, check_client_disconnected: Callable):
        """提交提示到页面。包含重试和自动刷新机制，以及多种提交方式的回退。"""
        max_retries = 2
        
        for attempt in range(max_retries):
            try:
                self.logger.info(f"[{self.req_id}] 填充并提交提示 (尝试 {attempt + 1}/{max_retries})...")
                
                prompt_textarea_locator = self.page.locator(PROMPT_TEXTAREA_SELECTOR)
                autosize_wrapper_locator = self.page.locator('ms-prompt-input-wrapper ms-autosize-textarea')
                submit_button_locator = self.page.locator(SUBMIT_BUTTON_SELECTOR)

                # 等待输入框可见 (Timeout 10s)
                await expect_async(prompt_textarea_locator).to_be_visible(timeout=10000)
                await self._check_disconnect(check_client_disconnected, "After Input Visible")

                # 使用 JavaScript 填充文本
                await prompt_textarea_locator.evaluate(
                    '''
                    (element, text) => {
                        element.value = text;
                        element.dispatchEvent(new Event('input', { bubbles: true, cancelable: true }));
                        element.dispatchEvent(new Event('change', { bubbles: true, cancelable: true }));
                    }
                    ''',
                    prompt
                )
                await autosize_wrapper_locator.evaluate('(element, text) => { element.setAttribute("data-value", text); }', prompt)
                await self._check_disconnect(check_client_disconnected, "After Input Fill")

                # 上传（仅使用菜单 + 隐藏 input 设置文件；处理可能的授权弹窗）
                try:
                    self.logger.info(f"[{self.req_id}] 待上传附件数量: {len(image_list)}")
                except Exception:
                    pass
                if len(image_list) > 0:
                    ok = await self._open_upload_menu_and_choose_file(image_list)
                    if not ok:
                        self.logger.error(f"[{self.req_id}] 在上传文件时发生错误: 通过菜单方式未能设置文件")

                # 等待发送按钮启用 (Timeout reduced to 10s to detect hang early)
                wait_timeout_ms_submit_enabled = 10000
                try:
                    await self._check_disconnect(check_client_disconnected, "填充提示后等待发送按钮启用 - 前置检查")
                    await expect_async(submit_button_locator).to_be_enabled(timeout=wait_timeout_ms_submit_enabled)
                    self.logger.info(f"[{self.req_id}] ✅ 发送按钮已启用。")
                except Exception as e_pw_enabled:
                    self.logger.warning(f"[{self.req_id}] ⚠️ 等待发送按钮启用超时 (可能是页面卡顿): {e_pw_enabled}")
                    raise # Trigger retry logic

                await self._check_disconnect(check_client_disconnected, "After Submit Button Enabled")
                await asyncio.sleep(0.3)

                # 优先点击按钮提交，其次回车提交，最后组合键提交
                button_clicked = False
                try:
                    self.logger.info(f"[{self.req_id}] 尝试点击提交按钮...")
                    # 提交前再处理一次潜在对话框，避免按钮点击被拦截
                    await self._handle_post_upload_dialog()
                    await submit_button_locator.click(timeout=5000)
                    self.logger.info(f"[{self.req_id}] ✅ 提交按钮点击完成。")
                    button_clicked = True
                    
                    # Immediate Check: Call check_quota_limit() immediately after clicking.
                    await check_quota_limit(self.page, self.req_id)

                except Exception as click_err:
                    self.logger.error(f"[{self.req_id}] ❌ 提交按钮点击失败: {click_err}")
                    # Don't snapshot here, retry mechanism handles it or next methods try

                # 如果按钮点击失败，或者虽然点击了但没有触发提交（这里简化逻辑，如果点击代码跑通则认为点击成功，
                # 后续通过响应检测来判定是否真正提交。如果点击报错，则 button_clicked 为 False，进入备用方案）
                
                if not button_clicked:
                    self.logger.info(f"[{self.req_id}] 按钮提交失败，尝试回车键提交...")
                    submitted_successfully = await self._try_enter_submit(prompt_textarea_locator, check_client_disconnected)
                    if not submitted_successfully:
                        self.logger.info(f"[{self.req_id}] 回车提交失败，尝试组合键提交...")
                        combo_ok = await self._try_combo_submit(prompt_textarea_locator, check_client_disconnected)
                        if not combo_ok:
                            self.logger.error(f"[{self.req_id}] ❌ 组合键提交也失败。")
                            raise Exception("Submit failed: Button, Enter, and Combo key all failed")

                await self._check_disconnect(check_client_disconnected, "After Submit")
                
                # If we got here, success!
                return

            except Exception as e_input_submit:
                self.logger.warning(f"[{self.req_id}] 输入/提交过程发生错误 (尝试 {attempt + 1}/{max_retries}): {e_input_submit}")
                
                if isinstance(e_input_submit, ClientDisconnectedError):
                    raise # Don't retry if client disconnected

                if isinstance(e_input_submit, QuotaExceededError):
                    raise # Don't retry if quota exceeded
                
                if attempt < max_retries - 1:
                    self.logger.info(f"[{self.req_id}] ⚠️ 遇到错误，尝试刷新页面并重试...")
                    try:
                        await save_error_snapshot(f"submit_retry_before_reload_{self.req_id}_{attempt}")
                        # 使用新的安全刷新方法
                        await self._safe_reload_page()
                        await asyncio.sleep(2) # Give it a bit more time
                        self.logger.info(f"[{self.req_id}] ✅ 页面刷新/恢复完成，准备重试。")
                    except Exception as reload_err:
                        self.logger.error(f"[{self.req_id}] ❌ 页面刷新失败: {reload_err}")
                        raise e_input_submit # If reload fails, raise original or reload error
                else:
                    self.logger.error(f"[{self.req_id}] ❌ 所有重试尝试均失败。")
                    await save_error_snapshot(f"input_submit_error_final_{self.req_id}")
                    raise e_input_submit

    async def _simulate_drag_drop_files(
        self, target_locator, files_list: List[str]
    ) -> None:
        """将本地文件以拖放事件的方式注入到目标元素。
        仅负责触发 dragenter/dragover/drop，不在此处做附加验证以节省时间。
        """
        payloads = []
        for path in files_list:
            try:
                with open(path, "rb") as f:
                    raw = f.read()
                b64 = base64.b64encode(raw).decode("ascii")
                mime, _ = mimetypes.guess_type(path)
                payloads.append(
                    {
                        "name": path.split("/")[-1],
                        "mime": mime or "application/octet-stream",
                        "b64": b64,
                    }
                )
            except Exception as e:
                self.logger.warning(f"[{self.req_id}] 读取文件失败，跳过拖放: {path} - {e}")

        if not payloads:
            raise Exception("无可用文件用于拖放")

        candidates = [
            target_locator,
            self.page.locator("ms-prompt-input-wrapper ms-autosize-textarea textarea"),
            self.page.locator("ms-prompt-input-wrapper ms-autosize-textarea"),
            self.page.locator("ms-prompt-input-wrapper"),
        ]

        last_err = None
        for idx, cand in enumerate(candidates):
            try:
                await expect_async(cand).to_be_visible(timeout=3000)
                await cand.evaluate(
                    """
                    (el, files) => {
                      const dt = new DataTransfer();
                      for (const p of files) {
                        const bstr = atob(p.b64);
                        const len = bstr.length;
                        const u8 = new Uint8Array(len);
                        for (let i = 0; i < len; i++) u8[i] = bstr.charCodeAt(i);
                        const blob = new Blob([u8], { type: p.mime || 'application/octet-stream' });
                        const file = new File([blob], p.name, { type: p.mime || 'application/octet-stream' });
                        dt.items.add(file);
                      }
                      const evEnter = new DragEvent('dragenter', { bubbles: true, cancelable: true, dataTransfer: dt });
                      el.dispatchEvent(evEnter);
                      const evOver = new DragEvent('dragover', { bubbles: true, cancelable: true, dataTransfer: dt });
                      el.dispatchEvent(evOver);
                      const evDrop = new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: dt });
                      el.dispatchEvent(evDrop);
                    }
                    """,
                    payloads,
                )
                await asyncio.sleep(0.5)
                self.logger.info(
                    f"[{self.req_id}] 拖放事件已在候选目标 {idx+1}/{len(candidates)} 上触发。"
                )
                return
            except Exception as e_try:
                last_err = e_try
                continue

        # 兜底：在 document.body 上尝试一次
        try:
            await self.page.evaluate(
                """
                (files) => {
                  const dt = new DataTransfer();
                  for (const p of files) {
                    const bstr = atob(p.b64);
                    const len = bstr.length;
                    const u8 = new Uint8Array(len);
                    for (let i = 0; i < len; i++) u8[i] = bstr.charCodeAt(i);
                    const blob = new Blob([u8], { type: p.mime || 'application/octet-stream' });
                    const file = new File([blob], p.name, { type: p.mime || 'application/octet-stream' });
                    dt.items.add(file);
                  }
                  const el = document.body;
                  const evEnter = new DragEvent('dragenter', { bubbles: true, cancelable: true, dataTransfer: dt });
                  el.dispatchEvent(evEnter);
                  const evOver = new DragEvent('dragover', { bubbles: true, cancelable: true, dataTransfer: dt });
                  el.dispatchEvent(evOver);
                  const evDrop = new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: dt });
                  el.dispatchEvent(evDrop);
                }
                """,
                payloads,
            )
            await asyncio.sleep(0.5)
            self.logger.info(f"[{self.req_id}] 拖放事件已在 document.body 上触发（兜底）。")
            return
        except Exception:
            pass

        raise last_err or Exception("拖放未能在任何候选目标上触发")

    async def _try_enter_submit(
        self, prompt_textarea_locator, check_client_disconnected: Callable
    ) -> bool:
        """优先使用回车键提交。"""
        import os

        try:
            # 检测操作系统
            host_os_from_launcher = os.environ.get("HOST_OS_FOR_SHORTCUT")
            is_mac_determined = False

            if host_os_from_launcher == "Darwin":
                is_mac_determined = True
            elif host_os_from_launcher in ["Windows", "Linux"]:
                is_mac_determined = False
            else:
                # 使用浏览器检测
                try:
                    user_agent_data_platform = await self.page.evaluate(
                        "() => navigator.userAgentData?.platform || ''"
                    )
                except Exception:
                    user_agent_string = await self.page.evaluate(
                        "() => navigator.userAgent || ''"
                    )
                    user_agent_string_lower = user_agent_string.lower()
                    if (
                        "macintosh" in user_agent_string_lower
                        or "mac os x" in user_agent_string_lower
                    ):
                        user_agent_data_platform = "macOS"
                    else:
                        user_agent_data_platform = "Other"

                is_mac_determined = "mac" in user_agent_data_platform.lower()

            shortcut_modifier = "Meta" if is_mac_determined else "Control"
            shortcut_key = "Enter"

            await prompt_textarea_locator.focus(timeout=5000)
            await self._check_disconnect(check_client_disconnected, "After Input Focus")
            await asyncio.sleep(0.1)

            # 记录提交前的输入框内容，用于验证
            original_content = ""
            try:
                original_content = (
                    await prompt_textarea_locator.input_value(timeout=2000) or ""
                )
            except Exception:
                # 如果无法获取原始内容，仍然尝试提交
                pass

            # 尝试回车键提交
            self.logger.info(f"[{self.req_id}] 尝试回车键提交")
            try:
                await self.page.keyboard.press("Enter")
            except Exception:
                try:
                    await prompt_textarea_locator.press("Enter")
                except Exception:
                    pass

            await self._check_disconnect(check_client_disconnected, "After Enter Press")
            await asyncio.sleep(2.0)

            # 验证提交是否成功
            submission_success = False
            try:
                # 方法1: 检查原始输入框是否清空
                current_content = (
                    await prompt_textarea_locator.input_value(timeout=2000) or ""
                )
                if original_content and not current_content.strip():
                    self.logger.info(f"[{self.req_id}] 验证方法1: 输入框已清空，回车键提交成功")
                    submission_success = True

                # 方法2: 检查提交按钮状态
                if not submission_success:
                    submit_button_locator = self.page.locator(SUBMIT_BUTTON_SELECTOR)
                    try:
                        is_disabled = await submit_button_locator.is_disabled(
                            timeout=2000
                        )
                        if is_disabled:
                            self.logger.info(f"[{self.req_id}] 验证方法2: 提交按钮已禁用，回车键提交成功")
                            submission_success = True
                    except Exception:
                        pass

                # 方法3: 检查是否有响应容器出现
                if not submission_success:
                    try:
                        response_container = self.page.locator(
                            RESPONSE_CONTAINER_SELECTOR
                        )
                        container_count = await response_container.count()
                        if container_count > 0:
                            # 检查最后一个容器是否是新的
                            last_container = response_container.last
                            if await last_container.is_visible(timeout=1000):
                                self.logger.info(
                                    f"[{self.req_id}] 验证方法3: 检测到响应容器，回车键提交成功"
                                )
                                submission_success = True
                    except Exception:
                        pass
            except Exception as verify_err:
                self.logger.warning(f"[{self.req_id}] 回车键提交验证过程出错: {verify_err}")
                # 出错时假定提交成功，让后续流程继续
                submission_success = True

            if submission_success:
                self.logger.info(f"[{self.req_id}] ✅ 回车键提交成功")
                return True
            else:
                self.logger.warning(f"[{self.req_id}] ⚠️ 回车键提交验证失败")
                return False
        except Exception as shortcut_err:
            self.logger.warning(f"[{self.req_id}] 回车键提交失败: {shortcut_err}")
            return False

    async def _try_combo_submit(
        self, prompt_textarea_locator, check_client_disconnected: Callable
    ) -> bool:
        """尝试使用组合键提交 (Meta/Control + Enter)。"""
        import os

        try:
            host_os_from_launcher = os.environ.get("HOST_OS_FOR_SHORTCUT")
            is_mac_determined = False
            if host_os_from_launcher == "Darwin":
                is_mac_determined = True
            elif host_os_from_launcher in ["Windows", "Linux"]:
                is_mac_determined = False
            else:
                try:
                    user_agent_data_platform = await self.page.evaluate(
                        "() => navigator.userAgentData?.platform || ''"
                    )
                except Exception:
                    user_agent_string = await self.page.evaluate(
                        "() => navigator.userAgent || ''"
                    )
                    user_agent_string_lower = user_agent_string.lower()
                    if (
                        "macintosh" in user_agent_string_lower
                        or "mac os x" in user_agent_string_lower
                    ):
                        user_agent_data_platform = "macOS"
                    else:
                        user_agent_data_platform = "Other"
                is_mac_determined = "mac" in user_agent_data_platform.lower()

            shortcut_modifier = "Meta" if is_mac_determined else "Control"
            shortcut_key = "Enter"

            await prompt_textarea_locator.focus(timeout=5000)
            await self._check_disconnect(check_client_disconnected, "After Input Focus")
            await asyncio.sleep(0.1)

            # 记录提交前的输入框内容，用于验证
            original_content = ""
            try:
                original_content = (
                    await prompt_textarea_locator.input_value(timeout=2000) or ""
                )
            except Exception:
                pass

            self.logger.info(
                f"[{self.req_id}] 尝试组合键提交: {shortcut_modifier}+{shortcut_key}"
            )
            try:
                await self.page.keyboard.press(f"{shortcut_modifier}+{shortcut_key}")
            except Exception:
                try:
                    await self.page.keyboard.down(shortcut_modifier)
                    await asyncio.sleep(0.05)
                    await self.page.keyboard.press(shortcut_key)
                    await asyncio.sleep(0.05)
                    await self.page.keyboard.up(shortcut_modifier)
                except Exception:
                    pass

            await self._check_disconnect(check_client_disconnected, "After Combo Press")
            await asyncio.sleep(2.0)

            submission_success = False
            try:
                current_content = (
                    await prompt_textarea_locator.input_value(timeout=2000) or ""
                )
                if original_content and not current_content.strip():
                    self.logger.info(f"[{self.req_id}] 验证方法1: 输入框已清空，组合键提交成功")
                    submission_success = True
                if not submission_success:
                    submit_button_locator = self.page.locator(SUBMIT_BUTTON_SELECTOR)
                    try:
                        is_disabled = await submit_button_locator.is_disabled(
                            timeout=2000
                        )
                        if is_disabled:
                            self.logger.info(f"[{self.req_id}] 验证方法2: 提交按钮已禁用，组合键提交成功")
                            submission_success = True
                    except Exception:
                        pass
                if not submission_success:
                    try:
                        response_container = self.page.locator(
                            RESPONSE_CONTAINER_SELECTOR
                        )
                        container_count = await response_container.count()
                        if container_count > 0:
                            last_container = response_container.last
                            if await last_container.is_visible(timeout=1000):
                                self.logger.info(
                                    f"[{self.req_id}] 验证方法3: 检测到响应容器，组合键提交成功"
                                )
                                submission_success = True
                    except Exception:
                        pass
            except Exception as verify_err:
                self.logger.warning(f"[{self.req_id}] 组合键提交验证过程出错: {verify_err}")
                submission_success = True

            if submission_success:
                self.logger.info(f"[{self.req_id}] ✅ 组合键提交成功")
                return True
            else:
                self.logger.warning(f"[{self.req_id}] ⚠️ 组合键提交验证失败")
                return False
        except Exception as combo_err:
            self.logger.warning(f"[{self.req_id}] 组合键提交失败: {combo_err}")
            return False

    async def get_response(self, check_client_disconnected: Callable, prompt_length: int, timeout: Optional[float] = None) -> str:
        """获取响应内容 - 增强版本，包含完整性验证"""
        self.logger.info(f"[{self.req_id}] 等待并获取响应...")

        try:
            # 等待响应容器出现
            response_container_locator = self.page.locator(
                RESPONSE_CONTAINER_SELECTOR
            ).last
            response_element_locator = response_container_locator.locator(
                RESPONSE_TEXT_SELECTOR
            )

            self.logger.info(f"[{self.req_id}] 等待响应元素附加到DOM...")
            await expect_async(response_element_locator).to_be_attached(timeout=90000)
            await self._check_disconnect(check_client_disconnected, "获取响应 - 响应元素已附加")

            # 等待响应完成
            submit_button_locator = self.page.locator(SUBMIT_BUTTON_SELECTOR)
            edit_button_locator = self.page.locator(EDIT_MESSAGE_BUTTON_SELECTOR)
            input_field_locator = self.page.locator(PROMPT_TEXTAREA_SELECTOR)

            self.logger.info(f"[{self.req_id}] 等待响应完成...")
            completion_detected = await _wait_for_response_completion(
                self.page,
                input_field_locator,
                submit_button_locator,
                edit_button_locator,
                self.req_id,
                check_client_disconnected,
                None,
                prompt_length=prompt_length,
                timeout=timeout
            )

            if not completion_detected:
                self.logger.warning(f"[{self.req_id}] 响应完成检测失败，尝试获取当前内容")
            else:
                self.logger.info(f"[{self.req_id}] ✅ 响应完成检测成功")

            # 获取最终响应内容
            final_content = await _get_final_response_content(
                self.page, self.req_id, check_client_disconnected
            )

            # === 核心修复：响应完整性验证 ===
            if not final_content or not final_content.strip():
                self.logger.warning(f"[{self.req_id}] ⚠️ 主方法获取到的响应内容为空，启动稳定性等待和完整性验证...")
                
                # 1. 首先执行稳定性等待，防止假阴性
                stability_success = await self._emergency_stability_wait(check_client_disconnected)
                
                if stability_success:
                    self.logger.info(f"[{self.req_id}] ✅ 稳定性等待成功，重新尝试获取响应...")
                    # 稳定性等待成功后，重新尝试获取内容
                    final_content = await _get_final_response_content(
                        self.page, self.req_id, check_client_disconnected
                    )
                    
                    if final_content and final_content.strip():
                        self.logger.info(f"[{self.req_id}] ✅ 稳定性等待后成功获取响应内容: {len(final_content)} chars")
                        return final_content
                
                # 2. 稳定性等待失败或仍无内容，启动完整性验证
                debug_info = await capture_response_state_for_debug(
                    self.req_id,
                    captured_content="",
                    detection_method="主方法返回空内容后的验证"
                )
                
                # 尝试完整性验证
                verified_data = await self.verify_response_integrity(
                    check_client_disconnected,
                    "主方法返回空内容"
                )
                
                if verified_data and verified_data.get("content", "").strip():
                    verified_content = verified_data["content"]
                    self.logger.info(f"[{self.req_id}] ✅ 完整性验证成功！DOM中存在响应内容: {len(verified_content)} chars")
                    # 保存调试快照以记录这个问题
                    await save_error_snapshot(
                        f"response_integrity_recovered_{self.req_id}",
                        extra_context={
                            "original_method": "get_response",
                            "verification_method": "verify_response_integrity",
                            "recovered_content_length": len(verified_content),
                            "debug_info": debug_info,
                            "stability_wait_attempted": stability_success
                        }
                    )
                    return verified_content
                else:
                    self.logger.error(f"[{self.req_id}] ❌ 稳定性等待和完整性验证均失败，DOM中确实没有响应内容")
                    await save_error_snapshot(
                        f"empty_response_verified_{self.req_id}",
                        extra_context={
                            "method": "get_response + stability_wait + verify_response_integrity",
                            "debug_info": debug_info,
                            "stability_wait_attempted": stability_success
                        }
                    )
                    return ""
            else:
                self.logger.info(f"[{self.req_id}] ✅ 成功获取响应内容 ({len(final_content)} chars)")
                return final_content

        except Exception as e:
            self.logger.error(f"[{self.req_id}] ❌ 获取响应时出错: {e}")
            if not isinstance(e, ClientDisconnectedError):
                await save_error_snapshot(f"get_response_error_{self.req_id}")
            raise

    async def verify_response_integrity(self, check_client_disconnected: Callable, trigger_reason: str = "") -> Dict[str, str]:
        """响应完整性验证 - 核心修复方法
        
        当流式拦截或主方法无法获取内容时，通过DOM直接验证并提取响应。
        这是解决"浏览器显示内容但API返回空"问题的关键方法。
        
        Args:
            check_client_disconnected: 客户端断开检查函数
            trigger_reason: 触发验证的原因描述
            
        Returns:
            Dict[str, str]: 包含content和reasoning_content的字典，如果失败则返回空字典
        """
        self.logger.info(f"[{self.req_id}] 开始响应完整性验证 (原因: {trigger_reason})")
        
        try:
            await self._check_disconnect(check_client_disconnected, "完整性验证开始")
            
            # 1. 检查生成是否真正完成
            regenerate_button_locator = self.page.locator('button[aria-label="Regenerate draft"], button[aria-label="Regenerate response"]')
            regenerate_visible = await regenerate_button_locator.is_visible(timeout=2000)
            
            if regenerate_visible:
                self.logger.info(f"[{self.req_id}] 检测到Regenerate按钮，响应应该已完成")
            else:
                self.logger.warning(f"[{self.req_id}] 未检测到Regenerate按钮，响应可能未完成，但继续验证...")
            
            # 2. 强制等待DOM稳定 (500ms稳定性检查)
            self.logger.info(f"[{self.req_id}] 执行DOM稳定性检查...")
            stability_content = ""
            stability_check_count = 0
            max_stability_checks = 5
            
            while stability_check_count < max_stability_checks:
                await asyncio.sleep(0.1)  # 100ms间隔
                current_content = await self._extract_dom_content()
                
                if current_content and current_content.strip():
                    if current_content == stability_content:
                        # 内容稳定，增加稳定性计数
                        stability_check_count += 1
                        self.logger.debug(f"[{self.req_id}] DOM内容稳定性检查 {stability_check_count}/{max_stability_checks}")
                    else:
                        # 内容变化，重置稳定性计数
                        stability_content = current_content
                        stability_check_count = 0
                        self.logger.debug(f"[{self.req_id}] DOM内容发生变化，重置稳定性计数")
                else:
                    stability_check_count = 0
                    stability_content = ""
                
                await self._check_disconnect(check_client_disconnected, f"稳定性检查 {stability_check_count}")
            
            if not stability_content or not stability_content.strip():
                self.logger.warning(f"[{self.req_id}] DOM稳定性检查后仍无内容")
                return {}
            
            self.logger.info(f"[{self.req_id}] ✅ DOM内容已稳定，包含 {len(stability_content)} 字符")
            
            # 3. 深度内容提取
            final_content = await self._extract_complete_response_content()
            
            if final_content and final_content.strip():
                self.logger.info(f"[{self.req_id}] ✅ 完整性验证成功！提取到 {len(final_content)} 字符的响应内容")
                
                # 分离thinking content和最终回答
                content, reasoning = self._separate_thinking_and_response(final_content)
                
                return {
                    "content": content,
                    "reasoning_content": reasoning,
                    "trigger_reason": trigger_reason
                }
            else:
                self.logger.warning(f"[{self.req_id}] 完整性验证失败，无法从DOM中提取有效内容")
                return {}
                
        except ClientDisconnectedError:
            self.logger.info(f"[{self.req_id}] 客户端在完整性验证过程中断开连接")
            raise
        except Exception as e:
            self.logger.error(f"[{self.req_id}] 完整性验证过程中发生错误: {e}")
            await save_error_snapshot(f"integrity_verification_error_{self.req_id}")
            return {}

    async def get_response_with_integrity_check(self, check_client_disconnected: Callable, prompt_length: int, timeout: Optional[float] = None) -> Dict[str, Any]:
        """获取响应内容 - 增强版本，包含完整性验证和混合响应支持
        
        这是主要的响应获取方法，集成了完整性验证逻辑，能够处理：
        1. 直接获取（正常情况）
        2. 完整性验证恢复（当直接获取失败时）
        3. Thinking content和最终回答的分离处理
        
        Returns:
            Dict[str, Any]: 包含content、reasoning_content、recovery_method等信息的字典
        """
        try:
            # 首先尝试直接获取响应
            direct_content = await self.get_response(check_client_disconnected, prompt_length, timeout)
            
            if direct_content and direct_content.strip():
                # 直接获取成功
                content, reasoning = self._separate_thinking_and_response(direct_content)
                return {
                    "content": content,
                    "reasoning_content": reasoning,
                    "recovery_method": "direct",
                    "trigger_reason": ""
                }
            else:
                # 直接获取失败，启动完整性验证
                self.logger.warning(f"[{self.req_id}] 直接获取响应失败，启动完整性验证...")
                
                verified_data = await self.verify_response_integrity(
                    check_client_disconnected,
                    "直接get_response返回空内容"
                )
                
                if verified_data and verified_data.get("content"):
                    # 完整性验证成功
                    return {
                        "content": verified_data["content"],
                        "reasoning_content": verified_data.get("reasoning_content", ""),
                        "recovery_method": "integrity_verification",
                        "trigger_reason": verified_data.get("trigger_reason", "")
                    }
                else:
                    # 完整性验证也失败
                    return {
                        "content": "",
                        "reasoning_content": "",
                        "recovery_method": "failed",
                        "trigger_reason": "所有方法均失败"
                    }
                    
        except Exception as e:
            self.logger.error(f"[{self.req_id}] 获取响应时发生错误: {e}")
            return {
                "content": "",
                "reasoning_content": "",
                "recovery_method": "error",
                "trigger_reason": f"异常: {str(e)}"
            }

    def _separate_thinking_and_response(self, content: str) -> Tuple[str, str]:
        """分离thinking content和最终回答
        
        Args:
            content: 原始内容，可能包含thinking和回答
            
        Returns:
            Tuple[str, str]: (最终回答, thinking内容)
        """
        if not content:
            return "", ""
        
        # 尝试匹配thinking标记
        thinking_pattern = r'\[THINKING\](.*?)\[/THINKING\]'
        thinking_matches = re.findall(thinking_pattern, content, re.DOTALL)
        
        if thinking_matches:
            # 找到thinking内容，提取最终回答
            reasoning = "\n".join(thinking_matches).strip()
            
            # 移除thinking标记和内容，得到最终回答
            final_content = re.sub(thinking_pattern, '', content, flags=re.DOTALL).strip()
            
            return final_content, reasoning
        else:
            # 没有找到thinking标记，整个作为最终回答
            return content.strip(), ""

    async def _emergency_stability_wait(self, check_client_disconnected: Callable) -> bool:
        """紧急稳定性等待 - 防止假阴性错误
        
        当主方法返回空内容时，等待一段时间观察页面状态变化，
        防止因为DOM更新延迟导致的假阴性判断。
        
        Returns:
            bool: 是否在等待期间检测到内容变化
        """
        from config.settings import EMERGENCY_WAIT_SECONDS
        
        emergency_wait_seconds = EMERGENCY_WAIT_SECONDS
        
        self.logger.info(f"[{self.req_id}] 开始紧急稳定性等待 ({emergency_wait_seconds}s)...")
        
        last_content_length = 0
        stability_detected = False
        retries = 3
        
        for attempt in range(retries):
            try:
                await self._check_disconnect(check_client_disconnected, f"稳定性等待尝试 {attempt + 1}")
                
                # 检查生成状态
                generation_active = await self._check_generation_activity()
                if generation_active:
                    self.logger.info(f"[{self.req_id}] 检测到生成仍在进行中，继续等待...")
                    await asyncio.sleep(1)
                    continue
                
                # 检查DOM内容变化
                current_content = await self._extract_dom_content()
                current_length = len(current_content.strip())
                
                if current_length > last_content_length:
                    self.logger.info(f"[{self.req_id}] 检测到内容增长: {last_content_length} -> {current_length}")
                    last_content_length = current_length
                    stability_detected = True
                elif current_length > 0 and current_length == last_content_length:
                    # 内容稳定且有内容
                    self.logger.info(f"[{self.req_id}] 检测到稳定内容，长度: {current_length}")
                    stability_detected = True
                    break
                
                await asyncio.sleep(1)  # 每秒检查一次
                
            except Exception as e:
                self.logger.warning(f"[{self.req_id}] 稳定性等待第 {attempt + 1} 次尝试出错: {e}")
                continue
        
        if stability_detected:
            self.logger.info(f"[{self.req_id}] ✅ 紧急稳定性等待成功，检测到内容变化")
        else:
            self.logger.warning(f"[{self.req_id}] ❌ 紧急稳定性等待失败，未检测到内容变化")
        
        return stability_detected

    async def _check_generation_activity(self) -> bool:
        """检查生成活动状态
        
        Returns:
            bool: 如果检测到生成仍在进行则返回True
        """
        try:
            # 检查停止按钮（表示正在生成）
            stop_button = self.page.locator('button[aria-label="Stop generating"]')
            if await stop_button.is_visible(timeout=1000):
                return True
            
            # 检查输入框状态（生成时输入框通常为空且提交按钮禁用）
            input_field = self.page.locator(PROMPT_TEXTAREA_SELECTOR)
            submit_button = self.page.locator(SUBMIT_BUTTON_SELECTOR)
            
            input_value = await input_field.input_value(timeout=1000) if await input_field.is_visible(timeout=1000) else ""
            is_submit_disabled = await submit_button.is_disabled(timeout=1000) if await submit_button.is_visible(timeout=1000) else False
            
            # 如果输入框为空且提交按钮禁用，可能表示正在生成
            if not input_value.strip() and is_submit_disabled:
                return True
                
            return False
            
        except Exception:
            # 如果检查失败，假设没有生成活动
            return False

    async def _emergency_stability_wait(self, check_client_disconnected: Callable) -> bool:
        """紧急稳定性等待 - 防止假阴性错误
        
        当主方法返回空内容时，等待一段时间观察页面状态变化，
        防止因为DOM更新延迟导致的假阴性判断。
        
        Returns:
            bool: 是否在等待期间检测到内容变化
        """
        from config import EMERGENCY_WAIT_SECONDS
        
        emergency_wait_seconds = getattr(EMERGENCY_WAIT_SECONDS, 'value', 3)
        
        self.logger.info(f"[{self.req_id}] 开始紧急稳定性等待 ({emergency_wait_seconds}s)...")
        
        last_content_length = 0
        stability_detected = False
        retries = 3
        
        for attempt in range(retries):
            try:
                await self._check_disconnect(check_client_disconnected, f"稳定性等待尝试 {attempt + 1}")
                
                # 检查生成状态
                generation_active = await self._check_generation_activity()
                if generation_active:
                    self.logger.info(f"[{self.req_id}] 检测到生成仍在进行中，继续等待...")
                    await asyncio.sleep(1)
                    continue
                
                # 检查DOM内容变化
                current_content = await self._extract_dom_content()
                current_length = len(current_content.strip())
                
                if current_length > last_content_length:
                    self.logger.info(f"[{self.req_id}] 检测到内容增长: {last_content_length} -> {current_length}")
                    last_content_length = current_length
                    stability_detected = True
                elif current_length > 0 and current_length == last_content_length:
                    # 内容稳定且有内容
                    self.logger.info(f"[{self.req_id}] 检测到稳定内容，长度: {current_length}")
                    stability_detected = True
                    break
                
                await asyncio.sleep(1)  # 每秒检查一次
                
            except Exception as e:
                self.logger.warning(f"[{self.req_id}] 稳定性等待第 {attempt + 1} 次尝试出错: {e}")
                continue
        
        if stability_detected:
            self.logger.info(f"[{self.req_id}] ✅ 紧急稳定性等待成功，检测到内容变化")
        else:
            self.logger.warning(f"[{self.req_id}] ❌ 紧急稳定性等待失败，未检测到内容变化")
        
        return stability_detected

    async def _check_generation_activity(self) -> bool:
        """检查生成活动状态
        
        Returns:
            bool: 如果检测到生成仍在进行则返回True
        """
        try:
            # 检查停止按钮（表示正在生成）
            stop_button = self.page.locator('button[aria-label="Stop generating"]')
            if await stop_button.is_visible(timeout=1000):
                return True
            
            # 检查输入框状态（生成时输入框通常为空且提交按钮禁用）
            input_field = self.page.locator(PROMPT_TEXTAREA_SELECTOR)
            submit_button = self.page.locator(SUBMIT_BUTTON_SELECTOR)
            
            input_value = await input_field.input_value(timeout=1000) if await input_field.is_visible(timeout=1000) else ""
            is_submit_disabled = await submit_button.is_disabled(timeout=1000) if await submit_button.is_visible(timeout=1000) else False
            
            # 如果输入框为空且提交按钮禁用，可能表示正在生成
            if not input_value.strip() and is_submit_disabled:
                return True
                
            return False
            
        except Exception:
            # 如果检查失败，假设没有生成活动
            return False

    async def _extract_dom_content(self) -> str:
        """从DOM中提取原始内容"""
        try:
            # 使用改进的选择器提取内容
            from config.selectors import (
                THINKING_CONTAINER_SELECTOR,
                THINKING_CONTENT_SELECTOR,
                FINAL_RESPONSE_SELECTOR,
                COMPLETE_RESPONSE_CONTAINER_SELECTOR
            )
            
            all_content_parts = []
            
            # 1. 提取Thinking内容（如果存在）
            thinking_containers = self.page.locator(THINKING_CONTAINER_SELECTOR)
            thinking_count = await thinking_containers.count()
            
            for i in range(thinking_count):
                try:
                    container = thinking_containers.nth(i)
                    if await container.is_visible(timeout=1000):
                        content_elem = container.locator(THINKING_CONTENT_SELECTOR)
                        if await content_elem.count() > 0:
                            thinking_text = await content_elem.first.inner_text(timeout=1000)
                            if thinking_text and thinking_text.strip():
                                all_content_parts.append(f"[THINKING]{thinking_text.strip()}[/THINKING]")
                except Exception:
                    continue
            
            # 2. 提取最终响应内容
            response_elements = self.page.locator(FINAL_RESPONSE_SELECTOR)
            response_count = await response_elements.count()
            
            for i in range(response_count):
                try:
                    elem = response_elements.nth(i)
                    if await elem.is_visible(timeout=1000):
                        response_text = await elem.inner_text(timeout=1000)
                        if response_text and response_text.strip():
                            all_content_parts.append(response_text.strip())
                except Exception:
                    continue
            
            # 3. 备用方法：直接从完整容器提取
            if not all_content_parts:
                complete_containers = self.page.locator(COMPLETE_RESPONSE_CONTAINER_SELECTOR)
                container_count = await complete_containers.count()
                
                for i in range(container_count):
                    try:
                        container = complete_containers.nth(i)
                        if await container.is_visible(timeout=1000):
                            # 尝试提取所有文本内容
                            full_text = await container.inner_text(timeout=1000)
                            if full_text and len(full_text.strip()) > 50:  # 过滤掉太短的内容
                                all_content_parts.append(full_text.strip())
                                break
                    except Exception:
                        continue
            
            return "\n".join(all_content_parts) if all_content_parts else ""
            
        except Exception as e:
            self.logger.warning(f"[{self.req_id}] DOM内容提取失败: {e}")
            return ""

    async def get_body_text_only_from_dom(self) -> str:
        """
        专门用于 'Thinking-to-Answer Handover' 协议。
        仅提取最终回答的文本内容，严格排除 Thinking 块。
        """
        try:
            # 使用 evaluate 执行更复杂的 DOM 排除逻辑
            return await self.page.evaluate("""() => {
                const thinkingSelectors = [
                    'ms-thought-accordion',
                    '[data-testid*="thinking"]',
                    '[data-testid*="reasoning"]',
                    '.thinking-process'
                ];
                
                const responseSelectors = [
                    'ms-cmark-node.cmark-node',
                    '.chat-response',
                    '[data-testid*="response"]'
                ];
                
                // 找到最后一个响应容器
                const turns = document.querySelectorAll('ms-chat-turn');
                if (!turns.length) return "";
                const lastTurn = turns[turns.length - 1];
                
                // 在最后一个 turn 中查找响应内容
                // 优先尝试找到明确的 text body
                let candidates = [];
                for (let sel of responseSelectors) {
                    candidates = Array.from(lastTurn.querySelectorAll(sel));
                    if (candidates.length > 0) break;
                }
                
                if (!candidates.length) {
                    // 如果没找到明确的 class，尝试找 chat-turn-container model
                    const container = lastTurn.querySelector('.chat-turn-container.model');
                    if (container) candidates = [container];
                    else candidates = [lastTurn]; // Fallback to whole turn
                }
                
                let fullText = "";
                
                candidates.forEach(el => {
                    // 克隆节点以避免修改页面
                    let clone = el.cloneNode(true);
                    
                    // 移除所有 thinking 相关的元素
                    thinkingSelectors.forEach(ts => {
                        const thoughts = clone.querySelectorAll(ts);
                        thoughts.forEach(t => t.remove());
                    });

                    // [Markdown Preservation] 处理代码块
                    // 查找 pre 元素或带有 code-block 类的元素，将其内容用 ``` 包裹
                    const codeBlocks = clone.querySelectorAll('pre, .code-block, .hljs');
                    codeBlocks.forEach(cb => {
                        // 尝试获取语言标识
                        let lang = '';
                        const classList = cb.className || '';
                        const match = classList.match(/language-(\\w+)/);
                        if (match) lang = match[1];
                        
                        // 如果内部有 code 标签，优先取 code 的内容
                        const codeInner = cb.querySelector('code');
                        const textContent = codeInner ? codeInner.innerText : cb.innerText;
                        
                        // 用 markdown 围栏替换元素内容 (注意：这只改变 Clone)
                        cb.innerText = "\\n```" + lang + "\\n" + textContent + "\\n```\\n";
                    });
                    
                    // 提取剩余文本
                    fullText += clone.innerText + "\\n";
                });
                
                return fullText.trim();
            }""")
        except Exception as e:
            self.logger.warning(f"[{self.req_id}] get_body_text_only_from_dom 失败: {e}")
            return ""

    async def _extract_complete_response_content(self) -> str:
        """提取完整的响应内容，包括Thinking和最终回答"""
        try:
            # 方法1：尝试通过编辑按钮获取（最可靠）
            edit_content = await get_response_via_edit_button(
                self.page, self.req_id, lambda x: None
            )
            if edit_content and edit_content.strip():
                return edit_content.strip()
            
            # 方法2：尝试通过复制按钮获取
            copy_content = await get_response_via_copy_button(
                self.page, self.req_id, lambda x: None
            )
            if copy_content and copy_content.strip():
                return copy_content.strip()
            
            # 方法3：直接DOM提取
            dom_content = await self._extract_dom_content()
            if dom_content and dom_content.strip():
                return dom_content.strip()
            
            return ""
            
        except Exception as e:
            self.logger.error(f"[{self.req_id}] 完整响应内容提取失败: {e}")
            return ""