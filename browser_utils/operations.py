# --- browser_utils/operations.py ---
# Browser page operation functional module

import asyncio
import json
import logging
import os
import time
from typing import Any, Callable, Dict, Optional

from playwright.async_api import (
    Error as PlaywrightAsyncError,
)
from playwright.async_api import (
    Locator,
)
from playwright.async_api import (
    Page as AsyncPage,
)

# Import config and models
from config import (
    CHAT_SESSION_CONTENT_SELECTOR,
    CLICK_TIMEOUT_MS,
    DEBUG_LOGS_ENABLED,
    ERROR_TOAST_SELECTOR,
    INITIAL_WAIT_MS_BEFORE_POLLING,
    LAST_CHAT_TURN_SELECTOR,
    MODELS_ENDPOINT_URL_CONTAINS,
    QUOTA_EXCEEDED_SELECTOR,
    SCROLL_CONTAINER_SELECTOR,
)
from config.global_state import GlobalState
from models import ClientDisconnectedError, QuotaExceededError

logger = logging.getLogger("AIStudioProxyServer")


async def check_quota_limit(page: AsyncPage, req_id: str) -> None:
    """Check for blocking quota errors immediately."""
    # 1. Check Global State first
    if GlobalState.IS_QUOTA_EXCEEDED:
        raise QuotaExceededError("Global Quota Exceeded Flag is Active.")

    try:
        # 2. Check UI for Quota Error (New Selector)
        if await page.locator(QUOTA_EXCEEDED_SELECTOR).count() > 0:
            element = page.locator(QUOTA_EXCEEDED_SELECTOR).first
            if await element.is_visible(timeout=500):
                text = await element.text_content()
                if text and "user has exceeded quota" in text.lower():
                    logger.critical(
                        f"[{req_id}] ❌ Quota Limit Detected via UI! Text: {text}"
                    )
                    GlobalState.set_quota_exceeded(message=text)
                    raise QuotaExceededError(f"Quota exceeded detected via UI: {text}")

        # 3. Check UI for Quota Error (Old Selector - Legacy Fallback)
        quota_selector = (
            'ms-callout.warning-callout:has-text("You are out of free generations")'
        )
        if await page.locator(quota_selector).count() > 0:
            if await page.locator(quota_selector).first.is_visible(timeout=500):
                logger.critical(
                    f"[{req_id}] ❌ Quota Limit Detected (Legacy)! Account is out of free generations."
                )
                GlobalState.set_quota_exceeded(
                    message="AI Studio Account is out of free generations"
                )
                raise QuotaExceededError(
                    "AI Studio Account is out of free generations."
                )

    except QuotaExceededError:
        raise
    except Exception as e:
        # Don't let check errors block the main flow, unless it's the quota error itself
        logger.warning(f"[{req_id}] Error checking for quota limit: {e}")


async def get_raw_text_content(
    response_element: Locator, previous_text: str, req_id: str
) -> str:
    """Get raw text content from response element"""
    raw_text = previous_text
    try:
        await response_element.wait_for(state="attached", timeout=1000)

        # [FIX-SELECTOR] Ensure element is in viewport for DOM virtualization
        try:
            await response_element.scroll_into_view_if_needed(timeout=1000)
        except Exception:
            pass

        pre_element = response_element.locator("pre").last
        pre_found_and_visible = False
        try:
            await pre_element.wait_for(state="visible", timeout=250)
            pre_found_and_visible = True
        except PlaywrightAsyncError:
            pass

        if pre_found_and_visible:
            try:
                # [FIX-SELECTOR] Ensure pre element is in viewport
                await pre_element.scroll_into_view_if_needed(timeout=500)
                raw_text = await pre_element.inner_text(timeout=500)
            except PlaywrightAsyncError as pre_err:
                if DEBUG_LOGS_ENABLED:
                    logger.debug(
                        f"[{req_id}] (GetRawText) Failed to get inner text of pre element: {pre_err}"
                    )
        else:
            try:
                # [FIX-SELECTOR] Ensure response element is in viewport
                await response_element.scroll_into_view_if_needed(timeout=500)
                raw_text = await response_element.inner_text(timeout=500)
            except PlaywrightAsyncError as e_parent:
                if DEBUG_LOGS_ENABLED:
                    logger.debug(
                        f"[{req_id}] (GetRawText) Failed to get inner text of response element: {e_parent}"
                    )
    except PlaywrightAsyncError as e_parent:
        if DEBUG_LOGS_ENABLED:
            logger.debug(
                f"[{req_id}] (GetRawText) Response element not ready: {e_parent}"
            )
    except Exception as e_unexpected:
        logger.warning(f"[{req_id}] (GetRawText) Unexpected error: {e_unexpected}")

    if raw_text != previous_text:
        if DEBUG_LOGS_ENABLED:
            preview = raw_text[:100].replace("\n", "\\n")
            logger.debug(
                f"[{req_id}] (GetRawText) Text updated, length: {len(raw_text)}, Preview: '{preview}...'"
            )
    return raw_text


