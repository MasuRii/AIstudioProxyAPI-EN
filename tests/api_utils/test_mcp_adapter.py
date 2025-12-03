"""
High-quality tests for api_utils/mcp_adapter.py - MCP-over-HTTP adapter.

Focus: Test all 5 functions with success paths, error paths, edge cases.
Strategy: Mock httpx Client/AsyncClient, environment variables, test all code paths.
"""

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from api_utils.mcp_adapter import (
    _normalize_endpoint,
    execute_mcp_tool,
    execute_mcp_tool_sync,
    execute_mcp_tool_with_endpoint,
    execute_mcp_tool_with_endpoint_sync,
)


def test_normalize_endpoint_empty_string_raises():
    """
    测试场景: 空字符串端点
    预期: 抛出 RuntimeError (lines 9-10)
    """
    with pytest.raises(RuntimeError) as exc_info:
        _normalize_endpoint("")

    # 验证: 错误消息
    assert "MCP HTTP endpoint not provided" in str(exc_info.value)


def test_normalize_endpoint_no_trailing_slash():
    """
    测试场景: 正常 URL 无尾部斜杠
    预期: 原样返回 (line 11)
    """
    url = "http://localhost:8080"
    result = _normalize_endpoint(url)

    # 验证: 不变
    assert result == url


def test_normalize_endpoint_with_single_trailing_slash():
    """
    测试场景: URL 有单个尾部斜杠
    预期: 去除尾部斜杠 (line 11)
    """
    url = "http://localhost:8080/"
    result = _normalize_endpoint(url)

    # 验证: 斜杠被去除
    assert result == "http://localhost:8080"


def test_normalize_endpoint_with_multiple_trailing_slashes():
    """
    测试场景: URL 有多个尾部斜杠
    预期: 去除所有尾部斜杠 (line 11)
    """
    url = "http://localhost:8080///"
    result = _normalize_endpoint(url)

    # 验证: 所有斜杠被去除
    assert result == "http://localhost:8080"


@pytest.mark.asyncio
async def test_execute_mcp_tool_success_with_json_response():
    """
    测试场景: 成功执行 MCP 工具,返回 JSON
    预期: 返回 JSON 字符串 (lines 14-35)
    """
    tool_name = "test_tool"
    params = {"arg1": "value1", "arg2": 123}
    response_data = {"result": "success", "data": {"output": "test"}}

    with patch.dict(os.environ, {"MCP_HTTP_ENDPOINT": "http://localhost:8080"}):
        mock_response = MagicMock()
        mock_response.json.return_value = response_data
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.post.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await execute_mcp_tool(tool_name, params)

    # 验证: 返回 JSON 字符串
    assert result == json.dumps(response_data, ensure_ascii=False)

    # 验证: POST 请求参数正确 (lines 24-29)
    mock_client.post.assert_called_once()
    call_args = mock_client.post.call_args
    assert call_args[0][0] == "http://localhost:8080/tools/execute"
    assert call_args[1]["json"] == {"name": tool_name, "arguments": params}
    assert call_args[1]["headers"] == {"Content-Type": "application/json"}


@pytest.mark.asyncio
async def test_execute_mcp_tool_success_with_non_json_response():
    """
    测试场景: 成功执行但响应非 JSON
    预期: 返回 {"raw": text} 格式 (lines 31-34)
    """
    tool_name = "test_tool"
    params = {}

    with patch.dict(os.environ, {"MCP_HTTP_ENDPOINT": "http://localhost:8080"}):
        mock_response = MagicMock()
        mock_response.json.side_effect = Exception("Invalid JSON")
        mock_response.text = "Plain text response"
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.post.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await execute_mcp_tool(tool_name, params)

    # 验证: 返回包装后的文本
    expected = json.dumps({"raw": "Plain text response"}, ensure_ascii=False)
    assert result == expected


@pytest.mark.asyncio
async def test_execute_mcp_tool_missing_endpoint_env():
    """
    测试场景: MCP_HTTP_ENDPOINT 未配置
    预期: 抛出 RuntimeError (lines 22-23)
    """
    tool_name = "test_tool"
    params = {}

    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(RuntimeError) as exc_info:
            await execute_mcp_tool(tool_name, params)

    # 验证: 错误消息
    assert "MCP_HTTP_ENDPOINT not configured" in str(exc_info.value)


@pytest.mark.asyncio
async def test_execute_mcp_tool_http_error():
    """
    测试场景: HTTP 请求失败 (非 2xx 状态)
    预期: 抛出 HTTPStatusError (line 30)
    """
    tool_name = "test_tool"
    params = {}

    with patch.dict(os.environ, {"MCP_HTTP_ENDPOINT": "http://localhost:8080"}):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500 Server Error", request=MagicMock(), response=MagicMock()
        )

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.post.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(httpx.HTTPStatusError):
                await execute_mcp_tool(tool_name, params)


