import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from playwright.async_api import Error as PlaywrightAsyncError

from browser_utils.operations import (
    _get_final_response_content,
    _handle_model_list_response,
    _wait_for_response_completion,
    detect_and_extract_page_error,
    get_raw_text_content,
    get_response_via_copy_button,
    get_response_via_edit_button,
)


@pytest.fixture(autouse=True)
def mock_check_quota_limit():
    with patch(
        "browser_utils.operations.check_quota_limit", new_callable=AsyncMock
    ) as m:
        yield m


def create_robust_locator(count_val=1, text=""):
    loc = MagicMock()
    loc.hover = AsyncMock()
    loc.click = AsyncMock()
    loc.fill = AsyncMock()
    loc.wait_for = AsyncMock()
    loc.inner_text = AsyncMock(return_value=text)
    loc.text_content = AsyncMock(return_value=text)
    loc.get_attribute = AsyncMock(return_value=None)
    loc.input_value = AsyncMock(return_value=text)
    loc.is_visible = AsyncMock(return_value=True)
    loc.is_enabled = AsyncMock(return_value=True)
    loc.is_disabled = AsyncMock(return_value=False)
    loc.count = AsyncMock(return_value=count_val)
    loc.all = AsyncMock(return_value=[loc] if count_val > 0 else [])
    loc.scroll_into_view_if_needed = AsyncMock()

    # Chaining properties and methods
    loc.locator = MagicMock(return_value=loc)
    loc.get_by_label = MagicMock(return_value=loc)
    loc.get_by_role = MagicMock(return_value=loc)
    loc.get_by_text = MagicMock(return_value=loc)
    loc.first = loc
    loc.last = loc
    return loc


def make_mock_page():
    page = MagicMock()
    page.goto = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.click = AsyncMock()
    page.fill = AsyncMock()
    page.evaluate = AsyncMock()
    page.content = AsyncMock(return_value="<html></html>")
    page.screenshot = AsyncMock()
    page.is_closed = MagicMock(return_value=False)
    page.url = "https://example.com"

    default_locator = create_robust_locator()
    page.locator = MagicMock(return_value=default_locator)
    page.get_by_role = MagicMock(return_value=default_locator)
    page.get_by_label = MagicMock(return_value=default_locator)
    page.get_by_text = MagicMock(return_value=default_locator)

    # Context
    page.context = MagicMock()
    page.context.cookies = AsyncMock(return_value=[])

    return page


@pytest.fixture
def mock_page():
    return make_mock_page()


@pytest.fixture(autouse=True)
def mock_server_state(mock_page):
    mock_state = MagicMock()
    mock_state.page_instance = mock_page
    mock_state.browser_instance = MagicMock()
    mock_state.browser_instance.is_connected = MagicMock(return_value=True)

    # For test_handle_model_list_response_success
    mock_state.parsed_model_list = []
    mock_state.global_model_list_raw_json = None
    mock_state.model_list_fetch_event = MagicMock()

    with patch("api_utils.server_state.state", mock_state):
        yield mock_state


@pytest.mark.asyncio
async def test_get_raw_text_content_pre_element():
    """Test getting text from pre element."""
    element = create_robust_locator()
    pre_element = create_robust_locator(text="pre content")

    element.locator.return_value.last = pre_element
    result = await get_raw_text_content(element, "old", "req_id")
    assert result == "pre content"


@pytest.mark.asyncio
async def test_get_raw_text_content_fallback():
    """Test fallback to element text when pre not found."""
    element = create_robust_locator(text="element content")
    pre_element = create_robust_locator()

    element.locator.return_value.last = pre_element
    pre_element.wait_for.side_effect = PlaywrightAsyncError("Not found")

    result = await get_raw_text_content(element, "old", "req_id")
    assert result == "element content"


@pytest.mark.asyncio
async def test_handle_model_list_response_success():
    """Test handling successful model list response."""
    response = MagicMock()
    response.url = "https://ai.google.dev/api/models"
    response.ok = True
    response.json = AsyncMock(
        return_value={
            "models": [
                {
                    "name": "models/gemini-pro",
                    "displayName": "Gemini Pro",
                    "description": "Best model",
                }
            ]
        }
    )

    await _handle_model_list_response(response)


@pytest.mark.asyncio
async def test_detect_and_extract_page_error_found(mock_page):
    """Test detecting page error."""
    error_locator = create_robust_locator()
    message_locator = create_robust_locator(text="Error message")

    mock_page.locator.return_value.last = error_locator
    error_locator.locator.return_value = message_locator

    result = await detect_and_extract_page_error(mock_page, "req_id")
    assert result == "Error message"


@pytest.mark.asyncio
async def test_detect_and_extract_page_error_not_found(mock_page):
    """Test detecting page error when none exists."""
    error_locator = create_robust_locator()
    mock_page.locator.return_value.last = error_locator
    error_locator.wait_for.side_effect = PlaywrightAsyncError("Timeout")

    result = await detect_and_extract_page_error(mock_page, "req_id")
    assert result is None


@pytest.mark.asyncio
async def test_get_response_via_edit_button_success(mock_page):
    """Test getting response via edit button."""
    check_disconnect = MagicMock()

    # Setup locator chain
    last_msg = create_robust_locator()
    edit_btn = create_robust_locator()
    textarea = create_robust_locator(text="Response content")

    mock_page.locator.return_value.last = last_msg
    last_msg.get_by_label.side_effect = (
        lambda label: edit_btn if label == "Edit" else create_robust_locator()
    )
    last_msg.locator.side_effect = (
        lambda selector: textarea
        if "ms-autosize-textarea" in selector
        else create_robust_locator()
    )
    textarea.get_attribute.return_value = "Response content"

    # Mock playwright expect
    with patch("playwright.async_api.expect", new_callable=MagicMock) as mock_expect:
        mock_expect_obj = MagicMock()
        mock_expect_obj.to_be_visible = AsyncMock()
        mock_expect.return_value = mock_expect_obj

        result = await get_response_via_edit_button(
            mock_page, "req_id", check_disconnect
        )

        assert result == "Response content"