async def _handle_model_list_response(response: Any):
    """Handle model list response"""
    # Need access to global variables
    from api_utils.server_state import state

    global_model_list_raw_json = state.global_model_list_raw_json  # noqa: F841
    parsed_model_list = state.parsed_model_list  # noqa: F841
    model_list_fetch_event = state.model_list_fetch_event
    excluded_model_ids = state.excluded_model_ids

    if MODELS_ENDPOINT_URL_CONTAINS in response.url and response.ok:
        # Check if in login flow
        launch_mode = os.environ.get("LAUNCH_MODE", "debug")
        is_in_login_flow = launch_mode in ["debug"] and not state.is_page_ready

        if is_in_login_flow:
            # Silent during login flow
            pass
        else:
            logger.info(
                f"Captured potential model list response from: {response.url} (Status: {response.status})"
            )
        try:
            # Fix: Handle Network.getResponseBody protocol error by using fallback methods
            try:
                data = await response.json()
            except Exception as protocol_err:
                if "Network.getResponseBody" in str(
                    protocol_err
                ) or "Protocol error" in str(protocol_err):
                    logger.warning(
                        f"Playwright Protocol Error detected in model list response: {protocol_err}"
                    )
                    # Fallback: Try to get response body text and parse manually
                    try:
                        response_text = await response.text()
                        data = json.loads(response_text)
                        logger.info(
                            "Successfully parsed model list response using fallback method"
                        )
                    except Exception as fallback_err:
                        logger.error(
                            f"Fallback parsing also failed for model list response: {fallback_err}"
                        )
                        if (
                            model_list_fetch_event
                            and not model_list_fetch_event.is_set()
                        ):
                            model_list_fetch_event.set()
                        return
                else:
                    raise  # Re-raise if it's not the specific protocol error we're handling
            models_array_container = None
            if isinstance(data, list) and data:
                if (
                    isinstance(data[0], list)
                    and data[0]
                    and isinstance(data[0][0], list)
                ):
                    if not is_in_login_flow:
                        logger.info(
                            "Detected three-level list structure data[0][0] is list. Setting models_array_container to data[0]."
                        )
                    models_array_container = data[0]
                elif (
                    isinstance(data[0], list)
                    and data[0]
                    and isinstance(data[0][0], str)
                ):
                    if not is_in_login_flow:
                        logger.info(
                            "Detected two-level list structure data[0][0] is str. Setting models_array_container to data."
                        )
                    models_array_container = data
                elif isinstance(data[0], dict):
                    if not is_in_login_flow:
                        logger.info(
                            "Detected root list with dictionaries. Using data directly as models_array_container."
                        )
                    models_array_container = data
                else:
                    logger.warning(
                        f"Unknown list nested structure. data[0] type: {type(data[0]) if data else 'N/A'}. data[0] Preview: {str(data[0])[:200] if data else 'N/A'}"
                    )
            elif isinstance(data, dict):
                if "data" in data and isinstance(data["data"], list):
                    models_array_container = data["data"]
                elif "models" in data and isinstance(data["models"], list):
                    models_array_container = data["models"]
                else:
                    for key, value in data.items():
                        if (
                            isinstance(value, list)
                            and len(value) > 0
                            and isinstance(value[0], (dict, list))
                        ):
                            models_array_container = value
                            logger.info(
                                f"Model list data found under '{key}' key via heuristic search."
                            )
                            break
                    if models_array_container is None:
                        logger.warning(
                            "Could not automatically locate model list array in dictionary response."
                        )
                        if (
                            model_list_fetch_event
                            and not model_list_fetch_event.is_set()
                        ):
                            model_list_fetch_event.set()
                        return
            else:
                logger.warning(
                    f"Received model list data is neither list nor dictionary: {type(data)}"
                )
                if model_list_fetch_event and not model_list_fetch_event.is_set():
                    model_list_fetch_event.set()
                return

            if models_array_container is not None:
                new_parsed_list = []
                for entry_in_container in models_array_container:
                    model_fields_list = None
                    if isinstance(entry_in_container, dict):
                        potential_id = entry_in_container.get(
                            "id",
                            entry_in_container.get(
                                "model_id", entry_in_container.get("modelId")
                            ),
                        )
                        if potential_id:
                            model_fields_list = entry_in_container
                        else:
                            model_fields_list = list(entry_in_container.values())
                    elif isinstance(entry_in_container, list):
                        model_fields_list = entry_in_container
                    else:
                        logger.debug(
                            f"Skipping entry of unknown type: {type(entry_in_container)}"
                        )
                        continue

                    if not model_fields_list:
                        logger.debug(
                            "Skipping entry because model_fields_list is empty or None."
                        )
                        continue

                    model_id_path_str = None
                    display_name_candidate = ""
                    description_candidate = "N/A"
                    default_max_output_tokens_val = None
                    default_top_p_val = None
                    default_temperature_val = 1.0
                    supported_max_output_tokens_val = None
                    current_model_id_for_log = "UnknownModelYet"

                    try:
                        if isinstance(model_fields_list, list):
                            if not (
                                len(model_fields_list) > 0
                                and isinstance(model_fields_list[0], (str, int, float))
                            ):
                                logger.debug(
                                    f"Skipping list-based model_fields due to invalid first element: {str(model_fields_list)[:100]}"
                                )
                                continue
                            model_id_path_str = str(model_fields_list[0])
                            current_model_id_for_log = (
                                model_id_path_str.split("/")[-1]
                                if model_id_path_str and "/" in model_id_path_str
                                else model_id_path_str
                            )
                            display_name_candidate = (
                                str(model_fields_list[3])
                                if len(model_fields_list) > 3
                                else ""
                            )
                            description_candidate = (
                                str(model_fields_list[4])
                                if len(model_fields_list) > 4
                                else "N/A"
                            )

                            if (
                                len(model_fields_list) > 6
                                and model_fields_list[6] is not None
                            ):
                                try:
                                    val_int = int(model_fields_list[6])
                                    default_max_output_tokens_val = val_int
                                    supported_max_output_tokens_val = val_int
                                except (ValueError, TypeError):
                                    logger.warning(
                                        f"Model {current_model_id_for_log}: Could not parse value at index 6 '{model_fields_list[6]}' as max_output_tokens."
                                    )

                            if (
                                len(model_fields_list) > 9
                                and model_fields_list[9] is not None
                            ):
                                try:
                                    raw_top_p = float(model_fields_list[9])
                                    if not (0.0 <= raw_top_p <= 1.0):
                                        logger.warning(
                                            f"Model {current_model_id_for_log}: raw top_p value {raw_top_p} (from index 9) out of [0,1] range, will clip."
                                        )
                                        default_top_p_val = max(
                                            0.0, min(1.0, raw_top_p)
                                        )
                                    else:
                                        default_top_p_val = raw_top_p
                                except (ValueError, TypeError):
                                    logger.warning(
                                        f"Model {current_model_id_for_log}: Could not parse value at index 9 '{model_fields_list[9]}' as top_p."
                                    )

                        elif isinstance(model_fields_list, dict):
                            model_id_path_str = str(
                                model_fields_list.get(
                                    "id",
                                    model_fields_list.get(
                                        "model_id", model_fields_list.get("modelId")
                                    ),
                                )
                            )
                            current_model_id_for_log = (
                                model_id_path_str.split("/")[-1]
                                if model_id_path_str and "/" in model_id_path_str
                                else model_id_path_str
                            )
                            display_name_candidate = str(
                                model_fields_list.get(
                                    "displayName",
                                    model_fields_list.get(
                                        "display_name",
                                        model_fields_list.get("name", ""),
                                    ),
                                )
                            )
                            description_candidate = str(
                                model_fields_list.get("description", "N/A")
                            )

                            mot_parsed = model_fields_list.get(
                                "maxOutputTokens",
                                model_fields_list.get(
                                    "defaultMaxOutputTokens",
                                    model_fields_list.get("outputTokenLimit"),
                                ),
                            )
                            if mot_parsed is not None:
                                try:
                                    val_int = int(mot_parsed)
                                    default_max_output_tokens_val = val_int
                                    supported_max_output_tokens_val = val_int
                                except (ValueError, TypeError):
                                    logger.warning(
                                        f"Model {current_model_id_for_log}: Could not parse dict value '{mot_parsed}' as max_output_tokens."
                                    )

                            top_p_parsed = model_fields_list.get(
                                "topP", model_fields_list.get("defaultTopP")
                            )
                            if top_p_parsed is not None:
                                try:
                                    raw_top_p = float(top_p_parsed)
                                    if not (0.0 <= raw_top_p <= 1.0):
                                        logger.warning(
                                            f"Model {current_model_id_for_log}: raw top_p value {raw_top_p} (from dict) out of [0,1] range, will clip."
                                        )
                                        default_top_p_val = max(
                                            0.0, min(1.0, raw_top_p)
                                        )
                                    else:
                                        default_top_p_val = raw_top_p
                                except (ValueError, TypeError):
                                    logger.warning(
                                        f"Model {current_model_id_for_log}: Could not parse dict value '{top_p_parsed}' as top_p."
                                    )

                            temp_parsed = model_fields_list.get(
                                "temperature",
                                model_fields_list.get("defaultTemperature"),
                            )
                            if temp_parsed is not None:
                                try:
                                    default_temperature_val = float(temp_parsed)
                                except (ValueError, TypeError):
                                    logger.warning(
                                        f"Model {current_model_id_for_log}: Could not parse dict value '{temp_parsed}' as temperature."
                                    )
                        else:
                            logger.debug(
                                f"Skipping entry because model_fields_list is not list or dict: {type(model_fields_list)}"
                            )
                            continue
                    except Exception as e_parse_fields:
                        logger.error(
                            f"Error parsing model fields for entry {str(entry_in_container)[:100]}: {e_parse_fields}"
                        )
                        continue

                    if model_id_path_str and model_id_path_str.lower() != "none":
                        simple_model_id_str = (
                            model_id_path_str.split("/")[-1]
                            if "/" in model_id_path_str
                            else model_id_path_str
                        )
                        if simple_model_id_str in excluded_model_ids:
                            if not is_in_login_flow:
                                logger.info(
                                    f"Model '{simple_model_id_str}' is in excluded_model_ids list, skipped."
                                )
                            continue

                        final_display_name_str = (
                            display_name_candidate
                            if display_name_candidate
                            else simple_model_id_str.replace("-", " ").title()
                        )
                        model_entry_dict = {
                            "id": simple_model_id_str,
                            "object": "model",
                            "created": int(time.time()),
                            "owned_by": "ai_studio",
                            "display_name": final_display_name_str,
                            "description": description_candidate,
                            "raw_model_path": model_id_path_str,
                            "default_temperature": default_temperature_val,
                            "default_max_output_tokens": default_max_output_tokens_val,
                            "supported_max_output_tokens": supported_max_output_tokens_val,
                            "default_top_p": default_top_p_val,
                        }
                        new_parsed_list.append(model_entry_dict)
                    else:
                        logger.debug(
                            f"Skipping entry due to invalid model_id_path: {model_id_path_str} from entry {str(entry_in_container)[:100]}"
                        )

                if new_parsed_list:
                    # Check if already has network intercepted injected models
                    has_network_injected_models = False
                    if models_array_container:
                        for entry_in_container in models_array_container:
                            if (
                                isinstance(entry_in_container, list)
                                and len(entry_in_container) > 10
                            ):
                                # Check for network injection marker
                                if "__NETWORK_INJECTED__" in entry_in_container:
                                    has_network_injected_models = True
                                    break

                    if has_network_injected_models and not is_in_login_flow:
                        logger.info("Detected network interception injected models")

                    # Note: No longer add injected models in backend
                    # Only rely on network interception injection

                    state.parsed_model_list = sorted(
                        new_parsed_list, key=lambda m: m.get("display_name", "").lower()
                    )
                    state.global_model_list_raw_json = json.dumps(
                        {"data": state.parsed_model_list, "object": "list"}
                    )
                    if DEBUG_LOGS_ENABLED:
                        log_output = f"Successfully parsed and updated model list. Total parsed models: {len(state.parsed_model_list)}.\n"
                        for i, item in enumerate(
                            state.parsed_model_list[
                                : min(3, len(state.parsed_model_list))
                            ]
                        ):
                            log_output += f"  Model {i + 1}: ID={item.get('id')}, Name={item.get('display_name')}, Temp={item.get('default_temperature')}, MaxTokDef={item.get('default_max_output_tokens')}, MaxTokSup={item.get('supported_max_output_tokens')}, TopP={item.get('default_top_p')}\n"
                        logger.info(log_output)
                    if model_list_fetch_event and not model_list_fetch_event.is_set():
                        model_list_fetch_event.set()
                elif not state.parsed_model_list:
                    logger.warning("Model list remains empty after parsing.")
                    if model_list_fetch_event and not model_list_fetch_event.is_set():
                        model_list_fetch_event.set()
            else:
                logger.warning(
                    "models_array_container is None, cannot parse model list."
                )
                if model_list_fetch_event and not model_list_fetch_event.is_set():
                    model_list_fetch_event.set()
        except json.JSONDecodeError as json_err:
            logger.error(
                f"Failed to parse model list JSON: {json_err}. Response (first 500 chars): {await response.text()[:500]}"
            )
        except Exception as e_handle_list_resp:
            logger.exception(
                f"Unexpected error handling model list response: {e_handle_list_resp}"
            )
        finally:
            if model_list_fetch_event and not model_list_fetch_event.is_set():
                logger.info(
                    "Model list response handling finished, forcing model_list_fetch_event set."
                )
                model_list_fetch_event.set()


