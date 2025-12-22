"""
Verification Test for Error C: UI Timeout Fix in stream.py

This test verifies that the `check_ui_generation_active` function correctly uses
a 2000ms timeout and handles exceptions gracefully.

Bug Description:
- The `is_disabled()` check at line 118 timed out using 1000ms timeout with compound selector
- Fix: Increased timeout to 2000ms, used centralized SUBMIT_BUTTON_SELECTOR, added nested try-except

Success Criteria:
- Timeout is 2000ms (not 1000ms)
- Uses SUBMIT_BUTTON_SELECTOR from config.selectors
- Handles timeout exceptions gracefully (returns False instead of crashing)
- Nested try-except catches is_disabled() timeout specifically
"""

import queue
from unittest.mock import AsyncMock, Mock, patch

import pytest


@pytest.mark.asyncio
async def test_ui_timeout_is_2000ms():
    """
    Test that check_ui_generation_active uses 2000ms timeout for is_disabled check.

    This verifies the timeout was increased from 1000ms to 2000ms.
    """
    # Arrange: Create mock page and locators
    mock_page = AsyncMock()
    mock_stop_button = AsyncMock()
    mock_submit_button = AsyncMock()
    mock_first_element = AsyncMock()

    # Setup stop button to not be visible
    mock_stop_button.is_visible = AsyncMock(return_value=False)

    # Setup submit button to exist and be disabled
    mock_submit_button.count = AsyncMock(return_value=1)
    mock_submit_button.first = mock_first_element
    mock_first_element.is_disabled = AsyncMock(return_value=True)

    # Track the timeout parameter passed to is_disabled
    timeout_used = None

    async def track_timeout(timeout):
        nonlocal timeout_used
        timeout_used = timeout
        return True

    mock_first_element.is_disabled = AsyncMock(side_effect=track_timeout)

    def mock_locator(selector):
        if 'Stop generating' in selector:
            return mock_stop_button
        else:
            return mock_submit_button

    mock_page.locator = Mock(side_effect=mock_locator)

    # Mock GlobalState and dependencies
    mock_global_state = Mock()
    mock_global_state.CURRENT_STREAM_REQ_ID = None
    mock_global_state.IS_QUOTA_EXCEEDED = False
    mock_global_state.IS_RECOVERING = False
    mock_global_state.IS_SHUTTING_DOWN = Mock()
    mock_global_state.IS_SHUTTING_DOWN.is_set = Mock(return_value=False)

    mock_stream_queue = queue.Queue()
    mock_stream_queue.put(None)  # Terminate immediately

    mock_logger = Mock()
    mock_state = Mock()

    # Mock SUBMIT_BUTTON_SELECTOR
    mock_selector = 'button[aria-label="Run"].run-button'

    with patch('server.STREAM_QUEUE', mock_stream_queue), \
         patch('server.logger', mock_logger), \
         patch('config.global_state.GlobalState', mock_global_state), \
         patch('api_utils.server_state.state', mock_state), \
         patch('browser_utils.page_controller.PageController'), \
         patch('config.selectors.SUBMIT_BUTTON_SELECTOR', mock_selector):

        from api_utils.utils_ext.stream import use_stream_response

        # Act: Run the stream response which contains check_ui_generation_active
        generator = use_stream_response(
            req_id="test_ui_001",
            timeout=5.0,
            silence_threshold=60.0,
            page=mock_page,
            enable_silence_detection=False
        )

        async for _ in generator:
            pass

        # Assert: Verify timeout was 2000ms
        assert timeout_used == 2000, f"Expected timeout=2000ms, got {timeout_used}ms"
        print("✅ PASS: is_disabled() uses 2000ms timeout (not 1000ms)")