@pytest.mark.asyncio
async def test_execute_mcp_tool_custom_timeout():
    """
    测试场景: 自定义超时时间 (MCP_HTTP_TIMEOUT)
    预期: 使用自定义超时创建客户端 (line 27-28)
    """
    tool_name = "test_tool"
    params = {}
    custom_timeout = "30"

    with patch.dict(
        os.environ,
        {
            "MCP_HTTP_ENDPOINT": "http://localhost:8080",
            "MCP_HTTP_TIMEOUT": custom_timeout,
        },
    ):
        mock_response = MagicMock()
        mock_response.json.return_value = {"result": "ok"}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.post.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client) as mock_async_client:
            await execute_mcp_tool(tool_name, params)

        # 验证: AsyncClient 使用自定义超时
        mock_async_client.assert_called_once_with(timeout=30.0)


@pytest.mark.asyncio
async def test_execute_mcp_tool_with_endpoint_success():
    """
    测试场景: 成功执行 (使用显式端点)
    预期: 返回 JSON 字符串 (lines 38-52)
    """
    endpoint = "http://custom-endpoint:9000"
    tool_name = "custom_tool"
    params = {"key": "value"}
    response_data = {"status": "done"}

    mock_response = MagicMock()
    mock_response.json.return_value = response_data
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mock_client.post.return_value = mock_response

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await execute_mcp_tool_with_endpoint(endpoint, tool_name, params)

    # 验证: 返回 JSON 字符串
    assert result == json.dumps(response_data, ensure_ascii=False)

    # 验证: 使用正确的 URL (line 41)
    mock_client.post.assert_called_once()
    call_args = mock_client.post.call_args
    assert call_args[0][0] == "http://custom-endpoint:9000/tools/execute"


@pytest.mark.asyncio
async def test_execute_mcp_tool_with_endpoint_empty_endpoint_raises():
    """
    测试场景: 空端点字符串
    预期: _normalize_endpoint 抛出 RuntimeError (line 41 调用)
    """
    endpoint = ""
    tool_name = "test_tool"
    params = {}

    with pytest.raises(RuntimeError) as exc_info:
        await execute_mcp_tool_with_endpoint(endpoint, tool_name, params)

    # 验证: 错误来自 _normalize_endpoint
    assert "MCP HTTP endpoint not provided" in str(exc_info.value)


@pytest.mark.asyncio
async def test_execute_mcp_tool_with_endpoint_non_json_response():
    """
    测试场景: 使用显式端点执行,响应非 JSON
    预期: 返回 {"raw": text} 格式 (lines 50-51)
    """
    endpoint = "http://custom-endpoint:9000"
    tool_name = "custom_tool"
    params = {"key": "value"}

    mock_response = MagicMock()
    mock_response.json.side_effect = ValueError("Invalid JSON")
    mock_response.text = "Non-JSON custom response"
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mock_client.post.return_value = mock_response

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await execute_mcp_tool_with_endpoint(endpoint, tool_name, params)

    # 验证: 返回包装后的文本 (lines 50-51)
    expected = json.dumps({"raw": "Non-JSON custom response"}, ensure_ascii=False)
    assert result == expected


def test_execute_mcp_tool_sync_success_with_json_response():
    """
    测试场景: 同步执行成功,返回 JSON
    预期: 返回 JSON 字符串 (lines 56-71)
    """
    tool_name = "sync_tool"
    params = {"param": "value"}
    response_data = {"sync": "result"}

    with patch.dict(os.environ, {"MCP_HTTP_ENDPOINT": "http://localhost:8080"}):
        mock_response = MagicMock()
        mock_response.json.return_value = response_data
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = None
        mock_client.post.return_value = mock_response

        with patch("httpx.Client", return_value=mock_client):
            result = execute_mcp_tool_sync(tool_name, params)

    # 验证: 返回 JSON 字符串
    assert result == json.dumps(response_data, ensure_ascii=False)

    # 验证: POST 请求参数正确 (lines 60-66)
    mock_client.post.assert_called_once()
    call_args = mock_client.post.call_args
    assert call_args[0][0] == "http://localhost:8080/tools/execute"
    assert call_args[1]["json"] == {"name": tool_name, "arguments": params}


