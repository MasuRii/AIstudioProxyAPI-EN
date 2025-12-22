"""
High-quality tests for api_utils/server_state.py - Server state management.

Focus: Test ServerState class methods and module-level __getattr__.
Strategy: Test clear_debug_logs and backward compatibility __getattr__.
"""

import pytest

from api_utils import server_state
from api_utils.server_state import ServerState, state


@pytest.fixture
def fresh_state():
    """Provide a fresh ServerState instance for each test."""
    test_state = ServerState()
    yield test_state
    test_state.reset()


def test_clear_debug_logs(fresh_state):
    """
    Test scenario: Clear debug logs
    Expected: console_logs and network_log are reset (lines 96-97)
    """
    # Setup: Fill some log data
    fresh_state.console_logs = [
        {"level": "info", "message": "test1"},
        {"level": "error", "message": "test2"},
    ]
    fresh_state.network_log = {
        "requests": [{"url": "http://example.com", "method": "GET"}],
        "responses": [{"status": 200, "body": "OK"}],
    }

    # Execute: Clear logs
    fresh_state.clear_debug_logs()

    # Verify: Logs cleared (lines 96-97)
    assert fresh_state.console_logs == []
    assert fresh_state.network_log == {"requests": [], "responses": []}


def test_module_getattr_success():
    """
    Test scenario: Access state attribute using __getattr__
    Expected: Return state attribute value (line 135)
    """
    # Access logger via __getattr__
    logger_via_getattr = server_state.logger

    # Verify: Return state.logger (line 135 triggers getattr)
    assert logger_via_getattr is state.logger


def test_module_getattr_missing_attribute():
    """
    Test scenario: Access non-existent attribute using __getattr__
    Expected: Throw AttributeError (line 136)
    """
    with pytest.raises(AttributeError) as exc_info:
        _ = server_state.nonexistent_attribute

    # Verify: Error message
    assert "has no attribute 'nonexistent_attribute'" in str(exc_info.value)


def test_state_reset():
    """
    Test scenario: Reset state
    Expected: All attributes restore to initial values
    """
    # Modify some states
    state.is_page_ready = True
    state.current_ai_studio_model_id = "test-model"
    state.console_logs = [{"test": "data"}]

    # Reset
    state.reset()

    # Verify: Restore initial values
    assert state.is_page_ready is False
    assert state.current_ai_studio_model_id is None
    assert state.console_logs == []


def test_state_singleton():
    """
    Test scenario: Verify state is a singleton
    Expected: Imported state is the same instance
    """
    from api_utils.server_state import state as state2

    # Verify: Is the same instance
    assert state is state2