@pytest.mark.asyncio
async def test_get_response_via_copy_button_success(mock_page):
    """Test getting response via copy button."""
    check_disconnect = MagicMock()

    # Setup locators
    last_msg = create_robust_locator()
    mock_page.locator.return_value.last = last_msg

    more_opts = create_robust_locator()
    last_msg.get_by_label.return_value = more_opts

    copy_btn = create_robust_locator()
    mock_page.get_by_role.return_value = copy_btn

    # Setup actions
    mock_page.evaluate.return_value = "Copied content"

    with patch("playwright.async_api.expect", new_callable=MagicMock) as mock_expect:
        mock_expect_obj = MagicMock()
        mock_expect_obj.to_be_visible = AsyncMock()
        mock_expect.return_value = mock_expect_obj

        result = await get_response_via_copy_button(
            mock_page, "req_id", check_disconnect
        )
        assert result == "Copied content"


@pytest.mark.asyncio
async def test_wait_for_response_completion_success(mock_page):
    """Test waiting for response completion."""
    prompt_area = create_robust_locator(text="")
    submit_btn = create_robust_locator()
    edit_btn = create_robust_locator()
    check_disconnect = MagicMock()

    # Setup states
    submit_btn.is_disabled.return_value = True
    edit_btn.is_visible.return_value = True

    result = await _wait_for_response_completion(
        mock_page,
        prompt_area,
        submit_btn,
        edit_btn,
        "req_id",
        check_disconnect,
        None,  # current_chat_id
        0,  # prompt_length
        timeout=1.0,
        initial_wait_ms=0,
    )
    assert result is True


@pytest.mark.asyncio
async def test_get_final_response_content_edit_success(mock_page):
    """Test getting final content via edit button."""
    check_disconnect = MagicMock()

    with patch(
        "browser_utils.operations.get_response_via_edit_button",
        new_callable=AsyncMock,
    ) as mock_edit:
        mock_edit.return_value = "Content"

        result = await _get_final_response_content(
            mock_page, "req_id", check_disconnect
        )
        assert result == "Content"


@pytest.mark.asyncio
async def test_get_final_response_content_fallback_copy(mock_page):
    """Test fallback to copy button when edit fails."""
    check_disconnect = MagicMock()

    with (
        patch(
            "browser_utils.operations.get_response_via_edit_button",
            new_callable=AsyncMock,
        ) as mock_edit,
        patch(
            "browser_utils.operations.get_response_via_copy_button",
            new_callable=AsyncMock,
        ) as mock_copy,
    ):
        mock_edit.return_value = None
        mock_copy.return_value = "Content"

        result = await _get_final_response_content(
            mock_page, "req_id", check_disconnect
        )
        assert result == "Content"


@pytest.mark.asyncio
async def test_get_raw_text_content_pre_error_with_debug():
    """Test pre element inner_text error with debug logging enabled."""
    element = create_robust_locator()
    pre_element = create_robust_locator()

    element.locator.return_value.last = pre_element
    pre_element.inner_text.side_effect = PlaywrightAsyncError(
        "Failed to get inner text"
    )

    with patch("config.DEBUG_LOGS_ENABLED", True):
        result = await get_raw_text_content(element, "old", "req_id")
        assert result == "old"


@pytest.mark.asyncio
async def test_get_raw_text_content_element_error_with_debug():
    """Test element inner_text error with debug logging enabled."""
    element = create_robust_locator()
    pre_element = create_robust_locator()

    element.locator.return_value.last = pre_element
    pre_element.wait_for.side_effect = PlaywrightAsyncError("Not found")
    element.inner_text.side_effect = PlaywrightAsyncError("Failed to get text")

    with patch("config.DEBUG_LOGS_ENABLED", True):
        result = await get_raw_text_content(element, "old", "req_id")
        assert result == "old"


@pytest.mark.asyncio
async def test_get_raw_text_content_element_not_attached_with_debug():
    """Test response element not attached with debug logging."""
    element = create_robust_locator()
    element.wait_for.side_effect = PlaywrightAsyncError("Element not attached")

    with patch("config.DEBUG_LOGS_ENABLED", True):
        result = await get_raw_text_content(element, "previous", "req_id")
        assert result == "previous"


@pytest.mark.asyncio
async def test_get_raw_text_content_unexpected_error():
    """Test unexpected error in get_raw_text_content."""
    element = create_robust_locator()
    element.wait_for.side_effect = RuntimeError("Unexpected")

    result = await get_raw_text_content(element, "prev", "req_id")
    assert result == "prev"


@pytest.mark.asyncio
async def test_get_raw_text_content_text_updated_with_debug():
    """Test text update logging when DEBUG_LOGS_ENABLED is True."""
    element = create_robust_locator()
    pre_element = create_robust_locator(text="new text content")

    element.locator.return_value.last = pre_element
    result = await get_raw_text_content(element, "old text", "req_id")
    assert result == "new text content"


@pytest.mark.asyncio
async def test_get_raw_text_content_cancelled_error():
    """Test CancelledError is properly re-raised."""
    element = create_robust_locator()
    element.wait_for.side_effect = asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await get_raw_text_content(element, "old", "req_id")


