import asyncio
from typing import Callable, List

from playwright.async_api import TimeoutError
from playwright.async_api import expect as expect_async

from browser_utils.operations import save_error_snapshot
from config import (
    CDK_OVERLAY_CONTAINER_SELECTOR,
    PROMPT_TEXTAREA_SELECTOR,
    RESPONSE_CONTAINER_SELECTOR,
    SUBMIT_BUTTON_SELECTOR,
    UPLOAD_BUTTON_SELECTOR,
)
from config.selector_utils import (
    AUTOSIZE_WRAPPER_SELECTORS,
    build_combined_selector,
)
from logging_utils import set_request_id
from models import ClientDisconnectedError

from .base import BaseController


class InputController(BaseController):
    """Handles prompt input and submission."""

    async def submit_prompt(
        self, prompt: str, image_list: List, check_client_disconnected: Callable
    ):
        """Submit prompt to the page."""
        set_request_id(self.req_id)
        self.logger.debug(f"[Input] Filling prompt ({len(prompt)} chars)")
        prompt_textarea_locator = self.page.locator(PROMPT_TEXTAREA_SELECTOR)
        # Use centralized selectors supporting new and old UI structures
        autosize_wrapper_locator = self.page.locator(
            build_combined_selector(
                AUTOSIZE_WRAPPER_SELECTORS[:2]
            )  # .text-wrapper element
        )
        legacy_autosize_wrapper = self.page.locator(
            build_combined_selector(
                AUTOSIZE_WRAPPER_SELECTORS[2:]
            )  # ms-autosize-textarea element
        )
        submit_button_locator = self.page.locator(SUBMIT_BUTTON_SELECTOR)

        try:
            await expect_async(prompt_textarea_locator).to_be_visible(timeout=5000)
            await self._check_disconnect(
                check_client_disconnected, "After Input Visible"
            )

            # Fill text using JavaScript
            await prompt_textarea_locator.evaluate(
                """
                (element, text) => {
                    element.value = text;
                    element.dispatchEvent(new Event('input', { bubbles: true, cancelable: true }));
                    element.dispatchEvent(new Event('change', { bubbles: true, cancelable: true }));
                }
                """,
                prompt,
            )
            autosize_target = autosize_wrapper_locator
            if await autosize_target.count() == 0:
                autosize_target = legacy_autosize_wrapper
            if await autosize_target.count() > 0:
                try:
                    await autosize_target.first.evaluate(
                        '(element, text) => { element.setAttribute("data-value", text); }',
                        prompt,
                    )
                except Exception as autosize_err:
                    self.logger.debug(
                        f"autosize wrapper update skipped: {autosize_err}"
                    )
            await self._check_disconnect(check_client_disconnected, "After Input Fill")

            # Attachment upload handled below if needed
            if len(image_list) > 0:
                ok = await self._open_upload_menu_and_choose_file(image_list)
                if not ok:
                    self.logger.error(
                        "Error during file upload: Failed to set files via menu method"
                    )

            # Wait for submit button to be enabled (using configurable fast-fail timeout)
            from config.timeouts import SUBMIT_BUTTON_ENABLE_TIMEOUT_MS

            wait_timeout_ms_submit_enabled = SUBMIT_BUTTON_ENABLE_TIMEOUT_MS
            start_time = asyncio.get_event_loop().time()
            self.logger.debug(
                f"[Input] Waiting for submit button (max {wait_timeout_ms_submit_enabled}ms)"
            )

            try:
                while True:
                    await self._check_disconnect(
                        check_client_disconnected, "Waiting for Submit Button Enabled"
                    )

                    try:
                        # Use short timeout polling to respond to interruption signals
                        if await submit_button_locator.is_enabled(timeout=500):
                            self.logger.debug("[Input] Submit button enabled")
                            break
                    except Exception:
                        # Ignore temporary errors (e.g. element not present yet)
                        pass

                    if (
                        asyncio.get_event_loop().time() - start_time
                    ) * 1000 > wait_timeout_ms_submit_enabled:
                        raise TimeoutError(
                            f"Submit button not enabled within {wait_timeout_ms_submit_enabled}ms"
                        )

                    await asyncio.sleep(0.5)

            except Exception as e_pw_enabled:
                self.logger.error(
                    f"Timeout or error waiting for submit button enabled: {e_pw_enabled}"
                )
                await save_error_snapshot(f"submit_button_enable_timeout_{self.req_id}")
                raise

            await self._check_disconnect(
                check_client_disconnected, "After Submit Button Enabled"
            )
            await asyncio.sleep(0.3)

            # Try clicking button first, then Enter, then Combo keys
            button_clicked = False
            try:
                self.logger.debug("[Input] Attempting to click submit button...")
                # Handle potential dialogs before submit
                await self._handle_post_upload_dialog()
                # Try to clear tooltip overlays
                await self._dismiss_tooltip_overlays()
                try:
                    await submit_button_locator.click(timeout=5000)
                except Exception:
                    # If normal click fails (possibly blocked by tooltip), use JavaScript click
                    self.logger.debug(
                        "[Input] Normal click failed, attempting JavaScript click..."
                    )
                    js_clicked = await self._js_click_submit_button(
                        submit_button_locator
                    )
                    if not js_clicked:
                        # Finally try force click
                        self.logger.debug(
                            "[Input] JavaScript click failed, attempting force click..."
                        )
                        await submit_button_locator.click(timeout=5000, force=True)
                self.logger.debug("[Input] Submit button click complete")
                button_clicked = True
            except Exception as click_err:
                self.logger.error(f"Submit button click failed: {click_err}")
                await save_error_snapshot(f"submit_button_click_fail_{self.req_id}")

            if not button_clicked:
                self.logger.info(
                    "Button submit failed, attempting Enter key submission..."
                )
                submitted_successfully = await self._try_enter_submit(
                    prompt_textarea_locator, check_client_disconnected
                )
                if not submitted_successfully:
                    self.logger.info(
                        "Enter submission failed, attempting combo key submission..."
                    )
                    combo_ok = await self._try_combo_submit(
                        prompt_textarea_locator, check_client_disconnected
                    )
                    if not combo_ok:
                        self.logger.error("Combo key submission also failed.")
                        raise Exception(
                            "Submit failed: Button, Enter, and Combo key all failed"
                        )

            await self._check_disconnect(check_client_disconnected, "After Submit")

        except Exception as e_input_submit:
            if isinstance(e_input_submit, asyncio.CancelledError):
                raise
            self.logger.error(
                f"Error during input and submit process: {e_input_submit}"
            )
            if not isinstance(e_input_submit, ClientDisconnectedError):
                await save_error_snapshot(f"input_submit_error_{self.req_id}")
            raise

    async def _open_upload_menu_and_choose_file(self, files_list: List[str]) -> bool:
        """Select 'Upload' from the 'Insert assets' menu and set files."""
        try:
            # If a transparent overlay from a previous menu/dialog exists, try to close it
            try:
                tb = self.page.locator(
                    "div.cdk-overlay-backdrop.cdk-overlay-transparent-backdrop.cdk-overlay-backdrop-showing"
                )
                if await tb.count() > 0 and await tb.first.is_visible(timeout=300):
                    await self.page.keyboard.press("Escape")
                    await asyncio.sleep(0.2)
            except Exception:
                pass

            trigger = self.page.locator(UPLOAD_BUTTON_SELECTOR).first
            await expect_async(trigger).to_be_visible(timeout=3000)
            await trigger.click()
            menu_container = self.page.locator(CDK_OVERLAY_CONTAINER_SELECTOR)
            # Wait for menu to show
            try:
                await expect_async(
                    menu_container.locator("div[role='menu']").first
                ).to_be_visible(timeout=3000)
            except Exception:
                # Try clicking again
                try:
                    await trigger.click()
                    await expect_async(
                        menu_container.locator("div[role='menu']").first
                    ).to_be_visible(timeout=3000)
                except Exception:
                    self.logger.warning("Failed to show upload menu panel.")
                    return False

            # Use menu item with aria-label or text match
            try:
                # Prefer new UI match
                upload_btn = menu_container.locator(
                    "div[role='menu'] button[role='menuitem'][aria-label='Upload a file']"
                )
                if await upload_btn.count() == 0:
                    # Fallback to old UI match
                    upload_btn = menu_container.locator(
                        "div[role='menu'] button[role='menuitem'][aria-label='Upload File']"
                    )
                if await upload_btn.count() == 0:
                    # Fallback to text match (new UI)
                    upload_btn = menu_container.locator(
                        "div[role='menu'] button[role='menuitem']:has-text('Upload a file')"
                    )
                if await upload_btn.count() == 0:
                    # Fallback to text match (old UI)
                    upload_btn = menu_container.locator(
                        "div[role='menu'] button[role='menuitem']:has-text('Upload File')"
                    )
                if await upload_btn.count() == 0:
                    self.logger.warning(
                        "Could not find 'Upload a file' or 'Upload File' menu item."
                    )
                    return False
                btn = upload_btn.first
                await expect_async(btn).to_be_visible(timeout=2000)
                # Prefer internal hidden input[type=file]
                input_loc = btn.locator('input[type="file"]')
                if await input_loc.count() > 0:
                    await input_loc.set_input_files(files_list)
                    self.logger.info(
                        f"Files successfully set via hidden input in menu item (Upload): {len(files_list)} files"
                    )
                else:
                    # Fallback to native file chooser
                    async with self.page.expect_file_chooser() as fc_info:
                        await btn.click()
                    file_chooser = await fc_info.value
                    await file_chooser.set_files(files_list)
                    self.logger.info(
                        f"Files successfully set via native file chooser: {len(files_list)} files"
                    )
            except Exception as e_set:
                self.logger.error(f"Failed to set files: {e_set}")
                return False
            # Close leftover menu overlay
            try:
                backdrop = self.page.locator(
                    "div.cdk-overlay-backdrop.cdk-overlay-backdrop-showing, div.cdk-overlay-backdrop.cdk-overlay-transparent-backdrop.cdk-overlay-backdrop-showing"
                )
                if await backdrop.count() > 0:
                    await self.page.keyboard.press("Escape")
                    await asyncio.sleep(0.2)
            except Exception:
                pass
            # Handle potential authorization popups
            await self._handle_post_upload_dialog()
            return True
        except Exception as e:
            if isinstance(e, asyncio.CancelledError):
                raise
            self.logger.error(f"Failed to set files via upload menu: {e}")
            return False

    async def _handle_post_upload_dialog(self):
        """Handle authorization/copyright confirmation dialogs that may appear after upload."""
        try:
            overlay_container = self.page.locator(CDK_OVERLAY_CONTAINER_SELECTOR)
            if await overlay_container.count() == 0:
                return

            # Candidate agreement button texts
            agree_texts = [
                "Agree",
                "I agree",
                "Allow",
                "Continue",
                "OK",
                "Confirm",
                "Yes",
            ]
            # Search for visible buttons within the overlay container
            for text in agree_texts:
                try:
                    btn = overlay_container.locator(f"button:has-text('{text}')")
                    if await btn.count() > 0 and await btn.first.is_visible(
                        timeout=300
                    ):
                        await btn.first.click()
                        self.logger.info(
                            f"Post-upload dialog: Clicked button '{text}'."
                        )
                        await asyncio.sleep(0.3)
                        break
                except Exception:
                    continue
            # If copyright acknowledgment button exists (via aria-label)
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
                        "Post-upload dialog: Clicked copyright acknowledgment button (aria-label match)."
                    )
                    await asyncio.sleep(0.3)
            except Exception:
                pass

            # Wait for overlay to disappear
            try:
                overlay_backdrop = self.page.locator(
                    "div.cdk-overlay-backdrop.cdk-overlay-backdrop-showing"
                )
                if await overlay_backdrop.count() > 0:
                    try:
                        await expect_async(overlay_backdrop).to_be_hidden(timeout=3000)
                        self.logger.info("Post-upload dialog overlay hidden.")
                    except Exception:
                        self.logger.warning(
                            "Post-upload dialog overlay still exists, subsequent submit might be blocked."
                        )
            except Exception:
                pass
        except asyncio.CancelledError:
            raise
        except Exception:
            pass

    async def _dismiss_tooltip_overlays(self):
        """Close tooltip overlays that may block clicks - directly remove from DOM."""
        try:
            # Try to move mouse to make tooltips disappear naturally
            await self.page.mouse.move(0, 0)
            await asyncio.sleep(0.1)

            # Use JavaScript to force remove potential tooltip/overlay elements
            removed_count = await self.page.evaluate("""
                () => {
                    const selectors = [
                        '.mdc-tooltip',
                        '.mat-mdc-tooltip',
                        '.mdc-tooltip__surface',
                        '.mat-mdc-tooltip-surface',
                        '.cdk-overlay-pane:has(.mdc-tooltip)',
                        '.mat-tooltip-panel',
                        '[role="tooltip"]'
                    ];
                    let count = 0;
                    for (const sel of selectors) {
                        const elements = document.querySelectorAll(sel);
                        elements.forEach(el => {
                            el.remove();
                            count++;
                        });
                    }
                    return count;
                }
            """)
            if removed_count > 0:
                self.logger.debug(f"[Input] Removed {removed_count} tooltip elements")
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.logger.debug(f"[Input] Tooltip cleanup exception: {e}")

    async def _js_click_submit_button(self, submit_button_locator) -> bool:
        """Use JavaScript to trigger the submit button click event directly."""
        try:
            await submit_button_locator.evaluate("el => el.click()")
            self.logger.debug("[Input] JavaScript click on submit button successful")
            return True
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.logger.debug(f"[Input] JavaScript click failed: {e}")
            return False

    async def _try_enter_submit(
        self, prompt_textarea_locator, check_client_disconnected: Callable
    ) -> bool:
        """Submit using the Enter key."""

        try:
            await prompt_textarea_locator.focus(timeout=5000)
            await self._check_disconnect(check_client_disconnected, "After Input Focus")
            await asyncio.sleep(0.1)

            # Record content before submit for verification
            original_content = ""
            try:
                original_content = (
                    await prompt_textarea_locator.input_value(timeout=2000) or ""
                )
            except Exception:
                pass

            # Try Enter key submission
            self.logger.info("Attempting Enter key submission")
            try:
                await self.page.keyboard.press("Enter")
            except asyncio.CancelledError:
                raise
            except Exception:
                try:
                    await prompt_textarea_locator.press("Enter")
                except Exception:
                    pass

            await self._check_disconnect(check_client_disconnected, "After Enter Press")
            await asyncio.sleep(2.0)

            # Verify submission
            submission_success = False
            try:
                # Method 1: Check if input area is cleared
                current_content = (
                    await prompt_textarea_locator.input_value(timeout=2000) or ""
                )
                if original_content and not current_content.strip():
                    self.logger.info(
                        "Verification method 1: Input cleared, Enter key submission successful"
                    )
                    submission_success = True

                # Method 2: Check submit button status
                if not submission_success:
                    submit_button_locator = self.page.locator(SUBMIT_BUTTON_SELECTOR)
                    try:
                        is_disabled = await submit_button_locator.is_disabled(
                            timeout=2000
                        )
                        if is_disabled:
                            self.logger.info(
                                "Verification method 2: Submit button disabled, Enter key submission successful"
                            )
                            submission_success = True
                    except Exception:
                        pass

                # Method 3: Check for response container
                if not submission_success:
                    try:
                        response_container = self.page.locator(
                            RESPONSE_CONTAINER_SELECTOR
                        )
                        container_count = await response_container.count()
                        if container_count > 0:
                            last_container = response_container.last
                            is_vis = await last_container.is_visible(timeout=1000)
                            if is_vis:
                                self.logger.info(
                                    "Verification method 3: Response container detected, Enter key submission successful"
                                )
                                submission_success = True
                    except Exception:
                        pass
            except Exception as verify_err:
                self.logger.warning(
                    f"Error during Enter key submission verification: {verify_err}"
                )
                submission_success = True

            if submission_success:
                self.logger.info("Enter key submission successful")
                return True
            else:
                self.logger.warning("Enter key submission verification failed")
                return False
        except asyncio.CancelledError:
            raise
        except Exception as shortcut_err:
            self.logger.warning(f"Enter key submission failed: {shortcut_err}")
            return False

    async def _try_combo_submit(
        self, prompt_textarea_locator, check_client_disconnected: Callable
    ) -> bool:
        """Attempt submission using combo keys (Meta/Control + Enter)."""
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

            # Record content before submit for verification
            original_content = ""
            try:
                original_content = (
                    await prompt_textarea_locator.input_value(timeout=2000) or ""
                )
            except Exception:
                pass

            self.logger.info(
                f"Attempting combo submission: {shortcut_modifier}+{shortcut_key}"
            )
            try:
                await self.page.keyboard.press(f"{shortcut_modifier}+{shortcut_key}")
            except asyncio.CancelledError:
                raise
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
                    self.logger.info(
                        "Verification method 1: Input cleared, combo submission successful"
                    )
                    submission_success = True
                if not submission_success:
                    submit_button_locator = self.page.locator(SUBMIT_BUTTON_SELECTOR)
                    try:
                        is_disabled = await submit_button_locator.is_disabled(
                            timeout=2000
                        )
                        if is_disabled:
                            self.logger.info(
                                "Verification method 2: Submit button disabled, combo submission successful"
                            )
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
                            is_vis = await last_container.is_visible(timeout=1000)
                            if is_vis:
                                self.logger.info(
                                    "Verification method 3: Response container detected, combo submission successful"
                                )
                                submission_success = True
                    except Exception:
                        pass
            except Exception as verify_err:
                if isinstance(verify_err, asyncio.CancelledError):
                    raise
                self.logger.warning(
                    f"Error during combo submission verification: {verify_err}"
                )
                submission_success = True

            if submission_success:
                self.logger.info("Combo submission successful")
                return True
            else:
                self.logger.warning("Combo submission verification failed")
                return False
        except Exception as combo_err:
            if isinstance(combo_err, asyncio.CancelledError):
                raise
            self.logger.warning(f"Combo submission failed: {combo_err}")
            return False
