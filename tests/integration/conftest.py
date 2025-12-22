"""
Fixtures for integration tests.

These fixtures provide real instances of components (locks, queues, state)
rather than mocks, allowing tests to verify actual behavior and concurrency.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api_utils.server_state import state


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


@pytest.fixture
async def real_server_state():
    """
    Provide real server state with real asyncio primitives.

    This fixture:
    - Resets server state to clean slate
    - Creates real asyncio.Lock, asyncio.Queue instances
    - Mocks only external boundaries (browser, page)
    - Cleans up properly after test

    Use this for integration tests that verify:
    - Lock behavior and concurrency
    - Queue processing
    - State management
    - Async task coordination
    """
    # Reset state to clean slate
    state.reset()

    # Create REAL asyncio primitives (not mocks)
    state.processing_lock = asyncio.Lock()
    state.model_switching_lock = asyncio.Lock()
    state.params_cache_lock = asyncio.Lock()
    state.request_queue = asyncio.Queue()

    # Mock only external boundaries (browser/page - these are I/O)
    mock_page = AsyncMock()
    mock_page.goto = AsyncMock()
    mock_page.wait_for_selector = AsyncMock()
    mock_page.click = AsyncMock()
    mock_page.fill = AsyncMock()
    mock_page.evaluate = AsyncMock(return_value='{"mock": "preferences"}')

    # Mock locator to return proper AsyncMock locator objects
    mock_locator = AsyncMock()
    mock_locator.fill = AsyncMock()
    mock_locator.click = AsyncMock()
    mock_locator.is_visible = AsyncMock(return_value=True)
    mock_locator.wait_for = AsyncMock()
    mock_page.locator = MagicMock(return_value=mock_locator)

    mock_page.is_closed = MagicMock(return_value=False)  # Page is open

    mock_browser = AsyncMock()
    mock_browser.new_context = AsyncMock(return_value=AsyncMock())
    mock_browser.close = AsyncMock()

    state.page_instance = mock_page
    state.browser_instance = mock_browser
    state.is_page_ready = True
    state.is_browser_connected = True

    yield state

    # Cleanup: Cancel any tasks, release locks, clear queue
    # This is CRITICAL for Windows to prevent hangs

    # Clear queue
    while not state.request_queue.empty():
        try:
            state.request_queue.get_nowait()
            state.request_queue.task_done()
        except asyncio.QueueEmpty:
            break

    # Cancel worker task if exists
    if state.worker_task and not state.worker_task.done():
        state.worker_task.cancel()
        try:
            await state.worker_task
        except asyncio.CancelledError:
            pass

    # Reset state again
    state.reset()


@pytest.fixture
def mock_http_request():
    """
    Create a mock HTTP request for testing.

    Provides:
    - is_disconnected() method that can be controlled
    - Common request attributes
    """
    request = MagicMock()
    request.is_disconnected = AsyncMock(return_value=False)
    request.client = MagicMock()
    request.client.host = "127.0.0.1"
    return request


@pytest.fixture
def mock_chat_request():
    """
    Create a mock ChatCompletionRequest for testing.

    Provides a realistic request object without needing full Pydantic validation.
    """
    from models import ChatCompletionRequest, Message

    return ChatCompletionRequest(
        model="gemini-1.5-pro",
        messages=[Message(role="user", content="Test message")],
        stream=False,
        temperature=0.7,
        max_output_tokens=1024,
    )


@pytest.fixture
async def queue_with_items(real_server_state, mock_http_request):
    """
    Provide a queue pre-populated with test items.

    Returns:
        tuple: (queue, items_list)
        - queue: The real asyncio.Queue from state
        - items_list: List of items added to queue for verification
    """
    items = []

    for i in range(3):
        item = {
            "req_id": f"test-req-{i}",
            "request_data": MagicMock(),
            "http_request": mock_http_request,
            "result_future": asyncio.Future(),
            "cancelled": False,
        }
        items.append(item)
        await real_server_state.request_queue.put(item)

    return real_server_state.request_queue, items


@pytest.fixture
def temp_auth_file(tmp_path):
    """
    Create a temporary authentication file for browser initialization tests.

    This fixture creates a realistic Playwright storage state JSON file
    with minimal cookie data. Use this for integration tests that need
    real file I/O instead of mocking os.path.exists.

    Returns:
        Path: Absolute path to the temporary auth.json file
    """
    import json

    auth_data = {
        "cookies": [
            {
                "name": "test_sid",
                "value": "test_session_id_12345",
                "domain": ".google.com",
                "path": "/",
                "expires": 1798102822,
                "httpOnly": False,
                "secure": True,
                "sameSite": "None",
            }
        ],
        "origins": [
            {
                "origin": "https://aistudio.google.com",
                "localStorage": [{"name": "test_key", "value": "test_value"}],
            }
        ],
    }

    auth_file = tmp_path / "test_auth.json"
    auth_file.write_text(json.dumps(auth_data), encoding="utf-8")

    return auth_file


@pytest.fixture
def temp_auth_file_missing(tmp_path):
    """
    Create a path to a non-existent auth file for testing missing file scenarios.

    Returns:
        Path: Absolute path to a non-existent file
    """
    return tmp_path / "missing_auth.json"
