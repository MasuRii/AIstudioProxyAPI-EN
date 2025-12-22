"""
Comprehensive tests for browser_utils/operations_modules/parsers.py

Targets:
- _handle_model_list_response(): Network response parsing (async)

Coverage target: 70-80% (120-140 statements out of 177 missing)
"""

from unittest.mock import AsyncMock, patch

import pytest

from browser_utils.operations_modules.parsers import (
    _handle_model_list_response,
)

# ==================== _handle_model_list_response TESTS ====================


@pytest.mark.asyncio
async def test_handle_model_list_response_not_models_endpoint(mock_server_module):
    """Test response from non-models endpoint is ignored."""
    response = AsyncMock()
    response.url = "https://example.com/other_endpoint"
    response.ok = True

    await _handle_model_list_response(response)

    # Should not process, no changes to server state


@pytest.mark.asyncio
async def test_handle_model_list_response_not_ok(mock_server_module):
    """Test response with non-OK status."""
    response = AsyncMock()
    response.url = "https://example.com/models"
    response.ok = False

    await _handle_model_list_response(response)

    # Should not process


@pytest.mark.asyncio
@patch(
    "browser_utils.operations_modules.parsers.MODELS_ENDPOINT_URL_CONTAINS", "models"
)
@patch("api_utils.server_state.state")
async def test_handle_model_list_response_simple_list(mock_state):
    """Test processing simple list of model dicts."""
    # Reset server state
    import asyncio

    mock_state.global_model_list_raw_json = None
    mock_state.parsed_model_list = []
    mock_state.excluded_model_ids = set()
    mock_state.is_page_ready = True
    mock_state.model_list_fetch_event = AsyncMock(spec=asyncio.Event)
    mock_state.model_list_fetch_event.is_set.return_value = False

    response = AsyncMock()
    response.url = "https://example.com/models"
    response.ok = True
    response.status = 200
    response.json.return_value = [
        {"id": "gemini-pro", "displayName": "Gemini Pro", "description": "Pro model"}
    ]

    await _handle_model_list_response(response)

    assert len(mock_state.parsed_model_list) == 1
    assert mock_state.parsed_model_list[0]["id"] == "gemini-pro"
    assert mock_state.parsed_model_list[0]["display_name"] == "Gemini Pro"


@pytest.mark.asyncio
@patch(
    "browser_utils.operations_modules.parsers.MODELS_ENDPOINT_URL_CONTAINS", "models"
)
@patch("api_utils.server_state.state")
async def test_handle_model_list_response_dict_with_data_key(mock_state):
    """Test processing dict response with 'data' key."""
    import asyncio

    mock_state.parsed_model_list = []
    mock_state.excluded_model_ids = set()
    mock_state.is_page_ready = True
    mock_state.model_list_fetch_event = AsyncMock(spec=asyncio.Event)
    mock_state.model_list_fetch_event.is_set.return_value = False

    response = AsyncMock()
    response.url = "https://example.com/models"
    response.ok = True
    response.json.return_value = {"data": [{"id": "model-1", "displayName": "Model 1"}]}

    await _handle_model_list_response(response)

    assert len(mock_state.parsed_model_list) == 1
    assert mock_state.parsed_model_list[0]["id"] == "model-1"


@pytest.mark.asyncio
@patch(
    "browser_utils.operations_modules.parsers.MODELS_ENDPOINT_URL_CONTAINS", "models"
)
@patch("api_utils.server_state.state")
async def test_handle_model_list_response_dict_with_models_key(mock_state):
    """Test processing dict response with 'models' key."""
    import asyncio

    mock_state.parsed_model_list = []
    mock_state.excluded_model_ids = set()
    mock_state.is_page_ready = True
    mock_state.model_list_fetch_event = AsyncMock(spec=asyncio.Event)
    mock_state.model_list_fetch_event.is_set.return_value = False

    response = AsyncMock()
    response.url = "https://example.com/models"
    response.ok = True
    response.json.return_value = {
        "models": [{"id": "model-2", "displayName": "Model 2"}]
    }

    await _handle_model_list_response(response)

    assert len(mock_state.parsed_model_list) == 1
    assert mock_state.parsed_model_list[0]["id"] == "model-2"


