"""
Verification Test for Error A: UnboundLocalError Fix in stream.py

This test verifies that the `use_stream_response` function can start without
hitting an UnboundLocalError when referencing `max_empty_retries` in logging.

Bug Description:
- Variable `max_empty_retries` was referenced in logging at line 55 before being defined at line 84
- Fix: Moved logging statement to line 84, AFTER variable initialization

Success Criteria:
- Function initialization completes without UnboundLocalError
- Variable `max_empty_retries` is accessible when logging occurs
- Logging statement includes correct max_empty_retries value
"""

import queue
from unittest.mock import AsyncMock, Mock, patch

import pytest


@pytest.mark.asyncio
async def test_stream_response_no_unbound_local_error():
    """
    Test that use_stream_response initializes without UnboundLocalError.

    This test verifies that max_empty_retries is defined before it's used in logging.
    """
    # Arrange: Mock all dependencies
    mock_stream_queue = queue.Queue()
    mock_stream_queue.put(None)  # Signal termination immediately

    mock_logger = Mock()
    mock_logger.info = Mock()
    mock_logger.warning = Mock()
    mock_logger.error = Mock()
    mock_logger.debug = Mock()

    mock_page = AsyncMock()

    # Mock GlobalState
    mock_global_state = Mock()
    mock_global_state.CURRENT_STREAM_REQ_ID = None
    mock_global_state.IS_QUOTA_EXCEEDED = False
    mock_global_state.IS_RECOVERING = False
    mock_global_state.IS_SHUTTING_DOWN = Mock()
    mock_global_state.IS_SHUTTING_DOWN.is_set = Mock(return_value=False)
    mock_global_state.LAST_ROTATION_TIMESTAMP = 0.0

    # Mock state
    mock_state = Mock()

    with patch('server.STREAM_QUEUE', mock_stream_queue), \
         patch('server.logger', mock_logger), \
         patch('config.global_state.GlobalState', mock_global_state), \
         patch('api_utils.server_state.state', mock_state), \
         patch('browser_utils.page_controller.PageController'):

        from api_utils.utils_ext.stream import use_stream_response

        # Act: Call the function - should not raise UnboundLocalError
        try:
            generator = use_stream_response(
                req_id="test_req_001",
                timeout=5.0,
                silence_threshold=60.0,
                page=mock_page,
                check_client_disconnected=None,
                stream_start_time=0.0,
                enable_silence_detection=True
            )

            # Consume the generator (will exit immediately due to None in queue)
            async for _ in generator:
                pass

            # Assert: Check that logger.info was called with max_empty_retries
            assert mock_logger.info.called, "Logger should have been called"

            # Find the call that contains "Starting stream response"
            starting_log_call = None
            for call in mock_logger.info.call_args_list:
                args = call[0]
                if args and "Starting stream response" in str(args[0]):
                    starting_log_call = args[0]
                    break

            assert starting_log_call is not None, "Should have logged 'Starting stream response'"
            assert "Max Retries:" in starting_log_call, "Log should contain 'Max Retries:'"

            # Verify max_empty_retries value is present (not causing UnboundLocalError)
            # The pattern should be: "Max Retries: <number>"
            import re
            match = re.search(r'Max Retries: (\d+)', starting_log_call)
            assert match is not None, "Max Retries value should be present in log"

            max_retries_value = int(match.group(1))
            # For timeout=5.0 and silence_threshold=60.0:
            # initial_wait_limit = int(5.0 * 10) = 50
            # silence_wait_limit = int(60.0 * 10) = 600
            # max_empty_retries = max(600, 50) = 600
            assert max_retries_value == 600, f"Expected max_empty_retries=600, got {max_retries_value}"

            print("✅ PASS: No UnboundLocalError - max_empty_retries is defined before use")
            print(f"✅ PASS: max_empty_retries value correctly calculated as {max_retries_value}")

        except UnboundLocalError as e:
            pytest.fail(f"UnboundLocalError should not occur: {e}")


