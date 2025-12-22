"""Browser utils test fixtures."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_expect():
    """Create a mock for playwright's expect function.

    This fixture patches both:
    1. browser_utils.initialization.core.expect_async (used directly in core.py)
    2. playwright.async_api.expect (used by find_first_visible_locator in selector_utils.py)

    This is necessary because find_first_visible_locator imports expect directly
    from playwright.async_api, while core.py imports it with an alias.
    """
    mock = MagicMock()
    assertion_wrapper = MagicMock()
    assertion_wrapper.to_be_visible = AsyncMock()
    mock.return_value = assertion_wrapper

    with (
        patch("browser_utils.initialization.core.expect_async", mock),
        patch("playwright.async_api.expect", mock),
    ):
        yield mock


@pytest.fixture(autouse=True)
def mock_server_state(request):
    """Automatically mock server_state.state for all browser_utils tests.

    This prevents tests from hanging on model_list_fetch_event.wait().
    If a test provides its own mock_server fixture, this fixture will use its values.

    Does not apply to integration tests (those with @pytest.mark.integration).
    """
    # Skip for integration tests
    if "integration" in request.keywords:
        yield
        return
    # Check if test has mock_server fixture
    if "mock_server" in request.fixturenames:
        mock_server = request.getfixturevalue("mock_server")
        mock_state = mock_server
    else:
        mock_state = MagicMock()
        mock_state.current_ai_studio_model_id = None
        mock_state.parsed_model_list = []

        # Configure browser_instance with sync is_connected method
        mock_state.browser_instance = MagicMock()
        mock_state.browser_instance.is_connected = MagicMock(return_value=True)

        # Configure page_instance with sync is_closed method
        mock_state.page_instance = MagicMock()
        mock_state.page_instance.is_closed = MagicMock(return_value=False)

    # Always ensure model_list_fetch_event exists and is set to avoid hanging
    if (
        not hasattr(mock_state, "model_list_fetch_event")
        or mock_state.model_list_fetch_event is None
    ):
        mock_event = asyncio.Event()
        mock_event.set()
        mock_state.model_list_fetch_event = mock_event

    # Ensure browser_instance.is_connected is sync (always override to prevent AsyncMock)
    if hasattr(mock_state, "browser_instance"):
        mock_state.browser_instance.is_connected = MagicMock(return_value=True)

    # Ensure page_instance.is_closed is sync (always override to prevent AsyncMock)
    if hasattr(mock_state, "page_instance"):
        mock_state.page_instance.is_closed = MagicMock(return_value=False)

    with patch("api_utils.server_state.state", mock_state):
        yield mock_state