def test_execute_mcp_tool_sync_success_with_non_json_response():
    """
    测试场景: 同步执行成功但响应非 JSON
    预期: 返回 {"raw": text} 格式 (lines 67-70)
    """
    tool_name = "sync_tool"
    params = {}

    with patch.dict(os.environ, {"MCP_HTTP_ENDPOINT": "http://localhost:8080"}):
        mock_response = MagicMock()
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_response.text = "Sync text response"
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = None
        mock_client.post.return_value = mock_response

        with patch("httpx.Client", return_value=mock_client):
            result = execute_mcp_tool_sync(tool_name, params)

    # 验证: 返回包装后的文本
    expected = json.dumps({"raw": "Sync text response"}, ensure_ascii=False)
    assert result == expected


def test_execute_mcp_tool_sync_missing_endpoint_env():
    """
    测试场景: 同步版本 MCP_HTTP_ENDPOINT 未配置
    预期: 抛出 RuntimeError (lines 57-59)
    """
    tool_name = "sync_tool"
    params = {}

    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(RuntimeError) as exc_info:
            execute_mcp_tool_sync(tool_name, params)

    # 验证: 错误消息
    assert "MCP_HTTP_ENDPOINT not configured" in str(exc_info.value)


def test_execute_mcp_tool_sync_http_error():
    """
    测试场景: 同步版本 HTTP 请求失败
    预期: 抛出 HTTPStatusError (line 66)
    """
    tool_name = "sync_tool"
    params = {}

    with patch.dict(os.environ, {"MCP_HTTP_ENDPOINT": "http://localhost:8080"}):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404 Not Found", request=MagicMock(), response=MagicMock()
        )

        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = None
        mock_client.post.return_value = mock_response

        with patch("httpx.Client", return_value=mock_client):
            with pytest.raises(httpx.HTTPStatusError):
                execute_mcp_tool_sync(tool_name, params)


def test_execute_mcp_tool_sync_custom_timeout():
    """
    测试场景: 同步版本使用自定义超时
    预期: 使用自定义超时创建客户端 (lines 63-64)
    """
    tool_name = "sync_tool"
    params = {}
    custom_timeout = "45"

    with patch.dict(
        os.environ,
        {
            "MCP_HTTP_ENDPOINT": "http://localhost:8080",
            "MCP_HTTP_TIMEOUT": custom_timeout,
        },
    ):
        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": True}
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = None
        mock_client.post.return_value = mock_response

        with patch("httpx.Client", return_value=mock_client) as mock_sync_client:
            execute_mcp_tool_sync(tool_name, params)

        # 验证: Client 使用自定义超时
        mock_sync_client.assert_called_once_with(timeout=45.0)


def test_execute_mcp_tool_with_endpoint_sync_success():
    """
    测试场景: 同步版本使用显式端点成功
    预期: 返回 JSON 字符串 (lines 74-88)
    """
    endpoint = "http://sync-endpoint:7000"
    tool_name = "sync_custom_tool"
    params = {"foo": "bar"}
    response_data = {"sync_result": "ok"}

    mock_response = MagicMock()
    mock_response.json.return_value = response_data
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = None
    mock_client.post.return_value = mock_response

    with patch("httpx.Client", return_value=mock_client):
        result = execute_mcp_tool_with_endpoint_sync(endpoint, tool_name, params)

    # 验证: 返回 JSON 字符串
    assert result == json.dumps(response_data, ensure_ascii=False)

    # 验证: 使用正确的 URL (line 77)
    mock_client.post.assert_called_once()
    call_args = mock_client.post.call_args
    assert call_args[0][0] == "http://sync-endpoint:7000/tools/execute"


def test_execute_mcp_tool_with_endpoint_sync_empty_endpoint_raises():
    """
    测试场景: 同步版本空端点字符串
    预期: _normalize_endpoint 抛出 RuntimeError (line 77 调用)
    """
    endpoint = ""
    tool_name = "sync_tool"
    params = {}

    with pytest.raises(RuntimeError) as exc_info:
        execute_mcp_tool_with_endpoint_sync(endpoint, tool_name, params)

    # 验证: 错误来自 _normalize_endpoint
    assert "MCP HTTP endpoint not provided" in str(exc_info.value)


def test_execute_mcp_tool_with_endpoint_sync_non_json_response():
    """
    测试场景: 同步版本显式端点,非 JSON 响应
    预期: 返回 {"raw": text} 格式 (lines 84-87)
    """
    endpoint = "http://sync-endpoint:7000"
    tool_name = "sync_tool"
    params = {}

    mock_response = MagicMock()
    mock_response.json.side_effect = json.JSONDecodeError("Expecting value", "", 0)
    mock_response.text = "Non-JSON sync response"
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = None
    mock_client.post.return_value = mock_response

    with patch("httpx.Client", return_value=mock_client):
        result = execute_mcp_tool_with_endpoint_sync(endpoint, tool_name, params)

    # 验证: 返回包装后的文本
    expected = json.dumps({"raw": "Non-JSON sync response"}, ensure_ascii=False)
    assert result == expected