async def detect_and_extract_page_error(page: AsyncPage, req_id: str) -> Optional[str]:
    """Detect and extract page error"""
    error_toast_locator = page.locator(ERROR_TOAST_SELECTOR).last
    try:
        await error_toast_locator.wait_for(state="visible", timeout=500)
        message_locator = error_toast_locator.locator("span.content-text")
        error_message = await message_locator.text_content(timeout=500)
        if error_message:
            logger.error(
                f"[{req_id}]    Detected and extracted error message: {error_message}"
            )
            return error_message.strip()
        else:
            logger.warning(
                f"[{req_id}]    Detected error toast but failed to extract message."
            )
            return "Detected error toast but failed to extract specific message."
    except PlaywrightAsyncError:
        return None
    except Exception as e:
        logger.warning(f"[{req_id}]    Error checking for page error: {e}")
        return None


async def save_error_snapshot(
    error_name: str = "error", extra_context: Optional[Dict[str, Any]] = None
):
    """Save error snapshot - enhanced version with extra context support

    Args:
        error_name: Error name used for filename generation
        extra_context: Extra context info to be saved as JSON file
    """
    from api_utils.server_state import state

    name_parts = error_name.split("_")
    req_id = (
        name_parts[-1] if len(name_parts) > 1 and len(name_parts[-1]) == 7 else None
    )
    base_error_name = error_name if not req_id else "_".join(name_parts[:-1])
    log_prefix = f"[{req_id}]" if req_id else "[No ReqID]"
    page_to_snapshot = state.page_instance

    if (
        not state.browser_instance
        or not state.browser_instance.is_connected()
        or not page_to_snapshot
        or page_to_snapshot.is_closed()
    ):
        logger.warning(
            f"{log_prefix} Cannot save snapshot ({base_error_name}), browser/page unavailable."
        )
        return

    logger.info(
        f"{log_prefix} Attempting to save error snapshot ({base_error_name})..."
    )
    timestamp = int(time.time() * 1000)
    error_dir = os.path.join(os.path.dirname(__file__), "..", "errors_py")

    try:
        os.makedirs(error_dir, exist_ok=True)
        filename_suffix = f"{req_id}_{timestamp}" if req_id else f"{timestamp}"
        filename_base = f"{base_error_name}_{filename_suffix}"
        screenshot_path = os.path.join(error_dir, f"{filename_base}.png")
        html_path = os.path.join(error_dir, f"{filename_base}.html")
        context_path = os.path.join(error_dir, f"{filename_base}_context.json")

        # Save screenshot
        try:
            await page_to_snapshot.screenshot(
                path=screenshot_path, full_page=True, timeout=15000
            )
            logger.info(f"{log_prefix}   Snapshot saved to: {screenshot_path}")
        except Exception as ss_err:
            logger.error(
                f"{log_prefix}   Failed to save screenshot ({base_error_name}): {ss_err}"
            )

        # Save HTML content
        try:
            content = await page_to_snapshot.content()
            f = None
            try:
                f = open(html_path, "w", encoding="utf-8")
                f.write(content)
                logger.info(f"{log_prefix}   HTML saved to: {html_path}")
            except Exception as write_err:
                logger.error(
                    f"{log_prefix}   Failed to save HTML ({base_error_name}): {write_err}"
                )
            finally:
                if f:
                    try:
                        f.close()
                        logger.debug(f"{log_prefix}   HTML file closed correctly")
                    except Exception as close_err:
                        logger.error(
                            f"{log_prefix}   Error closing HTML file: {close_err}"
                        )
        except Exception as html_err:
            logger.error(
                f"{log_prefix}   Failed to get page content ({base_error_name}): {html_err}"
            )

        # Save extra context info
        if extra_context:
            try:
                context_data = {
                    "timestamp": timestamp,
                    "error_name": base_error_name,
                    "req_id": req_id,
                    "context": extra_context,
                    "page_url": page_to_snapshot.url if page_to_snapshot else "N/A",
                    "user_agent": await page_to_snapshot.evaluate("navigator.userAgent")
                    if page_to_snapshot
                    else "N/A",
                }
                with open(context_path, "w", encoding="utf-8") as f:
                    json.dump(context_data, f, indent=2, ensure_ascii=False)
                logger.info(f"{log_prefix}   Context info saved to: {context_path}")
            except Exception as context_err:
                logger.error(
                    f"{log_prefix}   Failed to save context info ({base_error_name}): {context_err}"
                )

    except Exception as dir_err:
        logger.error(
            f"{log_prefix}   Error creating error directory or saving snapshot ({base_error_name}): {dir_err}"
        )