@pytest.mark.asyncio
async def test_get_response_via_edit_button_hover_failure(mock_page):
    """Test edit button flow when hover fails."""
    check_disconnect = MagicMock()

    last_msg = create_robust_locator()
    edit_btn = create_robust_locator()
    finish_btn = create_robust_locator()
    textarea = create_robust_locator(text="Response")

    mock_page.locator.return_value.last = last_msg
    last_msg.get_by_label.side_effect = (
        lambda label: edit_btn if label == "Edit" else finish_btn
    )
    last_msg.locator.return_value = textarea
    textarea.locator.return_value = textarea

    # Hover fails but we continue
    last_msg.hover.side_effect = RuntimeError("Hover failed")

    with patch("playwright.async_api.expect") as mock_expect:
        mock_expect_obj = MagicMock()
        mock_expect_obj.to_be_visible = AsyncMock()
        mock_expect.return_value = mock_expect_obj

        result = await get_response_via_edit_button(
            mock_page, "req_id", check_disconnect
        )
        assert result == "Response"


@pytest.mark.asyncio
async def test_get_response_via_edit_button_cancelled_during_hover(mock_page):
    """Test CancelledError during hover."""
    check_disconnect = MagicMock()

    last_msg = create_robust_locator()
    mock_page.locator.return_value.last = last_msg
    last_msg.hover.side_effect = asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await get_response_via_edit_button(mock_page, "req_id", check_disconnect)


@pytest.mark.asyncio
async def test_get_response_via_edit_button_edit_button_failure(mock_page):
    """Test when edit button is not visible or click fails."""
    check_disconnect = MagicMock()

    last_msg = create_robust_locator()
    edit_btn = create_robust_locator()

    mock_page.locator.return_value.last = last_msg
    last_msg.get_by_label.return_value = edit_btn

    with (
        patch("playwright.async_api.expect") as mock_expect,
        patch(
            "browser_utils.operations.save_error_snapshot",
            new_callable=AsyncMock,
        ) as mock_save,
    ):
        mock_expect_obj = MagicMock()
        mock_expect_obj.to_be_visible.side_effect = PlaywrightAsyncError("Not visible")
        mock_expect.return_value = mock_expect_obj

        result = await get_response_via_edit_button(
            mock_page, "req_id", check_disconnect
        )

        assert result is None
        mock_save.assert_called_once()


@pytest.mark.asyncio
async def test_get_response_via_edit_button_cancelled_during_edit_click(mock_page):
    """Test CancelledError when clicking edit button."""
    check_disconnect = MagicMock()

    last_msg = create_robust_locator()
    edit_btn = create_robust_locator()

    mock_page.locator.return_value.last = last_msg
    last_msg.get_by_label.return_value = edit_btn

    with patch("playwright.async_api.expect") as mock_expect:
        mock_expect_obj = MagicMock()
        mock_expect_obj.to_be_visible.side_effect = asyncio.CancelledError
        mock_expect.return_value = mock_expect_obj

        with pytest.raises(asyncio.CancelledError):
            await get_response_via_edit_button(mock_page, "req_id", check_disconnect)


@pytest.mark.asyncio
async def test_get_response_via_edit_button_data_value_error(mock_page):
    """Test when get_attribute for data-value fails."""
    check_disconnect = MagicMock()

    last_msg = create_robust_locator()
    edit_btn = create_robust_locator()
    finish_btn = create_robust_locator()
    autosize_textarea = create_robust_locator()
    actual_textarea = create_robust_locator(text="Input value content")

    mock_page.locator.return_value.last = last_msg
    last_msg.get_by_label.side_effect = (
        lambda label: edit_btn if label == "Edit" else finish_btn
    )

    def locator_side_effect(selector):
        if "ms-autosize-textarea" in selector:
            return autosize_textarea
        if "textarea" in selector:
            return actual_textarea
        return create_robust_locator()

    last_msg.locator.side_effect = locator_side_effect
    autosize_textarea.locator.side_effect = locator_side_effect

    # data-value fails, input_value succeeds
    autosize_textarea.get_attribute.side_effect = PlaywrightAsyncError(
        "Attribute error"
    )

    with patch("playwright.async_api.expect") as mock_expect:
        mock_expect_obj = MagicMock()
        mock_expect_obj.to_be_visible = AsyncMock()
        mock_expect.return_value = mock_expect_obj

        result = await get_response_via_edit_button(
            mock_page, "req_id", check_disconnect
        )

        assert result == "Input value content"


@pytest.mark.asyncio
async def test_get_response_via_edit_button_cancelled_during_data_value(mock_page):
    """Test CancelledError during get_attribute."""
    check_disconnect = MagicMock()

    last_msg = create_robust_locator()
    edit_btn = create_robust_locator()
    textarea = create_robust_locator()

    mock_page.locator.return_value.last = last_msg
    last_msg.get_by_label.return_value = edit_btn
    last_msg.locator.return_value = textarea
    textarea.get_attribute.side_effect = asyncio.CancelledError

    with patch("playwright.async_api.expect") as mock_expect:
        mock_expect_obj = MagicMock()
        mock_expect_obj.to_be_visible = AsyncMock()
        mock_expect.return_value = mock_expect_obj

        with pytest.raises(asyncio.CancelledError):
            await get_response_via_edit_button(mock_page, "req_id", check_disconnect)


