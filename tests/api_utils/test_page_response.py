"""
Tests for api_utils/page_response.py - Response element location.

Test Strategy:
- Mock only external boundaries: Playwright page and expect_async
- Use fixtures to reduce mock duplication (page with locator chain)
- Organize into test classes by error type
- Test success path, timeout handling, error paths

Coverage Target: 100% (simple 33-line file)
Mock Budget: <40 (down from ~56)
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from playwright.async_api import Error as PlaywrightAsyncError

from api_utils.page_response import locate_response_elements
from models.exceptions import ClientDisconnectedError


@pytest.fixture
def mock_page_response_setup():
    """Fixture providing common mocks for page_response tests."""
    logger = MagicMock()
    page = MagicMock()
    check_client_disconnected = MagicMock()

    # Mock locator chain: page.locator().last.locator()
    response_container_locator = MagicMock()
    response_element_locator = MagicMock()
    page.locator.return_value.last = response_container_locator
    response_container_locator.locator.return_value = response_element_locator

    return {
        "logger": logger,
        "page": page,
        "check_disconnect": check_client_disconnected,
        "container_locator": response_container_locator,
        "element_locator": response_element_locator,
    }


class TestLocateResponseElementsSuccess:
    """Tests for successful response element location."""

    @pytest.mark.asyncio
    async def test_successful_location_completes_without_error(
        self, mock_page_response_setup
    ):
        """Test normal success path completes without raising."""
        setup = mock_page_response_setup

        # Mock expect_async to succeed immediately
        with patch("api_utils.page_response.expect_async") as mock_expect:
            mock_expect_result = AsyncMock()
            mock_expect_result.to_be_attached = AsyncMock()
            mock_expect.return_value = mock_expect_result

            # Should not raise
            await locate_response_elements(
                setup["page"],
                "req1",
                setup["logger"],
                setup["check_disconnect"],
            )

    @pytest.mark.asyncio
    async def test_success_logs_start_and_completion_messages(
        self, mock_page_response_setup
    ):
        """Test success path logs correct messages (lines 16, 24)."""
        setup = mock_page_response_setup

        with patch("api_utils.page_response.expect_async") as mock_expect:
            mock_expect_result = AsyncMock()
            mock_expect_result.to_be_attached = AsyncMock()
            mock_expect.return_value = mock_expect_result

            await locate_response_elements(
                setup["page"],
                "req1",
                setup["logger"],
                setup["check_disconnect"],
            )

            # Verify logger.info called twice (lines 16, 24)
            assert setup["logger"].info.call_count == 2
            assert "定位响应元素..." in setup["logger"].info.call_args_list[0][0][0]
            assert "响应元素已定位。" in setup["logger"].info.call_args_list[1][0][0]

    @pytest.mark.asyncio
    async def test_success_checks_client_disconnect_after_container(
        self, mock_page_response_setup
    ):
        """Test disconnect check happens after container attached (line 22)."""
        setup = mock_page_response_setup

        with patch("api_utils.page_response.expect_async") as mock_expect:
            mock_expect_result = AsyncMock()
            mock_expect_result.to_be_attached = AsyncMock()
            mock_expect.return_value = mock_expect_result

            await locate_response_elements(
                setup["page"],
                "req1",
                setup["logger"],
                setup["check_disconnect"],
            )

            # Verify check_client_disconnected called (line 22)
            setup["check_disconnect"].assert_called_once_with(
                "After Response Container Attached: "
            )

    @pytest.mark.asyncio
    async def test_success_waits_for_both_container_and_element(
        self, mock_page_response_setup
    ):
        """Test both locators are awaited with expect_async."""
        setup = mock_page_response_setup

        with patch("api_utils.page_response.expect_async") as mock_expect:
            mock_expect_result = AsyncMock()
            mock_expect_result.to_be_attached = AsyncMock()
            mock_expect.return_value = mock_expect_result

            await locate_response_elements(
                setup["page"],
                "req1",
                setup["logger"],
                setup["check_disconnect"],
            )

            # Verify expect_async called twice (container + element)
            assert mock_expect.call_count == 2
            # Verify to_be_attached called twice
            assert mock_expect_result.to_be_attached.call_count == 2

    @pytest.mark.asyncio
    async def test_locator_chain_uses_correct_selectors(self, mock_page_response_setup):
        """Test correct selector usage (lines 17-18)."""
        setup = mock_page_response_setup

        with patch("api_utils.page_response.expect_async") as mock_expect:
            mock_expect_result = AsyncMock()
            mock_expect_result.to_be_attached = AsyncMock()
            mock_expect.return_value = mock_expect_result

            await locate_response_elements(
                setup["page"],
                "req1",
                setup["logger"],
                setup["check_disconnect"],
            )

            # Verify page.locator called with RESPONSE_CONTAINER_SELECTOR
            from config import RESPONSE_CONTAINER_SELECTOR

            setup["page"].locator.assert_called_once_with(RESPONSE_CONTAINER_SELECTOR)

            # Verify container.locator called with RESPONSE_TEXT_SELECTOR
            from config import RESPONSE_TEXT_SELECTOR

            setup["container_locator"].locator.assert_called_once_with(
                RESPONSE_TEXT_SELECTOR
            )

    @pytest.mark.asyncio
    async def test_timeout_values_are_correct(self, mock_page_response_setup):
        """Test timeout parameters: container=20000ms, element=90000ms (lines 21, 23)."""
        setup = mock_page_response_setup

        with patch("api_utils.page_response.expect_async") as mock_expect:
            mock_expect_result = AsyncMock()
            mock_expect_result.to_be_attached = AsyncMock()
            mock_expect.return_value = mock_expect_result

            await locate_response_elements(
                setup["page"],
                "req1",
                setup["logger"],
                setup["check_disconnect"],
            )

            # Verify timeout parameters
            calls = mock_expect_result.to_be_attached.call_args_list
            assert calls[0][1]["timeout"] == 20000  # Container timeout
            assert calls[1][1]["timeout"] == 90000  # Element timeout


class TestLocateResponseElementsTimeouts:
    """Tests for timeout error handling."""

    @pytest.mark.asyncio
    async def test_container_timeout_raises_http_502(self, mock_page_response_setup):
        """Test PlaywrightAsyncError during container wait raises 502 (lines 25-28)."""
        setup = mock_page_response_setup

        # Mock expect_async to raise PlaywrightAsyncError on first call
        with patch("api_utils.page_response.expect_async") as mock_expect:
            mock_expect_result = AsyncMock()
            mock_expect_result.to_be_attached = AsyncMock(
                side_effect=PlaywrightAsyncError("Timeout 20000ms exceeded")
            )
            mock_expect.return_value = mock_expect_result

            with pytest.raises(HTTPException) as exc_info:
                await locate_response_elements(
                    setup["page"],
                    "req1",
                    setup["logger"],
                    setup["check_disconnect"],
                )

            # Verify HTTPException status code 502 (upstream error)
            assert exc_info.value.status_code == 502
            assert "定位AI Studio响应元素失败" in exc_info.value.detail
            assert "Timeout 20000ms exceeded" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_element_timeout_raises_http_502(self, mock_page_response_setup):
        """Test asyncio.TimeoutError during element wait raises 502 (lines 25-28)."""
        setup = mock_page_response_setup

        # Mock expect_async: succeed on first call (container), fail on second (element)
        with patch("api_utils.page_response.expect_async") as mock_expect:
            mock_expect_result_container = AsyncMock()
            mock_expect_result_container.to_be_attached = AsyncMock()

            mock_expect_result_element = AsyncMock()
            mock_expect_result_element.to_be_attached = AsyncMock(
                side_effect=asyncio.TimeoutError("90000ms timeout")
            )

            # First call returns container result, second call returns element result
            mock_expect.side_effect = [
                mock_expect_result_container,
                mock_expect_result_element,
            ]

            with pytest.raises(HTTPException) as exc_info:
                await locate_response_elements(
                    setup["page"],
                    "req1",
                    setup["logger"],
                    setup["check_disconnect"],
                )

            # Verify HTTPException status code 502 (upstream error)
            assert exc_info.value.status_code == 502
            assert "定位AI Studio响应元素失败" in exc_info.value.detail

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "exception_type,error_message",
        [
            (PlaywrightAsyncError, "Playwright timeout error"),
            (asyncio.TimeoutError, "Async timeout error"),
        ],
    )
    async def test_timeout_error_types_both_raise_502(
        self, mock_page_response_setup, exception_type, error_message
    ):
        """Test both PlaywrightAsyncError and asyncio.TimeoutError raise 502."""
        setup = mock_page_response_setup

        with patch("api_utils.page_response.expect_async") as mock_expect:
            mock_expect_result = AsyncMock()
            mock_expect_result.to_be_attached = AsyncMock(
                side_effect=exception_type(error_message)
            )
            mock_expect.return_value = mock_expect_result

            with pytest.raises(HTTPException) as exc_info:
                await locate_response_elements(
                    setup["page"],
                    "req1",
                    setup["logger"],
                    setup["check_disconnect"],
                )

            assert exc_info.value.status_code == 502
            assert error_message in exc_info.value.detail


class TestLocateResponseElementsErrors:
    """Tests for error handling (client disconnect, generic errors)."""

    @pytest.mark.asyncio
    async def test_client_disconnect_raises_http_500(self, mock_page_response_setup):
        """Test ClientDisconnectedError raises 500 (generic Exception handler)."""
        setup = mock_page_response_setup
        setup["check_disconnect"].side_effect = ClientDisconnectedError(
            "Client disconnected"
        )

        # Mock expect_async to succeed (but check_disconnect raises first)
        with patch("api_utils.page_response.expect_async") as mock_expect:
            mock_expect_result = AsyncMock()
            mock_expect_result.to_be_attached = AsyncMock()
            mock_expect.return_value = mock_expect_result

            with pytest.raises(HTTPException) as exc_info:
                await locate_response_elements(
                    setup["page"],
                    "req1",
                    setup["logger"],
                    setup["check_disconnect"],
                )

            # Verify HTTPException status code 500 (server error from generic handler)
            assert exc_info.value.status_code == 500
            assert "定位响应元素时意外错误" in exc_info.value.detail
            # Verify check_disconnect was called (line 22)
            setup["check_disconnect"].assert_called_once()

    @pytest.mark.asyncio
    async def test_generic_exception_raises_http_500(self, mock_page_response_setup):
        """Test unexpected exception raises 500 with error details (lines 29-32)."""
        setup = mock_page_response_setup

        # Mock expect_async to raise generic exception
        with patch("api_utils.page_response.expect_async") as mock_expect:
            mock_expect.side_effect = ValueError("Unexpected validation error")

            with pytest.raises(HTTPException) as exc_info:
                await locate_response_elements(
                    setup["page"],
                    "req1",
                    setup["logger"],
                    setup["check_disconnect"],
                )

            # Verify HTTPException status code 500 (server error)
            assert exc_info.value.status_code == 500
            assert "定位响应元素时意外错误" in exc_info.value.detail
            assert "Unexpected validation error" in exc_info.value.detail

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "exception_class,error_msg",
        [
            (ValueError, "Validation failed"),
            (RuntimeError, "Runtime issue"),
            (AttributeError, "Missing attribute"),
        ],
    )
    async def test_various_generic_exceptions_raise_500(
        self, mock_page_response_setup, exception_class, error_msg
    ):
        """Test various generic exceptions are caught and raise 500."""
        setup = mock_page_response_setup

        with patch("api_utils.page_response.expect_async") as mock_expect:
            mock_expect.side_effect = exception_class(error_msg)

            with pytest.raises(HTTPException) as exc_info:
                await locate_response_elements(
                    setup["page"],
                    "req1",
                    setup["logger"],
                    setup["check_disconnect"],
                )

            assert exc_info.value.status_code == 500
            assert "定位响应元素时意外错误" in exc_info.value.detail
            assert error_msg in exc_info.value.detail
