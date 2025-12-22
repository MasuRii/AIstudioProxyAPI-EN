"""
Verification Test for Error B: NameError Fix in model_switching.py

This test verifies that the `handle_model_switching` function can reference
`state.current_ai_studio_model_id` without raising a NameError.

Bug Description:
- Module `server` was referenced at lines 60, 61, 66, 69 without being imported
- Used `server.current_ai_studio_model_id` which caused NameError
- Fix: Replaced all `server` references with `state` (already imported from api_utils.server_state)

Success Criteria:
- Function executes without NameError
- `state.current_ai_studio_model_id` is accessible throughout the function
- All references use `state` consistently, not undefined `server`
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest


@pytest.mark.asyncio
async def test_handle_model_switching_no_name_error():
    """
    Test that handle_model_switching uses state.current_ai_studio_model_id without NameError.
    
    This verifies the fix: all `server` references replaced with `state`.
    """
    # Arrange: Create mock context with all required fields
    mock_logger = Mock()
    mock_logger.info = Mock()
    mock_logger.warning = Mock()

    mock_page = AsyncMock()
    mock_model_switching_lock = AsyncMock()
    mock_model_switching_lock.__aenter__ = AsyncMock(return_value=None)
    mock_model_switching_lock.__aexit__ = AsyncMock(return_value=None)

    # Create mock state object
    mock_state = Mock()
    mock_state.current_ai_studio_model_id = "gemini-2.0-flash-exp"

    context = {
        "needs_model_switching": True,
        "logger": mock_logger,
        "page": mock_page,
        "model_switching_lock": mock_model_switching_lock,
        "model_id_to_use": "gemini-exp-1206",
        "model_actually_switched": False,
        "current_ai_studio_model_id": "gemini-2.0-flash-exp"
    }

    # Mock the browser_utils.switch_ai_studio_model function
    async def mock_switch_model(page, model_id, req_id):
        return True  # Simulate successful switch

    with patch('api_utils.model_switching.state', mock_state), \
         patch('api_utils.model_switching.switch_ai_studio_model', new=mock_switch_model):

        from api_utils.model_switching import handle_model_switching

        # Act: Call the function - should not raise NameError
        try:
            result_context = await handle_model_switching(
                req_id="test_req_model_001",
                context=context
            )

            # Assert: Verify state was accessed correctly
            assert mock_state.current_ai_studio_model_id == "gemini-exp-1206", \
                "State should have been updated to new model"

            # Verify logger was called with state values (not server values)
            assert mock_logger.info.called, "Logger should have been called"

            # Check the log messages contain the model switching info
            log_messages = [str(call[0][0]) for call in mock_logger.info.call_args_list]
            preparing_log = [msg for msg in log_messages if "Preparing to switch model" in msg]
            success_log = [msg for msg in log_messages if "Model switched successfully" in msg]

            assert len(preparing_log) > 0, "Should log preparation message"
            assert len(success_log) > 0, "Should log success message"

            # Verify the logs contain model IDs (proving state was accessible)
            assert "gemini-2.0-flash-exp" in preparing_log[0], "Should reference old model"
            assert "gemini-exp-1206" in preparing_log[0], "Should reference new model"
            assert "gemini-exp-1206" in success_log[0], "Should confirm new model"

            print("✅ PASS: No NameError - state.current_ai_studio_model_id is accessible")
            print("✅ PASS: Model switching logic uses state correctly")

        except NameError as e:
            pytest.fail(f"NameError should not occur: {e}")


@pytest.mark.asyncio
async def test_handle_model_switching_state_not_server():
    """
    Test that handle_model_switching uses 'state' object, not undefined 'server'.
    
    This explicitly verifies that no reference to 'server' module exists.
    """
    # Arrange
    mock_logger = Mock()
    mock_page = AsyncMock()
    mock_lock = AsyncMock()
    mock_lock.__aenter__ = AsyncMock(return_value=None)
    mock_lock.__aexit__ = AsyncMock(return_value=None)

    mock_state = Mock()
    mock_state.current_ai_studio_model_id = "model-a"

    context = {
        "needs_model_switching": True,
        "logger": mock_logger,
        "page": mock_page,
        "model_switching_lock": mock_lock,
        "model_id_to_use": "model-b",
        "model_actually_switched": False,
        "current_ai_studio_model_id": "model-a"
    }

    async def mock_switch(page, model_id, req_id):
        return True

    # Ensure 'server' module is NOT available (would cause NameError if referenced)
    import sys
    server_module_existed = 'server' in sys.modules
    if server_module_existed:
        original_server = sys.modules['server']
        del sys.modules['server']

    try:
        with patch('api_utils.model_switching.state', mock_state), \
             patch('api_utils.model_switching.switch_ai_studio_model', new=mock_switch):

            from api_utils.model_switching import handle_model_switching

            # Act: Should work without 'server' module
            result = await handle_model_switching(
                req_id="test_req_model_002",
                context=context
            )

            # Assert: Verify it completed successfully
            assert result is not None, "Should return context"
            assert mock_state.current_ai_studio_model_id == "model-b", "Should update state"

            print("✅ PASS: Function works without 'server' module - uses 'state' correctly")

    except NameError as e:
        if "'server' is not defined" in str(e) or "name 'server' is not defined" in str(e):
            pytest.fail(f"Function still references undefined 'server': {e}")
        raise
    finally:
        # Restore server module if it existed
        if server_module_existed:
            sys.modules['server'] = original_server


@pytest.mark.asyncio
async def test_handle_model_switch_failure_uses_state():
    """
    Test that _handle_model_switch_failure also uses state, not server.
    
    According to bug fix design, this function also had 'import server' removed.
    """
    # Arrange
    mock_logger = Mock()
    mock_page = AsyncMock()
    mock_lock = AsyncMock()
    mock_lock.__aenter__ = AsyncMock(return_value=None)
    mock_lock.__aexit__ = AsyncMock(return_value=None)

    mock_state = Mock()
    mock_state.current_ai_studio_model_id = "original-model"

    context = {
        "needs_model_switching": True,
        "logger": mock_logger,
        "page": mock_page,
        "model_switching_lock": mock_lock,
        "model_id_to_use": "new-model",
        "model_actually_switched": False,
        "current_ai_studio_model_id": "original-model"
    }

    # Mock switch to fail
    async def mock_switch_fail(page, model_id, req_id):
        return False  # Simulate failure

    # Mock http_error to raise exception
    class MockHTTPError(Exception):
        pass

    def mock_http_error(code, message):
        return MockHTTPError(message)

    with patch('api_utils.model_switching.state', mock_state), \
         patch('api_utils.model_switching.switch_ai_studio_model', new=mock_switch_fail), \
         patch('api_utils.model_switching.http_error', side_effect=mock_http_error):

        from api_utils.model_switching import handle_model_switching

        # Act & Assert: Should raise MockHTTPError (not NameError)
        try:
            await handle_model_switching(
                req_id="test_req_model_003",
                context=context
            )
            pytest.fail("Should have raised MockHTTPError on switch failure")
        except MockHTTPError:
            # Expected - verify state was used to restore original model
            assert mock_state.current_ai_studio_model_id == "original-model", \
                "State should be restored to original model on failure"
            print("✅ PASS: Failure handler uses state.current_ai_studio_model_id correctly")
        except NameError as e:
            pytest.fail(f"NameError should not occur in failure handler: {e}")


@pytest.mark.asyncio
async def test_model_switching_consistency_check():
    """
    Test that all model ID references use state consistently.
    
    Verifies consistency across the entire model switching flow.
    """
    # Arrange
    mock_logger = Mock()
    mock_page = AsyncMock()
    mock_lock = AsyncMock()
    mock_lock.__aenter__ = AsyncMock(return_value=None)
    mock_lock.__aexit__ = AsyncMock(return_value=None)

    # Track all accesses to state.current_ai_studio_model_id
    access_log = []

    class StateTracker:
        def __init__(self):
            self._model_id = "initial-model"

        @property
        def current_ai_studio_model_id(self):
            access_log.append(("read", self._model_id))
            return self._model_id

        @current_ai_studio_model_id.setter
        def current_ai_studio_model_id(self, value):
            access_log.append(("write", value))
            self._model_id = value

    mock_state = StateTracker()

    context = {
        "needs_model_switching": True,
        "logger": mock_logger,
        "page": mock_page,
        "model_switching_lock": mock_lock,
        "model_id_to_use": "target-model",
        "model_actually_switched": False,
        "current_ai_studio_model_id": "initial-model"
    }

    async def mock_switch(page, model_id, req_id):
        return True

    with patch('api_utils.model_switching.state', mock_state), \
         patch('api_utils.model_switching.switch_ai_studio_model', new=mock_switch):

        from api_utils.model_switching import handle_model_switching

        # Act
        await handle_model_switching(
            req_id="test_req_model_004",
            context=context
        )

        # Assert: Verify state was accessed multiple times
        assert len(access_log) > 0, "State should have been accessed"

        # Should have: read (comparison), write (update), read (logging)
        read_accesses = [a for a in access_log if a[0] == "read"]
        write_accesses = [a for a in access_log if a[0] == "write"]

        assert len(read_accesses) >= 2, "Should read state at least twice (compare, log)"
        assert len(write_accesses) >= 1, "Should write state at least once (update)"

        # Final state should be target model
        final_write = write_accesses[-1]
        assert final_write[1] == "target-model", "Should update to target model"

        print("✅ PASS: All model ID accesses use state consistently")
        print(f"   - Read operations: {len(read_accesses)}")
        print(f"   - Write operations: {len(write_accesses)}")


@pytest.mark.asyncio
async def test_no_model_switch_needed():
    """
    Test that when models match, no switching occurs but state is still accessible.
    
    Edge case: Current model == target model.
    """
    # Arrange
    mock_logger = Mock()
    mock_page = AsyncMock()
    mock_lock = AsyncMock()
    mock_lock.__aenter__ = AsyncMock(return_value=None)
    mock_lock.__aexit__ = AsyncMock(return_value=None)

    mock_state = Mock()
    mock_state.current_ai_studio_model_id = "same-model"

    context = {
        "needs_model_switching": True,
        "logger": mock_logger,
        "page": mock_page,
        "model_switching_lock": mock_lock,
        "model_id_to_use": "same-model",  # Same as current
        "model_actually_switched": False,
        "current_ai_studio_model_id": "same-model"
    }

    switch_called = False

    async def mock_switch(page, model_id, req_id):
        nonlocal switch_called
        switch_called = True
        return True

    with patch('api_utils.model_switching.state', mock_state), \
         patch('api_utils.model_switching.switch_ai_studio_model', new=mock_switch):

        from api_utils.model_switching import handle_model_switching

        # Act
        result = await handle_model_switching(
            req_id="test_req_model_005",
            context=context
        )

        # Assert: Switch should not be called when models match
        assert not switch_called, "Should not attempt switch when models match"
        assert result is not None, "Should return context"

        print("✅ PASS: No switching when models match - state accessible for comparison")


if __name__ == "__main__":
    print("=" * 80)
    print("VERIFICATION TEST: Error B - NameError Fix in model_switching.py")
    print("=" * 80)

    # Run tests
    pytest.main([__file__, "-v", "-s"])
