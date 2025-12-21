import asyncio
from enum import Enum, auto
from typing import Any, Callable, Dict, Optional

from playwright.async_api import TimeoutError
from playwright.async_api import expect as expect_async

from browser_utils.operations import save_error_snapshot
from browser_utils.thinking_normalizer import (
    format_directive_log,
    normalize_reasoning_effort_with_stream_check,
)
from config import (
    CLICK_TIMEOUT_MS,
    DEFAULT_THINKING_LEVEL_FLASH,
    DEFAULT_THINKING_LEVEL_PRO,
    ENABLE_THINKING_MODE_TOGGLE_SELECTOR,
    SET_THINKING_BUDGET_TOGGLE_SELECTOR,
    THINKING_BUDGET_INPUT_SELECTOR,
    THINKING_BUDGET_TOGGLE_OLD_ROOT_SELECTOR,
    THINKING_BUDGET_TOGGLE_PARENT_SELECTOR,
    THINKING_LEVEL_OPTION_HIGH_SELECTOR,
    THINKING_LEVEL_OPTION_LOW_SELECTOR,
    THINKING_LEVEL_OPTION_MEDIUM_SELECTOR,
    THINKING_LEVEL_OPTION_MINIMAL_SELECTOR,
    THINKING_LEVEL_SELECT_SELECTOR,
    THINKING_MODE_TOGGLE_OLD_ROOT_SELECTOR,
    THINKING_MODE_TOGGLE_PARENT_SELECTOR,
)
from models import ClientDisconnectedError

from .base import BaseController


class ThinkingCategory(Enum):
    """Model thinking capability categories."""

    NON_THINKING = auto()  # No thinking UI at all (gemini-2.0-*, gemini-1.5-*)
    THINKING_FLASH = auto()  # Toggleable thinking mode + budget (gemini-2.5-flash*)
    THINKING_PRO = auto()  # Always-on thinking, budget toggle/slider (gemini-2.5-pro*)
    THINKING_LEVEL = auto()  # 2-level dropdown only (gemini-3-pro*)
    THINKING_LEVEL_FLASH = auto()  # 4-level dropdown (gemini-3-flash*)