@pytest.mark.asyncio
async def test_get_response_via_edit_button_input_value_fallback(mock_page):
    """Test fallback to input_value when data-value is None."""
    check_disconnect = MagicMock()

    last_msg = create_robust_locator()
    edit_btn = create_robust_locator()
    finish_btn = create_robust_locator()
    autosize_textarea = create_robust_locator()
    actual_textarea = create_robust_locator(text="Fallback content")

    mock_page.locator.return_value.last = last_msg
    last_msg.get_by_label.side_effect = (
        lambda label: edit_btn if label == "Edit" else finish_btn
    )

    def locator_side_effect(selector):
        if "ms-autosize-textarea" in selector:
            return autosize_textarea
        if "textarea" in selector:
            return actual_textarea
        return create_robust_locator()

    last_msg.locator.side_effect = locator_side_effect
    autosize_textarea.locator.side_effect = locator_side_effect

    # data-value returns None, fallback to input_value
    autosize_textarea.get_attribute.return_value = None

    with patch("playwright.async_api.expect") as mock_expect:
        mock_expect_obj = MagicMock()
        mock_expect_obj.to_be_visible = AsyncMock()
        mock_expect.return_value = mock_expect_obj

        result = await get_response_via_edit_button(
            mock_page, "req_id", check_disconnect
        )

        assert result == "Fallback content"


@pytest.mark.asyncio
async def test_get_response_via_edit_button_input_value_error(mock_page):
    """Test when both data-value and input_value fail."""
    check_disconnect = MagicMock()

    last_msg = create_robust_locator()
    edit_btn = create_robust_locator()
    textarea = create_robust_locator()
    actual_textarea = create_robust_locator()

    mock_page.locator.return_value.last = last_msg
    last_msg.get_by_label.return_value = edit_btn

    def locator_side_effect(selector):
        if "ms-autosize-textarea" in selector:
            return textarea
        if "textarea" in selector:
            return actual_textarea
        return create_robust_locator()

    last_msg.locator.side_effect = locator_side_effect
    textarea.locator.side_effect = locator_side_effect

    # Both methods fail
    textarea.get_attribute.return_value = None
    actual_textarea.input_value.side_effect = PlaywrightAsyncError("Input error")

    with patch("playwright.async_api.expect") as mock_expect:
        mock_expect_obj = MagicMock()
        mock_expect_obj.to_be_visible = AsyncMock()
        mock_expect.return_value = mock_expect_obj

        result = await get_response_via_edit_button(
            mock_page, "req_id", check_disconnect
        )

        assert result is None


@pytest.mark.asyncio
async def test_get_response_via_edit_button_cancelled_during_input_value(mock_page):
    """Test CancelledError during input_value."""
    check_disconnect = MagicMock()

    last_msg = create_robust_locator()
    edit_btn = create_robust_locator()
    autosize_textarea = create_robust_locator()
    actual_textarea = create_robust_locator()

    mock_page.locator.return_value.last = last_msg
    last_msg.get_by_label.return_value = edit_btn

    def locator_side_effect(selector):
        if "ms-autosize-textarea" in selector:
            return autosize_textarea
        if "textarea" in selector:
            return actual_textarea
        return create_robust_locator()

    last_msg.locator.side_effect = locator_side_effect
    autosize_textarea.locator.side_effect = locator_side_effect

    autosize_textarea.get_attribute.return_value = None
    actual_textarea.input_value.side_effect = asyncio.CancelledError

    with patch("playwright.async_api.expect") as mock_expect:
        mock_expect_obj = MagicMock()
        mock_expect_obj.to_be_visible = AsyncMock()
        mock_expect.return_value = mock_expect_obj

        with pytest.raises(asyncio.CancelledError):
            await get_response_via_edit_button(mock_page, "req_id", check_disconnect)


@pytest.mark.asyncio
async def test_get_response_via_edit_button_textarea_error(mock_page):
    """Test when textarea locator fails."""
    check_disconnect = MagicMock()

    last_msg = create_robust_locator()
    edit_btn = create_robust_locator()
    textarea = create_robust_locator()

    mock_page.locator.return_value.last = last_msg
    last_msg.get_by_label.return_value = edit_btn
    last_msg.locator.return_value = textarea

    with patch("playwright.async_api.expect") as mock_expect:
        mock_expect_obj = MagicMock()
        mock_expect_obj.to_be_visible.side_effect = [
            None,
            PlaywrightAsyncError("Textarea not visible"),
        ]
        mock_expect.return_value = mock_expect_obj

        result = await get_response_via_edit_button(
            mock_page, "req_id", check_disconnect
        )

        assert result is None


@pytest.mark.asyncio
async def test_get_response_via_edit_button_cancelled_during_textarea(mock_page):
    """Test CancelledError during textarea visibility check."""
    check_disconnect = MagicMock()

    last_msg = create_robust_locator()
    edit_btn = create_robust_locator()
    textarea = create_robust_locator()

    mock_page.locator.return_value.last = last_msg
    last_msg.get_by_label.return_value = edit_btn
    last_msg.locator.return_value = textarea

    with patch("playwright.async_api.expect") as mock_expect:
        mock_expect_obj = MagicMock()

        # First call succeeds (edit button), second fails (textarea)
        async def async_success(*args, **kwargs):
            return None

        mock_expect_obj.to_be_visible.side_effect = [
            async_success(),
            asyncio.CancelledError,
        ]
        mock_expect.return_value = mock_expect_obj

        with pytest.raises(asyncio.CancelledError):
            await get_response_via_edit_button(mock_page, "req_id", check_disconnect)