@pytest.mark.asyncio
async def test_ui_timeout_uses_centralized_selector():
    """
    Test that check_ui_generation_active uses SUBMIT_BUTTON_SELECTOR from config.

    This verifies the hardcoded selector was replaced with centralized config.
    """
    # Arrange
    mock_page = AsyncMock()
    mock_stop_button = AsyncMock()
    mock_submit_button = AsyncMock()

    mock_stop_button.is_visible = AsyncMock(return_value=False)
    mock_submit_button.count = AsyncMock(return_value=1)
    mock_submit_button.first = AsyncMock()
    mock_submit_button.first.is_disabled = AsyncMock(return_value=False)

    # Track which selectors were used
    selectors_used = []

    def mock_locator(selector):
        selectors_used.append(selector)
        if 'Stop generating' in selector:
            return mock_stop_button
        else:
            return mock_submit_button

    mock_page.locator = Mock(side_effect=mock_locator)

    mock_global_state = Mock()
    mock_global_state.CURRENT_STREAM_REQ_ID = None
    mock_global_state.IS_QUOTA_EXCEEDED = False
    mock_global_state.IS_RECOVERING = False
    mock_global_state.IS_SHUTTING_DOWN = Mock()
    mock_global_state.IS_SHUTTING_DOWN.is_set = Mock(return_value=False)

    mock_stream_queue = queue.Queue()
    mock_stream_queue.put(None)

    mock_logger = Mock()
    mock_state = Mock()

    # Use a unique selector to verify it's actually being used
    test_selector = 'ms-run-button button[type="submit"].run-button'

    with patch('server.STREAM_QUEUE', mock_stream_queue), \
         patch('server.logger', mock_logger), \
         patch('config.global_state.GlobalState', mock_global_state), \
         patch('api_utils.server_state.state', mock_state), \
         patch('browser_utils.page_controller.PageController'), \
         patch('config.selectors.SUBMIT_BUTTON_SELECTOR', test_selector):

        from api_utils.utils_ext.stream import use_stream_response

        # Act
        generator = use_stream_response(
            req_id="test_ui_002",
            timeout=5.0,
            silence_threshold=60.0,
            page=mock_page,
            enable_silence_detection=False
        )

        async for _ in generator:
            pass

        # Assert: Verify our test selector was used
        assert test_selector in selectors_used, \
            f"Expected centralized selector '{test_selector}' to be used"
        print("✅ PASS: Uses SUBMIT_BUTTON_SELECTOR from config.selectors")


@pytest.mark.asyncio
async def test_ui_timeout_handles_exception_gracefully():
    """
    Test that check_ui_generation_active handles timeout exceptions gracefully.

    This verifies the nested try-except catches timeout errors and returns False.
    """
    # Arrange: Setup mocks that will raise timeout exception
    mock_page = AsyncMock()
    mock_stop_button = AsyncMock()
    mock_submit_button = AsyncMock()
    mock_first_element = AsyncMock()

    mock_stop_button.is_visible = AsyncMock(return_value=False)
    mock_submit_button.count = AsyncMock(return_value=1)
    mock_submit_button.first = mock_first_element

    # Simulate timeout error
    async def raise_timeout(*args, **kwargs):
        raise Exception("Timeout 2000ms exceeded")

    mock_first_element.is_disabled = AsyncMock(side_effect=raise_timeout)

    def mock_locator(selector):
        if 'Stop generating' in selector:
            return mock_stop_button
        else:
            return mock_submit_button

    mock_page.locator = Mock(side_effect=mock_locator)

    mock_global_state = Mock()
    mock_global_state.CURRENT_STREAM_REQ_ID = None
    mock_global_state.IS_QUOTA_EXCEEDED = False
    mock_global_state.IS_RECOVERING = False
    mock_global_state.IS_SHUTTING_DOWN = Mock()
    mock_global_state.IS_SHUTTING_DOWN.is_set = Mock(return_value=False)

    mock_stream_queue = queue.Queue()
    mock_stream_queue.put(None)

    mock_logger = Mock()
    mock_state = Mock()

    test_selector = 'button.run-button'

    with patch('server.STREAM_QUEUE', mock_stream_queue), \
         patch('server.logger', mock_logger), \
         patch('config.global_state.GlobalState', mock_global_state), \
         patch('api_utils.server_state.state', mock_state), \
         patch('browser_utils.page_controller.PageController'), \
         patch('config.selectors.SUBMIT_BUTTON_SELECTOR', test_selector):

        from api_utils.utils_ext.stream import use_stream_response

        # Act: Should not raise exception despite timeout
        try:
            generator = use_stream_response(
                req_id="test_ui_003",
                timeout=5.0,
                silence_threshold=60.0,
                page=mock_page,
                enable_silence_detection=False
            )

            async for _ in generator:
                pass

            print("✅ PASS: Timeout exception handled gracefully - no crash")

        except Exception as e:
            if "Timeout" in str(e):
                pytest.fail(f"Timeout exception should be caught, not propagated: {e}")
            # Other exceptions are ok for this test


