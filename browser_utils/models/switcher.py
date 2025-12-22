"""
Model Switching Logic
"""

import asyncio
import json
import logging
import os
from typing import Optional

from playwright.async_api import Page as AsyncPage
from playwright.async_api import expect as expect_async

from config import AI_STUDIO_URL_PATTERN, INPUT_SELECTOR, MODEL_NAME_SELECTOR

from .ui_state import _verify_and_apply_ui_state

logger = logging.getLogger("AIStudioProxyServer")


async def switch_ai_studio_model(page: AsyncPage, model_id: str, req_id: str) -> bool:
    """Switch AI Studio model"""
    logger.info(f"[Model] Switching to -> {model_id}")
    original_prefs_str: Optional[str] = None
    _original_prompt_model: Optional[str] = None
    new_chat_url = f"https://{AI_STUDIO_URL_PATTERN}prompts/new_chat"

    try:
        original_prefs_str = await page.evaluate(
            "() => localStorage.getItem('aiStudioUserPreference')"
        )
        if original_prefs_str:
            try:
                original_prefs_obj = json.loads(original_prefs_str)
                _original_prompt_model = original_prefs_obj.get("promptModel")
            except json.JSONDecodeError:
                logger.warning(
                    "Failed to parse original aiStudioUserPreference JSON string."
                )
                original_prefs_str = None

        current_prefs_for_modification = (
            json.loads(original_prefs_str) if original_prefs_str else {}
        )
        full_model_path = f"models/{model_id}"

        if current_prefs_for_modification.get("promptModel") == full_model_path:
            logger.debug(f"[Model] Already at target model {model_id}")
            if page.url != new_chat_url:
                logger.debug(
                    f"[Model] URL is not new_chat, navigating to {new_chat_url}"
                )
                await page.goto(
                    new_chat_url, wait_until="domcontentloaded", timeout=30000
                )
                await expect_async(page.locator(INPUT_SELECTOR)).to_be_visible(
                    timeout=30000
                )
            return True

        logger.debug(
            f"[Model] Updating localStorage.promptModel: {current_prefs_for_modification.get('promptModel', 'unknown')} -> {full_model_path}"
        )
        current_prefs_for_modification["promptModel"] = full_model_path
        await page.evaluate(
            "(prefsStr) => localStorage.setItem('aiStudioUserPreference', prefsStr)",
            json.dumps(current_prefs_for_modification),
        )

        # Use new forced setting feature
        logger.debug("[State] Applying forced UI state settings...")
        ui_state_success = await _verify_and_apply_ui_state(page, req_id)
        if not ui_state_success:
            logger.warning(
                "UI state setting failed, but continuing model switching flow"
            )

        # To maintain compatibility, also update current prefs object
        current_prefs_for_modification["isAdvancedOpen"] = True
        current_prefs_for_modification["areToolsOpen"] = True
        await page.evaluate(
            "(prefsStr) => localStorage.setItem('aiStudioUserPreference', prefsStr)",
            json.dumps(current_prefs_for_modification),
        )

        logger.debug(f"[Model] Navigating to {new_chat_url}...")
        await page.goto(new_chat_url, wait_until="domcontentloaded", timeout=30000)

        input_field = page.locator(INPUT_SELECTOR)
        await expect_async(input_field).to_be_visible(timeout=30000)
        logger.debug("[Model] Page navigation complete, input box visible")

        # Verify UI state settings again after page load
        logger.debug("[State] Verifying UI state...")
        final_ui_state_success = await _verify_and_apply_ui_state(page, req_id)
        if final_ui_state_success:
            logger.debug("[State] UI state verification successful")
        else:
            logger.warning(
                "Final UI state verification failed, but continuing model switching flow"
            )

        final_prefs_str = await page.evaluate(
            "() => localStorage.getItem('aiStudioUserPreference')"
        )
        final_prompt_model_in_storage: Optional[str] = None
        if final_prefs_str:
            try:
                final_prefs_obj = json.loads(final_prefs_str)
                final_prompt_model_in_storage = final_prefs_obj.get("promptModel")
            except json.JSONDecodeError:
                logger.warning(
                    "Failed to parse refreshed aiStudioUserPreference JSON string."
                )

        if final_prompt_model_in_storage == full_model_path:
            logger.debug(f"[Model] localStorage set correctly: {full_model_path}")

            page_display_match = False

            # Get parsed_model_list
            from api_utils.server_state import state

            parsed_model_list = getattr(state, "parsed_model_list", [])

            if parsed_model_list:
                for m_obj in parsed_model_list:
                    if m_obj.get("id") == model_id:
                        m_obj.get("display_name")
                        break

            try:
                model_name_locator = page.locator(MODEL_NAME_SELECTOR)
                actual_displayed_model_id_on_page_raw = (
                    await model_name_locator.first.inner_text(timeout=5000)
                )
                actual_displayed_model_id_on_page = (
                    actual_displayed_model_id_on_page_raw.strip()
                )

                target_model_id = model_id

                if actual_displayed_model_id_on_page == target_model_id:
                    page_display_match = True
                    logger.info("[Model] Switching successful")
                else:
                    page_display_match = False
                    logger.error(
                        f"Page displayed model ID ('{actual_displayed_model_id_on_page}') inconsistent with expected ID ('{target_model_id}')."
                    )

            except asyncio.CancelledError:
                raise
            except Exception as e_disp:
                page_display_match = False  # Reading failed, assume mismatch
                logger.warning(
                    f"Error reading displayed model ID: {e_disp}. Cannot verify page display."
                )

            if page_display_match:
                try:
                    logger.debug("[Model] Re-enabling temporary chat mode...")
                    incognito_button_locator = page.locator(
                        'button[aria-label="Temporary chat toggle"]'
                    )

                    await incognito_button_locator.wait_for(
                        state="visible", timeout=5000
                    )

                    button_classes = await incognito_button_locator.get_attribute(
                        "class"
                    )

                    if button_classes and "ms-button-active" in button_classes:
                        logger.debug("[Model] Temporary chat mode already active")
                    else:
                        logger.debug("[Model] Clicking to open temporary chat mode...")
                        await incognito_button_locator.click(timeout=3000)
                        await asyncio.sleep(0.5)

                        updated_classes = await incognito_button_locator.get_attribute(
                            "class"
                        )
                        if updated_classes and "ms-button-active" in updated_classes:
                            logger.debug("[Model] Temporary chat mode enabled")
                        else:
                            logger.warning(
                                "Temporary chat mode state verification failed after click, may not have opened successfully."
                            )

                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.warning(
                        f"Failed to re-enable temporary chat mode after model switching: {e}"
                    )
                return True
            else:
                logger.error(
                    "Model switching failed because page displayed model does not match expectation (even if localStorage may have changed)."
                )
        else:
            logger.error(
                f"AI Studio did not accept model change (localStorage). Expected='{full_model_path}', Actual='{final_prompt_model_in_storage or 'not set or invalid'}'."
            )

    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Serious error occurred during model switching")
        from browser_utils.operations import save_error_snapshot

        await save_error_snapshot(f"model_switch_error_{req_id}")
        return False
    return False


def load_excluded_models(filename: str):
    """Load excluded model list"""
    from api_utils.server_state import state

    excluded_model_ids = getattr(state, "excluded_model_ids", set())
    excluded_file_path = os.path.join(os.path.dirname(__file__), "..", "..", filename)
    try:
        if os.path.exists(excluded_file_path):
            with open(excluded_file_path, "r", encoding="utf-8") as f:
                loaded_ids = {line.strip() for line in f if line.strip()}
            if loaded_ids:
                excluded_model_ids.update(loaded_ids)
                state.excluded_model_ids = excluded_model_ids
                logger.debug(
                    f"Loaded {len(loaded_ids)} models from '{filename}' into exclusion list"
                )
            else:
                logger.debug(
                    f"'{filename}' file is empty or contains no valid model IDs, exclusion list unchanged."
                )
        else:
            logger.debug(
                f"Model exclusion list file '{filename}' not found, list is empty."
            )
    except Exception as e:
        logger.error(
            f"Error loading excluded models from '{filename}': {e}", exc_info=True
        )
