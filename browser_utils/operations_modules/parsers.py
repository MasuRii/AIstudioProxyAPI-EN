# --- browser_utils/operations_modules/parsers.py ---
import asyncio
import json
import logging
import os
import time
from typing import Any

from config import (
    DEBUG_LOGS_ENABLED,
    MODELS_ENDPOINT_URL_CONTAINS,
)

logger = logging.getLogger("AIStudioProxyServer")


async def _handle_model_list_response(response: Any):
    """Handle model list response"""
    # Need to access global variables
    from api_utils.server_state import state

    getattr(state, "global_model_list_raw_json", None)
    getattr(state, "parsed_model_list", [])
    model_list_fetch_event = getattr(state, "model_list_fetch_event", None)
    excluded_model_ids = getattr(state, "excluded_model_ids", set())

    if MODELS_ENDPOINT_URL_CONTAINS in response.url and response.ok:
        # Check if in login flow
        launch_mode = os.environ.get("LAUNCH_MODE", "debug")
        is_in_login_flow = launch_mode in ["debug"] and not getattr(
            state, "is_page_ready", False
        )

        if is_in_login_flow:
            # During login flow, handle silently to avoid interfering with user input
            pass  # Silent handling to avoid interfering with user input
        else:
            logger.debug(
                f"[Network] Captured model list response ({response.status} OK)"
            )
        try:
            data = await response.json()
            models_array_container = None
            if isinstance(data, list) and data:
                if (
                    isinstance(data[0], list)
                    and data[0]
                    and isinstance(data[0][0], list)
                ):
                    # [Parse] log moved to count change check
                    models_array_container = data[0]
                elif (
                    isinstance(data[0], list)
                    and data[0]
                    and isinstance(data[0][0], str)
                ):
                    # [Parse] log moved to count change check
                    models_array_container = data
                elif isinstance(data[0], dict):
                    # [Parse] log moved to count change check
                    models_array_container = data
                else:
                    logger.warning(
                        f"Unknown list nesting structure. data[0] type: {type(data[0]) if data else 'N/A'}. data[0] preview: {str(data[0])[:200] if data else 'N/A'}"
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
                            "Could not auto-locate model list array in dict response."
                        )
                        if (
                            model_list_fetch_event
                            and not model_list_fetch_event.is_set()
                        ):
                            model_list_fetch_event.set()
                        return
            else:
                logger.warning(
                    f"Received model list data is neither list nor dict: {type(data)}"
                )
                if model_list_fetch_event and not model_list_fetch_event.is_set():
                    model_list_fetch_event.set()
                return

            if models_array_container is not None:
                new_parsed_list = []
                excluded_during_parse: list[str] = []  # Collect excluded model IDs
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
                                        f"Model {current_model_id_for_log}: Cannot parse list index 6 value '{model_fields_list[6]}' as max_output_tokens."
                                    )

                            if (
                                len(model_fields_list) > 9
                                and model_fields_list[9] is not None
                            ):
                                try:
                                    raw_top_p = float(model_fields_list[9])
                                    if not (0.0 <= raw_top_p <= 1.0):
                                        logger.warning(
                                            f"Model {current_model_id_for_log}: Raw top_p value {raw_top_p} (from list index 9) exceeds [0,1] range, will be clipped."
                                        )
                                        default_top_p_val = max(
                                            0.0, min(1.0, raw_top_p)
                                        )
                                    else:
                                        default_top_p_val = raw_top_p
                                except (ValueError, TypeError):
                                    logger.warning(
                                        f"Model {current_model_id_for_log}: Cannot parse list index 9 value '{model_fields_list[9]}' as top_p."
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
                                        f"Model {current_model_id_for_log}: Cannot parse dict value '{mot_parsed}' as max_output_tokens."
                                    )

                            top_p_parsed = model_fields_list.get(
                                "topP", model_fields_list.get("defaultTopP")
                            )
                            if top_p_parsed is not None:
                                try:
                                    raw_top_p = float(top_p_parsed)
                                    if not (0.0 <= raw_top_p <= 1.0):
                                        logger.warning(
                                            f"Model {current_model_id_for_log}: Raw top_p value {raw_top_p} (from dict) exceeds [0,1] range, will be clipped."
                                        )
                                        default_top_p_val = max(
                                            0.0, min(1.0, raw_top_p)
                                        )
                                    else:
                                        default_top_p_val = raw_top_p
                                except (ValueError, TypeError):
                                    logger.warning(
                                        f"Model {current_model_id_for_log}: Cannot parse dict value '{top_p_parsed}' as top_p."
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
                                        f"Model {current_model_id_for_log}: Cannot parse dict value '{temp_parsed}' as temperature."
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
                            excluded_during_parse.append(simple_model_id_str)
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

                # Excluded model log moved to count change check
                excluded_count = (
                    len(excluded_during_parse) if excluded_during_parse else 0
                )

                if new_parsed_list:
                    # Check if network interception already injected models
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
                        logger.info(
                            "Detected network interception already injected models"
                        )

                    # Note: No longer adding injected models on backend
                    # If frontend didn't inject via network interception, these models won't be usable anyway
                    # So we only rely on network interception for injection

                    state.parsed_model_list = sorted(
                        new_parsed_list, key=lambda m: m.get("display_name", "").lower()
                    )
                    state.global_model_list_raw_json = json.dumps(
                        {"data": state.parsed_model_list, "object": "list"}
                    )
                    if DEBUG_LOGS_ENABLED:
                        # Only print full model list on first load or count change
                        previous_count = getattr(state, "_last_model_count", 0) or 0
                        current_count = len(state.parsed_model_list)
                        if previous_count != current_count or previous_count == 0:
                            # Only show detailed parsing info when list changes
                            if excluded_count > 0 and not is_in_login_flow:
                                logger.debug(
                                    f"[Model] Excluded {excluded_count} models"
                                )
                            log_output = (
                                f"[Model] List updated: {current_count} models\n"
                            )
                            for i, item in enumerate(
                                state.parsed_model_list[
                                    : min(3, len(state.parsed_model_list))
                                ]
                            ):
                                log_output += f"  {i + 1}. {item.get('id')} (MaxTok={item.get('default_max_output_tokens')})\n"
                            logger.debug(log_output.rstrip())
                            state._last_model_count = current_count  # type: ignore
                        else:
                            logger.debug(f"[Model] List unchanged ({current_count})")
                    else:
                        logger.info(
                            f"[Model] List updated (total {len(state.parsed_model_list)} models)"
                        )
                    if model_list_fetch_event and not model_list_fetch_event.is_set():
                        model_list_fetch_event.set()
                elif not state.parsed_model_list:
                    logger.warning("Model list still empty after parsing.")
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
        except asyncio.CancelledError:
            raise
        except Exception as e_handle_list_resp:
            logger.exception(
                f"Unknown error processing model list response: {e_handle_list_resp}"
            )
        finally:
            if model_list_fetch_event and not model_list_fetch_event.is_set():
                logger.info(
                    "Finished processing model list response, forcing model_list_fetch_event set."
                )
                model_list_fetch_event.set()
