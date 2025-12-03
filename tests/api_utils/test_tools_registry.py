import json
import os
from typing import Any, Dict, List, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import api_utils.tools_registry
from api_utils.tools_registry import (
    execute_tool_call,
    register_runtime_tools,
    tool_echo,
    tool_get_current_time,
    tool_sum,
)


@pytest.fixture(autouse=True)
def cleanup_registry():
    """Reset the registry state before and after each test."""
    api_utils.tools_registry._ALLOWED_RUNTIME_TOOLS.clear()
    api_utils.tools_registry._runtime_mcp_endpoint = None
    yield
    api_utils.tools_registry._ALLOWED_RUNTIME_TOOLS.clear()
    api_utils.tools_registry._runtime_mcp_endpoint = None


def test_tool_get_current_time():
    """Test get_current_time tool returns formatted timestamp."""
    result = tool_get_current_time({})
    assert "current_time" in result
    # Basic format check
    assert result["current_time"]


def test_tool_echo():
    """Test echo tool returns input parameters."""
    params = {"key": "value"}
    result = tool_echo(params)
    assert result["echo"] == params


def test_tool_sum():
    """Test sum tool handles valid, invalid, and missing values."""
    # Valid sum
    result = tool_sum({"values": [1, 2, 3]})
    assert result["sum"] == 6.0
    assert result["count"] == 3

    # Invalid values (non-numeric)
    result = tool_sum({"values": ["a", "b"]})
    assert result["sum"] is None
    assert result["count"] == 2

    # Not a list
    result = tool_sum({"values": "not a list"})
    assert result["sum"] is None
    assert result["count"] == 0

    # Missing key
    result = tool_sum({})
    assert result["sum"] is None
    assert result["count"] == 0


def test_register_runtime_tools_basic():
    """Test registering runtime tools with function and name fields."""
    tools = [{"function": {"name": "tool1"}}, {"name": "tool2"}]
    register_runtime_tools(tools)
    assert "tool1" in api_utils.tools_registry._ALLOWED_RUNTIME_TOOLS
    assert "tool2" in api_utils.tools_registry._ALLOWED_RUNTIME_TOOLS


def test_register_runtime_tools_empty():
    """Test registering empty or None tool lists."""
    register_runtime_tools([])
    assert len(api_utils.tools_registry._ALLOWED_RUNTIME_TOOLS) == 0

    register_runtime_tools(None)
    assert len(api_utils.tools_registry._ALLOWED_RUNTIME_TOOLS) == 0


def test_register_runtime_tools_malformed():
    """Test registering malformed tool definitions doesn't crash."""
    # Should not crash
    register_runtime_tools(cast(List[Dict[str, Any]], ["not a dict"]))
    # Should handle partially malformed
    register_runtime_tools([{"no_name": "foo"}])


def test_register_runtime_tools_mcp_endpoint():
    """Test MCP endpoint registration via argument and tool extensions."""
    # Via argument - needs at least one tool to process
    register_runtime_tools([{"name": "dummy"}], mcp_endpoint="http://mcp")
    assert api_utils.tools_registry._runtime_mcp_endpoint == "http://mcp"

    # Reset
    register_runtime_tools([])
    assert api_utils.tools_registry._runtime_mcp_endpoint is None

    # Via tool extension
    tools = [{"function": {"name": "mcp_tool", "x-mcp-endpoint": "http://tool-mcp"}}]
    register_runtime_tools(tools)
    assert "mcp_tool" in api_utils.tools_registry._ALLOWED_RUNTIME_TOOLS
    assert api_utils.tools_registry._runtime_mcp_endpoint == "http://tool-mcp"

    # Top level x-mcp-endpoint
    tools = [{"name": "mcp_tool_2", "x_mcp_endpoint": "http://tool-mcp-2"}]
    register_runtime_tools(tools)
    assert api_utils.tools_registry._runtime_mcp_endpoint == "http://tool-mcp-2"


def test_register_runtime_tools_exceptions():
    """Test exception handling during tool registration."""
    # Test line 55: function is not a dict
    tools = [{"function": "not_a_dict", "name": "tool_weird"}]
    register_runtime_tools(tools)
    assert "tool_weird" in api_utils.tools_registry._ALLOWED_RUNTIME_TOOLS

    # Test line 72-74: Exception handling (e.g. tools is not iterable but truthy)
    register_runtime_tools(
        cast(List[Dict[str, Any]], 123)
    )  # raises TypeError, caught by except
    # Should safely pass without error

    # Exception during iteration
    class BadTools:
        def __iter__(self):
            raise ValueError("Bad")

    register_runtime_tools(cast(List[Dict[str, Any]], BadTools()))


