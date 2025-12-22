"""
Model State Initialization and Synchronization
"""

import asyncio
import json
import logging

from playwright.async_api import Page as AsyncPage
from playwright.async_api import expect as expect_async

from config import INPUT_SELECTOR, MODEL_NAME_SELECTOR

from .ui_state import _verify_and_apply_ui_state, _verify_ui_state_settings

logger = logging.getLogger("AIStudioProxyServer")


async def _handle_initial_model_state_and_storage(page: AsyncPage):
    """Handle initial model state and storage"""
    from api_utils.server_state import state

    getattr(state, "current_ai_studio_model_id", None)
    getattr(state, "parsed_model_list", [])
    getattr(state, "model_list_fetch_event", None)

    logger.debug("[Init] Processing initial model state and localStorage...")
    needs_reload_and_storage_update = False
    reason_for_reload = ""

    try:
        initial_prefs_str = await page.evaluate(
            "() => localStorage.getItem('aiStudioUserPreference')"
        )
        if not initial_prefs_str:
            needs_reload_and_storage_update = True
            reason_for_reload = "localStorage not found"
        else:
            try:
                pref_obj = json.loads(initial_prefs_str)
                prompt_model_path = pref_obj.get("promptModel")
                pref_obj.get("isAdvancedOpen")
                is_prompt_model_valid = (
                    isinstance(prompt_model_path, str) and prompt_model_path.strip()
                )

                if not is_prompt_model_valid:
                    needs_reload_and_storage_update = True
                    reason_for_reload = "promptModel invalid"
                else:
                    # Use new UI state verification
                    ui_state = await _verify_ui_state_settings(page, "initial")
                    if ui_state["needsUpdate"]:
                        needs_reload_and_storage_update = True
                        reason_for_reload = "UI state mismatch"
                    else:
                        state.current_ai_studio_model_id = prompt_model_path.split("/")[
                            -1
                        ]
                        logger.debug(
                            f"localStorage valid and UI state correct. Initial model ID set from localStorage: {state.current_ai_studio_model_id}"
                        )
            except json.JSONDecodeError:
                needs_reload_and_storage_update = True
                reason_for_reload = (
                    "Failed to parse localStorage.aiStudioUserPreference JSON."
                )
                logger.error(
                    f"Determined refresh and storage update needed: {reason_for_reload}"
                )

        if needs_reload_and_storage_update:
            logger.debug(f"[State] Refresh needed: {reason_for_reload}")
            await _set_model_from_page_display(page, set_storage=True)

            current_page_url = page.url
            logger.info("[UI Operation] Reloading page to apply settings...")
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    logger.debug(
                        f"Attempting page reload (attempt {attempt + 1}/{max_retries}): {current_page_url}"
                    )
                    await page.goto(
                        current_page_url, wait_until="domcontentloaded", timeout=40000
                    )
                    await expect_async(page.locator(INPUT_SELECTOR)).to_be_visible(
                        timeout=30000
                    )
                    logger.debug(f"Page successfully reloaded to: {page.url}")

                    # Verify UI state after page reload
                    logger.debug("[State] Verifying UI state...")
                    reload_ui_state_success = await _verify_and_apply_ui_state(
                        page, "reload"
                    )
                    if reload_ui_state_success:
                        logger.info("[UI Check] Verification passed after page reload")
                    else:
                        logger.warning("UI state verification failed after reload")

                    break  # Exit loop on success
                except asyncio.CancelledError:
                    raise
                except Exception as reload_err:
                    logger.warning(
                        f"Page reload attempt {attempt + 1}/{max_retries} failed: {reload_err}"
                    )
                    if attempt < max_retries - 1:
                        logger.debug("[Init] Retrying in 5 seconds...")
                        await asyncio.sleep(5)
                    else:
                        logger.error(
                            f"Page reload ultimately failed after {max_retries} attempts: {reload_err}. Subsequent model state may be inaccurate.",
                            exc_info=True,
                        )
                        from browser_utils.operations import save_error_snapshot

                        await save_error_snapshot(
                            f"initial_storage_reload_fail_attempt_{attempt + 1}"
                        )

            logger.debug("[State] Syncing model ID after reload")
            await _set_model_from_page_display(page, set_storage=False)
            logger.debug(
                f"[State] Complete, current model: {state.current_ai_studio_model_id}"
            )
        else:
            logger.debug("[State] localStorage state OK, no refresh needed")
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(
            f"(New) Critical error processing initial model state and localStorage: {e}",
            exc_info=True,
        )
        try:
            logger.warning(
                "Due to error, attempting fallback to set global model ID from page display only (not writing to localStorage)..."
            )
            await _set_model_from_page_display(page, set_storage=False)
        except asyncio.CancelledError:
            raise
        except Exception as fallback_err:
            logger.error(f"Fallback model ID setting also failed: {fallback_err}")