async def capture_response_state_for_debug(
    req_id: str, captured_content: str = "", detection_method: str = ""
) -> Dict[str, Any]:
    """Capture response state for debug - dedicated for analysis of response integrity issues"""
    from api_utils.server_state import state

    page = state.page_instance

    if not page or page.is_closed():
        return {"error": "Page not available"}

    debug_info = {
        "req_id": req_id,
        "timestamp": int(time.time() * 1000),
        "detection_method": detection_method,
        "captured_content_length": len(captured_content) if captured_content else 0,
        "captured_content_preview": captured_content[:200] + "..."
        if len(captured_content) > 200
        else captured_content,
        "page_url": page.url,
        "thinking_blocks_found": [],
        "response_blocks_found": [],
        "generation_status": {},
        "ui_elements": {},
    }

    try:
        # Check Thinking blocks
        from config.selectors import (
            FINAL_RESPONSE_SELECTOR,
            GENERATION_STATUS_SELECTOR,
            THINKING_CONTAINER_SELECTOR,
        )

        # Find Thinking containers
        thinking_containers = await page.locator(THINKING_CONTAINER_SELECTOR).all()
        for i, container in enumerate(thinking_containers):
            try:
                is_visible = await container.is_visible(timeout=1000)
                text_content = (
                    await container.inner_text(timeout=1000) if is_visible else ""
                )
                debug_info["thinking_blocks_found"].append(
                    {
                        "index": i,
                        "visible": is_visible,
                        "text_length": len(text_content),
                        "text_preview": text_content[:100] + "..."
                        if len(text_content) > 100
                        else text_content,
                    }
                )
            except Exception as e:
                debug_info["thinking_blocks_found"].append(
                    {"index": i, "error": str(e)}
                )

        # Find final response blocks
        response_elements = await page.locator(FINAL_RESPONSE_SELECTOR).all()
        for i, elem in enumerate(response_elements):
            try:
                is_visible = await elem.is_visible(timeout=1000)
                text_content = await elem.inner_text(timeout=1000) if is_visible else ""
                debug_info["response_blocks_found"].append(
                    {
                        "index": i,
                        "visible": is_visible,
                        "text_length": len(text_content),
                        "text_preview": text_content[:100] + "..."
                        if len(text_content) > 100
                        else text_content,
                    }
                )
            except Exception as e:
                debug_info["response_blocks_found"].append(
                    {"index": i, "error": str(e)}
                )

        # Check generation status
        generation_elements = await page.locator(GENERATION_STATUS_SELECTOR).all()
        for i, elem in enumerate(generation_elements):
            try:
                is_visible = await elem.is_visible(timeout=1000)
                aria_label = (
                    await elem.get_attribute("aria-label") if is_visible else ""
                )
                debug_info["generation_status"][f"status_{i}"] = {
                    "visible": is_visible,
                    "aria_label": aria_label,
                }
            except Exception as e:
                debug_info["generation_status"][f"status_{i}"] = {"error": str(e)}

        # Check key UI elements
        from config.selectors import (
            INPUT_SELECTOR,
            REGENERATE_BUTTON_SELECTOR,
            SUBMIT_BUTTON_SELECTOR,
        )

        key_elements = {
            "input_field": INPUT_SELECTOR,
            "submit_button": SUBMIT_BUTTON_SELECTOR,
            "regenerate_button": REGENERATE_BUTTON_SELECTOR,
        }

        for name, selector in key_elements.items():
            try:
                elem = page.locator(selector)
                is_visible = await elem.is_visible(timeout=1000)
                is_disabled = (
                    await elem.is_disabled(timeout=1000) if is_visible else False
                )
                debug_info["ui_elements"][name] = {
                    "visible": is_visible,
                    "disabled": is_disabled,
                }
            except Exception as e:
                debug_info["ui_elements"][name] = {"error": str(e)}

    except Exception as e:
        debug_info["capture_error"] = str(e)

    return debug_info


