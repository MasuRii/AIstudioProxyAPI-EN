"""
Function Calling Controller Mixin

Provides browser automation for AI Studio's native function calling UI.
Handles enabling/disabling function calling toggle and managing function declarations.
"""

import asyncio
import json
from typing import Callable, List

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
from config.settings import FUNCTION_CALLING_UI_TIMEOUT
from models import ClientDisconnectedError

from .base import BaseController


class FunctionCallingController(BaseController):
    """
    Controller mixin for function calling UI automation.

    Provides methods to:
    - Check if function calling is enabled
    - Enable/disable function calling toggle
    - Open function declarations dialog
    - Input function declarations JSON
    - Save and close dialog
    """

    async def is_function_calling_enabled(
        self,
        check_client_disconnected: Callable,
    ) -> bool:
        """
        Check if function calling toggle is currently enabled.

        Returns:
            True if function calling is enabled, False otherwise.
        """
        await self._check_disconnect(
            check_client_disconnected, "Function calling - check enabled"
        )

        try:
            toggle_locator = self.page.locator(FUNCTION_CALLING_TOGGLE_SELECTOR)

            # Wait for toggle to be visible with a short timeout
            try:
                await expect_async(toggle_locator.first).to_be_visible(
                    timeout=FUNCTION_CALLING_UI_TIMEOUT
                )
            except Exception:
                self.logger.debug(
                    f"[{self.req_id}] Function calling toggle not visible, assuming disabled"
                )
                return False

            # Check aria-checked state
            is_checked_str = await toggle_locator.first.get_attribute("aria-checked")
            is_enabled = is_checked_str == "true"

            self.logger.debug(
                f"[{self.req_id}] Function calling is {'enabled' if is_enabled else 'disabled'}"
            )
            return is_enabled

        except asyncio.CancelledError:
            raise
        except ClientDisconnectedError:
            raise
        except Exception as e:
            self.logger.warning(
                f"[{self.req_id}] Error checking function calling state: {e}"
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
        self.logger.debug(f"[{self.req_id}] Attempting to {action} function calling")

        await self._check_disconnect(
            check_client_disconnected, f"Function calling - {action}"
        )

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
                self.logger.debug(
                    f"[{self.req_id}] Function calling already {'enabled' if enable else 'disabled'}"
                )
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

            if new_state == enable:
                self.logger.info(
                    f"[{self.req_id}] Function calling successfully {'enabled' if enable else 'disabled'}"
                )
                return True
            else:
                self.logger.warning(
                    f"[{self.req_id}] Function calling toggle state change failed. "
                    f"Expected: {enable}, Actual: {new_state}"
                )
                return False

        except asyncio.CancelledError:
            raise
        except ClientDisconnectedError:
            raise
        except Exception as e:
            self.logger.error(
                f"[{self.req_id}] Error {action}ing function calling: {e}"
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
        self.logger.debug(f"[{self.req_id}] Opening function declarations dialog")

        await self._check_disconnect(
            check_client_disconnected, "Function declarations - opening dialog"
        )

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

            self.logger.debug(f"[{self.req_id}] Function declarations dialog opened")
            return True

        except asyncio.CancelledError:
            raise
        except ClientDisconnectedError:
            raise
        except Exception as e:
            self.logger.error(
                f"[{self.req_id}] Error opening function declarations dialog: {e}"
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
        self.logger.debug(f"[{self.req_id}] Switching to Code Editor tab")

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
                self.logger.debug(
                    f"[{self.req_id}] Code Editor tab not found, assuming single-mode"
                )
                return True

            # Check if already selected
            is_selected = await code_editor_tab.first.get_attribute("aria-selected")
            if is_selected == "true":
                self.logger.debug(f"[{self.req_id}] Already on Code Editor tab")
                return True

            # Click to switch
            await code_editor_tab.first.click(timeout=CLICK_TIMEOUT_MS)
            await asyncio.sleep(0.3)

            self.logger.debug(f"[{self.req_id}] Switched to Code Editor tab")
            return True

        except asyncio.CancelledError:
            raise
        except ClientDisconnectedError:
            raise
        except Exception as e:
            self.logger.warning(
                f"[{self.req_id}] Error switching to Code Editor tab: {e}"
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
        self.logger.debug(
            f"[{self.req_id}] Inputting function declarations "
            f"({len(declarations_json)} chars)"
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

            self.logger.debug(
                f"[{self.req_id}] Function declarations JSON input complete"
            )
            return True

        except asyncio.CancelledError:
            raise
        except ClientDisconnectedError:
            raise
        except Exception as e:
            self.logger.error(
                f"[{self.req_id}] Error inputting function declarations: {e}"
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
        self.logger.debug(
            f"[{self.req_id}] Saving and closing function declarations dialog"
        )

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
                self.logger.debug(
                    f"[{self.req_id}] Function declarations dialog closed successfully"
                )
                return True
            except Exception:
                # Dialog might still be open, try close button
                self.logger.debug(
                    f"[{self.req_id}] Dialog still visible, trying close button"
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
            self.logger.error(
                f"[{self.req_id}] Error saving function declarations: {e}"
            )
            from browser_utils.operations import save_error_snapshot

            await save_error_snapshot(f"function_save_error_{self.req_id}")
            return False

    async def set_function_declarations(
        self,
        declarations: List[dict],
        check_client_disconnected: Callable,
    ) -> bool:
        """
        Set function declarations in the AI Studio UI.

        This method:
        0. Disables Google Search (required as it blocks function calling)
        1. Enables function calling if not already enabled
        2. Opens the function declarations dialog
        3. Switches to Code Editor tab
        4. Inputs the JSON declarations
        5. Saves and closes the dialog

        Args:
            declarations: List of function declaration dictionaries (Gemini format)
            check_client_disconnected: Callback to check client connection

        Returns:
            True if declarations were set successfully, False otherwise.
        """
        self.logger.info(
            f"[{self.req_id}] Setting {len(declarations)} function declaration(s)"
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
            if await search_toggle.count() > 0 and await search_toggle.is_visible(
                timeout=2000
            ):
                is_checked = await search_toggle.get_attribute("aria-checked")
                if is_checked == "true":
                    self.logger.info(
                        f"[{self.req_id}] Disabling Google Search to enable function calling"
                    )
                    await search_toggle.click(timeout=CLICK_TIMEOUT_MS)
                    await asyncio.sleep(0.5)

            # 0b. Disable URL Context
            url_toggle = self.page.locator(USE_URL_CONTEXT_SELECTOR)
            if await url_toggle.count() > 0 and await url_toggle.is_visible(
                timeout=2000
            ):
                is_checked = await url_toggle.get_attribute("aria-checked")
                if is_checked == "true":
                    self.logger.info(
                        f"[{self.req_id}] Disabling URL Context to enable function calling"
                    )
                    await url_toggle.click(timeout=CLICK_TIMEOUT_MS)
                    await asyncio.sleep(0.5)

            # Step 1: Enable function calling if not already enabled
            if not await self.is_function_calling_enabled(check_client_disconnected):
                if not await self.enable_function_calling(check_client_disconnected):
                    self.logger.error(
                        f"[{self.req_id}] Failed to enable function calling"
                    )
                    return False

            await self._check_disconnect(
                check_client_disconnected, "Function declarations - after enable"
            )

            # Step 2: Open the function declarations dialog
            if not await self._open_function_declarations_dialog(
                check_client_disconnected
            ):
                self.logger.error(
                    f"[{self.req_id}] Failed to open function declarations dialog"
                )
                return False

            await self._check_disconnect(
                check_client_disconnected, "Function declarations - after dialog open"
            )

            # Step 3: Switch to Code Editor tab
            if not await self._switch_to_code_editor_tab(check_client_disconnected):
                self.logger.warning(
                    f"[{self.req_id}] Could not switch to Code Editor tab, continuing anyway"
                )

            await self._check_disconnect(
                check_client_disconnected, "Function declarations - after tab switch"
            )

            # Step 4: Convert declarations to JSON and input
            declarations_json = json.dumps(declarations, indent=2)
            if not await self._input_function_declarations_json(
                declarations_json, check_client_disconnected
            ):
                self.logger.error(
                    f"[{self.req_id}] Failed to input function declarations JSON"
                )
                return False

            await self._check_disconnect(
                check_client_disconnected, "Function declarations - after input"
            )

            # Step 5: Save and close
            if not await self._save_and_close_dialog(check_client_disconnected):
                self.logger.error(
                    f"[{self.req_id}] Failed to save function declarations"
                )
                return False

            self.logger.info(f"[{self.req_id}] Function declarations set successfully")
            return True

        except asyncio.CancelledError:
            raise
        except ClientDisconnectedError:
            raise
        except Exception as e:
            self.logger.error(
                f"[{self.req_id}] Error setting function declarations: {e}"
            )
            from browser_utils.operations import save_error_snapshot

            await save_error_snapshot(f"set_function_declarations_error_{self.req_id}")
            return False

    async def clear_function_declarations(
        self,
        check_client_disconnected: Callable,
    ) -> bool:
        """
        Clear all function declarations.

        This method opens the dialog and uses the reset button to clear all declarations,
        or sets an empty array if reset button is not available.

        Args:
            check_client_disconnected: Callback to check client connection

        Returns:
            True if declarations were cleared successfully, False otherwise.
        """
        self.logger.info(f"[{self.req_id}] Clearing function declarations")

        try:
            # Check if function calling is enabled
            if not await self.is_function_calling_enabled(check_client_disconnected):
                self.logger.debug(
                    f"[{self.req_id}] Function calling not enabled, nothing to clear"
                )
                return True

            await self._check_disconnect(
                check_client_disconnected, "Clear function declarations - start"
            )

            # Open dialog
            if not await self._open_function_declarations_dialog(
                check_client_disconnected
            ):
                self.logger.error(
                    f"[{self.req_id}] Failed to open function declarations dialog for clearing"
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
                    self.logger.debug(
                        f"[{self.req_id}] Used reset button to clear declarations"
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
                self.logger.warning(
                    f"[{self.req_id}] Failed to input empty declarations"
                )

            # Save and close
            if not await self._save_and_close_dialog(check_client_disconnected):
                self.logger.error(
                    f"[{self.req_id}] Failed to save cleared declarations"
                )
                return False

            # Optionally disable function calling toggle
            if await self.is_function_calling_enabled(check_client_disconnected):
                await self.disable_function_calling(check_client_disconnected)

            self.logger.info(f"[{self.req_id}] Function declarations cleared")
            return True

        except asyncio.CancelledError:
            raise
        except ClientDisconnectedError:
            raise
        except Exception as e:
            self.logger.error(
                f"[{self.req_id}] Error clearing function declarations: {e}"
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

        try:
            container = self.page.locator(FUNCTION_CALLING_CONTAINER_SELECTOR)

            # Quick check with short timeout
            try:
                await expect_async(container.first).to_be_visible(
                    timeout=FUNCTION_CALLING_UI_TIMEOUT // 2
                )
                self.logger.debug(f"[{self.req_id}] Function calling UI is available")
                return True
            except Exception:
                self.logger.debug(f"[{self.req_id}] Function calling UI not available")
                return False

        except asyncio.CancelledError:
            raise
        except ClientDisconnectedError:
            raise
        except Exception as e:
            self.logger.warning(
                f"[{self.req_id}] Error checking function calling availability: {e}"
            )
            return False
