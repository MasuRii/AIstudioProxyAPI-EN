import asyncio
from typing import Any, Dict, List, Optional, Union

from api_utils.tools_registry import execute_tool_call, register_runtime_tools
from api_utils.utils_ext.string_utils import (
    extract_json_from_text,
    get_latest_user_text,
)
from models import Message


async def maybe_execute_tools(
    messages: List[Message],
    tools: Optional[List[Dict[str, Any]]],
    tool_choice: Optional[Union[str, Dict[str, Any]]],
) -> Optional[List[Dict[str, Any]]]:
    """
    Active function execution based on tools/tool_choice:
    - If tool_choice specifies a function name (string or {type:'function', function:{name}}), attempt to execute that function.
    - If tool_choice is 'auto' and only one tool is provided, execute that tool.
    - Argument source: Attempt to extract JSON from the text of the most recent user message; if fails, use empty parameters.
    - Returns [{name, arguments, result}]; returns None if no executable is found.
    """
    try:
        # Track runtime-declared tools and optional MCP endpoints
        mcp_ep: Optional[str] = None
        # support per-request MCP endpoint via request-level message or tool spec extension (if present later)
        # current: read from env only in registry when not provided
        register_runtime_tools(tools, mcp_ep)
        # If tool result messages already exist (role='tool'), follow the conversational calling loop,
        # driven by the client, the server does not actively execute again.
        for m in messages:
            if getattr(m, "role", None) == "tool":
                return None
        chosen_name: Optional[str] = None
        if isinstance(tool_choice, dict):
            fn_raw = tool_choice.get("function")
            if isinstance(fn_raw, dict):
                name_raw = fn_raw.get("name")
                if isinstance(name_raw, str):
                    chosen_name = name_raw
        elif isinstance(tool_choice, str):
            lc = tool_choice.lower()
            if lc in ("none", "no", "off"):
                return None
            if lc in ("auto", "required", "any"):
                if isinstance(tools, list) and len(tools) == 1:
                    first_tool = tools[0]
                    func_raw = first_tool.get("function", {})
                    if isinstance(func_raw, dict):
                        name_from_func = func_raw.get("name")
                        if isinstance(name_from_func, str):
                            chosen_name = name_from_func
                    if not chosen_name:
                        name_from_tool = first_tool.get("name")
                        if isinstance(name_from_tool, str):
                            chosen_name = name_from_tool
            else:
                chosen_name = tool_choice
        elif tool_choice is None:
            # Do not execute actively
            return None

        if not chosen_name:
            return None

        user_text = get_latest_user_text(messages)
        args_json = extract_json_from_text(user_text) or "{}"
        result_str = await execute_tool_call(chosen_name, args_json)
        return [{"name": chosen_name, "arguments": args_json, "result": result_str}]
    except asyncio.CancelledError:
        raise
    except Exception:
        return None