async def get_response_via_edit_button(
    page: AsyncPage, req_id: str, check_client_disconnected: Callable
) -> Optional[str]:
    """Get response via edit button"""
    logger.info(f"[{req_id}] (Helper) Attempting to get response via edit button...")
    last_message_container = page.locator("ms-chat-turn").last
    edit_button = last_message_container.get_by_label("Edit")
    finish_edit_button = last_message_container.get_by_label("Stop editing")
    autosize_textarea_locator = last_message_container.locator("ms-autosize-textarea")
    actual_textarea_locator = autosize_textarea_locator.locator("textarea")

    try:
        logger.info(
            f"[{req_id}]   - Attempting to hover last message to show 'Edit' button..."
        )
        try:
            # Perform hover on message container
            await last_message_container.hover(timeout=CLICK_TIMEOUT_MS / 2)
            await asyncio.sleep(0.3)  # Wait for hover effect
            check_client_disconnected("Edit Response - after hover: ")
        except Exception as hover_err:
            logger.warning(
                f"[{req_id}]   - (get_response_via_edit_button) Hover last message failed (ignoring): {type(hover_err).__name__}"
            )

        logger.info(f"[{req_id}]   - Locating and clicking 'Edit' button...")
        try:
            from playwright.async_api import expect as expect_async

            await expect_async(edit_button).to_be_visible(timeout=CLICK_TIMEOUT_MS)
            check_client_disconnected("Edit Response - 'Edit' button visible after: ")
            await edit_button.click(timeout=CLICK_TIMEOUT_MS)
            logger.info(f"[{req_id}]   - 'Edit' button clicked.")
        except Exception as edit_btn_err:
            logger.error(
                f"[{req_id}]   - 'Edit' button not visible or click failed: {edit_btn_err}"
            )
            await save_error_snapshot(f"edit_response_edit_button_failed_{req_id}")
            return None

        check_client_disconnected("Edit Response - after clicking 'Edit' button: ")
        await asyncio.sleep(0.3)
        check_client_disconnected(
            "Edit Response - after delay following 'Edit' button click: "
        )

        logger.info(f"[{req_id}]   - Getting content from textarea...")
        response_content = None
        textarea_failed = False

        try:
            await expect_async(autosize_textarea_locator).to_be_visible(
                timeout=CLICK_TIMEOUT_MS
            )
            check_client_disconnected(
                "Edit Response - after autosize-textarea visible: "
            )

            try:
                data_value_content = await autosize_textarea_locator.get_attribute(
                    "data-value"
                )
                check_client_disconnected(
                    "Edit Response - after get_attribute data-value: "
                )
                if data_value_content is not None:
                    response_content = str(data_value_content)
                    logger.info(
                        f"[{req_id}]   - Successfully obtained content from data-value."
                    )
            except Exception as data_val_err:
                logger.warning(
                    f"[{req_id}]   - Failed to get data-value: {data_val_err}"
                )
                check_client_disconnected(
                    "Edit Response - after get_attribute data-value error: "
                )

            if response_content is None:
                logger.info(
                    f"[{req_id}]   - data-value failed or None, attempting to get input_value from internal textarea..."
                )
                try:
                    await expect_async(actual_textarea_locator).to_be_visible(
                        timeout=CLICK_TIMEOUT_MS / 2
                    )
                    input_val_content = await actual_textarea_locator.input_value(
                        timeout=CLICK_TIMEOUT_MS / 2
                    )
                    check_client_disconnected("Edit Response - after input_value: ")
                    if input_val_content is not None:
                        response_content = str(input_val_content)
                        logger.info(
                            f"[{req_id}]   - Successfully obtained content from input_value."
                        )
                except Exception as input_val_err:
                    logger.warning(
                        f"[{req_id}]   - Failed to get input_value as well: {input_val_err}"
                    )
                    check_client_disconnected(
                        "Edit Response - after input_value error: "
                    )

            if response_content is not None:
                response_content = response_content.strip()
                content_preview = response_content[:100].replace("\\n", "\\\\n")
                logger.info(
                    f"[{req_id}]   - ✅ Final content obtained (length={len(response_content)}): '{content_preview}...'"
                )
            else:
                logger.warning(
                    f"[{req_id}]   - All content retrieval methods (data-value, input_value) failed or returned None."
                )
                textarea_failed = True

        except Exception as textarea_err:
            logger.error(
                f"[{req_id}]   - Failed to locate or process textarea: {textarea_err}"
            )
            textarea_failed = True
            response_content = None
            check_client_disconnected("Edit Response - after textarea error: ")

        if not textarea_failed:
            logger.info(
                f"[{req_id}]   - Locating and clicking 'Stop editing' button..."
            )
            try:
                await expect_async(finish_edit_button).to_be_visible(
                    timeout=CLICK_TIMEOUT_MS
                )
                check_client_disconnected(
                    "Edit Response - 'Stop editing' button visible after: "
                )
                await finish_edit_button.click(timeout=CLICK_TIMEOUT_MS)
                logger.info(f"[{req_id}]   - 'Stop editing' button clicked.")
            except Exception as finish_btn_err:
                logger.warning(
                    f"[{req_id}]   - 'Stop editing' button not visible or click failed: {finish_btn_err}"
                )
                await save_error_snapshot(
                    f"edit_response_finish_button_failed_{req_id}"
                )
            check_client_disconnected("Edit Response - after clicking 'Stop editing': ")
            await asyncio.sleep(0.2)
            check_client_disconnected(
                "Edit Response - after delay following 'Stop editing' click: "
            )
        else:
            logger.info(
                f"[{req_id}]   - Skipping 'Stop editing' button click due to textarea read failure."
            )

        return response_content

    except ClientDisconnectedError:
        logger.info(f"[{req_id}] (Helper Edit) Client disconnected.")
        raise
    except Exception:
        logger.exception(
            f"[{req_id}] Unexpected error during getting response via edit button"
        )
        await save_error_snapshot(f"edit_response_unexpected_error_{req_id}")
        return None