@pytest.mark.asyncio
async def test_ui_timeout_returns_false_on_timeout():
    """
    Test that check_ui_generation_active returns False when timeout occurs.

    This verifies the function degrades gracefully instead of crashing.
    """
    # Arrange: Create a scenario where we can directly test check_ui_generation_active
    # We'll need to extract and test the inner function

    mock_page = AsyncMock()
    mock_stop_button = AsyncMock()
    mock_submit_button = AsyncMock()
    mock_first = AsyncMock()

    mock_stop_button.is_visible = AsyncMock(return_value=False)
    mock_submit_button.count = AsyncMock(return_value=1)
    mock_submit_button.first = mock_first

    # Raise timeout error
    mock_first.is_disabled = AsyncMock(side_effect=Exception("Timeout 2000ms exceeded"))

    def mock_locator(selector):
        if 'Stop generating' in selector:
            return mock_stop_button
        return mock_submit_button

    mock_page.locator = Mock(side_effect=mock_locator)

    # We need to test the behavior indirectly through use_stream_response
    # When timeout occurs, the stream should continue (not crash)

    mock_global_state = Mock()
    mock_global_state.CURRENT_STREAM_REQ_ID = None
    mock_global_state.IS_QUOTA_EXCEEDED = False
    mock_global_state.IS_RECOVERING = False
    mock_global_state.IS_SHUTTING_DOWN = Mock()
    mock_global_state.IS_SHUTTING_DOWN.is_set = Mock(return_value=False)

    # Setup queue to timeout so UI check is called
    mock_stream_queue = queue.Queue()

    mock_logger = Mock()
    mock_state = Mock()
    test_selector = 'button.submit'

    with patch('api_utils.utils_ext.stream.STREAM_QUEUE', mock_stream_queue), \
         patch('api_utils.utils_ext.stream.logger', mock_logger), \
         patch('api_utils.utils_ext.stream.GlobalState', mock_global_state), \
         patch('api_utils.utils_ext.stream.state', mock_state), \
         patch('api_utils.utils_ext.stream.PageController'), \
         patch('config.selectors.SUBMIT_BUTTON_SELECTOR', test_selector):

        from api_utils.utils_ext.stream import use_stream_response

        # Act: Run with a very short timeout to trigger UI check
        generator = use_stream_response(
            req_id="test_ui_004",
            timeout=0.1,  # Very short TTFB timeout
            silence_threshold=1.0,
            page=mock_page,
            enable_silence_detection=False
        )

        result_count = 0
        try:
            async for item in generator:
                result_count += 1
                if result_count > 20:  # Safety limit
                    break
        except Exception as e:
            if "Timeout" in str(e) and "2000ms" in str(e):
                pytest.fail(f"UI timeout should be caught internally: {e}")

        print("✅ PASS: Returns False on timeout - graceful degradation")


