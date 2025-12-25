"""
Function Calling Controller Mixin

Provides browser automation for AI Studio's native function calling UI.
Handles enabling/disabling function calling toggle and managing function declarations.

Includes caching mechanism to skip redundant UI operations when same tools are used.
"""

import asyncio
import json
import time
from typing import Callable, List, Optional

from logging_utils.fc_debug import FCModule, get_fc_logger
from playwright.async_api import expect as expect_async

from config import (
    CLICK_TIMEOUT_MS,
    FUNCTION_CALLING_CONTAINER_SELECTOR,
    FUNCTION_CALLING_TOGGLE_SELECTOR,
    FUNCTION_DECLARATIONS_CODE_EDITOR_TAB_SELECTOR,
    FUNCTION_DECLARATIONS_CLOSE_BUTTON_SELECTOR,
    FUNCTION_DECLARATIONS_DIALOG_SELECTOR,
    FUNCTION_DECLARATIONS_EDIT_BUTTON_SELECTOR,
    FUNCTION_DECLARATIONS_RESET_BUTTON_SELECTOR,
    FUNCTION_DECLARATIONS_SAVE_BUTTON_SELECTOR,
    FUNCTION_DECLARATIONS_TEXTAREA_SELECTOR,
    SELECTOR_VISIBILITY_TIMEOUT_MS,
)
from config.settings import FUNCTION_CALLING_DEBUG, FUNCTION_CALLING_UI_TIMEOUT
from models import ClientDisconnectedError

from .base import BaseController

# FC debug logger for UI automation events
fc_logger = get_fc_logger()