async def get_response_via_copy_button(
    page: AsyncPage, req_id: str, check_client_disconnected: Callable
) -> Optional[str]:
    """Get response via copy button"""
    logger.info(f"[{req_id}] (Helper) Attempting to get response via copy button...")
    last_message_container = page.locator("ms-chat-turn").last
    more_options_button = last_message_container.get_by_label("Open options")
    copy_markdown_button = page.get_by_role("menuitem", name="Copy markdown")

    try:
        logger.info(
            f"[{req_id}]   - Attempting to hover last message to show options..."
        )
        await last_message_container.hover(timeout=CLICK_TIMEOUT_MS)
        check_client_disconnected("Copy Response - after hover: ")
        await asyncio.sleep(0.5)
        check_client_disconnected("Copy Response - after hover delay: ")
        logger.info(f"[{req_id}]   - Hovered.")

        logger.info(f"[{req_id}]   - Locating and clicking 'More options' button...")
        try:
            from playwright.async_api import expect as expect_async

            await expect_async(more_options_button).to_be_visible(
                timeout=CLICK_TIMEOUT_MS
            )
            check_client_disconnected(
                "Copy Response - after more options button visible: "
            )
            await more_options_button.click(timeout=CLICK_TIMEOUT_MS)
            logger.info(f"[{req_id}]   - 'More options' clicked (via get_by_label).")
        except Exception as more_opts_err:
            logger.error(
                f"[{req_id}]   - 'More options' button (via get_by_label) not visible or click failed: {more_opts_err}"
            )
            await save_error_snapshot(f"copy_response_more_options_failed_{req_id}")
            return None

        check_client_disconnected("Copy Response - after clicking more options: ")
        await asyncio.sleep(0.5)
        check_client_disconnected(
            "Copy Response - after delay following more options click: "
        )

        logger.info(f"[{req_id}]   - Locating and clicking 'Copy markdown' button...")
        copy_success = False
        try:
            await expect_async(copy_markdown_button).to_be_visible(
                timeout=CLICK_TIMEOUT_MS
            )
            check_client_disconnected("Copy Response - after copy button visible: ")
            await copy_markdown_button.click(timeout=CLICK_TIMEOUT_MS, force=True)
            copy_success = True
            logger.info(f"[{req_id}]   - 'Copy markdown' clicked (via get_by_role).")
        except Exception as copy_err:
            logger.error(
                f"[{req_id}]   - 'Copy markdown' button (via get_by_role) click failed: {copy_err}"
            )
            await save_error_snapshot(f"copy_response_copy_button_failed_{req_id}")
            return None

        if not copy_success:
            logger.error(f"[{req_id}]   - Failed to click 'Copy markdown' button.")
            return None

        check_client_disconnected("Copy Response - after clicking copy button: ")
        await asyncio.sleep(0.5)
        check_client_disconnected(
            "Copy Response - after delay following copy button click: "
        )

        logger.info(f"[{req_id}]   - Reading clipboard content...")
        try:
            clipboard_content = await page.evaluate("navigator.clipboard.readText()")
            check_client_disconnected("Copy Response - after reading clipboard: ")
            if clipboard_content:
                content_preview = clipboard_content[:100].replace("\n", "\\\\n")
                logger.info(
                    f"[{req_id}]   - ✅ Successfully obtained clipboard content (length={len(clipboard_content)}): '{content_preview}...'"
                )
                return clipboard_content
            else:
                logger.error(f"[{req_id}]   - Clipboard content is empty.")
                return None
        except Exception as clipboard_err:
            if "clipboard-read" in str(clipboard_err):
                logger.error(
                    f"[{req_id}]   - Clipboard read failed: possible permissions issue. Error: {clipboard_err}"
                )
            else:
                logger.error(f"[{req_id}]   - Clipboard read failed: {clipboard_err}")
            await save_error_snapshot(f"copy_response_clipboard_read_failed_{req_id}")
            return None

    except ClientDisconnectedError:
        logger.info(f"[{req_id}] (Helper Copy) Client disconnected.")
        raise
    except Exception:
        logger.exception(f"[{req_id}] Unexpected error during copying response")
        await save_error_snapshot(f"copy_response_unexpected_error_{req_id}")
        return None


