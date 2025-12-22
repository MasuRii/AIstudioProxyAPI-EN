"""
High-quality tests for api_utils/dependencies.py - FastAPI dependency injection.

Focus: Test all 12 dependency getter functions.
Strategy: Mock server module globals, verify each function returns correct object.
"""

from asyncio import Event, Lock, Queue
from unittest.mock import MagicMock, patch

from api_utils.dependencies import (
    get_current_ai_studio_model_id,
    get_excluded_model_ids,
    get_log_ws_manager,
    get_logger,
    get_model_list_fetch_event,
    get_page_instance,
    get_parsed_model_list,
    get_processing_lock,
    get_request_queue,
    get_server_state,
    get_worker_task,
)
from api_utils.server_state import state


def test_get_logger():
    """
    Test scenario: Get logger dependency
    Expected: Return state.logger object
    """
    mock_logger = MagicMock()

    with patch.object(state, "logger", mock_logger):
        result = get_logger()

        # Verify: Return state.logger
        assert result is mock_logger


def test_get_log_ws_manager():
    """
    Test scenario: Get WebSocket manager dependency
    Expected: Return state.log_ws_manager object
    """
    mock_ws_manager = MagicMock()

    with patch.object(state, "log_ws_manager", mock_ws_manager):
        result = get_log_ws_manager()

        # Verify: Return state.log_ws_manager
        assert result is mock_ws_manager


def test_get_request_queue():
    """
    Test scenario: Get request queue dependency
    Expected: Return state.request_queue object
    """
    mock_queue = MagicMock(spec=Queue)

    with patch.object(state, "request_queue", mock_queue):
        result = get_request_queue()

        # Verify: Return state.request_queue
        assert result is mock_queue


def test_get_processing_lock():
    """
    Test scenario: Get processing lock dependency
    Expected: Return state.processing_lock object
    """
    mock_lock = MagicMock(spec=Lock)

    with patch.object(state, "processing_lock", mock_lock):
        result = get_processing_lock()

        # Verify: Return state.processing_lock
        assert result is mock_lock


def test_get_worker_task():
    """
    Test scenario: Get worker task dependency
    Expected: Return state.worker_task object
    """
    mock_task = MagicMock()

    with patch.object(state, "worker_task", mock_task):
        result = get_worker_task()

        # Verify: Return state.worker_task
        assert result is mock_task


def test_get_server_state():
    """
    Test scenario: Get server state dependency
    Expected: Return dict containing 4 boolean flags
    """
    with (
        patch.object(state, "is_initializing", True),
        patch.object(state, "is_playwright_ready", False),
        patch.object(state, "is_browser_connected", True),
        patch.object(state, "is_page_ready", False),
    ):
        result = get_server_state()

        # Verify: Return dict contains all 4 flags
        assert isinstance(result, dict)
        assert result["is_initializing"] is True
        assert result["is_playwright_ready"] is False
        assert result["is_browser_connected"] is True
        assert result["is_page_ready"] is False


def test_get_server_state_immutable_snapshot():
    """
    Test scenario: Verify get_server_state returns immutable snapshot
    Expected: Return new dict, not original reference
    """
    with (
        patch.object(state, "is_initializing", False),
        patch.object(state, "is_playwright_ready", True),
        patch.object(state, "is_browser_connected", False),
        patch.object(state, "is_page_ready", True),
    ):
        result1 = get_server_state()
        result2 = get_server_state()

        # Verify: Each call returns a new dict
        assert result1 is not result2
        # Verify: Values are the same
        assert result1 == result2


def test_get_page_instance():
    """
    Test scenario: Get page instance dependency
    Expected: Return state.page_instance object
    """
    mock_page = MagicMock()

    with patch.object(state, "page_instance", mock_page):
        result = get_page_instance()

        # Verify: Return state.page_instance
        assert result is mock_page


def test_get_model_list_fetch_event():
    """
    Test scenario: Get model list fetch event dependency
    Expected: Return state.model_list_fetch_event object
    """
    mock_event = MagicMock(spec=Event)

    with patch.object(state, "model_list_fetch_event", mock_event):
        result = get_model_list_fetch_event()

        # Verify: Return state.model_list_fetch_event
        assert result is mock_event


def test_get_parsed_model_list():
    """
    Test scenario: Get parsed model list dependency
    Expected: Return state.parsed_model_list object
    """
    mock_model_list = [
        {"id": "gemini-1.5-pro", "object": "model"},
        {"id": "gemini-2.0-flash", "object": "model"},
    ]

    with patch.object(state, "parsed_model_list", mock_model_list):
        result = get_parsed_model_list()

        # Verify: Return state.parsed_model_list
        assert result is mock_model_list
        assert len(result) == 2


def test_get_excluded_model_ids():
    """
    Test scenario: Get excluded model IDs set dependency
    Expected: Return state.excluded_model_ids object
    """
    mock_excluded_ids = {"model-1", "model-2", "model-3"}

    with patch.object(state, "excluded_model_ids", mock_excluded_ids):
        result = get_excluded_model_ids()

        # Verify: Return state.excluded_model_ids
        assert result is mock_excluded_ids
        assert len(result) == 3


def test_get_current_ai_studio_model_id():
    """
    Test scenario: Get current AI Studio model ID dependency
    Expected: Return state.current_ai_studio_model_id object
    """
    mock_model_id = "gemini-1.5-pro"

    with patch.object(state, "current_ai_studio_model_id", mock_model_id):
        result = get_current_ai_studio_model_id()

        # Verify: Return state.current_ai_studio_model_id
        assert result == "gemini-1.5-pro"


def test_get_current_ai_studio_model_id_none():
    """
    Test scenario: Current model ID is None (initial state)
    Expected: Return None
    """
    with patch.object(state, "current_ai_studio_model_id", None):
        result = get_current_ai_studio_model_id()

        # Verify: Return None
        assert result is None
