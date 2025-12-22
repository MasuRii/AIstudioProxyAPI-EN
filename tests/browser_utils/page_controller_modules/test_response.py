from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from browser_utils.page_controller_modules.response import ResponseController
from models import ClientDisconnectedError


@pytest.fixture
def response_controller(mock_page):
    logger = MagicMock()
    req_id = "test_req_id"
    return ResponseController(mock_page, logger, req_id)


@pytest.mark.asyncio
async def test_get_response_success(response_controller, mock_page):
    """Test successful response retrieval."""
    check_client_disconnected = MagicMock(return_value=False)
    expected_content = "Test response content"

    # Mock locators
    response_container = AsyncMock()
    response_element = AsyncMock()

    mock_page.locator.return_value.last = response_container
    response_container.locator.return_value = response_element

    # Mock helper functions
    with (
        patch(
            "browser_utils.page_controller_modules.response.expect_async",
            new_callable=MagicMock,
        ) as mock_expect,
        patch(
            "browser_utils.page_controller_modules.response._wait_for_response_completion",
            new_callable=AsyncMock,
        ) as mock_wait,
        patch(
            "browser_utils.page_controller_modules.response._get_final_response_content",
            new_callable=AsyncMock,
        ) as mock_get_content,
    ):
        mock_expect.return_value.to_be_attached = AsyncMock()
        mock_wait.return_value = True
        mock_get_content.return_value = expected_content

        result = await response_controller.get_response(check_client_disconnected)

        assert result == expected_content
        mock_expect.return_value.to_be_attached.assert_called()
        mock_wait.assert_called()
        mock_get_content.assert_called()


@pytest.mark.asyncio
async def test_get_response_client_disconnected(response_controller, mock_page):
    """Test response retrieval with client disconnection."""
    check_client_disconnected = MagicMock(
        side_effect=lambda x: True
        if "Retrieve Response - Response element attached" in x
        else False
    )

    # Mock locators
    response_container = AsyncMock()
    response_element = AsyncMock()

    mock_page.locator.return_value.last = response_container
    response_container.locator.return_value = response_element

    with patch(
        "browser_utils.page_controller_modules.response.expect_async",
        new_callable=MagicMock,
    ) as mock_expect:
        mock_expect.return_value.to_be_attached = AsyncMock()

        with pytest.raises(ClientDisconnectedError):
            await response_controller.get_response(check_client_disconnected)


@pytest.mark.asyncio
async def test_get_response_empty_content(response_controller, mock_page):
    """Test response retrieval when content is empty."""
    check_client_disconnected = MagicMock(return_value=False)

    # Mock locators
    response_container = AsyncMock()
    response_element = AsyncMock()

    mock_page.locator.return_value.last = response_container
    response_container.locator.return_value = response_element

    with (
        patch(
            "browser_utils.page_controller_modules.response.expect_async",
            new_callable=MagicMock,
        ) as mock_expect,
        patch(
            "browser_utils.page_controller_modules.response._wait_for_response_completion",
            new_callable=AsyncMock,
        ) as mock_wait,
        patch(
            "browser_utils.page_controller_modules.response._get_final_response_content",
            new_callable=AsyncMock,
        ) as mock_get_content,
        patch(
            "browser_utils.page_controller_modules.response.save_error_snapshot",
            new_callable=AsyncMock,
        ) as mock_save_snapshot,
    ):
        mock_expect.return_value.to_be_attached = AsyncMock()
        mock_wait.return_value = True
        mock_get_content.return_value = ""

        result = await response_controller.get_response(check_client_disconnected)

        assert result == ""
        mock_save_snapshot.assert_called()