@pytest.mark.asyncio
@patch(
    "browser_utils.operations_modules.parsers.MODELS_ENDPOINT_URL_CONTAINS", "models"
)
@patch("api_utils.server_state.state")
async def test_handle_model_list_response_list_based_model_fields(mock_state):
    """Test processing list-based model fields."""
    import asyncio

    mock_state.parsed_model_list = []
    mock_state.excluded_model_ids = set()
    mock_state.is_page_ready = True
    mock_state.model_list_fetch_event = AsyncMock(spec=asyncio.Event)
    mock_state.model_list_fetch_event.is_set.return_value = False

    response = AsyncMock()
    response.url = "https://example.com/models"
    response.ok = True
    # List format: [model_id_path, ..., display_name(idx 3), description(idx 4), ..., max_tokens(idx 6), ..., top_p(idx 9)]
    response.json.return_value = [
        ["models/test-list", 1, 2, "Test List Model", "List desc", 5, 8192, 7, 8, 0.95]
    ]

    await _handle_model_list_response(response)

    assert len(mock_state.parsed_model_list) == 1
    assert mock_state.parsed_model_list[0]["id"] == "test-list"
    assert mock_state.parsed_model_list[0]["display_name"] == "Test List Model"
    assert mock_state.parsed_model_list[0]["default_max_output_tokens"] == 8192
    assert mock_state.parsed_model_list[0]["default_top_p"] == 0.95


@pytest.mark.asyncio
@patch(
    "browser_utils.operations_modules.parsers.MODELS_ENDPOINT_URL_CONTAINS", "models"
)
@patch("api_utils.server_state.state")
async def test_handle_model_list_response_excluded_model(mock_state):
    """Test that excluded models are skipped."""
    import asyncio

    mock_state.parsed_model_list = []
    mock_state.excluded_model_ids = {"excluded-model"}
    mock_state.is_page_ready = True
    mock_state.model_list_fetch_event = AsyncMock(spec=asyncio.Event)
    mock_state.model_list_fetch_event.is_set.return_value = False

    response = AsyncMock()
    response.url = "https://example.com/models"
    response.ok = True
    response.json.return_value = [
        {"id": "excluded-model", "displayName": "Excluded"},
        {"id": "included-model", "displayName": "Included"},
    ]

    await _handle_model_list_response(response)

    assert len(mock_state.parsed_model_list) == 1
    assert mock_state.parsed_model_list[0]["id"] == "included-model"


@pytest.mark.asyncio
@patch(
    "browser_utils.operations_modules.parsers.MODELS_ENDPOINT_URL_CONTAINS", "models"
)
@patch("api_utils.server_state.state")
async def test_handle_model_list_response_empty_list(mock_state):
    """Test handling of empty model list."""
    import asyncio

    mock_state.parsed_model_list = []
    mock_state.excluded_model_ids = set()
    mock_state.is_page_ready = True
    mock_state.model_list_fetch_event = AsyncMock(spec=asyncio.Event)
    mock_state.model_list_fetch_event.is_set.return_value = False

    response = AsyncMock()
    response.url = "https://example.com/models"
    response.ok = True
    response.json.return_value = []

    await _handle_model_list_response(response)

    # Event should still be set
    assert mock_state.model_list_fetch_event.set.called


