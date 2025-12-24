import base64
import json
import logging
import os
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple, Union, cast
from urllib.parse import unquote, urlparse

from api_utils.utils_ext.files import extract_data_url_to_local, save_blob_to_local
from api_utils.utils_ext.function_calling_orchestrator import should_skip_tool_injection
from logging_utils import set_request_id
from models import Message

if TYPE_CHECKING:
    from api_utils.utils_ext.function_calling_orchestrator import FunctionCallingState


def prepare_combined_prompt(
    messages: List[Message],
    req_id: str,
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
    fc_state: Optional["FunctionCallingState"] = None,
) -> Tuple[str, List[str]]:
    """Prepare combined prompt"""
    logger = logging.getLogger("AIStudioProxyServer")
    set_request_id(req_id)

    # Track summary stats for consolidated logging
    _has_system_prompt = False
    _msg_count = len(messages)
    # Do not clear upload_files here; it is cleared by the upper layer at the start of each request as needed
    # to avoid "file not found" errors caused by loss of historical attachments.

    combined_parts: List[str] = []
    system_prompt_content: Optional[str] = None
    processed_system_message_indices: Set[int] = set()
    files_list: List[
        str
    ] = []  # Collect local file paths to be uploaded (images, videos, PDFs, etc.)

    # If available tools are declared, inject the tool catalog before the prompt to help the model know available functions
    # Skip injection when using native function calling mode (tools configured via UI)
    # Pass fc_state to handle AUTO mode fallback correctly
    if isinstance(tools, list) and len(tools) > 0:
        if should_skip_tool_injection(tools, fc_state=fc_state):
            logger.debug(
                f"[{req_id}] Skipping tool catalog injection - native mode active and configured"
            )
        else:
            try:
                tool_lines: List[str] = ["Available Tools Catalog:"]
                for t in tools:
                    name: Optional[str] = None
                    params_schema: Optional[Dict[str, Any]] = None
                    # t is Dict[str, Any] from List[Dict[str, Any]]
                    fn_val: Any = t.get("function") if "function" in t else t
                    if isinstance(fn_val, dict):
                        # Type narrowed: fn_val is dict
                        typed_fn: Dict[str, Any] = cast(Dict[str, Any], fn_val)
                        name_raw: Any = typed_fn.get("name") or t.get("name")
                        if isinstance(name_raw, str):
                            name = name_raw
                        params_raw: Any = typed_fn.get("parameters")
                        if isinstance(params_raw, dict):
                            params_schema = cast(Dict[str, Any], params_raw)
                    else:
                        # fn_val is not dict, get name directly from t
                        name_raw: Any = t.get("name")
                        if isinstance(name_raw, str):
                            name = name_raw
                    if name:
                        tool_lines.append(f"- Function: {name}")
                        if params_schema:
                            try:
                                tool_lines.append(
                                    f"  Parameter Schema: {json.dumps(params_schema, ensure_ascii=False)}"
                                )
                            except Exception:
                                pass
                if tool_choice:
                    # Explicitly request or suggest callable function name
                    chosen_name: Optional[str] = None
                    if isinstance(tool_choice, dict):
                        # Type narrowed to dict by isinstance
                        typed_tool_choice: Dict[str, Any] = tool_choice
                        fn_val: Any = typed_tool_choice.get("function")
                        if isinstance(fn_val, dict):
                            # Standard format: {"type": "function", "function": {"name": "..."}}
                            typed_fn: Dict[str, Any] = cast(Dict[str, Any], fn_val)
                            name_raw: Any = typed_fn.get("name")
                            if isinstance(name_raw, str):
                                chosen_name = name_raw
                        elif "name" in typed_tool_choice:
                            # Flat format: {"type": "function", "name": "..."}
                            name_raw = typed_tool_choice.get("name")
                            if isinstance(name_raw, str):
                                chosen_name = name_raw
                    elif tool_choice.lower() not in (
                        "auto",
                        "none",
                        "no",
                        "off",
                        "required",
                        "any",
                    ):
                        chosen_name = tool_choice
                    if chosen_name:
                        tool_lines.append(f"Recommended function to use: {chosen_name}")
                combined_parts.append("\n".join(tool_lines) + "\n---\n")
            except Exception:
                pass

    # Process system messages
    for i, msg in enumerate(messages):
        if msg.role == "system":
            content = msg.content
            if isinstance(content, str) and content.strip():
                system_prompt_content = content.strip()
                processed_system_message_indices.add(i)
                _has_system_prompt = True
                logger.debug(
                    f"Found system prompt at index {i}: {system_prompt_content[:80]}..."
                )
                system_instr_prefix = "System Instructions:\n"
                combined_parts.append(f"{system_instr_prefix}{system_prompt_content}")
            else:
                logger.debug(f"Ignoring empty system message at index {i}")
                processed_system_message_indices.add(i)
            break

    role_map_ui = {
        "user": "User",
        "assistant": "Assistant",
        "system": "System",
        "tool": "Tool",
    }
    turn_separator = "\n---\n"

    # Process other messages
    for i, msg in enumerate(messages):
        if i in processed_system_message_indices:
            continue

        if msg.role == "system":
            logger.debug(f"Skipping subsequent system message at index {i}")
            continue

        if combined_parts:
            combined_parts.append(turn_separator)

        role = msg.role or "unknown"
        role_prefix_ui = f"{role_map_ui.get(role, role.capitalize())}:\n"
        current_turn_parts: List[str] = [role_prefix_ui]

        content = msg.content or ""
        content_str: str = ""

        if isinstance(content, str):
            content_str = content.strip()
        elif isinstance(content, list):
            # Process multimodal content
            text_parts: List[str] = []
            for item in content:
                # Get item type
                item_type: Optional[str] = None
                try:
                    # Guard against property exceptions when using hasattr/getattr
                    if hasattr(item, "type"):
                        item_type = item.type
                except Exception:
                    item_type = None

                if item_type is None and isinstance(item, dict):
                    typed_item: Dict[str, Any] = cast(Dict[str, Any], item)
                    item_type_raw: Any = typed_item.get("type")
                    if isinstance(item_type_raw, str):
                        item_type = item_type_raw

                if item_type == "text":
                    # Text item
                    if hasattr(item, "text"):
                        text_parts.append(getattr(item, "text", "") or "")
                    elif isinstance(item, dict):
                        typed_item: Dict[str, Any] = cast(Dict[str, Any], item)
                        text_raw: Any = typed_item.get("text", "")
                        text_parts.append(str(text_raw))
                    continue

                # Image/File/Media URL item
                if item_type in (
                    "image_url",
                    "file_url",
                    "media_url",
                    "input_image",
                ) or (
                    isinstance(item, dict)
                    and (
                        "image_url" in item
                        or "input_image" in item
                        or "file_url" in item
                        or "media_url" in item
                        or "url" in item
                    )
                ):
                    try:
                        url_value: Optional[str] = None
                        # Pydantic object attributes
                        if hasattr(item, "image_url") and item.image_url:
                            url_value = item.image_url.url
                            try:
                                detail_val: Optional[str] = getattr(
                                    item.image_url, "detail", None
                                )
                                if detail_val:
                                    text_parts.append(
                                        f"[Image Details: detail={detail_val}]"
                                    )
                            except Exception:
                                pass
                        elif hasattr(item, "input_image") and item.input_image:
                            url_value = item.input_image.url
                            try:
                                detail_val: Optional[str] = getattr(
                                    item.input_image, "detail", None
                                )
                                if detail_val:
                                    text_parts.append(
                                        f"[Image Details: detail={detail_val}]"
                                    )
                            except Exception:
                                pass
                        elif hasattr(item, "file_url") and item.file_url:
                            url_value = item.file_url.url
                        elif hasattr(item, "media_url") and item.media_url:
                            url_value = item.media_url.url
                        elif hasattr(item, "url") and item.url:
                            url_value = item.url
                        # Dictionary structure (backwards compatibility)
                        if url_value is None and isinstance(item, dict):
                            typed_item: Dict[str, Any] = cast(Dict[str, Any], item)
                            image_url_raw: Any = typed_item.get("image_url")
                            input_image_raw: Any = typed_item.get("input_image")

                            if isinstance(image_url_raw, dict):
                                typed_img_url: Dict[str, Any] = cast(
                                    Dict[str, Any], image_url_raw
                                )
                                url_raw: Any = typed_img_url.get("url")
                                if isinstance(url_raw, str):
                                    url_value = url_raw
                                detail_raw: Any = typed_img_url.get("detail")
                                if isinstance(detail_raw, str):
                                    text_parts.append(
                                        f"[Image Details: detail={detail_raw}]"
                                    )
                            elif isinstance(image_url_raw, str):
                                url_value = image_url_raw
                            elif isinstance(input_image_raw, dict):
                                typed_input_img: Dict[str, Any] = cast(
                                    Dict[str, Any], input_image_raw
                                )
                                url_raw: Any = typed_input_img.get("url")
                                if isinstance(url_raw, str):
                                    url_value = url_raw
                                detail_raw: Any = typed_input_img.get("detail")
                                if isinstance(detail_raw, str):
                                    text_parts.append(
                                        f"[Image Details: detail={detail_raw}]"
                                    )
                            elif isinstance(input_image_raw, str):
                                url_value = input_image_raw
                            else:
                                # Check other URL fields
                                file_url_raw: Any = typed_item.get("file_url")
                                media_url_raw: Any = typed_item.get("media_url")
                                file_raw: Any = typed_item.get("file")

                                if isinstance(file_url_raw, dict):
                                    typed_file_url: Dict[str, Any] = cast(
                                        Dict[str, Any], file_url_raw
                                    )
                                    url_raw: Any = typed_file_url.get("url")
                                    if isinstance(url_raw, str):
                                        url_value = url_raw
                                elif isinstance(file_url_raw, str):
                                    url_value = file_url_raw
                                elif isinstance(media_url_raw, dict):
                                    typed_media_url: Dict[str, Any] = cast(
                                        Dict[str, Any], media_url_raw
                                    )
                                    url_raw: Any = typed_media_url.get("url")
                                    if isinstance(url_raw, str):
                                        url_value = url_raw
                                elif isinstance(media_url_raw, str):
                                    url_value = media_url_raw
                                elif "url" in typed_item:
                                    url_raw: Any = typed_item.get("url")
                                    if isinstance(url_raw, str):
                                        url_value = url_raw
                                elif isinstance(file_raw, dict):
                                    # Compatible with general file field
                                    typed_file: Dict[str, Any] = cast(
                                        Dict[str, Any], file_raw
                                    )
                                    url_raw: Any = typed_file.get(
                                        "url"
                                    ) or typed_file.get("path")
                                    if isinstance(url_raw, str):
                                        url_value = url_raw

                        url_value = (url_value or "").strip()
                        if not url_value:
                            continue

                        # Normalize to local file list and log
                        if url_value.startswith("data:"):
                            file_path = extract_data_url_to_local(
                                url_value, req_id=req_id
                            )
                            if file_path:
                                files_list.append(file_path)
                                logger.debug(
                                    f"(Prepare Prompt) Identified and added data:URL attachment: {file_path}"
                                )
                        elif url_value.startswith("file:"):
                            parsed = urlparse(url_value)
                            local_path = unquote(parsed.path)
                            if os.path.exists(local_path):
                                files_list.append(local_path)
                                logger.debug(
                                    f"(Prepare Prompt) Identified and added local attachment (file://): {local_path}"
                                )
                            else:
                                logger.warning(
                                    f"(Prepare Prompt) Local file pointed to by file URL does not exist: {local_path}"
                                )
                        elif os.path.isabs(url_value) and os.path.exists(url_value):
                            files_list.append(url_value)
                            logger.debug(
                                f"(Prepare Prompt) Identified and added local attachment (absolute path): {url_value}"
                            )
                        else:
                            logger.debug(
                                f"(Prepare Prompt) Ignoring non-local attachment URL: {url_value}"
                            )
                    except Exception as e:
                        logger.warning(
                            f"(Prepare Prompt) Error processing attachment URL: {e}"
                        )
                    continue

                # Audio/Video input
                if item_type in ("input_audio", "input_video"):
                    try:
                        inp: Any = None
                        if hasattr(item, "input_audio") and item.input_audio:
                            inp = item.input_audio
                        elif hasattr(item, "input_video") and item.input_video:
                            inp = item.input_video
                        elif isinstance(item, dict):
                            typed_item: Dict[str, Any] = cast(Dict[str, Any], item)
                            inp = typed_item.get("input_audio") or typed_item.get(
                                "input_video"
                            )

                        if inp:
                            url_value: Optional[str] = None
                            data_val: Optional[str] = None
                            mime_val: Optional[str] = None
                            fmt_val: Optional[str] = None
                            if isinstance(inp, dict):
                                typed_inp: Dict[str, Any] = cast(Dict[str, Any], inp)
                                url_raw: Any = typed_inp.get("url")
                                if isinstance(url_raw, str):
                                    url_value = url_raw
                                data_raw: Any = typed_inp.get("data")
                                if isinstance(data_raw, str):
                                    data_val = data_raw
                                mime_raw: Any = typed_inp.get("mime_type")
                                if isinstance(mime_raw, str):
                                    mime_val = mime_raw
                                fmt_raw: Any = typed_inp.get("format")
                                if isinstance(fmt_raw, str):
                                    fmt_val = fmt_raw
                            else:
                                # Pydantic model or object with attributes
                                url_attr: Any = getattr(inp, "url", None)
                                if isinstance(url_attr, str):
                                    url_value = url_attr
                                data_attr: Any = getattr(inp, "data", None)
                                if isinstance(data_attr, str):
                                    data_val = data_attr
                                mime_attr: Any = getattr(inp, "mime_type", None)
                                if isinstance(mime_attr, str):
                                    mime_val = mime_attr
                                fmt_attr: Any = getattr(inp, "format", None)
                                if isinstance(fmt_attr, str):
                                    fmt_val = fmt_attr

                            if url_value:
                                if url_value.startswith("data:"):
                                    saved = extract_data_url_to_local(
                                        url_value, req_id=req_id
                                    )
                                    if saved:
                                        files_list.append(saved)
                                        logger.debug(
                                            f"(Prepare Prompt) Identified and added audio/video data:URL attachment: {saved}"
                                        )
                                elif url_value.startswith("file:"):
                                    parsed = urlparse(url_value)
                                    local_path = unquote(parsed.path)
                                    if os.path.exists(local_path):
                                        files_list.append(local_path)
                                        logger.debug(
                                            f"(Prepare Prompt) Identified and added local audio/video attachment (file://): {local_path}"
                                        )
                                elif os.path.isabs(url_value) and os.path.exists(
                                    url_value
                                ):
                                    files_list.append(url_value)
                                    logger.debug(
                                        f"(Prepare Prompt) Identified and added local audio/video attachment (absolute path): {url_value}"
                                    )
                            elif data_val:
                                if isinstance(data_val, str) and data_val.startswith(
                                    "data:"
                                ):
                                    saved = extract_data_url_to_local(
                                        data_val, req_id=req_id
                                    )
                                    if saved:
                                        files_list.append(saved)
                                        logger.debug(
                                            f"(Prepare Prompt) Identified and added audio/video data:URL attachment: {saved}"
                                        )
                                else:
                                    # Treat as pure base64 data
                                    try:
                                        raw = base64.b64decode(data_val)
                                        saved = save_blob_to_local(
                                            raw, mime_val, fmt_val, req_id=req_id
                                        )
                                        if saved:
                                            files_list.append(saved)
                                            logger.debug(
                                                f"(Prepare Prompt) Identified and added audio/video base64 attachment: {saved}"
                                            )
                                    except Exception:
                                        pass
                    except Exception as e:
                        logger.warning(
                            f"(Prepare Prompt) Error processing audio/video input: {e}"
                        )
                    continue

                # Other unknown items: log without affecting
                logger.warning(
                    f"(Prepare Prompt) Warning: Ignoring non-text or unknown type content item in message at index {i}"
                )
            content_str = "\n".join(text_parts).strip()
        elif isinstance(content, dict):
            # Compatible with dictionary format content, may contain 'attachments'/'images'/'media'/'files'
            typed_content: Dict[str, Any] = cast(Dict[str, Any], content)
            text_parts = []
            attachments_keys = ["attachments", "images", "media", "files"]
            for key in attachments_keys:
                items: Any = typed_content.get(key)
                if isinstance(items, list):
                    for it in items:
                        url_value: Optional[str] = None
                        if isinstance(it, str):
                            url_value = it
                        elif isinstance(it, dict):
                            typed_it: Dict[str, Any] = cast(Dict[str, Any], it)
                            url_raw: Any = typed_it.get("url") or typed_it.get("path")
                            if isinstance(url_raw, str):
                                url_value = url_raw
                            if not url_value:
                                image_url_raw: Any = typed_it.get("image_url")
                                input_image_raw: Any = typed_it.get("input_image")
                                if isinstance(image_url_raw, dict):
                                    typed_img_url: Dict[str, Any] = cast(
                                        Dict[str, Any], image_url_raw
                                    )
                                    url_from_image: Any = typed_img_url.get("url")
                                    if isinstance(url_from_image, str):
                                        url_value = url_from_image
                                elif isinstance(input_image_raw, dict):
                                    typed_input_img: Dict[str, Any] = cast(
                                        Dict[str, Any], input_image_raw
                                    )
                                    url_from_input: Any = typed_input_img.get("url")
                                    if isinstance(url_from_input, str):
                                        url_value = url_from_input
                        if not url_value:
                            continue
                        url_value = url_value.strip()
                        if not url_value:
                            continue
                        if url_value.startswith("data:"):
                            fp = extract_data_url_to_local(url_value)
                            if fp:
                                files_list.append(fp)
                                logger.debug(
                                    f"(Prepare Prompt) Identified and added dict attachment data:URL: {fp}"
                                )
                        elif url_value.startswith("file:"):
                            parsed = urlparse(url_value)
                            lp = unquote(parsed.path)
                            if os.path.exists(lp):
                                files_list.append(lp)
                                logger.debug(
                                    f"(Prepare Prompt) Identified and added dict attachment file://: {lp}"
                                )
                        elif os.path.isabs(url_value) and os.path.exists(url_value):
                            files_list.append(url_value)
                            logger.debug(
                                f"(Prepare Prompt) Identified and added dict attachment absolute path: {url_value}"
                            )
                        else:
                            logger.debug(
                                f"(Prepare Prompt) Ignoring non-local URL for dict attachment: {url_value}"
                            )
            # Also append potential plain text description in dictionary
            text_field: Any = typed_content.get("text")
            if isinstance(text_field, str):
                text_parts.append(text_field)
            content_str = "\n".join(text_parts).strip()
        else:
            logger.warning(
                f"(Prepare Prompt) Warning: Unexpected content type for role {role} at index {i} ({type(content)}) or is None."
            )
            content_str = str(content or "").strip()

        if content_str:
            current_turn_parts.append(content_str)

        # Handle tool calls (visualize only, do not execute actively here to avoid conflict with client execution in conversational loop)
        tool_calls = msg.tool_calls
        if role == "assistant" and tool_calls:
            if content_str:
                current_turn_parts.append("\n")

            tool_call_visualizations = []
            for tool_call in tool_calls:
                if hasattr(tool_call, "type") and tool_call.type == "function":
                    function_call = tool_call.function
                    func_name = function_call.name if function_call else None
                    func_args_str = function_call.arguments if function_call else None

                    try:
                        parsed_args = json.loads(
                            func_args_str if func_args_str else "{}"
                        )
                        formatted_args = json.dumps(
                            parsed_args, indent=2, ensure_ascii=False
                        )
                    except (json.JSONDecodeError, TypeError):
                        formatted_args = (
                            func_args_str if func_args_str is not None else "{}"
                        )

                    tool_call_visualizations.append(
                        f"Request function call: {func_name}\nParameters:\n{formatted_args}"
                    )

            if tool_call_visualizations:
                current_turn_parts.append("\n".join(tool_call_visualizations))

        # Handle tool result messages (role = 'tool'): include in prompt so model sees tool output
        if role == "tool":
            tool_result_lines: List[str] = []
            # Standard OpenAI style: content is string, tool_call_id associates with previous call
            tool_call_id = getattr(msg, "tool_call_id", None)
            if tool_call_id:
                tool_result_lines.append(f"Tool result (tool_call_id={tool_call_id}):")
            if isinstance(msg.content, str):
                tool_result_lines.append(msg.content)
            elif isinstance(msg.content, list):
                # Compatible with few clients putting results in a list
                try:
                    merged_parts: List[str] = []
                    for it in msg.content:
                        if isinstance(it, dict):
                            if it.get("type") == "text":
                                text_raw = it.get("text", "")
                                if isinstance(text_raw, str):
                                    merged_parts.append(text_raw)
                                else:
                                    merged_parts.append(str(text_raw))
                            else:
                                merged_parts.append(str(it))
                        else:
                            merged_parts.append(str(it))
                    merged = "\n".join(merged_parts)
                    tool_result_lines.append(merged)
                except Exception:
                    tool_result_lines.append(str(msg.content))
            else:
                tool_result_lines.append(str(msg.content))
            if tool_result_lines:
                if content_str:
                    current_turn_parts.append("\n")
                current_turn_parts.append("\n".join(tool_result_lines))

        if len(current_turn_parts) > 1 or (role == "assistant" and tool_calls):
            combined_parts.append("".join(current_turn_parts))
        elif not combined_parts and not current_turn_parts:
            logger.debug(
                f"(Prepare Prompt) Skipping empty message for role {role} at index {i} (and no tool calls)."
            )
        elif len(current_turn_parts) == 1 and not combined_parts:
            logger.debug(
                f"(Prepare Prompt) Skipping empty message for role {role} at index {i} (prefix only)."
            )

    final_prompt = "".join(combined_parts)
    if final_prompt:
        final_prompt += "\n"

    # Consolidated English summary (replaces verbose Chinese logs)
    sys_indicator = "Yes" if _has_system_prompt else "No"
    attach_info = f", {len(files_list)} attachments" if files_list else ""
    logger.debug(
        f"[Prompt] Built messages: {_msg_count} (System: {sys_indicator}), "
        f"Total {len(final_prompt):,} characters{attach_info}"
    )

    return final_prompt, files_list