@pytest.mark.asyncio
async def test_get_response_via_edit_button_finish_button_failure(mock_page):
    """Test when finish edit button fails to click."""
    check_disconnect = MagicMock()

    last_msg = create_robust_locator()
    edit_btn = create_robust_locator()
    finish_btn = create_robust_locator()
    textarea = create_robust_locator(text="Content")

    mock_page.locator.return_value.last = last_msg
    last_msg.get_by_label.side_effect = (
        lambda label: edit_btn if label == "Edit" else finish_btn
    )
    last_msg.locator.return_value = textarea
    textarea.locator.return_value = textarea

    textarea.get_attribute.return_value = "Content"
    finish_btn.click.side_effect = PlaywrightAsyncError("Click failed")

    with (
        patch("playwright.async_api.expect") as mock_expect,
        patch(
            "browser_utils.operations.save_error_snapshot",
            new_callable=AsyncMock,
        ) as mock_save,
    ):
        mock_expect_obj = MagicMock()
        mock_expect_obj.to_be_visible = AsyncMock()
        mock_expect.return_value = mock_expect_obj

        result = await get_response_via_edit_button(
            mock_page, "req_id", check_disconnect
        )

        # Should still return content even if finish button fails
        assert result == "Content"
        mock_save.assert_called_once()


@pytest.mark.asyncio
async def test_get_response_via_edit_button_cancelled_during_finish(mock_page):
    """Test CancelledError when clicking finish button."""
    check_disconnect = MagicMock()

    last_msg = create_robust_locator()
    edit_btn = create_robust_locator()
    finish_btn = create_robust_locator()
    textarea = create_robust_locator(text="Content")

    mock_page.locator.return_value.last = last_msg
    last_msg.get_by_label.side_effect = (
        lambda label: edit_btn if label == "Edit" else finish_btn
    )
    last_msg.locator.return_value = textarea
    textarea.locator.return_value = textarea

    textarea.get_attribute.return_value = "Content"

    with patch("playwright.async_api.expect") as mock_expect:
        mock_expect_obj = MagicMock()

        # Multiple calls: edit visible, textarea visible, finish visible (cancelled)
        async def async_success(*args, **kwargs):
            return None

        mock_expect_obj.to_be_visible.side_effect = [
            async_success(),
            async_success(),
            asyncio.CancelledError,
        ]
        mock_expect.return_value = mock_expect_obj

        with pytest.raises(asyncio.CancelledError):
            await get_response_via_edit_button(mock_page, "req_id", check_disconnect)


@pytest.mark.asyncio
async def test_get_response_via_edit_button_skip_finish_on_textarea_failure(mock_page):
    """Test that finish button is skipped when textarea reading fails."""
    check_disconnect = MagicMock()

    last_msg = create_robust_locator()
    edit_btn = create_robust_locator()
    textarea = create_robust_locator()

    mock_page.locator.return_value.last = last_msg
    last_msg.get_by_label.return_value = edit_btn
    last_msg.locator.return_value = textarea

    with patch("playwright.async_api.expect") as mock_expect:
        # Edit button visible, textarea not visible
        mock_expect_obj = MagicMock()
        mock_expect_obj.to_be_visible.side_effect = [
            None,
            PlaywrightAsyncError("Textarea not visible"),
        ]
        mock_expect.return_value = mock_expect_obj

        result = await get_response_via_edit_button(
            mock_page, "req_id", check_disconnect
        )

        # Should return None and skip finish button
        assert result is None


@pytest.mark.asyncio
async def test_get_response_via_edit_button_client_disconnected(mock_page):
    """Test ClientDisconnectedError is re-raised."""
    from models import ClientDisconnectedError

    check_disconnect = MagicMock(side_effect=ClientDisconnectedError("Disconnected"))

    with pytest.raises(ClientDisconnectedError):
        await get_response_via_edit_button(mock_page, "req_id", check_disconnect)


@pytest.mark.asyncio
async def test_get_response_via_edit_button_cancelled_top_level(mock_page):
    """Test top-level CancelledError handling."""
    check_disconnect = MagicMock()

    last_msg = create_robust_locator()
    mock_page.locator.return_value.last = last_msg
    last_msg.hover.side_effect = asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await get_response_via_edit_button(mock_page, "req_id", check_disconnect)


@pytest.mark.asyncio
async def test_get_response_via_edit_button_unexpected_error(mock_page):
    """Test unexpected exception handling."""
    check_disconnect = MagicMock()

    last_msg = create_robust_locator()
    mock_page.locator.return_value.last = last_msg
    last_msg.hover.side_effect = RuntimeError("Unexpected error")

    with patch(
        "browser_utils.operations.save_error_snapshot",
        new_callable=AsyncMock,
    ) as mock_save:
        result = await get_response_via_edit_button(
            mock_page, "req_id", check_disconnect
        )

        assert result is None
        mock_save.assert_called_once()


@pytest.mark.asyncio
async def test_get_response_via_copy_button_more_options_failure(mock_page):
    """Test when more options button fails."""
    check_disconnect = MagicMock()

    last_msg = create_robust_locator()
    more_opts = create_robust_locator()

    mock_page.locator.return_value.last = last_msg
    last_msg.get_by_label.return_value = more_opts

    with (
        patch("playwright.async_api.expect") as mock_expect,
        patch(
            "browser_utils.operations.save_error_snapshot",
            new_callable=AsyncMock,
        ) as mock_save,
    ):
        mock_expect_obj = MagicMock()
        mock_expect_obj.to_be_visible.side_effect = PlaywrightAsyncError("Not visible")
        mock_expect.return_value = mock_expect_obj

        result = await get_response_via_copy_button(
            mock_page, "req_id", check_disconnect
        )

        assert result is None
        mock_save.assert_called_once()


@pytest.mark.asyncio
async def test_get_response_via_copy_button_cancelled_during_more_options(mock_page):
    """Test CancelledError when clicking more options."""
    check_disconnect = MagicMock()

    last_msg = create_robust_locator()
    mock_page.locator.return_value.last = last_msg

    with patch("playwright.async_api.expect") as mock_expect:
        mock_expect_obj = MagicMock()
        mock_expect_obj.to_be_visible.side_effect = asyncio.CancelledError
        mock_expect.return_value = mock_expect_obj

        with pytest.raises(asyncio.CancelledError):
            await get_response_via_copy_button(mock_page, "req_id", check_disconnect)