@pytest.mark.asyncio
async def test_execute_tool_call_builtin():
    # Echo
    args = json.dumps({"msg": "hello"})
    result = await execute_tool_call("echo", args)
    data = json.loads(result)
    assert data["echo"] == {"msg": "hello"}

    # Sum
    args = json.dumps({"values": [10, 20]})
    result = await execute_tool_call("sum", args)
    data = json.loads(result)
    assert data["sum"] == 30.0


@pytest.mark.asyncio
async def test_execute_tool_call_invalid_json():
    # Should fallback to empty dict
    result = await execute_tool_call("echo", "{invalid")
    data = json.loads(result)
    assert data["echo"] == {}


@pytest.mark.asyncio
async def test_execute_tool_call_unknown():
    result = await execute_tool_call("unknown_tool", "{}")
    data = json.loads(result)
    assert "error" in data
    assert "Unknown tool" in data["error"]


@pytest.mark.asyncio
async def test_execute_tool_call_exception():
    # Mock a builtin tool raising exception
    with patch.dict(
        api_utils.tools_registry.FUNCTION_REGISTRY,
        {"fail": MagicMock(side_effect=Exception("Boom"))},
    ):
        result = await execute_tool_call("fail", "{}")
        data = json.loads(result)
        assert "error" in data
        assert "Execution failed" in data["error"]


@pytest.mark.asyncio
async def test_execute_tool_call_mcp_runtime():
    # Setup runtime tool
    api_utils.tools_registry._ALLOWED_RUNTIME_TOOLS.add("mcp_tool")
    api_utils.tools_registry._runtime_mcp_endpoint = "http://runtime-mcp"

    mock_mcp = AsyncMock(return_value=json.dumps({"result": "mcp_ok"}))
    mcp_adapter_mock = MagicMock()
    mcp_adapter_mock.execute_mcp_tool_with_endpoint = mock_mcp

    with patch.dict("sys.modules", {"api_utils.mcp_adapter": mcp_adapter_mock}):
        result = await execute_tool_call("mcp_tool", '{"a": 1}')
        assert result == json.dumps({"result": "mcp_ok"})
        mock_mcp.assert_awaited_with("http://runtime-mcp", "mcp_tool", {"a": 1})


@pytest.mark.asyncio
async def test_execute_tool_call_mcp_env():
    # Setup runtime tool allowed, but no runtime endpoint, fallback to env
    api_utils.tools_registry._ALLOWED_RUNTIME_TOOLS.add("mcp_env_tool")
    api_utils.tools_registry._runtime_mcp_endpoint = None

    with patch.dict(os.environ, {"MCP_HTTP_ENDPOINT": "http://env-mcp"}):
        mock_mcp = AsyncMock(return_value=json.dumps({"result": "env_ok"}))
        mcp_adapter_mock = MagicMock()
        mcp_adapter_mock.execute_mcp_tool = mock_mcp
        # We also need execute_mcp_tool_with_endpoint to be present to avoid import error
        mcp_adapter_mock.execute_mcp_tool_with_endpoint = AsyncMock()

        with patch.dict("sys.modules", {"api_utils.mcp_adapter": mcp_adapter_mock}):
            result = await execute_tool_call("mcp_env_tool", '{"b": 2}')
            assert result == json.dumps({"result": "env_ok"})
            mock_mcp.assert_awaited_with("mcp_env_tool", {"b": 2})


@pytest.mark.asyncio
async def test_execute_tool_call_mcp_fail():
    api_utils.tools_registry._ALLOWED_RUNTIME_TOOLS.add("fail_tool")
    api_utils.tools_registry._runtime_mcp_endpoint = "http://fail"

    mcp_adapter_mock = MagicMock()
    mcp_adapter_mock.execute_mcp_tool_with_endpoint = AsyncMock(
        side_effect=Exception("MCP Down")
    )

    with patch.dict("sys.modules", {"api_utils.mcp_adapter": mcp_adapter_mock}):
        result = await execute_tool_call("fail_tool", "{}")
        data = json.loads(result)
        assert "error" in data
        assert "MCP execution failed" in data["error"]