@pytest.mark.asyncio
async def test_get_response_completion_timeout(response_controller, mock_page):
    """Test response retrieval when completion detection times out."""
    check_client_disconnected = MagicMock(return_value=False)
    expected_content = "Partial content"

    # Mock locators
    response_container = AsyncMock()
    response_element = AsyncMock()

    mock_page.locator.return_value.last = response_container
    response_container.locator.return_value = response_element

    with (
        patch(
            "browser_utils.page_controller_modules.response.expect_async",
            new_callable=MagicMock,
        ) as mock_expect,
        patch(
            "browser_utils.page_controller_modules.response._wait_for_response_completion",
            new_callable=AsyncMock,
        ) as mock_wait,
        patch(
            "browser_utils.page_controller_modules.response._get_final_response_content",
            new_callable=AsyncMock,
        ) as mock_get_content,
    ):
        mock_expect.return_value.to_be_attached = AsyncMock()
        mock_wait.return_value = False  # Simulate timeout/failure
        mock_get_content.return_value = expected_content

        result = await response_controller.get_response(check_client_disconnected)

        assert result == expected_content
        # Should still try to get content even if completion check failed
        mock_get_content.assert_called()


@pytest.mark.asyncio
async def test_get_response_cancelled_error(response_controller, mock_page):
    """Test get_response re-raises CancelledError."""
    import asyncio

    check_client_disconnected = MagicMock(return_value=False)

    # Mock locators
    response_container = AsyncMock()
    response_element = AsyncMock()

    mock_page.locator.return_value.last = response_container
    response_container.locator.return_value = response_element

    with patch(
        "browser_utils.page_controller_modules.response.expect_async",
        new_callable=MagicMock,
    ) as mock_expect:
        # Simulate CancelledError
        mock_expect.return_value.to_be_attached = AsyncMock(
            side_effect=asyncio.CancelledError()
        )

        with pytest.raises(asyncio.CancelledError):
            await response_controller.get_response(check_client_disconnected)


@pytest.mark.asyncio
async def test_get_response_general_exception(response_controller, mock_page):
    """Test get_response saves snapshot for general exceptions."""
    check_client_disconnected = MagicMock(return_value=False)

    # Mock locators
    response_container = AsyncMock()
    response_element = AsyncMock()

    mock_page.locator.return_value.last = response_container
    response_container.locator.return_value = response_element

    with (
        patch(
            "browser_utils.page_controller_modules.response.expect_async",
            new_callable=MagicMock,
        ) as mock_expect,
        patch(
            "browser_utils.page_controller_modules.response.save_error_snapshot",
            new_callable=AsyncMock,
        ) as mock_save_snapshot,
    ):
        # Simulate general exception (not ClientDisconnectedError)
        mock_expect.return_value.to_be_attached = AsyncMock(
            side_effect=ValueError("Test error")
        )

        with pytest.raises(ValueError):
            await response_controller.get_response(check_client_disconnected)

        # Should save error snapshot (line 79)
        mock_save_snapshot.assert_called_once()
        assert "get_response_error_" in str(mock_save_snapshot.call_args)


@pytest.mark.asyncio
async def test_ensure_generation_stopped_button_enabled(response_controller, mock_page):
    """Test ensure_generation_stopped when button is enabled."""
    check_client_disconnected = MagicMock(return_value=None)

    submit_button = AsyncMock()
    mock_page.locator.return_value = submit_button

    # Button is enabled, should click it
    submit_button.is_enabled = AsyncMock(return_value=True)
    submit_button.click = AsyncMock()

    with patch(
        "browser_utils.page_controller_modules.response.expect_async",
        new_callable=MagicMock,
    ) as mock_expect:
        mock_expect.return_value.to_be_disabled = AsyncMock()

        await response_controller.ensure_generation_stopped(check_client_disconnected)

        # Should check if enabled
        submit_button.is_enabled.assert_called()
        # Should click button (lines 100-104)
        submit_button.click.assert_called_once()
        # Should wait for disabled
        mock_expect.return_value.to_be_disabled.assert_called()