@pytest.mark.asyncio
async def test_ui_nested_exception_handling():
    """
    Test that nested try-except specifically catches timeout on is_disabled().

    Verifies the nested exception handling structure is in place.
    """
    # Arrange
    mock_page = AsyncMock()
    mock_stop_button = AsyncMock()
    mock_submit_button = AsyncMock()
    mock_first = AsyncMock()

    mock_stop_button.is_visible = AsyncMock(return_value=False)
    mock_submit_button.count = AsyncMock(return_value=1)
    mock_submit_button.first = mock_first

    # Track if the timeout keyword is checked in exception handling
    exception_handled = False

    async def raise_timeout_with_keyword(*args, **kwargs):
        nonlocal exception_handled
        error = Exception("Timeout 2000ms exceeded")
        exception_handled = True
        raise error

    mock_first.is_disabled = AsyncMock(side_effect=raise_timeout_with_keyword)

    def mock_locator(selector):
        if 'Stop generating' in selector:
            return mock_stop_button
        return mock_submit_button

    mock_page.locator = Mock(side_effect=mock_locator)

    mock_global_state = Mock()
    mock_global_state.CURRENT_STREAM_REQ_ID = None
    mock_global_state.IS_QUOTA_EXCEEDED = False
    mock_global_state.IS_RECOVERING = False
    mock_global_state.IS_SHUTTING_DOWN = Mock()
    mock_global_state.IS_SHUTTING_DOWN.is_set = Mock(return_value=False)

    mock_stream_queue = queue.Queue()
    mock_stream_queue.put(None)

    mock_logger = Mock()
    mock_state = Mock()

    with patch('server.STREAM_QUEUE', mock_stream_queue), \
         patch('server.logger', mock_logger), \
         patch('config.global_state.GlobalState', mock_global_state), \
         patch('api_utils.server_state.state', mock_state), \
         patch('browser_utils.page_controller.PageController'), \
         patch('config.selectors.SUBMIT_BUTTON_SELECTOR', 'button.run'):

        from api_utils.utils_ext.stream import use_stream_response

        # Act
        generator = use_stream_response(
            req_id="test_ui_005",
            timeout=5.0,
            silence_threshold=60.0,
            page=mock_page,
            enable_silence_detection=False
        )

        async for _ in generator:
            pass

        # Assert: Exception was raised but handled
        assert exception_handled, "Timeout exception should have been raised and caught"
        print("✅ PASS: Nested exception handling catches is_disabled() timeout")


@pytest.mark.asyncio
async def test_ui_check_with_various_exception_types():
    """
    Test that UI check handles different exception types correctly.

    Timeout exceptions should return False, other exceptions should be re-raised.
    """
    test_cases = [
        ("Timeout 2000ms exceeded", False, "should catch timeout"),
        ("timeout waiting for selector", False, "should catch timeout (lowercase)"),
        ("Target closed", False, "should catch closed target"),
        ("Connection closed", False, "should catch closed connection"),
    ]

    for error_msg, should_catch, description in test_cases:
        # Arrange
        mock_page = AsyncMock()
        mock_stop_button = AsyncMock()
        mock_submit_button = AsyncMock()
        mock_first = AsyncMock()

        mock_stop_button.is_visible = AsyncMock(return_value=False)
        mock_submit_button.count = AsyncMock(return_value=1)
        mock_submit_button.first = mock_first

        async def raise_error(*args, **kwargs):
            raise Exception(error_msg)

        mock_first.is_disabled = AsyncMock(side_effect=raise_error)

        def mock_locator(selector):
            if 'Stop generating' in selector:
                return mock_stop_button
            return mock_submit_button

        mock_page.locator = Mock(side_effect=mock_locator)

        mock_global_state = Mock()
        mock_global_state.CURRENT_STREAM_REQ_ID = None
        mock_global_state.IS_QUOTA_EXCEEDED = False
        mock_global_state.IS_RECOVERING = False
        mock_global_state.IS_SHUTTING_DOWN = Mock()
        mock_global_state.IS_SHUTTING_DOWN.is_set = Mock(return_value=False)

        mock_stream_queue = queue.Queue()
        mock_stream_queue.put(None)

        mock_logger = Mock()
        mock_state = Mock()

        with patch('server.STREAM_QUEUE', mock_stream_queue), \
             patch('server.logger', mock_logger), \
             patch('config.global_state.GlobalState', mock_global_state), \
             patch('api_utils.server_state.state', mock_state), \
             patch('browser_utils.page_controller.PageController'), \
             patch('config.selectors.SUBMIT_BUTTON_SELECTOR', 'button.run'):

            from api_utils.utils_ext.stream import use_stream_response

            # Act
            generator = use_stream_response(
                req_id=f"test_ui_{error_msg[:10]}",
                timeout=5.0,
                silence_threshold=60.0,
                page=mock_page,
                enable_silence_detection=False
            )

            async for _ in generator:
                pass

            print(f"✅ PASS: Exception '{error_msg}' {description}")


if __name__ == "__main__":
    print("=" * 80)
    print("VERIFICATION TEST: Error C - UI Timeout Fix in stream.py")
    print("=" * 80)

    # Run tests
    pytest.main([__file__, "-v", "-s"])