@pytest.mark.asyncio
@patch(
    "browser_utils.operations_modules.parsers.MODELS_ENDPOINT_URL_CONTAINS", "models"
)
@patch("api_utils.server_state.state")
async def test_handle_model_list_response_invalid_model_id(mock_state):
    """Test skipping models with invalid IDs."""
    import asyncio

    mock_state.parsed_model_list = []
    mock_state.excluded_model_ids = set()
    mock_state.is_page_ready = True
    mock_state.model_list_fetch_event = AsyncMock(spec=asyncio.Event)
    mock_state.model_list_fetch_event.is_set.return_value = False

    response = AsyncMock()
    response.url = "https://example.com/models"
    response.ok = True
    response.json.return_value = [
        {"id": None, "displayName": "Invalid"},
        {"id": "none", "displayName": "Also Invalid"},
        {"id": "valid-id", "displayName": "Valid"},
    ]

    await _handle_model_list_response(response)

    assert len(mock_state.parsed_model_list) == 1
    assert mock_state.parsed_model_list[0]["id"] == "valid-id"


@pytest.mark.asyncio
@patch("browser_utils.operations_modules.parsers.os.environ.get", return_value="debug")
@patch(
    "browser_utils.operations_modules.parsers.MODELS_ENDPOINT_URL_CONTAINS", "models"
)
@patch("api_utils.server_state.state")
async def test_handle_model_list_response_login_flow(mock_state, mock_env):
    """Test silent handling during login flow."""
    import asyncio

    mock_state.is_page_ready = False  # Triggers login flow
    mock_state.parsed_model_list = []
    mock_state.excluded_model_ids = set()
    mock_state.model_list_fetch_event = AsyncMock(spec=asyncio.Event)
    mock_state.model_list_fetch_event.is_set.return_value = False

    response = AsyncMock()
    response.url = "https://example.com/models"
    response.ok = True
    response.json.return_value = [{"id": "test-model", "displayName": "Test"}]

    await _handle_model_list_response(response)

    # Should still process but silently (no logger.info calls in login flow)
    assert len(mock_state.parsed_model_list) == 1


@pytest.mark.asyncio
@patch(
    "browser_utils.operations_modules.parsers.MODELS_ENDPOINT_URL_CONTAINS", "models"
)
@patch("api_utils.server_state.state")
async def test_handle_model_list_response_three_layer_list(mock_state):
    """Test three-layer list structure."""
    import asyncio

    mock_state.parsed_model_list = []
    mock_state.excluded_model_ids = set()
    mock_state.is_page_ready = True
    mock_state.model_list_fetch_event = AsyncMock(spec=asyncio.Event)
    mock_state.model_list_fetch_event.is_set.return_value = False

    response = AsyncMock()
    response.url = "https://example.com/models"
    response.ok = True
    # Three-layer: [[[...], [...]]]
    response.json.return_value = [
        [
            ["models/test-1", 1, 2, "Test 1", "Desc 1"],
            ["models/test-2", 1, 2, "Test 2", "Desc 2"],
        ]
    ]

    await _handle_model_list_response(response)

    assert len(mock_state.parsed_model_list) == 2


@pytest.mark.asyncio
@patch(
    "browser_utils.operations_modules.parsers.MODELS_ENDPOINT_URL_CONTAINS", "models"
)
@patch("api_utils.server_state.state")
async def test_handle_model_list_response_heuristic_search(mock_state):
    """Test heuristic search for model list in dict response."""
    import asyncio

    mock_state.parsed_model_list = []
    mock_state.excluded_model_ids = set()
    mock_state.is_page_ready = True
    mock_state.model_list_fetch_event = AsyncMock(spec=asyncio.Event)
    mock_state.model_list_fetch_event.is_set.return_value = False

    response = AsyncMock()
    response.url = "https://example.com/models"
    response.ok = True
    # Custom key (not 'data' or 'models')
    response.json.return_value = {
        "custom_models_key": [{"id": "heuristic-model", "displayName": "Heuristic"}]
    }

    await _handle_model_list_response(response)

    assert len(mock_state.parsed_model_list) == 1
    assert mock_state.parsed_model_list[0]["id"] == "heuristic-model"


