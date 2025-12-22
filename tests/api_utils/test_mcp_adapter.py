"""
High-quality tests for api_utils/mcp_adapter.py - MCP-over-HTTP adapter.

Focus: Test all functions with success paths, error paths, edge cases.
Strategy: Mock httpx AsyncClient, environment variables, test all code paths.
"""

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from api_utils.mcp_adapter import (
    _normalize_endpoint,
    execute_mcp_tool,
    execute_mcp_tool_with_endpoint,
)


class TestNormalizeEndpoint:
    """Tests for _normalize_endpoint function."""

    def test_empty_string_raises(self):
        """
        Test scenario: Empty string endpoint
        Expected: Throw RuntimeError (lines 9-10)
        """
        with pytest.raises(RuntimeError) as exc_info:
            _normalize_endpoint("")

        # Verify: Error message
        assert "MCP HTTP endpoint not provided" in str(exc_info.value)

    def test_no_trailing_slash(self):
        """
        Test scenario: Normal URL without trailing slash
        Expected: Return as is (line 11)
        """
        url = "http://localhost:8080"
        result = _normalize_endpoint(url)

        # Verify: No change
        assert result == url

    def test_with_single_trailing_slash(self):
        """
        Test scenario: URL with single trailing slash
        Expected: Remove trailing slash (line 11)
        """
        url = "http://localhost:8080/"
        result = _normalize_endpoint(url)

        # Verify: Slash removed
        assert result == "http://localhost:8080"

    def test_with_multiple_trailing_slashes(self):
        """
        Test scenario: URL with multiple trailing slashes
        Expected: Remove all trailing slashes (line 11)
        """
        url = "http://localhost:8080///"
        result = _normalize_endpoint(url)

        # Verify: All slashes removed
        assert result == "http://localhost:8080"

    def test_with_path_and_trailing_slash(self):
        """
        Test scenario: URL with path and trailing slash
        Expected: Only remove trailing slash, keep path
        """
        url = "http://localhost:8080/api/v1/"
        result = _normalize_endpoint(url)

        assert result == "http://localhost:8080/api/v1"


class TestExecuteMcpTool:
    """Tests for execute_mcp_tool async function."""

    @pytest.mark.asyncio
    async def test_success_with_json_response(self):
        """
        Test scenario: Successfully execute MCP tool, return JSON
        Expected: Return JSON string
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

        # Verify: Return JSON string
        assert result == json.dumps(response_data, ensure_ascii=False)

        # Verify: POST request parameters correct
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert call_args[0][0] == "http://localhost:8080/tools/execute"
        assert call_args[1]["json"] == {"name": tool_name, "arguments": params}
        assert call_args[1]["headers"] == {"Content-Type": "application/json"}

    @pytest.mark.asyncio
    async def test_success_with_non_json_response(self):
        """
        Test scenario: Successfully executed but non-JSON response
        Expected: Return {"raw": text} format
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

        # Verify: Return wrapped text
        expected = json.dumps({"raw": "Plain text response"}, ensure_ascii=False)
        assert result == expected

    @pytest.mark.asyncio
    async def test_missing_endpoint_env(self):
        """
        Test scenario: MCP_HTTP_ENDPOINT not configured
        Expected: Throw RuntimeError
        """
        tool_name = "test_tool"
        params = {}

        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(RuntimeError) as exc_info:
                await execute_mcp_tool(tool_name, params)

        # Verify: Error message
        assert "MCP_HTTP_ENDPOINT not configured" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_http_error(self):
        """
        Test scenario: HTTP request failed (non-2xx status)
        Expected: Throw HTTPStatusError
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
    async def test_custom_timeout(self):
        """
        Test scenario: Custom timeout (MCP_HTTP_TIMEOUT)
        Expected: Create client with custom timeout
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

            with patch(
                "httpx.AsyncClient", return_value=mock_client
            ) as mock_async_client:
                await execute_mcp_tool(tool_name, params)

            # Verify: AsyncClient uses custom timeout
            mock_async_client.assert_called_once_with(timeout=30.0)

    @pytest.mark.asyncio
    async def test_default_timeout(self):
        """
        Test scenario: Use default timeout
        Expected: Use 15.0 second timeout
        """
        tool_name = "test_tool"
        params = {}

        with patch.dict(os.environ, {"MCP_HTTP_ENDPOINT": "http://localhost:8080"}):
            mock_response = MagicMock()
            mock_response.json.return_value = {"result": "ok"}
            mock_response.raise_for_status = MagicMock()

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post.return_value = mock_response

            with patch(
                "httpx.AsyncClient", return_value=mock_client
            ) as mock_async_client:
                await execute_mcp_tool(tool_name, params)

            # Verify: AsyncClient uses default timeout
            mock_async_client.assert_called_once_with(timeout=15.0)

    @pytest.mark.asyncio
    async def test_cancelled_error_propagates(self):
        """
        Test scenario: asyncio.CancelledError occurs
        Expected: Error re-thrown, not caught
        """
        import asyncio

        tool_name = "test_tool"
        params = {}

        with patch.dict(os.environ, {"MCP_HTTP_ENDPOINT": "http://localhost:8080"}):
            mock_response = MagicMock()
            mock_response.json.side_effect = asyncio.CancelledError()
            mock_response.raise_for_status = MagicMock()

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post.return_value = mock_response

            with patch("httpx.AsyncClient", return_value=mock_client):
                with pytest.raises(asyncio.CancelledError):
                    await execute_mcp_tool(tool_name, params)