@pytest.mark.asyncio
async def test_get_response_via_copy_button_copy_button_failure(mock_page):
    """Test when copy markdown button fails."""
    check_disconnect = MagicMock()

    last_msg = create_robust_locator()
    more_opts = create_robust_locator()
    copy_btn = create_robust_locator()

    mock_page.locator.return_value.last = last_msg
    last_msg.get_by_label.return_value = more_opts
    mock_page.get_by_role.return_value = copy_btn

    with (
        patch("playwright.async_api.expect") as mock_expect,
        patch(
            "browser_utils.operations.save_error_snapshot",
            new_callable=AsyncMock,
        ) as mock_save,
    ):
        mock_expect_obj = MagicMock()
        # More options visible, copy button not visible
        mock_expect_obj.to_be_visible.side_effect = [
            None,
            PlaywrightAsyncError("Copy button not visible"),
        ]
        mock_expect.return_value = mock_expect_obj

        result = await get_response_via_copy_button(
            mock_page, "req_id", check_disconnect
        )

        assert result is None
        mock_save.assert_called_once()


@pytest.mark.asyncio
async def test_get_response_via_copy_button_cancelled_during_copy_click(mock_page):
    """Test CancelledError when clicking copy button."""
    check_disconnect = MagicMock()

    last_msg = create_robust_locator()
    more_opts = create_robust_locator()

    mock_page.locator.return_value.last = last_msg
    last_msg.get_by_label.return_value = more_opts

    with patch("playwright.async_api.expect") as mock_expect:
        mock_expect_obj = MagicMock()

        # More options visible, then cancelled on copy button
        async def async_success(*args, **kwargs):
            return None

        mock_expect_obj.to_be_visible.side_effect = [
            async_success(),
            asyncio.CancelledError,
        ]
        mock_expect.return_value = mock_expect_obj

        with pytest.raises(asyncio.CancelledError):
            await get_response_via_copy_button(mock_page, "req_id", check_disconnect)


@pytest.mark.asyncio
async def test_get_response_via_copy_button_copy_not_successful(mock_page):
    """Test when copy_success flag is False."""
    check_disconnect = MagicMock()

    last_msg = create_robust_locator()
    more_opts = create_robust_locator()
    copy_btn = create_robust_locator()

    mock_page.locator.return_value.last = last_msg
    last_msg.get_by_label.return_value = more_opts
    mock_page.get_by_role.return_value = copy_btn

    with patch("playwright.async_api.expect") as mock_expect:
        mock_expect_obj = MagicMock()
        mock_expect_obj.to_be_visible = AsyncMock()
        mock_expect.return_value = mock_expect_obj

        copy_btn.click.side_effect = PlaywrightAsyncError("Silent failure")

        with patch(
            "browser_utils.operations.save_error_snapshot",
            new_callable=AsyncMock,
        ):
            result = await get_response_via_copy_button(
                mock_page, "req_id", check_disconnect
            )
            assert result is None


@pytest.mark.asyncio
async def test_get_response_via_copy_button_clipboard_empty(mock_page):
    """Test when clipboard content is empty."""
    check_disconnect = MagicMock()

    last_msg = create_robust_locator()
    more_opts = create_robust_locator()
    copy_btn = create_robust_locator()

    mock_page.locator.return_value.last = last_msg
    last_msg.get_by_label.return_value = more_opts
    mock_page.get_by_role.return_value = copy_btn
    mock_page.evaluate.return_value = ""  # Empty clipboard

    with patch("playwright.async_api.expect") as mock_expect:
        mock_expect_obj = MagicMock()
        mock_expect_obj.to_be_visible = AsyncMock()
        mock_expect.return_value = mock_expect_obj

        result = await get_response_via_copy_button(
            mock_page, "req_id", check_disconnect
        )

        assert result is None


@pytest.mark.asyncio
async def test_get_response_via_copy_button_clipboard_read_error(mock_page):
    """Test clipboard read failure."""
    check_disconnect = MagicMock()

    last_msg = create_robust_locator()
    more_opts = create_robust_locator()
    copy_btn = create_robust_locator()

    mock_page.locator.return_value.last = last_msg
    last_msg.get_by_label.return_value = more_opts
    mock_page.get_by_role.return_value = copy_btn
    mock_page.evaluate.side_effect = PlaywrightAsyncError(
        "clipboard-read permission denied"
    )

    with (
        patch("playwright.async_api.expect") as mock_expect,
        patch(
            "browser_utils.operations.save_error_snapshot",
            new_callable=AsyncMock,
        ) as mock_save,
    ):
        mock_expect_obj = MagicMock()
        mock_expect_obj.to_be_visible = AsyncMock()
        mock_expect.return_value = mock_expect_obj

        result = await get_response_via_copy_button(
            mock_page, "req_id", check_disconnect
        )

        assert result is None
        mock_save.assert_called_once()


@pytest.mark.asyncio
async def test_get_response_via_copy_button_clipboard_read_other_error(mock_page):
    """Test clipboard read with non-permission error."""
    check_disconnect = MagicMock()

    last_msg = create_robust_locator()
    more_opts = create_robust_locator()
    copy_btn = create_robust_locator()

    mock_page.locator.return_value.last = last_msg
    last_msg.get_by_label.return_value = more_opts
    mock_page.get_by_role.return_value = copy_btn
    mock_page.evaluate.side_effect = PlaywrightAsyncError("Network error")

    with (
        patch("playwright.async_api.expect") as mock_expect,
        patch(
            "browser_utils.operations.save_error_snapshot",
            new_callable=AsyncMock,
        ) as mock_save,
    ):
        mock_expect_obj = MagicMock()
        mock_expect_obj.to_be_visible = AsyncMock()
        mock_expect.return_value = mock_expect_obj

        result = await get_response_via_copy_button(
            mock_page, "req_id", check_disconnect
        )

        assert result is None
        mock_save.assert_called_once()