async def _wait_for_response_completion(
    page: AsyncPage,
    prompt_textarea_locator: Locator,
    submit_button_locator: Locator,
    edit_button_locator: Locator,
    req_id: str,
    check_client_disconnected_func: Callable,
    current_chat_id: Optional[str],
    prompt_length: int,
    initial_wait_ms=INITIAL_WAIT_MS_BEFORE_POLLING,
    timeout: Optional[float] = None,
) -> bool:
    """Wait for response completion"""
    from playwright.async_api import TimeoutError

    # [FIX-03] Dynamic TTFB Timeout - Rotation Aware
    if timeout is None:
        base_timeout_seconds = 5 + (prompt_length / 1000.0)

        # Rotation-aware adjustments
        if GlobalState.IS_QUOTA_EXCEEDED:
            rotation_overhead = 20  # 20 second overhead for rotation
            timeout_seconds = max(
                base_timeout_seconds + rotation_overhead, 30
            )  # Minimum 30s during rotation
            logger.info(
                f"[{req_id}] (WaitV3) Rotation detected - applying extended timeout: {timeout_seconds:.2f}s"
            )
        else:
            timeout_seconds = max(base_timeout_seconds, 10)
            timeout_seconds = min(timeout_seconds, 120)

            if prompt_length > 5000:
                timeout_seconds *= 1.5
                logger.info(
                    f"[{req_id}] (WaitV3) Large prompt detected - extending timeout by 50%: {timeout_seconds:.2f}s"
                )
    else:
        timeout_seconds = timeout
        if GlobalState.IS_QUOTA_EXCEEDED and timeout_seconds < 30:
            timeout_seconds = 30
            logger.info(
                f"[{req_id}] (WaitV3) Rotation detected - enforcing minimum timeout: {timeout_seconds:.2f}s"
            )

    _timeout_ms = timeout_seconds * 1000

    logger.info(
        f"[{req_id}] (WaitV3) Waiting for response completion... (Dynamic Timeout: {timeout_seconds:.2f}s)"
    )
    await asyncio.sleep(initial_wait_ms / 1000)

    start_time = time.time()

    from config import UI_GENERATION_WAIT_TIMEOUT_MS

    wait_timeout_ms_short = UI_GENERATION_WAIT_TIMEOUT_MS

    consecutive_empty_input_submit_disabled_count = 0

    current_timeout_seconds = timeout_seconds

    while True:
        # [FIX-SCROLL] Active Viewport Tracking (Auto-Scroll)
        try:
            await page.evaluate(
                """([scrollSel, contentSel, lastTurnSel]) => {
                const scrollContainer = document.querySelector(scrollSel);
                if (scrollContainer) {
                    scrollContainer.scrollTop = scrollContainer.scrollHeight;
                }

                const sessionContent = document.querySelector(contentSel);
                if (sessionContent) {
                     sessionContent.scrollTop = sessionContent.scrollHeight;
                }

                const lastTurn = document.querySelector(lastTurnSel);
                if (lastTurn) {
                    lastTurn.scrollIntoView({behavior: "instant", block: "end"});
                }

                window.scrollTo(0, document.body.scrollHeight);
            }""",
                [
                    SCROLL_CONTAINER_SELECTOR,
                    CHAT_SESSION_CONTENT_SELECTOR,
                    LAST_CHAT_TURN_SELECTOR,
                ],
            )
        except Exception:
            pass

        await check_quota_limit(page, req_id)

        try:
            check_client_disconnected_func("Wait for completion - loop start")
        except ClientDisconnectedError:
            logger.info(f"[{req_id}] (WaitV3) Client disconnected, aborting wait.")
            return False

        time_elapsed = time.time() - start_time
        if time_elapsed > current_timeout_seconds:
            is_thinking = await page.locator(
                'button[aria-label="Stop generating"]'
            ).is_visible()
            if is_thinking:
                logger.warning(
                    f"[{req_id}] 🚨 TIMEOUT REACHED despite active UI! Forcing stream completion."
                )
            else:
                logger.warning(
                    f"[{req_id}] ⏰ (WaitV3) Timed out waiting for response completion ({current_timeout_seconds:.1f}s). Aborting."
                )
            await save_error_snapshot(f"wait_completion_v3_overall_timeout_{req_id}")
            return False

        try:
            check_client_disconnected_func("Wait for completion - after timeout check")
        except ClientDisconnectedError:
            return False

        # C. Check if "Thinking" (UI is busy)
        stop_button_locator = page.locator('button[aria-label="Stop generating"]')
        is_thinking = await stop_button_locator.is_visible()
        if is_thinking:
            if DEBUG_LOGS_ENABLED:
                logger.debug(
                    f"[{req_id}] (WaitV3) UI shows thinking, but NOT resetting timeout (Network State Priority)"
                )

        # --- Primary conditions: Input empty & Submit disabled ---
        is_input_empty = await prompt_textarea_locator.input_value() == ""
        is_submit_disabled = False
        try:
            is_submit_disabled = await submit_button_locator.is_disabled(
                timeout=wait_timeout_ms_short
            )
        except TimeoutError:
            logger.warning(
                f"[{req_id}] (WaitV3) Timed out checking if submit button is disabled. Assuming not disabled for this check."
            )

        try:
            check_client_disconnected_func(
                "Wait for completion - after button status check"
            )
        except ClientDisconnectedError:
            return False

        if is_input_empty and is_submit_disabled:
            consecutive_empty_input_submit_disabled_count += 1
            if DEBUG_LOGS_ENABLED:
                logger.debug(
                    f"[{req_id}] (WaitV3) Primary conditions met: Input empty, submit disabled (count: {consecutive_empty_input_submit_disabled_count})."
                )

            # --- Final confirmation: Edit button visible ---
            try:
                if await edit_button_locator.is_visible(timeout=wait_timeout_ms_short):
                    logger.info(
                        f"[{req_id}] (WaitV3) ✅ Response complete: Input empty, submit disabled, edit button visible."
                    )
                    return True
            except TimeoutError:
                if DEBUG_LOGS_ENABLED:
                    logger.debug(
                        f"[{req_id}] (WaitV3) After primary conditions met, check for edit button visibility timed out."
                    )

            try:
                check_client_disconnected_func(
                    "Wait for completion - after edit button check"
                )
            except ClientDisconnectedError:
                return False

            # Heuristic completion: if primary conditions stay met but edit button doesn't appear
            if consecutive_empty_input_submit_disabled_count >= 3:
                logger.warning(
                    f"[{req_id}] (WaitV3) Response might be complete (heuristic): Input empty, submit disabled, but edit button still hasn't appeared after {consecutive_empty_input_submit_disabled_count} checks. Assuming complete."
                )
                return True
        else:
            consecutive_empty_input_submit_disabled_count = 0
            if DEBUG_LOGS_ENABLED:
                reasons = []
                if not is_input_empty:
                    reasons.append("input not empty")
                if not is_submit_disabled:
                    reasons.append("submit button not disabled")
                logger.debug(
                    f"[{req_id}] (WaitV3) Primary conditions not met ({', '.join(reasons)}). Continuing polling..."
                )

        await asyncio.sleep(0.5)


async def _get_final_response_content(
    page: AsyncPage, req_id: str, check_client_disconnected: Callable
) -> Optional[str]:
    """Get final response content"""
    logger.info(
        f"[{req_id}] (Helper GetContent) Starting to get final response content..."
    )
    response_content = await get_response_via_edit_button(
        page, req_id, check_client_disconnected
    )
    if response_content is not None:
        logger.info(
            f"[{req_id}] (Helper GetContent) ✅ Successfully obtained content via edit button."
        )
        return response_content

    logger.warning(
        f"[{req_id}] (Helper GetContent) Edit button method failed or returned empty, falling back to copy button method..."
    )
    response_content = await get_response_via_copy_button(
        page, req_id, check_client_disconnected
    )
    if response_content is not None:
        logger.info(
            f"[{req_id}] (Helper GetContent) ✅ Successfully obtained content via copy button."
        )
        return response_content

    logger.error(
        f"[{req_id}] (Helper GetContent) All response content retrieval methods failed."
    )
    await save_error_snapshot(f"get_content_all_methods_failed_{req_id}")
    return None
