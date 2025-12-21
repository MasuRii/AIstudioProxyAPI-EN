import asyncio
import json
import os
import time
from typing import Any, Dict, List, Optional, Set


def tool_get_current_time(params: Dict[str, Any]) -> Dict[str, Any]:
    return {"current_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def tool_echo(params: Dict[str, Any]) -> Dict[str, Any]:
    return {"echo": params}


def tool_sum(params: Dict[str, Any]) -> Dict[str, Any]:
    values = params.get("values")
    if isinstance(values, list):
        try:
            total = sum(float(v) for v in values)
        except Exception:
            total = None
    else:
        total = None
    return {"sum": total, "count": len(values) if isinstance(values, list) else 0}


FUNCTION_REGISTRY = {
    "get_current_time": tool_get_current_time,
    "echo": tool_echo,
    "sum": tool_sum,
}

# Runtime-allowed tool names from incoming requests (OpenAI tools array)
_ALLOWED_RUNTIME_TOOLS: Set[str] = set()
_runtime_mcp_endpoint: Optional[str] = None


def register_runtime_tools(
    tools: Optional[List[Dict[str, Any]]], mcp_endpoint: Optional[str] = None
) -> None:
    """Register tool names declared in the request as allowed.
    The server may delegate unknown tools to MCP if configured.
    """
    # Reset per-request registry to avoid leakage across requests
    global _runtime_mcp_endpoint
    _ALLOWED_RUNTIME_TOOLS.clear()
    _runtime_mcp_endpoint = None
    if not tools:
        return
    try:
        for t in tools:
            name = None
            fn = t.get("function") if "function" in t else t
            if isinstance(fn, dict):
                name = fn.get("name") or t.get("name")
            else:
                name = t.get("name")
            if name:
                _ALLOWED_RUNTIME_TOOLS.add(str(name))
            # Detect per-tool endpoint extension
            ext_ep = (
                t.get("x-mcp-endpoint")
                or t.get("x_mcp_endpoint")
                or (
                    isinstance(t.get("function"), dict)
                    and t["function"].get("x-mcp-endpoint")
                )
                or None
            )
            if ext_ep and not mcp_endpoint:
                mcp_endpoint = ext_ep
        # Capture per-request MCP endpoint if provided (explicit or via tool extension)
        if mcp_endpoint:
            _runtime_mcp_endpoint = mcp_endpoint
    except Exception:
        # be forgiving on malformed tools
        pass


async def execute_tool_call(name: str, arguments_json: str) -> str:
    """Execute registered tools and return stringified result. Unknown tools return descriptive errors.
    Fully asynchronous: built-in functions execute directly; MCP path uses async httpx client.
    """
    try:
        params = json.loads(arguments_json or "{}")
    except Exception:
        params = {}

    func = FUNCTION_REGISTRY.get(name)
    if not func:
        # If tool is not built-in but declared, try MCP adapter if configured (env or per-request)
        if name in _ALLOWED_RUNTIME_TOOLS:
            try:
                from api_utils.mcp_adapter import (
                    execute_mcp_tool,
                    execute_mcp_tool_with_endpoint,
                )

                if _runtime_mcp_endpoint:
                    return await execute_mcp_tool_with_endpoint(
                        _runtime_mcp_endpoint, name, params
                    )
                if os.environ.get("MCP_HTTP_ENDPOINT"):
                    return await execute_mcp_tool(name, params)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                return json.dumps(
                    {"error": f"MCP execution failed: {e}"}, ensure_ascii=False
                )
        return json.dumps(
            {"error": f"Unknown tool: {name}", "arguments": params}, ensure_ascii=False
        )

    try:
        result = func(params)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"Execution failed: {e}"}, ensure_ascii=False)