@pytest.mark.asyncio
async def test_get_response_via_copy_button_cancelled_during_clipboard(mock_page):
    """Test CancelledError during clipboard read."""
    check_disconnect = MagicMock()

    last_msg = create_robust_locator()
    more_opts = create_robust_locator()
    copy_btn = create_robust_locator()

    mock_page.locator.return_value.last = last_msg
    last_msg.get_by_label.return_value = more_opts
    mock_page.get_by_role.return_value = copy_btn
    mock_page.evaluate.side_effect = asyncio.CancelledError

    with patch("playwright.async_api.expect") as mock_expect:
        mock_expect_obj = MagicMock()
        mock_expect_obj.to_be_visible = AsyncMock()
        mock_expect.return_value = mock_expect_obj

        with pytest.raises(asyncio.CancelledError):
            await get_response_via_copy_button(mock_page, "req_id", check_disconnect)


@pytest.mark.asyncio
async def test_get_response_via_copy_button_unexpected_error(mock_page):
    """Test unexpected exception handling."""
    check_disconnect = MagicMock()

    last_msg = create_robust_locator()
    mock_page.locator.return_value.last = last_msg
    last_msg.hover.side_effect = RuntimeError("Unexpected")

    with patch(
        "browser_utils.operations.save_error_snapshot",
        new_callable=AsyncMock,
    ) as mock_save:
        result = await get_response_via_copy_button(
            mock_page, "req_id", check_disconnect
        )

        assert result is None
        mock_save.assert_called_once()


@pytest.mark.asyncio
async def test_wait_for_response_completion_client_disconnect_early(mock_page):
    """Test client disconnect at loop start."""
    from models import ClientDisconnectedError

    prompt_area = create_robust_locator()
    submit_btn = create_robust_locator()
    edit_btn = create_robust_locator()
    check_disconnect = MagicMock(side_effect=ClientDisconnectedError("Disconnected"))

    result = await _wait_for_response_completion(
        mock_page,
        prompt_area,
        submit_btn,
        edit_btn,
        "req_id",
        check_disconnect,
        None,  # current_chat_id
        0,  # prompt_length
        timeout=1.0,
        initial_wait_ms=0,
    )

    assert result is False


@pytest.mark.asyncio
async def test_wait_for_response_completion_timeout(mock_page):
    """Test timeout before completion."""
    prompt_area = create_robust_locator(text="text")
    submit_btn = create_robust_locator()
    edit_btn = create_robust_locator()
    check_disconnect = MagicMock()

    # Always return non-completion state
    submit_btn.is_disabled.return_value = False

    with patch(
        "browser_utils.operations.save_error_snapshot",
        new_callable=AsyncMock,
    ) as mock_save:
        result = await _wait_for_response_completion(
            mock_page,
            prompt_area,
            submit_btn,
            edit_btn,
            "req_id",
            check_disconnect,
            None,  # current_chat_id
            0,  # prompt_length
            timeout=0.1,
            initial_wait_ms=0,
        )

        assert result is False
        mock_save.assert_called_once()


@pytest.mark.asyncio
async def test_wait_for_response_completion_client_disconnect_after_timeout_check(
    mock_page,
):
    """Test client disconnect after timeout check."""
    from models import ClientDisconnectedError

    prompt_area = create_robust_locator()
    submit_btn = create_robust_locator()
    edit_btn = create_robust_locator()

    call_count = [0]

    def check_with_delay(msg):
        call_count[0] += 1
        if call_count[0] > 1:
            raise ClientDisconnectedError("Disconnected")

    check_disconnect = MagicMock(side_effect=check_with_delay)

    submit_btn.is_disabled.return_value = True

    result = await _wait_for_response_completion(
        mock_page,
        prompt_area,
        submit_btn,
        edit_btn,
        "req_id",
        check_disconnect,
        None,  # current_chat_id
        0,  # prompt_length
        timeout=5.0,
        initial_wait_ms=0,
    )

    assert result is False


