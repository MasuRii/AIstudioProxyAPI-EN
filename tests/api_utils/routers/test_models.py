from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api_utils.routers.models import list_models
from config import DEFAULT_FALLBACK_MODEL_ID


@pytest.mark.asyncio
async def test_list_models_success(mock_env):
    # Mock dependencies
    logger = MagicMock()
    model_list_fetch_event = MagicMock()
    model_list_fetch_event.is_set.return_value = True

    page_instance = AsyncMock()
    page_instance.is_closed.return_value = False

    parsed_model_list = [
        {"id": "gemini-1.5-pro", "object": "model"},
        {"id": "gemini-1.5-flash", "object": "model"},
    ]
    excluded_model_ids = {"gemini-1.5-flash"}

    response = await list_models(
        logger=logger,
        model_list_fetch_event=model_list_fetch_event,
        page_instance=page_instance,
        parsed_model_list=parsed_model_list,
        excluded_model_ids=excluded_model_ids,
    )

    assert response["object"] == "list"
    assert len(response["data"]) == 1
    assert response["data"][0]["id"] == "gemini-1.5-pro"


@pytest.mark.asyncio
async def test_list_models_fallback(mock_env):
    logger = MagicMock()
    model_list_fetch_event = MagicMock()
    model_list_fetch_event.is_set.return_value = True

    page_instance = AsyncMock()
    parsed_model_list = []  # Empty list
    excluded_model_ids = set()

    response = await list_models(
        logger=logger,
        model_list_fetch_event=model_list_fetch_event,
        page_instance=page_instance,
        parsed_model_list=parsed_model_list,
        excluded_model_ids=excluded_model_ids,
    )

    assert response["object"] == "list"
    assert len(response["data"]) == 1
    assert response["data"][0]["id"] == DEFAULT_FALLBACK_MODEL_ID


@pytest.mark.asyncio
async def test_list_models_fetch_timeout(mock_env):
    logger = MagicMock()
    model_list_fetch_event = AsyncMock()
    model_list_fetch_event.is_set.return_value = False
    # Simulate wait timeout
    model_list_fetch_event.wait.side_effect = TimeoutError("Timeout")

    page_instance = AsyncMock()
    page_instance.is_closed.return_value = False

    parsed_model_list = []
    excluded_model_ids = set()

    # Should handle exception gracefully and return fallback
    response = await list_models(
        logger=logger,
        model_list_fetch_event=model_list_fetch_event,
        page_instance=page_instance,
        parsed_model_list=parsed_model_list,
        excluded_model_ids=excluded_model_ids,
    )

    assert response["object"] == "list"
    assert len(response["data"]) == 1
    assert response["data"][0]["id"] == DEFAULT_FALLBACK_MODEL_ID


"""
Extended tests for api_utils/routers/models.py - Edge case coverage.

Focus: Cover uncovered lines in model refresh logic (35-43).
Strategy: Test page reload scenarios, event waiting, exception handling.
"""

import asyncio


@pytest.mark.asyncio
async def test_list_models_event_not_set_reload_success(mock_env):
    """
    Test scenario: Model list event not set, page reload success
    Expected: Execute reload and wait_for, cover lines 35-38
    """
    logger = MagicMock()
    model_list_fetch_event = MagicMock(spec=asyncio.Event)
    model_list_fetch_event.is_set.return_value = False

    # Use MagicMock for page, only reload is async
    page_instance = MagicMock()
    page_instance.is_closed.return_value = False
    page_instance.reload = AsyncMock()

    # Mock wait() finishes successfully inside wait_for
    async def mock_wait():
        # Simulate successful wait
        model_list_fetch_event.is_set.return_value = True
        return

    model_list_fetch_event.wait = mock_wait

    parsed_model_list = [{"id": "gemini-1.5-pro", "object": "model"}]
    excluded_model_ids = set()

    response = await list_models(
        logger=logger,
        model_list_fetch_event=model_list_fetch_event,
        page_instance=page_instance,
        parsed_model_list=parsed_model_list,
        excluded_model_ids=excluded_model_ids,
    )

    # Verify: Page reloaded
    page_instance.reload.assert_called_once()

    # Verify: Return model list
    assert response["object"] == "list"
    assert len(response["data"]) == 1


@pytest.mark.asyncio
async def test_list_models_reload_timeout(mock_env):
    """
    Test scenario: wait_for timeout, triggers except and finally
    Expected: Catch exception, log error, set event (lines 38-43)
    """
    logger = MagicMock()
    model_list_fetch_event = MagicMock(spec=asyncio.Event)
    model_list_fetch_event.is_set.return_value = False

    # Use MagicMock for page, only reload is async
    page_instance = MagicMock()
    page_instance.is_closed.return_value = False
    page_instance.reload = AsyncMock()

    # Mock wait() to sleep briefly, but longer than the mocked timeout
    async def mock_wait_longer_than_timeout():
        await asyncio.sleep(0.2)  # Longer than mocked 0.1s timeout

    model_list_fetch_event.wait = mock_wait_longer_than_timeout

    parsed_model_list = [{"id": "gemini-1.5-pro", "object": "model"}]
    excluded_model_ids = set()

    # Patch the wait_for timeout to be very short for testing
    with patch(
        "api_utils.routers.models.asyncio.wait_for", wraps=asyncio.wait_for
    ) as mock_wait_for:
        # Override wait_for to use a short timeout
        async def short_timeout_wait_for(coro, timeout):
            return await asyncio.wait_for(coro, timeout=0.1)

        mock_wait_for.side_effect = short_timeout_wait_for

        response = await list_models(
            logger=logger,
            model_list_fetch_event=model_list_fetch_event,
            page_instance=page_instance,
            parsed_model_list=parsed_model_list,
            excluded_model_ids=excluded_model_ids,
        )

    # Verify: Error logged
    assert logger.error.called

    # Verify: Event set (finally block)
    model_list_fetch_event.set.assert_called()

    # Verify: Return model list (because parsed_model_list is not empty)
    assert response["object"] == "list"
    assert len(response["data"]) == 1