class TestExecuteMcpToolWithEndpoint:
    """Tests for execute_mcp_tool_with_endpoint async function."""

    @pytest.mark.asyncio
    async def test_success(self):
        """
        Test scenario: Successfully executed (using explicit endpoint)
        Expected: Return JSON string
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

        # Verify: Return JSON string
        assert result == json.dumps(response_data, ensure_ascii=False)

        # Verify: Use correct URL
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert call_args[0][0] == "http://custom-endpoint:9000/tools/execute"

    @pytest.mark.asyncio
    async def test_empty_endpoint_raises(self):
        """
        Test scenario: Empty endpoint string
        Expected: _normalize_endpoint throws RuntimeError
        """
        endpoint = ""
        tool_name = "test_tool"
        params = {}

        with pytest.raises(RuntimeError) as exc_info:
            await execute_mcp_tool_with_endpoint(endpoint, tool_name, params)

        # Verify: Error from _normalize_endpoint
        assert "MCP HTTP endpoint not provided" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_non_json_response(self):
        """
        Test scenario: Execute using explicit endpoint, non-JSON response
        Expected: Return {"raw": text} format
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

        # Verify: Return wrapped text
        expected = json.dumps({"raw": "Non-JSON custom response"}, ensure_ascii=False)
        assert result == expected

    @pytest.mark.asyncio
    async def test_http_error(self):
        """
        Test scenario: HTTP request failed
        Expected: Throw HTTPStatusError
        """
        endpoint = "http://custom-endpoint:9000"
        tool_name = "test_tool"
        params = {}

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404 Not Found", request=MagicMock(), response=MagicMock()
        )

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.post.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(httpx.HTTPStatusError):
                await execute_mcp_tool_with_endpoint(endpoint, tool_name, params)

    @pytest.mark.asyncio
    async def test_cancelled_error_propagates(self):
        """
        Test scenario: asyncio.CancelledError occurs
        Expected: Error re-thrown
        """
        import asyncio

        endpoint = "http://custom-endpoint:9000"
        tool_name = "test_tool"
        params = {}

        mock_response = MagicMock()
        mock_response.json.side_effect = asyncio.CancelledError()
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.post.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(asyncio.CancelledError):
                await execute_mcp_tool_with_endpoint(endpoint, tool_name, params)

    @pytest.mark.asyncio
    async def test_uses_env_timeout(self):
        """
        Test scenario: Use environment variable timeout
        Expected: Get timeout value from MCP_HTTP_TIMEOUT
        """
        endpoint = "http://custom-endpoint:9000"
        tool_name = "test_tool"
        params = {}

        with patch.dict(os.environ, {"MCP_HTTP_TIMEOUT": "60"}):
            mock_response = MagicMock()
            mock_response.json.return_value = {"ok": True}
            mock_response.raise_for_status = MagicMock()

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post.return_value = mock_response

            with patch(
                "httpx.AsyncClient", return_value=mock_client
            ) as mock_async_client:
                await execute_mcp_tool_with_endpoint(endpoint, tool_name, params)

            mock_async_client.assert_called_once_with(timeout=60.0)

    @pytest.mark.asyncio
    async def test_endpoint_with_path(self):
        """
        Test scenario: Endpoint contains path
        Expected: Correctly concatenate /tools/execute
        """
        endpoint = "http://custom-endpoint:9000/api/v1"
        tool_name = "test_tool"
        params = {}
        response_data = {"ok": True}

        mock_response = MagicMock()
        mock_response.json.return_value = response_data
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.post.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            await execute_mcp_tool_with_endpoint(endpoint, tool_name, params)

        call_args = mock_client.post.call_args
        assert call_args[0][0] == "http://custom-endpoint:9000/api/v1/tools/execute"

    @pytest.mark.asyncio
    async def test_complex_params(self):
        """
        Test scenario: Complex parameter structure
        Expected: Correctly serialize nested data
        """
        endpoint = "http://custom-endpoint:9000"
        tool_name = "complex_tool"
        params = {
            "nested": {"level1": {"level2": "value"}},
            "list": [1, 2, 3],
            "unicode": "hello world",
            "boolean": True,
            "null": None,
        }
        response_data = {"received": True}

        mock_response = MagicMock()
        mock_response.json.return_value = response_data
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.post.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await execute_mcp_tool_with_endpoint(endpoint, tool_name, params)

        # Verify: Request contains correct complex parameters
        call_args = mock_client.post.call_args
        assert call_args[1]["json"]["arguments"] == params
        assert result == json.dumps(response_data, ensure_ascii=False)