@pytest.mark.asyncio
async def test_stream_response_variable_initialization_order():
    """
    Test that max_empty_retries is initialized BEFORE the logging statement.

    This verifies the execution order is correct.
    """
    # Arrange: Mock dependencies
    mock_stream_queue = queue.Queue()
    mock_stream_queue.put(None)  # Terminate immediately

    initialization_order = []

    # Create a custom logger that tracks when logging occurs
    original_info = Mock()

    def track_logging(*args, **kwargs):
        if args and "Starting stream response" in str(args[0]):
            initialization_order.append("logging_called")
        return original_info(*args, **kwargs)

    mock_logger = Mock()
    mock_logger.info = Mock(side_effect=track_logging)
    mock_logger.warning = Mock()
    mock_logger.error = Mock()
    mock_logger.debug = Mock()

    mock_page = AsyncMock()

    # Mock GlobalState
    mock_global_state = Mock()
    mock_global_state.CURRENT_STREAM_REQ_ID = None
    mock_global_state.IS_QUOTA_EXCEEDED = False
    mock_global_state.IS_RECOVERING = False
    mock_global_state.IS_SHUTTING_DOWN = Mock()
    mock_global_state.IS_SHUTTING_DOWN.is_set = Mock(return_value=False)
    mock_global_state.LAST_ROTATION_TIMESTAMP = 0.0

    mock_state = Mock()

    with patch('server.STREAM_QUEUE', mock_stream_queue), \
         patch('server.logger', mock_logger), \
         patch('config.global_state.GlobalState', mock_global_state), \
         patch('api_utils.server_state.state', mock_state), \
         patch('browser_utils.page_controller.PageController'):

        from api_utils.utils_ext.stream import use_stream_response

        # Act
        generator = use_stream_response(
            req_id="test_req_002",
            timeout=5.0,
            silence_threshold=60.0,
            page=mock_page
        )

        async for _ in generator:
            pass

        # Assert: Verify logging was called (proving no UnboundLocalError occurred)
        assert "logging_called" in initialization_order, "Logging should have been called without error"
        print("✅ PASS: Variable initialization happens before logging - no execution order error")


@pytest.mark.asyncio
async def test_stream_response_with_various_timeout_values():
    """
    Test max_empty_retries calculation with various timeout and silence threshold values.

    Verifies the fix works correctly with different parameter combinations.
    """
    test_cases = [
        # (timeout, silence_threshold, expected_max_empty_retries)
        (5.0, 60.0, 600),    # silence_threshold larger
        (10.0, 5.0, 100),    # timeout larger
        (3.0, 3.0, 30),      # equal values
        (1.0, 120.0, 1200),  # large silence_threshold
    ]

    for timeout, silence_threshold, expected_max_retries in test_cases:
        # Arrange
        mock_stream_queue = queue.Queue()
        mock_stream_queue.put(None)

        mock_logger = Mock()
        mock_page = AsyncMock()

        mock_global_state = Mock()
        mock_global_state.CURRENT_STREAM_REQ_ID = None
        mock_global_state.IS_QUOTA_EXCEEDED = False
        mock_global_state.IS_RECOVERING = False
        mock_global_state.IS_SHUTTING_DOWN = Mock()
        mock_global_state.IS_SHUTTING_DOWN.is_set = Mock(return_value=False)
        mock_global_state.LAST_ROTATION_TIMESTAMP = 0.0

        mock_state = Mock()

        with patch('server.STREAM_QUEUE', mock_stream_queue), \
             patch('server.logger', mock_logger), \
             patch('config.global_state.GlobalState', mock_global_state), \
             patch('api_utils.server_state.state', mock_state), \
             patch('browser_utils.page_controller.PageController'):

            from api_utils.utils_ext.stream import use_stream_response

            # Act
            generator = use_stream_response(
                req_id=f"test_req_{timeout}_{silence_threshold}",
                timeout=timeout,
                silence_threshold=silence_threshold,
                page=mock_page
            )

            async for _ in generator:
                pass

            # Assert: Verify correct max_empty_retries value in log
            log_message = None
            for call in mock_logger.info.call_args_list:
                args = call[0]
                if args and "Starting stream response" in str(args[0]):
                    log_message = args[0]
                    break

            assert log_message is not None, f"Should log for timeout={timeout}, silence={silence_threshold}"

            import re
            match = re.search(r'Max Retries: (\d+)', log_message)
            assert match is not None, f"Max Retries should be in log for timeout={timeout}"

            actual_max_retries = int(match.group(1))
            assert actual_max_retries == expected_max_retries, \
                f"For timeout={timeout}, silence={silence_threshold}: expected {expected_max_retries}, got {actual_max_retries}"

        print(f"✅ PASS: Correct max_empty_retries={expected_max_retries} for timeout={timeout}s, silence={silence_threshold}s")


if __name__ == "__main__":
    print("=" * 80)
    print("VERIFICATION TEST: Error A - UnboundLocalError Fix in stream.py")
    print("=" * 80)

    # Run tests
    pytest.main([__file__, "-v", "-s"])