@pytest.mark.asyncio
async def test_wait_for_response_completion_submit_button_timeout(mock_page):
    """Test submit button is_disabled timeout."""
    from playwright.async_api import TimeoutError

    prompt_area = create_robust_locator(text="")
    submit_btn = create_robust_locator()
    edit_btn = create_robust_locator()
    check_disconnect = MagicMock()

    call_count = [0]

    async def submit_timeout(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            raise TimeoutError("Timeout")
        return True

    submit_btn.is_disabled.side_effect = submit_timeout
    edit_btn.is_visible.return_value = True

    result = await _wait_for_response_completion(
        mock_page,
        prompt_area,
        submit_btn,
        edit_btn,
        "req_id",
        check_disconnect,
        None,  # current_chat_id
        0,  # prompt_length
        timeout=5.0,
        initial_wait_ms=0,
    )

    assert result is True


@pytest.mark.asyncio
async def test_wait_for_response_completion_client_disconnect_after_button_check(
    mock_page,
):
    """Test client disconnect after button state check."""
    from models import ClientDisconnectedError

    prompt_area = create_robust_locator()
    submit_btn = create_robust_locator()
    edit_btn = create_robust_locator()

    call_count = [0]

    def check_with_delay(msg):
        call_count[0] += 1
        if call_count[0] > 2:
            raise ClientDisconnectedError("Disconnected")

    check_disconnect = MagicMock(side_effect=check_with_delay)

    submit_btn.is_disabled.return_value = True

    result = await _wait_for_response_completion(
        mock_page,
        prompt_area,
        submit_btn,
        edit_btn,
        "req_id",
        check_disconnect,
        None,  # current_chat_id
        0,  # prompt_length
        timeout=5.0,
        initial_wait_ms=0,
    )

    assert result is False


@pytest.mark.asyncio
async def test_wait_for_response_completion_debug_logging(mock_page):
    """Test debug logging for main conditions."""
    prompt_area = create_robust_locator(text="")
    submit_btn = create_robust_locator()
    edit_btn = create_robust_locator()
    check_disconnect = MagicMock()

    submit_btn.is_disabled.return_value = True
    edit_btn.is_visible.return_value = True

    with patch("config.DEBUG_LOGS_ENABLED", True):
        result = await _wait_for_response_completion(
            mock_page,
            prompt_area,
            submit_btn,
            edit_btn,
            "req_id",
            check_disconnect,
            None,  # current_chat_id
            0,  # prompt_length
            timeout=5.0,
            initial_wait_ms=0,
        )

        assert result is True


@pytest.mark.asyncio
async def test_wait_for_response_completion_edit_button_timeout(mock_page):
    """Test edit button is_visible timeout with debug logging."""
    from playwright.async_api import TimeoutError

    prompt_area = create_robust_locator(text="")
    submit_btn = create_robust_locator()
    edit_btn = create_robust_locator()
    check_disconnect = MagicMock()

    submit_btn.is_disabled.return_value = True

    call_count = [0]

    async def edit_visible_side_effect(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] < 3:
            raise TimeoutError("Edit button not visible yet")
        return True

    edit_btn.is_visible.side_effect = edit_visible_side_effect

    with patch("config.DEBUG_LOGS_ENABLED", True):
        result = await _wait_for_response_completion(
            mock_page,
            prompt_area,
            submit_btn,
            edit_btn,
            "req_id",
            check_disconnect,
            None,  # current_chat_id
            0,  # prompt_length
            timeout=5.0,
            initial_wait_ms=0,
        )

        assert result is True


@pytest.mark.asyncio
async def test_wait_for_response_completion_client_disconnect_after_edit_check(
    mock_page,
):
    """Test client disconnect after edit button check."""
    from models import ClientDisconnectedError

    prompt_area = create_robust_locator()
    submit_btn = create_robust_locator()
    edit_btn = create_robust_locator()

    call_count = [0]

    def check_with_delay(msg):
        call_count[0] += 1
        if call_count[0] > 3:
            raise ClientDisconnectedError("Disconnected")

    check_disconnect = MagicMock(side_effect=check_with_delay)

    submit_btn.is_disabled.return_value = True
    edit_btn.is_visible.return_value = False

    result = await _wait_for_response_completion(
        mock_page,
        prompt_area,
        submit_btn,
        edit_btn,
        "req_id",
        check_disconnect,
        None,  # current_chat_id
        0,  # prompt_length
        timeout=5.0,
        initial_wait_ms=0,
    )

    assert result is False


@pytest.mark.asyncio
async def test_wait_for_response_completion_heuristic_completion(mock_page):
    """Test heuristic completion when conditions met 3+ times."""
    prompt_area = create_robust_locator(text="")
    submit_btn = create_robust_locator()
    edit_btn = create_robust_locator()
    check_disconnect = MagicMock()

    submit_btn.is_disabled.return_value = True
    edit_btn.is_visible.return_value = False

    result = await _wait_for_response_completion(
        mock_page,
        prompt_area,
        submit_btn,
        edit_btn,
        "req_id",
        check_disconnect,
        None,  # current_chat_id
        0,  # prompt_length
        timeout=5.0,
        initial_wait_ms=0,
    )

    assert result is True


@pytest.mark.asyncio
async def test_wait_for_response_completion_conditions_not_met_with_debug(mock_page):
    """Test debug logging when main conditions not met."""
    prompt_area = create_robust_locator()
    submit_btn = create_robust_locator()
    edit_btn = create_robust_locator()
    check_disconnect = MagicMock()

    call_count = [0]

    async def input_value_side_effect():
        call_count[0] += 1
        if call_count[0] < 2:
            return "text"
        return ""

    prompt_area.input_value.side_effect = input_value_side_effect
    submit_btn.is_disabled.return_value = True
    edit_btn.is_visible.return_value = True

    with patch("config.DEBUG_LOGS_ENABLED", True):
        result = await _wait_for_response_completion(
            mock_page,
            prompt_area,
            submit_btn,
            edit_btn,
            "req_id",
            check_disconnect,
            None,  # current_chat_id
            0,  # prompt_length
            timeout=5.0,
            initial_wait_ms=0,
        )

        assert result is True


@pytest.mark.asyncio
async def test_get_final_response_content_all_methods_fail(mock_page):
    """Test when both edit and copy methods fail."""
    check_disconnect = MagicMock()

    with (
        patch(
            "browser_utils.operations.get_response_via_edit_button",
            new_callable=AsyncMock,
        ) as mock_edit,
        patch(
            "browser_utils.operations.get_response_via_copy_button",
            new_callable=AsyncMock,
        ) as mock_copy,
        patch(
            "browser_utils.operations.save_error_snapshot",
            new_callable=AsyncMock,
        ) as mock_save,
    ):
        mock_edit.return_value = None
        mock_copy.return_value = None

        result = await _get_final_response_content(
            mock_page, "req_id", check_disconnect
        )

        assert result is None
        mock_save.assert_called_once()
