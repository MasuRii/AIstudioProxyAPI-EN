"""
Tests for browser_utils/initialization/network.py
Target coverage: >80% (from baseline 10%)
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from browser_utils.initialization.network import (
    _modify_model_list_response,
    _setup_model_list_interception,
    setup_network_interception_and_scripts,
)
from config import settings


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "interception_enabled, scripts_enabled, should_intercept, should_scripts",
    [
        (False, False, False, False),
        (True, True, True, True),
        (True, False, True, False),
        (False, True, False, True),
    ],
)
async def test_setup_network_and_scripts_combinations(
    interception_enabled, scripts_enabled, should_intercept, should_scripts
):
    """Test all combinations of network interception and script injection toggles"""
    mock_context = AsyncMock()

    with (
        patch.object(settings, "NETWORK_INTERCEPTION_ENABLED", interception_enabled),
        patch.object(settings, "ENABLE_SCRIPT_INJECTION", scripts_enabled),
        patch(
            "browser_utils.initialization.network._setup_model_list_interception"
        ) as mock_setup,
        patch(
            "browser_utils.initialization.network.add_init_scripts_to_context"
        ) as mock_scripts,
    ):
        await setup_network_interception_and_scripts(mock_context)

        if should_intercept:
            mock_setup.assert_called_once_with(mock_context)
        else:
            mock_setup.assert_not_called()

        if should_scripts:
            mock_scripts.assert_called_once_with(mock_context)
        else:
            mock_scripts.assert_not_called()


@pytest.mark.asyncio
async def test_route_handler_registered():
    """Test route handler registration"""
    mock_context = AsyncMock()

    await _setup_model_list_interception(mock_context)

    mock_context.route.assert_called_once()
    assert callable(mock_context.route.call_args[0][1])


@pytest.mark.asyncio
async def test_modify_response_anti_hijack_prefix():
    """Test anti-hijack prefix handling"""
    body_with_prefix = b')]}\'\n{"models": []}'

    result = await _modify_model_list_response(body_with_prefix, "https://example.com")

    # Should start with prefix
    assert result.startswith(b")]}'\n")
    # Should contain valid JSON after prefix (prefix is 5 bytes: ) ] } ' \n)
    json_part = result[5:]
    data = json.loads(json_part)
    assert "models" in data


@pytest.mark.asyncio
async def test_modify_response_no_prefix():
    """Test response without anti-hijack prefix"""
    body = b'{"models": []}'

    result = await _modify_model_list_response(body, "https://example.com")

    # Should NOT start with prefix
    assert not result.startswith(b")]}'\n")
    data = json.loads(result)
    assert "models" in data


@pytest.mark.asyncio
async def test_setup_exception_handling():
    """Test exception handling in setup_network_interception_and_scripts"""
    mock_context = AsyncMock()

    with (
        patch.object(settings, "ENABLE_SCRIPT_INJECTION", True),
        patch.object(settings, "NETWORK_INTERCEPTION_ENABLED", True),
        patch(
            "browser_utils.initialization.network._setup_model_list_interception",
            side_effect=RuntimeError("Route setup failed"),
        ),
        patch("browser_utils.initialization.network.logger") as mock_logger,
    ):
        # Should not raise, should log error
        await setup_network_interception_and_scripts(mock_context)

        # Verify error was logged
        assert mock_logger.error.called


@pytest.mark.asyncio
async def test_setup_model_list_interception_exception():
    """Test exception in _setup_model_list_interception"""
    mock_context = AsyncMock()
    mock_context.route.side_effect = RuntimeError("Route registration failed")

    with patch("browser_utils.initialization.network.logger") as mock_logger:
        await _setup_model_list_interception(mock_context)

        # Verify error was logged
        assert mock_logger.error.called


@pytest.mark.asyncio
async def test_modify_response_json_decode_error():
    """Test JSON decode error handling in _modify_model_list_response"""
    invalid_json_body = b'{"invalid json'

    # Should return original body on error
    result = await _modify_model_list_response(invalid_json_body, "https://example.com")

    assert result == invalid_json_body