@pytest.mark.asyncio
async def test_list_models_reload_exception(mock_env):
    """
    Test scenario: page.reload() throws exception
    Expected: Catch exception, log error, set event (lines 37-43)
    """
    logger = MagicMock()
    model_list_fetch_event = MagicMock(spec=asyncio.Event)
    model_list_fetch_event.is_set.return_value = False

    # Use MagicMock for page, only reload is async
    page_instance = MagicMock()
    page_instance.is_closed.return_value = False

    # Mock reload throws exception
    page_instance.reload = AsyncMock(side_effect=Exception("Reload failed"))

    parsed_model_list = []
    excluded_model_ids = set()

    response = await list_models(
        logger=logger,
        model_list_fetch_event=model_list_fetch_event,
        page_instance=page_instance,
        parsed_model_list=parsed_model_list,
        excluded_model_ids=excluded_model_ids,
    )

    # Verify: Error logged
    logger.error.assert_called_once()
    error_call_args = logger.error.call_args[0][0]
    assert "Error" in error_call_args

    # Verify: Event set (finally block)
    model_list_fetch_event.set.assert_called()

    # Verify: Return fallback model (because parsed_model_list is empty)
    assert response["object"] == "list"
    assert len(response["data"]) == 1
    assert response["data"][0]["id"] == DEFAULT_FALLBACK_MODEL_ID


@pytest.mark.asyncio
async def test_list_models_page_closed(mock_env):
    """
    Test scenario: Page closed, do not perform reload
    Expected: Skip reload logic, return directly
    """
    logger = MagicMock()
    model_list_fetch_event = MagicMock(spec=asyncio.Event)
    model_list_fetch_event.is_set.return_value = False

    # Use MagicMock for page, is_closed is synchronous
    page_instance = MagicMock()
    page_instance.is_closed.return_value = True  # Page closed

    parsed_model_list = [{"id": "gemini-1.5-pro", "object": "model"}]
    excluded_model_ids = set()

    response = await list_models(
        logger=logger,
        model_list_fetch_event=model_list_fetch_event,
        page_instance=page_instance,
        parsed_model_list=parsed_model_list,
        excluded_model_ids=excluded_model_ids,
    )

    # Verify: reload not called
    page_instance.reload.assert_not_called()

    # Verify: Return model list
    assert response["object"] == "list"
    assert len(response["data"]) == 1


@pytest.mark.asyncio
async def test_list_models_page_none(mock_env):
    """
    Test scenario: page_instance is None
    Expected: Skip reload logic, return directly
    """
    logger = MagicMock()
    model_list_fetch_event = MagicMock(spec=asyncio.Event)
    model_list_fetch_event.is_set.return_value = False

    page_instance = None  # No page instance

    parsed_model_list = [{"id": "gemini-1.5-pro", "object": "model"}]
    excluded_model_ids = set()

    response = await list_models(
        logger=logger,
        model_list_fetch_event=model_list_fetch_event,
        page_instance=page_instance,  # type: ignore[arg-type]
        parsed_model_list=parsed_model_list,
        excluded_model_ids=excluded_model_ids,
    )

    # Verify: Return model list (no reload needed)
    assert response["object"] == "list"
    assert len(response["data"]) == 1


@pytest.mark.asyncio
async def test_list_models_filter_non_dict_entries(mock_env):
    """
    Test scenario: parsed_model_list contains non-dict entries
    Expected: Filter non-dict entries, return only valid dicts
    """
    logger = MagicMock()
    model_list_fetch_event = MagicMock(spec=asyncio.Event)
    model_list_fetch_event.is_set.return_value = True

    # Use MagicMock for page
    page_instance = MagicMock()

    # Contains non-dict entries
    parsed_model_list = [
        {"id": "gemini-1.5-pro", "object": "model"},
        "invalid_string",  # non-dict
        None,  # non-dict
        {"id": "gemini-1.5-flash", "object": "model"},
    ]
    excluded_model_ids = set()

    response = await list_models(
        logger=logger,
        model_list_fetch_event=model_list_fetch_event,
        page_instance=page_instance,
        parsed_model_list=parsed_model_list,
        excluded_model_ids=excluded_model_ids,
    )

    # Verify: Return only dict entries
    assert response["object"] == "list"
    assert len(response["data"]) == 2
    assert all(isinstance(m, dict) for m in response["data"])


@pytest.mark.asyncio
async def test_list_models_empty_after_filtering(mock_env):
    """
    Test scenario: All models excluded
    Expected: Return empty list, not fallback model (because parsed_model_list is not None)
    """
    logger = MagicMock()
    model_list_fetch_event = MagicMock(spec=asyncio.Event)
    model_list_fetch_event.is_set.return_value = True

    # Use MagicMock for page
    page_instance = MagicMock()

    parsed_model_list = [
        {"id": "gemini-1.5-pro", "object": "model"},
        {"id": "gemini-1.5-flash", "object": "model"},
    ]
    excluded_model_ids = {"gemini-1.5-pro", "gemini-1.5-flash"}  # Exclude all

    response = await list_models(
        logger=logger,
        model_list_fetch_event=model_list_fetch_event,
        page_instance=page_instance,
        parsed_model_list=parsed_model_list,
        excluded_model_ids=excluded_model_ids,
    )

    # Verify: Return empty list (not fallback)
    assert response["object"] == "list"
    assert len(response["data"]) == 0