class ThinkingController(BaseController):
    """Handles thinking mode and budget logic."""

    async def _handle_thinking_budget(
        self,
        request_params: Dict[str, Any],
        page_params_cache: Dict[str, Any],
        params_cache_lock: asyncio.Lock,
        model_id_to_use: Optional[str],
        check_client_disconnected: Callable,
        is_streaming: bool = True,
    ):
        """Handle adjustments for thinking mode and budget."""
        reasoning_effort = request_params.get("reasoning_effort")

        async with params_cache_lock:
            if (
                "reasoning_effort" in page_params_cache
                and page_params_cache["reasoning_effort"] == reasoning_effort
            ):
                self.logger.debug(
                    f"[Thinking] Reasoning effort {reasoning_effort} matches cache, skipping"
                )
                return

            # Determine processing logic based on model category
            category = self._get_thinking_category(model_id_to_use)
            if category == ThinkingCategory.NON_THINKING:
                self.logger.debug(
                    "[Thinking] This model does not support thinking mode, skipping config"
                )
                page_params_cache["reasoning_effort"] = reasoning_effort
                return

            directive = normalize_reasoning_effort_with_stream_check(
                reasoning_effort, is_streaming
            )
            self.logger.debug(
                f"[Thinking] Directive: {format_directive_log(directive)}"
            )

            uses_level = (
                category
                in (
                    ThinkingCategory.THINKING_LEVEL,
                    ThinkingCategory.THINKING_LEVEL_FLASH,
                )
                and await self._has_thinking_dropdown()
            )

            def _should_enable_from_raw(rv: Any) -> bool:
                try:
                    if isinstance(rv, str):
                        rs = rv.strip().lower()
                        if rs in ["high", "medium", "low", "minimal", "-1"]:
                            return True
                        if rs == "none":
                            return False
                        v = int(rs)
                        return v > 0
                    if isinstance(rv, int):
                        return rv > 0 or rv == -1
                except Exception:
                    return False
                return False

            desired_enabled = directive.thinking_enabled or _should_enable_from_raw(
                reasoning_effort
            )

            # Special logic: for models using levels (Gemini 3 Pro), if reasoning_effort is not specified,
            # we default to enabled (or at least check and apply default level)
            if reasoning_effort is None and uses_level:
                desired_enabled = True

            has_main_toggle = category == ThinkingCategory.THINKING_FLASH
            if has_main_toggle:
                self.logger.info(
                    f"Setting main thinking toggle to: {'ON' if desired_enabled else 'OFF'}"
                )
                await self._control_thinking_mode_toggle(
                    should_be_enabled=desired_enabled,
                    check_client_disconnected=check_client_disconnected,
                )
            else:
                self.logger.info(
                    "This model has no main thinking toggle, skipping toggle setting."
                )

            if not desired_enabled:
                # Skip models without budget toggle
                if category in (
                    ThinkingCategory.THINKING_LEVEL,
                    ThinkingCategory.THINKING_LEVEL_FLASH,
                ):
                    page_params_cache["reasoning_effort"] = reasoning_effort
                    return
                # Flash/Flash Lite models: after turning off main thinking toggle, budget toggle is hidden
                if has_main_toggle:
                    self.logger.info(
                        "Flash model main thinking toggle turned off, skipping budget toggle operation (hidden)"
                    )
                    page_params_cache["reasoning_effort"] = reasoning_effort
                    return
                # If thinking is disabled, ensure budget toggle is off (legacy UI compatibility)
                await self._control_thinking_budget_toggle(
                    should_be_checked=False,
                    check_client_disconnected=check_client_disconnected,
                )
                page_params_cache["reasoning_effort"] = reasoning_effort
                return

            # 2) Thinking enabled: Set level or budget based on model type
            if uses_level:
                rv = reasoning_effort
                level_to_set = None
                is_flash_4_level = category == ThinkingCategory.THINKING_LEVEL_FLASH

                if isinstance(rv, str):
                    rs = rv.strip().lower()
                    if is_flash_4_level:
                        # Gemini 3 Flash: 4 levels (minimal, low, medium, high)
                        if rs in ["minimal", "low", "medium", "high"]:
                            level_to_set = rs
                        elif rs in ["none", "-1"]:
                            level_to_set = "high"
                        else:
                            try:
                                v = int(rs)
                                if v >= 16000:
                                    level_to_set = "high"
                                elif v >= 8000:
                                    level_to_set = "medium"
                                elif v >= 1024:
                                    level_to_set = "low"
                                else:
                                    level_to_set = "minimal"
                            except Exception:
                                level_to_set = None
                    else:
                        # Gemini 3 Pro: 2 levels (low, high)
                        if rs == "low" or rs == "minimal":
                            level_to_set = "low"
                        elif rs in ["high", "medium", "none", "-1"]:
                            level_to_set = "high"
                        else:
                            try:
                                v = int(rs)
                                level_to_set = "high" if v >= 8000 else "low"
                            except Exception:
                                level_to_set = None
                elif isinstance(rv, int):
                    if is_flash_4_level:
                        # Gemini 3 Flash: 4 levels
                        if rv >= 16000 or rv == -1:
                            level_to_set = "high"
                        elif rv >= 8000:
                            level_to_set = "medium"
                        elif rv >= 1024:
                            level_to_set = "low"
                        else:
                            level_to_set = "minimal"
                    else:
                        # Gemini 3 Pro: 2 levels
                        level_to_set = "high" if rv >= 8000 or rv == -1 else "low"

                if level_to_set is None and rv is None:
                    # Use model-specific default
                    level_to_set = (
                        DEFAULT_THINKING_LEVEL_FLASH
                        if is_flash_4_level
                        else DEFAULT_THINKING_LEVEL_PRO
                    )
                    # Ensure Pro only gets valid levels (high/low)
                    if not is_flash_4_level and level_to_set not in ["high", "low"]:
                        level_to_set = (
                            "high" if level_to_set in ["high", "medium"] else "low"
                        )

                if level_to_set is None:
                    self.logger.info(
                        "Unable to parse reasoning level, keeping current level."
                    )
                else:
                    await self._set_thinking_level(
                        level_to_set, check_client_disconnected
                    )
                page_params_cache["reasoning_effort"] = reasoning_effort
                return

            # Fallback path
            if desired_enabled and not directive.thinking_enabled:
                self.logger.info("Attempting to turn off main thinking toggle...")
                success = await self._control_thinking_mode_toggle(
                    should_be_enabled=False,
                    check_client_disconnected=check_client_disconnected,
                )

                if not success:
                    self.logger.warning(
                        "Main thinking toggle unavailable, using fallback: Setting budget to 0"
                    )
                    await self._control_thinking_budget_toggle(
                        should_be_checked=True,
                        check_client_disconnected=check_client_disconnected,
                    )
                    await self._set_thinking_budget_value(0, check_client_disconnected)
                page_params_cache["reasoning_effort"] = reasoning_effort
                return

            # Scenario 2 & 3: Enable thinking mode
            if not has_main_toggle:
                self.logger.info("Enabling main thinking toggle...")
                await self._control_thinking_mode_toggle(
                    should_be_enabled=True,
                    check_client_disconnected=check_client_disconnected,
                )

            # Scenario 2: Enable thinking, no budget limit
            if not directive.budget_enabled:
                self.logger.info("Disabling manual budget limit...")
                await self._control_thinking_budget_toggle(
                    should_be_checked=False,
                    check_client_disconnected=check_client_disconnected,
                )

            # Scenario 3: Enable thinking, with budget limit
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
                    f"Enabling manual budget limit and setting budget value: {value_to_set} tokens"
                )
                await self._control_thinking_budget_toggle(
                    should_be_checked=True,
                    check_client_disconnected=check_client_disconnected,
                )
                await self._set_thinking_budget_value(
                    value_to_set, check_client_disconnected
                )

            page_params_cache["reasoning_effort"] = reasoning_effort

    async def _has_thinking_dropdown(self) -> bool:
        try:
            locator = self.page.locator(THINKING_LEVEL_SELECT_SELECTOR)
            count = await locator.count()
            if count == 0:
                return False
            try:
                await expect_async(locator.first).to_be_visible(timeout=2000)
                return True
            except asyncio.CancelledError:
                raise
            except Exception:
                return True
        except asyncio.CancelledError:
            raise
        except Exception:
            return False

    def _get_thinking_category(self, model_id: Optional[str]) -> ThinkingCategory:
        """Return thinking category based on model ID."""
        if not model_id:
            return ThinkingCategory.NON_THINKING

        mid = model_id.lower()

        if "gemini-3" in mid and "flash" in mid:
            return ThinkingCategory.THINKING_LEVEL_FLASH

        if "gemini-3" in mid and "pro" in mid:
            return ThinkingCategory.THINKING_LEVEL

        if "gemini-2.5-pro" in mid:
            return ThinkingCategory.THINKING_PRO

        if "gemini-2.5-flash" in mid:
            return ThinkingCategory.THINKING_FLASH

        if mid == "gemini-flash-latest" or mid == "gemini-flash-lite-latest":
            return ThinkingCategory.THINKING_FLASH

        return ThinkingCategory.NON_THINKING

    async def _set_thinking_level(
        self, level: str, check_client_disconnected: Callable
    ):
        """Set thinking level in the dropdown."""
        level_lower = level.lower()
        if level_lower == "high":
            target_option_selector = THINKING_LEVEL_OPTION_HIGH_SELECTOR
        elif level_lower == "medium":
            target_option_selector = THINKING_LEVEL_OPTION_MEDIUM_SELECTOR
        elif level_lower == "low":
            target_option_selector = THINKING_LEVEL_OPTION_LOW_SELECTOR
        elif level_lower == "minimal":
            target_option_selector = THINKING_LEVEL_OPTION_MINIMAL_SELECTOR
        else:
            target_option_selector = THINKING_LEVEL_OPTION_HIGH_SELECTOR
        try:
            trigger = self.page.locator(THINKING_LEVEL_SELECT_SELECTOR)
            await expect_async(trigger).to_be_visible(timeout=5000)
            await trigger.scroll_into_view_if_needed()
            await trigger.click(timeout=CLICK_TIMEOUT_MS)
            await self._check_disconnect(
                check_client_disconnected, "After opening Thinking Level"
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
            except asyncio.CancelledError:
                raise
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
                self.logger.info(f"Thinking Level successfully set to {level}")
            else:
                self.logger.warning(
                    f"Thinking Level verification failed, page value: {value_text}, expected: {level}"
                )
        except Exception as e:
            if isinstance(e, asyncio.CancelledError):
                raise
            self.logger.error(f"Error setting Thinking Level: {e}")
            if isinstance(e, ClientDisconnectedError):
                raise

    async def _set_thinking_budget_value(
        self, token_budget: int, check_client_disconnected: Callable
    ):
        """Set specific thinking budget value."""
        self.logger.info(f"Setting thinking budget value: {token_budget} tokens")

        budget_input_locator = self.page.locator(THINKING_BUDGET_INPUT_SELECTOR)

        try:
            await expect_async(budget_input_locator).to_be_visible(timeout=5000)
            await self._check_disconnect(
                check_client_disconnected,
                "Thinking budget adjustment - after input visible",
            )

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
            except asyncio.CancelledError:
                raise
            except Exception:
                pass

            self.logger.info(f"Setting thinking budget to: {adjusted_budget}")
            await budget_input_locator.fill(str(adjusted_budget), timeout=5000)
            await self._check_disconnect(
                check_client_disconnected, "Thinking budget adjustment - after fill"
            )

            # Verify
            try:
                await expect_async(budget_input_locator).to_have_value(
                    str(adjusted_budget), timeout=3000
                )
                self.logger.info(
                    f"Thinking budget successfully updated to: {adjusted_budget}"
                )
            except Exception:
                new_value_str = await budget_input_locator.input_value(timeout=3000)
                try:
                    new_value_int = int(new_value_str)
                except Exception:
                    new_value_int = -1
                if new_value_int == adjusted_budget:
                    self.logger.info(
                        f"Thinking budget successfully updated to: {new_value_str}"
                    )
                else:
                    # Fallback: if page max is less than requested, try filling with page max
                    try:
                        page_max_str = await budget_input_locator.get_attribute("max")
                        page_max_val = (
                            int(page_max_str) if page_max_str is not None else None
                        )
                    except Exception:
                        page_max_val = None
                    if page_max_val is not None and page_max_val < adjusted_budget:
                        self.logger.warning(
                            f"Page max budget is {page_max_val}, requested budget {adjusted_budget} adjusted to {page_max_val}"
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
                        except asyncio.CancelledError:
                            raise
                        except Exception:
                            pass
                        await budget_input_locator.fill(str(page_max_val), timeout=5000)
                        try:
                            await expect_async(budget_input_locator).to_have_value(
                                str(page_max_val), timeout=2000
                            )
                        except asyncio.CancelledError:
                            raise
                        except Exception:
                            pass
                    else:
                        self.logger.warning(
                            f"Thinking budget verification failed after update. Page shows: {new_value_str}, expected: {adjusted_budget}"
                        )

        except Exception as e:
            if isinstance(e, asyncio.CancelledError):
                raise
            self.logger.error(f"Error adjusting thinking budget: {e}")
            if isinstance(e, ClientDisconnectedError):
                raise

    async def _control_thinking_mode_toggle(
        self, should_be_enabled: bool, check_client_disconnected: Callable
    ) -> bool:
        """Control main thinking toggle to enable/disable thinking mode."""
        toggle_selector = ENABLE_THINKING_MODE_TOGGLE_SELECTOR
        self.logger.info(
            f"Controlling main thinking toggle, expected state: {'ON' if should_be_enabled else 'OFF'}..."
        )

        try:
            toggle_locator = self.page.locator(toggle_selector)

            element_count = await toggle_locator.count()
            if element_count == 0:
                if not should_be_enabled:
                    self.logger.info(
                        "Main thinking toggle not found (unsupported), skipping disable."
                    )
                    return True
                else:
                    self.logger.warning(
                        "Main thinking toggle not found (unsupported), cannot enable."
                    )
                    return False

            await expect_async(toggle_locator).to_be_visible(timeout=5000)
            try:
                await toggle_locator.scroll_into_view_if_needed()
            except asyncio.CancelledError:
                raise
            except Exception:
                pass
            await self._check_disconnect(
                check_client_disconnected, "Main thinking toggle - after visible"
            )

            is_checked_str = await toggle_locator.get_attribute("aria-checked")
            current_state_is_enabled = is_checked_str == "true"
            self.logger.info(
                f"Main thinking toggle current state: {is_checked_str} (Enabled: {current_state_is_enabled})"
            )

            if current_state_is_enabled != should_be_enabled:
                action = "enable" if should_be_enabled else "disable"
                self.logger.info(
                    f"Main thinking toggle mismatch, clicking to {action} thinking mode..."
                )

                try:
                    await toggle_locator.click(timeout=CLICK_TIMEOUT_MS)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    try:
                        alt_toggle = self.page.locator(
                            THINKING_MODE_TOGGLE_PARENT_SELECTOR
                        )
                        if await alt_toggle.count() > 0:
                            await alt_toggle.click(timeout=CLICK_TIMEOUT_MS)
                        else:
                            root = self.page.locator(
                                THINKING_MODE_TOGGLE_OLD_ROOT_SELECTOR
                            )
                            label = root.locator("label.mdc-label")
                            await expect_async(label).to_be_visible(timeout=2000)
                            await label.click(timeout=CLICK_TIMEOUT_MS)
                    except Exception:
                        raise
                await self._check_disconnect(
                    check_client_disconnected,
                    f"Main thinking toggle - after click {action}",
                )

                new_state_str = await toggle_locator.get_attribute("aria-checked")
                new_state_is_enabled = new_state_str == "true"

                if new_state_is_enabled == should_be_enabled:
                    self.logger.info(
                        f"Main thinking toggle successfully {action}d. New state: {new_state_str}"
                    )
                    return True
                else:
                    self.logger.warning(
                        f"Main thinking toggle {action} verification failed. Expected: {should_be_enabled}, Actual: {new_state_str}"
                    )
                    return False
            else:
                self.logger.info("Main thinking toggle already in expected state.")
                return True

        except TimeoutError:
            self.logger.warning(
                "Main thinking toggle element not found or invisible (unsupported)"
            )
            return False
        except Exception as e:
            if isinstance(e, asyncio.CancelledError):
                raise
            self.logger.error(f"Error operating main thinking toggle: {e}")
            await save_error_snapshot(f"thinking_mode_toggle_error_{self.req_id}")
            if isinstance(e, ClientDisconnectedError):
                raise
            return False

    async def _control_thinking_budget_toggle(
        self, should_be_checked: bool, check_client_disconnected: Callable
    ):
        """Control 'Thinking Budget' toggle state based on should_be_checked."""
        toggle_selector = SET_THINKING_BUDGET_TOGGLE_SELECTOR
        self.logger.info(
            f"Controlling 'Thinking Budget' toggle, expected state: {'Checked' if should_be_checked else 'Unchecked'}..."
        )

        try:
            toggle_locator = self.page.locator(toggle_selector)

            element_count = await toggle_locator.count()
            if element_count == 0:
                if not should_be_checked:
                    self.logger.info(
                        "Thinking budget toggle not found, skipping disable."
                    )
                    return
                else:
                    self.logger.warning(
                        "Thinking budget toggle not found, cannot enable."
                    )
                    return

            await expect_async(toggle_locator).to_be_visible(timeout=5000)
            try:
                await toggle_locator.scroll_into_view_if_needed()
            except asyncio.CancelledError:
                raise
            except Exception:
                pass
            await self._check_disconnect(
                check_client_disconnected, "Thinking budget toggle - after visible"
            )

            is_checked_str = await toggle_locator.get_attribute("aria-checked")
            current_state_is_checked = is_checked_str == "true"
            self.logger.info(
                f"Thinking budget toggle current 'aria-checked': {is_checked_str} (Checked: {current_state_is_checked})"
            )

            if current_state_is_checked != should_be_checked:
                action = "enable" if should_be_checked else "disable"
                self.logger.info(
                    f"Thinking budget toggle mismatch, clicking to {action}..."
                )
                try:
                    await toggle_locator.click(timeout=CLICK_TIMEOUT_MS)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    try:
                        alt_toggle = self.page.locator(
                            THINKING_BUDGET_TOGGLE_PARENT_SELECTOR
                        )
                        if await alt_toggle.count() > 0:
                            await alt_toggle.click(timeout=CLICK_TIMEOUT_MS)
                        else:
                            root = self.page.locator(
                                THINKING_BUDGET_TOGGLE_OLD_ROOT_SELECTOR
                            )
                            label = root.locator("label.mdc-label")
                            await expect_async(label).to_be_visible(timeout=2000)
                            await label.click(timeout=CLICK_TIMEOUT_MS)
                    except Exception:
                        raise
                await self._check_disconnect(
                    check_client_disconnected,
                    f"Thinking budget toggle - after click {action}",
                )

                await asyncio.sleep(0.5)
                new_state_str = await toggle_locator.get_attribute("aria-checked")
                new_state_is_checked = new_state_str == "true"

                if new_state_is_checked == should_be_checked:
                    self.logger.info(
                        f"'Thinking Budget' toggle successfully {action}d. New state: {new_state_str}"
                    )
                else:
                    self.logger.warning(
                        f"'Thinking Budget' toggle verification failed after {action}. Expected: {should_be_checked}, Actual: {new_state_str}"
                    )
            else:
                self.logger.info("'Thinking Budget' toggle already in expected state.")

        except Exception as e:
            if isinstance(e, asyncio.CancelledError):
                raise
            self.logger.error(f"Error operating 'Thinking Budget toggle': {e}")
            if isinstance(e, ClientDisconnectedError):
                raise