async def _set_model_from_page_display(page: AsyncPage, set_storage: bool = False):
    """Set model from page display"""
    from api_utils.server_state import state

    getattr(state, "current_ai_studio_model_id", None)
    getattr(state, "parsed_model_list", [])
    model_list_fetch_event = getattr(state, "model_list_fetch_event", None)

    try:
        logger.debug("[Model] Reading current model from page display...")
        model_name_locator = page.locator(MODEL_NAME_SELECTOR)
        displayed_model_name_from_page_raw = await model_name_locator.first.inner_text(
            timeout=7000
        )
        displayed_model_name = displayed_model_name_from_page_raw.strip()
        logger.debug(f"[Model] Page display: '{displayed_model_name}'")

        found_model_id_from_display = None
        if model_list_fetch_event and not model_list_fetch_event.is_set():
            logger.debug("[Model] Waiting for model list data (up to 5 seconds)...")
            try:
                await asyncio.wait_for(model_list_fetch_event.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning(
                    "Timeout waiting for model list, may not be able to accurately convert display name to ID."
                )

        found_model_id_from_display = displayed_model_name

        new_model_value = found_model_id_from_display
        if state.current_ai_studio_model_id != new_model_value:
            state.current_ai_studio_model_id = new_model_value
            logger.debug(f"[Model] Global ID updated: {new_model_value}")
        # No log needed if unchanged

        if set_storage:
            logger.debug("[State] Preparing to update localStorage")
            existing_prefs_for_update_str = await page.evaluate(
                "() => localStorage.getItem('aiStudioUserPreference')"
            )
            prefs_to_set = {}
            if existing_prefs_for_update_str:
                try:
                    prefs_to_set = json.loads(existing_prefs_for_update_str)
                except json.JSONDecodeError:
                    logger.warning(
                        "Failed to parse existing localStorage.aiStudioUserPreference, will create new preferences."
                    )

            # Use new force settings feature
            logger.debug("[State] Applying forced UI state settings...")
            ui_state_success = await _verify_and_apply_ui_state(page, "set_model")
            if not ui_state_success:
                logger.warning("UI state setting failed, using legacy method")
                prefs_to_set["isAdvancedOpen"] = True
                prefs_to_set["areToolsOpen"] = True
            else:
                # Ensure prefs_to_set also contains correct settings
                prefs_to_set["isAdvancedOpen"] = True
                prefs_to_set["areToolsOpen"] = True
            logger.debug("[State] Set: isAdvancedOpen=true, areToolsOpen=true")

            if found_model_id_from_display:
                new_prompt_model_path = f"models/{found_model_id_from_display}"
                prefs_to_set["promptModel"] = new_prompt_model_path
            elif "promptModel" not in prefs_to_set:
                logger.warning(
                    f"Could not find model ID from page display '{displayed_model_name}', and no existing promptModel in localStorage. promptModel will not be actively set to avoid potential issues."
                )

            default_keys_if_missing = {
                "bidiModel": "models/gemini-1.0-pro-001",
                "isSafetySettingsOpen": False,
                "hasShownSearchGroundingTos": False,
                "autosaveEnabled": True,
                "theme": "system",
                "bidiOutputFormat": 3,
                "isSystemInstructionsOpen": False,
                "warmWelcomeDisplayed": True,
                "getCodeLanguage": "Node.js",
                "getCodeHistoryToggle": False,
                "fileCopyrightAcknowledged": True,
            }
            for key, val_default in default_keys_if_missing.items():
                if key not in prefs_to_set:
                    prefs_to_set[key] = val_default

            await page.evaluate(
                "(prefsStr) => localStorage.setItem('aiStudioUserPreference', prefsStr)",
                json.dumps(prefs_to_set),
            )
            logger.debug(
                f"[State] localStorage updated (model: {prefs_to_set.get('promptModel', 'N/A')})"
            )
    except asyncio.CancelledError:
        raise
    except Exception as e_set_disp:
        logger.error(
            f"Error setting model from page display: {e_set_disp}", exc_info=True
        )