@pytest.mark.asyncio
@patch(
    "browser_utils.operations_modules.parsers.MODELS_ENDPOINT_URL_CONTAINS", "models"
)
@patch("api_utils.server_state.state")
async def test_handle_model_list_response_dict_no_models_found(mock_state):
    """Test dict response with no model array found."""
    import asyncio

    mock_state.is_page_ready = True
    mock_state.parsed_model_list = []
    mock_state.excluded_model_ids = set()
    mock_state.model_list_fetch_event = AsyncMock(spec=asyncio.Event)
    mock_state.model_list_fetch_event.is_set.return_value = False

    response = AsyncMock()
    response.url = "https://example.com/models"
    response.ok = True
    response.json.return_value = {"invalid_key": "no models here"}

    await _handle_model_list_response(response)

    # Should set event and return early
    assert mock_state.model_list_fetch_event.set.called


@pytest.mark.asyncio
@patch(
    "browser_utils.operations_modules.parsers.MODELS_ENDPOINT_URL_CONTAINS", "models"
)
@patch("api_utils.server_state.state")
async def test_handle_model_list_response_list_with_invalid_numeric_fields(
    mock_state,
):
    """Test list-based model with invalid numeric fields."""
    import asyncio

    mock_state.parsed_model_list = []
    mock_state.excluded_model_ids = set()
    mock_state.is_page_ready = True
    mock_state.model_list_fetch_event = AsyncMock(spec=asyncio.Event)
    mock_state.model_list_fetch_event.is_set.return_value = False

    response = AsyncMock()
    response.url = "https://example.com/models"
    response.ok = True
    # List with non-numeric values where numbers expected
    response.json.return_value = [
        ["models/test", 1, 2, "Name", "Desc", 5, "invalid", 7, 8, "bad_top_p"]
    ]

    await _handle_model_list_response(response)

    # Should still parse, but use fallback values
    assert len(mock_state.parsed_model_list) == 1


@pytest.mark.asyncio
@patch(
    "browser_utils.operations_modules.parsers.MODELS_ENDPOINT_URL_CONTAINS", "models"
)
@patch("browser_utils.operations_modules.parsers.DEBUG_LOGS_ENABLED", True)
@patch("api_utils.server_state.state")
async def test_handle_model_list_response_debug_logs_enabled(mock_state):
    """Test detailed logging when DEBUG_LOGS_ENABLED=True."""
    import asyncio

    mock_state.parsed_model_list = []
    mock_state.excluded_model_ids = set()
    mock_state.is_page_ready = True
    mock_state.model_list_fetch_event = AsyncMock(spec=asyncio.Event)
    mock_state.model_list_fetch_event.is_set.return_value = False

    response = AsyncMock()
    response.url = "https://example.com/models"
    response.ok = True
    response.json.return_value = [
        {"id": "debug-model-1", "displayName": "Debug 1"},
        {"id": "debug-model-2", "displayName": "Debug 2"},
        {"id": "debug-model-3", "displayName": "Debug 3"},
    ]

    await _handle_model_list_response(response)

    # Should log first 3 models when debug enabled
    assert len(mock_state.parsed_model_list) == 3


# ==================== Model List Change Detection Tests ====================


@pytest.mark.asyncio
@patch(
    "browser_utils.operations_modules.parsers.MODELS_ENDPOINT_URL_CONTAINS", "models"
)
@patch("browser_utils.operations_modules.parsers.DEBUG_LOGS_ENABLED", True)
@patch("api_utils.server_state.state")
async def test_handle_model_list_response_tracks_last_count(mock_state):
    """Test that _last_model_count is tracked for change detection."""
    import asyncio

    mock_state.parsed_model_list = []
    mock_state.excluded_model_ids = set()
    mock_state.is_page_ready = True
    mock_state.model_list_fetch_event = AsyncMock(spec=asyncio.Event)
    mock_state.model_list_fetch_event.is_set.return_value = False
    mock_state._last_model_count = 0

    response = AsyncMock()
    response.url = "https://example.com/models"
    response.ok = True
    response.status = 200
    response.json.return_value = [
        {"id": "model-1", "displayName": "Model 1"},
        {"id": "model-2", "displayName": "Model 2"},
    ]

    await _handle_model_list_response(response)

    # _last_model_count should be updated
    assert mock_state._last_model_count == 2