class FunctionCallingController(BaseController):
    """
    Controller mixin for function calling UI automation.

    Provides methods to:
    - Check if function calling is enabled
    - Enable/disable function calling toggle
    - Open function declarations dialog
    - Input function declarations JSON
    - Save and close dialog

    Integrates with FunctionCallingCache to skip redundant UI operations
    when the same tools are used in subsequent requests.
    """

    # Instance-level cache for quick toggle state lookup
    _fc_toggle_cached: Optional[bool] = None

    def _get_fc_cache(self):
        """Get the function calling cache instance (lazy import to avoid circular deps)."""
        try:
            from api_utils.utils_ext.function_calling_cache import FunctionCallingCache

            return FunctionCallingCache.get_instance(self.logger)
        except ImportError:
            return None

    def invalidate_fc_cache(self, reason: str = "manual") -> None:
        """
        Invalidate the function calling cache.

        Call this on model switch, new chat creation, or explicit clear request.

        Args:
            reason: Reason for invalidation (for logging).
        """
        self._fc_toggle_cached = None
        cache = self._get_fc_cache()
        if cache:
            cache.invalidate(reason=reason, req_id=self.req_id)

    async def is_function_calling_enabled(
        self,
        check_client_disconnected: Callable,
        use_cache: bool = True,
    ) -> bool:
        """
        Check if function calling toggle is currently enabled.

        Args:
            check_client_disconnected: Callback to check client connection.
            use_cache: If True, check instance cache first (default True).

        Returns:
            True if function calling is enabled, False otherwise.
        """
        # Check instance-level cache first for fast path
        if use_cache and self._fc_toggle_cached is not None:
            if FUNCTION_CALLING_DEBUG:
                self.logger.debug(
                    f"[{self.req_id}] [FC:Cache] Toggle state from instance cache: "
                    f"{'enabled' if self._fc_toggle_cached else 'disabled'}"
                )
            return self._fc_toggle_cached

        await self._check_disconnect(
            check_client_disconnected, "Function calling - check enabled"
        )

        start_time = time.perf_counter()

        try:
            toggle_locator = self.page.locator(FUNCTION_CALLING_TOGGLE_SELECTOR)

            # Wait for toggle to be visible with a short timeout
            try:
                await expect_async(toggle_locator.first).to_be_visible(
                    timeout=FUNCTION_CALLING_UI_TIMEOUT
                )
            except Exception:
                if FUNCTION_CALLING_DEBUG:
                    self.logger.debug(
                        f"[{self.req_id}] [FC:UI] Toggle not visible, assuming disabled"
                    )
                self._fc_toggle_cached = False
                return False

            # Check aria-checked state
            is_checked_str = await toggle_locator.first.get_attribute("aria-checked")
            is_enabled = is_checked_str == "true"

            elapsed = time.perf_counter() - start_time
            if FUNCTION_CALLING_DEBUG:
                self.logger.debug(
                    f"[{self.req_id}] [FC:UI] Toggle check complete in {elapsed:.3f}s: "
                    f"{'enabled' if is_enabled else 'disabled'}"
                )
            if FUNCTION_CALLING_DEBUG:
                fc_logger.log_ui_action(
                    self.req_id,
                    "check",
                    "fc_toggle",
                    elapsed_ms=elapsed * 1000,
                )

            # Update instance cache
            self._fc_toggle_cached = is_enabled

            return is_enabled

        except asyncio.CancelledError:
            raise
        except ClientDisconnectedError:
            raise
        except Exception as e:
            if FUNCTION_CALLING_DEBUG:
                self.logger.warning(
                    f"[{self.req_id}] [FC] Error checking function calling state: {e}"
                )
            return False

    async def _set_function_calling_toggle(
        self,
        enable: bool,
        check_client_disconnected: Callable,
    ) -> bool:
        """
        Internal method to set function calling toggle state.

        Args:
            enable: True to enable, False to disable
            check_client_disconnected: Callback to check client connection

        Returns:
            True if toggle was set successfully, False otherwise.
        """
        action = "enable" if enable else "disable"
        if FUNCTION_CALLING_DEBUG:
            self.logger.debug(
                f"[{self.req_id}] [FC:UI] Attempting to {action} function calling"
            )

        await self._check_disconnect(
            check_client_disconnected, f"Function calling - {action}"
        )

        start_time = time.perf_counter()

        try:
            toggle_locator = self.page.locator(FUNCTION_CALLING_TOGGLE_SELECTOR)

            # Wait for toggle to be visible
            await expect_async(toggle_locator.first).to_be_visible(
                timeout=FUNCTION_CALLING_UI_TIMEOUT
            )

            # Check current state
            is_checked_str = await toggle_locator.first.get_attribute("aria-checked")
            is_currently_enabled = is_checked_str == "true"

            if is_currently_enabled == enable:
                elapsed = time.perf_counter() - start_time
                if FUNCTION_CALLING_DEBUG:
                    self.logger.debug(
                        f"[{self.req_id}] [FC:UI] Toggle already {'enabled' if enable else 'disabled'} "
                        f"(checked in {elapsed:.3f}s)"
                    )
                self._fc_toggle_cached = enable
                return True

            # Click to toggle
            await self._check_disconnect(
                check_client_disconnected, f"Function calling - before {action} click"
            )

            # Try to scroll into view first
            try:
                await toggle_locator.first.scroll_into_view_if_needed()
            except Exception:
                pass  # Ignore scroll errors

            await toggle_locator.first.click(timeout=CLICK_TIMEOUT_MS)

            # Wait for state change
            await asyncio.sleep(0.3)

            # Verify the change
            new_state_str = await toggle_locator.first.get_attribute("aria-checked")
            new_state = new_state_str == "true"

            elapsed = time.perf_counter() - start_time

            if new_state == enable:
                if FUNCTION_CALLING_DEBUG:
                    self.logger.info(
                        f"[{self.req_id}] [FC:UI] Toggle {action}d successfully in {elapsed:.2f}s"
                    )
                if FUNCTION_CALLING_DEBUG:
                    fc_logger.log_ui_action(
                        self.req_id,
                        action,
                        "fc_toggle",
                        elapsed_ms=elapsed * 1000,
                    )
                # Update instance cache
                self._fc_toggle_cached = enable
                # Update global cache
                cache = self._get_fc_cache()
                if cache:
                    cache.update_toggle_state(enable, req_id=self.req_id)
                return True
            else:
                if FUNCTION_CALLING_DEBUG:
                    self.logger.warning(
                        f"[{self.req_id}] [FC:UI] Toggle state change failed. "
                        f"Expected: {enable}, Actual: {new_state}"
                    )
                return False

        except asyncio.CancelledError:
            raise
        except ClientDisconnectedError:
            raise
        except Exception as e:
            if FUNCTION_CALLING_DEBUG:
                self.logger.error(
                    f"[{self.req_id}] [FC] Error {action}ing function calling: {e}"
                )
            from browser_utils.operations import save_error_snapshot

            await save_error_snapshot(f"function_calling_{action}_error_{self.req_id}")
            return False

    async def enable_function_calling(
        self,
        check_client_disconnected: Callable,
    ) -> bool:
        """
        Enable function calling toggle.

        Args:
            check_client_disconnected: Callback to check client connection

        Returns:
            True if enabled successfully, False otherwise.
        """
        return await self._set_function_calling_toggle(
            enable=True,
            check_client_disconnected=check_client_disconnected,
        )

    async def disable_function_calling(
        self,
        check_client_disconnected: Callable,
    ) -> bool:
        """
        Disable function calling toggle.

        Args:
            check_client_disconnected: Callback to check client connection

        Returns:
            True if disabled successfully, False otherwise.
        """
        return await self._set_function_calling_toggle(
            enable=False,
            check_client_disconnected=check_client_disconnected,
        )

    async def _open_function_declarations_dialog(
        self,
        check_client_disconnected: Callable,
    ) -> bool:
        """
        Open the function declarations editor dialog.

        Returns:
            True if dialog opened successfully, False otherwise.
        """
        if FUNCTION_CALLING_DEBUG:
            self.logger.debug(
                f"[{self.req_id}] [FC:UI] Opening function declarations dialog"
            )

        await self._check_disconnect(
            check_client_disconnected, "Function declarations - opening dialog"
        )

        start_time = time.perf_counter()

        try:
            # Find and click the edit button
            edit_button = self.page.locator(FUNCTION_DECLARATIONS_EDIT_BUTTON_SELECTOR)

            await expect_async(edit_button.first).to_be_visible(
                timeout=FUNCTION_CALLING_UI_TIMEOUT
            )

            # Try to scroll into view
            try:
                await edit_button.first.scroll_into_view_if_needed()
            except Exception:
                pass

            await edit_button.first.click(timeout=CLICK_TIMEOUT_MS)

            # Wait for dialog to appear
            dialog = self.page.locator(FUNCTION_DECLARATIONS_DIALOG_SELECTOR)
            await expect_async(dialog.first).to_be_visible(
                timeout=SELECTOR_VISIBILITY_TIMEOUT_MS
            )

            elapsed = time.perf_counter() - start_time
            if FUNCTION_CALLING_DEBUG:
                self.logger.debug(
                    f"[{self.req_id}] [FC:Perf] Dialog opened in {elapsed:.2f}s"
                )
                fc_logger.log_ui_action(
                    self.req_id,
                    "open",
                    "declarations_dialog",
                    elapsed_ms=elapsed * 1000,
                )
            return True

        except asyncio.CancelledError:
            raise
        except ClientDisconnectedError:
            raise
        except Exception as e:
            if FUNCTION_CALLING_DEBUG:
                self.logger.error(
                    f"[{self.req_id}] [FC:UI] Failed to open function declarations dialog: {e}"
                )
            from browser_utils.operations import save_error_snapshot

            await save_error_snapshot(f"function_dialog_open_error_{self.req_id}")
            return False

    async def _switch_to_code_editor_tab(
        self,
        check_client_disconnected: Callable,
    ) -> bool:
        """
        Switch to the Code Editor tab in the function declarations dialog.

        Returns:
            True if switched successfully or already on Code Editor tab, False otherwise.
        """
        if FUNCTION_CALLING_DEBUG:
            self.logger.debug(f"[{self.req_id}] UI: Clicking Code Editor tab")

        await self._check_disconnect(
            check_client_disconnected, "Function declarations - switch to code editor"
        )

        try:
            code_editor_tab = self.page.locator(
                FUNCTION_DECLARATIONS_CODE_EDITOR_TAB_SELECTOR
            )

            # Check if tab exists
            if await code_editor_tab.count() == 0:
                # Might already be in Code Editor mode or single-mode dialog
                if FUNCTION_CALLING_DEBUG:
                    self.logger.debug(
                        f"[{self.req_id}] UI: Code Editor tab not found, assuming single-mode"
                    )
                return True

            # Check if already selected
            is_selected = await code_editor_tab.first.get_attribute("aria-selected")
            if is_selected == "true":
                if FUNCTION_CALLING_DEBUG:
                    self.logger.debug(f"[{self.req_id}] UI: Already on Code Editor tab")
                return True

            # Click to switch
            await code_editor_tab.first.click(timeout=CLICK_TIMEOUT_MS)
            await asyncio.sleep(0.3)

            if FUNCTION_CALLING_DEBUG:
                self.logger.debug(f"[{self.req_id}] UI: Switched to Code Editor tab")
            return True

        except asyncio.CancelledError:
            raise
        except ClientDisconnectedError:
            raise
        except Exception as e:
            if FUNCTION_CALLING_DEBUG:
                self.logger.warning(
                    f"[{self.req_id}] UI: Error switching to Code Editor tab: {e}"
                )
            return True  # Continue anyway, might work

    async def _input_function_declarations_json(
        self,
        declarations_json: str,
        check_client_disconnected: Callable,
    ) -> bool:
        """
        Input function declarations JSON into the textarea.

        Args:
            declarations_json: JSON string of function declarations
            check_client_disconnected: Callback to check client connection

        Returns:
            True if input was successful, False otherwise.
        """
        if FUNCTION_CALLING_DEBUG:
            self.logger.debug(
                f"[{self.req_id}] UI: Pasting JSON ({len(declarations_json)} chars)"
            )

        await self._check_disconnect(
            check_client_disconnected, "Function declarations - input JSON"
        )

        try:
            textarea = self.page.locator(FUNCTION_DECLARATIONS_TEXTAREA_SELECTOR)

            await expect_async(textarea.first).to_be_visible(
                timeout=FUNCTION_CALLING_UI_TIMEOUT
            )

            # Clear existing content and input new JSON
            # Use evaluate for reliable content replacement
            await textarea.first.evaluate(
                """(el, json) => {
                    el.value = json;
                    el.dispatchEvent(new Event('input', {bubbles: true}));
                    el.dispatchEvent(new Event('change', {bubbles: true}));
                }""",
                declarations_json,
            )

            await asyncio.sleep(0.2)

            if FUNCTION_CALLING_DEBUG:
                self.logger.debug(f"[{self.req_id}] UI: JSON input complete")
            return True

        except asyncio.CancelledError:
            raise
        except ClientDisconnectedError:
            raise
        except Exception as e:
            if FUNCTION_CALLING_DEBUG:
                self.logger.error(
                    f"[{self.req_id}] UI: Error inputting function declarations: {e}"
                )
            from browser_utils.operations import save_error_snapshot

            await save_error_snapshot(f"function_input_error_{self.req_id}")
            return False

    async def _save_and_close_dialog(
        self,
        check_client_disconnected: Callable,
    ) -> bool:
        """
        Save function declarations and close the dialog.

        Returns:
            True if saved and closed successfully, False otherwise.
        """
        if FUNCTION_CALLING_DEBUG:
            self.logger.debug(f"[{self.req_id}] UI: Saving and closing dialog")

        await self._check_disconnect(
            check_client_disconnected, "Function declarations - save and close"
        )

        try:
            # Find and click save button
            save_button = self.page.locator(FUNCTION_DECLARATIONS_SAVE_BUTTON_SELECTOR)

            await expect_async(save_button.first).to_be_visible(
                timeout=FUNCTION_CALLING_UI_TIMEOUT
            )

            await save_button.first.click(timeout=CLICK_TIMEOUT_MS)

            # Wait for dialog to close
            await asyncio.sleep(0.5)

            # Verify dialog is closed
            dialog = self.page.locator(FUNCTION_DECLARATIONS_DIALOG_SELECTOR)
            try:
                await expect_async(dialog.first).not_to_be_visible(timeout=3000)
                if FUNCTION_CALLING_DEBUG:
                    self.logger.debug(f"[{self.req_id}] UI: Dialog closed successfully")
                return True
            except Exception:
                # Dialog might still be open, try close button
                if FUNCTION_CALLING_DEBUG:
                    self.logger.debug(
                        f"[{self.req_id}] UI: Dialog still visible, trying close button"
                    )
                close_button = self.page.locator(
                    FUNCTION_DECLARATIONS_CLOSE_BUTTON_SELECTOR
                )
                if await close_button.count() > 0:
                    await close_button.first.click(timeout=CLICK_TIMEOUT_MS)
                    await asyncio.sleep(0.3)

                return True

        except asyncio.CancelledError:
            raise
        except ClientDisconnectedError:
            raise
        except Exception as e:
            if FUNCTION_CALLING_DEBUG:
                self.logger.error(f"[{self.req_id}] UI: Error saving declarations: {e}")
            from browser_utils.operations import save_error_snapshot

            await save_error_snapshot(f"function_save_error_{self.req_id}")
            return False

    async def set_function_declarations(
        self,
        declarations: List[dict],
        check_client_disconnected: Callable,
        tools_digest: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> bool:
        """
        Set function declarations in the AI Studio UI.

        This method:
        0. Checks cache to skip redundant operations if same tools
        1. Disables Google Search (required as it blocks function calling)
        2. Enables function calling if not already enabled
        3. Opens the function declarations dialog
        4. Switches to Code Editor tab
        5. Inputs the JSON declarations
        6. Saves and closes the dialog
        7. Updates cache on success

        Args:
            declarations: List of function declaration dictionaries (Gemini format)
            check_client_disconnected: Callback to check client connection
            tools_digest: Optional pre-computed digest for caching
            model_name: Optional model name for cache validation

        Returns:
            True if declarations were set successfully, False otherwise.
        """
        total_start = time.perf_counter()

        # Check cache first
        cache = self._get_fc_cache()
        if cache and tools_digest:
            if cache.is_cache_valid(tools_digest, model_name, req_id=self.req_id):
                cached_state = cache.get_cached_state()
                if cached_state and cached_state.declarations_set:
                    elapsed = time.perf_counter() - total_start
                    if FUNCTION_CALLING_DEBUG:
                        self.logger.info(
                            f"[{self.req_id}] [FC:Cache] HIT - skipping UI configuration "
                            f"(saved ~2-4s, check took {elapsed:.3f}s)"
                        )
                    return True
                else:
                    if FUNCTION_CALLING_DEBUG:
                        self.logger.debug(
                            f"[{self.req_id}] [FC:Cache] Valid digest but declarations not set"
                        )

        if FUNCTION_CALLING_DEBUG:
            self.logger.info(
                f"[{self.req_id}] [FC:UI] Setting {len(declarations)} function declaration(s)"
            )
            fc_logger.info(
                FCModule.UI,
                f"Setting {len(declarations)} function declaration(s)",
                req_id=self.req_id,
            )

        try:
            # Step 0: Disable Google Search and URL Context if enabled (blocks FC)
            from config import (
                GROUNDING_WITH_GOOGLE_SEARCH_TOGGLE_SELECTOR,
                USE_URL_CONTEXT_SELECTOR,
            )

            # 0a. Disable Google Search
            search_toggle = self.page.locator(
                GROUNDING_WITH_GOOGLE_SEARCH_TOGGLE_SELECTOR
            )
            if await search_toggle.count() > 0:
                try:
                    if await search_toggle.is_visible(timeout=2000):
                        is_checked = await search_toggle.get_attribute("aria-checked")
                        if is_checked == "true":
                            if FUNCTION_CALLING_DEBUG:
                                self.logger.info(
                                    f"[{self.req_id}] [FC:UI] Disabling Google Search (blocks FC)"
                                )
                            await search_toggle.click(timeout=CLICK_TIMEOUT_MS)
                            await asyncio.sleep(0.5)
                except Exception:
                    pass  # Ignore if not visible

            # 0b. Disable URL Context
            url_toggle = self.page.locator(USE_URL_CONTEXT_SELECTOR)
            if await url_toggle.count() > 0:
                try:
                    if await url_toggle.is_visible(timeout=2000):
                        is_checked = await url_toggle.get_attribute("aria-checked")
                        if is_checked == "true":
                            if FUNCTION_CALLING_DEBUG:
                                self.logger.info(
                                    f"[{self.req_id}] [FC:UI] Disabling URL Context (blocks FC)"
                                )
                            await url_toggle.click(timeout=CLICK_TIMEOUT_MS)
                            await asyncio.sleep(0.5)
                except Exception:
                    pass  # Ignore if not visible

            # Step 1: Enable function calling if not already enabled
            toggle_start = time.perf_counter()
            if not await self.is_function_calling_enabled(check_client_disconnected):
                if not await self.enable_function_calling(check_client_disconnected):
                    if FUNCTION_CALLING_DEBUG:
                        self.logger.error(
                            f"[{self.req_id}] [FC] Failed to enable function calling"
                        )
                    return False
            toggle_elapsed = time.perf_counter() - toggle_start

            await self._check_disconnect(
                check_client_disconnected, "Function declarations - after enable"
            )

            # Step 2: Open the function declarations dialog
            dialog_start = time.perf_counter()
            if not await self._open_function_declarations_dialog(
                check_client_disconnected
            ):
                if FUNCTION_CALLING_DEBUG:
                    self.logger.error(
                        f"[{self.req_id}] [FC] Failed to open function declarations dialog"
                    )
                return False
            dialog_elapsed = time.perf_counter() - dialog_start

            await self._check_disconnect(
                check_client_disconnected, "Function declarations - after dialog open"
            )

            # Step 3: Switch to Code Editor tab
            if not await self._switch_to_code_editor_tab(check_client_disconnected):
                if FUNCTION_CALLING_DEBUG:
                    self.logger.warning(
                        f"[{self.req_id}] [FC:UI] Could not switch to Code Editor tab, continuing"
                    )

            await self._check_disconnect(
                check_client_disconnected, "Function declarations - after tab switch"
            )

            # Step 4: Convert declarations to JSON and input
            declarations_json = json.dumps(declarations, indent=2)
            input_start = time.perf_counter()
            if not await self._input_function_declarations_json(
                declarations_json, check_client_disconnected
            ):
                if FUNCTION_CALLING_DEBUG:
                    self.logger.error(
                        f"[{self.req_id}] [FC] Failed to input function declarations JSON"
                    )
                return False
            input_elapsed = time.perf_counter() - input_start

            await self._check_disconnect(
                check_client_disconnected, "Function declarations - after input"
            )

            # Step 5: Save and close
            save_start = time.perf_counter()
            if not await self._save_and_close_dialog(check_client_disconnected):
                if FUNCTION_CALLING_DEBUG:
                    self.logger.error(
                        f"[{self.req_id}] [FC] Failed to save function declarations"
                    )
                return False
            save_elapsed = time.perf_counter() - save_start

            total_elapsed = time.perf_counter() - total_start

            # Update cache on success
            if cache and tools_digest:
                cache.update_cache(
                    tools_digest=tools_digest,
                    toggle_enabled=True,
                    declarations_set=True,
                    model_name=model_name,
                    req_id=self.req_id,
                )
            self._fc_toggle_cached = True

            if FUNCTION_CALLING_DEBUG:
                self.logger.info(
                    f"[{self.req_id}] [FC:Perf] Function declarations set successfully "
                    f"(total={total_elapsed:.2f}s, toggle={toggle_elapsed:.2f}s, "
                    f"dialog={dialog_elapsed:.2f}s, input={input_elapsed:.2f}s, save={save_elapsed:.2f}s)"
                )
                fc_logger.info(
                    FCModule.UI,
                    f"Declarations set successfully in {total_elapsed:.2f}s",
                    req_id=self.req_id,
                )
            return True

        except asyncio.CancelledError:
            raise
        except ClientDisconnectedError:
            raise
        except Exception as e:
            if FUNCTION_CALLING_DEBUG:
                self.logger.error(
                    f"[{self.req_id}] [FC] Error setting function declarations: {e}"
                )
            from browser_utils.operations import save_error_snapshot

            await save_error_snapshot(f"set_function_declarations_error_{self.req_id}")
            return False

    async def clear_function_declarations(
        self,
        check_client_disconnected: Callable,
        invalidate_cache: bool = True,
    ) -> bool:
        """
        Clear all function declarations.

        This method opens the dialog and uses the reset button to clear all declarations,
        or sets an empty array if reset button is not available.

        Args:
            check_client_disconnected: Callback to check client connection
            invalidate_cache: If True, invalidate the FC cache (default True)

        Returns:
            True if declarations were cleared successfully, False otherwise.
        """
        if FUNCTION_CALLING_DEBUG:
            self.logger.info(f"[{self.req_id}] [FC:UI] Clearing function declarations")

        start_time = time.perf_counter()

        try:
            # Check if function calling is enabled
            if not await self.is_function_calling_enabled(check_client_disconnected):
                if FUNCTION_CALLING_DEBUG:
                    self.logger.debug(
                        f"[{self.req_id}] [FC] Function calling not enabled, nothing to clear"
                    )
                if invalidate_cache:
                    self.invalidate_fc_cache("clear - not enabled")
                return True

            await self._check_disconnect(
                check_client_disconnected, "Clear function declarations - start"
            )

            # Open dialog
            if not await self._open_function_declarations_dialog(
                check_client_disconnected
            ):
                if FUNCTION_CALLING_DEBUG:
                    self.logger.error(
                        f"[{self.req_id}] [FC] Failed to open dialog for clearing"
                    )
                return False

            await self._check_disconnect(
                check_client_disconnected,
                "Clear function declarations - after dialog open",
            )

            # Try to use reset button first
            reset_button = self.page.locator(
                FUNCTION_DECLARATIONS_RESET_BUTTON_SELECTOR
            )
            if await reset_button.count() > 0:
                try:
                    await reset_button.first.click(timeout=CLICK_TIMEOUT_MS)
                    await asyncio.sleep(0.3)
                    if FUNCTION_CALLING_DEBUG:
                        self.logger.debug(
                            f"[{self.req_id}] [FC:UI] Used reset button to clear declarations"
                        )
                except Exception:
                    # Fall back to clearing textarea
                    pass

            # Switch to code editor and clear
            await self._switch_to_code_editor_tab(check_client_disconnected)

            # Input empty array
            if not await self._input_function_declarations_json(
                "[]", check_client_disconnected
            ):
                if FUNCTION_CALLING_DEBUG:
                    self.logger.warning(
                        f"[{self.req_id}] [FC:UI] Failed to input empty declarations"
                    )

            # Save and close
            if not await self._save_and_close_dialog(check_client_disconnected):
                if FUNCTION_CALLING_DEBUG:
                    self.logger.error(
                        f"[{self.req_id}] [FC] Failed to save cleared declarations"
                    )
                return False

            # Optionally disable function calling toggle
            if await self.is_function_calling_enabled(
                check_client_disconnected, use_cache=False
            ):
                await self.disable_function_calling(check_client_disconnected)

            # Invalidate cache
            if invalidate_cache:
                self.invalidate_fc_cache("declarations cleared")

            elapsed = time.perf_counter() - start_time
            if FUNCTION_CALLING_DEBUG:
                self.logger.info(
                    f"[{self.req_id}] [FC:Perf] Declarations cleared in {elapsed:.2f}s"
                )
            return True

        except asyncio.CancelledError:
            raise
        except ClientDisconnectedError:
            raise
        except Exception as e:
            if FUNCTION_CALLING_DEBUG:
                self.logger.error(
                    f"[{self.req_id}] [FC] Error clearing function declarations: {e}"
                )
            from browser_utils.operations import save_error_snapshot

            await save_error_snapshot(
                f"clear_function_declarations_error_{self.req_id}"
            )
            return False

    async def is_function_calling_available(
        self,
        check_client_disconnected: Callable,
    ) -> bool:
        """
        Check if function calling UI is available on the current page/model.

        Some models may not support function calling, so this method checks
        if the function calling container is present in the UI.

        Args:
            check_client_disconnected: Callback to check client connection

        Returns:
            True if function calling is available, False otherwise.
        """
        await self._check_disconnect(
            check_client_disconnected, "Function calling - check available"
        )

        start_time = time.perf_counter()

        try:
            container = self.page.locator(FUNCTION_CALLING_CONTAINER_SELECTOR)

            # Quick check with short timeout
            try:
                await expect_async(container.first).to_be_visible(
                    timeout=FUNCTION_CALLING_UI_TIMEOUT // 2
                )
                elapsed = time.perf_counter() - start_time
                if FUNCTION_CALLING_DEBUG:
                    self.logger.debug(
                        f"[{self.req_id}] [FC:UI] Function calling available (checked in {elapsed:.3f}s)"
                    )
                return True
            except Exception:
                elapsed = time.perf_counter() - start_time
                if FUNCTION_CALLING_DEBUG:
                    self.logger.debug(
                        f"[{self.req_id}] [FC:UI] Function calling not available (checked in {elapsed:.3f}s)"
                    )
                return False

        except asyncio.CancelledError:
            raise
        except ClientDisconnectedError:
            raise
        except Exception as e:
            if FUNCTION_CALLING_DEBUG:
                self.logger.warning(
                    f"[{self.req_id}] [FC] Error checking function calling availability: {e}"
                )
            return False
