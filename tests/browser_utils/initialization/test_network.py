"""
Tests for browser_utils/initialization/network.py
Target coverage: >80% (from baseline 10%)
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from browser_utils.initialization.network import (
    _find_model_list_array,
    _find_template_model,
    _inject_models_to_response,
    _modify_model_list_response,
    _setup_model_list_interception,
    setup_network_interception_and_scripts,
)


@pytest.mark.asyncio
async def test_setup_disabled():
    """Test early return when script injection disabled"""
    mock_context = AsyncMock()

    with patch("config.settings.ENABLE_SCRIPT_INJECTION", False):
        await setup_network_interception_and_scripts(mock_context)

        mock_context.route.assert_not_called()


@pytest.mark.asyncio
async def test_setup_enabled():
    """Test setup when script injection enabled"""
    mock_context = AsyncMock()

    with (
        patch("config.settings.ENABLE_SCRIPT_INJECTION", True),
        patch(
            "browser_utils.initialization.network._setup_model_list_interception"
        ) as mock_setup,
        patch("browser_utils.initialization.network.add_init_scripts_to_context"),
    ):
        await setup_network_interception_and_scripts(mock_context)
        mock_setup.assert_called_once_with(mock_context)


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

    with patch(
        "browser_utils.initialization.network._inject_models_to_response"
    ) as mock_inject:
        mock_inject.return_value = {"models": []}

        result = await _modify_model_list_response(
            body_with_prefix, "https://example.com"
        )

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

    with patch(
        "browser_utils.initialization.network._inject_models_to_response"
    ) as mock_inject:
        mock_inject.return_value = {"models": []}

        result = await _modify_model_list_response(body, "https://example.com")

        # Should NOT start with prefix
        assert not result.startswith(b")]}'\n")
        data = json.loads(result)
        assert "models" in data


@pytest.mark.asyncio
async def test_inject_models_no_models_to_inject():
    """Test injection when no models configured"""
    data = {"models": [{"id": "existing"}]}

    with (
        patch(
            "browser_utils.initialization.network._find_model_list_array"
        ) as mock_find,
        patch("browser_utils.operations._get_injected_models") as mock_get,
    ):
        mock_find.return_value = data["models"]
        mock_get.return_value = []

        result = await _inject_models_to_response(data, "https://example.com")

        assert len(result["models"]) == 1  # No change


@pytest.mark.asyncio
async def test_inject_models_success():
    """Test successful model injection"""
    data = {"models": [{"id": "existing"}]}

    injected_spec = {
        "raw_model_path": "models/custom",
        "display_name": "Custom Model",
        "description": "Test",
    }

    template = [
        "models/template",
        None,
        None,
        "Template",
        "Desc",
        None,
        None,
        None,
        None,
        None,
        None,
    ]

    with (
        patch(
            "browser_utils.initialization.network._find_model_list_array"
        ) as mock_find,
        patch("browser_utils.operations._get_injected_models") as mock_get,
        patch(
            "browser_utils.initialization.network._find_template_model"
        ) as mock_template,
    ):
        mock_find.return_value = [template.copy()]  # Pass list with template
        mock_get.return_value = [injected_spec]
        mock_template.return_value = template

        result = await _inject_models_to_response(data, "https://example.com")

        # Should have injected model plus original template
        models_array = _find_model_list_array(result)
        assert models_array is not None
        assert len(models_array) == 2  # Template + injected


def test_find_model_list_direct():
    """Test finding models array at top level"""
    # Create proper model structure
    data = {"models": [["models/gemini-1.5-pro", None, None, "Pro"]]}

    result = _find_model_list_array(data)

    assert result == data["models"]


def test_find_model_list_nested():
    """Test finding models array in nested structure"""
    data = {
        "data": {"response": {"models": [["models/gemini-1.5-pro", None, None, "Pro"]]}}
    }

    result = _find_model_list_array(data)

    assert result is not None
    assert len(result) == 1


def test_find_model_list_not_found():
    """Test return None when no models found"""
    data = {"other": "data"}

    result = _find_model_list_array(data)

    assert result is None


def test_find_template_flash_preferred():
    """Test flash model preferred"""
    models = [
        ["models/gemini-pro", None, None, "Pro", "Desc", None, None, None],
        ["models/gemini-flash", None, None, "Flash", "Desc", None, None, None],
    ]

    result = _find_template_model(models)

    assert result is not None
    assert "flash" in result[0].lower()


def test_find_template_pro_fallback():
    """Test pro model fallback when no flash"""
    models = [
        ["models/other", None, None, "Other", "Desc", None, None, None],
        ["models/gemini-pro", None, None, "Pro", "Desc", None, None, None],
    ]

    result = _find_template_model(models)

    assert result is not None
    assert "pro" in result[0].lower()


def test_find_template_first_fallback():
    """Test first model fallback"""
    models = [["models/custom-1", None, None, "Custom", "Desc", None, None, None]]

    result = _find_template_model(models)

    assert result == models[0]


def test_find_template_empty():
    """Test empty models array"""
    result = _find_template_model([])
    assert result is None


# Additional coverage tests for uncovered lines


@pytest.mark.asyncio
async def test_setup_exception_handling():
    """Test exception handling in setup_network_interception_and_scripts"""
    mock_context = AsyncMock()

    with (
        patch("config.settings.ENABLE_SCRIPT_INJECTION", True),
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


@pytest.mark.asyncio
async def test_inject_models_no_array_found():
    """Test warning when models array not found"""
    data = {"other": "data", "no_models": True}

    with (
        patch("browser_utils.operations._get_injected_models") as mock_get,
        patch("browser_utils.initialization.network.logger") as mock_logger,
    ):
        mock_get.return_value = [
            {
                "raw_model_path": "models/test",
                "display_name": "Test",
                "description": "Test",
            }
        ]

        result = await _inject_models_to_response(data, "https://example.com")

        # Should return unmodified data and log warning
        assert result == data
        assert any(
            "未找到模型数组" in str(call) for call in mock_logger.warning.call_args_list
        )


@pytest.mark.asyncio
async def test_inject_models_no_template_found():
    """Test warning when template model not found"""
    data = {"models": [["models/test"]]}  # Model with len <= 7, won't be valid template

    with (
        patch(
            "browser_utils.initialization.network._find_model_list_array"
        ) as mock_find,
        patch("browser_utils.operations._get_injected_models") as mock_get,
        patch("browser_utils.initialization.network.logger") as mock_logger,
    ):
        mock_find.return_value = data["models"]
        mock_get.return_value = [
            {
                "raw_model_path": "models/new",
                "display_name": "New",
                "description": "New",
            }
        ]

        result = await _inject_models_to_response(data, "https://example.com")

        # Should return unmodified data and log warning
        assert result == data
        assert any(
            "未找到模板模型" in str(call) for call in mock_logger.warning.call_args_list
        )


@pytest.mark.asyncio
async def test_inject_models_array_extension():
    """Test model array extension when template < 10 elements"""
    data = {"models": []}

    # Template with only 8 elements (< 10)
    short_template = [
        "models/template",
        None,
        None,
        "Template",
        "Desc",
        None,
        None,
        None,
    ]

    injected_spec = {
        "raw_model_path": "models/custom",
        "display_name": "Custom",
        "description": "Test",
    }

    with (
        patch(
            "browser_utils.initialization.network._find_model_list_array"
        ) as mock_find,
        patch("browser_utils.operations._get_injected_models") as mock_get,
        patch(
            "browser_utils.initialization.network._find_template_model"
        ) as mock_template,
    ):
        models_array = [short_template.copy()]
        mock_find.return_value = models_array
        mock_get.return_value = [injected_spec]
        mock_template.return_value = short_template

        result = await _inject_models_to_response(data, "https://example.com")

        # Verify model was injected with extension to >10 elements
        models = _find_model_list_array(result)
        assert models is not None, "models should not be None"
        assert len(models) == 2  # Original + injected
        injected_model = models[0]
        assert len(injected_model) > 10  # Should be extended


@pytest.mark.asyncio
async def test_inject_models_get_exception():
    """Test exception handling in _inject_models_to_response"""
    data = {"models": []}

    with (
        patch(
            "browser_utils.operations._get_injected_models",
            side_effect=RuntimeError("Failed to get models"),
        ),
        patch("browser_utils.initialization.network.logger") as mock_logger,
    ):
        result = await _inject_models_to_response(data, "https://example.com")

        # Should return original data and log error
        assert result == data
        assert mock_logger.error.called


def test_find_model_list_nested_in_list():
    """Test finding models array nested in list structure"""
    data = [
        {"other": "data"},
        {"nested": {"models": [["models/gemini-1.5-pro", None, None, "Pro"]]}},
    ]

    result = _find_model_list_array(data)

    assert result is not None
    assert len(result) == 1


def test_find_template_invalid_length_models():
    """Test return None when all models have invalid length"""
    # All models have len <= 7
    models = [
        ["model1", None, None],
        ["model2", None],
        ["model3"],
    ]

    result = _find_template_model(models)

    assert result is None