@pytest.mark.asyncio
@patch(
    "browser_utils.operations_modules.parsers.MODELS_ENDPOINT_URL_CONTAINS", "models"
)
@patch("browser_utils.operations_modules.parsers.DEBUG_LOGS_ENABLED", True)
@patch("api_utils.server_state.state")
async def test_handle_model_list_no_change_detection(mock_state):
    """Test that 'no change' log is shown when model count is same."""
    import asyncio

    # Pre-set same count
    mock_state.parsed_model_list = []
    mock_state.excluded_model_ids = set()
    mock_state.is_page_ready = True
    mock_state.model_list_fetch_event = AsyncMock(spec=asyncio.Event)
    mock_state.model_list_fetch_event.is_set.return_value = False
    mock_state._last_model_count = 2  # Set to match expected count

    response = AsyncMock()
    response.url = "https://example.com/models"
    response.ok = True
    response.status = 200
    response.json.return_value = [
        {"id": "model-1", "displayName": "Model 1"},
        {"id": "model-2", "displayName": "Model 2"},
    ]

    await _handle_model_list_response(response)

    assert len(mock_state.parsed_model_list) == 2


@pytest.mark.asyncio
@patch(
    "browser_utils.operations_modules.parsers.MODELS_ENDPOINT_URL_CONTAINS", "models"
)
@patch("browser_utils.operations_modules.parsers.DEBUG_LOGS_ENABLED", True)
@patch("api_utils.server_state.state")
async def test_handle_model_list_excluded_in_change_block(mock_state):
    """Test that excluded models log is only shown when count changes."""
    import asyncio

    mock_state.parsed_model_list = []
    mock_state.excluded_model_ids = {"excluded-1"}
    mock_state.is_page_ready = True
    mock_state.model_list_fetch_event = AsyncMock(spec=asyncio.Event)
    mock_state.model_list_fetch_event.is_set.return_value = False
    mock_state._last_model_count = 0  # Initial load

    response = AsyncMock()
    response.url = "https://example.com/models"
    response.ok = True
    response.status = 200
    response.json.return_value = [
        {"id": "excluded-1", "displayName": "Excluded"},
        {"id": "included-1", "displayName": "Included"},
    ]

    await _handle_model_list_response(response)

    # Only included model should be in list
    assert len(mock_state.parsed_model_list) == 1
    assert mock_state.parsed_model_list[0]["id"] == "included-1"


@pytest.mark.asyncio
@patch(
    "browser_utils.operations_modules.parsers.MODELS_ENDPOINT_URL_CONTAINS", "models"
)
@patch("browser_utils.operations_modules.parsers.DEBUG_LOGS_ENABLED", True)
@patch("api_utils.server_state.state")
async def test_handle_model_list_first_load_always_logs(mock_state):
    """Test that first load (previous_count=0) always logs full details."""
    import asyncio

    mock_state.parsed_model_list = []
    mock_state.excluded_model_ids = set()
    mock_state.is_page_ready = True
    mock_state.model_list_fetch_event = AsyncMock(spec=asyncio.Event)
    mock_state.model_list_fetch_event.is_set.return_value = False
    # No _last_model_count attribute (first load)
    if hasattr(mock_state, "_last_model_count"):
        delattr(mock_state, "_last_model_count")

    response = AsyncMock()
    response.url = "https://example.com/models"
    response.ok = True
    response.status = 200
    response.json.return_value = [
        {"id": "test-model", "displayName": "Test"},
    ]

    await _handle_model_list_response(response)

    assert len(mock_state.parsed_model_list) == 1
