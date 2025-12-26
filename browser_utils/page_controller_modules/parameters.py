import asyncio
import re
from typing import Any, Callable, Dict, List, Optional

from playwright.async_api import expect as expect_async

from config import (
    CLICK_TIMEOUT_MS,
    DEFAULT_MAX_OUTPUT_TOKENS,
    DEFAULT_STOP_SEQUENCES,
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_P,
    ENABLE_GOOGLE_SEARCH,
    ENABLE_URL_CONTEXT,
    GROUNDING_WITH_GOOGLE_SEARCH_TOGGLE_SELECTOR,
    MAX_OUTPUT_TOKENS_SELECTOR,
    STOP_SEQUENCE_INPUT_SELECTOR,
    TEMPERATURE_INPUT_SELECTOR,
    TOP_P_INPUT_SELECTOR,
    USE_URL_CONTEXT_SELECTOR,
)
from models import ClientDisconnectedError

from .base import BaseController


class ParameterController(BaseController):
    """Handles parameter adjustments (temperature, tokens, etc.)."""

    async def adjust_parameters(
        self,
        request_params: Dict[str, Any],
        page_params_cache: Dict[str, Any],
        params_cache_lock: asyncio.Lock,
        model_id_to_use: Optional[str],
        parsed_model_list: List[Dict[str, Any]],
        check_client_disconnected: Callable,
    ):
        """Adjust all request parameters."""
        await self._check_disconnect(
            check_client_disconnected, "Start Parameter Adjustment"
        )

        # Adjust Temperature
        temp_to_set = request_params.get("temperature", DEFAULT_TEMPERATURE)
        await self._adjust_temperature(
            temp_to_set, page_params_cache, params_cache_lock, check_client_disconnected
        )
        await self._check_disconnect(
            check_client_disconnected, "After Temperature Adjustment"
        )

        # Adjust Max Tokens
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

        # Adjust Stop Sequences
        stop_to_set = request_params.get("stop", DEFAULT_STOP_SEQUENCES)
        await self._adjust_stop_sequences(
            stop_to_set, page_params_cache, params_cache_lock, check_client_disconnected
        )
        await self._check_disconnect(
            check_client_disconnected, "After Stop Sequences Adjustment"
        )

        # Adjust Top P
        top_p_to_set = request_params.get("top_p", DEFAULT_TOP_P)
        await self._adjust_top_p(top_p_to_set, check_client_disconnected)
        await self._check_disconnect(
            check_client_disconnected, "End Parameter Adjustment"
        )

        # Ensure tools panel is expanded
        await self._ensure_tools_panel_expanded(check_client_disconnected)

        # Determine if function calling is active to disable conflicting features
        # Grounding (Google Search) and URL Context MUST be disabled for Function Calling
        is_fc_active = False
        is_fc_enabled_fn = getattr(self, "is_function_calling_enabled", None)
        if is_fc_enabled_fn:
            is_fc_active = await is_fc_enabled_fn(check_client_disconnected)

        # Adjust URL CONTEXT - Force disable if function calling is active
        if is_fc_active:
            await self._adjust_url_context(False, check_client_disconnected)
        elif ENABLE_URL_CONTEXT:
            await self._adjust_url_context(True, check_client_disconnected)
        else:
            self.logger.debug(
                "[Param] URL Context feature disabled, skipping adjustment"
            )

        # Adjust Thinking Budget
        thinking_handler = getattr(self, "_handle_thinking_budget", None)
        if thinking_handler:
            await thinking_handler(
                request_params, model_id_to_use, check_client_disconnected
            )

        # Adjust Google Search Switch
        await self._adjust_google_search(
            request_params, model_id_to_use, check_client_disconnected
        )

    async def _adjust_temperature(
        self,
        temperature: float,
        page_params_cache: dict,
        params_cache_lock: asyncio.Lock,
        check_client_disconnected: Callable,
    ):
        """Adjust temperature parameter."""
        async with params_cache_lock:
            clamped_temp = max(0.0, min(2.0, temperature))
            if clamped_temp != temperature:
                self.logger.warning(
                    f"Temperature {temperature} out of range [0, 2], clamped to {clamped_temp}"
                )

            cached_temp = page_params_cache.get("temperature")
            if cached_temp is not None and abs(cached_temp - clamped_temp) < 0.001:
                self.logger.debug(f"[Param] Temperature: {clamped_temp} (Cached)")
                return

            temp_input_locator = self.page.locator(TEMPERATURE_INPUT_SELECTOR)

            try:
                await expect_async(temp_input_locator).to_be_visible(timeout=5000)
                await self._check_disconnect(
                    check_client_disconnected,
                    "Temperature adjustment - after input visible",
                )

                current_temp_str = await temp_input_locator.input_value(timeout=3000)
                await self._check_disconnect(
                    check_client_disconnected,
                    "Temperature adjustment - after reading value",
                )

                current_temp_float = float(current_temp_str)

                if abs(current_temp_float - clamped_temp) < 0.001:
                    self.logger.debug(
                        f"[Param] Temperature: {clamped_temp} (Matches page)"
                    )
                    page_params_cache["temperature"] = current_temp_float
                else:
                    self.logger.debug(
                        f"[Param] Temperature: {current_temp_float} -> {clamped_temp}"
                    )
                    await temp_input_locator.fill(str(clamped_temp), timeout=5000)
                    await self._check_disconnect(
                        check_client_disconnected, "Temperature adjustment - after fill"
                    )

                    await asyncio.sleep(0.1)
                    new_temp_str = await temp_input_locator.input_value(timeout=3000)
                    new_temp_float = float(new_temp_str)

                    if abs(new_temp_float - clamped_temp) < 0.001:
                        self.logger.debug(
                            f"[Param] Temperature: Updated -> {new_temp_float}"
                        )
                        page_params_cache["temperature"] = new_temp_float
                    else:
                        self.logger.warning(
                            f"Temperature update failed. Page shows: {new_temp_float}, expected: {clamped_temp}."
                        )
                        page_params_cache.pop("temperature", None)
                        from browser_utils.operations import save_error_snapshot

                        await save_error_snapshot(
                            f"temperature_verify_fail_{self.req_id}"
                        )

            except ValueError as ve:
                self.logger.error(
                    f"Error converting temperature to float: {ve}. Clearing cache."
                )
                page_params_cache.pop("temperature", None)
                from browser_utils.operations import save_error_snapshot

                await save_error_snapshot(f"temperature_value_error_{self.req_id}")
            except Exception as pw_err:
                if isinstance(pw_err, asyncio.CancelledError):
                    raise
                self.logger.error(
                    f"Error operating temperature input: {pw_err}. Clearing cache."
                )
                page_params_cache.pop("temperature", None)
                from browser_utils.operations import save_error_snapshot

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
                                f"Model {model_id_to_use} has invalid supported_max_output_tokens: {supported_tokens}"
                            )
                    except (ValueError, TypeError):
                        self.logger.warning(
                            f"Model {model_id_to_use} supported_max_output_tokens parse failed"
                        )

            clamped_max_tokens = max(
                min_val_for_tokens, min(max_val_for_tokens_from_model, max_tokens)
            )
            if clamped_max_tokens != max_tokens:
                self.logger.debug(
                    f"[Param] Max Tokens: {max_tokens} -> {clamped_max_tokens} (Clamped)"
                )

            cached_max_tokens = page_params_cache.get("max_output_tokens")
            if (
                cached_max_tokens is not None
                and cached_max_tokens == clamped_max_tokens
            ):
                self.logger.debug(f"[Param] Max Tokens: {clamped_max_tokens} (Cached)")
                return

            max_tokens_input_locator = self.page.locator(MAX_OUTPUT_TOKENS_SELECTOR)

            try:
                await expect_async(max_tokens_input_locator).to_be_visible(timeout=5000)
                await self._check_disconnect(
                    check_client_disconnected,
                    "Max Tokens adjustment - after input visible",
                )

                current_max_tokens_str = await max_tokens_input_locator.input_value(
                    timeout=3000
                )
                current_max_tokens_int = int(current_max_tokens_str)

                if current_max_tokens_int == clamped_max_tokens:
                    self.logger.debug(
                        f"[Param] Max Tokens: {clamped_max_tokens} (Matches page)"
                    )
                    page_params_cache["max_output_tokens"] = current_max_tokens_int
                else:
                    self.logger.debug(
                        f"[Param] Max Tokens: {current_max_tokens_int} -> {clamped_max_tokens}"
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
                        self.logger.debug(
                            f"[Param] Max Tokens: Updated -> {new_max_tokens_int}"
                        )
                        page_params_cache["max_output_tokens"] = new_max_tokens_int
                    else:
                        self.logger.warning(
                            f"Max Tokens update failed. Page shows: {new_max_tokens_int}, expected: {clamped_max_tokens}."
                        )
                        page_params_cache.pop("max_output_tokens", None)
                        from browser_utils.operations import save_error_snapshot

                        await save_error_snapshot(
                            f"max_tokens_verify_fail_{self.req_id}"
                        )

            except (ValueError, TypeError) as ve:
                self.logger.error(
                    f"Error converting Max Tokens value: {ve}. Clearing cache."
                )
                page_params_cache.pop("max_output_tokens", None)
                from browser_utils.operations import save_error_snapshot

                await save_error_snapshot(f"max_tokens_value_error_{self.req_id}")
            except Exception as e:
                if isinstance(e, asyncio.CancelledError):
                    raise
                self.logger.error(
                    f"Error adjusting Max Output Tokens: {e}. Clearing cache."
                )
                page_params_cache.pop("max_output_tokens", None)
                from browser_utils.operations import save_error_snapshot

                await save_error_snapshot(f"max_tokens_error_{self.req_id}")
                if isinstance(e, ClientDisconnectedError):
                    raise

    async def _get_current_stop_sequences(self) -> set:
        """Read current displayed stop sequences from the page."""
        try:
            remove_btns = self.page.locator(
                'mat-chip button.remove-button[aria-label*="Remove"]'
            )
            count = await remove_btns.count()
            current_stops = set()

            for i in range(count):
                label = await remove_btns.nth(i).get_attribute("aria-label")
                if label and label.startswith("Remove "):
                    text = label[7:].strip()
                    if text:
                        current_stops.add(text)
                else:
                    self.logger.warning(
                        f"Found remove button but aria-label format mismatch: {label}"
                    )

            self.logger.debug(f"[Param] Current page Stop Sequences: {current_stops}")
            return current_stops
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.logger.warning(f"Failed to read current stop sequences: {e}")
            return set()

    async def _adjust_stop_sequences(
        self,
        stop_sequences,
        page_params_cache: dict,
        params_cache_lock: asyncio.Lock,
        check_client_disconnected: Callable,
    ):
        """Adjust stop sequences parameter."""
        async with params_cache_lock:
            self.logger.debug(
                f"[Param] Stop Sequences input: {stop_sequences} (Type: {type(stop_sequences).__name__})"
            )

            # Normalize input to set
            normalized_requested_stops: set = set()
            if stop_sequences is not None:
                if isinstance(stop_sequences, str):
                    if stop_sequences.strip():
                        normalized_requested_stops.add(stop_sequences.strip())
                elif isinstance(stop_sequences, list):
                    for s in stop_sequences:
                        if isinstance(s, str) and s.strip():
                            normalized_requested_stops.add(s.strip())

            # Read current page state
            current_page_stops = await self._get_current_stop_sequences()

            if current_page_stops == normalized_requested_stops:
                self.logger.debug("[Param] Stop Sequences already match page")
                page_params_cache["stop_sequences"] = normalized_requested_stops
                return

            stop_input_locator = self.page.locator(STOP_SEQUENCE_INPUT_SELECTOR)

            # Calculate delta
            to_add = normalized_requested_stops - current_page_stops
            to_remove = current_page_stops - normalized_requested_stops

            try:
                # 1. Remove excess sequences
                if to_remove:
                    for text_to_remove in to_remove:
                        await self._check_disconnect(
                            check_client_disconnected,
                            f"Removing stop: {text_to_remove}",
                        )
                        selector = f'mat-chip button.remove-button[aria-label="Remove {text_to_remove}"]'
                        remove_btn = self.page.locator(selector)

                        if await remove_btn.count() > 0:
                            await remove_btn.first.click(timeout=2000)
                        else:
                            fallback_selector = f'mat-chip button.remove-button[aria-label*="Remove {text_to_remove}"]'
                            fallback_btn = self.page.locator(fallback_selector)
                            if await fallback_btn.count() > 0:
                                await fallback_btn.first.click(timeout=2000)

                # 2. Add missing sequences
                if to_add:
                    await expect_async(stop_input_locator).to_be_visible(timeout=5000)
                    for seq in to_add:
                        await self._check_disconnect(
                            check_client_disconnected, f"Adding stop: {seq}"
                        )
                        await stop_input_locator.fill(seq, timeout=3000)
                        await stop_input_locator.press("Enter", timeout=3000)
                        await asyncio.sleep(0.2)

                # 3. Verify final state
                final_page_stops = await self._get_current_stop_sequences()
                if final_page_stops == normalized_requested_stops:
                    page_params_cache["stop_sequences"] = normalized_requested_stops
                    self.logger.debug("[Param] Stop Sequences updated successfully")
                else:
                    self.logger.warning(
                        f"Stop Sequences verification failed. "
                        f"Expected: {normalized_requested_stops}, Actual: {final_page_stops}"
                    )
                    page_params_cache["stop_sequences"] = final_page_stops
                    from browser_utils.operations import save_error_snapshot

                    await save_error_snapshot(
                        f"stop_sequence_verify_fail_{self.req_id}"
                    )

            except Exception as e:
                if isinstance(e, asyncio.CancelledError):
                    raise
                self.logger.error(f"Stop Sequences error: {e}")
                page_params_cache.pop("stop_sequences", None)
                from browser_utils.operations import save_error_snapshot

                await save_error_snapshot(f"stop_sequence_error_{self.req_id}")
                if isinstance(e, ClientDisconnectedError):
                    raise

    async def _adjust_top_p(self, top_p: float, check_client_disconnected: Callable):
        """Adjust Top P parameter."""
        clamped_top_p = max(0.0, min(1.0, top_p))

        if abs(clamped_top_p - top_p) > 1e-9:
            self.logger.warning(
                f"Top P {top_p} out of range [0, 1], clamped to {clamped_top_p}"
            )

        top_p_input_locator = self.page.locator(TOP_P_INPUT_SELECTOR)
        try:
            await expect_async(top_p_input_locator).to_be_visible(timeout=5000)
            await self._check_disconnect(
                check_client_disconnected, "Top P adjustment - after input visible"
            )

            current_top_p_str = await top_p_input_locator.input_value(timeout=3000)
            current_top_p_float = float(current_top_p_str)

            if abs(current_top_p_float - clamped_top_p) > 1e-9:
                self.logger.debug(
                    f"[Param] Top P: {current_top_p_float} -> {clamped_top_p}"
                )
                await top_p_input_locator.fill(str(clamped_top_p), timeout=5000)
                await self._check_disconnect(
                    check_client_disconnected, "Top P adjustment - after fill"
                )

                await asyncio.sleep(0.1)
                new_top_p_str = await top_p_input_locator.input_value(timeout=3000)
                new_top_p_float = float(new_top_p_str)

                if abs(new_top_p_float - clamped_top_p) <= 1e-9:
                    self.logger.debug(f"[Param] Top P: Updated -> {new_top_p_float}")
                else:
                    self.logger.warning(
                        f"Top P update failed. Page shows: {new_top_p_float}, expected: {clamped_top_p}."
                    )
                    from browser_utils.operations import save_error_snapshot

                    await save_error_snapshot(f"top_p_verify_fail_{self.req_id}")
            else:
                self.logger.debug(f"[Param] Top P: {clamped_top_p} (Matches page)")

        except (ValueError, TypeError) as ve:
            self.logger.error(f"Error converting Top P value: {ve}")
            from browser_utils.operations import save_error_snapshot

            await save_error_snapshot(f"top_p_value_error_{self.req_id}")
        except Exception as e:
            if isinstance(e, asyncio.CancelledError):
                raise
            self.logger.error(f"Error adjusting Top P: {e}")
            from browser_utils.operations import save_error_snapshot

            await save_error_snapshot(f"top_p_error_{self.req_id}")
            if isinstance(e, ClientDisconnectedError):
                raise

    async def _ensure_tools_panel_expanded(self, check_client_disconnected: Callable):
        """Ensure tools panel is expanded."""
        self.logger.debug("[Param] Checking tools panel state...")
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
                self.logger.debug("[Param] Tools panel not expanded, expanding...")
                await collapse_tools_locator.click(timeout=CLICK_TIMEOUT_MS)
                await self._check_disconnect(
                    check_client_disconnected, "After expanding tools panel"
                )
                await expect_async(grandparent_locator).to_have_class(
                    re.compile(r".*expanded.*"), timeout=5000
                )
                self.logger.debug("[Param] Tools panel successfully expanded")
            else:
                self.logger.debug("[Param] Tools panel already expanded")
        except Exception as e:
            if isinstance(e, asyncio.CancelledError):
                raise
            self.logger.error(f"Error expanding tools panel: {e}")
            if isinstance(e, ClientDisconnectedError):
                raise

    async def _adjust_url_context(
        self, enable: bool, check_client_disconnected: Callable
    ):
        """Enable or disable URL Context."""
        action = "enabling" if enable else "disabling"
        try:
            self.logger.info(f"Checking and {action} URL Context...")
            use_url_content_selector = self.page.locator(USE_URL_CONTEXT_SELECTOR)

            # Use a shorter timeout to check visibility
            if await use_url_content_selector.count() == 0:
                self.logger.debug(
                    f"[Param] URL Context toggle not found, skipping {action}"
                )
                return

            await expect_async(use_url_content_selector).to_be_visible(timeout=2000)

            is_checked = await use_url_content_selector.get_attribute("aria-checked")
            is_currently_enabled = is_checked == "true"

            if is_currently_enabled != enable:
                self.logger.info(
                    f"URL Context {'not enabled' if enable else 'enabled'}, {action}..."
                )
                await use_url_content_selector.click(timeout=CLICK_TIMEOUT_MS)
                await self._check_disconnect(
                    check_client_disconnected, f"After {action} URL Context"
                )
                self.logger.info(f"URL Context {action[:-3]}ed.")
            else:
                self.logger.info(
                    f"URL Context already {'enabled' if enable else 'disabled'}."
                )
        except Exception as e:
            if isinstance(e, asyncio.CancelledError):
                raise
            self.logger.error(f"Error operating URL Context: {e}")
            if isinstance(e, ClientDisconnectedError):
                raise

    async def _open_url_content(self, check_client_disconnected: Callable):
        """Enable URL Context (legacy wrapper)."""
        await self._adjust_url_context(True, check_client_disconnected)

    def _should_enable_google_search(self, request_params: Dict[str, Any]) -> bool:
        """Determine if Google Search should be enabled."""
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
            self.logger.debug(
                f"[Param] Google Search tool detected: {has_google_search_tool}"
            )
            return has_google_search_tool
        else:
            self.logger.debug(
                f"[Param] Google Search using default: {ENABLE_GOOGLE_SEARCH}"
            )
            return ENABLE_GOOGLE_SEARCH

    def _supports_google_search(self, model_id: Optional[str]) -> bool:
        """Check if model supports Google Search."""
        if not model_id:
            return True
        model_lower = model_id.lower()
        if "gemini-2.0" in model_lower or "gemini2.0" in model_lower:
            return False
        return True

    async def _adjust_google_search(
        self,
        request_params: Dict[str, Any],
        model_id: Optional[str],
        check_client_disconnected: Callable,
    ):
        """Adjust Google Search toggle."""
        if not self._supports_google_search(model_id):
            self.logger.debug(
                "[Param] Google Search: Model does not support this feature, skipping"
            )
            return

        should_enable_search = self._should_enable_google_search(request_params)
        desired_state = "On" if should_enable_search else "Off"

        toggle_selector = GROUNDING_WITH_GOOGLE_SEARCH_TOGGLE_SELECTOR

        try:
            toggle_locator = self.page.locator(toggle_selector)
            await expect_async(toggle_locator).to_be_visible(timeout=5000)
            await self._check_disconnect(
                check_client_disconnected, "Google Search toggle visible"
            )

            is_checked_str = await toggle_locator.get_attribute("aria-checked")
            is_currently_checked = is_checked_str == "true"

            if should_enable_search == is_currently_checked:
                self.logger.debug(
                    f"[Param] Google Search: {desired_state} (Matches page)"
                )
                return

            self.logger.debug(
                f"[Param] Google Search: {'On' if is_currently_checked else 'Off'} -> {desired_state}"
            )
            try:
                await toggle_locator.scroll_into_view_if_needed()
            except asyncio.CancelledError:
                raise
            except Exception:
                pass
            await toggle_locator.click(timeout=CLICK_TIMEOUT_MS)
            await self._check_disconnect(
                check_client_disconnected, "Google Search toggle clicked"
            )
            await asyncio.sleep(0.5)
            new_state = await toggle_locator.get_attribute("aria-checked")
            if (new_state == "true") == should_enable_search:
                self.logger.debug(f"[Param] Google Search: {desired_state} (Updated)")
            else:
                self.logger.warning(
                    f"Google Search toggle failed. Expected: {desired_state}, Actual: {'On' if new_state == 'true' else 'Off'}"
                )

        except Exception as e:
            if isinstance(e, asyncio.CancelledError):
                raise
            if isinstance(e, AssertionError) and "visible" in str(e).lower():
                self.logger.debug(
                    "[Param] Google Search: Model does not support this feature, skipping"
                )
            else:
                self.logger.error(f"Google Search toggle error: {e}")
            if isinstance(e, ClientDisconnectedError):
                raise