@pytest.mark.asyncio
async def test_ensure_generation_stopped_button_disabled(
    response_controller, mock_page
):
    """Test ensure_generation_stopped when button is already disabled."""
    check_client_disconnected = MagicMock(return_value=None)

    submit_button = AsyncMock()
    mock_page.locator.return_value = submit_button

    # Button is already disabled
    submit_button.is_enabled = AsyncMock(return_value=False)
    submit_button.click = AsyncMock()

    with patch(
        "browser_utils.page_controller_modules.response.expect_async",
        new_callable=MagicMock,
    ) as mock_expect:
        mock_expect.return_value.to_be_disabled = AsyncMock()

        await response_controller.ensure_generation_stopped(check_client_disconnected)

        # Should check if enabled
        submit_button.is_enabled.assert_called()
        # Should NOT click button (lines 105-106)
        submit_button.click.assert_not_called()
        # Should still wait for disabled
        mock_expect.return_value.to_be_disabled.assert_called()


@pytest.mark.asyncio
async def test_ensure_generation_stopped_button_check_exception(
    response_controller, mock_page
):
    """Test ensure_generation_stopped handles button check exceptions."""
    check_client_disconnected = MagicMock(return_value=None)

    submit_button = AsyncMock()
    mock_page.locator.return_value = submit_button

    # Button check raises exception (lines 107-110)
    submit_button.is_enabled = AsyncMock(side_effect=ValueError("Button check failed"))

    with patch(
        "browser_utils.page_controller_modules.response.expect_async",
        new_callable=MagicMock,
    ) as mock_expect:
        mock_expect.return_value.to_be_disabled = AsyncMock()

        # Should not raise, just log warning
        await response_controller.ensure_generation_stopped(check_client_disconnected)

        # Should still wait for disabled
        mock_expect.return_value.to_be_disabled.assert_called()


@pytest.mark.asyncio
async def test_ensure_generation_stopped_final_wait_exception(
    response_controller, mock_page
):
    """Test ensure_generation_stopped handles final wait exceptions."""
    check_client_disconnected = MagicMock(return_value=None)

    submit_button = AsyncMock()
    mock_page.locator.return_value = submit_button

    submit_button.is_enabled = AsyncMock(return_value=False)

    with patch(
        "browser_utils.page_controller_modules.response.expect_async",
        new_callable=MagicMock,
    ) as mock_expect:
        # Final wait raises timeout exception (lines 117-120)
        mock_expect.return_value.to_be_disabled = AsyncMock(
            side_effect=ValueError("Timeout waiting for disabled")
        )

        # Should not raise, just log warning
        await response_controller.ensure_generation_stopped(check_client_disconnected)


@pytest.mark.asyncio
async def test_ensure_generation_stopped_cancelled_error_button_check(
    response_controller, mock_page
):
    """Test ensure_generation_stopped re-raises CancelledError during button check."""
    import asyncio

    check_client_disconnected = MagicMock(return_value=None)

    submit_button = AsyncMock()
    mock_page.locator.return_value = submit_button

    # Button check raises CancelledError (line 108-109)
    submit_button.is_enabled = AsyncMock(side_effect=asyncio.CancelledError())

    with pytest.raises(asyncio.CancelledError):
        await response_controller.ensure_generation_stopped(check_client_disconnected)


@pytest.mark.asyncio
async def test_ensure_generation_stopped_cancelled_error_final_wait(
    response_controller, mock_page
):
    """Test ensure_generation_stopped re-raises CancelledError during final wait."""
    import asyncio

    check_client_disconnected = MagicMock(return_value=None)

    submit_button = AsyncMock()
    mock_page.locator.return_value = submit_button

    submit_button.is_enabled = AsyncMock(return_value=False)

    with patch(
        "browser_utils.page_controller_modules.response.expect_async",
        new_callable=MagicMock,
    ) as mock_expect:
        # Final wait raises CancelledError (lines 118-119)
        mock_expect.return_value.to_be_disabled = AsyncMock(
            side_effect=asyncio.CancelledError()
        )

        with pytest.raises(asyncio.CancelledError):
            await response_controller.ensure_generation_stopped(
                check_client_disconnected
            )
